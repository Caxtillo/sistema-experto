import json
import re
import asyncio
from datetime import datetime
import csv, io
from fastapi import APIRouter, Query, HTTPException, Request
from fastapi.responses import PlainTextResponse, StreamingResponse, HTMLResponse, Response
from fastapi import WebSocket, WebSocketDisconnect

from core.knowledge_base import KnowledgeBase
from core.inference_engine import InferenceEngine
from core.explanation import ExplanationEngine
from iiot_simulator.sensors import IIoTSimulator, SCENARIOS, RECOMMENDATIONS

from web.limits import limiter

router = APIRouter()
active_connections: set[WebSocket] = set()
kb = KnowledgeBase()
inference = InferenceEngine()


def _require_role(request: Request, min_role: str):
    """Check if the authenticated user has at least the given role.
    Roles hierarchy: admin > supervisor > technician.
    Raises HTTPException(403) if unauthorized."""
    role = request.session.get("role", "")
    role_hierarchy = {"admin": 3, "supervisor": 2, "technician": 1}
    if role_hierarchy.get(role, 0) < role_hierarchy.get(min_role, 0):
        raise HTTPException(403, "No tienes permisos para esta operación")
    return True


def _filter_assets_by_scope(request: Request, assets: list):
    """Filter assets to the user's assigned condominiums for supervisor & technician roles."""
    role = request.session.get("role", "")
    if role in ("technician", "supervisor"):
        condo_ids = request.session.get("condominium_ids", [])
        if condo_ids:
            valid_names = set()
            for cid in condo_ids:
                valid_names.update(_get_condo_asset_names(cid))
            return [a for a in assets if getattr(a, 'name', None) in valid_names]
    return assets


def _get_condo_asset_names(condo_id: int) -> set:
    """Return set of asset names belonging to a condominium."""
    names = set()
    condo = kb.get_condominium(condo_id)
    if not condo:
        return names
    for b in kb.get_buildings(condo_id):
        for r in kb.get_rooms(b.id):
            for a in kb.get_assets_in_room(r.id):
                names.add(a.name)
    return names


def _scope_condo_ids(request: Request) -> list | None:
    """Return list of allowed condominium IDs, or None for all."""
    role = request.session.get("role", "")
    if role in ("technician", "supervisor"):
        return request.session.get("condominium_ids", [])
    return None
explainer = ExplanationEngine(inference)
simulator = IIoTSimulator(base_seed=42)

latest_sensor_values: dict[str, dict] = {}
latest_results: dict[str, dict] = {}
prev_statuses: dict[str, str] = {}
history_cache: dict[str, list] = {}
action_cache: list = []
event_cache = []
_cycle_counter = 0
manual_sources: dict[str, set] = {}  # asset_name -> set of sensor names entered manually
simulated_values: dict[str, dict] = {}  # sim data always writes here
real_values: dict[str, dict] = {}       # manual data always writes here
data_source_mode: dict[str, str] = {}   # "simulated" | "real" per asset, default "simulated"
_dedup_set: set[str | tuple[str, str, int]] = set()  # sync_uuid strings or (asset, sensor, captured_at) for dedup
visible_assets: set[str] | None = None  # None = simulate all; set() = simulate nothing; set of names = simulate only those


def load_asset_instances():
    """Load asset instances from seed mapping and register with simulator.
    Must be called AFTER seed() has run so the mapping file exists."""
    import os
    _instance_mapping_path = os.path.join(os.path.dirname(__file__), "..", "data", "asset_instances.json")
    if os.path.exists(_instance_mapping_path):
        try:
            with open(_instance_mapping_path) as _f:
                _instances = json.load(_f)
            for _name, _base in _instances.items():
                simulator.add_instance(_name, _base)
                _ensure_asset_caches(_name)
        except Exception:
            pass


def _ensure_asset_caches(asset_name: str, asset_label: str = ""):
    if asset_name not in latest_sensor_values:
        latest_sensor_values[asset_name] = {}
        latest_results[asset_name] = {"score": 0, "status": "none"}
        prev_statuses[asset_name] = "none"
        history_cache[asset_name] = []
        manual_sources[asset_name] = set()
        simulated_values[asset_name] = {}
        real_values[asset_name] = {}
        if asset_name not in data_source_mode:
            data_source_mode[asset_name] = "simulated"


def _get_asset_label(name: str) -> str:
    asset = kb.get_asset_by_name(name)
    return asset.label if asset else name


def update_asset_data(asset_name, sensors_dict, score, status, rules, asset_label):
    global latest_sensor_values, latest_results, prev_statuses, event_cache, history_cache, _cycle_counter

    _ensure_asset_caches(asset_name, asset_label)
    latest_sensor_values[asset_name] = sensors_dict
    latest_results[asset_name] = {"score": score, "status": status}

    old = prev_statuses.get(asset_name)
    if old and old != status:
        is_worsening = status in ("high",)

        event_entry = {
            "time": datetime.now().strftime("%H:%M:%S"),
            "asset": asset_name,
            "asset_name": asset_label or asset_name,
            "from": old,
            "to": status,
            "score": score,
            "type": "warning" if is_worsening else "info",
        }
        event_cache.append(event_entry)

        asset = kb.get_asset_by_name(asset_name)
        if asset:
            kb.add_event(asset.id, old, status, score,
                         message=f"{asset_label or asset_name}: {old} → {status}",
                         event_type="warning" if is_worsening else "info")

        if status in ("high", "medium"):
            _check_and_send_push(asset_name, status, asset_label)

    prev_statuses[asset_name] = status

    history_cache[asset_name].append({
        "time": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "score": score,
        "sensors": dict(sensors_dict),
    })
    if len(history_cache[asset_name]) > 60:
        history_cache[asset_name] = history_cache[asset_name][-60:]

    if len(event_cache) > 50:
        event_cache[:] = event_cache[-50:]

    _cycle_counter += 1

def _fill_missing_sensors(asset, sv: dict) -> dict:
    """Fill missing sensor values with midpoint defaults."""
    filled = dict(sv)
    for s in kb.get_sensors(asset.id):
        if s.name not in filled:
            filled[s.name] = (s.min_val + s.max_val) / 2.0
    return filled


def _evaluate_asset(asset_name: str, persist_readings: bool = True):
    """Run fuzzy inference for a single asset using only stored field values.
    Called when manual data arrives, a scenario is triggered, or simulation step runs."""
    asset = kb.get_asset_by_name(asset_name)
    if not asset:
        return
    _ensure_asset_caches(asset_name, asset.label)

    sensors_list = kb.get_sensors(asset.id)
    rules_list = kb.get_rules(asset.id)
    actuators_list = kb.get_actuators(asset.id)

    sv = _fill_missing_sensors(asset, latest_sensor_values.get(asset_name, {}))

    if not any(v is not None for v in sv.values()):
        return

    score = inference.evaluate(asset, sensors_list, rules_list, sv)
    status = inference.get_status(score, asset.output_max)
    active_rules = inference.get_active_rules(asset, sensors_list, rules_list, sv)

    for r in active_rules:
        action = r.get("action")
        if action and r["fire_strength"] > 0.5:
            act_name = action["actuator"]
            act_value = action["value"]
            act_db = next((a for a in actuators_list if a.name == act_name), None)
            if act_db and act_db.auto:
                kb.update_actuator(act_db.id, command=float(act_value), state=bool(act_value))
                action_cache.append({
                    "time": datetime.now().strftime("%H:%M:%S"),
                    "asset": asset_name,
                    "asset_name": asset.label,
                    "rule": r.get("id", ""),
                    "rule_desc": r.get("description", ""),
                    "actuator": act_db.label,
                    "value": act_value,
                    "fire_strength": r["fire_strength"],
                })

    if persist_readings:
        for s_name, s_val in sv.items():
            kb.add_reading(asset.id, s_name, float(s_val), score)

    update_asset_data(asset_name, sv, score, status, active_rules, asset.label)

    return True


async def _broadcast_if_connected():
    if active_connections:
        await broadcast(_build_full_data())

async def run_simulation():
    """Background task: continuously runs the IIoT simulator to generate sensor data.
    Always writes to simulated_values regardless of mode.
    Only copies to latest_sensor_values for assets in 'simulated' mode.
    Broadcasts updates via WebSocket every cycle (3s fixed interval)."""
    while True:
        try:
            await asyncio.sleep(3)
            simulator.step(3)
            readings = simulator.read_all()
            for asset_name, sensors in readings.items():
                try:
                    if visible_assets is not None and asset_name not in visible_assets:
                        continue
                    _ensure_asset_caches(asset_name)
                    asset = kb.get_asset_by_name(asset_name)
                    if not asset:
                        continue
                    simulated_values[asset_name].update(sensors)
                    if data_source_mode.get(asset_name, "simulated") == "simulated":
                        for s_name, s_val in sensors.items():
                            latest_sensor_values[asset_name][s_name] = s_val
                        _evaluate_asset(asset_name, persist_readings=False)
                except Exception as e:
                    print(f"[sim] Error evaluating {asset_name}: {e}")
            await _broadcast_if_connected()
        except asyncio.CancelledError:
            break
        except Exception:
            pass

def _build_asset_data(asset_name: str) -> dict | None:
    asset = kb.get_asset_by_name(asset_name)
    if not asset:
        return None
    sensors_list = kb.get_sensors(asset.id)
    rules_list = kb.get_rules(asset.id)
    sv = latest_sensor_values.get(asset_name, {})
    lr = latest_results.get(asset_name, {"score": 0, "status": "none"})
    active_rules = inference.get_active_rules(asset, sensors_list, rules_list, sv)
    explained = explainer.explain(asset, sensors_list, rules_list, sv, lr["score"], lr["status"])

    sensor_types = {s.name: s.sensor_type for s in sensors_list}
    sensors_meta = {s.name: {"label": s.label, "unit": s.unit,
                             "min": s.min_val, "max": s.max_val,
                             "sensor_type": s.sensor_type}
                    for s in sensors_list}
    current_mode = data_source_mode.get(asset_name, "simulated")
    manual_set = manual_sources.get(asset_name, set())
    if current_mode == "real":
        is_simulated = {
            s.name: s.name not in manual_set
            for s in sensors_list
        }
        all_simulated = False
    else:
        is_simulated = {s.name: True for s in sensors_list}
        all_simulated = True
    actuators_list = kb.get_actuators(asset.id)
    actuators_data = [
        {"id": a.id, "name": a.name, "label": a.label, "unit": a.unit,
         "value": a.command, "state": a.state, "auto": a.auto,
         "min_val": a.min_val, "max_val": a.max_val}
        for a in actuators_list
    ]
    has_data = bool(sv) and any(v is not None for v in sv.values())

    return {
        "id": asset.id,
        "name": asset.label,
        "has_data": has_data,
        "sensors": sv,
        "sensor_types": sensor_types,
        "sensors_meta": sensors_meta,
        "is_simulated": is_simulated,
        "all_simulated": all_simulated,
        "actuators": actuators_data,
        "score": lr["score"],
        "status": lr["status"],
        "recommendations": RECOMMENDATIONS.get({"bomba": "water", "planta": "generator", "ascensor": "elevator"}.get(asset.name.split("_")[0], "water"), {}).get(lr["status"], ["No data"]),
        "explanation": explained["summary"],
        "scenarios": simulator.get_scenarios_list(asset_name),
        "current_scenario": simulator.scenarios.get(asset_name, "normal"),
        "data_source": current_mode,
    }


def _build_full_data() -> dict:
    result = {}
    for asset in kb.get_all_assets():
        d = _build_asset_data(asset.name)
        if d:
            result[asset.name] = d
    return result


async def broadcast(data: dict):
    dead = set()
    global active_connections
    for ws in active_connections:
        try:
            await ws.send_json(data)
        except Exception:
            dead.add(ws)
    active_connections -= dead


@router.get("/api/data")
async def get_data(request: Request = None):
    data = _build_full_data()
    if request:
        allowed = _scope_condo_ids(request)
        if allowed is not None:
            valid_names = set()
            for cid in allowed:
                valid_names |= _get_condo_asset_names(cid)
            data = {k: v for k, v in data.items() if k in valid_names}
    return data

@router.post("/api/set-visible")
async def set_visible(body: dict):
    global visible_assets
    assets = body.get("assets")
    if assets is None:
        visible_assets = None
    else:
        visible_assets = set(assets)
    return {"status": "ok", "count": len(visible_assets) if visible_assets else "all"}

@router.get("/api/events")
async def get_events(request: Request = None):
    allowed_names = None
    if request:
        allowed_ids = _scope_condo_ids(request)
        if allowed_ids is not None:
            allowed_names = set()
            for cid in allowed_ids:
                allowed_names |= _get_condo_asset_names(cid)
    db_events = kb.get_recent_events(limit=50)
    result = []
    for e in db_events:
        asset = kb.get_asset(e.asset_id)
        if allowed_names is not None and (not asset or asset.name not in allowed_names):
            continue
        result.append({
            "time": e.timestamp.strftime("%H:%M:%S"),
            "asset": asset.name if asset else "unknown",
            "asset_name": asset.label if asset else "Desconocido",
            "from": e.old_status,
            "to": e.new_status,
            "score": e.score or 0,
            "type": e.event_type or "info",
        })
    if not result:
        result = event_cache
    return result

@router.get("/api/actions")
async def get_actions(limit: int = Query(30)):
    return action_cache[-limit:][::-1]

@router.get("/api/history/{asset_name}")
async def get_history(asset_name: str):
    asset = kb.get_asset_by_name(asset_name)
    if not asset:
        return []
    return kb.get_reading_batches(asset.id, limit=20)

@router.get("/api/sensor-readings/{asset_name}/{sensor_name}")
async def get_sensor_readings(asset_name: str, sensor_name: str, limit: int = Query(60)):
    asset = kb.get_asset_by_name(asset_name)
    if not asset:
        raise HTTPException(404)
    readings = kb.get_recent_readings(asset.id, sensor_name=sensor_name, limit=limit)
    return [
        {
            "time": r.timestamp.strftime("%Y-%m-%d %H:%M"),
            "value": r.value,
            "score": r.score,
        }
        for r in readings
    ]

@router.post("/api/scenario/{asset_name}")
async def set_scenario(asset_name: str, scenario: str = Query(...), request: Request = None):
    if request: _require_role(request, "supervisor")
    base = simulator.instances.get(asset_name, asset_name)
    if base not in SCENARIOS:
        raise HTTPException(404, "Asset not found")
    if scenario not in SCENARIOS[base]:
        raise HTTPException(400, f"Scenario must be one of: {list(SCENARIOS[base].keys())}")

    scenario_info = SCENARIOS[base].get(scenario, {})
    label = scenario_info.get("label", scenario)
    asset_label = _get_asset_label(asset_name)

    asset = kb.get_asset_by_name(asset_name)
    if asset:
        _ensure_asset_caches(asset_name, asset.label)
        sv = {}
        for s in kb.get_sensors(asset.id):
            base = scenario_info.get(s.name)
            if base is not None:
                sv[s.name] = float(base)
            elif scenario_info.get("amp") and isinstance(scenario_info.get("amp"), (int, float)):
                sv[s.name] = (s.min_val + s.max_val) / 2.0
        if sv:
            latest_sensor_values[asset_name].update(sv)

        _evaluate_asset(asset_name)

    simulator.set_scenario(asset_name, scenario, auto_recover=True)

    event_cache.append({
        "time": datetime.now().strftime("%H:%M:%S"),
        "asset": asset_name,
        "asset_name": asset_label,
        "from": simulator.scenarios.get(asset_name, "normal"),
        "to": scenario,
        "score": 0,
        "type": "warning" if scenario != "normal" else "info",
    })

    username = request.session.get("user", "unknown") if request else "unknown"
    kb.add_audit(username, "cambio_escenario", f"{asset_name}: {scenario}", asset_id=kb.get_asset_by_name(asset_name).id if kb.get_asset_by_name(asset_name) else None)

    if active_connections:
        await broadcast(_build_full_data())

    return {"asset": asset_name, "scenario": scenario, "label": label}

@router.post("/api/random-fault")
async def random_fault(request: Request = None):
    if request: _require_role(request, "supervisor")
    import random as rnd
    all_assets = list(simulator.instances.keys()) + [a for a in SCENARIOS if a not in simulator.instances]
    fault_assets = [a for a in all_assets if len(SCENARIOS.get(simulator.instances.get(a, a), {})) > 1]
    if not fault_assets:
        raise HTTPException(400, "No assets with fault scenarios")
    asset_name = rnd.choice(fault_assets)
    base = simulator.instances.get(asset_name, asset_name)
    fault_scenarios = [s for s in SCENARIOS[base] if s != "normal"]
    if not fault_scenarios:
        raise HTTPException(400, "No fault scenarios available")
    scenario = rnd.choice(fault_scenarios)
    scenario_info = SCENARIOS[base].get(scenario, {})
    label = scenario_info.get("label", scenario)
    asset_label = _get_asset_label(asset_name)

    asset = kb.get_asset_by_name(asset_name)
    if asset:
        _ensure_asset_caches(asset_name, asset.label)
        sv = {}
        for s in kb.get_sensors(asset.id):
            base = scenario_info.get(s.name)
            if base is not None:
                sv[s.name] = float(base)
            elif scenario_info.get("amp") and isinstance(scenario_info.get("amp"), (int, float)):
                sv[s.name] = (s.min_val + s.max_val) / 2.0
        if sv:
            latest_sensor_values[asset_name].update(sv)

        _evaluate_asset(asset_name)

    simulator.set_scenario(asset_name, scenario, auto_recover=True)

    event_cache.append({
        "time": datetime.now().strftime("%H:%M:%S"),
        "asset": asset_name,
        "asset_name": asset_label,
        "from": "normal",
        "to": scenario,
        "score": 0,
        "type": "warning",
    })
    username = request.session.get("user", "unknown") if request else "unknown"
    kb.add_audit(username, "falla_aleatoria", f"{asset_label}: {scenario}")

    if active_connections:
        await broadcast(_build_full_data())

    return {"asset": asset_name, "scenario": scenario, "label": label, "asset_name": asset_label}

@router.get("/api/scenarios/{asset_name}")
async def get_scenarios(asset_name: str):
    base = simulator.instances.get(asset_name, asset_name)
    if base not in SCENARIOS:
        raise HTTPException(404, "Asset not found")
    return simulator.get_scenarios_list(asset_name)

@router.get("/api/hierarchy")
async def get_hierarchy(request: Request = None):
    """Returns the full hierarchy with asset statuses for the map."""
    condos = kb.get_all_condominiums()
    if request:
        allowed = _scope_condo_ids(request)
        if allowed is not None:
            condos = [c for c in condos if c.id in allowed]
    result = []
    for c in condos:
        buildings = kb.get_buildings(c.id)
        b_list = []
        for b in buildings:
            rooms = kb.get_rooms(b.id)
            r_list = []
            for r in rooms:
                assets = kb.get_assets_in_room(r.id)
                a_list = []
                worst_score = 0
                worst_status = "low"
                for a in assets:
                    lr = latest_results.get(a.name, {"score": 0, "status": "low"})
                    if STATUS_ORDER.get(lr["status"], 0) > STATUS_ORDER.get(worst_status, 0):
                        worst_status = lr["status"]
                        worst_score = lr["score"]
                    a_list.append({
                        "id": a.id,
                        "name": a.name,
                        "label": a.label,
                        "icon": a.icon,
                        "score": lr["score"],
                        "status": lr["status"],
                    })
                r_list.append({
                    "id": r.id,
                    "name": r.name,
                    "assets": a_list,
                    "worst_score": worst_score,
                    "worst_status": worst_status,
                })
            b_list.append({
                "id": b.id,
                "name": b.name,
                "rooms": r_list,
            })
        worst_condo_status = "low"
        for b in b_list:
            for r in b["rooms"]:
                if STATUS_ORDER.get(r["worst_status"], 0) > STATUS_ORDER.get(worst_condo_status, 0):
                    worst_condo_status = r["worst_status"]
        result.append({
            "id": c.id,
            "name": c.name,
            "address": c.address,
            "lat": c.lat,
            "lng": c.lng,
            "buildings": b_list,
            "worst_status": worst_condo_status,
        })
    return result

STATUS_ORDER = {"high": 3, "medium": 2, "low": 1}

# ---- Hierarchy CRUD ----

@router.post("/api/condominiums")
async def create_condominium(data: dict, request: Request = None):
    if request: _require_role(request, "admin")
    c = kb.create_condominium(
        name=data["name"],
        slug=re.sub(r'[^a-z0-9]+', '_', data["name"].lower()).strip('_'),
        address=data.get("address", ""),
        lat=data.get("lat"),
        lng=data.get("lng"),
    )
    return {"id": c.id, "name": c.name, "slug": c.slug}

@router.put("/api/condominiums/{condo_id}")
async def update_condominium(condo_id: int, data: dict, request: Request = None):
    if request: _require_role(request, "admin")
    c = kb.update_condominium(condo_id, **data)
    if not c:
        raise HTTPException(404)
    return {"id": c.id, "name": c.name}

@router.delete("/api/condominiums/{condo_id}")
async def delete_condominium(condo_id: int, request: Request = None):
    if request: _require_role(request, "admin")
    c = kb.delete_condominium(condo_id)
    if not c:
        raise HTTPException(404)
    return {"deleted": condo_id}

@router.post("/api/buildings")
async def create_building(data: dict, request: Request = None):
    if request: _require_role(request, "admin")
    b = kb.create_building(condominium_id=data["condominium_id"], name=data["name"])
    return {"id": b.id, "name": b.name, "condominium_id": b.condominium_id}

@router.put("/api/buildings/{bld_id}")
async def update_building(bld_id: int, data: dict, request: Request = None):
    if request: _require_role(request, "admin")
    b = kb.update_building(bld_id, **data)
    if not b:
        raise HTTPException(404)
    return {"id": b.id, "name": b.name}

@router.delete("/api/buildings/{bld_id}")
async def delete_building(bld_id: int, request: Request = None):
    if request: _require_role(request, "admin")
    b = kb.delete_building(bld_id)
    if not b:
        raise HTTPException(404)
    return {"deleted": bld_id}

@router.post("/api/rooms")
async def create_room(data: dict, request: Request = None):
    if request: _require_role(request, "admin")
    r = kb.create_room(building_id=data["building_id"], name=data["name"])
    return {"id": r.id, "name": r.name, "building_id": r.building_id}

@router.put("/api/rooms/{room_id}")
async def update_room(room_id: int, data: dict, request: Request = None):
    if request: _require_role(request, "admin")
    r = kb.update_room(room_id, **data)
    if not r:
        raise HTTPException(404)
    return {"id": r.id, "name": r.name}

@router.delete("/api/rooms/{room_id}")
async def delete_room(room_id: int, request: Request = None):
    if request: _require_role(request, "admin")
    r = kb.delete_room(room_id)
    if not r:
        raise HTTPException(404)
    return {"deleted": room_id}

@router.get("/api/asset-types")
async def get_asset_types():
    """Return available asset types for nomenclature."""
    from core.knowledge_base import ASSET_TYPE_SLUGS
    return ASSET_TYPE_SLUGS

@router.get("/api/asset-name-preview")
async def asset_name_preview(type_slug: str, room_id: int):
    """Preview the auto-generated asset name for a type+location combination."""
    from core.knowledge_base import ASSET_TYPE_SLUGS
    if type_slug not in ASSET_TYPE_SLUGS:
        raise HTTPException(400, f"Tipo inválido: {type_slug}")
    room = kb.db_get_room(room_id)
    if not room:
        raise HTTPException(404, "Sala no encontrada")
    bld = kb.get_building(room.building_id)
    condo = kb.get_condominium(bld.condominium_id) if bld else None
    if not condo or not condo.slug:
        raise HTTPException(400, "Condominio sin slug")
    name = kb.make_asset_name(type_slug, condo.slug)
    return {"name": name, "condo_slug": condo.slug}

@router.get("/api/mtbf/{asset_id}")
async def get_mtbf(asset_id: int):
    """Calculate MTBF for an asset based on event history."""
    asset = kb.get_asset(asset_id)
    if not asset:
        raise HTTPException(404)
    events = kb.get_recent_events(asset_id=asset_id, limit=1000)
    failures = [e for e in events if e.new_status in ("high",) and e.event_type == "warning"]
    now = datetime.now().timestamp()
    if len(failures) >= 2:
        timestamps = [f.timestamp.timestamp() for f in failures]
        timestamps.sort(reverse=True)
        intervals = [timestamps[i] - timestamps[i + 1] for i in range(len(timestamps) - 1)]
        mtbf_hours = round((sum(intervals) / len(intervals)) / 3600, 1)
    elif len(failures) == 1:
        mtbf_hours = round((now - failures[0].timestamp.timestamp()) / 3600, 1)
    else:
        mtbf_hours = 720.0
    return {
        "asset_id": asset_id,
        "asset_name": asset.label,
        "mtbf_hours": mtbf_hours,
        "failure_count": len(failures),
        "status": "healthy" if mtbf_hours > 168 else "watch",
    }


@router.get("/api/assets")
async def list_assets(request: Request = None):
    assets = kb.get_all_assets()
    if request:
        assets = _filter_assets_by_scope(request, assets)
    return [{"id": a.id, "name": a.name, "label": a.label, "icon": a.icon} for a in assets]

@router.get("/api/assets/{asset_id}")
async def get_asset_detail(asset_id: int):
    asset = kb.get_asset(asset_id)
    if not asset:
        raise HTTPException(404)
    sensors = kb.get_sensors(asset_id)
    rules = kb.get_rules(asset_id, enabled_only=False)
    # Live data from the inference engine
    live = _build_asset_data(asset.name) or {}
    return {
        "asset": {"id": asset.id, "name": asset.name, "label": asset.label, "icon": asset.icon,
                  "description": asset.description, "output_name": asset.output_name,
                  "output_label": asset.output_label, "output_min": asset.output_min,
                  "output_max": asset.output_max,
                  "location_path": kb.get_location_path(asset_id)},
        "sensors": [{"id": s.id, "name": s.name, "label": s.label, "unit": s.unit,
                      "min_val": s.min_val, "max_val": s.max_val, "mf_config": s.mf_config,
                      "value": live.get("sensors", {}).get(s.name),
                      "is_simulated": live.get("is_simulated", {}).get(s.name, True)}
                     for s in sensors],
        "rules": [{"id": r.id, "name": r.name, "description": r.description,
                    "operator": r.operator, "antecedents": r.antecedents,
                    "consequent": r.consequent, "weight": r.weight, "enabled": r.enabled}
                   for r in rules],
        "actuators": live.get("actuators", []),
        "score": live.get("score", 0),
        "status": live.get("status", "none"),
        "explanation": live.get("explanation", ""),
        "recommendations": live.get("recommendations", ["No data"]),
        "data_source": live.get("data_source", "simulated"),
        "all_simulated": live.get("all_simulated", True),
    }

@router.post("/api/assets")
async def create_asset(data: dict, request: Request = None):
    if request: _require_role(request, "supervisor")
    # Auto-generate name if type_slug provided (nomenclature)
    if "type_slug" in data and "location_id" in data:
        from core.knowledge_base import ASSET_TYPE_SLUGS
        type_info = ASSET_TYPE_SLUGS.get(data["type_slug"])
        if not type_info:
            raise HTTPException(400, f"Tipo de activo inválido: {data['type_slug']}")
        # Find condo slug from location
        room = kb.db_get_room(data["location_id"])
        if not room:
            raise HTTPException(400, "Ubicación no encontrada")
        bld = kb.get_building(room.building_id)
        if not bld:
            raise HTTPException(400, "Edificio no encontrado")
        condo = kb.get_condominium(bld.condominium_id)
        if not condo or not condo.slug:
            raise HTTPException(400, "Condominio sin slug")
        name = kb.make_asset_name(data["type_slug"], condo.slug)
        label = data.get("label", f"{type_info['label']} {condo.name} #{name.split('_')[-1]}")
        icon = type_info["icon"]
        output_name = type_info["output_name"]
        output_label = type_info["output_label"]
        output_min = type_info["output_min"]
        output_max = type_info["output_max"]
    else:
        name = data["name"]
        label = data.get("label", name)
        icon = data.get("icon", "gear")
        output_name = data.get("output_name", "output")
        output_label = data.get("output_label", "Score")
        output_min = data.get("output_min", 0)
        output_max = data.get("output_max", 100)
    a = kb.create_asset(
        name=name, label=label,
        description=data.get("description", ""),
        icon=icon,
        output_name=output_name,
        output_label=output_label,
        output_min=output_min,
        output_max=output_max,
        location_id=data.get("location_id"),
    )
    return {"id": a.id, "name": a.name, "label": a.label}

@router.put("/api/assets/{asset_id}")
async def update_asset(asset_id: int, data: dict, request: Request = None):
    if request: _require_role(request, "admin")
    inference.clear_cache()
    a = kb.update_asset(asset_id, **data)
    if not a:
        raise HTTPException(404)
    return {"id": a.id}

@router.delete("/api/assets/{asset_id}")
async def delete_asset(asset_id: int, request: Request = None):
    if request: _require_role(request, "admin")
    inference.clear_cache()
    a = kb.delete_asset(asset_id)
    if not a:
        raise HTTPException(404)
    return {"deleted": asset_id}

@router.post("/api/assets/{asset_id}/reset-defaults")
async def reset_asset_defaults(asset_id: int, request: Request = None):
    if request: _require_role(request, "admin")
    inference.clear_cache()
    a = kb.get_asset(asset_id)
    if not a:
        raise HTTPException(404)
    ok = kb.reset_asset_defaults(a)
    if not ok:
        raise HTTPException(400, detail="No se pudo determinar el tipo de activo para restaurar valores por defecto")
    return {"status": "reset", "asset_id": asset_id}

@router.post("/api/assets/{asset_id}/sensors")
async def add_sensor(asset_id: int, data: dict, request: Request = None):
    if request: _require_role(request, "admin")
    inference.clear_cache()
    s = kb.add_sensor(
        asset_id=asset_id, name=data["name"], label=data.get("label", data["name"]),
        unit=data.get("unit", ""), min_val=data.get("min_val", 0),
        max_val=data.get("max_val", 100), mf_config=data.get("mf_config", []),
    )
    return {"id": s.id, "name": s.name}

@router.put("/api/sensors/{sensor_id}")
async def update_sensor(sensor_id: int, data: dict, request: Request = None):
    if request: _require_role(request, "admin")
    inference.clear_cache()
    s = kb.update_sensor(sensor_id, **data)
    if not s:
        raise HTTPException(404)
    return {"id": s.id}

@router.delete("/api/sensors/{sensor_id}")
async def delete_sensor(sensor_id: int, request: Request = None):
    if request: _require_role(request, "admin")
    inference.clear_cache()
    s = kb.delete_sensor(sensor_id)
    if not s:
        raise HTTPException(404)
    return {"deleted": sensor_id}

@router.post("/api/assets/{asset_id}/rules")
async def add_rule(asset_id: int, data: dict, request: Request = None):
    if request: _require_role(request, "admin")
    inference.clear_cache()
    r = kb.add_rule(
        asset_id=asset_id,
        name=data.get("name", ""),
        description=data.get("description", ""),
        antecedents=data["antecedents"],
        consequent=data["consequent"],
        operator=data.get("operator", "and"),
        weight=data.get("weight", 1.0),
        enabled=data.get("enabled", True),
    )
    return {"id": r.id, "name": r.name}

@router.put("/api/rules/{rule_id}")
async def update_rule(rule_id: int, data: dict, request: Request = None):
    if request: _require_role(request, "admin")
    inference.clear_cache()
    r = kb.update_rule(rule_id, **data)
    if not r:
        raise HTTPException(404)
    return {"id": r.id}

@router.delete("/api/rules/{rule_id}")
async def delete_rule(rule_id: int, request: Request = None):
    if request: _require_role(request, "admin")
    inference.clear_cache()
    r = kb.delete_rule(rule_id)
    if not r:
        raise HTTPException(404)
    return {"deleted": rule_id}

@router.get("/api/explain/{asset_name}")
async def get_explanation(asset_name: str):
    asset = kb.get_asset_by_name(asset_name)
    if not asset:
        raise HTTPException(404)
    sensors_list = kb.get_sensors(asset.id)
    rules_list = kb.get_rules(asset.id)
    sv = latest_sensor_values.get(asset_name, {})
    lr = latest_results.get(asset_name, {"score": 0, "status": "none"})
    return explainer.explain(asset, sensors_list, rules_list, sv, lr["score"], lr["status"])

@router.get("/api/report")
async def get_report(request: Request = None):
    """Enhanced text report with MTBF and audit summary."""
    if request: _require_role(request, "technician")
    now = datetime.now()
    assets = kb.get_all_assets()
    if request:
        allowed = _scope_condo_ids(request)
        if allowed is not None:
            valid_names = set()
            for cid in allowed:
                valid_names |= _get_condo_asset_names(cid)
            assets = [a for a in assets if a.name in valid_names]
    lines = []
    lines.append("=" * 70)
    lines.append("  SISTEMA EXPERTO - GESTIÓN DE ACTIVOS CRÍTICOS")
    lines.append("  REPORTE COMPLETO DE ESTADO")
    lines.append("=" * 70)
    lines.append(f"  Generado: {now.strftime('%d/%m/%Y %H:%M:%S')}")
    lines.append(f"  Total activos: {len(assets)}")
    lines.append("")

    status_counts = {"high": 0, "medium": 0, "low": 0}
    for asset in assets:
        lr = latest_results.get(asset.name, {"score": 0, "status": "low"})
        status_counts[lr["status"]] = status_counts.get(lr["status"], 0) + 1

    lines.append("--- RESUMEN ---")
    lines.append(f"  Rojo (ALTO):     {status_counts.get('high', 0)}")
    lines.append(f"  Amarillo (MEDIO): {status_counts.get('medium', 0)}")
    lines.append(f"  Verde (BAJO):    {status_counts.get('low', 0)}")
    lines.append("")

    for asset in assets:
        asset_name = asset.name
        sensors_list = kb.get_sensors(asset.id)
        rules_list = kb.get_rules(asset.id)
        sv = latest_sensor_values.get(asset_name, {})
        lr = latest_results.get(asset_name, {"score": 0, "status": "low"})
        active_rules = inference.get_active_rules(asset, sensors_list, rules_list, sv)
        mtbf_res = _calc_mtbf(asset.id)
        location = kb.get_location_path(asset.id) if hasattr(kb, 'get_location_path') else ""

        status_icon = {"high": "!!", "medium": "! ", "low": "  "}
        lines.append(f"{status_icon.get(lr['status'], '  ')} {asset.label} ({asset_name})")
        if location:
            lines.append(f"      Ubicación: {location}")
        lines.append(f"      Criticidad: {'ROJO' if lr['status'] == 'high' else 'AMARILLO' if lr['status'] == 'medium' else 'VERDE'}  IS: {lr['score']}/100")
        lines.append(f"      MTBF: {mtbf_res['mtbf_hours']}h  Fallos: {mtbf_res['failure_count']}")
        lines.append("      Sensores:")
        for k, v in sv.items():
            lines.append(f"        {k}: {v:.2f}")
        recs = RECOMMENDATIONS.get(asset_name, {}).get(lr["status"], [])
        if recs:
            lines.append("      Recomendaciones:")
            for r in recs:
                lines.append(f"        > {r}")
        if active_rules[:2]:
            lines.append("      Reglas activas:")
            for r in active_rules[:2]:
                lines.append(f"        [{r['id']}] ({r['fire_strength']:.2f})")
        lines.append("")

    lines.append("--- EVENTOS RECIENTES ---")
    for e in event_cache[-15:]:
        lines.append(f"  [{e['time']}] {e['asset_name']}: {e['from']} -> {e['to']}")

    lines.append("")
    lines.append("--- AUDITORÍA RECIENTE ---")
    audits = kb.get_recent_audits(limit=10)
    for a in audits:
        lines.append(f"  [{a.timestamp.strftime('%H:%M:%S')}] {a.username}: {a.action} - {a.detail}")

    lines.append("")
    lines.append("=" * 70)
    lines.append("  FIN DEL REPORTE")
    lines.append("=" * 70)
    return PlainTextResponse("\n".join(lines))


def _build_report_html(show_print_button: bool = True, allowed_asset_names: set = None) -> str:
    now = datetime.now()
    assets = kb.get_all_assets()
    if allowed_asset_names is not None:
        assets = [a for a in assets if a.name in allowed_asset_names]
    status_counts = {"high": 0, "medium": 0, "low": 0}
    status_colors = {"high": "#dc2626", "medium": "#ca8a04", "low": "#22c55e"}
    status_labels = {"high": "ROJO", "medium": "AMARILLO", "low": "VERDE"}

    rows_html = ""
    for asset in assets:
        sv = latest_sensor_values.get(asset.name, {})
        lr = latest_results.get(asset.name, {"score": 0, "status": "low"})
        mtbf_res = _calc_mtbf(asset.id)
        sensors_html = "".join(f"<tr><td>{k}</td><td>{v:.1f}</td></tr>" for k, v in sv.items()) or "<tr><td colspan='2'>—</td></tr>"
        color = status_colors.get(lr["status"], "#22c55e")
        rows_html += f"""
        <tr>
            <td>{asset.label}</td>
            <td><span class="status-dot" style="background:{color}"></span> {status_labels.get(lr['status'], 'VERDE')}</td>
            <td>{lr['score']:.0f}</td>
            <td>{mtbf_res['mtbf_hours']}h</td>
            <td>{mtbf_res['failure_count']}</td>
            <td><table class="inner">{sensors_html}</table></td>
        </tr>"""
        status_counts[lr["status"]] = status_counts.get(lr["status"], 0) + 1

    events_html = "".join(
        f"<tr><td>{e['time']}</td><td>{e['asset_name']}</td><td>{'VERDE' if e['from'] == 'low' else 'AMARILLO' if e['from'] == 'medium' else 'ROJO' if e['from'] == 'high' else e['from']}</td><td>{'VERDE' if e['to'] == 'low' else 'AMARILLO' if e['to'] == 'medium' else 'ROJO' if e['to'] == 'high' else e['to']}</td></tr>"
        for e in event_cache[-20:]
    ) or "<tr><td colspan='4'>Sin eventos</td></tr>"

    print_btn = '<div class="no-print"><button onclick="window.print()"> Imprimir / Guardar PDF</button></div>' if show_print_button else ""
    html = f"""<!DOCTYPE html>
<html lang="es">
<head><meta charset="UTF-8">
<title>Reporte - Sistema Experto</title>
<style>
    @page {{ margin: 1.5cm; size: A4; }}
    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
    body {{ font-family: 'Segoe UI', Arial, sans-serif; color: #1e293b; font-size: 11pt; line-height: 1.5; }}
    h1 {{ font-size: 18pt; color: #1e293b; margin-bottom: 0.2cm; }}
    h2 {{ font-size: 14pt; color: #334155; margin: 0.5cm 0 0.3cm; border-bottom: 2px solid #3b82f6; padding-bottom: 0.1cm; }}
    .subtitle {{ color: #64748b; font-size: 10pt; margin-bottom: 0.5cm; }}
    .summary {{ display: flex; gap: 0.3cm; margin: 0.4cm 0; }}
    .summary-item {{ flex: 1; text-align: center; padding: 0.3cm; border-radius: 8px; color: white; font-weight: 600; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 10pt; margin: 0.3cm 0; }}
    th, td {{ padding: 0.15cm 0.2cm; text-align: left; border-bottom: 1px solid #e2e8f0; }}
    th {{ background: #f1f5f9; color: #475569; font-size: 9pt; }}
    .status-dot {{ display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin-right: 0.15cm; }}
    .inner {{ font-size: 9pt; margin: 0; }}
    .inner td {{ border: none; padding: 0.05cm 0.1cm; }}
    .footer {{ text-align: center; color: #94a3b8; font-size: 8pt; margin-top: 0.5cm; border-top: 1px solid #e2e8f0; padding-top: 0.3cm; }}
    @media print {{ .no-print {{ display: none; }} }}
    .no-print {{ text-align: center; margin-bottom: 0.5cm; }}
    .no-print button {{ padding: 0.3cm 0.6cm; background: #3b82f6; color: white; border: none; border-radius: 6px; font-size: 11pt; cursor: pointer; }}
</style>
</head>
<body>
{print_btn}
<h1>Reporte de Estado - Sistema Experto</h1>
<div class="subtitle">Generado: {now.strftime('%d/%m/%Y %H:%M:%S')} | Activos: {len(assets)}</div>

<h2>Resumen</h2>
<div class="summary">
    <div class="summary-item" style="background:{status_colors['high']};">Rojo: {status_counts['high']}</div>
    <div class="summary-item" style="background:{status_colors['medium']};">Amarillo: {status_counts['medium']}</div>
    <div class="summary-item" style="background:{status_colors['low']};">Verde: {status_counts['low']}</div>
</div>

<h2>Detalle de Activos</h2>
<table><thead><tr><th>Activo</th><th>Criticidad</th><th>IS</th><th>MTBF</th><th>Fallos</th><th>Sensores</th></tr></thead>
<tbody>{rows_html}</tbody></table>

<h2>Eventos Recientes</h2>
<table><thead><tr><th>Hora</th><th>Activo</th><th>Anterior</th><th>Actual</th></tr></thead>
<tbody>{events_html}</tbody></table>

<div class="footer">Sistema Experto - Gestión de Activos Críticos con IIoT</div>
</body></html>"""
    return html


def _calc_mtbf(asset_id: int) -> dict:
    events = kb.get_recent_events(asset_id=asset_id, limit=1000)
    failures = [e for e in events if e.new_status == "high" and e.event_type == "warning"]
    now_ts = datetime.now().timestamp()
    if len(failures) >= 2:
        timestamps = sorted([f.timestamp.timestamp() for f in failures], reverse=True)
        intervals = [timestamps[i] - timestamps[i + 1] for i in range(len(timestamps) - 1)]
        mtbf_days = round((sum(intervals) / len(intervals)) / 86400, 1)
    elif len(failures) == 1:
        mtbf_days = round((now_ts - failures[0].timestamp.timestamp()) / 86400, 1)
    else:
        mtbf_days = 30.0
    return {"mtbf_days": mtbf_days, "mtbf_hours": round(mtbf_days * 24, 1), "failure_count": len(failures)}


def _csv_response(rows: list, filename: str, headers: list):
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(headers)
    writer.writerows(rows)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/api/report/csv/events")
async def report_csv_events(request: Request = None, limit: int = Query(500)):
    if request: _require_role(request, "technician")
    allowed_names = _allowed_asset_names(request)
    events = kb.get_recent_events(limit=limit * 3 if allowed_names is not None else limit)
    rows = []
    for e in events:
        asset = kb.get_asset(e.asset_id)
        if allowed_names is not None and (not asset or asset.name not in allowed_names):
            continue
        rows.append([
            e.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
            asset.name if asset else "?",
            asset.label if asset else "?",
            e.old_status, e.new_status, e.score, e.event_type
        ])
        if len(rows) >= limit:
            break
    return _csv_response(rows, "eventos.csv",
                         ["timestamp", "asset", "label", "from", "to", "score", "type"])


@router.get("/api/report/csv/readings")
async def report_csv_readings(request: Request = None, asset_name: str = Query(""), limit: int = Query(500)):
    if request: _require_role(request, "technician")
    allowed_names = _allowed_asset_names(request)
    readings = []
    if asset_name:
        if allowed_names is None or asset_name in allowed_names:
            asset = kb.get_asset_by_name(asset_name)
            if asset:
                readings = kb.get_recent_readings(asset.id, limit=limit)
    else:
        targets = kb.get_all_assets()
        if allowed_names is not None:
            targets = [a for a in targets if a.name in allowed_names]
        for a in targets:
            readings.extend(kb.get_recent_readings(a.id, limit=limit // max(len(targets), 1)))
    rows = []
    for r in readings[:limit]:
        asset = kb.get_asset(r.asset_id)
        rows.append([
            r.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
            asset.name if asset else "?", asset.label if asset else "?",
            r.sensor_name, r.value, r.score
        ])
    return _csv_response(rows, "lecturas.csv",
                         ["timestamp", "asset", "label", "sensor", "value", "score"])


@router.get("/api/report/csv/audit")
async def report_csv_audit(request: Request = None, limit: int = Query(500)):
    if request: _require_role(request, "supervisor")
    logs = kb.get_recent_audits(limit=limit)
    rows = []
    for l in logs:
        rows.append([
            l.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
            l.username, l.action, l.detail
        ])
    return _csv_response(rows, "auditoria.csv",
                         ["timestamp", "username", "action", "detail"])


def _allowed_asset_names(request: Request = None) -> set | None:
    """Return set of allowed asset names based on user scope, or None for admin."""
    if not request:
        return None
    allowed = _scope_condo_ids(request)
    if allowed is None:
        return None
    valid_names = set()
    for cid in allowed:
        valid_names |= _get_condo_asset_names(cid)
    return valid_names


@router.get("/api/report/html")
async def get_report_html(request: Request = None):
    """Rich HTML report for printing / PDF export."""
    if request: _require_role(request, "technician")
    return HTMLResponse(_build_report_html(show_print_button=True, allowed_asset_names=_allowed_asset_names(request)))

@router.get("/api/report/pdf")
async def get_report_pdf(request: Request = None):
    """Generate a native PDF report via xhtml2pdf."""
    if request: _require_role(request, "technician")
    import io
    from xhtml2pdf import pisa
    html_str = _build_report_html(show_print_button=False, allowed_asset_names=_allowed_asset_names(request))
    buf = io.BytesIO()
    pisa.CreatePDF(html_str, dest=buf, encoding="utf-8")
    pdf_bytes = buf.getvalue()
    return Response(pdf_bytes, media_type="application/pdf",
                    headers={"Content-Disposition": "inline; filename=reporte.pdf"})

@router.get("/api/reset")
async def reset_simulator():
    for asset in kb.get_all_assets():
        simulator.set_scenario(asset.name, "normal")
    latest_sensor_values.clear()
    latest_results.clear()
    prev_statuses.clear()
    event_cache.clear()
    history_cache.clear()
    action_cache.clear()
    simulated_values.clear()
    real_values.clear()
    data_source_mode.clear()

    from storage.database import get_session
    from models.models import Event, SensorReading
    session = get_session()
    try:
        session.query(Event).delete()
        session.query(SensorReading).delete()
        session.commit()
    finally:
        session.close()

    return {"status": "reset"}

@router.post("/api/sensor-data")
@limiter.limit("20/minute")
async def receive_sensor_data(data: dict, request: Request = None):
    if request: _require_role(request, "technician")
    asset_name = data.get("asset")
    sensor_name = data.get("sensor")
    value = data.get("value")
    captured_at = data.get("captured_at")
    sync_uuid = data.get("sync_uuid")

    if not all([asset_name, sensor_name, value is not None]):
        raise HTTPException(400, "Faltan campos: asset, sensor, value")

    # Dedup: check in-memory set (read-only, no mutation)
    if sync_uuid:
        if sync_uuid in _dedup_set:
            print(f"[sensor-data] DEDUP in-memory skip: {sync_uuid}")
            return {"status": "duplicate", "asset": asset_name, "sensor": sensor_name}
        # Check DB (read-only)
        from storage.database import get_session as _get_session
        from models.models import SensorReading as _SR
        _s = _get_session()
        try:
            existing = _s.query(_SR).filter_by(sync_uuid=sync_uuid).first()
        finally:
            _s.close()
        if existing:
            print(f"[sensor-data] DEDUP db skip: {sync_uuid}")
            return {"status": "duplicate", "asset": asset_name, "sensor": sensor_name}
    elif captured_at:
        dedup_key = (asset_name, sensor_name, int(captured_at))
        if dedup_key in _dedup_set:
            return {"status": "duplicate", "asset": asset_name, "sensor": sensor_name}

    asset = kb.get_asset_by_name(asset_name)
    if not asset:
        raise HTTPException(404, f"Activo '{asset_name}' no encontrado")

    sensors_list = kb.get_sensors(asset.id)
    sensor_config = next((s for s in sensors_list if s.name == sensor_name), None)
    if not sensor_config:
        raise HTTPException(404, f"Sensor '{sensor_name}' no encontrado en '{asset_name}'")

    value = float(value)
    value = max(sensor_config.min_val, min(sensor_config.max_val, value))

    try:
        _ensure_asset_caches(asset_name, asset.label)
        manual_sources[asset_name].add(sensor_name)
        real_values[asset_name][sensor_name] = value
        latest_sensor_values[asset_name][sensor_name] = value
        data_source_mode[asset_name] = "real"
        _evaluate_asset(asset_name, persist_readings=False)
        new_score = latest_results.get(asset_name, {}).get("score", 50)
        kwargs = {"sync_uuid": sync_uuid} if sync_uuid else {}
        kb.add_reading(asset.id, sensor_name, value, score=new_score, **kwargs)

        # Only add to dedup set AFTER successful save
        if sync_uuid:
            _dedup_set.add(sync_uuid)
        elif captured_at:
            _dedup_set.add((asset_name, sensor_name, int(captured_at)))
        if len(_dedup_set) > 1000:
            _dedup_set.clear()
    except Exception as e:
        print(f"[sensor-data] ERROR saving: asset={asset_name} sensor={sensor_name} value={value} error={e}")
        raise HTTPException(500, f"Error al guardar lectura: {str(e)}")

    print(f"[sensor-data] OK: {asset_name}/{sensor_name} = {value} (uuid={sync_uuid})")
    source_label = "teléfono" if sensor_config.sensor_type == "phone" else "externo"
    asset_label = _get_asset_label(asset_name)
    event_cache.append({
        "time": datetime.now().strftime("%H:%M:%S"),
        "asset": asset_name,
        "asset_name": asset_label,
        "from": "lectura",
        "to": f"{sensor_name}={value:.1f}",
        "score": value,
        "type": "info",
    })

    if active_connections:
        await broadcast(_build_full_data())

    return {"status": "ok", "asset": asset_name, "sensor": sensor_name, "value": value, "source": source_label}

@router.get("/api/sensor-types")
async def get_sensor_types(asset_name: str):
    asset = kb.get_asset_by_name(asset_name)
    if not asset:
        raise HTTPException(404)
    sensors_list = kb.get_sensors(asset.id)
    return [
        {"id": s.id, "name": s.name, "label": s.label, "unit": s.unit,
         "min_val": s.min_val, "max_val": s.max_val, "sensor_type": s.sensor_type}
        for s in sensors_list
    ]

@router.post("/api/sensor-type/{sensor_id}")
async def update_sensor_type(sensor_id: int, data: dict, request: Request = None):
    if request: _require_role(request, "admin")
    sensor_type = data.get("sensor_type")
    if sensor_type not in ("simulated", "external", "phone"):
        raise HTTPException(400, "Tipo debe ser: simulated, external, phone")
    s = kb.update_sensor(sensor_id, sensor_type=sensor_type)
    if not s:
        raise HTTPException(404)
    return {"id": s.id, "name": s.name, "sensor_type": s.sensor_type}

@router.get("/api/actuators/{asset_name}")
async def get_actuators(asset_name: str):
    asset = kb.get_asset_by_name(asset_name)
    if not asset:
        raise HTTPException(404)
    act_list = kb.get_actuators(asset.id)
    return [
        {"id": a.id, "name": a.name, "label": a.label, "unit": a.unit,
         "value": a.command, "state": a.state, "auto": a.auto,
         "min_val": a.min_val, "max_val": a.max_val}
        for a in act_list
    ]

@router.post("/api/actuator/{actuator_id}/command")
async def set_actuator_command(actuator_id: int, data: dict, request: Request = None):
    if request: _require_role(request, "supervisor")
    act = kb.get_actuator(actuator_id)
    if not act:
        raise HTTPException(404)
    value = float(data.get("value", 0))
    value = max(act.min_val, min(act.max_val, value))
    auto = data.get("auto", act.auto)
    act = kb.update_actuator(actuator_id, command=value, state=bool(value), auto=auto)
    asset = kb.get_asset(act.asset_id)
    simulator.set_actuator(asset.name, act.name, value)
    username = request.session.get("user", "unknown") if request else "unknown"
    kb.add_audit(username, "comando_actuador", f"{asset.label}/{act.label}={value}", asset_id=act.asset_id)
    return {"id": act.id, "name": act.name, "value": value, "state": bool(value), "auto": auto}


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    active_connections.add(websocket)
    try:
        data = _build_full_data()
        await websocket.send_json(data)
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        active_connections.discard(websocket)


@router.post("/api/source-mode/{asset_name}")
async def set_source_mode(asset_name: str, mode: str = Query(...), request: Request = None):
    """Toggle between 'simulated' and 'real' data source for an asset.
    In 'simulated' mode: shows data from the IIoT simulator.
    In 'real' mode: shows only manually captured field data.
    Both sources are always recorded independently."""
    if mode not in ("simulated", "real"):
        raise HTTPException(400, "Mode must be 'simulated' or 'real'")
    _ensure_asset_caches(asset_name)
    asset = kb.get_asset_by_name(asset_name)
    if not asset:
        raise HTTPException(404, f"Activo '{asset_name}' no encontrado")

    data_source_mode[asset_name] = mode

    if mode == "real":
        latest_sensor_values[asset_name] = dict(real_values.get(asset_name, {}))
    else:
        latest_sensor_values[asset_name] = dict(simulated_values.get(asset_name, {}))

    _evaluate_asset(asset_name)

    username = request.session.get("user", "unknown") if request else "unknown"
    kb.add_audit(username, "cambio_fuente", f"{asset_name}: {mode}", asset_id=asset.id)

    if active_connections:
        await broadcast(_build_full_data())

    return {"asset": asset_name, "mode": mode}


@router.get("/api/admin/users")
async def admin_list_users(request: Request = None):
    if request: _require_role(request, "supervisor")
    users = kb.get_all_users()
    if request:
        role = request.session.get("role", "")
        if role == "supervisor":
            my_ids = request.session.get("condominium_ids", [])
            users = [u for u in users if any(c.id in my_ids for c in u.condominiums)]
    condos = {c.id: c.name for c in kb.get_all_condominiums()}
    return [
        {"id": u.id, "username": u.username, "role": u.role,
         "condominium_ids": [c.id for c in u.condominiums],
         "condominium_names": [c.name for c in u.condominiums],
         "created_at": u.created_at.strftime("%Y-%m-%d %H:%M:%S") if u.created_at else ""}
        for u in users
    ]

@router.post("/api/admin/users")
async def admin_create_user(data: dict, request: Request = None):
    if request: _require_role(request, "supervisor")
    import hashlib
    username = data.get("username")
    password = data.get("password")
    role = data.get("role", "technician")
    condominium_ids = data.get("condominium_ids", [])
    if not username or not password:
        raise HTTPException(400, "username and password required")
    if request:
        req_role = request.session.get("role", "")
        if req_role == "supervisor":
            if role != "technician":
                raise HTTPException(403, "Supervisores solo pueden crear técnicos")
            my_ids = set(request.session.get("condominium_ids", []))
            if not my_ids.issuperset(condominium_ids):
                raise HTTPException(403, "Solo puedes asignar a tus propios condominios")
    existing = kb.get_user(username)
    if existing:
        raise HTTPException(409, "User already exists")
    pw_hash = hashlib.sha256(password.encode()).hexdigest()
    u = kb.create_user(username, pw_hash, role=role, condominium_ids=condominium_ids)
    return {"id": u.id, "username": username, "role": role}

@router.put("/api/admin/users/{user_id}")
async def admin_update_user(user_id: int, data: dict, request: Request = None):
    if request: _require_role(request, "supervisor")
    import hashlib
    target = kb.get_user_by_id(user_id)
    if not target:
        raise HTTPException(404)
    if request:
        req_role = request.session.get("role", "")
        if req_role == "supervisor":
            my_ids = set(request.session.get("condominium_ids", []))
            target_ids = set(c.id for c in target.condominiums)
            if not my_ids.intersection(target_ids):
                raise HTTPException(403, "Solo puedes editar usuarios de tus condominios")
            if target.role != "technician":
                raise HTTPException(403, "Supervisores solo pueden editar técnicos")
            if data.get("role", target.role) != "technician":
                raise HTTPException(403, "No puedes cambiar el rol de un técnico")
    update = {}
    if "username" in data:
        update["username"] = data["username"]
    if "password" in data and data["password"]:
        update["password_hash"] = hashlib.sha256(data["password"].encode()).hexdigest()
    if "role" in data:
        update["role"] = data["role"]
    if "condominium_ids" in data:
        update["condominium_ids"] = data["condominium_ids"]
    u = kb.update_user(user_id, **update)
    return {"id": u.id, "username": u.username, "role": u.role}

@router.delete("/api/admin/users/{user_id}")
async def admin_delete_user(user_id: int, request: Request = None):
    if request: _require_role(request, "supervisor")
    target = kb.get_user_by_id(user_id)
    if not target:
        raise HTTPException(404)
    if request:
        req_role = request.session.get("role", "")
        if req_role == "supervisor":
            my_ids = set(request.session.get("condominium_ids", []))
            target_ids = set(c.id for c in target.condominiums)
            if not my_ids.intersection(target_ids):
                raise HTTPException(403, "Solo puedes eliminar usuarios de tus condominios")
            if target.role != "technician":
                raise HTTPException(403, "Supervisores solo pueden eliminar técnicos")
    u = kb.delete_user(user_id)
    if not u:
        raise HTTPException(404)
    return {"deleted": user_id}


@router.get("/api/audit")
async def get_audit_logs(limit: int = Query(50), offset: int = Query(0)):
    logs = kb.get_recent_audits(limit=limit, offset=offset)
    total = kb.count_audits()
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "data": [
            {"id": l.id, "username": l.username, "action": l.action,
             "detail": l.detail, "timestamp": l.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
             "asset_id": l.asset_id}
            for l in logs
        ],
    }


# ── Web Push subscription ──


@router.post("/api/push/subscribe")
async def push_subscribe(data: dict):
    from web.push_notify import add_subscription, get_public_key
    add_subscription(data)
    return {"status": "ok"}


@router.post("/api/push/unsubscribe")
async def push_unsubscribe(data: dict):
    from web.push_notify import remove_subscription
    endpoint = data.get("endpoint")
    if endpoint:
        remove_subscription(endpoint)
    return {"status": "ok"}


@router.get("/api/push/public-key")
async def push_public_key():
    from web.push_notify import get_public_key
    return {"public_key": get_public_key()}


# ── Trigger push when a critical event is detected ──
def _check_and_send_push(asset_name: str, status: str, label: str = None):
    if status in ("high", "medium"):
        from web.push_notify import send_push
        level = "CRÍTICO" if status == "high" else "ATENCIÓN"
        send_push(
            title=f"Alerta {level} — {label or asset_name}",
            body=f"El activo {label or asset_name} cambió a estado {level}",
            tag=f"alert-{asset_name}",
            url="/",
        )


@router.post("/api/evaluate-all")
async def evaluate_all(request: Request = None):
    if request: _require_role(request, "supervisor")
    """Evaluate all assets using current sensor values.
    Called from the simulation drawer to recompute all assets."""
    for asset_name in list(latest_sensor_values.keys()):
        _evaluate_asset(asset_name)
    if active_connections:
        await broadcast(_build_full_data())
    return {"status": "ok", "evaluated": len(latest_sensor_values)}


@router.get("/api/health")
async def health():
    return {"status": "ok"}


@router.get("/api/debug")
async def debug():
    return {
        "sim_time": simulator.time,
        "scenarios": simulator.scenarios,
        "cycle": _cycle_counter,
        "active_connections": len(active_connections),
    }

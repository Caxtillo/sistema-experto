import json
from datetime import datetime
import csv, io
from fastapi import APIRouter, Query, HTTPException, Request
from fastapi.responses import PlainTextResponse, StreamingResponse, HTMLResponse
from fastapi import WebSocket, WebSocketDisconnect

from core.knowledge_base import KnowledgeBase
from core.inference_engine import InferenceEngine
from core.explanation import ExplanationEngine
from iiot_simulator.sensors import IIoTSimulator, SCENARIOS, RECOMMENDATIONS

router = APIRouter()
active_connections: set[WebSocket] = set()
kb = KnowledgeBase()
inference = InferenceEngine()
explainer = ExplanationEngine(inference)
simulator = IIoTSimulator(base_seed=42)

latest_sensor_values: dict[str, dict] = {}
latest_results: dict[str, dict] = {}
prev_statuses: dict[str, str] = {}
history_cache: dict[str, list] = {}
action_cache: list = []
event_cache = []
_cycle_counter = 0


def _ensure_asset_caches(asset_name: str, asset_label: str = ""):
    if asset_name not in latest_sensor_values:
        latest_sensor_values[asset_name] = {}
        latest_results[asset_name] = {"score": 0, "status": "none"}
        prev_statuses[asset_name] = "none"
        history_cache[asset_name] = []


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

    prev_statuses[asset_name] = status

    history_cache[asset_name].append({
        "time": datetime.now().strftime("%H:%M:%S"),
        "score": score,
        "sensors": dict(sensors_dict),
    })
    if len(history_cache[asset_name]) > 60:
        history_cache[asset_name] = history_cache[asset_name][-60:]

    if len(event_cache) > 50:
        event_cache[:] = event_cache[-50:]

    _cycle_counter += 1

async def run_simulation():
    import asyncio

    for asset in kb.get_all_assets():
        for act in kb.get_actuators(asset.id):
            simulator.set_actuator(asset.name, act.name, act.command)

    while True:
        try:
            assets = kb.get_all_assets()
            if not assets:
                await asyncio.sleep(2)
                continue
            sim_data = simulator.read_all()

            for asset in assets:
                asset_name = asset.name
                _ensure_asset_caches(asset_name, asset.label)

                sensors_list = kb.get_sensors(asset.id)
                rules_list = kb.get_rules(asset.id)
                actuators_list = kb.get_actuators(asset.id)

                sv = dict(sim_data.get(asset_name, {}))
                for s in sensors_list:
                    if s.sensor_type in ("external", "phone") and simulator.has_external(asset_name, s.name):
                        sv[s.name] = simulator.external_data[asset_name][s.name]

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
                            simulator.set_actuator(asset_name, act_name, act_value)
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

                update_asset_data(asset_name, sv, score, status, active_rules, asset.label)

                if _cycle_counter % 3 == 0:
                    for s_name, s_val in sv.items():
                        kb.add_reading(asset.id, s_name, float(s_val), score)

            simulator.step(dt=1.0)

            if active_connections:
                await broadcast(_build_full_data())

            if len(action_cache) > 100:
                action_cache[:] = action_cache[-100:]

            await asyncio.sleep(2)
        except Exception as e:
            import traceback
            traceback.print_exc()
            await asyncio.sleep(2)

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
    actuators_list = kb.get_actuators(asset.id)
    actuators_data = [
        {"id": a.id, "name": a.name, "label": a.label, "unit": a.unit,
         "value": a.command, "state": a.state, "auto": a.auto,
         "min_val": a.min_val, "max_val": a.max_val}
        for a in actuators_list
    ]
    return {
        "id": asset.id,
        "name": asset.label,
        "sensors": sv,
        "sensor_types": sensor_types,
        "sensors_meta": sensors_meta,
        "actuators": actuators_data,
        "score": lr["score"],
        "status": lr["status"],
        "rules": active_rules,
        "recommendations": RECOMMENDATIONS.get(asset_name, {}).get(lr["status"], ["No data"]),
        "explanation": explained["summary"],
        "scenarios": simulator.get_scenarios_list(asset_name),
        "current_scenario": simulator.scenarios.get(asset_name, "normal"),
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
async def get_data():
    return _build_full_data()

@router.get("/api/events")
async def get_events():
    db_events = kb.get_recent_events(limit=50)
    result = []
    for e in db_events:
        asset = kb.get_asset(e.asset_id)
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
    return history_cache.get(asset_name, [])

@router.get("/api/sensor-readings/{asset_name}/{sensor_name}")
async def get_sensor_readings(asset_name: str, sensor_name: str, limit: int = Query(60)):
    asset = kb.get_asset_by_name(asset_name)
    if not asset:
        raise HTTPException(404)
    readings = kb.get_recent_readings(asset.id, sensor_name=sensor_name, limit=limit)
    return [
        {
            "time": r.timestamp.strftime("%H:%M:%S"),
            "value": r.value,
            "score": r.score,
        }
        for r in readings
    ]

@router.post("/api/scenario/{asset_name}")
async def set_scenario(asset_name: str, scenario: str = Query(...), request: Request = None):
    if asset_name not in SCENARIOS:
        raise HTTPException(404, "Asset not found")
    if scenario not in SCENARIOS[asset_name]:
        raise HTTPException(400, f"Scenario must be one of: {list(SCENARIOS[asset_name].keys())}")

    simulator.set_scenario(asset_name, scenario)
    scenario_info = SCENARIOS[asset_name].get(scenario, {})
    label = scenario_info.get("label", scenario)
    asset_label = _get_asset_label(asset_name)

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

    return {"asset": asset_name, "scenario": scenario, "label": label}

@router.post("/api/random-fault")
async def random_fault(request: Request = None):
    import random as rnd
    fault_assets = [a for a in SCENARIOS if len(SCENARIOS[a]) > 1]
    if not fault_assets:
        raise HTTPException(400, "No assets with fault scenarios")
    asset = rnd.choice(fault_assets)
    fault_scenarios = [s for s in SCENARIOS[asset] if s != "normal"]
    if not fault_scenarios:
        raise HTTPException(400, "No fault scenarios available")
    scenario = rnd.choice(fault_scenarios)
    simulator.set_scenario(asset, scenario, auto_recover=True)
    scenario_info = SCENARIOS[asset][scenario]
    label = scenario_info.get("label", scenario)
    asset_label = _get_asset_label(asset)
    event_cache.append({
        "time": datetime.now().strftime("%H:%M:%S"),
        "asset": asset,
        "asset_name": asset_label,
        "from": "normal",
        "to": scenario,
        "score": 0,
        "type": "warning",
    })
    username = request.session.get("user", "unknown") if request else "unknown"
    kb.add_audit(username, "falla_aleatoria", f"{asset_label}: {scenario}")
    return {"asset": asset, "scenario": scenario, "label": label, "asset_name": asset_label}

@router.get("/api/scenarios/{asset_name}")
async def get_scenarios(asset_name: str):
    if asset_name not in SCENARIOS:
        raise HTTPException(404, "Asset not found")
    return simulator.get_scenarios_list(asset_name)

@router.get("/api/hierarchy")
async def get_hierarchy():
    """Returns the full hierarchy with asset statuses for the map."""
    condos = kb.get_all_condominiums()
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

@router.get("/api/mtbf/{asset_id}")
async def get_mtbf(asset_id: int):
    """Calculate MTBF for an asset based on event history."""
    asset = kb.get_asset(asset_id)
    if not asset:
        raise HTTPException(404)
    events = kb.get_recent_events(asset_id=asset_id, limit=1000)
    failures = [e for e in events if e.new_status in ("high",) and e.event_type == "warning"]
    now = datetime.now().timestamp()
    total_time = 3600 * 24 * 30
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
async def list_assets():
    assets = kb.get_all_assets()
    return [{"id": a.id, "name": a.name, "label": a.label, "icon": a.icon} for a in assets]

@router.get("/api/assets/{asset_id}")
async def get_asset_detail(asset_id: int):
    asset = kb.get_asset(asset_id)
    if not asset:
        raise HTTPException(404)
    sensors = kb.get_sensors(asset_id)
    rules = kb.get_rules(asset_id, enabled_only=False)
    return {
        "asset": {"id": asset.id, "name": asset.name, "label": asset.label, "icon": asset.icon,
                  "description": asset.description, "output_name": asset.output_name,
                  "output_label": asset.output_label, "output_min": asset.output_min,
                  "output_max": asset.output_max},
        "sensors": [{"id": s.id, "name": s.name, "label": s.label, "unit": s.unit,
                      "min_val": s.min_val, "max_val": s.max_val, "mf_config": s.mf_config}
                     for s in sensors],
        "rules": [{"id": r.id, "name": r.name, "description": r.description,
                    "operator": r.operator, "antecedents": r.antecedents,
                    "consequent": r.consequent, "weight": r.weight, "enabled": r.enabled}
                   for r in rules],
    }

@router.post("/api/assets")
async def create_asset(data: dict):
    a = kb.create_asset(
        name=data["name"], label=data.get("label", data["name"]),
        description=data.get("description", ""),
        icon=data.get("icon", "gear"),
        output_name=data.get("output_name", "output"),
        output_label=data.get("output_label", "Score"),
        output_min=data.get("output_min", 0),
        output_max=data.get("output_max", 100),
    )
    return {"id": a.id, "name": a.name, "label": a.label}

@router.put("/api/assets/{asset_id}")
async def update_asset(asset_id: int, data: dict):
    a = kb.update_asset(asset_id, **data)
    if not a:
        raise HTTPException(404)
    return {"id": a.id}

@router.delete("/api/assets/{asset_id}")
async def delete_asset(asset_id: int):
    a = kb.delete_asset(asset_id)
    if not a:
        raise HTTPException(404)
    return {"deleted": asset_id}

@router.post("/api/assets/{asset_id}/sensors")
async def add_sensor(asset_id: int, data: dict):
    s = kb.add_sensor(
        asset_id=asset_id, name=data["name"], label=data.get("label", data["name"]),
        unit=data.get("unit", ""), min_val=data.get("min_val", 0),
        max_val=data.get("max_val", 100), mf_config=data.get("mf_config", []),
    )
    return {"id": s.id, "name": s.name}

@router.put("/api/sensors/{sensor_id}")
async def update_sensor(sensor_id: int, data: dict):
    s = kb.update_sensor(sensor_id, **data)
    if not s:
        raise HTTPException(404)
    return {"id": s.id}

@router.delete("/api/sensors/{sensor_id}")
async def delete_sensor(sensor_id: int):
    s = kb.delete_sensor(sensor_id)
    if not s:
        raise HTTPException(404)
    return {"deleted": sensor_id}

@router.post("/api/assets/{asset_id}/rules")
async def add_rule(asset_id: int, data: dict):
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
async def update_rule(rule_id: int, data: dict):
    r = kb.update_rule(rule_id, **data)
    if not r:
        raise HTTPException(404)
    return {"id": r.id}

@router.delete("/api/rules/{rule_id}")
async def delete_rule(rule_id: int):
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
async def get_report():
    """Enhanced text report with MTBF and audit summary."""
    now = datetime.now()
    assets = kb.get_all_assets()
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
        lines.append(f"      Estado: {lr['status'].upper()}  Score: {lr['score']}/100")
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


def _calc_mtbf(asset_id: int) -> dict:
    events = kb.get_recent_events(asset_id=asset_id, limit=1000)
    failures = [e for e in events if e.new_status == "high" and e.event_type == "warning"]
    now_ts = datetime.now().timestamp()
    if len(failures) >= 2:
        timestamps = sorted([f.timestamp.timestamp() for f in failures], reverse=True)
        intervals = [timestamps[i] - timestamps[i + 1] for i in range(len(timestamps) - 1)]
        mtbf_hours = round((sum(intervals) / len(intervals)) / 3600, 1)
    elif len(failures) == 1:
        mtbf_hours = round((now_ts - failures[0].timestamp.timestamp()) / 3600, 1)
    else:
        mtbf_hours = 720.0
    return {"mtbf_hours": mtbf_hours, "failure_count": len(failures)}


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
async def report_csv_events(limit: int = Query(500)):
    events = kb.get_recent_events(limit=limit)
    rows = []
    for e in events:
        asset = kb.get_asset(e.asset_id)
        rows.append([
            e.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
            asset.name if asset else "?",
            asset.label if asset else "?",
            e.old_status, e.new_status, e.score, e.event_type
        ])
    return _csv_response(rows, "eventos.csv",
                         ["timestamp", "asset", "label", "from", "to", "score", "type"])


@router.get("/api/report/csv/readings")
async def report_csv_readings(asset_name: str = Query(""), limit: int = Query(500)):
    readings = []
    if asset_name:
        asset = kb.get_asset_by_name(asset_name)
        if asset:
            readings = kb.get_recent_readings(asset.id, limit=limit)
    else:
        for a in kb.get_all_assets():
            readings.extend(kb.get_recent_readings(a.id, limit=limit // max(len(kb.get_all_assets()), 1)))
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
async def report_csv_audit(limit: int = Query(500)):
    logs = kb.get_recent_audits(limit=limit)
    rows = []
    for l in logs:
        rows.append([
            l.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
            l.username, l.action, l.detail
        ])
    return _csv_response(rows, "auditoria.csv",
                         ["timestamp", "username", "action", "detail"])


@router.get("/api/report/html")
async def get_report_html():
    """Rich HTML report for printing / PDF export."""
    now = datetime.now()
    assets = kb.get_all_assets()
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
        f"<tr><td>{e['time']}</td><td>{e['asset_name']}</td><td>{e['from']}</td><td>{e['to']}</td></tr>"
        for e in event_cache[-20:]
    ) or "<tr><td colspan='4'>Sin eventos</td></tr>"

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
<div class="no-print"><button onclick="window.print()"> Imprimir / Guardar PDF</button></div>
<h1>Reporte de Estado - Sistema Experto</h1>
<div class="subtitle">Generado: {now.strftime('%d/%m/%Y %H:%M:%S')} | Activos: {len(assets)}</div>

<h2>Resumen</h2>
<div class="summary">
    <div class="summary-item" style="background:{status_colors['high']};">Rojo: {status_counts['high']}</div>
    <div class="summary-item" style="background:{status_colors['medium']};">Amarillo: {status_counts['medium']}</div>
    <div class="summary-item" style="background:{status_colors['low']};">Verde: {status_counts['low']}</div>
</div>

<h2>Detalle de Activos</h2>
<table><thead><tr><th>Activo</th><th>Estado</th><th>Score</th><th>MTBF</th><th>Fallos</th><th>Sensores</th></tr></thead>
<tbody>{rows_html}</tbody></table>

<h2>Eventos Recientes</h2>
<table><thead><tr><th>Hora</th><th>Activo</th><th>Anterior</th><th>Actual</th></tr></thead>
<tbody>{events_html}</tbody></table>

<div class="footer">Sistema Experto - Gestión de Activos Críticos con IIoT</div>
</body></html>"""
    return HTMLResponse(html)

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
async def receive_sensor_data(data: dict):
    asset_name = data.get("asset")
    sensor_name = data.get("sensor")
    value = data.get("value")

    if not all([asset_name, sensor_name, value is not None]):
        raise HTTPException(400, "Faltan campos: asset, sensor, value")

    asset = kb.get_asset_by_name(asset_name)
    if not asset:
        raise HTTPException(404, f"Activo '{asset_name}' no encontrado")

    sensors_list = kb.get_sensors(asset.id)
    sensor_config = next((s for s in sensors_list if s.name == sensor_name), None)
    if not sensor_config:
        raise HTTPException(404, f"Sensor '{sensor_name}' no encontrado en '{asset_name}'")

    value = float(value)
    value = max(sensor_config.min_val, min(sensor_config.max_val, value))

    simulator.inject_data(asset_name, sensor_name, value)

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
async def update_sensor_type(sensor_id: int, data: dict):
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


@router.get("/api/admin/users")
async def admin_list_users():
    users = kb.get_all_users()
    return [
        {"id": u.id, "username": u.username, "role": u.role,
         "condominium_id": u.condominium_id,
         "created_at": u.created_at.strftime("%Y-%m-%d %H:%M:%S") if u.created_at else ""}
        for u in users
    ]

@router.post("/api/admin/users")
async def admin_create_user(data: dict):
    import hashlib
    username = data.get("username")
    password = data.get("password")
    role = data.get("role", "technician")
    condominium_id = data.get("condominium_id")
    if not username or not password:
        raise HTTPException(400, "username and password required")
    existing = kb.get_user(username)
    if existing:
        raise HTTPException(409, "User already exists")
    pw_hash = hashlib.sha256(password.encode()).hexdigest()
    u = kb.create_user(username, pw_hash, role=role, condominium_id=condominium_id)
    users = kb.get_all_users()
    created = next((x for x in users if x.username == username), None)
    return {"id": created.id if created else 0, "username": username, "role": role}

@router.put("/api/admin/users/{user_id}")
async def admin_update_user(user_id: int, data: dict):
    import hashlib
    update = {}
    if "username" in data:
        update["username"] = data["username"]
    if "password" in data and data["password"]:
        update["password_hash"] = hashlib.sha256(data["password"].encode()).hexdigest()
    if "role" in data:
        update["role"] = data["role"]
    if "condominium_id" in data:
        update["condominium_id"] = data["condominium_id"]
    u = kb.update_user(user_id, **update)
    if not u:
        raise HTTPException(404)
    return {"id": u.id, "username": u.username, "role": u.role}

@router.delete("/api/admin/users/{user_id}")
async def admin_delete_user(user_id: int):
    u = kb.delete_user(user_id)
    if not u:
        raise HTTPException(404)
    return {"deleted": user_id}


@router.get("/api/audit")
async def get_audit_logs(limit: int = Query(100)):
    logs = kb.get_recent_audits(limit=limit)
    return [
        {"id": l.id, "username": l.username, "action": l.action,
         "detail": l.detail, "timestamp": l.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
         "asset_id": l.asset_id}
        for l in logs
    ]


@router.get("/api/debug")
async def debug():
    return {
        "sim_time": simulator.time,
        "scenarios": simulator.scenarios,
        "cycle": _cycle_counter,
        "active_connections": len(active_connections),
    }

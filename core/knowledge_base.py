"""Data access layer (CRUD) for all database models.

Provides a KnowledgeBase class with methods for creating, reading,
updating, and deleting assets, sensors, actuators, rules, and events.
Each method opens a new session, performs the operation, and closes it.

This is the single point of contact between the application logic
and the SQLAlchemy ORM.
"""

import re
from storage.database import get_session
from models.models import Asset, SensorConfig, Actuator, Rule, Event, SensorReading
from models.models import Condominium, Building, MachineRoom, User, AuditLog, user_condominiums
from sqlalchemy.orm import selectinload

# Default sensor/rule/actuator definitions for each base type (used by seed and reset)
SENSOR_DEFS = {
    "water": [
        ("vibration", "Vibración", "mm/s", 0, 20, ["bajo", "medio", "alto"]),
        ("temperature", "Temperatura", "°C", 0, 100, [{"name": "normal", "peak": 25}, {"name": "caliente", "peak": 50}, {"name": "critico", "peak": 80}]),
        ("pressure", "Presión", "bar", 0, 16, ["bajo", "normal", "alto"]),
        ("flow", "Caudal", "L/min", 0, 100, ["bajo", "normal", "alto"]),
        ("motor_current", "Corriente del Motor", "A", 0, 30, ["bajo", "normal", "alto"]),
    ],
    "generator": [
        ("rpm", "RPM", "rpm", 0, 2000, [{"name": "bajo", "peak": 0}, {"name": "normal", "peak": 1700}, {"name": "alto", "peak": 1900}]),
        ("temperature", "Temperatura", "°C", 0, 120, [{"name": "normal", "peak": 70}, {"name": "caliente", "peak": 90}, {"name": "critico", "peak": 110}]),
        ("fuel_level", "Nivel Combustible", "%", 0, 100, ["critico", "bajo", "normal"]),
        ("voltage", "Voltaje", "V", 0, 300, [{"name": "bajo", "peak": 140}, {"name": "normal", "peak": 220}, {"name": "alto", "peak": 260}]),
        ("oil_pressure", "Presión del Aceite", "bar", 0, 8, [{"name": "bajo", "peak": 0.5}, {"name": "normal", "peak": 5}, {"name": "alto", "peak": 7}]),
    ],
    "elevator": [
        ("vibration", "Vibración", "mm/s", 0, 15, ["bajo", "medio", "alto"]),
        ("temperature", "Temperatura", "°C", 0, 80, [{"name": "normal", "peak": 30}, {"name": "caliente", "peak": 50}, {"name": "critico", "peak": 70}]),
        ("speed_var", "Var. Velocidad", "%", 0, 20, ["estable", "moderado", "erratico"]),
        ("motor_current", "Corriente del Motor", "A", 0, 40, [{"name": "bajo", "peak": 0}, {"name": "normal", "peak": 8}, {"name": "alto", "peak": 25}]),
    ],
}

ACTUATOR_DEFS = {
    "water": [
        ("inlet_valve", "Válvula de entrada", "%", 0, 100, True),
        ("bypass_valve", "Válvula de by-pass", "%", 0, 100, True),
        ("alarm", "Alarma", None, 0, 1, False),
    ],
    "generator": [
        ("speed_control", "Control de velocidad", "%", 0, 100, True),
        ("choke", "Estrangulador", "%", 0, 100, True),
        ("alarm", "Alarma", None, 0, 1, False),
    ],
    "elevator": [
        ("speed_regulator", "Regulador velocidad", "%", 0, 100, True),
        ("brake", "Freno", None, 0, 1, True),
        ("alarm", "Alarma", None, 0, 1, False),
    ],
}

RULE_DEFS = {
    "water": [
        ("R1", "SI vibración ALTA Y temperatura CRÍTICO ENTONCES alta urgencia", "and",
         [{"sensor": "vibration", "term": "alto"}, {"sensor": "temperature", "term": "critico"}],
         {"sensor": "urgency", "term": "high"},
         {"actuator": "alarm", "value": 1}, 1.0),
        ("R2", "SI caudal BAJO Y presión ALTA ENTONCES alta urgencia", "and",
         [{"sensor": "flow", "term": "bajo"}, {"sensor": "pressure", "term": "alto"}],
         {"sensor": "urgency", "term": "high"},
         {"actuator": "bypass_valve", "value": 100}, 1.0),
        ("R3", "SI corriente ALTA ENTONCES alta urgencia", "and",
         [{"sensor": "motor_current", "term": "alto"}],
         {"sensor": "urgency", "term": "high"},
         {"actuator": "inlet_valve", "value": 100}, 1.0),
        ("R4", "SI vibración BAJA Y caudal NORMAL Y presión NORMAL ENTONCES baja urgencia", "and",
         [{"sensor": "vibration", "term": "bajo"}, {"sensor": "flow", "term": "normal"}, {"sensor": "pressure", "term": "normal"}],
         {"sensor": "urgency", "term": "low"},
         {"actuator": "inlet_valve", "value": 50}, 1.0),
    ],
    "generator": [
        ("R1", "SI temperatura CRÍTICO Y RPM ALTA ENTONCES alto mantenimiento", "and",
         [{"sensor": "temperature", "term": "critico"}, {"sensor": "rpm", "term": "alto"}],
         {"sensor": "maintenance", "term": "high"},
         {"actuator": "speed_control", "value": 60}, 1.0),
        ("R2", "SI combustible CRÍTICO ENTONCES alto mantenimiento", "and",
         [{"sensor": "fuel_level", "term": "critico"}],
         {"sensor": "maintenance", "term": "high"},
         {"actuator": "alarm", "value": 1}, 1.0),
        ("R3", "SI presión aceite BAJA Y temperatura CALIENTE ENTONCES alto mantenimiento", "and",
         [{"sensor": "oil_pressure", "term": "bajo"}, {"sensor": "temperature", "term": "caliente"}],
         {"sensor": "maintenance", "term": "high"},
         {"actuator": "choke", "value": 80}, 1.0),
        ("R4", "SI voltaje NORMAL Y temperatura NORMAL Y combustible NORMAL ENTONCES bajo mantenimiento", "and",
         [{"sensor": "voltage", "term": "normal"}, {"sensor": "temperature", "term": "normal"}, {"sensor": "fuel_level", "term": "normal"}],
         {"sensor": "maintenance", "term": "low"},
         {"actuator": "speed_control", "value": 50}, 1.0),
    ],
    "elevator": [
        ("R1", "SI vibración ALTA Y temperatura CRÍTICO ENTONCES alto mantenimiento", "and",
         [{"sensor": "vibration", "term": "alto"}, {"sensor": "temperature", "term": "critico"}],
         {"sensor": "maintenance", "term": "high"},
         {"actuator": "brake", "value": 1}, 1.0),
        ("R2", "SI velocidad ERRÁTICA Y corriente ALTA ENTONCES alto mantenimiento", "and",
         [{"sensor": "speed_var", "term": "erratico"}, {"sensor": "motor_current", "term": "alto"}],
         {"sensor": "maintenance", "term": "high"},
         {"actuator": "speed_regulator", "value": 70}, 1.0),
        ("R3", "SI vibración BAJA Y velocidad ESTABLE Y corriente NORMAL ENTONCES bajo mantenimiento", "and",
         [{"sensor": "vibration", "term": "bajo"}, {"sensor": "speed_var", "term": "estable"}, {"sensor": "motor_current", "term": "normal"}],
         {"sensor": "maintenance", "term": "low"},
         {"actuator": "speed_regulator", "value": 50}, 1.0),
    ],
}

TYPE_SLUG_TO_BASE = {"bomba": "water", "planta": "generator", "ascensor": "elevator"}

ASSET_TYPE_SLUGS = {
    "bomba": {"label": "Bomba", "icon": "droplets", "output_name": "urgency", "output_label": "Urgencia", "output_min": 0, "output_max": 100},
    "planta": {"label": "Planta Eléctrica", "icon": "zap", "output_name": "maintenance", "output_label": "Prioridad de Mantenimiento", "output_min": 0, "output_max": 100},
    "ascensor": {"label": "Ascensor", "icon": "arrow-up", "output_name": "maintenance", "output_label": "Prioridad de Mantenimiento", "output_min": 0, "output_max": 100},
}


def auto_generate_mf(terms, min_val, max_val):
    n = len(terms)
    if n == 0:
        return []
    step = (max_val - min_val) / max(n - 1, 1)
    peaks = []
    for i, t in enumerate(terms):
        if isinstance(t, str):
            peaks.append(min_val + i * step)
        else:
            peaks.append(t.get("peak", min_val + i * step))
    if n == 1:
        return [{"term": terms[0] if isinstance(terms[0], str) else terms[0]["name"], "type": "trimf", "params": [min_val, peaks[0], max_val]}]
    result = []
    for i in range(n):
        name = terms[i] if isinstance(terms[i], str) else terms[i]["name"]
        p = peaks[i]
        a = min_val if i == 0 else peaks[i - 1]
        c = max_val if i == n - 1 else peaks[i + 1]
        result.append({"term": name, "type": "trimf", "params": [a, p, c]})
    return result


class KnowledgeBase:
    """CRUD operations for all domain entities."""

    # ---- Asset ----

    def get_all_assets(self):
        """Return all assets."""
        session = get_session()
        try:
            return session.query(Asset).all()
        finally:
            session.close()

    def get_asset(self, asset_id):
        """Return a single asset by ID."""
        session = get_session()
        try:
            return session.query(Asset).filter_by(id=asset_id).first()
        finally:
            session.close()

    def get_asset_by_name(self, name):
        """Return a single asset by its unique name."""
        session = get_session()
        try:
            return session.query(Asset).filter_by(name=name).first()
        finally:
            session.close()

    def reset_asset_defaults(self, asset):
        """Delete all sensors/rules/actuators for an asset and recreate from hardcoded defaults."""
        type_slug = asset.name.split("_")[0]
        base_type = TYPE_SLUG_TO_BASE.get(type_slug)
        if not base_type:
            return False
        session = get_session()
        try:
            session.query(Rule).filter_by(asset_id=asset.id).delete()
            session.query(SensorConfig).filter_by(asset_id=asset.id).delete()
            session.query(Actuator).filter_by(asset_id=asset.id).delete()
            for s_name, s_label, s_unit, s_min, s_max, terms in SENSOR_DEFS[base_type]:
                mf = auto_generate_mf(terms, s_min, s_max)
                session.add(SensorConfig(
                    asset_id=asset.id, name=s_name, label=s_label, unit=s_unit,
                    min_val=s_min, max_val=s_max, mf_config=mf,
                ))
            for a_name, a_label, a_unit, a_min, a_max, a_auto in ACTUATOR_DEFS[base_type]:
                session.add(Actuator(
                    asset_id=asset.id, name=a_name, label=a_label,
                    unit=a_unit, min_val=a_min, max_val=a_max, auto=a_auto,
                ))
            for r_name, r_desc, r_op, r_ant, r_con, r_act, r_w in RULE_DEFS[base_type]:
                session.add(Rule(
                    asset_id=asset.id, name=r_name, description=r_desc,
                    operator=r_op, antecedents=r_ant, consequent=r_con,
                    action=r_act, weight=r_w,
                ))
            session.commit()
            return True
        finally:
            session.close()

    def get_sensors(self, asset_id):
        """Return all sensors for an asset."""
        session = get_session()
        try:
            return session.query(SensorConfig).filter_by(asset_id=asset_id).all()
        finally:
            session.close()

    def get_rules(self, asset_id, enabled_only=True):
        """Return rules for an asset, optionally filtering to enabled ones only."""
        session = get_session()
        try:
            q = session.query(Rule).filter_by(asset_id=asset_id)
            if enabled_only:
                q = q.filter_by(enabled=True)
            return q.all()
        finally:
            session.close()

    def create_asset(self, name, label, description="", icon="gear",
                     output_name="output", output_label="Score",
                     output_min=0, output_max=100, location_id=None):
        """Create a new asset with the given parameters."""
        session = get_session()
        try:
            a = Asset(name=name, label=label, description=description, icon=icon,
                      output_name=output_name, output_label=output_label,
                      output_min=output_min, output_max=output_max,
                      location_id=location_id)
            session.add(a)
            session.commit()
            return a
        finally:
            session.close()

    def update_asset(self, asset_id, **kwargs):
        """Update an asset's fields. Only updates attributes that exist on the model."""
        session = get_session()
        try:
            a = session.query(Asset).filter_by(id=asset_id).first()
            if a:
                for k, v in kwargs.items():
                    if hasattr(a, k):
                        setattr(a, k, v)
                session.commit()
            return a
        finally:
            session.close()

    def delete_asset(self, asset_id):
        """Delete an asset and all its cascaded data (sensors, rules, events)."""
        session = get_session()
        try:
            a = session.query(Asset).filter_by(id=asset_id).first()
            if a:
                session.delete(a)
                session.commit()
            return a
        finally:
            session.close()

    # ---- Sensor ----

    def add_sensor(self, asset_id, name, label, unit="", min_val=0, max_val=100, mf_config=None):
        """Add a new sensor configuration to an asset."""
        session = get_session()
        try:
            s = SensorConfig(asset_id=asset_id, name=name, label=label, unit=unit,
                             min_val=min_val, max_val=max_val,
                             mf_config=mf_config or [])
            session.add(s)
            session.commit()
            return s
        finally:
            session.close()

    def update_sensor(self, sensor_id, **kwargs):
        """Update a sensor configuration's fields."""
        session = get_session()
        try:
            s = session.query(SensorConfig).filter_by(id=sensor_id).first()
            if s:
                for k, v in kwargs.items():
                    if hasattr(s, k):
                        setattr(s, k, v)
                session.commit()
            return s
        finally:
            session.close()

    def delete_sensor(self, sensor_id):
        """Delete a sensor configuration."""
        session = get_session()
        try:
            s = session.query(SensorConfig).filter_by(id=sensor_id).first()
            if s:
                session.delete(s)
                session.commit()
            return s
        finally:
            session.close()

    # ---- Actuator ----

    def get_actuators(self, asset_id):
        """Return all actuators for an asset."""
        session = get_session()
        try:
            return session.query(Actuator).filter_by(asset_id=asset_id).all()
        finally:
            session.close()

    def get_actuator(self, actuator_id):
        """Return a single actuator by ID."""
        session = get_session()
        try:
            return session.query(Actuator).filter_by(id=actuator_id).first()
        finally:
            session.close()

    def update_actuator(self, actuator_id, **kwargs):
        """Update an actuator's command, state, or auto mode."""
        session = get_session()
        try:
            a = session.query(Actuator).filter_by(id=actuator_id).first()
            if a:
                for k, v in kwargs.items():
                    if hasattr(a, k):
                        setattr(a, k, v)
                session.commit()
            return a
        finally:
            session.close()

    # ---- Rule ----

    def add_rule(self, asset_id, antecedents, consequent, action=None, name="", description="",
                 operator="and", weight=1.0, enabled=True):
        """Add a new fuzzy rule with optional actuator action."""
        session = get_session()
        try:
            r = Rule(asset_id=asset_id, name=name, description=description,
                     operator=operator, antecedents=antecedents,
                     consequent=consequent, action=action,
                     weight=weight, enabled=enabled)
            session.add(r)
            session.commit()
            return r
        finally:
            session.close()

    def update_rule(self, rule_id, **kwargs):
        """Update a rule's fields."""
        session = get_session()
        try:
            r = session.query(Rule).filter_by(id=rule_id).first()
            if r:
                for k, v in kwargs.items():
                    if hasattr(r, k):
                        setattr(r, k, v)
                session.commit()
            return r
        finally:
            session.close()

    def delete_rule(self, rule_id):
        """Delete a rule."""
        session = get_session()
        try:
            r = session.query(Rule).filter_by(id=rule_id).first()
            if r:
                session.delete(r)
                session.commit()
            return r
        finally:
            session.close()

    # ---- Event ----

    def add_event(self, asset_id, old_status, new_status, score=0, message="", event_type="info"):
        """Record a status transition event for an asset."""
        session = get_session()
        try:
            e = Event(asset_id=asset_id, old_status=old_status,
                      new_status=new_status, score=score,
                      message=message, event_type=event_type)
            session.add(e)
            session.commit()
            return e
        finally:
            session.close()

    def get_recent_events(self, limit=50, asset_id=None):
        """Return the most recent events, ordered by timestamp descending."""
        session = get_session()
        try:
            q = session.query(Event)
            if asset_id is not None:
                q = q.filter(Event.asset_id == asset_id)
            return q.order_by(Event.timestamp.desc()).limit(limit).all()
        finally:
            session.close()

    # ---- Sensor Readings ----

    def add_reading(self, asset_id, sensor_name, value, score=0, sync_uuid=None):
        session = get_session()
        try:
            r = SensorReading(asset_id=asset_id, sensor_name=sensor_name,
                              value=value, score=score, sync_uuid=sync_uuid)
            session.add(r)
            session.commit()
            return r
        finally:
            session.close()

    def get_recent_readings(self, asset_id, sensor_name=None, limit=100):
        """Return recent sensor readings for an asset, optionally filtered by sensor name."""
        session = get_session()
        try:
            q = session.query(SensorReading).filter_by(asset_id=asset_id)
            if sensor_name:
                q = q.filter_by(sensor_name=sensor_name)
            return q.order_by(SensorReading.timestamp.desc()).limit(limit).all()
        finally:
            session.close()

    def get_reading_batches(self, asset_id, limit=20):
        """Return reading batches grouped by rounded timestamp, newest first.

        Each batch combines all sensor readings at the same minute into one snapshot
        with an average score.
        """
        session = get_session()
        try:
            readings = (session.query(SensorReading)
                        .filter_by(asset_id=asset_id)
                        .order_by(SensorReading.timestamp.desc())
                        .limit(limit * 10)
                        .all())
            batches = {}
            for r in readings:
                key = r.timestamp.replace(second=0, microsecond=0)
                if key not in batches:
                    batches[key] = {"time": r.timestamp, "sensors": {}, "scores": []}
                batches[key]["sensors"][r.sensor_name] = r.value
                batches[key]["scores"].append(r.score)
            result = []
            for ts, data in sorted(batches.items(), key=lambda x: x[0], reverse=True)[:limit]:
                avg_score = sum(data["scores"]) / len(data["scores"]) if data["scores"] else 0
                result.append({
                    "time": data["time"].strftime("%Y-%m-%d %H:%M"),
                    "score": round(avg_score),
                    "sensors": data["sensors"],
                })
            return result
        finally:
            session.close()

    def get_history_range(self, asset_id, sensor_name, minutes=30):
        """Return readings for a specific sensor within the last N minutes."""
        from datetime import datetime, timedelta, timezone
        since = datetime.now(timezone.utc) - timedelta(minutes=minutes)
        session = get_session()
        try:
            return session.query(SensorReading).filter_by(
                asset_id=asset_id, sensor_name=sensor_name
            ).filter(SensorReading.timestamp >= since).order_by(SensorReading.timestamp).all()
        finally:
            session.close()

    # ---- Hierarchy ----

    def get_all_condominiums(self):
        session = get_session()
        try:
            return session.query(Condominium).all()
        finally:
            session.close()

    def get_condominium(self, condominium_id):
        session = get_session()
        try:
            return session.query(Condominium).filter_by(id=condominium_id).first()
        finally:
            session.close()

    def create_condominium(self, name, slug=None, address="", lat=None, lng=None):
        session = get_session()
        try:
            if not slug:
                slug = re.sub(r'[^a-z0-9]+', '_', name.lower()).strip('_')
            c = Condominium(name=name, slug=slug, address=address, lat=lat, lng=lng)
            session.add(c)
            session.commit()
            return c
        finally:
            session.close()

    def update_condominium(self, condominium_id, **kwargs):
        session = get_session()
        try:
            c = session.query(Condominium).filter_by(id=condominium_id).first()
            if c:
                for k, v in kwargs.items():
                    if hasattr(c, k):
                        setattr(c, k, v)
                session.commit()
            return c
        finally:
            session.close()

    def delete_condominium(self, condominium_id):
        session = get_session()
        try:
            c = session.query(Condominium).filter_by(id=condominium_id).first()
            if c:
                session.delete(c)
                session.commit()
            return c
        finally:
            session.close()

    def get_building(self, building_id):
        session = get_session()
        try:
            return session.query(Building).filter_by(id=building_id).first()
        finally:
            session.close()

    def db_get_room(self, room_id):
        session = get_session()
        try:
            return session.query(MachineRoom).filter_by(id=room_id).first()
        finally:
            session.close()

    def get_buildings(self, condominium_id):
        session = get_session()
        try:
            return session.query(Building).filter_by(condominium_id=condominium_id).all()
        finally:
            session.close()

    def create_building(self, condominium_id, name):
        session = get_session()
        try:
            b = Building(condominium_id=condominium_id, name=name)
            session.add(b)
            session.commit()
            return b
        finally:
            session.close()

    def update_building(self, building_id, **kwargs):
        session = get_session()
        try:
            b = session.query(Building).filter_by(id=building_id).first()
            if b:
                for k, v in kwargs.items():
                    if hasattr(b, k):
                        setattr(b, k, v)
                session.commit()
            return b
        finally:
            session.close()

    def delete_building(self, building_id):
        session = get_session()
        try:
            b = session.query(Building).filter_by(id=building_id).first()
            if b:
                session.delete(b)
                session.commit()
            return b
        finally:
            session.close()

    def get_rooms(self, building_id):
        session = get_session()
        try:
            return session.query(MachineRoom).filter_by(building_id=building_id).all()
        finally:
            session.close()

    def create_room(self, building_id, name):
        session = get_session()
        try:
            r = MachineRoom(building_id=building_id, name=name)
            session.add(r)
            session.commit()
            return r
        finally:
            session.close()

    def update_room(self, room_id, **kwargs):
        session = get_session()
        try:
            r = session.query(MachineRoom).filter_by(id=room_id).first()
            if r:
                for k, v in kwargs.items():
                    if hasattr(r, k):
                        setattr(r, k, v)
                session.commit()
            return r
        finally:
            session.close()

    def delete_room(self, room_id):
        session = get_session()
        try:
            r = session.query(MachineRoom).filter_by(id=room_id).first()
            if r:
                session.delete(r)
                session.commit()
            return r
        finally:
            session.close()

    def get_assets_in_room(self, room_id):
        session = get_session()
        try:
            return session.query(Asset).filter_by(location_id=room_id).all()
        finally:
            session.close()

    def get_next_asset_number(self, type_slug: str, condo_slug: str) -> int:
        """Find the next available asset number for a type+condo combination.
        e.g. get_next_asset_number('bomba', 'san_miguel') -> 3 if bomba_san_miguel_1 and _2 exist.
        """
        session = get_session()
        try:
            prefix = f"{type_slug}_{condo_slug}_"
            pattern = prefix + "%"
            existing = session.query(Asset).filter(Asset.name.like(pattern)).all()
            max_n = 0
            for a in existing:
                parts = a.name.split("_")
                if parts and parts[-1].isdigit():
                    max_n = max(max_n, int(parts[-1]))
            return max_n + 1
        finally:
            session.close()

    def make_asset_name(self, type_slug: str, condo_slug: str) -> str:
        """Generate a unique asset name following the nomenclature.
        e.g. make_asset_name('bomba', 'san_miguel') -> 'bomba_san_miguel_3'
        """
        n = self.get_next_asset_number(type_slug, condo_slug)
        return f"{type_slug}_{condo_slug}_{n}"

    def get_location_path(self, asset_id):
        """Return the full location path for an asset, e.g. 'Los Olivos > Edificio Principal > Sótano'."""
        session = get_session()
        try:
            asset = session.query(Asset).filter_by(id=asset_id).first()
            if not asset or not asset.location_id:
                return ""
            room = session.query(MachineRoom).filter_by(id=asset.location_id).first()
            if not room:
                return ""
            building = session.query(Building).filter_by(id=room.building_id).first()
            condo = session.query(Condominium).filter_by(id=building.condominium_id).first() if building else None
            parts = []
            if condo: parts.append(condo.name)
            if building: parts.append(building.name)
            parts.append(room.name)
            return " > ".join(parts)
        finally:
            session.close()

    def get_full_hierarchy(self):
        """Return full tree: condominiums -> buildings -> rooms -> assets."""
        session = get_session()
        try:
            condos = session.query(Condominium).all()
            result = []
            for c in condos:
                cdata = {"id": c.id, "name": c.name, "address": c.address,
                         "lat": c.lat, "lng": c.lng, "buildings": []}
                for b in c.buildings:
                    bdata = {"id": b.id, "name": b.name, "rooms": []}
                    for r in b.rooms:
                        rdata = {"id": r.id, "name": r.name, "assets": []}
                        for a in r.assets:
                            rdata["assets"].append({
                                "id": a.id, "name": a.name, "label": a.label,
                                "icon": a.icon, "output_name": a.output_name
                            })
                        bdata["rooms"].append(rdata)
                    cdata["buildings"].append(bdata)
                result.append(cdata)
            return result
        finally:
            session.close()

    # ---- Users ----

    def get_user(self, username):
        session = get_session()
        try:
            return session.query(User).options(selectinload(User.condominiums)).filter_by(username=username).first()
        finally:
            session.close()

    def get_user_by_id(self, user_id):
        session = get_session()
        try:
            return session.query(User).options(selectinload(User.condominiums)).filter_by(id=user_id).first()
        finally:
            session.close()

    def create_user(self, username, password_hash, role="technician", condominium_ids=None):
        session = get_session()
        try:
            condominiums = []
            if condominium_ids:
                condominiums = session.query(Condominium).filter(Condominium.id.in_(condominium_ids)).all()
            u = User(username=username, password_hash=password_hash,
                     role=role, condominiums=condominiums)
            session.add(u)
            session.commit()
            return u
        finally:
            session.close()

    def get_all_users(self):
        session = get_session()
        try:
            return session.query(User).options(selectinload(User.condominiums)).all()
        finally:
            session.close()

    def update_user(self, user_id, **kwargs):
        session = get_session()
        try:
            u = session.query(User).filter_by(id=user_id).first()
            if not u:
                return None
            # Handle condominium_ids separately (many-to-many)
            condo_ids = kwargs.pop("condominium_ids", None)
            for k, v in kwargs.items():
                if hasattr(u, k):
                    setattr(u, k, v)
            if condo_ids is not None:
                condos = session.query(Condominium).filter(Condominium.id.in_(condo_ids)).all() if condo_ids else []
                u.condominiums = condos
            session.commit()
            return u
        finally:
            session.close()

    def delete_user(self, user_id):
        session = get_session()
        try:
            u = session.query(User).filter_by(id=user_id).first()
            if not u:
                return None
            session.delete(u)
            session.commit()
            return u
        finally:
            session.close()

    # ---- Audit Log ----

    def add_audit(self, username, action, detail="", asset_id=None, user_id=None):
        session = get_session()
        try:
            entry = AuditLog(username=username, action=action, detail=detail,
                             asset_id=asset_id, user_id=user_id)
            session.add(entry)
            session.commit()
            return entry
        finally:
            session.close()

    def get_recent_audits(self, limit=100, offset=0):
        session = get_session()
        try:
            return session.query(AuditLog).order_by(AuditLog.timestamp.desc()).offset(offset).limit(limit).all()
        finally:
            session.close()

    def count_audits(self):
        session = get_session()
        try:
            return session.query(AuditLog).count()
        finally:
            session.close()

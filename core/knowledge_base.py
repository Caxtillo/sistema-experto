"""Data access layer (CRUD) for all database models.

Provides a KnowledgeBase class with methods for creating, reading,
updating, and deleting assets, sensors, actuators, rules, and events.
Each method opens a new session, performs the operation, and closes it.

This is the single point of contact between the application logic
and the SQLAlchemy ORM.
"""

from storage.database import get_session
from models.models import Asset, SensorConfig, Actuator, Rule, Event, SensorReading
from models.models import Condominium, Building, MachineRoom, User, AuditLog


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

    def add_reading(self, asset_id, sensor_name, value, score=0):
        """Persist a sensor reading with its associated diagnosis score."""
        session = get_session()
        try:
            r = SensorReading(asset_id=asset_id, sensor_name=sensor_name,
                              value=value, score=score)
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

    def create_condominium(self, name, address="", lat=None, lng=None):
        session = get_session()
        try:
            c = Condominium(name=name, address=address, lat=lat, lng=lng)
            session.add(c)
            session.commit()
            return c
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

    def get_assets_in_room(self, room_id):
        session = get_session()
        try:
            return session.query(Asset).filter_by(location_id=room_id).all()
        finally:
            session.close()

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
            return session.query(User).filter_by(username=username).first()
        finally:
            session.close()

    def get_user_by_id(self, user_id):
        session = get_session()
        try:
            return session.query(User).filter_by(id=user_id).first()
        finally:
            session.close()

    def create_user(self, username, password_hash, role="technician", condominium_id=None):
        session = get_session()
        try:
            u = User(username=username, password_hash=password_hash,
                     role=role, condominium_id=condominium_id)
            session.add(u)
            session.commit()
            return u
        finally:
            session.close()

    def get_all_users(self):
        session = get_session()
        try:
            return session.query(User).all()
        finally:
            session.close()

    def update_user(self, user_id, **kwargs):
        session = get_session()
        try:
            u = session.query(User).filter_by(id=user_id).first()
            if not u:
                return None
            for k, v in kwargs.items():
                if hasattr(u, k):
                    setattr(u, k, v)
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

    def get_recent_audits(self, limit=100):
        session = get_session()
        try:
            return session.query(AuditLog).order_by(AuditLog.timestamp.desc()).limit(limit).all()
        finally:
            session.close()

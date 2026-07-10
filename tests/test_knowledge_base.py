import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from storage.database import engine, SessionLocal, init_db
from models.models import Base, Condominium, Building, MachineRoom, Asset, SensorConfig, Rule, User, AuditLog, SensorReading, Event


@pytest.fixture(autouse=True)
def setup_db():
    init_db()
    session = SessionLocal()
    try:
        for table in reversed(Base.metadata.sorted_tables):
            session.execute(table.delete())
        session.commit()
    finally:
        session.close()
    yield
    session = SessionLocal()
    try:
        for table in reversed(Base.metadata.sorted_tables):
            session.execute(table.delete())
        session.commit()
    finally:
        session.close()


@pytest.fixture
def session():
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()


@pytest.fixture
def kb():
    from core.knowledge_base import KnowledgeBase
    return KnowledgeBase()


def _create_minimal_condo(kb, session, name="C"):
    kb.create_condominium(name)
    return session.query(Condominium).filter_by(name=name).first().id


def _create_minimal_building(kb, session, condo_id, name="B"):
    kb.create_building(condo_id, name)
    return session.query(Building).filter_by(name=name, condominium_id=condo_id).first().id


def _create_minimal_room(kb, session, building_id, name="R"):
    kb.create_room(building_id, name)
    return session.query(MachineRoom).filter_by(name=name, building_id=building_id).first().id


def _create_minimal_asset(kb, session, room_id, name="a1", label="A1"):
    kb.create_asset(name=name, label=label, location_id=room_id)
    return session.query(Asset).filter_by(name=name).first().id


class TestKnowledgeBase:

    def test_create_condominium(self, kb, session):
        cid = _create_minimal_condo(kb, session, "Test Condo")
        assert cid is not None
        assert session.query(Condominium).count() == 1

    def test_get_all_condominiums(self, kb, session):
        kb.create_condominium("C1")
        kb.create_condominium("C2")
        assert len(kb.get_all_condominiums()) == 2

    def test_get_condominium(self, kb, session):
        cid = _create_minimal_condo(kb, session, "MyCondo")
        found = kb.get_condominium(cid)
        assert found is not None
        assert found.name == "MyCondo"

    def test_update_condominium(self, kb, session):
        cid = _create_minimal_condo(kb, session, "Old")
        kb.update_condominium(cid, name="New Name")
        session.expire_all()
        assert session.query(Condominium).filter_by(id=cid).first().name == "New Name"

    def test_delete_condominium(self, kb, session):
        cid = _create_minimal_condo(kb, session)
        kb.delete_condominium(cid)
        session.expire_all()
        assert session.query(Condominium).count() == 0

    def test_create_building(self, kb, session):
        cid = _create_minimal_condo(kb, session)
        bid = _create_minimal_building(kb, session, cid, "Torre A")
        assert session.query(Building).count() == 1

    def test_get_buildings(self, kb, session):
        cid = _create_minimal_condo(kb, session)
        kb.create_building(cid, "B1")
        kb.create_building(cid, "B2")
        assert len(kb.get_buildings(cid)) == 2

    def test_delete_building(self, kb, session):
        cid = _create_minimal_condo(kb, session)
        bid = _create_minimal_building(kb, session, cid)
        kb.delete_building(bid)
        session.expire_all()
        assert session.query(Building).count() == 0

    def test_create_room(self, kb, session):
        cid = _create_minimal_condo(kb, session)
        bid = _create_minimal_building(kb, session, cid)
        rid = _create_minimal_room(kb, session, bid, "Sótano")
        assert session.query(MachineRoom).count() == 1

    def test_get_rooms(self, kb, session):
        cid = _create_minimal_condo(kb, session)
        bid = _create_minimal_building(kb, session, cid)
        kb.create_room(bid, "R1")
        kb.create_room(bid, "R2")
        assert len(kb.get_rooms(bid)) == 2

    def test_delete_room(self, kb, session):
        cid = _create_minimal_condo(kb, session)
        bid = _create_minimal_building(kb, session, cid)
        rid = _create_minimal_room(kb, session, bid)
        kb.delete_room(rid)
        session.expire_all()
        assert session.query(MachineRoom).count() == 0

    def test_create_asset(self, kb, session):
        cid = _create_minimal_condo(kb, session)
        bid = _create_minimal_building(kb, session, cid)
        rid = _create_minimal_room(kb, session, bid)
        kb.create_asset(name="bomba_01", label="Bomba #1", location_id=rid)
        assert session.query(Asset).count() == 1
        assert session.query(Asset).first().name == "bomba_01"

    def test_get_assets_in_room(self, kb, session):
        cid = _create_minimal_condo(kb, session)
        bid = _create_minimal_building(kb, session, cid)
        rid = _create_minimal_room(kb, session, bid)
        kb.create_asset("a1", "A1", location_id=rid)
        kb.create_asset("a2", "A2", location_id=rid)
        session.expire_all()
        assert len(kb.get_assets_in_room(rid)) == 2

    def test_get_all_assets(self, kb, session):
        cid = _create_minimal_condo(kb, session)
        bid = _create_minimal_building(kb, session, cid)
        rid = _create_minimal_room(kb, session, bid)
        kb.create_asset("a1", "A1", location_id=rid)
        kb.create_asset("a2", "A2", location_id=rid)
        assert len(kb.get_all_assets()) == 2

    def test_get_asset(self, kb, session):
        cid = _create_minimal_condo(kb, session)
        bid = _create_minimal_building(kb, session, cid)
        rid = _create_minimal_room(kb, session, bid)
        aid = _create_minimal_asset(kb, session, rid, "test_asset", "Test")
        fetched = kb.get_asset(aid)
        assert fetched is not None
        assert fetched.name == "test_asset"

    def test_update_asset(self, kb, session):
        cid = _create_minimal_condo(kb, session)
        bid = _create_minimal_building(kb, session, cid)
        rid = _create_minimal_room(kb, session, bid)
        aid = _create_minimal_asset(kb, session, rid, "a1", "A1")
        kb.update_asset(aid, label="Updated")
        session.expire_all()
        assert session.query(Asset).filter_by(id=aid).first().label == "Updated"

    def test_delete_asset(self, kb, session):
        cid = _create_minimal_condo(kb, session)
        bid = _create_minimal_building(kb, session, cid)
        rid = _create_minimal_room(kb, session, bid)
        aid = _create_minimal_asset(kb, session, rid, "to_delete", "To Delete")
        kb.delete_asset(aid)
        session.expire_all()
        assert kb.get_asset(aid) is None

    def test_add_sensor(self, kb, session):
        cid = _create_minimal_condo(kb, session)
        bid = _create_minimal_building(kb, session, cid)
        rid = _create_minimal_room(kb, session, bid)
        aid = _create_minimal_asset(kb, session, rid)
        mf = [{"term": "bajo", "type": "trimf", "params": [0, 0, 5]}]
        s = kb.add_sensor(aid, "vibration", "Vibración", "mm/s", 0, 20, mf)
        assert s.name == "vibration"
        assert len(kb.get_sensors(aid)) == 1

    def test_update_sensor(self, kb, session):
        cid = _create_minimal_condo(kb, session)
        bid = _create_minimal_building(kb, session, cid)
        rid = _create_minimal_room(kb, session, bid)
        aid = _create_minimal_asset(kb, session, rid)
        mf = [{"term": "bajo", "type": "trimf", "params": [0, 0, 5]}]
        s = kb.add_sensor(aid, "vibration", "Vibración", "mm/s", 0, 20, mf)
        kb.update_sensor(s.id, label="Vibración Actualizada")
        session.expire_all()
        updated = session.query(SensorConfig).filter_by(id=s.id).first()
        assert updated.label == "Vibración Actualizada"

    def test_delete_sensor(self, kb, session):
        cid = _create_minimal_condo(kb, session)
        bid = _create_minimal_building(kb, session, cid)
        rid = _create_minimal_room(kb, session, bid)
        aid = _create_minimal_asset(kb, session, rid)
        mf = [{"term": "bajo", "type": "trimf", "params": [0, 0, 5]}]
        s = kb.add_sensor(aid, "vibration", "Vibración", "mm/s", 0, 20, mf)
        kb.delete_sensor(s.id)
        session.expire_all()
        assert len(kb.get_sensors(aid)) == 0

    def test_add_rule(self, kb, session):
        cid = _create_minimal_condo(kb, session)
        bid = _create_minimal_building(kb, session, cid)
        rid = _create_minimal_room(kb, session, bid)
        aid = _create_minimal_asset(kb, session, rid)
        rule = kb.add_rule(
            asset_id=aid, antecedents=[{"sensor": "vib", "term": "alto"}],
            consequent={"term": "high"}, name="R1", description="test",
            operator="and", weight=1.0
        )
        assert rule.name == "R1"
        assert len(kb.get_rules(aid)) == 1

    def test_get_rules(self, kb, session):
        cid = _create_minimal_condo(kb, session)
        bid = _create_minimal_building(kb, session, cid)
        rid = _create_minimal_room(kb, session, bid)
        aid = _create_minimal_asset(kb, session, rid)
        kb.add_rule(aid, [{"sensor": "vib", "term": "alto"}], {"term": "high"}, name="R1")
        kb.add_rule(aid, [{"sensor": "vib", "term": "bajo"}], {"term": "low"}, name="R2")
        assert len(kb.get_rules(aid)) == 2

    def test_update_rule(self, kb, session):
        cid = _create_minimal_condo(kb, session)
        bid = _create_minimal_building(kb, session, cid)
        rid = _create_minimal_room(kb, session, bid)
        aid = _create_minimal_asset(kb, session, rid)
        rule = kb.add_rule(aid, [{"sensor": "vib", "term": "alto"}], {"term": "high"}, name="R1", description="old")
        kb.update_rule(rule.id, description="new desc")
        session.expire_all()
        assert session.query(Rule).filter_by(id=rule.id).first().description == "new desc"

    def test_delete_rule(self, kb, session):
        cid = _create_minimal_condo(kb, session)
        bid = _create_minimal_building(kb, session, cid)
        rid = _create_minimal_room(kb, session, bid)
        aid = _create_minimal_asset(kb, session, rid)
        rule = kb.add_rule(aid, [{"sensor": "vib", "term": "alto"}], {"term": "high"}, name="R1")
        kb.delete_rule(rule.id)
        session.expire_all()
        assert len(kb.get_rules(aid)) == 0

    def test_get_user(self, kb, session):
        u = User(username="testuser", password_hash="hash123", role="technician")
        session.add(u)
        session.commit()
        fetched = kb.get_user("testuser")
        assert fetched is not None
        assert fetched.role == "technician"

    def test_get_user_not_found(self, kb):
        assert kb.get_user("nonexistent") is None

    def test_create_user(self, kb, session):
        u = kb.create_user("newuser", "pbkdf2_hash_here", "technician", condominium_ids=[])
        assert u is not None
        assert session.query(User).count() == 1

    def test_update_user(self, kb, session):
        u = User(username="u1", password_hash="h1", role="technician")
        session.add(u)
        session.commit()
        uid = session.query(User).filter_by(username="u1").first().id
        kb.update_user(uid, role="supervisor")
        session.expire_all()
        assert session.query(User).filter_by(id=uid).first().role == "supervisor"

    def test_delete_user(self, kb, session):
        u = User(username="u1", password_hash="h1", role="technician")
        session.add(u)
        session.commit()
        uid = session.query(User).filter_by(username="u1").first().id
        kb.delete_user(uid)
        session.expire_all()
        assert session.query(User).count() == 0

    def test_add_audit(self, kb, session):
        kb.add_audit("admin", "test_action", "test detail")
        assert session.query(AuditLog).count() == 1
        assert session.query(AuditLog).first().username == "admin"

    def test_get_full_hierarchy(self, kb, session):
        cid = _create_minimal_condo(kb, session, "C")
        bid = _create_minimal_building(kb, session, cid, "B")
        rid = _create_minimal_room(kb, session, bid, "R")
        kb.create_asset("a1", "A1", location_id=rid)
        hierarchy = kb.get_full_hierarchy()
        assert len(hierarchy) == 1
        assert hierarchy[0]["name"] == "C"
        assert hierarchy[0]["buildings"][0]["rooms"][0]["name"] == "R"

    def test_auto_generate_mf_peak_terms(self):
        from core.knowledge_base import auto_generate_mf
        terms = [{"name": "bajo", "peak": 5}, {"name": "alto", "peak": 15}]
        mf = auto_generate_mf(terms, 0, 20)
        assert len(mf) == 2
        assert mf[0]["term"] == "bajo"

    def test_auto_generate_mf_string_terms(self):
        from core.knowledge_base import auto_generate_mf
        mf = auto_generate_mf(["bajo", "medio", "alto"], 0, 100)
        assert len(mf) == 3
        assert mf[0]["term"] == "bajo"

    def test_reading_batches(self, kb, session):
        cid = _create_minimal_condo(kb, session)
        bid = _create_minimal_building(kb, session, cid)
        rid = _create_minimal_room(kb, session, bid)
        aid = _create_minimal_asset(kb, session, rid)
        from datetime import datetime, timezone
        for i in range(5):
            session.add(SensorReading(
                asset_id=aid, sensor_name="vib", value=float(i),
                score=50, timestamp=datetime.now(timezone.utc)
            ))
        session.commit()
        batches = kb.get_reading_batches(aid, limit=20)
        assert len(batches) > 0

    def test_add_event(self, kb, session):
        cid = _create_minimal_condo(kb, session)
        bid = _create_minimal_building(kb, session, cid)
        rid = _create_minimal_room(kb, session, bid)
        aid = _create_minimal_asset(kb, session, rid)
        kb.add_event(aid, "low", "high", 75.0, "test msg", "warning")
        assert session.query(Event).count() == 1

    def test_delete_condominium_cascade(self, kb, session):
        cid = _create_minimal_condo(kb, session, "C")
        bid = _create_minimal_building(kb, session, cid, "B")
        rid = _create_minimal_room(kb, session, bid, "R")
        kb.create_asset("a1", "A1", location_id=rid)
        kb.delete_condominium(cid)
        session.expire_all()
        assert session.query(Condominium).count() == 0
        assert session.query(Asset).count() == 0

    def test_delete_building_cascade(self, kb, session):
        cid = _create_minimal_condo(kb, session, "C")
        bid = _create_minimal_building(kb, session, cid, "B")
        rid = _create_minimal_room(kb, session, bid, "R")
        kb.create_asset("a1", "A1", location_id=rid)
        kb.delete_building(bid)
        session.expire_all()
        assert session.query(Building).count() == 0
        assert session.query(Asset).count() == 0

    def test_delete_room_cascade(self, kb, session):
        cid = _create_minimal_condo(kb, session, "C")
        bid = _create_minimal_building(kb, session, cid, "B")
        rid = _create_minimal_room(kb, session, bid, "R")
        kb.create_asset("a1", "A1", location_id=rid)
        kb.delete_room(rid)
        session.expire_all()
        assert session.query(MachineRoom).count() == 0
        assert session.query(Asset).count() == 0

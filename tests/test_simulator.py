import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from iiot_simulator.sensors import IIoTSimulator


@pytest.fixture
def sim():
    s = IIoTSimulator()
    s.add_instance("bomba_01", "water")
    s.add_instance("elevator_01", "elevator")
    s.add_instance("gen_01", "generator")
    return s


class TestIIoTSimulator:
    def test_init_has_base_types(self):
        """A new simulator auto-registers all SCENARIOS base types."""
        sim = IIoTSimulator()
        names = sim.get_all_asset_names()
        assert "water" in names
        assert "elevator" in names
        assert len(names) >= 8

    def test_add_instance(self, sim):
        assets = sim.get_all_asset_names()
        assert "bomba_01" in assets
        assert "elevator_01" in assets

    def test_add_instance_unknown_type_not_added(self):
        sim = IIoTSimulator()
        sim.add_instance("unknown_01", "nonexistent_type")
        assert "unknown_01" not in sim.get_all_asset_names()

    def test_step_increments_time(self, sim):
        t0 = sim.time
        sim.step(3)
        assert sim.time == t0 + 3
        sim.step(2)
        assert sim.time == t0 + 5

    def test_read_all_returns_dict(self, sim):
        data = sim.read_all()
        assert isinstance(data, dict)
        assert "bomba_01" in data

    def test_read_all_has_sensors(self, sim):
        data = sim.read_all()
        water_data = data["bomba_01"]
        assert "vibration" in water_data
        assert "temperature" in water_data

    def test_read_one(self, sim):
        data = sim.read_one("bomba_01")
        assert "vibration" in data

    def test_read_one_unknown(self, sim):
        data = sim.read_one("nonexistent")
        assert data == {}

    def test_inject_stores_external_data(self, sim):
        sim.inject_data("bomba_01", "vibration", 99.9)
        assert sim.has_external("bomba_01", "vibration")

    def test_inject_appears_in_read_one(self, sim):
        sim.inject_data("bomba_01", "vibration", 42.0)
        data = sim.read_one("bomba_01")
        assert data["vibration"] == 42.0

    def test_inject_appears_in_read_all(self, sim):
        sim.inject_data("bomba_01", "vibration", 77.0)
        all_data = sim.read_all()
        assert all_data["bomba_01"]["vibration"] == 77.0

    def test_has_external(self, sim):
        assert not sim.has_external("bomba_01", "vibration")
        sim.inject_data("bomba_01", "vibration", 50)
        assert sim.has_external("bomba_01", "vibration")

    def test_clear_external(self, sim):
        sim.inject_data("bomba_01", "vibration", 50)
        sim.clear_external("bomba_01")
        assert not sim.has_external("bomba_01", "vibration")

    def test_clear_all_external(self, sim):
        sim.inject_data("bomba_01", "vibration", 50)
        sim.clear_external()
        assert not sim.has_external("bomba_01", "vibration")

    def test_set_scenario_changes_readings(self, sim):
        sim.set_scenario("bomba_01", "cavitacion")
        data = sim.read_one("bomba_01")
        assert data.get("vibration", 0) > 5

    def test_set_scenario_auto_recover(self, sim):
        sim.set_scenario("bomba_01", "cavitacion", auto_recover=True)
        for _ in range(20):
            sim.step(1)
        data = sim.read_one("bomba_01")
        assert data.get("vibration", 99) < 5

    def test_get_scenarios_list(self, sim):
        scenarios = sim.get_scenarios_list("bomba_01")
        ids = [s["id"] for s in scenarios]
        assert "normal" in ids
        assert "cavitacion" in ids

    def test_get_scenarios_list_unknown_asset(self):
        sim = IIoTSimulator()
        assert sim.get_scenarios_list("unknown_asset") == []

    def test_noise_variability(self, sim):
        values = set()
        for _ in range(20):
            data = sim.read_one("bomba_01")
            values.add(round(data.get("vibration", 0), 1))
        assert len(values) > 1

    def test_actuator_modifies_readings(self, sim):
        sim.set_actuator("bomba_01", "relief_valve", 100)
        data = sim.read_one("bomba_01")
        assert "pressure" in data

    def test_generator_sensors(self, sim):
        data = sim.read_one("gen_01")
        for key in ["fuel_level", "rpm", "temperature", "voltage"]:
            assert key in data

    def test_sensor_values_in_range(self, sim):
        data = sim.read_one("bomba_01")
        assert 0 <= data.get("vibration", 0) <= 20
        assert 0 <= data.get("temperature", 0) <= 100

    def test_elevator_sensors(self, sim):
        data = sim.read_one("elevator_01")
        assert "speed_var" in data

    def test_set_scenario_on_base_type(self, sim):
        sim.set_scenario("water", "cavitacion")
        data = sim.read_one("water")
        assert data.get("vibration", 0) > 5

    def test_scenario_unknown_asset(self):
        sim = IIoTSimulator()
        sim.set_scenario("nonexistent", "normal")

    def test_inject_data_format(self, sim):
        sim.inject_data("bomba_01", "vibration", 123.0)
        ext = sim.external_data
        assert ext["bomba_01"]["vibration"] == 123.0

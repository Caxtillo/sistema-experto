import pytest
from unittest.mock import MagicMock, patch
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.inference_engine import InferenceEngine

@pytest.fixture
def engine():
    return InferenceEngine()

@pytest.fixture
def mock_asset():
    asset = MagicMock()
    asset.id = 999
    asset.name = "test_asset"
    asset.label = "Test Asset"
    asset.output_name = "output"
    asset.output_label = "Score"
    asset.output_min = 0
    asset.output_max = 100
    return asset

@pytest.fixture
def mock_sensors():
    sensors = []
    for s_data in [
        {"name": "sensor_a", "label": "Sensor A", "min_val": 0, "max_val": 10,
         "mf_config": [
             {"term": "low", "type": "trimf", "params": [0, 0, 4]},
             {"term": "medium", "type": "trimf", "params": [2, 5, 8]},
             {"term": "high", "type": "trimf", "params": [6, 10, 10]},
         ]},
        {"name": "sensor_b", "label": "Sensor B", "min_val": 0, "max_val": 100,
         "mf_config": [
             {"term": "cold", "type": "trimf", "params": [0, 0, 40]},
             {"term": "warm", "type": "trimf", "params": [30, 50, 70]},
             {"term": "hot", "type": "trimf", "params": [60, 100, 100]},
         ]},
    ]:
        s = MagicMock()
        s.name = s_data["name"]
        s.label = s_data["label"]
        s.min_val = s_data["min_val"]
        s.max_val = s_data["max_val"]
        s.mf_config = s_data["mf_config"]
        sensors.append(s)
    return sensors

@pytest.fixture
def mock_rules():
    rules = []
    for r_data in [
        {"name": "R1", "antecedents": [{"sensor": "sensor_a", "term": "high"}],
         "consequent": {"term": "high"}, "operator": "and", "enabled": True, "weight": 1.0,
         "description": "IF sensor_a high THEN high"},
        {"name": "R2", "antecedents": [{"sensor": "sensor_a", "term": "low"}, {"sensor": "sensor_b", "term": "cold"}],
         "consequent": {"term": "low"}, "operator": "and", "enabled": True, "weight": 1.0,
         "description": "IF sensor_a low AND sensor_b cold THEN low"},
    ]:
        r = MagicMock()
        for k, v in r_data.items():
            setattr(r, k, v)
        r.id = hash(r.name) % 1000
        rules.append(r)
    return rules

def test_inference_evaluates(engine, mock_asset, mock_sensors, mock_rules):
    score = engine.evaluate(mock_asset, mock_sensors, mock_rules, {"sensor_a": 8, "sensor_b": 80})
    assert isinstance(score, float)
    assert 0 <= score <= 100

def test_inference_low_values(engine, mock_asset, mock_sensors, mock_rules):
    score = engine.evaluate(mock_asset, mock_sensors, mock_rules, {"sensor_a": 1, "sensor_b": 10})
    assert score < 40

def test_inference_high_values(engine, mock_asset, mock_sensors, mock_rules):
    score = engine.evaluate(mock_asset, mock_sensors, mock_rules, {"sensor_a": 9, "sensor_b": 90})
    assert score > 50

def test_get_status(engine):
    assert engine.get_status(95, 100) == "critical"
    assert engine.get_status(75, 100) == "high"
    assert engine.get_status(45, 100) == "medium"
    assert engine.get_status(20, 100) == "low"
    assert engine.get_status(5, 100) == "none"

def test_get_active_rules(engine, mock_asset, mock_sensors, mock_rules):
    rules = engine.get_active_rules(mock_asset, mock_sensors, mock_rules, {"sensor_a": 9, "sensor_b": 90})
    assert len(rules) > 0

def test_get_active_rules_low(engine, mock_asset, mock_sensors, mock_rules):
    rules = engine.get_active_rules(mock_asset, mock_sensors, mock_rules, {"sensor_a": 1, "sensor_b": 10})
    assert len(rules) > 0
    assert any(r["fire_strength"] > 0 for r in rules)

def test_rules_sorted_by_fire_strength(engine, mock_asset, mock_sensors, mock_rules):
    rules = engine.get_active_rules(mock_asset, mock_sensors, mock_rules, {"sensor_a": 9, "sensor_b": 90})
    for i in range(len(rules) - 1):
        assert rules[i]["fire_strength"] >= rules[i + 1]["fire_strength"]

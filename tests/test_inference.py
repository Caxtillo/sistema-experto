import pytest
from unittest.mock import MagicMock, patch
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.inference_engine import InferenceEngine


@pytest.fixture
def engine():
    eng = InferenceEngine()
    eng._cache = {}
    return eng


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
        {"name": "R3", "antecedents": [{"sensor": "sensor_a", "term": "medium"}, {"sensor": "sensor_b", "term": "warm"}],
         "consequent": {"term": "medium"}, "operator": "and", "enabled": True, "weight": 1.0,
         "description": "IF sensor_a medium AND sensor_b warm THEN medium"},
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
    assert score < 30


def test_inference_high_values(engine, mock_asset, mock_sensors, mock_rules):
    score = engine.evaluate(mock_asset, mock_sensors, mock_rules, {"sensor_a": 9, "sensor_b": 90})
    assert score >= 60


def test_get_status(engine):
    assert engine.get_status(95, 100) == "high"
    assert engine.get_status(60, 100) == "high"
    assert engine.get_status(59, 100) == "medium"
    assert engine.get_status(45, 100) == "medium"
    assert engine.get_status(30, 100) == "medium"
    assert engine.get_status(29, 100) == "low"
    assert engine.get_status(0, 100) == "low"


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


def test_cache_persistence(engine, mock_asset, mock_sensors, mock_rules):
    engine.evaluate(mock_asset, mock_sensors, mock_rules, {"sensor_a": 5, "sensor_b": 50})
    assert mock_asset.id in engine._cache
    engine.evaluate(mock_asset, mock_sensors, mock_rules, {"sensor_a": 6, "sensor_b": 60})
    assert mock_asset.id in engine._cache


def test_cache_clear(engine, mock_asset, mock_sensors, mock_rules):
    engine.evaluate(mock_asset, mock_sensors, mock_rules, {"sensor_a": 5, "sensor_b": 50})
    engine._cache.clear()
    assert mock_asset.id not in engine._cache
    engine.evaluate(mock_asset, mock_sensors, mock_rules, {"sensor_a": 5, "sensor_b": 50})
    assert mock_asset.id in engine._cache


def test_empty_sensors(engine, mock_asset, mock_rules):
    score = engine.evaluate(mock_asset, [], mock_rules, {})
    assert score == 0


def test_empty_rules(engine, mock_asset, mock_sensors):
    score = engine.evaluate(mock_asset, mock_sensors, [], {"sensor_a": 5, "sensor_b": 50})
    assert score == 0


def test_disabled_rules(engine, mock_asset, mock_sensors, mock_rules):
    for r in mock_rules:
        r.enabled = False
    with pytest.raises((ValueError, KeyError)):
        engine.evaluate(mock_asset, mock_sensors, mock_rules, {"sensor_a": 9, "sensor_b": 90})


def test_missing_sensor_value(engine, mock_asset, mock_sensors, mock_rules):
    with pytest.raises((ValueError, KeyError)):
        engine.evaluate(mock_asset, mock_sensors, mock_rules, {})


def test_or_operator(engine, mock_asset, mock_sensors):
    rules = []
    for r_data in [
        {"name": "R1", "antecedents": [{"sensor": "sensor_a", "term": "high"}, {"sensor": "sensor_b", "term": "hot"}],
         "consequent": {"term": "high"}, "operator": "or", "enabled": True, "weight": 1.0,
         "description": "IF sensor_a high OR sensor_b hot THEN high"},
    ]:
        r = MagicMock()
        for k, v in r_data.items():
            setattr(r, k, v)
        r.id = hash(r.name) % 1000
        rules.append(r)

    score_high = engine.evaluate(mock_asset, mock_sensors, rules, {"sensor_a": 9, "sensor_b": 10})
    score_low = engine.evaluate(mock_asset, mock_sensors, rules, {"sensor_a": 1, "sensor_b": 10})
    assert 0 <= score_high <= 100
    assert 0 <= score_low <= 100


def test_trapmf_sensor(engine, mock_asset):
    s = MagicMock()
    s.name = "trap_sensor"
    s.label = "Trap Sensor"
    s.min_val = 0
    s.max_val = 100
    s.mf_config = [
        {"term": "low", "type": "trapmf", "params": [0, 0, 30, 50]},
        {"term": "high", "type": "trapmf", "params": [40, 70, 100, 100]},
    ]

    r = MagicMock()
    r.id = 1
    r.name = "R1"
    r.description = "test"
    r.operator = "and"
    r.antecedents = [{"sensor": "trap_sensor", "term": "high"}]
    r.consequent = {"term": "high"}
    r.action = None
    r.weight = 1.0
    r.enabled = True

    score = engine.evaluate(mock_asset, [s], [r], {"trap_sensor": 80})
    assert isinstance(score, float)
    assert score > 0


def test_gaussmf_sensor(engine, mock_asset):
    s = MagicMock()
    s.name = "gauss_sensor"
    s.label = "Gauss Sensor"
    s.min_val = 0
    s.max_val = 100
    s.mf_config = [
        {"term": "low", "type": "gaussmf", "params": [0, 15]},
        {"term": "high", "type": "gaussmf", "params": [85, 15]},
    ]

    r = MagicMock()
    r.id = 2
    r.name = "R1"
    r.description = "test"
    r.operator = "and"
    r.antecedents = [{"sensor": "gauss_sensor", "term": "high"}]
    r.consequent = {"term": "high"}
    r.action = None
    r.weight = 1.0
    r.enabled = True

    score = engine.evaluate(mock_asset, [s], [r], {"gauss_sensor": 90})
    assert isinstance(score, float)
    assert score > 0


def test_get_status_boundary(engine):
    assert engine.get_status(0, 100) == "low"
    assert engine.get_status(29, 100) == "low"
    assert engine.get_status(30, 100) == "medium"
    assert engine.get_status(59, 100) == "medium"
    assert engine.get_status(60, 100) == "high"
    assert engine.get_status(100, 100) == "high"

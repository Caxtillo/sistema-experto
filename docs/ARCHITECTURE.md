# System Architecture

## Overview

Condominium Expert is a fuzzy-logic-based expert system for critical asset management in condominium complexes. It monitors sensor data from pumps, generators, and elevators, evaluates asset health through fuzzy inference, and generates alerts and reports.

```
┌─────────────┐     ┌──────────────────┐     ┌──────────────┐
│  Web UI     │────▶│  FastAPI Server  │────▶│  SQLite DB   │
│  (HTML/JS)  │◀────│  (app.py/api.py) │◀────│  (SQLAlchemy) │
└─────────────┘     └──────────────────┘     └──────────────┘
                           │
                    ┌──────┴──────┐
                    │              │
              ┌──────────┐ ┌────────────┐
              │ Inference │ │  Simulator  │
              │  Engine   │ │  (IIoT)    │
              └──────────┘ └────────────┘
```

## Module Map

| Package | Module | Responsibility |
|---------|--------|----------------|
| `models/` | `models.py` | SQLAlchemy ORM: 10 tables (Condominium → Building → MachineRoom → Asset → SensorConfig/Actuator/Rule/Event/SensorReading) |
| `storage/` | `database.py` | SQLite session factory, `init_db()`, schema migrations |
| `core/` | `knowledge_base.py` | CRUD gateway — 50+ methods for all domain entities |
| `core/` | `inference_engine.py` | Mamdani fuzzy inference via scikit-fuzzy |
| `core/` | `explanation.py` | Human-readable diagnosis text from fuzzy results |
| `web/` | `app.py` | FastAPI entry point, page routes (dashboard, config, admin, reports) |
| `web/` | `api.py` | 58 REST endpoints (data, control, admin, reports, push) |
| `web/` | `push_notify.py` | VAPID push notification service |
| `web/` | `limits.py` | Shared rate limiter (slowapi) |
| `iiot_simulator/` | `sensors.py` | Signal generators for 3 asset types, scenario injection |
| `static/` | `*.html` / `*.js` | Frontend pages (dashboard, config, admin, login, reports) |
| `scripts/` | import scripts | CLI utilities |

## Key Design Decisions

### Session pattern (`expire_on_commit=False`)
All knowledge_base methods open a new session per call and close it immediately. This avoids stale-object issues but requires `expire_on_commit=False` so returned objects remain usable after the session commit.

### Fuzzy inference caching
`InferenceEngine` caches the built `ctrl.ControlSystem` per asset. The cache is cleared when sensor/rule configs change via the admin API.

### Sensor data flow
1. IIoTSimulator generates base values per asset + scenario
2. External API (`POST /api/sensor-data`) can override values
3. Inference engine evaluates → score + status
4. Events are created on status transitions (ROJO/AMARILLO/VERDE)
5. Push notifications are sent on ROJO or AMARILLO transitions

### Offline sync
A service worker caches POST requests to IndexedDB when offline and replays them when connectivity returns. Deduplication is handled by `sync_uuid`.

## Adding a New Asset Type

1. Add sensor/actuator/rule definitions to `knowledge_base.py` (`SENSOR_DEFS`, `ACTUATOR_DEFS`, `RULE_DEFS`)
2. Add the type slug to `TYPE_SLUG_TO_BASE` and `ASSET_TYPE_SLUGS`
3. Implement a scenario function in `iiot_simulator/sensors.py`
4. Register the type icon in `static/dashboard.js`

## API Documentation

All endpoints are self-documented via FastAPI OpenAPI at `/docs` when the server is running.

## Testing

Tests are in `tests/` using pytest. Current coverage: 81 tests across inference, knowledge_base, and simulator modules.

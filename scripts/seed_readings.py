"""Seed historical sensor readings for all assets.

Creates one batch of readings per day for the last 7 days (Jun 29 - Jul 5, 2026)
for every asset in the database. Each batch includes values for all sensors
of that asset with normal-range values and plausible health scores.
"""

import random
from datetime import datetime, timezone, timedelta
from storage.database import get_session, engine
from models.models import Asset, SensorConfig, SensorReading, Base


def _normal_value(s_min, s_max, terms):
    """Generate a normal-range value for a sensor based on its term labels."""
    peak = (s_min + s_max) / 2
    spread = (s_max - s_min) * 0.15
    return round(random.gauss(peak, spread), 1)


def _calc_score(sensor_values, sensor_configs):
    """Calculate a health score (0-100) from sensor values.

    Score is higher when values are near the center of normal terms,
    lower when values drift toward extremes.
    """
    score = 0
    count = 0
    for s_name, s_val in sensor_values.items():
        cfg = sensor_configs.get(s_name)
        if not cfg:
            continue
        mid = (cfg.min_val + cfg.max_val) / 2
        half = (cfg.max_val - cfg.min_val) / 2
        dist = abs(s_val - mid) / half
        s = max(0, 100 - dist * 100)
        score += s
        count += 1
    return round(score / count) if count else 50


def seed_readings():
    Base.metadata.create_all(bind=engine)
    session = get_session()

    assets = session.query(Asset).all()
    if not assets:
        print("No assets found. Run seed.py first.")
        session.close()
        return

    existing = session.query(SensorReading).first()
    if existing:
        print("Historical readings already exist, skipping.")
        session.close()
        return

    now = datetime(2026, 7, 5, 15, 0, 0, tzinfo=timezone.utc)
    total = 0

    for asset in assets:
        sensors = session.query(SensorConfig).filter_by(asset_id=asset.id).all()
        if not sensors:
            continue

        sensor_cfg = {s.name: s for s in sensors}
        sensor_defs = [(s.name, s.min_val, s.max_val, s.mf_config) for s in sensors]

        for i in range(5):
            base_time = now - timedelta(days=i * 2)
            ts = base_time.replace(hour=12, minute=random.randint(0, 59),
                                   second=0, microsecond=0)
            values = {}
            for s_name, s_min, s_max, mf in sensor_defs:
                val = _normal_value(s_min, s_max, mf)
                values[s_name] = val

            score = round(100 - _calc_score(values, sensor_cfg))

            for s_name, val in values.items():
                session.add(SensorReading(
                    asset_id=asset.id,
                    sensor_name=s_name,
                    value=val,
                    score=score,
                    timestamp=ts,
                ))
                total += 1

        if assets.index(asset) % 10 == 0:
            session.commit()

    session.commit()

    print(f"Seeded {total} historical readings for {len(assets)} assets "
          f"(7 days, 3 readings/day, all sensors per batch).")
    session.close()


if __name__ == "__main__":
    seed_readings()

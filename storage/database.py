"""SQLite database engine and session management.

Provides a scoped SQLAlchemy session factory for thread-safe access
to the SQLite database stored in data/condominium.db.
"""

from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session

DB_PATH = Path(__file__).parent.parent / "data" / "condominium.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

DATABASE_URL = f"sqlite:///{DB_PATH}"

engine = create_engine(DATABASE_URL, echo=False, connect_args={"check_same_thread": False})
SessionLocal = scoped_session(sessionmaker(bind=engine, expire_on_commit=False))


def init_db():
    """Create all tables if they don't exist.

    Safe to call on every startup — does NOT drop existing data.
    Applies lightweight migrations for schema additions.
    """
    from models.models import Base
    Base.metadata.create_all(bind=engine)
    _migrate_sync_uuid()


def _migrate_sync_uuid():
    """Add sync_uuid column + non-unique index if missing (migration for existing databases).
    Also drops old UNIQUE index if it exists (caused IntegrityError on retries)."""
    from sqlalchemy import inspect, text
    inspector = inspect(engine)
    columns = {c["name"] for c in inspector.get_columns("sensor_readings")}
    with engine.connect() as conn:
        if "sync_uuid" not in columns:
            conn.execute(text("ALTER TABLE sensor_readings ADD COLUMN sync_uuid VARCHAR(36)"))
        # Drop old UNIQUE index if present (bug: caused 500 on dedup retries)
        conn.execute(text("DROP INDEX IF EXISTS ix_sensor_readings_sync_uuid"))
        # Create non-unique index
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_sensor_readings_sync_uuid ON sensor_readings(sync_uuid)"))
        conn.commit()


def get_session():
    """Return a new scoped SQLAlchemy session."""
    return SessionLocal()

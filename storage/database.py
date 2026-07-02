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
SessionLocal = scoped_session(sessionmaker(bind=engine))


def init_db():
    """Drop all tables and recreate them.

    Warning: Destroys existing data. Used for development/demo purposes.
    In production, use database migrations instead.
    """
    from models.models import Base
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def get_session():
    """Return a new scoped SQLAlchemy session."""
    return SessionLocal()

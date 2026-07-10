"""SQLAlchemy ORM models for the Expert System.

Defines the database schema with hierarchical asset organization:
- Condominium → Building → MachineRoom → Asset
- SensorConfig, Actuator, Rule, Event, SensorReading
- User for role-based access control (many-to-many with condominiums)
"""

from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Float, Boolean, Text, JSON, DateTime, ForeignKey, Table
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


user_condominiums = Table(
    "user_condominiums", Base.metadata,
    Column("user_id", Integer, ForeignKey("users.id"), primary_key=True),
    Column("condominium_id", Integer, ForeignKey("condominiums.id"), primary_key=True),
)


class Condominium(Base):
    """A condominium complex being managed."""
    __tablename__ = "condominiums"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(200), nullable=False)
    slug = Column(String(50), unique=True, nullable=True)
    address = Column(Text, default="")
    lat = Column(Float, nullable=True)
    lng = Column(Float, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    buildings = relationship("Building", back_populates="condominium", cascade="all, delete-orphan")
    users = relationship("User", secondary=user_condominiums, back_populates="condominiums")


class Building(Base):
    """A building within a condominium."""
    __tablename__ = "buildings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    condominium_id = Column(Integer, ForeignKey("condominiums.id"), nullable=False)
    name = Column(String(200), nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    condominium = relationship("Condominium", back_populates="buildings")
    rooms = relationship("MachineRoom", back_populates="building", cascade="all, delete-orphan")


class MachineRoom(Base):
    """A machine room within a building (e.g., basement, rooftop)."""
    __tablename__ = "machine_rooms"

    id = Column(Integer, primary_key=True, autoincrement=True)
    building_id = Column(Integer, ForeignKey("buildings.id"), nullable=False)
    name = Column(String(200), nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    building = relationship("Building", back_populates="rooms")
    assets = relationship("Asset", back_populates="location", cascade="all, delete-orphan")


class Asset(Base):
    """A critical condominium asset being monitored and controlled.

    Each asset has sensors, actuators, rules, and a fuzzy output variable
    that represents its health/risk score. Assets are organized hierarchically
    under a MachineRoom.
    """
    __tablename__ = "assets"

    id = Column(Integer, primary_key=True, autoincrement=True)
    location_id = Column(Integer, ForeignKey("machine_rooms.id"), nullable=True)
    name = Column(String(100), unique=True, nullable=False)
    label = Column(String(100), nullable=False)
    description = Column(Text, default="")
    icon = Column(String(50), default="gear")
    output_name = Column(String(50), default="output")
    output_label = Column(String(100), default="Score")
    output_min = Column(Float, default=0)
    output_max = Column(Float, default=100)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    location = relationship("MachineRoom", back_populates="assets")
    sensors = relationship("SensorConfig", back_populates="asset", cascade="all, delete-orphan")
    actuators = relationship("Actuator", back_populates="asset", cascade="all, delete-orphan")
    rules = relationship("Rule", back_populates="asset", cascade="all, delete-orphan")
    events = relationship("Event", back_populates="asset", cascade="all, delete-orphan")


class SensorConfig(Base):
    """Configuration for a sensor attached to an asset.

    Stores the sensor range, unit, type (simulated/external/phone),
    and the fuzzy membership function configuration for each linguistic term.
    """
    __tablename__ = "sensor_configs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    asset_id = Column(Integer, ForeignKey("assets.id"), nullable=False)
    name = Column(String(100), nullable=False)
    label = Column(String(100), nullable=False)
    unit = Column(String(20), default="")
    min_val = Column(Float, default=0)
    max_val = Column(Float, default=100)
    mf_config = Column(JSON, nullable=False)
    sensor_type = Column(String(20), default="simulated")

    asset = relationship("Asset", back_populates="sensors")


class Actuator(Base):
    """A controllable actuator for an asset (e.g., valve, brake, breaker).

    Tracks the current command value, on/off state, and whether it is
    in automatic mode (controlled by the expert system) or manual mode.
    """
    __tablename__ = "actuators"

    id = Column(Integer, primary_key=True, autoincrement=True)
    asset_id = Column(Integer, ForeignKey("assets.id"), nullable=False)
    name = Column(String(100), nullable=False)
    label = Column(String(100), nullable=False)
    unit = Column(String(20), default="")
    min_val = Column(Float, default=0)
    max_val = Column(Float, default=100)
    command = Column(Float, default=0)
    state = Column(Boolean, default=False)
    auto = Column(Boolean, default=True)

    asset = relationship("Asset", back_populates="actuators")


class Rule(Base):
    """A fuzzy rule with antecedents, consequent, and optional actuator action.

    Example: IF vibration IS high AND temperature IS hot THEN maintenance IS critical
    with action={"actuator": "speed_controller", "value": 10}
    """
    __tablename__ = "rules"

    id = Column(Integer, primary_key=True, autoincrement=True)
    asset_id = Column(Integer, ForeignKey("assets.id"), nullable=False)
    name = Column(String(200), default="")
    description = Column(Text, default="")
    operator = Column(String(10), default="and")
    antecedents = Column(JSON, nullable=False)
    consequent = Column(JSON, nullable=False)
    action = Column(JSON, nullable=True)
    weight = Column(Float, default=1.0)
    enabled = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    asset = relationship("Asset", back_populates="rules")


class Event(Base):
    """A persisted status transition event for an asset.

    Generated whenever an asset's status changes (e.g., 'low' -> 'high').
    """
    __tablename__ = "events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    asset_id = Column(Integer, ForeignKey("assets.id"), nullable=False)
    old_status = Column(String(20), default="")
    new_status = Column(String(20), nullable=False)
    score = Column(Float, default=0)
    message = Column(String(500), default="")
    event_type = Column(String(20), default="info")
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    asset = relationship("Asset", back_populates="events")


class SensorReading(Base):
    __tablename__ = "sensor_readings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    asset_id = Column(Integer, ForeignKey("assets.id"), nullable=False)
    sensor_name = Column(String(100), nullable=False)
    value = Column(Float, nullable=False)
    score = Column(Float, default=0)
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    sync_uuid = Column(String(36), nullable=True, index=True)


class User(Base):
    """System user with role-based access control.

    Can be assigned to multiple condominiums via the user_condominiums association table.
    """
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(100), unique=True, nullable=False)
    password_hash = Column(String(200), nullable=False)
    role = Column(String(20), nullable=False, default="technician")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    condominiums = relationship("Condominium", secondary=user_condominiums, back_populates="users")
    audits = relationship("AuditLog", back_populates="user", cascade="all, delete-orphan")


class AuditLog(Base):
    """Audit log for tracking user actions in the system."""
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(100), nullable=False)
    action = Column(String(200), nullable=False)
    detail = Column(Text, default="")
    asset_id = Column(Integer, nullable=True)
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    user = relationship("User", back_populates="audits")

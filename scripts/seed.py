"""Database seeding script for the Expert System.

Creates the initial schema and populates it with hierarchical data:
- 2 condominiums with buildings and machine rooms
- 8 assets distributed across rooms
- Each with sensors, actuators, and fuzzy rules
- 3 user accounts for role-based access
"""

import hashlib
from storage.database import init_db, get_session
from models.models import Asset, SensorConfig, Actuator, Rule
from models.models import Condominium, Building, MachineRoom, User


def _hash(pw):
    return hashlib.sha256(pw.encode()).hexdigest()


def seed():
    """Drop and recreate all tables, then seed with initial data.

    Creates the full hierarchy: Condominium -> Building -> MachineRoom -> Asset.
    Also creates 3 users with role-based access.
    """
    init_db()
    session = get_session()

    if session.query(Asset).count() > 0:
        print("Database already seeded.")
        session.close()
        return

    # ---- Hierarchy: 2 condominiums, 3 buildings, 4 machine rooms ----
    c1 = Condominium(name="Los Olivos", address="Av. Principal 123",
                     lat=-12.046, lng=-77.043)
    c2 = Condominium(name="Vista Alegre", address="Jr. Las Flores 456",
                     lat=-12.120, lng=-77.030)
    session.add_all([c1, c2])
    session.flush()

    b1 = Building(name="Edificio Principal", condominium_id=c1.id)
    b2 = Building(name="Edificio Secundario", condominium_id=c1.id)
    b3 = Building(name="Torre A", condominium_id=c2.id)
    session.add_all([b1, b2, b3])
    session.flush()

    rm_sotano = MachineRoom(name="Sótano", building_id=b1.id)
    rm_electrico = MachineRoom(name="Cuarto Eléctrico", building_id=b1.id)
    rm_azotea = MachineRoom(name="Azotea", building_id=b2.id)
    rm_pbaja = MachineRoom(name="Planta Baja", building_id=b3.id)
    session.add_all([rm_sotano, rm_electrico, rm_azotea, rm_pbaja])
    session.flush()

    # ---- Users ----
    admin = User(username="admin", password_hash=_hash("admin123"),
                 role="admin", condominium_id=None)
    supervisor = User(username="supervisor", password_hash=_hash("super123"),
                      role="supervisor", condominium_id=None)
    tecnico = User(username="tecnico", password_hash=_hash("tec123"),
                   role="technician", condominium_id=c1.id)
    session.add_all([admin, supervisor, tecnico])
    session.flush()

    # ---- ELEVATOR (Sótano) ----
    ascensor = Asset(name="elevator", label="Ascensor",
                     description="Sistema de ascensor del condominio",
                     icon="arrow-up", output_name="maintenance", output_label="Prioridad de Mantenimiento",
                     output_min=0, output_max=100, location_id=rm_sotano.id)
    session.add(ascensor)
    session.flush()

    session.add_all([
        SensorConfig(asset_id=ascensor.id, name="vibration", label="Vibración", unit="mm/s",
                     min_val=0, max_val=10,
                     mf_config=[
                         {"term": "low", "type": "trimf", "params": [0, 0, 4]},
                         {"term": "medium", "type": "trimf", "params": [2, 5, 8]},
                         {"term": "high", "type": "trimf", "params": [6, 10, 10]},
                     ]),
        SensorConfig(asset_id=ascensor.id, name="temperature", label="Temperatura", unit="°C",
                     min_val=0, max_val=100,
                     mf_config=[
                         {"term": "normal", "type": "trimf", "params": [0, 30, 60]},
                         {"term": "warm", "type": "trimf", "params": [40, 60, 80]},
                         {"term": "hot", "type": "trimf", "params": [65, 100, 100]},
                     ]),
        SensorConfig(asset_id=ascensor.id, name="speed_var", label="Var. Velocidad", unit="%",
                     min_val=0, max_val=10,
                     mf_config=[
                         {"term": "stable", "type": "trimf", "params": [0, 0, 4]},
                         {"term": "moderate", "type": "trimf", "params": [2, 5, 8]},
                         {"term": "erratic", "type": "trimf", "params": [6, 10, 10]},
                     ]),
    ])
    session.flush()

    session.add_all([
        Actuator(asset_id=ascensor.id, name="speed_controller", label="Control Velocidad", unit="%", min_val=0, max_val=100, command=100, state=True),
        Actuator(asset_id=ascensor.id, name="emergency_brake", label="Freno Emergencia", unit="", min_val=0, max_val=1, command=0, state=False),
        Actuator(asset_id=ascensor.id, name="door_lock", label="Bloqueo Puertas", unit="", min_val=0, max_val=1, command=0, state=False),
    ])
    session.flush()

    session.add_all([
        Rule(asset_id=ascensor.id, name="R1",
             description="SI vibración ALTA Y temperatura CALIENTE ENTONCES critical",
             operator="and",
             antecedents=[{"sensor": "vibration", "term": "high"}, {"sensor": "temperature", "term": "hot"}],
             consequent={"sensor": "maintenance", "term": "critical"},
             action={"actuator": "speed_controller", "value": 10}, weight=1.0),
        Rule(asset_id=ascensor.id, name="R2",
             description="SI vibración ALTA O velocidad ERRÁTICA ENTONCES high → reducir velocidad",
             operator="or",
             antecedents=[{"sensor": "vibration", "term": "high"}, {"sensor": "speed_var", "term": "erratic"}],
             consequent={"sensor": "maintenance", "term": "high"},
             action={"actuator": "speed_controller", "value": 40}, weight=1.0),
        Rule(asset_id=ascensor.id, name="R3",
             description="SI vibración MEDIA Y temperatura CÁLIDA ENTONCES medium → reducir velocidad",
             operator="and",
             antecedents=[{"sensor": "vibration", "term": "medium"}, {"sensor": "temperature", "term": "warm"}],
             consequent={"sensor": "maintenance", "term": "medium"},
             action={"actuator": "speed_controller", "value": 70}, weight=1.0),
        Rule(asset_id=ascensor.id, name="R4",
             description="SI vibración BAJA Y temperatura NORMAL Y velocidad ESTABLE ENTONCES low → velocidad normal",
             operator="and",
             antecedents=[{"sensor": "vibration", "term": "low"}, {"sensor": "temperature", "term": "normal"}, {"sensor": "speed_var", "term": "stable"}],
             consequent={"sensor": "maintenance", "term": "low"},
             action={"actuator": "speed_controller", "value": 100}, weight=1.0),
        Rule(asset_id=ascensor.id, name="R5",
             description="SI velocidad MODERADA ENTONCES medium → ajustar velocidad",
             operator="and",
             antecedents=[{"sensor": "speed_var", "term": "moderate"}],
             consequent={"sensor": "maintenance", "term": "medium"},
             action={"actuator": "speed_controller", "value": 60}, weight=1.0),
    ])

    # ---- ELECTRICAL ----
    electrico = Asset(name="electrical", label="Sistema Eléctrico",
                      description="Sistema eléctrico del condominio (transformador, tableros)",
                      icon="zap", output_name="risk", output_label="Nivel de Riesgo",
                      output_min=0, output_max=100, location_id=rm_electrico.id)
    session.add(electrico)
    session.flush()

    session.add_all([
        SensorConfig(asset_id=electrico.id, name="voltage", label="Voltaje", unit="V",
                     min_val=100, max_val=260,
                     mf_config=[
                         {"term": "low", "type": "trimf", "params": [100, 100, 180]},
                         {"term": "normal", "type": "trimf", "params": [170, 220, 240]},
                         {"term": "high", "type": "trimf", "params": [230, 260, 260]},
                     ]),
        SensorConfig(asset_id=electrico.id, name="current", label="Corriente", unit="A",
                     min_val=0, max_val=100,
                     mf_config=[
                         {"term": "low", "type": "trimf", "params": [0, 0, 40]},
                         {"term": "medium", "type": "trimf", "params": [20, 50, 80]},
                         {"term": "high", "type": "trimf", "params": [60, 100, 100]},
                     ]),
        SensorConfig(asset_id=electrico.id, name="temp_rise", label="Temp. Rise", unit="°C",
                     min_val=0, max_val=80,
                     mf_config=[
                         {"term": "low", "type": "trimf", "params": [0, 0, 25]},
                         {"term": "medium", "type": "trimf", "params": [15, 40, 60]},
                         {"term": "high", "type": "trimf", "params": [50, 80, 80]},
                     ]),
    ])
    session.flush()

    session.add_all([
        Actuator(asset_id=electrico.id, name="load_shedder", label="Desconexión Cargas", unit="", min_val=0, max_val=1, command=0, state=False),
        Actuator(asset_id=electrico.id, name="capacitor_bank", label="Banco Capacitores", unit="", min_val=0, max_val=1, command=0, state=False),
        Actuator(asset_id=electrico.id, name="main_breaker", label="Breaker Principal", unit="", min_val=0, max_val=1, command=1, state=True),
    ])
    session.flush()

    session.add_all([
        Rule(asset_id=electrico.id, name="R1",
             description="SI voltaje ALTO Y corriente ALTA Y temperatura ALTA ENTONCES critical → cortar breaker",
             operator="and",
             antecedents=[{"sensor": "voltage", "term": "high"}, {"sensor": "current", "term": "high"}, {"sensor": "temp_rise", "term": "high"}],
             consequent={"sensor": "risk", "term": "critical"},
             action={"actuator": "main_breaker", "value": 0}, weight=1.0),
        Rule(asset_id=electrico.id, name="R2",
             description="SI voltaje ALTO O corriente ALTA ENTONCES high → desconectar cargas",
             operator="or",
             antecedents=[{"sensor": "voltage", "term": "high"}, {"sensor": "current", "term": "high"}],
             consequent={"sensor": "risk", "term": "high"},
             action={"actuator": "load_shedder", "value": 1}, weight=1.0),
        Rule(asset_id=electrico.id, name="R3",
             description="SI corriente MEDIA Y temperatura MEDIA ENTONCES medium → activar banco capacitores",
             operator="and",
             antecedents=[{"sensor": "current", "term": "medium"}, {"sensor": "temp_rise", "term": "medium"}],
             consequent={"sensor": "risk", "term": "medium"},
             action={"actuator": "capacitor_bank", "value": 1}, weight=1.0),
        Rule(asset_id=electrico.id, name="R4",
             description="SI voltaje NORMAL Y corriente BAJA Y temperatura BAJA ENTONCES low → normalizar",
             operator="and",
             antecedents=[{"sensor": "voltage", "term": "normal"}, {"sensor": "current", "term": "low"}, {"sensor": "temp_rise", "term": "low"}],
             consequent={"sensor": "risk", "term": "low"},
             action={"actuator": "load_shedder", "value": 0}, weight=1.0),
        Rule(asset_id=electrico.id, name="R5",
             description="SI voltaje BAJO Y corriente ALTA ENTONCES high → activar banco capacitores",
             operator="and",
             antecedents=[{"sensor": "voltage", "term": "low"}, {"sensor": "current", "term": "high"}],
             consequent={"sensor": "risk", "term": "high"},
             action={"actuator": "capacitor_bank", "value": 1}, weight=1.0),
        Rule(asset_id=electrico.id, name="R6",
             description="SI temperatura ALTA ENTONCES high → desconectar cargas",
             operator="and",
             antecedents=[{"sensor": "temp_rise", "term": "high"}],
             consequent={"sensor": "risk", "term": "high"},
             action={"actuator": "load_shedder", "value": 1}, weight=1.0),
    ])

    # ---- WATER ----
    agua = Asset(name="water", label="Sistema de Agua",
                  description="Sistema de bombeo y tanques de agua del condominio",
                  icon="droplets", output_name="urgency", output_label="Urgencia",
                  output_min=0, output_max=100, location_id=rm_sotano.id)
    session.add(agua)
    session.flush()

    session.add_all([
        SensorConfig(asset_id=agua.id, name="flow", label="Caudal", unit="L/min",
                     min_val=0, max_val=100,
                     mf_config=[
                         {"term": "very_low", "type": "trimf", "params": [0, 0, 20]},
                         {"term": "low", "type": "trimf", "params": [10, 30, 50]},
                         {"term": "normal", "type": "trimf", "params": [40, 60, 80]},
                         {"term": "high", "type": "trimf", "params": [70, 100, 100]},
                     ]),
        SensorConfig(asset_id=agua.id, name="pressure", label="Presión", unit="PSI",
                     min_val=0, max_val=100,
                     mf_config=[
                         {"term": "very_low", "type": "trimf", "params": [0, 0, 20]},
                         {"term": "low", "type": "trimf", "params": [10, 30, 50]},
                         {"term": "normal", "type": "trimf", "params": [40, 65, 85]},
                         {"term": "high", "type": "trimf", "params": [75, 100, 100]},
                     ]),
        SensorConfig(asset_id=agua.id, name="tank_level", label="Nivel Tanque", unit="%",
                     min_val=0, max_val=100,
                     mf_config=[
                         {"term": "empty", "type": "trimf", "params": [0, 0, 25]},
                         {"term": "low", "type": "trimf", "params": [15, 35, 55]},
                         {"term": "medium", "type": "trimf", "params": [40, 60, 80]},
                         {"term": "full", "type": "trimf", "params": [70, 100, 100]},
                     ]),
    ])
    session.flush()

    session.add_all([
        Actuator(asset_id=agua.id, name="relief_valve", label="Válvula Alivio", unit="%", min_val=0, max_val=100, command=0, state=False),
        Actuator(asset_id=agua.id, name="booster_pump", label="Bomba Presurizadora", unit="", min_val=0, max_val=1, command=0, state=False),
        Actuator(asset_id=agua.id, name="inlet_valve", label="Válvula Entrada", unit="", min_val=0, max_val=1, command=1, state=True),
    ])
    session.flush()

    session.add_all([
        Rule(asset_id=agua.id, name="R1",
             description="SI tanque VACÍO Y caudal MUY BAJO ENTONCES critical → abrir válvula entrada",
             operator="and",
             antecedents=[{"sensor": "tank_level", "term": "empty"}, {"sensor": "flow", "term": "very_low"}],
             consequent={"sensor": "urgency", "term": "critical"},
             action={"actuator": "inlet_valve", "value": 1}, weight=1.0),
        Rule(asset_id=agua.id, name="R2",
             description="SI presión MUY BAJA Y caudal MUY BAJO ENTONCES high → activar bomba",
             operator="and",
             antecedents=[{"sensor": "pressure", "term": "very_low"}, {"sensor": "flow", "term": "very_low"}],
             consequent={"sensor": "urgency", "term": "high"},
             action={"actuator": "booster_pump", "value": 1}, weight=1.0),
        Rule(asset_id=agua.id, name="R3",
             description="SI tanque BAJO Y presión BAJA ENTONCES medium → abrir válvula entrada",
             operator="and",
             antecedents=[{"sensor": "tank_level", "term": "low"}, {"sensor": "pressure", "term": "low"}],
             consequent={"sensor": "urgency", "term": "medium"},
             action={"actuator": "inlet_valve", "value": 1}, weight=1.0),
        Rule(asset_id=agua.id, name="R4",
             description="SI tanque LLENO Y presión NORMAL Y caudal NORMAL ENTONCES none → normalizar",
             operator="and",
             antecedents=[{"sensor": "tank_level", "term": "full"}, {"sensor": "pressure", "term": "normal"}, {"sensor": "flow", "term": "normal"}],
             consequent={"sensor": "urgency", "term": "none"},
             action={"actuator": "booster_pump", "value": 0}, weight=1.0),
        Rule(asset_id=agua.id, name="R5",
             description="SI tanque VACÍO ENTONCES high → abrir válvula entrada",
             operator="and",
             antecedents=[{"sensor": "tank_level", "term": "empty"}],
             consequent={"sensor": "urgency", "term": "high"},
             action={"actuator": "inlet_valve", "value": 1}, weight=1.0),
        Rule(asset_id=agua.id, name="R6",
             description="SI tanque MEDIO Y presión NORMAL ENTONCES low → cerrar válvula si estaba abierta",
             operator="and",
             antecedents=[{"sensor": "tank_level", "term": "medium"}, {"sensor": "pressure", "term": "normal"}],
             consequent={"sensor": "urgency", "term": "low"},
             action={"actuator": "inlet_valve", "value": 0}, weight=1.0),
    ])

    _seed_hvac(session, rm_azotea.id)
    _seed_fire(session, rm_azotea.id)
    _seed_generator(session, rm_pbaja.id)
    _seed_lighting(session, rm_electrico.id)
    _seed_access(session, rm_pbaja.id)

    session.commit()
    print("Database seeded successfully!")
    print(f"  - {session.query(Condominium).count()} condominiums")
    print(f"  - {session.query(Building).count()} buildings")
    print(f"  - {session.query(MachineRoom).count()} machine rooms")
    print(f"  - {session.query(Asset).count()} assets")
    print(f"  - {session.query(SensorConfig).count()} sensors")
    print(f"  - {session.query(Actuator).count()} actuators")
    print(f"  - {session.query(Rule).count()} rules")
    print(f"  - {session.query(User).count()} users")
    session.close()


def _seed_hvac(session, location_id):
    """HVAC system with temp, pressure, rpm sensors and 3 actuators."""
    hvac = Asset(name="hvac", label="HVAC",
                 description="Sistema de climatización y ventilación",
                 icon="thermometer", output_name="priority", output_label="Prioridad HVAC",
                 output_min=0, output_max=100, location_id=location_id)
    session.add(hvac)
    session.flush()

    session.add_all([
        SensorConfig(asset_id=hvac.id, name="temp_in", label="Temp. Interior", unit="°C",
                     min_val=10, max_val=40,
                     mf_config=[
                         {"term": "cool", "type": "trimf", "params": [10, 18, 24]},
                         {"term": "normal", "type": "trimf", "params": [20, 25, 30]},
                         {"term": "hot", "type": "trimf", "params": [28, 35, 40]},
                     ]),
        SensorConfig(asset_id=hvac.id, name="temp_out", label="Temp. Salida", unit="°C",
                     min_val=5, max_val=35,
                     mf_config=[
                         {"term": "cold", "type": "trimf", "params": [5, 10, 16]},
                         {"term": "normal", "type": "trimf", "params": [12, 18, 24]},
                         {"term": "warm", "type": "trimf", "params": [20, 28, 35]},
                     ]),
        SensorConfig(asset_id=hvac.id, name="pressure", label="Presión", unit="PSI",
                     min_val=0, max_val=250,
                     mf_config=[
                         {"term": "low", "type": "trimf", "params": [0, 50, 100]},
                         {"term": "normal", "type": "trimf", "params": [80, 130, 170]},
                         {"term": "high", "type": "trimf", "params": [150, 200, 250]},
                     ]),
        SensorConfig(asset_id=hvac.id, name="rpm", label="RPM Ventilador", unit="RPM",
                     min_val=0, max_val=3000,
                     mf_config=[
                         {"term": "slow", "type": "trimf", "params": [0, 500, 1200]},
                         {"term": "normal", "type": "trimf", "params": [1000, 1800, 2400]},
                         {"term": "fast", "type": "trimf", "params": [2000, 2600, 3000]},
                     ]),
    ])
    session.flush()

    session.add_all([
        Actuator(asset_id=hvac.id, name="compressor", label="Compresor", unit="", min_val=0, max_val=1, command=1, state=True),
        Actuator(asset_id=hvac.id, name="fan_speed", label="Velocidad Ventilador", unit="%", min_val=0, max_val=100, command=100, state=True),
        Actuator(asset_id=hvac.id, name="damper", label="Compuerta Aire", unit="%", min_val=0, max_val=100, command=100, state=True),
    ])
    session.flush()

    session.add_all([
        Rule(asset_id=hvac.id, name="R1",
             description="SI temp_salida CALIENTE Y presión ALTA ENTONCES critical → apagar compresor",
             operator="and",
             antecedents=[{"sensor": "temp_out", "term": "warm"}, {"sensor": "pressure", "term": "high"}],
             consequent={"sensor": "priority", "term": "critical"},
             action={"actuator": "compressor", "value": 0}, weight=1.0),
        Rule(asset_id=hvac.id, name="R2",
             description="SI temp_interior CALIENTE O rpm LENTA ENTONCES high → ventilador máximo",
             operator="or",
             antecedents=[{"sensor": "temp_in", "term": "hot"}, {"sensor": "rpm", "term": "slow"}],
             consequent={"sensor": "priority", "term": "high"},
             action={"actuator": "fan_speed", "value": 100}, weight=1.0),
        Rule(asset_id=hvac.id, name="R3",
             description="SI presión BAJA ENTONCES high → cerrar compuerta",
             operator="and",
             antecedents=[{"sensor": "pressure", "term": "low"}],
             consequent={"sensor": "priority", "term": "high"},
             action={"actuator": "damper", "value": 50}, weight=1.0),
        Rule(asset_id=hvac.id, name="R4",
             description="SI temp_interior NORMAL Y presión NORMAL ENTONCES low → velocidad normal",
             operator="and",
             antecedents=[{"sensor": "temp_in", "term": "normal"}, {"sensor": "pressure", "term": "normal"}],
             consequent={"sensor": "priority", "term": "low"},
             action={"actuator": "fan_speed", "value": 70}, weight=1.0),
        Rule(asset_id=hvac.id, name="R5",
             description="SI temp_salida FRÍA Y rpm NORMAL ENTONCES none",
             operator="and",
             antecedents=[{"sensor": "temp_out", "term": "cold"}, {"sensor": "rpm", "term": "normal"}],
             consequent={"sensor": "priority", "term": "none"},
             action={"actuator": "compressor", "value": 1}, weight=1.0),
    ])


def _seed_fire(session, location_id):
    """Fire suppression system with smoke, temp, pressure sensors."""
    fire = Asset(name="fire", label="Sistema Contra Incendios",
                  description="Sistema de detección y extinción de incendios",
                  icon="flame", output_name="risk", output_label="Riesgo Incendio",
                  output_min=0, output_max=100, location_id=location_id)
    session.add(fire)
    session.flush()

    session.add_all([
        SensorConfig(asset_id=fire.id, name="smoke_level", label="Nivel Humo", unit="%",
                     min_val=0, max_val=100,
                     mf_config=[
                         {"term": "clear", "type": "trimf", "params": [0, 0, 20]},
                         {"term": "detected", "type": "trimf", "params": [15, 40, 65]},
                         {"term": "heavy", "type": "trimf", "params": [55, 80, 100]},
                     ]),
        SensorConfig(asset_id=fire.id, name="temp_rise", label="Temp. Ambiente", unit="°C",
                     min_val=0, max_val=100,
                     mf_config=[
                         {"term": "normal", "type": "trimf", "params": [0, 25, 40]},
                         {"term": "elevated", "type": "trimf", "params": [30, 50, 70]},
                         {"term": "critical", "type": "trimf", "params": [60, 85, 100]},
                     ]),
        SensorConfig(asset_id=fire.id, name="water_pressure", label="Presión Agua", unit="PSI",
                     min_val=0, max_val=200,
                     mf_config=[
                         {"term": "low", "type": "trimf", "params": [0, 0, 60]},
                         {"term": "normal", "type": "trimf", "params": [50, 90, 130]},
                         {"term": "high", "type": "trimf", "params": [110, 160, 200]},
                     ]),
    ])
    session.flush()

    session.add_all([
        Actuator(asset_id=fire.id, name="sprinkler_valve", label="Válvula Rociadores", unit="", min_val=0, max_val=1, command=0, state=False),
        Actuator(asset_id=fire.id, name="alarm", label="Alarma Incendio", unit="", min_val=0, max_val=1, command=0, state=False),
        Actuator(asset_id=fire.id, name="fire_pump", label="Bomba Incendio", unit="", min_val=0, max_val=1, command=0, state=False),
    ])
    session.flush()

    session.add_all([
        Rule(asset_id=fire.id, name="R1",
             description="SI humo ALTO Y temp CRÍTICA ENTONCES critical → activar rociadores y alarma",
             operator="and",
             antecedents=[{"sensor": "smoke_level", "term": "heavy"}, {"sensor": "temp_rise", "term": "critical"}],
             consequent={"sensor": "risk", "term": "critical"},
             action={"actuator": "sprinkler_valve", "value": 1}, weight=1.0),
        Rule(asset_id=fire.id, name="R2",
             description="SI humo DETECTADO ENTONCES high → activar alarma",
             operator="and",
             antecedents=[{"sensor": "smoke_level", "term": "detected"}],
             consequent={"sensor": "risk", "term": "high"},
             action={"actuator": "alarm", "value": 1}, weight=1.0),
        Rule(asset_id=fire.id, name="R3",
             description="SI temp ELEVADA Y presión BAJA ENTONCES high → activar bomba",
             operator="and",
             antecedents=[{"sensor": "temp_rise", "term": "elevated"}, {"sensor": "water_pressure", "term": "low"}],
             consequent={"sensor": "risk", "term": "high"},
             action={"actuator": "fire_pump", "value": 1}, weight=1.0),
        Rule(asset_id=fire.id, name="R4",
             description="SI humo DETECTADO Y temp ELEVADA ENTONCES critical → rociadores + alarma + bomba",
             operator="and",
             antecedents=[{"sensor": "smoke_level", "term": "detected"}, {"sensor": "temp_rise", "term": "elevated"}],
             consequent={"sensor": "risk", "term": "critical"},
             action={"actuator": "sprinkler_valve", "value": 1}, weight=1.0),
        Rule(asset_id=fire.id, name="R5",
             description="SI ambiente NORMAL Y humo NORMAL ENTONCES low → resetear todo",
             operator="and",
             antecedents=[{"sensor": "temp_rise", "term": "normal"}, {"sensor": "smoke_level", "term": "clear"}],
             consequent={"sensor": "risk", "term": "low"},
             action={"actuator": "alarm", "value": 0}, weight=1.0),
    ])


def _seed_generator(session, location_id):
    """Backup generator with fuel, rpm, temp, voltage sensors."""
    gen = Asset(name="generator", label="Generador Eléctrico",
                 description="Generador de emergencia del condominio",
                 icon="activity", output_name="urgency", output_label="Urgencia Generador",
                 output_min=0, output_max=100, location_id=location_id)
    session.add(gen)
    session.flush()

    session.add_all([
        SensorConfig(asset_id=gen.id, name="fuel_level", label="Nivel Combustible", unit="%",
                     min_val=0, max_val=100,
                     mf_config=[
                         {"term": "empty", "type": "trimf", "params": [0, 0, 20]},
                         {"term": "low", "type": "trimf", "params": [10, 30, 50]},
                         {"term": "normal", "type": "trimf", "params": [40, 70, 100]},
                     ]),
        SensorConfig(asset_id=gen.id, name="rpm", label="RPM Motor", unit="RPM",
                     min_val=0, max_val=3000,
                     mf_config=[
                         {"term": "stopped", "type": "trimf", "params": [0, 0, 200]},
                         {"term": "low", "type": "trimf", "params": [100, 800, 1500]},
                         {"term": "normal", "type": "trimf", "params": [1400, 1800, 2200]},
                         {"term": "over", "type": "trimf", "params": [2000, 2600, 3000]},
                     ]),
        SensorConfig(asset_id=gen.id, name="coolant_temp", label="Temp. Refrigerante", unit="°C",
                     min_val=0, max_val=120,
                     mf_config=[
                         {"term": "cold", "type": "trimf", "params": [0, 0, 40]},
                         {"term": "normal", "type": "trimf", "params": [40, 80, 95]},
                         {"term": "hot", "type": "trimf", "params": [85, 105, 120]},
                     ]),
        SensorConfig(asset_id=gen.id, name="voltage_out", label="Voltaje Salida", unit="V",
                     min_val=0, max_val=260,
                     mf_config=[
                         {"term": "none", "type": "trimf", "params": [0, 0, 50]},
                         {"term": "low", "type": "trimf", "params": [50, 150, 200]},
                         {"term": "normal", "type": "trimf", "params": [200, 220, 240]},
                         {"term": "high", "type": "trimf", "params": [230, 250, 260]},
                     ]),
    ])
    session.flush()

    session.add_all([
        Actuator(asset_id=gen.id, name="fuel_valve", label="Válvula Combustible", unit="", min_val=0, max_val=1, command=1, state=True),
        Actuator(asset_id=gen.id, name="starter", label="Motor Arranque", unit="", min_val=0, max_val=1, command=0, state=False),
        Actuator(asset_id=gen.id, name="load_transfer", label="Transferencia Carga", unit="", min_val=0, max_val=1, command=1, state=True),
    ])
    session.flush()

    session.add_all([
        Rule(asset_id=gen.id, name="R1",
             description="SI combustible VACÍO Y rpm DETENIDA ENTONCES critical → cerrar válvula",
             operator="and",
             antecedents=[{"sensor": "fuel_level", "term": "empty"}, {"sensor": "rpm", "term": "stopped"}],
             consequent={"sensor": "urgency", "term": "critical"},
             action={"actuator": "fuel_valve", "value": 0}, weight=1.0),
        Rule(asset_id=gen.id, name="R2",
             description="SI refrigerante CALIENTE O rpm ALTA ENTONCES high → reducir carga",
             operator="or",
             antecedents=[{"sensor": "coolant_temp", "term": "hot"}, {"sensor": "rpm", "term": "over"}],
             consequent={"sensor": "urgency", "term": "high"},
             action={"actuator": "load_transfer", "value": 0}, weight=1.0),
        Rule(asset_id=gen.id, name="R3",
             description="SI combustible BAJO ENTONCES medium → programar recarga",
             operator="and",
             antecedents=[{"sensor": "fuel_level", "term": "low"}],
             consequent={"sensor": "urgency", "term": "medium"},
             action={"actuator": "fuel_valve", "value": 1}, weight=1.0),
        Rule(asset_id=gen.id, name="R4",
             description="SI rpm DETENIDA Y combustible NORMAL ENTONCES high → arrancar motor",
             operator="and",
             antecedents=[{"sensor": "rpm", "term": "stopped"}, {"sensor": "fuel_level", "term": "normal"}],
             consequent={"sensor": "urgency", "term": "high"},
             action={"actuator": "starter", "value": 1}, weight=1.0),
        Rule(asset_id=gen.id, name="R5",
             description="SI rpm NORMAL Y voltaje NORMAL Y refrigerante NORMAL ENTONCES low → normal",
             operator="and",
             antecedents=[{"sensor": "rpm", "term": "normal"}, {"sensor": "voltage_out", "term": "normal"}, {"sensor": "coolant_temp", "term": "normal"}],
             consequent={"sensor": "urgency", "term": "low"},
             action={"actuator": "starter", "value": 0}, weight=1.0),
    ])


def _seed_lighting(session, location_id):
    """Lighting system with ambient light, current, voltage sensors."""
    light = Asset(name="lighting", label="Iluminación",
                   description="Sistema de iluminación general del condominio",
                   icon="sun", output_name="risk", output_label="Riesgo Eléctrico",
                   output_min=0, output_max=100, location_id=location_id)
    session.add(light)
    session.flush()

    session.add_all([
        SensorConfig(asset_id=light.id, name="ambient_light", label="Luz Ambiente", unit="lux",
                     min_val=0, max_val=100,
                     mf_config=[
                         {"term": "dim", "type": "trimf", "params": [0, 0, 30]},
                         {"term": "normal", "type": "trimf", "params": [20, 50, 75]},
                         {"term": "bright", "type": "trimf", "params": [60, 85, 100]},
                     ]),
        SensorConfig(asset_id=light.id, name="current_draw", label="Consumo", unit="A",
                     min_val=0, max_val=100,
                     mf_config=[
                         {"term": "low", "type": "trimf", "params": [0, 0, 30]},
                         {"term": "medium", "type": "trimf", "params": [20, 45, 70]},
                         {"term": "high", "type": "trimf", "params": [60, 85, 100]},
                     ]),
        SensorConfig(asset_id=light.id, name="voltage", label="Voltaje", unit="V",
                     min_val=100, max_val=260,
                     mf_config=[
                         {"term": "low", "type": "trimf", "params": [100, 100, 180]},
                         {"term": "normal", "type": "trimf", "params": [180, 220, 240]},
                         {"term": "high", "type": "trimf", "params": [230, 250, 260]},
                     ]),
    ])
    session.flush()

    session.add_all([
        Actuator(asset_id=light.id, name="dimmer", label="Regulador Luz", unit="%", min_val=0, max_val=100, command=100, state=True),
        Actuator(asset_id=light.id, name="circuit_breaker", label="Breaker Circuito", unit="", min_val=0, max_val=1, command=1, state=True),
    ])
    session.flush()

    session.add_all([
        Rule(asset_id=light.id, name="R1",
             description="SI consumo ALTO Y voltaje BAJO ENTONCES critical → cortar breaker",
             operator="and",
             antecedents=[{"sensor": "current_draw", "term": "high"}, {"sensor": "voltage", "term": "low"}],
             consequent={"sensor": "risk", "term": "critical"},
             action={"actuator": "circuit_breaker", "value": 0}, weight=1.0),
        Rule(asset_id=light.id, name="R2",
             description="SI consumo ALTO ENTONCES high → reducir luz",
             operator="and",
             antecedents=[{"sensor": "current_draw", "term": "high"}],
             consequent={"sensor": "risk", "term": "high"},
             action={"actuator": "dimmer", "value": 50}, weight=1.0),
        Rule(asset_id=light.id, name="R3",
             description="SI voltaje ALTO ENTONCES high → reducir carga",
             operator="and",
             antecedents=[{"sensor": "voltage", "term": "high"}],
             consequent={"sensor": "risk", "term": "high"},
             action={"actuator": "dimmer", "value": 60}, weight=1.0),
        Rule(asset_id=light.id, name="R4",
             description="SI voltaje NORMAL Y consumo BAJO ENTONCES low → luz normal",
             operator="and",
             antecedents=[{"sensor": "voltage", "term": "normal"}, {"sensor": "current_draw", "term": "low"}],
             consequent={"sensor": "risk", "term": "low"},
             action={"actuator": "dimmer", "value": 100}, weight=1.0),
    ])


def _seed_access(session, location_id):
    """Access/security system with door, motion, battery sensors."""
    access = Asset(name="access", label="Control de Acceso",
                    description="Sistema de seguridad y control de acceso perimetral",
                    icon="shield", output_name="alert", output_label="Nivel Alerta",
                    output_min=0, output_max=100, location_id=location_id)
    session.add(access)
    session.flush()

    session.add_all([
        SensorConfig(asset_id=access.id, name="door_sensors", label="Sensores Puertas", unit="",
                     min_val=0, max_val=1,
                     mf_config=[
                         {"term": "closed", "type": "trimf", "params": [0, 0, 0]},
                         {"term": "open", "type": "trimf", "params": [1, 1, 1]},
                     ]),
        SensorConfig(asset_id=access.id, name="motion_detect", label="Detección Movimiento", unit="",
                     min_val=0, max_val=1,
                     mf_config=[
                         {"term": "clear", "type": "trimf", "params": [0, 0, 0]},
                         {"term": "detected", "type": "trimf", "params": [1, 1, 1]},
                     ]),
        SensorConfig(asset_id=access.id, name="battery_level", label="Batería", unit="%",
                     min_val=0, max_val=100,
                     mf_config=[
                         {"term": "critical", "type": "trimf", "params": [0, 0, 15]},
                         {"term": "low", "type": "trimf", "params": [10, 25, 40]},
                         {"term": "normal", "type": "trimf", "params": [35, 65, 100]},
                     ]),
    ])
    session.flush()

    session.add_all([
        Actuator(asset_id=access.id, name="lock", label="Cerradura Electrónica", unit="", min_val=0, max_val=1, command=1, state=True),
        Actuator(asset_id=access.id, name="alarm", label="Alarma Perimetral", unit="", min_val=0, max_val=1, command=0, state=False),
        Actuator(asset_id=access.id, name="camera_switch", label="Cámaras Seguridad", unit="", min_val=0, max_val=1, command=1, state=True),
    ])
    session.flush()

    session.add_all([
        Rule(asset_id=access.id, name="R1",
             description="SI puerta ABIERTA Y movimiento DETECTADO ENTONCES critical → alarma + cámaras",
             operator="and",
             antecedents=[{"sensor": "door_sensors", "term": "open"}, {"sensor": "motion_detect", "term": "detected"}],
             consequent={"sensor": "alert", "term": "critical"},
             action={"actuator": "alarm", "value": 1}, weight=1.0),
        Rule(asset_id=access.id, name="R2",
             description="SI puerta ABIERTA ENTONCES high → activar alarma",
             operator="and",
             antecedents=[{"sensor": "door_sensors", "term": "open"}],
             consequent={"sensor": "alert", "term": "high"},
             action={"actuator": "alarm", "value": 1}, weight=1.0),
        Rule(asset_id=access.id, name="R3",
             description="SI batería CRÍTICA ENTONCES high → respaldo",
             operator="and",
             antecedents=[{"sensor": "battery_level", "term": "critical"}],
             consequent={"sensor": "alert", "term": "high"},
             action={"actuator": "lock", "value": 0}, weight=1.0),
        Rule(asset_id=access.id, name="R4",
             description="SI batería BAJA ENTONCES medium → mantenimiento",
             operator="and",
             antecedents=[{"sensor": "battery_level", "term": "low"}],
             consequent={"sensor": "alert", "term": "medium"},
             action={"actuator": "camera_switch", "value": 0}, weight=1.0),
        Rule(asset_id=access.id, name="R5",
             description="SI puerta CERRADA Y sin movimiento Y batería NORMAL ENTONCES none",
             operator="and",
             antecedents=[{"sensor": "door_sensors", "term": "closed"}, {"sensor": "motion_detect", "term": "clear"}, {"sensor": "battery_level", "term": "normal"}],
             consequent={"sensor": "alert", "term": "none"},
             action={"actuator": "alarm", "value": 0}, weight=1.0),
    ])


if __name__ == "__main__":
    seed()

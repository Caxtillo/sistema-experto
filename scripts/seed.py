"""Database seeding script for the Expert System.

Creates the initial schema and populates it with hierarchical data:
- 8 condominiums with real addresses
- Real equipment distribution: bombas (water), plantas (generator), ascensores (elevator)
- Each with sensors, actuators, and fuzzy rules
- 17 user accounts (1 admin + 1 tech + 1 supervisor per condominium) for role-based access
"""

import hashlib
import secrets
from storage.database import get_session
from models.models import Asset, SensorConfig, Actuator, Rule
from models.models import Condominium, Building, MachineRoom, User
from core.knowledge_base import auto_generate_mf


def _hash(pw):
    """Hash password with PBKDF2-SHA256 and a random 16-byte salt.
    Returns salt$hash (both hex-encoded) for storage."""
    salt = secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt.encode(), 100_000)
    return f"{salt}${h.hex()}"


# Equipment config per condominium: (base_type, name_suffix, quantity)
CONDO_EQUIPMENT = [
    ("Centro Residencial San Miguel", "Av. Alirio Ugarte Pelayo, frente a la sede PDVSA", 9.7997, -63.1627, "Edificio Principal",
     [("water", 2), ("generator", 1), ("elevator", 1)]),
    ("Condominio La Ceiba", "Vía Viboral, Urb. Lomas del Bosque", 9.797, -63.163, "Torre A",
     [("water", 4)]),
    ("Condominio Villas Merey", "Vía Viboral, al lado C.C. Sambilito", 9.798, -63.162, "Torre B",
     [("water", 2), ("generator", 1)]),
    ("Cond. Los Chaguaramos", "Vía La Toscana, Sector Tipuro, Urb. San Miguel", 9.796, -63.161, "Torre C",
     [("water", 2)]),
    ("Condominio Los Robles", "Vía La Toscana, Sector Tipuro, Urb. San Miguel", 9.797, -63.160, "Torre D",
     [("water", 2)]),
    ("Condominio Golf Plaza", "Vía La Toscana, Calle Guarapiche, Urb. San Miguel", 9.8001, -63.1614, "Torre E",
     [("water", 8), ("generator", 1), ("elevator", 4)]),
    ("Condominio Vista Golf", "Vía La Toscana, Calle Guarapiche, Urb. San Miguel", 9.8009, -63.1604, "Torre F",
     [("water", 8), ("generator", 1), ("elevator", 4)]),
    ("Condominio San Andrés", "Vía La Toscana, Calle Guarapiche, Urb. San Miguel", 9.7985, -63.1595, "Torre G",
     [("water", 2), ("generator", 1), ("elevator", 2)]),
    ("Centro Empresarial San Miguel", "Av. Alirio Ugarte Pelayo, frente PDVSA ESEM", 9.7845, -63.1535, "Oficinas",
     [("generator", 1)]),
]

# Base types and their display properties
ASSET_TYPE_SLUGS = {"water": "bomba", "generator": "planta", "elevator": "ascensor"}

ASSET_TYPES = {
    "water":     {"label": "Bomba", "icon": "droplets", "output_name": "urgency", "output_label": "Urgencia", "output_min": 0, "output_max": 100,
                  "room": "Cuarto de Bombas"},
    "generator": {"label": "Planta Eléctrica", "icon": "zap", "output_name": "maintenance", "output_label": "Prioridad de Mantenimiento",
                  "output_min": 0, "output_max": 100, "room": "Planta Baja"},
    "elevator":  {"label": "Ascensor", "icon": "arrow-up", "output_name": "maintenance", "output_label": "Prioridad de Mantenimiento",
                  "output_min": 0, "output_max": 100, "room": "Sótano"},
}

# Sensor configs per base type: (name, label, unit, min, max, [term_names])
SENSOR_DEFS = {
    "water": [
        ("vibration", "Vibración", "mm/s", 0, 20, ["bajo", "medio", "alto"]),
        ("temperature", "Temperatura", "°C", 0, 100, [{"name": "normal", "peak": 25}, {"name": "caliente", "peak": 50}, {"name": "critico", "peak": 80}]),
        ("pressure", "Presión", "bar", 0, 16, ["bajo", "normal", "alto"]),
        ("flow", "Caudal", "L/min", 0, 100, ["bajo", "normal", "alto"]),
        ("motor_current", "Corriente del Motor", "A", 0, 30, ["bajo", "normal", "alto"]),
    ],
    "generator": [
        ("rpm", "RPM", "rpm", 0, 2000, [{"name": "bajo", "peak": 0}, {"name": "normal", "peak": 1700}, {"name": "alto", "peak": 1900}]),
        ("temperature", "Temperatura", "°C", 0, 120, [{"name": "normal", "peak": 70}, {"name": "caliente", "peak": 90}, {"name": "critico", "peak": 110}]),
        ("fuel_level", "Nivel Combustible", "%", 0, 100, ["critico", "bajo", "normal"]),
        ("voltage", "Voltaje", "V", 0, 300, [{"name": "bajo", "peak": 140}, {"name": "normal", "peak": 220}, {"name": "alto", "peak": 260}]),
        ("oil_pressure", "Presión del Aceite", "bar", 0, 8, [{"name": "bajo", "peak": 0.5}, {"name": "normal", "peak": 5}, {"name": "alto", "peak": 7}]),
    ],
    "elevator": [
        ("vibration", "Vibración", "mm/s", 0, 15, ["bajo", "medio", "alto"]),
        ("temperature", "Temperatura", "°C", 0, 80, [{"name": "normal", "peak": 30}, {"name": "caliente", "peak": 50}, {"name": "critico", "peak": 70}]),
        ("speed_var", "Var. Velocidad", "%", 0, 20, ["estable", "moderado", "erratico"]),
        ("motor_current", "Corriente del Motor", "A", 0, 40, [{"name": "bajo", "peak": 0}, {"name": "normal", "peak": 8}, {"name": "alto", "peak": 25}]),
    ],
}

# Actuator defs per base type: (name, label, unit, min, max, auto)
ACTUATOR_DEFS = {
    "water": [
        ("inlet_valve", "Válvula de entrada", "%", 0, 100, True),
        ("bypass_valve", "Válvula de by-pass", "%", 0, 100, True),
        ("alarm", "Alarma", None, 0, 1, False),
    ],
    "generator": [
        ("speed_control", "Control de velocidad", "%", 0, 100, True),
        ("choke", "Estrangulador", "%", 0, 100, True),
        ("alarm", "Alarma", None, 0, 1, False),
    ],
    "elevator": [
        ("speed_regulator", "Regulador velocidad", "%", 0, 100, True),
        ("brake", "Freno", None, 0, 1, True),
        ("alarm", "Alarma", None, 0, 1, False),
    ],
}

# Rule defs per base type: list of (name, description, operator, antecedents, consequent, action, weight)
RULE_DEFS = {
    "water": [
        ("R1", "SI vibración ALTA Y temperatura CRÍTICO ENTONCES alta urgencia", "and",
         [{"sensor": "vibration", "term": "alto"}, {"sensor": "temperature", "term": "critico"}],
         {"sensor": "urgency", "term": "high"},
         {"actuator": "alarm", "value": 1}, 1.0),
        ("R2", "SI caudal BAJO Y presión ALTA ENTONCES alta urgencia", "and",
         [{"sensor": "flow", "term": "bajo"}, {"sensor": "pressure", "term": "alto"}],
         {"sensor": "urgency", "term": "high"},
         {"actuator": "bypass_valve", "value": 100}, 1.0),
        ("R3", "SI corriente ALTA ENTONCES alta urgencia", "and",
         [{"sensor": "motor_current", "term": "alto"}],
         {"sensor": "urgency", "term": "high"},
         {"actuator": "inlet_valve", "value": 100}, 1.0),
        ("R4", "SI vibración BAJA Y caudal NORMAL Y presión NORMAL ENTONCES baja urgencia", "and",
         [{"sensor": "vibration", "term": "bajo"}, {"sensor": "flow", "term": "normal"}, {"sensor": "pressure", "term": "normal"}],
         {"sensor": "urgency", "term": "low"},
         {"actuator": "inlet_valve", "value": 50}, 1.0),
    ],
    "generator": [
        ("R1", "SI temperatura CRÍTICO Y RPM ALTA ENTONCES alto mantenimiento", "and",
         [{"sensor": "temperature", "term": "critico"}, {"sensor": "rpm", "term": "alto"}],
         {"sensor": "maintenance", "term": "high"},
         {"actuator": "speed_control", "value": 60}, 1.0),
        ("R2", "SI combustible CRÍTICO ENTONCES alto mantenimiento", "and",
         [{"sensor": "fuel_level", "term": "critico"}],
         {"sensor": "maintenance", "term": "high"},
         {"actuator": "alarm", "value": 1}, 1.0),
        ("R3", "SI presión aceite BAJA Y temperatura CALIENTE ENTONCES alto mantenimiento", "and",
         [{"sensor": "oil_pressure", "term": "bajo"}, {"sensor": "temperature", "term": "caliente"}],
         {"sensor": "maintenance", "term": "high"},
         {"actuator": "choke", "value": 80}, 1.0),
        ("R4", "SI voltaje NORMAL Y temperatura NORMAL Y combustible NORMAL ENTONCES bajo mantenimiento", "and",
         [{"sensor": "voltage", "term": "normal"}, {"sensor": "temperature", "term": "normal"}, {"sensor": "fuel_level", "term": "normal"}],
         {"sensor": "maintenance", "term": "low"},
         {"actuator": "speed_control", "value": 50}, 1.0),
    ],
    "elevator": [
        ("R1", "SI vibración ALTA Y temperatura CRÍTICO ENTONCES alto mantenimiento", "and",
         [{"sensor": "vibration", "term": "alto"}, {"sensor": "temperature", "term": "critico"}],
         {"sensor": "maintenance", "term": "high"},
         {"actuator": "brake", "value": 1}, 1.0),
        ("R2", "SI velocidad ERRÁTICA Y corriente ALTA ENTONCES alto mantenimiento", "and",
         [{"sensor": "speed_var", "term": "erratico"}, {"sensor": "motor_current", "term": "alto"}],
         {"sensor": "maintenance", "term": "high"},
         {"actuator": "speed_regulator", "value": 70}, 1.0),
        ("R3", "SI vibración BAJA Y velocidad ESTABLE Y corriente NORMAL ENTONCES bajo mantenimiento", "and",
         [{"sensor": "vibration", "term": "bajo"}, {"sensor": "speed_var", "term": "estable"}, {"sensor": "motor_current", "term": "normal"}],
         {"sensor": "maintenance", "term": "low"},
         {"actuator": "speed_regulator", "value": 50}, 1.0),
    ],
}


_asset_counter = 0

def _create_asset(session, base_type, instance_num, location_id, condo_slug, condo_short):
    """Create an asset instance with its sensors, actuators, and rules."""
    global _asset_counter
    _asset_counter += 1
    t = ASSET_TYPES[base_type]
    type_slug = ASSET_TYPE_SLUGS[base_type]
    asset_name = f"{type_slug}_{condo_slug}_{instance_num}"
    asset_label = f"{t['label']} {condo_short} #{instance_num}"

    asset = Asset(
        name=asset_name, label=asset_label,
        description=f"{t['label']} de {condo_short}",
        icon=t["icon"], output_name=t["output_name"],
        output_label=t["output_label"],
        output_min=t["output_min"], output_max=t["output_max"],
        location_id=location_id,
    )
    session.add(asset)
    session.flush()

    # Sensors
    for s_name, s_label, s_unit, s_min, s_max, terms in SENSOR_DEFS[base_type]:
        mf = auto_generate_mf(terms, s_min, s_max)
        session.add(SensorConfig(
            asset_id=asset.id, name=s_name, label=s_label, unit=s_unit,
            min_val=s_min, max_val=s_max, mf_config=mf,
        ))

    # Actuators
    for a_name, a_label, a_unit, a_min, a_max, a_auto in ACTUATOR_DEFS[base_type]:
        session.add(Actuator(
            asset_id=asset.id, name=a_name, label=a_label,
            unit=a_unit, min_val=a_min, max_val=a_max, auto=a_auto,
        ))

    # Rules
    for r_name, r_desc, r_op, r_ant, r_con, r_act, r_w in RULE_DEFS[base_type]:
        session.add(Rule(
            asset_id=asset.id, name=r_name, description=r_desc,
            operator=r_op, antecedents=r_ant, consequent=r_con,
            action=r_act, weight=r_w,
        ))

    return asset_name


def seed():
    """Seed the database with initial data if it's empty.

    Creates the full hierarchy: Condominium -> Building -> MachineRoom -> Asset.
    Creates equipment per condo: bombas, plantas, ascensores.
    Also creates 17 users with role-based access (1 admin + 8 sup + 8 tec).
    """
    session = get_session()

    if session.query(Asset).count() > 0:
        print("Database already seeded.")
        session.close()
        return

    asset_instance_map = {}  # asset_name -> base_type for simulator registration

    # ---- Create condos with their equipment ----
    CONDO_SLUGS = {
        "Centro Residencial San Miguel": ("san_miguel", "San Miguel"),
        "Condominio La Ceiba": ("ceiba", "Ceiba"),
        "Condominio Villas Merey": ("merey", "Merey"),
        "Cond. Los Chaguaramos": ("chaguaramos", "Chaguaramos"),
        "Condominio Los Robles": ("robles", "Robles"),
        "Condominio Golf Plaza": ("golf_plaza", "Golf Plaza"),
        "Condominio Vista Golf": ("vista_golf", "Vista Golf"),
        "Condominio San Andrés": ("san_andres", "San Andrés"),
        "Centro Empresarial San Miguel": ("empresarial_sm", "Empresarial SM"),
    }

    for condo_data in CONDO_EQUIPMENT:
        name, address, lat, lng, building_name, equipment = condo_data
        slug, short = CONDO_SLUGS.get(name, (name.lower().replace(" ", "_"), name))

        condo = Condominium(name=name, address=address, lat=lat, lng=lng, slug=slug)
        session.add(condo)
        session.flush()

        building = Building(name=building_name, condominium_id=condo.id)
        session.add(building)
        session.flush()

        # Group equipment by room type
        room_map = {}  # room_name -> list of (base_type, count)
        for base_type, count in equipment:
            room_name = ASSET_TYPES[base_type]["room"]
            if room_name not in room_map:
                room_map[room_name] = []
            room_map[room_name].append((base_type, count))

        for room_name, items in room_map.items():
            room = MachineRoom(name=room_name, building_id=building.id)
            session.add(room)
            session.flush()

            for base_type, count in items:
                for i in range(1, count + 1):
                    asset_name = _create_asset(session, base_type, i, room.id, slug, short)
                    asset_instance_map[asset_name] = base_type

    # ---- Users ----
    admin = User(username="admin", password_hash=_hash("admin123"),
                 role="admin", condominiums=[])
    users = [admin]

    all_condos = session.query(Condominium).all()
    for c in all_condos:
        slug, _ = CONDO_SLUGS.get(c.name, (c.name.lower().replace(" ", "_"), c.name))
        tec = User(username=f"tec_{slug}", password_hash=_hash("tec123"),
                   role="technician", condominiums=[c])
        sup = User(username=f"sup_{slug}", password_hash=_hash("sup123"),
                   role="supervisor", condominiums=[c])
        users.extend([tec, sup])
    session.add_all(users)

    session.commit()

    # Print summary
    condo_count = session.query(Condominium).count()
    building_count = session.query(Building).count()
    room_count = session.query(MachineRoom).count()
    asset_count = session.query(Asset).count()
    sensor_count = session.query(SensorConfig).count()
    actuator_count = session.query(Actuator).count()
    rule_count = session.query(Rule).count()

    print("Database seeded successfully!")
    print(f"  - {condo_count} condominiums")
    print(f"  - {building_count} buildings")
    print(f"  - {room_count} machine rooms")
    print(f"  - {asset_count} assets")
    print(f"  - {sensor_count} sensors")
    print(f"  - {actuator_count} actuators")
    print(f"  - {rule_count} rules")
    user_count = session.query(User).count()
    print(f"  - {user_count} users")

    # Export instance mapping for use by api.py
    import json, os
    mapping_path = os.path.join(os.path.dirname(__file__), "..", "data", "asset_instances.json")
    os.makedirs(os.path.dirname(mapping_path), exist_ok=True)
    with open(mapping_path, "w") as f:
        json.dump(asset_instance_map, f)

    session.close()


if __name__ == "__main__":
    seed()

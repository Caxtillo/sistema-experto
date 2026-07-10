"""IIoT sensor simulator for the Expert System.

Generates realistic sensor readings for 3 critical condominium assets
(elevator, electrical system, water system) with configurable scenarios
that simulate normal operation and various fault conditions.

The simulator uses a combination of:
- Base values defined per scenario
- Random noise for variability
- Sine-wave cycles for natural drift
- Actuator feedback: commands from the expert system modify sensor readings

External data from real sensors or phone inputs can override simulated values
for hybrid simulated/real operation.
"""

import random
import math

SCENARIOS = {
    "elevator": {
        "normal": {"vibration": 1, "temperature": 25, "speed_var": 1, "motor_current": 5, "amp": 0.05},
        "desgaste_poleas": {"vibration": 8, "temperature": 45, "speed_var": 4, "motor_current": 8, "amp": 0.15,
                            "label": "Desgaste de Poleas", "icon": "tools"},
        "sobrecalentamiento": {"vibration": 3, "temperature": 70, "speed_var": 3, "motor_current": 10, "amp": 0.1,
                               "label": "Sobrecalentamiento", "icon": "thermometer"},
        "falla_motor": {"vibration": 12, "temperature": 65, "speed_var": 14, "motor_current": 18, "amp": 0.2,
                        "label": "Falla de Motor", "icon": "alert-triangle"},
    },
    "electrical": {
        "normal": {"voltage": 220, "current": 20, "temp_rise": 20, "amp": 0.05},
        "sobrecarga": {"voltage": 200, "current": 85, "temp_rise": 65, "amp": 0.12,
                       "label": "Sobrecarga Eléctrica", "icon": "zap"},
        "corto_circuito": {"voltage": 160, "current": 90, "temp_rise": 70, "amp": 0.15,
                           "label": "Riesgo de Cortocircuito", "icon": "alert-triangle"},
        "bajo_voltaje": {"voltage": 140, "current": 60, "temp_rise": 30, "amp": 0.1,
                         "label": "Bajo Voltaje", "icon": "arrow-down"},
    },
    "water": {
        "normal": {"vibration": 2, "temperature": 30, "pressure": 8, "flow": 50, "motor_current": 10, "amp": 0.05},
        "cavitacion": {"vibration": 8, "temperature": 45, "pressure": 4, "flow": 20, "motor_current": 15, "amp": 0.15,
                       "label": "Cavitación", "icon": "droplet"},
        "bomba_danada": {"vibration": 14, "temperature": 70, "pressure": 12, "flow": 5, "motor_current": 22, "amp": 0.12,
                          "label": "Bomba Dañada", "icon": "alert-circle"},
        "obstruccion": {"vibration": 5, "temperature": 35, "pressure": 14, "flow": 8, "motor_current": 18, "amp": 0.1,
                         "label": "Obstrucción", "icon": "alert-triangle"},
    },
    "hvac": {
        "normal": {"temp_in": 24, "temp_out": 12, "pressure": 120, "rpm": 1800, "amp": 0.05},
        "sobrecarga": {"temp_in": 35, "temp_out": 25, "pressure": 180, "rpm": 2500, "amp": 0.12,
                       "label": "Sobrecarga HVAC", "icon": "thermometer"},
        "fuga_refrigerante": {"temp_in": 28, "temp_out": 22, "pressure": 80, "rpm": 2000, "amp": 0.15,
                              "label": "Fuga de Refrigerante", "icon": "alert-triangle"},
        "falla_compresor": {"temp_in": 36, "temp_out": 30, "pressure": 60, "rpm": 1200, "amp": 0.18,
                            "label": "Falla de Compresor", "icon": "alert-circle"},
    },
    "fire": {
        "normal": {"smoke_level": 1, "temp_rise": 22, "water_pressure": 100, "amp": 0.05},
        "deteccion_humo": {"smoke_level": 60, "temp_rise": 35, "water_pressure": 100, "amp": 0.1,
                           "label": "Detección de Humo", "icon": "alert-triangle"},
        "principio_incendio": {"smoke_level": 85, "temp_rise": 55, "water_pressure": 100, "amp": 0.12,
                               "label": "Principio de Incendio", "icon": "flame"},
        "alarma_total": {"smoke_level": 95, "temp_rise": 75, "water_pressure": 100, "amp": 0.15,
                         "label": "Alarma Total", "icon": "alert-octagon"},
    },
    "generator": {
        "normal": {"fuel_level": 90, "rpm": 1800, "temperature": 70, "voltage": 220, "oil_pressure": 5, "amp": 0.05},
        "bajo_combustible": {"fuel_level": 12, "rpm": 1800, "temperature": 70, "voltage": 218, "oil_pressure": 4.5, "amp": 0.08,
                             "label": "Bajo Combustible", "icon": "fuel"},
        "sobrecalentamiento": {"fuel_level": 60, "rpm": 1900, "temperature": 110, "voltage": 225, "oil_pressure": 3, "amp": 0.12,
                               "label": "Sobrecalentamiento", "icon": "thermometer"},
        "falla_arranque": {"fuel_level": 80, "rpm": 200, "temperature": 25, "voltage": 120, "oil_pressure": 1, "amp": 0.2,
                           "label": "Falla de Arranque", "icon": "alert-circle"},
        "baja_presion_aceite": {"fuel_level": 70, "rpm": 1700, "temperature": 85, "voltage": 215, "oil_pressure": 0.8, "amp": 0.15,
                                "label": "Baja Presión de Aceite", "icon": "alert-triangle"},
    },
    "lighting": {
        "normal": {"ambient_light": 50, "current_draw": 20, "voltage": 220, "amp": 0.05},
        "sobrecarga": {"ambient_light": 80, "current_draw": 75, "voltage": 210, "amp": 0.1,
                       "label": "Sobrecarga Iluminación", "icon": "zap"},
        "falla_transformador": {"ambient_light": 20, "current_draw": 50, "voltage": 160, "amp": 0.15,
                                "label": "Falla Transformador", "icon": "alert-triangle"},
    },
    "access": {
        "normal": {"door_sensors": 0, "motion_detect": 0, "battery_level": 95, "amp": 0.05},
        "intrusion": {"door_sensors": 1, "motion_detect": 1, "battery_level": 95, "amp": 0.1,
                      "label": "Intrusión Detectada", "icon": "shield-off"},
        "bateria_baja": {"door_sensors": 0, "motion_detect": 0, "battery_level": 8, "amp": 0.05,
                         "label": "Batería Baja", "icon": "battery-charging"},
        "falla_sistema": {"door_sensors": 0, "motion_detect": 0, "battery_level": 50, "amp": 0.1,
                          "label": "Falla del Sistema", "icon": "alert-circle"},
    },
}

RECOMMENDATIONS = {
    "elevator": {
        "critical": [
            "DETENER ASCENSOR INMEDIATAMENTE",
            "Notificar a mantenimiento de emergencia",
            "Evacuar cabina si hay pasajeros",
            "Inspección estructural completa requerida",
        ],
        "high": [
            "Programar mantenimiento prioritario (24h)",
            "Revisar sistema de frenos y poleas",
            "Monitorear vibraciones continuamente",
            "Restringir uso a personal autorizado",
        ],
        "medium": [
            "Inspección preventiva en 7 días",
            "Revisar lubricación de rieles",
            "Verificar alineación de puertas",
            "Monitorear temperatura del motor",
        ],
        "low": [
            "Mantenimiento rutinario mensual",
            "Sistema operando normalmente",
            "Continuar monitoreo estándar",
        ],
        "none": ["Sistema operando normalmente"],
    },
    "electrical": {
        "critical": [
            "CORTAR SUMINISTRO ELÉCTRICO INMEDIATAMENTE",
            "Notificar a bomberos y electricista certificado",
            "Evacuar área del tablero eléctrico",
            "Riesgo de incendio - Activar protocolo de emergencia",
        ],
        "high": [
            "Reducir carga eléctrica del sistema",
            "Inspección térmica con cámara infrarroja",
            "Revisar conexiones y bornes",
            "Programar revisión de emergencia (12h)",
        ],
        "medium": [
            "Monitorear carga y temperatura cada hora",
            "Revisar sistema de ventilación del cuarto eléctrico",
            "Verificar protecciones termomagnéticas",
            "Mantenimiento preventivo en 15 días",
        ],
        "low": [
            "Sistema eléctrico estable",
            "Monitoreo rutinario semanal",
            "Limpieza programada de tableros",
        ],
        "none": ["Sistema eléctrico estable"],
    },
    "generator": {
        "critical": [
            "DETENER GENERADOR INMEDIATAMENTE",
            "Notificar a J.G.M y técnico certificado",
            "Revisar sistema de combustible y refrigeración",
            "Riesgo de falla catastrófica del generador",
        ],
        "high": [
            "Inspeccionar sistema de lubricación y filtros",
            "Verificar nivel de combustible y baterías",
            "Medir temperatura y presión de aceite",
            "Programar revisión de emergencia (24h)",
        ],
        "medium": [
            "Revisar RPM y voltaje de salida",
            "Verificar correas y tensores",
            "Monitorear temperatura del motor",
            "Mantenimiento preventivo en 15 días",
        ],
        "low": [
            "Sistema de generación estable",
            "Revisión semanal de niveles",
            "Encendido programado de prueba",
        ],
        "none": ["Sistema de generación en óptimas condiciones"],
    },
    "water": {
        "critical": [
            "DETENER BOMBA INMEDIATAMENTE",
            "Notificar a Junta de Condominio urgente",
            "Revisar motor eléctrico y acople",
            "Riesgo de falla catastrófica del equipo",
        ],
        "high": [
            "Inspeccionar rodamientos y sellos mecánicos",
            "Revisar válvulas y filtros del sistema",
            "Medir vibración y temperatura del motor",
            "Programar reparación en 24h",
        ],
        "medium": [
            "Revisar presión de descarga y caudal",
            "Verificar corriente del motor",
            "Monitorear temperatura operativa",
            "Mantenimiento preventivo en 15 días",
        ],
        "low": [
            "Inspección visual mensual",
            "Lubricación programada de rodamientos",
            "Sistema operando normalmente",
        ],
        "none": ["Sistema de bombeo en óptimas condiciones"],
    },
    "hvac": {
        "critical": [
            "DETENER SISTEMA HVAC INMEDIATAMENTE",
            "Notificar a técnico de refrigeración",
            "Evacuar áreas con fuga de refrigerante",
            "Inspección completa del compresor",
        ],
        "high": [
            "Reducir carga del sistema HVAC",
            "Revisar niveles de refrigerante",
            "Inspeccionar serpentines y filtros",
            "Monitorear temperatura de salida",
        ],
        "medium": [
            "Mantenimiento preventivo de HVAC",
            "Limpiar filtros de aire",
            "Verificar presión del sistema",
            "Revisar ventiladores y motores",
        ],
        "low": [
            "Sistema HVAC operando normalmente",
            "Cambio de filtros programado",
            "Monitoreo rutinario de temperaturas",
        ],
        "none": ["Climatización en óptimas condiciones"],
    },
    "fire": {
        "critical": [
            "ACTIVAR ALARMA GENERAL DE INCENDIO",
            "Notificar a bomberos inmediatamente",
            "Evacuar todas las áreas del edificio",
            "Activar sistema de rociadores",
        ],
        "high": [
            "Verificar origen de humo o calor",
            "Activar protocolo de incendio",
            "Preparar equipos de extinción",
            "Notificar a seguridad del edificio",
        ],
        "medium": [
            "Inspeccionar detectores de humo",
            "Revisar presión de red contra incendios",
            "Prueba de alarmas y rociadores",
            "Mantenimiento preventivo del sistema",
        ],
        "low": [
            "Sistema contra incendios normal",
            "Prueba mensual de detectores",
            "Verificar fechas de recarga de extintores",
        ],
        "none": ["Protección contra incendios activa"],
    },
    "generator": {
        "critical": [
            "DETENER GENERADOR INMEDIATAMENTE",
            "Revisar sobrecalentamiento del motor",
            "Verificar presión de aceite y nivel de refrigerante",
            "Notificar a técnico especialista",
        ],
        "high": [
            "Programar recarga de combustible urgente",
            "Reducir carga del generador",
            "Revisar sistema de lubricación (presión de aceite)",
            "Monitorear temperatura del motor y presión de aceite",
        ],
        "medium": [
            "Programar mantenimiento del generador",
            "Revisar niveles de aceite y refrigerante",
            "Prueba de transferencia automática",
            "Verificar presión de aceite y estado de baterías",
        ],
        "low": [
            "Generador en buen estado",
            "Prueba semanal de arranque",
            "Verificar presión de aceite en cada encendido",
        ],
        "none": ["Generador disponible y operativo"],
    },
    "lighting": {
        "critical": [
            "CORTAR CIRCUITO DE ILUMINACIÓN",
            "Riesgo de cortocircuito - Revisar inmediatamente",
            "Notificar a electricista certificado",
            "Inspeccionar transformadores y reguladores",
        ],
        "high": [
            "Reducir carga de iluminación",
            "Revisar estado de balastros y lámparas",
            "Medir consumo por fase",
            "Programar revisión del transformador",
        ],
        "medium": [
            "Revisar sistema de iluminación general",
            "Verificar voltaje en tableros secundarios",
            "Cambiar lámparas fundidas",
            "Mantenimiento preventivo de luminarias",
        ],
        "low": [
            "Iluminación operando normalmente",
            "Monitoreo rutinario de consumo",
            "Limpieza programada de luminarias",
        ],
        "none": ["Sistema de iluminación óptimo"],
    },
    "access": {
        "critical": [
            "ACTIVAR PROTOCOLO DE SEGURIDAD",
            "Notificar a seguridad y administración",
            "Verificar estado de cerraduras electrónicas",
            "Activar sistema de respaldo",
        ],
        "high": [
            "Intrusión detectada - Verificar cámaras",
            "Reforzar seguridad de perímetro",
            "Revisar registros de acceso",
            "Notificar a vigilancia",
        ],
        "medium": [
            "Reemplazar baterías del sistema",
            "Revisar sensores de puertas y ventanas",
            "Prueba de funcionamiento de alarmas",
            "Mantenimiento preventivo del sistema",
        ],
        "low": [
            "Sistema de acceso normal",
            "Monitoreo rutinario de baterías",
            "Verificar estado de cámaras",
        ],
        "none": ["Seguridad perimetral activa"],
    },
}
class IIoTSimulator:
    """Simulates IIoT sensors for elevator, electrical, and water systems.

    Each asset has multiple scenarios (normal + fault conditions) that define
    base sensor values. Readings include random noise and cyclic variation.
    Actuator commands from the expert system modify sensor values to simulate
    closed-loop control.

    External/phone sensor data can override simulated values for hybrid operation.
    """

    def __init__(self, base_seed=None):
        """Initialize the simulator with optional random seed for reproducibility."""
        if base_seed:
            random.seed(base_seed)
        self.time = 0.0
        self.scenarios = {}
        for asset_name in SCENARIOS:
            self.scenarios[asset_name] = "normal"
        self.instances = {}  # reg_name -> base_type (e.g. "water_1" -> "water")
        self.external_data = {}
        self.actuator_commands = {}
        self.fault_recovery = {}

    def add_instance(self, name, base_type):
        """Register an asset instance that uses a base type's scenario config."""
        if base_type in SCENARIOS:
            self.instances[name] = base_type
            self.scenarios[name] = "normal"

    def get_all_asset_names(self):
        """Return all known asset names (base types + instances)."""
        return list(SCENARIOS.keys()) + list(self.instances.keys())

    def inject_data(self, asset_name, sensor_name, value):
        """Override a simulated sensor value with an external/phone reading."""
        if asset_name not in self.external_data:
            self.external_data[asset_name] = {}
        self.external_data[asset_name][sensor_name] = value

    def clear_external(self, asset_name=None):
        """Clear all external data, or for a specific asset."""
        if asset_name:
            self.external_data.pop(asset_name, None)
        else:
            self.external_data.clear()

    def has_external(self, asset_name, sensor_name):
        """Check if external data exists for a specific sensor."""
        return (
            asset_name in self.external_data
            and sensor_name in self.external_data[asset_name]
        )

    def set_scenario(self, asset, scenario_name, auto_recover=True):
        """Set the active scenario for an asset (e.g., 'normal', 'falla_motor').
        
        If auto_recover is True and scenario is not normal, schedules automatic
        recovery after ~15 seconds (7-8 simulation cycles).
        """
        base = self.instances.get(asset, asset)
        if asset in self.scenarios and scenario_name in SCENARIOS.get(base, {}):
            self.scenarios[asset] = scenario_name
            if auto_recover and scenario_name != "normal":
                self.fault_recovery[asset] = self.time + 15


    def get_scenarios_list(self, asset):
        """Return available scenarios for an asset with labels and icons."""
        base = self.instances.get(asset, asset)
        return [
            {"id": k, "label": v.get("label", k.capitalize()), "icon": v.get("icon", "circle")}
            for k, v in SCENARIOS.get(base, {}).items()
        ]


    def _read(self, asset, inst_name=None):
        """Generate raw sensor readings for an asset based on its current scenario.

        Applies random noise and sine-wave variation to the scenario base values.
        If inst_name is provided, checks for an instance-specific scenario first.
        """
        configs = SCENARIOS.get(asset, {})
        scenario_key = inst_name if (inst_name and inst_name in self.scenarios) else asset
        scenario_name = self.scenarios.get(scenario_key, "normal")
        scenario = configs.get(scenario_name, configs.get("normal", {}))
        if not scenario:
            return {}

        t = self.time
        result = {}
        for key in scenario:
            if key in ("label", "icon", "amp"):
                continue
            base = scenario.get(key, 50) if isinstance(scenario.get(key), (int, float)) else 50
            amp = scenario.get("amp", 0.1)
            noise = 1 + random.uniform(-amp, amp)
            cycle = 1 + 0.1 * math.sin(t * 0.01 + hash(key) % 10)
            result[key] = max(0, base * noise * cycle)

        return result

    def read_one(self, asset_name):
        """Read sensors for a single asset and apply actuator effects.
        External/injected data overrides simulated values."""
        base = self.instances.get(asset_name, asset_name)
        raw = self._read(base, asset_name)
        if asset_name in self.external_data:
            raw.update(self.external_data[asset_name])
        return self.apply_actuators(raw, asset_name)

    def read_all(self):
        """Read all sensors for all assets and instances, then apply actuator effects.

        External/injected data overrides simulated values.

        Returns a dict keyed by asset name, each containing sensor name->value mappings.
        """
        raw = {}
        for asset_name in SCENARIOS:
            raw[asset_name] = self._read(asset_name)
        for inst_name, base_type in self.instances.items():
            raw[inst_name] = self._read(base_type, inst_name)
        for asset in raw:
            if asset in self.external_data:
                raw[asset].update(self.external_data[asset])
            raw[asset] = self.apply_actuators(raw[asset], asset)
        return raw

    def step(self, dt=1.0):
        """Advance the simulation time by dt seconds and auto-recover faults."""
        self.time += dt
        for asset, recover_at in list(self.fault_recovery.items()):
            if self.time >= recover_at:
                self.scenarios[asset] = "normal"
                del self.fault_recovery[asset]

    def set_actuator(self, asset_name, actuator_name, value):
        """Set an actuator command value. Called by the simulation loop when rules fire."""
        if asset_name not in self.actuator_commands:
            self.actuator_commands[asset_name] = {}
        self.actuator_commands[asset_name][actuator_name] = value

    def apply_actuators(self, values, asset_name):
        """Modify sensor values based on active actuator commands.

        This simulates the physical effect of actuators on sensor readings,
        closing the control loop between the expert system and the simulated plant.

        Elevator:
          - speed_controller < 100% reduces vibration and speed_var
          - emergency_brake stops all motion and cools temperature

        Electrical:
          - main_breaker OFF zeros all values
          - load_shedder reduces current by 40%
          - capacitor_bank stabilizes voltage toward 220V

        Water:
          - relief_valve reduces pressure proportionally
          - booster_pump increases pressure and flow
          - inlet_valve increases tank level
        """
        cmds = self.actuator_commands.get(asset_name, {})

        if asset_name == "elevator":
            sc = cmds.get("speed_controller", 100)
            if sc < 100:
                factor = sc / 100.0
                if "vibration" in values:
                    values["vibration"] *= factor
                if "speed_var" in values:
                    values["speed_var"] *= factor
            if cmds.get("emergency_brake", 0) > 0.5:
                values["vibration"] = 0
                values["speed_var"] = 0
                values["temperature"] = max(20, values.get("temperature", 40) - 5)

        elif asset_name == "electrical":
            if cmds.get("main_breaker", 1) < 0.5:
                for k in values:
                    values[k] = 0
                return values
            if cmds.get("load_shedder", 0) > 0.5:
                if "current" in values:
                    values["current"] *= 0.6
            if cmds.get("capacitor_bank", 0) > 0.5:
                if "voltage" in values:
                    values["voltage"] = values["voltage"] * 0.5 + 220 * 0.5

        elif asset_name == "water":
            if cmds.get("bypass_valve", 0) > 0.5:
                if "pressure" in values:
                    values["pressure"] *= 0.7
                if "flow" in values:
                    values["flow"] *= 0.8
            if cmds.get("inlet_valve", 0) > 50:
                factor = cmds["inlet_valve"] / 100.0
                if "flow" in values:
                    values["flow"] = min(100, values["flow"] + 10 * factor)
                if "pressure" in values:
                    values["pressure"] = min(16, values["pressure"] + 2 * factor)
            if cmds.get("alarm", 0) > 0.5:
                if "vibration" in values:
                    values["vibration"] *= 0.9

        elif asset_name == "hvac":
            if cmds.get("compressor", 1) < 0.5:
                if "temp_in" in values:
                    values["temp_in"] = max(30, values["temp_in"] + 5)
                if "rpm" in values:
                    values["rpm"] *= 0.3
            fs = cmds.get("fan_speed", 100)
            if fs < 100:
                factor = fs / 100.0
                if "temp_out" in values:
                    values["temp_out"] = values["temp_out"] * factor + 20 * (1 - factor)
                if "rpm" in values:
                    values["rpm"] *= factor
            if cmds.get("damper", 100) < 100 and "pressure" in values:
                values["pressure"] *= cmds["damper"] / 100.0

        elif asset_name == "fire":
            if cmds.get("sprinkler_valve", 0) > 0.5:
                if "smoke_level" in values:
                    values["smoke_level"] = max(0, values["smoke_level"] * 0.3)
                if "temp_rise" in values:
                    values["temp_rise"] = max(25, values["temp_rise"] * 0.5)
                if "water_pressure" in values:
                    values["water_pressure"] = max(0, values["water_pressure"] - 30)
            if cmds.get("alarm", 0) > 0.5:
                pass
            if cmds.get("fire_pump", 0) > 0.5 and "water_pressure" in values:
                values["water_pressure"] = min(150, values["water_pressure"] + 40)

        elif asset_name == "generator":
            if cmds.get("choke", 0) > 0.5:
                if "rpm" in values:
                    values["rpm"] = max(0, values["rpm"] * 0.1)
                if "voltage" in values:
                    values["voltage"] = max(0, values["voltage"] * 0.1)
            if cmds.get("speed_control", 100) > 50:
                if "rpm" in values:
                    values["rpm"] = max(values["rpm"], 1700)
                if "voltage" in values:
                    values["voltage"] = min(230, values["voltage"] + 20)
            if cmds.get("alarm", 0) < 0.5 and "voltage" in values:
                values["voltage"] = 0

        elif asset_name == "lighting":
            if cmds.get("dimmer", 100) < 100:
                factor = cmds["dimmer"] / 100.0
                if "ambient_light" in values:
                    values["ambient_light"] *= factor
                if "current_draw" in values:
                    values["current_draw"] *= factor
            if cmds.get("circuit_breaker", 1) < 0.5:
                for k in values:
                    values[k] = 0
                return values

        elif asset_name == "access":
            if cmds.get("lock", 0) > 0.5:
                if "door_sensors" in values:
                    values["door_sensors"] = 0
            if cmds.get("alarm", 0) > 0.5:
                pass
            if cmds.get("camera_switch", 0) < 0.5:
                pass

        return values

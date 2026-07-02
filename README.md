# Sistema Experto para Gestión de Activos Críticos con IIoT

Sistema experto basado en lógica difusa (Mamdani) con simulación IIoT, semáforo de 3 estados, PWA offline, mapa georeferenciado, MTBF, auditoría y gestión de usuarios. Desarrollado para la gestión y control de activos críticos en condominios.

**Cliente:** Loyalty Soluciones Inmobiliarias

---

## Arquitectura

```
┌──────────────────────────────────────────────────────────────────┐
│                     Frontend Web (Jinja2 + JS)                    │
│  ┌──────────┐ ┌──────────────┐ ┌───────────┐ ┌───────────────┐  │
│  │Dashboard  │ │ Configuración│ │  Mapa     │ │ Sensor Input  │  │
│  │ (WS en   │ │ (Admin:      │ │ (Leaflet) │ │ (PWA Offline) │  │
│  │  vivo)   │ │  reglas + MF)│ │           │ │               │  │
│  └────┬─────┘ └──────┬───────┘ └─────┬─────┘ └───────┬───────┘  │
│       │              │               │               │          │
│  ┌────┴──────────────┴───────────────┴───────────────┴──────┐   │
│  │              FastAPI + REST API + WebSocket               │   │
│  │  ┌────────────────────────────────────────────────────┐   │   │
│  │  │ Auth (sesión) │ CRUD │ Lógica Difusa │ Explicación│   │   │
│  │  │ MTBF │ Auditoría │ Reportes CSV/HTML │ Jerarquía  │   │   │
│  │  └───────────────────────┬────────────────────────────┘   │   │
│  ├──────────────────────────┴────────────────────────────────┤   │
│  │                     Capa de Datos                          │   │
│  │  ┌────────────────┐  ┌──────────────┐  ┌───────────────┐  │   │
│  │  │ KnowledgeBase  │  │ SQLAlchemy   │  │   SQLite      │  │   │
│  │  │ (CRUD+reglas)  │──│ (ORM 2.0)    │──│ condominium.db│  │   │
│  │  └────────────────┘  └──────────────┘  └───────────────┘  │   │
│  ├────────────────────────────────────────────────────────────┤   │
│  │        Simulador IIoT + Motor de Control Difuso            │   │
│  │  ┌──────────────────────────────────────────────────────┐  │   │
│  │  │  IIoTSimulator (8 activos, 26 sensores)              │  │   │
│  │  │  + Motor Inferencia (scikit-fuzzy)                   │  │   │
│  │  │  + Explanation Engine (lenguaje natural)             │  │   │
│  │  └──────────────────────┬───────────────────────────────┘  │   │
│  │                         │                                  │   │
│  │  Ciclo de control (cada 2s):                               │   │
│  │  Sensor → Reglas Difusas → Diagnóstico → Actuador → Sensor │   │
│  │         ↑                                       │         │   │
│  │         └─────────── Ciclo Cerrado ─────────────┘         │   │
│  └────────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────┘
```

## Módulos del Sistema (8 módulos del documento)

### 1. Gestión de Activos (Jerarquía)
- **Modelo jerárquico:** Condominio → Edificio → Sala de Máquinas → Activo
- 2 condominios, 3 edificios, 4 salas, 8 activos
- CRUD completo vía API y panel de configuración
- Ubicación georeferenciada (lat/lng) por condominio

### 2. Captura Manual de Campo (PWA Offline)
- Aplicación Web Progresiva instalable en el móvil
- Modo offline con cola de IndexedDB
- Sincronización automática al恢复ar conexión
- Entrada numérica y cualitativa (Bajo/Medio/Alto) por términos difusos
- Captura vía sensores del teléfono (acelerómetro, etc.)

### 3. Telemetría y Simulación IIoT
- 8 activos simulados con 26 sensores en total
- 4-6 escenarios por activo (normal + fallas)
- Ruido gaussiano, variación sinusoidal
- Inyección de datos externos (sensor real reemplaza al simulado)
- Endpoint `/api/random-fault` para falla aleatoria

### 4. Sincronización
- Auto-sync de datos offline cuando se restablece la conexión
- WebSocket bidireccional para actualización en vivo del dashboard
- Service Worker con estrategia cache-first para el PWA

### 5. Lógica Difusa
- Motor Mamdani con scikit-fuzzy
- Funciones de membresía: trimf, trapmf, gaussmf
- 5 términos por variable de salida (none, low, medium, high, critical)
- Caché por activo para rendimiento

### 6. Experto de Decisión
- 41 reglas difusas distribuidas en 8 activos
- Operadores AND/OR, pesos configurables
- Acciones sobre actuadores (control en lazo cerrado)
- Semáforo de 3 estados: **Verde** (normal), **Amarillo** (atención), **Rojo** (crítico)

### 7. Visualización y Reportes
- **Dashboard** en vivo con WebSocket, tarjetas, semáforo, charts históricos
- **Mapa** Leaflet.js con marcadores por estado del condominio
- **Ficha técnica** de activo con sensores, reglas, MTBF
- **Reporte HTML** con diseño A4 para imprimir/PDF
- **Exportación CSV** de eventos, lecturas y auditoría
- **Reporte de texto** plano descargable

### 8. Gestión de Usuarios
- 3 roles: `admin` (CRUD completo), `supervisor` (lectura+alertas), `technician` (solo su condominio)
- Autenticación por sesión con hash SHA-256
- Panel de administración: CRUD de usuarios, auditoría, jerarquía
- Restricción de rutas por rol (admin: `/config`, `/admin`)
- Auditoría de acciones: login, escenarios, actuadores, fallas

---

## Activos del Sistema (8)

| Activo | Sala | Sensores | Actuadores | Reglas |
|--------|------|----------|------------|--------|
| **Ascensor** | Sótano | Vibración, Temperatura, Var. Velocidad | Control Velocidad, Freno Emergencia, Bloqueo Puertas | 5 |
| **Sistema Eléctrico** | Cuarto Eléctrico | Voltaje, Corriente, Temp. Rise | Desconexión Cargas, Banco Capacitores, Breaker Principal | 6 |
| **Sistema de Agua** | Sótano | Caudal, Presión, Nivel Tanque | Válvula Alivio, Bomba Presurizadora, Válvula Entrada | 6 |
| **HVAC** | Azotea | Temp. Interior, Temp. Salida, Presión, RPM | Compresor, Velocidad Ventilador, Compuerta Aire | 5 |
| **Contra Incendios** | Azotea | Nivel Humo, Temp. Ambiente, Presión Agua | Válvula Rociadores, Alarma, Bomba Incendio | 5 |
| **Generador** | Planta Baja | Nivel Combustible, RPM Motor, Temp. Refrigerante, Voltaje Salida | Válvula Combustible, Motor Arranque, Transferencia Carga | 5 |
| **Iluminación** | Cuarto Eléctrico | Luz Ambiente, Consumo, Voltaje | Regulador Luz, Breaker Circuito | 4 |
| **Control Acceso** | Planta Baja | Sensores Puertas, Detección Movimiento, Batería | Cerradura Electrónica, Alarma Perimetral, Cámaras Seguridad | 5 |

**Total:** 26 sensores, 23 actuadores, 41 reglas

---

## Jerarquía de Instalaciones

```
Los Olivos (Av. Principal 123) ◎ -12.046, -77.043
├── Edificio Principal
│   ├── 🏭 Sótano → Ascensor, Agua
│   └── ⚡ Cuarto Eléctrico → Eléctrico, Iluminación
└── Edificio Secundario
    └── 🏗️ Azotea → HVAC, Contra Incendios

Vista Alegre (Jr. Las Flores 456) ◎ -12.120, -77.030
└── Torre A
    └── 🏗️ Planta Baja → Generador, Control Acceso
```

---

## Semáforo de 3 Estados

| Estado | Rango | Color | Significado |
|--------|-------|-------|-------------|
| **Verde** (low) | 0-29 | 🟢 | Normal, sin intervención requerida |
| **Amarillo** (medium) | 30-59 | 🟡 | Atención, monitorear |
| **Rojo** (high) | 60-100 | 🔴 | Crítico, intervención inmediata |

---

## Requisitos

- **Python 3.13+** (probado en 3.13)
- Windows, Linux, o macOS
- Navegador moderno para PWA (Chrome, Edge, Safari)

### Dependencias

```txt
fastapi>=0.115
uvicorn>=0.30
sqlalchemy>=2.0
scikit-fuzzy>=0.5
python-multipart>=0.0
jinja2>=3.1
numpy>=1.26
aiofiles>=24.1
```

---

## Instalación y Ejecución

```bash
# 1. Clonar
git clone https://github.com/Caxtillo/sistema-experto.git
cd sistema-experto/condominium_expert

# 2. Instalar dependencias
pip install -r requirements.txt

# 3. Iniciar servidor
python3.13 -m uvicorn app:app --host 0.0.0.0 --port 8000 --reload

# O en Windows:
start.bat
```

El servidor inicia en **http://localhost:8000**

### Usuarios por Defecto

| Usuario | Contraseña | Rol | Acceso |
|---------|-----------|-----|--------|
| `admin` | `admin123` | Administrador | Todas las rutas, incluyendo `/config` y `/admin` |
| `supervisor` | `super123` | Supervisor | Dashboard, Mapa, Reportes, Ficha Técnica |
| `tecnico` | `tec123` | Técnico | Dashboard, Sensor Input (asignado a Los Olivos) |

### Primer Inicio

Al iniciar el servidor por primera vez, la base de datos se crea y se puebla automáticamente con:
- 2 condominios, 3 edificios, 4 salas de máquinas
- 8 activos con 26 sensores, 23 actuadores, 41 reglas
- 3 usuarios (admin, supervisor, tecnico)

---

## Páginas Web

| Ruta | Descripción | Acceso |
|------|-------------|--------|
| `/login` | Inicio de sesión | Público |
| `/` | Dashboard con monitoreo en vivo (WebSocket) | Autenticado |
| `/config` | Configuración de reglas, sensores y membresías | Admin |
| `/sensor-input` | Captura manual de datos (PWA offline) | Autenticado |
| `/map` | Mapa georeferenciado con Leaflet.js | Autenticado |
| `/asset?id=N` | Ficha técnica del activo | Autenticado |
| `/reports` | Reportes exportables (HTML/CSV) | Autenticado |
| `/admin` | Panel de administración (usuarios, auditoría, jerarquía) | Admin |

---

## API REST Completa

### Datos en Vivo
| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | `/api/data` | Estado completo de todos los activos (score, sensores, actuadores, reglas activas) |
| GET | `/api/events` | Eventos de transición de estado (últimos 50) |
| GET | `/api/history/{asset}` | Historial de scores y valores de sensores |
| GET | `/api/sensor-readings/{asset}/{sensor}` | Lecturas históricas de un sensor |
| WS | `/ws` | WebSocket para actualización en vivo del dashboard |

### Control y Simulación
| Método | Ruta | Descripción |
|--------|------|-------------|
| POST | `/api/scenario/{asset}?scenario=X` | Activar escenario de falla |
| POST | `/api/random-fault` | Falla aleatoria con auto-recuperación |
| GET | `/api/scenarios/{asset}` | Listar escenarios disponibles |
| POST | `/api/sensor-data` | Recibir dato de sensor externo/phone |
| POST | `/api/actuator/{id}/command` | Comando manual de actuador |
| GET | `/api/reset` | Resetear todos los escenarios a normal |
| GET | `/api/debug` | Información de depuración (sim_time, escenarios) |

### Jerarquía y MTBF
| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | `/api/hierarchy` | Árbol completo: condominios → edificios → salas → activos con estados |
| GET | `/api/mtbf/{asset_id}` | MTBF (Mean Time Between Failures) para un activo |
| GET | `/api/assets` | Listar todos los activos |
| GET | `/api/assets/{id}` | Detalle del activo con sensores y reglas |
| GET | `/api/explain/{asset}` | Explicación detallada del diagnóstico en lenguaje natural |

### CRUD de Activos
| Método | Ruta | Descripción |
|--------|------|-------------|
| POST | `/api/assets` | Crear activo |
| PUT | `/api/assets/{id}` | Actualizar activo |
| DELETE | `/api/assets/{id}` | Eliminar activo |
| POST | `/api/assets/{id}/sensors` | Agregar sensor |
| PUT | `/api/sensors/{id}` | Actualizar sensor |
| DELETE | `/api/sensors/{id}` | Eliminar sensor |
| POST | `/api/assets/{id}/rules` | Agregar regla difusa |
| PUT | `/api/rules/{id}` | Actualizar regla |
| DELETE | `/api/rules/{id}` | Eliminar regla |
| POST | `/api/sensor-type/{id}` | Cambiar tipo de sensor (simulated/external/phone) |
| GET | `/api/sensor-types?asset_name=X` | Obtener configuración de sensores |

### Reportes
| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | `/api/report` | Reporte de texto plano con resumen, MTBF, eventos y auditoría |
| GET | `/api/report/html` | Reporte HTML con diseño A4 para imprimir/PDF |
| GET | `/api/report/csv/events?limit=N` | Exportar eventos como CSV |
| GET | `/api/report/csv/readings?asset_name=X&limit=N` | Exportar lecturas como CSV |
| GET | `/api/report/csv/audit?limit=N` | Exportar auditoría como CSV |

### Administración (Admin)
| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | `/api/admin/users` | Listar usuarios |
| POST | `/api/admin/users` | Crear usuario |
| PUT | `/api/admin/users/{id}` | Actualizar usuario |
| DELETE | `/api/admin/users/{id}` | Eliminar usuario |
| GET | `/api/audit?limit=N` | Registros de auditoría |

---

## Estructura del Proyecto

```
condominium_expert/
├── app.py                        # Punto de entrada FastAPI + rutas web
├── requirements.txt              # Dependencias Python
├── start.bat                     # Lanzador Windows
├── PLAN.md                       # Seguimiento de fases del proyecto
│
├── core/
│   ├── inference_engine.py       # Motor de inferencia difusa Mamdani
│   ├── knowledge_base.py         # Capa de acceso a datos (CRUD completo)
│   └── explanation.py            # Generador de explicaciones en lenguaje natural
│
├── web/
│   ├── api.py                    # Endpoints REST + simulación + reportes
│   └── templates/
│       ├── base.html             # Layout base con nav, drawer de simulación
│       ├── login.html            # Página de inicio de sesión
│       ├── dashboard.html        # Dashboard con WebSocket en vivo
│       ├── config.html           # Editor de reglas, sensores, MF
│       ├── sensor_input.html     # PWA offline con IndexedDB
│       ├── map.html              # Mapa Leaflet.js georeferenciado
│       ├── asset.html            # Ficha técnica del activo
│       ├── reports.html          # Página de reportes exportables
│       └── admin.html            # Panel de administración
│
├── models/
│   └── models.py                 # Modelos SQLAlchemy (12 tablas)
│
├── storage/
│   └── database.py               # Conexión SQLite + init_db()
│
├── iiot_simulator/
│   └── sensors.py                # Simulador IIoT (8 activos, 26 sensores)
│
├── scripts/
│   └── seed.py                   # Poblado inicial de la BD
│
├── tests/
│   └── test_inference.py         # Pruebas del motor de inferencia
│
├── static/
│   ├── style.css                 # Estilos legacy
│   ├── manifest.json             # PWA manifest
│   ├── service-worker.js         # Service Worker para PWA
│   └── sensor-icon.svg           # Icono para PWA
│
└── data/
    └── condominium.db            # Base de datos SQLite (auto-creada)
```

## Modelo de Datos (12 tablas)

| Tabla | Descripción |
|-------|-------------|
| `condominiums` | Condominios con coordenadas geográficas |
| `buildings` | Edificios dentro de cada condominio |
| `machine_rooms` | Salas de máquinas dentro de cada edificio |
| `assets` | Activos críticos con ubicación en sala |
| `sensor_configs` | Configuración de sensores con MF difusas |
| `actuators` | Actuadores con comando y modo automático |
| `rules` | Reglas difusas con antecedentes, consecuente, acción |
| `events` | Eventos de transición de estado |
| `sensor_readings` | Lecturas históricas de sensores |
| `users` | Usuarios con roles y hash de contraseña |
| `audit_logs` | Registro de auditoría de acciones |

---

## Personalización

### Agregar un Nuevo Activo

1. **Crear el activo:** `POST /api/assets` con nombre, label, rango de salida
2. **Agregar sensores:** `POST /api/assets/{id}/sensors` con funciones de membresía
3. **Agregar actuadores:** Directamente en la DB o por API
4. **Agregar reglas:** `POST /api/assets/{id}/rules` con antecedentes y consecuente
5. **Opcional:** Agregar escenarios de falla en `iiot_simulator/sensors.py`
6. **Opcional:** Asignar ubicación en la jerarquía actualizando `location_id`

### Conectar Sensores Reales

```bash
# Configurar el sensor como tipo "external" en /config
# Luego enviar datos vía POST:
curl -X POST http://localhost:8000/api/sensor-data \
  -H "Content-Type: application/json" \
  -d '{"asset": "elevator", "sensor": "vibration", "value": 3.5}'
```

El sistema ignora los datos simulados para ese sensor mientras reciba datos externos.

---

## Tecnologías

- **Backend:** Python 3.13, FastAPI, Uvicorn, SQLAlchemy 2.0, SQLite
- **Lógica Difusa:** scikit-fuzzy (Mamdani), numpy
- **Frontend:** Jinja2, HTML5, CSS3, JavaScript vanilla, Chart.js, Leaflet.js
- **PWA:** Service Worker, IndexedDB, Web App Manifest
- **Tiempo Real:** WebSocket (bidireccional)
- **Autenticación:** Starlette SessionMiddleware, SHA-256

---

## Pruebas

```bash
cd condominium_expert
python3.13 -m pytest tests/ -v
```

---

## Licencia

Proyecto académico — Loyalty Soluciones Inmobiliarias

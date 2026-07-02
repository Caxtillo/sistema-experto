# SISTEMA EXPERTO - GESTIÓN DE ACTIVOS CRÍTICOS

## Documentación Completa para el Cliente

### Loyalty Soluciones Inmobiliarias — Julio 2026

---

## ÍNDICE

1. [Resumen Ejecutivo](#1-resumen-ejecutivo)
2. [Arquitectura del Sistema](#2-arquitectura-del-sistema)
3. [Los 8 Módulos del Sistema](#3-los-8-módulos-del-sistema)
4. [Jerarquía de Instalaciones](#4-jerarquía-de-instalaciones)
5. [Semáforo de 3 Estados](#5-semáforo-de-3-estados)
6. [Activos Monitoreados](#6-activos-monitoreados)
7. [Usuarios y Roles](#7-usuarios-y-roles)
8. [API REST Completa](#8-api-rest-completa)
9. [Páginas Web](#9-páginas-web)
10. [PWA Offline (Aplicación Móvil)](#10-pwa-offline)
11. [Mapa Georeferenciado](#11-mapa-georeferenciado)
12. [Reportes Exportables](#12-reportes-exportables)
13. [Modelo de Base de Datos](#13-modelo-de-base-de-datos)
14. [Tecnologías Utilizadas](#14-tecnologías-utilizadas)
15. [Instalación y Ejecución](#15-instalación-y-ejecución)
16. [Estructura del Proyecto](#16-estructura-del-proyecto)
17. [Personalización](#17-personalización)
18. [Pruebas](#18-pruebas)
19. [Seguridad](#19-seguridad)
20. [Despliegue a Producción](#20-despliegue-a-producción)
21. [Repositorio GitHub](#21-repositorio-github)

---

## 1. Resumen Ejecutivo

Sistema experto basado en **lógica difusa (Mamdani)** con simulación **IIoT**, diseñado para la gestión y control de **activos críticos en condominios**. El sistema monitorea 8 activos a través de 26 sensores simulados, aplica 41 reglas difusas para diagnóstico, y genera alertas mediante un **semáforo de 3 estados** (Verde/Amarillo/Rojo).

**Características principales:**
- Monitoreo en **tiempo real** vía WebSocket
- **PWA offline** instalable en el móvil del técnico
- **Mapa georeferenciado** con Leaflet.js
- **3 roles de usuario** (admin, supervisor, técnico)
- **Cálculo de MTBF** para cada activo
- **Auditoría completa** de todas las acciones
- **Reportes exportables** (HTML imprimible, CSV, texto plano)
- **Simulación IIoT** con 4-6 escenarios por activo
- **Panel de administración** con CRUD de usuarios

---

## 2. Arquitectura del Sistema

```
┌──────────────────────────────────────────────────────────────────────────┐
│                         Frontend Web (Jinja2 + JS)                        │
│  ┌───────────┐  ┌──────────────┐  ┌──────────┐  ┌────────────────┐      │
│  │ Dashboard  │  │Configuración │  │   Mapa   │  │  Sensor Input  │      │
│  │ (WS vivo)  │  │(reglas + MF) │  │(Leaflet) │  │ (PWA Offline)  │      │
│  └─────┬─────┘  └──────┬───────┘  └────┬─────┘  └───────┬────────┘      │
│        │               │               │                │               │
│  ┌─────┴───────────────┴───────────────┴────────────────┴───────────┐   │
│  │                   FastAPI + REST API + WebSocket                   │   │
│  │  ┌────────────────────────────────────────────────────────────┐   │   │
│  │  │ Auth │ CRUD │ Lógica Difusa │ Explicación │ MTBF          │   │   │
│  │  │ Auditoría │ Reportes CSV/HTML │ Jerarquía │ Admin Panel    │   │   │
│  │  └──────────────────────┬─────────────────────────────────────┘   │   │
│  ├─────────────────────────┴─────────────────────────────────────────┤   │
│  │                       Capa de Datos                                │   │
│  │  ┌────────────────┐  ┌────────────────┐  ┌────────────────────┐   │   │
│  │  │ KnowledgeBase  │  │  SQLAlchemy    │  │  SQLite            │   │   │
│  │  │ (CRUD + reglas)│──│ (ORM 2.0)      │──│ condominium.db     │   │   │
│  │  └────────────────┘  └────────────────┘  └────────────────────┘   │   │
│  ├────────────────────────────────────────────────────────────────────┤   │
│  │          Simulador IIoT + Motor de Control Difuso                   │   │
│  │  ┌──────────────────────────────────────────────────────────────┐  │   │
│  │  │  IIoTSimulator (8 activos, 26 sensores, 23 actuadores)       │  │   │
│  │  │  + Motor Inferencia Mamdani (scikit-fuzzy)                   │  │   │
│  │  │  + Explanation Engine (lenguaje natural)                     │  │   │
│  │  └────────────────────────┬─────────────────────────────────────┘  │   │
│  │                           │                                        │   │
│  │  Ciclo de control (cada 2s):                                       │   │
│  │  Sensor → Reglas Difusas → Diagnóstico → Actuador → Sensor         │   │
│  │         ↑                                             │            │   │
│  │         └─────────── Ciclo Cerrado ───────────────────┘            │   │
│  └────────────────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────────────┘
```

### Flujo de Datos

1. **Simulador IIoT** genera lecturas de sensores cada 2 segundos
2. **Motor de Inferencia** evalúa las 41 reglas difusas con las lecturas actuales
3. **Diagnóstico**: asigna un score (0-100) y estado (low/medium/high)
4. **Actuadores**: las reglas activas con fuerza >0.5 envían comandos a actuadores
5. **Actuadores** modifican el comportamiento físico simulado (lazo cerrado)
6. **WebSocket** transmite el estado completo a todos los dashboards conectados
7. **Datos externos** (técnico en campo o sensor real) reemplazan valores simulados

---

## 3. Los 8 Módulos del Sistema

### Módulo 1: Gestión de Activos (Jerarquía)
- Modelo jerárquico de 4 niveles: **Condominio → Edificio → Sala de Máquinas → Activo**
- 2 condominios, 3 edificios, 4 salas, 8 activos pre-cargados
- CRUD completo vía API REST
- Ubicación georeferenciada (lat/lng) por condominio
- Cada activo pertenece a una sala de máquinas específica

### Módulo 2: Captura Manual de Campo (PWA Offline)
- **Aplicación Web Progresiva** instalable en el móvil del técnico
- Funciona sin internet con **IndexedDB** para almacenamiento local
- Sincronización automática al recuperar conexión
- Dos modos de entrada: **numérico** (valor exacto) y **cualitativo** (Bajo/Medio/Alto)
- Captura vía **sensores del teléfono** (acelerómetro/giroscopio)
- Interfaz optimizada para uso móvil (standalone, portrait)

### Módulo 3: Telemetría y Simulación IIoT
- 8 activos simulados con **26 sensores** en total
- Cada activo tiene 4-6 escenarios (normal + fallas)
- Ruido gaussiano y variación sinusoidal para realismo
- Modos de sensor: **simulated**, **external**, **phone**
- Inyección de datos externos: `POST /api/sensor-data`
- Falla aleatoria con auto-recuperación (~15s): `POST /api/random-fault`

### Módulo 4: Sincronización
- **Auto-sync** de datos offline cuando se restablece la conexión
- **WebSocket bidireccional** para actualización en vivo del dashboard
- **Service Worker** con estrategia cache-first para el PWA
- Cola de IndexedDB con reintento automático

### Módulo 5: Lógica Difusa
- Motor **Mamdani** con librería scikit-fuzzy
- Funciones de membresía: `trimf`, `trapmf`, `gaussmf`
- 5 términos por variable de salida: none, low, medium, high, critical
- Caché por activo para rendimiento (se invalida al cambiar reglas/sensores)
- Defuzzificación por centro de gravedad

### Módulo 6: Experto de Decisión
- **41 reglas difusas** distribuidas en 8 activos (4-6 reglas cada uno)
- Operadores **AND/OR**, pesos configurables (0-1)
- Acciones sobre **actuadores** con umbral de activación (fire_strength > 0.5)
- **Semáforo de 3 estados**: Verde (normal), Amarillo (atención), Rojo (crítico)
- **Explicación en lenguaje natural** del diagnóstico

### Módulo 7: Visualización y Reportes
- **Dashboard** en vivo con WebSocket, tarjetas de activos, semáforo, mini charts de historial (60 puntos), panel de eventos
- **Mapa** Leaflet.js con marcadores circulares de colores por estado del condominio
- **Ficha técnica** de activo con sensores, reglas, MTBF, recomendaciones
- **Reporte HTML** con diseño A4 profesional para imprimir/guardar como PDF
- **Exportación CSV** de eventos, lecturas de sensores y auditoría
- **Reporte de texto** plano con resumen completo

### Módulo 8: Gestión de Usuarios
- **3 roles**: admin (CRUD completo), supervisor (lectura+alertas), technician (solo su condominio)
- **Autenticación por sesión** con hash SHA-256
- **Panel de administración** en 3 pestañas: Usuarios (CRUD), Auditoría (filtrable), Jerarquía
- Restricción de rutas web por rol (admin: `/config`, `/admin`)
- **Auditoría** de todas las acciones: login, cambios de escenario, comandos de actuadores, fallas aleatorias

---

## 4. Jerarquía de Instalaciones

```
Los Olivos (Av. Principal 123) ◎ -12.046, -77.043
│
├── Edificio Principal
│   ├── 🏭 Sótano
│   │   ├── Ascensor (Ascensor)
│   │   └── Sistema de Agua (Bombeo)
│   │
│   └── ⚡ Cuarto Eléctrico
│       ├── Sistema Eléctrico (Transformador, tableros)
│       └── Iluminación (Sistema de iluminación general)
│
└── Edificio Secundario
│    └── 🏗️ Azotea
│        ├── HVAC (Climatización)
│        └── Sistema Contra Incendios (Detección y extinción)
│
Vista Alegre (Jr. Las Flores 456) ◎ -12.120, -77.030
│
└── Torre A
    └── 🏗️ Planta Baja
        ├── Generador Eléctrico (Emergencia)
        └── Control de Acceso (Seguridad perimetral)
```

---

## 5. Semáforo de 3 Estados

El sistema implementa un semáforo de **3 estados** basado en el score difuso (0-100):

| Estado | Color | Rango | Significado | Acción Requerida |
|--------|-------|-------|-------------|-------------------|
| **Verde** (low) | 🟢 | 0-29 | Normal | Ninguna, monitoreo rutinario |
| **Amarillo** (medium) | 🟡 | 30-59 | Atención | Monitorear, programar mantenimiento preventivo |
| **Rojo** (high) | 🔴 | 60-100 | Crítico | Intervención inmediata, acción correctiva |

### Transiciones
- De Verde a Amarillo → evento tipo "info", score sube a 30+
- De Amarillo a Rojo → evento tipo "warning", score sube a 60+
- De Rojo a Amarillo o Verde → evento tipo "info", mejora
- Cada transición se guarda en la tabla `events` y se muestra en el dashboard

### Alertas
- **Modal**: aparece cuando un activo pasa a Rojo (cooldown de 5 segundos)
- **Toast**: notificación en esquina superior derecha con color según gravedad
- **Sonido**: tono de alerta configurable (muteable desde el botón 🔇)
- **Dashboard**: borde rojo pulsante en tarjetas de activos en estado crítico

---

## 6. Activos Monitoreados

El sistema incluye **8 activos críticos** preconfigurados con sensores, actuadores y reglas:

| # | Activo | Sala | Nombre API | Sensores | Actuadores | Reglas |
|---|--------|------|-----------|----------|------------|--------|
| 1 | **Ascensor** | Sótano | `elevator` | Vibración, Temperatura, Var. Velocidad | Control Velocidad, Freno Emergencia, Bloqueo Puertas | 5 |
| 2 | **Sistema Eléctrico** | Cuarto Eléctrico | `electrical` | Voltaje, Corriente, Temp. Rise | Desconexión Cargas, Banco Capacitores, Breaker Principal | 6 |
| 3 | **Sistema de Agua** | Sótano | `water` | Caudal, Presión, Nivel Tanque | Válvula Alivio, Bomba Presurizadora, Válvula Entrada | 6 |
| 4 | **HVAC** | Azotea | `hvac` | Temp. Interior, Temp. Salida, Presión, RPM | Compresor, Velocidad Ventilador, Compuerta Aire | 5 |
| 5 | **Contra Incendios** | Azotea | `fire` | Nivel Humo, Temp. Ambiente, Presión Agua | Válvula Rociadores, Alarma, Bomba Incendio | 5 |
| 6 | **Generador** | Planta Baja | `generator` | Nivel Combustible, RPM Motor, Temp. Refrigerante, Voltaje Salida | Válvula Combustible, Motor Arranque, Transferencia Carga | 5 |
| 7 | **Iluminación** | Cuarto Eléctrico | `lighting` | Luz Ambiente, Consumo, Voltaje | Regulador Luz, Breaker Circuito | 4 |
| 8 | **Control Acceso** | Planta Baja | `access` | Sensores Puertas, Detección Movimiento, Batería | Cerradura Electrónica, Alarma Perimetral, Cámaras Seguridad | 5 |

**Totales:** 26 sensores, 23 actuadores, 41 reglas

### Escenarios de Falla por Activo

Cada activo tiene escenarios predefinidos que simulan condiciones anormales:

| Activo | Escenarios de Falla |
|--------|---------------------|
| Ascensor | Desgaste de Poleas, Sobrecalentamiento, Falla de Motor |
| Sistema Eléctrico | Sobrecarga Eléctrica, Riesgo de Cortocircuito, Bajo Voltaje |
| Agua | Fuga en Tubería, Bomba Dañada, Tanque Vacío |
| HVAC | Sobrecarga HVAC, Fuga de Refrigerante, Falla de Compresor |
| Contra Incendios | Detección de Humo, Principio de Incendio, Alarma Total |
| Generador | Bajo Combustible, Sobrecalentamiento, Falla de Arranque |
| Iluminación | Sobrecarga Iluminación, Falla Transformador |
| Control Acceso | Intrusión Detectada, Batería Baja, Falla del Sistema |

### Efecto de los Actuadores (Lazo Cerrado)

Cuando una regla se activa con fire_strength > 0.5, el sistema ejecuta la acción del actuador, que modifica el comportamiento físico simulado:

| Activo | Actuador | Efecto |
|--------|----------|--------|
| Ascensor | speed_controller | Reduce vibración y variación de velocidad |
| Ascensor | emergency_brake | Detiene todo, enfría motor |
| Eléctrico | main_breaker | Corta todo el suministro (valores a 0) |
| Eléctrico | load_shedder | Reduce corriente en 40% |
| Eléctrico | capacitor_bank | Estabiliza voltaje hacia 220V |
| Agua | relief_valve | Reduce presión proporcionalmente |
| Agua | booster_pump | Aumenta presión y caudal en +20 |
| Agua | inlet_valve | Aumenta nivel de tanque en +5 |
| HVAC | compressor | Apagar compresor eleva temp interior |
| HVAC | fan_speed | Reduce RPM y temp de salida |
| HVAC | damper | Reduce presión |
| Fuego | sprinkler_valve | Reduce humo y temperatura |
| Fuego | fire_pump | Aumenta presión de agua |
| Generador | fuel_valve | Corta RPM y voltaje |
| Generador | starter | Arranca motor (RPM >1700) |
| Generador | load_transfer | Corta voltaje de salida |
| Iluminación | dimmer | Reduce luz ambiente y consumo |
| Iluminación | circuit_breaker | Corta todo |
| Acceso | lock | Cierra puertas |
| Acceso | alarm | Activa alerta (sin efecto físico) |
| Acceso | camera_switch | Sin efecto físico |

---

## 7. Usuarios y Roles

### Credenciales por Defecto

| Usuario | Contraseña | Rol | Acceso a Condominio |
|---------|-----------|-----|---------------------|
| `admin` | `admin123` | Administrador | Todos (sin restricción) |
| `supervisor` | `super123` | Supervisor | Todos (sin restricción) |
| `tecnico` | `tec123` | Técnico | Solo Los Olivos (condominium_id=1) |

### Permisos por Rol

| Funcionalidad | admin | supervisor | technician |
|--------------|-------|------------|------------|
| Dashboard (/) | ✅ | ✅ | ✅ |
| Sensor Input | ✅ | ✅ | ✅ |
| Mapa | ✅ | ✅ | ✅ |
| Ficha Técnica | ✅ | ✅ | ✅ |
| Reportes | ✅ | ✅ | ✅ |
| Configuración (/config) | ✅ | ❌ Redirige a / | ❌ Redirige a / |
| Admin Panel (/admin) | ✅ | ❌ Redirige a / | ❌ Redirige a / |
| API CRUD usuarios | ✅ | ❌ | ❌ |
| API CRUD activos/reglas | ✅ | ✅ | ✅ |
| API escenarios/fallas | ✅ | ✅ | ✅ |

### Creación de Usuarios

Solo el admin puede crear usuarios desde el panel `/admin` o vía API:
```http
POST /api/admin/users
Content-Type: application/json

{
  "username": "nuevo_usuario",
  "password": "contraseña123",
  "role": "technician",
  "condominium_id": 1
}
```

---

## 8. API REST Completa

### 8.1 Datos en Vivo

| Método | Ruta | Descripción | Response |
|--------|------|-------------|----------|
| `GET` | `/api/data` | Estado completo de todos los activos | JSON con score, status, sensores, actuadores, reglas activas, recomendaciones, explicación, escenarios |
| `GET` | `/api/events` | Últimos 50 eventos de transición | Array con time, asset, from, to, score, type |
| `GET` | `/api/actions` | Últimas acciones de actuadores | Array con time, asset, rule, actuator, value, fire_strength |
| `GET` | `/api/history/{asset}` | Historial de scores (últimos 60) | Array con time, score, sensors |
| `GET` | `/api/sensor-readings/{asset}/{sensor}?limit=60` | Lecturas históricas de un sensor | Array con time, value, score |
| `WS` | `/ws` | WebSocket bidireccional | Stream JSON con estado completo cada 2s |

**Ejemplo GET /api/data:**
```json
{
  "elevator": {
    "id": 1,
    "name": "Ascensor",
    "sensors": {"vibration": 1.2, "temperature": 25.3, "speed_var": 0.8},
    "sensor_types": {"vibration": "simulated", "temperature": "simulated", "speed_var": "simulated"},
    "sensors_meta": {"vibration": {"label": "Vibración", "unit": "mm/s", "min": 0, "max": 10, "sensor_type": "simulated"}},
    "actuators": [{"id": 1, "name": "speed_controller", "label": "Control Velocidad", "value": 100, "state": true, "auto": true}],
    "score": 12.5,
    "status": "low",
    "rules": [{"id": "R4", "name": "R4", "fire_strength": 0.85, "description": "..."}],
    "recommendations": ["Mantenimiento rutinario mensual"],
    "explanation": "El diagnóstico indica condición normal...",
    "scenarios": [{"id": "normal", "label": "Normal", "icon": "circle"}],
    "current_scenario": "normal"
  }
}
```

### 8.2 Control y Simulación

| Método | Ruta | Descripción |
|--------|------|-------------|
| `POST` | `/api/scenario/{asset}?scenario=X` | Activar escenario de falla para un activo |
| `POST` | `/api/random-fault` | Falla aleatoria con auto-recuperación en ~15s |
| `GET` | `/api/scenarios/{asset}` | Listar escenarios disponibles para un activo |
| `POST` | `/api/sensor-data` | Recibir dato de sensor externo o teléfono |
| `POST` | `/api/actuator/{id}/command` | Comando manual de actuador (override automático) |
| `GET` | `/api/reset` | Resetear todos los escenarios a normal y limpiar BD |
| `GET` | `/api/debug` | Información de depuración (sim_time, escenarios, ciclos) |

**POST /api/scenario/elevator?scenario=falla_motor:**
```json
{"asset": "elevator", "scenario": "falla_motor", "label": "Falla de Motor"}
```

**POST /api/sensor-data:**
```json
{"asset": "elevator", "sensor": "vibration", "value": 3.5}
```

### 8.3 Jerarquía y MTBF

| Método | Ruta | Descripción |
|--------|------|-------------|
| `GET` | `/api/hierarchy` | Árbol completo: condominios → edificios → salas → activos con estados |
| `GET` | `/api/mtbf/{asset_id}` | MTBF (Mean Time Between Failures) en horas |
| `GET` | `/api/assets` | Listar todos los activos (id, name, label, icon) |
| `GET` | `/api/assets/{id}` | Detalle del activo con sensores y reglas |
| `GET` | `/api/explain/{asset}` | Explicación detallada en lenguaje natural |

**GET /api/hierarchy:**
```json
[
  {
    "id": 1, "name": "Los Olivos", "address": "Av. Principal 123",
    "lat": -12.046, "lng": -77.043,
    "buildings": [{
      "id": 1, "name": "Edificio Principal",
      "rooms": [{
        "id": 1, "name": "Sótano",
        "assets": [{"id": 1, "name": "elevator", "label": "Ascensor", "score": 12.5, "status": "low"}],
        "worst_score": 12.5, "worst_status": "low"
      }]
    }],
    "worst_status": "low"
  }
]
```

**GET /api/mtbf/1:**
```json
{"asset_id": 1, "asset_name": "Ascensor", "mtbf_hours": 720.0, "failure_count": 0, "status": "healthy"}
```

**GET /api/explain/elevator:**
```json
{
  "asset": "Ascensor",
  "score": 12.5,
  "status": "low",
  "total_rules": 5,
  "active_rules_count": 1,
  "top_rules": [{"id": "R4", "name": "R4", "fire_strength": 0.85}],
  "membership_detail": [
    {"sensor": "vibration", "sensor_label": "Vibración", "value": 1.2, "term": "low", "degree": 0.7}
  ],
  "summary": "El diagnóstico indica condición normal con monitoreo de rutina..."
}
```

### 8.4 CRUD de Activos, Sensores y Reglas

| Método | Ruta | Descripción |
|--------|------|-------------|
| `POST` | `/api/assets` | Crear nuevo activo |
| `PUT` | `/api/assets/{id}` | Actualizar activo |
| `DELETE` | `/api/assets/{id}` | Eliminar activo (cascade: sensores, reglas, eventos) |
| `POST` | `/api/assets/{id}/sensors` | Agregar sensor a un activo |
| `PUT` | `/api/sensors/{id}` | Actualizar sensor |
| `DELETE` | `/api/sensors/{id}` | Eliminar sensor |
| `POST` | `/api/assets/{id}/rules` | Agregar regla difusa |
| `PUT` | `/api/rules/{id}` | Actualizar regla |
| `DELETE` | `/api/rules/{id}` | Eliminar regla |
| `POST` | `/api/sensor-type/{id}` | Cambiar tipo de sensor (simulated/external/phone) |
| `GET` | `/api/sensor-types?asset_name=X` | Obtener configuración de sensores |

### 8.5 Reportes

| Método | Ruta | Descripción |
|--------|------|-------------|
| `GET` | `/api/report` | Reporte de texto plano con resumen completo |
| `GET` | `/api/report/html` | Reporte HTML con diseño A4 para imprimir/PDF |
| `GET` | `/api/report/csv/events?limit=500` | Exportar eventos como CSV |
| `GET` | `/api/report/csv/readings?asset_name=X&limit=500` | Exportar lecturas como CSV |
| `GET` | `/api/report/csv/audit?limit=500` | Exportar registros de auditoría como CSV |

### 8.6 Administración (Solo Admin)

| Método | Ruta | Descripción |
|--------|------|-------------|
| `GET` | `/api/admin/users` | Listar todos los usuarios |
| `POST` | `/api/admin/users` | Crear nuevo usuario |
| `PUT` | `/api/admin/users/{id}` | Actualizar usuario (username, password, role, condominium_id) |
| `DELETE` | `/api/admin/users/{id}` | Eliminar usuario |
| `GET` | `/api/audit?limit=100` | Registros de auditoría |

---

## 9. Páginas Web

### 9.1 Login (`/login`)
- Interfaz oscura minimalista
- Formulario con usuario y contraseña
- Hint con credenciales por defecto
- Redirección a dashboard si ya autenticado

### 9.2 Dashboard (`/`)
- **WebSocket** en vivo para actualización cada 2 segundos
- **Tarjetas de activos** con score, semáforo (borde coloreado), sensores, actuadores
- **Gráfico de score** histórico (Chart.js, últimos 60 puntos)
- **Panel de eventos** con lista de transiciones de estado
- **Modal de alerta** cuando un activo pasa a Rojo (cooldown 5s)
- **Toast notifications** para cambios de estado
- **Drawer de simulación** para cambiar escenarios desde el dashboard
- **Conexión WebSocket**: indicador de estado

### 9.3 Configuración (`/config`) — Solo Admin
- Editor de **reglas difusas** por activo
- Editor de **sensores** (MF, rangos, tipo)
- Editor de **funciones de membresía** (trimf, trapmf, gaussmf)
- Gestión de actuadores (modo automático/manual)

### 9.4 Sensor Input (`/sensor-input`) — PWA Offline
- **PWA instalable**: manifest.json, service-worker, icono SVG
- **Modo offline**: cola de IndexedDB con auto-sync
- **Entrada numérica**: slider + input manual por sensor
- **Entrada cualitativa**: dropdown Bajo/Medio/Alto (mapeo a centroides difusos)
- **Captura por sensor del teléfono**: acelerómetro con fallback a giroscopio
- **Botón de envío**: envía datos al servidor, encola si offline

### 9.5 Mapa (`/map`)
- **Leaflet.js** con OpenStreetMap
- **Marcadores circulares** por condominio (color = peor estado de activos)
- **Popup jerárquico**: Edificio → Sala → Activo con scores y colores
- Vista centrada en coordenadas de los condominios

### 9.6 Ficha Técnica (`/asset?id=N`)
- Dropdown para seleccionar activo
- Información del activo: nombre, descripción, ubicación en jerarquía
- **Sensores**: tabla con nombre, label, unidad, rango, MF config
- **Reglas**: tabla con antecedentes, consecuente, peso, estado
- **MTBF**: horas entre fallos, conteo de fallos, estado (healthy/watch)
- **Recomendaciones** según estado actual

### 9.7 Reportes (`/reports`)
- **Tarjetas** de descarga: Reporte Texto, Reporte HTML, CSV Eventos, CSV Lecturas, CSV Auditoría
- **Selector de activo** para filtrar lecturas CSV
- **Vista previa** del reporte HTML en iframe
- Diseño responsive para escritorio y móvil

### 9.8 Admin Panel (`/admin`) — Solo Admin
- **Pestaña Usuarios**: tabla CRUD con modal de creación/edición
- **Pestaña Auditoría**: tabla filtrable con acciones, usuarios, fechas
- **Pestaña Jerarquía**: árbol visual de condominios, edificios, salas, activos

---

## 10. PWA Offline

### Instalación
1. Abrir `/sensor-input` en Chrome/Edge/Safari en el móvil
2. Esperar el banner "Agregar a pantalla de inicio"
3. La aplicación se abre en modo **standalone** (sin barra de navegación)

### Almacenamiento Offline
- **IndexedDB**: base de datos local llamada `SensorQueueDB`
- Almacena lecturas pendientes con: `{asset, sensor, value, timestamp, type}`
- Sincronización automática al detectar evento `online`

### Service Worker
- **Cache-first** para assets estáticos
- Archivos cacheados: `/sensor-input`, `/static/manifest.json`, `/static/sensor-icon.svg`
- Actualización automática al cambiar el SW

### Captura Móvil
- Acelerómetro: usa `DeviceMotionEvent` para capturar en eje Z
- Fallback: giroscopio con `DeviceOrientationEvent`
- Botón "Capturar desde sensor" activa/desactiva la lectura continua

---

## 11. Mapa Georeferenciado

- Librería: **Leaflet.js 1.9.4**
- Capa base: **OpenStreetMap** (tile layer estándar)
- 2 marcadores (condominios):
  - Los Olivos: `-12.046, -77.043`
  - Vista Alegre: `-12.120, -77.030`
- **Color del marcador** según el peor estado entre sus activos:
  - 🔴 Rojo: algún activo en high
  - 🟡 Amarillo: algún activo en medium (ninguno en high)
  - 🟢 Verde: todos en low
- **Popup al hacer clic**: árbol jerárquico con colores por estado
- **Actualización automática**: llama a `/api/hierarchy` cada 3 segundos

---

## 12. Reportes Exportables

### 12.1 Reporte HTML (Imprimible → PDF)
- Diseño **A4** con márgenes y estilos @page
- Cabecera: nombre del sistema, fecha, total activos
- **Resumen semáforo**: 3 tarjetas de color (Rojo/Amarillo/Verde) con conteos
- **Tabla de activos**: activo, estado (color), score, MTBF, fallos, sensores
- **Tabla de eventos**: últimos 20 eventos
- Botón "Imprimir / Guardar PDF" (usa `window.print()`)
- Footer institucional

### 12.2 Reporte de Texto Plano
- Archivo descargable con extensión `.txt`
- Misma información que el HTML pero en texto
- Formato alineado con separadores `=` y espacios

### 12.3 Exportación CSV
- **Eventos**: timestamp, asset, label, from, to, score, type
- **Lecturas**: timestamp, asset, label, sensor, value, score (filtrable por activo)
- **Auditoría**: timestamp, username, action, detail
- Encabezados en español, puntos y comas como separadores

---

## 13. Modelo de Base de Datos

SQLite con 11 tablas y SQLAlchemy ORM 2.0:

### Diagrama Entidad-Relación

```
condominiums 1──N buildings 1──N machine_rooms 1──N assets
                                                      │
                                                      ├──N sensor_configs
                                                      ├──N actuators
                                                      ├──N rules
                                                      ├──N events
                                                      └──N sensor_readings

users 1──N audit_logs
users N──1 condominiums (asignación por condominium_id)
```

### Tabla: `condominiums`
| Campo | Tipo | Descripción |
|-------|------|-------------|
| id | INTEGER PK | Auto-increment |
| name | VARCHAR(200) | Nombre del condominio |
| address | TEXT | Dirección física |
| lat | FLOAT | Latitud (mapa) |
| lng | FLOAT | Longitud (mapa) |
| created_at | DATETIME | Fecha de registro |

### Tabla: `buildings`
| Campo | Tipo | Descripción |
|-------|------|-------------|
| id | INTEGER PK | Auto-increment |
| condominium_id | INTEGER FK → condominiums | Condominio padre |
| name | VARCHAR(200) | Nombre del edificio |

### Tabla: `machine_rooms`
| Campo | Tipo | Descripción |
|-------|------|-------------|
| id | INTEGER PK | Auto-increment |
| building_id | INTEGER FK → buildings | Edificio padre |
| name | VARCHAR(200) | Nombre de la sala |

### Tabla: `assets`
| Campo | Tipo | Descripción |
|-------|------|-------------|
| id | INTEGER PK | Auto-increment |
| location_id | INTEGER FK → machine_rooms | Sala donde se ubica |
| name | VARCHAR(100) UNIQUE | Nombre interno (e.g., "elevator") |
| label | VARCHAR(100) | Nombre mostrable (e.g., "Ascensor") |
| description | TEXT | Descripción del activo |
| icon | VARCHAR(50) | Icono (gear, zap, flame, etc.) |
| output_name | VARCHAR(50) | Nombre variable de salida difusa |
| output_label | VARCHAR(100) | Etiqueta mostrable del output |
| output_min | FLOAT (default 0) | Mínimo del rango de salida |
| output_max | FLOAT (default 100) | Máximo del rango de salida |

### Tabla: `sensor_configs`
| Campo | Tipo | Descripción |
|-------|------|-------------|
| id | INTEGER PK | Auto-increment |
| asset_id | INTEGER FK → assets | Activo al que pertenece |
| name | VARCHAR(100) | Nombre interno (e.g., "vibration") |
| label | VARCHAR(100) | Nombre mostrable (e.g., "Vibración") |
| unit | VARCHAR(20) | Unidad física (mm/s, °C, A, V, etc.) |
| min_val | FLOAT (default 0) | Mínimo del rango del sensor |
| max_val | FLOAT (default 100) | Máximo del rango del sensor |
| mf_config | JSON | Configuración de funciones de membresía |
| sensor_type | VARCHAR(20) | simulated / external / phone |

**Ejemplo mf_config:**
```json
[
  {"term": "low", "type": "trimf", "params": [0, 0, 4]},
  {"term": "medium", "type": "trimf", "params": [2, 5, 8]},
  {"term": "high", "type": "trimf", "params": [6, 10, 10]}
]
```

### Tabla: `actuators`
| Campo | Tipo | Descripción |
|-------|------|-------------|
| id | INTEGER PK | Auto-increment |
| asset_id | INTEGER FK → assets | Activo al que pertenece |
| name | VARCHAR(100) | Nombre interno |
| label | VARCHAR(100) | Nombre mostrable |
| unit | VARCHAR(20) | Unidad |
| min_val | FLOAT (default 0) | Rango mínimo |
| max_val | FLOAT (default 100) | Rango máximo |
| command | FLOAT (default 0) | Valor de comando actual |
| state | BOOLEAN (default False) | Encendido/apagado |
| auto | BOOLEAN (default True) | Modo automático (experto) o manual |

### Tabla: `rules`
| Campo | Tipo | Descripción |
|-------|------|-------------|
| id | INTEGER PK | Auto-increment |
| asset_id | INTEGER FK → assets | Activo al que pertenece |
| name | VARCHAR(200) | Nombre corto (R1, R2, etc.) |
| description | TEXT | Descripción legible |
| operator | VARCHAR(10) | and / or |
| antecedents | JSON | Array de condiciones (sensor + term) |
| consequent | JSON | Conclusión (term + opcional mf_config) |
| action | JSON (nullable) | Acción sobre actuador |
| weight | FLOAT (default 1.0) | Peso de la regla |
| enabled | BOOLEAN (default True) | Habilitada/deshabilitada |

**Ejemplo rule:**
```json
{
  "antecedents": [
    {"sensor": "vibration", "term": "high"},
    {"sensor": "temperature", "term": "hot"}
  ],
  "consequent": {"sensor": "maintenance", "term": "critical"},
  "action": {"actuator": "speed_controller", "value": 10}
}
```

### Tabla: `events`
| Campo | Tipo | Descripción |
|-------|------|-------------|
| id | INTEGER PK | Auto-increment |
| asset_id | INTEGER FK → assets | Activo involucrado |
| old_status | VARCHAR(20) | Estado anterior (none/low/medium/high/critical) |
| new_status | VARCHAR(20) | Estado nuevo |
| score | FLOAT | Score al momento del evento |
| message | VARCHAR(500) | Mensaje descriptivo |
| event_type | VARCHAR(20) | info / warning |

### Tabla: `sensor_readings`
| Campo | Tipo | Descripción |
|-------|------|-------------|
| id | INTEGER PK | Auto-increment |
| asset_id | INTEGER FK → assets | Activo |
| sensor_name | VARCHAR(100) | Nombre del sensor |
| value | FLOAT | Valor de la lectura |
| score | FLOAT | Score del diagnóstico al momento |
| timestamp | DATETIME | Marca de tiempo |

### Tabla: `users`
| Campo | Tipo | Descripción |
|-------|------|-------------|
| id | INTEGER PK | Auto-increment |
| username | VARCHAR(100) UNIQUE | Nombre de usuario |
| password_hash | VARCHAR(200) | SHA-256 hash de la contraseña |
| role | VARCHAR(20) | admin / supervisor / technician |
| condominium_id | INTEGER FK → condominiums (nullable) | Condominio asignado (solo técnicos) |

### Tabla: `audit_logs`
| Campo | Tipo | Descripción |
|-------|------|-------------|
| id | INTEGER PK | Auto-increment |
| username | VARCHAR(100) | Usuario que realizó la acción |
| action | VARCHAR(200) | Tipo de acción (login, cambio_escenario, etc.) |
| detail | TEXT | Detalle de la acción |
| asset_id | INTEGER (nullable) | Activo involucrado (opcional) |
| user_id | INTEGER FK → users (nullable) | ID del usuario |
| timestamp | DATETIME | Marca de tiempo |

---

## 14. Tecnologías Utilizadas

### Backend
| Tecnología | Versión | Propósito |
|------------|---------|-----------|
| Python | 3.13+ | Lenguaje principal |
| FastAPI | 0.136.1 | Framework web REST + WebSocket |
| Uvicorn | 0.47.0 | Servidor ASGI |
| SQLAlchemy | 2.0.46 | ORM para base de datos |
| SQLite | 3.x | Motor de base de datos (archivo local) |
| aiosqlite | 0.22.1 | Driver async para SQLite |
| Jinja2 | 3.1.6 | Motor de plantillas HTML |
| python-multipart | 0.0.32 | Procesamiento de formularios |
| aiofiles | 25.1.0 | Archivos asíncronos |

### Lógica Difusa
| Tecnología | Versión | Propósito |
|------------|---------|-----------|
| scikit-fuzzy | 0.5.0 | Motor de inferencia Mamdani |
| scipy | 1.18.0 | Dependencia de scikit-fuzzy |
| numpy | 1.26+ | Operaciones numéricas |

### Frontend
| Tecnología | Propósito |
|------------|-----------|
| HTML5 + CSS3 | Estructura y estilos (modo oscuro/claro) |
| JavaScript Vanilla | Lógica del cliente |
| Chart.js 4.4.7 | Gráficos históricos en dashboard |
| Leaflet.js 1.9.4 | Mapa georeferenciado |
| IndexedDB | Almacenamiento offline (PWA) |
| Service Worker | Cache offline + PWA |
| Web App Manifest | Instalación PWA |
| WebSocket API | Tiempo real |

---

## 15. Instalación y Ejecución

### Requisitos
- **Python 3.13+** (probado en 3.13.0)
- Windows, Linux, o macOS
- Navegador moderno (Chrome 90+, Edge 90+, Safari 15+, Firefox 90+)

### Instalación

```bash
# 1. Clonar el repositorio
git clone https://github.com/Caxtillo/sistema-experto.git
cd sistema-experto/condominium_expert

# 2. (Opcional) Crear y activar entorno virtual
python -m venv venv
# Windows: venv\Scripts\activate
# Linux/Mac: source venv/bin/activate

# 3. Instalar dependencias
pip install -r requirements.txt
```

### Ejecución

```bash
# Opción 1: Usando Uvicorn directamente
python3.13 -m uvicorn app:app --host 0.0.0.0 --port 8000 --reload

# Opción 2: Usando el script start.bat (Windows)
start.bat

# Opción 3: Usando python app.py
python app.py
```

### Acceso
- Abrir navegador en: **http://localhost:8000**
- **Login**: http://localhost:8000/login

### Notas
- La base de datos se **crea y puebla automáticamente** al iniciar
- Los datos se **recrean en cada inicio** (modo desarrollo)
- Para datos persistentes, cambiar `init_db()` + `seed()` en `lifespan`

---

## 16. Estructura del Proyecto

```
condominium_expert/
│
├── app.py                        # Punto de entrada FastAPI (rutas web + auth middleware + lifespan)
├── requirements.txt              # Dependencias Python con versiones fijas
├── start.bat                     # Script de inicio para Windows
├── DOCUMENTACION_CLIENTE.md      # Este documento
│
├── core/
│   ├── inference_engine.py       # Motor Mamdani con scikit-fuzzy (build_system, evaluate, get_status, get_active_rules)
│   ├── knowledge_base.py         # Capa CRUD completa (11 tablas, 30+ métodos)
│   └── explanation.py            # Explicaciones en lenguaje natural del diagnóstico difuso
│
├── web/
│   ├── api.py                    # ~80 endpoints REST + simulación + WebSocket + reportes CSV/HTML
│   └── templates/
│       ├── base.html             # Layout base (nav, modals, toast, drawer, theme toggle)
│       ├── login.html            # Página de inicio de sesión
│       ├── dashboard.html        # Dashboard con WebSocket, Chart.js, tarjetas de activos
│       ├── config.html           # Editor de reglas, sensores y MF (solo admin)
│       ├── sensor_input.html     # PWA offline con IndexedDB + sensor phone
│       ├── map.html              # Mapa Leaflet.js con marcadores de estado
│       ├── asset.html            # Ficha técnica del activo (sensors, rules, MTBF)
│       ├── reports.html          # Reportes exportables con selector de activo
│       └── admin.html            # Panel admin (usuarios, auditoría, jerarquía)
│
├── models/
│   └── models.py                 # SQLAlchemy ORM: 11 clases (Base, Condominium, Building, MachineRoom, Asset, SensorConfig, Actuator, Rule, Event, SensorReading, User, AuditLog)
│
├── storage/
│   └── database.py               # Conexión SQLite + engine + session factory + init_db()
│
├── iiot_simulator/
│   └── sensors.py                # IIoTSimulator: 8 activos, 26 sensores, 23 actuadores, SCENARIOS, RECOMMENDATIONS, apply_actuators
│
├── scripts/
│   └── seed.py                   # Seed completo: jerarquía, 8 activos, sensores, actuadores, reglas, usuarios
│
├── tests/
│   └── test_inference.py         # Tests del motor de inferencia (pytest)
│
├── static/
│   ├── style.css                 # Estilos CSS legacy
│   ├── manifest.json             # PWA Web App Manifest
│   ├── service-worker.js         # Service Worker (cache-first, install, activate, fetch)
│   └── sensor-icon.svg           # Icono SVG para PWA
│
└── data/
    └── condominium.db            # Base de datos SQLite (auto-creada)
```

---

## 17. Personalización

### 17.1 Agregar un Nuevo Activo

```bash
# 1. Crear el activo vía API
curl -X POST http://localhost:8000/api/assets \
  -H "Content-Type: application/json" \
  -d '{"name": "nuevo_activo", "label": "Nuevo Activo", "description": "Descripción", "icon": "gear"}'

# 2. Agregar sensores con MF
curl -X POST http://localhost:8000/api/assets/{id}/sensors \
  -H "Content-Type: application/json" \
  -d '{"name": "sensor1", "label": "Sensor 1", "unit": "°C", "min_val": 0, "max_val": 100, "mf_config": [{"term": "bajo", "type": "trimf", "params": [0,0,40]}]}'

# 3. Agregar reglas difusas
curl -X POST http://localhost:8000/api/assets/{id}/rules \
  -H "Content-Type: application/json" \
  -d '{"antecedents": [{"sensor": "sensor1", "term": "bajo"}], "consequent": {"term": "low"}, "operator": "and"}'
```

### 17.2 Agregar Escenarios de Falla

Editar `iiot_simulator/sensors.py` y agregar en `SCENARIOS`:
```python
"nuevo_activo": {
    "normal": {"sensor1": 50, "sensor2": 25, "amp": 0.01},
    "falla_ejemplo": {"sensor1": 90, "sensor2": 80, "amp": 0.15,
                      "label": "Falla de Ejemplo", "icon": "alert-triangle"},
}
```

### 17.3 Conectar Sensores Reales

```bash
# 1. Cambiar tipo de sensor en /config o vía API
curl -X POST http://localhost:8000/api/sensor-type/{id} \
  -H "Content-Type: application/json" \
  -d '{"sensor_type": "external"}'

# 2. Enviar datos desde el sensor real
curl -X POST http://localhost:8000/api/sensor-data \
  -H "Content-Type: application/json" \
  -d '{"asset": "elevator", "sensor": "vibration", "value": 3.5}'
```

El sistema ignora los datos simulados para ese sensor mientras reciba datos externos.

### 17.4 Modo Manual de Actuadores

Cada actuador tiene una propiedad `auto` (booleano). Cuando `auto: false`, el sistema experto no modifica el actuador, permitiendo control manual:

```bash
curl -X POST http://localhost:8000/api/actuator/{id}/command \
  -H "Content-Type: application/json" \
  -d '{"value": 50, "auto": false}'
```

### 17.5 Tema Claro/Oscuro

El sistema soporta tema claro y oscuro:
- Botón ☀️/🌙 en la barra de navegación
- Persiste en `localStorage`
- CSS variables en `:root` y `[data-theme="light"]`
- Transiciones suaves entre temas

---

## 18. Pruebas

```bash
cd condominium_expert
python3.13 -m pytest tests/ -v
```

### Tests incluidos:

| Test | Archivo | Descripción |
|------|---------|-------------|
| `test_inference_evaluates` | test_inference.py | Verifica que evaluate devuelve float entre 0-100 |
| `test_inference_low_values` | test_inference.py | Valores bajos → score < 40 |
| `test_inference_high_values` | test_inference.py | Valores altos → score > 50 |
| `test_get_status` | test_inference.py | 3 estados: high (>=60), medium (>=30), low (<30) |
| `test_get_active_rules` | test_inference.py | Reglas activas con fire_strength > 0 |
| `test_rules_sorted_by_fire_strength` | test_inference.py | Reglas ordenadas descendente |
| `test_cache_persistence` | test_inference.py | Cache reutiliza build_system |
| `test_cache_clear` | test_inference.py | Clear cache fuerza rebuild |
| `test_empty_sensors` | test_inference.py | Sin sensores → score 0 |
| `test_empty_rules` | test_inference.py | Sin reglas → score 0 |
| `test_disabled_rules` | test_inference.py | Reglas deshabilitadas no se evalúan |
| `test_missing_sensor_value` | test_inference.py | Valor faltante → maneja sin error |
| `test_trapmf_sensor` | test_inference.py | Sensor con MF tipo trapmf |
| `test_gaussmf_sensor` | test_inference.py | Sensor con MF tipo gaussmf |
| `test_get_status_boundary` | test_inference.py | Límites exactos: 0, 29, 30, 59, 60, 100 |
| `test_or_operator` | test_inference.py | Regla con operador OR |

---

## 19. Seguridad

### Autenticación
- **SessionMiddleware** con clave secreta (`capstone-secret-key-2026`)
- Contraseñas hasheadas con **SHA-256** antes de almacenar
- Sesión almacena: `username`, `role`, `condominium_id`
- Middleware protege rutas web (`require_auth`)

### Control de Acceso
- **Rutas admin** (`/config`, `/admin`) bloqueadas para no-admin (redirect a /)
- **Auditoría** de acciones sensibles: login, cambios de escenario, comandos de actuadores, fallas aleatorias
- **Roles** aplicados en backend (API no discrimina por rol salvo admin)

### Recomendaciones para Producción
- Cambiar `secret_key` en `SessionMiddleware` a una variable de entorno
- Usar **HTTPS** en producción (detrás de nginx/Caddy)
- Agregar **rate limiting** a endpoints públicos
- Migrar de SQLite a **PostgreSQL** para concurrencia
- Agregar **validación de entrada** más estricta en API
- Implementar **CSRF tokens** en formularios
- Usar **contraseñas más fuertes** (bcrypt/argon2 en vez de SHA-256)

---

## 20. Despliegue a Producción

### Opción 1: Servidor Dedicado (Windows/Linux)

```bash
# Usando Gunicorn (Linux) o Uvicorn (cualquier SO)
uvicorn app:app --host 0.0.0.0 --port 8000 --workers 4

# Con systemd (Linux) o NSSM (Windows) para servicio
```

### Opción 2: Docker (Recomendado)

```dockerfile
FROM python:3.13-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8000
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
```

### Opción 3: Proxy Inverso (nginx + Gunicorn)

```nginx
server {
    listen 80;
    server_name sistema-experto.midominio.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
    }

    location /ws {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
```

---

## 21. Repositorio GitHub

- **URL**: https://github.com/Caxtillo/sistema-experto
- **Rama principal**: `main`
- **Commits**: 1 commit inicial con 34 archivos (~7100 líneas)
- **Visibilidad**: Público

### Clonar
```bash
git clone https://github.com/Caxtillo/sistema-experto.git
```

---

## Contacto

Proyecto desarrollado para **Loyalty Soluciones Inmobiliarias**.

Para soporte técnico, consultas o reportes de bugs, contactar al equipo de desarrollo.

---

*Documento generado el 01/07/2026*
*Sistema Experto - Gestión de Activos Críticos con IIoT v1.0*

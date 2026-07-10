# Tour del Sistema Experto — Guía para Video Demo al Cliente

> Documento de recorrido funcional, descripción de cada módulo, guion para video demo y análisis de brechas.

---

## 1. Login

**Cómo funciona:** Pantalla independiente con formulario de usuario/contraseña. La autenticación es por sesión (cookie). Hay 3 roles con ejemplos visibles: admin, supervisor, técnico.  
**Roles:**
- `admin` — acceso total a todo
- `sup_{slug}` — admin de su condominio
- `tec_{slug}` — solo ingresa datos de campo

**Demo (20s):**
1. Mostrar pantalla de login con hints de usuarios seed
2. Ingresar como `admin / admin123`
3. Señalar que hay 3 niveles de acceso

---

## 2. Dashboard — Monitoreo en Tiempo Real (`/`)

**Cómo funciona:** Panel principal con tarjetas de activos agrupadas por condominio → edificio. Cada tarjeta muestra:
- Nombre del activo + badge SIM/REAL + badge de estado (VERDE/AMARILLO/ROJO)
- Sensores con barras de salud
- Índice de Salud (IS) numérico + barra de progreso
- Minigráfico de tendencia (últimos ~30 ciclos)
- Diagnóstico en texto
- Selector de origen: Simulado / Real (toggle por activo)
- Link a ingreso de datos manual

A la derecha hay 4 paneles secundarios: Recomendaciones, Actuadores, Eventos, Acciones.
Abajo hay un botón de simulación (drawer lateral) para inyectar escenarios de falla.

**Interno:** WebSocket para tiempo real + polling cada 2s como fallback. El motor de inferencia evalúa cada activo cada 2s usando lógica difusa Mamdani (scikit-fuzzy).

**Demo (1.5 min):**
1. Mostrar el grid de activos — explicar agrupación por condominio
2. Señalar una tarjeta: nombre, sensores, barra de salud, score
3. Toggle Simulado → Real en un activo (explicar que es por activo, no global)
4. Hover sobre el badge de estado (VERDE = normal, AMARILLO = precaución, ROJO = crítica)
5. Abrir el drawer de simulación → seleccionar activo → aplicar escenario de falla
6. Mostrar cómo cambia el badge a ROJO, el score baja, aparecen recomendaciones
7. Mostrar los paneles de Eventos (transiciones de estado) y Acciones (actuadores disparados)

---

## 3. Configuración — Editor de Reglas y Sensores (`/config`)

**Cómo funciona:** Página principal de configuración del sistema experto. Arriba hay un selector de ruta (Condominio → Edificio → Sala → Activo) para elegir qué activo configurar. Debajo hay 5 pestañas:

### 3a. Reglas
- Lista de reglas del activo seleccionado con formato visual: `SI [sensor]=[término] Y [sensor]=[término] ENTONCES [salida]`
- Modal de creación/edición con:
  - Nombre de regla
  - Operador lógico (Y/O)
  - Descripción
  - Condiciones dinámicas (sensor + término difuso, con selectores encadenados)
  - Conclusión (término de salida: none/low/medium/high/critical)
  - Checkbox de habilitado

**Demo (1 min):**
1. Seleccionar un activo en la barra de ruta
2. Mostrar lista de reglas existentes
3. Crear una regla nueva: "SI vibration=high Y temperature=hot ENTONCES critical"
4. Señalar los selectores de sensor que se llenan automáticamente
5. Guardar y mostrar que aparece en la lista
6. Editar una regla (cambiar operador de Y a O)

### 3b. Sensores
- Tabla de sensores del activo: nombre, etiqueta, unidad, rango, términos difusos
- Modal de creación con:
  - Nombre interno, etiqueta visible, unidad
  - Valor mínimo/máximo
  - Términos difusos dinámicos (tipo: trimf/trapmf/gaussmf + parámetros)

**Demo (45s):**
1. Mostrar tabla de sensores del activo
2. Crear sensor nuevo: "vibration / Vibración / mm/s / rango 0-50"
3. Agregar 3 términos: bajo trimf(0,0,15), medio trimf(5,25,40), alto trimf(30,50,50)
4. Guardar y mostrar en tabla

### 3c. Visualizador de Pertenencia
- Gráfico canvas con curvas de funciones de membresía del sensor seleccionado
- Input para probar valores → muestra a qué términos pertenece y con qué porcentaje
- Leyenda y explicación dinámica

**Demo (30s):**
1. Seleccionar un sensor en el dropdown
2. Mostrar las curvas (triangulares/trapezoidales)
3. Ingresar un valor de prueba → mostrar cómo se clasifica (ej: "75% medio, 25% alto")
4. Explicar que esto es la base de la lógica difusa

### 3d. Exportar
- Botones: Reporte de Estado (PDF/texto), Exportar Config (JSON), Documentación API (Swagger)

**Demo (15s):** Mostrar los botones de exportación

### 3e. Usuarios
- CRUD completo de usuarios con tabla, modal de creación/edición
- Roles: Admin, Supervisor, Técnico
- Asignación de condominio
- Restricciones según rol del usuario logueado

**Demo (30s):**
1. Mostrar lista de usuarios
2. Crear un técnico nuevo asignado a un condominio
3. Editar rol de un usuario existente

---

## 4. Gestión de Jerarquía (`/config/hierarchy`)

**Cómo funciona:** Página independiente con árbol expandible de Condominios → Edificios → Salas. CRUD inline: los formularios aparecen en el mismo lugar al hacer clic en los botones.

**Demo (45s):**
1. Mostrar el árbol con todos los condominios
2. Pasar el mouse sobre un condominio → mostrar botones ✏️ 🗑️ ➕
3. Agregar un edificio nuevo a un condominio
4. Mostrar inline form (aparece justo debajo)
5. Editar nombre de una sala
6. Eliminar un edificio (mostrar confirmación)

---

## 5. Gestión de Activos (`/config/assets`)

**Cómo funciona:** Página con formulario de creación de activos + lista de activos existentes. El formulario tiene selectores encadenados (Condominio → Edificio → Sala), selector de tipo de equipo, previsualización del nombre auto-generado, y nombre visible.

**Demo (30s):**
1. Mostrar la lista de activos existentes con su ruta (Condominio → Edificio → Sala)
2. Crear un activo nuevo: seleccionar condominio, edificio, sala, tipo "Bomba"
3. Señalar la previsualización del nombre auto-generado ("bomba_ceiba_3")
4. Guardar y mostrar que aparece en la lista
5. Eliminar un activo

---

## 6. Sensor Input — Captura de Datos de Campo (`/sensor-input`)

**Cómo funciona:** Página PWA diseñada para uso móvil en campo (offline-first). Acordeón de jerarquía (Condominio → Edificio → Sala → Activo). Dos modos de entrada:

### Modo Numérico
- Inputs numéricos para cada sensor del activo
- Slider visual con rango del sensor
- Botón "Enviar lectura"

### Modo Cualitativo
- 5 niveles fijos: Muy Bajo, Bajo, Medio, Alto, Muy Alto
- Cada nivel tiene tooltip con el rango escalado al sensor
- Botón "Enviar valor"

**Offline:** Las lecturas se guardan en IndexedDB y se sincronizan automáticamente cuando hay conexión.

**Demo (1 min):**
1. Navegar por el acordeón: Condominio → Edificio → Sala → Activo
2. Seleccionar un activo → mostrar sensores
3. Ingresar valor numérico en un sensor y enviar
4. Cambiar a modo cualitativo → seleccionar "Alto"
5. Señalar que los niveles se escalan al rango del sensor
6. Desconectar Wi-Fi → enviar otra lectura → reconectar → mostrar que se sincronizó
7. Mostrar el indicador de cola offline (contador)

---

## 7. Mapa Geo-referenciado (`/map`)

**Cómo funciona:** Mapa Leaflet con marcadores circulares para cada condominio, coloreados según el peor estado de sus activos. Popup con árbol de jerarquía y estado de cada activo.

**Demo (30s):**
1. Mostrar el mapa con los 8 condominios en Maturín
2. Hacer clic en un marcador → mostrar popup con edificios y activos
3. Mostrar los colores: verde/amarillo/rojo según estado
4. Alejar/acercar

---

## 8. Ficha Técnica (`/asset`)

**Cómo funciona:** Página de detalle de un activo específico. Barra de navegación de activos. Muestra:
- Información general (nombre, tipo, ubicación)
- MTBF (Mean Time Between Failures)
- Lista de sensores con configuración
- Lista de reglas
- Estado actual

**Demo (30s):**
1. Navegar entre activos con la barra superior
2. Mostrar información general y MTBF
3. Mostrar lista de sensores y reglas

---

## 9. Admin (`/admin`)

**Cómo funciona:** Panel de administración con 3 pestañas:
- **Usuarios:** CRUD completo
- **Auditoría:** Log filtrable de acciones de usuarios
- **Jerarquía:** Árbol de jerarquía con colores de estado (similar al del mapa pero en texto)

**Demo (30s):**
1. Mostrar pestaña de usuarios (similar a Config → Usuarios pero más completo)
2. Ir a Auditoría → mostrar eventos recientes
3. Ir a Jerarquía → mostrar árbol con códigos de color

---

## 10. Reportes (`/reports`)

**Cómo funciona:** Centro de generación de reportes:
- Reporte HTML (para ver/imprimir en navegador)
- Reporte de texto plano
- CSV de eventos
- CSV de lecturas de sensores
- CSV de auditoría
- Previsualización de jerarquía JSON

**Demo (20s):**
1. Mostrar la página con los botones
2. Abrir reporte HTML en nueva pestaña
3. Descargar CSV de eventos

---

## Brechas y Cosas No Prácticas

### 🚨 Críticas

| # | Problema | Impacto |
|---|----------|---------|
| 1 | **`init_db()` borra toda la DB al reiniciar** — Cada vez que se reinicia el servidor, se pierden todos los datos (reglas, sensores, activos, usuarios). Solo los datos del seed sobreviven si se ejecuta `seed()`. | **Producción inviable.** Cualquier configuración hecha por el usuario se pierde al reiniciar. |
| 2 | **Contraseñas con SHA-256 sin salt** — Las contraseñas se hashean con SHA-256 directo. | Riesgo de seguridad alto. Usar bcrypt/argon2. |
| 3 | **Sin HTTPS** — La app corre en HTTP plano. | Datos de sesión y contraseñas viajan en texto claro. |
| 4 | **Sin CSRF** — No hay tokens CSRF en formularios POST. | Vulnerable a ataques CSRF. |

### ⚠️ Funcionales

| # | Problema | Impacto |
|---|----------|---------|
| 5 | **Auto-recuperación de fallas en ~15s** — Las simulaciones de falla se autorevierten. Para demo está bien, pero en producción no debe auto-revertirse. | Falso sentido de "recuperación automática". |
| 6 | **Editor de reglas: términos no filtrados por sensor** — El dropdown de términos en las condiciones muestra TODOS los términos posibles en vez de solo los definidos para ese sensor. | Usuario puede seleccionar un término que no existe para ese sensor → regla inválida. |
| 7 | **Mapa centrado en Lima, Perú** — Las coordenadas están en Maturín, Venezuela (~9.75, -63.18) pero el mapa inicia en Lima. | El auto-fit lo corrige, pero la vista inicial está mal. |
| 8 | **admin.html línea 147: comparación de rol frágil** — Usa `'{{ role }}'` en JS, que es propenso a errores de sintaxis. | Podría romper la UI de admin. |
| 9 | **Auditoría sin paginación** — Carga hasta 200 eventos. Con uso continuo se vuelve lento. | Degradación con el tiempo. |
| 10 | **Dos páginas de gestión de usuarios** — Config → Usuarios y Admin → Usuarios tienen funcionalidad similar pero no idéntica. | Confusión y mantenimiento duplicado. |

### 🟡 Estética / UX

| # | Problema | Impacto |
|---|----------|---------|
| 11 | **Dashboard: tarjetas sin scroll horizontal en pantallas pequeñas** — En móvil las tarjetas se apilan verticalmente. | Usable pero no óptimo. |
| 12 | **Service worker se registra en cada página** — Cada template registra el SW individualmente. | Duplicación, potencial conflicto de versiones. |
| 13 | **`config_hierarchy.html` sin colores de estado** — A diferencia de la jerarquía en admin.html, la página de gestión no muestra el estado de los activos. | Menos informativo. |

### 📦 Funcionalidades Faltantes (No Implementadas)

| # | Funcionalidad | Notas |
|---|---------------|-------|
| 14 | **Notificaciones push** — Solo hay toast en pantalla y sonido. No hay notificaciones push mobile/desktop. | Útil para alertas fuera de la app. |
| 15 | **Exportar a PDF** — Solo hay HTML (imprimible) y texto. No hay generación de PDF nativa. | Para reportes formales. |
| 16 | **Historial de lecturas con gráfica temporal** — El minigráfico del dashboard es en tiempo real. No hay vista de histórico (días/semanas). | Para análisis de tendencias. |
| 17 | **Dashboard por rol** — Técnico y supervisor ven el mismo dashboard completo. No hay vista filtrada por condominio. | El supervisor de Ceiba ve todos los condominios. |
| 18 | **Múltiples idiomas** — Toda la UI está en español. | OK para cliente actual, pero no internacionalizable. |
| 19 | **Onboarding/tutorial** — No hay guía de primeros pasos para el usuario nuevo. | Curva de aprendizaje. |

---

## Resumen para el Video

### Estructura Sugerida (5-7 min)

| Tiempo | Sección | Qué Mostrar |
|--------|---------|-------------|
| 0:00-0:20 | Login | Ingresar como admin, mencionar roles |
| 0:20-2:00 | Dashboard | Grid de activos, sensores, score, toggle SIM/REAL, drawer de simulación, falla, eventos |
| 2:00-3:00 | Configuración | Selector de activo, pestaña Reglas (crear/editar), pestaña Sensores (crear), Membresía (gráfico + test) |
| 3:00-3:30 | Jerarquía | Árbol inline, CRUD de condominios/edificios/salas |
| 3:30-4:00 | Activos | Crear activo con nomenclatura automática, lista de activos |
| 4:00-4:45 | Sensor Input (móvil) | Acordeón, modo numérico, modo cualitativo, offline |
| 4:45-5:15 | Mapa | Marcadores por condominio, colores de estado, popups |
| 5:15-5:45 | Reportes | HTML report, CSV export |
| 5:45-6:00 | Admin | Usuarios, auditoría, jerarquía |
| 6:00-6:30 | Cierre | Mencionar que es un sistema en evolución, resaltar flexibilidad de lógica difusa, personalización por activo |

### Puntos Clave a Enfatizar al Cliente

1. **Por activo, no global** — Cada activo tiene sus propios sensores, reglas y fuente de datos (SIM/REAL). No hay configuraciones globales que afecten todo.
2. **Lógica difusa** — No es sí/no binario. Los valores pueden ser "parcialmente altos y parcialmente medios", dando diagnósticos más precisos.
3. **Offline-first** — El técnico puede tomar lecturas sin conexión y se sincronizan automáticamente.
4. **Jerarquía flexible** — Condominios, edificios, salas y activos se crean/editan/eliminan desde la UI. No requiere SQL.
5. **Tres roles** — Admin ve todo, supervisor gestiona su condominio, técnico solo ingresa datos.
6. **Código abierto** — El cliente tiene el control total del código y los datos.

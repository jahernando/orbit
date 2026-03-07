# 🚀 Orbit

Sistema personal de gestión de proyectos científicos y personales en markdown plano.

---

## Estructura

```
Orbit/
├── 🚀proyectos/
│   ├── INDEX.md                        ← tabla maestra de proyectos
│   └── {emoji}nombre/                  ← directorio del proyecto
│       ├── {emoji}Nombre.md            ← índice: objetivo, tareas, referencias
│       ├── 📓Nombre.md                 ← logbook cronológico
│       ├── references/                 ← PDFs e imágenes (no en git)
│       └── results/                    ← resultados numéricos (no en git)
├── ☀️mision-log/
│   ├── diario/YYYY-MM-DD.md            ← planificación del día
│   ├── semanal/YYYY-Wnn.md             ← revisión semanal
│   └── mensual/YYYY-MM.md              ← revisión mensual
├── 📐templates/                        ← plantillas para todos los ficheros
├── orbit.py                            ← CLI principal
├── CHULETA.md                          ← referencia rápida de comandos
└── core/                               ← módulos del CLI
```

---

## Tipos de proyecto

| Emoji | Tipo |
|-------|------|
| 🌀 | Investigación |
| 📚 | Docencia |
| ⚙️ | Gestión |
| 📖 | Formación |
| 💻 | Software |
| 🌿 | Personal |

---

## Estados y prioridades

**Estado:**
`⬜ Inicial` · `▶️ En marcha` · `⏸️ Parado` · `⏳ Esperando` · `💤 Durmiendo` · `✅ Completado`

**Prioridad:**
`🟠 Alta` · `🟡 Media` · `🔵 Baja`

---

## Logbook — tipos de entrada

Cada entrada es una línea con formato `YYYY-MM-DD mensaje #tipo`:

| Hashtag | Significado |
|---------|-------------|
| `#idea` | 💡 Idea nueva |
| `#referencia` | 📎 Paper, link o recurso |
| `#tarea` | ✅ Tarea a realizar |
| `#problema` | ⚠️ Problema encontrado |
| `#resultado` | 📊 Resultado obtenido |
| `#apunte` | 📝 Nota o apunte general |
| `#decision` | 🔀 Decisión tomada |
| `#evento` | 📅 Evento de calendario |

Ejemplo:
```
2026-03-06 Idea sobre calibración relativa #idea
2026-03-06 [Gonzalez 2024](./references/gonzalez2024.pdf) #referencia
2026-03-06 Reproducir figura 3 del paper #tarea
2026-03-06 El fit no converge con el dataset completo #problema
2026-03-06 Energy resolution σ/E = 2.3% @ 1 MeV #resultado
```

---

## Dinámica de trabajo

### Cada día
1. Abre o crea `☀️mision-log/diario/YYYY-MM-DD.md` desde la plantilla
2. Decide el proyecto en foco y las tareas del día
3. Registra entradas en el logbook del proyecto con `orbit log`

### Cada semana
1. Crea `☀️mision-log/semanal/YYYY-Wnn.md` desde la plantilla
2. Selecciona 2 proyectos en foco para la semana
3. Revisa qué salió bien, qué no, y arrastra tareas pendientes

### Cada mes
1. Ejecuta `python orbit.py monthreport` — genera la tabla de actividad en `mensual/YYYY-MM.md`
2. Rellena la sección 🎯 Priorización al inicio del mes
3. Rellena la sección 🍅 Valoración al final del mes
4. Ejecuta con `--apply` si quieres actualizar los estados reales en `proyecto.md`

---

## CLI — orbit.py

### `project` — crear un proyecto nuevo

```bash
python orbit.py project --name NOMBRE --type TIPO [--priority PRIORIDAD]
```

```bash
python orbit.py project --name NEXT-GALA --type investigacion
python orbit.py project --name FNyP --type docencia --priority alta
```

Crea el directorio `{emoji}nombre/` con `{emoji}Nombre.md` y `📓Nombre.md` desde las plantillas.

Tipos: `investigacion` · `docencia` · `gestion` · `formacion` · `software` · `personal`

---

### `import` — importar nota de Evernote

```bash
python orbit.py import --file FICHERO.enex --project PROYECTO
```

```bash
python orbit.py import --file "~/Downloads/NEXT-Kr.enex" --project next-kr
```

Extrae del `.enex`:
- **Logbook** (`<h2>Logbook`) → añade entradas a `📓Nombre.md` (sin duplicar fechas)
- **Referencias** (`<h2>References/Referencias`) → añade links a `## 📎 Referencias clave`
- **Tareas** (`<h2>Tasks/Tareas`) → añade a `## ✅ Tareas`
- **Imágenes** (recursos `<resource>`) → guarda como `fig-NN.png` en `references/` y enlaza en el logbook
- **Resto de secciones** → `references/informacion-evernote.md`

---

### `setpriority` — establecer prioridad en varios proyectos a la vez

```bash
python orbit.py setpriority --priority PRIORIDAD --projects P1 P2 ...
```

```bash
python orbit.py setpriority --priority alta --projects next-kr next-gala hk-general
python orbit.py setpriority --priority baja --projects appec catedra
```

Aplica la misma prioridad a todos los proyectos listados. Usa coincidencia parcial de nombre, igual que `update`.

---

### `update` — cambiar estado o prioridad de un proyecto

```bash
python orbit.py update <proyecto> [--status ESTADO] [--priority PRIORIDAD]
```

```bash
python orbit.py update next-kr --status "en marcha"
python orbit.py update catedra --priority alta
python orbit.py update orbit --status completado --priority baja
```

Estados: `inicial` · `en marcha` · `parado` · `esperando` · `durmiendo` · `completado`

---

### `log` — añadir entrada al logbook

```bash
python orbit.py log <proyecto> "<mensaje>" [--type TIPO] [--path RUTA] [--date YYYY-MM-DD]
```

```bash
python orbit.py log detector-xenon "El fit no converge" --type problema
python orbit.py log detector-xenon "Gonzalez 2024" --type referencia --path ./references/gonzalez2024.pdf
python orbit.py log 💻-orbit "Comando monthreport implementado" --type resultado
```

### `list` — listar entradas del logbook

```bash
python orbit.py list <proyecto> [--type TIPO...] [--date YYYY-MM o YYYY-MM-DD] [--output FICHERO]
```

```bash
python orbit.py list detector-xenon
python orbit.py list detector-xenon --type tarea problema
python orbit.py list detector-xenon --date 2026-03
```

### `tasks` — listar tareas pendientes

```bash
python orbit.py tasks [--project PROYECTO] [--type TIPO] [--status ESTADO] [--priority PRIORIDAD] [--date FECHA] [--output FICHERO]
```

```bash
python orbit.py tasks
python orbit.py tasks --type investigacion
python orbit.py tasks --priority alta
python orbit.py tasks --date 2026-03
```

Tareas vencidas se marcan con `⚠️`. Tareas sin fecha de vencimiento aparecen con `—`.

### `activity` — informe de actividad por proyecto

```bash
python orbit.py activity [--project PROYECTO] [--type TIPO] [--priority PRIORIDAD] [--period FECHA [FECHA]] [--apply] [--output FICHERO]
```

```bash
python orbit.py activity
python orbit.py activity --period 2026-03
python orbit.py activity --period 2026-02 2026-03
python orbit.py activity --type investigacion --apply
```

El período por defecto son los **últimos 60 días**. El estado real se calcula así:

| Condición | Estado resultante |
|---|---|
| Sin actividad en los últimos 60 días | 💤 Durmiendo |
| Sin actividad en los últimos 30 días | ⏸️ Parado |
| Actividad en los últimos 30 días | ▶️ En marcha |
| ⏳ Esperando o ✅ Completado | siempre sin cambio |

La prioridad se degrada un nivel si no hay actividad en un período ≥ 30 días. Proyectos en `🔵 Baja` sin actividad desaparecen del listado.

`--apply` escribe los cambios directamente en `proyecto.md`.

### `day` / `week` / `month` — crear ficheros de planificación

```bash
python orbit.py day   [--date YYYY-MM-DD] [--force] [--focus PROYECTO...]
python orbit.py week  [--date YYYY-MM-DD] [--force] [--focus PROYECTO...]
python orbit.py month [--date YYYY-MM]    [--force] [--focus PROYECTO...]
```

```bash
python orbit.py day                                    # crea el diario de hoy
python orbit.py day --focus next-kr orbit              # crea el diario con proyectos en foco
python orbit.py week --date 2026-03-04                 # crea semanal de la semana que contiene esa fecha
python orbit.py month                                  # crea el mensual del mes actual
python orbit.py week --focus next-kr hk-ana --force    # crea la semana con proyectos en foco
```

Crea los ficheros en `☀️mision-log/diario/`, `semanal/` o `mensual/` desde la plantilla. Usa `--force` para sobreescribir si ya existe. Con `--focus` inyecta los proyectos en foco y las tareas próximas.

---

### `report` — generar informe de actividad

```bash
python orbit.py report day   [--date YYYY-MM-DD] [--inject]
python orbit.py report week  [--date YYYY-MM-DD] [--inject]
python orbit.py report month [--date YYYY-MM]    [--output FICHERO]
```

```bash
python orbit.py report day                    # informe del día de hoy
python orbit.py report week --inject          # informe semanal e inyecta en el fichero
python orbit.py report month --date 2026-02   # informe mensual de febrero
```

Genera un resumen de actividad con evaluación 🍅 de proyectos en foco, tareas completadas y próximas. `--inject` escribe el informe en el fichero `.md` correspondiente.

---

### `done` — marcar tarea como completada

```bash
python orbit.py done <proyecto> "<tarea>" [--date YYYY-MM-DD]
```

```bash
python orbit.py done next-kr "Reproducir figura 3"
python orbit.py done orbit "Implementar calendar sync" --date 2026-03-07
```

Busca la tarea en `proyecto.md` por coincidencia parcial y la marca como `- [x] Descripción (YYYY-MM-DD)`.

---

### `calendar` — sincronizar Google Calendar

```bash
python orbit.py calendar [--date YYYY-MM-DD] [--dry-run]
```

```bash
python orbit.py calendar              # sincroniza eventos de hoy
python orbit.py calendar --dry-run    # muestra qué se sincronizaría sin escribir
python orbit.py calendar --date 2026-03-05
```

Lee los eventos de todos tus calendarios de Google y añade los que tengan `proyecto: nombre` en la descripción al logbook del proyecto como `#evento`. Requiere `credentials.json` en el directorio Orbit (ver Google Cloud Console → OAuth 2.0).

---

### `monthreport` — generar revisión mensual

```bash
python orbit.py monthreport [--month YYYY-MM] [--apply] [--output FICHERO]
```

```bash
python orbit.py monthreport
python orbit.py monthreport --month 2026-02
python orbit.py monthreport --apply
```

Crea `☀️mision-log/mensual/YYYY-MM.md` desde la plantilla si no existe, e inyecta la tabla de actividad entre los marcadores `<!-- orbit:monthreport:start -->` y `<!-- orbit:monthreport:end -->`. El estado real se evalúa con la misma lógica que `activity` (ventanas de 30 y 60 días desde el fin del mes).

---

## Convenciones

- **Tareas** en `proyecto.md`: `- [ ] Descripción (YYYY-MM-DD)` — la fecha es el vencimiento
- **Nombre de directorio** del proyecto: kebab-case con emoji de tipo opcional (`detector-xenon`, `💻-orbit`)
- **Referencias, figuras y resultados** binarios no se suben a git — solo el texto markdown
- **Fuente de verdad** de las tareas: sección `## ✅ Tareas` de `proyecto.md`
- **Fuente de verdad** del historial: logbook del proyecto

### Entradas multilínea en el logbook

Para entradas con varias líneas o listas, edita el logbook directamente. La fecha y el hashtag van en la primera línea; las líneas indentadas forman parte de la misma entrada:

```
2026-03-06 Resultados del fit de calibración #resultado
  - σ/E = 2.3% @ 1 MeV
  - σ/E = 1.8% @ 3 MeV
  - El modelo lineal ajusta bien en todo el rango
```

El comando `orbit log` sigue siendo útil para entradas rápidas de una línea.

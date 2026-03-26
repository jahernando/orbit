# CLAUDE.md — Contexto para Claude Code

## Visión del proyecto

Orbit es un sistema personal de gestión de proyectos científicos en markdown plano. Está diseñado para un investigador/profesor que necesita coordinar múltiples proyectos (investigación, docencia, gestión, software) con un flujo de trabajo basado en ficheros locales, git y sincronización con Google Calendar/Tasks y una nube (OneDrive).

Principios de diseño:
- **Markdown plano** — todo son ficheros `.md` editables con cualquier editor
- **CLI interactiva** — shell propio (`orbit`) con comandos cortos
- **Git como backbone** — versionado, historial, recuperación
- **Separación código/datos** — `~/orbit` (público) + workspaces privados (`~/🚀orbit-ws`, `~/🌿orbit-ps`)
- **Sincronización bidireccional** — Google Calendar/Tasks, Reminders.app de macOS, nube

## Arquitectura

```
~/orbit/                  ← este repo (código público)
  orbit.py                ← CLI principal y dispatchers
  core/
    agenda_cmds.py        ← CRUD de las 4 citas (task, ms, ev, reminder)
    ring.py               ← resolución de ring y programación en Reminders.app
    gsync.py              ← sincronización con Google Calendar/Tasks
    doctor.py             ← validación de sintaxis de ficheros
    shell.py              ← shell interactivo y startup
    config.py             ← ORBIT_HOME, ORBIT_PROMPT, orbit.json
    log.py                ← logbook entries
    highlights.py         ← highlights CRUD
    project.py            ← gestión de proyectos
  tests/                  ← pytest, ~765 tests

~/🚀orbit-ws/             ← workspace de trabajo (privado)
~/🌿orbit-ps/             ← workspace personal (privado)
```

## Las 4 citas (appointments)

El sistema de citas es uniforme. Las cuatro comparten la misma interfaz:

| Tipo | Emoji | Sección agenda.md | Tiene status | Tiene done |
|------|-------|-------------------|-------------|------------|
| task | ✅ | `## ✅ Tareas` | sí (pending/done/cancelled) | sí |
| ms (milestone) | 🏁 | `## 🏁 Hitos` | sí | sí |
| ev (event) | 📅 | `## 📅 Eventos` | no | no |
| reminder | 💬 | `## 💬 Recordatorios` | no (cancelled) | no |

Comandos uniformes: `add`, `drop`, `edit`, `list`, `log` (crear entrada de logbook desde cita).
Además: task/ms tienen `done`. Alias: `rem` = `reminder`.

### Recurrencia
- Todos soportan `--recur` y `--until`
- `drop` en recurrentes: `-o` (avanza ocurrencia), `-s` (elimina serie), interactivo sin flags
- `--force` en recurrentes = opción segura (avanza)

### Ring (notificaciones Mac)
- `--ring` programa notificaciones en Reminders.app de macOS
- Al crear cita con `--time` sin `--ring`, se pregunta interactivamente (defecto 5m)
- Al editar: si cambia título/hora/ring y suena hoy → borra viejo + programa nuevo
- Al borrar: si sonaba hoy → borra del Mac
- Startup programa las 4 citas del día (tasks, ms, ev, reminders)
- Formato: `🚀[☀️mission] ✅ título` (workspace emoji + tipo proyecto + emoji cita + título)

### gsync (Google sync)
- Tasks/milestones → Google Tasks (una lista por tipo)
- Events → Google Calendar (un calendario por tipo, RRULE para recurrentes)
- Descripción: notas indentadas bajo el item se propagan a Google
- Error en un evento no bloquea el resto
- IDs en `.gsync-ids.json` por proyecto

## Convenciones de código

- Python 3.9+ (anaconda del usuario)
- Tests con pytest, ~989 tests (2 fallan por dependencia de fecha, preexistentes)
- Ignorar `tests/test_notes_commit.py` y `tests/test_undo.py` si fallan por fecha
- Funciones públicas: `run_*` (dispatchers en orbit.py las llaman)
- Funciones internas: `_*` (prefijo underscore)
- Selección interactiva: `_select_from_list` (genérica), wrappers `_select_item`, `_select_event`, `_select_item_reminder`
- Validación de params: `_validate_add_params()`, `_prompt_and_validate_ring()`
- Dispatchers: helpers `_ga()`, `_add_args()`, `_drop_args()`, `_edit_args()`
- Al añadir features: actualizar CHULETA.md, TUTORIAL.md, README.md

## Documentación

- `CHULETA.md` — referencia completa de comandos (la usa `orbit help` y `orbit claude`)
- `TUTORIAL.md` — tutorial para nuevos usuarios
- `README.md` — visión general y referencia rápida
- `SETUP.md` — instrucciones de instalación

## Estado actual (v0.26.0, 2026-03-26)

### Próximo: Cronogramas (diseño cerrado, pendiente de implementar)
- Nuevo tipo: cronograma = tareas anidadas con dependencias y duración temporal
- Fichero propio: `cronos/crono-<nombre>.md`, enlazado desde `## 📊 Cronogramas` en agenda.md
- Formato lista indentada: `- [ ] 1.1 Título | inicio | duración`
- Inicio: fecha ISO, semana ISO, semana+día (`2026-W12-wed`), o `after:<índice>`
- Duración: `Nd`, `NW`; tareas padre se calculan de hijas
- Doctor: índices únicos, deps válidas, sin ciclos, hojas con inicio+duración
- Fase 1: parser, cálculo fechas, doctor, `crono show/add/list/done/check`
- Fase 2: Gantt ANSI terminal
- Fase 3: gsync (pendiente de decisión)
- Diseño completo en `~/🚀orbit-ws/💻software/💻orbit/notes/2026-03-21_output_cronograma.md`

### v0.26.0 (2026-03-26)
- **Federación de workspaces**: lectura cruzada entre workspaces via `federation.json`
  - Comandos de lectura (panel, agenda, report, ls, search) incluyen federados por defecto
  - `--no-fed` para desactivar; escritura siempre local
  - Items federados con emoji del workspace (🌿); proyectos locales con link a project.md
  - Ring startup programa recordatorios de ambos workspaces
- **Panel y agenda en formato tabla markdown** (prioridad, agenda por día)
- **Vencidas agrupadas en hoy** con fecha original: `(📅2026-03-22) ⚠️`
- **`orbit agenda --open`** escribe a `agenda.md` (fijable en Obsidian)
- **Editor configurable en `orbit.json`**: `"editor": "obsidian"`
  - Prioridad: `ORBIT_EDITOR` env → `orbit.json` → sistema
- **Limpieza Typora → Obsidian** en comentarios y help text
- **Secciones con separadores** (`---`) en panel y agenda markdown
- **`## Calendario`** como sección explícita en panel y agenda
- **Exact match ignora emoji de tipo**: `igfae` → `⚙️igfae` sin ambigüedad
- **`project create`**: avisa si nombre similar a proyecto existente
- **Doctor**: muestra preview del texto de la línea problemática

### v0.23.0 (2026-03-21)
- `ev add/edit --end-date` — alias explícito de `--end` (claridad)
- `ev add/edit --end-time HH:MM` — hora de fin separada (se combina con `--time` → `HH:MM-HH:MM`)
  - Si no hay `--time`, usa `09:00` como inicio por defecto
- `orbit ls tasks --unplanned` — filtra tareas sin fecha (futuribles)
- Doctor pre-check en `orbit commit`:
  - Valida agendas/logbooks antes de commitear
  - Muestra problemas y pregunta si continuar `[s/N]`
  - Ejecuta reconciliación gsync y reporta drift
- Reconciliación gsync por título (`reconcile_gsync_renames`):
  - Detecta cuando el usuario cambia el título de una cita editando el markdown
  - Matchea keys huérfanas con items que comparten fecha/recur pero título diferente
  - Migra Google IDs al nuevo key, actualiza snapshot, re-sincroniza
  - Se ejecuta automáticamente en cada commit

### v0.22.0 (2026-03-20)
- `orbit panel [week|month]` — dashboard dinámico (prioridad, agenda, actividad)
  - Calendario ANSI en terminal, markdown table para `--open` (Typora)
  - Prioridad: alta (con motivo), urgente (tareas/eventos en periodo), hitos del mes
  - Agenda: ordenada por hora, agrupada por día en semana/mes. Tareas como `[ ]`
  - Actividad: logbook entries del periodo por proyecto
  - `--open` escribe a `panel.md` (no `cmd.md`)
- `project priority` pregunta motivo al poner alta (`--reason`)
  - Motivo en `project.md`: `- Prioridad: 🔴 Alta — Paper deadline`
- `--append proyecto:nota` en report, agenda, view, search, ls, panel — añade salida a nota

### v0.21.0 (2026-03-20)
- `orbit date` — fecha YYYY-MM-DD al portapapeles
- `orbit week` — semana ISO YYYY-Wnn al portapapeles
- `orbit report today/week/month` — atajos de periodo
- `orbit link proj file --from otro_proj` — enlaces relativos entre proyectos (Typora)
- `orbit note --no-date` — sin prefijo de fecha, sigue registrando en logbook
- Eliminado `--no-log` de note (siempre registra)
- `_parse_period` soporta ISO week (`YYYY-Wnn`)
- Fix: `NameError: time` en edición de recordatorios
- Fix: tests preexistentes en `test_notes_commit.py` (prefijo de fecha)

### v0.20.0 (2026-03-19)
- `orbit render` — renderizado estático MD→HTML al cloud para acceso móvil
  - `core/render.py`: conversor con KaTeX (LaTeX), CSS académico responsive
  - `core/orbit.css`: estilo compartido en la raíz del cloud
  - Dashboard: `index.html` (hub), `agenda.html` (calendario 2 semanas), `proyectos.html`
  - Auto-render en background tras cada `commit` (`cloudsync.py`)
  - `orbit render [project] [--full]` para renderizado manual
- Cloud inbox: `inbox.txt` (no .md) para edición desde móvil (Drive/OneDrive Android)
  - `inbox.py` busca `inbox.txt` primero, fallback a `inbox.md`
  - Orbit los recoge al arrancar la shell
- `orbit link <proyecto>` — link markdown al portapapeles
- Fix: `_reminders_on()` no evaluaba recurrencia (`🔄weekdays`) — ahora usa `_next_occurrence()`
- Cloud solo tiene HTML + inbox.txt — los .md no se copian
- Limitación: visores de Drive/OneDrive Android no siguen links entre HTMLs

### v0.19.1 (2026-03-18)
- Fix: `_build_parser()` — `main()` shadowed causaba `NameError` al arrancar
- Fix: `edit` en citas recurrentes ahora pregunta ocurrencia vs serie (`-o`/`-s`/`--force`)
  - `-o`: crea copia no-recurrente con edits + avanza la serie
  - `-s`: edita la serie en sitio
  - `--force`: equivale a `-o` (opción segura)
  - Helper compartido: `_ask_edit_occurrence_or_series()`
- Migración de agendas de orbit-ps al formato emoji (⏰🔄🔔☁️)

### v0.19.0 (2026-03-18)
- `reminder` promovido a ciudadano de primera clase (edit, drop, log, ls, --desc)
- Flags `-o`/`-s` en todos los drop para recurrentes
- Disambiguación interactiva cuando hay múltiples coincidencias
- Mac Reminders: formato con emojis, sync en edit/drop, startup programa las 4 citas
- gsync resiliente (error por item, no por lote)
- Doctor muestra línea problemática
- Prompt de ring al crear citas con hora
- Deliver a cloud por defecto al adjuntar fichero
- `task log` / `ms log` / `reminder log` (crear logbook entry desde cita)
- Alias `rem` para `reminder`
- Refactorización: `run_command()`, `track_operation`, `_validate_add_params`,
  `_select_from_list`, dispatchers simplificados, args unificados

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

## Estado actual (v0.29.5, 2026-05-11)

### v0.29.5 (2026-05-11) — `ev log` propaga agenda y zoom al logbook
- **`ev log`**: cuando el evento tiene notas `📋` (agenda/indico) o `🚪` (room/zoom), aparecen como líneas indentadas debajo de la entrada principal del logbook. Formato:
  ```
  2026-05-10 📅 Project kickoff #evento
    [📋](https://indico.cern.ch/event/12345)
    [📹](https://zoom.us/j/9999)
  ```
  Los iconos son markdown clickable (misma convención que `event_indicators(markdown=True)` y que el panel/agenda renders). Para rooms físicos (texto plano, sin URL) se escribe `  🚪 Aula A1-01` sin link.
- **API**: `format_entry`/`add_entry` reciben un parámetro nuevo `continuations: Optional[list[str]]`. Es general — cualquier tipo de entrada puede llevar continuations, pero hoy solo `ev log` las usa.

### v0.29.4 (2026-05-11) — sin link de GitHub en descripciones
- **`_project_description`** ahora devuelve solo `Proyecto: <name>` — el link a GitHub ya no se incluye. Aplica a partir de la próxima sincronización: los eventos ya existentes mantienen su URL hasta que se vuelvan a sincronizar (sin migración explícita).
- **`_project_url`** queda dormante en código por si se quiere reutilizar el scaffolding para un futuro `cloud_url` u otro link. La config `repo_url` en `calendar-sync.json` se ignora silenciosamente; se puede borrar a mano si se quiere.

### v0.29.3 (2026-05-11) — cronogramas al calendario de events
- **Routing**: `_sync_cronos_for_project` ahora soporta dos backends. Bajo `reminders_backend: "calendar"` (default v0.29) cada cronograma se sube como evento 0-min al calendario per-tipo de events (`config["calendars"][tipo]`, fallback `default`). Bajo `"reminders"` mantiene la rama legacy a Reminders.app.
- **Render**: igual que antes — 1 evento por cronograma con desc `[proj] 📊 crono-<n>: <leaf desc>` y due = deadline de la próxima hoja abierta. Vencidas no avanzan (siguen viéndose en su fecha original).
- **All done**: en backend calendar, borra el evento del calendario y limpia `ids["_cronos"][name]`. En backend reminders, marca el reminder completed (comportamiento legacy).
- **Migración auto**: si `_cronos[name]` tiene `gtask_id` legacy y Reminders.app está corriendo, lo borra de Reminders por orbit-id (best-effort), pone el `gcal_id` nuevo en su lugar y elimina el `gtask_id` del JSON. Si Reminders.app está cerrado, salta el cleanup y solo crea en Calendar (el orphan en Reminders se irá cuando esté abierta).
- **Storage**: misma namespace `ids["_cronos"][crono_name]`. Campos: `gcal_id` (nuevo) o `gtask_id` (legacy), `orbit_id`, `leaf`.
- **`orbit gsync` gating**: la llamada a `_sync_cronos_for_project` ya no está dentro de `if rem_app_ok:` — corre cuando hay Calendar.app O Reminders.app disponible.

### v0.29.2 (2026-05-11) — milestones al calendario de events
- **Routing**: `sync_item(item, "milestone")` ahora va al calendario per-tipo de events (`config["calendars"][tipo]`, fallback a `default`), no al calendario "agenda" del workspace. Las ms ya no se pierden entre tasks/reminders en el calendario común.
- **Render**: idéntico al anterior — 0-min event con prefijo `🏁` (vía `_sync_one_agenda_event` / `_agenda_props_for_calendar_app`). Sin RRULE (orbit avanza ocurrencias localmente). Alarma al inicio o según `--ring`.
- **Storage**: `_agenda_storage_key(item, "milestone")` sigue siendo `milestone::desc::date` — no choca con events del mismo desc+date en el mismo proyecto.
- **Migración auto**: cuando `sync_item(ms)` ve un `gcal_id` previo y crea uno nuevo (señal de que el viejo apuntaba al calendario agenda), borra el viejo de `agenda_cal` automáticamente. Idempotente. En terminal (`done`/`cancelled`), intenta borrar de ambos calendarios. Sin comando extra.
- **Tareas y reminders**: sin cambios — siguen en el calendario agenda del workspace.

### v0.29.1 (2026-05-11) — fix: sync inmediato de siguiente ocurrencia
- **Bug**: al completar (`task done`/`ms done`) o avanzar (drop) una cita recurrente, orbit creaba la siguiente ocurrencia en `agenda.md` pero no la sincronizaba a Calendar — solo aparecía tras `gsync` o reinicio. En v0.29 (backend=calendar) esto rompía el contrato "calendar = render en vivo de lo pending".
- **Fix** (`core/agenda_cmds.py`): `run_task_done`, `run_ms_done`, `run_reminder_drop` y `_generic_drop` ahora llaman `sync_item` también sobre la nueva ocurrencia, después de sincronizar la antigua (orden: vieja → libera slot → nueva crea evento limpio).
- **`run_ms_done`**: además ahora avanza recurrencia (antes solo marcaba done). Mismo patrón que `run_task_done`.
- **API**: `_advance_recurrence` ahora devuelve `(info_str, new_item or None)` para que el caller pueda sincronizar el nuevo item.
- **Tests**: `tests/test_recurrence_sync.py` (8 tests) cubre task/ms done, task drop recurrente, reminder advance, y casos sin recur o pasando `until`.

### v0.29.0 (2026-05-10) — agenda backend = Calendar.app
- **Nuevo backend único**: tasks/ms/reminders → eventos de 0 min en un calendario "agenda" por workspace (e.g. `🚀orbit-ws-rem`). Alarma vía `display alarm` del evento + CalendarAgent del sistema. Calendar.app no necesita estar abierta. Reminders.app deja de usarse (excepto cronogramas, todavía).
- **Config**: `reminders_backend: "calendar" | "reminders"` y `agenda_calendar: "<nombre>"` en `calendar-sync.json`. Default `"calendar"` para fresh installs y configs sin la key.
- **Coexistencia**: el backend `"reminders"` queda dormante en código (rama legacy en `_sync_one_to_reminders` y todo el path `core/ring.py`/`agenda_cmds.py` con guard `_agenda_via_calendar()`). Se puede revertir cambiando el flag.
- **Migración one-shot**: `orbit gsync --migrate-rem-to-calendar [--dry-run]`. Sube items pending a Calendar, borra los equivalentes en Reminders.app por orbit-id, mueve `gtask_id` → `gcal_id` en `.gsync-ids.json` con prefijo `task::`/`milestone::`/`reminder::`. Idempotente.
- **Recurrencia**: orbit avanza ocurrencias localmente (un evento por ocurrencia). No se usa RRULE para tasks/ms/rem — solo eventos. Razón: orbit es la verdad y `task done` ya genera la siguiente.
- **Alarmas**: por defecto al inicio (`alarm_minutes=0`). `--ring 15m` → alarma 15 min antes (mismo cálculo que para events).
- **Storage key**: `f"{kind}::{_item_key(item)}"` en `.gsync-ids.json` para evitar colisión con events que compartan desc+date.
- **Done/cancelled → delete**: cuando una task/ms se marca `done`/`cancelled` (o reminder `cancelled`), `sync_item` borra el evento del calendario y limpia su entry de `.gsync-ids.json`. El calendario refleja sólo lo pending.

## Estado anterior (v0.26.0, 2026-03-26)

### Deprecado: Buzón (inbox)
- `core/inbox.py` sigue en el repo pero ya no se llama desde shell/render/cloudsync
- Motivo: los visores móviles de Drive/OneDrive no permiten editar `inbox.txt` cómodamente
- Reactivar requiere: restaurar `startup_inbox_check()` en shell, `ensure_cloud_inboxes()` en render/cloudsync, link "📬 Buzón" en nav/dashboard

### Próximo: Cronogramas (diseño cerrado, pendiente de implementar)
- Nuevo tipo: cronograma = tareas anidadas con dependencias y duración temporal
- Fichero propio: `cronos/crono-<nombre>.md`, enlazado desde `## 📊 Cronogramas` en agenda.md
- Formato lista indentada: `- [ ] 1.1 Título | inicio | duración`
- Inicio: fecha ISO, semana ISO, semana+día (`2026-W12-wed`), o `after:<índice>`
- Duración: `Nd`, `NW`; tareas padre se calculan de hijas
- Doctor: índices únicos, deps válidas, sin ciclos, hojas con inicio+duración
- Fase 1: parser, cálculo fechas, doctor, `crono show/add/list/done/check` ✅
- Fase 2: Gantt ANSI terminal, reindex, edit, after herencia, panel progress, done interactivo ✅
- Fase 3: gsync (pendiente de decisión)
- Diseño completo en `~/🚀orbit-ws/💻software/💻orbit/notes/2026-03-21_output_cronograma.md`

### v0.28.0 (2026-05-10)
- **`orbit reorganize`** — modo interactivo para triage de pendientes (drop/done/fecha/hora/skip), con filtros `type`, `--project`, `--period`, y `--undated` para mostrar undated. Refresca dash al salir. Llama por debajo a los runners ya existentes.
- **`orbit-id` como identidad estable**: tag `[orbit:xxx]` (8 hex) embebido en `agenda.md`, body de Reminder y description de Calendar. Match por id sobrevive renames, cambios de fecha, recurrencia, timeouts AppleScript. Resuelve el bug crónico de duplicados.
- **Migración de keys recurrentes v1→v2** (`desc::🔄recur::date`): permite múltiples series con el mismo título (e.g. natación lun/mié/vie). `_migrate_recurring_keys` cubre la transición automáticamente.
- **Drop de markers redundantes**: ☁️/synced y prefijo `🚀`/`🌿` ya no se escriben en agenda.md ni en summaries de Reminder/Calendar (la lista/calendar ya identifica el workspace).
- **Phase 2A complete**: tasks/ms/reminders/cronogramas → Reminders.app vía AppleScript. Cronograma G: 1 reminder por crono con due = próxima hoja no completada (vencidas no avanzan).
- **`📹` para meeting URLs**: `--room URL` muestra cámara, `--room "Aula A1-01"` muestra puerta 🚪.
- **Auto-advance recurrentes vencidas en startup/00:00** (cambio de día detectado al volver al prompt) + gsync_background tras avance.
- **Fuente de verdad**: orbit es la verdad, Calendar/Reminders son render + alarmas. Reverse-sync (`gpull`) implementado y descartado en la misma sesión — código queda dormante en `core/gimport.py`.
- **Performance**: `_SYNC_TIMEOUT` reducido a 2s (sync continúa en bg), `gpull` optimizado a 3-5s con server-side filter.
- **`gsync <project>`**: filtro por proyecto en push.
- **Parser**: índices con punto final (`1.`), `+N`/`-N` short-form para fechas (suma N días desde hoy), `viernes`/`hoy` ya soportados consistentemente en todos los entry points.

### v0.27.0 (2026-04-16)
- **Cronogramas fase 2**: gantt, reindex, edit, after herencia, panel progress, done interactivo
  - `crono gantt`: vista progreso (DAG) o timeline (fechas), `--progress`/`--timeline`
  - `crono reindex`: renumera índices y actualiza `after:` automáticamente
  - `crono edit`: abre cronograma en editor
  - `crono done` interactivo: sin índice muestra lista, acepta texto parcial
  - Herencia de `after:` del padre a hojas sin inicio propio
  - Indentación flexible: 2-space, 4-space, tabs (autodetección)
  - Panel: sección `📊 Cronogramas` con barra de progreso por cronograma
  - Colores daltonismo-safe: azul/amarillo/gris (sin rojo/verde)
- **gsync**: flags `sync_tasks`/`sync_milestones` independientes en `google-sync.json`
  - Permite desactivar tasks pero mantener milestones en Google Tasks

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

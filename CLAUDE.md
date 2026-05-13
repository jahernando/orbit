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

## Estado actual (v0.33.0, 2026-05-12)

### v0.33.0 (2026-05-12) — Fase 2: AppleScript-write dormante + ics-only
- **Motivación**: validada la fase 1 (.ics emitido por orbit, Calendar.app suscrita a la URL pública de OneDrive en `🚀orbit-ws`), el camino AppleScript-write deja de tener sentido. Era una fuente recurrente de drift y `calsync` v0.31 fue un parche sobre el problema en vez de la solución. La verdad sigue siendo `agenda.md`, la presentación es `.ics`, y Calendar.app no edita nada porque la suscripción es read-only por construcción.
- **Flag `applescript_writes` en `calendar-sync.json`** (default `false`):
  - Helper: `core.gsync._applescript_writes_enabled(config=None)`.
  - Activo (`true`): camino legacy completo (sync_item AppleScript, calsync, ☁️ marker, gsync-failures journal, gsync_background, etc.).
  - Inactivo (`false`, default): early-return en `sync_item`, `reconcile_gsync_renames`, `check_gsync_drift`, `gsync_background`, `delete_gcal_event`, `run_gsync`, `run_calsync`. El doctor salta el pass de failures. Los helpers internos (`_create/update/delete_calendar_event`, `_sync_one_agenda_event`, etc.) siguen en el repo dormantes — sin tocar — siguiendo el patrón de [[feedback_dormant_deprecation]].
  - **Cómo revivir**: añade `"applescript_writes": true` a `calendar-sync.json` del workspace. No hace falta nada más; los entry points vuelven a hacer su antiguo trabajo.
- **Marker `☁️`**: deja de escribirse en formatters (`_format_task_line`, `_format_event_line`, `_format_reminder_line`). Parsers lo siguen reconociendo (para no romper agendas existentes) pero el campo `cloud_verified` queda vestigial. Existe un script one-shot: `python scripts/strip_cloud_marker.py` (con `--dry-run`) que round-tripéa cada agenda del workspace para eliminar el marker físicamente. Ya ejecutado en orbit-ws.
- **`orbit gsync` y `orbit calsync` siguen visibles en el CLI**, pero imprimen un aviso de deprecación y `return 0` cuando el flag está off. CLI usable solo si reactivas explícitamente.
- **Duraciones sintéticas en `.ics`** (`core/ics.py:_DEFAULT_DURATION_MIN`): event=60, milestone=60, task=60, cronograma=60, reminder=5. Aplican solo al `.ics` (no a `agenda.md`); permiten que los bloques sean visibles en cualquier cliente de calendar. Eventos con `--time HH:MM-HH:MM` o `--end-time` respetan la duración real.
- **`orbit_id` en `DESCRIPTION` del VEVENT**: añadido al final como `[orbit:xxxxxxxx]` para que sea referenciable desde la UI de cualquier calendario (Calendar.app no muestra `X-*` custom props). El `X-ORBIT-ID` y el UID (`<orbit_id>@orbit`) siguen presentes para parsers automatizados.
- **`orbit ics --validate`** (nuevo): dry-run. Renderiza buckets y per-project counting VEVENTs, no escribe nada. Útil para verificar el estado antes de un render real o para debugging de buckets.
- **`orbit doctor` añade check de frescura .ics**: avisa si algún bucket `.ics` tiene más de 24h sin actualizar (síntoma de que el hook render no se está disparando).
- **Buckets per-workspace finales en orbit-ws** (decididos durante validación de fase 1):
  ```json
  "ics_buckets": {
    "events": ["event"],
    "ms":     ["milestone"],
    "agenda": ["task", "reminder", "cronograma"]
  }
  ```
  Tres URLs públicos OneDrive distintos → Calendar.app los suscribe como tres calendarios separados, cada uno con su color. `ms` quedó como calendario propio para que los hitos destaquen visualmente; `cronograma` se movió de `events` a `agenda` (semánticamente: tarea con deadline, no bloque programado).
- **Receta OneDrive Share → suscripción** (USC tenant — `nubeusc-my.sharepoint.com`):
  1. En OneDrive web, click derecho sobre el `.ics` → Compartir → `Cualquiera con el enlace` (no `Personas de la USC`).
  2. Copia el enlace (formato `:u:/g/personal/.../<id>?e=<token>` — la `g` indica anonymous guest).
  3. Convierte: `https://` → `webcal://` + añade `&download=1` al final (fuerza SharePoint a devolver el .ics crudo en lugar del visor HTML).
  4. En Calendar.app: `Archivo → Nueva suscripción de calendario` → pega el `webcal://` → Ubicación: `En mi Mac` (Apple quitó iCloud del diálogo ~2023; para propagar a iPhone/iPad usa `icloud.com/calendar` web).
  5. Refresh: `Cada 5 minutos`. Color a elección.
- **Convivencia con la fase 1**: `core/ics.py` y `core/render.py` siguen idénticos. `_emit_ics` se sigue disparando en `render_all`/`render_changed`/`run_dash`. El cambio de fase 2 es puramente apagar el AppleScript-write — nada del render se ve afectado.
- **Tests**: TestSetCloudVerified en `tests/test_sync_verify.py` quedó marcada `@pytest.mark.skip` (documentación viva del contrato si se revive el marker). `conftest.py` patchea `_applescript_writes_enabled` a True por defecto para que los tests legacy de gsync sigan ejecutándose. Suite: 1579 pass, 4 skipped.

### v0.32.0 (2026-05-12) — Fase 1: export iCalendar (.ics) y subscripciones
- **Motivación**: independizarse del AppleScript-write de Calendar.app. iCalendar (RFC 5545) es universal — Calendar.app, Google Calendar, Outlook, Thunderbird todos lo entienden. La idea es: `orbit render` emite `.ics`, Calendar.app se suscribe, refresh automático cada 5 min (o `reload calendars` AppleScript de solo lectura para latencia inmediata). El `sync_item` AppleScript-write entra en deprecación natural en fase 2.
- **`core/ics.py`** (~570 líneas, autocontenido):
  - `render_vevent(item, kind, project_name, occurrence_date=...)` — serializa una cita a un bloque `VEVENT` con `UID`, `DTSTART`/`DTEND` (floating local), `SUMMARY`, `DESCRIPTION`, `URL`/`LOCATION` (meeting URLs), `VALARM`, y custom props `X-ORBIT-ID` / `X-ORBIT-PROJECT` / `X-ORBIT-KIND` / `CATEGORIES`.
  - `_expand_dates(item, window_start, window_end)` — expansión de recurrencia en VEVENTs individuales (no RRULE). Reutiliza `_next_occurrence` de `agenda_cmds`. Cap en 2000 iteraciones por seguridad. Ventana default: ±180 días.
  - Helpers RFC: `_escape` (TEXT-type), `_fold` (line folding ≤75 octets respetando UTF-8 multibyte), `_fmt_dt_local` (floating local sin TZ), `_fmt_date` (VALUE=DATE all-day).
  - `_calendar_wrapper(name, body)` — envuelve VEVENTs en `VCALENDAR` con `PRODID`, `VERSION:2.0`, `METHOD:PUBLISH`, `X-WR-CALNAME`.
- **Topología**: `cloud_root/calendar/`:
  - `<bucket>.ics` — agregadores de workspace (default: `agenda.ics` = task+rem, `events.ics` = ev+ms+crono)
  - `projects/<proyecto>.ics` — per-proyecto, TODAS las citas (compartir/refs puntuales)
- **`ics_buckets` configurable** en `calendar-sync.json`. `doctor` valida que cada kind aparezca en exactamente un bucket. Pegado al final del check de gsync drift.
- **Snapshot diff**: cada `.ics` escribe en paralelo un `.ics.snapshot` (versión anterior). `_parse_vevents` deserializa eventos a `{uid: {prop: val}}`, ignora `DTSTAMP` (UTC-now → no-determinismo) y `unfold`-ea las líneas plegadas. `diff_snapshot(current, snapshot)` devuelve `{added, removed, changed}` por UID. Permite saber "qué cambió desde el último render" sin invertir la dirección de verdad (agenda.md sigue siendo truth, .ics es transport + memory).
- **Hook en `core/render.py`**: `render_all` y `render_changed` llaman a `_emit_ics(cloud_root)` al final → `core.ics.write_workspace` → escribe todos los `.ics`, hace diff vs snapshot, imprime resumen, dispara `reload calendars` AppleScript (read-only, no escribe eventos). Fallos en `_emit_ics` no bloquean el render HTML.
- **`orbit ics` CLI**: `orbit ics <proyecto> [--out PATH]` para export ad-hoc; `orbit ics --bucket NAME` para un bucket; `orbit ics --workspace` para regenerar todo (usa `cloud_root`). Dispatcher: `cmd_ics` en `orbit.py:1003-1042`.
- **UIDs estables**: `<orbit_id>@orbit` (no recurrente) o `<orbit_id>-<date>@orbit` (occurrence). Critical para que Calendar.app vea "evento existente, posible update" en vez de "delete + create" (resetearía alarmas).
- **Decisiones de diseño confirmadas con el usuario**:
  - **Verdad sigue siendo `agenda.md`**, no `.ics` (el cambio inverso fue considerado y descartado: rompe editabilidad markdown, diffs git legibles, workflow móvil).
  - **Recurrencia = expansión** (no RRULE) — simplifica overrides single-occurrence sin EXDATE/RECURRENCE-ID.
  - **Floating local time** (no `TZID=` ni Z) — replica el modelo actual; cambiable cuando alguien use orbit viajando.
  - **Ventana ±180 días** — ~700KB peor caso para una serie diaria-año.
  - **Buckets per-workspace, no per-tipo de proyecto** — simplifica vs topología actual de Calendar.app, alinea con cómo el usuario piensa (por proyecto, no por tipo).
- **Tests**: `tests/test_ics.py` (40 tests) — escape/fold/dt format, UID stability, VEVENT por kind, alarm block, recurrence expansion, all-day, URL passthrough, bucket validation, snapshot diff (DTSTAMP ignored, added/removed/changed), write_workspace filesystem. Suite total: **1576 pass**.
- **Convivencia**: `gsync` (AppleScript-write) sigue corriendo en paralelo. La idea es validar fase 1 (subscripción + refresh) antes de marcar las funciones write como dormantes. Pasos para fase 2 (cuando se pruebe que funciona en `phd-diego` con creación/borrado/edit de serie y de ocurrencia única):
  1. Marcar dormante en `core/gsync.py`: `_create_calendar_event`, `_update_calendar_event`, `_delete_calendar_event`, todos los caminos write en `sync_item`.
  2. `calsync` mantiene su rol como auditor de calendarios externos (no orbit-managed) — el orbit-managed pasa a estar libre de drift por construcción.
  3. `ics-share` para compartir eventos puntuales por email/Slack.

### v0.31.0 (2026-05-12) — `orbit calsync`: auditoría + reconciliación atributo a atributo
- **Motivación**: `gsync` empuja en bloque y silenciosamente; cuando algo divergía (edit en iPhone, fallo de sync no recuperado, etc.) no había forma cómoda de cuadrarlo sin retipearlo. v0.30 dejó el ☁️ como señal visible pero no hay UI para resolver drifts. `calsync` es esa UI.
- **Comando nuevo**: `orbit calsync <proyecto> [--type LIST] [--all|--pending] [--dry-run]`.
- **Diseño "auditor con pull explícito" (opción B)**: orbit sigue siendo la verdad (v0.28), pero `2-cal` es azúcar sintáctico para "`3-input` precargado con el valor de Calendar" → cada adopción es decisión humana por atributo, no auto-pull. Pasa por la misma ruta que `3-input` (`_apply_pull`), así no se abre la puerta a un `gpull` futuro.
- **Flujo por cita**:
  1. Bulk read de cada calendario afectado (`_fetch_window`, 1 AppleScript por calendario, window `today-30d..today+365d`).
  2. Match por `orbit-id` (no por título+fecha → robusto a renames).
  3. Diff de `summary`, `start`, `end`, `description`. `end` sintético (`= start+1min` de tasks/ms/rem v0.29.9) se ignora; `2-cal` también bloqueado para `end` cuando el evento de Calendar es también sintético (evita adoptar el `+1min` ficticio).
  4. Tabla `attr | orbit | calendar`. Por atributo: `[1-orbit / 2-cal / 3-input / s-skip]`.
- **Modos** (mutex `--all`/`--pending`):
  - default: salta los ☁️ verificados.
  - `--all`: incluye verificados (auditoría completa).
  - `--pending`: subset → orbit-id sin ☁️ (los sospechosos según v0.30).
- **Filtros**: `--type task,ms,ev,rem,crono` (separados por coma). Aliases CLI mapean a internos vía `_TYPE_ALIASES`.
- **Cronogramas**: comparten flujo de diff pero solo aceptan `1-orbit` y `s-skip` (su verdad vive en `cronos/crono-<n>.md`, no en agenda.md → pull no aplica). Synthesis on-the-fly imita la de `gsync._sync_cronos_for_project`.
- **Huérfanos**: eventos en Calendar sin `[orbit:xxx]` → report-only al final con `summary`, `start_iso` y calendario. Sin auto-import en v1 (decisión explícita del usuario para evitar interrupciones no pedidas).
- **Resumen**: `N ☁️ / M corregidos / K skipped / E ausentes / F errores / H huérfanos`.
- **Implementación**: `core/calsync.py` (~570 líneas, autocontenido). Solo importa helpers existentes de `gsync` (`_osa`, `_esc`, `_FETCH_FIELD_SEP/SEP`, `_parse_orbit_tag`, `_project_description`, `_item_description`, `_load_config`, `_get_project_tipo`, `_agenda_calendar_name`, `sync_item`, `_calendar_app_running`). El push usa `sync_item` tal cual; el pull es `_apply_pull` que muta `agenda.md` y luego llama `sync_item` para empujar el nuevo valor.
- **Tests**: `tests/test_calsync.py` (51 tests) — parse de filtros, expected summary/start/end por tipo, diff (drift, ignore_end, strip orbit-tag), prompt routing (1/2/3/s y bloqueos), apply_pull para todas las attrs y kinds, run_calsync end-to-end con _fetch_window mockeado (mutex, verified short-circuit, orphan report, missing event). Suite total: 1536 pass.

### v0.30.0 (2026-05-11) — verificación post-sync con marker ☁️ y journal de fallos
- **Problema**: `sync_item` lanzaba AppleScript en daemon thread y devolvía inmediatamente. Cualquier error (start/end inválido, evento en otro calendario, ApleEventHandler error, etc.) se perdía silenciosamente. El usuario veía orbit decir "✓ Tarea actualizada" pero Calendar no cambiaba.
- **Solución (A+B)**:
  1. **Verify post-sync**: tras la AppleScript de update/create, el mismo daemon thread hace un read-back del evento por uid (`_verify_calendar_event`). Compara start_iso y summary contra lo esperado. Si coinciden → éxito.
  2. **Marker ☁️**: si verify pasa, se añade `☁️` a la línea de la cita en `agenda.md`, justo antes de `[orbit:xxx]`. Cualquier edit (`_apply_edits`) borra el ☁️ inmediatamente → reaparece tras el siguiente verify exitoso.
  3. **Journal de fallos** (`.gsync-failures.json` por proyecto): si verify falla, se escribe `{when, orbit_id, kind, reason, expected}`. El marker no se pone (la ausencia es el signo visible).
  4. **Doctor check**: `orbit doctor` ahora reporta cuántas citas tienen fallos pendientes con la razón. Sugiere re-editar para relanzar el sync.
- **Estados visibles del usuario**:
  - **Sin marker, sin orbit_id** → nunca sincronizada.
  - **Sin marker, con orbit_id** → cambio pendiente / fallo (revisa doctor).
  - **Con ☁️ y orbit_id** → orbit y Calendar coinciden, verificado.
- **Parser y formatter**: `_parse_task_line`/`_parse_event_line`/`_parse_reminder_line` reconocen `☁️` y exponen `cloud_verified: bool`. Los formatters lo escriben antes del orbit-id.
- **Done/cancelled**: borra el evento de Calendar y limpia ☁️ + journal entry.
- **Limitaciones (TODO)**:
  - Falta `orbit gsync --retry` para reintentar entries del journal en lote.
  - Verify solo en backend calendar; reminders legacy no lo tiene.
  - Tests cubren el grueso (15 en `tests/test_sync_verify.py`), pero el wiring de `sync_item` confía en los tests de integración existentes.

### v0.29.9 (2026-05-11) — fix Calendar.app error -10025 en updates
- **Root cause**: los eventos de agenda se creaban con `start == end` (0-min markers). `make new event` lo acepta, pero `set start date of ev` valida la transición a-estado y rechaza con `error -10025 ("La fecha de inicio debe ser anterior a la fecha de finalización")` si quedaría `start >= end` en cualquier estado intermedio. Resultado: **ningún edit de hora se propagaba al evento existente**. El usuario veía Calendar congelado en la hora de la creación inicial (a menudo 9:00 por defecto).
- **Fix 1** (`_agenda_props_for_calendar_app`): `end_iso = start + 1 minuto`. Los eventos quedan visualmente discretos (1-min) pero satisfacen `start < end` estricto. Aplica también para nuevos eventos.
- **Fix 2** (`_update_calendar_event`): orden de actualización seguro. Antes de tocar start/end, se empuja `end` a un sentinel lejano (2099-12-31 23:59), luego se setea `start`, luego el `end` real. Cada paso intermedio mantiene `start < end` invariante, sin importar si la nueva hora es anterior o posterior a la existente.
- **Scripts/diagnóstico** (`scripts/`): nuevos `diagnose_calendar_sync.py` y `try_update_calendar_event.py` para futuros bugs de sync (no se distribuyen, viven en `scripts/`).
- **Tests**: actualizados los dos tests que asumían `end_iso == start_iso`. Suite: 1534 pasan.

### v0.29.8 (2026-05-11) — `reconcile_gsync_renames` respeta el prefijo `kind::`
- **Bug**: `reconcile_gsync_renames` (corre en cada `orbit commit`) calculaba `current_key = _item_key(item)` (formato legacy `desc::date`). Para tareas/ms/rem cuyo entry estaba en formato v0.29 (`task::desc::date` / `task::desc::🔄recur::date`), detectaba "rename" y revertía el entry al formato legacy — deshaciendo la migración de v0.29.6 en cada commit. Bucle infinito: sync_item migra a prefijo, commit revierte, etc.
- **Fix** (`core/gsync.py`): nuevo helper `_canonical_storage_key(item, kind)` que devuelve `_agenda_storage_key` para task/ms/rem y `_item_key` para event. `reconcile_gsync_renames` ahora compara contra el canónico, y el set `current_keys` (usado por el orphan detection del pass 2) también usa el canónico.
- **Tests**: `tests/test_v0230_improvements.py` añade 3 casos (migración legacy→prefijo, prefijo se mantiene, events siguen en formato legacy). Suite: 1534 pasan.

### v0.29.7 (2026-05-11) — fix orbit-id lookup en eventos de Calendar para recurrentes
- **Bug**: para tareas/ms/rem recurrentes, el tag en la descripción del evento de Calendar es `[orbit:xxx@date]` (con sufijo `@date` por ocurrencia). `_find_calendar_event_by_orbit_id` buscaba `[orbit:xxx]` (con `]` justo después del id) — sustring que no aparece en el tag recurrente. Resultado: editar tiempo/título de una tarea recurrente no encontraba el evento por orbit-id, caía a la búsqueda título+fecha con la **nueva** hora (que no matchea el evento existente con la vieja hora) y creaba un duplicado en Calendar.
- **Fix** (`core/gsync.py:_find_calendar_event_by_orbit_id`): la needle ahora es `[orbit:xxx` sin `]`, igual que `_find_reminder_by_orbit_id`. Matchea ambos formatos. El riesgo de falso positivo con 8 hex chars es despreciable.
- **Tests**: `tests/test_gsync_calendar_app.py::TestFindCalendarEventByOrbitIdNeedle`. Suite: 1531 pasan.

### v0.29.6 (2026-05-11) — fallback legacy-key en `sync_item`
- **Bug**: tareas/ms/rem cuyo entry en `.gsync-ids.json` quedó bajo la key legacy `desc::date` (pre-v0.29, o que escapó del `--migrate-rem-to-calendar`) no se reconocían en sync_item — el código nuevo buscaba `kind::desc::date`. Resultado: editar tiempo/título/etc no actualizaba el evento en Calendar (o creaba un duplicado al caer en la rama "create new").
- **Fix** (`core/gsync.py:sync_item`): si no hay entry bajo `_agenda_storage_key(item, kind)` pero sí hay uno bajo `_item_key(item)` con `gcal_id`, usarlo como `existing`. El siguiente save migra el entry al formato nuevo y `_purge_orbit_orphans` borra el legacy. Migración silenciosa, sin comando.
- **Save también detecta drift de snapshot**: antes la condición de save era `new_uid != existing.gcal_id` — perdía cambios de tiempo/desc cuando el uid se mantenía. Ahora se guarda cuando `gcal_id`, `snapshot` u `orbit_id` divergen del estado en `storage_key`. Cubre también el caso legacy donde el uid no cambia pero la key sí.
- **Tests**: `tests/test_gsync_agenda.py::TestLegacyKeyFallback` (2 tests). Suite: 1530 pasan.

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

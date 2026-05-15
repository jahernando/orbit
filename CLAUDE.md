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
    ring.py               ← parsing y helpers AppleScript-direct (legacy, gateado)
    ring_export.py        ← ring.json + invoke daemon (modelo declarativo v0.37)
    orbit_ring_daemon.py  ← EventKit upsert idempotente en Reminders.app
    ics.py / ics_share.py ← emisión de buckets .ics que Calendar.app subscribe
    doctor.py             ← validación de sintaxis de ficheros
    shell.py              ← shell interactivo
    startup.py            ← prompts de arranque (untracked, commit, code update)
    config.py             ← ORBIT_HOME, ORBIT_PROMPT, orbit.json
    log.py                ← logbook entries
    highlights.py         ← highlights CRUD
    project.py            ← gestión de proyectos
  tests/                  ← pytest, ~1567 tests

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

### Salida de citas (v0.38: gsync borrado)

Una sola dirección: orbit es source-of-truth, los backends consumen.

- **Calendar.app** (eventos / tasks-as-0min-events / reminders-as-0min-events): se suscribe a buckets `.ics` emitidos a `cloud_root/<workspace>/calendar/` por `ics.py` + `ics_share.py`. Read-only por construcción → no hay drift posible.
- **Reminders.app** (alarmas con ring): `ring_export` proyecta agenda.md → `<workspace>/.reminders/ring.json`. El daemon `orbit_ring_daemon.py` (EventKit) hace upsert idempotente. Una lista Reminders.app por workspace (default = nombre del directorio).
- Anteriormente había un push AppleScript-direct vía `gsync.py` + `calsync.py` (3673 ℓ); borrado en v0.38 tras 2 semanas de validación del modelo `.ics`. Ver DORMANT.md.

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

## Estado actual (v0.37.0, 2026-05-14)

### v0.37.0 (2026-05-14) — Ring desacoplado: ring.json + daemon EventKit + launchd

Sustituto del backend `reminders_backend: "reminders"` dormante de v0.29. Cierra las fases B–F de [RING.md](RING.md) (la fase A — mirror `.ics` + diff — ya estaba). [ADR-027](DECISIONS.md).

**Arquitectura declarativa**:
```
agenda.md (verdad)
   │
   ▼
orbit ring refresh / hook commit_post / hook shell_start
   │
   ▼
<workspace>/.reminders/ring.json   (gitignored, ventana rolling 7 días)
   │  (launchd WatchPaths o hook dispara el daemon)
   ▼
orbit_ring_daemon.py   (EventKit/PyObjC, NO AppleScript)
   │
   ▼
Reminders.app — lista por workspace (default: nombre del directorio del workspace)
   │  (iCloud sync gratis)
   ▼
iPhone / iPad
```

**Decisiones clave** (diff respecto a RING.md original):

- **Una lista por workspace** (`workspace_root.name`, e.g. `🚀orbit-ws`, `🌿orbit-ps`), no una única `Orbit Ring`. Coherente con "una vida = una lista" preexistente; permite silenciar contextos enteros.
- **EventKit/PyObjC**, no AppleScript: misma fiabilidad de Reminders.app (es el framework subyacente), sin timeouts de `osascript`, sin necesidad de app abierta, API estructurada testeable.
- **Items con orbit-tag únicamente**: el daemon **nunca** toca reminders sin `[orbit:xxx]` en notes. Items manuales del usuario en la misma lista están a salvo. Dedup defensivo si aparecen duplicados con mismo orbit_id.
- **Identidad por ocurrencia recurrente**: `<base_id>-<YYYY-MM-DD>`. Cada ocurrencia es un EKReminder distinto; `task done` regenera la siguiente ocurrencia y el próximo sweep limpia la vieja.

**Config en `orbit.json` del workspace**:
```json
"ring": {
  "enabled": true,           // false → vacía la lista del workspace (sweep)
  "days":    7,              // ventana rolling, clamped a [1, 30]
  "list":    "🚀orbit-ws"    // default = workspace_root.name
}
```

**Componentes nuevos**:
- `core/ring_export.py` (~300 LOC): `build_payload`, `write_payload`, `refresh_all`, `invoke_daemon`, `run_ring_refresh/status/install/uninstall`, `_action_ring_refresh`, `_load_ring_config`.
- `orbit_ring_daemon.py` (~200 LOC, standalone): EventKit upsert idempotente, dedup, agrupación por lista, manejo de TCC permission denied.
- `core/hooks_catalog.json`: nueva acción `ring_refresh` añadida a `commit_post.post` y `shell_start.post`.
- `core/doctor.py::_check_ring_health`: avisa de plist no instalado, TCC denied en stderr log reciente, ring.json viejo (>24h).
- `core/ring.py` antiguo queda **dormante** (la API `schedule_new_format_reminders` ya estaba marcada como deprecada; ahora aún más).

**CLI**:
```
orbit ring refresh [--no-daemon]   # regenera ring.json en todos los workspaces y aplica
orbit ring status                  # ring.json por workspace + estado del plist
orbit ring install                 # ~/Library/LaunchAgents/com.orbit.ring-daemon.plist
orbit ring uninstall               # descarga y elimina
```

**Triggers automáticos**:
- `shell_start` (acción `ring_refresh`)
- `commit_post` (acción `ring_refresh`)
- `launchctl WatchPaths` sobre cada `ring.json` → daemon (si instalado)
- `StartCalendarInterval` 00:05 → sweep nocturno (si instalado)

**Caveat TCC**: primera vez tras `orbit ring install`, macOS bloquea EventKit hasta que el usuario autorice el binario Python en *System Settings → Privacy & Security → Reminders*. Doctor lo detecta leyendo `~/Library/Logs/orbit/ring-daemon.stderr.log`.

**Tests**: `tests/test_ring_export.py` (45 tests). Suite: 1874 pass, 4 skipped.

**Migración**: las 3 listas obsoletas (`Orbit`, `🚀 orbit-ws` con espacio, `🌿 orbit-ps` con espacio) y `Orbit Ring` (modelo único original) borradas tras validación. Las listas nuevas son `🚀orbit-ws` y `🌿orbit-ps` (sin espacio).

**Dependencia nueva**: `pyobjc-framework-EventKit` (registrada en `DEPENDENCIES.md`).


## CI (2026-05-14)

GitHub Actions workflow en `.github/workflows/tests.yml`. Ejecuta `pytest -q` en cada push a `main` y en cada PR a `main`. Runner: `ubuntu-latest`, Python 3.11, deps mínimas (`pytest`, `markdown`). El daemon EventKit y los tests `uses_osa` corren sin tocar AppleScript real gracias a los stubs del autouse fixture en `tests/conftest.py`, así que la suite es 100% pasable en Linux.


## Historial anterior

Resumen muy breve de las últimas versiones; detalle completo en [CHANGELOG.md](CHANGELOG.md).

- **v0.36.0** (2026-05-14) — Notes propia/externa con symlinks relativos. Reemplaza el modelo tracked v0.34 (ADR-026 deroga ADR-024). `core/tracked.py` reescrito (~80 LOC), nuevo `note --from <path>`.
- **v0.35** (2026-05-14, sin tag) — Hook system shipped. F1-F7 migration: 17 acciones declarativas en `core/hooks_catalog.json`, modelo trigger → chain → [pre, core, post]. Doc en [HOOKSYSTEM.md](HOOKSYSTEM.md).
- **v0.34.0** (2026-05-13) — Tracked external files (predecesor de v0.36, derogado) + mirror local de `.ics` con `orbit ics --diff` (ADR-025).
- **v0.33.0** (2026-05-12) — AppleScript-write a Calendar dormante; `.ics`-only ya validado.
- **v0.32.0** (2026-05-12) — Export iCalendar y subscripciones Calendar.app.
- Versiones anteriores (v0.19 → v0.31) — ver [CHANGELOG.md](CHANGELOG.md).

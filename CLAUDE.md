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
  core/                   ← writers de la verdad + infra
    agenda_cmds.py        ← CRUD de las 4 citas (task, ms, ev, reminder)
    cartero_invoke.py     ← subprocess shim al satélite cartero (sin imports cruzados)
    shell.py              ← shell interactivo
    startup.py            ← prompts de arranque (untracked, commit, code update)
    config.py             ← ORBIT_HOME, ORBIT_PROMPT, orbit.json
    log.py                ← logbook entries
    highlights.py         ← highlights CRUD
    project.py            ← gestión de proyectos
    types.py              ← dataclasses compartidas entre core/ y views/ (Issue, …)
  views/                  ← readers de la verdad → artefactos derivados (regla en RULES.md)
    render/render.py      ← MD → HTML en cloud_root (+ orbit.css)
    doctor/doctor.py      ← validación de sintaxis / refs / entorno
    cal/ics.py + share.py ← emisión de buckets .ics que Calendar.app subscribe
    ring/export.py        ← ring.json + invoke daemon (modelo declarativo v0.37)
    ring/parse.py         ← parsing y helpers AppleScript-direct (legacy, gateado)
  satellites/             ← daemons externos, invocados por subprocess; cero imports de core/
    ring-daemon/daemon.py ← EventKit upsert idempotente en Reminders.app
    cartero/daemon.py     ← notificador de mail/Slack (poll + globito macOS)
    cartero/google_oauth.py ← OAuth helpers (Gmail), solo usados por cartero
  tests/                  ← pytest, ~1541 tests

~/🚀orbit-ws/             ← workspace de trabajo (privado)
~/🌿orbit-ps/             ← workspace personal (privado)
```

Reglas e invariantes del sistema en [RULES.md](RULES.md); decisiones arquitectónicas con su razonamiento en [DECISIONS.md](DECISIONS.md).

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
- **Reminders.app** (alarmas con ring): `ring_export` proyecta agenda.md → `<workspace>/.reminders/ring.json`. El daemon `satellites/ring-daemon/daemon.py` (EventKit) hace upsert idempotente. Una lista Reminders.app por workspace (default = nombre del directorio).
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

## Estado actual (v0.38.0, 2026-05-16)

Pulido arquitectónico mayor — 5 ADRs nuevos, separación core/views/, save flow unificado, secretary como tercera familia (junto a cartero y ring-daemon), wrap CLI completo, watchdog daemon, modo pretty para hooks.

### Tres ejes principales

**1. Separación `core/` vs `views/`** ([ADR-033](DECISIONS.md#adr-033--separación-core-writers-vs-views-readers))
`render`, `doctor`, `ics`, `ring` salen de `core/` a `views/{render,doctor,cal,ring}/`. Writers (core) escriben la verdad; viewers (views) leen y proyectan derivados. Regla: core no importa views salvo lazy. Más [ADR-034](DECISIONS.md#adr-034--save-como-verbo-de-cierre--chain-commit_post-unificado): `save` como verbo primario (alias legacy `commit`); chains `commit_pre`/`commit_post` con todas las acciones declarativas.

**2. Secretary + dashboard cloud unificado** ([ADR-035](DECISIONS.md#adr-035--viewssecretary-como-viewers-del-workspace--dashboard-cloud-unificado))
Nuevo `views/secretary/` con 5 viewers puros (panel, agenda-next, calendar, projects, report-summary). Outputs en `📋secretary/*.md`. Front-page del workspace: `workspace.md` estático (bootstrappeado por `orbit setup`). En cloud: `workspace.md → workspace.html` + `index.html` stub redirect (auto-open del browser preservado).

Config en `<workspace>/orbit.json`:
```json
"secretary": { "agenda_days": 14, "report_days": 14 }
```

**3. Wrap CLI + watchdog + pretty hooks** ([ADR-036](DECISIONS.md#adr-036--wrap-de-refresh-tras-mutación-cli-matriz-por-comando-sin-render) + [ADR-037](DECISIONS.md#adr-037--watchdog-doctor--full-refresh-periódico-tras-edición-externa))

Matriz tras mutación CLI:
- Citas (task/ms/ev/rem/crono/ics-import/email) → dash (coalescido 10s) + ring + ics(project_filter)
- log/hl/project → solo dash
- Render reservado para `save` (commit_post)

Watchdog daemon: cada tick (defecto 60min, configurable) → doctor primero; si issues → `.doctor-pending` + congelar derivados; si limpio → `_run_full_refresh_coalesced`. REPL surface el aviso al siguiente input. Config:
```json
"watchdog": { "enabled": true, "interval_minutes": 60 }
```

Modo pretty para chains: banner + tick + emoji + label + msg uniforme. Ejemplo:
```
━━━ Save · publicar ━━━
  ✓ 📋 Secretary       5 viewers
  ✓ 🔔 Ring            12 items
  ✓ 📅 Calendar (.ics) 8 buckets · 23 .ics
  ✓ ☁️ Render          29 .md → .html
```

### Otros cambios en v0.38

- **gsync borrado**: `gsync.py` + `calsync.py` (3673 ℓ AppleScript-write) eliminados tras 2 semanas de validación del modelo .ics. Cierra [ADR-018](DECISIONS.md#adr-018--sincronización-con-calendarapp-vía-ics-no-applescript-write).
- **Phase 3 + 4 del plan de simplificación**: `icalendar` lib (ADR-029), `python-dateutil` (ADR-030), `core/agenda/` subpaquete (ADR-031), seam `core/api.py` con funciones puras (ADR-032), noun-verb convention.
- **Satellites**: `ring-daemon` y `cartero` movidos a `orbit/satellites/`, uno por workspace.
- **link/import** como verbos primarios (alias de track/deliver).
- **Doctor 3-way model**: sintaxis + refs + entorno.

Para detalle de cada commit ver [CHANGELOG.md](CHANGELOG.md).


## CI (2026-05-14)

GitHub Actions workflow en `.github/workflows/tests.yml`. Ejecuta `pytest -q` en cada push a `main` y en cada PR a `main`. Runner: `ubuntu-latest`, Python 3.11, deps mínimas (`pytest`, `markdown`). El daemon EventKit y los tests `uses_osa` corren sin tocar AppleScript real gracias a los stubs del autouse fixture en `tests/conftest.py`, así que la suite es 100% pasable en Linux.


## Historial anterior

Resumen muy breve de las últimas versiones; detalle completo en [CHANGELOG.md](CHANGELOG.md).

- **v0.37.0** (2026-05-14) — Ring desacoplado: `ring.json` (gitignored, ventana rolling 7d) + daemon EventKit/PyObjC en `satellites/ring-daemon/` + launchd. Una lista Reminders.app por workspace; identidad por ocurrencia recurrente `<base_id>-<YYYY-MM-DD>`. ADR-027.
- **v0.36.0** (2026-05-14) — Notes propia/externa con symlinks relativos. Reemplaza el modelo tracked v0.34 (ADR-026 deroga ADR-024). `core/tracked.py` reescrito (~80 LOC), nuevo `note --from <path>`.
- **v0.35** (2026-05-14, sin tag) — Hook system shipped. F1-F7 migration: 17 acciones declarativas en `core/hooks_catalog.json`, modelo trigger → chain → [pre, core, post]. Doc en [HOOKSYSTEM.md](docs/HOOKSYSTEM.md).
- **v0.34.0** (2026-05-13) — Tracked external files (predecesor de v0.36, derogado) + mirror local de `.ics` con `orbit ics --diff` (ADR-025).
- **v0.33.0** (2026-05-12) — AppleScript-write a Calendar dormante; `.ics`-only ya validado.
- **v0.32.0** (2026-05-12) — Export iCalendar y subscripciones Calendar.app.
- Versiones anteriores (v0.19 → v0.31) — ver [CHANGELOG.md](CHANGELOG.md).

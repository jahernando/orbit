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
  tests/                  ← pytest, ~750 tests

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

Comandos uniformes: `add`, `drop`, `edit`, `list`.
Además: task/ms tienen `done`; ev tiene `log` (crear entrada de logbook desde evento).

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
- Tests con pytest, ~750 tests (2 fallan por dependencia de fecha, preexistentes)
- Ignorar `tests/test_notes_commit.py` y `tests/test_undo.py` si fallan por fecha
- Funciones públicas: `run_*` (dispatchers en orbit.py las llaman)
- Funciones internas: `_*` (prefijo underscore)
- Selección interactiva: `_select_item` (task/ms), `_select_event` (ev), `_select_item_reminder` (reminder)
- Al añadir features: actualizar CHULETA.md, TUTORIAL.md, README.md

## Documentación

- `CHULETA.md` — referencia completa de comandos (la usa `orbit help` y `orbit claude`)
- `TUTORIAL.md` — tutorial para nuevos usuarios
- `README.md` — visión general y referencia rápida
- `SETUP.md` — instrucciones de instalación

## Estado actual (v0.18.1, 2026-03-18)

Sesión de hoy — mejoras al sistema de citas:
- `reminder` promovido a ciudadano de primera clase (edit, drop, ls reminders)
- Flags `-o`/`-s` en todos los drop para recurrentes
- Disambiguación interactiva cuando hay múltiples coincidencias
- Mac Reminders: formato con emojis, sync en edit/drop, startup programa las 4 citas
- gsync resiliente (error por evento, no por lote)
- Doctor muestra línea problemática
- Prompt de ring al crear citas con hora
- Deliver a cloud por defecto al adjuntar fichero

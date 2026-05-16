# RING.md — alarmas vía Reminders.app desacopladas (SHIPPED v0.35)

Diseño cerrado en sesión de 2026-05-13 con el usuario, implementado el
2026-05-14 (fases B–F). Sustituye al backend `reminders_backend:
"reminders"` dormante de v0.29 (acoplado a `sync_item` → AppleScript
directo) por una arquitectura **declarativa + daemon**.

**Estado**: VIGENTE desde v0.35 (ADR-027). Cambio respecto al diseño
original aquí descrito: el `list` por defecto es `workspace_root.name`
(una lista por workspace, ej. `🚀orbit-ws`, `🌿orbit-ps`) en lugar de
una lista única `Orbit Ring`. Decidido en la sesión de implementación
para alinear con el patrón existente.

---

## Motivación

Las alarmas de calendarios suscritos (`.ics` con `VALARM`) en Calendar.app /
iCloud no son fiables:

- macOS muestra alarmas como banner sin sonido por defecto en calendarios suscritos.
- iOS ignora a menudo las alarmas (depende del toggle "Ignorar alertas" por calendario).
- El refresh es cada 5 min como mínimo → alarmas a < 5 min de "ahora" pueden no dispararse.

Reminders.app sí tiene notificaciones system-level fiables, sincroniza con
iPhone/iPad por iCloud, y despierta el Mac de suspend para alarmas en cola.

## Arquitectura aprobada

```
agenda.md (verdad)
    │
    ▼
orbit  ──escribe──▶  <workspace>/.reminders/ring.json   (ventana 7 días)
                          │
                          │ (launchd WatchPaths dispara el daemon)
                          ▼
                    orbit_ring_daemon.py
                          │
                          ▼
                    Reminders.app — lista "Orbit Ring"
                          │
                          ▼  (iCloud sync gratis)
                    iPhone / iPad
```

Orbit es la **única fuente de verdad** (agenda.md). El fichero `ring.json` es
una proyección declarativa de lo que **debería** estar en Reminders.app. El
daemon reconcilia idempotentemente — crea, actualiza, borra para que
Reminders.app coincida con `ring.json`.

`.ics` con `VALARM` se mantiene como **redundancia** (belt-and-suspenders) por
decisión del usuario: si el daemon falla, la suscripción todavía dispara algo.

## Decisiones tomadas

| Decisión | Valor | Razón |
|---|---|---|
| Qué citas entran al ring | Todas las que tengan `--ring` (task/ms/ev/reminder) | Carril crítico = lo que el usuario marca explícitamente |
| Default `alarm_minutes` | 5m | Igual que el actual; orbit ya pregunta interactivo |
| Ventana temporal | Próximos 7 días (rolling) | Fija el problema del finde: si el viernes regeneras, sat/sun ya están en Reminders aunque no abras orbit |
| Lista en Reminders.app | Única: `Orbit Ring` | Configurable en `orbit.json`; lista única simplifica daemon e iCloud sync |
| Formato del fichero | JSON propio | VTODO no compra nada (Reminders.app no consume `.ics` local); JSON es legible y diff-able |
| Lenguaje del daemon | Python | Consistencia con resto de orbit |
| Backend de escritura | **EventKit vía PyObjC** (no AppleScript) | Misma fiabilidad que Reminders.app (es el framework subyacente), sin timeouts de osascript, sin necesidad de que la app esté abierta, API estructurada |
| Trigger del daemon | launchd `WatchPaths` (short-lived, sin `KeepAlive`) + `StartCalendarInterval` 00:00 | Mac-native, sin proceso persistente, cero polling |
| Conflicto con `.ics` VALARM | Mantener `VALARM` (redundancia) | Si daemon falla, la subscription todavía suena |
| Cancelaciones | Daemon quita el item inmediato (siguiente sweep) | Reminders.app refleja sólo lo activo |
| Federación | Daemon procesa **todos** los workspaces federados en una pasada | Un sólo plist watcheando los paths de los federados |

## Triggers (los 4 elegidos por el usuario)

Todos invocan la misma función `ring_export.refresh(workspace)`:

1. **Shell startup** (en `core/shell.py::startup`)
2. **Commit hook** (post-commit en `orbit commit`, junto al render `.ics` actual)
3. **Cron 00:00** (launchd `StartCalendarInterval`)
4. **Comando explícito** (`orbit ring refresh`)

Idempotencia garantiza que disparar varias veces no causa daño.

## Schema de `ring.json`

Path: `<workspace>/.reminders/ring.json` (gitignored, vive bajo `.reminders/`).

```json
{
  "generated_at": "2026-05-13T08:30:00",
  "window_start": "2026-05-13",
  "window_end":   "2026-05-20",
  "items": [
    {
      "orbit_id":      "a1b2c3d4",
      "project":       "💻orbit",
      "kind":          "reminder",
      "title":         "Llamar al banco",
      "due_iso":       "2026-05-13T11:30:00",
      "alarm_minutes": 5,
      "list":          "Orbit Ring"
    },
    {
      "orbit_id":      "e5f67890",
      "project":       "⚙️igfae",
      "kind":          "task",
      "title":         "Revisar paper",
      "due_iso":       "2026-05-14T16:00:00",
      "alarm_minutes": 15,
      "list":          "Orbit Ring"
    }
  ]
}
```

Notas:

- Items con `--ring` pero **sin hora** se omiten (skip silencioso).
- Recurrentes se **expanden** dentro de la ventana (un item por ocurrencia).
- El `orbit_id` es la identidad estable; el daemon matchea por `[orbit:xxx]`
  en el body del Reminder.

## Implementación real (v0.35, 2026-05-14)

Lo que efectivamente shipping difiere del plan original en estos puntos:

- **Lista por workspace** (no única `Orbit Ring`). Default = `workspace_root.name`. Override vía `orbit.json/ring.list`.
- **Config en `orbit.json`** del workspace, no en un fichero nuevo: `"ring": { "enabled": true, "days": 7, "list": "..." }`. Defaults aplicados con `_load_ring_config()`.
- **Hooks**: el catálogo (`core/hooks_catalog.json`) gana la acción `ring_refresh` añadida al chain `commit_post` y a `shell_start`. El hook compone el behavior; no se tocó `core/shell.py` ni `core/commit.py` directamente.
- **`pyobjc-framework-EventKit`** añadido como dependencia en [DEPENDENCIES.md](DEPENDENCIES.md).
- **launchd plist** con `WatchPaths` por workspace + `StartCalendarInterval` 00:05 (no 00:00 para no chocar con backups y cron jobs comunes).
- **Doctor check**: `views/doctor/doctor.py::_check_ring_health` reporta plist no instalado / TCC denied / ring.json viejo.

## Plan de implementación original — fases B a F (referencia histórica)

### Fase B — Generación de `ring.json` (~2-3h)

| Cambios | Archivos |
|---|---|
| Módulo nuevo `views/ring/export.py` (separado de `views/ring/parse.py`) | nuevo |
| Función `build_ring_payload(workspace_root, days=7)` itera proyectos federados-aware, filtra `--ring`, expande recurrencia 7d, normaliza schema | nuevo |
| CLI: `orbit ring refresh\|status\|install\|uninstall` | `orbit.py` |
| `orbit ring refresh` escribe `<workspace>/.reminders/ring.json` (atómico: write tmp + rename) | nuevo |
| `orbit ring status` muestra paths, count, hash actual, ¿plist cargado? | nuevo |
| Tests: schema, filtro `--ring`, expansión 7d, items sin time, recurrentes | `tests/test_ring_export.py` |

### Fase C — Daemon `orbit_ring_daemon.py` (~3-4h)

Usa **EventKit vía PyObjC** (no AppleScript). EventKit es el framework subyacente
de Reminders.app — saltamos dos capas (`osascript` + el proceso de la app)
hablando directo al store de Reminders. Misma fiabilidad de notificaciones,
misma sincronización iCloud → iPhone, **sin** los problemas crónicos de
AppleScript (timeouts, error -10025, escape de strings, necesidad de
Reminders.app lanzada).

```python
# Esqueleto del path EventKit
from EventKit import EKEventStore, EKReminder, EKAlarm
from Foundation import NSDateComponents, NSCalendar

store = EKEventStore.alloc().init()
store.requestFullAccessToRemindersWithCompletion_(...)  # permiso una vez

reminder = EKReminder.reminderWithEventStore_(store)
reminder.setTitle_(f"[{project}] {kind_emoji} {title}")
reminder.setNotes_(f"[orbit:{orbit_id}]")
reminder.setDueDateComponents_(_components_from_iso(due_iso))
reminder.addAlarm_(EKAlarm.alarmWithRelativeOffset_(-alarm_minutes * 60))
reminder.setCalendar_(_get_or_create_list(store, "Orbit Ring"))
store.saveReminder_commit_error_(reminder, True, None)
```

| Cambios | Archivos |
|---|---|
| Script standalone en raíz del repo | nuevo |
| Dependencia nueva: `pyobjc-framework-EventKit` (registrar en `DEPENDENCIES.md`) | — |
| Procesa **todos** los `ring.json` federados en una pasada | — |
| Crea lista `Orbit Ring` si no existe; upsert por `[orbit:xxx]` en notes; borra orphans **solo dentro de la lista** y **solo si tienen orbit-tag** (nunca toca items manuales del usuario) | — |
| Hash check (`.reminders/last_applied.sha`) para idempotencia → exit rápido si nada cambió | — |
| Logging a `~/.orbit/ring-daemon.log` con rotación naive | — |
| Tests con EventKit mockeado (pyobjc permite mock fácil de `EKEventStore`) | `tests/test_ring_daemon.py` |

### Fase D — Hooks y triggers (~1h)

| Cambios | Archivos |
|---|---|
| Shell startup llama `ring_export.refresh_all_federated()` | `core/shell.py` |
| `orbit commit` post-hook regenera `ring.json` del workspace afectado (junto al render `.ics`) | `orbit.py` o `core/commit.py` |
| Tests de integración: edit cita con `--ring` → `ring.json` contiene el item | `tests/test_ring_integration.py` |

### Fase E — Plist install/uninstall (~1h)

| Cambios | Archivos |
|---|---|
| `orbit ring install` genera `~/Library/LaunchAgents/com.orbit.ring-daemon.plist` | `views/ring/export.py` |
| Plist con `WatchPaths` (uno por federado) + `StartCalendarInterval` 00:00 + `ProgramArguments` (`sys.executable` + script path) | — |
| Ejecuta `launchctl load` y un primer `ring refresh` de bootstrap | — |
| `orbit ring uninstall` hace `launchctl unload` y borra plist | — |
| Doc en `CHULETA.md`, `TUTORIAL.md`, mención en `SETUP.md` | — |

### Fase F — Doctor + observability (~30min)

| Cambios | Archivos |
|---|---|
| `orbit doctor` chequea: plist cargado, último `last_applied` vs ahora, count `ring.json` vs Reminders.app | `views/doctor/doctor.py` |
| `orbit ring status` enriquecido con la misma info | `views/ring/export.py` |

## Estimación

~9-10h totales, repartibles en 2-3 sesiones. Versión sugerida al cerrar: v0.35.0.

## Riesgos / unknowns

- **Permisos de Reminders desde launchd**: EventKit pide acceso "Full Access
  to Reminders" la primera vez que se invoca. Aparecerá un prompt de macOS
  (TCC) — el daemon debe manejar el caso "permiso denegado" sin colapsar.
  Documentar en TUTORIAL.
- **Wake-for-alarms**: depende de `pmset` settings. Si Mac está en clamshell
  sleep profundo, podría no despertar para una alarma de Reminders. Mencionar
  como caveat, no resolverlo en v1.
- **Lista preexistente** llamada `Orbit Ring`: el daemon la adopta y empieza
  a borrar items sin orbit-tag dentro. **Crítico**: nunca borrar items que
  **no tengan** `[orbit:xxx]` en `notes`. Doble-check en código y test
  explícito.

## Conexión con código dormante (v0.29)

El path viejo `sync_item` → Reminders.app (`reminders_backend: "reminders"`
con guard `_agenda_via_calendar()`) queda **definitivamente dormante**. Su
problema era el acoplamiento directo orbit → AppleScript. La nueva
arquitectura es decoupled — orbit sólo escribe `ring.json`, el daemon es
responsabilidad aparte.

Ver [DORMANT.md](DORMANT.md) para revival steps del path antiguo si alguna vez
se decide rescatar (no se prevé).

## Bonus: iCloud sync a iPhone/iPad

Si la lista `Orbit Ring` vive en la cuenta iCloud (no "On My Mac"), los
reminders + alarmas viajan automáticamente al iPhone/iPad. Esto resuelve el
problema crónico de las alarmas `.ics` en iOS **sin esfuerzo extra**. Worth
highlighting en TUTORIAL.md cuando se implemente.

# DORMANT.md

Lista única de código dormante en orbit con las instrucciones exactas para revivirlo. Cada entrada incluye **qué** está apagado, **por qué**, **cómo revivir**, y **tests** que cubren el contrato de reactivación.

Sigue el patrón de [feedback memory: "dormant deprecation"]: cuando se decide retirar una pieza, se desconecta de los flujos activos pero el código se conserva. Borrar solo cuando hay suficiente confianza de que no se necesita (ver fecha-criterio al final de cada entrada).

## Tabla de un vistazo

| Subsystem | Módulo | Estado | Borrar después de |
|-----------|--------|--------|-------------------|
| AppleScript-write a Calendar.app | `core/gsync.py` (push), `core/calsync.py` (audit) | DORMANTE detrás de flag `applescript_writes:false` | 2026-05-27 si no se reactivó en ningún workspace |
| Reminders.app backend para tasks/ms/rem | `core/agenda_cmds._agenda_via_calendar()` y rama legacy en `core/gsync._sync_one_to_reminders` | DORMANTE detrás de flag `reminders_backend:"reminders"` | Cuando borremos gsync (paso anterior) |
| Google Tasks / Google Calendar API | `core/gsync.py:run_gsync` cuerpo legacy | UNREACHABLE (return 0 antes del cuerpo Google API) desde v0.29 | Junto con el resto de `gsync.py` |
| `☁️` marker en agenda.md | parsers en `core/agenda_cmds._parse_*_line` | Reconocido pero nunca escrito desde v0.33 (formatters omiten) | Cuando borremos gsync — el campo `cloud_verified` deja de tener sentido |
| `TestSetCloudVerified` | `tests/test_sync_verify.py` | `@pytest.mark.skip` desde v0.33 | Cuando borremos gsync |

---

## 1. AppleScript-write a Calendar.app (`gsync`, `calsync`)

### Qué está dormante

- `core/gsync.py:sync_item` y sus helpers `_create_calendar_event`, `_update_calendar_event`, `_delete_calendar_event`, `_sync_one_agenda_event`.
- `core/gsync.py:reconcile_gsync_renames`, `check_gsync_drift`, `gsync_background`.
- `core/calsync.py:run_calsync` (auditoría atributo-a-atributo con Calendar.app).
- Comandos CLI `orbit gsync` y `orbit calsync` **eliminados de `_COMMANDS`** desde v0.33 (no aparecen en `orbit help`).

### Por qué

Calendar.app se suscribe a los `.ics` que emite orbit. La subscripción es read-only por construcción → no hay drift posible. El camino AppleScript-write tenía un historial de fragilidad (errores -10025, sync silencioso, drift) que motivó capas sucesivas de parches (☁️ marker, failures journal, calsync). El `.ics` resuelve la clase de bugs entera.

### Cómo revivir

1. **Activar el flag** en `calendar-sync.json` del workspace:
   ```json
   { "applescript_writes": true }
   ```
2. **Restaurar los comandos CLI** en `orbit.py:_COMMANDS`:
   ```python
   "gsync": cmd_gsync, "calsync": cmd_calsync,
   ```
3. **Restaurar argparse entries** para `gsync` y `calsync`. Los parsers están en el git history; commit que los retiró: ver `git log -- orbit.py | head` (post-v0.33).
4. **Restaurar `calendar-sync.json`** con los campos necesarios. Mínimo:
   ```json
   {
     "applescript_writes": true,
     "reminders_backend": "calendar",
     "calendars": { "default": "<nombre-calendario>", ... },
     "agenda_calendar": "<nombre-calendario-agenda>"
   }
   ```
   Los campos se limpiaron en v0.33 con `scripts/cleanup_v033_dormant_state.py` — revertir manualmente.
5. Ejecutar `orbit gsync` para repoblar `.gsync-ids.json` por proyecto.

### Tests del contrato de reactivación

- `tests/test_gsync_agenda.py` — sync_item routing por kind y backend.
- `tests/test_gsync_calendar_app.py` — find/create/update/delete event helpers.
- `tests/test_calsync.py` — auditoría atributo a atributo (la clase `TestRunCalsync` confía en que `conftest.py` patchea el flag a True).
- `tests/test_recurrence_sync.py` — sync inmediato de próxima ocurrencia en `task done`/`drop`.
- `tests/test_sync_verify.py` — verify-after-sync + ☁️ marker. `TestSetCloudVerified` está skipped; quitar el skip al revivir.
- `tests/test_v0230_improvements.py` — reconcile_gsync_renames con prefijo kind::.

### Criterio para borrar

**2026-05-27** (2 semanas desde el corte v0.33 = 2026-05-13). Si en ese momento:
- ningún workspace tiene `applescript_writes:true` en su `calendar-sync.json`
- la suscripción `.ics` ha funcionado sin necesidad de fallback manual

→ proceder a borrar físicamente `core/gsync.py`, `core/calsync.py`, sus tests, las menciones en CLAUDE.md y este apartado de DORMANT.md.

---

## 2. Reminders.app backend para tasks/ms/rem

### Qué está dormante

- Rama `_sync_one_to_reminders` en `core/gsync.py` y todo el camino `core/ring.py` para programar reminders.
- Guard `_agenda_via_calendar()` en `core/agenda_cmds.py`.

### Por qué

v0.29 movió tasks/ms/rem de Reminders.app a Calendar.app (eventos de 0 min con alarma). El backend Reminders.app quedó como fallback durante el periodo de validación. v0.33 retiró ambos a favor de `.ics`. Reminders.app no se usa para nada relacionado con orbit.

### Cómo revivir

Cambiar `"reminders_backend": "reminders"` en `calendar-sync.json`. Requiere que `applescript_writes:true` también esté activo (es una capa por debajo).

### Criterio para borrar

Junto con el paquete anterior (gsync). No tiene sentido tener un fallback de un fallback.

---

## 3. Google Tasks / Google Calendar API

### Qué está dormante

Cuerpo legacy de `core/gsync.py:run_gsync` después del `return 0` que marcaba la transición v0.29. El comentario en el código lo dice literal:
```python
return 0
# ── unreachable: original Google-API body retained below for reference ──
```

### Por qué

Pre-v0.29 orbit subía tasks/ms a Google Tasks vía API. v0.29 lo cambió por AppleScript-write a la app local. El cuerpo legacy se mantuvo "por si acaso". Hoy no se llama desde ningún flujo activo.

Las únicas referencias activas a Google API en orbit están en:
- `core/cartero.py` (captura de Gmail, separado de la sincronización de calendarios)
- `core/calendar_sync.py` (helper `_build_service` usado solo por cartero y por gsync dormante)

### Cómo revivir

No tiene sentido en aislamiento. Si se quisiera, restaurar las llamadas en `run_gsync` antes del `return 0`. Requiere `credentials.json` y `token.json` con scopes de Google Tasks + Calendar API.

### Criterio para borrar

Junto con el resto de gsync.

---

## 4. `☁️` marker en agenda.md

### Qué está dormante

- Parsers (`_parse_task_line`, `_parse_event_line`, `_parse_reminder_line`) reconocen `☁️` y exponen `cloud_verified: bool`.
- Formatters (`_format_task_line`, `_format_event_line`, `_format_reminder_line`) **nunca lo escriben** desde v0.33.
- `set_cloud_verified` en `core/agenda_cmds.py` sigue existiendo pero ya no se llama.

### Por qué

v0.30 introdujo `☁️` como señal visible de "cita verificada en Calendar.app tras AppleScript-write". Sin AppleScript-write, el marker pierde sentido. Strippeado one-shot con `scripts/strip_cloud_marker.py` en ambos workspaces.

### Cómo revivir

Restaurar la línea `if X.get("cloud_verified"): parts.append("☁️")` en cada formatter (`core/agenda_cmds.py`). Hoy reemplazada por un comentario `# ☁️ marker dormant since v0.33`.

### Criterio para borrar

Junto con gsync. El campo `cloud_verified` puede entonces eliminarse del dict del parser.

---

## Cómo registrar nuevas dormancias

Cuando deprecemos algo nuevo:

1. Añadir entrada a la tabla "de un vistazo" arriba.
2. Sección detallada con: qué / por qué / cómo revivir / tests / criterio para borrar.
3. Comentario `# DORMANT since vX.Y` en el código apagado, con puntero a esta entrada de DORMANT.md.
4. Actualizar CLAUDE.md → sección "Estado actual" solo si la dormancia introduce un cambio observable; el log histórico va en CHANGELOG.md (cuando lo separemos).

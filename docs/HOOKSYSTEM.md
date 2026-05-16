# HOOKSYSTEM.md — El hook system de orbit

> Estado: documento vivo. Pasada 1 (inventario) completada 2026-05-14. Pasada 2 (diseño) acordada 2026-05-14. **F1-F7 shipped 2026-05-14.** F5 restantes (`appointment_sync`, `sync_item`, `note_create`) **descartados** (ver §8.6). Migración cerrada.

## 1. ¿Qué es "automagia"?

**Automagia** = cualquier serie de acciones encadenadas que orbit ejecuta *implícitamente* en respuesta a un evento (commit, startup, edit, render, cambio de día, done de cita recurrente…) sin que el usuario las invoque por nombre.

No es mala per se — buena parte de la utilidad de orbit viene de que `orbit commit` haga "lo que tiene que hacer" sin que el usuario lo enumere. Es **peligrosa** cuando:

- Falla silenciosamente y el síntoma aparece lejos de la causa (ver ☁️ marker, `.gsync-failures.json` — observabilidad añadida *después* de pagar el coste).
- Acopla operaciones que conceptualmente no deberían ir juntas (¿qué *significa* exactamente `commit`?).
- No se puede desactivar puntualmente sin parchear código.
- Crece sin presupuesto: cada feature añade su pequeña magia barata; en agregado el startup tarda y nadie recuerda el conjunto.
- Permite bucles entre hooks (ver bug v0.29.8: `reconcile_gsync_renames` revertía la migración de v0.29.6 en cada commit).

## 2. Nombre formal del patrón

Lo que orbit hace es una combinación de tres patrones de la literatura:

1. **Event-Condition-Action (ECA) rules** — patrón de bases de datos activas (HiPAC, Starburst, ~1990): `ON event IF condition DO action`. Es el núcleo del modelo orbit: trigger → chain.
2. **Aspect-Oriented Programming (AOP) advice** — "before/after de un join point ejecuta este advice". Encaja exactamente con la noción de **pre-actions / post-actions** alrededor de un comando explícito (`commit`).
3. **Workflow orchestration / lifecycle hooks** — Airflow, Prefect, npm lifecycle scripts, Rails callbacks, Maven phases, git hooks, pre-commit. Chains nombradas e invocables con actions encapsuladas.

Industrialmente esto se llama **hook-based architecture** (informal, lo usan git, npm, webpack, pytest, pre-commit) o **lifecycle hooks** (Rails, React, Vue). La construcción formal más cercana es **ECA rules + named pipelines**.

Para orbit lo llamaremos **hook system** (formal) o **automagia** (idiomático). El meta-código de orbit es:

```
trigger → chain (named) → [pre_actions] → [core_action?] → [post_actions]
```

## 3. Vocabulario orbit

| Término | Definición |
|---------|------------|
| **Action** | Unidad atómica, nombrada, encapsulada, idempotente. Ej: `doctor_check`, `gsync_reconcile_renames`, `render_changed`, `ics_emit_workspace`, `advance_overdue_recurring`, `ring_schedule_today`. Debe poder invocarse suelta. |
| **Chain** | Secuencia ordenada de actions, con nombre propio y *invocable como comando*. Ej: `commit = [doctor_check, git_save, render_changed, ics_emit, cloudsync_push]`. |
| **Trigger** | Evento que dispara una chain. Tres tipos: **explicit** (usuario tecleó el comando), **reactive** (cambio de estado: `after_edit`, `after_done_recurring`), **temporal** (paso del tiempo: `startup`, `day_changed`, `every_hour`). |
| **Binding** | `trigger → chain`. Tabla declarativa que sustituye al hardcoding actual. Ej: `startup → shell_start`, `commit_done → post_commit`. |
| **Pre-action** | Action que corre *antes* del core action. Suele validar o preparar. |
| **Core action** | La acción que el usuario *pidió*. En triggers explicit es el verbo del comando. En triggers reactive/temporal no hay core action — la chain entera es secundaria. |
| **Post-action** | Action que corre *después* del core action. Suele propagar/sincronizar/limpiar. |

## 4. Propiedades obligatorias de toda action

1. **Idempotente** — correr dos veces = correr una.
2. **Independiente** — invocable suelta (test, debug, retry).
3. **Visible** — imprime una línea cuando corre: `→ render_changed: 12 files, 0.3s`. Excepción: no-ops triviales.
4. **No bloquea la chain** salvo que se marque `critical: true`. Una action no-crítica que falla loguea y continúa.
5. **Devuelve resultado estructurado** `{ok, msg, data, duration_ms}` → al journal.
6. **Declara su trigger en el output** cuando es no-explícito: `[trigger=startup] doctor_check:`. El usuario *siempre* sabe qué disparó qué.

## 5. Controles de desactivación (tres niveles)

| Nivel | Cómo | Ejemplo |
|-------|------|---------|
| 1. Desactivar binding | Config `orbit.json`: `"bindings": {"startup": null}` | "No quiero que startup dispare nada" |
| 2. Saltar action en chain | Flag CLI: `orbit commit --no-render --no-sync` | "Solo commitear esta vez" |
| 3. Kill switch global de action | Config: `"actions": {"render_changed": "off"}` | "Nunca renderices, dispare quien dispare" |

Más: `--dry-run` en cualquier chain enumera lo que correría sin ejecutar.

## 6. Distinción pre / post

Esta distinción no es solo estética — el usuario las cancela distinto:

- **Pre** = "antes de lo que pedí". Validación, preparación, dependencias. Cancelar pre suele decir *"sé lo que hago, no me valides"*. Ej: `--no-doctor` antes de commit.
- **Post** = "después de lo que pedí". Propagación, sincronización, side effects. Cancelar post suele decir *"hazlo pero no propagues todavía"*. Ej: `--no-cloudsync` después de commit.

Una action que falla en **pre crítico** debe abortar la chain (la condición de entrada no se cumple). Una action que falla en **post** no debe bloquear el commit ya hecho — solo loguear y dejar trail.

---

# Inventario actual (mayo 2026, v0.34.0)

> Estado tomado del código en `~/orbit` el 2026-05-14. Cuando el código cambie, actualizar esta sección.

## 6.1. Trigger: `orbit commit` (explicit)

**Chain implícita: `commit`** — entrada `core/commit.py:272` (`run_commit`)

### Pre-actions

| # | Action | File:Line | Crítica | Desactivable | Notas |
|---|--------|-----------|---------|--------------|-------|
| 1 | `git_stage_tracked` | `core/commit.py:272-274` | no | no | Stage de cambios en tracked files |
| 2 | `prompt_untracked` | `core/commit.py:276-277` | no | interactivo | Detecta untracked y pregunta add/ignore |
| 3 | `cloud_imgs_process` | `core/commit.py:287-293` | no | no | Try/except silencioso. Re-stagea logbook si hay cambios |
| 4 | `cronograma_log_completed` | `core/commit.py:297-303` | no | no | Try/except silencioso |
| 5 | **`tracked_files_refresh`** | `core/commit.py:308-334` | **sí** | no | v0.34.0. **Aborta commit si dest_tampered o conflicts**. Llama `core/tracked.py:269` |
| 6 | `doctor_check_all_projects` | `core/commit.py:339` | no | interactivo `[s/N]` | Pre-check, pregunta si continuar |
| 7 | `gsync_reconcile_renames` | `core/commit.py:~360` | no | `applescript_writes: false` (default) → DORMANT | Patch loop bug v0.29.8 resuelto via `_canonical_storage_key` |
| 8 | `gsync_check_drift` | `core/commit.py:~370` | no | DORMANT | Warns post-sync deltas |

### Core action

| # | Action | File:Line | Notas |
|---|--------|-----------|-------|
| 9 | `git_commit` | `core/commit.py:419` | `git commit -m <message>` |

### Post-actions

| # | Action | File:Line | Crítica | Desactivable | Notas |
|---|--------|-----------|---------|--------------|-------|
| 10 | `cloudsync_push_background` | `core/commit.py:422-424` → `core/cloudsync.py:117` | no | no | `subprocess.Popen` detached. Verificar si invoca render dentro |

**Problemas conocidos:**
- (3), (4) tienen `try/except` que tragan errores sin reportar.
- (7), (8) están dormantes pero siguen siendo invocadas — overhead inútil en cada commit.
- (5) aborta antes que (6), así que el usuario ve error de tracked antes que avisos de doctor.
- ¿(10) llama a render internamente? Verificar en `cloudsync.py:117`.

---

## 6.2. Trigger: `orbit render` (explicit) + post-commit implícito (vía cloudsync)

**Chain: `render`** — entrada `views/render/render.py` (`render_changed`)

### Core action

| # | Action | File:Line | Notas |
|---|--------|-----------|-------|
| 1 | `render_changed_html` | `views/render/render.py` | Renderiza .md cambiados a HTML en cloud |

### Post-actions

| # | Action | File:Line | Crítica | Desactivable | Notas |
|---|--------|-----------|---------|--------------|-------|
| 2 | `ics_emit_workspace` | `views/render/render.py` → `views/cal/ics.py` | no | no | Llamado en CADA render, no condicional |
| 3 | `calendar_app_reload` | `views/cal/ics.py` → `_trigger_calendar_reload` | no | si Calendar.app cerrado | AppleScript best-effort, fail silencioso |

**Problemas conocidos:**
- (2) corre incondicionalmente aunque no haya cambios reales en `.ics` — el dedup vive *dentro* de `write_workspace`.
- (3) silencioso si falla; no hay journal.

---

## 6.3. Trigger: `shell_startup` (temporal)

**Chain: `shell_start`** — entrada `core/shell.py:50` (`_run_startup`)

Esta es la chain con **más actions** del sistema. Solo es trigger temporal: ninguna action es "core" — todas son colaterales.

| # | Action | File:Line | Crítica | Desactivable | Notas |
|---|--------|-----------|---------|--------------|-------|
| 1 | `doctor_check_background` | `views/doctor/doctor.py` | no | no | Thread daemon, 5s timeout. Muestra fixable/unfixable |
| 1b | `doctor_interactive_fix` | `views/doctor/doctor.py` | no | tty-only | Si hay fixables y tty, ofrece fix |
| 2 | `advance_overdue_recurring` | `core/agenda_cmds.py:2126` | no | no | Modifica `agenda.md` en disco sin pedir confirmación |
| 3 | `cloud_sync_status_check` | `core/cloudsync.py:159` | no | no | Lee `.cloud-sync.json`, avisa si último sync falló |
| 4 | `untracked_check` | `core/commit.py:626-633` | no | tty-only | Pregunta add/ignore |
| 5 | `commit_offer` | `core/commit.py:636-687` | no | tty-only | Ofrece commit + push si hay cambios |
| 6 | `code_update_check` | `core/commit.py:499-622` | no | tty-only | Checkea si orbit repo tiene nuevos commits, ofrece pull |
| 7 | `gsync_background` | `core/gsync.py:2829` | no | `applescript_writes: false` → DORMANT | Thread daemon |
| 8 | `schedule_reminders` | `core/ring.py:442` | no | NO-OP | **Dead code**. Cuerpo unreachable (`return []` en línea 453). Llamada vestigial |
| 9 | `cartero_startup` | `core/cartero_invoke.py` → `satellites/cartero/daemon.py --startup` | no | falta `cartero.json` | Daemon de mail/Slack si está configurado |
| 10 | `dash_render` | `core/shell.py:126-131` → `run_dash(silent=False)` | no | no | Updatea `panel.md`, `agenda.md`, `calendar.md` |
| 11 | `dash_background_loop_start` | `core/shell.py:134-136` | no | no | Thread daemon: refresh dash cada 1h |

**Problemas conocidos:**
- (1) puede seguir corriendo cuando startup termina ("Doctor aún revisando…").
- (2) modifica `agenda.md` **sin pedir confirmación** — si la recur está rota podría perder ocurrencias.
- (7) sigue lanzándose aunque sea dormante (overhead inútil).
- (8) es código muerto desde v0.29; debería borrarse o documentarse.
- (11) no tiene shutdown limpio — `_dash_stop.set()` solo se chequea en el límite del intervalo de 1h. En shell exit el thread sigue vivo hasta el siguiente tick.

---

## 6.4. Trigger: `day_changed` (temporal, en REPL loop)

**Chain: `day_open`** — entrada `core/shell.py:199-218`

| # | Action | File:Line | Crítica | Desactivable | Notas |
|---|--------|-----------|---------|--------------|-------|
| 1 | `advance_overdue_recurring` | `core/shell.py:206` | no | no | Re-dispara el de startup |
| 2 | `print_advanced_items` | `core/shell.py:207-211` | no | no | UI |
| 3 | `gsync_background` | `core/shell.py:213` | no | DORMANT | Redundante si ya corrió en startup |
| 4 | `schedule_reminders` | `core/shell.py:214` | no | NO-OP | Mismo dead code que (8) en startup |

**Problemas conocidos:**
- No hace commit ni render — los cambios de `advance_overdue_recurring` quedan en `agenda.md` hasta próximo commit (incoherencia con `.ics` y HTML cloud).
- (3), (4) inútiles por defecto.

---

## 6.5. Trigger: `after_appointment_mutation` (reactive)

**Sub-trigger por verbo**: `after_task_add`, `after_task_edit`, `after_task_done`, `after_task_drop` (y equivalentes para `ms`, `ev`, `reminder`).

**Chain: `appointment_sync`** — distribuida en `core/agenda_cmds.py`

| # | Action | File:Line | Crítica | Desactivable | Notas |
|---|--------|-----------|---------|--------------|-------|
| 1 | `apply_edits` | `core/agenda_cmds.py:1451` | sí | no | Modifica item, pone `cloud_verified=False` |
| 2 | `advance_recurrence` | `core/agenda_cmds.py:1310, 1330` | no | no | Si `done` recurrente, crea nueva ocurrencia |
| 3 | `sync_item_old` | `agenda_cmds.py:921-922, 1589-1592, 1742-1745, 1983-1984` | no | DORMANT | Empuja a Calendar/Reminders. Thread daemon con timeout 2s |
| 4 | `sync_item_new` | Mismas líneas (post-advance) | no | DORMANT | Empuja la nueva ocurrencia tras (2) |
| 5 | `agenda_write` | implícito en callers | sí | no | Persiste cambios a `agenda.md` |

**Problemas conocidos:**
- Sub-chain `sync_item` (sección 6.6) corre dentro de cada llamada — anidación profunda no visible al usuario.
- Múltiples `sync_item` secuenciales no se baten — cada uno con su propio timeout.

---

## 6.6. Sub-chain: `sync_item` (reactive, llamada desde 6.5)

**Entrada: `core/gsync.py:2499`** — DORMANT por defecto (`applescript_writes: false`).

| # | Action | File:Line | Notas |
|---|--------|-----------|-------|
| 1 | `load_config_ids` | `gsync.py:2518-2521` | Lee `.gsync-ids.json` |
| 2 | `applescript_write_calendar_or_reminder` | `gsync.py:2544-2742` | El push real |
| 3 | `verify_post_sync` | `gsync.py:2645-2675` | Read-back. Pone `cloud_verified` (☁️) o journalea fallo |
| 4 | `save_ids` | `gsync.py:2631, 2696, 2733` | Update `.gsync-ids.json` + persiste orbit-id en `agenda.md` |
| 5 | `migrate_pre_v0_29_entries` | `gsync.py:2619-2626` | Limpieza de copias antiguas |

**Problemas conocidos:**
- (3) no falla la chain ante mismatch — solo journalea. Diseño deliberado (ver `feedback_dormant_deprecation`).
- (4) muta `agenda.md` con orbit-id si es la primera sync — interfiere con `tracked_files_refresh` si la agenda es tracked.

---

## 6.7. Trigger: `after_note_create` (reactive)

**Chain: `note_create`** — entrada `core/notes.py:131` (`run_note_create`)

| # | Action | File:Line | Crítica | Desactivable | Notas |
|---|--------|-----------|---------|--------------|-------|
| 1 | `create_or_import_file` | `notes.py:~150` | sí | no | El verbo del comando |
| 2 | `register_tracked` (opt) | `notes.py:186-191` | no | sin `--track` | v0.34.0 |
| 3 | `log_to_logbook_or_highlights` | `notes.py:219-226` | no | flags `--hl-type` | |
| 4 | `open_in_editor` (opt) | `notes.py:228-229` | no | `--no-open` | |
| 5 | `git_track_prompt` | `notes.py:204-214` | no | no-tty | Pregunta `git add` |

**Problemas conocidos:**
- Sin auto-commit ni auto-render — el note no aparece en cloud hasta `orbit commit`.

---

## 6.8. Background daemons / procesos detached

Estos no son "chains" en sentido estricto pero son automagia: corren sin que el usuario lo pida y sin output a menos que algo vaya mal.

| Daemon | File:Line | Trigger | Lifetime | Shutdown limpio |
|--------|-----------|---------|----------|-----------------|
| Doctor thread | `views/doctor/doctor.py` | startup | hasta join (5s) o end-of-startup | sí (join) |
| gsync thread | `core/gsync.py:2878` | startup + day-change | daemon, muere con shell | no (daemon=True) |
| Dash refresh loop | `core/shell.py:135` | startup | hasta `_dash_stop.set()` o shell exit | parcial (se chequea solo al límite del intervalo de 1h) |
| Cartero daemon | `satellites/cartero/daemon.py::startup_cartero` (vía `core/cartero_invoke.py` por subprocess) | startup si configurado | double-fork → independiente del shell | sí (`_stop_background()`) |
| Cloudsync subprocess | `core/cloudsync.py:132` | post-commit | detached (start_new_session=True) | no (fire & forget) |

**Problemas conocidos:**
- Solo Cartero tiene shutdown limpio.
- Cloudsync detached → no se puede saber si tuvo éxito sin leer `.cloud-sync.json` en el próximo startup.

---

# 7. Resumen del estado actual

## 7.1. Métricas

- **Triggers identificados**: 7 (commit, render, startup, day_changed, after_appointment_mutation, after_note_create, post_commit).
- **Chains implícitas**: ~9 (incluyendo sub-chains como `sync_item`).
- **Actions totales**: ~50.
- **Actions dormantes**: ~10 (todas las de AppleScript-write desde v0.33).
- **Actions con kill switch real**: 1 (`applescript_writes`).
- **Actions con flag CLI per-action**: 0.
- **Actions con output visible**: ~10 de 50.
- **Actions con resultado estructurado / journaleadas**: 1 (`sync_item` vía `.gsync-failures.json`).

## 7.2. Síntomas principales

1. **Hardcoding masivo**: los hooks viven inline en `run_commit`, `_run_startup`, `_apply_edits`, etc. No hay tabla declarativa.
2. **Granularidad de control desigual**: `applescript_writes` apaga 10 actions a la vez; no hay forma de apagar solo `gsync_reconcile_renames`.
3. **Output pobre**: la mayoría de actions no imprimen nada salvo error. El usuario no sabe qué ocurrió en su commit.
4. **Código muerto invocado**: `schedule_new_format_reminders` (no-op) se llama en startup y day-change.
5. **Daemons sin shutdown**: dash refresh y cloudsync subprocess no se cierran limpiamente.
6. **Side effects no documentados**: `advance_overdue_recurring` modifica `agenda.md` silenciosamente.
7. **Inconsistencia temporal**: `day_changed` avanza recurrentes pero no renderiza ni commitea → `.ics` y HTML quedan desfasados hasta próximo commit.

## 7.3. Riesgos confirmados (no hipotéticos)

- Bug v0.29.8: doble hook acoplado a commit (sync_item + reconcile_gsync_renames) creó loop de migración / reversión. Resuelto con `_canonical_storage_key` pero el patrón puede repetirse.
- Bug v0.29.7: lookup por orbit-id en eventos recurrentes fallaba → duplicados en Calendar. Síntoma típico de magia sin verificación.
- Bug v0.29.6: entries legacy en `.gsync-ids.json` no se reconocían → `sync_item` creaba duplicados. Fallback añadido a posteriori.

Patrón común: **una action no idempotente, con observabilidad pobre, acoplada a un trigger frecuente**.

---

# 8. Pasada 2 — diseño (acordado 2026-05-14)

## 8.1. Decisiones clave (locked-in)

1. **Materializar el modelo en código.** Módulo nuevo `core/hooks.py` con registry, `fire()`, `HookResult`. No basta con disciplina — el hardcoding es la raíz de los bugs v0.29.6/7/8.
2. **Las chains son datos; las actions son código.** Composición declarativa, ejecución imperativa.
3. **Catálogo en Python primero, JSON después.** Empezar con dataclasses cuyo shape sea JSON-compatible (`asdict()` + `json.dump` = migración). Mover a `hooks_catalog.json` en fase F6, cuando el shape esté probado.
4. **Journal opt-out.** Siempre on, ignorable. Bajo coste, alto valor de debug.
5. **`day_changed` cierra la inconsistencia temporal.** Tras `advance_overdue_recurring` se dispara render + commit (no solo render local). Añade I/O pero elimina el desfase entre `agenda.md`, `.ics` y HTML cloud.
6. **Migración con coexistencia.** Chain a chain. La función antigua queda como wrapper que llama `fire()`. Cero riesgo de regresión, rollback trivial por chain.

## 8.2. Arquitectura

**Módulo nuevo: `core/hooks.py`** (~200 líneas).

```python
TriggerType = Literal["explicit", "reactive", "temporal"]

@dataclass
class HookResult:
    action: str
    ok: bool
    msg: str = ""
    data: Any = None
    duration_ms: int = 0
    skipped: bool = False
    skip_reason: str = ""

@dataclass
class Action:
    name: str                    # "doctor_check_all_projects"
    fn: Callable                 # función real
    critical: bool = False       # si true, falla aborta chain
    cli_flag: str = ""           # autogenerado: --no-doctor-check
    disable_config_key: str = "" # e.g. "actions.doctor_check.off"

@dataclass
class Chain:
    name: str                    # "commit"
    trigger_type: TriggerType
    pre: list[str] = field(default_factory=list)    # action names
    core: str | None = None                          # action name (solo explicit)
    post: list[str] = field(default_factory=list)
    cli_verb: str = ""           # "commit" / "render" / "" si no es user-callable

# Registries
ACTIONS: dict[str, Action] = {}
CHAINS: dict[str, Chain] = {}
BINDINGS: dict[str, str] = {}   # trigger_name → chain_name

def register_action(name, fn, *, critical=False, cli_flag="", disable_config_key=""): ...
def register_chain(name, *, trigger_type, pre=None, core=None, post=None, cli_verb=""): ...
def bind(trigger, chain_name): ...
def fire(trigger, ctx=None, *, dry_run=False, skip_actions=None) -> list[HookResult]: ...
```

`fire()` se encarga de: cargar config de kill switches → recorrer pre/core/post en orden → respetar `skip_actions` (de flags CLI) → cronometrar → imprimir línea por action → journalear → abortar si action crítica falla.

## 8.3. Output unificado

```
→ doctor_check: ok (340ms)
→ tracked_files_refresh: ok, 3 refreshed (12ms)
⚠ gsync_reconcile_renames: skipped (applescript_writes=off)
→ git_commit: ok (89ms)
→ cloudsync_push_background: launched (5ms)
```

Modos: `--quiet` (solo críticos), default (una línea por action), `--verbose` (también `data`).

## 8.4. Controles de desactivación

```jsonc
// orbit.json (workspace)
{
  "hooks": {
    "bindings": {
      "shell_startup": "shell_start",
      "day_changed": null            // nivel 1: desactivar binding
    },
    "actions": {
      "gsync_background": "off",     // nivel 3: kill switch global
      "advance_overdue_recurring": { "verbose": true }
    }
  }
}
```

CLI per-action (nivel 2): `orbit commit --no-render --no-cloudsync` → argparse generado del catálogo del chain.

## 8.5. Journal

`<workspace>/.journal.jsonl` (gitignored). Una línea por chain ejecutado:

```json
{"when": "2026-05-14T10:23:11", "trigger": "explicit", "chain": "commit",
 "results": [{"action": "doctor_check", "ok": true, "ms": 340}, ...]}
```

Rotación: cuando >10MB, mover a `.journal.1.jsonl`. `orbit doctor --hooks` lee los últimos N y muestra fallos recientes.

## 8.6. Plan de migración (fases)

| Fase | Alcance | Riesgo | Estado |
|------|---------|--------|--------|
| **F1** | `core/hooks.py` con registry + `HookResult` + `fire()` + journal. Tests del registry. No migra nada. | bajo | **✓ shipped 2026-05-14** (34 tests) |
| **F2** | Migrar chain `commit`. Pre/post de inline a `register_action()` + catálogo. `run_commit` ahora llama `fire("commit_pre")` antes del flujo interactivo y `fire("commit_post")` después. Doctor check se queda inline (interactivo). Dos chains (`commit_pre`, `commit_post`) por la interacción entre medias. | medio | **✓ shipped 2026-05-14** (32 tests) |
| **F3** | Quick wins (sección 8.7). | bajo | **✓ shipped 2026-05-14** |
| **F4** | Migrar `shell_start` (la más larga, 10 actions tras F3). | medio | **✓ shipped 2026-05-14** (19 tests) |
| **F5** | `render` + `day_open` (con render añadido). `appointment_sync` / `sync_item` / `note_create` descartados (justificación abajo). | medio | **✓ shipped 2026-05-14** (parcial — 16 tests) |
| **F6** | Catálogo declarativo en `core/hooks_catalog.json`. Inline `register_*` removidas de los módulos. `hooks.bootstrap()` lo carga en orbit.py import y tests/conftest.py session fixture. | bajo | **✓ shipped 2026-05-14** (6 tests) |
| **F7** | `--no-X` flags al CLI generados del catálogo. Helpers en `core/hooks.py`: `actions_in_chain`, `add_chain_flags`, `collected_skip_actions`. `orbit commit` y `orbit render` exponen los flags. | bajo | **✓ shipped 2026-05-14** (7 tests) |

Cada fase se commitea aparte y puede revertirse aislada. Tests específicos por fase.

**Nota F2**: se usó `verbosity="quiet"` en los `fire()` para no duplicar output — las actions wrappers conservan los prints ricos originales (e.g. `↻ [proj] file ← source`), y el registry solo imprime fallos. El journal sigue capturando todo.

**Nota F5 — `appointment_sync` / `sync_item` / `note_create` descartados.** Tras releer el código:

- **`appointment_sync`** y **`sync_item`** son *verbs*, no chains. El "ciclo" `apply_edits → advance_recurrence → sync_item → agenda_write` está entrelazado con la lógica de cada verb (task add/edit/done/drop × 4 tipos = ~14 funciones), no es una capa de hooks alrededor de un verb. Migrarlos tocaría 14 call sites para mover solo `sync_item` a chain, y `sync_item` está **dormant por defecto** (`applescript_writes: false`) — el usuario no notaría diferencia. Sin valor.
- **`note_create`** es un solo verb. Sus 5 "pasos" (crear fichero, log o highlight, git_add prompt, abrir editor, register tracked) están atados a parámetros del comando (`title`, `file_str`, `hl_type`, `track`, `open_after`); refactorizar para que los pasos sean actions independientes con ctx threading sería un refactor mayor sin valor añadido — el usuario ya tiene control mediante flags CLI.

El meta-modelo `trigger → chain → actions` aplica cuando *hay* automatización alrededor del verb. Cuando los pasos *son* el verb, no hay chain que migrar.

## 8.7. Quick wins (F3 — independientes del registry)

| # | Acción | Estado |
|---|--------|--------|
| 1 | Borrar `schedule_new_format_reminders` de startup + day_changed (dead code). Función en `core/ring.py` queda como no-op (tests la cubren). | ✓ done |
| 2 | Move-up `applescript_writes` check en `gsync_background`. | descartado — el check ya estaba en `gsync.py:2836`, nada que mover |
| 3 | `_dash_stop` poll cada 5s en vez de cada 1h. Shutdown latency ≤5s. | ✓ done |
| 4 | Print en `advance_overdue_recurring`. | descartado — el print ya existe en el caller (`shell.py:88-94`) |
| 5 | Documentar en docstring que `advance_overdue_recurring` muta disco. | ✓ done |
| **bonus** | **Decisión 2 del diseño**: `day_changed` ahora invoca `run_dash(silent=True)` tras avanzar recurrentes → regenera dash + `.ics`. Cierra la inconsistencia temporal (render). Commit auto pendiente para F5 (riesgo de prompt interactivo). | ✓ done |

## 8.8. Lo que NO se hace

- No abstraer actions detrás de interfaces / clases / herencia. Funciones planas + dataclass del registry.
- No plugin system. Las actions las registra orbit, no terceros.
- No async/await. Threads existentes siguen siendo threads; el registry no fuerza modelo de ejecución.
- No tocar el binding-design del ring system (RING.md, pendiente) hasta tener F1–F2 estables.

## 8.9. Cierre

ADR en `DECISIONS.md` se escribirá cuando F2 se haya validado en producción durante ≥1 semana. Hasta entonces este doc es la spec.

Referencias relacionadas:
- `DECISIONS.md` — ADRs.
- `DORMANT.md` — código dormante (varios hooks viven allí).
- `ROADMAP.md` — esta revisión está listada como pendiente.
- `RING.md` — el sistema de ring (futuro) introduce *más* hooks; F1–F2 estables antes.

---

*Pasada 1 (inventario) cerrada 2026-05-14.*
*Pasada 2 (diseño) acordada 2026-05-14.*

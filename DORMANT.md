# DORMANT.md

Lista única de código dormante en orbit con las instrucciones exactas para revivirlo. Cada entrada incluye **qué** está apagado, **por qué**, **cómo revivir**, y **tests** que cubren el contrato de reactivación.

Sigue el patrón de [feedback memory: "dormant deprecation"]: cuando se decide retirar una pieza, se desconecta de los flujos activos pero el código se conserva. Borrar solo cuando hay suficiente confianza de que no se necesita (ver fecha-criterio al final de cada entrada).

## Tabla de un vistazo

| Subsystem | Módulo | Estado | Borrar después de |
|-----------|--------|--------|-------------------|
| Tracked v0.34 (copia + 4-scenario refresh) | `core/tracked.py` reescrito en v0.36 | RETIRADO completamente desde v0.36 (no dormante: borrado del repo). El código vive en git history, ver `git show v0.34.0:core/tracked.py` | n/a (history-only) |

(No quedan dormancias activas tras Fase 2 sub-paso 2.)

## Borrados ejecutados

Para auditoría histórica. Si necesitas cualquiera de estos paths, recupéralos de `git log`.

- **2026-05-15 (Fase 2)** — `core/calendar_sync.py` (247 ℓ) + 3 clases de test (`TestEventInAgenda`, `TestSyncNewFormat`, `TestSyncEventsToLogbooks` ≈ 165 ℓ, 14 tests). Salvage: los OAuth helpers (`CREDENTIALS_PATH`, `TOKEN_PATH`, `SCOPES`, `_get_credentials`, `_build_service`) extraídos a `core/google_oauth.py` (cartero los importa desde ahí). El pull Google→orbit estaba sin CLI desde v0.33 (commit `c952889`, 2026-05-12); la precondición original de 3 meses se acortó porque no había callers ni ruta posible de reactivación accidental.
- **2026-05-15 (v0.38)** — `core/gsync.py` (2880 ℓ) + `core/calsync.py` (793 ℓ) + 8 tests (≈3950 ℓ). Cumplido el criterio "ningún workspace tiene `applescript_writes:true`". Junto con ello murieron: AppleScript-write a Calendar.app, backend Reminders.app vía `_sync_one_to_reminders`, cuerpo legacy Google Tasks/Calendar API en `run_gsync`, marker `☁️` en agenda.md, `TestSetCloudVerified`. La rama `_agenda_via_calendar()` en `agenda_cmds.py` queda stub a `True`; las antiguas ramas legacy gateadas por `not _agenda_via_calendar()` son código muerto pendiente de podar (Fase 3 del plan en `MODULES.md`). Commit: ver `git log --grep="drop gsync"`.
- **2026-05-15 (v0.38)** — `core/migrate.py` + `core/tracked_migrate.py` + `core/importer.py` + CLI wiring + 4 tests (~1325 ℓ). Migraciones one-shot completadas en todos los workspaces; importador Evernote sin uso.
- **2026-05-15 (v0.38)** — `core/reminders.py` + sus tests (508 ℓ). Superseded por `ring_export` + `satellites/ring-daemon/daemon.py` (v0.37; daemon movido a `satellites/` en F1 satellites refactor 2026-05-15).
- **2026-05-15 (v0.38)** — `schedule_new_format_reminders` (no-op) + 2 helpers huérfanos en `ring.py` (~250 ℓ).

---

## 1. Tracked v0.34 — copia versionada + refresh con 4-scenario

### Qué se retiró

- `core/tracked.py` v0.34: ~250 líneas con `register`, `unregister`, `retrack`, `check_entry` (4-scenario), `apply_refresh`, `refresh_all`, `_inject_tracked_frontmatter`.
- `core/commit.py:_action_tracked_files_refresh` (acción pre-commit critical=True).
- `core/hooks_catalog.json`: la entrada `tracked_files_refresh` en `actions` y en `commit_pre`.
- Frontmatter `orbit_tracked_from: <path>` inyectado en cada copia.
- CLI: `orbit tracked refresh|remove|retrack` y `orbit track <proj> <title> --file <path>` (la variante con title).

### Por qué

Ver ADR-026 en DECISIONS.md. Resumen: dos puntos de fricción reales (cross-links a no-tracked rotos, abort en commit al editar el mirror desde Obsidian) y un coste alto (~250 LOC, 4 escenarios, frontmatter) para una característica usada con 3-4 ficheros típicos. v0.36 baja el coste a un symlink relativo.

### Cómo revivir (poco probable)

No es un dormant "detrás de flag" — el código fue **eliminado** del repo. Si alguna vez quieres volver al modelo de copia versionada:

1. `git show v0.34.0:core/tracked.py > core/tracked.py` (restaurar fichero).
2. `git show v0.34.0:core/commit.py` — recuperar `_action_tracked_files_refresh` y reinstalarla.
3. `git show v0.34.0:core/hooks_catalog.json` — restaurar la entrada `tracked_files_refresh` (critical=True) en `actions` y en `commit_pre.pre`.
4. Restaurar `views/doctor/doctor.py:check_tracked` (versión con `iter_tracked` + `check_entry`).
5. Restaurar `tests/test_tracked.py` con los 16 tests de v0.34.
6. Adaptar `core/notes.py:run_note_create` y `core/highlights.py:run_hl_add` para llamar al viejo `register` en vez del nuevo `track`.

### Migración v0.36 → v0.34 (inversa)

Si has migrado y quieres volver:

1. En cada workspace con externas (v0.36 symlinks), por cada entry del registry `{name: source_path}`:
   - Borra el symlink en `notes/<name>`.
   - Copia el contenido del fuente a `notes/<name>` con frontmatter `orbit_tracked_from: <source_path>`.
   - Reescribe el registry al schema v0.34: `{f"notes/{name}": {"source": src, "sha256": <sha>, "added": <date>}}`.
2. Comitea — el viejo refresh pre-commit asumirá control desde el siguiente commit.

### Criterio para borrar esta sección

Nunca (es history-only). Se mantiene para que si alguien lee DECISIONS.md ADR-024 + ADR-026 pueda reconstruir el camino completo.

---

## Cómo registrar nuevas dormancias

Cuando deprecemos algo nuevo:

1. Añadir entrada a la tabla "de un vistazo" arriba.
2. Sección detallada con: qué / por qué / cómo revivir / tests / criterio para borrar.
3. Comentario `# DORMANT since vX.Y` en el código apagado, con puntero a esta entrada de DORMANT.md.
4. Actualizar CLAUDE.md → sección "Estado actual" solo si la dormancia introduce un cambio observable; el log histórico va en CHANGELOG.md (cuando lo separemos).

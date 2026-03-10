# Valoración v0.6.1 — Recomendaciones

Estado: 9,500+ líneas, 15 subcomandos, 595 tests, deps mínimas (stdlib + Google API opcional).

---

## Funcionalidad para el usuario

### Prioridad alta

- **Undo / deshacer** — `task done` o `drop` son irreversibles. Un `orbit undo` o `--undo` en el último comando daría tranquilidad.
- **Recurrencia visible en agenda** — Las tareas recurrentes (`--recur weekly`) no muestran sus próximas ocurrencias en `agenda --calendar` ni en rangos.

### Prioridad media

- **Filtros combinados en search** — `--entry` y `--project` funcionan, pero no hay `--type` (refs/results en highlights), ni combinación `--from + --entry`.
- **Agenda semanal/mensual en report** — `report` lista actividad pasada; una sección "próxima semana" ayudaría a planificar.
- **Templates editables** — Los templates en `📐templates/` existen pero no se documentan como personalizables; un `orbit template edit agenda` facilitaría.

### Prioridad baja

- **Export** — Exportar un proyecto o report a PDF/HTML para compartir.
- **Colores/temas** — Output ANSI fijo; un `ORBIT_THEME` o `--no-color` para entornos sin soporte.

---

## Refactorización de software

### Prioridad alta

- **`main()` en orbit.py — 477 líneas** — Todo el argparse en una sola función. Extraer la construcción del parser a función separada haría el CLI testeable y extensible.
- **Tests para módulos críticos sin cobertura**:
  - `log.py` (247 líneas, 0 tests)
  - `gsync.py` (748 líneas, 0 tests)
  - `stats.py` (306 líneas, 0 tests)
  - `commit.py` (341 líneas, 0 tests)
- **`encoding='utf-8'` explícito** — 65 llamadas a `.read_text()`/`.write_text()` sin encoding. Funciona en macOS pero fallaría en Windows.

### Prioridad media

- **Tests para agenda_view.py** — 579 líneas de visualización sin tests. Tests de snapshot protegerían el formato.
- **Excepciones específicas en gsync.py** — 7 `except Exception` genéricos. Usar tipos concretos (`ValueError`, `KeyError`, `HttpError`).

### Prioridad baja

- **migrate.py + importer.py** — 990 líneas de código de un solo uso. Mover a `tools/` o `legacy/` para no ensuciar `core/`.

---

## Orden recomendado

1. Tests para `log.py` y `stats.py` (riesgo de regresión alto)
2. Extraer parser de `main()` (desbloquea testing del CLI)
3. `encoding='utf-8'` (cambio mecánico, una pasada)
4. Recurrencia en agenda (funcionalidad más visible que falta)

---

## Bug detectado

- `orbit note create orbit "título"` falla — conflicto entre subparser `create` y el shorthand positional del padre. `args.project` queda `None`.

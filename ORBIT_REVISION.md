# Orbit — Revisión y plan de mejora

Análisis del estado actual de Orbit (v0.18.1) con propuestas de simplificación, unificación y mejora.

---

## A. Conceptual / UX

### A1. Interfaz uniforme de las 4 citas

Las 4 citas (task, ms, ev, reminder) deberían tener la misma interfaz. Estado actual:

| Feature | task | ms | ev | reminder |
|---------|------|----|----|----------|
| add | ✓ | ✓ | ✓ | ✓ |
| done | ✓ | ✓ | — | — |
| drop (-o/-s) | ✓ | ✓ | ✓ | ✓ |
| edit | ✓ | ✓ | ✓ | ✓ |
| list | ✓ | ✓ | ✓ | ✓ |
| ls | ✓ | ✓ | ✓ | ✓ |
| log (→ logbook) | — | — | ✓ | — |
| --desc | ✓ | ✓ | ✓ | **no** |
| --ring | ✓ | ✓ | ✓ | **no** (usa date+time) |
| gsync | ✓ | ✓ | ✓ | **no** |

**Propuestas:**
- [ ] Añadir `--desc` a `reminder add/edit` (notas indentadas, como task/ms/ev)
- [ ] Considerar si `ev log` debería existir también para task/ms (crear logbook entry desde una cita)
- [ ] Considerar si reminders deberían sincronizarse con Google (¿Tasks? ¿Calendar?)

### A2. Nombres de argumentos posicionales inconsistentes en `ls`

- `ls tasks [project...]` — acepta múltiples proyectos (`nargs="*"`, attr `projects`)
- `ls ms [project...]` — acepta múltiples proyectos (`nargs="*"`, attr `projects`)
- `ls ev [project]` — acepta uno solo (`nargs="?"`, attr `project_name`)
- `ls reminders [project]` — acepta uno solo (`nargs="?"`, attr `project_name`)
- `ls hl [project]` — acepta uno solo (`nargs="?"`, attr `project_name`)

**Propuesta:**
- [ ] Unificar: todos aceptan `[project...]` (múltiples) con attr `projects`
- [ ] O todos aceptan `[project]` (uno solo) — depende de qué sea más útil

### A3. Parámetros `--from`/`--to` con nombres internos distintos

- `ls ev`: `period_from`, `period_to`
- `search`, `agenda`, `report`: `date_from`, `date_to`

**Propuesta:**
- [x] Unificar a `date_from`/`date_to` en todos los comandos

### A4. Subcomando `project` usa `sub` en vez de `action`

- task, ms, ev, reminder, hl, note: usan `dest="action"`
- project: usa `dest="sub"`

**Propuesta:**
- [x] Renombrar a `action` para consistencia

### A5. Prompt de confirmación: `[s/N]` vs `[S/n]`

- `drop` no recurrente: `[s/N]` (defecto No) — correcto, operación destructiva
- `deliver a cloud`: `[S/n]` (defecto Sí) — correcto, casi siempre quieres entregar
- `añadir a git`: `[S/n]` (defecto Sí)
- `ring prompt`: `[5m]` (defecto 5m, 0=no)

**Estado:** Bien alineados. No requiere cambios.

### A6. El comando `ev log` podría generalizarse

`ev log` crea una entrada en logbook desde un evento. Podría ser útil para task/ms:
- `task log` — registrar en logbook que trabajaste en una tarea
- `ms log` — registrar un hito alcanzado con más detalle en logbook

**Propuesta:**
- [ ] Evaluar si añadir `task log` y `ms log` (bajo prioridad)

### A7. Abreviatura `ls rem` en vez de `ls reminders`

`ls tasks`, `ls ms`, `ls ev` son cortos. `ls reminders` es largo.

**Propuesta:**
- [x] Añadir alias `rem` → `reminders` en el parser de ls
- [x] Alias `rem` → `reminder` en el comando principal

---

## B. Técnico

### B1. Validación duplicada en los 4 `add`

Los bloques de validación de date/time/recur/ring/until son casi idénticos en:
- `run_task_add` (~20 líneas)
- `run_ms_add` (~20 líneas)
- `run_ev_add` (~20 líneas)
- `run_reminder_add` (~15 líneas)

**Propuesta:**
- [x] Extraer a `_validate_add_params(date_val, time_val, recur, until, ring)` → returns error msg or None

### B2. Prompt de ring duplicado en 3 `add`

El bloque `_prompt_ring()` + validación se repite idéntico en task/ms/ev add.

**Propuesta:**
- [x] Extraer a `_prompt_and_validate_ring()` → returns ring value or None

### B3. Dos funciones de selección interactiva casi idénticas

- `_select_item()` — para task/ms (filtra por `status == "pending"`)
- `_select_event()` — para ev (sin filtro de status)
- `_select_item_reminder()` — para reminders (filtra por `not cancelled`)

**Propuesta:**
- [ ] Unificar en `_select_from_list(items, label, text, filter_fn, display_fn)`
- [ ] Cada tipo pasa su propio filtro y formato de display

### B4. Dispatchers verbose en orbit.py

Cada `cmd_*` tiene 5-15 líneas de `getattr()` repetitivos para cada acción.

**Propuesta:**
- [ ] Crear helper `_extract_args(args, *fields)` que devuelve un dict
- [ ] Reducir cada dispatcher a 2-3 líneas por acción

### B5. Shell manipula sys.argv directamente

```python
old_argv = sys.argv
sys.argv = ["orbit"] + tokens
try: main()
finally: sys.argv = old_argv
```

**Propuesta:**
- [ ] Extraer `run_command(argv: list) -> int` que recibe argv sin manipular global
- [ ] El shell llama a `run_command()` en vez de `main()`

### B6. Undo tracking manual (commit/discard)

Cada comando en el shell necesita `commit_operation()` / `discard_operation()` explícito.

**Propuesta:**
- [ ] Context manager: `with track_operation("task add..."): main()`

### B7. Estructura de datos de reminders difiere de task/ms

- Tasks/ms: `status: "pending"|"done"|"cancelled"`
- Reminders: `cancelled: bool` (sin campo status)

**Propuesta:**
- [ ] Evaluar si unificar a `status` (requiere migración de agenda.md existentes)
- [ ] O aceptar la diferencia (reminders son conceptualmente distintos — no se completan)

### B8. `_d()` helper: el string `"none"` como valor especial

`_d()` devuelve `"none"` (string) para el valor especial, pero luego los edit comparan `if new_date == "none"`. Mezcla de None (python) y "none" (string).

**Propuesta:**
- [ ] Estandarizar: `_d()` devuelve None para "none", usar sentinel separado si hace falta

### B9. gsync: error handling por evento pero no por tarea

El try/except por item se añadió para eventos pero no para tasks/milestones.

**Propuesta:**
- [x] Añadir el mismo try/except a `_sync_tasks_for_project`

---

## C. Prioridades sugeridas

### Rápidos (alto valor, poco esfuerzo) — ✅ completados
1. ~~**B1** — Extraer validación común de `add`~~
2. ~~**B2** — Extraer prompt+validación de ring~~
3. ~~**A3** — Unificar `period_from` → `date_from`~~
4. ~~**A4** — `project sub` → `action`~~
5. ~~**A7** — Alias `rem` para `reminder`/`ls reminders`~~
6. ~~**B9** — try/except por tarea en gsync~~

### Medio esfuerzo
7. **B3** — Unificar funciones de selección interactiva
8. **B4** — Simplificar dispatchers
9. **A2** — Unificar args posicionales en `ls`
10. **A1** — `--desc` para reminders

### Arquitectural (largo plazo)
11. **B5** — `run_command()` en vez de sys.argv
12. **B6** — Context manager para undo
13. **B8** — Limpiar `_d()` y el patrón "none"
14. **A6** — `task log` / `ms log`

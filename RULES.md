# RULES.md — Invariantes del sistema

Propiedades que **siempre** deben cumplirse en el repo. Si una operación las viola hay que parar y revisar el diseño antes de seguir.

Cada regla apunta a su ADR en [DECISIONS.md](DECISIONS.md) con el razonamiento detallado.

---

## Arquitectura

### `core/` no importa de `views/` salvo lazy

`core/` contiene los **writers de la verdad** + infraestructura. `views/` contiene los **readers** que producen artefactos derivados (HTML, .ics, ring.json, reports de doctor).

- **Top-level prohibido**: ningún módulo de `core/` puede tener `from views.X import Y` ni `import views.X` en la cabecera.
- **Lazy permitido**: dentro de una función, `from views.X import Y` es aceptable cuando el caller es:
  - Una hook action (`_action_*`)
  - Un wrapper cloud (`cloudsync`, `deliver` → `views.render`)
  - Un check pre-/post-commit (`commit` → `views.doctor`)
  - Scheduling AppleScript-direct legacy (`core.agenda.{lifecycle,runners}` → `views.ring.parse`)
  - El seam API (`core.api` → `views.ring.parse`)
- **Tipos compartidos** entre `core/` y `views/` viven en `core/types.py` (e.g. `Issue`), no en `views/`.

Ver [ADR-033](DECISIONS.md#adr-033--separación-corewriters-vs-viewsreaders).

**Excepción documentada — `views/ring/export.py` backfill de `orbit_id`**: el ring exporter reescribe la línea en `agenda.md` cuando un item lleva `🔔` pero no `[orbit:XXXX]`. Justificación y tradeoffs en [ADR-041](DECISIONS.md#adr-041--excepción-a-views-no-escriben-verdad-backfill-de-orbit_id-en-ring-export). Si añades otra excepción, primero pregúntate si no estás reintroduciendo escrituras en views por la puerta de atrás.

---

## Shell

### Un shell fijado no toca otro proyecto, ni el workspace

Un shell arrancado con `--project X` (o `ORBIT_PROJECT`) trabaja **sólo** en ese proyecto durante toda su vida. Tres invariantes, en `core/context.py`:

- **Inmutable**: no existe verbo para cambiar de proyecto fijado. Si añades uno, rompes la garantía que hace segura la desaparición del argumento `project`.
- **El posicional se quita de la gramática, no se rellena después**: `add_project_arg()` omite el argumento cuando hay fijado. Rellenarlo tras parsear no funciona — argparse asigna de izquierda a derecha y `log "texto"` ya habría leído *"texto"* como proyecto.
- **Nombrar otro proyecto es error, nunca un destino distinto**: el guardia de `run_command` corre sobre el argv crudo, antes de parsear. Un comando nuevo que acepte proyectos no necesita hacer nada; uno que los acepte por una vía rara (ni posicional `project`, ni `projects`, ni `--project`) debe declararlo en `core/context.py`.

**El panel general es el dueño del workspace.** El fijado arranca en modo ligero: ninguna acción de la cadena `shell_start`, ni cadena de medianoche, ni consumo del aviso del watchdog. Si añades un action de arranque, hereda la regla sin tocar nada — y si crees que tu action *debe* correr también en el panel fijado, comprueba antes qué pasa con dos ventanas abiertas a la vez.

Ver [ADR-049](DECISIONS.md#adr-049--panel-de-proyecto-shell-fijado-a-un-proyecto-inmutable-y-en-modo-ligero).

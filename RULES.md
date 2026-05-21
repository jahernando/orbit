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

**Excepción documentada — `views/ring/export.py` backfill de `orbit_id`**: el ring exporter reescribe la línea en `<project>-agenda.md` cuando un item lleva `🔔` pero no `[orbit:XXXX]`. Justificación y tradeoffs en [ADR-041](DECISIONS.md#adr-041--excepción-a-views-no-escriben-verdad-backfill-de-orbit_id-en-ring-export). Si añades otra excepción, primero pregúntate si no estás reintroduciendo escrituras en views por la puerta de atrás.

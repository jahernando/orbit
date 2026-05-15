# ROADMAP.md — trabajo comprometido pendiente

Este fichero lista trabajo **decidido pero no empezado** o **en pausa
deliberada**. A diferencia de [IDEAS.md](docs/IDEAS.md) (ideas sin decidir),
las entradas aquí ya tienen luz verde para implementarse — solo falta
acometerlas.

Diferencia con [ORBIT_REVISION.md](docs/conv/ORBIT_REVISION.md): ese
fichero (archivado en `docs/conv/`) fue la revisión sistemática del
estado en v0.18.1 — congelado en el tiempo, valor histórico.
ROADMAP.md mira hacia adelante: features y revisiones nuevas
pendientes de hacer.

---

## 1. Actualizar acciones del workflow de CI a Node.js 24

**Estado**: pendiente, fecha objetivo **2026-06-02**.

**Objetivo**: en `.github/workflows/tests.yml`, bumpear:
- `actions/checkout@v4` → `@v5`
- `actions/setup-python@v5` → `@v6`

**Motivo**: GitHub forzará Node.js 24 como runtime de Actions el 2026-06-02.
Las versiones actuales corren sobre Node.js 20 y, aunque seguirán
funcionando un tiempo gracias a `ACTIONS_ALLOW_USE_UNSECURE_NODE_VERSION`,
queremos quitarnos el aviso de deprecación.

**Estimación**: 5 min (editar 2 líneas + verificar que el run sigue verde).

---

## 2. Visor de `.ics` sin Calendar.app (HTML local lanzado desde terminal)

**Estado**: pendiente. Decidido como ruta única tras descartar la TUI
(khal/calcurse) — el HTML servido en `localhost` y abierto en el navegador
gana en aspecto y reaprovecha el pipeline de `core/render.py`, sin perder
la ergonomía de "un comando en terminal".

**Objetivo**: comando `orbit cal` (o `orbit kal`) que:

1. Renderiza los `.ics` que orbit ya emite (mirror local en
   `<workspace>/.cache/ics/`, v0.34) a un `calendar.html` con vistas
   semana/mes navegables.
2. Sirve el HTML en `localhost:PORT` con `python -m http.server` en
   background.
3. Lanza el navegador (`open http://localhost:PORT` en macOS,
   `xdg-open` en Linux) y deja el server vivo hasta `Ctrl-C` o hasta
   cerrar la pestaña.

Sin dependencia de Calendar.app, iCloud, ni subscriptions.

**Diseño tentativo**:
- Una única página por workspace (multi-workspace = varias pestañas).
- Render: tabla HTML con celdas día × hora + bloques de eventos
  posicionados. Alternativa más rica: embed [FullCalendar.js](
  https://fullcalendar.io) con los `.ics` como data sources →
  navegación cliente día/semana/mes sin re-renderizar.
- Color por tipo de proyecto (☀️/💻/📚/...) o por workspace.
- Notas indentadas (`📋` / `🚪` / `✉️`) como sub-líneas o tooltip.
- Solo lectura: ningún botón "editar" — orbit es la verdad.

**A decidir antes de empezar**:
- ¿Render estático (tabla HTML pura, sin JS) o dinámico (FullCalendar.js)?
  Estático es ~1 día, dinámico ~2 días pero la navegación queda mucho
  mejor. Recomendación: FullCalendar.js de CDN — sin build step, sin
  añadir deps Python.
- ¿Vistas: semana + mes solamente, o también día y agenda-lista?
- ¿Puerto fijo (siempre 8765) o aleatorio? Fijo facilita re-abrir desde
  cualquier pestaña, aleatorio evita colisiones si lo lanzas dos veces.
- ¿Server vive hasta `Ctrl-C` (foreground) o se autodetiene a los X
  minutos (background daemon, similar al ring daemon)?

**Estimación**: 1-2 días (incluye decidir FullCalendar.js vs estático,
generador HTML, integración con `orbit` CLI y test).

**Descartado por el camino** (mover a IDEAS.md si surge interés):
- TUI con khal o calcurse: aspecto inferior al HTML, y la ergonomía
  terminal-only no aporta en el setup del usuario (siempre con GUI).
- HTML estático "sin server" en el cloud: pierde la navegación cliente
  y obliga a re-renderizar en cada commit; el server local es trivial
  y resuelve ambas cosas.

---

## 3. Fase 3 del plan de simplificación · Reemplazar internals con libs estándar

**Estado**: 3.A ✅ + 3.B ✅ + 3.C ✅ cerradas 2026-05-15. **Fase 3 completa.**

**Objetivo**: delegar mecánica RFC 5545 y recurrencia a libs maduras + reorganizar el monolito de agenda. Ahorro neto de mecánica −120 ℓ (más correctitud en edge cases); 3.C suma +170 ℓ de docstrings de subpaquete pero rompe el monolito de 2202 ℓ en seis módulos manejables.

**Orden táctico**:

- **3.A · `icalendar` ✅** (commits `f63f7ac` + `5223dbd` + `40d4a93` + `9846194`, 2026-05-15). Sustituye el hand-rolled ICS en `core/ics.py`, `core/ics_share.py` y `core/email._parse_ics`. Ahorro real: **−110 ℓ netas + 17 tests de implementación borrados**. Ver [ADR-029](DECISIONS.md#adr-029--migración-a-icalendar-pypi-para-mecánica-rfc-5545).

- **3.B · `python-dateutil` ✅** (commit `e130c38`, 2026-05-15). Sustituye la aritmética manual de `_next_occurrence` en `core/agenda_cmds.py` con `relativedelta(months=N)` (clamp natural) + `rrule(MONTHLY/DAILY, byweekday=..., bysetpos=±1)` (weekdays, first-X, last-X). Ahorro real: **−13 ℓ netas**; los 12 tests existentes (`TestNextOccurrence`) pasan sin cambios. La dep ya estaba como transitiva de `icalendar` — coste real cero. Ver [ADR-030](DECISIONS.md#adr-030--migración-a-python-dateutil-para-la-mecánica-de-recurrencia).

- **3.C · Partir `core/agenda_cmds.py` ✅** (commit `1db9fba`, 2026-05-15). 2202 ℓ → subpaquete `core/agenda/{recurrence,io,display,lifecycle,runners,startup}.py` (6 módulos entre 120 y 840 ℓ) + shim de 28 ℓ en `core/agenda_cmds.py` que preserva la compat para los ~20 callers externos. **Reorganización, no consolidación**: ninguna función borrada, suite sin cambios (1536 → 1536). El acoplamiento previsto con cronograma 2.3.2 (campo `composite` en task) queda pospuesto: la partición se hizo con `composite=None` placeholder y se rellenará al final del plan. Ver [ADR-031](DECISIONS.md#adr-031--partir-coreagenda_cmdspy-en-subpaquete-coreagenda).

---

## 4. Fase 4 del plan de simplificación · Simplificar API/CLI

**Estado**: 4.A ✅ cerrada 2026-05-15. 4.B pendiente.

**Objetivo**: `orbit.py` de ~2200 ℓ → ~800 ℓ a través del seam `orbit/api.py`. CLI navegable por intuición, no por chuleta.

**Piezas**:

- **4.A · Convención `noun verb` ✅** (commit `e46931f`, 2026-05-15). Tras Fase 2 (`orbit cloud {deliver,sync,imgs}`, `orbit task crono <sub>`) y 4.A (`orbit tracked {add,drop,list}`), el patrón está aplicado donde encajaba. Atajos top-level mantenidos para uso diario: `deliver`, `crono`, `track`, `untrack`, `log`, `dash`, `commit`, `shell`. **No aplicado a `ics`** por conflicto técnico de argparse (positional `project nargs="?"` + 5 flags + add_subparsers no combinan sin romper la UX actual de `orbit ics <project>`); `ics-share`/`ics-import` se mantienen flat. Decisión registrada en el commit.

- **4.B · Seam estable `orbit/api.py`** con funciones puras (`add_task(project, title, **kw) → Task`, `add_event(...)`, `add_milestone(...)`, etc.) que CLI, hooks y scripts externos llaman. Independiente para las 4 citas básicas. `add_task_composite(...)` queda para cuando 2.3.2 cierre. Aprovechar el seam para revisitar `ics` con subcomandos sin romper UX (preprocesado controlado en el seam, no en argparse).

**Pendiente cronograma (sub-pasos 2.3.2/2.3.3)**: ver [ADR-028](DECISIONS.md#adr-028--cronograma-como-task-compuesta-extensión-del-sistema-task) y `MODULES.md §5`. Diseño del vínculo `agenda.md ↔ cronos/`, done-cascading y migración de datos en ambos workspaces. Pospuesto al final del plan (después de 4.B).

**Estimación restante**: 4.B ~2-3 días.

---

## Convenciones del fichero

- Cada entrada lleva: **Estado**, **Objetivo**, **A decidir** (si aplica),
  **Estimación**.
- Cuando una entrada se completa, se mueve la nota a la sección
  correspondiente de [CLAUDE.md](CLAUDE.md) ("Estado actual") y se borra
  de aquí.
- Si una entrada se abandona, se mueve a [IDEAS.md](docs/IDEAS.md) con
  comentario explicando por qué no se hizo.

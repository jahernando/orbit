# ROADMAP.md — trabajo comprometido pendiente

Este fichero lista trabajo **decidido pero no empezado** o **en pausa
deliberada**. A diferencia de [IDEAS.md](IDEAS.md) (ideas sin decidir),
las entradas aquí ya tienen luz verde para implementarse — solo falta
acometerlas.

Diferencia con [ORBIT_REVISION.md](ORBIT_REVISION.md): ese fichero es la
revisión sistemática del estado actual (housekeeping de la base de
código existente). ROADMAP.md mira hacia adelante: features y revisiones
nuevas pendientes de hacer.

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

**Estado**: pendiente. Plan táctico decidido 2026-05-15 al cierre de Fase 2.

**Objetivo**: ~−1000 ℓ de código propio a cambio de 2 deps pip nuevas (`icalendar`, `python-dateutil`). Registro de la decisión en `DECISIONS.md` al adoptar y bump en `DEPENDENCIES.md §3`.

**Orden táctico recomendado** (de más aislado a más entrelazado):

- **3.A · `icalendar`** (PyPI) sustituye el hand-rolled ICS en `core/ics.py`, `core/ics_share.py` y `core/email._parse_ics`. Ahorro estimado: 500-800 ℓ. **Independiente del estado de cronograma** (cronograma no usa ICS más allá del bucket que emite `.ics.py`).

- **3.B · `python-dateutil.rrule`** sustituye la lógica hand-rolled de recurrencia en `core/agenda_cmds.py` y `core/ring.py`. Ahorro estimado: 200-400 ℓ. **Independiente de cronograma** (cronograma usa scheduling propio `after:1.2` + working days, no RRULE).

- **3.C · Partir `core/agenda_cmds.py`** (2245 ℓ) → subpaquete `core/agenda/{io,recurrence,task,ms,ev,reminder}.py`. **Parcialmente acoplado a cronograma**: si el sub-paso 3.2 del plan (ADR-028) decide añadir un campo `composite: <name>` al modelo task, conviene saberlo antes. Alternativa: partir con `composite=None` placeholder y rellenar después.

**Decisión paralela a registrar**: subir deps pip de 2 (`markdown`, `pyobjc-framework-EventKit`) a 4 (`+icalendar`, `+python-dateutil`). Trade-off consciente: ~1000 ℓ menos de código propio + menos edge cases de TZ/RRULE serialization a cambio de 2 dependencias mantenidas por terceros.

**Estimación**: 3.A ~1 día, 3.B ~1 día, 3.C ~1-2 días (depende de si cronograma 3.2 está cerrado).

---

## 4. Fase 4 del plan de simplificación · Simplificar API/CLI

**Estado**: pendiente. Algunas piezas ya parcialmente iniciadas en Fase 2 (cluster cloud, task crono).

**Objetivo**: `orbit.py` de ~2200 ℓ → ~800 ℓ. CLI navegable por intuición, no por chuleta.

**Piezas**:

- **4.A · Convención `noun verb` para el resto del CLI**. Ya iniciada: `orbit cloud {deliver,sync,imgs}` (Fase 2.1) y `orbit task crono <sub>` (Fase 2.3.1). Aplicar al resto donde tenga sentido: `orbit ics share`, `orbit hl add`, etc. Mantener atajos top-level para los verbos de uso diario (`log`, `dash`, `commit`, `shell`). Independiente de cronograma.

- **4.B · Seam estable `orbit/api.py`** con funciones puras (`add_task(project, title, **kw) → Task`, `add_event(...)`, `add_milestone(...)`, etc.) que CLI, hooks y scripts externos llaman. Independiente para las 4 citas básicas. `add_task_composite(...)` queda para cuando 3.2 cierre.

**Pendiente cronograma (sub-pasos 3.2/3.3)**: ver [ADR-028](DECISIONS.md#adr-028--cronograma-como-task-compuesta-extensi%C3%B3n-del-sistema-task) y `MODULES.md §5` (orden táctico Fase 2). Diseño del vínculo `agenda.md ↔ cronos/`, done-cascading y migración de datos en ambos workspaces. No bloquea 3.A, 3.B, 4.A ni la mitad básica de 4.B.

**Estimación**: 4.A ~1-2 días, 4.B ~2-3 días (el seam requiere refactor de dispatchers en `orbit.py`).

---

## Convenciones del fichero

- Cada entrada lleva: **Estado**, **Objetivo**, **A decidir** (si aplica),
  **Estimación**.
- Cuando una entrada se completa, se mueve la nota a la sección
  correspondiente de [CLAUDE.md](CLAUDE.md) ("Estado actual") y se borra
  de aquí.
- Si una entrada se abandona, se mueve a [IDEAS.md](IDEAS.md) con
  comentario explicando por qué no se hizo.

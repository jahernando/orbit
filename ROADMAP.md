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

## 3. Cronograma 2.3.2/2.3.3 — vínculo agenda↔cronos como task-compuesta

**Estado**: pospuesto al final del plan de simplificación. Resto de Fase 4 (4.A + 4.B) ya cerrado en v0.38; este es el único sub-paso pendiente del plan completo.

**Objetivo**: integrar el modelo de cronograma como **task compuesta** en la propia agenda — un único sistema de tareas con sub-pasos opcionales, en vez de dos sistemas paralelos (`task` + `cronograma`). Ver [ADR-028](DECISIONS.md#adr-028--cronograma-como-task-compuesta-extensión-del-sistema-task) y `MODULES.md §5`.

**Sub-pasos**:

- **2.3.2 · Diseño del vínculo agenda.md ↔ cronos/** — campo `composite` en task (placeholder ya añadido en Phase 3.C); done-cascading entre task padre y sub-tareas; representación markdown del cronograma; reglas de migración para datos existentes en ambos workspaces.

- **2.3.3 · Ejecución de la migración** — convertir los cronogramas existentes en `🚀orbit-ws` y `🌿orbit-ps` al nuevo formato; actualizar `core/agenda/` para entender el campo `composite`; ajustar render/secretary para mostrar la jerarquía.

**Estimación**: 2.3.2 ~1-2 días de diseño + 2.3.3 ~1-2 días de ejecución.

---

## Convenciones del fichero

- Cada entrada lleva: **Estado**, **Objetivo**, **A decidir** (si aplica),
  **Estimación**.
- Cuando una entrada se completa, se mueve la nota a la sección
  correspondiente de [CLAUDE.md](CLAUDE.md) ("Estado actual") y se borra
  de aquí.
- Si una entrada se abandona, se mueve a [IDEAS.md](docs/IDEAS.md) con
  comentario explicando por qué no se hizo.

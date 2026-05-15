# DECISIONS.md

Registro vivo de las decisiones arquitectónicas de orbit, en formato ADR ligero (una página por decisión, con contexto + decisión + consecuencias + estado).

Las decisiones están ordenadas por orden de adopción, no por importancia. Las marcadas como **DEROGADA** se reemplazaron por una decisión posterior; quedan aquí porque el código todavía las refleja parcialmente o porque su lección es útil. Las marcadas como **VIGENTE** son el estado actual.

---

## Mapa mental del sistema

Orbit tiene **dos subsistemas relacionados** pero conceptualmente independientes:

1. **Sistema de log curado** — el seguimiento de actividad por proyecto. Vive en `logbook.md` (append-only) + `project.md` (metadata) por proyecto. El usuario añade entradas con `note`, `hl`, `log`, `email`, y al hacer `commit` el render produce HTML para revisar en el móvil.

2. **Sistema de agenda** — tareas (task), hitos (ms), eventos (ev), recordatorios (rem) y cronogramas. Vive en `agenda.md` por proyecto + `cronos/crono-*.md`. La verdad es el markdown; orbit emite `.ics` para que clientes de calendario (Calendar.app, Google Calendar, etc.) se suscriban.

Ambos subsistemas se cruzan en **`logbook.md`**: cualquier cita puede generar una entrada de logbook (`task log`, `ev log`), y cualquier email capturado deja una entrada en logbook + opcionalmente una cita en agenda.

La **fuente de verdad** es el markdown del repo (versionado con git). El cloud es **réplica read-only** (HTML + ficheros pesados); los calendarios suscritos son **réplica read-only** (`.ics`).

------

---

## ADR-001 — Markdown plano como modelo de datos
**Estado**: VIGENTE
**Contexto**: alternativa habitual sería SQLite o JSON estructurado.
**Decisión**: todo el estado del usuario (proyectos, agendas, logs, notas) vive en ficheros `.md`/`.json` planos editables con cualquier editor.
**Consecuencias positivas**: editabilidad sin orbit, diffs git legibles, recuperación trivial, herramientas terceras (grep, ripgrep, etc.) funcionan tal cual, futuro-proof.
**Consecuencias negativas**: validación más cara (parsers tolerantes, doctor que repare); operaciones de bulk (ej. mover tareas entre proyectos) son edición de texto.
**Cuando se revisaría**: nunca probablemente. Es el principio fundacional.

---

## ADR-002 — Git como backbone
**Estado**: VIGENTE
**Decisión**: cada workspace es un repositorio git. Cada `orbit commit` ejecuta un git commit + push.
**Consecuencias**: versionado automático, recuperación de cualquier estado, sincronización entre máquinas vía remote, history del proyecto sin tooling adicional.

---

## ADR-003 — Single-user, no multi-tenant
**Estado**: VIGENTE
**Decisión**: orbit es para una persona. No permisos, no resolución de conflictos colaborativos, no identidad de usuario.
**Consecuencias**: el código es pragmático y libre de abstracciones genéricas. Si dos personas quisieran colaborar, harían fork + merge manual.

---

## ADR-004 — CLI interactiva como UI primaria
**Estado**: VIGENTE
**Decisión**: shell propio (`orbit`) con dispatcher central + comandos cortos. No hay UI web ni desktop app.
**Consecuencias**: barrera de entrada alta (terminal); zero overhead; integración natural con scripting y editor.

---

## ADR-005 — Separación código / datos en dos directorios
**Estado**: VIGENTE
**Decisión**: `~/orbit/` es el código (público en GitHub); `~/🚀orbit-ws/` y `~/🌿orbit-ps/` son los workspaces (privados).
**Consecuencias**: el código se puede compartir; los datos quedan locales. `ORBIT_HOME` env var selecciona workspace.

---

## ADR-006 — Federation read-only entre workspaces
**Estado**: VIGENTE
**Decisión**: un workspace puede leer del otro (panel, agenda, search, ls) sin poder escribir.
**Consecuencias**: vista unificada de la semana cruzando profesional y personal; la escritura permanece local al workspace para evitar acoplamiento.

---

## ADR-007 — Cinco tipos de cita con CRUD uniforme
**Estado**: VIGENTE
**Decisión**: `task`, `ms` (milestone), `ev` (event), `reminder` (rem), `cronograma`. Comparten `add/drop/edit/list/log`. Cada uno tiene su sección en `agenda.md`.
**Consecuencias**: curva de aprendizaje mínima una vez sabes uno. Algún código duplicado entre formatters/parsers (deuda manejable).
**Tradeoff considerado**: unificar en un solo tipo con flag. Descartado por ahora — los emojis y secciones separadas facilitan la lectura del markdown a mano.

---

## ADR-008 — orbit-id (8-hex) como identidad estable
**Estado**: VIGENTE (desde v0.28)
**Decisión**: cada cita lleva un tag `[orbit:xxxxxxxx]` en `agenda.md`. Los IDs son **locales al workspace** (no globales).
**Consecuencias**: renames, cambios de fecha, recurrencia y timeouts no rompen la identidad. Cualquier export (.ics) lleva el id en SUMMARY/DESCRIPTION/X-ORBIT-ID para referencia desde clientes externos.

---

## ADR-009 — Recurrencia expandida localmente, no RRULE en `.ics`
**Estado**: VIGENTE (desde v0.32)
**Decisión**: orbit avanza ocurrencias localmente al hacer `task done`/`drop`. En `.ics` se emite un VEVENT por ocurrencia dentro de una ventana ±180 días (no RRULE).
**Consecuencias**: cada ocurrencia es un VEVENT independiente → overrides de una sola ocurrencia (mover una clase a otra hora) son triviales. Coste: más bytes en el `.ics` (~700KB peor caso por serie diaria-año, asumible).
**Tradeoff**: RRULE sería más compacto pero rompería el modelo "avanza ocurrencia al hacer done".

---

## ADR-010 — agenda.md es la verdad, `.ics` es transporte
**Estado**: VIGENTE (desde v0.32)
**Decisión**: la dirección de la verdad va de `agenda.md` hacia `.ics`, nunca al revés. No hay reverse sync (Calendar.app → orbit).
**Contexto**: la inversión ("`.ics` como verdad para poder editar en Calendar.app") se consideró y se descartó: rompe editabilidad markdown, diffs git legibles, workflow móvil vía inbox.md.
**Consecuencias**: reorganizar requiere `orbit reorganize` o `task edit`/`ev edit`; no se puede tocar Calendar.app esperando que llegue a orbit.

---

## ADR-011 — `.ics` floating local time (sin TZID)
**Estado**: VIGENTE
**Decisión**: los DTSTART/DTEND del `.ics` no llevan `TZID=` ni el sufijo `Z`. El cliente los interpreta en su zona horaria local.
**Consecuencias**: simple, encaja con el modelo (orbit no maneja zonas horarias). Cuando viajes con orbit (Madrid → otro huso), las citas se desplazarán visualmente — entonces toca añadir `TZID=Europe/Madrid`.

---

## ADR-012 — Tres buckets de `.ics` por workspace
**Estado**: VIGENTE (configurable en `calendar-sync.json:ics_buckets`)
**Decisión**: `events.ics` (event), `ms.ics` (milestone), `agenda.ics` (task + reminder + cronograma). Permite asignar colores distintos en el cliente de calendar.
**Tradeoff considerado**: dos buckets (events+ms juntos). Descartado porque los milestones merecen destacar visualmente como deadlines.
**Tradeoff considerado**: un bucket por kind (5 calendarios). Descartado por gestión de muchos calendarios suscritos.

---

## ADR-013 — Duraciones sintéticas en `.ics` (presentación, no datos)
**Estado**: VIGENTE (desde v0.33)
**Decisión**: las citas sin duración explícita reciben una duración default en `.ics` para que sean visibles en clientes:
- event/milestone/task/cronograma: 60 min
- reminder: 5 min
Solo en `.ics`. `agenda.md` no contiene este dato.
**Consecuencias**: si un usuario añade un evento "rápido" sin `--end-time`, lo verá como bloque de 1h en Calendar.app aunque no haya bloqueado realmente 1h. Es una decisión de **presentación**, no de planificación.

---

## ADR-014 — Cloud como réplica HTML read-only
**Estado**: VIGENTE
**Decisión**: tras cada `commit`, los `.md` se renderizan a `.html` y se copian al `cloud_root` (OneDrive/Google Drive). Ficheros pesados (pdf/imagen/etc.) se **copian** al cloud para ser referenciables desde el HTML; el original sigue donde el usuario lo tenía en el workspace local (no se mueve, se duplica).
**Razón**: visores móviles (Drive/OneDrive Android) no permiten editar markdown, pero sí navegar HTML siguiendo URLs.
**Comando**: `orbit deliver <proyecto> <fichero>` hace la copia explícita; el render automático tras commit también copia los pesados de los proyectos modificados.
**Limitación conocida**: la navegación entre HTMLs en Drive/OneDrive móvil solo funciona desde el visor web (no desde la app nativa). El usuario navega por URL pública.

---

## ADR-015 — `inbox.txt` deprecado
**Estado**: VIGENTE
**Contexto**: previa intención de tener un `inbox.md` editable desde móvil que orbit recogiera al arrancar.
**Decisión**: deprecado en v0.26. Los visores de Drive/OneDrive Android no permiten editar texto cómodamente.
**Vía actual**: para captura móvil → email a uno mismo + `orbit email <proj>` al volver al Mac.

---

## ADR-016 — Email captura activa
**Estado**: VIGENTE
**Decisión**: `orbit email <proj>` captura el email seleccionado en Apple Mail (o Outlook) y lo guarda como nota + opcional cita.
**Backends**: AppleScript a Mail.app, AppleScript a Outlook (parcialmente roto en Outlook 16.108), `.eml` directo desde fichero.
**Date extraction** (v0.33): primero `.ics` adjunto, luego heurística sobre el cuerpo (ISO, DD/MM/YYYY, "22 de mayo [de 2030]", "May 22[, 2030]"), por último el send-date del email.

---

## ADR-017 — Auto-magia tras mutaciones CLI
**Estado**: VIGENTE
**Decisión**: tras cualquier `task add`, `ev edit`, `ms done`, `email <proj>`, `ics-import`, etc., orbit dispara en background:
1. `run_dash` → regenera `panel.md`, `agenda.md`, `calendar.md`
2. `write_workspace(project_filter=<proj>)` → regenera los `.ics` del workspace
3. Eventualmente, post-commit, `render_changed` → HTML al cloud + reload de Calendar.app

**Trigger central**: `orbit.py:_DASH_TRIGGERS`.
**Consecuencias**: experiencia "todo se actualiza solo"; debugging más opaco si algo falla (mitigado parcialmente con doctor + ics --validate).

---

## ADR-018 — Sincronización con Calendar.app vía `.ics` (no AppleScript-write)
**Estado**: VIGENTE (desde v0.33). Reemplaza el camino AppleScript-write.
**Contexto**: pre-v0.33, orbit empujaba a Calendar.app vía AppleScript. Padecía drift, errores -10025, sync silencioso, race conditions.
**Decisión**: emitir `.ics` al cloud público (OneDrive USC / Google Drive personal) y suscribirlo desde Calendar.app. Read-only por construcción → no hay drift posible.
**Consecuencias positivas**: cero AppleScript activo (excepto el `reload calendars` read-only); arquitectura limpia; cualquier cliente RFC 5545 funciona (Calendar.app, Google Calendar web, Outlook, Thunderbird).
**Consecuencias negativas**: latencia ~5 min en lugar de ~2 s; URL pública implica exposición (mitigable rotando el share link).
**Propagación a iPhone/iPad**: la suscripción registrada en macOS Calendar.app con "Ubicación: En mi Mac" solo aparece localmente. Para que aparezca también en iPhone/iPad, hay que añadirla a iCloud Calendar (vía `icloud.com/calendar` web). iCloud distribuye la suscripción entera (eventos + sus `VALARM` blocks) a todos los Apple devices del usuario.
**Limitación conocida**: las alarmas en calendarios suscritos en iOS son **menos fiables** que las de eventos nativos (iCloud Calendar / Exchange) — gotcha histórico de Apple. Aceptable para uso general; no fiar las citas críticas a esta cadena.
**Convivencia**: el camino AppleScript-write queda dormante detrás de flag `applescript_writes:false`. Ver `DORMANT.md`.

---

## ADR-019 — `logbook.md` append-only por proyecto
**Estado**: VIGENTE
**Decisión**: cada proyecto tiene un `logbook.md` que orbit trata como append-only. `log`, `note`, `hl add`, `task log`, `ev log`, `email <proj>` añaden líneas al final (con fecha y emoji de tipo); orbit nunca reescribe líneas existentes del logbook salvo a través de `orbit undo` (revertir la última entrada).
**Razón**: historial inmutable evita la trampa de "limpiar el log" y borrar accidentalmente contexto valioso. El logbook es la base del `orbit report`.
**Consecuencias**: el `logbook.md` crece monótonamente; si quieres "limpiar", lo haces archivando (`orbit archive`) o moviéndolo manualmente — no editando entradas. Las entradas multilínea usan indentación (2+ espacios) para continuaciones.
**Cruza con agenda**: cualquier cita puede generar entrada de logbook (`task log`, `ev log`). Es el puente entre los dos subsistemas (agenda + log).

---

## ADR-020 — Cronograma como fichero propio, no sección de `agenda.md`
**Estado**: VIGENTE (desde v0.26)
**Contexto**: la alternativa habría sido una sección `## 📊 Cronogramas` en `agenda.md` con sintaxis indentada.
**Decisión**: cada cronograma vive en `cronos/crono-<nombre>.md` dentro del proyecto. `agenda.md` solo lo lista bajo `## 📊 Cronogramas` con un link al fichero.
**Razón**: un cronograma tiene jerarquía (tareas-padre con hijos), dependencias (`after:`), fechas + duraciones por hoja, y un Gantt. Meter eso en `agenda.md` haría el parser de citas mucho más complejo. Separarlo permite que el parser de cronos sea independiente.
**Consecuencias**: hay un quinto tipo de "cita" (cronograma) que aparece en `.ics` (próxima hoja con deadline) pero su edición es vía `crono <subcomando>` o tocando `cronos/crono-*.md`, no en `agenda.md`.

---

## ADR-021 — `orbit doctor` como gate pre-commit
**Estado**: VIGENTE (desde v0.23)
**Decisión**: antes de cada `orbit commit`, doctor ejecuta una validación (sintaxis de agendas/logbooks, ics_buckets, frescura de .ics, citas con orbit-id huérfanos, etc.). Si hay errores, muestra la línea problemática y pregunta `[s/N]` antes de continuar.
**Razón**: capturar errores de edición manual (alguien tocando `agenda.md` con un editor genérico) antes de que se commiten y propaguen a HTML/.ics.
**Consecuencias**: `doctor` es el único validador "oficial" — si un check pasa doctor, el resto del sistema lo acepta. Añadir un check nuevo es añadirlo a `core/doctor.py` y queda automáticamente en el pre-commit gate.
**Override**: cuando el usuario sabe que un warning es benigno, responde `[s]` y el commit procede.

---

## ADR-022 — Mensajes y prompts en español
**Estado**: VIGENTE
**Decisión**: toda la UI (prompts, errores, output de comandos, help text, CHULETA.md, TUTORIAL.md) está en español.
**Razón**: orbit es para un usuario (hispanohablante). Optimización pragmática.
**Consecuencia**: barrera de entrada alta para no-hispanohablantes. Internacionalización (`core/i18n.py` con dict por locale) es **pendiente identificado** si el usuario eventualmente quiere compartir orbit con un colega anglo. Lista de tareas de generalización en CLAUDE.md.

---

## ADR-023 — Share/import de citas puntuales vía `.ics`
**Estado**: VIGENTE (desde v0.33)
**Decisión**: `orbit ics-share` exporta un VEVENT para attach a email; `orbit ics-import` lee un `.ics` (fichero o portapapeles) y crea una cita.
**Scope explícito**: solo citas puntuales, no series recurrentes. RRULE de entrada se ignora; recurrentes de salida exportan solo la próxima ocurrencia.

---

## ADR-024 — Ficheros tracked: copia versionada en orbit-ws con refresh automático
**Estado**: DEROGADA por **ADR-026** (v0.36, 2026-05-14). Mantenida aquí como histórico de razonamiento.
**Contexto**: hay ficheros markdown que evolucionan y viven *fuera* del workspace de orbit (DECISIONS.md en el repo del código, drafts compartidos con colaboradores, planes vivos). Querías versionarlos en orbit-ws y tener el cloud actualizado sin re-importación manual tras cada edición.
**Decisión (v0.34)**: dos modos de importación distintos para notes y highlights:

- **Static** (`--file`): copia única, fechada en el filename, congelada.
- **Dynamic / tracked** (`--track`): mirror sin fecha en `notes/<slug>.md`, registrado en `.orbit-tracked.json` por proyecto. El pre-commit hook re-importa el fichero si el origen cambió. Sólo `.md`. Frontmatter `orbit_tracked_from: <path>` como pista humana.

**Detección de conflictos** (cuatro escenarios): clean / refresh / dest_tampered / conflict; los dos últimos abortaban el commit.

**Por qué se derogó**: dos puntos de fricción reales durante el primer mes de uso:
1. Cross-links rotos — DECISIONS.md → RING.md no resolvía si RING.md no estaba también tracked.
2. Edición desde Obsidian sobre el mirror → abort en commit. Correcto pero friccional.
La copia versionada en git de orbit-ws sí era valor (historia local), pero el precio (4-scenario + abort + frontmatter + sólo-md-only) era alto para una característica usada con 3-4 ficheros típicamente. ADR-026 mantiene el espíritu (verdad fuera + ventana dentro + render al cloud) pero baja el coste a un symlink relativo.

**Tradeoff considerado en v0.34** (revisado en v0.36): symlinks rechazados entonces por (cross-volume / clone público / OneDrive sync). En v0.36 se reabrieron tras confirmar que el workspace es local-only (sin cloud sync), los clones son raros y bajo control del usuario, y el repo público es `~/orbit/` (público) — `~/🚀orbit-ws/` (privado, sin terceros que lo clonen).

---

## ADR-026 — Notes: modelo propia/externa con symlinks
**Estado**: VIGENTE (desde v0.36, 2026-05-14). Reemplaza ADR-024.
**Contexto**: tras un mes con el sistema de tracked-con-copia de v0.34, dos puntos de fricción concretos (ver ADR-024): cross-links rotos a no-tracked y abort-on-commit cuando editas el mirror sin querer desde Obsidian. La copia versionada en orbit-ws era valor menor (el repo fuente ya tiene su propia historia git en la mayoría de casos reales).
**Decisión**: simplificar a un único eje **propia / externa** basado en *dónde vive la verdad del fichero*:

- **Propia** — vive entera en el workspace, en `notes/<name>.md`. El usuario la crea, la edita, la versiona. Sin registry.
- **Externa** — vive fuera; orbit guarda un **symlink relativo** en `notes/<basename>` apuntando al fuente. El registry `.orbit-tracked.json` (esquema `{"files": {<name>: <source_path>}}`) lista qué externas hay para que render sepa cuáles publicar al cloud.

Editar la externa desde Obsidian escribe en el fuente directamente. No hay refresh, no hay 4-scenario, no hay abort. Render lee el fuente al momento; un mirror gitignored en `.cache/notes/<proj>/` actúa de fallback si el fuente no es accesible (mismo patrón que `.cache/ics/` de ADR-025).

**Comando**: `orbit track <proj> <fullpath>` (alias `note <proj> <title> --track --file <path>`). Eco de confirmación `local? <dir>` + `note? <basename>`. `untrack` borra el symlink, deja el fuente intacto.

Además, `note --from <path>` para el caso "cópiame el contenido de un fichero externo como punto de partida, pero la nota es **mía** desde el primer momento" (Drive USC compartido, email, draft de un colega que vas a hacer tuyo). Es el reemplazo del modo "static snapshot" sin reintroducirlo como modo separado.

**Migración v0.34 → v0.36** (`orbit tracked migrate`): para cada entry v0.34 con copia idéntica al fuente, borra la copia y crea symlink. Si la copia diverge, aborta para resolución manual. Idempotente.

**Consecuencias positivas**:
- Una sola verdad (el fuente externo), sin duplicación que pueda divergir.
- Edits en Obsidian fluyen al fuente, sin fricción.
- Render más simple, doctor más simple, sin pre-commit refresh hook.
- Cross-links entre externas funcionan automáticamente (siblings en `notes/` a través del symlink).
- ~200 LOC menos en `core/tracked.py` + tests.

**Consecuencias negativas**:
- Pierdes la "historia git en orbit-ws" del contenido tracked. Mitigación: el repo fuente ya la tiene en la mayoría de casos (`~/orbit` es git, repos colaborativos son git).
- En migración a otro Mac, hay una ventana entre clonar `~/orbit` y `~/🚀orbit-ws` donde los symlinks están rotos. Doctor lo flagea.
- Cross-links a ficheros NO trackeados se rompen silenciosamente en cloud HTML. Mitigación: render emite warning con la lista.
- Si el fuente desaparece y el cache local no existe, render salta esa nota con warning.

**Tradeoff considerado**:
- Mantener v0.34 (rechazado — la fricción supera el valor de la copia versionada).
- Symlink de directorio único `notes/orbit-src/` → `~/orbit/` (rechazado — expone todo el repo fuente al vault, no solo lo trackeable; mezcla visible y publishable).
- Stub files con metadata + sin copia + manifest (rechazado — Obsidian no abre el fuente, hay que navegar fuera del vault).
- Lazy refresh en render manteniendo la copia (rechazado — sigue siendo dos artefactos a sincronizar).

**Where lives**: `core/tracked.py` (~80 líneas, reescrito), `core/tracked_migrate.py` (one-shot), tests en `tests/test_tracked.py`, doctor check en `core/doctor.py`, render integration en `core/render.py::_resolve_external` + `.cache/notes/<proj>/`.

---

## ADR-025 — Copia local gitignored de `.ics` por workspace
**Estado**: VIGENTE (desde v0.34)
**Contexto**: el `.ics` es **artefacto derivado** de `agenda.md` (la verdad). Tener historia git del calendario sería útil ("¿qué cambió ayer?"), pero versionarlo contamina el repo: doblas el diff por cada edit lógico (agenda + 1-3 buckets + per-project), y abres la puerta a que `.ics` y `agenda.md` queden desfasados dentro de un commit.
**Decisión**: `core/ics.py::write_workspace` escribe a **dos sitios**:

- `<workspace>/.cache/ics/` — copia canónica local, **gitignored**. Tiene `.ics` + `.ics.snapshot` (trail para diff). Vive bajo `.cache/` (genérico, ya en `.gitignore`).
- `cloud_root/calendar/` — copia publicada para Calendar.app. Solo `.ics`, sin snapshots (no aportan valor a subscribers y ensucian sync OneDrive).

Las snapshots viven **solo en local** — son artefacto interno del diff, irrelevantes para la suscripción.

El comando **`orbit ics --diff`** renderiza in-memory y compara contra el mirror local. Muestra added/removed/changed por UID con SUMMARY humano, deduplicado entre buckets y per-project. Es el sustituto declarativo de lo que sería `git diff` sobre un `.ics` versionado.

**Consecuencias positivas**: historia "qué cambiará en el próximo render" disponible sin contaminar git; offline-friendly (el mirror sobrevive caídas de cloud sync); inspección con herramientas estándar (`cat`, `diff`).
**Consecuencias negativas**: doble escritura por render (~50 ms extra, despreciable); un directorio nuevo en cada workspace.
**Tradeoff considerado**: versionar `.ics` en git (descartado — doble diff, drift posible); snapshot solo en cloud (descartado — pierdes diff offline).

**Where lives**: `core/ics.py::_local_mirror_dir`, `core/ics.py::diff_workspace`, `orbit.py::cmd_ics` (rama `--diff`).

---

## ADR-028 — Cronograma como task-compuesta (extensión del sistema task)
**Estado**: VIGENTE (decisión 2026-05-15, Fase 2 del plan en `MODULES.md §5`). Complementa (no deroga) [ADR-020](#adr-020--cronograma-como-fichero-propio-no-secci%C3%B3n-de-agendamd).

**Contexto**: ADR-020 estableció que cada cronograma vive en su propio fichero `cronos/crono-<nombre>.md` y no se inline-a en `agenda.md`. Esa decisión es **física** (dónde viven los datos) y sigue vigente. Lo que faltaba era una decisión **conceptual** sobre qué ES un cronograma en el modelo de citas: en la documentación anterior aparecía como "quinto tipo" paralelo a task/ms/ev/reminder (CLAUDE.md lo llama así), pero su CRUD no comparte interfaz con los otros 4 — no tiene `add/drop/edit/list/log/done` uniformes, sino su propio set de 9 verbos (`add/show/edit/check/list/done/reindex/gantt/mermaid`).

**Decisión**: cronograma se modela como **task-compuesta** — una extensión del sistema `task`, no un tipo paralelo. CLI canónico: `orbit task crono <sub>`. `orbit crono <sub>` se mantiene como atajo top-level por uso diario (mismo patrón que `orbit deliver` ↔ `orbit cloud deliver`).

**Razón**: una task hoy puede tener título, fecha, status (pending/done/cancelled), recurrencia y ring. Una task-compuesta añade subtareas con índices jerárquicos, dependencias `after:`, duración por hoja, fechas calculadas (no inputadas) y visualizaciones. Es estrictamente más, no algo paralelo. La fusión conceptual con `task` ordena el modelo mental (cinco citas → cuatro tipos + composite); la separación física (ADR-020) sigue justificándose por la complejidad propia del fichero `cronos/`.

**Consecuencias**:
- Inmediatas (Fase 2 sub-paso 3.1, commit `5828196`): el CLI ya expone ambas formas. Internals de `core/cronograma.py` intactos.
- Pendientes (sub-paso 3.2): diseñar el vínculo modelo entre la task-padre en `agenda.md` y `cronos/<name>.md`. Decisiones abiertas: ¿atributo `composite: <name>` en la línea de task?, ¿done-cascading?, ¿`task crono add` crea ambos artefactos?, ¿`task crono drop` los borra a la vez? Salida natural: un futuro ADR cuando esto se decida.
- Pendientes (sub-paso 3.3): ejecución del 3.2 + script one-shot de migración para crear la task-padre faltante en los cronogramas existentes de cada workspace.
- Las menciones a "quinto tipo de cita" en CLAUDE.md y CHULETA.md deben repasarse cuando 3.2 cierre — ahora siguen ahí porque describen el comportamiento actual (cronograma sigue apareciendo en `.ics` con su propio bucket).

**Tradeoff considerado**: embed total en `agenda.md` (cronos indentado en `## ✅ Tareas` con metadata inline). Descartado: rompe `agenda_cmds.py`, exige migración de datos en ambos workspaces y elimina la separación que ADR-020 justifica.

**Where lives**: `core/cronograma.py` (motor), `orbit.py::_add_crono_subparsers` (helper CLI reusable), `orbit.py::cmd_crono` (dispatcher polimórfico que lee `action` o `crono_action`).

---

## ADR-027 — Ring desacoplado: ring.json + daemon EventKit + launchd
**Estado**: VIGENTE (desde v0.35)
**Contexto**: las alarmas de calendarios suscritos (`.ics` con `VALARM`) no son fiables — macOS muestra alarmas como banner sin sonido en suscripciones; iOS las ignora a veces; el refresh es ≥5 min. Reminders.app sí tiene notificaciones system-level fiables + iCloud sync gratis a iPhone/iPad. El path antiguo (`reminders_backend: "reminders"` en v0.29) acoplaba `sync_item` → AppleScript directamente, con todos los problemas crónicos de `osascript` (timeouts, error -10025, escape de strings, app abierta requerida).

**Decisión**: arquitectura **declarativa + daemon**.

1. **`agenda.md` sigue siendo la verdad**.
2. Orbit escribe un **`ring.json`** por workspace en `<workspace>/.reminders/ring.json` (gitignored) — proyección de la ventana rolling de items con `--ring` y hora.
3. Un **daemon standalone `orbit_ring_daemon.py`** consume uno o más `ring.json` y reconcilia idempotentemente las listas de Reminders.app vía **EventKit/PyObjC** (no AppleScript). El match se hace por `[orbit:<id>]` embebido en el body del reminder; items sin orbit-tag nunca se tocan (preserva manuales del usuario).
4. **Launchd plist** (`~/Library/LaunchAgents/com.orbit.ring-daemon.plist`) con `WatchPaths` sobre cada `ring.json` + `StartCalendarInterval` 00:05 dispara el daemon automáticamente sin proceso persistente.
5. **Triggers desde orbit**: `shell_start` y `commit_post` regeneran `ring.json` (vía acción `ring_refresh` del catálogo de hooks) y lanzan el daemon en background. Cubre el caso "edito agenda sin tocar ring.json directamente".

Config en `<workspace>/orbit.json`:
```json
"ring": { "enabled": true, "days": 7, "list": "🚀orbit-ws" }
```
Default `list` = nombre del workspace (`workspace_root.name`), de forma que cada workspace tiene su propia lista en Reminders.app (alineado con el modelo "una vida = una lista" preexistente). `enabled: false` vacía la lista sin tocar otras. `days` clamped a [1, 30].

EventKit elegido frente a AppleScript: misma fiabilidad de notificaciones (Reminders.app usa EventKit internamente), sin osascript timeouts, app abierta no requerida, API estructurada testeable.

**Consecuencias positivas**: alarmas fiables en Mac e iPhone (vía iCloud sync); decoupling total orbit ↔ Reminders.app; daemon idempotente — dispararlo 10 veces o 1 vez = mismo resultado; cualquier edit de `ring.json` (launchd, hook, manual) dispara el sweep.
**Consecuencias negativas**: dependencia nueva `pyobjc-framework-EventKit`; primera vez requiere autorizar TCC el binario de Python para Reminders (`System Settings → Privacy → Reminders`); doctor incluye un check que avisa cuando hay drift.

**Tradeoff considerado**: una lista única `Orbit Ring` para todos los workspaces (RING.md original, descartado en sesión 2026-05-14 a favor de una lista por workspace — coherente con el patrón existente y permite silenciar contextos completos en horarios específicos). AppleScript-write directo (rechazado — el camino dormante v0.29 ya falló por acoplamiento + osascript fragility).

**Where lives**: `core/ring_export.py` (build + write + CLI), `orbit_ring_daemon.py` (standalone EventKit), `core/hooks_catalog.json` (acción `ring_refresh`), `core/doctor.py::_check_ring_health`, tests en `tests/test_ring_export.py`.

---

## ADR-029 — Migración a `icalendar` (PyPI) para mecánica RFC 5545
**Estado**: VIGENTE (decisión 2026-05-15, Fase 3 sub-paso A del plan en `MODULES.md §5` / `ROADMAP.md §3`).

**Contexto**: tres ficheros (`core/ics.py`, `core/ics_share.py`, `core/email.py`) implementaban su propia mecánica RFC 5545: escape de TEXT, line folding a 75 octetos UTF-8 conscientes, parser DTSTART/DTEND, VALARM TRIGGER decoding, RRULE handling, unfolding de continuation lines. ~280 ℓ de helpers de bajo nivel (`_escape`, `_fold`, `_fmt_dt_local`, `_fmt_date`, `_now_stamp`, `_alarm_block`, `_unfold`, `_unescape`, `_split_prop_line`, `_parse_dt`, `_parse_ics_dt`). El bulk del código no era acreción — era mecánica reinventada que cualquier librería madura cubre con más correctitud (TZID handling, parámetros raros, edge cases de escape en parámetros).

**Decisión**: adoptar [`icalendar`](https://pypi.org/project/icalendar/) (PyPI, 7.x) como dependencia. Borrar los helpers RFC y delegar:
- *Render*: `Event()` + `Alarm()` + `Calendar()` + `to_ical()` reemplazan `render_vevent` + `_calendar_wrapper` + helpers de format.
- *Parse*: `Calendar.from_ical().walk("VEVENT")` reemplaza los parsers ad-hoc en los 3 ficheros.

Las funciones públicas (`render_vevent`, `_calendar_wrapper`, `_parse_vevents`, `parse_first_vevent`, `_parse_ics`) **mantienen su firma externa** para no propagar el cambio fuera del paquete. Los consumers en `orbit.py`, `core/render.py`, `core/doctor.py` no se enteran.

**Razón**:
- *Correctitud*: edge cases RFC 5545 (TZID, escape de TEXT en parámetros, line folding multibyte, RRULE serialization) cubiertos por una librería testada por terceros.
- *Mantenimiento*: ~280 ℓ menos de mecánica propia; cualquier bug futuro en parsing de invitaciones reales recae en upstream.
- *Recalibración honesta de ahorro*: estimación inicial en `ROADMAP.md` (500-800 ℓ) era optimista — los ficheros tienen mucha lógica orbit (buckets, snapshots, conflict resolution, kind detection) que NO migra. Ahorro real medido: **~110 ℓ netas** en core + ~50 ℓ de tests de implementación borrados. Vale la pena igualmente por la correctitud, no por la cifra.

**Lo que NO migra** (decisión deliberada):
- Expansión per-ocurrencia en lugar de emitir RRULE en los `.ics` que orbit publica — ver [ADR-009](#adr-009--recurrencia-expandida-localmente-no-rrule-en-ics).
- `_alarm_minutes` y `_item_uid` siguen siendo orbit-side: la mecánica de "ring → minutos" y la estabilidad de UIDs son contratos orbit, no RFC.
- Floating-local time en DTSTART (sin TZID, sin Z) — ver [ADR-011](#adr-011--ics-floating-local-time-sin-tzid). `icalendar` respeta `datetime` naive.

**Consecuencias**:
- Dependencia nueva: `icalendar` añadida a `DEPENDENCIES.md §3` (sube de 2 a 3 deps externas en core). `icalendar` tiene a su vez `python-dateutil` y `tzdata` como dependencias transitivas; con eso queda preparado el terreno para Fase 3.B (sustituir hand-rolled recurrence con `python-dateutil.rrule`).
- 1 byte-diff cosmético en el output: `VALARM TRIGGER` para 0-min alarmas emite `P0D` en lugar de `-PT0M` (RFC-equivalentes; Calendar.app / iOS Reminders los aceptan ambos por igual).
- Tests de implementación borrados (no comportamiento): 9 en `test_ics.py` + 4 en `test_ics_share.py` + 4 en `test_email.py` = 17 tests del helper RFC. Suite 1553 → 1536 sin regresiones de comportamiento.

**Tradeoff considerado**: mantener el código hand-rolled. Descartado: tres parsers RFC independientes en tres ficheros, cada uno con su propia idea de unfolding/escaping, era exactamente el tipo de deuda que el plan de simplificación busca acometer.

**Where lives**: cambios en commits `f63f7ac` (`core/ics.py`), `5223dbd` (`core/ics_share.py`), `40d4a93` (`core/email.py`).

---

## ADR-030 — Migración a `python-dateutil` para la mecánica de recurrencia
**Estado**: VIGENTE (decisión 2026-05-15, Fase 3 sub-paso B del plan en `MODULES.md §5` / `ROADMAP.md §3`).

**Contexto**: `core/agenda_cmds._next_occurrence` (58 ℓ) calculaba "siguiente ocurrencia" para 8 patrones de recurrencia (`daily`, `weekly`, `monthly`, `weekdays`, `every-N-{days,weeks,months}`, `first-X`, `last-X`) usando aritmética manual con `datetime.timedelta` + `calendar.monthrange`. El path delicado era `monthly` con clamp del 31 al último día del mes corto (31-Jan + 1 mes → 28-Feb), implementado a base de `min(base.day, monthrange(...)[1])`. Los `first-X` / `last-X` exigían un while-loop sobre los días del mes destino.

**Decisión**: adoptar [`python-dateutil`](https://pypi.org/project/python-dateutil/) como dependencia directa y reescribir `_next_occurrence`:
- `monthly` / `every-N-months` → `relativedelta(months=N)` (clamp natural automático).
- `weekdays` → `rrule(DAILY, byweekday=(MO,TU,WE,TH,FR))`.
- `first-X` / `last-X` → `rrule(MONTHLY, byweekday=X, bysetpos=±1)`.
- `daily` / `weekly` / `every-N-{days,weeks}` siguen con `timedelta` (ya eran one-liners).

La firma `_next_occurrence(due, recur, done_date) → str` se mantiene; los 6 callers externos (`ring.py`, `ring_export.py`, `agenda_view.py`, `ics_share.py`, `ics.py`) no se enteran.

**Razón**:
- *Correctitud*: el clamp de `monthly` y el manejo de `first-X`/`last-X` son lógica delicada que `relativedelta` y `rrule` cubren con semántica testada por una librería madura. La aritmética manual con `monthrange` funcionaba pero era frágil — cualquier edit accidental podía romper el clamp.
- *Coste cero de dependencia*: `python-dateutil` ya estaba en el árbol como transitiva obligatoria de `icalendar` (ADR-029). Promoverla a directa solo añade un `import` explícito en `DEPENDENCIES.md §3`; no aparece ningún paquete nuevo en `pip list`.
- *Coherencia con la dirección del plan*: 3.A ya delegó la mecánica RFC 5545 a una lib; 3.B delega la mecánica de recurrencia. Ambos pasos siguen el mismo principio.

**Lo que NO migra** (decisión deliberada):
- Constantes y gramática: `VALID_RECUR`, `_EVERY_RE`, `_POS_RE`, `_normalize_recur`, `is_valid_recur` — esa es **gramática orbit** (cómo el user escribe `🔄every-2-weeks` en `agenda.md`), no semántica calendar; queda donde está.
- Expansión en `core/ics.py::_expand_dates` — sigue usando `_next_occurrence` en un loop. Por [ADR-009](#adr-009--recurrencia-expandida-localmente-no-rrule-en-ics) orbit emite VEVENTs por-ocurrencia en lugar de RRULE en los `.ics`; ese contrato no cambia.

**Consecuencias**:
- Dependencia `python-dateutil` registrada como directa en `DEPENDENCIES.md §3` (3 deps externas en core: `markdown`, `pyobjc-framework-EventKit`, `icalendar`, `python-dateutil` — bueno, técnicamente 4, pero las 2 últimas comparten árbol de transitivas).
- Net: −13 ℓ en `core/agenda_cmds.py` (lejos de las 200-400 ℓ estimadas en el ROADMAP). El ROADMAP era optimista porque la mecánica de recurrencia estaba concentrada en una sola función pequeña; el resto del fichero es lógica orbit que no migra. Igual que en 3.A, la ganancia real es **correctitud y claridad**, no LOC.
- Tests sin cambios — los 12 casos de `TestNextOccurrence` (incluyendo el clamp 31-Jan → 28-Feb) pasan byte-idénticos. No fue necesario añadir ni borrar ningún test.

**Tradeoff considerado**: dejar la aritmética manual. Descartado: 58 ℓ de while-loops y `monthrange` para algo que la lib cubre con 3 ó 4 expresiones declarativas, y con coste real de dependencia = 0 (ya estaba transitivamente).

**Where lives**: refactor en commit `e130c38` (`core/agenda_cmds._next_occurrence`, `_WEEKDAY_NAMES` → `_WEEKDAY_RRULE`).

---

## ADR-031 — Partir `core/agenda_cmds.py` en subpaquete `core/agenda/`
**Estado**: VIGENTE (decisión 2026-05-15, Fase 3 sub-paso C del plan en `MODULES.md §5` / `ROADMAP.md §3`).

**Contexto**: `core/agenda_cmds.py` acumuló **2202 ℓ y 89 funciones top-level** mezclando gramática de recurrencia, line parsers/formatters, IO de `agenda.md`, helpers de selección interactiva, lifecycle CRUD (validate / ask / advance / ring hooks), 22 entry points públicos `run_*`, y el hook de startup. Era el fichero más grande del repo después de `orbit.py`, y la sección "Lifecycle helpers" (~620 ℓ) en particular era difícil de localizar sin abrir el fichero entero. **21 ficheros externos importan de él** (orbit.py, ring.py, ring_export.py, ics.py, ics_share.py, agenda_view.py, panel.py, doctor.py, email.py, archive.py, stats.py, inbox.py, reorganize.py, cronograma.py, project_view.py, shell.py + tests + scripts), así que la partición tiene que cuidar la compatibilidad de imports.

**Decisión**: partir en **6 módulos** bajo el subpaquete `core/agenda/`, agrupados por responsabilidad:

| Módulo | LOC | Contenido |
|---|---:|---|
| `recurrence.py` | 140 | Gramática + `_next_occurrence` + `_advance_to_today_or_future` |
| `io.py` | 405 | `_read_agenda`/`_write_agenda` + line parsers/formatters + validators |
| `display.py` | 212 | `_display_*` + `_select_*` + `event_*_urls` + `event_indicators` |
| `lifecycle.py` | 844 | `_TYPE_CONFIG` + generic CRUD + ring hooks + validate + ask helpers |
| `runners.py` | 567 | `run_task_*` (6) + `run_ms_*` (6) + `run_ev_*` (5) + `run_reminder_*` (5) |
| `startup.py` | 118 | `startup_advance_past_recurring` |

`core/agenda_cmds.py` queda como **shim de 28 ℓ** que inyecta cada símbolo del paquete (incluyendo `_underscore` privates) en su namespace vía `setattr(self, name, getattr(core.agenda, name))`. Esto preserva `from core.agenda_cmds import _read_agenda, _next_occurrence, ...` para los ~20 callers existentes sin pedirles que migren todavía.

**Razón**:
- *Localización*: cada bloque conceptual tiene un home; la gramática de recurrencia ya no vive entreverada con `_TYPE_CONFIG` ni con `_display_event`. Buscar dónde ajustar el VALARM ring → mira `lifecycle.py`, no escanea 2200 ℓ.
- *Sin riesgo de breakage*: el shim mantiene compat 100%. Las 21 importaciones externas siguen funcionando. La suite (1536 tests) pasa sin tocar ningún test.
- *Preparación para 4.B*: el seam `orbit/api.py` previsto en Fase 4.B se construirá sobre los runners. Tenerlos en su propio módulo (`runners.py`, 567 ℓ) hace ese paso directo.

**Lo que NO se hizo** (deliberado):
- *Migrar los 21 callers* para que importen de `core.agenda.<submódulo>` directamente. Sería un commit grande tocando muchos ficheros sin valor inmediato — el shim cubre el caso sin tocarlos. Migración incremental queda para cuando 4.B reescriba consumers.
- *Partir aún más fino* (un módulo por kind: `task.py`, `ms.py`, `ev.py`, `reminder.py`). Considerado y descartado por el usuario el 2026-05-15: 11 módulos pequeños con mucho cross-import era peor ratio coste/beneficio que 6 módulos con responsabilidad clara.
- *Borrar funciones intactas*: ninguna función desaparece. Esto es **reorganización**, no consolidación. El número absoluto de líneas sube ~170 ℓ por los docstrings de cada nuevo módulo y los imports por-fichero; eso es coste explícito asumido.

**Consecuencias**:
- Una pequeña limpieza colateral: `core/email.py` importaba `resolve_file` de `core.agenda_cmds` (re-export accidental de `core.log` que sobrevivía solo porque `agenda_cmds.py` tenía `from core.log import ... resolve_file` en sus imports). Corregido al import directo en `email.py`.
- Net del fichero shim: 2202 → 28 ℓ (−2174). El subpaquete suma 2378 ℓ. **Total +176 ℓ** — pero el problema que 3.C resolvía no era LOC, era el monolito.
- Suite sin cambios (1536 → 1536, sin regresiones).

**Tradeoff considerado**: dejar el monolito + añadir comentarios de sección. Descartado: los comentarios no resuelven el problema de localización ni preparan el seam para Fase 4.B.

**Where lives**: refactor en commit `1db9fba`. Subpaquete en `core/agenda/{recurrence,io,display,lifecycle,runners,startup}.py` + `__init__.py`. Shim en `core/agenda_cmds.py`.

---

## ADR-032 — Seam `core.api` + split parcial de `_build_parser`
**Estado**: VIGENTE (decisión 2026-05-15, Fase 4 sub-paso B del plan en `MODULES.md §5` / `ROADMAP.md §4`).

**Contexto**: el ROADMAP §4.B prometía dos cosas en un sub-paso: (a) un seam estable `orbit/api.py` con funciones puras consumibles por hooks/scripts externos, y (b) reducir `orbit.py` de 2200 a ~800 ℓ partiendo `_build_parser`. Tras 3.C los runners de `core.agenda` ya cumplían un rol de seam parcial, así que la decisión de qué shape darle al API y cuánto del CLI dispatcher tocar era abierta. La estimación 2200→800 era además optimista (lección registrada en `feedback_orbit_refactor_lessons` tras Fase 3).

**Decisión**: tres elementos concretos:

1. **`core/api.py` con shape pura, no fachada de nombres** (4 add + 2 complete + 4 drop). Cada función:
   * Valida sus argumentos. Errores → `raise ValueError` (no exit codes).
   * Ejecuta la lógica de datos (read agenda → mutar → write agenda).
   * Devuelve el item dict (o tupla `(item, next_or_None)` para complete/drop con recurrencia).
   * **No imprime, no agenda ring scheduling, no toca Google sync**. Esos son CLI concerns que viven en los wrappers de `core.agenda.lifecycle` y `core.agenda.runners`.

2. **Path = `core/api.py`, no `orbit/api.py`** como sugería el ROADMAP. `orbit.py` es un script, no un paquete; todo lo importable en el repo vive bajo `core/`. Mantener convención.

3. **Split parcial de `_build_parser`** en `core/parsers/` con tres ficheros: `_helpers.py` (la clase `_OrbitParser` + 8 `_add_*_args`), `agenda.py` (los 4 verbos task/ms/ev/reminder), y el resto en `__init__.py`/orbit.py. orbit.py baja 2303 → 2072 ℓ.

**Razón**:
- *Pure shape over fachada*: el usuario explícitamente eligió "API verdaderamente pura" sobre la opción más conservadora (aliasing de runners). La motivación: scripts externos pueden invocar `core.api.add_task("proj", "do X")` sin captar prints ni mockear stdout.
- *Errores como excepciones*: las funciones puras son testables sin parsear stdout. El runner CLI las captura con `try/except` y traduce a wording legacy vía `_translate_api_error`.
- *Scope incompleto deliberado*: `edit_*` y `log_*` quedan fuera del API. El primero arrastra la maquinaria de occurrence-vs-series con preservación de structured notes (📋 / 🚪); el segundo es trivial (`core.log.add_entry`). Ninguno entra en el 80/20 de "qué pide un script externo".
- *Split parcial sobre split total*: extraer solo el bloque agenda + helpers da el grueso del valor de reorganización. Cada uno de los ~30 bloques restantes en `_build_parser` añade ~10 ℓ de boilerplate al subpaquete por cada ~15 ℓ que saca de orbit.py — ratio decreciente. La estimación 2200→800 era optimista.

**Lo que NO se hizo** (deuda explícita):
- `core.api.edit_*` / `core.api.log_*`. Si emerge un consumer externo claro, se añaden en C2-bis.
- Refactor de `_generic_drop` para usar `core.api.drop_*`. La lógica CLI (interactive confirmation, advance-in-place de reminder, ring cleanup, logbook entry) está demasiado entrelazada para separar sin triplicar el diff. La API existe y funciona; el flow CLI sigue usando el código legacy.
- Resto del split de `_build_parser` (~30 subparsers / ~470 ℓ). Futuro C4-bis.

**Consecuencias**:
- 5 commits en Fase 4.B: `6e3b464` (api.add_*), `2ad4c73` (api.complete_*/drop_*), `3ccf3e8` (ics share/import via argv rewrite — cierra deuda 4.A), `af7397f` (split parcial de `_build_parser`), `<este>` (docs).
- Net del repo: `core/api.py` +405 ℓ + `core/parsers/` +300 ℓ + orbit.py −231 ℓ + lifecycle/runners deltas. **~+500 ℓ totales** sobre el repo. La ganancia real es **API contractual estable** + **localización del argparse**, no reducción de LOC.
- Suite sin cambios (1536 → 1536, ninguna regresión).
- Deuda 4.A resuelta: `orbit ics share` / `orbit ics import` aceptados vía argv rewrite en `_fix_argv` (no via argparse subparsers — argparse no combina positional + flags + add_subparsers; el rewrite es coherente con el patrón `add task → task add` ya existente).

**Tradeoff considerado**: opción A (fachada de nombres) habría sido coste mínimo pero entregaría una "API" que es solo `add_task = run_task_add`. El user eligió shape diferente — más trabajo, más valor real para scripts externos.

**Where lives**: `core/api.py`, `core/parsers/{_helpers,agenda}.py`, `orbit.py::_fix_argv` (argv rewrite), `core/agenda/lifecycle.py::_generic_add` (CLI wrapper sobre el API).

---

## Lo que se ha descartado explícitamente

Lista breve de propuestas consideradas y rechazadas, para que no vuelvan a discutirse sin contexto:

- **Multi-user / colaborativo** — cambia todo (permisos, identidad, conflict resolution). No es el valor.
- **UI web o desktop app** — el terminal + markdown ES el valor.
- **Base de datos (SQLite, etc.)** — agenda.md / logbook.md ES la database.
- **Plugin system** — prematuro. Cuando llegue un caso real, se rediseña.
- **`cloud_url` en descripción de eventos de Calendar.app** — descartado 2026-05-11 (memoria `project_cloud_url_in_calendar`).
- **Reverse sync Calendar.app → orbit (`gpull`)** — descartado v0.28; código dormante en `core/gimport.py` (borrado en v0.33).
- **`.ics` como verdad** — descartado v0.32; ver ADR-010.
- **Más backends de sync** (Office365 nativo, CalDAV) — `.ics` ya los cubre. Cada backend nuevo es deuda.

---

## Cómo añadir una decisión nueva

1. Asignar siguiente ADR-NNN.
2. Estructura: **Estado** + **Contexto** + **Decisión** + **Consecuencias** + (opcional) **Tradeoff considerado**.
3. Si reemplaza una decisión previa: marcar la anterior como **DEROGADA** y enlazar.
4. Mencionar el ADR cuando la decisión se invoca en código (`# see ADR-018`).

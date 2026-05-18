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
**Consecuencias**: reorganizar requiere `orbit organize` o `task edit`/`ev edit`; no se puede tocar Calendar.app esperando que llegue a orbit.

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
**Estado**: VIGENTE — refinado por [ADR-036](#adr-036--wrap-de-refresh-tras-mutación-cli-matriz-por-comando-sin-render).
**Decisión**: tras cualquier `task add`, `ev edit`, `ms done`, `email <proj>`, `ics-import`, etc., orbit dispara en background un wrap que regenera secretary + ring + ics (con filtro por proyecto cuando aplica). Render a HTML se reserva para `save` (commit_post). Detalle de la matriz por comando y diseño del wrap en ADR-036.

**Trigger central**: `orbit.py:_DASH_TRIGGERS` + `_CITA_TRIGGERS`.
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

## ADR-033 — Separación `core/` (writers) vs `views/` (readers)
**Estado**: VIGENTE (decisión 2026-05-16, refactor en 4 commits independientes).

**Contexto**: tras los refactors previos (satellites/, link/import, doctor 3-way) `core/` acumulaba 42 módulos mezclando dos roles muy distintos: los **writers de la verdad** (mutan `agenda.md`, `*-project.md`, `log`, `notes`, `inbox`, `registry`, `orbit.json`) y los **readers que producen artefactos derivados** (consumen la verdad y emiten HTML, `.ics`, `ring.json`, reports de doctor). El usuario lo expresó como dificultad para "seguir la lógica de inferencia": al abrir `core/` no era posible distinguir de un vistazo qué módulos pueden mutar el estado y cuáles sólo lo leen.

La alternativa considerada — mantener todo en `core/` y documentar el rol en MODULES.md — se descartó porque la documentación deriva del árbol, no al revés: si la estructura lo hace explícito, no hace falta acordarse de leer una tabla.

**Decisión**: extraer cuatro readers a un paquete hermano `views/`, con un subpaquete por extensión:

```
views/
  render/render.py + orbit.css   (era core/render.py)
  doctor/doctor.py               (era core/doctor.py)
  cal/ics.py + cal/share.py      (era core/{ics,ics_share}.py)
  ring/export.py + ring/parse.py (era core/{ring_export,ring}.py)
```

Regla unidireccional: **`core/` no importa de `views/` en top-level**. Los imports lazy (dentro de cuerpos de función) son aceptables para hook actions, wrappers cloud, checks pre-commit, scheduling legacy y el seam API. La regla queda escrita en [RULES.md](RULES.md).

Los **tipos compartidos** entre los dos lados (e.g. la dataclass `Issue` usada por `views.doctor` y `core.cronograma`) viven en `core/types.py`, no en `views/`, para evitar aristas conceptuales.

**Razón**:
- *Esquema mental*: al abrir el repo, `core/` es ahora "writers + infra" y `views/` es "readers que proyectan a artefacto". El árbol responde a la pregunta de un vistazo.
- *Paralelismo con satellites/*: mismo patrón estructural (subpaquete por unidad funcional). El proyecto ya tiene dos hermanos a `core/` (`satellites/` desde 2026-05-15, `views/` desde 2026-05-16) con reglas de acoplamiento explícitas.
- *Lazy aceptable*: la prohibición pura "core no importa views jamás" obligaría a hookificar los pocos sites legítimos sin valor real. Aceptar el lazy es pragmático y suficiente para que el árbol cuente la historia.

**Lo que NO se hizo** (deuda explícita):
- *Mover viewers de shell* (`panel`, `agenda_view`, `project_view`, `stats`, `search`, `list_entries`, `ls`) a `views/`. Producen salida al shell, no artefacto en cloud; quedan en `core/`.
- *Hookificar los 8-10 sites lazy `core → views`*. Cada uno tiene una razón legítima (orquestación, no eventos asíncronos). La regla acepta el lazy.
- *Colapsar `views/render/render.py` y `views/doctor/doctor.py` a planos `views/render.py` y `views/doctor.py`*. Hoy el subpaquete es innecesario (1 .py dentro); el plan es que `doctor` se parta en sub-doctores (log/agenda/ficheros/sistema) y entonces el subpaquete se justifica.
- *Satélite del render*. Considerado y descartado en la auditoría: render lee mucha estructura del workspace y no es un daemon — encaja como reader, no como satélite.

**Consecuencias**:
- 4 commits atómicos: `ec6a624` (render F1), `ce48e72` (doctor F2 + Issue → core/types.py), `55c5ec2` (cal F3), `e81b103` (ring F4).
- Suite invariante: 1541 passed, 1 skipped en cada fase.
- Net del repo: 0 líneas borradas o añadidas (sólo `git mv` + renombre de imports). La ganancia es de claridad, no de capacidad.
- Hook catalog: 2 acciones renombran su `"module"`: `ics_emit_workspace` (a `views.render.render`) y `ring_refresh` (a `views.ring.export`).

**Tradeoff considerado**: la división writers/readers no es única — también cabría "puro vs side-effect", o "interno vs API". Se eligió writers/readers porque captura la intuición del usuario ("la verdad" vs "lo que se deriva de ella") y se mapea a un test sencillo: ¿este módulo cambia `.md`/`.json` del workspace? Si sí → core. Si no, y sólo emite → views.

**Where lives**: `views/{render,doctor,cal,ring}/`, `core/types.py`, [RULES.md](RULES.md), `core/hooks_catalog.json`. Memoria viva en `project_orbit_views` (snapshot 2026-05-16).

---

## ADR-034 — `save` como verbo de cierre + chain commit_post unificado
**Estado**: VIGENTE (decisión 2026-05-16, 4 commits: `e162257`, `7f49ef2`, `01b09a6`, `f0c6af8`).

**Contexto**: el comando `orbit commit` arrastraba significado git ("git commit con extras") que ya no capturaba lo que la operación hace: validar (doctor) + versionar (git commit) + proyectar (cloud HTML + .ics + Reminders.app). El nombre engañaba y, a la vez, el flujo interno escondía la mitad de las cosas: doctor estaba inline en `run_commit`, render era side-effect de `cloudsync_push_background`, ICS estaba tres niveles bajo el commit_post chain (vía `after_render`). El chain visible en `hooks_catalog.json` no contaba la historia real de lo que pasa al cerrar el trabajo.

**Decisión**: dos cosas combinadas.

1. **Rename público a `save`**:
   - `orbit save` es el verbo canónico; `orbit commit` queda como alias legacy (patrón ya usado en `link/track`, `import/deliver`).
   - Strings UI ("Mensaje del save", "Confirmar save?", "Save realizado", "sin save"), shell COMMANDS, docs (CHULETA/TUTORIAL/README/HOOKSYSTEM) actualizados.
   - **Internos intactos**: `run_commit`, `cmd_commit`, hook chains `commit_pre/post/offer`, `_git_commit()` se mantienen — el blame/log de git histórico habla de "commit", y el git real sigue siendo git commit.

2. **Limpieza del chain en 3 sub-fases (A, B, C)**:
   - **A** — Doctor declarativo: `_action_doctor_check_save` en `views/doctor/doctor.py`, crítica en `commit_pre.pre`. El usuario rechaza interactivamente → action devuelve `ok=False` + critical=True → `_chain_aborted` aborta el save. En no-tty: warning + continúa. Borrado del bloque inline en `run_commit` (~25 ℓ).
   - **B** — Render como post-action propia: `cloudsync_push_background` → `render_changed_background` (módulo `views.render.render`). Las funciones `sync_to_*` salen de `core/cloudsync.py` y pasan a `views/render/render.py` con nombre claro (`render_changed_to_cloud*`, `render_all_to_cloud`). `cloudsync.py` queda con sólo los status helpers (`_write/_read_sync_status`, `startup_cloud_check`, `check_cloud_sync`).
   - **C** — ICS a `commit_post` directo: `ics_emit_workspace` sube de `after_render` (chain eliminado) a `commit_post.post`. `render_changed`/`render_all` ya no disparan ningún chain. `_action_ics_emit_workspace` resuelve `cloud_root` por sí mismo si no viene en ctx. **Cambio observable**: `orbit render` manual ya no regenera los `.ics`; usar `orbit ics --workspace` aparte.

Estado final del chain:
```
fire("commit_pre"):  cloud_imgs_process · cronograma_log_completed · doctor_check_save (CRITICAL)
[git commit]
fire("commit_post"): render_changed_background · ics_emit_workspace · ring_refresh
```

**Razón**:
- *Save captura mejor "guardar el estado"*. La metáfora editorial (Ctrl+S) es universal; "commit" arrastra jerga git que no captura el workflow.
- *Cada acción visible y skippeable*. `orbit save --help` expone `--no-doctor-check-save`, `--no-render-changed-background`, etc. — gratis vía `add_chain_flags`. Antes, las acciones sepultadas no se podían saltar.
- *El catálogo cuenta la historia*. Quien lee `hooks_catalog.json` ve las 3 pre + 3 post sin tener que escarbar en `run_commit` ni en `cloudsync.py` para descubrir qué pasa de verdad.
- *Internos vs UX separados*. Renombrar sólo la cara visible (fase F1 público) deja el `git log/blame` legible — los commits históricos hablan de "commit" porque hablaban de git commit; la fase F2 (rename interno) queda opcional para más adelante.

**Lo que NO se hizo** (deuda explícita):
- F2 interno: `run_commit→run_save`, `cmd_commit→cmd_save`, chains `commit_pre/post/offer→save_pre/post/offer`. Coste alto (bindings legacy en hooks_catalog para no romper `orbit.json` del usuario), valor bajo (sólo cosmético en código). Aplazado sin compromiso.
- Mover `cloudsync.py` entero a `views/render/`: el módulo se quedó con utilidades de status + check. Aceptable.

**Consecuencias**:
- Cambio menor de exit code: cancelar save por rechazo del doctor devolvía exit 0 (no-error); ahora exit 1 (chain abortado). Coherente con "el usuario abortó a propósito".
- Mensaje cambia: `Sincronización al cloud en background` → `Render al cloud en background`.
- `orbit render` manual emite un mensaje informativo ("`.ics` no regenerados — `orbit ics --workspace` si los necesitas").

**Tradeoff considerado**: la opción C ("dejar `after_render` chain con ICS, sólo añadir a commit_post") fue descartada por **doble ejecución** — la action correría dos veces tras un save (una desde el subprocess de render, otra desde el shell principal). Eliminar `after_render` es lo correcto.

**Where lives**: `core/hooks_catalog.json` (`commit_pre.pre` + `commit_post.post`), `core/commit.py::run_commit`, `views/doctor/doctor.py::_action_doctor_check_save`, `views/render/render.py::{render_changed_to_cloud*, _action_render_changed_background, _action_ics_emit_workspace}`, `orbit.py::cmd_commit` (alias `save`/`commit`). Memoria viva en `project_orbit_save` (si se crea) y notas en `project_orbit_next_session`.

---

## ADR-035 — `views/secretary/` como viewers del workspace + dashboard cloud unificado
**Estado**: VIGENTE (decisión 2026-05-16, 7 commits: `ad2e30f`, `5e79069`, `c7400e2`, `7a21dde`, `a826313`, `44b60e3`, `9e63d8d`).

**Contexto**: tras introducir [ADR-033](#adr-033--separación-core-writers-vs-views-readers), `views/` ya tenía render, doctor, cal y ring. Faltaba un sitio coherente para los viewers que regeneran el dashboard del workspace (panel del día, agenda próxima, calendar, lista de proyectos): vivían inline en `orbit.py::run_dash`, mezclados con la orquestación, y emitían sus `.md` a la raíz del workspace con el nombre `agenda.md` — chocando con `{proj}-agenda.md` (la verdad escrita por el usuario en Obsidian). Y a la vez, `render.py` generaba en cloud **otro** dashboard ad-hoc (`index.html`, `proyectos.html`, `agenda.html`) con lógica paralela al que vivía localmente.

**Decisión**: introducir el concepto **secretary** como tercera familia (junto a `cartero` y `ring-daemon`), con dos cosas combinadas.

1. **`views/secretary/` con viewers puros** (regla "secretary = viewer puro"; sin orquestación, sin daemons, sin side-effects fuera del path de salida):
   - `panel.py`, `agenda_next.py`, `calendar.py`, `projects.py`, cada uno con `generate(out_path)`.
   - Outputs en `📋secretary/{panel,agenda-next,calendar,projects}.md` dentro del workspace. Rename `agenda.md → agenda-next.md` para resolver la colisión nominal con `{proj}-agenda.md`.
   - `projects.py` (nuevo): tabla markdown por tipo con Proyecto · Prio · Estado · Descripción (extraída de `## Estado actual` del project.md) · Secciones.
   - `run_dash` re-cableado: orquesta los 4 viewers, sin lógica inline.

2. **Front-page del workspace**: `workspace.md` estático en la raíz del workspace, escrito por el usuario (descripción libre) con links al dashboard. Análogo a `{proj}-project.md` por proyecto. Lo bootstrappea `bootstrap_workspace_md()` desde `orbit setup` con un template básico; no sobreescribe si ya existe.

3. **Dashboard cloud unificado (fase E2)**: render lee de secretary como fuente única.
   - `workspace.md` → `cloud_root/workspace.html` (front-page real del cloud).
   - `cloud_root/index.html` (escrito automáticamente): stub con `<meta http-equiv="refresh">` apuntando a `workspace.html` — los navegadores abren `index.html` por convención al entrar a un folder; el redirect lleva al contenido real. Permite que el nombre del fichero refleje su semántica (`workspace.md` ↔ `workspace.html`) sin perder el auto-open del browser.
   - `📋secretary/*.md` → `cloud_root/📋secretary/*.html`.
   - **Eliminadas** `render_index`, `render_proyectos`, `render_agenda` y `_render_dashboard` (~230 ℓ borradas) — su lógica vivía duplicada en secretary; cloud y local comparten ahora la misma fuente, sólo cambia el formato.

**Razón**:
- *Una sola fuente de verdad-derivada*. Antes la lista de proyectos vivía dos veces (`render_proyectos` para cloud y `secretary/projects` para local) con lógica paralela. Tras E2, vive una vez en `secretary/projects.py`; el cloud sólo proyecta a HTML.
- *Resolución de la colisión `agenda.md`*. El derivado del workspace y la verdad de proyecto compartían nombre — fuente real de confusión. `agenda-next.md` (en `📋secretary/`) las distingue.
- *workspace.md como front-page de autor*. Análogo al `{proj}-project.md`: descripción + links. Editable por el usuario, no sobrescrito por bootstrap; render lo proyecta a `workspace.html` del cloud (con `index.html` como stub redirect para que el browser auto-abra).
- *Coherencia con la metáfora oficinista*. cartero + ring-daemon + secretary cubren los tres roles auxiliares (mensajería + alarmas + dashboard).

**Lo que NO se hizo** (deuda o decisiones aplazadas):
- *Daemon background que regenere secretary periódicamente*. Hoy `dash_background_loop_start` está vivo pero sin actualizar al nuevo modelo — decisión pendiente (incondicional cada hora vs sólo si hay cambios; ver próxima sesión).
- *Más viewers en secretary* (agenda-today, today-log, start-projects, log-summary). El usuario los esbozó como dirección futura; por ahora `panel.md` consolida los tres primeros. Dividir cuando el uso lo pida.
- *Secretary no orquesta ni lanza otros satélites*. Regla acordada; aplazada la discusión sobre si secretary "lanza" cartero/ring (probablemente no — rompería el concepto de viewer puro).
- *Borrado de `panel.md`/`agenda.md`/`calendar.md` legacy en raíz*: se hizo manualmente tras E2 (no automático en código). Coherente con "no migración automática del histórico".

**Consecuencias**:
- Cambio observable: `orbit render` manual ya no regenera `.ics`; el dashboard del cloud ahora vive en `📋secretary/*.html` con `workspace.html` viniendo de `workspace.md` (+ `index.html` como stub redirect, 2026-05-16 PM).
- Acción manual ejecutada al cierre: `bootstrap_workspace_md()` invocado one-shot en orbit-ws y orbit-ps; `git rm` de los .md viejos en orbit-ws (staged para el próximo save).
- −197 ℓ netas en `render.py` por la unificación E2.

**Tradeoff considerado**:
- *E1 (mantener ambos paralelos)*: cloud generaría `index.html`/`proyectos.html`/`agenda.html` ad-hoc + también `📋secretary/*.html`. Duplicación sin valor. Rechazado.
- *E3 (no llevar secretary a cloud)*: workspace.md y secretary/*.md sólo en local. Rompe la metáfora del front-page (`workspace.md` invisible para el móvil). Rechazado.

**Where lives**: `views/secretary/{panel,agenda_next,calendar,projects}.py`, `core/setup.py::bootstrap_workspace_md`, `views/render/render.py::render_workspace_dashboard`, `orbit.py::run_dash` (orquestador), `orbit.py::SECRETARY_DIR` (constante). Memoria viva en `project_orbit_secretary` (snapshot 2026-05-16).

---

## ADR-036 — Wrap de refresh tras mutación CLI: matriz por comando, sin render
**Estado**: VIGENTE (decisión 2026-05-16, refina [ADR-017](#adr-017--auto-magia-tras-mutaciones-cli)).

**Contexto**: tras [ADR-035](#adr-035--viewssecretary-como-viewers-del-workspace--dashboard-cloud-unificado), `run_dash` quedó atómico (5 viewers, sin .ics ni render dentro). El wrap que disparaba `run_dash` en bg tras mutaciones CLI (`_DASH_TRIGGERS` en `orbit.py`) tenía dos problemas:
1. **Bug latente**: pasaba `args=(True, hint)` a `run_dash(silent)` → TypeError silencioso en el thread daemon. El refresh post-mutación llevaba meses sin funcionar; pasaba desapercibido porque el chain `commit_post` (save) hacía el trabajo completo.
2. **Cobertura incompleta**: aunque funcionara, solo refrescaba dash. Tras `task add` con `--time --ring`, Calendar.app y Reminders.app quedaban stale hasta el siguiente save.

Además, tras añadir el viewer `report_summary` (que lee logbook + highlights), `log` y `hl` necesitaban disparar refresh — antes no estaban en `_DASH_TRIGGERS`.

**Decisión**: el wrap post-mutación se estructura en una matriz por tipo de comando, sin render. Render es caro (HTML + KaTeX + Mermaid para todos los .md tocados) y solo se justifica en el momento de cierre (`save`).

| Trigger | Mutaciones | Acciones en bg |
|---|---|---|
| `_CITA_TRIGGERS` | `task`, `ms`, `ev`, `reminder`/`rem`, `crono`, `ics-import`, `email` | dash (coalescido) + `ring.refresh_all()` + `ics.write_workspace(project_filter=<proj>)` |
| `_DASH_TRIGGERS \ _CITA_TRIGGERS` | `log`, `hl`, `project` | dash (coalescido) |

**Por qué `project_filter` solo en ics**:
- `ics.write_workspace` genera **un .ics por proyecto** además de los buckets workspace-level. Con filtro, evita reescribir N-1 .ics inalterados. Ahorro real de escritura.
- `secretary` y `ring` producen artefactos workspace-agregados (1 fichero por viewer / 1 `ring.json`). El filtro no ahorraría nada: hay que reescanear todos los proyectos para reconstruir el agregado. Caché de `project_data` entre runs se aplazó como deuda — añadirlo cuando el coste duela en uso real, no preventivamente.

**Coalescencia**:
- `dash` coalesce por `.dash-stamp` con ventana `_DASH_COALESCE_SECONDS = 10`. Bursts (p.ej. varios `log` seguidos) colapsan en un refresh.
- `ics` y `ring` corren cada vez (más baratos individualmente, idempotentes en sus consumidores: bucket .ics se reescribe igual, daemon EventKit upsertea idempotente). Si aparece thrash observable, evaluar payload-diff en `ring.refresh` para no tocar mtime → no spawnea daemon (opción B discutida); no implementado hoy.

**Fail-isolation**: cada paso del wrap (`_run_full_refresh_coalesced`) try/except independiente. Un fallo en dash no impide ring; un fallo en ring no impide ics. Excepciones absorbidas silenciosamente — el thread es daemon y un print interferiría con la prompt del usuario. Estrategia futura si los fallos silenciosos molestan: notification queue + flush al siguiente prompt.

**Por qué render queda fuera del wrap**:
- Coste: render escribe HTML por cada .md del workspace (~docenas o más). KaTeX + Mermaid amplifican.
- Valor marginal del cloud mid-session: el HTML en cloud sirve para consulta móvil — no necesita refresh instantáneo tras cada `task add` local.
- Acoplamiento con commit: render lógicamente cierra la cadena "guardar trabajo + publicar"; es coherente que viva en `commit_post`.
- Aceptable si más adelante se quiere "publish on demand" → `orbit render` manual ya existe.

**Trade-offs considerados**:
- *Render también en wrap*: rechazado por coste/valor (justificado arriba).
- *Caché de `project_data` para optimizar secretary con filtro*: rechazado por complejidad (cache invalidation) sin evidencia de coste. Reabrir si los logbooks crecen.
- *Generar un `report-summary-<proj>.md` por proyecto*: rechazado — añade ficheros sin caso de uso claro hoy.
- *Stamps separados ics-stamp / ring-stamp*: rechazado — sin evidencia de thrash; añadir si aparece.
- *Doctor en el wrap (cita / log / hl / project)*: rechazado. El caso de "fichero externo missing" ya lo captura el writer (`core/tracked.py::track` lanza `FileNotFoundError`; `hl add --track` y `note --from/--track` lo gestionan con `print + return 1`). El caso de "drift posterior" (target movido/borrado fuera de orbit) no es una mutación CLI → el wrap no se dispararía aunque corriera doctor; está cubierto por `commit_pre` (bloquea `save`) y `shell_start` (prompt interactivo). Además doctor escanea todos los proyectos (caro) y prints async desde un daemon thread interferirían con la prompt. Reabrir si aparece un caso real no cubierto por las dos redes existentes.

**Where lives**: `orbit.py::_run_full_refresh_coalesced`, `orbit.py::_run_dash_coalesced`, `orbit.py::_CITA_TRIGGERS` ⊂ `_DASH_TRIGGERS`, dispatch en `run_command`. Tests en `tests/test_dash_coalesce.py`. Commits relevantes: `397fe1a` (fix + dash debounce + log/hl/project), el commit que añade el full-refresh wrap.

---

## ADR-037 — Watchdog: doctor + full-refresh periódico tras edición externa
**Estado**: VIGENTE (decisión 2026-05-16 PM, extiende [ADR-036](#adr-036--wrap-de-refresh-tras-mutación-cli-matriz-por-comando-sin-render)).

**Contexto**: el wrap de [ADR-036](#adr-036--wrap-de-refresh-tras-mutación-cli-matriz-por-comando-sin-render) solo se dispara tras mutaciones CLI. Pero el usuario edita habitualmente `agenda.md`, `logbook.md` y `highlights.md` directamente en Obsidian o un editor externo. Esos cambios no pasan por ningún comando orbit → ningún derivado se entera (dash, ics, ring quedan stale hasta el siguiente save o shell start). El hourly background loop preexistente (`_dash_background_loop`) sólo regeneraba dash; era además vulnerable a propagar drift (si la edición externa rompía la sintaxis, panel/agenda-next/ics emitían basura silenciosa).

**Decisión**: rebautizar el daemon background como **watchdog** y darle dos responsabilidades nuevas:

1. **Doctor pre-check**. Cada tick empieza por `check_all_projects()`. Si hay issues, **no regenera derivados** (los derivados se congelan en su última versión limpia) y escribe un marker `.doctor-pending` (timestamp + count). El REPL prompt lo surface al siguiente input — una sola vez por sesión — con un aviso de una línea: `🏥 Doctor (HH:MM): N problemas detectados — ejecuta doctor`.

2. **Full refresh**, no sólo dash. Cuando el tick corre limpio, llama a `orbit._run_full_refresh_coalesced()` (mismo helper que [ADR-036](#adr-036--wrap-de-refresh-tras-mutación-cli-matriz-por-comando-sin-render): dash + ring + ics). Render sigue reservado para `save`.

3. **Configurable**. `<workspace>/orbit.json → "watchdog": {"enabled": true, "interval_minutes": 60}` (clamp `[5, 1440]`). `enabled=false` → el thread retorna inmediatamente.

**Ciclo de vida del `.doctor-pending`**:
- Escrito por watchdog tick cuando detecta issues.
- Surface en el REPL: una vez por sesión (flag en memoria), no borra el fichero.
- Borrado por watchdog tick cuando corre limpio (auto-clear cuando el usuario arregla y el siguiente tick lo confirma).

**Razón**:
- *Catch-early*. La edición externa es justo el punto donde más probable es introducir drift sintáctico; ahí tiene más valor un check.
- *No propagar basura*. Si `agenda.md` tiene una línea rota, panel/ics/ring quedan en su versión limpia anterior — mejor que reflejar el error en los derivados sin avisar.
- *UX limpia*. Daemon thread no imprime a stdout (intercala con prompt); en su lugar deja un marker y el REPL lo surface al input — sin interrumpir typing.
- *Surfacing una vez por sesión*. Evita spam si el usuario tarda en arreglar; el siguiente shell start vuelve a verlo (el `_action_doctor_startup` síncrono ya lo cubre).
- *Configurable*. Permite desactivar (sesiones largas sin edición externa) o ajustar el periodo (5 min para flujos intensivos, 1440 para "una vez al día").

**Coherencia con [ADR-036](#adr-036--wrap-de-refresh-tras-mutación-cli-matriz-por-comando-sin-render)**:
- Wrap CLI y watchdog comparten el mismo helper `_run_full_refresh_coalesced` → un solo punto de mantenimiento del orden dash → ring → ics.
- Ambos respetan la regla "render solo en save".
- El stamp `.dash-stamp` coalesce los dos caminos: si el wrap CLI acaba de correr, el watchdog skipea (vía coalescencia interna de `_run_dash_coalesced`).

**Trade-offs considerados**:
- *Print directo a stderr desde el daemon*: rechazado por UX (intercala con prompt).
- *Notificación macOS (osascript)*: rechazado por dependencia de OS-specific tooling y porque el aviso pre-prompt cubre el caso bien.
- *Eliminar el watchdog* (la nota previa en memoria lo cuestionaba): rechazado tras este upgrade — ahora cubre un caso real (edición externa) que ni shell_start ni day_open ni save cubren entre eventos.

**Where lives**: `core/shell.py::_load_watchdog_config`, `_watchdog_tick`, `_watchdog_loop`, `_maybe_show_doctor_pending`, `_DOCTOR_PENDING`. Spawn desde `_action_daemons_startup` (chain `shell_start`). Tests en `tests/test_watchdog.py` (18 tests).

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

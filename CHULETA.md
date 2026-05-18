# Orbit — Chuleta de comandos

## Shell interactivo

```bash
orbit              # entra al shell (sin prefijo orbit en cada comando)
orbit shell        # equivalente explícito
orbit claude       # abre Claude Code en el directorio Orbit
```

Al entrar: `¡Hola! ¡Bienvenido!` + startup (doctor, untracked, save+push, gsync)
Al salir: `exit`/`quit` (directo) o `end` (ofrece save+push antes de salir)

---

## project — gestión de proyectos

```bash
orbit project create   <name> --type TIPO [--priority alta|media|baja]
orbit project status   <name> [--set STATUS]
orbit project priority <name> alta|media|baja
orbit project edit     <name> [--editor E]
orbit project drop     <name> [--force]
orbit project type                          # lista tipos configurados
orbit project type add <name> <emoji>       # añade tipo
orbit project type drop <name>              # elimina tipo
```

- `create` genera la estructura completa: `project.md`, `logbook.md`, `highlights.md`, `agenda.md`, `notes/`
- `drop` pide confirmación interactiva (defecto **No**); `--force` la omite
- tipos configurables en `orbit.json` (ver `project type`)

---

## task — tareas

```bash
orbit task add    <project> "<text>" [--date DATE] [--time HH:MM] [--recur FREQ] [--until DATE] [--ring WHEN] [--desc DESC]
orbit task done   [<project>] ["<text>"]
orbit task drop   [<project>] ["<text>"] [--force] [-o] [-s]
orbit task log    [<project>] ["<text>"]
orbit task edit   [<project>] ["<text>"] [--text "<new>"] [--date DATE|none] [--time HH:MM|none] [--recur FREQ|none] [--until DATE|none] [--ring WHEN|none] [--desc DESC|none]
```

- `done` y `drop`: interactivos si no se especifica texto; `drop` pide confirmación
- Si el texto coincide con varias citas, se muestra una lista numerada para elegir (aplica a task, ms, ev y reminder)
- `done` en tarea recurrente: avanza a la siguiente ocurrencia automáticamente
- `drop` en tarea recurrente: pregunta si quitar solo esta ocurrencia o toda la serie; `-o` avanza al próximo, `-s` elimina la serie (sin prompt); `--force` avanza al próximo (seguro por defecto)
- `log`: crea una entrada en el logbook del proyecto a partir de una cita (task→#apunte, ms→#resultado, ev→#evento)
- `--open`: escribe el resultado en `cmd.md` y lo abre en el editor

### Recurrencia (`--recur`)

| Valor | Significado |
|-------|------------|
| `daily` | Cada día |
| `weekly` | Cada semana |
| `monthly` | Cada mes |
| `weekdays` | Días laborables (lun–vie) |
| `every 2 weeks` | Cada 2 semanas |
| `every 3 days` | Cada 3 días |
| `every 2 months` | Cada 2 meses |
| `first monday` | Primer lunes de cada mes |
| `last friday` | Último viernes de cada mes |
| `none` | Eliminar recurrencia (solo en `edit`) |

Se aceptan días de la semana en inglés y español (`lunes`, `viernes`, etc.).

### Fin de recurrencia (`--until`)

`--until YYYY-MM-DD` indica la fecha límite de la recurrencia. Cuando la siguiente ocurrencia supera esa fecha, la serie se da por finalizada. No confundir con `--end`/`--end-date` de eventos, que indican el día de fin de un evento multi-día.

Ejemplo: `orbit ev add proj "Seminario" --date 2026-04-01 --recur weekly --until 2026-06-30`

En `edit`: `--until none` elimina el límite (la serie pasa a ser indefinida).

### Ring (`--ring`)

| Valor | Significado |
|-------|------------|
| `1d` | 1 día antes del deadline (a las 09:00) |
| `2h` | 2 horas antes |
| `30m` | 30 minutos antes |
| `HH:MM` | Hoy (o en la fecha de la tarea) a esa hora |
| `YYYY-MM-DD HH:MM` | Fecha/hora exacta |
| `none` | Eliminar ring (solo en `edit`) |

Si la tarea tiene `--time`, los rings relativos (`1h`, `30m`) se calculan desde esa hora.
Sin `--time`, se usa 09:00 como ancla por defecto.

Si al crear una tarea, hito o evento con `--time` no se indica `--ring`, Orbit pregunta interactivamente (defecto `5m`, `0` para no añadir ring).

---

## ms — hitos

```bash
orbit ms add    <project> "<text>" [--date DATE] [--time HH:MM] [--recur FREQ] [--until DATE] [--ring WHEN] [--desc DESC]
orbit ms done   [<project>] ["<text>"]
orbit ms drop   [<project>] ["<text>"] [--force] [-o] [-s]
orbit ms log    [<project>] ["<text>"]
orbit ms edit   [<project>] ["<text>"] [--text "<new>"] [--date DATE|none] [--time HH:MM|none] [--recur FREQ|none] [--until DATE|none] [--ring WHEN|none] [--desc DESC|none]
```

---

## ev — eventos

```bash
orbit ev add  <project> "<text>" --date DATE [--end DATE] [--end-time HH:MM] [--time HH:MM|HH:MM-HH:MM] [--recur FREQ] [--until DATE] [--ring WHEN] [--desc DESC] [--agenda URL] [--room URL]
orbit ev drop [<project>] ["<text>"] [--force] [-o] [-s]
orbit ev edit [<project>] ["<text>"] [--text "<new>"] [--date DATE] [--end DATE|none] [--end-time HH:MM] [--time HH:MM|HH:MM-HH:MM|none] [--recur FREQ|none] [--until DATE|none] [--ring WHEN|none] [--desc DESC|none] [--agenda URL|none] [--room URL|none]
```

- `--time`: hora del evento. `HH:MM` (solo inicio, 1h por defecto) o `HH:MM-HH:MM` (inicio-fin)
- `--end-time HH:MM`: hora de fin separada (se combina con `--time` → `HH:MM-HH:MM`). Si no hay `--time`, usa 09:00 como inicio
- `--end` / `--end-date`: fecha de fin para eventos multi-día
- Sin `--time`: evento de día completo
- `drop` en evento recurrente: pregunta si quitar solo esta ocurrencia o toda la serie; `-o` avanza al próximo, `-s` elimina la serie (sin prompt); `--force` avanza al próximo (seguro por defecto)
- `drop` pide confirmación (defecto **No**); `--force` la omite
- `--desc`: descripción (enlaces, notas). Se guarda como líneas indentadas en agenda.md y se propaga a Google Calendar/Tasks. No se muestra en `ls`/`agenda` — solo en el fichero. Aplica también a `task` y `ms`
- `--agenda URL`: agenda/indico del evento. Se guarda como `📋 URL` indentada bajo el item; en `edit`, `none` la quita
- `--room URL`: sala (Zoom, Meet, Teams, Webex, Jitsi). Se guarda como `🚪 URL`; `none` la quita
- Una `--desc` en edit preserva las notas con prefijo `📋`/`🚪` (no las borra)

---

## reminder (rem) — recordatorios

```bash
orbit reminder add  <project> "<text>" --date DATE --time HH:MM [--recur FREQ] [--until DATE] [--desc DESC]
orbit reminder drop [<project>] ["<text>"] [--force] [-o] [-s]
orbit reminder log  [<project>] ["<text>"]
orbit reminder edit [<project>] ["<text>"] [--text "<new>"] [--date DATE|none] [--time HH:MM|none] [--recur FREQ|none] [--until DATE|none] [--desc DESC|none]
```

- Los recordatorios son notificaciones programadas: no tienen estado (done/pending), solo se disparan en la fecha/hora indicada
- Se guardan en la sección `## 💬 Recordatorios` del `agenda.md` del proyecto
- Formato en agenda.md: `- texto (YYYY-MM-DD) ⏰HH:MM [🔄recur[:until]]`
- `drop` en recurrente: pregunta ocurrencia o serie (como task/ev); `-o` avanza al próximo, `-s` elimina toda la serie
- `drop` pide confirmación (defecto **No**); `--force` la omite
- Al iniciar la shell, `ring` programa los recordatorios del día como notificaciones en Reminders.app de macOS
- `--date` y `--time` son obligatorios
- `--recur` y `--until` funcionan igual que en tareas/eventos

---

## hl — highlights

```bash
orbit hl add  <project> "<text>" [<file|url>] --type TYPE [--import] [--link] [--date [FECHA]]
orbit hl drop [<project>] ["<text>"] [--type TYPE] [--force]
orbit hl edit [<project>] ["<text>"] [--text "<new>"] [--link URL] [--type TYPE] [--editor E]
```

- `<file|url>`: argumento posicional opcional. Si es URL, enlaza el texto. Si es fichero local, enlaza y pregunta si quieres importarlo a cloud o linkar a la fuente
- `--import`: importa el fichero a cloud sin preguntar (copia a `hls/`, sin prefijo de fecha). Alias legacy: `--deliver`
- `--link`: registra el fichero como **externa** (symlink al fuente). Solo `.md`. Alias legacy: `--track`. Ver sección [externa](#externa--symlink-a-md-fuera-del-workspace) abajo
- `--type`: `refs` (📎) · `results` (📊) · `decisions` (📌) · `ideas` (💡) · `evals` (🔍) · `plans` (🗓️)
- `--date`: añade fecha al final del texto — `--date` (hoy), `--date tomorrow`, `--date 2026-04-15`
- `drop` pide confirmación (defecto **No**); `--force` la omite
- **Auto-log**: cada `hl add` escribe también una entrada en el logbook con tag `#headline` + el tipo mapeado (`refs→#referencia`, `results→#resultado`, `decisions→#decision`, `ideas→#idea`, `evals→#evaluacion`, `plans→#plan`). Si la highlight tiene link, queda también en el log

---

## note — notas de proyecto

Modelo **propia / externa** (v0.36, ver `DECISIONS.md` ADR-026):

- **Propia**: vive entera en el workspace. Tú la creas, tú la editas.
- **Externa**: vive fuera (otro repo, Drive, etc.). En `notes/` solo hay un symlink relativo al fuente. Editar = editar el original.

```bash
orbit note <project> "<title>" [--from PATH]      # crear propia (atajo)
orbit note create <project> "<title>" [--from PATH] [--no-date] [--no-open] [--editor E]
orbit note open   <project> [<name>] [--date D] [--editor E]
orbit note list   <project> [--open [EDITOR]]
orbit note drop   <project> [<file>] [--force]    # propia: borra; externa: untrack

orbit link    <project> <fullpath>                 # crear externa (alias top-level)
orbit unlink  <project> <name>                     # quitar externa, source intacto
```

> Aliases legacy: `orbit track` / `orbit untrack` siguen funcionando.

- **create** (propia): crea nota en `notes/` desde plantilla y registra en logbook
  - Nombre: `YYYY-MM-DD_título.md` (con fecha de hoy como prefijo)
  - Con `--hl <tipo>`: registra en highlights en vez de logbook, sin prefijo de fecha
  - Con `--no-date`: sin prefijo de fecha, sigue registrando en logbook
  - Con `--from PATH`: contenido pre-cargado de `PATH` (cualquier extensión, escribe como `.md`). Resultado completamente propio, sin link al origen. Útil para "copia inicial" de un Drive compartido, un email, etc.
  - Pregunta: `¿Añadir <fichero> a git? [S/n]`
- **open**: abre nota existente o la crea si no existe
  - `--date D`: nombre por fecha (YYYY-MM-DD, YYYY-Wnn, YYYY-MM)
  - Sin nombre ni fecha: selector interactivo
- **drop**:
  - Si la nota es propia → borra el fichero (pide confirmación; `--force` la omite)
  - Si la nota es externa → equivale a `untrack` (borra el symlink, source intacto)
- **list**: marca el tipo de cada nota:
  - ✏️ propia (vive en el workspace)
  - 🔄 externa (symlink al fuente; muestra `→ /ruta/fuente`)

---

## externa — symlink a `.md` fuera del workspace

Casos: `DECISIONS.md` de tu repo público, draft compartido en Drive de la USC, plan vivo de otro proyecto. **Markdown que vive fuera de orbit-ws, lo quieres a mano en Obsidian y publicado al cloud, sin duplicar la verdad**.

```bash
orbit link    <project> <fullpath>         # crear externa (atajo top-level, uso diario)
orbit unlink  <project> <name>             # quitar externa, source intacto

# forma canónica noun-verb (equivalente):
orbit tracked add  <project> <fullpath>    # = orbit link
orbit tracked drop <project> <name>        # = orbit unlink
orbit tracked list [<project>]             # listar externas con status
```

> Aliases legacy: `orbit track` / `orbit untrack` siguen funcionando. La noun-verb `orbit tracked …` conserva su nombre porque coincide con el registry (`.orbit-tracked.json`).

UX de `link` / `tracked add` con eco de confirmación:

```
$ orbit link orbit /Users/hernando/orbit/DECISIONS.md
  local? /Users/hernando/orbit/
  note?  DECISIONS.md
✓ [💻orbit] Linked: notes/DECISIONS.md → /Users/hernando/orbit/DECISIONS.md
```

- **Mecanismo**: orbit crea un **symlink relativo** en `notes/<basename>` apuntando al fuente. La verdad es el fuente; el symlink solo es una ventana. Editar en Obsidian = editar el fuente.
- **Solo `.md`** (git no diffea binarios; PDFs usa `orbit import`).
- **Registry**: `<project>/.orbit-tracked.json` con schema `{"files": {<name>: <source_path>}}`.
- **Render HTML al cloud**: para cada externa, render lee el fuente al momento, lo convierte a HTML y lo escribe en `cloud/notes/`. Si el fuente no es accesible, usa el último mirror cacheado en `.cache/notes/<proj>/` (gitignored).
- **Doctor**: chequea que cada symlink existe y su target es legible. Si no, reporta `broken_link` / `missing_link` / `not_link` y sugiere `untrack` o `retrack`.
- **Cross-links**: si DECISIONS.md tiene `[RING](RING.md)`, el link resuelve si RING.md también está tracked (siblings en `notes/`). Si no, queda roto silenciosamente en cloud HTML — render emite warning.
- **Sección "🔄 Tracked"** automática en project.md HTML listando las externas con link al HTML y al fuente.
- Diseño completo en `DECISIONS.md` ADR-026 (supersedes ADR-024).

---

## email — capturar un email a un proyecto

```bash
orbit email <project> [--note] [--ev] [--mail|--outlook|--gmail|--eml PATH]
```

- **Default**: añade entry al logbook con link al email original (`message://<id>`, abre Mail.app). Sin nota md.
- Tag de log: `#referencia #email [O]`

**Modificadores aditivos** (combinables):
- `--note` — además guarda la nota `notes/emails/YYYY-MM-DD-<slug>.md` (frontmatter + cuerpo) y la entry pasa a doble link: `[Email: subject](nota.md) ✉️ [original](message://...)`. Con esto la nota es inmortal aunque borres el email original
- `--ev` — además propone crear un evento con los datos detectados: título, fecha, hora, room/agenda. Confirmación interactiva `[S/n/e=editar]`. Si el .eml trae ICS adjunto se usa primero (más fiable); fallback a heurística sobre body (URLs Zoom/Meet/Teams/Webex/Jitsi como rooms; Indico como agendas). No detecta recurrencia (la editas con `ev edit --recur` después)

**Sources** (mutuamente exclusivos; default según `email_source` en `orbit.json`):
- `--mail` — Apple Mail.app, mensaje seleccionado (recomendado, robusto)
- `--outlook` — Microsoft Outlook for Mac (frágil con Outlook 16.x; usa drag→`.eml` si falla)
- `--gmail` — Gmail (pendiente)
- `--eml PATH` — parsea un `.eml` exportado de cualquier cliente. En Outlook: arrastra el email al Finder → genera `<subject>.eml`

**Configuración por workspace** (`orbit.json`):
```json
"email_source": "mail"   // mail | outlook | gmail
```

---

## view / open — navegar proyectos

```bash
orbit view  [<project>] [--open [EDITOR]]
orbit open  <project> [logbook|highlights|agenda|project] [--editor E] [--dir]
```

- `view` sin proyecto: muestra lista para selección interactiva
- `view <project>`: resumen en terminal (estado, tareas, hitos, próximos eventos, entradas recientes)
- `view <project> --open`: genera `cmd.md` y lo abre en el editor
- `open --dir`: abre el directorio del proyecto en Finder

---

## log y search

```bash
orbit log <project> "<título>" [<file|url>] [--entry TIPO] [--import] [--link] [--note NOTA] [--date D] [--open [EDITOR]]

orbit search [query] [--project P...] [--entry TIPO] [--date D] [--from D] [--to D]
             [--in logbook|highlights|agenda] [--any] [--notes]
             [--limit N] [--open [EDITOR]]
```

- `<file|url>`: argumento posicional opcional. Si es URL, enlaza el título. Si es fichero local, pregunta si quieres importarlo a cloud o linkar a la fuente
- `--import`: importa a cloud sin preguntar (copia a `logs/` con prefijo `YYYY-MM-DD_`). Alias legacy: `--deliver`
- `--link`: linka a la fuente sin preguntar (sin copia). Alias legacy: `--track`
Muchos comandos soportan `--append proyecto:nota` para añadir su salida a una nota:

```bash
orbit report today --append catedra:calibracion     # report del día → nota
orbit agenda --append mission:W12                    # agenda → nota semanal
orbit view catedra --append catedra:estado           # vista del proyecto → nota
orbit search "algo" --append catedra:busqueda        # resultados de búsqueda → nota
```
- Si el fichero es imagen (png, jpg, svg...), se inserta `![título](link)` en la línea siguiente de la entrada
- `--entry`: filtra por tipo de entrada (`idea` · `referencia` · `apunte` · `problema` · `solucion` · `resultado` · `decision` · `evaluacion` · `plan`)
- `--in`: busca en un tipo de fichero específico (por defecto logbook)

---

## crono — cronogramas (task compuesta)

Cronogramas: tareas anidadas con dependencias y duración temporal. Conceptualmente son una **task-compuesta** (extensión del sistema task). Se almacenan en `cronos/crono-<nombre>.md` dentro del proyecto, enlazados desde `## 📊 Cronogramas` en agenda.md.

```bash
orbit task crono add     <project> "<name>"                    # crear cronograma
orbit task crono show    <project> "<name>" [--open]           # mostrar con fechas calculadas
orbit task crono edit    <project> "<name>" [--open [EDITOR]]  # abrir en editor
orbit task crono check   <project> "<name>"                    # validar (doctor)
orbit task crono list    <project> [--open]                    # listar cronogramas del proyecto
orbit task crono done    <project> "<name>" [<index|texto>]    # marcar tarea como completada
orbit task crono reindex <project> "<name>"                    # renumerar índices automáticamente
orbit task crono gantt   <project> "<name>" [--open]           # visualizar como Gantt

orbit crono <sub> ...                                          # atajo top-level (uso diario)
```

- `done` sin argumento: selección interactiva de tareas pendientes
- `done` con texto parcial: busca por índice o título
- `done` registra la completación en el logbook del proyecto (`📊crono] idx título #apunte`)
- Las tareas completadas manualmente en Obsidian (clic en checkbox) se detectan y registran automáticamente al hacer `save`
- `gantt`: auto-detecta modo DAG (progreso) o con fechas (timeline)
- `gantt --progress`: fuerza vista de progreso (barras + checkboxes)
- `gantt --timeline`: fuerza vista temporal (eje de fechas)
- `reindex`: corrige huecos e inconsistencias en la numeración (actualiza `after:`)

### Formato del fichero

```markdown
# Cronograma: nombre del cronograma

deadline: 2026-05-30
exclude: sat, sun

- [ ] 1 Fase 1 título
  - [ ] 1.1 Subtarea | 2026-03-20 | 2W
  - [ ] 1.2 Otra subtarea | after:1.1 | 3d
- [ ] 2 Fase 2 | after:1
  - [ ] 2.1 Siguiente | | 1W
```

- **Inicio**: fecha ISO (`2026-03-20`), semana ISO (`2026-W12`), semana+día (`2026-W12-wed`), o dependencia (`after:<índice>`)
- **Duración**: `Nd` (días), `NW` (semanas)
- **Tareas padre** calculan su inicio/fin de las hijas
- **`after:` en padres**: se hereda a las hojas sin inicio propio (`2.1` hereda `after:1` de `2`)
- **Modo DAG**: sin duraciones — solo estructura y dependencias, útil para seguimiento de progreso
- **Deadline**: fecha límite del cronograma. Muestra ritmo necesario y avisa si vas retrasado:
  `⚠️ deadline 2026-05-30 (4d) — 12 pendientes, ritmo: 3/día`
  Acepta fecha ISO o nombre de hito del proyecto (busca la fecha en la agenda)
- **Metadatos**: `deadline`, `exclude: sat, sun` (excluir fines de semana), `initial-time: 2026-06-01` (inicio por defecto)
- **Indentación**: soporta 2 espacios, 4 espacios o tabs (autodetección)
- `check` valida: índices únicos, dependencias válidas, sin ciclos, hojas con inicio+duración
- El progreso y deadline de los cronogramas se muestran en `orbit panel`
- Cronogramas completados (100%) se ocultan del panel automáticamente

---

## undo — deshacer operaciones

```bash
orbit undo
```

- Muestra la lista de operaciones deshacibles (más reciente primero)
- El usuario elige cuál deshacer (por defecto la última; 0 para cancelar)
- Si se elige N, se deshacen las N operaciones más recientes
- Restaura el estado anterior de todos los ficheros afectados
- Stack de hasta 20 operaciones (en memoria, durante la sesión del shell)
- Si se creó un fichero nuevo, lo elimina; si se borró, lo restaura

---

## clip — copiar al portapapeles

Comando unificado para copiar fechas, semanas y enlaces al portapapeles:

```bash
orbit clip date                # hoy: 2026-03-20 (copiado al portapapeles)
orbit clip date wednesday      # próximo miércoles
orbit clip date in 2 weeks     # dentro de 2 semanas
orbit clip week                # esta semana: 2026-W12
orbit clip week next week      # próxima semana
orbit clip <project>                                        # enlace al proyecto
orbit clip <project> notes/result.md                        # enlace a un fichero del proyecto
orbit clip catedra notes/tramos.md --from complementos      # enlace relativo entre proyectos
```

- `clip date [expr]`: fecha YYYY-MM-DD al portapapeles. Sin argumento: hoy
- `clip week [expr]`: semana ISO YYYY-Wnn al portapapeles. Sin argumento: semana actual
- `clip <project> [fichero]`: enlace markdown al proyecto o a un fichero del proyecto
  - Sin fichero: `[⚙️catedra](⚙️gestion/⚙️catedra/catedra-project.md)`
  - Con fichero: busca por nombre parcial en el proyecto (interactivo si hay varias coincidencias)
  - `--from <proyecto>`: calcula ruta relativa desde la raíz del proyecto origen (para Obsidian)

---

## ls — listados

```bash
orbit ls                              # lista proyectos (por defecto)
orbit ls projects [--status S] [--type T] [--sort type|status|priority]
orbit ls tasks    [project...] [--status pending|done|all] [--date D] [--dated] [--unplanned]
orbit ls ms       [project...] [--status pending|done|all] [--date D] [--dated]
orbit ls ev         [project]    [--from D] [--to D]
orbit ls reminders  [project]    # recordatorios activos (alias: ls rem)
orbit ls hl        [project]    [--type T]
orbit ls files    [project]    # ficheros md del proyecto con estado git
orbit ls notes    [project]    # notas con estado git
```

- `--unplanned`: solo tareas sin fecha asignada (futuribles)
- `--no-fed`: excluye proyectos federados del listado

Indicadores git en `files` y `notes`: `✓` tracked · `M` modified · `+` untracked · `✗` ignored

---

> **Panel y agenda** son las dos herramientas dinámicas para gestionar el día. Se abren al empezar (`--open` para fijar en Obsidian) y se refrescan durante la jornada. Panel da la vista de alto nivel (prioridad + citas + actividad); agenda detalla las citas. Al final del día, `report` resume la actividad.

## agenda — citas del día (herramienta dinámica)

```bash
orbit agenda [project...] [--date D] [--from D] [--to D] [--no-cal] [--summary] [--dated] [--order project|date] [--no-fed] [--open [EDITOR]]
orbit agenda week                     # esta semana
orbit agenda month                    # este mes
```

- Sin fecha: muestra el día de hoy (tareas pendientes, vencidas, eventos, hitos)
- Atajos de periodo: `today`/`hoy`, `week`/`semana`, `month`/`mes`
- `--date 2026-03`: todo el mes
- `--from monday --to friday`: rango
- El calendario se muestra por defecto; `--no-cal` lo suprime (para calendarios dedicados, usa `cal`)
- Colores del calendario: azul (semana) · amarillo (tarea) · cian (evento) · magenta (hito) · rojo (vencida) · invertido (hoy)
- `--summary`: tabla resumen por proyecto (primera/última fecha, conteo de tareas/hitos/eventos/sin fecha)
- `--dated`: solo muestra tareas/hitos que tienen fecha asignada
- `--order project`: agrupa por proyecto (por defecto)
- `--order date`: agrupa por día, con horas como sub-cabeceras; sin-fecha al final
- `--no-fed`: excluye proyectos de workspaces federados
- `--open` escribe a `📋secretary/agenda-next.md` (fijable en Obsidian) — formato tabla markdown
- Tareas vencidas se agrupan en el día de hoy con la fecha original: `(📅2026-03-22) ⚠️`
- Compatible con `--log`

---

## panel — dashboard dinámico

```bash
orbit panel                                        # panel del día
orbit panel week                                   # panel de la semana
orbit panel month                                  # panel del mes
orbit panel --from monday --to friday              # rango personalizado
orbit panel --open                                 # abre en editor (📋secretary/panel.md)
orbit panel --no-fed                               # sin proyectos federados
orbit panel --append mission:W12                   # añade a una nota
```

Dashboard con cuatro secciones (formato tabla markdown):

- **Prioridad**: tabla con 🔴 alta, 🔶 urgente (citas/vencidas en periodo), 🏁 hitos del mes
- **Agenda**: tabla por día con columnas: tipo, hora, descripción, proyecto (con link)
- **📊 Cronogramas**: barra de progreso por cronograma (solo si hay cronogramas activos)
- **Actividad**: entradas de logbook del periodo por proyecto

`--open` escribe a `📋secretary/panel.md` (fijable en Obsidian). `--no-fed` excluye federados.

Proyectos locales se muestran como links a `project.md`; federados con emoji del workspace (🌿).

---

## organize — triage interactivo

```bash
orbit organize                       # hoy + vencidas, todos los tipos
orbit organize tasks                 # solo tareas
orbit organize ev -P week            # eventos de esta semana
orbit organize -p next-kr            # solo proyecto next-kr
orbit organize -P 2026-W22           # ISO week específica
orbit organize -P 2026-05-15         # un día concreto
orbit organize --triage              # pending tasks con ⏩ <= today
```

Modo default (planned + overdue): acciones `[d]rop [n]done [f]echa [h]ora [s]kip`.

Modo `--triage` (pending): acciones `[p]lan-date  [f]f-snooze  [d]rop  do[n]e  [s]kip`. `p` promueve a planned con fecha (limpia ⏩, incrementa ❌ si vencida). `f` actualiza ⏩ (incrementa 💤, acepta `someday`, default `tomorrow`).

Alias legacy: `orbit reorganize` sigue funcionando.

Modo bucle:

1. Lista los items pendientes que cumplen los filtros (vencidas arriba con ⚠️, luego cronológico, sin fecha al final).
2. Eliges un número.
3. Acciones disponibles:
   - `d` — drop (cancela / borra ocurrencia)
   - `n` — done (task/ms/reminder; los eventos no aplican)
   - `f` — cambiar fecha (lenguaje natural: `tomorrow`, `next monday`, `+7`, `2026-05-25`)
   - `h` — cambiar hora (`HH:MM` o `HH:MM-HH:MM`; `none` quita)
   - `s` — skip, vuelve a la lista
4. Tras cada cambio, refresca la lista. Sale con `q`.

Cada acción dispara `sync_item` automático → Calendar/Reminders se actualizan al instante. Para editar título / notas / recurrencia / ring, sales con `q` y usas `task edit` (etc.) directamente.

---

## report — informe de actividad

```bash
orbit report [project...] [--date D] [--from D] [--to D] [--no-fed] [--open [EDITOR]]
orbit report today                    # actividad de hoy
orbit report week                     # actividad de esta semana
orbit report month                    # actividad de este mes
orbit report yesterday                # actividad de ayer
orbit report myproject today          # actividad de hoy en un proyecto
orbit report --summary [logbook|agenda|highlights|all] [--date D] [--from D] [--to D]
```

- Atajos de periodo: `today`/`hoy`, `yesterday`/`ayer`, `week`/`semana`, `month`/`mes`
- Sin proyecto: muestra informe de todos los proyectos activos
- Con proyecto(s): informe solo de esos proyectos
- Sin fechas: últimos 30 días
- Muestra: entradas de logbook, highlights, tareas completadas/pendientes/vencidas, hitos, eventos
- `--summary`: tabla markdown ordenada por actividad descendente
  - Sin valor: logbook + agenda (las secciones con datos filtrados por periodo)
  - `logbook`: solo tabla de entradas por tipo
  - `agenda`: solo tabla de tareas/hitos/eventos
  - `highlights`: solo tabla de highlights (snapshot actual, sin filtro de periodo)
  - `all`: las tres tablas
- Compatible con `--log`: redirige el informe al logbook de otro proyecto (tablas markdown se insertan sin code block)

---

## Servicios externos

> Orbit gestiona estas conexiones automáticamente (al arrancar, al operar sobre citas, al hacer save). Los comandos siguientes permiten interactuar manualmente.

### Git — versionado (workflow `save`)

```bash
orbit save ["<mensaje>"]
```

Alias legacy: `orbit commit` sigue funcionando.

- Sin mensaje: pide interactivamente; intro vacío → genera mensaje automático
- Muestra ficheros modificados y pide `[S/n]` antes de ejecutar
- Ejecuta doctor pre-check: valida agendas/logbooks antes del save
- Ejecuta reconciliación gsync: detecta renombramientos de citas en el markdown y migra IDs de Google
- Push al remoto: `orbit_push` desde la terminal del sistema (fuera de la shell)

### Sincronización legacy con Calendar.app (`gsync`, `calsync`)

**Deprecado desde v0.33**. La sincronización con Calendar pasa ahora por `.ics` (ver sección siguiente) y `agenda.md` es la única fuente de verdad. Calendar.app es read-only por subscripción.

Si por alguna razón necesitas el camino AppleScript-write antiguo (push directo, reconciliación de drift…), ver `DORMANT.md` con los pasos exactos para revivirlo. Por defecto los comandos `orbit gsync` y `orbit calsync` ya no aparecen en el CLI.

### Calendar.app — ics (export iCalendar / suscripciones) ← ruta principal desde v0.33

```bash
orbit ics <proyecto>                       # imprime .ics a stdout
orbit ics <proyecto> --out file.ics        # escribe a fichero
orbit ics --bucket agenda                  # un bucket de workspace (agenda|events|ms|...)
orbit ics --workspace                      # regenera todos los .ics en cloud_root/calendar/
orbit ics --validate                       # dry-run: cuenta VEVENTs por bucket, sin escribir
```

**Auto-regen**: cualquier mutación CLI sobre task/ms/ev/reminder/crono/ics-import/email dispara en background un thread daemon que ejecuta `dash` (coalescido) + `ring.refresh_all()` + `write_workspace(project_filter=<proj>)` — `.ics` y Reminders.app se actualizan solos sin esperar a `save`. Mutaciones de `log`/`hl`/`project` disparan solo dash (no afectan a citas). Render a HTML se reserva para `save` (commit_post).

**Topología** (en `cloud_root/calendar/`, configurable en `ics_buckets`):

```
calendar/
  ├── events.ics                ← solo eventos (azul)
  ├── ms.ics                    ← solo milestones (amarillo) — destacan visualmente
  ├── agenda.ics                ← tasks + reminders + cronogramas (gris)
  └── projects/
        ├── phd-diego.ics       ← per-proyecto, TODAS las citas (para compartir refs puntuales)
        └── …
```

**Suscripción desde Calendar.app** (USC OneDrive — receta probada en orbit-ws):

1. En OneDrive web, click derecho sobre el `.ics` → Compartir → `Cualquier persona con el enlace` (no `Personas de la USC`).
2. Copia el enlace; tendrá formato `https://nubeusc-my.sharepoint.com/:u:/g/personal/.../<id>?e=<token>`.
3. Convierte para Calendar.app:
   - `https://` → `webcal://`
   - Añade `&download=1` al final (fuerza .ics crudo en vez del visor HTML)
4. Calendar.app → `Archivo → Nueva suscripción de calendario` → pega el `webcal://` → `Suscribir`.
5. Configura: nombre, Ubicación = `En mi Mac`, refresco = `Cada 5 minutos`, color a elección.

**Propagación a iPhone/iPad**: Apple quitó la opción "iCloud" del diálogo macOS ~2023. Para sincronizar entre dispositivos: ve a `icloud.com/calendar` web → sidebar → click derecho en `Calendarios` → `Nueva suscripción` → pega el mismo URL. Aparecerá automáticamente en todos tus Apple devices.

**Si OneDrive de tu institución no permite "Cualquiera con el enlace"** (USC sí lo permitía): alternativas son GitHub Pages (repo público con el .ics) o Google Drive personal con `https://drive.google.com/uc?export=download&id=<id>`.

**Buckets**: configurables en `calendar-sync.json`. Ejemplo de orbit-ws (3 buckets para colorear ms aparte):

```json
{
  "ics_buckets": {
    "events": ["event"],
    "ms":     ["milestone"],
    "agenda": ["task", "reminder", "cronograma"]
  }
}
```

Default si no defines `ics_buckets`: `agenda=task+rem`, `events=ev+ms+crono`. Cada `kind` (`task`/`milestone`/`event`/`reminder`/`cronograma`) debe aparecer en **exactamente un** bucket. `doctor` valida el reparto y la frescura (alerta si un `.ics` lleva >24h sin update). El nombre del bucket es el nombre del fichero (`agenda` → `agenda.ics`).

**Duración de cada cita en .ics** (sintética; no toca `agenda.md`):
- `event` (sin `--end-time`), `milestone`, `task`, `cronograma`: 60 min
- `reminder`: 5 min
- `event` con `--time HH:MM-HH:MM` o `--end-time`: respeta lo declarado

**orbit-id visible**: cada VEVENT lleva `[orbit:xxxxxxxx]` al final de `DESCRIPTION` (visible en Calendar.app/iOS) + `X-ORBIT-ID` custom prop + UID `<orbit_id>@orbit`. Si ves un evento "raro" en Calendar.app, el orbit-id en la descripción te permite localizar la cita en `agenda.md` rápido.

**Propagación a Calendar.app**: `orbit render` (que corre tras cada save) regenera todos los `.ics` y lanza un `tell application "Calendar" to reload calendars` AppleScript (read-only) para forzar refresh inmediato. Latencia de Mac → ~2 s. iPhone hereda vía iCloud al ritmo de iCloud (5-15 min).

**Snapshot diff**: cada `.ics` se guarda con un `.ics.snapshot` paralelo (versión anterior). `write_workspace` reporta cuántas citas se añadieron/modificaron/eliminaron desde el último render — útil para auditar drift sin abrir Calendar.app.

### Compartir e importar citas puntuales

```bash
orbit ics-share <proj> --orbit-id ID     # exporta esa cita a /tmp/orbit-<id>.ics
orbit ics-share <proj> --desc PATTERN    # busca por descripción (interactivo si ambigüedad)
orbit ics-share <proj> --orbit-id ID --out ruta.ics
orbit ics-import <proj> ruta.ics         # importa un .ics como nueva cita
orbit ics-import <proj> --clipboard      # lee del portapapeles (pbpaste)
```

**Scope** (v0.33): solo **citas puntuales**, no series recurrentes. Si exportas una cita recurrente, exporta solo la **próxima ocurrencia**. Si el `.ics` de entrada trae `RRULE`, se ignora y se importa solo la primera ocurrencia con un warning.

**Export**: el path resultante se imprime y se copia al portapapeles para que en Mail solo tengas que `Cmd+V` en el adjunto. El .ics lleva `METHOD:PUBLISH`, `X-WR-CALNAME` informativo, y la cita con todos sus props (UID, SUMMARY, DTSTART, DTEND, DESCRIPTION con `[orbit:xxx]`, X-ORBIT-*, VALARM si tiene ring).

**Import**:
- Auto-detecta el `kind`: respeta `X-ORBIT-KIND` (round-trip), o usa `event` si es all-day / time-range, o pregunta si es ambiguo.
- Si el SUMMARY trae el prefijo `[<proyecto>] [<emoji>] ` (export propio de orbit), lo strippea.
- `URL`/`LOCATION` con URL de meeting (zoom/meet/teams/indico) → nota `🚪 <url>`.
- `DESCRIPTION` → notas indentadas (sin la línea "Proyecto:" ni el tag `[orbit:xxx]`).
- TZIDs: `Z` (UTC) se convierte a local; `Europe/Madrid` se toma como floating; otros se toman como floating con warning.
- Conflicto: si ya existe cita con mismo `desc+date` en el destino → prompt `[d-duplicar / o-overwrite / c-cancel]`.
- Tras crear: regen automático del `.ics` del proyecto.

### Cloud (OneDrive/Google Drive) — render y cloud

```bash
orbit render                          # renderiza ficheros del último save
orbit render <project>                # renderiza un proyecto completo
orbit render --full                   # renderiza todos los proyectos

orbit cloud deliver <project> <file>  # entrega un fichero al cloud del proyecto
orbit cloud sync [--dry-run]          # fuerza sync completo md→HTML al cloud
orbit cloud imgs [--dry-run]          # recoge imágenes de _imgs/ y entrega a cloud

orbit deliver <project> <file>        # alias top-level de `cloud deliver`
```

- Convierte ficheros `.md` de cada proyecto a `.html` en el directorio cloud
- Front-page del cloud: `workspace.html` (de `workspace.md`) + `index.html` stub con `<meta http-equiv="refresh">` redirigiendo a `workspace.html` (para que el browser abra el cloud-root automáticamente)
- Incluye soporte KaTeX para ecuaciones LaTeX (`$...$` y `$$...$$`)
- `cloud sync` se ejecuta automáticamente en background tras cada `save`; el verbo manual sirve para forzar o auditar con `--dry-run`
- `deliver` también disponible como `--deliver` en `log` y `hl add`
- Estructura cloud: `cloud_root/{tipo}/{proyecto}/cloud/{logs,hls,imgs,...}/`
- `cloud_root` se configura en `orbit.json`; cada proyecto tiene un link `[cloud]` en `project.md`

### Mac Reminders — notificaciones

No hay un comando propio — `--ring` es un flag transversal disponible en `task`, `ms`, `ev`:

```bash
orbit task add next-kr "Reunión" --date tomorrow --time 10:00 --ring 30m
```

- Si creas una cita con `--time` sin `--ring`, Orbit pregunta interactivamente (defecto: 5 min antes)
- Al entrar en la shell, se programan las notificaciones del día de todos los workspaces
- Valores: `1d` (1 día antes), `2h`, `30m`, `HH:MM` (hora fija), `YYYY-MM-DD HH:MM`

### Setup — configuración interactiva

```bash
orbit setup                    # asistente interactivo de configuración
```

- Guía paso a paso: workspace, tipos, editor, Google Sync, cartero (Gmail/Slack), federación
- Si `orbit.json` ya existe, muestra valores actuales como defaults
- Cada sección es opcional — Enter para saltar
- Genera/actualiza `orbit.json` y `federation.json`

### Cartero — notificaciones de correo

```bash
orbit mail                     # check manual: muestra no leídos por etiqueta (detallado)
orbit mail --summary           # check en vivo, formato compacto (una línea por fuente)
orbit mail --status            # estado del proceso background
orbit mail --start             # arranca el proceso background
orbit mail --stop              # para el proceso background
```

- Vigila Mail.app, Gmail (legacy) y/o Slack y avisa de mensajes no leídos
- Notificación macOS cuando llegan mensajes nuevos (solo al subir el conteo, no en cada check)
- Proceso background: se lanza al entrar en la shell, un solo proceso por workspace (PID lock)
- Configuración en `orbit.json`:

```json
"cartero": {
  "mail": {
    "watch": [
      {"account": "🏛️ USC",     "mailbox": "Inbox"},
      {"account": "🏠 Personal", "mailbox": "🏠 hogar"}
    ],
    "interval": 600
  },
  "slack": {
    "channels": ["general", "alertas"],
    "interval": 600
  }
}
```

- **Mail (recomendado)**: AppleScript a Mail.app. `watch` lista pares `{account, mailbox}` — los nombres son los que muestra Mail.app (los Gmail labels aparecen como mailboxes IMAP dentro de la cuenta Gmail). Sin OAuth, sin tokens. Requiere Mail.app abierto y sincronizado; si no está corriendo, cartero salta esa fuente sin error
  - Listar tus cuentas: `osascript -e 'tell application "Mail" to get name of every account'`
  - Listar mailboxes: `osascript -e 'tell application "Mail" to get name of every mailbox of account "X"'`
- **Gmail (legacy)**: `labels` = etiquetas a vigilar. Requiere `credentials.json` + API de Gmail habilitada en Google Cloud Console. Mantener solo si no migras a Mail.app
- **Slack**: `channels` = canales a vigilar. Requiere token de usuario en `ORBIT_HOME/.slack-token` (una línea, `xoxp-...`). Slack para Mac no expone AppleScript útil — la API es la única vía con conteo por canal
- `interval`: segundos entre checks (default: 600 = 10 min)
- Estado en `ORBIT_HOME/.cartero-state.json`, PID en `ORBIT_HOME/.cartero.pid`

---

## Mantenimiento interno

### history — historial de comandos

```bash
orbit history                          # hoy
orbit history --date 2026-03-11        # día concreto
orbit history --date 2026-03           # mes
orbit history --date 2026-W11          # semana
orbit history --from D --to D          # rango
orbit history --open                   # abrir en editor
```

- Registra automáticamente los comandos que modifican estado (log, task, ms, ev, note, save, hl, project...)
- No registra comandos de solo lectura (agenda, report, view, ls, doctor, search, history, open)
- Fichero: `history.md` en la raíz de Orbit

### doctor — validación de ficheros

```bash
orbit doctor [<project>]        # revisa todos o un proyecto
orbit doctor --fix [<project>]  # revisa y ofrece corregir
```

El doctor hace 3 tipos de check (mismo comando, salida segmentada):

1. **Sintaxis por proyecto** — logbook (fechas, tipos, emojis), agenda (marcadores, recurrencia, eventos), highlights (secciones, items, links), cronogramas.
2. **Refs por proyecto** — para cada link `[…](target)` en logbook + highlights, verifica que el target existe:
   - `./cloud/...` → busca en `<workspace>/<proj>/cloud/...` (el symlink a cloud_root)
   - `./notes/...` → busca en `<proj>/notes/...` (propia o symlink a externa)
   - `/abs/path` o `~/path` → busca en el filesystem local
   - Refs cross-project (`⚙️gestion/⚙️foo/...`) → busca en `ORBIT_HOME/...`
   - URLs (`http://`, `mailto:`, `message://`, etc.) y anchors (`#sec`) se ignoran
3. **Entorno (workspace)** — corre una sola vez por invocación:
   - `orbit.json` existe, JSON válido, claves `cloud_root` y `types` presentes
   - `cloud_root` apunta a un directorio existente y escribible
   - `federation.json` (si existe) JSON válido y cada `federated[].path` existe
   - Linked md externos: cada symlink en `notes/` apunta a un fichero real
   - Ring: plist, TCC, ring.json freshness
   - ICS: buckets bien configurados + frescura de los `.ics` en cloud

Se ejecuta automáticamente al iniciar la shell, antes de cada save **y periódicamente en background por el watchdog** (ver más abajo). Con `--fix`: muestra correcciones disponibles y permite aplicarlas interactivamente.

### watchdog — pre-check + refresh periódico

Daemon background que arranca al abrir la shell. Cada `interval_minutes` (defecto 60):

1. Corre `doctor` sobre el workspace.
2. **Si hay issues** → escribe `.doctor-pending` (marker) y NO regenera derivados (panel/agenda-next/calendar/projects/report-summary, .ics, ring.json se congelan en su última versión limpia). El prompt del REPL muestra al siguiente input — una sola vez por sesión:

   ```
   🏥 Doctor (14:30): 3 problemas detectados — ejecuta `doctor`
   ```

3. **Si limpio** → `_run_full_refresh_coalesced` (dash + ring + ics) y borra el `.doctor-pending` si existía.

Propósito: capturar drift introducido por edición externa (Obsidian, editor) entre comandos orbit. Sin watchdog, el `.ics` y Reminders.app no se enterarían de un `agenda.md` editado a mano hasta el siguiente `save`.

Config en `<workspace>/orbit.json` (clamp `[5, 1440]` minutos):
```json
"watchdog": {
  "enabled": true,
  "interval_minutes": 60
}
```

Para desactivarlo: `"enabled": false`.

### ring — alarmas vía Reminders.app (Orbit Ring)

```bash
orbit ring refresh                        # regenera ring.json en todos los workspaces y aplica
orbit ring refresh --no-daemon            # solo escribe ring.json, sin tocar Reminders.app
orbit ring status                         # muestra ring.json por workspace + estado del plist launchd
orbit ring install                        # instala ~/Library/LaunchAgents/com.orbit.ring-daemon.plist
orbit ring uninstall                      # descarga y elimina el plist
```

Modelo declarativo: `agenda.md` (verdad) → `<ws>/.reminders/ring.json` (ventana 7 días) → daemon EventKit reconcilia la lista de Reminders.app del workspace. Una lista por workspace (default = nombre del directorio del workspace, e.g. `🚀orbit-ws`, `🌿orbit-ps`). El daemon nunca toca items sin tag `[orbit:xxx]` — los reminders manuales del usuario en la misma lista están a salvo.

Triggers automáticos (vía hook system):
- `shell_start` → refresca al arrancar `orbit shell`
- `commit_post` → refresca tras cada `orbit save` (nombre interno del chain mantiene `commit_post`)
- `launchctl WatchPaths` (si has hecho `orbit ring install`) → cualquier escritura del `ring.json` dispara el daemon
- `StartCalendarInterval` 00:05 (vía launchd) → sweep nocturno

Config en `<workspace>/orbit.json`:
```json
"ring": {
  "enabled": true,           // false → vacía la lista del workspace
  "days":    7,              // ventana rolling, clamped a [1, 30]
  "list":    "🚀orbit-ws"    // default = workspace_root.name
}
```

Eligibilidad de una cita en el ring: tiene `--ring`, tiene `time`, tiene `orbit_id`, status pending (task/ms) o no cancelled (reminder). Recurrentes se expanden en la ventana (un EKReminder por ocurrencia con orbit_id derivado `<base>-<date>`).

Primera vez tras `orbit ring install`: macOS pide autorizar el binario Python en *System Settings → Privacy & Security → Reminders*. Si el log `~/Library/Logs/orbit/ring-daemon.stderr.log` dice `access denied`, autoriza y haz `launchctl kickstart -k gui/$(id -u)/com.orbit.ring-daemon`.

### archive — archivado de entradas antiguas

```bash
orbit archive [<project>] [--months N] [--dry-run] [--force]
orbit archive orbit --agenda              # solo tareas/hitos done + eventos pasados
orbit archive orbit --logbook             # solo entradas de logbook
orbit archive orbit --notes               # solo notas obsoletas
orbit archive orbit --agenda --logbook    # combinación
```

- Sin proyecto: limpia todos los proyectos
- Sin flags: limpia todo, preguntando confirmación por cada categoría
- `--months N`: antigüedad mínima para eliminar (defecto: 6 meses)
- `--dry-run`: muestra qué se eliminaría sin borrar nada
- `--force`: salta todas las confirmaciones

Qué se limpia:
1. **agenda**: tareas/hitos completados `[x]`/cancelados `[-]` + eventos pasados
2. **logbook**: entradas con fecha anterior al corte
3. **notes**: notas en `notes/` no modificadas en N meses

Los datos eliminados son recuperables con `git log -p -- <fichero>`.

### claude — asistente integrado

```bash
orbit claude "¿cómo creo una tarea recurrente?"
orbit claude "quiero ver la agenda de la semana"
```

- Envía la pregunta a Claude con la CHULETA como contexto
- Si un comando falla y hay API key, sugiere alternativas automáticamente
- Requiere: `pip install anthropic` + `ANTHROPIC_API_KEY` env var

---

## Startup — al iniciar la shell

Al entrar en `orbit shell`:

1. **Doctor** — valida la integridad de logbook, agenda y highlights; ofrece corregir errores
2. **Ficheros sin trackear** en `🚀proyectos/` — ofrece añadirlos a git
3. **Cambios sin save** — ofrece hacer save + push (mensaje por defecto: `sync YYYY-MM-DD`)
4. **gsync** en background + **recordatorios** — sincroniza con Google y programa los recordatorios del día (tras save)
5. **Cartero** — lanza el proceso background de correo si hay configuración en `orbit.json`

---

## Federación de workspaces

Orbit puede leer proyectos de otros workspaces (lectura federada). Útil para ver citas personales desde el workspace de trabajo.

Configuración: `federation.json` en la raíz del workspace:

```json
{
  "federated": [
    {"name": "personal", "path": "~/🌿orbit-ps", "emoji": "🌿"}
  ]
}
```

- Los comandos de lectura (`panel`, `agenda`, `report`, `ls`, `search`) incluyen proyectos federados por defecto
- `--no-fed`: desactiva la federación para ese comando
- Los comandos de escritura (`add`, `edit`, `done`, `drop`) solo operan en el workspace activo
- Los proyectos federados se muestran con el emoji del workspace (🌿) sin link
- Los recordatorios del Mac (`ring`) se programan para ambos workspaces al entrar en la shell
- La federación es asimétrica: cada workspace decide qué otros ve

---

## help — documentación

```bash
orbit help            # muestra CHULETA.md en terminal (paginado)
orbit help chuleta    # equivalente (paginado)
orbit help tutorial   # muestra TUTORIAL.md en terminal (paginado)
orbit help about      # muestra README.md en terminal (paginado)
orbit help --open     # abre CHULETA.md en el editor
orbit help tutorial --open   # abre TUTORIAL.md en el editor
```

---

## --open — abrir resultado en editor

Los comandos de consulta aceptan `--open [EDITOR]`:
capturan el output, lo escriben en un fichero markdown y lo abren en el editor.

```bash
orbit agenda --open               # abre en editor por defecto
orbit agenda --open obsidian      # abre en Obsidian
orbit panel --open code           # abre en VS Code
```

- `panel --open` → `📋secretary/panel.md`
- `agenda --open` → `📋secretary/agenda-next.md`
- `cal --open`   → `📋secretary/calendar.md`
- El resto → `cmd.md`

`orbit dash` regenera además `📋secretary/{projects,report-summary}.md`
(tabla de proyectos del workspace + `report --summary` de los últimos N
días). Ventanas configurables en `orbit.json`:

```json
"secretary": {
  "agenda_days": 14,   // ventana de agenda-next, [1, 90]
  "report_days": 14    // ventana de report-summary, [1, 365]
}
```

Estos ficheros se pueden fijar en Obsidian (pin tab) para tener un dashboard permanente.

Sin especificar editor, se usa el editor por defecto (en orden de prioridad):
1. `ORBIT_EDITOR` (variable de entorno)
2. `"editor"` en `orbit.json` (por workspace)
3. Abridor del sistema (`open` en macOS)

Comandos que lo admiten: `ls` · `view` · `search` · `report` · `agenda` · `panel` · `help` · `history` · `crono show/list/gantt` · `note list`

Los comandos que abren ficheros directamente usan `--editor E` (no `--open`): `open`, `note create/open/import`, `hl edit`, `project edit`, `shell`.

---

## --log — guardar resultado en logbook

```bash
orbit ls projects --log mission                     # guarda en logbook de mission como #apunte
orbit ls tasks --log mission --log-entry evaluacion  # como #evaluacion
orbit view next-kr --log orbit                      # resumen al logbook de orbit
orbit report orbit --log mission                    # informe de orbit al logbook de mission
```

- `--log PROJECT` captura el output y lo añade como entrada al logbook del proyecto indicado.
- `--log-entry TYPE` cambia el tipo de entrada (por defecto `apunte`).
- La entrada incluye una línea resumen + el output completo en bloque de código.
- Compatible con `--open`: ambos pueden usarse a la vez.

Comandos que lo admiten: los mismos que `--open`.

---

## Tipos de proyecto

Configurables en `orbit.json`. Ver: `orbit project type`

## Estados

`new` ⬜ · `active` ▶️ · `paused` ⏸️ · `sleeping` 💤 · `[auto]` (inferido por Orbit)

- `new`: proyecto recién creado, sin entradas en logbook

## Prioridades

`alta` 🔴 · `media` 🔶 · `baja` 🔹

---

## Fechas — lenguaje natural

Todos los `--date`, `--from`, `--to` aceptan:

`today/hoy` · `yesterday/ayer` · `tomorrow/mañana` · `this week/esta semana` · `last month/mes pasado` · `next friday/próximo viernes` · `in 5 days/en 5 días` · `last friday of march` · `YYYY-MM-DD` · `YYYY-M-D` (zero-pad automático) · `YYYY-MM` · `YYYY-Wnn`

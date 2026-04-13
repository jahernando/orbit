# Orbit — Chuleta de comandos

## Shell interactivo

```bash
orbit              # entra al shell (sin prefijo orbit en cada comando)
orbit shell        # equivalente explícito
orbit claude       # abre Claude Code en el directorio Orbit
```

Al entrar: `¡Hola! ¡Bienvenido!` + startup (doctor, untracked, commit+push, gsync)
Al salir: `exit`/`quit` (directo) o `end` (ofrece commit+push antes de salir)

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
orbit ev add  <project> "<text>" --date DATE [--end DATE] [--end-time HH:MM] [--time HH:MM|HH:MM-HH:MM] [--recur FREQ] [--until DATE] [--ring WHEN] [--desc DESC]
orbit ev drop [<project>] ["<text>"] [--force] [-o] [-s]
orbit ev edit [<project>] ["<text>"] [--text "<new>"] [--date DATE] [--end DATE|none] [--end-time HH:MM] [--time HH:MM|HH:MM-HH:MM|none] [--recur FREQ|none] [--until DATE|none] [--ring WHEN|none] [--desc DESC|none]
```

- `--time`: hora del evento. `HH:MM` (solo inicio, 1h por defecto) o `HH:MM-HH:MM` (inicio-fin)
- `--end-time HH:MM`: hora de fin separada (se combina con `--time` → `HH:MM-HH:MM`). Si no hay `--time`, usa 09:00 como inicio
- `--end` / `--end-date`: fecha de fin para eventos multi-día
- Sin `--time`: evento de día completo
- `drop` en evento recurrente: pregunta si quitar solo esta ocurrencia o toda la serie; `-o` avanza al próximo, `-s` elimina la serie (sin prompt); `--force` avanza al próximo (seguro por defecto)
- `drop` pide confirmación (defecto **No**); `--force` la omite
- `--desc`: descripción (enlaces, notas). Se guarda como líneas indentadas en agenda.md y se propaga a Google Calendar/Tasks. No se muestra en `ls`/`agenda` — solo en el fichero. Aplica también a `task` y `ms`

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
orbit hl add  <project> "<text>" [<file|url>] --type TYPE [--deliver] [--date [FECHA]]
orbit hl drop [<project>] ["<text>"] [--type TYPE] [--force]
orbit hl edit [<project>] ["<text>"] [--text "<new>"] [--link URL] [--type TYPE] [--editor E]
```

- `<file|url>`: argumento posicional opcional. Si es URL, enlaza el texto. Si es fichero local, enlaza y pregunta si quieres entregarlo a cloud
- `--deliver`: entrega el fichero directamente a cloud sin preguntar (copia a `hls/`, sin prefijo de fecha)
- `--type`: `refs` (📎) · `results` (📊) · `decisions` (📌) · `ideas` (💡) · `evals` (🔍) · `plans` (🗓️)
- `--date`: añade fecha al final del texto — `--date` (hoy), `--date tomorrow`, `--date 2026-04-15`
- `drop` pide confirmación (defecto **No**); `--force` la omite

---

## note — notas de proyecto

```bash
orbit note <project> "<title>" [<file>]          # crear nota (atajo sin subcomando)
orbit note create <project> "<title>" [--file F] [--no-open] [--editor E]
orbit note import <project> "<title>" <file>     # importar .md existente (log + clip)
orbit note open   <project> [<name>] [--date D] [--editor E]
orbit note list   <project> [--open [EDITOR]]
orbit note drop   <project> [<file>] [--force]
```

- **import**: importa un fichero `.md` existente en `notes/`, registra en logbook y copia el enlace markdown al portapapeles
  - Acepta los mismos flags que `create` (`--no-date`, `--entry`, `--hl`, `--no-open`)
- **create**: crea nota en `notes/` a partir de plantilla y registra en logbook
  - Nombre del fichero: `YYYY-MM-DD_título.md` (con fecha de hoy como prefijo)
  - Contenido: título + línea `*YYYY-MM-DD — [proyecto](link)*`
  - Con `--hl <tipo>`: registra en highlights en vez de logbook, sin prefijo de fecha en el nombre
  - Con `--no-date`: sin prefijo de fecha en el nombre, sigue registrando en logbook
  - Con `<file>`: importa un `.md` existente en vez de crear desde plantilla
  - Pregunta: `¿Añadir <fichero> a git? [S/n]`
- **open**: abre nota existente o la crea si no existe
  - `--date D`: genera nombre por fecha (YYYY-MM-DD, YYYY-Wnn, YYYY-MM)
  - Sin nombre ni fecha: selector interactivo
- **drop**: pide confirmación (defecto **No**); `--force` la omite

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
orbit log <project> "<título>" [<file|url>] [--entry TIPO] [--deliver] [--note NOTA] [--date D] [--open [EDITOR]]

orbit search [query] [--project P...] [--entry TIPO] [--date D] [--from D] [--to D]
             [--in logbook|highlights|agenda] [--any] [--notes]
             [--limit N] [--open [EDITOR]]
```

- `<file|url>`: argumento posicional opcional. Si es URL, enlaza el título. Si es fichero local, enlaza al fichero y pregunta si quieres entregarlo a cloud
Muchos comandos soportan `--append proyecto:nota` para añadir su salida a una nota:

```bash
orbit report today --append catedra:calibracion     # report del día → nota
orbit agenda --append mission:W12                    # agenda → nota semanal
orbit view catedra --append catedra:estado           # vista del proyecto → nota
orbit search "algo" --append catedra:busqueda        # resultados de búsqueda → nota
```
- `--deliver`: entrega el fichero directamente a cloud sin preguntar (copia a `logs/` con prefijo `YYYY-MM-DD_`)
- Si el fichero es imagen (png, jpg, svg...), se inserta `![título](link)` en la línea siguiente de la entrada
- `--entry`: filtra por tipo de entrada (`idea` · `referencia` · `apunte` · `problema` · `solucion` · `resultado` · `decision` · `evaluacion` · `plan`)
- `--in`: busca en un tipo de fichero específico (por defecto logbook)

---

## crono — cronogramas

Cronogramas: tareas anidadas con dependencias y duración temporal. Se almacenan en `cronos/crono-<nombre>.md` dentro del proyecto, enlazados desde `## 📊 Cronogramas` en agenda.md.

```bash
orbit crono add   <project> "<name>"                    # crear cronograma (abre en editor)
orbit crono show  <project> "<name>" [--open]           # mostrar con fechas calculadas
orbit crono check <project> "<name>"                    # validar (doctor)
orbit crono list  <project> [--open]                    # listar cronogramas del proyecto
orbit crono done  <project> "<name>" <index>            # marcar tarea como completada
```

### Formato del fichero

```markdown
# Crono: nombre del cronograma

- [ ] 1. Fase 1 título
  - [ ] 1.1 Subtarea | 2026-03-20 | 2W
  - [ ] 1.2 Otra subtarea | after:1.1 | 3d
- [ ] 2. Fase 2
  - [ ] 2.1 Siguiente | after:1 | 1W
```

- Inicio: fecha ISO (`2026-03-20`), semana ISO (`2026-W12`), semana+día (`2026-W12-wed`), o dependencia (`after:<índice>`)
- Duración: `Nd` (días), `NW` (semanas)
- Tareas padre calculan su inicio/fin de las hijas
- `check` valida: índices únicos, dependencias válidas, sin ciclos, hojas con inicio+duración

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
- `--open` escribe a `agenda.md` (fijable en Obsidian) — formato tabla markdown
- Tareas vencidas se agrupan en el día de hoy con la fecha original: `(📅2026-03-22) ⚠️`
- Compatible con `--log`

---

## panel — dashboard dinámico

```bash
orbit panel                                        # panel del día
orbit panel week                                   # panel de la semana
orbit panel month                                  # panel del mes
orbit panel --from monday --to friday              # rango personalizado
orbit panel --open                                 # abre en editor (panel.md)
orbit panel --no-fed                               # sin proyectos federados
orbit panel --append mission:W12                   # añade a una nota
```

Dashboard con tres secciones (formato tabla markdown):

- **Prioridad**: tabla con 🔴 alta, 🔶 urgente (citas/vencidas en periodo), 🏁 hitos del mes
- **Agenda**: tabla por día con columnas: tipo, hora, descripción, proyecto (con link)
- **Actividad**: entradas de logbook del periodo por proyecto

`--open` escribe a `panel.md` (fijable en Obsidian). `--no-fed` excluye federados.

Proyectos locales se muestran como links a `project.md`; federados con emoji del workspace (🌿).

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

> Orbit gestiona estas conexiones automáticamente (al arrancar, al operar sobre citas, al commitear). Los comandos siguientes permiten interactuar manualmente.

### Git — versionado

```bash
orbit commit ["<mensaje>"]
```

- Sin mensaje: pide interactivamente; intro vacío → genera mensaje automático
- Muestra ficheros modificados y pide `[S/n]` antes de ejecutar
- Ejecuta doctor pre-check: valida agendas/logbooks antes de commitear
- Ejecuta reconciliación gsync: detecta renombramientos de citas en el markdown y migra IDs de Google
- Push al remoto: `orbit_push` desde la terminal del sistema (fuera de la shell)

### Google Calendar/Tasks — gsync

```bash
orbit gsync                        # sincroniza tareas/hitos/eventos con Google
orbit gsync --dry-run              # preview sin escribir
orbit gsync --list-calendars       # muestra calendarios disponibles
orbit gsync --migrate-recurring    # migrar eventos recurrentes viejos a RRULE
```

- Tareas e hitos → Google Tasks (una lista por tipo: `🚀[📚Docencia]`, `🚀[🌀Investigacion]`, etc.)
- Eventos → Google Calendar (un calendario por tipo, configurable en `google-sync.json`)
- Eventos recurrentes → serie RRULE en Google Calendar (una sola entrada en agenda.md, serie completa en Google)
- Títulos en Google: `🚀[proyecto] descripción` (eventos y tareas)
- Sincronización automática: al iniciar la shell + al añadir/completar/editar/eliminar items
- IDs de sincronización en `.gsync-ids.json` por proyecto (no en agenda.md)
- Items recurrentes usan clave estable (`desc::🔄recur`) para que al avanzar la fecha no se dupliquen en Google
- Items sincronizados muestran `[G]` en agenda.md

### Cloud (OneDrive/Google Drive) — render y deliver

```bash
orbit render                  # renderiza ficheros del último commit
orbit render <project>        # renderiza un proyecto completo
orbit render --full           # renderiza todos los proyectos
orbit deliver <project> <file>   # entrega un fichero al cloud del proyecto
```

- Convierte ficheros `.md` de cada proyecto a `.html` en el directorio cloud
- Genera `index.html` con dashboard de proyectos
- Incluye soporte KaTeX para ecuaciones LaTeX (`$...$` y `$$...$$`)
- Se ejecuta automáticamente en background tras cada `commit`
- `deliver` también disponible como `--deliver` en `log` y `hl add`
- Estructura cloud: `cloud_root/{tipo}/{proyecto}/logs/`, `hls/`
- `cloud_root` se configura en `orbit.json`; cada proyecto tiene un link `[cloud]` en `project.md`

### Mac Reminders — notificaciones

No hay un comando propio — `--ring` es un flag transversal disponible en `task`, `ms`, `ev`:

```bash
orbit task add next-kr "Reunión" --date tomorrow --time 10:00 --ring 30m
```

- Si creas una cita con `--time` sin `--ring`, Orbit pregunta interactivamente (defecto: 5 min antes)
- Al entrar en la shell, se programan las notificaciones del día de todos los workspaces
- Valores: `1d` (1 día antes), `2h`, `30m`, `HH:MM` (hora fija), `YYYY-MM-DD HH:MM`

### Cartero — notificaciones de correo

```bash
orbit mail                     # check manual: muestra no leídos por etiqueta
orbit mail --status            # estado del proceso background
orbit mail --start             # arranca el proceso background
orbit mail --stop              # para el proceso background
```

- Vigila Gmail y/o Slack y avisa de mensajes no leídos
- Indicador en el prompt: `🚀[📬7] >` (suma de todas las fuentes, solo si hay mensajes)
- Notificación macOS cuando llegan mensajes nuevos (solo al subir el conteo, no en cada check)
- Proceso background: se lanza al entrar en la shell, un solo proceso por workspace (PID lock)
- Configuración en `orbit.json`:

```json
"cartero": {
  "gmail": {
    "labels": ["🏠 hogar", "🤗  Eva y familia"],
    "interval": 600
  },
  "slack": {
    "channels": ["general", "alertas"],
    "interval": 600
  }
}
```

- **Gmail**: `labels` = etiquetas a vigilar (nombres exactos de la API, pueden tener emojis). Requiere `credentials.json` + API de Gmail habilitada en Google Cloud Console
- **Slack**: `channels` = canales a vigilar. Requiere token de usuario en `ORBIT_HOME/.slack-token` (una línea, `xoxp-...`)
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

- Registra automáticamente los comandos que modifican estado (log, task, ms, ev, note, commit, hl, project...)
- No registra comandos de solo lectura (agenda, report, view, ls, doctor, search, history, open)
- Fichero: `history.md` en la raíz de Orbit

### doctor — validación de ficheros

```bash
orbit doctor [<project>]        # revisa todos o un proyecto
orbit doctor --fix [<project>]  # revisa y ofrece corregir
```

- Valida logbook (fechas, tipos, emojis), agenda (marcadores, fechas, recurrencia, formato de eventos) y highlights (secciones, formato de items, links)
- Se ejecuta automáticamente al iniciar la shell y antes de cada commit
- Con `--fix`: muestra correcciones disponibles y permite aplicarlas interactivamente

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
3. **Cambios sin commit** — ofrece hacer commit + push (mensaje por defecto: `sync YYYY-MM-DD`)
4. **gsync** en background + **recordatorios** — sincroniza con Google y programa los recordatorios del día (tras commit)
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

- `panel --open` → `panel.md`
- `agenda --open` → `agenda.md`
- El resto → `cmd.md`

Estos ficheros se pueden fijar en Obsidian (pin tab) para tener un dashboard permanente.

Sin especificar editor, se usa el editor por defecto (en orden de prioridad):
1. `ORBIT_EDITOR` (variable de entorno)
2. `"editor"` en `orbit.json` (por workspace)
3. Abridor del sistema (`open` en macOS)

Comandos que lo admiten: `ls` · `view` · `search` · `report` · `agenda` · `panel` · `help` · `history` · `crono show/list` · `note list`

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

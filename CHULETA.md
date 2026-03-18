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
orbit ev add  <project> "<text>" --date DATE [--end DATE] [--time HH:MM|HH:MM-HH:MM] [--recur FREQ] [--until DATE] [--ring WHEN] [--desc DESC]
orbit ev drop [<project>] ["<text>"] [--force] [-o] [-s]
orbit ev edit [<project>] ["<text>"] [--text "<new>"] [--date DATE] [--end DATE|none] [--time HH:MM|HH:MM-HH:MM|none] [--recur FREQ|none] [--until DATE|none] [--ring WHEN|none] [--desc DESC|none]
orbit ev list [<project>] [--from DATE] [--to DATE]
```

- `--time`: hora del evento. `HH:MM` (solo inicio, 1h por defecto) o `HH:MM-HH:MM` (inicio-fin)
- Sin `--time`: evento de día completo
- `drop` en evento recurrente: pregunta si quitar solo esta ocurrencia o toda la serie; `-o` avanza al próximo, `-s` elimina la serie (sin prompt); `--force` avanza al próximo (seguro por defecto)
- `drop` pide confirmación (defecto **No**); `--force` la omite
- `--desc`: descripción (enlaces, notas). Se guarda como líneas indentadas en agenda.md y se propaga a Google Calendar/Tasks. No se muestra en `ls`/`agenda` — solo en el fichero. Aplica también a `task` y `ms`

---

## reminder (rem) — recordatorios

```bash
orbit reminder add  <project> "<text>" --date DATE --time HH:MM [--recur FREQ] [--until DATE] [--desc DESC]
orbit reminder drop [<project>] ["<text>"] [--force] [-o] [-s]
orbit reminder edit [<project>] ["<text>"] [--text "<new>"] [--date DATE|none] [--time HH:MM|none] [--recur FREQ|none] [--until DATE|none] [--desc DESC|none]
orbit reminder list [<project>]
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
orbit hl edit [<project>] ["<text>"] [--text "<new>"] [--link URL] [--type TYPE]
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
orbit note open   <project> [<name>] [--date D] [--editor E]
orbit note list   <project> [--open] [--editor E]
orbit note drop   <project> [<file>] [--force]
```

- Sin `<file>`: crea `título_con_guiones.md` en `notes/` a partir de plantilla
- Al crear, pregunta: `¿Añadir <fichero> a git? [S/n]`
- `open`: abre nota existente o la crea si no existe; `--date` genera nombre por fecha (YYYY-MM-DD, YYYY-Wnn, YYYY-MM); sin nombre ni fecha: selector interactivo
- `drop` pide confirmación (defecto **No**); `--force` la omite

---

## view / open — navegar proyectos

```bash
orbit view  [<project>] [--open] [--editor E]
orbit open  <project> [logbook|highlights|agenda|notes|project] [--editor E] [--dir]
```

- `view` sin proyecto: muestra lista para selección interactiva
- `view <project>`: resumen en terminal (estado, tareas, hitos, próximos eventos, entradas recientes)
- `view <project> --open`: genera `cmd.md` y lo abre en el editor
- `open --dir`: abre el directorio del proyecto en Finder

---

## log y search

```bash
orbit log <project> "<título>" [<file|url>] [--entry TIPO] [--deliver] [--date D] [--open] [--editor E]

orbit search [query] [--project P...] [--tag TAG] [--date D] [--from D] [--to D]
             [--in logbook|highlights|agenda] [--any] [--notes]
             [--limit N] [--open] [--editor E]
```

- `<file|url>`: argumento posicional opcional. Si es URL, enlaza el título. Si es fichero local, enlaza al fichero y pregunta si quieres entregarlo a cloud
- `--deliver`: entrega el fichero directamente a cloud sin preguntar (copia a `logs/` con prefijo `YYYY-MM-DD_`)
- Si el fichero es imagen (png, jpg, svg...), se inserta `![título](link)` en la línea siguiente de la entrada
- `--tag`: filtra por hashtag (`idea` · `referencia` · `apunte` · `problema` · `solucion` · `resultado` · `decision` · `evaluacion` · `plan`)
- `--in`: busca en un tipo de fichero específico (por defecto logbook)

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

## deliver — entregar ficheros a la nube

```bash
orbit deliver <project> <file>
```

- Copia el fichero al directorio cloud del proyecto y deja la ruta en el portapapeles
- Para entregar un fichero y crear entrada de logbook o highlight, usa `--deliver` en `log` o `hl add`

### Estructura cloud

```
cloud_root/                         ← definido en orbit.json ("cloud_root")
  {type_emoji}{type_name}/          ← ej. ⚙️gestion
    {project_dir}/                  ← ej. ⚙️catedra
      logs/                         ← ficheros entregados desde log (con prefijo YYYY-MM-DD_)
      hls/                          ← ficheros entregados desde hl
      ...                           ← otros ficheros manuales
```

### Configuracion cloud en orbit.json

Cada workspace necesita `cloud_root` en su `orbit.json`:

```json
{
  "space": "orbit-ws",
  "emoji": "🚀",
  "cloud_root": "~/Library/CloudStorage/OneDrive-.../🚀orbit-ws",
  "types": { ... }
}
```

El directorio cloud raiz deberia llamarse `{emoji}{space}` (ej. `🚀orbit-ws`, `🌿orbit-ps`) para identificarlo visualmente en el servicio de nube.

Cada proyecto tiene un link `[cloud]` en su `project.md` que apunta a su directorio en cloud.

---

## commit

```bash
orbit commit ["<mensaje>"]
```

- Sin mensaje: pide interactivamente; intro vacío → genera mensaje automático
- Muestra ficheros modificados y pide `[S/n]` antes de ejecutar

---

## ls — listados

```bash
orbit ls                              # lista proyectos (por defecto)
orbit ls projects [--status S] [--type T] [--sort type|status|priority]
orbit ls tasks    [project...] [--status pending|done|all] [--date D] [--dated]
orbit ls ms       [project...] [--status pending|done|all] [--dated]
orbit ls ev         [project]    [--from D] [--to D]
orbit ls reminders  [project]    # recordatorios activos (alias: ls rem)
orbit ls hl        [project]    [--type T]
orbit ls files    [project]    # ficheros md del proyecto con estado git
orbit ls notes    [project]    # notas con estado git
```

Indicadores git en `files` y `notes`: `✓` tracked · `M` modified · `+` untracked · `✗` ignored

---

## agenda — vista temporal

```bash
orbit agenda [project...] [--date D] [--from D] [--to D] [--calendar] [--summary] [--dated] [--order project|date] [--open] [--editor E]
```

- Sin fecha: muestra el día de hoy (tareas pendientes, vencidas, eventos, hitos)
- `--date 2026-03`: todo el mes
- `--from monday --to friday`: rango
- `--calendar`: vista de calendario con colores (máx. 3 meses)
  - Azul: número de semana
  - Amarillo: tarea
  - Cian: evento
  - Magenta: hito
  - Rojo: vencida
  - Invertido: hoy
- `--summary`: tabla resumen por proyecto (primera/última fecha, conteo de tareas/hitos/eventos/sin fecha)
- `--dated`: solo muestra tareas/hitos que tienen fecha asignada
- `--order project`: agrupa por proyecto (por defecto)
- `--order date`: agrupa por día, con horas como sub-cabeceras; sin-fecha al final
- Compatible con `--open` y `--log`

---

## report — informe de actividad

```bash
orbit report [project...] [--date D] [--from D] [--to D] [--open] [--editor E]
orbit report --summary [logbook|agenda|highlights|all] [--date D] [--from D] [--to D]
```

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

## gsync — sincronización con Google

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

---

## history — historial de comandos

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

---

## claude — asistente integrado

```bash
orbit claude "¿cómo creo una tarea recurrente?"
orbit claude "quiero ver la agenda de la semana"
```

- Envía la pregunta a Claude con la CHULETA como contexto
- Si un comando falla y hay API key, sugiere alternativas automáticamente
- Requiere: `pip install anthropic` + `ANTHROPIC_API_KEY` env var
- Usa Haiku (rápido y económico)

---

## doctor — validación de ficheros

```bash
orbit doctor [<project>]        # revisa todos o un proyecto
orbit doctor --fix [<project>]  # revisa y ofrece corregir
```

- Valida logbook (fechas, tipos, emojis), agenda (marcadores, fechas, recurrencia, formato de eventos) y highlights (secciones, formato de items, links)
- Se ejecuta automáticamente en segundo plano al iniciar la shell
- Con `--fix`: muestra correcciones disponibles y permite aplicarlas interactivamente

---

## archive — archivado de entradas antiguas

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

---

## Startup — al iniciar la shell

Al entrar en `orbit shell`:

1. **Doctor** — valida la integridad de logbook, agenda y highlights; ofrece corregir errores
2. **Ficheros sin trackear** en `🚀proyectos/` — ofrece añadirlos a git
3. **Cambios sin commit** — ofrece hacer commit + push (mensaje por defecto: `sync YYYY-MM-DD`)
4. **gsync** en background + **recordatorios** — sincroniza con Google y programa los recordatorios del día (tras commit)

---

## help — documentación

```bash
orbit help            # muestra CHULETA.md en terminal (paginado)
orbit help chuleta    # abre CHULETA.md en el editor
orbit help about      # abre README.md en el editor
orbit help tutorial   # abre TUTORIAL.md en el editor
```

---

## --open — abrir resultado en editor

Los comandos de listado aceptan `--open [--editor E]`:
capturan el output, lo escriben en `cmd.md` y abren el fichero en el editor.

El editor se configura con `export ORBIT_EDITOR=typora` (o el que prefieras).
Sin variable, usa el abridor del sistema (`open` en macOS, `xdg-open` en Linux).

Comandos que lo admiten: `ls` · `view` · `search` · `report`

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

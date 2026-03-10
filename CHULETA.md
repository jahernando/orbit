# Orbit — Chuleta de comandos

## Shell interactivo

```bash
orbit              # entra al shell (sin prefijo orbit en cada comando)
orbit shell        # equivalente explícito
orbit claude       # abre Claude Code en el directorio Orbit
```

Al entrar: `¡Hola! ¡Bienvenido!`
Al salir: `¡Hasta pronto!`

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
orbit task add    <project> "<text>" [--date DATE] [--recur FREQ] [--until DATE] [--ring WHEN]
orbit task done   [<project>] ["<text>"]
orbit task drop   [<project>] ["<text>"] [--force]
orbit task edit   [<project>] ["<text>"] [--text "<new>"] [--date DATE|none] [--recur FREQ|none] [--until DATE|none] [--ring WHEN|none]
```

- `done` y `drop`: interactivos si no se especifica texto; `drop` pide confirmación
- `done` en tarea recurrente: avanza a la siguiente ocurrencia automáticamente
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
| `HH:MM` | Hoy (o en la fecha de la tarea) a esa hora |
| `YYYY-MM-DD HH:MM` | Fecha/hora exacta |
| `none` | Eliminar ring (solo en `edit`) |

---

## ms — hitos

```bash
orbit ms add    <project> "<text>" [--date DATE] [--recur FREQ] [--until DATE] [--ring WHEN]
orbit ms done   [<project>] ["<text>"]
orbit ms drop   [<project>] ["<text>"] [--force]
orbit ms edit   [<project>] ["<text>"] [--text "<new>"] [--date DATE|none] [--recur FREQ|none] [--until DATE|none] [--ring WHEN|none]
```

---

## ev — eventos

```bash
orbit ev add  <project> "<text>" --date DATE [--end DATE] [--recur FREQ] [--until DATE] [--ring WHEN]
orbit ev drop [<project>] ["<text>"] [--force]
orbit ev edit [<project>] ["<text>"] [--text "<new>"] [--date DATE] [--end DATE|none] [--recur FREQ|none] [--until DATE|none] [--ring WHEN|none]
orbit ev list [<project>] [--from DATE] [--to DATE]
```

- `drop` pide confirmación (defecto **No**); `--force` la omite

---

## hl — highlights

```bash
orbit hl add  <project> "<text>" --type TYPE [--link URL]
orbit hl drop [<project>] ["<text>"] [--type TYPE] [--force]
orbit hl edit [<project>] ["<text>"] [--text "<new>"] [--link URL] [--type TYPE]
```

- `--type`: `refs` · `results` · `decisions` · `ideas` · `evals`
- `drop` pide confirmación (defecto **No**); `--force` la omite

---

## note — notas de proyecto

```bash
orbit note <project> "<title>" [<file>]          # crear nota (atajo sin subcomando)
orbit note create <project> "<title>" [--file F] [--no-open] [--editor E]
orbit note list   <project> [--open] [--editor E]
orbit note drop   <project> [<file>] [--force]
```

- Sin `<file>`: crea `título_con_guiones.md` en `notes/` a partir de plantilla
- Al crear, pregunta: `¿Añadir <fichero> a git? [S/n]`
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
orbit log <project> <msg> [--entry TIPO] [--path RUTA] [--date D] [--open] [--editor E]

orbit search [query] [--project P...] [--tag TAG] [--date D] [--from D] [--to D]
             [--in logbook|highlights|agenda] [--any] [--notes]
             [--limit N] [--open] [--editor E]
```

`--tag`: filtra por hashtag (`idea` · `referencia` · `tarea` · `problema` · `resultado` · `apunte` · `decision`)
`--in`: busca en un tipo de fichero específico (por defecto logbook)

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
orbit ls tasks    [project...] [--status pending|done|all] [--date D]
orbit ls ms       [project...] [--status pending|done|all]
orbit ls ev       [project]    [--from D] [--to D]
orbit ls hl       [project]    [--type T]
orbit ls files    [project]    # ficheros md del proyecto con estado git
orbit ls notes    [project]    # notas con estado git
```

Indicadores git en `files` y `notes`: `✓` tracked · `M` modified · `+` untracked · `✗` ignored

---

## agenda — vista temporal

```bash
orbit agenda [project...] [--date D] [--from D] [--to D] [--calendar] [--open] [--editor E]
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
- Compatible con `--open` y `--log`

---

## report — informe de actividad

```bash
orbit report [project...] [--date D] [--from D] [--to D] [--open] [--editor E]
```

- Sin proyecto: muestra informe de todos los proyectos activos
- Con proyecto(s): informe solo de esos proyectos
- Sin fechas: últimos 30 días
- Muestra: entradas de logbook, highlights, tareas completadas/pendientes/vencidas, hitos, eventos
- Compatible con `--log`: redirige el informe al logbook de otro proyecto

---

## gsync — sincronización con Google

```bash
orbit gsync                    # sincroniza tareas/hitos/eventos con Google
orbit gsync --dry-run          # preview sin escribir
orbit gsync --list-calendars   # muestra calendarios disponibles
```

- Tareas e hitos → Google Tasks (una lista por tipo de proyecto)
- Eventos → Google Calendar (un calendario por tipo, configurable en `google-sync.json`)
- Sincronización automática: al iniciar la shell + al añadir/completar/editar/eliminar items
- IDs de sincronización almacenados en agenda.md: `[gtask:id]` y `[gcal:id]`

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

## clean — limpieza de entradas antiguas

```bash
orbit clean [<project>] [--months N] [--dry-run]
```

- Sin proyecto: limpia todos los proyectos
- `--months N`: antigüedad mínima para eliminar (defecto: 6 meses)
- `--dry-run`: muestra qué se eliminaría sin borrar nada

Qué se limpia:
1. Entradas de logbook con fecha anterior al corte
2. Eventos pasados en agenda.md
3. Notas en `notes/` no modificadas en N meses (interactivo)

Los datos eliminados son recuperables con `git log -p -- <fichero>`.

---

## Startup — al iniciar la shell

Al entrar en `orbit shell`:

1. **Doctor** — valida la integridad de logbook, agenda y highlights; ofrece corregir errores
2. **gsync** + **recordatorios** — sincroniza con Google y programa los recordatorios del día (solo tras validar datos)
3. **Ficheros sin trackear** en `🚀proyectos/` — ofrece añadirlos a git
4. **Cambios sin commit** — ofrece hacer commit + push (mensaje por defecto: `sync YYYY-MM-DD`)

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

`today/hoy` · `yesterday/ayer` · `tomorrow/mañana` · `this week/esta semana` · `last month/mes pasado` · `next friday/próximo viernes` · `in 5 days/en 5 días` · `last friday of march` · `YYYY-MM-DD` · `YYYY-MM` · `YYYY-Wnn`

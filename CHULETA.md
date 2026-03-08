# Orbit — Chuleta de comandos

## Shell interactivo

```bash
orbit              # entra al shell (sin prefijo orbit en cada comando)
orbit shell        # equivalente explícito
orbit claude       # abre Claude Code en el directorio Orbit
```

---

## create — crear cosas nuevas

```bash
orbit create project  --name NOMBRE --type TIPO [--priority alta|media|baja]
orbit create import   --file FICHERO.enex --project PROYECTO
```

Las notas de día, semana y mes se crean automáticamente al entrar en el shell de Orbit.

---

## add — añadir items a un proyecto

```bash
orbit add task     [project] <desc>   [--date D] [--time HH:MM] [--ring] [--recur RULE] [--open]
orbit add ref      <project> <título> [--url URL] [--file PATH] [--sync] [--open]
orbit add result   <project> <título> [--url URL] [--file PATH] [--sync] [--open]
orbit add decision <project> <título> [--url URL] [--file PATH] [--sync] [--open]
```

- Sin proyecto → va a **mission** por defecto
- `--date today` → también se copia al diario del día
- `--ring` → tarea con alarma; si omites `--time` se pide en el prompt (defecto 09:00)
- `--date today` + `--ring` → también se programa en Reminders.app
- `--recur` acepta: `daily/diario` · `weekly/semanal` · `monthly/mensual` · `yearly/anual` · `weekdays/laborables` · `every:Nd` · `every:Nw`
- `--sync` → `git add -f` sobre el fichero copiado

---

## change — modificar cosas existentes

```bash
orbit change task schedule <project> <desc> --date D [--time HH:MM] [--recur RULE] [--open]
orbit change task close    <project> <desc> [--date D] [--open]
```

`change task close` con `@recur` avanza la fecha en vez de cerrar (se pide confirmación interactiva).

---

## list — listar proyectos y secciones

```bash
orbit list projects  [--type T] [--status S] [--priority P] [--output F] [--open]
orbit list tasks     [--project P] [--type T] [--status S] [--priority P] [--date D] [--keyword K] [--ring]
```

- `--ring` → muestra solo tareas con alarma (⏰)

---

## report — informes

Los reportes de día, semana y mes se generan automáticamente al salir del shell.

```bash
orbit report stats  [--date D] [--from D] [--to D] [--project P] [--type T] [--priority P] [--output F] [--open]
```

---

## log y search

```bash
orbit log [project] <msg> [--entry TIPO] [--path RUTA] [--date D] [--open] [--editor E]
# Sin proyecto → anota en el diario de hoy

orbit search [query] [--project P...] [--entry TIPO] [--date D] [--from D] [--to D]
             [--type T] [--status S] [--priority P] [--any] [--diario] [--limit N]
             [--output F] [--open] [--editor E]
```

`--entry`: `idea` · `referencia` · `tarea` · `problema` · `resultado` · `apunte` · `decision` · `evento`

---

## open

```bash
orbit open [target] [--log] [--editor E]
orbit open [target] --terminal [--section S] [--entry TIPO] [--log] [--output F]
# target: nombre-proyecto · YYYY-MM-DD · YYYY-Wnn · YYYY-MM  (defecto: hoy)
```

---

## calendar — calendario visual

```bash
orbit calendar week  [--date D] [--no-open] [--editor E]
orbit calendar month [--date D] [--no-open] [--editor E]
orbit calendar year  [--date D] [--no-open] [--editor E]
```

Genera un fichero markdown con tareas (✅) y recordatorios (⏰) del período y lo abre en Typora.
Guardado en `☀️mision-log/calendar-{week,month,year}.md`.

---

## info — documentación

```bash
orbit info chuleta    # abre CHULETA.md en Typora
orbit info about      # abre README.md en Typora
orbit info tutorial   # abre TUTORIAL.md en Typora
orbit info help       # muestra el help completo de orbit
```

---

## Tipos de proyecto

`investigacion` 🌀 · `docencia` 📚 · `gestion` ⚙️ · `formacion` 📖 · `software` 💻 · `personal` 🌿 · `mision` ☀️

## Estados

`inicial` ⬜ · `en marcha` ▶️ · `parado` ⏸️ · `durmiendo` 💤 · `completado` ✅

## Prioridades

`alta` 🟠 · `media` 🟡 · `baja` 🔵

---

## Fechas — lenguaje natural

Todos los `--date`, `--from`, `--to` aceptan:

`today/hoy` · `yesterday/ayer` · `tomorrow/mañana` · `this week/esta semana` · `last month/mes pasado` · `next friday/próximo viernes` · `in 5 days/en 5 días` · `last friday of march` · `YYYY-MM-DD` · `YYYY-MM` · `YYYY-Wnn`

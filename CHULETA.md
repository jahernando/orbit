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
orbit create day      [--date D] [--force] [--focus P...] [--no-open] [--editor E]
orbit create week     [--date D] [--force] [--focus P...] [--no-open] [--editor E]
orbit create month    [--date D] [--force] [--focus P...] [--no-open] [--editor E]
```

`create day` crea la nota mensual y semanal en cascada si no existen, y hereda el foco automáticamente.

---

## add — añadir items a un proyecto

```bash
orbit add task     [project] <desc>   [--date D] [--time HH:MM] [--recur RULE] [--open]
orbit add ring     [project] <desc>    --date D   --time HH:MM  [--recur RULE] [--open]
orbit add ref      <project> <título> [--url URL] [--file PATH] [--sync] [--open]
orbit add result   <project> <título> [--url URL] [--file PATH] [--sync] [--open]
orbit add decision <project> <título> [--url URL] [--file PATH] [--sync] [--open]
```

- Sin proyecto → va a **mission** por defecto
- `--date today` → también se copia al diario del día
- `--date today` en `ring` → también se programa en Reminders.app
- `--recur` acepta: `daily/diario` · `weekly/semanal` · `monthly/mensual` · `yearly/anual` · `weekdays/laborables` · `every:Nd` · `every:Nw`
- `--sync` → `git add -f` sobre el fichero copiado

---

## change — modificar cosas existentes

```bash
# Proyectos
orbit change status   <nuevo_estado>    [project...] [--from-status S] [--from-priority P] [--type T]
orbit change priority <nueva_prioridad> [project...] [--from-status S] [--from-priority P] [--type T]
orbit change type     <nuevo_tipo>      [project...] [--from-status S] [--from-priority P]

# Tareas
orbit change task schedule <project> <desc> --date D [--time HH:MM] [--recur RULE] [--open]
orbit change task close    <project> <desc> [--date D] [--open]

# Recordatorios
orbit change ring schedule <project> <desc> --date D --time HH:MM [--recur RULE] [--open]
orbit change ring close    <project> <desc> [--open]
```

`change task close` con `@recur` avanza la fecha en vez de cerrar.

---

## list — listar proyectos y secciones

```bash
orbit list projects  [--type T] [--status S] [--priority P] [--output F] [--open]
orbit list tasks     [--project P] [--type T] [--status S] [--priority P] [--date D] [--keyword K]
orbit list rings     [project] [--output F] [--open]
orbit list refs      [project] [--output F] [--open]
orbit list results   [project] [--output F] [--open]
orbit list decisions [project] [--output F] [--open]
```

---

## report — informes

```bash
orbit report day    [--date D] [--inject] [--output F] [--open] [--editor E]
orbit report week   [--date D] [--inject] [--output F] [--open] [--editor E]
orbit report month  [--date D] [--inject] [--apply]   [--output F] [--open] [--editor E]
orbit report stats  [--date D] [--from D] [--to D] [--project P] [--type T] [--priority P] [--output F] [--open]
orbit report status [--date D] [--apply] [--output F] [--open] [--editor E]
```

- `report week/month` guarda automáticamente una entrada en el logbook de **mission**
- `--inject` → inyecta el reporte en la nota del período
- `--apply`  → aplica cambios de estado/prioridad a los proyectos
- `report status` → tabla proyecto · act-60 · act-30 · estado · prioridad → propuesta

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

## open y calendar

```bash
orbit open [target] [--log] [--editor E]
orbit open [target] --terminal [--section S] [--entry TIPO] [--log] [--output F]
# target: nombre-proyecto · YYYY-MM-DD · YYYY-Wnn · YYYY-MM  (defecto: hoy)

orbit calendar [--date D] [--dry-run]
```

---

## Tipos de proyecto

`investigacion` 🌀 · `docencia` 📚 · `gestion` ⚙️ · `formacion` 📖 · `software` 💻 · `personal` 🌿 · `mision` ☀️

## Estados

`inicial` ⬜ · `en marcha` ▶️ · `parado` ⏸️ · `esperando` ⏳ · `durmiendo` 💤 · `completado` ✅

## Prioridades

`alta` 🟠 · `media` 🟡 · `baja` 🔵

---

## Fechas — lenguaje natural

Todos los `--date`, `--from`, `--to` aceptan:

`today/hoy` · `yesterday/ayer` · `tomorrow/mañana` · `this week/esta semana` · `last month/mes pasado` · `next friday/próximo viernes` · `in 5 days/en 5 días` · `last friday of march` · `YYYY-MM-DD` · `YYYY-MM` · `YYYY-Wnn`

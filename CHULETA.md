# Orbit — Chuleta de comandos

## Logbook

```bash
# Sin proyecto → anota en el diario de hoy
orbit log "<mensaje>" [--type TIPO] [--date YYYY-MM-DD] [--open] [--editor EDITOR]

# Con proyecto → anota en el logbook del proyecto
orbit log <proyecto> "<mensaje>" [--type TIPO] [--path RUTA] [--date YYYY-MM-DD] [--open] [--editor EDITOR]
```

Tipos: `apunte` `idea` `referencia` `tarea` `problema` `resultado` `decision` `evento`

## Búsqueda

```bash
orbit search ["keyword"] [--project P [P...]] [--tag TIPO] [--date YYYY-MM | YYYY-MM-DD]
             [--from YYYY-MM-DD] [--to YYYY-MM-DD] [--any] [--diario] [--limit N]
             [--type T] [--status S] [--priority P]
             [--output FILE] [--open] [--editor E]
```

- Sin `--tag` → busca en logbooks **y** notas de proyecto
- Con `--tag` → busca solo en logbooks con ese tag
- Sin `--project` → busca en todos los proyectos
- `--any` → lógica OR entre palabras clave (por defecto: AND)
- `--diario` → incluye también diario, semanal y mensual de mision-log
- `--from`/`--to` → filtra por rango de fechas (YYYY-MM-DD)
- `--limit N` → limita el número de resultados
- `--open` → guarda en `☀️mision-log/search.md` y abre en editor

## Abrir notas

```bash
orbit open [<target>] [--log] [--editor EDITOR]   # por defecto: diario de hoy en Typora
orbit view [<target>] [--section S] [--entrada TIPO] [--log] [--output FILE]
```

`<target>`: nombre de proyecto · `YYYY-MM-DD` · `YYYY-Wnn` · `YYYY-MM`

Editores: `typora` (defecto) · `glow` · `code` · cualquier comando

## Tareas

```bash
orbit tasks [--project P] [--type T] [--status S] [--priority P] [--date D] [--output FILE]
orbit task open     [<proyecto>] "<tarea>" [--date YYYY-MM-DD] [--open] [--editor E]
orbit task schedule [<proyecto>] "<tarea>" --date YYYY-MM-DD  [--open] [--editor E]
orbit task close    [<proyecto>] "<tarea>" [--date YYYY-MM-DD] [--open] [--editor E]
```

## Planificación

```bash
orbit day   [--date YYYY-MM-DD] [--force] [--focus P...] [--no-open] [--editor E]
orbit week  [--date YYYY-MM-DD] [--force] [--focus P...] [--no-open] [--editor E]
orbit month [--date YYYY-MM]    [--force] [--focus P...] [--no-open] [--editor E]
```

`day/week/month` abren la nota automáticamente al crearla. Usa `--no-open` para suprimirlo.

## Reports

```bash
orbit report day    [--date D] [--inject] [--output FILE] [--open] [--editor E]
orbit report week   [--date D] [--inject] [--output FILE] [--open] [--editor E]
orbit report month  [--date D] [--inject] [--apply] [--output FILE] [--open] [--editor E]
orbit report stats  [--date D] [--from D] [--to D]
                    [--project P] [--type T] [--priority P]
                    [--output FILE] [--open] [--editor E]
orbit report review [--date D] [--inject] [--apply] [--output FILE] [--open] [--editor E]
```

`--date` acepta lenguaje natural: `today` · `yesterday` · `this week` · `last month` · `next friday` · `in 5 days` · `last friday of march` · y sus equivalentes en español.

- `--inject` → inyecta el reporte en la sección correspondiente de la nota del período
- `--apply`  → aplica cambios de estado/prioridad a los proyectos (month/review)
- `--open`   → abre la nota del período en editor tras generar el reporte

## Google Calendar

```bash
orbit calendar [--date YYYY-MM-DD] [--dry-run]
```

Requiere `credentials.json` en el directorio Orbit.
En la descripción del evento en Google: `proyecto: nombre-proyecto`

## Proyectos

```bash
orbit project create --name NOMBRE --type TIPO [--priority P]
orbit project import --file FICHERO.enex --project PROYECTO

# Cambiar estado/prioridad — un proyecto, varios, o por filtro
orbit project update [<proyecto>...] [--status NUEVO] [--priority NUEVO]
                     [--type T] [--from-status S] [--from-priority P]
```

Tipos de proyecto: `investigacion` `docencia` `gestion` `formacion` `software` `personal`

Estados: `inicial` `en marcha` `parado` `esperando` `durmiendo` `completado`

Prioridades: `alta` `media` `baja`

## Estructura de ficheros

```
🚀proyectos/
└── {emoji}nombre/
    ├── {emoji}Nombre.md     ← índice: objetivo, tareas, referencias
    └── 📓Nombre.md          ← logbook cronológico

☀️mision-log/
├── diario/   YYYY-MM-DD.md
├── semanal/  YYYY-Wnn.md
└── mensual/  YYYY-MM.md
```

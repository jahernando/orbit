# Orbit — Chuleta de comandos

## Logbook

```bash
# Sin proyecto → anota en el diario de hoy
orbit log "<mensaje>" [--type TIPO] [--date YYYY-MM-DD] [--open] [--editor EDITOR]

# Con proyecto → anota en el logbook del proyecto
orbit log <proyecto> "<mensaje>" [--type TIPO] [--path RUTA] [--date YYYY-MM-DD] [--open] [--editor EDITOR]

# Listar entradas
orbit list <proyecto> [--type TIPO...] [--date YYYY-MM o YYYY-MM-DD] [--output FILE]
```

Tipos: `apunte` `idea` `referencia` `tarea` `problema` `resultado` `decision` `evento`

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
orbit report day   [--date YYYY-MM-DD] [--inject]
orbit report week  [--date YYYY-MM-DD] [--inject]
orbit report month [--date YYYY-MM]    [--output FILE]
```

## Actividad y revisión mensual

```bash
orbit activity    [--project P] [--type T] [--priority P] [--period D [D]] [--apply] [--output FILE]
orbit report month [--date YYYY-MM] [--apply] [--output FILE]
```

## Google Calendar

```bash
orbit calendar [--date YYYY-MM-DD] [--dry-run]
```

Requiere `credentials.json` en el directorio Orbit.
En la descripción del evento en Google: `proyecto: nombre-proyecto`

## Proyectos

```bash
orbit project     --name NOMBRE --type TIPO [--priority PRIORIDAD]
orbit update      <proyecto> [--status ESTADO] [--priority PRIORIDAD]
orbit setpriority --priority PRIORIDAD --projects P1 P2 ...
orbit import      --file FICHERO.enex --project PROYECTO
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

# Orbit — Chuleta de comandos

## Logbook

```bash
orbit log    <proyecto> "<mensaje>" [--type TYPE] [--date YYYY-MM-DD]
orbit list   <proyecto> [--type TYPE...] [--date YYYY-MM o YYYY-MM-DD]
orbit logday "<mensaje>" [--type TYPE] [--date YYYY-MM-DD]
```

Tipos: `apunte` `idea` `referencia` `tarea` `problema` `resultado` `decision` `evento`

## Tareas

```bash
orbit tasks [--project P] [--type T] [--status S] [--priority P] [--date D]
```

## Google Calendar

```bash
orbit calendar [--date YYYY-MM-DD] [--dry-run]
```

Requiere `credentials.json` en el directorio Orbit.
En la descripción del evento en Google: `proyecto: nombre-proyecto`

## Actividad y revisión mensual

```bash
orbit activity    [--project P] [--type T] [--priority P] [--period D [D]] [--apply]
orbit monthreport [--month YYYY-MM] [--apply] [--output FILE]
```

## Planificación

```bash
orbit day   [--date YYYY-MM-DD] [--force] [--focus P1 P2...]
orbit week  [--date YYYY-MM-DD] [--force] [--focus P1 P2...]
orbit month [--date YYYY-MM]    [--force] [--focus P1 P2...]
```

## Reports

```bash
orbit report day   [--date YYYY-MM-DD] [--inject]
orbit report week  [--date YYYY-MM-DD] [--inject]
orbit report month [--date YYYY-MM]    [--output FILE]
```

## Proyectos

```bash
orbit project     --name NOMBRE --type TIPO [--priority PRIORIDAD]
orbit import      --file FICHERO.enex --project PROYECTO
orbit tarea open     [<proyecto>] "<tarea>" [--date YYYY-MM-DD]
orbit tarea schedule [<proyecto>] "<tarea>" --date YYYY-MM-DD
orbit tarea close    [<proyecto>] "<tarea>" [--date YYYY-MM-DD]
orbit update      <proyecto> [--status ESTADO] [--priority PRIORIDAD]
orbit setpriority --priority PRIORIDAD --projects P1 P2 ...
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

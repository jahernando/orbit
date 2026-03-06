# Orbit — Chuleta de comandos

## Logbook

```bash
orbit log <proyecto> "<mensaje>" [--type TYPE] [--date YYYY-MM-DD]
orbit list <proyecto> [--type TYPE...] [--date YYYY-MM o YYYY-MM-DD]
```

Tipos: `apunte` `idea` `referencia` `tarea` `problema` `resultado` `decision`

## Tareas

```bash
orbit tasks [--project P] [--type T] [--status S] [--priority P] [--date D]
```

## Actividad y revisión mensual

```bash
orbit activity [--project P] [--type T] [--priority P] [--period D [D]] [--apply]
orbit monthly  [--month YYYY-MM] [--apply] [--output FILE]
```

## Planificación

```bash
orbit day   [--date YYYY-MM-DD]  [--copy YYYY-MM-DD] [--force]
orbit week  [--date YYYY-MM-DD]  [--copy YYYY-Wnn]   [--force]
orbit month [--date YYYY-MM]     [--copy YYYY-MM]    [--force]
```

## Proyectos

```bash
orbit project --name NOMBRE --type TIPO [--priority PRIORIDAD]
orbit import  --file FICHERO.enex --project PROYECTO
orbit update  <proyecto> [--status ESTADO] [--priority PRIORIDAD]
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

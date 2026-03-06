# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

**Orbit** is a personal scientific project management workspace. It is not a software codebase — it is a structured collection of markdown documents for organizing research projects and daily/weekly/monthly planning.

## Structure

```
Orbit/
├── 🚀proyectos/
│   ├── INDEX.md                        ← master table: project, type, status, priority
│   └── nombre-proyecto/
│       ├── proyecto.md                 ← index: type, status, priority, objective, pending tasks, latest results
│       ├── logbook.md                  ← chronological entries with hashtag types
│       ├── references/                 ← local PDFs (not tracked by git)
│       └── results/                    ← numerical results (not tracked by git)
├── ☀️mision-log/
│   ├── diario/YYYY-MM-DD.md            ← daily: focus project, tasks, notes
│   ├── semanal/YYYY-Wnn.md             ← weekly: 2 focus projects, review, evaluation
│   └── mensual/YYYY-MM.md              ← monthly: prioritize projects, strategic decisions
├── 📐templates/                        ← templates for all file types
│   ├── proyecto.md
│   ├── logbook.md
│   ├── diario.md
│   ├── semanal.md
│   └── mensual.md
├── orbit.py                            ← CLI entry point
└── core/                               ← CLI modules (log, list_entries, tasks, activity, monthly)
```

## Project types
- 🌀 Investigación
- 📚 Docencia
- ⚙️ Gestión
- 📖 Formación
- 💻 Software
- 🌿 Personal

## Logbook entry format

Entries are single lines: date first, content, hashtag type at the end.

```
2026-03-06 Idea sobre calibración relativa en vez de absoluta #idea
2026-03-06 [Gonzalez 2024](./references/gonzalez2024.pdf) #referencia
2026-03-06 Reproducir figura 3 del paper de Gonzalez #tarea
2026-03-06 El fit no converge con el dataset completo #problema
2026-03-06 Energy resolution σ/E = 2.3% @ 1 MeV #resultado
2026-03-06 La reunión con el grupo fue productiva #apunte
2026-03-06 Usaremos calibración relativa como estándar #decision
```

Valid hashtags: `#idea` `#referencia` `#tarea` `#problema` `#resultado` `#apunte` `#decision`

## Task format in proyecto.md

```markdown
## ✅ Tareas
- [ ] Descripción de tarea con fecha (2026-03-15)
- [ ] Descripción de tarea sin fecha
- [x] Tarea completada
```

## Git ignore

`references/` and `results/` directories are not tracked by git (binary files).

## CLI — orbit.py

| Command | Description |
|---------|-------------|
| `orbit log <project> "<msg>" [--type TYPE] [--path PATH] [--date DATE]` | Add entry to logbook |
| `orbit list <project> [--type TYPE...] [--date DATE] [--output FILE]` | List logbook entries |
| `orbit tasks [--project P] [--type T] [--status S] [--priority P] [--date D]` | List pending tasks |
| `orbit activity [--project P] [--type T] [--priority P] [--period D [D]] [--apply]` | Activity report |
| `orbit monthly [--month YYYY-MM] [--apply] [--output FILE]` | Generate monthly review |

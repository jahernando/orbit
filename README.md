# Orbit

Sistema personal de gestión de proyectos científicos en markdown plano.

---

## Estructura

```
Orbit/
├── 🚀proyectos/
│   └── {emoji}nombre-proyecto/
│       ├── project.md        ← metadatos: tipo, estado, prioridad, objetivo
│       ├── logbook.md        ← registro permanente (append-only)
│       ├── highlights.md     ← índice curado: refs, resultados, decisiones, ideas
│       ├── agenda.md         ← tareas, hitos y eventos
│       └── notes/            ← notas libres del usuario (.md)
├── 📐templates/              ← plantillas para project, logbook, highlights, agenda, note
├── cmd.md                    ← salida temporal de comandos --open
├── orbit.py                  ← CLI
├── core/                     ← módulos Python
├── CHULETA.md                ← referencia rápida de comandos
├── TUTORIAL.md               ← tutorial para nuevos usuarios
└── README.md                 ← este fichero
```

---

## Tipos de proyecto

| Emoji | Tipo | Uso |
|-------|------|-----|
| ☀️ | Misión | Proyecto raíz — gestión global, planificación, evaluaciones |
| 🌀 | Investigación | Proyectos de investigación científica |
| 📚 | Docencia | Asignaturas, TFGs, tesis |
| ⚙️ | Gestión | Gestión, propuestas, comités |
| 📖 | Formación | Cursos, lecturas, aprendizaje |
| 💻 | Software | Proyectos de software |
| 🌿 | Personal | Proyectos personales |

---

## Logbook — tipos de entrada (`--entry`)

| Tag | Emoji | Significado |
|-----|-------|-------------|
| `#idea` | 💡 | Idea nueva |
| `#referencia` | 📎 | Paper, link o recurso |
| `#apunte` | 📝 | Nota general |
| `#problema` | ⚠️ | Problema encontrado |
| `#resultado` | 📊 | Resultado obtenido |
| `#decision` | 📌 | Decisión tomada |
| `#evaluacion` | 🔍 | Evaluación parcial |

---

## CLI — referencia de comandos

Ver `CHULETA.md` para la referencia rápida completa.

### Shell interactiva

```bash
orbit              # entra al shell (¡Hola! ¡Bienvenido! / ¡Hasta pronto!)
orbit shell        # equivalente explícito
```

### Proyectos

```bash
orbit project create next-kr --type investigacion --priority alta
orbit project list [--status active] [--open]
orbit project status next-kr [--set paused]
orbit project edit next-kr
orbit project delete next-kr [--force]
```

### Tareas, hitos y eventos

```bash
orbit task add next-kr "Reproducir figura" --date 2026-03-20 --ring 1d
orbit task done next-kr "Reproducir"
orbit task list [next-kr] [--open]

orbit ms add next-kr "Primera calibración validada" --date 2026-04-01
orbit ms done next-kr
orbit ms list [--open]

orbit ev add next-kr "Congreso JINST" --date 2026-04-15 --end 2026-04-18
orbit ev list next-kr [--open]
```

### Highlights y notas

```bash
orbit hl add next-kr "González 2024" --type refs --link ./refs/g2024.pdf
orbit hl list next-kr [--open]

orbit note next-kr "Análisis de calibración"
orbit note list next-kr [--open]
```

### Anotación y búsqueda

```bash
orbit log next-kr "El fit converge" --entry resultado
orbit search "calibración" --entry resultado
orbit search --project next-kr --from 2026-03-01 [--open]
```

### Vista y navegación

```bash
orbit view [next-kr] [--open]
orbit open next-kr logbook
orbit open next-kr agenda
```

### Agenda y report

```bash
orbit agenda [--date D] [--from D] [--to D] [--calendar] [--open]
orbit report [project...] [--from D] [--to D] [--open]
```

### Otros

```bash
orbit commit ["mensaje"]
orbit help
orbit help chuleta
orbit help tutorial
```

---

## Convenciones

- `logbook.md` de cada proyecto — fuente de verdad del historial de trabajo (append-only).
- `notes/` — notas libres, rastreadas opcionalmente en git.
- `cmd.md` — fichero temporal de salida de comandos con `--open`.
- Las operaciones destructivas piden confirmación (defecto **No**) o requieren `--force`.
- `--open [--editor E]` disponible en comandos de listado; abre `cmd.md` en el editor.
- `--log PROJECT [--log-entry TYPE]` guarda el output como entrada en el logbook de un proyecto.
- `--date` acepta lenguaje natural: `today/hoy` · `next friday` · `in 5 days` · `YYYY-MM-DD`.

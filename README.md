# Orbit

Sistema personal de gestión de proyectos científicos en markdown plano.

---

## Estructura

```
Orbit/
├── 🚀proyectos/
│   ├── INDEX.md                        ← tabla maestra de proyectos
│   └── {emoji}nombre/
│       ├── {emoji}Nombre.md            ← índice: objetivo, tareas, referencias, resultados, decisiones
│       ├── 📓Nombre.md                 ← logbook cronológico
│       ├── references/                 ← PDFs (no en git)
│       ├── results/                    ← resultados numéricos (no en git)
│       └── decisions/                  ← documentos de decisión (no en git)
├── 🚀proyectos/☀️mission/
│   ├── diario/YYYY-MM-DD.md            ← notas de evaluación diaria
│   ├── semanal/YYYY-Wnn.md             ← notas de evaluación semanal
│   └── mensual/YYYY-MM.md             ← notas de evaluación mensual
├── ☀️mision-log/
│   ├── diario/YYYY-MM-DD.md            ← diario del día
│   ├── semanal/YYYY-Wnn.md             ← nota semanal
│   └── mensual/YYYY-MM.md             ← nota mensual
├── .orbit/
│   ├── focus.json                      ← foco activo por período (fuente de verdad)
│   └── session.json                    ← timestamps de última sesión start/end
├── 📐templates/
├── orbit.py                            ← CLI
├── CHULETA.md                          ← referencia rápida
└── core/                               ← módulos Python
```

---

## Arquitectura — foco y evaluación

### Foco (`focus.json`)

El foco es la lista de proyectos en los que el usuario trabaja activamente en un período. Se gestiona con `orbit focus` y se guarda en `.orbit/focus.json` — la única fuente de verdad para el foco. Todos los demás comandos (`agenda`, `eval`, `end`, `status --focus`) leen de aquí.

```json
{
  "month": { "2026-03": ["💻orbit", "☀️mission"] },
  "week":  { "2026-W10": ["💻orbit"] },
  "day":   { "2026-03-08": ["💻orbit"] }
}
```

### Evaluación (`☀️mission/`)

Las notas de evaluación son generadas por `orbit eval` / `orbit end` y se guardan dentro del proyecto `☀️mission`. Tienen dos partes:

- **Estadísticas** (`orbit:eval-stats`) — actualizadas automáticamente en cada llamada.
- **Reflexión** — secciones en blanco creadas una sola vez; el usuario las completa a mano y nunca se sobreescriben.

Separar las notas de evaluación de las notas de trabajo evita que el sistema sobreescriba texto del usuario.

---

## Tipos de proyecto

| Emoji | Tipo | Uso |
|-------|------|-----|
| ☀️ | Misión | Proyecto raíz — tareas, recordatorios y evaluaciones |
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
| `#tarea` | ✅ | Tarea a realizar |
| `#problema` | ⚠️ | Problema encontrado |
| `#resultado` | 📊 | Resultado obtenido |
| `#apunte` | 📝 | Nota general |
| `#decision` | 📌 | Decisión tomada |
| `#evento` | 📅 | Evento de calendario |

---

## Flujo de trabajo recomendado

```bash
# Al empezar el día:
orbit start                            # estado + foco + alerta sesión perdida

# Durante el día:
orbit agenda                           # ver tareas del día (con foco marcado)
orbit log next-kr "El fit converge" --entry resultado
orbit add task next-kr "Revisar paper" --date "next friday"

# Al terminar:
orbit end                              # resumen de actividad + nota de evaluación
```

---

## CLI — referencia de comandos

Ver `CHULETA.md` para referencia rápida completa.

### Sesión

```bash
orbit start                             # inicio de sesión
orbit end                               # fin de sesión + evaluación
```

### Foco

```bash
orbit focus                             # ver foco de todos los períodos
orbit focus month --set orbit mission   # establecer foco mensual
orbit focus week  --set orbit           # foco semanal
orbit focus day   --clear               # limpiar foco del día
orbit focus week  --interactive         # selección interactiva
```

### Estado de proyectos

```bash
orbit status                            # todos los proyectos
orbit status --focus                    # solo proyectos en foco
orbit status --project next-kr          # un proyecto concreto
```

### Agenda

```bash
orbit agenda                            # agenda del día
orbit agenda week                       # semana agrupada por día
orbit agenda month                      # mes agrupado por semana
orbit agenda day --ring                 # hoy + Reminders.app
```

### Evaluación

```bash
orbit eval day                          # nota de evaluación del día
orbit eval week                         # nota de evaluación de la semana
orbit eval month                        # nota de evaluación del mes
```

### Anotación

```bash
orbit log next-kr "El fit converge" --entry resultado
orbit log "Llamada a la secretaría"     # sin proyecto → diario de hoy

orbit add task next-kr "Reproducir figura" --date "next friday"
orbit add task "Reunión CERN" --date today --ring
orbit add ref  next-kr "Gonzalez 2024" --file ~/Downloads/gonzalez2024.pdf
```

### Búsqueda y listados

```bash
orbit search "calibración" --entry resultado
orbit search --project next-kr --from "last month"
orbit list projects --type investigacion
orbit list tasks --priority alta
orbit list tasks --ring
```

### Apertura de ficheros

```bash
orbit open                              # diario de hoy en Typora
orbit open next-kr                      # proyecto en Typora
orbit open next-kr --log                # logbook del proyecto
orbit open 2026-W10                     # nota semanal
```

### Calendario visual

```bash
orbit calendar week                     # semana actual en Typora
orbit calendar month                    # mes actual en Typora
orbit calendar year                     # año actual en Typora
```

### Modificar tareas

```bash
orbit change task schedule next-kr "Reproducir figura" --date "next monday"
orbit change task close next-kr "Reproducir figura"
```

### Documentación

```bash
orbit info chuleta    # chuleta de comandos
orbit info about      # README
orbit info tutorial   # tutorial
orbit info help       # help completo
```

---

## Convenciones

- `.orbit/focus.json` — fuente de verdad del foco activo por período.
- `proyecto.md` de cada proyecto — fuente de verdad de tareas y metadatos.
- `logbook.md` de cada proyecto — fuente de verdad del historial de trabajo.
- `☀️mission/diario|semanal|mensual/` — evaluaciones generadas por Orbit (no editar manualmente).
- `references/`, `results/`, `decisions/` no se suben a git (binarios).
- `--date` acepta lenguaje natural: `today/hoy` · `next friday` · `in 5 days` · `last week` · `YYYY-MM-DD`.

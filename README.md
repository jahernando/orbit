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
├── ☀️mision-log/
│   ├── diario/YYYY-MM-DD.md
│   ├── semanal/YYYY-Wnn.md
│   └── mensual/YYYY-MM.md
├── 📐templates/
├── orbit.py                            ← CLI
├── CHULETA.md                          ← referencia rápida
└── core/                               ← módulos Python
```

---

## Tipos de proyecto

| Emoji | Tipo | Uso |
|-------|------|-----|
| ☀️ | Misión | Proyecto raíz — tareas y recordatorios generales |
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

## Proyecto Mission ☀️

`mission` es el proyecto raíz del workspace:
- `orbit add task "desc"` sin proyecto → va a mission
- `orbit add task "desc" --ring` → tarea con alarma en Reminders.app
- `--date today` → también se copia al diario del día
- `--date today --ring` → también se programa en Reminders.app
- Los reportes de día, semana y mes se generan automáticamente al salir del shell

---

## Flujo de trabajo diario

```bash
orbit log next-kr "El fit converge con N=500" --entry resultado
orbit add task "Revisar paper de Gonzalez" --date "next friday"
orbit add ring "Reunión grupo NEXT" --date today --time 10:00

orbit report stats --from "last month" --to today
```

---

## CLI — referencia de comandos

Ver `CHULETA.md` para referencia rápida.

### Shell interactivo

```bash
orbit          # entra al shell — escribe comandos sin prefijo "orbit"
orbit claude   # abre Claude Code en el directorio Orbit
```

### create

```bash
orbit create project --name NEXT-GALA --type investigacion --priority alta
orbit create project --name mission --type mision --priority alta
orbit create import  --file ~/Downloads/NEXT-Kr.enex --project next-kr
```

### add

```bash
orbit add task next-kr "Reproducir figura 3" --date "next friday"
orbit add task "Llamar al banco" --date today              # → mission + diario
orbit add task "Reunión CERN" --date today --ring          # → alarma + Reminders.app
orbit add task next-kr "Reunión semanal" --date "next monday" --ring --recur weekly
orbit add ref  next-kr "Gonzalez 2024" --file ~/Downloads/gonzalez2024.pdf --sync
orbit add result next-kr "σ/E = 2.3% @ 1 MeV" --url https://...
orbit add decision next-kr "Usaremos calibración relativa"
```

### change

```bash
orbit change task schedule next-kr "Reproducir figura" --date "next monday"
orbit change task close next-kr "Reproducir figura"
```

### list

```bash
orbit list projects
orbit list projects --type investigacion --status "en marcha"
orbit list tasks --priority alta
orbit list tasks --project next-kr
orbit list tasks --ring                    # solo tareas con alarma (⏰)
```

### report

```bash
orbit report stats --from "last month" --to today
```

### log y search

```bash
orbit log next-kr "El fit no converge" --entry problema
orbit log "Reunión productiva con Diego"     # → diario de hoy

orbit search "calibración" --entry resultado
orbit search --project next-kr --from "last month"
orbit search "fit" --entry problema --type investigacion
```

### open

```bash
orbit open                          # diario de hoy en Typora
orbit open next-kr                  # proyecto en Typora
orbit open next-kr --log            # logbook en Typora
orbit open 2026-W10                 # nota semanal
orbit open next-kr --terminal       # imprime en terminal
orbit open next-kr --terminal --log --entry resultado  # filtra entradas
```

### calendar

```bash
orbit calendar week                 # semana actual en Typora
orbit calendar month                # mes actual en Typora
orbit calendar year                 # año actual en Typora
orbit calendar week --date "next week"
orbit calendar month --date 2026-04
```

Genera un fichero markdown con tareas (✅) y recordatorios (⏰) del período y lo abre en Typora.

### info

```bash
orbit info chuleta    # abre CHULETA.md en Typora
orbit info about      # abre README.md en Typora
orbit info tutorial   # abre TUTORIAL.md en Typora
orbit info help       # muestra el help completo de orbit
```

---

## Tareas con alarma (rings)

Las tareas con `@ring` en `proyecto.md` se programan automáticamente en Reminders.app al entrar en el shell. Se marcan `[~]` una vez programadas. Las recurrentes avanzan la fecha a la siguiente ocurrencia.

```markdown
## ✅ Tareas
- [ ] Reunión semanal del grupo (2026-03-10 09:00) @ring @weekly
- [ ] Standup (2026-03-07 08:30) @ring @daily
- [ ] Revisión mensual (2026-03-01 10:00) @ring @monthly
```

Para añadir tareas con alarma:

```bash
orbit add task "Reunión grupo" --date "next monday" --time 09:00 --ring
orbit add task "Standup" --date today --ring --recur daily
```

---

## Automatización diaria (cron)


Si la nota ya existe (creada manualmente antes), el cron no hace nada.

---

## Convenciones

- `--date` acepta lenguaje natural: `today/hoy` · `next friday/próximo viernes` · `in 5 days/en 5 días` · `last week` · `YYYY-MM-DD`
- **Fuente de verdad** de tareas y recordatorios: `proyecto.md` de cada proyecto
- **Fuente de verdad** del historial: `logbook.md` de cada proyecto
- **mission** es la fuente de verdad de tareas y recordatorios generales
- `references/`, `results/`, `decisions/` no se suben a git (binarios)

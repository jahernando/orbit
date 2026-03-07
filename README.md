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
- `orbit add ring "desc" --date ... --time ...` sin proyecto → va a mission
- `--date today` en `add task/ring` → también se copia al diario del día
- `--date today` en `add ring` → también se programa en Reminders.app
- `orbit report week/month` guarda una entrada en el logbook de mission

---

## Flujo de trabajo diario

```bash
orbit create day          # crea diario (y semanal/mensual en cascada si no existen)
                          # hereda foco de la nota semanal automáticamente
                          # programa los recordatorios del día en Reminders.app

orbit log next-kr "El fit converge con N=500" --entry resultado
orbit add task "Revisar paper de Gonzalez" --date "next friday"
orbit add ring "Reunión grupo NEXT" --date today --time 10:00

orbit report day --inject # al final del día
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
orbit create day     --focus next-kr orbit
orbit create week
orbit create month
```

### add

```bash
orbit add task next-kr "Reproducir figura 3" --date "next friday"
orbit add task "Llamar al banco" --date today          # → mission + diario
orbit add ring "Reunión CERN" --date today --time 10:00 # → mission + diario + Reminders.app
orbit add ring next-kr "Reunión semanal" --date "next monday" --time 09:00 --recur weekly
orbit add ref  next-kr "Gonzalez 2024" --file ~/Downloads/gonzalez2024.pdf --sync
orbit add result next-kr "σ/E = 2.3% @ 1 MeV" --url https://...
orbit add decision next-kr "Usaremos calibración relativa"
```

### change

```bash
orbit change status "en marcha" next-kr next-gala
orbit change status parado --from-status esperando
orbit change priority alta --type investigacion
orbit change task schedule next-kr "Reproducir figura" --date "next monday"
orbit change task close next-kr "Reproducir figura"
orbit change ring schedule next-kr "Reunión semanal" --date "next monday" --time 09:00
```

### list

```bash
orbit list projects
orbit list projects --type investigacion --status "en marcha"
orbit list tasks --priority alta
orbit list tasks --project next-kr
orbit list rings
orbit list refs next-kr
orbit list decisions
```

### report

```bash
orbit report day
orbit report week --inject
orbit report month --inject --apply
orbit report stats --from "last month" --to today
orbit report status
orbit report status --apply
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

---

## Recordatorios recurrentes

En `proyecto.md`, sección `## ⏰ Recordatorios`:

```markdown
- [ ] 2026-03-10 09:00 Reunión semanal del grupo @weekly
- [ ] 2026-03-07 08:30 Standup @daily
- [ ] 2026-03-01 10:00 Revisión mensual @monthly
- [ ] 2026-03-07 09:00 Backup datos @every:3d
```

Al ejecutar `orbit create day`, los recordatorios de hoy se programan automáticamente en Reminders.app y se marcan `[~]`. Los recurrentes avanzan la fecha a la siguiente ocurrencia.

---

## Automatización diaria (cron)

```bash
# Crear la nota del día automáticamente a las 8:00 (lunes-viernes)
0 8 * * 1-5 cd /Users/hernando/Orbit && python3 orbit.py create day --no-open
```

Si la nota ya existe (creada manualmente antes), el cron no hace nada.

---

## Convenciones

- `--date` acepta lenguaje natural: `today/hoy` · `next friday/próximo viernes` · `in 5 days/en 5 días` · `last week` · `YYYY-MM-DD`
- **Fuente de verdad** de tareas y recordatorios: `proyecto.md` de cada proyecto
- **Fuente de verdad** del historial: `logbook.md` de cada proyecto
- **mission** es la fuente de verdad de tareas y recordatorios generales
- `references/`, `results/`, `decisions/` no se suben a git (binarios)

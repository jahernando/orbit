# Orbit — Chuleta de comandos

## Shell interactivo

```bash
orbit              # entra al shell (sin prefijo orbit en cada comando)
orbit shell        # equivalente explícito
orbit claude       # abre Claude Code en el directorio Orbit
```

---

## start / end — rutinas de sesión

```bash
orbit start [--editor E]   # inicio de sesión: status + foco + alerta si hay sesión perdida
orbit end   [--editor E]   # fin de sesión: resumen de actividad + nota de evaluación
```

- `start` muestra el estado de proyectos, el foco actual y detecta si ayer hubo actividad sin evaluación.
- `end` crea o actualiza la nota de evaluación del período que corresponda y la abre en el editor.
- Fin de semana (vie/sáb/dom) → `end` genera también la evaluación semanal.
- Últimos 3 días del mes → `end` genera también la evaluación mensual.

---

## focus — gestión del foco

```bash
orbit focus                              # muestra foco activo en todos los períodos
orbit focus month                        # muestra solo el foco mensual
orbit focus month --set orbit mission    # establece proyectos en foco para el mes
orbit focus week  --set orbit            # foco de la semana
orbit focus day   --set orbit            # foco del día
orbit focus week  --clear                # limpia el foco semanal
orbit focus month --interactive          # selección interactiva de proyectos
```

- El foco se guarda en `.orbit/focus.json` — fuente de verdad, versionada en git.
- Los comandos `agenda`, `eval` y `end` consultan el foco automáticamente.

---

## status — salud de proyectos

```bash
orbit status                   # todos los proyectos agrupados por estado de actividad
orbit status --project orbit   # un proyecto concreto
orbit status --focus           # solo proyectos en foco (según focus.json)
```

- 🟢 **Activo** — actividad en el logbook en los últimos 30 días.
- 🟡 **Parado** — sin actividad en 30 días, pero sí en 60.
- 🔴 **Durmiendo** — sin actividad en 60 días.
- No depende del campo manual en `proyecto.md`; se basa en el logbook real.

---

## agenda — planificación por período

```bash
orbit agenda                          # agenda del día (default)
orbit agenda day                      # explícito
orbit agenda week                     # semana actual agrupada por día
orbit agenda month                    # mes actual agrupado por semana
orbit agenda --date 2026-03-15        # fecha concreta
orbit agenda day --ring               # hoy + programa @ring en Reminders.app
orbit agenda --output agenda.md       # guarda en fichero
```

- Vista siempre dinámica — nunca escribe en notas del usuario.
- 🎯 marca las tareas de proyectos en foco (según `focus.json`).
- ⚠️ marca tareas vencidas (shown al principio).
- `--ring` activa el envío de tareas `@ring` a Reminders.app (solo para `day`).

---

## eval — notas de evaluación

```bash
orbit eval day   [--date YYYY-MM-DD] [--no-open]   # evaluación del día
orbit eval week  [--date YYYY-MM-DD] [--no-open]   # evaluación de la semana
orbit eval month [--date YYYY-MM-DD] [--no-open]   # evaluación del mes
orbit eval       [--date YYYY-MM-DD]               # crea/actualiza las tres
```

- Las notas se guardan en `🚀proyectos/☀️mission/diario/`, `semanal/`, `mensual/`.
- El bloque de estadísticas (`orbit:eval-stats`) se actualiza en cada llamada.
- La sección de reflexión se crea una sola vez y nunca se sobreescribe.

---

## create — crear cosas nuevas

```bash
orbit create project  --name NOMBRE --type TIPO [--priority alta|media|baja]
orbit create import   --file FICHERO.enex --project PROYECTO
```

Las notas de día, semana y mes se crean automáticamente al entrar en el shell de Orbit.

---

## add — añadir items a un proyecto

```bash
orbit add task  [project] <desc>   [--date D] [--time HH:MM] [--ring] [--recur RULE] [--open]
orbit add ref   <project> <título> [--entry TIPO] [--url URL] [--file PATH] [--sync] [--open]
orbit add note  <project> <título> [--file FILE.md] [--entry TIPO] [--no-link] [--no-date] [--open]
```

- `add task` sin proyecto → va a **mission** por defecto
- `--date today` → también se copia al diario del día
- `--ring` → tarea con alarma; si omites `--time` se pide en el prompt (defecto 09:00)
- `--date today` + `--ring` → también se programa en Reminders.app
- `--recur` acepta: `daily/diario` · `weekly/semanal` · `monthly/mensual` · `yearly/anual` · `weekdays/laborables` · `every:Nd` · `every:Nw`
- `add ref --entry TIPO` → determina la sección del proyecto y el tag del logbook; si se omite se pide en el prompt
- `--entry`: `referencia` 📎 · `resultado` 📊 · `decision` 📌 · `apunte` 📝 · `idea` 💡 · `problema` ⚠️
- `add note` sin `--file` → crea `YYYYMMDD_título.md` desde plantilla y la abre en Typora

---

## change — modificar cosas existentes

```bash
orbit change task schedule <project> <desc> --date D [--time HH:MM] [--recur RULE] [--open]
orbit change task close    <project> <desc> [--date D] [--open]
```

`change task close` con `@recur` avanza la fecha en vez de cerrar (se pide confirmación interactiva).

---

## list — listar proyectos y secciones

```bash
orbit list projects   [--type T] [--status S] [--priority P] [--output F] [--open]
orbit list tasks      [--project P] [--type T] [--status S] [--priority P] [--date D] [--keyword K] [--ring]
orbit list refs       [project]   [--entry TIPO] [--output F] [--open]
orbit list results    [project]   [--output F] [--open]
orbit list decisions  [project]   [--output F] [--open]
orbit list files      [project]   [--output F] [--open]
orbit list notes      [project]   [--output F] [--open]
```

- `--ring` → muestra solo tareas con alarma (⏰)
- `list refs --entry TIPO` → filtra dentro de Referencias por tipo

---

## report — informes

```bash
orbit report stats  [--date D] [--from D] [--to D] [--project P] [--type T] [--priority P] [--output F] [--open]
```

---

## log y search

```bash
orbit log [project] <msg> [--entry TIPO] [--path RUTA] [--date D] [--open] [--editor E]
# Sin proyecto → anota en el diario de hoy

orbit search [query] [--project P...] [--entry TIPO] [--date D] [--from D] [--to D]
             [--type T] [--status S] [--priority P] [--any] [--diario] [--notes]
             [--limit N] [--output F] [--open] [--editor E]
```

`--entry`: `idea` · `referencia` · `tarea` · `problema` · `resultado` · `apunte` · `decision` · `evento`

---

## open

```bash
orbit open [target] [--log] [--note NAME] [--editor E]
orbit open [target] --terminal [--section S] [--entry TIPO] [--log] [--output F]
# target: nombre-proyecto · YYYY-MM-DD · YYYY-Wnn · YYYY-MM  (defecto: hoy)
```

---

## calendar — calendario visual

```bash
orbit calendar week  [--date D] [--no-open] [--editor E]
orbit calendar month [--date D] [--no-open] [--editor E]
orbit calendar year  [--date D] [--no-open] [--editor E]
```

Genera un fichero markdown con tareas (✅) y recordatorios (⏰) del período y lo abre en Typora.
Guardado en `☀️mision-log/calendar-{week,month,year}.md`.

---

## info — documentación

```bash
orbit info chuleta    # abre CHULETA.md en Typora
orbit info about      # abre README.md en Typora
orbit info tutorial   # abre TUTORIAL.md en Typora
orbit info help       # muestra el help completo de orbit
```

---

## Tipos de proyecto

`investigacion` 🌀 · `docencia` 📚 · `gestion` ⚙️ · `formacion` 📖 · `software` 💻 · `personal` 🌿 · `mision` ☀️

## Estados

`inicial` ⬜ · `en marcha` ▶️ · `parado` ⏸️ · `durmiendo` 💤 · `completado` ✅

## Prioridades

`alta` 🟠 · `media` 🟡 · `baja` 🔵

---

## Fechas — lenguaje natural

Todos los `--date`, `--from`, `--to` aceptan:

`today/hoy` · `yesterday/ayer` · `tomorrow/mañana` · `this week/esta semana` · `last month/mes pasado` · `next friday/próximo viernes` · `in 5 days/en 5 días` · `last friday of march` · `YYYY-MM-DD` · `YYYY-MM` · `YYYY-Wnn`

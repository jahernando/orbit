# Orbit — Tutorial para nuevos usuarios

Orbit es un sistema de gestión de proyectos científicos basado en ficheros markdown planos. Todo se guarda localmente, se versiona con git y se visualiza en cualquier editor de markdown.

---

## 1. Primeros pasos — instalar y configurar

### Requisito previo

Carga `orbit.sh` desde tu `~/.zshrc`:

```zsh
source /ruta/a/orbit/orbit.sh
```

Esto te da los comandos `worbit` (workspace de trabajo) y `porbit` (workspace personal).

Ejecuta `orbit setup` para configurar el workspace de forma interactiva:

```bash
orbit setup
```

El asistente te guía por: emoji del workspace, tipos de proyecto, editor, Google Sync, cartero (Gmail/Slack) y federación. Cada sección es opcional — pulsa Enter para saltar.

Si prefieres configurar manualmente, edita `orbit.json` directamente (ver SETUP.md).

### Entrar en Orbit

```bash
orbit
```

Se abre el shell interactivo `🚀`. Dentro del shell no necesitas el prefijo `orbit`.

---

## 2. Crear proyectos

```bash
project create next-kr --type investigacion --priority alta
```

Tipos: `investigacion` · `docencia` · `gestion` · `formacion` · `software` · `personal`

Esto crea `🚀proyectos/🌀next-kr/` con: `project.md`, `logbook.md`, `highlights.md`, `agenda.md` y `notes/`.

Abre el proyecto en el editor para completar el objetivo:

```bash
open next-kr
```

---

## 3. El proyecto Mission

Orbit incluye un proyecto especial **☀️mission**. Es el proyecto raíz para:

- Planificación general (hitos del día, semana, mes).
- Evaluaciones y decisiones de gestión.
- Tareas que no pertenecen a ningún proyecto concreto.

Puedes usar sus hitos para definir el **foco** de cada período y revisarlos con `report`.

---

## 4. Empezar el día — panel y agenda

Panel y agenda son las dos herramientas dinámicas para gestionar el día. Ambas muestran información actualizada cada vez que las ejecutas: citas, tareas, actividad. La idea es abrirlas al empezar y refrescarlas durante la jornada.

### Panel — el dashboard

El panel es la vista de alto nivel: proyectos prioritarios, citas del periodo y actividad reciente.

```bash
panel                      # panel del día
panel week                 # panel semanal
panel month                # panel mensual
panel --from monday --to friday   # rango personalizado
panel --open               # escribe a panel.md y abre en editor (fijable en Obsidian)
```

Secciones del panel:
- **Prioridad**: proyectos 🔴 alta, 🔶 urgentes (con citas/vencidas), 🏁 hitos del mes
- **Agenda**: tabla con las citas del periodo (tipo, hora, descripción, proyecto)
- **📊 Cronogramas**: barra de progreso por cronograma (solo si hay cronogramas activos)
- **Actividad**: entradas de logbook del periodo por proyecto

### Agenda — las citas del día

La agenda muestra tareas pendientes y vencidas, eventos, hitos y recordatorios.

```bash
agenda                     # agenda de hoy
agenda week                # agenda de la semana
agenda month               # agenda del mes
agenda --open              # escribe a agenda.md y abre en editor (fijable en Obsidian)
agenda --date 2026-03      # agenda de un mes concreto
agenda --from monday --to friday   # rango personalizado
agenda --dated             # solo tareas/hitos con fecha
agenda --order date        # agrupa por día con horas
```

Con `--open`, tanto panel como agenda escriben a ficheros fijos (`panel.md`, `agenda.md`) que puedes fijar como pestañas en Obsidian. Cada vez que ejecutas el comando, el fichero se actualiza.

### Flujo típico del día

```
Por la mañana
──────────────
orbit
  panel --open              # abre panel.md: ¿qué proyectos son prioritarios?
  agenda --open             # abre agenda.md: ¿qué citas hay hoy?
  note mission "notas-día"  # (opcional) nota temporal para apuntes sueltos

Durante el día
──────────────
  # Trabajar, anotar, completar tareas...
  log next-kr "σ/E = 2.1%" --entry resultado
  task done next-kr "Reproducir"
  panel                     # refrescar: ve la actividad actualizada
  agenda                    # refrescar: ve las tareas completadas

Al final del día
────────────────
  report today              # resumen de actividad del día
  commit                    # guardar cambios en git
```

---

## 5. Trabajar y anotar — log

El logbook es el registro cronológico de cada proyecto. Cada entrada tiene un tipo:

| Tipo | Uso |
|------|-----|
| `apunte` 📝 | Nota general |
| `idea` 💡 | Idea nueva |
| `referencia` 📎 | Paper, enlace o recurso |
| `problema` ⚠️ | Problema encontrado |
| `solucion` ✔️ | Solución a un problema |
| `resultado` 📊 | Resultado obtenido |
| `decision` 📌 | Decisión tomada |
| `evaluacion` 🔍 | Evaluación parcial |

```bash
log next-kr "σ/E = 2.3% @ 1 MeV con N=500" --entry resultado
log next-kr "El fit no converge con dataset completo" --entry problema
log next-kr "Usaremos calibración relativa" --entry decision
```

Para añadir una referencia con enlace a un fichero local:

```bash
log next-kr "González 2024 — calibración" ./refs/gonzalez2024.pdf --entry referencia
```

Orbit preguntará si quieres entregar el fichero a cloud. Para entregarlo directamente:

```bash
log next-kr "González 2024 — calibración" ./refs/gonzalez2024.pdf --entry referencia --deliver
```

El fichero se copia a `logs/` en cloud con prefijo de fecha (`2026-03-15_gonzalez2024.pdf`) y la entrada enlaza al fichero en cloud. Si el fichero es una imagen, se inserta como figura en la línea siguiente.

Para enlazar a una URL:

```bash
log next-kr "Paper interesante" https://arxiv.org/abs/2401.12345 --entry referencia
```

---

## 6. Gestión de tareas, hitos y eventos

### Tareas

```bash
task add next-kr "Reproducir figura 3" --date 2026-03-20
task add next-kr "Reunión semanal" --date 2026-03-15 --recur weekly --ring 1d
task done next-kr "Reproducir"     # interactivo con match parcial
task list                          # todas las pendientes
```

### Hitos

Los hitos son objetivos importantes. Úsalos en el proyecto `mission` para marcar el foco del día o la semana:

```bash
ms add mission "Foco: avanzar calibración next-kr" --date 2026-03-09 --ring 1d
ms done mission "Foco"
```

### Eventos

```bash
ev add next-kr "Congreso JINST" --date 2026-04-15 --end 2026-04-18 --ring 1d
ev add next-kr "Seminario" --date 2026-03-20 --time 10:00-11:00 --recur weekly
ev add next-kr "WG12" --date 2026-05-08 --time 12:00 \
       --agenda https://indico.cern.ch/event/17950/ \
       --room https://cern.zoom.us/j/8463658000
ev edit next-kr "WG12" --room none      # quitar la sala
```

- `--time HH:MM` — evento con hora de inicio (1h por defecto en Google Calendar)
- `--time HH:MM-HH:MM` — evento con hora de inicio y fin
- Sin `--time` — evento de día completo (o multi-día con `--end`)
- `--agenda URL` (📋) — agenda/indico del evento; queda como nota indentada
- `--room` — sala. URL (Zoom/Meet/Teams/Webex) → 📹 cámara (clickable en Calendar.app); texto plano (`Aula A1-01`) → 🚪 puerta (queda en las notas)
- En `edit`, `none` quita el campo. `--desc` no borra estos campos estructurados

Los cuatro tipos comparten `--date`, `--recur`, `--until`. Tasks, hitos y eventos aceptan `--ring`.
Las tareas y hitos recurrentes avanzan automáticamente al completarlas.
Los eventos recurrentes se expanden automáticamente en la agenda y el calendario.
`--ring` programa una alarma en Reminders.app de macOS.

### Crear entrada de logbook desde una cita

```bash
task log next-kr "Reproducir"        # → #apunte en logbook
ms log next-kr "Calibración"         # → #resultado en logbook
ev log next-kr "Congreso"            # → #evento en logbook
reminder log next-kr "correo"        # → #apunte en logbook
```

Útil para anotar qué se hizo cuando se completó una tarea, se alcanzó un hito, se asistió a un evento o se atendió un recordatorio.

### Recordatorios

Los recordatorios son notificaciones simples: tienen fecha, hora y texto, pero no tienen estado (no se completan ni vencen). Orbit los programa en Reminders.app de macOS para que te llegue la notificación.

```bash
reminder add mission "¡Revisa el correo!" --date 2026-03-18 --time 17:00
reminder add next-kr "Llamar al laboratorio" --date tomorrow --time 10:00
reminder add next-kr "Backup semanal" --date 2026-03-20 --time 09:00 --recur weekly
reminder add next-kr "Gym" --date 2026-03-20 --time 07:00 --recur daily --until 2026-06-30
reminder edit mission "correo" --text "Revisa el correo personal" --time 18:00
reminder drop mission "correo"      # elimina por match parcial
reminder drop mission "Backup" -o  # solo esta ocurrencia (avanza al próximo)
reminder drop mission "Gym" -s     # elimina toda la serie
ls reminders                        # lista recordatorios activos de todos los proyectos
```

Se guardan en la sección `## 💬 Recordatorios` del `agenda.md`. Al iniciar la shell, los recordatorios del día se programan automáticamente en Reminders.app.

---

## 7. Highlights — índice curado

Los highlights son el índice permanente de lo más relevante: referencias clave, resultados importantes, decisiones fundamentales.

```bash
hl add next-kr "González 2024 — calibración relativa" ./refs/g2024.pdf --type refs
hl add next-kr "González 2024" ./refs/g2024.pdf --type refs --deliver   # entrega a cloud (hls/)
hl add next-kr "Paper relevante" https://arxiv.org/... --type refs      # con URL
hl add next-kr "σ/E = 2.3% @ 1 MeV" --type results
hl add next-kr "Calibración relativa como estándar" --type decisions
hl list next-kr
```

Tipos: `refs` · `results` · `decisions` · `ideas` · `evals`

Cada `hl add` deja también una entrada en el logbook con tag `#headline` + el tipo mapeado (refs→#referencia, results→#resultado, etc.). El link, si lo hay, queda en la entrada del log también — no necesitas hacer un `note` adicional.

---

## 8. Capturar emails a un proyecto

A veces recibes un email importante (una invitación, un paper, un acuerdo). Lo registras en un proyecto en un comando:

```bash
# Selecciona el email en Mail.app y desde orbit:
email next-kr                     # log con link al email (default, ligero)
email next-kr --note              # ↑ + guarda nota md (cuerpo del email)
email next-kr --ev                # ↑ + propone crear evento de la cita
email next-kr --note --ev         # los tres: log + nota + evento

# Desde un .eml exportado (Outlook → drag al Finder):
email next-kr --eml ~/Desktop/"Invite WG12.eml"
email next-kr --eml ~/Desktop/foo.eml --ev
```

- **Default**: el log lleva `✉️ [Email: subject](message://<id>)` — clickeable, abre Mail.app en el mensaje. Si después borras el email, el link se rompe pero el asunto y la fecha quedan registrados. El prefijo ✉️ marca "esto apunta a un mensaje"
- **Con `--note`**: el log pasa a doble link `📎 [Email: subject](nota.md) ✉️ [original](message://...)`. El 📎 (clip = fichero) marca el primario que apunta a la nota md; ✉️ queda como secundario al original. La nota es inmortal aunque borres el email
- **Con `--ev`**: detecta título, fecha, hora, agenda (Indico) y room (Zoom/Meet/Teams) — vía adjunto ICS si existe, o regex sobre el cuerpo. Te muestra preview y pregunta `[S/n/e=editar]`
- Source default por workspace en `orbit.json`: `"email_source": "mail"` (recomendado, Apple Mail.app)

---

## 9. Buscar

```bash
search "calibración"                                # en todos los proyectos
search "fit" --project next-kr                      # en un proyecto concreto
search "resolución" --entry resultado               # filtrar por tipo
search --from "last month" --to today               # por rango de fechas
search "sigma" --in highlights                      # buscar en highlights
search "calibración" --notes                        # incluir notas/
```

---

## 10. Ver proyectos

```bash
view next-kr              # resumen en terminal: estado, tareas, hitos, últimas entradas
view next-kr --open       # genera cmd.md y lo abre en el editor
open next-kr logbook      # abre el logbook en el editor
open next-kr highlights   # abre highlights en el editor
```

---

## 11. Al final del día — report

```bash
report
```

Muestra un informe de actividad de todos los proyectos (últimos 30 días por defecto):
entradas de logbook, tareas completadas/pendientes/vencidas, hitos y eventos.

```bash
report next-kr --from 2026-03-01 --to 2026-03-09
report --summary             # tabla resumen: logbook + agenda
report --summary logbook     # solo tabla de entradas por tipo
report --summary agenda      # solo tareas/hitos/eventos
report --summary highlights  # snapshot actual de highlights
report --summary all         # las tres tablas
report --open                # abre el informe en el editor
report --summary --log mission   # tabla markdown en el logbook de mission
```

Guardar el report en el logbook de `mission` es útil para tomar decisiones de gestión: al revisarlo puedes añadir una evaluación como highlight:

```bash
hl add mission "Semana productiva en next-kr, retrasar hk-sources" --type evals
```

---

## 12. Flujo de trabajo completo — ejemplo típico

```
Lunes por la mañana
───────────────────
orbit
  panel --open                     # dashboard en Obsidian: prioridad + citas + actividad
  agenda --open                    # agenda del día en Obsidian (fijar como pestaña)
  note mission "notas-lunes"       # nota temporal para apuntes del día

  # Trabajar y anotar:
  log next-kr "σ/E = 2.1% @ 511 keV" --entry resultado
  log next-kr "Probar con diferentes ROI" --entry idea
  log next-kr "Espectro calibrado" spectrum.png --entry resultado --deliver
  task done next-kr "Reproducir"
  task add next-kr "Preparar presentación" --date "next thursday"
  hl add next-kr "Resolución validada a 511 keV" --type results

  # Refrescar durante el día:
  panel                            # actualiza panel.md: nueva actividad
  agenda                           # actualiza agenda.md: tareas completadas

Lunes por la tarde
──────────────────
  report today                     # ¿qué se ha hecho hoy?
  report --log mission             # guardar en logbook de mission
  commit                           # guardar cambios en git

Viernes por la tarde
────────────────────
  panel week --open                # dashboard semanal
  report --from monday --to friday # informe semanal
  report --from monday --to friday --log mission
  hl add mission "Buena semana: calibración avanzada, pendiente topo" --type evals
  commit
```

---

## 13. Otros comandos útiles

### Notas: propia vs externa

Modelo (v0.36): todas las notas son markdown vivos. Lo único que cambia es **dónde vive la verdad**:

- **Propia**: la nota vive en el workspace. Tú la creas, tú la editas. Está en `notes/` como un `.md` normal.
- **Externa**: el `.md` vive fuera del workspace (otro repo, Drive compartido, etc.). En `notes/` hay un **symlink relativo** al fuente. Editar en Obsidian = editar el fuente.

```bash
# Propia
note next-kr "Análisis detallado de calibración"           # nueva, con fecha
note next-kr "Plantilla" --no-date                          # nueva, sin fecha
note next-kr "Brief inicial" --from ~/drive/shared.md      # contenido pre-cargado

# Externa
track next-kr ~/repos/specs/calibration.md                 # symlink
note list next-kr                                          # ✏️ propia / 🔄 externa
untrack next-kr calibration.md                             # quita la externa, fuente intacta
```

`note list` marca cada nota:

- **✏️ propia**: vive en el workspace.
- **🔄 externa**: symlink; muestra `→ /ruta/al/fuente`.

### Externa — `.md` que vive fuera del workspace

Para markdown que evoluciona en otro sitio y quieres a mano en Obsidian + publicado al cloud, sin duplicar la verdad. Casos típicos:

- `DECISIONS.md` de tu repo público de código
- Draft compartido en un Drive USC (carpeta de equipo)
- Plan vivo de otro proyecto del workspace personal

```bash
$ track next-kr /Users/hernando/repos/specs/calibration.md
  local? /Users/hernando/repos/specs/
  note?  calibration.md
✓ [next-kr] Tracked: notes/calibration.md → /Users/hernando/repos/specs/calibration.md
```

Lo que pasa:

1. Orbit crea un symlink relativo en `next-kr/notes/calibration.md` → `~/repos/specs/calibration.md`.
2. Lo registra en `next-kr/.orbit-tracked.json` con el path del fuente.
3. Desde ese momento Obsidian abre el fuente cuando navegas a esa nota.

Después, cualquier edición:

- **En Obsidian** sobre la externa → se escribe en el fuente directamente. Sin refresh, sin abort, sin frontmatter.
- **Render HTML al cloud** (`orbit render` o `commit`) lee el fuente en ese momento. Si no es accesible (disco desmontado, fuente borrada), usa el último mirror cacheado en `.cache/notes/<proj>/` y emite warning.

Gestión:

```bash
tracked list                          # listar externas con status
tracked list next-kr                  # solo un proyecto
untrack next-kr calibration.md        # quita el symlink (fuente intacta)
tracked migrate                       # one-shot v0.34 → v0.36 (si vienes de la copia antigua)
```

**Cross-links**: si `DECISIONS.md` (externa) tiene `[RING](RING.md)`, el link resuelve si **también** trackeas `RING.md` desde el mismo dir. Render avisa de cross-links a no-tracked.

**Limitación**: solo ficheros `.md`. Git no diffea binarios útilmente y el render solo procesa markdown. Para PDFs que cambian, usa `orbit deliver` con re-entrega cuando haga falta.

**Diseño completo** en `DECISIONS.md` ADR-024.

### Clip — copiar al portapapeles

```bash
clip date                  # fecha de hoy YYYY-MM-DD al portapapeles
clip date next friday      # fecha del próximo viernes
clip week                  # semana ISO YYYY-Wnn al portapapeles
clip next-kr               # enlace markdown al proyecto
clip next-kr notes/result.md  # enlace a un fichero del proyecto
```

### Cronogramas

Tareas anidadas con dependencias y duración temporal. Útiles para descomponer metas grandes en subtareas y seguir el progreso:

```bash
crono add next-kr "plan-calibracion"    # crea cronograma
crono show next-kr "plan"               # muestra con fechas calculadas
crono edit next-kr "plan"               # abre en editor
crono gantt next-kr "plan"              # visualiza progreso o timeline
crono done next-kr "plan"               # selección interactiva de tarea
crono done next-kr "plan" 1.2           # marca tarea 1.2 directamente
crono done next-kr "plan" katrin        # busca por texto parcial
crono check next-kr "plan"              # valida dependencias y ciclos
crono reindex next-kr "plan"            # renumera índices automáticamente
crono list next-kr                      # lista cronogramas del proyecto
```

#### Ejemplo: construir un cronograma paso a paso

Supongamos que tienes un hito "paper deadline" el 30 de mayo y quieres desglosar el trabajo:

**1. Crear el cronograma:**

```bash
crono add next-kr "paper-jinst"
```

Esto crea `cronos/crono-paper-jinst.md` con una plantilla. Ábrelo:

```bash
crono edit next-kr "paper"
```

**2. Editar el fichero en Obsidian/editor:**

Puedes empezar en modo DAG (solo estructura, sin fechas) para pensar en las subtareas. Añade `deadline` para activar el seguimiento de ritmo:

```markdown
# Cronograma: paper-jinst

deadline: 2026-05-30

- [ ] 1 Paper JINST
  - [ ] 1.1 Analisis
    - [ ] 1.1.1 Reproducir resultados MC
    - [ ] 1.1.2 Fit sistematicos
    - [ ] 1.1.3 Tablas y figuras finales
  - [ ] 1.2 Escritura | after:1.1
    - [ ] 1.2.1 Introduccion y estado del arte
    - [ ] 1.2.2 Seccion de metodo
    - [ ] 1.2.3 Resultados y discusion
    - [ ] 1.2.4 Conclusiones
  - [ ] 1.3 Revision | after:1.2
    - [ ] 1.3.1 Revision interna del grupo
    - [ ] 1.3.2 Correciones
    - [ ] 1.3.3 Revision de ingles
  - [ ] 1.4 Envio | after:1.3
```

Nota: `after:` en los padres (`1.2`, `1.3`) se hereda a sus hojas. No necesitas repetirlo en cada subtarea.

**3. Ver el progreso:**

```bash
crono gantt next-kr "paper"     # barra de progreso por seccion
crono show next-kr "paper"      # tabla con estado
```

**4. Ir completando tareas:**

```bash
crono done next-kr "paper"            # elige de la lista interactiva
crono done next-kr "paper" MC         # busca "MC" entre las pendientes
crono done next-kr "paper" 1.1.2      # por indice exacto
```

**5. Cuando quieras añadir fechas**, edita el fichero y pon duraciones en las hojas:

```markdown
deadline: 2026-05-30
exclude: sat, sun

- [ ] 1 Paper JINST
  - [ ] 1.1 Analisis
    - [ ] 1.1.1 Reproducir resultados MC | 2026-05-05 | 3d
    - [ ] 1.1.2 Fit sistematicos | after:1.1.1 | 2d
    - [ ] 1.1.3 Tablas y figuras finales | after:1.1.2 | 2d
  - [ ] 1.2 Escritura | after:1.1
    - [ ] 1.2.1 Introduccion y estado del arte | | 2d
    ...
```

Ahora `crono gantt --timeline` muestra un Gantt con eje temporal y `crono show` calcula las fechas.

**6. Si renumeras o reorganizas**, usa `crono reindex` para arreglar los indices:

```bash
crono reindex next-kr "paper"   # corrige huecos, actualiza after:
```

El progreso del cronograma aparece automaticamente en `orbit panel`. Con `deadline`, orbit calcula el ritmo necesario y avisa si vas retrasado (`⚠️ deadline 2026-05-30 (14d) — 8 pendientes, ritmo: 0.6/dia`). Los cronogramas completados al 100% se ocultan del panel automaticamente.

### Listados

```bash
ls projects                # lista de proyectos con estado
ls tasks                   # tareas pendientes de todos los proyectos
ls tasks --unplanned       # tareas sin fecha (futuribles)
ls ms                      # hitos pendientes
ls files next-kr           # ficheros del proyecto con estado git
ls notes next-kr           # notas con estado git
```

### Documentación

```bash
help                       # chuleta de comandos (terminal, paginado)
help chuleta               # equivalente (paginado)
help tutorial              # tutorial en terminal (paginado)
help about                 # README en terminal (paginado)
help --open                # abre CHULETA.md en el editor
help tutorial --open       # abre TUTORIAL.md en el editor
```

---

## 14. Servicios externos y mantenimiento

Orbit gestiona automáticamente la conexión con servicios externos: sincroniza citas con Google, versiona con git, renderiza a cloud y programa notificaciones en el Mac. No necesitas pensar en ello durante el día — Orbit se encarga al arrancar la shell, al operar sobre citas y al hacer commit.

Los comandos de esta sección son para **configurar** los servicios la primera vez o para **diagnosticar** si algo no funciona.

### Git — versionado y backup

Al hacer `commit`, Orbit valida los ficheros (doctor), reconcilia los IDs de Google y guarda en git. Es lo único que haces manualmente:

```bash
commit                     # muestra cambios, pide confirmación, genera mensaje
commit "feat: calibración validada"   # con mensaje directo
undo                       # deshacer la última operación de Orbit
```

Para hacer push al remoto, usa `orbit_push` desde la terminal del sistema (fuera de la shell). Si hay cambios sin commit, hace commit primero.

### Reorganizar tareas (`reorganize`)

Cuando llegas por la mañana y tienes vencidas + las del día por delante, lo más rápido es:

```bash
reorganize                # lista hoy + vencidas, te deja moverlas/cerrarlas una a una
reorganize ev -P week     # solo eventos de esta semana
reorganize -p santiago    # solo el proyecto santiago
```

El bucle: te lista, eliges número, acción rápida (`d` drop, `n` done, `f` fecha, `h` hora, `s` skip), vuelve a la lista. Sale con `q`. Cada cambio se sincroniza al momento a Calendar/Reminders.

Para editar título o notas → sal de reorganize y usa `task edit "X" --desc "..."` directo.

### Calendar.app (vía suscripción `.ics`)

Desde v0.33 orbit emite ficheros `.ics` al cloud y Calendar.app se suscribe a su URL pública. **Calendar.app no edita nada**: la suscripción es de solo lectura por construcción. Tú mantienes `agenda.md` como fuente de verdad y lo que pase por `task add`, `ev edit`, `ms done`, etc. se refleja en Calendar.app en ≤5 min (o al instante con `Cmd+R`).

**Topología** (en `cloud_root/calendar/`):

- `events.ics` — solo eventos
- `ms.ics` — solo milestones (calendario aparte para que destaquen con color propio)
- `agenda.ics` — tareas + recordatorios + cronogramas
- `projects/<proyecto>.ics` — per-proyecto, todas las citas (para compartir refs puntuales)

**Configuración**: `calendar-sync.json` en la raíz del workspace:

```json
{
  "ics_buckets": {
    "events": ["event"],
    "ms":     ["milestone"],
    "agenda": ["task", "reminder", "cronograma"]
  }
}
```

**Suscripción desde Calendar.app** (receta probada en orbit-ws con OneDrive USC):

1. En OneDrive web → click derecho sobre el `.ics` → Compartir → `Cualquier persona con el enlace`.
2. Copia el enlace.
3. Conviértelo para Calendar.app: cambia `https://` por `webcal://` y añade `&download=1` al final.
4. Calendar.app → `Archivo → Nueva suscripción de calendario` → pega el `webcal://`. Refresh = `Cada 5 minutos`. Color a elección (sugerencia: azul=events, amarillo=ms, gris=agenda).

**Propagación a iPhone/iPad**: ve a `icloud.com/calendar` web, sidebar → click derecho en `Calendarios` → `Nueva suscripción` → pega el mismo URL. Aparecerá automáticamente en todos tus Apple devices.

**Auto-regen**: cualquier mutación CLI (`task add`, `ev edit`, `ms done`, `crono done`, ...) dispara una reescritura del `.ics` en background. Igual `orbit commit`, `orbit render`, `orbit dash`. Si necesitas forzar manualmente:

```bash
orbit ics --workspace             # regenera todos los .ics
orbit ics --validate              # dry-run: cuenta VEVENTs por bucket
orbit ics phd-diego --out a.ics   # exporta un proyecto a fichero
```

**Identificar una cita** desde la UI: el `[orbit:xxxxxxxx]` al final de la `Descripción` del evento corresponde al tag homónimo en `agenda.md`. Si ves algo raro en Calendar.app, copia ese orbit-id y vienes a orbit.

**Servicios deprecados (v0.33)**: `gsync` (AppleScript-write a Calendar.app/Reminders.app) y `calsync` (auditoría de drift) quedan dormantes. Los comandos siguen ahí pero solo se activan si pones `"applescript_writes": true` en `calendar-sync.json`. La ruta por defecto es la suscripción `.ics`.

Orbit es la fuente de verdad. Calendar.app es sólo render: para reorganizar tareas usa el CLI (`task edit`, `ev edit`, ...) o el modo interactivo `orbit reorganize`.

### Cloud (OneDrive/Google Drive)

Tras cada `commit`, Orbit renderiza los markdown a HTML y los copia al cloud automáticamente. Puedes consultar proyectos, agendas y logbooks desde el móvil abriendo `index.html` en la app de cloud.

**Configuración**: `"cloud_root"` en `orbit.json` apunta al directorio del servicio de nube.

**Comandos manuales** (primera vez o para forzar):

```bash
render --full              # renderiza todo (primera vez)
render next-kr             # renderiza un proyecto concreto
deliver next-kr paper.pdf  # entrega un fichero al cloud del proyecto
```

También puedes entregar ficheros directamente desde `log` y `hl add` con `--deliver`.

### Mac Reminders

Orbit programa notificaciones en Reminders.app automáticamente al entrar en la shell: recorre las citas del día (de todos los workspaces) y las programa en el Mac.

Al crear citas con `--time`, Orbit pregunta si quieres un recordatorio (por defecto 5 minutos antes). También puedes especificarlo directamente con `--ring`:

```bash
task add next-kr "Reunión" --date tomorrow --time 10:00 --ring 30m
```

### Cartero — notificaciones de correo

El cartero vigila tu correo (Gmail/Outlook) y canales de Slack, y te avisa desde la shell cuando hay mensajes nuevos. No es un cliente — para leer los mensajes, abre la aplicación correspondiente.

**Configuración** en `orbit.json`:

```json
"cartero": {
  "gmail": {
    "labels": ["🏠 hogar", "🤗  Eva y familia", "🧳 viajes"],
    "interval": 600
  },
  "slack": {
    "channels": ["general", "alertas"],
    "interval": 600
  }
}
```

- **Gmail**: requiere habilitar la API de Gmail en Google Cloud Console y tener `credentials.json` en el workspace. Los nombres de etiqueta deben ser exactos (usa `labels.list` de la API para verlos).
- **Slack**: requiere un user token (`xoxp-...`) guardado en `ORBIT_HOME/.slack-token`. Se obtiene creando una Slack App con scopes `channels:read` y `groups:read`.

Al arrancar la shell, el cartero se lanza en background y revisa cada 10 minutos. Si hay mensajes no leídos, verás un indicador en el prompt:

```
🚀[📬7] > _
```

Y una notificación macOS cuando lleguen mensajes nuevos.

**Comandos manuales**:

```bash
mail                       # check ahora: muestra conteo por fuente (detallado)
mail --summary             # check en vivo, resumen compacto (una línea por fuente)
mail --status              # ¿está corriendo el background?
mail --stop                # para el background
mail --start               # arranca el background
```

### Doctor y archive — mantenimiento interno

Doctor valida la sintaxis de los ficheros y se ejecuta automáticamente al arrancar y antes de cada commit. Solo lo ejecutas manualmente si quieres revisar o corregir:

```bash
doctor                     # valida logbook, agenda y highlights
doctor --fix               # ofrece corregir errores detectados
```

Archive limpia entradas antiguas (tareas completadas, logbook viejo, notas sin modificar):

```bash
archive                    # archiva todo (pregunta por cada categoría)
archive --dry-run          # muestra qué se archivaría sin borrar
archive next-kr --months 3 # solo un proyecto, antigüedad 3 meses
```

---

## 15. Federación de workspaces — ver citas de otro espacio

Si tienes más de un workspace (por ejemplo, uno de trabajo y otro personal), puedes federar uno desde el otro para ver sus citas en panel, agenda y otros comandos de lectura.

### Configurar la federación

Crea `federation.json` en la raíz del workspace desde el que quieres ver el otro:

```json
{
  "federated": [
    {"name": "personal", "path": "~/🌿orbit-ps", "emoji": "🌿"}
  ]
}
```

Puedes federar varios workspaces añadiendo más entradas al array.

### Qué incluye y qué no

La federación es **solo lectura**. Los proyectos federados aparecen automáticamente en los comandos de consulta:

```bash
panel                      # incluye citas de ambos workspaces
agenda                     # incluye citas de ambos workspaces
ls tasks                   # tareas pendientes de todos los workspaces
search "reunión"           # busca en todos los workspaces
report week                # actividad de todos los workspaces
```

Pero **no puedes crear, editar ni borrar** citas o notas de proyectos federados. Los comandos de escritura (`add`, `edit`, `done`, `drop`, `log`, `note`) solo operan en el workspace activo. Para modificar un proyecto federado, entra en su workspace directamente.

Los proyectos federados se distinguen visualmente con el emoji del workspace (🌿) en vez de un link al `project.md`.

### Desactivar la federación puntualmente

```bash
agenda --no-fed            # solo citas del workspace activo
panel --no-fed             # solo proyectos del workspace activo
```

### Notificaciones Mac

Al entrar en la shell, Orbit programa las notificaciones (`ring`) del día de **ambos** workspaces, no solo el activo. Así no te pierdes recordatorios del espacio personal mientras trabajas.

---

## Referencia rápida

Ver `CHULETA.md` para la referencia completa de todos los comandos.

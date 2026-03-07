# Orbit — Tutorial para nuevos usuarios

Orbit es un sistema de gestión de proyectos científicos basado en ficheros markdown planos. Todo se guarda localmente, se versiona con git y se visualiza en Typora.

---

## 1. Primeros pasos — instalar y configurar

### Requisito previo

Añade la función `orbit` a tu `~/.zshrc`:

```zsh
orbit() {
    if [[ "$1" == "claude" ]]; then
        cd /Users/TU_USUARIO/Orbit && claude
    elif [[ $# -eq 0 ]]; then
        python3 /Users/TU_USUARIO/Orbit/orbit.py shell
    else
        python3 /Users/TU_USUARIO/Orbit/orbit.py "$@"
    fi
}
```

Recarga la shell:

```bash
source ~/.zshrc
```

### Entrar en Orbit

```bash
orbit
```

Al entrar se abre el shell interactivo `🚀` y se crea (o abre) automáticamente la nota del día en Typora.

---

## 2. El proyecto Mission

Orbit incluye un proyecto especial llamado **mission** (`☀️`). Es el proyecto raíz donde van:

- Las tareas generales que no pertenecen a ningún proyecto concreto.
- Los recordatorios generales.
- Un resumen automático de los reportes semanal y mensual.

No necesitas crearlo — ya existe. Cuando añades una tarea sin especificar proyecto, va a mission.

---

## 3. Crear tu primer proyecto

```bash
orbit create project --name next-kr --type investigacion --priority alta
```

Tipos disponibles: `investigacion` · `docencia` · `gestion` · `formacion` · `software` · `personal`

Prioridades: `alta` · `media` · `baja`

Esto crea la carpeta `🚀proyectos/🌀next-kr/` con dos ficheros:

- `🌀next-kr.md` — índice del proyecto (objetivo, tareas, referencias, resultados, decisiones, recordatorios)
- `📓next-kr.md` — logbook cronológico

Abre el proyecto en Typora y rellena el **objetivo**:

```bash
orbit open next-kr
```

---

## 4. La nota diaria

### Crear la nota del día

```bash
orbit create day
```

Orbit crea la nota diaria en `☀️mision-log/diario/YYYY-MM-DD.md`. Si no existe la nota semanal o mensual, las crea en cascada automáticamente.

La nota incluye:
- El proyecto en foco heredado de la nota semanal.
- Las tareas próximas con fecha.
- Los eventos del calendario (si está configurado).

### Rutina diaria recomendada

```bash
# Al empezar el día:
orbit                          # entra al shell y abre la nota del día

# Durante el día — anotar cosas:
orbit log next-kr "El fit converge con N=500" --entry resultado
orbit log "Llamar a la secretaría"             # sin proyecto → va al diario

# Añadir una tarea:
orbit add task next-kr "Reproducir figura 3" --date "next friday"

# Añadir una tarea para hoy (también aparece en el diario):
orbit add task "Revisar email de Diego" --date today

# Al final del día — inyectar resumen:
orbit report day --inject
```

---

## 5. Gestión de tareas

### Añadir tareas

```bash
orbit add task next-kr "Reproducir figura 3" --date "2026-03-15"
orbit add task "Llamar al banco"               # sin fecha → solo en el proyecto
orbit add task "Reunión de grupo" --date today # → proyecto + diario de hoy
```

### Modificar y cerrar tareas

```bash
# Reprogramar:
orbit change task schedule next-kr "Reproducir figura" --date "next monday"

# Marcar como completada:
orbit change task close next-kr "Reproducir figura"
```

### Ver tareas pendientes

```bash
orbit list tasks                         # todas
orbit list tasks --project next-kr       # de un proyecto
orbit list tasks --priority alta         # filtrar por prioridad
```

---

## 6. Recordatorios (rings)

Los recordatorios son como tareas pero con hora, y se programan automáticamente en **Reminders.app** de macOS cuando son para hoy.

```bash
# Añadir un recordatorio:
orbit add ring next-kr "Reunión semanal del grupo" --date "next monday" --time 09:00

# Con recurrencia:
orbit add ring "Standup diario" --date today --time 08:30 --recur daily
orbit add ring next-kr "Revisión mensual" --date "2026-04-01" --time 10:00 --recur monthly

# Reprogramar / cerrar:
orbit change ring schedule next-kr "Reunión semanal" --date "next monday" --time 09:00
orbit change ring close next-kr "Reunión semanal"
```

Reglas de recurrencia: `daily` · `weekly` · `monthly` · `yearly` · `weekdays` · `every:3d` · `every:2w`

---

## 7. Anotar en el logbook

El logbook es el historial cronológico de cada proyecto. Cada entrada tiene un tipo:

| Tipo | Uso |
|------|-----|
| `resultado` | Resultado obtenido |
| `idea` | Idea nueva |
| `problema` | Problema encontrado |
| `decision` | Decisión tomada |
| `referencia` | Paper, enlace o recurso |
| `tarea` | Tarea a realizar |
| `apunte` | Nota general |

```bash
orbit log next-kr "σ/E = 2.3% @ 1 MeV con N=500" --entry resultado
orbit log next-kr "El fit no converge con dataset completo" --entry problema
orbit log next-kr "Usaremos calibración relativa" --entry decision
orbit log next-kr "Gonzalez 2024 tiene la figura que necesitamos" --entry referencia

# Sin proyecto → va al diario de hoy:
orbit log "Reunión productiva con Diego"
```

---

## 8. Buscar en los logbooks

```bash
orbit search "calibración"                          # busca en todos los proyectos
orbit search "fit" --project next-kr                # en un proyecto concreto
orbit search "resolución" --entry resultado         # filtrar por tipo
orbit search --from "last month" --to today         # por rango de fechas
orbit search "sigma" --type investigacion           # por tipo de proyecto
```

---

## 9. Notas semanal y mensual

### Nota semanal

```bash
orbit create week
```

Crea `☀️mision-log/semanal/YYYY-Wnn.md` con los proyectos en foco (heredados del mensual o elegidos interactivamente) y las tareas próximas de las siguientes 2 semanas.

### Nota mensual

```bash
orbit create month
```

Crea `☀️mision-log/mensual/YYYY-MM.md` con los 3 proyectos más activos como foco del mes.

### Reportes

```bash
orbit report day    --inject   # inyecta actividad del día en la nota diaria
orbit report week   --inject   # inyecta actividad de la semana en la nota semanal
orbit report month  --inject   # inyecta actividad del mes en la nota mensual
orbit report status            # tabla de todos los proyectos con actividad reciente
orbit report status --apply    # aplica las propuestas de cambio de estado/prioridad
```

El reporte semanal y mensual quedan registrados automáticamente en el logbook de **mission**.

---

## 10. Listar proyectos y secciones

```bash
orbit list projects                          # todos los proyectos ordenados por prioridad
orbit list projects --type investigacion     # filtrar por tipo
orbit list projects --status "en marcha"     # filtrar por estado
orbit list tasks                             # todas las tareas pendientes
orbit list rings                             # todos los recordatorios
orbit list refs    next-kr                   # referencias de un proyecto
orbit list results next-kr                   # resultados de un proyecto
orbit list decisions                         # decisiones de todos los proyectos
```

---

## 11. Cambiar estado y prioridad de proyectos

```bash
orbit change status "en marcha" next-kr next-gala
orbit change status parado --from-status esperando   # cambia todos los que estén esperando
orbit change priority alta next-kr
orbit change type gestion appec
```

Estados: `inicial` · `en marcha` · `parado` · `esperando` · `durmiendo` · `completado`

---

## 12. Abrir ficheros

```bash
orbit open                        # diario de hoy en Typora
orbit open next-kr                # proyecto en Typora
orbit open next-kr --log          # logbook del proyecto
orbit open 2026-W10               # nota semanal
orbit open 2026-03                # nota mensual

# Ver en terminal:
orbit open next-kr --terminal
orbit open next-kr --terminal --log --entry resultado   # filtrar entradas
```

---

## 13. Calendario visual

Genera una vista de calendario con tus tareas y recordatorios y la abre en Typora:

```bash
orbit calendar week              # semana actual
orbit calendar month             # mes actual
orbit calendar year              # año actual

orbit calendar week --date "next week"
orbit calendar month --date 2026-04
```

Los días con eventos aparecen en **negrita** en la rejilla mensual. Los ficheros se guardan en `☀️mision-log/`.

---

## 14. Documentación integrada

```bash
orbit info chuleta    # abre la chuleta de comandos en Typora
orbit info about      # abre el README en Typora
orbit info tutorial   # abre este tutorial en Typora
orbit info help       # muestra el help completo de orbit
```

---

## 15. Automatización diaria con cron

Para que la nota del día se cree sola cada mañana a las 8:00 (lunes a viernes):

```bash
crontab -e
```

Añade:

```
0 8 * * 1-5 cd /Users/TU_USUARIO/Orbit && python3 orbit.py create day --no-open
```

Si la nota ya existe (porque la has creado antes), el cron no hace nada.

---

## 16. Flujo de trabajo completo — ejemplo típico

```
Lunes por la mañana
───────────────────
orbit                              # abre shell + nota del día

# Revisar tareas pendientes:
list tasks --priority alta

# Anotar resultados del experimento:
log next-kr "Resolución del detector: 2.1% @ 511 keV" --entry resultado

# Reprogramar una reunión:
change ring schedule next-kr "Reunión grupo" --date "next thursday" --time 10:00

# Añadir una idea nueva:
log next-kr "Probar con diferentes regiones de interés para mejorar S/N" --entry idea

Viernes por la tarde
────────────────────
report week --inject               # resumen semanal en la nota
open 2026-W10                      # revisar la semana en Typora
```

---

## Referencia rápida

Ver `CHULETA.md` para la referencia completa de todos los comandos.

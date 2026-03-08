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

### Notas de día, semana y mes

Al entrar en el shell de Orbit (`orbit`), las notas se crean automáticamente en cascada si no existen: primero el mes, luego la semana, luego el día. En cada paso se puede seleccionar el foco interactivamente.

La nota del día incluye:
- El proyecto en foco seleccionado al entrar.
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

# Al salir del shell, el reporte del día se inyecta automáticamente
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

## 6. Tareas con alarma (rings)

Las tareas con alarma son tareas normales con la flag `--ring`. Cuando son para hoy, se programan automáticamente en **Reminders.app** de macOS.

```bash
# Añadir una tarea con alarma:
orbit add task next-kr "Reunión semanal del grupo" --date "next monday" --ring
# Si omites --time, Orbit te pide la hora en el prompt (defecto 09:00)

# Con hora explícita:
orbit add task next-kr "Reunión semanal" --date "next monday" --time 09:00 --ring

# Con recurrencia:
orbit add task "Standup diario" --date today --ring --recur daily
orbit add task next-kr "Revisión mensual" --date "2026-04-01" --time 10:00 --ring --recur monthly

# Reprogramar / cerrar (igual que tareas normales):
orbit change task schedule next-kr "Reunión semanal" --date "next monday" --time 09:00
orbit change task close next-kr "Reunión semanal"
```

Al reprogramar o cerrar una tarea recurrente, Orbit pregunta si quieres mantener, cambiar o eliminar la recurrencia.

Las tareas con alarma aparecen marcadas con ⏰ en los listados. Para ver solo las alarmas:

```bash
orbit list tasks --ring
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

### Nota mensual

Crea `☀️mision-log/mensual/YYYY-MM.md` con los 3 proyectos más activos como foco del mes.

El reporte semanal y mensual quedan registrados automáticamente en el logbook de **mission**.

---

## 10. Listar proyectos y secciones

```bash
orbit list projects                          # todos los proyectos ordenados por prioridad
orbit list projects --type investigacion     # filtrar por tipo
orbit list projects --status "en marcha"     # filtrar por estado
orbit list tasks                             # todas las tareas pendientes
orbit list tasks --ring                      # solo tareas con alarma (⏰)
```

---

## 11. Cambiar estado y prioridad de proyectos

```bash
```

Estados: `inicial` · `en marcha` · `parado` · `durmiendo` · `completado`

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

Orbit gestiona automáticamente la creación de notas al entrar en el shell. No es necesario configurar un cron.

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
change task schedule next-kr "Reunión grupo" --date "next thursday" --time 10:00

# Añadir una idea nueva:
log next-kr "Probar con diferentes regiones de interés para mejorar S/N" --entry idea

Viernes por la tarde
────────────────────
open 2026-W10                      # revisar la semana en Typora
```

---

## Referencia rápida

Ver `CHULETA.md` para la referencia completa de todos los comandos.

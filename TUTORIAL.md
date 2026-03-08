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
- Las **notas de evaluación** generadas por `orbit end` y `orbit eval`.

No necesitas crearlo — ya existe. Cuando añades una tarea sin especificar proyecto, va a mission.

---

## 3. Crear tu primer proyecto

```bash
orbit create project --name next-kr --type investigacion --priority alta
```

Tipos disponibles: `investigacion` · `docencia` · `gestion` · `formacion` · `software` · `personal`

Prioridades: `alta` · `media` · `baja`

Esto crea la carpeta `🚀proyectos/🌀next-kr/` con dos ficheros:

- `🌀next-kr.md` — índice del proyecto (objetivo, tareas, referencias, resultados, decisiones)
- `📓next-kr.md` — logbook cronológico

Abre el proyecto en Typora y rellena el **objetivo**:

```bash
orbit open next-kr
```

---

## 4. Rutina de sesión — start y end

La forma recomendada de trabajar con Orbit es arrancar con `orbit start` y terminar con `orbit end`.

### orbit start

```bash
orbit start
```

Al ejecutarlo, Orbit:

1. Muestra un **resumen del estado de los proyectos** (cuántos activos, parados, durmiendo).
2. Muestra el **foco actual** para el mes, la semana y el día.
3. Si algún período no tiene foco establecido, **pregunta si quieres definirlo ahora**.
4. Si ayer hubo actividad en el logbook pero no se generó evaluación, **ofrece crearla**.

### orbit end

```bash
orbit end
```

Al ejecutarlo, Orbit:

1. Muestra la **actividad de hoy** en los proyectos en foco.
2. Crea o actualiza la **nota de evaluación** del día en `☀️mission/diario/`.
3. Si es fin de semana (vie/sáb/dom), genera también la evaluación **semanal**.
4. Si es fin de mes (últimos 3 días), genera también la evaluación **mensual**.
5. Abre la nota de evaluación de mayor prioridad en Typora.

### Flujo completo de un día de trabajo

```
08:30  orbit start         → estado + foco + agenda
         orbit agenda      → ver tareas del día

       ... trabajar, anotar ...

17:00  orbit end           → resumen + nota de evaluación
         → Typora se abre con la nota de evaluación para reflexionar
```

---

## 5. Foco de proyectos

El foco determina qué proyectos son prioritarios en cada período. Se guarda en `.orbit/focus.json` y es la fuente de verdad que usan `agenda`, `eval`, `status --focus` y `end`.

### Ver el foco actual

```bash
orbit focus
```

Muestra el foco establecido para el mes, la semana y el día actual.

### Establecer el foco

```bash
orbit focus month --set orbit mission    # proyectos en foco este mes
orbit focus week  --set orbit            # foco de esta semana
orbit focus day   --set orbit            # foco de hoy
```

Los nombres de proyecto se resuelven por coincidencia parcial (igual que todos los demás comandos).

### Selección interactiva

```bash
orbit focus month --interactive
```

Muestra la lista de proyectos disponibles y permite seleccionarlos por número o nombre parcial.

### Ver o limpiar un período

```bash
orbit focus week           # solo el foco semanal
orbit focus day --clear    # elimina el foco del día
```

---

## 6. Estado de salud de proyectos

```bash
orbit status
```

Muestra todos los proyectos agrupados por actividad real (basada en el logbook):

- 🟢 **Activo** — actividad en los últimos 30 días.
- 🟡 **Parado** — sin actividad en 30 días, pero sí en 60.
- 🔴 **Durmiendo** — sin actividad en 60 días.

```bash
orbit status --focus           # solo proyectos en foco
orbit status --project next-kr # un proyecto concreto
```

Útil para revisar el estado real del portfolio antes de decidir el foco.

---

## 7. Agenda de planificación

```bash
orbit agenda
```

Muestra la agenda del día: tareas de hoy, vencidas y próximas 7 días. Los proyectos en foco aparecen marcados con 🎯.

```bash
orbit agenda day               # equivalente al anterior
orbit agenda week              # semana actual, agrupada por día
orbit agenda month             # mes actual, agrupado por semana
orbit agenda --date 2026-03-15 # una fecha concreta
orbit agenda day --ring        # hoy + programa @ring en Reminders.app
```

La agenda es siempre dinámica — nunca escribe en tus notas.

---

## 8. Notas de evaluación

Las evaluaciones son notas generadas en `☀️mission/diario/`, `semanal/` y `mensual/`. Tienen dos partes:

- **Estadísticas** (auto-actualizadas): actividad en los proyectos en foco.
- **Reflexión** (solo se crea una vez): secciones en blanco para que el usuario las complete.

El usuario escribe en la sección de reflexión. Orbit nunca sobreescribe ese texto.

### Generar evaluaciones manualmente

```bash
orbit eval day                  # evaluación del día
orbit eval week                 # evaluación de la semana
orbit eval month                # evaluación del mes
orbit eval                      # las tres a la vez
orbit eval day --date 2026-03-07 --no-open   # día concreto, sin abrir
```

`orbit end` llama a `orbit eval` automáticamente con el período correcto.

---

## 9. Anotar en el logbook

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

## 10. Gestión de tareas

### Añadir tareas

```bash
orbit add task next-kr "Reproducir figura 3" --date "2026-03-15"
orbit add task "Llamar al banco"               # sin fecha → solo en el proyecto
orbit add task "Reunión de grupo" --date today # → proyecto + diario de hoy
```

### Modificar y cerrar tareas

```bash
orbit change task schedule next-kr "Reproducir figura" --date "next monday"
orbit change task close next-kr "Reproducir figura"
```

### Ver tareas pendientes

```bash
orbit list tasks                         # todas
orbit list tasks --project next-kr       # de un proyecto
orbit list tasks --priority alta         # filtrar por prioridad
```

---

## 11. Tareas con alarma (rings)

Las tareas con alarma son tareas normales con la flag `--ring`. Cuando son para hoy, se programan automáticamente en **Reminders.app** de macOS.

```bash
orbit add task next-kr "Reunión semanal del grupo" --date "next monday" --ring
orbit add task next-kr "Revisión mensual" --date "2026-04-01" --time 10:00 --ring --recur monthly
orbit list tasks --ring                   # ver solo alarmas
```

---

## 12. Buscar en los logbooks

```bash
orbit search "calibración"                          # busca en todos los proyectos
orbit search "fit" --project next-kr                # en un proyecto concreto
orbit search "resolución" --entry resultado         # filtrar por tipo
orbit search --from "last month" --to today         # por rango de fechas
orbit search "sigma" --type investigacion           # por tipo de proyecto
```

---

## 13. Listar proyectos y secciones

```bash
orbit list projects                          # todos los proyectos ordenados por prioridad
orbit list projects --type investigacion     # filtrar por tipo
orbit list projects --status "en marcha"     # filtrar por estado
orbit list tasks                             # todas las tareas pendientes
orbit list refs next-kr                      # referencias de un proyecto
orbit list decisions                         # decisiones de todos los proyectos
```

---

## 14. Abrir ficheros

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

## 15. Calendario visual

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

## 16. Documentación integrada

```bash
orbit info chuleta    # abre la chuleta de comandos en Typora
orbit info about      # abre el README en Typora
orbit info tutorial   # abre este tutorial en Typora
orbit info help       # muestra el help completo de orbit
```

---

## 17. Flujo de trabajo completo — ejemplo típico

```
Lunes por la mañana
───────────────────
orbit start                        # estado + foco + alerta sesión perdida
orbit focus month --set orbit mission next-kr   # si no estaba definido
orbit agenda                       # tareas del día (🎯 marca los proyectos en foco)

# Revisar estado del portfolio:
orbit status

# Anotar trabajo durante el día:
log next-kr "Resolución del detector: 2.1% @ 511 keV" --entry resultado
log next-kr "Probar con diferentes regiones de interés" --entry idea
add task next-kr "Preparar presentación para el grupo" --date "next thursday"

# Reprogramar una reunión:
change task schedule next-kr "Reunión grupo" --date "next thursday" --time 10:00

Lunes por la tarde
──────────────────
orbit end                          # resumen de actividad + nota de evaluación
# → Typora abre ☀️mission/diario/2026-03-09.md
# → Completar la sección de reflexión manualmente

Viernes por la tarde
────────────────────
orbit end                          # genera también la evaluación SEMANAL
# → Typora abre ☀️mission/semanal/2026-W11.md
```

---

## Referencia rápida

Ver `CHULETA.md` para la referencia completa de todos los comandos.

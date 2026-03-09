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

Se abre el shell interactivo `🚀`. Dentro del shell no necesitas el prefijo `orbit`.

---

## 2. Crear proyectos

```bash
project create next-kr --type investigacion --priority alta
```

Tipos: `investigacion` · `docencia` · `gestion` · `formacion` · `software` · `personal`

Esto crea `🚀proyectos/🌀next-kr/` con: `project.md`, `logbook.md`, `highlights.md`, `agenda.md` y `notes/`.

Abre el proyecto en Typora para completar el objetivo:

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

## 4. Empezar el día — revisar la agenda

```bash
agenda
```

Muestra las tareas pendientes y vencidas, eventos de hoy y hitos próximos de todos los proyectos.

```bash
agenda --date 2026-03     # agenda del mes completo
agenda --calendar         # vista calendario con colores
agenda --from monday --to friday   # rango personalizado
```

Con esto planificas el día: ves qué hay pendiente y qué vence pronto.

---

## 5. Trabajar y anotar — log

El logbook es el registro cronológico de cada proyecto. Cada entrada tiene un tipo:

| Tipo | Uso |
|------|-----|
| `resultado` | Resultado obtenido |
| `idea` | Idea nueva |
| `problema` | Problema encontrado |
| `decision` | Decisión tomada |
| `referencia` | Paper, enlace o recurso |
| `apunte` | Nota general |

```bash
log next-kr "σ/E = 2.3% @ 1 MeV con N=500" --entry resultado
log next-kr "El fit no converge con dataset completo" --entry problema
log next-kr "Usaremos calibración relativa" --entry decision
```

Para añadir una referencia con enlace a un fichero local:

```bash
log next-kr "González 2024 — calibración" --entry referencia --path ./refs/gonzalez2024.pdf
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

Las tareas con `--ring` se programan como alarma en Reminders.app de macOS.
Las tareas recurrentes (`--recur`) avanzan automáticamente al completarlas.

### Hitos

Los hitos son objetivos importantes. Úsalos en el proyecto `mission` para marcar el foco del día o la semana:

```bash
ms add mission "Foco: avanzar calibración next-kr" --date 2026-03-09
ms done mission "Foco"
```

### Eventos

```bash
ev add next-kr "Congreso JINST" --date 2026-04-15 --end 2026-04-18
ev list next-kr
```

---

## 7. Highlights — índice curado

Los highlights son el índice permanente de lo más relevante: referencias clave, resultados importantes, decisiones fundamentales.

```bash
hl add next-kr "González 2024 — calibración relativa" --type refs --link ./refs/g2024.pdf
hl add next-kr "σ/E = 2.3% @ 1 MeV" --type results
hl add next-kr "Calibración relativa como estándar" --type decisions
hl list next-kr
```

Tipos: `refs` · `results` · `decisions` · `ideas` · `evals`

---

## 8. Buscar

```bash
search "calibración"                                # en todos los proyectos
search "fit" --project next-kr                      # en un proyecto concreto
search "resolución" --entry resultado               # filtrar por tipo
search --from "last month" --to today               # por rango de fechas
search "sigma" --in highlights                      # buscar en highlights
search "calibración" --notes                        # incluir notas/
```

---

## 9. Ver proyectos

```bash
view next-kr              # resumen en terminal: estado, tareas, hitos, últimas entradas
view next-kr --open       # genera cmd.md y lo abre en Typora
open next-kr logbook      # abre el logbook en Typora
open next-kr highlights   # abre highlights en Typora
```

---

## 10. Al final del día — report

```bash
report
```

Muestra un informe de actividad de todos los proyectos (últimos 30 días por defecto):
entradas de logbook, tareas completadas/pendientes/vencidas, hitos y eventos.

```bash
report next-kr --from 2026-03-01 --to 2026-03-09
report --open                # abre el informe en Typora
report --log mission         # guarda el informe en el logbook de mission
```

Guardar el report en el logbook de `mission` es útil para tomar decisiones de gestión: al revisarlo puedes añadir una evaluación como highlight:

```bash
hl add mission "Semana productiva en next-kr, retrasar hk-sources" --type evals
```

---

## 11. Flujo de trabajo completo — ejemplo típico

```
Lunes por la mañana
───────────────────
orbit
  agenda                           # ver qué hay pendiente hoy
  project list                     # revisar estado del portfolio

  # Trabajar y anotar:
  log next-kr "σ/E = 2.1% @ 511 keV" --entry resultado
  log next-kr "Probar con diferentes ROI" --entry idea
  task add next-kr "Preparar presentación" --date "next thursday"
  hl add next-kr "Resolución validada a 511 keV" --type results

Lunes por la tarde
──────────────────
  report                           # ¿qué se ha hecho hoy?
  report --log mission             # guardar en logbook de mission
  commit                           # guardar cambios en git

Viernes por la tarde
────────────────────
  report --from monday --to friday # informe semanal
  report --from monday --to friday --log mission
  hl add mission "Buena semana: calibración avanzada, pendiente topo" --type evals
  commit
```

---

## 12. Otros comandos útiles

### Notas libres

```bash
note next-kr "Análisis detallado de calibración"   # crea nota en notes/
note list next-kr                                   # listar notas con estado git
```

### Listados

```bash
ls projects                # lista de proyectos con estado
ls tasks                   # tareas pendientes de todos los proyectos
ls ms                      # hitos pendientes
ls files next-kr           # ficheros del proyecto con estado git
ls notes next-kr           # notas con estado git
```

### Commit

```bash
commit                     # muestra cambios, pide confirmación, genera mensaje
commit "feat: calibración validada"
```

### Documentación

```bash
help                       # chuleta de comandos (terminal, paginado)
help chuleta               # abre CHULETA.md en Typora
help tutorial              # abre este tutorial en Typora
help about                 # abre README.md en Typora
```

---

## Referencia rápida

Ver `CHULETA.md` para la referencia completa de todos los comandos.

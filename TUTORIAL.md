# Orbit — Tutorial para nuevos usuarios

Orbit es un sistema de gestión de proyectos científicos basado en ficheros markdown planos. Todo se guarda localmente, se versiona con git y se visualiza en cualquier editor de markdown.

---

## 1. Primeros pasos — instalar y configurar

### Requisito previo

Añade estas líneas a tu `~/.zshrc`:

```zsh
export ORBIT_EDITOR=typora                          # tu editor de markdown preferido
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

Si no defines `ORBIT_EDITOR`, Orbit usará el abridor por defecto del sistema (`open` en macOS, `xdg-open` en Linux). También puedes usar `--editor` en cualquier comando para una apertura puntual.

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

## 4. Empezar el día — revisar la agenda

```bash
agenda
```

Muestra las tareas pendientes y vencidas, eventos de hoy y hitos próximos de todos los proyectos.

```bash
agenda --date 2026-03     # agenda del mes completo
agenda --calendar         # vista calendario con colores
agenda --from monday --to friday   # rango personalizado
agenda --dated                   # solo tareas/hitos con fecha
```

Con esto planificas el día: ves qué hay pendiente y qué vence pronto.

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
ev add next-kr "Dentista" --date 2026-03-25 --time 16:00
ev edit next-kr "Congreso" --date 2026-04-20
ev list next-kr
```

- `--time HH:MM` — evento con hora de inicio (1h por defecto en Google Calendar)
- `--time HH:MM-HH:MM` — evento con hora de inicio y fin
- Sin `--time` — evento de día completo (o multi-día con `--end`)

Los tres (task, ms, ev) comparten la misma interfaz: `--date`, `--recur`, `--until`, `--ring`.
Las tareas y hitos recurrentes avanzan automáticamente al completarlas.
Los eventos recurrentes se expanden automáticamente en la agenda y el calendario.
`--ring` programa una alarma en Reminders.app de macOS.

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
reminder list                       # lista recordatorios activos de todos los proyectos
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
view next-kr --open       # genera cmd.md y lo abre en el editor
open next-kr logbook      # abre el logbook en el editor
open next-kr highlights   # abre highlights en el editor
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
  log next-kr "Espectro calibrado" spectrum.png --entry resultado --deliver
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

### Undo — deshacer

```bash
undo                       # muestra operaciones y pregunta cuál deshacer
```

Orbit guarda el estado de los ficheros antes de cada operación. Al ejecutar `undo`, verás la lista numerada de operaciones deshacibles. Elige el número (1 = última, 2 = las dos últimas, etc.) o 0 para cancelar. Puedes deshacer hasta 20 operaciones por sesión.

### Doctor y archive

```bash
doctor                       # valida sintaxis de logbook, agenda y highlights
doctor --fix                 # ofrece corregir errores detectados

archive                      # archiva todo (pregunta por cada categoría)
archive next-kr --months 3   # solo un proyecto, antigüedad 3 meses
archive --agenda             # solo tareas/hitos completados + eventos pasados
archive --logbook            # solo entradas de logbook antiguas
archive --notes              # solo notas obsoletas
archive --dry-run            # muestra qué se archivaría sin borrar
archive --force              # salta confirmaciones
```

### Documentación

```bash
help                       # chuleta de comandos (terminal, paginado)
help chuleta               # abre CHULETA.md en el editor
help tutorial              # abre este tutorial en el editor
help about                 # abre README.md en el editor
```

---

## Referencia rápida

Ver `CHULETA.md` para la referencia completa de todos los comandos.

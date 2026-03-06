# 🚀 Orbit

Sistema personal de gestión de proyectos científicos y personales en markdown plano.

---

## Estructura

```
Orbit/
├── 🚀proyectos/
│   ├── INDEX.md                        ← tabla maestra de proyectos
│   └── nombre-proyecto/
│       ├── proyecto.md                 ← índice del proyecto
│       ├── logbook.md                  ← registro cronológico de entradas
│       ├── references/                 ← PDFs locales (no en git)
│       └── results/                    ← resultados numéricos (no en git)
├── ☀️mision-log/
│   ├── diario/YYYY-MM-DD.md            ← planificación del día
│   ├── semanal/YYYY-Wnn.md             ← revisión semanal
│   └── mensual/YYYY-MM.md              ← revisión mensual (generada por script)
├── 📐templates/                        ← plantillas para todos los ficheros
├── orbit.py                            ← CLI principal
└── core/                               ← módulos del CLI
```

---

## Tipos de proyecto

| Emoji | Tipo |
|-------|------|
| 🌀 | Investigación |
| 📚 | Docencia |
| ⚙️ | Gestión |
| 📖 | Formación |
| 💻 | Software |
| 🌿 | Personal |

---

## Estados y prioridades

**Estado:**
`⬜ Inicial` · `▶️ En marcha` · `⏸️ Parado` · `⏳ Esperando` · `💤 Durmiendo` · `✅ Completado`

**Prioridad:**
`🟠 Alta` · `🟡 Media` · `🔵 Baja`

---

## Logbook — tipos de entrada

Cada entrada es una línea con formato `YYYY-MM-DD mensaje #tipo`:

| Hashtag | Significado |
|---------|-------------|
| `#idea` | 💡 Idea nueva |
| `#referencia` | 📎 Paper, link o recurso |
| `#tarea` | ✅ Tarea a realizar |
| `#problema` | ⚠️ Problema encontrado |
| `#resultado` | 📊 Resultado obtenido |
| `#apunte` | 📝 Nota o apunte general |
| `#decision` | 🔀 Decisión tomada |

Ejemplo:
```
2026-03-06 Idea sobre calibración relativa #idea
2026-03-06 [Gonzalez 2024](./references/gonzalez2024.pdf) #referencia
2026-03-06 Reproducir figura 3 del paper #tarea
2026-03-06 El fit no converge con el dataset completo #problema
2026-03-06 Energy resolution σ/E = 2.3% @ 1 MeV #resultado
```

---

## Dinámica de trabajo

### Cada día
1. Abre o crea `☀️mision-log/diario/YYYY-MM-DD.md` desde la plantilla
2. Decide el proyecto en foco y las tareas del día
3. Registra entradas en el logbook del proyecto con `orbit log`

### Cada semana
1. Crea `☀️mision-log/semanal/YYYY-Wnn.md` desde la plantilla
2. Selecciona 2 proyectos en foco para la semana
3. Revisa qué salió bien, qué no, y arrastra tareas pendientes

### Cada mes
1. Ejecuta `python orbit.py monthly` — genera la tabla de actividad en `mensual/YYYY-MM.md`
2. Rellena la sección 🎯 Priorización al inicio del mes
3. Rellena la sección 🍅 Valoración al final del mes
4. Ejecuta con `--apply` si quieres actualizar los estados reales en `proyecto.md`

---

## CLI — orbit.py

### `log` — añadir entrada al logbook

```bash
python orbit.py log <proyecto> "<mensaje>" [--type TIPO] [--path RUTA] [--date YYYY-MM-DD]
```

```bash
python orbit.py log detector-xenon "El fit no converge" --type problema
python orbit.py log detector-xenon "Gonzalez 2024" --type referencia --path ./references/gonzalez2024.pdf
python orbit.py log 💻-orbit "Comando monthly implementado" --type resultado
```

### `list` — listar entradas del logbook

```bash
python orbit.py list <proyecto> [--type TIPO...] [--date YYYY-MM o YYYY-MM-DD] [--output FICHERO]
```

```bash
python orbit.py list detector-xenon
python orbit.py list detector-xenon --type tarea problema
python orbit.py list detector-xenon --date 2026-03
```

### `tasks` — listar tareas pendientes

```bash
python orbit.py tasks [--project PROYECTO] [--type TIPO] [--status ESTADO] [--priority PRIORIDAD] [--date FECHA] [--output FICHERO]
```

```bash
python orbit.py tasks
python orbit.py tasks --type investigacion
python orbit.py tasks --priority alta
python orbit.py tasks --date 2026-03
```

Tareas vencidas se marcan con `⚠️`. Tareas sin fecha de vencimiento aparecen con `—`.

### `activity` — informe de actividad por proyecto

```bash
python orbit.py activity [--project PROYECTO] [--type TIPO] [--priority PRIORIDAD] [--period FECHA [FECHA]] [--apply] [--output FICHERO]
```

```bash
python orbit.py activity
python orbit.py activity --period 2026-03
python orbit.py activity --period 2026-02 2026-03
python orbit.py activity --type investigacion --apply
```

Calcula el **estado real** y la **prioridad real** de cada proyecto según su actividad en el período:

| Estado nominal | Con actividad | Sin actividad |
|---|---|---|
| ⬜ Inicial | ▶️ En marcha | sin cambio |
| ▶️ En marcha | sin cambio | ⏸️ Parado |
| ⏸️ Parado | ▶️ En marcha | 💤 Durmiendo |
| ⏳ Esperando | sin cambio | sin cambio |
| 💤 Durmiendo | ▶️ En marcha | sin cambio |

La prioridad se degrada un nivel si no hay actividad en un período ≥ 30 días. Proyectos en `🔵 Baja` sin actividad desaparecen del listado.

`--apply` escribe los cambios directamente en `proyecto.md`.

### `monthly` — generar revisión mensual

```bash
python orbit.py monthly [--month YYYY-MM] [--apply] [--output FICHERO]
```

```bash
python orbit.py monthly
python orbit.py monthly --month 2026-02
python orbit.py monthly --apply
```

Crea `☀️mision-log/mensual/YYYY-MM.md` desde la plantilla si no existe, e inyecta la tabla de actividad entre los marcadores `<!-- orbit:monthly:start -->` y `<!-- orbit:monthly:end -->`.

---

## Convenciones

- **Tareas** en `proyecto.md`: `- [ ] Descripción (YYYY-MM-DD)` — la fecha es el vencimiento
- **Nombre de directorio** del proyecto: kebab-case con emoji de tipo opcional (`detector-xenon`, `💻-orbit`)
- **Referencias, figuras y resultados** binarios no se suben a git — solo el texto markdown
- **Fuente de verdad** de las tareas: sección `## ✅ Tareas` de `proyecto.md`
- **Fuente de verdad** del historial: logbook del proyecto

### Entradas multilínea en el logbook

Para entradas con varias líneas o listas, edita el logbook directamente. La fecha y el hashtag van en la primera línea; las líneas indentadas forman parte de la misma entrada:

```
2026-03-06 Resultados del fit de calibración #resultado
  - σ/E = 2.3% @ 1 MeV
  - σ/E = 1.8% @ 3 MeV
  - El modelo lineal ajusta bien en todo el rango
```

El comando `orbit log` sigue siendo útil para entradas rápidas de una línea.

# Orbit

Sistema personal de gestión de proyectos científicos en markdown plano.

---

## Arquitectura

Orbit separa **codigo** y **datos** en repositorios distintos:

```
~/orbit/              ← repo publico, solo codigo (este repo)
  orbit.py
  core/
  bin/                ← comandos auxiliares (deliver, ...)
  📐templates/
  tests/

~/mi-workspace/       ← repo privado, tus datos de trabajo
  {emoji}proyectos/
  orbit.json          ← space, emoji, cloud_root, tipos de proyecto
  google-sync.json    ← sincronizacion con Google
  credentials.json    ← Google API (gitignored)
  history.md
```

Puedes tener tantos workspaces como quieras. Todos comparten el mismo codigo.

Ver [SETUP.md](SETUP.md) para instrucciones de instalacion.

---

## Estructura de un workspace

```
mi-workspace/
├── {emoji}proyectos/
│   └── {emoji}nombre-proyecto/
│       ├── project.md        ← metadatos: tipo, estado, prioridad, objetivo + link a cloud
│       ├── logbook.md        ← registro permanente (append-only)
│       ├── highlights.md     ← indice curado: refs, resultados, decisiones, ideas
│       ├── agenda.md         ← tareas, hitos y eventos
│       └── notes/            ← notas libres del usuario (.md)
├── orbit.json                ← configuracion del workspace (space, emoji, cloud_root, tipos)
├── google-sync.json          ← mapa tipo → calendario de Google
├── history.md                ← historial de sesiones
└── cmd.md                    ← salida temporal de comandos --open
```

---

## Tipos de proyecto

Cada workspace se configura en `orbit.json`:

```json
{
  "space": "orbit-ws",
  "emoji": "🚀",
  "cloud_root": "~/Library/CloudStorage/OneDrive-.../🚀orbit-ws",
  "types": { "investigacion": "🌀", "docencia": "📚", ... }
}
```

- `space`: nombre del espacio (aparece en la ruta cloud)
- `emoji`: emoji del espacio (prefijo de `proyectos/` y del directorio cloud raiz)
- `cloud_root`: ruta al directorio raiz en el servicio de nube (OneDrive, Google Drive, etc.)

Los tipos se definen en `orbit.json` de cada workspace. Ejemplo:

| Emoji | Tipo | Uso |
|-------|------|-----|
| ☀️ | Mision | Proyecto raiz — gestion global, planificacion, evaluaciones |
| 🌀 | Investigacion | Proyectos de investigacion cientifica |
| 📚 | Docencia | Asignaturas, TFGs, tesis |
| ⚙️ | Gestion | Gestion, propuestas, comites |
| 📖 | Formacion | Cursos, lecturas, aprendizaje |
| 💻 | Software | Proyectos de software |
| 🌿 | Personal | Proyectos personales |

---

## Logbook — tipos de entrada (`--entry`)

| Tag | Emoji | Significado |
|-----|-------|-------------|
| `#idea` | 💡 | Idea nueva |
| `#referencia` | 📎 | Paper, link o recurso |
| `#apunte` | 📝 | Nota general |
| `#problema` | ⚠️ | Problema encontrado |
| `#solucion` | ✔️ | Solución a un problema |
| `#resultado` | 📊 | Resultado obtenido |
| `#decision` | 📌 | Decision tomada |
| `#evaluacion` | 🔍 | Evaluacion parcial |

---

## CLI — referencia de comandos

Ver `CHULETA.md` para la referencia rapida completa.

### Shell interactiva

```bash
worbit              # entra al shell del workspace de trabajo
porbit              # entra al shell del workspace personal
worbit ls           # ejecuta un comando sin entrar al shell
```

### Proyectos

```bash
orbit project create next-kr --type investigacion --priority alta
orbit project list [--status active] [--open]
orbit project status next-kr [--set paused]
orbit project edit next-kr
orbit project drop next-kr [--force]
```

### Tareas, hitos y eventos

Los tres tipos comparten la misma interfaz: `add`, `done` (excepto ev), `drop`, `edit`, `list`.
Todos aceptan `--date`, `--recur`, `--until` y `--ring`.

```bash
orbit task add next-kr "Reproducir figura" --date 2026-03-20 --ring 1d
orbit task add next-kr "Reunion semanal" --date 2026-03-15 --recur weekly
orbit task done next-kr "Reproducir"
orbit task list [next-kr] [--open]

orbit ms add next-kr "Calibracion validada" --date 2026-04-01 --ring 1d
orbit ms done next-kr
orbit ms list [--open]

orbit ev add next-kr "Congreso JINST" --date 2026-04-15 --end 2026-04-18 --ring 1d
orbit ev edit next-kr "Congreso" --date 2026-04-20
orbit ev list next-kr [--open]
```

### Recordatorios

```bash
orbit reminder add mission "¡Revisa el correo!" --date 2026-03-18 --time 17:00
orbit reminder add next-kr "Backup" --date 2026-03-20 --time 09:00 --recur weekly
orbit reminder edit mission "correo" --text "Nuevo título" --time 18:00
orbit reminder drop mission "correo"
orbit reminder list [project]
```

### Highlights y notas

```bash
orbit hl add next-kr "Gonzalez 2024" ./refs/g2024.pdf --type refs --deliver
orbit hl list next-kr [--open]

orbit note next-kr "Analisis de calibracion"
orbit note list next-kr [--open]
```

### Anotacion y busqueda

```bash
orbit log next-kr "El fit converge" --entry resultado
orbit log next-kr "Resultados Q1" results.pdf --entry resultado --deliver
orbit search "calibracion" --entry resultado
orbit search --project next-kr --from 2026-03-01 [--open]
```

### Vista y navegacion

```bash
orbit view [next-kr] [--open]
orbit open next-kr logbook
orbit open next-kr agenda
```

### Agenda y report

```bash
orbit agenda [--date D] [--from D] [--to D] [--calendar] [--dated] [--open]
orbit report [project...] [--from D] [--to D] [--open]
orbit report today                  # actividad de hoy
orbit report week                   # actividad de esta semana
orbit report month                  # actividad de este mes
```

### Date — fecha al portapapeles

```bash
orbit date                # 2026-03-20 (copiado al portapapeles)
orbit date wednesday      # próximo miércoles
orbit date in 2 weeks     # dentro de 2 semanas
```

### Render — vista HTML para móvil

```bash
orbit render                  # renderiza cambios del último commit
orbit render catedra          # renderiza un proyecto completo
orbit render --full           # renderiza todo (primera vez)
```

Tras cada `commit`, Orbit renderiza los `.md` modificados a HTML y los copia al cloud (OneDrive/Google Drive). Desde el móvil/tablet, abre `index.html` en la app de cloud para navegar proyectos, agendas, logbooks y notas — con soporte LaTeX (KaTeX).

Los `inbox.md` en cloud permiten capturar ideas desde el móvil; Orbit los recoge al arrancar la shell.

### Link — enlace markdown al proyecto

```bash
orbit link catedra                                      # → [⚙️catedra](⚙️gestion/⚙️catedra/catedra-project.md)
orbit link catedra notes/result.md                      # → [result](⚙️gestion/⚙️catedra/notes/result.md)
orbit link catedra notes/tramos.md --from complementos  # → [tramos](../⚙️catedra/notes/tramos.md)
```

### Deliver — entregar ficheros a la nube

```bash
orbit deliver next-kr notes/results.pdf                                          # copia a cloud + portapapeles
orbit log next-kr "Resultados Q1" results.pdf --entry resultado --deliver        # log + entrega a cloud/logs/
orbit hl add next-kr "Paper calibracion" paper.pdf --type refs --deliver         # highlight + entrega a cloud/hls/
```

Cada workspace define su `cloud_root` en `orbit.json`. La estructura cloud:

```
{emoji}{space}/                     ← ej. 🚀orbit-ws en OneDrive
  {type_emoji}{type}/               ← ej. ⚙️gestion
    {project}/                      ← ej. ⚙️catedra
      logs/                         ← ficheros de log (prefijo YYYY-MM-DD_)
      hls/                          ← ficheros de highlights
```

### Mantenimiento

```bash
orbit doctor [project] [--fix]     # validar sintaxis de ficheros
orbit archive [project] [--months N] [--dry-run] [--force]
                                   # --agenda --logbook --notes para filtrar
orbit gsync [--dry-run]            # sincronizar con Google Tasks/Calendar
orbit commit ["mensaje"]           # commit + push interactivo
```

### Documentacion

```bash
orbit help                         # chuleta de comandos (terminal)
orbit help chuleta                 # abre CHULETA.md en el editor
orbit help tutorial                # abre TUTORIAL.md en el editor
```

---

## Convenciones

- `logbook.md` de cada proyecto — fuente de verdad del historial de trabajo (append-only).
- Logbook multilinea: lineas indentadas con 2+ espacios son continuacion de la entrada anterior.
- `notes/` — notas libres, rastreadas opcionalmente en git.
- `cmd.md` — fichero temporal de salida de comandos con `--open`.
- `[G]` en agenda.md indica que el item esta sincronizado con Google (IDs en `.gsync-ids.json`).
- Las operaciones destructivas piden confirmacion (defecto **No**) o requieren `--force`.
- `--open [--editor E]` disponible en comandos de listado; abre `cmd.md` en el editor.
- `--log PROJECT [--log-entry TYPE]` guarda el output como entrada en el logbook de un proyecto.
- `--date` acepta lenguaje natural: `today/hoy` · `next friday` · `in 5 days` · `YYYY-MM-DD`.

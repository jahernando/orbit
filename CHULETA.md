# Orbit — Chuleta de comandos

## Shell interactivo

```bash
orbit              # entra al shell (sin prefijo orbit en cada comando)
orbit shell        # equivalente explícito
orbit claude       # abre Claude Code en el directorio Orbit
```

Al entrar: `¡Hola! ¡Bienvenido!` + startup (doctor, untracked, save+push, gsync)
Al salir: `exit`/`quit` (directo) o `end` (save+push antes de salir)

El save+push del arranque y de `end` sigue la regla de `save`: no pregunta, mensaje `sync <fecha hora>`.

### Panel de proyecto — shell fijado a un proyecto

```bash
orbit shell --project next-pn24     # o -p next-pn24
ORBIT_PROJECT=next-pn24 orbit shell # equivalente por entorno
```

Es lo que abre `wks <proyecto>` en su segunda ventana. Dentro:

```bash
log "añadidos ingresos y gastos"    # sin nombre de proyecto
task add "escribir el ADR" --date friday
agenda                              # sólo este proyecto
day                                 # triaje de hoy de este proyecto
organize                            # triaje de todo lo pendiente del proyecto
```

- **El nombre del proyecto desaparece de los comandos**: se sobreentiende.
- **Inmutable**: no hay verbo para cambiar de proyecto. Para otro, otra ventana.
- **Nombrar otro proyecto es un error**, no un cambio de destino. Si el texto
  empieza por el nombre exacto de otro proyecto, entrecomíllalo.
- **Comandos de workspace bloqueados**: `dash`, `panel`, `cal`,
  `focus`, `ring`, `mail`, `setup`, `cloud sync|imgs`, `project create|drop|type`,
  `ls projects` → para ésos, el panel general. `save`/`commit` sí funcionan.
- **Modo ligero**: no pasa el doctor del workspace, no levanta daemons ni
  ofrece save al arrancar. De eso se encarga el panel general, que es el dueño
  del workspace. `end` sigue ofreciendo guardar.
- Historial de flecha-arriba propio de cada panel.

Ver [ADR-049](DECISIONS.md#adr-049--panel-de-proyecto-shell-fijado-a-un-proyecto-inmutable-y-en-modo-ligero).

---

## help / man — índice de comandos y manual

```bash
help                    # índice: una línea por comando
help <comando>          # la página de ese comando + su gramática
man <comando>           # alias de `help <comando>`
help chuleta            # esta referencia completa, paginada
help tutorial           # el tutorial · help about → el README
help <comando> --open   # abrir la página en el editor
<comando> --help        # sólo la gramática (opciones y subcomandos)
```

Ni el índice ni las páginas tienen texto propio: se **derivan de este mismo
fichero**. Cada sección `## <verbo> — <descripción>` de la chuleta es la página
de manual de ese verbo, y la descripción tras el guión largo es su línea en el
índice. Un alias entre paréntesis o separado por barra en el encabezado cuelga
de la misma página: `## reminder (rem) — …` sirve a los dos.

La consecuencia práctica: **documentar un comando nuevo es escribir su sección
aquí**, y aparece solo en `help`. No hay un segundo sitio que actualizar.

`doctor` avisa de los verbos del CLI que no tienen encabezado donde aparezca su
nombre, porque el índice no puede encontrarlos aunque estén explicados dentro
de otra sección.

---

## project — gestión de proyectos

```bash
orbit project create   <name> --type TIPO [--priority alta|media|baja]
orbit project status   <name> [--set STATUS]
orbit project priority <name> alta|media|baja
orbit project edit     <name> [--editor E]
orbit project drop     <name> [--force]
orbit project type                          # lista tipos configurados
orbit project type add <name> <emoji>       # añade tipo
orbit project type drop <name>              # elimina tipo
```

- `create` genera la estructura completa: `project.md`, `logbook.md`, `highlights.md`, `agenda.md`, `notes/`
- `drop` pide confirmación interactiva (defecto **No**); `--force` la omite
- tipos configurables en `orbit.json` (ver `project type`)

---

## task — tareas

```bash
orbit task add     <project> "<text>" [--date DATE] [--time HH:MM] [--recur FREQ] [--until DATE] [--ring WHEN] [--desc DESC] [--fup DATE|none] [--crono [NAME]] [-i]
orbit task done    [<project>] ["<text>"]
orbit task drop    [<project>] ["<text>"] [--force] [-o] [-s]
orbit task log     [<project>] ["<text>"]
orbit task edit    [<project>] ["<text>"] [--text "<new>"] [--date DATE|none] [--time HH:MM|none] [--recur FREQ|none] [--until DATE|none] [--ring WHEN|none] [--desc DESC|none] [--fup DATE|none] [--crono [NAME]|none]
orbit task fup     <project> "<text>" <DATE|clean|none> [--desc DESC] # añade/quita followup ⏩; none = sin fecha (ver Followups)
```

### Tarea / hito con cronograma (`--crono`)

Una tarea o un hito puede llevar su cronograma: el item enlaza el fichero al
**final de la cabecera** y la fecha límite es la del propio item.

```bash
orbit task add  <p> "Informe final" --date 2026-12-15 --crono         # crea cronos/crono-informe-final.md
orbit ms   add  <p> "Entrega" --date 2026-12-15 --crono plan-q4       # nombre explícito
orbit task edit <p> "Informe final" --crono                           # asociar a un item existente
orbit task edit <p> "Informe final" --crono none                      # desasociar (el fichero se queda)
```
```
- [ ] ✏️ Informe final #tarea [📊](cronos/crono-informe-final.md)
    ▶️ 2026-12-15
```
- Sin `NAME`, el crono se nombra por el título (sin tildes, `-` por espacios).
  Si el fichero ya existe se **enlaza** tal cual: así se adoptan cronos antiguos.
- Un crono pertenece a **un solo item abierto**; no va en citas recurrentes.
- El enlace es por fichero: renombrar el item (`--text`) no lo rompe.
- El **porcentaje** (hojas hechas) sale en las vistas — `day`, `organize`,
  `agenda`, `ls tasks`/`ls ms` (clicable en la terminal), panel, echo — como
  `📊 37% (3/8)` o `[📊 37%](…)`; nunca se escribe
  en `agenda.md`. `📊 ✓ 100%` = listo para cerrar (lo cierras tú); `📊 ?` =
  fichero no encontrado.
- `NAME` que no existe tal cual se busca por coincidencia parcial única entre
  los cronos del proyecto (`--crono hk` adopta `crono-hk-general.md`).
- Sus pasos activos o vencidos salen bajo el item en `day`/`organize` y en la
  celda del item en el panel del secretario (`<br>↳ …`); un paso así hace
  aflorar el item en *Hoy*.
- La fecha del item es el plazo del crono: el `⏩` del triaje no la quita y
  `--fup none` se rechaza.
- Al calendario (`.ics`) va solo el item; los pasos del crono enlazado no.

### Títulos únicos por agenda

`add` rechaza una cita cuyo título ya lo tiene **otra abierta del mismo tipo**
en la misma agenda (sin distinguir mayúsculas ni espacios repetidos); `edit
--text` rechaza renombrar sobre uno existente. Las cerradas (hechas o
canceladas) no cuentan: repetir el título de algo terminado es normal. Motivo:
los verbos (`edit`, `done`, `drop`, `fup`, y `day`) localizan la cita por su
título, y dos iguales abiertas son ambiguas. No aplica a los bloques de `focus`
(que se crean por la API y llevan id propio).

### Modelo planned / someday (F5: eje `ff` retirado)

Una task vive en uno de dos estados abiertos, derivados solo de `date`:

| Estado | `date` | significado |
|---|---|---|
| planned | ✓ | compromiso firme; aparece en la Agenda del panel |
| someday | — | reposo, sin presión; no aflora hasta que le pongas fecha o un followup |

- `task add --date DATE` → **planned**. `task add` sin fecha → **someday** (captura en reposo, ya no se auto-programa a hoy).
- Para **planificar** una someday: `task edit --date DATE`. Para **posponer/triar** cualquier cita: un **followup** `<tipo> fup` (`⏩ FECHA` en el cuerpo; ver sección Followups). El followup es lo que hace aflorar la cita en "Decidir hoy" cuando `⏩ <= today`.
- Los verbos `plan`/`pending` y los campos `ff`/`💤`/`❌` se **retiraron en F5**: el eje de triaje es ahora el followup (línea de cuerpo, aplica a las 4 citas), no un campo de cabecera de la task.

- `done` y `drop`: interactivos si no se especifica texto; `drop` pide confirmación
- Si el texto coincide con varias citas, se muestra una lista numerada para elegir (aplica a task, ms, ev y reminder)
- `done` en tarea recurrente: avanza a la siguiente ocurrencia automáticamente
- `drop` en tarea recurrente: pregunta si quitar solo esta ocurrencia o toda la serie; `-o` avanza al próximo, `-s` elimina la serie (sin prompt); `--force` avanza al próximo (seguro por defecto)
- `log`: crea una entrada en el logbook del proyecto a partir de una cita (task→#apunte, ms→#resultado, ev→#evento)
- `--open`: escribe el resultado en `cmd.md` y lo abre en el editor

### Recurrencia (`--recur`)

| Valor | Significado |
|-------|------------|
| `daily` | Cada día |
| `weekly` | Cada semana |
| `monthly` | Cada mes |
| `weekdays` | Días laborables (lun–vie) |
| `every 2 weeks` | Cada 2 semanas |
| `every 3 days` | Cada 3 días |
| `every 2 months` | Cada 2 meses |
| `first monday` | Primer lunes de cada mes |
| `last friday` | Último viernes de cada mes |
| `none` | Eliminar recurrencia (solo en `edit`) |

Se aceptan días de la semana en inglés y español (`lunes`, `viernes`, etc.).

### Fin de recurrencia (`--until`)

`--until YYYY-MM-DD` indica la fecha límite de la recurrencia. Cuando la siguiente ocurrencia supera esa fecha, la serie se da por finalizada. No confundir con `--end`/`--end-date` de eventos, que indican el día de fin de un evento multi-día (orbit rechaza un `--end` que haga durar cada ocurrencia hasta la siguiente).

Ejemplo: `orbit ev add proj "Seminario" --date 2026-04-01 --recur weekly --until 2026-06-30`

En `edit`: `--until none` elimina el límite (la serie pasa a ser indefinida).

### Alarmas de la cita (`--ring`)

| Valor | Significado |
|-------|------------|
| `1d` | 1 día antes del deadline (a las 09:00) |
| `2h` | 2 horas antes |
| `30m` | 30 minutos antes |
| `HH:MM` | Hoy (o en la fecha de la tarea) a esa hora |
| `YYYY-MM-DD HH:MM` | Fecha/hora exacta |
| `none` | Eliminar ring (solo en `edit`) |

Si la tarea tiene `--time`, los rings relativos (`1h`, `30m`) se calculan desde esa hora.
Sin `--time`, se usa 09:00 como ancla por defecto.

Si al crear una tarea, hito o evento con `--time` no se indica `--ring`, Orbit pregunta interactivamente (defecto `5m`, `0` para no añadir ring).

### Modo guiado (`-i` / `--ask`)

`add … -i` activa un interrogador que rellena los huecos **opcionales** de forma interactiva: ring, descripción, sala/enlace (eventos), fecha/hora si faltan, y **followups** en bucle (`⏩ FECHA [desc]`, repite hasta Enter vacío). Calibrado para no molestar:

- Solo en terminal interactiva (TTY): en scripts/pipes nunca pregunta (usa defaults/salta) → no cuelga.
- Lo pasado inline **no** se vuelve a preguntar; solo rellena lo que falta.
- Todo prompt muestra su default; Enter lo acepta.
- Los campos obligatorios por tipo (ev→`--date`, reminder→`--date`+`--time`) siguen siendo obligatorios en línea.
- Por defecto el modo es **mínimo** (sin `-i` no pregunta nada extra). En `orbit.json`, `"add_mode": "guided"` invierte el defecto (sobreescribible por invocación).

### Echo del item al mutar

Todos los verbos que modifican una cita (`add`, `edit`, `done`, `drop`, `fup`) confirman imprimiendo el **orbit-item resultante** tal cual queda en `agenda.md` (mismo serializador → fiel byte a byte), incluido su cuerpo (followups/links). El `[orbit:id]` se oculta salvo con `-v`/`--verbose`.

---

## ms — hitos

```bash
orbit ms add    <project> "<text>" [--date DATE] [--time HH:MM] [--recur FREQ] [--until DATE] [--ring WHEN] [--desc DESC] [--fup DATE|none] [--crono [NAME]] [-i]
orbit ms done   [<project>] ["<text>"]
orbit ms drop   [<project>] ["<text>"] [--force] [-o] [-s]
orbit ms log    [<project>] ["<text>"]
orbit ms edit   [<project>] ["<text>"] [--text "<new>"] [--date DATE|none] [--time HH:MM|none] [--recur FREQ|none] [--until DATE|none] [--ring WHEN|none] [--desc DESC|none] [--fup DATE|none] [--crono [NAME]|none]
orbit ms fup    <project> "<text>" <DATE|clean|none> [--desc DESC]
```

---

## ev — eventos

```bash
orbit ev add  <project> "<text>" --date DATE [--end DATE] [--end-time HH:MM] [--time HH:MM|HH:MM-HH:MM] [--recur FREQ] [--until DATE] [--ring WHEN] [--desc DESC] [--agenda URL] [--room URL] [--fup DATE] [-i]
orbit ev drop [<project>] ["<text>"] [--force] [-o] [-s]
orbit ev edit [<project>] ["<text>"] [--text "<new>"] [--date DATE] [--end DATE|none] [--end-time HH:MM] [--time HH:MM|HH:MM-HH:MM|none] [--recur FREQ|none] [--until DATE|none] [--ring WHEN|none] [--desc DESC|none] [--agenda URL|none] [--room URL|none] [--fup DATE]
orbit ev fup  <project> "<text>" <DATE|clean> [--desc DESC]
```

- `--time`: hora del evento. `HH:MM` (solo inicio, 1h por defecto) o `HH:MM-HH:MM` (inicio-fin)
- `--end-time HH:MM`: hora de fin separada (se combina con `--time` → `HH:MM-HH:MM`). Si no hay `--time`, usa 09:00 como inicio
- `--end` / `--end-date`: fecha de fin para eventos multi-día. **No es el fin de una serie** (eso es `--until`): en un evento recurrente, un `--end` que llega a la siguiente ocurrencia se rechaza, porque el evento se solaparía consigo mismo y saldría todos los días. Para arreglar uno ya escrito: `ev edit … --end none --until FECHA`
- Sin `--time`: evento de día completo
- `drop` en evento recurrente: pregunta si quitar solo esta ocurrencia o toda la serie; `-o` avanza al próximo, `-s` elimina la serie (sin prompt); `--force` avanza al próximo (seguro por defecto)
- `drop` pide confirmación (defecto **No**); `--force` la omite
- `--desc`: descripción (enlaces, notas). Se guarda como líneas indentadas en agenda.md y se propaga a Google Calendar/Tasks. No se muestra en `ls`/`agenda` — solo en el fichero. Aplica también a `task` y `ms`
- `--agenda URL`: agenda/indico del evento. Se guarda como `📋 URL` indentada bajo el item; en `edit`, `none` la quita
- `--room URL`: sala (Zoom, Meet, Teams, Webex, Jitsi). Se guarda como `🚪 URL`; `none` la quita
- Una `--desc` en edit preserva las notas con prefijo `📋`/`🚪` (no las borra)

---

## reminder (rem) — recordatorios

```bash
orbit reminder add  <project> "<text>" --date DATE --time HH:MM [--recur FREQ] [--until DATE] [--desc DESC] [--fup DATE] [-i]
orbit reminder drop [<project>] ["<text>"] [--force] [-o] [-s]
orbit reminder log  [<project>] ["<text>"]
orbit reminder edit [<project>] ["<text>"] [--text "<new>"] [--date DATE|none] [--time HH:MM|none] [--recur FREQ|none] [--until DATE|none] [--desc DESC|none] [--fup DATE]
orbit reminder fup  <project> "<text>" <DATE|clean> [--desc DESC]     # (rem = alias)
```

- Los recordatorios son notificaciones programadas: no tienen estado (done/pending), solo se disparan en la fecha/hora indicada
- Se guardan en la sección `## 💬 Recordatorios` del `agenda.md` del proyecto
- Formato en agenda.md: `- texto (YYYY-MM-DD) ⏰HH:MM [🔄recur[:until]]`
- `drop` en recurrente: pregunta ocurrencia o serie (como task/ev); `-o` avanza al próximo, `-s` elimina toda la serie
- `drop` pide confirmación (defecto **No**); `--force` la omite
- Al iniciar la shell, `ring` programa los recordatorios del día como notificaciones en Reminders.app de macOS
- `--date` y `--time` son obligatorios
- `--recur` y `--until` funcionan igual que en tareas/eventos

---

## clog — logbook de la cita activa ahora

```bash
orbit clog ["<text>"]     # entrada de logbook de la cita en curso (las 4 citas, sin indicar tipo)
```

`clog` localiza la cita activa ahora mismo (now ∈ [inicio, fin+10min]) sobre los 4 tipos y crea una entrada de logbook, sin que indiques proyecto/tipo/texto. Si hay >1 activa o ninguna, abre un selector. `["<text>"]` filtra por subcadena.

> **v0.42 — el paraguas `cita` se retiró.** `clog` es su único superviviente. Los antiguos `cita fup/done/drop` viven ahora en los **verbos tipados**: followups → `task fup` / `ms fup` / `ev fup` / `rem fup` (+ `--fup` al alta/edición, ver Followups); completar/cancelar → `task done`/`task drop`, `ms done`/`ms drop`, `ev drop`, `rem drop`.

### Followups (`⏩` en el cuerpo)

Un **followup** es un empujón blando colgado bajo cualquier cita como línea de cuerpo indentada `⏩ FECHA [desc]`. Hace aflorar la cita en "Decidir hoy" del secretario cuando su fecha `<= hoy`, **sin** marcarla vencida (❗) y **sin** estado (no acumula contadores). Una cita puede llevar varios followups.

Se gestionan con el **verbo tipado `fup`** (uno por tipo de cita) y con el flag `--fup` al crear/editar:

```bash
orbit <tipo> fup <project> "<text>" <date> [--desc DESC]   # añade ⏩ (tipo = task|ms|ev|rem)
orbit <tipo> fup <project> "<text>" clean                  # borra un ⏩ (listado numerado si hay varios)
orbit <tipo> add  <project> "<text>" ... --fup <date>      # crea la cita ya con un ⏩ colgado
orbit <tipo> edit <project> "<text>" ... --fup <date>      # añade un ⏩ al editar
orbit <tipo> fup  <project> "<text>" none                  # sin fecha (ver abajo)
orbit <tipo> edit <project> "<text>" --fup none            # ídem
```

- **`none` = "sin fecha"**: la tarea o el hito se queda **sin fecha, sin hora,
  sin ring y sin `⏩`** — en reposo (*someday*); vuelve a salir en `organize`
  (bloque Sin fecha). Solo tareas e hitos **no recurrentes**: un evento o un
  recordatorio necesitan fecha (para quitarlos, `drop`) y una serie recurrente
  hay que desrecurrirla antes (`--recur none`). `add … --fup none` es la captura
  sin fecha de siempre; no se combina con `--date`/`--time`/`--recur`.

- `<tipo> fup` acota la búsqueda a ese tipo (un `task fup` nunca engancha un evento homónimo).
- `clean` lista los `⏩` de la cita numerados y borra el que elijas; si solo hay uno, lo borra directo. `--desc` se ignora con `clean`.
- `--fup <date>` (en `add`/`edit`) cuelga **una** fecha sola; para varios followups o poner descripción, usa el verbo `fup` o el interrogador `-i`.
- `date` acepta `YYYY-MM-DD`, `today`, `mañana`, `monday`, `+N`, … (se normaliza a ISO). `--des` es alias de `--desc`.
- Mutación silenciosa: no escribe en el logbook, pero el comando muestra el item resultante.
- El followup es el **único** mecanismo de triaje (F5 retiró el campo `ff` de cabecera): va en una **línea de cuerpo** indentada y aplica a las 4 citas.

---

## hl — highlights

```bash
orbit hl add  <project> "<text>" [<file|url>] --type TYPE [--import] [--link] [--no-date] [--date [FECHA]]
orbit hl drop [<project>] ["<text>"] [--type TYPE] [--force]
orbit hl edit [<project>] ["<text>"] [--text "<new>"] [--link URL] [--type TYPE] [--editor E]
```

**Formato** (v0.43, ADR-046): `highlights.md` es una **lista plana de orbit-items** (misma gramática que `agenda.md`), sin secciones. Un ítem por línea a columna 0: guión, emoji-tipo, texto o `[link](url)`, y la etiqueta primaria; una nota opcional cuelga indentada dos espacios. El emoji **es** el discriminador de tipo (por eso cada tipo tiene emoji único) y `#etiqueta` lo duplica, dejando sitio a más `#etiquetas` libres detrás.

```
- 📎 [Paper](https://…) #referencia
- 💡 Idea a conservar #idea
  nota opcional del ítem
```

Ficheros antiguos con secciones `## <emoji> <Palabra>` se **migran perezosamente** (se leen tolerantes y se reescriben planos en el primer `add/drop/edit`).

- `<file|url>`: argumento posicional opcional. URL → enlaza el texto. Fichero local → routing por extensión (`.md` va a `notes/`, resto va a `cloud/hls/`) y pregunta si import (copia) o link (symlink)
- `--import`: copia el fichero al destino sin preguntar. Para no-md añade prefijo `YYYY-MM-DD_`
- `--no-date`: con `--import` no-md, suprime el prefijo `YYYY-MM-DD_` (el nombre del fichero llega tal cual; el usuario asume el riesgo de colisión)
- `--link`: symlink relativo al destino sin preguntar. Para `.md` además registra en `.orbit-tracked.json` (externa)
- `--type`: `refs` (📎 `#referencia`) · `results` (📊 `#resultado`) · `decisions` (📌 `#decisión`) · `ideas` (💡 `#idea`) · `evals` (🔍 `#evaluación`) · `plans` (🗓️ `#plan`) · `contacts` (👥 `#contacto`)
- `--date`: añade fecha al final del texto — `--date` (hoy), `--date tomorrow`, `--date 2026-04-15`
- `drop` pide confirmación (defecto **No**); `--force` la omite
- **Auto-log**: cada `hl add` escribe también una entrada en el logbook con tag `#headline` + el tipo mapeado (`refs→#referencia`, `results→#resultado`, `decisions→#decision`, `ideas→#idea`, `evals→#evaluacion`, `plans→#plan`). Si la highlight tiene link, queda también en el log

---

## arxiv — feed diario de artículos

```bash
orbit arxiv init   <project>
orbit arxiv fetch  [<project>] [--since FECHA] [--until FECHA] [--max N] [--dry-run] [--force]
orbit arxiv triage [<project>] [--purge]
```

Barrido de arXiv por proyecto: los artículos nuevos que casan con tus temas
caen en una **bandeja** dentro de `notes/`, tú marcas los que valen y el triaje
los promociona a `highlights.md` como `📎 #referencia`.

**Dos ficheros en `notes/`**:

- `arxiv-temas.md` — la **config**, la escribes tú; orbit sólo la lee.
- `arxiv.md` — la **bandeja**, la escribe orbit; lo más reciente arriba.

**Fichero de temas** — secciones reconocidas por su encabezado `##`:

```markdown
## Categorías
hep-ex, physics.ins-det, astro-ph.CO

## Autores vigilados
Gómez Cadenas

## Tema: detectores #detectores
- liquid xenon
- "TPC"

## Tema: redes neuronales e IA #ia +acompaña
- deep learning

## Excluir
- swampland

## Ajustes
tope: 15
umbral: 3
retroceso: 7
```

- La **etiqueta** tras el nombre del tema es la que aparece en la entrada; si
  falta, se deriva del nombre.
- Término **entre comillas** = acrónimo estricto: mayúsculas exactas y límite
  de palabra, para que `"TPC"` no dispare con *tpc* ni con *TPCs*.
- Un acierto en el **título** puntúa el doble que en el resumen.
- `+acompaña` en la cabecera del tema = sólo cuenta si además acierta un tema
  propio. Es lo que evita que *deep learning* traiga artículos de otro campo.
- Un autor vigilado suma 5, muy por encima de cualquier término suelto.
- Un término de `Excluir` tumba la entrada entera.
- `tope` = artículos escritos por barrido · `umbral` = puntuación mínima ·
  `retroceso` = días que mira atrás el primer barrido.

**Recuperar un tramo viejo**: `--since` ignora la marca de agua y `--until`
acota el final. Un barrido trae como mucho 1000 artículos, los más recientes
del rango, así que una ventana de meses no llega al principio: se avisa cuando
pasa, y la vía es ir por tramos de una o dos semanas.

```bash
arxiv fetch 📖phys --since 2026-08-01 --until 2026-08-08
arxiv fetch 📖phys --since 2026-08-08 --until 2026-08-15   # …y así hasta hoy
```

Recuperar un tramo viejo **no hace retroceder la marca de agua**: el barrido
diario sigue cubriendo los días pendientes.

**Límite de ritmo**: si arXiv responde 429 se anota una espera de 6 horas en el
estado y no se le vuelve a pedir hasta que pase, ni siquiera desde el arranque.
Insistir alarga el bloqueo. `--force` la ignora, para cuando sabes que ya pasó.

**Marcado y triaje**: cada artículo de la bandeja es una línea con casilla,
`- [ ] 📎 [título](url) #tema`. Marca la casilla (un clic en Obsidian, una `x`
en cualquier editor) y lanza `arxiv triage`. Escribir `#relevante` en la línea
marca igual, para cuando la casilla no sea clicable. Los marcados pasan a
`highlights.md` conservando sus etiquetas de tema, y salen de la bandeja. Los
no marcados se quedan; `triage` pregunta si vaciarlos (defecto **No**), y
`--purge` los tira sin preguntar.

**Automático**: la acción `arxiv_fetch` de la cadena `shell_start` barre los
días laborables, una vez al día, en todo proyecto que tenga fichero de temas.
Silenciosa cuando no hay nada. Si arXiv no responde, la marca de agua no avanza
y se reintenta al día siguiente. El estado vive en `<workspace>/.arxiv-state.json`
(última fecha barrida + identificadores ya vistos, deduplicados **sin versión**,
así que una `v2` de un artículo ya visto no vuelve a aparecer).

**Nota**: el panel de proyecto (shell fijado) no corre la cadena de arranque
(ADR-049), así que el barrido automático ocurre sólo en el panel general.

---

## note — notas de proyecto

Modelo **propia / externa** (v0.36, ver `DECISIONS.md` ADR-026):

- **Propia**: vive entera en el workspace. Tú la creas, tú la editas.
- **Externa**: vive fuera (otro repo, Drive, etc.). En `notes/` solo hay un symlink relativo al fuente. Editar = editar el original.

```bash
orbit note <project> "<title>" [--from PATH]      # crear propia (atajo)
orbit note create <project> "<title>" [--from PATH] [--no-date] [--no-open] [--editor E]
orbit note open   <project> [<name>] [--date D] [--editor E]
orbit note list   <project> [--open [EDITOR]]
orbit note drop   <project> [<file>] [--force]    # propia: borra; externa: untrack

orbit link    <project> <fullpath>                 # crear externa (alias top-level)
orbit unlink  <project> <name>                     # quitar externa, source intacto
```

> Aliases legacy: `orbit track` / `orbit untrack` siguen funcionando.

- **create** (propia): crea nota en `notes/` desde plantilla y registra en logbook
  - Nombre: `YYYY-MM-DD_título.md` (con fecha de hoy como prefijo)
  - Con `--hl <tipo>`: registra en highlights en vez de logbook, sin prefijo de fecha
  - Con `--no-date`: sin prefijo de fecha, sigue registrando en logbook
  - Con `--from PATH`: contenido pre-cargado de `PATH` (cualquier extensión, escribe como `.md`). Resultado completamente propio, sin link al origen. Útil para "copia inicial" de un Drive compartido, un email, etc.
  - Pregunta: `¿Añadir <fichero> a git? [S/n]`
- **open**: abre nota existente o la crea si no existe
  - `--date D`: nombre por fecha (YYYY-MM-DD, YYYY-Wnn, YYYY-MM)
  - Sin nombre ni fecha: selector interactivo
- **drop**:
  - Si la nota es propia → borra el fichero (pide confirmación; `--force` la omite)
  - Si la nota es externa → equivale a `untrack` (borra el symlink, source intacto)
- **list**: marca el tipo de cada nota:
  - ✏️ propia (vive en el workspace)
  - 🔄 externa (symlink al fuente; muestra `→ /ruta/fuente`)

---

## link / unlink / tracked — notas externas: symlink a `.md` fuera del workspace

Casos: `DECISIONS.md` de tu repo público, draft compartido en Drive de la USC, plan vivo de otro proyecto. **Markdown que vive fuera de orbit-ws, lo quieres a mano en Obsidian y publicado al cloud, sin duplicar la verdad**.

```bash
orbit link    <project> <fullpath>         # crear externa (atajo top-level, uso diario)
orbit unlink  <project> <name>             # quitar externa, source intacto

# forma canónica noun-verb (equivalente):
orbit tracked add  <project> <fullpath>    # = orbit link
orbit tracked drop <project> <name>        # = orbit unlink
orbit tracked list [<project>]             # listar externas con status
```

> Aliases legacy: `orbit track` / `orbit untrack` siguen funcionando. La noun-verb `orbit tracked …` conserva su nombre porque coincide con el registry (`.orbit-tracked.json`).

UX de `link` / `tracked add` con eco de confirmación:

```
$ orbit link orbit /Users/hernando/orbit/DECISIONS.md
  local? /Users/hernando/orbit/
  note?  DECISIONS.md
✓ [💻orbit] Linked: notes/DECISIONS.md → /Users/hernando/orbit/DECISIONS.md
```

- **Mecanismo**: orbit crea un **symlink relativo** en `notes/<basename>` apuntando al fuente. La verdad es el fuente; el symlink solo es una ventana. Editar en Obsidian = editar el fuente.
- **Solo `.md`** (git no diffea binarios; PDFs usa `orbit import`).
- **Registry**: `<project>/.orbit-tracked.json` con schema `{"files": {<name>: <source_path>}}`.
- **Render HTML al cloud**: para cada externa, render lee el fuente al momento, lo convierte a HTML y lo escribe en `cloud/notes/`. Si el fuente no es accesible, usa el último mirror cacheado en `.cache/notes/<proj>/` (gitignored).
- **Doctor**: chequea que cada symlink existe y su target es legible. Si no, reporta `broken_link` / `missing_link` / `not_link` y sugiere `untrack` o `retrack`.
- **Cross-links**: si DECISIONS.md tiene `[RING](RING.md)`, el link resuelve si RING.md también está tracked (siblings en `notes/`). Si no, queda roto silenciosamente en cloud HTML — render emite warning.
- **Sección "🔄 Tracked"** automática en project.md HTML listando las externas con link al HTML y al fuente.
- Diseño completo en `DECISIONS.md` ADR-026 (supersedes ADR-024).

---

## email — capturar un email a un proyecto

```bash
orbit email <project> [--note] [--ev] [--mail|--outlook|--gmail|--eml PATH]
```

- **Default**: añade entry al logbook con link al email original (`message://<id>`, abre Mail.app). Sin nota md.
- Tag de log: `#referencia #email [O]`

**Modificadores aditivos** (combinables):
- `--note` — además guarda la nota `notes/emails/YYYY-MM-DD-<slug>.md` (frontmatter + cuerpo) y la entry pasa a doble link: `[Email: subject](nota.md) ✉️ [original](message://...)`. Con esto la nota es inmortal aunque borres el email original
- `--ev` — además propone crear un evento con los datos detectados: título, fecha, hora, room/agenda. Confirmación interactiva `[S/n/e=editar]`. Si el .eml trae ICS adjunto se usa primero (más fiable); fallback a heurística sobre body (URLs Zoom/Meet/Teams/Webex/Jitsi como rooms; Indico como agendas). No detecta recurrencia (la editas con `ev edit --recur` después)

**Sources** (mutuamente exclusivos; default según `email_source` en `orbit.json`):
- `--mail` — Apple Mail.app, mensaje seleccionado (recomendado, robusto)
- `--outlook` — Microsoft Outlook for Mac (frágil con Outlook 16.x; usa drag→`.eml` si falla)
- `--gmail` — Gmail (pendiente)
- `--eml PATH` — parsea un `.eml` exportado de cualquier cliente. En Outlook: arrastra el email al Finder → genera `<subject>.eml`

**Configuración por workspace** (`orbit.json`):
```json
"email_source": "mail"   // mail | outlook | gmail
```

---

## view / open — navegar proyectos

```bash
orbit view  [<project>] [--open [EDITOR]]
orbit open  <project> [logbook|highlights|agenda|project] [--editor E] [--dir]
```

- `view` sin proyecto: muestra lista para selección interactiva
- `view <project>`: resumen en terminal (estado, tareas, hitos, próximos eventos, entradas recientes)
- `view <project> --open`: genera `cmd.md` y lo abre en el editor
- `open --dir`: abre el directorio del proyecto en Finder

---

## log / search — apuntes en el logbook y búsqueda

```bash
orbit log <project> "<título>" [<file|url>] [--entry TIPO] [--import] [--link] [--no-date] [--note NOTA] [--date D] [--open [EDITOR]]

orbit search [query] [--project P...] [--entry TIPO] [--date D] [--from D] [--to D]
             [--in logbook|highlights|agenda] [--any] [--notes]
             [--limit N] [--open [EDITOR]]
```

- `<file|url>`: argumento posicional opcional. URL → enlaza el título. Fichero local → routing por extensión (`.md` va a `notes/`, resto va a `cloud/logs/`) y pregunta si import (copia) o link (symlink)
- `--import`: copia el fichero al destino sin preguntar. Para no-md añade prefijo `YYYY-MM-DD_`
- `--no-date`: con `--import` no-md, suprime el prefijo `YYYY-MM-DD_` (el nombre del fichero llega tal cual; el usuario asume el riesgo de colisión)
- `--link`: symlink relativo al destino sin preguntar. Para `.md` además registra en `.orbit-tracked.json` (externa)

Muchos comandos soportan `--append proyecto:nota` para añadir su salida a una nota:

```bash
orbit report today --append catedra:calibracion     # report del día → nota
orbit agenda --append mission:W12                    # agenda → nota semanal
orbit view catedra --append catedra:estado           # vista del proyecto → nota
orbit search "algo" --append catedra:busqueda        # resultados de búsqueda → nota
```
- Si el fichero es imagen (png, jpg, svg...), se inserta `![título](link)` en la línea siguiente de la entrada
- `--entry`: filtra por tipo de entrada (`idea` · `referencia` · `apunte` · `problema` · `solucion` · `resultado` · `decision` · `evaluacion` · `plan`)
- `--in`: busca en un tipo de fichero específico (por defecto logbook)

### Ledger — la cuenta del proyecto

#### Libro de contabilidad propio (ADR-054, en paralelo hasta migrar)

Si el proyecto tiene **libro** (`ledger.md` con cabecera de partida y
validez), **él es la verdad**; si no, sigue valiendo lo de más abajo (los
movimientos en el logbook). En un proyecto con libro, `log --entry gasto…` se
rechaza.

```bash
orbit ledger <p> init --partida X --from D --to D   # crea ledger.md (proyecto sin movimientos)
orbit ledger <p> add ["Título"] [PDF]               # en terminal pregunta lo que falte
orbit ledger <p> add [PDF] --type ingreso|compromiso|gasto --title … --payee … \
          --amount N --cat C [--date D] [--id REF] [--commit N [--closes]] \
          [--nota …] [--no-log] [--force]
orbit ledger <p> edit E [PDF] [--title --payee --cat --doc --amount --date --id --nota] [--force]
orbit ledger <p> edit E --confirm ID [--amount …]   # ☑️ hoy · ID (herramienta externa)
orbit ledger <p> edit E --unconfirm
orbit ledger <p> close E                            # cierra un compromiso a mano (🔒)
orbit ledger <p> cancel E [--force]                 # anula (🚫): se queda y no cuenta
# E = nº de entrada o un trozo del título / beneficiario / referencia; sin E
#     (o si coinciden varias) te enseña la lista y eliges. --title es el título NUEVO.
orbit ledger <p> edit ginebra factura.pdf           # cambia el justificante de «…Ginebra…»
orbit ledger <p> check [--strict]
orbit ledger <p> migrate --from D --to D [--partida X] [--cats 2=viajes,3=congresos…] \
          [--dry-run] [--force]                     # logbook → libro (una vez por proyecto)
```

**`migrate`** pasa los movimientos del logbook de ese proyecto al libro:
numera por fecha, `🔗 P01` → `🔗 <nº>` (las referencias provisionales
desaparecen), mueve los PDF de `cloud/logs/` a `cloud/ledger-logs/` y
reescribe los enlaces que apuntaban a ellos en el resto del proyecto
(logbook, highlights, notes…), y sustituye cada entrada del logbook por su
rastro. En terminal pregunta la categoría que falte; sin terminal, `--cats`.
Primero `--dry-run`. Deja undo de los markdown; los PDF movidos no.

```markdown
- 💶 0006 [Vuelo Ginebra](./cloud/ledger-logs/2026-09-18_billete.pdf) #compromiso
  📅 2026-09-18 · 🗂️ viajes · 👤 Viajes Ejemplo, S.L. · 💶 -1.250,00 · 🆔 CM26XXXX0001
  ☑️ 2026-11-03 · 2026/000123
  📝 2026-10-05 modificado: 👤 Viajes Ejemplo → Viajes Ejemplo, S.L.
```

- **Números** por orden de anotación: no se reutilizan, renumeran ni borran
  (lo equivocado se **anula**). `🔗` apunta al **nº** del compromiso.
- **Obligatorio**: tipo, fecha (dentro de la validez; `--force` si no),
  título, beneficiario, importe y, salvo en ingresos, **categoría** (lista
  cerrada en `orbit.json` → `ledger.categories`; por defecto viajes ·
  congresos · personal · fungible · inventariable).
- **Justificantes** a `cloud/ledger-logs/` (con fecha).
- **Rastro en el logbook**: `💶 título · ledger N #tipo`, sin enlace ni
  importe (`--no-log` lo omite; `edit --title/--date` lo actualiza).
- **`edit`** deja una nota `📝 fecha modificado: campo a → b`; no cambia el
  tipo (se anula y se anota otra). Una entrada **confirmada** solo se corrige
  con `--force`, y pierde el ☑️. `--confirm` sin cambios no deja nota.
- **Derivados**: `ledger-summary.md` (validado ☑️ frente a vivo, por
  categoría, compromisos abiertos, movimientos con acumulados) y `ledger.json`
  v2 (clave = nº). `ledger.md` no se regenera nunca.
- **`ls ledger [p]`** lista el libro: nº, fecha, tipo, categoría, importe,
  disponible acumulado, ☑️/🚫, y el resumen validado frente a vivo con el
  total por categoría. Solo lee.
- **`project.md`** enlaza el libro en su pie (`[ledger] ([resumen])`): lo añade
  `init`/`migrate`, y `orbit ledger <p>` en proyectos ya migrados.
- `--mark N ID` / `--unmark N` / `--close N` siguen valiendo sobre un libro
  (se traducen a `edit --confirm` / `--unconfirm` / `close`).

#### Movimientos en el logbook (ADR-048/053, hasta migrar)

Una cuenta por proyecto, con tres tipos de movimiento: **`#ingreso`** (entra
dinero), **`#compromiso`** (lo reservas: una hoja de pedido, una reserva…) y
**`#gasto`** (sale). Cada movimiento es una entrada de logbook; `ledger.md` y
`ledger.json` son derivados. Sirve igual para una partida de la USC que para
cuentas personales.

```bash
orbit log <proyecto> --entry ledger                  # en terminal: pregunta el tipo y lo demás
orbit log <proyecto> "<concepto>" [<justificante>] --entry ingreso|compromiso|gasto \
          --amount N --payee P [--id REF] [--compromiso REF [--cierra]] [--nota "…"] \
          [--tag PARTIDA] [--date D]

orbit ledger <proyecto>                          # regenera ledger.md y ledger.json + resumen
orbit ledger <proyecto> --check [--strict]       # coherencia interna (no escribe)
orbit ledger <proyecto> --close <REF>            # cierra a mano un compromiso
orbit ledger <proyecto> --mark <clave> <REF_EXT> # conciliado (lo usa una herramienta externa)
orbit ledger <proyecto> --unmark <clave>
orbit ls ledger [proyecto]                       # solo imprime (no toca el disco)
```

- **Obligatorio:** beneficiario (en un ingreso, quién paga) e importe en €.
- **Opcional:** justificante (PDF: se copia solo a `cloud/logs/` con fecha; si
  ya está dentro del proyecto, solo se enlaza), referencia `--id` (nº de
  autorización, de factura…), nota `--nota`.
- Un **compromiso** lleva siempre referencia: si no la das, una provisional
  (`P01`, `P02`…).

**Asociar un gasto a un compromiso**: `--compromiso REF` (en terminal, `--entry
ledger` → gasto **te lista los compromisos abiertos** con lo pendiente y eliges
uno; Enter = ninguno). Un compromiso admite **varios gastos**. Sigue **abierto**
—y lo no gastado sigue comprometido— hasta que:
- lo gastado contra él llega a lo comprometido (se cierra solo), o
- lo cierras: `--cierra` en el último gasto (en terminal te lo pregunta si el
  gasto no lo cubre), o `orbit ledger <proyecto> --close REF` (anulado, o el
  sobrante que ya no se va a gastar).

```markdown
2026-09-18 💶 [Reserva vuelo](./cloud/logs/2026-09-18_reserva.pdf) #compromiso
  🏷️ viaje · 👤 Axencia Viaxes · 💶 -1.250,00 · 🆔 CM26XXXX0001

2026-10-02 💶 [Factura vuelo](./cloud/logs/2026-10-02_factura.pdf) #gasto
  🏷️ viaje · 👤 Axencia Viaxes · 💶 -1.200,00 · 🆔 F-4471 · 🔗 CM26XXXX0001 · 🔒 cierra
  📝 al cambio del día
```

- **El signo lo pone la tag**: `--amount` sin signo; acepta `218,40` ·
  `4.000,00` · `218.40`; más de 2 decimales se rechaza. `Decimal`, nunca float.
- **Partida**: `--tag` solo en el primer movimiento; los demás la heredan.
- **Al escribir se es estricto**: referencia repetida, `--compromiso` a uno que
  no existe o ya está cerrado → no se escribe.
- Dietas, factura, devolución…: en el concepto o la nota. Moneda extranjera:
  el importe en €, el original en la nota.

**`ledger.md`**: resumen (dotación · gastado · comprometido pendiente ·
**disponible**) y la tabla de **movimientos** en orden, cada uno con
**Gastado** y **Disponible** acumulados a esa fecha (disponible = ingresos −
gastado − comprometido pendiente), su referencia, el compromiso que consume
(🔒 si lo cierra), el estado de los compromisos (abierto / cerrado) y si está
**conciliado**. Se regenera al anotar y en cada `save`.

**`ledger.json`**, al lado, lo mismo para máquinas (una fila por movimiento con
`key`, tipo, fecha, concepto, beneficiario, importe como texto decimal,
referencia, compromiso, cierre, estado, nota, justificante y su ruta absoluta,
y `conciliated`). Lo leen herramientas de fuera, como **`usc-ledger`** (la
revisión con la contabilidad de la USC).

**Conciliado** = la entrada lleva `☑️ <referencia externa>`. Lo pone una
herramienta de conciliación (p. ej. `usc-ledger`, o una con el extracto del
banco) llamando a `orbit ledger <proyecto> --mark <clave> <REF_EXT>` (la
`clave` es el campo `key` de `ledger.json`). Si un compromiso tenía referencia
provisional, pasa a ser la externa, también en el `🔗` de sus gastos. `--unmark`
la quita.

**Comprobación** (`--check`). No escribe nada.

- ❌ **errores** (salen también en `orbit doctor`): justificante enlazado que
  no existe · `🔗` a un compromiso que no existe · referencia repetida ·
  entrada ilegible.
- ⚠️ **avisos** (solo aquí): compromiso abierto más de 60 días · documento de
  `cloud/logs/` con pinta económica que no enlaza nadie (los legítimos, en
  `<proyecto>/.ledger-ignore`).
- `--strict`: los avisos también dan error. Umbral y patrón en `orbit.json` →
  `"ledger": {"open_days": 60, "doc_patterns": …}`.
- **Provisional, hasta que exista `usc-ledger`**: `--check <Execucion.pdf>
  <obrigas.xls>` imprime una comparación con la USC por referencia. No escribe.

**Export** (`--export <dir>`, provisional hasta `usc-ledger`): `ledger.pdf`,
`ledger.xlsx` y `justificantes/` con solo lo enlazado. Necesita `pip install
reportlab openpyxl` (extra `ledger`).

**Archivar un proyecto con movimientos**: `archive` borra las entradas
anteriores al corte, así que antes pregunta si consolidar su saldo neto en una
entrada `#arrastre` por partida (sí: el saldo no cambia; no: una `#arrastre`
de importe 0 marca el corte y `ledger.md` avisa). `--force` consolida. **Un
compromiso solo se archiva entero y cerrado**: si sigue abierto o alguno de sus
gastos es posterior al corte, se quedan todos. El arrastre solo suma lo que
mueve caja.

---

## crono — cronogramas (task compuesta)

Cronogramas: tareas anidadas con dependencias y duración temporal. Conceptualmente son una **task-compuesta** (extensión del sistema task). Se almacenan en `cronos/crono-<nombre>.md` dentro del proyecto.

> **En transición**: la forma nueva de crear un cronograma es colgarlo de una tarea o un hito con `--crono` (ver *Tarea / hito con cronograma* en `task`). `crono add` y el `deadline:` por nombre de hito siguen funcionando hasta que se retiren.

```bash
orbit task crono add     <project> "<name>"                    # crear cronograma
orbit task crono show    <project> "<name>" [--open]           # mostrar con fechas calculadas
orbit task crono edit    <project> "<name>" [--open [EDITOR]]  # abrir en editor
orbit task crono check   <project> "<name>"                    # validar (doctor)
orbit task crono list    <project> [--open]                    # listar cronogramas del proyecto
orbit task crono done    <project> "<name>" [<index|texto>]    # marcar tarea como completada
orbit task crono reindex <project> "<name>"                    # renumerar índices automáticamente
orbit task crono gantt   <project> "<name>" [--open]           # visualizar como Gantt

orbit crono <sub> ...                                          # atajo top-level (uso diario)
```

- `done` sin argumento: selección interactiva de tareas pendientes
- `done` con texto parcial: busca por índice o título
- `done` registra la completación en el logbook del proyecto (`📊crono] idx título #apunte`)
- Las tareas completadas manualmente en Obsidian (clic en checkbox) se detectan y registran automáticamente al hacer `save`
- `gantt`: auto-detecta modo DAG (progreso) o con fechas (timeline)
- `gantt --progress`: fuerza vista de progreso (barras + checkboxes)
- `gantt --timeline`: fuerza vista temporal (eje de fechas)
- `reindex`: corrige huecos e inconsistencias en la numeración (actualiza `after:`)

### Formato del fichero

```markdown
# Cronograma: nombre del cronograma

deadline: 2026-05-30
exclude: sat, sun

- [ ] 1 Fase 1 título
  - [ ] 1.1 Subtarea | 2026-03-20 | 2W
  - [ ] 1.2 Otra subtarea | after:1.1 | 3d
- [ ] 2 Fase 2 | after:1
  - [ ] 2.1 Siguiente | | 1W
```

- **Inicio**: fecha ISO (`2026-03-20`), semana ISO (`2026-W12`), semana+día (`2026-W12-wed`), o dependencia (`after:<índice>`)
- **Duración**: `Nd` (días), `NW` (semanas)
- **Tareas padre** calculan su inicio/fin de las hijas
- **`after:` en padres**: se hereda a las hojas sin inicio propio (`2.1` hereda `after:1` de `2`)
- **Modo DAG**: sin duraciones — solo estructura y dependencias, útil para seguimiento de progreso
- **Deadline**: fecha límite del cronograma. Muestra ritmo necesario y avisa si vas retrasado:
  `⚠️ deadline 2026-05-30 (4d) — 12 pendientes, ritmo: 3/día`
  Acepta fecha ISO o nombre de hito del proyecto (busca la fecha en la agenda)
- **Metadatos**: `deadline`, `exclude: sat, sun` (excluir fines de semana), `initial-time: 2026-06-01` (inicio por defecto)
- **Indentación**: soporta 2 espacios, 4 espacios o tabs (autodetección)
- `check` valida: índices únicos, dependencias válidas, sin ciclos, hojas con inicio+duración
- El progreso y deadline de los cronogramas se muestran en `orbit panel`
- Cronogramas completados (100%) se ocultan del panel automáticamente

---

## undo — deshacer operaciones

```bash
orbit undo
```

- Muestra la lista de operaciones deshacibles (más reciente primero)
- El usuario elige cuál deshacer (por defecto la última; 0 para cancelar)
- Si se elige N, se deshacen las N operaciones más recientes
- Restaura el estado anterior de todos los ficheros afectados
- Stack de hasta 20 operaciones (en memoria, durante la sesión del shell)
- Si se creó un fichero nuevo, lo elimina; si se borró, lo restaura

---

## clip — copiar al portapapeles

Comando unificado para copiar fechas, semanas y enlaces al portapapeles:

```bash
orbit clip date                # hoy: 2026-03-20 (copiado al portapapeles)
orbit clip date wednesday      # próximo miércoles
orbit clip date in 2 weeks     # dentro de 2 semanas
orbit clip week                # esta semana: 2026-W12
orbit clip week next week      # próxima semana
orbit clip <project>                                        # enlace al proyecto
orbit clip <project> notes/result.md                        # enlace a un fichero del proyecto
orbit clip catedra notes/tramos.md --from complementos      # enlace relativo entre proyectos
```

- `clip date [expr]`: fecha YYYY-MM-DD al portapapeles. Sin argumento: hoy
- `clip week [expr]`: semana ISO YYYY-Wnn al portapapeles. Sin argumento: semana actual
- `clip <project> [fichero]`: enlace markdown al proyecto o a un fichero del proyecto
  - Sin fichero: `[⚙️catedra](⚙️gestion/⚙️catedra/project.md)`
  - Con fichero: busca por nombre parcial en el proyecto (interactivo si hay varias coincidencias)
  - `--from <proyecto>`: calcula ruta relativa desde la raíz del proyecto origen (para Obsidian)

---

## ls — listados

```bash
orbit ls                              # lista proyectos (por defecto)
orbit ls projects [--status S] [--type T] [--sort type|status|priority]
orbit ls tasks    [project...] [--status pending|done|all] [--date D] [--dated] [--unplanned] [--someday]
orbit ls ms       [project...] [--status pending|done|all] [--date D] [--dated]
orbit ls ev         [project]    [--from D] [--to D]
orbit ls reminders  [project]    # recordatorios activos (alias: ls rem)
orbit ls hl        [project]    [--type T]
orbit ls log       [project]    [--type T...] [--date D] [--from D] [--to D]
orbit ls ledger    [project]    # movimientos y saldo (solo lectura)
orbit ls cronos    [project]    # cronos: progreso, item que lo lleva, siguiente paso
orbit ls files    [project]    # ficheros md del proyecto con estado git
orbit ls notes    [project]    # notas con estado git
```

- `ls log` lista las cabeceras de entrada del logbook; `ls <proyecto>` hace lo mismo (forma antigua)
- `ls ledger` **no regenera** `ledger.md` — para eso está `orbit ledger <proyecto>`
- `ls cronos` da el nombre que acepta `crono edit <p> <nombre>` (abre en el editor de
  `orbit.json`; otro con `--open typora`); el nombre es enlace al fichero
- Sin proyecto, `ls hl/log/ledger/cronos/files/notes` barren el workspace entero
- **Enlaces clicables**: en una terminal que los entiende (iTerm2, WezTerm, kitty, VS Code…)
  cada `[texto](enlace)`, la cabecera `[proyecto]`, los ficheros de `ls files/notes` y los
  proyectos de `ls projects` salen como `texto ↗`: ⌘-clic o ctrl-clic (según iTerm2) abre el fichero o la web. Con
  `--open`/`--log`/`--append`, una tubería o `ORBIT_NO_LINKS=1`, sale el markdown de siempre
- `--unplanned`: solo tareas sin fecha asignada (futuribles)
- `--someday`: solo tareas sin fecha (reposo) — equivalente a `--unplanned` tras F5
- `--no-fed`: excluye proyectos federados del listado

Indicadores git en `files` y `notes`: `✓` tracked · `M` modified · `+` untracked · `✗` ignored

---

> **Panel y agenda** son las dos herramientas dinámicas para gestionar el día. Se abren al empezar (`--open` para fijar en Obsidian) y se refrescan durante la jornada. Panel da la vista de alto nivel (prioridad + citas + actividad); agenda detalla las citas. Al final del día, `report` resume la actividad.

## agenda — citas del día (herramienta dinámica)

```bash
orbit agenda [project...] [--date D] [--from D] [--to D] [--no-cal] [--summary] [--dated] [--order project|date] [--no-fed] [--open [EDITOR]]
orbit agenda week                     # esta semana
orbit agenda <fecha|periodo> --sec      # formato secretario → 📊panel/secretary/agenda-rango.md
orbit agenda month                    # este mes
orbit agenda future [project...]      # vista previa del formato nuevo de citas
orbit agenda migrate [project...]     # reescribe agenda.md al formato nuevo (in situ)
orbit agenda clean [project...] [--dry-run]   # borra lo cerrado y lo pasado hasta hoy
```

- `agenda clean` = `archive <project> --agenda --months 0`: tareas/hitos hechos o
  cancelados y eventos ya terminados; las series recurrentes solo si acabaron
  (ver `archive`). **Lista una a una las citas que borraría y pregunta
  `[s/N]`** (Enter = no borrar); no hace falta un paso previo. `--dry-run` solo
  lista, sin preguntar. Sin proyecto: el del panel fijado o, en el general, todos.

- **`--sec`**: la agenda de un día o un rango en **formato secretario** (tabla por
  día + mini-calendario de carga), en `📊panel/secretary/agenda-rango.md` (se
  reescribe cada vez) y la abre (`--open EDITOR` para otro editor). Todo el
  workspace: lo posicional es la fecha (`agenda viernes --sec`, `agenda next
  week --sec`, `agenda 2026-10 --sec`) o `--from/--to`. Máx. 62 días. Si el
  rango incluye hoy, hoy sale como en `agenda.md` (vencidas, ⏩, crono); los
  días pasados solo muestran lo que sigue abierto.
- Sin fecha: muestra el día de hoy (tareas pendientes, vencidas, eventos, hitos)
- Atajos de periodo: `today`/`hoy`, `week`/`semana`, `month`/`mes`
- `--date 2026-03`: todo el mes
- `--from monday --to friday`: rango
- El calendario se muestra por defecto; `--no-cal` lo suprime (para calendarios dedicados, usa `cal`)
- Colores del calendario: azul (semana) · amarillo (tarea) · cian (evento) · magenta (hito) · rojo (vencida) · invertido (hoy)
- `--summary`: tabla resumen por proyecto (primera/última fecha, conteo de tareas/hitos/eventos/sin fecha)
- `--dated`: solo muestra tareas/hitos que tienen fecha asignada
- `--order project`: agrupa por proyecto (por defecto)
- `--order date`: agrupa por día, con horas como sub-cabeceras; sin-fecha al final
- `--no-fed`: excluye proyectos de workspaces federados
- `--open` escribe a fichero transitorio (`cmd.md`) y lo abre; el dashboard fijo pineable es `📊panel/secretary/agenda.md`, regenerado en cada mutación.
- Tareas vencidas se agrupan en el día de hoy con la fecha original: `(📅2026-03-22) ⚠️`
- Compatible con `--log`
- `future [project...]`: genera un `<project>-agenda_futura.md` por proyecto con la agenda en el **formato unificado nuevo** (header + cuerpo indentado: `▶️` fechas, `✏️` tareas, tags, followups `⏩`). Es una **vista derivada** de solo lectura para ver cómo quedará — no toca `agenda.md`. Sin proyectos: todos. (Transitorio durante la migración al formato nuevo.)
- `migrate [project...]`: reescribe **la verdad** `agenda.md` de cada proyecto propio al formato nuevo (in situ). Solo toca los que aún están en formato viejo (idempotente); pliega `⏩ff` inline → followup de cuerpo y descarta la tabla cronos incrustada. Cada escritura deja snapshot de undo y el cambio queda en git. Federados se saltan. Sin proyectos: todos. Útil para migrar el workspace de golpe en vez de esperar a la migración perezosa comando a comando.

---

## cal — calendario del mes

```bash
cal                        # mes actual
cal abril                  # un mes por su nombre (o april)
cal 2026-04                # un mes por su fecha
cal abril 3                # tres meses desde abril (máximo 3)
cal --from 2026-04-01 --to 2026-05-15   # rango libre
cal --open                 # abre 📊panel/secretary/calendar.md en el editor
```

Vuelca en terminal la rejilla del mes con las citas de todos los proyectos, una
línea por día. Es **lectura pura**: no escribe la verdad ni regenera derivados.

Acepta los destinos de salida comunes (`--open`, `--log`, `--append`). Con
`--open` el volcado va a `📊panel/secretary/calendar.md`; el resto de comandos
de consulta usan el `cmd.md` transitorio.

---

## dash — regenerar los derivados del workspace

```bash
dash                       # regenera los viewers + los .ics del cloud
```

Rehace los viewers de `📊panel/` (agenda, proyectos, calendario, cronogramas,
hitos, logbook, resumen) y, a continuación, los buckets `.ics` del cloud, para
que Calendar.app vea el estado actual sin esperar a un `save`.

Normalmente **no hace falta llamarlo**: cada mutación de cita, log, highlight o
proyecto lo dispara en segundo plano, y `save` lo incluye en su cadena. Se usa a
mano tras editar un `.md` a pelo en el editor, que es la vía por la que orbit no
se entera del cambio.

---

## panel — dashboard dinámico

```bash
orbit panel                                        # panel del día
orbit panel week                                   # panel de la semana
orbit panel month                                  # panel del mes
orbit panel --from monday --to friday              # rango personalizado
orbit panel --open                                 # abre en editor (fichero transitorio cmd.md)
orbit panel --no-fed                               # sin proyectos federados
orbit panel --append mission:W12                   # añade a una nota
```

Dashboard con cuatro secciones (formato tabla markdown):

- **Prioridad**: tabla con 🔴 alta, 🔶 urgente (citas/vencidas en periodo), 🏁 hitos del mes
- **Agenda**: tabla por día con columnas: tipo, hora, descripción, proyecto (con link)
- **📊 Cronogramas**: barra de progreso por cronograma (solo si hay cronogramas activos)
- **Actividad**: entradas de logbook del periodo por proyecto

`--open` escribe a un fichero transitorio (`cmd.md`) y lo abre. El dashboard fijo del workspace es `📊panel/secretary/agenda.md` (regenerado en cada mutación tras F3 2026-05-19). `--no-fed` excluye federados.

Proyectos locales se muestran como links a `project.md`; federados con emoji del workspace (🌿).

---

## day — triaje del día

```bash
day                  # hoy en todo el workspace
day next-kr          # hoy en un proyecto (en su panel fijado: `day` a secas)
day fup              # aplazar: calendario de carga + ⏩ por lotes (3 5 viernes)
day fup next-kr      # ídem en un proyecto (en su panel fijado: `day fup`)
```

Lista numerada de lo que pide atención **hoy**, por bloques (la misma
agenda de hoy del secretario, con números):

- **🎯 Focus** — si hay hoja de focus esta semana: las tareas del `focus day`
  de hoy, en el orden de la hoja, numeradas primero (`✅ hechas/total` en la
  cabecera, debajo la línea de bloques de la semana). Salen aunque no tocaran
  hoy (p. ej. una tarea ancla sin fecha). Las ya hechas o cerradas se ven
  (`✅` / `❌`) pero **sin número**.
- **Hoy** — citas que caen hoy: eventos (también los de varios días ya
  empezados y las ocurrencias de los recurrentes), tareas e hitos con fecha de
  hoy. Por hora, y debajo lo que no tiene hora (como el secretario).
- **⚠️ Vencidas** — tareas e hitos pendientes con fecha pasada.
- **⏩ Decidir** — citas con un followup `⏩ <= hoy` (❗ si es de un día anterior).

**🎯** delante del título (fuera del bloque Focus) = bloque de la `focus week`
que no está en el `focus day`.

Cada cita sale una sola vez, en el primer bloque que le toca; sus `⏩` se ven
como marca en la fila (`❗⏩09-01`, `(+N)` si tiene más). **No salen** los
recordatorios, ni las tareas sin fecha y sin `⏩` vencido, ni los proyectos
federados (se leen, no se editan).

**Tarea / hito con crono**: sus pasos activos hoy o vencidos salen sangrados
bajo la fila (`↳ 1.2 Redactar intro · ⚠️ vencido 09-28`). Un paso así hace
aflorar el item aunque su fecha quede lejos (en ⚠️ Vencidas si algún paso venció,
si no en Hoy). Un paso sin fecha propia no cuenta: su fecha es la de hoy por
defecto y saldría todos los días.

Debajo, **📊 Cronogramas (solo lectura, sin número)**: los cronos **sin item**
(los de `crono add`), con sus pasos activos hoy o vencidos.

Eliges un número y una acción (mismo menú que `organize`):

| Tecla | Acción |
|---|---|
| ⏰ `h` | hora (`HH:MM` o `HH:MM-HH:MM`); si la cita no es de hoy, pide fecha (Enter = hoy) |
| 🗓️ `f` | fecha (`mañana`, `viernes`, `+3`, `YYYY-MM-DD`) |
| ⏩ `u` | followup: `fecha [descripción]`, Enter = mañana, `none` = sin fecha. Si la cita tenía `⏩` vencidos, los **mueve** a esa fecha (conservando su descripción); si no, añade uno. **No toca la fecha de la cita** (ADR-058): una cita o un hito con día sigue en su día; para moverlo, `f`. `none` deja la tarea / hito sin fecha y sin `⏩` (rechazado en eventos, recurrentes y con crono) |
| 🧹 `c` | borra un `⏩` (si hay varios, pregunta cuál) |
| 🏷️ `t` | título nuevo (Enter = dejarlo). Rechaza un título que ya tenga otra cita abierta del mismo tipo; el crono enlazado se conserva |
| ✅ `n` | done (tareas e hitos) |
| ❌ `d` | drop, con confirmación (defecto No) |
| ⏭️ `s` / Enter | vuelve a la lista sin tocar nada |

- Dar fecha u hora (`f`/`h`) **resuelve** los `⏩` vencidos de la cita: se borran.
- Tras cada acción, encima del prompt, una línea **relee la agenda** y dice cómo
  quedó la cita: `✓ ✏️ «X» · 💻foo → cancelada` (o `completada`, `eliminado de
  la agenda`, `2026-10-05 · ⏩ 10-07`, `sin fecha`, `2026-10-01 10:00`…). Si un drop o un done
  no surtió efecto, lo dice con `⚠️ … NO se ha cancelado`.
- `day fup`: la misma lista, sin menú, con un **calendario de carga** (semana
  en curso + 4) encima del prompt. El fondo gris de cada día indica cuántas
  citas tiene: sin fondo = 0, y de claro a oscuro 1–4 · 5–9 · 10–14 · ≥15
  (fuera de un terminal, glifos `· ░ ▒ ▓ █`). Hoy, entre corchetes, cuenta lo
  que lista `day` (incluido el arrastre); un día futuro, sus citas y sus `⏩`.
  Sin recordatorios. El número va entre paréntesis si lo pides en `orbit.json`:
  `"load_calendar": {"counts": true}`.

  Entrada (un entero solo es siempre un número de cita; lo demás, fecha):

  | Entrada | Efecto |
  |---|---|
  | `3 5 7 viernes [desc]` | la misma fecha a varias |
  | `3:viernes 5:+7` | parejas (fecha de una palabra) |
  | `3` · `3 5` | pide la fecha (Enter = mañana) |
  | `3 5 none` | sin fecha |

  Con más de una cita enseña lo entendido y pide confirmación (`[S/n]`); si
  algún número o fecha no vale, no aplica nada. Ver
  [ADR-056](DECISIONS.md#adr-056--day-fup-calendario-de-carga-y--por-lotes).
- Las mutaciones usan los mismos runners que `task edit`, `task done`…: imprimen
  el item resultante, dejan undo y, en recurrentes, preguntan ocurrencia o serie.
- Al salir (`q`) con cambios, refresca derivados (dash + ring + .ics).
- Para título, notas, recurrencia o ring: sal y usa `task edit` etc.

Ver [ADR-051](DECISIONS.md#adr-051--day-y-organize-proyecto-dos-triajes-un-motor).

---

## organize — triaje de un proyecto

```bash
organize next-kr     # todo lo pendiente del proyecto
organize             # en el panel fijado a un proyecto
```

Mismo motor y mismo menú que `day`, pero con **todo** lo pendiente del
proyecto. Bloques, en orden: **Hoy · ⚠️ Vencidas · ⏩ Decidir · Próximas · Sin
fecha**. A diferencia de `day`:

- Salen los **recordatorios**.
- **Próximas**: citas con fecha futura (y series recurrentes vivas).
- **Sin fecha**: tareas e hitos en reposo (hitos primero).
- Los `⏩` futuros también se ven en la fila.
- **📊 Cronogramas**: todos los abiertos **sin item**, con barra de progreso y
  deadline, más sus pasos activos o vencidos. Solo lectura. Los que cuelgan de
  una tarea / hito salen bajo su fila, como en `day`.

`organize` sin proyecto en el panel general no hace nada y remite a `day`.

**Modo antiguo** (se mantiene hasta retirarlo; avisa al entrar):

```bash
organize --triage                # followups ⏩ <= hoy: [p]lan [s]nooze [c]lear do[n]e [d]rop s[k]ip
organize tasks                   # filtro de tipo: tasks | ms | ev | rem
organize -P week                 # periodo: today | week | month | YYYY-MM-DD | YYYY-Wnn
organize --undated               # incluye tareas/hitos sin fecha
```

Cualquiera de esas opciones activa el flujo anterior (`[d]rop [n]done [f]echa
[h]ora [s]kip`); con `-p <proyecto>` se acota. Alias legacy: `reorganize`.

---

## focus — semana por carriles y día

```bash
orbit focus week              # planifica la semana actual (ISO)
orbit focus week --next       # planifica la semana siguiente
orbit focus week --review     # abre el archivo semanal en $EDITOR
orbit focus day               # hasta 5 tareas focus de hoy (ver «Focus del día»)
orbit focus summary           # éxito 0–5 por día y semana (ver «Resumen»)
```

Crea **bloques** (tasks con `date` + `time HH:MM-HH:MM`) en `mission/agenda.md` agrupados por carril:

| Carril | Significado | Default template |
|--------|-------------|------------------|
| ⚓ Anchor | sostiene la semana, trabajo principal | 2 proyectos × 2 bloques |
| 🔥 Push   | iniciativa que estás empujando        | 1-2 proyectos × 1 bloque |
| 🌿 Joy    | opcional que nutre                    | 0-1 proyectos × 1 bloque |

**Plantilla por workspace**: `mission/notes/focus-template.md` se materializa la primera vez desde `📐templates/focus-template.md` y queda editable a mano. Define cuántos proyectos por carril, cuántos bloques por proyecto, duración default (90 min) y theme days. Cada workspace tiene la suya (personal ≠ trabajo).

**Tres modos** al ejecutar `orbit focus week`:

1. **Repetir** (default si existe W-1) — clona la semana anterior: mismos proyectos en cada carril, mismos slots desplazados +7 días. Pide confirmación [Y/n].
2. **Plantilla** — usa el template para cantidades y W-1 (si existe) como default de proyectos. Pregunta sólo qué proyectos llenan cada carril.
3. **Libre** — prompt proyecto a proyecto. Para cada bloque: día (`lun`/`mar`/`mie`/`jue`/`vie`) y hora (`HH:MM` o `HH:MM-HH:MM`; si das sólo start, añade duration del template).

**Archivo semanal**: `mission/notes/2026-WNN-focus.md`, válido **lunes–domingo**, con cabecera (fechas, status: `normal` o `especial`, balance), proyectos por carril, bloques agrupados con su símbolo de estado, contador autogenerado y retrospectiva (texto libre).

**Símbolos por bloque** (los escribe orbit, no son casillas): `⬜` abierto · `✅` hecho · `❌` no hecho / drop · `❔` no encontrado. Al hacer `task done` / `task drop` de un bloque (también desde `organize`/triaje), su línea pasa a `✅ MM-DD` / `❌ MM-DD` en la hoja de esta semana, o en la de la anterior si aún no está balanceada. Lo cerrado a mano en Obsidian lo recoge el balance, sin fecha.

**Contador**: regenera al ejecutar `orbit focus week` sobre semana existente. Cuenta tasks `done` en mission por carril (lookup por orbit-id, robusto a renombrados del título) y refresca los símbolos.

**Balance**: el primer `save` (con cambios) tras el domingo cierra la semana: drop de los bloques abiertos en mission, símbolos congelados y `- Balance: hecho YYYY-MM-DD`. Desde ahí la hoja es la verdad histórica (contador y `focus year` leen los símbolos, no la agenda). Aproximado: una task cerrada entre el domingo y el save cuenta como hecha. Hojas anteriores a esta versión (sin línea `Balance`) se balancean una vez **sin** drop.

**Status: especial** (vacaciones, congreso) → contador muestra `—` en lugar de `done/total`. Edita a mano en el frontmatter.

**Sobre una semana ya creada**, el comando **muestra la semana** (estado en vivo: `focus week — 2026-W41 · ✅ 2/7 bloques`, una línea por proyecto con sus bloques `✅ lun 09:00 · ⬜ mié 09:00`, y `Días: lun ✅ 3/3 · mar ⬜ 1/2`) y luego el menú; **Enter sale** sin tocar nada:
1. **cambiar proyectos / fechas** — muestra los bloques numerados con fecha y hora, y en bucle (Enter termina):
   - `a` añadir proyecto (+ bloques; flujo libre con el estado existente, no reescribe la hoja)
   - `q` quitar proyecto — **borra** sus bloques abiertos de `mission/agenda.md` y de la hoja (replanificar no es fallar: no cuentan como ❌); los ya cerrados se quedan como registro. Sin bloques, sale de `## Carriles`
   - `m` mover bloque — nuevo día y hora del bloque abierto `#n` (misma task, mismo `orbit_id`)
2. contar — regenera contador y símbolos (útil tras editar a mano; done/drop ya lo hacen solos)
3. abrir en $EDITOR (== `--review`; la retrospectiva está al final)

**Retrospectiva guiada**: cada fichero semanal recién creado lleva tres preguntas en un comentario HTML (invisible en render, visible al editar): "¿Qué sostuvo la semana?", "¿Qué cedió y por qué?", "¿Qué pruebo distinto la W siguiente?". Texto libre debajo, sin formulario.

Los bloques aparecen automáticamente en Calendar.app (vía `.ics`) por ser tasks normales de mission.

### Focus del día

```bash
orbit focus day               # elige hasta 5 tareas focus de hoy
```

Lista, en tres grupos numerados de seguido, las tasks e hitos abiertos de proyectos locales:

- **📅 Hoy y vencidas** — fecha **hoy** (por hora) y **vencidos** (⚠️), incluidos los bloques de focus week de hoy;
- **⏩ Followups** — con un ⏩ de hoy o pasado (`⏩ MM-DD`, y `🗓️ MM-DD` si además tienen fecha);
- **⚓ Proyectos ancla** — todas las tasks abiertas (con o sin fecha) de los proyectos del carril ⚓ de la focus week.

Elegir una no cambia nada en su `agenda.md`: ni fecha ni ⏩ (el ⏩ se resuelve con `day fup`). Selección por números (`1 3 4`); `+proyecto` añade todas las abiertas de ese proyecto a la lista. Máximo 5.

Se apuntan en la sección `## Días` de la hoja semanal (`### 2026-10-05 · lunes`, una línea `- ⬜ [orbit:id] [[proyecto]] · título` por tarea). Si la semana no tiene focus week se crea una hoja mínima solo con días; un `focus week` posterior la planifica conservando días y retrospectiva. Las tareas son las reales: focus solo les asigna `orbit_id` si no lo tenían; nunca las crea ni hace drop.

Repetido el mismo día: **muestra el focus de hoy** con el estado en vivo (`focus day — 2026-10-05 · lunes · ✅ 1/3` y una línea por tarea) y luego `1) añadir` (hasta completar 5) · `2) rehacer`; **Enter sale** sin tocar nada.

**En la agenda del secretario** (`📊panel/secretary/agenda.md`): sección `## 🎯 Focus` entre los contadores y `📅 Hoy`, con la semana (bloques por carril ✅⬜ y `✅ n/m`) y las tareas de hoy. Lee el estado **en vivo** de la verdad (también lo cerrado a mano en Obsidian). Aparece solo si hay hoja para esta semana; `- Status: off` en la hoja la oculta.

`task done` / `task drop` marcan la línea `✅ MM-DD` / `❌ MM-DD`. **Balance del día**: el primer `save` (con cambios) de un día posterior congela los símbolos (abierta → ❌, desaparecida → ❔) y la cabecera pasa a `### … · balance n/m`; desde ahí no se toca.

### Resumen

```bash
orbit focus summary              # últimas 8 semanas (la actual incluida)
orbit focus summary --weeks 12
```

Una fila por semana: siete celdas de día (focus day) y, **aparte**, la celda de la semana (bloques de focus week, con `n/m bloques`). Cada celda es un nivel **0–5 = round(5 · hechas / total)** — proporción: 3/3 es 5. Vacía = sin focus. El nivel va como dígito y, en terminal, con fondo gris más oscuro cuanto más alto (sin depender del color). `[ ]` = hoy. Pie con totales (días con focus, tareas ✅, días a 5; bloques ✅). Días/semanas balanceados se leen de la hoja; los no balanceados, en vivo de la verdad.

### Vista anual

```bash
orbit focus year              # regenera mission/notes/YYYY-focus.md (año actual)
orbit focus year --year 2025  # otro año
```

Construye una tabla con una fila por semana ISO (52 ó 53) y columnas `Semana | Fechas | Status | Anchor | Push | Joy`. La columna `Fechas` muestra `MM-DD/MM-DD` (lun-vie) y se rellena siempre, incluso para semanas sin planificar. La celda de cada carril muestra el proyecto y un tomate 🍅 por bloque hecho o una cruz ❌ por bloque planificado-no-hecho (`[[paper-neutrinos]] 🍅🍅`); con N proyectos en un carril se renderizan en líneas separadas (`<br>`) — anchor/push/joy admiten cualquier cantidad. La columna `Status` usa 🟢 para semana normal, 🟡 para `especial` y `—` para semanas sin fichero. Las semanas sin fichero aparecen como `WNN` plano (sin wikilink) para evitar links fantasma en Obsidian.

Footer `## Totales` agrega bloques hechos / planificados por carril; **las semanas `especial` se excluyen del agregado** (sus targets están aparcados por diseño).

Refresh: además del verbo explícito, la vista anual se regenera automáticamente al cerrar `orbit focus week` (creación inicial o menú opciones 1 y 3). El fichero anual es **vista derivada** — `orbit focus year` lo sobrescribe sin preguntar; edita los semanales, no el anual.

---

## report — informe de actividad

```bash
orbit report [project...] [--date D] [--from D] [--to D] [--no-fed] [--open [EDITOR]]
orbit report today                    # actividad de hoy
orbit report week                     # actividad de esta semana
orbit report month                    # actividad de este mes
orbit report yesterday                # actividad de ayer
orbit report myproject today          # actividad de hoy en un proyecto
orbit report --summary [logbook|agenda|highlights|all] [--date D] [--from D] [--to D]
```

- Atajos de periodo: `today`/`hoy`, `yesterday`/`ayer`, `week`/`semana`, `month`/`mes`
- Sin proyecto: muestra informe de todos los proyectos activos
- Con proyecto(s): informe solo de esos proyectos
- Sin fechas: últimos 30 días
- Muestra: entradas de logbook, highlights, tareas completadas/pendientes/vencidas, hitos, eventos
- `--summary`: tabla markdown ordenada por actividad descendente
  - Sin valor: logbook + agenda (las secciones con datos filtrados por periodo)
  - `logbook`: solo tabla de entradas por tipo
  - `agenda`: solo tabla de tareas/hitos/eventos
  - `highlights`: solo tabla de highlights (snapshot actual, sin filtro de periodo)
  - `all`: las tres tablas
- Compatible con `--log`: redirige el informe al logbook de otro proyecto (tablas markdown se insertan sin code block)

---

## Servicios externos

> Orbit gestiona estas conexiones automáticamente (al arrancar, al operar sobre citas, al hacer save). Los comandos siguientes permiten interactuar manualmente.

### save — versionado con git

```bash
orbit save [--commit "<mensaje>"]
```

Alias legacy: `orbit commit` sigue funcionando.

- No pregunta nada: muestra los ficheros modificados y guarda con el mensaje `sync <fecha hora>`
- Un mensaje propio solo con `--commit "…"`
- Ejecuta doctor pre-check: valida agendas/logbooks antes del save
- Ejecuta reconciliación gsync: detecta renombramientos de citas en el markdown y migra IDs de Google
- Push al remoto: `orbit_push` desde la terminal del sistema (fuera de la shell)

### Sincronización legacy con Calendar.app (`gsync`, `calsync`)

**Deprecado desde v0.33**. La sincronización con Calendar pasa ahora por `.ics` (ver sección siguiente) y `agenda.md` es la única fuente de verdad. Calendar.app es read-only por subscripción.

Si por alguna razón necesitas el camino AppleScript-write antiguo (push directo, reconciliación de drift…), ver `DORMANT.md` con los pasos exactos para revivirlo. Por defecto los comandos `orbit gsync` y `orbit calsync` ya no aparecen en el CLI.

### ics — export iCalendar y suscripciones de Calendar.app (ruta principal desde v0.33)

```bash
orbit ics <proyecto>                       # imprime .ics a stdout
orbit ics <proyecto> --out file.ics        # escribe a fichero
orbit ics --bucket agenda                  # un bucket de workspace (agenda|events|ms|...)
orbit ics --workspace                      # regenera todos los .ics en cloud_root/calendar/
orbit ics --validate                       # dry-run: cuenta VEVENTs por bucket, sin escribir
```

**Auto-regen**: cualquier mutación CLI sobre task/ms/ev/reminder/crono/ics-import/email dispara en background un thread daemon que ejecuta `dash` (coalescido) + `ring.refresh_all()` + `write_workspace(project_filter=<proj>)` — `.ics` y Reminders.app se actualizan solos sin esperar a `save`. Mutaciones de `log`/`hl`/`project` disparan solo dash (no afectan a citas). Render a HTML se reserva para `save` (commit_post).

**Topología** (en `cloud_root/calendar/`, configurable en `ics_buckets`):

```
calendar/
  ├── events.ics                ← solo eventos (azul)
  ├── ms.ics                    ← solo milestones (amarillo) — destacan visualmente
  ├── agenda.ics                ← tasks + reminders + cronogramas (gris)
  └── projects/
        ├── phd-diego.ics       ← per-proyecto, TODAS las citas (para compartir refs puntuales)
        └── …
```

**Suscripción desde Calendar.app** (USC OneDrive — receta probada en orbit-ws):

1. En OneDrive web, click derecho sobre el `.ics` → Compartir → `Cualquier persona con el enlace` (no `Personas de la USC`).
2. Copia el enlace; tendrá formato `https://nubeusc-my.sharepoint.com/:u:/g/personal/.../<id>?e=<token>`.
3. Convierte para Calendar.app:
   - `https://` → `webcal://`
   - Añade `&download=1` al final (fuerza .ics crudo en vez del visor HTML)
4. Calendar.app → `Archivo → Nueva suscripción de calendario` → pega el `webcal://` → `Suscribir`.
5. Configura: nombre, Ubicación = `En mi Mac`, refresco = `Cada 5 minutos`, color a elección.

**Propagación a iPhone/iPad**: Apple quitó la opción "iCloud" del diálogo macOS ~2023. Para sincronizar entre dispositivos: ve a `icloud.com/calendar` web → sidebar → click derecho en `Calendarios` → `Nueva suscripción` → pega el mismo URL. Aparecerá automáticamente en todos tus Apple devices.

**Si OneDrive de tu institución no permite "Cualquiera con el enlace"** (USC sí lo permitía): alternativas son GitHub Pages (repo público con el .ics) o Google Drive personal con `https://drive.google.com/uc?export=download&id=<id>`.

**Buckets**: configurables en `calendar-sync.json`. Ejemplo de orbit-ws (3 buckets para colorear ms aparte):

```json
{
  "ics_buckets": {
    "events": ["event"],
    "ms":     ["milestone"],
    "agenda": ["task", "reminder", "cronograma"]
  }
}
```

Default si no defines `ics_buckets`: `agenda=task+rem`, `events=ev+ms+crono`. Cada `kind` (`task`/`milestone`/`event`/`reminder`/`cronograma`) debe aparecer en **exactamente un** bucket. `doctor` valida el reparto y la frescura (alerta si un `.ics` lleva >24h sin update). El nombre del bucket es el nombre del fichero (`agenda` → `agenda.ics`).

**Duración de cada cita en .ics** (sintética; no toca `agenda.md`):
- `event` (sin `--end-time`), `milestone`, `task`, `cronograma`: 60 min
- `reminder`: 5 min
- `event` con `--time HH:MM-HH:MM` o `--end-time`: respeta lo declarado

**orbit-id visible**: cada VEVENT lleva `[orbit:xxxxxxxx]` al final de `DESCRIPTION` (visible en Calendar.app/iOS) + `X-ORBIT-ID` custom prop + UID `<orbit_id>@orbit`. Si ves un evento "raro" en Calendar.app, el orbit-id en la descripción te permite localizar la cita en `agenda.md` rápido.

**Propagación a Calendar.app**: `orbit render` (que corre tras cada save) regenera todos los `.ics` y lanza un `tell application "Calendar" to reload calendars` AppleScript (read-only) para forzar refresh inmediato. Latencia de Mac → ~2 s. iPhone hereda vía iCloud al ritmo de iCloud (5-15 min).

**Snapshot diff**: cada `.ics` se guarda con un `.ics.snapshot` paralelo (versión anterior). `write_workspace` reporta cuántas citas se añadieron/modificaron/eliminaron desde el último render — útil para auditar drift sin abrir Calendar.app.

### ics-share / ics-import — compartir e importar citas puntuales

```bash
orbit ics-share <proj> --orbit-id ID     # exporta esa cita a /tmp/orbit-<id>.ics
orbit ics-share <proj> --desc PATTERN    # busca por descripción (interactivo si ambigüedad)
orbit ics-share <proj> --orbit-id ID --out ruta.ics
orbit ics-import <proj> ruta.ics         # importa un .ics como nueva cita
orbit ics-import <proj> --clipboard      # lee del portapapeles (pbpaste)
```

**Scope** (v0.33): solo **citas puntuales**, no series recurrentes. Si exportas una cita recurrente, exporta solo la **próxima ocurrencia**. Si el `.ics` de entrada trae `RRULE`, se ignora y se importa solo la primera ocurrencia con un warning.

**Export**: el path resultante se imprime y se copia al portapapeles para que en Mail solo tengas que `Cmd+V` en el adjunto. El .ics lleva `METHOD:PUBLISH`, `X-WR-CALNAME` informativo, y la cita con todos sus props (UID, SUMMARY, DTSTART, DTEND, DESCRIPTION con `[orbit:xxx]`, X-ORBIT-*, VALARM si tiene ring).

**Import**:
- Auto-detecta el `kind`: respeta `X-ORBIT-KIND` (round-trip), o usa `event` si es all-day / time-range, o pregunta si es ambiguo.
- Si el SUMMARY trae el prefijo `[<proyecto>] [<emoji>] ` (export propio de orbit), lo strippea.
- `URL`/`LOCATION` con URL de meeting (zoom/meet/teams/indico) → nota `🚪 <url>`.
- `DESCRIPTION` → notas indentadas (sin la línea "Proyecto:" ni el tag `[orbit:xxx]`).
- TZIDs: `Z` (UTC) se convierte a local; `Europe/Madrid` se toma como floating; otros se toman como floating con warning.
- Conflicto: si ya existe cita con mismo `desc+date` en el destino → prompt `[d-duplicar / o-overwrite / c-cancel]`.
- Tras crear: regen automático del `.ics` del proyecto.

### cloud / render / deliver — OneDrive, Google Drive y entrega de ficheros

```bash
orbit render                          # renderiza ficheros del último save
orbit render <project>                # renderiza un proyecto completo
orbit render --full                   # renderiza todos los proyectos

orbit cloud deliver <project> <file>  # entrega un fichero al cloud del proyecto
orbit cloud sync [--dry-run]          # fuerza sync completo md→HTML al cloud
orbit cloud imgs [--dry-run]          # recoge imágenes de _imgs/ y entrega a cloud

orbit deliver <project> <file>        # alias top-level de `cloud deliver`
```

- Convierte ficheros `.md` de cada proyecto a `.html` en el directorio cloud
- Front-page del cloud: `workspace.html` (de `workspace.md`) + `index.html` stub con `<meta http-equiv="refresh">` redirigiendo a `workspace.html` (para que el browser abra el cloud-root automáticamente)
- Incluye soporte KaTeX para ecuaciones LaTeX (`$...$` y `$$...$$`)
- `cloud sync` se ejecuta automáticamente en background tras cada `save`; el verbo manual sirve para forzar o auditar con `--dry-run`
- Estructura cloud: `cloud_root/{tipo}/{proyecto}/cloud/{logs,hls,imgs,...}/`
- `cloud_root` se configura en `orbit.json`; cada proyecto tiene un link `[cloud]` en `project.md`

### Mac Reminders — notificaciones

No hay un comando propio — `--ring` es un flag transversal disponible en `task`, `ms`, `ev`:

```bash
orbit task add next-kr "Reunión" --date tomorrow --time 10:00 --ring 30m
```

- Si creas una cita con `--time` sin `--ring`, Orbit pregunta interactivamente (defecto: 5 min antes)
- Al entrar en la shell, se programan las notificaciones del día de todos los workspaces
- Valores: `1d` (1 día antes), `2h`, `30m`, `HH:MM` (hora fija), `YYYY-MM-DD HH:MM`

### Setup — configuración interactiva

```bash
orbit setup                    # asistente interactivo de configuración
```

- Guía paso a paso: workspace, tipos, editor, Google Sync, cartero (Gmail/Slack), federación
- Si `orbit.json` ya existe, muestra valores actuales como defaults
- Cada sección es opcional — Enter para saltar
- Genera/actualiza `orbit.json` y `federation.json`

### mail (cartero) — notificaciones de correo

```bash
orbit mail                     # check manual: muestra no leídos por etiqueta (detallado)
orbit mail --summary           # check en vivo, formato compacto (una línea por fuente)
orbit mail --status            # estado del proceso background
orbit mail --start             # arranca el proceso background
orbit mail --stop              # para el proceso background
```

- Vigila Mail.app, Gmail (legacy) y/o Slack y avisa de mensajes no leídos
- Notificación macOS cuando llegan mensajes nuevos (solo al subir el conteo, no en cada check)
- Proceso background: se lanza al entrar en la shell, un solo proceso por workspace (PID lock)
- Configuración en `orbit.json`:

```json
"cartero": {
  "mail": {
    "watch": [
      {"account": "🏛️ USC",     "mailbox": "Inbox"},
      {"account": "🏠 Personal", "mailbox": "🏠 hogar"}
    ],
    "interval": 600
  },
  "slack": {
    "channels": ["general", "alertas"],
    "interval": 600
  }
}
```

- **Mail (recomendado)**: AppleScript a Mail.app. `watch` lista pares `{account, mailbox}` — los nombres son los que muestra Mail.app (los Gmail labels aparecen como mailboxes IMAP dentro de la cuenta Gmail). Sin OAuth, sin tokens. Requiere Mail.app abierto y sincronizado; si no está corriendo, cartero salta esa fuente sin error
  - Listar tus cuentas: `osascript -e 'tell application "Mail" to get name of every account'`
  - Listar mailboxes: `osascript -e 'tell application "Mail" to get name of every mailbox of account "X"'`
- **Gmail (legacy)**: `labels` = etiquetas a vigilar. Requiere `credentials.json` + API de Gmail habilitada en Google Cloud Console. Mantener solo si no migras a Mail.app
- **Slack**: `channels` = canales a vigilar. Requiere token de usuario en `ORBIT_HOME/.slack-token` (una línea, `xoxp-...`). Slack para Mac no expone AppleScript útil — la API es la única vía con conteo por canal
- `interval`: segundos entre checks (default: 600 = 10 min)
- Estado en `ORBIT_HOME/.cartero-state.json`, PID en `ORBIT_HOME/.cartero.pid`

---

## Mantenimiento interno

### history — historial de comandos

```bash
orbit history                          # hoy
orbit history --date 2026-03-11        # día concreto
orbit history --date 2026-03           # mes
orbit history --date 2026-W11          # semana
orbit history --from D --to D          # rango
orbit history --open                   # abrir en editor
```

- Registra automáticamente los comandos que modifican estado (log, task, ms, ev, note, save, hl, project...)
- No registra comandos de solo lectura (agenda, report, view, ls, doctor, search, history, open)
- Fichero: `history.md` en la raíz de Orbit

### doctor — validación de ficheros

```bash
orbit doctor [<project>]        # revisa todos o un proyecto
orbit doctor --fix [<project>]  # revisa y ofrece corregir
```

El doctor hace 3 tipos de check (mismo comando, salida segmentada):

1. **Sintaxis por proyecto** — logbook (fechas, tipos, emojis), agenda (marcadores, recurrencia, eventos), highlights (orbit-items: emoji-tipo reconocido, links balanceados), cronogramas.
2. **Refs por proyecto** — para cada link `[…](target)` en logbook + highlights, verifica que el target existe:
   - `./cloud/...` → busca en `<workspace>/<proj>/cloud/...` (el symlink a cloud_root)
   - `./notes/...` → busca en `<proj>/notes/...` (propia o symlink a externa)
   - `/abs/path` o `~/path` → busca en el filesystem local
   - Refs cross-project (`⚙️gestion/⚙️foo/...`) → busca en `ORBIT_HOME/...`
   - URLs (`http://`, `mailto:`, `message://`, etc.) y anchors (`#sec`) se ignoran
3. **Entorno (workspace)** — corre una sola vez por invocación:
   - `orbit.json` existe, JSON válido, claves `cloud_root` y `types` presentes
   - `cloud_root` apunta a un directorio existente y escribible
   - `federation.json` (si existe) JSON válido y cada `federated[].path` existe
   - Linked md externos: cada symlink en `notes/` apunta a un fichero real
   - Ring: plist, TCC, ring.json freshness
   - ICS: buckets bien configurados + frescura de los `.ics` en cloud

Se ejecuta automáticamente al iniciar la shell, antes de cada save **y periódicamente en background por el watchdog** (ver más abajo). Con `--fix`: muestra correcciones disponibles y permite aplicarlas interactivamente.

### watchdog — pre-check + refresh periódico

Daemon background que arranca al abrir la shell. Cada `interval_minutes` (defecto 60):

1. Corre `doctor` sobre el workspace.
2. **Si hay issues** → escribe `.doctor-pending` (marker) y NO regenera derivados (📊panel/secretary/{agenda,projects,calendar,report-summary} + 📊panel/ring/rings, .ics, ring.json se congelan en su última versión limpia). El prompt del REPL muestra al siguiente input — una sola vez por sesión:

   ```
   🏥 Doctor (14:30): 3 problemas detectados — ejecuta `doctor`
   ```

3. **Si limpio** → `_run_full_refresh_coalesced` (dash + ring + ics) y borra el `.doctor-pending` si existía.

Propósito: capturar drift introducido por edición externa (Obsidian, editor) entre comandos orbit. Sin watchdog, el `.ics` y Reminders.app no se enterarían de un `agenda.md` editado a mano hasta el siguiente `save`.

Config en `<workspace>/orbit.json` (clamp `[5, 1440]` minutos):
```json
"watchdog": {
  "enabled": true,
  "interval_minutes": 60
}
```

Para desactivarlo: `"enabled": false`.

### ring — alarmas vía Reminders.app (Orbit Ring)

```bash
orbit ring refresh                        # regenera ring.json en todos los workspaces y aplica
orbit ring refresh --no-daemon            # solo escribe ring.json, sin tocar Reminders.app
orbit ring status                         # muestra ring.json por workspace + estado del plist launchd
orbit ring install                        # instala ~/Library/LaunchAgents/com.orbit.ring-daemon.plist
orbit ring uninstall                      # descarga y elimina el plist
```

Modelo declarativo: `agenda.md` (verdad) → `<ws>/.reminders/ring.json` (ventana 7 días) → daemon EventKit reconcilia la lista de Reminders.app del workspace. Una lista por workspace (default = nombre del directorio del workspace, e.g. `🚀orbit-ws`, `🌿orbit-ps`). El daemon nunca toca items sin tag `[orbit:xxx]` — los reminders manuales del usuario en la misma lista están a salvo.

Triggers automáticos (vía hook system):
- `shell_start` → refresca al arrancar `orbit shell`
- `commit_post` → refresca tras cada `orbit save` (nombre interno del chain mantiene `commit_post`)
- `launchctl WatchPaths` (si has hecho `orbit ring install`) → cualquier escritura del `ring.json` dispara el daemon
- `StartCalendarInterval` 00:05 (vía launchd) → sweep nocturno

Config en `<workspace>/orbit.json`:
```json
"ring": {
  "enabled": true,           // false → vacía la lista del workspace
  "days":    7,              // ventana rolling, clamped a [1, 30]
  "list":    "🚀orbit-ws"    // default = workspace_root.name
}
```

Eligibilidad de una cita en el ring: tiene `--ring`, tiene `time`, tiene `orbit_id`, status pending (task/ms) o no cancelled (reminder). Recurrentes se expanden en la ventana (un EKReminder por ocurrencia con orbit_id derivado `<base>-<date>`).

Primera vez tras `orbit ring install`: macOS pide autorizar el binario Python en *System Settings → Privacy & Security → Reminders*. Si el log `~/Library/Logs/orbit/ring-daemon.stderr.log` dice `access denied`, autoriza y haz `launchctl kickstart -k gui/$(id -u)/com.orbit.ring-daemon`.

### archive — archivado de entradas antiguas

```bash
orbit archive [<project>] [--months N] [--dry-run] [--force]
orbit archive orbit --agenda              # solo tareas/hitos done + eventos pasados
orbit archive orbit --logbook             # solo entradas de logbook
orbit archive orbit --notes               # solo notas obsoletas
orbit archive orbit --agenda --logbook    # combinación
```

- Sin proyecto: limpia todos los proyectos
- Sin flags: limpia todo, preguntando confirmación por cada categoría
- La agenda muestra la lista de citas que se borrarían y pregunta `[s/N]`
  (Enter = no); logbook y notas siguen preguntando `[S/n]` con el recuento
- `--months N`: antigüedad mínima para eliminar (defecto: 6 meses)
- `--dry-run`: muestra qué se eliminaría sin borrar nada
- `--force`: salta todas las confirmaciones

Qué se limpia:
1. **agenda**: tareas/hitos completados `[x]`/cancelados `[-]` + eventos pasados
   - Evento de varios días: cuenta su **fin** (`--end`), no su inicio.
   - Serie recurrente: **nunca** se borra mientras viva; solo cuando acabó, es
     decir, con `--until` anterior al corte. Una serie sin `--until` no se
     archiva nunca. Sus ocurrencias pasadas no están escritas (se calculan); las
     ocurrencias editadas sí, como eventos sueltos, y se archivan como tales.
2. **logbook**: entradas con fecha anterior al corte
3. **notes**: notas en `notes/` no modificadas en N meses

Los datos eliminados son recuperables con `git log -p -- <fichero>`.

### claude — asistente integrado

```bash
orbit claude "¿cómo creo una tarea recurrente?"
orbit claude "quiero ver la agenda de la semana"
```

- Envía la pregunta a Claude con la CHULETA como contexto
- Si un comando falla y hay API key, sugiere alternativas automáticamente
- Requiere: `pip install anthropic` + `ANTHROPIC_API_KEY` env var

---

## Startup — al iniciar la shell

Al entrar en `orbit shell`:

1. **Doctor** — valida la integridad de logbook, agenda y highlights; ofrece corregir errores
2. **Ficheros sin trackear** en `🚀proyectos/` — ofrece añadirlos a git
3. **Cambios sin save** — ofrece hacer save + push (mensaje por defecto: `sync YYYY-MM-DD`)
4. **gsync** en background + **recordatorios** — sincroniza con Google y programa los recordatorios del día (tras save)
5. **Cartero** — lanza el proceso background de correo si hay configuración en `orbit.json`

En un **panel de proyecto** (`orbit shell --project X`) no corre ninguno de
los cinco: son trabajo del workspace y los lleva el panel general. Correrlos
en las dos ventanas duplicaría watchdogs y ofertas de commit, y repartiría el
aviso del doctor entre ambas.

---

## Federación de workspaces

Orbit puede leer proyectos de otros workspaces (lectura federada). Útil para ver citas personales desde el workspace de trabajo.

Configuración: `federation.json` en la raíz del workspace:

```json
{
  "federated": [
    {"name": "personal", "path": "~/🌿orbit-ps", "emoji": "🌿"}
  ]
}
```

- Los comandos de lectura (`panel`, `agenda`, `report`, `ls`, `search`) incluyen proyectos federados por defecto
- `--no-fed`: desactiva la federación para ese comando
- Los comandos de escritura (`add`, `edit`, `done`, `drop`) solo operan en el workspace activo
- Los proyectos federados se muestran con el emoji del workspace (🌿) sin link
- Los recordatorios del Mac (`ring`) se programan para ambos workspaces al entrar en la shell
- La federación es asimétrica: cada workspace decide qué otros ve

---

## --open — abrir resultado en editor

Los comandos de consulta aceptan `--open [EDITOR]`:
capturan el output, lo escriben en un fichero markdown y lo abren en el editor.

```bash
orbit agenda --open               # abre en editor por defecto
orbit agenda --open obsidian      # abre en Obsidian
orbit panel --open code           # abre en VS Code
```

- `cal --open` → `📊panel/secretary/calendar.md`
- `panel --open` / `agenda --open` / el resto → `cmd.md` (transitorio)

El dashboard fijo del workspace es `📊panel/secretary/agenda.md`, regenerado
en cada mutación de cita / log / hl / project (carril hot). `orbit dash`
refresca además los viewers cold: `📊panel/secretary/{projects,calendar,
cronos,hitos,logbook,report-summary}.md` + `📊panel/ring/rings.md`. Outputs
agrupados por backend (`secretary/` lee la verdad de proyectos; `ring/` lee
`ring.json`). El header de `agenda.md` enlaza `hitos.md` (detalle de los
hitos vencidos + próximos 30 días: 🏁, fecha (con ⚠️ si vencido), proyecto,
hito y barra del cronograma asociado si su `deadline:` nombra el hito).
Convención de columnas en todas las tablas de citas: **col1 = tipo**
(📅/☐/🏁/💬), **col2 = estado/alerta** (🔔 alarma · ⏩ por-triar · ⚠️
vencida). Ventanas configurables en `orbit.json`:

```json
"secretary": {
  "report_days": 14    // ventana de report-summary, [1, 365]
}
```

Estos ficheros se pueden fijar en Obsidian (pin tab) para tener un dashboard permanente.

Sin especificar editor, se usa el editor por defecto (en orden de prioridad):
1. `ORBIT_EDITOR` (variable de entorno)
2. `"editor"` en `orbit.json` (por workspace)
3. Abridor del sistema (`open` en macOS)

Comandos que lo admiten: `ls` · `view` · `search` · `report` · `agenda` · `panel` · `help` · `history` · `crono show/list/gantt` · `note list`

Los comandos que abren ficheros directamente usan `--editor E` (no `--open`): `open`, `note create/open/import`, `hl edit`, `project edit`, `shell`.

---

## --log — guardar resultado en logbook

```bash
orbit ls projects --log mission                     # guarda en logbook de mission como #apunte
orbit ls tasks --log mission --log-entry evaluacion  # como #evaluacion
orbit view next-kr --log orbit                      # resumen al logbook de orbit
orbit report orbit --log mission                    # informe de orbit al logbook de mission
```

- `--log PROJECT` captura el output y lo añade como entrada al logbook del proyecto indicado.
- `--log-entry TYPE` cambia el tipo de entrada (por defecto `apunte`).
- La entrada incluye una línea resumen + el output completo en bloque de código.
- Compatible con `--open`: ambos pueden usarse a la vez.

Comandos que lo admiten: los mismos que `--open`.

---

## Tipos de proyecto

Configurables en `orbit.json`. Ver: `orbit project type`

## Estados

`new` ⬜ · `active` ▶️ · `paused` ⏸️ · `sleeping` 💤 · `[auto]` (inferido por Orbit)

- `new`: proyecto recién creado, sin entradas en logbook

## Prioridades

`alta` 🔴 · `media` 🔶 · `baja` 🔹

---

## Fechas — lenguaje natural

Todos los `--date`, `--from`, `--to` aceptan:

`today/hoy` · `yesterday/ayer` · `tomorrow/mañana` · `this week/esta semana` · `last month/mes pasado` · `next friday/próximo viernes` · `in 5 days/en 5 días` · `last friday of march` · `YYYY-MM-DD` · `YYYY-M-D` (zero-pad automático) · `YYYY-MM` · `YYYY-Wnn`

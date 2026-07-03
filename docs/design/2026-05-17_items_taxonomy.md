# Taxonomía de items en agenda — diseño rev 2

**Fecha:** 2026-05-17
**Estado:** diseño cerrado, pre-implementación
**Sucede a:** `/Users/hernando/Downloads/propuesta-1-taxonomia-items.md` (propuesta inicial de 5 tipos, superada)

JAngel cerró (2026-05-17, conversación larga iterando sobre la propuesta-1) el modelo conceptual de items en agenda. **Diseño, no implementación. La conversación pasó por seis iteraciones — esta versión es la cerrada definitiva.**

**Revisión 2026-05-17 (segunda sesión, misma fecha):** rename `play` → `ff` (⏩), verbos primarios sustituyen flags, `snooze_count`/`failed_count` entran al MVP, panel del secretary recibe sección "Decidir hoy" sin tocar Prioridad/Agenda/Actividad, `reorganize` se separa en dos modos.

## Principio rector

1. **Cero tipos nuevos**: las 4 citas (task / ms / ev / reminder) y las 4 secciones de `agenda.md` siguen sin tocar.
2. **Cero mutación automática**: secretary NO reescribe `agenda.md`. Sólo señala (❗) las fallidas; el usuario procesa con verbos explícitos.
3. **`task` gana un único campo nuevo, `ff`** (emoji ⏩, "fast-forward"), que controla todo el ciclo pending/someday.

## El campo `ff`

Único pivote. Tres tipos de valor:

| Valor | Significado | Resultado |
|-------|-------------|-----------|
| ausente | comportamiento clásico | `planned` si `date`; "vacío" (default `ff: today`) si no |
| fecha `YYYY-MM-DD` | "vuelve a aparecer en dashboard cuando hoy >= ff" | `pending` |
| `someday` | sin presión, fuera de dashboard | `someday` |

**Invariante (validada por `doctor`):** `ff <= date` (warning en igualdad).

**Si `ff: someday`** → `date`, `time`, `ring`, `recur` pierden sentido (no se aplican).

**Insight clave que motivó el diseño** (cita JAngel):
> "Sería como tener un ring con [date][time] de una tarea pero cuando la tarea no tiene [date][time]"

Pending dispara por **interacción** (secretary al arrancar shell), reminder dispara por **tiempo** (ring macOS). Misma idea (sistema te empuja a atender), distinto disparador.

**Nombre: por qué `ff` y no `next` ni `play`.** `play` describe el *efecto* (entra al dashboard), no el contenido. `next` colisiona con "next action" de GTD (que significa otra cosa). `ff` (fast-forward, ⏩) describe el *gesto* del usuario (avanza esta tarea hasta esta fecha) y a la vez el valor del campo (destino del salto). 2 chars en frontmatter, inequívoco. Decidido 2026-05-17.

## Verbos CLI (primarios, sin flags `--pending`/`--someday`/`--play`)

Cinco verbos que mapean 1-a-1 con los gestos del usuario. El segundo argumento es posicional y manda al campo:

```
task add proj "X"                   → captura cruda → pending con ff: today
task add proj "X" --date YYYY-MM-DD → planned (backwards compat)
task plan    X <date> [<time>]      → fechar (promueve a planned, limpia ff)
task pending X [<date>|someday]     → sinedie / repensar planning (pending; ff = arg o tomorrow)
task drop    X                      → descartar
task done    X                      → completado
task edit    X ...                  → editar campos arbitrarios (incluido ff)
```

Semántica idempotente:
- `task pending X <date>` sobre una pending **es** "repensar planning" — actualiza `ff` e incrementa `snooze_count`.
- `task pending X` sobre una **planned** la **degrada**: mueve `date` a `ff` (o usa el arg), sigue siendo el mismo task.
- `task plan X <date>` sobre una **pending** la **promueve**: copia `ff` a `date` (o usa el arg), limpia `ff`.
- `task plan X <date>` sobre una **planned vencida** (reschedule) incrementa `failed_count`.

Defaults:
- `task pending X` sin segundo arg → `ff: tomorrow`.
- `task add proj "X"` (captura cruda) → `ff: today`.
- **Default `recur` en pending:** `daily`.

## Modo cognitivo (ortogonal, declarable)

- `--shallow` — 15m por defecto.
- `--deep` — 1h por defecto.
- `--duration Nh|Nm` — opcional, sobreescribe el default cognitivo.

Aplicable a cualquier task (planned, pending, someday). En fase 2 (block scheduling) alimentará la planificación: shallow superponibles hasta 2, deep exclusivas.

## Comportamiento de secretary (viewer puro, sin mutación)

Dashboard en arranque del shell:

```
┌─ Tareas planeadas para hoy
│ tasks planned con date == today

├─ ❗ Sin hacer (acción pendiente)
│ tasks planned con date < today y no done
│ → usuario procesa con: plan / pending / done / drop

├─ ⏩ Decidir hoy (pending)
│ tasks pending con ff <= today
│ ❗ marca ff vencido sin atender
│ ❗❗ marca al 3º snooze consecutivo sin decisión (snooze_count >= 3)

├─ 📅 Eventos / 🏁 Hitos / 💬 Reminders
│ como hoy
```

## Panel del secretary — invariante de preservación

El panel diario (`📊panel/secretary/panel.md`, generado por `views/secretary/panel.py` que delega en `core/panel.py::run_panel(period="today")`) tiene hoy 4 secciones. La revisión inserta UNA sola sección nueva, sin tocar el resto:

```
## Calendario       ← intacta
## Prioridad        ← intacta (proyectos relevantes)
## Agenda           ← intacta (citas de hoy; overdue marcadas con ❗ inline)
## Decidir hoy      ← NUEVA: pendings con ff <= today, orden ff asc
## Actividad        ← intacta (log)
```

Posición: **entre Agenda y Actividad**. Razón: Agenda son compromisos firmes (planned hoy + overdue); Decidir hoy son blandos (pending pidiendo decisión); Actividad es retrospectiva. Lectura natural top-to-bottom: lo que debo hacer → lo que debería considerar → lo que hice.

Contenido de "Decidir hoy":
- Lista de tasks pending con `ff <= today`.
- Orden: ff ascendente (más vencidas primero).
- Marcas: ❗ si `ff < today`; ❗❗ si `snooze_count >= 3`.
- Si vacía: `(nada que decidir hoy)`.

Las secciones Prioridad y Actividad NO se tocan en este cambio.

## Reorganize — dos modos separados (planned vs pending)

`core/reorganize.py` actual procesa overdue + hoy en un solo flujo (`_resolve_period("today")` ya hace ambos). El nuevo modelo lo separa explícitamente:

| Modo | Invocación | Procesa | Verbos del bucle |
|------|------------|---------|------------------|
| Planned (default) | `orbit reorganize` | citas planeadas de hoy + overdue (planned con `date <= today` no done) + ev/ms/reminder | `plan / pending / done / drop / skip` |
| Pending (triage) | `orbit reorganize --triage` (nombre a decidir) | tasks pending con `ff <= today` | `plan <date> / pending <new-date>\|someday / drop / skip` |

Nombre del flag del modo pending: **NO `--pending`** (colisiona con el verbo `task pending`, mismo nombre). Candidatos: `--triage`, `--decide`, `--ff`. Decisión pendiente al implementar.

Cero merge automático: el usuario invoca uno u otro según la fricción que quiere afrontar (planned exige compromiso firme; pending exige decisión).

## Filosofía: task estricto

`task --planned` es compromiso real. Si falla, **NO se arrastra silenciosamente ni se reescribe automáticamente**: queda en `agenda.md` con su fecha pasada, secretary la marca con ❗ visualmente, y la fricción de procesarla explícitamente es lo que entrena la disciplina.

## Decisiones cerradas (recopilación final)

| # | Decisión |
|---|---|
| 1 | Cero tipos nuevos; sólo campo `ff` (⏩) en task |
| 2 | `ff` valores: `someday` / fecha / ausente |
| 3 | Política: ff manda si está; invariante `ff <= date` (warning en igualdad) |
| 4 | Estado derivado de los campos (no label canónica) |
| 5 | Captura cruda → `ff: today`; verbo `task pending` sin arg → `ff: tomorrow`; `task pending X someday` → `ff: someday` |
| 6 | Default `recur: daily` en pending |
| 7 | Defaults cognitivos: deep 1h, shallow 15m; `--duration` opcional |
| 8 | Planned = `date` obligatoria, `time` opcional |
| 9 | Planned fallida → **NO mutación auto**; secretary marca con ❗; usuario procesa |
| 10 | Pending con ff vencido → mismo trato |
| 11 | Recurrentes: ocurrencia falla, serie avanza, sin entrar al ciclo |
| 12 | Reminder se reinterpreta semánticamente como ambient/invitación; cero cambio de código |
| 13 | ev, ms sin tocar |
| 14 | **Verbos primarios `plan / pending / drop / done / edit`** sustituyen flags `--pending/--someday/--play`. Idempotencia en `task pending` cubre "repensar planning" sin verbo extra. |
| 15 | **`snooze_count` y `failed_count` entran al MVP**, no se aparcan a v2. Razón: sin contador, la sección "Decidir hoy" colapsa visualmente (todos los items se ven igual de urgentes) y la confrontación al 3º snooze es imposible. |
| 16 | **Panel del secretary preserva Calendario/Prioridad/Agenda/Actividad** y sólo inserta "Decidir hoy" entre Agenda y Actividad. |
| 17 | **`reorganize` se separa en dos modos** (planned por defecto vs pending vía flag). No merge automático. |

## Aparcado a fase 2

- **Block scheduling**: deep/shallow + duración alimentarán capacidad del día, blocks, deep exclusivas vs shallow superponibles hasta 2.
- **Meta / cronograma**: aparte. Tensión con cronograma absorbido en agenda como task-compuesta. No se reabrió.

## Pendientes menores de implementación (no afectan modelo)

Estos puntos NO requieren decisiones de diseño conceptual, sólo de implementación:

1. Formato exacto en `.md`: `⏩ 2026-05-24` al final de línea, sintaxis precisa.
2. Limpieza del `--ring` macOS si una planned con ring pasa a "sin hacer" y luego el usuario la baja a pending.
3. Render HTML: cómo se ven pending vs planned vs someday vs ❗ en cloud.
4. Doctor: dónde encaja el check `ff <= date` (sub-modo sintaxis o nuevo "semántica").
5. Nombre del flag de `reorganize` modo pending: `--triage` / `--decide` / `--ff`.
6. Umbrales por defecto de `snooze_count` (sugerencia: ❗❗ a partir de 3) y `failed_count` (a definir tras observar).
7. Semántica de incremento de contadores: dónde y cuándo exactamente (¿`task pending` siempre incrementa, o sólo si la cita ya era pending? ¿`task plan` reset a 0 al promover pending → planned?).

## MVP (v1) y v2 — scope decidido

Tras llegar al modelo, JAngel pidió bajar al mínimo aprovechable para validar en uso real una semana antes de añadir más capas.

**MVP (v1) incluye:**
- Parser/writer del campo `ff` (⏩) en task.
- Campos persistentes `snooze_count` y `failed_count` en task (incrementados por los verbos correspondientes).
- Estados derivados: planned / pending / someday.
- Verbos CLI: `task plan / pending / drop / done / edit` (sin flags `--pending/--someday/--play`).
- Captura cruda: `task add` sin nada → `ff: today`.
- Secretary panel: nueva sección "Decidir hoy" insertada entre Agenda y Actividad; el resto intacto.
- Reorganize: separación en dos modos (planned por defecto vs pending vía flag).
- Doctor: invariante `ff <= date` (warning en igualdad).

**v2 — reabrible tras 1 semana de uso, si hace falta:**
- Confronte automático al N-ésimo snooze (umbral configurable, no sólo señal visual).
- Comando de migración (decidido: para 15 tasks, mejor a mano).
- Block scheduling (deep/shallow + duration → capacidad de día).
- Tracking opt-in de recurrentes perdidas.

## Orden de implementación sugerido

1. Decidir formato exacto en línea (`⏩ 2026-05-24` / `⏩ someday` al final). Pruebas de parser.
2. Implementar parser/writer en `core/agenda/io.py` (campo `ff`, `snooze_count`, `failed_count`).
3. Doctor: añadir check de invariante `ff <= date`.
4. CLI: refactor de verbos. `task plan` (date posicional), `task pending` (idempotente, segundo arg posicional date|someday), incremento de contadores en los verbos. `task edit` admite campo `ff`.
5. Secretary: añadir sección "Decidir hoy" en `views/secretary/panel.py` (vía `core/panel.py::run_panel`) entre Agenda y Actividad.
6. Reorganize: separar en dos modos.
7. Tests.
8. Migrar las 15 tasks a mano en los proyectos reales (ver sección siguiente).
9. Probar una semana. Anotar qué se echa en falta.

## Migración manual (estado pre-implementación, 2026-05-17)

JAngel estimó ~15 tasks pending en proyectos activos — manejable a mano, sin necesitar comando de migración.

**Reglas decididas:**
- Tasks **sin date/time** (pre-existentes) → migrar a `⏩ someday` ANTES de actualizar código (si no, el default `ff: today` causa aluvión).
- Tasks **con date y/o time** → dejar como planned, sin campo `ff`. Cero cambio.
- Tasks **pasadas no done** → caso-a-caso al revisar; sugerencia: `someday` por defecto, no `today` (evita aluvión inicial).
- **Recurrentes**: cero migración (siguen con `advance_overdue_recurring` existente).
- **Reminders / ev / ms**: cero migración.

## Casos de uso validadores del modelo

JAngel identificó casos reales que el modelo cubre limpiamente sin extras:

1. **"Quiero hacerlo pero no es compromiso"** (motivación original): `task add proj "X"` (captura → pending con ff: today), aparece cuando toca según `recur`, decides.
2. **"Decide qué hacer esta semana con X"**: `task add proj "X" --recur weekly` (default daily).
3. **"Cuando vuelva del congreso hablar con Y"**: `task add proj "Y"` + `task pending Y <fecha-vuelta>` → `ff: <fecha-vuelta>`.
4. **"Esperar entrega de Z (revisión / paper / etc.)"**: `task pending Z <fecha-prometida+1>` — el día después de la promesa, te aparece; si llegó → `task done Z`; si no → `task pending Z +N` (snooze, incrementa `snooze_count`). **Cubre el caso `reminder` con trigger de la propuesta-1 original sin necesitar campo trigger separado**.
5. **"Preparar charla del viernes con review previo"**: `task plan X viernes 17:00` + `task edit X --ff martes` (combinación planned+ff para review interno).

El modelo absorbe los 5 sin extensiones.

## Encaje con arquitectura orbit

- `core/agenda/io.py`: añadir parsing/escritura del campo `ff`, `snooze_count`, `failed_count`.
- `core/agenda/runners.py` (o `core/agenda_cmds.py`): lógica de los verbos `plan / pending / drop / done / edit` (incremento de contadores incluido).
- `core/hooks_catalog.json`: probable nada nuevo (sin auto-reschedule para no recurrentes).
- `core/reorganize.py`: separar en dos modos (planned por defecto vs pending vía flag).
- `views/doctor/`: nuevo check de invariante `ff <= date`.
- `views/secretary/panel.py` + `core/panel.py`: insertar sección "Decidir hoy" entre Agenda y Actividad; resto intacto.
- CLI (`orbit.py`): verbos `task plan / pending / drop / done / edit` (refactor); flags `--pending/--someday/--play` quedan retirados de la propuesta.
- CHULETA / TUTORIAL / README / CLAUDE.md: documentar el campo `ff` y los nuevos verbos.
- DECISIONS.md: ADR para taxonomía y el principio "secretary señala, no muta".

## Recurrentes — precedente arquitectónico relevante

Orbit YA muta `agenda.md` silenciosamente en `shell_init` para recurrentes vencidas:

- `core/hooks_catalog.json` declara `advance_overdue_recurring` (acción en dos chains).
- `core/agenda/recurrence.py::_advance_to_today_or_future` avanza la fecha de la línea hasta hoy o futuro.

**Comportamiento decidido para recurrentes en el nuevo modelo** (sin cambio respecto a hoy):
- Recurrente con `date < today` y no done → avance silencioso, ocurrencia perdida desaparece, siguiente toma su lugar.
- NO entra al ciclo pending. NO marca ❗. NO requiere procesado manual.
- Asimetría legítima vs no recurrentes: el patrón importa más que la ocurrencia.

**Implicación**: la regla "no mutación auto" se refiere a no recurrentes y/o a `views/`. Core sí puede mutar en chains de arranque — hay precedente.

## Versiones descartadas durante la conversación (cronológicamente)

1. ❌ Crear tipos nuevos `pending` + `nudge` (5 tipos en total).
2. ❌ Intercambiar semánticamente `reminder ↔ nudge`.
3. ❌ Crear sólo `pending` como tipo nuevo manteniendo reminder como está.
4. ❌ Labels `--planned --pending --someday` con estado derivado de date/time (sin campo).
5. ❌ Hook automático en core que muta agenda.md (reschedule_planned_to_pending para no recurrentes).
6. ❌ Campo `play` con emoji ▶️ (descartado: describe efecto, no contenido; metáfora ambigua con "tarea reproducible").
7. ❌ Campo `next` con emoji ⏭️ (descartado: colisión semántica con "next action" de GTD).
8. ❌ Flags `--pending` / `--someday` / `--play` en CLI (sustituidos por verbos primarios `plan / pending / drop / done / edit`).
9. ❌ MVP sin contadores (revertido: `snooze_count` / `failed_count` entran al MVP).
10. ✅ **Esta**: campo único `ff` (⏩) + verbos primarios + contadores en MVP + secretary señala ❗ + usuario procesa explícito + panel preserva secciones existentes + reorganize en dos modos.

Cada iteración cerró un agujero distinto:
- (4) → (5) cerró "qué pasa cuando combinaciones útiles no se pueden expresar" (planned con review interno).
- (5) → (6) NO fue por imposibilidad arquitectónica (orbit ya muta en shell_init vía `advance_overdue_recurring`), sino por **preferencia de UX**: control del usuario sobre fallidas no-recurrentes + fricción educativa de "task estricto". Las recurrentes siguen con mutación auto.
- (6) → (7) → (10): naming pasó por `play` (efecto) → `next` (colisión GTD) → `ff` (gesto fast-forward).
- (8): verbos primarios → CLI más limpio, sin overload de flag-name vs verb-name.
- (9): contadores reincorporados → "Decidir hoy" necesita señalar urgencia para no colapsar visualmente.

Documento fuente: `/Users/hernando/Downloads/propuesta-1-taxonomia-items.md`.

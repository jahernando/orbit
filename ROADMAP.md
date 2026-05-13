# ROADMAP.md — trabajo comprometido pendiente

Este fichero lista trabajo **decidido pero no empezado** o **en pausa
deliberada**. A diferencia de [IDEAS.md](IDEAS.md) (ideas sin decidir),
las entradas aquí ya tienen luz verde para implementarse — solo falta
acometerlas.

Diferencia con [ORBIT_REVISION.md](ORBIT_REVISION.md): ese fichero es la
revisión sistemática del estado actual (housekeeping de la base de
código existente). ROADMAP.md mira hacia adelante: features y revisiones
nuevas pendientes de hacer.

---

## 1. Tests automáticos desde GitHub Actions

**Estado**: discutido en sesión previa, pendiente de empezar.

**Objetivo**: workflow en `.github/workflows/` que ejecute `pytest` en cada
push a `main` y en cada PR. Hoy la suite se ejecuta solo localmente (~3.7s,
1650 pasan, 4 skipped).

**A decidir antes de empezar**:

- ¿Solo `pytest`, o también `ruff`/`black`/`mypy`? Hoy orbit no tiene
  formateador ni type-checker configurados → si añadimos, decidir cuáles.
- ¿Matrix de versiones de Python? El target es 3.9+; testar 3.9, 3.11, 3.13
  parece razonable.
- ¿Tests dependientes de fecha? `tests/test_notes_commit.py` y
  `tests/test_undo.py` fallan por fecha en local (preexistente). En CI esto
  se haría visible cada día — habría que parchearlos primero o excluirlos
  con marcador específico.
- ¿Tests que tocan AppleScript / `osascript`? Saltan en CI Linux por
  ausencia. Marcar con `@pytest.mark.skipif(sys.platform != "darwin", ...)`.
- ¿Self-hosted runner en el Mac o GitHub-hosted ubuntu-latest? Self-hosted
  permite los tests de AppleScript pero añade fricción de mantenimiento.

**Estimación**: 1-2h.

---

## 2. Revisión de "auto-magia"

**Estado**: pendiente. El usuario quiere revisar qué comportamientos
automáticos siguen siendo útiles / sorprendentes / over-engineered.

**Candidatos a revisar** (de [CLAUDE.md](CLAUDE.md) y comportamiento observado):

| Auto-magia | Trigger | ¿Útil? | ¿Predecible? |
|---|---|---|---|
| Auto-render `.ics` tras `commit` | `core/render.py:_emit_ics` | sí | sí |
| Auto-render HTML tras `commit` | `core/render.py:render_changed` | revisar | sí |
| Auto-advance recurrentes vencidas en shell startup | `core/shell.py` startup | sí | sí |
| Auto-advance recurrentes a las 00:00 (detección al volver al prompt) | `core/shell.py` | revisar — ¿sigue funcionando? | medio |
| Cloud sync background tras `commit` | `core/cloudsync.py` | revisar | medio |
| Reconcile gsync por título tras `commit` | `core/gsync.py::reconcile_gsync_renames` | **dormante** desde v0.33 (flag off) | n/a |
| Doctor pre-check en `commit` | `core/commit.py` | sí | sí |
| Tracked files auto-refresh tras `commit` | `core/notes.py` | sí (nuevo en v0.34) | sí |
| Ring startup (programa citas del día en Reminders) | `core/ring.py` | dormante v0.29+ | n/a |
| Gitignore auto-add desde doctor | `core/commit.py` | revisar | medio |

**Preguntas para la sesión**:

- ¿Cuáles son **silenciosas** (cero output) y cuáles **ruidosas** (líneas en
  stdout)? ¿Hay desbalance?
- ¿Cuáles bloquean (sync) y cuáles van en background (daemon thread)?
  ¿Está claro al usuario?
- ¿Hay alguna que ya no aporte (porque su feature está dormante) y deba
  quitarse del path crítico?
- ¿Hay alguna que se "olvida" después de un fallo (failure silenciado)?
- ¿Cómo se prueba cada una en aislamiento?

**Estimación**: 1-2h de auditoría + tiempo variable según hallazgos.

---

## 3. Ring desacoplado (fases B–F)

**Estado**: diseño cerrado, Fase A implementada (mirror `.ics` + `--diff`),
fases B–F bloqueadas en espera de items 1 y 2.

Ver [RING.md](RING.md) para el plan completo: schema `ring.json`, daemon
Python, plist `launchd` con `WatchPaths`, federación, triggers.

**Resumen ejecutivo**:

- Sustituye al backend `reminders_backend: "reminders"` dormante (v0.29).
- Arquitectura declarativa: orbit escribe `ring.json` con 7 días de items
  con `--ring`, daemon Python reconcilia Reminders.app idempotentemente.
- Disparado por `launchd WatchPaths` (cada cambio del JSON) +
  `StartCalendarInterval` 00:00.
- iCloud sync gratis → alarmas llegan al iPhone/iPad sin esfuerzo extra.

**Estimación total**: ~9-10h, repartibles en 2-3 sesiones. Versión al
cerrar: v0.35.0.

---

## Convenciones del fichero

- Cada entrada lleva: **Estado**, **Objetivo**, **A decidir** (si aplica),
  **Estimación**.
- Cuando una entrada se completa, se mueve la nota a la sección
  correspondiente de [CLAUDE.md](CLAUDE.md) ("Estado actual") y se borra
  de aquí.
- Si una entrada se abandona, se mueve a [IDEAS.md](IDEAS.md) con
  comentario explicando por qué no se hizo.

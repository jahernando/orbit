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
push a `main` y en cada PR. Hoy la suite se ejecuta solo localmente (~4s,
1804 pasan, 4 skipped — v0.37).

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

## Convenciones del fichero

- Cada entrada lleva: **Estado**, **Objetivo**, **A decidir** (si aplica),
  **Estimación**.
- Cuando una entrada se completa, se mueve la nota a la sección
  correspondiente de [CLAUDE.md](CLAUDE.md) ("Estado actual") y se borra
  de aquí.
- Si una entrada se abandona, se mueve a [IDEAS.md](IDEAS.md) con
  comentario explicando por qué no se hizo.

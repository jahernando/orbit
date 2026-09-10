"""views/ledger.py — `ledger.md`, la vista derivada del libro de caja.

Lee la verdad (entradas `#gasto`/`#ingreso`/`#arrastre` del logbook) y emite la
tabla con saldo corrido. **Nadie edita este fichero**: es 100 % regenerable, así
que si se rompe basta con volver a generarlo.

Dos particularidades respecto al resto de `views/`:

1. **Emite al directorio del proyecto**, no a `📊panel/`. Es una excepción
   consciente al principio truth-layer/view-layer: el usuario quiere abrir su
   ledger donde tiene los otros cuatro ficheros. Como `📊panel/` es
   transversal y esto es por-proyecto, sacarlo de ahí lo alejaría de su sitio.
2. **Creación perezosa**: solo existe en proyectos con movimientos. Es el
   primer fichero de proyecto opcional, así que nada debe exigir su presencia.
"""

from decimal import Decimal
from pathlib import Path
from typing import List, Optional, Tuple

from core.ledger import (
    CARRY_TAG, EXPENSE_TAG, INCOME_TAG, Movement,
    balance, currency_symbol, format_amount, read_movements,
)

LEDGER_FILE = "ledger.md"

_KIND_LABEL = {EXPENSE_TAG: "Gasto", INCOME_TAG: "Ingreso", CARRY_TAG: "Arrastre"}


def _concept_cell(mov: Movement) -> str:
    """Concepto, enlazado al justificante si lo hay."""
    text = mov.concept.replace("|", "\\|")
    return f"[{text}]({mov.link})" if mov.link else text


def _rows(movements: List[Movement]) -> Tuple[List[str], Decimal]:
    """Filas de la tabla con saldo corrido. Devuelve (filas, saldo final)."""
    rows, running = [], Decimal("0.00")
    for mov in movements:
        running += mov.amount
        rows.append("| {} | {} | {} | {} | {} | {} |".format(
            mov.date.isoformat(),
            _KIND_LABEL.get(mov.tag, mov.tag),
            _concept_cell(mov),
            (mov.payee or "—").replace("|", "\\|"),
            format_amount(mov.amount, plus=True),
            format_amount(running),
        ))
    return rows, running


def build_ledger_md(project_dir: Path) -> str:
    """Contenido de `ledger.md` (sin el banner de autogenerado)."""
    from core.ledger import project_partida

    movements, problems = read_movements(project_dir)
    rows, total = _rows(movements)
    symbol = currency_symbol()
    partida = project_partida(project_dir)

    out = [f"# 💶 Ledger — {project_dir.name}", ""]
    if partida:
        out += [f"Partida: **#{partida}**", ""]

    # Corte de `archive` sin arrastre: el saldo NO incluye lo anterior y el
    # fichero tiene que decirlo, porque por sí solo parecería correcto.
    for cut in (m for m in movements if m.is_cut):
        out += [f"> ⚠️ Histórico truncado en {cut.date.isoformat()} sin arrastre "
                f"— el saldo no incluye los movimientos anteriores.", ""]

    if rows:
        out += ["| Fecha | Tipo | Concepto | Beneficiario | Importe | Saldo |",
                "|---|---|---|---|---|---|"] + rows + [""]
    else:
        out += ["*Sin movimientos.*", ""]

    out += [f"**Saldo actual: {format_amount(total)} {symbol}**", ""]

    if problems:
        out += ["## ⚠️ Entradas que no he podido leer", ""]
        out += [f"- {p}" for p in problems]
        out += ["", "Corrígelas en `logbook.md` y vuelve a lanzar `orbit ledger`.", ""]

    return "\n".join(out)


def _unchanged(path: Path, body: str) -> bool:
    """¿El contenido es el mismo salvo el banner (que lleva timestamp)?

    Sin esta comprobación, cada `save` reescribiría el fichero solo por la
    hora y ensuciaría el historial de git con diffs vacíos.
    """
    if not path.exists():
        return False
    previous = path.read_text()
    marker = body.split("\n", 1)[0]        # el H1, primera línea del cuerpo
    return marker in previous and previous.endswith(body)


def write_ledger(project_dir: Path, force: bool = False) -> Optional[Path]:
    """Regenera `ledger.md`. Devuelve la ruta escrita, o None si no tocaba.

    Creación perezosa: sin movimientos y sin fichero previo, no se crea nada.
    Si el fichero existe pero ya no hay movimientos, se reescribe vacío en vez
    de borrarlo — un derivado se regenera, no se elimina a espaldas del usuario.
    """
    from views import autogen_banner

    movements, _ = read_movements(project_dir)
    path = project_dir / LEDGER_FILE
    if not movements and not path.exists():
        return None

    body = build_ledger_md(project_dir)
    if not force and _unchanged(path, body):
        return None
    path.write_text(autogen_banner("ledger") + body)
    return path


def refresh_all() -> int:
    """Regenera el ledger de todos los proyectos que lo tengan. Devuelve cuántos."""
    from core.config import iter_project_dirs

    return sum(1 for d in iter_project_dirs() if write_ledger(d))


def _action_ledger_refresh(ctx):
    """Hook `commit_post`: regenera los ledgers antes de publicar.

    Cierra el hueco de la edición externa: un movimiento tecleado a mano en
    Obsidian no pasa por la CLI, así que sin esto `ledger.md` se quedaría
    atrás hasta el siguiente `orbit ledger`.
    """
    try:
        n = refresh_all()
    except Exception as e:                     # un derivado nunca tumba el save
        return {"ok": False, "msg": f"{type(e).__name__}: {e}"}
    return {"ok": True, "msg": f"{n} ledger{'s' if n != 1 else ''}"}


def print_ledger(project_dir: Path, label: Optional[str] = None) -> int:
    """Imprime en terminal la tabla de movimientos y el saldo. No toca el disco.

    Es la mitad legible de `run_ledger`, separada para que `ls ledger` pueda
    leer sin regenerar: un `ls` que escribe ficheros sería una sorpresa.
    """
    from core.ledger import project_partida

    movements, problems = read_movements(project_dir)
    if not movements:
        print(f"[{project_dir.name}] sin movimientos. "
              f"Anota uno con: orbit log {label or project_dir.name} \"<concepto>\" "
              f"--entry gasto --amount N --tag <partida>")
        return 0

    rows, total = _rows(movements)
    partida = project_partida(project_dir)
    symbol = currency_symbol()

    print(f"💶 Ledger — {project_dir.name}"
          + (f" · partida #{partida}" if partida else ""))
    for cut in (m for m in movements if m.is_cut):
        print(f"  ⚠️  Histórico truncado en {cut.date.isoformat()} sin arrastre: "
              f"el saldo no incluye lo anterior")
    for mov in movements:
        print(f"  {mov.date.isoformat()}  {_KIND_LABEL.get(mov.tag, mov.tag):<8} "
              f"{format_amount(mov.amount, plus=True):>12}  {mov.concept}"
              + (f" · {mov.payee}" if mov.payee else ""))
    print(f"  {'─' * 46}")
    print(f"  Saldo actual: {format_amount(total)} {symbol} "
          f"({len(movements)} movimiento{'s' if len(movements) != 1 else ''})")
    for problem in problems:
        print(f"  ⚠️  {problem}")
    return 0


def run_ledger(project: str) -> int:
    """`orbit ledger <proyecto>` — regenera `ledger.md` e imprime tabla + saldo."""
    from core.log import find_project

    project_dir = find_project(project)
    if not project_dir:
        return 1

    if read_movements(project_dir)[0]:
        write_ledger(project_dir, force=True)
    return print_ledger(project_dir, label=project)


def run_ls_ledger(project: Optional[str] = None) -> int:
    """`orbit ls ledger [P]` — lectura pura del libro de caja.

    Sin proyecto recorre el workspace, como el resto de la familia `ls`, y
    salta los proyectos sin movimientos: el ledger es un fichero opcional.
    """
    from core.ls import collect_project_dirs

    if project:
        dirs = collect_project_dirs(project)
        if not dirs:
            return 1
        return print_ledger(dirs[0], label=project)

    shown = 0
    for project_dir in collect_project_dirs():
        if not read_movements(project_dir)[0]:
            continue
        if shown:
            print()
        print_ledger(project_dir)
        shown += 1
    if not shown:
        print("No hay movimientos.")
    return 0

"""views/ledger.py — `ledger.md`, la vista derivada del libro de caja.

Lee la verdad (las entradas del ledger en el logbook) y emite un resumen
(dotación · gastado · comprometido · disponible) y **una fila por operación**:
un pedido con sus facturas, o un gasto directo (ADR-053). **Nadie edita este
fichero**: es 100 % regenerable, así que si se rompe basta con volver a
generarlo.

Dos particularidades respecto al resto de `views/`:

1. **Emite al directorio del proyecto**, no a `📊panel/`. Es una excepción
   consciente al principio truth-layer/view-layer: el usuario quiere abrir su
   ledger donde tiene los otros cuatro ficheros. Como `📊panel/` es
   transversal y esto es por-proyecto, sacarlo de ahí lo alejaría de su sitio.
2. **Creación perezosa**: solo existe en proyectos con movimientos. Es el
   primer fichero de proyecto opcional, así que nada debe exigir su presencia.
"""

from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import List, Optional, Tuple

from core.ledger import (
    CARRY_TAG, DIRECT, INCOME_TAG, Movement, Operation, Summary,
    build_operations, currency_symbol, format_amount,
    read_movements, summarize,
)

LEDGER_FILE = "ledger.md"
LEDGER_JSON = "ledger.json"

#: Versión del formato de `ledger.json`. Es el contrato con herramientas de
#: fuera de orbit (la revisión contable frente a la USC): si cambia de forma
#: incompatible, se sube.
JSON_VERSION = 1

_FUNDS_LABEL = {INCOME_TAG: "Ingreso", CARRY_TAG: "Arrastre"}


def _esc(text: Optional[str]) -> str:
    return (text or "—").replace("|", "\\|")


def _link(text: str, url: Optional[str]) -> str:
    text = _esc(text)
    return f"[{text}]({url})" if url else text


def _concept_cell(op: Operation) -> str:
    """Concepto del pedido (o del gasto) con su justificante, y detrás los
    justificantes de las facturas/anulaciones que lo cierran."""
    head, rest = op.entries[0], op.entries[1:]
    cell = _link(op.concept, head.link)
    for m in rest:
        cell += " · " + _link(m.concept, m.link)
    return cell


def _money(value: Decimal) -> str:
    return format_amount(value) if value else "—"


def _state_label(op: Operation) -> str:
    return "gasto directo" if op.state == DIRECT else op.state


def _summary_rows(s: Summary, symbol: str) -> List[Tuple[str, str]]:
    rows = []
    if s.carried:
        rows.append(("Saldo arrastrado", format_amount(s.carried)))
    rows += [
        ("Dotación", format_amount(s.income)),
        ("Gastado", format_amount(s.spent)),
        ("Comprometido (pedidos abiertos)", format_amount(s.committed)),
        ("Disponible", format_amount(s.available)),
    ]
    return rows


def usc_cell(op: Operation, status) -> str:
    """Celda USC de una operación: `ok CM26…`, `!↓`, `!`."""
    mark, ids = status.for_operation(op)
    return f"{mark} {ids}".strip() or "—"


def usc_extra_rows(status):
    """Lo que está en la USC y no aquí (`!↑`), como filas de operación y de
    dotación: `(fecha, aut, factura, concepto, tercero, comprometido,
    gastado)` y `(fecha, concepto, importe)`."""
    from views.ledger_reconcile import Aut, Mod, Obl, ONLY_USC
    ops, funds = [], []
    for item in status.only_usc:
        if isinstance(item, Aut):
            ops.append((item.date, item.id, None, "(solo en la USC)",
                        item.payee, item.amount, None))
        elif isinstance(item, Obl):
            ops.append((item.date, item.aut_id, item.invoice,
                        item.concept or "(solo en la USC)", item.payee,
                        None, item.amount))
        elif isinstance(item, Mod):
            funds.append((item.date, item.concept, item.amount))
    key = lambda r: r[0] or date.min
    return sorted(ops, key=key), sorted(funds, key=key), ONLY_USC


def load_usc(project_dir: Path, movements):
    """Estado de la última conciliación (o None). Nunca tumba la vista."""
    try:
        from views.ledger_reconcile import usc_status
        return usc_status(project_dir, movements)
    except Exception as exc:                       # un derivado no se cae
        from views.ledger_reconcile import UscStatus
        return UscStatus(as_of=None, error=str(exc))


def build_ledger_md(project_dir: Path) -> str:
    """Contenido de `ledger.md` (sin el banner de autogenerado)."""
    from core.ledger import project_partida

    movements, problems = read_movements(project_dir)
    operations, op_problems = build_operations(movements)
    problems = problems + op_problems
    summary = summarize(movements, operations)
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

    out += [f"| Resumen | {symbol} |", "|---|---:|"]
    for label, value in _summary_rows(summary, symbol):
        if label == "Disponible":
            label, value = f"**{label}**", f"**{value}**"
        out.append(f"| {label} | {value} |")
    out.append("")

    status = load_usc(project_dir, movements)
    usc = status is not None and status.error is None
    if status is not None and status.error:
        out += [f"> ⚠️ Columna USC no disponible: {status.error}", ""]
    elif usc:
        when = status.as_of.isoformat() if status.as_of else "—"
        out += [f"Conciliado con la USC el {when}. Columna USC: `ok` casa "
                f"(con el nº de la USC) · `!↑` está en la USC y no aquí · "
                f"`!↓` está aquí y no en la USC · `!` no encaja.", ""]
    extra_ops, extra_funds, only_mark = (usc_extra_rows(status) if usc
                                         else ([], [], ""))

    out += ["## Operaciones", ""]
    if operations or extra_ops:
        head = ("| Fecha | Aut. | Factura | Concepto | Beneficiario | "
                "Comprometido | Gastado | Estado |")
        sep = "|---|---|---|---|---|---:|---:|---|"
        if usc:
            head, sep = head + " USC |", sep + "---|"
        out += [head, sep]
        rows = []
        for op in operations:
            cells = [op.date.isoformat(), _esc(op.op_id),
                     _esc(", ".join(op.invoice_ids) or None), _concept_cell(op),
                     _esc(op.payee), _money(op.committed), _money(op.spent),
                     _state_label(op)]
            if usc:
                cells.append(usc_cell(op, status))
            rows.append((op.date, cells))
        for d, aut, inv, concept, payee, committed, spent in extra_ops:
            rows.append((d or date.min, [
                d.isoformat() if d else "—", _esc(aut), _esc(inv),
                _esc(concept), _esc(payee),
                _money(committed or Decimal("0")), _money(spent or Decimal("0")),
                "—", only_mark]))
        rows.sort(key=lambda r: r[0])
        out += ["| " + " | ".join(cells) + " |" for _d, cells in rows]
        out.append("")
    else:
        out += ["*Sin operaciones.*", ""]

    funds = [m for m in movements if m.tag in _FUNDS_LABEL and not m.is_cut]
    if funds or extra_funds:
        head = "| Fecha | Tipo | Concepto | Origen | Importe |"
        sep = "|---|---|---|---|---:|"
        if usc:
            head, sep = head + " USC |", sep + "---|"
        out += ["## Dotación", "", head, sep]
        rows = []
        for m in funds:
            cells = [m.date.isoformat(), _FUNDS_LABEL[m.tag],
                     _link(m.concept, m.link), _esc(m.payee),
                     format_amount(m.amount, plus=True)]
            if usc:
                mark, ids = status.marks.get(m.raw, ("—", ""))
                cells.append(f"{mark} {ids}".strip())
            rows.append((m.date, cells))
        for d, concept, amount in extra_funds:
            rows.append((d or date.min, [d.isoformat() if d else "—", "—",
                                         _esc(concept), "USC",
                                         format_amount(amount, plus=True),
                                         only_mark]))
        rows.sort(key=lambda r: r[0])
        out += ["| " + " | ".join(cells) + " |" for _d, cells in rows]
        out.append("")

    if usc and status.notes:
        out += ["## ⚠️ No encaja con la USC", ""]
        by_raw = {m.raw: m for m in movements}
        for raw, note in status.notes.items():
            m = by_raw.get(raw)
            what = f"{m.date.isoformat()} {m.concept}" if m else raw
            out += [f"- {what}: {note}"]
        out.append("")

    if problems:
        out += ["## ⚠️ Entradas que no he podido leer o no cuadran", ""]
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


def build_ledger_json(project_dir: Path) -> str:
    """Contenido de `ledger.json`: los movimientos en forma legible por máquina.

    Es la interfaz para herramientas de fuera de orbit, que no deben leer el
    markdown. Sin fecha de generación, para que regenerar sin cambios no toque
    el fichero. Importes como texto decimal con signo (`"-1578.64"`), nunca
    float. `justificante` es el enlace tal cual (relativo al proyecto) y
    `justificante_path` la ruta absoluta, si es un fichero local.
    """
    import json
    from core.ledger import ORDER_TAG, project_partida
    from views.ledger_check import _resolve_link

    movements, problems = read_movements(project_dir)
    operations, op_problems = build_operations(movements)
    summary = summarize(movements, operations)
    state_of = {}
    for op in operations:
        for m in op.entries:
            state_of[m.raw] = op.state

    rows = []
    for m in movements:
        path = _resolve_link(project_dir, m.link) if m.link else None
        rows.append({
            "date": m.date.isoformat(),
            "type": m.tag,
            "concept": m.concept,
            "payee": m.payee,
            "amount": str(m.amount),
            "id": m.op_id,
            "order": m.ref,
            "state": state_of.get(m.raw) if m.tag in (ORDER_TAG, "gasto") else None,
            "justificante": m.link,
            "justificante_path": str(path.resolve()) if path is not None else None,
        })
    data = {
        "version": JSON_VERSION,
        "project": project_dir.name,
        "partida": project_partida(project_dir),
        "currency": "EUR",
        "summary": {
            "income": str(summary.income + summary.carried),
            "spent": str(summary.spent),
            "committed": str(summary.committed),
            "available": str(summary.available),
        },
        "movements": rows,
        "problems": problems + op_problems,
    }
    return json.dumps(data, ensure_ascii=False, indent=2) + "\n"


def write_ledger(project_dir: Path, force: bool = False) -> Optional[Path]:
    """Regenera `ledger.md` (y `ledger.json`). Devuelve la ruta de `ledger.md`
    si lo escribió, o None si no tocaba.

    Creación perezosa: sin movimientos y sin fichero previo, no se crea nada.
    Si el fichero existe pero ya no hay movimientos, se reescribe vacío en vez
    de borrarlo — un derivado se regenera, no se elimina a espaldas del usuario.
    """
    from views import autogen_banner

    movements, _ = read_movements(project_dir)
    path = project_dir / LEDGER_FILE
    if not movements and not path.exists():
        return None

    data = build_ledger_json(project_dir)
    json_path = project_dir / LEDGER_JSON
    if force or not json_path.exists() or json_path.read_text() != data:
        json_path.write_text(data)

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

    operations, op_problems = build_operations(movements)
    summary = summarize(movements, operations)
    partida = project_partida(project_dir)
    symbol = currency_symbol()
    status = load_usc(project_dir, movements)
    usc = status is not None and status.error is None

    print(f"💶 Ledger — {project_dir.name}"
          + (f" · partida #{partida}" if partida else ""))
    for cut in (m for m in movements if m.is_cut):
        print(f"  ⚠️  Histórico truncado en {cut.date.isoformat()} sin arrastre: "
              f"el saldo no incluye lo anterior")
    for m in movements:
        if m.tag in _FUNDS_LABEL and not m.is_cut:
            print(f"  {m.date.isoformat()}  {_FUNDS_LABEL[m.tag]:<13} "
                  f"{format_amount(m.amount, plus=True):>12}  {m.concept}"
                  + (f" · {m.payee}" if m.payee else ""))
    for op in operations:
        amount = op.spent if op.state in ("cerrado", DIRECT) else op.committed
        ids = [i for i in [op.op_id] + op.invoice_ids if i]
        ident = f"{' · '.join(ids)} " if ids else ""
        mark = f"  [USC {usc_cell(op, status)}]" if usc else ""
        print(f"  {op.date.isoformat()}  {_state_label(op):<13} "
              f"{format_amount(-amount):>12}  {ident}{op.concept}"
              + (f" · {op.payee}" if op.payee else "") + mark)
    if usc:
        for d, aut, inv, concept, payee, committed, spent in usc_extra_rows(status)[0]:
            print(f"  {d.isoformat() if d else '—':<10}  {'solo en USC':<13} "
                  f"{format_amount(-(committed or spent or 0)):>12}  "
                  f"{aut or inv or ''} {payee or concept}  [USC !↑]")
    print(f"  {'─' * 46}")
    for label, value in _summary_rows(summary, symbol):
        print(f"  {label + ':':<33}{value:>12} {symbol}")
    if status is not None and status.error:
        print(f"  ⚠️  columna USC no disponible: {status.error}")
    elif usc:
        when = status.as_of.isoformat() if status.as_of else "—"
        print(f"  USC: conciliado el {when} "
              f"(ok · !↑ solo en la USC · !↓ solo aquí · ! no encaja)")
    for problem in problems + op_problems:
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

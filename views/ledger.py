"""views/ledger.py — `ledger.md` y `ledger.json`, las vistas derivadas del ledger.

Lee la verdad (las entradas `#ingreso`, `#compromiso`, `#gasto` del logbook) y
emite un resumen (dotación · gastado · comprometido · disponible) y la tabla
de movimientos con **Gastado** y **Disponible** acumulados (ADR-053).
**Nadie edita estos ficheros**: son 100 % regenerables.

Dos particularidades respecto al resto de `views/`:

1. **Emiten al directorio del proyecto**, no a `📊panel/`: el usuario quiere
   su ledger junto a los otros ficheros del proyecto.
2. **Creación perezosa**: solo existen en proyectos con movimientos.
"""

from dataclasses import dataclass
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
#: fuera de orbit (p. ej. la conciliación con la USC): si cambia de forma
#: incompatible, se sube.
JSON_VERSION = 1

_FUNDS_LABEL = {INCOME_TAG: "ingreso", CARRY_TAG: "arrastre"}


def _esc(text: Optional[str]) -> str:
    return (text or "—").replace("|", "\\|")


def _link(text: str, url: Optional[str]) -> str:
    text = _esc(text)
    return f"[{text}]({url})" if url else text


def _concept_cell(op: Operation) -> str:
    """Concepto del compromiso (o del gasto) con su justificante, y detrás
    los justificantes de los gastos que lo consumen."""
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
        ("Comprometido (pendiente)", format_amount(s.committed)),
        ("Disponible", format_amount(s.available)),
    ]
    return rows


def usc_cell(op: Operation) -> str:
    """Referencias externas con que están conciliadas las entradas de la
    operación (marca `☑️`). Sin marca, "—": aún no conciliada."""
    ids = [m.usc for m in op.entries if m.usc]
    return " · ".join(dict.fromkeys(ids)) or "—"


def kind_cell(op: Operation) -> str:
    """Tipo de la operación: el de su primera entrada (el compromiso, si lo hay)."""
    return op.entries[0].label or op.entries[0].tag


@dataclass
class Row:
    """Una fila de la tabla de movimientos, con los acumulados a esa fecha."""
    mov:       Movement
    spent:     Decimal            # gastado acumulado (magnitud)
    available: Decimal            # disponible a esa fecha
    state:     str = ""           # compromiso: abierto / cerrado


def running_rows(movements: List[Movement], operations) -> List[Row]:
    """Recorre los movimientos en orden y lleva Gastado y Disponible.

    Disponible = ingresos − gastado − comprometido pendiente, donde lo
    pendiente de un compromiso es lo aún no gastado contra él mientras siga
    abierto (se cierra al cubrirlo o con `🔒`).
    """
    from core.ledger import ORDER_TAG, EXPENSE_TAG
    state_of = {op.op_id: op.state for op in operations
                if op.op_id and op.entries[0].tag == ORDER_TAG}
    income = spent = Decimal("0.00")
    committed, used, closed = {}, {}, set()
    rows = []
    for m in movements:
        key = m.op_id
        if m.tag == ORDER_TAG:
            committed[key] = abs(m.amount)
            used.setdefault(key, Decimal("0.00"))
            if m.closes:
                closed.add(key)
        elif m.tag == EXPENSE_TAG:
            spent += abs(m.amount)
            if m.ref in committed:
                used[m.ref] += abs(m.amount)
                if m.closes or used[m.ref] >= committed[m.ref]:
                    closed.add(m.ref)
        else:                                   # ingreso / arrastre
            income += m.amount
        pending = sum((max(committed[k] - used[k], Decimal("0.00"))
                       for k in committed if k not in closed), Decimal("0.00"))
        rows.append(Row(m, spent, income - spent - pending,
                        state_of.get(key, "") if m.tag == ORDER_TAG else ""))
    return rows


def _kind_label(m: Movement) -> str:
    return _FUNDS_LABEL.get(m.tag) or m.tag


def _concept_md(m: Movement) -> str:
    cell = _link(m.concept, m.link)
    return cell + (f" (📝 {_esc(m.note)})" if m.note else "")


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

    rows = [r for r in running_rows(movements, operations) if not r.mov.is_cut]
    out += ["## Movimientos", ""]
    if rows:
        out += ["| Fecha | Tipo | Concepto | Beneficiario | Ref. | Compromiso | "
                "Importe | Gastado | Disponible | Estado | Conciliado |",
                "|---|---|---|---|---|---|---:|---:|---:|---|---|"]
        for r in rows:
            m = r.mov
            ref = m.ref + (" 🔒" if m.closes else "") if m.ref else "—"
            out.append("| " + " | ".join([
                m.date.isoformat(), _kind_label(m), _concept_md(m),
                _esc(m.payee), _esc(m.op_id), ref,
                format_amount(m.amount, plus=True), format_amount(r.spent),
                format_amount(r.available), r.state or "—",
                _esc(m.usc)]) + " |")
        n_ok = sum(1 for r in rows if r.mov.usc)
        out += ["", f"Conciliado: la referencia externa con que casa (☑️, la pone "
                f"una herramienta de conciliación); — = aún no. {n_ok} de "
                f"{len(rows)} conciliados.", ""]
    else:
        out += ["*Sin movimientos.*", ""]

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
            "key": m.key,
            "date": m.date.isoformat(),
            "type": m.tag,
            "label": m.label,
            "concept": m.concept,
            "payee": m.payee,
            "amount": str(m.amount),
            "id": m.op_id,
            "order": m.ref,
            "state": state_of.get(m.raw) if m.tag in (ORDER_TAG, "gasto") else None,
            "justificante": m.link,
            "justificante_path": str(path.resolve()) if path is not None else None,
            "closes": m.closes,
            "note": m.note,
            "conciliated": m.usc,
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

    print(f"💶 Ledger — {project_dir.name}"
          + (f" · partida #{partida}" if partida else ""))
    for cut in (m for m in movements if m.is_cut):
        print(f"  ⚠️  Histórico truncado en {cut.date.isoformat()} sin arrastre: "
              f"el saldo no incluye lo anterior")
    for r in running_rows(movements, operations):
        m = r.mov
        if m.is_cut:
            continue
        extra = [x for x in (m.op_id, f"🔗 {m.ref}" if m.ref else None,
                             r.state, f"☑️ {m.usc}" if m.usc else None) if x]
        print(f"  {m.date.isoformat()}  {_kind_label(m):<10} "
              f"{format_amount(m.amount, plus=True):>12}  "
              f"gastado {format_amount(r.spent):>10}  "
              f"disp. {format_amount(r.available):>10}  {m.concept}"
              + (f" · {m.payee}" if m.payee else "")
              + (f"  [{' · '.join(extra)}]" if extra else ""))
    print(f"  {'─' * 46}")
    for label, value in _summary_rows(summary, symbol):
        print(f"  {label + ':':<33}{value:>12} {symbol}")
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


def run_ledger_close(project: str, ref: str) -> int:
    """`orbit ledger <proyecto> --close <ref>`: cierra un compromiso a mano."""
    from core.ledger import close_commitment
    from core.log import find_project

    project_dir = find_project(project)
    if not project_dir:
        return 1
    try:
        m = close_commitment(project_dir, ref)
    except ValueError as exc:
        print(f"⚠️  {exc}")
        return 1
    write_ledger(project_dir, force=True)
    print(f"  🔒 cerrado: {ref} «{m.concept}» · lo no gastado deja de estar comprometido")
    return 0


def run_ledger_mark(project: str, key: str, usc_id) -> int:
    """`orbit ledger <proyecto> --mark <clave> <ref externa>` / `--unmark`.

    Para una herramienta de conciliación (p. ej. usc-ledger): orbit es el único
    que escribe en su logbook, así que la marca se pone por aquí, no editando
    el markdown desde fuera. Regenera `ledger.md` y `ledger.json`.
    """
    from core.ledger import mark_conciliated
    from core.log import find_project

    project_dir = find_project(project)
    if not project_dir:
        return 1
    try:
        before = mark_conciliated(project_dir, key, usc_id)
    except ValueError as exc:
        print(f"⚠️  {exc}")
        return 1
    write_ledger(project_dir, force=True)
    what = f"{before.date.isoformat()} {before.label} «{before.concept}»"
    if usc_id:
        extra = ""
        if before.op_id and before.op_id != usc_id and before.tag == "compromiso":
            extra = f" (🆔 {before.op_id} → {usc_id}, y sus gastos)"
        print(f"  ☑️ conciliado: {what} = {usc_id}{extra}")
    else:
        print(f"  ☑️ sin marca: {what}")
    return 0


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

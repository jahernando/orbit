"""views/ledger_reconcile.py — conciliación con la ejecución oficial de la USC.

`orbit ledger <proyecto> --check <fichero>...` lee lo que da la USC y lo
empareja con el ledger (ADR-053):

* **Ejecución de la partida** (PDF, `Execucion_<partida>.pdf`): el resumen
  (crédito · gastado incl. autorizaciones · disponible), las modificaciones
  (dotaciones) y las autorizaciones pendientes con su tercero.
* **Obrigas** (`obrigasexcel.xls`, que en realidad es una tabla HTML en
  latin-1): una fila por autorización y obligación, con nº de autorización,
  importes, nº de factura, NIF, perceptor y fecha de pago.

Vocabulario: una **autorización** de la USC es nuestro `#pedido` (su número
va en el `🆔`); una **obriga** es nuestro `#gasto` (el nº de factura va en su
`🆔` y la autorización, si la hay, en su `🔗`).

Emparejado **solo por número**: si el número no está en el ledger, no se
adivina (a lo sumo se sugiere). Las dotaciones, que no tienen número, por
importe.

Lo único que escribe: copia los ficheros a `cloud/logs/` con la fecha de la
USC. `ledger.md` saca la **columna USC** de los más recientes que haya allí
(:func:`usc_status`): sin estado guardado aparte.
"""

import re
import subprocess
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from html.parser import HTMLParser
from pathlib import Path
from typing import List, Optional, Tuple

from core.ledger import (
    EXPENSE_TAG, INCOME_TAG, ORDER_TAG, Movement, format_amount, parse_amount,
    read_movements, summarize,
)

_CENT = Decimal("0.01")


# ── Lo que da la USC ─────────────────────────────────────────────────────────

@dataclass
class Aut:
    """Autorización (hoja de pedido tramitada)."""
    id:      str
    date:    Optional[date]
    amount:  Decimal                      # ImpAut
    pending: Optional[Decimal] = None     # Saldo Aut.
    payee:   Optional[str] = None


@dataclass
class Obl:
    """Obligación reconocida (factura, liquidación de dietas…)."""
    aut_id:  Optional[str]
    invoice: Optional[str]                # Nfac
    date:    Optional[date]               # DataFac
    amount:  Decimal                      # ImpOrzamento (o ImpObr)
    payee:   Optional[str] = None
    nif:     Optional[str] = None
    concept: Optional[str] = None
    paid:    Optional[date] = None


@dataclass
class Mod:
    """Modificación presupuestaria (dotación)."""
    date:    Optional[date]
    concept: str
    amount:  Decimal


@dataclass
class UscReport:
    as_of:     Optional[date] = None      # "Datos dispoñibles … en ata"
    partida:   Optional[str] = None
    credit:    Optional[Decimal] = None
    spent:     Optional[Decimal] = None   # gastos incl. saldo de autorizaciones
    available: Optional[Decimal] = None
    auts:      List[Aut] = field(default_factory=list)
    obls:      List[Obl] = field(default_factory=list)
    mods:      List[Mod] = field(default_factory=list)
    sources:   List[str] = field(default_factory=list)
    has_obls:  bool = False               # se leyó una fuente con obligaciones


def _dmy(text: Optional[str]) -> Optional[date]:
    try:
        return datetime.strptime((text or "").strip(), "%d/%m/%Y").date()
    except ValueError:
        return None


def _money(text: Optional[str]) -> Decimal:
    text = (text or "").strip()
    return parse_amount(text, allow_sign=True) if text else Decimal("0.00")


# ── Obrigas (xls = tabla HTML) ───────────────────────────────────────────────

class _Table(HTMLParser):
    def __init__(self):
        super().__init__()
        self.rows: List[List[str]] = []
        self._row = None
        self._cell = None

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self._row = []
        elif tag in ("td", "th") and self._row is not None:
            self._cell = []

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self._cell is not None:
            self._row.append(" ".join("".join(self._cell).split()))
            self._cell = None
        elif tag == "tr" and self._row is not None:
            self.rows.append(self._row)
            self._row = None

    def handle_data(self, data):
        if self._cell is not None:
            self._cell.append(data)


def _decode(raw: bytes) -> str:
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("latin-1")


def parse_obligations(text: str) -> Tuple[List[Aut], List[Obl]]:
    """Filas del excel de obrigas → autorizaciones y obligaciones.

    Se lee por **nombre de columna**, no por posición. Una autorización con
    varias obligaciones sale en varias filas; sin obligaciones, en una fila
    con los campos de la factura vacíos e importes a cero.
    """
    table = _Table()
    table.feed(text)
    return _obligations_from_rows(table.rows)


def partida_of_obligations(text: str) -> Optional[str]:
    m = re.search(r"Partida:\s*([\w.]+)", text)
    return m.group(1) if m else None


def _obligations_from_rows(rows) -> Tuple[List[Aut], List[Obl]]:
    header_idx = next((i for i, r in enumerate(rows)
                       if any(c.lower().startswith("cód.aut") or c == "Nfac"
                              for c in r)), None)
    if header_idx is None:
        raise ValueError("no encuentro la cabecera de columnas (Cód.Aut, Nfac…)")
    header = rows[header_idx]

    def col(row, name):
        for i, h in enumerate(header):
            if h.lower().replace("ó", "o") == name.lower().replace("ó", "o"):
                return row[i] if i < len(row) else ""
        return ""

    auts, obls, seen = [], [], set()
    for row in rows[header_idx + 1:]:
        if not any(row):
            continue
        aut_id = col(row, "Cód.Aut") or None
        if aut_id and aut_id not in seen:
            seen.add(aut_id)
            auts.append(Aut(id=aut_id, date=_dmy(col(row, "DatAut")),
                            amount=_money(col(row, "ImpAut")),
                            pending=_money(col(row, "SaldoAut"))))
        amount = _money(col(row, "ImpOrzamento")) or _money(col(row, "ImpObr"))
        invoice = col(row, "Nfac") or None
        if not invoice and not amount:
            continue                      # autorización sin obligaciones
        obls.append(Obl(aut_id=aut_id, invoice=invoice,
                        date=_dmy(col(row, "DataFac")), amount=abs(amount),
                        payee=col(row, "Perceptor") or None,
                        nif=col(row, "Nif") or None,
                        concept=col(row, "Concepto") or None,
                        paid=_dmy(col(row, "DataPagmto"))))
    return auts, obls


# ── Ejecución (PDF) ──────────────────────────────────────────────────────────

_AMT = r"(-?[\d.]+,\d{2})"
_ASOF_RE = re.compile(r"en ata:\s*(\d{2}/\d{2}/\d{4})")
_PARTIDA_RE = re.compile(r"Partida\s+(\d{4}\.\w+\.\d+)")
_RESUMO_RE = re.compile(r"Credito total:\s*" + _AMT + r".*?Gastos[^:]*:\s*" + _AMT
                        + r".*?Disp\w*:\s*" + _AMT, re.S)
_MOD_RE = re.compile(r"^\s*\d{4}\s+(\d{2}/\d{2}/\d{4})\s+(.+?)\s{2,}" + _AMT
                     + r"\s+" + _AMT + r"\s*$")
_AUT_RE = re.compile(r"^\s*\d{4}\s+(\S+)\s+(\d{2}/\d{2}/\d{4})\s+(.+?)\s{2,}"
                     + _AMT + r"\s+" + _AMT + r"\s+" + _AMT + r"\s*$")


def parse_execution_text(text: str) -> UscReport:
    """Texto de `pdftotext -layout` del PDF de ejecución → `UscReport`.

    Las obligaciones no se leen de aquí (su tabla del PDF no trae el nº de
    autorización): para eso está el excel de obrigas.
    """
    report = UscReport()
    m = _ASOF_RE.search(text)
    report.as_of = _dmy(m.group(1)) if m else None
    m = _PARTIDA_RE.search(text)
    report.partida = m.group(1) if m else None
    m = _RESUMO_RE.search(text)
    if m:
        report.credit, report.spent, report.available = (
            parse_amount(g, allow_sign=True) for g in m.groups())

    section = None
    for line in text.splitlines():
        if "Modificacións Orzamentarias" in line:
            section = "mods"
            continue
        if "Autorizacións" in line:
            section = "auts"
            continue
        if line.strip().startswith("Obrigas"):
            section = None
            continue
        if section == "mods":
            hit = _MOD_RE.match(line)
            if hit:
                pos, neg = (parse_amount(x, allow_sign=True) for x in hit.group(3, 4))
                report.mods.append(Mod(date=_dmy(hit.group(1)),
                                       concept=hit.group(2).strip(),
                                       amount=pos - neg))
        elif section == "auts":
            hit = _AUT_RE.match(line)
            if hit:
                report.auts.append(Aut(
                    id=hit.group(1), date=_dmy(hit.group(2)),
                    payee=hit.group(3).strip(),
                    amount=parse_amount(hit.group(4), allow_sign=True),
                    pending=parse_amount(hit.group(6), allow_sign=True)))
    return report


def _pdf_text(path: Path) -> str:
    try:
        out = subprocess.run(["pdftotext", "-layout", str(path), "-"],
                             capture_output=True, text=True, check=True)
    except FileNotFoundError:
        raise ValueError("falta `pdftotext` (brew install poppler)")
    except subprocess.CalledProcessError as exc:
        raise ValueError(f"no puedo leer {path.name}: {exc.stderr.strip()}")
    return out.stdout


def load_report(paths: List[Path]) -> UscReport:
    """Junta lo que den los ficheros. El excel manda en obligaciones; el PDF
    en resumen, dotaciones y nombre del tercero de cada autorización."""
    report = UscReport()
    for path in paths:
        raw = path.read_bytes()
        if raw[:5] == b"%PDF-":
            part = parse_execution_text(_pdf_text(path))
            report.as_of = part.as_of or report.as_of
            report.partida = part.partida or report.partida
            report.credit = part.credit if part.credit is not None else report.credit
            report.spent = part.spent if part.spent is not None else report.spent
            report.available = (part.available if part.available is not None
                                else report.available)
            report.mods += part.mods
            _merge_auts(report.auts, part.auts)
        else:
            text = _decode(raw)
            auts, obls = parse_obligations(text)
            report.partida = report.partida or partida_of_obligations(text)
            _merge_auts(report.auts, auts)
            report.obls += obls
            report.has_obls = True
        report.sources.append(path.name)
    return report


def _merge_auts(into: List[Aut], new: List[Aut]) -> None:
    by_id = {a.id: a for a in into}
    for a in new:
        known = by_id.get(a.id)
        if known is None:
            into.append(a)
            by_id[a.id] = a
            continue
        known.payee = known.payee or a.payee
        known.date = known.date or a.date
        if known.pending is None:
            known.pending = a.pending


# ── Emparejado (solo por número) ─────────────────────────────────────────────

OK, ONLY_USC, ONLY_HERE, PROBLEM = "ok", "!↑", "!↓", "!"
_SEVERITY = {OK: 0, ONLY_HERE: 1, PROBLEM: 2}


@dataclass
class Pair:
    usc:  object                     # Aut | Obl | Mod
    mov:  Movement
    note: Optional[str] = None       # por qué no encaja (→ "!")


@dataclass
class Reconciliation:
    pairs:       List[Pair] = field(default_factory=list)
    only_usc:    List[object] = field(default_factory=list)
    only_ledger: List[Movement] = field(default_factory=list)


def _by_number(items, movs, key_usc, key_mov, amount_usc) -> Reconciliation:
    rec = Reconciliation()
    left = list(movs)
    for item in items:
        k = key_usc(item)
        mov = next((m for m in left if k and key_mov(m) == k), None)
        if mov is None:
            rec.only_usc.append(item)
            continue
        left.remove(mov)
        note = None
        if abs(amount_usc(item) - abs(mov.amount)) >= _CENT:
            note = (f"importe distinto: USC {format_amount(amount_usc(item))} · "
                    f"ledger {format_amount(abs(mov.amount))}")
        rec.pairs.append(Pair(item, mov, note))
    rec.only_ledger = left
    return rec


def _by_amount(items, movs) -> Reconciliation:
    """Dotaciones: sin número, se emparejan por importe (el más cercano en fecha)."""
    rec = Reconciliation()
    left = list(movs)
    for item in items:
        cands = [m for m in left if abs(item.amount - m.amount) < _CENT]
        if not cands:
            rec.only_usc.append(item)
            continue
        cands.sort(key=lambda m: abs((m.date - (item.date or m.date)).days))
        left.remove(cands[0])
        rec.pairs.append(Pair(item, cands[0]))
    rec.only_ledger = left
    return rec


def reconcile(movements: List[Movement], report: UscReport) -> dict:
    """`{"auts": Reconciliation, "obls": …, "mods": …}`."""
    orders = [m for m in movements if m.tag == ORDER_TAG]
    expenses = [m for m in movements if m.tag == EXPENSE_TAG]
    incomes = [m for m in movements if m.tag == INCOME_TAG]
    out = {
        "auts": _by_number(report.auts, orders, lambda a: a.id,
                           lambda m: m.op_id, lambda a: a.amount),
        "mods": _by_amount(report.mods, incomes),
    }
    if report.has_obls:
        out["obls"] = _by_number(report.obls, expenses, lambda o: o.invoice,
                                 lambda m: m.op_id, lambda o: o.amount)
    return out


def hints(result: dict) -> List[str]:
    """Pedidos con id provisional que parecen una autorización de la USC que
    no está en el ledger (mismo importe). Solo se sugiere: no se escribe."""
    rec = result.get("auts")
    if rec is None:
        return []
    out = []
    for m in rec.only_ledger:
        twins = [a for a in rec.only_usc if abs(a.amount - abs(m.amount)) < _CENT]
        for a in twins:
            out.append(f"{m.op_id or '(sin id)'} «{m.concept}» podría ser la "
                       f"autorización {a.id} ({a.payee or 'sin tercero'}): si lo "
                       f"es, pon 🆔 {a.id} en su entrada del logbook")
    return out


# ── Salida en terminal ───────────────────────────────────────────────────────

def _d(x: Optional[date]) -> str:
    return x.isoformat() if x else "—"


def _usc_line(item) -> str:
    if isinstance(item, Aut):
        return (f"aut. {item.id}  {_d(item.date)}  {format_amount(item.amount):>10}"
                f"  {item.payee or ''}")
    if isinstance(item, Obl):
        return (f"factura {item.invoice or '—'}  {_d(item.date)}  "
                f"{format_amount(item.amount):>10}  {item.payee or ''}"
                + (f"  (aut. {item.aut_id})" if item.aut_id else ""))
    return f"{_d(item.date)}  {format_amount(item.amount):>10}  {item.concept}"


def _mov_line(m: Movement) -> str:
    ident = f"{m.op_id}  " if m.op_id else ""
    return (f"{ident}{m.date.isoformat()}  {format_amount(abs(m.amount)):>10}  "
            f"{m.concept}" + (f" · {m.payee}" if m.payee else ""))


def _suggest(project: str, item) -> str:
    """El `orbit log` que crearía la entrada que falta (sin justificante)."""
    if isinstance(item, Aut):
        return (f'log {project} "<concepto>" <folla.pdf> --import --entry pedido '
                f'--amount {format_amount(item.amount)} --id {item.id} '
                f'--date {_d(item.date)}'
                + (f' --payee "{item.payee}"' if item.payee else ""))
    if isinstance(item, Obl):
        return (f'log {project} "{item.concept or "<concepto>"}" <factura.pdf> '
                f'--import --entry gasto --amount {format_amount(item.amount)}'
                + (f" --id {item.invoice}" if item.invoice else "")
                + (f" --pedido {item.aut_id}" if item.aut_id else "")
                + (f" --date {_d(item.date)}" if item.date else "")
                + (f' --payee "{item.payee}"' if item.payee else ""))
    return (f'log {project} "{item.concept}" <justificante.pdf> --import '
            f'--entry ingreso --amount {format_amount(item.amount)} '
            f'--date {_d(item.date)}')


_TITLES = {"auts": "Autorizaciones ↔ #pedido",
           "obls": "Obligaciones ↔ #gasto",
           "mods": "Dotaciones ↔ #ingreso"}


def print_reconciliation(project_dir: Path, label: str, report: UscReport,
                         result: dict, movements: List[Movement]) -> None:
    print(f"💶 Conciliación con la USC — {project_dir.name} "
          f"({', '.join(report.sources)})")

    if report.credit is not None:
        s = summarize(movements)
        rows = [("Crédito", report.credit, s.carried + s.income),
                ("Gastado + comprometido", report.spent, -(s.spent + s.committed)),
                ("Disponible", report.available, s.available)]
        print(f"  {'':<24}{'USC':>12}{'ledger':>12}{'diferencia':>12}")
        for name, usc, ours in rows:
            diff = ours - usc
            print(f"  {name:<24}{format_amount(usc):>12}{format_amount(ours):>12}"
                  f"{('—' if not diff else format_amount(diff, plus=True)):>12}")

    for key in ("mods", "auts", "obls"):
        rec = result.get(key)
        if rec is None:
            continue
        print(f"\n  ── {_TITLES[key]}")
        for p in rec.pairs:
            mark = "!" if p.note else "ok"
            print(f"  {mark:<3}{_usc_line(p.usc)}\n       ↔ {_mov_line(p.mov)}")
            if p.note:
                print(f"       {p.note}")
        for item in rec.only_usc:
            print(f"  !↑ {_usc_line(item)}   (en la USC, no aquí)")
            print(f"       → {_suggest(label, item)}")
        for m in rec.only_ledger:
            print(f"  !↓ {_mov_line(m)}   (aquí, aún no en la USC)")
        if not (rec.pairs or rec.only_usc or rec.only_ledger):
            print("  (nada)")
    for h in hints(result):
        print(f"\n  💡 {h}")
    if not report.has_obls:
        print("\n  (sin el excel de obrigas no comparo facturas)")


# ── Guardar los ficheros ─────────────────────────────────────────────────────

_EXEC_GLOB, _OBL_GLOB = "*_Execucion_*.pdf", "*_obrigas*.xls"


def _target_name(path: Path, when: date, partida: Optional[str], is_pdf: bool) -> str:
    """`2026-09-29_Execucion_<partida>.pdf` / `2026-09-29_obrigas_<partida>.xls`.

    Se quita el ` (6)` que añade el navegador y no se repite la fecha si el
    nombre ya empieza por una.
    """
    stem = re.sub(r"\s*\(\d+\)$", "", path.stem).strip().replace(" ", "_")
    if not is_pdf and stem.lower().startswith("obrigas"):
        stem = f"obrigas_{partida}" if partida else "obrigas"
    if not re.match(r"^\d{4}-\d{2}-\d{2}_", stem):
        stem = f"{when.isoformat()}_{stem}"
    return stem + path.suffix.lower()


def import_usc_files(project_dir: Path, paths: List[Path],
                     report: UscReport) -> List[str]:
    """Copia los ficheros a `cloud/logs/` con la fecha de la USC. Devuelve
    los nombres con que quedan."""
    import shutil
    when = report.as_of or date.today()
    logs = project_dir / "cloud" / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    names = []
    for path in paths:
        is_pdf = path.read_bytes()[:5] == b"%PDF-"
        name = _target_name(path, when, report.partida, is_pdf)
        target = logs / name
        if path.resolve() != target.resolve():
            shutil.copy2(path, target)
        names.append(name)
    return names


def latest_usc_files(project_dir: Path) -> List[Path]:
    """El PDF de ejecución y el excel de obrigas más recientes de `cloud/logs/`
    (por la fecha del nombre)."""
    logs = project_dir / "cloud" / "logs"
    if not logs.is_dir():
        return []
    out = []
    for pattern in (_EXEC_GLOB, _OBL_GLOB):
        found = sorted(logs.glob(pattern))
        if found:
            out.append(found[-1])
    return out


# ── Estado para la columna USC de ledger.md ─────────────────────────────────

@dataclass
class UscStatus:
    """Lo que la vista necesita: marca por movimiento y lo que falta aquí."""
    as_of:    Optional[date]
    marks:    dict = field(default_factory=dict)      # raw → (marca, nº USC)
    only_usc: List[object] = field(default_factory=list)
    notes:    dict = field(default_factory=dict)      # raw → texto
    error:    Optional[str] = None

    def for_operation(self, op) -> Tuple[str, str]:
        """Peor marca de las entradas de la operación y los nº de la USC."""
        marks = [self.marks[m.raw] for m in op.entries if m.raw in self.marks]
        if not marks:
            return "", ""
        worst = max(marks, key=lambda x: _SEVERITY[x[0]])[0]
        ids = " · ".join(dict.fromkeys(i for _mk, i in marks if i))
        return worst, ids


def status_from(movements: List[Movement], report: UscReport,
                result: Optional[dict] = None) -> UscStatus:
    result = result or reconcile(movements, report)
    st = UscStatus(as_of=report.as_of)
    for key, rec in result.items():
        for p in rec.pairs:
            usc_id = (p.usc.id if key == "auts" else
                      p.usc.invoice if key == "obls" else "")
            st.marks[p.mov.raw] = (PROBLEM if p.note else OK, usc_id or "")
            if p.note:
                st.notes[p.mov.raw] = p.note
        for m in rec.only_ledger:
            st.marks[m.raw] = (ONLY_HERE, "")
        st.only_usc += rec.only_usc
    return st


def usc_status(project_dir: Path, movements: List[Movement]) -> Optional[UscStatus]:
    """Estado frente a los ficheros de la USC más recientes de `cloud/logs/`,
    o None si no hay ninguno. Si no se pueden leer, lo dice en `error`."""
    paths = latest_usc_files(project_dir)
    if not paths:
        return None
    try:
        report = load_report(paths)
    except (ValueError, OSError) as exc:
        return UscStatus(as_of=None, error=str(exc))
    if report.as_of is None:
        from views.ledger_check import _date_of_file
        report.as_of = _date_of_file(paths[0].name)
    return status_from(movements, report)


# ── `ledger --check <ficheros>` ──────────────────────────────────────────────

def run_reconcile(project_dir: Path, label: str, files: List[str]) -> Optional[dict]:
    """Guarda los ficheros, concilia e imprime. None si no se pudieron leer."""
    paths = [Path(f).expanduser() for f in files]
    missing = [p for p in paths if not p.exists()]
    if missing:
        print(f"⚠️  No existe: {', '.join(str(p) for p in missing)}")
        return None
    try:
        report = load_report(paths)
    except ValueError as exc:
        print(f"⚠️  {exc}")
        return None
    names = import_usc_files(project_dir, paths, report)
    print(f"  📥 guardados en cloud/logs/: {', '.join(names)}")

    movements, _ = read_movements(project_dir)
    result = reconcile(movements, report)
    print()
    print_reconciliation(project_dir, label, report, result, movements)
    return result

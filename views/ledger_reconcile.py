"""views/ledger_reconcile.py — conciliación con la ejecución oficial de la USC.

`orbit ledger <proyecto> --reconcile <fichero>...` lee lo que da la USC y lo
empareja, línea a línea, con el ledger (ADR-053):

* **Ejecución de la partida** (PDF, `Execucion_<partida>.pdf`): el resumen
  (crédito · gastado incl. autorizaciones · disponible), las modificaciones
  (dotaciones) y las autorizaciones pendientes con su tercero.
* **Obrigas** (`obrigasexcel.xls`, que en realidad es una tabla HTML en
  latin-1): una fila por autorización y obligación, con nº de autorización,
  importes, nº de factura, NIF, perceptor y fecha de pago.

Vocabulario: una **autorización** de la USC es nuestro `#pedido` (su número
va en el `🆔`); una **obriga** es nuestro `#gasto` (el nº de factura va en su
`🆔` y la autorización, si la hay, en su `🔗`).

Emparejado: primero por número (seguro); lo que no casa, por importe + fecha
cercana + tercero (probable). Esto solo **lee**; lo único que escribe, y solo
si se confirma una a una, es el número oficial en las coincidencias probables
(:func:`core.ledger.rewrite_ids`).
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

#: Días de margen entre la fecha del ledger y la de la USC en un emparejado
#: probable: la USC fecha la autorización cuando la tramita, no cuando se firma.
DATE_WINDOW = 30

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
    header_idx = next((i for i, r in enumerate(table.rows)
                       if any(c.lower().startswith("cód.aut") or c == "Nfac"
                              for c in r)), None)
    if header_idx is None:
        raise ValueError("no encuentro la cabecera de columnas (Cód.Aut, Nfac…)")
    header = table.rows[header_idx]

    def col(row, name):
        for i, h in enumerate(header):
            if h.lower().replace("ó", "o") == name.lower().replace("ó", "o"):
                return row[i] if i < len(row) else ""
        return ""

    auts, obls, seen = [], [], set()
    for row in table.rows[header_idx + 1:]:
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
            report.credit = part.credit if part.credit is not None else report.credit
            report.spent = part.spent if part.spent is not None else report.spent
            report.available = (part.available if part.available is not None
                                else report.available)
            report.mods += part.mods
            _merge_auts(report.auts, part.auts)
        else:
            auts, obls = parse_obligations(_decode(raw))
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


# ── Emparejado ───────────────────────────────────────────────────────────────

SURE, PROBABLE = "seguro", "probable"


@dataclass
class Pair:
    usc:   object                    # Aut | Obl | Mod
    mov:   Movement
    how:   str                       # SURE | PROBABLE
    notes: List[str] = field(default_factory=list)


@dataclass
class Reconciliation:
    pairs:       List[Pair] = field(default_factory=list)
    only_usc:    List[object] = field(default_factory=list)
    only_ledger: List[Movement] = field(default_factory=list)


def _payee_ok(a: Optional[str], b: Optional[str]) -> bool:
    from views.ledger_check import _words
    if not a or not b:
        return True
    return bool(_words(a) & _words(b))


def _close(a: Optional[date], b: Optional[date]) -> bool:
    return a is None or b is None or abs((a - b).days) <= DATE_WINDOW


def _match(items, movs, key_usc, key_mov, amount_usc, amount_mov,
           date_usc, payee_usc) -> Reconciliation:
    rec = Reconciliation()
    left = list(movs)
    pending = []
    for item in items:                                  # 1) por número
        k = key_usc(item)
        mov = next((m for m in left if k and key_mov(m) == k), None)
        if mov is None:
            pending.append(item)
            continue
        left.remove(mov)
        pair = Pair(item, mov, SURE)
        if abs(amount_usc(item) - amount_mov(mov)) >= _CENT:
            pair.notes.append(f"importe distinto: USC {format_amount(amount_usc(item))}"
                              f" · ledger {format_amount(amount_mov(mov))}")
        rec.pairs.append(pair)
    for item in pending:                                # 2) por importe/fecha/tercero
        cands = [m for m in left
                 if abs(amount_usc(item) - amount_mov(m)) < _CENT
                 and _close(date_usc(item), m.date)
                 and _payee_ok(payee_usc(item), m.payee)]
        if len(cands) >= 1:
            cands.sort(key=lambda m: abs((m.date - (date_usc(item) or m.date)).days))
            left.remove(cands[0])
            rec.pairs.append(Pair(item, cands[0], PROBABLE))
        else:
            rec.only_usc.append(item)
    rec.only_ledger = left
    return rec


def reconcile(movements: List[Movement], report: UscReport) -> dict:
    """`{"auts": Reconciliation, "obls": …, "mods": …}`."""
    orders = [m for m in movements if m.tag == ORDER_TAG]
    expenses = [m for m in movements if m.tag == EXPENSE_TAG]
    incomes = [m for m in movements if m.tag == INCOME_TAG]
    out = {
        "auts": _match(report.auts, orders,
                       key_usc=lambda a: a.id, key_mov=lambda m: m.op_id,
                       amount_usc=lambda a: a.amount,
                       amount_mov=lambda m: abs(m.amount),
                       date_usc=lambda a: a.date, payee_usc=lambda a: a.payee),
        "mods": _match(report.mods, incomes,
                       key_usc=lambda x: None, key_mov=lambda m: None,
                       amount_usc=lambda x: x.amount,
                       amount_mov=lambda m: m.amount,
                       date_usc=lambda x: x.date, payee_usc=lambda x: None),
    }
    if report.has_obls:
        out["obls"] = _match(report.obls, expenses,
                             key_usc=lambda o: o.invoice,
                             key_mov=lambda m: m.op_id,
                             amount_usc=lambda o: o.amount,
                             amount_mov=lambda m: abs(m.amount),
                             date_usc=lambda o: o.date,
                             payee_usc=lambda o: o.payee)
    return out


# ── Salida ───────────────────────────────────────────────────────────────────

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
_ONLY_LEDGER = {"auts": "la USC aún no la ha tramitado",
                "obls": "la USC aún no la ha reconocido",
                "mods": "la USC no la registra"}


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
            mark = "✓" if p.how == SURE else "≈"
            why = "importe y fecha" if key == "mods" else "importe, fecha y tercero"
            print(f"  {mark} {_usc_line(p.usc)}\n      ↔ {_mov_line(p.mov)}"
                  + ("" if p.how == SURE else f"   (probable: {why})"))
            for note in p.notes:
                print(f"      ⚠️  {note}")
        for item in rec.only_usc:
            print(f"  ＋ solo en la USC: {_usc_line(item)}")
            print(f"      → {_suggest(label, item)}")
        for m in rec.only_ledger:
            print(f"  ・ solo en el ledger: {_mov_line(m)}  ({_ONLY_LEDGER[key]})")
        if not (rec.pairs or rec.only_usc or rec.only_ledger):
            print("  (nada)")
    if not report.has_obls:
        print("\n  (sin el excel de obrigas no comparo facturas: pásamelo también)")


def _apply(project_dir: Path, result: dict) -> int:
    """Ofrece escribir el número oficial en cada coincidencia probable."""
    import sys
    from core.ledger import rewrite_ids

    probables = [(k, p) for k in ("auts", "obls") if k in result
                 for p in result[k].pairs if p.how == PROBABLE]
    offers = [(k, p) for k, p in probables
              if (p.usc.id if k == "auts" else p.usc.invoice)]
    if not offers:
        return 0
    if not sys.stdin.isatty():
        print("\n  (hay coincidencias probables: lánzalo en terminal para "
              "escribir los números oficiales)")
        return 0
    written = 0
    print()
    for k, p in offers:
        new_id = p.usc.id if k == "auts" else p.usc.invoice
        what = "autorización" if k == "auts" else "factura"
        extra = (f" (y los 🔗 {p.mov.op_id} de sus facturas)"
                 if k == "auts" and p.mov.op_id else "")
        try:
            ans = input(f"  ¿Escribir 🆔 {new_id} ({what}) en «{p.mov.concept}»"
                        f"{extra}? [s/N]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if ans in ("s", "si", "sí", "y", "yes"):
            n = rewrite_ids(project_dir, p.mov.raw, new_id)
            print(f"    ✓ {n} entrada{'s' if n != 1 else ''} actualizada"
                  f"{'s' if n != 1 else ''}")
            written += 1
    if written:
        from views.ledger import write_ledger
        write_ledger(project_dir, force=True)
    return written


def run_ledger_reconcile(project: str, files: List[str]) -> int:
    from core.log import find_project

    project_dir = find_project(project)
    if not project_dir:
        return 1
    paths = [Path(f).expanduser() for f in files]
    missing = [p for p in paths if not p.exists()]
    if missing:
        print(f"⚠️  No existe: {', '.join(str(p) for p in missing)}")
        return 1
    try:
        report = load_report(paths)
    except ValueError as exc:
        print(f"⚠️  {exc}")
        return 1
    movements, _ = read_movements(project_dir)
    result = reconcile(movements, report)
    print_reconciliation(project_dir, project, report, result, movements)
    _apply(project_dir, result)
    return 0

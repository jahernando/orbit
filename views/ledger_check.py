"""views/ledger_check.py — comprobación del ledger (ADR-053, F3).

`orbit ledger <proyecto> --check` lee la verdad (el logbook y los ficheros de
`cloud/logs/`) y devuelve hallazgos en tres niveles:

* **error** — el ledger no es fiable tal cual: un justificante que no existe,
  un gasto o pedido sin justificante, un `🔗` roto, un id repetido, una entrada
  ilegible. Bloquean el export (F4) y salen en `orbit doctor`.
* **aviso** — algo que probablemente hay que mirar: pedidos abiertos hace
  mucho, facturas que parecen de un pedido y no están enlazadas, PDFs
  económicos sin movimiento, duplicados, variantes de un beneficiario…
  No bloquean (salvo `--strict`) y **no** van al doctor: cualquier issue del
  doctor hace preguntar al `save`, y estos saldrían en cada save.
* **info** — nombres de fichero raros.

Todo es heurística de lectura: nada aquí escribe. Umbrales y patrones se
configuran en `orbit.json` → `ledger` (ver :data:`DEFAULTS`); los huérfanos
legítimos se ignoran listándolos en `<proyecto>/.ledger-ignore`.
"""

import fnmatch
import json
import re
import unicodedata
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import List, Optional
from urllib.parse import unquote

from core.ledger import (
    CANCEL_TAG, CARRY_TAG, CLOSED, EXPENSE_TAG, INCOME_TAG, OPEN, ORDER_TAG, RECON_TAG,
    Movement, build_operations, format_amount, read_movements, summarize,
)

ERROR, WARNING, INFO = "error", "aviso", "info"
_LEVEL_MARK = {ERROR: "❌", WARNING: "⚠️ ", INFO: "ℹ️ "}

IGNORE_FILE = ".ledger-ignore"

#: Umbrales y patrones por defecto; se sobrescriben en orbit.json → ledger.
#: Los patrones son regex sobre el nombre de fichero normalizado (minúsculas,
#: sin tildes) y cubren gallego, castellano e inglés.
DEFAULTS = {
    "open_days": 60,            # pedido abierto más de N días → aviso
    "diff_pct": 10,             # factura difiere del pedido más de X % → aviso
    "duplicate_days": 7,        # mismo importe y beneficiario a ≤ N días
    "order_patterns": r"folla|pedimento|pedido|purchase.?order",
    "invoice_patterns": r"factura|(?<![a-z])fra(?![a-z])|invoice|recibo|receipt|ticket",
    "expense_patterns": r"dieta|liquidacion|axuda|viaxe|travel.?expense",
}

#: Palabras que no identifican a nadie: no cuentan para emparejar un pedido
#: con una factura por su nombre.
_STOPWORDS = {"factura", "invoice", "folla", "pedimento", "pedido", "fdo",
              "firmado", "asinado", "para", "from", "with", "the", "del",
              "las", "los", "una", "pdf"}


@dataclass(frozen=True)
class Finding:
    level: str
    msg:   str
    where: str = ""             # entrada del logbook o fichero afectado

    def render(self) -> str:
        where = f"\n        │ {self.where}" if self.where else ""
        return f"  {_LEVEL_MARK[self.level]} {self.level}: {self.msg}{where}"


# ── Utilidades ───────────────────────────────────────────────────────────────

def _norm(text: Optional[str]) -> str:
    """Minúsculas, sin tildes, espacios colapsados: para comparar nombres."""
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(c for c in text if not unicodedata.combining(c))
    return " ".join(text.casefold().split())


def _words(text: str) -> set:
    return {w for w in re.split(r"[^a-z0-9]+", _norm(text))
            if len(w) >= 4 and not w.isdigit() and w not in _STOPWORDS}


def load_config(workspace_root: Optional[Path] = None) -> dict:
    if workspace_root is None:
        from core.config import ORBIT_HOME
        workspace_root = ORBIT_HOME
    cfg = dict(DEFAULTS)
    path = workspace_root / "orbit.json"
    if path.exists():
        try:
            section = json.loads(path.read_text()).get("ledger")
            if isinstance(section, dict):
                cfg.update({k: v for k, v in section.items() if k in DEFAULTS})
        except (json.JSONDecodeError, OSError):
            pass
    return cfg


def _resolve_link(project_dir: Path, link: str) -> Optional[Path]:
    """Ruta local de un justificante, o None si es una URL."""
    if re.match(r"^[a-z][a-z0-9+.-]*:", link, re.I):
        return None
    target = unquote(link.split("#", 1)[0])
    if target.startswith(("/", "~")):
        return Path(target).expanduser()
    if target.startswith("./"):
        target = target[2:]
    return project_dir / target


def _logs_dir(project_dir: Path) -> Path:
    return project_dir / "cloud" / "logs"


def _ignored(project_dir: Path) -> List[str]:
    path = project_dir / IGNORE_FILE
    if not path.exists():
        return []
    return [line.strip() for line in path.read_text().splitlines()
            if line.strip() and not line.strip().startswith("#")]


def _is_ignored(name: str, patterns: List[str]) -> bool:
    return any(fnmatch.fnmatch(name, p) for p in patterns)


def _date_of_file(name: str) -> Optional[date]:
    m = re.match(r"^(\d{4}-\d{2}-\d{2})", name)
    if not m:
        return None
    try:
        return date.fromisoformat(m.group(1))
    except ValueError:
        return None


# ── Comprobaciones ───────────────────────────────────────────────────────────

def _check_entries(project_dir: Path, movements: List[Movement],
                   read_problems: List[str], op_problems: List[str],
                   cfg: dict) -> List[Finding]:
    out: List[Finding] = []

    for p in read_problems:
        # El signo contradictorio ya se corrigió al leer: es un aviso.
        level = WARNING if "el signo contradice" in p else ERROR
        out.append(Finding(level, p))
    for p in op_problems:
        level = WARNING if "ya estaba" in p else ERROR
        out.append(Finding(level, p))

    order_re = re.compile(cfg["order_patterns"])
    for m in movements:
        if m.tag in (CANCEL_TAG, RECON_TAG, CARRY_TAG):
            continue
        if not m.link:
            level = WARNING if m.tag == INCOME_TAG else ERROR
            out.append(Finding(level, f"#{m.tag} sin justificante", m.raw))
            continue
        path = _resolve_link(project_dir, m.link)
        if path is not None and not path.exists():
            out.append(Finding(ERROR, f"el justificante no existe: {m.link}", m.raw))
        if m.tag == EXPENSE_TAG and order_re.search(_norm(Path(m.link).name)):
            out.append(Finding(WARNING, "este #gasto enlaza una hoja de pedido: "
                               "¿debería ser #pedido?", m.raw))
    return out


def _check_operations(operations, today: date, cfg: dict) -> List[Finding]:
    out = []
    limit = today - timedelta(days=int(cfg["open_days"]))
    pct = Decimal(str(cfg["diff_pct"]))
    for op in operations:
        if op.state == OPEN and op.date < limit:
            days = (today - op.date).days
            out.append(Finding(WARNING, f"pedido {op.op_id} abierto hace {days} "
                               f"días: {op.concept}", op.entries[0].raw))
        if op.state == CLOSED and op.committed:
            diff = abs(op.spent - op.committed) / op.committed * 100
            if diff > pct:
                out.append(Finding(
                    WARNING, f"pedido {op.op_id}: la factura "
                    f"({format_amount(op.spent)}) difiere un {diff:.0f} % de lo "
                    f"comprometido ({format_amount(op.committed)})",
                    op.entries[0].raw))
    return out


def _check_duplicates(movements: List[Movement], cfg: dict) -> List[Finding]:
    out = []
    window = int(cfg["duplicate_days"])
    money = [m for m in movements
             if m.tag in (EXPENSE_TAG, ORDER_TAG, INCOME_TAG) and m.amount]
    for i, a in enumerate(money):
        for b in money[i + 1:]:
            if (b.date - a.date).days > window:
                break
            if (a.tag == b.tag and a.amount == b.amount
                    and _norm(a.payee) == _norm(b.payee)):
                out.append(Finding(
                    WARNING, f"posible duplicado: {format_amount(a.amount)} "
                    f"{a.date.isoformat()} «{a.concept}» y {b.date.isoformat()} "
                    f"«{b.concept}»", b.raw))
    return out


def _check_invoice_ids(movements: List[Movement]) -> List[Finding]:
    seen = {}
    out = []
    for m in movements:
        if m.tag != EXPENSE_TAG or not m.op_id:
            continue
        if m.op_id in seen:
            out.append(Finding(WARNING, f"la factura {m.op_id} aparece dos veces "
                               f"(también «{seen[m.op_id].concept}»)", m.raw))
        seen.setdefault(m.op_id, m)
    return out


def _check_payees(movements: List[Movement]) -> List[Finding]:
    variants = {}
    for m in movements:
        if m.payee:
            variants.setdefault(_norm(m.payee), set()).add(m.payee)
    return [Finding(WARNING, "beneficiario escrito de varias formas: "
                    + " / ".join(sorted(names)))
            for names in variants.values() if len(names) > 1]


def _check_reconciliation(movements: List[Movement]) -> List[Finding]:
    """La última conciliación frente a lo que dice el ledger en esa fecha.

    No se sabe si el saldo oficial es el de caja o el disponible (depende de
    cómo lo dé contabilidad), así que se avisa solo si no cuadra con ninguno.
    """
    recons = [m for m in movements if m.tag == RECON_TAG]
    if not recons:
        return []
    last = recons[-1]
    upto = [m for m in movements if m.date <= last.date]
    s = summarize(upto)
    if last.amount in (s.cash, s.available):
        return []
    return [Finding(WARNING, f"la conciliación del {last.date.isoformat()} "
                    f"({format_amount(last.amount)}) no cuadra: el ledger da "
                    f"{format_amount(s.cash)} de caja y "
                    f"{format_amount(s.available)} disponible", last.raw)]


def _check_files(project_dir: Path, movements: List[Movement], operations,
                 cfg: dict) -> List[Finding]:
    """Huérfanos, facturas candidatas y nombres raros en `cloud/logs/`."""
    logs = _logs_dir(project_dir)
    if not logs.is_dir():
        return []
    linked = set()
    for m in movements:
        path = _resolve_link(project_dir, m.link) if m.link else None
        if path is not None:
            linked.add(path.name)
    ignore = _ignored(project_dir)
    economic = re.compile("|".join(cfg[k] for k in (
        "order_patterns", "invoice_patterns", "expense_patterns")))

    out = []
    opens = [op for op in operations if op.state == OPEN]
    for f in sorted(logs.iterdir()):
        if not f.is_file() or f.name.startswith("."):
            continue
        name = f.name
        if re.match(r"^\d{4}-\d{2}-\d{2}_\d{4}-\d{2}-\d{2}_", name):
            out.append(Finding(INFO, f"fecha duplicada en el nombre: {name}"))
        if re.search(r"\.pdf.+\.pdf$|_\.pdf$", name, re.I):
            out.append(Finding(INFO, f"extensión repetida o rara: {name}"))
        if name in linked or _is_ignored(name, ignore):
            continue
        # Candidata: comparte una palabra con el concepto o el beneficiario de
        # un pedido abierto y no es anterior a él. No se exige que el nombre
        # diga "factura": muchas llegan como `CM26XXXX0001_Axencia Viaxes.pdf`.
        fdate = _date_of_file(name)
        norm = _norm(name)
        own = [op for op in operations
               if op.op_id and len(op.op_id) >= 5 and _norm(op.op_id) in norm]
        if own:
            out.append(Finding(WARNING, f"documento de la autorización "
                               f"{own[0].op_id} sin enlazar: cloud/logs/{name}"))
            continue
        # Una hoja de pedido no es la factura de nadie: si sobra, es un
        # pedido sin anotar (cae abajo como documento sin movimiento).
        is_order = re.search(cfg["order_patterns"], norm)
        candidates = [] if is_order else [
            op for op in opens
            if not (fdate and fdate < op.date - timedelta(days=7))
            and _words(name) & (_words(op.concept) | _words(op.payee or ""))]
        if not candidates and not economic.search(norm):
            continue
        if candidates:
            ids = ", ".join(op.op_id or "?" for op in candidates)
            out.append(Finding(WARNING, f"factura candidata de {ids} sin "
                               f"enlazar: cloud/logs/{name}"))
        else:
            out.append(Finding(WARNING, f"documento económico sin movimiento: "
                               f"cloud/logs/{name} (si no lo es, añádelo a "
                               f"{IGNORE_FILE})"))
    return out


def check_ledger(project_dir: Path, today: Optional[date] = None,
                 cfg: Optional[dict] = None) -> List[Finding]:
    """Todos los hallazgos del ledger de *project_dir*, errores primero."""
    today = today or date.today()
    cfg = cfg or load_config()
    movements, read_problems = read_movements(project_dir)
    if not movements and not read_problems:
        return []
    operations, op_problems = build_operations(movements)
    findings = (
        _check_entries(project_dir, movements, read_problems, op_problems, cfg)
        + _check_operations(operations, today, cfg)
        + _check_duplicates(movements, cfg)
        + _check_invoice_ids(movements)
        + _check_payees(movements)
        + _check_reconciliation(movements)
        + _check_files(project_dir, movements, operations, cfg)
    )
    order = {ERROR: 0, WARNING: 1, INFO: 2}
    return sorted(findings, key=lambda f: order[f.level])


def ledger_errors(project_dir: Path) -> List[Finding]:
    """Solo los errores: lo que ve `orbit doctor` (y lo que bloquea el export)."""
    return [f for f in check_ledger(project_dir) if f.level == ERROR]


def run_ledger_check(project: str, strict: bool = False) -> int:
    """`orbit ledger <proyecto> --check [--strict]`.

    Código de salida 1 si hay errores (o avisos, con `--strict`).
    """
    from core.log import find_project

    project_dir = find_project(project)
    if not project_dir:
        return 1
    findings = check_ledger(project_dir)
    counts = {lvl: sum(1 for f in findings if f.level == lvl)
              for lvl in (ERROR, WARNING, INFO)}
    print(f"💶 Comprobación del ledger — {project_dir.name}")
    if not findings:
        print("  ✓ sin errores ni avisos")
        return 0
    for f in findings:
        print(f.render())
    print(f"  {'─' * 46}")
    print(f"  {counts[ERROR]} error{'es' if counts[ERROR] != 1 else ''} · "
          f"{counts[WARNING]} aviso{'s' if counts[WARNING] != 1 else ''} · "
          f"{counts[INFO]} info")
    if counts[ERROR] or (strict and counts[WARNING]):
        return 1
    return 0

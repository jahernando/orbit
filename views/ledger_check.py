"""views/ledger_check.py — comprobación del ledger (ADR-053).

`orbit ledger <proyecto> --check` lee la verdad (el logbook y los ficheros de
`cloud/logs/`) y devuelve hallazgos en dos niveles:

* **error** — el ledger no es fiable tal cual: un justificante enlazado que no
  existe, un `🔗` a un compromiso que no existe, una referencia repetida, una
  entrada ilegible. Bloquean el export y salen en `orbit doctor`.
* **aviso** — compromisos abiertos hace mucho y documentos económicos de
  `cloud/logs/` sin movimiento. No bloquean (salvo `--strict`) y **no** van al
  doctor: cualquier issue del doctor hace preguntar al `save`.

Con ficheros de la USC (`--check <pdf> <xls>`), además concilia: ver
:mod:`views.ledger_reconcile`.

Umbral y patrones en `orbit.json` → `ledger` (ver :data:`DEFAULTS`); los
documentos legítimos que parecen económicos se ignoran listándolos en
`<proyecto>/.ledger-ignore`.
"""

import fnmatch
import json
import re
import unicodedata
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import List, Optional
from urllib.parse import unquote

from core.ledger import (
    EXPENSE_TAG, OPEN, ORDER_TAG, Movement, build_operations, read_movements,
)

ERROR, WARNING = "error", "aviso"
_LEVEL_MARK = {ERROR: "❌", WARNING: "⚠️ "}

IGNORE_FILE = ".ledger-ignore"

#: Umbral y patrones por defecto; se sobrescriben en orbit.json → ledger. El
#: patrón es una regex sobre el nombre de fichero normalizado (minúsculas, sin
#: tildes) y cubre gallego, castellano e inglés.
DEFAULTS = {
    "open_days": 60,            # compromiso abierto más de N días → aviso
    "doc_patterns": (r"folla|pedimento|pedido|purchase.?order|factura"
                     r"|(?<![a-z])fra(?![a-z])|invoice|recibo|receipt|ticket"
                     r"|dieta|liquidacion"),
}


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


def _ignored(project_dir: Path) -> List[str]:
    path = project_dir / IGNORE_FILE
    if not path.exists():
        return []
    return [line.strip() for line in path.read_text().splitlines()
            if line.strip() and not line.strip().startswith("#")]


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
                   problems: List[str]) -> List[Finding]:
    out = []
    for p in problems:
        # El signo contradictorio ya se corrigió al leer: es un aviso.
        out.append(Finding(WARNING if "el signo contradice" in p else ERROR, p))

    seen = {}
    for m in movements:
        if m.link:
            path = _resolve_link(project_dir, m.link)
            if path is not None and not path.exists():
                out.append(Finding(ERROR, f"el justificante no existe: {m.link}",
                                   m.raw))
        if m.tag == EXPENSE_TAG and m.op_id:
            if m.op_id in seen:
                out.append(Finding(ERROR, f"la referencia {m.op_id} está en dos gastos "
                                   f"(también «{seen[m.op_id].concept}»)", m.raw))
            seen.setdefault(m.op_id, m)
    return out


def _check_open_orders(operations, today: date, cfg: dict) -> List[Finding]:
    limit = today - timedelta(days=int(cfg["open_days"]))
    return [Finding(WARNING, f"compromiso {op.op_id} abierto hace "
                    f"{(today - op.date).days} días: {op.concept}",
                    op.entries[0].raw)
            for op in operations if op.state == OPEN and op.date < limit]


def _check_orphans(project_dir: Path, movements: List[Movement],
                   cfg: dict) -> List[Finding]:
    """Documentos de aspecto económico en `cloud/logs/` que no enlaza nadie."""
    logs = project_dir / "cloud" / "logs"
    if not logs.is_dir():
        return []
    linked = {p.name for p in (_resolve_link(project_dir, m.link)
                               for m in movements if m.link) if p is not None}
    ignore = _ignored(project_dir)
    economic = re.compile(cfg["doc_patterns"])
    return [Finding(WARNING, f"documento económico sin movimiento: "
                    f"cloud/logs/{f.name} (si no lo es, añádelo a {IGNORE_FILE})")
            for f in sorted(logs.iterdir())
            if f.is_file() and not f.name.startswith(".")
            and f.name not in linked
            and not any(fnmatch.fnmatch(f.name, p) for p in ignore)
            and economic.search(_norm(f.name))]


def _check_book(project_dir: Path, book, today: date, cfg: dict) -> List[Finding]:
    """Hallazgos del libro propio (ADR-054)."""
    from core.ledger_book import LEDGER_LOGS, categories, trail_nums

    out = [Finding(WARNING if "el signo contradice" in p else ERROR, p)
           for p in book.problems]
    if not book.partida:
        out.append(Finding(ERROR, "la cabecera no tiene partida (- 🏷️ Partida: X)"))
    if not (book.valid_from and book.valid_to):
        out.append(Finding(ERROR, "la cabecera no tiene validez "
                                  "(- 📆 Validez: AAAA-MM-DD → AAAA-MM-DD)"))

    seen = set()
    for i, e in enumerate(book.entries, 1):
        if e.num in seen:
            out.append(Finding(ERROR, f"nº {e.num} repetido", f"ledger {e.num}"))
        elif int(e.num) != i:
            out.append(Finding(ERROR, f"numeración no correlativa: se esperaba "
                                      f"{i:04d} y hay {e.num} (los números no se "
                                      f"borran: se anulan)", f"ledger {e.num}"))
        seen.add(e.num)

    cats = categories()
    by_num = {e.num: e for e in book.entries}
    ids = {}
    for e in book.live():
        where = f"ledger {e.num} {e.title}"
        if not e.payee:
            out.append(Finding(ERROR, "sin beneficiario (👤)", where))
        if e.tag != "ingreso" and not e.category:
            out.append(Finding(ERROR, "sin categoría (🗂️)", where))
        elif e.category and e.category not in cats:
            out.append(Finding(ERROR, f"categoría «{e.category}» desconocida "
                                      f"({', '.join(cats)})", where))
        if e.date and not book.in_range(e.date):
            out.append(Finding(ERROR, f"{e.date} fuera de la validez "
                                      f"({book.valid_from} → {book.valid_to})", where))
        if e.link:
            path = _resolve_link(project_dir, e.link)
            if path is not None and not path.exists():
                out.append(Finding(ERROR, f"el justificante no existe: {e.link}", where))
        if e.commit:
            target = by_num.get(e.commit)
            if target is None or target.tag != ORDER_TAG:
                out.append(Finding(ERROR, f"🔗 {e.commit} no es un compromiso", where))
            elif not target.live:
                out.append(Finding(ERROR, f"🔗 {e.commit} está anulado", where))
        if e.op_id and e.tag == EXPENSE_TAG:
            if e.op_id in ids:
                out.append(Finding(ERROR, f"la referencia {e.op_id} está también en "
                                          f"la entrada {ids[e.op_id]}", where))
            ids.setdefault(e.op_id, e.num)

    movements = book.movements()
    operations, op_problems = build_operations(movements)
    out += [Finding(ERROR, p) for p in op_problems]
    out += _check_open_orders(operations, today, cfg)

    logs = project_dir / "cloud" / LEDGER_LOGS
    if logs.is_dir():
        linked = {p.name for p in (_resolve_link(project_dir, e.link)
                                   for e in book.entries if e.link) if p is not None}
        out += [Finding(WARNING, f"justificante sin entrada: cloud/{LEDGER_LOGS}/{f.name}")
                for f in sorted(logs.iterdir())
                if f.is_file() and not f.name.startswith(".") and f.name not in linked]
    out += _check_orphans(project_dir, movements, cfg)

    trails = set(trail_nums(project_dir))
    missing = [e.num for e in book.live() if e.num not in trails]
    if missing:
        out.append(Finding(WARNING, f"sin rastro en el logbook: {', '.join(missing)}"))
    unknown = sorted(n for n in trails if n not in by_num)
    if unknown:
        out.append(Finding(WARNING, f"rastro en el logbook sin entrada en el libro: "
                                    f"{', '.join(unknown)}"))
    return out


def check_ledger(project_dir: Path, today: Optional[date] = None,
                 cfg: Optional[dict] = None) -> List[Finding]:
    """Todos los hallazgos del ledger de *project_dir*, errores primero."""
    from core.ledger_book import read_book

    today = today or date.today()
    cfg = cfg or load_config()
    book = read_book(project_dir)
    if book is not None:
        return sorted(_check_book(project_dir, book, today, cfg),
                      key=lambda f: f.level != ERROR)
    movements, read_problems = read_movements(project_dir)
    if not movements and not read_problems:
        return []
    operations, op_problems = build_operations(movements)
    findings = (_check_entries(project_dir, movements, read_problems + op_problems)
                + _check_open_orders(operations, today, cfg)
                + _check_orphans(project_dir, movements, cfg))
    return sorted(findings, key=lambda f: f.level != ERROR)


def ledger_errors(project_dir: Path) -> List[Finding]:
    """Solo los errores: lo que ve `orbit doctor` (y lo que bloquea el export)."""
    return [f for f in check_ledger(project_dir) if f.level == ERROR]


def run_ledger_check(project: str, strict: bool = False,
                     files: Optional[List[str]] = None) -> int:
    """`orbit ledger <proyecto> --check [ficheros de la USC] [--strict]`.

    Sin ficheros, la comprobación interna. Con ficheros (PDF de ejecución y/o
    excel de obrigas), además concilia con la USC: los guarda en
    `cloud/logs/` y regenera `ledger.md` con la columna USC. Código de salida
    1 si hay errores (o, con `--strict`, avisos o marcas `!` / `!↑`).
    """
    from core.log import find_project

    project_dir = find_project(project)
    if not project_dir:
        return 1
    usc_bad = 0
    if files:
        # Informe provisional en terminal, hasta que exista usc-ledger.
        from views.ledger_reconcile import run_reconcile
        result = run_reconcile(project_dir, project, files)
        if result is None:
            return 1
        usc_bad = sum(len(r.only_usc) + sum(1 for p in r.pairs if p.note)
                      for r in result.values())
        print()
    findings = check_ledger(project_dir)
    n_err = sum(1 for f in findings if f.level == ERROR)
    n_warn = len(findings) - n_err
    print(f"💶 Comprobación del ledger — {project_dir.name}")
    if not findings:
        print("  ✓ sin errores ni avisos")
    else:
        for f in findings:
            print(f.render())
        print(f"  {'─' * 46}")
        print(f"  {n_err} error{'es' if n_err != 1 else ''} · "
              f"{n_warn} aviso{'s' if n_warn != 1 else ''}")
    if n_err or (strict and (n_warn or usc_bad)):
        return 1
    return 0

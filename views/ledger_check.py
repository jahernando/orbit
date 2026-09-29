"""views/ledger_check.py — comprobación del ledger (ADR-053).

`orbit ledger <proyecto> --check` lee la verdad (el logbook y los ficheros de
`cloud/logs/`) y devuelve hallazgos en dos niveles:

* **error** — el ledger no es fiable tal cual: un `#pedido` o `#gasto` sin
  justificante o con un justificante que no existe, un `🔗` a un pedido que no
  existe, un número repetido, una entrada ilegible. Bloquean el export y salen
  en `orbit doctor`.
* **aviso** — pedidos abiertos hace mucho y documentos económicos de
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
    "open_days": 60,            # pedido abierto más de N días → aviso
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
        if m.tag not in (ORDER_TAG, EXPENSE_TAG):
            continue
        if not m.link:
            out.append(Finding(ERROR, f"#{m.label or m.tag} sin justificante", m.raw))
        else:
            path = _resolve_link(project_dir, m.link)
            if path is not None and not path.exists():
                out.append(Finding(ERROR, f"el justificante no existe: {m.link}",
                                   m.raw))
        if m.tag == EXPENSE_TAG and m.op_id:
            if m.op_id in seen:
                out.append(Finding(ERROR, f"la factura {m.op_id} está dos veces "
                                   f"(también «{seen[m.op_id].concept}»)", m.raw))
            seen.setdefault(m.op_id, m)
    return out


def _check_open_orders(operations, today: date, cfg: dict) -> List[Finding]:
    limit = today - timedelta(days=int(cfg["open_days"]))
    return [Finding(WARNING, f"pedido {op.op_id} abierto hace "
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


def check_ledger(project_dir: Path, today: Optional[date] = None,
                 cfg: Optional[dict] = None) -> List[Finding]:
    """Todos los hallazgos del ledger de *project_dir*, errores primero."""
    today = today or date.today()
    cfg = cfg or load_config()
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

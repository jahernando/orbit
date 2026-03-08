"""focus.py — manage project focus via .orbit/focus.json.

Focus is the single source of truth for which projects the user is
working on in each period (day / week / month).  All other views
(dynamic notes, evaluation reports) derive from this file.
"""

import json
import sys
from datetime import date
from pathlib import Path
from typing import Optional

from core.log import PROJECTS_DIR, find_project

# .orbit/ lives at workspace root (parent of core/)
FOCUS_FILE = Path(__file__).parent.parent / ".orbit" / "focus.json"

PERIODS       = ("day", "week", "month")
PERIOD_LABELS = {"day": "Día", "week": "Semana", "month": "Mes"}


def focus_line(projects: list) -> str:
    """Format a list of focus project names as a readable string."""
    return "  ·  ".join(projects) if projects else "—"


# ── helpers ────────────────────────────────────────────────────────────────────

def _week_key(d: date) -> str:
    """ISO week key: YYYY-Wnn."""
    return d.strftime("%G-W%V")


def _period_key(period: str, d: date) -> str:
    if period == "day":
        return d.isoformat()
    if period == "week":
        return _week_key(d)
    if period == "month":
        return d.strftime("%Y-%m")
    raise ValueError(f"Unknown period: {period}")


def _load() -> dict:
    if FOCUS_FILE.exists():
        try:
            return json.loads(FOCUS_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            return {p: {} for p in PERIODS}
    return {p: {} for p in PERIODS}


def _save(data: dict):
    FOCUS_FILE.parent.mkdir(parents=True, exist_ok=True)
    FOCUS_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")


# ── public API ─────────────────────────────────────────────────────────────────

def get_focus(period: str, d: date = None) -> list:
    """Return list of focus project names for period on date d (default: today)."""
    d = d or date.today()
    data = _load()
    return data.get(period, {}).get(_period_key(period, d), [])


def get_current_focus() -> dict:
    """Return {period: [projects]} for all periods today."""
    today = date.today()
    return {p: get_focus(p, today) for p in PERIODS}


def set_focus(period: str, projects: list, d: date = None):
    """Persist focus projects for a period."""
    d = d or date.today()
    data = _load()
    data.setdefault(period, {})[_period_key(period, d)] = projects
    _save(data)


def clear_focus(period: str, d: date = None):
    set_focus(period, [], d)


# ── project resolution ────────────────────────────────────────────────────────

def _all_projects() -> list:
    if not PROJECTS_DIR.exists():
        return []
    return sorted(d.name for d in PROJECTS_DIR.iterdir() if d.is_dir())


def _resolve(name: str) -> Optional[str]:
    """Resolve partial name to full project dir name; None if not found."""
    proj_dir = find_project(name)
    return proj_dir.name if proj_dir else None


def _prompt_projects(period: str) -> list:
    """Interactive project selection for a period; returns [] on cancel."""
    if not sys.stdin.isatty():
        return []

    all_proj = _all_projects()
    if not all_proj:
        print("No hay proyectos disponibles.")
        return []

    print(f"\nProyectos disponibles:")
    for i, p in enumerate(all_proj, 1):
        print(f"  {i:2}. {p}")
    print()

    label = PERIOD_LABELS[period]
    try:
        raw = input(
            f"Proyectos en foco para {label} "
            f"(números o nombres parciales, separados por coma): "
        ).strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return []

    if not raw:
        return []

    selected = []
    for token in raw.replace(",", " ").split():
        token = token.strip()
        if not token:
            continue
        if token.isdigit():
            idx = int(token) - 1
            if 0 <= idx < len(all_proj):
                selected.append(all_proj[idx])
            else:
                print(f"⚠️  Número fuera de rango: {token}")
        else:
            matches = [p for p in all_proj if token.lower() in p.lower()]
            if len(matches) == 1:
                selected.append(matches[0])
            elif len(matches) > 1:
                print(f"⚠️  Ambiguo '{token}': {', '.join(matches)}")
            else:
                print(f"⚠️  No encontrado: {token}")

    return selected


# ── command ───────────────────────────────────────────────────────────────────

def run_focus(
    period: Optional[str]   = None,
    set_projects: Optional[list] = None,
    clear: bool             = False,
    interactive: bool       = False,
) -> int:
    today = date.today()

    # --clear
    if clear:
        p = period or "day"
        clear_focus(p, today)
        key = _period_key(p, today)
        print(f"✓ Foco de {PERIOD_LABELS[p]} ({key}) limpiado.")
        return 0

    # --set project1 project2 ...
    if set_projects:
        p = period or "day"
        resolved = []
        for name in set_projects:
            full = _resolve(name)
            if full:
                resolved.append(full)
            else:
                print(f"⚠️  Proyecto no encontrado: {name}")
                resolved.append(name)
        set_focus(p, resolved, today)
        key = _period_key(p, today)
        print(f"✓ Foco de {PERIOD_LABELS[p]} ({key}):")
        for proj in resolved:
            print(f"   • {proj}")
        return 0

    # --interactive (for a specific period or prompt which one)
    if interactive:
        p = period
        if not p:
            if not sys.stdin.isatty():
                print("Error: --interactive requiere una terminal.")
                return 1
            try:
                raw = input("Periodo [day/week/month]: ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                print()
                return 0
            p = raw if raw in PERIODS else "day"
        projects = _prompt_projects(p)
        if projects:
            set_focus(p, projects, today)
            key = _period_key(p, today)
            print(f"\n✓ Foco de {PERIOD_LABELS[p]} ({key}):")
            for proj in projects:
                print(f"   • {proj}")
        return 0

    # Default: show current focus
    if period:
        projects = get_focus(period, today)
        key = _period_key(period, today)
        label = PERIOD_LABELS[period]
        print(f"\n── FOCO {label.upper()} ({key}) ──")
        if projects:
            for proj in projects:
                print(f"  • {proj}")
        else:
            print("  —  sin proyectos en foco")
            print(f"\n  Usa: orbit focus {period} --set <proyecto> ...")
        print()
        return 0

    # Show all periods
    current = get_current_focus()
    has_any = any(current[p] for p in PERIODS)

    print(f"\n── FOCO ACTUAL ({today.isoformat()}) ──")
    for p in ("month", "week", "day"):
        label = PERIOD_LABELS[p]
        key   = _period_key(p, today)
        projects = current[p]
        if projects:
            print(f"\n{label} ({key}):")
            for proj in projects:
                print(f"  • {proj}")
        else:
            print(f"\n{label} ({key}):  —")

    if not has_any:
        print(
            "\n  Sin proyectos en foco. "
            "Usa 'orbit focus month --set proj1 proj2' para establecer el foco."
        )
    print()
    return 0

"""reorganize — interactive batch reschedule of pending items.

The morning/evening workflow: see what's pending today (plus anything
overdue), pick items one by one and act on them quickly without typing
the full command. Each action delegates to the existing CLI runners
(`run_task_done` etc.) so behaviour stays consistent and the gsync
push happens automatically.

Scope: drop / done / move-date / move-time / skip. For other edits
(title, notes, recur, ring) the user exits and runs `task edit` etc.
directly — keeping reorganize simple.
"""

from datetime import date, timedelta
from pathlib import Path
from typing import Optional

from core.agenda_cmds import (
    _read_agenda,
    run_task_done, run_task_drop, run_task_edit,
    run_ms_done, run_ms_drop, run_ms_edit,
    run_ev_drop, run_ev_edit,
    run_reminder_drop, run_reminder_edit,
)
from core.config import iter_project_dirs, normalize as _normalize
from core.dateparse import parse_date as _parse_date
from core.log import resolve_file
from core.project import _is_new_project, _find_new_project


_KIND_EMOJI = {"task": "✅", "ms": "🏁", "ev": "📅", "reminder": "💬"}
_KIND_LABEL = {"task": "tarea", "ms": "hito", "ev": "evento", "reminder": "recordatorio"}
_TYPE_TO_KEY = {"task": "tasks", "ms": "milestones",
                "ev": "events", "reminder": "reminders"}

# Accepted CLI aliases for the type filter; None / "all" = no filter.
_TYPE_ALIASES = {
    "task": "task", "tasks": "task",
    "ms": "ms", "milestone": "ms", "milestones": "ms",
    "ev": "ev", "event": "ev", "events": "ev",
    "rem": "reminder", "reminder": "reminder", "reminders": "reminder",
}


def _canonical_type(t: Optional[str]) -> Optional[str]:
    """Return the canonical kind name or None for "all"."""
    if not t or t == "all":
        return None
    return _TYPE_ALIASES.get(t, t)


def _looks_iso(s: str) -> bool:
    """Whether *s* matches a standard date form runner-validators accept."""
    import re as _re
    return bool(_re.match(r"^\d{4}-\d{2}-\d{2}$", s or ""))


# ── Period resolution ──────────────────────────────────────────────────────

def _resolve_period(period: str) -> tuple:
    """Return (lo, hi, include_overdue) date pair for *period*.

    - ``today`` → today..today, with overdue pending also surfaced.
    - ``week``  → ISO week containing today (Mon..Sun).
    - ``month`` → calendar month containing today.
    - ``YYYY-MM-DD``    → that single day.
    - ``YYYY-Wnn``      → that ISO week.
    """
    today = date.today()
    if not period or period == "today":
        return today, today, True
    if period == "week":
        mon = today - timedelta(days=today.weekday())
        return mon, mon + timedelta(days=6), False
    if period == "month":
        first = today.replace(day=1)
        if first.month == 12:
            next_first = first.replace(year=first.year + 1, month=1)
        else:
            next_first = first.replace(month=first.month + 1)
        last = next_first - timedelta(days=1)
        return first, last, False
    # ISO week: 2026-W21
    if "W" in period and len(period) == 8:
        y, w = period.split("-W")
        jan4 = date(int(y), 1, 4)
        mon_w1 = jan4 - timedelta(days=jan4.weekday())
        mon = mon_w1 + timedelta(weeks=int(w) - 1)
        return mon, mon + timedelta(days=6), False
    # Concrete date
    try:
        d = date.fromisoformat(period)
        return d, d, False
    except ValueError:
        return today, today, True


# ── Item collection ────────────────────────────────────────────────────────

def _item_in_period(item: dict, kind: str, lo: date, hi: date,
                    include_overdue: bool) -> bool:
    """Decide whether *item* should appear in the listing."""
    # Skip cancelled items always.
    if item.get("cancelled"):
        return False
    if kind in ("task", "ms") and item.get("status") in ("done", "cancelled"):
        return False

    raw = item.get("date")
    if not raw:
        # Tasks/ms without date — only listed when period is "today" with
        # include_overdue=True (the catch-all "to do whenever" pile).
        return include_overdue and kind in ("task", "ms")
    try:
        d = date.fromisoformat(raw)
    except ValueError:
        return False
    if lo <= d <= hi:
        return True
    if include_overdue and d < lo and kind in ("task", "ms", "reminder"):
        return True
    return False


def _collect_items(type_filter: Optional[str],
                   project_filter: Optional[str],
                   period: str) -> list:
    """Walk projects and return the items that match the filters.

    Returns a list of (kind, project_dir, item) sorted by date (overdue
    first, then chronological; undated last).
    """
    lo, hi, include_overdue = _resolve_period(period)

    if project_filter:
        project_dir = _find_new_project(project_filter)
        if not project_dir:
            print(f"⚠️  Proyecto no encontrado: {project_filter!r}")
            return []
        dirs = [project_dir]
    else:
        dirs = [d for d in iter_project_dirs() if _is_new_project(d)]

    canonical = _canonical_type(type_filter)
    kinds = ("task", "ms", "ev", "reminder") if canonical is None else (canonical,)

    out = []
    for project_dir in dirs:
        agenda = resolve_file(project_dir, "agenda")
        if not agenda.exists():
            continue
        data = _read_agenda(agenda)
        for kind in kinds:
            section_key = _TYPE_TO_KEY[kind]
            for item in data.get(section_key) or []:
                if _item_in_period(item, kind, lo, hi, include_overdue):
                    out.append((kind, project_dir, item))

    today = date.today()
    def _sort_key(entry):
        kind, _, item = entry
        raw = item.get("date")
        if not raw:
            return (1, today + timedelta(days=365), 0)
        try:
            d = date.fromisoformat(raw)
        except ValueError:
            return (1, today + timedelta(days=365), 0)
        return (0, d, 0 if d < today else 1)
    out.sort(key=_sort_key)
    return out


# ── Display ────────────────────────────────────────────────────────────────

def _format_item_row(idx: int, kind: str, project_dir: Path, item: dict) -> str:
    today = date.today()
    raw = item.get("date")
    if raw:
        try:
            d = date.fromisoformat(raw)
        except ValueError:
            d = None
        overdue = d is not None and d < today
        date_part = raw + (f" ⏰{item['time']}" if item.get("time") else "")
        if overdue:
            date_part = "⚠️ " + date_part
    else:
        date_part = "sin fecha"
    emoji = _KIND_EMOJI.get(kind, "•")
    return f"  {idx:>3}. {emoji} [{project_dir.name}] {item['desc']:<50.50} ({date_part})"


def _print_listing(items: list, period: str):
    if not items:
        return
    print(f"Reorganizar — {period}")
    print("─" * 70)
    for i, (kind, pd, item) in enumerate(items, 1):
        print(_format_item_row(i, kind, pd, item))
    print("─" * 70)


# ── Action prompts ─────────────────────────────────────────────────────────

def _prompt(prompt_str: str, default: str = "") -> str:
    try:
        v = input(prompt_str).strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return ""
    return v or default


def _apply_action(action: str, kind: str, project_dir: Path, item: dict) -> bool:
    """Run the matching CLI operation. Return True if something changed."""
    proj = project_dir.name
    desc = item["desc"]
    if action == "d":
        if kind == "task":
            run_task_drop(proj, desc, force=True)
        elif kind == "ms":
            run_ms_drop(proj, desc, force=True)
        elif kind == "ev":
            run_ev_drop(proj, desc, force=True)
        elif kind == "reminder":
            run_reminder_drop(proj, desc, force=True)
        return True
    if action == "n":
        if kind == "task":
            run_task_done(proj, desc)
        elif kind == "ms":
            run_ms_done(proj, desc)
        elif kind == "reminder":
            # Reminders have no `done` — drop instead.
            run_reminder_drop(proj, desc, force=True)
        elif kind == "ev":
            print("  (eventos no se completan; usa 'd' para descartar.)")
            return False
        return True
    if action == "f":
        raw = _prompt("    nueva fecha (hoy/mañana/viernes/next monday/+N/YYYY-MM-DD): ")
        if not raw:
            return False
        # Translate natural language ("viernes", "mañana", "next monday", …)
        # to a standard form before delegating to the runner. Runners use
        # _valid_date which only accepts ISO.
        new_date = _parse_date(raw)
        if new_date == raw and not _looks_iso(new_date):
            print(f"  ⚠️  Fecha no reconocida: {raw!r}.")
            return False
        if kind == "task":
            run_task_edit(proj, desc, new_date=new_date, force=True)
        elif kind == "ms":
            run_ms_edit(proj, desc, new_date=new_date, force=True)
        elif kind == "ev":
            run_ev_edit(proj, desc, new_date=new_date, force=True)
        elif kind == "reminder":
            run_reminder_edit(proj, desc, new_date=new_date, force=True)
        return True
    if action == "h":
        new_time = _prompt("    nueva hora (HH:MM o HH:MM-HH:MM, 'none' = quitar): ")
        if not new_time:
            return False
        if kind == "task":
            run_task_edit(proj, desc, new_time=new_time, force=True)
        elif kind == "ms":
            run_ms_edit(proj, desc, new_time=new_time, force=True)
        elif kind == "ev":
            run_ev_edit(proj, desc, new_time=new_time, force=True)
        elif kind == "reminder":
            run_reminder_edit(proj, desc, new_time=new_time, force=True)
        return True
    return False


def _action_for(idx: int, items: list) -> Optional[str]:
    """Show the action menu for one item; return chosen action letter."""
    if idx < 1 or idx > len(items):
        return None
    kind, project_dir, item = items[idx - 1]
    print()
    print(_format_item_row(idx, kind, project_dir, item).strip())
    print("  [d]rop  [n]done  [f]echa  [h]ora  [s]kip")
    a = _prompt("  ?> ").lower()
    return a


# ── Main entry ─────────────────────────────────────────────────────────────

def run_reorganize(type_filter: Optional[str] = None,
                   project: Optional[str] = None,
                   period: str = "today") -> int:
    """Interactive loop to triage pending items."""
    actions_applied = 0
    while True:
        items = _collect_items(type_filter, project, period)
        if not items:
            if actions_applied:
                print(f"\n✓ {actions_applied} cambio{'s' if actions_applied != 1 else ''} aplicado{'s' if actions_applied != 1 else ''}.")
            else:
                print("Sin items para reorganizar.")
            return 0

        _print_listing(items, period)
        sel = _prompt("\n#? (número, q=salir) > ")
        if not sel or sel.lower() in ("q", "quit", "exit"):
            if actions_applied:
                print(f"✓ {actions_applied} cambio{'s' if actions_applied != 1 else ''} aplicado{'s' if actions_applied != 1 else ''}.")
            return 0
        try:
            idx = int(sel)
        except ValueError:
            print(f"  ⚠️  No reconozco {sel!r}.")
            continue

        action = _action_for(idx, items)
        if not action or action == "s":
            continue
        if action == "q":
            if actions_applied:
                print(f"✓ {actions_applied} cambio{'s' if actions_applied != 1 else ''} aplicado{'s' if actions_applied != 1 else ''}.")
            return 0
        kind, project_dir, item = items[idx - 1]
        try:
            if _apply_action(action, kind, project_dir, item):
                actions_applied += 1
        except Exception as exc:
            print(f"  ⚠️  Error: {exc}")

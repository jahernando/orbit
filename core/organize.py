"""organize — interactive batch processing of agenda items.

The morning/evening workflow: see what's pending today (plus anything
overdue), pick items one by one and act on them quickly without typing
the full command. Each action delegates to the existing CLI runners
(`run_task_done` etc.) so behaviour stays consistent and the gsync
push happens automatically.

Scope: drop / done / move-date / move-time / skip. For other edits
(title, notes, recur, ring) the user exits and runs `task edit` etc.
directly — keeping organize simple.

The command was named ``reorganize`` until 2026-05-18; the old name is
still accepted as an alias for muscle-memory.
"""

from datetime import date, timedelta
from pathlib import Path
from typing import Optional

from core.agenda_cmds import (
    _read_agenda, _write_agenda,
    run_task_done, run_task_drop, run_task_edit,
    run_ms_done, run_ms_drop, run_ms_edit,
    run_ev_drop, run_ev_edit,
    run_reminder_drop, run_reminder_edit,
)
from core.agenda.display import item_followups, add_followup, drop_followup
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
                    include_overdue: bool,
                    include_undated: bool = False) -> bool:
    """Decide whether *item* should appear in the listing."""
    # Skip cancelled items always.
    if item.get("cancelled"):
        return False
    if kind in ("task", "ms") and item.get("status") in ("done", "cancelled"):
        return False

    raw = item.get("date")
    if not raw:
        # Undated tasks/ms only when explicitly opted in.
        return include_undated and kind in ("task", "ms")
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
                   period: str,
                   include_undated: bool = False) -> list:
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
                if _item_in_period(item, kind, lo, hi, include_overdue,
                                    include_undated=include_undated):
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
    print(f"Organizar — {period}")
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

def _summary_and_refresh(actions_applied: int) -> None:
    """Print the count of changes and, if any, refresh dash artifacts."""
    if actions_applied:
        plural = "s" if actions_applied != 1 else ""
        print(f"✓ {actions_applied} cambio{plural} aplicado{plural}.")
        try:
            from orbit import run_dash
            run_dash(silent=True)
        except Exception:
            # Dash refresh is best-effort; failures shouldn't bubble up.
            pass


def run_organize(type_filter: Optional[str] = None,
                   project: Optional[str] = None,
                   period: str = "today",
                   include_undated: bool = False,
                   triage: bool = False) -> int:
    """Interactive loop to triage agenda items.

    ``triage=True`` switches the flow to *followups* (``⏩ <= today``) across
    all four cita types — the "Decidir hoy" surface after F5 retired the
    ``ff`` axis. Default mode processes planned + overdue + ev/ms/reminder
    with the date/time/done/drop verbs.
    """
    if triage:
        return _run_organize_triage(project_filter=project)

    actions_applied = 0
    while True:
        items = _collect_items(type_filter, project, period,
                                include_undated=include_undated)
        if not items:
            if actions_applied:
                _summary_and_refresh(actions_applied)
            else:
                print("Sin items para organizar.")
            return 0

        _print_listing(items, period)
        sel = _prompt("\n#? (número, q=salir) > ")
        if not sel or sel.lower() in ("q", "quit", "exit"):
            _summary_and_refresh(actions_applied)
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
            _summary_and_refresh(actions_applied)
            return 0
        kind, project_dir, item = items[idx - 1]
        try:
            if _apply_action(action, kind, project_dir, item):
                actions_applied += 1
        except Exception as exc:
            print(f"  ⚠️  Error: {exc}")


# ── Triage mode (followups ⏩ <= today across all citas) ─────────────────────
#
# After F5, "Decidir hoy" is driven by followups (⏩ body lines), not by the
# retired ``ff`` header axis. A triage row is one followup ≤ today anchored to
# a cita of any of the four types. Five actions resolve it:
#   plan   → give the cita a date (edit) and clear this followup
#   snooze → move the followup to a later date
#   clear  → drop the followup (decided; cita stays dateless = reposo)
#   done   → complete the cita (task/ms only)
#   drop   → delete the cita entirely

_TRIAGE_KINDS = [("task", "tasks"), ("ms", "milestones"),
                 ("ev", "events"), ("reminder", "reminders")]


def _collect_followup_items(project_filter: Optional[str],
                            today: date) -> list:
    """Return ``[(project_dir, kind, item, fup)]`` for followups ⏩ <= today,
    across all four cita types, skipping done/cancelled items.

    Sorted ascending by followup date (most overdue first), then by
    description, so the order is deterministic across runs.
    """
    if project_filter:
        project_dir = _find_new_project(project_filter)
        if not project_dir:
            print(f"⚠️  Proyecto no encontrado: {project_filter!r}")
            return []
        dirs = [project_dir]
    else:
        dirs = [d for d in iter_project_dirs() if _is_new_project(d)]

    today_iso = today.isoformat()
    out = []
    for project_dir in dirs:
        agenda = resolve_file(project_dir, "agenda")
        if not agenda.exists():
            continue
        data = _read_agenda(agenda)
        for kind, key in _TRIAGE_KINDS:
            for item in data.get(key) or []:
                if item.get("status") in ("done", "cancelled"):
                    continue
                if item.get("cancelled"):   # reminders
                    continue
                for fup in item_followups(item):
                    if fup["date"] and fup["date"] <= today_iso:
                        out.append((project_dir, kind, item, fup))

    out.sort(key=lambda r: (r[3]["date"], r[2].get("desc", "")))
    return out


def _format_triage_row(idx: int, project_dir: Path, kind: str,
                       item: dict, fup: dict, today_iso: str) -> str:
    mark = "❗ " if fup["date"] < today_iso else "  "
    emoji = _KIND_EMOJI[kind]
    extra = f" — {fup['desc']}" if fup.get("desc") else ""
    return (f"  {idx:>3}. {mark}{emoji} [{project_dir.name}] "
            f"{(item.get('desc') or ''):<50.50} ⏩{fup['date']}{extra}")


def _print_triage_listing(items: list, today_iso: str):
    if not items:
        return
    print("Decidir hoy — followups ⏩ <= today")
    print("─" * 70)
    for i, (pd, kind, item, fup) in enumerate(items, 1):
        print(_format_triage_row(i, pd, kind, item, fup, today_iso))
    print("─" * 70)


def _edit_kind_date(kind: str, proj: str, desc: str,
                    new_date: str, new_time: Optional[str]) -> None:
    """Set date (and optional time) on a cita of any kind. force=True."""
    if kind == "task":
        run_task_edit(proj, desc, new_date=new_date, new_time=new_time, force=True)
    elif kind == "ms":
        run_ms_edit(proj, desc, new_date=new_date, new_time=new_time, force=True)
    elif kind == "ev":
        run_ev_edit(proj, desc, new_date=new_date, new_time=new_time, force=True)
    elif kind == "reminder":
        run_reminder_edit(proj, desc, new_date=new_date, new_time=new_time, force=True)


def _drop_kind(kind: str, proj: str, desc: str) -> None:
    if kind == "task":
        run_task_drop(proj, desc, force=True)
    elif kind == "ms":
        run_ms_drop(proj, desc, force=True)
    elif kind == "ev":
        run_ev_drop(proj, desc, force=True)
    elif kind == "reminder":
        run_reminder_drop(proj, desc, force=True)


def _locate_in_data(data: dict, item: dict) -> Optional[dict]:
    """Find *item* in a freshly-read agenda dict by orbit_id, else by desc."""
    oid, desc = item.get("orbit_id"), item.get("desc")
    for key in ("tasks", "milestones", "events", "reminders"):
        for it in data.get(key) or []:
            if oid and it.get("orbit_id") == oid:
                return it
            if not oid and it.get("desc") == desc:
                return it
    return None


def _mutate_followup(project_dir: Path, item: dict, *,
                     drop_date: Optional[str] = None,
                     add_date: Optional[str] = None,
                     add_desc: Optional[str] = None) -> bool:
    """Re-read the agenda, locate *item*, mutate its followups, write.

    Direct body edit (no state, silent) — followups have no side effects
    (design §0.5). Returns True if the file was written.
    """
    agenda = resolve_file(project_dir, "agenda")
    data = _read_agenda(agenda)
    target = _locate_in_data(data, item)
    if target is None:
        return False
    if drop_date:
        drop_followup(target, drop_date)
    if add_date:
        add_followup(target, add_date, add_desc)
    _write_agenda(agenda, data)
    return True


def _apply_triage_action(action: str, project_dir: Path, kind: str,
                         item: dict, fup: dict) -> bool:
    """Resolve one followup-triage row. Return True if something changed."""
    proj = project_dir.name
    desc = item.get("desc")
    fdate = fup["date"]

    if action == "p":  # plan: give the cita a date, then clear this followup
        raw = _prompt("    fecha (today/mañana/viernes/+N/YYYY-MM-DD): ")
        if not raw:
            return False
        new_date = _parse_date(raw)
        if new_date == raw and not _looks_iso(new_date):
            print(f"  ⚠️  Fecha no reconocida: {raw!r}.")
            return False
        time_raw = _prompt("    hora (opcional, HH:MM[-HH:MM], enter para ninguna): ")
        _edit_kind_date(kind, proj, desc, new_date, time_raw or None)
        _mutate_followup(project_dir, item, drop_date=fdate)
        return True

    if action == "s":  # snooze: move the followup to a later date
        raw = _prompt("    nuevo ⏩ (YYYY-MM-DD/mañana/+N, enter=mañana): ")
        if not raw:
            new = (date.today() + timedelta(days=1)).isoformat()
        else:
            new = _parse_date(raw)
            if new == raw and not _looks_iso(new):
                print(f"  ⚠️  Fecha no reconocida: {raw!r}.")
                return False
        return _mutate_followup(project_dir, item, drop_date=fdate,
                                add_date=new, add_desc=fup.get("desc"))

    if action == "c":  # clear: drop the followup; cita stays (someday/reposo)
        return _mutate_followup(project_dir, item, drop_date=fdate)

    if action == "n":  # done: complete the cita (task/ms only)
        if kind == "task":
            run_task_done(proj, desc)
        elif kind == "ms":
            run_ms_done(proj, desc)
        else:
            print(f"  ({_KIND_LABEL[kind]} no tiene 'done'; usa [c]lear o [d]rop.)")
            return False
        return True

    if action == "d":  # drop: delete the whole cita
        _drop_kind(kind, proj, desc)
        return True

    return False


def _triage_action_for(idx: int, items: list, today_iso: str) -> Optional[str]:
    if idx < 1 or idx > len(items):
        return None
    pd, kind, item, fup = items[idx - 1]
    print()
    print(_format_triage_row(idx, pd, kind, item, fup, today_iso).strip())
    print("  [p]lan-fecha  [s]nooze-⏩  [c]lear-⏩  do[n]e  [d]rop  s[k]ip")
    return _prompt("  ?> ").lower()


def _run_organize_triage(project_filter: Optional[str] = None) -> int:
    today = date.today()
    today_iso = today.isoformat()
    actions_applied = 0
    while True:
        items = _collect_followup_items(project_filter, today)
        if not items:
            if actions_applied:
                _summary_and_refresh(actions_applied)
            else:
                print("Nada que decidir hoy.")
            return 0

        _print_triage_listing(items, today_iso)
        sel = _prompt("\n#? (número, q=salir) > ")
        if not sel or sel.lower() in ("q", "quit", "exit"):
            _summary_and_refresh(actions_applied)
            return 0
        try:
            idx = int(sel)
        except ValueError:
            print(f"  ⚠️  No reconozco {sel!r}.")
            continue

        action = _triage_action_for(idx, items, today_iso)
        if not action or action == "k":
            continue
        if action == "q":
            _summary_and_refresh(actions_applied)
            return 0
        pd, kind, item, fup = items[idx - 1]
        try:
            if _apply_triage_action(action, pd, kind, item, fup):
                actions_applied += 1
        except Exception as exc:
            print(f"  ⚠️  Error: {exc}")


# Backwards-compat alias (the command was named ``reorganize`` until 2026-05-18).
run_reorganize = run_organize

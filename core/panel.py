"""core/panel.py — dashboard: priority projects, agenda, activity.

  orbit panel [week|month] [--open] [--append proyecto:nota]

Sections:
  1. Priority (alta + milestones this month + urgent for period)
  2. Agenda (dated items in period, grouped by day if multi-day)
  3. Activity (logbook entries in period)
"""

import calendar
from datetime import date, timedelta
from pathlib import Path

from core.config import iter_federated_project_dirs, get_federation_emoji
from core.log import find_logbook_file, find_proyecto_file, resolve_file
from core.project import _read_project_meta, _resolve_status, _is_new_project
from core.tasks import PRIORITY_MAP


# ── Period helpers ────────────────────────────────────────────────────────────

_WEEKDAYS_ES = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes",
                "Sábado", "Domingo"]


def _parse_panel_period(period_str):
    """Return (start, end, label) for a panel period.

    Accepts: None/'today'/'hoy', 'week'/'semana', 'month'/'mes'.
    """
    today = date.today()
    if not period_str or period_str.lower() in ("today", "hoy"):
        return today, today, f"{today.isoformat()} ({today.strftime('%A')})"
    p = period_str.lower()
    if p in ("week", "semana"):
        monday = today - timedelta(days=today.weekday())
        sunday = monday + timedelta(days=6)
        iso = today.isocalendar()
        label = f"{iso[0]}-W{iso[1]:02d} ({monday.isoformat()} → {sunday.isoformat()})"
        return monday, sunday, label
    if p in ("month", "mes"):
        first = date(today.year, today.month, 1)
        last = date(today.year, today.month,
                    calendar.monthrange(today.year, today.month)[1])
        label = f"{today.strftime('%Y-%m')} ({first.isoformat()} → {last.isoformat()})"
        return first, last, label
    return today, today, f"{today.isoformat()} ({today.strftime('%A')})"


# ── Priority scanning ─────────────────────────────────────────────────────────

def _scan_project_agenda(project_dir, start, end):
    """Return (milestones_this_month, has_items_in_period, has_overdue).

    milestones_this_month: list of (date_str, desc) — always scanned for the month.
    has_items_in_period: True if tasks/events/milestones fall in [start, end].
    has_overdue: True if tasks are overdue (before today).
    """
    from core.agenda_cmds import _read_agenda

    agenda_path = resolve_file(project_dir, "agenda")
    if not agenda_path.exists():
        return [], False, False

    data = _read_agenda(agenda_path)
    today = date.today()
    month_end = date(today.year, today.month,
                     calendar.monthrange(today.year, today.month)[1])

    milestones = []
    has_items = False
    has_overdue = False

    for m in data["milestones"]:
        if m["status"] != "pending" or not m.get("date"):
            continue
        try:
            d = date.fromisoformat(m["date"])
            if today <= d <= month_end:
                milestones.append((m["date"], m["desc"]))
            if start <= d <= end:
                has_items = True
        except ValueError:
            pass

    for t in data["tasks"]:
        if t["status"] != "pending" or not t.get("date"):
            continue
        try:
            d = date.fromisoformat(t["date"])
            if start <= d <= end:
                has_items = True
            if d < today:
                has_overdue = True
        except ValueError:
            pass

    for e in data["events"]:
        if not e.get("date"):
            continue
        try:
            d = date.fromisoformat(e["date"])
            if start <= d <= end:
                has_items = True
        except ValueError:
            pass

    return milestones, has_items, has_overdue


def _project_link(project_dir) -> str:
    """Markdown link to project.md; federated get emoji prefix with brackets, no link."""
    fed_emoji = get_federation_emoji(project_dir)
    if fed_emoji:
        return f"{fed_emoji} \\[{project_dir.name}\\]"
    proj_file = find_proyecto_file(project_dir)
    rel = f"{project_dir.parent.name}/{project_dir.name}"
    if proj_file:
        return f"[{project_dir.name}]({rel}/{proj_file.name})"
    return f"[{project_dir.name}]({rel}/)"


def _fed_tag(project_dir) -> str:
    """Terminal tag: [name] for local, 🌿 [name] for federated."""
    emoji = get_federation_emoji(project_dir)
    if emoji:
        return f"{emoji} [{project_dir.name}]"
    return f"[{project_dir.name}]"


def _fed_label(project_dir) -> str:
    """Project name with federation emoji prefix and brackets if federated."""
    emoji = get_federation_emoji(project_dir)
    return f"{emoji} [{project_dir.name}]" if emoji else project_dir.name


def _collect_priority_projects(start, end, include_federated=True):
    """Return (alta, milestones, media)."""
    alta = []
    milestones = []
    media = []
    media_seen = set()

    for project_dir in iter_federated_project_dirs(include_federated):
        if not _is_new_project(project_dir):
            continue
        meta = _read_project_meta(project_dir)
        status_key, _, _ = _resolve_status(meta, project_dir)
        if status_key in ("sleeping", "paused"):
            continue

        prio = meta.get("prioridad", "media").lower()
        motivo = meta.get("prioridad_motivo", "")
        ms_list, has_items, has_overdue = _scan_project_agenda(
            project_dir, start, end)

        if prio == "alta":
            alta.append((project_dir, motivo))

        for ms_date, ms_desc in ms_list:
            milestones.append((project_dir, ms_date, ms_desc))

        reasons = []
        if has_items:
            reasons.append("citas en periodo")
        if has_overdue:
            reasons.append("tareas vencidas")
        if reasons and project_dir not in media_seen:
            media.append((project_dir, ", ".join(reasons)))
            media_seen.add(project_dir)

    milestones.sort(key=lambda x: x[1])
    return alta, milestones, media


# ── Agenda ────────────────────────────────────────────────────────────────────

def _collect_agenda(start, end, include_federated=True):
    """Collect agenda items for period. Returns dict {date_str: [(sort_key, line)]}."""
    from core.agenda_view import _collect_data

    today = date.today()
    dirs = [d for d in iter_federated_project_dirs(include_federated) if _is_new_project(d)]
    collected = _collect_data(dirs, start, end, dated_only=True)

    by_day = {}  # date_str → [(sort_key, line)]
    for project_dir, tasks, events, milestones in collected:
        proj = _project_link(project_dir)
        for e in events:
            day = e.get("date", "")
            time = e.get("time", "")
            time_display = f"⏰{time} " if time else ""
            key = time if time else "zz"
            by_day.setdefault(day, []).append(
                (key, f"- 📅 {time_display}{e['desc']} — {proj}"))
        for m in milestones:
            day = m.get("date", "")
            by_day.setdefault(day, []).append(
                ("zz", f"- ☐ 🏁 {m['desc']} — {proj}"))
        for t in tasks:
            day = t.get("date", "")
            time = t.get("time", "")
            time_display = f"⏰{time} " if time else ""
            overdue = ""
            if day:
                try:
                    if date.fromisoformat(day) < today:
                        overdue = " ⚠️ vencida"
                except ValueError:
                    pass
            key = time if time else "zz"
            by_day.setdefault(day, []).append(
                (key, f"- ☐ {time_display}{t['desc']}{overdue} — {proj}"))

    # For single-day view, fold overdue items into today
    if start == end:
        today_str = start.isoformat()
        for day_str in list(by_day.keys()):
            if day_str and day_str < today_str:
                by_day.setdefault(today_str, []).extend(by_day.pop(day_str))

    # Sort items within each day by time
    for day in by_day:
        by_day[day].sort(key=lambda x: x[0])

    return by_day


# ── Activity ──────────────────────────────────────────────────────────────────

def _collect_activity(start, end, include_federated=True):
    """Collect logbook entries for period. Returns list of (project_dir, entries)."""
    from core.stats import _scan_logbook

    results = []
    for project_dir in sorted(iter_federated_project_dirs(include_federated)):
        if not _is_new_project(project_dir):
            continue
        logbook_path = find_logbook_file(project_dir)
        if not logbook_path or not logbook_path.exists():
            continue
        _, entries, _, _ = _scan_logbook(logbook_path, start, end)
        if entries:
            results.append((project_dir, entries))
    return results


# ── Main ──────────────────────────────────────────────────────────────────────

def _print_calendar(start, end):
    """Print calendar grid. ANSI for terminal, markdown for --open/--append."""
    import sys
    from core.agenda_view import _print_calendar_grid_md, _print_calendar_grid_ansi

    today = date.today()
    dirs = [d for d in iter_federated_project_dirs() if _is_new_project(d)]

    # Always show at least the current week
    cal_start = min(start, today - timedelta(days=today.weekday()))
    cal_end = max(end, cal_start + timedelta(days=6))

    if sys.stdout.isatty():
        _print_calendar_grid_ansi(dirs, cal_start, cal_end)
    else:
        _print_calendar_grid_md(dirs, cal_start, cal_end)


def run_panel(period=None, include_federated=True) -> int:
    """Print dashboard as markdown."""
    start, end, label = _parse_panel_period(period)
    is_single_day = start == end

    print(f"# Panel — {label}")

    # ── Calendar ──
    print()
    _print_calendar(start, end)

    # ── 1. Prioridad ──
    alta, milestones, media = _collect_priority_projects(start, end, include_federated)

    print(f"\n## Prioridad\n")
    if alta:
        print(f"🔴 **Alta**")
        for project_dir, motivo in alta:
            suffix = f" — {motivo}" if motivo else ""
            print(f"- {_project_link(project_dir)}{suffix}")
    if media:
        if alta:
            print()
        print(f"🔶 **Urgente**")
        for project_dir, reason in media:
            print(f"- {_project_link(project_dir)} — {reason}")
    if milestones:
        if alta or media:
            print()
        print(f"🏁 **Hitos este mes**")
        for project_dir, ms_date, ms_desc in milestones:
            print(f"- {ms_date} — {ms_desc} ({_fed_label(project_dir)})")
    if not alta and not media and not milestones:
        print("(ninguno)")
    print("\n---")

    # ── 2. Agenda ──
    by_day = _collect_agenda(start, end, include_federated)

    print(f"\n## Agenda\n")
    if by_day:
        if is_single_day:
            # Single day: flat list
            items = by_day.get(start.isoformat(), [])
            for _, line in items:
                print(line)
            if not items:
                print("(sin citas)")
        else:
            # Multi-day: group by day
            for day_str in sorted(by_day.keys()):
                if not day_str:
                    continue
                try:
                    d = date.fromisoformat(day_str)
                    wd = _WEEKDAYS_ES[d.weekday()]
                    print(f"**{day_str} ({wd})**")
                except ValueError:
                    print(f"**{day_str}**")
                for _, line in by_day[day_str]:
                    print(line)
                print()
    else:
        print("(sin citas)")
    print("\n---")

    # ── 3. Actividad ──
    activity = _collect_activity(start, end, include_federated)

    print(f"\n## Actividad\n")
    if activity:
        for project_dir, entries in activity:
            print(f"**{_project_link(project_dir)}**")
            for e in entries:
                print(f"- {e}")
            print()
    else:
        print("(sin actividad)")

    return 0

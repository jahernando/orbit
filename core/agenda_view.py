"""orbit agenda — show tasks, events and milestones for a day or period.

  orbit agenda                           # today
  orbit agenda --date tomorrow           # specific day
  orbit agenda --from monday --to friday # range
  orbit agenda mission orbit             # only those projects
  orbit agenda --calendar                # calendar grid view
  orbit agenda --calendar --date 2026-03 # calendar for a month
"""

import calendar as _cal
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

_MONTH_NAMES = [
    "", "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
    "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
]

from core.log import PROJECTS_DIR, resolve_file
from core.project import _find_new_project, _is_new_project
from core.agenda_cmds import _read_agenda, _next_occurrence


# ── ANSI helpers ──────────────────────────────────────────────────────────────

# Colorblind-friendly palette: rely on luminosity + shape, not red-green.
_RESET   = "\033[0m"
_BOLD    = "\033[1m"
_DIM     = "\033[2m"
_UNDERLINE = "\033[4m"
_BLUE    = "\033[34m"
_CYAN    = "\033[36m"
_YELLOW  = "\033[33m"
_RED     = "\033[31m"
_MAGENTA = "\033[35m"
_BG_BLUE    = "\033[44m\033[37m"   # blue bg, white text — tasks
_BG_CYAN    = "\033[46m\033[30m"   # cyan bg, black text — events
_BG_WHITE   = "\033[47m\033[30m"   # white bg, black text — milestones
_BG_TODAY   = "\033[7m"            # reverse video        — today


# ── Period parsing (agenda default: today) ────────────────────────────────────

def _parse_period(date_str: Optional[str],
                  date_from: Optional[str], date_to: Optional[str]):
    """Return (start, end).  Default is today (not last-30-days like report)."""
    today = date.today()

    def _start(s: str) -> date:
        if len(s) == 7:
            y, m = int(s[:4]), int(s[5:7])
            return date(y, m, 1)
        return date.fromisoformat(s)

    def _end(s: str) -> date:
        if len(s) == 7:
            y, m = int(s[:4]), int(s[5:7])
            return date(y, m, _cal.monthrange(y, m)[1])
        return date.fromisoformat(s)

    if date_from or date_to:
        s = _start(date_from) if date_from else today
        e = _end(date_to) if date_to else today
        return s, e
    if date_str:
        if len(date_str) == 7:
            y, m = int(date_str[:4]), int(date_str[5:7])
            return date(y, m, 1), date(y, m, _cal.monthrange(y, m)[1])
        d = date.fromisoformat(date_str)
        return d, d
    return today, today


def _resolve_dirs(projects: Optional[list]) -> list:
    if projects:
        dirs = []
        for p in projects:
            d = _find_new_project(p)
            if d:
                dirs.append(d)
        return dirs
    return sorted(d for d in PROJECTS_DIR.iterdir()
                  if d.is_dir() and _is_new_project(d))


def _in_range(d_str: Optional[str], start: date, end: date) -> bool:
    """Check if a YYYY-MM-DD string falls within [start, end]."""
    if not d_str:
        return False
    try:
        d = date.fromisoformat(d_str)
        return start <= d <= end
    except ValueError:
        return False


def _event_overlaps(ev: dict, start: date, end: date) -> bool:
    """Check if event date or date range overlaps [start, end]."""
    try:
        ev_start = date.fromisoformat(ev["date"])
    except ValueError:
        return False
    ev_end = ev_start
    if ev.get("end"):
        try:
            ev_end = date.fromisoformat(ev["end"])
        except ValueError:
            pass
    return ev_start <= end and ev_end >= start


# ── Recurrence expansion ─────────────────────────────────────────────────────

def _expand_recurrences(task: dict, start: date, end: date) -> list:
    """Expand a recurring task into virtual occurrences within [start, end].

    Returns a list of task dicts with concrete dates (no recur).
    The original task is NOT included — caller handles that.
    """
    if not task.get("recur") or not task.get("date"):
        return []

    recur = task["recur"]
    until_date = None
    if task.get("until"):
        try:
            until_date = date.fromisoformat(task["until"])
        except ValueError:
            pass

    base = date.fromisoformat(task["date"])
    occurrences = []
    current = base

    # Generate occurrences up to end (or until, whichever is earlier)
    limit = end
    if until_date and until_date < limit:
        limit = until_date

    # Safety cap: max 366 occurrences
    for _ in range(366):
        if current > limit:
            break
        if current >= start:
            occurrences.append(current)
        nxt_str = _next_occurrence(current.isoformat(), recur, current.isoformat())
        nxt = date.fromisoformat(nxt_str)
        if nxt <= current:
            break  # safety: no infinite loop
        current = nxt

    # Build virtual task dicts (without recur, to avoid re-expansion)
    result = []
    for d in occurrences:
        if d == base:
            continue  # skip the original date, caller handles it
        vt = dict(task)
        vt["date"] = d.isoformat()
        vt["_virtual"] = True  # marker: not a real entry
        result.append(vt)
    return result


# ── Collect agenda data ──────────────────────────────────────────────────────

def _collect_data(dirs, start, end, dated_only=False):
    """Collect tasks/events/milestones per project for the given period.

    Returns list of (project_dir, tasks, events, milestones).
    If dated_only, excludes tasks/milestones without a date.
    """
    today = date.today()
    is_single_day = start == end
    results = []

    for project_dir in dirs:
        agenda_path = resolve_file(project_dir, "agenda")
        data = _read_agenda(agenda_path)

        tasks = []
        for t in data["tasks"]:
            if t["status"] != "pending":
                continue
            if t.get("date") and _in_range(t["date"], start, end):
                tasks.append(t)
            elif not dated_only and is_single_day and start == today and not t.get("date"):
                tasks.append(t)
            elif t.get("date"):
                try:
                    if date.fromisoformat(t["date"]) < start:
                        tasks.append(t)
                except ValueError:
                    pass
            # Expand recurring tasks into virtual occurrences
            if t.get("recur") and t.get("date"):
                tasks.extend(_expand_recurrences(t, start, end))

        events = [e for e in data["events"] if _event_overlaps(e, start, end)]

        milestones = []
        for m in data["milestones"]:
            if m["status"] != "pending":
                continue
            if m.get("date") and _in_range(m["date"], start, end):
                milestones.append(m)
            elif not dated_only and is_single_day and start == today and not m.get("date"):
                milestones.append(m)
            elif m.get("date"):
                try:
                    if date.fromisoformat(m["date"]) < start:
                        milestones.append(m)
                except ValueError:
                    pass

        if tasks or events or milestones:
            results.append((project_dir, tasks, events, milestones))

    return results


# ── List view ─────────────────────────────────────────────────────────────────

def run_agenda(
    projects: Optional[list] = None,
    date_str: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    show_calendar: bool = False,
    markdown: bool = False,
    dated_only: bool = False,
) -> int:
    """Print agenda (tasks/events/milestones) for a day or period."""
    if not PROJECTS_DIR.exists():
        print(f"Error: directorio de proyectos no encontrado en {PROJECTS_DIR}")
        return 1

    start, end = _parse_period(date_str, date_from, date_to)
    dirs = _resolve_dirs(projects)
    if projects and not dirs:
        return 1

    if show_calendar:
        if markdown:
            return _print_calendar_md(dirs, start, end)
        return _print_calendar_ansi(dirs, start, end)

    today = date.today()
    is_single_day = start == end

    if is_single_day:
        header = f"AGENDA — {start.isoformat()}"
        if start == today:
            header += " (hoy)"
    else:
        days = (end - start).days + 1
        header = f"AGENDA — {start.isoformat()} → {end.isoformat()}  ({days}d)"

    lines = [header, "─" * 56]

    collected = _collect_data(dirs, start, end, dated_only=dated_only)
    lines.extend(_format_detail_lines(collected, markdown=markdown))

    total_tasks = sum(len(t) for _, t, _, _ in collected)
    total_events = sum(len(e) for _, _, e, _ in collected)
    total_ms = sum(len(m) for _, _, _, m in collected)

    lines.append("")
    lines.append("─" * 56)
    parts = []
    if total_tasks:
        parts.append(f"{total_tasks} tarea{'s' if total_tasks != 1 else ''}")
    if total_events:
        parts.append(f"{total_events} evento{'s' if total_events != 1 else ''}")
    if total_ms:
        parts.append(f"{total_ms} hito{'s' if total_ms != 1 else ''}")
    if parts:
        lines.append(" · ".join(parts))
    else:
        lines.append("Sin actividad programada.")

    print("\n".join(lines))
    return 0


# ── Calendar: ANSI terminal version ──────────────────────────────────────────

def _collect_calendar_dates(dirs, start: date = None, end: date = None):
    """Collect date sets for calendar display. Returns (task_dates, event_dates, ms_dates, overdue_dates, overdue_items)."""
    today = date.today()
    task_dates = set()
    event_dates = set()
    ms_dates = set()
    overdue_dates = set()
    overdue_items = []

    for project_dir in dirs:
        agenda_path = resolve_file(project_dir, "agenda")
        data = _read_agenda(agenda_path)

        for t in data["tasks"]:
            if t["status"] == "pending" and t.get("date"):
                try:
                    d = date.fromisoformat(t["date"])
                    task_dates.add(d)
                    if d < today:
                        overdue_dates.add(d)
                        overdue_items.append(
                            (project_dir.name, "[ ]", t["desc"], t["date"]))
                except ValueError:
                    pass
                # Expand recurring tasks for calendar
                if t.get("recur"):
                    for vt in _expand_recurrences(t, start, end):
                        try:
                            vd = date.fromisoformat(vt["date"])
                            task_dates.add(vd)
                        except ValueError:
                            pass

        for e in data["events"]:
            try:
                ev_start = date.fromisoformat(e["date"])
                ev_end = ev_start
                if e.get("end"):
                    try:
                        ev_end = date.fromisoformat(e["end"])
                    except ValueError:
                        pass
                d = ev_start
                while d <= ev_end:
                    event_dates.add(d)
                    d += timedelta(days=1)
            except ValueError:
                pass

        for m in data["milestones"]:
            if m["status"] == "pending" and m.get("date"):
                try:
                    d = date.fromisoformat(m["date"])
                    ms_dates.add(d)
                    if d < today:
                        overdue_dates.add(d)
                        overdue_items.append(
                            (project_dir.name, "🏁", m["desc"], m["date"]))
                except ValueError:
                    pass

    return task_dates, event_dates, ms_dates, overdue_dates, overdue_items


def _cap_end(start, end):
    """Limit calendar to max 3 months."""
    max_end = date(start.year + (start.month + 2) // 12,
                   (start.month + 2) % 12 + 1, 1) - timedelta(days=1)
    return min(end, max_end)


def _week_overlaps(week, y, m, start, end):
    """Check if any real day in the week falls within [start, end]."""
    for day in week:
        if day != 0 and start <= date(y, m, day) <= end:
            return True
    return False


def _format_detail_lines(collected, markdown=False):
    """Format the detail list of tasks/events/milestones (shared by calendar views)."""
    today = date.today()
    lines = []
    for project_dir, tasks, events, milestones in collected:
        lines.append("")
        lines.append(f"**[{project_dir.name}]**" if markdown else f"[{project_dir.name}]")

        pfx = "- " if markdown else "  "

        for e in sorted(events, key=lambda x: x["date"]):
            end_s = f" → {e['end']}" if e.get("end") else ""
            lines.append(f"{pfx}📅 {e['date']} — {e['desc']}{end_s}")

        for m in milestones:
            date_s = f" ({m['date']})" if m.get("date") else ""
            overdue = ""
            if m.get("date"):
                try:
                    if date.fromisoformat(m["date"]) < today:
                        overdue = " ⚠️"
                except ValueError:
                    pass
            lines.append(f"{pfx}🏁 {m['desc']}{date_s}{overdue}")

        check = "☐" if markdown else "[ ]"
        for t in sorted(tasks, key=lambda x: x.get("date") or "9999"):
            date_s = f" ({t['date']})" if t.get("date") else ""
            overdue = ""
            if t.get("date"):
                try:
                    if date.fromisoformat(t["date"]) < today:
                        overdue = " ⚠️"
                except ValueError:
                    pass
            recur_s = ""
            if t.get("recur"):
                recur_s = f" [recur:{t['recur']}"
                if t.get("until"):
                    recur_s += f":{t['until']}"
                recur_s += "]"
            lines.append(f"{pfx}{check} {t['desc']}{date_s}{recur_s}{overdue}")

    return lines


def _print_calendar_ansi(dirs: list, start: date, end: date) -> int:
    """Print a colored calendar grid using ANSI codes (for terminal)."""
    today = date.today()
    end = _cap_end(start, end)
    task_dates, event_dates, ms_dates, overdue_dates, overdue_items = \
        _collect_calendar_dates(dirs, start, end)

    lines = []
    if overdue_items:
        lines.append(f"  {_RED}{_BOLD}⚠️  Vencidas{_RESET}")
        for proj, kind, desc, d_str in sorted(overdue_items, key=lambda x: x[3]):
            lines.append(f"  {_RED}{kind} {desc} ({d_str}) — {proj}{_RESET}")
        lines.append("")

    current = date(start.year, start.month, 1)
    while current <= end:
        y, m = current.year, current.month
        month_name = _MONTH_NAMES[m]
        cal = _cal.Calendar(firstweekday=0)
        weeks = [w for w in cal.monthdayscalendar(y, m)
                 if _week_overlaps(w, y, m, start, end)]

        if weeks:
            lines.append("")
            lines.append(f"  {_BOLD}{month_name} {y}{_RESET}")
            lines.append(f"  {_BLUE}{_BOLD} Wk{_RESET}  {_DIM}Lu  Ma  Mi  Ju  Vi{_RESET}  Sa  Do")

            for week in weeks:
                first_day = next((d for d in week if d != 0), None)
                if first_day is None:
                    continue
                wk_num = date(y, m, first_day).isocalendar()[1]
                row = f"  {_BLUE}{_BOLD}W{wk_num:02d}{_RESET}  "

                for day in week:
                    if day == 0:
                        row += "    "
                        continue
                    d = date(y, m, day)
                    label = f"{day:>2}"
                    in_range = start <= d <= end

                    if not in_range:
                        cell = f"{_DIM}{label}{_RESET}"
                    elif d == today:
                        cell = f"{_BG_TODAY}{_BOLD}{label}{_RESET}"
                    elif d in overdue_dates:
                        cell = f"{_RED}{_BOLD}{_UNDERLINE}{label}{_RESET}"
                    elif d in ms_dates:
                        cell = f"{_BG_WHITE}{_BOLD}{label}{_RESET}"
                    elif d in event_dates:
                        cell = f"{_BG_CYAN}{label}{_RESET}"
                    elif d in task_dates:
                        cell = f"{_BG_BLUE}{label}{_RESET}"
                    else:
                        cell = label
                    row += cell + "  "

                lines.append(row)

        current = date(y, m + 1, 1) if m < 12 else date(y + 1, 1, 1)

    lines.append("")
    lines.append(
        f"  {_BG_TODAY} hoy {_RESET}  "
        f"{_BG_CYAN} evento {_RESET}  "
        f"{_BG_BLUE} tarea {_RESET}  "
        f"{_BG_WHITE}{_BOLD} hito {_RESET}  "
        f"{_RED}{_BOLD}{_UNDERLINE} vencida {_RESET}"
    )

    # Detail list below calendar
    collected = _collect_data(dirs, start, end)
    if collected:
        lines.append("")
        lines.append("─" * 56)
        lines.extend(_format_detail_lines(collected, markdown=False))

    lines.append("")
    print("\n".join(lines))
    return 0


# ── Calendar: Markdown version (for Typora / --open / --log) ─────────────────

def _print_calendar_md(dirs: list, start: date, end: date) -> int:
    """Print a markdown calendar table with emoji markers."""
    today = date.today()
    end = _cap_end(start, end)
    task_dates, event_dates, ms_dates, overdue_dates, overdue_items = \
        _collect_calendar_dates(dirs, start, end)

    lines = []

    # Overdue section
    if overdue_items:
        lines.append("### ⚠️ Vencidas")
        lines.append("")
        for proj, kind, desc, d_str in sorted(overdue_items, key=lambda x: x[3]):
            # Replace [ ] with ☐ to prevent clickable checkboxes in Typora
            display_kind = "☐" if kind == "[ ]" else kind
            lines.append(f"- {display_kind} {desc} ({d_str}) — {proj}")
        lines.append("")

    current = date(start.year, start.month, 1)
    while current <= end:
        y, m = current.year, current.month
        month_name = _MONTH_NAMES[m]
        cal = _cal.Calendar(firstweekday=0)
        weeks = [w for w in cal.monthdayscalendar(y, m)
                 if _week_overlaps(w, y, m, start, end)]

        if weeks:
            lines.append(f"### {month_name} {y}")
            lines.append("")
            lines.append("| Wk | Lu | Ma | Mi | Ju | Vi | Sa | Do |")
            lines.append("|---:|---:|---:|---:|---:|---:|---:|---:|")

            for week in weeks:
                first_day = next((d for d in week if d != 0), None)
                if first_day is None:
                    continue
                wk_num = date(y, m, first_day).isocalendar()[1]
                cells = [f"**W{wk_num:02d}**"]

                for day in week:
                    if day == 0:
                        cells.append("")
                        continue
                    d = date(y, m, day)
                    in_range = start <= d <= end

                    if not in_range:
                        cells.append(f"~~{day}~~")
                    elif d == today:
                        cells.append(f"**[{day}]**")
                    elif d in overdue_dates:
                        cells.append(f"⚠️{day}")
                    elif d in ms_dates:
                        cells.append(f"🏁{day}")
                    elif d in event_dates:
                        cells.append(f"📅{day}")
                    elif d in task_dates:
                        cells.append(f"✅{day}")
                    else:
                        cells.append(str(day))

                lines.append("| " + " | ".join(cells) + " |")

            lines.append("")

        current = date(y, m + 1, 1) if m < 12 else date(y + 1, 1, 1)

    # Legend
    lines.append("**[N]** hoy · 📅 evento · ✅ tarea · 🏁 hito · ⚠️ vencida")

    # Detail list below calendar
    collected = _collect_data(dirs, start, end)
    if collected:
        lines.append("")
        lines.append("---")
        lines.extend(_format_detail_lines(collected, markdown=True))

    lines.append("")
    print("\n".join(lines))
    return 0

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

from core.log import resolve_file, find_proyecto_file
from core.config import iter_project_dirs
from core.project import _find_new_project, _is_new_project
from core.agenda_cmds import _read_agenda, _next_occurrence


def _project_link(project_dir):
    """Build a markdown link to the project file: [name](relative/path)."""
    proj_file = find_proyecto_file(project_dir)
    rel = f"{project_dir.parent.name}/{project_dir.name}"
    if proj_file:
        return f"[{project_dir.name}]({rel}/{proj_file.name})"
    return f"[{project_dir.name}]({rel}/)"


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
        if "W" in s:                              # YYYY-Wnn
            y, w = int(s[:4]), int(s.split("W")[1])
            return date.fromisocalendar(y, w, 1)  # Monday
        if len(s) == 7:
            y, m = int(s[:4]), int(s[5:7])
            return date(y, m, 1)
        return date.fromisoformat(s)

    def _end(s: str) -> date:
        if "W" in s:                              # YYYY-Wnn
            y, w = int(s[:4]), int(s.split("W")[1])
            return date.fromisocalendar(y, w, 7)  # Sunday
        if len(s) == 7:
            y, m = int(s[:4]), int(s[5:7])
            return date(y, m, _cal.monthrange(y, m)[1])
        return date.fromisoformat(s)

    if date_from or date_to:
        s = _start(date_from) if date_from else today
        e = _end(date_to) if date_to else today
        return s, e
    if date_str:
        if "W" in date_str:
            return _start(date_str), _end(date_str)
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
    return [d for d in iter_project_dirs() if _is_new_project(d)]


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

def _expand_recurrences(item: dict, start: date, end: date) -> list:
    """Expand a recurring item (task, milestone or event) into virtual
    occurrences within [start, end].

    Returns a list of dicts with concrete dates (no recur).
    The original item is NOT included — caller handles that.
    For events with an ``end`` date, each occurrence preserves the same
    duration (offset between date and end).
    """
    if not item.get("recur") or not item.get("date"):
        return []

    recur = item["recur"]
    until_date = None
    if item.get("until"):
        try:
            until_date = date.fromisoformat(item["until"])
        except ValueError:
            pass

    base = date.fromisoformat(item["date"])

    # Event duration (for multi-day events)
    duration = None
    if item.get("end"):
        try:
            duration = date.fromisoformat(item["end"]) - base
        except ValueError:
            pass

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

    # Build virtual dicts (without recur, to avoid re-expansion)
    result = []
    for d in occurrences:
        if d == base:
            continue  # skip the original date, caller handles it
        vi = dict(item)
        vi["date"] = d.isoformat()
        if duration is not None:
            vi["end"] = (d + duration).isoformat()
        vi["_virtual"] = True  # marker: not a real entry
        result.append(vi)
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
            elif not dated_only and start <= today <= end and not t.get("date"):
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

        events = []
        for e in data["events"]:
            if _event_overlaps(e, start, end):
                events.append(e)
            # Expand recurring events into virtual occurrences
            if e.get("recur") and e.get("date"):
                events.extend(_expand_recurrences(e, start, end))

        milestones = []
        for m in data["milestones"]:
            if m["status"] != "pending":
                continue
            if m.get("date") and _in_range(m["date"], start, end):
                milestones.append(m)
            elif not dated_only and start <= today <= end and not m.get("date"):
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


# ── Summary view ──────────────────────────────────────────────────────────────

def _print_summary(dirs, start: date, end: date, markdown: bool = False) -> int:
    """Print a per-project summary table for the given period."""
    today = date.today()
    is_single_day = start == end

    if is_single_day:
        header = f"AGENDA RESUMEN — {start.isoformat()}"
        if start == today:
            header += " (hoy)"
    else:
        days = (end - start).days + 1
        header = f"AGENDA RESUMEN — {start.isoformat()} → {end.isoformat()}  ({days}d)"

    # Collect full data (including undated) per project
    collected = _collect_data(dirs, start, end, dated_only=False)

    if not collected:
        print(header)
        print("─" * 56)
        print("\nSin actividad programada.")
        return 0

    rows = []
    for project_dir, tasks, events, milestones in collected:
        # Dates from all dated items
        all_dates = []
        for t in tasks:
            if t.get("date"):
                all_dates.append(t["date"])
        for e in events:
            if e.get("date"):
                all_dates.append(e["date"])
        for m in milestones:
            if m.get("date"):
                all_dates.append(m["date"])

        first = min(all_dates) if all_dates else ""
        last = max(all_dates) if all_dates else ""

        n_tasks = len(tasks)
        n_events = len(events)
        n_ms = len(milestones)
        n_undated = sum(1 for t in tasks if not t.get("date")) + \
                    sum(1 for m in milestones if not m.get("date"))

        proj_link = _project_link(project_dir)
        proj_name = project_dir.name

        rows.append({
            "name": proj_name, "link": proj_link,
            "first": first, "last": last,
            "tasks": n_tasks, "events": n_events,
            "ms": n_ms, "undated": n_undated,
        })

    if markdown:
        lines = [f"# {header}", ""]
        lines.append("| Proyecto | Primera | Última | Tareas | Hitos | Eventos | Sin fecha |")
        lines.append("|----------|---------|--------|-------:|------:|--------:|----------:|")
        for r in rows:
            lines.append(
                f"| {r['link']} | {r['first']} | {r['last']} "
                f"| {r['tasks']} | {r['ms']} | {r['events']} | {r['undated']} |"
            )
        lines.append("")
        totals = {k: sum(r[k] for r in rows) for k in ("tasks", "events", "ms", "undated")}
        parts = []
        if totals["tasks"]:
            parts.append(f"{totals['tasks']} tarea{'s' if totals['tasks'] != 1 else ''}")
        if totals["events"]:
            parts.append(f"{totals['events']} evento{'s' if totals['events'] != 1 else ''}")
        if totals["ms"]:
            parts.append(f"{totals['ms']} hito{'s' if totals['ms'] != 1 else ''}")
        lines.append(" · ".join(parts) if parts else "Sin actividad programada.")
        print("\n".join(lines))
    else:
        lines = [header, "─" * 56, ""]
        # Column widths
        name_w = max(len(r["name"]) for r in rows)
        name_w = max(name_w, 8)  # min "Proyecto"
        hdr = (f"  {'Proyecto':<{name_w}}  {'Primera':>10}  {'Última':>10}"
               f"  {'Tar':>3}  {'Hit':>3}  {'Ev':>3}  {'S/F':>3}")
        lines.append(hdr)
        lines.append(f"  {'─' * name_w}  {'─' * 10}  {'─' * 10}"
                     f"  {'─' * 3}  {'─' * 3}  {'─' * 3}  {'─' * 3}")
        for r in rows:
            lines.append(
                f"  {r['name']:<{name_w}}  {r['first']:>10}  {r['last']:>10}"
                f"  {r['tasks']:>3}  {r['ms']:>3}  {r['events']:>3}  {r['undated']:>3}"
            )
        lines.append("")
        lines.append("─" * 56)
        totals = {k: sum(r[k] for r in rows) for k in ("tasks", "events", "ms", "undated")}
        parts = []
        if totals["tasks"]:
            parts.append(f"{totals['tasks']} tarea{'s' if totals['tasks'] != 1 else ''}")
        if totals["events"]:
            parts.append(f"{totals['events']} evento{'s' if totals['events'] != 1 else ''}")
        if totals["ms"]:
            parts.append(f"{totals['ms']} hito{'s' if totals['ms'] != 1 else ''}")
        lines.append(" · ".join(parts) if parts else "Sin actividad programada.")
        print("\n".join(lines))

    return 0


# ── List view ─────────────────────────────────────────────────────────────────

def run_agenda(
    projects: Optional[list] = None,
    date_str: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    no_cal: bool = False,
    markdown: bool = False,
    dated_only: bool = False,
    order: str = "date",
    summary: bool = False,
) -> int:
    """Print agenda (tasks/events/milestones) for a day or period.

    Calendar grid is shown by default above the list.  Use no_cal=True to suppress.
    """
    start, end = _parse_period(date_str, date_from, date_to)
    dirs = _resolve_dirs(projects)
    if projects and not dirs:
        return 1

    if summary:
        return _print_summary(dirs, start, end, markdown=markdown)

    today = date.today()
    is_single_day = start == end

    if is_single_day:
        header = f"AGENDA — {start.isoformat()}"
        if start == today:
            header += " (hoy)"
    else:
        days = (end - start).days + 1
        header = f"AGENDA — {start.isoformat()} → {end.isoformat()}  ({days}d)"

    # Calendar grid (default on, unless --no-cal)
    if not no_cal:
        cal_end = _cap_end(start, end)
        if markdown:
            _print_calendar_grid_md(dirs, start, cal_end)
        else:
            _print_calendar_grid_ansi(dirs, start, cal_end)

    lines = [header, "─" * 56]

    collected = _collect_data(dirs, start, end, dated_only=dated_only)

    if order == "date":
        lines.extend(_format_by_date(collected, markdown=markdown, dated_only=dated_only))
    elif order == "type":
        lines.extend(_format_by_type(collected, markdown=markdown, dated_only=dated_only))
    else:
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
                            (project_dir, "[ ]", t["desc"], t["date"]))
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
            # Collect the original event + any virtual recurrences
            ev_instances = [e]
            if e.get("recur") and e.get("date"):
                ev_instances.extend(_expand_recurrences(e, start, end))
            for ei in ev_instances:
                try:
                    ev_start = date.fromisoformat(ei["date"])
                    ev_end = ev_start
                    if ei.get("end"):
                        try:
                            ev_end = date.fromisoformat(ei["end"])
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
                            (project_dir, "🏁", m["desc"], m["date"]))
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


# ── Plain calendar (no agenda data) ──────────────────────────────────────────

def _parse_cal_period(date_str, date_from, date_to):
    """Return (start, end) for `cal`.  Default is the current month."""
    today = date.today()

    def _start(s):
        if "W" in s:
            y, w = int(s[:4]), int(s.split("W")[1])
            return date.fromisocalendar(y, w, 1)
        if len(s) == 7:
            y, m = int(s[:4]), int(s[5:7])
            return date(y, m, 1)
        return date.fromisoformat(s)

    def _end(s):
        if "W" in s:
            y, w = int(s[:4]), int(s.split("W")[1])
            return date.fromisocalendar(y, w, 7)
        if len(s) == 7:
            y, m = int(s[:4]), int(s[5:7])
            return date(y, m, _cal.monthrange(y, m)[1])
        return date.fromisoformat(s)

    if date_from or date_to:
        s = _start(date_from) if date_from else date(today.year, today.month, 1)
        e = _end(date_to) if date_to else date(today.year, today.month, _cal.monthrange(today.year, today.month)[1])
        return s, e
    if date_str:
        if "W" in date_str:
            return _start(date_str), _end(date_str)
        if len(date_str) == 7:
            y, m = int(date_str[:4]), int(date_str[5:7])
            return date(y, m, 1), date(y, m, _cal.monthrange(y, m)[1])
        d = date.fromisoformat(date_str)
        return d, d
    # default: current month
    return date(today.year, today.month, 1), date(today.year, today.month, _cal.monthrange(today.year, today.month)[1])


def _plain_calendar_ansi(start: date, end: date) -> None:
    """Print a plain calendar grid (no agenda data) using ANSI codes."""
    today = date.today()
    end = _cap_end(start, end)
    lines = []

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
                    else:
                        cell = label
                    row += cell + "  "

                lines.append(row)

        current = date(y, m + 1, 1) if m < 12 else date(y + 1, 1, 1)

    lines.append("")
    lines.append(f"  {_BG_TODAY} hoy {_RESET}")
    lines.append("")
    print("\n".join(lines))


def _plain_calendar_md(start: date, end: date) -> None:
    """Print a plain calendar grid in markdown (no agenda data)."""
    today = date.today()
    end = _cap_end(start, end)
    lines = []

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
                    else:
                        cells.append(str(day))

                lines.append("| " + " | ".join(cells) + " |")

            lines.append("")

        current = date(y, m + 1, 1) if m < 12 else date(y + 1, 1, 1)

    lines.append("**[N]** hoy")
    lines.append("")
    print("\n".join(lines))


def run_cal(
    date_str: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    markdown: bool = False,
) -> int:
    """Print a plain calendar grid (no agenda data)."""
    start, end = _parse_cal_period(date_str, date_from, date_to)
    if markdown:
        _plain_calendar_md(start, end)
    else:
        _plain_calendar_ansi(start, end)
    return 0


_DAY_NAMES = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]


def _item_time_key(item):
    """Return a sort key: (has_time, time_str).  Items with time sort first."""
    t = item.get("time") or ""
    if t:
        return (0, t.split("-")[0])   # start time for ranges like 09:00-10:00
    return (1, "")


def _format_item_line(kind, item, proj_tag, markdown=False):
    """Format a single item line with project tag for date-ordered view.

    proj_tag is a pre-built string: markdown link or plain [name].
    """
    today = date.today()
    pfx = "- " if markdown else "  "
    check = "☐" if markdown else "[ ]"

    if kind == "event":
        time_s = f" {item['time']}" if item.get("time") else ""
        end_s = f" → {item['end']}" if item.get("end") else ""
        recur_s = ""
        if item.get("recur"):
            recur_s = f" [recur:{item['recur']}"
            if item.get("until"):
                recur_s += f":{item['until']}"
            recur_s += "]"
        return f"{pfx}📅{time_s} — {item['desc']}{end_s}{recur_s}  {proj_tag}"

    elif kind == "milestone":
        overdue = ""
        if item.get("date"):
            try:
                if date.fromisoformat(item["date"]) < today:
                    overdue = " ⚠️"
            except ValueError:
                pass
        return f"{pfx}🏁 {item['desc']}{overdue}  {proj_tag}"

    else:  # task
        overdue = ""
        if item.get("date"):
            try:
                if date.fromisoformat(item["date"]) < today:
                    overdue = " ⚠️"
            except ValueError:
                pass
        recur_s = ""
        if item.get("recur"):
            recur_s = f" [recur:{item['recur']}"
            if item.get("until"):
                recur_s += f":{item['until']}"
            recur_s += "]"
        return f"{pfx}{check} {item['desc']}{recur_s}{overdue}  {proj_tag}"


def _format_by_date(collected, markdown=False, dated_only=False):
    """Format agenda items grouped by date, then by hour within each date.

    Order within each day: items with time first (sorted by time),
    then items without time.  Within each time slot: milestones, events, tasks.
    Undated items go in a final "Sin fecha" block (unless dated_only).
    """
    # Flatten all items with project info
    # Each entry: (date_str|None, kind, item, proj_name)
    all_items = []
    for project_dir, tasks, events, milestones in collected:
        tag = _project_link(project_dir) if markdown else f"[{project_dir.name}]"
        for e in events:
            all_items.append((e.get("date"), "event", e, tag))
        for m in milestones:
            all_items.append((m.get("date"), "milestone", m, tag))
        for t in tasks:
            all_items.append((t.get("date"), "task", t, tag))

    # Split into dated and undated
    dated = [(d, k, it, p) for d, k, it, p in all_items if d]
    undated = [(d, k, it, p) for d, k, it, p in all_items if not d]

    # Group dated items by date
    by_date = {}
    for d_str, kind, item, proj in dated:
        by_date.setdefault(d_str, []).append((kind, item, proj))

    # Kind priority: milestone=0, event=1, task=2
    kind_order = {"milestone": 0, "event": 1, "task": 2}

    lines = []
    for d_str in sorted(by_date.keys()):
        try:
            d = date.fromisoformat(d_str)
            day_name = _DAY_NAMES[d.weekday()]
            day_label = f"{d_str} ({day_name})"
        except ValueError:
            day_label = d_str

        lines.append("")
        if markdown:
            lines.append(f"**{day_label}**")
        else:
            lines.append(f"{_BOLD}{day_label}{_RESET}")

        items = by_date[d_str]
        # Sort: items with time first (by time), then without time; within group by kind
        items.sort(key=lambda x: (
            _item_time_key(x[1]),
            kind_order.get(x[0], 9),
        ))

        # Group by hour for display
        current_time = None
        for kind, item, proj in items:
            item_time = item.get("time")
            if item_time and item_time != current_time:
                current_time = item_time
                hour_label = item_time.split("-")[0]  # show start time for ranges
                lines.append(f"  {_DIM}{hour_label}{_RESET}" if not markdown else f"  *{hour_label}*")
            lines.append(_format_item_line(kind, item, proj, markdown=markdown))

    # Undated block
    if undated and not dated_only:
        lines.append("")
        if markdown:
            lines.append("**Sin fecha**")
        else:
            lines.append(f"{_BOLD}Sin fecha{_RESET}")

        # Sort: milestones, events, tasks
        undated.sort(key=lambda x: kind_order.get(x[1], 9))
        for _, kind, item, proj in undated:
            lines.append(_format_item_line(kind, item, proj, markdown=markdown))

    return lines


def _format_by_type(collected, markdown=False, dated_only=False):
    """Format agenda items grouped by type (events, milestones, tasks),
    within each type sorted by date.  Undated items go at the end of their group.
    """
    # Flatten all items
    all_items = []
    for project_dir, tasks, events, milestones in collected:
        tag = _project_link(project_dir) if markdown else f"[{project_dir.name}]"
        for e in events:
            all_items.append(("event", e, tag))
        for m in milestones:
            all_items.append(("milestone", m, tag))
        for t in tasks:
            all_items.append(("task", t, tag))

    type_groups = [
        ("📅 Eventos",  [x for x in all_items if x[0] == "event"]),
        ("🏁 Hitos",    [x for x in all_items if x[0] == "milestone"]),
        ("[ ] Tareas",  [x for x in all_items if x[0] == "task"]),
    ]

    lines = []
    for label, items in type_groups:
        if not items:
            continue

        # Split dated / undated
        dated = [(k, it, p) for k, it, p in items if it.get("date")]
        undated = [(k, it, p) for k, it, p in items if not it.get("date")]

        if dated_only and not dated:
            continue

        lines.append("")
        if markdown:
            lines.append(f"**{label}**")
        else:
            lines.append(f"{_BOLD}{label}{_RESET}")

        # Dated items sorted by date then time
        for kind, item, proj in sorted(dated, key=lambda x: (
            x[1].get("date", ""), _item_time_key(x[1])
        )):
            d_str = item["date"]
            try:
                d = date.fromisoformat(d_str)
                day_name = _DAY_NAMES[d.weekday()][:3]
                date_prefix = f"{d_str} ({day_name})"
            except ValueError:
                date_prefix = d_str
            time_s = f" {item['time']}" if item.get("time") else ""
            line = _format_item_line(kind, item, proj, markdown=markdown)
            # Prepend date for context
            pfx = "- " if markdown else "  "
            lines.append(f"{pfx}{date_prefix}{time_s}  {line.strip()}")

        # Undated items
        if undated and not dated_only:
            for kind, item, proj in undated:
                lines.append(_format_item_line(kind, item, proj, markdown=markdown))

    return lines


def _format_detail_lines(collected, markdown=False):
    """Format the detail list of tasks/events/milestones (shared by calendar views)."""
    today = date.today()
    lines = []
    for project_dir, tasks, events, milestones in collected:
        lines.append("")
        lines.append(f"**{_project_link(project_dir)}**" if markdown else f"[{project_dir.name}]")

        pfx = "- " if markdown else "  "

        for e in sorted(events, key=lambda x: (x["date"], x.get("time") or "")):
            time_s = f" {e['time']}" if e.get("time") else ""
            end_s = f" → {e['end']}" if e.get("end") else ""
            recur_s = ""
            if e.get("recur"):
                recur_s = f" [recur:{e['recur']}"
                if e.get("until"):
                    recur_s += f":{e['until']}"
                recur_s += "]"
            lines.append(f"{pfx}📅 {e['date']}{time_s} — {e['desc']}{end_s}{recur_s}")

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


def _print_calendar_grid_ansi(dirs: list, start: date, end: date) -> None:
    """Print only the calendar grid (no detail list below). Used by run_agenda."""
    today = date.today()
    task_dates, event_dates, ms_dates, overdue_dates, overdue_items = \
        _collect_calendar_dates(dirs, start, end)

    lines = []
    if overdue_items:
        lines.append(f"  {_RED}{_BOLD}⚠️  Vencidas{_RESET}")
        for proj_dir, kind, desc, d_str in sorted(overdue_items, key=lambda x: x[3]):
            lines.append(f"  {_RED}{kind} {desc} ({d_str}) — {proj_dir.name}{_RESET}")
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
    lines.append("")
    print("\n".join(lines))


def _print_calendar_grid_md(dirs: list, start: date, end: date) -> None:
    """Print only the calendar grid in markdown (no detail list). Used by run_agenda."""
    today = date.today()
    task_dates, event_dates, ms_dates, overdue_dates, overdue_items = \
        _collect_calendar_dates(dirs, start, end)

    lines = []
    if overdue_items:
        lines.append("### ⚠️ Vencidas")
        lines.append("")
        for proj_dir, kind, desc, d_str in sorted(overdue_items, key=lambda x: x[3]):
            display_kind = "☐" if kind == "[ ]" else kind
            proj_tag = _project_link(proj_dir)
            lines.append(f"- {display_kind} {desc} ({d_str}) — {proj_tag}")
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

    lines.append("**[N]** hoy · 📅 evento · ✅ tarea · 🏁 hito · ⚠️ vencida")
    lines.append("")
    print("\n".join(lines))


def _print_calendar_ansi(dirs: list, start: date, end: date, dated_only: bool = False) -> int:
    """Print a colored calendar grid using ANSI codes (for terminal)."""
    today = date.today()
    end = _cap_end(start, end)
    task_dates, event_dates, ms_dates, overdue_dates, overdue_items = \
        _collect_calendar_dates(dirs, start, end)

    lines = []
    if overdue_items:
        lines.append(f"  {_RED}{_BOLD}⚠️  Vencidas{_RESET}")
        for proj_dir, kind, desc, d_str in sorted(overdue_items, key=lambda x: x[3]):
            lines.append(f"  {_RED}{kind} {desc} ({d_str}) — {proj_dir.name}{_RESET}")
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
    collected = _collect_data(dirs, start, end, dated_only=dated_only)
    if collected:
        lines.append("")
        lines.append("─" * 56)
        lines.extend(_format_detail_lines(collected, markdown=False))

    lines.append("")
    print("\n".join(lines))
    return 0


# ── Calendar: Markdown version (for Typora / --open / --log) ─────────────────

def _print_calendar_md(dirs: list, start: date, end: date, dated_only: bool = False) -> int:
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
        for proj_dir, kind, desc, d_str in sorted(overdue_items, key=lambda x: x[3]):
            # Replace [ ] with ☐ to prevent clickable checkboxes in Typora
            display_kind = "☐" if kind == "[ ]" else kind
            proj_tag = _project_link(proj_dir)
            lines.append(f"- {display_kind} {desc} ({d_str}) — {proj_tag}")
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
    collected = _collect_data(dirs, start, end, dated_only=dated_only)
    if collected:
        lines.append("")
        lines.append("---")
        lines.extend(_format_detail_lines(collected, markdown=True))

    lines.append("")
    print("\n".join(lines))
    return 0

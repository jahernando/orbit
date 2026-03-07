"""orbit calendar week/month/year — human-readable calendar views."""

import re
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

from core.log import find_proyecto_file, PROJECTS_DIR
from core.tasks import load_project_meta
from core.open import open_file

MISION_LOG_DIR = Path(__file__).parent.parent / "☀️mision-log"

DIAS_ES   = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
MESES_ES  = ["", "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
             "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]


# ── data collection ───────────────────────────────────────────────────────────

def _collect_events(start: date, end: date) -> dict:
    """Return {date: [{"time": str|None, "kind": "task"|"ring", "desc": str, "project": str}]}"""
    events: dict = {}

    def _add(d, entry):
        events.setdefault(d, []).append(entry)

    if not PROJECTS_DIR.exists():
        return events

    for project_dir in sorted(PROJECTS_DIR.iterdir()):
        if not project_dir.is_dir():
            continue
        proyecto_path = find_proyecto_file(project_dir)
        if not proyecto_path or not proyecto_path.exists():
            continue
        meta = load_project_meta(proyecto_path)
        pname = project_dir.name

        # tasks with due date
        for task in meta.get("tasks", []):
            if not task.get("due") or task.get("done"):
                continue
            try:
                d = date.fromisoformat(task["due"])
            except ValueError:
                continue
            if start <= d <= end:
                _add(d, {"time": None, "kind": "task", "desc": task["description"], "project": pname})

        # rings (reminders)
        ring_re = re.compile(r"^- \[.\] (\d{4}-\d{2}-\d{2}) (\d{2}:\d{2}) (.+?)(\s+@\S+)?\s*$")
        for line in proyecto_path.read_text().splitlines():
            m = ring_re.match(line.strip())
            if not m:
                continue
            try:
                d = date.fromisoformat(m.group(1))
            except ValueError:
                continue
            if start <= d <= end:
                _add(d, {"time": m.group(2), "kind": "ring", "desc": m.group(3).strip(), "project": pname})

    # sort each day's events: rings first (by time), then tasks
    for d in events:
        events[d].sort(key=lambda e: (e["kind"] == "task", e["time"] or ""))
    return events


def _fmt_event(e: dict) -> str:
    icon = "⏰" if e["kind"] == "ring" else "✅"
    time = f" {e['time']}" if e["time"] else ""
    return f"- {icon}{time}  {e['desc']}  _(→ {e['project']})_"


# ── week ──────────────────────────────────────────────────────────────────────

def _week_key(d: date) -> str:
    return d.strftime("%G-W%V")


def run_calendar_week(date_str: Optional[str], open_after: bool, editor: str) -> int:
    ref    = date.fromisoformat(date_str) if date_str else date.today()
    monday = ref - timedelta(days=ref.weekday())
    sunday = monday + timedelta(days=6)
    wkey   = _week_key(monday)

    events = _collect_events(monday, sunday)

    lines = [f"# Semana {wkey}  ({monday.strftime('%d %b')} — {sunday.strftime('%d %b %Y')})", ""]

    for i in range(7):
        d     = monday + timedelta(days=i)
        label = DIAS_ES[i]
        marker = " ·" if d == date.today() else ""
        lines.append(f"## {label} {d.isoformat()}{marker}")
        day_events = events.get(d, [])
        if day_events:
            lines.extend(_fmt_event(e) for e in day_events)
        else:
            lines.append("_Sin tareas ni recordatorios_")
        lines.append("")

    return _output(lines, MISION_LOG_DIR / "calendar-week.md", open_after, editor)


# ── month ─────────────────────────────────────────────────────────────────────

def run_calendar_month(date_str: Optional[str], open_after: bool, editor: str) -> int:
    import calendar as _cal
    if date_str and len(date_str) == 7:
        y, m = int(date_str[:4]), int(date_str[5:7])
    elif date_str:
        ref = date.fromisoformat(date_str)
        y, m = ref.year, ref.month
    else:
        today = date.today()
        y, m  = today.year, today.month

    first = date(y, m, 1)
    days_in_month = _cal.monthrange(y, m)[1]
    last = date(y, m, days_in_month)

    events = _collect_events(first, last)

    # Grid
    lines = [f"# {MESES_ES[m]} {y}", ""]
    lines.append("| L | M | X | J | V | S | D |")
    lines.append("|---|---|---|---|---|---|---|")

    week_day_start = first.weekday()  # 0=Mon
    row = ["   "] * week_day_start
    for day_n in range(1, days_in_month + 1):
        d   = date(y, m, day_n)
        tag = f"**{day_n:2d}**" if d in events else f"{day_n:2d} "
        row.append(tag)
        if len(row) == 7:
            lines.append("| " + " | ".join(row) + " |")
            row = []
    if row:
        row += ["   "] * (7 - len(row))
        lines.append("| " + " | ".join(row) + " |")

    lines.append("")

    # Event list
    event_days = sorted(d for d in events if events[d])
    if event_days:
        lines.append("---")
        lines.append("")
        for d in event_days:
            marker = " ·" if d == date.today() else ""
            lines.append(f"## {d.isoformat()}  {DIAS_ES[d.weekday()]}{marker}")
            lines.extend(_fmt_event(e) for e in events[d])
            lines.append("")
    else:
        lines.append("_Sin tareas ni recordatorios este mes._")

    return _output(lines, MISION_LOG_DIR / "calendar-month.md", open_after, editor)


# ── year ──────────────────────────────────────────────────────────────────────

def run_calendar_year(date_str: Optional[str], open_after: bool, editor: str) -> int:
    y = int(date_str[:4]) if date_str else date.today().year

    start = date(y, 1, 1)
    end   = date(y, 12, 31)
    events = _collect_events(start, end)

    lines = [f"# Calendario {y}", ""]

    for m in range(1, 13):
        import calendar as _cal
        days_in_month = _cal.monthrange(y, m)[1]
        month_days    = [date(y, m, d) for d in range(1, days_in_month + 1)]
        month_events  = {d: events[d] for d in month_days if d in events}

        n_tasks = sum(1 for evs in month_events.values() for e in evs if e["kind"] == "task")
        n_rings = sum(1 for evs in month_events.values() for e in evs if e["kind"] == "ring")

        parts = []
        if n_tasks: parts.append(f"✅ {n_tasks}")
        if n_rings: parts.append(f"⏰ {n_rings}")
        summary = "  —  " + "  ".join(parts) if parts else ""

        lines.append(f"## {MESES_ES[m]}{summary}")

        for d, evs in sorted(month_events.items()):
            marker = " ·" if d == date.today() else ""
            lines.append(f"### {d.isoformat()}  {DIAS_ES[d.weekday()]}{marker}")
            lines.extend(_fmt_event(e) for e in evs)
            lines.append("")

        if not month_events:
            lines.append("_Sin tareas ni recordatorios._")
            lines.append("")

    return _output(lines, MISION_LOG_DIR / "calendar-year.md", open_after, editor)


# ── output ────────────────────────────────────────────────────────────────────

def _output(lines: list, dest: Path, open_after: bool, editor: str) -> int:
    text = "\n".join(lines) + "\n"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(text)
    print(f"✓ {dest.name}")
    if open_after:
        open_file(dest, editor)
    return 0

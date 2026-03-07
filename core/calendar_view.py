"""orbit calendar week/month/year — human-readable calendar views (tasks only)."""

import re
import calendar as _cal
import unicodedata
from datetime import date, timedelta
from pathlib import Path
from typing import Optional, Tuple

from core.log import find_proyecto_file, PROJECTS_DIR
from core.tasks import load_project_meta
from core.open import open_file

MISION_LOG_DIR = Path(__file__).parent.parent / "☀️mision-log"

DIAS_ES  = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
MESES_ES = ["", "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
            "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]

_MONTH_NAMES_ES = {unicodedata.normalize("NFD", m.lower()).encode("ascii","ignore").decode(): i
                   for i, m in enumerate(MESES_ES) if i}
_MONTH_NAMES_EN = {"january":1,"february":2,"march":3,"april":4,"may":5,"june":6,
                   "july":7,"august":8,"september":9,"october":10,"november":11,"december":12}


# ── date parsers ──────────────────────────────────────────────────────────────

def _norm(s: str) -> str:
    return unicodedata.normalize("NFD", s.lower()).encode("ascii", "ignore").decode().strip()


def _parse_week_ref(expr: Optional[str]) -> date:
    """Accept: None→today, '10'→week 10 of current year, '2026-W10', or YYYY-MM-DD."""
    if not expr:
        return date.today()
    s = expr.strip()
    # bare number → week N of current year
    if re.match(r'^\d{1,2}$', s):
        week_n = int(s)
        jan4   = date(date.today().year, 1, 4)   # ISO week 1 always contains Jan 4
        monday = jan4 + timedelta(weeks=week_n - jan4.isocalendar()[1],
                                  days=-jan4.weekday())
        return monday
    # YYYY-Wnn
    m = re.match(r'^(\d{4})-W(\d{2})$', s)
    if m:
        year, week_n = int(m.group(1)), int(m.group(2))
        jan4   = date(year, 1, 4)
        monday = jan4 + timedelta(weeks=week_n - jan4.isocalendar()[1],
                                  days=-jan4.weekday())
        return monday
    # YYYY-MM-DD
    try:
        return date.fromisoformat(s)
    except ValueError:
        pass
    return date.today()


def _parse_month_ref(expr: Optional[str]) -> Tuple[int, int]:
    """Accept: None→today, 'enero'/'march'/'3'/'2026-03'/'2026-03-15'. Returns (year, month)."""
    if not expr:
        t = date.today(); return t.year, t.month
    s = expr.strip()
    n = _norm(s)
    # month name in Spanish
    if n in _MONTH_NAMES_ES:
        return date.today().year, _MONTH_NAMES_ES[n]
    # month name in English
    if n in _MONTH_NAMES_EN:
        return date.today().year, _MONTH_NAMES_EN[n]
    # bare month number 1-12
    if re.match(r'^\d{1,2}$', s) and 1 <= int(s) <= 12:
        return date.today().year, int(s)
    # YYYY-MM
    m = re.match(r'^(\d{4})-(\d{2})$', s)
    if m:
        return int(m.group(1)), int(m.group(2))
    # YYYY-MM-DD
    try:
        d = date.fromisoformat(s); return d.year, d.month
    except ValueError:
        pass
    t = date.today(); return t.year, t.month


def _parse_year_ref(expr: Optional[str]) -> int:
    if not expr:
        return date.today().year
    s = expr.strip()
    if re.match(r'^\d{4}$', s):
        return int(s)
    try:
        return date.fromisoformat(s).year
    except ValueError:
        return date.today().year


# ── data collection (tasks only) ─────────────────────────────────────────────

def _collect_tasks(start: date, end: date) -> dict:
    """Return {date: [{"desc": str, "project": str}]} for pending tasks in range."""
    tasks: dict = {}
    if not PROJECTS_DIR.exists():
        return tasks
    for project_dir in sorted(PROJECTS_DIR.iterdir()):
        if not project_dir.is_dir():
            continue
        proyecto_path = find_proyecto_file(project_dir)
        if not proyecto_path or not proyecto_path.exists():
            continue
        meta  = load_project_meta(proyecto_path)
        pname = project_dir.name
        for task in meta.get("tasks", []):
            if not task.get("due") or task.get("done"):
                continue
            try:
                d = date.fromisoformat(task["due"])
            except ValueError:
                continue
            if start <= d <= end:
                tasks.setdefault(d, []).append({"desc": task["description"], "project": pname})
    return tasks


def _fmt_task(t: dict) -> str:
    return f"- ✅  {t['desc']}  _(→ {t['project']})_"


def _week_key(d: date) -> str:
    return d.strftime("%G-W%V")


# ── week ──────────────────────────────────────────────────────────────────────

def run_calendar_week(date_str: Optional[str], open_after: bool, editor: str) -> int:
    monday = _parse_week_ref(date_str)
    monday = monday - timedelta(days=monday.weekday())  # ensure Monday
    sunday = monday + timedelta(days=6)
    wkey   = _week_key(monday)

    tasks = _collect_tasks(monday, sunday)

    lines = [f"# Semana {wkey}  ({monday.strftime('%d %b')} — {sunday.strftime('%d %b %Y')})", ""]
    for i in range(7):
        d      = monday + timedelta(days=i)
        marker = " ·" if d == date.today() else ""
        lines.append(f"## {DIAS_ES[i]} {d.isoformat()}{marker}")
        day_tasks = tasks.get(d, [])
        if day_tasks:
            lines.extend(_fmt_task(t) for t in day_tasks)
        else:
            lines.append("_Sin tareas_")
        lines.append("")

    return _output(lines, MISION_LOG_DIR / "calendar-week.md", open_after, editor)


# ── month ─────────────────────────────────────────────────────────────────────

def run_calendar_month(date_str: Optional[str], open_after: bool, editor: str) -> int:
    y, m  = _parse_month_ref(date_str)
    first = date(y, m, 1)
    last  = date(y, m, _cal.monthrange(y, m)[1])
    tasks = _collect_tasks(first, last)

    lines = [f"# {MESES_ES[m]} {y}", ""]
    lines += ["| L | M | X | J | V | S | D |", "|---|---|---|---|---|---|---|"]

    row = ["   "] * first.weekday()
    for day_n in range(1, last.day + 1):
        d   = date(y, m, day_n)
        tag = f"**{day_n:2d}**" if d in tasks else f"{day_n:2d} "
        row.append(tag)
        if len(row) == 7:
            lines.append("| " + " | ".join(row) + " |")
            row = []
    if row:
        row += ["   "] * (7 - len(row))
        lines.append("| " + " | ".join(row) + " |")
    lines.append("")

    task_days = sorted(tasks)
    if task_days:
        lines.append("---")
        lines.append("")
        for d in task_days:
            marker = " ·" if d == date.today() else ""
            lines.append(f"## {d.isoformat()}  {DIAS_ES[d.weekday()]}{marker}")
            lines.extend(_fmt_task(t) for t in tasks[d])
            lines.append("")
    else:
        lines.append("_Sin tareas este mes._")

    return _output(lines, MISION_LOG_DIR / "calendar-month.md", open_after, editor)


# ── year ──────────────────────────────────────────────────────────────────────

def run_calendar_year(date_str: Optional[str], open_after: bool, editor: str) -> int:
    y     = _parse_year_ref(date_str)
    tasks = _collect_tasks(date(y, 1, 1), date(y, 12, 31))

    lines = [f"# Calendario {y}", ""]
    for m in range(1, 13):
        days_in_month = _cal.monthrange(y, m)[1]
        month_tasks   = {d: tasks[d] for d in
                         (date(y, m, n) for n in range(1, days_in_month + 1)) if d in tasks}
        n = sum(len(v) for v in month_tasks.values())
        summary = f"  —  ✅ {n}" if n else ""
        lines.append(f"## {MESES_ES[m]}{summary}")
        for d, ts in sorted(month_tasks.items()):
            marker = " ·" if d == date.today() else ""
            lines.append(f"### {d.isoformat()}  {DIAS_ES[d.weekday()]}{marker}")
            lines.extend(_fmt_task(t) for t in ts)
            lines.append("")
        if not month_tasks:
            lines.append("_Sin tareas._")
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

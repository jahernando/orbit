"""agenda.py — terminal planning view for a period.

orbit agenda [day|week|month] [--ring] [--date DATE]

  day   (default) — today's tasks + overdue + upcoming 7 days
  week            — this week's tasks grouped by day
  month           — this month's tasks grouped by week

Focus projects (from focus.json) are marked with 🎯.
Overdue tasks are flagged with ⚠️.
"""

import calendar as _cal
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

from core.log import PROJECTS_DIR, find_proyecto_file
from core.tasks import load_project_meta, is_overdue, parse_task
from core.focus import get_focus, _week_key, _period_key, focus_line

_DAY_ES = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
_MON_ES = ["", "enero", "febrero", "marzo", "abril", "mayo", "junio",
           "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]


# ── task collection ────────────────────────────────────────────────────────────

def _collect(start: date, end: date) -> dict:
    """Return {date: [{"desc", "project", "path", "time", "ring"}]} for pending tasks."""
    tasks: dict = {}
    if not PROJECTS_DIR.exists():
        return tasks
    for proj_dir in sorted(PROJECTS_DIR.iterdir()):
        if not proj_dir.is_dir():
            continue
        ppath = find_proyecto_file(proj_dir)
        if not ppath or not ppath.exists():
            continue
        meta = load_project_meta(ppath)
        for t in meta.get("tasks", []):
            if t.get("done") or not t.get("due"):
                continue
            try:
                d = date.fromisoformat(t["due"])
            except ValueError:
                continue
            if start <= d <= end:
                tasks.setdefault(d, []).append({
                    "desc":    t["description"],
                    "project": proj_dir.name,
                    "path":    ppath,
                    "time":    t.get("time"),
                    "ring":    t.get("ring", False),
                })
    return tasks


def _overdue(today: date) -> list:
    """Return tasks with due < today, sorted by date."""
    far_past = today - timedelta(days=365)
    yesterday = today - timedelta(days=1)
    by_date = _collect(far_past, yesterday)
    result = []
    for d in sorted(by_date):
        for t in by_date[d]:
            result.append({**t, "due": d})
    return result


# ── formatting helpers ─────────────────────────────────────────────────────────

def _focus_set(period: str, d: date) -> set:
    """Return lowercased set of focus project substrings for the period."""
    return {p.lower() for p in get_focus(period, d)}


def _proj_marker(proj_name: str, focus: set) -> str:
    """Return '🎯' if project is in focus, else '  '."""
    return "🎯" if any(f in proj_name.lower() for f in focus) else "  "


def _task_line(t: dict, focus: set, show_date: bool = False, show_overdue: bool = False) -> str:
    marker = _proj_marker(t["project"], focus)
    ring   = "🔔 " if t.get("ring") else ""
    time   = f" {t['time']}" if t.get("time") else ""
    warn   = "⚠️  " if show_overdue else ""
    date_  = f"{t['due'].isoformat()}  " if show_date and "due" in t else ""
    return f"   {marker} {warn}{ring}{date_}{t['project']} — {t['desc']}{time}"


# ── day view ───────────────────────────────────────────────────────────────────

def _format_day(d: date) -> str:
    focus     = _focus_set("day", d)
    focus_str = focus_line(get_focus("day", d))
    day_name  = _DAY_ES[d.weekday()]
    month_s   = _MON_ES[d.month]

    lines = [
        f"── AGENDA {d.isoformat()} ({day_name} {d.day} {month_s}) ──",
        "",
        f"🎯 Foco del día: {focus_str}",
        "",
    ]

    # Overdue
    od = _overdue(d)
    if od:
        lines.append("⚠️  VENCIDAS")
        for t in od:
            lines.append(_task_line(t, focus, show_date=True, show_overdue=True))
        lines.append("")

    # Today
    today_tasks = _collect(d, d).get(d, [])
    lines.append(f"📅 HOY ({day_name.upper()})")
    if today_tasks:
        for t in today_tasks:
            lines.append(_task_line(t, focus))
    else:
        lines.append("   (sin tareas)")
    lines.append("")

    # Upcoming 7 days
    tomorrow = d + timedelta(days=1)
    next7    = d + timedelta(days=7)
    upcoming = _collect(tomorrow, next7)
    if upcoming:
        lines.append("📆 PRÓXIMOS 7 DÍAS")
        for ud in sorted(upcoming):
            day_label = _DAY_ES[ud.weekday()]
            for t in upcoming[ud]:
                lines.append(_task_line({**t, "due": ud}, focus, show_date=True))
        lines.append("")

    return "\n".join(lines)


# ── week view ──────────────────────────────────────────────────────────────────

def _format_week(d: date) -> str:
    monday = d - timedelta(days=d.weekday())
    sunday = monday + timedelta(days=6)
    wkey   = _week_key(d)
    focus  = _focus_set("week", d)
    focus_str = "  ·  ".join(get_focus("week", d)) or "—"

    lines = [
        f"── AGENDA SEMANA {wkey} "
        f"({monday.strftime('%d %b')} — {sunday.strftime('%d %b %Y')}) ──",
        "",
        f"🎯 Foco de la semana: {focus_str}",
        "",
    ]

    # Overdue (shown once at top)
    od = _overdue(monday)
    if od:
        lines.append("⚠️  VENCIDAS")
        for t in od:
            lines.append(_task_line(t, focus, show_date=True, show_overdue=True))
        lines.append("")

    tasks = _collect(monday, sunday)
    today = date.today()

    for i in range(7):
        day = monday + timedelta(days=i)
        day_tasks = tasks.get(day, [])
        today_mark = " ◀ hoy" if day == today else ""
        lines.append(f"{_DAY_ES[day.weekday()]} {day.strftime('%d %b')}{today_mark}")
        if day_tasks:
            for t in day_tasks:
                lines.append(_task_line(t, focus))
        else:
            lines.append("   (nada)")
        lines.append("")

    return "\n".join(lines)


# ── month view ─────────────────────────────────────────────────────────────────

def _format_month(d: date) -> str:
    last_day = _cal.monthrange(d.year, d.month)[1]
    start    = date(d.year, d.month, 1)
    end      = date(d.year, d.month, last_day)
    focus    = _focus_set("month", d)
    focus_str = "  ·  ".join(get_focus("month", d)) or "—"
    month_label = f"{_MON_ES[d.month].capitalize()} {d.year}"

    lines = [
        f"── AGENDA {month_label.upper()} ──",
        "",
        f"🎯 Foco del mes: {focus_str}",
        "",
    ]

    # Overdue
    od = _overdue(start)
    if od:
        lines.append("⚠️  VENCIDAS")
        for t in od:
            lines.append(_task_line(t, focus, show_date=True, show_overdue=True))
        lines.append("")

    tasks = _collect(start, end)
    today = date.today()

    if not tasks:
        lines.append("   (sin tareas este mes)")
        return "\n".join(lines)

    # Group by ISO week
    weeks: dict = {}
    for td in sorted(tasks):
        wk = _week_key(td)
        weeks.setdefault(wk, []).append(td)

    for wk in sorted(weeks):
    # Week header: first and last day in the group within this month
        days_in_week = sorted(weeks[wk])
        first, last  = days_in_week[0], days_in_week[-1]
        header = f"Semana {wk}  ({first.strftime('%d')}–{last.strftime('%d %b')})"
        lines.append(header)
        for td in days_in_week:
            today_mark = " ◀ hoy" if td == today else ""
            for t in tasks[td]:
                lines.append(
                    _task_line({**t, "due": td}, focus, show_date=True) + today_mark
                )
        lines.append("")

    return "\n".join(lines)


# ── reminders ──────────────────────────────────────────────────────────────────

def _schedule_reminders(d: date) -> None:
    """Schedule @ring tasks in macOS Reminders.app (silently skip if unavailable)."""
    try:
        from core.reminders import schedule_today_reminders
        scheduled = schedule_today_reminders(d)
        if scheduled:
            print(f"🔔 {len(scheduled)} recordatorio(s) programado(s) en Reminders.app")
        else:
            print("🔔 Sin recordatorios para hoy")
    except Exception as e:
        print(f"⚠️  No se pudo acceder a Reminders.app: {e}")


# ── public API ─────────────────────────────────────────────────────────────────

def run_agenda(
    period: Optional[str]   = None,
    date_str: Optional[str] = None,
    ring: bool              = False,
    output: Optional[str]   = None,
) -> int:
    """Generate and print agenda for the given period."""
    d = date.fromisoformat(date_str) if date_str else date.today()
    p = period or "day"

    formatters = {
        "day":   _format_day,
        "week":  _format_week,
        "month": _format_month,
    }
    if p not in formatters:
        print(f"Error: periodo desconocido '{p}'. Usa day, week o month.")
        return 1

    text = formatters[p](d)

    if output:
        Path(output).write_text(text + "\n")
        print(f"✓ Agenda guardada en {output}")
    else:
        print(text)

    if ring and p == "day":
        _schedule_reminders(d)

    return 0

"""core/panel.py — daily dashboard: priority projects, agenda, activity.

  orbit panel [--open] [--append proyecto:nota]

Sections:
  1. Priority projects (alta + milestones this month, media + tasks today/overdue)
  2. Today's agenda (dated items)
  3. Today's activity (logbook entries)
"""

import calendar
from datetime import date
from pathlib import Path

from core.config import iter_project_dirs
from core.log import find_logbook_file, resolve_file
from core.project import _read_project_meta, _resolve_status, _is_new_project
from core.tasks import PRIORITY_MAP


# ── Priority scanning ─────────────────────────────────────────────────────────

def _scan_project_agenda(project_dir: Path):
    """Return (milestones_this_month, has_tasks_today, has_tasks_overdue).

    milestones_this_month is a list of (date_str, desc).
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
    for m in data["milestones"]:
        if m["status"] != "pending" or not m.get("date"):
            continue
        try:
            d = date.fromisoformat(m["date"])
            if today <= d <= month_end:
                milestones.append((m["date"], m["desc"]))
        except ValueError:
            pass

    has_tasks_today = False
    has_tasks_overdue = False
    for t in data["tasks"]:
        if t["status"] != "pending" or not t.get("date"):
            continue
        try:
            d = date.fromisoformat(t["date"])
            if d == today:
                has_tasks_today = True
            elif d < today:
                has_tasks_overdue = True
        except ValueError:
            pass

    return milestones, has_tasks_today, has_tasks_overdue


def _collect_priority_projects():
    """Return (alta, milestones, media).

    alta: list of (project_dir,) for explicit alta priority
    milestones: list of (project_dir, date_str, desc) — pending this month
    media: list of (project_dir, reason) — tasks today/overdue
    """
    alta = []
    milestones = []
    media = []

    for project_dir in iter_project_dirs():
        if not _is_new_project(project_dir):
            continue
        meta = _read_project_meta(project_dir)
        status_key, _, _ = _resolve_status(meta, project_dir)
        if status_key in ("sleeping", "paused"):
            continue

        prio = meta.get("prioridad", "media").lower()
        ms_list, has_tasks, has_overdue = _scan_project_agenda(project_dir)

        if prio == "alta":
            alta.append(project_dir)

        for ms_date, ms_desc in ms_list:
            milestones.append((project_dir, ms_date, ms_desc))

        if has_tasks or has_overdue:
            reasons = []
            if has_tasks:
                reasons.append("tareas hoy")
            if has_overdue:
                reasons.append("tareas vencidas")
            media.append((project_dir, ", ".join(reasons)))

    # Sort milestones by date
    milestones.sort(key=lambda x: x[1])

    return alta, milestones, media


# ── Agenda (markdown) ─────────────────────────────────────────────────────────

def _collect_agenda_today():
    """Collect today's dated agenda items. Returns list of (project_dir, items)."""
    from core.agenda_view import _collect_data

    today = date.today()
    dirs = [d for d in iter_project_dirs() if _is_new_project(d)]
    collected = _collect_data(dirs, today, today, dated_only=True)

    results = []
    for project_dir, tasks, events, milestones in collected:
        items = []
        for e in events:
            time_str = f" ⏰{e['time']}" if e.get("time") else ""
            items.append(f"- 📅 {e['desc']}{time_str}")
        for m in milestones:
            items.append(f"- 🏁 {m['desc']}")
        for t in tasks:
            overdue = ""
            if t.get("date"):
                try:
                    if date.fromisoformat(t["date"]) < today:
                        overdue = " ⚠️ vencida"
                except ValueError:
                    pass
            items.append(f"- ✅ {t['desc']}{overdue}")
        if items:
            results.append((project_dir, items))
    return results


# ── Activity ──────────────────────────────────────────────────────────────────

def _collect_activity_today():
    """Collect today's logbook entries. Returns list of (project_dir, entries)."""
    from core.stats import _scan_logbook

    today = date.today()
    results = []

    for project_dir in sorted(iter_project_dirs()):
        if not _is_new_project(project_dir):
            continue
        logbook_path = find_logbook_file(project_dir)
        if not logbook_path or not logbook_path.exists():
            continue

        _, entries, _, _ = _scan_logbook(logbook_path, today, today)
        if entries:
            results.append((project_dir, entries))

    return results


# ── Main ──────────────────────────────────────────────────────────────────────

def run_panel() -> int:
    """Print daily dashboard as markdown."""
    today = date.today()
    print(f"# Panel — {today.isoformat()} ({today.strftime('%A')})")

    # ── 1. Priority projects ──
    alta, milestones, media = _collect_priority_projects()

    print(f"\n## 🔴 Prioridad ({len(alta)})\n")
    if alta:
        for project_dir in alta:
            print(f"- **{project_dir.name}**")
    else:
        print("(ninguno)")

    print(f"\n## 🏁 Hitos este mes ({len(milestones)})\n")
    if milestones:
        for project_dir, ms_date, ms_desc in milestones:
            print(f"- **{ms_date}** — {ms_desc} ({project_dir.name})")
    else:
        print("(ninguno)")

    print(f"\n## 🔶 Urgente ({len(media)})\n")
    if media:
        for project_dir, reason in media:
            print(f"- **{project_dir.name}** — {reason}")
    else:
        print("(ninguno)")

    # ── 2. Agenda ──
    agenda = _collect_agenda_today()

    print(f"\n## 📅 Agenda\n")
    if agenda:
        for project_dir, items in agenda:
            print(f"**{project_dir.name}**")
            for item in items:
                print(item)
            print()
    else:
        print("(sin citas hoy)")

    # ── 3. Activity ──
    activity = _collect_activity_today()

    print(f"\n## 📝 Actividad\n")
    if activity:
        for project_dir, entries in activity:
            print(f"**{project_dir.name}**")
            for e in entries:
                print(f"- {e}")
            print()
    else:
        print("(sin actividad)")

    return 0

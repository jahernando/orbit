"""core/panel.py — daily dashboard: priority projects, agenda, activity.

  orbit panel [--open] [--append proyecto:nota]

Sections:
  1. Priority projects (alta + milestones this month + tasks today)
  2. Today's agenda (dated items)
  3. Today's activity (logbook entries)
"""

import calendar
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

from core.config import iter_project_dirs
from core.log import find_logbook_file, find_proyecto_file
from core.project import _read_project_meta, _resolve_status, _is_new_project
from core.tasks import PRIORITY_MAP


def _has_milestones_this_month(project_dir: Path) -> bool:
    """Check if project has pending milestones due this month."""
    from core.agenda_cmds import _read_agenda
    from core.log import resolve_file

    agenda_path = resolve_file(project_dir, "agenda")
    if not agenda_path.exists():
        return False

    data = _read_agenda(agenda_path)
    today = date.today()
    month_end = date(today.year, today.month,
                     calendar.monthrange(today.year, today.month)[1])

    for m in data["milestones"]:
        if m["status"] != "pending":
            continue
        if m.get("date"):
            try:
                d = date.fromisoformat(m["date"])
                if today <= d <= month_end:
                    return True
            except ValueError:
                pass
    return False


def _has_tasks_today(project_dir: Path) -> bool:
    """Check if project has pending tasks due today."""
    from core.agenda_cmds import _read_agenda
    from core.log import resolve_file

    agenda_path = resolve_file(project_dir, "agenda")
    if not agenda_path.exists():
        return False

    data = _read_agenda(agenda_path)
    today_str = date.today().isoformat()

    for t in data["tasks"]:
        if t["status"] != "pending":
            continue
        if t.get("date") == today_str:
            return True
    return False


def _collect_priority_projects():
    """Return (alta_projects, media_projects) as lists of (project_dir, meta, reason)."""
    alta = []
    media = []

    for project_dir in iter_project_dirs():
        if not _is_new_project(project_dir):
            continue
        meta = _read_project_meta(project_dir)
        status_key, _, _ = _resolve_status(meta, project_dir)
        if status_key in ("sleeping", "paused"):
            continue

        prio = meta.get("prioridad", "media").lower()
        has_ms = _has_milestones_this_month(project_dir)
        has_tasks = _has_tasks_today(project_dir)

        if prio == "alta" or has_ms:
            reason = []
            if prio == "alta":
                reason.append("prioridad alta")
            if has_ms:
                reason.append("hito este mes")
            alta.append((project_dir, meta, ", ".join(reason)))
        elif has_tasks:
            media.append((project_dir, meta, "tareas hoy"))

    return alta, media


def _print_agenda_today():
    """Print today's agenda (dated items only)."""
    from core.agenda_view import run_agenda
    run_agenda(dated_only=True, no_cal=True)


def _print_activity_today():
    """Print today's logbook entries across all active projects."""
    from core.stats import _scan_logbook

    today = date.today()
    found = False

    for project_dir in sorted(iter_project_dirs()):
        if not _is_new_project(project_dir):
            continue
        logbook_path = find_logbook_file(project_dir)
        if not logbook_path or not logbook_path.exists():
            continue

        _, entries, _, _ = _scan_logbook(logbook_path, today, today)
        if entries:
            if not found:
                found = True
            print(f"\n  **{project_dir.name}**")
            for e in entries:
                print(f"  {e}")

    if not found:
        print("  (sin actividad)")


def run_panel() -> int:
    """Print daily dashboard: priority projects, agenda, activity."""
    today = date.today()
    print(f"PANEL — {today.isoformat()} ({today.strftime('%A')})")
    print("=" * 54)

    # ── 1. Priority projects ──
    alta, media = _collect_priority_projects()

    print(f"\n🔴 PRIORIDAD ALTA ({len(alta)})")
    print("─" * 40)
    if alta:
        for project_dir, meta, reason in alta:
            emoji = PRIORITY_MAP.get("alta", "")
            print(f"  {emoji} {project_dir.name}  — {reason}")
    else:
        print("  (ninguno)")

    print(f"\n🔶 PRIORIDAD MEDIA ({len(media)})")
    print("─" * 40)
    if media:
        for project_dir, meta, reason in media:
            emoji = PRIORITY_MAP.get("media", "")
            print(f"  {emoji} {project_dir.name}  — {reason}")
    else:
        print("  (ninguno)")

    # ── 2. Agenda ──
    print(f"\n📅 AGENDA")
    print("─" * 40)
    _print_agenda_today()

    # ── 3. Activity ──
    print(f"\n📝 ACTIVIDAD")
    print("─" * 40)
    _print_activity_today()

    print()
    return 0

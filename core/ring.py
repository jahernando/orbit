"""ring.py — ring attribute resolution and reminder scheduling for new-format projects.

Ring attribute values on agenda.md tasks:
  [ring:1d]              → remind 1 day before due date at 09:00
  [ring:2h]              → remind 2 hours before (due date 09:00 if no time)
  [ring:YYYY-MM-DD HH:MM]→ remind at exact datetime

Schedule flow:
  1. Scan all new-format projects for pending tasks with ring attribute.
  2. Resolve ring datetime for each task.
  3. For tasks whose ring fires on *target* date, schedule via macOS Reminders.app.
  4. After scheduling, clear the ring attribute (one-shot) or leave it (recurring).
"""
import re
import subprocess
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Optional

from core.project import _is_new_project, PROJECTS_DIR
from core.agenda_cmds import _read_agenda, _write_agenda
from core.log import resolve_file

from core.config import ORBIT_HOME as ORBIT_DIR
REMINDERS_LIST  = "Orbit"

# ── Ring datetime resolution ───────────────────────────────────────────────────

def _parse_ring(ring: str) -> Optional[dict]:
    """Parse a ring attribute string into a structured dict.

    Returns one of:
      {"type": "relative", "unit": "d"|"h", "n": int}
      {"type": "absolute", "date": "YYYY-MM-DD", "time": "HH:MM"}
    Returns None if unparseable.
    """
    ring = ring.strip()

    # Exact datetime: YYYY-MM-DD HH:MM
    m = re.match(r"^(\d{4}-\d{2}-\d{2})\s+(\d{2}:\d{2})$", ring)
    if m:
        return {"type": "absolute", "date": m.group(1), "time": m.group(2)}

    # Relative: Nd or Nh
    m = re.match(r"^(\d+)([dh])$", ring)
    if m:
        return {"type": "relative", "unit": m.group(2), "n": int(m.group(1))}

    return None


def resolve_ring_datetime(due_date: str, ring: str,
                          due_time: Optional[str] = None) -> Optional[datetime]:
    """Compute the datetime when a ring reminder should fire.

    due_date : "YYYY-MM-DD"
    ring     : ring attribute value, e.g. "1d", "2h", "2026-04-01 09:00"
    due_time : optional "HH:MM" attached to the task
    """
    parsed = _parse_ring(ring)
    if parsed is None:
        return None

    if parsed["type"] == "absolute":
        try:
            d = date.fromisoformat(parsed["date"])
            h, m = map(int, parsed["time"].split(":"))
            return datetime(d.year, d.month, d.day, h, m)
        except ValueError:
            return None

    # Relative — compute anchor datetime
    try:
        base = date.fromisoformat(due_date)
    except ValueError:
        return None

    if due_time:
        try:
            h, m = map(int, due_time.split(":"))
            anchor = datetime(base.year, base.month, base.day, h, m)
        except ValueError:
            anchor = datetime(base.year, base.month, base.day, 9, 0)
    else:
        anchor = datetime(base.year, base.month, base.day, 9, 0)

    n = parsed["n"]
    if parsed["unit"] == "d":
        return anchor - timedelta(days=n)
    else:  # hours
        return anchor - timedelta(hours=n)


# ── AppleScript helper ─────────────────────────────────────────────────────────

def _schedule_reminder(title: str, project: str,
                        dt: datetime) -> bool:
    """Create a reminder in macOS Reminders.app. Returns True on success."""
    full_title = f"[{project}] {title}"
    script = f"""
tell application "Reminders"
    if not (exists list "{REMINDERS_LIST}") then
        make new list with properties {{name:"{REMINDERS_LIST}"}}
    end if
    set reminderDate to current date
    set year of reminderDate to {dt.year}
    set month of reminderDate to {dt.month}
    set day of reminderDate to {dt.day}
    set hours of reminderDate to {dt.hour}
    set minutes of reminderDate to {dt.minute}
    set seconds of reminderDate to 0
    tell list "{REMINDERS_LIST}"
        make new reminder with properties {{name:"{full_title}", remind me date:reminderDate, due date:reminderDate}}
    end tell
end tell
"""
    try:
        result = subprocess.run(["osascript", "-e", script],
                                capture_output=True, text=True)
        return result.returncode == 0
    except FileNotFoundError:
        return False


# ── Task ring collection ───────────────────────────────────────────────────────

def _tasks_ringing_on(project_dir: Path, target: date) -> list:
    """Return list of task dicts from agenda.md whose ring fires on *target* date."""
    data    = _read_agenda(resolve_file(project_dir, "agenda"))
    results = []

    for i, task in enumerate(data["tasks"]):
        if task["status"] != "pending":
            continue
        if not task.get("ring") or not task.get("date"):
            continue

        ring_dt = resolve_ring_datetime(task["date"], task["ring"])
        if ring_dt is None:
            continue
        if ring_dt.date() != target:
            continue

        results.append({
            "index":   i,
            "desc":    task["desc"],
            "due":     task["date"],
            "ring":    task["ring"],
            "recur":   task.get("recur"),
            "ring_dt": ring_dt,
        })

    return results


def _clear_ring(project_dir: Path, task_index: int) -> None:
    """Remove the ring attribute from a task after it has been scheduled."""
    data = _read_agenda(resolve_file(project_dir, "agenda"))
    if 0 <= task_index < len(data["tasks"]):
        data["tasks"][task_index]["ring"] = None
        _write_agenda(resolve_file(project_dir, "agenda"), data)


# ── Public API ─────────────────────────────────────────────────────────────────

def schedule_new_format_reminders(target: Optional[date] = None) -> list:
    """Scan all new-format projects for ring tasks firing on *target*.

    Schedules each via Reminders.app and clears the ring attribute on
    non-recurring tasks.  Returns list of scheduled task dicts.
    """
    target = target or date.today()
    if not PROJECTS_DIR.exists():
        return []

    scheduled = []
    for project_dir in sorted(PROJECTS_DIR.iterdir()):
        if not project_dir.is_dir() or not _is_new_project(project_dir):
            continue

        tasks = _tasks_ringing_on(project_dir, target)
        for t in tasks:
            ok = _schedule_reminder(t["desc"], project_dir.name, t["ring_dt"])
            if ok:
                print(f"  ⏰ {project_dir.name}  "
                      f"{t['ring_dt'].strftime('%H:%M')}  {t['desc']}")
                # Clear ring on one-shot tasks; keep it for recurring tasks
                if not t.get("recur"):
                    _clear_ring(project_dir, t["index"])
                scheduled.append({**t, "project": project_dir.name})
            else:
                print(f"  ⚠️  No se pudo programar: [{project_dir.name}] {t['desc']}")

    return scheduled

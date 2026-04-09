"""ring.py — ring attribute resolution and reminder scheduling for new-format projects.

Ring attribute values on agenda.md tasks:
  [ring:1d]              → remind 1 day before due date at 09:00
  [ring:2h]              → remind 2 hours before (due date 09:00 if no time)
  [ring:30m]             → remind 30 minutes before (uses task time or 09:00)
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

from core.project import _is_new_project
from core.config import iter_project_dirs, iter_federated_project_dirs, is_federated
from core.agenda_cmds import _read_agenda, _write_agenda, _next_occurrence
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

    # Time only: HH:MM → same day as due date (or today)
    m = re.match(r"^(\d{2}:\d{2})$", ring)
    if m:
        return {"type": "time_only", "time": m.group(1)}

    # Relative: Nd, Nh, or Nm
    m = re.match(r"^(\d+)([dhm])$", ring)
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

    if parsed["type"] == "time_only":
        try:
            base = date.fromisoformat(due_date)
        except ValueError:
            base = date.today()
        h, m = map(int, parsed["time"].split(":"))
        return datetime(base.year, base.month, base.day, h, m)

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
    elif parsed["unit"] == "h":
        return anchor - timedelta(hours=n)
    else:  # minutes
        return anchor - timedelta(minutes=n)


# ── AppleScript helper ─────────────────────────────────────────────────────────

_KIND_EMOJI = {"task": "✅", "milestone": "🏁", "event": "📅", "reminder": "💬"}

def _schedule_reminder(title: str, project: str,
                        dt: datetime, kind: str = "") -> bool:
    """Create a reminder in macOS Reminders.app. Returns True on success."""
    from core.config import ORBIT_PROMPT
    prefix = f"{_KIND_EMOJI[kind]} " if kind in _KIND_EMOJI else ""
    full_title = f"{ORBIT_PROMPT}[{project}] {prefix}{title}"
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


def _delete_reminder(title: str, project: str, kind: str = "") -> bool:
    """Delete a reminder from macOS Reminders.app by title. Returns True on success."""
    from core.config import ORBIT_PROMPT
    prefix = f"{_KIND_EMOJI[kind]} " if kind in _KIND_EMOJI else ""
    full_title = f"{ORBIT_PROMPT}[{project}] {prefix}{title}"
    # Escape quotes for AppleScript
    escaped = full_title.replace('"', '\\"')
    script = f"""
tell application "Reminders"
    if (exists list "{REMINDERS_LIST}") then
        tell list "{REMINDERS_LIST}"
            set matchingReminders to (every reminder whose name is "{escaped}" and completed is false)
            repeat with r in matchingReminders
                delete r
            end repeat
        end tell
    end if
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

        ring_dt = resolve_ring_datetime(task["date"], task["ring"],
                                        due_time=task.get("time"))
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


def _milestones_ringing_on(project_dir: Path, target: date) -> list:
    """Return list of milestone dicts from agenda.md whose ring fires on *target* date."""
    data = _read_agenda(resolve_file(project_dir, "agenda"))
    results = []

    for i, ms in enumerate(data["milestones"]):
        if ms["status"] != "pending":
            continue
        if not ms.get("ring") or not ms.get("date"):
            continue

        ring_dt = resolve_ring_datetime(ms["date"], ms["ring"],
                                        due_time=ms.get("time"))
        if ring_dt is None:
            continue
        if ring_dt.date() != target:
            continue

        results.append({
            "index":   i,
            "desc":    ms["desc"],
            "due":     ms["date"],
            "ring":    ms["ring"],
            "recur":   ms.get("recur"),
            "ring_dt": ring_dt,
        })

    return results


def _events_ringing_on(project_dir: Path, target: date) -> list:
    """Return list of event dicts from agenda.md whose ring fires on *target* date."""
    data = _read_agenda(resolve_file(project_dir, "agenda"))
    results = []

    for i, ev in enumerate(data["events"]):
        if not ev.get("ring") or not ev.get("date"):
            continue

        ev_time = ev.get("time", "").split("-")[0] if ev.get("time") else None
        ring_dt = resolve_ring_datetime(ev["date"], ev["ring"], due_time=ev_time)
        if ring_dt is None:
            continue
        if ring_dt.date() != target:
            continue

        results.append({
            "index":   i,
            "desc":    ev["desc"],
            "due":     ev["date"],
            "ring":    ev["ring"],
            "recur":   ev.get("recur"),
            "ring_dt": ring_dt,
        })

    return results


# ── Reminder collection ───────────────────────────────────────────────────────

def _reminders_on(project_dir: Path, target: date) -> list:
    """Return list of active reminders from agenda.md firing on *target* date."""
    data = _read_agenda(resolve_file(project_dir, "agenda"))
    results = []

    for i, rem in enumerate(data.get("reminders", [])):
        if rem.get("cancelled"):
            continue
        if not rem.get("date") or not rem.get("time"):
            continue
        try:
            rem_date = date.fromisoformat(rem["date"])
        except ValueError:
            continue

        # Check if this reminder fires on target date
        fires_today = (rem_date == target)

        # For recurring reminders, check if target is a valid occurrence
        if not fires_today and rem.get("recur") and rem_date <= target:
            until_date = None
            if rem.get("until"):
                try:
                    until_date = date.fromisoformat(rem["until"])
                except ValueError:
                    pass
            if until_date and target > until_date:
                continue
            # Walk occurrences from base date to target
            current = rem_date
            for _ in range(5000):
                if current >= target:
                    break
                nxt_str = _next_occurrence(current.isoformat(),
                                           rem["recur"], current.isoformat())
                current = date.fromisoformat(nxt_str)
            fires_today = (current == target)

        if not fires_today:
            continue

        fire_dt = datetime.fromisoformat(f"{target.isoformat()}T{rem['time']}:00")
        results.append({
            "index":   i,
            "desc":    rem["desc"],
            "due":     rem["date"],
            "time":    rem["time"],
            "recur":   rem.get("recur"),
            "ring_dt": fire_dt,
            "is_reminder": True,
        })

    return results


# ── Public API ─────────────────────────────────────────────────────────────────

def schedule_new_format_reminders(target: Optional[date] = None) -> list:
    """Scan all new-format projects for ring tasks and reminders firing on *target*.

    Schedules each via Reminders.app and clears the ring attribute on
    non-recurring tasks.  Returns list of scheduled task dicts.
    Skips if reminders were already scheduled today (stamp file).
    """
    target = target or date.today()
    now = datetime.now()

    # Avoid duplicate scheduling: check stamp file
    stamp = ORBIT_DIR / ".last_ring"
    if stamp.exists():
        try:
            last = date.fromisoformat(stamp.read_text().strip())
            if last == target:
                return []
        except ValueError:
            pass

    scheduled = []
    for project_dir in iter_federated_project_dirs():
        if not _is_new_project(project_dir):
            continue
        federated = is_federated(project_dir)

        # Schedule ring tasks
        tasks = _tasks_ringing_on(project_dir, target)
        for t in tasks:
            ring_dt = t["ring_dt"] if t["ring_dt"] > now else now + timedelta(minutes=1)
            ok = _schedule_reminder(t["desc"], project_dir.name, ring_dt, kind="task")
            if ok:
                print(f"  ⏰ {t['ring_dt'].strftime('%H:%M')}  "
                      f"{project_dir.name}  {t['desc']}")
                if not t.get("recur") and not federated:
                    _clear_ring(project_dir, t["index"])
                scheduled.append({**t, "project": project_dir.name})
            else:
                print(f"  ⚠️  No se pudo programar: [{project_dir.name}] {t['desc']}")

        # Schedule ring milestones
        milestones = _milestones_ringing_on(project_dir, target)
        for m in milestones:
            ring_dt = m["ring_dt"] if m["ring_dt"] > now else now + timedelta(minutes=1)
            ok = _schedule_reminder(m["desc"], project_dir.name, ring_dt, kind="milestone")
            if ok:
                print(f"  🏁 {m['ring_dt'].strftime('%H:%M')}  "
                      f"{project_dir.name}  {m['desc']}")
                scheduled.append({**m, "project": project_dir.name})
            else:
                print(f"  ⚠️  No se pudo programar: [{project_dir.name}] {m['desc']}")

        # Schedule ring events
        events = _events_ringing_on(project_dir, target)
        for e in events:
            ring_dt = e["ring_dt"] if e["ring_dt"] > now else now + timedelta(minutes=1)
            ok = _schedule_reminder(e["desc"], project_dir.name, ring_dt, kind="event")
            if ok:
                print(f"  📅 {e['ring_dt'].strftime('%H:%M')}  "
                      f"{project_dir.name}  {e['desc']}")
                scheduled.append({**e, "project": project_dir.name})
            else:
                print(f"  ⚠️  No se pudo programar: [{project_dir.name}] {e['desc']}")

        # Schedule reminders (💬)
        reminders = _reminders_on(project_dir, target)
        for r in reminders:
            ring_dt = r["ring_dt"] if r["ring_dt"] > now else now + timedelta(minutes=1)
            ok = _schedule_reminder(r['desc'], project_dir.name, ring_dt, kind="reminder")
            if ok:
                print(f"  💬 {r['ring_dt'].strftime('%H:%M')}  "
                      f"{project_dir.name}  {r['desc']}")
                scheduled.append({**r, "project": project_dir.name})
            else:
                print(f"  ⚠️  No se pudo programar: [{project_dir.name}] {r['desc']}")

    # Write stamp so we don't re-schedule on subsequent shell starts today
    stamp.write_text(target.isoformat())
    return scheduled

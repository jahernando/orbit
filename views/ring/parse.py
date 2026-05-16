"""ring.py — ring attribute resolution + AppleScript-direct Reminders helpers.

Ring attribute values on agenda.md tasks:
  [ring:1d]              → remind 1 day before due date at 09:00
  [ring:2h]              → remind 2 hours before (due date 09:00 if no time)
  [ring:30m]             → remind 30 minutes before (uses task time or 09:00)
  [ring:YYYY-MM-DD HH:MM]→ remind at exact datetime

Public surface (still in use):
  - ``_parse_ring`` / ``resolve_ring_datetime`` — used by agenda_cmds, gsync, ring_export.
  - ``_schedule_reminder`` / ``_delete_reminder`` — AppleScript-direct path used by
    agenda_cmds when ``reminders_backend != "calendar"``. **Dormant behind that flag**
    in v0.37+; the active backend is ``ring_export.py`` + ``orbit_ring_daemon.py``
    (EventKit). See DORMANT.md.
  - ``_tasks_ringing_on`` / ``_reminders_on`` — used by tests and agenda_cmds.
  - ``_clear_ring`` — used by tests.
"""
import re
import subprocess
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Optional

from core.agenda_cmds import _read_agenda, _write_agenda, _next_occurrence
from core.log import resolve_file

REMINDERS_LIST  = "Orbit"

_WEEKDAYS_ABBR_ES = ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"]


def _appointment_dt(due_date: str, time_str: Optional[str]) -> Optional[datetime]:
    """Compute the appointment datetime from due date + optional time.

    Events may store time as 'HH:MM-HH:MM'; only the start is used.
    Falls back to 09:00 when no time is set (matches ring resolution).
    """
    try:
        d = date.fromisoformat(due_date)
    except ValueError:
        return None
    if time_str:
        start = time_str.split("-")[0]
        try:
            h, m = map(int, start.split(":"))
            return datetime(d.year, d.month, d.day, h, m)
        except ValueError:
            pass
    return datetime(d.year, d.month, d.day, 9, 0)


def _ring_hint(ring: Optional[str]) -> str:
    """Return '🔔<offset>' for non-trivial rings (Nh, Nd), '' otherwise.

    Minutes-based rings are hidden because 5m/10m are the common default.
    """
    if not ring:
        return ""
    m = re.match(r"^(\d+)([hd])$", ring.strip())
    if m:
        return f"🔔{ring.strip()}"
    return ""


def _format_appt(appt_dt: datetime, today: date) -> str:
    """Format appointment datetime relative to today.

    - today              → 'HH:MM'
    - tomorrow           → 'mañana HH:MM'
    - within 7 days      → '<dow> HH:MM' (e.g. 'jue 09:00')
    - further / past     → 'YYYY-MM-DD HH:MM'
    """
    hhmm = appt_dt.strftime("%H:%M")
    d = appt_dt.date()
    delta = (d - today).days
    if delta == 0:
        return hhmm
    if delta == 1:
        return f"mañana {hhmm}"
    if 2 <= delta <= 7:
        return f"{_WEEKDAYS_ABBR_ES[d.weekday()]} {hhmm}"
    return f"{d.isoformat()} {hhmm}"


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

# Short adaptive timeout for background AppleScript calls. Long enough to
# catch fast errors (bad list name, syntax — usually <50 ms) but short
# enough to be imperceptible. iCloud-blocked calls (5-15 s) keep running
# in the background after we return.
_BG_TIMEOUT = 0.15  # seconds


def _run_osascript_bg(script: str, label: str) -> bool:
    """Run osascript with a short timeout. Returns True if the script
    either succeeded quickly or is still running (fire-and-forget). Prints
    a warning and returns False only on a fast failure.
    """
    import threading
    err = {}

    def _do_run():
        try:
            r = subprocess.run(["osascript", "-e", script],
                               capture_output=True, text=True)
            if r.returncode != 0:
                err["msg"] = (r.stderr or "").strip() or f"exit {r.returncode}"
        except FileNotFoundError:
            err["msg"] = "osascript no encontrado"
        except Exception as exc:
            err["msg"] = str(exc)

    t = threading.Thread(target=_do_run, daemon=True)
    t.start()
    t.join(timeout=_BG_TIMEOUT)
    if t.is_alive():
        return True
    if err:
        print(f"  ⚠️  {label}: {err['msg']}")
        return False
    return True

def _schedule_reminder(title: str, project: str,
                        dt: datetime, kind: str = "",
                        background: bool = False) -> bool:
    """Create a reminder in macOS Reminders.app. Returns True on success.

    With ``background=True`` the AppleScript is fired via ``Popen`` and the
    function returns True immediately — the caller doesn't wait for
    Reminders.app/iCloud (which can take 5-15 s when busy). Used by
    interactive add/edit/drop so the prompt comes back instantly.
    """
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
    if background:
        return _run_osascript_bg(script, "reminder")
    try:
        result = subprocess.run(["osascript", "-e", script],
                                capture_output=True, text=True)
        return result.returncode == 0
    except FileNotFoundError:
        return False


def _delete_reminder(title: str, project: str, kind: str = "",
                      background: bool = False) -> bool:
    """Delete a reminder from macOS Reminders.app by title. Returns True on success.

    With ``background=True`` the AppleScript runs fire-and-forget — see
    :func:`_schedule_reminder` for rationale.
    """
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
    if background:
        return _run_osascript_bg(script, "reminder")
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
            "appt_dt": _appointment_dt(task["date"], task.get("time")),
        })

    return results


def _clear_ring(project_dir: Path, task_index: int) -> None:
    """Remove the ring attribute from a task after it has been scheduled."""
    data = _read_agenda(resolve_file(project_dir, "agenda"))
    if 0 <= task_index < len(data["tasks"]):
        data["tasks"][task_index]["ring"] = None
        _write_agenda(resolve_file(project_dir, "agenda"), data)


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
            "appt_dt": fire_dt,
            "is_reminder": True,
        })

    return results

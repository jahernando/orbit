"""core/reminders.py — schedule project reminders via macOS Reminders.app."""

import re
import subprocess
from datetime import date
from pathlib import Path
from typing import Optional

from core.log import PROJECTS_DIR, find_proyecto_file

REMINDERS_LIST = "Orbit"

_RE_REMINDER = re.compile(
    r"^- \[ \] (\d{4}-\d{2}-\d{2}) (\d{2}):(\d{2}) (.+)$"
)


def _parse_reminders(proyecto_path: Path, target: date) -> list:
    """Return list of (line_index, hour, minute, title) for target date."""
    results = []
    lines = proyecto_path.read_text().splitlines()
    in_section = False
    for i, line in enumerate(lines):
        if "## ⏰ Recordatorios" in line:
            in_section = True
            continue
        if in_section and line.startswith("## "):
            break
        if not in_section:
            continue
        m = _RE_REMINDER.match(line)
        if not m:
            continue
        reminder_date = date.fromisoformat(m.group(1))
        if reminder_date != target:
            continue
        results.append({
            "line_index":    i,
            "hour":          int(m.group(2)),
            "minute":        int(m.group(3)),
            "title":         m.group(4).strip(),
            "project":       proyecto_path.parent.name,
            "proyecto_path": proyecto_path,
        })
    return results


def _schedule_via_applescript(title: str, project: str,
                               year: int, month: int, day: int,
                               hour: int, minute: int) -> bool:
    """Create a reminder in Reminders.app. Returns True on success."""
    full_title = f"[{project}] {title}"
    script = f"""
tell application "Reminders"
    if not (exists list "{REMINDERS_LIST}") then
        make new list with properties {{name:"{REMINDERS_LIST}"}}
    end if
    set reminderDate to current date
    set year of reminderDate to {year}
    set month of reminderDate to {month}
    set day of reminderDate to {day}
    set hours of reminderDate to {hour}
    set minutes of reminderDate to {minute}
    set seconds of reminderDate to 0
    tell list "{REMINDERS_LIST}"
        make new reminder with properties {{name:"{full_title}", remind me date:reminderDate, due date:reminderDate}}
    end tell
end tell
"""
    result = subprocess.run(["osascript", "-e", script],
                            capture_output=True, text=True)
    return result.returncode == 0


def _mark_scheduled(proyecto_path: Path, line_index: int) -> None:
    """Replace '- [ ]' with '- [~]' on the given line."""
    lines = proyecto_path.read_text().splitlines(keepends=True)
    lines[line_index] = lines[line_index].replace("- [ ] ", "- [~] ", 1)
    proyecto_path.write_text("".join(lines))


INJECT_START = "<!-- orbit:reminders:start -->"
INJECT_END   = "<!-- orbit:reminders:end -->"


def schedule_today_reminders(target: Optional[date] = None) -> list:
    """Scan all projects and schedule reminders for target date via Reminders.app.

    Returns list of scheduled reminder dicts.
    """
    target = target or date.today()
    if not PROJECTS_DIR.exists():
        return []

    scheduled = []
    for project_dir in sorted(PROJECTS_DIR.iterdir()):
        if not project_dir.is_dir():
            continue
        proyecto_path = find_proyecto_file(project_dir)
        if not proyecto_path or not proyecto_path.exists():
            continue

        reminders = _parse_reminders(proyecto_path, target)
        for r in reminders:
            ok = _schedule_via_applescript(
                title=r["title"],
                project=r["project"],
                year=target.year, month=target.month, day=target.day,
                hour=r["hour"], minute=r["minute"],
            )
            if ok:
                _mark_scheduled(proyecto_path, r["line_index"])
                print(f"  ⏰ [{r['project']}] {r['hour']:02d}:{r['minute']:02d} {r['title']}")
                scheduled.append(r)
            else:
                print(f"  ⚠️  No se pudo programar: [{r['project']}] {r['title']}")

    return scheduled


def inject_reminders_into_note(note_path: Path, reminders: list) -> None:
    """Inject scheduled reminders into the diario note between markers."""
    if not note_path.exists() or not reminders:
        return
    text = note_path.read_text()
    if INJECT_START not in text or INJECT_END not in text:
        return
    def _link(r):
        anchor = "recordatorios"
        path   = r["proyecto_path"].resolve()
        return f"[{r['project']}](file://{path}#{anchor})"

    lines = [f"- {r['hour']:02d}:{r['minute']:02d}  {_link(r)} — {r['title']}"
             for r in sorted(reminders, key=lambda r: (r["hour"], r["minute"]))]
    block = INJECT_START + "\n" + "\n".join(lines) + "\n" + INJECT_END
    import re
    new_text = re.sub(
        re.escape(INJECT_START) + r".*?" + re.escape(INJECT_END),
        block, text, flags=re.DOTALL,
    )
    note_path.write_text(new_text)

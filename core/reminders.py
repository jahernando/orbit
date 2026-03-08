"""core/reminders.py — schedule project reminders via macOS Reminders.app."""

import calendar
import re
import subprocess
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

from core.log import PROJECTS_DIR, find_proyecto_file

REMINDERS_LIST = "Orbit"

_RE_REMINDER = re.compile(
    r"^- \[ \] (\d{4}-\d{2}-\d{2}) (\d{2}):(\d{2}) (.+?)(\s+@\S+)?\s*$"
)

_RECUR_ES = {
    "diario": "daily", "semanal": "weekly", "mensual": "monthly",
    "anual": "yearly", "laborables": "weekdays",
}


def _next_date(d: date, recur: str) -> date:
    """Return the next occurrence date for a recurrence tag like @weekly."""
    tag = recur.lstrip("@").lower()
    tag = _RECUR_ES.get(tag, tag)

    if tag == "daily":
        return d + timedelta(days=1)
    if tag == "weekly":
        return d + timedelta(weeks=1)
    if tag == "monthly":
        month = d.month % 12 + 1
        year  = d.year + (1 if d.month == 12 else 0)
        last  = calendar.monthrange(year, month)[1]
        return d.replace(year=year, month=month, day=min(d.day, last))
    if tag == "yearly":
        try:
            return d.replace(year=d.year + 1)
        except ValueError:
            return d.replace(year=d.year + 1, day=28)
    if tag == "weekdays":
        nxt = d + timedelta(days=1)
        while nxt.weekday() >= 5:
            nxt += timedelta(days=1)
        return nxt
    if ":" in tag:
        unit_key, val = tag.split(":", 1)
        try:
            n = int(val[:-1])
            if val.endswith("w"):
                return d + timedelta(weeks=n)
            if val.endswith("d"):
                return d + timedelta(days=n)
        except ValueError:
            pass
    return d


import re as _re


def _parse_reminders(proyecto_path: Path, target: date) -> list:
    """Return reminder dicts for target date — scans both new (## ✅ Tareas @ring)
    and legacy (## ⏰ Recordatorios) formats."""
    results = []
    lines = proyecto_path.read_text().splitlines()

    # ── New format: ## ✅ Tareas with @ring ───────────────────────────────────
    in_section = False
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("## ") and "✅" in stripped and "tareas" in stripped.lower():
            in_section = True
            continue
        if in_section and stripped.startswith("## "):
            break
        if not in_section:
            continue
        if not (stripped.startswith("- [ ]") or stripped.startswith("- [~]")):
            continue
        content = stripped[5:].strip()
        all_tags = _re.findall(r'@\S+', content)
        if '@ring' not in all_tags:
            continue
        content_clean = _re.sub(r'(\s+@\S+)+\s*$', '', content).strip()
        # Expect: Title (YYYY-MM-DD HH:MM)
        m2 = _re.match(r'^(.+?)\s+\((\d{4}-\d{2}-\d{2})\s+(\d{2}:\d{2})\)\s*$', content_clean)
        if not m2:
            continue
        task_date = date.fromisoformat(m2.group(2))
        if task_date != target:
            continue
        h_str, mi_str = m2.group(3).split(':')
        recur = next((t for t in all_tags if t != '@ring'), None)
        results.append({
            "line_index":    i,
            "hour":          int(h_str),
            "minute":        int(mi_str),
            "title":         m2.group(1).strip(),
            "recur":         recur,
            "date":          task_date,
            "project":       proyecto_path.parent.name,
            "proyecto_path": proyecto_path,
        })

    # ── Legacy format: ## ⏰ Recordatorios ────────────────────────────────────
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
            "recur":         m.group(5).strip() if m.group(5) else None,
            "date":          reminder_date,
            "project":       proyecto_path.parent.name,
            "proyecto_path": proyecto_path,
        })

    return results


def _schedule_via_applescript(title: str, project: str,
                               year: int, month: int, day: int,
                               hour: int, minute: int) -> bool:
    """Create a reminder in Reminders.app. Returns True on success."""
    full_title = f"🚀 [{project}] {title}"
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


def _advance_recurring(proyecto_path: Path, line_index: int,
                        recur: str, current_date: date) -> date:
    """Advance the date of a recurring reminder to the next occurrence."""
    next_d = _next_date(current_date, recur)
    lines  = proyecto_path.read_text().splitlines(keepends=True)
    lines[line_index] = re.sub(
        r"\d{4}-\d{2}-\d{2}", next_d.isoformat(), lines[line_index], count=1,
    )
    proyecto_path.write_text("".join(lines))
    return next_d


def _find_ring_line(lines: list, desc: str) -> int:
    """Return index of first pending ring matching desc, or -1."""
    for i, line in enumerate(lines):
        if not line.strip().startswith("- [ ]"):
            continue
        m = _RE_REMINDER.match(line.strip())
        if m and desc.lower() in m.group(4).lower():
            return i
    return -1


def run_ring_schedule(project: str, desc: str, date_str: str,
                      time_str: str, recur: Optional[str] = None) -> int:
    """Reschedule a ring — delegates to run_task_schedule (unified format)."""
    from core.task import run_task_schedule
    return run_task_schedule(
        project=project, task_desc=desc,
        fecha=date_str, time_str=time_str, recur=recur,
    )


def run_ring_close(project: str, desc: str) -> int:
    """Close/mark a ring as done — delegates to run_task_close (unified format)."""
    from core.task import run_task_close
    return run_task_close(project=project, task_desc=desc, fecha=None)


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
                if r.get("recur"):
                    next_d = _advance_recurring(
                        proyecto_path, r["line_index"], r["recur"], target,
                    )
                    print(f"  ⏰ [{r['project']}] {r['hour']:02d}:{r['minute']:02d} {r['title']} "
                          f"{r['recur']} → próximo: {next_d}")
                else:
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
        anchor = "tareas"
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

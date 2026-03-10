"""agenda_cmds.py — task / milestone / event commands for new-format projects.

All commands operate on agenda.md in new-model project directories.

  task add <project> "<text>" [--date DATE] [--recur FREQ] [--ring WHEN]
  task done   [<project>] ["<text>"]
  task cancel [<project>] ["<text>"]
  task edit   [<project>] ["<text>"] [--text] [--date] [--recur] [--ring]
  task list   [<project>...] [--status pending|done|all] [--date DATE]

  ms add    <project> "<text>" [--date DATE]
  ms done   [<project>] ["<text>"]
  ms cancel [<project>] ["<text>"]
  ms edit   [<project>] ["<text>"] [--text "<new>"] [--date DATE|none]
  ms list   [<project>...] [--status pending|done|all]

  ev add  <project> "<text>" --date DATE [--end DATE]
  ev drop [<project>] ["<text>"]
  ev list [<project>] [--period DATE DATE]
"""
import calendar as _cal
import re
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

from core.project import _find_new_project, _is_new_project
from core.log import PROJECTS_DIR, add_orbit_entry, resolve_file

VALID_RECUR = {"daily", "weekly", "monthly", "weekdays"}


def _valid_date(val: str) -> bool:
    """Check if a date string is a valid ISO date (YYYY-MM-DD)."""
    try:
        date.fromisoformat(val)
        return True
    except ValueError:
        return False

# Extended recurrence patterns (stored in [recur:...])
_WEEKDAY_NAMES = {
    "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
    "friday": 4, "saturday": 5, "sunday": 6,
    "lunes": 0, "martes": 1, "miercoles": 2, "jueves": 3,
    "viernes": 4, "sabado": 5, "domingo": 6,
}

_EVERY_RE = re.compile(r"^every[- ](\d+)[- ](days?|weeks?|months?)$")
_POS_RE   = re.compile(r"^(first|last|1st)[- ](monday|tuesday|wednesday|thursday|friday|saturday|sunday"
                        r"|lunes|martes|miercoles|jueves|viernes|sabado|domingo)$")


def _normalize_recur(raw: str) -> str:
    """Normalize a recurrence expression to its stored key.

    Accepts:
      daily, weekly, monthly, weekdays           → as-is
      "every 2 weeks" / "every-2-weeks"          → every-2-weeks
      "every 3 days"                             → every-3-days
      "first monday" / "first-monday"            → first-monday
      "last friday"  / "last-friday"             → last-friday
    Returns the canonical key or the original string if not recognized.
    """
    s = raw.strip().lower().replace(" ", "-")
    if s in VALID_RECUR:
        return s
    if _EVERY_RE.match(s):
        m = _EVERY_RE.match(s)
        n = int(m.group(1))
        unit = m.group(2).rstrip("s")  # day/week/month
        return f"every-{n}-{unit}s"
    if _POS_RE.match(s):
        m = _POS_RE.match(s)
        pos = "first" if m.group(1) in ("first", "1st") else "last"
        return f"{pos}-{m.group(2)}"
    return raw


def is_valid_recur(raw: str) -> bool:
    """Check if a recurrence expression is valid."""
    key = _normalize_recur(raw)
    if key in VALID_RECUR:
        return True
    if _EVERY_RE.match(key):
        return True
    if _POS_RE.match(key):
        return True
    return False

_TASK_HEADER = "## ✅ Tareas"
_MS_HEADER   = "## 🏁 Hitos"
_EV_HEADER   = "## 📅 Eventos"

# ── Task/milestone line parsing ────────────────────────────────────────────────

def _parse_task_line(line: str) -> Optional[dict]:
    """Parse - [ ]/[x]/[-] line → dict with status/desc/date/recur/ring."""
    m = re.match(r"^- \[( |x|-)\] (.+)$", line)
    if not m:
        return None
    status = {" ": "pending", "x": "done", "-": "cancelled"}[m.group(1)]
    rest   = m.group(2)

    date_val = recur = until = ring = None
    synced = False
    date_m = re.search(r"\((\d{4}-\d{2}-\d{2})\)", rest)
    if date_m:
        date_val = date_m.group(1)
    recur_m = re.search(r"\[recur:([^\]]+)\]", rest)
    if recur_m:
        raw = recur_m.group(1)
        # Format: freq or freq:YYYY-MM-DD (with until date)
        if ":" in raw:
            recur, until = raw.split(":", 1)
        else:
            recur = raw
    ring_m = re.search(r"\[ring:([^\]]+)\]", rest)
    if ring_m:
        ring = ring_m.group(1)
    if re.search(r"\[G\]", rest):
        synced = True
    # Legacy: parse old [gtask:...] as synced
    if re.search(r"\[gtask:[^\]]+\]", rest):
        synced = True

    # Description = rest minus attribute patterns
    desc = rest
    for pat in [r"\(\d{4}-\d{2}-\d{2}\)", r"\[recur:[^\]]+\]",
                r"\[ring:[^\]]+\]", r"\[gtask:[^\]]+\]", r"\[G\]"]:
        desc = re.sub(pat, "", desc)
    desc = desc.strip()

    return {"status": status, "desc": desc, "date": date_val,
            "recur": recur, "until": until, "ring": ring, "synced": synced}


def _format_task_line(task: dict) -> str:
    """Serialize a task/milestone dict → markdown line."""
    char = {"pending": " ", "done": "x", "cancelled": "-"}[task["status"]]
    parts = [task["desc"]]
    if task.get("date"):
        parts.append(f"({task['date']})")
    if task.get("recur"):
        recur_tag = task["recur"]
        if task.get("until"):
            recur_tag += f":{task['until']}"
        parts.append(f"[recur:{recur_tag}]")
    if task.get("ring"):
        parts.append(f"[ring:{task['ring']}]")
    if task.get("synced"):
        parts.append("[G]")
    return f"- [{char}] {' '.join(parts)}"


# ── Event line parsing ─────────────────────────────────────────────────────────

def _parse_event_line(line: str) -> Optional[dict]:
    """Parse YYYY-MM-DD — desc [end:YYYY-MM-DD] [recur:...] [ring:...] → dict."""
    m = re.match(r"^(\d{4}-\d{2}-\d{2})\s+—\s+(.+)$", line)
    if not m:
        return None
    date_val = m.group(1)
    rest     = m.group(2)
    end = recur = until = ring = None
    synced = False
    end_m = re.search(r"\[end:(\d{4}-\d{2}-\d{2})\]", rest)
    if end_m:
        end  = end_m.group(1)
    recur_m = re.search(r"\[recur:([^\]]+)\]", rest)
    if recur_m:
        raw = recur_m.group(1)
        if ":" in raw:
            recur, until = raw.split(":", 1)
        else:
            recur = raw
    ring_m = re.search(r"\[ring:([^\]]+)\]", rest)
    if ring_m:
        ring = ring_m.group(1)
    if re.search(r"\[G\]", rest):
        synced = True
    # Legacy: parse old [gcal:...] as synced
    if re.search(r"\[gcal:[^\]]+\]", rest):
        synced = True
    # Strip attribute tags from description
    for pat in [r"\[end:[^\]]+\]", r"\[recur:[^\]]+\]",
                r"\[ring:[^\]]+\]", r"\[gcal:[^\]]+\]", r"\[G\]"]:
        rest = re.sub(pat, "", rest)
    rest = rest.strip()
    return {"date": date_val, "desc": rest, "end": end,
            "recur": recur, "until": until, "ring": ring, "synced": synced}


def _format_event_line(ev: dict) -> str:
    """Serialize an event dict → markdown line."""
    line = f"{ev['date']} — {ev['desc']}"
    if ev.get("end"):
        line += f" [end:{ev['end']}]"
    if ev.get("recur"):
        recur_tag = ev["recur"]
        if ev.get("until"):
            recur_tag += f":{ev['until']}"
        line += f" [recur:{recur_tag}]"
    if ev.get("ring"):
        line += f" [ring:{ev['ring']}]"
    if ev.get("synced"):
        line += " [G]"
    return line


# ── Agenda file I/O ────────────────────────────────────────────────────────────

def _read_agenda(path: Path) -> dict:
    """Parse agenda.md → {header, tasks, milestones, events}."""
    if not path.exists():
        return {"header": ["# Agenda"], "tasks": [], "milestones": [], "events": []}

    lines   = path.read_text().splitlines()
    result  = {"header": [], "tasks": [], "milestones": [], "events": []}
    section = None   # "tasks" | "milestones" | "events" | None

    for line in lines:
        if section is None:
            # Collect header (everything before first ## section)
            if line == _TASK_HEADER:
                section = "tasks"
            elif line == _MS_HEADER:
                section = "milestones"
            elif line == _EV_HEADER:
                section = "events"
            else:
                result["header"].append(line)
        elif line == _TASK_HEADER:
            section = "tasks"
        elif line == _MS_HEADER:
            section = "milestones"
        elif line == _EV_HEADER:
            section = "events"
        elif not line.strip():
            continue   # skip blank lines inside sections
        elif section == "tasks":
            t = _parse_task_line(line)
            if t:
                result["tasks"].append(t)
        elif section == "milestones":
            t = _parse_task_line(line)
            if t:
                result["milestones"].append(t)
        elif section == "events":
            e = _parse_event_line(line)
            if e:
                result["events"].append(e)

    return result


def _write_agenda(path: Path, data: dict) -> None:
    """Serialize data dict back to agenda.md."""
    out = list(data["header"])
    # Strip trailing blank lines from header block
    while out and not out[-1].strip():
        out.pop()
    out.append("")

    if data["tasks"]:
        out.append(_TASK_HEADER)
        for t in data["tasks"]:
            out.append(_format_task_line(t))
        out.append("")

    if data["milestones"]:
        out.append(_MS_HEADER)
        for ms in data["milestones"]:
            out.append(_format_task_line(ms))
        out.append("")

    if data["events"]:
        out.append(_EV_HEADER)
        # Sort events by date
        for ev in sorted(data["events"], key=lambda e: e["date"]):
            out.append(_format_event_line(ev))
        out.append("")

    path.write_text("\n".join(out) + "\n")


# ── Interactive selection ──────────────────────────────────────────────────────

def _select_item(items: list, label: str, text: Optional[str] = None) -> Optional[int]:
    """Return list index of selected item among pending items.

    If *text* given: find by partial match (error if 0 or >1 matches).
    Else: show interactive numbered list.
    """
    pending_idx = [i for i, t in enumerate(items) if t["status"] == "pending"]
    pending     = [items[i] for i in pending_idx]

    if text:
        matches = [i for i, t in enumerate(pending) if text.lower() in t["desc"].lower()]
        if not matches:
            print(f"Error: no se encontró '{text}'")
            return None
        if len(matches) > 1:
            descs = ", ".join(f'"{pending[i]["desc"]}"' for i in matches)
            print(f"Ambiguo: {len(matches)} coincidencias: {descs}")
            return None
        return pending_idx[matches[0]]

    if not pending:
        print(f"No hay {label} pendientes.")
        return None

    print(f"\n{label}:")
    for i, t in enumerate(pending, 1):
        date_s = f" ({t['date']})" if t.get("date") else ""
        print(f"  {i}. {t['desc']}{date_s}")
    print()

    if not sys.stdin.isatty():
        return None

    try:
        raw = input("Selecciona (número o texto parcial): ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return None

    if not raw:
        return None
    if raw.isdigit():
        idx = int(raw) - 1
        if 0 <= idx < len(pending):
            return pending_idx[idx]
        print(f"Fuera de rango (1–{len(pending)})")
        return None
    matches = [i for i, t in enumerate(pending) if raw.lower() in t["desc"].lower()]
    if not matches:
        print(f"Sin coincidencias para '{raw}'")
        return None
    if len(matches) > 1:
        print(f"Ambiguo: {len(matches)} coincidencias")
        return None
    return pending_idx[matches[0]]


def _select_event(events: list, text: Optional[str]) -> Optional[int]:
    """Select an event by text or interactive list. Returns index in events list."""
    if text:
        matches = [i for i, e in enumerate(events) if text.lower() in e["desc"].lower()]
        if not matches:
            print(f"Error: no se encontró '{text}'")
            return None
        if len(matches) > 1:
            print(f"Ambiguo: {len(matches)} coincidencias")
            return None
        return matches[0]

    if not events:
        print("No hay eventos disponibles.")
        return None

    print("\nEventos:")
    for i, e in enumerate(events, 1):
        end_s = f" → {e['end']}" if e.get("end") else ""
        print(f"  {i}. {e['date']} — {e['desc']}{end_s}")
    print()

    if not sys.stdin.isatty():
        return None

    try:
        raw = input("Selecciona (número o texto parcial): ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return None

    if not raw:
        return None
    if raw.isdigit():
        idx = int(raw) - 1
        if 0 <= idx < len(events):
            return idx
        print(f"Fuera de rango (1–{len(events)})")
        return None
    matches = [i for i, e in enumerate(events) if raw.lower() in e["desc"].lower()]
    if not matches:
        print(f"Sin coincidencias para '{raw}'")
        return None
    if len(matches) > 1:
        print(f"Ambiguo: {len(matches)} coincidencias")
        return None
    return matches[0]


# ── Recurrence helpers ─────────────────────────────────────────────────────────

def _next_occurrence(due: Optional[str], recur: str, done_date: str) -> str:
    """Compute next recurrence date after completing a task."""
    base = date.fromisoformat(due) if due else date.fromisoformat(done_date)
    if recur == "daily":
        nxt = base + timedelta(days=1)
    elif recur == "weekly":
        nxt = base + timedelta(weeks=1)
    elif recur == "monthly":
        m = base.month + 1
        y = base.year + (m - 1) // 12
        m = (m - 1) % 12 + 1
        last = _cal.monthrange(y, m)[1]
        nxt = date(y, m, min(base.day, last))
    elif recur == "weekdays":
        nxt = base + timedelta(days=1)
        while nxt.weekday() >= 5:
            nxt += timedelta(days=1)
    else:
        # Extended patterns
        em = _EVERY_RE.match(recur)
        if em:
            n = int(em.group(1))
            unit = em.group(2).rstrip("s")
            if unit == "day":
                nxt = base + timedelta(days=n)
            elif unit == "week":
                nxt = base + timedelta(weeks=n)
            elif unit == "month":
                for _ in range(n):
                    mo = base.month + 1
                    yr = base.year + (mo - 1) // 12
                    mo = (mo - 1) % 12 + 1
                    last = _cal.monthrange(yr, mo)[1]
                    base = date(yr, mo, min(base.day, last))
                nxt = base
            else:
                nxt = base + timedelta(weeks=1)
        else:
            pm = _POS_RE.match(recur)
            if pm:
                pos = pm.group(1)
                wd = _WEEKDAY_NAMES.get(pm.group(2), 0)
                # Advance to next month
                mo = base.month + 1
                yr = base.year + (mo - 1) // 12
                mo = (mo - 1) % 12 + 1
                if pos in ("first", "1st"):
                    d = date(yr, mo, 1)
                    while d.weekday() != wd:
                        d += timedelta(days=1)
                else:  # last
                    last_day = _cal.monthrange(yr, mo)[1]
                    d = date(yr, mo, last_day)
                    while d.weekday() != wd:
                        d -= timedelta(days=1)
                nxt = d
            else:
                nxt = base + timedelta(weeks=1)
    return nxt.isoformat()


# ── TASK commands ──────────────────────────────────────────────────────────────

def run_task_add(project: str, text: str, date_val: Optional[str] = None,
                 recur: Optional[str] = None, until: Optional[str] = None,
                 ring: Optional[str] = None) -> int:
    if date_val and not _valid_date(date_val):
        print(f"⚠️  Fecha '{date_val}' no reconocida. Usa: YYYY-MM-DD, today, mañana, next monday, ...")
        return 1
    if until and not _valid_date(until):
        print(f"⚠️  Fecha --until '{until}' no reconocida.")
        return 1
    if recur:
        recur = _normalize_recur(recur)
        if not is_valid_recur(recur):
            print(f"⚠️  Recurrencia '{recur}' no válida. Usa: daily, weekly, monthly, weekdays, every 2 weeks, first monday, ...")
            return 1
    if until and not recur:
        print("Error: --until requiere --recur.")
        return 1
    if ring and not date_val:
        print("⚠️  --ring requiere --date.")
        return 1
    if ring:
        from core.ring import _parse_ring
        if _parse_ring(ring) is None:
            print(f"⚠️  Ring '{ring}' no válido. Usa: HH:MM, 1d, 2h, o YYYY-MM-DD HH:MM")
            return 1

    project_dir = _find_new_project(project)
    if project_dir is None:
        return 1

    agenda_path = resolve_file(project_dir, "agenda")
    data = _read_agenda(agenda_path)
    new_task = {"status": "pending", "desc": text,
                "date": date_val, "recur": recur,
                "until": until, "ring": ring}
    data["tasks"].append(new_task)
    _write_agenda(agenda_path, data)

    attrs = ""
    if date_val: attrs += f" ({date_val})"
    if recur:
        recur_s = recur
        if until:
            recur_s += f":{until}"
        attrs += f" [recur:{recur_s}]"
    if ring:     attrs += f" [ring:{ring}]"
    print(f"✓ [{project_dir.name}] Tarea: {text}{attrs}")

    # Schedule reminder immediately if ring fires today
    if ring:
        from core.ring import resolve_ring_datetime, _schedule_reminder
        ring_dt = resolve_ring_datetime(date_val, ring)
        if ring_dt and ring_dt.date() == date.today():
            ok = _schedule_reminder(text, project_dir.name, ring_dt)
            if ok:
                print(f"  ⏰ Recordatorio programado: {ring_dt.strftime('%H:%M')}")
            else:
                print(f"  ⚠️  No se pudo programar el recordatorio")

    # Sync to Google
    from core.gsync import sync_item
    sync_item(project_dir, new_task, "task")

    return 0


def run_task_done(project: Optional[str], text: Optional[str]) -> int:
    project_dir = _find_new_project(project) if project else None
    if project and project_dir is None:
        return 1
    if project_dir is None:
        print("Error: especifica un proyecto (ej. task done <proyecto>)")
        return 1

    agenda_path = resolve_file(project_dir, "agenda")
    data = _read_agenda(agenda_path)

    idx = _select_item(data["tasks"], "Tareas pendientes", text)
    if idx is None:
        return 1

    task      = data["tasks"][idx]
    task_desc = task["desc"]
    done_date = date.today().isoformat()
    task["status"] = "done"

    next_info = ""
    if task.get("recur"):
        next_due = _next_occurrence(task.get("date"), task["recur"], done_date)
        until = task.get("until")
        # Only create next occurrence if within until limit
        if until and date.fromisoformat(next_due) > date.fromisoformat(until):
            next_info = f" (recur: {task['recur']}) — serie finalizada ({until})"
        else:
            data["tasks"].append({"status": "pending", "desc": task_desc,
                                   "date": next_due, "recur": task["recur"],
                                   "until": until, "ring": task.get("ring")})
            next_info = f" (recur: {task['recur']}) → próxima: {next_due}"

    _write_agenda(agenda_path, data)
    add_orbit_entry(project_dir, f"[completada] Tarea: {task_desc}{next_info}", "apunte")
    print(f"✓ [{project_dir.name}] [completada] {task_desc}{next_info}")

    # Sync completed task to Google
    from core.gsync import sync_item
    sync_item(project_dir, task, "task")

    return 0


def run_task_drop(project: Optional[str], text: Optional[str],
                  force: bool = False) -> int:
    project_dir = _find_new_project(project) if project else None
    if project and project_dir is None:
        return 1
    if project_dir is None:
        print("Error: especifica un proyecto")
        return 1

    agenda_path = resolve_file(project_dir, "agenda")
    data = _read_agenda(agenda_path)

    idx = _select_item(data["tasks"], "Tareas pendientes", text)
    if idx is None:
        return 1

    task_desc = data["tasks"][idx]["desc"]

    if not force:
        if not sys.stdin.isatty():
            print("Error: usa --force para confirmar en modo no interactivo.")
            return 1
        try:
            ans = input(f"¿Cancelar tarea \"{task_desc}\"? [s/N]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            return 1
        if ans not in ("s", "si", "sí", "y", "yes"):
            print("Cancelado.")
            return 0

    task = data["tasks"][idx]
    task["status"] = "cancelled"

    _write_agenda(agenda_path, data)
    add_orbit_entry(project_dir, f"[cancelada] Tarea: {task_desc}", "apunte")
    print(f"✓ [{project_dir.name}] [cancelada] {task_desc}")

    # Sync cancelled task to Google
    from core.gsync import sync_item
    sync_item(project_dir, task, "task")

    return 0


def run_task_edit(project: Optional[str], text: Optional[str],
                  new_text: Optional[str] = None, new_date: Optional[str] = None,
                  new_recur: Optional[str] = None, new_until: Optional[str] = None,
                  new_ring: Optional[str] = None) -> int:
    project_dir = _find_new_project(project) if project else None
    if project and project_dir is None:
        return 1
    if project_dir is None:
        print("Error: especifica un proyecto")
        return 1

    if new_date and new_date != "none" and not _valid_date(new_date):
        print(f"⚠️  Fecha '{new_date}' no reconocida. Usa: YYYY-MM-DD, today, mañana, next monday, ...")
        return 1
    if new_until and new_until != "none" and not _valid_date(new_until):
        print(f"⚠️  Fecha --until '{new_until}' no reconocida.")
        return 1
    if new_recur and new_recur != "none":
        new_recur = _normalize_recur(new_recur)
    if new_recur and new_recur != "none" and not is_valid_recur(new_recur):
        print(f"⚠️  Recurrencia '{new_recur}' no válida. Usa: daily, weekly, monthly, weekdays, every 2 weeks, first monday, ...")
        return 1
    if new_ring and new_ring != "none":
        from core.ring import _parse_ring
        if _parse_ring(new_ring) is None:
            print(f"⚠️  Ring '{new_ring}' no válido. Usa: HH:MM, 1d, 2h, o YYYY-MM-DD HH:MM")
            return 1

    agenda_path = resolve_file(project_dir, "agenda")
    data = _read_agenda(agenda_path)

    idx = _select_item(data["tasks"], "Tareas pendientes", text)
    if idx is None:
        return 1

    task = data["tasks"][idx]
    if new_text:  task["desc"]  = new_text
    if new_date:
        task["date"]  = None if new_date == "none" else new_date
    if new_recur:
        task["recur"] = None if new_recur == "none" else new_recur
    if new_until:
        task["until"] = None if new_until == "none" else new_until
    if new_ring:
        task["ring"]  = None if new_ring  == "none" else new_ring

    _write_agenda(agenda_path, data)
    print(f"✓ [{project_dir.name}] Tarea actualizada: {task['desc']}")

    # Sync updated task to Google
    from core.gsync import sync_item
    sync_item(project_dir, task, "task")

    return 0


def run_task_list(projects: Optional[list] = None,
                  status_filter: str = "pending",
                  date_filter: Optional[str] = None) -> int:
    """List tasks from new-format projects."""
    if projects:
        dirs = []
        for p in projects:
            d = _find_new_project(p)
            if d:
                dirs.append(d)
        if not dirs:
            return 1
    else:
        dirs = sorted(d for d in PROJECTS_DIR.iterdir()
                      if d.is_dir() and _is_new_project(d))

    total = 0
    for project_dir in dirs:
        data  = _read_agenda(resolve_file(project_dir, "agenda"))
        tasks = data["tasks"]

        if status_filter != "all":
            tasks = [t for t in tasks if t["status"] == status_filter]
        if date_filter:
            tasks = [t for t in tasks if t.get("date", "").startswith(date_filter)]

        if not tasks:
            continue

        print(f"\n[{project_dir.name}]")
        for t in tasks:
            status_s = {"pending": "[ ]", "done": "[x]", "cancelled": "[-]"}[t["status"]]
            date_s   = f" ({t['date']})" if t.get("date") else ""
            recur_s = ""
            if t.get("recur"):
                recur_s = f" [recur:{t['recur']}"
                if t.get("until"):
                    recur_s += f":{t['until']}"
                recur_s += "]"
            ring_s   = f" [ring:{t['ring']}]"   if t.get("ring")  else ""
            print(f"  {status_s} {t['desc']}{date_s}{recur_s}{ring_s}")
            total += 1

    if not total:
        sf = f" ({status_filter})" if status_filter != "all" else ""
        print(f"No hay tareas{sf}.")
    else:
        print()
    return 0


# ── MILESTONE commands ─────────────────────────────────────────────────────────

def run_ms_add(project: str, text: str, date_val: Optional[str] = None,
               recur: Optional[str] = None, until: Optional[str] = None,
               ring: Optional[str] = None) -> int:
    if date_val and not _valid_date(date_val):
        print(f"⚠️  Fecha '{date_val}' no reconocida. Usa: YYYY-MM-DD, today, mañana, next monday, ...")
        return 1
    if until and not _valid_date(until):
        print(f"⚠️  Fecha --until '{until}' no reconocida.")
        return 1
    if recur:
        recur = _normalize_recur(recur)
        if not is_valid_recur(recur):
            print(f"⚠️  Recurrencia '{recur}' no válida. Usa: daily, weekly, monthly, weekdays, every 2 weeks, first monday, ...")
            return 1
    if until and not recur:
        print("Error: --until requiere --recur.")
        return 1
    if ring and not date_val:
        print("⚠️  --ring requiere --date.")
        return 1
    if ring:
        from core.ring import _parse_ring
        if _parse_ring(ring) is None:
            print(f"⚠️  Ring '{ring}' no válido. Usa: HH:MM, 1d, 2h, o YYYY-MM-DD HH:MM")
            return 1

    project_dir = _find_new_project(project)
    if project_dir is None:
        return 1

    agenda_path = resolve_file(project_dir, "agenda")
    data = _read_agenda(agenda_path)
    new_ms = {"status": "pending", "desc": text,
              "date": date_val, "recur": recur, "until": until, "ring": ring}
    data["milestones"].append(new_ms)
    _write_agenda(agenda_path, data)

    attrs = ""
    if date_val: attrs += f" ({date_val})"
    if recur:
        recur_s = recur
        if until: recur_s += f":{until}"
        attrs += f" [recur:{recur_s}]"
    if ring:     attrs += f" [ring:{ring}]"
    print(f"✓ [{project_dir.name}] Hito: {text}{attrs}")

    # Schedule reminder immediately if ring fires today
    if ring:
        from core.ring import resolve_ring_datetime, _schedule_reminder
        ring_dt = resolve_ring_datetime(date_val, ring)
        if ring_dt and ring_dt.date() == date.today():
            ok = _schedule_reminder(text, project_dir.name, ring_dt)
            if ok:
                print(f"  ⏰ Recordatorio programado: {ring_dt.strftime('%H:%M')}")

    from core.gsync import sync_item
    sync_item(project_dir, new_ms, "milestone")

    return 0


def run_ms_done(project: Optional[str], text: Optional[str]) -> int:
    project_dir = _find_new_project(project) if project else None
    if project and project_dir is None:
        return 1
    if project_dir is None:
        print("Error: especifica un proyecto")
        return 1

    agenda_path = resolve_file(project_dir, "agenda")
    data = _read_agenda(agenda_path)

    idx = _select_item(data["milestones"], "Hitos pendientes", text)
    if idx is None:
        return 1

    ms = data["milestones"][idx]
    ms_desc = ms["desc"]
    ms["status"] = "done"

    _write_agenda(agenda_path, data)
    add_orbit_entry(project_dir, f"[alcanzado] Hito: {ms_desc}", "apunte")
    print(f"✓ [{project_dir.name}] [alcanzado] {ms_desc}")

    from core.gsync import sync_item
    sync_item(project_dir, ms, "milestone")

    return 0


def run_ms_drop(project: Optional[str], text: Optional[str],
                force: bool = False) -> int:
    project_dir = _find_new_project(project) if project else None
    if project and project_dir is None:
        return 1
    if project_dir is None:
        print("Error: especifica un proyecto")
        return 1

    agenda_path = resolve_file(project_dir, "agenda")
    data = _read_agenda(agenda_path)

    idx = _select_item(data["milestones"], "Hitos pendientes", text)
    if idx is None:
        return 1

    ms_desc = data["milestones"][idx]["desc"]

    if not force:
        if not sys.stdin.isatty():
            print("Error: usa --force para confirmar en modo no interactivo.")
            return 1
        try:
            ans = input(f"¿Cancelar hito \"{ms_desc}\"? [s/N]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            return 1
        if ans not in ("s", "si", "sí", "y", "yes"):
            print("Cancelado.")
            return 0

    ms = data["milestones"][idx]
    ms["status"] = "cancelled"

    _write_agenda(agenda_path, data)
    add_orbit_entry(project_dir, f"[cancelado] Hito: {ms_desc}", "apunte")
    print(f"✓ [{project_dir.name}] [cancelado] {ms_desc}")

    from core.gsync import sync_item
    sync_item(project_dir, ms, "milestone")

    return 0


def run_ms_edit(project: Optional[str], text: Optional[str],
                new_text: Optional[str] = None, new_date: Optional[str] = None,
                new_recur: Optional[str] = None, new_until: Optional[str] = None,
                new_ring: Optional[str] = None) -> int:
    if new_date and new_date != "none" and not _valid_date(new_date):
        print(f"⚠️  Fecha '{new_date}' no reconocida. Usa: YYYY-MM-DD, today, mañana, next monday, ...")
        return 1
    if new_until and new_until != "none" and not _valid_date(new_until):
        print(f"⚠️  Fecha --until '{new_until}' no reconocida.")
        return 1
    if new_recur and new_recur != "none":
        new_recur = _normalize_recur(new_recur)
    if new_recur and new_recur != "none" and not is_valid_recur(new_recur):
        print(f"⚠️  Recurrencia '{new_recur}' no válida. Usa: daily, weekly, monthly, weekdays, every 2 weeks, first monday, ...")
        return 1
    if new_ring and new_ring != "none":
        from core.ring import _parse_ring
        if _parse_ring(new_ring) is None:
            print(f"⚠️  Ring '{new_ring}' no válido. Usa: HH:MM, 1d, 2h, o YYYY-MM-DD HH:MM")
            return 1

    project_dir = _find_new_project(project) if project else None
    if project and project_dir is None:
        return 1
    if project_dir is None:
        print("Error: especifica un proyecto")
        return 1

    agenda_path = resolve_file(project_dir, "agenda")
    data = _read_agenda(agenda_path)

    idx = _select_item(data["milestones"], "Hitos pendientes", text)
    if idx is None:
        return 1

    ms = data["milestones"][idx]
    if new_text:  ms["desc"]  = new_text
    if new_date:  ms["date"]  = None if new_date  == "none" else new_date
    if new_recur: ms["recur"] = None if new_recur == "none" else new_recur
    if new_until: ms["until"] = None if new_until == "none" else new_until
    if new_ring:  ms["ring"]  = None if new_ring  == "none" else new_ring

    _write_agenda(agenda_path, data)
    print(f"✓ [{project_dir.name}] Hito actualizado: {ms['desc']}")

    from core.gsync import sync_item
    sync_item(project_dir, ms, "milestone")

    return 0


def run_ms_list(projects: Optional[list] = None, status_filter: str = "pending") -> int:
    if projects:
        dirs = []
        for p in projects:
            d = _find_new_project(p)
            if d:
                dirs.append(d)
        if not dirs:
            return 1
    else:
        dirs = sorted(d for d in PROJECTS_DIR.iterdir()
                      if d.is_dir() and _is_new_project(d))

    total = 0
    for project_dir in dirs:
        data = _read_agenda(resolve_file(project_dir, "agenda"))
        mss  = data["milestones"]

        if status_filter != "all":
            mss = [ms for ms in mss if ms["status"] == status_filter]
        if not mss:
            continue

        print(f"\n[{project_dir.name}]")
        for ms in mss:
            status_s = {"pending": "[ ]", "done": "[x]", "cancelled": "[-]"}[ms["status"]]
            date_s   = f" ({ms['date']})" if ms.get("date") else ""
            print(f"  {status_s} {ms['desc']}{date_s}")
            total += 1

    if not total:
        print(f"No hay hitos ({status_filter}).")
    else:
        print()
    return 0


# ── EVENT commands ─────────────────────────────────────────────────────────────

def run_ev_add(project: str, text: str, date_val: str,
               end_date: Optional[str] = None, recur: Optional[str] = None,
               until: Optional[str] = None, ring: Optional[str] = None) -> int:
    if not _valid_date(date_val):
        print(f"⚠️  Fecha '{date_val}' no reconocida. Usa: YYYY-MM-DD, today, mañana, next monday, ...")
        return 1
    if end_date and not _valid_date(end_date):
        print(f"⚠️  Fecha --end '{end_date}' no reconocida. Usa: YYYY-MM-DD, today, mañana, next monday, ...")
        return 1
    if until and not _valid_date(until):
        print(f"⚠️  Fecha --until '{until}' no reconocida.")
        return 1
    if recur:
        recur = _normalize_recur(recur)
        if not is_valid_recur(recur):
            print(f"⚠️  Recurrencia '{recur}' no válida. Usa: daily, weekly, monthly, weekdays, every 2 weeks, first monday, ...")
            return 1
    if until and not recur:
        print("Error: --until requiere --recur.")
        return 1
    if ring and not date_val:
        print("⚠️  --ring requiere --date.")
        return 1
    if ring:
        from core.ring import _parse_ring
        if _parse_ring(ring) is None:
            print(f"⚠️  Ring '{ring}' no válido. Usa: HH:MM, 1d, 2h, o YYYY-MM-DD HH:MM")
            return 1

    project_dir = _find_new_project(project)
    if project_dir is None:
        return 1

    agenda_path = resolve_file(project_dir, "agenda")
    data = _read_agenda(agenda_path)
    new_ev = {"date": date_val, "desc": text, "end": end_date,
              "recur": recur, "until": until, "ring": ring}
    data["events"].append(new_ev)
    _write_agenda(agenda_path, data)

    attrs = ""
    if end_date: attrs += f" → {end_date}"
    if recur:
        recur_s = recur
        if until: recur_s += f":{until}"
        attrs += f" [recur:{recur_s}]"
    if ring: attrs += f" [ring:{ring}]"
    print(f"✓ [{project_dir.name}] Evento: {date_val} — {text}{attrs}")

    # Schedule reminder immediately if ring fires today
    if ring:
        from core.ring import resolve_ring_datetime, _schedule_reminder
        ring_dt = resolve_ring_datetime(date_val, ring)
        if ring_dt and ring_dt.date() == date.today():
            ok = _schedule_reminder(text, project_dir.name, ring_dt)
            if ok:
                print(f"  ⏰ Recordatorio programado: {ring_dt.strftime('%H:%M')}")

    from core.gsync import sync_item
    sync_item(project_dir, new_ev, "event")

    return 0


def run_ev_drop(project: Optional[str], text: Optional[str],
                force: bool = False) -> int:
    import sys
    project_dir = _find_new_project(project) if project else None
    if project and project_dir is None:
        return 1
    if project_dir is None:
        print("Error: especifica un proyecto")
        return 1

    agenda_path = resolve_file(project_dir, "agenda")
    data = _read_agenda(agenda_path)

    idx = _select_event(data["events"], text)
    if idx is None:
        return 1

    ev = data["events"][idx]
    display = f"{ev['date']} — {ev['desc']}"

    if not force:
        if not sys.stdin.isatty():
            print("Error: usa --force para confirmar el borrado en modo no interactivo.")
            return 1
        try:
            ans = input(f"¿Seguro que quieres eliminar \"{display}\"? [s/N]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            return 1
        if ans not in ("s", "si", "sí", "y", "yes"):
            print("Cancelado.")
            return 0

    ev_removed = data["events"].pop(idx)
    _write_agenda(agenda_path, data)
    print(f"✓ [{project_dir.name}] Evento eliminado: {display}")

    # Delete from Google Calendar if synced
    if ev_removed.get("synced"):
        from core.gsync import delete_gcal_event
        delete_gcal_event(project_dir, ev_removed)

    return 0


def run_ev_edit(project: Optional[str], text: Optional[str],
                new_text: Optional[str] = None, new_date: Optional[str] = None,
                new_end: Optional[str] = None, new_recur: Optional[str] = None,
                new_until: Optional[str] = None, new_ring: Optional[str] = None) -> int:
    if new_date and not _valid_date(new_date):
        print(f"⚠️  Fecha '{new_date}' no reconocida. Usa: YYYY-MM-DD, today, mañana, next monday, ...")
        return 1
    if new_end and new_end != "none" and not _valid_date(new_end):
        print(f"⚠️  Fecha --end '{new_end}' no reconocida. Usa: YYYY-MM-DD, today, mañana, next monday, ...")
        return 1
    if new_until and new_until != "none" and not _valid_date(new_until):
        print(f"⚠️  Fecha --until '{new_until}' no reconocida.")
        return 1
    if new_recur and new_recur != "none":
        new_recur = _normalize_recur(new_recur)
    if new_recur and new_recur != "none" and not is_valid_recur(new_recur):
        print(f"⚠️  Recurrencia '{new_recur}' no válida. Usa: daily, weekly, monthly, weekdays, every 2 weeks, first monday, ...")
        return 1
    if new_ring and new_ring != "none":
        from core.ring import _parse_ring
        if _parse_ring(new_ring) is None:
            print(f"⚠️  Ring '{new_ring}' no válido. Usa: HH:MM, 1d, 2h, o YYYY-MM-DD HH:MM")
            return 1

    project_dir = _find_new_project(project) if project else None
    if project and project_dir is None:
        return 1
    if project_dir is None:
        print("Error: especifica un proyecto")
        return 1

    agenda_path = resolve_file(project_dir, "agenda")
    data = _read_agenda(agenda_path)

    idx = _select_event(data["events"], text)
    if idx is None:
        return 1

    ev = data["events"][idx]
    if new_text:  ev["desc"]  = new_text
    if new_date:  ev["date"]  = new_date
    if new_end:   ev["end"]   = None if new_end   == "none" else new_end
    if new_recur: ev["recur"] = None if new_recur == "none" else new_recur
    if new_until: ev["until"] = None if new_until == "none" else new_until
    if new_ring:  ev["ring"]  = None if new_ring  == "none" else new_ring

    _write_agenda(agenda_path, data)
    print(f"✓ [{project_dir.name}] Evento actualizado: {ev['date']} — {ev['desc']}")

    from core.gsync import sync_item
    sync_item(project_dir, ev, "event")

    return 0


def run_ev_list(project: Optional[str] = None,
                period_from: Optional[str] = None,
                period_to:   Optional[str] = None) -> int:
    if project:
        project_dir = _find_new_project(project)
        if project_dir is None:
            return 1
        dirs = [project_dir]
    else:
        dirs = sorted(d for d in PROJECTS_DIR.iterdir()
                      if d.is_dir() and _is_new_project(d))

    total = 0
    for project_dir in dirs:
        data   = _read_agenda(resolve_file(project_dir, "agenda"))
        events = data["events"]
        if period_from:
            events = [e for e in events if e["date"] >= period_from]
        if period_to:
            events = [e for e in events if e["date"] <= period_to]
        if not events:
            continue

        print(f"\n[{project_dir.name}]")
        for e in sorted(events, key=lambda x: x["date"]):
            end_s = f" → {e['end']}" if e.get("end") else ""
            print(f"  {e['date']} — {e['desc']}{end_s}")
            total += 1

    if not total:
        print("No hay eventos.")
    else:
        print()
    return 0

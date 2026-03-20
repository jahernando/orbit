"""agenda_cmds.py — task / milestone / event commands for new-format projects.

All commands operate on agenda.md in new-model project directories.

  task add <project> "<text>" [--date DATE] [--recur FREQ] [--ring WHEN] [--desc DESC]
  task done   [<project>] ["<text>"]
  task cancel [<project>] ["<text>"]
  task edit   [<project>] ["<text>"] [--text] [--date] [--recur] [--ring] [--desc]
  task list   [<project>...] [--status pending|done|all] [--date DATE]

  ms add    <project> "<text>" [--date DATE] [--desc DESC]
  ms done   [<project>] ["<text>"]
  ms cancel [<project>] ["<text>"]
  ms edit   [<project>] ["<text>"] [--text "<new>"] [--date DATE|none] [--desc]
  ms list   [<project>...] [--status pending|done|all]

  ev add  <project> "<text>" --date DATE [--end DATE] [--desc DESC]
  ev drop [<project>] ["<text>"]
  ev edit [<project>] ["<text>"] [--desc DESC]
  ev list [<project>] [--period DATE DATE]

Description lines are stored as indented lines (4 spaces) below the item
in agenda.md.  They are NOT shown in list/agenda views — only in the raw
file and propagated to Google Calendar/Tasks descriptions.
"""
import calendar as _cal
import re
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

from core.project import _find_new_project, _is_new_project
from core.log import add_orbit_entry, resolve_file
from core.config import iter_project_dirs

VALID_RECUR = {"daily", "weekly", "monthly", "weekdays"}


def _prompt_ring() -> Optional[str]:
    """Ask for ring time when adding a timed task/milestone. Returns ring value or None."""
    import sys
    if not sys.stdin.isatty():
        return "5m"
    try:
        ans = input("  🔔 ¿Recordatorio? [5m] (0=no): ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return "5m"
    if not ans:
        return "5m"
    if ans in ("0", "no", "n"):
        return None
    return ans


def _prompt_and_validate_ring() -> Optional[str]:
    """Prompt for ring and validate. Returns valid ring value or None."""
    ring = _prompt_ring()
    if ring:
        from core.ring import _parse_ring
        if _parse_ring(ring) is None:
            print(f"⚠️  Ring '{ring}' no válido, ignorando.")
            return None
    return ring


def _validate_add_params(date_val: Optional[str], time_val: Optional[str],
                         recur: Optional[str], until: Optional[str],
                         ring: Optional[str],
                         time_format: str = "simple") -> Optional[str]:
    """Validate common add parameters. Returns error message or None if valid.

    time_format: "simple" for HH:MM (task/ms), "event" for HH:MM[-HH:MM] (ev).
    Note: recur should be pre-normalized with _normalize_recur() before calling.
    """
    if date_val and not _valid_date(date_val):
        return f"⚠️  Fecha '{date_val}' no reconocida. Usa: YYYY-MM-DD, today, mañana, next monday, ..."
    if until and not _valid_date(until):
        return f"⚠️  Fecha --until '{until}' no reconocida."
    if recur and not is_valid_recur(recur):
        return f"⚠️  Recurrencia '{recur}' no válida. Usa: daily, weekly, monthly, weekdays, every 2 weeks, first monday, ..."
    if until and not recur:
        return "Error: --until requiere --recur."
    if ring and not date_val:
        return "⚠️  --ring requiere --date."
    if ring:
        from core.ring import _parse_ring
        if _parse_ring(ring) is None:
            return f"⚠️  Ring '{ring}' no válido. Usa: HH:MM, 1d, 2h, 30m, o YYYY-MM-DD HH:MM"
    if time_val and time_format == "simple":
        if not date_val:
            return "⚠️  --time requiere --date."
        if not re.match(r"^\d{2}:\d{2}$", time_val):
            return f"⚠️  Hora '{time_val}' no válida. Usa: HH:MM (ej. 15:00)"
    if time_val and time_format == "event":
        if not _valid_time(time_val):
            return f"⚠️  Hora '{time_val}' no válida. Usa: HH:MM o HH:MM-HH:MM (ej. 10:00, 10:00-12:30)"
    return None


def _valid_date(val: str) -> bool:
    """Check if a date string is a valid ISO date (YYYY-MM-DD)."""
    try:
        date.fromisoformat(val)
        return True
    except ValueError:
        return False


def _valid_time(val: str) -> bool:
    """Validate time spec: HH:MM or HH:MM-HH:MM."""
    pat = r'^\d{2}:\d{2}(-\d{2}:\d{2})?$'
    if not re.match(pat, val):
        return False
    parts = val.split("-")
    for p in parts:
        h, m = int(p[:2]), int(p[3:5])
        if h > 23 or m > 59:
            return False
    return True

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
_REM_HEADER  = "## 💬 Recordatorios"

# ── Task/milestone line parsing ────────────────────────────────────────────────

def _parse_task_line(line: str) -> Optional[dict]:
    """Parse - [ ]/[x]/[-] line → dict with status/desc/date/recur/ring."""
    m = re.match(r"^- \[( |x|-)\] (.+)$", line)
    if not m:
        return None
    status = {" ": "pending", "x": "done", "-": "cancelled"}[m.group(1)]
    rest   = m.group(2)

    date_val = recur = until = ring = time_val = None
    synced = False
    date_m = re.search(r"\((\d{4}-\d{2}-\d{2})\)", rest)
    if date_m:
        date_val = date_m.group(1)
    # Recur: emoji 🔄 or legacy [recur:]
    recur_m = re.search(r"🔄(\S+)", rest) or re.search(r"\[recur:([^\]]+)\]", rest)
    if recur_m:
        raw = recur_m.group(1)
        if ":" in raw:
            recur, until = raw.split(":", 1)
        else:
            recur = raw
    # Ring: emoji 🔔 or legacy [ring:]
    ring_m = re.search(r"🔔(\S+)", rest) or re.search(r"\[ring:([^\]]+)\]", rest)
    if ring_m:
        ring = ring_m.group(1)
    # Time: emoji ⏰ or legacy [time:]
    time_m = re.search(r"⏰(\S+)", rest) or re.search(r"\[time:([^\]]+)\]", rest)
    if time_m:
        time_val = time_m.group(1)
    # Synced: emoji ☁️ or legacy [G] or [gtask:]
    if re.search(r"☁️", rest) or re.search(r"\[G\]", rest) or re.search(r"\[gtask:[^\]]+\]", rest):
        synced = True

    # Description = rest minus attribute patterns (both emoji and legacy)
    desc = rest
    for pat in [r"\(\d{4}-\d{2}-\d{2}\)",
                r"🔄\S+", r"\[recur:[^\]]+\]",
                r"🔔\S+", r"\[ring:[^\]]+\]",
                r"⏰\S+", r"\[time:[^\]]+\]",
                r"☁️", r"\[G\]", r"\[gtask:[^\]]+\]"]:
        desc = re.sub(pat, "", desc)
    desc = desc.strip()

    return {"status": status, "desc": desc, "date": date_val,
            "recur": recur, "until": until, "ring": ring,
            "time": time_val, "synced": synced}


def _format_task_line(task: dict) -> str:
    """Serialize a task/milestone dict → markdown line."""
    char = {"pending": " ", "done": "x", "cancelled": "-"}[task["status"]]
    parts = [task["desc"]]
    if task.get("date"):
        parts.append(f"({task['date']})")
    if task.get("time"):
        parts.append(f"⏰{task['time']}")
    if task.get("recur"):
        recur_tag = task["recur"]
        if task.get("until"):
            recur_tag += f":{task['until']}"
        parts.append(f"🔄{recur_tag}")
    if task.get("ring"):
        parts.append(f"🔔{task['ring']}")
    if task.get("synced"):
        parts.append("☁️")
    return f"- [{char}] {' '.join(parts)}"


# ── Event line parsing ─────────────────────────────────────────────────────────

def _parse_event_line(line: str) -> Optional[dict]:
    """Parse YYYY-MM-DD — desc [end:YYYY-MM-DD] [recur:...] [ring:...] → dict."""
    m = re.match(r"^(\d{4}-\d{2}-\d{2})\s+—\s+(.+)$", line)
    if not m:
        return None
    date_val = m.group(1)
    rest     = m.group(2)
    end = recur = until = ring = time_val = None
    synced = False
    # End: emoji →YYYY-MM-DD or legacy [end:]
    end_m = re.search(r"→(\d{4}-\d{2}-\d{2})", rest) or re.search(r"\[end:(\d{4}-\d{2}-\d{2})\]", rest)
    if end_m:
        end  = end_m.group(1)
    # Time: emoji ⏰ or legacy [time:]
    time_m = re.search(r"⏰(\S+)", rest) or re.search(r"\[time:([^\]]+)\]", rest)
    if time_m:
        time_val = time_m.group(1)
    # Recur: emoji 🔄 or legacy [recur:]
    recur_m = re.search(r"🔄(\S+)", rest) or re.search(r"\[recur:([^\]]+)\]", rest)
    if recur_m:
        raw = recur_m.group(1)
        if ":" in raw:
            recur, until = raw.split(":", 1)
        else:
            recur = raw
    # Ring: emoji 🔔 or legacy [ring:]
    ring_m = re.search(r"🔔(\S+)", rest) or re.search(r"\[ring:([^\]]+)\]", rest)
    if ring_m:
        ring = ring_m.group(1)
    # Synced: emoji ☁️ or legacy [G] or [gcal:]
    if re.search(r"☁️", rest) or re.search(r"\[G\]", rest) or re.search(r"\[gcal:[^\]]+\]", rest):
        synced = True
    # Strip attribute tags from description (both emoji and legacy)
    for pat in [r"→\d{4}-\d{2}-\d{2}", r"\[end:[^\]]+\]",
                r"⏰\S+", r"\[time:[^\]]+\]",
                r"🔄\S+", r"\[recur:[^\]]+\]",
                r"🔔\S+", r"\[ring:[^\]]+\]",
                r"☁️", r"\[G\]", r"\[gcal:[^\]]+\]"]:
        rest = re.sub(pat, "", rest)
    rest = rest.strip()
    return {"date": date_val, "desc": rest, "end": end, "time": time_val,
            "recur": recur, "until": until, "ring": ring, "synced": synced}


def _format_event_line(ev: dict) -> str:
    """Serialize an event dict → markdown line."""
    line = f"{ev['date']} — {ev['desc']}"
    if ev.get("end"):
        line += f" →{ev['end']}"
    if ev.get("time"):
        line += f" ⏰{ev['time']}"
    if ev.get("recur"):
        recur_tag = ev["recur"]
        if ev.get("until"):
            recur_tag += f":{ev['until']}"
        line += f" 🔄{recur_tag}"
    if ev.get("ring"):
        line += f" 🔔{ev['ring']}"
    if ev.get("synced"):
        line += " ☁️"
    return line


# ── Reminder line parsing ──────────────────────────────────────────────────────

def _parse_reminder_line(line: str) -> Optional[dict]:
    """Parse - / [-] reminder line → dict with desc/date/time/recur."""
    m = re.match(r"^- (?:\[-\] )?(.+)$", line)
    if not m:
        return None
    rest = m.group(0)
    cancelled = rest.startswith("- [-]")
    rest = m.group(1)

    date_val = recur = until = time_val = None
    date_m = re.search(r"\((\d{4}-\d{2}-\d{2})\)", rest)
    if date_m:
        date_val = date_m.group(1)
    time_m = re.search(r"⏰(\S+)", rest) or re.search(r"\[time:([^\]]+)\]", rest)
    if time_m:
        time_val = time_m.group(1)
    recur_m = re.search(r"🔄(\S+)", rest) or re.search(r"\[recur:([^\]]+)\]", rest)
    if recur_m:
        raw = recur_m.group(1)
        if ":" in raw:
            recur, until = raw.split(":", 1)
        else:
            recur = raw

    desc = rest
    for pat in [r"\(\d{4}-\d{2}-\d{2}\)", r"⏰\S+", r"\[time:[^\]]+\]",
                r"🔄\S+", r"\[recur:[^\]]+\]"]:
        desc = re.sub(pat, "", desc)
    desc = desc.strip()

    if not date_val or not time_val:
        return None  # recordatorios require both date and time

    return {"desc": desc, "date": date_val, "time": time_val,
            "recur": recur, "until": until,
            "cancelled": cancelled}


def _format_reminder_line(rem: dict) -> str:
    """Serialize a reminder dict → markdown line."""
    prefix = "- [-] " if rem.get("cancelled") else "- "
    parts = [rem["desc"]]
    if rem.get("date"):
        parts.append(f"({rem['date']})")
    if rem.get("time"):
        parts.append(f"⏰{rem['time']}")
    if rem.get("recur"):
        recur_tag = rem["recur"]
        if rem.get("until"):
            recur_tag += f":{rem['until']}"
        parts.append(f"🔄{recur_tag}")
    return f"{prefix}{' '.join(parts)}"


# ── Agenda file I/O ────────────────────────────────────────────────────────────

def _read_agenda(path: Path) -> dict:
    """Parse agenda.md → {header, tasks, milestones, events, reminders}.

    Indented lines (4+ spaces or tab) after an item are collected as
    ``notes`` (list of strings, without the leading whitespace).
    """
    if not path.exists():
        return {"header": ["# Agenda"], "tasks": [], "milestones": [], "events": [], "reminders": []}

    lines   = path.read_text().splitlines()
    result  = {"header": [], "tasks": [], "milestones": [], "events": [], "reminders": []}
    section = None   # "tasks" | "milestones" | "events" | "reminders" | None
    last_item = None  # reference to last parsed item dict (for notes)

    for line in lines:
        # Indented line → append to previous item's notes
        # Accept 4+ spaces, tab, or zero-width space (Typora) as indentation
        stripped_zw = line.lstrip("\u200b")
        if last_item is not None and line and (
            line.startswith("    ") or line.startswith("\t") or
            stripped_zw.startswith("\t") or stripped_zw.startswith("    ")
        ):
            last_item.setdefault("notes", []).append(line.strip().strip("\u200b\t"))
            continue

        if section is None:
            # Collect header (everything before first ## section)
            if line == _TASK_HEADER:
                section = "tasks"; last_item = None
            elif line == _MS_HEADER:
                section = "milestones"; last_item = None
            elif line == _EV_HEADER:
                section = "events"; last_item = None
            elif line == _REM_HEADER:
                section = "reminders"; last_item = None
            else:
                result["header"].append(line)
        elif line == _TASK_HEADER:
            section = "tasks"; last_item = None
        elif line == _MS_HEADER:
            section = "milestones"; last_item = None
        elif line == _EV_HEADER:
            section = "events"; last_item = None
        elif line == _REM_HEADER:
            section = "reminders"; last_item = None
        elif not line.strip():
            continue   # skip blank lines inside sections (keep last_item for notes)
        elif section == "tasks":
            t = _parse_task_line(line)
            if t:
                result["tasks"].append(t)
                last_item = t
        elif section == "milestones":
            t = _parse_task_line(line)
            if t:
                result["milestones"].append(t)
                last_item = t
        elif section == "events":
            e = _parse_event_line(line)
            if e:
                result["events"].append(e)
                last_item = e
        elif section == "reminders":
            r = _parse_reminder_line(line)
            if r:
                result["reminders"].append(r)
                last_item = r

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
            for note in t.get("notes") or []:
                out.append(f"    {note}")
        out.append("")

    if data["milestones"]:
        out.append(_MS_HEADER)
        for ms in data["milestones"]:
            out.append(_format_task_line(ms))
            for note in ms.get("notes") or []:
                out.append(f"    {note}")
        out.append("")

    if data["events"]:
        out.append(_EV_HEADER)
        # Sort events by date
        for ev in sorted(data["events"], key=lambda e: e["date"]):
            out.append(_format_event_line(ev))
            for note in ev.get("notes") or []:
                out.append(f"    {note}")
        out.append("")

    if data.get("reminders"):
        out.append(_REM_HEADER)
        for rem in sorted(data["reminders"], key=lambda r: (r["date"], r["time"])):
            out.append(_format_reminder_line(rem))
        out.append("")

    from core.undo import save_snapshot
    save_snapshot(path)
    path.write_text("\n".join(out) + "\n")


# ── Interactive selection ──────────────────────────────────────────────────────

def _display_task(t: dict) -> str:
    date_s = f" ({t['date']})" if t.get("date") else ""
    return f"{t['desc']}{date_s}"

def _display_event(e: dict) -> str:
    end_s = f" → {e['end']}" if e.get("end") else ""
    return f"{e['date']} — {e['desc']}{end_s}"

def _display_reminder(r: dict) -> str:
    return f"{r['desc']} ({r['date']}) ⏰{r['time']}"


def _select_from_list(items: list, label: str, text: Optional[str],
                      display_fn, filter_fn=None,
                      match_fn=None) -> Optional[int]:
    """Generic interactive selection. Returns index in original *items* list.

    filter_fn(item) → bool: which items are selectable (default: all).
    display_fn(item) → str: how to display each item.
    match_fn(item, text) → bool: how to match text (default: case-insensitive substring on desc).
    """
    if filter_fn:
        sel_idx = [i for i, t in enumerate(items) if filter_fn(t)]
    else:
        sel_idx = list(range(len(items)))
    sel = [items[i] for i in sel_idx]

    if match_fn is None:
        match_fn = lambda item, txt: txt.lower() in item["desc"].lower()

    def _pick_from_matches(matches):
        """Show numbered list for ambiguous matches, return selected index or None."""
        print(f"Múltiples coincidencias{f' para {chr(39)}{text}{chr(39)}' if text else ''}:")
        for j, mi in enumerate(matches, 1):
            print(f"  {j}. {display_fn(sel[mi])}")
        if not sys.stdin.isatty():
            return None
        try:
            raw = input("Selecciona (#): ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return None
        if raw.isdigit():
            idx = int(raw) - 1
            if 0 <= idx < len(matches):
                return sel_idx[matches[idx]]
        print("Cancelado.")
        return None

    if text:
        matches = [i for i, t in enumerate(sel) if match_fn(t, text)]
        if not matches:
            print(f"Error: no se encontró '{text}'")
            return None
        if len(matches) == 1:
            return sel_idx[matches[0]]
        return _pick_from_matches(matches)

    if not sel:
        print(f"No hay {label}.")
        return None

    print(f"\n{label}:")
    for i, t in enumerate(sel, 1):
        print(f"  {i}. {display_fn(t)}")
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
        if 0 <= idx < len(sel):
            return sel_idx[idx]
        print(f"Fuera de rango (1–{len(sel)})")
        return None
    matches = [i for i, t in enumerate(sel) if match_fn(t, raw)]
    if not matches:
        print(f"Sin coincidencias para '{raw}'")
        return None
    if len(matches) == 1:
        return sel_idx[matches[0]]
    return _pick_from_matches(matches)


def _select_item(items: list, label: str, text: Optional[str] = None) -> Optional[int]:
    """Select a pending task or milestone by text or interactive list."""
    return _select_from_list(items, label, text,
                             display_fn=_display_task,
                             filter_fn=lambda t: t["status"] == "pending")


def _select_event(events: list, text: Optional[str]) -> Optional[int]:
    """Select an event by text or interactive list."""
    return _select_from_list(events, "Eventos", text,
                             display_fn=_display_event)


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


def _ask_edit_occurrence_or_series(desc: str, recur: str,
                                   force: bool, occurrence: bool,
                                   series: bool) -> Optional[bool]:
    """Decide whether to edit only this occurrence or the whole series.

    Returns True for occurrence, False for series, None for cancel.
    """
    if occurrence or series:
        return occurrence  # explicit flag
    if not force:
        if not sys.stdin.isatty():
            print("Error: usa --force para confirmar en modo no interactivo.")
            return None
        try:
            ans = input(
                f"\"{desc}\" es recurrente ({recur}).\n"
                f"  [o] Editar solo esta ocurrencia (crear copia editada + avanzar serie)\n"
                f"  [s] Editar toda la serie\n"
                f"  [c] Cancelar\n"
                f"  ¿Qué hacer? [o/s/C]: "
            ).strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            return None
        if ans in ("o", "ocurrencia"):
            return True
        if ans in ("s", "serie"):
            return False
        print("Cancelado.")
        return None
    # --force without -o/-s: safe default = occurrence
    return True


# ── TASK commands ──────────────────────────────────────────────────────────────

def run_task_add(project: str, text: str, date_val: Optional[str] = None,
                 recur: Optional[str] = None, until: Optional[str] = None,
                 ring: Optional[str] = None, time_val: Optional[str] = None,
                 desc: Optional[str] = None) -> int:
    if recur:
        recur = _normalize_recur(recur)
    err = _validate_add_params(date_val, time_val, recur, until, ring)
    if err:
        print(err)
        return 1
    if date_val and time_val and not ring:
        ring = _prompt_and_validate_ring()

    project_dir = _find_new_project(project)
    if project_dir is None:
        return 1

    agenda_path = resolve_file(project_dir, "agenda")
    data = _read_agenda(agenda_path)
    notes = [desc] if desc else []
    new_task = {"status": "pending", "desc": text,
                "date": date_val, "recur": recur,
                "until": until, "ring": ring, "time": time_val, "notes": notes}
    data["tasks"].append(new_task)
    _write_agenda(agenda_path, data)

    attrs = ""
    if date_val: attrs += f" ({date_val})"
    if time_val: attrs += f" ⏰{time_val}"
    if recur:
        recur_s = recur
        if until:
            recur_s += f":{until}"
        attrs += f" 🔄{recur_s}"
    if ring:     attrs += f" 🔔{ring}"
    print(f"✓ [{project_dir.name}] Tarea: {text}{attrs}")

    # Schedule reminder immediately if ring fires today
    if ring:
        from core.ring import resolve_ring_datetime, _schedule_reminder
        ring_dt = resolve_ring_datetime(date_val, ring, due_time=time_val)
        if ring_dt and ring_dt.date() == date.today():
            ok = _schedule_reminder(text, project_dir.name, ring_dt, kind="task")
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
                                   "until": until, "ring": task.get("ring"),
                                   "notes": list(task.get("notes") or [])})
            next_info = f" (recur: {task['recur']}) → próxima: {next_due}"

    _write_agenda(agenda_path, data)
    add_orbit_entry(project_dir, f"[completada] Tarea: {task_desc}{next_info}", "apunte")
    print(f"✓ [{project_dir.name}] [completada] {task_desc}{next_info}")

    # Sync completed task to Google
    from core.gsync import sync_item
    sync_item(project_dir, task, "task")

    return 0


def run_task_drop(project: Optional[str], text: Optional[str],
                  force: bool = False, occurrence: bool = False,
                  series: bool = False) -> int:
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

    task = data["tasks"][idx]
    task_desc = task["desc"]
    drop_series = series

    if occurrence or series:
        # Explicit flag — skip interactive prompt
        pass
    elif not force:
        if not sys.stdin.isatty():
            print("Error: usa --force para confirmar en modo no interactivo.")
            return 1
        if task.get("recur"):
            try:
                ans = input(
                    f"\"{task_desc}\" es recurrente ({task['recur']}).\n"
                    f"  [o] Quitar esta ocurrencia (avanzar al próximo)\n"
                    f"  [s] Eliminar toda la serie\n"
                    f"  [c] Cancelar\n"
                    f"  ¿Qué hacer? [o/s/C]: "
                ).strip().lower()
            except (EOFError, KeyboardInterrupt):
                print()
                return 1
            if ans in ("s", "serie"):
                drop_series = True
            elif ans in ("o", "ocurrencia"):
                drop_series = False
            else:
                print("Cancelado.")
                return 0
        else:
            try:
                ans = input(f"¿Cancelar tarea \"{task_desc}\"? [s/N]: ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                print()
                return 1
            if ans not in ("s", "si", "sí", "y", "yes"):
                print("Cancelado.")
                return 0

    task["status"] = "cancelled"

    next_info = ""
    if task.get("recur") and not drop_series:
        today_str = date.today().isoformat()
        next_due = _next_occurrence(task.get("date"), task["recur"], today_str)
        until = task.get("until")
        if until and date.fromisoformat(next_due) > date.fromisoformat(until):
            next_info = f" (recur: {task['recur']}) — serie finalizada ({until})"
        else:
            data["tasks"].append({"status": "pending", "desc": task_desc,
                                   "date": next_due, "recur": task["recur"],
                                   "until": until, "ring": task.get("ring"),
                                   "notes": list(task.get("notes") or [])})
            next_info = f" (recur: {task['recur']}) → próxima: {next_due}"

    _write_agenda(agenda_path, data)

    if drop_series:
        add_orbit_entry(project_dir, f"[serie cancelada] Tarea: {task_desc} ({task['recur']})", "apunte")
        print(f"✓ [{project_dir.name}] [serie cancelada] {task_desc} ({task['recur']})")
    else:
        add_orbit_entry(project_dir, f"[cancelada] Tarea: {task_desc}{next_info}", "apunte")
        print(f"✓ [{project_dir.name}] [cancelada] {task_desc}{next_info}")

    # Delete Mac reminder if ring was firing today
    if task.get("ring") and task.get("date"):
        from core.ring import resolve_ring_datetime, _delete_reminder
        ring_dt = resolve_ring_datetime(task["date"], task["ring"],
                                        due_time=task.get("time"))
        if ring_dt and ring_dt.date() == date.today():
            _delete_reminder(task_desc, project_dir.name, kind="task")

    # Sync cancelled task to Google
    from core.gsync import sync_item
    sync_item(project_dir, task, "task")

    return 0


def run_task_edit(project: Optional[str], text: Optional[str],
                  new_text: Optional[str] = None, new_date: Optional[str] = None,
                  new_recur: Optional[str] = None, new_until: Optional[str] = None,
                  new_ring: Optional[str] = None, new_time: Optional[str] = None,
                  new_desc: Optional[str] = None,
                  force: bool = False, occurrence: bool = False,
                  series: bool = False) -> int:
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
            print(f"⚠️  Ring '{new_ring}' no válido. Usa: HH:MM, 1d, 2h, 30m, o YYYY-MM-DD HH:MM")
            return 1
    if new_time and new_time != "none" and not re.match(r"^\d{2}:\d{2}$", new_time):
        print(f"⚠️  Hora '{new_time}' no válida. Usa: HH:MM (ej. 15:00)")
        return 1

    agenda_path = resolve_file(project_dir, "agenda")
    data = _read_agenda(agenda_path)

    idx = _select_item(data["tasks"], "Tareas pendientes", text)
    if idx is None:
        return 1

    task = data["tasks"][idx]
    old_desc = task["desc"]

    # ── Occurrence vs Series for recurring items ──
    if task.get("recur") and not (new_recur and new_recur == "none"):
        choice = _ask_edit_occurrence_or_series(
            task["desc"], task["recur"], force, occurrence, series)
        if choice is None:
            return 1 if not sys.stdin.isatty() else 0
        if choice:  # occurrence
            today_str = date.today().isoformat()
            next_due = _next_occurrence(task.get("date"), task["recur"], today_str)
            until = task.get("until")
            # Create a non-recurring copy with edits
            new_item = {
                "status": "pending",
                "desc": new_text or task["desc"],
                "date": (None if new_date == "none" else new_date) if new_date else task.get("date"),
                "time": (None if new_time == "none" else new_time) if new_time else task.get("time"),
                "ring": (None if new_ring == "none" else new_ring) if new_ring else task.get("ring"),
                "notes": ([new_desc] if new_desc and new_desc != "none" else []) if new_desc is not None else list(task.get("notes") or []),
            }
            data["tasks"].append(new_item)
            # Advance the series
            if until and date.fromisoformat(next_due) > date.fromisoformat(until):
                task["status"] = "cancelled"
                next_info = f" — serie finalizada ({until})"
            else:
                task["date"] = next_due
                next_info = f" → serie avanza a {next_due}"
            _write_agenda(agenda_path, data)
            print(f"✓ [{project_dir.name}] Ocurrencia editada: {new_item['desc']}{next_info}")
            from core.gsync import sync_item
            sync_item(project_dir, new_item, "task")
            sync_item(project_dir, task, "task")
            return 0

    # ── Series path (or non-recurring) ──
    if new_text:  task["desc"]  = new_text
    if new_date:
        task["date"]  = None if new_date == "none" else new_date
    if new_recur:
        task["recur"] = None if new_recur == "none" else new_recur
    if new_until:
        task["until"] = None if new_until == "none" else new_until
    if new_ring:
        task["ring"]  = None if new_ring  == "none" else new_ring
    if new_time:
        task["time"]  = None if new_time  == "none" else new_time
    if new_desc is not None:
        task["notes"] = [new_desc] if new_desc and new_desc != "none" else []

    _write_agenda(agenda_path, data)
    print(f"✓ [{project_dir.name}] Tarea actualizada: {task['desc']}")

    # Update Mac reminder if ring fires today
    if task.get("ring") and task.get("date"):
        from core.ring import resolve_ring_datetime, _schedule_reminder, _delete_reminder
        ring_dt = resolve_ring_datetime(task["date"], task["ring"],
                                        due_time=task.get("time"))
        if ring_dt and ring_dt.date() == date.today():
            if new_text or new_time or new_ring:
                _delete_reminder(old_desc, project_dir.name, kind="task")
            ok = _schedule_reminder(task["desc"], project_dir.name, ring_dt, kind="task")
            if ok:
                print(f"  ⏰ Recordatorio programado: {ring_dt.strftime('%H:%M')}")

    # Sync updated task to Google
    from core.gsync import sync_item
    sync_item(project_dir, task, "task")

    return 0


def run_task_list(projects: Optional[list] = None,
                  status_filter: str = "pending",
                  date_filter: Optional[str] = None,
                  dated_only: bool = False) -> int:
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
        dirs = [d for d in iter_project_dirs() if _is_new_project(d)]

    total = 0
    for project_dir in dirs:
        data  = _read_agenda(resolve_file(project_dir, "agenda"))
        tasks = data["tasks"]

        if status_filter != "all":
            tasks = [t for t in tasks if t["status"] == status_filter]
        if date_filter:
            tasks = [t for t in tasks if t.get("date", "").startswith(date_filter)]
        if dated_only:
            tasks = [t for t in tasks if t.get("date")]

        if not tasks:
            continue

        print(f"\n[{project_dir.name}]")
        for t in tasks:
            status_s = {"pending": "[ ]", "done": "[x]", "cancelled": "[-]"}[t["status"]]
            date_s   = f" ({t['date']})" if t.get("date") else ""
            recur_s = ""
            if t.get("recur"):
                recur_s = f" 🔄{t['recur']}"
                if t.get("until"):
                    recur_s += f":{t['until']}"
            ring_s   = f" 🔔{t['ring']}"   if t.get("ring")  else ""
            print(f"  {status_s} {t['desc']}{date_s}{recur_s}{ring_s}")
            total += 1

    if not total:
        sf = f" ({status_filter})" if status_filter != "all" else ""
        print(f"No hay tareas{sf}.")
    else:
        print()
    return 0


def run_task_log(project: Optional[str], text: Optional[str]) -> int:
    """Create a logbook entry (#apunte) from an existing task."""
    project_dir = _find_new_project(project) if project else None
    if project and project_dir is None:
        return 1
    if project_dir is None:
        print("Error: especifica un proyecto")
        return 1

    data = _read_agenda(resolve_file(project_dir, "agenda"))
    idx = _select_item(data["tasks"], "Tareas pendientes", text)
    if idx is None:
        return 1

    task = data["tasks"][idx]
    from core.log import add_entry
    return add_entry(project, task["desc"], "apunte", None, task.get("date"))


# ── MILESTONE commands ─────────────────────────────────────────────────────────

def run_ms_add(project: str, text: str, date_val: Optional[str] = None,
               recur: Optional[str] = None, until: Optional[str] = None,
               ring: Optional[str] = None, time_val: Optional[str] = None,
               desc: Optional[str] = None) -> int:
    if recur:
        recur = _normalize_recur(recur)
    err = _validate_add_params(date_val, time_val, recur, until, ring)
    if err:
        print(err)
        return 1
    if date_val and time_val and not ring:
        ring = _prompt_and_validate_ring()

    project_dir = _find_new_project(project)
    if project_dir is None:
        return 1

    agenda_path = resolve_file(project_dir, "agenda")
    data = _read_agenda(agenda_path)
    notes = [desc] if desc else []
    new_ms = {"status": "pending", "desc": text,
              "date": date_val, "recur": recur, "until": until, "ring": ring,
              "time": time_val, "notes": notes}
    data["milestones"].append(new_ms)
    _write_agenda(agenda_path, data)

    attrs = ""
    if date_val: attrs += f" ({date_val})"
    if time_val: attrs += f" ⏰{time_val}"
    if recur:
        recur_s = recur
        if until: recur_s += f":{until}"
        attrs += f" 🔄{recur_s}"
    if ring:     attrs += f" 🔔{ring}"
    print(f"✓ [{project_dir.name}] Hito: {text}{attrs}")

    # Schedule reminder immediately if ring fires today
    if ring:
        from core.ring import resolve_ring_datetime, _schedule_reminder
        ring_dt = resolve_ring_datetime(date_val, ring, due_time=time_val)
        if ring_dt and ring_dt.date() == date.today():
            ok = _schedule_reminder(text, project_dir.name, ring_dt, kind="milestone")
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
    add_orbit_entry(project_dir, f"[alcanzado] Hito: {ms_desc}", "resultado")
    print(f"✓ [{project_dir.name}] [alcanzado] {ms_desc}")

    from core.gsync import sync_item
    sync_item(project_dir, ms, "milestone")

    return 0


def run_ms_drop(project: Optional[str], text: Optional[str],
                force: bool = False, occurrence: bool = False,
                series: bool = False) -> int:
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
    drop_series = series

    if occurrence or series:
        # Explicit flag — skip interactive prompt
        pass
    elif not force:
        if not sys.stdin.isatty():
            print("Error: usa --force para confirmar en modo no interactivo.")
            return 1
        if ms.get("recur"):
            try:
                ans = input(
                    f"\"{ms_desc}\" es recurrente ({ms['recur']}).\n"
                    f"  [o] Quitar esta ocurrencia (avanzar al próximo)\n"
                    f"  [s] Eliminar toda la serie\n"
                    f"  [c] Cancelar\n"
                    f"  ¿Qué hacer? [o/s/C]: "
                ).strip().lower()
            except (EOFError, KeyboardInterrupt):
                print()
                return 1
            if ans in ("s", "serie"):
                drop_series = True
            elif ans in ("o", "ocurrencia"):
                drop_series = False
            else:
                print("Cancelado.")
                return 0
        else:
            try:
                ans = input(f"¿Cancelar hito \"{ms_desc}\"? [s/N]: ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                print()
                return 1
            if ans not in ("s", "si", "sí", "y", "yes"):
                print("Cancelado.")
                return 0

    ms["status"] = "cancelled"

    next_info = ""
    if ms.get("recur") and not drop_series:
        today_str = date.today().isoformat()
        next_due = _next_occurrence(ms.get("date"), ms["recur"], today_str)
        until = ms.get("until")
        if until and date.fromisoformat(next_due) > date.fromisoformat(until):
            next_info = f" (recur: {ms['recur']}) — serie finalizada ({until})"
        else:
            data["milestones"].append({"status": "pending", "desc": ms_desc,
                                        "date": next_due, "recur": ms["recur"],
                                        "until": until, "ring": ms.get("ring"),
                                        "notes": list(ms.get("notes") or [])})
            next_info = f" (recur: {ms['recur']}) → próximo: {next_due}"

    _write_agenda(agenda_path, data)

    if drop_series:
        add_orbit_entry(project_dir, f"[serie cancelada] Hito: {ms_desc} ({ms['recur']})", "apunte")
        print(f"✓ [{project_dir.name}] [serie cancelada] {ms_desc} ({ms['recur']})")
    else:
        add_orbit_entry(project_dir, f"[cancelado] Hito: {ms_desc}{next_info}", "apunte")
        print(f"✓ [{project_dir.name}] [cancelado] {ms_desc}{next_info}")

    # Delete Mac reminder if ring was firing today
    if ms.get("ring") and ms.get("date"):
        from core.ring import resolve_ring_datetime, _delete_reminder
        ring_dt = resolve_ring_datetime(ms["date"], ms["ring"],
                                        due_time=ms.get("time"))
        if ring_dt and ring_dt.date() == date.today():
            _delete_reminder(ms_desc, project_dir.name, kind="milestone")

    from core.gsync import sync_item
    sync_item(project_dir, ms, "milestone")

    return 0


def run_ms_edit(project: Optional[str], text: Optional[str],
                new_text: Optional[str] = None, new_date: Optional[str] = None,
                new_recur: Optional[str] = None, new_until: Optional[str] = None,
                new_ring: Optional[str] = None, new_time: Optional[str] = None,
                new_desc: Optional[str] = None,
                force: bool = False, occurrence: bool = False,
                series: bool = False) -> int:
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
            print(f"⚠️  Ring '{new_ring}' no válido. Usa: HH:MM, 1d, 2h, 30m, o YYYY-MM-DD HH:MM")
            return 1
    if new_time and new_time != "none" and not re.match(r"^\d{2}:\d{2}$", new_time):
        print(f"⚠️  Hora '{new_time}' no válida. Usa: HH:MM (ej. 15:00)")
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
    old_desc = ms["desc"]

    # ── Occurrence vs Series for recurring items ──
    if ms.get("recur") and not (new_recur and new_recur == "none"):
        choice = _ask_edit_occurrence_or_series(
            ms["desc"], ms["recur"], force, occurrence, series)
        if choice is None:
            return 1 if not sys.stdin.isatty() else 0
        if choice:  # occurrence
            today_str = date.today().isoformat()
            next_due = _next_occurrence(ms.get("date"), ms["recur"], today_str)
            until = ms.get("until")
            new_item = {
                "status": "pending",
                "desc": new_text or ms["desc"],
                "date": (None if new_date == "none" else new_date) if new_date else ms.get("date"),
                "time": (None if new_time == "none" else new_time) if new_time else ms.get("time"),
                "ring": (None if new_ring == "none" else new_ring) if new_ring else ms.get("ring"),
                "notes": ([new_desc] if new_desc and new_desc != "none" else []) if new_desc is not None else list(ms.get("notes") or []),
            }
            data["milestones"].append(new_item)
            if until and date.fromisoformat(next_due) > date.fromisoformat(until):
                ms["status"] = "cancelled"
                next_info = f" — serie finalizada ({until})"
            else:
                ms["date"] = next_due
                next_info = f" → serie avanza a {next_due}"
            _write_agenda(agenda_path, data)
            print(f"✓ [{project_dir.name}] Ocurrencia editada: {new_item['desc']}{next_info}")
            from core.gsync import sync_item
            sync_item(project_dir, new_item, "milestone")
            sync_item(project_dir, ms, "milestone")
            return 0

    # ── Series path (or non-recurring) ──
    if new_text:  ms["desc"]  = new_text
    if new_date:  ms["date"]  = None if new_date  == "none" else new_date
    if new_recur: ms["recur"] = None if new_recur == "none" else new_recur
    if new_until: ms["until"] = None if new_until == "none" else new_until
    if new_ring:  ms["ring"]  = None if new_ring  == "none" else new_ring
    if new_time:  ms["time"]  = None if new_time  == "none" else new_time
    if new_desc is not None:
        ms["notes"] = [new_desc] if new_desc and new_desc != "none" else []

    _write_agenda(agenda_path, data)
    print(f"✓ [{project_dir.name}] Hito actualizado: {ms['desc']}")

    # Update Mac reminder if ring fires today
    if ms.get("ring") and ms.get("date"):
        from core.ring import resolve_ring_datetime, _schedule_reminder, _delete_reminder
        ring_dt = resolve_ring_datetime(ms["date"], ms["ring"],
                                        due_time=ms.get("time"))
        if ring_dt and ring_dt.date() == date.today():
            if new_text or new_time or new_ring:
                _delete_reminder(old_desc, project_dir.name, kind="milestone")
            ok = _schedule_reminder(ms["desc"], project_dir.name, ring_dt, kind="milestone")
            if ok:
                print(f"  ⏰ Recordatorio programado: {ring_dt.strftime('%H:%M')}")

    from core.gsync import sync_item
    sync_item(project_dir, ms, "milestone")

    return 0


def run_ms_list(projects: Optional[list] = None, status_filter: str = "pending",
                dated_only: bool = False) -> int:
    if projects:
        dirs = []
        for p in projects:
            d = _find_new_project(p)
            if d:
                dirs.append(d)
        if not dirs:
            return 1
    else:
        dirs = [d for d in iter_project_dirs() if _is_new_project(d)]

    total = 0
    for project_dir in dirs:
        data = _read_agenda(resolve_file(project_dir, "agenda"))
        mss  = data["milestones"]

        if status_filter != "all":
            mss = [ms for ms in mss if ms["status"] == status_filter]
        if dated_only:
            mss = [ms for ms in mss if ms.get("date")]
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


def run_ms_log(project: Optional[str], text: Optional[str]) -> int:
    """Create a logbook entry (#resultado) from an existing milestone."""
    project_dir = _find_new_project(project) if project else None
    if project and project_dir is None:
        return 1
    if project_dir is None:
        print("Error: especifica un proyecto")
        return 1

    data = _read_agenda(resolve_file(project_dir, "agenda"))
    idx = _select_item(data["milestones"], "Hitos pendientes", text)
    if idx is None:
        return 1

    ms = data["milestones"][idx]
    from core.log import add_entry
    return add_entry(project, ms["desc"], "resultado", None, ms.get("date"))


# ── EVENT commands ─────────────────────────────────────────────────────────────

def run_ev_add(project: str, text: str, date_val: str,
               end_date: Optional[str] = None, time_val: Optional[str] = None,
               recur: Optional[str] = None,
               until: Optional[str] = None, ring: Optional[str] = None,
               desc: Optional[str] = None) -> int:
    if end_date and not _valid_date(end_date):
        print(f"⚠️  Fecha --end '{end_date}' no reconocida. Usa: YYYY-MM-DD, today, mañana, next monday, ...")
        return 1
    if recur:
        recur = _normalize_recur(recur)
    err = _validate_add_params(date_val, time_val, recur, until, ring, time_format="event")
    if err:
        print(err)
        return 1
    if time_val and not ring:
        ring = _prompt_and_validate_ring()

    project_dir = _find_new_project(project)
    if project_dir is None:
        return 1

    agenda_path = resolve_file(project_dir, "agenda")
    data = _read_agenda(agenda_path)
    notes = [desc] if desc else []
    new_ev = {"date": date_val, "desc": text, "end": end_date,
              "time": time_val, "recur": recur, "until": until, "ring": ring,
              "notes": notes}
    data["events"].append(new_ev)
    _write_agenda(agenda_path, data)

    attrs = ""
    if time_val: attrs += f" ⏰{time_val}"
    if end_date: attrs += f" →{end_date}"
    if recur:
        recur_s = recur
        if until: recur_s += f":{until}"
        attrs += f" 🔄{recur_s}"
    if ring: attrs += f" 🔔{ring}"
    print(f"✓ [{project_dir.name}] Evento: {date_val} — {text}{attrs}")

    # Schedule reminder immediately if ring fires today
    if ring:
        from core.ring import resolve_ring_datetime, _schedule_reminder
        # For events, use start time from time_val (e.g. "09:00" or "09:00-10:00")
        ev_time = time_val.split("-")[0] if time_val else None
        ring_dt = resolve_ring_datetime(date_val, ring, due_time=ev_time)
        if ring_dt and ring_dt.date() == date.today():
            ok = _schedule_reminder(text, project_dir.name, ring_dt, kind="event")
            if ok:
                print(f"  ⏰ Recordatorio programado: {ring_dt.strftime('%H:%M')}")

    from core.gsync import sync_item
    sync_item(project_dir, new_ev, "event")

    return 0


def run_ev_drop(project: Optional[str], text: Optional[str],
                force: bool = False, occurrence: bool = False,
                series: bool = False) -> int:
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

    drop_series = series  # For recurring: drop whole series?

    if occurrence or series:
        # Explicit flag — skip interactive prompt
        pass
    elif not force:
        if not sys.stdin.isatty():
            print("Error: usa --force para confirmar el borrado en modo no interactivo.")
            return 1
        if ev.get("recur"):
            # Recurring event: ask whether to drop occurrence or whole series
            try:
                ans = input(
                    f"\"{display}\" es recurrente ({ev['recur']}).\n"
                    f"  [o] Quitar esta ocurrencia (avanzar al próximo)\n"
                    f"  [s] Eliminar toda la serie\n"
                    f"  [c] Cancelar\n"
                    f"  ¿Qué hacer? [o/s/C]: "
                ).strip().lower()
            except (EOFError, KeyboardInterrupt):
                print()
                return 1
            if ans in ("s", "serie"):
                drop_series = True
            elif ans in ("o", "ocurrencia"):
                drop_series = False
            else:
                print("Cancelado.")
                return 0
        else:
            try:
                ans = input(f"¿Seguro que quieres eliminar \"{display}\"? [s/N]: ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                print()
                return 1
            if ans not in ("s", "si", "sí", "y", "yes"):
                print("Cancelado.")
                return 0

    ev_removed = data["events"].pop(idx)

    next_info = ""
    if ev_removed.get("recur") and not drop_series:
        today_str = date.today().isoformat()
        next_due = _next_occurrence(ev_removed.get("date"), ev_removed["recur"], today_str)
        until = ev_removed.get("until")
        if until and date.fromisoformat(next_due) > date.fromisoformat(until):
            next_info = f" (recur: {ev_removed['recur']}) — serie finalizada ({until})"
        else:
            new_ev = {k: v for k, v in ev_removed.items() if k != "synced"}
            new_ev["date"] = next_due
            data["events"].append(new_ev)
            next_info = f" (recur: {ev_removed['recur']}) → próximo: {next_due}"

    _write_agenda(agenda_path, data)

    if drop_series:
        print(f"✓ [{project_dir.name}] Serie eliminada: {display} ({ev_removed['recur']})")
        # Delete whole series from Google Calendar
        if ev_removed.get("synced"):
            from core.gsync import delete_gcal_event
            delete_gcal_event(project_dir, ev_removed)
    else:
        print(f"✓ [{project_dir.name}] Evento eliminado: {display}{next_info}")
        # Recurring: don't delete Google series (gsync will update start date)
        # Non-recurring: delete from Google Calendar
        if not ev_removed.get("recur") and ev_removed.get("synced"):
            from core.gsync import delete_gcal_event
            delete_gcal_event(project_dir, ev_removed)

    # Delete Mac reminder if ring was firing today
    if ev_removed.get("ring") and ev_removed.get("date"):
        from core.ring import resolve_ring_datetime, _delete_reminder
        ev_time = ev_removed.get("time", "").split("-")[0] if ev_removed.get("time") else None
        ring_dt = resolve_ring_datetime(ev_removed["date"], ev_removed["ring"],
                                        due_time=ev_time)
        if ring_dt and ring_dt.date() == date.today():
            _delete_reminder(ev_removed["desc"], project_dir.name, kind="event")

    return 0


def run_ev_edit(project: Optional[str], text: Optional[str],
                new_text: Optional[str] = None, new_date: Optional[str] = None,
                new_end: Optional[str] = None, new_time: Optional[str] = None,
                new_recur: Optional[str] = None,
                new_until: Optional[str] = None, new_ring: Optional[str] = None,
                new_desc: Optional[str] = None,
                force: bool = False, occurrence: bool = False,
                series: bool = False) -> int:
    if new_date and not _valid_date(new_date):
        print(f"⚠️  Fecha '{new_date}' no reconocida. Usa: YYYY-MM-DD, today, mañana, next monday, ...")
        return 1
    if new_end and new_end != "none" and not _valid_date(new_end):
        print(f"⚠️  Fecha --end '{new_end}' no reconocida. Usa: YYYY-MM-DD, today, mañana, next monday, ...")
        return 1
    if new_time and new_time != "none" and not _valid_time(new_time):
        print(f"⚠️  Hora '{new_time}' no válida. Usa: HH:MM o HH:MM-HH:MM (ej. 10:00, 10:00-12:30)")
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
            print(f"⚠️  Ring '{new_ring}' no válido. Usa: HH:MM, 1d, 2h, 30m, o YYYY-MM-DD HH:MM")
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
    old_desc = ev["desc"]

    # ── Occurrence vs Series for recurring items ──
    if ev.get("recur") and not (new_recur and new_recur == "none"):
        choice = _ask_edit_occurrence_or_series(
            ev["desc"], ev["recur"], force, occurrence, series)
        if choice is None:
            return 1 if not sys.stdin.isatty() else 0
        if choice:  # occurrence
            today_str = date.today().isoformat()
            next_due = _next_occurrence(ev.get("date"), ev["recur"], today_str)
            until = ev.get("until")
            new_item = {
                "desc": new_text or ev["desc"],
                "date": (None if new_date == "none" else new_date) if new_date else ev.get("date"),
                "end": (None if new_end == "none" else new_end) if new_end else ev.get("end"),
                "time": (None if new_time == "none" else new_time) if new_time else ev.get("time"),
                "ring": (None if new_ring == "none" else new_ring) if new_ring else ev.get("ring"),
                "notes": ([new_desc] if new_desc and new_desc != "none" else []) if new_desc is not None else list(ev.get("notes") or []),
            }
            data["events"].append(new_item)
            if until and date.fromisoformat(next_due) > date.fromisoformat(until):
                data["events"].remove(ev)
                next_info = f" — serie finalizada ({until})"
            else:
                ev["date"] = next_due
                next_info = f" → serie avanza a {next_due}"
            _write_agenda(agenda_path, data)
            print(f"✓ [{project_dir.name}] Ocurrencia editada: {new_item['date']} — {new_item['desc']}{next_info}")
            from core.gsync import sync_item
            sync_item(project_dir, new_item, "event")
            sync_item(project_dir, ev, "event")
            return 0

    # ── Series path (or non-recurring) ──
    if new_text:  ev["desc"]  = new_text
    if new_date:  ev["date"]  = new_date
    if new_end:   ev["end"]   = None if new_end   == "none" else new_end
    if new_time:  ev["time"]  = None if new_time  == "none" else new_time
    if new_recur: ev["recur"] = None if new_recur == "none" else new_recur
    if new_until: ev["until"] = None if new_until == "none" else new_until
    if new_ring:  ev["ring"]  = None if new_ring  == "none" else new_ring
    if new_desc is not None:
        ev["notes"] = [new_desc] if new_desc and new_desc != "none" else []

    _write_agenda(agenda_path, data)
    print(f"✓ [{project_dir.name}] Evento actualizado: {ev['date']} — {ev['desc']}")

    # Update Mac reminder if ring fires today
    if ev.get("ring") and ev.get("date"):
        from core.ring import resolve_ring_datetime, _schedule_reminder, _delete_reminder
        ev_time = ev.get("time", "").split("-")[0] if ev.get("time") else None
        ring_dt = resolve_ring_datetime(ev["date"], ev["ring"], due_time=ev_time)
        if ring_dt and ring_dt.date() == date.today():
            if new_text or new_time or new_ring:
                _delete_reminder(old_desc, project_dir.name, kind="event")
            ok = _schedule_reminder(ev["desc"], project_dir.name, ring_dt, kind="event")
            if ok:
                print(f"  ⏰ Recordatorio programado: {ring_dt.strftime('%H:%M')}")

    from core.gsync import sync_item
    sync_item(project_dir, ev, "event")

    return 0


def run_ev_log(project: Optional[str], text: Optional[str]) -> int:
    """Create a logbook entry (#evento) from an existing event."""
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
    ev_desc = ev["desc"]
    ev_date = ev.get("date")

    from core.log import add_entry
    return add_entry(
        project, ev_desc, "evento", None, ev_date,
    )


def run_ev_list(project: Optional[str] = None,
                period_from: Optional[str] = None,
                period_to:   Optional[str] = None) -> int:
    if project:
        project_dir = _find_new_project(project)
        if project_dir is None:
            return 1
        dirs = [project_dir]
    else:
        dirs = [d for d in iter_project_dirs() if _is_new_project(d)]

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


# ── Reminder commands ─────────────────────────────────────────────────────────

def run_reminder_add(project: str, text: str, date_val: str,
                     time_val: str,
                     recur: Optional[str] = None,
                     until: Optional[str] = None,
                     desc: Optional[str] = None) -> int:
    """Add a reminder to a project's agenda."""
    if recur:
        recur = _normalize_recur(recur)
    err = _validate_add_params(date_val, time_val, recur, until, None)
    if err:
        print(err)
        return 1

    project_dir = _find_new_project(project)
    if project_dir is None:
        return 1

    agenda_path = resolve_file(project_dir, "agenda")
    data = _read_agenda(agenda_path)
    notes = [desc] if desc else []
    new_rem = {"desc": text, "date": date_val, "time": time_val,
               "recur": recur, "until": until, "cancelled": False,
               "notes": notes}
    data.setdefault("reminders", []).append(new_rem)
    _write_agenda(agenda_path, data)

    attrs = f"({date_val}) ⏰{time_val}"
    if recur:
        recur_s = recur
        if until:
            recur_s += f":{until}"
        attrs += f" 🔄{recur_s}"
    print(f"✓ [{project_dir.name}] Recordatorio: {text} {attrs}")

    # Schedule notification immediately if it fires today
    from datetime import date as _date
    if date_val == _date.today().isoformat():
        from core.ring import resolve_ring_datetime, _schedule_reminder
        from datetime import datetime
        fire_dt = datetime.fromisoformat(f"{date_val}T{time_val}:00")
        if fire_dt > datetime.now():
            ok = _schedule_reminder(text, project_dir.name, fire_dt, kind="reminder")
            if ok:
                print(f"  🔔 Notificación programada para hoy a las {time_val}")

    return 0


def run_reminder_drop(project: Optional[str], text: Optional[str],
                      force: bool = False, occurrence: bool = False,
                      series: bool = False) -> int:
    """Drop a reminder: remove or advance to next occurrence."""
    import sys
    if project:
        project_dir = _find_new_project(project)
        if project_dir is None:
            return 1
        dirs = [project_dir]
    else:
        dirs = [d for d in iter_project_dirs() if _is_new_project(d)]

    for project_dir in dirs:
        agenda_path = resolve_file(project_dir, "agenda")
        data = _read_agenda(agenda_path)
        reminders = [r for r in data.get("reminders", []) if not r.get("cancelled")]
        if not reminders:
            continue

        idx = _select_item_reminder(reminders, text)
        if idx is None:
            continue

        rem = reminders[idx]
        drop_series = series

        if occurrence or series:
            # Explicit flag — skip interactive prompt
            pass
        elif not force:
            if not sys.stdin.isatty():
                print("Error: usa --force para confirmar en modo no interactivo.")
                return 1
            if rem.get("recur"):
                try:
                    ans = input(
                        f"\"{rem['desc']}\" es recurrente ({rem['recur']}).\n"
                        f"  [o] Quitar esta ocurrencia (avanzar al próximo)\n"
                        f"  [s] Eliminar toda la serie\n"
                        f"  [c] Cancelar\n"
                        f"  ¿Qué hacer? [o/s/C]: "
                    ).strip().lower()
                except (EOFError, KeyboardInterrupt):
                    print()
                    return 1
                if ans in ("s", "serie"):
                    drop_series = True
                elif ans in ("o", "ocurrencia"):
                    drop_series = False
                else:
                    print("Cancelado.")
                    return 0
            else:
                try:
                    ans = input(f"¿Eliminar recordatorio \"{rem['desc']}\"? [s/N]: ").strip().lower()
                except (EOFError, KeyboardInterrupt):
                    print()
                    return 1
                if ans not in ("s", "si", "sí", "y", "yes"):
                    print("Cancelado.")
                    return 0

        next_info = ""
        if rem.get("recur") and not drop_series:
            today_str = date.today().isoformat()
            next_due = _next_occurrence(rem.get("date"), rem["recur"], today_str)
            until = rem.get("until")
            if until and date.fromisoformat(next_due) > date.fromisoformat(until):
                next_info = f" (recur: {rem['recur']}) — serie finalizada ({until})"
            else:
                # Advance to next occurrence
                for r in data["reminders"]:
                    if r is rem:
                        r["date"] = next_due
                        break
                _write_agenda(agenda_path, data)
                # Delete Mac reminder if it was for today
                if rem.get("date") == date.today().isoformat() or rem.get("date") == today_str:
                    from core.ring import _delete_reminder
                    _delete_reminder(rem['desc'], project_dir.name, kind="reminder")
                print(f"✓ [{project_dir.name}] Recordatorio avanzado: {rem['desc']} → {next_due}")
                return 0

        # Cancel (mark [-]) or remove
        for r in data["reminders"]:
            if r is rem:
                r["cancelled"] = True
                break

        _write_agenda(agenda_path, data)
        # Delete Mac reminder if it was for today
        if rem.get("date") == date.today().isoformat():
            from core.ring import _delete_reminder
            _delete_reminder(rem['desc'], project_dir.name, kind="reminder")
        if drop_series:
            print(f"✓ [{project_dir.name}] Serie eliminada: {rem['desc']} ({rem['recur']})")
        else:
            print(f"✓ [{project_dir.name}] Recordatorio eliminado: {rem['desc']}{next_info}")
        return 0

    print("No se encontró el recordatorio.")
    return 1


def run_reminder_edit(project: Optional[str], text: Optional[str],
                      new_text: Optional[str] = None, new_date: Optional[str] = None,
                      new_time: Optional[str] = None, new_recur: Optional[str] = None,
                      new_until: Optional[str] = None,
                      new_desc: Optional[str] = None,
                      force: bool = False, occurrence: bool = False,
                      series: bool = False) -> int:
    """Edit an existing reminder."""
    if new_date and new_date != "none" and not _valid_date(new_date):
        print(f"⚠️  Fecha '{new_date}' no reconocida. Usa: YYYY-MM-DD, today, mañana, next monday, ...")
        return 1
    if new_until and new_until != "none" and not _valid_date(new_until):
        print(f"⚠️  Fecha --until '{new_until}' no reconocida.")
        return 1
    if new_recur and new_recur != "none":
        new_recur = _normalize_recur(new_recur)
    if new_recur and new_recur != "none" and not is_valid_recur(new_recur):
        print(f"⚠️  Recurrencia '{new_recur}' no válida. Usa: daily, weekly, monthly, weekdays, every 2 weeks, ...")
        return 1
    if new_time and new_time != "none" and not re.match(r"^\d{2}:\d{2}$", new_time):
        print(f"⚠️  Hora '{new_time}' no válida. Usa: HH:MM (ej. 15:00)")
        return 1

    if project:
        project_dir = _find_new_project(project)
        if project_dir is None:
            return 1
        dirs = [project_dir]
    else:
        dirs = [d for d in iter_project_dirs() if _is_new_project(d)]

    for project_dir in dirs:
        agenda_path = resolve_file(project_dir, "agenda")
        data = _read_agenda(agenda_path)
        reminders = [r for r in data.get("reminders", []) if not r.get("cancelled")]
        if not reminders:
            continue

        idx = _select_item_reminder(reminders, text)
        if idx is None:
            continue

        rem = reminders[idx]
        old_desc = rem["desc"]

        # ── Occurrence vs Series for recurring items ──
        if rem.get("recur") and not (new_recur and new_recur == "none"):
            choice = _ask_edit_occurrence_or_series(
                rem["desc"], rem["recur"], force, occurrence, series)
            if choice is None:
                return 1 if not sys.stdin.isatty() else 0
            if choice:  # occurrence
                today_str = date.today().isoformat()
                next_due = _next_occurrence(rem.get("date"), rem["recur"], today_str)
                until = rem.get("until")
                new_item = {
                    "desc": new_text or rem["desc"],
                    "date": (None if new_date == "none" else new_date) if new_date else rem.get("date"),
                    "time": (None if new_time == "none" else new_time) if new_time else rem.get("time"),
                    "notes": ([new_desc] if new_desc and new_desc != "none" else []) if new_desc is not None else list(rem.get("notes") or []),
                }
                data["reminders"].append(new_item)
                if until and date.fromisoformat(next_due) > date.fromisoformat(until):
                    rem["cancelled"] = True
                    next_info = f" — serie finalizada ({until})"
                else:
                    rem["date"] = next_due
                    next_info = f" → serie avanza a {next_due}"
                _write_agenda(agenda_path, data)
                print(f"✓ [{project_dir.name}] Ocurrencia editada: {new_item['desc']}{next_info}")
                return 0

        # ── Series path (or non-recurring) ──
        if new_text:   rem["desc"]  = new_text
        if new_date:   rem["date"]  = None if new_date == "none" else new_date
        if new_time:   rem["time"]  = None if new_time == "none" else new_time
        if new_recur:  rem["recur"] = None if new_recur == "none" else new_recur
        if new_until:  rem["until"] = None if new_until == "none" else new_until
        if new_desc is not None:
            rem["notes"] = [new_desc] if new_desc and new_desc != "none" else []

        _write_agenda(agenda_path, data)
        attrs = f"({rem.get('date', '?')}) ⏰{rem.get('time', '?')}"
        if rem.get("recur"):
            attrs += f" 🔄{rem['recur']}"
        print(f"✓ [{project_dir.name}] Recordatorio actualizado: {rem['desc']} {attrs}")

        # Update Mac reminder if fires today
        if rem.get("date") and rem.get("time") and rem["date"] == date.today().isoformat():
            from core.ring import _schedule_reminder, _delete_reminder
            from datetime import datetime as _dt, time as _time
            fire_dt = _dt.combine(date.today(), _time.fromisoformat(rem["time"]))
            if new_text or new_time:
                _delete_reminder(old_desc, project_dir.name, kind="reminder")
            ok = _schedule_reminder(rem['desc'], project_dir.name, fire_dt, kind="reminder")
            if ok:
                print(f"  🔔 Notificación actualizada: {rem['time']}")

        return 0

    print("No se encontró el recordatorio.")
    return 1


def _select_item_reminder(items: list, text: Optional[str]) -> Optional[int]:
    """Select a reminder by partial match or interactive list."""
    from core.config import normalize
    return _select_from_list(
        items, "Recordatorios", text,
        display_fn=_display_reminder,
        match_fn=lambda r, txt: normalize(txt) in normalize(r["desc"]))


def run_reminder_list(project: Optional[str] = None) -> int:
    """List active reminders."""
    if project:
        project_dir = _find_new_project(project)
        if project_dir is None:
            return 1
        dirs = [project_dir]
    else:
        dirs = [d for d in iter_project_dirs() if _is_new_project(d)]

    total = 0
    for project_dir in dirs:
        data = _read_agenda(resolve_file(project_dir, "agenda"))
        reminders = [r for r in data.get("reminders", []) if not r.get("cancelled")]
        if not reminders:
            continue

        print(f"\n[{project_dir.name}]")
        for r in sorted(reminders, key=lambda x: (x["date"], x["time"])):
            recur_s = f" 🔄{r['recur']}" if r.get("recur") else ""
            print(f"  💬 {r['desc']} ({r['date']}) ⏰{r['time']}{recur_s}")
            total += 1

    if not total:
        print("No hay recordatorios activos.")
    else:
        print()
    return 0


def run_reminder_log(project: Optional[str], text: Optional[str]) -> int:
    """Create a logbook entry (#apunte) from an existing reminder."""
    if project:
        project_dir = _find_new_project(project)
        if project_dir is None:
            return 1
        dirs = [project_dir]
    else:
        dirs = [d for d in iter_project_dirs() if _is_new_project(d)]

    for project_dir in dirs:
        data = _read_agenda(resolve_file(project_dir, "agenda"))
        reminders = [r for r in data.get("reminders", []) if not r.get("cancelled")]
        if not reminders:
            continue

        idx = _select_item_reminder(reminders, text)
        if idx is None:
            continue

        rem = reminders[idx]
        from core.log import add_entry
        return add_entry(project or project_dir.name, rem["desc"], "apunte", None, rem.get("date"))

    print("No se encontró el recordatorio.")
    return 1

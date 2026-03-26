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
from core.config import iter_project_dirs, iter_federated_project_dirs, get_federation_emoji

VALID_RECUR = {"daily", "weekly", "monthly", "weekdays"}


def _fed_tag(project_dir) -> str:
    """Terminal tag: [name] for local, 🌿 [name] for federated."""
    emoji = get_federation_emoji(project_dir)
    if emoji:
        return f"{emoji} [{project_dir.name}]"
    return f"[{project_dir.name}]"


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


# ── Type configuration ─────────────────────────────────────────────────────────

_TYPE_CONFIG = {
    "task": {
        "key": "tasks", "label": "Tarea", "kind": "task",
        "has_status": True, "has_ring": True, "has_gsync": True,
        "has_end": False, "time_format": "simple",
        "select_fn": lambda data, text: _select_item(data["tasks"], "Tareas pendientes", text),
        "drop_action": "cancel", "drop_verb": "cancelada",
        "log_type": "apunte",
    },
    "milestone": {
        "key": "milestones", "label": "Hito", "kind": "milestone",
        "has_status": True, "has_ring": True, "has_gsync": True,
        "has_end": False, "time_format": "simple",
        "select_fn": lambda data, text: _select_item(data["milestones"], "Hitos pendientes", text),
        "drop_action": "cancel", "drop_verb": "cancelado",
        "log_type": "resultado",
    },
    "event": {
        "key": "events", "label": "Evento", "kind": "event",
        "has_status": False, "has_ring": True, "has_gsync": True,
        "has_end": True, "time_format": "event",
        "select_fn": lambda data, text: _select_event(data["events"], text),
        "drop_action": "pop", "drop_verb": "eliminado",
        "log_type": "evento",
    },
    "reminder": {
        "key": "reminders", "label": "Recordatorio", "kind": "reminder",
        "has_status": False, "has_ring": False, "has_gsync": False,
        "has_end": False, "time_format": "simple",
        "select_fn": None,  # reminders iterate projects, use _select_item_reminder
        "drop_action": "cancel_bool", "drop_verb": "eliminado",
        "log_type": "apunte",
    },
}


# ── Shared helpers ─────────────────────────────────────────────────────────────

def _resolve_project(project: Optional[str]) -> Optional[Path]:
    """Resolve project name to dir. Returns None on failure (prints error)."""
    project_dir = _find_new_project(project) if project else None
    if project and project_dir is None:
        return None
    if project_dir is None:
        print("Error: especifica un proyecto")
        return None
    return project_dir


def _format_add_attrs(date_val, time_val, recur, until, ring,
                      end_date=None, is_event=False) -> str:
    """Build attribute string for add confirmation message."""
    attrs = ""
    if is_event:
        if time_val: attrs += f" ⏰{time_val}"
        if end_date: attrs += f" →{end_date}"
    else:
        if date_val: attrs += f" ({date_val})"
        if time_val: attrs += f" ⏰{time_val}"
    if recur:
        recur_s = recur
        if until: recur_s += f":{until}"
        attrs += f" 🔄{recur_s}"
    if ring: attrs += f" 🔔{ring}"
    return attrs


def _schedule_ring_if_today(text, project_dir, date_val, ring, time_val, kind):
    """Schedule Mac reminder if ring fires today."""
    if not ring:
        return
    from core.ring import resolve_ring_datetime, _schedule_reminder
    ev_time = time_val.split("-")[0] if time_val and "-" in time_val else time_val
    ring_dt = resolve_ring_datetime(date_val, ring, due_time=ev_time)
    if ring_dt and ring_dt.date() == date.today():
        ok = _schedule_reminder(text, project_dir.name, ring_dt, kind=kind)
        if ok:
            print(f"  ⏰ Recordatorio programado: {ring_dt.strftime('%H:%M')}")


def _delete_ring_if_today(desc, project_dir, date_val, ring, time_val, kind):
    """Delete Mac reminder if it was firing today."""
    if not ring or not date_val:
        return
    from core.ring import resolve_ring_datetime, _delete_reminder
    ev_time = time_val.split("-")[0] if time_val and "-" in time_val else time_val
    ring_dt = resolve_ring_datetime(date_val, ring, due_time=ev_time)
    if ring_dt and ring_dt.date() == date.today():
        _delete_reminder(desc, project_dir.name, kind=kind)


def _update_ring_on_edit(old_desc, item, project_dir, kind, changed_fields):
    """Update Mac reminder on edit: delete old + schedule new if changed."""
    if not item.get("ring") or not item.get("date"):
        return
    from core.ring import resolve_ring_datetime, _schedule_reminder, _delete_reminder
    ev_time = item.get("time", "").split("-")[0] if item.get("time") and "-" in item.get("time", "") else item.get("time")
    ring_dt = resolve_ring_datetime(item["date"], item["ring"], due_time=ev_time)
    if ring_dt and ring_dt.date() == date.today():
        if any(changed_fields):
            _delete_reminder(old_desc, project_dir.name, kind=kind)
        ok = _schedule_reminder(item["desc"], project_dir.name, ring_dt, kind=kind)
        if ok:
            print(f"  ⏰ Recordatorio programado: {ring_dt.strftime('%H:%M')}")


def _sync_to_google(project_dir, item, kind):
    """Sync item to Google if type supports it."""
    from core.gsync import sync_item
    sync_item(project_dir, item, kind)


def _ask_drop_confirmation(desc, recur, force, occurrence, series, label) -> tuple:
    """Handle interactive drop confirmation.

    Returns (proceed: bool, drop_series: bool).
    """
    drop_series = series
    if occurrence or series:
        return True, drop_series
    if not force:
        if not sys.stdin.isatty():
            print("Error: usa --force para confirmar en modo no interactivo.")
            return False, False
        if recur:
            try:
                ans = input(
                    f"\"{desc}\" es recurrente ({recur}).\n"
                    f"  [o] Quitar esta ocurrencia (avanzar al próximo)\n"
                    f"  [s] Eliminar toda la serie\n"
                    f"  [c] Cancelar\n"
                    f"  ¿Qué hacer? [o/s/C]: "
                ).strip().lower()
            except (EOFError, KeyboardInterrupt):
                print()
                return False, False
            if ans in ("s", "serie"):
                return True, True
            if ans in ("o", "ocurrencia"):
                return True, False
            print("Cancelado.")
            return False, False
        else:
            try:
                ans = input(f"¿Eliminar {label.lower()} \"{desc}\"? [s/N]: ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                print()
                return False, False
            if ans not in ("s", "si", "sí", "y", "yes"):
                print("Cancelado.")
                return False, False
    return True, drop_series


def _advance_recurrence(item, items_list, cfg) -> str:
    """Advance a recurring item to next occurrence.

    Returns info string like ' (recur: weekly) → próxima: 2026-04-01'.
    Appends new item to items_list if within until limit.
    """
    if not item.get("recur"):
        return ""
    today_str = date.today().isoformat()
    next_due = _next_occurrence(item.get("date"), item["recur"], today_str)
    until = item.get("until")
    if until and date.fromisoformat(next_due) > date.fromisoformat(until):
        return f" (recur: {item['recur']}) — serie finalizada ({until})"
    new_item = {"desc": item["desc"], "date": next_due, "recur": item["recur"],
                "until": until, "notes": list(item.get("notes") or [])}
    if cfg["has_status"]:
        new_item["status"] = "pending"
    if cfg["has_ring"]:
        new_item["ring"] = item.get("ring")
    if cfg.get("has_end"):
        # Events: copy all fields except synced
        new_item = {k: v for k, v in item.items() if k != "synced"}
        new_item["date"] = next_due
    items_list.append(new_item)
    return f" (recur: {item['recur']}) → próxima: {next_due}"


def _validate_edit_params(new_date=None, new_until=None, new_recur=None,
                          new_ring=None, new_time=None,
                          new_end=None, time_format="simple") -> Optional[str]:
    """Validate edit parameters. Returns error message or None."""
    if new_date and new_date != "none" and not _valid_date(new_date):
        return f"⚠️  Fecha '{new_date}' no reconocida. Usa: YYYY-MM-DD, today, mañana, next monday, ..."
    if new_until and new_until != "none" and not _valid_date(new_until):
        return f"⚠️  Fecha --until '{new_until}' no reconocida."
    if new_end and new_end != "none" and not _valid_date(new_end):
        return f"⚠️  Fecha --end '{new_end}' no reconocida. Usa: YYYY-MM-DD, today, mañana, next monday, ..."
    if new_recur and new_recur != "none" and not is_valid_recur(new_recur):
        return f"⚠️  Recurrencia '{new_recur}' no válida. Usa: daily, weekly, monthly, weekdays, every 2 weeks, first monday, ..."
    if new_ring and new_ring != "none":
        from core.ring import _parse_ring
        if _parse_ring(new_ring) is None:
            return f"⚠️  Ring '{new_ring}' no válido. Usa: HH:MM, 1d, 2h, 30m, o YYYY-MM-DD HH:MM"
    if new_time and new_time != "none":
        if time_format == "simple" and not re.match(r"^\d{2}:\d{2}$", new_time):
            return f"⚠️  Hora '{new_time}' no válida. Usa: HH:MM (ej. 15:00)"
        if time_format == "event" and not _valid_time(new_time):
            return f"⚠️  Hora '{new_time}' no válida. Usa: HH:MM o HH:MM-HH:MM (ej. 10:00, 10:00-12:30)"
    return None


def _apply_edits(item: dict, edits: dict):
    """Apply edit fields to item in place. 'none' → None."""
    for key, val in edits.items():
        if val is not None:
            if key == "notes":
                item["notes"] = [val] if val and val != "none" else []
            else:
                item[key] = None if val == "none" else val


def _make_edit_occurrence(item, data_list, cfg, edits: dict):
    """Create edited occurrence copy + advance series.

    Returns (new_item_dict, next_info_str).
    """
    today_str = date.today().isoformat()
    next_due = _next_occurrence(item.get("date"), item["recur"], today_str)
    until = item.get("until")

    # Build non-recurring copy with edits
    new_item = {"desc": edits.get("desc") or item["desc"]}
    for field in ("date", "time", "ring", "end"):
        if field in edits:
            new_item[field] = None if edits[field] == "none" else edits[field]
        elif item.get(field) is not None:
            new_item[field] = item.get(field)
    # Notes
    new_desc = edits.get("notes")
    if new_desc is not None:
        new_item["notes"] = [new_desc] if new_desc and new_desc != "none" else []
    else:
        new_item["notes"] = list(item.get("notes") or [])
    # Status only for task/ms
    if cfg["has_status"]:
        new_item["status"] = "pending"

    data_list.append(new_item)

    # Advance the series
    if until and date.fromisoformat(next_due) > date.fromisoformat(until):
        if cfg["has_status"]:
            item["status"] = "cancelled"
        elif cfg["key"] == "events":
            data_list.remove(item)
        elif not cfg["has_status"]:
            item["cancelled"] = True
        return new_item, f" — serie finalizada ({until})"
    else:
        item["date"] = next_due
        return new_item, f" → serie avanza a {next_due}"


# ── Generic operations ────────────────────────────────────────────────────────

def _generic_add(type_name: str, project: str, text: str,
                 date_val=None, recur=None, until=None,
                 ring=None, time_val=None, desc=None,
                 end_date=None) -> int:
    """Generic add for all 4 appointment types."""
    cfg = _TYPE_CONFIG[type_name]
    if recur:
        recur = _normalize_recur(recur)
    if cfg["has_end"] and end_date and not _valid_date(end_date):
        print(f"⚠️  Fecha --end '{end_date}' no reconocida. Usa: YYYY-MM-DD, today, mañana, next monday, ...")
        return 1
    err = _validate_add_params(date_val, time_val, recur, until,
                               ring if cfg["has_ring"] else None,
                               time_format=cfg["time_format"])
    if err:
        print(err)
        return 1
    if cfg["has_ring"] and date_val and time_val and not ring:
        ring = _prompt_and_validate_ring()

    project_dir = _find_new_project(project)
    if project_dir is None:
        return 1

    agenda_path = resolve_file(project_dir, "agenda")
    data = _read_agenda(agenda_path)
    notes = [desc] if desc else []

    # Build item dict
    new_item = {"desc": text, "date": date_val, "recur": recur,
                "until": until, "notes": notes}
    if cfg["has_status"]:
        new_item["status"] = "pending"
    if cfg["has_ring"]:
        new_item["ring"] = ring
    new_item["time"] = time_val
    if cfg["has_end"]:
        new_item["end"] = end_date
    if not cfg["has_status"] and not cfg["has_ring"]:
        # Reminder: cancelled flag
        new_item["cancelled"] = False

    data.setdefault(cfg["key"], []).append(new_item)
    _write_agenda(agenda_path, data)

    # Print confirmation
    if type_name == "event":
        attrs = _format_add_attrs(date_val, time_val, recur, until, ring,
                                  end_date=end_date, is_event=True)
        print(f"✓ [{project_dir.name}] {cfg['label']}: {date_val} — {text}{attrs}")
    elif type_name == "reminder":
        attrs = f"({date_val}) ⏰{time_val}"
        if recur:
            recur_s = recur + (f":{until}" if until else "")
            attrs += f" 🔄{recur_s}"
        print(f"✓ [{project_dir.name}] {cfg['label']}: {text} {attrs}")
    else:
        attrs = _format_add_attrs(date_val, time_val, recur, until, ring)
        print(f"✓ [{project_dir.name}] {cfg['label']}: {text}{attrs}")

    # Ring scheduling
    if cfg["has_ring"]:
        _schedule_ring_if_today(text, project_dir, date_val, ring, time_val, cfg["kind"])
    elif type_name == "reminder" and date_val == date.today().isoformat():
        # Reminders: schedule notification at exact time
        from datetime import datetime
        fire_dt = datetime.fromisoformat(f"{date_val}T{time_val}:00")
        if fire_dt > datetime.now():
            from core.ring import _schedule_reminder
            ok = _schedule_reminder(text, project_dir.name, fire_dt, kind="reminder")
            if ok:
                print(f"  🔔 Notificación programada para hoy a las {time_val}")

    # Google sync
    if cfg["has_gsync"]:
        _sync_to_google(project_dir, new_item, cfg["kind"])

    return 0


def _generic_drop(type_name: str, project_dir: Path, data: dict,
                  agenda_path: Path, text: Optional[str],
                  force=False, occurrence=False, series=False) -> int:
    """Generic drop for task/ms/ev. Reminder uses wrapper with project iteration."""
    cfg = _TYPE_CONFIG[type_name]
    items = data[cfg["key"]]

    idx = cfg["select_fn"](data, text)
    if idx is None:
        return 1

    item = items[idx]
    item_desc = item["desc"]
    display = f"{item['date']} — {item_desc}" if type_name == "event" else item_desc

    proceed, drop_series = _ask_drop_confirmation(
        display, item.get("recur"), force, occurrence, series, cfg["label"])
    if not proceed:
        return 0 if sys.stdin.isatty() else 1

    # Mark cancelled / remove
    if cfg["drop_action"] == "cancel":
        item["status"] = "cancelled"
    elif cfg["drop_action"] == "pop":
        items.pop(idx)
    elif cfg["drop_action"] == "cancel_bool":
        item["cancelled"] = True

    # Advance recurrence
    next_info = ""
    if item.get("recur") and not drop_series:
        if cfg["drop_action"] == "pop":
            # Event was already popped; advance operates on the popped item
            next_info = _advance_recurrence(item, items, cfg)
        elif cfg["drop_action"] == "cancel_bool":
            # Reminder: advance date in-place instead of new item
            today_str = date.today().isoformat()
            next_due = _next_occurrence(item.get("date"), item["recur"], today_str)
            until = item.get("until")
            if until and date.fromisoformat(next_due) > date.fromisoformat(until):
                next_info = f" (recur: {item['recur']}) — serie finalizada ({until})"
            else:
                item["cancelled"] = False  # un-cancel, just advance
                item["date"] = next_due
                _write_agenda(agenda_path, data)
                # Delete Mac reminder if for today
                if date_val_is_today(item.get("date")):
                    from core.ring import _delete_reminder
                    _delete_reminder(item_desc, project_dir.name, kind="reminder")
                print(f"✓ [{project_dir.name}] Recordatorio avanzado: {item_desc} → {next_due}")
                return 0
        else:
            next_info = _advance_recurrence(item, items, cfg)

    _write_agenda(agenda_path, data)

    # Logbook + print
    if drop_series:
        if cfg["has_status"]:
            add_orbit_entry(project_dir, f"[serie cancelada] {cfg['label']}: {item_desc} ({item['recur']})", "apunte")
            print(f"✓ [{project_dir.name}] [serie cancelada] {item_desc} ({item['recur']})")
        else:
            print(f"✓ [{project_dir.name}] Serie eliminada: {display} ({item['recur']})")
        # Event series: delete from Google Calendar
        if type_name == "event" and item.get("synced"):
            from core.gsync import delete_gcal_event
            delete_gcal_event(project_dir, item)
    else:
        if cfg["has_status"]:
            add_orbit_entry(project_dir, f"[{cfg['drop_verb']}] {cfg['label']}: {item_desc}{next_info}", "apunte")
            print(f"✓ [{project_dir.name}] [{cfg['drop_verb']}] {item_desc}{next_info}")
        else:
            print(f"✓ [{project_dir.name}] {cfg['label']} {cfg['drop_verb']}: {display}{next_info}")
        # Event non-recurring: delete from Google Calendar
        if type_name == "event" and not item.get("recur") and item.get("synced"):
            from core.gsync import delete_gcal_event
            delete_gcal_event(project_dir, item)

    # Ring cleanup
    if cfg["has_ring"]:
        _delete_ring_if_today(item_desc, project_dir, item.get("date"),
                              item.get("ring"), item.get("time"), cfg["kind"])
    elif type_name == "reminder" and item.get("date") == date.today().isoformat():
        from core.ring import _delete_reminder
        _delete_reminder(item_desc, project_dir.name, kind="reminder")

    # Google sync (task/ms: sync cancelled item)
    if cfg["has_gsync"] and cfg["drop_action"] == "cancel":
        _sync_to_google(project_dir, item, cfg["kind"])

    return 0


def _generic_edit(type_name: str, project_dir: Path, data: dict,
                  agenda_path: Path, text: Optional[str],
                  new_text=None, new_date=None, new_time=None,
                  new_recur=None, new_until=None, new_ring=None,
                  new_desc=None, new_end=None,
                  force=False, occurrence=False, series=False) -> int:
    """Generic edit for all 4 appointment types."""
    cfg = _TYPE_CONFIG[type_name]

    # Normalize recur
    if new_recur and new_recur != "none":
        new_recur = _normalize_recur(new_recur)

    # Validate
    err = _validate_edit_params(new_date=new_date, new_until=new_until,
                                new_recur=new_recur, new_ring=new_ring,
                                new_time=new_time, new_end=new_end,
                                time_format=cfg["time_format"])
    if err:
        print(err)
        return 1

    # Select item
    items = data[cfg["key"]]
    if type_name == "reminder":
        reminders = [r for r in items if not r.get("cancelled")]
        idx = _select_item_reminder(reminders, text)
        if idx is None:
            return 1
        item = reminders[idx]
    else:
        idx = cfg["select_fn"](data, text)
        if idx is None:
            return 1
        item = items[idx]

    old_desc = item["desc"]

    # ── Occurrence vs Series for recurring items ──
    if item.get("recur") and not (new_recur and new_recur == "none"):
        choice = _ask_edit_occurrence_or_series(
            item["desc"], item["recur"], force, occurrence, series)
        if choice is None:
            return 1 if not sys.stdin.isatty() else 0
        if choice:  # occurrence
            edits = {}
            if new_text: edits["desc"] = new_text
            if new_date: edits["date"] = new_date
            if new_time: edits["time"] = new_time
            if new_ring and cfg["has_ring"]: edits["ring"] = new_ring
            if new_end and cfg["has_end"]: edits["end"] = new_end
            if new_desc is not None: edits["notes"] = new_desc
            new_item, next_info = _make_edit_occurrence(item, items, cfg, edits)
            _write_agenda(agenda_path, data)
            print(f"✓ [{project_dir.name}] Ocurrencia editada: {new_item['desc']}{next_info}")
            if cfg["has_gsync"]:
                _sync_to_google(project_dir, new_item, cfg["kind"])
                _sync_to_google(project_dir, item, cfg["kind"])
            return 0

    # ── Series path (or non-recurring) ──
    edits = {}
    if new_text:  edits["desc"]  = new_text
    if new_date:  edits["date"]  = new_date
    if new_time:  edits["time"]  = new_time
    if new_recur: edits["recur"] = new_recur
    if new_until: edits["until"] = new_until
    if new_ring and cfg["has_ring"]:  edits["ring"]  = new_ring
    if new_end and cfg["has_end"]:    edits["end"]   = new_end
    if new_desc is not None:          edits["notes"] = new_desc
    _apply_edits(item, edits)

    _write_agenda(agenda_path, data)
    if type_name == "event":
        print(f"✓ [{project_dir.name}] {cfg['label']} actualizado: {item['date']} — {item['desc']}")
    elif type_name == "reminder":
        attrs = f"({item.get('date', '?')}) ⏰{item.get('time', '?')}"
        if item.get("recur"):
            attrs += f" 🔄{item['recur']}"
        print(f"✓ [{project_dir.name}] {cfg['label']} actualizado: {item['desc']} {attrs}")
    else:
        print(f"✓ [{project_dir.name}] {cfg['label']} actualizada: {item['desc']}")

    # Ring update
    if cfg["has_ring"]:
        _update_ring_on_edit(old_desc, item, project_dir, cfg["kind"],
                             [new_text, new_time, new_ring])
    elif type_name == "reminder" and item.get("date") and item.get("time"):
        if item["date"] == date.today().isoformat():
            from core.ring import _schedule_reminder, _delete_reminder
            from datetime import datetime as _dt, time as _time
            fire_dt = _dt.combine(date.today(), _time.fromisoformat(item["time"]))
            if new_text or new_time:
                _delete_reminder(old_desc, project_dir.name, kind="reminder")
            ok = _schedule_reminder(item["desc"], project_dir.name, fire_dt, kind="reminder")
            if ok:
                print(f"  🔔 Notificación actualizada: {item['time']}")

    # Google sync
    if cfg["has_gsync"]:
        _sync_to_google(project_dir, item, cfg["kind"])

    return 0


def _generic_log(type_name: str, project_dir: Path, data: dict,
                 text: Optional[str], project_name: str) -> int:
    """Generic log entry creation for all 4 appointment types."""
    cfg = _TYPE_CONFIG[type_name]
    if type_name == "reminder":
        reminders = [r for r in data.get("reminders", []) if not r.get("cancelled")]
        idx = _select_item_reminder(reminders, text)
        if idx is None:
            return 1
        item = reminders[idx]
    else:
        idx = cfg["select_fn"](data, text)
        if idx is None:
            return 1
        item = data[cfg["key"]][idx]

    from core.log import add_entry
    return add_entry(project_name, item["desc"], cfg["log_type"], None, item.get("date"))


def date_val_is_today(date_val):
    """Check if a date string is today."""
    return date_val == date.today().isoformat() if date_val else False


# ── TASK commands ──────────────────────────────────────────────────────────────

def run_task_add(project: str, text: str, date_val: Optional[str] = None,
                 recur: Optional[str] = None, until: Optional[str] = None,
                 ring: Optional[str] = None, time_val: Optional[str] = None,
                 desc: Optional[str] = None) -> int:
    return _generic_add("task", project, text, date_val=date_val, recur=recur,
                        until=until, ring=ring, time_val=time_val, desc=desc)


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
    project_dir = _resolve_project(project)
    if project_dir is None:
        return 1
    agenda_path = resolve_file(project_dir, "agenda")
    data = _read_agenda(agenda_path)
    return _generic_drop("task", project_dir, data, agenda_path, text,
                         force=force, occurrence=occurrence, series=series)


def run_task_edit(project: Optional[str], text: Optional[str],
                  new_text: Optional[str] = None, new_date: Optional[str] = None,
                  new_recur: Optional[str] = None, new_until: Optional[str] = None,
                  new_ring: Optional[str] = None, new_time: Optional[str] = None,
                  new_desc: Optional[str] = None,
                  force: bool = False, occurrence: bool = False,
                  series: bool = False) -> int:
    project_dir = _resolve_project(project)
    if project_dir is None:
        return 1
    agenda_path = resolve_file(project_dir, "agenda")
    data = _read_agenda(agenda_path)
    return _generic_edit("task", project_dir, data, agenda_path, text,
                         new_text=new_text, new_date=new_date, new_time=new_time,
                         new_recur=new_recur, new_until=new_until, new_ring=new_ring,
                         new_desc=new_desc, force=force, occurrence=occurrence, series=series)


def run_task_list(projects: Optional[list] = None,
                  status_filter: str = "pending",
                  date_filter: Optional[str] = None,
                  dated_only: bool = False,
                  unplanned: bool = False,
                  include_federated: bool = True) -> int:
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
        dirs = [d for d in iter_federated_project_dirs(include_federated) if _is_new_project(d)]

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
        if unplanned:
            tasks = [t for t in tasks if not t.get("date")]

        if not tasks:
            continue

        print(f"\n{_fed_tag(project_dir)}")
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
    project_dir = _resolve_project(project)
    if project_dir is None:
        return 1
    data = _read_agenda(resolve_file(project_dir, "agenda"))
    return _generic_log("task", project_dir, data, text, project or project_dir.name)


# ── MILESTONE commands ─────────────────────────────────────────────────────────

def run_ms_add(project: str, text: str, date_val: Optional[str] = None,
               recur: Optional[str] = None, until: Optional[str] = None,
               ring: Optional[str] = None, time_val: Optional[str] = None,
               desc: Optional[str] = None) -> int:
    return _generic_add("milestone", project, text, date_val=date_val, recur=recur,
                        until=until, ring=ring, time_val=time_val, desc=desc)


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
    project_dir = _resolve_project(project)
    if project_dir is None:
        return 1
    agenda_path = resolve_file(project_dir, "agenda")
    data = _read_agenda(agenda_path)
    return _generic_drop("milestone", project_dir, data, agenda_path, text,
                         force=force, occurrence=occurrence, series=series)


def run_ms_edit(project: Optional[str], text: Optional[str],
                new_text: Optional[str] = None, new_date: Optional[str] = None,
                new_recur: Optional[str] = None, new_until: Optional[str] = None,
                new_ring: Optional[str] = None, new_time: Optional[str] = None,
                new_desc: Optional[str] = None,
                force: bool = False, occurrence: bool = False,
                series: bool = False) -> int:
    project_dir = _resolve_project(project)
    if project_dir is None:
        return 1
    agenda_path = resolve_file(project_dir, "agenda")
    data = _read_agenda(agenda_path)
    return _generic_edit("milestone", project_dir, data, agenda_path, text,
                         new_text=new_text, new_date=new_date, new_time=new_time,
                         new_recur=new_recur, new_until=new_until, new_ring=new_ring,
                         new_desc=new_desc, force=force, occurrence=occurrence, series=series)


def run_ms_list(projects: Optional[list] = None, status_filter: str = "pending",
                date_filter: Optional[str] = None,
                dated_only: bool = False, include_federated: bool = True) -> int:
    if projects:
        dirs = []
        for p in projects:
            d = _find_new_project(p)
            if d:
                dirs.append(d)
        if not dirs:
            return 1
    else:
        dirs = [d for d in iter_federated_project_dirs(include_federated) if _is_new_project(d)]

    total = 0
    for project_dir in dirs:
        data = _read_agenda(resolve_file(project_dir, "agenda"))
        mss  = data["milestones"]

        if status_filter != "all":
            mss = [ms for ms in mss if ms["status"] == status_filter]
        if date_filter:
            mss = [ms for ms in mss if ms.get("date", "").startswith(date_filter)]
        if dated_only:
            mss = [ms for ms in mss if ms.get("date")]
        if not mss:
            continue

        print(f"\n{_fed_tag(project_dir)}")
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
    project_dir = _resolve_project(project)
    if project_dir is None:
        return 1
    data = _read_agenda(resolve_file(project_dir, "agenda"))
    return _generic_log("milestone", project_dir, data, text, project or project_dir.name)


# ── EVENT commands ─────────────────────────────────────────────────────────────

def run_ev_add(project: str, text: str, date_val: str,
               end_date: Optional[str] = None, time_val: Optional[str] = None,
               recur: Optional[str] = None,
               until: Optional[str] = None, ring: Optional[str] = None,
               desc: Optional[str] = None) -> int:
    return _generic_add("event", project, text, date_val=date_val, end_date=end_date,
                        recur=recur, until=until, ring=ring, time_val=time_val, desc=desc)


def run_ev_drop(project: Optional[str], text: Optional[str],
                force: bool = False, occurrence: bool = False,
                series: bool = False) -> int:
    project_dir = _resolve_project(project)
    if project_dir is None:
        return 1
    agenda_path = resolve_file(project_dir, "agenda")
    data = _read_agenda(agenda_path)
    return _generic_drop("event", project_dir, data, agenda_path, text,
                         force=force, occurrence=occurrence, series=series)


def run_ev_edit(project: Optional[str], text: Optional[str],
                new_text: Optional[str] = None, new_date: Optional[str] = None,
                new_end: Optional[str] = None, new_time: Optional[str] = None,
                new_recur: Optional[str] = None,
                new_until: Optional[str] = None, new_ring: Optional[str] = None,
                new_desc: Optional[str] = None,
                force: bool = False, occurrence: bool = False,
                series: bool = False) -> int:
    project_dir = _resolve_project(project)
    if project_dir is None:
        return 1
    agenda_path = resolve_file(project_dir, "agenda")
    data = _read_agenda(agenda_path)
    return _generic_edit("event", project_dir, data, agenda_path, text,
                         new_text=new_text, new_date=new_date, new_end=new_end,
                         new_time=new_time, new_recur=new_recur, new_until=new_until,
                         new_ring=new_ring, new_desc=new_desc,
                         force=force, occurrence=occurrence, series=series)


def run_ev_log(project: Optional[str], text: Optional[str]) -> int:
    """Create a logbook entry (#evento) from an existing event."""
    project_dir = _resolve_project(project)
    if project_dir is None:
        return 1
    data = _read_agenda(resolve_file(project_dir, "agenda"))
    return _generic_log("event", project_dir, data, text, project or project_dir.name)


def run_ev_list(project: Optional[str] = None,
                period_from: Optional[str] = None,
                period_to:   Optional[str] = None,
                include_federated: bool = True) -> int:
    if project:
        project_dir = _find_new_project(project)
        if project_dir is None:
            return 1
        dirs = [project_dir]
    else:
        dirs = [d for d in iter_federated_project_dirs(include_federated) if _is_new_project(d)]

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

        print(f"\n{_fed_tag(project_dir)}")
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
    return _generic_add("reminder", project, text, date_val=date_val,
                        time_val=time_val, recur=recur, until=until, desc=desc)


def run_reminder_drop(project: Optional[str], text: Optional[str],
                      force: bool = False, occurrence: bool = False,
                      series: bool = False) -> int:
    """Drop a reminder: remove or advance to next occurrence."""
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
        proceed, drop_series = _ask_drop_confirmation(
            rem["desc"], rem.get("recur"), force, occurrence, series, "Recordatorio")
        if not proceed:
            return 0 if sys.stdin.isatty() else 1

        # Advance recurrence in-place
        if rem.get("recur") and not drop_series:
            today_str = date.today().isoformat()
            next_due = _next_occurrence(rem.get("date"), rem["recur"], today_str)
            until = rem.get("until")
            if until and date.fromisoformat(next_due) > date.fromisoformat(until):
                pass  # fall through to cancel
            else:
                rem["date"] = next_due
                _write_agenda(agenda_path, data)
                if date_val_is_today(today_str):
                    from core.ring import _delete_reminder
                    _delete_reminder(rem["desc"], project_dir.name, kind="reminder")
                print(f"✓ [{project_dir.name}] Recordatorio avanzado: {rem['desc']} → {next_due}")
                return 0

        # Cancel
        rem["cancelled"] = True
        _write_agenda(agenda_path, data)
        if date_val_is_today(rem.get("date")):
            from core.ring import _delete_reminder
            _delete_reminder(rem["desc"], project_dir.name, kind="reminder")
        if drop_series:
            print(f"✓ [{project_dir.name}] Serie eliminada: {rem['desc']} ({rem['recur']})")
        else:
            print(f"✓ [{project_dir.name}] Recordatorio eliminado: {rem['desc']}")
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
        # Check if text matches any reminder in this project
        test_idx = _select_item_reminder(reminders, text)
        if test_idx is None:
            continue
        return _generic_edit("reminder", project_dir, data, agenda_path, text,
                             new_text=new_text, new_date=new_date, new_time=new_time,
                             new_recur=new_recur, new_until=new_until,
                             new_desc=new_desc, force=force,
                             occurrence=occurrence, series=series)

    print("No se encontró el recordatorio.")
    return 1


def _select_item_reminder(items: list, text: Optional[str]) -> Optional[int]:
    """Select a reminder by partial match or interactive list."""
    from core.config import normalize
    return _select_from_list(
        items, "Recordatorios", text,
        display_fn=_display_reminder,
        match_fn=lambda r, txt: normalize(txt) in normalize(r["desc"]))


def run_reminder_list(project: Optional[str] = None,
                      include_federated: bool = True) -> int:
    """List active reminders."""
    if project:
        project_dir = _find_new_project(project)
        if project_dir is None:
            return 1
        dirs = [project_dir]
    else:
        dirs = [d for d in iter_federated_project_dirs(include_federated) if _is_new_project(d)]

    total = 0
    for project_dir in dirs:
        data = _read_agenda(resolve_file(project_dir, "agenda"))
        reminders = [r for r in data.get("reminders", []) if not r.get("cancelled")]
        if not reminders:
            continue

        print(f"\n{_fed_tag(project_dir)}")
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
        test_idx = _select_item_reminder(reminders, text)
        if test_idx is None:
            continue
        return _generic_log("reminder", project_dir, data, text,
                            project or project_dir.name)

    print("No se encontró el recordatorio.")
    return 1

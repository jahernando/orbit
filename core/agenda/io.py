"""io — parsing/formatting of agenda.md lines and whole-file read/write.

Layered on top of :mod:`core.agenda.recurrence` for the recur grammar.
Everything that turns markdown text into a Python dict (and back) lives
here: line regexes, the kind-specific parsers/formatters, plus the
top-level :func:`_read_agenda` / :func:`_write_agenda`.
"""
from __future__ import annotations

import re
from datetime import date
from pathlib import Path
from typing import Optional

from core.agenda.recurrence import is_valid_recur  # noqa: F401  (re-exported for tests)


# ── Validators ────────────────────────────────────────────────────────────

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


# ── Section headers ───────────────────────────────────────────────────────

_TASK_HEADER = "## ✅ Tareas"
_MS_HEADER   = "## 🏁 Hitos"
_EV_HEADER   = "## 📅 Eventos"
_REM_HEADER  = "## 💬 Recordatorios"


# ── Orbit-id tag (stable identity across user edits in markdown) ──────────
#
# Items synced to Reminders.app / Calendar.app carry an 8-char hex orbit-id
# in their .md line as ``[orbit:abc12345]``. It survives any edit of title,
# date, time, recur or notes — the next sync uses it to find the existing
# Reminder/Event without creating a duplicate.
_ORBIT_ID_RE = re.compile(r"\[orbit:([0-9a-f]{8})\]")


def _extract_orbit_id(text: str) -> Optional[str]:
    """Return the orbit-id tagged in *text*, or None."""
    m = _ORBIT_ID_RE.search(text or "")
    return m.group(1) if m else None


# ── Shared regex patterns for "simple cita" lines (task / milestone / reminder)
#
# These three kinds share the same attribute syntax — only their prefix
# differs (`- [ ]/[x]/[-]` for task/ms, `- ` or `- [-]` for reminder).
# Each pattern has an emoji form and a legacy bracketed form that older
# agendas may still use.

_DATE_RE  = re.compile(r"\((\d{4}-\d{2}-\d{2})\)")
_RECUR_RE = re.compile(r"🔄(\S+)|\[recur:([^\]]+)\]")
_RING_RE  = re.compile(r"🔔(\S+)|\[ring:([^\]]+)\]")
_TIME_RE  = re.compile(r"⏰(\S+)|\[time:([^\]]+)\]")

# Patterns stripped from a line to recover the bare ``desc`` (one pass).
# Includes legacy sync markers (`[G]`, `[gtask:…]`) and the dormant
# `☁️` so old agendas parse cleanly.
_DESC_STRIP_PATS = [
    r"\(\d{4}-\d{2}-\d{2}\)",
    r"🔄\S+", r"\[recur:[^\]]+\]",
    r"🔔\S+", r"\[ring:[^\]]+\]",
    r"⏰\S+", r"\[time:[^\]]+\]",
    r"☁️", r"\[G\]", r"\[gtask:[^\]]+\]",
    r"\[orbit:[0-9a-f]{8}\]",
]
_DESC_STRIP_RE = re.compile("|".join(_DESC_STRIP_PATS))


def _extract_recur(text: str) -> tuple:
    """Return (recur, until) — either via 🔄 or legacy [recur:]."""
    m = _RECUR_RE.search(text)
    if not m:
        return (None, None)
    raw = m.group(1) or m.group(2)
    if ":" in raw:
        recur, until = raw.split(":", 1)
        return (recur, until)
    return (raw, None)


def _extract_emoji_or_legacy(regex, text: str) -> Optional[str]:
    """Match either group of an emoji-or-legacy regex pair."""
    m = regex.search(text)
    if not m:
        return None
    return m.group(1) or m.group(2)


def _clean_desc(text: str) -> str:
    """Strip all known attribute patterns to recover bare desc."""
    return _DESC_STRIP_RE.sub("", text).strip()


# ── Task / milestone / reminder line parsing ──────────────────────────────

def _parse_simple_line(line: str, kind: str) -> Optional[dict]:
    """Parse one task/milestone/reminder line.

    ``kind`` controls the prefix shape and which attributes are read:
    - ``task`` / ``milestone``: ``- [ ]/[x]/[-]`` prefix with status; ring supported.
    - ``reminder``: ``- `` or ``- [-]`` prefix (cancellable, no status); no ring.

    Returns a dict with the standard fields, or ``None`` if the line
    doesn't match the expected shape.
    """
    if kind == "reminder":
        m = re.match(r"^- (?:\[-\] )?(.+)$", line)
        if not m:
            return None
        cancelled = line.startswith("- [-]")
        rest = m.group(1)
        prefix_data = {"cancelled": cancelled}
    else:   # task | milestone
        m = re.match(r"^- \[( |x|-)\] (.+)$", line)
        if not m:
            return None
        status = {" ": "pending", "x": "done", "-": "cancelled"}[m.group(1)]
        rest = m.group(2)
        prefix_data = {"status": status}

    date_m = _DATE_RE.search(rest)
    date_val = date_m.group(1) if date_m else None
    recur, until = _extract_recur(rest)
    time_val = _extract_emoji_or_legacy(_TIME_RE, rest)
    orbit_id = _extract_orbit_id(rest)
    # v0.30 ☁️ marker: parser still tolerates it; formatter no longer
    # writes it (v0.33 — AppleScript-write retired).
    cloud_verified = "☁️" in rest
    desc = _clean_desc(rest)

    if kind == "reminder" and (not date_val or not time_val):
        # Reminders require both a date and a time (it's the only thing
        # that distinguishes them in the absence of a checkbox prefix).
        return None

    item = {
        "desc": desc, "date": date_val, "recur": recur, "until": until,
        "time": time_val, "orbit_id": orbit_id,
        "cloud_verified": cloud_verified,
    }
    item.update(prefix_data)
    if kind != "reminder":
        item["ring"] = _extract_emoji_or_legacy(_RING_RE, rest)
    return item


def _format_simple_line(item: dict, kind: str) -> str:
    """Serialize a task/milestone/reminder dict → markdown line.

    Inverse of :func:`_parse_simple_line`. ``kind`` selects the prefix:
    - ``task`` / ``milestone``: ``- [ ]/[x]/[-]`` from ``item["status"]``.
    - ``reminder``: ``- [-] `` if cancelled, else ``- ``.

    Attribute order in the line: ``desc (date) ⏰time 🔄recur 🔔ring [orbit:id]``.
    """
    parts = [item["desc"]]
    if item.get("date"):
        parts.append(f"({item['date']})")
    if item.get("time"):
        parts.append(f"⏰{item['time']}")
    if item.get("recur"):
        recur_tag = item["recur"]
        if item.get("until"):
            recur_tag += f":{item['until']}"
        parts.append(f"🔄{recur_tag}")
    if kind != "reminder" and item.get("ring"):
        parts.append(f"🔔{item['ring']}")
    # ☁️ marker dormant since v0.33 — vestigial cloud_verified is parsed
    # but never re-emitted.
    if item.get("orbit_id"):
        parts.append(f"[orbit:{item['orbit_id']}]")
    body = " ".join(parts)
    if kind == "reminder":
        prefix = "- [-] " if item.get("cancelled") else "- "
        return f"{prefix}{body}"
    char = {"pending": " ", "done": "x", "cancelled": "-"}[item["status"]]
    return f"- [{char}] {body}"


# Thin wrappers kept so existing callers (orbit.py, render.py, ics.py,
# tests, etc.) don't break. They just dispatch to the unified parsers/
# formatters above.

def _parse_task_line(line: str) -> Optional[dict]:
    """Parse a task/milestone line. See :func:`_parse_simple_line`."""
    return _parse_simple_line(line, "task")


def _format_task_line(task: dict) -> str:
    """Serialize a task or milestone dict. See :func:`_format_simple_line`."""
    return _format_simple_line(task, "task")


# ── Event line parsing ─────────────────────────────────────────────────────

def _parse_event_line(line: str) -> Optional[dict]:
    """Parse YYYY-MM-DD — desc [end:YYYY-MM-DD] [recur:...] [ring:...] → dict."""
    m = re.match(r"^(\d{4}-\d{2}-\d{2})\s+—\s+(.+)$", line)
    if not m:
        return None
    date_val = m.group(1)
    rest     = m.group(2)
    end = recur = until = ring = time_val = None
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
    orbit_id = _extract_orbit_id(rest)
    cloud_verified = "☁️" in rest
    # Strip everything emitted by _format_event_line so desc is recovered clean.
    desc_only = re.sub(r"⏰\S+|→\d{4}-\d{2}-\d{2}|🔄\S+|🔔\S+|"
                       r"\[end:[^\]]+\]|\[recur:[^\]]+\]|\[ring:[^\]]+\]|\[time:[^\]]+\]|"
                       r"☁️|\[G\]|\[gtask:[^\]]+\]|\[orbit:[0-9a-f]{8}\]",
                       "", rest).strip()
    return {
        "date": date_val, "desc": desc_only, "end": end,
        "recur": recur, "until": until, "ring": ring, "time": time_val,
        "orbit_id": orbit_id, "cloud_verified": cloud_verified,
    }


def _format_event_line(ev: dict) -> str:
    """Serialize an event dict back to its markdown line."""
    line = f"{ev['date']} — {ev['desc']}"
    if ev.get("time"):
        line += f" ⏰{ev['time']}"
    if ev.get("end"):
        line += f" →{ev['end']}"
    if ev.get("recur"):
        recur_tag = ev["recur"]
        if ev.get("until"):
            recur_tag += f":{ev['until']}"
        line += f" 🔄{recur_tag}"
    if ev.get("ring"):
        line += f" 🔔{ev['ring']}"
    # ☁️ marker dormant since v0.33 — vestigial cloud_verified is parsed
    # but never re-emitted.
    if ev.get("orbit_id"):
        line += f" [orbit:{ev['orbit_id']}]"
    return line


def _parse_reminder_line(line: str) -> Optional[dict]:
    """Parse a reminder line. See :func:`_parse_simple_line`."""
    return _parse_simple_line(line, "reminder")


def _format_reminder_line(rem: dict) -> str:
    """Serialize a reminder dict. See :func:`_format_simple_line`."""
    return _format_simple_line(rem, "reminder")


# ── Whole-file read/write ──────────────────────────────────────────────────

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

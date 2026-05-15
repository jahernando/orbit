"""ics_share — export/import single appointments as iCalendar (.ics).

Two entry points for sharing citas with the outside world:

* :func:`run_ics_share` — export ONE cita (project + identifier) to a
  single-VEVENT ``.ics``. Useful to attach in an email or paste in a
  chat. Recurring citas export only their next occurrence (scope agreed
  with user 2026-05-13).

* :func:`run_ics_import` — read a ``.ics`` (file or clipboard), pick
  the first VEVENT, and add it to a project's ``agenda.md`` as a new
  cita. RRULE is ignored (only the master occurrence is imported);
  multi-VEVENT files emit a warning and import only the first.

The render path reuses :func:`core.ics.render_vevent` and
:func:`core.ics._calendar_wrapper`; the parse path is a small custom
RFC-5545 reader tailored to our import needs (we keep parameter info
that :func:`core.ics._parse_vevents` discards, e.g. ``VALUE=DATE``).
"""
from __future__ import annotations

import re
import secrets
import subprocess
import sys
from datetime import date as _date, datetime, timedelta
from pathlib import Path
from typing import Optional

from core.agenda_cmds import (
    _read_agenda, _write_agenda, _next_occurrence,
)
from core.ics import (
    render_vevent, _calendar_wrapper, _KIND_EMOJI, write_workspace,
)


def _new_orbit_id() -> str:
    """Generate a fresh 8-char hex id for a cita's [orbit:xxx] tag."""
    return secrets.token_hex(4)
from core.log import find_project, resolve_file


# ── Export ─────────────────────────────────────────────────────────────

_KIND_TO_SECTION = {
    "task":      "tasks",
    "milestone": "milestones",
    "event":     "events",
    "reminder":  "reminders",
}


def _find_cita_by_orbit_id(data: dict, orbit_id: str) -> Optional[tuple]:
    """Return (kind, item) for the cita with the given orbit_id, or None."""
    for kind, section in _KIND_TO_SECTION.items():
        for it in data.get(section, []):
            if it.get("orbit_id") == orbit_id:
                return (kind, it)
    return None


def _find_cita_by_desc(data: dict, pattern: str) -> list:
    """Return list of (kind, item) whose desc matches ``pattern`` (case-insensitive substring)."""
    out = []
    needle = pattern.lower()
    for kind, section in _KIND_TO_SECTION.items():
        for it in data.get(section, []):
            if needle in it.get("desc", "").lower():
                out.append((kind, it))
    return out


def _disambig_pick(matches: list) -> Optional[tuple]:
    """Interactive picker for multi-match list. Returns (kind, item) or None."""
    if not sys.stdin.isatty():
        print(f"Múltiples coincidencias ({len(matches)}); CLI no interactiva — usa --orbit-id.")
        return None
    print(f"Múltiples coincidencias ({len(matches)}):")
    for j, (kind, it) in enumerate(matches, 1):
        emoji = _KIND_EMOJI.get(kind, "")
        oid = it.get("orbit_id", "?")
        print(f"  {j}. {emoji} {it['desc']} ({it.get('date', '?')}) [orbit:{oid}]")
    try:
        raw = input("Selecciona (#, o vacío para cancelar): ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return None
    if not raw:
        return None
    if raw.isdigit():
        idx = int(raw) - 1
        if 0 <= idx < len(matches):
            return matches[idx]
    print("Cancelado.")
    return None


def _next_occurrence_for_export(item: dict) -> Optional[str]:
    """For a recurring cita, return the next occurrence date (today or later).

    Non-recurring → returns item['date']. Returns None if the recurring
    series has passed its ``until``.
    """
    if not item.get("recur"):
        return item.get("date")
    try:
        start = _date.fromisoformat(item["date"])
    except (KeyError, ValueError):
        return None
    today = _date.today()
    until_iso = item.get("until")
    until = _date.fromisoformat(until_iso) if until_iso else None
    cur = start
    # Walk forward until cur >= today (cap defensively).
    for _ in range(2000):
        if cur >= today:
            return cur.isoformat()
        if until and cur > until:
            return None
        nxt = _next_occurrence(cur.isoformat(), item["recur"], cur.isoformat())
        nxt_d = _date.fromisoformat(nxt)
        if nxt_d <= cur:
            return None   # recur didn't advance
        cur = nxt_d
    return None


def _copy_to_clipboard(text: str) -> bool:
    """Copy text to macOS clipboard. Return True on success."""
    try:
        subprocess.run(["pbcopy"], input=text.encode(), check=True, timeout=2)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        return False


def run_ics_share(project: str,
                   orbit_id: Optional[str] = None,
                   desc: Optional[str] = None,
                   out: Optional[str] = None) -> int:
    """Export one cita to a single-VEVENT .ics. See module docstring."""
    project_dir = find_project(project)
    if project_dir is None:
        return 1
    project_name = project_dir.name
    data = _read_agenda(resolve_file(project_dir, "agenda"))

    # 1. Resolve which cita.
    target = None
    if orbit_id:
        target = _find_cita_by_orbit_id(data, orbit_id)
        if target is None:
            print(f"Error: no se encontró cita con orbit-id '{orbit_id}' en {project_name}.")
            return 1
    elif desc:
        matches = _find_cita_by_desc(data, desc)
        if not matches:
            print(f"Error: ninguna cita coincide con '{desc}' en {project_name}.")
            return 1
        if len(matches) == 1:
            target = matches[0]
        else:
            target = _disambig_pick(matches)
            if target is None:
                return 1
    else:
        print("Uso: orbit ics-share <project> [--orbit-id ID | --desc PATTERN] [--out PATH]")
        return 2

    kind, item = target

    # 2. Decide which date to render (next occurrence for recurring).
    out_date = _next_occurrence_for_export(item)
    if out_date is None:
        print(f"Error: la serie recurrente ya expiró (until={item.get('until')}).")
        return 1
    is_recur = bool(item.get("recur"))
    if is_recur and out_date != item.get("date"):
        print(f"ℹ️  Recurrente: exportada la próxima ocurrencia ({out_date}), no la serie.")

    # 3. Render VEVENT + VCALENDAR wrapper.
    occurrence_arg = out_date if is_recur else None
    body_lines = render_vevent(item, kind, project_name,
                                occurrence_date=occurrence_arg)
    label = f"Orbit · {project_name} · {item['desc']}"
    ics_text = _calendar_wrapper(label, body_lines)

    # 4. Pick output path.
    if out:
        out_path = Path(out).expanduser()
    else:
        oid = item.get("orbit_id") or "anon"
        out_path = Path(f"/tmp/orbit-{oid}.ics")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(ics_text)

    # 5. Copy path to clipboard (for drag/attach into Mail).
    abs_path = str(out_path.resolve())
    clipped = _copy_to_clipboard(abs_path)

    print(f"✓ Exportada cita '{item['desc']}' ({out_date}) → {out_path}")
    print(f"  {len(ics_text)} bytes, kind={kind}, orbit-id={item.get('orbit_id') or 'n/a'}")
    if clipped:
        print(f"  📋 Path copiado al portapapeles.")
    return 0


# ── Import ─────────────────────────────────────────────────────────────

def _read_clipboard() -> Optional[str]:
    """Return clipboard text or None on failure."""
    try:
        res = subprocess.run(["pbpaste"], capture_output=True, timeout=2, check=True)
        return res.stdout.decode("utf-8", errors="replace")
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        return None


def _unfold(text: str) -> str:
    """RFC-5545 line unfolding: a CRLF followed by SP/HTAB is a continuation."""
    return (text.replace("\r\n ", "").replace("\r\n\t", "")
                .replace("\n ", "").replace("\n\t", ""))


def _unescape(s: str) -> str:
    """Reverse of core.ics._escape (TEXT-type)."""
    return (s.replace("\\n", "\n").replace("\\N", "\n")
             .replace("\\,", ",").replace("\\;", ";")
             .replace("\\\\", "\\"))


def _split_prop_line(line: str) -> tuple[str, dict, str]:
    """Split ``KEY[;param=val;…]:value`` → (key, params_dict, value)."""
    if ":" not in line:
        return ("", {}, "")
    head, _, val = line.partition(":")
    parts = head.split(";")
    key = parts[0].upper()
    params = {}
    for p in parts[1:]:
        if "=" in p:
            pk, _, pv = p.partition("=")
            params[pk.upper()] = pv
    return (key, params, val)


def parse_first_vevent(ics_text: str) -> tuple[Optional[dict], list]:
    """Parse the first VEVENT from .ics text.

    Returns (props, warnings):
      ``props`` keys: ``uid``, ``summary``, ``description``, ``dtstart``,
      ``dtend``, ``dtstart_is_date``, ``dtstart_tzid``, ``url``,
      ``location``, ``rrule``, ``valarm_minutes``, ``x_orbit_kind``,
      ``x_orbit_id``. Missing keys are absent.
      ``warnings`` is a list of human-readable issues.
    """
    warnings = []
    text = _unfold(ics_text)
    lines = text.splitlines()

    # Find first VEVENT block.
    in_event = False
    in_alarm = False
    vevent_lines = []
    valarm_minutes = None
    vevent_count = 0
    for raw in lines:
        line = raw.rstrip("\r")
        if line == "BEGIN:VEVENT":
            vevent_count += 1
            if vevent_count == 1:
                in_event = True
            continue
        if line == "END:VEVENT":
            if in_event:
                in_event = False
            continue
        if not in_event:
            continue
        if line == "BEGIN:VALARM":
            in_alarm = True
            continue
        if line == "END:VALARM":
            in_alarm = False
            continue
        if in_alarm:
            # Capture TRIGGER:-PTxxM (or H/D).
            if line.upper().startswith("TRIGGER"):
                m = re.search(r"TRIGGER[^:]*:-?PT?(\d+)([MHD])?", line, re.IGNORECASE)
                if m:
                    n = int(m.group(1))
                    unit = (m.group(2) or "M").upper()
                    mins = n * (1 if unit == "M" else 60 if unit == "H" else 1440)
                    valarm_minutes = mins
            continue
        vevent_lines.append(line)

    if vevent_count == 0:
        return (None, ["No se encontró ningún VEVENT en la entrada."])
    if vevent_count > 1:
        warnings.append(f"{vevent_count} VEVENTs en la entrada; importando solo el primero.")

    props: dict = {}
    for line in vevent_lines:
        key, params, val = _split_prop_line(line)
        if not key:
            continue
        if key == "SUMMARY":
            props["summary"] = _unescape(val)
        elif key == "DESCRIPTION":
            props["description"] = _unescape(val)
        elif key == "DTSTART":
            props["dtstart"] = val
            props["dtstart_is_date"] = (params.get("VALUE") == "DATE")
            props["dtstart_tzid"] = params.get("TZID")
        elif key == "DTEND":
            props["dtend"] = val
            props["dtend_is_date"] = (params.get("VALUE") == "DATE")
        elif key == "URL":
            props["url"] = _unescape(val)
        elif key == "LOCATION":
            props["location"] = _unescape(val)
        elif key == "RRULE":
            props["rrule"] = val
            warnings.append("RRULE detectada — importando solo la primera ocurrencia, sin la regla.")
        elif key == "UID":
            props["uid"] = val
        elif key == "X-ORBIT-KIND":
            props["x_orbit_kind"] = val
        elif key == "X-ORBIT-ID":
            props["x_orbit_id"] = val

    if valarm_minutes is not None:
        props["valarm_minutes"] = valarm_minutes
    return (props, warnings)


def _parse_dt(val: str, is_date: bool, tzid: Optional[str]) -> tuple[str, Optional[str]]:
    """Convert ``DTSTART``/``DTEND`` value to (date_iso, time_iso_or_None).

    ``is_date`` True → all-day → (YYYY-MM-DD, None).
    Otherwise YYYYMMDDTHHMMSS[Z] → (YYYY-MM-DD, HH:MM). UTC ('Z') is
    converted to local; other TZIDs are taken at face value (floating).
    """
    if is_date or "T" not in val:
        # YYYYMMDD → YYYY-MM-DD
        v = val.rstrip("Z")[:8]
        return (f"{v[:4]}-{v[4:6]}-{v[6:8]}", None)
    # Has a time part.
    is_utc = val.endswith("Z")
    body = val.rstrip("Z")
    d, _, t = body.partition("T")
    iso_date = f"{d[:4]}-{d[4:6]}-{d[6:8]}"
    hh = t[:2]; mm = t[2:4]
    if is_utc:
        # Convert UTC → local via datetime arithmetic.
        try:
            dt_utc = datetime(int(d[:4]), int(d[4:6]), int(d[6:8]),
                              int(hh), int(mm))
            offset = datetime.now() - datetime.utcnow()
            dt_local = dt_utc + timedelta(seconds=round(offset.total_seconds()))
            iso_date = dt_local.strftime("%Y-%m-%d")
            return (iso_date, dt_local.strftime("%H:%M"))
        except ValueError:
            pass
    return (iso_date, f"{hh}:{mm}")


def _is_meeting_url(s: str) -> bool:
    """Cheap match for Zoom/Meet/Teams/WebEx URLs."""
    if not s.startswith(("http://", "https://")):
        return False
    low = s.lower()
    return any(host in low for host in (
        "zoom.us", "meet.google.com", "teams.microsoft.com",
        "webex.com", "indico.cern.ch", "bluejeans.com",
    ))


def _strip_orbit_summary_prefix(summary: str, kind_emoji: str = "") -> str:
    """Strip the ``[<project>] [<emoji>] `` prefix orbit prepends in
    ``SUMMARY`` when exporting. Only applied when we're importing a
    round-trip (X-ORBIT-KIND present), so non-orbit .ics keep their
    original summary intact.
    """
    if not summary:
        return summary
    # Drop the leading "[<project>] " block.
    m = re.match(r"^\[[^\]]+\]\s+", summary)
    if not m:
        return summary
    rest = summary[m.end():]
    # Optional: drop a leading kind emoji (✅🏁💬) followed by space.
    if kind_emoji and rest.startswith(kind_emoji + " "):
        rest = rest[len(kind_emoji) + 1:]
    else:
        # Best-effort: drop any of our known kind emojis at the start.
        for e in ("✅", "🏁", "💬", "📊"):
            if rest.startswith(e + " "):
                rest = rest[len(e) + 1:]
                break
    return rest.strip()


def _strip_orbit_tag(text: str) -> str:
    """Drop ``[orbit:xxxxxxxx]`` and its surrounding inline whitespace.

    Preserves newlines so the line structure of ``DESCRIPTION`` survives
    for downstream per-line processing.
    """
    if not text:
        return text
    # Strip the tag + any spaces/tabs immediately around it (but NOT newlines).
    cleaned = re.sub(r"[ \t]*\[orbit:[a-f0-9]+\][ \t]*", "", text)
    # Drop lines that became empty after the strip.
    out_lines = [ln for ln in cleaned.splitlines() if ln.strip()]
    return "\n".join(out_lines).strip()


def _props_to_orbit_item(props: dict, kind: str) -> tuple[dict, list]:
    """Build the agenda item dict from parsed VEVENT props. Returns (item, warnings)."""
    warnings = []
    summary = props.get("summary", "(sin título)")
    # If this is an orbit-origin .ics (X-ORBIT-KIND present), strip the
    # "[<project>] <emoji> " prefix the exporter adds for Calendar.app UI.
    if props.get("x_orbit_kind"):
        emoji = _KIND_EMOJI.get(kind, "")
        summary = _strip_orbit_summary_prefix(summary, emoji)
    dtstart = props.get("dtstart") or ""
    dtend   = props.get("dtend") or ""
    is_date = bool(props.get("dtstart_is_date"))
    tzid    = props.get("dtstart_tzid")

    if tzid and tzid not in ("Europe/Madrid",):
        warnings.append(f"TZID={tzid} no es Europe/Madrid; hora interpretada como floating local.")

    date_iso, time_iso = _parse_dt(dtstart, is_date, tzid)

    end_date_iso = None
    end_time_iso = None
    if dtend:
        end_is_date = bool(props.get("dtend_is_date"))
        end_date_iso, end_time_iso = _parse_dt(dtend, end_is_date, tzid)

    # Build the time string per kind.
    item: dict = {
        "desc":  summary.strip(),
        "date":  date_iso,
        "notes": [],
        "orbit_id": _new_orbit_id(),
    }
    if kind == "task":
        item["time"] = time_iso
        item["ring"] = None
        item["recur"] = None
        item["until"] = None
        item["status"] = "pending"
        item["cloud_verified"] = False
    elif kind == "milestone":
        item["time"] = time_iso
        item["ring"] = None
        item["recur"] = None
        item["until"] = None
        item["status"] = "pending"
        item["cloud_verified"] = False
    elif kind == "reminder":
        item["time"] = time_iso
        item["ring"] = None
        item["recur"] = None
        item["until"] = None
        item["cancelled"] = False
        item["cloud_verified"] = False
    elif kind == "event":
        # For events: combine start+end into "HH:MM-HH:MM" if both present
        # and different; else just the start time.
        item["end"] = None
        item["recur"] = None
        item["until"] = None
        item["ring"] = None
        item["cloud_verified"] = False
        if is_date:
            item["time"] = None
            # All-day with multi-day range: end is exclusive in iCal.
            if end_date_iso and end_date_iso > date_iso:
                # Subtract one day (iCal DTEND is exclusive for VALUE=DATE).
                try:
                    inclusive_end = (_date.fromisoformat(end_date_iso)
                                      - timedelta(days=1)).isoformat()
                    if inclusive_end != date_iso:
                        item["end"] = inclusive_end
                except ValueError:
                    pass
        elif time_iso and end_time_iso and end_time_iso != time_iso:
            item["time"] = f"{time_iso}-{end_time_iso}"
            if end_date_iso and end_date_iso != date_iso:
                item["end"] = end_date_iso
        else:
            item["time"] = time_iso

    # VALARM → ring (if non-zero — at-start alarms are default for agenda kinds).
    valarm_mins = props.get("valarm_minutes")
    if valarm_mins is not None and valarm_mins > 0:
        # Express as Nm / Nh / Nd
        if valarm_mins % 1440 == 0:
            item["ring"] = f"{valarm_mins // 1440}d"
        elif valarm_mins % 60 == 0:
            item["ring"] = f"{valarm_mins // 60}h"
        else:
            item["ring"] = f"{valarm_mins}m"

    # Notes from DESCRIPTION (strip embedded orbit-id tag).
    description = _strip_orbit_tag(props.get("description", ""))
    # Strip leading "Proyecto: <name>" line (orbit's own export).
    desc_lines = [ln for ln in description.splitlines()
                  if not ln.startswith("Proyecto:")]
    notes = [ln.strip() for ln in desc_lines if ln.strip()]

    # URL/LOCATION → 🚪 note (only one, prefer URL since it's machine-readable).
    meeting_ref = props.get("url") or props.get("location")
    if meeting_ref:
        notes.append(f"🚪 {meeting_ref}")

    item["notes"] = notes
    return (item, warnings)


def _detect_kind(props: dict, warnings: list) -> Optional[str]:
    """Decide which orbit kind the VEVENT maps to. May prompt the user."""
    # 1. Round-trip from orbit.
    xkind = props.get("x_orbit_kind")
    if xkind in ("task", "milestone", "event", "reminder"):
        return xkind
    if xkind == "cronograma":
        warnings.append("X-ORBIT-KIND=cronograma no es importable (los cronogramas viven en cronos/crono-*.md); tratando como event.")
        return "event"

    # 2. Shape-based: all-day or time-range → event.
    if props.get("dtstart_is_date"):
        return "event"
    dtstart = props.get("dtstart", "")
    dtend   = props.get("dtend", "")
    if dtstart and dtend and dtstart != dtend:
        return "event"

    # 3. Ambiguous (single time or no time): prompt.
    if not sys.stdin.isatty():
        warnings.append("Kind ambiguo y CLI no interactiva; usando 'event' por defecto.")
        return "event"
    print("\n¿Qué tipo de cita es?")
    print("  1. ✅ task")
    print("  2. 🏁 milestone (ms)")
    print("  3. 📅 event  (default)")
    print("  4. 💬 reminder (rem)")
    try:
        raw = input("Selecciona [1/2/3/4, vacío=3]: ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return None
    mapping = {"1": "task", "2": "milestone", "3": "event", "4": "reminder", "": "event"}
    return mapping.get(raw)


def _conflict_resolution(existing: dict, new: dict, kind: str) -> Optional[str]:
    """Prompt for conflict. Returns one of 'duplicate', 'overwrite', 'cancel'."""
    if not sys.stdin.isatty():
        return "duplicate"   # safest non-interactive default
    print(f"\n⚠️  Ya existe una cita similar en {kind}:")
    print(f"    {existing.get('desc')} ({existing.get('date')}) [orbit:{existing.get('orbit_id')}]")
    print(f"    Importando: {new['desc']} ({new['date']})")
    try:
        raw = input("[d-duplicar / o-overwrite / c-cancel]: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        return "cancel"
    if raw in ("o", "overwrite"):
        return "overwrite"
    if raw in ("c", "cancel"):
        return "cancel"
    return "duplicate"   # default


def run_ics_import(project: str,
                    path: Optional[str] = None,
                    clipboard: bool = False) -> int:
    """Import one VEVENT into a project's agenda.md. See module docstring."""
    project_dir = find_project(project)
    if project_dir is None:
        return 1
    project_name = project_dir.name

    # 1. Read .ics text.
    if clipboard:
        ics_text = _read_clipboard()
        if not ics_text:
            print("Error: portapapeles vacío o pbpaste no disponible.")
            return 1
    elif path:
        p = Path(path).expanduser()
        if not p.exists():
            print(f"Error: no existe el fichero {p}.")
            return 1
        ics_text = p.read_text()
    else:
        print("Uso: orbit ics-import <project> <path.ics>  |  --clipboard")
        return 2

    # 2. Parse first VEVENT.
    props, warnings = parse_first_vevent(ics_text)
    if props is None:
        for w in warnings:
            print(f"⚠️  {w}")
        return 1

    # 3. Decide kind.
    kind = _detect_kind(props, warnings)
    if kind is None:
        print("Cancelado.")
        return 1

    # 4. Build orbit item.
    item, build_warnings = _props_to_orbit_item(props, kind)
    warnings.extend(build_warnings)

    # 5. Conflict check (same desc + date in target section).
    data = _read_agenda(resolve_file(project_dir, "agenda"))
    section = _KIND_TO_SECTION[kind]
    existing = next(
        (it for it in data.get(section, [])
         if it.get("desc") == item["desc"] and it.get("date") == item["date"]),
        None
    )
    overwrite_idx = None
    if existing is not None:
        decision = _conflict_resolution(existing, item, kind)
        if decision == "cancel":
            print("Cancelado.")
            return 1
        if decision == "overwrite":
            # Find the index in the section list.
            overwrite_idx = next(
                (i for i, it in enumerate(data.get(section, []))
                 if it.get("orbit_id") == existing.get("orbit_id")),
                None
            )

    # 6. Print warnings (parser, build, TZ, RRULE, etc.).
    for w in warnings:
        print(f"⚠️  {w}")

    # 7. Confirm before writing.
    print(f"\nImportar a {project_name}:")
    print(f"  kind:  {kind} ({_KIND_EMOJI.get(kind, '')})")
    print(f"  desc:  {item['desc']}")
    print(f"  date:  {item['date']}")
    if item.get("time"):
        print(f"  time:  {item['time']}")
    if item.get("ring"):
        print(f"  ring:  {item['ring']}")
    if item.get("notes"):
        for n in item["notes"]:
            print(f"  note:  {n}")
    print(f"  orbit-id: {item['orbit_id']}")
    if sys.stdin.isatty():
        try:
            raw = input("¿Confirmar? [Y/n]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            return 1
        if raw in ("n", "no"):
            print("Cancelado.")
            return 1

    # 8. Write.
    if overwrite_idx is not None:
        data[section][overwrite_idx] = item
    else:
        data.setdefault(section, []).append(item)
    _write_agenda(resolve_file(project_dir, "agenda"), data)

    print(f"✓ Importada cita '{item['desc']}' en {project_name} ({section})")
    # Dash + .ics regen are triggered automatically by run_command's
    # _DASH_TRIGGERS hook once this returns 0 (since v0.33). No manual
    # write_workspace call here — that would double the work.
    return 0

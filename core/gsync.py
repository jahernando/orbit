"""gsync — push Orbit tasks, milestones and events to local apps + Google.

  orbit gsync                    # push pending items
  orbit gsync --dry-run          # preview without writing
  orbit gsync --list-calendars   # show available Calendar.app calendars

Architecture:
  - Events → Calendar.app via AppleScript (one calendar per project type)
              The calendar's backing account (Google, iCloud, Exchange…)
              is irrelevant — orbit just talks to Calendar.app.
  - Tasks + Milestones → Google Tasks API (one TaskList per project type)
              Legacy; will move to Reminders.app via AppleScript later.
  - Orbit is the source of truth (one-directional sync)
  - Sync IDs stored in .gsync-ids.json per project (not in agenda.md)
  - Synced items show ☁️ marker in agenda.md
  - Recurring events use RRULE
  - Snapshots stored in .gsync-ids.json for drift detection

Config file: calendar-sync.json in ORBIT_HOME (auto-migrated from
google-sync.json on first read).
"""

import json
import re
import secrets
import subprocess
from datetime import date
from pathlib import Path
from typing import Optional

from core.config import ORBIT_HOME, ORBIT_PROMPT, normalize as _normalize
from core.log import resolve_file
from core.config import iter_project_dirs
from core.project import _find_new_project, _is_new_project, _read_project_meta
from core.agenda_cmds import _read_agenda, _write_agenda

CONFIG_PATH        = ORBIT_HOME / "calendar-sync.json"
_LEGACY_CONFIG     = ORBIT_HOME / "google-sync.json"

_IDS_FILE = ".gsync-ids.json"


def _ids_path(project_dir: Path) -> Path:
    """Path to .gsync-ids.json in a project directory."""
    return project_dir / _IDS_FILE


def _load_ids(project_dir: Path) -> dict:
    """Load sync IDs mapping for a project. Returns {key: {gtask_id, gcal_id}}."""
    p = _ids_path(project_dir)
    if p.exists():
        return json.loads(p.read_text())
    return {}


def _save_ids(project_dir: Path, ids: dict) -> None:
    """Save sync IDs mapping for a project."""
    _ids_path(project_dir).write_text(json.dumps(ids, indent=2, ensure_ascii=False) + "\n")


def _item_key(item: dict) -> str:
    """Build a unique key for an item.

    Recurring items must include the anchor date — otherwise multiple series
    sharing the same description (e.g. three "🏊 natación" weekly series on
    Mon/Wed/Fri) collapse onto the same key and only one ever syncs.
    """
    if item.get("recur"):
        return f"{item.get('desc', '')}::🔄{item['recur']}::{item.get('date', '')}"
    return f"{item.get('desc', '')}::{item.get('date', '')}"


_SNAPSHOT_FIELDS = ("desc", "date", "end", "time", "recur", "until", "ring", "status")


def _make_snapshot(item: dict) -> dict:
    """Extract serializable fields for drift detection."""
    return {k: item[k] for k in _SNAPSHOT_FIELDS if item.get(k)}


def _diff_snapshot(current: dict, saved: dict) -> list:
    """Compare current item state to saved snapshot. Returns list of change descriptions."""
    if not saved:
        return []
    diffs = []
    for k in _SNAPSHOT_FIELDS:
        old = saved.get(k)
        new = current.get(k)
        if old != new:
            if old and new:
                diffs.append(f"{k}: {old} → {new}")
            elif new:
                diffs.append(f"{k}: (vacío) → {new}")
            elif old:
                diffs.append(f"{k}: {old} → (eliminado)")
    return diffs


# ── Config ──────────────────────────────────────────────────────────────────

def _normalize_tipo(tipo_label: str) -> str:
    """Normalize project type label to a canonical key."""
    return _normalize(tipo_label)


def _load_config() -> dict:
    """Load calendar-sync.json config. Migrate from google-sync.json if needed."""
    if CONFIG_PATH.exists():
        return json.loads(CONFIG_PATH.read_text())
    if _LEGACY_CONFIG.exists():
        # One-time auto-migration; user is told to update calendar names.
        config = json.loads(_LEGACY_CONFIG.read_text())
        _save_config(config)
        print(f"ℹ️  Config migrada: {_LEGACY_CONFIG.name} → {CONFIG_PATH.name}")
        print(f"   Cambia los IDs de Google Calendar por los nombres tal como")
        print(f"   aparecen en Calendar.app (e.g. \"🚀 orbit-ws\").")
        return config
    config = {
        "calendars": {},
        "task_lists": {},
        "sync_tasks": True,
        # Default for fresh installs: tasks/ms/reminders go to Calendar.app
        # as events (alarm via CalendarAgent). See _agenda_backend().
        "reminders_backend": "calendar",
    }
    _save_config(config)
    return config


def _sync_tasks_enabled(config: dict) -> bool:
    """Check if task sync is enabled. Default True for backwards compat."""
    return config.get("sync_tasks", True)


def _sync_milestones_enabled(config: dict) -> bool:
    """Check if milestone sync is enabled. Default True for backwards compat."""
    return config.get("sync_milestones", True)


# ── Agenda backend (tasks/milestones/reminders) ──────────────────────────────
#
# Two backends are supported. Choose with `reminders_backend` in
# calendar-sync.json:
#
#   "calendar"  → tasks/ms/rem sync as 0-min events with alarm to a single
#                 per-workspace calendar (e.g. "🚀orbit-ws-rem"). The alarm
#                 fires via macOS CalendarAgent (no Calendar.app needed).
#                 This is the default for new installs.
#
#   "reminders" → tasks/ms/rem sync as items in Reminders.app (legacy).
#                 Kept for fallback during the migration validation period.
#
# Existing configs without the key default to "calendar" too — flip back to
# "reminders" manually if the calendar route breaks something for you.

def _agenda_backend(config: dict) -> str:
    """Return "calendar" or "reminders" — see module note above."""
    val = (config.get("reminders_backend") or "calendar").lower()
    return "reminders" if val == "reminders" else "calendar"


def _agenda_calendar_name(config: dict) -> str:
    """Return the Calendar.app calendar name for tasks/ms/reminders.

    Falls back to ``<workspace-dir-name>-rem`` so a fresh setup just works.
    Override in calendar-sync.json with ``"agenda_calendar": "..."``.
    """
    explicit = config.get("agenda_calendar")
    if explicit:
        return explicit
    return f"{ORBIT_HOME.name}-rem"


def _save_config(config: dict) -> None:
    """Save config back to google-sync.json."""
    CONFIG_PATH.write_text(json.dumps(config, indent=2, ensure_ascii=False) + "\n")


def _get_project_tipo(project_dir: Path) -> str:
    """Get normalized project type key."""
    meta = _read_project_meta(project_dir)
    return _normalize_tipo(meta.get("tipo_label", ""))


# ── Description / title helpers ──────────────────────────────────────────────

def _project_url(project_dir: Path, config: dict) -> Optional[str]:
    """DORMANT (v0.29.4) — used to build a GitHub URL for the project file.
    Disabled because the link cluttered calendar event descriptions and the
    user never followed it. Kept here so a future ``cloud_url`` feature can
    reuse the path-building scaffolding. To revive: re-wire from
    :func:`_project_description`.
    """
    from urllib.parse import quote
    repo_url = config.get("repo_url")
    if not repo_url:
        return None
    from core.log import find_proyecto_file
    pfile = find_proyecto_file(project_dir)
    if not pfile:
        return None
    rel = pfile.relative_to(ORBIT_HOME)
    return f"{repo_url}/{quote(str(rel))}"


def _project_description(project_dir: Path, config: dict, html: bool = False) -> str:
    """Build the description embedded in synced calendar events / reminders.

    Always plain text "Proyecto: <name>". The ``html`` flag is preserved for
    callers (none in tree at the moment) that may want a richer rendering
    in the future.
    """
    return f"Proyecto: {project_dir.name}"


def _item_description(item: dict, base_desc: str, html: bool = False) -> str:
    """Combine item notes with project description for Google sync.

    Item notes (from indented lines in agenda.md) are prepended before the
    project description.
    """
    notes = item.get("notes") or []
    if not notes:
        return base_desc
    if html:
        notes_html = "<br>".join(notes)
        return f"{notes_html}<br><br>{base_desc}"
    else:
        notes_text = "\n".join(notes)
        return f"{notes_text}\n\n{base_desc}"


# ── Calendar.app (AppleScript) helpers ─────────────────────────────────────

def _osa(script: str, timeout: int = 30) -> Optional[str]:
    """Run osascript and return stdout (stripped) or None on error."""
    try:
        r = subprocess.run(["osascript", "-e", script],
                           capture_output=True, text=True, timeout=timeout)
        if r.returncode != 0:
            return None
        return r.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None


def _calendar_app_running() -> bool:
    out = _osa('tell application "System Events" to (exists process "Calendar")')
    return out == "true"


# ── Orbit-id: stable identifier embedded in Reminder body / Calendar description ──
#
# Every synced item gets an 8-char hex id assigned the first time it lands in
# Reminders.app or Calendar.app. The id is embedded as a tag in the item's body
# (Reminders) or description (Calendar):
#
#     [orbit:abc12345]              — non-recurring item or full series
#     [orbit:abc12345@YYYY-MM-DD]   — specific occurrence of a recurring series
#                                     (Reminders only — Calendar.app handles
#                                     recurrence natively as one event with RRULE)
#
# Match-by-orbit-id is bullet-proof against AppleScript timeouts, calendar
# renames, and user-driven title edits. It replaces the fragile match-by-name
# fallback as the primary lookup path.

_ORBIT_TAG_RE = re.compile(r"\[orbit:([0-9a-f]{8})(?:@(\d{4}-\d{2}-\d{2}))?\]")


def _new_orbit_id() -> str:
    """Generate a fresh 8-char hex id."""
    return secrets.token_hex(4)


def _build_orbit_tag(orbit_id: str, occurrence_date: Optional[str] = None) -> str:
    """Build the embedded tag. With occurrence_date for recurring Reminders."""
    if occurrence_date:
        return f"[orbit:{orbit_id}@{occurrence_date}]"
    return f"[orbit:{orbit_id}]"


def _parse_orbit_tag(text: str) -> tuple:
    """Extract (orbit_id, occurrence_date) from text. Both None if absent."""
    m = _ORBIT_TAG_RE.search(text or "")
    if not m:
        return None, None
    return m.group(1), m.group(2)


def _append_orbit_tag(body: str, tag: str) -> str:
    """Embed *tag* in *body*. Replaces any existing tag for the same orbit-id.

    Recurring Reminders advance their occurrence date on every `done`, so
    the tag changes from ``[orbit:xxx@2026-05-11]`` to
    ``[orbit:xxx@2026-05-18]``. Without in-place replacement the body would
    accumulate stale tags forever.
    """
    body = body or ""
    new_id, _ = _parse_orbit_tag(tag)
    if new_id:
        existing_re = re.compile(
            r"\[orbit:" + re.escape(new_id) + r"(?:@\d{4}-\d{2}-\d{2})?\]"
        )
        if existing_re.search(body):
            return existing_re.sub(tag, body)
    sep = "\n\n" if body.strip() else ""
    return body + sep + tag


def _esc(s: str) -> str:
    """Escape a string for AppleScript double-quoted literal."""
    return (s or "").replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def _build_date_var(var: str, iso_dt: str, all_day: bool = False) -> str:
    """AppleScript snippet that sets *var* to the given ISO date/time."""
    if "T" in iso_dt:
        date_part, time_part = iso_dt.split("T", 1)
        h, m = (time_part.split(":") + ["0", "0"])[:2]
    else:
        date_part = iso_dt
        h, m = "0", "0"
    y, mo, d = date_part.split("-")
    return (
        f'set {var} to current date\n'
        f'        set year of {var} to {int(y)}\n'
        f'        set month of {var} to {int(mo)}\n'
        f'        set day of {var} to {int(d)}\n'
        f'        set hours of {var} to {int(h)}\n'
        f'        set minutes of {var} to {int(m)}\n'
        f'        set seconds of {var} to 0'
    )


def _list_calendar_app_calendars() -> list:
    """Return list of calendar titles available in Calendar.app."""
    out = _osa('tell application "Calendar" to get title of every calendar')
    if not out:
        return []
    # AppleScript returns "name1, name2, name3"
    return [n.strip() for n in out.split(",") if n.strip()]


def _create_calendar_event(calendar_name: str, props: dict) -> Optional[str]:
    """Create event in Calendar.app and return its uid. None on error."""
    cal = _esc(calendar_name)
    sumr = _esc(props.get("summary", ""))
    desc = _esc(props.get("description", ""))
    loc  = _esc(props.get("location", ""))
    url  = _esc(props.get("url", ""))
    rrule = _esc(props.get("rrule", ""))
    alarm_minutes = props.get("alarm_minutes")

    extras = []
    if desc:  extras.append(f'set description of newEv to "{desc}"')
    if loc:   extras.append(f'set location of newEv to "{loc}"')
    if url:   extras.append(f'set url of newEv to "{url}"')
    if rrule: extras.append(f'set recurrence of newEv to "{rrule}"')
    if isinstance(alarm_minutes, int):
        # Calendar.app trigger interval is in minutes, negative = before event start
        extras.append(
            f'make new display alarm at end of display alarms of newEv '
            f'with properties {{trigger interval:-{int(alarm_minutes)}}}'
        )
    extras_block = "\n        ".join(extras) or "-- no extras"

    script = (
        f'tell application "Calendar"\n'
        f'    tell calendar "{cal}"\n'
        f'        {_build_date_var("startD", props["start_iso"])}\n'
        f'        {_build_date_var("endD", props["end_iso"])}\n'
        f'        set newEv to make new event with properties '
        f'{{summary:"{sumr}", start date:startD, end date:endD}}\n'
        f'        {extras_block}\n'
        f'        return uid of newEv\n'
        f'    end tell\n'
        f'end tell'
    )
    return _osa(script)


def _update_calendar_event(uid: str, calendar_name: str, props: dict) -> bool:
    """Update an existing event by uid. Returns True on success."""
    cal = _esc(calendar_name)
    uid_esc = _esc(uid)
    sumr = _esc(props.get("summary", ""))
    desc = _esc(props.get("description", ""))
    loc  = _esc(props.get("location", ""))
    url  = _esc(props.get("url", ""))
    rrule = _esc(props.get("rrule", ""))
    alarm_minutes = props.get("alarm_minutes")

    if isinstance(alarm_minutes, int):
        alarm_block = (
            f'        delete every display alarm of ev\n'
            f'        make new display alarm at end of display alarms of ev '
            f'with properties {{trigger interval:-{int(alarm_minutes)}}}'
        )
    else:
        # No --ring on the orbit item: clear any existing alarm so the event
        # doesn't keep notifying after the user removed the ring.
        alarm_block = '        delete every display alarm of ev'

    script = (
        f'tell application "Calendar"\n'
        f'    tell calendar "{cal}"\n'
        f'        try\n'
        f'            set ev to first event whose uid is "{uid_esc}"\n'
        f'        on error\n'
        f'            return "missing"\n'
        f'        end try\n'
        f'        set summary of ev to "{sumr}"\n'
        f'        {_build_date_var("startD", props["start_iso"])}\n'
        f'        {_build_date_var("endD", props["end_iso"])}\n'
        f'        set start date of ev to startD\n'
        f'        set end date of ev to endD\n'
        f'        set description of ev to "{desc}"\n'
        f'        set location of ev to "{loc}"\n'
        f'        set url of ev to "{url}"\n'
        f'        set recurrence of ev to "{rrule}"\n'
        f'{alarm_block}\n'
        f'        return "ok"\n'
        f'    end tell\n'
        f'end tell'
    )
    return _osa(script, timeout=60) == "ok"


def _find_calendar_event_by_title_date(calendar_name: str,
                                       summary: str,
                                       start_iso: str) -> Optional[str]:
    """Find event by exact summary on the start date. Returns uid or None.

    Used as a fallback when an update fails (uid stale after a calendar
    rename/recreate). Avoids creating duplicates of events that already
    exist under a fresh uid.
    """
    cal = _esc(calendar_name)
    sumr = _esc(summary)
    date_part = start_iso.split("T", 1)[0]
    y, mo, d = date_part.split("-")
    script = (
        f'tell application "Calendar"\n'
        f'    tell calendar "{cal}"\n'
        f'        set d0 to current date\n'
        f'        set year of d0 to {int(y)}\n'
        f'        set month of d0 to {int(mo)}\n'
        f'        set day of d0 to {int(d)}\n'
        f'        set hours of d0 to 0\n'
        f'        set minutes of d0 to 0\n'
        f'        set seconds of d0 to 0\n'
        f'        set d1 to d0 + (24 * hours)\n'
        f'        try\n'
        f'            set evs to (every event whose summary is "{sumr}" '
        f'and start date >= d0 and start date < d1)\n'
        f'            if (count of evs) > 0 then\n'
        f'                return uid of (item 1 of evs)\n'
        f'            end if\n'
        f'        end try\n'
        f'        return ""\n'
        f'    end tell\n'
        f'end tell'
    )
    out = _osa(script, timeout=60)
    return out if out else None


def _find_calendar_event_by_orbit_id(calendar_name: str,
                                     orbit_id: str) -> Optional[str]:
    """Find event by orbit-id tag in description. Returns uid or None.

    Matches both ``[orbit:xxx]`` and ``[orbit:xxx@date]`` (occurrence-tagged
    recurring items) — the needle is the open prefix without the closing
    bracket. 8 hex chars after ``orbit:`` is unique enough to make a false
    positive virtually impossible.
    """
    cal = _esc(calendar_name)
    needle = f"[orbit:{orbit_id}"
    script = (
        f'tell application "Calendar"\n'
        f'    tell calendar "{cal}"\n'
        f'        try\n'
        f'            set evs to (every event whose description contains "{needle}")\n'
        f'            if (count of evs) > 0 then\n'
        f'                return uid of (item 1 of evs)\n'
        f'            end if\n'
        f'        end try\n'
        f'        return ""\n'
        f'    end tell\n'
        f'end tell'
    )
    out = _osa(script, timeout=60)
    return out if out else None


def _delete_calendar_event(uid: str, calendar_name: str) -> bool:
    """Delete event by uid. Returns True if deleted (or already absent)."""
    cal = _esc(calendar_name)
    uid_esc = _esc(uid)
    script = (
        f'tell application "Calendar"\n'
        f'    tell calendar "{cal}"\n'
        f'        try\n'
        f'            delete (first event whose uid is "{uid_esc}")\n'
        f'            return "ok"\n'
        f'        on error\n'
        f'            return "missing"\n'
        f'        end try\n'
        f'    end tell\n'
        f'end tell'
    )
    return _osa(script) in ("ok", "missing")


# ── Reminders.app (AppleScript) helpers ─────────────────────────────────────

# orbit puts every task/ms/reminder of a workspace into a single Reminders list.
# Configure per workspace in calendar-sync.json with `"reminders_list": "🚀 orbit-ws"`.
# Falls back to "Orbit" (legacy name).
DEFAULT_REMINDERS_LIST = "Orbit"

# Item-kind prefix in the Reminder name (so users can scan visually):
_REMINDER_KIND_EMOJI = {
    "task":       "✅",
    "milestone":  "🏁",
    "reminder":   "💬",
    "cronograma": "📊",
}


def _reminders_app_running() -> bool:
    out = _osa('tell application "System Events" to (exists process "Reminders")')
    return out == "true"


def _reminders_list_name(config: dict) -> str:
    return config.get("reminders_list") or DEFAULT_REMINDERS_LIST


def _ensure_reminders_list(list_name: str) -> bool:
    """Create the list if it doesn't exist. Returns True on success."""
    name = _esc(list_name)
    script = (
        f'tell application "Reminders"\n'
        f'    if not (exists list "{name}") then\n'
        f'        make new list with properties {{name:"{name}"}}\n'
        f'    end if\n'
        f'    return "ok"\n'
        f'end tell'
    )
    return _osa(script, timeout=60) == "ok"


def _create_reminder_item(list_name: str, props: dict) -> Optional[str]:
    """Create a reminder in Reminders.app. Returns its id (uid)."""
    lst  = _esc(list_name)
    name = _esc(props.get("name", ""))
    body = _esc(props.get("body", ""))
    due_iso    = props.get("due_iso")    # YYYY-MM-DDTHH:MM or YYYY-MM-DD or None
    remind_iso = props.get("remind_iso") # alarm time; if None no alert

    extras = []
    base_props = [f'name:"{name}"']
    if body:
        extras.append(f'set body of newR to "{body}"')

    blocks = []
    if due_iso:
        blocks.append(_build_date_var("dueD", due_iso))
        base_props.append("due date:dueD")
    if remind_iso:
        blocks.append(_build_date_var("remindD", remind_iso))
        base_props.append("remind me date:remindD")

    blocks_text = "\n        ".join(blocks) if blocks else "-- no dates"
    extras_block = "\n        ".join(extras) if extras else "-- no extras"
    props_block = ", ".join(base_props)

    script = (
        f'tell application "Reminders"\n'
        f'    tell list "{lst}"\n'
        f'        {blocks_text}\n'
        f'        set newR to make new reminder with properties {{{props_block}}}\n'
        f'        {extras_block}\n'
        f'        return id of newR\n'
        f'    end tell\n'
        f'end tell'
    )
    return _osa(script, timeout=60)


def _update_reminder_item(uid: str, list_name: str, props: dict) -> bool:
    """Update reminder by uid. Returns True on success ("ok"), False on missing."""
    lst  = _esc(list_name)
    uid_esc = _esc(uid)
    name = _esc(props.get("name", ""))
    body = _esc(props.get("body", ""))
    due_iso    = props.get("due_iso")
    remind_iso = props.get("remind_iso")
    completed  = "true" if props.get("completed") else "false"

    set_lines = [f'set name of r to "{name}"',
                 f'set body of r to "{body}"',
                 f'set completed of r to {completed}']
    blocks = []
    if due_iso:
        blocks.append(_build_date_var("dueD", due_iso))
        set_lines.append("set due date of r to dueD")
    else:
        set_lines.append("set due date of r to missing value")
    if remind_iso:
        blocks.append(_build_date_var("remindD", remind_iso))
        set_lines.append("set remind me date of r to remindD")
    else:
        set_lines.append("set remind me date of r to missing value")

    blocks_text = "\n        ".join(blocks) if blocks else "-- no dates"
    sets_text = "\n        ".join(set_lines)

    script = (
        f'tell application "Reminders"\n'
        f'    tell list "{lst}"\n'
        f'        try\n'
        f'            set r to first reminder whose id is "{uid_esc}"\n'
        f'        on error\n'
        f'            return "missing"\n'
        f'        end try\n'
        f'        {blocks_text}\n'
        f'        {sets_text}\n'
        f'        return "ok"\n'
        f'    end tell\n'
        f'end tell'
    )
    return _osa(script, timeout=60) == "ok"


def _find_reminder_by_name(list_name: str, name: str) -> Optional[str]:
    """Find non-completed reminder by exact name. Returns id or None."""
    lst = _esc(list_name)
    name_esc = _esc(name)
    script = (
        f'tell application "Reminders"\n'
        f'    tell list "{lst}"\n'
        f'        try\n'
        f'            set rs to (every reminder whose name is "{name_esc}" '
        f'and completed is false)\n'
        f'            if (count of rs) > 0 then\n'
        f'                return id of (item 1 of rs)\n'
        f'            end if\n'
        f'        end try\n'
        f'        return ""\n'
        f'    end tell\n'
        f'end tell'
    )
    out = _osa(script, timeout=60)
    return out if out else None


def _find_reminder_by_orbit_id(list_name: str, orbit_id: str) -> Optional[str]:
    """Find a reminder whose body contains [orbit:<id>...]. Returns uid or None.

    Matches both ``[orbit:xxx]`` and ``[orbit:xxx@date]`` (occurrence-tagged).
    """
    lst = _esc(list_name)
    needle = f"[orbit:{orbit_id}"
    script = (
        f'tell application "Reminders"\n'
        f'    tell list "{lst}"\n'
        f'        try\n'
        f'            set rs to (every reminder whose body contains "{needle}")\n'
        f'            if (count of rs) > 0 then\n'
        f'                return id of (item 1 of rs)\n'
        f'            end if\n'
        f'        end try\n'
        f'        return ""\n'
        f'    end tell\n'
        f'end tell'
    )
    out = _osa(script, timeout=60)
    return out if out else None


def _read_reminder_body(uid: str, list_name: str) -> Optional[str]:
    """Read the body of a reminder by uid. None on failure."""
    lst = _esc(list_name)
    uid_esc = _esc(uid)
    script = (
        f'tell application "Reminders"\n'
        f'    tell list "{lst}"\n'
        f'        try\n'
        f'            return body of (first reminder whose id is "{uid_esc}")\n'
        f'        end try\n'
        f'        return ""\n'
        f'    end tell\n'
        f'end tell'
    )
    return _osa(script, timeout=30)


def _read_event_description(uid: str, calendar_name: str) -> Optional[str]:
    """Read the description of an event by uid. None on failure."""
    cal = _esc(calendar_name)
    uid_esc = _esc(uid)
    script = (
        f'tell application "Calendar"\n'
        f'    tell calendar "{cal}"\n'
        f'        try\n'
        f'            return description of (first event whose uid is "{uid_esc}")\n'
        f'        end try\n'
        f'        return ""\n'
        f'    end tell\n'
        f'end tell'
    )
    return _osa(script, timeout=30)


# ── Bulk fetch helpers (used by reverse sync: backend → orbit) ─────────────

# ASCII control chars used as record/field separators when AppleScript
# returns a stream of items. They never appear in legitimate user data.
_FETCH_FIELD_SEP  = "\x1F"  # Unit Separator
_FETCH_RECORD_SEP = "\x1E"  # Record Separator


def _fetch_completed_orbit_ids(list_name: str) -> set:
    """Return the set of orbit-ids whose reminder is currently ``completed``.

    Only iterates reminders with ``completed is true and body contains
    "[orbit:"`` server-side, so the AppleScript work scales with the number
    of done items (typically 0-2), not the total list size. Items without
    an orbit-id (manual reminders the user added) are skipped.
    """
    lst = _esc(list_name)
    fld = "(ASCII character 31)"
    rec = "(ASCII character 30)"
    script = (
        f'tell application "Reminders"\n'
        f'    tell list "{lst}"\n'
        f'        set fld to {fld}\n'
        f'        set rec to {rec}\n'
        f'        set out to ""\n'
        f'        try\n'
        f'            set rs to (every reminder whose completed is true and body contains "[orbit:")\n'
        f'            repeat with r in rs\n'
        f'                set out to out & (id of r) & fld & (body of r) & rec\n'
        f'            end repeat\n'
        f'        end try\n'
        f'        return out\n'
        f'    end tell\n'
        f'end tell'
    )
    out = _osa(script, timeout=60)
    if not out:
        return set()
    ids = set()
    for raw in out.split(_FETCH_RECORD_SEP):
        if not raw.strip():
            continue
        parts = raw.split(_FETCH_FIELD_SEP)
        if len(parts) < 2:
            continue
        body = parts[1]
        oid, _ = _parse_orbit_tag(body)
        if oid:
            ids.add(oid)
    return ids


def _fetch_all_events(calendar_name: str) -> list:
    """Bulk fetch every event from a calendar.

    Returns list of {"uid", "summary", "description", "start_iso",
    "end_iso", "all_day", "orbit_id"}. Recurring series surface as one
    entry per series (the anchor event), not per occurrence.

    Note: Calendar.app expands recurrences when iterating ``events``, so
    we filter to entries whose start date matches an "anchor" (first
    occurrence). For our purposes here we use the description's orbit-id
    to distinguish series — an item we created with [orbit:xxx] has only
    one such tag for the series, so AppleScript's ``whose description
    contains`` returns each series exactly once.
    """
    cal = _esc(calendar_name)
    fld = "(ASCII character 31)"
    rec = "(ASCII character 30)"
    script = (
        f'tell application "Calendar"\n'
        f'    tell calendar "{cal}"\n'
        f'        set fld to {fld}\n'
        f'        set rec to {rec}\n'
        f'        set out to ""\n'
        f'        repeat with e in (every event whose description contains "[orbit:")\n'
        f'            set s_str to ""\n'
        f'            try\n'
        f'                set sd to start date of e\n'
        f'                set s_str to (year of sd as text) & "-" & ¬\n'
        f'                  (text -2 thru -1 of ("0" & (month of sd as integer))) & "-" & ¬\n'
        f'                  (text -2 thru -1 of ("0" & (day of sd))) & "T" & ¬\n'
        f'                  (text -2 thru -1 of ("0" & (hours of sd))) & ":" & ¬\n'
        f'                  (text -2 thru -1 of ("0" & (minutes of sd)))\n'
        f'            end try\n'
        f'            set e_str to ""\n'
        f'            try\n'
        f'                set ed to end date of e\n'
        f'                set e_str to (year of ed as text) & "-" & ¬\n'
        f'                  (text -2 thru -1 of ("0" & (month of ed as integer))) & "-" & ¬\n'
        f'                  (text -2 thru -1 of ("0" & (day of ed))) & "T" & ¬\n'
        f'                  (text -2 thru -1 of ("0" & (hours of ed))) & ":" & ¬\n'
        f'                  (text -2 thru -1 of ("0" & (minutes of ed)))\n'
        f'            end try\n'
        f'            set desc_str to ""\n'
        f'            try\n'
        f'                set desc_str to description of e\n'
        f'            end try\n'
        f'            set out to out & (uid of e) & fld & (summary of e) & fld ¬\n'
        f'                & s_str & fld & e_str & fld & desc_str & rec\n'
        f'        end repeat\n'
        f'        return out\n'
        f'    end tell\n'
        f'end tell'
    )
    out = _osa(script, timeout=120)
    if not out:
        return []
    items = []
    seen_uids = set()
    for raw in out.split(_FETCH_RECORD_SEP):
        if not raw.strip():
            continue
        parts = raw.split(_FETCH_FIELD_SEP)
        if len(parts) < 5:
            continue
        uid, summary, start_iso, end_iso, description = parts[:5]
        # Calendar.app expands recurring events into one entry per occurrence
        # when iterating; dedupe by uid (the series uid is shared).
        if uid in seen_uids:
            continue
        seen_uids.add(uid)
        oid, _ = _parse_orbit_tag(description)
        items.append({
            "uid":         uid,
            "summary":     summary,
            "start_iso":   start_iso or None,
            "end_iso":     end_iso or None,
            "description": description,
            "orbit_id":    oid,
        })
    return items


def _delete_reminder_item(uid: str, list_name: str) -> bool:
    """Delete reminder by uid. Idempotent (missing → also true)."""
    lst = _esc(list_name)
    uid_esc = _esc(uid)
    script = (
        f'tell application "Reminders"\n'
        f'    tell list "{lst}"\n'
        f'        try\n'
        f'            delete (first reminder whose id is "{uid_esc}")\n'
        f'            return "ok"\n'
        f'        on error\n'
        f'            return "missing"\n'
        f'        end try\n'
        f'    end tell\n'
        f'end tell'
    )
    return _osa(script) in ("ok", "missing")


def _item_props_for_reminders(item: dict, project_name: str, kind: str) -> dict:
    """Build the property dict for _create/_update_reminder_item.

    kind: "task" | "milestone" | "reminder" | "cronograma"

    Embeds an [orbit:<id>] tag (or [orbit:<id>@<date>] for recurring items)
    at the end of the body so future syncs can match-by-id reliably.
    """
    from datetime import datetime
    from core.ring import resolve_ring_datetime

    emoji = _REMINDER_KIND_EMOJI.get(kind, "")
    prefix = f"{emoji} " if emoji else ""
    # Workspace prefix dropped: the Reminders list (🚀 orbit-ws / 🌿 orbit-ps)
    # already groups items by workspace, so the leading emoji was redundant.
    name = f"[{project_name}] {prefix}{item['desc']}"

    # Body: combine notes + orbit-id tag at the end
    notes = item.get("notes") or []
    body = "\n".join(notes) if notes else ""

    # Due date
    due_iso = None
    date_s = item.get("date")
    time_s = item.get("time")
    if date_s:
        if time_s:
            # reminder items in orbit always have time; tasks/ms may or may not
            due_iso = f"{date_s}T{time_s.split('-')[0]}"
        else:
            # all-day style (task without time): pick a sensible hour
            due_iso = f"{date_s}T09:00"

    # Alarm: items with --ring (task/ms) use that; reminder kind uses its own time
    remind_iso = None
    ring = item.get("ring")
    if kind == "reminder":
        # reminders fire AT their scheduled time (no extra ring usually)
        remind_iso = due_iso
    elif ring and date_s:
        ring_dt = resolve_ring_datetime(date_s, ring, due_time=time_s)
        if ring_dt:
            remind_iso = ring_dt.strftime("%Y-%m-%dT%H:%M")

    completed = (item.get("status") in ("done", "cancelled"))

    # Embed orbit-id tag. Recurring items get the occurrence date appended.
    orbit_id = item.get("_orbit_id")
    if orbit_id:
        occurrence = date_s if item.get("recur") else None
        body = _append_orbit_tag(body, _build_orbit_tag(orbit_id, occurrence))

    return {
        "name":      name,
        "body":      body,
        "due_iso":   due_iso,
        "remind_iso": remind_iso,
        "completed": completed,
    }


def _sync_one_to_reminders(list_name: str, item: dict, project_name: str,
                           kind: str, dry_run: bool) -> Optional[str]:
    """Create or update one orbit item in Reminders.app. Returns its id.

    Resolution order (most reliable → most fragile):
      1. Match-by-orbit-id (tag in body) — survives rename, dedup-proof
      2. Stored uid → update in place
      3. Match-by-name (legacy fallback for items synced before orbit-ids)
      4. Create new

    A failed _update on a found reminder does NOT fall through to _create —
    the reminder exists, we just couldn't update it (likely AppleScript
    timeout under iCloud sync pressure). Returning the matched uid keeps
    the mapping intact and avoids creating a duplicate.
    """
    props = _item_props_for_reminders(item, project_name, kind)
    name = props["name"]
    orbit_id = item.get("_orbit_id")
    uid = item.get("_gtask_id")

    if dry_run:
        print(f"  ~ {('actualizar' if uid else 'crear')}: {name}")
        return uid

    # 1. Try orbit-id match (survives renames, list recreations, timeouts).
    if orbit_id:
        found_uid = _find_reminder_by_orbit_id(list_name, orbit_id)
        if found_uid:
            _update_reminder_item(found_uid, list_name, props)
            return found_uid

    # 2. Try the stored uid directly.
    if uid:
        if _update_reminder_item(uid, list_name, props):
            return uid
        # Stored uid is stale — fall through to legacy name match.
        print(f"  ⚠️  Reminder uid={uid[:30]}… stale; busco por nombre")

    # 3. Legacy match-by-name (for items created before orbit-ids,
    #    or when our key changed and lost the reference).
    matched_uid = _find_reminder_by_name(list_name, name)
    if matched_uid:
        # Recover any existing orbit-id from the body so we don't generate a
        # fresh one and end up with two ids referring to the same reminder.
        existing_body = _read_reminder_body(matched_uid, list_name)
        recovered_id, _ = _parse_orbit_tag(existing_body)
        if recovered_id and recovered_id != orbit_id:
            item["_orbit_id"] = recovered_id
            props = _item_props_for_reminders(item, project_name, kind)
            print(f"  ↺ reasocio reminder y recupero orbit-id={recovered_id} ({name})")
        else:
            print(f"  ↺ asocio reminder existente ({name})")
        # Update in best-effort mode — even if it times out, return the uid
        # so we record the association. Update will retry on the next sync.
        _update_reminder_item(matched_uid, list_name, props)
        return matched_uid

    # 4. Create new.
    new_uid = _create_reminder_item(list_name, props)
    if not new_uid:
        print(f"  ⚠️  Error creando reminder '{name}' en \"{list_name}\"")
    return new_uid


def _sync_to_reminders_for_project(project_dir: Path, config: dict,
                                   dry_run: bool) -> tuple:
    """Sync all tasks + milestones + reminders of a project to Reminders.app.

    Returns (created, updated, skipped).
    """
    list_name = _reminders_list_name(config)
    if not _ensure_reminders_list(list_name):
        return 0, 0, 0

    agenda_path = resolve_file(project_dir, "agenda")
    data = _read_agenda(agenda_path)
    project_name = project_dir.name

    ids = _load_ids(project_dir)
    seen_recur_keys = set()

    total_c = total_u = total_s = 0
    changed_total = False
    ids_changed_total = False

    # Process each kind with the same generic loop
    for kind, items_key in (("task", "tasks"),
                            ("milestone", "milestones"),
                            ("reminder", "reminders")):
        items = data.get(items_key) or []
        # For 'reminder' kind, skip cancelled items
        if kind == "reminder":
            items = [r for r in items if not r.get("cancelled")]
        if not items:
            continue
        _migrate_recurring_keys(items, ids)
        sync_fn = lambda it, _k=kind: _sync_one_to_reminders(
            list_name, it, project_name, _k, dry_run)
        c, u, s, changed, ids_changed = _sync_item_loop(
            items, sync_fn, "gtask_id", _REMINDER_KIND_EMOJI.get(kind, kind),
            project_name, ids, seen_recur_keys, dry_run)
        total_c += c
        total_u += u
        total_s += s
        changed_total = changed_total or changed
        ids_changed_total = ids_changed_total or ids_changed

    if changed_total and not dry_run:
        _write_agenda(agenda_path, data)
    if ids_changed_total and not dry_run:
        _save_ids(project_dir, ids)
    return total_c, total_u, total_s


def _sync_cronos_for_project(project_dir: Path, config: dict,
                             dry_run: bool) -> tuple:
    """Sync each cronograma's next open leaf as a single Calendar event
    (calendar backend, default) or Reminder (reminders backend, legacy).

    For each ``cronos/crono-<name>.md``:
      - Compute dates over the task tree.
      - Find the next non-completed leaf with a computed end_date
        (overdue leaves keep their slot — they don't auto-advance).
      - Upsert a single 0-min event / reminder ``[proj] 📊 crono-<n>: <leaf desc>``
        on the next leaf's deadline.
      - When all leaves are done → delete the event (calendar) or mark the
        reminder completed (reminders).
      - When no leaf has a date → skip silently (cronograma is just an
        outline, not yet operational).

    Under the calendar backend, cronogramas land in the per-tipo events
    calendar (same as milestones and events). Storage keeps the
    ``ids["_cronos"][crono_name]`` namespace but switches ``gtask_id`` →
    ``gcal_id``; if a legacy ``gtask_id`` is found and Reminders.app is
    running, the old reminder is deleted opportunistically so the migration
    is invisible.

    Returns (created, updated, skipped).
    """
    cronos_dir = project_dir / "cronos"
    if not cronos_dir.exists():
        return 0, 0, 0
    crono_files = sorted(cronos_dir.glob("crono-*.md"))
    if not crono_files:
        return 0, 0, 0

    from core.cronograma import (_parse_crono_file, _compute_dates,
                                 next_open_leaf, cronograma_all_done,
                                 _leaf_deadline)

    backend = _agenda_backend(config)

    if backend == "calendar":
        tipo = _get_project_tipo(project_dir)
        cal_name = (config.get("calendars", {}).get(tipo)
                    or config.get("calendars", {}).get("default"))
        if not cal_name:
            return 0, 0, 0
        if not _calendar_app_running():
            return 0, 0, 0
        description = _project_description(project_dir, config, html=False)
        # Try once whether Reminders.app is around — drives the legacy
        # cleanup. Cached so we don't ask AppleScript repeatedly per crono.
        rem_list_for_cleanup = (_reminders_list_name(config)
                                if _reminders_app_running() else None)
        list_name = None
    else:
        list_name = _reminders_list_name(config)
        if not _ensure_reminders_list(list_name):
            return 0, 0, 0
        cal_name = None
        description = None
        rem_list_for_cleanup = None

    ids = _load_ids(project_dir)
    project_name = project_dir.name
    cronos_ids = ids.setdefault("_cronos", {})
    ids_changed = False

    total_c = total_u = total_s = 0

    for crono_path in crono_files:
        crono_name = crono_path.stem.removeprefix("crono-")
        try:
            data = _parse_crono_file(crono_path)
            _compute_dates(data["tasks"], data["metadata"])
        except Exception as exc:
            print(f"  ⚠️  [{project_name}] Error parseando crono '{crono_name}': {exc}")
            total_s += 1
            continue

        leaf = next_open_leaf(data)
        all_done = cronograma_all_done(data)

        if leaf is None and not all_done:
            total_s += 1
            continue

        existing = cronos_ids.get(crono_name) or {}
        orbit_id = existing.get("orbit_id") or _new_orbit_id()

        if backend == "calendar":
            # Migration cleanup: if we still have a legacy gtask_id, try to
            # remove the old reminder from Reminders.app (best-effort).
            legacy_gtask = existing.get("gtask_id")
            if legacy_gtask and rem_list_for_cleanup and not dry_run:
                _delete_reminder_item(legacy_gtask, rem_list_for_cleanup)

            # All leaves done → drop the event from Calendar.
            if all_done:
                existing_uid = existing.get("gcal_id")
                if existing_uid and not dry_run:
                    _delete_calendar_event(existing_uid, cal_name)
                if crono_name in cronos_ids and not dry_run:
                    cronos_ids.pop(crono_name, None)
                    ids_changed = True
                    total_u += 1
                else:
                    total_s += 1
                continue

            item = {
                "desc":      f"crono-{crono_name}: {leaf['title']}",
                "date":      _leaf_deadline(leaf).isoformat(),
                "time":      None,
                "ring":      None,
                "status":    "pending",
                "notes":     [f"Cronograma: cronos/{crono_path.name}"],
                "_gcal_id":  existing.get("gcal_id"),
                "_orbit_id": orbit_id,
            }

            try:
                new_uid = _sync_one_agenda_event(cal_name, item, project_name,
                                                  description, "cronograma",
                                                  dry_run=dry_run)
            except Exception as exc:
                print(f"  ⚠️  [{project_name}] Error sync crono '{crono_name}': {exc}")
                total_s += 1
                continue

            if dry_run:
                total_s += 1
                continue

            old_uid = existing.get("gcal_id")
            if new_uid and new_uid != old_uid:
                cronos_ids[crono_name] = {"gcal_id":  new_uid,
                                          "orbit_id": orbit_id,
                                          "leaf":     leaf["index"]}
                total_c += 1
                ids_changed = True
            elif old_uid:
                cronos_ids[crono_name]["gcal_id"]  = old_uid
                cronos_ids[crono_name]["orbit_id"] = orbit_id
                cronos_ids[crono_name]["leaf"]     = leaf["index"]
                # Forget the legacy reminder uid — it was just deleted above
                # (or will fail silently if missing).
                cronos_ids[crono_name].pop("gtask_id", None)
                total_u += 1
                ids_changed = True
            else:
                total_s += 1
            continue

        # ── Backend = "reminders" (legacy) ────────────────────────────────
        if leaf:
            desc = f"crono-{crono_name}: {leaf['title']}"
            date_s = _leaf_deadline(leaf).isoformat()
            status = "pending"
            tracked_leaf = leaf["index"]
        else:  # all_done
            desc = f"crono-{crono_name}"
            date_s = None
            status = "done"
            tracked_leaf = None

        item = {
            "desc":       desc,
            "date":       date_s,
            "time":       None,
            "ring":       None,
            "status":     status,
            "notes":      [f"Cronograma: cronos/{crono_path.name}"],
            "_gtask_id":  existing.get("gtask_id"),
            "_orbit_id":  orbit_id,
        }

        try:
            new_id = _sync_one_to_reminders(list_name, item, project_name,
                                            "cronograma", dry_run)
        except Exception as exc:
            print(f"  ⚠️  [{project_name}] Error sync crono '{crono_name}': {exc}")
            total_s += 1
            continue

        if dry_run:
            total_s += 1
            continue

        old_uid = existing.get("gtask_id")
        if new_id and new_id != old_uid:
            cronos_ids[crono_name] = {"gtask_id": new_id,
                                       "orbit_id": orbit_id,
                                       "leaf": tracked_leaf}
            total_c += 1
            ids_changed = True
        elif old_uid:
            cronos_ids[crono_name]["orbit_id"] = orbit_id
            cronos_ids[crono_name]["leaf"] = tracked_leaf
            total_u += 1
            ids_changed = True
        else:
            total_s += 1

    if ids_changed and not dry_run:
        _save_ids(project_dir, ids)

    return total_c, total_u, total_s


# ── Google API helpers (legacy: tasks/milestones only) ─────────────────────

def _get_tasks_service():
    from core.calendar_sync import _build_service
    return _build_service("tasks", "v1")


def _get_calendar_service():
    """DEPRECATED — kept only because run_gsync_migrate_recurring (one-shot
    legacy migration) still references it. Events now flow through
    Calendar.app via AppleScript."""
    from core.calendar_sync import _build_service
    return _build_service("calendar", "v3")


# ── TaskList management ─────────────────────────────────────────────────────

def _ensure_task_list(service, tipo: str, config: dict) -> Optional[str]:
    """Get or create a Google TaskList for this project type. Returns list ID."""
    list_id = config.get("task_lists", {}).get(tipo)
    if list_id:
        return list_id

    # Search existing lists
    from core.config import get_type_map
    type_emoji = get_type_map().get(tipo, "")
    list_name = f"{ORBIT_PROMPT}[{type_emoji}{tipo.capitalize()}]"
    try:
        results = service.tasklists().list(maxResults=100).execute()
    except Exception as e:
        if "accessNotConfigured" in str(e) or "tasks.googleapis.com" in str(e):
            print("⚠️  Google Tasks API no está habilitada en tu proyecto.")
            print("   Habilítala en: https://console.developers.google.com/apis/api/tasks.googleapis.com")
            return None
        raise
    for tl in results.get("items", []):
        if tl["title"] == list_name:
            config.setdefault("task_lists", {})[tipo] = tl["id"]
            _save_config(config)
            return tl["id"]

    # Create new list
    new_list = service.tasklists().insert(body={"title": list_name}).execute()
    config.setdefault("task_lists", {})[tipo] = new_list["id"]
    _save_config(config)
    print(f"  ✓ Creada TaskList: {list_name}")
    return new_list["id"]


# ── Task/Milestone sync ────────────────────────────────────────────────────

def _sync_one_task(service, tasklist_id: str, item: dict,
                   project_name: str, is_milestone: bool,
                   description: str, dry_run: bool) -> Optional[str]:
    """Sync a single task/milestone to Google Tasks. Returns Google Task ID."""
    prefix = "🏁 " if is_milestone else ""
    suffix = " 🔄" if item.get("recur") else ""
    title = f"{ORBIT_PROMPT}[{project_name}] {prefix}{item['desc']}{suffix}"
    notes = _item_description(item, description)

    # Build due date (Google Tasks uses RFC 3339)
    due = None
    if item.get("date"):
        due = f"{item['date']}T00:00:00.000Z"

    status_map = {"pending": "needsAction", "done": "completed", "cancelled": "completed"}
    g_status = status_map.get(item["status"], "needsAction")

    gtask_id = item.get("_gtask_id")  # looked up from .gsync-ids.json
    if gtask_id:
        # Update existing
        if dry_run:
            print(f"  ~ actualizar: {title}")
            return gtask_id
        try:
            body = {"title": title, "notes": notes, "status": g_status}
            if due:
                body["due"] = due
            service.tasks().patch(
                tasklist=tasklist_id, task=gtask_id, body=body
            ).execute()
            return gtask_id
        except Exception as e:
            print(f"  ⚠️  Error actualizando '{item['desc']}': {e}")
            return gtask_id
    else:
        # Create new
        if dry_run:
            print(f"  ~ crear: {title}")
            return None
        try:
            body = {"title": title, "notes": notes, "status": g_status}
            if due:
                body["due"] = due
            result = service.tasks().insert(
                tasklist=tasklist_id, body=body
            ).execute()
            return result["id"]
        except Exception as e:
            print(f"  ⚠️  Error creando '{item['desc']}': {e}")
            return None


def _migrate_recurring_keys(items: list, ids: dict) -> None:
    """Migrate legacy recurring keys to the current format in-place.

    Two historical key formats coexist for recurring items:

      v0  ``desc::date``               (very old — pre-2026)
      v1  ``desc::🔄recur``             (single key per series, lost identity
                                         when multiple series shared a desc)
      v2  ``desc::🔄recur::date``       (current — anchor date is part of
                                         identity, fixes the natación bug)

    Without this migration, the v1→v2 transition would orphan every
    recurring item's stored uid+orbit_id, the next sync would think the
    item is brand new, find_by_orbit_id would miss, find_by_title_date
    would also miss (because we changed the summary format too), and we'd
    end up with duplicate Calendar events. That's exactly what happened
    with the 7 stale `🚀[…]` events in orbit-ws.

    For each recurring item: if its current key is missing from ids but
    one of the legacy keys exists, rename in place.
    """
    for item in items:
        if not item.get("recur"):
            continue
        new_key = _item_key(item)
        if new_key in ids:
            continue
        # v1 legacy: desc::🔄recur (no anchor date)
        v1_key = f"{item.get('desc', '')}::🔄{item['recur']}"
        if v1_key in ids:
            ids[new_key] = ids.pop(v1_key)
            continue
        # v0 legacy: desc::date (treated like a non-recurring at the time)
        v0_key = f"{item.get('desc', '')}::{item.get('date', '')}"
        if v0_key in ids:
            ids[new_key] = ids.pop(v0_key)


def _sync_item_loop(items: list, sync_fn, id_key: str, label: str,
                    project_name: str, ids: dict, seen_recur_keys: set,
                    dry_run: bool) -> tuple:
    """Generic sync loop for tasks, milestones, or events.

    Args:
        items: list of item dicts from agenda
        sync_fn: callable(item) -> Optional[str] (Google ID)
        id_key: "gtask_id" or "gcal_id"
        label: human label for error messages ("tarea", "hito", "evento")
        project_name: for error messages
        ids: gsync IDs dict (mutated in place)
        seen_recur_keys: set of already-processed recurring keys (mutated)
        dry_run: if True, no writes

    Returns:
        (created, updated, skipped, changed, ids_changed)
    """
    created = updated = skipped = 0
    changed = False
    ids_changed = False
    temp_key = f"_{id_key}"

    for item in items:
        key = _item_key(item)
        if item.get("recur"):
            if key in seen_recur_keys:
                skipped += 1
                continue
            seen_recur_keys.add(key)

        existing = ids.get(key, {})
        item[temp_key] = existing.get(id_key)
        # Resolve orbit-id with this priority:
        #   1. orbit-id already in the markdown line (most authoritative —
        #      the user could not have invented it, so it must be ours)
        #   2. orbit-id stored in .gsync-ids.json under this key
        #   3. fresh id (first time we see this item)
        orbit_id = (item.get("orbit_id")
                    or existing.get("orbit_id")
                    or _new_orbit_id())
        item["_orbit_id"] = orbit_id
        should_sync = item.get("status", "pending") == "pending" or item.get(temp_key)
        if not should_sync:
            item.pop(temp_key, None)
            item.pop("_orbit_id", None)
            continue

        try:
            new_id = sync_fn(item)
        except Exception as exc:
            print(f"  ⚠️  [{project_name}] Error sincronizando {label} "
                  f"'{item.get('desc', '?')}': {exc}")
            item.pop(temp_key, None)
            item.pop("_orbit_id", None)
            skipped += 1
            continue

        old_id = item.get(temp_key)
        # sync_fn may have recovered an older orbit-id from the body of a
        # matched item — persist whatever ended up in item["_orbit_id"].
        final_orbit_id = item.get("_orbit_id") or orbit_id
        # Persist orbit-id back into the agenda item so _write_agenda
        # embeds it as [orbit:xxx] in the markdown line.
        item["orbit_id"] = final_orbit_id
        if new_id and new_id != old_id:
            ids.setdefault(key, {})[id_key] = new_id
            ids[key]["orbit_id"] = final_orbit_id
            ids[key]["snapshot"] = _make_snapshot(item)
            if _purge_orbit_orphans(ids, key, final_orbit_id):
                ids_changed = True
            created += 1
            changed = True
            ids_changed = True
        elif old_id:
            ids.setdefault(key, {})["orbit_id"] = final_orbit_id
            ids[key]["snapshot"] = _make_snapshot(item)
            if _purge_orbit_orphans(ids, key, final_orbit_id):
                ids_changed = True
            updated += 1
            # Markdown line gains [orbit:xxx] on first sync — count as changed.
            changed = True
            ids_changed = True
        else:
            skipped += 1
        item.pop(temp_key, None)
        item.pop("_orbit_id", None)

    return created, updated, skipped, changed, ids_changed


def _sync_tasks_for_project(tasks_service, project_dir: Path,
                            config: dict, dry_run: bool) -> tuple:
    """Sync tasks and/or milestones for a project. Returns (created, updated, skipped).

    Respects sync_tasks and sync_milestones config flags independently.
    """
    do_tasks = _sync_tasks_enabled(config)
    do_milestones = _sync_milestones_enabled(config)
    if not do_tasks and not do_milestones:
        return 0, 0, 0

    tipo = _get_project_tipo(project_dir)
    if not tipo:
        return 0, 0, 0

    agenda_path = resolve_file(project_dir, "agenda")
    data = _read_agenda(agenda_path)
    project_name = project_dir.name
    description = _project_description(project_dir, config)

    tasklist_id = _ensure_task_list(tasks_service, tipo, config)
    if not tasklist_id:
        return 0, 0, 0

    ids = _load_ids(project_dir)
    _migrate_recurring_keys(data["tasks"] + data["milestones"], ids)

    seen_recur_keys = set()
    total_created = total_updated = total_skipped = 0
    any_changed = False
    any_ids_changed = False

    sync_pairs = []
    if do_tasks:
        sync_pairs.append((data["tasks"], False, "tarea"))
    if do_milestones:
        sync_pairs.append((data["milestones"], True, "hito"))

    for items, is_milestone, label in sync_pairs:
        sync_fn = lambda item, _ms=is_milestone: _sync_one_task(
            tasks_service, tasklist_id, item,
            project_name, _ms, description, dry_run)
        c, u, s, changed, ids_changed = _sync_item_loop(
            items, sync_fn, "gtask_id", label,
            project_name, ids, seen_recur_keys, dry_run)
        total_created += c
        total_updated += u
        total_skipped += s
        any_changed = any_changed or changed
        any_ids_changed = any_ids_changed or ids_changed

    if any_changed and not dry_run:
        _write_agenda(agenda_path, data)
    if any_ids_changed and not dry_run:
        _save_ids(project_dir, ids)

    return total_created, total_updated, total_skipped


# ── RRULE mapping ──────────────────────────────────────────────────────────

import re as _re

_RRULE_WEEKDAY = {
    "monday": "MO", "tuesday": "TU", "wednesday": "WE", "thursday": "TH",
    "friday": "FR", "saturday": "SA", "sunday": "SU",
    "lunes": "MO", "martes": "TU", "miercoles": "WE", "jueves": "TH",
    "viernes": "FR", "sabado": "SA", "domingo": "SU",
}

_RRULE_EVERY_RE = _re.compile(r"^every-(\d+)-(day|week|month)s?$")
_RRULE_POS_RE = _re.compile(r"^(first|last)-(\w+)$")


def _recur_to_rrule(recur: str, until: str = None) -> list:
    """Convert orbit recurrence pattern to Google Calendar RRULE list."""
    rule = None
    if recur == "daily":
        rule = "RRULE:FREQ=DAILY"
    elif recur == "weekly":
        rule = "RRULE:FREQ=WEEKLY"
    elif recur == "monthly":
        rule = "RRULE:FREQ=MONTHLY"
    elif recur == "weekdays":
        rule = "RRULE:FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR"
    else:
        em = _RRULE_EVERY_RE.match(recur)
        if em:
            n = int(em.group(1))
            unit = em.group(2).upper()
            freq = {"DAY": "DAILY", "WEEK": "WEEKLY", "MONTH": "MONTHLY"}[unit]
            rule = f"RRULE:FREQ={freq};INTERVAL={n}"
        else:
            pm = _RRULE_POS_RE.match(recur)
            if pm:
                pos = 1 if pm.group(1) == "first" else -1
                wd = _RRULE_WEEKDAY.get(pm.group(2))
                if wd:
                    rule = f"RRULE:FREQ=MONTHLY;BYDAY={pos}{wd}"
    if not rule:
        return []
    if until:
        rule += f";UNTIL={until.replace('-', '')}T235959Z"
    return [rule]


# ── Agenda backend: tasks/ms/reminders as 0-min events in Calendar.app ─────
#
# When `reminders_backend == "calendar"`, every task/milestone/reminder is
# rendered as a 0-min event in the per-workspace agenda calendar (e.g.
# 🚀orbit-ws-rem). The display alarm fires at start via CalendarAgent —
# Calendar.app does not need to be open. Recurrence is NOT translated to
# RRULE: orbit advances series locally on `task done`/`drop`, and the next
# occurrence syncs as a new event.

# Per-session memo of agenda calendars we've already warned about, so the
# user sees the missing-calendar message at most once per shell session.
_agenda_calendar_warned: set = set()


def _ensure_agenda_calendar(name: str) -> bool:
    """Return True if the calendar exists in Calendar.app. Print one-time
    setup instructions otherwise. We do NOT auto-create the calendar:
    Calendar.app's AppleScript can only create local calendars, and the
    user wants this calendar to live in their Google account so it shows
    up on mobile.
    """
    if not name:
        return False
    if name in _list_calendar_app_calendars():
        return True
    if name not in _agenda_calendar_warned:
        _agenda_calendar_warned.add(name)
        print(f"⚠️  Calendar \"{name}\" no existe en Calendar.app.")
        print(f"   Crea uno con ese nombre exacto en Google Calendar")
        print(f"   (calendar.google.com → +Otros calendarios → Crear) y espera")
        print(f"   a que sincronice. O cambia 'agenda_calendar' en")
        print(f"   calendar-sync.json a un calendario que ya tengas.")
    return False


def _agenda_storage_key(item: dict, kind: str) -> str:
    """Storage key in .gsync-ids.json for a task/ms/rem under the calendar
    backend. Prefixed with kind so it doesn't collide with an event that
    happens to share desc+date inside the same project.
    """
    return f"{kind}::{_item_key(item)}"


def _agenda_props_for_calendar_app(item: dict, project_name: str,
                                    base_description: str, kind: str) -> dict:
    """Build property dict for an agenda item rendered as a 0-min event.

    Title carries the kind emoji (✅🏁💬) so users can scan the calendar at
    a glance even though all three kinds share the same calendar.
    """
    from datetime import datetime

    emoji   = _REMINDER_KIND_EMOJI.get(kind, "")
    summary = f"[{project_name}] {emoji} {item['desc']}".rstrip()

    start_date = item["date"]
    time_val   = item.get("time")
    raw_start  = (time_val.split("-")[0] if time_val and "-" in time_val
                  else time_val)
    start_time = raw_start or "09:00"
    start_iso  = f"{start_date}T{start_time}"
    end_iso    = start_iso  # 0-min event: discrete marker, doesn't block slots

    # Alarm: fire at start by default. If the item has --ring, honour it
    # (alarm earlier — same semantics as for events).
    alarm_minutes = 0
    ring_val = item.get("ring")
    if ring_val:
        from core.ring import resolve_ring_datetime
        ring_dt = resolve_ring_datetime(start_date, ring_val, due_time=start_time)
        if ring_dt is not None:
            try:
                start_dt = datetime.fromisoformat(f"{start_date}T{start_time}:00")
                delta_min = int((start_dt - ring_dt).total_seconds() / 60)
                alarm_minutes = max(delta_min, 0)
            except ValueError:
                pass

    description = _item_description(item, base_description, html=False)
    orbit_id = item.get("_orbit_id")
    if orbit_id:
        description = _append_orbit_tag(description, _build_orbit_tag(orbit_id))

    return {
        "summary":       summary,
        "start_iso":     start_iso,
        "end_iso":       end_iso,
        "description":   description,
        "url":           "",
        # No RRULE: orbit advances recurring tasks/ms/rem locally on
        # `done`/`drop`. Each occurrence is a single event.
        "rrule":         "",
        "alarm_minutes": alarm_minutes,
    }


def _sync_one_agenda_event(calendar_name: str, item: dict,
                            project_name: str, description: str,
                            kind: str, dry_run: bool = False) -> Optional[str]:
    """Sync a task/ms/rem as a 0-min event. Same resolution order as
    :func:`_sync_one_event`: orbit-id → stored uid → title+date → create.
    """
    props    = _agenda_props_for_calendar_app(item, project_name, description, kind)
    summary  = props["summary"]
    orbit_id = item.get("_orbit_id")
    uid      = item.get("_gcal_id")

    if dry_run:
        action = "actualizar" if uid else "crear"
        emoji  = _REMINDER_KIND_EMOJI.get(kind, "")
        print(f"  ~ {action}: {emoji} {item['date']} — {summary}")
        return uid

    if orbit_id:
        found_uid = _find_calendar_event_by_orbit_id(calendar_name, orbit_id)
        if found_uid:
            _update_calendar_event(found_uid, calendar_name, props)
            return found_uid

    if uid and _update_calendar_event(uid, calendar_name, props):
        return uid

    matched_uid = _find_calendar_event_by_title_date(
        calendar_name, summary, props["start_iso"])
    if matched_uid:
        existing_desc = _read_event_description(matched_uid, calendar_name)
        recovered_id, _ = _parse_orbit_tag(existing_desc)
        if recovered_id and recovered_id != orbit_id:
            item["_orbit_id"] = recovered_id
            props = _agenda_props_for_calendar_app(item, project_name,
                                                    description, kind)
        _update_calendar_event(matched_uid, calendar_name, props)
        return matched_uid

    new_uid = _create_calendar_event(calendar_name, props)
    if not new_uid:
        print(f"  ⚠️  Error creando agenda event '{summary}' en \"{calendar_name}\"")
    return new_uid


# ── Event sync (Calendar.app via AppleScript) ──────────────────────────────

def _alarm_minutes_for_event(start_iso: str, ring: str,
                             due_time: Optional[str]) -> Optional[int]:
    """Minutes before the event's start when the alarm should fire.

    Positive means "N minutes before" (Calendar.app trigger interval = -N).
    Returns None if ring can't be resolved or fires after the event start.
    """
    from datetime import datetime
    from core.ring import resolve_ring_datetime

    date_part = start_iso.split("T", 1)[0]
    ring_dt = resolve_ring_datetime(date_part, ring, due_time=due_time)
    if ring_dt is None:
        return None
    try:
        start_dt = datetime.fromisoformat(start_iso)
    except ValueError:
        return None
    delta = start_dt - ring_dt
    minutes = int(delta.total_seconds() / 60)
    return minutes if minutes >= 0 else 0


def _ev_props_for_calendar_app(ev: dict, project_name: str,
                               base_description: str) -> dict:
    """Build the property dict consumed by _create/_update_calendar_event."""
    from datetime import timedelta, datetime

    # Workspace prefix dropped: the Calendar.app calendar (🚀orbit-ws /
    # 🌿orbit-ps) already encodes workspace via its color/name.
    summary = f"[{project_name}] {ev['desc']}"
    start_date = ev["date"]
    time_val = ev.get("time")

    if time_val:
        parts = time_val.split("-")
        start_time = parts[0]
        start_iso = f"{start_date}T{start_time}"
        if len(parts) == 2:
            end_iso = f"{ev.get('end') or start_date}T{parts[1]}"
        else:
            dt = datetime.fromisoformat(f"{start_date}T{start_time}:00")
            end_dt = dt + timedelta(hours=1)
            end_iso = end_dt.strftime("%Y-%m-%dT%H:%M")
    else:
        # All-day: AppleScript needs explicit start/end dates; use 00:00→23:59
        start_iso = f"{start_date}T00:00"
        end_d = ev.get("end") or start_date
        end_iso = f"{end_d}T23:59"

    rrule_list = _recur_to_rrule(ev["recur"], ev.get("until")) if ev.get("recur") else []
    # gsync's _recur_to_rrule returns ['RRULE:...'] — strip the prefix for AppleScript
    rrule = rrule_list[0].removeprefix("RRULE:") if rrule_list else ""

    # Pull a clickable URL out of the event notes (📋/🚪 prefixes) into the
    # event's `url` property — Calendar.app shows a video-camera button.
    # Plain-text rooms (e.g. "Aula A1-01") stay in the notes only.
    from core.agenda_cmds import event_room_urls, event_agenda_urls, _is_meeting_url
    rooms = event_room_urls(ev)
    agendas = event_agenda_urls(ev)
    candidates = [u for u in rooms + agendas if _is_meeting_url(u)]
    url = candidates[0] if candidates else ""

    # Translate orbit's --ring into a Calendar.app display alarm.
    alarm_minutes = None
    if ev.get("ring"):
        ev_time = ev.get("time") or ""
        due_time = ev_time.split("-")[0] if ev_time else None
        alarm_minutes = _alarm_minutes_for_event(start_iso, ev["ring"], due_time)

    # Build description (notes + project link) and embed orbit-id tag.
    description = _item_description(ev, base_description, html=False)
    orbit_id = ev.get("_orbit_id")
    if orbit_id:
        description = _append_orbit_tag(description, _build_orbit_tag(orbit_id))

    return {
        "summary":       summary,
        "start_iso":     start_iso,
        "end_iso":       end_iso,
        "description":   description,
        "url":           url,
        "rrule":         rrule,
        "alarm_minutes": alarm_minutes,
    }


def _sync_one_event(calendar_name: str, ev: dict,
                    project_name: str, description: str,
                    dry_run: bool) -> Optional[str]:
    """Sync one event to Calendar.app. Returns the AppleScript-side uid.

    Resolution order (most reliable → most fragile):
      1. Match-by-orbit-id (tag in description) — survives rename, dedup-proof
      2. Stored uid → update in place
      3. Match-by-title-date (legacy fallback for events synced before orbit-ids)
      4. Create new

    A failed _update on a found event does NOT fall through to _create —
    returning the matched uid avoids duplicates if the update timed out.
    """
    props = _ev_props_for_calendar_app(ev, project_name, description)
    summary = props["summary"]
    orbit_id = ev.get("_orbit_id")
    uid = ev.get("_gcal_id")

    if dry_run:
        print(f"  ~ {('actualizar' if uid else 'crear')}: 📅 {ev['date']} — {summary}")
        return uid

    # 1. Match-by-orbit-id (most reliable).
    if orbit_id:
        found_uid = _find_calendar_event_by_orbit_id(calendar_name, orbit_id)
        if found_uid:
            _update_calendar_event(found_uid, calendar_name, props)
            return found_uid

    # 2. Try the stored uid directly.
    if uid:
        if _update_calendar_event(uid, calendar_name, props):
            return uid
        print(f"  ⚠️  Evento uid={uid[:8]}… stale; busco por título+fecha")

    # 3. Legacy match-by-title-date (for events created before orbit-ids,
    #    or when our key changed and lost the reference).
    matched_uid = _find_calendar_event_by_title_date(
        calendar_name, summary, props["start_iso"])
    if matched_uid:
        existing_desc = _read_event_description(matched_uid, calendar_name)
        recovered_id, _ = _parse_orbit_tag(existing_desc)
        if recovered_id and recovered_id != orbit_id:
            ev["_orbit_id"] = recovered_id
            props = _ev_props_for_calendar_app(ev, project_name, description)
            print(f"  ↺ reasocio evento y recupero orbit-id={recovered_id} ({summary})")
        else:
            print(f"  ↺ asocio existente uid={matched_uid[:8]}… ({summary})")
        _update_calendar_event(matched_uid, calendar_name, props)
        return matched_uid

    # 4. Create new.
    new_uid = _create_calendar_event(calendar_name, props)
    if not new_uid:
        print(f"  ⚠️  Error creando evento '{summary}' en \"{calendar_name}\"")
    return new_uid


def _sync_events_for_project(project_dir: Path, config: dict,
                             dry_run: bool) -> tuple:
    """Sync all events for a project to Calendar.app.

    Returns (created, updated, skipped).
    """
    tipo = _get_project_tipo(project_dir)
    calendar_name = config.get("calendars", {}).get(tipo)
    if not calendar_name:
        calendar_name = config.get("calendars", {}).get("default")
    if not calendar_name:
        return 0, 0, 0

    agenda_path = resolve_file(project_dir, "agenda")
    data = _read_agenda(agenda_path)
    project_name = project_dir.name
    description = _project_description(project_dir, config, html=False)

    ids = _load_ids(project_dir)
    _migrate_recurring_keys(data["events"], ids)

    seen_recur_keys = set()
    sync_fn = lambda ev: _sync_one_event(
        calendar_name, ev, project_name, description, dry_run)
    created, updated, skipped, changed, ids_changed = _sync_item_loop(
        data["events"], sync_fn, "gcal_id", "evento",
        project_name, ids, seen_recur_keys, dry_run)

    if changed and not dry_run:
        _write_agenda(agenda_path, data)
    if ids_changed and not dry_run:
        _save_ids(project_dir, ids)

    return created, updated, skipped


# ── List calendars ──────────────────────────────────────────────────────────

def run_gsync_migrate_recurring(dry_run: bool = False) -> int:
    """One-time legacy migration that needed Google Calendar API.

    No-op now that events flow through Calendar.app. Kept for argparse
    compatibility; returns 0 immediately.
    """
    print("ℹ️  Esta migración aplicaba a la antigua sincronización con Google "
          "Calendar API. Con Calendar.app no se necesita; ignorada.")
    return 0


def run_gsync_migrate_rem_to_calendar(dry_run: bool = False) -> int:
    """Migrate tasks/milestones/reminders from Reminders.app to the agenda
    calendar in Calendar.app. After a successful run, flips
    ``reminders_backend`` to ``"calendar"`` in calendar-sync.json.

    Idempotent: matches existing items by orbit-id, so re-running does not
    create duplicates. Pending items only — done/cancelled stay where they
    are (Reminders.app legacy items will simply be removed in batch).
    """
    config    = _load_config()
    cal_name  = _agenda_calendar_name(config)
    list_name = _reminders_list_name(config)

    if not _calendar_app_running():
        print("⚠️  Calendar.app no está corriendo. Lánzala antes de migrar.")
        return 1
    if not dry_run and not _ensure_agenda_calendar(cal_name):
        return 1

    rem_running = _reminders_app_running() if not dry_run else False
    if not dry_run and not rem_running:
        print("ℹ️  Reminders.app no está corriendo; subo a Calendar pero no")
        print("    borraré los items legacy. Lanza Reminders y reejecuta para limpiar.")

    print(f"🔄 Migrando tasks/ms/reminders → calendario \"{cal_name}\""
          + (" [dry-run]" if dry_run else ""))

    total_items    = 0
    total_uploaded = 0
    total_deleted  = 0

    for project_dir in iter_project_dirs():
        if not _is_new_project(project_dir):
            continue
        agenda_path = resolve_file(project_dir, "agenda")
        if not agenda_path.exists():
            continue
        data = _read_agenda(agenda_path)
        ids  = _load_ids(project_dir)

        candidates = []
        for t in data.get("tasks", []):
            if t.get("status") == "pending" and t.get("date"):
                candidates.append((t, "task"))
        for m in data.get("milestones", []):
            if m.get("status") == "pending" and m.get("date"):
                candidates.append((m, "milestone"))
        for r in data.get("reminders", []):
            if not r.get("cancelled") and r.get("date"):
                candidates.append((r, "reminder"))

        if not candidates:
            continue

        project_name = project_dir.name
        description  = _project_description(project_dir, config, html=False)
        print(f"\n[{project_name}] {len(candidates)} item(s)")

        ids_changed = False
        agenda_changed = False
        for item, kind in candidates:
            total_items += 1
            old_key = _item_key(item)
            new_key = _agenda_storage_key(item, kind)
            existing_old = ids.get(old_key, {}) or {}
            existing_new = ids.get(new_key, {}) or {}

            orbit_id = (item.get("orbit_id")
                        or existing_new.get("orbit_id")
                        or existing_old.get("orbit_id")
                        or _new_orbit_id())
            item["_orbit_id"] = orbit_id
            item["_gcal_id"]  = existing_new.get("gcal_id")

            new_uid = _sync_one_agenda_event(cal_name, item, project_name,
                                              description, kind, dry_run=dry_run)
            if dry_run:
                # No AppleScript ran; count would-upload so the summary
                # reflects what the real run will do.
                total_uploaded += 1
            elif new_uid:
                total_uploaded += 1
                ids.setdefault(new_key, {})["gcal_id"] = new_uid
                ids[new_key]["orbit_id"] = orbit_id
                ids[new_key]["snapshot"] = _make_snapshot(item)
                ids_changed = True
                if item.get("orbit_id") != orbit_id:
                    item["orbit_id"] = orbit_id
                    agenda_changed = True

            # Delete from Reminders.app — by orbit-id first (survives renames),
            # then by stored gtask_id as a fallback.
            if not dry_run and rem_running:
                deleted = False
                if orbit_id:
                    found_uid = _find_reminder_by_orbit_id(list_name, orbit_id)
                    if found_uid and _delete_reminder_item(found_uid, list_name):
                        deleted = True
                old_gtask = existing_old.get("gtask_id")
                if not deleted and old_gtask:
                    if _delete_reminder_item(old_gtask, list_name):
                        deleted = True
                if deleted:
                    total_deleted += 1
                # Drop the legacy ids entry whether or not deletion succeeded —
                # it points at a defunct gtask_id and would only confuse later
                # syncs. Calendar entry is the new source of truth.
                if old_key in ids and old_key != new_key:
                    ids.pop(old_key, None)
                    ids_changed = True

            item.pop("_orbit_id", None)
            item.pop("_gcal_id", None)

        if not dry_run:
            if ids_changed:
                _save_ids(project_dir, ids)
            if agenda_changed:
                _write_agenda(agenda_path, data)

    print()
    print(f"✓ {total_uploaded}/{total_items} items en calendario \"{cal_name}\"")
    print(f"  {total_deleted}/{total_items} items borrados de Reminders.app")
    if dry_run:
        print("  (dry-run: ningún cambio escrito)")
        return 0

    if config.get("reminders_backend") != "calendar":
        config["reminders_backend"] = "calendar"
        _save_config(config)
        print("  ↻ reminders_backend → \"calendar\" en calendar-sync.json")
    return 0
    # ── unreachable: original Google-API body retained below for reference ──
    config = _load_config()
    cal_service = _get_calendar_service()
    if not cal_service:
        print("⚠️  No se pudo conectar con Google Calendar.")
        return 1

    dirs = [d for d in iter_project_dirs() if _is_new_project(d)]
    total = 0

    for project_dir in dirs:
        ids = _load_ids(project_dir)
        if not ids:
            continue

        agenda_path = resolve_file(project_dir, "agenda")
        data = _read_agenda(agenda_path)
        ids_changed = False

        for ev in data["events"]:
            if not ev.get("recur"):
                continue
            key = _item_key(ev)
            entry = ids.get(key, {})
            gcal_id = entry.get("gcal_id")
            if not gcal_id:
                continue

            # Mark old event in Google Calendar
            label = f"[{project_dir.name}] {ev['desc']}"
            if dry_run:
                print(f"  ~ marcar: ⚠️ ANTIGUO: {label}")
            else:
                try:
                    existing = cal_service.events().get(
                        calendarId=_get_calendar_id(config, project_dir),
                        eventId=gcal_id
                    ).execute()
                    existing["summary"] = f"⚠️ ANTIGUO: {existing.get('summary', label)}"
                    cal_service.events().update(
                        calendarId=_get_calendar_id(config, project_dir),
                        eventId=gcal_id, body=existing
                    ).execute()
                    print(f"  ⚠️ Marcado: {label}")
                except Exception as e:
                    print(f"  ⚠️ Error marcando '{label}': {e}")

            # Clear gcal_id so gsync creates a new RRULE series
            entry.pop("gcal_id", None)
            entry.pop("snapshot", None)
            ev.pop("orbit_id", None)
            ids_changed = True
            total += 1

        if ids_changed and not dry_run:
            _save_ids(project_dir, ids)
            _write_agenda(agenda_path, data)

    label = "  [dry-run]" if dry_run else ""
    print(f"\n{total} evento{'s' if total != 1 else ''} recurrente{'s' if total != 1 else ''} migrado{'s' if total != 1 else ''}.{label}")
    if total and not dry_run:
        print("Ejecuta `orbit gsync` para crear las nuevas series RRULE.")
    return 0


def _get_calendar_id(config: dict, project_dir) -> str:
    """Get the calendar ID for a project."""
    tipo = _get_project_tipo(project_dir)
    cal_id = config.get("calendars", {}).get(tipo)
    if not cal_id:
        cal_id = config.get("calendars", {}).get("default")
    return cal_id


def check_gsync_drift() -> list:
    """Check all synced items for drift (changes since last gsync).

    Returns list of (project_name, item_desc, diffs) tuples.
    """
    config = _load_config()
    do_tasks = _sync_tasks_enabled(config)
    do_milestones = _sync_milestones_enabled(config)
    results = []
    dirs = [d for d in iter_project_dirs() if _is_new_project(d)]
    for project_dir in dirs:
        ids = _load_ids(project_dir)
        if not ids:
            continue
        agenda_path = resolve_file(project_dir, "agenda")
        data = _read_agenda(agenda_path)
        all_items = [(e, "evento") for e in data["events"]]
        if do_tasks:
            all_items = [(t, "tarea") for t in data["tasks"]] + all_items
        if do_milestones:
            all_items = [(m, "hito") for m in data["milestones"]] + all_items
        for item, kind in all_items:
            key = _item_key(item)
            saved = ids.get(key, {}).get("snapshot")
            if not saved:
                continue
            diffs = _diff_snapshot(item, saved)
            if diffs:
                results.append((project_dir.name, kind, item.get("desc", "?"), diffs))
    return results


def _secondary_key(item: dict) -> str:
    """Build a secondary key (without desc) for matching renames.

    Uses date (non-recurring) or recur+date pattern (recurring) to identify
    the same item even when its title has changed. Including the anchor date
    for recurring items lets us distinguish between multiple series sharing
    the same recur pattern.
    """
    if item.get("recur"):
        return f"🔄{item['recur']}::{item.get('date', '')}"
    return item.get("date", "")


def _canonical_storage_key(item: dict, kind: str) -> str:
    """Return the key an entry SHOULD live under given the item and its kind.

    Tasks / milestones / reminders use the kind-prefixed form
    introduced by the v0.29 calendar backend. Events still use the
    legacy ``_item_key`` form because their batch sync path
    (``_sync_events_for_project``) was never migrated.
    """
    if kind in ("task", "milestone", "reminder"):
        return _agenda_storage_key(item, kind)
    return _item_key(item)


def reconcile_gsync_renames() -> list:
    """Detect items whose title/date/recur changed in the markdown and
    re-link their gsync IDs.

    Strategy: every item with an ``[orbit:xxx]`` tag in the .md carries its
    identity. If its canonical key (see :func:`_canonical_storage_key`)
    differs from the key under which it is stored in `.gsync-ids.json`, the
    user must have edited title/date/recur (or the entry is in the legacy
    pre-v0.29 ``_item_key`` form). We migrate the stored uid+orbit_id to
    the canonical key, update the snapshot and re-sync to propagate.

    Falls back to the legacy secondary-key heuristic for items without an
    orbit-id (pre-tag agendas).

    Returns list of (project_name, old_desc, new_desc) for each rename.
    """
    config = _load_config()
    do_tasks = _sync_tasks_enabled(config)
    do_milestones = _sync_milestones_enabled(config)
    results = []
    dirs = [d for d in iter_project_dirs() if _is_new_project(d)]
    for project_dir in dirs:
        ids = _load_ids(project_dir)
        if not ids:
            continue
        agenda_path = resolve_file(project_dir, "agenda")
        data = _read_agenda(agenda_path)
        all_items = [(e, "event") for e in data["events"]]
        if do_tasks:
            all_items = [(t, "task") for t in data["tasks"]] + all_items
        if do_milestones:
            all_items = [(m, "milestone") for m in data["milestones"]] + all_items

        # Map every item to its canonical key. The set is used as the
        # "currently-in-use" key set so pass 2's orphan detection doesn't
        # flag a legitimate prefixed entry as an orphan.
        current_keys = {_canonical_storage_key(it, kind): (it, kind)
                        for it, kind in all_items}
        # Reverse index: orbit_id → key in .gsync-ids.json (only the
        # top-level item entries; cronograma `_cronos` sub-dict is excluded).
        ids_by_orbit = {v.get("orbit_id"): k
                        for k, v in ids.items()
                        if isinstance(v, dict) and v.get("orbit_id")}

        changed = False

        # Pass 1 — orbit-id authoritative. For each item carrying an
        # orbit-id, locate its stored key. If different from canonical,
        # that's a rename (or date/recur change, or a pre-v0.29 entry
        # that pre-dates the kind:: prefix) — migrate.
        #
        # We do NOT push to the backend here: every CLI edit already
        # ran sync_item, and editing the .md by hand is rare enough
        # that ad-hoc `orbit gsync` is the right place to recover.
        # Calling sync_item from inside commit was double work and
        # made commit feel slow when reorganize had just run.
        for item, kind in all_items:
            oid = item.get("orbit_id")
            if not oid:
                continue
            stored_key = ids_by_orbit.get(oid)
            if not stored_key:
                continue
            canonical = _canonical_storage_key(item, kind)
            if stored_key == canonical:
                continue
            # Extract the "old desc" for reporting. If the stored key has
            # a kind:: prefix, strip it so the user sees the same desc the
            # markdown line shows.
            naked = stored_key
            for k in ("task::", "milestone::", "reminder::"):
                if naked.startswith(k):
                    naked = naked[len(k):]
                    break
            old_desc = naked.split("::", 1)[0]
            ids[canonical] = ids.pop(stored_key)
            ids[canonical]["snapshot"] = _make_snapshot(item)
            ids_by_orbit[oid] = canonical
            results.append((project_dir.name, old_desc, item.get("desc", "?")))
            changed = True

        # Pass 2 — legacy fallback for items without orbit-id. Uses the
        # old secondary-key match (date or recur+date) against orphan ids.
        orphans = {k: v for k, v in ids.items()
                   if k not in current_keys and not k.startswith("_")}
        if orphans:
            for item, kind in all_items:
                if item.get("orbit_id"):
                    continue  # handled in pass 1
                key = _item_key(item)
                if key in ids:
                    continue
                sec = _secondary_key(item)
                if not sec:
                    continue
                for okey in list(orphans.keys()):
                    osec = okey.split("::", 1)[1] if "::" in okey else ""
                    if sec == osec:
                        old_desc = okey.split("::")[0]
                        ids[key] = ids.pop(okey)
                        ids[key]["snapshot"] = _make_snapshot(item)
                        orphans.pop(okey)
                        results.append((project_dir.name, old_desc, item.get("desc", "?")))
                        changed = True
                        break

        if changed:
            _save_ids(project_dir, ids)

    return results


def run_list_calendars() -> int:
    """List calendars available in Calendar.app."""
    if not _calendar_app_running():
        print("⚠️  Calendar.app no está corriendo. Ábrela y reintenta.")
        return 1
    cals = _list_calendar_app_calendars()
    if not cals:
        print("⚠️  No se encontraron calendarios en Calendar.app.")
        return 1
    print("Calendarios disponibles en Calendar.app:")
    print("─" * 60)
    for name in cals:
        print(f"  {name}")
    print("─" * 60)
    print(f"\nUsa el nombre tal cual aparece arriba en {CONFIG_PATH}:")
    print('  "calendars": {')
    print('    "investigacion": "🌀 Investigacion",')
    print('    "default": "🌿 orbit-ps"')
    print('  }')
    return 0


# ── Main entry point ────────────────────────────────────────────────────────

def run_gsync(dry_run: bool = False, list_calendars: bool = False,
              project: Optional[str] = None) -> int:
    """Push Orbit events to Calendar.app and tasks/ms/reminders to Reminders.app.

    project: if given, sync only that one project (substring match accepted).
    """
    if list_calendars:
        return run_list_calendars()

    config = _load_config()

    has_calendars = any(v for v in config.get("calendars", {}).values())
    cal_app_ok = _calendar_app_running() if has_calendars else False
    if has_calendars and not cal_app_ok:
        print("⚠️  Calendar.app no está corriendo — los eventos no se sincronizan.")
        print("   Abre Calendar.app y vuelve a ejecutar.")

    if not has_calendars:
        print(f"⚠️  No hay calendarios configurados en {CONFIG_PATH}")
        print(f"   Ejecuta: orbit gsync --list-calendars  (lista Calendar.app)")
        print(f"   Y edita {CONFIG_PATH} con los nombres de tus calendarios.\n")

    do_reminders = (_sync_tasks_enabled(config) or _sync_milestones_enabled(config))
    rem_app_ok = _reminders_app_running() if do_reminders else False
    if do_reminders and not rem_app_ok:
        print("⚠️  Reminders.app no está corriendo — tareas/hitos/recordatorios no se sincronizan.")

    if not (rem_app_ok or (has_calendars and cal_app_ok)):
        print("⚠️  Nada que sincronizar (ni Calendar.app ni Reminders.app disponibles)")
        return 1

    if project:
        project_dir = _find_new_project(project)
        if not project_dir:
            print(f"⚠️  Proyecto no encontrado: {project!r}")
            return 1
        dirs = [project_dir]
        scope = f" — solo {project_dir.name}"
    else:
        dirs = [d for d in iter_project_dirs() if _is_new_project(d)]
        scope = ""

    label = "  [dry-run]" if dry_run else ""
    print(f"Sincronizando Orbit → Calendar.app + Reminders.app{scope}{label}")
    print("─" * 50)

    total_created = total_updated = total_skipped = 0
    events_created = events_updated = events_skipped = 0
    no_calendar_tipos = set()

    for project_dir in dirs:
        tipo = _get_project_tipo(project_dir)

        # Tasks + milestones + reminders → Reminders.app (legacy backend)
        if rem_app_ok:
            c, u, s = _sync_to_reminders_for_project(project_dir, config, dry_run)
            if c or u:
                print(f"  [{project_dir.name}] tareas/hitos/recordatorios: {c} nuevos, {u} actualizados")
            total_created += c
            total_updated += u
            total_skipped += s

        # Cronogramas: 1 event/reminder per cronograma tracking its next open
        # leaf. The function picks Calendar vs Reminders internally based on
        # `reminders_backend` in calendar-sync.json.
        if (rem_app_ok or (has_calendars and cal_app_ok)):
            cc, cu, cs = _sync_cronos_for_project(project_dir, config, dry_run)
            if cc or cu:
                print(f"  [{project_dir.name}] cronogramas: {cc} nuevos, {cu} actualizados")
            total_created += cc
            total_updated += cu
            total_skipped += cs

        # Events → Calendar.app
        if has_calendars and cal_app_ok:
            calendar_name = config.get("calendars", {}).get(tipo)
            if not calendar_name:
                calendar_name = config.get("calendars", {}).get("default")
            if not calendar_name:
                agenda_path = resolve_file(project_dir, "agenda")
                data = _read_agenda(agenda_path)
                if data["events"]:
                    no_calendar_tipos.add(tipo or project_dir.name)
            else:
                c, u, s = _sync_events_for_project(project_dir, config, dry_run)
                if c or u:
                    print(f"  [{project_dir.name}] eventos: {c} nuevos, {u} actualizados")
                events_created += c
                events_updated += u
                events_skipped += s

    print("─" * 50)

    parts = []
    tc = total_created + events_created
    tu = total_updated + events_updated
    if tc:
        parts.append(f"{tc} creados")
    if tu:
        parts.append(f"{tu} actualizados")
    if not tc and not tu:
        parts.append("Todo sincronizado")
    print("  ".join(parts))

    if no_calendar_tipos:
        tipos_str = ", ".join(sorted(no_calendar_tipos))
        print(f"\n⚠️  Eventos sin calendario configurado para: {tipos_str}")
        print(f"   Edita {CONFIG_PATH} para asignar calendarios.")

    return 0


# ── Helpers for hooks ──────────────────────────────────────────────────────

def _is_gsync_configured() -> bool:
    """True if calendar-sync.json declares either calendars or a reminders list.

    An empty placeholder (``{"calendars": {}, "task_lists": {}}``) does NOT
    count as configured — it would otherwise wake up AppleScript on every
    operation, even in test environments that just create the file.
    """
    if not CONFIG_PATH.exists():
        return False
    try:
        cfg = json.loads(CONFIG_PATH.read_text())
    except (OSError, json.JSONDecodeError):
        return False
    if any(cfg.get("calendars", {}).values()):
        return True
    if cfg.get("reminders_list"):
        return True
    return False


# ── Delete from Google ──────────────────────────────────────────────────────

def delete_gcal_event(project_dir: Path, ev: dict) -> None:
    """Delete a Google Calendar event. Fails silently."""
    if not _is_gsync_configured():
        return

    ids = _load_ids(project_dir)
    key = _item_key(ev)
    gcal_id = ids.get(key, {}).get("gcal_id")
    if not gcal_id:
        return

    import threading

    def _do_delete():
        try:
            config = _load_config()
            tipo = _get_project_tipo(project_dir)
            cal_name = config.get("calendars", {}).get(tipo)
            if not cal_name:
                cal_name = config.get("calendars", {}).get("default")
            if not cal_name:
                return
            if _calendar_app_running():
                _delete_calendar_event(gcal_id, cal_name)
            ids_data = _load_ids(project_dir)
            ids_data.pop(key, None)
            _save_ids(project_dir, ids_data)
        except Exception:
            pass

    t = threading.Thread(target=_do_delete, daemon=True)
    t.start()


# ── Individual item sync (for add/done/edit/drop hooks) ────────────────────

# How long sync_item waits for AppleScript before letting the prompt
# return. The thread keeps running either way; this just bounds how long
# the CLI blocks. AppleScript reads/writes against Reminders.app/
# Calendar.app commonly take 5-15 s when iCloud is busy — those finish in
# the background. 0.15 s is enough to catch fast scripting errors
# (missing list, syntax — typically <50 ms) without being perceptible at
# the prompt.
_SYNC_TIMEOUT = 0.15  # seconds


def _purge_orbit_orphans(ids: dict, current_key: str, orbit_id: str) -> bool:
    """Drop other entries in *ids* that share *orbit_id* but live under a
    stale key. Returns True if anything was removed.

    When a CLI edit changes desc/date/recur, the item's `_item_key` shifts
    to ``current_key`` and the entry is rewritten there. Without this
    cleanup the previous key lingers as a duplicate pointing at the same
    Reminder/Calendar uid, and the next ``commit`` would surface it as a
    fake rename in `reconcile_gsync_renames`.
    """
    if not orbit_id:
        return False
    removed = False
    for k in list(ids.keys()):
        if k == current_key or k.startswith("_"):
            continue
        v = ids[k]
        if isinstance(v, dict) and v.get("orbit_id") == orbit_id:
            del ids[k]
            removed = True
    return removed


def sync_item(project_dir: Path, item: dict, kind: str = "task") -> None:
    """Sync a single task/milestone/event to Google after a local operation.

    kind: "task", "milestone", or "event"
    Runs with a short timeout; fails silently with a warning.
    """
    if not _is_gsync_configured():
        return

    import threading

    def _do_sync():
        try:
            config = _load_config()
            tipo = _get_project_tipo(project_dir)
            ids = _load_ids(project_dir)
            key = _item_key(item)

            if kind in ("task", "milestone", "reminder"):
                if kind == "task" and not _sync_tasks_enabled(config):
                    return
                if kind == "milestone" and not _sync_milestones_enabled(config):
                    return

                # ── Backend = "calendar": render as 0-min event ──────────
                if _agenda_backend(config) == "calendar":
                    # Milestones go to the per-tipo events calendar (same as
                    # events), so they're not buried among tasks/reminders in
                    # the agenda calendar. Tasks and reminders stay in the
                    # workspace's agenda calendar.
                    agenda_cal = _agenda_calendar_name(config)
                    if kind == "milestone":
                        cal_name = (config.get("calendars", {}).get(tipo)
                                    or config.get("calendars", {}).get("default"))
                    else:
                        cal_name = agenda_cal

                    if not cal_name:
                        return
                    if not _calendar_app_running():
                        return
                    # Only enforce the setup-help message for the agenda
                    # calendar; the per-tipo events calendar gets a simpler
                    # error from _sync_one_agenda_event if it's missing.
                    if kind != "milestone" and not _ensure_agenda_calendar(cal_name):
                        return

                    storage_key  = _agenda_storage_key(item, kind)
                    legacy_key   = _item_key(item)

                    # Legacy-key fallback: pre-v0.29 entries (and a handful
                    # of v0.29.0 ones that slipped past the migration) live
                    # under `desc::date` instead of `kind::desc::date`. If
                    # the new key isn't there yet but the legacy one is,
                    # treat that as the existing entry — the next save will
                    # write under the new key and `_purge_orbit_orphans`
                    # removes the legacy entry.
                    existing = ids.get(storage_key, {})
                    if not existing and legacy_key != storage_key:
                        legacy = ids.get(legacy_key, {})
                        if legacy.get("gcal_id"):
                            existing = legacy

                    # Done / cancelled / reminder-cancelled → remove the event.
                    # The calendar should reflect only what's pending;
                    # otherwise it accumulates crossed-out clutter and the
                    # alarms (already-fired) hang around in NotificationCenter.
                    is_terminal = (item.get("status") in ("done", "cancelled")
                                   or (kind == "reminder" and item.get("cancelled")))
                    if is_terminal:
                        existing_uid = existing.get("gcal_id")
                        if existing_uid:
                            _delete_calendar_event(existing_uid, cal_name)
                            # Best-effort cleanup for ms migrated from
                            # pre-v0.29.2 (where ms lived in the agenda
                            # calendar). Safe if the event isn't there.
                            if kind == "milestone" and agenda_cal and agenda_cal != cal_name:
                                _delete_calendar_event(existing_uid, agenda_cal)
                            ids.pop(storage_key, None)
                            if legacy_key != storage_key:
                                ids.pop(legacy_key, None)
                            _save_ids(project_dir, ids)
                        return

                    project_name = project_dir.name
                    description  = _project_description(project_dir, config, html=False)
                    item["_gcal_id"] = existing.get("gcal_id")
                    item["_orbit_id"] = (item.get("orbit_id")
                                         or existing.get("orbit_id")
                                         or _new_orbit_id())
                    new_uid = _sync_one_agenda_event(cal_name, item,
                                                     project_name, description,
                                                     kind, dry_run=False)
                    if new_uid:
                        # Save when anything visible changed (new uid, drifted
                        # snapshot, or different orbit-id) AND when migrating
                        # from a legacy `desc::date` key — in the legacy case
                        # the uid often stays the same but the storage key
                        # still needs to move to `kind::desc::date`.
                        current = ids.get(storage_key, {})
                        snapshot = _make_snapshot(item)
                        if (current.get("gcal_id") != new_uid
                                or current.get("snapshot") != snapshot
                                or current.get("orbit_id") != item.get("_orbit_id")):
                            # Milestone migration cleanup (pre-v0.29.2 routing):
                            # if the previous uid was for the agenda calendar,
                            # remove it so the user doesn't see the ms twice.
                            old_uid = existing.get("gcal_id")
                            if (old_uid and old_uid != new_uid
                                    and kind == "milestone"
                                    and agenda_cal and agenda_cal != cal_name):
                                _delete_calendar_event(old_uid, agenda_cal)
                            ids.setdefault(storage_key, {})["gcal_id"] = new_uid
                            ids[storage_key]["orbit_id"] = item.get("_orbit_id")
                            ids[storage_key]["snapshot"] = snapshot
                            _purge_orbit_orphans(ids, storage_key, item.get("_orbit_id"))
                            _save_ids(project_dir, ids)
                            # Persist orbit-id back into agenda.md.
                            agenda_path = resolve_file(project_dir, "agenda")
                            data = _read_agenda(agenda_path)
                            section = {"task": "tasks", "milestone": "milestones",
                                       "reminder": "reminders"}[kind]
                            for it in data.get(section, []):
                                if (it.get("desc") == item["desc"]
                                        and it.get("date") == item.get("date")):
                                    it["orbit_id"] = item.get("_orbit_id")
                                    break
                            _write_agenda(agenda_path, data)
                    item.pop("_gcal_id", None)
                    return

                # ── Backend = "reminders": legacy Reminders.app path ─────
                if not _reminders_app_running():
                    return
                list_name = _reminders_list_name(config)
                _ensure_reminders_list(list_name)
                project_name = project_dir.name
                existing = ids.get(key, {})
                item["_gtask_id"] = existing.get("gtask_id")
                item["_orbit_id"] = (item.get("orbit_id")
                                     or existing.get("orbit_id")
                                     or _new_orbit_id())
                new_id = _sync_one_to_reminders(list_name, item, project_name,
                                                kind, dry_run=False)
                old_uid = existing.get("gtask_id")
                if new_id and new_id != old_uid:
                    ids.setdefault(key, {})["gtask_id"] = new_id
                    ids[key]["snapshot"] = _make_snapshot(item)
                    ids[key]["orbit_id"] = item.get("_orbit_id")
                    _purge_orbit_orphans(ids, key, item.get("_orbit_id"))
                    _save_ids(project_dir, ids)
                    # Persist orbit-id back into agenda.md.
                    agenda_path = resolve_file(project_dir, "agenda")
                    data = _read_agenda(agenda_path)
                    section_map = {"task": "tasks", "milestone": "milestones",
                                   "reminder": "reminders"}
                    section = section_map[kind]
                    for it in data.get(section, []):
                        if it.get("desc") == item["desc"] and it.get("date") == item.get("date"):
                            it["orbit_id"] = item.get("_orbit_id")
                            break
                    _write_agenda(agenda_path, data)
                item.pop("_gtask_id", None)

            elif kind == "event":
                cal_name = config.get("calendars", {}).get(tipo)
                if not cal_name:
                    cal_name = config.get("calendars", {}).get("default")
                if not cal_name:
                    return
                if not _calendar_app_running():
                    return
                project_name = project_dir.name
                description = _project_description(project_dir, config, html=False)
                existing = ids.get(key, {})
                item["_gcal_id"] = existing.get("gcal_id")
                item["_orbit_id"] = (item.get("orbit_id")
                                     or existing.get("orbit_id")
                                     or _new_orbit_id())
                new_id = _sync_one_event(cal_name, item,
                                         project_name, description,
                                         dry_run=False)
                if new_id and not existing.get("gcal_id"):
                    ids.setdefault(key, {})["gcal_id"] = new_id
                    ids[key]["orbit_id"] = item.get("_orbit_id")
                    ids[key]["snapshot"] = _make_snapshot(item)
                    _purge_orbit_orphans(ids, key, item.get("_orbit_id"))
                    _save_ids(project_dir, ids)
                    # Persist orbit-id back into agenda.md.
                    agenda_path = resolve_file(project_dir, "agenda")
                    data = _read_agenda(agenda_path)
                    for e in data["events"]:
                        if e["desc"] == item["desc"] and e["date"] == item["date"]:
                            e["orbit_id"] = item.get("_orbit_id")
                            break
                    _write_agenda(agenda_path, data)
                item.pop("_gcal_id", None)

        except Exception as exc:
            _do_sync.error = exc

    _do_sync.error = None
    t = threading.Thread(target=_do_sync, daemon=True)
    t.start()
    t.join(timeout=_SYNC_TIMEOUT)
    if t.is_alive():
        # AppleScript still running — sync continues in background, the
        # change will land in Reminders/Calendar shortly. Stay quiet here:
        # the message used to appear under reorganize → commit and looked
        # alarming even though nothing was wrong.
        return
    if _do_sync.error:
        print(f"  ⚠️  gsync: {_do_sync.error}")


# ── Migration: [gtask:id]/[gcal:id] → .gsync-ids.json + [G] ──────────────

def migrate_sync_ids() -> int:
    """Migrate old [gtask:id]/[gcal:id] from agenda.md to .gsync-ids.json.

    Reads each project's agenda.md, extracts Google IDs into .gsync-ids.json,
    and rewrites agenda.md with [G] markers instead of raw IDs.
    """
    import re

    migrated = 0
    for project_dir in iter_project_dirs():
        if not _is_new_project(project_dir):
            continue

        agenda_path = resolve_file(project_dir, "agenda")
        if not agenda_path.exists():
            continue

        text = agenda_path.read_text()
        if "[gtask:" not in text and "[gcal:" not in text:
            continue

        # Parse and extract IDs
        ids = _load_ids(project_dir)
        data = _read_agenda(agenda_path)

        for section in ("tasks", "milestones"):
            for item in data[section]:
                # _parse_task_line already strips [gtask:...] from desc
                # but we need the raw ID — re-parse from file
                pass

        # Re-read raw lines to extract IDs
        gtask_re = re.compile(r"\[gtask:([^\]]+)\]")
        gcal_re = re.compile(r"\[gcal:([^\]]+)\]")

        for item in data["tasks"] + data["milestones"]:
            key = _item_key(item)
            # Find matching raw line for this item
            for line in text.splitlines():
                if item["desc"] in line:
                    gm = gtask_re.search(line)
                    if gm:
                        ids.setdefault(key, {})["gtask_id"] = gm.group(1)
                        item["synced"] = True
                    break

        for ev in data["events"]:
            key = _item_key(ev)
            for line in text.splitlines():
                if ev["desc"] in line and ev["date"] in line:
                    gm = gcal_re.search(line)
                    if gm:
                        ids.setdefault(key, {})["gcal_id"] = gm.group(1)
                        ev["synced"] = True
                    break

        _save_ids(project_dir, ids)
        _write_agenda(agenda_path, data)
        migrated += 1
        print(f"  ✓ {project_dir.name}: IDs migrados a .gsync-ids.json")

    return migrated


# ── Background sync on shell startup ───────────────────────────────────────

def gsync_background() -> "threading.Thread | None":
    """Run a full gsync in a background thread. Called on shell startup.

    Returns the thread so the caller can join() it before checking git status.
    """
    if not _is_gsync_configured():
        return None

    import threading

    def _do_full_sync():
        try:
            config = _load_config()
            has_calendars = any(v for v in config.get("calendars", {}).values())
            do_reminders = (_sync_tasks_enabled(config) or _sync_milestones_enabled(config))

            cal_app_ok = _calendar_app_running() if has_calendars else False
            rem_app_ok = _reminders_app_running() if do_reminders else False
            if not (rem_app_ok or (has_calendars and cal_app_ok)):
                return

            dirs = [d for d in iter_project_dirs() if _is_new_project(d)]

            total = 0
            for project_dir in dirs:
                if rem_app_ok:
                    c, u, _ = _sync_to_reminders_for_project(
                        project_dir, config, dry_run=False)
                    total += c + u
                if has_calendars and cal_app_ok:
                    tipo = _get_project_tipo(project_dir)
                    cal_name = config.get("calendars", {}).get(tipo)
                    if not cal_name:
                        cal_name = config.get("calendars", {}).get("default")
                    if cal_name:
                        c, u, _ = _sync_events_for_project(
                            project_dir, config, dry_run=False)
                        total += c + u

            if total:
                print(f"\n  ☁️  gsync: {total} items sincronizados")

        except Exception:
            pass  # fail silently — user can run gsync manually

    t = threading.Thread(target=_do_full_sync, daemon=True)
    t.start()
    return t

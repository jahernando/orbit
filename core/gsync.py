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

    Recurring events use desc::🔄{recur} (stable across date changes).
    Non-recurring events use desc::date.
    """
    if item.get("recur"):
        return f"{item.get('desc', '')}::🔄{item['recur']}"
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
    }
    _save_config(config)
    return config


def _sync_tasks_enabled(config: dict) -> bool:
    """Check if task sync is enabled. Default True for backwards compat."""
    return config.get("sync_tasks", True)


def _sync_milestones_enabled(config: dict) -> bool:
    """Check if milestone sync is enabled. Default True for backwards compat."""
    return config.get("sync_milestones", True)


def _save_config(config: dict) -> None:
    """Save config back to google-sync.json."""
    CONFIG_PATH.write_text(json.dumps(config, indent=2, ensure_ascii=False) + "\n")


def _get_project_tipo(project_dir: Path) -> str:
    """Get normalized project type key."""
    meta = _read_project_meta(project_dir)
    return _normalize_tipo(meta.get("tipo_label", ""))


# ── Description / title helpers ──────────────────────────────────────────────

def _project_url(project_dir: Path, config: dict) -> Optional[str]:
    """Build GitHub URL for the project file, or None."""
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
    """Build description with project name and GitHub link.

    html=True: returns HTML link (for Google Calendar events).
    html=False: returns plain text (for Google Tasks notes).
    """
    project_name = project_dir.name
    url = _project_url(project_dir, config)

    if html and url:
        return f'<a href="{url}">{project_name}</a>'
    elif url:
        return f"Proyecto: {project_name}\n{url}"
    else:
        return f"Proyecto: {project_name}"


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

    extras = []
    if desc:  extras.append(f'set description of newEv to "{desc}"')
    if loc:   extras.append(f'set location of newEv to "{loc}"')
    if url:   extras.append(f'set url of newEv to "{url}"')
    if rrule: extras.append(f'set recurrence of newEv to "{rrule}"')
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
        f'        return "ok"\n'
        f'    end tell\n'
        f'end tell'
    )
    return _osa(script) == "ok"


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
    """Migrate old recurring keys (desc::date → desc::🔄recur) in-place."""
    for item in items:
        if not item.get("recur"):
            continue
        new_key = _item_key(item)
        if new_key in ids:
            continue
        old_key = f"{item.get('desc', '')}::{item.get('date', '')}"
        if old_key in ids:
            ids[new_key] = ids.pop(old_key)


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

        item[temp_key] = ids.get(key, {}).get(id_key)
        should_sync = item.get("status", "pending") == "pending" or item.get(temp_key)
        if not should_sync:
            item.pop(temp_key, None)
            continue

        try:
            new_id = sync_fn(item)
        except Exception as exc:
            print(f"  ⚠️  [{project_name}] Error sincronizando {label} "
                  f"'{item.get('desc', '?')}': {exc}")
            item.pop(temp_key, None)
            skipped += 1
            continue

        old_id = item.get(temp_key)
        if new_id and new_id != old_id:
            # Either no prior id (true create) or fallback-recreate (relink to fresh uid).
            # Always overwrite so the saved id matches what's actually in the backend.
            ids.setdefault(key, {})[id_key] = new_id
            ids[key]["snapshot"] = _make_snapshot(item)
            item["synced"] = True
            created += 1
            changed = True
            ids_changed = True
        elif old_id:
            ids.setdefault(key, {})["snapshot"] = _make_snapshot(item)
            updated += 1
            ids_changed = True
        else:
            skipped += 1
        item.pop(temp_key, None)

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


# ── Event sync (Calendar.app via AppleScript) ──────────────────────────────

def _ev_props_for_calendar_app(ev: dict, project_name: str,
                               base_description: str) -> dict:
    """Build the property dict consumed by _create/_update_calendar_event."""
    from datetime import timedelta, datetime

    summary = f"{ORBIT_PROMPT}[{project_name}] {ev['desc']}"
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

    # Pull a room URL out of the event notes (📋/🚪 prefixes) into the
    # event's `url` property — Calendar.app shows it as a clickable button.
    from core.agenda_cmds import event_room_urls, event_agenda_urls
    rooms = event_room_urls(ev)
    agendas = event_agenda_urls(ev)
    url = rooms[0] if rooms else (agendas[0] if agendas else "")

    return {
        "summary":     summary,
        "start_iso":   start_iso,
        "end_iso":     end_iso,
        "description": _item_description(ev, base_description, html=False),
        "url":         url,
        "rrule":       rrule,
    }


def _sync_one_event(calendar_name: str, ev: dict,
                    project_name: str, description: str,
                    dry_run: bool) -> Optional[str]:
    """Sync one event to Calendar.app. Returns the AppleScript-side uid."""
    props = _ev_props_for_calendar_app(ev, project_name, description)
    summary = props["summary"]
    uid = ev.get("_gcal_id")
    if uid:
        if dry_run:
            print(f"  ~ actualizar: 📅 {ev['date']} — {summary}")
            return uid
        if _update_calendar_event(uid, calendar_name, props):
            return uid
        # If update failed (e.g. the user deleted the event in Calendar.app),
        # fall through to creating a fresh one so re-sync repairs the link.
        print(f"  ⚠️  No se encontró evento uid={uid}; lo recreo")
        uid = None
    if not uid:
        if dry_run:
            print(f"  ~ crear: 📅 {ev['date']} — {summary}")
            return None
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
            ev["synced"] = False
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

    Uses date (non-recurring) or recur pattern (recurring) to identify
    the same item even when its title has changed.
    """
    if item.get("recur"):
        return f"🔄{item['recur']}"
    return item.get("date", "")


def reconcile_gsync_renames() -> list:
    """Detect items whose title changed in the markdown and re-link their gsync IDs.

    Strategy: find orphaned keys in .gsync-ids.json (no matching item in agenda)
    and unmatched synced items in agenda (☁️ but no key in ids). If an orphan and
    an unmatched item share the same date/recur, treat it as a rename: migrate
    the Google IDs to the new key, update the snapshot, and re-sync.

    Returns list of (project_name, old_desc, new_desc) for each reconciled rename.
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

        # Build set of current item keys
        current_keys = {}
        for item, kind in all_items:
            current_keys[_item_key(item)] = (item, kind)

        # Find orphaned keys (in ids but not in current items)
        orphans = {}
        for key in list(ids.keys()):
            if key not in current_keys:
                orphans[key] = ids[key]

        if not orphans:
            continue

        # Find unmatched items (synced marker but no key in ids)
        unmatched = []
        for item, kind in all_items:
            key = _item_key(item)
            if key not in ids and item.get("synced"):
                unmatched.append((item, kind))

        # Also include items without synced marker that simply don't have a key
        # but share a secondary key with an orphan — these are likely renames
        # where the user also didn't touch the ☁️ marker
        for item, kind in all_items:
            key = _item_key(item)
            if key not in ids and not item.get("synced"):
                # Check if secondary key matches any orphan
                sec = _secondary_key(item)
                for okey, odata in orphans.items():
                    osec = okey.split("::", 1)[1] if "::" in okey else ""
                    if sec and sec == osec:
                        unmatched.append((item, kind))
                        break

        # Try to match orphans to unmatched items by secondary key
        changed = False
        for item, kind in unmatched:
            sec = _secondary_key(item)
            if not sec:
                continue
            # Find matching orphan
            for okey in list(orphans.keys()):
                osec = okey.split("::", 1)[1] if "::" in okey else ""
                if sec == osec:
                    # Found a match — migrate
                    old_desc = okey.split("::")[0]
                    new_key = _item_key(item)
                    odata = orphans.pop(okey)
                    ids.pop(okey, None)
                    ids[new_key] = odata
                    ids[new_key]["snapshot"] = _make_snapshot(item)
                    changed = True
                    results.append((project_dir.name, old_desc, item.get("desc", "?")))

                    # Re-sync to Google with new title
                    try:
                        sync_item(project_dir, item, kind)
                    except Exception:
                        pass
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

def run_gsync(dry_run: bool = False, list_calendars: bool = False) -> int:
    """Push Orbit events to Calendar.app and tasks/milestones to Google Tasks."""
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

    do_gtasks_api = _sync_tasks_enabled(config) or _sync_milestones_enabled(config)
    tasks_service = _get_tasks_service() if do_gtasks_api else None
    if not tasks_service and not (has_calendars and cal_app_ok):
        print("⚠️  Nada que sincronizar (Calendar.app no disponible y tasks desactivadas)")
        return 1

    label = "  [dry-run]" if dry_run else ""
    print(f"Sincronizando Orbit → Calendar.app + Google Tasks{label}")
    print("─" * 50)

    dirs = [d for d in iter_project_dirs() if _is_new_project(d)]

    total_created = total_updated = total_skipped = 0
    events_created = events_updated = events_skipped = 0
    no_calendar_tipos = set()

    for project_dir in dirs:
        tipo = _get_project_tipo(project_dir)

        # Tasks + milestones (Google Tasks, legacy)
        if tasks_service:
            c, u, s = _sync_tasks_for_project(tasks_service, project_dir, config, dry_run)
            if c or u:
                print(f"  [{project_dir.name}] tareas/hitos: {c} nuevas, {u} actualizadas")
            total_created += c
            total_updated += u
            total_skipped += s

        # Events (Calendar.app via AppleScript)
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
    """True if any backend is usable (Calendar.app for events, OR Google for tasks)."""
    if not CONFIG_PATH.exists():
        return False
    config = _load_config()
    has_calendars = any(v for v in config.get("calendars", {}).values())
    if has_calendars:
        return True
    # No event sync configured — but tasks via Google may still be set up
    from core.calendar_sync import CREDENTIALS_PATH, TOKEN_PATH
    return CREDENTIALS_PATH.exists() and TOKEN_PATH.exists()


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

_SYNC_TIMEOUT = 6  # seconds


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

            if kind in ("task", "milestone"):
                if kind == "task" and not _sync_tasks_enabled(config):
                    return
                if kind == "milestone" and not _sync_milestones_enabled(config):
                    return
                service = _get_tasks_service()
                if not service:
                    return
                tasklist_id = _ensure_task_list(service, tipo, config)
                if not tasklist_id:
                    return
                project_name = project_dir.name
                description = _project_description(project_dir, config)
                is_ms = kind == "milestone"
                item["_gtask_id"] = ids.get(key, {}).get("gtask_id")
                new_id = _sync_one_task(service, tasklist_id, item,
                                        project_name, is_ms, description,
                                        dry_run=False)
                if new_id and not item.get("_gtask_id"):
                    ids.setdefault(key, {})["gtask_id"] = new_id
                    _save_ids(project_dir, ids)
                    # Mark [G] in agenda.md
                    agenda_path = resolve_file(project_dir, "agenda")
                    data = _read_agenda(agenda_path)
                    section = "tasks" if kind == "task" else "milestones"
                    for t in data[section]:
                        if t["desc"] == item["desc"] and t.get("date") == item.get("date"):
                            t["synced"] = True
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
                item["_gcal_id"] = ids.get(key, {}).get("gcal_id")
                new_id = _sync_one_event(cal_name, item,
                                         project_name, description,
                                         dry_run=False)
                if new_id and not item.get("_gcal_id"):
                    ids.setdefault(key, {})["gcal_id"] = new_id
                    _save_ids(project_dir, ids)
                    # Mark [G] in agenda.md
                    agenda_path = resolve_file(project_dir, "agenda")
                    data = _read_agenda(agenda_path)
                    for e in data["events"]:
                        if e["desc"] == item["desc"] and e["date"] == item["date"]:
                            e["synced"] = True
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
        print("  ⚠️  gsync: timeout (sincronización en background)")
    elif _do_sync.error:
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
            do_gtasks_api = _sync_tasks_enabled(config) or _sync_milestones_enabled(config)

            tasks_service = _get_tasks_service() if do_gtasks_api else None
            cal_app_ok = _calendar_app_running() if has_calendars else False
            if not tasks_service and not (has_calendars and cal_app_ok):
                return

            dirs = [d for d in iter_project_dirs() if _is_new_project(d)]

            total = 0
            for project_dir in dirs:
                if tasks_service:
                    c, u, _ = _sync_tasks_for_project(
                        tasks_service, project_dir, config, dry_run=False)
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

"""lifecycle — common CRUD orchestration shared by the four appointment kinds.

Sits between :mod:`core.agenda.io` (line parsers/formatters + read/write)
and :mod:`core.agenda.runners` (the per-kind ``run_*`` entry points).
Exposes the generic add/drop/edit/log flows plus the small helpers they
need (validation, ring scheduling, recurrence advance, type config).
"""
from __future__ import annotations

import re
import sys
from datetime import date
from pathlib import Path
from typing import Optional

from core.project import _find_new_project
from core.log import add_orbit_entry, resolve_file
from core.config import get_federation_emoji

from core.agenda.recurrence import _normalize_recur, is_valid_recur, _next_occurrence
from core.agenda.io import _read_agenda, _write_agenda, _valid_date, _valid_time
from core.agenda.display import (
    _select_item, _select_event, _select_item_reminder,
    _AGENDA_NOTE_PREFIX, _ROOM_NOTE_PREFIX, _STRUCTURED_PREFIXES,
)


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
        from views.ring.parse import _parse_ring
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
        from views.ring.parse import _parse_ring
        if _parse_ring(ring) is None:
            return f"⚠️  Ring '{ring}' no válido. Usa: HH:MM, 1d, 2h, 30m, o YYYY-MM-DD HH:MM"
    # Warn if date is in the past (non-recurring only)
    if date_val and _valid_date(date_val) and not recur:
        if date.fromisoformat(date_val) < date.today() and sys.stdin.isatty():
            print(f"⚠️  La fecha {date_val} está en el pasado.")
            try:
                resp = input("   ¿Continuar? [s/N]: ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                resp = ""
            if resp not in ("s", "si", "sí", "y", "yes"):
                return "Cancelado."

    if time_val and time_format == "simple":
        if not date_val:
            return "⚠️  --time requiere --date."
        if not re.match(r"^\d{2}:\d{2}$", time_val):
            return f"⚠️  Hora '{time_val}' no válida. Usa: HH:MM (ej. 15:00)"
    if time_val and time_format == "event":
        if not _valid_time(time_val):
            return f"⚠️  Hora '{time_val}' no válida. Usa: HH:MM o HH:MM-HH:MM (ej. 10:00, 10:00-12:30)"
    return None


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
        "has_end": False, "time_format": "event",
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


def set_cloud_verified(project_dir: Path, orbit_id: str, on: bool) -> bool:
    """Toggle the ``☁️`` (calendar-render-verified) marker on the agenda
    line carrying the given orbit-id.

    Returns True if a line was actually updated, False if no matching
    item was found. Safe to call from background threads — the agenda
    file is read fully into memory, mutated, and re-written.
    """
    from core.log import resolve_file
    agenda_path = resolve_file(project_dir, "agenda")
    if not agenda_path.exists():
        return False
    data = _read_agenda(agenda_path)
    touched = False
    for section in ("tasks", "milestones", "events", "reminders"):
        for it in data.get(section, []):
            if it.get("orbit_id") == orbit_id and it.get("cloud_verified") != on:
                it["cloud_verified"] = on
                touched = True
    if touched:
        _write_agenda(agenda_path, data)
    return touched


def _agenda_via_calendar() -> bool:
    """Return True when tasks/ms/reminders are delivered as Calendar events
    (alarm via CalendarAgent). Used to short-circuit Reminders.app paths.

    Always True since v0.38 (gsync removed): the only path is the
    declarative one — agenda.md → ics_share/.ics → Calendar.app subscribes,
    plus ring_export → daemon → Reminders.app. The legacy AppleScript-direct
    branches gated by ``not _agenda_via_calendar()`` are unreachable.
    """
    return True


def _schedule_ring_if_today(text, project_dir, date_val, ring, time_val, kind):
    """Schedule Mac reminder if ring fires today."""
    if not ring:
        return
    if _agenda_via_calendar():
        # Alarm is attached to the Calendar event by gsync; nothing to do.
        return
    from views.ring.parse import resolve_ring_datetime, _schedule_reminder
    ev_time = time_val.split("-")[0] if time_val and "-" in time_val else time_val
    ring_dt = resolve_ring_datetime(date_val, ring, due_time=ev_time)
    if ring_dt and ring_dt.date() == date.today():
        # Optimistic print: AppleScript runs in background.
        print(f"  ⏰ Recordatorio programado: {ring_dt.strftime('%H:%M')}")
        _schedule_reminder(text, project_dir.name, ring_dt, kind=kind, background=True)


def _delete_ring_if_today(desc, project_dir, date_val, ring, time_val, kind):
    """Delete Mac reminder if it was firing today."""
    if not ring or not date_val:
        return
    if _agenda_via_calendar():
        return
    from views.ring.parse import resolve_ring_datetime, _delete_reminder
    ev_time = time_val.split("-")[0] if time_val and "-" in time_val else time_val
    ring_dt = resolve_ring_datetime(date_val, ring, due_time=ev_time)
    if ring_dt and ring_dt.date() == date.today():
        _delete_reminder(desc, project_dir.name, kind=kind, background=True)


def _update_ring_on_edit(old_desc, item, project_dir, kind, changed_fields):
    """Update Mac reminder on edit: delete old + schedule new if changed."""
    if not item.get("ring") or not item.get("date"):
        return
    if _agenda_via_calendar():
        return
    from views.ring.parse import resolve_ring_datetime, _schedule_reminder, _delete_reminder
    ev_time = item.get("time", "").split("-")[0] if item.get("time") and "-" in item.get("time", "") else item.get("time")
    ring_dt = resolve_ring_datetime(item["date"], item["ring"], due_time=ev_time)
    if ring_dt and ring_dt.date() == date.today():
        if any(changed_fields):
            _delete_reminder(old_desc, project_dir.name, kind=kind, background=True)
        # Optimistic print: AppleScript runs in background.
        print(f"  ⏰ Recordatorio programado: {ring_dt.strftime('%H:%M')}")
        _schedule_reminder(item["desc"], project_dir.name, ring_dt, kind=kind,
                           background=True)


def _sync_to_google(project_dir, item, kind):
    """No-op since v0.38 (gsync removed). Kept as a stub so the many call
    sites in this module don't need surgery yet — they fall through harmlessly."""
    return


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


def _advance_recurrence(item, items_list, cfg) -> tuple:
    """Advance a recurring item to next occurrence.

    Returns (info_str, new_item or None). Appends new item to items_list when
    within until limit; otherwise reports the series has ended and appends
    nothing.
    """
    if not item.get("recur"):
        return "", None
    today_str = date.today().isoformat()
    next_due = _next_occurrence(item.get("date"), item["recur"], today_str)
    until = item.get("until")
    if until and date.fromisoformat(next_due) > date.fromisoformat(until):
        return f" (recur: {item['recur']}) — serie finalizada ({until})", None
    new_item = {"desc": item["desc"], "date": next_due, "recur": item["recur"],
                "until": until, "notes": list(item.get("notes") or [])}
    if cfg["has_status"]:
        new_item["status"] = "pending"
    if cfg["has_ring"]:
        new_item["ring"] = item.get("ring")
    if cfg.get("has_end"):
        # Events: copy all fields, dropping the orbit-id (the new occurrence
        # gets its own identity). Legacy `synced` field is also dropped if
        # present (no longer used).
        new_item = {k: v for k, v in item.items()
                    if k not in ("synced", "orbit_id")}
        new_item["date"] = next_due
    items_list.append(new_item)
    return f" (recur: {item['recur']}) → próxima: {next_due}", new_item


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
        from views.ring.parse import _parse_ring
        if _parse_ring(new_ring) is None:
            return f"⚠️  Ring '{new_ring}' no válido. Usa: HH:MM, 1d, 2h, 30m, o YYYY-MM-DD HH:MM"
    if new_time and new_time != "none":
        if time_format == "simple" and not re.match(r"^\d{2}:\d{2}$", new_time):
            return f"⚠️  Hora '{new_time}' no válida. Usa: HH:MM (ej. 15:00)"
        if time_format == "event" and not _valid_time(new_time):
            return f"⚠️  Hora '{new_time}' no válida. Usa: HH:MM o HH:MM-HH:MM (ej. 10:00, 10:00-12:30)"
    return None


def _upsert_emoji_note(notes: list, prefix: str, value: Optional[str]) -> list:
    """Insert/replace/remove a note line that starts with *prefix*.

    - value is None        → no change
    - value == "none"      → remove all notes with this prefix
    - otherwise            → replace the first matching note, or append
    """
    if value is None:
        return notes
    out = [n for n in notes if not n.startswith(prefix)]
    if value != "none":
        # Insert in the position of the first matching note, or append
        idx = next((i for i, n in enumerate(notes) if n.startswith(prefix)), len(out))
        out.insert(min(idx, len(out)), f"{prefix}{value}")
    return out


def _apply_edits(item: dict, edits: dict, type_name: Optional[str] = None):
    """Apply edit fields to item in place. 'none' → None.

    For events, when ``notes`` is replaced, structured-prefix notes
    (📋 agenda, 📺 room) are preserved so a `--desc` edit doesn't drop them.

    Any edit invalidates the ``cloud_verified`` flag — the calendar
    render now differs from agenda state until the next ``sync_item``
    confirms it. The ☁️ marker disappears immediately on save.
    """
    for key, val in edits.items():
        if val is not None:
            if key == "notes":
                preserved = []
                if type_name == "event":
                    existing = item.get("notes") or []
                    preserved = [n for n in existing
                                 if n.startswith(_STRUCTURED_PREFIXES)]
                if val and val != "none":
                    item["notes"] = [val] + preserved
                else:
                    item["notes"] = preserved
            else:
                item[key] = None if val == "none" else val
    item["cloud_verified"] = False


def _make_edit_occurrence(item, data_list, cfg, edits: dict,
                          type_name: Optional[str] = None):
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
    # Notes — for events, preserve structured-prefix notes (📋, 📺) across
    # a `--desc` edit so user doesn't lose room/agenda inadvertently.
    new_desc = edits.get("notes")
    if new_desc is not None:
        preserved = []
        if type_name == "event":
            existing = item.get("notes") or []
            preserved = [n for n in existing if n.startswith(_STRUCTURED_PREFIXES)]
        new_item["notes"] = ([new_desc] + preserved) if (new_desc and new_desc != "none") else preserved
    else:
        new_item["notes"] = list(item.get("notes") or [])
    # Apply structured field edits (only meaningful for events)
    new_item["notes"] = _upsert_emoji_note(
        new_item["notes"], _AGENDA_NOTE_PREFIX, edits.get("agenda"))
    new_item["notes"] = _upsert_emoji_note(
        new_item["notes"], _ROOM_NOTE_PREFIX, edits.get("room"))
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

def _translate_api_error(msg: str) -> str:
    """Map an API ValueError string to the legacy CLI wording.

    The API raises with short technical strings (``invalid date: 'foo'``);
    the existing CLI tests and CHULETA examples expect longer Spanish
    messages with the ``⚠️`` prefix and a usage hint. This translator
    keeps backward-compatibility without forcing the API to carry CLI
    wording.
    """
    import re as _re
    if (m := _re.match(r"invalid date: '?(.+?)'?$", msg)):
        return (f"⚠️  Fecha '{m.group(1)}' no reconocida. "
                "Usa: YYYY-MM-DD, today, mañana, next monday, ...")
    if (m := _re.match(r"invalid end_date: '?(.+?)'?$", msg)):
        return (f"⚠️  Fecha --end '{m.group(1)}' no reconocida. "
                "Usa: YYYY-MM-DD, today, mañana, next monday, ...")
    if (m := _re.match(r"invalid until: '?(.+?)'?$", msg)):
        return f"⚠️  Fecha --until '{m.group(1)}' no reconocida."
    if (m := _re.match(r"invalid recur: '?(.+?)'?$", msg)):
        return (f"⚠️  Recurrencia '{m.group(1)}' no válida. "
                "Usa: daily, weekly, monthly, weekdays, every 2 weeks, first monday, ...")
    if msg == "until requires recur":
        return "Error: --until requiere --recur."
    if msg == "ring requires date":
        return "⚠️  --ring requiere --date."
    if (m := _re.match(r"invalid ring: '?(.+?)'?$", msg)):
        return (f"⚠️  Ring '{m.group(1)}' no válido. "
                "Usa: HH:MM, 1d, 2h, 30m, o YYYY-MM-DD HH:MM")
    if msg == "time requires date":
        return "⚠️  --time requiere --date."
    if (m := _re.match(r"invalid time: '?(.+?)'?$", msg)):
        return (f"⚠️  Hora '{m.group(1)}' no válida. "
                "Usa: HH:MM o HH:MM-HH:MM (ej. 10:00, 10:00-12:30)")
    if msg.startswith("project not found:"):
        return msg  # _find_new_project already printed; this is rarely surfaced
    # Fallback: pass through with prefix.
    return f"⚠️  {msg}" if not msg.startswith("⚠️") else msg


def _generic_add(type_name: str, project: str, text: str,
                 date_val=None, recur=None, until=None,
                 ring=None, time_val=None, desc=None,
                 end_date=None,
                 ff: Optional[str] = None,
                 agenda: Optional[str] = None,
                 room: Optional[str] = None) -> int:
    """CLI wrapper around :mod:`core.api` ``add_*`` functions.

    Handles the CLI-only concerns the API doesn't (Phase 4.B, ADR-032):
      * Prompt for ring interactively when applicable.
      * Past-date confirmation prompt.
      * Print confirmation line.
      * Schedule Mac reminder when firing today.
      * Translate :class:`ValueError` from the API to legacy CLI error
        wording with the ``⚠️`` prefix.
    """
    from core import api

    cfg = _TYPE_CONFIG[type_name]
    # Reject empty text — argparse leaves the positional as None when
    # omitted; without this the item would land in agenda.md as a
    # literal "None" desc (bug from before v0.32).
    if text is None or not str(text).strip():
        label = cfg["label"].lower()
        print(f"⚠️  Falta el texto del {label}. Uso: orbit {type_name} add "
              f"<proyecto> \"<texto>\" ...")
        return 1

    # Past-date confirmation (CLI-only, never raised by the API).
    if date_val and _valid_date(date_val) and not recur:
        if date.fromisoformat(date_val) < date.today() and sys.stdin.isatty():
            print(f"⚠️  La fecha {date_val} está en el pasado.")
            try:
                resp = input("   ¿Continuar? [s/N]: ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                resp = ""
            if resp not in ("s", "si", "sí", "y", "yes"):
                print("Cancelado.")
                return 1

    if cfg["has_ring"] and date_val and time_val and not ring:
        ring = _prompt_and_validate_ring()

    notes_in = [desc] if desc else None

    try:
        if type_name == "task":
            new_item = api.add_task(project=project, text=text,
                                    date=date_val, time=time_val,
                                    recur=recur, until=until,
                                    ring=ring, ff=ff, notes=notes_in)
        elif type_name == "milestone":
            new_item = api.add_milestone(project=project, text=text,
                                          date=date_val, time=time_val,
                                          recur=recur, until=until,
                                          ring=ring, notes=notes_in)
        elif type_name == "event":
            new_item = api.add_event(project=project, text=text,
                                      date=date_val, time=time_val,
                                      end_date=end_date,
                                      recur=recur, until=until,
                                      ring=ring, notes=notes_in,
                                      agenda=agenda, room=room)
        elif type_name == "reminder":
            new_item = api.add_reminder(project=project, text=text,
                                         date=date_val, time=time_val,
                                         recur=recur, until=until,
                                         notes=notes_in)
        else:
            return 1
    except ValueError as exc:
        # Translate API-level errors to the legacy CLI wording.
        msg = _translate_api_error(str(exc))
        print(msg)
        return 1

    # The api normalised recur and resolved the project; pick them up
    # from the returned item so the print line below shows the same.
    recur = new_item.get("recur")
    project_dir = _find_new_project(project)

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
    elif (type_name == "reminder" and date_val == date.today().isoformat()
            and not _agenda_via_calendar()):
        # Reminders: schedule notification at exact time
        from datetime import datetime
        fire_dt = datetime.fromisoformat(f"{date_val}T{time_val}:00")
        if fire_dt > datetime.now():
            from views.ring.parse import _schedule_reminder
            # Optimistic print: AppleScript runs in background.
            print(f"  🔔 Notificación programada para hoy a las {time_val}")
            _schedule_reminder(text, project_dir.name, fire_dt, kind="reminder",
                                background=True)

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
    next_item = None
    if item.get("recur") and not drop_series:
        if cfg["drop_action"] == "pop":
            # Event was already popped; advance operates on the popped item
            next_info, next_item = _advance_recurrence(item, items, cfg)
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
                if date_val_is_today(item.get("date")) and not _agenda_via_calendar():
                    from views.ring.parse import _delete_reminder
                    _delete_reminder(item_desc, project_dir.name, kind="reminder",
                                      background=True)
                print(f"✓ [{project_dir.name}] Recordatorio avanzado: {item_desc} → {next_due}")
                return 0
        else:
            next_info, next_item = _advance_recurrence(item, items, cfg)

    _write_agenda(agenda_path, data)

    # Logbook + print
    if drop_series:
        if cfg["has_status"]:
            add_orbit_entry(project_dir, f"[serie cancelada] {cfg['label']}: {item_desc} ({item['recur']})", "apunte")
            print(f"✓ [{project_dir.name}] [serie cancelada] {item_desc} ({item['recur']})")
        else:
            print(f"✓ [{project_dir.name}] Serie eliminada: {display} ({item['recur']})")
    else:
        if cfg["has_status"]:
            add_orbit_entry(project_dir, f"[{cfg['drop_verb']}] {cfg['label']}: {item_desc}{next_info}", "apunte")
            print(f"✓ [{project_dir.name}] [{cfg['drop_verb']}] {item_desc}{next_info}")
        else:
            print(f"✓ [{project_dir.name}] {cfg['label']} {cfg['drop_verb']}: {display}{next_info}")
    # Ring cleanup
    if cfg["has_ring"]:
        _delete_ring_if_today(item_desc, project_dir, item.get("date"),
                              item.get("ring"), item.get("time"), cfg["kind"])
    elif (type_name == "reminder" and item.get("date") == date.today().isoformat()
            and not _agenda_via_calendar()):
        from views.ring.parse import _delete_reminder
        _delete_reminder(item_desc, project_dir.name, kind="reminder",
                          background=True)

    # Google sync (task/ms: sync cancelled item, then the advanced occurrence
    # so Calendar shows the next pending one instead of waiting for batch sync)
    if cfg["has_gsync"] and cfg["drop_action"] == "cancel":
        _sync_to_google(project_dir, item, cfg["kind"])
        if next_item is not None:
            _sync_to_google(project_dir, next_item, cfg["kind"])

    return 0


def _generic_edit(type_name: str, project_dir: Path, data: dict,
                  agenda_path: Path, text: Optional[str],
                  new_text=None, new_date=None, new_time=None,
                  new_recur=None, new_until=None, new_ring=None,
                  new_desc=None, new_end=None,
                  new_ff: Optional[str] = None,
                  new_agenda: Optional[str] = None,
                  new_room: Optional[str] = None,
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
    if (new_ff and new_ff not in ("none", "someday")
            and not _valid_date(new_ff)):
        print(f"⚠️  Fast-forward '{new_ff}' no válido. Usa: YYYY-MM-DD, someday, o none.")
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
            if new_ff is not None: edits["ff"] = new_ff
            if new_agenda is not None: edits["agenda"] = new_agenda
            if new_room is not None: edits["room"] = new_room
            new_item, next_info = _make_edit_occurrence(item, items, cfg, edits,
                                                        type_name=type_name)
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
    if new_ff is not None:            edits["ff"]    = new_ff
    _apply_edits(item, edits, type_name=type_name)
    item["notes"] = _upsert_emoji_note(item.get("notes") or [],
                                       _AGENDA_NOTE_PREFIX, new_agenda)
    item["notes"] = _upsert_emoji_note(item["notes"],
                                       _ROOM_NOTE_PREFIX, new_room)

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
    elif (type_name == "reminder" and item.get("date") and item.get("time")
            and not _agenda_via_calendar()):
        if item["date"] == date.today().isoformat():
            from views.ring.parse import _schedule_reminder, _delete_reminder
            from datetime import datetime as _dt, time as _time
            fire_dt = _dt.combine(date.today(), _time.fromisoformat(item["time"]))
            if new_text or new_time:
                _delete_reminder(old_desc, project_dir.name, kind="reminder",
                                  background=True)
            # Optimistic print: AppleScript runs in background.
            print(f"  🔔 Notificación actualizada: {item['time']}")
            _schedule_reminder(item["desc"], project_dir.name, fire_dt,
                                kind="reminder", background=True)

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

    # Events: forward agenda (📋) and room (🚪/📹) notes as indented log
    # continuations so a meeting's indico/zoom links land in the logbook
    # alongside the entry. Use the markdown clickable-icon convention
    # already established by `event_indicators(markdown=True)`.
    continuations = None
    if type_name == "event":
        from core.agenda.display import (
            event_agenda_urls, event_room_urls, _is_meeting_url, _room_icon,
        )
        lines = []
        for url in event_agenda_urls(item):
            lines.append(f"[📋]({url})")
        for room in event_room_urls(item):
            if _is_meeting_url(room):
                lines.append(f"[{_room_icon(room)}]({room})")
            else:
                lines.append(f"🚪 {room}")
        if lines:
            continuations = lines

    from core.log import add_entry
    return add_entry(project_name, item["desc"], cfg["log_type"], None,
                     item.get("date"), continuations=continuations)


def date_val_is_today(date_val):
    """Check if a date string is today."""
    return date_val == date.today().isoformat() if date_val else False

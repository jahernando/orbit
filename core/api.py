"""core.api — stable public seam for orbit's four appointment kinds.

This module is the seam that scripts, hooks and external integrations
should call instead of the CLI-flavoured ``run_*`` functions in
:mod:`core.agenda.runners`. The contract is:

  * **Pure data** — each function validates its arguments, mutates the
    project's ``agenda.md`` on disk, and returns the created item dict.
  * **No stdout**, no ring scheduling, no Google sync, no past-date
    prompt. All side-effects beyond the on-disk write live in the
    callers (typically :mod:`core.agenda.lifecycle._generic_add`).
  * **Errors are exceptions**, not exit codes — invalid input or an
    unknown project raise :class:`ValueError`. CLI wrappers translate
    these to printed messages + nonzero exit codes.

Available so far (Phase 4.B step 1):
  * :func:`add_task` / :func:`add_milestone` / :func:`add_event` / :func:`add_reminder`

The drop / edit / done / log entry points and the ``core.api`` module
naming itself (vs. the ``orbit/api.py`` path the ROADMAP originally
mentioned) are tracked in ADR-032.
"""
from __future__ import annotations

from datetime import date
from typing import Optional, Tuple

from core.project import _find_new_project
from core.log import resolve_file
from core.agenda.recurrence import _normalize_recur, is_valid_recur, _next_occurrence
from core.agenda.io import _read_agenda, _write_agenda, _valid_date, _valid_time
from core.agenda.display import _AGENDA_NOTE_PREFIX, _ROOM_NOTE_PREFIX
from core.agenda.lifecycle import _TYPE_CONFIG


def _resolve_project_or_raise(project: str):
    """Resolve a project name to its directory; raise on failure."""
    if not project:
        raise ValueError("project is required")
    project_dir = _find_new_project(project)
    if project_dir is None:
        raise ValueError(f"project not found: {project}")
    return project_dir


def _validate_common(*, date: Optional[str], time: Optional[str],
                     recur: Optional[str], until: Optional[str],
                     ring: Optional[str], end_date: Optional[str] = None,
                     time_format: str = "simple") -> Optional[str]:
    """Shared validation. Returns the normalised recur (or None).

    Raises ValueError on any invalid input. ``time_format`` is "simple"
    (HH:MM) for task/ms/reminder and "event" (HH:MM[-HH:MM]) for event.
    """
    if date and not _valid_date(date):
        raise ValueError(f"invalid date: {date!r}")
    if end_date and not _valid_date(end_date):
        raise ValueError(f"invalid end_date: {end_date!r}")
    if until and not _valid_date(until):
        raise ValueError(f"invalid until: {until!r}")
    if recur:
        recur = _normalize_recur(recur)
        if not is_valid_recur(recur):
            raise ValueError(f"invalid recur: {recur!r}")
    if until and not recur:
        raise ValueError("until requires recur")
    if ring and not date:
        raise ValueError("ring requires date")
    if ring:
        from core.ring import _parse_ring
        if _parse_ring(ring) is None:
            raise ValueError(f"invalid ring: {ring!r}")
    if time:
        if time_format == "simple":
            import re
            if not date:
                raise ValueError("time requires date")
            if not re.match(r"^\d{2}:\d{2}$", time):
                raise ValueError(f"invalid time: {time!r}")
        elif time_format == "event":
            if not _valid_time(time):
                raise ValueError(f"invalid time: {time!r}")
    return recur


def _build_item(kind: str, *, text: str, date, time, recur, until,
                ring, end_date, notes_in, agenda, room) -> dict:
    """Construct the item dict for the appointments section."""
    cfg = _TYPE_CONFIG[kind]
    notes = list(notes_in or [])
    if agenda:
        notes.append(f"{_AGENDA_NOTE_PREFIX}{agenda}")
    if room:
        notes.append(f"{_ROOM_NOTE_PREFIX}{room}")
    item: dict = {"desc": text, "date": date, "recur": recur,
                  "until": until, "notes": notes, "time": time}
    if cfg["has_status"]:
        item["status"] = "pending"
    if cfg["has_ring"]:
        item["ring"] = ring
    if cfg["has_end"]:
        item["end"] = end_date
    if not cfg["has_status"] and not cfg["has_ring"]:
        # Reminder carries a `cancelled` flag instead of status.
        item["cancelled"] = False
    return item


def _append_and_write(kind: str, project_dir, item: dict) -> dict:
    """Append ``item`` to the appropriate section and write ``agenda.md``."""
    cfg = _TYPE_CONFIG[kind]
    agenda_path = resolve_file(project_dir, "agenda")
    data = _read_agenda(agenda_path)
    data.setdefault(cfg["key"], []).append(item)
    _write_agenda(agenda_path, data)
    return item


# ── Public add_* functions ──────────────────────────────────────────────

def add_task(project: str, text: str, *,
             date: Optional[str] = None,
             time: Optional[str] = None,
             recur: Optional[str] = None,
             until: Optional[str] = None,
             ring: Optional[str] = None,
             notes: Optional[list] = None) -> dict:
    """Add a task to ``project``'s agenda. Returns the created task dict.

    Raises :class:`ValueError` for invalid args or unknown project.
    """
    if not text or not str(text).strip():
        raise ValueError("text is required")
    project_dir = _resolve_project_or_raise(project)
    recur = _validate_common(date=date, time=time, recur=recur,
                             until=until, ring=ring, time_format="simple")
    item = _build_item("task", text=text, date=date, time=time,
                       recur=recur, until=until, ring=ring,
                       end_date=None, notes_in=notes,
                       agenda=None, room=None)
    return _append_and_write("task", project_dir, item)


def add_milestone(project: str, text: str, *,
                  date: Optional[str] = None,
                  time: Optional[str] = None,
                  recur: Optional[str] = None,
                  until: Optional[str] = None,
                  ring: Optional[str] = None,
                  notes: Optional[list] = None) -> dict:
    """Add a milestone. Returns the created milestone dict."""
    if not text or not str(text).strip():
        raise ValueError("text is required")
    project_dir = _resolve_project_or_raise(project)
    recur = _validate_common(date=date, time=time, recur=recur,
                             until=until, ring=ring, time_format="simple")
    item = _build_item("milestone", text=text, date=date, time=time,
                       recur=recur, until=until, ring=ring,
                       end_date=None, notes_in=notes,
                       agenda=None, room=None)
    return _append_and_write("milestone", project_dir, item)


def add_event(project: str, text: str, *,
              date: str,
              time: Optional[str] = None,
              end_date: Optional[str] = None,
              recur: Optional[str] = None,
              until: Optional[str] = None,
              ring: Optional[str] = None,
              notes: Optional[list] = None,
              agenda: Optional[str] = None,
              room: Optional[str] = None) -> dict:
    """Add an event. ``date`` is required (unlike task/milestone)."""
    if not text or not str(text).strip():
        raise ValueError("text is required")
    if not date:
        raise ValueError("date is required for an event")
    project_dir = _resolve_project_or_raise(project)
    recur = _validate_common(date=date, time=time, recur=recur,
                             until=until, ring=ring, end_date=end_date,
                             time_format="event")
    item = _build_item("event", text=text, date=date, time=time,
                       recur=recur, until=until, ring=ring,
                       end_date=end_date, notes_in=notes,
                       agenda=agenda, room=room)
    return _append_and_write("event", project_dir, item)


def add_reminder(project: str, text: str, *,
                 date: str,
                 time: str,
                 recur: Optional[str] = None,
                 until: Optional[str] = None,
                 notes: Optional[list] = None) -> dict:
    """Add a reminder. Both ``date`` and ``time`` are required."""
    if not text or not str(text).strip():
        raise ValueError("text is required")
    if not date:
        raise ValueError("date is required for a reminder")
    if not time:
        raise ValueError("time is required for a reminder")
    project_dir = _resolve_project_or_raise(project)
    recur = _validate_common(date=date, time=time, recur=recur,
                             until=until, ring=None, time_format="simple")
    item = _build_item("reminder", text=text, date=date, time=time,
                       recur=recur, until=until, ring=None,
                       end_date=None, notes_in=notes,
                       agenda=None, room=None)
    return _append_and_write("reminder", project_dir, item)


# ── Item identification ────────────────────────────────────────────────

def _find_matching(items: list, *, orbit_id: Optional[str],
                   desc: Optional[str], date_val: Optional[str]) -> Optional[int]:
    """Locate an item by orbit_id first, then by ``desc`` (+ optional ``date_val``).

    Returns the index in ``items`` or None. Raises ``ValueError`` when
    ``desc`` matches multiple items and ``date_val`` is not given.
    """
    if orbit_id:
        for i, it in enumerate(items):
            if it.get("orbit_id") == orbit_id:
                return i
        return None
    if desc is None:
        return None
    matches = [i for i, it in enumerate(items)
               if it.get("desc") == desc
               and (date_val is None or it.get("date") == date_val)]
    if len(matches) == 0:
        return None
    if len(matches) > 1:
        raise ValueError(
            f"ambiguous match: {len(matches)} items with desc={desc!r}"
            + (f" date={date_val!r}" if date_val else ""))
    return matches[0]


# ── Complete (task / milestone) ────────────────────────────────────────

def _complete_kind(kind: str, project: str, *,
                   orbit_id: Optional[str] = None,
                   desc: Optional[str] = None,
                   date_val: Optional[str] = None) -> Tuple[dict, Optional[dict]]:
    """Shared body of complete_task / complete_milestone."""
    cfg = _TYPE_CONFIG[kind]
    project_dir = _resolve_project_or_raise(project)
    agenda_path = resolve_file(project_dir, "agenda")
    data = _read_agenda(agenda_path)
    items = data[cfg["key"]]
    idx = _find_matching(items, orbit_id=orbit_id, desc=desc, date_val=date_val)
    if idx is None:
        raise ValueError(f"{kind} not found in {project}")
    item = items[idx]
    item["status"] = "done"

    next_item = None
    if item.get("recur"):
        done_iso = date.today().isoformat()
        next_due = _next_occurrence(item.get("date"), item["recur"], done_iso)
        until = item.get("until")
        if not (until and date.fromisoformat(next_due) > date.fromisoformat(until)):
            next_item = {"status": "pending", "desc": item["desc"],
                         "date": next_due, "recur": item["recur"],
                         "until": until, "ring": item.get("ring"),
                         "notes": list(item.get("notes") or [])}
            items.append(next_item)

    _write_agenda(agenda_path, data)
    return item, next_item


def complete_task(project: str, *,
                  orbit_id: Optional[str] = None,
                  desc: Optional[str] = None,
                  date: Optional[str] = None) -> Tuple[dict, Optional[dict]]:
    """Mark a pending task as done. Returns ``(completed, next_or_None)``.

    Identify the task by ``orbit_id`` (preferred) or by ``desc`` (with
    optional ``date`` to disambiguate). For recurring tasks within their
    ``until`` window, a fresh pending occurrence is appended and returned
    as the second tuple element.
    """
    return _complete_kind("task", project, orbit_id=orbit_id,
                          desc=desc, date_val=date)


def complete_milestone(project: str, *,
                       orbit_id: Optional[str] = None,
                       desc: Optional[str] = None,
                       date: Optional[str] = None) -> Tuple[dict, Optional[dict]]:
    """Mark a pending milestone as reached. See :func:`complete_task`."""
    return _complete_kind("milestone", project, orbit_id=orbit_id,
                          desc=desc, date_val=date)


# ── Drop (task / milestone / event / reminder) ─────────────────────────

def _drop_kind(kind: str, project: str, *,
               orbit_id: Optional[str] = None,
               desc: Optional[str] = None,
               date_val: Optional[str] = None,
               drop_series: bool = False) -> Tuple[dict, Optional[dict]]:
    """Shared body of drop_task / drop_milestone / drop_event / drop_reminder.

    Returns ``(dropped_item, next_or_None)``. ``next`` is populated when
    the item is recurring and ``drop_series=False`` and the series has
    not yet exceeded its ``until`` window.
    """
    cfg = _TYPE_CONFIG[kind]
    project_dir = _resolve_project_or_raise(project)
    agenda_path = resolve_file(project_dir, "agenda")
    data = _read_agenda(agenda_path)
    items = data[cfg["key"]]
    idx = _find_matching(items, orbit_id=orbit_id, desc=desc, date_val=date_val)
    if idx is None:
        raise ValueError(f"{kind} not found in {project}")
    item = items[idx]

    # Reminder advance-in-place: if recurring and not drop_series and
    # within `until`, do not cancel — just bump the date and return.
    if (kind == "reminder" and item.get("recur") and not drop_series):
        next_due = _next_occurrence(item.get("date"), item["recur"],
                                    date.today().isoformat())
        until = item.get("until")
        if not (until and date.fromisoformat(next_due) > date.fromisoformat(until)):
            item["date"] = next_due
            item["cancelled"] = False
            _write_agenda(agenda_path, data)
            return item, None

    # Mark cancelled / pop based on kind.
    if cfg["drop_action"] == "cancel":
        item["status"] = "cancelled"
    elif cfg["drop_action"] == "pop":
        items.pop(idx)
    elif cfg["drop_action"] == "cancel_bool":
        item["cancelled"] = True

    # Advance recurrence (non-reminder kinds) if not dropping the series.
    next_item = None
    if item.get("recur") and not drop_series and kind != "reminder":
        done_iso = date.today().isoformat()
        next_due = _next_occurrence(item.get("date"), item["recur"], done_iso)
        until = item.get("until")
        if not (until and date.fromisoformat(next_due) > date.fromisoformat(until)):
            next_item = {k: v for k, v in item.items()
                         if k not in ("synced", "orbit_id")} if cfg.get("has_end") \
                        else {"desc": item["desc"], "date": next_due,
                              "recur": item["recur"], "until": until,
                              "notes": list(item.get("notes") or [])}
            if cfg["has_end"]:
                next_item["date"] = next_due
            else:
                if cfg["has_status"]:
                    next_item["status"] = "pending"
                if cfg["has_ring"]:
                    next_item["ring"] = item.get("ring")
            items.append(next_item)

    _write_agenda(agenda_path, data)
    return item, next_item


def drop_task(project: str, *,
              orbit_id: Optional[str] = None,
              desc: Optional[str] = None,
              date: Optional[str] = None,
              drop_series: bool = False) -> Tuple[dict, Optional[dict]]:
    """Cancel a task. See :func:`_drop_kind`."""
    return _drop_kind("task", project, orbit_id=orbit_id,
                      desc=desc, date_val=date, drop_series=drop_series)


def drop_milestone(project: str, *,
                   orbit_id: Optional[str] = None,
                   desc: Optional[str] = None,
                   date: Optional[str] = None,
                   drop_series: bool = False) -> Tuple[dict, Optional[dict]]:
    return _drop_kind("milestone", project, orbit_id=orbit_id,
                      desc=desc, date_val=date, drop_series=drop_series)


def drop_event(project: str, *,
               orbit_id: Optional[str] = None,
               desc: Optional[str] = None,
               date: Optional[str] = None,
               drop_series: bool = False) -> Tuple[dict, Optional[dict]]:
    return _drop_kind("event", project, orbit_id=orbit_id,
                      desc=desc, date_val=date, drop_series=drop_series)


def drop_reminder(project: str, *,
                  orbit_id: Optional[str] = None,
                  desc: Optional[str] = None,
                  date: Optional[str] = None,
                  drop_series: bool = False) -> Tuple[dict, Optional[dict]]:
    return _drop_kind("reminder", project, orbit_id=orbit_id,
                      desc=desc, date_val=date, drop_series=drop_series)

"""runners — per-kind public ``run_*`` entry points called by the CLI.

These are the functions ``orbit.py`` imports for each subcommand. They
orchestrate the four kinds (task / milestone / event / reminder) on top
of the generic add/drop/edit/log flows in :mod:`core.agenda.lifecycle`.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

from core.project import _find_new_project, _is_new_project
from core.log import add_orbit_entry, resolve_file
from core.config import iter_project_dirs, iter_federated_project_dirs

from core.agenda.recurrence import _next_occurrence
from core.agenda.io import _read_agenda, _write_agenda, _valid_date, _valid_time
from core.agenda.display import _select_item, _select_item_reminder
from core.agenda.lifecycle import (
    _fed_tag, _resolve_project,
    _generic_add, _generic_drop, _generic_edit, _generic_log,
    _agenda_via_calendar, _ask_drop_confirmation,
    date_val_is_today,
)


# ── TASK commands ──────────────────────────────────────────────────────────────

def run_task_add(project: str, text: str, date_val: Optional[str] = None,
                 recur: Optional[str] = None, until: Optional[str] = None,
                 ring: Optional[str] = None, time_val: Optional[str] = None,
                 desc: Optional[str] = None,
                 ff: Optional[str] = None) -> int:
    return _generic_add("task", project, text, date_val=date_val, recur=recur,
                        until=until, ring=ring, time_val=time_val, desc=desc,
                        ff=ff)


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

    selected = data["tasks"][idx]
    task_desc = selected["desc"]

    from core import api
    try:
        completed, next_task = api.complete_task(
            project_dir.name,
            orbit_id=selected.get("orbit_id"),
            desc=selected["desc"],
            date=selected.get("date"))
    except ValueError as exc:
        print(f"⚠️  {exc}")
        return 1

    next_info = ""
    if next_task:
        next_info = (f" (recur: {completed['recur']}) → próxima: "
                     f"{next_task['date']}")
    elif completed.get("recur"):
        next_info = (f" (recur: {completed['recur']}) — serie finalizada "
                     f"({completed.get('until')})")

    add_orbit_entry(project_dir, f"[completada] Tarea: {task_desc}{next_info}", "apunte")
    print(f"✓ [{project_dir.name}] [completada] {task_desc}{next_info}")

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
                  new_desc: Optional[str] = None, new_ff: Optional[str] = None,
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
                         new_desc=new_desc, new_ff=new_ff,
                         force=force, occurrence=occurrence, series=series)


def run_task_plan(project: Optional[str], text: Optional[str],
                  date_val: Optional[str] = None,
                  time_val: Optional[str] = None) -> int:
    """Promote pending→planned or reschedule planned. Sets ``date`` (and
    optionally ``time``), clears ``ff``. If the task was already planned
    and its previous ``date`` was overdue, increment ``failed_count``;
    if the task was pending (had ``ff``), reset ``snooze_count`` to 0.
    """
    project_dir = _resolve_project(project)
    if project_dir is None:
        return 1
    if not date_val:
        print("Error: especifica fecha (ej. task plan <proyecto> <texto> <YYYY-MM-DD>)")
        return 1
    if not _valid_date(date_val):
        print(f"⚠️  Fecha '{date_val}' no reconocida. Usa: YYYY-MM-DD, today, mañana, ...")
        return 1
    if time_val and not _valid_time(time_val):
        print(f"⚠️  Hora '{time_val}' no válida. Usa: HH:MM o HH:MM-HH:MM")
        return 1

    agenda_path = resolve_file(project_dir, "agenda")
    data = _read_agenda(agenda_path)
    idx = _select_item(data["tasks"], "Tareas pendientes", text)
    if idx is None:
        return 1
    task = data["tasks"][idx]

    old_date = task.get("date")
    old_ff   = task.get("ff")
    today_iso = date.today().isoformat()
    was_overdue = bool(old_date) and old_date < today_iso

    task["date"] = date_val
    if time_val is not None:
        task["time"] = time_val
    task["ff"] = None

    if old_ff is not None:
        # pending/someday → planned: reset snooze on promotion
        task["snooze_count"] = 0
        kind_msg = "planeada"
    elif was_overdue:
        # planned overdue → reschedule: count the slip
        task["failed_count"] = task.get("failed_count", 0) + 1
        kind_msg = "replaneada (atrasada)"
    else:
        kind_msg = "replaneada"

    _write_agenda(agenda_path, data)

    desc = task["desc"]
    add_orbit_entry(project_dir, f"[{kind_msg}] Tarea: {desc} → {date_val}", "apunte")
    print(f"✓ [{project_dir.name}] {kind_msg}: {desc} → {date_val}")
    return 0


def run_task_pending(project: Optional[str], text: Optional[str],
                     target_ff: Optional[str] = None) -> int:
    """Demote planned→pending or snooze an existing pending. ``target_ff``
    accepts ``None`` (default: tomorrow for snooze, keep date for demote),
    ``"someday"``, or ``YYYY-MM-DD``. Snoozing a pending increments
    ``snooze_count``; demoting a planned does not (it's a kind change,
    not a slip).
    """
    project_dir = _resolve_project(project)
    if project_dir is None:
        return 1

    agenda_path = resolve_file(project_dir, "agenda")
    data = _read_agenda(agenda_path)
    idx = _select_item(data["tasks"], "Tareas pendientes", text)
    if idx is None:
        return 1
    task = data["tasks"][idx]

    old_ff   = task.get("ff")
    old_date = task.get("date")
    tomorrow = (date.today() + timedelta(days=1)).isoformat()

    if target_ff is None:
        if old_ff is not None:
            target_ff = tomorrow                # snooze: bump to tomorrow
        else:
            target_ff = old_date or tomorrow    # demote: keep date as ff
    elif target_ff != "someday" and not _valid_date(target_ff):
        print(f"⚠️  Fecha '{target_ff}' no reconocida. Usa: YYYY-MM-DD o someday.")
        return 1

    if old_ff is not None:
        # already pending → snooze
        task["ff"] = target_ff
        task["snooze_count"] = task.get("snooze_count", 0) + 1
        kind_msg = "aplazada"
    else:
        # planned → pending (degrade). ff carries the slot; date/time/ring
        # have no meaning without a planned moment, so drop them.
        task["ff"] = target_ff
        task["date"] = None
        task["time"] = None
        task["ring"] = None
        kind_msg = "a pendiente"

    _write_agenda(agenda_path, data)

    desc = task["desc"]
    add_orbit_entry(project_dir, f"[{kind_msg}] Tarea: {desc} ⏩{target_ff}", "apunte")
    print(f"✓ [{project_dir.name}] {kind_msg}: {desc} ⏩{target_ff}")
    return 0


def run_task_list(projects: Optional[list] = None,
                  status_filter: str = "pending",
                  date_filter: Optional[str] = None,
                  dated_only: bool = False,
                  unplanned: bool = False,
                  pending_only: bool = False,
                  someday_only: bool = False,
                  include_federated: bool = True) -> int:
    """List tasks from new-format projects.

    ``pending_only`` filters to tasks with ``ff`` set, excluding
    ``ff:someday``. ``someday_only`` filters to ``ff:someday``. Both
    flags can be combined with the legacy filters (``status_filter``,
    ``date_filter``, ``dated_only``, ``unplanned``).
    """
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
        if pending_only:
            tasks = [t for t in tasks if t.get("ff") and t["ff"] != "someday"]
        if someday_only:
            tasks = [t for t in tasks if t.get("ff") == "someday"]

        if not tasks:
            continue

        print(f"\n{_fed_tag(project_dir)}")
        for t in tasks:
            status_s = {"pending": "[ ]", "done": "[x]", "cancelled": "[-]"}[t["status"]]
            date_s   = f" ({t['date']})" if t.get("date") else ""
            time_s   = f" ⏰{t['time']}"  if t.get("time")  else ""
            recur_s = ""
            if t.get("recur"):
                recur_s = f" 🔄{t['recur']}"
                if t.get("until"):
                    recur_s += f":{t['until']}"
            ring_s   = f" 🔔{t['ring']}"   if t.get("ring")  else ""
            ff_s     = f" ⏩{t['ff']}"     if t.get("ff")    else ""
            snooze   = t.get("snooze_count", 0) or 0
            failed   = t.get("failed_count", 0) or 0
            cnt_s    = (f" 💤{snooze}" if snooze else "") + (f" ❌{failed}" if failed else "")
            print(f"  {status_s} {t['desc']}{date_s}{time_s}{recur_s}{ring_s}{ff_s}{cnt_s}")
            total += 1

    if not total:
        if pending_only:
            print("No hay tareas pending.")
        elif someday_only:
            print("No hay tareas someday.")
        else:
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

    selected = data["milestones"][idx]
    ms_desc = selected["desc"]

    from core import api
    try:
        completed, next_ms = api.complete_milestone(
            project_dir.name,
            orbit_id=selected.get("orbit_id"),
            desc=selected["desc"],
            date=selected.get("date"))
    except ValueError as exc:
        print(f"⚠️  {exc}")
        return 1

    next_info = ""
    if next_ms:
        next_info = (f" (recur: {completed['recur']}) → próxima: "
                     f"{next_ms['date']}")
    elif completed.get("recur"):
        next_info = (f" (recur: {completed['recur']}) — serie finalizada "
                     f"({completed.get('until')})")

    add_orbit_entry(project_dir, f"[alcanzado] Hito: {ms_desc}{next_info}", "resultado")
    print(f"✓ [{project_dir.name}] [alcanzado] {ms_desc}{next_info}")

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
               desc: Optional[str] = None,
               agenda: Optional[str] = None,
               room: Optional[str] = None) -> int:
    return _generic_add("event", project, text, date_val=date_val, end_date=end_date,
                        recur=recur, until=until, ring=ring, time_val=time_val,
                        desc=desc, agenda=agenda, room=room)


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
                new_agenda: Optional[str] = None,
                new_room: Optional[str] = None,
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
                         new_agenda=new_agenda, new_room=new_room,
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
                if date_val_is_today(today_str) and not _agenda_via_calendar():
                    from views.ring.parse import _delete_reminder
                    _delete_reminder(rem["desc"], project_dir.name,
                                      kind="reminder", background=True)
                print(f"✓ [{project_dir.name}] Recordatorio avanzado: {rem['desc']} → {next_due}")
                return 0

        # Cancel
        rem["cancelled"] = True
        _write_agenda(agenda_path, data)
        if date_val_is_today(rem.get("date")) and not _agenda_via_calendar():
            from views.ring.parse import _delete_reminder
            _delete_reminder(rem["desc"], project_dir.name, kind="reminder",
                              background=True)
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


# ── CITA commands ─────────────────────────────────────────────────────────────

# Cita = umbrella para las 4 citas (task / ms / event / reminder). `cita log`
# elimina la fricción de "buscar el proyecto + tipo + texto" cuando quieres
# loguear algo sobre una cita actualmente en curso o reciente.

_CITA_LOG_TAIL_MIN = 10        # tolerancia post-end: cita "viva" 10min después
_CITA_KIND_EMOJI = {
    "events":     "📅",
    "tasks":      "✅",
    "milestones": "🏁",
    "reminders":  "💬",
}
_CITA_LOG_TYPE = {
    "events":     "evento",
    "tasks":      "apunte",
    "milestones": "resultado",
    "reminders":  "apunte",
}
_CITA_DEFAULT_MIN = {
    "events":     60,
    "tasks":      15,
    "milestones": 0,
    "reminders":  0,
}


def _cita_start_min(item) -> int:
    t = item.get("time") or ""
    if not t:
        return 0
    h, m = map(int, t.split("-")[0].split(":"))
    return h * 60 + m


def _cita_duration_min(item, kind: str) -> int:
    t = item.get("time") or ""
    if not t:
        return 0
    if "-" in t:
        a, b = t.split("-", 1)
        ah, am = map(int, a.split(":"))
        bh, bm = map(int, b.split(":"))
        return max((bh * 60 + bm) - (ah * 60 + am), 0)
    return _CITA_DEFAULT_MIN.get(kind, 0)


def _cita_pick(items, label: str, text: Optional[str]):
    """Selector interactivo entre `items` = lista de (kind, project_dir, item).

    Si `text` filtra a un único item → retorna directamente. Si filtra a >1 →
    pregunta. Si no hay text y hay >1 items → pregunta.
    """
    import sys
    if text:
        text_l = text.lower()
        matches = [i for i, (_k, _p, it) in enumerate(items)
                   if text_l in (it.get("desc") or "").lower()]
        if not matches:
            print(f"Sin coincidencias para '{text}'")
            return None
        if len(matches) == 1:
            return matches[0]
        # Restrict pool to matches
        pool = [items[i] for i in matches]
        sub = _cita_pick(pool, label, None)
        return matches[sub] if sub is not None else None

    if len(items) == 1:
        return 0

    print(f"\n{label}:")
    for i, (kind, project_dir, item) in enumerate(items, 1):
        time_s = item.get("time") or "—"
        emoji = _CITA_KIND_EMOJI[kind]
        print(f"  {i}. {emoji} {time_s} [{project_dir.name}] {item['desc']}")
    if not sys.stdin.isatty():
        return None
    try:
        raw = input("Selecciona (#): ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return None
    if raw.isdigit():
        idx = int(raw) - 1
        if 0 <= idx < len(items):
            return idx
    print("Cancelado.")
    return None


def _cita_locate(project_dir, data, text: Optional[str]):
    """Locate one appointment in *data* by *text* across the 4 types.

    Returns ``(kind, index)`` or ``None``. Reuses :func:`_cita_pick` for
    disambiguation, so a unique substring resolves directly and ambiguity
    opens the numbered selector (single shared locator, design §1).
    """
    candidates, index_map = [], []
    for kind in ("tasks", "milestones", "events", "reminders"):
        for i, item in enumerate(data.get(kind, [])):
            candidates.append((kind, project_dir, item))
            index_map.append((kind, i))
    if not candidates:
        print("No hay citas en este proyecto.")
        return None
    pick = _cita_pick(candidates, "Citas del proyecto", text)
    if pick is None:
        return None
    return index_map[pick]


def run_cita_fup(project: Optional[str], text: Optional[str],
                 date_val: Optional[str], desc: Optional[str] = None,
                 drop: bool = False) -> int:
    """Add or drop a ⏩ followup on any appointment (cross-type) in *project*.

    Followups are soft nudges (design §2): they surface the cita on/after
    *date_val* without marking it ❗ and carry no state. Mutations are
    silent — no logbook entry, no side-effect (§0.5) — but echo what
    changed. The key for ``--drop`` is the date.
    """
    from core.agenda.display import add_followup, drop_followup
    from core.dateparse import parse_date

    project_dir = _resolve_project(project)
    if project_dir is None:
        return 1
    if not date_val:
        print("Error: especifica fecha (ej. cita fup <proyecto> <texto> <YYYY-MM-DD>)")
        return 1
    date_norm = parse_date(date_val)
    if not _valid_date(date_norm):
        print(f"⚠️  Fecha '{date_val}' no reconocida. Usa: YYYY-MM-DD, today, mañana, ...")
        return 1

    agenda_path = resolve_file(project_dir, "agenda")
    data  = _read_agenda(agenda_path)
    found = _cita_locate(project_dir, data, text)
    if found is None:
        return 1
    kind, idx = found
    item  = data[kind][idx]
    emoji = _CITA_KIND_EMOJI[kind]

    if drop:
        removed = drop_followup(item, date_norm)
        if not removed:
            print(f"No hay followup ⏩{date_norm} en {emoji} {item['desc']}.")
            return 1
        _write_agenda(agenda_path, data)
        for line in removed:
            print(f"✓ [{project_dir.name}] followup borrado: {emoji} {item['desc']} — {line}")
        return 0

    line = add_followup(item, date_norm, desc)
    _write_agenda(agenda_path, data)
    print(f"✓ [{project_dir.name}] followup: {emoji} {item['desc']} — {line}")
    return 0


def run_cita_done(project: Optional[str], text: Optional[str]) -> int:
    """Mark a task/milestone done, located cross-type (design §1).

    `done` only applies to task/ms (the typed citas with status); events and
    reminders have no done — they are cancelled with `cita drop`. Locates via
    the shared locator, rejects ev/reminder with a clear message, then
    delegates to the per-type runner (full reuse of its logbook/ring logic).
    """
    project_dir = _resolve_project(project)
    if project_dir is None:
        return 1
    data  = _read_agenda(resolve_file(project_dir, "agenda"))
    found = _cita_locate(project_dir, data, text)
    if found is None:
        return 1
    kind, idx = found
    if kind not in ("tasks", "milestones"):
        emoji = _CITA_KIND_EMOJI[kind]
        print(f"⚠️  `done` solo aplica a tareas/hitos, no a {emoji}. "
              f"Usa `cita drop` para cancelar.")
        return 1
    desc   = data[kind][idx]["desc"]
    runner = run_task_done if kind == "tasks" else run_ms_done
    return runner(project=project_dir.name, text=desc)


def run_cita_drop(project: Optional[str], text: Optional[str],
                  force: bool = False, occurrence: bool = False,
                  series: bool = False) -> int:
    """Cancel any appointment, located cross-type (design §1).

    Works on all four types. Locates via the shared locator, then delegates
    to the per-type drop runner so recurrence handling (-o/-s/--force), ring
    deletion and logbook all behave identically to `<type> drop`.
    """
    project_dir = _resolve_project(project)
    if project_dir is None:
        return 1
    data  = _read_agenda(resolve_file(project_dir, "agenda"))
    found = _cita_locate(project_dir, data, text)
    if found is None:
        return 1
    kind, idx = found
    desc   = data[kind][idx]["desc"]
    runner = {"tasks": run_task_drop, "milestones": run_ms_drop,
              "events": run_ev_drop, "reminders": run_reminder_drop}[kind]
    return runner(project=project_dir.name, text=desc,
                  force=force, occurrence=occurrence, series=series)


def run_cita_log(text: Optional[str] = None) -> int:
    """Crea entrada de logbook de la cita activa ahora (o selector).

    Flujo:
    1. Busca items de hoy con hora (tasks/events/ms/reminders, locales — no
       federados, escritura denegada en federación read-only).
    2. Filtra a "activos": `now ∈ [start, end + 10min]`. Reminders excluidos
       de la detección de overlaps pero sí pueden ser "activos" si están a
       <= 10min de now (tratan como instantáneos).
    3. 1 activo → usa ese. >1 → selector. 0 activos → selector con todos los
       items del día.
    4. Una vez elegido, llama directo a `core.log.add_entry` con
       `item.desc` como mensaje y el `log_type` según kind. Para eventos,
       reenvía agenda/room URLs como continuations (paridad con `ev log`).
    """
    from datetime import date as _date, datetime
    from core.agenda.io import _read_agenda
    from core.agenda_view import _resolve_dirs
    from core.log import resolve_file, add_entry

    today = _date.today()
    today_str = today.isoformat()
    now = datetime.now()
    now_min = now.hour * 60 + now.minute

    candidates = []  # (kind, project_dir, item)
    for project_dir in _resolve_dirs(None, include_federated=False):
        agenda_path = resolve_file(project_dir, "agenda")
        if not agenda_path.exists():
            continue
        data = _read_agenda(agenda_path)
        for kind in ("events", "tasks", "milestones", "reminders"):
            for item in data.get(kind, []):
                if item.get("status") in ("done", "cancelled"):
                    continue
                if item.get("date") != today_str:
                    continue
                candidates.append((kind, project_dir, item))

    if not candidates:
        print("No hay citas para hoy.")
        return 1

    # Filtrar activos ahora.
    active = []
    for entry in candidates:
        kind, _proj, item = entry
        t = item.get("time") or ""
        if not t:
            continue  # sin hora no se considera activo
        start = _cita_start_min(item)
        if kind == "reminders":
            # reminders: instantáneo, "activo" si now ∈ [start, start + tail]
            if start <= now_min <= start + _CITA_LOG_TAIL_MIN:
                active.append(entry)
        else:
            end = start + _cita_duration_min(item, kind)
            if start <= now_min <= end + _CITA_LOG_TAIL_MIN:
                active.append(entry)

    # Elegir cita.
    if active:
        idx = _cita_pick(active, "Citas activas ahora", text)
        pool = active
    else:
        # Sort by start_time (con-hora primero, sin-hora al final)
        candidates.sort(key=lambda e: (
            0 if e[2].get("time") else 1,
            _cita_start_min(e[2]) if e[2].get("time") else 0
        ))
        print("(sin citas activas ahora — selecciona de hoy)")
        idx = _cita_pick(candidates, "Citas de hoy", text)
        pool = candidates

    if idx is None:
        return 1
    kind, project_dir, item = pool[idx]

    # Construir continuations para events (paridad con _generic_log).
    continuations = None
    if kind == "events":
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

    log_type = _CITA_LOG_TYPE[kind]
    return add_entry(project_dir.name, item["desc"], log_type, None,
                     item.get("date"), project_dir=project_dir,
                     continuations=continuations)

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

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
                 desc: Optional[str] = None, fup: Optional[str] = None,
                 ask: bool = False) -> int:
    return _generic_add("task", project, text, date_val=date_val, recur=recur,
                        until=until, ring=ring, time_val=time_val, desc=desc,
                        fup=fup, ask=ask)


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
    from core.agenda.display import format_item_block
    print(format_item_block("task", completed,
                            banner=f"task done · {project_dir.name}", state="completada"))
    if next_info:
        print(f"  ↻{next_info}")

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
                  new_desc: Optional[str] = None, fup: Optional[str] = None,
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
                         new_desc=new_desc, fup=fup,
                         force=force, occurrence=occurrence, series=series)


def run_task_list(projects: Optional[list] = None,
                  status_filter: str = "pending",
                  date_filter: Optional[str] = None,
                  dated_only: bool = False,
                  unplanned: bool = False,
                  someday_only: bool = False,
                  include_federated: bool = True) -> int:
    """List tasks from new-format projects.

    ``someday_only`` filters to dateless open tasks (state *someday*, the
    reposo lane). F5 retired the ``ff`` axis, so there is no ``--pending``
    filter anymore; triage now surfaces via followups (``⏩``), collected
    by the "Decidir hoy" viewers, not by a task filter here.
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
        if someday_only:
            # someday = open task with no date (reposo)
            tasks = [t for t in tasks if not t.get("date")]

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
            print(f"  {status_s} {t['desc']}{date_s}{time_s}{recur_s}{ring_s}")
            total += 1

    if not total:
        if someday_only:
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
               desc: Optional[str] = None, fup: Optional[str] = None,
               ask: bool = False) -> int:
    return _generic_add("milestone", project, text, date_val=date_val, recur=recur,
                        until=until, ring=ring, time_val=time_val, desc=desc,
                        fup=fup, ask=ask)


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
    from core.agenda.display import format_item_block
    print(format_item_block("milestone", completed,
                            banner=f"ms done · {project_dir.name}", state="alcanzado"))
    if next_info:
        print(f"  ↻{next_info}")

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
                new_desc: Optional[str] = None, fup: Optional[str] = None,
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
                         new_desc=new_desc, fup=fup,
                         force=force, occurrence=occurrence, series=series)


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
               room: Optional[str] = None, fup: Optional[str] = None,
               ask: bool = False) -> int:
    return _generic_add("event", project, text, date_val=date_val, end_date=end_date,
                        recur=recur, until=until, ring=ring, time_val=time_val,
                        desc=desc, agenda=agenda, room=room, fup=fup, ask=ask)


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
                new_room: Optional[str] = None, fup: Optional[str] = None,
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
                         new_agenda=new_agenda, new_room=new_room, fup=fup,
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
                     desc: Optional[str] = None, fup: Optional[str] = None,
                     ask: bool = False) -> int:
    """Add a reminder to a project's agenda."""
    return _generic_add("reminder", project, text, date_val=date_val,
                        time_val=time_val, recur=recur, until=until, desc=desc,
                        fup=fup, ask=ask)


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
                from core.agenda.display import format_item_block
                print(format_item_block("reminder", rem,
                                        banner=f"reminder drop · {project_dir.name}",
                                        state="avanzada"))
                print(f"  ↻ avanzado → {next_due}")
                return 0

        # Cancel
        rem["cancelled"] = True
        _write_agenda(agenda_path, data)
        if date_val_is_today(rem.get("date")) and not _agenda_via_calendar():
            from views.ring.parse import _delete_reminder
            _delete_reminder(rem["desc"], project_dir.name, kind="reminder",
                              background=True)
        from core.agenda.display import format_item_block
        if drop_series:
            print(f"━━━ reminder drop · {project_dir.name} · serie ━━━")
            print(f"  Serie eliminada: {rem['desc']} ({rem['recur']})")
        else:
            print(format_item_block("reminder", rem,
                                    banner=f"reminder drop · {project_dir.name}",
                                    state="eliminado"))
        return 0

    print("No se encontró el recordatorio.")
    return 1


def run_reminder_edit(project: Optional[str], text: Optional[str],
                      new_text: Optional[str] = None, new_date: Optional[str] = None,
                      new_time: Optional[str] = None, new_recur: Optional[str] = None,
                      new_until: Optional[str] = None,
                      new_desc: Optional[str] = None, fup: Optional[str] = None,
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
                             new_desc=new_desc, fup=fup, force=force,
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


def _cita_locate(project_dir, data, text: Optional[str], kinds=None):
    """Locate one appointment in *data* by *text* across the 4 types.

    Returns ``(kind, index)`` or ``None``. Reuses :func:`_cita_pick` for
    disambiguation, so a unique substring resolves directly and ambiguity
    opens the numbered selector (single shared locator, design §1).

    *kinds* optionally restricts the search to a subset of section keys
    (e.g. ``("tasks",)`` for the typed ``task fup`` verb).
    """
    order = ("tasks", "milestones", "events", "reminders")
    if kinds:
        order = tuple(k for k in order if k in kinds)
    candidates, index_map = [], []
    for kind in order:
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


# ── Typed followup verb (`<type> fup ...`) ─────────────────────────────────
#
# Soft-nudge followups scoped to one appointment type
# so `task fup` never matches an event of the same name. The date positional
# doubles as the verb selector: a real date adds a ⏩, the literal `clean`
# opens a numbered remover ("clean" is never a valid date, no collision).

_FUP_KIND_SECTION = {
    "task": "tasks", "milestone": "milestones", "ms": "milestones",
    "event": "events", "ev": "events",
    "reminder": "reminders", "rem": "reminders",
}


def _fup_open(project, text, kinds):
    """Resolve project + locate one cita (within *kinds*). Returns
    ``(project_dir, agenda_path, data, kind, idx)`` or ``None``."""
    project_dir = _resolve_project(project)
    if project_dir is None:
        return None
    agenda_path = resolve_file(project_dir, "agenda")
    data  = _read_agenda(agenda_path)
    found = _cita_locate(project_dir, data, text, kinds=kinds)
    if found is None:
        return None
    kind, idx = found
    return project_dir, agenda_path, data, kind, idx


def _fup_add(project, text, date_val, desc, kinds):
    from core.agenda.display import add_followup, format_item_block
    from core.dateparse import parse_date

    date_norm = parse_date(date_val)
    if not _valid_date(date_norm):
        print(f"⚠️  Fecha '{date_val}' no reconocida. Usa: YYYY-MM-DD, today, mañana, ...")
        return 1
    opened = _fup_open(project, text, kinds)
    if opened is None:
        return 1
    project_dir, agenda_path, data, kind, idx = opened
    item = data[kind][idx]
    add_followup(item, date_norm, desc)
    _write_agenda(agenda_path, data)
    print(format_item_block(kind, item, banner=f"fup · {project_dir.name}"))
    return 0


def _fup_clean(project, text, kinds):
    import sys
    from core.agenda.display import (item_followups, drop_followup_at,
                                     format_item_block)

    opened = _fup_open(project, text, kinds)
    if opened is None:
        return 1
    project_dir, agenda_path, data, kind, idx = opened
    item  = data[kind][idx]
    emoji = _CITA_KIND_EMOJI[kind]
    fups  = item_followups(item)
    if not fups:
        print(f"No hay followups ⏩ en {emoji} {item['desc']}.")
        return 1

    if len(fups) == 1:
        sel = 0
    else:
        print(f"\nFollowups de {emoji} {item['desc']}:")
        for i, f in enumerate(fups, 1):
            extra = f" — {f['desc']}" if f.get("desc") else ""
            print(f"  {i}. ⏩{f['date']}{extra}")
        if not sys.stdin.isatty():
            print("Varios followups: indica cuál (no interactivo). Cancelado.")
            return 1
        try:
            raw = input("¿Cuál borrar? (#): ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 1
        if not raw.isdigit() or not (1 <= int(raw) <= len(fups)):
            print("Cancelado.")
            return 1
        sel = int(raw) - 1

    removed = drop_followup_at(item, sel)
    _write_agenda(agenda_path, data)
    print(f"  ⏩ borrado: {removed}")
    print(format_item_block(kind, item, banner=f"fup clean · {project_dir.name}"))
    return 0


def run_fup(kind: str, project: Optional[str], text: Optional[str],
            target: Optional[str], desc: Optional[str] = None) -> int:
    """Typed followup verb: ``<kind> fup <project> <title> <date|clean>``.

    *kind* is a singular type name (task/milestone/event/reminder). *target*
    is a date (adds a ⏩) or the literal ``clean`` (numbered remover).
    """
    section = _FUP_KIND_SECTION.get(kind)
    kinds   = (section,) if section else None
    if target == "clean":
        return _fup_clean(project, text, kinds)
    if not target:
        print("Error: especifica fecha o 'clean' "
              "(ej. task fup <proyecto> <texto> <YYYY-MM-DD>)")
        return 1
    return _fup_add(project, text, target, desc, kinds)


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

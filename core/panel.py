"""core/panel.py — dashboard: priority projects, agenda, activity.

  orbit panel [week|month] [--open] [--append proyecto:nota]

Sections:
  1. Priority (alta + milestones this month + urgent for period)
  2. Agenda (dated items in period, grouped by day if multi-day)
  3. Activity (logbook entries in period)
"""

import calendar
from datetime import date, timedelta
from pathlib import Path

from core.config import iter_federated_project_dirs, get_federation_emoji
from core.log import find_logbook_file, find_proyecto_file, resolve_file
from core.project import _read_project_meta, _resolve_status, _is_new_project
from core.tasks import PRIORITY_MAP


# ── Period helpers ────────────────────────────────────────────────────────────

_WEEKDAYS_ES = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]


def _parse_panel_period(period_str):
    """Return (start, end, label) for a panel period.

    Accepts: None/'today'/'hoy', 'week'/'semana', 'month'/'mes'.
    """
    today = date.today()
    if not period_str or period_str.lower() in ("today", "hoy"):
        return today, today, f"{today.isoformat()} ({_WEEKDAYS_ES[today.weekday()]})"
    p = period_str.lower()
    if p in ("week", "semana"):
        monday = today - timedelta(days=today.weekday())
        sunday = monday + timedelta(days=6)
        iso = today.isocalendar()
        label = f"{iso[0]}-W{iso[1]:02d} ({monday.isoformat()} → {sunday.isoformat()})"
        return monday, sunday, label
    if p in ("month", "mes"):
        first = date(today.year, today.month, 1)
        last = date(today.year, today.month,
                    calendar.monthrange(today.year, today.month)[1])
        label = f"{today.strftime('%Y-%m')} ({first.isoformat()} → {last.isoformat()})"
        return first, last, label
    return today, today, f"{today.isoformat()} ({_WEEKDAYS_ES[today.weekday()]})"


# ── Priority scanning ─────────────────────────────────────────────────────────

def _scan_project_agenda(project_dir, start, end):
    """Return (milestones_this_month, has_items_in_period, has_overdue).

    milestones_this_month: list of (date_str, desc) — always scanned for the month.
    has_items_in_period: True if tasks/events/milestones fall in [start, end].
    has_overdue: True if tasks are overdue (before today).
    """
    from core.agenda_cmds import _read_agenda

    agenda_path = resolve_file(project_dir, "agenda")
    if not agenda_path.exists():
        return [], False, False

    data = _read_agenda(agenda_path)
    today = date.today()
    month_end = date(today.year, today.month,
                     calendar.monthrange(today.year, today.month)[1])

    milestones = []
    has_items = False
    has_overdue = False

    for m in data["milestones"]:
        if m["status"] != "pending" or not m.get("date"):
            continue
        try:
            d = date.fromisoformat(m["date"])
            if today <= d <= month_end:
                milestones.append((m["date"], m["desc"]))
            if start <= d <= end:
                has_items = True
        except ValueError:
            pass

    for t in data["tasks"]:
        if t["status"] != "pending" or not t.get("date"):
            continue
        try:
            d = date.fromisoformat(t["date"])
            if start <= d <= end:
                has_items = True
            if d < today:
                has_overdue = True
        except ValueError:
            pass

    for e in data["events"]:
        if not e.get("date"):
            continue
        try:
            d = date.fromisoformat(e["date"])
            if start <= d <= end:
                has_items = True
        except ValueError:
            pass

    return milestones, has_items, has_overdue


def _project_link(project_dir) -> str:
    """Markdown link to project.md; federated get emoji prefix with brackets, no link."""
    fed_emoji = get_federation_emoji(project_dir)
    if fed_emoji:
        return f"{fed_emoji} \\[{project_dir.name}\\]"
    proj_file = find_proyecto_file(project_dir)
    rel = f"{project_dir.parent.name}/{project_dir.name}"
    if proj_file:
        return f"[{project_dir.name}]({rel}/{proj_file.name})"
    return f"[{project_dir.name}]({rel}/)"


def _fed_tag(project_dir) -> str:
    """Terminal tag: [name] for local, 🌿 [name] for federated."""
    emoji = get_federation_emoji(project_dir)
    if emoji:
        return f"{emoji} [{project_dir.name}]"
    return f"[{project_dir.name}]"


def _fed_label(project_dir) -> str:
    """Project name with federation emoji prefix and brackets if federated."""
    emoji = get_federation_emoji(project_dir)
    return f"{emoji} [{project_dir.name}]" if emoji else project_dir.name


def _collect_priority_projects(start, end, include_federated=True):
    """Return (alta, milestones, media)."""
    alta = []
    milestones = []
    media = []
    media_seen = set()

    for project_dir in iter_federated_project_dirs(include_federated):
        if not _is_new_project(project_dir):
            continue
        meta = _read_project_meta(project_dir)
        status_key, _, _ = _resolve_status(meta, project_dir)
        if status_key in ("sleeping", "paused"):
            continue

        prio = meta.get("prioridad", "media").lower()
        motivo = meta.get("prioridad_motivo", "")
        ms_list, has_items, has_overdue = _scan_project_agenda(
            project_dir, start, end)

        if prio == "alta":
            alta.append((project_dir, motivo))

        for ms_date, ms_desc in ms_list:
            milestones.append((project_dir, ms_date, ms_desc))

        reasons = []
        if has_items:
            reasons.append("citas en periodo")
        if has_overdue:
            reasons.append("tareas vencidas")
        if reasons and project_dir not in media_seen:
            media.append((project_dir, ", ".join(reasons)))
            media_seen.add(project_dir)

    milestones.sort(key=lambda x: x[1])
    return alta, milestones, media


# ── Agenda ────────────────────────────────────────────────────────────────────

def _collect_agenda(start, end, include_federated=True):
    """Collect agenda items + adapt to `_agenda_table` format.

    Returns dict ``{date_str: [(kind, item, project_dir, proj_md)]}`` listo
    para `_agenda_table.render_day_rows` (mismo helper que usa
    `agenda.py` → consistencia visual entre las vistas de agenda).

    Comportamiento heredado del panel original:
    - Sólo items con `date` (dated_only=True) — los sin fecha no se
      agrupan por día.
    - En single-day view, items con fecha pasada (no eventos) se pliegan
      a hoy con suffix " (📅fecha) ⚠️" en `desc`. El item se copia para
      no mutar la caché de `_read_agenda`.
    - Recurrencia: heredada de `_collect_data` (que la expande).
    - Reminders: NO incluidos (preserva comportamiento previo del panel;
      ver `agenda.md` si quieres reminders).
    """
    from core.agenda_view import _collect_data
    from views.secretary._agenda_table import proj_link_md

    today = date.today()
    dirs = [d for d in iter_federated_project_dirs(include_federated) if _is_new_project(d)]
    collected = _collect_data(dirs, start, end, dated_only=True)

    by_day = {}  # date_str → [(kind, item, project_dir, proj_md)]
    for project_dir, tasks, events, milestones in collected:
        proj_md = proj_link_md(project_dir)
        for kind, items_list in (("events", events),
                                  ("tasks", tasks),
                                  ("milestones", milestones)):
            for item in items_list:
                day = item.get("date") or ""
                if not day:
                    continue
                entry = (kind, item, project_dir, proj_md)
                # Siempre al start date — preserva el overdue fold de
                # single-day view (tasks/ms de ayer entran a by_day[ayer]
                # y luego se folden a hoy).
                by_day.setdefault(day, []).append(entry)
                # Multi-day events: además a los días subsiguientes que
                # caen en el rango de vista. Tasks/ms no tienen `end`.
                end_day = item.get("end")
                if end_day and end_day != day:
                    try:
                        start_dt = date.fromisoformat(day)
                        end_dt   = date.fromisoformat(end_day)
                    except ValueError:
                        continue
                    cur = max(start_dt + timedelta(days=1), start)
                    last = min(end_dt, end)
                    while cur <= last:
                        by_day.setdefault(cur.isoformat(), []).append(entry)
                        cur += timedelta(days=1)

    # Single-day overdue fold: non-event items de fechas pasadas → hoy.
    # Decora desc con " (📅date) ⚠️" para que se vea que está overdue.
    if start == end:
        today_str = start.isoformat()
        for day_str in list(by_day.keys()):
            if not day_str or day_str >= today_str:
                continue
            items = by_day.pop(day_str)
            non_events = []
            for (kind, item, project_dir, proj_md) in items:
                if kind == "events":
                    continue
                decorated = dict(item)
                decorated["desc"] = f"{item.get('desc', '')} (📅{day_str}) ⚠️"
                non_events.append((kind, decorated, project_dir, proj_md))
            if non_events:
                by_day.setdefault(today_str, []).extend(non_events)

    return by_day


# ── Activity ──────────────────────────────────────────────────────────────────

def _collect_decidir_hoy(today, include_federated=True):
    """Collect pending tasks with ``ff <= today`` across all projects.

    Used by the "Decidir hoy" section of the daily panel. Excludes
    ``ff: someday`` (parked) and items already done/cancelled. Sorted
    ascending by ``ff`` so the most overdue surface first.

    Returns a list of ``(project_dir, task_dict)``.
    """
    from core.agenda_cmds import _read_agenda
    from core.log import resolve_file

    today_iso = today.isoformat()
    results = []
    for project_dir in iter_federated_project_dirs(include_federated):
        if not _is_new_project(project_dir):
            continue
        agenda_path = resolve_file(project_dir, "agenda")
        if not agenda_path or not agenda_path.exists():
            continue
        data = _read_agenda(agenda_path)
        for t in data.get("tasks", []):
            if t.get("status") != "pending":
                continue
            ff = t.get("ff")
            if not ff or ff == "someday":
                continue
            if ff > today_iso:
                continue
            results.append((project_dir, t))

    results.sort(key=lambda r: r[1]["ff"])
    return results


def _collect_activity(start, end, include_federated=True):
    """Collect logbook entries for period. Returns list of (project_dir, entries)."""
    from core.stats import _scan_logbook

    results = []
    for project_dir in sorted(iter_federated_project_dirs(include_federated)):
        if not _is_new_project(project_dir):
            continue
        logbook_path = find_logbook_file(project_dir)
        if not logbook_path or not logbook_path.exists():
            continue
        _, entries, _, _ = _scan_logbook(logbook_path, start, end)
        if entries:
            results.append((project_dir, entries))
    return results


# ── Main ──────────────────────────────────────────────────────────────────────

def _print_calendar(start, end):
    """Print calendar grid. ANSI for terminal, markdown for --open/--append."""
    import sys
    from core.agenda_view import _print_calendar_grid_md, _print_calendar_grid_ansi

    today = date.today()
    dirs = [d for d in iter_federated_project_dirs() if _is_new_project(d)]

    # Always show at least the current week
    cal_start = min(start, today - timedelta(days=today.weekday()))
    cal_end = max(end, cal_start + timedelta(days=6))

    if sys.stdout.isatty():
        _print_calendar_grid_ansi(dirs, cal_start, cal_end)
    else:
        _print_calendar_grid_md(dirs, cal_start, cal_end)


def _collect_cronogramas(include_federated=True):
    """Collect cronograma progress across all projects.

    Returns list of (project_dir, crono_name, done, total, deadline)
    sorted by project. Only includes cronogramas with pending tasks.
    """
    from core.cronograma import (_parse_crono_file, _parent_indices,
                                 _is_leaf, _resolve_deadline)

    results = []
    today = date.today()
    for project_dir in iter_federated_project_dirs(include_federated):
        if not _is_new_project(project_dir):
            continue
        cronos_dir = project_dir / "cronos"
        if not cronos_dir.exists():
            continue
        for crono_file in sorted(cronos_dir.glob("crono-*.md")):
            data = _parse_crono_file(crono_file)
            tasks = data["tasks"]
            if not tasks:
                continue
            parents = _parent_indices(tasks)
            leaves = [t for t in tasks if _is_leaf(t, parents)]
            total = len(leaves)
            done = sum(1 for t in leaves if t["done"])
            if done == total:
                continue  # skip completed cronogramas
            deadline = _resolve_deadline(data["metadata"], project_dir, today)
            results.append((project_dir, data["name"], done, total, deadline))
    return results


def run_panel(period=None, include_federated=True,
              date_from=None, date_to=None) -> int:
    """Print dashboard as markdown."""
    if date_from or date_to:
        from core.dateparse import parse_date
        today = date.today()
        start = date.fromisoformat(parse_date(date_from)) if date_from else today
        end = date.fromisoformat(parse_date(date_to)) if date_to else start
        label = f"{start.isoformat()} → {end.isoformat()}"
    else:
        start, end, label = _parse_panel_period(period)
    is_single_day = start == end

    print(f"# Panel — {label}")
    print("\n---")

    # ── Calendar ──
    print(f"\n## Calendario\n")
    _print_calendar(start, end)
    print("\n---")

    # ── 1. Prioridad ──
    alta, milestones, media = _collect_priority_projects(start, end, include_federated)

    print(f"\n## Prioridad\n")
    has_any = alta or media or milestones
    if has_any:
        print("| | Proyecto | Detalle |")
        print("|---|---------|---------|")
        for project_dir, motivo in alta:
            detail = motivo if motivo else ""
            print(f"| 🔴 | {_project_link(project_dir)} | {detail} |")
        for project_dir, reason in media:
            print(f"| 🔶 | {_project_link(project_dir)} | {reason} |")
        for project_dir, ms_date, ms_desc in milestones:
            print(f"| 🏁 | {_project_link(project_dir)} | {ms_date} — {ms_desc} |")
    else:
        print("(ninguno)")
    print("\n---")

    # ── 2. Agenda ──
    # Usa `_agenda_table.render_day_rows` (helper compartido con
    # `agenda.py`) para que las vistas mantengan exactamente el mismo
    # formato de tabla.
    from views.secretary._agenda_table import render_day_rows
    by_day = _collect_agenda(start, end, include_federated)

    print(f"\n## Agenda\n")
    if by_day:
        if is_single_day:
            items = by_day.get(start.isoformat(), [])
            if items:
                for line in render_day_rows(items):
                    print(line)
            else:
                print("(sin citas)")
        else:
            for day_str in sorted(by_day.keys()):
                if not day_str:
                    continue
                try:
                    d = date.fromisoformat(day_str)
                    wd = _WEEKDAYS_ES[d.weekday()]
                    print(f"**{day_str} ({wd})**\n")
                except ValueError:
                    print(f"**{day_str}**\n")
                for line in render_day_rows(by_day[day_str]):
                    print(line)
                print()
    else:
        print("(sin citas)")
    print("\n---")

    # ── 2.5 Decidir hoy (pending tasks with ff <= today) ──
    today = date.today()
    if is_single_day and start == today:
        decidir = _collect_decidir_hoy(today, include_federated)
        print(f"\n## Decidir hoy\n")
        if decidir:
            today_iso = today.isoformat()
            print("| | ff | Tarea | Proyecto |")
            print("|---|----|------|----------|")
            for project_dir, t in decidir:
                ff_val = t["ff"]
                snooze = t.get("snooze_count", 0) or 0
                if snooze >= 3:
                    mark = "❗❗ "
                elif ff_val < today_iso:
                    mark = "❗ "
                else:
                    mark = ""
                extras = ""
                if snooze:
                    extras += f" 💤{snooze}"
                failed = t.get("failed_count", 0) or 0
                if failed:
                    extras += f" ❌{failed}"
                print(f"| ☐ | {ff_val} | {mark}{t['desc']}{extras} | {_project_link(project_dir)} |")
        else:
            print("(nada que decidir hoy)")
        print("\n---")

    # ── 3. Cronogramas ──
    cronogramas = _collect_cronogramas(include_federated)
    if cronogramas:
        from core.cronograma import _deadline_short_str
        today = date.today()
        print(f"\n## 📊 Cronogramas\n")
        print("| Proyecto | Cronograma | Progreso | | Deadline |")
        print("|----------|------------|----------|---|----------|")
        for project_dir, crono_name, done, total, deadline in cronogramas:
            pct = done * 100 // total if total else 0
            filled = round(pct / 10)
            bar = "█" * filled + "░" * (10 - filled)
            proj = _project_link(project_dir)
            dl_str = _deadline_short_str(done, total, deadline, today)
            print(f"| {proj} | {crono_name} | {bar} | {done}/{total} ({pct}%) | {dl_str} |")
        print("\n---")

    # ── 4. Actividad ──
    activity = _collect_activity(start, end, include_federated)

    print(f"\n## Actividad\n")
    if activity:
        for project_dir, entries in activity:
            print(f"**{_project_link(project_dir)}**")
            for e in entries:
                print(f"- {e}")
            print()
    else:
        print("(sin actividad)")

    return 0

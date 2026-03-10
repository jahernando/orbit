"""orbit report — activity report for projects in a time period.

  orbit report [project...] [--from D] [--to D] [--date D]

Scans logbook, highlights, and agenda of each project and prints
a summary of activity within the period.
"""

import calendar
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

from core.log import PROJECTS_DIR, VALID_TYPES, TAG_EMOJI, find_logbook_file, resolve_file
from core.project import _find_new_project, _is_new_project


# ── Period parsing ────────────────────────────────────────────────────────────

def _parse_period(date_str: Optional[str],
                  date_from: Optional[str] = None,
                  date_to: Optional[str] = None):
    """Return (start, end) dates.  Priority: from/to > date > last 30 days."""
    today = date.today()

    def _start(s: str) -> date:
        if len(s) == 7:
            y, m = int(s[:4]), int(s[5:7])
            return date(y, m, 1)
        return date.fromisoformat(s)

    def _end(s: str) -> date:
        if len(s) == 7:
            y, m = int(s[:4]), int(s[5:7])
            return date(y, m, calendar.monthrange(y, m)[1])
        return date.fromisoformat(s)

    if date_from or date_to:
        s = _start(date_from) if date_from else date(today.year, today.month, 1)
        e = min(_end(date_to), today) if date_to else today
        return s, e

    if not date_str:
        return today - timedelta(days=29), today
    if len(date_str) == 7:
        y, m = int(date_str[:4]), int(date_str[5:7])
        return date(y, m, 1), date(y, m, calendar.monthrange(y, m)[1])
    d = date.fromisoformat(date_str)
    return d, d


# ── Logbook scanning ─────────────────────────────────────────────────────────

def _scan_logbook(path: Path, start: date, end: date):
    """Scan logbook entries in [start, end].

    Returns (counts_by_tag, entries, completed_tasks, completed_ms)
    where entries is a list of raw lines,
    completed_tasks/completed_ms are lists of description strings.
    """
    counts = {}
    entries = []
    completed_tasks = []
    completed_ms = []

    for line in path.read_text().splitlines():
        s = line.strip()
        # Skip continuation lines (indented)
        if line.startswith("  "):
            continue
        if len(s) < 10 or not s[:4].isdigit() or s[4] != "-":
            continue
        try:
            entry_date = date.fromisoformat(s[:10])
        except ValueError:
            continue
        if not (start <= entry_date <= end):
            continue

        entries.append(s)

        # Detect tag
        tag_found = None
        for tag in VALID_TYPES:
            if s.endswith(f"#{tag}"):
                tag_found = tag
                break
        if tag_found:
            counts[tag_found] = counts.get(tag_found, 0) + 1
        else:
            counts["apunte"] = counts.get("apunte", 0) + 1

        # Detect completion traces
        if "[completada] Tarea:" in s:
            desc = s.split("[completada] Tarea:", 1)[1].split("#")[0].strip()
            completed_tasks.append(desc)
        elif "[alcanzado] Hito:" in s:
            desc = s.split("[alcanzado] Hito:", 1)[1].split("#")[0].strip()
            completed_ms.append(desc)

    return counts, entries, completed_tasks, completed_ms


# ── Agenda scanning ──────────────────────────────────────────────────────────

def _scan_agenda(path: Path, end: date):
    """Read agenda.md and return pending/overdue counts.

    Returns dict with:
      tasks_pending, tasks_overdue (list of desc),
      ms_pending, ms_overdue (list of desc),
      events_upcoming (list of (date, desc)) in period.
    """
    from core.agenda_cmds import _read_agenda

    data = _read_agenda(path)

    tasks_pending = []
    tasks_overdue = []
    for t in data["tasks"]:
        if t["status"] != "pending":
            continue
        tasks_pending.append(t)
        if t.get("date"):
            try:
                if date.fromisoformat(t["date"]) < end:
                    tasks_overdue.append(t)
            except ValueError:
                pass

    ms_pending = []
    ms_overdue = []
    for m in data["milestones"]:
        if m["status"] != "pending":
            continue
        ms_pending.append(m)
        if m.get("date"):
            try:
                if date.fromisoformat(m["date"]) < end:
                    ms_overdue.append(m)
            except ValueError:
                pass

    return {
        "tasks_pending": tasks_pending,
        "tasks_overdue": tasks_overdue,
        "ms_pending": ms_pending,
        "ms_overdue": ms_overdue,
        "events": data["events"],
    }


# ── Highlights count ─────────────────────────────────────────────────────────

def _count_highlights(path: Path) -> dict:
    """Return {section_key: count} for highlights."""
    from core.highlights import _read_highlights
    data = _read_highlights(path)
    return {k: len(v) for k, v in data["sections"].items() if v}


# ── Main report ──────────────────────────────────────────────────────────────

def run_report(
    projects: Optional[list] = None,
    date_str: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
) -> int:
    """Print activity report for project(s) in a time period."""
    if not PROJECTS_DIR.exists():
        print(f"Error: directorio de proyectos no encontrado en {PROJECTS_DIR}")
        return 1

    start, end = _parse_period(date_str, date_from, date_to)
    period_days = (end - start).days + 1

    # Resolve project dirs
    if projects:
        dirs = []
        for p in projects:
            d = _find_new_project(p)
            if d:
                dirs.append(d)
        if not dirs:
            return 1
    else:
        dirs = sorted(d for d in PROJECTS_DIR.iterdir()
                      if d.is_dir() and _is_new_project(d))

    lines = [
        f"REPORT — {start.isoformat()} → {end.isoformat()}  ({period_days}d)",
        "═" * 56,
    ]

    grand_entries = 0
    grand_completed_tasks = 0
    grand_completed_ms = 0

    for project_dir in dirs:
        # ── Logbook ──
        logbook_path = find_logbook_file(project_dir)
        if logbook_path and logbook_path.exists():
            counts, entries, comp_tasks, comp_ms = _scan_logbook(
                logbook_path, start, end)
        else:
            counts, entries, comp_tasks, comp_ms = {}, [], [], []

        # ── Agenda ──
        agenda_path = resolve_file(project_dir, "agenda")
        agenda = _scan_agenda(agenda_path, end)

        # ── Highlights ──
        hl_path = resolve_file(project_dir, "highlights")
        hl_counts = _count_highlights(hl_path)

        # ── Events in period ──
        events_in_period = [
            e for e in agenda["events"]
            if start.isoformat() <= e["date"] <= end.isoformat()
        ]

        # Skip project if no activity at all
        total_entries = len(entries)
        has_activity = (total_entries or comp_tasks or comp_ms
                        or agenda["tasks_overdue"] or agenda["ms_overdue"]
                        or events_in_period)
        if not has_activity:
            continue

        grand_entries += total_entries
        grand_completed_tasks += len(comp_tasks)
        grand_completed_ms += len(comp_ms)

        lines.append("")
        lines.append(f"[{project_dir.name}]")

        # Logbook summary
        if total_entries:
            tag_parts = []
            for tag in VALID_TYPES:
                n = counts.get(tag, 0)
                if n:
                    emoji = TAG_EMOJI.get(tag, "")
                    tag_parts.append(f"{emoji}{n}")
            tags_str = "  ".join(tag_parts) if tag_parts else ""
            lines.append(f"  Logbook: {total_entries} entrada{'s' if total_entries != 1 else ''}  {tags_str}")

        # Highlights snapshot
        if hl_counts:
            hl_parts = [f"{k}: {v}" for k, v in hl_counts.items()]
            lines.append(f"  Highlights: {', '.join(hl_parts)}")

        # Tasks
        n_pending = len(agenda["tasks_pending"])
        n_overdue = len(agenda["tasks_overdue"])
        n_completed = len(comp_tasks)
        if n_pending or n_completed or n_overdue:
            parts = []
            if n_completed:
                parts.append(f"{n_completed} completada{'s' if n_completed != 1 else ''}")
            if n_pending:
                parts.append(f"{n_pending} pendiente{'s' if n_pending != 1 else ''}")
            if n_overdue:
                parts.append(f"{n_overdue} vencida{'s' if n_overdue != 1 else ''}")
            lines.append(f"  Tareas: {' · '.join(parts)}")
            # List overdue tasks
            for t in agenda["tasks_overdue"]:
                lines.append(f"    ⚠️  {t['desc']} ({t['date']})")
            # List completed tasks
            for desc in comp_tasks:
                lines.append(f"    ✓  {desc}")

        # Milestones
        n_ms_pending = len(agenda["ms_pending"])
        n_ms_overdue = len(agenda["ms_overdue"])
        n_ms_done = len(comp_ms)
        if n_ms_pending or n_ms_done or n_ms_overdue:
            parts = []
            if n_ms_done:
                parts.append(f"{n_ms_done} alcanzado{'s' if n_ms_done != 1 else ''}")
            if n_ms_pending:
                parts.append(f"{n_ms_pending} pendiente{'s' if n_ms_pending != 1 else ''}")
            if n_ms_overdue:
                parts.append(f"{n_ms_overdue} vencido{'s' if n_ms_overdue != 1 else ''}")
            lines.append(f"  Hitos: {' · '.join(parts)}")

        # Events
        if events_in_period:
            lines.append(f"  Eventos:")
            for e in sorted(events_in_period, key=lambda x: x["date"]):
                lines.append(f"    {e['date']} — {e['desc']}")

    # ── Totals ──
    lines.append("")
    lines.append("─" * 56)
    total_parts = [f"{grand_entries} entradas"]
    if grand_completed_tasks:
        total_parts.append(f"{grand_completed_tasks} tareas completadas")
    if grand_completed_ms:
        total_parts.append(f"{grand_completed_ms} hitos alcanzados")
    lines.append(f"Total: {' · '.join(total_parts)}")

    print("\n".join(lines))
    return 0

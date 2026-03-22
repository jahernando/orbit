"""orbit report — activity report for projects in a time period.

  orbit report [project...] [--from D] [--to D] [--date D]

Scans logbook, highlights, and agenda of each project and prints
a summary of activity within the period.
"""

from datetime import date, timedelta
from pathlib import Path
from typing import Optional

from core.log import VALID_TYPES, TAG_EMOJI, find_logbook_file, resolve_file
from core.config import iter_project_dirs
from core.project import _find_new_project, _is_new_project
from core.agenda_view import _parse_period as _parse_period_base


# ── Period parsing ────────────────────────────────────────────────────────────

def _parse_period(date_str: Optional[str],
                  date_from: Optional[str] = None,
                  date_to: Optional[str] = None):
    """Return (start, end) dates.  Priority: from/to > date > last 30 days.

    Stats-specific: caps end to today when --to is given.
    """
    start, end = _parse_period_base(date_str, date_from, date_to,
                                    default="last_30_days")
    if date_to:
        end = min(end, date.today())
    return start, end


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
    summary: Optional[str] = None,
) -> int:
    """Print activity report for project(s) in a time period."""
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
        dirs = [d for d in iter_project_dirs() if _is_new_project(d)]

    # ── Collect data for all projects ──
    project_data = []
    for project_dir in dirs:
        logbook_path = find_logbook_file(project_dir)
        if logbook_path and logbook_path.exists():
            counts, entries, comp_tasks, comp_ms = _scan_logbook(
                logbook_path, start, end)
        else:
            counts, entries, comp_tasks, comp_ms = {}, [], [], []

        agenda_path = resolve_file(project_dir, "agenda")
        agenda = _scan_agenda(agenda_path, end)

        hl_path = resolve_file(project_dir, "highlights")
        hl_counts = _count_highlights(hl_path)

        events_in_period = [
            e for e in agenda["events"]
            if start.isoformat() <= e["date"] <= end.isoformat()
        ]

        total_entries = len(entries)
        has_activity = (total_entries or comp_tasks or comp_ms
                        or agenda["tasks_overdue"] or agenda["ms_overdue"]
                        or events_in_period)
        if not has_activity:
            continue

        project_data.append({
            "name": project_dir.name,
            "counts": counts,
            "total_entries": total_entries,
            "comp_tasks": comp_tasks,
            "comp_ms": comp_ms,
            "agenda": agenda,
            "hl_counts": hl_counts,
            "events_in_period": events_in_period,
        })

    if summary is not None:
        return _print_summary(project_data, start, end, period_days, summary)
    return _print_report(project_data, start, end, period_days)


# ── Summary table ─────────────────────────────────────────────────────────────

# Logbook tags shown in summary (exclude legacy tarea/evento)
_SUMMARY_TAGS = ["apunte", "idea", "referencia", "problema", "solucion",
                 "resultado", "decision", "evaluacion"]

# Highlights sections shown in summary
_HL_KEYS = ["refs", "results", "decisions", "ideas", "evals", "plans"]
_HL_EMOJI = {"refs": "📎", "results": "📊", "decisions": "📌",
             "ideas": "💡", "evals": "🔍", "plans": "🗓️"}


_SUMMARY_SECTIONS = {"logbook", "agenda", "highlights", "all"}


def _print_summary(project_data: list, start: date, end: date,
                   period_days: int, section: str = "") -> int:
    """Print a compact summary table sorted by total activity.

    section: "" or "all" → logbook+agenda (default),
             "logbook", "agenda", "highlights", or "all" for everything.
    """
    section = section.lower().strip() if section else ""
    if section and section not in _SUMMARY_SECTIONS:
        print(f"⚠️  Sección desconocida: '{section}'")
        print(f"   Opciones: {', '.join(sorted(_SUMMARY_SECTIONS))}")
        return 1

    show_logbook = section in ("", "logbook", "all")
    show_agenda = section in ("", "agenda", "all")
    show_highlights = section in ("highlights", "all")

    # Sort by total activity descending
    for p in project_data:
        p["_activity"] = (p["total_entries"] + len(p["comp_tasks"])
                          + len(p["comp_ms"]) + len(p["events_in_period"]))
    project_data.sort(key=lambda p: p["_activity"], reverse=True)

    # ── Header ──
    header = f"SUMMARY — {start.isoformat()} → {end.isoformat()}  ({period_days}d)"
    print(header)
    print("═" * len(header))

    # ── Logbook table ──
    if show_logbook:
        used_tags = [t for t in _SUMMARY_TAGS
                     if any(p["counts"].get(t, 0) for p in project_data)]
        tag_headers = [TAG_EMOJI.get(t, t) for t in used_tags]
        print()
        print("**Logbook**")
        _print_table(
            project_data, "total_entries",
            extra_cols=tag_headers,
            extra_fn=lambda p: [str(p["counts"].get(t, 0) or "") for t in used_tags],
        )

    # ── Highlights table ──
    if show_highlights:
        has_hl = any(p["hl_counts"] for p in project_data)
        if has_hl:
            used_hl = [k for k in _HL_KEYS
                       if any(p["hl_counts"].get(k, 0) for p in project_data)]
            hl_headers = [_HL_EMOJI.get(k, k) for k in used_hl]
            print()
            print("**Highlights** (snapshot actual)")
            total_hl_fn = lambda p: sum(p["hl_counts"].get(k, 0) for k in used_hl)
            _print_table(
                [p for p in project_data if p["hl_counts"]],
                total_hl_fn,
                extra_cols=hl_headers,
                extra_fn=lambda p: [str(p["hl_counts"].get(k, 0) or "") for k in used_hl],
            )

    # ── Agenda table (tasks + milestones + events) ──
    if show_agenda:
        has_agenda = any(
            p["comp_tasks"] or p["comp_ms"]
            or p["agenda"]["tasks_overdue"] or p["agenda"]["ms_overdue"]
            or p["events_in_period"]
            for p in project_data
        )
        if has_agenda:
            print()
            print("**Agenda**")
            agenda_cols = ["✅done", "⚠️venc", "🏁done", "🏁⚠️", "📅"]
            agenda_data = [p for p in project_data
                           if (p["comp_tasks"] or p["comp_ms"]
                               or p["agenda"]["tasks_overdue"]
                               or p["agenda"]["ms_overdue"]
                               or p["events_in_period"])]
            total_agenda_fn = lambda p: (len(p["comp_tasks"])
                                         + len(p["agenda"]["tasks_overdue"])
                                         + len(p["comp_ms"])
                                         + len(p["agenda"]["ms_overdue"])
                                         + len(p["events_in_period"]))
            _print_table(
                agenda_data, total_agenda_fn,
                extra_cols=agenda_cols,
                extra_fn=lambda p: [
                    str(len(p["comp_tasks"]) or ""),
                    str(len(p["agenda"]["tasks_overdue"]) or ""),
                    str(len(p["comp_ms"]) or ""),
                    str(len(p["agenda"]["ms_overdue"]) or ""),
                    str(len(p["events_in_period"]) or ""),
                ],
            )

    # ── Grand totals ──
    print()
    grand_entries = sum(p["total_entries"] for p in project_data)
    grand_ct = sum(len(p["comp_tasks"]) for p in project_data)
    grand_cm = sum(len(p["comp_ms"]) for p in project_data)
    grand_ev = sum(len(p["events_in_period"]) for p in project_data)
    parts = [f"{grand_entries} entradas"]
    if grand_ct:
        parts.append(f"{grand_ct} tareas completadas")
    if grand_cm:
        parts.append(f"{grand_cm} hitos alcanzados")
    if grand_ev:
        parts.append(f"{grand_ev} eventos")
    print(f"Total: {' · '.join(parts)}")

    return 0


def _print_table(data: list, total_col, extra_cols: list, extra_fn):
    """Print a markdown table.

    total_col: either a string key into p dict, or a callable(p) -> int.
    extra_cols: list of column header strings.
    extra_fn: callable(p) -> list of cell strings (same length as extra_cols).
    """
    if not data:
        return

    # Compute totals
    totals = []
    for p in data:
        if callable(total_col):
            totals.append(total_col(p))
        else:
            totals.append(p[total_col])

    # Header
    hdr = "| Proyecto | # |"
    sep = "|---|--:|"
    for h in extra_cols:
        hdr += f" {h} |"
        sep += "--:|"

    print(hdr)
    print(sep)

    # Data rows
    for j, p in enumerate(data):
        t = totals[j]
        row = f"| {p['name']} | {t} |"
        extras = extra_fn(p)
        for val in extras:
            row += f" {val} |"
        print(row)


# ── Detailed report (original) ───────────────────────────────────────────────

def _print_report(project_data: list, start: date, end: date,
                  period_days: int) -> int:
    """Print the detailed per-project report."""
    lines = [
        f"REPORT — {start.isoformat()} → {end.isoformat()}  ({period_days}d)",
        "═" * 56,
    ]

    grand_entries = 0
    grand_completed_tasks = 0
    grand_completed_ms = 0

    for p in project_data:
        grand_entries += p["total_entries"]
        grand_completed_tasks += len(p["comp_tasks"])
        grand_completed_ms += len(p["comp_ms"])

        lines.append("")
        lines.append(f"[{p['name']}]")

        # Logbook summary
        if p["total_entries"]:
            tag_parts = []
            for tag in VALID_TYPES:
                n = p["counts"].get(tag, 0)
                if n:
                    emoji = TAG_EMOJI.get(tag, "")
                    tag_parts.append(f"{emoji}{n}")
            tags_str = "  ".join(tag_parts) if tag_parts else ""
            lines.append(f"  Logbook: {p['total_entries']} entrada{'s' if p['total_entries'] != 1 else ''}  {tags_str}")

        # Highlights snapshot
        if p["hl_counts"]:
            hl_parts = [f"{k}: {v}" for k, v in p["hl_counts"].items()]
            lines.append(f"  Highlights: {', '.join(hl_parts)}")

        # Tasks
        n_pending = len(p["agenda"]["tasks_pending"])
        n_overdue = len(p["agenda"]["tasks_overdue"])
        n_completed = len(p["comp_tasks"])
        if n_pending or n_completed or n_overdue:
            parts = []
            if n_completed:
                parts.append(f"{n_completed} completada{'s' if n_completed != 1 else ''}")
            if n_pending:
                parts.append(f"{n_pending} pendiente{'s' if n_pending != 1 else ''}")
            if n_overdue:
                parts.append(f"{n_overdue} vencida{'s' if n_overdue != 1 else ''}")
            lines.append(f"  Tareas: {' · '.join(parts)}")
            for t in p["agenda"]["tasks_overdue"]:
                lines.append(f"    ⚠️  {t['desc']} ({t['date']})")
            for desc in p["comp_tasks"]:
                lines.append(f"    ✓  {desc}")

        # Milestones
        n_ms_pending = len(p["agenda"]["ms_pending"])
        n_ms_overdue = len(p["agenda"]["ms_overdue"])
        n_ms_done = len(p["comp_ms"])
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
        if p["events_in_period"]:
            lines.append(f"  Eventos:")
            for e in sorted(p["events_in_period"], key=lambda x: x["date"]):
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

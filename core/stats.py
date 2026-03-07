"""orbit report stats — quantitative analytics across projects and mision-log."""

import calendar
import re
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

from core.log import PROJECTS_DIR, VALID_TYPES, find_logbook_file, find_proyecto_file
from core.tasks import load_project_meta, normalize
from core.open import open_file

MISION_LOG_DIR = Path(__file__).parent.parent / "☀️mision-log"
DIARIO_DIR     = MISION_LOG_DIR / "diario"
STATS_OUTPUT   = MISION_LOG_DIR / "stats.md"

TAG_EMOJI = {
    "idea":       "💡",
    "referencia": "📎",
    "tarea":      "✅",
    "problema":   "⚠️",
    "resultado":  "📊",
    "apunte":     "📝",
    "decision":   "🔀",
    "evento":     "📅",
}


def _parse_period(date_str: Optional[str],
                  date_from: Optional[str] = None,
                  date_to: Optional[str] = None):
    """Return (start, end) dates. Priority: from/to > date > last 30 days."""
    today = date.today()

    def _parse_start(s: str) -> date:
        if len(s) == 7:
            y, m = int(s[:4]), int(s[5:7])
            return date(y, m, 1)
        return date.fromisoformat(s)

    def _parse_end(s: str) -> date:
        if len(s) == 7:
            y, m = int(s[:4]), int(s[5:7])
            return date(y, m, calendar.monthrange(y, m)[1])
        return date.fromisoformat(s)

    if date_from or date_to:
        start = _parse_start(date_from) if date_from else date(today.year, today.month, 1)
        end   = min(_parse_end(date_to), today) if date_to else today
        return start, end

    if not date_str:
        return today - timedelta(days=29), today
    if len(date_str) == 7:
        y, m = int(date_str[:4]), int(date_str[5:7])
        return date(y, m, 1), date(y, m, calendar.monthrange(y, m)[1])
    d = date.fromisoformat(date_str)
    return d, d


def _bar(count: int, max_count: int, width: int = 16) -> str:
    if max_count == 0:
        return "░" * width
    filled = round(count / max_count * width)
    return "█" * filled + "░" * (width - filled)


def _scan_logbook(path: Path, start: date, end: date):
    """Return (counts_by_tag, total) for entries in [start, end]."""
    counts = {t: 0 for t in VALID_TYPES}
    for line in path.read_text().splitlines():
        s = line.strip()
        if len(s) < 10 or not s[:4].isdigit() or s[4] != "-":
            continue
        try:
            entry_date = date.fromisoformat(s[:10])
        except ValueError:
            continue
        if not (start <= entry_date <= end):
            continue
        for tag in VALID_TYPES:
            if s.endswith(f"#{tag}"):
                counts[tag] += 1
                break
        else:
            counts["apunte"] += 1  # untagged lines count as apunte
    total = sum(counts.values())
    return counts, total


def _scan_tasks(proyecto_path: Path, period_end: date):
    """Return (open_count, overdue_count) from ## Tareas section."""
    open_count = overdue_count = 0
    in_tasks = False
    for line in proyecto_path.read_text().splitlines():
        if "## ✅" in line or ("## " in line and "tarea" in line.lower()):
            in_tasks = True
            continue
        if in_tasks and line.startswith("## "):
            in_tasks = False
        if not in_tasks:
            continue
        if re.match(r"- \[ \]", line):
            open_count += 1
            m = re.search(r"\((\d{4}-\d{2}-\d{2})\)", line)
            if m:
                try:
                    due = date.fromisoformat(m.group(1))
                    if due < period_end:
                        overdue_count += 1
                except ValueError:
                    pass
    return open_count, overdue_count


def run_stats(
    date_str: Optional[str],
    date_from: Optional[str],
    date_to: Optional[str],
    output: Optional[str],
    open_after: bool,
    editor: str,
) -> int:
    if not PROJECTS_DIR.exists():
        print(f"Error: directorio de proyectos no encontrado en {PROJECTS_DIR}")
        return 1

    start, end = _parse_period(date_str, date_from, date_to)
    period_days = (end - start).days + 1

    global_counts = {t: 0 for t in VALID_TYPES}
    project_totals = []   # (name, tipo_emoji, total_entries)
    total_open = total_overdue = 0

    for project_dir in sorted(PROJECTS_DIR.iterdir()):
        if not project_dir.is_dir():
            continue
        proyecto_path = find_proyecto_file(project_dir)
        if not proyecto_path or not proyecto_path.exists():
            continue

        meta = load_project_meta(proyecto_path)
        if "completado" in meta["estado_raw"]:
            continue

        logbook_path = find_logbook_file(project_dir)
        if logbook_path and logbook_path.exists():
            counts, total = _scan_logbook(logbook_path, start, end)
            for tag in VALID_TYPES:
                global_counts[tag] += counts[tag]
            if total:
                project_totals.append((project_dir.name, meta["tipo"], total))

        open_c, over_c = _scan_tasks(proyecto_path, end)
        total_open += open_c
        total_overdue += over_c

    # Also scan mision-log/diario
    diario_total = 0
    if DIARIO_DIR.exists():
        for md in DIARIO_DIR.glob("*.md"):
            _, total = _scan_logbook(md, start, end)
            diario_total += total

    grand_total = sum(global_counts.values()) + diario_total
    project_totals.sort(key=lambda x: x[2], reverse=True)
    max_tag = max(global_counts.values(), default=1) or 1
    max_proj = project_totals[0][2] if project_totals else 1

    # Build output
    lines = [
        f"STATS — {start.isoformat()} → {end.isoformat()}  ({period_days}d)",
        "═" * 56,
        "",
        f"Entradas totales: {grand_total}",
        f"  (proyectos: {grand_total - diario_total}  ·  diario: {diario_total})",
        "",
        "Por tipo de entrada:",
    ]

    for tag in VALID_TYPES:
        n = global_counts[tag]
        bar = _bar(n, max_tag)
        lines.append(f"  {TAG_EMOJI[tag]} {tag:<12} {n:>4}  {bar}")

    lines += [
        "",
        "Proyectos más activos:",
    ]
    if project_totals:
        for i, (name, _, total) in enumerate(project_totals[:10], 1):
            bar = _bar(total, max_proj)
            lines.append(f"  {i:>2}. {name:<30} {total:>4}  {bar}")
    else:
        lines.append("  Sin actividad en el período.")

    lines += [
        "",
        f"Tareas: {total_open} abiertas  ·  {total_overdue} vencidas",
    ]

    text = "\n".join(lines)

    if open_after and not output:
        dest = STATS_OUTPUT
    elif output:
        dest = Path(output)
    else:
        dest = None

    if dest:
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(text + "\n")
        print(f"✓ Guardado en {dest}")
        if open_after:
            open_file(dest, editor)
    else:
        print(text)

    return 0

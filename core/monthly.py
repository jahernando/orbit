import calendar
from datetime import date
from pathlib import Path
from typing import Optional

from core.activity import (
    PRIORITY_ORDER, PASSIVE_STATES, TYPE_EMOJI,
    compute_real_priority, compute_real_status,
    get_logbook_activity, parse_date_range,
)
from core.log import PROJECTS_DIR, VALID_TYPES
from core.tasks import PRIORITY_MAP, STATUS_MAP, TYPE_MAP, normalize, read_proyecto_field

MISSION_LOG_DIR = Path(__file__).parent.parent / "☀️mision-log" / "mensual"
TEMPLATE_PATH = Path(__file__).parent.parent / "📐templates" / "mensual.md"

MARKER_START = "<!-- orbit:monthly:start -->"
MARKER_END = "<!-- orbit:monthly:end -->"


def get_month_period(month: Optional[str]) -> tuple:
    today = date.today()
    if month:
        y, m = int(month[:4]), int(month[5:7])
    else:
        y, m = today.year, today.month
    start = date(y, m, 1)
    end = date(y, m, calendar.monthrange(y, m)[1])
    return start, end


def build_table(start: date, end: date, apply: bool) -> tuple:
    """Build markdown table rows. Returns (table_lines, changes)."""
    period_days = (end - start).days + 1
    rows = []
    changes = []

    for project_dir in sorted(PROJECTS_DIR.iterdir()):
        if not project_dir.is_dir():
            continue

        proyecto_path = project_dir / "proyecto.md"
        if not proyecto_path.exists():
            continue

        lines = proyecto_path.read_text().splitlines()
        tipo_raw = normalize(read_proyecto_field(lines, "tipo") or "")
        estado_raw = normalize(read_proyecto_field(lines, "estado") or "")
        prioridad_raw = normalize(read_proyecto_field(lines, "prioridad") or "")
        tipo_emoji = next((TYPE_MAP[k] for k in TYPE_MAP if k in tipo_raw), "")

        if "completado" in estado_raw:
            continue

        nominal_status_key = next((k for k in STATUS_MAP if normalize(k) in estado_raw), "")
        nominal_priority_key = next((k for k in PRIORITY_MAP if normalize(k) in prioridad_raw), "")

        last_entry, counts = get_logbook_activity(project_dir / "logbook.md", start, end)
        has_activity = sum(counts.values()) > 0

        real_status_key = compute_real_status(nominal_status_key, has_activity)
        real_priority_key = compute_real_priority(nominal_priority_key, has_activity, period_days)

        if real_priority_key is None:
            continue

        status_changed = real_status_key != nominal_status_key
        priority_changed = real_priority_key != nominal_priority_key

        if status_changed or priority_changed:
            changes.append({
                "name": project_dir.name,
                "proyecto_path": proyecto_path,
                "real_status_key": real_status_key,
                "real_priority_key": real_priority_key,
            })

        nom_s = STATUS_MAP.get(nominal_status_key, "")
        nom_p = PRIORITY_MAP.get(nominal_priority_key, "")
        real_s = STATUS_MAP.get(real_status_key, "")
        real_p = PRIORITY_MAP.get(real_priority_key, "")

        flag = " ⚠️" if status_changed or priority_changed else ""
        counts_str = " | ".join(str(counts[t]) for t in VALID_TYPES)
        rows.append(
            f"| {project_dir.name} | {tipo_emoji} | {nom_s}{nom_p} | {real_s}{real_p} "
            f"| {last_entry or '—'} | {counts_str} |{flag}"
        )

    type_header = " | ".join(TYPE_EMOJI[t] for t in VALID_TYPES)
    header = f"| Proyecto | T | Nominal | Real | Última | {type_header} |"
    separator = "|---|---|---|---|---|" + "|".join(["---"] * len(VALID_TYPES)) + "|"

    table_lines = [header, separator] + rows
    return table_lines, changes


def inject_table(monthly_path: Path, table_lines: list) -> None:
    content = monthly_path.read_text()
    if MARKER_START not in content or MARKER_END not in content:
        print(f"Warning: markers not found in {monthly_path}")
        return
    before = content.split(MARKER_START)[0]
    after = content.split(MARKER_END)[1]
    new_content = (
        before
        + MARKER_START + "\n"
        + "\n".join(table_lines) + "\n"
        + MARKER_END
        + after
    )
    monthly_path.write_text(new_content)


def run_monthly(month: Optional[str], apply: bool, output: Optional[str]) -> int:
    if not PROJECTS_DIR.exists():
        print(f"Error: projects directory not found at {PROJECTS_DIR}")
        return 1

    start, end = get_month_period(month)
    month_str = start.strftime("%Y-%m")

    table_lines, changes = build_table(start, end, apply)

    # Ensure mensual directory exists
    MISSION_LOG_DIR.mkdir(parents=True, exist_ok=True)
    monthly_path = MISSION_LOG_DIR / f"{month_str}.md"

    # Create from template if it doesn't exist
    if not monthly_path.exists():
        if TEMPLATE_PATH.exists():
            template = TEMPLATE_PATH.read_text()
            # Fix previous month link before replacing YYYY-MM
            y, m = start.year, start.month
            prev_m = m - 1 if m > 1 else 12
            prev_y = y if m > 1 else y - 1
            prev_str = f"{prev_y}-{prev_m:02d}"
            template = template.replace(
                "← [Mes anterior](../mensual/YYYY-MM.md)",
                f"← [Mes anterior](./{prev_str}.md)"
            )
            template = template.replace("YYYY-MM", month_str)
            monthly_path.write_text(template)
            print(f"✓ Created {monthly_path}")
        else:
            print(f"Warning: template not found at {TEMPLATE_PATH}")

    # Inject table into monthly file
    inject_table(monthly_path, table_lines)
    print(f"✓ Table injected into {monthly_path}")

    # Apply status/priority changes if requested
    if apply and changes:
        from core.activity import update_proyecto_field
        for c in changes:
            sk = c["real_status_key"]
            pk = c["real_priority_key"]
            update_proyecto_field(c["proyecto_path"], "estado", f"{STATUS_MAP[sk]} {sk.capitalize()}")
            update_proyecto_field(c["proyecto_path"], "prioridad", f"{PRIORITY_MAP[pk]} {pk.capitalize()}")
        print(f"✓ {len(changes)} proyecto(s) actualizado(s) en proyecto.md")
    elif changes:
        print(f"  {len(changes)} cambio(s) propuesto(s) — ejecuta con --apply para aplicarlos")

    # Optional terminal/file output
    type_header = " | ".join(TYPE_EMOJI[t] for t in VALID_TYPES)
    out = [
        f"MONTHLY — {month_str}  ({start.isoformat()} → {end.isoformat()})",
        "═" * 62,
        "",
        f"| Proyecto | T | Nominal | Real | Última | {type_header} |",
        "|---|---|---|---|---|" + "|".join(["---"] * len(VALID_TYPES)) + "|",
    ] + table_lines[2:]  # skip header/separator already added

    text = "\n".join(out)
    if output:
        Path(output).write_text(text + "\n")
        print(f"✓ Saved to {output}")
    else:
        print(text)

    return 0

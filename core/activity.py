import calendar
from datetime import date, timedelta
from pathlib import Path
from typing import Optional, Tuple

from core.log import PROJECTS_DIR, VALID_TYPES, find_proyecto_file, find_logbook_file
from core.tasks import (
    PRIORITY_MAP, STATUS_MAP, TYPE_MAP,
    normalize, read_proyecto_field, update_proyecto_field, load_project_meta,
)

TYPE_EMOJI = {
    "idea":       "💡",
    "referencia": "📎",
    "tarea":      "✅",
    "problema":   "⚠️",
    "resultado":  "📊",
    "apunte":     "📝",
    "decision":   "📌",
    "evento":     "📅",
}

PRIORITY_ORDER = ["alta", "media", "baja"]


def parse_date_range(
    desde: Optional[str],
    hasta: Optional[str],
) -> Tuple[date, date]:
    today = date.today()

    def parse_start(s: str) -> date:
        if len(s) == 7:
            y, m = int(s[:4]), int(s[5:7])
            return date(y, m, 1)
        return date.fromisoformat(s)

    def parse_end(s: str) -> date:
        if len(s) == 7:
            y, m = int(s[:4]), int(s[5:7])
            return date(y, m, calendar.monthrange(y, m)[1])
        return date.fromisoformat(s)

    if desde and not hasta:
        # Single value: full month or single day
        return parse_start(desde), min(parse_end(desde), today)
    if desde or hasta:
        return (
            parse_start(desde) if desde else date(today.year, today.month, 1),
            min(parse_end(hasta), today) if hasta else today,
        )
    # Default: last 60 days
    return today - timedelta(days=60), today


def get_logbook_activity(
    logbook_path: Path, start: date, end: date
) -> Tuple[Optional[str], dict]:
    """Return (last_entry_date_str, counts_by_type) for the given period."""
    counts = {t: 0 for t in VALID_TYPES}
    last_date = None

    if not logbook_path.exists():
        return None, counts

    today = date.today()
    for line in logbook_path.read_text().splitlines():
        line = line.strip()
        if len(line) < 10 or not line[:4].isdigit() or line[4] != "-":
            continue
        try:
            entry_date = date.fromisoformat(line[:10])
        except ValueError:
            continue

        if entry_date > today:
            continue  # ignore future-dated entries

        if start <= entry_date <= end:
            if last_date is None or entry_date > last_date:
                last_date = entry_date
            for tipo in VALID_TYPES:
                if line.endswith(f"#{tipo}"):
                    counts[tipo] += 1
                    break

    return last_date.isoformat() if last_date else None, counts


def has_activity_in(logbook_path: Optional[Path], start: date, end: date) -> bool:
    """Return True if there is any logbook entry in [start, end]."""
    if not logbook_path or not logbook_path.exists():
        return False
    today = date.today()
    for line in logbook_path.read_text().splitlines():
        line = line.strip()
        if len(line) < 10 or not line[:4].isdigit() or line[4] != "-":
            continue
        try:
            entry_date = date.fromisoformat(line[:10])
        except ValueError:
            continue
        if entry_date > today:
            continue
        if start <= entry_date <= end:
            return True
    return False


def compute_real_status(nominal_key: str, has_activity_30: bool, has_activity_60: bool) -> str:
    """Compute real status based on activity in last 30 and 60 days.

    - completado / esperando → always unchanged
    - inicial → en marcha if activity in 30d, else stays inicial (not started ≠ sleeping)
    - No activity in 60d → durmiendo
    - No activity in 30d → parado
    - Activity in 30d → en marcha
    """
    if nominal_key in ("completado", "esperando"):
        return nominal_key
    if nominal_key == "inicial":
        return "en marcha" if has_activity_30 else "inicial"
    if not has_activity_60:
        return "durmiendo"
    if not has_activity_30:
        return "parado"
    return "en marcha"


def compute_real_priority(
    priority_key: str, has_activity: bool, period_days: int, is_passive: bool = False
) -> Optional[str]:
    """Return new priority key, or None if project should be archived.

    is_passive: if True (esperando, inicial), skip degradation.
    """
    if is_passive or has_activity or period_days < 30:
        return priority_key
    idx = PRIORITY_ORDER.index(priority_key) if priority_key in PRIORITY_ORDER else -1
    if idx == -1:
        return priority_key
    if idx + 1 >= len(PRIORITY_ORDER):
        return None  # baja + no activity → archived
    return PRIORITY_ORDER[idx + 1]



def run_activity(
    project: Optional[str],
    tipo: Optional[str],
    prioridad: Optional[str],
    desde: Optional[str],
    hasta: Optional[str],
    apply: bool,
    output: Optional[str],
) -> int:
    if not PROJECTS_DIR.exists():
        print(f"Error: projects directory not found at {PROJECTS_DIR}")
        return 1

    start, end = parse_date_range(desde, hasta)
    period_days = (end - start).days + 1

    rows = []
    changes = []
    archived = []

    for project_dir in sorted(PROJECTS_DIR.iterdir()):
        if not project_dir.is_dir():
            continue
        if project and project.lower() not in project_dir.name.lower():
            continue

        proyecto_path = find_proyecto_file(project_dir)
        if not proyecto_path or not proyecto_path.exists():
            continue

        meta = load_project_meta(proyecto_path)
        tipo_raw      = meta["tipo_raw"]
        estado_raw    = meta["estado_raw"]
        prioridad_raw = meta["prioridad_raw"]
        tipo_emoji    = meta["tipo"]

        if tipo and normalize(tipo) not in tipo_raw:
            continue
        if prioridad and normalize(prioridad) not in prioridad_raw:
            continue
        if "completado" in estado_raw:
            continue

        nominal_status_key = next((k for k in STATUS_MAP if normalize(k) in estado_raw), "")
        nominal_priority_key = next((k for k in PRIORITY_MAP if normalize(k) in prioridad_raw), "")

        logbook_path = find_logbook_file(project_dir)
        last_entry, counts = get_logbook_activity(logbook_path, start, end)
        has_activity_60 = has_activity_in(logbook_path, end - timedelta(days=60), end)
        has_activity_30 = has_activity_in(logbook_path, end - timedelta(days=30), end)

        real_status_key = compute_real_status(nominal_status_key, has_activity_30, has_activity_60)
        is_passive = nominal_status_key in ("esperando", "inicial")
        real_priority_key = compute_real_priority(nominal_priority_key, has_activity_30, period_days, is_passive)

        if real_priority_key is None:
            archived.append(project_dir.name)
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

        rows.append({
            "name": project_dir.name,
            "tipo": tipo_emoji,
            "nominal_status": STATUS_MAP.get(nominal_status_key, ""),
            "real_status": STATUS_MAP.get(real_status_key, ""),
            "nominal_priority": PRIORITY_MAP.get(nominal_priority_key, ""),
            "real_priority": PRIORITY_MAP.get(real_priority_key, ""),
            "status_changed": status_changed,
            "priority_changed": priority_changed,
            "last_entry": last_entry or "—",
            "counts": counts,
        })

    # Build output lines
    out = [
        f"ACTIVIDAD — {start.isoformat()} → {end.isoformat()}  ({period_days}d)",
        "═" * 62,
        "",
    ]

    if not rows:
        out.append("No se encontraron proyectos con los filtros indicados.")
    else:
        type_header = "  ".join(TYPE_EMOJI[t] for t in VALID_TYPES)
        out.append(f"{'Proyecto':<24} {'T':<3} {'Nominal':<6} {'Real':<6} {'Última':<12}  {type_header}")
        out.append("─" * 72)

        for r in rows:
            nom = f"{r['nominal_status']}{r['nominal_priority']}"
            real = f"{r['real_status']}{r['real_priority']}"
            flag = " ⚠️" if r["status_changed"] or r["priority_changed"] else ""
            counts_str = "   ".join(f"{r['counts'][t]:>1}" for t in VALID_TYPES)
            out.append(f"{r['name']:<24} {r['tipo']:<3} {nom:<6} {real:<6} {r['last_entry']:<12}  {counts_str}{flag}")

        if changes:
            out += ["", "─" * 40, "CAMBIOS PROPUESTOS:"]
            for c in changes:
                s = f"{STATUS_MAP[c['real_status_key']]} {c['real_status_key']}"
                p = f"{PRIORITY_MAP[c['real_priority_key']]} {c['real_priority_key']}"
                out.append(f"  {c['name']}: estado → {s}   prioridad → {p}")

            if apply:
                for c in changes:
                    sk = c["real_status_key"]
                    pk = c["real_priority_key"]
                    update_proyecto_field(c["proyecto_path"], "estado", f"{STATUS_MAP[sk]} {sk.capitalize()}")
                    update_proyecto_field(c["proyecto_path"], "prioridad", f"{PRIORITY_MAP[pk]} {pk.capitalize()}")
                out += ["", f"  ✓ {len(changes)} proyecto(s) actualizado(s) en proyecto.md"]
            else:
                out += ["", "  Ejecuta con --apply para aplicar estos cambios en proyecto.md"]

    if archived:
        out += ["", "─" * 40, f"ARCHIVADOS — 💤🔵 sin actividad ({len(archived)}):"]
        for name in archived:
            out.append(f"  {name}")

    text = "\n".join(out)

    if output:
        Path(output).write_text(text + "\n")
        print(f"✓ Saved to {output}")
    else:
        print(text)

    return 0

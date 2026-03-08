"""orbit report status — project activity and health table."""

from datetime import date, timedelta
from pathlib import Path
from typing import Optional

from core.log import PROJECTS_DIR, find_logbook_file, find_proyecto_file
from core.tasks import STATUS_MAP, PRIORITY_MAP, load_project_meta, normalize, update_proyecto_field
from core.activity import get_logbook_activity, compute_real_status, compute_real_priority
from core.open import open_file

MISION_LOG_DIR = Path(__file__).parent.parent / "☀️mision-log"
STATUS_OUTPUT  = MISION_LOG_DIR / "status.md"


def _count_entries(lb_path: Optional[Path], date_from: date, date_to: date) -> int:
    """Count logbook entries between two dates (inclusive)."""
    if not lb_path or not lb_path.exists():
        return 0
    _, counts = get_logbook_activity(lb_path, date_from, date_to)
    return sum(counts.values()) if counts else 0


def run_review(
    date_str: Optional[str],
    apply: bool,
    output: Optional[str],
    open_after: bool,
    editor: str,
) -> int:
    if not PROJECTS_DIR.exists():
        print(f"Error: directorio de proyectos no encontrado en {PROJECTS_DIR}")
        return 1

    today = date.today()
    if date_str:
        try:
            today = date.fromisoformat(date_str[:10])
        except ValueError:
            pass

    d30 = today - timedelta(days=30)
    d60 = today - timedelta(days=60)

    # ── Collect rows ──────────────────────────────────────────────────────────
    rows = []
    for project_dir in sorted(PROJECTS_DIR.iterdir()):
        if not project_dir.is_dir():
            continue
        proyecto_path = find_proyecto_file(project_dir)
        if not proyecto_path or not proyecto_path.exists():
            continue

        meta = load_project_meta(proyecto_path)
        if "completado" in meta["estado_raw"]:
            continue

        nominal_estado_key = next(
            (k for k in STATUS_MAP   if normalize(k) in meta["estado_raw"]), "")
        nominal_prio_key   = next(
            (k for k in PRIORITY_MAP if normalize(k) in meta["prioridad_raw"]), "")

        lb     = find_logbook_file(project_dir)
        act60  = _count_entries(lb, d60, today)
        act30  = _count_entries(lb, d30, today)

        real_estado_key = compute_real_status(nominal_estado_key, act30 > 0, act60 > 0)
        is_passive      = nominal_estado_key == "inicial"
        real_prio_key   = compute_real_priority(nominal_prio_key, act30 > 0, 30, is_passive)

        if real_prio_key is None:
            real_prio_key = nominal_prio_key  # skip archiving logic here

        rows.append({
            "name":         project_dir.name,
            "proyecto_path": proyecto_path,
            "tipo":         meta.get("tipo", ""),
            "act60":        act60,
            "act30":        act30,
            "estado":       nominal_estado_key,
            "prioridad":    nominal_prio_key,
            "estado_new":   real_estado_key,
            "prioridad_new": real_prio_key,
            "changed":      (real_estado_key != nominal_estado_key or
                             real_prio_key   != nominal_prio_key),
        })

    if not rows:
        print("No hay proyectos activos.")
        return 0

    # ── Build table ───────────────────────────────────────────────────────────
    nw = max(len(r["name"])     for r in rows) + 1
    tw = max(len(r["tipo"])     for r in rows) + 1
    ew = max(len(r["estado"])   for r in rows) + 1
    pw = max(len(r["prioridad"]) for r in rows) + 1

    def row_str(r):
        if r["changed"]:
            arrow   = " →"
            e_new   = r["estado_new"]
            p_new   = r["prioridad_new"]
            e_flag  = " *" if r["estado_new"]   != r["estado"]   else "  "
            p_flag  = " *" if r["prioridad_new"] != r["prioridad"] else "  "
        else:
            arrow  = "  "
            e_new  = "="
            p_new  = "="
            e_flag = "  "
            p_flag = "  "
        return (
            f"{r['name']:<{nw}}  {r['act60']:>6}  {r['act30']:>6}  "
            f"{r['tipo']:<{tw}}  {r['estado']:<{ew}}  {r['prioridad']:<{pw}}"
            f" {arrow}  {e_new:<{ew}}{e_flag}  {p_new:<{pw}}{p_flag}"
        )

    header = (
        f"{'proyecto':<{nw}}  {'act-60':>6}  {'act-30':>6}  "
        f"{'tipo':<{tw}}  {'estado':<{ew}}  {'prioridad':<{pw}}"
        f"      {'estado*':<{ew}}    {'prioridad*':<{pw}}"
    )
    sep = "─" * len(header)

    n_changes = sum(1 for r in rows if r["changed"])
    title     = f"ESTADO DE PROYECTOS — {today.isoformat()}"

    lines = [title, "═" * len(header), "", header, sep]
    for r in rows:
        lines.append(row_str(r))
    lines += [
        sep,
        f"  {len(rows)} proyectos activos · {n_changes} con cambios propuestos",
    ]

    if apply and n_changes:
        for r in rows:
            if not r["changed"]:
                continue
            sk, pk = r["estado_new"], r["prioridad_new"]
            update_proyecto_field(
                r["proyecto_path"], "estado",
                f"{STATUS_MAP.get(sk, '')} {sk.capitalize()}")
            update_proyecto_field(
                r["proyecto_path"], "prioridad",
                f"{PRIORITY_MAP.get(pk, '')} {pk.capitalize()}")
        lines.append(f"  ✓ {n_changes} proyecto(s) actualizado(s)")
    elif n_changes:
        lines.append("  Ejecuta con --apply para aplicar los cambios.")

    text = "\n".join(lines)

    # ── Output ────────────────────────────────────────────────────────────────
    if open_after and not output:
        dest = STATUS_OUTPUT
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

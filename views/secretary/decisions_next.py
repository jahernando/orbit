"""views/secretary/decisions_next.py — pending tasks que tocan decidir
en los próximos N días.

Complementa la sección "Decidir hoy" de panel.md: hoy se ve lo que toca
ahora; este viewer adelanta lo que viene en el horizonte (defecto 7 días,
configurable vía `orbit.json::secretary.decisions_days`).

Modelo (mismo que `_collect_decidir_hoy` en panel.py, sólo cambia el
rango de fechas):
- pending tasks con campo ⏩ `ff` (forced/forecast date) seteado.
- Excluye `ff: someday` (parked) y tareas done/cancelled.
- Filtro de rango: `today < ff <= today + N` (estrictamente futuras, sin
  solaparse con "Decidir hoy" que captura `ff <= today`).

Tabla: ``| | ff | Tarea | Proyecto |`` (idéntica a la del panel para
"Decidir hoy", para consistencia visual). Marks:
- ``❗❗`` snooze ≥ 3
- ``💤N`` snooze count, ``❌N`` failed count

El link de proyecto apunta a ``<project>-agenda.md`` (no a project.md)
para poder ir directo a marcar pending/done desde la vista.

Viewer puro: lee agenda.md de los proyectos locales (federación
read-only no aparece aquí — el usuario no puede actuar sobre ellas
desde su propio orbit), escribe el .md, return.
"""

from datetime import date, timedelta
from pathlib import Path
from typing import Optional

from views import autogen_banner
from views.secretary import _load_secretary_config
from views.secretary._agenda_table import proj_link_md


def _collect_decisions_in_range(start_iso: str, end_iso: str) -> list:
    """Returns ``[(project_dir, task)]`` for pending tasks con ``start_iso <=
    ff <= end_iso``. Excluye ``ff: someday``. Sólo proyectos locales."""
    from core.config import iter_federated_project_dirs
    from core.project import _is_new_project
    from core.log import resolve_file
    from core.agenda.io import _read_agenda

    results = []
    for project_dir in iter_federated_project_dirs(False):
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
            if ff < start_iso or ff > end_iso:
                continue
            results.append((project_dir, t))

    results.sort(key=lambda r: r[1]["ff"])
    return results


def _render_decision_row(project_dir, t) -> str:
    """Markdown row con el mismo formato que panel.md `Decidir hoy`."""
    ff_val = t["ff"]
    snooze = t.get("snooze_count", 0) or 0
    mark = "❗❗ " if snooze >= 3 else ""
    extras = ""
    if snooze:
        extras += f" 💤{snooze}"
    failed = t.get("failed_count", 0) or 0
    if failed:
        extras += f" ❌{failed}"
    desc = (t.get("desc") or "").replace("|", "\\|")
    proj_md = proj_link_md(project_dir)
    return f"| ☐ | {ff_val} | {mark}{desc}{extras} | {proj_md} |"


def generate(out_path: Path, days: Optional[int] = None) -> None:
    """Escribe la vista de decisiones próximas en out_path."""
    from core.config import ORBIT_HOME

    if days is None:
        days = _load_secretary_config(ORBIT_HOME)["decisions_days"]

    today = date.today()
    start_iso = (today + timedelta(days=1)).isoformat()
    end_iso = (today + timedelta(days=days)).isoformat()
    decisions = _collect_decisions_in_range(start_iso, end_iso)

    lines = [
        autogen_banner("secretary.decisions_next").rstrip(),
        "",
        f"# 🤔 Decisiones próximas — {days} días",
        "",
    ]
    if not decisions:
        lines.append(f"*Sin decisiones pendientes en los próximos {days} días.*")
    else:
        lines.append("| | ff | Tarea | Proyecto |")
        lines.append("|---|----|------|----------|")
        for project_dir, t in decisions:
            lines.append(_render_decision_row(project_dir, t))

    out_path.write_text("\n".join(lines) + "\n")

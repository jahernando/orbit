"""views/secretary/cronos.py — tabla de cronogramas abiertos.

Reproduce la tabla `## 📊 Cronogramas` del antiguo `orbit panel` como
viewer dedicado del workspace dashboard. Columnas: Proyecto · Cronograma
· barra de progreso · done/total (pct%) · Deadline (con días restantes /
aviso de ritmo). Sólo cronogramas con tareas pendientes; los completos se
omiten.

Viewer puro: lee la verdad (los `cronos/crono-*.md` de cada proyecto),
escribe el `.md`, return.
"""

from datetime import date
from pathlib import Path


def generate(out_path: Path) -> None:
    """Escribe la tabla de cronogramas abiertos en out_path."""
    from core.panel import _collect_cronogramas
    from core.cronograma import _deadline_short_str
    from views import autogen_banner
    from views.secretary._agenda_table import proj_link_md

    lines = [autogen_banner("secretary.cronos").rstrip(), "",
             "# 📊 Cronogramas\n"]

    cronogramas = _collect_cronogramas()
    if not cronogramas:
        lines.append("(sin cronogramas abiertos)")
        out_path.write_text("\n".join(lines) + "\n")
        return

    today = date.today()
    lines.append("| Proyecto | Cronograma | Progreso |  | Deadline |")
    lines.append("|----------|------------|----------|---|----------|")
    for project_dir, crono_name, done, total, deadline in cronogramas:
        pct = done * 100 // total if total else 0
        filled = round(pct / 10)
        bar = "█" * filled + "░" * (10 - filled)
        proj = proj_link_md(project_dir)
        dl_str = _deadline_short_str(done, total, deadline, today)
        lines.append(
            f"| {proj} | {crono_name} | {bar} | {done}/{total} ({pct}%) "
            f"| {dl_str} |"
        )

    out_path.write_text("\n".join(lines) + "\n")

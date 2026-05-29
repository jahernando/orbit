"""views/secretary/logbook.py — entradas de logbook de hoy agrupadas por proyecto.

Recupera la sección "Actividad" del antiguo `orbit panel` como viewer
dedicado del workspace dashboard. Sólo entradas con fecha == hoy, agrupadas
por proyecto. Si ningún proyecto registró nada, "(sin actividad hoy)".

Viewer puro: lee la verdad (los `<project>-logbook.md`), escribe el `.md`,
return.
"""

from datetime import date
from pathlib import Path


def generate(out_path: Path) -> None:
    """Escribe el logbook diario en out_path."""
    from core.panel import _collect_activity
    from views import autogen_banner
    from views.secretary._agenda_table import proj_link_md

    today = date.today()
    lines = [autogen_banner("secretary.logbook").rstrip(), "",
             f"# 📓 Logbook — {today.isoformat()}\n"]

    activity = _collect_activity(today, today)
    if not activity:
        lines.append("(sin actividad hoy)")
        out_path.write_text("\n".join(lines) + "\n")
        return

    for project_dir, entries in activity:
        lines.append(f"**{proj_link_md(project_dir)}**")
        lines.append("")
        for e in entries:
            lines.append(f"- {e}")
        lines.append("")

    out_path.write_text("\n".join(lines) + "\n")

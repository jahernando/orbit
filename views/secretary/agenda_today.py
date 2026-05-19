"""views/secretary/agenda_today.py — agenda del día como tabla markdown.

Variante markdown nativa (Obsidian la renderiza directamente) de today.md.
Pineable como pestaña aparte para evitar buscar la sección dentro de
panel.md.

Estructura de la tabla (compartida con `agenda_next.py` vía `_agenda_table`):
emoji | Inicio | Fin | overlap | Descripción | Proyecto.

- Inicio/Fin: derivados con defaults (event 1h, task 15min) si falta tramo.
- Overlap: `░ ▒ ▓` según solapamiento (0 / 1 / 2+).
- Proyecto: markdown link a la `<project>-agenda.md`.
"""

from datetime import date as _date
from pathlib import Path

from views import autogen_banner
from views.secretary._agenda_table import collect_items_by_day, render_day_rows


def generate(out_path: Path) -> None:
    today = _date.today()
    by_day = collect_items_by_day(today, today, include_federated=True)
    items = by_day.get(today.isoformat(), [])

    lines = [
        autogen_banner("secretary.agenda_today").rstrip(),
        "",
        f"# 📅 Agenda — {today.isoformat()}",
        "",
    ]
    if not items:
        lines.append("*Sin citas para hoy.*")
    else:
        lines.extend(render_day_rows(items))

    out_path.write_text("\n".join(lines) + "\n")

"""views/secretary/agenda_next.py — viewer de la agenda próxima (n días).

Rolling window de los próximos N días (defecto 14, configurable vía
`orbit.json → secretary.agenda_days`). Una tabla por día con la misma
estructura que `agenda_today.md` (emoji | Inicio | Fin | overlap | Desc |
Proyecto), compartida vía `_agenda_table`.

Viewer puro: lee agenda.md de todos los proyectos del workspace,
escribe el .md, return.
"""

from datetime import date, timedelta
from pathlib import Path
from typing import Optional

from views import autogen_banner
from views.secretary import _load_secretary_config
from views.secretary._agenda_table import collect_items_by_day, render_day_rows


_WEEKDAYS_ES = ["lunes", "martes", "miércoles", "jueves", "viernes",
                "sábado", "domingo"]


def generate(out_path: Path, days: Optional[int] = None) -> None:
    """Escribe la agenda próxima (rolling `days` días) en out_path."""
    from core.config import ORBIT_HOME

    if days is None:
        days = _load_secretary_config(ORBIT_HOME)["agenda_days"]

    today = date.today()
    end = today + timedelta(days=days - 1)
    by_day = collect_items_by_day(today, end, include_federated=True)

    lines = [
        autogen_banner("secretary.agenda_next").rstrip(),
        "",
        f"# 📅 Agenda próxima — {days} días",
        "",
    ]

    if not by_day:
        lines.append("*Sin citas en los próximos {} días.*".format(days))
    else:
        for day_str in sorted(by_day.keys()):
            items = by_day[day_str]
            if not items:
                continue
            try:
                d = date.fromisoformat(day_str)
                wd = _WEEKDAYS_ES[d.weekday()]
                lines.append(f"## {day_str} · {wd}")
            except ValueError:
                lines.append(f"## {day_str}")
            lines.append("")
            lines.extend(render_day_rows(items))
            lines.append("")

    out_path.write_text("\n".join(lines) + "\n")

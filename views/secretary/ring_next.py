"""views/secretary/ring_next.py — alarmas próximas (toda la ventana del ring.json).

Análogo a `ring_today.py` pero cubre toda la ventana ya proyectada en
`ring.json` (`window_start..window_end`, defecto 7 días). No re-configura
la ventana: si el usuario quiere otra, ajusta `ring.days` en
`<workspace>/orbit.json`.

Agrupado por día-de-alarma (cuándo suena, no cuándo es la cita). Para
un item con alarma a varios días vista, aparece bajo el día en que
dispara — coherente con el propósito de diagnóstico "¿qué va a sonar
cuándo?".
"""

from datetime import date
from pathlib import Path

from views.secretary._ring_table import (
    build_project_index, header_lines, load_ring_json, render_rows, ring_dt,
)


_WEEKDAYS_ES = ["lunes", "martes", "miércoles", "jueves", "viernes",
                "sábado", "domingo"]


def generate(out_path: Path) -> None:
    from core.config import ORBIT_HOME
    payload = load_ring_json(ORBIT_HOME)

    if payload is None:
        from views import autogen_banner
        out_path.write_text(
            autogen_banner("secretary.ring_next")
            + "# 🔔 Alarmas próximas\n\n"
            "*Sin `ring.json` en este workspace. "
            "Crea una cita con `--ring` o lanza `orbit dash` para "
            "regenerarlo.*\n"
        )
        return

    today = date.today()
    items = payload.get("items", [])
    ring_dt_map = {}
    by_day: dict = {}
    for it in items:
        rd = ring_dt(it)
        if rd is None:
            continue
        ring_dt_map[id(it)] = rd
        if rd.date() < today:
            continue  # ring del pasado: ignorar
        by_day.setdefault(rd.date().isoformat(), []).append(it)

    lines = header_lines(payload, "secretary.ring_next")
    lines.append("# 🔔 Alarmas próximas")
    lines.append("")

    if not by_day:
        lines.append("*Sin alarmas programadas en la ventana.*")
    else:
        proj_index = build_project_index()
        for day_str in sorted(by_day.keys()):
            day_items = by_day[day_str]
            try:
                d = date.fromisoformat(day_str)
                wd = _WEEKDAYS_ES[d.weekday()]
                lines.append(f"## {day_str} · {wd}")
            except ValueError:
                lines.append(f"## {day_str}")
            lines.append("")
            lines.extend(render_rows(day_items, ring_dt_map, proj_index))
            lines.append("")

    out_path.write_text("\n".join(lines) + "\n")

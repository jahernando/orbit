"""views/ring/rings.py — alarmas hoy + próximas en un único fichero.

Fusiona lo que antes eran `ring_today.py` y `ring_next.py` en una sola
vista, paralela al `agenda.md` hot único: counter telegráfico arriba,
sección "Hoy" destacada, y sección "Próximos días" con sub-tablas por
día. Output a `📊panel/ring/rings.md`.

Filtro por **hora de alarma** (cuándo suena), no por hora de cita. Un
ring -1d de una cita de mañana cae en "Hoy" porque hoy es cuando salta.

Pasado: ignorado (no tiene sentido listar alarmas que ya sonaron). El
horizonte por arriba lo fija la ventana de `ring.json` (defecto 7d,
configurable en `<workspace>/orbit.json:ring.days`).
"""

from datetime import date
from pathlib import Path

from views.ring._ring_table import (
    build_project_index, header_lines, load_ring_json, render_rows, ring_dt,
)


_WEEKDAYS_ES = ["lunes", "martes", "miércoles", "jueves", "viernes",
                "sábado", "domingo"]


def _short_date_es(d: date) -> str:
    return f"{_WEEKDAYS_ES[d.weekday()]} {d.day:02d}/{d.month:02d}"


def _counter_line(n_today: int, n_next: int) -> str:
    """Counter telegráfico adaptativo. Si todo es 0 → mensaje placeholder."""
    if not n_today and not n_next:
        return "> 🔔 Sin alarmas programadas"
    parts = []
    if n_today:
        parts.append(f"🔔 Hoy: {n_today}")
    if n_next:
        parts.append(f"Próximos 7d: {n_next}")
    return "> " + " · ".join(parts)


def generate(out_path: Path) -> None:
    """Escribe `rings.md` — vista única hoy + próximos en out_path."""
    from core.config import ORBIT_HOME
    today = date.today()
    payload = load_ring_json(ORBIT_HOME)

    if payload is None:
        from views import autogen_banner
        out_path.write_text(
            autogen_banner("ring.rings")
            + "# 🔔 Alarmas\n\n"
            "*Sin `ring.json` en este workspace. "
            "Crea una cita con `--ring` o lanza `orbit dash` para "
            "regenerarlo.*\n"
        )
        return

    items = payload.get("items", [])
    ring_dt_map: dict = {}
    today_items: list = []
    by_day: dict = {}
    for it in items:
        rd = ring_dt(it)
        if rd is None:
            continue
        ring_dt_map[id(it)] = rd
        if rd.date() < today:
            continue                       # pasado: ignorar
        if rd.date() == today:
            today_items.append(it)
        else:
            by_day.setdefault(rd.date().isoformat(), []).append(it)

    lines = header_lines(payload, "ring.rings")
    lines.append("# 🔔 Alarmas")
    lines.append("")
    lines.append(_counter_line(len(today_items),
                               sum(len(v) for v in by_day.values())))
    lines.append("")
    lines.append(f"## 🔔 Hoy — {_short_date_es(today)}")
    lines.append("")

    if not today_items:
        lines.append("*Sin alarmas programadas para hoy.*")
        lines.append("")
    else:
        proj_index = build_project_index()
        lines.extend(render_rows(today_items, ring_dt_map, proj_index))
        lines.append("")

    if by_day:
        lines.append("## 🔔 Próximos días")
        lines.append("")
        proj_index = build_project_index()
        for day_str in sorted(by_day.keys()):
            day_items = by_day[day_str]
            try:
                d = date.fromisoformat(day_str)
                wd = _WEEKDAYS_ES[d.weekday()]
                lines.append(f"### {day_str} · {wd}")
            except ValueError:
                lines.append(f"### {day_str}")
            lines.append("")
            lines.extend(render_rows(day_items, ring_dt_map, proj_index))
            lines.append("")

    out_path.write_text("\n".join(lines) + "\n")

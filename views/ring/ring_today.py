"""views/ring/ring_today.py — alarmas que suenan hoy.

Viewer de diagnóstico: lee `<workspace>/.reminders/ring.json` y muestra
los items cuya **hora de alarma** (no de cita) cae hoy. Útil para
comparar contra lo que realmente suena en Reminders.app cuando hay
sospecha de drift.

Por qué se filtra por hora de alarma y no de cita: un item con
`alarm_minutes=1440` tiene su cita mañana pero suena hoy — debe aparecer
aquí. Recíprocamente, un item de hoy con alarma `-5m` aparecerá aquí
porque tanto la cita como el ring caen hoy.

Si `ring.json` no existe (workspace sin citas con `--ring` o ring
deshabilitado), el viewer escribe un .md informativo.
"""

from datetime import date
from pathlib import Path

from views.ring._ring_table import (
    build_project_index, header_lines, load_ring_json, render_rows, ring_dt,
)


def generate(out_path: Path) -> None:
    from core.config import ORBIT_HOME
    today = date.today()
    payload = load_ring_json(ORBIT_HOME)

    if payload is None:
        from views import autogen_banner
        out_path.write_text(
            autogen_banner("ring.today")
            + f"# 🔔 Alarmas — {today.isoformat()}\n\n"
            f"*Sin `ring.json` en este workspace. "
            f"Crea una cita con `--ring` o lanza `orbit dash` para "
            f"regenerarlo.*\n"
        )
        return

    items = payload.get("items", [])
    ring_dt_map = {}
    today_items = []
    for it in items:
        rd = ring_dt(it)
        if rd is None:
            continue
        ring_dt_map[id(it)] = rd
        if rd.date() == today:
            today_items.append(it)

    lines = header_lines(payload, "ring.today")
    lines.append(f"# 🔔 Alarmas — {today.isoformat()}")
    lines.append("")
    if not today_items:
        lines.append("*Sin alarmas programadas para hoy.*")
    else:
        lines.extend(render_rows(today_items, ring_dt_map,
                                 build_project_index()))

    out_path.write_text("\n".join(lines) + "\n")

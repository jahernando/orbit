"""views/secretary/report_summary.py — viewer del resumen de actividad.

Rolling window de los últimos N días (defecto 14, configurable vía
orbit.json → secretary.report_days). Llama a `core.stats.run_report`
con --summary (sin sección → logbook+agenda) e incluye federados.
Viewer puro: lee la verdad, escribe el .md, return.
"""

from contextlib import redirect_stdout
from datetime import date, timedelta
from io import StringIO
from pathlib import Path
from typing import Optional


def generate(out_path: Path, days: Optional[int] = None) -> None:
    """Escribe el report-summary (rolling `days` días) en out_path.

    Si `days` es None, lee el valor de orbit.json (defaults a 14).
    """
    from core.config import ORBIT_HOME
    from core.stats import run_report
    from views.secretary import _load_secretary_config

    if days is None:
        days = _load_secretary_config(ORBIT_HOME)["report_days"]

    today = date.today()
    start = today - timedelta(days=days - 1)
    buf = StringIO()
    with redirect_stdout(buf):
        run_report(
            date_from=start.isoformat(),
            date_to=today.isoformat(),
            summary="",
            include_federated=True,
        )
    out_path.write_text(buf.getvalue())

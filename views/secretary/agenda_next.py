"""views/secretary/agenda_next.py — viewer de la agenda próxima (n días).

Rolling window de los próximos N días (defecto 14, configurable vía
orbit.json → secretary.agenda_days). Viewer puro: lee citas del
workspace, escribe el .md, return.
"""

from contextlib import redirect_stdout
from datetime import date, timedelta
from io import StringIO
from pathlib import Path
from typing import Optional


def generate(out_path: Path, days: Optional[int] = None) -> None:
    """Escribe la agenda próxima (rolling `days` días) en out_path.

    Si `days` es None, lee el valor de orbit.json (defaults a 14).
    """
    from core.agenda_view import run_agenda
    from core.config import ORBIT_HOME
    from views.secretary import _load_secretary_config

    if days is None:
        days = _load_secretary_config(ORBIT_HOME)["agenda_days"]

    today = date.today()
    end = today + timedelta(days=days - 1)
    buf = StringIO()
    with redirect_stdout(buf):
        run_agenda(date_from=today.isoformat(), date_to=end.isoformat(),
                   markdown=True)
    out_path.write_text(buf.getvalue())

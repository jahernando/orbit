"""views/secretary/calendar.py — viewer del calendario (3 meses).

Mes actual + 2 meses por delante. Viewer puro: lee citas del workspace,
escribe el .md, return.
"""

import calendar as _calmod
from contextlib import redirect_stdout
from datetime import date
from io import StringIO
from pathlib import Path


def generate(out_path: Path) -> None:
    """Escribe el calendario (mes actual + 2 meses) en out_path."""
    from core.agenda_view import run_cal
    today = date.today()
    m1 = today.replace(day=1)
    m3_month = (m1.month + 2 - 1) % 12 + 1
    m3_year = m1.year + (m1.month + 2 - 1) // 12
    m3_end = date(m3_year, m3_month, _calmod.monthrange(m3_year, m3_month)[1])
    buf = StringIO()
    with redirect_stdout(buf):
        run_cal(date_from=m1.isoformat(), date_to=m3_end.isoformat(),
                markdown=True)
    out_path.write_text(buf.getvalue())

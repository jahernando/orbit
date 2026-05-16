"""views/secretary/agenda_next.py — viewer de la agenda próxima (n días).

Rolling window de ~14 días por defecto. Viewer puro: lee citas del
workspace, escribe el .md, return.
"""

from contextlib import redirect_stdout
from datetime import date, timedelta
from io import StringIO
from pathlib import Path


def generate(out_path: Path, days: int = 14) -> None:
    """Escribe la agenda próxima (rolling `days` días) en out_path."""
    from core.agenda_view import run_agenda
    today = date.today()
    end = today + timedelta(days=days - 1)
    buf = StringIO()
    with redirect_stdout(buf):
        run_agenda(date_from=today.isoformat(), date_to=end.isoformat(),
                   markdown=True)
    out_path.write_text(buf.getvalue())

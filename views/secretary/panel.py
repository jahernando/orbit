"""views/secretary/panel.py — viewer del panel del día.

Regenera la vista resumen del día (citas + actividad + prioridades de
proyectos) como markdown. Viewer puro: lee la verdad, escribe el .md,
return. Sin orquestación, sin daemons, sin side-effects fuera de su path.
"""

from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path


def generate(out_path: Path) -> None:
    """Escribe el panel del día en out_path."""
    from core.panel import run_panel
    buf = StringIO()
    with redirect_stdout(buf):
        run_panel(period="today")
    out_path.write_text(buf.getvalue())

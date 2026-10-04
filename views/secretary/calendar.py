"""views/secretary/calendar.py — viewer del calendario (3 meses).

Mes actual + 2 meses por delante, con la **carga** de cada día (nº de
citas) en gris, como el calendario de ``day fup`` (ADR-056), y los días
con hito subrayados. Viewer puro: lee citas del workspace, escribe el .md,
return.
"""

import calendar as _calmod
from datetime import date
from pathlib import Path

_MONTHS = ("", "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio",
           "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre")


def _months(today: date, n: int = 3) -> list:
    out = []
    y, m = today.year, today.month
    for _ in range(n):
        out.append((y, m))
        y, m = (y, m + 1) if m < 12 else (y + 1, 1)
    return out


def calendar_lines(dirs: list, today: date) -> list:
    from core import loadcal
    cal = _calmod.Calendar(firstweekday=0)
    months = [(y, m, cal.monthdatescalendar(y, m)) for y, m in _months(today)]
    days = sorted({d for _, _, weeks in months for w in weeks for d in w})
    loads = loadcal.day_loads(dirs, today, days)
    ms_days = loadcal.milestone_days(dirs, today, days)
    lines = [loadcal.md_legend(), ""]
    for y, m, weeks in months:
        lines.append(f"### {_MONTHS[m]} {y}")
        lines.append("")
        lines.extend(loadcal.render_md(loads, today, weeks, ms_days, month=m))
        lines.append("")
    return lines


def generate(out_path: Path) -> None:
    """Escribe el calendario de carga (mes actual + 2 meses) en out_path."""
    from core.triage import resolve_dirs
    from views import autogen_banner
    lines = calendar_lines(resolve_dirs(None), date.today())
    out_path.write_text(autogen_banner("secretary.calendar")
                        + "\n".join(lines) + "\n")

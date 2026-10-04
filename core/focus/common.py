"""core.focus.common — constantes, semana ISO y rutas de mission/notes."""
from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from typing import Optional
from core.project import _find_new_project


_MISSION_NAME = "mission"
_TEMPLATE_FILENAME = "focus-template.md"

_RAILS = ("anchor", "push", "joy")
_RAIL_EMOJI = {"anchor": "⚓", "push": "🔥", "joy": "🌿"}
_RAIL_LABEL = {"anchor": "Anchor", "push": "Push", "joy": "Joy"}
_DAYS = ("mon", "tue", "wed", "thu", "fri")
_DAY_LABEL = {"mon": "Lunes", "tue": "Martes", "wed": "Miércoles",
              "thu": "Jueves", "fri": "Viernes"}
_DAY_FROM_ES = {v.lower(): k for k, v in _DAY_LABEL.items()}



def _iso_week_label(d: date) -> str:
    """Return ``YYYY-WNN`` for the ISO week containing *d*."""
    y, w, _ = d.isocalendar()
    return f"{y}-W{w:02d}"


def _week_bounds(d: date) -> tuple[date, date]:
    """Return (monday, friday) of the ISO week containing *d*."""
    monday = d - timedelta(days=d.weekday())
    return monday, monday + timedelta(days=4)


def _resolve_mission_dir() -> Optional[Path]:
    """Locate the mission project in the current workspace. None if absent."""
    return _find_new_project(_MISSION_NAME)


def _week_file_path(mission_dir: Path, d: date) -> Path:
    """Return ``mission/notes/<YYYY-WNN>-focus.md`` for the week of *d*."""
    return mission_dir / "notes" / f"{_iso_week_label(d)}-focus.md"


def _template_path(mission_dir: Path) -> Path:
    return mission_dir / "notes" / _TEMPLATE_FILENAME

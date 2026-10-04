"""core.focus.week — Punto de entrada ``orbit focus week``."""
from __future__ import annotations

from datetime import date, timedelta
from core.focus.common import (
    _iso_week_label,
    _resolve_mission_dir,
    _week_file_path,
)
from core.focus.days import _is_day_only, _transplant_day_sheet
from core.focus.modes import (
    _menu_existing_week,
    _run_mode_libre,
    _run_mode_plantilla,
    _run_mode_repetir,
    _select_mode,
)
from core.focus.template import (
    _bootstrap_template_from_factory,
    _load_template,
)
from core.focus.weekfile import _regenerate_counter
from core.focus.year import _refresh_year_silent


# ── Public entry point ───────────────────────────────────────────────────

def run_focus_week(next_week: bool = False, review: bool = False) -> int:
    """Plan (or review) the focus blocks for the current or next ISO week.

    *next_week*: target ``today + 7d`` instead of today.
    *review*:    open the week file in ``$EDITOR`` and exit.

    Returns a CLI-style exit code.
    """
    mission_dir = _resolve_mission_dir()
    if mission_dir is None:
        print("⚠️  No existe el proyecto 'mission' en este workspace.")
        return 1

    target = date.today() + (timedelta(days=7) if next_week else timedelta())
    week_file = _week_file_path(mission_dir, target)

    if review:
        if not week_file.exists():
            print(f"⚠️  No hay archivo semanal para {_iso_week_label(target)}.")
            return 1
        import os
        os.system(f"$EDITOR '{week_file}'")
        return 0

    # Bootstrap or load the per-workspace template.
    template = _load_template(mission_dir)
    if template is None:
        template = _bootstrap_template_from_factory(mission_dir)

    # Hoja creada solo por `focus day`: se planifica como semana nueva y
    # luego se le devuelven sus días y su retrospectiva.
    day_only_text = None
    if week_file.exists():
        text = week_file.read_text()
        if not _is_day_only(text):
            return _menu_existing_week(week_file, mission_dir, template, target)
        day_only_text = text

    print(f"focus week — {_iso_week_label(target)}")
    mode = _select_mode(mission_dir, target)
    if mode is None:
        print("Cancelado.")
        return 1
    if mode == "libre":
        rc = _run_mode_libre(mission_dir, template, target, week_file)
    elif mode == "plantilla":
        rc = _run_mode_plantilla(mission_dir, template, target, week_file)
    elif mode == "repetir":
        rc = _run_mode_repetir(mission_dir, template, target, week_file)
    else:
        return 1
    if day_only_text is not None:
        if rc == 0 and week_file.read_text() != day_only_text:
            week_file.write_text(_transplant_day_sheet(day_only_text,
                                                       week_file.read_text()))
        elif rc != 0:
            week_file.write_text(day_only_text)
    if rc == 0 and week_file.exists():
        # Counter starts at 0/N by construction, but regenerate to keep the
        # single source of truth (avoids drift if the user did `task done`
        # on a block before this command finished).
        _regenerate_counter(week_file, mission_dir)
        _refresh_year_silent(mission_dir, target.year)
    return rc

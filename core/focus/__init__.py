"""core.focus — planificación semanal por carriles (anchor / push / joy).

Paquete (antes ``core/focus.py`` mono-fichero, ADR-038). El ``__init__``
re-exporta la API histórica para que ``from core.focus import …`` siga
funcionando. Submódulos, de base a cima (sin ciclos)::

    common → template, prompts → weekfile → days → hook, year → balance → modes → week, day, summary


Mission-specific por construcción en v1. Cada workspace declara su propia
plantilla en ``mission/notes/focus-template.md``; el archivo semanal vive
en ``mission/notes/<ISO-week>-focus.md`` y contiene IDs (``[orbit:…]``)
de las tasks-bloque, no wikilinks frágiles.

Bloque = task en ``mission/agenda.md`` con ``date`` + ``time HH:MM-HH:MM``
y wikilink al proyecto-carril en el título. Se crea vía
:func:`core.api.add_task` (capa pura que devuelve el dict con ``orbit_id``).

Formato del template (bullets, sin YAML — coherente con project.md)::

    # Focus · plantilla

    ## Carriles

    - Anchor: 2 proyectos × 2 bloques
    - Push:   1-2 proyectos × 1 bloque
    - Joy:    0-1 proyectos × 1 bloque

    ## Bloque

    - Duración: 90 min

    ## Theme days

    - Lunes: research
    - Martes: research
    - Miércoles: teaching
    - Jueves: gestion
    - Viernes: light
"""
from __future__ import annotations

from core.focus.common import (  # noqa: F401
    _DAYS,
    _DAY_FROM_ES,
    _DAY_LABEL,
    _MISSION_NAME,
    _RAILS,
    _RAIL_EMOJI,
    _RAIL_LABEL,
    _TEMPLATE_FILENAME,
    _iso_week_label,
    _resolve_mission_dir,
    _template_path,
    _week_bounds,
    _week_file_path,
)
from core.focus.template import (  # noqa: F401
    _DURATION_RE,
    _RAIL_RE,
    _THEME_RE,
    _bootstrap_template_from_factory,
    _format_template,
    _load_template,
    _parse_template,
    _write_template,
)
from core.focus.prompts import (  # noqa: F401
    _DAY_ES_SHORT,
    _ask_yn,
    _create_block,
    _create_blocks_for_project,
    _list_available_projects,
    _prompt_day,
    _prompt_time_range,
    _resolve_project_name,
)
from core.focus.weekfile import (  # noqa: F401
    _append_blocks_to_week_file,
    _BALANCE_DONE,
    _BALANCE_PENDING,
    _SYM_OPEN,
    _SYM_DONE,
    _SYM_DROP,
    _SYM_MISSING,
    _effective_status_index,
    _is_balanced,
    _parse_balance,
    _parse_block_states,
    _set_balance_line,
    _sync_block_symbols,
    _ORBIT_LINE_RE,
    _RAIL_FROM_EMOJI,
    _build_id_status_index,
    _build_id_task_index,
    _format_counter_section,
    _format_week_file,
    _parse_week_blocks_detailed,
    _parse_week_file,
    _regenerate_counter,
    _write_week_file,
)
from core.focus.year import (  # noqa: F401
    _STATUS_ICON,
    _collect_year,
    _format_year_file,
    _refresh_year_silent,
    _render_rail_cell,
    _week_dates_short,
    _weeks_in_iso_year,
    _year_file_path,
    _year_totals,
    run_focus_year,
)
from core.focus.days import (  # noqa: F401
    DAYS_SECTION,
    MAX_DAY_ITEMS,
    _balance_days,
    _day_header,
    _day_line,
    _find_day,
    _frozen_line_indices,
    _is_day_only,
    _minimal_sheet,
    _parse_days,
    _project_status_lookup,
    _transplant_day_sheet,
    _write_day,
)
from core.focus.hook import (  # noqa: F401
    _mark_in_sheet,
    mark_closed,
    suppressed,
)
from core.focus.balance import (  # noqa: F401
    _action_focus_balance,
    _balance_week,
    _drop_open_blocks,
    _pending_balances,
    _week_sunday,
    run_focus_balance,
)
from core.focus.modes import (  # noqa: F401
    _extract_w_minus_1_projects,
    _load_existing_state,
    _menu_existing_week,
    _prev_week_file,
    _prompt_project_with_default,
    _run_mode_libre,
    _run_mode_plantilla,
    _run_mode_repetir,
    _select_mode,
)
from core.focus.week import (  # noqa: F401
    run_focus_week,
)
from core.focus.day import (  # noqa: F401
    _collect_candidates,
    _project_candidates,
    run_focus_day,
)
from core.focus.summary import (  # noqa: F401
    level as _summary_level,
    render as _render_summary,
    run_focus_summary,
)
from core.focus.summary import _collect as _collect_summary  # noqa: F401

"""core.agenda — the agenda subsystem (task / milestone / event / reminder).

Split out of the historical ``core/agenda_cmds.py`` monolith in
Phase 3.C (ADR-031). The subpackage has six modules:

  * :mod:`core.agenda.recurrence` — recur grammar + ``_next_occurrence``.
  * :mod:`core.agenda.io`         — line parsers/formatters + read/write.
  * :mod:`core.agenda.display`    — selection helpers + event metadata.
  * :mod:`core.agenda.lifecycle`  — generic CRUD + ring hooks + validate.
  * :mod:`core.agenda.runners`    — public ``run_*`` entry points.
  * :mod:`core.agenda.startup`    — :func:`startup_advance_past_recurring`.

``core/agenda_cmds.py`` survives as a compatibility shim that re-exports
everything below; new code should import from ``core.agenda`` (or one of
its submodules) directly.
"""
from core.agenda.recurrence import (  # noqa: F401
    VALID_RECUR, _WEEKDAY_RRULE, _EVERY_RE, _POS_RE,
    _normalize_recur, is_valid_recur,
    _next_occurrence, _advance_to_today_or_future,
)
from core.agenda.io import (  # noqa: F401
    _TASK_HEADER, _MS_HEADER, _EV_HEADER, _REM_HEADER,
    _ORBIT_ID_RE, _DATE_RE, _RECUR_RE, _RING_RE, _TIME_RE,
    _DESC_STRIP_PATS, _DESC_STRIP_RE,
    _valid_date, _valid_time,
    _extract_orbit_id, _extract_recur, _extract_emoji_or_legacy, _clean_desc,
    _parse_simple_line, _format_simple_line,
    _parse_task_line, _format_task_line,
    _parse_event_line, _format_event_line,
    _parse_reminder_line, _format_reminder_line,
    _read_agenda, _write_agenda,
)
from core.agenda.display import (  # noqa: F401
    _AGENDA_NOTE_PREFIX, _ROOM_NOTE_PREFIX, _EMAIL_NOTE_PREFIX,
    _STRUCTURED_PREFIXES,
    _is_meeting_url, _room_icon,
    event_room_urls, event_agenda_urls, event_email_urls, event_indicators,
    _display_task, _display_event, _display_reminder,
    _select_from_list, _select_item, _select_event, _select_item_reminder,
)
from core.agenda.lifecycle import (  # noqa: F401
    _fed_tag, _prompt_ring, _prompt_and_validate_ring,
    _validate_add_params, _validate_edit_params,
    _TYPE_CONFIG, _resolve_project, _format_add_attrs,
    set_cloud_verified, _agenda_via_calendar,
    _schedule_ring_if_today, _delete_ring_if_today, _update_ring_on_edit,
    _sync_to_google,
    _ask_drop_confirmation, _ask_edit_occurrence_or_series,
    _advance_recurrence,
    _upsert_emoji_note, _apply_edits, _make_edit_occurrence,
    _generic_add, _generic_drop, _generic_edit, _generic_log,
    date_val_is_today,
)
from core.agenda.runners import (  # noqa: F401
    run_task_add, run_task_done, run_task_drop, run_task_edit,
    run_task_list, run_task_log,
    run_task_plan, run_task_pending,
    run_ms_add, run_ms_done, run_ms_drop, run_ms_edit,
    run_ms_list, run_ms_log,
    run_ev_add, run_ev_drop, run_ev_edit, run_ev_log, run_ev_list,
    run_reminder_add, run_reminder_drop, run_reminder_edit,
    run_reminder_list, run_reminder_log,
)
from core.agenda.startup import startup_advance_past_recurring  # noqa: F401

"""Subparsers for the four appointment kinds (task / ms / ev / reminder).

Each ``register_*(subparsers)`` adds one verb-cluster (with its
add/done/drop/edit/log sub-subparsers) to a top-level argparse
subparsers object. ``orbit.py::_build_parser`` calls them in the
original declaration order so ``orbit --help`` stays stable.
"""
from __future__ import annotations

from core.parsers._helpers import (
    _add_project_text, _add_add_args, _add_edit_args, _add_drop_args,
    _add_crono_subparsers,
)


def register_task(subparsers):
    """``orbit task {add,done,drop,edit,log,crono}``."""
    tsknew_p   = subparsers.add_parser("task", help="Task commands: add, done, cancel, edit, list")
    tsknew_sub = tsknew_p.add_subparsers(dest="action")

    tn_add = tsknew_sub.add_parser("add", help="Add a task")
    _add_project_text(tn_add, project_required=True)
    _add_add_args(tn_add)

    tn_done = tsknew_sub.add_parser("done", help="Complete a pending task")
    _add_project_text(tn_done, project_required=False)

    tn_drop = tsknew_sub.add_parser("drop", help="Cancel a pending task")
    _add_project_text(tn_drop, project_required=False)
    _add_drop_args(tn_drop)

    tn_edit = tsknew_sub.add_parser("edit", help="Edit a pending task")
    _add_project_text(tn_edit, project_required=False)
    _add_edit_args(tn_edit)

    tn_log = tsknew_sub.add_parser("log", help="Create logbook entry from a task")
    _add_project_text(tn_log, project_required=False)

    # composite task = cronograma. Decided 2026-05-15: cronograma is a
    # composite task. The flat `crono X` top-level remains as a daily-use
    # alias of `task crono X`.
    tn_crono = tsknew_sub.add_parser("crono",
                                     help="Composite task (cronograma): nested tasks with deps")
    _add_crono_subparsers(tn_crono.add_subparsers(dest="crono_action"))


def register_ms(subparsers):
    """``orbit ms {add,done,drop,edit,log}``."""
    ms_p   = subparsers.add_parser("ms", help="Milestone commands (agenda.md)")
    ms_sub = ms_p.add_subparsers(dest="action")

    ms_add = ms_sub.add_parser("add", help="Add a milestone")
    _add_project_text(ms_add, project_required=True)
    _add_add_args(ms_add)

    ms_done = ms_sub.add_parser("done", help="Mark milestone as reached")
    _add_project_text(ms_done, project_required=False)

    ms_drop = ms_sub.add_parser("drop", help="Cancel a milestone")
    _add_project_text(ms_drop, project_required=False)
    _add_drop_args(ms_drop)

    ms_edit = ms_sub.add_parser("edit", help="Edit a milestone")
    _add_project_text(ms_edit, project_required=False)
    _add_edit_args(ms_edit)

    ms_log = ms_sub.add_parser("log", help="Create logbook entry from a milestone")
    _add_project_text(ms_log, project_required=False)


def register_ev(subparsers):
    """``orbit ev {add,drop,edit,log}``."""
    ev_p   = subparsers.add_parser("ev", help="Event commands (agenda.md)")
    ev_sub = ev_p.add_subparsers(dest="action")

    ev_add = ev_sub.add_parser("add", help="Add an event")
    _add_project_text(ev_add, project_required=True)
    _add_add_args(ev_add, date_required=True)
    ev_add.add_argument("--end", "--end-date", default=None, help="End date YYYY-MM-DD")
    ev_add.add_argument("--end-time", default=None, dest="end_time", help="End time HH:MM")
    ev_add.add_argument("--agenda", default=None, metavar="URL",
                        help="Agenda/indico URL (📋 note under event)")
    ev_add.add_argument("--room", default=None, metavar="URL",
                        help="Room URL: zoom, meet, teams (🚪 note under event)")

    ev_drop = ev_sub.add_parser("drop", help="Remove an event")
    _add_project_text(ev_drop, project_required=False)
    _add_drop_args(ev_drop)

    ev_edit = ev_sub.add_parser("edit", help="Edit an event")
    _add_project_text(ev_edit, project_required=False)
    _add_edit_args(ev_edit, has_end=True, has_end_time=True)
    ev_edit.add_argument("--agenda", dest="new_agenda", default=None, metavar="URL|none",
                         help="New agenda URL (or 'none' to remove)")
    ev_edit.add_argument("--room", dest="new_room", default=None, metavar="URL|none",
                         help="New room URL (or 'none' to remove)")

    ev_log = ev_sub.add_parser("log", help="Create logbook entry from an event")
    _add_project_text(ev_log, project_required=False)


def register_reminder(subparsers):
    """``orbit reminder|rem {add,drop,edit,log}``."""
    rem_p   = subparsers.add_parser("reminder", aliases=["rem"], help="Reminder commands (agenda.md 💬)")
    rem_sub = rem_p.add_subparsers(dest="action")

    rem_add = rem_sub.add_parser("add", help="Add a reminder")
    _add_project_text(rem_add, project_required=True)
    _add_add_args(rem_add, date_required=True, time_required=True, has_ring=False)

    rem_drop = rem_sub.add_parser("drop", help="Remove a reminder")
    _add_project_text(rem_drop, project_required=False)
    _add_drop_args(rem_drop)

    rem_edit = rem_sub.add_parser("edit", help="Edit a reminder")
    _add_project_text(rem_edit, project_required=False)
    _add_edit_args(rem_edit)

    rem_log = rem_sub.add_parser("log", help="Create logbook entry from a reminder")
    _add_project_text(rem_log, project_required=False)

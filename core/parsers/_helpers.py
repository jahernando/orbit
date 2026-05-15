"""Argparse helpers reused across :mod:`core.parsers` modules."""
from __future__ import annotations

import argparse
import sys

from core.log import VALID_TYPES


class _OrbitParser(argparse.ArgumentParser):
    """ArgumentParser that shows a friendlier error message."""

    def error(self, message):
        # For invalid command choices, suggest closest match
        import re
        m = re.search(r"invalid choice: '(\w+)'", message)
        if m:
            from difflib import get_close_matches
            bad = m.group(1)
            choices_m = re.search(r"choose from (.+)\)", message)
            if choices_m:
                choices = [c.strip().strip("'") for c in choices_m.group(1).split(",")]
                close = get_close_matches(bad, choices, n=1, cutoff=0.5)
                if close:
                    sys.stderr.write(f"⚠️  Comando '{bad}' no reconocido. ¿Quisiste decir '{close[0]}'?\n")
                    sys.exit(2)
        sys.stderr.write(f"⚠️  No pude ejecutar el comando: {message}\n")
        self.print_usage(sys.stderr)
        sys.exit(2)

    def add_subparsers(self, **kwargs):
        kwargs.setdefault("parser_class", _OrbitParser)
        return super().add_subparsers(**kwargs)


# ── Argument-group helpers ──────────────────────────────────────────────

def _add_log_args(p):
    """``--log``, ``--log-entry``, ``--append``."""
    p.add_argument("--log", default=None, metavar="PROJECT",
                   help="Log output to a project's logbook (default: mission)")
    p.add_argument("--log-entry", dest="log_entry", default="apunte",
                   choices=VALID_TYPES, metavar="TYPE",
                   help="Entry type for --log (default: apunte)")
    p.add_argument("--append", dest="append_note", default=None, metavar="PROJ:NOTA",
                   help="Append output to a note (e.g. --append catedra:calibracion)")


def _add_project_text(p, project_required=True):
    """``project`` + ``text`` positional args."""
    if project_required:
        p.add_argument("project", help="Project name (partial match)")
    else:
        p.add_argument("project", nargs="?", default=None,
                       help="Project name (partial match; omit for interactive)")
    p.add_argument("text", nargs="?", default=None, help="Text or partial match")


def _add_add_args(p, date_required=False, time_required=False, has_ring=True):
    """``--date``, ``--recur``, ``--until``, ``--time``, ``--desc``, ``--ring``."""
    p.add_argument("--date", required=date_required, default=None, help="Date: YYYY-MM-DD, today, tomorrow...")
    p.add_argument("--recur", default=None, help="Recurrence: daily, weekly, monthly, weekdays, ...")
    p.add_argument("--until", default=None, help="End date for recurrence YYYY-MM-DD")
    p.add_argument("--time", required=time_required, default=None, help="Time HH:MM")
    p.add_argument("--desc", default=None, help="Description (links, notes)")
    if has_ring:
        p.add_argument("--ring", default=None, help="Reminder: 1d, 2h, HH:MM, YYYY-MM-DD HH:MM")


def _add_edit_args(p, has_end=False, has_end_time=False):
    """Common args for ``edit`` subcommands."""
    p.add_argument("--text", dest="new_text", default=None, help="New description")
    p.add_argument("--date", dest="new_date", default=None, help="New date (or 'none')")
    p.add_argument("--recur", dest="new_recur", default=None, help="New recurrence (or 'none')")
    p.add_argument("--until", dest="new_until", default=None, help="End date (or 'none')")
    p.add_argument("--ring", dest="new_ring", default=None, help="New ring (or 'none')")
    p.add_argument("--time", dest="new_time", default=None, help="New time HH:MM (or 'none')")
    p.add_argument("--desc", dest="new_desc", default=None, help="New description (or 'none')")
    if has_end:
        p.add_argument("--end", "--end-date", dest="new_end", default=None, help="End date or 'none'")
    if has_end_time:
        p.add_argument("--end-time", dest="new_end_time", default=None, help="End time HH:MM")
    p.add_argument("--force", action="store_true", help="Skip prompt; safe default = occurrence")
    p.add_argument("-o", dest="occurrence", action="store_true", help="Edit this occurrence only")
    p.add_argument("-s", dest="series", action="store_true", help="Edit the entire series")


def _add_drop_args(p):
    """``--force``, ``-o``, ``-s`` for drop subcommands."""
    p.add_argument("--force", action="store_true", help="Skip confirmation")
    p.add_argument("-o", dest="occurrence", action="store_true", help="Drop this occurrence only")
    p.add_argument("-s", dest="series", action="store_true", help="Drop the entire series")


def _add_crono_subparsers(sub):
    """Add the 9 crono subcommands to a parser's add_subparsers() object.

    Used twice: once under top-level ``crono`` and once under ``task crono``.
    The shared dispatcher reads either ``action`` or ``crono_action`` to find
    the chosen subcommand.
    """
    cr_add = sub.add_parser("add", help="Crear cronograma")
    cr_add.add_argument("project", help="Project name")
    cr_add.add_argument("name", help="Cronograma name")

    cr_show = sub.add_parser("show", help="Mostrar cronograma con fechas calculadas")
    cr_show.add_argument("project", help="Project name")
    cr_show.add_argument("name", help="Cronograma name (partial match)")
    cr_show.add_argument("--open", nargs="?", const=True, default=None, metavar="EDITOR")
    _add_log_args(cr_show)

    cr_check = sub.add_parser("check", help="Validar cronograma (doctor)")
    cr_check.add_argument("project", help="Project name")
    cr_check.add_argument("name", help="Cronograma name (partial match)")

    cr_list = sub.add_parser("list", help="Listar cronogramas del proyecto")
    cr_list.add_argument("project", help="Project name")
    cr_list.add_argument("--open", nargs="?", const=True, default=None, metavar="EDITOR")
    _add_log_args(cr_list)

    cr_edit = sub.add_parser("edit", help="Abrir cronograma en el editor")
    cr_edit.add_argument("project", help="Project name")
    cr_edit.add_argument("name", help="Cronograma name (partial match)")
    cr_edit.add_argument("--open", nargs="?", const=True, default=None, metavar="EDITOR",
                         help="Editor (default: configured editor)")

    cr_done = sub.add_parser("done", help="Marcar tarea de cronograma como completada")
    cr_done.add_argument("project", help="Project name")
    cr_done.add_argument("name", help="Cronograma name")
    cr_done.add_argument("index", nargs="?", default=None,
                         help="Task index, partial text, or omit for interactive")

    cr_reindex = sub.add_parser("reindex", help="Renumerar índices del cronograma")
    cr_reindex.add_argument("project", help="Project name")
    cr_reindex.add_argument("name", help="Cronograma name (partial match)")

    cr_gantt = sub.add_parser("gantt", help="Visualizar cronograma como Gantt")
    cr_gantt.add_argument("project", help="Project name")
    cr_gantt.add_argument("name", help="Cronograma name (partial match)")
    cr_gantt_mode = cr_gantt.add_mutually_exclusive_group()
    cr_gantt_mode.add_argument("--progress", action="store_true",
                               help="Forzar vista de progreso (barras + checkboxes)")
    cr_gantt_mode.add_argument("--timeline", action="store_true",
                               help="Forzar vista temporal (Gantt con eje de fechas)")
    cr_gantt.add_argument("--open", nargs="?", const=True, default=None, metavar="EDITOR")
    _add_log_args(cr_gantt)

    cr_mermaid = sub.add_parser("mermaid",
                                help="Embeber visualización (gantt/tabla) en el crono md")
    cr_mermaid.add_argument("project", help="Project name")
    cr_mermaid.add_argument("name", help="Cronograma name (partial match)")
    cr_mermaid.add_argument("--table", action="store_true",
                            help="Tabla markdown (renderer-agnóstico, sin Mermaid)")


def _add_fed_args(p):
    """``--no-fed`` to skip federated workspaces."""
    p.add_argument("--no-fed", action="store_true",
                   help="No incluir espacios federados")


def _add_output_args(p):
    """``--open [EDITOR]``."""
    p.add_argument("--open", nargs="?", const=True, default=None, metavar="EDITOR",
                   help="Open in editor (optionally specify editor name)")

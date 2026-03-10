#!/usr/bin/env python3
"""Orbit — personal project management CLI."""

import argparse
import sys
from pathlib import Path

from core.log import VALID_TYPES, add_entry, find_project, find_logbook_file, find_proyecto_file
from core.search import run_search
from core.stats import run_report
from core.project import (run_project_create, run_project_list,
                          run_project_status, run_project_edit, run_project_drop)
from core.importer import run_import
from core.open import open_file, capture_output, open_cmd_output, log_cmd_output, default_editor
from core.dateparse import parse_date
from core.agenda_cmds import (
    run_task_add, run_task_done, run_task_drop, run_task_edit, run_task_list,
    run_ms_add, run_ms_done, run_ms_drop, run_ms_edit, run_ms_list,
    run_ev_add, run_ev_drop, run_ev_edit, run_ev_list,
)
from core.highlights import (
    run_hl_add, run_hl_drop, run_hl_edit, run_hl_list, VALID_TYPES as HL_TYPES,
)
from core.project_view import run_new_view, run_new_open
from core.notes import run_note_create, run_note_list, run_note_drop
from core.commit import run_commit
from core.migrate import run_migrate, run_migrate_all
from core.agenda_view import run_agenda
from core.ls import run_ls_files, run_ls_notes
from core.gsync import run_gsync


def _d(expr):
    """Parse a natural language date expression, or return None if not provided."""
    return parse_date(expr) if expr else None


def _handle_output(args, run_fn, cmd_label: str = ""):
    """Run run_fn capturing output, then --open / --log / print as needed.

    run_fn is a zero-arg callable that prints to stdout.
    Returns exit code (int).
    """
    do_open = getattr(args, "open", False)
    log_target = getattr(args, "log", None)

    if do_open or log_target:
        with capture_output() as buf:
            run_fn()
        content = buf.getvalue()
        if do_open:
            open_cmd_output(content, getattr(args, "editor", None) or "")
        if log_target:
            entry_type = getattr(args, "log_entry", "apunte")
            log_cmd_output(content, log_target, entry_type, cmd_label)
        return 0
    else:
        run_fn()
        return 0


# Long options that users often type with a single dash (e.g. -date instead of --date)
_SINGLE_DASH_FIX = {
    "-date", "-time", "-recur", "-until", "-ring", "-entry", "-project", "-type", "-status",
    "-list-calendars", "-dry-run",
    "-priority", "-output", "-editor", "-from", "-to", "-limit",
    "-log", "-open", "-force", "-no-open",
    "-file", "-keyword", "-dry-run", "-name", "-date-from",
    "-date-to", "-notes", "-fix",
}

def _fix_argv(argv: list) -> list:
    """Convert single-dash long options to double-dash so argparse accepts them."""
    fixed = []
    for token in argv:
        if token in _SINGLE_DASH_FIX:
            fixed.append("-" + token)   # -date → --date
        else:
            fixed.append(token)
    return fixed


def cmd_log(args):
    if not args.project:
        print("Error: especifica un proyecto → orbit log <proyecto> \"mensaje\"")
        return 1
    rc = add_entry(
        project=args.project,
        message=args.message,
        tipo=args.entry,
        path=args.path,
        fecha=_d(args.date),
    )
    if rc == 0 and args.open:
        project_dir = find_project(args.project)
        if project_dir:
            logbook = find_logbook_file(project_dir)
            if logbook:
                open_file(logbook, args.editor)
    return rc


def cmd_search(args):
    fn = lambda: run_search(
        query=args.query,
        projects=args.project,
        tag=args.entry,
        date_filter=_d(args.date),
        date_from=_d(args.date_from),
        date_to=_d(args.date_to),
        any_mode=args.any,
        notes=getattr(args, "notes", False),
        limit=args.limit,
        open_after=args.open,
        editor=args.editor,
        in_filter=getattr(args, "in_filter", None),
    )
    return _handle_output(args, fn, "search")



def cmd_open(args):
    if getattr(args, "dir", False):
        from core.project_view import run_open_dir
        return run_open_dir(args.target)
    what = getattr(args, "what", None)
    return run_new_open(args.target, what=what,
                        editor=getattr(args, "editor", None) or default_editor())


def cmd_view_new(args):
    log_target = getattr(args, "log", None)
    if log_target:
        fn = lambda: run_new_view(project=getattr(args, "project", None),
                                  open_after=False, editor=default_editor())
        return _handle_output(args, fn, "view")
    return run_new_view(
        project    = getattr(args, "project", None),
        open_after = getattr(args, "open", False),
        editor     = getattr(args, "editor", None) or default_editor(),
    )






def cmd_hl(args):
    """Highlights subcommand dispatcher."""
    action = getattr(args, "action", None) or "list"

    if action == "add":
        return run_hl_add(
            project = args.project,
            text    = args.text,
            hl_type = args.type,
            link    = getattr(args, "link", None),
        )
    if action == "drop":
        return run_hl_drop(
            project = getattr(args, "project", None),
            text    = getattr(args, "text", None),
            hl_type = getattr(args, "type", None),
            force   = getattr(args, "force", False),
        )
    if action == "edit":
        return run_hl_edit(
            project  = getattr(args, "project", None),
            text     = getattr(args, "text", None),
            new_text = getattr(args, "new_text", None),
            new_link = getattr(args, "new_link", None),
            hl_type  = getattr(args, "type", None),
            editor   = getattr(args, "editor", None) or default_editor(),
        )
    return 1


def cmd_note(args):
    """Note subcommand dispatcher: note create/list/drop."""
    action = getattr(args, "action", None) or "create"
    if action == "list":
        fn = lambda: run_note_list(project=args.project)
        return _handle_output(args, fn, "note list")
    if action == "drop":
        return run_note_drop(project=args.project,
                             file_str=getattr(args, "file", None),
                             force=getattr(args, "force", False))
    # default: create
    return run_note_create(
        project   = args.project,
        title     = getattr(args, "title", "") or "",
        file_str  = getattr(args, "file", None),
        open_after= not getattr(args, "no_open", False),
        editor    = getattr(args, "editor", None) or default_editor(),
    )


def cmd_commit(args):
    return run_commit(message=getattr(args, "message", None))


def cmd_task_new(args):
    """New-model task subcommand dispatcher (task add/done/cancel/edit/list)."""
    action = getattr(args, "action", None) or "add"

    if action == "add":
        return run_task_add(
            project  = args.project,
            text     = args.text,
            date_val = _d(getattr(args, "date", None)),
            recur    = getattr(args, "recur", None),
            until    = _d(getattr(args, "until", None)),
            ring     = getattr(args, "ring", None),
        )
    if action == "done":
        return run_task_done(
            project = getattr(args, "project", None),
            text    = getattr(args, "text", None),
        )
    if action == "drop":
        return run_task_drop(
            project = getattr(args, "project", None),
            text    = getattr(args, "text", None),
            force   = getattr(args, "force", False),
        )
    if action == "edit":
        return run_task_edit(
            project   = getattr(args, "project", None),
            text      = getattr(args, "text", None),
            new_text  = getattr(args, "new_text", None),
            new_date  = _d(getattr(args, "new_date", None)) or getattr(args, "new_date", None),
            new_recur = getattr(args, "new_recur", None),
            new_until = _d(getattr(args, "new_until", None)) or getattr(args, "new_until", None),
            new_ring  = getattr(args, "new_ring", None),
        )
    return 1


def cmd_ms(args):
    """Milestone subcommand dispatcher."""
    action = getattr(args, "action", None) or "list"

    if action == "add":
        return run_ms_add(
            project  = args.project,
            text     = args.text,
            date_val = _d(getattr(args, "date", None)),
            recur    = getattr(args, "recur", None),
            until    = _d(getattr(args, "until", None)),
            ring     = getattr(args, "ring", None),
        )
    if action == "done":
        return run_ms_done(
            project = getattr(args, "project", None),
            text    = getattr(args, "text", None),
        )
    if action == "drop":
        return run_ms_drop(
            project = getattr(args, "project", None),
            text    = getattr(args, "text", None),
            force   = getattr(args, "force", False),
        )
    if action == "edit":
        return run_ms_edit(
            project   = getattr(args, "project", None),
            text      = getattr(args, "text", None),
            new_text  = getattr(args, "new_text", None),
            new_date  = _d(getattr(args, "new_date", None)) or getattr(args, "new_date", None),
            new_recur = getattr(args, "new_recur", None),
            new_until = _d(getattr(args, "new_until", None)) or getattr(args, "new_until", None),
            new_ring  = getattr(args, "new_ring", None),
        )
    return 1


def cmd_ev(args):
    """Event subcommand dispatcher."""
    action = getattr(args, "action", None) or "list"

    if action == "add":
        return run_ev_add(
            project  = args.project,
            text     = args.text,
            date_val = args.date,
            end_date = _d(getattr(args, "end", None)),
            recur    = getattr(args, "recur", None),
            until    = _d(getattr(args, "until", None)),
            ring     = getattr(args, "ring", None),
        )
    if action == "drop":
        return run_ev_drop(
            project = getattr(args, "project", None),
            text    = getattr(args, "text", None),
            force   = getattr(args, "force", False),
        )
    if action == "edit":
        return run_ev_edit(
            project   = getattr(args, "project", None),
            text      = getattr(args, "text", None),
            new_text  = getattr(args, "new_text", None),
            new_date  = _d(getattr(args, "new_date", None)) or getattr(args, "new_date", None),
            new_end   = _d(getattr(args, "new_end", None)) or getattr(args, "new_end", None),
            new_recur = getattr(args, "new_recur", None),
            new_until = _d(getattr(args, "new_until", None)) or getattr(args, "new_until", None),
            new_ring  = getattr(args, "new_ring", None),
        )
    if action == "list":
        return run_ev_list(
            project     = getattr(args, "project", None),
            period_from = _d(getattr(args, "from_date", None)),
            period_to   = _d(getattr(args, "to_date", None)),
        )
    return 1


from core.config import ORBIT_HOME as ORBIT_DIR


def cmd_project(args):
    sub = getattr(args, "sub", None)
    if sub == "create":
        return run_project_create(name=args.name, tipo=args.type,
                                  prioridad=args.priority)
    elif sub == "status":
        return run_project_status(name=args.name,
                                  set_status=getattr(args, "set", None))
    elif sub == "edit":
        return run_project_edit(name=args.name,
                                editor=getattr(args, "editor", None) or default_editor())
    elif sub == "drop":
        return run_project_drop(name=args.name,
                                force=getattr(args, "force", False))
    elif sub == "priority":
        from core.project import run_project_priority
        return run_project_priority(name=args.name,
                                     new_priority=args.priority)
    elif sub == "type":
        type_sub = getattr(args, "type_sub", None)
        if type_sub == "add":
            from core.config import run_type_add
            return run_type_add(name=args.name, emoji=args.emoji)
        elif type_sub == "drop":
            from core.config import run_type_drop
            return run_type_drop(name=args.name)
        else:
            from core.config import run_type_list
            return run_type_list()
    return 1


def cmd_import(args):
    return run_import(enex_path=args.file, project=args.project)


def cmd_migrate(args):
    dry_run = getattr(args, "dry_run", False)
    force   = getattr(args, "force",   False)
    name    = getattr(args, "name", None)
    if not name:
        print("Error: especifica un nombre de proyecto o 'all' para migrar todos.")
        print("  orbit migrate phd-martin [--dry-run]")
        print("  orbit migrate all        [--dry-run] [--force]")
        return 1
    if name == "all":
        return run_migrate_all(dry_run=dry_run, force=force)
    return run_migrate(name, dry_run=dry_run, force=force)


def cmd_help(args):
    import subprocess
    topic = getattr(args, "topic", None)
    editor = getattr(args, "editor", None) or default_editor()
    if topic in (None, "chuleta"):
        if topic is None:
            # Print in terminal (paged)
            try:
                text = (ORBIT_DIR / "CHULETA.md").read_text()
                pager = subprocess.Popen(["less", "-R"], stdin=subprocess.PIPE)
                pager.communicate(input=text.encode())
            except Exception:
                print((ORBIT_DIR / "CHULETA.md").read_text())
        else:
            open_file(ORBIT_DIR / "CHULETA.md", editor)
    elif topic == "tutorial":
        open_file(ORBIT_DIR / "TUTORIAL.md", editor)
    elif topic == "about":
        open_file(ORBIT_DIR / "README.md", editor)
    return 0





def cmd_agenda(args):
    to_file = getattr(args, "open", False) or getattr(args, "log", None)
    fn = lambda: run_agenda(
        projects=getattr(args, "projects", None) or None,
        date_str=_d(getattr(args, "date", None)),
        date_from=_d(getattr(args, "date_from", None)),
        date_to=_d(getattr(args, "date_to", None)),
        show_calendar=getattr(args, "calendar", False),
        markdown=bool(to_file),
    )
    return _handle_output(args, fn, "agenda")


def cmd_report(args):
    fn = lambda: run_report(
        projects=getattr(args, "projects", None) or None,
        date_str=_d(getattr(args, "date", None)),
        date_from=_d(getattr(args, "date_from", None)),
        date_to=_d(getattr(args, "date_to", None)),
    )
    return _handle_output(args, fn, "report")


def cmd_gsync(args):
    return run_gsync(
        dry_run=getattr(args, "dry_run", False),
        list_calendars=getattr(args, "list_calendars", False),
    )


def cmd_doctor(args):
    from core.doctor import run_doctor
    return run_doctor(
        project=getattr(args, "project", None),
        fix=getattr(args, "fix", False),
    )


def cmd_clean(args):
    from core.clean import run_clean
    return run_clean(
        project=getattr(args, "project", None),
        months=getattr(args, "months", 6),
        dry_run=getattr(args, "dry_run", False),
        force=getattr(args, "force", False),
        do_agenda=getattr(args, "agenda", False),
        do_logbook=getattr(args, "logbook", False),
        do_notes=getattr(args, "notes", False),
    )


def cmd_ls(args):
    """Unified ls command: ls [what] [project...] [--open] [--editor E]."""
    what = getattr(args, "what", None) or "projects"

    if what == "projects":
        fn = lambda: run_project_list(
            status_filter=getattr(args, "status", None),
            tipo_filter=getattr(args, "type", None),
            sort_by=getattr(args, "sort", None))
        return _handle_output(args, fn, "ls projects")

    if what == "tasks":
        fn = lambda: run_task_list(
            projects=getattr(args, "projects", None) or None,
            status_filter=getattr(args, "status", "pending"),
            date_filter=_d(getattr(args, "date", None)),
            dated_only=getattr(args, "dated", False))
        return _handle_output(args, fn, "ls tasks")

    if what == "ms":
        fn = lambda: run_ms_list(
            projects=getattr(args, "projects", None) or None,
            status_filter=getattr(args, "status", "pending"),
            dated_only=getattr(args, "dated", False))
        return _handle_output(args, fn, "ls ms")

    if what == "ev":
        fn = lambda: run_ev_list(
            project=getattr(args, "project_name", None),
            period_from=_d(getattr(args, "period_from", None)),
            period_to=_d(getattr(args, "period_to", None)))
        return _handle_output(args, fn, "ls ev")

    if what == "hl":
        fn = lambda: run_hl_list(
            project=getattr(args, "project_name", None),
            hl_type=getattr(args, "type", None))
        return _handle_output(args, fn, "ls hl")

    if what == "files":
        fn = lambda: run_ls_files(
            project=getattr(args, "project_name", None))
        return _handle_output(args, fn, "ls files")

    if what == "notes":
        fn = lambda: run_ls_notes(
            project=getattr(args, "project_name", None))
        return _handle_output(args, fn, "ls notes")

    # Fallback: treat 'what' as a project name → list logbook entries
    from core.list_entries import list_entries
    return list_entries(
        project=what,
        tipos=getattr(args, "type_filter", None),
        fecha=_d(getattr(args, "date", None)),
        output=None,
        period_from=_d(getattr(args, "period_from", None)),
        period_to=_d(getattr(args, "period_to", None)),
    )



def _add_log_args(p):
    """Add --log and --log-entry arguments to a parser."""
    p.add_argument("--log", default=None, metavar="PROJECT",
                   help="Log output to a project's logbook (default: mission)")
    p.add_argument("--log-entry", dest="log_entry", default="apunte",
                   choices=VALID_TYPES, metavar="TYPE",
                   help="Entry type for --log (default: apunte)")


class _OrbitParser(argparse.ArgumentParser):
    """ArgumentParser that shows a friendlier error message."""

    def error(self, message):
        sys.stderr.write(f"⚠️  No pude ejecutar el comando: {message}\n")
        self.print_usage(sys.stderr)
        sys.exit(2)

    def add_subparsers(self, **kwargs):
        kwargs.setdefault("parser_class", _OrbitParser)
        return super().add_subparsers(**kwargs)


def main():
    parser = _OrbitParser(prog="orbit", description="Orbit project management CLI")
    subparsers = parser.add_subparsers(dest="command")

    # --- log ---
    log_p = subparsers.add_parser("log", help="Add an entry to a project logbook")
    log_p.add_argument("project", help="Project name (partial match)")
    log_p.add_argument("message", help="Entry message")
    log_p.add_argument(
        "--entry",
        default="apunte",
        choices=VALID_TYPES,
        metavar="ENTRY",
        help=f"Entry type: {', '.join(VALID_TYPES)} (default: apunte)",
    )
    log_p.add_argument("--path", default=None, help="Optional file path — formats entry as a markdown link")
    log_p.add_argument("--date", default=None, help="Entry date YYYY-MM-DD (default: today)")
    log_p.add_argument("--open", action="store_true", help="Open the logbook in editor after logging")
    log_p.add_argument("--editor", default=None, help="Editor (env ORBIT_EDITOR, or system default)")

    # --- search ---
    search_p = subparsers.add_parser("search", help="Search across project logbooks and notes")
    search_p.add_argument("query", nargs="?", default="", help="Keywords to search (all entries if omitted)")
    search_p.add_argument("--project", nargs="+", metavar="P", default=None,
                          help="Project(s) to search in (partial match; default: all)")
    search_p.add_argument("--entry", default=None, choices=VALID_TYPES, metavar="ENTRY",
                          help=f"Filter logbook entries by type: {', '.join(VALID_TYPES)}")
    search_p.add_argument("--date", default=None, help="Filter by date: YYYY-MM-DD or YYYY-MM")
    search_p.add_argument("--from", dest="date_from", default=None, metavar="YYYY-MM-DD",
                          help="Filter entries from this date (inclusive)")
    search_p.add_argument("--to", dest="date_to", default=None, metavar="YYYY-MM-DD",
                          help="Filter entries up to this date (inclusive)")
    search_p.add_argument("--in", dest="in_filter", default=None,
                          choices=["logbook", "highlights", "agenda"],
                          help="Search in: logbook (default), highlights, or agenda")
    search_p.add_argument("--any", action="store_true",
                          help="OR logic: match any keyword (default: AND)")
    search_p.add_argument("--notes", action="store_true",
                          help="Also search inside notes/ files of each project")
    search_p.add_argument("--limit", type=int, default=0, metavar="N",
                          help="Maximum number of results (default: unlimited)")
    search_p.add_argument("--open", action="store_true",
                          help="Open results in editor")
    search_p.add_argument("--editor", default=None, help="Editor (env ORBIT_EDITOR, or system default)")
    _add_log_args(search_p)

    # --- ls (unified listing) ---
    ls_p   = subparsers.add_parser("ls", help="List projects, tasks, milestones, events, highlights, files, notes")
    ls_sub = ls_p.add_subparsers(dest="what")

    # ls projects (default when no subcommand)
    ls_proj = ls_sub.add_parser("projects", help="List projects with status")
    ls_proj.add_argument("--status", default=None, help="Filter: active, paused, sleeping")
    ls_proj.add_argument("--type",   default=None, help="Filter: investigacion, docencia, ...")
    ls_proj.add_argument("--sort",   default=None, choices=["type", "status", "priority"],
                         help="Sort by: type, status, priority")
    ls_proj.add_argument("--open",   action="store_true")
    ls_proj.add_argument("--editor", default=None)
    _add_log_args(ls_proj)

    # ls tasks [project...]
    ls_tasks = ls_sub.add_parser("tasks", help="List tasks")
    ls_tasks.add_argument("projects", nargs="*", default=None, help="Project(s)")
    ls_tasks.add_argument("--status", default="pending",
                          choices=["pending", "done", "cancelled", "all"])
    ls_tasks.add_argument("--date",   default=None, help="Filter by date")
    ls_tasks.add_argument("--dated",  action="store_true", help="Only show tasks with a date")
    ls_tasks.add_argument("--open",   action="store_true")
    ls_tasks.add_argument("--editor", default=None)
    _add_log_args(ls_tasks)

    # ls ms [project...]
    ls_ms = ls_sub.add_parser("ms", help="List milestones")
    ls_ms.add_argument("projects", nargs="*", default=None, help="Project(s)")
    ls_ms.add_argument("--status", default="pending",
                       choices=["pending", "done", "cancelled", "all"])
    ls_ms.add_argument("--dated",  action="store_true", help="Only show milestones with a date")
    ls_ms.add_argument("--open",   action="store_true")
    ls_ms.add_argument("--editor", default=None)
    _add_log_args(ls_ms)

    # ls ev [project]
    ls_ev = ls_sub.add_parser("ev", help="List events")
    ls_ev.add_argument("project_name", nargs="?", default=None, help="Project")
    ls_ev.add_argument("--from", dest="period_from", default=None, metavar="DATE")
    ls_ev.add_argument("--to",   dest="period_to",   default=None, metavar="DATE")
    ls_ev.add_argument("--open",   action="store_true")
    ls_ev.add_argument("--editor", default=None)
    _add_log_args(ls_ev)

    # ls hl [project]
    ls_hl = ls_sub.add_parser("hl", help="List highlights")
    ls_hl.add_argument("project_name", nargs="?", default=None, help="Project")
    ls_hl.add_argument("--type", default=None, choices=HL_TYPES, help="Section type")
    ls_hl.add_argument("--open",   action="store_true")
    ls_hl.add_argument("--editor", default=None)
    _add_log_args(ls_hl)

    # ls files [project]
    ls_files = ls_sub.add_parser("files", help="List project md files with git status")
    ls_files.add_argument("project_name", nargs="?", default=None, help="Project")
    ls_files.add_argument("--open",   action="store_true")
    ls_files.add_argument("--editor", default=None)
    _add_log_args(ls_files)

    # ls notes [project]
    ls_notes = ls_sub.add_parser("notes", help="List notes with git status")
    ls_notes.add_argument("project_name", nargs="?", default=None, help="Project")
    ls_notes.add_argument("--open",   action="store_true")
    ls_notes.add_argument("--editor", default=None)
    _add_log_args(ls_notes)

    # ls <project> — fallback: list logbook entries
    ls_p.add_argument("--type",        nargs="+", default=None, dest="type_filter",
                      metavar="TYPE", help="Filter by entry type(s)")
    ls_p.add_argument("--date",        default=None, help="Filter by date")
    ls_p.add_argument("--from",        dest="period_from", default=None, metavar="DATE")
    ls_p.add_argument("--to",          dest="period_to",   default=None, metavar="DATE")
    ls_p.add_argument("--open",        action="store_true")
    ls_p.add_argument("--editor",      default=None)
    _add_log_args(ls_p)

    shell_p = subparsers.add_parser("shell", help="Enter interactive Orbit shell")
    shell_p.add_argument("--editor", default=None, help="Editor (env ORBIT_EDITOR, or system default)")

    # --- open ---
    open_p = subparsers.add_parser("open", help="Open a project file in editor")
    open_p.add_argument("target", nargs="?", default=None,
                        help="Project name (partial match)")
    open_p.add_argument("what", nargs="?", default=None,
                        choices=["logbook", "highlights", "agenda", "notes", "project"],
                        help="Which file to open: project (default), logbook, highlights, agenda, notes")
    open_p.add_argument("--dir",      action="store_true",
                        help="Open the project directory in Finder")
    open_p.add_argument("--editor",   default=None,
                        help="Editor: typora, glow, code, or any command (env ORBIT_EDITOR)")

    # --- report ---
    rep_p = subparsers.add_parser("report", help="Activity report for projects in a time period")
    rep_p.add_argument("projects", nargs="*", default=None,
                       help="Project(s) (partial match; omit for all)")
    rep_p.add_argument("--date", default=None,
                       help="Date or month YYYY-MM-DD / YYYY-MM (default: last 30 days)")
    rep_p.add_argument("--from", dest="date_from", default=None, metavar="DATE",
                       help="Period start")
    rep_p.add_argument("--to", dest="date_to", default=None, metavar="DATE",
                       help="Period end")
    rep_p.add_argument("--open", action="store_true", help="Open in editor")
    rep_p.add_argument("--editor", default=None)
    _add_log_args(rep_p)

    # --- agenda ---
    ag_p = subparsers.add_parser("agenda",
                                  help="Show tasks, events and milestones for a day or period")
    ag_p.add_argument("projects", nargs="*", default=None,
                      help="Project(s) (partial match; omit for all)")
    ag_p.add_argument("--date", default=None, help="Date: YYYY-MM-DD, YYYY-MM, today, tomorrow...")
    ag_p.add_argument("--from", dest="date_from", default=None, metavar="DATE",
                      help="Period start")
    ag_p.add_argument("--to", dest="date_to", default=None, metavar="DATE",
                      help="Period end")
    ag_p.add_argument("--calendar", action="store_true",
                      help="Show calendar grid with colored markers (max 3 months)")
    ag_p.add_argument("--open",   action="store_true", help="Open in editor")
    ag_p.add_argument("--editor", default=None)
    _add_log_args(ag_p)

    # --- gsync ---
    gsync_p = subparsers.add_parser("gsync",
                                     help="Sync tasks/milestones/events to Google Tasks/Calendar")
    gsync_p.add_argument("--dry-run", action="store_true", dest="dry_run",
                         help="Preview sync without writing to Google")
    gsync_p.add_argument("--list-calendars", action="store_true", dest="list_calendars",
                         help="List available Google Calendars with IDs")

    # --- doctor ---
    doc_p = subparsers.add_parser("doctor",
                                   help="Check syntax of project files (logbook, agenda, highlights)")
    doc_p.add_argument("project", nargs="?", default=None,
                       help="Project name (omit for all)")
    doc_p.add_argument("--fix", action="store_true",
                       help="Offer to fix issues interactively")

    # --- clean ---
    clean_p = subparsers.add_parser("clean",
                                     help="Remove old entries, done tasks, past events, stale notes")
    clean_p.add_argument("project", nargs="?", default=None,
                         help="Project name (omit for all)")
    clean_p.add_argument("--months", type=int, default=6,
                         help="Age threshold in months (default: 6)")
    clean_p.add_argument("--dry-run", action="store_true", dest="dry_run",
                         help="Preview what would be removed without deleting")
    clean_p.add_argument("--force", action="store_true",
                         help="Skip all confirmations")
    clean_p.add_argument("--agenda", action="store_true",
                         help="Only clean done tasks/milestones and past events")
    clean_p.add_argument("--logbook", action="store_true",
                         help="Only clean old logbook entries")
    clean_p.add_argument("--notes", action="store_true",
                         help="Only clean stale notes")

    # --- task (add/done/cancel/edit/list on agenda.md) ---
    tsknew_p   = subparsers.add_parser("task", help="Task commands: add, done, cancel, edit, list")
    tsknew_sub = tsknew_p.add_subparsers(dest="action")

    def _task_project_text(p, project_required=True):
        if project_required:
            p.add_argument("project", help="Project name (partial match)")
        else:
            p.add_argument("project", nargs="?", default=None,
                           help="Project name (partial match; omit for interactive)")
        p.add_argument("text", nargs="?", default=None,
                       help="Task text or partial match for selection")

    tn_add = tsknew_sub.add_parser("add", help="Add a task")
    _task_project_text(tn_add, project_required=True)
    tn_add.add_argument("--date",  default=None, help="Due date YYYY-MM-DD")
    tn_add.add_argument("--recur", default=None,
                        help="Recurrence: daily, weekly, monthly, weekdays")
    tn_add.add_argument("--until", default=None,
                        help="End date for recurrence YYYY-MM-DD (requires --recur)")
    tn_add.add_argument("--ring",  default=None,
                        help="Reminder: 1d, 2h, or YYYY-MM-DD HH:MM")

    tn_done = tsknew_sub.add_parser("done", help="Complete a pending task")
    _task_project_text(tn_done, project_required=False)

    tn_drop = tsknew_sub.add_parser("drop", help="Cancel a pending task")
    _task_project_text(tn_drop, project_required=False)
    tn_drop.add_argument("--force", action="store_true", help="Skip confirmation")

    tn_edit = tsknew_sub.add_parser("edit", help="Edit a pending task")
    _task_project_text(tn_edit, project_required=False)
    tn_edit.add_argument("--text",  dest="new_text",  default=None, help="New description")
    tn_edit.add_argument("--date",  dest="new_date",  default=None, help="New date (or 'none')")
    tn_edit.add_argument("--recur", dest="new_recur", default=None,
                         help="New recurrence (or 'none')")
    tn_edit.add_argument("--until", dest="new_until", default=None,
                         help="New end date for recurrence (or 'none')")
    tn_edit.add_argument("--ring",  dest="new_ring",  default=None,
                         help="New ring value (or 'none')")

    # --- ms ---
    ms_p   = subparsers.add_parser("ms", help="Milestone commands (agenda.md)")
    ms_sub = ms_p.add_subparsers(dest="action")

    ms_add = ms_sub.add_parser("add", help="Add a milestone")
    ms_add.add_argument("project", help="Project name")
    ms_add.add_argument("text",    nargs="?", default=None, help="Milestone description")
    ms_add.add_argument("--date",  default=None, help="Target date YYYY-MM-DD")
    ms_add.add_argument("--recur", default=None, help="Recurrence: daily, weekly, monthly, every 2 weeks, ...")
    ms_add.add_argument("--until", default=None, help="End date for recurrence")
    ms_add.add_argument("--ring",  default=None, help="Reminder: HH:MM, 1d, 2h, YYYY-MM-DD HH:MM")

    ms_done = ms_sub.add_parser("done", help="Mark milestone as reached")
    ms_done.add_argument("project", nargs="?", default=None)
    ms_done.add_argument("text",    nargs="?", default=None)

    ms_drop = ms_sub.add_parser("drop", help="Cancel a milestone")
    ms_drop.add_argument("project", nargs="?", default=None)
    ms_drop.add_argument("text",    nargs="?", default=None)
    ms_drop.add_argument("--force", action="store_true", help="Skip confirmation")

    ms_edit = ms_sub.add_parser("edit", help="Edit a milestone")
    ms_edit.add_argument("project", nargs="?", default=None)
    ms_edit.add_argument("text",    nargs="?", default=None)
    ms_edit.add_argument("--text",  dest="new_text",  default=None)
    ms_edit.add_argument("--date",  dest="new_date",  default=None)
    ms_edit.add_argument("--recur", dest="new_recur", default=None, help="Recurrence (or 'none')")
    ms_edit.add_argument("--until", dest="new_until", default=None, help="End date for recurrence (or 'none')")
    ms_edit.add_argument("--ring",  dest="new_ring",  default=None, help="HH:MM, 1d, 2h, YYYY-MM-DD HH:MM, or none")

    # --- ev ---
    ev_p   = subparsers.add_parser("ev", help="Event commands (agenda.md)")
    ev_sub = ev_p.add_subparsers(dest="action")

    ev_add = ev_sub.add_parser("add", help="Add an event")
    ev_add.add_argument("project",  help="Project name")
    ev_add.add_argument("text",     nargs="?", default=None, help="Event description")
    ev_add.add_argument("--date",   required=True, help="Event date YYYY-MM-DD")
    ev_add.add_argument("--end",    default=None, help="End date YYYY-MM-DD (optional)")
    ev_add.add_argument("--recur",  default=None, help="Recurrence: daily, weekly, monthly, every 2 weeks, ...")
    ev_add.add_argument("--until",  default=None, help="End date for recurrence")
    ev_add.add_argument("--ring",   default=None, help="Reminder: HH:MM, 1d, 2h, YYYY-MM-DD HH:MM")

    ev_drop = ev_sub.add_parser("drop", help="Remove an event")
    ev_drop.add_argument("project", nargs="?", default=None)
    ev_drop.add_argument("text",    nargs="?", default=None)
    ev_drop.add_argument("--force", action="store_true", help="Skip confirmation")

    ev_edit = ev_sub.add_parser("edit", help="Edit an event")
    ev_edit.add_argument("project", nargs="?", default=None)
    ev_edit.add_argument("text",    nargs="?", default=None)
    ev_edit.add_argument("--text",  dest="new_text",  default=None)
    ev_edit.add_argument("--date",  dest="new_date",  default=None)
    ev_edit.add_argument("--end",   dest="new_end",   default=None, help="End date or 'none'")
    ev_edit.add_argument("--recur", dest="new_recur", default=None, help="Recurrence (or 'none')")
    ev_edit.add_argument("--until", dest="new_until", default=None, help="End date for recurrence (or 'none')")
    ev_edit.add_argument("--ring",  dest="new_ring",  default=None, help="HH:MM, 1d, 2h, YYYY-MM-DD HH:MM, or none")

    ev_list = ev_sub.add_parser("list", help="List events")
    ev_list.add_argument("project", nargs="?", default=None)
    ev_list.add_argument("--from",  dest="from_date", default=None)
    ev_list.add_argument("--to",    dest="to_date", default=None)

    # --- hl ---
    hl_p   = subparsers.add_parser("hl", help="Highlights commands (highlights.md)")
    hl_sub = hl_p.add_subparsers(dest="action")

    hl_add = hl_sub.add_parser("add", help="Add a highlight")
    hl_add.add_argument("project", help="Project name (partial match)")
    hl_add.add_argument("text",    help="Highlight text or title")
    hl_add.add_argument("--type",  required=True, choices=HL_TYPES,
                        help="Section type: refs, results, decisions, ideas, evals")
    hl_add.add_argument("--link",  default=None, help="URL or file path to link")

    hl_drop = hl_sub.add_parser("drop", help="Remove a highlight (interactive)")
    hl_drop.add_argument("project", nargs="?", default=None)
    hl_drop.add_argument("text",    nargs="?", default=None)
    hl_drop.add_argument("--force", action="store_true", help="Skip confirmation")
    hl_drop.add_argument("--type",  default=None, choices=HL_TYPES,
                         help="Restrict to section type")

    hl_edit = hl_sub.add_parser("edit", help="Edit a highlight")
    hl_edit.add_argument("project", nargs="?", default=None)
    hl_edit.add_argument("text",    nargs="?", default=None)
    hl_edit.add_argument("--type",   default=None, choices=HL_TYPES)
    hl_edit.add_argument("--text",   dest="new_text", default=None, help="New text/title")
    hl_edit.add_argument("--link",   dest="new_link", default=None,
                         help="New link (or 'none' to remove)")
    hl_edit.add_argument("--editor", default=None)

    # --- view (project summary) ---
    v2_p = subparsers.add_parser("view",
                                  help="Terminal summary of a project (or interactive picker)")
    v2_p.add_argument("project", nargs="?", default=None,
                      help="Project name (partial match; omit for interactive picker)")
    v2_p.add_argument("--open",   action="store_true",
                      help="Open summary as markdown in editor")
    v2_p.add_argument("--editor", default=None)
    _add_log_args(v2_p)

    # --- note (new-model notes/) ---
    note_p   = subparsers.add_parser("note", help="Note commands for new-model projects")
    note_sub = note_p.add_subparsers(dest="action")

    nt_create = note_sub.add_parser("create", help="Create or import a note")
    nt_create.add_argument("project", help="Project name (partial match)")
    nt_create.add_argument("title",   help="Note title")
    nt_create.add_argument("--file",    default=None,
                           help="Import an existing .md file instead of creating a new one")
    nt_create.add_argument("--no-open", action="store_true",
                           help="Do not open the note after creating")
    nt_create.add_argument("--editor",  default=None)

    nt_list = note_sub.add_parser("list", help="List notes with git status")
    nt_list.add_argument("project", help="Project name (partial match)")
    nt_list.add_argument("--open",   action="store_true", help="Open output in editor")
    nt_list.add_argument("--editor", default=None)
    _add_log_args(nt_list)

    nt_drop = note_sub.add_parser("drop", help="Delete a note (interactive)")
    nt_drop.add_argument("project", help="Project name (partial match)")
    nt_drop.add_argument("file",    nargs="?", default=None,
                         help="Filename or partial name (omit for interactive selection)")
    nt_drop.add_argument("--force", action="store_true", help="Skip confirmation")

    # Also accept:  note <project> <title>  (without 'create' subcommand)
    note_p.add_argument("project", nargs="?", default=None)
    note_p.add_argument("title",   nargs="?", default=None)
    note_p.add_argument("--file",    default=None)
    note_p.add_argument("--no-open", action="store_true")
    note_p.add_argument("--editor",  default=None)

    # --- commit ---
    cmt_p = subparsers.add_parser("commit", help="Git commit with confirmation")
    cmt_p.add_argument("message", nargs="?", default=None,
                       help="Commit message (prompted if omitted; auto-generated on empty input)")

    # --- project ---
    prj_p   = subparsers.add_parser("project", help="Manage projects (new model)")
    prj_sub = prj_p.add_subparsers(dest="sub")

    # project create
    prc_p = prj_sub.add_parser("create", help="Create a new project")
    prc_p.add_argument("name", help="Project name (e.g. my-project)")
    prc_p.add_argument("--type",     required=True,
                       help="Project type (see: orbit project type)")
    prc_p.add_argument("--priority", default="media",
                       help="Priority: alta, media, baja (default: media)")

    # project status
    prs_p = prj_sub.add_parser("status", help="Show or set project status")
    prs_p.add_argument("name", help="Project name (partial match)")
    prs_p.add_argument("--set", default=None, metavar="STATUS",
                       help="Declare status: active/activo, paused/pausado, sleeping/durmiendo, [auto]")

    # project edit
    pre_p = prj_sub.add_parser("edit", help="Open project.md in editor")
    pre_p.add_argument("name", help="Project name (partial match)")
    pre_p.add_argument("--editor", default=None, help="Editor (env ORBIT_EDITOR, or system default)")

    # project priority
    prp_p = prj_sub.add_parser("priority", help="Change project priority")
    prp_p.add_argument("name", help="Project name (partial match)")
    prp_p.add_argument("priority", choices=["alta", "media", "baja"],
                        help="New priority: alta, media, baja")

    # project drop
    prd_p = prj_sub.add_parser("drop", help="Drop a project (requires confirmation)")
    prd_p.add_argument("name", help="Project name (partial match)")
    prd_p.add_argument("--force", action="store_true",
                       help="Skip confirmation prompt")

    # project type
    prt_p = prj_sub.add_parser("type", help="Manage project types")
    prt_sub = prt_p.add_subparsers(dest="type_sub")
    prt_add = prt_sub.add_parser("add", help="Add a new project type")
    prt_add.add_argument("name",  help="Type name (e.g. viajes)")
    prt_add.add_argument("emoji", help="Emoji for the type (e.g. ✈️)")
    prt_drop = prt_sub.add_parser("drop", help="Remove a project type")
    prt_drop.add_argument("name", help="Type name to remove")

    # --- migrate ---
    mig_p = subparsers.add_parser("migrate",
                                  help="Migrate old-format projects to new format")
    mig_p.add_argument("name", nargs="?", default=None,
                        help="Project name (partial match), or 'all' to migrate everything")
    mig_p.add_argument("--dry-run", action="store_true", dest="dry_run",
                        help="Preview migration without writing files")
    mig_p.add_argument("--force",   action="store_true",
                        help="Skip confirmation prompt")

    # --- import ---
    imp_p = subparsers.add_parser("import", help="Import an Evernote .enex note into a project")
    imp_p.add_argument("--file",    required=True, help="Path to the .enex file")
    imp_p.add_argument("--project", required=True, help="Target project (partial name match)")

    # --- help ---
    hlp_p   = subparsers.add_parser("help", help="Show help: chuleta (default), tutorial, about")
    hlp_sub = hlp_p.add_subparsers(dest="topic")
    for _name, _help in [("chuleta",  "Open CHULETA.md in editor"),
                          ("tutorial", "Open TUTORIAL.md in editor"),
                          ("about",    "Open README.md in editor")]:
        _p = hlp_sub.add_parser(_name, help=_help)
        _p.add_argument("--editor", default=None)

    args = parser.parse_args(_fix_argv(sys.argv[1:]))

    # Simple commands: one function, no subcommand required
    _simple = {
        "task": cmd_task_new,
        "ms": cmd_ms, "ev": cmd_ev, "hl": cmd_hl,
        "view": cmd_view_new,
        "note": cmd_note, "commit": cmd_commit,
        "log": cmd_log, "search": cmd_search,
        "report": cmd_report, "open": cmd_open,
        "import": cmd_import,
        "project": cmd_project, "migrate": cmd_migrate,
        "ls": cmd_ls, "agenda": cmd_agenda, "gsync": cmd_gsync,
        "doctor": cmd_doctor, "clean": cmd_clean,
    }

    if args.command is None:
        run_shell()
    elif args.command in _simple:
        sys.exit(_simple[args.command](args))
    elif args.command == "shell":
        run_shell(editor=getattr(args, "editor", None) or default_editor())
    elif args.command == "help":
        sys.exit(cmd_help(args))
    else:
        parser.print_help()


def run_shell(editor: str = ""):
    from core.shell import run_shell as _run_shell
    _run_shell(editor)


if __name__ == "__main__":
    main()

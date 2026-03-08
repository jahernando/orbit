#!/usr/bin/env python3
"""Orbit — personal project management CLI."""

import argparse
import sys
from pathlib import Path

from core.log import VALID_TYPES, add_entry, find_project, find_logbook_file, find_proyecto_file
from core.search import run_search
from core.tasks import list_tasks
from core.stats import run_stats
from core.misionlog import add_entry_to_day, run_shell_startup
from core.project import run_project
from core.importer import run_import
from core.update import run_update
from core.task import run_task_open, run_task_schedule, run_task_close
from core.list_cmd import run_list_projects, run_list_section
from core.add import run_add
from core.view import run_view
from core.open import run_open, open_file
from core.calendar_sync import run_calendar_sync
from core.calendar_view import run_calendar_week, run_calendar_month, run_calendar_year
from core.dateparse import parse_date


def _d(expr):
    """Parse a natural language date expression, or return None if not provided."""
    return parse_date(expr) if expr else None


# Long options that users often type with a single dash (e.g. -date instead of --date)
_SINGLE_DASH_FIX = {
    "-date", "-time", "-recur", "-ring", "-entry", "-project", "-type", "-status",
    "-priority", "-output", "-editor", "-focus", "-from", "-to", "-limit",
    "-section", "-log", "-open", "-inject", "-apply", "-force", "-no-open",
    "-sync", "-url", "-file", "-keyword", "-dry-run", "-name", "-date-from",
    "-date-to", "-from-status", "-from-priority",
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
        return add_entry_to_day(
            message=args.message, tipo=args.entry, path=args.path,
            date_str=_d(args.date), open_after=args.open, editor=args.editor,
        )
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
    return run_search(
        query=args.query,
        projects=args.project,
        tag=args.entry,
        date_filter=_d(args.date),
        date_from=_d(args.date_from),
        date_to=_d(args.date_to),
        tipo=args.type,
        estado=args.status,
        prioridad=args.priority,
        any_mode=args.any,
        diario=args.diario,
        limit=args.limit,
        output=args.output,
        open_after=args.open,
        editor=args.editor,
    )


def cmd_tasks(args):
    return list_tasks(
        project=getattr(args, "project", None),
        tipo=getattr(args, "type", None),
        estado=getattr(args, "status", None),
        prioridad=getattr(args, "priority", None),
        fecha=_d(getattr(args, "date", None)),
        keyword=getattr(args, "keyword", None),
        output=getattr(args, "output", None),
        ring_only=getattr(args, "ring", False),
        open_after=getattr(args, "open", False),
        editor=getattr(args, "editor", "typora"),
    )




def cmd_create(args):
    if args.what == "project":
        return run_project(name=args.name, tipo=args.type, prioridad=args.priority)
    elif args.what == "import":
        return run_import(enex_path=args.file, project=args.project)
    return 1


def cmd_open(args):
    if args.terminal:
        return run_view(
            target=args.target, section=args.section,
            entrada=args.entry, log=args.log, output=args.output,
        )
    return run_open(target=args.target, log=args.log, editor=args.editor)


def cmd_view(args):
    return run_view(
        target=args.target,
        section=args.section,
        entrada=args.entrada,
        log=args.log,
        output=args.output,
    )


def cmd_change(args):
    target = args.target   # "task"
    action = args.action   # "schedule" or "close"

    if target == "task":
        if action == "schedule":
            rc = run_task_schedule(
                project=args.project, task_desc=args.desc,
                fecha=_d(args.date), time_str=getattr(args, "time", None),
                recur=getattr(args, "recur", None),
                interactive=True,
            )
        else:
            rc = run_task_close(
                project=args.project, task_desc=args.desc,
                fecha=_d(getattr(args, "date", None)),
                interactive=True,
            )
    else:
        return 1

    if rc == 0 and args.open and args.project:
        project_dir = find_project(args.project)
        if project_dir:
            proyecto = find_proyecto_file(project_dir)
            if proyecto:
                open_file(proyecto, args.editor)
    return rc


def _project_exists(name: str) -> bool:
    """Silent check: return True if any project dir matches name."""
    from core.log import PROJECTS_DIR
    if not PROJECTS_DIR.exists():
        return False
    return any(name.lower() in d.name.lower() for d in PROJECTS_DIR.iterdir() if d.is_dir())


def _resolve_add_project_title(args):
    """If project doesn't match any real project but title does, swap them."""
    project = args.project
    title   = args.title
    if project and not _project_exists(project):
        if _project_exists(title):
            project, title = title, project
        else:
            # Neither matches — treat project as part of title, use mission
            title   = f"{project} {title}"
            project = None
    return project, title


def cmd_add(args):
    if args.action == "task":
        project, title = _resolve_add_project_title(args)
        ring = getattr(args, "ring", False)
        time_str = getattr(args, "time", None)
        if ring and not time_str:
            try:
                raw = input("Hora del recordatorio (HH:MM) [09:00]: ").strip()
                time_str = raw if raw else "09:00"
            except (EOFError, KeyboardInterrupt):
                time_str = "09:00"
        fecha = _d(getattr(args, "date", None))
        if not fecha:
            from datetime import date as _date
            fecha = _date.today().isoformat()
        rc = run_task_open(
            project=project or "mission", task_desc=title,
            fecha=fecha,
            time_str=time_str,
            recur=getattr(args, "recur", None),
            ring=ring,
        )
        if rc == 0 and args.open and project:
            project_dir = find_project(project)
            if project_dir:
                proyecto = find_proyecto_file(project_dir)
                if proyecto:
                    open_file(proyecto, args.editor)
        return rc
    project, title = _resolve_add_project_title(args)
    return run_add(
        action=args.action,
        project=project or "mission",
        title=title,
        url=getattr(args, "url", None),
        file_str=getattr(args, "file", None),
        sync=getattr(args, "sync", False),
        date_str=_d(getattr(args, "date", None)),
        open_after=args.open,
        editor=args.editor,
    )


def cmd_calendar(args):
    editor     = getattr(args, "editor", "typora")
    open_after = not getattr(args, "no_open", False)
    date_str   = getattr(args, "date", None)
    if args.period == "week":
        return run_calendar_week(date_str=date_str, open_after=open_after, editor=editor)
    elif args.period == "month":
        return run_calendar_month(date_str=date_str, open_after=open_after, editor=editor)
    elif args.period == "year":
        return run_calendar_year(date_str=date_str, open_after=open_after, editor=editor)
    return 1


ORBIT_DIR = Path(__file__).parent

def cmd_info(args):
    editor = getattr(args, "editor", "typora")
    if args.topic == "chuleta":
        open_file(ORBIT_DIR / "CHULETA.md", editor)
    elif args.topic == "about":
        open_file(ORBIT_DIR / "README.md", editor)
    elif args.topic == "tutorial":
        open_file(ORBIT_DIR / "TUTORIAL.md", editor)
    elif args.topic == "help":
        # Re-invoke main with --help to print full help
        old_argv = sys.argv
        sys.argv = ["orbit", "--help"]
        try:
            main()
        except SystemExit:
            pass
        finally:
            sys.argv = old_argv
    return 0




def cmd_report(args):
    if args.period == "stats":
        return run_stats(date_str=_d(args.date), date_from=_d(args.date_from),
                         date_to=_d(args.date_to), project=args.project,
                         tipo=args.type, prioridad=args.priority,
                         output=args.output, open_after=args.open, editor=args.editor)
    return 1


def cmd_list(args):
    if args.what == "projects":
        return run_list_projects(
            tipo=args.type, status=args.status, priority=args.priority,
            output=args.output, open_after=args.open, editor=args.editor,
        )
    return run_list_section(
        project=getattr(args, "project", None), section=args.what,
        output=args.output, open_after=args.open, editor=args.editor,
    )



def main():
    parser = argparse.ArgumentParser(prog="orbit", description="Orbit project management CLI")
    subparsers = parser.add_subparsers(dest="command")

    # --- log ---
    log_p = subparsers.add_parser("log", help="Add an entry to a project logbook or today's diary")
    log_p.add_argument("project", nargs="?", default=None,
                       help="Project name (partial match); omit to log to today's diary")
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
    log_p.add_argument("--editor", default="typora", help="Editor to use (default: typora)")

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
    search_p.add_argument("--any", action="store_true",
                          help="OR logic: match any keyword (default: AND)")
    search_p.add_argument("--diario", action="store_true",
                          help="Also search in mision-log (diario, semanal, mensual)")
    search_p.add_argument("--limit", type=int, default=0, metavar="N",
                          help="Maximum number of results (default: unlimited)")
    search_p.add_argument("--type", default=None, help="Filter by project type (investigacion, docencia, ...)")
    search_p.add_argument("--status", default=None, help="Filter by project status (en marcha, parado, ...)")
    search_p.add_argument("--priority", default=None, help="Filter by project priority (alta, media, baja)")
    search_p.add_argument("--output", default=None, help="Save output to file")
    search_p.add_argument("--open", action="store_true",
                          help="Open results in editor (saves to mision-log/search.md)")
    search_p.add_argument("--editor", default="typora", help="Editor to use (default: typora)")

    # --- list ---
    list_p   = subparsers.add_parser("list", help="List projects or project sections")
    list_sub = list_p.add_subparsers(dest="what")

    # list projects
    lpr_p = list_sub.add_parser("projects", help="Table of all projects")
    lpr_p.add_argument("--type",     default=None, help="Filter by type (investigacion, docencia, ...)")
    lpr_p.add_argument("--status",   default=None, help="Filter by status (en marcha, parado, ...)")
    lpr_p.add_argument("--priority", default=None, help="Filter by priority (alta, media, baja)")
    lpr_p.add_argument("--output",   default=None, help="Save output to file")
    lpr_p.add_argument("--open",     action="store_true", help="Save to mision-log/projects.md and open")
    lpr_p.add_argument("--editor",   default="typora")

    # list tasks
    ltk_p = list_sub.add_parser("tasks", help="List pending tasks across projects")
    ltk_p.add_argument("--project",  default=None, help="Filter by project name (partial match)")
    ltk_p.add_argument("--type",     default=None, help="Filter by project type")
    ltk_p.add_argument("--status",   default=None, help="Filter by project status")
    ltk_p.add_argument("--priority", default=None, help="Filter by priority (alta, media, baja)")
    ltk_p.add_argument("--date",     default=None, help="Filter by due date — supports natural language")
    ltk_p.add_argument("--ring",     action="store_true", help="Show only tasks with @ring (reminders)")
    ltk_p.add_argument("--keyword",  default=None, help="Filter by keyword in description")
    ltk_p.add_argument("--output",   default=None, help="Save output to file")
    ltk_p.add_argument("--open",     action="store_true", help="Save to mision-log/tasks.md and open")
    ltk_p.add_argument("--editor",   default="typora")

    # list refs / results / decisions  (shared args)
    def _add_section_args(p, project_required=False):
        if project_required:
            p.add_argument("project", help="Project name (partial match)")
        else:
            p.add_argument("project", nargs="?", default=None,
                           help="Project name (partial match); omit for all projects")
        p.add_argument("--output", default=None, help="Save output to file")
        p.add_argument("--open",   action="store_true", help="Save and open in editor")
        p.add_argument("--editor", default="typora")


    subparsers.add_parser("shell", help="Enter interactive Orbit shell")

    # --- open ---
    open_p = subparsers.add_parser("open", help="Open or display a note / logbook")
    open_p.add_argument("target", nargs="?", default=None,
                        help="Project name, YYYY-MM-DD, YYYY-Wnn or YYYY-MM (default: today)")
    open_p.add_argument("--log",      action="store_true", help="Open logbook instead of project note")
    open_p.add_argument("--terminal", action="store_true", help="Print to terminal instead of opening editor")
    open_p.add_argument("--section",  default=None, help="(--terminal) Show only the section containing this word")
    open_p.add_argument("--entry",    default=None, metavar="ENTRY",
                        help=f"(--terminal) Filter logbook entries by type: {', '.join(VALID_TYPES)}")
    open_p.add_argument("--output",   default=None, help="(--terminal) Save output to file")
    open_p.add_argument("--editor",   default="typora",
                        help="Editor to use: typora (default), glow, code, or any command")

    # --- change (task/ring × schedule/close) ---
    chg_p   = subparsers.add_parser("change", help="Reschedule or close a task or reminder")
    chg_sub = chg_p.add_subparsers(dest="target")

    def _chg_common(p, *, needs_time=False, time_required=False):
        p.add_argument("project", help="Project name (partial match)")
        p.add_argument("desc",    help="Description to match (partial)")
        p.add_argument("--open",   action="store_true", help="Open proyecto.md in editor after change")
        p.add_argument("--editor", default="typora",    help="Editor to use (default: typora)")

    # change task
    ct_p   = chg_sub.add_parser("task", help="Reschedule or close a task")
    ct_sub = ct_p.add_subparsers(dest="action")

    cts_p = ct_sub.add_parser("schedule", help="Set or update due date of a task")
    cts_p.add_argument("project", help="Project name (partial match)")
    cts_p.add_argument("desc",    help="Task description to match (partial)")
    cts_p.add_argument("--date",  required=True, help="New due date — supports natural language")
    cts_p.add_argument("--time",  default=None, metavar="HH:MM", help="Optional due time")
    cts_p.add_argument("--recur", default=None, metavar="RULE",
                       help="Set or update recurrence rule")
    cts_p.add_argument("--open",   action="store_true")
    cts_p.add_argument("--editor", default="typora")

    ctc_p = ct_sub.add_parser("close", help="Mark a task as done (or advance if recurring)")
    ctc_p.add_argument("project", help="Project name (partial match)")
    ctc_p.add_argument("desc",    help="Task description to match (partial)")
    ctc_p.add_argument("--date",  default=None, help="Done date (default: today)")
    ctc_p.add_argument("--open",   action="store_true")
    ctc_p.add_argument("--editor", default="typora")

    # --- create ---
    cre_p   = subparsers.add_parser("create", help="Create a project, note or import")
    cre_sub = cre_p.add_subparsers(dest="what")

    # create project
    crp_p = cre_sub.add_parser("project", help="Create a new project from template")
    crp_p.add_argument("--name",     required=True, help="Project name (e.g. NEXT-GALA)")
    crp_p.add_argument("--type",     required=True,
                       help="Project type: investigacion, docencia, gestion, formacion, software, personal, mision")
    crp_p.add_argument("--priority", default="media", help="Initial priority: alta, media, baja (default: media)")

    # create import
    cri_p = cre_sub.add_parser("import", help="Import an Evernote .enex note into a project")
    cri_p.add_argument("--file",    required=True, help="Path to the .enex file")
    cri_p.add_argument("--project", required=True, help="Target project (partial name match)")


    # --- add ---
    add_p   = subparsers.add_parser("add", help="Add a ref, result, decision or reminder to a project")
    add_sub = add_p.add_subparsers(dest="action")

    def _add_common(p, *, has_file=False):
        p.add_argument("project", help="Project name (partial match)")
        p.add_argument("title",   help="Title / description")
        p.add_argument("--url",   default=None, help="URL to attach as a markdown link")
        if has_file:
            p.add_argument("--file", default=None, metavar="PATH",
                           help="Local file to copy into the project directory")
            p.add_argument("--sync", action="store_true",
                           help="Run git add -f on the copied file")
        p.add_argument("--open",   action="store_true", help="Open proyecto.md in editor after adding")
        p.add_argument("--editor", default="typora",    help="Editor to use (default: typora)")

    # add ref
    ar_p = add_sub.add_parser("ref", help="Add a key reference to a project")
    _add_common(ar_p, has_file=True)

    # add result
    ares_p = add_sub.add_parser("result", help="Add a result to a project")
    _add_common(ares_p, has_file=True)

    # add decision
    ad_p = add_sub.add_parser("decision", help="Add a decision to a project")
    _add_common(ad_p, has_file=True)

    # add task
    at_p = add_sub.add_parser("task", help="Add a task to a project")
    at_p.add_argument("project", nargs="?", default=None,
                      help="Project name (partial match; omit to add to today's daily note)")
    at_p.add_argument("title",   help="Task description")
    at_p.add_argument("--date",  default=None, metavar="DATE",
                      help="Due date — supports natural language")
    at_p.add_argument("--time",  default=None, metavar="HH:MM", help="Optional due time")
    at_p.add_argument("--ring",  action="store_true",
                      help="Add as a reminder (schedules in Reminders.app); prompts for time if omitted")
    at_p.add_argument("--recur", default=None, metavar="RULE",
                      help="Recurrence: daily/diario, weekly/semanal, monthly/mensual, "
                           "yearly/anual, weekdays/laborables, every:Nd, every:Nw")
    at_p.add_argument("--open",   action="store_true", help="Open the project note in editor after adding")
    at_p.add_argument("--editor", default="typora",    help="Editor to use (default: typora)")

    # --- report ---
    rep_p   = subparsers.add_parser("report", help="Generate reports: stats")
    rep_sub = rep_p.add_subparsers(dest="period")

    # report stats
    rs_p = rep_sub.add_parser("stats", help="Quantitative analytics across projects")
    rs_p.add_argument("--date", default=None, help="Month YYYY-MM (default: last 30 days) — supports natural language")
    rs_p.add_argument("--from", dest="date_from", default=None, metavar="DATE",
                      help="Period start — supports natural language")
    rs_p.add_argument("--to", dest="date_to", default=None, metavar="DATE",
                      help="Period end — supports natural language")
    rs_p.add_argument("--project", default=None, help="Filter by project name (partial match)")
    rs_p.add_argument("--type", default=None, help="Filter by project type (investigacion, docencia, ...)")
    rs_p.add_argument("--priority", default=None, help="Filter by priority (alta, media, baja)")
    rs_p.add_argument("--output", default=None, help="Save output to file")
    rs_p.add_argument("--open", action="store_true", help="Save to mision-log/stats.md and open in editor")
    rs_p.add_argument("--editor", default="typora", help="Editor to use (default: typora)")

    # --- calendar ---
    cal_p   = subparsers.add_parser("calendar", help="Show week / month / year calendar in Typora")
    cal_sub = cal_p.add_subparsers(dest="period")

    def _cal_args(p, date_help):
        p.add_argument("date",      nargs="?", default=None, help=date_help)
        p.add_argument("--no-open", action="store_true", help="Do not open in editor")
        p.add_argument("--editor",  default="typora")

    _cal_args(cal_sub.add_parser("week",  help="Weekly calendar with tasks"),
              "Week: 10, 2026-W10, or any date (default: current week)")
    _cal_args(cal_sub.add_parser("month", help="Monthly calendar grid with tasks"),
              "Month: enero, march, 3, 2026-03, or any date (default: current month)")
    _cal_args(cal_sub.add_parser("year",  help="Yearly overview with tasks"),
              "Year: 2026 or any date (default: current year)")

    # --- info ---
    info_p   = subparsers.add_parser("info", help="Show chuleta, README, tutorial or full help")
    info_sub = info_p.add_subparsers(dest="topic")
    for _name, _help in [("chuleta", "Open CHULETA.md in editor"),
                          ("about",   "Open README.md in editor"),
                          ("tutorial","Open TUTORIAL.md in editor"),
                          ("help",    "Show full orbit help")]:
        _p = info_sub.add_parser(_name, help=_help)
        _p.add_argument("--editor", default="typora")

    args = parser.parse_args(_fix_argv(sys.argv[1:]))

    if args.command is None:
        run_shell()
        return
    elif args.command == "add":
        if not args.action:
            add_p.print_help()
        else:
            sys.exit(cmd_add(args))
    elif args.command == "open":
        sys.exit(cmd_open(args))
    elif args.command == "list":
        if not args.what:
            list_p.print_help()
        elif args.what == "tasks":
            sys.exit(cmd_tasks(args))
        else:
            sys.exit(cmd_list(args))
    elif args.command == "report":
        if not args.period:
            rep_p.print_help()
        else:
            sys.exit(cmd_report(args))
    elif args.command == "change":
        if not args.target:
            chg_p.print_help()
        elif not getattr(args, "action", None):
            ct_p.print_help()
        else:
            sys.exit(cmd_change(args))
    elif args.command == "create":
        if not args.what:
            cre_p.print_help()
        else:
            sys.exit(cmd_create(args))
    elif args.command == "log":
        sys.exit(cmd_log(args))
    elif args.command == "search":
        sys.exit(cmd_search(args))
    elif args.command == "shell":
        run_shell()
    elif args.command == "calendar":
        if not args.period:
            cal_p.print_help()
        else:
            sys.exit(cmd_calendar(args))
    elif args.command == "info":
        if not args.topic:
            info_p.print_help()
        else:
            sys.exit(cmd_info(args))
    else:
        parser.print_help()


def run_shell():
    import readline
    import shlex

    # Enable persistent history
    history_file = Path.home() / ".orbit_history"
    try:
        readline.read_history_file(history_file)
    except FileNotFoundError:
        pass
    readline.set_history_length(500)

    COMMANDS = ["create", "add", "change", "list", "log", "search",
                "open", "report", "calendar", "info", "claude", "exit", "quit"]

    def completer(text, state):
        options = [c for c in COMMANDS if c.startswith(text)]
        return options[state] if state < len(options) else None

    readline.set_completer(completer)
    readline.parse_and_bind("tab: complete")

    print("¡Bienvenido a Orbit 🚀!")
    print()

    from core.misionlog import run_shell_startup
    run_shell_startup()

    while True:
        try:
            line = input("🚀 ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not line or line.startswith("#"):
            continue
        if line in ("exit", "quit", "q"):
            break
        if line == "claude":
            import subprocess
            subprocess.run(["claude"], cwd=Path(__file__).parent)
            continue

        try:
            tokens = shlex.split(line)
        except ValueError as e:
            print(f"Error al parsear: {e}")
            continue

        old_argv = sys.argv
        sys.argv  = ["orbit"] + tokens
        try:
            main()
        except SystemExit:
            pass
        finally:
            sys.argv = old_argv

    readline.write_history_file(history_file)

    from datetime import date as _date
    from core.misionlog import run_dayreport, run_weekreport
    from core.monthly import run_monthly

    today = _date.today()
    print()
    print("Generando reporte del día…")
    run_dayreport(date_str=None, inject=True, output=None, open_after=True)

    if today.weekday() in (4, 5, 6):  # viernes, sábado, domingo
        print("Generando reporte de la semana…")
        run_weekreport(date_str=None, inject=True, output=None, open_after=True)

    if today.day >= 28:
        print("Generando reporte del mes…")
        run_monthly(month=None, apply=False, inject=True, output=None, open_after=True)

    print()
    print("Aquí tienes el resumen de tu trabajo. ¡Hasta Pronto!")


if __name__ == "__main__":
    main()

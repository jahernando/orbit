#!/usr/bin/env python3
"""Orbit — personal project management CLI."""

import argparse
import sys

from core.log import VALID_TYPES, add_entry, find_project, find_logbook_file, find_proyecto_file
from core.search import run_search
from core.tasks import list_tasks
from core.activity import run_activity
from core.monthly import run_monthly
from core.misionlog import run_day, run_week, run_month, run_logday, run_dayreport, run_weekreport, add_entry_to_day
from core.project import run_project
from core.importer import run_import
from core.update import run_update
from core.task import run_task_open, run_task_schedule, run_task_close
from core.view import run_view
from core.open import run_open, open_file
from core.calendar_sync import run_calendar_sync


def cmd_log(args):
    if not args.project:
        return add_entry_to_day(
            message=args.message, tipo=args.type, path=args.path,
            date_str=args.date, open_after=args.open, editor=args.editor,
        )
    rc = add_entry(
        project=args.project,
        message=args.message,
        tipo=args.type,
        path=args.path,
        fecha=args.date,
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
        tag=args.tag,
        date_filter=args.date,
        tipo=args.type,
        estado=args.status,
        prioridad=args.priority,
        output=args.output,
        open_after=args.open,
        editor=args.editor,
    )


def cmd_tasks(args):
    return list_tasks(
        project=args.project,
        tipo=args.type,
        estado=args.status,
        prioridad=args.priority,
        fecha=args.date,
        keyword=args.keyword,
        output=args.output,
        open_after=args.open,
        editor=args.editor,
    )




def cmd_import(args):
    return run_import(enex_path=args.file, project=args.project)


def cmd_project(args):
    return run_project(name=args.name, tipo=args.type, prioridad=args.priority)


def cmd_update(args):
    return run_update(
        projects=args.project or [],
        status=args.status,
        priority=args.priority,
        tipo=args.type,
        from_status=args.from_status,
        from_priority=args.from_priority,
    )


def cmd_open(args):
    return run_open(target=args.target, log=args.log, editor=args.editor)


def cmd_view(args):
    return run_view(
        target=args.target,
        section=args.section,
        entrada=args.entrada,
        log=args.log,
        output=args.output,
    )


def cmd_task(args):
    if args.action == "open":
        rc = run_task_open(project=args.project, task_desc=args.task, fecha=args.date)
    elif args.action == "schedule":
        rc = run_task_schedule(project=args.project, task_desc=args.task, fecha=args.date)
    elif args.action == "close":
        rc = run_task_close(project=args.project, task_desc=args.task, fecha=args.date)
    else:
        return 1
    if rc == 0 and args.open and args.project:
        project_dir = find_project(args.project)
        if project_dir:
            proyecto = find_proyecto_file(project_dir)
            if proyecto:
                open_file(proyecto, args.editor)
    return rc


def cmd_calendar(args):
    return run_calendar_sync(date_str=args.date, dry_run=args.dry_run)




def cmd_report(args):
    if args.period == "day":
        return run_dayreport(date_str=args.date, inject=args.inject)
    elif args.period == "week":
        return run_weekreport(date_str=args.date, inject=args.inject)
    elif args.period == "month":
        return run_monthly(month=args.date, apply=args.apply, output=args.output)
    return 1


def cmd_logday(args):
    return run_logday(message=args.message, tipo=args.type, date_str=args.date,
                      open_after=args.open, editor=args.editor)


def cmd_day(args):
    return run_day(date_str=args.date, force=args.force, focus=args.focus,
                   open_after=not args.no_open, editor=args.editor)


def cmd_week(args):
    return run_week(date_str=args.date, force=args.force, focus=args.focus,
                    open_after=not args.no_open, editor=args.editor)


def cmd_month(args):
    return run_month(date_str=args.date, force=args.force, focus=args.focus,
                     open_after=not args.no_open, editor=args.editor)


def cmd_activity(args):
    period = args.period or []
    if len(period) > 2:
        print("Error: --period accepts at most 2 values (from to)")
        return 1
    desde = period[0] if len(period) >= 1 else None
    hasta = period[1] if len(period) == 2 else None
    return run_activity(
        project=args.project,
        tipo=args.type,
        prioridad=args.priority,
        desde=desde,
        hasta=hasta,
        apply=args.apply,
        output=args.output,
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
        "--type",
        default="apunte",
        choices=VALID_TYPES,
        metavar="TYPE",
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
    search_p.add_argument("--tag", default=None, choices=VALID_TYPES, metavar="TAG",
                          help=f"Filter logbook entries by tag: {', '.join(VALID_TYPES)}")
    search_p.add_argument("--date", default=None, help="Filter by date: YYYY-MM-DD or YYYY-MM")
    search_p.add_argument("--type", default=None, help="Filter by project type (investigacion, docencia, ...)")
    search_p.add_argument("--status", default=None, help="Filter by project status (en marcha, parado, ...)")
    search_p.add_argument("--priority", default=None, help="Filter by project priority (alta, media, baja)")
    search_p.add_argument("--output", default=None, help="Save output to file")
    search_p.add_argument("--open", action="store_true",
                          help="Open results in editor (saves to mision-log/search.md)")
    search_p.add_argument("--editor", default="typora", help="Editor to use (default: typora)")

    # --- tasks ---
    tasks_p = subparsers.add_parser("tasks", help="List pending tasks across projects")
    tasks_p.add_argument("--project", default=None, help="Filter by project name (partial match)")
    tasks_p.add_argument("--type", default=None, help="Filter by project type (investigacion, docencia, gestion, formacion)")
    tasks_p.add_argument("--status", default=None, help="Filter by project status (en marcha, parado, ...)")
    tasks_p.add_argument("--priority", default=None, help="Filter by priority (alta, media, baja)")
    tasks_p.add_argument("--date", default=None, help="Filter tasks by due date: YYYY-MM-DD or YYYY-MM")
    tasks_p.add_argument("--keyword", default=None, help="Filter tasks by keyword in description")
    tasks_p.add_argument("--output", default=None, help="Save output to file instead of terminal")
    tasks_p.add_argument("--open", action="store_true",
                         help="Open results in editor (saves to mision-log/tasks.md)")
    tasks_p.add_argument("--editor", default="typora", help="Editor to use (default: typora)")

    # --- import ---
    imp_p = subparsers.add_parser("import", help="Import an Evernote .enex note into a project")
    imp_p.add_argument("--file", required=True, help="Path to the .enex file")
    imp_p.add_argument("--project", required=True, help="Target project (partial name match)")

    # --- calendar ---
    cal_p = subparsers.add_parser("calendar", help="Sync Google Calendar events to project logbooks")
    cal_p.add_argument("--date", default=None, help="Date YYYY-MM-DD (default: today)")
    cal_p.add_argument("--dry-run", action="store_true", help="Preview without writing to logbooks")

    # --- open ---
    open_p = subparsers.add_parser("open", help="Open a note in an external editor or renderer")
    open_p.add_argument("target", nargs="?", default=None,
                        help="Project name, YYYY-MM-DD, YYYY-Wnn or YYYY-MM (default: today)")
    open_p.add_argument("--log", action="store_true", help="Open logbook instead of project note")
    open_p.add_argument("--editor", default="typora",
                        help="Editor to use: typora (default), glow, code, or any command")

    # --- view ---
    view_p = subparsers.add_parser("view", help="Display a note, logbook or mision-log file")
    view_p.add_argument("target", nargs="?", default=None, help="Project name, YYYY-MM-DD, YYYY-Wnn or YYYY-MM (default: today)")
    view_p.add_argument("--section", default=None, help="Show only the section whose heading contains this word")
    view_p.add_argument("--entrada", default=None, metavar="TIPO", help=f"Filter logbook entries by type: {', '.join(VALID_TYPES)}")
    view_p.add_argument("--log", action="store_true", help="Show logbook instead of project note")
    view_p.add_argument("--output", default=None, help="Save output to file")

    # --- task ---
    task_p = subparsers.add_parser("task", help="Open, schedule or close a task")
    task_p.add_argument("action", choices=["open", "schedule", "close"], help="Action: open | schedule | close")
    task_p.add_argument("project", nargs="?", default=None, help="Project name (partial match; omit to use daily note)")
    task_p.add_argument("task", help="Task description")
    task_p.add_argument("--date", default=None, help="Date YYYY-MM-DD (due date for open/schedule, done date for close)")
    task_p.add_argument("--open", action="store_true", help="Open the project note in editor after action")
    task_p.add_argument("--editor", default="typora", help="Editor to use (default: typora)")

    # --- update ---
    upd_p = subparsers.add_parser("update", help="Set status and/or priority on one or more projects")
    upd_p.add_argument("project", nargs="*", default=None, help="Project name(s) (partial match; omit to use filters)")
    upd_p.add_argument("--status", default=None, help="New status: inicial, en marcha, parado, esperando, durmiendo, completado")
    upd_p.add_argument("--priority", default=None, help="New priority: alta, media, baja")
    upd_p.add_argument("--type", default=None, help="Filter: project type (investigacion, docencia, ...)")
    upd_p.add_argument("--from-status", default=None, dest="from_status", help="Filter: only projects with this current status")
    upd_p.add_argument("--from-priority", default=None, dest="from_priority", help="Filter: only projects with this current priority")

    # --- project ---
    proj_p = subparsers.add_parser("project", help="Create a new project from template")
    proj_p.add_argument("--name", required=True, help="Project name (e.g. NEXT-GALA)")
    proj_p.add_argument("--type", required=True, help="Project type: investigacion, docencia, gestion, formacion, software, personal")
    proj_p.add_argument("--priority", default="media", help="Initial priority: alta, media, baja (default: media)")

    # --- report ---
    rep_p = subparsers.add_parser("report", help="Generate activity report for a day, week or month")
    rep_p.add_argument("period", choices=["day", "week", "month"], help="Report period")
    rep_p.add_argument("--date", default=None, help="Date: YYYY-MM-DD for day/week, YYYY-MM for month (default: today/current)")
    rep_p.add_argument("--inject", action="store_true", help="Inject report into the log file (day/week)")
    rep_p.add_argument("--apply", action="store_true", help="Apply computed status/priority changes to proyecto.md (month)")
    rep_p.add_argument("--output", default=None, help="Save output to file (month)")

    # --- logday ---
    logday_p = subparsers.add_parser("logday", help="Add a note to today's daily log")
    logday_p.add_argument("message", help="Note text")
    logday_p.add_argument(
        "--type",
        default="apunte",
        choices=VALID_TYPES,
        metavar="TYPE",
        help=f"Entry type: {', '.join(VALID_TYPES)} (default: apunte)",
    )
    logday_p.add_argument("--date", default=None, help="Target date YYYY-MM-DD (default: today)")
    logday_p.add_argument("--open", action="store_true", help="Open the daily note in editor after logging")
    logday_p.add_argument("--editor", default="typora", help="Editor to use (default: typora)")

    # --- day ---
    day_p = subparsers.add_parser("day", help="Create daily log file in ☀️mision-log/diario/")
    day_p.add_argument("--date", default=None, help="Target date YYYY-MM-DD (default: today)")
    day_p.add_argument("--force", action="store_true", help="Overwrite if file already exists")
    day_p.add_argument("--focus", nargs="+", metavar="PROJECT", default=None, help="Focus project (partial name)")
    day_p.add_argument("--no-open", action="store_true", help="Do not open the note after creating")
    day_p.add_argument("--editor", default="typora", help="Editor to use (default: typora)")

    # --- week ---
    week_p = subparsers.add_parser("week", help="Create weekly log file in ☀️mision-log/semanal/")
    week_p.add_argument("--date", default=None, help="Any date in the target week YYYY-MM-DD (default: today)")
    week_p.add_argument("--force", action="store_true", help="Overwrite if file already exists")
    week_p.add_argument("--focus", nargs="+", metavar="PROJECT", default=None, help="Up to 2 focus projects (partial name)")
    week_p.add_argument("--no-open", action="store_true", help="Do not open the note after creating")
    week_p.add_argument("--editor", default="typora", help="Editor to use (default: typora)")

    # --- month ---
    month_p = subparsers.add_parser("month", help="Create monthly log file in ☀️mision-log/mensual/")
    month_p.add_argument("--date", default=None, help="Target month YYYY-MM (default: current month)")
    month_p.add_argument("--force", action="store_true", help="Overwrite if file already exists")
    month_p.add_argument("--focus", nargs="+", metavar="PROJECT", default=None, help="Up to 3 focus projects (partial name)")
    month_p.add_argument("--no-open", action="store_true", help="Do not open the note after creating")
    month_p.add_argument("--editor", default="typora", help="Editor to use (default: typora)")

    # --- activity ---
    act_p = subparsers.add_parser("activity", help="Project activity report with real status/priority")
    act_p.add_argument("--project", default=None, help="Filter by project name (partial match)")
    act_p.add_argument("--type", default=None, help="Filter by project type")
    act_p.add_argument("--priority", default=None, help="Filter by priority (alta, media, baja)")
    act_p.add_argument("--period", nargs="+", metavar="DATE", default=None,
                       help="Period: one value (YYYY-MM or YYYY-MM-DD) or two values (from to)")
    act_p.add_argument("--apply", action="store_true", help="Apply computed status/priority changes to proyecto.md")
    act_p.add_argument("--output", default=None, help="Save output to file instead of terminal")

    args = parser.parse_args()

    if args.command == "open":
        sys.exit(cmd_open(args))
    elif args.command == "logday":
        sys.exit(cmd_logday(args))
    elif args.command == "report":
        sys.exit(cmd_report(args))
    elif args.command == "calendar":
        sys.exit(cmd_calendar(args))
    elif args.command == "view":
        sys.exit(cmd_view(args))
    elif args.command == "task":
        sys.exit(cmd_task(args))
    elif args.command == "update":
        sys.exit(cmd_update(args))
    elif args.command == "import":
        sys.exit(cmd_import(args))
    elif args.command == "project":
        sys.exit(cmd_project(args))
    elif args.command == "day":
        sys.exit(cmd_day(args))
    elif args.command == "week":
        sys.exit(cmd_week(args))
    elif args.command == "month":
        sys.exit(cmd_month(args))
    elif args.command == "log":
        sys.exit(cmd_log(args))
    elif args.command == "search":
        sys.exit(cmd_search(args))
    elif args.command == "tasks":
        sys.exit(cmd_tasks(args))
    elif args.command == "activity":
        sys.exit(cmd_activity(args))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()

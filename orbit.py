#!/usr/bin/env python3
"""Orbit — personal project management CLI."""

import argparse
import sys

from core.log import VALID_TYPES, add_entry
from core.list_entries import list_entries
from core.tasks import list_tasks
from core.activity import run_activity
from core.monthly import run_monthly
from core.misionlog import run_day, run_week, run_month, run_logday, run_dayreport, run_weekreport
from core.project import run_project
from core.importer import run_import
from core.update import run_update
from core.done import run_done


def cmd_log(args):
    return add_entry(
        project=args.project,
        message=args.message,
        tipo=args.type,
        path=args.path,
        fecha=args.date,
    )


def cmd_list(args):
    return list_entries(
        project=args.project,
        tipos=args.type,
        fecha=args.date,
        output=args.output,
    )


def cmd_tasks(args):
    return list_tasks(
        project=args.project,
        tipo=args.type,
        estado=args.status,
        prioridad=args.priority,
        fecha=args.date,
        output=args.output,
    )


def cmd_monthreport(args):
    return run_monthly(
        month=args.month,
        apply=args.apply,
        output=args.output,
    )


def cmd_import(args):
    return run_import(enex_path=args.file, project=args.project)


def cmd_project(args):
    return run_project(name=args.name, tipo=args.type, prioridad=args.priority)


def cmd_update(args):
    return run_update(project=args.project, status=args.status, priority=args.priority)


def cmd_done(args):
    return run_done(project=args.project, task_desc=args.task, done_date=args.date)


def cmd_setpriority(args):
    errors = 0
    for project in args.projects:
        result = run_update(project=project, status=None, priority=args.priority)
        if result != 0:
            errors += 1
    return 1 if errors else 0


def cmd_report(args):
    if args.period == "day":
        return run_dayreport(date_str=args.date, inject=args.inject)
    elif args.period == "week":
        return run_weekreport(date_str=args.date, inject=args.inject)
    elif args.period == "month":
        return run_monthly(month=args.date, apply=False, output=args.output)
    return 1


def cmd_logday(args):
    return run_logday(message=args.message, tipo=args.type, date_str=args.date)


def cmd_day(args):
    return run_day(date_str=args.date, copy=args.copy, force=args.force, focus=args.focus)


def cmd_week(args):
    return run_week(date_str=args.date, copy=args.copy, force=args.force, focus=args.focus)


def cmd_month(args):
    return run_month(date_str=args.date, copy=args.copy, force=args.force, focus=args.focus)


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
    log_p = subparsers.add_parser("log", help="Add an entry to a project logbook")
    log_p.add_argument("project", help="Project name (partial match supported)")
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

    # --- list ---
    list_p = subparsers.add_parser("list", help="List logbook entries with optional filters")
    list_p.add_argument("project", help="Project name (partial match supported)")
    list_p.add_argument(
        "--type",
        nargs="+",
        choices=VALID_TYPES,
        metavar="TYPE",
        help=f"Filter by type (one or more): {', '.join(VALID_TYPES)}",
    )
    list_p.add_argument("--date", default=None, help="Filter by date: YYYY-MM-DD or YYYY-MM")
    list_p.add_argument("--output", default=None, help="Save output to file instead of terminal")

    # --- tasks ---
    tasks_p = subparsers.add_parser("tasks", help="List pending tasks across projects")
    tasks_p.add_argument("--project", default=None, help="Filter by project name (partial match)")
    tasks_p.add_argument("--type", default=None, help="Filter by project type (investigacion, docencia, gestion, formacion)")
    tasks_p.add_argument("--status", default=None, help="Filter by project status (en marcha, parado, ...)")
    tasks_p.add_argument("--priority", default=None, help="Filter by priority (alta, media, baja)")
    tasks_p.add_argument("--date", default=None, help="Filter tasks by due date: YYYY-MM-DD or YYYY-MM")
    tasks_p.add_argument("--output", default=None, help="Save output to file instead of terminal")

    # --- import ---
    imp_p = subparsers.add_parser("import", help="Import an Evernote .enex note into a project")
    imp_p.add_argument("--file", required=True, help="Path to the .enex file")
    imp_p.add_argument("--project", required=True, help="Target project (partial name match)")

    # --- done ---
    done_p = subparsers.add_parser("done", help="Mark a task as completed")
    done_p.add_argument("project", help="Project name (partial match)")
    done_p.add_argument("task", help="Task description (partial match)")
    done_p.add_argument("--date", default=None, help="Completion date YYYY-MM-DD (default: today)")

    # --- update ---
    upd_p = subparsers.add_parser("update", help="Set status and/or priority of a project")
    upd_p.add_argument("project", help="Project name (partial match)")
    upd_p.add_argument("--status", default=None, help="New status: inicial, en marcha, parado, esperando, durmiendo, completado")
    upd_p.add_argument("--priority", default=None, help="New priority: alta, media, baja")

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

    # --- day ---
    day_p = subparsers.add_parser("day", help="Create daily log file in ☀️mision-log/diario/")
    day_p.add_argument("--date", default=None, help="Target date YYYY-MM-DD (default: today)")
    day_p.add_argument("--copy", default=None, metavar="YYYY-MM-DD", help="Copy this existing day instead of template")
    day_p.add_argument("--force", action="store_true", help="Overwrite if file already exists")
    day_p.add_argument("--focus", nargs="+", metavar="PROJECT", default=None, help="Focus project (partial name)")

    # --- week ---
    week_p = subparsers.add_parser("week", help="Create weekly log file in ☀️mision-log/semanal/")
    week_p.add_argument("--date", default=None, help="Any date in the target week YYYY-MM-DD (default: today)")
    week_p.add_argument("--copy", default=None, metavar="YYYY-Wnn", help="Copy this existing week instead of template")
    week_p.add_argument("--force", action="store_true", help="Overwrite if file already exists")
    week_p.add_argument("--focus", nargs="+", metavar="PROJECT", default=None, help="Up to 2 focus projects (partial name)")

    # --- month ---
    month_p = subparsers.add_parser("month", help="Create monthly log file in ☀️mision-log/mensual/")
    month_p.add_argument("--date", default=None, help="Target month YYYY-MM (default: current month)")
    month_p.add_argument("--copy", default=None, metavar="YYYY-MM", help="Copy this existing month instead of template")
    month_p.add_argument("--force", action="store_true", help="Overwrite if file already exists")
    month_p.add_argument("--focus", nargs="+", metavar="PROJECT", default=None, help="Up to 3 focus projects (partial name)")

    # --- monthreport ---
    mon_p = subparsers.add_parser("monthreport", help="Generate monthly review table and inject into mensual/YYYY-MM.md")
    mon_p.add_argument("--month", default=None, help="Month as YYYY-MM (default: current month)")
    mon_p.add_argument("--apply", action="store_true", help="Apply computed status/priority changes to proyecto.md")
    mon_p.add_argument("--output", default=None, help="Also save output to file")

    # --- setpriority ---
    sp_p = subparsers.add_parser("setpriority", help="Set priority for one or more projects at once")
    sp_p.add_argument("--priority", required=True, help="Priority: alta, media, baja")
    sp_p.add_argument("--projects", nargs="+", required=True, metavar="PROJECT", help="Project names (partial match supported)")

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

    if args.command == "logday":
        sys.exit(cmd_logday(args))
    elif args.command == "report":
        sys.exit(cmd_report(args))
    elif args.command == "done":
        sys.exit(cmd_done(args))
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
    elif args.command == "list":
        sys.exit(cmd_list(args))
    elif args.command == "tasks":
        sys.exit(cmd_tasks(args))
    elif args.command == "setpriority":
        sys.exit(cmd_setpriority(args))
    elif args.command == "activity":
        sys.exit(cmd_activity(args))
    elif args.command == "monthreport":
        sys.exit(cmd_monthreport(args))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()

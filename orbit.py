#!/usr/bin/env python3
"""Orbit — personal project management CLI."""

import argparse
import sys

from core.log import VALID_TYPES, add_entry
from core.list_entries import list_entries
from core.tasks import list_tasks
from core.activity import run_activity
from core.monthly import run_monthly
from core.misionlog import run_day, run_week, run_month
from core.project import run_project
from core.importer import run_import
from core.update import run_update


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


def cmd_monthly(args):
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


def cmd_day(args):
    return run_day(date_str=args.date, copy=args.copy, force=args.force)


def cmd_week(args):
    return run_week(date_str=args.date, copy=args.copy, force=args.force)


def cmd_month(args):
    return run_month(date_str=args.date, copy=args.copy, force=args.force)


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

    # --- day ---
    day_p = subparsers.add_parser("day", help="Create daily log file in ☀️mision-log/diario/")
    day_p.add_argument("--date", default=None, help="Target date YYYY-MM-DD (default: today)")
    day_p.add_argument("--copy", default=None, metavar="YYYY-MM-DD", help="Copy this existing day instead of template")
    day_p.add_argument("--force", action="store_true", help="Overwrite if file already exists")

    # --- week ---
    week_p = subparsers.add_parser("week", help="Create weekly log file in ☀️mision-log/semanal/")
    week_p.add_argument("--date", default=None, help="Any date in the target week YYYY-MM-DD (default: today)")
    week_p.add_argument("--copy", default=None, metavar="YYYY-Wnn", help="Copy this existing week instead of template")
    week_p.add_argument("--force", action="store_true", help="Overwrite if file already exists")

    # --- month ---
    month_p = subparsers.add_parser("month", help="Create monthly log file in ☀️mision-log/mensual/")
    month_p.add_argument("--date", default=None, help="Target month YYYY-MM (default: current month)")
    month_p.add_argument("--copy", default=None, metavar="YYYY-MM", help="Copy this existing month instead of template")
    month_p.add_argument("--force", action="store_true", help="Overwrite if file already exists")

    # --- monthly ---
    mon_p = subparsers.add_parser("monthly", help="Generate monthly review table and inject into mensual/YYYY-MM.md")
    mon_p.add_argument("--month", default=None, help="Month as YYYY-MM (default: current month)")
    mon_p.add_argument("--apply", action="store_true", help="Apply computed status/priority changes to proyecto.md")
    mon_p.add_argument("--output", default=None, help="Also save output to file")

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

    if args.command == "update":
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
    elif args.command == "activity":
        sys.exit(cmd_activity(args))
    elif args.command == "monthly":
        sys.exit(cmd_monthly(args))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()

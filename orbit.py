#!/usr/bin/env python3
"""Orbit — personal project management CLI."""

import argparse
import re
import sys

from core.log import VALID_TYPES, add_entry, add_entry_with_ref, find_project, find_logbook_file, find_proyecto_file
from core.search import run_search
from core.stats import run_report
from core.project import (run_project_create, run_project_list,
                          run_project_status, run_project_edit, run_project_drop)
from core.importer import run_import
from core.open import open_file, capture_output, open_cmd_output, log_cmd_output, default_editor
from core.dateparse import parse_date
from core.agenda_cmds import (
    run_task_add, run_task_done, run_task_drop, run_task_edit, run_task_list, run_task_log,
    run_ms_add, run_ms_done, run_ms_drop, run_ms_edit, run_ms_list, run_ms_log,
    run_ev_add, run_ev_drop, run_ev_edit, run_ev_list, run_ev_log,
    run_reminder_add, run_reminder_drop, run_reminder_edit, run_reminder_list, run_reminder_log,
)
from core.highlights import (
    run_hl_add, run_hl_drop, run_hl_edit, run_hl_list, VALID_TYPES as HL_TYPES,
)
from core.project_view import run_new_view, run_new_open
from core.notes import run_note_create, run_note_open, run_note_list, run_note_drop
from core.commit import run_commit
from core.migrate import run_migrate, run_migrate_all
from core.agenda_view import run_agenda, run_cal
from core.ls import run_ls_files, run_ls_notes
from core.gsync import run_gsync, run_gsync_migrate_recurring
from core.history import log_history, run_history
from core.claude import run_claude
from core.deliver import run_deliver
from core.recloud import run_recloud


def _d(expr):
    """Parse a natural language date expression, or return None if not provided.

    Passes through special values like 'none' unchanged (used by edit commands).
    Raises SystemExit with a clear message for unrecognised date expressions.
    """
    if not expr:
        return None
    if expr.strip().lower() == "none":
        return "none"
    result = parse_date(expr)
    # If parse_date returned the input unchanged, validate it
    if result == expr.strip() and not re.match(r'^\d{4}-\d{2}(-\d{2})?$', result) \
            and not re.match(r'^\d{4}-W\d{2}$', result):
        print(f"Error: fecha no reconocida: '{expr}'")
        print("  Formatos válidos: YYYY-MM-DD, YYYY-MM, hoy, mañana, ayer,")
        print("  lunes..domingo, 'en 3 días', 'próxima semana', etc.")
        raise SystemExit(1)
    return result


def _ga(args, name, default=None):
    """Get attribute from args, shorthand for getattr with default."""
    return getattr(args, name, default)


def _add_args(args):
    """Extract common add parameters from args."""
    return dict(
        project=args.project, text=args.text,
        date_val=_d(_ga(args, "date")), recur=_ga(args, "recur"),
        until=_d(_ga(args, "until")), ring=_ga(args, "ring"),
        time_val=_ga(args, "time"), desc=_ga(args, "desc"),
    )


def _drop_args(args):
    """Extract common drop parameters from args."""
    return dict(
        project=_ga(args, "project"), text=_ga(args, "text"),
        force=_ga(args, "force", False),
        occurrence=_ga(args, "occurrence", False),
        series=_ga(args, "series", False),
    )


def _edit_args(args):
    """Extract common edit parameters from args."""
    return dict(
        project=_ga(args, "project"), text=_ga(args, "text"),
        new_text=_ga(args, "new_text"),
        new_date=_d(_ga(args, "new_date")) or _ga(args, "new_date"),
        new_recur=_ga(args, "new_recur"),
        new_until=_d(_ga(args, "new_until")) or _ga(args, "new_until"),
        new_ring=_ga(args, "new_ring"),
        new_time=_ga(args, "new_time"),
        new_desc=_ga(args, "new_desc"),
        force=_ga(args, "force", False),
        occurrence=_ga(args, "occurrence", False),
        series=_ga(args, "series", False),
    )


def _handle_output(args, run_fn, cmd_label: str = ""):
    """Run run_fn capturing output, then --open / --log / --to / print as needed.

    run_fn is a zero-arg callable that prints to stdout.
    Returns exit code (int).
    """
    do_open = getattr(args, "open", False)
    log_target = getattr(args, "log", None)
    to_note = getattr(args, "to_note", None)

    if do_open or log_target or to_note:
        with capture_output() as buf:
            run_fn()
        content = buf.getvalue()
        if do_open:
            open_cmd_output(content, getattr(args, "editor", None) or "")
        if log_target:
            entry_type = getattr(args, "log_entry", "apunte")
            log_cmd_output(content, log_target, entry_type, cmd_label)
        if to_note:
            _append_to_note(to_note, content, cmd_label)
        return 0
    else:
        run_fn()
        return 0


def _append_to_note(to_note: str, content: str, cmd_label: str = ""):
    """Append captured output to a note file. Format: project:note_name."""
    from core.project import _find_new_project
    from core.notes import _pick_note
    from core.log import _append_entry

    # Parse project:note format
    if ":" in to_note:
        project_name, note_name = to_note.split(":", 1)
    else:
        print("Error: usa --note proyecto:nota (ej. --note catedra:calibracion)")
        return 1

    project_dir = _find_new_project(project_name)
    if project_dir is None:
        return 1
    notes_dir = project_dir / "notes"
    dest = _pick_note(notes_dir, note_name)
    if dest is None:
        return 1

    # Append content with header
    from datetime import date
    header = f"\n## [{cmd_label}] {date.today().isoformat()}\n\n"
    block = content.strip()
    has_md_table = any(l.startswith("|") for l in block.splitlines())
    if has_md_table:
        entry = f"{header}{block}\n\n"
    else:
        entry = f"{header}```\n{block}\n```\n\n"
    _append_entry(dest, entry)
    print(f"✓ [{project_dir.name}] → nota: {dest.name}")


# Long options that users often type with a single dash (e.g. -date instead of --date)
_SINGLE_DASH_FIX = {
    "-date", "-time", "-recur", "-until", "-ring", "-entry", "-project", "-type", "-status",
    "-list-calendars", "-dry-run",
    "-priority", "-output", "-editor", "-from", "-to", "-limit",
    "-log", "-open", "-force", "-no-open",
    "-file", "-keyword", "-dry-run", "-name", "-date-from",
    "-date-to", "-notes", "-fix",
}

_VERB_ENTITY_SWAP = {
    # verb → set of entities it can precede
    "add":      {"task", "ms", "ev", "hl"},
    "done":     {"task", "ms"},
    "drop":     {"task", "ms", "ev", "hl", "project", "note"},
    "edit":     {"task", "ms", "ev", "hl", "note"},
    "list":     {"task", "ms", "ev", "hl", "note"},
    "create":   {"project", "note"},
    "status":   {"project"},
    "priority": {"project"},
}

_NOTE_SUBCOMMANDS = {"create", "open", "list", "drop"}

def _fix_argv(argv: list) -> list:
    """Normalize argv: fix single-dash options, swap verb-entity order."""
    # Swap "add task ..." → "task add ..." etc.
    if len(argv) >= 2 and argv[0] in _VERB_ENTITY_SWAP:
        if argv[1] in _VERB_ENTITY_SWAP[argv[0]]:
            argv = [argv[1], argv[0]] + argv[2:]

    # Shorthand: "note <project> ..." → "note create <project> ..."
    if len(argv) >= 2 and argv[0] == "note" and argv[1] not in _NOTE_SUBCOMMANDS:
        argv = ["note", "create"] + argv[1:]

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

    # --note / --to: redirect log entry to a note file
    note_flag = getattr(args, "note", False)
    to_note = getattr(args, "to_note", None)
    if note_flag or to_note:
        from core.notes import _title_to_filename, _find_new_project, _pick_note
        from core.log import format_entry, _append_entry
        from datetime import date as _date

        project_dir = _find_new_project(args.project)
        if project_dir is None:
            return 1
        notes_dir = project_dir / "notes"

        entry_text = format_entry(args.message, args.entry, args.ref,
                                  _d(args.date))

        if to_note:
            # Append to existing note
            dest = _pick_note(notes_dir, to_note)
            if dest is None:
                return 1
            _append_entry(dest, entry_text)
            print(f"✓ [{project_dir.name}] {entry_text.strip()}")
            print(f"  → nota: {dest.name}")
        else:
            # Create new note with entry as content
            notes_dir.mkdir(exist_ok=True)
            base_name = _title_to_filename(args.message)
            note_name = f"{_date.today().isoformat()}_{base_name}"
            dest = notes_dir / note_name
            dest.write_text(f"# {args.message}\n\n{entry_text}\n---\n\n")
            print(f"✓ [{project_dir.name}] Nota creada: {note_name}")
            print(f"  {entry_text.strip()}")

        if getattr(args, "open", False):
            open_file(dest, getattr(args, "editor", None) or default_editor())
        return 0

    rc = add_entry_with_ref(
        project=args.project,
        ref=args.ref,
        message=args.message,
        tipo=args.entry,
        fecha=_d(args.date),
        deliver=getattr(args, "deliver", False),
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
    if args.target is None:
        from core.project import generate_proyectos_md
        path = generate_proyectos_md()
        print(f"Generado {path.name}")
        return open_file(path, getattr(args, "editor", None) or default_editor())
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
            link    = getattr(args, "ref", None),
            date_str = getattr(args, "date", None),
            deliver = getattr(args, "deliver", False),
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
    """Note subcommand dispatcher: note open/create/list/drop."""
    action = getattr(args, "action", None) or "create"
    # Subcommands use 'project'; shorthand fallback uses '_project'/'_title'
    project = getattr(args, "project", None) or getattr(args, "_project", None)
    if action == "open":
        return run_note_open(
            project  = project,
            name     = getattr(args, "name", None),
            date_str = _d(getattr(args, "date", None)),
            editor   = getattr(args, "editor", None) or default_editor(),
        )
    if action == "list":
        fn = lambda: run_note_list(project=project)
        return _handle_output(args, fn, "note list")
    if action == "drop":
        return run_note_drop(project=project,
                             file_str=getattr(args, "file", None),
                             force=getattr(args, "force", False))
    # default: create (shorthand uses _project/_title/_file)
    title = getattr(args, "title", None) or getattr(args, "_title", "") or ""
    file_str = getattr(args, "file", None) or getattr(args, "_file", None)
    return run_note_create(
        project   = project,
        title     = title,
        file_str  = file_str,
        open_after= not getattr(args, "no_open", False),
        editor    = getattr(args, "editor", None) or default_editor(),
        no_date   = getattr(args, "no_date", False),
        entry     = getattr(args, "entry", None) or "apunte",
        hl_type   = getattr(args, "hl", None),
    )


def cmd_link(args):
    from core.project import run_link
    return run_link(name=args.project, file=getattr(args, "file", None),
                    from_project=getattr(args, "from_project", None))


def cmd_date(args):
    import subprocess
    from core.dateparse import parse_date
    expr = " ".join(args.expr) if args.expr else "today"
    result = parse_date(expr)
    # Validate it resolved to a YYYY-MM-DD date
    if not re.match(r'^\d{4}-\d{2}-\d{2}$', result):
        print(f"  no se pudo resolver a una fecha: {expr}")
        return 1
    print(result)
    try:
        subprocess.run(["pbcopy"], input=result.encode(), check=True)
        print("  (copiado al portapapeles)")
    except (FileNotFoundError, subprocess.CalledProcessError):
        pass
    return 0


def cmd_week(args):
    import subprocess
    from datetime import date as _date
    from core.dateparse import parse_date, _week_key
    expr = " ".join(args.expr) if args.expr else "today"
    result = parse_date(expr)
    # Convert resolved date to ISO week
    if re.match(r'^\d{4}-W\d{2}$', result):
        week = result
    elif re.match(r'^\d{4}-\d{2}-\d{2}$', result):
        week = _week_key(_date.fromisoformat(result))
    else:
        print(f"  no se pudo resolver a una semana: {expr}")
        return 1
    print(week)
    try:
        subprocess.run(["pbcopy"], input=week.encode(), check=True)
        print("  (copiado al portapapeles)")
    except (FileNotFoundError, subprocess.CalledProcessError):
        pass
    return 0


def cmd_render(args):
    from core.render import run_render
    return run_render(project=args.project, full=args.full, check=args.check)


def cmd_deliver(args):
    return run_deliver(project=args.project, file=args.file)


def cmd_recloud(args):
    return run_recloud(dry_run=args.dry_run)


def cmd_commit(args):
    return run_commit(message=getattr(args, "message", None))


def cmd_task_new(args):
    """Task subcommand dispatcher."""
    action = _ga(args, "action") or "add"
    if action == "add":    return run_task_add(**_add_args(args))
    if action == "done":   return run_task_done(project=_ga(args, "project"), text=_ga(args, "text"))
    if action == "drop":   return run_task_drop(**_drop_args(args))
    if action == "edit":   return run_task_edit(**_edit_args(args))
    if action == "log":    return run_task_log(project=_ga(args, "project"), text=_ga(args, "text"))
    return 1


def cmd_ms(args):
    """Milestone subcommand dispatcher."""
    action = _ga(args, "action") or "list"
    if action == "add":    return run_ms_add(**_add_args(args))
    if action == "done":   return run_ms_done(project=_ga(args, "project"), text=_ga(args, "text"))
    if action == "drop":   return run_ms_drop(**_drop_args(args))
    if action == "edit":   return run_ms_edit(**_edit_args(args))
    if action == "log":    return run_ms_log(project=_ga(args, "project"), text=_ga(args, "text"))
    return 1


def cmd_ev(args):
    """Event subcommand dispatcher."""
    action = _ga(args, "action") or "list"
    if action == "add":
        kw = _add_args(args)
        kw["end_date"] = _d(_ga(args, "end"))
        return run_ev_add(**kw)
    if action == "drop":   return run_ev_drop(**_drop_args(args))
    if action == "edit":
        kw = _edit_args(args)
        kw["new_end"] = _d(_ga(args, "new_end")) or _ga(args, "new_end")
        return run_ev_edit(**kw)
    if action == "list":
        return run_ev_list(project=_ga(args, "project"),
                           period_from=_d(_ga(args, "from_date")),
                           period_to=_d(_ga(args, "to_date")))
    if action == "log":
        return run_ev_log(project=_ga(args, "project"), text=_ga(args, "text"))
    return 1


def cmd_reminder(args):
    """Reminder subcommand dispatcher."""
    action = _ga(args, "action") or "list"
    if action == "add":
        return run_reminder_add(
            project=args.project, text=args.text,
            date_val=_d(args.date), time_val=args.time,
            recur=_ga(args, "recur"), until=_d(_ga(args, "until")),
            desc=_ga(args, "desc"))
    if action == "drop":   return run_reminder_drop(**_drop_args(args))
    if action == "edit":
        return run_reminder_edit(
            project=_ga(args, "project"), text=_ga(args, "text"),
            new_text=_ga(args, "new_text"),
            new_date=_d(_ga(args, "new_date")) or _ga(args, "new_date"),
            new_time=_ga(args, "new_time"),
            new_recur=_ga(args, "new_recur"),
            new_until=_d(_ga(args, "new_until")) or _ga(args, "new_until"),
            new_desc=_ga(args, "new_desc"),
            force=_ga(args, "force", False),
            occurrence=_ga(args, "occurrence", False),
            series=_ga(args, "series", False))
    if action == "log":    return run_reminder_log(project=_ga(args, "project"), text=_ga(args, "text"))
    if action == "list":   return run_reminder_list(project=_ga(args, "project"))
    return 1


from core.config import ORBIT_HOME as ORBIT_DIR


def cmd_project(args):
    sub = getattr(args, "action", None)
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
        else:  # list or no subcommand
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
    from core.config import ORBIT_CODE
    topic = getattr(args, "topic", None)
    editor = getattr(args, "editor", None) or default_editor()
    if topic in (None, "chuleta"):
        if topic is None:
            # Print in terminal (paged)
            try:
                text = (ORBIT_CODE / "CHULETA.md").read_text()
                pager = subprocess.Popen(["less", "-R"], stdin=subprocess.PIPE)
                pager.communicate(input=text.encode())
            except Exception:
                print((ORBIT_CODE / "CHULETA.md").read_text())
        else:
            open_file(ORBIT_CODE / "CHULETA.md", editor)
    elif topic == "tutorial":
        open_file(ORBIT_CODE / "TUTORIAL.md", editor)
    elif topic == "about":
        open_file(ORBIT_CODE / "README.md", editor)
    return 0





def cmd_agenda(args):
    to_file = getattr(args, "open", False) or getattr(args, "log", None)
    fn = lambda: run_agenda(
        projects=getattr(args, "projects", None) or None,
        date_str=_d(getattr(args, "date", None)),
        date_from=_d(getattr(args, "date_from", None)),
        date_to=_d(getattr(args, "date_to", None)),
        no_cal=getattr(args, "no_cal", False),
        markdown=bool(to_file),
        dated_only=getattr(args, "dated", False),
        order=getattr(args, "order", "date"),
        summary=getattr(args, "summary", False),
    )
    return _handle_output(args, fn, "agenda")


def cmd_cal(args):
    to_file = getattr(args, "open", False) or getattr(args, "log", None)
    fn = lambda: run_cal(
        date_str=_d(getattr(args, "date", None)),
        date_from=_d(getattr(args, "date_from", None)),
        date_to=_d(getattr(args, "date_to", None)),
        markdown=bool(to_file),
    )
    return _handle_output(args, fn, "cal")


_REPORT_PERIODS = {
    "today": "today", "hoy": "today",
    "yesterday": "yesterday", "ayer": "yesterday",
    "week": "this week", "semana": "this week",
    "month": "this month", "mes": "this month",
}


def cmd_report(args):
    projects = getattr(args, "projects", None) or None
    date_str = getattr(args, "date", None)
    date_from = getattr(args, "date_from", None)
    date_to = getattr(args, "date_to", None)

    # Allow "report today", "report week", "report month" as shortcuts
    if projects and not date_str and not date_from and not date_to:
        first = projects[0].lower()
        if first in _REPORT_PERIODS:
            date_str = _REPORT_PERIODS[first]
            projects = projects[1:] or None

    fn = lambda: run_report(
        projects=projects,
        date_str=_d(date_str),
        date_from=_d(date_from),
        date_to=_d(date_to),
        summary=getattr(args, "summary", False),
    )
    return _handle_output(args, fn, "report")


def cmd_gsync(args):
    if getattr(args, "migrate_recurring", False):
        return run_gsync_migrate_recurring(
            dry_run=getattr(args, "dry_run", False),
        )
    return run_gsync(
        dry_run=getattr(args, "dry_run", False),
        list_calendars=getattr(args, "list_calendars", False),
    )


def cmd_history(args):
    to_file = getattr(args, "open", False) or getattr(args, "log", None)
    fn = lambda: run_history(
        date_str=_d(getattr(args, "date", None)),
        date_from=_d(getattr(args, "date_from", None)),
        date_to=_d(getattr(args, "date_to", None)),
    )
    return _handle_output(args, fn, "history")


def cmd_claude(args):
    question = getattr(args, "question", None)
    if not question:
        print("Uso: orbit claude \"tu pregunta\"")
        return 1
    return run_claude(question=" ".join(question) if isinstance(question, list) else question)


def cmd_doctor(args):
    from core.doctor import run_doctor
    return run_doctor(
        project=getattr(args, "project", None),
        fix=getattr(args, "fix", False),
    )


def cmd_undo(args):
    from core.undo import run_undo
    return run_undo()


def cmd_archive(args):
    from core.archive import run_archive
    return run_archive(
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
            project=_ga(args, "project"),
            period_from=_d(_ga(args, "date_from")),
            period_to=_d(_ga(args, "date_to")))
        return _handle_output(args, fn, "ls ev")

    if what in ("reminders", "rem"):
        fn = lambda: run_reminder_list(
            project=_ga(args, "project"))
        return _handle_output(args, fn, "ls reminders")

    if what == "hl":
        fn = lambda: run_hl_list(
            project=_ga(args, "project"),
            hl_type=getattr(args, "type", None))
        return _handle_output(args, fn, "ls hl")

    if what == "files":
        fn = lambda: run_ls_files(
            project=_ga(args, "project"))
        return _handle_output(args, fn, "ls files")

    if what == "notes":
        fn = lambda: run_ls_notes(
            project=_ga(args, "project"))
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
    """Add --log, --log-entry, and --to arguments to a parser."""
    p.add_argument("--log", default=None, metavar="PROJECT",
                   help="Log output to a project's logbook (default: mission)")
    p.add_argument("--log-entry", dest="log_entry", default="apunte",
                   choices=VALID_TYPES, metavar="TYPE",
                   help="Entry type for --log (default: apunte)")
    p.add_argument("--note", dest="to_note", default=None, metavar="PROJ:NOTA",
                   help="Append output to a note (e.g. --note catedra:calibracion)")


class _OrbitParser(argparse.ArgumentParser):
    """ArgumentParser that shows a friendlier error message."""

    def error(self, message):
        # For invalid command choices, suggest closest match
        import re
        m = re.search(r"invalid choice: '(\w+)'", message)
        if m:
            from difflib import get_close_matches
            bad = m.group(1)
            # Extract valid choices from the message
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


def _build_parser():
    parser = _OrbitParser(prog="orbit", description="Orbit project management CLI")
    subparsers = parser.add_subparsers(dest="command")

    # --- log ---
    log_p = subparsers.add_parser("log", help="Add an entry to a project logbook")
    log_p.add_argument("project", help="Project name (partial match)")
    log_p.add_argument("message", help="Entry message / title")
    log_p.add_argument("ref",     nargs="?", default=None, help="File path or URL (optional)")
    log_p.add_argument(
        "--entry",
        default="apunte",
        choices=VALID_TYPES,
        metavar="ENTRY",
        help=f"Entry type: {', '.join(VALID_TYPES)} (default: apunte)",
    )
    log_p.add_argument("--note",    action="store_true", help="Create a note file with the log entry")
    log_p.add_argument("--to",      dest="to_note", default=None, metavar="NOTE",
                        help="Append log entry to an existing note (partial name match)")
    log_p.add_argument("--deliver", action="store_true", help="Deliver file to cloud (logs/ with date prefix)")
    log_p.add_argument("--date", default=None, help="Entry date YYYY-MM-DD (default: today)")
    log_p.add_argument("--open", action="store_true", help="Open the logbook/note in editor after logging")
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
    ls_ev.add_argument("project", nargs="?", default=None, help="Project")
    ls_ev.add_argument("--from", dest="date_from", default=None, metavar="DATE")
    ls_ev.add_argument("--to",   dest="date_to",   default=None, metavar="DATE")
    ls_ev.add_argument("--open",   action="store_true")
    ls_ev.add_argument("--editor", default=None)
    _add_log_args(ls_ev)

    # ls reminders [project]
    ls_rem = ls_sub.add_parser("reminders", aliases=["rem"], help="List active reminders")
    ls_rem.add_argument("project", nargs="?", default=None, help="Project")
    ls_rem.add_argument("--open",   action="store_true")
    ls_rem.add_argument("--editor", default=None)
    _add_log_args(ls_rem)

    # ls hl [project]
    ls_hl = ls_sub.add_parser("hl", help="List highlights")
    ls_hl.add_argument("project", nargs="?", default=None, help="Project")
    ls_hl.add_argument("--type", default=None, choices=HL_TYPES, help="Section type")
    ls_hl.add_argument("--open",   action="store_true")
    ls_hl.add_argument("--editor", default=None)
    _add_log_args(ls_hl)

    # ls files [project]
    ls_files = ls_sub.add_parser("files", help="List project md files with git status")
    ls_files.add_argument("project", nargs="?", default=None, help="Project")
    ls_files.add_argument("--open",   action="store_true")
    ls_files.add_argument("--editor", default=None)
    _add_log_args(ls_files)

    # ls notes [project]
    ls_notes = ls_sub.add_parser("notes", help="List notes with git status")
    ls_notes.add_argument("project", nargs="?", default=None, help="Project")
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
    rep_p.add_argument("--summary", nargs="?", const="", default=None,
                       metavar="SECTION",
                       help="Summary table: logbook, agenda, highlights, all (default: logbook+agenda)")
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
    ag_p.add_argument("--calendar", action="store_true", default=None,
                      help="Show calendar grid (default; kept for backwards compat)")
    ag_p.add_argument("--no-cal", action="store_true", dest="no_cal",
                      help="Suppress calendar grid, show only the list")
    ag_p.add_argument("--dated",  action="store_true",
                      help="Only show tasks/milestones with a date")
    ag_p.add_argument("--order", choices=["project", "date", "type"], default="date",
                      help="Order by date (default), project, or type (events/milestones/tasks)")
    ag_p.add_argument("--summary", action="store_true",
                      help="Per-project summary table (counts and date range)")
    ag_p.add_argument("--open",   action="store_true", help="Open in editor")
    ag_p.add_argument("--editor", default=None)
    _add_log_args(ag_p)

    # --- cal ---
    cal_p = subparsers.add_parser("cal",
                                  help="Show a plain calendar grid (no agenda data)")
    cal_p.add_argument("--date", default=None, help="Date: YYYY-MM-DD, YYYY-MM, YYYY-Wnn...")
    cal_p.add_argument("--from", dest="date_from", default=None, metavar="DATE",
                       help="Period start (default: 1st of current month)")
    cal_p.add_argument("--to", dest="date_to", default=None, metavar="DATE",
                       help="Period end (default: last day of current month)")
    cal_p.add_argument("--open", action="store_true", help="Open in editor")
    cal_p.add_argument("--editor", default=None)
    _add_log_args(cal_p)

    # --- gsync ---
    gsync_p = subparsers.add_parser("gsync",
                                     help="Sync tasks/milestones/events to Google Tasks/Calendar")
    gsync_p.add_argument("--dry-run", action="store_true", dest="dry_run",
                         help="Preview sync without writing to Google")
    gsync_p.add_argument("--list-calendars", action="store_true", dest="list_calendars",
                         help="List available Google Calendars with IDs")
    gsync_p.add_argument("--migrate-recurring", action="store_true", dest="migrate_recurring",
                         help="One-time: mark old recurring events with ⚠️ and reset for RRULE re-creation")

    # --- doctor ---
    doc_p = subparsers.add_parser("doctor",
                                   help="Check syntax of project files (logbook, agenda, highlights)")
    doc_p.add_argument("project", nargs="?", default=None,
                       help="Project name (omit for all)")
    doc_p.add_argument("--fix", action="store_true",
                       help="Offer to fix issues interactively")

    # --- archive ---
    archive_p = subparsers.add_parser("archive",
                                       help="Archive old entries, done tasks, past events, stale notes")
    archive_p.add_argument("project", nargs="?", default=None,
                           help="Project name (omit for all)")
    archive_p.add_argument("--months", type=int, default=6,
                           help="Age threshold in months (default: 6)")
    archive_p.add_argument("--dry-run", action="store_true", dest="dry_run",
                           help="Preview what would be removed without deleting")
    archive_p.add_argument("--force", action="store_true",
                           help="Skip all confirmations")
    archive_p.add_argument("--agenda", action="store_true",
                           help="Only archive done tasks/milestones and past events")
    archive_p.add_argument("--logbook", action="store_true",
                           help="Only archive old logbook entries")
    archive_p.add_argument("--notes", action="store_true",
                           help="Only archive stale notes")

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
    tn_add.add_argument("--time",  default=None,
                        help="Time HH:MM (e.g. 15:00)")
    tn_add.add_argument("--desc",  default=None,
                        help="Description (links, notes — stored as indented lines)")

    tn_done = tsknew_sub.add_parser("done", help="Complete a pending task")
    _task_project_text(tn_done, project_required=False)

    tn_drop = tsknew_sub.add_parser("drop", help="Cancel a pending task")
    _task_project_text(tn_drop, project_required=False)
    tn_drop.add_argument("--force", action="store_true", help="Skip confirmation")
    tn_drop.add_argument("-o", dest="occurrence", action="store_true", help="Drop this occurrence only (advance to next)")
    tn_drop.add_argument("-s", dest="series", action="store_true", help="Drop the entire series")

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
    tn_edit.add_argument("--time",  dest="new_time",  default=None,
                         help="New time HH:MM (or 'none')")
    tn_edit.add_argument("--desc",  dest="new_desc",  default=None,
                         help="New description (or 'none' to clear)")
    tn_edit.add_argument("--force", action="store_true", help="Skip prompt; safe default = occurrence")
    tn_edit.add_argument("-o", dest="occurrence", action="store_true", help="Edit this occurrence only")
    tn_edit.add_argument("-s", dest="series", action="store_true", help="Edit the entire series")

    tn_log = tsknew_sub.add_parser("log", help="Create logbook entry from a task")
    _task_project_text(tn_log, project_required=False)

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
    ms_add.add_argument("--time",  default=None, help="Time HH:MM (e.g. 15:00)")
    ms_add.add_argument("--desc",  default=None, help="Description (links, notes)")

    ms_done = ms_sub.add_parser("done", help="Mark milestone as reached")
    ms_done.add_argument("project", nargs="?", default=None)
    ms_done.add_argument("text",    nargs="?", default=None)

    ms_drop = ms_sub.add_parser("drop", help="Cancel a milestone")
    ms_drop.add_argument("project", nargs="?", default=None)
    ms_drop.add_argument("text",    nargs="?", default=None)
    ms_drop.add_argument("--force", action="store_true", help="Skip confirmation")
    ms_drop.add_argument("-o", dest="occurrence", action="store_true", help="Drop this occurrence only (advance to next)")
    ms_drop.add_argument("-s", dest="series", action="store_true", help="Drop the entire series")

    ms_edit = ms_sub.add_parser("edit", help="Edit a milestone")
    ms_edit.add_argument("project", nargs="?", default=None)
    ms_edit.add_argument("text",    nargs="?", default=None)
    ms_edit.add_argument("--text",  dest="new_text",  default=None)
    ms_edit.add_argument("--date",  dest="new_date",  default=None)
    ms_edit.add_argument("--recur", dest="new_recur", default=None, help="Recurrence (or 'none')")
    ms_edit.add_argument("--until", dest="new_until", default=None, help="End date for recurrence (or 'none')")
    ms_edit.add_argument("--ring",  dest="new_ring",  default=None, help="HH:MM, 1d, 2h, YYYY-MM-DD HH:MM, or none")
    ms_edit.add_argument("--time",  dest="new_time",  default=None, help="New time HH:MM (or 'none')")
    ms_edit.add_argument("--desc",  dest="new_desc",  default=None, help="New description (or 'none' to clear)")
    ms_edit.add_argument("--force", action="store_true", help="Skip prompt; safe default = occurrence")
    ms_edit.add_argument("-o", dest="occurrence", action="store_true", help="Edit this occurrence only")
    ms_edit.add_argument("-s", dest="series", action="store_true", help="Edit the entire series")

    ms_log = ms_sub.add_parser("log", help="Create logbook entry from a milestone")
    ms_log.add_argument("project", nargs="?", default=None)
    ms_log.add_argument("text",    nargs="?", default=None)

    # --- ev ---
    ev_p   = subparsers.add_parser("ev", help="Event commands (agenda.md)")
    ev_sub = ev_p.add_subparsers(dest="action")

    ev_add = ev_sub.add_parser("add", help="Add an event")
    ev_add.add_argument("project",  help="Project name")
    ev_add.add_argument("text",     nargs="?", default=None, help="Event description")
    ev_add.add_argument("--date",   required=True, help="Event date YYYY-MM-DD")
    ev_add.add_argument("--end",    default=None, help="End date YYYY-MM-DD (optional)")
    ev_add.add_argument("--time",   default=None, help="Time: HH:MM or HH:MM-HH:MM (ej. 10:00, 10:00-12:30)")
    ev_add.add_argument("--recur",  default=None, help="Recurrence: daily, weekly, monthly, every 2 weeks, ...")
    ev_add.add_argument("--until",  default=None, help="End date for recurrence")
    ev_add.add_argument("--ring",   default=None, help="Reminder: HH:MM, 1d, 2h, YYYY-MM-DD HH:MM")
    ev_add.add_argument("--desc",   default=None, help="Description (links, notes)")

    ev_drop = ev_sub.add_parser("drop", help="Remove an event")
    ev_drop.add_argument("project", nargs="?", default=None)
    ev_drop.add_argument("text",    nargs="?", default=None)
    ev_drop.add_argument("--force", action="store_true", help="Skip confirmation")
    ev_drop.add_argument("-o", dest="occurrence", action="store_true", help="Drop this occurrence only (advance to next)")
    ev_drop.add_argument("-s", dest="series", action="store_true", help="Drop the entire series")

    ev_edit = ev_sub.add_parser("edit", help="Edit an event")
    ev_edit.add_argument("project", nargs="?", default=None)
    ev_edit.add_argument("text",    nargs="?", default=None)
    ev_edit.add_argument("--text",  dest="new_text",  default=None)
    ev_edit.add_argument("--date",  dest="new_date",  default=None)
    ev_edit.add_argument("--end",   dest="new_end",   default=None, help="End date or 'none'")
    ev_edit.add_argument("--time",  dest="new_time",  default=None, help="HH:MM, HH:MM-HH:MM, or 'none'")
    ev_edit.add_argument("--recur", dest="new_recur", default=None, help="Recurrence (or 'none')")
    ev_edit.add_argument("--until", dest="new_until", default=None, help="End date for recurrence (or 'none')")
    ev_edit.add_argument("--ring",  dest="new_ring",  default=None, help="HH:MM, 1d, 2h, YYYY-MM-DD HH:MM, or none")
    ev_edit.add_argument("--desc",  dest="new_desc",  default=None, help="New description (or 'none' to clear)")
    ev_edit.add_argument("--force", action="store_true", help="Skip prompt; safe default = occurrence")
    ev_edit.add_argument("-o", dest="occurrence", action="store_true", help="Edit this occurrence only")
    ev_edit.add_argument("-s", dest="series", action="store_true", help="Edit the entire series")

    ev_list = ev_sub.add_parser("list", help="List events")
    ev_list.add_argument("project", nargs="?", default=None)
    ev_list.add_argument("--from",  dest="from_date", default=None)
    ev_list.add_argument("--to",    dest="to_date", default=None)

    ev_log = ev_sub.add_parser("log", help="Create logbook entry from an event")
    ev_log.add_argument("project", nargs="?", default=None)
    ev_log.add_argument("text",    nargs="?", default=None,
                        help="Event name (partial match; omit for interactive)")

    # --- reminder ---
    rem_p   = subparsers.add_parser("reminder", aliases=["rem"], help="Reminder commands (agenda.md 💬)")
    rem_sub = rem_p.add_subparsers(dest="action")

    rem_add = rem_sub.add_parser("add", help="Add a reminder")
    rem_add.add_argument("project",  help="Project name")
    rem_add.add_argument("text",     help="Reminder text")
    rem_add.add_argument("--date",   required=True, help="Date: YYYY-MM-DD, today, tomorrow...")
    rem_add.add_argument("--time",   required=True, help="Time: HH:MM")
    rem_add.add_argument("--recur",  default=None, help="Recurrence: daily, weekly, monthly, ...")
    rem_add.add_argument("--until",  default=None, help="End date for recurrence")
    rem_add.add_argument("--desc",   default=None, help="Description (links, notes)")

    rem_drop = rem_sub.add_parser("drop", help="Remove a reminder")
    rem_drop.add_argument("project", nargs="?", default=None)
    rem_drop.add_argument("text",    nargs="?", default=None)
    rem_drop.add_argument("--force", action="store_true", help="Skip confirmation")
    rem_drop.add_argument("-o", dest="occurrence", action="store_true", help="Drop this occurrence only (advance to next)")
    rem_drop.add_argument("-s", dest="series", action="store_true", help="Drop the entire series")

    rem_edit = rem_sub.add_parser("edit", help="Edit a reminder")
    rem_edit.add_argument("project", nargs="?", default=None)
    rem_edit.add_argument("text",    nargs="?", default=None)
    rem_edit.add_argument("--text",  dest="new_text",  default=None, help="New description")
    rem_edit.add_argument("--date",  dest="new_date",  default=None, help="New date (or 'none')")
    rem_edit.add_argument("--time",  dest="new_time",  default=None, help="New time HH:MM (or 'none')")
    rem_edit.add_argument("--recur", dest="new_recur", default=None, help="New recurrence (or 'none')")
    rem_edit.add_argument("--until", dest="new_until", default=None, help="End date for recurrence (or 'none')")
    rem_edit.add_argument("--desc",  dest="new_desc",  default=None, help="Description (or 'none')")
    rem_edit.add_argument("--force", action="store_true", help="Skip prompt; safe default = occurrence")
    rem_edit.add_argument("-o", dest="occurrence", action="store_true", help="Edit this occurrence only")
    rem_edit.add_argument("-s", dest="series", action="store_true", help="Edit the entire series")

    rem_log = rem_sub.add_parser("log", help="Create logbook entry from a reminder")
    rem_log.add_argument("project", nargs="?", default=None)
    rem_log.add_argument("text",    nargs="?", default=None)

    rem_list = rem_sub.add_parser("list", help="List active reminders")
    rem_list.add_argument("project", nargs="?", default=None)

    # --- hl ---
    hl_p   = subparsers.add_parser("hl", help="Highlights commands (highlights.md)")
    hl_sub = hl_p.add_subparsers(dest="action")

    hl_add = hl_sub.add_parser("add", help="Add a highlight")
    hl_add.add_argument("project", help="Project name (partial match)")
    hl_add.add_argument("text",    help="Highlight text or title")
    hl_add.add_argument("ref",     nargs="?", default=None, help="File path or URL (optional)")
    hl_add.add_argument("--type",  required=True, choices=HL_TYPES,
                        help="Section type: refs, results, decisions, ideas, evals")
    hl_add.add_argument("--deliver", action="store_true", help="Deliver file to cloud (hls/)")
    hl_add.add_argument("--date",  nargs="?", const="today", default=None,
                        help="Prefix date (today, tomorrow, YYYY-MM-DD)")

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
    nt_create.add_argument("file",    nargs="?", default=None,
                           help="File to import (omit to create new)")
    nt_create.add_argument("--no-open", action="store_true",
                           help="Do not open the note after creating")
    nt_create.add_argument("--no-date", action="store_true",
                           help="No date prefix in filename (still registers in logbook)")
    nt_create.add_argument("--entry",   default="apunte",
                           help="Logbook entry type (default: apunte)")
    nt_create.add_argument("--hl",      default=None, metavar="TYPE",
                           help="Register in highlights instead of logbook (e.g. referencia)")
    nt_create.add_argument("--editor",  default=None)

    nt_open = note_sub.add_parser("open", help="Open note (create if missing)")
    nt_open.add_argument("project", help="Project name (partial match)")
    nt_open.add_argument("name", nargs="?", default=None,
                         help="Note name (omit for interactive selection)")
    nt_open.add_argument("--date", default=None,
                         help="Date-based name: YYYY-MM-DD, YYYY-Wnn, YYYY-MM")
    nt_open.add_argument("--editor", default=None)

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

    # Also accept:  note <project> <title> [file]  (without 'create' subcommand)
    note_p.add_argument("_project", nargs="?", default=None)
    note_p.add_argument("_title",   nargs="?", default=None)
    note_p.add_argument("_file",    nargs="?", default=None)
    note_p.add_argument("--no-open", action="store_true")
    note_p.add_argument("--no-date", action="store_true")
    note_p.add_argument("--entry",   default="apunte")
    note_p.add_argument("--hl",      default=None, metavar="TYPE")
    note_p.add_argument("--editor",  default=None)

    # --- link ---
    link_p = subparsers.add_parser("link", help="Markdown link to project (copied to clipboard)")
    link_p.add_argument("project", help="Project name (partial match)")
    link_p.add_argument("file", nargs="?", default=None, help="File path within project (e.g. notes/result.md)")
    link_p.add_argument("--from", dest="from_project", default=None,
                        help="Source project (for relative path from its notes/)")

    # --- date ---
    date_p = subparsers.add_parser("date", help="Print date in YYYY-MM-DD (copied to clipboard)")
    date_p.add_argument("expr", nargs="*", help="Date expression (e.g. wednesday, in 2 weeks)")

    # --- week ---
    week_p = subparsers.add_parser("week", help="Print ISO week in YYYY-Wnn (copied to clipboard)")
    week_p.add_argument("expr", nargs="*", help="Date expression (e.g. next week, in 2 weeks)")

    # --- render ---
    rnd_p = subparsers.add_parser("render", help="Render project files to HTML for cloud")
    rnd_p.add_argument("project", nargs="?", default=None, help="Project name (partial match)")
    rnd_p.add_argument("--full", action="store_true", help="Full render of all projects")
    rnd_p.add_argument("--check", action="store_true", help="Check cloud sync status")

    # --- deliver ---
    dlv_p = subparsers.add_parser("deliver", help="Deliver file to cloud (copy + clipboard)")
    dlv_p.add_argument("project", help="Project name (partial match)")
    dlv_p.add_argument("file",    help="File path to deliver")

    # --- recloud ---
    rcl_p = subparsers.add_parser("recloud", help="Migrate cloud links to use symlink")
    rcl_p.add_argument("--dry-run", action="store_true", help="Show changes without applying")

    # --- commit ---
    cmt_p = subparsers.add_parser("commit", help="Git commit with confirmation")
    cmt_p.add_argument("message", nargs="?", default=None,
                       help="Commit message (prompted if omitted; auto-generated on empty input)")

    # --- project ---
    prj_p   = subparsers.add_parser("project", help="Manage projects (new model)")
    prj_sub = prj_p.add_subparsers(dest="action")

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
    prt_sub.add_parser("list", help="List configured project types")
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

    # --- history ---
    hist_p = subparsers.add_parser("history",
                                    help="Show command history for a day or period")
    hist_p.add_argument("--date", default=None,
                        help="Date: YYYY-MM-DD, YYYY-MM, YYYY-Wnn, today, tomorrow...")
    hist_p.add_argument("--from", dest="date_from", default=None, metavar="DATE",
                        help="Period start")
    hist_p.add_argument("--to", dest="date_to", default=None, metavar="DATE",
                        help="Period end")
    hist_p.add_argument("--open", action="store_true", help="Open in editor")
    hist_p.add_argument("--editor", default=None)
    _add_log_args(hist_p)

    # --- claude ---
    claude_p = subparsers.add_parser("claude",
                                      help="Ask Claude about Orbit usage")
    claude_p.add_argument("question", nargs="+", help="Your question about Orbit")

    # --- undo ---
    subparsers.add_parser("undo", help="Undo the last operation")

    # --- help ---
    hlp_p   = subparsers.add_parser("help", help="Show help: chuleta (default), tutorial, about")
    hlp_sub = hlp_p.add_subparsers(dest="topic")
    for _name, _help in [("chuleta",  "Open CHULETA.md in editor"),
                          ("tutorial", "Open TUTORIAL.md in editor"),
                          ("about",    "Open README.md in editor")]:
        _p = hlp_sub.add_parser(_name, help=_help)
        _p.add_argument("--editor", default=None)

    return parser


# Command dispatch table
_COMMANDS = {
    "task": cmd_task_new,
    "ms": cmd_ms, "ev": cmd_ev, "reminder": cmd_reminder, "rem": cmd_reminder, "hl": cmd_hl,
    "view": cmd_view_new,
    "note": cmd_note, "commit": cmd_commit, "deliver": cmd_deliver, "link": cmd_link,
    "date": cmd_date, "week": cmd_week,
    "render": cmd_render, "recloud": cmd_recloud,
    "log": cmd_log, "search": cmd_search,
    "report": cmd_report, "open": cmd_open,
    "import": cmd_import,
    "project": cmd_project, "migrate": cmd_migrate,
    "ls": cmd_ls, "agenda": cmd_agenda, "cal": cmd_cal, "gsync": cmd_gsync,
    "doctor": cmd_doctor, "archive": cmd_archive, "undo": cmd_undo,
    "history": cmd_history, "claude": cmd_claude,
}


def run_command(argv: list) -> int:
    """Execute an orbit command from a list of arguments. Returns exit code."""
    parser = _build_parser()
    args = parser.parse_args(_fix_argv(argv))

    log_history(argv)

    if args.command is None:
        run_shell()
        return 0
    if args.command in _COMMANDS:
        return _COMMANDS[args.command](args) or 0
    if args.command == "shell":
        run_shell(editor=getattr(args, "editor", None) or default_editor())
        return 0
    if args.command == "help":
        return cmd_help(args) or 0
    parser.print_help()
    return 1


def main():
    sys.exit(run_command(sys.argv[1:]))


def run_shell(editor: str = ""):
    from core.shell import run_shell as _run_shell
    _run_shell(editor)


if __name__ == "__main__":
    import io as _io
    _old_stderr = sys.stderr
    sys.stderr = _io.StringIO()
    try:
        main()
    except SystemExit as _e:
        _captured = sys.stderr.getvalue()
        sys.stderr = _old_stderr
        if _captured:
            sys.stderr.write(_captured)
        _code = _e.code if isinstance(_e.code, int) else 1
        if _code != 0 and _captured and sys.stdin.isatty():
            from core.claude import suggest_on_error
            _chosen = suggest_on_error(sys.argv[1:], _captured.strip())
            if _chosen:
                import shlex as _shlex
                try:
                    sys.argv = ["orbit"] + _shlex.split(_chosen.removeprefix("orbit "))
                    main()
                except SystemExit:
                    pass
        sys.exit(_code)
    finally:
        if sys.stderr != _old_stderr:
            _cap = sys.stderr.getvalue()
            sys.stderr = _old_stderr
            if _cap:
                sys.stderr.write(_cap)

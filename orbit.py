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


def _editor_from_args(args) -> str:
    """Extract editor from --open [EDITOR] or --editor, with default fallback."""
    open_val = getattr(args, "open", None)
    if isinstance(open_val, str):
        return open_val
    editor_val = getattr(args, "editor", None)
    return editor_val or default_editor()


def _handle_output(args, run_fn, cmd_label: str = "", open_file_path=None):
    """Run run_fn capturing output, then --open / --log / --append / print as needed.

    run_fn is a zero-arg callable that prints to stdout.
    open_file_path: if given, --open writes to this path instead of cmd.md.
    Returns exit code (int).
    """
    open_val = getattr(args, "open", False)
    do_open = bool(open_val)
    editor = _editor_from_args(args)
    log_target = getattr(args, "log", None)
    append_note = getattr(args, "append_note", None)

    if do_open or log_target or append_note:
        with capture_output() as buf:
            run_fn()
        content = buf.getvalue()
        if do_open:
            if open_file_path:
                open_file_path.write_text(content)
                open_file(open_file_path, editor)
            else:
                open_cmd_output(content, editor)
        if log_target:
            entry_type = getattr(args, "log_entry", "apunte")
            log_cmd_output(content, log_target, entry_type, cmd_label)
        if append_note:
            _append_to_note(append_note, content, cmd_label)
        return 0
    else:
        run_fn()
        return 0


def _append_to_note(to_note: str, content: str, cmd_label: str = ""):
    """Append captured output to a note file. Format: project:note."""
    from core.log import _append_entry

    if ":" not in to_note:
        print("Error: usa --append proyecto:nota (ej. --append catedra:calibracion)")
        return 1

    project_dir, dest = _resolve_and_find_note(None, to_note)
    if project_dir is None:
        return 1
    if dest is None:
        _, note_name = to_note.split(":", 1)
        dest = _create_note_for_entry(project_dir, note_name)
        if dest is None:
            return 1

    # Format content block
    from datetime import date
    label = f"**[{cmd_label}] {date.today().isoformat()}**"
    block = content.strip()
    has_md_table = any(l.startswith("|") for l in block.splitlines())
    if has_md_table:
        entry = f"{label}\n\n{block}\n\n"
    else:
        entry = f"{label}\n\n```\n{block}\n```\n\n"

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
    "done":     {"task", "ms", "crono"},
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


# ── Note helpers for --append ──────────────────────────────────────────────────

def _find_note(project_dir, note_name):
    """Find a note by partial name match. Returns Path or None."""
    notes_dir = project_dir / "notes"
    if not notes_dir.exists():
        return None
    notes = sorted(notes_dir.glob("*.md"))
    matches = [n for n in notes if note_name.lower() in n.name.lower()]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        print(f"Ambiguo: {', '.join(n.name for n in matches)}")
    return None


def _resolve_and_find_note(project_name, note_name):
    """Parse project:note or plain note, find the file.

    Returns (project_dir, dest_path_or_None).
    project_dir is None on error.
    """
    from core.project import _find_new_project

    # project:note syntax
    if ":" in note_name:
        proj_name, note_name = note_name.split(":", 1)
    else:
        proj_name = project_name

    project_dir = _find_new_project(proj_name)
    if project_dir is None:
        return None, None

    dest = _find_note(project_dir, note_name)
    return project_dir, dest


def _create_note_for_entry(project_dir, note_name, entry_text=None):
    """Create a new note, asking for confirmation. Returns dest Path or None."""
    import sys as _sys
    from core.notes import _title_to_filename
    from datetime import date as _date

    if _sys.stdin.isatty():
        try:
            ans = input(f"Nota '{note_name}' no encontrada. ¿Crear nueva? [S/n]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            return None
        if ans not in ("", "s", "si", "sí", "y", "yes"):
            return None

    notes_dir = project_dir / "notes"
    notes_dir.mkdir(exist_ok=True)

    base_name = _title_to_filename(note_name)
    fname = f"{_date.today().isoformat()}_{base_name}"
    dest = notes_dir / fname
    content = f"# {note_name}\n\n"
    if entry_text:
        content += entry_text + "\n---\n\n"
    dest.write_text(content)

    print(f"✓ [{project_dir.name}] Nota creada: {fname}")
    if entry_text:
        print(f"  {entry_text.strip()}")
    return dest


def cmd_log(args):
    if not args.project:
        print("Error: especifica un proyecto → orbit log <proyecto> \"mensaje\"")
        return 1

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
                open_file(logbook, _editor_from_args(args))
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
        open_after=False,
        editor="",
        in_filter=getattr(args, "in_filter", None),
        include_federated=not getattr(args, "no_fed", False),
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
        return open_file(path, _editor_from_args(args))
    what = getattr(args, "what", None)
    return run_new_open(args.target, what=what,
                        editor=_editor_from_args(args))


def cmd_view_new(args):
    log_target = getattr(args, "log", None)
    editor = _editor_from_args(args)
    if log_target:
        fn = lambda: run_new_view(project=getattr(args, "project", None),
                                  open_after=False, editor=editor)
        return _handle_output(args, fn, "view")
    return run_new_view(
        project    = getattr(args, "project", None),
        open_after = bool(getattr(args, "open", None)),
        editor     = editor,
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
            editor   = _editor_from_args(args),
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
            editor   = _editor_from_args(args),
        )
    if action == "list":
        fn = lambda: run_note_list(project=project)
        return _handle_output(args, fn, "note list")
    if action == "drop":
        return run_note_drop(project=project,
                             file_str=getattr(args, "file", None),
                             force=getattr(args, "force", False))
    if action == "import":
        from core.notes import run_note_import
        return run_note_import(
            project   = project,
            title     = getattr(args, "title", ""),
            file_str  = getattr(args, "file", None),
            open_after= not getattr(args, "no_open", False),
            editor    = _editor_from_args(args),
            no_date   = getattr(args, "no_date", False),
            entry     = getattr(args, "entry", None) or "apunte",
            hl_type   = getattr(args, "hl", None),
        )
    # default: create (shorthand uses _project/_title/_file)
    title = getattr(args, "title", None) or getattr(args, "_title", "") or ""
    file_str = getattr(args, "file", None) or getattr(args, "_file", None)
    return run_note_create(
        project   = project,
        title     = title,
        file_str  = file_str,
        open_after= not getattr(args, "no_open", False),
        editor    = _editor_from_args(args),
        no_date   = getattr(args, "no_date", False),
        entry     = getattr(args, "entry", None) or "apunte",
        hl_type   = getattr(args, "hl", None),
    )


def cmd_clip(args):
    from core.clip import run_clip
    return run_clip(mode=args.mode, args=args)


def cmd_render(args):
    from core.render import run_render
    return run_render(project=args.project, full=args.full, check=args.check)


def cmd_deliver(args):
    return run_deliver(project=args.project, file=args.file)


def cmd_cloud(args):
    """Cloud subcommand dispatcher."""
    action = _ga(args, "action")
    if action == "imgs":
        from core.cloud_imgs import run_cloud_imgs
        return run_cloud_imgs(dry_run=getattr(args, "dry_run", False))
    print("Uso: orbit cloud imgs [--dry-run]")
    return 1


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
        # --end-time → merge into --time as HH:MM-HH:MM
        end_time = _ga(args, "end_time")
        if end_time:
            start_time = kw.get("time_val") or "09:00"
            kw["time_val"] = f"{start_time}-{end_time}"
        return run_ev_add(**kw)
    if action == "drop":   return run_ev_drop(**_drop_args(args))
    if action == "edit":
        kw = _edit_args(args)
        kw["new_end"] = _d(_ga(args, "new_end")) or _ga(args, "new_end")
        # --end-time → merge into --time as HH:MM-HH:MM
        new_end_time = _ga(args, "new_end_time")
        if new_end_time:
            start_time = (kw.get("new_time") or "").split("-")[0] or None
            if start_time:
                kw["new_time"] = f"{start_time}-{new_end_time}"
            else:
                print("⚠️  --end-time requiere --time para especificar la hora de inicio.")
                return 1
        return run_ev_edit(**kw)
    # list: use "ls ev" instead
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
    # list: use "ls reminders" instead
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
                                editor=_editor_from_args(args))
    elif sub == "drop":
        return run_project_drop(name=args.name,
                                force=getattr(args, "force", False))
    elif sub == "priority":
        from core.project import run_project_priority
        return run_project_priority(name=args.name,
                                     new_priority=args.priority,
                                     reason=getattr(args, "reason", None))
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
    to_editor = bool(getattr(args, "open", None))
    editor = _editor_from_args(args)

    _HELP_FILES = {
        None:       ("CHULETA.md",  "chuleta.md"),
        "chuleta":  ("CHULETA.md",  "chuleta.md"),
        "tutorial": ("TUTORIAL.md", "tutorial.md"),
        "about":    ("README.md",   "readme.md"),
    }
    entry = _HELP_FILES.get(topic)
    if not entry:
        print(f"Tema desconocido: {topic}. Usa: chuleta, tutorial, about")
        return 1

    source, workspace_name = entry
    path = ORBIT_CODE / source
    if to_editor:
        dest = ORBIT_DIR / workspace_name
        dest.write_text(path.read_text())
        open_file(dest, editor)
    else:
        try:
            text = path.read_text()
            pager = subprocess.Popen(["less", "-R"], stdin=subprocess.PIPE)
            pager.communicate(input=text.encode())
        except Exception:
            print(path.read_text())
    return 0





_AGENDA_PERIODS = {
    "today": "today", "hoy": "today",
    "week": "this week", "semana": "this week",
    "month": "this month", "mes": "this month",
}


def cmd_agenda(args):
    to_file = getattr(args, "open", False) or getattr(args, "log", None)
    projects = getattr(args, "projects", None) or None
    date_str = getattr(args, "date", None)
    date_from = getattr(args, "date_from", None)
    date_to = getattr(args, "date_to", None)

    # Allow "agenda week", "agenda month" as period shortcuts
    if projects and not date_str and not date_from and not date_to:
        first = projects[0].lower()
        if first in _AGENDA_PERIODS:
            date_str = _AGENDA_PERIODS[first]
            projects = projects[1:] or None

    fn = lambda: run_agenda(
        projects=projects,
        date_str=_d(date_str),
        date_from=_d(date_from),
        date_to=_d(date_to),
        no_cal=getattr(args, "no_cal", False),
        markdown=bool(to_file),
        dated_only=getattr(args, "dated", False),
        order=getattr(args, "order", "date"),
        summary=getattr(args, "summary", False),
        include_federated=not getattr(args, "no_fed", False),
    )
    return _handle_output(args, fn, "agenda",
                          open_file_path=ORBIT_DIR / "agenda.md")


_MONTH_MAP = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4,
    "mayo": 5, "junio": 6, "julio": 7, "agosto": 8,
    "septiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12,
    "jan": 1, "feb": 2, "mar": 3, "apr": 4,
    "jun": 6, "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
    "ene": 1, "abr": 4, "ago": 8, "dic": 12,
}


def _resolve_cal_month(s):
    """Resolve a month name or YYYY-MM to (from_str, to_str) or None."""
    import calendar as _calmod
    from datetime import date as _date_cls
    # YYYY-MM format
    if len(s) == 7 and s[4] == '-':
        try:
            y, m = int(s[:4]), int(s[5:7])
            last = _calmod.monthrange(y, m)[1]
            return _date_cls(y, m, 1).isoformat(), _date_cls(y, m, last).isoformat()
        except ValueError:
            return None
    # Month name
    m = _MONTH_MAP.get(s.lower())
    if m:
        y = _date_cls.today().year
        last = _calmod.monthrange(y, m)[1]
        return _date_cls(y, m, 1).isoformat(), _date_cls(y, m, last).isoformat()
    return None


def cmd_cal(args):
    to_file = getattr(args, "open", False) or getattr(args, "log", None)
    date_str = _d(getattr(args, "date", None))
    date_from = _d(getattr(args, "date_from", None))
    date_to = _d(getattr(args, "date_to", None))

    # Resolve positional month/span if no explicit --date/--from/--to
    month_arg = getattr(args, "month", None)
    span_arg = getattr(args, "span", None)
    if month_arg and not date_str and not date_from and not date_to:
        resolved = _resolve_cal_month(month_arg)
        if resolved:
            date_from = resolved[0]  # only set start; span will set end
            if not span_arg:
                date_to = resolved[1]
        else:
            # month_arg might be a number (span from current month)
            try:
                span_arg = int(month_arg)
            except ValueError:
                print(f"⚠️  Mes no reconocido: {month_arg}")
                return 1
    if span_arg:
        span = max(1, min(span_arg, 3))
        from datetime import date as _date_cls
        import calendar as _calmod
        if date_from:
            base = _date_cls.fromisoformat(date_from) if isinstance(date_from, str) else date_from
        else:
            base = _date_cls.today()
        start_m = _date_cls(base.year, base.month, 1)
        end_y = start_m.year + (start_m.month + span - 2) // 12
        end_m = (start_m.month + span - 2) % 12 + 1
        end_d = _calmod.monthrange(end_y, end_m)[1]
        date_from = start_m.isoformat()
        date_to = _date_cls(end_y, end_m, end_d).isoformat()

    fn = lambda: run_cal(
        date_str=date_str,
        date_from=date_from,
        date_to=date_to,
        markdown=bool(to_file),
    )
    return _handle_output(args, fn, "cal")


_REPORT_PERIODS = {
    "today": "today", "hoy": "today",
    "yesterday": "yesterday", "ayer": "yesterday",
    "week": "this week", "semana": "this week",
    "month": "this month", "mes": "this month",
}


def cmd_panel(args):
    from core.panel import run_panel
    from core.config import ORBIT_HOME
    period = getattr(args, "period", None)
    fn = lambda: run_panel(period=period,
                           include_federated=not getattr(args, "no_fed", False),
                           date_from=_d(getattr(args, "date_from", None)),
                           date_to=_d(getattr(args, "date_to", None)))
    return _handle_output(args, fn, "panel",
                          open_file_path=ORBIT_HOME / "panel.md")


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
        include_federated=not getattr(args, "no_fed", False),
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


def cmd_crono(args):
    """Cronograma subcommand dispatcher."""
    from core.cronograma import (
        run_crono_add, run_crono_show, run_crono_check,
        run_crono_list, run_crono_done,
    )
    action = _ga(args, "action")
    if action == "add":
        return run_crono_add(project=args.project, name=args.name)
    if action == "show":
        fn = lambda: run_crono_show(project=args.project, name=args.name)
        return _handle_output(args, fn, "crono show")
    if action == "check":
        return run_crono_check(project=args.project, name=args.name)
    if action == "list":
        fn = lambda: run_crono_list(project=args.project)
        return _handle_output(args, fn, "crono list")
    if action == "done":
        return run_crono_done(project=args.project, name=args.name, index=args.index)
    print("Uso: crono add|show|check|list|done ...")
    return 1


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

    _inc_fed = not getattr(args, "no_fed", False)

    if what == "tasks":
        fn = lambda: run_task_list(
            projects=getattr(args, "projects", None) or None,
            status_filter=getattr(args, "status", "pending"),
            date_filter=_d(getattr(args, "date", None)),
            dated_only=getattr(args, "dated", False),
            unplanned=getattr(args, "unplanned", False),
            include_federated=_inc_fed)
        return _handle_output(args, fn, "ls tasks")

    if what == "ms":
        fn = lambda: run_ms_list(
            projects=getattr(args, "projects", None) or None,
            status_filter=getattr(args, "status", "pending"),
            date_filter=_d(getattr(args, "date", None)),
            dated_only=getattr(args, "dated", False),
            include_federated=_inc_fed)
        return _handle_output(args, fn, "ls ms")

    if what == "ev":
        fn = lambda: run_ev_list(
            project=_ga(args, "project"),
            period_from=_d(_ga(args, "date_from")),
            period_to=_d(_ga(args, "date_to")),
            include_federated=_inc_fed)
        return _handle_output(args, fn, "ls ev")

    if what in ("reminders", "rem"):
        fn = lambda: run_reminder_list(
            project=_ga(args, "project"),
            include_federated=_inc_fed)
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
    p.add_argument("--append", dest="append_note", default=None, metavar="PROJ:NOTA",
                   help="Append output to a note (e.g. --append catedra:calibracion)")


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


# ── Argument helpers (reduce repetition in _build_parser) ────────────────────

def _add_project_text(p, project_required=True):
    """Add project + text positional args (used by all appointment subcommands)."""
    if project_required:
        p.add_argument("project", help="Project name (partial match)")
    else:
        p.add_argument("project", nargs="?", default=None,
                       help="Project name (partial match; omit for interactive)")
    p.add_argument("text", nargs="?", default=None, help="Text or partial match")


def _add_add_args(p, date_required=False, time_required=False, has_ring=True):
    """Add common args for 'add' subcommands (date, recur, until, time, desc, ring)."""
    p.add_argument("--date", required=date_required, default=None, help="Date: YYYY-MM-DD, today, tomorrow...")
    p.add_argument("--recur", default=None, help="Recurrence: daily, weekly, monthly, weekdays, ...")
    p.add_argument("--until", default=None, help="End date for recurrence YYYY-MM-DD")
    p.add_argument("--time", required=time_required, default=None, help="Time HH:MM")
    p.add_argument("--desc", default=None, help="Description (links, notes)")
    if has_ring:
        p.add_argument("--ring", default=None, help="Reminder: 1d, 2h, HH:MM, YYYY-MM-DD HH:MM")


def _add_edit_args(p, has_end=False, has_end_time=False):
    """Add common args for 'edit' subcommands (new_text, new_date, new_recur, etc.)."""
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
    """Add common args for 'drop' subcommands (force, -o, -s)."""
    p.add_argument("--force", action="store_true", help="Skip confirmation")
    p.add_argument("-o", dest="occurrence", action="store_true", help="Drop this occurrence only")
    p.add_argument("-s", dest="series", action="store_true", help="Drop the entire series")


def _add_fed_args(p):
    """Add --no-fed flag to disable federated workspace reading."""
    p.add_argument("--no-fed", action="store_true",
                   help="No incluir espacios federados")


def _add_output_args(p):
    """Add --open [EDITOR], --log, --log-entry, --append args."""
    p.add_argument("--open", nargs="?", const=True, default=None, metavar="EDITOR",
                   help="Open in editor (optionally specify editor name)")


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
    log_p.add_argument("--deliver", action="store_true", help="Deliver file to cloud (logs/ with date prefix)")
    log_p.add_argument("--date", default=None, help="Entry date YYYY-MM-DD (default: today)")
    log_p.add_argument("--open", nargs="?", const=True, default=None, metavar="EDITOR",
                       help="Open in editor (optionally specify editor name)")

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
    search_p.add_argument("--open", nargs="?", const=True, default=None, metavar="EDITOR",
                          help="Open in editor (optionally specify editor name)")
    _add_log_args(search_p)
    _add_fed_args(search_p)

    # --- ls (unified listing) ---
    ls_p   = subparsers.add_parser("ls", help="List projects, tasks, milestones, events, highlights, files, notes")
    ls_sub = ls_p.add_subparsers(dest="what")

    # ls projects (default when no subcommand)
    ls_proj = ls_sub.add_parser("projects", help="List projects with status")
    ls_proj.add_argument("--status", default=None, help="Filter: active, paused, sleeping")
    ls_proj.add_argument("--type",   default=None, help="Filter: investigacion, docencia, ...")
    ls_proj.add_argument("--sort",   default=None, choices=["type", "status", "priority"],
                         help="Sort by: type, status, priority")
    _add_output_args(ls_proj)
    _add_log_args(ls_proj)

    # ls tasks [project...]
    ls_tasks = ls_sub.add_parser("tasks", help="List tasks")
    ls_tasks.add_argument("projects", nargs="*", default=None, help="Project(s)")
    ls_tasks.add_argument("--status", default="pending",
                          choices=["pending", "done", "cancelled", "all"])
    ls_tasks.add_argument("--date",   default=None, help="Filter by date")
    ls_tasks.add_argument("--dated",     action="store_true", help="Only show tasks with a date")
    ls_tasks.add_argument("--unplanned", action="store_true", help="Only show tasks without a date")
    _add_output_args(ls_tasks)
    _add_log_args(ls_tasks)
    _add_fed_args(ls_tasks)

    # ls ms [project...]
    ls_ms = ls_sub.add_parser("ms", help="List milestones")
    ls_ms.add_argument("projects", nargs="*", default=None, help="Project(s)")
    ls_ms.add_argument("--status", default="pending",
                       choices=["pending", "done", "cancelled", "all"])
    ls_ms.add_argument("--date",   default=None, help="Filter by date")
    ls_ms.add_argument("--dated",  action="store_true", help="Only show milestones with a date")
    _add_output_args(ls_ms)
    _add_log_args(ls_ms)
    _add_fed_args(ls_ms)

    # ls ev [project]
    ls_ev = ls_sub.add_parser("ev", help="List events")
    ls_ev.add_argument("project", nargs="?", default=None, help="Project")
    ls_ev.add_argument("--from", dest="date_from", default=None, metavar="DATE")
    ls_ev.add_argument("--to",   dest="date_to",   default=None, metavar="DATE")
    _add_output_args(ls_ev)
    _add_log_args(ls_ev)
    _add_fed_args(ls_ev)

    # ls reminders [project]
    ls_rem = ls_sub.add_parser("reminders", aliases=["rem"], help="List active reminders")
    ls_rem.add_argument("project", nargs="?", default=None, help="Project")
    _add_output_args(ls_rem)
    _add_log_args(ls_rem)
    _add_fed_args(ls_rem)

    # ls hl [project]
    ls_hl = ls_sub.add_parser("hl", help="List highlights")
    ls_hl.add_argument("project", nargs="?", default=None, help="Project")
    ls_hl.add_argument("--type", default=None, choices=HL_TYPES, help="Section type")
    _add_output_args(ls_hl)
    _add_log_args(ls_hl)

    # ls files [project]
    ls_files = ls_sub.add_parser("files", help="List project md files with git status")
    ls_files.add_argument("project", nargs="?", default=None, help="Project")
    _add_output_args(ls_files)
    _add_log_args(ls_files)

    # ls notes [project]
    ls_notes = ls_sub.add_parser("notes", help="List notes with git status")
    ls_notes.add_argument("project", nargs="?", default=None, help="Project")
    _add_output_args(ls_notes)
    _add_log_args(ls_notes)

    # ls <project> — fallback: list logbook entries
    ls_p.add_argument("--type",        nargs="+", default=None, dest="type_filter",
                      metavar="TYPE", help="Filter by entry type(s)")
    ls_p.add_argument("--date",        default=None, help="Filter by date")
    ls_p.add_argument("--from",        dest="period_from", default=None, metavar="DATE")
    ls_p.add_argument("--to",          dest="period_to",   default=None, metavar="DATE")
    _add_output_args(ls_p)
    _add_log_args(ls_p)

    shell_p = subparsers.add_parser("shell", help="Enter interactive Orbit shell")
    shell_p.add_argument("--editor", default=None, help="Editor (env ORBIT_EDITOR, or system default)")

    # --- open ---
    open_p = subparsers.add_parser("open", help="Open a project file in editor")
    open_p.add_argument("target", nargs="?", default=None,
                        help="Project name (partial match)")
    open_p.add_argument("what", nargs="?", default=None,
                        choices=["logbook", "highlights", "agenda", "project"],
                        help="Which file to open: project (default), logbook, highlights, agenda, notes")
    open_p.add_argument("--dir",      action="store_true",
                        help="Open the project directory in Finder")
    open_p.add_argument("--editor",   default=None,
                        help="Editor: obsidian, glow, code, or any command")

    # --- panel ---
    pan_p = subparsers.add_parser("panel", help="Dashboard: priority projects, agenda, activity")
    pan_p.add_argument("period", nargs="?", default=None,
                       help="Period: today (default), week, month")
    pan_p.add_argument("--from", dest="date_from", default=None, metavar="DATE",
                       help="Period start")
    pan_p.add_argument("--to", dest="date_to", default=None, metavar="DATE",
                       help="Period end")
    pan_p.add_argument("--open", nargs="?", const=True, default=None, metavar="EDITOR",
                       help="Open in editor (optionally specify editor name)")
    _add_log_args(pan_p)
    _add_fed_args(pan_p)

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
    rep_p.add_argument("--open", nargs="?", const=True, default=None, metavar="EDITOR",
                       help="Open in editor (optionally specify editor name)")
    _add_log_args(rep_p)
    _add_fed_args(rep_p)

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
    ag_p.add_argument("--no-cal", action="store_true", dest="no_cal",
                      help="Suppress calendar grid, show only the list")
    ag_p.add_argument("--dated",  action="store_true",
                      help="Only show tasks/milestones with a date")
    ag_p.add_argument("--order", choices=["project", "date", "type"], default="date",
                      help="Order by date (default), project, or type (events/milestones/tasks)")
    ag_p.add_argument("--summary", action="store_true",
                      help="Per-project summary table (counts and date range)")
    ag_p.add_argument("--open", nargs="?", const=True, default=None, metavar="EDITOR",
                      help="Open in editor (optionally specify editor name)")
    _add_log_args(ag_p)
    _add_fed_args(ag_p)

    # --- cal ---
    cal_p = subparsers.add_parser("cal",
                                  help="Show a plain calendar grid (no agenda data)")
    cal_p.add_argument("month", nargs="?", default=None,
                       help="Month name (april/abril) or YYYY-MM")
    cal_p.add_argument("span", nargs="?", default=None, type=int,
                       help="Number of months to show (1-3, default 1)")
    cal_p.add_argument("--date", default=None, help="Date: YYYY-MM-DD, YYYY-MM, YYYY-Wnn...")
    cal_p.add_argument("--from", dest="date_from", default=None, metavar="DATE",
                       help="Period start (default: 1st of current month)")
    cal_p.add_argument("--to", dest="date_to", default=None, metavar="DATE",
                       help="Period end (default: last day of current month)")
    cal_p.add_argument("--open", nargs="?", const=True, default=None, metavar="EDITOR",
                       help="Open in editor (optionally specify editor name)")
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

    # --- ms ---
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

    # --- ev ---
    ev_p   = subparsers.add_parser("ev", help="Event commands (agenda.md)")
    ev_sub = ev_p.add_subparsers(dest="action")

    ev_add = ev_sub.add_parser("add", help="Add an event")
    _add_project_text(ev_add, project_required=True)
    _add_add_args(ev_add, date_required=True)
    ev_add.add_argument("--end", "--end-date", default=None, help="End date YYYY-MM-DD")
    ev_add.add_argument("--end-time", default=None, dest="end_time", help="End time HH:MM")

    ev_drop = ev_sub.add_parser("drop", help="Remove an event")
    _add_project_text(ev_drop, project_required=False)
    _add_drop_args(ev_drop)

    ev_edit = ev_sub.add_parser("edit", help="Edit an event")
    _add_project_text(ev_edit, project_required=False)
    _add_edit_args(ev_edit, has_end=True, has_end_time=True)

    ev_log = ev_sub.add_parser("log", help="Create logbook entry from an event")
    _add_project_text(ev_log, project_required=False)

    # --- reminder ---
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
    v2_p.add_argument("--open", nargs="?", const=True, default=None, metavar="EDITOR",
                      help="Open in editor (optionally specify editor name)")
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

    nt_import = note_sub.add_parser("import", help="Import an existing .md file as a note")
    nt_import.add_argument("project", help="Project name (partial match)")
    nt_import.add_argument("title",   help="Note title")
    nt_import.add_argument("file",    help="Path to .md file to import")
    nt_import.add_argument("--no-open", action="store_true",
                           help="Do not open the note after importing")
    nt_import.add_argument("--no-date", action="store_true",
                           help="No date prefix in filename")
    nt_import.add_argument("--entry",   default="apunte",
                           help="Logbook entry type (default: apunte)")
    nt_import.add_argument("--hl",      default=None, metavar="TYPE",
                           help="Register in highlights instead of logbook")
    nt_import.add_argument("--editor",  default=None)

    nt_open = note_sub.add_parser("open", help="Open note (create if missing)")
    nt_open.add_argument("project", help="Project name (partial match)")
    nt_open.add_argument("name", nargs="?", default=None,
                         help="Note name (omit for interactive selection)")
    nt_open.add_argument("--date", default=None,
                         help="Date-based name: YYYY-MM-DD, YYYY-Wnn, YYYY-MM")
    nt_open.add_argument("--editor", default=None)

    nt_list = note_sub.add_parser("list", help="List notes with git status")
    nt_list.add_argument("project", help="Project name (partial match)")
    nt_list.add_argument("--open", nargs="?", const=True, default=None, metavar="EDITOR",
                         help="Open in editor (optionally specify editor name)")
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

    # --- clip ---
    clip_p = subparsers.add_parser("clip", help="Copy reference to clipboard (date, week, month, project link)")
    clip_p.add_argument("mode", help="date | week | month | <project name>")
    clip_p.add_argument("target", nargs="?", default=None,
                        help="Date expr (for date/week) or file query (for project)")
    clip_p.add_argument("expr", nargs="*", help="Additional date expression words")
    clip_p.add_argument("--from", dest="from_project", default=None,
                        help="Source project (for relative path from its notes/)")

    # --- render ---
    rnd_p = subparsers.add_parser("render", help="Render project files to HTML for cloud")
    rnd_p.add_argument("project", nargs="?", default=None, help="Project name (partial match)")
    rnd_p.add_argument("--full", action="store_true", help="Full render of all projects")
    rnd_p.add_argument("--check", action="store_true", help="Check cloud sync status")

    # --- deliver ---
    dlv_p = subparsers.add_parser("deliver", help="Deliver file to cloud (copy + clipboard)")
    dlv_p.add_argument("project", help="Project name (partial match)")
    dlv_p.add_argument("file",    help="File path to deliver")

    # --- cloud ---
    cld_p   = subparsers.add_parser("cloud", help="Cloud operations: imgs")
    cld_sub = cld_p.add_subparsers(dest="action")

    ci_p = cld_sub.add_parser("imgs", help="Collect images from _imgs/ and deliver to project cloud")
    ci_p.add_argument("--dry-run", action="store_true", help="Show what would be done without moving files")

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
    pre_p.add_argument("--editor", default=None, help="Editor")

    # project priority
    prp_p = prj_sub.add_parser("priority", help="Change project priority")
    prp_p.add_argument("name", help="Project name (partial match)")
    prp_p.add_argument("priority", choices=["alta", "media", "baja"],
                        help="New priority: alta, media, baja")
    prp_p.add_argument("--reason", default=None,
                        help="Reason for priority (shown in panel)")

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
    hist_p.add_argument("--open", nargs="?", const=True, default=None, metavar="EDITOR",
                        help="Open in editor (optionally specify editor name)")
    _add_log_args(hist_p)

    # --- claude ---
    claude_p = subparsers.add_parser("claude",
                                      help="Ask Claude about Orbit usage")
    claude_p.add_argument("question", nargs="+", help="Your question about Orbit")

    # --- crono ---
    crono_p = subparsers.add_parser("crono", help="Cronogramas: tareas anidadas con dependencias")
    crono_sub = crono_p.add_subparsers(dest="action")

    cr_add = crono_sub.add_parser("add", help="Crear cronograma")
    cr_add.add_argument("project", help="Project name")
    cr_add.add_argument("name", help="Cronograma name")

    cr_show = crono_sub.add_parser("show", help="Mostrar cronograma con fechas calculadas")
    cr_show.add_argument("project", help="Project name")
    cr_show.add_argument("name", help="Cronograma name (partial match)")
    cr_show.add_argument("--open", nargs="?", const=True, default=None, metavar="EDITOR")
    _add_log_args(cr_show)

    cr_check = crono_sub.add_parser("check", help="Validar cronograma (doctor)")
    cr_check.add_argument("project", help="Project name")
    cr_check.add_argument("name", help="Cronograma name (partial match)")

    cr_list = crono_sub.add_parser("list", help="Listar cronogramas del proyecto")
    cr_list.add_argument("project", help="Project name")
    cr_list.add_argument("--open", nargs="?", const=True, default=None, metavar="EDITOR")
    _add_log_args(cr_list)

    cr_done = crono_sub.add_parser("done", help="Marcar tarea de cronograma como completada")
    cr_done.add_argument("project", help="Project name")
    cr_done.add_argument("name", help="Cronograma name")
    cr_done.add_argument("index", help="Task index (e.g. 1.2)")

    # --- undo ---
    subparsers.add_parser("undo", help="Undo the last operation")

    # --- help ---
    hlp_p   = subparsers.add_parser("help", help="Show help: chuleta (default), tutorial, about")
    hlp_p.add_argument("--open", nargs="?", const=True, default=None, metavar="EDITOR",
                       help="Open in editor (optionally specify editor name)")
    hlp_sub = hlp_p.add_subparsers(dest="topic")
    for _name, _help in [("chuleta",  "Open CHULETA.md in editor"),
                          ("tutorial", "Open TUTORIAL.md"),
                          ("about",    "Open README.md")]:
        _p = hlp_sub.add_parser(_name, help=_help)

    return parser


# Command dispatch table
_COMMANDS = {
    "task": cmd_task_new,
    "ms": cmd_ms, "ev": cmd_ev, "reminder": cmd_reminder, "rem": cmd_reminder, "hl": cmd_hl,
    "view": cmd_view_new,
    "note": cmd_note, "commit": cmd_commit, "deliver": cmd_deliver,
    "clip": cmd_clip,
    "cloud": cmd_cloud, "render": cmd_render, "recloud": cmd_recloud,
    "log": cmd_log, "search": cmd_search,
    "panel": cmd_panel, "report": cmd_report, "open": cmd_open,
    "import": cmd_import,
    "project": cmd_project, "migrate": cmd_migrate,
    "ls": cmd_ls, "agenda": cmd_agenda, "cal": cmd_cal, "gsync": cmd_gsync,
    "crono": cmd_crono,
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
        run_shell(editor=_editor_from_args(args))
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

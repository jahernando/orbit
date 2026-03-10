"""shell.py — interactive Orbit shell with startup sequence.

Startup flow:
  1. gsync + doctor run in background (parallel)
  2. Today's reminders are scheduled
  3. Wait for background tasks (max 5s)
  4. Doctor issues presented with fix option
  5. Untracked files detected, commit+push offered
"""

import readline
import shlex
import sys
from datetime import date as _date
from pathlib import Path

from core.config import ORBIT_HOME as ORBIT_DIR, ORBIT_PROMPT


# ── Startup sequence ─────────────────────────────────────────────────────────

def _run_startup():
    """Execute all startup checks. Called once when shell starts.

    Order matters:
      1. Doctor — validate data integrity (fast, local)
      2. Google sync + reminders — only after data is clean
      3. Untracked files + commit + push
    """

    # 1. Doctor first — validate before syncing
    from core.doctor import doctor_background
    doctor_thread, doctor_issues = doctor_background()
    doctor_thread.join(timeout=5)

    if doctor_thread.is_alive():
        print("  🏥 Doctor aún revisando... (ejecuta 'doctor' manualmente)")
        print()
    elif doctor_issues:
        fixable = [i for i in doctor_issues if i.fix]
        unfixable = [i for i in doctor_issues if not i.fix]
        n = len(doctor_issues)
        print(f"  🏥 {n} problema{'s' if n != 1 else ''} de sintaxis encontrado{'s' if n != 1 else ''}:")
        for issue in doctor_issues:
            prefix = "🔧" if issue.fix else "⚠️"
            print(f"      {prefix} [{issue.project}] {issue.file}:{issue.line_num} — {issue.msg}")
        print()
        if fixable:
            from core.doctor import _interactive_fix
            _interactive_fix(fixable)
            print()
        if unfixable:
            print(f"  {len(unfixable)} problema{'s' if len(unfixable) != 1 else ''} requiere{'n' if len(unfixable) != 1 else ''} corrección manual.")
            print()

    # 2. Google sync + reminders (parallel, after data validated)
    from core.gsync import gsync_background
    from core.ring import schedule_new_format_reminders

    gsync_thread = gsync_background()
    scheduled = schedule_new_format_reminders()
    if scheduled:
        print(f"  {len(scheduled)} recordatorio{'s' if len(scheduled) != 1 else ''} programado{'s' if len(scheduled) != 1 else ''} para hoy.")
        print()
    if gsync_thread is not None:
        gsync_thread.join(timeout=5)

    # 3. Untracked files + commit + push
    from core.commit import startup_commit_check
    startup_commit_check()
    print()


# ── Shell REPL ───────────────────────────────────────────────────────────────

def run_shell(editor: str = ""):
    """Interactive Orbit shell with readline, tab completion, and startup checks."""

    # Enable persistent history
    history_file = Path.home() / ".orbit_history"
    try:
        readline.read_history_file(history_file)
    except FileNotFoundError:
        pass
    readline.set_history_length(500)

    COMMANDS = ["task", "ms", "ev", "hl", "view", "note", "commit", "migrate",
                "import", "ls", "log", "search", "open", "report", "agenda",
                "gsync", "doctor", "clean", "help", "project", "claude", "exit", "quit"]

    def completer(text, state):
        options = [c for c in COMMANDS if c.startswith(text)]
        return options[state] if state < len(options) else None

    readline.set_completer(completer)
    readline.parse_and_bind("tab: complete")

    print("¡Hola! ¡Bienvenido!")
    print()

    _run_startup()

    shell_start_date = _date.today()

    # Lazy import to avoid circular dependency
    from orbit import main

    while True:
        # Midnight check
        if _date.today() != shell_start_date:
            print()
            print("🎃 ¡Medianoche! Orbit se convierte en calabaza.")
            print("   Los recordatorios del nuevo día no se programarán hasta que reinicies el shell.")
            print()
            shell_start_date = _date.today()

        try:
            line = input(f"{ORBIT_PROMPT} ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not line or line.startswith("#"):
            continue
        if line in ("exit", "quit", "q"):
            break
        if line == "claude":
            import subprocess
            subprocess.run(["claude"], cwd=ORBIT_DIR)
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

    print()
    print("¡Hasta pronto!")

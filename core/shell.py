"""shell.py — interactive Orbit shell with startup sequence.

Startup flow:
  1. Doctor — validate data integrity, offer fixes
  2. Untracked files — prompt to stage new files
  3. Commit + push — offer to commit staged changes
  4. Code update — check for new code in orbit repo
  5. gsync in background (fire & forget) + schedule reminders
"""

import readline
import shlex
import sys
from datetime import date as _date
from pathlib import Path

from core.config import ORBIT_HOME as ORBIT_DIR, ORBIT_CODE, ORBIT_PROMPT


# ── Startup sequence ─────────────────────────────────────────────────────────

def _run_startup():
    """Execute all startup checks. Called once when shell starts.

    Order matters:
      1. Doctor — validate data integrity (fast, local)
      2. Google sync + reminders — only after data is clean
      3. Untracked files + commit + push
    """

    # 1. Doctor — validate data integrity, offer fixes
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

    # 2. Untracked files — prompt to stage new files
    from core.commit import startup_untracked_check, startup_commit_offer
    startup_untracked_check()

    # 3. Commit + push — offer to commit staged changes
    startup_commit_offer()
    print()

    # 4. Code update check — pull new code from orbit repo
    from core.commit import startup_code_update_check
    startup_code_update_check()

    # 5. gsync in background (fire & forget) + schedule reminders
    from core.gsync import gsync_background
    from core.ring import schedule_new_format_reminders

    gsync_background()
    scheduled = schedule_new_format_reminders()
    if scheduled:
        print(f"  {len(scheduled)} recordatorio{'s' if len(scheduled) != 1 else ''} programado{'s' if len(scheduled) != 1 else ''} para hoy.")
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
                "gsync", "doctor", "archive", "undo", "help", "project", "claude", "exit", "quit"]

    # Shell commands allowed to run from the Orbit REPL
    SHELL_COMMANDS = {"deliver", "git", "cat", "head", "tail", "pwd", "echo"}

    all_completions = COMMANDS + sorted(SHELL_COMMANDS)

    def completer(text, state):
        options = [c for c in all_completions if c.startswith(text)]
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

        # Dispatch whitelisted shell commands directly
        if tokens[0] in SHELL_COMMANDS:
            import subprocess
            orbit_sh = ORBIT_DIR / "orbit.sh"
            if not orbit_sh.exists():
                orbit_sh = ORBIT_CODE / "orbit.sh"
            if orbit_sh.exists():
                subprocess.run(f"source '{orbit_sh}' && {line}", shell=True,
                               cwd=ORBIT_DIR, executable="/bin/zsh")
            else:
                subprocess.run(line, shell=True, cwd=ORBIT_DIR)
            continue

        from core.undo import commit_operation, discard_operation

        old_argv = sys.argv
        sys.argv  = ["orbit"] + tokens
        exit_code = 0
        captured_err = ""
        try:
            # Capture stderr to detect errors for suggestions
            import io
            old_stderr = sys.stderr
            sys.stderr = io.StringIO()
            try:
                main()
            finally:
                captured_err = sys.stderr.getvalue()
                sys.stderr = old_stderr
                if captured_err:
                    sys.stdout.write(captured_err)
                    sys.stdout.flush()
            commit_operation(label=line)
        except SystemExit as e:
            exit_code = e.code if isinstance(e.code, int) else 1
            commit_operation(label=line)
        except Exception:
            discard_operation()
            raise
        finally:
            sys.argv = old_argv

        # On error, offer Claude suggestions
        if exit_code != 0 and captured_err:
            from core.claude import suggest_on_error
            chosen = suggest_on_error(tokens, captured_err.strip())
            if chosen:
                # Strip "orbit " prefix if present and execute
                cmd = chosen.removeprefix("orbit ")
                try:
                    new_tokens = shlex.split(cmd)
                except ValueError:
                    continue
                old_argv = sys.argv
                sys.argv = ["orbit"] + new_tokens
                try:
                    main()
                    commit_operation(label=cmd)
                except SystemExit:
                    commit_operation(label=cmd)
                except Exception:
                    discard_operation()
                    raise
                finally:
                    sys.argv = old_argv

    readline.write_history_file(history_file)

    print()
    print("¡Hasta pronto!")

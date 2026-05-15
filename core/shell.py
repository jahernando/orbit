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
import threading
from datetime import date as _date
from pathlib import Path

from core.config import ORBIT_HOME as ORBIT_DIR, ORBIT_CODE, ORBIT_PROMPT


# ── Background dash refresh ─────────────────────────────────────────────────

_dash_stop = threading.Event()

DASH_INTERVAL = 3600  # seconds (1 hour) — refresh cadence
_DASH_STOP_POLL = 5   # seconds — shutdown latency
_DASH_STAMP = ORBIT_DIR / ".dash-stamp"


def _dash_background_loop():
    """Refresh dash files every DASH_INTERVAL in background.

    Polls _dash_stop every _DASH_STOP_POLL seconds so shell exit terminates
    the daemon promptly (otherwise it would linger up to DASH_INTERVAL).
    Uses a timestamp file so multiple shells don't duplicate work.
    """
    import time
    last_refresh = time.time()
    while True:
        # Wait briefly; if stop signal arrives, return immediately.
        if _dash_stop.wait(_DASH_STOP_POLL):
            return
        if time.time() - last_refresh < DASH_INTERVAL:
            continue
        try:
            if _DASH_STAMP.exists():
                age = time.time() - _DASH_STAMP.stat().st_mtime
                if age < DASH_INTERVAL * 0.9:
                    last_refresh = time.time()
                    continue
            from orbit import run_dash
            run_dash(silent=True)
            _DASH_STAMP.touch()
            last_refresh = time.time()
        except Exception:
            pass


# ── Shell-start hook actions (chain `shell_start`) ────────────────────────────
#
# See HOOKSYSTEM.md §6.3. Each function is a registered hook action; the chain
# is bound to the temporal trigger `shell_startup` and runs once when the
# shell starts.

def _action_doctor_startup(ctx):
    """Background doctor check + interactive fix prompt."""
    from core.doctor import doctor_background
    doctor_thread, doctor_issues = doctor_background()
    doctor_thread.join(timeout=5)

    if doctor_thread.is_alive():
        print("  🏥 Doctor aún revisando... (ejecuta 'doctor' manualmente)")
        print()
        return {"ok": True, "msg": "still running"}

    if not doctor_issues:
        return {"ok": True, "msg": "clean"}

    fixable = [i for i in doctor_issues if i.fix]
    unfixable = [i for i in doctor_issues if not i.fix]
    n = len(doctor_issues)
    print(f"  🏥 {n} problema{'s' if n != 1 else ''} de sintaxis encontrado{'s' if n != 1 else ''}:")
    for issue in doctor_issues:
        prefix = "🔧" if issue.fix else "⚠️"
        line_preview = issue.line.strip()[:60]
        print(f"      {prefix} [{issue.project}] {issue.file}:{issue.line_num} — {issue.msg}")
        print(f"        │ {line_preview}")
    print()
    if fixable:
        from core.doctor import _interactive_fix
        _interactive_fix(fixable)
        print()
    if unfixable:
        print(f"  {len(unfixable)} problema{'s' if len(unfixable) != 1 else ''} requiere{'n' if len(unfixable) != 1 else ''} corrección manual.")
        print()
    return {"ok": True, "msg": f"{n} issues ({len(fixable)} fixable)"}


def _action_advance_overdue_recurring(ctx):
    """Auto-advance recurring items past today. See agenda_cmds.startup_advance_past_recurring."""
    from core.agenda_cmds import startup_advance_past_recurring
    adv = startup_advance_past_recurring()
    if adv:
        n = len(adv)
        print(f"  🔄 {n} cita{'s' if n != 1 else ''} recurrente{'s' if n != 1 else ''} avanzada{'s' if n != 1 else ''}:")
        for info in adv:
            print(f"     {info}")
        print()
    return {"ok": True, "msg": f"{len(adv)} advanced"}


def _action_cloud_sync_status_check(ctx):
    """Warn if last background cloud sync failed (reads .cloud-sync.json)."""
    from core.cloudsync import startup_cloud_check
    startup_cloud_check()
    return {"ok": True}


def _action_untracked_check(ctx):
    """Stage tracked + prompt to add untracked (tty-only)."""
    from core.startup import startup_untracked_check
    startup_untracked_check()
    return {"ok": True}


def _action_commit_offer(ctx):
    """Show uncommitted changes and offer commit + push (tty-only)."""
    from core.startup import startup_commit_offer
    startup_commit_offer()
    print()
    return {"ok": True}


def _action_code_update_check(ctx):
    """Check upstream of orbit code repo and offer pull (tty-only)."""
    from core.startup import startup_code_update_check
    startup_code_update_check()
    return {"ok": True}


def _action_cartero_startup(ctx):
    """Start the mail/Slack daemon if cartero.json is configured."""
    from core.cartero import startup_cartero
    startup_cartero()
    return {"ok": True}


def _action_dash_render(ctx):
    """Regenerate panel.md / agenda.md / calendar.md + emit .ics.

    `silent` flag in ctx (default False) skips the leading print() separator
    and runs run_dash silently — used by `day_open` chain at midnight.
    """
    silent = bool((ctx or {}).get("silent")) if isinstance(ctx, dict) else False
    try:
        from orbit import run_dash
        if not silent:
            print()
        run_dash(silent=silent)
        return {"ok": True, "msg": "silent" if silent else "shown"}
    except Exception as e:
        return {"ok": False, "msg": f"{type(e).__name__}: {e}"}


def _action_dash_background_loop_start(ctx):
    """Spawn the hourly dash refresh daemon (polls _dash_stop every 5s)."""
    _dash_stop.clear()
    t = threading.Thread(target=_dash_background_loop, daemon=True)
    t.start()
    return {"ok": True, "msg": "daemon started"}


# Chain composition and bindings live in core/hooks_catalog.json — loaded once
# by hooks.bootstrap() at orbit startup.
from core import hooks as _hooks


# ── Startup sequence ─────────────────────────────────────────────────────────

def _run_startup():
    """Execute the `shell_start` chain. See HOOKSYSTEM.md §6.3 for the action list."""
    _hooks.fire("shell_startup", verbosity="quiet")
    print()


# ── Shutdown sequence ────────────────────────────────────────────────────────

def _run_shutdown():
    """Refresh dash files + offer to commit + push pending changes before exiting the shell."""
    from core.startup import startup_untracked_check, startup_commit_offer
    print()
    # Refresh panel.md and agenda.md so they're up-to-date for commit & cloud render
    try:
        from orbit import run_dash
        run_dash(silent=True)
        print("  ✓ dash actualizado (panel.md + agenda.md)")
        print()
    except Exception:
        pass
    startup_untracked_check()
    startup_commit_offer()


# ── Shell REPL ───────────────────────────────────────────────────────────────

def run_shell(editor: str = ""):
    """Interactive Orbit shell with readline, tab completion, and startup checks."""

    # Enable persistent history
    history_file = Path.home() / ".orbit_history"
    try:
        readline.read_history_file(history_file)
    except (FileNotFoundError, OSError):
        pass
    readline.set_history_length(500)

    COMMANDS = ["task", "ms", "ev", "hl", "view", "note", "commit", "deliver",
                "import", "ls", "log", "search", "open", "report", "agenda", "dash", "wks",
                "mail", "doctor", "archive", "undo", "help", "project", "claude", "end", "exit", "quit"]

    # Shell commands allowed to run from the Orbit REPL
    SHELL_COMMANDS = {"git", "cat", "head", "tail", "pwd", "echo"}

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
    from orbit import run_command

    while True:
        # Midnight check — fire `day_open` chain (see HOOKSYSTEM.md §6.4).
        if _date.today() != shell_start_date:
            print()
            print("☀️ Nuevo día. Avanzando recurrentes...")
            _hooks.fire("day_changed", ctx={"silent": True}, verbosity="quiet")
            print()
            shell_start_date = _date.today()

        try:
            from core.cartero import get_prompt_indicator
            _mail = get_prompt_indicator()
            _prompt = f"{ORBIT_PROMPT}{_mail} " if _mail else f"{ORBIT_PROMPT} "
            line = input(_prompt).strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not line or line.startswith("#"):
            continue
        if line in ("exit", "quit", "q"):
            break
        if line == "end":
            _run_shutdown()
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

        # wks — delegate to ~/work/scripts/wks
        if tokens[0] == "wks":
            import subprocess
            wks_script = Path.home() / "work" / "scripts" / "wks"
            subprocess.run([str(wks_script)] + tokens[1:], cwd=ORBIT_DIR)
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

        from core.undo import track_operation

        import io
        exit_code = 0
        captured_err = ""
        old_stderr = sys.stderr
        sys.stderr = io.StringIO()
        try:
            with track_operation(line):
                exit_code = run_command(tokens)
        except SystemExit as e:
            exit_code = e.code if isinstance(e.code, int) else 1
        finally:
            captured_err = sys.stderr.getvalue()
            sys.stderr = old_stderr
            if captured_err:
                sys.stdout.write(captured_err)
                sys.stdout.flush()

        # On error, offer Claude suggestions
        if exit_code != 0 and captured_err:
            from core.claude import suggest_on_error
            chosen = suggest_on_error(tokens, captured_err.strip())
            if chosen:
                cmd = chosen.removeprefix("orbit ")
                try:
                    new_tokens = shlex.split(cmd)
                except ValueError:
                    continue
                with track_operation(cmd):
                    try:
                        run_command(new_tokens)
                    except SystemExit:
                        pass

    _dash_stop.set()  # stop background dash refresh

    readline.write_history_file(history_file)

    print()
    print("¡Hasta pronto!")

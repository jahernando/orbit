"""shell.py — interactive Orbit shell with startup sequence.

Startup flow:
  1. Doctor — validate data integrity, offer fixes
  2. Untracked files — prompt to stage new files
  3. Commit + push — offer to commit staged changes
  4. Code update — check for new code in orbit repo
  5. gsync in background (fire & forget) + schedule reminders
"""

import json
import readline
import shlex
import sys
import threading
from datetime import date as _date, datetime as _datetime
from pathlib import Path

from core.config import ORBIT_HOME as ORBIT_DIR, ORBIT_CODE, ORBIT_PROMPT


# ── Watchdog: periodic refresh + doctor pre-check ───────────────────────────
#
# Captura drift introducido por ediciones manuales de .md (en Obsidian o
# editor externo) entre comandos CLI de orbit. Cada tick:
#   1. Doctor sobre el workspace.
#   2. Si hay issues → escribe .doctor-pending (la prompt lo surface);
#      NO regenera derivados (panel/agenda/ics/ring) para no propagar basura.
#   3. Si limpio → _run_full_refresh_coalesced (dash + ring + ics) y borra
#      .doctor-pending si existía.
#
# Configurable en `<workspace>/orbit.json` → "watchdog":
#   { "enabled": true, "interval_minutes": 60 }   // clamped [5, 1440]

_dash_stop = threading.Event()

_WATCHDOG_DEFAULT_ENABLED = True
_WATCHDOG_DEFAULT_INTERVAL_MIN = 60
_WATCHDOG_MIN_MIN, _WATCHDOG_MAX_MIN = 5, 1440
_DASH_STOP_POLL = 5   # seconds — shutdown latency

_DASH_STAMP = ORBIT_DIR / ".dash-stamp"
_DOCTOR_PENDING = ORBIT_DIR / ".doctor-pending"


def _load_watchdog_config(workspace_root: Path) -> dict:
    """Read <workspace>/orbit.json → 'watchdog' section.

    Defaults: enabled=True, interval_minutes=60. The 'interval_minutes'
    value is clamped to [_WATCHDOG_MIN_MIN, _WATCHDOG_MAX_MIN]; bad types
    or out-of-range fall back silently.
    """
    cfg = {
        "enabled": _WATCHDOG_DEFAULT_ENABLED,
        "interval_minutes": _WATCHDOG_DEFAULT_INTERVAL_MIN,
    }
    path = workspace_root / "orbit.json"
    if not path.exists():
        return cfg
    try:
        data = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return cfg
    user = data.get("watchdog")
    if not isinstance(user, dict):
        return cfg
    if "enabled" in user:
        cfg["enabled"] = bool(user["enabled"])
    if "interval_minutes" in user:
        try:
            v = int(user["interval_minutes"])
            if _WATCHDOG_MIN_MIN <= v <= _WATCHDOG_MAX_MIN:
                cfg["interval_minutes"] = v
        except (TypeError, ValueError):
            pass
    return cfg


def _write_doctor_pending(issue_count: int) -> None:
    """Write .doctor-pending JSON marker for the REPL prompt to surface."""
    payload = {
        "timestamp": _datetime.now().strftime("%H:%M"),
        "count":     issue_count,
    }
    try:
        tmp = _DOCTOR_PENDING.with_suffix(".pending.tmp")
        tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
        tmp.replace(_DOCTOR_PENDING)
    except OSError:
        pass


def _clear_doctor_pending() -> None:
    """Remove .doctor-pending if it exists (no-op otherwise)."""
    try:
        _DOCTOR_PENDING.unlink()
    except (FileNotFoundError, OSError):
        pass


def _watchdog_tick() -> dict:
    """One iteration of the watchdog. Testable in isolation.

    Returns a status dict so tests can assert behavior:
      {"status": "issues", "count": N}  — doctor found problems
      {"status": "clean"}                — doctor clean, full refresh ran
      {"status": "error", "msg": "..."}  — doctor itself threw
    """
    try:
        from views.doctor.doctor import check_all_projects
        issues = check_all_projects()
    except Exception as exc:
        return {"status": "error", "msg": f"{type(exc).__name__}: {exc}"}

    if issues:
        _write_doctor_pending(len(issues))
        return {"status": "issues", "count": len(issues)}

    _clear_doctor_pending()
    try:
        from orbit import _run_full_refresh_coalesced
        _run_full_refresh_coalesced()
    except Exception:
        pass
    return {"status": "clean"}


def _watchdog_loop():
    """Background daemon thread: tick every `interval_minutes` (from config).

    Polls _dash_stop every _DASH_STOP_POLL seconds so shell exit terminates
    promptly (otherwise daemon could linger up to one interval). Returns
    immediately if watchdog is disabled in config.
    """
    import time
    cfg = _load_watchdog_config(ORBIT_DIR)
    if not cfg["enabled"]:
        return
    interval_seconds = cfg["interval_minutes"] * 60
    last_tick = time.time()
    while True:
        if _dash_stop.wait(_DASH_STOP_POLL):
            return
        if time.time() - last_tick < interval_seconds:
            continue
        _watchdog_tick()  # internal try/except absorbs errors
        last_tick = time.time()


# REPL session state for one-shot doctor pending notification.
_doctor_pending_shown = False


def _maybe_show_doctor_pending() -> None:
    """Si .doctor-pending existe y aún no se mostró en esta sesión, print 1 línea.

    No borra el fichero — persiste hasta que el watchdog corra limpio o
    el usuario ejecute `doctor` (que limpia el state al arreglar).
    """
    global _doctor_pending_shown
    if _doctor_pending_shown:
        return
    if not _DOCTOR_PENDING.exists():
        return
    try:
        data = json.loads(_DOCTOR_PENDING.read_text())
        ts = data.get("timestamp", "?")
        n = data.get("count", "?")
        plural = "s" if isinstance(n, int) and n != 1 else ""
        print(f"  🏥 Doctor ({ts}): {n} problema{plural} detectado{plural} "
              f"— ejecuta `doctor`")
        _doctor_pending_shown = True
    except (json.JSONDecodeError, OSError):
        pass


# ── Shell-start hook actions (chain `shell_start`) ────────────────────────────
#
# See HOOKSYSTEM.md §6.3. Each function is a registered hook action; the chain
# is bound to the temporal trigger `shell_startup` and runs once when the
# shell starts.

def _action_doctor_startup(ctx):
    """Background doctor check + interactive fix prompt."""
    from views.doctor.doctor import doctor_background
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
        from views.doctor.doctor import _interactive_fix
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


def _action_save_offer(ctx):
    """Stage tracked + prompt untracked + offer save (tty-only).

    Consolidación 2026-05-16 de las dos actions previas
    (`untracked_check` + `commit_offer`) en un solo bloque conceptual
    "save". El usuario las pensaba como un único paso del startup
    ("¿quieres guardar?") por lo que tiene sentido un único action.
    """
    from core.startup import startup_untracked_check, startup_commit_offer
    startup_untracked_check()
    startup_commit_offer()
    print()
    return {"ok": True}


def _action_code_update_check(ctx):
    """Check upstream of orbit code repo and offer pull (tty-only)."""
    from core.startup import startup_code_update_check
    startup_code_update_check()
    return {"ok": True}


def _action_secretary_refresh(ctx):
    """Regenerate the secretary viewers: panel + agenda-next + calendar + projects.

    Salida local únicamente — los .md viven en `📋secretary/`. La
    proyección a HTML (cloud) es trabajo del action `render_to_cloud`,
    y los .ics son del action `ics_emit_workspace` (ambos en commit_post).

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


def _action_daemons_startup(ctx):
    """Arranca los daemons del workspace: cartero (mail/Slack) + watchdog loop.

    Consolidación 2026-05-16 de `cartero_startup` + `dash_background_loop_start`,
    luego renombrado a watchdog (doctor + full-refresh) en 2026-05-16 PM.
    Son daemons ortogonales (mail/Slack notifier vs periodic doctor+refresh)
    pero conceptualmente forman un único grupo "spawn workspace daemons".

    Cartero es no-op si no hay `cartero.json` configurado. El watchdog
    poll _dash_stop cada 5s y se termina limpiamente en _run_shutdown.
    Si watchdog está disabled en orbit.json, el thread retorna inmediatamente.
    """
    from core.cartero_invoke import startup_cartero
    startup_cartero()

    _dash_stop.clear()
    t = threading.Thread(target=_watchdog_loop, daemon=True)
    t.start()
    return {"ok": True, "msg": "daemons started"}


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

    COMMANDS = ["task", "ms", "ev", "hl", "view", "note", "save", "commit", "deliver",
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

        # Watchdog deferred notification (one-shot per session).
        _maybe_show_doctor_pending()

        try:
            line = input(f"{ORBIT_PROMPT} ").strip()
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

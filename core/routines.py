"""routines.py — orbit start / orbit end routines.

orbit start:
  1. Status summary (1 line: active/stopped/sleeping counts)
  2. Current focus (all periods)
  3. Prompt for missing focus in current period(s)
  4. Detect missed yesterday session → offer to create eval
  5. Record start time in .orbit/session.json

orbit end:
  1. Activity summary for focus projects today
  2. Create/update daily evaluation note
  3. If end of week → weekly evaluation
  4. If end of month → monthly evaluation
  5. Open highest-priority evaluation note
  6. Record end time in .orbit/session.json
"""

import calendar as _cal
import json
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

from core.log import PROJECTS_DIR, find_logbook_file, find_proyecto_file
from core.activity import has_activity_in, run_status
from core.focus import (
    get_focus, get_current_focus, run_focus,
    _week_key, _period_key, PERIODS, PERIOD_LABELS, focus_line,
)
from core.evaluation import create_or_update_eval, eval_path
from core.open import open_file

# ── session tracking ───────────────────────────────────────────────────────────

_SESSION_FILE = Path(__file__).parent.parent / ".orbit" / "session.json"


def _load_session() -> dict:
    if _SESSION_FILE.exists():
        try:
            return json.loads(_SESSION_FILE.read_text())
        except Exception:
            pass
    return {}


def _save_session(data: dict):
    _SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
    _SESSION_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")


# ── helpers ────────────────────────────────────────────────────────────────────

def _status_summary() -> str:
    """Return a one-line status count string: 🟢 N  🟡 N  🔴 N."""
    today = date.today()
    d30   = today - timedelta(days=30)
    d60   = today - timedelta(days=60)
    counts = {"activo": 0, "parado": 0, "durmiendo": 0}

    if not PROJECTS_DIR.exists():
        return ""

    from core.tasks import load_project_meta

    for proj_dir in PROJECTS_DIR.iterdir():
        if not proj_dir.is_dir():
            continue
        ppath = find_proyecto_file(proj_dir)
        if not ppath:
            continue
        meta = load_project_meta(ppath)
        if "completado" in meta["estado_raw"]:
            continue
        logbook = find_logbook_file(proj_dir)
        if has_activity_in(logbook, d30, today):
            counts["activo"] += 1
        elif has_activity_in(logbook, d60, today):
            counts["parado"] += 1
        else:
            counts["durmiendo"] += 1

    return (
        f"🟢 {counts['activo']} activos  "
        f"🟡 {counts['parado']} parados  "
        f"🔴 {counts['durmiendo']} durmiendo"
    )


def _had_activity_yesterday() -> bool:
    """Return True if any logbook had an entry yesterday."""
    yesterday = date.today() - timedelta(days=1)
    if not PROJECTS_DIR.exists():
        return False
    for proj_dir in PROJECTS_DIR.iterdir():
        if not proj_dir.is_dir():
            continue
        logbook = find_logbook_file(proj_dir)
        if has_activity_in(logbook, yesterday, yesterday):
            return True
    return False


def _print_focus_summary():
    """Print current focus for all three periods."""
    today = date.today()
    current = get_current_focus()
    for p in ("month", "week", "day"):
        key      = _period_key(p, today)
        projects = current[p]
        print(f"  {PERIOD_LABELS[p]} ({key}): {focus_line(projects)}")


def _prompt_missing_focus(today: date):
    """Interactively prompt for any period that has no focus set."""
    if not sys.stdin.isatty():
        return
    current = get_current_focus()
    for p in ("month", "week", "day"):
        if not current[p]:
            try:
                resp = input(
                    f"\n  ⚠️  Sin foco para {PERIOD_LABELS[p]}. ¿Establecer ahora? [S/n]: "
                ).strip().lower()
            except (EOFError, KeyboardInterrupt):
                print()
                return
            if resp in ("", "s", "si", "sí", "y", "yes"):
                run_focus(period=p, interactive=True)


def _activity_today(focus_projects: list) -> list:
    """Return list of (project_name, entry_count) for focus projects today."""
    today = date.today()
    result = []
    for name in focus_projects:
        for proj_dir in PROJECTS_DIR.iterdir():
            if proj_dir.is_dir() and name.lower() in proj_dir.name.lower():
                logbook = find_logbook_file(proj_dir)
                count = 0
                if logbook and logbook.exists():
                    for line in logbook.read_text().splitlines():
                        s = line.strip()
                        if len(s) >= 10 and s[:10] == today.isoformat():
                            count += 1
                result.append((proj_dir.name, count))
                break
    return result


# ── routines ───────────────────────────────────────────────────────────────────

def run_start(editor: str = "typora") -> int:
    today     = date.today()
    day_name  = today.strftime("%A")

    print(f"\n🚀 ORBIT START — {today.isoformat()} ({day_name})")
    print("─" * 50)

    # 1. Status summary
    summary = _status_summary()
    if summary:
        print(f"\n{summary}")

    # 2. Current focus
    print("\n── Foco actual ──")
    _print_focus_summary()

    # 3. Prompt for missing focus
    _prompt_missing_focus(today)

    # 4. Detect missed yesterday session
    yesterday = today - timedelta(days=1)
    if sys.stdin.isatty() and _had_activity_yesterday():
        yesterday_eval = eval_path("day", yesterday)
        if yesterday_eval and not yesterday_eval.exists():
            try:
                resp = input(
                    f"\n  ⚠️  Ayer ({yesterday}) hubo actividad sin evaluación. "
                    f"¿Crear ahora? [S/n]: "
                ).strip().lower()
            except (EOFError, KeyboardInterrupt):
                print()
                resp = "n"
            if resp in ("", "s", "si", "sí", "y", "yes"):
                create_or_update_eval("day", yesterday, open_after=False)

    # 5. Record session start
    session = _load_session()
    session["last_start"] = today.isoformat()
    _save_session(session)

    print()
    return 0


def run_end(editor: str = "typora") -> int:
    today = date.today()
    last_day = _cal.monthrange(today.year, today.month)[1]

    print(f"\n🌙 ORBIT END — {today.isoformat()}")
    print("─" * 50)

    # 1. Show today's focus activity
    focus_today = get_focus("day", today)
    if focus_today:
        print("\n── Actividad de hoy (proyectos en foco) ──")
        activity = _activity_today(focus_today)
        for name, count in activity:
            icon = "🍅" if count > 0 else "⬜"
            suffix = f"{count} entrada{'s' if count != 1 else ''}" if count > 0 else "sin actividad hoy"
            print(f"  {icon} {name} — {suffix}")
    else:
        print("\n  Sin proyectos en foco para hoy. Usa 'orbit focus day --set <proyecto>'.")

    # 2. Always create/update daily eval
    print()
    open_path = create_or_update_eval("day", today, open_after=False, editor=editor)

    # 3. End of week (Fri/Sat/Sun) → weekly eval
    is_end_of_week = today.weekday() in (4, 5, 6)
    if is_end_of_week:
        weekly = create_or_update_eval("week", today, open_after=False, editor=editor)
        if weekly:
            open_path = weekly  # higher priority

    # 4. End of month (last 3 days) → monthly eval
    is_end_of_month = today.day >= last_day - 2
    if is_end_of_month:
        monthly = create_or_update_eval("month", today, open_after=False, editor=editor)
        if monthly:
            open_path = monthly  # highest priority

    # 5. Open highest-priority note
    if open_path and open_path.exists():
        print(f"\n  Abriendo evaluación en {editor}…")
        open_file(open_path, editor)

    # 6. Record session end
    session = _load_session()
    session["last_end"] = today.isoformat()
    _save_session(session)

    print()
    print("¡Hasta mañana! Recuerda reflexionar en la nota de evaluación.")
    print()
    return 0

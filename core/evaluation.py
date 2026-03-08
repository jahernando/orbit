"""evaluation.py — evaluation notes for the ☀️mission project.

Evaluation notes are stored inside the mission project:
  🚀proyectos/☀️mission/diario/YYYY-MM-DD.md
  🚀proyectos/☀️mission/semanal/YYYY-Wnn.md
  🚀proyectos/☀️mission/mensual/YYYY-MM.md

Stats block (auto-updated on every `orbit end`):
  <!-- orbit:eval-stats:start -->
  <!-- orbit:eval-stats:end -->

Reflection sections (created once, never overwritten).
"""

import re
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

from core.log import PROJECTS_DIR, VALID_TYPES, find_logbook_file
from core.activity import TYPE_EMOJI, get_logbook_activity, has_activity_in
from core.focus import get_focus, _week_key, _period_key, focus_line
from core.open import open_file

# ── paths ──────────────────────────────────────────────────────────────────────

_EVAL_STATS_START = "<!-- orbit:eval-stats:start -->"
_EVAL_STATS_END   = "<!-- orbit:eval-stats:end -->"


def _mission_dir() -> Optional[Path]:
    """Return the ☀️mission project directory, or None if not found."""
    if not PROJECTS_DIR.exists():
        return None
    for d in PROJECTS_DIR.iterdir():
        if d.is_dir() and "mission" in d.name.lower():
            return d
    return None


def eval_path(period: str, d: date = None) -> Optional[Path]:
    """Return the Path for an evaluation note, or None if mission dir not found."""
    d = d or date.today()
    mission = _mission_dir()
    if not mission:
        return None
    subdir = {"day": "diario", "week": "semanal", "month": "mensual"}[period]
    key = _period_key(period, d)
    return mission / subdir / f"{key}.md"


# ── helpers ────────────────────────────────────────────────────────────────────

def _inject_block(dest: Path, block: str) -> None:
    """Replace content between eval-stats markers; append if markers absent."""
    if not dest.exists():
        return
    text = dest.read_text()
    injected = f"{_EVAL_STATS_START}\n{block}{_EVAL_STATS_END}"
    if _EVAL_STATS_START in text:
        text = re.sub(
            rf"{re.escape(_EVAL_STATS_START)}.*?{re.escape(_EVAL_STATS_END)}",
            injected,
            text,
            flags=re.DOTALL,
        )
    else:
        if not text.endswith("\n"):
            text += "\n"
        text += "\n" + injected + "\n"
    dest.write_text(text)


def _has(dest: Path, text: str) -> bool:
    return dest.exists() and text in dest.read_text()


def _count_entries(project_dir: Path, start: date, end: date) -> tuple:
    """Return (total_count, by_type_dict) for a project in [start, end]."""
    logbook = find_logbook_file(project_dir)
    if not logbook or not logbook.exists():
        return 0, {}
    _, counts = get_logbook_activity(logbook, start, end)
    total = sum(counts.values())
    return total, counts



def _stats_block(focus_projects: list, start: date, end: date) -> str:
    """Build the stats block content for the eval-stats marker.

    Always includes the current focus line so it stays up-to-date on every update.
    """
    lines = [f"**Foco:** {focus_line(focus_projects)}", ""]
    grand_total = 0

    if PROJECTS_DIR.exists() and focus_projects:
        for proj_name in focus_projects:
            for proj_dir in PROJECTS_DIR.iterdir():
                if proj_dir.is_dir() and proj_name.lower() in proj_dir.name.lower():
                    total, by_type = _count_entries(proj_dir, start, end)
                    grand_total += total
                    parts = [
                        f"{TYPE_EMOJI[t]}×{by_type[t]}"
                        for t in VALID_TYPES if by_type.get(t, 0) > 0
                    ]
                    suffix = f" ({', '.join(parts)})" if parts else ""
                    lines.append(f"- {proj_dir.name} — {total} entrada{'s' if total != 1 else ''}{suffix}")
                    break

    lines.append(f"- Total: {grand_total} entrada{'s' if grand_total != 1 else ''}")
    return "\n".join(lines) + "\n"


# ── note templates ─────────────────────────────────────────────────────────────

def _reflection_day() -> str:
    return (
        "\n## 📝 Reflexión\n\n"
        "### ¿Qué fue bien hoy?\n\n"
        "### ¿Qué mejorar?\n\n"
        "### 📌 Decisiones\n\n"
    )


def _reflection_week() -> str:
    return (
        "\n## 📝 Reflexión\n\n"
        "### Balance de la semana\n\n"
        "### 🎯 Objetivos para la semana siguiente\n\n"
        "### 📌 Decisiones de la semana\n\n"
    )


def _reflection_month() -> str:
    return (
        "\n## 📝 Reflexión\n\n"
        "### Balance del mes\n\n"
        "### 🎯 Objetivos para el mes siguiente\n\n"
        "### 📌 Decisiones del mes\n\n"
    )


def _build_day_note(d: date, focus: list) -> str:
    return (
        f"# Evaluación — {d.isoformat()}\n\n"
        f"## 📊 Actividad\n\n"
        f"{_EVAL_STATS_START}\n"
        f"{_EVAL_STATS_END}\n"
        + _reflection_day()
    )


def _build_week_note(d: date, focus: list) -> str:
    wkey = _week_key(d)
    mon  = d - timedelta(days=d.weekday())
    sun  = mon + timedelta(days=6)
    return (
        f"# Evaluación — Semana {wkey} ({mon.isoformat()} — {sun.isoformat()})\n\n"
        f"## 📊 Actividad de la semana\n\n"
        f"{_EVAL_STATS_START}\n"
        f"{_EVAL_STATS_END}\n"
        + _reflection_week()
    )


def _build_month_note(d: date, focus: list) -> str:
    month_str = d.strftime("%Y-%m")
    return (
        f"# Evaluación — Mes {month_str}\n\n"
        f"## 📊 Actividad del mes\n\n"
        f"{_EVAL_STATS_START}\n"
        f"{_EVAL_STATS_END}\n"
        + _reflection_month()
    )


# ── public API ─────────────────────────────────────────────────────────────────

def create_or_update_eval(period: str, d: date = None, open_after: bool = False,
                          editor: str = "typora") -> Optional[Path]:
    """Create (or update stats in) an evaluation note for a period.

    Returns the Path of the note, or None on failure.
    Stats block is always refreshed.
    Reflection scaffold is written once and never overwritten.
    """
    d = d or date.today()
    dest = eval_path(period, d)
    if dest is None:
        print("⚠️  No se encontró el proyecto ☀️mission.")
        return None

    dest.parent.mkdir(parents=True, exist_ok=True)
    focus = get_focus(period, d)

    # Date range for the period
    if period == "day":
        start, end = d, d
    elif period == "week":
        start = d - timedelta(days=d.weekday())
        end   = start + timedelta(days=6)
    else:  # month
        import calendar as _cal
        start = date(d.year, d.month, 1)
        end   = date(d.year, d.month, _cal.monthrange(d.year, d.month)[1])

    # Create note if missing
    if not dest.exists():
        builders = {"day": _build_day_note, "week": _build_week_note, "month": _build_month_note}
        dest.write_text(builders[period](d, focus))
        print(f"✓ Evaluación creada: {dest.relative_to(PROJECTS_DIR.parent)}")
    else:
        print(f"✓ Actualizando stats: {dest.relative_to(PROJECTS_DIR.parent)}")

    # Always update stats block
    block = _stats_block(focus, start, end)
    _inject_block(dest, block)

    # Inject reflection scaffold once
    labels = {"day": _reflection_day, "week": _reflection_week, "month": _reflection_month}
    guard  = {"day": "### ¿Qué fue bien", "week": "### Balance de la semana",
               "month": "### Balance del mes"}
    if not _has(dest, guard[period]):
        text = dest.read_text()
        if not text.endswith("\n"):
            text += "\n"
        dest.write_text(text + labels[period]())

    if open_after:
        open_file(dest, editor)

    return dest


def run_eval(period: Optional[str] = None, date_str: Optional[str] = None,
             open_after: bool = True, editor: str = "typora") -> int:
    """CLI entry point: create/update evaluation note for the given period."""
    d = date.fromisoformat(date_str) if date_str else date.today()

    if period and period not in ("day", "week", "month"):
        print(f"Error: periodo desconocido '{period}'. Usa day, week o month.")
        return 1

    if period:
        dest = create_or_update_eval(period, d, open_after=open_after, editor=editor)
        return 0 if dest else 1

    # No period specified → create/update all three
    ok = True
    for p in ("day", "week", "month"):
        dest = create_or_update_eval(p, d, open_after=False, editor=editor)
        if dest is None:
            ok = False
    return 0 if ok else 1

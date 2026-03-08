import calendar as _cal
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

from core.log import VALID_TYPES, find_logbook_file, find_proyecto_file, log_to_mission
from core.open import open_file
from core.tasks import TYPE_MAP, load_project_meta
from core.activity import has_activity_in, TYPE_EMOJI
from core.focus import _week_key
from core.reports import (
    _inject_block, _count_focus_entries, _format_valoracion_stats_month,
    _VALORACION_STATS_START, _VALORACION_STATS_END, run_dayreport,
)

PROJECTS_DIR   = Path(__file__).parent.parent / "🚀proyectos"
MISION_LOG_DIR = Path(__file__).parent.parent / "☀️mision-log"
TEMPLATES_DIR  = Path(__file__).parent.parent / "📐templates"

DIARIO_DIR  = MISION_LOG_DIR / "diario"
SEMANAL_DIR = MISION_LOG_DIR / "semanal"
MENSUAL_DIR = MISION_LOG_DIR / "mensual"


MAX_MONTH_FOCUS = 6

_TYPE_ORDER = ["investigacion", "docencia", "gestion", "formacion", "software", "personal", "mision"]
_TYPE_LABELS = {
    "investigacion": "🌀 Investigación",
    "docencia":      "📚 Docencia",
    "gestion":       "⚙️ Gestión",
    "formacion":     "📖 Formación",
    "software":      "💻 Software",
    "personal":      "🌿 Personal",
    "mision":        "☀️ Misión",
}


def _active_projects_by_type() -> dict:
    """Return active projects grouped by type, ordered by _TYPE_ORDER, sorted by priority within each group."""
    from core.tasks import load_project_meta, find_proyecto_file
    PRIORITY_ORDER = {"alta": 0, "media": 1, "baja": 2}
    groups: dict = {t: [] for t in _TYPE_ORDER}
    for project_dir in sorted(PROJECTS_DIR.iterdir()):
        if not project_dir.is_dir():
            continue
        proyecto_path = find_proyecto_file(project_dir)
        if not proyecto_path or not proyecto_path.exists():
            continue
        meta = load_project_meta(proyecto_path)
        if "completado" in meta["estado_raw"] or "durmiendo" in meta["estado_raw"]:
            continue
        tipo_raw = meta["tipo_raw"]
        prio = next((k for k in PRIORITY_ORDER if k in meta["prioridad_raw"]), "baja")
        bucket = next((t for t in _TYPE_ORDER if t in tipo_raw), "personal")
        groups[bucket].append((PRIORITY_ORDER[prio], project_dir.name))
    result = {}
    for t in _TYPE_ORDER:
        if groups[t]:
            groups[t].sort()
            result[t] = [name for _, name in groups[t]]
    return result


def _top_active_projects(max_count: int) -> list:
    """Return up to max_count active project names sorted by priority (non-TTY fallback)."""
    from core.tasks import load_project_meta, find_proyecto_file
    PRIORITY_ORDER = {"alta": 0, "media": 1, "baja": 2}
    results = []
    for project_dir in sorted(PROJECTS_DIR.iterdir()):
        if not project_dir.is_dir():
            continue
        proyecto_path = find_proyecto_file(project_dir)
        if not proyecto_path or not proyecto_path.exists():
            continue
        meta = load_project_meta(proyecto_path)
        if "completado" in meta["estado_raw"] or "durmiendo" in meta["estado_raw"]:
            continue
        prio = next((k for k in PRIORITY_ORDER if k in meta["prioridad_raw"]), "baja")
        results.append((PRIORITY_ORDER[prio], project_dir.name))
    results.sort()
    return [name for _, name in results[:max_count]]


def _prompt_focus_grouped(groups: dict, highlighted: list, max_count: int, label: str) -> list:
    """Show projects grouped by type. User types names (partial), not numbers."""
    print(f"\n{label}:")
    if highlighted:
        print(f"  🎯 Sugeridos: {'  ·  '.join(highlighted)}")
    for tipo, names in groups.items():
        remaining = [n for n in names if n not in highlighted]
        if not remaining:
            continue
        print(f"  {_TYPE_LABELS.get(tipo, tipo)}: {'  ·  '.join(remaining)}")
    plural = f"hasta {max_count}" if max_count > 1 else "uno"
    print(f"Escribe {plural} (nombre parcial, coma para separar, intro = ninguno):")
    try:
        resp = input("> ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return []
    if not resp:
        return []
    selected = []
    for token in [t.strip() for t in resp.split(",") if t.strip()]:
        if token not in selected:
            selected.append(token)
    return selected[:max_count]


def _week_bounds(d: date) -> tuple:
    monday = d - timedelta(days=d.weekday())
    return monday, monday + timedelta(days=6)


def _write(dest: Path, content: str, copy: Optional[str], force: bool) -> int:
    if dest.exists() and not force:
        print(f"Ya existe: {dest}  (usa --force para sobreescribir)")
        return 1
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(content)
    print(f"✓ {'Copiado' if copy else 'Creado'} {dest}")
    return 0


# ── reminders ────────────────────────────────────────────────────────────────

def _schedule_day_reminders(target: date, dest: Path) -> None:
    try:
        from core.reminders import schedule_today_reminders, inject_reminders_into_note
        scheduled = schedule_today_reminders(target)
        if scheduled:
            inject_reminders_into_note(dest, scheduled)
            print(f"⏰ {len(scheduled)} recordatorio(s) programado(s) en Reminders")
    except Exception:
        pass  # never block orbit day


# ── shell startup ─────────────────────────────────────────────────────────────

def run_shell_startup(editor: str = "typora") -> None:
    """Sequential cascade on shell entry: create month/week if missing, always open day."""
    today = date.today()

    month_str    = today.strftime("%Y-%m")
    mensual_path = MENSUAL_DIR / f"{month_str}.md"
    if not mensual_path.exists():
        run_month(date_str=month_str, force=False, focus=None, open_after=False, editor=editor)

    wkey         = _week_key(today)
    semanal_path = SEMANAL_DIR / f"{wkey}.md"
    if not semanal_path.exists():
        run_week(date_str=today.isoformat(), force=False, focus=None, open_after=False, editor=editor)

    # Detect missed session: yesterday's note exists but run_dayreport never ran
    # (stats content is absent — the template has the markers but no injected data)
    yesterday      = today - timedelta(days=1)
    yesterday_note = DIARIO_DIR / f"{yesterday.isoformat()}.md"
    if (yesterday_note.exists()
            and "### 📊 Actividad" not in yesterday_note.read_text()
            and sys.stdin.isatty()):
        resp = input(
            f"⚠️  La nota de ayer ({yesterday}) no tiene reporte. ¿Inyectar ahora? [s/N] "
        ).strip().lower()
        if resp in ("s", "si", "sí", "y", "yes"):
            run_dayreport(date_str=yesterday.isoformat(), inject=True,
                          output=None, open_after=False, editor=editor)

    run_day(date_str=None, force=False, focus=None, open_after=True, prompt=False)


# ── day ──────────────────────────────────────────────────────────────────────

def _ensure_cascade(target: date, editor: str, open_after: bool = False) -> str:
    """Create month and week notes if they don't exist. Returns the week key."""
    month_str    = target.strftime("%Y-%m")
    mensual_path = MENSUAL_DIR / f"{month_str}.md"
    if not mensual_path.exists():
        print(f"  → creando nota mensual {month_str}…")
        run_month(date_str=month_str, force=False, focus=None,
                  open_after=open_after, editor=editor)

    wkey         = _week_key(target)
    semanal_path = SEMANAL_DIR / f"{wkey}.md"
    if not semanal_path.exists():
        print(f"  → creando nota semanal {wkey}…")
        run_week(date_str=target.isoformat(), force=False, focus=None,
                 open_after=open_after, editor=editor)
    return wkey


def run_day(date_str: Optional[str], force: bool, focus: list = None,
            open_after: bool = True, editor: str = "typora", prompt: bool = True) -> int:
    target = date.fromisoformat(date_str) if date_str else date.today()
    dest   = DIARIO_DIR / f"{target.isoformat()}.md"

    # ── Note already exists ───────────────────────────────────────────────────
    if dest.exists() and not force:
        _ensure_cascade(target, editor, open_after=False)  # create week/month silently if missing
        if prompt and sys.stdin.isatty():
            print(f"La nota del día ya existe: {dest.name}")
            resp = input("¿Abrir nota existente o crear nueva? [abrir/nueva] (intro = abrir): ").strip().lower()
            if resp in ("nueva", "n", "new"):
                pass  # fall through to create a new note
            else:
                if open_after:
                    print("¡Aquí tienes tu nota del día!")
                    open_file(dest, editor)
                return 0
        else:
            if open_after:
                print("¡Aquí tienes tu nota del día!")
                open_file(dest, editor)
            return 0

    tpl = TEMPLATES_DIR / "diario.md"
    if not tpl.exists():
        print(f"Error: plantilla no encontrada en {tpl}")
        return 1
    content = tpl.read_text().replace("YYYY-MM-DD", target.isoformat())

    # ── Cascade: ensure month and week notes exist ────────────────────────────
    wkey         = _ensure_cascade(target, editor, open_after=False)
    semanal_path = SEMANAL_DIR / f"{wkey}.md"

    # ── Focus: prompt interactively or auto-inherit from semanal (non-TTY) ───
    if not focus:
        if sys.stdin.isatty():
            suggested = _parse_focus_projects(semanal_path, "### 🎯 Proyectos en foco")
            groups = _active_projects_by_type()
            focus = _prompt_focus_grouped(groups, suggested, 1, f"Proyecto en foco — {target.isoformat()}")
        else:
            candidates = _parse_focus_projects(semanal_path, "### 🎯 Proyectos en foco")
            focus = candidates[:1]
            if focus:
                print(f"  → foco día heredado: {focus[0]}")

    rc = _write(dest, content, None, True)  # always overwrite here (guard is above)
    if rc == 0:
        if focus:
            _inject_focus_projects(dest, focus[:1], "### 🎯 Proyecto en foco")
            _elevate_focus_priorities(focus[:1])
        upcoming = _collect_upcoming_tasks(7)
        _inject_block(dest, _format_upcoming_tasks(upcoming), _UPCOMING_START, _UPCOMING_END)
        _sync_calendar_to_day(dest, target)
        _schedule_day_reminders(target, dest)
        if open_after:
            print("¡Aquí tienes tu nota del día!")
            open_file(dest, editor)
    return rc


def _sync_calendar_to_day(dest: Path, target: date) -> None:
    """Fetch calendar events, inject into daily note, and sync to project logbooks."""
    try:
        from core.calendar_sync import fetch_day_events, sync_events_to_logbooks
    except ImportError:
        return

    events = fetch_day_events(target)
    if events is None:
        return  # no credentials, skip silently

    # Inject all events into the daily note
    if events:
        lines = []
        for e in events:
            project_name = e["project_name"]
            suffix = f" → `{project_name}`" if project_name else ""
            lines.append(f"- {e['start_time']}  {e['title']}{suffix}")
        block = "\n".join(lines) + "\n"
        print(f"  📅 {len(events)} evento(s) del calendario")
    else:
        block = "_Sin eventos en el calendario._\n"

    _inject_block(dest, block, _EVENTS_START, _EVENTS_END)

    # Sync events with proyecto: to project logbooks
    synced, _, not_found = sync_events_to_logbooks(events, target, dry_run=False)
    if synced:
        print(f"  ✓  {synced} evento(s) añadido(s) a logbooks de proyectos")


# ── logday ────────────────────────────────────────────────────────────────────

def add_entry_to_day(message: str, tipo: str, path: Optional[str],
                     date_str: Optional[str], open_after: bool = False,
                     editor: str = "typora") -> int:
    """Append a dated logbook-style entry to today's (or given) diario."""
    from core.log import format_entry, _append_entry
    target = date.fromisoformat(date_str) if date_str else date.today()
    dest = DIARIO_DIR / f"{target.isoformat()}.md"

    if not dest.exists():
        tpl = TEMPLATES_DIR / "diario.md"
        if not tpl.exists():
            print(f"Error: plantilla no encontrada en {tpl}")
            return 1
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(tpl.read_text().replace("YYYY-MM-DD", target.isoformat()))
        print(f"✓ Creado {dest}")

    entry = format_entry(message, tipo, path, date_str or target.isoformat())
    _append_entry(dest, entry)
    print(f"✓ [diario/{target.isoformat()}] {entry.strip()}")
    if open_after:
        open_file(dest, editor)
    return 0


def run_logday(message: str, tipo: str, date_str: Optional[str],
               open_after: bool = False, editor: str = "typora") -> int:
    target = date.fromisoformat(date_str) if date_str else date.today()
    dest = DIARIO_DIR / f"{target.isoformat()}.md"

    if not dest.exists():
        tpl = TEMPLATES_DIR / "diario.md"
        if not tpl.exists():
            print(f"Error: plantilla no encontrada en {tpl}")
            return 1
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(tpl.read_text().replace("YYYY-MM-DD", target.isoformat()))
        print(f"✓ Creado {dest}")

    now = datetime.now().strftime("%H:%M")
    entry = f"{now} {message} #{tipo}\n"

    from core.log import _append_entry
    _append_entry(dest, entry)

    print(f"✓ [{target.isoformat()}] {entry.strip()}")
    if open_after:
        open_file(dest, editor)
    return 0


# ── week ─────────────────────────────────────────────────────────────────────

def run_week(date_str: Optional[str], force: bool, focus: list = None,
             open_after: bool = True, editor: str = "typora") -> int:
    d      = date.fromisoformat(date_str) if date_str else date.today()
    wkey   = _week_key(d)
    mon, sun = _week_bounds(d)
    dest   = SEMANAL_DIR / f"{wkey}.md"

    # ── Note already exists ───────────────────────────────────────────────────
    if dest.exists() and not force:
        print(f"La nota ya existe: {dest.name}")
        if sys.stdin.isatty():
            resp = input("¿Inyectar reporte semanal? [s/N] ").strip().lower()
            if resp in ("s", "si", "sí", "y", "yes"):
                run_weekreport(date_str=d.isoformat(), inject=True,
                               output=None, open_after=open_after, editor=editor)
                return 0
        if open_after:
            open_file(dest, editor)
        return 0

    tpl = TEMPLATES_DIR / "semanal.md"
    if not tpl.exists():
        print(f"Error: plantilla no encontrada en {tpl}")
        return 1
    lines = tpl.read_text().split("\n")
    lines[0] = (lines[0]
                .replace("YYYY-Wnn", wkey)
                .replace("YYYY-MM-DD", mon.isoformat(), 1)
                .replace("YYYY-MM-DD", sun.isoformat(), 1))
    content = "\n".join(lines)

    # If no focus given: prompt interactively or auto-inherit from mensual (non-TTY)
    if not focus:
        month_str    = d.strftime("%Y-%m")
        mensual_path = MENSUAL_DIR / f"{month_str}.md"
        if sys.stdin.isatty():
            suggested = _parse_focus_projects(mensual_path, "### 🎯 Proyectos en foco")
            groups = _active_projects_by_type()
            focus = _prompt_focus_grouped(groups, suggested, 2, f"Proyectos en foco — semana {wkey}")
        else:
            candidates = _parse_focus_projects(mensual_path, "### 🎯 Proyectos en foco")
            focus = candidates[:2]
            if focus:
                print(f"  → foco semana heredado: {', '.join(focus)}")

    rc = _write(dest, content, None, force)
    if rc == 0:
        if focus:
            _inject_focus_projects(dest, focus[:2], "### 🎯 Proyectos en foco")
            _elevate_focus_priorities(focus[:2])
        upcoming = _collect_upcoming_tasks(15)
        _inject_block(dest, _format_upcoming_tasks(upcoming), _UPCOMING_START, _UPCOMING_END)
        if open_after:
            open_file(dest, editor)
    return rc


# ── month ─────────────────────────────────────────────────────────────────────

def _apply_monthly_status_degradation(prev_start: date, prev_end: date) -> None:
    """Degrade en marcha→parado and parado→durmiendo for projects with no activity last month."""
    from core.tasks import load_project_meta, update_proyecto_field, find_proyecto_file
    from core.activity import has_activity_in
    from core.log import find_logbook_file

    changed = []
    for project_dir in sorted(PROJECTS_DIR.iterdir()):
        if not project_dir.is_dir():
            continue
        proyecto_path = find_proyecto_file(project_dir)
        if not proyecto_path:
            continue
        meta = load_project_meta(proyecto_path)
        nominal_key = next(
            (k for k in ("en marcha", "parado", "durmiendo", "inicial", "completado")
             if k in meta["estado_raw"]), ""
        )
        if nominal_key not in ("en marcha", "parado"):
            continue
        logbook_path = find_logbook_file(project_dir)
        has_activity = has_activity_in(logbook_path, prev_start, prev_end)
        if not has_activity:
            new_key = "parado" if nominal_key == "en marcha" else "durmiendo"
            update_proyecto_field(proyecto_path, "estado", new_key)
            changed.append((project_dir.name, nominal_key, new_key))

    if changed:
        print("\n  📊 Estados actualizados (sin actividad el mes anterior):")
        for name, old, new in changed:
            arrow = "⏸️" if new == "parado" else "💤"
            print(f"    {arrow} {name}: {old} → {new}")


def run_month(date_str: Optional[str], force: bool, focus: list = None,
              open_after: bool = True, editor: str  = "typora") -> int:
    if date_str:
        y, m = int(date_str[:4]), int(date_str[5:7])
    else:
        today = date.today()
        y, m  = today.year, today.month
    month_str = f"{y}-{m:02d}"
    dest = MENSUAL_DIR / f"{month_str}.md"

    # ── Note already exists ───────────────────────────────────────────────────
    if dest.exists() and not force:
        print(f"La nota ya existe: {dest.name}")
        if sys.stdin.isatty():
            resp = input("¿Inyectar reporte mensual? [s/N] ").strip().lower()
            if resp in ("s", "si", "sí", "y", "yes"):
                from core.monthly import run_monthly
                run_monthly(month_str=month_str, apply=False, output=None,
                            open_after=open_after, editor=editor)
                return 0
        if open_after:
            open_file(dest, editor)
        return 0

    tpl = TEMPLATES_DIR / "mensual.md"
    if not tpl.exists():
        print(f"Error: plantilla no encontrada en {tpl}")
        return 1
    prev_m = m - 1 if m > 1 else 12
    prev_y = y if m > 1 else y - 1
    prev_str = f"{prev_y}-{prev_m:02d}"
    content = (tpl.read_text()
               .replace("← [Mes anterior](../mensual/YYYY-MM.md)",
                        f"← [Mes anterior](./{prev_str}.md)")
               .replace("YYYY-MM", month_str))

    # Apply status degradation based on previous month's activity (before focus prompt)
    prev_start = date(prev_y, prev_m, 1)
    prev_end   = date(prev_y, prev_m, _cal.monthrange(prev_y, prev_m)[1])
    _apply_monthly_status_degradation(prev_start, prev_end)

    # If no focus given: prompt interactively or auto-pick top projects (non-TTY)
    if not focus:
        if sys.stdin.isatty():
            groups = _active_projects_by_type()
            focus = _prompt_focus_grouped(groups, [], MAX_MONTH_FOCUS, f"Proyectos en foco — {month_str}")
        else:
            focus = _top_active_projects(MAX_MONTH_FOCUS)
            if focus:
                print(f"  → foco mes heredado: {', '.join(focus)}")

    rc = _write(dest, content, None, force)
    if rc == 0:
        if focus:
            _inject_focus_projects(dest, focus[:MAX_MONTH_FOCUS], "### 🎯 Proyectos en foco")
            prev_mensual = MENSUAL_DIR / f"{prev_str}.md"
            old_focus = _parse_focus_projects(prev_mensual, "### 🎯 Proyectos en foco")
            _apply_monthly_focus_priorities(focus, old_focus)
        upcoming = _collect_upcoming_tasks(30)
        _inject_block(dest, _format_upcoming_tasks(upcoming), _UPCOMING_START, _UPCOMING_END)
        # Inyectar valoración inicial (focus check pendiente, reflexión vacía)
        y_int, m_int = int(month_str[:4]), int(month_str[5:7])
        month_start = date(y_int, m_int, 1)
        month_end   = date(y_int, m_int, _cal.monthrange(y_int, m_int)[1])
        focus_counts = _count_focus_entries(focus if focus else [], month_start, min(month_end, date.today()))
        stats_block = _format_valoracion_stats_month(focus_counts)
        if stats_block:
            _inject_block(dest, stats_block, _VALORACION_STATS_START, _VALORACION_STATS_END)
        if open_after:
            open_file(dest, editor)
    return rc

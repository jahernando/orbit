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


# ── dayreport / weekreport ────────────────────────────────────────────────────

_WR_START = "<!-- orbit:weekreport:start -->"
_WR_END   = "<!-- orbit:weekreport:end -->"


def _collect_activity(start: date, end: date) -> list:
    """Return list of {name, entries} for projects with activity in [start, end]."""
    import re as _re
    results = []
    if not PROJECTS_DIR.exists():
        return results

    for project_dir in sorted(PROJECTS_DIR.iterdir()):
        if not project_dir.is_dir():
            continue
        logbook_path = find_logbook_file(project_dir)
        if not logbook_path or not logbook_path.exists():
            continue

        entries = []
        for line in logbook_path.read_text().splitlines():
            stripped = line.strip()
            if len(stripped) < 10 or not stripped[:4].isdigit() or stripped[4] != "-":
                continue
            try:
                entry_date = date.fromisoformat(stripped[:10])
            except ValueError:
                continue
            if not (start <= entry_date <= end):
                continue
            tipo = next((t for t in VALID_TYPES if stripped.endswith(f"#{t}")), None)
            content = stripped[10:].strip()
            if tipo and content.endswith(f"#{tipo}"):
                content = content[: -len(f"#{tipo}")].strip()
            entries.append({"date": entry_date, "tipo": tipo, "content": content})

        if entries:
            results.append({"name": project_dir.name, "entries": entries})

    return results


def _format_report(activity: list, title: str) -> str:
    lines = [f"## 📊 {title}", ""]
    if not activity:
        lines.append("_Sin actividad registrada en proyectos._")
    else:
        for proj in activity:
            lines.append(f"- **{proj['name']}** ({len(proj['entries'])})")
            for e in proj["entries"]:
                tag = f" #{e['tipo']}" if e["tipo"] else ""
                date_prefix = f"{e['date'].isoformat()} " if e.get("date") else ""
                lines.append(f"  - {date_prefix}{e['content']}{tag}")
    lines.append("")
    return "\n".join(lines)


def _inject_block(dest: Path, block: str, start_marker: str, end_marker: str) -> None:
    import re as _re
    text = dest.read_text()
    injected = f"{start_marker}\n{block}{end_marker}"
    if start_marker in text:
        text = _re.sub(
            rf"{_re.escape(start_marker)}.*?{_re.escape(end_marker)}",
            injected,
            text,
            flags=_re.DOTALL,
        )
    else:
        if not text.endswith("\n"):
            text += "\n"
        text += "\n" + injected + "\n"
    dest.write_text(text)


_UPCOMING_START         = "<!-- orbit:upcoming:start -->"
_UPCOMING_END           = "<!-- orbit:upcoming:end -->"
_EVENTS_START           = "<!-- orbit:events:start -->"
_EVENTS_END             = "<!-- orbit:events:end -->"
_VALORACION_STATS_START = "<!-- orbit:valoracion-stats:start -->"
_VALORACION_STATS_END   = "<!-- orbit:valoracion-stats:end -->"


def _parse_focus_projects(file_path: Path, heading: str = "## 🎯") -> list:
    """Extract project names from markdown links under a 🎯 heading."""
    if not file_path or not file_path.exists():
        return []
    text = file_path.read_text()
    match = re.search(rf"{re.escape(heading)}[^\n]*\n(.*?)(?=^#|\Z)", text, re.MULTILINE | re.DOTALL)
    if not match:
        return []
    return re.findall(r'\[([^\]]+)\]', match.group(1))


def _find_logbook(name: str):
    """Return logbook Path for the first project whose dir name contains name (case-insensitive)."""
    for project_dir in sorted(PROJECTS_DIR.iterdir()):
        if project_dir.is_dir() and name.lower() in project_dir.name.lower():
            return find_logbook_file(project_dir)
    return None


def _count_focus_entries(names: list, start: date, end: date) -> dict:
    """Return {name: entry_count} for focus projects in [start, end]."""
    counts = {}
    for name in names:
        logbook = _find_logbook(name)
        count = 0
        if logbook and logbook.exists():
            for line in logbook.read_text().splitlines():
                s = line.strip()
                if len(s) < 10 or not s[:4].isdigit():
                    continue
                try:
                    entry_date = date.fromisoformat(s[:10])
                except ValueError:
                    continue
                if start <= entry_date <= end:
                    count += 1
        counts[name] = count
    return counts


def _print_tomato_verdict(results: dict) -> None:
    """Print a human message to the terminal based on focus activity."""
    if not results:
        return
    active = sum(1 for v in results.values() if v)
    total = len(results)
    if active == total:
        print(f"  🍅👏 ¡Enhorabuena! Trabajaste en {'todos tus' if total > 1 else 'tu'} proyecto{'s' if total > 1 else ''} en foco.")
    else:
        print(f"  😔 Lamento que no trabajases en {'todos los' if total > 1 else 'el'} proyecto{'s' if total > 1 else ''} relevante{'s' if total > 1 else ''}.")


def _format_valoracion_day(focus_counts: dict, activity: list, completed: list) -> str:
    """Valoración block for daily note: focus check + activity summary."""
    lines = []

    # Focus check
    if focus_counts:
        lines.append("### 🎯 Foco del día")
        for name, count in focus_counts.items():
            mark = "🍅" if count > 0 else "⬜"
            suffix = f"{count} entrada{'s' if count != 1 else ''}" if count > 0 else "sin actividad"
            lines.append(f"- {mark} {name} — {suffix}")
        lines.append("")

    # Activity summary
    total = sum(len(p["entries"]) for p in activity)
    counts = {}
    for proj in activity:
        for e in proj["entries"]:
            if e["tipo"]:
                counts[e["tipo"]] = counts.get(e["tipo"], 0) + 1
    parts = [f"{TYPE_EMOJI[t]}×{counts[t]}" for t in VALID_TYPES if counts.get(t, 0) > 0]
    lines.append("### 📊 Actividad")
    lines.append(f"- Entradas: {total}{'  ' + '  '.join(parts) if parts else ''}")
    if completed:
        lines.append(f"- Tareas cerradas: {len(completed)}")
    lines.append("")

    return "\n".join(lines)


def _has_section(dest: Path, text: str) -> bool:
    """Return True if text appears anywhere in the file (used to guard one-time injections)."""
    if not dest.exists():
        return False
    return text in dest.read_text()


def _format_valoracion_stats_week(focus_counts: dict, activity: list, completed: list) -> str:
    """Stats-only valoración block for weekly note: focus check + activity table.
    Updated on every shell exit — does NOT include the reflection scaffold.
    """
    lines = []

    # Focus check
    if focus_counts:
        lines.append("### 🎯 Verificación de foco")
        for name, count in focus_counts.items():
            if count > 0:
                lines.append(f"- ✅ {name} — {count} entrada{'s' if count != 1 else ''}")
            else:
                lines.append(f"- ❌ {name} — sin actividad")
        lines.append("")

    # Activity summary by project
    if activity:
        lines.append("### 📊 Actividad de la semana")
        header = "| Proyecto | Entradas | " + " | ".join(TYPE_EMOJI[t] for t in VALID_TYPES) + " |"
        sep    = "|----------|----------| " + " | ".join("----" for _ in VALID_TYPES) + " |"
        lines.append(header)
        lines.append(sep)
        for proj in activity:
            counts = {}
            for e in proj["entries"]:
                if e["tipo"]:
                    counts[e["tipo"]] = counts.get(e["tipo"], 0) + 1
            cols = " | ".join(str(counts.get(t, "")) for t in VALID_TYPES)
            lines.append(f"| {proj['name']} | {len(proj['entries'])} | {cols} |")
        lines.append("")

    if completed:
        lines.append(f"- 🏁 Tareas cerradas: {len(completed)}")
        lines.append("")

    return "\n".join(lines)


def _format_reflection_week() -> str:
    """Empty reflection scaffold injected once at end of week."""
    return "\n".join([
        "### 🍅 Reflexión semanal",
        "",
        "#### ¿Qué salió bien?",
        "",
        "#### ¿Qué no salió bien?",
        "",
        "#### ¿Qué cambio para la próxima semana?",
        "",
    ])




def _format_valoracion_stats_month(focus_counts: dict) -> str:
    """Stats-only valoración block for monthly note: focus check.
    Updated on every shell exit — does NOT include the reflection scaffold.
    """
    if not focus_counts:
        return ""
    lines = ["### 🎯 Verificación de foco"]
    for name, count in focus_counts.items():
        if count > 0:
            lines.append(f"- ✅ {name} — {count} entrada{'s' if count != 1 else ''}")
        else:
            lines.append(f"- ❌ {name} — sin actividad")
    lines.append("")
    return "\n".join(lines)


def _format_reflection_month() -> str:
    """Empty reflection + decisions scaffold injected once at end of month."""
    return "\n".join([
        "### 🍅 Reflexión mensual",
        "",
        "#### Balance del mes",
        "",
        "#### ¿Qué proyectos han avanzado más?",
        "",
        "#### ¿Qué me ha bloqueado?",
        "",
        "### 🧭 Decisiones estratégicas",
        "-",
        "",
        "### 🎯 Objetivos para el mes siguiente",
        "-",
        "",
    ])




def _find_project_dir(name: str):
    """Return (project_dir, proyecto_path) for the first project matching name, or (None, None)."""
    from core.tasks import find_proyecto_file
    for project_dir in sorted(PROJECTS_DIR.iterdir()):
        if project_dir.is_dir() and name.lower() in project_dir.name.lower():
            proyecto_path = find_proyecto_file(project_dir)
            if proyecto_path:
                return project_dir, proyecto_path
    return None, None


def _elevate_focus_priorities(focus: list) -> None:
    """Ensure focus projects have at least media priority (baja → media)."""
    from core.tasks import load_project_meta, update_proyecto_field
    for name in focus:
        project_dir, proyecto_path = _find_project_dir(name)
        if not proyecto_path:
            continue
        meta = load_project_meta(proyecto_path)
        if "baja" in meta["prioridad_raw"]:
            update_proyecto_field(proyecto_path, "prioridad", "media")
            print(f"  ↑ Prioridad media: {project_dir.name}")


def _apply_monthly_focus_priorities(new_focus: list, old_focus: list) -> None:
    """Elevate new focus projects to alta; drop one level for projects leaving focus."""
    from core.tasks import load_project_meta, update_proyecto_field

    def _drop(raw: str) -> str:
        if "alta" in raw:
            return "alta"   # alta stays alta while in focus (handled separately)
        if "media" in raw:
            return "baja"
        return "baja"

    def _matches(name_a: str, name_b: str) -> bool:
        a, b = name_a.lower(), name_b.lower()
        return a in b or b in a

    # Elevate projects entering or staying in focus
    for name in new_focus:
        project_dir, proyecto_path = _find_project_dir(name)
        if not proyecto_path:
            continue
        meta = load_project_meta(proyecto_path)
        if "alta" not in meta["prioridad_raw"]:
            update_proyecto_field(proyecto_path, "prioridad", "alta")
            print(f"  ↑ Prioridad alta: {project_dir.name}")

    # Drop projects leaving focus
    exiting = [n for n in old_focus if not any(_matches(n, f) for f in new_focus)]
    for name in exiting:
        project_dir, proyecto_path = _find_project_dir(name)
        if not proyecto_path:
            continue
        meta = load_project_meta(proyecto_path)
        if "alta" in meta["prioridad_raw"]:
            update_proyecto_field(proyecto_path, "prioridad", "media")
            print(f"  ↓ Prioridad media: {project_dir.name}")
        elif "media" in meta["prioridad_raw"]:
            update_proyecto_field(proyecto_path, "prioridad", "baja")
            print(f"  ↓ Prioridad baja: {project_dir.name}")


def _resolve_focus_link(name: str):
    """Find project dir by partial name and return (dir_name, relative_path)."""
    for project_dir in sorted(PROJECTS_DIR.iterdir()):
        if project_dir.is_dir() and name.lower() in project_dir.name.lower():
            proyecto_path = find_proyecto_file(project_dir)
            if proyecto_path:
                return project_dir.name, f"../../🚀proyectos/{project_dir.name}/{proyecto_path.name}"
    return None


def _inject_focus_projects(dest: Path, names: list, heading: str) -> None:
    """Replace focus section links with real project links (dynamic count)."""
    resolved = []
    for name in names:
        result = _resolve_focus_link(name)
        if result:
            resolved.append(result)
        else:
            print(f"  ⚠️ Proyecto '{name}' no encontrado")
    if not resolved:
        return

    use_bullets = len(resolved) == 1
    lines = dest.read_text().splitlines()
    out = []
    in_section = False
    wrote_items = False
    for line in lines:
        if line.strip().startswith(heading):
            in_section = True
            wrote_items = False
            out.append(line)
            continue
        if in_section and re.match(r'^#{1,6}\s', line):
            in_section = False
            if out and out[-1] != "":
                out.append("")
            out.append(line)
            continue
        if in_section:
            is_link = line.startswith("- [") or bool(re.match(r'^\d+\.\s+\[', line))
            if is_link and not wrote_items:
                for i, (dir_name, path) in enumerate(resolved, 1):
                    if use_bullets:
                        out.append(f"- [{dir_name}]({path})")
                    else:
                        out.append(f"{i}. [{dir_name}]({path})")
                wrote_items = True
                continue  # skip placeholder line
            elif is_link and wrote_items:
                continue  # skip remaining placeholders
            else:
                out.append(line)
        else:
            out.append(line)

    if in_section and not wrote_items:
        for i, (dir_name, path) in enumerate(resolved, 1):
            if use_bullets:
                out.append(f"- [{dir_name}]({path})")
            else:
                out.append(f"{i}. [{dir_name}]({path})")

    dest.write_text("\n".join(out) + "\n")
    for dir_name, _ in resolved:
        print(f"  🎯 Foco: {dir_name}")


def _project_link(name: str, path: Path) -> str:
    """Return a markdown link to the project's tasks section."""
    return f"[{name}](file://{path.resolve()}#tareas)"


def _collect_upcoming_tasks(horizon_days: int) -> list:
    """Return tasks due within horizon_days from today, including overdue, sorted by date."""
    today = date.today()
    horizon = today + timedelta(days=horizon_days)
    results = []
    if not PROJECTS_DIR.exists():
        return results
    for project_dir in sorted(PROJECTS_DIR.iterdir()):
        if not project_dir.is_dir():
            continue
        proyecto_path = find_proyecto_file(project_dir)
        if not proyecto_path or not proyecto_path.exists():
            continue
        meta = load_project_meta(proyecto_path)
        if "completado" in meta.get("estado_raw", ""):
            continue
        for task in meta["tasks"]:
            if not task["due"]:
                continue
            try:
                due_date = date.fromisoformat(task["due"])
            except ValueError:
                continue
            if due_date <= horizon:
                results.append({
                    "due_date": due_date,
                    "project": project_dir.name,
                    "proyecto_path": proyecto_path,
                    "tipo": meta["tipo"],
                    "description": task["description"],
                    "overdue": due_date < today,
                    "ring": task.get("ring", False),
                    "time": task.get("time"),
                })
    results.sort(key=lambda x: x["due_date"])
    return results


def _format_upcoming_tasks(tasks: list) -> str:
    """Format upcoming tasks as a markdown list."""
    if not tasks:
        return "_Sin tareas con vencimiento próximo._\n"
    lines = []
    for t in tasks:
        if t["overdue"]:
            marker = "⚠️"
        elif t.get("ring"):
            marker = "⏰"
        else:
            marker = "[ ]"
        path = t.get("proyecto_path")
        project_label = (f"[{t['project']}](file://{path.resolve()}#tareas)" if path
                         else t["project"])
        time_str = f" {t['time']}" if t.get("time") else ""
        lines.append(f"- {marker} {t['due_date'].isoformat()}{time_str}  {project_label} — {t['description']}")
    return "\n".join(lines) + "\n"


def _collect_completed_tasks(start: date, end: date) -> list:
    """Return tasks completed (marked [x] with date) within [start, end]."""
    results = []
    if not PROJECTS_DIR.exists():
        return results
    for project_dir in sorted(PROJECTS_DIR.iterdir()):
        if not project_dir.is_dir():
            continue
        proyecto_path = find_proyecto_file(project_dir)
        if not proyecto_path or not proyecto_path.exists():
            continue
        meta = load_project_meta(proyecto_path)
        for task in meta["tasks"]:
            if not task.get("done") or not task.get("completed"):
                continue
            try:
                comp_date = date.fromisoformat(task["completed"])
            except ValueError:
                continue
            if start <= comp_date <= end:
                results.append({
                    "completed_date": comp_date,
                    "project": project_dir.name,
                    "proyecto_path": proyecto_path,
                    "description": task["description"],
                })
    results.sort(key=lambda x: x["completed_date"])
    return results


def _collect_tasks_due(start: date, end: date) -> list:
    """Return list of {project, task} for tasks with due date in [start, end]."""
    results = []
    if not PROJECTS_DIR.exists():
        return results
    for project_dir in sorted(PROJECTS_DIR.iterdir()):
        if not project_dir.is_dir():
            continue
        proyecto_path = find_proyecto_file(project_dir)
        if not proyecto_path or not proyecto_path.exists():
            continue
        meta = load_project_meta(proyecto_path)
        for task in meta["tasks"]:
            if task["due"]:
                try:
                    due_date = date.fromisoformat(task["due"])
                except ValueError:
                    continue
                if start <= due_date <= end:
                    results.append({"project": project_dir.name, "proyecto_path": proyecto_path, "task": task})
    return results


def _type_summary(activity: list) -> str:
    """Return a one-line summary of entry counts by type."""
    counts = {t: 0 for t in VALID_TYPES}
    for proj in activity:
        for e in proj["entries"]:
            if e["tipo"]:
                counts[e["tipo"]] += 1
    parts = [f"{TYPE_EMOJI[t]} {counts[t]}" for t in VALID_TYPES if counts[t] > 0]
    return "  ".join(parts) if parts else "Sin entradas"


def _activate_projects_with_activity(activity: list) -> None:
    """Set status to 'en marcha' for any project with logbook activity, unless already there or completado."""
    from core.tasks import load_project_meta, update_proyecto_field, find_proyecto_file
    for proj in activity:
        if not proj.get("entries"):
            continue
        project_dir = next(
            (d for d in PROJECTS_DIR.iterdir()
             if d.is_dir() and d.name == proj["name"]), None
        )
        if not project_dir:
            continue
        proyecto_path = find_proyecto_file(project_dir)
        if not proyecto_path:
            continue
        meta = load_project_meta(proyecto_path)
        if "en marcha" not in meta["estado_raw"] and "completado" not in meta["estado_raw"]:
            update_proyecto_field(proyecto_path, "estado", "en marcha")
            print(f"  → estado: en marcha ({project_dir.name})")


def run_dayreport(date_str: Optional[str], inject: bool,
                  output: Optional[str] = None, open_after: bool = False,
                  editor: str = "typora") -> int:
    target = date.fromisoformat(date_str) if date_str else date.today()
    dest = DIARIO_DIR / f"{target.isoformat()}.md"

    activity = _collect_activity(target, target)
    _activate_projects_with_activity(activity)
    tasks_due = _collect_tasks_due(target, target)
    completed = _collect_completed_tasks(target, target)
    focus = _parse_focus_projects(dest, "### 🎯 Proyecto en foco")
    focus_counts = _count_focus_entries(focus, target, target)
    _print_tomato_verdict({name: count > 0 for name, count in focus_counts.items()})

    block = _format_report(activity, f"Actividad — {target.isoformat()}")

    if tasks_due:
        task_lines = ["## ✅ Tareas vencidas hoy", ""]
        for item in tasks_due:
            ring_marker = " ⏰" if item['task'].get('ring') else ""
            task_lines.append(f"- {_project_link(item['project'], item['proyecto_path'])}{ring_marker} — {item['task']['description']}")
        task_lines.append("")
        block += "\n" + "\n".join(task_lines)

    if completed:
        done_lines = ["## 🏁 Completadas hoy", ""]
        for item in completed:
            done_lines.append(f"- {_project_link(item['project'], item['proyecto_path'])} — {item['description']}")
        done_lines.append("")
        block += "\n" + "\n".join(done_lines)

    val_block = _format_valoracion_day(focus_counts, activity, completed)

    if output:
        # Full report to file: stats + detailed activity
        Path(output).write_text((val_block + "\n" if val_block else "") + block + "\n")
        print(f"✓ Guardado en {output}")
    elif not inject:
        # Terminal: readable activity report only (no markdown table)
        print(block)

    if inject or open_after:
        if not dest.exists():
            print(f"Aviso: nota del día no existe ({dest.name}). Crea primero con 'orbit day'.")
            return 1
        if inject:
            # Only inject compact stats into the note; detailed report stays in terminal/output
            _inject_block(dest, val_block, _VALORACION_STATS_START, _VALORACION_STATS_END)
            print(f"✓ Inyectado en {dest}")
        if open_after:
            open_file(dest, editor)

    return 0


def run_weekreport(date_str: Optional[str], inject: bool,
                   output: Optional[str] = None, open_after: bool = False,
                   editor: str = "typora") -> int:
    d = date.fromisoformat(date_str) if date_str else date.today()
    wkey = _week_key(d)
    mon, sun = _week_bounds(d)
    end = min(sun, date.today())
    dest = SEMANAL_DIR / f"{wkey}.md"

    activity = _collect_activity(mon, end)
    tasks_due = _collect_tasks_due(mon, sun)
    completed = _collect_completed_tasks(mon, end)
    focus = _parse_focus_projects(dest, "### 🎯 Proyectos en foco")
    focus_counts = _count_focus_entries(focus, mon, end)
    _print_tomato_verdict({name: count > 0 for name, count in focus_counts.items()})

    summary = _type_summary(activity)
    block = _format_report(activity, f"Actividad semana {wkey}  ({mon.isoformat()} — {sun.isoformat()})")
    block = block.replace("\n\n", f"\n\n_{summary}_\n\n", 1)

    if tasks_due:
        task_lines = ["## ✅ Tareas con vencimiento esta semana", ""]
        for item in tasks_due:
            ring_marker = " ⏰" if item['task'].get('ring') else ""
            time_str = f" {item['task']['time']}" if item['task'].get('time') else ""
            task_lines.append(f"- {_project_link(item['project'], item['proyecto_path'])}{ring_marker} — {item['task']['description']} ({item['task']['due']}{time_str})")
        task_lines.append("")
        block += "\n" + "\n".join(task_lines)

    if completed:
        done_lines = ["## 🏁 Completadas esta semana", ""]
        for item in completed:
            done_lines.append(f"- {item['completed_date'].isoformat()}  {_project_link(item['project'], item['proyecto_path'])} — {item['description']}")
        done_lines.append("")
        block += "\n" + "\n".join(done_lines)

    stats_block = _format_valoracion_stats_week(focus_counts, activity, completed)

    if output:
        # Full report to file: stats table + activity detail
        full = (stats_block + "\n" if stats_block else "") + block
        Path(output).write_text(full + "\n")
        print(f"✓ Guardado en {output}")
    elif not inject:
        # Terminal: readable activity report only (no markdown table)
        print(block)

    if inject or open_after:
        if not dest.exists():
            print(f"Error: no existe {dest}. Crea el fichero semanal primero con 'orbit week'.")
            return 1
        if inject:
            _inject_block(dest, stats_block, _VALORACION_STATS_START, _VALORACION_STATS_END)
            file_text = dest.read_text()                          # single read after stats update
            if "### 🍅 Reflexión semanal" not in file_text:
                file_text = re.sub(
                    re.escape(_VALORACION_STATS_END),
                    _VALORACION_STATS_END + "\n" + _format_reflection_week(),
                    file_text, count=1,
                )
                dest.write_text(file_text)
                print("  → Reflexión semanal añadida")
            _inject_block(dest, block, _WR_START, _WR_END)
            print(f"✓ Inyectado en {dest}")
            log_to_mission(f"Reporte semanal {wkey}", "apunte")
        if open_after:
            open_file(dest, editor)

    return 0

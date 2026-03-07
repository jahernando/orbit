import re
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

from core.log import VALID_TYPES, find_logbook_file, find_proyecto_file
from core.tasks import TYPE_MAP, load_project_meta
from core.activity import has_activity_in

PROJECTS_DIR   = Path(__file__).parent.parent / "🚀proyectos"
MISION_LOG_DIR = Path(__file__).parent.parent / "☀️mision-log"
TEMPLATES_DIR  = Path(__file__).parent.parent / "📐templates"

DIARIO_DIR  = MISION_LOG_DIR / "diario"
SEMANAL_DIR = MISION_LOG_DIR / "semanal"
MENSUAL_DIR = MISION_LOG_DIR / "mensual"


def _week_key(d: date) -> str:
    return d.strftime("%G-W%V")


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


# ── day ──────────────────────────────────────────────────────────────────────

def run_day(date_str: Optional[str], force: bool, focus: list = None) -> int:
    target = date.fromisoformat(date_str) if date_str else date.today()
    dest   = DIARIO_DIR / f"{target.isoformat()}.md"

    tpl = TEMPLATES_DIR / "diario.md"
    if not tpl.exists():
        print(f"Error: plantilla no encontrada en {tpl}")
        return 1
    content = tpl.read_text().replace("YYYY-MM-DD", target.isoformat())

    rc = _write(dest, content, None, force)
    if rc == 0:
        if focus:
            _inject_focus_projects(dest, focus[:1], "## 🎯 Proyecto en foco")
        upcoming = _collect_upcoming_tasks(7)
        _inject_block(dest, _format_upcoming_tasks(upcoming), _UPCOMING_START, _UPCOMING_END)
        _sync_calendar_to_day(dest, target)
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

def run_logday(message: str, tipo: str, date_str: Optional[str]) -> int:
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
    return 0


# ── week ─────────────────────────────────────────────────────────────────────

def run_week(date_str: Optional[str], force: bool, focus: list = None) -> int:
    d      = date.fromisoformat(date_str) if date_str else date.today()
    wkey   = _week_key(d)
    mon, sun = _week_bounds(d)
    dest   = SEMANAL_DIR / f"{wkey}.md"

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

    rc = _write(dest, content, None, force)
    if rc == 0:
        if focus:
            _inject_focus_projects(dest, focus[:2], "## 🎯 Proyectos en foco")
        upcoming = _collect_upcoming_tasks(15)
        _inject_block(dest, _format_upcoming_tasks(upcoming), _UPCOMING_START, _UPCOMING_END)
    return rc


# ── month ─────────────────────────────────────────────────────────────────────

def run_month(date_str: Optional[str], force: bool, focus: list = None) -> int:
    if date_str:
        y, m = int(date_str[:4]), int(date_str[5:7])
    else:
        today = date.today()
        y, m  = today.year, today.month
    month_str = f"{y}-{m:02d}"
    dest = MENSUAL_DIR / f"{month_str}.md"

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

    rc = _write(dest, content, None, force)
    if rc == 0:
        if focus:
            _inject_focus_projects(dest, focus[:3], "## 🎯 Proyectos en foco")
        upcoming = _collect_upcoming_tasks(30)
        _inject_block(dest, _format_upcoming_tasks(upcoming), _UPCOMING_START, _UPCOMING_END)
    return rc


# ── dayreport / weekreport ────────────────────────────────────────────────────

_DR_START = "<!-- orbit:dayreport:start -->"
_DR_END   = "<!-- orbit:dayreport:end -->"
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


_TOMATO_START    = "<!-- orbit:tomato:start -->"
_TOMATO_END      = "<!-- orbit:tomato:end -->"
_UPCOMING_START  = "<!-- orbit:upcoming:start -->"
_UPCOMING_END    = "<!-- orbit:upcoming:end -->"
_EVENTS_START    = "<!-- orbit:events:start -->"
_EVENTS_END      = "<!-- orbit:events:end -->"


def _parse_focus_projects(file_path: Path, heading: str = "## 🎯") -> list:
    """Extract project names from markdown links under a 🎯 heading."""
    if not file_path or not file_path.exists():
        return []
    text = file_path.read_text()
    match = re.search(rf"{re.escape(heading)}.*?\n(.*?)(?=^##|\Z)", text, re.MULTILINE | re.DOTALL)
    if not match:
        return []
    return re.findall(r'\[([^\]]+)\]', match.group(1))


def _check_focus_activity(project_names: list, start: date, end: date) -> dict:
    """Return {name: has_activity} for each focus project."""
    results = {}
    for name in project_names:
        matched = None
        for project_dir in sorted(PROJECTS_DIR.iterdir()):
            if project_dir.is_dir() and name.lower() in project_dir.name.lower():
                matched = project_dir
                break
        logbook = find_logbook_file(matched) if matched else None
        results[name] = has_activity_in(logbook, start, end)
    return results


def _format_tomato_block(results: dict, label: str) -> str:
    """Format the 🍅 evaluation block."""
    if not results:
        return ""
    active = sum(1 for v in results.values() if v)
    total = len(results)
    lines = []
    for name, has_act in results.items():
        lines.append(f"- {'🍅' if has_act else '⬜'} {name}")
    if active == total:
        verdict = "🍅 " * total + f"Fructífero"
    elif active > 0:
        verdict = f"🍅 ×{active}/{total} Parcialmente fructífero"
    else:
        verdict = "⬜ Sin actividad en proyectos en foco"
    lines.append(f"\n**{verdict.strip()}**")
    return "\n".join(lines) + "\n"


def _resolve_focus_link(name: str):
    """Find project dir by partial name and return (dir_name, relative_path)."""
    for project_dir in sorted(PROJECTS_DIR.iterdir()):
        if project_dir.is_dir() and name.lower() in project_dir.name.lower():
            proyecto_path = find_proyecto_file(project_dir)
            if proyecto_path:
                return project_dir.name, f"../../🚀proyectos/{project_dir.name}/{proyecto_path.name}"
    return None


def _inject_focus_projects(dest: Path, names: list, heading: str) -> None:
    """Replace placeholder focus links in a section with real project links."""
    resolved = []
    for name in names:
        result = _resolve_focus_link(name)
        if result:
            resolved.append(result)
        else:
            print(f"  ⚠️ Proyecto '{name}' no encontrado")
    if not resolved:
        return

    lines = dest.read_text().splitlines()
    in_section = False
    link_idx = 0
    new_lines = []
    for line in lines:
        if line.strip().startswith(heading):
            in_section = True
            new_lines.append(line)
            continue
        if in_section and line.startswith("## "):
            in_section = False
        if in_section and re.search(r'\[.*?\]\(', line) and link_idx < len(resolved):
            dir_name, path = resolved[link_idx]
            marker_match = re.match(r'^(\s*(?:-|\d+\.)\s*)', line)
            marker = marker_match.group(1) if marker_match else "- "
            new_lines.append(f"{marker}[{dir_name}]({path})")
            link_idx += 1
            continue
        new_lines.append(line)
    dest.write_text("\n".join(new_lines) + "\n")
    for dir_name, _ in resolved:
        print(f"  🎯 Foco: {dir_name}")


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
                    "tipo": meta["tipo"],
                    "description": task["description"],
                    "overdue": due_date < today,
                })
    results.sort(key=lambda x: x["due_date"])
    return results


def _format_upcoming_tasks(tasks: list) -> str:
    """Format upcoming tasks as a markdown list."""
    if not tasks:
        return "_Sin tareas con vencimiento próximo._\n"
    lines = []
    for t in tasks:
        marker = "⚠️" if t["overdue"] else "[ ]"
        lines.append(f"- {marker} {t['due_date'].isoformat()}  {t['project']} — {t['description']}")
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
                    results.append({"project": project_dir.name, "task": task})
    return results


def _type_summary(activity: list) -> str:
    """Return a one-line summary of entry counts by type."""
    from core.activity import TYPE_EMOJI
    counts = {t: 0 for t in VALID_TYPES}
    for proj in activity:
        for e in proj["entries"]:
            if e["tipo"]:
                counts[e["tipo"]] += 1
    parts = [f"{TYPE_EMOJI[t]} {counts[t]}" for t in VALID_TYPES if counts[t] > 0]
    return "  ".join(parts) if parts else "Sin entradas"


def run_dayreport(date_str: Optional[str], inject: bool) -> int:
    target = date.fromisoformat(date_str) if date_str else date.today()
    dest = DIARIO_DIR / f"{target.isoformat()}.md"

    activity = _collect_activity(target, target)
    tasks_due = _collect_tasks_due(target, target)
    completed = _collect_completed_tasks(target, target)
    focus = _parse_focus_projects(dest, "## 🎯 Proyecto en foco")
    tomato = _check_focus_activity(focus, target, target)
    tomato_block = _format_tomato_block(tomato, target.isoformat())

    block = _format_report(activity, f"Actividad — {target.isoformat()}")

    if tasks_due:
        task_lines = ["## ✅ Tareas vencidas hoy", ""]
        for item in tasks_due:
            task_lines.append(f"- **{item['project']}** — {item['task']['description']}")
        task_lines.append("")
        block += "\n" + "\n".join(task_lines)

    if completed:
        done_lines = ["## 🏁 Completadas hoy", ""]
        for item in completed:
            done_lines.append(f"- **{item['project']}** — {item['description']}")
        done_lines.append("")
        block += "\n" + "\n".join(done_lines)

    if tomato_block:
        print(tomato_block)
    print(block)

    if not inject:
        return 0

    if not dest.exists():
        tpl = TEMPLATES_DIR / "diario.md"
        if not tpl.exists():
            print(f"Error: plantilla no encontrada en {tpl}")
            return 1
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(tpl.read_text().replace("YYYY-MM-DD", target.isoformat()))
        print(f"✓ Creado {dest}")

    _inject_block(dest, block, _DR_START, _DR_END)
    if tomato_block:
        _inject_block(dest, tomato_block, _TOMATO_START, _TOMATO_END)
    print(f"✓ Inyectado en {dest}")
    return 0


def run_weekreport(date_str: Optional[str], inject: bool) -> int:
    d = date.fromisoformat(date_str) if date_str else date.today()
    wkey = _week_key(d)
    mon, sun = _week_bounds(d)
    end = min(sun, date.today())
    dest = SEMANAL_DIR / f"{wkey}.md"

    activity = _collect_activity(mon, end)
    tasks_due = _collect_tasks_due(mon, sun)
    completed = _collect_completed_tasks(mon, end)
    focus = _parse_focus_projects(dest, "## 🎯 Proyectos en foco")
    tomato = _check_focus_activity(focus, mon, end)
    tomato_block = _format_tomato_block(tomato, f"semana {wkey}")

    summary = _type_summary(activity)
    block = _format_report(activity, f"Actividad semana {wkey}  ({mon.isoformat()} — {sun.isoformat()})")
    block = block.replace("\n\n", f"\n\n_{summary}_\n\n", 1)

    if tasks_due:
        task_lines = ["## ✅ Tareas con vencimiento esta semana", ""]
        for item in tasks_due:
            task_lines.append(f"- **{item['project']}** — {item['task']['description']} ({item['task']['due']})")
        task_lines.append("")
        block += "\n" + "\n".join(task_lines)

    if completed:
        done_lines = ["## 🏁 Completadas esta semana", ""]
        for item in completed:
            done_lines.append(f"- {item['completed_date'].isoformat()}  **{item['project']}** — {item['description']}")
        done_lines.append("")
        block += "\n" + "\n".join(done_lines)

    if tomato_block:
        print(tomato_block)
    print(block)

    if not inject:
        return 0

    if not dest.exists():
        print(f"Error: no existe {dest}. Crea el fichero semanal primero con 'orbit week'.")
        return 1

    _inject_block(dest, block, _WR_START, _WR_END)
    if tomato_block:
        _inject_block(dest, tomato_block, _TOMATO_START, _TOMATO_END)
    print(f"✓ Inyectado en {dest}")
    return 0

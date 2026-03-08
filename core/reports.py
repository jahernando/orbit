"""reports.py — dayreport / weekreport generation for ☀️mision-log notes.

orbit dayreport  — inject today's activity summary into the daily note
orbit weekreport — inject this week's activity summary into the weekly note

All helpers are private to this module.  The three constants and helpers also
needed by misionlog.py (_inject_block, _count_focus_entries,
_format_valoracion_stats_month, _VALORACION_STATS_START/END) are exported and
imported back into misionlog.py so they remain as a single implementation.
"""

import re
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

from core.log import VALID_TYPES, find_logbook_file, find_proyecto_file, log_to_mission
from core.open import open_file
from core.tasks import load_project_meta
from core.activity import TYPE_EMOJI
from core.focus import _week_key

PROJECTS_DIR   = Path(__file__).parent.parent / "🚀proyectos"
MISION_LOG_DIR = Path(__file__).parent.parent / "☀️mision-log"
DIARIO_DIR     = MISION_LOG_DIR / "diario"
SEMANAL_DIR    = MISION_LOG_DIR / "semanal"


def _week_bounds(d: date) -> tuple:
    monday = d - timedelta(days=d.weekday())
    return monday, monday + timedelta(days=6)


# ── markers ───────────────────────────────────────────────────────────────────

_WR_START = "<!-- orbit:weekreport:start -->"
_WR_END   = "<!-- orbit:weekreport:end -->"

_UPCOMING_START         = "<!-- orbit:upcoming:start -->"
_UPCOMING_END           = "<!-- orbit:upcoming:end -->"
_EVENTS_START           = "<!-- orbit:events:start -->"
_EVENTS_END             = "<!-- orbit:events:end -->"
_VALORACION_STATS_START = "<!-- orbit:valoracion-stats:start -->"
_VALORACION_STATS_END   = "<!-- orbit:valoracion-stats:end -->"


# ── activity collection ───────────────────────────────────────────────────────

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


# ── focus helpers ─────────────────────────────────────────────────────────────

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


# ── valoración formatters ─────────────────────────────────────────────────────

def _format_valoracion_day(focus_counts: dict, activity: list, completed: list) -> str:
    """Valoración block for daily note: focus check + activity summary."""
    lines = []

    if focus_counts:
        lines.append("### 🎯 Foco del día")
        for name, count in focus_counts.items():
            mark = "🍅" if count > 0 else "⬜"
            suffix = f"{count} entrada{'s' if count != 1 else ''}" if count > 0 else "sin actividad"
            lines.append(f"- {mark} {name} — {suffix}")
        lines.append("")

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
    """Stats-only valoración block for weekly note: focus check + activity table."""
    lines = []

    if focus_counts:
        lines.append("### 🎯 Verificación de foco")
        for name, count in focus_counts.items():
            if count > 0:
                lines.append(f"- ✅ {name} — {count} entrada{'s' if count != 1 else ''}")
            else:
                lines.append(f"- ❌ {name} — sin actividad")
        lines.append("")

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
    """Stats-only valoración block for monthly note: focus check."""
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


# ── project helpers ───────────────────────────────────────────────────────────

def _find_project_dir(name: str):
    """Return (project_dir, proyecto_path) for the first project matching name, or (None, None)."""
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
            return "alta"
        if "media" in raw:
            return "baja"
        return "baja"

    def _matches(name_a: str, name_b: str) -> bool:
        a, b = name_a.lower(), name_b.lower()
        return a in b or b in a

    for name in new_focus:
        project_dir, proyecto_path = _find_project_dir(name)
        if not proyecto_path:
            continue
        meta = load_project_meta(proyecto_path)
        if "alta" not in meta["prioridad_raw"]:
            update_proyecto_field(proyecto_path, "prioridad", "alta")
            print(f"  ↑ Prioridad alta: {project_dir.name}")

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
                continue
            elif is_link and wrote_items:
                continue
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


# ── task collection ───────────────────────────────────────────────────────────

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


# ── public API ────────────────────────────────────────────────────────────────

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
        Path(output).write_text((val_block + "\n" if val_block else "") + block + "\n")
        print(f"✓ Guardado en {output}")
    elif not inject:
        print(block)

    if inject or open_after:
        if not dest.exists():
            print(f"Aviso: nota del día no existe ({dest.name}). Crea primero con 'orbit day'.")
            return 1
        if inject:
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
        full = (stats_block + "\n" if stats_block else "") + block
        Path(output).write_text(full + "\n")
        print(f"✓ Guardado en {output}")
    elif not inject:
        print(block)

    if inject or open_after:
        if not dest.exists():
            print(f"Error: no existe {dest}. Crea el fichero semanal primero con 'orbit week'.")
            return 1
        if inject:
            _inject_block(dest, stats_block, _VALORACION_STATS_START, _VALORACION_STATS_END)
            file_text = dest.read_text()
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

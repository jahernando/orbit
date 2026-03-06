from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

from core.log import VALID_TYPES, find_logbook_file, find_proyecto_file
from core.tasks import TYPE_MAP, load_project_meta

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

def run_day(date_str: Optional[str], copy: Optional[str], force: bool) -> int:
    target = date.fromisoformat(date_str) if date_str else date.today()
    dest   = DIARIO_DIR / f"{target.isoformat()}.md"

    if copy:
        src = DIARIO_DIR / f"{copy}.md"
        if not src.exists():
            print(f"Error: no existe {src}")
            return 1
        lines = src.read_text().splitlines(keepends=True)
        if lines and lines[0].startswith("# Diario"):
            lines[0] = f"# Diario — {target.isoformat()}\n"
        content = "".join(lines)
    else:
        tpl = TEMPLATES_DIR / "diario.md"
        if not tpl.exists():
            print(f"Error: plantilla no encontrada en {tpl}")
            return 1
        content = tpl.read_text().replace("YYYY-MM-DD", target.isoformat())

    return _write(dest, content, copy, force)


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

    text = dest.read_text()
    if not text.endswith("\n"):
        text += "\n"
    dest.write_text(text + entry)

    print(f"✓ [{target.isoformat()}] {entry.strip()}")
    return 0


# ── week ─────────────────────────────────────────────────────────────────────

def run_week(date_str: Optional[str], copy: Optional[str], force: bool) -> int:
    d      = date.fromisoformat(date_str) if date_str else date.today()
    wkey   = _week_key(d)
    mon, sun = _week_bounds(d)
    dest   = SEMANAL_DIR / f"{wkey}.md"

    if copy:
        src = SEMANAL_DIR / f"{copy}.md"
        if not src.exists():
            print(f"Error: no existe {src}")
            return 1
        lines = src.read_text().splitlines(keepends=True)
        if lines and lines[0].startswith("# Semana"):
            lines[0] = f"# Semana {wkey} ({mon.isoformat()} — {sun.isoformat()})\n"
        content = "".join(lines)
    else:
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

    return _write(dest, content, copy, force)


# ── month ─────────────────────────────────────────────────────────────────────

def run_month(date_str: Optional[str], copy: Optional[str], force: bool) -> int:
    if date_str:
        y, m = int(date_str[:4]), int(date_str[5:7])
    else:
        today = date.today()
        y, m  = today.year, today.month
    month_str = f"{y}-{m:02d}"
    dest = MENSUAL_DIR / f"{month_str}.md"

    if copy:
        src = MENSUAL_DIR / f"{copy}.md"
        if not src.exists():
            print(f"Error: no existe {src}")
            return 1
        lines = src.read_text().splitlines(keepends=True)
        if lines and lines[0].startswith("# Mes"):
            lines[0] = f"# Mes {month_str}\n"
        content = "".join(lines)
    else:
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

    return _write(dest, content, copy, force)


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
    activity = _collect_activity(target, target)
    tasks_due = _collect_tasks_due(target, target)

    block = _format_report(activity, f"Actividad — {target.isoformat()}")

    if tasks_due:
        task_lines = [f"## ✅ Tareas vencidas hoy", ""]
        for item in tasks_due:
            task_lines.append(f"- **{item['project']}** — {item['task']['description']}")
        task_lines.append("")
        block += "\n" + "\n".join(task_lines)

    print(block)

    if not inject:
        return 0

    dest = DIARIO_DIR / f"{target.isoformat()}.md"
    if not dest.exists():
        tpl = TEMPLATES_DIR / "diario.md"
        if not tpl.exists():
            print(f"Error: plantilla no encontrada en {tpl}")
            return 1
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(tpl.read_text().replace("YYYY-MM-DD", target.isoformat()))
        print(f"✓ Creado {dest}")

    _inject_block(dest, block, _DR_START, _DR_END)
    print(f"✓ Inyectado en {dest}")
    return 0


def run_weekreport(date_str: Optional[str], inject: bool) -> int:
    d = date.fromisoformat(date_str) if date_str else date.today()
    wkey = _week_key(d)
    mon, sun = _week_bounds(d)
    # cap end at today
    end = min(sun, date.today())
    activity = _collect_activity(mon, end)
    tasks_due = _collect_tasks_due(mon, sun)

    summary = _type_summary(activity)
    block = _format_report(activity, f"Actividad semana {wkey}  ({mon.isoformat()} — {sun.isoformat()})")

    # Prepend type summary after the title
    block = block.replace("\n\n", f"\n\n_{summary}_\n\n", 1)

    if tasks_due:
        task_lines = [f"## ✅ Tareas con vencimiento esta semana", ""]
        for item in tasks_due:
            task_lines.append(f"- **{item['project']}** — {item['task']['description']} ({item['task']['due']})")
        task_lines.append("")
        block += "\n" + "\n".join(task_lines)

    print(block)

    if not inject:
        return 0

    dest = SEMANAL_DIR / f"{wkey}.md"
    if not dest.exists():
        print(f"Error: no existe {dest}. Crea el fichero semanal primero con 'orbit week'.")
        return 1

    _inject_block(dest, block, _WR_START, _WR_END)
    print(f"✓ Inyectado en {dest}")
    return 0

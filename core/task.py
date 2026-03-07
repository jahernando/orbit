"""orbit tarea — open, schedule or close tasks in projects or daily note."""

from datetime import date
from pathlib import Path
from typing import Optional

from core.log import PROJECTS_DIR, find_project, find_proyecto_file
from core.tasks import _extract_date_from_parens

MISION_LOG_DIR = Path(__file__).parent.parent / "☀️mision-log"
DIARIO_DIR = MISION_LOG_DIR / "diario"
TEMPLATES_DIR = Path(__file__).parent.parent / "📐templates"


def _find_task_line(lines: list, task_desc: str, done: bool = False) -> int:
    """Return index of first pending (or done) task matching task_desc, or -1."""
    marker = "- [x]" if done else "- [ ]"
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped.startswith(marker):
            continue
        content = stripped[5:].strip()
        desc_only, _ = _extract_date_from_parens(content)
        if task_desc.lower() in desc_only.lower():
            return i
    return -1


def _write_lines(path: Path, lines: list) -> None:
    path.write_text("\n".join(lines) + "\n")


# ── open ──────────────────────────────────────────────────────────────────────

def run_task_open(project: Optional[str], task_desc: str, fecha: Optional[str]) -> int:
    date_str = f" ({fecha})" if fecha else ""
    entry = f"- [ ] {task_desc}{date_str}"

    if not project:
        return _open_in_daily(entry, task_desc, fecha)

    project_dir = find_project(project)
    if not project_dir:
        return 1
    proyecto_path = find_proyecto_file(project_dir)
    if not proyecto_path or not proyecto_path.exists():
        print(f"Error: no se encontró el archivo de proyecto en {project_dir.name}")
        return 1

    lines = proyecto_path.read_text().splitlines()
    # Find ## ✅ Tareas section and insert before the first non-task line after it
    in_tasks = False
    insert_at = None
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("## ") and "✅" in stripped and "tareas" in stripped.lower():
            in_tasks = True
            insert_at = i + 1
            continue
        if in_tasks:
            if stripped.startswith("- ["):
                insert_at = i + 1  # keep moving past existing tasks
            elif stripped.startswith("## ") or (stripped and not stripped.startswith("-")):
                break  # end of tasks section

    if insert_at is not None:
        lines.insert(insert_at, entry)
        _write_lines(proyecto_path, lines)
        print(f"✓ [{project_dir.name}] {entry}")
        return 0

    # Fallback: append at end
    lines.append(entry)
    _write_lines(proyecto_path, lines)
    print(f"✓ [{project_dir.name}] {entry}")
    return 0


def _open_in_daily(entry: str, task_desc: str, fecha: Optional[str]) -> int:
    today = date.today()
    dest = DIARIO_DIR / f"{today.isoformat()}.md"

    if not dest.exists():
        tpl = TEMPLATES_DIR / "diario.md"
        if not tpl.exists():
            print(f"Error: plantilla no encontrada en {tpl}")
            return 1
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(tpl.read_text().replace("YYYY-MM-DD", today.isoformat()))
        print(f"✓ Creado {dest}")

    lines = dest.read_text().splitlines()
    for i, line in enumerate(lines):
        if "tareas del día" in line.lower() or (line.strip().startswith("## ✅")):
            lines.insert(i + 1, entry)
            _write_lines(dest, lines)
            print(f"✓ [diario {today.isoformat()}] {entry}")
            return 0

    lines.append(entry)
    _write_lines(dest, lines)
    print(f"✓ [diario {today.isoformat()}] {entry}")
    return 0


# ── schedule ──────────────────────────────────────────────────────────────────

def run_task_schedule(project: Optional[str], task_desc: str, fecha: Optional[str]) -> int:
    if not fecha:
        print("Error: --date es obligatorio para schedule")
        return 1

    project_dirs = _resolve_projects(project)
    if not project_dirs:
        return 1

    for project_dir, proyecto_path in project_dirs:
        lines = proyecto_path.read_text().splitlines()
        idx = _find_task_line(lines, task_desc)
        if idx == -1:
            continue
        stripped = lines[idx].strip()
        content = stripped[5:].strip()
        desc_only, old_date = _extract_date_from_parens(content)
        lines[idx] = f"- [ ] {desc_only} ({fecha})"
        _write_lines(proyecto_path, lines)
        old = f" (antes: {old_date})" if old_date else ""
        print(f"✓ [{project_dir.name}] Reprogramada{old} → ({fecha}): {desc_only}")
        return 0

    print(f"Error: no se encontró tarea que coincida con '{task_desc}'")
    return 1


# ── close ─────────────────────────────────────────────────────────────────────

def run_task_close(project: Optional[str], task_desc: str, fecha: Optional[str]) -> int:
    done_str = fecha or date.today().isoformat()

    project_dirs = _resolve_projects(project)
    if not project_dirs:
        return 1

    for project_dir, proyecto_path in project_dirs:
        lines = proyecto_path.read_text().splitlines()
        idx = _find_task_line(lines, task_desc)
        if idx == -1:
            continue
        stripped = lines[idx].strip()
        content = stripped[5:].strip()
        desc_only, _ = _extract_date_from_parens(content)
        lines[idx] = f"- [x] {desc_only} ({done_str})"
        _write_lines(proyecto_path, lines)
        print(f"✓ [{project_dir.name}] Completada: {desc_only} ({done_str})")
        return 0

    print(f"Error: no se encontró tarea que coincida con '{task_desc}'")
    return 1


# ── helpers ───────────────────────────────────────────────────────────────────

def _resolve_projects(project: Optional[str]) -> list:
    """Return list of (project_dir, proyecto_path). If project given, find one match.
    If not given, return all active projects."""
    results = []
    if project:
        project_dir = find_project(project)
        if not project_dir:
            return []
        proyecto_path = find_proyecto_file(project_dir)
        if not proyecto_path or not proyecto_path.exists():
            print(f"Error: no se encontró el archivo de proyecto en {project_dir.name}")
            return []
        return [(project_dir, proyecto_path)]

    if not PROJECTS_DIR.exists():
        return []
    for project_dir in sorted(PROJECTS_DIR.iterdir()):
        if not project_dir.is_dir():
            continue
        proyecto_path = find_proyecto_file(project_dir)
        if proyecto_path and proyecto_path.exists():
            results.append((project_dir, proyecto_path))
    return results

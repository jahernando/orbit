"""orbit done — mark a task as completed with today's date."""

from datetime import date
from typing import Optional

from core.log import find_project, find_proyecto_file
from core.tasks import _extract_date_from_parens


def run_done(project: str, task_desc: str, done_date: Optional[str] = None) -> int:
    done_str = done_date or date.today().isoformat()

    project_dir = find_project(project)
    if not project_dir:
        return 1

    proyecto_path = find_proyecto_file(project_dir)
    if not proyecto_path or not proyecto_path.exists():
        print(f"Error: no se encontró el archivo de proyecto en {project_dir.name}")
        return 1

    lines = proyecto_path.read_text().splitlines()
    found = False
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped.startswith("- [ ]"):
            continue
        content = stripped[5:].strip()
        desc_only, _ = _extract_date_from_parens(content)
        if task_desc.lower() in desc_only.lower():
            lines[i] = f"- [x] {desc_only} ({done_str})"
            found = True
            print(f"✓ [{project_dir.name}] Completada: {desc_only} ({done_str})")
            break

    if not found:
        print(f"Error: no se encontró tarea que coincida con '{task_desc}' en {project_dir.name}")
        return 1

    proyecto_path.write_text("\n".join(lines) + "\n")
    return 0

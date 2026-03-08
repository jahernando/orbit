"""core/add.py — add items to project sections (ref, result, decision)."""

import shutil
import subprocess
from pathlib import Path
from typing import Optional

from core.log import (
    PROJECTS_DIR, find_project, find_proyecto_file, find_logbook_file,
    format_entry, _append_entry,
)
from core.open import open_file

# Maps action → (section heading, logbook tag, files subdirectory)
SECTION_MAP = {
    "ref":      ("## 📎 Referencias", "referencia", "references"),
    "result":   ("## 📊 Resultados",  "resultado",  "results"),
    "decision": ("## 📌 Decisiones",  "decision",   "decisions"),
}


def _insert_into_section(proyecto_path: Path, heading: str, new_line: str) -> bool:
    """Insert new_line into the section identified by heading in proyecto.md."""
    lines = proyecto_path.read_text().splitlines()

    section_idx = next((i for i, l in enumerate(lines) if l.strip() == heading), None)
    if section_idx is None:
        return False

    # Find where the section ends (next ## heading or EOF)
    end_idx = len(lines)
    for i in range(section_idx + 1, len(lines)):
        if lines[i].startswith("## "):
            end_idx = i
            break

    # Collect section body, drop standalone placeholder '-' and trailing blanks
    body = [l for l in lines[section_idx + 1:end_idx]
            if l.strip() and l.strip() != "-"]
    body.append(new_line)

    rebuilt = lines[:section_idx + 1] + body + [""] + lines[end_idx:]
    proyecto_path.write_text("\n".join(rebuilt) + "\n")
    return True


def _copy_file(file_str: str, dest_dir: Path) -> Optional[Path]:
    src = Path(file_str).expanduser().resolve()
    if not src.exists():
        print(f"Error: fichero no encontrado: {src}")
        return None
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / src.name
    shutil.copy2(src, dest)
    return dest


def _git_add(file_path: Path) -> bool:
    result = subprocess.run(
        ["git", "add", "-f", str(file_path)],
        capture_output=True,
        cwd=Path(__file__).parent.parent,
    )
    return result.returncode == 0


def _valid_time(t: str) -> bool:
    parts = t.split(":")
    if len(parts) != 2:
        return False
    try:
        h, m = int(parts[0]), int(parts[1])
        return 0 <= h <= 23 and 0 <= m <= 59
    except ValueError:
        return False


def run_add(
    action: str,
    project: str,
    title: str,
    url: Optional[str],
    file_str: Optional[str],
    sync: bool,
    date_str: Optional[str],
    open_after: bool,
    editor: str,
) -> int:
    project_dir = find_project(project)
    if not project_dir:
        return 1

    proyecto_path = find_proyecto_file(project_dir)
    if not proyecto_path or not proyecto_path.exists():
        print(f"Error: fichero de proyecto no encontrado en {project_dir}")
        return 1

    # ── ref / result / decision ───────────────────────────────────────────────
    heading, tag, dir_name = SECTION_MAP[action]

    # Resolve content and optional file copy
    log_path = None
    if file_str:
        dest_file = _copy_file(file_str, project_dir / dir_name)
        if not dest_file:
            return 1
        rel_path  = f"./{dir_name}/{dest_file.name}"
        content   = f"[{title}]({rel_path})"
        log_path  = rel_path
        if sync:
            if _git_add(dest_file):
                print(f"  ✓ git add -f {dest_file.name}")
            else:
                print(f"  ⚠️  No se pudo añadir a git: {dest_file.name}")
    elif url:
        content  = f"[{title}]({url})"
        log_path = url
    else:
        content = title

    # Insert into project section
    if not _insert_into_section(proyecto_path, heading, f"- {content}"):
        print(f"Error: sección '{heading}' no encontrada en {proyecto_path.name}")
        return 1
    print(f"✓ [{project_dir.name}] {heading}: {content}")

    # Append to logbook
    logbook = find_logbook_file(project_dir)
    if logbook:
        entry = format_entry(title, tag, log_path, None)
        _append_entry(logbook, entry)
        print(f"  → logbook: {entry.strip()}")

    if open_after:
        open_file(proyecto_path, editor)
    return 0

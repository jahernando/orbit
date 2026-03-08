"""core/add.py — add refs, results, decisions and notes to projects."""

import shutil
import subprocess
from datetime import date
from pathlib import Path
from typing import Optional

from core.log import (
    PROJECTS_DIR, find_project, find_proyecto_file, find_logbook_file,
    format_entry, _append_entry, TAG_EMOJI,
)
from core.open import open_file

# entry type → (section heading in proyecto.md, file subdirectory)
ENTRY_SECTION_MAP = {
    "referencia": ("## 📎 Referencias", "references"),
    "resultado":  ("## 📊 Resultados",  "results"),
    "decision":   ("## 📌 Decisiones",  "decisions"),
    "apunte":     ("## 📎 Referencias", "references"),
    "idea":       ("## 📎 Referencias", "references"),
    "problema":   ("## 📎 Referencias", "references"),
}

VALID_ENTRIES = list(ENTRY_SECTION_MAP.keys())
NOTES_DIR_NAME = "notes"
TEMPLATES_DIR  = Path(__file__).parent.parent / "📐templates"


def _insert_into_section(proyecto_path: Path, heading: str, new_line: str) -> bool:
    """Insert new_line into the section identified by heading in proyecto.md."""
    lines = proyecto_path.read_text().splitlines()
    section_idx = next((i for i, l in enumerate(lines) if l.strip() == heading), None)
    if section_idx is None:
        return False
    end_idx = len(lines)
    for i in range(section_idx + 1, len(lines)):
        if lines[i].startswith("## "):
            end_idx = i
            break
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


def run_add(
    project: str,
    title: str,
    entry: str,
    url: Optional[str],
    file_str: Optional[str],
    sync: bool,
    open_after: bool,
    editor: str,
) -> int:
    """Add a ref, result, decision, apunte or idea to a project.

    entry determines the section in proyecto.md and the logbook tag.
    """
    project_dir = find_project(project)
    if not project_dir:
        return 1
    proyecto_path = find_proyecto_file(project_dir)
    if not proyecto_path or not proyecto_path.exists():
        print(f"Error: fichero de proyecto no encontrado en {project_dir}")
        return 1

    heading, dir_name = ENTRY_SECTION_MAP.get(entry, ("## 📎 Referencias", "references"))
    emoji = TAG_EMOJI.get(entry, "")

    log_path = None
    if file_str:
        dest_file = _copy_file(file_str, project_dir / dir_name)
        if not dest_file:
            return 1
        rel_path = f"./{dir_name}/{dest_file.name}"
        content  = f"{emoji} [{title}]({rel_path})"
        log_path = rel_path
        if sync:
            if _git_add(dest_file):
                print(f"  ✓ git add -f {dest_file.name}")
            else:
                print(f"  ⚠️  No se pudo añadir a git: {dest_file.name}")
    elif url:
        content  = f"{emoji} [{title}]({url})"
        log_path = url
    else:
        content = f"{emoji} {title}"

    if not _insert_into_section(proyecto_path, heading, f"- {content}"):
        print(f"Error: sección '{heading}' no encontrada en {proyecto_path.name}")
        return 1
    print(f"✓ [{project_dir.name}] {heading}: {content}")

    logbook = find_logbook_file(project_dir)
    if logbook:
        log_entry = format_entry(title, entry, log_path, None)
        _append_entry(logbook, log_entry)
        print(f"  → logbook: {log_entry.strip()}")

    if open_after:
        open_file(proyecto_path, editor)
    return 0


def run_add_note(
    project: str,
    title: str,
    entry: str,
    file_str: Optional[str],
    link: bool,
    open_after: bool,
    editor: str,
) -> int:
    """Create or import a markdown note into the project's notes/ directory.

    Without --file: creates a new .md from template and opens it in editor.
    With --file:    copies an existing .md into notes/.
    With --link:    adds a reference line to proyecto.md.
    Always adds a logbook entry.
    """
    project_dir = find_project(project)
    if not project_dir:
        return 1
    proyecto_path = find_proyecto_file(project_dir)
    if not proyecto_path or not proyecto_path.exists():
        print(f"Error: fichero de proyecto no encontrado en {project_dir}")
        return 1

    notes_dir  = project_dir / NOTES_DIR_NAME
    emoji      = TAG_EMOJI.get(entry, "📝")
    today      = date.today().isoformat()

    if file_str:
        dest_file  = _copy_file(file_str, notes_dir)
        if not dest_file:
            return 1
        note_title = title or dest_file.stem
        print(f"✓ [{project_dir.name}] Nota importada: {dest_file.name}")
    else:
        # Create new note from template
        slug      = title.lower().replace(" ", "-")[:40]
        note_name = f"{today}-{slug}.md"
        dest_file = notes_dir / note_name
        note_title = title
        tpl = TEMPLATES_DIR / "note.md"
        if tpl.exists():
            content = (tpl.read_text()
                       .replace("TÍTULO", title)
                       .replace("YYYY-MM-DD", today)
                       .replace("PROYECTO", project_dir.name))
        else:
            content = f"# {title}\n\n*{today} — {project_dir.name}*\n\n---\n\n"
        notes_dir.mkdir(parents=True, exist_ok=True)
        dest_file.write_text(content)
        print(f"✓ [{project_dir.name}] Nota creada: {dest_file.name}")

    rel_path = f"./{NOTES_DIR_NAME}/{dest_file.name}"

    if link:
        heading, _ = ENTRY_SECTION_MAP.get(entry, ("## 📎 Referencias", "references"))
        line = f"- {emoji} [{note_title}]({rel_path})"
        if _insert_into_section(proyecto_path, heading, line):
            print(f"  → {heading}: {line}")
        else:
            print(f"  ⚠️  Sección '{heading}' no encontrada, sin enlace en proyecto")

    logbook = find_logbook_file(project_dir)
    if logbook:
        log_entry = format_entry(note_title, entry, rel_path, None)
        _append_entry(logbook, log_entry)
        print(f"  → logbook: {log_entry.strip()}")

    # Always open new notes; open imported notes only if --open
    if open_after or not file_str:
        open_file(dest_file, editor)
    return 0

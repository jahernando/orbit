"""orbit open — open a note in an external editor or renderer."""

import re
import subprocess
import sys
from datetime import date
from pathlib import Path
from typing import Optional

from core.log import find_project, find_logbook_file, find_proyecto_file

MISION_LOG_DIR = Path(__file__).parent.parent / "☀️mision-log"
DIARIO_DIR  = MISION_LOG_DIR / "diario"
SEMANAL_DIR = MISION_LOG_DIR / "semanal"
MENSUAL_DIR = MISION_LOG_DIR / "mensual"

EDITORS = {
    "typora": ["open", "-a", "Typora"],
    "glow":   ["glow"],
    "code":   ["code"],
}


def _resolve_path(target: str, log: bool) -> Optional[Path]:
    """Resolve target string to a file path."""
    # Week: YYYY-Wnn
    if re.match(r"^\d{4}-W\d{2}$", target):
        return SEMANAL_DIR / f"{target}.md"
    # Month: YYYY-MM
    if re.match(r"^\d{4}-\d{2}$", target) and len(target) == 7:
        return MENSUAL_DIR / f"{target}.md"
    # Date: YYYY-MM-DD
    if re.match(r"^\d{4}-\d{2}-\d{2}$", target):
        return DIARIO_DIR / f"{target}.md"
    # Project name
    project_dir = find_project(target)
    if not project_dir:
        return None
    if log:
        return find_logbook_file(project_dir)
    return find_proyecto_file(project_dir)


def open_file(path: Path, editor: str) -> int:
    """Open a file in the given editor. Returns 0 on success."""
    cmd_base = EDITORS.get(editor)
    if cmd_base:
        cmd = cmd_base + [str(path)]
    else:
        # fallback: treat editor as a raw command
        cmd = [editor, str(path)]

    # glow runs in the foreground (terminal renderer); others launch a GUI app
    foreground = editor == "glow" or editor not in EDITORS
    try:
        if foreground:
            result = subprocess.run(cmd)
            return result.returncode
        else:
            subprocess.Popen(cmd)
            return 0
    except FileNotFoundError:
        print(f"Error: editor '{editor}' no encontrado. ¿Está instalado?")
        return 1


def find_note(project_dir: Path, note_partial: str) -> Optional[Path]:
    """Return the first note in notes/ whose name contains note_partial (case-insensitive).
    If not found, prints available notes as suggestions.
    """
    notes_dir = project_dir / "notes"
    if not notes_dir.exists():
        print(f"Error: el proyecto '{project_dir.name}' no tiene directorio notes/")
        return None
    low = note_partial.lower()
    all_notes = sorted(notes_dir.glob("*.md"))
    matches = [f for f in all_notes if low in f.name.lower()]
    if matches:
        return matches[0]
    print(f"Error: nota '{note_partial}' no encontrada en {project_dir.name}/notes/")
    if all_notes:
        print("  Notas disponibles:")
        for n in all_notes:
            print(f"    📝 {n.name}")
    else:
        print("  (no hay notas en este proyecto)")
    return None


def run_open(target: Optional[str], log: bool, note: Optional[str], editor: str) -> int:
    if not target:
        target = date.today().isoformat()

    # --note: open a specific note inside a project
    if note:
        if not target or target == date.today().isoformat():
            print("Error: --note requiere especificar un proyecto (ej: orbit open mi-proyecto --note titulo)")
            return 1
        project_dir = find_project(target)
        if not project_dir:
            print(f"Error: proyecto '{target}' no encontrado")
            return 1
        path = find_note(project_dir, note)
        if not path:
            return 1
    else:
        path = _resolve_path(target, log)
        if path is None:
            print(f"Error: no se encontró ningún fichero para '{target}'")
            return 1

    if not path.exists():
        print(f"Error: el fichero no existe: {path}")
        return 1

    print(f"Abriendo {path.name} con {editor}...")
    return open_file(path, editor)

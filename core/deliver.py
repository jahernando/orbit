"""deliver.py — deliver files to cloud and optionally log/highlight them.

  deliver <project> <file> "<title>" [--log] [--hl] [--entry TIPO] [--type TIPO]

Wraps the bash deliver script and optionally creates logbook/highlights entries.
"""
import subprocess
import sys
from pathlib import Path
from typing import Optional

from core.config import ORBIT_HOME as ORBIT_DIR
from core.log import find_project, add_entry, VALID_TYPES
from core.highlights import run_hl_add, VALID_TYPES as HL_TYPES


IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".bmp", ".tiff"}


def _run_bash_deliver(project: str, file: str) -> int:
    """Call the bash deliver script. Returns returncode."""
    deliver_bin = ORBIT_DIR / "bin" / "deliver"
    if not deliver_bin.exists():
        print(f"Error: no se encuentra {deliver_bin}")
        return 1
    try:
        result = subprocess.run(
            [str(deliver_bin), project, file],
            cwd=ORBIT_DIR,
        )
        return result.returncode
    except FileNotFoundError:
        print("Error: no se pudo ejecutar deliver")
        return 1


def _format_log_path(file: str) -> str:
    """Build the path string for a logbook entry.

    For images, uses ![](path) syntax so markdown renderers show the image.
    For other files, uses a plain relative path (format_entry wraps it as a link).
    """
    ext = Path(file).suffix.lower()
    if ext in IMAGE_EXTS:
        return f"![]({file})"
    return file


def run_deliver(project: str, file: str, title: str,
                log: bool = False, hl: bool = False,
                entry_type: str = "apunte", hl_type: str = "refs") -> int:
    """Deliver a file and optionally create logbook/highlights entries."""

    # Validate types before doing anything
    if log and entry_type not in VALID_TYPES:
        print(f"Error: --entry '{entry_type}' no válido. Opciones: {', '.join(VALID_TYPES)}")
        return 1
    if hl and hl_type not in HL_TYPES:
        print(f"Error: --type '{hl_type}' no válido. Opciones: {', '.join(HL_TYPES)}")
        return 1

    # Check the source file exists
    project_dir = find_project(project)
    if not project_dir:
        return 1
    src = project_dir / file
    if not src.exists():
        print(f"Error: no existe {src}")
        return 1

    # 1. Deliver to cloud
    rc = _run_bash_deliver(project, file)
    if rc != 0:
        return rc

    # 2. Logbook entry
    if log:
        path_str = _format_log_path(file)
        rc = add_entry(project, title, entry_type, path_str, None)
        if rc != 0:
            return rc

    # 3. Highlights entry
    if hl:
        rc = run_hl_add(project, title, hl_type, link=file)
        if rc != 0:
            return rc

    return 0

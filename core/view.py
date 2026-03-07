"""orbit view — display notes, logbooks and mision-log files in the terminal."""

import re
from datetime import date
from pathlib import Path
from typing import Optional

from core.log import PROJECTS_DIR, VALID_TYPES, find_project, find_logbook_file, find_proyecto_file

MISION_LOG_DIR = Path(__file__).parent.parent / "☀️mision-log"
DIARIO_DIR  = MISION_LOG_DIR / "diario"
SEMANAL_DIR = MISION_LOG_DIR / "semanal"
MENSUAL_DIR = MISION_LOG_DIR / "mensual"

# Markers to strip from output
_ORBIT_MARKERS = re.compile(r'<!-- orbit:[^>]+ -->')


def _render(text: str) -> str:
    """Strip HTML comments and orbit markers for clean terminal display."""
    text = _ORBIT_MARKERS.sub("", text)
    text = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)
    # Collapse resulting blank lines > 2
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _extract_section(text: str, section: str) -> str:
    """Return content of the first ## section whose title contains 'section' (case-insensitive)."""
    lines = text.splitlines()
    in_section = False
    result = []
    for line in lines:
        if line.startswith("## "):
            if in_section:
                break
            if section.lower() in line.lower():
                in_section = True
                result.append(line)
            continue
        if in_section:
            result.append(line)
    if not result:
        return f"(sección '{section}' no encontrada)"
    return "\n".join(result).strip()


def _filter_entries(text: str, tipo: str) -> str:
    """Return only logbook lines ending with #tipo, plus the header."""
    lines = text.splitlines()
    result = []
    for line in lines:
        # Keep header lines (# headings and comments)
        if line.startswith("#") or line.startswith("<!--"):
            result.append(line)
            continue
        if line.strip().endswith(f"#{tipo}"):
            result.append(line)
    return "\n".join(result).strip()


def _resolve_target(target: str):
    """Return (path, kind) where kind is 'project', 'logbook', 'diario', 'semanal', 'mensual'."""
    # Week: YYYY-Wnn
    if re.match(r"^\d{4}-W\d{2}$", target):
        p = SEMANAL_DIR / f"{target}.md"
        return p, "semanal"
    # Month: YYYY-MM (7 chars)
    if re.match(r"^\d{4}-\d{2}$", target) and len(target) == 7:
        p = MENSUAL_DIR / f"{target}.md"
        return p, "mensual"
    # Date: YYYY-MM-DD
    if re.match(r"^\d{4}-\d{2}-\d{2}$", target):
        p = DIARIO_DIR / f"{target}.md"
        return p, "diario"
    # Project name
    return None, "project"


def run_view(
    target: Optional[str],
    section: Optional[str],
    entrada: Optional[str],
    log: bool,
    output: Optional[str],
) -> int:
    if not target:
        target = date.today().isoformat()
    path, kind = _resolve_target(target)

    if kind == "project":
        project_dir = find_project(target)
        if not project_dir:
            return 1
        if log or entrada:
            path = find_logbook_file(project_dir)
            if not path:
                print(f"Error: no se encontró logbook en {project_dir.name}")
                return 1
            kind = "logbook"
        else:
            path = find_proyecto_file(project_dir)
            if not path:
                print(f"Error: no se encontró fichero de proyecto en {project_dir.name}")
                return 1

    if not path or not path.exists():
        print(f"Error: no existe {path or target}")
        return 1

    text = path.read_text()

    # Apply --entrada filter (logbook entries by type)
    if entrada:
        if entrada not in VALID_TYPES:
            print(f"Error: tipo '{entrada}' no válido. Tipos: {', '.join(VALID_TYPES)}")
            return 1
        text = _filter_entries(text, entrada)

    # Apply --section filter
    if section:
        text = _extract_section(text, section)

    # Clean markers
    text = _render(text)

    # Header showing what we're viewing
    label = path.name
    print(f"── {label} ──")
    print()
    print(text)
    print()

    if output:
        Path(output).write_text(text + "\n")
        print(f"✓ Guardado en {output}")

    return 0

"""orbit search — full-text search across project logbooks and notes."""

import re
import unicodedata
from pathlib import Path
from typing import Optional

from core.log import PROJECTS_DIR, find_project, find_logbook_file, find_proyecto_file
from core.tasks import load_project_meta
from core.open import open_file

MISION_LOG_DIR = Path(__file__).parent.parent / "☀️mision-log"
SEARCH_OUTPUT  = MISION_LOG_DIR / "search.md"


def _heading_anchor(heading: str) -> str:
    """Convert a ## heading line to a URL anchor."""
    text = heading.lstrip("#").strip()
    text = unicodedata.normalize("NFD", text).encode("ascii", "ignore").decode()
    text = re.sub(r"[^\w\s-]", "", text).strip().lower()
    return re.sub(r"\s+", "-", text)


def _matches(line: str, keywords: list) -> bool:
    """True if all keywords appear in line (case-insensitive)."""
    low = line.lower()
    return all(kw.lower() in low for kw in keywords)


def _search_logbook(path: Path, keywords: list, tag: Optional[str], date_filter: Optional[str]) -> list:
    results = []
    for line in path.read_text().splitlines():
        s = line.strip()
        if not s or s.startswith("#") or s.startswith("<!--"):
            continue
        if tag and not s.endswith(f"#{tag}"):
            continue
        if date_filter and not s.startswith(date_filter):
            continue
        if keywords and not _matches(s, keywords):
            continue
        results.append(s)
    return results


def _search_proyecto(path: Path, keywords: list) -> list:
    """Return list of (section_heading, anchor, line) matches in proyecto.md."""
    results = []
    current_section = ""
    current_anchor  = ""
    for line in path.read_text().splitlines():
        if line.startswith("## "):
            current_section = line.strip()
            current_anchor  = _heading_anchor(line)
            continue
        if line.startswith("#") or line.startswith("<!--") or not line.strip():
            continue
        if keywords and not _matches(line, keywords):
            continue
        results.append((current_section, current_anchor, line.strip()))
    return results


def run_search(
    query: Optional[str],
    projects: Optional[list],
    tag: Optional[str],
    date_filter: Optional[str],
    output: Optional[str],
    open_after: bool,
    editor: str,
) -> int:
    if not PROJECTS_DIR.exists():
        print(f"Error: directorio de proyectos no encontrado en {PROJECTS_DIR}")
        return 1

    keywords = query.split() if query else []
    logbooks_only = bool(tag)

    # Resolve project dirs
    if projects:
        project_dirs = []
        for p in projects:
            d = find_project(p)
            if d:
                project_dirs.append(d)
        if not project_dirs:
            return 1
    else:
        project_dirs = sorted([d for d in PROJECTS_DIR.iterdir() if d.is_dir()])

    query_label = f'"{query}"' if query else "(todas las entradas)"
    lines_out = [f"🔍 {query_label}", ""]
    total = 0

    for project_dir in project_dirs:
        proyecto_path = find_proyecto_file(project_dir)
        if not proyecto_path or not proyecto_path.exists():
            continue

        meta = load_project_meta(proyecto_path)
        project_hits = []

        # Search logbook
        logbook_path = find_logbook_file(project_dir)
        if logbook_path and logbook_path.exists():
            matches = _search_logbook(logbook_path, keywords, tag, date_filter)
            if matches:
                link = f"[{logbook_path.name}](file://{logbook_path.resolve()})"
                project_hits.append((link, matches))
                total += len(matches)

        # Search proyecto.md (only when no tag filter)
        if not logbooks_only:
            proj_matches = _search_proyecto(proyecto_path, keywords)
            if proj_matches:
                by_section: dict = {}
                for section, anchor, line in proj_matches:
                    by_section.setdefault((section, anchor), []).append(line)
                for (section, anchor), hits in by_section.items():
                    label = (f"{proyecto_path.name} › {section.lstrip('# ').strip()}"
                             if section else proyecto_path.name)
                    link = f"[{label}](file://{proyecto_path.resolve()}#{anchor})"
                    project_hits.append((link, hits))
                    total += len(hits)

        if project_hits:
            header = f"{project_dir.name}  {meta['tipo']} {meta['estado']}  {meta['prioridad']}"
            lines_out.append(f"**{header}**")
            for link, hits in project_hits:
                lines_out.append(f"  {link}")
                for h in hits:
                    lines_out.append(f"    {h}")
            lines_out.append("")

    lines_out[0] = f'🔍 {query_label} — {total} resultado{"s" if total != 1 else ""}'
    if not total:
        lines_out.append("_Sin resultados._")

    text = "\n".join(lines_out)

    # Determine output destination
    if open_after and not output:
        dest = SEARCH_OUTPUT
    elif output:
        dest = Path(output)
    else:
        dest = None

    if dest:
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(text + "\n")
        print(f"✓ Guardado en {dest}")
        if open_after:
            open_file(dest, editor)
    else:
        print(text)

    return 0

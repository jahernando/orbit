"""orbit search — full-text search across project logbooks, notes and diario."""

import re
import unicodedata
from datetime import date
from pathlib import Path
from typing import Optional

from core.log import PROJECTS_DIR, find_project, find_logbook_file, find_proyecto_file
from core.tasks import load_project_meta, normalize
from core.open import open_file

MISION_LOG_DIR = Path(__file__).parent.parent / "☀️mision-log"
DIARIO_DIR     = MISION_LOG_DIR / "diario"
SEMANAL_DIR    = MISION_LOG_DIR / "semanal"
MENSUAL_DIR    = MISION_LOG_DIR / "mensual"
SEARCH_OUTPUT  = MISION_LOG_DIR / "search.md"


def _heading_anchor(heading: str) -> str:
    text = heading.lstrip("#").strip()
    text = unicodedata.normalize("NFD", text).encode("ascii", "ignore").decode()
    text = re.sub(r"[^\w\s-]", "", text).strip().lower()
    return re.sub(r"\s+", "-", text)


def _matches(line: str, keywords: list, any_mode: bool) -> bool:
    """AND mode: all keywords must match. OR mode: at least one."""
    low = line.lower()
    if not keywords:
        return True
    if any_mode:
        return any(kw.lower() in low for kw in keywords)
    return all(kw.lower() in low for kw in keywords)


def _in_date_range(line: str, date_from: Optional[str], date_to: Optional[str],
                   date_filter: Optional[str]) -> bool:
    """Check if a logbook line's date falls within the specified range/filter."""
    if not date_from and not date_to and not date_filter:
        return True
    # Extract leading date YYYY-MM-DD
    m = re.match(r"^(\d{4}-\d{2}-\d{2})", line.strip())
    if not m:
        return not (date_from or date_to or date_filter)
    line_date = m.group(1)
    if date_filter:
        return line_date.startswith(date_filter)
    if date_from and line_date < date_from:
        return False
    if date_to and line_date > date_to:
        return False
    return True


def _search_logbook(path: Path, keywords: list, tag: Optional[str],
                    date_filter: Optional[str], date_from: Optional[str],
                    date_to: Optional[str], any_mode: bool, limit: int) -> list:
    results = []
    for line in path.read_text().splitlines():
        if limit and len(results) >= limit:
            break
        s = line.strip()
        if not s or s.startswith("#") or s.startswith("<!--"):
            continue
        if tag and not s.endswith(f"#{tag}"):
            continue
        if not _in_date_range(s, date_from, date_to, date_filter):
            continue
        if keywords and not _matches(s, keywords, any_mode):
            continue
        results.append(s)
    return results


def _search_proyecto(path: Path, keywords: list, any_mode: bool) -> list:
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
        if keywords and not _matches(line, keywords, any_mode):
            continue
        results.append((current_section, current_anchor, line.strip()))
    return results


def _search_misionlog(keywords: list, tag: Optional[str], date_filter: Optional[str],
                      date_from: Optional[str], date_to: Optional[str],
                      any_mode: bool, limit: int) -> list:
    """Search across diario, semanal and mensual files. Returns list of (label, link, hits)."""
    results = []
    for directory, label in [(DIARIO_DIR, "diario"), (SEMANAL_DIR, "semanal"), (MENSUAL_DIR, "mensual")]:
        if not directory.exists():
            continue
        for md_file in sorted(directory.glob("*.md"), reverse=True):
            hits = _search_logbook(md_file, keywords, tag, date_filter, date_from, date_to, any_mode, limit)
            if hits:
                link = f"[{label}/{md_file.name}](file://{md_file.resolve()})"
                results.append((link, hits))
    return results


def _search_notes(project_dir: Path, keywords: list, any_mode: bool, limit: int) -> list:
    """Search all .md files in project notes/ dir. Returns list of (filename, hits)."""
    notes_dir = project_dir / "notes"
    if not notes_dir.exists():
        return []
    results = []
    for md_file in sorted(notes_dir.glob("*.md")):
        hits = []
        for line in md_file.read_text().splitlines():
            if limit and len(hits) >= limit:
                break
            s = line.strip()
            if not s or s.startswith("<!--"):
                continue
            # Include H1 titles; skip deeper headings (## and beyond) as structural noise
            if s.startswith("## ") or s.startswith("### "):
                continue
            if keywords and not _matches(s, keywords, any_mode):
                continue
            hits.append(s)
        if hits:
            results.append((md_file, hits))
    return results


def run_search(
    query: Optional[str],
    projects: Optional[list],
    tag: Optional[str],
    date_filter: Optional[str],
    date_from: Optional[str],
    date_to: Optional[str],
    tipo: Optional[str],
    estado: Optional[str],
    prioridad: Optional[str],
    any_mode: bool,
    diario: bool,
    notes: bool,
    limit: int,
    output: Optional[str],
    open_after: bool,
    editor: str,
) -> int:
    if not PROJECTS_DIR.exists():
        print(f"Error: directorio de proyectos no encontrado en {PROJECTS_DIR}")
        return 1

    keywords = query.split() if query else []
    logbooks_only = bool(tag)

    # Build query label for header
    query_label = f'"{query}"' if query else "(todas las entradas)"
    if any_mode and len(keywords) > 1:
        query_label += " [OR]"

    lines_out = [f"🔍 {query_label}", ""]
    total = 0

    # Search mision-log if requested
    if diario:
        mision_hits = _search_misionlog(keywords, tag, date_filter, date_from, date_to, any_mode, limit)
        for link, hits in mision_hits:
            lines_out.append(f"**☀️ mision-log**")
            lines_out.append(f"  {link}")
            for h in hits:
                lines_out.append(f"    {h}")
            lines_out.append("")
            total += len(hits)

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

    remaining = (limit - total) if limit else 0

    for project_dir in project_dirs:
        if limit and total >= limit:
            break

        proyecto_path = find_proyecto_file(project_dir)
        if not proyecto_path or not proyecto_path.exists():
            continue

        meta = load_project_meta(proyecto_path)

        if tipo and normalize(tipo) not in meta["tipo_raw"]:
            continue
        if estado and normalize(estado) not in meta["estado_raw"]:
            continue
        if prioridad and normalize(prioridad) not in meta["prioridad_raw"]:
            continue

        project_hits = []
        proj_limit = (limit - total) if limit else 0

        # Search logbook
        logbook_path = find_logbook_file(project_dir)
        if logbook_path and logbook_path.exists():
            matches = _search_logbook(logbook_path, keywords, tag, date_filter,
                                      date_from, date_to, any_mode, proj_limit)
            if matches:
                link = f"[{logbook_path.name}](file://{logbook_path.resolve()})"
                project_hits.append((link, matches))
                total += len(matches)

        # Search proyecto.md (only when no tag filter)
        if not logbooks_only:
            proj_matches = _search_proyecto(proyecto_path, keywords, any_mode)
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

        # Search notes/ directory if requested
        if notes and not logbooks_only:
            note_matches = _search_notes(project_dir, keywords, any_mode,
                                         (limit - total) if limit else 0)
            for note_file, hits in note_matches:
                link = f"[notes/{note_file.name}](file://{note_file.resolve()})"
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

    suffix = f" (primeros {limit})" if limit and total >= limit else ""
    lines_out[0] = f'🔍 {query_label} — {total} resultado{"s" if total != 1 else ""}{suffix}'
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

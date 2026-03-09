"""orbit search — full-text search across project logbooks, highlights, agenda and notes."""

import re
from pathlib import Path
from typing import Optional

from core.log import (PROJECTS_DIR, find_project, find_logbook_file,
                      find_highlights_file, find_agenda_file)
from core.open import open_file, open_cmd_output
from core.project import _is_new_project, _read_project_meta


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


def _search_file(path: Path, keywords: list, any_mode: bool, limit: int) -> list:
    """Search any markdown file for matching non-comment lines."""
    results = []
    for line in path.read_text().splitlines():
        if limit and len(results) >= limit:
            break
        s = line.strip()
        if not s or s.startswith("#") or s.startswith("<!--"):
            continue
        if keywords and not _matches(s, keywords, any_mode):
            continue
        results.append(s)
    return results


def _search_notes(project_dir: Path, keywords: list, any_mode: bool, limit: int) -> list:
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
    projects: Optional[list] = None,
    tag: Optional[str] = None,
    date_filter: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    any_mode: bool = False,
    notes: bool = False,
    limit: int = 0,
    open_after: bool = False,
    editor: str = "",
    in_filter: Optional[str] = None,
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

    for project_dir in project_dirs:
        if limit and total >= limit:
            break

        is_new = _is_new_project(project_dir)
        proj_limit = (limit - total) if limit else 0

        # Read metadata for display header
        if is_new:
            meta = _read_project_meta(project_dir)
            header_meta = f"{meta['tipo_emoji']} {meta.get('tipo_label', '')}"
        else:
            header_meta = ""

        project_hits = []

        # Determine which files to search based on --in filter
        search_logbook_f    = not in_filter or in_filter == "logbook"
        search_highlights_f = in_filter == "highlights"
        search_agenda_f     = in_filter == "agenda"

        # Search logbook
        if search_logbook_f:
            logbook_path = find_logbook_file(project_dir)
            if logbook_path and logbook_path.exists():
                matches = _search_logbook(logbook_path, keywords, tag, date_filter,
                                          date_from, date_to, any_mode, proj_limit)
                if matches:
                    link = f"[{logbook_path.name}](file://{logbook_path.resolve()})"
                    project_hits.append((link, matches))
                    total += len(matches)

        # Search highlights
        if search_highlights_f and is_new:
            hl_path = find_highlights_file(project_dir)
            if hl_path and hl_path.exists():
                matches = _search_file(hl_path, keywords, any_mode, proj_limit)
                if matches:
                    link = f"[{hl_path.name}](file://{hl_path.resolve()})"
                    project_hits.append((link, matches))
                    total += len(matches)

        # Search agenda
        if search_agenda_f and is_new:
            ag_path = find_agenda_file(project_dir)
            if ag_path and ag_path.exists():
                matches = _search_file(ag_path, keywords, any_mode, proj_limit)
                if matches:
                    link = f"[{ag_path.name}](file://{ag_path.resolve()})"
                    project_hits.append((link, matches))
                    total += len(matches)

        # Search notes/ directory if requested
        if notes and not logbooks_only and not in_filter:
            note_matches = _search_notes(project_dir, keywords, any_mode,
                                         (limit - total) if limit else 0)
            for note_file, hits in note_matches:
                link = f"[notes/{note_file.name}](file://{note_file.resolve()})"
                project_hits.append((link, hits))
                total += len(hits)

        if project_hits:
            lines_out.append(f"**{project_dir.name}  {header_meta}**")
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

    if open_after:
        open_cmd_output(text + "\n", editor)
    else:
        print(text)

    return 0

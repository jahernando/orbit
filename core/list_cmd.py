"""orbit list — list projects and project sections."""

import re
from pathlib import Path
from typing import Optional

from core.log import PROJECTS_DIR, find_proyecto_file, TAG_EMOJI
from core.tasks import load_project_meta, normalize
from core.open import open_file
from core.add import extract_section

MISION_LOG_DIR = Path(__file__).parent.parent / "☀️mision-log"

SECTION_HEADINGS = {
    "refs":      "## 📎 Referencias",
    "results":   "## 📊 Resultados",
    "decisions": "## 📌 Decisiones",
}

_FILE_DIRS = ["references", "results", "decisions", "notes"]
_DIR_EMOJI = {"references": "📎", "results": "📊", "decisions": "📌", "notes": "📝"}



def _write_output(text: str, output: Optional[str],
                  open_after: bool, editor: str, default_dest: Path) -> None:
    if open_after and not output:
        dest = default_dest
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


# ── list projects ──────────────────────────────────────────────────────────────

def run_list_projects(tipo: Optional[str], status: Optional[str],
                      priority: Optional[str], output: Optional[str],
                      open_after: bool, editor: str) -> int:
    if not PROJECTS_DIR.exists():
        print("Error: directorio de proyectos no encontrado")
        return 1

    rows = []
    for project_dir in sorted(PROJECTS_DIR.iterdir()):
        if not project_dir.is_dir():
            continue
        proyecto_path = find_proyecto_file(project_dir)
        if not proyecto_path or not proyecto_path.exists():
            continue
        meta = load_project_meta(proyecto_path)
        if tipo     and normalize(tipo)     not in normalize(meta.get("tipo", "")):
            continue
        if status   and normalize(status)   not in normalize(meta.get("estado_raw", "")):
            continue
        if priority and normalize(priority) not in normalize(meta.get("prioridad_raw", "")):
            continue
        rel_path = f"../../🚀proyectos/{project_dir.name}/{proyecto_path.name}"
        rows.append({
            "name":      project_dir.name,
            "link":      f"[{project_dir.name}]({rel_path})",
            "tipo":      meta.get("tipo", ""),
            "estado":    meta.get("estado", ""),
            "prioridad": meta.get("prioridad", ""),
        })

    if not rows:
        print("No hay proyectos que coincidan.")
        return 0

    PRIORITY_ORDER = {"alta": 0, "media": 1, "baja": 2}
    rows.sort(key=lambda r: PRIORITY_ORDER.get(normalize(r["prioridad"]), 9))

    nw = max(len(r["link"])      for r in rows) + 1
    tw = max(len(r["tipo"])      for r in rows) + 1
    ew = max(len(r["estado"])    for r in rows) + 1
    pw = max(len(r["prioridad"]) for r in rows) + 1

    header = f"{'proyecto':<{nw}}  {'tipo':<{tw}}  {'estado':<{ew}}  {'prioridad':<{pw}}"
    sep    = "─" * len(header)

    lines = [f"PROYECTOS ({len(rows)})", "═" * len(header), "", header, sep]
    for r in rows:
        lines.append(
            f"{r['link']:<{nw}}  {r['tipo']:<{tw}}  {r['estado']:<{ew}}  {r['prioridad']:<{pw}}")
    lines.append(sep)

    _write_output("\n".join(lines), output, open_after, editor,
                  MISION_LOG_DIR / "projects.md")
    return 0


# ── list section ───────────────────────────────────────────────────────────────

def run_list_section(project: Optional[str], section: str,
                     entry: Optional[str],
                     output: Optional[str], open_after: bool, editor: str) -> int:
    if not PROJECTS_DIR.exists():
        print("Error: directorio de proyectos no encontrado")
        return 1

    heading = SECTION_HEADINGS.get(section)
    if not heading:
        print(f"Error: sección desconocida '{section}'")
        return 1

    # Emoji filter for --entry
    from core.log import TAG_EMOJI
    entry_emoji = TAG_EMOJI.get(entry) if entry else None

    title = heading.lstrip("# ").strip()
    if entry_emoji:
        title = f"{title} [{entry}]"
    lines = [title, "═" * len(title), ""]
    found = False

    for project_dir in sorted(PROJECTS_DIR.iterdir()):
        if not project_dir.is_dir():
            continue
        if project and project.lower() not in project_dir.name.lower():
            continue
        proyecto_path = find_proyecto_file(project_dir)
        if not proyecto_path or not proyecto_path.exists():
            continue
        items = extract_section(proyecto_path, heading)
        if entry_emoji:
            items = [i for i in items if entry_emoji in i]
        if not items:
            continue
        found = True
        rel_path = f"../../🚀proyectos/{project_dir.name}/{proyecto_path.name}"
        lines.append(f"### [{project_dir.name}]({rel_path})")
        lines.extend(f"  {item}" for item in items)
        lines.append("")

    if not found:
        print(f"No hay entradas en '{title}'.")
        return 0

    _write_output("\n".join(lines), output, open_after, editor,
                  MISION_LOG_DIR / f"{section}.md")
    return 0


# ── list notes ──────────────────────────────────────────────────────────────

def run_list_notes(project: Optional[str], output: Optional[str],
                   open_after: bool, editor: str) -> int:
    """List markdown notes inside projects, with date and title extracted from filename."""
    if not PROJECTS_DIR.exists():
        print("Error: directorio de proyectos no encontrado")
        return 1

    lines = ["NOTAS DE PROYECTO", "═" * 40, ""]
    found = False

    for project_dir in sorted(PROJECTS_DIR.iterdir()):
        if not project_dir.is_dir():
            continue
        if project and project.lower() not in project_dir.name.lower():
            continue
        notes_dir = project_dir / "notes"
        if not notes_dir.exists():
            continue
        notes = sorted(
            (f for f in notes_dir.glob("*.md") if not f.name.startswith(".")),
            reverse=True,
        )
        if not notes:
            continue

        found = True
        proyecto_path = find_proyecto_file(project_dir)
        rel_path = (f"../../🚀proyectos/{project_dir.name}/{proyecto_path.name}"
                    if proyecto_path else f"../../🚀proyectos/{project_dir.name}")
        lines.append(f"### [{project_dir.name}]({rel_path})")

        for note in notes:
            # Extract date from YYYYMMDD_ prefix if present
            m = re.match(r"^(\d{4})(\d{2})(\d{2})_(.+)\.md$", note.name)
            if m:
                date_str  = f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
                title_str = m.group(4).replace("-", " ")
            else:
                date_str  = ""
                title_str = note.stem.replace("-", " ")
            note_link = f"[{title_str}](file://{note.resolve()})"
            suffix    = f"  — {date_str}" if date_str else ""
            lines.append(f"  📝 {note_link}{suffix}")

        lines.append("")

    if not found:
        print("No hay notas en ningún proyecto.")
        return 0

    _write_output("\n".join(lines), output, open_after, editor,
                  MISION_LOG_DIR / "notes.md")
    return 0


# ── list files ──────────────────────────────────────────────────────────────

def run_list_files(project: Optional[str], output: Optional[str],
                   open_after: bool, editor: str) -> int:
    """List artifact files inside a project (or all projects), marking orphans."""
    if not PROJECTS_DIR.exists():
        print("Error: directorio de proyectos no encontrado")
        return 1

    lines = ["FICHEROS DE PROYECTO", "═" * 40, ""]
    found = False

    for project_dir in sorted(PROJECTS_DIR.iterdir()):
        if not project_dir.is_dir():
            continue
        if project and project.lower() not in project_dir.name.lower():
            continue
        proyecto_path = find_proyecto_file(project_dir)
        if not proyecto_path or not proyecto_path.exists():
            continue

        # Collect all relative paths linked from proyecto.md
        text   = proyecto_path.read_text()
        linked = set(re.findall(r'\]\(\./([^)]+)\)', text))

        dir_lines = []
        for dir_name in _FILE_DIRS:
            dir_path = project_dir / dir_name
            if not dir_path.exists():
                continue
            files = sorted(f for f in dir_path.iterdir()
                           if f.is_file() and not f.name.startswith("."))
            if not files:
                continue
            emoji = _DIR_EMOJI[dir_name]
            for f in files:
                rel        = f"{dir_name}/{f.name}"
                orphan     = " ⚠️ sin enlace" if rel not in linked else ""
                file_link  = f"[{f.name}](file://{f.resolve()})"
                dir_lines.append(f"  {emoji} {file_link}{orphan}")

        if dir_lines:
            found = True
            rel_path = f"../../🚀proyectos/{project_dir.name}/{proyecto_path.name}"
            lines.append(f"### [{project_dir.name}]({rel_path})")
            lines.extend(dir_lines)
            lines.append("")

    if not found:
        print("No hay ficheros en ningún proyecto.")
        return 0

    _write_output("\n".join(lines), output, open_after, editor,
                  MISION_LOG_DIR / "files.md")
    return 0

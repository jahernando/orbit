"""orbit list — list projects and project sections."""

from pathlib import Path
from typing import Optional

from core.log import PROJECTS_DIR, find_proyecto_file
from core.tasks import load_project_meta, normalize
from core.open import open_file

MISION_LOG_DIR = Path(__file__).parent.parent / "☀️mision-log"

SECTION_HEADINGS = {
    "rings":     "## ⏰ Recordatorios",
    "refs":      "## 📎 Referencias",
    "results":   "## 📊 Resultados",
    "decisions": "## 📌 Decisiones",
}


def _extract_section(proyecto_path: Path, heading: str) -> list:
    """Return non-empty, non-placeholder lines from a section."""
    lines      = proyecto_path.read_text().splitlines()
    in_section = False
    items      = []
    for line in lines:
        if line.strip() == heading:
            in_section = True
            continue
        if in_section:
            if line.startswith("## "):
                break
            stripped = line.strip()
            if stripped and stripped != "-" and not stripped.startswith("<!--"):
                items.append(stripped)
    return items


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
                     output: Optional[str], open_after: bool, editor: str) -> int:
    heading = SECTION_HEADINGS.get(section)
    if not heading:
        print(f"Error: sección desconocida '{section}'")
        return 1
    if not PROJECTS_DIR.exists():
        print("Error: directorio de proyectos no encontrado")
        return 1

    title = heading.lstrip("# ").strip()
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
        items = _extract_section(proyecto_path, heading)
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

"""views/secretary/projects.py — lista de proyectos del workspace.

Genera un markdown con una tabla por tipo de proyecto, cada tabla con
columnas: Proyecto · Prio · Estado · Descripción · Secciones. La
descripción se lee de la sección `## Estado actual` del {proj}-project.md.

Viewer puro: lee la verdad (los proyectos), escribe el .md, return.
Análogo al estilo de tablas de panel pero al nivel de workspace.
"""

import re
from pathlib import Path

from core.config import ORBIT_HOME, iter_project_dirs


_STATUS_EMOJI = {
    "new":      "⬜",
    "active":   "▶️",
    "paused":   "⏸️",
    "sleeping": "💤",
}

_DESC_MAX_CHARS = 70


def _read_project_description(project_file: Path) -> str:
    """Extrae la primera línea no-vacía de `## Estado actual` o `## Descripción`.

    Si lo único es el placeholder italic (`*Descripción breve...*`) o no
    hay sección, devuelve "". Trunca a _DESC_MAX_CHARS con elipsis.
    """
    if not project_file or not project_file.exists():
        return ""
    text = project_file.read_text()
    # Buscar sección "## Estado actual" o "## Descripción" (case-insensitive).
    pattern = re.compile(
        r"^## +(?:Estado actual|Descripción|Descripcion)\s*$",
        re.IGNORECASE | re.MULTILINE,
    )
    m = pattern.search(text)
    if not m:
        return ""
    body = text[m.end():]
    # Cortar al siguiente "## " o "---" o "[link inline]".
    end_match = re.search(r"^(?:##\s|---\s*$|\[[^\]]+\]\([^\)]+\))",
                          body, re.MULTILINE)
    if end_match:
        body = body[:end_match.start()]

    for raw in body.splitlines():
        line = raw.strip()
        if not line:
            continue
        # Strip envolvente italic *...*.
        while line.startswith("*") and line.endswith("*") and len(line) > 2:
            line = line[1:-1].strip()
        # Saltar placeholder.
        if "descripción breve" in line.lower() or "descripcion breve" in line.lower():
            continue
        # Asterisco residual (línea italic que se cortaría tras truncar).
        if line.startswith("*"):
            line = line[1:].lstrip()
        line = re.sub(r"\s+", " ", line)
        if len(line) > _DESC_MAX_CHARS:
            line = line[:_DESC_MAX_CHARS - 1].rstrip() + "…"
        # Escapar pipe para que no rompa la tabla.
        return line.replace("|", "\\|")
    return ""


def _md_escape(text: str) -> str:
    """Escape pipe character that breaks markdown tables."""
    return text.replace("|", "\\|")


def generate(out_path: Path) -> None:
    """Escribe la tabla de proyectos del workspace en out_path.

    Los links son relativos a out_path (que vive en `📋secretary/`), por
    lo que suben un nivel con `../` para alcanzar los directorios de
    proyecto en la raíz del workspace.
    """
    from core.project import _is_new_project, _read_project_meta, _resolve_status
    from core.log import find_proyecto_file, resolve_file
    from core.tasks import PRIORITY_MAP, normalize

    lines = ["# 📂 Proyectos\n"]

    out_dir = out_path.parent
    try:
        prefix = Path("..") / out_dir.relative_to(ORBIT_HOME).parent
    except ValueError:
        prefix = Path("..")

    type_groups: dict = {}
    for project_dir in iter_project_dirs():
        if not _is_new_project(project_dir):
            continue
        rel = project_dir.relative_to(ORBIT_HOME)
        type_dir = rel.parts[0]
        type_groups.setdefault(type_dir, [])

        meta = _read_project_meta(project_dir)
        status, _, _ = _resolve_status(meta, project_dir)
        project_file = find_proyecto_file(project_dir)

        if project_file:
            link = f"{prefix}/{type_dir}/{project_dir.name}/{project_file.name}"
            desc = _read_project_description(project_file)
        else:
            link = f"{prefix}/{type_dir}/{project_dir.name}/"
            desc = ""

        section_links = []
        for kind, label in [("agenda", "📅"), ("logbook", "📓"),
                            ("highlights", "⭐")]:
            f = resolve_file(project_dir, kind)
            if f.exists():
                section_links.append(
                    f"[{label}]({prefix}/{type_dir}/{project_dir.name}/{f.name})"
                )

        prio_key = normalize(meta["prioridad"])
        prio_emoji = PRIORITY_MAP.get(prio_key, "")
        status_emoji = _STATUS_EMOJI.get(status, "❓")

        type_groups[type_dir].append({
            "name":     project_dir.name,
            "link":     link,
            "status":   status_emoji,
            "prio":     prio_emoji,
            "desc":     desc,
            "sections": " ".join(section_links),
        })

    for type_dir, projects in sorted(type_groups.items()):
        lines.append(f"\n## {type_dir}\n")
        lines.append("| Proyecto | Prio | Estado | Descripción | Secciones |")
        lines.append("|---|:---:|:---:|---|---|")
        for p in sorted(projects, key=lambda x: x["name"]):
            lines.append(
                f"| [{_md_escape(p['name'])}]({p['link']}) "
                f"| {p['prio']} | {p['status']} "
                f"| {p['desc']} | {p['sections']} |"
            )

    out_path.write_text("\n".join(lines) + "\n")

"""views/secretary/projects.py — lista de proyectos del workspace.

Genera un markdown con todos los proyectos agrupados por tipo, con
icono de estado (active/paused/sleeping) + prioridad + links a las
piezas del proyecto (project.md, logbook, agenda, highlights).

Viewer puro: lee la verdad (los proyectos), escribe el .md, return.
Análogo a `views/render/render.py::render_proyectos` pero output
markdown (no HTML) y links relativos al workspace (no a cloud_root).
"""

from pathlib import Path

from core.config import ORBIT_HOME, iter_project_dirs


_STATUS_EMOJI = {
    "new":      "⬜",
    "active":   "▶️",
    "paused":   "⏸️",
    "sleeping": "💤",
}


def generate(out_path: Path) -> None:
    """Escribe la lista de proyectos del workspace en out_path.

    Los links son relativos a out_path (que vive en `📋secretary/`), por
    lo que suben un nivel con `../` para alcanzar los directorios de
    proyecto en la raíz del workspace.
    """
    from core.project import _is_new_project, _read_project_meta, _resolve_status
    from core.log import find_proyecto_file, resolve_file
    from core.tasks import PRIORITY_MAP, normalize

    lines = ["# 📂 Proyectos\n"]

    # Relative prefix: out_path lives in <ws>/📋secretary/, projects in <ws>/<type>/<proj>/.
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
        else:
            link = f"{prefix}/{type_dir}/{project_dir.name}/"

        sections = []
        for kind, label in [("agenda", "📅"), ("logbook", "📓"),
                            ("highlights", "⭐")]:
            f = resolve_file(project_dir, kind)
            if f.exists():
                sections.append(
                    f"[{label}]({prefix}/{type_dir}/{project_dir.name}/{f.name})"
                )

        prio_key = normalize(meta["prioridad"])
        prio_emoji = PRIORITY_MAP.get(prio_key, "")
        status_emoji = _STATUS_EMOJI.get(status, "❓")

        type_groups[type_dir].append({
            "name": project_dir.name,
            "link": link,
            "status_emoji": status_emoji,
            "prio_emoji": prio_emoji,
            "sections": " ".join(sections),
        })

    for type_dir, projects in sorted(type_groups.items()):
        lines.append(f"\n## {type_dir}\n")
        for p in sorted(projects, key=lambda x: x["name"]):
            lines.append(
                f"- [{p['name']}]({p['link']})  "
                f"{p['status_emoji']} {p['prio_emoji']}  {p['sections']}"
            )

    out_path.write_text("\n".join(lines) + "\n")

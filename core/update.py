"""orbit update — set status and/or priority on one or more projects."""

from pathlib import Path
from typing import Optional

from core.log import PROJECTS_DIR, find_project, find_proyecto_file
from core.tasks import STATUS_MAP, PRIORITY_MAP, normalize, update_proyecto_field, load_project_meta

STATUS_LABEL = {
    "inicial":    "Inicial",
    "en marcha":  "En marcha",
    "parado":     "Parado",
    "esperando":  "Esperando",
    "durmiendo":  "Durmiendo",
    "completado": "Completado",
}

PRIORITY_LABEL = {
    "alta":  "Alta",
    "media": "Media",
    "baja":  "Baja",
}


def run_update(
    projects: list,
    status: Optional[str],
    priority: Optional[str],
    tipo: Optional[str],
    from_status: Optional[str],
    from_priority: Optional[str],
) -> int:
    if not status and not priority:
        print("Error: indica al menos --status o --priority")
        return 1

    # Validate new values upfront
    status_key = priority_key = None
    if status:
        status_key = normalize(status)
        if status_key not in STATUS_MAP:
            print(f"Error: estado '{status}' no válido. Opciones: {', '.join(STATUS_MAP)}")
            return 1
    if priority:
        priority_key = normalize(priority)
        if priority_key not in PRIORITY_MAP:
            print(f"Error: prioridad '{priority}' no válida. Opciones: alta, media, baja")
            return 1

    # Collect candidate project dirs
    if projects:
        candidates = []
        for p in projects:
            d = find_project(p)
            if d:
                candidates.append(d)
        if not candidates:
            return 1
    else:
        if not tipo and not from_status and not from_priority:
            print("Error: especifica al menos un proyecto o un filtro (--type, --from-status, --from-priority)")
            return 1
        candidates = sorted([d for d in PROJECTS_DIR.iterdir() if d.is_dir()])

    errors = 0
    changed = 0

    for project_dir in candidates:
        proyecto_path = find_proyecto_file(project_dir)
        if not proyecto_path or not proyecto_path.exists():
            continue

        # Apply filters (only when no explicit projects given)
        if not projects:
            meta = load_project_meta(proyecto_path)
            if tipo and normalize(tipo) not in meta["tipo_raw"]:
                continue
            if from_status and normalize(from_status) not in meta["estado_raw"]:
                continue
            if from_priority and normalize(from_priority) not in meta["prioridad_raw"]:
                continue

        parts = []
        if status_key:
            emoji = STATUS_MAP[status_key]
            label = STATUS_LABEL[status_key]
            update_proyecto_field(proyecto_path, "estado", f"{emoji} {label}")
            parts.append(f"estado → {emoji} {label}")
        if priority_key:
            emoji = PRIORITY_MAP[priority_key]
            label = PRIORITY_LABEL[priority_key]
            update_proyecto_field(proyecto_path, "prioridad", f"{emoji} {label}")
            parts.append(f"prioridad → {emoji} {label}")

        print(f"✓ {project_dir.name}  {' · '.join(parts)}")
        changed += 1

    if changed == 0:
        print("No se encontraron proyectos con los filtros indicados.")
    return 0 if not errors else 1

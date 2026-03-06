"""orbit update — set status and/or priority of a project."""

import re
from typing import Optional

from core.log import find_project, find_proyecto_file
from core.tasks import STATUS_MAP, PRIORITY_MAP, normalize

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


def run_update(project: str, status: Optional[str], priority: Optional[str]) -> int:
    if not status and not priority:
        print("Error: indica al menos --status o --priority")
        return 1

    project_dir = find_project(project)
    if not project_dir:
        return 1

    proyecto_path = find_proyecto_file(project_dir)
    if not proyecto_path or not proyecto_path.exists():
        print(f"Error: no se encontró el archivo de proyecto en {project_dir.name}")
        return 1

    md = proyecto_path.read_text()

    if status:
        key = normalize(status)
        if key not in STATUS_MAP:
            valid = ", ".join(STATUS_MAP.keys())
            print(f"Error: estado '{status}' no válido. Opciones: {valid}")
            return 1
        emoji = STATUS_MAP[key]
        label = STATUS_LABEL[key]
        md = re.sub(
            r"(## 🔄 Estado\n).*",
            rf"\1{emoji} {label}",
            md,
        )
        print(f"✓ Estado → {emoji} {label}")

    if priority:
        key = normalize(priority)
        if key not in PRIORITY_MAP:
            valid = ", ".join(PRIORITY_MAP.keys())
            print(f"Error: prioridad '{priority}' no válida. Opciones: {valid}")
            return 1
        emoji = PRIORITY_MAP[key]
        label = PRIORITY_LABEL[key]
        md = re.sub(
            r"(## ⭐ Prioridad\n).*",
            rf"\1{emoji} {label}",
            md,
        )
        print(f"✓ Prioridad → {emoji} {label}")

    proyecto_path.write_text(md)
    print(f"  [{project_dir.name}] {proyecto_path.name}")
    return 0

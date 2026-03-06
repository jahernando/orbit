from datetime import date
from pathlib import Path
from typing import Optional

from core.log import PROJECTS_DIR
from core.tasks import TYPE_MAP, PRIORITY_MAP, normalize

TEMPLATES_DIR = Path(__file__).parent.parent / "📐templates"

TYPE_LABEL = {
    "investigacion": "Investigación",
    "investigación": "Investigación",
    "docencia":      "Docencia",
    "gestion":       "Gestión",
    "gestión":       "Gestión",
    "formacion":     "Formación",
    "formación":     "Formación",
    "software":      "Software",
    "personal":      "Personal",
}


def run_project(name: str, tipo: str, prioridad: str) -> int:
    tipo_key = normalize(tipo)
    if tipo_key not in TYPE_MAP:
        valid = ", ".join(k for k in TYPE_MAP if not k.endswith("ón"))  # skip accented duplicates
        print(f"Error: tipo '{tipo}' no válido. Opciones: {valid}")
        return 1

    prio_key = normalize(prioridad)
    if prio_key not in PRIORITY_MAP:
        print(f"Error: prioridad '{prioridad}' no válida. Opciones: alta, media, baja")
        return 1

    tipo_emoji  = TYPE_MAP[tipo_key]
    tipo_label  = TYPE_LABEL.get(tipo_key, tipo.capitalize())
    prio_emoji  = PRIORITY_MAP[prio_key]
    prio_label  = prio_key.capitalize()

    dir_name    = f"{tipo_emoji}-{name.lower()}"
    project_dir = PROJECTS_DIR / dir_name

    if project_dir.exists():
        print(f"Error: ya existe el proyecto en {project_dir}")
        return 1

    tpl_proyecto = TEMPLATES_DIR / "proyecto.md"
    tpl_logbook  = TEMPLATES_DIR / "logbook.md"
    if not tpl_proyecto.exists() or not tpl_logbook.exists():
        print(f"Error: plantillas no encontradas en {TEMPLATES_DIR}")
        return 1

    project_dir.mkdir(parents=True)

    logbook_filename = f"📓{name}.md"

    # {tipo_emoji}{name}.md — project index
    proyecto_content = (
        tpl_proyecto.read_text()
        .replace("# [Nombre del proyecto]", f"# {dir_name}")
        .replace(
            "🌀 Investigación / 📚 Docencia / ⚙️ Gestión / 📖 Formación / 💻 Software / 🌿 Personal",
            f"{tipo_emoji} {tipo_label}"
        )
        .replace(
            "⬜ Inicial / ▶️ En marcha / ⏸️ Parado / ⏳ Esperando / 💤 Durmiendo / ✅ Completado",
            "⬜ Inicial"
        )
        .replace(
            "🟠 Alta / 🟡 Media / 🔵 Baja",
            f"{prio_emoji} {prio_label}"
        )
        .replace("./logbook.md", f"./{logbook_filename}")
    )
    proyecto_file = project_dir / f"{tipo_emoji}{name}.md"
    proyecto_file.write_text(proyecto_content)

    # 📓{name}.md — logbook
    logbook_content = (
        tpl_logbook.read_text()
        .replace("# Logbook — [Nombre del proyecto]", f"# Logbook — {dir_name}")
        .replace("## YYYY-MM-DD\n\nYYYY-MM-DD Primera entrada. #apunte", "")
        .replace("YYYY-MM-DD", date.today().isoformat())
    )
    logbook_file = project_dir / logbook_filename
    logbook_file.write_text(logbook_content)

    print(f"✓ Proyecto creado: {project_dir}")
    print(f"  {proyecto_file}")
    print(f"  {logbook_file}")
    return 0

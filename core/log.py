from datetime import date
from pathlib import Path
from typing import Optional

PROJECTS_DIR = Path(__file__).parent.parent / "🚀proyectos"

VALID_TYPES = ["idea", "referencia", "tarea", "problema", "resultado", "apunte", "decision"]


def find_project(name: str) -> Optional[Path]:
    if not PROJECTS_DIR.exists():
        print(f"Error: projects directory not found at {PROJECTS_DIR}")
        return None

    matches = [d for d in PROJECTS_DIR.iterdir() if d.is_dir() and name.lower() in d.name.lower()]

    if not matches:
        print(f"Error: no project found matching '{name}'")
        return None

    if len(matches) > 1:
        print(f"Ambiguous name '{name}'. Did you mean:")
        for m in sorted(matches):
            print(f"  {m.name}")
        return None

    return matches[0]


def format_entry(message: str, tipo: str, path: Optional[str], fecha: Optional[str]) -> str:
    date_str = fecha or date.today().isoformat()
    content = f"[{message}]({path})" if path else message
    return f"{date_str} {content} #{tipo}\n"


def init_logbook(logbook_path: Path, project_name: str) -> None:
    logbook_path.write_text(
        f"# Logbook — {project_name}\n\n"
        "<!-- Tipos: #idea #referencia #tarea #problema #resultado #apunte #decision -->\n\n"
    )


def add_entry(project: str, message: str, tipo: str, path: Optional[str], fecha: Optional[str]) -> int:
    project_dir = find_project(project)
    if not project_dir:
        return 1

    logbook_path = project_dir / "logbook.md"

    if not logbook_path.exists():
        init_logbook(logbook_path, project_dir.name)

    entry = format_entry(message, tipo, path, fecha)

    with open(logbook_path, "a") as f:
        f.write(entry)

    print(f"✓ [{project_dir.name}] {entry.strip()}")
    return 0

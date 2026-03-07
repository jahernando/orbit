from datetime import date
from pathlib import Path
from typing import Optional

PROJECTS_DIR = Path(__file__).parent.parent / "🚀proyectos"

VALID_TYPES = ["idea", "referencia", "tarea", "problema", "resultado", "apunte", "decision", "evento"]


def find_proyecto_file(project_dir: Path) -> Optional[Path]:
    """Find the project index file: proyecto.md (legacy) or {emoji}{name}.md."""
    legacy = project_dir / "proyecto.md"
    if legacy.exists():
        return legacy
    candidates = [f for f in project_dir.glob("*.md") if not f.name.startswith("📓")]
    return candidates[0] if len(candidates) == 1 else None


def find_logbook_file(project_dir: Path) -> Optional[Path]:
    """Find the logbook file: logbook.md (legacy) or 📓{name}.md."""
    legacy = project_dir / "logbook.md"
    if legacy.exists():
        return legacy
    candidates = list(project_dir.glob("📓*.md"))
    return candidates[0] if candidates else None


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


TAG_EMOJI = {
    "idea":       "💡",
    "referencia": "📎",
    "tarea":      "✅",
    "problema":   "⚠️",
    "resultado":  "📊",
    "apunte":     "📝",
    "decision":   "📌",
    "evento":     "📅",
}


def format_entry(message: str, tipo: str, path: Optional[str], fecha: Optional[str]) -> str:
    date_str = fecha or date.today().isoformat()
    content  = f"[{message}]({path})" if path else message
    emoji    = TAG_EMOJI.get(tipo, "")
    return f"{date_str} {emoji} {content} #{tipo}\n"


def _append_entry(logbook_path: Path, entry: str) -> None:
    """Append an entry ensuring a blank line separator for markdown readability."""
    existing = logbook_path.read_text() if logbook_path.exists() else ""
    with open(logbook_path, "a") as f:
        if existing and not existing.endswith("\n\n"):
            f.write("" if existing.endswith("\n") else "\n")
            f.write("\n")
        f.write(entry)


def init_logbook(logbook_path: Path, project_name: str) -> None:
    logbook_path.write_text(
        f"# Logbook — {project_name}\n\n"
        "<!-- Tipos: #idea #referencia #tarea #problema #resultado #apunte #decision -->\n\n"
    )


def add_entry(project: str, message: str, tipo: str, path: Optional[str], fecha: Optional[str]) -> int:
    if fecha:
        try:
            entry_date = date.fromisoformat(fecha)
        except ValueError:
            print(f"Error: fecha '{fecha}' no es válida. Usa formato YYYY-MM-DD")
            return 1
        if entry_date > date.today():
            print(f"Error: la fecha {fecha} es futura. Las entradas deben ser de hoy o anteriores")
            return 1

    project_dir = find_project(project)
    if not project_dir:
        return 1

    logbook_path = find_logbook_file(project_dir)
    if not logbook_path:
        logbook_path = project_dir / "logbook.md"

    if not logbook_path.exists():
        init_logbook(logbook_path, project_dir.name)

    entry = format_entry(message, tipo, path, fecha)
    _append_entry(logbook_path, entry)

    print(f"✓ [{project_dir.name}] {entry.strip()}")
    return 0

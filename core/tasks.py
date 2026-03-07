import unicodedata
from datetime import date
from pathlib import Path
from typing import Optional

from core.log import PROJECTS_DIR, find_proyecto_file


def normalize(text: str) -> str:
    return unicodedata.normalize("NFD", text).encode("ascii", "ignore").decode().lower()

STATUS_MAP = {
    "inicial":    "⬜",
    "en marcha":  "▶️",
    "parado":     "⏸️",
    "esperando":  "⏳",
    "durmiendo":  "💤",
    "completado": "✅",
}

PRIORITY_MAP = {
    "alta":  "🟠",
    "media": "🟡",
    "baja":  "🔵",
}

TYPE_MAP = {
    "investigación": "🌀",
    "investigacion": "🌀",
    "docencia":      "📚",
    "gestión":       "⚙️",
    "gestion":       "⚙️",
    "formación":     "📖",
    "formacion":     "📖",
    "software":      "💻",
    "personal":      "🌿",
}


def read_proyecto_field(lines: list, field: str) -> Optional[str]:
    """Read the value on the line after a ## field heading."""
    for i, line in enumerate(lines):
        if line.strip().lower().startswith(f"## ") and field in line.lower():
            if i + 1 < len(lines):
                return lines[i + 1].strip()
    return None


def _extract_date_from_parens(content: str):
    """Extract (YYYY-MM-DD) from end of string. Returns (content_without_date, date_str or None)."""
    if content.endswith(")") and "(" in content:
        paren_start = content.rfind("(")
        candidate = content[paren_start + 1:-1]
        if len(candidate) == 10 and candidate[4] == "-" and candidate[7] == "-":
            return content[:paren_start].strip(), candidate
    return content, None


def parse_task(line: str) -> Optional[dict]:
    """Parse a pending or completed task line."""
    stripped = line.strip()
    if stripped.startswith("- [x]") or stripped.startswith("- [X]"):
        content = stripped[5:].strip()
        content, completed = _extract_date_from_parens(content)
        return {"description": content, "due": None, "done": True, "completed": completed}
    if not stripped.startswith("- [ ]"):
        return None
    content = stripped[5:].strip()
    content, due = _extract_date_from_parens(content)
    return {"description": content, "due": due, "done": False, "completed": None}


def is_overdue(due: str, today: date) -> bool:
    try:
        return date.fromisoformat(due) < today
    except ValueError:
        return False


def matches_fecha(due: Optional[str], fecha: Optional[str]) -> bool:
    if not fecha:
        return True
    if not due:
        return False
    return due.startswith(fecha)


def load_project_meta(proyecto_path: Path) -> dict:
    lines = proyecto_path.read_text().splitlines()
    tipo_raw = normalize(read_proyecto_field(lines, "tipo") or "")
    estado_raw = normalize(read_proyecto_field(lines, "estado") or "")
    prioridad_raw = normalize(read_proyecto_field(lines, "prioridad") or "")

    # Match against known values (line may contain multiple options separated by /)
    tipo = next((TYPE_MAP[k] for k in TYPE_MAP if k in tipo_raw), "")
    estado = next((STATUS_MAP[k] for k in STATUS_MAP if k in estado_raw), "")
    prioridad = next((PRIORITY_MAP[k] for k in PRIORITY_MAP if k in prioridad_raw), "")

    tasks = []
    in_tasks = False
    for line in lines:
        if line.strip().lower().startswith("## ") and "tarea" in line.lower():
            in_tasks = True
            continue
        if in_tasks:
            if line.startswith("## "):
                break
            task = parse_task(line)
            if task:
                tasks.append(task)

    return {
        "tipo": tipo,
        "estado": estado,
        "prioridad": prioridad,
        "estado_raw": estado_raw,
        "prioridad_raw": prioridad_raw,
        "tipo_raw": tipo_raw,
        "tasks": tasks,
    }


def list_tasks(
    project: Optional[str],
    tipo: Optional[str],
    estado: Optional[str],
    prioridad: Optional[str],
    fecha: Optional[str],  # kept as internal name for date filtering
    output: Optional[str],
) -> int:
    if not PROJECTS_DIR.exists():
        print(f"Error: projects directory not found at {PROJECTS_DIR}")
        return 1

    today = date.today()
    lines_out = [f"TAREAS PENDIENTES — {today.isoformat()}", "=" * 42, ""]

    project_dirs = sorted([d for d in PROJECTS_DIR.iterdir() if d.is_dir()])

    found_any = False

    for project_dir in project_dirs:
        # Filter by project name
        if project and project.lower() not in project_dir.name.lower():
            continue

        proyecto_path = find_proyecto_file(project_dir)
        if not proyecto_path or not proyecto_path.exists():
            continue

        meta = load_project_meta(proyecto_path)

        # Filter by tipo
        if tipo and normalize(tipo) not in meta["tipo_raw"]:
            continue

        # Filter by estado
        if estado and normalize(estado) not in meta["estado_raw"]:
            continue

        # Filter by prioridad
        if prioridad and normalize(prioridad) not in meta["prioridad_raw"]:
            continue

        # Only pending tasks
        tasks = [t for t in meta["tasks"] if not t.get("done")]
        if fecha:
            tasks = [t for t in tasks if matches_fecha(t["due"], fecha)]

        if not tasks:
            continue

        found_any = True

        # Project header — project name as a link to proyecto.md#tareas
        project_link = f"[{project_dir.name}](file://{proyecto_path.resolve()}#tareas)"
        header = f"{project_link}  {meta['tipo']} {meta['estado']}  {meta['prioridad']}"
        lines_out.append(header)

        # Sort: overdue first, then by date, then no date
        def sort_key(t):
            if t["due"] is None:
                return (2, "")
            if is_overdue(t["due"], today):
                return (0, t["due"])
            return (1, t["due"])

        for task in sorted(tasks, key=sort_key):
            if task["due"] and is_overdue(task["due"], today):
                marker = "⚠️ "
                due_str = task["due"]
            elif task["due"]:
                marker = "[ ]"
                due_str = task["due"]
            else:
                marker = "[ ]"
                due_str = "—"
            lines_out.append(f"  {marker}  {due_str}  {task['description']}")

        lines_out.append("")

    if not found_any:
        lines_out.append("No se encontraron tareas con los filtros indicados.")

    text = "\n".join(lines_out)

    if output:
        Path(output).write_text(text + "\n")
        print(f"✓ Saved to {output}")
    else:
        print(text)

    return 0

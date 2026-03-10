import re
from datetime import date
from pathlib import Path
from typing import Optional

from core.log import PROJECTS_DIR, find_proyecto_file
from core.open import open_file
from core.config import normalize

STATUS_MAP = {
    "inicial":    "⬜",
    "en marcha":  "▶️",
    "parado":     "⏸️",
    "durmiendo":  "💤",
    "completado": "✅",
}

PRIORITY_MAP = {
    "alta":  "🔴",
    "media": "🔶",
    "baja":  "🔹",
}

from core.config import get_type_map, get_type_emojis

TYPE_MAP = get_type_map()


def read_proyecto_field(lines: list, field: str) -> Optional[str]:
    """Read the value on the line after a ## field heading (legacy format)."""
    for i, line in enumerate(lines):
        if line.strip().lower().startswith("## ") and field in line.lower():
            if i + 1 < len(lines):
                return lines[i + 1].strip()
    return None


_TYPE_EMOJIS     = get_type_emojis()
_STATUS_EMOJIS   = ("⬜", "▶️", "⏸️", "💤", "✅")
_PRIORITY_EMOJIS = ("🔴", "🔶", "🔹")


def update_proyecto_field(proyecto_path: Path, field: str, new_value: str) -> None:
    """Update a field in proyecto.md — supports both old (## heading) and new (emoji line) formats."""
    lines = proyecto_path.read_text().splitlines()

    # Old format: ## heading + next line
    for i, line in enumerate(lines):
        if line.strip().lower().startswith("## ") and field in normalize(line):
            if i + 1 < len(lines):
                lines[i + 1] = new_value
                proyecto_path.write_text("\n".join(lines) + "\n")
                return

    # New format: find line starting with known emoji for this field
    emojis = {"estado": _STATUS_EMOJIS, "prioridad": _PRIORITY_EMOJIS, "tipo": _TYPE_EMOJIS}.get(field)
    if not emojis:
        return
    for i, line in enumerate(lines):
        if any(line.strip().startswith(e) for e in emojis):
            lines[i] = new_value
            proyecto_path.write_text("\n".join(lines) + "\n")
            return


def _read_compact_meta(lines: list) -> tuple:
    """Read tipo/estado/prioridad from compact emoji lines (new format)."""
    tipo = estado = prioridad = None
    scanned = 0
    for line in lines:
        s = line.strip()
        if not s or s.startswith("# "):
            continue
        if s.startswith("## "):
            break
        scanned += 1
        if scanned > 15:
            break
        if any(s.startswith(e) for e in _TYPE_EMOJIS):
            tipo = s
        elif any(s.startswith(e) for e in _STATUS_EMOJIS):
            estado = s
        elif any(s.startswith(e) for e in _PRIORITY_EMOJIS):
            prioridad = s
    return tipo, estado, prioridad


_RE_TRAILING_TAGS = re.compile(r'(\s+@\S+)+\s*$')


def parse_tags(content: str):
    """Strip trailing @tags. Returns (clean_content, has_ring, recur_or_None)."""
    all_tags = re.findall(r'@\S+', content)
    clean = _RE_TRAILING_TAGS.sub('', content).strip() if all_tags else content
    ring  = '@ring' in all_tags
    recur = next((t for t in all_tags if t != '@ring'), None)
    return clean, ring, recur


def _split_due(due_full):
    """Split 'YYYY-MM-DD HH:MM' into (date, time) or (date, None)."""
    if not due_full:
        return None, None
    parts = due_full.split(' ', 1)
    return parts[0], (parts[1] if len(parts) > 1 else None)


def _extract_date_from_parens(content: str):
    """Extract (YYYY-MM-DD) or (YYYY-MM-DD HH:MM) from end of string.
    Returns (content_without_date, date_or_datetime_str or None)."""
    if content.endswith(")") and "(" in content:
        paren_start = content.rfind("(")
        candidate = content[paren_start + 1:-1]
        # YYYY-MM-DD
        if len(candidate) == 10 and candidate[4] == "-" and candidate[7] == "-":
            return content[:paren_start].strip(), candidate
        # YYYY-MM-DD HH:MM
        if (len(candidate) == 16 and candidate[4] == "-" and candidate[7] == "-"
                and candidate[10] == " " and candidate[13] == ":"):
            return content[:paren_start].strip(), candidate
    return content, None


def parse_task(line: str) -> Optional[dict]:
    """Parse a pending, scheduled or completed task line."""
    stripped = line.strip()

    if stripped.startswith("- [x]") or stripped.startswith("- [X]"):
        content = stripped[5:].strip()
        content, ring, _ = parse_tags(content)
        content, completed = _extract_date_from_parens(content)
        return {"description": content, "due": None, "time": None, "done": True,
                "completed": completed, "ring": ring, "recur": None}

    # [~] = ring already scheduled in Reminders.app — treat as pending
    if stripped.startswith("- [~]"):
        content = stripped[5:].strip()
        content, _, recur = parse_tags(content)
        content, due_full = _extract_date_from_parens(content)
        due, time = _split_due(due_full)
        return {"description": content, "due": due, "time": time, "done": False,
                "completed": None, "ring": True, "recur": recur, "scheduled": True}

    if not stripped.startswith("- [ ]"):
        return None

    content = stripped[5:].strip()
    content, ring, recur = parse_tags(content)
    content, due_full = _extract_date_from_parens(content)
    due, time = _split_due(due_full)
    return {"description": content, "due": due, "time": time, "done": False,
            "completed": None, "ring": ring, "recur": recur}


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
    tipo_raw     = normalize(read_proyecto_field(lines, "tipo") or "")
    estado_raw   = normalize(read_proyecto_field(lines, "estado") or "")
    prioridad_raw = normalize(read_proyecto_field(lines, "prioridad") or "")

    # Fallback: compact emoji format (new projects)
    if not tipo_raw and not estado_raw and not prioridad_raw:
        t, e, p = _read_compact_meta(lines)
        tipo_raw      = normalize(t or "")
        estado_raw    = normalize(e or "")
        prioridad_raw = normalize(p or "")

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
    fecha: Optional[str],
    keyword: Optional[str],
    output: Optional[str],
    ring_only: bool = False,
    open_after: bool = False,
    editor: str = "",
) -> int:
    if not PROJECTS_DIR.exists():
        print(f"Error: projects directory not found at {PROJECTS_DIR}")
        return 1

    today = date.today()
    header = f"{'RECORDATORIOS' if ring_only else 'TAREAS PENDIENTES'} — {today.isoformat()}"
    lines_out = [header, "=" * 42, ""]

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
        if ring_only:
            tasks = [t for t in tasks if t.get("ring")]
        if fecha:
            tasks = [t for t in tasks if matches_fecha(t["due"], fecha)]
        if keyword:
            kws = keyword.lower().split()
            tasks = [t for t in tasks if all(kw in t["description"].lower() for kw in kws)]

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
            time_suffix = f" {task['time']}" if task.get("time") else ""
            if task["due"] and is_overdue(task["due"], today):
                marker = "⚠️ "
                due_str = task["due"] + time_suffix
            elif task["due"]:
                marker = "⏰ " if task.get("ring") else "[ ]"
                due_str = task["due"] + time_suffix
            else:
                marker = "[ ]"
                due_str = "—"
            lines_out.append(f"  {marker}  {due_str}  {task['description']}")

        lines_out.append("")

    if not found_any:
        lines_out.append("No se encontraron tareas con los filtros indicados.")

    text = "\n".join(lines_out)

    if output:
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

    return 0

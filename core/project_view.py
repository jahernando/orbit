"""project_view.py — terminal summary and file-open for new-format projects.

  view [<project>]                            # terminal summary or project picker
  view <project> --open                       # same as markdown, open in editor
  open <project> [logbook|highlights|agenda|notes|project]
"""
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

from core.project import (
    _find_new_project, _is_new_project, _read_project_meta, _resolve_status,
)
from core.config import iter_project_dirs
from core.agenda_cmds import _read_agenda
from core.highlights import _read_highlights, SECTION_MAP
from core.log import find_logbook_file, resolve_file
from core.open import open_file

_WIDTH = 54   # summary box width

# ── Logbook helpers ────────────────────────────────────────────────────────────

def _recent_logbook_entries(project_dir: Path, n: int = 5) -> list:
    """Return the last *n* logbook entries (with continuation lines joined)."""
    logbook = find_logbook_file(project_dir)
    if not logbook or not logbook.exists():
        return []
    entries = []
    for line in logbook.read_text().splitlines():
        s = line.strip()
        if not s or s.startswith("#") or s.startswith("<!--"):
            continue
        if line.startswith("  ") and entries:
            # Continuation line — append to previous entry
            entries[-1] += "\n  " + s
        elif len(s) >= 10 and s[:4].isdigit() and s[4] == "-":
            entries.append(s)
    return entries[-n:]


# ── Upcoming events ────────────────────────────────────────────────────────────

def _upcoming_events(project_dir: Path, days: int = 5) -> list:
    """Return events in the next *days* days, sorted by date."""
    data    = _read_agenda(resolve_file(project_dir, "agenda"))
    today   = date.today()
    horizon = today + timedelta(days=days)
    result  = []
    for ev in data["events"]:
        try:
            d = date.fromisoformat(ev["date"])
        except ValueError:
            continue
        if today <= d <= horizon:
            result.append((d, ev["desc"]))
    return sorted(result, key=lambda x: x[0])


# ── Summary builder ────────────────────────────────────────────────────────────

def _build_summary(project_dir: Path) -> str:
    meta             = _read_project_meta(project_dir)
    status, display, _ = _resolve_status(meta, project_dir)
    data             = _read_agenda(resolve_file(project_dir, "agenda"))
    name             = meta["name"]

    bar   = "─" * _WIDTH
    lines = [
        f"── {name} " + "─" * max(0, _WIDTH - len(name) - 4),
        f"Estado: {display}   Prioridad: {meta['prioridad']}",
        "",
    ]

    # Pending tasks
    pending_tasks = [t for t in data["tasks"] if t["status"] == "pending"]
    if pending_tasks:
        lines.append("Tareas pendientes")
        for t in pending_tasks:
            date_s = f" ({t['date']})" if t.get("date") else ""
            lines.append(f"  · {t['desc']}{date_s}")
        lines.append("")

    # Pending milestones
    pending_ms = [ms for ms in data["milestones"] if ms["status"] == "pending"]
    if pending_ms:
        lines.append("Hitos pendientes")
        for ms in pending_ms:
            date_s = f" ({ms['date']})" if ms.get("date") else ""
            lines.append(f"  · {ms['desc']}{date_s}")
        lines.append("")

    # Upcoming events (next 5 days)
    upcoming = _upcoming_events(project_dir, days=5)
    if upcoming:
        lines.append("Próximos 5 días")
        for d, desc in upcoming:
            lines.append(f"  · {d.isoformat()} — {desc}")
        lines.append("")

    # Recent logbook entries
    recent = _recent_logbook_entries(project_dir, n=5)
    if recent:
        lines.append("Últimas entradas")
        for entry in recent:
            lines.append(f"  {entry}")
        lines.append("")

    lines.append(bar)
    return "\n".join(lines)


def _build_summary_md(project_dir: Path) -> str:
    """Same content as terminal summary but formatted as markdown."""
    meta               = _read_project_meta(project_dir)
    status, display, _ = _resolve_status(meta, project_dir)
    data               = _read_agenda(resolve_file(project_dir, "agenda"))
    name               = meta["name"]

    parts = [
        f"# {name}",
        "",
        f"**Estado:** {display}   **Prioridad:** {meta['prioridad']}",
        "",
    ]

    pending_tasks = [t for t in data["tasks"] if t["status"] == "pending"]
    if pending_tasks:
        parts.append("## ✅ Tareas pendientes")
        for t in pending_tasks:
            date_s = f" ({t['date']})" if t.get("date") else ""
            parts.append(f"- [ ] {t['desc']}{date_s}")
        parts.append("")

    pending_ms = [ms for ms in data["milestones"] if ms["status"] == "pending"]
    if pending_ms:
        parts.append("## 🏁 Hitos pendientes")
        for ms in pending_ms:
            date_s = f" ({ms['date']})" if ms.get("date") else ""
            parts.append(f"- [ ] {ms['desc']}{date_s}")
        parts.append("")

    upcoming = _upcoming_events(project_dir, days=5)
    if upcoming:
        parts.append("## 📅 Próximos 5 días")
        for d, desc in upcoming:
            parts.append(f"- {d.isoformat()} — {desc}")
        parts.append("")

    recent = _recent_logbook_entries(project_dir, n=5)
    if recent:
        parts.append("## 📓 Últimas entradas")
        for entry in recent:
            parts.append(f"  {entry}")
        parts.append("")

    return "\n".join(parts)


# ── Project picker ─────────────────────────────────────────────────────────────

def _pick_project() -> Optional[Path]:
    """Show numbered list of new-format projects; return selected dir or None."""
    dirs = [d for d in iter_project_dirs() if _is_new_project(d)]
    if not dirs:
        print("No hay proyectos (nuevo modelo) disponibles.")
        return None

    print("\nProyectos:")
    for i, d in enumerate(dirs, 1):
        meta             = _read_project_meta(d)
        _, display, _    = _resolve_status(meta, d)
        print(f"  {i:2}. {meta['name']:<25} {display}")
    print()

    if not sys.stdin.isatty():
        return None

    try:
        raw = input("Selecciona (número o nombre parcial): ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return None

    if not raw:
        return None
    if raw.isdigit():
        idx = int(raw) - 1
        if 0 <= idx < len(dirs):
            return dirs[idx]
        print(f"Fuera de rango (1–{len(dirs)})")
        return None
    matches = [d for d in dirs if raw.lower() in d.name.lower()]
    if not matches:
        print(f"Sin coincidencias para '{raw}'")
        return None
    if len(matches) > 1:
        print(f"Ambiguo: {len(matches)} coincidencias")
        return None
    return matches[0]


# ── Public commands ────────────────────────────────────────────────────────────

def run_new_view(project: Optional[str] = None,
                 open_after: bool = False,
                 editor: str = "") -> int:
    """Terminal summary of a new-format project (or picker if no project given)."""
    if project:
        project_dir = _find_new_project(project)
        if project_dir is None:
            return 1
    else:
        project_dir = _pick_project()
        if project_dir is None:
            return 1

    if open_after:
        md = _build_summary_md(project_dir)
        with tempfile.NamedTemporaryFile(suffix=".md", mode="w",
                                         delete=False, prefix="orbit_view_") as f:
            f.write(md)
            tmp = Path(f.name)
        return open_file(tmp, editor)
    else:
        print(_build_summary(project_dir))
        return 0


_VALID_WHAT = {"logbook", "highlights", "agenda", "project"}


def run_new_open(project: str, what: Optional[str] = None,
                 editor: str = "") -> int:
    """Open a file from a new-format project in the editor.

    *what*: logbook | highlights | agenda | notes | project  (default: project)
    """
    project_dir = _find_new_project(project)
    if project_dir is None:
        return 1

    if what == "notes":
        # Open the notes/ directory (Typora shows a file tree)
        path = project_dir / "notes"
        if not path.exists():
            print(f"Error: no existe notes/ en {project_dir.name}")
            return 1
    elif what is None or what in _VALID_WHAT:
        kind = what or "project"
        path = resolve_file(project_dir, kind)
    else:
        print(f"Error: '{what}' no válido. Opciones: {', '.join(sorted(_VALID_WHAT))} notes")
        return 1

    if not path.exists():
        print(f"Error: no existe {path.name} en {project_dir.name}")
        return 1

    print(f"Abriendo {path.name}...")
    return open_file(path, editor)


def run_open_dir(project: str) -> int:
    """Open the project directory in Finder."""
    project_dir = _find_new_project(project)
    if project_dir is None:
        return 1
    import subprocess
    subprocess.run(["open", str(project_dir)])
    print(f"Abriendo directorio {project_dir.name}...")
    return 0

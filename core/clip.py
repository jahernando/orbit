"""orbit clip — copy useful references to the clipboard.

  orbit clip date [expr]                  →  2026-03-22
  orbit clip week [expr]                  →  2026-W12
  orbit clip proj [target] [--from proj]  →  [label](path)

`clip proj` without target links to the project file.
`clip proj target` resolves target as:
  1. Exact file path within the project (e.g. agenda.md, notes/foo.md)
  2. Recursive partial-match search across all project subdirectories
     (disambiguates interactively if multiple matches)
"""

import os
import re
import subprocess
from pathlib import Path, PurePosixPath
from typing import Optional

from core.config import ORBIT_HOME
from core.log import find_proyecto_file, resolve_file
from core.project import _find_new_project


# ── Clipboard helper ─────────────────────────────────────────────────────────

def _copy_to_clipboard(text: str) -> None:
    """Copy text to macOS clipboard and confirm."""
    try:
        subprocess.run(["pbcopy"], input=text.encode(), check=True)
        print("  (copiado al portapapeles)")
    except (FileNotFoundError, subprocess.CalledProcessError):
        pass


# ── clip date ────────────────────────────────────────────────────────────────

def _clip_date(expr: str = "today") -> int:
    from core.dateparse import parse_date
    result = parse_date(expr)
    if not re.match(r'^\d{4}-\d{2}-\d{2}$', result):
        print(f"  no se pudo resolver a una fecha: {expr}")
        return 1
    print(result)
    _copy_to_clipboard(result)
    return 0


# ── clip week ────────────────────────────────────────────────────────────────

def _clip_week(expr: str = "today") -> int:
    from datetime import date
    from core.dateparse import parse_date, _week_key
    result = parse_date(expr)
    if re.match(r'^\d{4}-W\d{2}$', result):
        week = result
    elif re.match(r'^\d{4}-\d{2}-\d{2}$', result):
        week = _week_key(date.fromisoformat(result))
    else:
        print(f"  no se pudo resolver a una semana: {expr}")
        return 1
    print(week)
    _copy_to_clipboard(week)
    return 0


# ── clip proj ────────────────────────────────────────────────────────────────

def _find_file_in_project(project_dir: Path, query: str) -> Optional[Path]:
    """Find a file in a project by exact path or recursive partial match.

    Returns the resolved Path, or None (with error printed).
    """
    # 1. Try as literal path (with or without .md)
    for candidate in [project_dir / query, project_dir / f"{query}.md"]:
        if candidate.exists() and candidate.is_file():
            return candidate

    # 2. Recursive search by stem match
    query_low = query.lower()
    matches = []
    for p in project_dir.rglob("*"):
        if not p.is_file():
            continue
        if p.name.startswith("."):
            continue
        if query_low in p.stem.lower():
            matches.append(p)

    if not matches:
        print(f"Error: no se encontró '{query}' en {project_dir.name}")
        return None

    if len(matches) == 1:
        return matches[0]

    # Exact stem match takes priority
    exact = [m for m in matches if m.stem.lower() == query_low]
    if len(exact) == 1:
        return exact[0]

    # Interactive disambiguation
    matches.sort(key=lambda p: p.name)
    print(f"  '{query}' es ambiguo en {project_dir.name}:")
    for i, m in enumerate(matches, 1):
        rel = m.relative_to(project_dir)
        print(f"  {i}. {rel}")
    try:
        choice = input("  Elige [1]: ").strip()
        idx = int(choice) - 1 if choice else 0
        if 0 <= idx < len(matches):
            return matches[idx]
    except (ValueError, EOFError, KeyboardInterrupt):
        pass
    print("  Cancelado.")
    return None


def _clip_proj(name: str, target: str = None,
               from_project: str = None) -> int:
    project_dir = _find_new_project(name)
    if project_dir is None:
        return 1

    if target:
        found = _find_file_in_project(project_dir, target)
        if found is None:
            return 1
        target_rel = found.relative_to(ORBIT_HOME)
        label = found.stem
    else:
        project_file = find_proyecto_file(project_dir)
        if project_file is None:
            print(f"Error: no se encontró fichero de proyecto en {project_dir.name}")
            return 1
        target_rel = project_file.relative_to(ORBIT_HOME)
        label = project_dir.name

    if from_project:
        from_dir = _find_new_project(from_project)
        if from_dir is None:
            return 1
        from_root = from_dir.relative_to(ORBIT_HOME)
        rel = PurePosixPath(os.path.relpath(target_rel, from_root))
    else:
        rel = target_rel

    link = f"[{label}]({rel})"
    print(link)
    _copy_to_clipboard(link)
    return 0


# ── Dispatcher ───────────────────────────────────────────────────────────────

def run_clip(mode: str, args) -> int:
    """Main entry point for `orbit clip`."""
    if mode in ("date", "week"):
        # Combine target + expr into a single expression string
        parts = []
        if getattr(args, "target", None):
            parts.append(args.target)
        if getattr(args, "expr", None):
            parts.extend(args.expr)
        expr = " ".join(parts) if parts else "today"
        if mode == "date":
            return _clip_date(expr)
        return _clip_week(expr)
    # Default: project link
    return _clip_proj(
        name=mode,
        target=getattr(args, "target", None),
        from_project=getattr(args, "from_project", None),
    )

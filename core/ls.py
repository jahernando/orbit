"""orbit ls — unified listing command.

  ls                  list projects (default)
  ls projects         list projects with status
  ls tasks [P...]     list tasks
  ls ms   [P...]      list milestones
  ls ev   [P]         list events
  ls hl   [P]         list highlights
  ls files [P]        list all md files in project with git status
  ls notes [P]        list notes with git status
"""

import subprocess
from pathlib import Path
from typing import Optional

from core.log import PROJECTS_DIR
from core.project import _find_new_project, _is_new_project

ORBIT_DIR = Path(__file__).parent.parent


# ── Git helpers ───────────────────────────────────────────────────────────────

def _git_status_indicator(path: Path) -> str:
    """Return a git status indicator for a file.

    ✓  tracked and clean
    M  tracked and modified
    +  untracked (new)
    ✗  ignored by .gitignore
    """
    try:
        # Check if ignored
        r = subprocess.run(
            ["git", "check-ignore", "-q", str(path)],
            capture_output=True, cwd=ORBIT_DIR,
        )
        if r.returncode == 0:
            return "✗"

        # Check if tracked
        r = subprocess.run(
            ["git", "ls-files", "--error-unmatch", str(path)],
            capture_output=True, cwd=ORBIT_DIR,
        )
        if r.returncode != 0:
            return "+"

        # Tracked — check if modified
        r = subprocess.run(
            ["git", "diff", "--name-only", str(path)],
            capture_output=True, text=True, cwd=ORBIT_DIR,
        )
        if r.stdout.strip():
            return "M"

        # Also check staged changes
        r = subprocess.run(
            ["git", "diff", "--cached", "--name-only", str(path)],
            capture_output=True, text=True, cwd=ORBIT_DIR,
        )
        if r.stdout.strip():
            return "M"

        return "✓"
    except FileNotFoundError:
        return "?"


def _collect_project_dirs(project: Optional[str] = None) -> list:
    """Resolve project arg(s) to a list of project directories."""
    if project:
        d = _find_new_project(project)
        return [d] if d else []
    return sorted(d for d in PROJECTS_DIR.iterdir()
                  if d.is_dir() and _is_new_project(d))


# ── ls files ──────────────────────────────────────────────────────────────────

def run_ls_files(project: Optional[str] = None) -> int:
    """List all markdown files in project directory (non-recursive) with git status."""
    dirs = _collect_project_dirs(project)
    if project and not dirs:
        return 1

    total = 0
    for project_dir in dirs:
        md_files = sorted(f for f in project_dir.iterdir()
                          if f.is_file() and f.suffix == ".md")
        if not md_files:
            continue

        print(f"\n[{project_dir.name}]")
        for f in md_files:
            indicator = _git_status_indicator(f)
            print(f"  {indicator}  {f.name}")
            total += 1

    if not total:
        print("No hay ficheros.")
    else:
        print()
    return 0


# ── ls notes ──────────────────────────────────────────────────────────────────

def run_ls_notes(project: Optional[str] = None) -> int:
    """List notes/ markdown files with git status."""
    dirs = _collect_project_dirs(project)
    if project and not dirs:
        return 1

    total = 0
    for project_dir in dirs:
        notes_dir = project_dir / "notes"
        if not notes_dir.exists():
            continue
        notes = sorted(f for f in notes_dir.glob("*.md")
                       if not f.name.startswith("."))
        if not notes:
            continue

        print(f"\n[{project_dir.name}/notes]")
        for f in notes:
            indicator = _git_status_indicator(f)
            print(f"  {indicator}  {f.name}")
            total += 1

    if not total:
        print("No hay notas.")
    else:
        print()
    return 0

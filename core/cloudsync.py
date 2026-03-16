"""cloudsync.py — sync .md project files to cloud.

After a git commit, copies changed .md files to the corresponding
cloud directory so they can be read from mobile devices via Obsidian.

Also provides a full sync for initial setup.

Cloud structure mirrors the repo:
  cloud_root/{type_dir}/{project_dir}/file.md
  cloud_root/{type_dir}/{project_dir}/notes/*.md
  cloud_root/{type_dir}/{project_dir}/cloud/logs/  (delivered files)
"""

import shutil
import subprocess
from pathlib import Path

from core.config import ORBIT_HOME, get_type_emojis, iter_project_dirs
from core.deliver import _find_cloud_root


def _committed_files() -> list:
    """Return list of file paths changed in the last commit."""
    try:
        result = subprocess.run(
            ["git", "diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD"],
            capture_output=True, text=True, cwd=ORBIT_HOME,
        )
        if result.returncode != 0:
            return []
        return [p.strip() for p in result.stdout.splitlines() if p.strip()]
    except FileNotFoundError:
        return []


def _is_project_file(rel_path: str) -> bool:
    """Check if a relative path is inside a type/project directory."""
    parts = Path(rel_path).parts
    if len(parts) < 2:
        return False
    type_emojis = get_type_emojis()
    return any(parts[0].startswith(e) for e in type_emojis)


def _sync_file(src: Path, dest: Path) -> bool:
    """Copy src to dest if src is newer or dest doesn't exist.

    Returns True if the file was copied.
    """
    if dest.exists() and dest.stat().st_mtime >= src.stat().st_mtime:
        return False
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(str(src), str(dest))
    return True


def sync_to_cloud() -> int:
    """Copy recently committed .md files to cloud.

    Returns the number of files synced.
    """
    cloud_root = _find_cloud_root()
    if not cloud_root:
        return 0

    files = _committed_files()
    if not files:
        return 0

    synced = 0
    for rel_path in files:
        if not rel_path.endswith(".md"):
            continue
        if not _is_project_file(rel_path):
            continue

        src = ORBIT_HOME / rel_path
        if not src.exists():
            continue  # file was deleted

        dest = cloud_root / rel_path
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(src), str(dest))
        synced += 1

    return synced


def sync_all_to_cloud(dry_run: bool = False) -> int:
    """Copy all .md project files to cloud (initial full sync).

    Only copies files that are newer than the cloud copy or don't
    exist in cloud yet.

    Returns the number of files synced.
    """
    cloud_root = _find_cloud_root()
    if not cloud_root:
        return 0

    synced = 0
    for project_dir in iter_project_dirs():
        rel_project = project_dir.relative_to(ORBIT_HOME)

        # Collect all .md files in the project directory (non-recursive + notes/)
        md_files = list(project_dir.glob("*.md"))
        notes_dir = project_dir / "notes"
        if notes_dir.is_dir():
            md_files.extend(notes_dir.rglob("*.md"))

        for src in md_files:
            rel = src.relative_to(ORBIT_HOME)
            dest = cloud_root / rel

            if dry_run:
                if not dest.exists() or dest.stat().st_mtime < src.stat().st_mtime:
                    synced += 1
            else:
                if _sync_file(src, dest):
                    synced += 1

    return synced

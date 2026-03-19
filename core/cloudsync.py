"""cloudsync.py — sync project files to cloud as HTML.

After a git commit, renders changed .md files to HTML and copies them
to the cloud directory for reading from mobile devices.

Cloud structure:
  cloud_root/index.html                          ← project dashboard
  cloud_root/orbit.css                           ← shared stylesheet
  cloud_root/inbox.md                            ← global mobile inbox
  cloud_root/{type_dir}/{project_dir}/*.html     ← rendered project files
  cloud_root/{type_dir}/{project_dir}/notes/*.html
  cloud_root/{type_dir}/{project_dir}/inbox.md   ← per-project mobile inbox
  cloud_root/{type_dir}/{project_dir}/cloud/     ← delivered files (logs, hls)
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
    """Render recently committed .md files to HTML in cloud.

    Returns the number of files rendered.
    """
    from core.render import render_changed, _render_dashboard, ensure_cloud_inboxes
    cloud_root = _find_cloud_root()
    if not cloud_root:
        return 0

    n = render_changed(cloud_root)
    _render_dashboard(cloud_root)
    ensure_cloud_inboxes(cloud_root)
    return n


def sync_to_cloud_background() -> None:
    """Run sync_to_cloud in a background subprocess (fire & forget)."""
    import sys
    subprocess.Popen(
        [sys.executable, "-c",
         "from core.cloudsync import sync_to_cloud; sync_to_cloud()"],
        cwd=str(ORBIT_HOME),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def sync_all_to_cloud(dry_run: bool = False) -> int:
    """Render all .md project files to HTML in cloud (initial full sync).

    Returns the number of files rendered.
    """
    from core.render import render_all, _render_dashboard, ensure_cloud_inboxes
    cloud_root = _find_cloud_root()
    if not cloud_root:
        return 0

    n = render_all(cloud_root)
    _render_dashboard(cloud_root)
    ensure_cloud_inboxes(cloud_root)
    return n

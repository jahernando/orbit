"""cloudsync.py — sync project files to cloud as HTML.

After a git commit, renders changed .md files to HTML and copies them
to the cloud directory for reading from mobile devices.

Cloud structure:
  cloud_root/index.html                          ← project dashboard
  cloud_root/orbit.css                           ← shared stylesheet
  cloud_root/{type_dir}/{project_dir}/*.html     ← rendered project files
  cloud_root/{type_dir}/{project_dir}/notes/*.html
  cloud_root/{type_dir}/{project_dir}/cloud/     ← delivered files (logs, hls)
"""

import json
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

from core.config import ORBIT_HOME, get_type_emojis, iter_project_dirs
from core.deliver import _find_cloud_root

_SYNC_STATUS_FILE = ORBIT_HOME / ".cloud-sync.json"


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


def _write_sync_status(rendered: int, error: str = "") -> None:
    """Write sync result to .cloud-sync.json for startup verification."""
    commit = ""
    try:
        r = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, cwd=ORBIT_HOME,
        )
        if r.returncode == 0:
            commit = r.stdout.strip()
    except FileNotFoundError:
        pass

    status = {
        "time": datetime.now().isoformat(timespec="seconds"),
        "commit": commit,
        "rendered": rendered,
        "ok": not error,
    }
    if error:
        status["error"] = error
    try:
        _SYNC_STATUS_FILE.write_text(json.dumps(status, ensure_ascii=False))
    except OSError:
        pass


def _read_sync_status() -> dict:
    """Read last sync status. Returns {} if not available."""
    try:
        return json.loads(_SYNC_STATUS_FILE.read_text())
    except (OSError, json.JSONDecodeError):
        return {}


def sync_to_cloud() -> int:
    """Render recently committed .md files to HTML in cloud.

    Returns the number of files rendered.
    """
    from core.render import render_changed, _render_dashboard
    cloud_root = _find_cloud_root()
    if not cloud_root:
        _write_sync_status(0, error="cloud_root no encontrado")
        return 0

    try:
        n = render_changed(cloud_root)
        _render_dashboard(cloud_root)
        _write_sync_status(n)
        return n
    except Exception as e:
        _write_sync_status(0, error=str(e))
        raise


def sync_to_cloud_background() -> None:
    """Run sync_to_cloud in a background subprocess (fire & forget)."""
    import os
    import sys
    from core.config import ORBIT_CODE
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ORBIT_CODE) + os.pathsep + env.get("PYTHONPATH", "")
    # Wrap in try/except so errors are captured in .cloud-sync.json
    cmd = (
        "try:\n"
        "    from core.cloudsync import sync_to_cloud; sync_to_cloud()\n"
        "except Exception as e:\n"
        "    from core.cloudsync import _write_sync_status; "
        "_write_sync_status(0, error=str(e))\n"
    )
    subprocess.Popen(
        [sys.executable, "-c", cmd],
        cwd=str(ORBIT_HOME),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env=env,
        start_new_session=True,
    )


def sync_all_to_cloud(dry_run: bool = False) -> int:
    """Render all .md project files to HTML in cloud (initial full sync).

    Returns the number of files rendered.
    """
    from core.render import render_all, _render_dashboard
    cloud_root = _find_cloud_root()
    if not cloud_root:
        return 0

    n = render_all(cloud_root)
    _render_dashboard(cloud_root)
    return n


# ── Cloud check ──────────────────────────────────────────────────────────────

def startup_cloud_check() -> None:
    """Check last background sync status and warn if it failed."""
    status = _read_sync_status()
    if not status:
        return
    if status.get("ok"):
        return
    error = status.get("error", "desconocido")
    commit = status.get("commit", "?")
    time = status.get("time", "?")
    print(f"  ⚠️  El último cloud sync falló ({time}, commit {commit})")
    print(f"      Error: {error}")
    print(f"      Ejecuta 'render --full' para re-sincronizar.")
    print()


def check_cloud_sync() -> int:
    """Compare source .md mtimes vs cloud .html — report stale files.

    Returns 0 if all up to date, 1 if stale files found.
    """
    from core.deliver import _project_cloud_dir
    from core.project import _is_new_project

    cloud_root = _find_cloud_root()
    if not cloud_root:
        return 1

    stale = []
    missing = []
    ok = 0

    for project_dir in iter_project_dirs():
        if not _is_new_project(project_dir):
            continue
        cloud_dir = _project_cloud_dir(project_dir, cloud_root)
        if not cloud_dir:
            continue

        md_files = list(project_dir.glob("*.md"))
        notes_dir = project_dir / "notes"
        if notes_dir.is_dir():
            md_files.extend(notes_dir.rglob("*.md"))

        for src in md_files:
            rel = src.relative_to(project_dir)
            dest = cloud_dir / rel.with_suffix(".html")
            if not dest.exists():
                missing.append((project_dir.name, rel))
            elif dest.stat().st_mtime < src.stat().st_mtime:
                stale.append((project_dir.name, rel))
            else:
                ok += 1

    # Show last sync status
    status = _read_sync_status()
    if status:
        flag = "✓" if status.get("ok") else "✗"
        print(f"  Último sync: {flag} {status.get('time', '?')} "
              f"(commit {status.get('commit', '?')}, "
              f"{status.get('rendered', 0)} renderizados)")

    if not stale and not missing:
        print(f"  ☁️  Cloud al día — {ok} ficheros OK")
        return 0

    if stale:
        print(f"\n  ⚠️  {len(stale)} fichero{'s' if len(stale) != 1 else ''} desactualizado{'s' if len(stale) != 1 else ''}:")
        for proj, rel in stale[:10]:
            print(f"      {proj}/{rel}")
        if len(stale) > 10:
            print(f"      ... y {len(stale) - 10} más")

    if missing:
        print(f"\n  ❌ {len(missing)} fichero{'s' if len(missing) != 1 else ''} sin HTML en cloud:")
        for proj, rel in missing[:10]:
            print(f"      {proj}/{rel}")
        if len(missing) > 10:
            print(f"      ... y {len(missing) - 10} más")

    print(f"\n  Ejecuta 'render --full' para re-sincronizar.")
    return 1

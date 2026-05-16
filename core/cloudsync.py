"""cloudsync.py — estado del último render-to-cloud + health checks.

El flujo "render → cloud_root" vive en views/render/render.py
(`render_changed_to_cloud` y compañía). Este módulo se queda con la
parte de status-reporting: escribir `.cloud-sync.json` cuando termina
una pasada, leerlo en startup, y un check on-demand que compara mtimes
md vs html.

Cloud structure:
  cloud_root/index.html                          ← project dashboard
  cloud_root/orbit.css                           ← shared stylesheet
  cloud_root/{type_dir}/{project_dir}/*.html     ← rendered project files
  cloud_root/{type_dir}/{project_dir}/notes/*.html
  cloud_root/{type_dir}/{project_dir}/cloud/     ← delivered files (logs, hls)
"""

import json
import subprocess
from datetime import datetime
from pathlib import Path

from core.config import ORBIT_HOME, iter_project_dirs
from core.deliver import _find_cloud_root

_SYNC_STATUS_FILE = ORBIT_HOME / ".cloud-sync.json"


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

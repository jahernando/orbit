"""deliver.py — deliver files to cloud.

  deliver <project> <file>

Copies a file (from any location) to the project's cloud directory and
leaves the cloud path in the clipboard.

Cloud structure:
  cloud_root/{emoji}{space_name}/{type_emoji}{type_name}/{project_dir}/
"""
import shutil
import subprocess
from datetime import date
from pathlib import Path
from typing import Optional

from core.config import (ORBIT_HOME as ORBIT_DIR,
                         _load_orbit_json, _load_types,
                         get_reverse_type_map)
from core.log import find_project


IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".bmp", ".tiff"}


def encode_cloud_link(path: str) -> str:
    """Encode a cloud path for safe use in markdown links.

    Replaces @ and spaces so GitHub's renderer doesn't choke on emails
    or break on whitespace in paths.
    """
    return path.replace("@", "%40").replace(" ", "%20")


def _find_cloud_root() -> Optional[Path]:
    """Return the cloud root for the current workspace from orbit.json."""
    config = _load_orbit_json()
    cr = config.get("cloud_root")
    if cr:
        return Path(cr.replace("~", str(Path.home())))
    print("Error: no existe cloud_root en orbit.json")
    return None


def _project_type_name(project_dir: Path) -> Optional[str]:
    """Extract the type name from a project directory's leading emoji."""
    dirname = project_dir.name
    reverse_map = get_reverse_type_map()
    for emoji, type_name in reverse_map.items():
        if dirname.startswith(emoji):
            return type_name
    return None


def _project_cloud_dir(project_dir: Path, cloud_root: Path) -> Optional[Path]:
    """Build cloud path: cloud_root/{type_emoji}{type}/{project_dir}/"""
    type_name = _project_type_name(project_dir)
    if not type_name:
        print(f"Error: no se pudo determinar el tipo del proyecto '{project_dir.name}'")
        return None
    types = _load_types()
    type_emoji = types[type_name]
    type_dir = f"{type_emoji}{type_name}"
    return cloud_root / type_dir / project_dir.name


def _copy_to_clipboard(text: str) -> None:
    """Copy text to macOS clipboard."""
    try:
        subprocess.run(["pbcopy"], input=text.encode(), check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass


def _is_url(ref: str) -> bool:
    """Check if a reference is a URL."""
    return ref.startswith("http://") or ref.startswith("https://")


def deliver_file(project_dir: Path, src: Path, subdir: str = "",
                 date_prefix: bool = False) -> Optional[Path]:
    """Copy a file to the project's cloud directory.

    Args:
        project_dir: local project directory
        src: source file path
        subdir: subdirectory under cloud project dir ("logs", "hls", or "")
        date_prefix: if True, prefix filename with YYYY-MM-DD_

    Returns the cloud destination path, or None on error.
    """
    cloud_root = _find_cloud_root()
    if not cloud_root:
        return None

    cloud_dir = _project_cloud_dir(project_dir, cloud_root)
    if not cloud_dir:
        return None

    dest_dir = cloud_dir / subdir if subdir else cloud_dir
    filename = f"{date.today().isoformat()}_{src.name}" if date_prefix else src.name
    dest = dest_dir / filename
    dest.parent.mkdir(parents=True, exist_ok=True)

    shutil.copy2(str(src), str(dest))
    print(f"  📦 {src.name} → {dest.parent}/")
    return dest


def run_deliver(project: str, file: str) -> int:
    """Deliver a file to cloud and copy the cloud path to clipboard."""

    # Resolve source file
    src = Path(file).expanduser()
    if not src.is_absolute():
        project_dir = find_project(project)
        if not project_dir:
            return 1
        candidate = project_dir / file
        if candidate.exists():
            src = candidate
        else:
            src = Path.cwd() / file
    else:
        project_dir = find_project(project)
        if not project_dir:
            return 1

    if not src.exists():
        print(f"Error: no existe {src}")
        return 1

    dest = deliver_file(project_dir, src)
    if not dest:
        return 1

    _copy_to_clipboard(str(dest))
    print(f"💾 Fichero entregado (enlace en portapapeles)")
    return 0

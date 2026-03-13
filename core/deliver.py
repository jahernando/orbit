"""deliver.py — deliver files to cloud and optionally log/highlight them.

  deliver <project> <file> "<title>" [--log] [--hl] [--entry TIPO] [--type TIPO]

Copies a file (from any location) to the project's cloud directory and
optionally creates logbook/highlights entries linking to the cloud copy.
"""
import shutil
from pathlib import Path
from typing import Optional

from core.config import ORBIT_HOME as ORBIT_DIR
from core.log import find_project, add_entry, VALID_TYPES
from core.highlights import run_hl_add, VALID_TYPES as HL_TYPES


IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".bmp", ".tiff"}

_CONF = Path.home() / ".config" / "deliver.conf"


def _find_cloud_root() -> Optional[Path]:
    """Read deliver.conf and return the cloud root for the current workspace."""
    if not _CONF.exists():
        print(f"Error: no existe {_CONF}")
        return None
    ws = str(ORBIT_DIR)
    for line in _CONF.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        left, right = line.split("=", 1)
        left = left.strip().replace("~", str(Path.home()))
        right = right.strip().replace("~", str(Path.home()))
        if left == ws:
            return Path(right)
    print(f"Error: workspace {ws} no está en {_CONF}")
    return None


def _project_cloud_dir(project_dir: Path, cloud_root: Path) -> Path:
    """Return the cloud directory for a project."""
    rel = project_dir.relative_to(ORBIT_DIR)
    return cloud_root / rel


def run_deliver(project: str, file: str, title: str,
                log: bool = False, hl: bool = False,
                entry_type: str = "apunte", hl_type: str = "refs") -> int:
    """Deliver a file to cloud and optionally create logbook/highlights entries."""

    # Validate types before doing anything
    if log and entry_type not in VALID_TYPES:
        print(f"Error: --entry '{entry_type}' no válido. Opciones: {', '.join(VALID_TYPES)}")
        return 1
    if hl and hl_type not in HL_TYPES:
        print(f"Error: --type '{hl_type}' no válido. Opciones: {', '.join(HL_TYPES)}")
        return 1

    # Resolve source file
    src = Path(file).expanduser()
    if not src.is_absolute():
        # Try relative to project dir first, then cwd
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

    # Resolve cloud destination
    cloud_root = _find_cloud_root()
    if not cloud_root:
        return 1

    cloud_dir = _project_cloud_dir(project_dir, cloud_root)
    dest = cloud_dir / src.name
    dest.parent.mkdir(parents=True, exist_ok=True)

    # Copy to cloud
    shutil.copy2(str(src), str(dest))
    print(f"📦 {src.name} → {dest.parent}/")
    print(f"💾 Fichero entregado")

    # Cloud link for logbook/highlights entries
    cloud_link = str(dest)

    # Logbook entry
    if log:
        ext = src.suffix.lower()
        if ext in IMAGE_EXTS:
            path_str = f"![]({cloud_link})"
        else:
            path_str = cloud_link
        rc = add_entry(project, title, entry_type, path_str, None)
        if rc != 0:
            return rc

    # Highlights entry
    if hl:
        rc = run_hl_add(project, title, hl_type, link=cloud_link)
        if rc != 0:
            return rc

    return 0

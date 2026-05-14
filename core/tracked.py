"""tracked — registry of tracked external markdown files (propia/externa model).

In the v0.36 model:

* **Propia** notes live entirely in the workspace (`notes/<name>.md`),
  owned by the user, edited freely. They are not registered here.
* **Externa** notes live elsewhere (a public docs repo, a shared Drive
  folder, a colleague's directory). The workspace holds a **symlink**
  at `notes/<name>` pointing to the source. The truth never leaves the
  source; orbit just keeps a window into it.

The registry lives in ``<project>/.orbit-tracked.json``:

    {
        "files": {
            "DECISIONS.md": "/Users/hernando/orbit/DECISIONS.md",
            "RING.md":      "/Users/hernando/orbit/RING.md"
        }
    }

The registry exists so orbit can enumerate "what's tracked here" without
scanning the filesystem, and so render knows which symlinks to publish
to the cloud HTML. The symlink itself is the operational truth.

Symlinks are stored as **relative paths** computed from the symlink's
own location to the target. This makes them survive a clone to another
Mac as long as orbit-ws and the source repo maintain their relative
position (the user's standard layout: both under ``$HOME``).

See DECISIONS.md ADR-026 for the rationale (supersedes ADR-024).
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Iterable, Optional


REGISTRY_NAME = ".orbit-tracked.json"


# ── Registry I/O ───────────────────────────────────────────────────────

def _registry_path(project_dir: Path) -> Path:
    return project_dir / REGISTRY_NAME


def load_registry(project_dir: Path) -> dict:
    """Return ``{filename: source_path}`` map for the project (empty if none).

    Transparently handles both v0.36 (``{"files": {...}}``) and legacy
    v0.34 (``{"notes/x.md": {"source": ...}}``) formats; legacy format is
    surfaced under the same dict for read-only consumers, but writers
    should use ``save_registry`` to canonicalize on next save.
    """
    p = _registry_path(project_dir)
    if not p.exists():
        return {}
    try:
        raw = json.loads(p.read_text())
    except json.JSONDecodeError:
        return {}
    # v0.36 schema
    if isinstance(raw, dict) and "files" in raw and isinstance(raw["files"], dict):
        return {k: str(v) for k, v in raw["files"].items()}
    # v0.34 schema: keys "notes/<name>" → {"source": ...}
    out: dict = {}
    for k, v in raw.items():
        if isinstance(v, dict) and "source" in v:
            name = k.split("/", 1)[1] if k.startswith("notes/") else k
            out[name] = v["source"]
    return out


def save_registry(project_dir: Path, files: dict) -> None:
    """Persist the registry in v0.36 schema. Deletes the file when empty."""
    p = _registry_path(project_dir)
    if not files:
        p.unlink(missing_ok=True)
        return
    payload = {"files": {k: str(v) for k, v in files.items()}}
    p.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")


# ── Symlink helpers ────────────────────────────────────────────────────

def _relative_symlink_target(symlink_path: Path, target: Path) -> str:
    """Compute a relative path from symlink_path's parent to target.

    The result survives git clones as long as both paths sit in the same
    relative arrangement on the new host.
    """
    return os.path.relpath(target, start=symlink_path.parent)


def resolve_target(project_dir: Path, name: str) -> Optional[Path]:
    """Return the resolved absolute path the symlink points to, or None
    if the symlink is missing or its target doesn't exist."""
    link = project_dir / "notes" / name
    if not link.is_symlink():
        return None
    try:
        return link.resolve(strict=True)
    except (FileNotFoundError, OSError):
        return None


def is_external(project_dir: Path, note_path: Path) -> bool:
    """True if ``note_path`` (under ``project_dir/notes/``) is registered
    as externa (its filename is in the project's registry)."""
    if note_path.parent.name != "notes":
        return False
    return note_path.name in load_registry(project_dir)


# ── Track / untrack ────────────────────────────────────────────────────

def track(project_dir: Path, source: Path,
          name: Optional[str] = None) -> str:
    """Track ``source`` (external .md) as externa in ``project_dir``.

    Creates a relative symlink at ``project_dir/notes/<name>`` pointing
    to ``source``, and registers the pair. Returns the filename used.

    Args:
        source: full path to the external markdown file.
        name: filename for the symlink in notes/ (defaults to source.name).

    Raises:
        FileNotFoundError: if ``source`` does not exist.
        ValueError: if ``source`` is not a .md file.
        FileExistsError: if ``notes/<name>`` already exists.
    """
    source = source.expanduser().resolve()
    if not source.exists():
        raise FileNotFoundError(str(source))
    if source.is_dir():
        raise ValueError(f"track requiere un fichero, no un directorio: {source}")
    if source.suffix.lower() != ".md":
        raise ValueError(
            f"track solo soporta .md; recibido {source.suffix or 'sin extensión'}"
        )

    notes_dir = project_dir / "notes"
    notes_dir.mkdir(exist_ok=True)
    filename = name or source.name
    link = notes_dir / filename
    if link.exists() or link.is_symlink():
        raise FileExistsError(f"notes/{filename} ya existe en {project_dir.name}")

    rel_target = _relative_symlink_target(link, source)
    link.symlink_to(rel_target)

    files = load_registry(project_dir)
    files[filename] = str(source)
    save_registry(project_dir, files)
    return filename


def untrack(project_dir: Path, name: str) -> bool:
    """Remove a tracked entry. Deletes the symlink (source intact).

    Returns True if an entry was removed, False if it didn't exist.
    """
    files = load_registry(project_dir)
    if name not in files:
        return False
    link = project_dir / "notes" / name
    if link.is_symlink() or link.exists():
        link.unlink()
    del files[name]
    save_registry(project_dir, files)
    return True


# ── Scan all projects ──────────────────────────────────────────────────

def iter_tracked(project_dirs: Iterable[Path]):
    """Yield ``(project_dir, filename, source_path)`` over every tracked
    file across the given project dirs."""
    for pd in project_dirs:
        for name, src in load_registry(pd).items():
            yield (pd, name, src)


def check_status(project_dir: Path, name: str) -> str:
    """Return a status string for one tracked entry:

        "ok"            — symlink + target both exist and readable
        "broken_link"   — symlink exists but target missing
        "missing_link"  — registry entry but no symlink on disk
        "not_link"      — notes/<name> exists but isn't a symlink (manual override)
    """
    files = load_registry(project_dir)
    if name not in files:
        return "not_tracked"
    link = project_dir / "notes" / name
    if not link.exists() and not link.is_symlink():
        return "missing_link"
    if not link.is_symlink():
        return "not_link"
    try:
        target = link.resolve(strict=True)
        if target.is_file():
            return "ok"
        return "broken_link"
    except (FileNotFoundError, OSError):
        return "broken_link"

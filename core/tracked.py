"""tracked — registry of tracked external files mirrored into orbit-ws.

A *tracked file* is a markdown document whose truth lives outside the
workspace (a public docs repo, a draft elsewhere, a colleague's notes)
but that orbit mirrors into a project's ``notes/`` so:

* the file is versioned in orbit-ws's git history (one diff per commit
  in which the source evolved),
* the post-commit render generates HTML to the cloud automatically.

The registry lives in ``<project>/.orbit-tracked.json`` (one per project):

    {
        "notes/decisions.md": {
            "source":  "/absolute/path/to/DECISIONS.md",
            "sha256":  "a3f5…",       # hash at the last successful refresh
            "added":   "2026-05-13"
        }
    }

The mirrored note also carries a YAML frontmatter line so a human
reading the file in Obsidian/GitHub immediately knows "don't edit me,
the truth is elsewhere":

    ---
    orbit_tracked_from: /absolute/path/to/DECISIONS.md
    ---
    # Contenido importado…

Refresh policy (pre-commit hook in ``core/commit.py``):

    | source changed | dest changed | action                            |
    |----------------|--------------|-----------------------------------|
    | no             | no           | nothing                           |
    | yes            | no           | copy source → dest, update sha    |
    | no             | yes          | ABORT: dest tampered (warning)    |
    | yes            | yes          | ABORT: conflict (manual resolve)  |

See DECISIONS.md ADR-024 for the broader design rationale.
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
from dataclasses import dataclass
from datetime import date as _date
from pathlib import Path
from typing import Iterable, Optional


REGISTRY_NAME = ".orbit-tracked.json"
FRONTMATTER_KEY = "orbit_tracked_from"


# ── Registry I/O ───────────────────────────────────────────────────────

def _registry_path(project_dir: Path) -> Path:
    return project_dir / REGISTRY_NAME


def load_registry(project_dir: Path) -> dict:
    """Return the project's registry dict, or ``{}`` if none."""
    p = _registry_path(project_dir)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text())
    except json.JSONDecodeError:
        return {}


def save_registry(project_dir: Path, registry: dict) -> None:
    """Persist the registry. Deletes the file when empty."""
    p = _registry_path(project_dir)
    if not registry:
        p.unlink(missing_ok=True)
        return
    p.write_text(json.dumps(registry, indent=2, ensure_ascii=False) + "\n")


# ── Hashing ────────────────────────────────────────────────────────────

def _sha256_of_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


# ── Frontmatter helpers ────────────────────────────────────────────────

_FRONTMATTER_RE = re.compile(
    rf"^---\s*\n([^-]*\n)?\s*{FRONTMATTER_KEY}:\s*(.+?)\s*\n([^-]*\n)?---\s*\n",
    re.DOTALL,
)


def _strip_tracked_frontmatter(text: str) -> str:
    """Remove our YAML frontmatter block if present. Leaves other
    frontmatter alone (we only inject our key when missing)."""
    # Conservative implementation: only strip if the frontmatter is
    # exactly our minimal injected block.
    m = re.match(r"^---\s*\n" + re.escape(FRONTMATTER_KEY)
                 + r":[^\n]+\n---\s*\n", text)
    if m:
        return text[m.end():]
    return text


def _inject_tracked_frontmatter(text: str, source: str) -> str:
    """Prepend (or replace) our minimal frontmatter block."""
    text = _strip_tracked_frontmatter(text)
    return f"---\n{FRONTMATTER_KEY}: {source}\n---\n{text}"


# ── Refresh primitives ─────────────────────────────────────────────────

@dataclass
class RefreshOutcome:
    rel_dest: str        # path under project_dir (e.g. "notes/decisions.md")
    project: str         # project dir name
    status: str          # "clean" | "refreshed" | "dest_tampered" | "conflict" | "source_missing"
    source: str
    detail: str = ""     # optional explanation


def _content_with_frontmatter(source: Path, source_str: str) -> bytes:
    """Source content (bytes) wrapped with our frontmatter."""
    raw = source.read_text()
    return _inject_tracked_frontmatter(raw, source_str).encode("utf-8")


def _hash_dest_payload(dest: Path) -> str:
    """SHA256 of the dest *with* our frontmatter — that's what we wrote,
    so that's what we compare. If we hashed the source only, the
    frontmatter we inject would always show "dest tampered"."""
    return _sha256_of_file(dest)


def check_entry(project_dir: Path, rel_dest: str, entry: dict) -> RefreshOutcome:
    """Inspect one tracked entry without modifying anything."""
    source = Path(entry["source"])
    dest = project_dir / rel_dest
    stored_sha = entry.get("sha256", "")

    if not source.exists():
        return RefreshOutcome(rel_dest, project_dir.name, "source_missing",
                              str(source), detail=f"{source} no existe")

    if not dest.exists():
        # Dest deleted manually — treat as conflict to force resolution.
        return RefreshOutcome(rel_dest, project_dir.name, "conflict",
                              str(source),
                              detail=f"{dest} fue borrado; re-add con orbit tracked refresh --force-source")

    # Compute current hash of source-with-frontmatter and current dest.
    current_payload = _content_with_frontmatter(source, str(source))
    current_source_sha = hashlib.sha256(current_payload).hexdigest()
    current_dest_sha = _hash_dest_payload(dest)

    source_changed = (current_source_sha != stored_sha)
    dest_changed = (current_dest_sha != stored_sha)

    if not source_changed and not dest_changed:
        return RefreshOutcome(rel_dest, project_dir.name, "clean", str(source))
    if source_changed and not dest_changed:
        return RefreshOutcome(rel_dest, project_dir.name, "refreshed",
                              str(source))
    if not source_changed and dest_changed:
        return RefreshOutcome(rel_dest, project_dir.name, "dest_tampered",
                              str(source),
                              detail="la copia tracked fue editada; tus cambios se perderán al próximo refresh")
    # both changed
    return RefreshOutcome(rel_dest, project_dir.name, "conflict",
                          str(source),
                          detail="source y dest divergieron; resolución manual requerida")


def apply_refresh(project_dir: Path, rel_dest: str, entry: dict) -> RefreshOutcome:
    """Copy source → dest, update sha. Assumes the caller already
    decided it's safe to proceed."""
    source = Path(entry["source"])
    dest = project_dir / rel_dest
    payload = _content_with_frontmatter(source, str(source))
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(payload)
    entry["sha256"] = hashlib.sha256(payload).hexdigest()
    return RefreshOutcome(rel_dest, project_dir.name, "refreshed",
                          str(source))


# ── Registration ───────────────────────────────────────────────────────

def register(project_dir: Path, rel_dest: str, source: Path) -> dict:
    """Copy the source into dest, write frontmatter, register, save.

    Raises ``FileNotFoundError`` if source doesn't exist.
    Returns the registry entry for the new tracked file.
    """
    source = source.resolve()
    if not source.exists():
        raise FileNotFoundError(str(source))
    if source.suffix.lower() != ".md":
        raise ValueError(
            f"--track solo soporta .md; recibido {source.suffix or 'sin extensión'}"
        )

    payload = _content_with_frontmatter(source, str(source))
    dest = project_dir / rel_dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(payload)

    entry = {
        "source":  str(source),
        "sha256":  hashlib.sha256(payload).hexdigest(),
        "added":   _date.today().isoformat(),
    }
    registry = load_registry(project_dir)
    registry[rel_dest] = entry
    save_registry(project_dir, registry)
    return entry


def unregister(project_dir: Path, rel_dest: str,
               keep_file: bool = True) -> bool:
    """Remove an entry from the registry. If ``keep_file`` is False,
    also remove the mirrored file. Returns True if an entry was removed."""
    registry = load_registry(project_dir)
    if rel_dest not in registry:
        return False
    del registry[rel_dest]
    save_registry(project_dir, registry)
    if not keep_file:
        (project_dir / rel_dest).unlink(missing_ok=True)
    return True


def retrack(project_dir: Path, rel_dest: str, new_source: Path) -> dict:
    """Repoint an existing tracked entry at a new source. Re-imports
    immediately. Returns the updated entry."""
    new_source = new_source.resolve()
    if not new_source.exists():
        raise FileNotFoundError(str(new_source))
    registry = load_registry(project_dir)
    if rel_dest not in registry:
        raise KeyError(rel_dest)
    registry[rel_dest]["source"] = str(new_source)
    payload = _content_with_frontmatter(new_source, str(new_source))
    (project_dir / rel_dest).write_bytes(payload)
    registry[rel_dest]["sha256"] = hashlib.sha256(payload).hexdigest()
    save_registry(project_dir, registry)
    return registry[rel_dest]


# ── Scan all projects ──────────────────────────────────────────────────

def iter_tracked(project_dirs: Iterable[Path]):
    """Yield ``(project_dir, rel_dest, entry)`` over every tracked file
    across the given project dirs."""
    for pd in project_dirs:
        registry = load_registry(pd)
        for rel, entry in registry.items():
            yield (pd, rel, entry)


def refresh_all(project_dirs: Iterable[Path], force: bool = False) -> list:
    """Refresh every tracked file. Returns list of RefreshOutcomes.

    If ``force=False`` (default): only "refreshed" outcomes apply
    changes. "dest_tampered" and "conflict" are reported untouched
    (caller decides whether to abort).

    If ``force=True``: even tampered/conflict get the source written
    over the dest (source wins, dest edits lost).
    """
    outcomes = []
    for pd, rel, entry in iter_tracked(project_dirs):
        outcome = check_entry(pd, rel, entry)
        if outcome.status == "refreshed":
            apply_refresh(pd, rel, entry)
            registry = load_registry(pd)
            registry[rel] = entry
            save_registry(pd, registry)
        elif outcome.status in ("dest_tampered", "conflict") and force:
            apply_refresh(pd, rel, entry)
            registry = load_registry(pd)
            registry[rel] = entry
            save_registry(pd, registry)
            outcome = RefreshOutcome(rel, pd.name, "refreshed",
                                      entry["source"],
                                      detail="forced (previous state discarded)")
        outcomes.append(outcome)
    return outcomes

"""tracked_migrate — one-shot migration of v0.34 tracked entries to v0.36.

v0.34 stored each tracked entry as a *copy* of the source content (with
an injected frontmatter line) inside ``notes/``, plus a registry mapping
``"notes/<name>"`` → ``{source, sha256, added}``.

v0.36 replaces the copy with a **relative symlink** to the source. The
registry simplifies to ``{"files": {name: source_path}}``.

For each entry:

* If the v0.34 copy's content is byte-identical to ``source + frontmatter``
  (i.e. clean — the user never tampered) → delete the copy, create a
  relative symlink at ``notes/<name>``, rewrite the registry.
* If the copy diverges → ABORT for that entry, surface the divergence
  so the user can resolve manually (with diff/edit/decide).

Idempotent: if a project is already on the new schema, the migration
visits no entries.
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Iterable

from core.tracked import (
    REGISTRY_NAME, load_registry, save_registry,
    track as _tracked_track,
)


_LEGACY_FRONTMATTER_RE = re.compile(
    r"^---\s*\norbit_tracked_from:[^\n]+\n---\s*\n",
)


def _strip_legacy_frontmatter(text: str) -> str:
    m = _LEGACY_FRONTMATTER_RE.match(text)
    return text[m.end():] if m else text


def _is_legacy_format(project_dir: Path) -> bool:
    """True if the registry file is in v0.34 schema."""
    import json
    p = project_dir / REGISTRY_NAME
    if not p.exists():
        return False
    try:
        raw = json.loads(p.read_text())
    except json.JSONDecodeError:
        return False
    if not isinstance(raw, dict):
        return False
    if "files" in raw and isinstance(raw["files"], dict):
        return False   # v0.36
    # v0.34 keys look like "notes/x.md" → {source, sha256, ...}
    for k, v in raw.items():
        if isinstance(v, dict) and "source" in v:
            return True
    return False


def _read_legacy_registry(project_dir: Path) -> dict:
    """Return the raw v0.34 registry dict."""
    import json
    p = project_dir / REGISTRY_NAME
    try:
        raw = json.loads(p.read_text())
    except json.JSONDecodeError:
        return {}
    return raw if isinstance(raw, dict) else {}


def migrate_project(project_dir: Path, dry_run: bool = False) -> dict:
    """Migrate one project from v0.34 to v0.36 schema.

    Returns a summary dict::

        {"project": str, "migrated": [name], "skipped": [(name, reason)],
         "tampered": [(name, source)]}
    """
    summary = {"project": project_dir.name,
               "migrated": [], "skipped": [], "tampered": []}

    if not _is_legacy_format(project_dir):
        return summary   # nothing to do

    legacy = _read_legacy_registry(project_dir)
    new_files: dict = {}

    for rel, entry in legacy.items():
        if not (isinstance(entry, dict) and "source" in entry):
            summary["skipped"].append((rel, "entry inválido"))
            continue
        source = Path(entry["source"])
        # Filename in notes/ (strip "notes/" prefix if present).
        name = rel.split("/", 1)[1] if rel.startswith("notes/") else rel
        copy_path = project_dir / "notes" / name

        if not source.exists():
            summary["skipped"].append((name, f"source ausente: {source}"))
            continue
        if not copy_path.exists():
            # No local copy to compare → create symlink directly.
            if not dry_run:
                try:
                    _tracked_track(project_dir, source, name=name)
                except (FileNotFoundError, ValueError, FileExistsError) as e:
                    summary["skipped"].append((name, f"track falló: {e}"))
                    continue
            new_files[name] = str(source)
            summary["migrated"].append(name)
            continue

        # Compare: copy content (minus our injected frontmatter) vs source.
        try:
            copy_text = copy_path.read_text(encoding="utf-8")
            source_text = source.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError) as e:
            summary["skipped"].append((name, f"lectura falló: {e}"))
            continue

        stripped = _strip_legacy_frontmatter(copy_text)
        if stripped == source_text:
            # Clean: replace copy with symlink.
            if not dry_run:
                copy_path.unlink()
                try:
                    _tracked_track(project_dir, source, name=name)
                except (FileNotFoundError, ValueError, FileExistsError) as e:
                    summary["skipped"].append((name, f"track falló: {e}"))
                    continue
            new_files[name] = str(source)
            summary["migrated"].append(name)
        else:
            summary["tampered"].append((name, str(source)))

    if not dry_run and new_files:
        save_registry(project_dir, new_files)
    elif not dry_run and not new_files and summary["migrated"]:
        # All entries migrated but for some reason new_files is empty:
        # ensure the registry file is gone (no entries left).
        save_registry(project_dir, {})

    return summary


def migrate_all(project_dirs: Iterable[Path], dry_run: bool = False) -> int:
    """Run migrate_project across all given projects. Print a report.

    Returns 0 if everything migrated cleanly (or nothing to do).
    Returns 1 if any project had tampered entries needing manual fix.
    """
    any_tampered = False
    any_migrated = False
    prefix = "[DRY-RUN] " if dry_run else ""
    for pd in project_dirs:
        summary = migrate_project(pd, dry_run=dry_run)
        if not summary["migrated"] and not summary["skipped"] \
                and not summary["tampered"]:
            continue
        any_migrated = any_migrated or bool(summary["migrated"])
        print(f"{prefix}🔄 [{summary['project']}]")
        for name in summary["migrated"]:
            print(f"  ✓ {name} (clean → symlink)")
        for name, reason in summary["skipped"]:
            print(f"  ⚠️  {name}: {reason}")
        for name, src in summary["tampered"]:
            any_tampered = True
            print(f"  ❌ {name}: contenido diverge de {src}")
            print(f"      → edita notes/{name} para resolver, luego repite migrate")

    if any_tampered:
        return 1
    if not any_migrated:
        print("Nada que migrar (todos los proyectos ya en v0.36 o sin tracked).")
    return 0

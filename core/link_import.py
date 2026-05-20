"""link_import — unify link-vs-import decision and execution for log/hl/note.

Two modes for attaching a local file to a project entry:

  * **link**: create a relative symlink at the destination, pointing to the
    source. No copy. The source stays the truth.
  * **import**: copy the file to the destination. The destination becomes a
    fully-owned snapshot. No link to source.

Routing by file extension:

  * ``.md`` files → ``project_dir/notes/<name>`` (Obsidian-visible).
  * anything else → ``project_dir/cloud/<non_md_subdir>/<name>`` (cloud-synced).

The asymmetry exists because Markdown notes belong in the workspace's note
vault (so Obsidian indexes them) while other artefacts (PDFs, images, CSV,
ZIPs) belong in the cloud-synced area so they're accessible from mobile.

Two public entry points:

* :func:`ask_mode` — strict interactive prompt, re-prompts on invalid input
* :func:`apply_mode` — execute the chosen mode, return the relative
  markdown link the caller should store in the logbook / highlights line
"""
from __future__ import annotations

import os
import shutil
import sys
import unicodedata
from datetime import date as _date
from pathlib import Path
from typing import Tuple


# ── Interactive prompt ─────────────────────────────────────────────────────────

def echo_mode(mode: str, rel_link: str) -> None:
    """Print one line confirming where the file landed.

    Example:
        🔗 modo: link → notes/foo.md
        📦 modo: import → cloud/logs/2026-05-20_foo.pdf
    """
    emoji = "🔗" if mode == "link" else "📦"
    target = rel_link.lstrip("./") if rel_link.startswith("./") else rel_link
    print(f"  {emoji} modo: {mode} → {target}")


def ask_mode() -> str:
    """Strict interactive prompt: returns ``"import"`` or ``"link"``.

    Interactive defaults:
        Enter / empty input → ``"import"``
        invalid input       → re-prompts with a hint
        EOF / Ctrl-C        → ``"import"``

    Non-tty (scripts): returns ``"link"`` so the source file is referenced
    rather than copied. The conservative choice — scripts shouldn't
    silently move files into cloud/ without explicit consent.
    """
    if not sys.stdin.isatty():
        return "link"
    while True:
        try:
            ans = input(
                "  📦 ¿Cómo guardar este fichero? "
                "[I]mportar (cloud, defecto) / [L]ink (fuente): "
            ).strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            return "import"
        if ans in ("", "i", "import"):
            return "import"
        if ans in ("l", "link"):
            return "link"
        print(f"  ⚠️  Respuesta no reconocida: '{ans}'. "
              "Usa i/import o l/link, o Enter para import.")


# ── NFD → ASCII for Obsidian-friendly filenames ────────────────────────────────

def _strip_diacritics(name: str) -> str:
    """Return ``name`` with combining diacritics removed.

    Obsidian on macOS does not resolve wiki-links to files whose names
    contain NFD-decomposed accents (see [[project_orbit_obsidian_nfd_filenames]]).
    Imported/linked .md files are normalised to NFC and stripped of
    diacritics to keep them findable.
    """
    nfkd = unicodedata.normalize("NFKD", name)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


# ── apply_mode ────────────────────────────────────────────────────────────────

def apply_mode(project_dir: Path, src: Path, mode: str, *,
               non_md_subdir: str,
               date_prefix: bool = False) -> Tuple[str, Path]:
    """Apply link or import for ``src`` in ``project_dir``.

    Returns ``(relative_link, dest_path)``:
      * ``relative_link`` — markdown link the caller should write into the
        logbook / highlights line (e.g. ``./notes/foo.md`` or
        ``./cloud/logs/2026-05-20_foo.pdf``).
      * ``dest_path`` — absolute path of the created symlink or copy.

    Args:
        project_dir: local project directory.
        src: source file (must exist; directories not supported).
        mode: ``"link"`` (symlink) or ``"import"`` (copy).
        non_md_subdir: subdir under ``cloud/`` for non-md files
            (e.g. ``"logs"`` for log, ``"hls"`` for hl).
        date_prefix: prepend ``YYYY-MM-DD_`` to the destination filename.
            Applied to .md files in notes/ AND non-md in cloud/ uniformly.

    Raises:
        FileNotFoundError: source missing.
        ValueError: source is a directory, mode unknown, or .md link
            target is not actually .md.
        FileExistsError: destination already taken.
        RuntimeError: cloud_root or project type not resolvable
            (non-md path only).
    """
    src = src.expanduser().resolve()
    if not src.exists():
        raise FileNotFoundError(str(src))
    if src.is_dir():
        raise ValueError(f"link/import requiere un fichero, no un directorio: {src}")
    if mode not in ("link", "import"):
        raise ValueError(f"modo desconocido: {mode!r}")

    is_md = src.suffix.lower() == ".md"
    base = _strip_diacritics(src.name) if is_md else src.name
    filename = f"{_date.today().isoformat()}_{base}" if date_prefix else base

    if is_md:
        return _apply_md(project_dir, src, mode, filename)
    return _apply_non_md(project_dir, src, mode, filename, non_md_subdir)


# ── Implementations ────────────────────────────────────────────────────────────

def _apply_md(project_dir: Path, src: Path, mode: str,
              filename: str) -> Tuple[str, Path]:
    """Place an .md file in ``notes/`` as symlink (link) or copy (import)."""
    notes_dir = project_dir / "notes"
    notes_dir.mkdir(exist_ok=True)
    dest = notes_dir / filename
    if dest.exists() or dest.is_symlink():
        raise FileExistsError(f"notes/{filename} ya existe en {project_dir.name}")

    if mode == "link":
        # Reuse the tracked registry — externa semantics already established.
        from core.tracked import track as _tracked_track
        try:
            registered = _tracked_track(project_dir, src, name=filename)
        except FileExistsError:
            raise
        dest = notes_dir / registered
    else:  # import
        shutil.copy2(str(src), str(dest))

    rel_link = f"./notes/{filename}"
    return rel_link, dest


def _apply_non_md(project_dir: Path, src: Path, mode: str,
                  filename: str, subdir: str) -> Tuple[str, Path]:
    """Place a non-md file in ``cloud/<subdir>/`` as symlink or copy.

    For *link* the symlink target is the source on the local filesystem.
    Note that cloud-sync services may not follow symlinks; the symlink
    is functional locally but may appear broken in cloud web/mobile views.
    """
    from core.deliver import (_find_cloud_root, _project_cloud_dir,
                              CLOUD_SUBDIR, ensure_project_cloud_symlink,
                              encode_cloud_link)

    cloud_root = _find_cloud_root()
    if not cloud_root:
        raise RuntimeError("cloud_root no configurado en orbit.json")
    cloud_dir = _project_cloud_dir(project_dir, cloud_root)
    if not cloud_dir:
        raise RuntimeError(
            f"no se pudo determinar directorio cloud para {project_dir.name}")

    dest_dir = cloud_dir / CLOUD_SUBDIR / subdir
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / filename
    if dest.exists() or dest.is_symlink():
        raise FileExistsError(f"cloud/{subdir}/{filename} ya existe en "
                              f"{project_dir.name}")

    if mode == "link":
        rel_target = os.path.relpath(src, start=dest.parent)
        dest.symlink_to(rel_target)
    else:  # import
        shutil.copy2(str(src), str(dest))

    ensure_project_cloud_symlink(project_dir)
    rel_link = encode_cloud_link(f"./{CLOUD_SUBDIR}/{subdir}/{filename}")
    return rel_link, dest


# ── Mode resolution from CLI flags ─────────────────────────────────────────────

def resolve_mode(as_link: bool, as_import: bool) -> str:
    """Resolve mode from the two CLI flags, prompting if both are False.

    Returns ``"import"`` or ``"link"``. Raises :class:`ValueError` if both
    flags are True (mutex violation).
    """
    if as_link and as_import:
        raise ValueError("--link y --import son mutuamente exclusivos")
    if as_link:
        return "link"
    if as_import:
        return "import"
    return ask_mode()

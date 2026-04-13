"""cloud_imgs.py — collect pasted images from Obsidian and deliver to project cloud.

Obsidian pastes images into a shared _imgs/ directory at the vault root.
This module scans _imgs/, finds which .md file references each image,
determines the project, renames the file (date_note_figN.ext), moves it
to cloud/imgs/, and updates the link in the markdown.

  orbit cloud imgs [--dry-run]
"""

import re
import shutil
from pathlib import Path
from typing import Optional

from core.config import ORBIT_HOME, iter_project_dirs
from core.deliver import (
    IMAGE_EXTS, CLOUD_SUBDIR, deliver_file, ensure_project_cloud_symlink,
    encode_cloud_link,
)

# Directory where Obsidian drops pasted images (configurable in Obsidian settings)
IMGS_DIR_NAME = "_imgs"

# Regex patterns for image references in markdown
# Obsidian wikilink: ![[filename.png]]
_WIKILINK_IMG_RE = re.compile(r'!\[\[([^\]]+)\]\]')
# Standard markdown: ![alt](path)
_MD_IMG_RE = re.compile(r'!\[([^\]]*)\]\(([^\)]+)\)')


def _imgs_dir() -> Path:
    """Return the shared _imgs/ directory in the workspace root."""
    return ORBIT_HOME / IMGS_DIR_NAME


def _list_pending_images() -> list:
    """List image files waiting in _imgs/."""
    d = _imgs_dir()
    if not d.exists():
        return []
    return [f for f in sorted(d.iterdir())
            if f.is_file() and f.suffix.lower() in IMAGE_EXTS]


def _find_references(image_name: str) -> list:
    """Find all .md files that reference this image name.

    Searches for both wikilink (![[name]]) and markdown (![](path/name))
    syntax across all project directories.

    Returns list of (md_path, project_dir) tuples.
    """
    refs = []
    for project_dir in iter_project_dirs():
        for md_file in project_dir.rglob("*.md"):
            # Skip cloud/ directory (symlink to cloud storage)
            try:
                rel = md_file.relative_to(project_dir)
                if str(rel).startswith(CLOUD_SUBDIR):
                    continue
            except ValueError:
                continue
            try:
                content = md_file.read_text()
            except (OSError, UnicodeDecodeError):
                continue
            # Check wikilink: ![[image_name]] (Obsidian may omit extension)
            stem = Path(image_name).stem
            if image_name in content or stem in content:
                # Verify it's actually an image reference
                for m in _WIKILINK_IMG_RE.finditer(content):
                    ref = m.group(1)
                    # Obsidian wikilinks may include path or just filename
                    if Path(ref).name == image_name or Path(ref).stem == stem:
                        refs.append((md_file, project_dir))
                        break
                else:
                    # Check markdown image syntax
                    for m in _MD_IMG_RE.finditer(content):
                        ref_path = m.group(2)
                        if Path(ref_path).name == image_name:
                            refs.append((md_file, project_dir))
                            break
    return refs


def _note_stem(md_path: Path) -> str:
    """Extract a clean stem from a note path for use in image naming.

    '2026-03-25_resultados.md' → 'resultados'
    'logbook.md' → 'logbook'
    'highlights.md' → 'highlights'
    """
    stem = md_path.stem
    # Remove date prefix if present (YYYY-MM-DD_)
    if re.match(r'^\d{4}-\d{2}-\d{2}_', stem):
        stem = stem[11:]
    return stem


def _note_date(md_path: Path) -> str:
    """Extract date from note filename, or use today's date.

    '2026-03-25_resultados.md' → '2026-03-25'
    'logbook.md' → today's date
    """
    from datetime import date
    m = re.match(r'^(\d{4}-\d{2}-\d{2})', md_path.stem)
    if m:
        return m.group(1)
    return date.today().isoformat()


def _build_new_name(image_path: Path, md_path: Path, fig_index: int,
                    total_figs: int) -> str:
    """Build new filename: date_notestem[_figN].ext

    Args:
        image_path: original image file
        md_path: the .md file referencing it
        fig_index: 1-based index of this figure
        total_figs: total figures for this note

    Returns e.g. '2026-03-25_resultados_fig1.png'
    """
    d = _note_date(md_path)
    stem = _note_stem(md_path)
    ext = image_path.suffix.lower()
    if total_figs > 1:
        return f"{d}_{stem}_fig{fig_index}{ext}"
    return f"{d}_{stem}{ext}"


def _update_link_in_file(md_path: Path, old_name: str, new_rel_path: str) -> bool:
    """Replace image references in a markdown file.

    Handles both:
      ![[old_name]]           → ![](new_rel_path)
      ![...](path/old_name)  → ![...](new_rel_path)

    Returns True if any replacement was made.
    """
    try:
        content = md_path.read_text()
    except (OSError, UnicodeDecodeError):
        return False

    old_stem = Path(old_name).stem
    new_content = content
    changed = False

    # Replace wikilink: ![[old_name]] or ![[old_stem]]
    for pattern_str in [re.escape(old_name), re.escape(old_stem)]:
        wiki_re = re.compile(r'!\[\[' + pattern_str + r'\]\]')
        if wiki_re.search(new_content):
            new_content = wiki_re.sub(f'![]({new_rel_path})', new_content)
            changed = True

    # Replace markdown image: ![...](anything/old_name)
    def _replace_md_img(m):
        nonlocal changed
        alt = m.group(1)
        ref = m.group(2)
        if Path(ref).name == old_name:
            changed = True
            return f'![{alt}]({new_rel_path})'
        return m.group(0)

    new_content = _MD_IMG_RE.sub(_replace_md_img, new_content)

    if changed:
        md_path.write_text(new_content)
    return changed


def run_cloud_imgs(dry_run: bool = False) -> int:
    """Collect images from _imgs/, deliver to project cloud/imgs/, update links.

    Returns 0 on success, 1 on error.
    """
    images = _list_pending_images()
    if not images:
        print("✓ No hay imágenes pendientes en _imgs/")
        return 0

    print(f"  🖼️  {len(images)} imagen{'es' if len(images) != 1 else ''} en _imgs/")
    print()

    # Phase 1: match each image to its referencing .md and project
    matched = []    # (image_path, md_path, project_dir)
    orphans = []    # image_path (no reference found)

    for img in images:
        refs = _find_references(img.name)
        if not refs:
            orphans.append(img)
        elif len(refs) == 1:
            md_path, project_dir = refs[0]
            matched.append((img, md_path, project_dir))
        else:
            # Multiple references — use first, warn
            md_path, project_dir = refs[0]
            matched.append((img, md_path, project_dir))
            other_projs = [r[1].name for r in refs[1:]]
            print(f"  ⚠️  {img.name} referenciada en múltiples proyectos, "
                  f"usando {project_dir.name} (también en: {', '.join(other_projs)})")

    # Phase 2: group by (md_path) to assign fig indices
    from collections import defaultdict
    by_note = defaultdict(list)
    for img, md_path, project_dir in matched:
        by_note[(md_path, project_dir)].append(img)

    # Phase 3: rename, move, update links
    moved = 0
    for (md_path, project_dir), imgs_for_note in by_note.items():
        total = len(imgs_for_note)
        for idx, img in enumerate(imgs_for_note, 1):
            new_name = _build_new_name(img, md_path, idx, total)
            cloud_rel = encode_cloud_link(
                f"./{CLOUD_SUBDIR}/imgs/{new_name}")

            # Compute relative path from md_path to cloud/imgs/
            try:
                md_rel = md_path.relative_to(project_dir)
                depth = len(md_rel.parts) - 1  # how many dirs deep
                if depth > 0:
                    prefix = "/".join([".."] * depth)
                    rel_path = encode_cloud_link(
                        f"{prefix}/{CLOUD_SUBDIR}/imgs/{new_name}")
                else:
                    rel_path = cloud_rel
            except ValueError:
                rel_path = cloud_rel

            if dry_run:
                print(f"  📋 {img.name}")
                print(f"     → {project_dir.name}/cloud/imgs/{new_name}")
                print(f"     🔗 {md_path.name}: {rel_path}")
            else:
                # Ensure cloud/imgs/ exists
                ensure_project_cloud_symlink(project_dir)
                cloud_imgs = project_dir / CLOUD_SUBDIR / "imgs"
                cloud_imgs.mkdir(parents=True, exist_ok=True)

                dest = cloud_imgs / new_name
                shutil.move(str(img), str(dest))

                # Update link in markdown
                _update_link_in_file(md_path, img.name, rel_path)

                print(f"  📦 {img.name} → {project_dir.name}/cloud/imgs/{new_name}")

            moved += 1

    # Report orphans
    if orphans:
        print()
        print(f"  ⚠️  {len(orphans)} imagen{'es' if len(orphans) != 1 else ''} "
              f"sin referencia en ningún .md (huérfana{'s' if len(orphans) != 1 else ''}):")
        for o in orphans:
            print(f"     {o.name}")

    if not dry_run and moved:
        print()
        print(f"  ✓ {moved} imagen{'es' if moved != 1 else ''} "
              f"entregada{'s' if moved != 1 else ''} al cloud")

    return 0


def check_pending_imgs() -> int:
    """Check if there are images pending in _imgs/. For doctor integration.

    Returns the count of pending images.
    """
    return len(_list_pending_images())

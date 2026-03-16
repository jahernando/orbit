"""recloud.py — migrate cloud structure and links to use per-project cloud/ dir.

Cloud structure (after migration):
  cloud_root/{type_dir}/{project_dir}/cloud/logs/
  cloud_root/{type_dir}/{project_dir}/cloud/hls/
  cloud_root/{type_dir}/{project_dir}/cloud/{any_other}/

Repo structure:
  {type_dir}/{project_dir}/cloud  → symlink to cloud dir above

Links in .md files:
  ./cloud/logs/file.pdf   (relative — works locally via symlink, in mobile via cloud fs)
"""

import shutil
from pathlib import Path
from typing import Optional

from core.config import ORBIT_HOME, iter_project_dirs
from core.deliver import (_find_cloud_root, _project_cloud_dir,
                          encode_cloud_link, ensure_project_cloud_symlink,
                          CLOUD_SUBDIR)
from core.log import find_logbook_file, project_file_path


# Known subdirs that deliver uses; others are left in place
_KNOWN_SUBDIRS = {"logs", "hls"}


def _move_subdir_into_cloud(cloud_project_dir: Path, subdir: str,
                            dry_run: bool = False) -> bool:
    """Move cloud_project_dir/subdir/ → cloud_project_dir/cloud/subdir/.

    Returns True if files were moved.
    """
    src = cloud_project_dir / subdir
    if not src.exists() or not src.is_dir():
        return False

    dst = cloud_project_dir / CLOUD_SUBDIR / subdir
    if dst.exists():
        # Already migrated — but there might be files left in src
        remaining = list(src.iterdir())
        if not remaining:
            return False
        # Move remaining files
        if not dry_run:
            dst.mkdir(parents=True, exist_ok=True)
            for f in remaining:
                target = dst / f.name
                if not target.exists():
                    shutil.move(str(f), str(target))
        return True

    if dry_run:
        n = len(list(src.iterdir()))
        if n > 0:
            print(f"    {subdir}/ → cloud/{subdir}/ ({n} fichero{'s' if n != 1 else ''})")
        return n > 0

    dst.mkdir(parents=True, exist_ok=True)
    for f in src.iterdir():
        shutil.move(str(f), str(dst / f.name))

    # Remove empty source dir
    try:
        src.rmdir()
    except OSError:
        pass

    return True


def _remove_old_symlink(project_dir: Path, name: str) -> bool:
    """Remove a per-subdir symlink (logs, hls) from the repo if it exists."""
    link = project_dir / name
    if link.is_symlink():
        link.unlink()
        return True
    return False


def _rewrite_file(filepath: Path, cloud_project_prefix: str,
                  dry_run: bool = False) -> int:
    """Replace absolute/old cloud paths with ./cloud/ relative links.

    Handles:
      - Raw cloud paths:      .../project_dir/logs/file  → ./cloud/logs/file
      - Old symlink paths:    ORBIT_HOME/cloud/.../logs/  → ./cloud/logs/
      - Previous relative:    ./logs/file                 → ./cloud/logs/file

    Returns the number of replacements made.
    """
    if not filepath.exists():
        return 0

    text = filepath.read_text()
    count = 0

    # 1. Replace absolute cloud paths: cloud_project_prefix/{subdir}/ → ./cloud/{subdir}/
    for prefix in [cloud_project_prefix, encode_cloud_link(cloud_project_prefix)]:
        for subdir in _KNOWN_SUBDIRS:
            old = f"{prefix}/{subdir}/"
            new = f"./{CLOUD_SUBDIR}/{subdir}/"
            n = text.count(old)
            if n > 0:
                text = text.replace(old, new)
                count += n

    # 2. Replace old global-symlink paths: ...ORBIT_HOME/cloud/.../{subdir}/ → ./cloud/{subdir}/
    # Build the old symlink-based prefix
    old_global_symlink = str(ORBIT_HOME / "cloud")
    cloud_root = _find_cloud_root()
    if cloud_root:
        cloud_dir_from_root = cloud_project_prefix.replace(str(cloud_root), "")
        old_symlink_prefix = old_global_symlink + cloud_dir_from_root
        for prefix in [old_symlink_prefix, encode_cloud_link(old_symlink_prefix)]:
            for subdir in _KNOWN_SUBDIRS:
                old = f"{prefix}/{subdir}/"
                new = f"./{CLOUD_SUBDIR}/{subdir}/"
                n = text.count(old)
                if n > 0:
                    text = text.replace(old, new)
                    count += n

    # 3. Replace previous relative links: ./logs/ → ./cloud/logs/, ./hls/ → ./cloud/hls/
    for subdir in _KNOWN_SUBDIRS:
        old = f"./{subdir}/"
        new = f"./{CLOUD_SUBDIR}/{subdir}/"
        n = text.count(old)
        if n > 0:
            text = text.replace(old, new)
            count += n

    if count > 0:
        if dry_run:
            print(f"  {filepath.name}: {count} enlace{'s' if count != 1 else ''}")
        else:
            filepath.write_text(text)
            print(f"  ✓ {filepath.name}: {count} enlace{'s' if count != 1 else ''} migrado{'s' if count != 1 else ''}")

    return count


def run_recloud(dry_run: bool = False) -> int:
    """Migrate cloud structure and links to per-project cloud/ directory.

    Steps:
      1. For each project with cloud content:
         a. Move files in cloud from logs/, hls/ into cloud/logs/, cloud/hls/
         b. Create project_dir/cloud symlink
         c. Remove old per-subdir symlinks (logs/, hls/)
         d. Rewrite logbook and highlights to use ./cloud/{subdir}/ links
    """
    cloud_root = _find_cloud_root()
    if not cloud_root:
        return 1

    if dry_run:
        print("Dry run: mostrando cambios sin aplicar")
        print()

    total_links = 0
    total_symlinks = 0
    total_moved = 0
    projects = 0

    for project_dir in iter_project_dirs():
        cloud_dir = _project_cloud_dir(project_dir, cloud_root)
        if not cloud_dir:
            continue

        project_touched = False

        # 1. Move files in cloud into cloud/ subdirectory
        if cloud_dir.exists():
            for subdir in _KNOWN_SUBDIRS:
                if _move_subdir_into_cloud(cloud_dir, subdir, dry_run=dry_run):
                    total_moved += 1
                    project_touched = True

        # 2. Create per-project cloud symlink
        if not dry_run:
            cloud_link = project_dir / CLOUD_SUBDIR
            was_symlink = cloud_link.is_symlink()
            ensure_project_cloud_symlink(project_dir)
            if cloud_link.is_symlink() and not was_symlink:
                total_symlinks += 1

        # 3. Remove old per-subdir symlinks
        if not dry_run:
            for subdir in _KNOWN_SUBDIRS:
                _remove_old_symlink(project_dir, subdir)

        # 4. Rewrite links in logbook and highlights
        cloud_prefix = str(cloud_dir)
        logbook = find_logbook_file(project_dir)
        highlights = project_file_path(project_dir, "highlights")

        project_link_count = 0
        for filepath in [logbook, highlights]:
            if filepath:
                project_link_count += _rewrite_file(
                    filepath, cloud_prefix, dry_run=dry_run)

        if project_link_count > 0:
            projects += 1
            total_links += project_link_count

    if total_links == 0 and total_symlinks == 0 and total_moved == 0:
        print("No se encontraron cambios pendientes.")
    else:
        if total_moved > 0:
            verb = "a mover" if dry_run else "movidos"
            print(f"\n  📦 {total_moved} directorio{'s' if total_moved != 1 else ''} {verb} a cloud/.")
        if total_links > 0:
            verb = "encontrados" if dry_run else "migrados"
            print(f"  {'🔍' if dry_run else '✅'} {total_links} enlace{'s' if total_links != 1 else ''} "
                  f"{verb} en {projects} proyecto{'s' if projects != 1 else ''}.")
        if total_symlinks > 0:
            print(f"  🔗 {total_symlinks} symlink{'s' if total_symlinks != 1 else ''} creado{'s' if total_symlinks != 1 else ''}.")

    # Full sync: copy all .md project files to cloud
    from core.cloudsync import sync_all_to_cloud
    n = sync_all_to_cloud(dry_run=dry_run)
    if n > 0:
        verb = "a sincronizar" if dry_run else "sincronizados"
        print(f"  ☁️  {n} fichero{'s' if n != 1 else ''} .md {verb} al cloud.")

    return 0

"""commit.py — git commit with auto-message and interactive confirmation.

  commit ["<message>"]

Without message: prompted interactively. Empty input → Orbit generates one.
Shows changed files and asks for confirmation before executing.
"""
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

from core.config import ORBIT_HOME as ORBIT_DIR, get_type_emojis


# ── Git helpers ────────────────────────────────────────────────────────────────

def _git_status() -> list:
    """Return list of (status_code, path) for modified/untracked tracked files."""
    try:
        result = subprocess.run(
            ["git", "-c", "core.quotePath=false", "status", "--porcelain"],
            capture_output=True, text=True, cwd=ORBIT_DIR,
        )
        if result.returncode != 0:
            return []
        lines = []
        for line in result.stdout.splitlines():
            if len(line) >= 4:
                code = line[:2].strip()
                path = line[3:].strip()
                if code and path:
                    lines.append((code, path))
        return lines
    except FileNotFoundError:
        return []


def _git_staged() -> list:
    """Return list of (status_code, path) for staged files only."""
    try:
        result = subprocess.run(
            ["git", "-c", "core.quotePath=false", "diff", "--cached", "--name-status"],
            capture_output=True, text=True, cwd=ORBIT_DIR,
        )
        if result.returncode != 0:
            return []
        lines = []
        for line in result.stdout.splitlines():
            parts = line.split("\t", 1)
            if len(parts) == 2:
                lines.append((parts[0].strip(), parts[1].strip()))
        return lines
    except FileNotFoundError:
        return []


def _git_add_all_tracked() -> bool:
    """Stage all changes to tracked files (git add -u)."""
    try:
        result = subprocess.run(
            ["git", "add", "-u"], cwd=ORBIT_DIR, capture_output=True,
        )
        return result.returncode == 0
    except FileNotFoundError:
        return False


def _git_untracked_in_projects() -> list:
    """Return list of untracked file paths inside all type directories."""
    all_untracked = []
    type_emojis = get_type_emojis()
    try:
        for child in sorted(ORBIT_DIR.iterdir()):
            if not child.is_dir():
                continue
            if not any(child.name.startswith(e) for e in type_emojis):
                continue
            result = subprocess.run(
                ["git", "-c", "core.quotePath=false", "ls-files", "--others",
                 "--exclude-standard", f"{child.name}/"],
                capture_output=True, text=True, cwd=ORBIT_DIR,
            )
            if result.returncode == 0:
                all_untracked.extend(p.strip() for p in result.stdout.splitlines() if p.strip())
    except FileNotFoundError:
        pass
    return all_untracked


def _git_add_files(files: list) -> bool:
    """Stage specific files."""
    try:
        result = subprocess.run(
            ["git", "add"] + files, cwd=ORBIT_DIR, capture_output=True,
        )
        return result.returncode == 0
    except FileNotFoundError:
        return False


def _gitignore_files(files: list) -> None:
    """Append files to .gitignore."""
    gitignore = Path(ORBIT_DIR) / ".gitignore"
    with open(gitignore, "a") as f:
        f.write("\n# Auto-ignored by Orbit\n")
        for p in files:
            f.write(p + "\n")
    print(f"  ✓ {len(files)} fichero{'s' if len(files) != 1 else ''} añadido{'s' if len(files) != 1 else ''} a .gitignore")


def _confirm_gitignore(files: list) -> bool:
    """Show files and confirm before adding to .gitignore.

    Returns True if confirmed (or cancelled), False to go back to main menu.
    """
    n = len(files)
    print(f"\n  Se añadirán a .gitignore ({n} fichero{'s' if n != 1 else ''}):")
    for p in files:
        print(f"      ✗  {p}")
    try:
        ans = input("  ¿Confirmar? [S/n/r(repetir)]: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        return True
    if ans in ("r", "repetir"):
        return False
    if ans in ("", "s", "si", "sí", "y", "yes"):
        _gitignore_files(files)
        return True
    return True  # n/no → cancel, don't loop


def _prompt_untracked() -> None:
    """Detect untracked files in projects and ask to add them.

    Shows numbered list; user can select all, specific indices, or none.
    Confirms selection before staging.
    """
    untracked = _git_untracked_in_projects()
    if not untracked or not sys.stdin.isatty():
        return

    while True:
        n = len(untracked)
        print(f"  📂 {n} fichero{'s' if n != 1 else ''} nuevo{'s' if n != 1 else ''} sin trackear:")
        for i, p in enumerate(untracked, 1):
            print(f"      [{i}] +  {p}")

        try:
            prompt = ("  ¿Añadir? [S=todos / 1,2,... / n / i=ignorar]: "
                      if n > 1 else "  ¿Añadir? [S/n/i=ignorar]: ")
            ans = input(prompt).strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return

        if ans.lower() in ("n", "no"):
            return

        if ans.lower() in ("i", "ignorar"):
            if _confirm_gitignore(untracked):
                return
            print()
            continue

        # Determine selected files
        if ans == "" or ans.lower() in ("s", "si", "sí", "y", "yes"):
            selected = untracked
        else:
            # Parse comma-separated indices
            try:
                indices = [int(x.strip()) for x in ans.split(",")]
                selected = [untracked[i - 1] for i in indices if 1 <= i <= n]
            except (ValueError, IndexError):
                print("  ⚠️  Selección no válida")
                continue
            if not selected:
                print("  ⚠️  Ningún fichero seleccionado")
                continue

        # Confirm selection (skip if all selected with S)
        if len(selected) < n:
            print(f"\n  Ficheros seleccionados:")
            for p in selected:
                print(f"      +  {p}")
            try:
                confirm = input("  ¿Confirmar? [S/n/r(repetir)]: ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                print()
                return
            if confirm in ("r", "repetir"):
                print()
                continue
            if confirm not in ("", "s", "si", "sí", "y", "yes"):
                return

        _git_add_files(selected)
        ns = len(selected)
        print(f"  ✓ {ns} fichero{'s' if ns != 1 else ''} añadido{'s' if ns != 1 else ''}")

        # Offer to gitignore the remaining untracked files
        remaining = [f for f in untracked if f not in selected]
        if remaining:
            _confirm_gitignore(remaining)
        return


def _git_commit(message: str) -> int:
    """Run git commit -m message. Returns returncode."""
    try:
        result = subprocess.run(
            ["git", "commit", "-m", message],
            cwd=ORBIT_DIR,
        )
        return result.returncode
    except FileNotFoundError:
        print("Error: git no encontrado")
        return 1


# ── Auto-message builder ───────────────────────────────────────────────────────

def _auto_message(status_lines: list) -> str:
    """Generate a short automatic commit message from changed files."""
    projects  = set()
    n_logbook = n_agenda = n_highlights = n_notes = n_other = 0

    type_emojis = get_type_emojis()
    for _, path in status_lines:
        parts = Path(path).parts
        # Check if inside a type_dir/project_dir
        if len(parts) >= 2 and any(parts[0].startswith(e) for e in type_emojis):
            projects.add(parts[1])
        fname = Path(path).name
        if fname.endswith("-logbook.md") or fname == "logbook.md":
            n_logbook += 1
        elif fname.endswith("-agenda.md") or fname == "agenda.md":
            n_agenda += 1
        elif fname.endswith("-highlights.md") or fname == "highlights.md":
            n_highlights += 1
        elif "notes" in parts:
            n_notes += 1
        else:
            n_other += 1

    parts_msg = []
    if n_logbook:   parts_msg.append(f"{n_logbook} logbook{'s' if n_logbook>1 else ''}")
    if n_agenda:    parts_msg.append(f"{n_agenda} agenda{'s' if n_agenda>1 else ''}")
    if n_highlights: parts_msg.append(f"{n_highlights} highlights")
    if n_notes:     parts_msg.append(f"{n_notes} nota{'s' if n_notes>1 else ''}")
    if n_other:     parts_msg.append(f"{n_other} otros")

    proj_str = ""
    if projects:
        names = sorted(projects)[:3]
        proj_str = ", ".join(
            p.lstrip("🚀💻🌀📚⚙️📖🌿🔬⚗️☀️").strip() for p in names
        )
        if len(projects) > 3:
            proj_str += f" +{len(projects)-3}"

    summary = " · ".join(parts_msg) if parts_msg else "cambios varios"
    if proj_str:
        return f"orbit: {proj_str} — {summary}"
    return f"orbit: {summary}"


# ── Main command ───────────────────────────────────────────────────────────────

def run_commit(message: Optional[str] = None) -> int:
    # Stage all tracked-file changes
    _git_add_all_tracked()

    # Detect and offer to add untracked files in projects
    _prompt_untracked()

    status = _git_status()

    if not status:
        print("Sin cambios para commitear.")
        return 0

    # Show changed files
    print("\nFicheros modificados:")
    for code, path in status:
        print(f"  {code:<2}  {path}")
    print()

    # Determine commit message
    if message:
        final_msg = message
    else:
        default_msg = f"sync {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        if sys.stdin.isatty():
            try:
                raw = input(f"Mensaje del commit [Enter=\"{default_msg}\"]: ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                return 1
            final_msg = raw if raw else default_msg
        else:
            final_msg = default_msg

    print(f"Mensaje: \"{final_msg}\"")

    # Confirm
    if sys.stdin.isatty():
        try:
            ans = input("\n¿Confirmar commit? [S/n]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            return 1
        if ans not in ("", "s", "si", "sí", "y", "yes"):
            print("Commit cancelado.")
            return 0

    rc = _git_commit(final_msg)
    if rc == 0:
        print("\n✓ Commit realizado.")
    else:
        print("\n✗ Error al hacer el commit.")
    return rc


# ── Git push ──────────────────────────────────────────────────────────────────

def _can_push() -> bool:
    """Check if origin has a valid push URL (not 'no-push')."""
    try:
        result = subprocess.run(
            ["git", "remote", "get-url", "--push", "origin"],
            capture_output=True, text=True, cwd=ORBIT_DIR,
        )
        url = result.stdout.strip()
        return result.returncode == 0 and url and url != "no-push"
    except FileNotFoundError:
        return False


def _git_push() -> int:
    """Push to origin. Returns returncode. Skips if push is disabled."""
    if not _can_push():
        return 0
    try:
        result = subprocess.run(
            ["git", "push"],
            cwd=ORBIT_DIR,
            capture_output=True, text=True,
        )
        return result.returncode
    except FileNotFoundError:
        print("Error: git no encontrado")
        return 1


# ── Code update check ────────────────────────────────────────────────────────

def _code_commits_behind() -> int:
    """Fetch origin in ORBIT_CODE and return how many commits we are behind.

    Returns 0 if up-to-date, not a git repo, or on error.
    """
    from core.config import ORBIT_CODE
    code_dir = str(ORBIT_CODE)
    try:
        # Check if ORBIT_CODE is a git repo
        rc = subprocess.run(
            ["git", "rev-parse", "--git-dir"],
            capture_output=True, cwd=code_dir,
        )
        if rc.returncode != 0:
            return 0

        # Fetch silently
        rc = subprocess.run(
            ["git", "fetch", "origin", "--quiet"],
            capture_output=True, cwd=code_dir,
        )
        if rc.returncode != 0:
            return 0

        # Count commits in origin/main that are not in HEAD
        result = subprocess.run(
            ["git", "rev-list", "--count", "HEAD..origin/main"],
            capture_output=True, text=True, cwd=code_dir,
        )
        if result.returncode != 0:
            return 0
        return int(result.stdout.strip())
    except (FileNotFoundError, ValueError):
        return 0


def startup_code_update_check() -> None:
    """Check for code updates in the orbit code repo and offer to pull.

    Works in two modes:
    - Separated: ORBIT_CODE != ORBIT_HOME → check origin in ORBIT_CODE
    - Combined: ORBIT_CODE == ORBIT_HOME with 'public' remote → check public remote
    """
    from core.config import ORBIT_CODE
    code_dir = str(ORBIT_CODE)

    # Separated mode: code repo is separate from data
    if str(ORBIT_CODE) != str(ORBIT_DIR):
        behind = _code_commits_behind()
        if behind == 0:
            return

        print(f"  🔄 {behind} commit{'s' if behind != 1 else ''} nuevo{'s' if behind != 1 else ''} en orbit código")
        try:
            result = subprocess.run(
                ["git", "log", "--oneline", "HEAD..origin/main"],
                capture_output=True, text=True, cwd=code_dir,
            )
            if result.returncode == 0 and result.stdout.strip():
                for line in result.stdout.strip().splitlines()[:5]:
                    print(f"      {line}")
                if behind > 5:
                    print(f"      ... y {behind - 5} más")
        except FileNotFoundError:
            pass

        print()
        if not sys.stdin.isatty():
            return

        try:
            ans = input("  ¿Actualizar código? [S/n]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            return

        if ans not in ("", "s", "si", "sí", "y", "yes"):
            return

        try:
            result = subprocess.run(
                ["git", "pull", "origin", "main"],
                cwd=code_dir,
            )
            if result.returncode == 0:
                print("  ✓ Código actualizado.")
            else:
                print("  ⚠️  Error en pull. Actualiza manualmente: cd ~/orbit && git pull")
        except FileNotFoundError:
            pass
        return

    # Combined mode: ORBIT_CODE == ORBIT_HOME, check 'public' remote
    try:
        result = subprocess.run(
            ["git", "remote"],
            capture_output=True, text=True, cwd=ORBIT_DIR,
        )
        if "public" not in result.stdout.splitlines():
            return
    except FileNotFoundError:
        return

    try:
        subprocess.run(
            ["git", "fetch", "public", "--quiet"],
            capture_output=True, cwd=ORBIT_DIR,
        )
        result = subprocess.run(
            ["git", "rev-list", "--count", "HEAD..public/main"],
            capture_output=True, text=True, cwd=ORBIT_DIR,
        )
        if result.returncode != 0:
            return
        behind = int(result.stdout.strip())
    except (FileNotFoundError, ValueError):
        return

    if behind == 0:
        return

    print(f"  🔄 {behind} commit{'s' if behind != 1 else ''} nuevo{'s' if behind != 1 else ''} en orbit público")
    try:
        result = subprocess.run(
            ["git", "log", "--oneline", "HEAD..public/main"],
            capture_output=True, text=True, cwd=ORBIT_DIR,
        )
        if result.returncode == 0 and result.stdout.strip():
            for line in result.stdout.strip().splitlines()[:5]:
                print(f"      {line}")
            if behind > 5:
                print(f"      ... y {behind - 5} más")
    except FileNotFoundError:
        pass

    print()
    if not sys.stdin.isatty():
        return

    try:
        ans = input("  ¿Merge desde public? [S/n]: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        return

    if ans not in ("", "s", "si", "sí", "y", "yes"):
        return

    try:
        result = subprocess.run(
            ["git", "merge", "public/main", "--no-edit"],
            cwd=ORBIT_DIR,
        )
        if result.returncode == 0:
            print("  ✓ Merge desde public realizado.")
        else:
            print("  ⚠️  Error en merge. Resuelve conflictos manualmente.")
    except FileNotFoundError:
        pass


# ── Startup check ────────────────────────────────────────────────────────────

def startup_untracked_check() -> None:
    """Stage tracked files and prompt to add untracked ones.

    Called early in the startup sequence so new files are staged
    before the commit prompt.
    """
    _git_add_all_tracked()
    _prompt_untracked()


def startup_commit_offer() -> None:
    """Show uncommitted changes and offer to commit + push.

    Called after untracked check so all staged files are visible.
    """
    status = [(c, p) for c, p in _git_status() if c != "??"]
    if not status:
        return

    n = len(status)
    print(f"  📌 {n} fichero{'s' if n != 1 else ''} modificado{'s' if n != 1 else ''} sin commit")
    for code, path in status[:5]:
        print(f"      {code:<2}  {path}")
    if n > 5:
        print(f"      ... y {n - 5} más")
    print()

    default_msg = f"sync {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    can_push = _can_push()

    if not sys.stdin.isatty():
        return

    try:
        prompt = "  ¿Commit + push?" if can_push else "  ¿Commit?"
        raw = input(f"{prompt} [mensaje / Enter=\"{default_msg}\" / n]: ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return

    if raw.lower() in ("n", "no"):
        return

    msg = raw if raw else default_msg

    rc = _git_commit(msg)
    if rc != 0:
        print("  ✗ Error al hacer el commit.")
        return

    print(f"  ✓ Commit: \"{msg}\"")

    if can_push:
        rc = _git_push()
        if rc == 0:
            print("  ✓ Push realizado.")
        else:
            print("  ⚠️  Error en push (puedes hacerlo manualmente con: git push)")

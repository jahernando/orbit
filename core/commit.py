"""commit.py — git commit with auto-message and interactive confirmation.

  commit ["<message>"]

Without message: prompted interactively. Empty input → Orbit generates one.
Shows changed files and asks for confirmation before executing.
"""
import subprocess
import sys
from datetime import date
from pathlib import Path
from typing import Optional

from core.config import ORBIT_HOME as ORBIT_DIR


# ── Git helpers ────────────────────────────────────────────────────────────────

def _git_status() -> list:
    """Return list of (status_code, path) for modified/untracked tracked files."""
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
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
            ["git", "diff", "--cached", "--name-status"],
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
    """Return list of untracked file paths inside 🚀proyectos/."""
    try:
        result = subprocess.run(
            ["git", "ls-files", "--others", "--exclude-standard", "🚀proyectos/"],
            capture_output=True, text=True, cwd=ORBIT_DIR,
        )
        if result.returncode != 0:
            return []
        return [p.strip() for p in result.stdout.splitlines() if p.strip()]
    except FileNotFoundError:
        return []


def _git_add_files(files: list) -> bool:
    """Stage specific files."""
    try:
        result = subprocess.run(
            ["git", "add"] + files, cwd=ORBIT_DIR, capture_output=True,
        )
        return result.returncode == 0
    except FileNotFoundError:
        return False


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
            prompt = "  ¿Añadir? [S=todos / 1,2,... / n]: " if n > 1 else "  ¿Añadir? [S/n]: "
            ans = input(prompt).strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return

        if ans.lower() in ("n", "no"):
            return

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

    for _, path in status_lines:
        parts = Path(path).parts
        # Check if inside a project
        if len(parts) >= 2 and "proyectos" in parts[0]:
            if len(parts) >= 2:
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
        if sys.stdin.isatty():
            try:
                raw = input("Mensaje del commit (intro para auto-generar): ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                return 1
            final_msg = raw if raw else _auto_message(status)
        else:
            final_msg = _auto_message(status)

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

def _git_push() -> int:
    """Push to origin. Returns returncode."""
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


# ── Startup check ────────────────────────────────────────────────────────────

def startup_commit_check() -> None:
    """Check for uncommitted changes on shell startup.

    Shows a summary and prompts the user to commit + push.
    """
    _git_add_all_tracked()

    # Detect and offer to add untracked files in projects
    _prompt_untracked()

    status = _git_status()
    if not status:
        return

    n = len(status)
    print(f"  📌 {n} fichero{'s' if n != 1 else ''} modificado{'s' if n != 1 else ''} sin commit")
    for code, path in status[:5]:
        print(f"      {code:<2}  {path}")
    if n > 5:
        print(f"      ... y {n - 5} más")
    print()

    default_msg = f"sync {date.today().isoformat()}"

    if not sys.stdin.isatty():
        return

    try:
        raw = input(f"  ¿Commit + push? [mensaje / Enter=\"{default_msg}\" / n]: ").strip()
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

    rc = _git_push()
    if rc == 0:
        print("  ✓ Push realizado.")
    else:
        print("  ⚠️  Error en push (puedes hacerlo manualmente con: git push)")

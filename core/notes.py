"""notes.py — note commands for new-format projects.

  note <project> "<title>" [<file>]   create note (or import existing .md)
  note list <project>                 list notes with git status
  note drop <project> [<file>]        delete note (interactive)
"""
import re
import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path
from typing import Optional

from core.project import _find_new_project
from core.log import add_orbit_entry
from core.open import open_file

from core.config import ORBIT_HOME, TEMPLATES_DIR, normalize as _normalize


# ── Filename helpers ───────────────────────────────────────────────────────────

def _title_to_filename(title: str) -> str:
    """Convert a note title to a safe filename: lowercase, spaces→underscore, no accents."""
    text = _normalize(title)
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s]+", "_", text).strip("_")
    return f"{text}.md"


def _note_template(title: str, project_name: str) -> str:
    today = date.today().isoformat()
    tpl = TEMPLATES_DIR / "note.md"
    if tpl.exists():
        return (tpl.read_text()
                .replace("TÍTULO", title)
                .replace("YYYY-MM-DD", today)
                .replace("PROYECTO", project_name))
    return f"# {title}\n\n*{today} — {project_name}*\n\n---\n\n"


# ── Git status helper ─────────────────────────────────────────────────────────

def _git_tracked(path: Path) -> Optional[bool]:
    """Return True if path is tracked by git, False if untracked, None on error."""
    try:
        result = subprocess.run(
            ["git", "ls-files", "--error-unmatch", str(path)],
            capture_output=True, cwd=ORBIT_HOME,
        )
        return result.returncode == 0
    except FileNotFoundError:
        return None


def _git_add_file(path: Path) -> bool:
    try:
        result = subprocess.run(
            ["git", "add", str(path)],
            capture_output=True, cwd=ORBIT_HOME,
        )
        return result.returncode == 0
    except FileNotFoundError:
        return False


# ── Interactive note picker ────────────────────────────────────────────────────

def _pick_note(notes_dir: Path, text: Optional[str]) -> Optional[Path]:
    """Return a note path by partial name match or interactive selection."""
    notes = sorted(notes_dir.glob("*.md"))
    if not notes:
        print("No hay notas en este proyecto.")
        return None

    if text:
        matches = [n for n in notes if text.lower() in n.name.lower()]
        if not matches:
            print(f"Error: nota '{text}' no encontrada.")
            return None
        if len(matches) > 1:
            print(f"Ambiguo: {', '.join(n.name for n in matches)}")
            return None
        return matches[0]

    print("\nNotas:")
    for i, n in enumerate(notes, 1):
        tracked = _git_tracked(n)
        mark = "✓" if tracked else ("✗" if tracked is False else "?")
        print(f"  {i:2}. [{mark}] {n.name}")
    print()

    if not sys.stdin.isatty():
        return None

    try:
        raw = input("Selecciona (número o nombre parcial): ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return None

    if not raw:
        return None
    if raw.isdigit():
        idx = int(raw) - 1
        if 0 <= idx < len(notes):
            return notes[idx]
        print(f"Fuera de rango (1–{len(notes)})")
        return None
    matches = [n for n in notes if raw.lower() in n.name.lower()]
    if not matches:
        print(f"Sin coincidencias para '{raw}'")
        return None
    if len(matches) > 1:
        print(f"Ambiguo: {len(matches)} coincidencias")
        return None
    return matches[0]


# ── Commands ──────────────────────────────────────────────────────────────────

def run_note_create(project: str, title: str, file_str: Optional[str] = None,
                    open_after: bool = True, editor: str = "") -> int:
    """Create a new note or import an existing .md into project notes/."""
    project_dir = _find_new_project(project)
    if project_dir is None:
        return 1

    notes_dir = project_dir / "notes"
    notes_dir.mkdir(exist_ok=True)

    if file_str:
        src = Path(file_str).expanduser().resolve()
        if not src.exists():
            print(f"Error: fichero no encontrado: {src}")
            return 1
        if src.suffix.lower() != ".md":
            print(f"Error: solo se pueden importar ficheros .md (recibido: {src.name})")
            return 1
        dest = notes_dir / src.name
        shutil.copy2(src, dest)
        note_name = dest.name
        print(f"✓ [{project_dir.name}] Nota importada: {note_name}")
    else:
        note_name = _title_to_filename(title)
        dest      = notes_dir / note_name
        if dest.exists():
            print(f"⚠️  La nota ya existe: {note_name} (se sobreescribirá)")
        dest.write_text(_note_template(title, project_dir.name))
        print(f"✓ [{project_dir.name}] Nota creada: {note_name}")

    # Ask about git tracking
    if sys.stdin.isatty():
        try:
            ans = input(f"¿Añadir {note_name} a git? [S/n]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            ans = "n"
        if ans in ("", "s", "si", "sí", "y", "yes"):
            if _git_add_file(dest):
                print(f"  ✓ git add {note_name}")
            else:
                print(f"  ⚠️  No se pudo añadir a git")

    add_orbit_entry(project_dir,
                    f"[nota creada] {note_name} — \"{title}\"", "apunte")

    if open_after:
        open_file(dest, editor)
    return 0


def run_note_list(project: str) -> int:
    """List notes in project notes/ with git tracking status."""
    project_dir = _find_new_project(project)
    if project_dir is None:
        return 1

    notes_dir = project_dir / "notes"
    if not notes_dir.exists():
        print(f"[{project_dir.name}] no tiene directorio notes/")
        return 0

    notes = sorted(notes_dir.glob("*.md"))
    if not notes:
        print(f"[{project_dir.name}/notes/] — sin notas")
        return 0

    print(f"\nNotas — {project_dir.name}/notes/:")
    for note in notes:
        tracked = _git_tracked(note)
        mark = "✓ git" if tracked else ("✗ git" if tracked is False else "? git")
        print(f"  {mark}   {note.name}")
    print()
    return 0


def run_note_drop(project: str, file_str: Optional[str] = None,
                  force: bool = False) -> int:
    """Delete a note from project notes/ (interactive if no file given)."""
    import sys
    project_dir = _find_new_project(project)
    if project_dir is None:
        return 1

    notes_dir = project_dir / "notes"
    note_path = _pick_note(notes_dir, file_str)
    if note_path is None:
        return 1

    note_name = note_path.name
    # Read title from first # line
    title = note_name
    for line in note_path.read_text().splitlines():
        if line.startswith("# "):
            title = line[2:].strip()
            break

    if not force:
        if not sys.stdin.isatty():
            print("Error: usa --force para confirmar el borrado en modo no interactivo.")
            return 1
        try:
            ans = input(f"¿Seguro que quieres eliminar \"{note_name}\"? [s/N]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            return 1
        if ans not in ("s", "si", "sí", "y", "yes"):
            print("Cancelado.")
            return 0

    note_path.unlink()
    print(f"✓ [{project_dir.name}] Nota borrada: {note_name}")
    add_orbit_entry(project_dir,
                    f"[nota borrada] {note_name} — \"{title}\"", "apunte")
    return 0

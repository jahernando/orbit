"""inbox.py — process inbox.md files from cloud.

Each project can have a cloud/inbox.md for quick captures from mobile.
There is also a global inbox.md at cloud_root/ for entries without project.

Inbox format (one entry per line):
  - tarea: preparar presentación APPEC --date 2026-03-20
  - idea: usar ML para calibración de PMTs
  - nota: reunión con Diego, decidimos cambiar approach
  - apunte: referencia al paper de García 2024

Dispatch rules:
  - tarea  → task add <project> <text> [--date ...]
  - idea   → log <project> <text> --entry idea
  - nota   → creates/appends to a note in notes/
  - Other valid log types (apunte, referencia, problema, solucion,
    resultado, decision, evaluacion) → log <project> <text> --entry <type>

Lines that don't match the format are left in the inbox.
"""

import re
import shutil
import sys
from datetime import date
from pathlib import Path
from typing import Optional

from core.config import ORBIT_HOME, iter_project_dirs
from core.deliver import _find_cloud_root, _project_cloud_dir, CLOUD_SUBDIR
from core.log import VALID_TYPES as LOG_TYPES


_TASK_TYPE = "tarea"
_NOTE_TYPE = "nota"

# Pattern: "- tipo: texto" with optional flags
_ENTRY_RE = re.compile(r"^-\s+(\w+):\s+(.+)$")

# Flags inside entry text
_DATE_RE = re.compile(r"\s+--date\s+(\S+)")


def _find_project_inboxes() -> list:
    """Find all non-empty inbox.md files in cloud project dirs.

    Returns list of (project_dir, inbox_path, entries) tuples.
    """
    cloud_root = _find_cloud_root()
    if not cloud_root:
        return []

    results = []
    for project_dir in iter_project_dirs():
        cloud_dir = _project_cloud_dir(project_dir, cloud_root)
        if not cloud_dir:
            continue
        inbox = cloud_dir / "inbox.txt"
        if not inbox.exists():
            # Fallback to legacy inbox.md
            inbox = cloud_dir / "inbox.md"
        if not inbox.exists():
            continue
        text = inbox.read_text().strip()
        if not text:
            continue
        results.append((project_dir, inbox, text))

    return results


def _find_global_inbox() -> Optional[tuple]:
    """Find the global inbox.md at cloud_root/.

    Returns (inbox_path, text) or None.
    """
    cloud_root = _find_cloud_root()
    if not cloud_root:
        return None
    inbox = cloud_root / "inbox.txt"
    if not inbox.exists():
        inbox = cloud_root / "inbox.md"
    if not inbox.exists():
        return None
    text = inbox.read_text().strip()
    if not text:
        return None
    return (inbox, text)


def _parse_entries(text: str) -> list:
    """Parse inbox lines into structured entries.

    Returns list of dicts: {type, text, date, raw_line}
    Unparseable lines get type=None.
    """
    entries = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        m = _ENTRY_RE.match(line)
        if not m:
            entries.append({"type": None, "text": line, "date": None, "raw_line": line})
            continue

        tipo = m.group(1).lower()
        body = m.group(2).strip()

        # Extract --date flag
        date_val = None
        dm = _DATE_RE.search(body)
        if dm:
            date_val = dm.group(1)
            body = body[:dm.start()] + body[dm.end():]
            body = body.strip()

        entries.append({"type": tipo, "text": body, "date": date_val, "raw_line": line})

    return entries


def _dispatch_entry(entry: dict, project: str) -> bool:
    """Dispatch a single inbox entry to the right orbit command.

    Returns True if successfully dispatched, False if skipped.
    """
    tipo = entry["type"]
    text = entry["text"]
    date_val = entry["date"]

    if tipo == _TASK_TYPE:
        from core.agenda_cmds import run_task_add
        rc = run_task_add(project=project, text=text, date_val=date_val)
        return rc == 0

    if tipo == _NOTE_TYPE:
        # Append to today's note
        from core.log import find_project, project_file_path
        project_dir = find_project(project)
        if not project_dir:
            return False
        notes_dir = project_dir / "notes"
        notes_dir.mkdir(exist_ok=True)
        note_path = notes_dir / f"{date.today().isoformat()}.md"
        if note_path.exists():
            with open(note_path, "a") as f:
                f.write(f"\n{text}\n")
        else:
            note_path.write_text(f"# {date.today().isoformat()}\n\n{text}\n")
        print(f"  ✓ [{project}] nota → {note_path.name}")
        return True

    if tipo in LOG_TYPES:
        from core.log import add_entry
        rc = add_entry(project=project, message=text, tipo=tipo,
                       path=None, fecha=None)
        return rc == 0

    return False


def _clear_inbox(inbox_path: Path, remaining_lines: list) -> None:
    """Rewrite inbox with only unparsed lines, or delete if empty."""
    if remaining_lines:
        inbox_path.write_text("\n".join(remaining_lines) + "\n")
    else:
        inbox_path.write_text("")


def _process_project_inbox(project_dir: Path, inbox_path: Path,
                           text: str) -> int:
    """Process a single project's inbox. Returns number of entries dispatched."""
    from core.log import _base_name
    project_name = _base_name(project_dir)

    entries = _parse_entries(text)
    dispatched = 0
    remaining = []

    for entry in entries:
        if entry["type"] is None:
            remaining.append(entry["raw_line"])
            continue
        if _dispatch_entry(entry, project_name):
            dispatched += 1
        else:
            remaining.append(entry["raw_line"])

    _clear_inbox(inbox_path, remaining)
    return dispatched


def _copy_inbox_to_repo(inbox_path: Path, project_dir: Path) -> None:
    """Copy inbox.md to the project's cloud/ dir in the repo (for local reference)."""
    local_inbox = project_dir / CLOUD_SUBDIR / "inbox.md"
    if local_inbox.parent.exists() or local_inbox.parent.is_symlink():
        # The symlink points to cloud, so this is redundant — skip
        return


def check_inboxes() -> int:
    """Check all inboxes and report. Returns total number of entries found."""
    project_inboxes = _find_project_inboxes()
    global_inbox = _find_global_inbox()

    total = 0
    if project_inboxes:
        for project_dir, inbox_path, text in project_inboxes:
            entries = _parse_entries(text)
            total += len(entries)
    if global_inbox:
        _, text = global_inbox
        entries = _parse_entries(text)
        total += len(entries)

    return total


def process_inboxes() -> int:
    """Process all inbox files. Returns total entries dispatched."""
    project_inboxes = _find_project_inboxes()
    global_inbox = _find_global_inbox()

    total = 0

    for project_dir, inbox_path, text in project_inboxes:
        from core.log import _base_name
        n = _process_project_inbox(project_dir, inbox_path, text)
        if n > 0:
            total += n

    if global_inbox:
        inbox_path, text = global_inbox
        entries = _parse_entries(text)
        n = len(entries)
        if n > 0:
            # Copy to repo-level inbox.md for manual processing
            local = ORBIT_HOME / "inbox.md"
            local.write_text(text + "\n")
            print(f"  📬 {n} entrada{'s' if n != 1 else ''} en buzón general → inbox.md")
            _clear_inbox(inbox_path, [])
            total += n

    return total


def startup_inbox_check() -> None:
    """Check inboxes at shell startup and offer to process."""
    project_inboxes = _find_project_inboxes()
    global_inbox = _find_global_inbox()

    if not project_inboxes and not global_inbox:
        return

    # Show summary
    print("  📬 Buzones con contenido:")
    total = 0
    for project_dir, inbox_path, text in project_inboxes:
        from core.log import _base_name
        entries = _parse_entries(text)
        n = len(entries)
        total += n
        print(f"      {_base_name(project_dir)}: {n} entrada{'s' if n != 1 else ''}")

    if global_inbox:
        _, text = global_inbox
        entries = _parse_entries(text)
        n = len(entries)
        total += n
        print(f"      (general): {n} entrada{'s' if n != 1 else ''}")

    print()

    if not sys.stdin.isatty():
        return

    try:
        ans = input(f"  ¿Procesar {total} entrada{'s' if total != 1 else ''}? [S/n]: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        return

    if ans not in ("", "s", "si", "sí", "y", "yes"):
        return

    n = process_inboxes()
    if n > 0:
        print(f"\n  ✅ {n} entrada{'s' if n != 1 else ''} procesada{'s' if n != 1 else ''}.")
    print()

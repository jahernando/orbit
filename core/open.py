"""orbit open — open a note in an external editor or renderer."""

import io
import subprocess
import sys
from contextlib import contextmanager
from datetime import date
from pathlib import Path

from core.log import find_project, resolve_file, format_entry, _append_entry, init_logbook


EDITORS = {
    "typora": ["open", "-a", "Typora"],
    "glow":   ["glow"],
    "code":   ["code"],
}


def open_file(path: Path, editor: str) -> int:
    """Open a file in the given editor. Returns 0 on success."""
    cmd_base = EDITORS.get(editor)
    if cmd_base:
        cmd = cmd_base + [str(path)]
    else:
        # fallback: treat editor as a raw command
        cmd = [editor, str(path)]

    # glow runs in the foreground (terminal renderer); others launch a GUI app
    foreground = editor == "glow" or editor not in EDITORS
    try:
        if foreground:
            result = subprocess.run(cmd)
            return result.returncode
        else:
            subprocess.Popen(cmd)
            return 0
    except FileNotFoundError:
        print(f"Error: editor '{editor}' no encontrado. ¿Está instalado?")
        return 1


ORBIT_DIR = Path(__file__).parent.parent
CMD_MD    = ORBIT_DIR / "cmd.md"


@contextmanager
def capture_output():
    """Context manager that captures stdout into a string buffer."""
    buf = io.StringIO()
    old = sys.stdout
    sys.stdout = buf
    try:
        yield buf
    finally:
        sys.stdout = old


def open_cmd_output(content: str, editor: str = "typora") -> None:
    """Write content to cmd.md and open it in the editor."""
    CMD_MD.write_text(content)
    open_file(CMD_MD, editor)


def log_cmd_output(content: str, project: str, entry_type: str = "apunte",
                   cmd_label: str = "") -> int:
    """Log captured command output as a logbook entry in the given project."""
    project_dir = find_project(project)
    if not project_dir:
        return 1

    logbook = resolve_file(project_dir, "logbook")
    if not logbook.exists():
        init_logbook(logbook, project_dir.name)

    # Build summary line
    lines = [l for l in content.strip().splitlines() if l.strip()]
    n = len(lines)
    label = cmd_label or "output"
    summary = f"[{label}] {n} líneas"

    # Entry: summary line + code block with content
    date_str = date.today().isoformat()
    from core.log import TAG_EMOJI
    emoji = TAG_EMOJI.get(entry_type, "")
    block = content.strip()
    entry = f"{date_str} {emoji} {summary} #{entry_type} [O]\n\n```\n{block}\n```\n"
    _append_entry(logbook, entry)
    print(f"✓ [{project_dir.name}] {summary} #{entry_type}")
    return 0

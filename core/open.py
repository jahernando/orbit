"""orbit open — open a note in an external editor or renderer."""

import io
import os
import platform
import subprocess
import sys
from contextlib import contextmanager
from datetime import date
from pathlib import Path

from core.log import find_project, resolve_file, _append_entry, init_logbook

EDITORS = {
    "typora":   ["open", "-a", "Typora"],
    "obsidian": ["open", "-a", "Obsidian"],
    "glow":     ["glow"],
    "code":     ["code"],
}

# Foreground editors (terminal renderers) — block until exit
_FOREGROUND = {"glow"}


def default_editor() -> str:
    """Return the default editor from ORBIT_EDITOR env var, or system opener."""
    env = os.environ.get("ORBIT_EDITOR", "").strip()
    if env:
        return env
    # System default: 'open' on macOS, 'xdg-open' on Linux
    return "open" if platform.system() == "Darwin" else "xdg-open"


def open_file(path: Path, editor: str = "") -> int:
    """Open a file in the given editor. Returns 0 on success."""
    if not editor:
        editor = default_editor()

    cmd_base = EDITORS.get(editor)
    if cmd_base:
        cmd = cmd_base + [str(path)]
    elif editor == "open":
        cmd = ["open", str(path)]
    else:
        cmd = [editor, str(path)]

    foreground = editor in _FOREGROUND or editor not in EDITORS
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


from core.config import ORBIT_HOME, CMD_MD


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


def open_cmd_output(content: str, editor: str = "") -> None:
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

    # Entry: summary line + content block
    date_str = date.today().isoformat()
    from core.log import TAG_EMOJI
    emoji = TAG_EMOJI.get(entry_type, "")
    block = content.strip()

    # If content contains markdown tables, insert as-is so renderers
    # (e.g. Typora) display them properly; otherwise wrap in code block.
    has_md_table = any(l.startswith("|") for l in block.splitlines())
    if has_md_table:
        entry = f"{date_str} {emoji} {summary} #{entry_type} [O]\n\n{block}\n\n"
    else:
        entry = f"{date_str} {emoji} {summary} #{entry_type} [O]\n\n```\n{block}\n```\n"
    _append_entry(logbook, entry)
    print(f"✓ [{project_dir.name}] {summary} #{entry_type}")
    return 0

"""core/undo.py — undo stack for reversing the last user operation.

The stack stores file snapshots (path → content) before each mutating
command.  On ``undo`` the most recent snapshot is restored.

Usage from other modules::

    from core.undo import save_snapshot
    save_snapshot(path)          # before writing to *path*

    from core.undo import run_undo
    run_undo()                   # restores the last operation
"""

from pathlib import Path
from typing import Optional

# Each entry is a dict  {Path: str|None}
# str  = previous file content (restore on undo)
# None = file did not exist   (delete on undo)
_stack: list[dict[Path, Optional[str]]] = []

# Files saved within the current operation (before commit)
_current: dict[Path, Optional[str]] = {}

MAX_STACK = 20


# ── Recording ────────────────────────────────────────────────────────────────

def save_snapshot(path: Path) -> None:
    """Save the current content of *path* into the pending operation.

    Call this **before** writing to the file.  Multiple calls for the
    same path within one operation keep only the first (= the original
    state).
    """
    path = Path(path).resolve()
    if path in _current:
        return  # already captured for this operation
    if path.exists():
        _current[path] = path.read_text()
    else:
        _current[path] = None


def commit_operation(label: str = "") -> None:
    """Seal the current pending snapshots as one undoable operation.

    Called automatically after each shell command.
    """
    global _current
    if not _current:
        return
    entry = dict(_current)
    entry["__label__"] = label  # type: ignore[assignment]
    _stack.append(entry)
    if len(_stack) > MAX_STACK:
        _stack.pop(0)
    _current = {}


def discard_operation() -> None:
    """Drop pending snapshots without committing (e.g. command failed)."""
    global _current
    _current = {}


# ── Undo ──────────────────────────────────────────────────────────────────────

def run_undo() -> int:
    """Undo the last operation by restoring saved file states."""
    if not _stack:
        print("No hay nada que deshacer.")
        return 0

    entry = _stack.pop()
    label = entry.pop("__label__", "")  # type: ignore[arg-type]
    restored = 0

    for path, content in entry.items():
        path = Path(path)
        if content is None:
            # File didn't exist before — remove it
            if path.exists():
                path.unlink()
                print(f"  ✗ eliminado: {path.name}")
                restored += 1
        else:
            # Restore previous content
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
            print(f"  ↩ restaurado: {path.name}")
            restored += 1

    if restored:
        what = f" ({label})" if label else ""
        print(f"✓ Undo{what}: {restored} fichero{'s' if restored != 1 else ''} restaurado{'s' if restored != 1 else ''}.")
    else:
        print("Nada que restaurar.")
    return 0


def can_undo() -> bool:
    """Return True if there is at least one operation to undo."""
    return bool(_stack)


def peek_label() -> str:
    """Return the label of the last undoable operation, or empty string."""
    if not _stack:
        return ""
    return _stack[-1].get("__label__", "")  # type: ignore[return-value]


def clear() -> None:
    """Clear the entire undo stack (e.g. on shell exit)."""
    _stack.clear()
    _current.clear()

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

def _file_count(entry: dict) -> int:
    """Number of file snapshots in an entry (excluding __label__)."""
    return sum(1 for k in entry if k != "__label__")


def _restore_entry(entry: dict) -> int:
    """Restore a single stack entry. Returns number of files restored."""
    label = entry.pop("__label__", "")  # type: ignore[arg-type]
    restored = 0
    for path, content in entry.items():
        path = Path(path)
        if content is None:
            if path.exists():
                path.unlink()
                print(f"  ✗ eliminado: {path.name}")
                restored += 1
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
            print(f"  ↩ restaurado: {path.name}")
            restored += 1
    return restored


def run_undo(choice: Optional[int] = None) -> int:
    """Undo operations interactively.

    If *choice* is given (1-based, most recent first), skip the interactive
    prompt and undo the top *choice* operations.  This is handy for tests.
    """
    if not _stack:
        print("No hay nada que deshacer.")
        return 0

    # --- show the stack ---
    print("Operaciones deshacibles (más reciente primero):\n")
    for i, entry in enumerate(reversed(_stack), 1):
        label = entry.get("__label__", "") or "sin etiqueta"
        nfiles = _file_count(entry)
        print(f"  {i}. {label}  ({nfiles} fichero{'s' if nfiles != 1 else ''})")
    print()

    # --- get user choice ---
    if choice is None:
        try:
            raw = input("¿Deshacer hasta cuál? [1 = última] (0 para cancelar): ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nCancelado.")
            return 0
        if not raw:
            choice = 1
        else:
            try:
                choice = int(raw)
            except ValueError:
                print("Valor no válido.")
                return 1
    if choice <= 0:
        print("Cancelado.")
        return 0
    if choice > len(_stack):
        print(f"Solo hay {len(_stack)} operación{'es' if len(_stack) != 1 else ''} en la pila.")
        return 1

    # --- undo top `choice` entries ---
    total_restored = 0
    for n in range(choice):
        entry = _stack.pop()
        label = entry.get("__label__", "")
        restored = _restore_entry(entry)
        total_restored += restored

    if total_restored:
        ops = f"{choice} operación{'es' if choice != 1 else ''}"
        print(f"✓ Undo: {ops}, {total_restored} fichero{'s' if total_restored != 1 else ''} restaurado{'s' if total_restored != 1 else ''}.")
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

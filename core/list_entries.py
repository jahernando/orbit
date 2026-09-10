from pathlib import Path
from typing import Optional

from core.log import PROJECTS_DIR, VALID_TYPES, TAG_EMOJI  # noqa: F401 (PROJECTS_DIR used via monkeypatch in tests)

TYPE_EMOJI = TAG_EMOJI  # backward-compatible alias


def parse_entry_type(line: str) -> Optional[str]:
    """Return the #tipo tag from a logbook line, or None."""
    # Strip [O] marker before checking
    s = line.strip().removesuffix(" [O]")
    for tipo in VALID_TYPES:
        if s.endswith(f"#{tipo}"):
            return tipo
    return None


def _entry_in_period(line: str, fecha: Optional[str],
                     period_from: Optional[str], period_to: Optional[str]) -> bool:
    """Return True if the entry line's date matches the given filters."""
    if not fecha and not period_from and not period_to:
        return True
    if len(line) < 10 or not line[:4].isdigit() or line[4] != "-":
        return False
    entry_date = line[:10]
    if fecha:
        return entry_date.startswith(fecha)
    if period_from and entry_date < period_from:
        return False
    if period_to and entry_date > period_to:
        return False
    return True


def _entries_for(
    project_dir: Path,
    tipos: Optional[list],
    fecha: Optional[str],
    period_from: Optional[str] = None,
    period_to:   Optional[str] = None,
) -> Optional[list]:
    """Entradas del logbook de un proyecto tras aplicar los filtros.

    Devuelve None si el proyecto no tiene logbook (distinto de tenerlo vacío).
    """
    from core.log import find_logbook_file

    logbook_path = find_logbook_file(project_dir)
    if not logbook_path or not logbook_path.exists():
        return None

    lines = logbook_path.read_text().splitlines()

    # Filter only entry lines (start with a date YYYY-MM-DD)
    entries = [l for l in lines if len(l) >= 10 and l[:4].isdigit() and l[4] == "-"]

    if tipos:
        entries = [e for e in entries if parse_entry_type(e) in tipos]
    return [e for e in entries
            if _entry_in_period(e, fecha, period_from, period_to)]


def _block(
    project_dir: Path,
    entries: list,
    tipos: Optional[list],
    fecha: Optional[str],
    period_from: Optional[str] = None,
    period_to:   Optional[str] = None,
) -> str:
    """Cabecera + separador + entradas, listo para imprimir."""
    header = f"[{project_dir.name}]"
    if tipos:
        emojis = " ".join(TYPE_EMOJI.get(t, f"#{t}") for t in tipos)
        header += f" {emojis}"
    if fecha:
        header += f" {fecha}"
    elif period_from or period_to:
        rng = f"{period_from or '…'} → {period_to or '…'}"
        header += f" {rng}"
    header += f" — {len(entries)} entrada{'s' if len(entries) != 1 else ''}"

    separator = "─" * len(header)
    return "\n".join([header, separator] + entries) + "\n"


def run_ls_log(
    project: Optional[str] = None,
    tipos: Optional[list] = None,
    fecha: Optional[str] = None,
    period_from: Optional[str] = None,
    period_to:   Optional[str] = None,
) -> int:
    """`orbit ls log [P]` — entradas del logbook, en terminal.

    Sin proyecto recorre el workspace, como el resto de la familia `ls`, y
    salta los proyectos sin entradas que casen con los filtros.
    """
    from core.ls import collect_project_dirs

    if project:
        dirs = collect_project_dirs(project)
        if not dirs:
            return 1
        entries = _entries_for(dirs[0], tipos, fecha, period_from, period_to)
        if entries is None:
            print(f"No logbook found for '{dirs[0].name}'")
            return 1
        print(_block(dirs[0], entries, tipos, fecha, period_from, period_to))
        return 0

    shown = 0
    for project_dir in collect_project_dirs():
        entries = _entries_for(project_dir, tipos, fecha, period_from, period_to)
        if not entries:
            continue
        print(_block(project_dir, entries, tipos, fecha, period_from, period_to))
        shown += 1
    if not shown:
        print("No hay entradas.")
    return 0


def list_entries(
    project: str,
    tipos: Optional[list],
    fecha: Optional[str],
    output: Optional[str],
    period_from: Optional[str] = None,
    period_to:   Optional[str] = None,
) -> int:
    from core.log import find_project

    project_dir = find_project(project)
    if not project_dir:
        return 1

    entries = _entries_for(project_dir, tipos, fecha, period_from, period_to)
    if entries is None:
        print(f"No logbook found for '{project_dir.name}'")
        return 1

    text = _block(project_dir, entries, tipos, fecha, period_from, period_to)

    if output:
        Path(output).write_text(text)
        print(f"✓ Saved to {output}")
    else:
        print(text)

    return 0

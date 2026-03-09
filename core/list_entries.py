from pathlib import Path
from typing import Optional

from core.log import PROJECTS_DIR, VALID_TYPES, TAG_EMOJI

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


def list_entries(
    project: str,
    tipos: Optional[list],
    fecha: Optional[str],
    output: Optional[str],
    period_from: Optional[str] = None,
    period_to:   Optional[str] = None,
) -> int:
    from core.log import find_project, find_logbook_file

    project_dir = find_project(project)
    if not project_dir:
        return 1

    logbook_path = find_logbook_file(project_dir)
    if not logbook_path or not logbook_path.exists():
        print(f"No logbook found for '{project_dir.name}'")
        return 1

    lines = logbook_path.read_text().splitlines()

    # Filter only entry lines (start with a date YYYY-MM-DD)
    entries = [l for l in lines if len(l) >= 10 and l[:4].isdigit() and l[4] == "-"]

    # Apply filters
    if tipos:
        entries = [e for e in entries if parse_entry_type(e) in tipos]
    entries = [e for e in entries
               if _entry_in_period(e, fecha, period_from, period_to)]

    # Build output
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
    lines_out = [header, separator] + entries

    text = "\n".join(lines_out) + "\n"

    if output:
        Path(output).write_text(text)
        print(f"✓ Saved to {output}")
    else:
        print(text)

    return 0

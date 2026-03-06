from pathlib import Path
from typing import Optional

from core.log import PROJECTS_DIR, VALID_TYPES

TYPE_EMOJI = {
    "idea":       "💡",
    "referencia": "📎",
    "tarea":      "✅",
    "problema":   "⚠️",
    "resultado":  "📊",
    "apunte":     "📝",
    "decision":   "🔀",
}


def parse_entry_type(line: str) -> Optional[str]:
    for tipo in VALID_TYPES:
        if line.strip().endswith(f"#{tipo}"):
            return tipo
    return None


def entry_matches_fecha(line: str, fecha: Optional[str]) -> bool:
    if not fecha:
        return True
    # line starts with YYYY-MM-DD
    return line.startswith(fecha)


def list_entries(
    project: str,
    tipos: Optional[list],
    fecha: Optional[str],
    output: Optional[str],
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
    if fecha:
        entries = [e for e in entries if entry_matches_fecha(e, fecha)]

    # Build output
    header = f"[{project_dir.name}]"
    if tipos:
        emojis = " ".join(TYPE_EMOJI.get(t, f"#{t}") for t in tipos)
        header += f" {emojis}"
    if fecha:
        header += f" {fecha}"
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

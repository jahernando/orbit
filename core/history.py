"""history.py — command history log for Orbit.

Appends a timestamped line to history.md for each state-changing command.
Read-only commands (agenda, report, view, ls, doctor, search, help) are skipped.

  orbit history                         # today
  orbit history --date 2026-03-11       # specific day
  orbit history --from monday --to friday  # range
  orbit history --open                  # open in editor
"""

from datetime import date, datetime
from pathlib import Path
from typing import Optional

from core.config import HISTORY_MD

# Commands that only read — never logged
_SKIP = frozenset({
    "agenda", "report", "view", "ls", "doctor", "search",
    "help", "shell", "history", "open", "claude",
})


def log_history(argv: list) -> None:
    """Append a command line to history.md.  Called from main dispatch."""
    if not argv:
        return
    cmd = argv[0] if argv else ""
    if cmd in _SKIP:
        return
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    line = " ".join(argv)
    with open(HISTORY_MD, "a") as f:
        f.write(f"{ts} {line}\n")


def run_history(
    date_str: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
) -> int:
    """Print history entries filtered by date range."""
    if not HISTORY_MD.exists():
        print("Sin historial.")
        return 0

    today = date.today()

    # Determine period
    if date_from or date_to:
        start = date.fromisoformat(date_from) if date_from else today
        end = date.fromisoformat(date_to) if date_to else today
    elif date_str:
        if len(date_str) == 7:  # YYYY-MM
            y, m = int(date_str[:4]), int(date_str[5:7])
            import calendar
            start = date(y, m, 1)
            end = date(y, m, calendar.monthrange(y, m)[1])
        elif "W" in date_str:  # YYYY-Wnn
            y, w = int(date_str[:4]), int(date_str.split("W")[1])
            start = date.fromisocalendar(y, w, 1)
            end = date.fromisocalendar(y, w, 7)
        else:
            d = date.fromisoformat(date_str)
            start = end = d
    else:
        start = end = today

    lines = HISTORY_MD.read_text().splitlines()
    filtered = []
    for line in lines:
        # Lines: "YYYY-MM-DD HH:MM command..."
        if len(line) < 10:
            continue
        try:
            d = date.fromisoformat(line[:10])
        except ValueError:
            continue
        if start <= d <= end:
            filtered.append(line)

    if not filtered:
        if start == end:
            print(f"Sin historial para {start.isoformat()}.")
        else:
            print(f"Sin historial para {start.isoformat()} → {end.isoformat()}.")
        return 0

    # Header
    if start == end:
        header = f"HISTORIAL — {start.isoformat()}"
        if start == today:
            header += " (hoy)"
    else:
        days = (end - start).days + 1
        header = f"HISTORIAL — {start.isoformat()} → {end.isoformat()}  ({days}d)"

    print(header)
    print("─" * 56)
    for line in filtered:
        print(f"  {line}")
    print("─" * 56)
    print(f"{len(filtered)} entrada{'s' if len(filtered) != 1 else ''}")

    return 0

"""Strip ☁️ marker from every agenda.md / *-agenda.md in ORBIT_HOME.

The ☁️ marker became inert in v0.33 (AppleScript-write retired). The
parser/formatter ignore it from that version on, so existing markers
will disappear naturally the next time orbit re-writes each file. This
script forces the rewrite in one pass so you don't see the symbol
lingering until the next edit per cita.

Usage:
    ORBIT_HOME=~/🚀orbit-ws python scripts/strip_cloud_marker.py
    ORBIT_HOME=~/🌿orbit-ps python scripts/strip_cloud_marker.py [--dry-run]

Idempotent — safe to run multiple times.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Allow `python scripts/strip_cloud_marker.py` from anywhere.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.agenda_cmds import _read_agenda, _write_agenda   # noqa: E402
from core.config import iter_project_dirs                  # noqa: E402
from core.log import resolve_file                          # noqa: E402


def main() -> int:
    dry_run = "--dry-run" in sys.argv
    touched = 0
    scanned = 0
    for project_dir in iter_project_dirs():
        path = resolve_file(project_dir, "agenda")
        if not path.exists():
            continue
        scanned += 1
        text = path.read_text()
        if "☁️" not in text:
            continue
        # Round-trip through parser+formatter; the v0.33 formatter
        # drops ☁️ regardless of cloud_verified value.
        data = _read_agenda(path)
        if dry_run:
            print(f"  would strip: {path}")
        else:
            _write_agenda(path, data)
            print(f"  stripped:    {path}")
        touched += 1
    suffix = " (dry-run)" if dry_run else ""
    print(f"\n{touched}/{scanned} agendas con ☁️{suffix}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

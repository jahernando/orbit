#!/usr/bin/env python3
"""Diagnose why a task/ms/reminder isn't propagating to Calendar.app.

Usage (from any directory; ORBIT_HOME must be set in the env or come from
``orbit.json`` discovered in the cwd):

    python3 scripts/diagnose_calendar_sync.py <orbit-id> [<uid>]

Example:

    python3 scripts/diagnose_calendar_sync.py af50f3bd 22F53512-3EAD-4EEB-B4CE-88CE9B4B2BE3

What it does:
  1. Loads ``calendar-sync.json`` and reports the agenda calendar name.
  2. Lists every calendar present in Calendar.app.
  3. Searches every calendar for an event whose description contains
     ``[orbit:<id>``  (prefix, matches both ``[orbit:id]`` and
     ``[orbit:id@date]``).
  4. (Optional) If a uid is also given, searches every calendar for the
     event with that uid.

Output is plain text — copy/paste the result back to Claude.
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(2)

    orbit_id = sys.argv[1].strip()
    uid = sys.argv[2].strip() if len(sys.argv) >= 3 else None

    from core.gsync import (
        _load_config, _agenda_calendar_name, _list_calendar_app_calendars,
        _esc, _osa,
    )

    config = _load_config()
    agenda_cal = _agenda_calendar_name(config)
    print(f"ORBIT_HOME            : {os.environ.get('ORBIT_HOME', '<unset>')}")
    print(f"calendar-sync.json    : {config}")
    print(f"agenda calendar name  : {agenda_cal!r}")
    print()

    cals = _list_calendar_app_calendars()
    print(f"Calendars in Calendar.app ({len(cals)}):")
    for c in cals:
        marker = "  ← agenda" if c == agenda_cal else ""
        print(f"  - {c}{marker}")
    print()

    # 1) Find by orbit-id (prefix match — handles `[orbit:id]` and
    #    `[orbit:id@date]`). Scan EVERY calendar so we see where the event
    #    actually lives.
    needle = f"[orbit:{orbit_id}"
    script = (
        'tell application "Calendar"\n'
        '  set out to ""\n'
        '  repeat with c in (every calendar)\n'
        '    try\n'
        f'      set evs to (every event of c whose description contains "{_esc(needle)}")\n'
        '      repeat with e in evs\n'
        '        set out to out & "cal=" & (name of c) & " | uid=" & (uid of e as string) '
        '& " | start=" & ((start date of e) as string) '
        '& " | summary=" & (summary of e) & linefeed\n'
        '      end repeat\n'
        '    end try\n'
        '  end repeat\n'
        '  if out is "" then return "NO MATCH"\n'
        '  return out\n'
        'end tell'
    )
    print(f"── Buscando '{needle}' en todos los calendarios ──")
    out = _osa(script, timeout=120)
    print(out or "(AppleScript devolvió None — error o timeout)")
    print()

    # 2) Find by uid across all calendars.
    if uid:
        script_uid = (
            'tell application "Calendar"\n'
            '  set out to ""\n'
            '  repeat with c in (every calendar)\n'
            '    try\n'
            f'      set ev to first event of c whose uid is "{_esc(uid)}"\n'
            '      set out to out & "cal=" & (name of c) & " | start=" & ((start date of ev) as string) '
            '& " | summary=" & (summary of ev) & " | desc=" & (description of ev) & linefeed\n'
            '    end try\n'
            '  end repeat\n'
            '  if out is "" then return "UID not found in any calendar"\n'
            '  return out\n'
            'end tell'
        )
        print(f"── Buscando uid '{uid}' en todos los calendarios ──")
        out = _osa(script_uid, timeout=120)
        print(out or "(AppleScript devolvió None — error o timeout)")
        print()


if __name__ == "__main__":
    main()

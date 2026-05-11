#!/usr/bin/env python3
"""Try to update a Calendar event and dump AppleScript stderr so we can see
why it's failing silently.

Usage:

    python3 scripts/try_update_calendar_event.py <project-dir> <orbit-id>

Example:

    python3 scripts/try_update_calendar_event.py \\
        "/Users/hernando/🌿orbit-ps/☀️mision/☀️mission" af50f3bd

Builds the same props that ``sync_item`` would build for the recurring
task with the given orbit-id, then runs ``_update_calendar_event`` and
prints the raw AppleScript stdout + stderr + return code instead of
swallowing them. If AppleScript errors out (e.g. read-only event, escape
issue, etc.) we'll see exactly why here.
"""
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def main():
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(2)

    project_dir = Path(sys.argv[1]).resolve()
    orbit_id    = sys.argv[2].strip()

    # Make sure ORBIT_HOME is set so calendar-sync.json resolves correctly.
    if "ORBIT_HOME" not in os.environ:
        os.environ["ORBIT_HOME"] = str(project_dir.parent.parent)

    from core.agenda_cmds import _read_agenda
    from core.log import resolve_file
    from core.gsync import (
        _load_config, _agenda_calendar_name, _agenda_props_for_calendar_app,
        _project_description, _load_ids, _esc, _build_date_var,
    )

    config = _load_config()
    cal_name = _agenda_calendar_name(config)
    print(f"ORBIT_HOME     : {os.environ.get('ORBIT_HOME')}")
    print(f"project_dir    : {project_dir}")
    print(f"agenda calendar: {cal_name!r}")
    print()

    # Locate the item by orbit_id in agenda.md.
    agenda_path = resolve_file(project_dir, "agenda")
    data = _read_agenda(agenda_path)
    item = None
    kind = None
    for k, section in (("task", "tasks"), ("milestone", "milestones"),
                       ("reminder", "reminders")):
        for it in data.get(section, []):
            if it.get("orbit_id") == orbit_id:
                item = it
                kind = k
                break
        if item:
            break

    if not item:
        print(f"❌ No encontré item con orbit_id={orbit_id} en {agenda_path}")
        sys.exit(1)

    print(f"Item encontrado ({kind}): {item}")
    print()

    # Get uid from .gsync-ids.json.
    ids = _load_ids(project_dir)
    uid = None
    for key, entry in ids.items():
        if isinstance(entry, dict) and entry.get("orbit_id") == orbit_id:
            uid = entry.get("gcal_id")
            print(f"Entry: {key} → gcal_id={uid}")
            break
    if not uid:
        print("❌ No hay gcal_id para este orbit_id en .gsync-ids.json")
        sys.exit(1)
    print()

    description = _project_description(project_dir, config, html=False)
    item["_orbit_id"] = orbit_id
    props = _agenda_props_for_calendar_app(item, project_dir.name, description, kind)
    print("Props que se van a enviar a Calendar:")
    for k, v in props.items():
        print(f"  {k}: {v!r}")
    print()

    # Build the same script as _update_calendar_event but RUN it manually
    # so we can capture stderr.
    cal      = _esc(cal_name)
    uid_esc  = _esc(uid)
    sumr     = _esc(props.get("summary", ""))
    desc     = _esc(props.get("description", ""))
    loc      = _esc(props.get("location", ""))
    url_v    = _esc(props.get("url", ""))
    rrule    = _esc(props.get("rrule", ""))
    alarm_minutes = props.get("alarm_minutes")

    if isinstance(alarm_minutes, int):
        alarm_block = (
            '        delete every display alarm of ev\n'
            '        make new display alarm at end of display alarms of ev '
            f'with properties {{trigger interval:-{int(alarm_minutes)}}}'
        )
    else:
        alarm_block = '        delete every display alarm of ev'

    script = (
        f'tell application "Calendar"\n'
        f'    tell calendar "{cal}"\n'
        f'        try\n'
        f'            set ev to first event whose uid is "{uid_esc}"\n'
        f'        on error\n'
        f'            return "missing"\n'
        f'        end try\n'
        f'        set summary of ev to "{sumr}"\n'
        f'        {_build_date_var("startD", props["start_iso"])}\n'
        f'        {_build_date_var("endD", props["end_iso"])}\n'
        f'        set safeEnd to current date\n'
        f'        set year of safeEnd to 2099\n'
        f'        set month of safeEnd to 12\n'
        f'        set day of safeEnd to 31\n'
        f'        set hours of safeEnd to 23\n'
        f'        set minutes of safeEnd to 59\n'
        f'        set seconds of safeEnd to 0\n'
        f'        set end date of ev to safeEnd\n'
        f'        set start date of ev to startD\n'
        f'        set end date of ev to endD\n'
        f'        set description of ev to "{desc}"\n'
        f'        set location of ev to "{loc}"\n'
        f'        set url of ev to "{url_v}"\n'
        f'        set recurrence of ev to "{rrule}"\n'
        f'{alarm_block}\n'
        f'        return "ok"\n'
        f'    end tell\n'
        f'end tell'
    )

    print("── AppleScript que se va a ejecutar ──")
    print(script)
    print("──────────────────────────────────────")
    print()

    r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True,
                       timeout=120)
    print(f"return code : {r.returncode}")
    print(f"stdout      : {r.stdout!r}")
    print(f"stderr      : {r.stderr!r}")


if __name__ == "__main__":
    main()

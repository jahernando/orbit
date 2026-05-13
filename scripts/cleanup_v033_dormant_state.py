"""Delete inert state files left by the now-dormant gsync/calsync paths
and trim dead config fields from ``calendar-sync.json``.

Run once per workspace after v0.33:

    ORBIT_HOME=~/🚀orbit-ws python scripts/cleanup_v033_dormant_state.py
    ORBIT_HOME=~/🌿orbit-ps python scripts/cleanup_v033_dormant_state.py [--dry-run]

Removes:
* ``<project>/.gsync-ids.json`` — Calendar.app UID registry (inert)
* ``<project>/.gsync-failures.json`` — failures journal from v0.30 (inert)

Trims from ``calendar-sync.json`` (only the dead fields; preserves
``ics_buckets`` and anything else you've added):
* ``task_lists`` — Google Tasks list IDs (Google API path dormant since v0.29)
* ``reminders_list`` — Reminders.app list name (dormant since v0.29 backend=calendar)
* ``agenda_calendar`` — Calendar.app calendar name (dormant since v0.33 ics-only)
* ``sync_tasks``, ``sync_milestones`` — per-kind toggles (dormant since v0.33)
* ``reminders_backend`` — backend selector (dormant since v0.33 ics-only)
* ``repo_url`` — already a no-op since v0.29.4

Idempotent. Safe to run multiple times. To revive any of these paths,
see DORMANT.md.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.config import ORBIT_HOME, iter_project_dirs   # noqa: E402


_DEAD_CONFIG_FIELDS = (
    "task_lists", "reminders_list", "agenda_calendar",
    "sync_tasks", "sync_milestones",
    "reminders_backend", "repo_url",
)

_DEAD_STATE_FILES = (".gsync-ids.json", ".gsync-failures.json")


def _clean_state_files(dry_run: bool) -> int:
    removed = 0
    for pd in iter_project_dirs():
        for name in _DEAD_STATE_FILES:
            p = pd / name
            if not p.exists():
                continue
            if dry_run:
                print(f"  would rm: {p}")
            else:
                p.unlink()
                print(f"  rm: {p}")
            removed += 1
    return removed


def _clean_config(dry_run: bool) -> int:
    config_path = ORBIT_HOME / "calendar-sync.json"
    if not config_path.exists():
        return 0
    config = json.loads(config_path.read_text())
    touched = []
    for f in _DEAD_CONFIG_FIELDS:
        if f in config:
            touched.append(f)
            if not dry_run:
                del config[f]
    if touched:
        action = "would trim" if dry_run else "trimmed"
        print(f"  {action} de {config_path.name}: {', '.join(touched)}")
        if not dry_run:
            config_path.write_text(json.dumps(config, indent=2, ensure_ascii=False) + "\n")
    return len(touched)


def main() -> int:
    dry_run = "--dry-run" in sys.argv
    print(f"Workspace: {ORBIT_HOME}")
    if dry_run:
        print("(dry-run — no se escribirá nada)\n")

    state = _clean_state_files(dry_run)
    cfg = _clean_config(dry_run)

    suffix = " (dry-run)" if dry_run else ""
    print(f"\n{state} ficheros .gsync-* y {cfg} campos de config eliminados{suffix}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

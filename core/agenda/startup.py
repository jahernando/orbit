"""startup — shell-startup hook that fast-forwards stale recurring items.

Called from :mod:`core.shell` at session boot and on day-change. For each
local project, advances recurring items whose date is in the past so the
user doesn't see "due yesterday" lines that were just calendar drift.
"""
from __future__ import annotations

from datetime import date

from core.config import iter_project_dirs
from core.log import resolve_file

from core.agenda.recurrence import _advance_to_today_or_future
from core.agenda.io import _read_agenda, _write_agenda
from core.agenda.lifecycle import _TYPE_CONFIG


def startup_advance_past_recurring() -> list:
    """Auto-advance recurring items with dates strictly before today.

    Called at shell startup and on day-change. For each local project, advances
    recurring items whose date is in the past:
      - Events: pop old, append new occurrence
      - Reminders: advance date in-place
      - Tasks/milestones: cancel old, append new occurrence

    Advances multiple steps if needed (e.g. user was away for weeks).
    Returns list of info strings like "[project] Título → 2026-04-22".

    **Side effect**: writes modified `agenda.md` files to disk without prompting
    for confirmation. The caller is expected to surface the returned list to the
    user (shell.py:88 does this). To inspect what would change without writing,
    no dry-run mode is provided — read agendas via `_read_agenda` and reproduce
    the loop manually.
    """
    today = date.today()
    advanced = []

    for project_dir in iter_project_dirs():
        agenda_path = resolve_file(project_dir, "agenda")
        if not agenda_path.exists():
            continue

        data = _read_agenda(agenda_path)
        modified = False
        proj_name = project_dir.name

        for type_name, cfg in _TYPE_CONFIG.items():
            items = data[cfg["key"]]
            to_advance = []

            for i, item in enumerate(items):
                if not item.get("recur") or not item.get("date"):
                    continue
                try:
                    item_date = date.fromisoformat(item["date"])
                except ValueError:
                    continue
                if item_date >= today:
                    continue
                # Skip done/cancelled
                if cfg["has_status"] and item.get("status") != "pending":
                    continue
                if item.get("cancelled"):
                    continue
                to_advance.append(i)

            # Process in reverse to preserve indices when popping
            for i in reversed(to_advance):
                item = items[i]
                desc = item["desc"]
                next_due, ended = _advance_to_today_or_future(
                    item["date"], item["recur"], item.get("until"))

                if ended:
                    # Series exceeded until limit
                    if cfg["drop_action"] == "pop":
                        items.pop(i)
                    elif cfg["drop_action"] == "cancel_bool":
                        item["cancelled"] = True
                    else:
                        item["status"] = "cancelled"
                    info = f" — serie finalizada ({item.get('until')})"
                elif cfg["drop_action"] == "pop":
                    # Events: pop old, create new with next_due. Drop the
                    # legacy `synced` flag if present (no longer used) but
                    # KEEP orbit_id so the next sync recognises this as the
                    # same series advanced to a new anchor date.
                    popped = items.pop(i)
                    new_item = {k: v for k, v in popped.items() if k != "synced"}
                    new_item["date"] = next_due
                    items.append(new_item)
                    info = f" → {next_due}"
                elif cfg["drop_action"] == "cancel_bool":
                    # Reminders: advance date in-place
                    item["date"] = next_due
                    info = f" → {next_due}"
                else:
                    # Tasks/milestones: cancel old, create new
                    item["status"] = "cancelled"
                    new_item = {"desc": desc, "date": next_due,
                                "recur": item["recur"],
                                "until": item.get("until"),
                                "notes": list(item.get("notes") or []),
                                "status": "pending"}
                    if item.get("ring"):
                        new_item["ring"] = item["ring"]
                    items.append(new_item)
                    info = f" → {next_due}"

                modified = True
                advanced.append(f"[{proj_name}] {desc}{info}")

        if modified:
            _write_agenda(agenda_path, data)

    return advanced

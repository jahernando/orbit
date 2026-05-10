"""gimport — pull `completed` toggles from Reminders.app back into agenda.md.

One-way reverse sync, deliberately narrow in scope:
- imports only ``completed`` (with recurrence advance)
- ignores title / date / notes changes — agenda.md stays the source of
  truth for metadata
- ignores items added in Reminders without an orbit-id — orbit can't
  know which project they belong to
- when an item disappears from the list, marks it ``cancelled``

Run from the CLI as ``orbit gpull [project]``.

Identification: every item synced by orbit carries an ``[orbit:xxx]`` tag
in its body. We bulk-fetch all reminders, build an ``orbit_id → reminder``
map, then walk the agenda items that have an orbit_id and apply the
``completed`` flag.
"""

from datetime import date
from pathlib import Path
from typing import Optional

from core.config import iter_project_dirs
from core.log import resolve_file
from core.project import _is_new_project, _find_new_project
from core.agenda_cmds import _read_agenda, _write_agenda, _next_occurrence
from core.gsync import (
    _load_ids, _save_ids, _item_key, _make_snapshot,
    _fetch_completed_orbit_ids,
    _load_config, _reminders_list_name,
    _reminders_app_running,
)


# ── Reminder reconciliation ────────────────────────────────────────────────

def _advance_recurring(item: dict) -> Optional[str]:
    """Mutate a recurring item to its next occurrence in place.

    Returns "advanced" / "ended" / None (not recurring).
    The orbit_id stays the same — same series identity.
    """
    if not item.get("recur"):
        return None
    today_str = date.today().isoformat()
    nxt = _next_occurrence(item.get("date"), item["recur"], today_str)
    if item.get("until") and date.fromisoformat(nxt) > date.fromisoformat(item["until"]):
        return "ended"
    item["date"] = nxt
    return "advanced"


def _mark_done(item: dict, kind: str) -> Optional[str]:
    """Apply a `completed` toggle: mark done, advancing recurrences.

    Returns a short human-readable description, or None if the item was
    already done/cancelled (no-op).

    By design we import only ``completed``. Title and date changes stay in
    orbit's hands — agenda.md remains the source of truth for metadata.
    """
    is_pending_task = (kind in ("task", "milestone")
                      and item.get("status", "pending") == "pending")
    is_active_reminder = (kind == "reminder" and not item.get("cancelled"))
    if not (is_pending_task or is_active_reminder):
        return None

    if item.get("recur"):
        outcome = _advance_recurring(item)
        if outcome == "ended":
            if kind == "reminder":
                item["cancelled"] = True
            else:
                item["status"] = "cancelled"
            return "done (serie finalizada)"
        return f"done → próxima ocurrencia {item['date']}"
    if kind == "reminder":
        item["cancelled"] = True
    else:
        item["status"] = "done"
    return "marcado done"


# ── Main entry points ──────────────────────────────────────────────────────

def import_changes_for_project(project_dir: Path,
                               completed_oids: set,
                               dry_run: bool = False) -> dict:
    """Apply the set of completed orbit-ids to one project's agenda.

    *completed_oids* is the set of orbit-ids whose Reminder is currently
    ``completed=True`` (gathered by `_fetch_completed_orbit_ids` once per
    workspace, not per project).

    Returns ``{"project", "modified", "lines"}``.
    """
    project_name = project_dir.name
    result = {"project": project_name, "modified": 0, "lines": []}

    agenda_path = resolve_file(project_dir, "agenda")
    if not agenda_path.exists():
        return result
    data = _read_agenda(agenda_path)
    ids = _load_ids(project_dir)
    changed = False

    for kind, key in (("task", "tasks"), ("milestone", "milestones"),
                      ("reminder", "reminders")):
        for item in data.get(key) or []:
            oid = item.get("orbit_id")
            if not oid or oid not in completed_oids:
                continue
            change = _mark_done(item, kind)
            if change:
                result["lines"].append(f"  [{project_name}] {item['desc']}: {change}")
                result["modified"] += 1
                changed = True
                ids.setdefault(_item_key(item), {})["snapshot"] = _make_snapshot(item)

    if changed and not dry_run:
        _write_agenda(agenda_path, data)
        _save_ids(project_dir, ids)

    return result


def import_changes(project: Optional[str] = None,
                   dry_run: bool = False) -> int:
    """Pull Reminders.app `completed` toggles back to agenda.md.

    project: if given, only that one project. Otherwise all in the
    current workspace.
    """
    config = _load_config()
    list_name = _reminders_list_name(config)

    if not _reminders_app_running():
        print("⚠️  Reminders.app no está corriendo.")
        return 1

    if project:
        project_dir = _find_new_project(project)
        if not project_dir:
            print(f"⚠️  Proyecto no encontrado: {project!r}")
            return 1
        dirs = [project_dir]
    else:
        dirs = [d for d in iter_project_dirs() if _is_new_project(d)]

    label = "  [dry-run]" if dry_run else ""
    print(f"Importando cambios externos → Orbit{label}")
    print(f"  lista Reminders: {list_name}")

    # ONE AppleScript call for the whole workspace — only the completed
    # items with an orbit-id come back.
    completed_oids = _fetch_completed_orbit_ids(list_name)
    if not completed_oids:
        print("Sin cambios externos.")
        return 0

    print("─" * 50)
    total_mod = 0
    for project_dir in dirs:
        res = import_changes_for_project(project_dir, completed_oids,
                                          dry_run=dry_run)
        for line in res["lines"]:
            print(line)
        total_mod += res["modified"]

    print("─" * 50)
    if total_mod:
        print(f"Importados: {total_mod} modificado{'s' if total_mod != 1 else ''}")
    else:
        print("Sin cambios externos aplicables.")
    return 0

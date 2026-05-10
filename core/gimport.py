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
    _fetch_all_reminders,
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


def _reconcile_reminder(item: dict, kind: str, r: dict, snapshot: dict) -> list:
    """Apply the backend ``completed`` toggle from one reminder to *item*.

    Returns a list of human-readable change descriptions.

    By design we import only ``completed`` (and the recurrence advance it
    triggers). Title and date changes stay in orbit's hands — agenda.md
    remains the source of truth for metadata. This keeps conflict surface
    near zero: there is essentially no way for the user and orbit to both
    flip ``completed`` in incompatible ways.
    """
    changes = []
    if not r["completed"]:
        return changes

    is_pending_task = (kind in ("task", "milestone")
                      and item.get("status", "pending") == "pending")
    is_active_reminder = (kind == "reminder" and not item.get("cancelled"))
    if not (is_pending_task or is_active_reminder):
        return changes

    if item.get("recur"):
        outcome = _advance_recurring(item)
        if outcome == "ended":
            if kind == "reminder":
                item["cancelled"] = True
            else:
                item["status"] = "cancelled"
            changes.append("done (serie finalizada)")
        else:
            changes.append(f"done → próxima ocurrencia {item['date']}")
    else:
        if kind == "reminder":
            item["cancelled"] = True
        else:
            item["status"] = "done"
        changes.append("marcado done")
    return changes


# ── Main entry points ──────────────────────────────────────────────────────

def import_changes_for_project(project_dir: Path, dry_run: bool = False) -> dict:
    """Pull Reminders.app + Calendar.app changes for a single project.

    Returns dict {project, modified_count, change_lines, deleted_count}.
    """
    config = _load_config()
    list_name = _reminders_list_name(config)
    project_name = project_dir.name
    result = {"project": project_name, "modified": 0,
              "lines": [], "deleted": 0}

    if not _reminders_app_running():
        return result

    reminders = _fetch_all_reminders(list_name)
    by_oid = {r["orbit_id"]: r for r in reminders if r["orbit_id"]}

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
            if not oid:
                continue
            r = by_oid.get(oid)
            if r is None:
                # Disappeared from Reminders.app — cancel in orbit.
                if kind == "reminder" and not item.get("cancelled"):
                    item["cancelled"] = True
                    result["lines"].append(f"  [{project_name}] {item['desc']}: borrado en Reminders → cancelled")
                    result["deleted"] += 1
                    changed = True
                elif kind in ("task", "milestone") and item.get("status") != "cancelled":
                    item["status"] = "cancelled"
                    result["lines"].append(f"  [{project_name}] {item['desc']}: borrado en Reminders → cancelled")
                    result["deleted"] += 1
                    changed = True
                continue
            # Compare against the snapshot we stored on the last push.
            snapshot = ids.get(_item_key(item), {}).get("snapshot", {})
            changes = _reconcile_reminder(item, kind, r, snapshot)
            if changes:
                for c in changes:
                    result["lines"].append(f"  [{project_name}] {item['desc']}: {c}")
                result["modified"] += 1
                changed = True
                # Update snapshot to current state (so the next sync doesn't
                # think orbit just changed it).
                ids.setdefault(_item_key(item), {})["snapshot"] = _make_snapshot(item)

    if changed and not dry_run:
        _write_agenda(agenda_path, data)
        _save_ids(project_dir, ids)

    return result


def import_changes(project: Optional[str] = None,
                   dry_run: bool = False) -> int:
    """Pull Reminders.app + Calendar.app changes back to agenda.md.

    project: if given, sync only that one project. Otherwise all projects
    in the current workspace.
    """
    config = _load_config()
    list_name = _reminders_list_name(config)
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
    print("─" * 50)

    total_mod = total_del = 0
    for project_dir in dirs:
        res = import_changes_for_project(project_dir, dry_run=dry_run)
        for line in res["lines"]:
            print(line)
        total_mod += res["modified"]
        total_del += res["deleted"]

    print("─" * 50)
    if total_mod or total_del:
        parts = []
        if total_mod:
            parts.append(f"{total_mod} modificado{'s' if total_mod != 1 else ''}")
        if total_del:
            parts.append(f"{total_del} cancelado{'s' if total_del != 1 else ''}")
        print(f"Importados: {' · '.join(parts)}")
    else:
        print("Sin cambios externos.")
    return 0

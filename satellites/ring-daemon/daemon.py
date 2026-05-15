#!/usr/bin/env python3
"""satellites/ring-daemon/daemon.py — reconcile ring.json → Reminders.app via EventKit.

Reads one or more ring.json payloads (each describing the rolling 7-day ring
window for a workspace) and upserts EKReminder objects in a single list
("Orbit Ring" by default) so that the list matches the union of payloads
exactly. Items are matched by `[orbit:<id>]` embedded in `notes`; orphans
inside the list that carry an orbit-tag are removed.

Items in the list **without** an orbit-tag are never touched — the user
can add manual reminders to the same list safely.

Usage:
    python3 satellites/ring-daemon/daemon.py <ring.json> [<ring.json> ...]

Exit codes:
    0  success
    2  bad args / missing file
    3  Reminders access denied
"""
import json
import re
import sys
from datetime import datetime
from pathlib import Path

from EventKit import (
    EKAlarm,
    EKCalendar,
    EKEntityTypeReminder,
    EKEventStore,
    EKReminder,
    EKSourceTypeLocal,
)
from Foundation import (
    NSDate,
    NSDateComponents,
    NSDefaultRunLoopMode,
    NSRunLoop,
)

ORBIT_TAG_RE = re.compile(r"\[orbit:([A-Za-z0-9_\-]+)\]")
DEFAULT_LIST_NAME = "Orbit Ring"
KIND_EMOJI = {"task": "✅", "milestone": "🏁", "event": "📅", "reminder": "💬"}


def _pump(seconds: float) -> None:
    deadline = NSDate.dateWithTimeIntervalSinceNow_(seconds)
    NSRunLoop.currentRunLoop().runUntilDate_(deadline)


def _request_access(store) -> bool:
    """Request full access to Reminders. Returns True if granted."""
    result = {"granted": False}

    def handler(granted, err):
        result["granted"] = bool(granted)
        if err is not None:
            sys.stderr.write(f"EventKit access error: {err}\n")

    if hasattr(store, "requestFullAccessToRemindersWithCompletion_"):
        store.requestFullAccessToRemindersWithCompletion_(handler)
    else:
        store.requestAccessToEntityType_completion_(EKEntityTypeReminder, handler)
    _pump(2.0)
    return result["granted"]


def _get_or_create_list(store, name: str):
    for cal in store.calendarsForEntityType_(EKEntityTypeReminder):
        if cal.title() == name:
            return cal

    src = None
    for s in store.sources():
        if s.sourceType() == EKSourceTypeLocal:
            src = s
            break
    if src is None and store.sources():
        src = store.sources()[0]
    if src is None:
        raise RuntimeError("no EventKit source available for new list")

    cal = EKCalendar.calendarForEntityType_eventStore_(EKEntityTypeReminder, store)
    cal.setTitle_(name)
    cal.setSource_(src)
    ok, err = store.saveCalendar_commit_error_(cal, True, None)
    if not ok:
        raise RuntimeError(f"saveCalendar failed: {err}")
    return cal


def _components_from_iso(iso: str):
    dt = datetime.fromisoformat(iso)
    c = NSDateComponents.alloc().init()
    c.setYear_(dt.year)
    c.setMonth_(dt.month)
    c.setDay_(dt.day)
    c.setHour_(dt.hour)
    c.setMinute_(dt.minute)
    c.setSecond_(0)
    return c


def _fetch_reminders(store, cal) -> list:
    pred = store.predicateForRemindersInCalendars_([cal])
    result = {"items": None}

    def handler(found):
        result["items"] = list(found or [])

    store.fetchRemindersMatchingPredicate_completion_(pred, handler)
    deadline = NSDate.dateWithTimeIntervalSinceNow_(5.0)
    while result["items"] is None and NSDate.date().compare_(deadline) < 0:
        NSRunLoop.currentRunLoop().runMode_beforeDate_(
            NSDefaultRunLoopMode, NSDate.dateWithTimeIntervalSinceNow_(0.1)
        )
    return result["items"] or []


def _extract_orbit_id(reminder) -> str | None:
    notes = reminder.notes() or ""
    m = ORBIT_TAG_RE.search(notes)
    return m.group(1) if m else None


def _format_title(item: dict) -> str:
    prefix = KIND_EMOJI.get(item.get("kind", ""), "")
    proj = item.get("project", "")
    title = item.get("title", "")
    parts = []
    if proj:
        parts.append(f"[{proj}]")
    if prefix:
        parts.append(prefix)
    parts.append(title)
    return " ".join(p for p in parts if p)


def _apply_one_list(store, list_name: str, desired_items: list) -> dict:
    """Reconcile a single Reminders.app list against the desired items.

    Items without `[orbit:xxx]` in notes are never touched.
    """
    cal = _get_or_create_list(store, list_name)
    existing = _fetch_reminders(store, cal)

    grouped: dict = {}
    untagged = 0
    for r in existing:
        oid = _extract_orbit_id(r)
        if oid is None:
            untagged += 1
            continue
        grouped.setdefault(oid, []).append(r)

    by_id = {}
    dup_orphans = []
    for oid, rs in grouped.items():
        by_id[oid] = rs[0]
        dup_orphans.extend(rs[1:])

    desired_ids = set()
    created = updated = errors = removed = 0

    for item in desired_items:
        oid = item["orbit_id"]
        desired_ids.add(oid)
        title = _format_title(item)
        notes = f"[orbit:{oid}]"
        due_iso = item["due_iso"]
        alarm_min = int(item.get("alarm_minutes", 5))

        r = by_id.get(oid)
        is_new = r is None
        if is_new:
            r = EKReminder.reminderWithEventStore_(store)
            r.setCalendar_(cal)
        r.setTitle_(title)
        r.setNotes_(notes)
        r.setDueDateComponents_(_components_from_iso(due_iso))
        for a in list(r.alarms() or []):
            r.removeAlarm_(a)
        r.addAlarm_(EKAlarm.alarmWithRelativeOffset_(-alarm_min * 60))

        ok, err = store.saveReminder_commit_error_(r, True, None)
        if not ok:
            errors += 1
            sys.stderr.write(f"  ✗ save failed orbit:{oid} ({list_name}): {err}\n")
        elif is_new:
            created += 1
        else:
            updated += 1

    for oid, r in by_id.items():
        if oid not in desired_ids:
            ok, err = store.removeReminder_commit_error_(r, True, None)
            if ok:
                removed += 1
            else:
                errors += 1
                sys.stderr.write(f"  ✗ remove failed orbit:{oid} ({list_name}): {err}\n")

    for r in dup_orphans:
        ok, err = store.removeReminder_commit_error_(r, True, None)
        if ok:
            removed += 1
        else:
            errors += 1
            sys.stderr.write(f"  ✗ remove dup failed ({list_name}): {err}\n")

    return {
        "list": list_name,
        "created": created,
        "updated": updated,
        "removed": removed,
        "untouched_untagged": untagged,
        "errors": errors,
    }


def apply_payloads(store, payloads: list, default_list: str = DEFAULT_LIST_NAME) -> dict:
    """Reconcile all Reminders.app lists named by the payloads.

    Each payload names a `list` (workspace list); items may override.
    For each list mentioned, we sweep idempotently with the union of
    desired items targeting that list. Lists named by a payload but with
    no items are swept (orbit-tagged reminders removed) — that's how a
    workspace with `enabled: false` cleans up its old reminders.
    """
    by_list: dict = {}
    lists_named = set()
    for payload in payloads:
        ws_list = (payload.get("list") or default_list).strip() or default_list
        lists_named.add(ws_list)
        for item in payload.get("items", []):
            lst = (item.get("list") or ws_list).strip() or ws_list
            lists_named.add(lst)
            by_list.setdefault(lst, []).append(item)

    if not lists_named:
        lists_named.add(default_list)

    aggregate = {"created": 0, "updated": 0, "removed": 0,
                 "untouched_untagged": 0, "errors": 0, "per_list": []}
    for list_name in sorted(lists_named):
        sub = _apply_one_list(store, list_name, by_list.get(list_name, []))
        aggregate["created"] += sub["created"]
        aggregate["updated"] += sub["updated"]
        aggregate["removed"] += sub["removed"]
        aggregate["untouched_untagged"] += sub["untouched_untagged"]
        aggregate["errors"] += sub["errors"]
        aggregate["per_list"].append(sub)
    return aggregate


def main(argv: list) -> int:
    if len(argv) < 2:
        print("Usage: satellites/ring-daemon/daemon.py <ring.json> [<ring.json> ...]")
        return 2
    payloads = []
    for arg in argv[1:]:
        p = Path(arg)
        if not p.exists():
            sys.stderr.write(f"Not found: {p}\n")
            return 2
        payloads.append(json.loads(p.read_text()))

    store = EKEventStore.alloc().init()
    if not _request_access(store):
        sys.stderr.write(
            "Reminders access denied. Grant in System Settings → Privacy → Reminders.\n"
        )
        return 3

    stats = apply_payloads(store, payloads)
    for sub in stats["per_list"]:
        print(
            f"ring-daemon → {sub['list']!r}: "
            f"created={sub['created']}  updated={sub['updated']}  "
            f"removed={sub['removed']}  untagged_kept={sub['untouched_untagged']}  "
            f"errors={sub['errors']}"
        )
    return 0 if stats["errors"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))

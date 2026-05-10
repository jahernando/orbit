"""Tests for gimport — pulling `completed` toggles from Reminders.app."""

import json
from pathlib import Path

import pytest

from core import gimport, gsync


# ── Helpers ────────────────────────────────────────────────────────────────

def _make_proj(tmp_path: Path, name: str = "🌀test") -> Path:
    """Build a minimal project directory with agenda + ids files."""
    proj = tmp_path / name
    proj.mkdir()
    base = name.lstrip("🌀")
    (proj / f"{base}-agenda.md").write_text("# Agenda\n\n## ✅ Tareas\n\n## 📅 Eventos\n\n## 💬 Recordatorios\n")
    (proj / f"{base}-project.md").write_text("# project\n")
    return proj


def _seed_agenda(proj: Path, items: dict):
    """Write a minimal agenda with given tasks/events/reminders."""
    base = proj.name.lstrip("🌀")
    agenda = proj / f"{base}-agenda.md"
    from core.agenda_cmds import _read_agenda, _write_agenda
    data = _read_agenda(agenda)
    for k, lst in items.items():
        data[k] = lst
    _write_agenda(agenda, data)


def _seed_ids(proj: Path, ids: dict):
    (proj / ".gsync-ids.json").write_text(json.dumps(ids))


def _read_back(proj: Path) -> dict:
    base = proj.name.lstrip("🌀")
    from core.agenda_cmds import _read_agenda
    return _read_agenda(proj / f"{base}-agenda.md")


# ── Single-item mark-done ──────────────────────────────────────────────────

class TestMarkDone:

    def test_pending_task_marked_done(self):
        item = {"desc": "Foo", "date": "2026-05-15", "status": "pending"}
        msg = gimport._mark_done(item, "task")
        assert item["status"] == "done"
        assert "done" in msg

    def test_recurring_advances(self):
        item = {"desc": "Daily", "date": "2026-05-15", "recur": "daily",
                "status": "pending"}
        gimport._mark_done(item, "task")
        assert item["status"] == "pending"
        assert item["date"] == "2026-05-16"

    def test_recurring_until_finishes(self):
        item = {"desc": "End", "date": "2026-05-15", "recur": "daily",
                "until": "2026-05-15", "status": "pending"}
        gimport._mark_done(item, "task")
        assert item["status"] == "cancelled"

    def test_reminder_kind_cancels(self):
        item = {"desc": "Llamar", "date": "2026-05-15", "time": "10:00"}
        gimport._mark_done(item, "reminder")
        assert item["cancelled"] is True

    def test_already_done_is_noop(self):
        item = {"desc": "Foo", "date": "2026-05-15", "status": "done"}
        msg = gimport._mark_done(item, "task")
        assert msg is None
        assert item["status"] == "done"

    def test_already_cancelled_reminder_noop(self):
        item = {"desc": "Foo", "date": "2026-05-15", "time": "10:00",
                "cancelled": True}
        msg = gimport._mark_done(item, "reminder")
        assert msg is None


# ── End-to-end import_changes_for_project ──────────────────────────────────

class TestImportForProject:

    def test_pending_to_done(self, tmp_path):
        proj = _make_proj(tmp_path, "🌀foo")
        _seed_agenda(proj, {"tasks": [{
            "desc": "Bar", "date": "2026-05-15", "status": "pending",
            "orbit_id": "ab12cd34"
        }]})
        _seed_ids(proj, {"Bar::2026-05-15": {
            "gtask_id": "uid-1", "orbit_id": "ab12cd34",
            "snapshot": {"desc": "Bar", "date": "2026-05-15"}
        }})
        res = gimport.import_changes_for_project(proj, {"ab12cd34"}, dry_run=False)
        assert res["modified"] == 1
        assert _read_back(proj)["tasks"][0]["status"] == "done"

    def test_dry_run_does_not_persist(self, tmp_path):
        proj = _make_proj(tmp_path, "🌀dry")
        _seed_agenda(proj, {"tasks": [{
            "desc": "Foo", "date": "2026-05-15", "status": "pending",
            "orbit_id": "ab12cd34"
        }]})
        _seed_ids(proj, {"Foo::2026-05-15": {
            "gtask_id": "u", "orbit_id": "ab12cd34",
            "snapshot": {"desc": "Foo", "date": "2026-05-15"}
        }})
        gimport.import_changes_for_project(proj, {"ab12cd34"}, dry_run=True)
        assert _read_back(proj)["tasks"][0]["status"] == "pending"

    def test_no_orbit_id_skipped(self, tmp_path):
        """Items without an orbit-id (legacy or never synced) are not touched."""
        proj = _make_proj(tmp_path, "🌀nox")
        _seed_agenda(proj, {"tasks": [{
            "desc": "Untagged", "date": "2026-05-15", "status": "pending",
            "orbit_id": None,
        }]})
        # Pretend an item with that desc was completed externally — no
        # orbit-id, so we can't match it. Should be skipped.
        res = gimport.import_changes_for_project(proj, {"ab12cd34"}, dry_run=False)
        assert res["modified"] == 0

    def test_empty_set_no_op(self, tmp_path):
        proj = _make_proj(tmp_path, "🌀empty")
        _seed_agenda(proj, {"tasks": [{
            "desc": "Foo", "date": "2026-05-15", "status": "pending",
            "orbit_id": "abc12345"
        }]})
        res = gimport.import_changes_for_project(proj, set(), dry_run=False)
        assert res["modified"] == 0
        assert _read_back(proj)["tasks"][0]["status"] == "pending"

    def test_recurring_advances(self, tmp_path):
        proj = _make_proj(tmp_path, "🌀rec")
        _seed_agenda(proj, {"tasks": [{
            "desc": "Daily", "date": "2026-05-15", "recur": "daily",
            "status": "pending", "orbit_id": "abcdef12"
        }]})
        gimport.import_changes_for_project(proj, {"abcdef12"}, dry_run=False)
        # Item still pending but advanced one day
        agenda = _read_back(proj)
        assert agenda["tasks"][0]["status"] == "pending"
        assert agenda["tasks"][0]["date"] == "2026-05-16"

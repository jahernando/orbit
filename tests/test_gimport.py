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


# ── Single-item reconciliation ─────────────────────────────────────────────

class TestReconcileReminder:

    def test_completed_marks_task_done(self):
        item = {"desc": "Foo", "date": "2026-05-15",
                "status": "pending", "orbit_id": "abc"}
        r = {"completed": True, "name": "[p] ✅ Foo",
             "due_iso": "2026-05-15T09:00", "orbit_id": "abc"}
        changes = gimport._reconcile_reminder(item, "task", r, {})
        assert item["status"] == "done"
        assert any("done" in c for c in changes)

    def test_completed_recurring_advances(self):
        item = {"desc": "Daily", "date": "2026-05-15", "recur": "daily",
                "status": "pending", "orbit_id": "abc"}
        r = {"completed": True, "name": "[p] ✅ Daily",
             "due_iso": "2026-05-15T09:00", "orbit_id": "abc"}
        gimport._reconcile_reminder(item, "task", r, {})
        assert item["status"] == "pending"
        assert item["date"] == "2026-05-16"

    def test_completed_recurring_with_until_finishes(self):
        item = {"desc": "End", "date": "2026-05-15", "recur": "daily",
                "until": "2026-05-15", "status": "pending", "orbit_id": "abc"}
        r = {"completed": True, "name": "[p] ✅ End",
             "due_iso": "2026-05-15T09:00", "orbit_id": "abc"}
        gimport._reconcile_reminder(item, "task", r, {})
        assert item["status"] == "cancelled"

    def test_completed_reminder_kind_cancels(self):
        """Reminders (non-task kind) have no `done` state — they get cancelled."""
        item = {"desc": "Llamar", "date": "2026-05-15", "time": "10:00",
                "orbit_id": "abc"}
        r = {"completed": True, "name": "[p] 💬 Llamar",
             "due_iso": "2026-05-15T10:00", "orbit_id": "abc"}
        gimport._reconcile_reminder(item, "reminder", r, {})
        assert item["cancelled"] is True

    def test_completed_idempotent_when_already_done(self):
        item = {"desc": "Foo", "date": "2026-05-15", "status": "done",
                "orbit_id": "abc"}
        r = {"completed": True, "name": "[p] ✅ Foo",
             "due_iso": "2026-05-15T09:00", "orbit_id": "abc"}
        changes = gimport._reconcile_reminder(item, "task", r, {})
        assert changes == []
        assert item["status"] == "done"

    def test_not_completed_no_change(self):
        """Renamed/redated reminders don't propagate — only `completed` does."""
        item = {"desc": "Old", "date": "2026-05-15",
                "status": "pending", "orbit_id": "abc"}
        r = {"completed": False, "name": "[p] ✅ New title",
             "due_iso": "2026-05-20T09:00", "orbit_id": "abc"}
        changes = gimport._reconcile_reminder(item, "task", r, {})
        assert changes == []
        assert item["desc"] == "Old"   # untouched
        assert item["date"] == "2026-05-15"  # untouched


# ── End-to-end import_changes_for_project ──────────────────────────────────

class TestImportForProject:

    def test_pending_to_done(self, tmp_path, monkeypatch):
        proj = _make_proj(tmp_path, "🌀foo")
        _seed_agenda(proj, {"tasks": [{
            "desc": "Bar", "date": "2026-05-15", "status": "pending",
            "orbit_id": "ab12cd34"
        }]})
        _seed_ids(proj, {"Bar::2026-05-15": {
            "gtask_id": "uid-1", "orbit_id": "ab12cd34",
            "snapshot": {"desc": "Bar", "date": "2026-05-15"}
        }})
        monkeypatch.setattr(gimport, "_load_config", lambda: {"reminders_list": "L"})
        monkeypatch.setattr(gimport, "_reminders_list_name", lambda c: "L")
        monkeypatch.setattr(gimport, "_reminders_app_running", lambda: True)
        monkeypatch.setattr(gimport, "_fetch_all_reminders", lambda lst: [{
            "uid": "uid-1", "name": "[foo] ✅ Bar",
            "due_iso": "2026-05-15T09:00", "completed": True,
            "body": "[orbit:ab12cd34]", "orbit_id": "ab12cd34",
            "occurrence": None,
        }])
        res = gimport.import_changes_for_project(proj, dry_run=False)
        assert res["modified"] == 1
        assert _read_back(proj)["tasks"][0]["status"] == "done"

    def test_deleted_in_reminders_cancels(self, tmp_path, monkeypatch):
        proj = _make_proj(tmp_path, "🌀baz")
        _seed_agenda(proj, {"tasks": [{
            "desc": "Gone", "date": "2026-05-15", "status": "pending",
            "orbit_id": "deadbeef"
        }]})
        _seed_ids(proj, {"Gone::2026-05-15": {
            "gtask_id": "u", "orbit_id": "deadbeef",
            "snapshot": {"desc": "Gone", "date": "2026-05-15"}
        }})
        monkeypatch.setattr(gimport, "_load_config", lambda: {"reminders_list": "L"})
        monkeypatch.setattr(gimport, "_reminders_list_name", lambda c: "L")
        monkeypatch.setattr(gimport, "_reminders_app_running", lambda: True)
        # Empty Reminders → item disappeared
        monkeypatch.setattr(gimport, "_fetch_all_reminders", lambda lst: [])
        res = gimport.import_changes_for_project(proj, dry_run=False)
        assert res["deleted"] == 1
        assert _read_back(proj)["tasks"][0]["status"] == "cancelled"

    def test_dry_run_does_not_persist(self, tmp_path, monkeypatch):
        proj = _make_proj(tmp_path, "🌀dry")
        _seed_agenda(proj, {"tasks": [{
            "desc": "Foo", "date": "2026-05-15", "status": "pending",
            "orbit_id": "ab12cd34"
        }]})
        _seed_ids(proj, {"Foo::2026-05-15": {
            "gtask_id": "u", "orbit_id": "ab12cd34",
            "snapshot": {"desc": "Foo", "date": "2026-05-15"}
        }})
        monkeypatch.setattr(gimport, "_load_config", lambda: {"reminders_list": "L"})
        monkeypatch.setattr(gimport, "_reminders_list_name", lambda c: "L")
        monkeypatch.setattr(gimport, "_reminders_app_running", lambda: True)
        monkeypatch.setattr(gimport, "_fetch_all_reminders", lambda lst: [{
            "uid": "u", "name": "[dry] ✅ Foo", "due_iso": "2026-05-15T09:00",
            "completed": True, "body": "[orbit:ab12cd34]",
            "orbit_id": "ab12cd34", "occurrence": None,
        }])
        gimport.import_changes_for_project(proj, dry_run=True)
        # Status untouched on disk
        assert _read_back(proj)["tasks"][0]["status"] == "pending"

    def test_no_orbit_id_skipped(self, tmp_path, monkeypatch):
        """Items without an orbit-id (legacy or never synced) are not touched."""
        proj = _make_proj(tmp_path, "🌀nox")
        _seed_agenda(proj, {"tasks": [{
            "desc": "Untagged", "date": "2026-05-15", "status": "pending",
            "orbit_id": None,
        }]})
        monkeypatch.setattr(gimport, "_load_config", lambda: {"reminders_list": "L"})
        monkeypatch.setattr(gimport, "_reminders_list_name", lambda c: "L")
        monkeypatch.setattr(gimport, "_reminders_app_running", lambda: True)
        monkeypatch.setattr(gimport, "_fetch_all_reminders", lambda lst: [])
        res = gimport.import_changes_for_project(proj, dry_run=False)
        assert res["modified"] == 0 and res["deleted"] == 0

    def test_not_running_returns_zero(self, tmp_path, monkeypatch):
        proj = _make_proj(tmp_path)
        monkeypatch.setattr(gimport, "_reminders_app_running", lambda: False)
        res = gimport.import_changes_for_project(proj, dry_run=False)
        assert res["modified"] == 0

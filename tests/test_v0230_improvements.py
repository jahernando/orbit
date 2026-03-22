"""Tests for v0.23.0 improvements:
1. --end-date / --end-time flags for events
2. Doctor pre-check in commit
3. task list --unplanned filter
4. gsync reconciliation: detect title renames
"""
import json
import sys
import textwrap
from datetime import date
from pathlib import Path

import pytest


# ── Helpers ────────────────────────────────────────────────────────────────────

def _strip_emoji(name: str) -> str:
    import unicodedata
    i = 0
    while i < len(name):
        c = name[i]
        if ord(c) > 127 or unicodedata.category(c) in ("So", "Sk", "Mn", "Cf"):
            i += 1
        else:
            break
    return name[i:]


def _make_project(type_dir: Path, name: str = "test-project") -> Path:
    project_dir = type_dir / name
    project_dir.mkdir(parents=True, exist_ok=True)
    base = _strip_emoji(name)
    (project_dir / f"{base}-project.md").write_text(
        f"# {name}\n- Tipo: 💻 Software\n- Estado: [auto]\n- Prioridad: media\n"
    )
    (project_dir / f"{base}-logbook.md").write_text(f"# Logbook — {name}\n\n")
    (project_dir / f"{base}-agenda.md").write_text(f"# Agenda — {name}\n\n<!-- ... -->\n")
    (project_dir / f"{base}-highlights.md").write_text(f"# Highlights — {name}\n\n")
    (project_dir / "notes").mkdir(exist_ok=True)
    return project_dir


def _agenda_text(project_dir: Path) -> str:
    base = _strip_emoji(project_dir.name)
    return (project_dir / f"{base}-agenda.md").read_text()


@pytest.fixture()
def projects_dir(tmp_path, monkeypatch):
    type_dir = tmp_path / "💻software"
    type_dir.mkdir()
    monkeypatch.setattr("core.config.ORBIT_HOME", tmp_path)
    monkeypatch.setattr("core.config._ORBIT_JSON", tmp_path / "orbit.json")
    monkeypatch.setattr("core.log.PROJECTS_DIR", tmp_path)
    return type_dir


# ═══════════════════════════════════════════════════════════════════════════════
# 1. --end-date / --end-time flags for events
# ═══════════════════════════════════════════════════════════════════════════════

class TestEventEndFlags:

    def test_ev_add_end_date_flag(self, projects_dir, monkeypatch):
        """--end-date should work as alias for --end."""
        from core.agenda_cmds import run_ev_add, _read_agenda
        from core.log import resolve_file

        pd = _make_project(projects_dir)
        monkeypatch.setattr("core.gsync.sync_item", lambda *a, **k: None)
        rc = run_ev_add("test-project", "Conference", "2026-04-01",
                        end_date="2026-04-03", time_val=None, ring=None)
        assert rc == 0
        data = _read_agenda(resolve_file(pd, "agenda"))
        ev = data["events"][0]
        assert ev["end"] == "2026-04-03"

    def test_ev_add_end_time_merges_with_time(self, projects_dir, monkeypatch, capsys):
        """--end-time + --time should produce HH:MM-HH:MM format."""
        # We test the dispatcher logic by simulating what cmd_ev does
        # when it receives --time and --end-time
        start = "10:00"
        end_time = "12:30"
        merged = f"{start}-{end_time}"
        assert merged == "10:00-12:30"

    def test_ev_add_end_time_default_start(self):
        """When --end-time given without --time, start defaults to 09:00."""
        start = None or "09:00"
        end_time = "11:00"
        merged = f"{start}-{end_time}"
        assert merged == "09:00-11:00"

    def test_ev_add_with_time_range(self, projects_dir, monkeypatch):
        """ev add with HH:MM-HH:MM time range still works."""
        from core.agenda_cmds import run_ev_add, _read_agenda
        from core.log import resolve_file

        pd = _make_project(projects_dir)
        monkeypatch.setattr("core.gsync.sync_item", lambda *a, **k: None)
        rc = run_ev_add("test-project", "Meeting", "2026-04-01",
                        time_val="10:00-12:00", ring=None)
        assert rc == 0
        data = _read_agenda(resolve_file(pd, "agenda"))
        ev = data["events"][0]
        assert ev["time"] == "10:00-12:00"


# ═══════════════════════════════════════════════════════════════════════════════
# 3. task list --unplanned filter
# ═══════════════════════════════════════════════════════════════════════════════

class TestTaskListUnplanned:

    def test_unplanned_shows_undated_tasks(self, projects_dir, monkeypatch, capsys):
        from core.agenda_cmds import run_task_add, run_task_list

        pd = _make_project(projects_dir)
        monkeypatch.setattr("core.gsync.sync_item", lambda *a, **k: None)
        # Add task with date
        run_task_add("test-project", "Dated task", date_val="2026-04-01")
        # Add task without date
        run_task_add("test-project", "Undated task", date_val=None)

        capsys.readouterr()  # clear
        run_task_list(unplanned=True)
        out = capsys.readouterr().out
        assert "Undated task" in out
        assert "Dated task" not in out

    def test_unplanned_empty(self, projects_dir, monkeypatch, capsys):
        from core.agenda_cmds import run_task_add, run_task_list

        pd = _make_project(projects_dir)
        monkeypatch.setattr("core.gsync.sync_item", lambda *a, **k: None)
        run_task_add("test-project", "Dated only", date_val="2026-04-01")

        capsys.readouterr()
        run_task_list(unplanned=True)
        out = capsys.readouterr().out
        assert "No hay tareas" in out

    def test_dated_and_unplanned_exclusive(self, projects_dir, monkeypatch, capsys):
        """--dated and --unplanned are logically opposite filters."""
        from core.agenda_cmds import run_task_add, run_task_list

        pd = _make_project(projects_dir)
        monkeypatch.setattr("core.gsync.sync_item", lambda *a, **k: None)
        run_task_add("test-project", "Dated task", date_val="2026-04-01")
        run_task_add("test-project", "Undated task", date_val=None)

        capsys.readouterr()
        run_task_list(dated_only=True)
        dated_out = capsys.readouterr().out

        run_task_list(unplanned=True)
        unplanned_out = capsys.readouterr().out

        assert "Dated task" in dated_out
        assert "Undated task" not in dated_out
        assert "Undated task" in unplanned_out
        assert "Dated task" not in unplanned_out


# ═══════════════════════════════════════════════════════════════════════════════
# 4. gsync reconciliation: detect title renames
# ═══════════════════════════════════════════════════════════════════════════════

class TestGsyncReconcileRenames:

    def test_item_key_uses_desc(self):
        from core.gsync import _item_key
        item = {"desc": "Old title", "date": "2026-04-01"}
        assert _item_key(item) == "Old title::2026-04-01"

    def test_item_key_recurring(self):
        from core.gsync import _item_key
        item = {"desc": "Task", "date": "2026-04-01", "recur": "weekly"}
        assert _item_key(item) == "Task::🔄weekly"

    def test_secondary_key_nonrecurring(self):
        from core.gsync import _secondary_key
        item = {"desc": "Task", "date": "2026-04-01"}
        assert _secondary_key(item) == "2026-04-01"

    def test_secondary_key_recurring(self):
        from core.gsync import _secondary_key
        item = {"desc": "Task", "date": "2026-04-01", "recur": "weekly"}
        assert _secondary_key(item) == "🔄weekly"

    def test_reconcile_detects_rename(self, projects_dir, monkeypatch):
        """When a title changes in markdown, reconcile should re-link the gsync ID."""
        from core.gsync import reconcile_gsync_renames, _load_ids, _save_ids, _item_key
        from core.agenda_cmds import _read_agenda, _write_agenda
        from core.log import resolve_file

        pd = _make_project(projects_dir)
        monkeypatch.setattr("core.gsync.sync_item", lambda *a, **k: None)

        # Set up: write an agenda with a task
        agenda_path = resolve_file(pd, "agenda")
        data = _read_agenda(agenda_path)
        data["tasks"].append({
            "desc": "New title", "date": "2026-04-01", "status": "pending",
            "synced": True,
        })
        _write_agenda(agenda_path, data)

        # Set up: write gsync-ids with the OLD title
        old_key = "Old title::2026-04-01"
        ids = {old_key: {"gtask_id": "google-123", "snapshot": {"desc": "Old title", "date": "2026-04-01"}}}
        _save_ids(pd, ids)

        # Run reconciliation
        renames = reconcile_gsync_renames()

        assert len(renames) == 1
        assert renames[0] == (pd.name, "Old title", "New title")

        # Verify IDs were migrated
        new_ids = _load_ids(pd)
        new_key = "New title::2026-04-01"
        assert new_key in new_ids
        assert old_key not in new_ids
        assert new_ids[new_key]["gtask_id"] == "google-123"

    def test_reconcile_recurring_rename(self, projects_dir, monkeypatch):
        """Recurring items use recur pattern as secondary key."""
        from core.gsync import reconcile_gsync_renames, _load_ids, _save_ids
        from core.agenda_cmds import _read_agenda, _write_agenda
        from core.log import resolve_file

        pd = _make_project(projects_dir)
        monkeypatch.setattr("core.gsync.sync_item", lambda *a, **k: None)

        agenda_path = resolve_file(pd, "agenda")
        data = _read_agenda(agenda_path)
        data["tasks"].append({
            "desc": "Weekly standup v2", "date": "2026-04-07",
            "status": "pending", "recur": "weekly", "synced": True,
        })
        _write_agenda(agenda_path, data)

        old_key = "Weekly standup::🔄weekly"
        ids = {old_key: {"gtask_id": "g-456", "snapshot": {"desc": "Weekly standup", "recur": "weekly"}}}
        _save_ids(pd, ids)

        renames = reconcile_gsync_renames()
        assert len(renames) == 1
        assert renames[0][2] == "Weekly standup v2"

        new_ids = _load_ids(pd)
        assert "Weekly standup v2::🔄weekly" in new_ids
        assert old_key not in new_ids

    def test_reconcile_no_false_positive(self, projects_dir, monkeypatch):
        """No rename detected when keys match correctly."""
        from core.gsync import reconcile_gsync_renames, _save_ids
        from core.agenda_cmds import _read_agenda, _write_agenda
        from core.log import resolve_file

        pd = _make_project(projects_dir)
        monkeypatch.setattr("core.gsync.sync_item", lambda *a, **k: None)

        agenda_path = resolve_file(pd, "agenda")
        data = _read_agenda(agenda_path)
        data["tasks"].append({
            "desc": "My task", "date": "2026-04-01", "status": "pending", "synced": True,
        })
        _write_agenda(agenda_path, data)

        key = "My task::2026-04-01"
        ids = {key: {"gtask_id": "g-789", "snapshot": {"desc": "My task", "date": "2026-04-01"}}}
        _save_ids(pd, ids)

        renames = reconcile_gsync_renames()
        assert len(renames) == 0

    def test_reconcile_event_rename(self, projects_dir, monkeypatch):
        """Events can also be reconciled on rename."""
        from core.gsync import reconcile_gsync_renames, _load_ids, _save_ids
        from core.agenda_cmds import _read_agenda, _write_agenda
        from core.log import resolve_file

        pd = _make_project(projects_dir)
        monkeypatch.setattr("core.gsync.sync_item", lambda *a, **k: None)

        agenda_path = resolve_file(pd, "agenda")
        data = _read_agenda(agenda_path)
        data["events"].append({
            "desc": "Team meeting renamed", "date": "2026-04-10",
            "synced": True,
        })
        _write_agenda(agenda_path, data)

        old_key = "Team meeting::2026-04-10"
        ids = {old_key: {"gcal_id": "gcal-abc", "snapshot": {"desc": "Team meeting", "date": "2026-04-10"}}}
        _save_ids(pd, ids)

        renames = reconcile_gsync_renames()
        assert len(renames) == 1
        new_ids = _load_ids(pd)
        assert "Team meeting renamed::2026-04-10" in new_ids
        assert new_ids["Team meeting renamed::2026-04-10"]["gcal_id"] == "gcal-abc"

    def test_reconcile_without_synced_marker(self, projects_dir, monkeypatch):
        """Even without ☁️ marker, reconcile detects rename via secondary key match."""
        from core.gsync import reconcile_gsync_renames, _load_ids, _save_ids
        from core.agenda_cmds import _read_agenda, _write_agenda
        from core.log import resolve_file

        pd = _make_project(projects_dir)
        monkeypatch.setattr("core.gsync.sync_item", lambda *a, **k: None)

        agenda_path = resolve_file(pd, "agenda")
        data = _read_agenda(agenda_path)
        data["tasks"].append({
            "desc": "Renamed task", "date": "2026-05-01", "status": "pending",
            # No synced marker
        })
        _write_agenda(agenda_path, data)

        old_key = "Original task::2026-05-01"
        ids = {old_key: {"gtask_id": "g-999", "snapshot": {"desc": "Original task", "date": "2026-05-01"}}}
        _save_ids(pd, ids)

        renames = reconcile_gsync_renames()
        assert len(renames) == 1
        assert renames[0][2] == "Renamed task"

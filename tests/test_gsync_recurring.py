"""Tests for recurring event sync: stable keys, deduplication, and drop behavior."""
import json
import pytest
from core.gsync import _item_key, _make_snapshot


# ── _item_key: stable keys for recurring items ──────────────────────────────

class TestItemKeyRecurring:

    def test_non_recurring_uses_date(self):
        item = {"desc": "Meeting", "date": "2026-03-20"}
        assert _item_key(item) == "Meeting::2026-03-20"

    def test_recurring_uses_recur_pattern(self):
        item = {"desc": "Standup", "date": "2026-03-20", "recur": "weekly"}
        assert _item_key(item) == "Standup::🔄weekly"

    def test_recurring_key_stable_across_date_changes(self):
        item1 = {"desc": "Standup", "date": "2026-03-20", "recur": "weekly"}
        item2 = {"desc": "Standup", "date": "2026-03-27", "recur": "weekly"}
        assert _item_key(item1) == _item_key(item2)

    def test_different_recur_patterns_different_keys(self):
        item_w = {"desc": "Sync", "date": "2026-03-20", "recur": "weekly"}
        item_d = {"desc": "Sync", "date": "2026-03-20", "recur": "daily"}
        assert _item_key(item_w) != _item_key(item_d)

    def test_recurring_daily(self):
        item = {"desc": "Plan day", "date": "2026-03-17", "recur": "daily"}
        assert _item_key(item) == "Plan day::🔄daily"

    def test_recurring_every_2_weeks(self):
        item = {"desc": "Biweekly", "date": "2026-03-18", "recur": "every-2-weeks"}
        assert _item_key(item) == "Biweekly::🔄every-2-weeks"

    def test_recurring_with_none_recur_uses_date(self):
        """recur=None should behave like non-recurring."""
        item = {"desc": "One-off", "date": "2026-03-20", "recur": None}
        assert _item_key(item) == "One-off::2026-03-20"

    def test_recurring_with_empty_recur_uses_date(self):
        """recur='' should behave like non-recurring."""
        item = {"desc": "One-off", "date": "2026-03-20", "recur": ""}
        assert _item_key(item) == "One-off::2026-03-20"


# ── Drop: interactive recurring prompts ──────────────────────────────────────

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


def _make_project(type_dir, name="test-project"):
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


@pytest.fixture()
def projects_dir(tmp_path, monkeypatch):
    type_dir = tmp_path / "💻software"
    type_dir.mkdir()
    monkeypatch.setattr("core.config.ORBIT_HOME", tmp_path)
    monkeypatch.setattr("core.config._ORBIT_JSON", tmp_path / "orbit.json")
    monkeypatch.setattr("core.log.PROJECTS_DIR", tmp_path)
    return type_dir


@pytest.fixture()
def proj(projects_dir):
    return _make_project(projects_dir, "💻test-project")


# ── ev drop: force advances recurring, no Google delete ──────────────────────

class TestEvDropRecurring:

    def test_force_advances_recurring_event(self, proj, projects_dir, capsys):
        """--force on recurring event advances to next occurrence (safe default)."""
        from core.agenda_cmds import run_ev_add, run_ev_drop, _read_agenda
        run_ev_add("test-project", "Weekly standup", "2026-03-09", recur="weekly")
        rc = run_ev_drop("test-project", "Weekly standup", force=True)
        assert rc == 0
        data = _read_agenda(proj / "test-project-agenda.md")
        assert len(data["events"]) == 1
        assert data["events"][0]["date"] == "2026-03-16"
        assert data["events"][0]["recur"] == "weekly"
        out = capsys.readouterr().out
        assert "próxima: 2026-03-16" in out

    def test_interactive_occurrence_advances(self, proj, projects_dir, monkeypatch, capsys):
        """Answering 'o' advances to next occurrence."""
        from core.agenda_cmds import run_ev_add, run_ev_drop, _read_agenda
        run_ev_add("test-project", "Biweekly sync", "2026-03-10", recur="every-2-weeks")
        monkeypatch.setattr("builtins.input", lambda _: "o")
        monkeypatch.setattr("sys.stdin", type("FakeTTY", (), {"isatty": lambda self: True})())
        rc = run_ev_drop("test-project", "Biweekly sync")
        assert rc == 0
        data = _read_agenda(proj / "test-project-agenda.md")
        assert len(data["events"]) == 1
        assert data["events"][0]["date"] == "2026-03-24"
        out = capsys.readouterr().out
        assert "próxima: 2026-03-24" in out

    def test_interactive_series_deletes_all(self, proj, projects_dir, monkeypatch, capsys):
        """Answering 's' removes the event entirely (no next occurrence)."""
        from core.agenda_cmds import run_ev_add, run_ev_drop, _read_agenda
        run_ev_add("test-project", "Daily check", "2026-03-17", recur="daily")
        monkeypatch.setattr("builtins.input", lambda _: "s")
        monkeypatch.setattr("sys.stdin", type("FakeTTY", (), {"isatty": lambda self: True})())
        rc = run_ev_drop("test-project", "Daily check")
        assert rc == 0
        data = _read_agenda(proj / "test-project-agenda.md")
        assert len(data["events"]) == 0
        out = capsys.readouterr().out
        assert "Serie eliminada" in out

    def test_interactive_cancel_aborts(self, proj, projects_dir, monkeypatch, capsys):
        """Answering 'c' cancels the drop."""
        from core.agenda_cmds import run_ev_add, run_ev_drop, _read_agenda
        run_ev_add("test-project", "Keep me", "2026-03-17", recur="weekly")
        monkeypatch.setattr("builtins.input", lambda _: "c")
        monkeypatch.setattr("sys.stdin", type("FakeTTY", (), {"isatty": lambda self: True})())
        rc = run_ev_drop("test-project", "Keep me")
        assert rc == 0
        data = _read_agenda(proj / "test-project-agenda.md")
        assert len(data["events"]) == 1
        out = capsys.readouterr().out
        assert "Cancelado" in out

    def test_nonrecurring_force_deletes(self, proj, projects_dir):
        """--force on non-recurring event deletes it completely."""
        from core.agenda_cmds import run_ev_add, run_ev_drop, _read_agenda
        run_ev_add("test-project", "One-off", "2026-03-20")
        rc = run_ev_drop("test-project", "One-off", force=True)
        assert rc == 0
        data = _read_agenda(proj / "test-project-agenda.md")
        assert data["events"] == []


# ── task drop: interactive recurring prompts ─────────────────────────────────

class TestTaskDropRecurring:

    def test_force_advances_recurring_task(self, proj, projects_dir, capsys):
        """--force on recurring task advances to next occurrence."""
        from core.agenda_cmds import run_task_add, run_task_drop, _read_agenda
        run_task_add("test-project", "Weekly review", date_val="2026-03-09", recur="weekly")
        rc = run_task_drop("test-project", "Weekly review", force=True)
        assert rc == 0
        data = _read_agenda(proj / "test-project-agenda.md")
        pending = [t for t in data["tasks"] if t["status"] == "pending"]
        assert len(pending) == 1
        assert pending[0]["date"] == "2026-03-16"
        assert pending[0]["recur"] == "weekly"

    def test_interactive_occurrence_advances(self, proj, projects_dir, monkeypatch, capsys):
        """Answering 'o' advances task to next occurrence."""
        from core.agenda_cmds import run_task_add, run_task_drop, _read_agenda
        run_task_add("test-project", "Daily plan", date_val="2026-03-17", recur="daily")
        monkeypatch.setattr("builtins.input", lambda _: "o")
        monkeypatch.setattr("sys.stdin", type("FakeTTY", (), {"isatty": lambda self: True})())
        rc = run_task_drop("test-project", "Daily plan")
        assert rc == 0
        data = _read_agenda(proj / "test-project-agenda.md")
        pending = [t for t in data["tasks"] if t["status"] == "pending"]
        assert len(pending) == 1
        assert pending[0]["date"] == "2026-03-18"

    def test_interactive_series_deletes_all(self, proj, projects_dir, monkeypatch, capsys):
        """Answering 's' cancels the task with no next occurrence."""
        from core.agenda_cmds import run_task_add, run_task_drop, _read_agenda
        run_task_add("test-project", "Monthly report", date_val="2026-03-01", recur="monthly")
        monkeypatch.setattr("builtins.input", lambda _: "s")
        monkeypatch.setattr("sys.stdin", type("FakeTTY", (), {"isatty": lambda self: True})())
        rc = run_task_drop("test-project", "Monthly report")
        assert rc == 0
        data = _read_agenda(proj / "test-project-agenda.md")
        pending = [t for t in data["tasks"] if t["status"] == "pending"]
        assert len(pending) == 0
        out = capsys.readouterr().out
        assert "serie cancelada" in out

    def test_interactive_cancel_aborts(self, proj, projects_dir, monkeypatch, capsys):
        """Answering 'c' cancels the drop."""
        from core.agenda_cmds import run_task_add, run_task_drop, _read_agenda
        run_task_add("test-project", "Keep task", date_val="2026-03-17", recur="weekly")
        monkeypatch.setattr("builtins.input", lambda _: "c")
        monkeypatch.setattr("sys.stdin", type("FakeTTY", (), {"isatty": lambda self: True})())
        rc = run_task_drop("test-project", "Keep task")
        assert rc == 0
        data = _read_agenda(proj / "test-project-agenda.md")
        pending = [t for t in data["tasks"] if t["status"] == "pending"]
        assert len(pending) == 1
        out = capsys.readouterr().out
        assert "Cancelado" in out


# ── Deduplication of recurring items in sync ─────────────────────────────────

class TestRecurringDedup:
    """Test that _item_key produces the same key for duplicate recurring entries,
    enabling deduplication during sync."""

    def test_duplicate_recurring_events_same_key(self):
        ev1 = {"desc": "reunion semanal", "date": "2026-03-20", "recur": "weekly"}
        ev2 = {"desc": "reunion semanal", "date": "2026-03-27", "recur": "weekly"}
        assert _item_key(ev1) == _item_key(ev2)

    def test_duplicate_recurring_tasks_same_key(self):
        t1 = {"desc": "Plan day", "date": "2026-03-17", "recur": "daily", "status": "pending"}
        t2 = {"desc": "Plan day", "date": "2026-03-18", "recur": "daily", "status": "pending"}
        assert _item_key(t1) == _item_key(t2)

    def test_different_desc_different_key(self):
        ev1 = {"desc": "meeting A", "date": "2026-03-20", "recur": "weekly"}
        ev2 = {"desc": "meeting B", "date": "2026-03-20", "recur": "weekly"}
        assert _item_key(ev1) != _item_key(ev2)

    def test_recurring_vs_nonrecurring_different_key(self):
        ev_recur = {"desc": "meeting", "date": "2026-03-20", "recur": "weekly"}
        ev_plain = {"desc": "meeting", "date": "2026-03-20"}
        assert _item_key(ev_recur) != _item_key(ev_plain)


# ── Key migration: old desc::date → new desc::🔄recur ────────────────────────

class TestKeyMigration:
    """Test that old-format keys (desc::date) can be migrated to new format."""

    def test_old_key_format(self):
        """Old format used date; new format uses recur pattern."""
        item = {"desc": "Standup", "date": "2026-03-20", "recur": "weekly"}
        old_key = f"{item['desc']}::{item['date']}"
        new_key = _item_key(item)
        assert old_key == "Standup::2026-03-20"
        assert new_key == "Standup::🔄weekly"
        assert old_key != new_key

    def test_migration_preserves_data(self):
        """Simulates the migration logic in _sync_events_for_project.
        Migration matches old_key = desc::date where date is the current agenda date.
        """
        ids = {
            "Standup::2026-03-20": {"gcal_id": "abc123", "snapshot": {"desc": "Standup"}},
            "One-off::2026-04-01": {"gcal_id": "xyz789", "snapshot": {"desc": "One-off"}},
        }
        events = [
            {"desc": "Standup", "date": "2026-03-20", "recur": "weekly"},
            {"desc": "One-off", "date": "2026-04-01"},
        ]

        # Simulate migration logic
        for ev in events:
            if not ev.get("recur"):
                continue
            new_key = _item_key(ev)
            if new_key in ids:
                continue
            old_key = f"{ev.get('desc', '')}::{ev.get('date', '')}"
            if old_key in ids:
                ids[new_key] = ids.pop(old_key)

        # Recurring event migrated to new key
        assert "Standup::🔄weekly" in ids
        assert "Standup::2026-03-20" not in ids
        assert ids["Standup::🔄weekly"]["gcal_id"] == "abc123"

        # Non-recurring event untouched
        assert "One-off::2026-04-01" in ids
        assert ids["One-off::2026-04-01"]["gcal_id"] == "xyz789"

    def test_migration_skips_if_new_key_exists(self):
        """If new-format key already exists, don't overwrite."""
        ids = {
            "Standup::2026-03-06": {"gcal_id": "old_id"},
            "Standup::🔄weekly": {"gcal_id": "new_id"},
        }
        events = [{"desc": "Standup", "date": "2026-03-13", "recur": "weekly"}]

        for ev in events:
            if not ev.get("recur"):
                continue
            new_key = _item_key(ev)
            if new_key in ids:
                continue
            old_key = f"{ev.get('desc', '')}::{ev.get('date', '')}"
            if old_key in ids:
                ids[new_key] = ids.pop(old_key)

        # New key preserved, old key untouched (different date, no match)
        assert ids["Standup::🔄weekly"]["gcal_id"] == "new_id"

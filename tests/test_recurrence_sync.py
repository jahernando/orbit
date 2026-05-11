"""Regression tests for the v0.29 recurring-occurrence sync bug.

When a recurring task/ms/reminder is completed or dropped, orbit advances the
local agenda to the next occurrence. Before the fix, only the old (done /
cancelled) item was pushed to Calendar — the new pending occurrence stayed
invisible until the next batch gsync. These tests pin down that both the old
AND the new occurrence are now passed to ``sync_item`` (old first, new second).
"""

from datetime import date
from pathlib import Path

import pytest


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


@pytest.fixture()
def sync_calls(monkeypatch):
    """Capture every (kind, status, date, desc) tuple passed to sync_item."""
    calls = []

    def fake_sync_item(project_dir, item, kind="task"):
        calls.append({
            "kind":   kind,
            "status": item.get("status"),
            "date":   item.get("date"),
            "desc":   item.get("desc"),
            "cancelled": item.get("cancelled"),
        })

    import core.gsync
    monkeypatch.setattr(core.gsync, "sync_item", fake_sync_item)
    return calls


# ── task done ─────────────────────────────────────────────────────────────────

class TestTaskDoneRecurringSync:
    def test_recurring_task_syncs_done_then_new_occurrence(
            self, proj, projects_dir, sync_calls):
        from core.agenda_cmds import run_task_add, run_task_done

        run_task_add("test-project", "Weekly standup",
                     date_val="2026-03-09", recur="weekly")
        sync_calls.clear()  # ignore the add-time sync

        run_task_done("test-project", "Weekly standup")

        kinds = [c["kind"] for c in sync_calls]
        statuses = [c["status"] for c in sync_calls]
        dates = [c["date"] for c in sync_calls]
        assert kinds == ["task", "task"]
        # Done first, new pending second — order matters so the calendar slot
        # is cleared before the next occurrence claims its identity.
        assert statuses == ["done", "pending"]
        assert dates == ["2026-03-09", "2026-03-16"]

    def test_nonrecurring_task_only_syncs_once(
            self, proj, projects_dir, sync_calls):
        from core.agenda_cmds import run_task_add, run_task_done

        run_task_add("test-project", "One-off", date_val="2026-03-09")
        sync_calls.clear()

        run_task_done("test-project", "One-off")

        assert [c["status"] for c in sync_calls] == ["done"]

    def test_recurring_past_until_only_syncs_done(
            self, proj, projects_dir, sync_calls):
        """When the next occurrence would fall past `until`, no new item is
        created → only the completed item is synced."""
        from core.agenda_cmds import run_task_add, run_task_done

        run_task_add("test-project", "Limited", date_val="2026-03-09",
                     recur="weekly", until="2026-03-10")
        sync_calls.clear()

        run_task_done("test-project", "Limited")

        assert [c["status"] for c in sync_calls] == ["done"]


# ── ms done ────────────────────────────────────────────────────────────────────

class TestMsDoneRecurringSync:
    def test_recurring_ms_syncs_done_then_new_occurrence(
            self, proj, projects_dir, sync_calls):
        from core.agenda_cmds import run_ms_add, run_ms_done

        run_ms_add("test-project", "Sprint review",
                   date_val="2026-03-09", recur="weekly")
        sync_calls.clear()

        run_ms_done("test-project", "Sprint review")

        kinds = [c["kind"] for c in sync_calls]
        statuses = [c["status"] for c in sync_calls]
        dates = [c["date"] for c in sync_calls]
        assert kinds == ["milestone", "milestone"]
        assert statuses == ["done", "pending"]
        assert dates == ["2026-03-09", "2026-03-16"]

    def test_nonrecurring_ms_only_syncs_once(
            self, proj, projects_dir, sync_calls):
        from core.agenda_cmds import run_ms_add, run_ms_done

        run_ms_add("test-project", "v1.0 release", date_val="2026-03-09")
        sync_calls.clear()

        run_ms_done("test-project", "v1.0 release")

        assert [c["status"] for c in sync_calls] == ["done"]


# ── task drop (recurring) ──────────────────────────────────────────────────────

class TestTaskDropRecurringSync:
    def test_recurring_drop_syncs_cancelled_then_new(
            self, proj, projects_dir, sync_calls):
        from core.agenda_cmds import run_task_add, run_task_drop

        run_task_add("test-project", "Weekly sync",
                     date_val="2026-03-09", recur="weekly")
        sync_calls.clear()

        run_task_drop("test-project", "Weekly sync", force=True)

        statuses = [c["status"] for c in sync_calls]
        dates = [c["date"] for c in sync_calls]
        assert statuses == ["cancelled", "pending"]
        assert dates == ["2026-03-09", "2026-03-16"]


# ── reminder drop (advance in-place) ──────────────────────────────────────────

class TestReminderAdvanceSync:
    def test_recurring_reminder_advance_syncs_new_date(
            self, proj, projects_dir, sync_calls):
        """Reminder drop on a recurring item advances the same dict in-place;
        it's a single sync_item call carrying the new date."""
        from core.agenda_cmds import run_reminder_add, run_reminder_drop

        run_reminder_add("test-project", "Hydrate",
                         date_val="2026-03-09", time_val="10:00",
                         recur="weekly")
        sync_calls.clear()

        run_reminder_drop("test-project", "Hydrate", force=True)

        assert len(sync_calls) == 1
        assert sync_calls[0]["kind"] == "reminder"
        assert sync_calls[0]["date"] == "2026-03-16"
        # Reminder advanced (un-cancelled) — must be the next pending date.
        assert sync_calls[0]["cancelled"] in (False, None)

    def test_recurring_reminder_past_until_falls_through_to_cancel(
            self, proj, projects_dir, sync_calls):
        """When the next occurrence is past `until`, drop cancels the series.
        That path does NOT sync (no advancement) — covered by the gsync
        batch flow, not by the on-demand path."""
        from core.agenda_cmds import run_reminder_add, run_reminder_drop

        run_reminder_add("test-project", "Bounded",
                         date_val="2026-03-09", time_val="10:00",
                         recur="weekly", until="2026-03-10")
        sync_calls.clear()

        run_reminder_drop("test-project", "Bounded", force=True)

        # No sync_item triggered along the advance path — the cancel path is
        # the legacy behaviour for reminders.
        assert sync_calls == []

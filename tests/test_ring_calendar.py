"""Tests for core/ring.py and Phase-7 extensions to core/calendar_sync.py."""

import importlib
from datetime import date, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ── helpers ────────────────────────────────────────────────────────────────────

def _make_project(tmp_path: Path, name: str = "alpha") -> Path:
    """Create a minimal new-format project directory."""
    d = tmp_path / name
    d.mkdir()
    (d / f"{name}-project.md").write_text(f"# {name}\n")
    (d / f"{name}-logbook.md").write_text("")
    (d / f"{name}-highlights.md").write_text("")
    (d / f"{name}-agenda.md").write_text(
        "## ✅ Tareas\n\n## 🏁 Hitos\n\n## 📅 Eventos\n"
    )
    return d


# ══════════════════════════════════════════════════════════════════════════════
# _parse_ring
# ══════════════════════════════════════════════════════════════════════════════

from core.ring import _parse_ring, resolve_ring_datetime


class TestParseRing:
    def test_relative_days(self):
        r = _parse_ring("1d")
        assert r == {"type": "relative", "unit": "d", "n": 1}

    def test_relative_hours(self):
        r = _parse_ring("3h")
        assert r == {"type": "relative", "unit": "h", "n": 3}

    def test_absolute_datetime(self):
        r = _parse_ring("2026-04-01 09:00")
        assert r == {"type": "absolute", "date": "2026-04-01", "time": "09:00"}

    def test_absolute_midnight(self):
        r = _parse_ring("2026-12-31 00:00")
        assert r == {"type": "absolute", "date": "2026-12-31", "time": "00:00"}

    def test_multi_digit_days(self):
        r = _parse_ring("14d")
        assert r == {"type": "relative", "unit": "d", "n": 14}

    def test_invalid_returns_none(self):
        assert _parse_ring("bad") is None
        assert _parse_ring("") is None
        assert _parse_ring("1w") is None          # 'w' is not a valid unit
        assert _parse_ring("2026-04-01") is None  # date without time

    def test_whitespace_stripped(self):
        r = _parse_ring("  2d  ")
        assert r == {"type": "relative", "unit": "d", "n": 2}


# ══════════════════════════════════════════════════════════════════════════════
# resolve_ring_datetime
# ══════════════════════════════════════════════════════════════════════════════

class TestResolveRingDatetime:
    def test_absolute(self):
        dt = resolve_ring_datetime("2026-04-05", "2026-04-01 14:30")
        assert dt == datetime(2026, 4, 1, 14, 30)

    def test_relative_days_no_due_time(self):
        # due_date 2026-04-05, anchor = 09:00, minus 1 day → 2026-04-04 09:00
        dt = resolve_ring_datetime("2026-04-05", "1d")
        assert dt == datetime(2026, 4, 4, 9, 0)

    def test_relative_days_with_due_time(self):
        # due at 15:00, minus 2 days → 2026-04-03 15:00
        dt = resolve_ring_datetime("2026-04-05", "2d", "15:00")
        assert dt == datetime(2026, 4, 3, 15, 0)

    def test_relative_hours_no_due_time(self):
        # anchor = 09:00, minus 2h → 07:00
        dt = resolve_ring_datetime("2026-04-05", "2h")
        assert dt == datetime(2026, 4, 5, 7, 0)

    def test_relative_hours_with_due_time(self):
        # due at 10:00, minus 3h → 07:00
        dt = resolve_ring_datetime("2026-04-05", "3h", "10:00")
        assert dt == datetime(2026, 4, 5, 7, 0)

    def test_relative_hours_crosses_midnight(self):
        # due at 01:00, minus 3h → previous day 22:00
        dt = resolve_ring_datetime("2026-04-05", "3h", "01:00")
        assert dt == datetime(2026, 4, 4, 22, 0)

    def test_invalid_ring_returns_none(self):
        assert resolve_ring_datetime("2026-04-05", "bad") is None

    def test_invalid_due_date_returns_none(self):
        assert resolve_ring_datetime("not-a-date", "1d") is None

    def test_malformed_due_time_falls_back_to_0900(self):
        # invalid due_time → fallback to 09:00
        dt = resolve_ring_datetime("2026-04-05", "1h", "99:99")
        assert dt == datetime(2026, 4, 5, 8, 0)


# ══════════════════════════════════════════════════════════════════════════════
# _tasks_ringing_on
# ══════════════════════════════════════════════════════════════════════════════

from core.ring import _tasks_ringing_on


class TestTasksRingingOn:
    def _write_agenda(self, project_dir: Path, content: str):
        name = project_dir.name
        (project_dir / f"{name}-agenda.md").write_text(content)

    def test_finds_task_ringing_today(self, tmp_path):
        pd = _make_project(tmp_path)
        # task due 2026-04-05, ring 1d → fires 2026-04-04
        self._write_agenda(pd, (
            "## ✅ Tareas\n"
            "- [ ] Revisar datos (2026-04-05) [ring:1d]\n"
            "\n## 🏁 Hitos\n\n## 📅 Eventos\n"
        ))
        results = _tasks_ringing_on(pd, date(2026, 4, 4))
        assert len(results) == 1
        assert results[0]["desc"] == "Revisar datos"
        assert results[0]["ring"] == "1d"

    def test_no_task_for_wrong_day(self, tmp_path):
        pd = _make_project(tmp_path)
        self._write_agenda(pd, (
            "## ✅ Tareas\n"
            "- [ ] Revisar datos (2026-04-05) [ring:1d]\n"
            "\n## 🏁 Hitos\n\n## 📅 Eventos\n"
        ))
        results = _tasks_ringing_on(pd, date(2026, 4, 3))
        assert results == []

    def test_skips_completed_task(self, tmp_path):
        pd = _make_project(tmp_path)
        self._write_agenda(pd, (
            "## ✅ Tareas\n"
            "- [x] Revisar datos (2026-04-05) [ring:1d]\n"
            "\n## 🏁 Hitos\n\n## 📅 Eventos\n"
        ))
        results = _tasks_ringing_on(pd, date(2026, 4, 4))
        assert results == []

    def test_skips_task_without_ring(self, tmp_path):
        pd = _make_project(tmp_path)
        self._write_agenda(pd, (
            "## ✅ Tareas\n"
            "- [ ] Sin ring (2026-04-05)\n"
            "\n## 🏁 Hitos\n\n## 📅 Eventos\n"
        ))
        results = _tasks_ringing_on(pd, date(2026, 4, 4))
        assert results == []

    def test_skips_task_without_due_date(self, tmp_path):
        pd = _make_project(tmp_path)
        self._write_agenda(pd, (
            "## ✅ Tareas\n"
            "- [ ] Sin fecha [ring:1d]\n"
            "\n## 🏁 Hitos\n\n## 📅 Eventos\n"
        ))
        results = _tasks_ringing_on(pd, date(2026, 4, 4))
        assert results == []

    def test_absolute_ring(self, tmp_path):
        pd = _make_project(tmp_path)
        self._write_agenda(pd, (
            "## ✅ Tareas\n"
            "- [ ] Reunión anual (2026-06-01) [ring:2026-05-31 10:00]\n"
            "\n## 🏁 Hitos\n\n## 📅 Eventos\n"
        ))
        results = _tasks_ringing_on(pd, date(2026, 5, 31))
        assert len(results) == 1
        assert results[0]["ring_dt"] == datetime(2026, 5, 31, 10, 0)

    def test_multiple_tasks_same_day(self, tmp_path):
        pd = _make_project(tmp_path)
        self._write_agenda(pd, (
            "## ✅ Tareas\n"
            "- [ ] Tarea A (2026-04-05) [ring:1d]\n"
            "- [ ] Tarea B (2026-04-05) [ring:1d]\n"
            "\n## 🏁 Hitos\n\n## 📅 Eventos\n"
        ))
        results = _tasks_ringing_on(pd, date(2026, 4, 4))
        assert len(results) == 2

    def test_recur_field_included(self, tmp_path):
        pd = _make_project(tmp_path)
        self._write_agenda(pd, (
            "## ✅ Tareas\n"
            "- [ ] Tarea rec (2026-04-05) [recur:weekly] [ring:1d]\n"
            "\n## 🏁 Hitos\n\n## 📅 Eventos\n"
        ))
        results = _tasks_ringing_on(pd, date(2026, 4, 4))
        assert len(results) == 1
        assert results[0]["recur"] == "weekly"


# ══════════════════════════════════════════════════════════════════════════════
# _clear_ring
# ══════════════════════════════════════════════════════════════════════════════

from core.ring import _clear_ring


class TestClearRing:
    def test_clears_ring_attribute(self, tmp_path):
        pd = _make_project(tmp_path)
        (pd / "alpha-agenda.md").write_text(
            "## ✅ Tareas\n"
            "- [ ] Revisar datos (2026-04-05) [ring:1d]\n"
            "\n## 🏁 Hitos\n\n## 📅 Eventos\n"
        )
        _clear_ring(pd, 0)
        from core.agenda_cmds import _read_agenda
        data = _read_agenda(pd / "alpha-agenda.md")
        assert data["tasks"][0]["ring"] is None

    def test_out_of_bounds_index_is_noop(self, tmp_path):
        pd = _make_project(tmp_path)
        original = (pd / "alpha-agenda.md").read_text()
        _clear_ring(pd, 99)  # should not raise
        assert (pd / "alpha-agenda.md").read_text() == original


# ══════════════════════════════════════════════════════════════════════════════
# schedule_new_format_reminders
# ══════════════════════════════════════════════════════════════════════════════

import core.ring as ring_mod
from core.ring import schedule_new_format_reminders


class TestScheduleNewFormatReminders:
    def _patch_projects(self, tmp_path, monkeypatch):
        monkeypatch.setattr(ring_mod, "PROJECTS_DIR", tmp_path)

    def test_no_projects_returns_empty(self, tmp_path, monkeypatch):
        self._patch_projects(tmp_path, monkeypatch)
        result = schedule_new_format_reminders(date(2026, 4, 4))
        assert result == []

    def test_schedules_ringing_task(self, tmp_path, monkeypatch, capsys):
        self._patch_projects(tmp_path, monkeypatch)
        pd = _make_project(tmp_path, "alpha")
        (pd / "alpha-agenda.md").write_text(
            "## ✅ Tareas\n"
            "- [ ] Revisar datos (2026-04-05) [ring:1d]\n"
            "\n## 🏁 Hitos\n\n## 📅 Eventos\n"
        )
        with patch.object(ring_mod, "_schedule_reminder", return_value=True):
            scheduled = schedule_new_format_reminders(date(2026, 4, 4))

        assert len(scheduled) == 1
        assert scheduled[0]["desc"] == "Revisar datos"
        assert scheduled[0]["project"] == "alpha"

    def test_clears_ring_on_one_shot_task(self, tmp_path, monkeypatch):
        self._patch_projects(tmp_path, monkeypatch)
        pd = _make_project(tmp_path, "alpha")
        (pd / "alpha-agenda.md").write_text(
            "## ✅ Tareas\n"
            "- [ ] Revisar datos (2026-04-05) [ring:1d]\n"
            "\n## 🏁 Hitos\n\n## 📅 Eventos\n"
        )
        with patch.object(ring_mod, "_schedule_reminder", return_value=True):
            schedule_new_format_reminders(date(2026, 4, 4))

        from core.agenda_cmds import _read_agenda
        data = _read_agenda(pd / "alpha-agenda.md")
        assert data["tasks"][0]["ring"] is None

    def test_keeps_ring_on_recurring_task(self, tmp_path, monkeypatch):
        self._patch_projects(tmp_path, monkeypatch)
        pd = _make_project(tmp_path, "alpha")
        (pd / "alpha-agenda.md").write_text(
            "## ✅ Tareas\n"
            "- [ ] Revisar (2026-04-05) [recur:weekly] [ring:1d]\n"
            "\n## 🏁 Hitos\n\n## 📅 Eventos\n"
        )
        with patch.object(ring_mod, "_schedule_reminder", return_value=True):
            schedule_new_format_reminders(date(2026, 4, 4))

        from core.agenda_cmds import _read_agenda
        data = _read_agenda(pd / "alpha-agenda.md")
        assert data["tasks"][0]["ring"] == "1d"

    def test_skips_reminder_on_failure(self, tmp_path, monkeypatch, capsys):
        self._patch_projects(tmp_path, monkeypatch)
        pd = _make_project(tmp_path, "alpha")
        (pd / "alpha-agenda.md").write_text(
            "## ✅ Tareas\n"
            "- [ ] Revisar datos (2026-04-05) [ring:1d]\n"
            "\n## 🏁 Hitos\n\n## 📅 Eventos\n"
        )
        with patch.object(ring_mod, "_schedule_reminder", return_value=False):
            scheduled = schedule_new_format_reminders(date(2026, 4, 4))

        assert scheduled == []
        out = capsys.readouterr().out
        assert "No se pudo programar" in out

    def test_non_new_format_project_ignored(self, tmp_path, monkeypatch):
        """Old-format projects (no {name}-agenda.md) must be skipped."""
        self._patch_projects(tmp_path, monkeypatch)
        old = tmp_path / "old-project"
        old.mkdir()
        (old / "old-project-logbook.md").write_text("")
        # no old-project-agenda.md → not a new-format project

        with patch.object(ring_mod, "_schedule_reminder", return_value=True) as mock:
            result = schedule_new_format_reminders(date(2026, 4, 4))

        assert result == []
        mock.assert_not_called()

    def test_multiple_projects(self, tmp_path, monkeypatch):
        self._patch_projects(tmp_path, monkeypatch)
        for name in ("alpha", "beta"):
            pd = _make_project(tmp_path, name)
            (pd / f"{name}-agenda.md").write_text(
                "## ✅ Tareas\n"
                "- [ ] Tarea (2026-04-05) [ring:1d]\n"
                "\n## 🏁 Hitos\n\n## 📅 Eventos\n"
            )
        with patch.object(ring_mod, "_schedule_reminder", return_value=True):
            scheduled = schedule_new_format_reminders(date(2026, 4, 4))

        assert len(scheduled) == 2
        projects = {s["project"] for s in scheduled}
        assert projects == {"alpha", "beta"}


# ══════════════════════════════════════════════════════════════════════════════
# calendar_sync — _event_in_agenda
# ══════════════════════════════════════════════════════════════════════════════

from core.calendar_sync import _event_in_agenda, _sync_new_format


class TestEventInAgenda:
    def test_event_not_present(self, tmp_path):
        pd = _make_project(tmp_path)
        assert not _event_in_agenda(pd, "Reunión", "2026-04-05")

    def test_event_present(self, tmp_path):
        pd = _make_project(tmp_path)
        (pd / "alpha-agenda.md").write_text(
            "## ✅ Tareas\n\n## 🏁 Hitos\n\n"
            "## 📅 Eventos\n"
            "2026-04-05 — Reunión\n"
        )
        assert _event_in_agenda(pd, "Reunión", "2026-04-05")

    def test_different_date_not_match(self, tmp_path):
        pd = _make_project(tmp_path)
        (pd / "alpha-agenda.md").write_text(
            "## ✅ Tareas\n\n## 🏁 Hitos\n\n"
            "## 📅 Eventos\n"
            "2026-04-06 — Reunión\n"
        )
        assert not _event_in_agenda(pd, "Reunión", "2026-04-05")


# ══════════════════════════════════════════════════════════════════════════════
# calendar_sync — _sync_new_format
# ══════════════════════════════════════════════════════════════════════════════

class TestSyncNewFormat:
    def test_adds_event_to_agenda(self, tmp_path):
        pd = _make_project(tmp_path)
        result = _sync_new_format(pd, "Workshop AI", "2026-04-10", dry_run=False)
        assert result is True
        from core.agenda_cmds import _read_agenda
        data = _read_agenda(pd / "alpha-agenda.md")
        evs = data["events"]
        assert any(e["date"] == "2026-04-10" and e["desc"] == "Workshop AI"
                   for e in evs)

    def test_adds_logbook_entry(self, tmp_path):
        pd = _make_project(tmp_path)
        _sync_new_format(pd, "Workshop AI", "2026-04-10", dry_run=False)
        logbook = (pd / "alpha-logbook.md").read_text()
        assert "Workshop AI" in logbook
        assert "#apunte" in logbook

    def test_dry_run_does_not_write(self, tmp_path):
        pd = _make_project(tmp_path)
        original = (pd / "alpha-agenda.md").read_text()
        _sync_new_format(pd, "Workshop AI", "2026-04-10", dry_run=True)
        assert (pd / "alpha-agenda.md").read_text() == original

    def test_dry_run_prints_tilde(self, tmp_path, capsys):
        pd = _make_project(tmp_path)
        _sync_new_format(pd, "Workshop AI", "2026-04-10", dry_run=True)
        out = capsys.readouterr().out
        assert "~" in out

    def test_duplicate_returns_false(self, tmp_path):
        pd = _make_project(tmp_path)
        _sync_new_format(pd, "Workshop AI", "2026-04-10", dry_run=False)
        result = _sync_new_format(pd, "Workshop AI", "2026-04-10", dry_run=False)
        assert result is False

    def test_prints_checkmark_on_success(self, tmp_path, capsys):
        pd = _make_project(tmp_path)
        _sync_new_format(pd, "Workshop AI", "2026-04-10", dry_run=False)
        out = capsys.readouterr().out
        assert "✓" in out


# ══════════════════════════════════════════════════════════════════════════════
# calendar_sync — sync_events_to_logbooks (routing)
# ══════════════════════════════════════════════════════════════════════════════

import core.calendar_sync as cs_mod
from core.calendar_sync import sync_events_to_logbooks


class TestSyncEventsToLogbooks:
    """Integration-style tests for the routing logic."""

    def _patch(self, monkeypatch, tmp_path):
        """Patch PROJECTS_DIR in relevant modules."""
        import core.project as proj_mod
        monkeypatch.setattr(proj_mod, "PROJECTS_DIR", tmp_path)
        # _find_new_project uses core.project.PROJECTS_DIR
        # find_project uses core.log.PROJECTS_DIR
        import core.log as log_mod
        monkeypatch.setattr(log_mod, "PROJECTS_DIR", tmp_path)

    def test_new_format_routed_to_agenda(self, tmp_path, monkeypatch):
        self._patch(monkeypatch, tmp_path)
        pd = _make_project(tmp_path, "alpha")

        events = [{"title": "Conf", "description": "proyecto: alpha",
                   "project_name": "alpha", "start_time": "10:00"}]
        synced, skipped, not_found = sync_events_to_logbooks(
            events, date(2026, 4, 10), dry_run=False
        )
        assert synced == 1
        assert skipped == 0
        assert not_found == 0

        from core.agenda_cmds import _read_agenda
        data = _read_agenda(pd / "alpha-agenda.md")
        assert any(e["desc"] == "Conf" for e in data["events"])

    def test_event_without_project_skipped(self, tmp_path, monkeypatch):
        self._patch(monkeypatch, tmp_path)
        events = [{"title": "Free event", "description": "",
                   "project_name": None, "start_time": "09:00"}]
        synced, skipped, not_found = sync_events_to_logbooks(
            events, date(2026, 4, 10), dry_run=False
        )
        assert synced == 0
        assert skipped == 0
        assert not_found == 0

    def test_unknown_project_increments_not_found(self, tmp_path, monkeypatch, capsys):
        self._patch(monkeypatch, tmp_path)
        events = [{"title": "Conf", "description": "proyecto: ghost",
                   "project_name": "ghost", "start_time": "10:00"}]
        synced, skipped, not_found = sync_events_to_logbooks(
            events, date(2026, 4, 10), dry_run=False
        )
        assert not_found == 1
        assert synced == 0

    def test_duplicate_event_increments_skipped(self, tmp_path, monkeypatch):
        self._patch(monkeypatch, tmp_path)
        pd = _make_project(tmp_path, "alpha")

        events = [{"title": "Conf", "description": "proyecto: alpha",
                   "project_name": "alpha", "start_time": "10:00"}]
        # First sync
        sync_events_to_logbooks(events, date(2026, 4, 10), dry_run=False)
        # Second sync — should be a duplicate
        synced, skipped, not_found = sync_events_to_logbooks(
            events, date(2026, 4, 10), dry_run=False
        )
        assert synced == 0
        assert skipped == 1

    def test_dry_run_does_not_persist(self, tmp_path, monkeypatch):
        self._patch(monkeypatch, tmp_path)
        pd = _make_project(tmp_path, "alpha")
        original = (pd / "alpha-agenda.md").read_text()

        events = [{"title": "Conf", "description": "proyecto: alpha",
                   "project_name": "alpha", "start_time": "10:00"}]
        synced, skipped, not_found = sync_events_to_logbooks(
            events, date(2026, 4, 10), dry_run=True
        )
        assert (pd / "alpha-agenda.md").read_text() == original
        # synced still reports 1 (would have synced)
        assert synced == 1

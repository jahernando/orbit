"""Tests for startup_advance_past_recurring in core/agenda_cmds.py."""

import json
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest


@pytest.fixture
def project_dir(tmp_path, monkeypatch):
    """Create a minimal project with agenda.md."""
    # Setup workspace structure: type_dir/project_dir
    ws = tmp_path / "ws"
    ws.mkdir()
    type_dir = ws / "🌀investigacion"
    type_dir.mkdir()
    proj = type_dir / "🌀test-project"
    proj.mkdir()

    # Minimal orbit.json
    (ws / "orbit.json").write_text(json.dumps({
        "emoji": "🚀",
        "types": {"investigacion": "🌀"},
    }))

    monkeypatch.setattr("core.config.ORBIT_HOME", ws)
    monkeypatch.setattr("core.config.PROJECTS_DIR", ws)
    return proj


def _write_agenda(proj, content):
    (proj / "test-project-agenda.md").write_text(content)


def _read_agenda(proj):
    return (proj / "test-project-agenda.md").read_text()


def _past(days=5):
    return (date.today() - timedelta(days=days)).isoformat()


def _future(days=5):
    return (date.today() + timedelta(days=days)).isoformat()


def _today():
    return date.today().isoformat()


# ── Event auto-advance ────────────────────────────────────────────────────

class TestEventAutoAdvance:

    def test_past_biweekly_event_advanced(self, project_dir):
        from core.agenda_cmds import startup_advance_past_recurring
        past = _past(10)
        _write_agenda(project_dir, f"""\
## 📅 Eventos
{past} — Meeting ⏰12:00 🔄every-2-weeks 🔔5m

## ✅ Tareas

## 🏁 Hitos

## 💬 Recordatorios
""")
        with patch("core.config.iter_project_dirs", return_value=[project_dir]):
            result = startup_advance_past_recurring()

        assert len(result) == 1
        assert "Meeting" in result[0]
        # Verify the agenda was updated
        content = _read_agenda(project_dir)
        assert past not in content  # old date removed

    def test_today_event_not_advanced(self, project_dir):
        from core.agenda_cmds import startup_advance_past_recurring
        today = _today()
        _write_agenda(project_dir, f"""\
## 📅 Eventos
{today} — Meeting ⏰12:00 🔄weekly 🔔5m

## ✅ Tareas

## 🏁 Hitos

## 💬 Recordatorios
""")
        with patch("core.config.iter_project_dirs", return_value=[project_dir]):
            result = startup_advance_past_recurring()

        assert len(result) == 0

    def test_future_event_not_advanced(self, project_dir):
        from core.agenda_cmds import startup_advance_past_recurring
        future = _future()
        _write_agenda(project_dir, f"""\
## 📅 Eventos
{future} — Meeting ⏰12:00 🔄weekly 🔔5m

## ✅ Tareas

## 🏁 Hitos

## 💬 Recordatorios
""")
        with patch("core.config.iter_project_dirs", return_value=[project_dir]):
            result = startup_advance_past_recurring()

        assert len(result) == 0

    def test_non_recurring_event_ignored(self, project_dir):
        from core.agenda_cmds import startup_advance_past_recurring
        past = _past()
        _write_agenda(project_dir, f"""\
## 📅 Eventos
{past} — One-time meeting ⏰12:00

## ✅ Tareas

## 🏁 Hitos

## 💬 Recordatorios
""")
        with patch("core.config.iter_project_dirs", return_value=[project_dir]):
            result = startup_advance_past_recurring()

        assert len(result) == 0


# ── Task auto-advance ─────────────────────────────────────────────────────

class TestTaskAutoAdvance:

    def test_past_weekly_task_advanced(self, project_dir):
        from core.agenda_cmds import startup_advance_past_recurring
        past = _past(3)
        _write_agenda(project_dir, f"""\
## ✅ Tareas
- [ ] Weekly review ({past}) 🔄weekly

## 🏁 Hitos

## 📅 Eventos

## 💬 Recordatorios
""")
        with patch("core.config.iter_project_dirs", return_value=[project_dir]):
            result = startup_advance_past_recurring()

        assert len(result) == 1
        assert "Weekly review" in result[0]
        # Old task should be cancelled, new one appended
        content = _read_agenda(project_dir)
        assert "[-]" in content  # cancelled
        assert "[ ]" in content  # new pending

    def test_done_task_not_advanced(self, project_dir):
        from core.agenda_cmds import startup_advance_past_recurring
        past = _past()
        _write_agenda(project_dir, f"""\
## ✅ Tareas
- [x] Done task ({past}) 🔄weekly

## 🏁 Hitos

## 📅 Eventos

## 💬 Recordatorios
""")
        with patch("core.config.iter_project_dirs", return_value=[project_dir]):
            result = startup_advance_past_recurring()

        assert len(result) == 0


# ── Reminder auto-advance ────────────────────────────────────────────────

class TestReminderAutoAdvance:

    def test_past_reminder_advanced_in_place(self, project_dir):
        from core.agenda_cmds import startup_advance_past_recurring
        past = _past(3)
        _write_agenda(project_dir, f"""\
## 💬 Recordatorios
- Llamar al médico ({past}) ⏰10:00 🔄monthly

## ✅ Tareas

## 🏁 Hitos

## 📅 Eventos
""")
        with patch("core.config.iter_project_dirs", return_value=[project_dir]):
            result = startup_advance_past_recurring()

        assert len(result) == 1
        assert "Llamar al médico" in result[0]
        # Reminder advanced in-place (no cancelled copy)
        content = _read_agenda(project_dir)
        assert past not in content

    def test_cancelled_reminder_not_advanced(self, project_dir):
        from core.agenda_cmds import startup_advance_past_recurring
        past = _past()
        _write_agenda(project_dir, f"""\
## 💬 Recordatorios
- [-] Cancelled reminder ({past}) ⏰10:00 🔄weekly

## ✅ Tareas

## 🏁 Hitos

## 📅 Eventos
""")
        with patch("core.config.iter_project_dirs", return_value=[project_dir]):
            result = startup_advance_past_recurring()

        assert len(result) == 0


# ── Until limit ───────────────────────────────────────────────────────────

class TestUntilLimit:

    def test_series_ended(self, project_dir):
        from core.agenda_cmds import startup_advance_past_recurring
        past = _past(3)
        yesterday = _past(1)
        _write_agenda(project_dir, f"""\
## 📅 Eventos
{past} — Temp event ⏰10:00 🔄daily:{yesterday}

## ✅ Tareas

## 🏁 Hitos

## 💬 Recordatorios
""")
        with patch("core.config.iter_project_dirs", return_value=[project_dir]):
            result = startup_advance_past_recurring()

        assert len(result) == 1
        assert "serie finalizada" in result[0]


# ── Multiple items ────────────────────────────────────────────────────────

class TestMultipleItems:

    def test_multiple_projects_and_types(self, project_dir, tmp_path, monkeypatch):
        from core.agenda_cmds import startup_advance_past_recurring
        # Create second project
        type_dir = project_dir.parent
        proj2 = type_dir / "🌀other-project"
        proj2.mkdir()

        past = _past(3)
        _write_agenda(project_dir, f"""\
## 📅 Eventos
{past} — Meeting A ⏰12:00 🔄weekly 🔔5m

## ✅ Tareas

## 🏁 Hitos

## 💬 Recordatorios
""")
        (proj2 / "other-project-agenda.md").write_text(f"""\
## 📅 Eventos
{past} — Meeting B ⏰10:00 🔄weekly

## ✅ Tareas

## 🏁 Hitos

## 💬 Recordatorios
""")

        with patch("core.config.iter_project_dirs", return_value=[project_dir, proj2]):
            result = startup_advance_past_recurring()

        assert len(result) == 2
        descs = " ".join(result)
        assert "Meeting A" in descs
        assert "Meeting B" in descs

    def test_no_agenda_file(self, project_dir):
        """Project without agenda.md should be skipped."""
        from core.agenda_cmds import startup_advance_past_recurring
        # Don't create agenda file
        with patch("core.config.iter_project_dirs", return_value=[project_dir]):
            result = startup_advance_past_recurring()

        assert len(result) == 0

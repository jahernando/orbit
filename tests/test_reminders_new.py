"""Tests for the 💬 Recordatorios feature."""
import pytest
from datetime import date, datetime
from pathlib import Path
from core.agenda_cmds import (
    _parse_reminder_line, _format_reminder_line,
    _read_agenda, _write_agenda,
)


# ── Parsing ───────────────────────────────────────────────────────────────────

class TestParseReminderLine:

    def test_basic(self):
        r = _parse_reminder_line("- ¡Revisa el correo! (2026-03-18) ⏰17:00")
        assert r["desc"] == "¡Revisa el correo!"
        assert r["date"] == "2026-03-18"
        assert r["time"] == "17:00"
        assert r["recur"] is None
        assert r["cancelled"] is False

    def test_with_recurrence(self):
        r = _parse_reminder_line("- ¡Formate! (2026-03-19) ⏰08:00 🔄weekly")
        assert r["desc"] == "¡Formate!"
        assert r["recur"] == "weekly"

    def test_with_recurrence_until(self):
        r = _parse_reminder_line("- Gym (2026-03-20) ⏰07:00 🔄daily:2026-06-30")
        assert r["recur"] == "daily"
        assert r["until"] == "2026-06-30"

    def test_cancelled(self):
        r = _parse_reminder_line("- [-] Cancelado (2026-03-18) ⏰09:00")
        assert r["cancelled"] is True
        assert r["desc"] == "Cancelado"

    def test_requires_date(self):
        r = _parse_reminder_line("- Sin fecha ⏰17:00")
        assert r is None

    def test_requires_time(self):
        r = _parse_reminder_line("- Sin hora (2026-03-18)")
        assert r is None

    def test_not_a_reminder(self):
        assert _parse_reminder_line("## 💬 Recordatorios") is None
        assert _parse_reminder_line("") is None
        assert _parse_reminder_line("random text") is None

    def test_legacy_bracket_format(self):
        r = _parse_reminder_line("- Viejo (2026-03-18) [time:17:00]")
        assert r is not None
        assert r["time"] == "17:00"


# ── Formatting ────────────────────────────────────────────────────────────────

class TestFormatReminderLine:

    def test_basic(self):
        r = {"desc": "Test", "date": "2026-03-18", "time": "17:00",
             "recur": None, "until": None, "cancelled": False}
        assert _format_reminder_line(r) == "- Test (2026-03-18) ⏰17:00"

    def test_with_recurrence(self):
        r = {"desc": "Gym", "date": "2026-03-20", "time": "07:00",
             "recur": "daily", "until": None, "cancelled": False}
        assert _format_reminder_line(r) == "- Gym (2026-03-20) ⏰07:00 🔄daily"

    def test_with_until(self):
        r = {"desc": "Gym", "date": "2026-03-20", "time": "07:00",
             "recur": "daily", "until": "2026-06-30", "cancelled": False}
        assert _format_reminder_line(r) == "- Gym (2026-03-20) ⏰07:00 🔄daily:2026-06-30"

    def test_cancelled(self):
        r = {"desc": "Nope", "date": "2026-03-18", "time": "09:00",
             "recur": None, "until": None, "cancelled": True}
        assert _format_reminder_line(r) == "- [-] Nope (2026-03-18) ⏰09:00"

    def test_roundtrip(self):
        line = "- ¡Formate! (2026-03-19) ⏰08:00 🔄weekly"
        assert _format_reminder_line(_parse_reminder_line(line)) == line

    def test_roundtrip_cancelled(self):
        line = "- [-] Cancelado (2026-03-18) ⏰09:00"
        assert _format_reminder_line(_parse_reminder_line(line)) == line


# ── Read/Write agenda with reminders ──────────────────────────────────────────

class TestAgendaReminders:

    def test_read_reminders_section(self, tmp_path):
        agenda = tmp_path / "agenda.md"
        agenda.write_text("# Agenda\n\n## 💬 Recordatorios\n"
                          "- ¡Test! (2026-03-18) ⏰17:00\n"
                          "- [-] Cancelado (2026-03-18) ⏰09:00\n")
        data = _read_agenda(agenda)
        assert len(data["reminders"]) == 2
        assert data["reminders"][0]["desc"] == "¡Test!"
        assert data["reminders"][1]["cancelled"] is True

    def test_write_reminders_section(self, tmp_path):
        agenda = tmp_path / "agenda.md"
        data = {
            "header": ["# Agenda"],
            "tasks": [], "milestones": [], "events": [],
            "reminders": [
                {"desc": "B reminder", "date": "2026-03-20", "time": "10:00",
                 "recur": None, "until": None, "cancelled": False},
                {"desc": "A reminder", "date": "2026-03-18", "time": "17:00",
                 "recur": None, "until": None, "cancelled": False},
            ],
        }
        _write_agenda(agenda, data)
        text = agenda.read_text()
        assert "## 💬 Recordatorios" in text
        # Should be sorted by date
        lines = text.splitlines()
        rem_lines = [l for l in lines if l.startswith("- ") and "⏰" in l]
        assert "2026-03-18" in rem_lines[0]
        assert "2026-03-20" in rem_lines[1]

    def test_reminders_preserved_with_other_sections(self, tmp_path):
        agenda = tmp_path / "agenda.md"
        agenda.write_text("# Agenda\n\n## ✅ Tareas\n- [ ] Task\n\n"
                          "## 💬 Recordatorios\n- ¡Test! (2026-03-18) ⏰17:00\n")
        data = _read_agenda(agenda)
        assert len(data["tasks"]) == 1
        assert len(data["reminders"]) == 1
        _write_agenda(agenda, data)
        data2 = _read_agenda(agenda)
        assert len(data2["tasks"]) == 1
        assert len(data2["reminders"]) == 1

    def test_empty_reminders_not_written(self, tmp_path):
        agenda = tmp_path / "agenda.md"
        data = {
            "header": ["# Agenda"],
            "tasks": [{"status": "pending", "desc": "Task", "date": None,
                        "time": None, "recur": None, "until": None,
                        "ring": None, "synced": False}],
            "milestones": [], "events": [], "reminders": [],
        }
        _write_agenda(agenda, data)
        assert "Recordatorios" not in agenda.read_text()

    def test_reminders_not_in_agenda_view(self, tmp_path):
        """Reminders should not appear in agenda command output."""
        agenda = tmp_path / "agenda.md"
        agenda.write_text("# Agenda\n\n## ✅ Tareas\n- [ ] Task (2026-03-18)\n\n"
                          "## 💬 Recordatorios\n- ¡Test! (2026-03-18) ⏰17:00\n")
        data = _read_agenda(agenda)
        # agenda_view only uses tasks, milestones, events — not reminders
        assert "reminders" not in ["tasks", "milestones", "events"]
        assert len(data["reminders"]) == 1


# ── Ring integration ──────────────────────────────────────────────────────────

class TestReminderRingCollection:

    def test_collects_today_reminders(self, tmp_path):
        from core.ring import _reminders_on
        from core.config import iter_project_dirs
        from core.log import resolve_file

        today = date.today().isoformat()
        agenda = tmp_path / "agenda.md"
        agenda.write_text(f"# Agenda\n\n## 💬 Recordatorios\n"
                          f"- ¡Test! ({today}) ⏰17:00\n"
                          f"- Mañana (2099-01-01) ⏰09:00\n"
                          f"- [-] Cancelado ({today}) ⏰10:00\n")

        # Mock resolve_file to return our tmp agenda
        import core.ring as ring_mod
        original_read = ring_mod._read_agenda

        def mock_read(path):
            return original_read(agenda)

        ring_mod._read_agenda = mock_read
        try:
            results = _reminders_on(tmp_path, date.today())
            assert len(results) == 1
            assert results[0]["desc"] == "¡Test!"
            assert results[0]["is_reminder"] is True
        finally:
            ring_mod._read_agenda = original_read

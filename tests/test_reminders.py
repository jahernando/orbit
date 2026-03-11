"""tests/test_reminders.py — unit tests for core/reminders.py."""

import pytest
from datetime import date
from pathlib import Path

from core.reminders import (
    _next_date,
    _parse_reminders,
    _mark_scheduled,
    _advance_recurring,
    _process_reminder,
    schedule_today_reminders,
)

TARGET = date(2026, 3, 8)


# ── helpers ───────────────────────────────────────────────────────────────────

def _write_proyecto(path: Path, tasks_body: str) -> None:
    path.write_text(
        f"# Proyecto\n\n## ✅ Tareas\n{tasks_body}\n## 📎 Referencias\n-\n"
    )


def _write_legacy(path: Path, body: str) -> None:
    path.write_text(
        f"# Proyecto\n\n## ✅ Tareas\n\n## ⏰ Recordatorios\n{body}\n## 📎 Referencias\n-\n"
    )


# ── _next_date ────────────────────────────────────────────────────────────────

class TestNextDate:

    def test_daily(self):
        d = date(2026, 3, 8)
        assert _next_date(d, "@daily") == date(2026, 3, 9)

    def test_diario_alias(self):
        d = date(2026, 3, 8)
        assert _next_date(d, "@diario") == date(2026, 3, 9)

    def test_weekly(self):
        d = date(2026, 3, 8)  # domingo
        assert _next_date(d, "@weekly") == date(2026, 3, 15)

    def test_monthly(self):
        d = date(2026, 1, 31)
        # febrero no tiene 31 → debe usar el último día
        assert _next_date(d, "@monthly") == date(2026, 2, 28)

    def test_monthly_december(self):
        d = date(2026, 12, 15)
        assert _next_date(d, "@monthly") == date(2027, 1, 15)

    def test_weekdays_from_friday(self):
        friday = date(2026, 3, 6)
        assert _next_date(friday, "@weekdays") == date(2026, 3, 9)  # lunes

    def test_weekdays_from_monday(self):
        monday = date(2026, 3, 9)
        assert _next_date(monday, "@weekdays") == date(2026, 3, 10)

    def test_every_nd(self):
        d = date(2026, 3, 8)
        assert _next_date(d, "@every:3d") == date(2026, 3, 11)

    def test_every_nw(self):
        d = date(2026, 3, 8)
        assert _next_date(d, "@every:2w") == date(2026, 3, 22)

    def test_unknown_tag_returns_same_date(self):
        d = date(2026, 3, 8)
        assert _next_date(d, "@desconocido") == d


# ── _parse_reminders ──────────────────────────────────────────────────────────

class TestParseReminders:

    def test_new_format_with_time(self, orbit_env):
        p = orbit_env["proyecto_path"]
        _write_proyecto(p, "- [ ] Reunión de grupo (2026-03-08 09:30) @ring\n")
        results = _parse_reminders(p.read_text().splitlines(), p, TARGET)
        assert len(results) == 1
        r = results[0]
        assert r["title"] == "Reunión de grupo"
        assert r["hour"] == 9
        assert r["minute"] == 30
        assert r["recur"] is None
        assert r["date"] == TARGET

    def test_new_format_with_recur(self, orbit_env):
        p = orbit_env["proyecto_path"]
        _write_proyecto(p, "- [ ] Standup (2026-03-08 08:30) @ring @weekly\n")
        results = _parse_reminders(p.read_text().splitlines(), p, TARGET)
        assert len(results) == 1
        assert results[0]["recur"] == "@weekly"

    def test_new_format_no_time_defaults_to_0900(self, orbit_env, capsys):
        p = orbit_env["proyecto_path"]
        _write_proyecto(p, "- [ ] Sin hora (2026-03-08) @ring\n")
        results = _parse_reminders(p.read_text().splitlines(), p, TARGET)
        assert len(results) == 1
        assert results[0]["hour"] == 9
        assert results[0]["minute"] == 0
        out = capsys.readouterr().out
        assert "09:00" in out

    def test_new_format_wrong_date_excluded(self, orbit_env):
        p = orbit_env["proyecto_path"]
        _write_proyecto(p, "- [ ] Otra reunión (2026-03-09 10:00) @ring\n")
        assert _parse_reminders(p.read_text().splitlines(), p, TARGET) == []

    def test_new_format_no_ring_excluded(self, orbit_env):
        p = orbit_env["proyecto_path"]
        _write_proyecto(p, "- [ ] Tarea normal (2026-03-08)\n")
        assert _parse_reminders(p.read_text().splitlines(), p, TARGET) == []

    def test_new_format_already_scheduled_excluded(self, orbit_env):
        """[~] tasks must be skipped — already in Reminders.app, avoid duplicate alarms."""
        p = orbit_env["proyecto_path"]
        _write_proyecto(p, "- [~] Reunión (2026-03-08 10:00) @ring\n")
        assert _parse_reminders(p.read_text().splitlines(), p, TARGET) == []

    def test_new_format_done_excluded(self, orbit_env):
        p = orbit_env["proyecto_path"]
        _write_proyecto(p, "- [x] Completada (2026-03-08) @ring\n")
        assert _parse_reminders(p.read_text().splitlines(), p, TARGET) == []

    def test_legacy_section_ignored(self, orbit_env):
        """## ⏰ Recordatorios (legacy) is no longer parsed — section eliminated."""
        p = orbit_env["proyecto_path"]
        _write_legacy(p, "- [ ] 2026-03-08 10:00 Standup @weekly\n")
        assert _parse_reminders(p.read_text().splitlines(), p, TARGET) == []

    def test_multiple_tasks_same_day(self, orbit_env):
        p = orbit_env["proyecto_path"]
        _write_proyecto(p,
            "- [ ] Reunión (2026-03-08 09:00) @ring\n"
            "- [ ] Standup (2026-03-08 10:00) @ring\n"
        )
        results = _parse_reminders(p.read_text().splitlines(), p, TARGET)
        assert len(results) == 2

    def test_project_name_set(self, orbit_env):
        p = orbit_env["proyecto_path"]
        _write_proyecto(p, "- [ ] Reunión (2026-03-08 09:00) @ring\n")
        results = _parse_reminders(p.read_text().splitlines(), p, TARGET)
        assert results[0]["project"] == orbit_env["proj_dir"].name


# ── _mark_scheduled ───────────────────────────────────────────────────────────

class TestMarkScheduled:

    def test_replaces_marker(self, orbit_env):
        p = orbit_env["proyecto_path"]
        _write_proyecto(p, "- [ ] Reunión (2026-03-08 09:00) @ring\n")
        lines = p.read_text().splitlines()
        idx = next(i for i, l in enumerate(lines) if "- [ ]" in l and "Reunión" in l)
        _mark_scheduled(p, idx)
        result = p.read_text().splitlines()[idx]
        assert result.startswith("- [~]")
        assert "- [ ]" not in result

    def test_only_replaces_target_line(self, orbit_env):
        p = orbit_env["proyecto_path"]
        _write_proyecto(p,
            "- [ ] Primera (2026-03-08 09:00) @ring\n"
            "- [ ] Segunda (2026-03-08 10:00) @ring\n"
        )
        lines = p.read_text().splitlines()
        idx = next(i for i, l in enumerate(lines) if "Primera" in l)
        _mark_scheduled(p, idx)
        content = p.read_text()
        assert "- [~] Primera" in content
        assert "- [ ] Segunda" in content


# ── _advance_recurring ────────────────────────────────────────────────────────

class TestAdvanceRecurring:

    def test_weekly_advances_date(self, orbit_env):
        p = orbit_env["proyecto_path"]
        _write_proyecto(p, "- [~] Reunión (2026-03-08 09:00) @ring @weekly\n")
        lines = p.read_text().splitlines()
        idx = next(i for i, l in enumerate(lines) if "Reunión" in l)
        next_d = _advance_recurring(p, idx, "@weekly", date(2026, 3, 8))
        assert next_d == date(2026, 3, 15)
        new_line = p.read_text().splitlines()[idx]
        assert "2026-03-15" in new_line

    def test_advance_resets_scheduled_marker(self, orbit_env):
        """[~] must become [ ] after advancing."""
        p = orbit_env["proyecto_path"]
        _write_proyecto(p, "- [~] Standup (2026-03-08 08:30) @ring @daily\n")
        lines = p.read_text().splitlines()
        idx = next(i for i, l in enumerate(lines) if "Standup" in l)
        _advance_recurring(p, idx, "@daily", date(2026, 3, 8))
        new_line = p.read_text().splitlines()[idx]
        assert new_line.strip().startswith("- [ ]")
        assert "- [~]" not in new_line

    def test_monthly_end_of_month(self, orbit_env):
        p = orbit_env["proyecto_path"]
        _write_proyecto(p, "- [ ] Revisión (2026-01-31 10:00) @ring @monthly\n")
        lines = p.read_text().splitlines()
        idx = next(i for i, l in enumerate(lines) if "Revisión" in l)
        next_d = _advance_recurring(p, idx, "@monthly", date(2026, 1, 31))
        assert next_d == date(2026, 2, 28)

    def test_every_nd(self, orbit_env):
        p = orbit_env["proyecto_path"]
        _write_proyecto(p, "- [ ] Backup (2026-03-08 09:00) @ring @every:3d\n")
        lines = p.read_text().splitlines()
        idx = next(i for i, l in enumerate(lines) if "Backup" in l)
        next_d = _advance_recurring(p, idx, "@every:3d", date(2026, 3, 8))
        assert next_d == date(2026, 3, 11)
        assert "2026-03-11" in p.read_text()

    def test_advance_without_tilde_warns(self, orbit_env, capsys):
        """If line has [ ] instead of [~], advance still works but emits warning."""
        p = orbit_env["proyecto_path"]
        _write_proyecto(p, "- [ ] Tarea (2026-03-08 09:00) @ring @weekly\n")
        lines = p.read_text().splitlines()
        idx = next(i for i, l in enumerate(lines) if "Tarea" in l)
        next_d = _advance_recurring(p, idx, "@weekly", date(2026, 3, 8))
        assert next_d == date(2026, 3, 15)
        out = capsys.readouterr().out
        assert "⚠️" in out


# ── _process_reminder ─────────────────────────────────────────────────────────

class TestProcessReminder:

    def _reminder(self, proyecto_path, line_index=3, recur=None):
        return {
            "line_index": line_index, "hour": 9, "minute": 0,
            "title": "Reunión", "recur": recur,
            "project": "testproj", "proyecto_path": proyecto_path,
        }

    def test_non_recurring_marks_scheduled(self, orbit_env):
        p = orbit_env["proyecto_path"]
        _write_proyecto(p, "- [ ] Reunión (2026-03-08 09:00) @ring\n")
        lines = p.read_text().splitlines()
        idx = next(i for i, l in enumerate(lines) if "Reunión" in l)
        r = self._reminder(p, line_index=idx)
        _process_reminder(r, p, TARGET)
        assert "- [~]" in p.read_text()

    def test_recurring_advances_date(self, orbit_env):
        p = orbit_env["proyecto_path"]
        _write_proyecto(p, "- [~] Standup (2026-03-08 08:30) @ring @weekly\n")
        lines = p.read_text().splitlines()
        idx = next(i for i, l in enumerate(lines) if "Standup" in l)
        r = self._reminder(p, line_index=idx, recur="@weekly")
        _process_reminder(r, p, TARGET)
        content = p.read_text()
        assert "2026-03-15" in content
        assert "- [ ]" in content


# ── schedule_today_reminders ──────────────────────────────────────────────────

class TestScheduleTodayReminders:

    def _setup_ring(self, orbit_env, target: date, time_str="09:00", recur=None):
        p = orbit_env["proyecto_path"]
        recur_tag = f" {recur}" if recur else ""
        _write_proyecto(p, f"- [ ] Reunión ({target.isoformat()} {time_str}) @ring{recur_tag}\n")

    def test_schedules_and_marks(self, orbit_env, monkeypatch):
        self._setup_ring(orbit_env, TARGET)
        monkeypatch.setattr("core.reminders.PROJECTS_DIR", orbit_env["projects_dir"])
        monkeypatch.setattr("core.reminders._schedule_via_applescript", lambda **kw: True)

        result = schedule_today_reminders(TARGET)

        assert len(result) == 1
        assert result[0]["title"] == "Reunión"
        content = orbit_env["proyecto_path"].read_text()
        assert "- [~]" in content

    def test_failed_applescript_not_added(self, orbit_env, monkeypatch):
        self._setup_ring(orbit_env, TARGET)
        monkeypatch.setattr("core.reminders.PROJECTS_DIR", orbit_env["projects_dir"])
        monkeypatch.setattr("core.reminders._schedule_via_applescript", lambda **kw: False)

        result = schedule_today_reminders(TARGET)

        assert result == []
        # marker must NOT have been set
        assert "- [ ]" in orbit_env["proyecto_path"].read_text()

    def test_recurring_advances_date(self, orbit_env, monkeypatch):
        self._setup_ring(orbit_env, TARGET, recur="@weekly")
        monkeypatch.setattr("core.reminders.PROJECTS_DIR", orbit_env["projects_dir"])
        monkeypatch.setattr("core.reminders._schedule_via_applescript", lambda **kw: True)

        schedule_today_reminders(TARGET)

        content = orbit_env["proyecto_path"].read_text()
        assert "2026-03-15" in content   # avanzado 7 días
        assert "- [ ]" in content        # resetado a pendiente

    def test_no_ring_for_target_returns_empty(self, orbit_env, monkeypatch):
        p = orbit_env["proyecto_path"]
        _write_proyecto(p, "- [ ] Tarea sin ring (2026-03-08)\n")
        monkeypatch.setattr("core.reminders.PROJECTS_DIR", orbit_env["projects_dir"])
        monkeypatch.setattr("core.reminders._schedule_via_applescript", lambda **kw: True)

        assert schedule_today_reminders(TARGET) == []

"""tests/test_reminders.py — unit tests for core/reminders.py."""

import pytest
from datetime import date
from pathlib import Path

from core.reminders import (
    _next_date,
    _parse_reminders,
    _mark_scheduled,
    _advance_recurring,
    inject_reminders_into_note,
    schedule_today_reminders,
    INJECT_START,
    INJECT_END,
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
        results = _parse_reminders(p, TARGET)
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
        results = _parse_reminders(p, TARGET)
        assert len(results) == 1
        assert results[0]["recur"] == "@weekly"

    def test_new_format_no_time_defaults_to_0900(self, orbit_env, capsys):
        p = orbit_env["proyecto_path"]
        _write_proyecto(p, "- [ ] Sin hora (2026-03-08) @ring\n")
        results = _parse_reminders(p, TARGET)
        assert len(results) == 1
        assert results[0]["hour"] == 9
        assert results[0]["minute"] == 0
        out = capsys.readouterr().out
        assert "09:00" in out

    def test_new_format_wrong_date_excluded(self, orbit_env):
        p = orbit_env["proyecto_path"]
        _write_proyecto(p, "- [ ] Otra reunión (2026-03-09 10:00) @ring\n")
        assert _parse_reminders(p, TARGET) == []

    def test_new_format_no_ring_excluded(self, orbit_env):
        p = orbit_env["proyecto_path"]
        _write_proyecto(p, "- [ ] Tarea normal (2026-03-08)\n")
        assert _parse_reminders(p, TARGET) == []

    def test_new_format_already_scheduled_included(self, orbit_env):
        """[~] tasks (already scheduled) must still be returned."""
        p = orbit_env["proyecto_path"]
        _write_proyecto(p, "- [~] Reunión (2026-03-08 10:00) @ring\n")
        results = _parse_reminders(p, TARGET)
        assert len(results) == 1
        assert results[0]["title"] == "Reunión"

    def test_new_format_done_excluded(self, orbit_env):
        p = orbit_env["proyecto_path"]
        _write_proyecto(p, "- [x] Completada (2026-03-08) @ring\n")
        assert _parse_reminders(p, TARGET) == []

    def test_legacy_format(self, orbit_env):
        p = orbit_env["proyecto_path"]
        _write_legacy(p, "- [ ] 2026-03-08 10:00 Standup @weekly\n")
        results = _parse_reminders(p, TARGET)
        assert len(results) == 1
        r = results[0]
        assert r["title"] == "Standup"
        assert r["hour"] == 10
        assert r["minute"] == 0
        assert r["recur"] == "@weekly"

    def test_legacy_format_wrong_date_excluded(self, orbit_env):
        p = orbit_env["proyecto_path"]
        _write_legacy(p, "- [ ] 2026-03-09 10:00 Standup\n")
        assert _parse_reminders(p, TARGET) == []

    def test_multiple_tasks_same_day(self, orbit_env):
        p = orbit_env["proyecto_path"]
        _write_proyecto(p,
            "- [ ] Reunión (2026-03-08 09:00) @ring\n"
            "- [ ] Standup (2026-03-08 10:00) @ring\n"
        )
        results = _parse_reminders(p, TARGET)
        assert len(results) == 2

    def test_project_name_set(self, orbit_env):
        p = orbit_env["proyecto_path"]
        _write_proyecto(p, "- [ ] Reunión (2026-03-08 09:00) @ring\n")
        results = _parse_reminders(p, TARGET)
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


# ── inject_reminders_into_note ────────────────────────────────────────────────

class TestInjectReminders:

    def _make_reminders(self, proyecto_path: Path) -> list:
        return [
            {"hour": 10, "minute": 0,  "title": "Reunión",  "project": "testproj", "proyecto_path": proyecto_path},
            {"hour":  9, "minute": 30, "title": "Standup",  "project": "testproj", "proyecto_path": proyecto_path},
        ]

    def test_injects_between_markers(self, orbit_env):
        note = orbit_env["diario_path"]
        reminders = self._make_reminders(orbit_env["proyecto_path"])
        inject_reminders_into_note(note, reminders)
        content = note.read_text()
        assert "Reunión" in content
        assert "Standup" in content
        assert INJECT_START in content
        assert INJECT_END in content

    def test_sorted_by_time(self, orbit_env):
        note = orbit_env["diario_path"]
        reminders = self._make_reminders(orbit_env["proyecto_path"])
        inject_reminders_into_note(note, reminders)
        content = note.read_text()
        pos_standup = content.index("Standup")
        pos_reunion = content.index("Reunión")
        assert pos_standup < pos_reunion   # 09:30 antes que 10:00

    def test_no_markers_leaves_file_unchanged(self, orbit_env):
        note = orbit_env["diario_path"]
        original = note.read_text().replace(INJECT_START, "").replace(INJECT_END, "")
        note.write_text(original)
        reminders = self._make_reminders(orbit_env["proyecto_path"])
        inject_reminders_into_note(note, reminders)
        assert note.read_text() == original

    def test_empty_reminders_leaves_file_unchanged(self, orbit_env):
        note = orbit_env["diario_path"]
        original = note.read_text()
        inject_reminders_into_note(note, [])
        assert note.read_text() == original

    def test_link_contains_proyecto_path(self, orbit_env):
        note = orbit_env["diario_path"]
        reminders = self._make_reminders(orbit_env["proyecto_path"])
        inject_reminders_into_note(note, reminders)
        content = note.read_text()
        assert "file://" in content
        assert "#tareas" in content


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

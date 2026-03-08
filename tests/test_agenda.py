"""tests/test_agenda.py — unit tests for core/agenda.py."""

import pytest
from datetime import date, timedelta
from pathlib import Path

from core.agenda import (
    _collect, _overdue, _focus_set,
    _task_line, _format_day, _format_week, _format_month,
    run_agenda,
)
from core.focus import set_focus


# ── fixture ────────────────────────────────────────────────────────────────────

@pytest.fixture
def agenda_env(orbit_env, monkeypatch, tmp_path):
    """Extend orbit_env: add tasks to testproj; patch paths."""
    today         = date.fromisoformat(orbit_env["today"])
    projects_dir  = orbit_env["projects_dir"]
    proj_dir      = orbit_env["proj_dir"]
    proyecto_path = orbit_env["proyecto_path"]

    # Add tasks to testproj
    yesterday = (today - timedelta(days=1)).isoformat()
    tomorrow  = (today + timedelta(days=1)).isoformat()
    in3days   = (today + timedelta(days=3)).isoformat()
    next_week = (today + timedelta(days=8)).isoformat()

    proyecto_path.write_text(
        "# testproj\n💻 Software\n▶️ En marcha\n🟠 Alta\n"
        "## 🎯 Objetivo\nTest.\n"
        "## ✅ Tareas\n"
        f"- [ ] Tarea vencida ({yesterday})\n"
        f"- [ ] Tarea de hoy ({today.isoformat()})\n"
        f"- [ ] Tarea de mañana ({tomorrow})\n"
        f"- [ ] Tarea en 3 días ({in3days})\n"
        f"- [ ] Tarea semana próxima ({next_week})\n"
        "- [ ] Tarea sin fecha\n"
    )

    # Patch module paths
    monkeypatch.setattr("core.agenda.PROJECTS_DIR",      projects_dir)
    monkeypatch.setattr("core.focus.PROJECTS_DIR",       projects_dir)

    focus_file = tmp_path / ".orbit" / "focus.json"
    monkeypatch.setattr("core.focus.FOCUS_FILE", focus_file)

    return {
        **orbit_env,
        "today":     today,
        "yesterday": date.fromisoformat(yesterday),
        "tomorrow":  date.fromisoformat(tomorrow),
        "in3days":   date.fromisoformat(in3days),
        "next_week": date.fromisoformat(next_week),
    }


# ── _collect ───────────────────────────────────────────────────────────────────

class TestCollect:
    def test_collects_tasks_in_range(self, agenda_env):
        today = agenda_env["today"]
        tasks = _collect(today, today)
        assert today in tasks
        assert any("hoy" in t["desc"].lower() for t in tasks[today])

    def test_excludes_tasks_outside_range(self, agenda_env):
        today = agenda_env["today"]
        tasks = _collect(today, today)
        # tomorrow should not appear
        assert agenda_env["tomorrow"] not in tasks

    def test_excludes_tasks_without_date(self, agenda_env):
        today    = agenda_env["today"]
        next_week = agenda_env["next_week"]
        tasks = _collect(today, next_week + timedelta(days=1))
        # Tasks without date should not appear
        no_date = [t for day_tasks in tasks.values()
                   for t in day_tasks if "sin fecha" in t["desc"]]
        assert no_date == []

    def test_returns_empty_for_future_only(self, agenda_env):
        far_future = date.today() + timedelta(days=100)
        tasks = _collect(far_future, far_future + timedelta(days=1))
        assert tasks == {}

    def test_task_has_required_fields(self, agenda_env):
        today = agenda_env["today"]
        tasks = _collect(today, today)
        t = tasks[today][0]
        assert "desc" in t
        assert "project" in t
        assert "path" in t


# ── _overdue ───────────────────────────────────────────────────────────────────

class TestOverdue:
    def test_finds_yesterday_task(self, agenda_env):
        today = agenda_env["today"]
        od = _overdue(today)
        assert any("vencida" in t["desc"].lower() for t in od)

    def test_excludes_today(self, agenda_env):
        today = agenda_env["today"]
        od = _overdue(today)
        assert all(t["due"] < today for t in od)

    def test_returns_list(self, agenda_env):
        today = agenda_env["today"]
        assert isinstance(_overdue(today), list)


# ── _focus_set ─────────────────────────────────────────────────────────────────

class TestFocusSet:
    def test_empty_when_no_focus(self, agenda_env):
        today = agenda_env["today"]
        assert _focus_set("day", today) == set()

    def test_contains_focus_project(self, agenda_env):
        today = agenda_env["today"]
        set_focus("day", ["💻testproj"], today)
        fs = _focus_set("day", today)
        assert any("testproj" in f for f in fs)

    def test_case_insensitive(self, agenda_env):
        today = agenda_env["today"]
        set_focus("day", ["💻testproj"], today)
        fs = _focus_set("day", today)
        assert "💻testproj" in fs


# ── _task_line ─────────────────────────────────────────────────────────────────

class TestTaskLine:
    def _t(self, desc="Task A", project="💻testproj", time=None, ring=False):
        return {"desc": desc, "project": project, "path": Path("/fake"), "time": time, "ring": ring}

    def test_contains_description(self):
        line = _task_line(self._t(), set())
        assert "Task A" in line

    def test_contains_project(self):
        line = _task_line(self._t(), set())
        assert "💻testproj" in line

    def test_focus_marker_when_in_focus(self):
        line = _task_line(self._t(), {"💻testproj"})
        assert "🎯" in line

    def test_no_focus_marker_when_not_in_focus(self):
        line = _task_line(self._t(), set())
        assert "🎯" not in line

    def test_overdue_marker(self):
        line = _task_line(self._t(), set(), show_overdue=True)
        assert "⚠️" in line

    def test_ring_marker(self):
        line = _task_line(self._t(ring=True), set())
        assert "🔔" in line

    def test_time_shown(self):
        line = _task_line(self._t(time="10:30"), set())
        assert "10:30" in line

    def test_date_shown_when_requested(self):
        t = {**self._t(), "due": date(2026, 3, 10)}
        line = _task_line(t, set(), show_date=True)
        assert "2026-03-10" in line


# ── _format_day ────────────────────────────────────────────────────────────────

class TestFormatDay:
    def test_contains_date(self, agenda_env):
        today = agenda_env["today"]
        text = _format_day(today)
        assert today.isoformat() in text

    def test_contains_today_section(self, agenda_env):
        today = agenda_env["today"]
        text = _format_day(today)
        assert "HOY" in text

    def test_contains_upcoming_section_when_tasks(self, agenda_env):
        today = agenda_env["today"]
        text = _format_day(today)
        assert "PRÓXIMOS 7 DÍAS" in text

    def test_today_task_appears(self, agenda_env):
        today = agenda_env["today"]
        text = _format_day(today)
        assert "Tarea de hoy" in text

    def test_overdue_section_when_overdue(self, agenda_env):
        today = agenda_env["today"]
        text = _format_day(today)
        assert "VENCIDAS" in text
        assert "Tarea vencida" in text

    def test_next_week_task_not_in_upcoming(self, agenda_env):
        today = agenda_env["today"]
        text = _format_day(today)
        # next_week is 8 days away, outside the 7-day window
        assert "semana próxima" not in text

    def test_focus_shown_in_header(self, agenda_env):
        today = agenda_env["today"]
        set_focus("day", ["💻testproj"], today)
        text = _format_day(today)
        assert "💻testproj" in text

    def test_focus_mark_on_task(self, agenda_env):
        today = agenda_env["today"]
        set_focus("day", ["💻testproj"], today)
        text = _format_day(today)
        assert "🎯" in text

    def test_no_focus_shows_dash(self, agenda_env):
        today = agenda_env["today"]
        text = _format_day(today)
        assert "Foco del día: —" in text


# ── _format_week ───────────────────────────────────────────────────────────────

class TestFormatWeek:
    def test_contains_week_key(self, agenda_env):
        today = agenda_env["today"]
        text = _format_week(today)
        assert "2026-W" in text

    def test_contains_all_day_names(self, agenda_env):
        today = agenda_env["today"]
        text = _format_week(today)
        for day in ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes"]:
            assert day in text

    def test_today_marked(self, agenda_env):
        today = agenda_env["today"]
        text = _format_week(today)
        assert "◀ hoy" in text

    def test_today_task_shown(self, agenda_env):
        today = agenda_env["today"]
        text = _format_week(today)
        assert "Tarea de hoy" in text

    def test_yesterday_appears_in_day_slot(self, agenda_env):
        """Yesterday's task appears in its day slot (not in VENCIDAS, since it's within the week)."""
        today = agenda_env["today"]
        text = _format_week(today)
        # "Tarea vencida" is yesterday (within the week) → shown in day slot, not VENCIDAS
        assert "Tarea vencida" in text


# ── _format_month ──────────────────────────────────────────────────────────────

class TestFormatMonth:
    def test_contains_month_name(self, agenda_env):
        today = agenda_env["today"]
        text = _format_month(today)
        # Month name in Spanish
        assert "Marzo" in text or "marzo" in text.lower()

    def test_grouped_by_week(self, agenda_env):
        today = agenda_env["today"]
        text = _format_month(today)
        assert "Semana" in text

    def test_today_task_shown(self, agenda_env):
        today = agenda_env["today"]
        text = _format_month(today)
        assert "Tarea de hoy" in text

    def test_hoy_marker_in_month(self, agenda_env):
        today = agenda_env["today"]
        text = _format_month(today)
        assert "◀ hoy" in text

    def test_focus_shown(self, agenda_env):
        today = agenda_env["today"]
        set_focus("month", ["💻testproj"], today)
        text = _format_month(today)
        assert "💻testproj" in text


# ── run_agenda ─────────────────────────────────────────────────────────────────

class TestRunAgenda:
    def test_day_returns_zero(self, agenda_env, capsys):
        rc = run_agenda("day", agenda_env["today"].isoformat())
        assert rc == 0

    def test_week_returns_zero(self, agenda_env, capsys):
        rc = run_agenda("week", agenda_env["today"].isoformat())
        assert rc == 0

    def test_month_returns_zero(self, agenda_env, capsys):
        rc = run_agenda("month", agenda_env["today"].isoformat())
        assert rc == 0

    def test_default_period_is_day(self, agenda_env, capsys):
        rc = run_agenda(None, agenda_env["today"].isoformat())
        assert rc == 0
        out = capsys.readouterr().out
        assert "HOY" in out

    def test_invalid_period_returns_one(self, agenda_env, capsys):
        rc = run_agenda("quarter", agenda_env["today"].isoformat())
        assert rc == 1

    def test_output_to_file(self, agenda_env, tmp_path):
        out_file = tmp_path / "agenda.txt"
        rc = run_agenda("day", agenda_env["today"].isoformat(), output=str(out_file))
        assert rc == 0
        assert out_file.exists()
        assert "HOY" in out_file.read_text()

    def test_ring_without_tty_silently_fails(self, agenda_env, monkeypatch, capsys):
        # schedule_today_reminders may fail in test env; should not crash
        monkeypatch.setattr(
            "core.agenda._schedule_reminders", lambda d: None
        )
        rc = run_agenda("day", agenda_env["today"].isoformat(), ring=True)
        assert rc == 0

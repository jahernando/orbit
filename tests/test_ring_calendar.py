"""Tests for views/ring/parse.py and Phase-7 extensions to core/calendar_sync.py."""

import importlib
from datetime import date, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ── helpers ────────────────────────────────────────────────────────────────────

def _make_project(type_dir: Path, name: str = "alpha") -> Path:
    """Create a minimal new-format project directory inside a type dir."""
    d = type_dir / name
    d.mkdir(parents=True, exist_ok=True)
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

from views.ring.parse import _parse_ring, resolve_ring_datetime


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

from views.ring.parse import _tasks_ringing_on


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

from views.ring.parse import _clear_ring


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

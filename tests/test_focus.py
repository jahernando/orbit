"""tests/test_focus.py — unit tests for core/focus.py."""

import json
import pytest
from datetime import date
from pathlib import Path

from core.focus import (
    FOCUS_FILE, PERIODS, PERIOD_LABELS,
    _week_key, _period_key,
    _load, _save,
    get_focus, get_current_focus,
    set_focus, clear_focus,
    run_focus,
)


# ── fixtures ───────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def isolated_focus(tmp_path, monkeypatch):
    """Redirect FOCUS_FILE to a temp location so tests never touch real data."""
    focus_file = tmp_path / ".orbit" / "focus.json"
    monkeypatch.setattr("core.focus.FOCUS_FILE", focus_file)
    yield focus_file


@pytest.fixture
def today():
    return date.today()


@pytest.fixture
def focus_with_data(today):
    """Pre-populate focus with known projects for all periods."""
    for period, projects in [
        ("month", ["💻orbit"]),
        ("week",  ["💻orbit", "☀️mission"]),
        ("day",   ["💻orbit"]),
    ]:
        set_focus(period, projects, today)


# ── helpers ────────────────────────────────────────────────────────────────────

class TestWeekKey:
    def test_format(self):
        d = date(2026, 3, 9)       # Monday of W11
        assert _week_key(d).startswith("2026-W")

    def test_iso_week(self):
        # 2026-01-01 is Thursday, ISO week 1 of 2026
        key = _week_key(date(2026, 1, 1))
        assert "W" in key

    def test_different_weeks(self):
        w10 = _week_key(date(2026, 3, 2))    # Monday
        w11 = _week_key(date(2026, 3, 9))    # next Monday
        assert w10 != w11


class TestPeriodKey:
    def test_day(self):
        d = date(2026, 3, 8)
        assert _period_key("day", d) == "2026-03-08"

    def test_week(self):
        d = date(2026, 3, 8)
        key = _period_key("week", d)
        assert key.startswith("2026-W")

    def test_month(self):
        d = date(2026, 3, 8)
        assert _period_key("month", d) == "2026-03"

    def test_invalid_period(self):
        with pytest.raises(ValueError):
            _period_key("year", date.today())


# ── load / save ────────────────────────────────────────────────────────────────

class TestLoadSave:
    def test_load_missing_returns_empty(self, isolated_focus):
        data = _load()
        assert data == {"day": {}, "week": {}, "month": {}}

    def test_save_creates_parent(self, isolated_focus):
        _save({"day": {}, "week": {}, "month": {}})
        assert isolated_focus.exists()

    def test_roundtrip(self, isolated_focus):
        payload = {"day": {"2026-03-08": ["💻orbit"]}, "week": {}, "month": {}}
        _save(payload)
        assert _load() == payload

    def test_save_is_valid_json(self, isolated_focus):
        _save({"day": {}, "week": {}, "month": {}})
        loaded = json.loads(isolated_focus.read_text())
        assert isinstance(loaded, dict)


# ── get / set / clear ──────────────────────────────────────────────────────────

class TestGetSetClear:
    def test_get_empty(self, today):
        assert get_focus("month", today) == []

    def test_set_and_get(self, today):
        set_focus("month", ["💻orbit", "☀️mission"], today)
        assert get_focus("month", today) == ["💻orbit", "☀️mission"]

    def test_set_overwrites(self, today):
        set_focus("month", ["💻orbit"], today)
        set_focus("month", ["☀️mission"], today)
        assert get_focus("month", today) == ["☀️mission"]

    def test_clear(self, today):
        set_focus("week", ["💻orbit"], today)
        clear_focus("week", today)
        assert get_focus("week", today) == []

    def test_periods_are_independent(self, today):
        set_focus("month", ["💻orbit"], today)
        set_focus("week",  ["☀️mission"], today)
        assert get_focus("month", today) == ["💻orbit"]
        assert get_focus("week",  today) == ["☀️mission"]

    def test_different_dates_are_independent(self):
        d1 = date(2026, 3, 1)
        d2 = date(2026, 4, 1)
        set_focus("month", ["💻orbit"],   d1)
        set_focus("month", ["☀️mission"], d2)
        assert get_focus("month", d1) == ["💻orbit"]
        assert get_focus("month", d2) == ["☀️mission"]


class TestGetCurrentFocus:
    def test_all_periods_present(self, today):
        current = get_current_focus()
        assert set(current.keys()) == set(PERIODS)

    def test_empty_by_default(self, today):
        current = get_current_focus()
        for p in PERIODS:
            assert current[p] == []

    def test_reflects_set_values(self, today, focus_with_data):
        current = get_current_focus()
        assert "💻orbit" in current["month"]
        assert "💻orbit" in current["week"]
        assert "☀️mission" in current["week"]
        assert "💻orbit" in current["day"]


# ── run_focus ──────────────────────────────────────────────────────────────────

class TestRunFocus:
    def test_show_all_returns_zero(self, today, capsys):
        rc = run_focus()
        assert rc == 0

    def test_show_all_contains_periods(self, today, capsys):
        run_focus()
        out = capsys.readouterr().out
        assert "Mes" in out
        assert "Semana" in out
        assert "Día" in out

    def test_show_period_returns_zero(self, today, capsys):
        rc = run_focus(period="month")
        assert rc == 0

    def test_show_period_output(self, today, capsys, focus_with_data):
        run_focus(period="month")
        out = capsys.readouterr().out
        assert "💻orbit" in out

    def test_set_writes_to_json(self, today, isolated_focus):
        run_focus(period="month", set_projects=["💻orbit"])
        data = json.loads(isolated_focus.read_text())
        key = _period_key("month", today)
        assert "💻orbit" in data["month"][key]

    def test_set_defaults_to_day_if_no_period(self, today, isolated_focus):
        run_focus(set_projects=["💻orbit"])
        data = json.loads(isolated_focus.read_text())
        key = _period_key("day", today)
        assert "💻orbit" in data["day"][key]

    def test_set_unknown_project_kept_as_is(self, today, monkeypatch, capsys):
        # _resolve returns None for unknown projects
        monkeypatch.setattr("core.focus.find_project", lambda name: None)
        run_focus(period="day", set_projects=["nonexistent"])
        out = capsys.readouterr().out
        assert "no encontrado" in out.lower() or "⚠️" in out

    def test_clear_empties_period(self, today, focus_with_data):
        run_focus(period="month", clear=True)
        assert get_focus("month", today) == []

    def test_clear_returns_zero(self, today, capsys):
        rc = run_focus(period="day", clear=True)
        assert rc == 0

    def test_clear_defaults_to_day(self, today, focus_with_data):
        # Clear with no period should default to "day"
        run_focus(clear=True)
        assert get_focus("day", today) == []
        assert get_focus("month", today) != []   # month untouched

    def test_show_suggests_command_when_empty(self, today, capsys):
        run_focus(period="week")
        out = capsys.readouterr().out
        assert "orbit focus week --set" in out

    def test_show_no_focus_suggestion_in_all_view(self, today, capsys):
        run_focus()
        out = capsys.readouterr().out
        assert "orbit focus month --set" in out

    def test_interactive_no_tty_returns_zero(self, today, monkeypatch, capsys):
        monkeypatch.setattr("sys.stdin.isatty", lambda: False)
        rc = run_focus(interactive=True, period="month")
        assert rc == 0

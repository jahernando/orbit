"""Tests for orbit reorganize — interactive triage of pending items."""

from datetime import date, timedelta
from pathlib import Path

import pytest

from core import reorganize


# ── Period resolution ─────────────────────────────────────────────────────

class TestResolvePeriod:

    def test_today_default(self):
        lo, hi, overdue = reorganize._resolve_period("today")
        assert lo == hi == date.today()
        assert overdue is True

    def test_empty_means_today(self):
        lo, hi, overdue = reorganize._resolve_period("")
        assert lo == hi == date.today()
        assert overdue is True

    def test_week_is_iso_week(self):
        lo, hi, overdue = reorganize._resolve_period("week")
        assert (hi - lo).days == 6
        assert lo.weekday() == 0  # Monday
        assert overdue is False

    def test_month(self):
        lo, hi, overdue = reorganize._resolve_period("month")
        assert lo.day == 1
        assert (hi + timedelta(days=1)).day == 1  # next day is the 1st of next month
        assert overdue is False

    def test_iso_week_explicit(self):
        lo, hi, _ = reorganize._resolve_period("2026-W21")
        assert lo.weekday() == 0
        assert lo.year == 2026
        assert (hi - lo).days == 6

    def test_specific_date(self):
        lo, hi, overdue = reorganize._resolve_period("2026-05-15")
        assert lo == hi == date(2026, 5, 15)
        assert overdue is False


# ── Item-in-period filter ─────────────────────────────────────────────────

class TestItemInPeriod:

    def setup_method(self):
        self.lo = date(2026, 5, 11)
        self.hi = date(2026, 5, 17)

    def test_in_range(self):
        item = {"date": "2026-05-13", "status": "pending"}
        assert reorganize._item_in_period(item, "task", self.lo, self.hi, False)

    def test_out_of_range(self):
        item = {"date": "2026-05-20", "status": "pending"}
        assert not reorganize._item_in_period(item, "task", self.lo, self.hi, False)

    def test_overdue_included_when_today(self):
        item = {"date": "2026-04-01", "status": "pending"}
        assert reorganize._item_in_period(item, "task", self.lo, self.hi, True)

    def test_overdue_excluded_otherwise(self):
        item = {"date": "2026-04-01", "status": "pending"}
        assert not reorganize._item_in_period(item, "task", self.lo, self.hi, False)

    def test_done_excluded(self):
        item = {"date": "2026-05-13", "status": "done"}
        assert not reorganize._item_in_period(item, "task", self.lo, self.hi, True)

    def test_cancelled_excluded(self):
        item = {"date": "2026-05-13", "cancelled": True}
        assert not reorganize._item_in_period(item, "reminder", self.lo, self.hi, True)

    def test_undated_task_in_today_with_overdue(self):
        item = {"date": None, "status": "pending"}
        assert reorganize._item_in_period(item, "task", self.lo, self.hi, True)

    def test_undated_event_excluded(self):
        item = {"date": None}
        assert not reorganize._item_in_period(item, "ev", self.lo, self.hi, True)


# ── Type alias normalization ──────────────────────────────────────────────

class TestCanonicalType:

    def test_aliases(self):
        assert reorganize._canonical_type("tasks") == "task"
        assert reorganize._canonical_type("task") == "task"
        assert reorganize._canonical_type("milestone") == "ms"
        assert reorganize._canonical_type("milestones") == "ms"
        assert reorganize._canonical_type("event") == "ev"
        assert reorganize._canonical_type("events") == "ev"
        assert reorganize._canonical_type("ev") == "ev"
        assert reorganize._canonical_type("rem") == "reminder"
        assert reorganize._canonical_type("reminders") == "reminder"

    def test_all_or_none(self):
        assert reorganize._canonical_type(None) is None
        assert reorganize._canonical_type("all") is None
        assert reorganize._canonical_type("") is None


# ── Item collection (file-system level) ──────────────────────────────────

def _make_proj(tmp_path: Path, name: str = "🌀test") -> Path:
    proj = tmp_path / name
    proj.mkdir()
    base = name.lstrip("🌀")
    (proj / f"{base}-agenda.md").write_text(
        "# Agenda\n\n"
        "## ✅ Tareas\n\n"
        "## 🏁 Hitos\n\n"
        "## 📅 Eventos\n\n"
        "## 💬 Recordatorios\n"
    )
    (proj / f"{base}-project.md").write_text("# project\n")
    return proj


def _seed(proj: Path, items: dict):
    base = proj.name.lstrip("🌀")
    agenda = proj / f"{base}-agenda.md"
    from core.agenda_cmds import _read_agenda, _write_agenda
    data = _read_agenda(agenda)
    for k, lst in items.items():
        data[k] = lst
    _write_agenda(agenda, data)


class TestCollectItems:

    def test_collects_all_kinds(self, tmp_path, monkeypatch):
        proj = _make_proj(tmp_path, "🌀foo")
        today = date.today().isoformat()
        _seed(proj, {
            "tasks":      [{"desc": "T",  "date": today, "status": "pending"}],
            "milestones": [{"desc": "M",  "date": today, "status": "pending"}],
            "events":     [{"desc": "E",  "date": today, "time": "10:00"}],
            "reminders":  [{"desc": "R",  "date": today, "time": "09:00"}],
        })
        monkeypatch.setattr(reorganize, "iter_project_dirs", lambda: [proj])
        monkeypatch.setattr(reorganize, "_is_new_project", lambda d: True)

        items = reorganize._collect_items(None, None, "today")
        kinds = sorted(k for k, _, _ in items)
        assert kinds == ["ev", "ms", "reminder", "task"]

    def test_filters_by_type(self, tmp_path, monkeypatch):
        proj = _make_proj(tmp_path, "🌀foo")
        today = date.today().isoformat()
        _seed(proj, {
            "tasks":   [{"desc": "T", "date": today, "status": "pending"}],
            "events":  [{"desc": "E", "date": today, "time": "10:00"}],
        })
        monkeypatch.setattr(reorganize, "iter_project_dirs", lambda: [proj])
        monkeypatch.setattr(reorganize, "_is_new_project", lambda d: True)

        items = reorganize._collect_items("tasks", None, "today")
        assert {k for k, _, _ in items} == {"task"}

    def test_overdue_surfaced_when_today(self, tmp_path, monkeypatch):
        proj = _make_proj(tmp_path, "🌀foo")
        long_ago = (date.today() - timedelta(days=30)).isoformat()
        _seed(proj, {"tasks": [{"desc": "Old", "date": long_ago, "status": "pending"}]})
        monkeypatch.setattr(reorganize, "iter_project_dirs", lambda: [proj])
        monkeypatch.setattr(reorganize, "_is_new_project", lambda d: True)
        items = reorganize._collect_items(None, None, "today")
        assert len(items) == 1
        assert items[0][2]["desc"] == "Old"

    def test_overdue_not_surfaced_when_specific_week(self, tmp_path, monkeypatch):
        proj = _make_proj(tmp_path, "🌀foo")
        long_ago = (date.today() - timedelta(days=30)).isoformat()
        _seed(proj, {"tasks": [{"desc": "Old", "date": long_ago, "status": "pending"}]})
        monkeypatch.setattr(reorganize, "iter_project_dirs", lambda: [proj])
        monkeypatch.setattr(reorganize, "_is_new_project", lambda d: True)
        items = reorganize._collect_items(None, None, "week")
        # "Old" is well outside this week and overdue isn't included.
        assert items == []

    def test_done_excluded(self, tmp_path, monkeypatch):
        proj = _make_proj(tmp_path, "🌀foo")
        today = date.today().isoformat()
        _seed(proj, {
            "tasks": [
                {"desc": "T1", "date": today, "status": "pending"},
                {"desc": "T2", "date": today, "status": "done"},
            ]
        })
        monkeypatch.setattr(reorganize, "iter_project_dirs", lambda: [proj])
        monkeypatch.setattr(reorganize, "_is_new_project", lambda d: True)
        items = reorganize._collect_items(None, None, "today")
        descs = [i["desc"] for _, _, i in items]
        assert descs == ["T1"]

    def test_overdue_first_in_sort(self, tmp_path, monkeypatch):
        proj = _make_proj(tmp_path, "🌀foo")
        today = date.today()
        _seed(proj, {"tasks": [
            {"desc": "Today",   "date": today.isoformat(),                 "status": "pending"},
            {"desc": "Overdue", "date": (today - timedelta(days=5)).isoformat(), "status": "pending"},
        ]})
        monkeypatch.setattr(reorganize, "iter_project_dirs", lambda: [proj])
        monkeypatch.setattr(reorganize, "_is_new_project", lambda d: True)
        items = reorganize._collect_items(None, None, "today")
        assert [i["desc"] for _, _, i in items] == ["Overdue", "Today"]


# ── Format row (smoke) ────────────────────────────────────────────────────

class TestFormatRow:

    def test_dated(self, tmp_path):
        proj = tmp_path / "🌀foo"
        proj.mkdir()
        item = {"desc": "Hi", "date": (date.today() + timedelta(days=1)).isoformat()}
        line = reorganize._format_item_row(1, "task", proj, item)
        assert "Hi" in line and "[🌀foo]" in line and "✅" in line

    def test_overdue_marker(self, tmp_path):
        proj = tmp_path / "🌀foo"
        proj.mkdir()
        item = {"desc": "Old", "date": (date.today() - timedelta(days=3)).isoformat()}
        line = reorganize._format_item_row(1, "task", proj, item)
        assert "⚠️" in line

    def test_undated(self, tmp_path):
        proj = tmp_path / "🌀foo"
        proj.mkdir()
        item = {"desc": "Some day", "date": None}
        line = reorganize._format_item_row(1, "task", proj, item)
        assert "sin fecha" in line

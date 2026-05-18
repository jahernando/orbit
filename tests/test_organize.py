"""Tests for orbit organize — interactive triage of pending items."""

from datetime import date, timedelta
from pathlib import Path

import pytest

from core import organize


# ── Period resolution ─────────────────────────────────────────────────────

class TestResolvePeriod:

    def test_today_default(self):
        lo, hi, overdue = organize._resolve_period("today")
        assert lo == hi == date.today()
        assert overdue is True

    def test_empty_means_today(self):
        lo, hi, overdue = organize._resolve_period("")
        assert lo == hi == date.today()
        assert overdue is True

    def test_week_is_iso_week(self):
        lo, hi, overdue = organize._resolve_period("week")
        assert (hi - lo).days == 6
        assert lo.weekday() == 0  # Monday
        assert overdue is False

    def test_month(self):
        lo, hi, overdue = organize._resolve_period("month")
        assert lo.day == 1
        assert (hi + timedelta(days=1)).day == 1  # next day is the 1st of next month
        assert overdue is False

    def test_iso_week_explicit(self):
        lo, hi, _ = organize._resolve_period("2026-W21")
        assert lo.weekday() == 0
        assert lo.year == 2026
        assert (hi - lo).days == 6

    def test_specific_date(self):
        lo, hi, overdue = organize._resolve_period("2026-05-15")
        assert lo == hi == date(2026, 5, 15)
        assert overdue is False


# ── Item-in-period filter ─────────────────────────────────────────────────

class TestItemInPeriod:

    def setup_method(self):
        self.lo = date(2026, 5, 11)
        self.hi = date(2026, 5, 17)

    def test_in_range(self):
        item = {"date": "2026-05-13", "status": "pending"}
        assert organize._item_in_period(item, "task", self.lo, self.hi, False)

    def test_out_of_range(self):
        item = {"date": "2026-05-20", "status": "pending"}
        assert not organize._item_in_period(item, "task", self.lo, self.hi, False)

    def test_overdue_included_when_today(self):
        item = {"date": "2026-04-01", "status": "pending"}
        assert organize._item_in_period(item, "task", self.lo, self.hi, True)

    def test_overdue_excluded_otherwise(self):
        item = {"date": "2026-04-01", "status": "pending"}
        assert not organize._item_in_period(item, "task", self.lo, self.hi, False)

    def test_done_excluded(self):
        item = {"date": "2026-05-13", "status": "done"}
        assert not organize._item_in_period(item, "task", self.lo, self.hi, True)

    def test_cancelled_excluded(self):
        item = {"date": "2026-05-13", "cancelled": True}
        assert not organize._item_in_period(item, "reminder", self.lo, self.hi, True)

    def test_undated_task_excluded_by_default(self):
        """Default is to require a date; undated only with explicit opt-in."""
        item = {"date": None, "status": "pending"}
        assert not organize._item_in_period(item, "task", self.lo, self.hi, True)

    def test_undated_task_with_opt_in(self):
        item = {"date": None, "status": "pending"}
        assert organize._item_in_period(item, "task", self.lo, self.hi, True,
                                            include_undated=True)

    def test_undated_event_excluded_even_with_opt_in(self):
        """Events without a date are nonsensical — never list."""
        item = {"date": None}
        assert not organize._item_in_period(item, "ev", self.lo, self.hi, True,
                                                include_undated=True)


# ── Type alias normalization ──────────────────────────────────────────────

class TestCanonicalType:

    def test_aliases(self):
        assert organize._canonical_type("tasks") == "task"
        assert organize._canonical_type("task") == "task"
        assert organize._canonical_type("milestone") == "ms"
        assert organize._canonical_type("milestones") == "ms"
        assert organize._canonical_type("event") == "ev"
        assert organize._canonical_type("events") == "ev"
        assert organize._canonical_type("ev") == "ev"
        assert organize._canonical_type("rem") == "reminder"
        assert organize._canonical_type("reminders") == "reminder"

    def test_all_or_none(self):
        assert organize._canonical_type(None) is None
        assert organize._canonical_type("all") is None
        assert organize._canonical_type("") is None


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
        monkeypatch.setattr(organize, "iter_project_dirs", lambda: [proj])
        monkeypatch.setattr(organize, "_is_new_project", lambda d: True)

        items = organize._collect_items(None, None, "today")
        kinds = sorted(k for k, _, _ in items)
        assert kinds == ["ev", "ms", "reminder", "task"]

    def test_filters_by_type(self, tmp_path, monkeypatch):
        proj = _make_proj(tmp_path, "🌀foo")
        today = date.today().isoformat()
        _seed(proj, {
            "tasks":   [{"desc": "T", "date": today, "status": "pending"}],
            "events":  [{"desc": "E", "date": today, "time": "10:00"}],
        })
        monkeypatch.setattr(organize, "iter_project_dirs", lambda: [proj])
        monkeypatch.setattr(organize, "_is_new_project", lambda d: True)

        items = organize._collect_items("tasks", None, "today")
        assert {k for k, _, _ in items} == {"task"}

    def test_overdue_surfaced_when_today(self, tmp_path, monkeypatch):
        proj = _make_proj(tmp_path, "🌀foo")
        long_ago = (date.today() - timedelta(days=30)).isoformat()
        _seed(proj, {"tasks": [{"desc": "Old", "date": long_ago, "status": "pending"}]})
        monkeypatch.setattr(organize, "iter_project_dirs", lambda: [proj])
        monkeypatch.setattr(organize, "_is_new_project", lambda d: True)
        items = organize._collect_items(None, None, "today")
        assert len(items) == 1
        assert items[0][2]["desc"] == "Old"

    def test_overdue_not_surfaced_when_specific_week(self, tmp_path, monkeypatch):
        proj = _make_proj(tmp_path, "🌀foo")
        long_ago = (date.today() - timedelta(days=30)).isoformat()
        _seed(proj, {"tasks": [{"desc": "Old", "date": long_ago, "status": "pending"}]})
        monkeypatch.setattr(organize, "iter_project_dirs", lambda: [proj])
        monkeypatch.setattr(organize, "_is_new_project", lambda d: True)
        items = organize._collect_items(None, None, "week")
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
        monkeypatch.setattr(organize, "iter_project_dirs", lambda: [proj])
        monkeypatch.setattr(organize, "_is_new_project", lambda d: True)
        items = organize._collect_items(None, None, "today")
        descs = [i["desc"] for _, _, i in items]
        assert descs == ["T1"]

    def test_overdue_first_in_sort(self, tmp_path, monkeypatch):
        proj = _make_proj(tmp_path, "🌀foo")
        today = date.today()
        _seed(proj, {"tasks": [
            {"desc": "Today",   "date": today.isoformat(),                 "status": "pending"},
            {"desc": "Overdue", "date": (today - timedelta(days=5)).isoformat(), "status": "pending"},
        ]})
        monkeypatch.setattr(organize, "iter_project_dirs", lambda: [proj])
        monkeypatch.setattr(organize, "_is_new_project", lambda d: True)
        items = organize._collect_items(None, None, "today")
        assert [i["desc"] for _, _, i in items] == ["Overdue", "Today"]

    def test_undated_excluded_by_default(self, tmp_path, monkeypatch):
        proj = _make_proj(tmp_path, "🌀foo")
        today = date.today().isoformat()
        _seed(proj, {"tasks": [
            {"desc": "Dated",   "date": today, "status": "pending"},
            {"desc": "Undated", "date": None,  "status": "pending"},
        ]})
        monkeypatch.setattr(organize, "iter_project_dirs", lambda: [proj])
        monkeypatch.setattr(organize, "_is_new_project", lambda d: True)
        items = organize._collect_items(None, None, "today")
        assert [i["desc"] for _, _, i in items] == ["Dated"]

    def test_undated_included_with_flag(self, tmp_path, monkeypatch):
        proj = _make_proj(tmp_path, "🌀foo")
        today = date.today().isoformat()
        _seed(proj, {"tasks": [
            {"desc": "Dated",   "date": today, "status": "pending"},
            {"desc": "Undated", "date": None,  "status": "pending"},
        ]})
        monkeypatch.setattr(organize, "iter_project_dirs", lambda: [proj])
        monkeypatch.setattr(organize, "_is_new_project", lambda d: True)
        items = organize._collect_items(None, None, "today", include_undated=True)
        descs = sorted(i["desc"] for _, _, i in items)
        assert descs == ["Dated", "Undated"]


# ── Format row (smoke) ────────────────────────────────────────────────────

class TestFormatRow:

    def test_dated(self, tmp_path):
        proj = tmp_path / "🌀foo"
        proj.mkdir()
        item = {"desc": "Hi", "date": (date.today() + timedelta(days=1)).isoformat()}
        line = organize._format_item_row(1, "task", proj, item)
        assert "Hi" in line and "[🌀foo]" in line and "✅" in line

    def test_overdue_marker(self, tmp_path):
        proj = tmp_path / "🌀foo"
        proj.mkdir()
        item = {"desc": "Old", "date": (date.today() - timedelta(days=3)).isoformat()}
        line = organize._format_item_row(1, "task", proj, item)
        assert "⚠️" in line

    def test_undated(self, tmp_path):
        proj = tmp_path / "🌀foo"
        proj.mkdir()
        item = {"desc": "Some day", "date": None}
        line = organize._format_item_row(1, "task", proj, item)
        assert "sin fecha" in line


# ══════════════════════════════════════════════════════════════════════════════
# Triage mode — _collect_pending_items + _format_triage_row + _apply_triage_action
# ══════════════════════════════════════════════════════════════════════════════

class TestCollectPendingItems:

    def test_includes_ff_today_and_overdue(self, tmp_path, monkeypatch):
        proj = _make_proj(tmp_path, "🌀foo")
        today = date.today()
        past = (today - timedelta(days=4)).isoformat()
        _seed(proj, {"tasks": [
            {"desc": "Hoy",   "date": None, "status": "pending",
             "ff": today.isoformat()},
            {"desc": "Vieja", "date": None, "status": "pending", "ff": past},
        ]})
        monkeypatch.setattr(organize, "iter_project_dirs", lambda: [proj])
        monkeypatch.setattr(organize, "_is_new_project", lambda d: True)
        items = organize._collect_pending_items(None, today)
        # Most overdue first.
        assert [t["desc"] for _, t in items] == ["Vieja", "Hoy"]

    def test_excludes_ff_future(self, tmp_path, monkeypatch):
        proj = _make_proj(tmp_path, "🌀foo")
        today = date.today()
        future = (today + timedelta(days=3)).isoformat()
        _seed(proj, {"tasks": [
            {"desc": "Mañana", "date": None, "status": "pending", "ff": future},
        ]})
        monkeypatch.setattr(organize, "iter_project_dirs", lambda: [proj])
        monkeypatch.setattr(organize, "_is_new_project", lambda d: True)
        assert organize._collect_pending_items(None, today) == []

    def test_excludes_someday(self, tmp_path, monkeypatch):
        proj = _make_proj(tmp_path, "🌀foo")
        today = date.today()
        _seed(proj, {"tasks": [
            {"desc": "Quizá", "date": None, "status": "pending", "ff": "someday"},
        ]})
        monkeypatch.setattr(organize, "iter_project_dirs", lambda: [proj])
        monkeypatch.setattr(organize, "_is_new_project", lambda d: True)
        assert organize._collect_pending_items(None, today) == []

    def test_excludes_planned_without_ff(self, tmp_path, monkeypatch):
        proj = _make_proj(tmp_path, "🌀foo")
        today = date.today()
        _seed(proj, {"tasks": [
            {"desc": "Planned", "date": today.isoformat(), "status": "pending"},
        ]})
        monkeypatch.setattr(organize, "iter_project_dirs", lambda: [proj])
        monkeypatch.setattr(organize, "_is_new_project", lambda d: True)
        assert organize._collect_pending_items(None, today) == []

    def test_excludes_done(self, tmp_path, monkeypatch):
        proj = _make_proj(tmp_path, "🌀foo")
        today = date.today()
        _seed(proj, {"tasks": [
            {"desc": "Hecha", "date": None, "status": "done",
             "ff": today.isoformat()},
        ]})
        monkeypatch.setattr(organize, "iter_project_dirs", lambda: [proj])
        monkeypatch.setattr(organize, "_is_new_project", lambda d: True)
        assert organize._collect_pending_items(None, today) == []


class TestFormatTriageRow:

    def test_today_no_mark(self, tmp_path):
        proj = tmp_path / "🌀foo"; proj.mkdir()
        t = {"desc": "X", "ff": "2026-05-18", "snooze_count": 0, "failed_count": 0}
        line = organize._format_triage_row(1, proj, t, "2026-05-18")
        assert "X" in line and "⏩2026-05-18" in line
        assert "❗" not in line and "💤" not in line

    def test_overdue_marks_exclamation(self, tmp_path):
        proj = tmp_path / "🌀foo"; proj.mkdir()
        t = {"desc": "X", "ff": "2026-05-15", "snooze_count": 0, "failed_count": 0}
        line = organize._format_triage_row(1, proj, t, "2026-05-18")
        assert "❗" in line and "❗❗" not in line

    def test_three_snoozes_double_exclamation(self, tmp_path):
        proj = tmp_path / "🌀foo"; proj.mkdir()
        t = {"desc": "X", "ff": "2026-05-18", "snooze_count": 3, "failed_count": 0}
        line = organize._format_triage_row(1, proj, t, "2026-05-18")
        assert "❗❗" in line and "💤3" in line

    def test_failed_counter_shown(self, tmp_path):
        proj = tmp_path / "🌀foo"; proj.mkdir()
        t = {"desc": "X", "ff": "2026-05-18", "snooze_count": 0, "failed_count": 2}
        line = organize._format_triage_row(1, proj, t, "2026-05-18")
        assert "❌2" in line


class TestApplyTriageAction:
    """Smoke-test that triage actions route to the correct runner."""

    def _setup(self, tmp_path, monkeypatch):
        from core.agenda_cmds import _read_agenda
        # Real environment: ORBIT_HOME so api.add_task can resolve the project.
        type_dir = tmp_path / "💻sw"
        type_dir.mkdir()
        proj = type_dir / "💻foo"
        proj.mkdir()
        (proj / "foo-project.md").write_text(
            "# foo\n- Tipo: 💻 Software\n- Estado: [auto]\n- Prioridad: media\n")
        (proj / "foo-logbook.md").write_text("# Logbook — foo\n\n")
        (proj / "foo-agenda.md").write_text("# Agenda — foo\n\n<!-- -->\n")
        monkeypatch.setattr("core.config.ORBIT_HOME", tmp_path)
        monkeypatch.setattr("core.config._ORBIT_JSON", tmp_path / "orbit.json")
        monkeypatch.setattr("core.log.PROJECTS_DIR", tmp_path)
        return proj, lambda: _read_agenda(proj / "foo-agenda.md")

    def test_p_plan_promotes(self, tmp_path, monkeypatch):
        from core import api
        proj, read = self._setup(tmp_path, monkeypatch)
        api.add_task(project="💻foo", text="X", ff="2026-05-18")
        # Feed: date prompt then time prompt (empty)
        prompts = iter(["2026-06-01", ""])
        monkeypatch.setattr(organize, "_prompt",
                            lambda *a, **k: next(prompts))
        task = read()["tasks"][-1]
        ok = organize._apply_triage_action("p", proj, task)
        assert ok is True
        new = read()["tasks"][-1]
        assert new["date"] == "2026-06-01"
        assert new["ff"] is None

    def test_f_snooze_increments_count(self, tmp_path, monkeypatch):
        from core import api
        proj, read = self._setup(tmp_path, monkeypatch)
        api.add_task(project="💻foo", text="X", ff="2026-05-18")
        monkeypatch.setattr(organize, "_prompt",
                            lambda *a, **k: "2026-05-25")
        task = read()["tasks"][-1]
        ok = organize._apply_triage_action("f", proj, task)
        assert ok is True
        new = read()["tasks"][-1]
        assert new["ff"] == "2026-05-25"
        assert new["snooze_count"] == 1

    def test_f_someday_keyword(self, tmp_path, monkeypatch):
        from core import api
        proj, read = self._setup(tmp_path, monkeypatch)
        api.add_task(project="💻foo", text="X", ff="2026-05-18")
        monkeypatch.setattr(organize, "_prompt",
                            lambda *a, **k: "someday")
        task = read()["tasks"][-1]
        ok = organize._apply_triage_action("f", proj, task)
        assert ok is True
        assert read()["tasks"][-1]["ff"] == "someday"

    def test_d_drop_cancels(self, tmp_path, monkeypatch):
        from core import api
        proj, read = self._setup(tmp_path, monkeypatch)
        api.add_task(project="💻foo", text="X", ff="2026-05-18")
        task = read()["tasks"][-1]
        ok = organize._apply_triage_action("d", proj, task)
        assert ok is True
        assert read()["tasks"][-1]["status"] == "cancelled"

    def test_n_done_marks_completed(self, tmp_path, monkeypatch):
        from core import api
        proj, read = self._setup(tmp_path, monkeypatch)
        api.add_task(project="💻foo", text="X", ff="2026-05-18")
        task = read()["tasks"][-1]
        ok = organize._apply_triage_action("n", proj, task)
        assert ok is True
        assert read()["tasks"][-1]["status"] == "done"


class TestApplyActionPending:
    """[p]ending verb in organize default mode (planned → pending)."""

    def _setup(self, tmp_path, monkeypatch):
        from core.agenda_cmds import _read_agenda
        type_dir = tmp_path / "💻sw"
        type_dir.mkdir()
        proj = type_dir / "💻foo"
        proj.mkdir()
        (proj / "foo-project.md").write_text(
            "# foo\n- Tipo: 💻 Software\n- Estado: [auto]\n- Prioridad: media\n")
        (proj / "foo-logbook.md").write_text("# Logbook — foo\n\n")
        (proj / "foo-agenda.md").write_text("# Agenda — foo\n\n<!-- -->\n")
        monkeypatch.setattr("core.config.ORBIT_HOME", tmp_path)
        monkeypatch.setattr("core.config._ORBIT_JSON", tmp_path / "orbit.json")
        monkeypatch.setattr("core.log.PROJECTS_DIR", tmp_path)
        return proj, lambda: _read_agenda(proj / "foo-agenda.md")

    def test_p_someday_degrades_planned(self, tmp_path, monkeypatch):
        from core import api
        proj, read = self._setup(tmp_path, monkeypatch)
        api.add_task(project="💻foo", text="Old X", date="2020-01-01")
        monkeypatch.setattr(organize, "_prompt",
                            lambda *a, **k: "someday")
        item = read()["tasks"][-1]
        ok = organize._apply_action("p", "task", proj, item)
        assert ok is True
        new = read()["tasks"][-1]
        assert new["ff"] == "someday"
        assert new["date"] is None
        assert new["time"] is None

    def test_p_enter_keeps_date_as_ff(self, tmp_path, monkeypatch):
        from core import api
        proj, read = self._setup(tmp_path, monkeypatch)
        api.add_task(project="💻foo", text="X", date="2020-01-01")
        monkeypatch.setattr(organize, "_prompt",
                            lambda *a, **k: "")
        item = read()["tasks"][-1]
        ok = organize._apply_action("p", "task", proj, item)
        assert ok is True
        assert read()["tasks"][-1]["ff"] == "2020-01-01"

    def test_p_rejected_for_ms(self, tmp_path, monkeypatch, capsys):
        proj, _ = self._setup(tmp_path, monkeypatch)
        # No prompt should happen because we early-exit on kind!=task.
        ok = organize._apply_action("p", "ms", proj,
                                     {"desc": "M", "status": "pending"})
        assert ok is False
        assert "sólo tasks" in capsys.readouterr().out

    def test_demote_planned_clears_ring(self, tmp_path, monkeypatch):
        """Bug fix: degrading planned→pending must also drop ring (ring needs date+time)."""
        from core import api
        from core.agenda_cmds import run_task_pending
        proj, read = self._setup(tmp_path, monkeypatch)
        api.add_task(project="💻foo", text="X",
                     date="2020-01-01", time="10:00", ring="15m")
        run_task_pending(project="💻foo", text="X", target_ff="someday")
        t = read()["tasks"][-1]
        assert t["date"] is None
        assert t["time"] is None
        assert t["ring"] is None
        assert t["ff"] == "someday"

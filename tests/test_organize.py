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
# Triage mode (F5) — followups ⏩ <= today across the four cita types.
#   _collect_followup_items + _format_triage_row + _apply_triage_action
# ══════════════════════════════════════════════════════════════════════════════

class TestCollectFollowupItems:
    """`_collect_followup_items` surfaces one row per followup ⏩ <= today,
    across all four cita types, skipping done/cancelled and future ones."""

    def test_includes_due_and_overdue_all_kinds(self, tmp_path, monkeypatch):
        proj = _make_proj(tmp_path, "🌀foo")
        today = date.today()
        due = today.isoformat()
        past = (today - timedelta(days=4)).isoformat()
        _seed(proj, {
            "tasks":      [{"desc": "T", "date": None, "status": "pending",
                            "notes": [f"⏩ {due} rev"]}],
            "milestones": [{"desc": "M", "date": None, "status": "pending",
                            "notes": [f"⏩ {past}"]}],
            "events":     [{"desc": "E", "date": due, "notes": [f"⏩ {due}"]}],
            "reminders":  [{"desc": "R", "date": due, "notes": [f"⏩ {past}"]}],
        })
        monkeypatch.setattr(organize, "iter_project_dirs", lambda: [proj])
        monkeypatch.setattr(organize, "_is_new_project", lambda d: True)
        items = organize._collect_followup_items(None, today)
        # (project_dir, kind, item, fup) — all four kinds surface.
        assert sorted(k for _, k, _, _ in items) == ["ev", "ms", "reminder", "task"]
        # Sorted ascending by followup date (most overdue first).
        dates = [fup["date"] for _, _, _, fup in items]
        assert dates == sorted(dates)
        assert dates[0] == past

    def test_ties_broken_by_description(self, tmp_path, monkeypatch):
        proj = _make_proj(tmp_path, "🌀foo")
        today = date.today()
        past = (today - timedelta(days=2)).isoformat()
        _seed(proj, {
            "milestones": [{"desc": "M", "date": None, "status": "pending",
                            "notes": [f"⏩ {past}"]}],
            "reminders":  [{"desc": "R", "date": today.isoformat(),
                            "notes": [f"⏩ {past}"]}],
        })
        monkeypatch.setattr(organize, "iter_project_dirs", lambda: [proj])
        monkeypatch.setattr(organize, "_is_new_project", lambda d: True)
        items = organize._collect_followup_items(None, today)
        # Same followup date → order is by item description ("M" before "R").
        assert [it["desc"] for _, _, it, _ in items] == ["M", "R"]

    def test_excludes_future_followups(self, tmp_path, monkeypatch):
        proj = _make_proj(tmp_path, "🌀foo")
        today = date.today()
        future = (today + timedelta(days=3)).isoformat()
        _seed(proj, {"tasks": [
            {"desc": "Later", "date": None, "status": "pending",
             "notes": [f"⏩ {future}"]},
        ]})
        monkeypatch.setattr(organize, "iter_project_dirs", lambda: [proj])
        monkeypatch.setattr(organize, "_is_new_project", lambda d: True)
        assert organize._collect_followup_items(None, today) == []

    def test_excludes_done_and_cancelled(self, tmp_path, monkeypatch):
        proj = _make_proj(tmp_path, "🌀foo")
        today = date.today()
        due = today.isoformat()
        _seed(proj, {
            "tasks":     [{"desc": "Done", "date": None, "status": "done",
                           "notes": [f"⏩ {due}"]}],
            "reminders": [{"desc": "Cxl", "date": due, "cancelled": True,
                           "notes": [f"⏩ {due}"]}],
        })
        monkeypatch.setattr(organize, "iter_project_dirs", lambda: [proj])
        monkeypatch.setattr(organize, "_is_new_project", lambda d: True)
        assert organize._collect_followup_items(None, today) == []

    def test_item_without_followup_excluded(self, tmp_path, monkeypatch):
        proj = _make_proj(tmp_path, "🌀foo")
        today = date.today()
        _seed(proj, {"tasks": [
            {"desc": "Plain", "date": today.isoformat(), "status": "pending"},
        ]})
        monkeypatch.setattr(organize, "iter_project_dirs", lambda: [proj])
        monkeypatch.setattr(organize, "_is_new_project", lambda d: True)
        assert organize._collect_followup_items(None, today) == []

    def test_row_carries_item_and_followup(self, tmp_path, monkeypatch):
        proj = _make_proj(tmp_path, "🌀foo")
        today = date.today()
        due = today.isoformat()
        _seed(proj, {"tasks": [
            {"desc": "T", "date": None, "status": "pending",
             "notes": [f"⏩ {due} llamar a Ana"]},
        ]})
        monkeypatch.setattr(organize, "iter_project_dirs", lambda: [proj])
        monkeypatch.setattr(organize, "_is_new_project", lambda d: True)
        items = organize._collect_followup_items(None, today)
        assert len(items) == 1
        pd, kind, item, fup = items[0]
        assert pd == proj and kind == "task"
        assert item["desc"] == "T"
        assert fup == {"date": due, "desc": "llamar a Ana"}


class TestFormatTriageRow:
    """New signature `(idx, project_dir, kind, item, fup, today_iso)`; no
    snooze/failed marks after F5."""

    def _fup(self, fdate, desc=None):
        return {"date": fdate, "desc": desc}

    def test_emoji_per_kind(self, tmp_path):
        proj = tmp_path / "🌀foo"; proj.mkdir()
        item = {"desc": "X"}
        fup = self._fup("2026-07-09")
        assert "✅" in organize._format_triage_row(1, proj, "task", item, fup, "2026-07-09")
        assert "🏁" in organize._format_triage_row(1, proj, "ms", item, fup, "2026-07-09")
        assert "📅" in organize._format_triage_row(1, proj, "ev", item, fup, "2026-07-09")
        assert "💬" in organize._format_triage_row(1, proj, "reminder", item, fup, "2026-07-09")

    def test_today_no_mark(self, tmp_path):
        proj = tmp_path / "🌀foo"; proj.mkdir()
        line = organize._format_triage_row(
            1, proj, "task", {"desc": "X"}, self._fup("2026-07-09"), "2026-07-09")
        assert "X" in line and "[🌀foo]" in line and "⏩2026-07-09" in line
        assert "❗" not in line

    def test_overdue_marks_exclamation(self, tmp_path):
        proj = tmp_path / "🌀foo"; proj.mkdir()
        line = organize._format_triage_row(
            1, proj, "task", {"desc": "X"}, self._fup("2026-07-05"), "2026-07-09")
        assert "❗" in line

    def test_desc_appended_as_extra(self, tmp_path):
        proj = tmp_path / "🌀foo"; proj.mkdir()
        line = organize._format_triage_row(
            1, proj, "reminder", {"desc": "X"},
            self._fup("2026-07-09", "revisar presupuesto"), "2026-07-09")
        assert "— revisar presupuesto" in line

    def test_no_desc_no_dash(self, tmp_path):
        proj = tmp_path / "🌀foo"; proj.mkdir()
        line = organize._format_triage_row(
            1, proj, "task", {"desc": "X"}, self._fup("2026-07-09"), "2026-07-09")
        assert " — " not in line


class TestApplyTriageAction:
    """The five followup-triage actions: p/s/c/n/d."""

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

    def _attach_fup(self, proj, section_key, desc, fdate, fdesc=None):
        """Hang a ⏩ followup on an already-written cita, via the real API."""
        from core.agenda_cmds import _read_agenda, _write_agenda
        from core.agenda.display import add_followup
        agenda = proj / "foo-agenda.md"
        data = _read_agenda(agenda)
        for it in data[section_key]:
            if it["desc"] == desc:
                add_followup(it, fdate, fdesc)
        _write_agenda(agenda, data)

    def _row(self, read, section_key):
        """Return (item, fup) for the last cita in *section_key*."""
        from core.agenda.display import item_followups
        item = read()[section_key][-1]
        return item, item_followups(item)[0]

    def test_p_plan_sets_date_and_clears_followup(self, tmp_path, monkeypatch):
        from core import api
        from core.agenda.display import item_followups
        proj, read = self._setup(tmp_path, monkeypatch)
        api.add_task(project="💻foo", text="X")
        self._attach_fup(proj, "tasks", "X", "2026-07-01", "tema")
        # Feed: date prompt then time prompt (empty).
        prompts = iter(["2026-06-01", ""])
        monkeypatch.setattr(organize, "_prompt", lambda *a, **k: next(prompts))
        item, fup = self._row(read, "tasks")
        ok = organize._apply_triage_action("p", proj, "task", item, fup)
        assert ok is True
        new = read()["tasks"][-1]
        assert new["date"] == "2026-06-01"
        assert item_followups(new) == []   # the followup was cleared

    def test_s_snooze_moves_followup(self, tmp_path, monkeypatch):
        from core import api
        from core.agenda.display import item_followups
        proj, read = self._setup(tmp_path, monkeypatch)
        api.add_task(project="💻foo", text="X")
        self._attach_fup(proj, "tasks", "X", "2026-07-01", "tema")
        monkeypatch.setattr(organize, "_prompt", lambda *a, **k: "2026-07-20")
        item, fup = self._row(read, "tasks")
        ok = organize._apply_triage_action("s", proj, "task", item, fup)
        assert ok is True
        fups = item_followups(read()["tasks"][-1])
        assert len(fups) == 1
        assert fups[0]["date"] == "2026-07-20"
        assert fups[0]["desc"] == "tema"        # description preserved

    def test_s_snooze_enter_defaults_tomorrow(self, tmp_path, monkeypatch):
        from core import api
        from core.agenda.display import item_followups
        proj, read = self._setup(tmp_path, monkeypatch)
        api.add_task(project="💻foo", text="X")
        self._attach_fup(proj, "tasks", "X", "2026-07-01")
        monkeypatch.setattr(organize, "_prompt", lambda *a, **k: "")
        item, fup = self._row(read, "tasks")
        ok = organize._apply_triage_action("s", proj, "task", item, fup)
        assert ok is True
        tomorrow = (date.today() + timedelta(days=1)).isoformat()
        assert item_followups(read()["tasks"][-1])[0]["date"] == tomorrow

    def test_c_clear_drops_followup_keeps_cita(self, tmp_path, monkeypatch):
        from core import api
        from core.agenda.display import item_followups
        proj, read = self._setup(tmp_path, monkeypatch)
        api.add_task(project="💻foo", text="X")
        self._attach_fup(proj, "tasks", "X", "2026-07-01")
        item, fup = self._row(read, "tasks")
        ok = organize._apply_triage_action("c", proj, "task", item, fup)
        assert ok is True
        cita = read()["tasks"][-1]
        assert item_followups(cita) == []           # followup gone
        assert cita["status"] == "pending"          # cita itself untouched

    def test_n_done_completes_task(self, tmp_path, monkeypatch):
        from core import api
        proj, read = self._setup(tmp_path, monkeypatch)
        api.add_task(project="💻foo", text="X")
        self._attach_fup(proj, "tasks", "X", "2026-07-01")
        item, fup = self._row(read, "tasks")
        ok = organize._apply_triage_action("n", proj, "task", item, fup)
        assert ok is True
        assert read()["tasks"][-1]["status"] == "done"

    def test_n_rejected_for_event(self, tmp_path, monkeypatch, capsys):
        proj, _ = self._setup(tmp_path, monkeypatch)
        # ev/rem have no `done`: early-exit with a notice, no runner touched.
        item = {"desc": "E"}
        fup = {"date": "2026-07-01", "desc": None}
        ok = organize._apply_triage_action("n", proj, "ev", item, fup)
        assert ok is False
        assert "no tiene 'done'" in capsys.readouterr().out

    def test_d_drop_cancels_cita(self, tmp_path, monkeypatch):
        from core import api
        proj, read = self._setup(tmp_path, monkeypatch)
        api.add_task(project="💻foo", text="X")
        self._attach_fup(proj, "tasks", "X", "2026-07-01")
        item, fup = self._row(read, "tasks")
        ok = organize._apply_triage_action("d", proj, "task", item, fup)
        assert ok is True
        assert read()["tasks"][-1]["status"] == "cancelled"

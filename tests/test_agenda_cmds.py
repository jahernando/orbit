"""Unit tests for core/agenda_cmds.py — Phase 3: task / milestone / event commands."""

import sys
import textwrap
from datetime import date, timedelta
from pathlib import Path

import pytest

# ── Helpers ────────────────────────────────────────────────────────────────────

def _strip_emoji(name: str) -> str:
    """Strip leading non-ASCII chars and variation selectors from a name."""
    import unicodedata
    i = 0
    while i < len(name):
        c = name[i]
        if ord(c) > 127 or unicodedata.category(c) in ("So", "Sk", "Mn", "Cf"):
            i += 1
        else:
            break
    return name[i:]


def _make_project(type_dir: Path, name: str = "test-project") -> Path:
    """Create a minimal new-format project directory inside a type dir."""
    project_dir = type_dir / name
    project_dir.mkdir(parents=True, exist_ok=True)
    base = _strip_emoji(name)
    (project_dir / f"{base}-project.md").write_text(
        f"# {name}\n- Tipo: 💻 Software\n- Estado: [auto]\n- Prioridad: media\n"
    )
    (project_dir / f"{base}-logbook.md").write_text(f"# Logbook — {name}\n\n")
    (project_dir / f"{base}-agenda.md").write_text(f"# Agenda — {name}\n\n<!-- ... -->\n")
    (project_dir / f"{base}-highlights.md").write_text(f"# Highlights — {name}\n\n")
    (project_dir / "notes").mkdir(exist_ok=True)
    return project_dir


def _agenda_text(project_dir: Path) -> str:
    base = _strip_emoji(project_dir.name)
    return (project_dir / f"{base}-agenda.md").read_text()


def _logbook_text(project_dir: Path) -> str:
    base = _strip_emoji(project_dir.name)
    return (project_dir / f"{base}-logbook.md").read_text()


# ── Fixtures ───────────────────────────────────────────────────────────────────

@pytest.fixture()
def projects_dir(tmp_path, monkeypatch):
    """Patch ORBIT_HOME so iter_project_dirs() scans tmp_path for type dirs."""
    type_dir = tmp_path / "💻software"
    type_dir.mkdir()
    monkeypatch.setattr("core.config.ORBIT_HOME", tmp_path)
    monkeypatch.setattr("core.config._ORBIT_JSON", tmp_path / "orbit.json")
    monkeypatch.setattr("core.log.PROJECTS_DIR", tmp_path)
    return type_dir


@pytest.fixture()
def proj(projects_dir):
    """One ready-made project inside the patched projects_dir."""
    return _make_project(projects_dir, "💻test-project")


# ══════════════════════════════════════════════════════════════════════════════
# _parse_task_line / _format_task_line
# ══════════════════════════════════════════════════════════════════════════════

class TestParseTaskLine:
    from core.agenda_cmds import _parse_task_line, _format_task_line

    def test_pending_no_extras(self):
        from core.agenda_cmds import _parse_task_line
        t = _parse_task_line("- [ ] Do something")
        assert t["status"] == "pending"
        assert t["desc"]   == "Do something"
        assert t["date"]   is None
        assert t["recur"]  is None
        assert t["ring"]   is None

    def test_done(self):
        from core.agenda_cmds import _parse_task_line
        t = _parse_task_line("- [x] Task done (2026-03-10)")
        assert t["status"] == "done"
        assert t["date"]   == "2026-03-10"

    def test_cancelled(self):
        from core.agenda_cmds import _parse_task_line
        t = _parse_task_line("- [-] Cancelled task")
        assert t["status"] == "cancelled"

    def test_with_all_attrs(self):
        from core.agenda_cmds import _parse_task_line
        t = _parse_task_line("- [ ] Weekly report (2026-03-14) [recur:weekly] [ring:1d]")
        assert t["desc"]  == "Weekly report"
        assert t["date"]  == "2026-03-14"
        assert t["recur"] == "weekly"
        assert t["ring"]  == "1d"

    def test_returns_none_for_non_task(self):
        from core.agenda_cmds import _parse_task_line
        assert _parse_task_line("## ✅ Tareas") is None
        assert _parse_task_line("2026-03-10 — meeting") is None
        assert _parse_task_line("") is None

    def test_roundtrip(self):
        from core.agenda_cmds import _parse_task_line, _format_task_line
        line = "- [ ] My task (2026-04-01) [recur:monthly] [ring:2h]"
        t = _parse_task_line(line)
        assert _format_task_line(t) == "- [ ] My task (2026-04-01) 🔄monthly 🔔2h"

    def test_format_pending_no_date(self):
        from core.agenda_cmds import _format_task_line
        t = {"status": "pending", "desc": "Simple task", "date": None, "recur": None, "ring": None}
        assert _format_task_line(t) == "- [ ] Simple task"

    def test_format_done(self):
        from core.agenda_cmds import _format_task_line
        t = {"status": "done", "desc": "Done task", "date": "2026-03-09", "recur": None, "ring": None}
        assert _format_task_line(t) == "- [x] Done task (2026-03-09)"

    def test_time_range_accepted(self, proj):
        # Focus blocks: task accepts --time HH:MM-HH:MM and persists it
        # to agenda.md as ⏰HH:MM-HH:MM.
        from core import api
        from core.agenda_cmds import _read_agenda
        api.add_task(project=proj.name, text="Focus block",
                     date="2026-05-15", time="09:00-11:00")
        data = _read_agenda(proj / f"{_strip_emoji(proj.name)}-agenda.md")
        assert data["tasks"][-1]["time"] == "09:00-11:00"
        assert "⏰09:00-11:00" in _agenda_text(proj)

    def test_time_simple_still_accepted(self, proj):
        # Backwards compat: HH:MM (no range) still works on task.
        from core import api
        from core.agenda_cmds import _read_agenda
        api.add_task(project=proj.name, text="Plain timed",
                     date="2026-05-15", time="09:00")
        data = _read_agenda(proj / f"{_strip_emoji(proj.name)}-agenda.md")
        assert data["tasks"][-1]["time"] == "09:00"

    def test_time_range_invalid_rejected(self, proj):
        # Garbage range is still rejected by _valid_time.
        from core import api
        with pytest.raises(ValueError, match="invalid time"):
            api.add_task(project=proj.name, text="Bad",
                         date="2026-05-15", time="09:00-noon")


# ══════════════════════════════════════════════════════════════════════════════
# ff / snooze_count / failed_count — taxonomy items rev 2
# ══════════════════════════════════════════════════════════════════════════════

class TestFfAndCounters:
    """Parser+writer of ⏩ (fast-forward), 💤 (snooze_count), ❌ (failed_count)."""

    def test_parse_ff_date(self):
        from core.agenda_cmds import _parse_task_line
        t = _parse_task_line("- [ ] Esperar X ⏩2026-05-24")
        assert t["ff"] == "2026-05-24"
        assert t["desc"] == "Esperar X"
        assert t["snooze_count"] == 0
        assert t["failed_count"] == 0

    def test_parse_ff_someday(self):
        from core.agenda_cmds import _parse_task_line
        t = _parse_task_line("- [ ] Quizá Y ⏩someday")
        assert t["ff"] == "someday"

    def test_parse_counters(self):
        from core.agenda_cmds import _parse_task_line
        t = _parse_task_line("- [ ] Esperar Z ⏩2026-05-24 💤3 ❌1")
        assert t["ff"] == "2026-05-24"
        assert t["snooze_count"] == 3
        assert t["failed_count"] == 1
        assert t["desc"] == "Esperar Z"

    def test_parse_legacy_bracketed(self):
        from core.agenda_cmds import _parse_task_line
        t = _parse_task_line("- [ ] Old style [ff:2026-05-24] [snooze:2] [failed:5]")
        assert t["ff"] == "2026-05-24"
        assert t["snooze_count"] == 2
        assert t["failed_count"] == 5

    def test_parse_absent_defaults(self):
        from core.agenda_cmds import _parse_task_line
        t = _parse_task_line("- [ ] Plain task (2026-04-01)")
        assert t["ff"] is None
        assert t["snooze_count"] == 0
        assert t["failed_count"] == 0

    def test_format_emits_only_when_truthy(self):
        from core.agenda_cmds import _format_task_line
        t = {"status": "pending", "desc": "X", "date": None,
             "recur": None, "ring": None,
             "ff": None, "snooze_count": 0, "failed_count": 0}
        assert _format_task_line(t) == "- [ ] X"

    def test_format_with_ff_only(self):
        from core.agenda_cmds import _format_task_line
        t = {"status": "pending", "desc": "X", "date": None,
             "recur": None, "ring": None,
             "ff": "2026-05-24", "snooze_count": 0, "failed_count": 0}
        assert _format_task_line(t) == "- [ ] X ⏩2026-05-24"

    def test_format_with_counters(self):
        from core.agenda_cmds import _format_task_line
        t = {"status": "pending", "desc": "X", "date": None,
             "recur": None, "ring": None,
             "ff": "2026-05-24", "snooze_count": 3, "failed_count": 1}
        assert _format_task_line(t) == "- [ ] X ⏩2026-05-24 💤3 ❌1"

    def test_roundtrip_full(self):
        from core.agenda_cmds import _parse_task_line, _format_task_line
        line = "- [ ] Esperar revisión (2026-05-30) 🔄weekly 🔔1h ⏩2026-05-24 💤2 ❌1"
        t = _parse_task_line(line)
        assert _format_task_line(t) == line

    def test_roundtrip_someday(self):
        from core.agenda_cmds import _parse_task_line, _format_task_line
        line = "- [ ] Quizá algún día ⏩someday"
        t = _parse_task_line(line)
        assert _format_task_line(t) == line

    def test_desc_strips_ff_and_counters(self):
        # Bare desc must not include the ⏩/💤/❌ tokens.
        from core.agenda_cmds import _parse_task_line
        t = _parse_task_line("- [ ] Esperar Z ⏩2026-05-24 💤3 ❌1")
        assert "⏩" not in t["desc"]
        assert "💤" not in t["desc"]
        assert "❌" not in t["desc"]


# ══════════════════════════════════════════════════════════════════════════════
# Verbs: task plan / task pending — F2 of taxonomy plan
# ══════════════════════════════════════════════════════════════════════════════

class TestTaskAddDefaultFf:
    """api.add_task without date defaults ff to today (raw capture)."""

    def test_no_date_sets_ff_today(self, proj):
        from datetime import date
        from core import api
        from core.agenda_cmds import _read_agenda
        api.add_task(project=proj.name, text="Bare capture")
        data = _read_agenda(proj / f"{_strip_emoji(proj.name)}-agenda.md")
        assert data["tasks"][-1]["ff"] == date.today().isoformat()

    def test_with_date_no_ff_default(self, proj):
        from core import api
        from core.agenda_cmds import _read_agenda
        api.add_task(project=proj.name, text="Planned",
                     date="2026-06-01")
        t = _read_agenda(proj / f"{_strip_emoji(proj.name)}-agenda.md")["tasks"][-1]
        assert t["ff"] is None

    def test_explicit_ff_overrides_default(self, proj):
        from core import api
        from core.agenda_cmds import _read_agenda
        api.add_task(project=proj.name, text="Someday X", ff="someday")
        t = _read_agenda(proj / f"{_strip_emoji(proj.name)}-agenda.md")["tasks"][-1]
        assert t["ff"] == "someday"

    def test_run_task_add_with_ff(self, proj):
        from core.agenda_cmds import run_task_add, _read_agenda
        # CLI surface: run_task_add accepts ff and propagates to api.
        rc = run_task_add(project=proj.name, text="Esperar X", ff="2026-06-15")
        assert rc == 0
        t = _read_agenda(proj / f"{_strip_emoji(proj.name)}-agenda.md")["tasks"][-1]
        assert t["ff"] == "2026-06-15"
        assert t["date"] is None

    def test_run_task_add_ff_someday(self, proj):
        from core.agenda_cmds import run_task_add, _read_agenda
        rc = run_task_add(project=proj.name, text="Quizá Y", ff="someday")
        assert rc == 0
        t = _read_agenda(proj / f"{_strip_emoji(proj.name)}-agenda.md")["tasks"][-1]
        assert t["ff"] == "someday"

    def test_run_task_add_ff_with_date_combined(self, proj):
        # Both can coexist: a planned date with an earlier ff for internal review.
        from core.agenda_cmds import run_task_add, _read_agenda
        rc = run_task_add(project=proj.name, text="Charla viernes",
                          date_val="2026-06-05", ff="2026-06-02")
        assert rc == 0
        t = _read_agenda(proj / f"{_strip_emoji(proj.name)}-agenda.md")["tasks"][-1]
        assert t["date"] == "2026-06-05"
        assert t["ff"] == "2026-06-02"

    def test_add_invalid_ff_rejected(self, proj, capsys):
        from core.agenda_cmds import run_task_add
        rc = run_task_add(project=proj.name, text="Bad", ff="garbage")
        assert rc == 1
        # _generic_add translates api ValueError to CLI error wording
        assert "ff" in capsys.readouterr().out.lower()


class TestRunTaskPlan:
    """task plan: promote pending→planned or reschedule planned."""

    def _add_pending(self, proj, text, ff_val):
        from core import api
        api.add_task(project=proj.name, text=text, ff=ff_val)

    def _add_planned(self, proj, text, date_val):
        from core import api
        api.add_task(project=proj.name, text=text, date=date_val)

    def _tasks(self, proj):
        from core.agenda_cmds import _read_agenda
        return _read_agenda(proj / f"{_strip_emoji(proj.name)}-agenda.md")["tasks"]

    def test_promote_pending_to_planned(self, proj):
        from core.agenda_cmds import run_task_plan
        self._add_pending(proj, "X", "2026-05-20")
        run_task_plan(project=proj.name, text="X", date_val="2026-06-01")
        t = self._tasks(proj)[-1]
        assert t["date"] == "2026-06-01"
        assert t["ff"] is None
        assert t["snooze_count"] == 0

    def test_promote_resets_snooze_count(self, proj):
        from core.agenda_cmds import run_task_plan, _read_agenda, _write_agenda
        self._add_pending(proj, "X", "2026-05-20")
        # bump snooze on the underlying item
        agenda_path = proj / f"{_strip_emoji(proj.name)}-agenda.md"
        data = _read_agenda(agenda_path)
        data["tasks"][-1]["snooze_count"] = 5
        _write_agenda(agenda_path, data)
        run_task_plan(project=proj.name, text="X", date_val="2026-06-01")
        assert self._tasks(proj)[-1]["snooze_count"] == 0

    def test_reschedule_overdue_increments_failed_count(self, proj):
        from core.agenda_cmds import run_task_plan
        self._add_planned(proj, "X", "2020-01-01")   # very overdue
        run_task_plan(project=proj.name, text="X", date_val="2026-06-01")
        t = self._tasks(proj)[-1]
        assert t["date"] == "2026-06-01"
        assert t["failed_count"] == 1

    def test_reschedule_future_does_not_increment(self, proj):
        from core.agenda_cmds import run_task_plan
        self._add_planned(proj, "X", "2099-01-01")   # future
        run_task_plan(project=proj.name, text="X", date_val="2099-02-01")
        t = self._tasks(proj)[-1]
        assert t["failed_count"] == 0

    def test_plan_with_time(self, proj):
        from core.agenda_cmds import run_task_plan
        self._add_pending(proj, "Focus block", "2026-05-20")
        run_task_plan(project=proj.name, text="Focus block",
                      date_val="2026-06-01", time_val="09:00-11:00")
        t = self._tasks(proj)[-1]
        assert t["time"] == "09:00-11:00"

    def test_missing_date_returns_error(self, proj, capsys):
        from core.agenda_cmds import run_task_plan
        self._add_pending(proj, "X", "2026-05-20")
        rc = run_task_plan(project=proj.name, text="X", date_val=None)
        assert rc == 1
        assert "fecha" in capsys.readouterr().out.lower()


class TestRunTaskPending:
    """task pending: demote planned→pending or snooze pending."""

    def _add_pending(self, proj, text, ff_val):
        from core import api
        api.add_task(project=proj.name, text=text, ff=ff_val)

    def _add_planned(self, proj, text, date_val):
        from core import api
        api.add_task(project=proj.name, text=text, date=date_val)

    def _tasks(self, proj):
        from core.agenda_cmds import _read_agenda
        return _read_agenda(proj / f"{_strip_emoji(proj.name)}-agenda.md")["tasks"]

    def test_snooze_pending_increments_snooze_count(self, proj):
        from core.agenda_cmds import run_task_pending
        self._add_pending(proj, "X", "2026-05-20")
        run_task_pending(project=proj.name, text="X", target_ff="2026-05-25")
        t = self._tasks(proj)[-1]
        assert t["ff"] == "2026-05-25"
        assert t["snooze_count"] == 1

    def test_snooze_default_is_tomorrow(self, proj):
        from datetime import date, timedelta
        from core.agenda_cmds import run_task_pending
        self._add_pending(proj, "X", "2026-05-20")
        run_task_pending(project=proj.name, text="X", target_ff=None)
        t = self._tasks(proj)[-1]
        assert t["ff"] == (date.today() + timedelta(days=1)).isoformat()
        assert t["snooze_count"] == 1

    def test_snooze_to_someday(self, proj):
        from core.agenda_cmds import run_task_pending
        self._add_pending(proj, "X", "2026-05-20")
        run_task_pending(project=proj.name, text="X", target_ff="someday")
        t = self._tasks(proj)[-1]
        assert t["ff"] == "someday"

    def test_demote_planned_moves_date_to_ff(self, proj):
        from core.agenda_cmds import run_task_pending
        self._add_planned(proj, "X", "2026-06-01")
        run_task_pending(project=proj.name, text="X", target_ff=None)
        t = self._tasks(proj)[-1]
        assert t["ff"] == "2026-06-01"
        assert t["date"] is None
        # demote is not a snooze: counter stays
        assert t["snooze_count"] == 0

    def test_demote_with_explicit_target(self, proj):
        from core.agenda_cmds import run_task_pending
        self._add_planned(proj, "X", "2026-06-01")
        run_task_pending(project=proj.name, text="X", target_ff="2026-07-15")
        t = self._tasks(proj)[-1]
        assert t["ff"] == "2026-07-15"
        assert t["date"] is None

    def test_invalid_target_rejected(self, proj, capsys):
        from core.agenda_cmds import run_task_pending
        self._add_pending(proj, "X", "2026-05-20")
        rc = run_task_pending(project=proj.name, text="X", target_ff="garbage")
        assert rc == 1
        assert "no reconocida" in capsys.readouterr().out.lower()


class TestTaskEditFf:
    """task edit --ff allows direct manipulation of the ff field."""

    def test_edit_sets_ff(self, proj):
        from core import api
        from core.agenda_cmds import run_task_edit, _read_agenda
        api.add_task(project=proj.name, text="X", date="2026-06-01")
        run_task_edit(project=proj.name, text="X", new_ff="2026-05-25")
        t = _read_agenda(proj / f"{_strip_emoji(proj.name)}-agenda.md")["tasks"][-1]
        assert t["ff"] == "2026-05-25"

    def test_edit_ff_none_clears(self, proj):
        from core import api
        from core.agenda_cmds import run_task_edit, _read_agenda
        api.add_task(project=proj.name, text="X", ff="2026-05-24")
        run_task_edit(project=proj.name, text="X", new_ff="none")
        t = _read_agenda(proj / f"{_strip_emoji(proj.name)}-agenda.md")["tasks"][-1]
        assert t["ff"] is None

    def test_edit_invalid_ff_rejected(self, proj, capsys):
        from core import api
        from core.agenda_cmds import run_task_edit
        api.add_task(project=proj.name, text="X", date="2026-06-01")
        rc = run_task_edit(project=proj.name, text="X", new_ff="garbage")
        assert rc == 1
        assert "fast-forward" in capsys.readouterr().out.lower()


# ══════════════════════════════════════════════════════════════════════════════
# _parse_event_line / _format_event_line
# ══════════════════════════════════════════════════════════════════════════════

class TestParseEventLine:
    def test_simple(self):
        from core.agenda_cmds import _parse_event_line
        e = _parse_event_line("2026-03-15 — Conference")
        assert e["date"] == "2026-03-15"
        assert e["desc"] == "Conference"
        assert e["end"]  is None

    def test_with_end(self):
        from core.agenda_cmds import _parse_event_line
        e = _parse_event_line("2026-03-15 — Conference [end:2026-03-17]")
        assert e["end"] == "2026-03-17"
        assert e["desc"] == "Conference"

    def test_none_for_non_event(self):
        from core.agenda_cmds import _parse_event_line
        assert _parse_event_line("- [ ] task") is None
        assert _parse_event_line("## 📅 Eventos") is None

    def test_roundtrip(self):
        from core.agenda_cmds import _parse_event_line, _format_event_line
        line = "2026-06-01 — Summer school [end:2026-06-05]"
        assert _format_event_line(_parse_event_line(line)) == "2026-06-01 — Summer school →2026-06-05"


# ══════════════════════════════════════════════════════════════════════════════
# _read_agenda / _write_agenda
# ══════════════════════════════════════════════════════════════════════════════

class TestAgendaIO:
    def test_empty_agenda(self, proj):
        from core.agenda_cmds import _read_agenda
        data = _read_agenda(proj / "test-project-agenda.md")
        assert data["tasks"]      == []
        assert data["milestones"] == []
        assert data["events"]     == []

    def test_missing_file(self, proj):
        from core.agenda_cmds import _read_agenda
        data = _read_agenda(proj / "nonexistent.md")
        assert data["tasks"] == []

    def test_write_and_read_tasks(self, proj):
        from core.agenda_cmds import _read_agenda, _write_agenda
        data = _read_agenda(proj / "test-project-agenda.md")
        data["tasks"].append({"status": "pending", "desc": "Test task",
                               "date": "2026-04-01", "recur": None, "ring": None})
        _write_agenda(proj / "test-project-agenda.md", data)
        data2 = _read_agenda(proj / "test-project-agenda.md")
        assert len(data2["tasks"]) == 1
        assert data2["tasks"][0]["desc"] == "Test task"

    def test_write_preserves_header(self, proj):
        from core.agenda_cmds import _read_agenda, _write_agenda
        data = _read_agenda(proj / "test-project-agenda.md")
        data["tasks"].append({"status": "pending", "desc": "X",
                               "date": None, "recur": None, "ring": None})
        _write_agenda(proj / "test-project-agenda.md", data)
        text = _agenda_text(proj)
        assert text.startswith("# Agenda")

    def test_write_multiple_sections(self, proj):
        from core.agenda_cmds import _read_agenda, _write_agenda
        data = _read_agenda(proj / "test-project-agenda.md")
        data["tasks"].append({"status": "pending", "desc": "Task A",
                               "date": None, "recur": None, "ring": None})
        data["milestones"].append({"status": "pending", "desc": "Milestone A",
                                   "date": "2026-06-01", "recur": None, "ring": None})
        data["events"].append({"date": "2026-04-10", "desc": "Conference", "end": None})
        _write_agenda(proj / "test-project-agenda.md", data)
        text = _agenda_text(proj)
        assert "## ✅ Tareas" in text
        assert "## 🏁 Hitos" in text
        assert "## 📅 Eventos" in text

    def test_events_sorted_by_date(self, proj):
        from core.agenda_cmds import _read_agenda, _write_agenda
        data = _read_agenda(proj / "test-project-agenda.md")
        data["events"] = [
            {"date": "2026-05-01", "desc": "Later", "end": None},
            {"date": "2026-03-01", "desc": "Earlier", "end": None},
        ]
        _write_agenda(proj / "test-project-agenda.md", data)
        data2 = _read_agenda(proj / "test-project-agenda.md")
        assert data2["events"][0]["date"] == "2026-03-01"
        assert data2["events"][1]["date"] == "2026-05-01"

    def test_roundtrip_complex(self, proj):
        from core.agenda_cmds import _read_agenda, _write_agenda
        data = _read_agenda(proj / "test-project-agenda.md")
        data["tasks"] = [
            {"status": "pending", "desc": "T1", "date": "2026-04-01",
             "recur": "weekly", "ring": "1d"},
            {"status": "done", "desc": "T2", "date": "2026-03-01",
             "recur": None, "ring": None},
        ]
        data["milestones"] = [
            {"status": "pending", "desc": "M1", "date": "2026-07-01",
             "recur": None, "ring": None},
        ]
        _write_agenda(proj / "test-project-agenda.md", data)
        data2 = _read_agenda(proj / "test-project-agenda.md")
        assert len(data2["tasks"])      == 2
        assert len(data2["milestones"]) == 1
        assert data2["tasks"][0]["recur"] == "weekly"


# ══════════════════════════════════════════════════════════════════════════════
# _next_occurrence
# ══════════════════════════════════════════════════════════════════════════════

class TestNextOccurrence:
    def test_daily(self):
        from core.agenda_cmds import _next_occurrence
        assert _next_occurrence("2026-03-10", "daily", "2026-03-10") == "2026-03-11"

    def test_weekly(self):
        from core.agenda_cmds import _next_occurrence
        assert _next_occurrence("2026-03-10", "weekly", "2026-03-10") == "2026-03-17"

    def test_monthly(self):
        from core.agenda_cmds import _next_occurrence
        assert _next_occurrence("2026-03-10", "monthly", "2026-03-10") == "2026-04-10"

    def test_monthly_end_of_month(self):
        from core.agenda_cmds import _next_occurrence
        # Jan 31 → Feb last day
        assert _next_occurrence("2026-01-31", "monthly", "2026-01-31") == "2026-02-28"

    def test_weekdays_from_friday(self):
        from core.agenda_cmds import _next_occurrence
        # 2026-03-06 is Friday → next weekday is Monday 2026-03-09
        result = _next_occurrence("2026-03-06", "weekdays", "2026-03-06")
        d = date.fromisoformat(result)
        assert d.weekday() < 5  # Mon–Fri

    def test_no_due_date_uses_done_date(self):
        from core.agenda_cmds import _next_occurrence
        result = _next_occurrence(None, "weekly", "2026-03-09")
        assert result == "2026-03-16"

    # Extended recurrence

    def test_every_2_weeks(self):
        from core.agenda_cmds import _next_occurrence
        assert _next_occurrence("2026-03-10", "every-2-weeks", "2026-03-10") == "2026-03-24"

    def test_every_3_days(self):
        from core.agenda_cmds import _next_occurrence
        assert _next_occurrence("2026-03-10", "every-3-days", "2026-03-10") == "2026-03-13"

    def test_every_2_months(self):
        from core.agenda_cmds import _next_occurrence
        assert _next_occurrence("2026-03-10", "every-2-months", "2026-03-10") == "2026-05-10"

    def test_first_monday(self):
        from core.agenda_cmds import _next_occurrence
        # Base 2026-03-10 → first Monday of April = 2026-04-06
        assert _next_occurrence("2026-03-10", "first-monday", "2026-03-10") == "2026-04-06"

    def test_last_friday(self):
        from core.agenda_cmds import _next_occurrence
        # Base 2026-03-10 → last Friday of April = 2026-04-24
        assert _next_occurrence("2026-03-10", "last-friday", "2026-03-10") == "2026-04-24"


class TestNormalizeRecur:

    def test_simple_values_unchanged(self):
        from core.agenda_cmds import _normalize_recur
        assert _normalize_recur("daily") == "daily"
        assert _normalize_recur("weekly") == "weekly"
        assert _normalize_recur("monthly") == "monthly"
        assert _normalize_recur("weekdays") == "weekdays"

    def test_every_n_weeks(self):
        from core.agenda_cmds import _normalize_recur
        assert _normalize_recur("every 2 weeks") == "every-2-weeks"
        assert _normalize_recur("every-2-weeks") == "every-2-weeks"

    def test_every_n_days(self):
        from core.agenda_cmds import _normalize_recur
        assert _normalize_recur("every 3 days") == "every-3-days"

    def test_every_n_months(self):
        from core.agenda_cmds import _normalize_recur
        assert _normalize_recur("every 2 months") == "every-2-months"

    def test_first_monday(self):
        from core.agenda_cmds import _normalize_recur
        assert _normalize_recur("first monday") == "first-monday"
        assert _normalize_recur("first-monday") == "first-monday"
        assert _normalize_recur("1st monday") == "first-monday"

    def test_last_friday(self):
        from core.agenda_cmds import _normalize_recur
        assert _normalize_recur("last friday") == "last-friday"

    def test_spanish_weekday(self):
        from core.agenda_cmds import _normalize_recur
        assert _normalize_recur("first lunes") == "first-lunes"
        assert _normalize_recur("last viernes") == "last-viernes"


class TestIsValidRecur:

    def test_simple_valid(self):
        from core.agenda_cmds import is_valid_recur
        assert is_valid_recur("daily")
        assert is_valid_recur("weekly")

    def test_extended_valid(self):
        from core.agenda_cmds import is_valid_recur
        assert is_valid_recur("every 2 weeks")
        assert is_valid_recur("first monday")
        assert is_valid_recur("last friday")

    def test_invalid(self):
        from core.agenda_cmds import is_valid_recur
        assert not is_valid_recur("biweekly")
        assert not is_valid_recur("every banana")


# ══════════════════════════════════════════════════════════════════════════════
# run_task_add
# ══════════════════════════════════════════════════════════════════════════════

class TestRunTaskAdd:
    def test_adds_task(self, proj, projects_dir, capsys):
        from core.agenda_cmds import run_task_add
        rc = run_task_add("test-project", "Write tests")
        assert rc == 0
        captured = capsys.readouterr()
        assert "Write tests" in captured.out

    def test_task_appears_in_file(self, proj, projects_dir):
        from core.agenda_cmds import run_task_add, _read_agenda
        run_task_add("test-project", "My task", date_val="2026-04-01")
        data = _read_agenda(proj / "test-project-agenda.md")
        assert data["tasks"][0]["desc"]  == "My task"
        assert data["tasks"][0]["date"]  == "2026-04-01"
        assert data["tasks"][0]["status"] == "pending"

    def test_task_with_recur_and_ring(self, proj, projects_dir):
        from core.agenda_cmds import run_task_add, _read_agenda
        run_task_add("test-project", "Weekly check", date_val="2026-03-15", recur="weekly", ring="1d")
        data = _read_agenda(proj / "test-project-agenda.md")
        t = data["tasks"][0]
        assert t["recur"] == "weekly"
        assert t["ring"]  == "1d"

    def test_invalid_recur(self, proj, projects_dir, capsys):
        from core.agenda_cmds import run_task_add
        rc = run_task_add("test-project", "Bad recur", recur="hourly")
        assert rc == 1
        assert "hourly" in capsys.readouterr().out

    def test_project_not_found(self, projects_dir, capsys):
        from core.agenda_cmds import run_task_add
        rc = run_task_add("nonexistent", "Task")
        assert rc == 1

    def test_creates_agenda_if_missing(self, proj, projects_dir):
        from core.agenda_cmds import run_task_add, _read_agenda
        (proj / "test-project-agenda.md").unlink()
        rc = run_task_add("test-project", "New task")
        # Agenda file is re-created on write
        assert rc == 0
        data = _read_agenda(proj / "test-project-agenda.md")
        assert data["tasks"][0]["desc"] == "New task"

    def test_multiple_tasks(self, proj, projects_dir):
        from core.agenda_cmds import run_task_add, _read_agenda
        run_task_add("test-project", "Task A")
        run_task_add("test-project", "Task B")
        data = _read_agenda(proj / "test-project-agenda.md")
        assert len(data["tasks"]) == 2

    def test_output_includes_date(self, proj, projects_dir, capsys):
        from core.agenda_cmds import run_task_add
        run_task_add("test-project", "Task with date", date_val="2026-05-01")
        out = capsys.readouterr().out
        assert "2026-05-01" in out


# ══════════════════════════════════════════════════════════════════════════════
# run_task_done
# ══════════════════════════════════════════════════════════════════════════════

class TestRunTaskDone:
    def _setup_task(self, proj, projects_dir, desc="Finish report", recur=None):
        from core.agenda_cmds import run_task_add, _read_agenda, _write_agenda
        run_task_add("test-project", desc, date_val="2026-03-15", recur=recur)

    def test_marks_done_by_text(self, proj, projects_dir, capsys):
        from core.agenda_cmds import run_task_add, run_task_done, _read_agenda
        run_task_add("test-project", "Finish report")
        rc = run_task_done("test-project", "Finish")
        assert rc == 0
        data = _read_agenda(proj / "test-project-agenda.md")
        assert data["tasks"][0]["status"] == "done"

    def test_logbook_entry_on_done(self, proj, projects_dir):
        from core.agenda_cmds import run_task_add, run_task_done
        run_task_add("test-project", "Important task")
        run_task_done("test-project", "Important")
        log = _logbook_text(proj)
        assert "[completada] Tarea: Important task" in log
        assert "[O]" in log

    def test_recurring_task_creates_next(self, proj, projects_dir, capsys):
        from core.agenda_cmds import run_task_add, run_task_done, _read_agenda
        run_task_add("test-project", "Weekly standup", date_val="2026-03-09", recur="weekly")
        rc = run_task_done("test-project", "Weekly standup")
        assert rc == 0
        data = _read_agenda(proj / "test-project-agenda.md")
        # Original is done, new pending task created
        done_tasks    = [t for t in data["tasks"] if t["status"] == "done"]
        pending_tasks = [t for t in data["tasks"] if t["status"] == "pending"]
        assert len(done_tasks)    == 1
        assert len(pending_tasks) == 1
        assert pending_tasks[0]["date"] == "2026-03-16"

    def test_recurring_logbook_includes_next_date(self, proj, projects_dir):
        from core.agenda_cmds import run_task_add, run_task_done
        run_task_add("test-project", "Weekly standup", date_val="2026-03-09", recur="weekly")
        run_task_done("test-project", "standup")
        log = _logbook_text(proj)
        assert "recur: weekly" in log
        assert "próxima:" in log

    def test_done_no_text_interactive_skip(self, proj, projects_dir, monkeypatch):
        from core.agenda_cmds import run_task_add, run_task_done
        run_task_add("test-project", "Some task")
        # stdin not a tty → should return None from _interactive_select
        monkeypatch.setattr(sys, "stdin", open("/dev/null"))
        rc = run_task_done("test-project", None)
        # Returns 1 because no selection was made
        assert rc == 1

    def test_not_found_text(self, proj, projects_dir, capsys):
        from core.agenda_cmds import run_task_add, run_task_done
        run_task_add("test-project", "Existing task")
        rc = run_task_done("test-project", "nonexistent")
        assert rc == 1
        assert "no se encontró" in capsys.readouterr().out


# ══════════════════════════════════════════════════════════════════════════════
# run_task_drop
# ══════════════════════════════════════════════════════════════════════════════

class TestRunTaskDrop:
    def test_drops_task(self, proj, projects_dir):
        from core.agenda_cmds import run_task_add, run_task_drop, _read_agenda
        run_task_add("test-project", "To drop")
        rc = run_task_drop("test-project", "drop", force=True)
        assert rc == 0
        data = _read_agenda(proj / "test-project-agenda.md")
        assert data["tasks"][0]["status"] == "cancelled"

    def test_logbook_drop_entry(self, proj, projects_dir):
        from core.agenda_cmds import run_task_add, run_task_drop
        run_task_add("test-project", "Bad idea")
        run_task_drop("test-project", "Bad idea", force=True)
        log = _logbook_text(proj)
        assert "[cancelada] Tarea: Bad idea" in log
        assert "[O]" in log

    def test_drop_requires_force_in_noninteractive(self, proj, projects_dir):
        from core.agenda_cmds import run_task_add, run_task_drop, _read_agenda
        run_task_add("test-project", "Keep me")
        rc = run_task_drop("test-project", "Keep me")  # no force, not a tty
        assert rc == 1
        data = _read_agenda(proj / "test-project-agenda.md")
        assert data["tasks"][0]["status"] == "pending"

    def test_drop_recurring_creates_next(self, proj, projects_dir, capsys):
        from core.agenda_cmds import run_task_add, run_task_drop, _read_agenda
        run_task_add("test-project", "Weekly sync", date_val="2026-03-09", recur="weekly")
        rc = run_task_drop("test-project", "Weekly sync", force=True)
        assert rc == 0
        data = _read_agenda(proj / "test-project-agenda.md")
        assert data["tasks"][0]["status"] == "cancelled"
        pending = [t for t in data["tasks"] if t["status"] == "pending"]
        assert len(pending) == 1
        assert pending[0]["desc"] == "Weekly sync"
        assert pending[0]["date"] == "2026-03-16"
        assert pending[0]["recur"] == "weekly"
        out = capsys.readouterr().out
        assert "próxima: 2026-03-16" in out

    def test_drop_recurring_respects_until(self, proj, projects_dir, capsys):
        from core.agenda_cmds import run_task_add, run_task_drop, _read_agenda
        run_task_add("test-project", "Limited task", date_val="2026-03-09",
                     recur="weekly", until="2026-03-10")
        rc = run_task_drop("test-project", "Limited task", force=True)
        assert rc == 0
        data = _read_agenda(proj / "test-project-agenda.md")
        pending = [t for t in data["tasks"] if t["status"] == "pending"]
        assert len(pending) == 0
        out = capsys.readouterr().out
        assert "serie finalizada" in out

    def test_drop_nonrecurring_no_next(self, proj, projects_dir):
        from core.agenda_cmds import run_task_add, run_task_drop, _read_agenda
        run_task_add("test-project", "One-off task", date_val="2026-03-09")
        run_task_drop("test-project", "One-off task", force=True)
        data = _read_agenda(proj / "test-project-agenda.md")
        assert len(data["tasks"]) == 1
        assert data["tasks"][0]["status"] == "cancelled"


# ══════════════════════════════════════════════════════════════════════════════
# run_task_edit
# ══════════════════════════════════════════════════════════════════════════════

class TestRunTaskEdit:
    def test_edit_description(self, proj, projects_dir):
        from core.agenda_cmds import run_task_add, run_task_edit, _read_agenda
        run_task_add("test-project", "Old name")
        rc = run_task_edit("test-project", "Old name", new_text="New name")
        assert rc == 0
        data = _read_agenda(proj / "test-project-agenda.md")
        assert data["tasks"][0]["desc"] == "New name"

    def test_edit_date(self, proj, projects_dir):
        from core.agenda_cmds import run_task_add, run_task_edit, _read_agenda
        run_task_add("test-project", "Task", date_val="2026-03-01")
        run_task_edit("test-project", "Task", new_date="2026-04-01")
        data = _read_agenda(proj / "test-project-agenda.md")
        assert data["tasks"][0]["date"] == "2026-04-01"

    def test_remove_date_with_none(self, proj, projects_dir):
        from core.agenda_cmds import run_task_add, run_task_edit, _read_agenda
        run_task_add("test-project", "Task", date_val="2026-03-01")
        run_task_edit("test-project", "Task", new_date="none")
        data = _read_agenda(proj / "test-project-agenda.md")
        assert data["tasks"][0]["date"] is None

    def test_remove_recur_with_none(self, proj, projects_dir):
        from core.agenda_cmds import run_task_add, run_task_edit, _read_agenda
        run_task_add("test-project", "Task", recur="weekly")
        run_task_edit("test-project", "Task", new_recur="none")
        data = _read_agenda(proj / "test-project-agenda.md")
        assert data["tasks"][0]["recur"] is None

    def test_invalid_recur_in_edit(self, proj, projects_dir, capsys):
        from core.agenda_cmds import run_task_add, run_task_edit
        run_task_add("test-project", "Task")
        rc = run_task_edit("test-project", "Task", new_recur="hourly")
        assert rc == 1


# ══════════════════════════════════════════════════════════════════════════════
# run_task_list
# ══════════════════════════════════════════════════════════════════════════════

class TestRunTaskList:
    def test_lists_pending(self, proj, projects_dir, capsys):
        from core.agenda_cmds import run_task_add, run_task_list
        run_task_add("test-project", "Pending task")
        rc = run_task_list()
        assert rc == 0
        assert "Pending task" in capsys.readouterr().out

    def test_done_filter(self, proj, projects_dir, capsys):
        from core.agenda_cmds import run_task_add, run_task_done, run_task_list
        run_task_add("test-project", "Done task")
        run_task_done("test-project", "Done")
        run_task_list(status_filter="done")
        out = capsys.readouterr().out
        assert "Done task" in out

    def test_no_results(self, proj, projects_dir, capsys):
        from core.agenda_cmds import run_task_list
        rc = run_task_list()
        assert rc == 0
        assert "No hay tareas" in capsys.readouterr().out

    def test_date_filter(self, proj, projects_dir, capsys):
        from core.agenda_cmds import run_task_add, run_task_list
        run_task_add("test-project", "March task", date_val="2026-03-15")
        run_task_add("test-project", "April task", date_val="2026-04-01")
        capsys.readouterr()  # discard add output
        run_task_list(date_filter="2026-03")
        out = capsys.readouterr().out
        assert "March task" in out
        assert "April task" not in out

    def test_specific_project(self, proj, projects_dir, capsys):
        from core.agenda_cmds import run_task_add, run_task_list
        run_task_add("test-project", "My task")
        run_task_list(projects=["test-project"])
        assert "My task" in capsys.readouterr().out

    def test_pending_only_filter(self, proj, projects_dir, capsys):
        from core import api
        from core.agenda_cmds import run_task_list
        api.add_task(project="test-project", text="Planned X", date="2026-06-01")
        api.add_task(project="test-project", text="Pending Y", ff="2026-05-25")
        api.add_task(project="test-project", text="Someday Z", ff="someday")
        capsys.readouterr()  # discard add output
        run_task_list(pending_only=True)
        out = capsys.readouterr().out
        assert "Pending Y" in out
        assert "Planned X" not in out
        assert "Someday Z" not in out

    def test_someday_only_filter(self, proj, projects_dir, capsys):
        from core import api
        from core.agenda_cmds import run_task_list
        api.add_task(project="test-project", text="Pending Y", ff="2026-05-25")
        api.add_task(project="test-project", text="Someday Z", ff="someday")
        capsys.readouterr()
        run_task_list(someday_only=True)
        out = capsys.readouterr().out
        assert "Someday Z" in out
        assert "Pending Y" not in out

    def test_display_shows_ff_and_counters(self, proj, projects_dir, capsys):
        from core import api
        from core.agenda_cmds import run_task_list, _read_agenda, _write_agenda
        api.add_task(project="test-project", text="X", ff="2026-05-25")
        # Bump counters directly to verify display.
        from pathlib import Path
        path = Path(proj) / f"{_strip_emoji(proj.name)}-agenda.md"
        data = _read_agenda(path)
        data["tasks"][-1]["snooze_count"] = 2
        data["tasks"][-1]["failed_count"] = 1
        _write_agenda(path, data)
        capsys.readouterr()
        run_task_list()
        out = capsys.readouterr().out
        assert "⏩2026-05-25" in out
        assert "💤2" in out
        assert "❌1" in out

    def test_pending_only_empty_message(self, proj, projects_dir, capsys):
        from core import api
        from core.agenda_cmds import run_task_list
        api.add_task(project="test-project", text="Planned X", date="2026-06-01")
        capsys.readouterr()
        run_task_list(pending_only=True)
        assert "No hay tareas pending" in capsys.readouterr().out


# ══════════════════════════════════════════════════════════════════════════════
# run_ms_add / run_ms_done / run_ms_cancel / run_ms_edit / run_ms_list
# ══════════════════════════════════════════════════════════════════════════════

class TestMilestones:
    def test_add_milestone(self, proj, projects_dir, capsys):
        from core.agenda_cmds import run_ms_add, _read_agenda
        rc = run_ms_add("test-project", "First calibration complete", date_val="2026-06-01")
        assert rc == 0
        data = _read_agenda(proj / "test-project-agenda.md")
        assert data["milestones"][0]["desc"] == "First calibration complete"
        assert data["milestones"][0]["date"] == "2026-06-01"

    def test_done_milestone(self, proj, projects_dir):
        from core.agenda_cmds import run_ms_add, run_ms_done, _read_agenda
        run_ms_add("test-project", "Key milestone")
        run_ms_done("test-project", "Key")
        data = _read_agenda(proj / "test-project-agenda.md")
        assert data["milestones"][0]["status"] == "done"

    def test_done_logbook_entry(self, proj, projects_dir):
        from core.agenda_cmds import run_ms_add, run_ms_done
        run_ms_add("test-project", "Release v1.0")
        run_ms_done("test-project", "Release")
        log = _logbook_text(proj)
        assert "[alcanzado] Hito: Release v1.0" in log
        assert "[O]" in log

    def test_drop_milestone(self, proj, projects_dir):
        from core.agenda_cmds import run_ms_add, run_ms_drop, _read_agenda
        run_ms_add("test-project", "Deprecated goal")
        run_ms_drop("test-project", "Deprecated", force=True)
        data = _read_agenda(proj / "test-project-agenda.md")
        assert data["milestones"][0]["status"] == "cancelled"

    def test_drop_logbook_entry(self, proj, projects_dir):
        from core.agenda_cmds import run_ms_add, run_ms_drop
        run_ms_add("test-project", "Old milestone")
        run_ms_drop("test-project", "Old milestone", force=True)
        log = _logbook_text(proj)
        assert "[cancelado] Hito: Old milestone" in log

    def test_drop_recurring_creates_next(self, proj, projects_dir, capsys):
        from core.agenda_cmds import run_ms_add, run_ms_drop, _read_agenda
        run_ms_add("test-project", "Monthly review", date_val="2026-03-01", recur="monthly")
        rc = run_ms_drop("test-project", "Monthly review", force=True)
        assert rc == 0
        data = _read_agenda(proj / "test-project-agenda.md")
        assert data["milestones"][0]["status"] == "cancelled"
        pending = [m for m in data["milestones"] if m["status"] == "pending"]
        assert len(pending) == 1
        assert pending[0]["date"] == "2026-04-01"
        assert pending[0]["recur"] == "monthly"
        out = capsys.readouterr().out
        assert "próxima: 2026-04-01" in out

    def test_edit_text(self, proj, projects_dir):
        from core.agenda_cmds import run_ms_add, run_ms_edit, _read_agenda
        run_ms_add("test-project", "Old name")
        run_ms_edit("test-project", "Old name", new_text="New name")
        data = _read_agenda(proj / "test-project-agenda.md")
        assert data["milestones"][0]["desc"] == "New name"

    def test_edit_date_none(self, proj, projects_dir):
        from core.agenda_cmds import run_ms_add, run_ms_edit, _read_agenda
        run_ms_add("test-project", "MS", date_val="2026-06-01")
        run_ms_edit("test-project", "MS", new_date="none")
        data = _read_agenda(proj / "test-project-agenda.md")
        assert data["milestones"][0]["date"] is None

    def test_list_milestones(self, proj, projects_dir, capsys):
        from core.agenda_cmds import run_ms_add, run_ms_list
        run_ms_add("test-project", "Big goal")
        rc = run_ms_list()
        assert rc == 0
        assert "Big goal" in capsys.readouterr().out

    def test_list_no_results(self, proj, projects_dir, capsys):
        from core.agenda_cmds import run_ms_list
        rc = run_ms_list()
        assert rc == 0
        assert "No hay hitos" in capsys.readouterr().out

    def test_list_done_filter(self, proj, projects_dir, capsys):
        from core.agenda_cmds import run_ms_add, run_ms_done, run_ms_list
        run_ms_add("test-project", "Completed MS")
        run_ms_done("test-project", "Completed")
        run_ms_list(status_filter="done")
        assert "Completed MS" in capsys.readouterr().out


# ══════════════════════════════════════════════════════════════════════════════
# run_ev_add / run_ev_drop / run_ev_list
# ══════════════════════════════════════════════════════════════════════════════

class TestEvents:
    def test_add_event(self, proj, projects_dir, capsys):
        from core.agenda_cmds import run_ev_add, _read_agenda
        rc = run_ev_add("test-project", "Conference", "2026-05-10")
        assert rc == 0
        data = _read_agenda(proj / "test-project-agenda.md")
        assert data["events"][0]["date"] == "2026-05-10"
        assert data["events"][0]["desc"] == "Conference"

    def test_add_event_with_end(self, proj, projects_dir):
        from core.agenda_cmds import run_ev_add, _read_agenda
        run_ev_add("test-project", "Summer school", "2026-07-01", end_date="2026-07-05")
        data = _read_agenda(proj / "test-project-agenda.md")
        assert data["events"][0]["end"] == "2026-07-05"

    def test_invalid_date(self, proj, projects_dir, capsys):
        from core.agenda_cmds import run_ev_add
        rc = run_ev_add("test-project", "Bad event", "not-a-date")
        assert rc == 1
        assert "no reconocida" in capsys.readouterr().out

    def test_drop_event_by_text(self, proj, projects_dir, capsys):
        from core.agenda_cmds import run_ev_add, run_ev_drop, _read_agenda
        run_ev_add("test-project", "Meeting", "2026-03-20")
        rc = run_ev_drop("test-project", "Meeting", force=True)
        assert rc == 0
        data = _read_agenda(proj / "test-project-agenda.md")
        assert data["events"] == []

    def test_drop_recurring_creates_next(self, proj, projects_dir, capsys):
        from core.agenda_cmds import run_ev_add, run_ev_drop, _read_agenda
        run_ev_add("test-project", "Weekly standup", "2026-03-09", recur="weekly")
        rc = run_ev_drop("test-project", "Weekly standup", force=True)
        assert rc == 0
        data = _read_agenda(proj / "test-project-agenda.md")
        assert len(data["events"]) == 1
        assert data["events"][0]["date"] == "2026-03-16"
        assert data["events"][0]["recur"] == "weekly"
        out = capsys.readouterr().out
        assert "próxima: 2026-03-16" in out

    def test_drop_recurring_event_clears_orbit_id(self, proj, projects_dir):
        """Advancing a recurring event creates a fresh occurrence — the
        orbit-id of the previous anchor must NOT carry over (the new
        occurrence is a different identity for sync purposes)."""
        from core.agenda_cmds import run_ev_add, run_ev_drop, _read_agenda
        run_ev_add("test-project", "Synced meeting", "2026-03-09", recur="weekly")
        # Manually mark with an orbit-id (as if it had been synced).
        data = _read_agenda(proj / "test-project-agenda.md")
        data["events"][0]["orbit_id"] = "abc12345"
        from core.agenda_cmds import _write_agenda
        _write_agenda(proj / "test-project-agenda.md", data)
        run_ev_drop("test-project", "Synced meeting", force=True)
        data = _read_agenda(proj / "test-project-agenda.md")
        assert len(data["events"]) == 1
        assert not data["events"][0].get("orbit_id")

    def test_drop_nonexistent(self, proj, projects_dir, capsys):
        from core.agenda_cmds import run_ev_drop
        rc = run_ev_drop("test-project", "Ghost event", force=True)
        assert rc == 1
        assert "no se encontró" in capsys.readouterr().out

    def test_list_events(self, proj, projects_dir, capsys):
        from core.agenda_cmds import run_ev_add, run_ev_list
        run_ev_add("test-project", "Workshop", "2026-04-15")
        rc = run_ev_list()
        assert rc == 0
        assert "Workshop" in capsys.readouterr().out

    def test_list_with_period_filter(self, proj, projects_dir, capsys):
        from core.agenda_cmds import run_ev_add, run_ev_list
        run_ev_add("test-project", "March event",   "2026-03-10")
        run_ev_add("test-project", "June event",    "2026-06-01")
        run_ev_add("test-project", "October event", "2026-10-01")
        capsys.readouterr()  # discard add output
        run_ev_list(period_from="2026-04-01", period_to="2026-07-31")
        out = capsys.readouterr().out
        assert "June event"    in out
        assert "March event"   not in out
        assert "October event" not in out

    def test_list_empty(self, proj, projects_dir, capsys):
        from core.agenda_cmds import run_ev_list
        rc = run_ev_list()
        assert rc == 0
        assert "No hay eventos" in capsys.readouterr().out

    def test_list_specific_project(self, proj, projects_dir, capsys):
        from core.agenda_cmds import run_ev_add, run_ev_list
        run_ev_add("test-project", "Team meeting", "2026-04-01")
        run_ev_list(project="test-project")
        assert "Team meeting" in capsys.readouterr().out

    def test_events_sorted_in_list(self, proj, projects_dir, capsys):
        from core.agenda_cmds import run_ev_add, run_ev_list
        run_ev_add("test-project", "Later",   "2026-06-01")
        run_ev_add("test-project", "Earlier", "2026-03-01")
        capsys.readouterr()  # discard add output
        run_ev_list()
        out = capsys.readouterr().out
        assert out.index("Earlier") < out.index("Later")


# ══════════════════════════════════════════════════════════════════════════════
# --dated flag
# ══════════════════════════════════════════════════════════════════════════════

class TestDatedFlag:
    def test_task_list_dated_excludes_undated(self, proj, projects_dir, capsys):
        from core.agenda_cmds import run_task_add, run_task_list
        run_task_add("test-project", "With date", date_val="2026-05-01")
        run_task_add("test-project", "Without date")
        capsys.readouterr()
        run_task_list(dated_only=True)
        out = capsys.readouterr().out
        assert "With date" in out
        assert "Without date" not in out

    def test_task_list_default_shows_undated(self, proj, projects_dir, capsys):
        from core.agenda_cmds import run_task_add, run_task_list
        run_task_add("test-project", "With date", date_val="2026-05-01")
        run_task_add("test-project", "Without date")
        capsys.readouterr()
        run_task_list()
        out = capsys.readouterr().out
        assert "With date" in out
        assert "Without date" in out

    def test_ms_list_dated_excludes_undated(self, proj, projects_dir, capsys):
        from core.agenda_cmds import run_ms_add, run_ms_list
        run_ms_add("test-project", "Dated milestone", date_val="2026-06-01")
        run_ms_add("test-project", "Undated milestone")
        capsys.readouterr()
        run_ms_list(dated_only=True)
        out = capsys.readouterr().out
        assert "Dated milestone" in out
        assert "Undated milestone" not in out

    def test_ms_list_default_shows_undated(self, proj, projects_dir, capsys):
        from core.agenda_cmds import run_ms_add, run_ms_list
        run_ms_add("test-project", "Dated milestone", date_val="2026-06-01")
        run_ms_add("test-project", "Undated milestone")
        capsys.readouterr()
        run_ms_list()
        out = capsys.readouterr().out
        assert "Dated milestone" in out
        assert "Undated milestone" in out

    def test_agenda_dated_excludes_undated(self, proj, projects_dir, capsys):
        from core.agenda_cmds import run_task_add, run_ms_add
        import core.agenda_view as av
        # ORBIT_HOME already patched via projects_dir fixture
        run_task_add("test-project", "Dated task", date_val="2026-03-10")
        run_task_add("test-project", "Undated task")
        capsys.readouterr()
        av.run_agenda(date_str="2026-03-10", dated_only=True, no_cal=True)
        out = capsys.readouterr().out
        assert "Dated task" in out
        assert "Undated task" not in out

    def test_agenda_default_shows_undated(self, proj, projects_dir, capsys):
        from datetime import date as _date
        from core.agenda_cmds import run_task_add
        import core.agenda_view as av
        # ORBIT_HOME already patched via projects_dir fixture
        today = _date.today().isoformat()
        run_task_add("test-project", "Dated task", date_val=today)
        run_task_add("test-project", "Undated task")
        capsys.readouterr()
        av.run_agenda(date_str=today, dated_only=False, no_cal=True)
        out = capsys.readouterr().out
        assert "Dated task" in out
        assert "Undated task" in out


# ══════════════════════════════════════════════════════════════════════════════
# Event time field
# ══════════════════════════════════════════════════════════════════════════════

class TestEventTime:

    def test_valid_time_hhmm(self):
        from core.agenda_cmds import _valid_time
        assert _valid_time("10:00")
        assert _valid_time("09:30")
        assert _valid_time("23:59")

    def test_valid_time_range(self):
        from core.agenda_cmds import _valid_time
        assert _valid_time("10:00-12:30")
        assert _valid_time("09:00-17:00")

    def test_invalid_time(self):
        from core.agenda_cmds import _valid_time
        assert not _valid_time("25:00")
        assert not _valid_time("10")
        assert not _valid_time("10:00-")
        assert not _valid_time("abc")
        assert not _valid_time("10:60")

    def test_parse_event_with_time(self):
        from core.agenda_cmds import _parse_event_line
        e = _parse_event_line("2026-03-15 — Meeting [time:10:00-11:30]")
        assert e["time"] == "10:00-11:30"
        assert e["desc"] == "Meeting"

    def test_parse_event_time_only_start(self):
        from core.agenda_cmds import _parse_event_line
        e = _parse_event_line("2026-03-25 — Dentist [time:16:00]")
        assert e["time"] == "16:00"

    def test_parse_event_no_time(self):
        from core.agenda_cmds import _parse_event_line
        e = _parse_event_line("2026-03-15 — All day event")
        assert e["time"] is None

    def test_format_event_with_time(self):
        from core.agenda_cmds import _format_event_line
        ev = {"date": "2026-03-15", "desc": "Meeting", "end": None,
              "time": "10:00-11:30", "recur": None, "until": None,
              "ring": None}
        line = _format_event_line(ev)
        assert "⏰10:00-11:30" in line

    def test_format_event_without_time(self):
        from core.agenda_cmds import _format_event_line
        ev = {"date": "2026-03-15", "desc": "All day", "end": None,
              "time": None, "recur": None, "until": None,
              "ring": None}
        line = _format_event_line(ev)
        assert "⏰" not in line

    def test_roundtrip_event_with_time(self):
        from core.agenda_cmds import _parse_event_line, _format_event_line
        line = "2026-03-15 — Team meeting [time:10:00-11:30] [recur:weekly]"
        ev = _parse_event_line(line)
        assert ev["time"] == "10:00-11:30"
        assert ev["recur"] == "weekly"
        formatted = _format_event_line(ev)
        assert "⏰10:00-11:30" in formatted
        assert "🔄weekly" in formatted

    def test_roundtrip_all_fields(self):
        from core.agenda_cmds import _parse_event_line, _format_event_line
        line = "2026-03-15 — Conference [end:2026-03-17] [time:09:00] [recur:monthly] [ring:1d] [G]"
        ev = _parse_event_line(line)
        assert ev["time"] == "09:00"
        assert ev["end"] == "2026-03-17"
        assert ev["recur"] == "monthly"
        assert ev["ring"] == "1d"
        # Legacy [G] marker is stripped silently — no longer surfaced as a field.
        assert "synced" not in ev
        formatted = _format_event_line(ev)
        assert "⏰09:00" in formatted
        assert "→2026-03-17" in formatted

    def test_add_event_with_time(self, proj, projects_dir, capsys):
        from core.agenda_cmds import run_ev_add, _read_agenda
        rc = run_ev_add("test-project", "Standup", "2026-03-15",
                        time_val="09:00-09:30")
        assert rc == 0
        data = _read_agenda(proj / "test-project-agenda.md")
        assert data["events"][0]["time"] == "09:00-09:30"

    def test_add_event_invalid_time(self, proj, projects_dir, capsys):
        from core.agenda_cmds import run_ev_add
        rc = run_ev_add("test-project", "Bad", "2026-03-15", time_val="25:00")
        assert rc == 1
        assert "no válida" in capsys.readouterr().out

    def test_add_event_without_time(self, proj, projects_dir):
        from core.agenda_cmds import run_ev_add, _read_agenda
        run_ev_add("test-project", "All day", "2026-03-15")
        data = _read_agenda(proj / "test-project-agenda.md")
        assert data["events"][0]["time"] is None

    def test_write_read_roundtrip_with_time(self, proj, projects_dir):
        from core.agenda_cmds import run_ev_add, _read_agenda
        run_ev_add("test-project", "Meeting", "2026-03-15",
                   time_val="14:00-15:30")
        data = _read_agenda(proj / "test-project-agenda.md")
        assert data["events"][0]["time"] == "14:00-15:30"
        assert data["events"][0]["desc"] == "Meeting"

    def test_edit_event_text(self, proj, projects_dir):
        from core.agenda_cmds import run_ev_add, run_ev_edit, _read_agenda
        run_ev_add("test-project", "Old meeting", "2026-03-15")
        rc = run_ev_edit("test-project", "Old meeting", new_text="New meeting")
        assert rc == 0
        data = _read_agenda(proj / "test-project-agenda.md")
        assert data["events"][0]["desc"] == "New meeting"

    def test_edit_event_add_time(self, proj, projects_dir):
        from core.agenda_cmds import run_ev_add, run_ev_edit, _read_agenda
        run_ev_add("test-project", "Meeting", "2026-03-15")
        data = _read_agenda(proj / "test-project-agenda.md")
        assert data["events"][0]["time"] is None
        run_ev_edit("test-project", "Meeting", new_time="10:00-11:00")
        data = _read_agenda(proj / "test-project-agenda.md")
        assert data["events"][0]["time"] == "10:00-11:00"

    def test_edit_event_remove_time(self, proj, projects_dir):
        from core.agenda_cmds import run_ev_add, run_ev_edit, _read_agenda
        run_ev_add("test-project", "Meeting", "2026-03-15", time_val="10:00")
        run_ev_edit("test-project", "Meeting", new_time="none")
        data = _read_agenda(proj / "test-project-agenda.md")
        assert data["events"][0]["time"] is None

    def test_edit_event_invalid_time(self, proj, projects_dir, capsys):
        from core.agenda_cmds import run_ev_add, run_ev_edit
        run_ev_add("test-project", "Meeting", "2026-03-15")
        rc = run_ev_edit("test-project", "Meeting", new_time="25:00")
        assert rc == 1
        assert "no válida" in capsys.readouterr().out


# ══════════════════════════════════════════════════════════════════════════════
# Event recurrence in agenda view
# ══════════════════════════════════════════════════════════════════════════════

class TestEventRecurrence:

    def test_recurring_event_expands_in_agenda(self, proj, projects_dir, capsys):
        from core.agenda_cmds import run_ev_add
        import core.agenda_view as av
        # ORBIT_HOME already patched via projects_dir fixture
        run_ev_add("test-project", "Weekly sync", "2026-03-10",
                   recur="weekly")
        capsys.readouterr()
        av.run_agenda(date_from="2026-03-10", date_to="2026-03-31")
        out = capsys.readouterr().out
        # Should appear multiple times (original + virtual occurrences)
        assert out.count("Weekly sync") >= 3  # Mar 10, 17, 24, 31

    def test_recurring_event_in_calendar(self, proj, projects_dir, capsys):
        from core.agenda_cmds import run_ev_add
        import core.agenda_view as av
        # ORBIT_HOME already patched via projects_dir fixture
        run_ev_add("test-project", "Monthly review", "2026-03-15",
                   recur="monthly")
        capsys.readouterr()
        av.run_agenda(date_from="2026-03-01", date_to="2026-05-31")
        out = capsys.readouterr().out
        # Should appear in detail section multiple times
        assert out.count("Monthly review") >= 3  # Mar, Apr, May

    def test_recurring_event_with_time_in_agenda(self, proj, projects_dir, capsys):
        from core.agenda_cmds import run_ev_add
        import core.agenda_view as av
        # ORBIT_HOME already patched via projects_dir fixture
        run_ev_add("test-project", "Standup", "2026-03-10",
                   time_val="09:00-09:30", recur="weekly")
        capsys.readouterr()
        av.run_agenda(date_from="2026-03-10", date_to="2026-03-24")
        out = capsys.readouterr().out
        assert "09:00-09:30" in out
        assert out.count("Standup") >= 2

    def test_recurring_multiday_event_preserves_duration(self):
        from datetime import date
        from core.agenda_view import _expand_recurrences
        ev = {"date": "2026-03-10", "end": "2026-03-12", "desc": "Conf",
              "recur": "monthly", "until": None}
        results = _expand_recurrences(ev, date(2026, 4, 1), date(2026, 5, 31))
        assert len(results) == 2  # Apr and May
        # Duration preserved: 2 days
        for r in results:
            start = date.fromisoformat(r["date"])
            end = date.fromisoformat(r["end"])
            assert (end - start).days == 2

    def test_agenda_dated_with_calendar(self, proj, projects_dir, capsys):
        """--dated with --calendar should exclude undated tasks."""
        from core.agenda_cmds import run_task_add
        import core.agenda_view as av
        # ORBIT_HOME already patched via projects_dir fixture
        run_task_add("test-project", "Dated task", date_val="2026-03-15")
        run_task_add("test-project", "Undated task")
        capsys.readouterr()
        av.run_agenda(date_str="2026-03", dated_only=True)
        out = capsys.readouterr().out
        assert "Dated task" in out
        assert "Undated task" not in out


# ══════════════════════════════════════════════════════════════════════════════
# drop -o / -s flags for task, ms, ev
# ══════════════════════════════════════════════════════════════════════════════

class TestDropOccurrenceSeriesTask:
    def test_drop_o_advances_recurring(self, proj, projects_dir, capsys):
        from core.agenda_cmds import run_task_add, run_task_drop, _read_agenda
        run_task_add("test-project", "Weekly sync", date_val="2026-03-09", recur="weekly")
        rc = run_task_drop("test-project", "Weekly sync", occurrence=True)
        assert rc == 0
        data = _read_agenda(proj / "test-project-agenda.md")
        pending = [t for t in data["tasks"] if t["status"] == "pending"]
        assert len(pending) == 1
        assert pending[0]["date"] > "2026-03-09"
        assert pending[0]["recur"] == "weekly"

    def test_drop_s_removes_series(self, proj, projects_dir, capsys):
        from core.agenda_cmds import run_task_add, run_task_drop, _read_agenda
        run_task_add("test-project", "Weekly sync", date_val="2026-03-09", recur="weekly")
        rc = run_task_drop("test-project", "Weekly sync", series=True)
        assert rc == 0
        data = _read_agenda(proj / "test-project-agenda.md")
        pending = [t for t in data["tasks"] if t["status"] == "pending"]
        assert len(pending) == 0
        out = capsys.readouterr().out
        assert "serie cancelada" in out

    def test_drop_o_nonrecurring_still_works(self, proj, projects_dir):
        """'-o' on a non-recurring task should just cancel it (no crash)."""
        from core.agenda_cmds import run_task_add, run_task_drop, _read_agenda
        run_task_add("test-project", "One-off", date_val="2026-03-09")
        rc = run_task_drop("test-project", "One-off", occurrence=True)
        assert rc == 0
        data = _read_agenda(proj / "test-project-agenda.md")
        assert data["tasks"][0]["status"] == "cancelled"


class TestDropOccurrenceSeriesMs:
    def test_drop_o_advances_recurring(self, proj, projects_dir, capsys):
        from core.agenda_cmds import run_ms_add, run_ms_drop, _read_agenda
        run_ms_add("test-project", "Monthly review", date_val="2026-03-01", recur="monthly")
        rc = run_ms_drop("test-project", "Monthly review", occurrence=True)
        assert rc == 0
        data = _read_agenda(proj / "test-project-agenda.md")
        pending = [m for m in data["milestones"] if m["status"] == "pending"]
        assert len(pending) == 1
        assert pending[0]["date"] == "2026-04-01"

    def test_drop_s_removes_series(self, proj, projects_dir, capsys):
        from core.agenda_cmds import run_ms_add, run_ms_drop, _read_agenda
        run_ms_add("test-project", "Monthly review", date_val="2026-03-01", recur="monthly")
        rc = run_ms_drop("test-project", "Monthly review", series=True)
        assert rc == 0
        data = _read_agenda(proj / "test-project-agenda.md")
        pending = [m for m in data["milestones"] if m["status"] == "pending"]
        assert len(pending) == 0
        out = capsys.readouterr().out
        assert "serie cancelada" in out


class TestDropOccurrenceSeriesEv:
    def test_drop_o_advances_recurring(self, proj, projects_dir, capsys):
        from core.agenda_cmds import run_ev_add, run_ev_drop, _read_agenda
        run_ev_add("test-project", "Weekly standup", "2026-03-09", recur="weekly")
        rc = run_ev_drop("test-project", "Weekly standup", occurrence=True)
        assert rc == 0
        data = _read_agenda(proj / "test-project-agenda.md")
        assert len(data["events"]) == 1
        assert data["events"][0]["date"] == "2026-03-16"

    def test_drop_s_removes_series(self, proj, projects_dir, capsys):
        from core.agenda_cmds import run_ev_add, run_ev_drop, _read_agenda
        run_ev_add("test-project", "Weekly standup", "2026-03-09", recur="weekly")
        rc = run_ev_drop("test-project", "Weekly standup", series=True)
        assert rc == 0
        data = _read_agenda(proj / "test-project-agenda.md")
        assert data["events"] == []
        out = capsys.readouterr().out
        assert "Serie eliminada" in out


class TestDropOccurrenceSeriesReminder:
    def test_drop_o_advances_recurring(self, proj, projects_dir, capsys):
        from core.agenda_cmds import run_reminder_add, run_reminder_drop, _read_agenda
        run_reminder_add("test-project", "Daily standup", date_val="2026-03-09",
                         time_val="09:00", recur="daily")
        rc = run_reminder_drop("test-project", "standup", occurrence=True)
        assert rc == 0
        data = _read_agenda(proj / "test-project-agenda.md")
        active = [r for r in data["reminders"] if not r.get("cancelled")]
        assert len(active) == 1
        assert active[0]["date"] > "2026-03-09"
        assert active[0]["recur"] == "daily"
        out = capsys.readouterr().out
        assert "avanzado" in out

    def test_drop_s_cancels_series(self, proj, projects_dir, capsys):
        from core.agenda_cmds import run_reminder_add, run_reminder_drop, _read_agenda
        run_reminder_add("test-project", "Daily standup", date_val="2026-03-09",
                         time_val="09:00", recur="daily")
        rc = run_reminder_drop("test-project", "standup", series=True)
        assert rc == 0
        data = _read_agenda(proj / "test-project-agenda.md")
        active = [r for r in data["reminders"] if not r.get("cancelled")]
        assert len(active) == 0
        out = capsys.readouterr().out
        assert "Serie eliminada" in out

    def test_drop_nonrecurring(self, proj, projects_dir, capsys):
        from core.agenda_cmds import run_reminder_add, run_reminder_drop, _read_agenda
        run_reminder_add("test-project", "One-off reminder", date_val="2026-03-20",
                         time_val="17:00")
        rc = run_reminder_drop("test-project", "One-off", force=True)
        assert rc == 0
        data = _read_agenda(proj / "test-project-agenda.md")
        active = [r for r in data["reminders"] if not r.get("cancelled")]
        assert len(active) == 0

    def test_drop_requires_force_in_noninteractive(self, proj, projects_dir):
        from core.agenda_cmds import run_reminder_add, run_reminder_drop, _read_agenda
        run_reminder_add("test-project", "Keep me", date_val="2026-03-20",
                         time_val="10:00")
        rc = run_reminder_drop("test-project", "Keep me")
        assert rc == 1
        data = _read_agenda(proj / "test-project-agenda.md")
        active = [r for r in data["reminders"] if not r.get("cancelled")]
        assert len(active) == 1


# ══════════════════════════════════════════════════════════════════════════════
# Edit occurrence vs series — recurring items
# ══════════════════════════════════════════════════════════════════════════════

class TestEditOccurrenceSeriesTask:
    def test_edit_o_creates_occurrence_and_advances(self, proj, projects_dir, capsys):
        from core.agenda_cmds import run_task_add, run_task_edit, _read_agenda
        run_task_add("test-project", "Weekly sync", date_val="2026-03-09", recur="weekly")
        rc = run_task_edit("test-project", "Weekly sync", new_text="Edited sync", occurrence=True)
        assert rc == 0
        data = _read_agenda(proj / "test-project-agenda.md")
        pending = [t for t in data["tasks"] if t["status"] == "pending"]
        assert len(pending) == 2
        recurring = [t for t in pending if t.get("recur")]
        assert len(recurring) == 1
        assert recurring[0]["date"] == "2026-03-16"
        assert recurring[0]["desc"] == "Weekly sync"
        one_off = [t for t in pending if not t.get("recur")]
        assert len(one_off) == 1
        assert one_off[0]["desc"] == "Edited sync"
        assert one_off[0]["date"] == "2026-03-09"
        out = capsys.readouterr().out
        assert "Ocurrencia editada" in out

    def test_edit_s_edits_series_in_place(self, proj, projects_dir, capsys):
        from core.agenda_cmds import run_task_add, run_task_edit, _read_agenda
        run_task_add("test-project", "Weekly sync", date_val="2026-03-09", recur="weekly")
        rc = run_task_edit("test-project", "Weekly sync", new_text="Renamed sync", series=True)
        assert rc == 0
        data = _read_agenda(proj / "test-project-agenda.md")
        pending = [t for t in data["tasks"] if t["status"] == "pending"]
        assert len(pending) == 1
        assert pending[0]["desc"] == "Renamed sync"
        assert pending[0]["recur"] == "weekly"
        assert pending[0]["date"] == "2026-03-09"

    def test_edit_force_defaults_to_occurrence(self, proj, projects_dir, capsys):
        from core.agenda_cmds import run_task_add, run_task_edit, _read_agenda
        run_task_add("test-project", "Weekly sync", date_val="2026-03-09", recur="weekly")
        rc = run_task_edit("test-project", "Weekly sync", new_text="Forced edit", force=True)
        assert rc == 0
        data = _read_agenda(proj / "test-project-agenda.md")
        pending = [t for t in data["tasks"] if t["status"] == "pending"]
        assert len(pending) == 2
        one_off = [t for t in pending if not t.get("recur")]
        assert one_off[0]["desc"] == "Forced edit"

    def test_edit_o_nonrecurring_edits_normally(self, proj, projects_dir, capsys):
        from core.agenda_cmds import run_task_add, run_task_edit, _read_agenda
        run_task_add("test-project", "One-off", date_val="2026-03-09")
        rc = run_task_edit("test-project", "One-off", new_text="Updated", occurrence=True)
        assert rc == 0
        data = _read_agenda(proj / "test-project-agenda.md")
        pending = [t for t in data["tasks"] if t["status"] == "pending"]
        assert len(pending) == 1
        assert pending[0]["desc"] == "Updated"

    def test_edit_o_respects_until(self, proj, projects_dir, capsys):
        from core.agenda_cmds import run_task_add, run_task_edit, _read_agenda
        run_task_add("test-project", "Weekly sync", date_val="2026-03-09",
                     recur="weekly", until="2026-03-15")
        rc = run_task_edit("test-project", "Weekly sync", new_text="Last one", occurrence=True)
        assert rc == 0
        data = _read_agenda(proj / "test-project-agenda.md")
        pending = [t for t in data["tasks"] if t["status"] == "pending"]
        assert len(pending) == 1
        assert pending[0]["desc"] == "Last one"
        assert not pending[0].get("recur")
        out = capsys.readouterr().out
        assert "serie finalizada" in out


class TestEditOccurrenceSeriesMs:
    def test_edit_o_creates_occurrence_and_advances(self, proj, projects_dir, capsys):
        from core.agenda_cmds import run_ms_add, run_ms_edit, _read_agenda
        run_ms_add("test-project", "Monthly review", date_val="2026-03-01", recur="monthly")
        rc = run_ms_edit("test-project", "Monthly review", new_text="Edited review", occurrence=True)
        assert rc == 0
        data = _read_agenda(proj / "test-project-agenda.md")
        pending = [m for m in data["milestones"] if m["status"] == "pending"]
        assert len(pending) == 2
        recurring = [m for m in pending if m.get("recur")]
        assert len(recurring) == 1
        assert recurring[0]["date"] == "2026-04-01"
        one_off = [m for m in pending if not m.get("recur")]
        assert len(one_off) == 1
        assert one_off[0]["desc"] == "Edited review"

    def test_edit_s_edits_series_in_place(self, proj, projects_dir, capsys):
        from core.agenda_cmds import run_ms_add, run_ms_edit, _read_agenda
        run_ms_add("test-project", "Monthly review", date_val="2026-03-01", recur="monthly")
        rc = run_ms_edit("test-project", "Monthly review", new_text="Renamed", series=True)
        assert rc == 0
        data = _read_agenda(proj / "test-project-agenda.md")
        pending = [m for m in data["milestones"] if m["status"] == "pending"]
        assert len(pending) == 1
        assert pending[0]["desc"] == "Renamed"
        assert pending[0]["recur"] == "monthly"


class TestEditOccurrenceSeriesEv:
    def test_edit_o_creates_occurrence_and_advances(self, proj, projects_dir, capsys):
        from core.agenda_cmds import run_ev_add, run_ev_edit, _read_agenda
        run_ev_add("test-project", "Weekly standup", "2026-03-09", recur="weekly")
        rc = run_ev_edit("test-project", "Weekly standup", new_text="Edited standup", occurrence=True)
        assert rc == 0
        data = _read_agenda(proj / "test-project-agenda.md")
        assert len(data["events"]) == 2
        recurring = [e for e in data["events"] if e.get("recur")]
        assert len(recurring) == 1
        assert recurring[0]["date"] == "2026-03-16"
        one_off = [e for e in data["events"] if not e.get("recur")]
        assert len(one_off) == 1
        assert one_off[0]["desc"] == "Edited standup"
        assert one_off[0]["date"] == "2026-03-09"

    def test_edit_s_edits_series_in_place(self, proj, projects_dir, capsys):
        from core.agenda_cmds import run_ev_add, run_ev_edit, _read_agenda
        run_ev_add("test-project", "Weekly standup", "2026-03-09", recur="weekly")
        rc = run_ev_edit("test-project", "Weekly standup", new_text="Renamed", series=True)
        assert rc == 0
        data = _read_agenda(proj / "test-project-agenda.md")
        assert len(data["events"]) == 1
        assert data["events"][0]["desc"] == "Renamed"
        assert data["events"][0]["recur"] == "weekly"
        assert data["events"][0]["date"] == "2026-03-09"

    def test_edit_o_with_recur_none_edits_in_place(self, proj, projects_dir, capsys):
        """--recur none bypasses occurrence/series logic."""
        from core.agenda_cmds import run_ev_add, run_ev_edit, _read_agenda
        run_ev_add("test-project", "Weekly standup", "2026-03-09", recur="weekly")
        rc = run_ev_edit("test-project", "Weekly standup", new_recur="none", occurrence=True)
        assert rc == 0
        data = _read_agenda(proj / "test-project-agenda.md")
        assert len(data["events"]) == 1
        assert data["events"][0].get("recur") is None


class TestEditOccurrenceSeriesReminder:
    def test_edit_o_creates_occurrence_and_advances(self, proj, projects_dir, capsys):
        from core.agenda_cmds import run_reminder_add, run_reminder_edit, _read_agenda
        run_reminder_add("test-project", "Daily standup", date_val="2026-03-09",
                         time_val="09:00", recur="daily")
        rc = run_reminder_edit("test-project", "standup", new_text="Edited standup", occurrence=True)
        assert rc == 0
        data = _read_agenda(proj / "test-project-agenda.md")
        active = [r for r in data["reminders"] if not r.get("cancelled")]
        assert len(active) == 2
        recurring = [r for r in active if r.get("recur")]
        assert len(recurring) == 1
        assert recurring[0]["date"] == "2026-03-10"
        one_off = [r for r in active if not r.get("recur")]
        assert len(one_off) == 1
        assert one_off[0]["desc"] == "Edited standup"

    def test_edit_s_edits_series_in_place(self, proj, projects_dir, capsys):
        from core.agenda_cmds import run_reminder_add, run_reminder_edit, _read_agenda
        run_reminder_add("test-project", "Daily standup", date_val="2026-03-09",
                         time_val="09:00", recur="daily")
        rc = run_reminder_edit("test-project", "standup", new_text="Renamed", series=True)
        assert rc == 0
        data = _read_agenda(proj / "test-project-agenda.md")
        active = [r for r in data["reminders"] if not r.get("cancelled")]
        assert len(active) == 1
        assert active[0]["desc"] == "Renamed"
        assert active[0]["recur"] == "daily"


# ══════════════════════════════════════════════════════════════════════════════
# Ambiguous match — interactive disambiguation
# ══════════════════════════════════════════════════════════════════════════════

class TestAmbiguousSelectTask:
    def test_ambiguous_lists_and_selects(self, proj, projects_dir, monkeypatch, capsys):
        """When text matches multiple tasks, show list and let user pick."""
        from core.agenda_cmds import run_task_add, run_task_drop, _read_agenda
        run_task_add("test-project", "Reunión semanal", date_val="2026-03-10", recur="weekly")
        run_task_add("test-project", "Reunión mensual", date_val="2026-04-01", recur="monthly")
        # Simulate user picking option 2
        monkeypatch.setattr("sys.stdin", type("FakeTTY", (), {
            "isatty": lambda self: True,
            "readline": lambda self: "2\n",
        })())
        monkeypatch.setattr("builtins.input", lambda prompt: "2")
        rc = run_task_drop("test-project", "Reunión", occurrence=True)
        assert rc == 0
        data = _read_agenda(proj / "test-project-agenda.md")
        out = capsys.readouterr().out
        assert "Múltiples coincidencias" in out
        # "Reunión mensual" (option 2) should have been advanced
        pending = [t for t in data["tasks"] if t["status"] == "pending"]
        descs = [t["desc"] for t in pending]
        assert "Reunión semanal" in descs  # untouched
        assert "Reunión mensual" in descs  # advanced (new occurrence)

    def test_ambiguous_noninteractive_returns_none(self, proj, projects_dir, capsys):
        """In non-interactive mode, ambiguous match should fail gracefully."""
        from core.agenda_cmds import run_task_add, run_task_drop
        run_task_add("test-project", "Reunión semanal", date_val="2026-03-10")
        run_task_add("test-project", "Reunión mensual", date_val="2026-04-01")
        rc = run_task_drop("test-project", "Reunión", force=True)
        assert rc == 1  # can't select in non-tty
        out = capsys.readouterr().out
        assert "Múltiples coincidencias" in out


class TestAmbiguousSelectMs:
    def test_ambiguous_lists_and_selects(self, proj, projects_dir, monkeypatch, capsys):
        from core.agenda_cmds import run_ms_add, run_ms_drop, _read_agenda
        run_ms_add("test-project", "Revisión semanal", date_val="2026-03-10", recur="weekly")
        run_ms_add("test-project", "Revisión mensual", date_val="2026-04-01", recur="monthly")
        monkeypatch.setattr("sys.stdin", type("FakeTTY", (), {
            "isatty": lambda self: True,
        })())
        monkeypatch.setattr("builtins.input", lambda prompt: "2")
        rc = run_ms_drop("test-project", "Revisión", occurrence=True)
        assert rc == 0
        data = _read_agenda(proj / "test-project-agenda.md")
        out = capsys.readouterr().out
        assert "Múltiples coincidencias" in out
        pending = [m for m in data["milestones"] if m["status"] == "pending"]
        descs = [m["desc"] for m in pending]
        assert "Revisión semanal" in descs  # untouched
        assert "Revisión mensual" in descs  # advanced (new occurrence)
        mensual = [m for m in pending if m["desc"] == "Revisión mensual"][0]
        assert mensual["date"] > "2026-04-01"

    def test_ambiguous_noninteractive_returns_none(self, proj, projects_dir, capsys):
        from core.agenda_cmds import run_ms_add, run_ms_drop
        run_ms_add("test-project", "Revisión semanal", date_val="2026-03-10")
        run_ms_add("test-project", "Revisión mensual", date_val="2026-04-01")
        rc = run_ms_drop("test-project", "Revisión", force=True)
        assert rc == 1
        out = capsys.readouterr().out
        assert "Múltiples coincidencias" in out


class TestAmbiguousSelectEvent:
    def test_ambiguous_lists_and_selects(self, proj, projects_dir, monkeypatch, capsys):
        from core.agenda_cmds import run_ev_add, run_ev_drop, _read_agenda
        run_ev_add("test-project", "Reunión semanal", "2026-03-10", recur="weekly")
        run_ev_add("test-project", "Reunión mensual", "2026-04-01", recur="monthly")
        monkeypatch.setattr("sys.stdin", type("FakeTTY", (), {
            "isatty": lambda self: True,
        })())
        monkeypatch.setattr("builtins.input", lambda prompt: "1")
        rc = run_ev_drop("test-project", "Reunión", occurrence=True)
        assert rc == 0
        data = _read_agenda(proj / "test-project-agenda.md")
        out = capsys.readouterr().out
        assert "Múltiples coincidencias" in out
        # First event (semanal) should have been advanced
        descs = [e["desc"] for e in data["events"]]
        assert "Reunión semanal" in descs
        assert "Reunión mensual" in descs
        semanal = [e for e in data["events"] if e["desc"] == "Reunión semanal"][0]
        assert semanal["date"] > "2026-03-10"


class TestAmbiguousSelectReminder:
    def test_ambiguous_lists_and_selects(self, proj, projects_dir, monkeypatch, capsys):
        from core.agenda_cmds import run_reminder_add, run_reminder_drop, _read_agenda
        run_reminder_add("test-project", "Llamar a Juan", date_val="2026-03-20", time_val="10:00")
        run_reminder_add("test-project", "Llamar a Pedro", date_val="2026-03-21", time_val="11:00")
        monkeypatch.setattr("sys.stdin", type("FakeTTY", (), {
            "isatty": lambda self: True,
        })())
        monkeypatch.setattr("builtins.input", lambda prompt: "2")
        rc = run_reminder_drop("test-project", "Llamar", force=True)
        assert rc == 0
        data = _read_agenda(proj / "test-project-agenda.md")
        out = capsys.readouterr().out
        assert "Múltiples coincidencias" in out
        active = [r for r in data["reminders"] if not r.get("cancelled")]
        assert len(active) == 1
        assert active[0]["desc"] == "Llamar a Juan"  # Pedro (option 2) was dropped


# ══════════════════════════════════════════════════════════════════════════════
# run_reminder_edit
# ══════════════════════════════════════════════════════════════════════════════

class TestReminderEdit:
    def test_edit_text(self, proj, projects_dir, capsys):
        from core.agenda_cmds import run_reminder_add, run_reminder_edit, _read_agenda
        run_reminder_add("test-project", "Old title", date_val="2026-03-20",
                         time_val="10:00")
        rc = run_reminder_edit("test-project", "Old title", new_text="New title")
        assert rc == 0
        data = _read_agenda(proj / "test-project-agenda.md")
        assert data["reminders"][0]["desc"] == "New title"
        out = capsys.readouterr().out
        assert "actualizado" in out

    def test_edit_date(self, proj, projects_dir):
        from core.agenda_cmds import run_reminder_add, run_reminder_edit, _read_agenda
        run_reminder_add("test-project", "Move me", date_val="2026-03-20",
                         time_val="10:00")
        run_reminder_edit("test-project", "Move me", new_date="2026-04-01")
        data = _read_agenda(proj / "test-project-agenda.md")
        assert data["reminders"][0]["date"] == "2026-04-01"

    def test_edit_time(self, proj, projects_dir):
        from core.agenda_cmds import run_reminder_add, run_reminder_edit, _read_agenda
        run_reminder_add("test-project", "Change time", date_val="2026-03-20",
                         time_val="10:00")
        run_reminder_edit("test-project", "Change time", new_time="15:00")
        data = _read_agenda(proj / "test-project-agenda.md")
        assert data["reminders"][0]["time"] == "15:00"

    def test_edit_recur(self, proj, projects_dir):
        from core.agenda_cmds import run_reminder_add, run_reminder_edit, _read_agenda
        run_reminder_add("test-project", "Make recur", date_val="2026-03-20",
                         time_val="10:00")
        run_reminder_edit("test-project", "Make recur", new_recur="weekly")
        data = _read_agenda(proj / "test-project-agenda.md")
        assert data["reminders"][0]["recur"] == "weekly"

    def test_edit_remove_recur(self, proj, projects_dir):
        from core.agenda_cmds import run_reminder_add, run_reminder_edit, _read_agenda
        run_reminder_add("test-project", "Stop recur", date_val="2026-03-20",
                         time_val="10:00", recur="daily")
        run_reminder_edit("test-project", "Stop recur", new_recur="none")
        data = _read_agenda(proj / "test-project-agenda.md")
        assert data["reminders"][0]["recur"] is None

    def test_edit_not_found(self, proj, projects_dir, capsys):
        from core.agenda_cmds import run_reminder_add, run_reminder_edit
        run_reminder_add("test-project", "Exists", date_val="2026-03-20",
                         time_val="10:00")
        rc = run_reminder_edit("test-project", "Ghost")
        assert rc == 1

    def test_edit_invalid_time(self, proj, projects_dir, capsys):
        from core.agenda_cmds import run_reminder_add, run_reminder_edit
        run_reminder_add("test-project", "Bad time", date_val="2026-03-20",
                         time_val="10:00")
        rc = run_reminder_edit("test-project", "Bad time", new_time="not-a-time")
        assert rc == 1
        assert "no válida" in capsys.readouterr().out


# ══════════════════════════════════════════════════════════════════════════════
# _validate_add_params
# ══════════════════════════════════════════════════════════════════════════════

class TestValidateAddParams:
    def test_valid_params(self):
        from core.agenda_cmds import _validate_add_params
        assert _validate_add_params("2026-03-20", "10:00", "weekly", None, "5m") is None

    def test_invalid_date(self):
        from core.agenda_cmds import _validate_add_params
        err = _validate_add_params("not-a-date", None, None, None, None)
        assert err and "Fecha" in err

    def test_invalid_recur(self):
        from core.agenda_cmds import _validate_add_params
        err = _validate_add_params("2026-03-20", None, "bogus", None, None)
        assert err and "Recurrencia" in err

    def test_until_without_recur(self):
        from core.agenda_cmds import _validate_add_params
        err = _validate_add_params("2026-03-20", None, None, "2026-04-01", None)
        assert err and "--until" in err

    def test_ring_without_date(self):
        from core.agenda_cmds import _validate_add_params
        err = _validate_add_params(None, None, None, None, "5m")
        assert err and "--ring" in err

    def test_invalid_ring(self):
        from core.agenda_cmds import _validate_add_params
        err = _validate_add_params("2026-03-20", None, None, None, "bogus")
        assert err and "Ring" in err

    def test_time_without_date(self):
        from core.agenda_cmds import _validate_add_params
        err = _validate_add_params(None, "10:00", None, None, None)
        assert err and "--time" in err

    def test_invalid_time_simple(self):
        from core.agenda_cmds import _validate_add_params
        err = _validate_add_params("2026-03-20", "bad", None, None, None)
        assert err and "Hora" in err

    def test_event_time_format(self):
        from core.agenda_cmds import _validate_add_params
        assert _validate_add_params("2026-03-20", "10:00-11:00", None, None, None,
                                    time_format="event") is None

    def test_invalid_event_time(self):
        from core.agenda_cmds import _validate_add_params
        err = _validate_add_params("2026-03-20", "bad", None, None, None,
                                   time_format="event")
        assert err and "Hora" in err


# ══════════════════════════════════════════════════════════════════════════════
# task log / ms log / ev log / reminder log
# ══════════════════════════════════════════════════════════════════════════════

class TestTaskLog:
    def test_creates_logbook_entry(self, proj, projects_dir, capsys):
        from core.agenda_cmds import run_task_add, run_task_log
        run_task_add("test-project", "Review paper", date_val="2026-03-10")
        rc = run_task_log("test-project", "Review")
        assert rc == 0
        log = _logbook_text(proj)
        assert "Review paper" in log
        assert "#apunte" in log

    def test_not_found(self, proj, projects_dir, capsys):
        from core.agenda_cmds import run_task_add, run_task_log
        run_task_add("test-project", "Exists")
        rc = run_task_log("test-project", "Ghost")
        assert rc == 1


class TestMsLog:
    def test_creates_logbook_entry(self, proj, projects_dir, capsys):
        from core.agenda_cmds import run_ms_add, run_ms_log
        run_ms_add("test-project", "Calibration done", date_val="2026-03-10")
        rc = run_ms_log("test-project", "Calibration")
        assert rc == 0
        log = _logbook_text(proj)
        assert "Calibration done" in log
        assert "#resultado" in log

    def test_not_found(self, proj, projects_dir, capsys):
        from core.agenda_cmds import run_ms_add, run_ms_log
        run_ms_add("test-project", "Exists")
        rc = run_ms_log("test-project", "Ghost")
        assert rc == 1


class TestEvLog:
    def test_creates_logbook_entry_plain(self, proj, projects_dir, capsys):
        from core.agenda_cmds import run_ev_add, run_ev_log
        run_ev_add("test-project", "Sprint review",
                   date_val="2026-03-10", time_val="10:00")
        rc = run_ev_log("test-project", "Sprint review")
        assert rc == 0
        log = _logbook_text(proj)
        assert "Sprint review" in log
        assert "#evento" in log
        # No agenda/room → no continuation lines.
        for line in log.splitlines():
            assert not line.startswith("  ["), f"unexpected continuation: {line!r}"

    def test_agenda_and_zoom_become_continuation_lines(
            self, proj, projects_dir, capsys):
        from core.agenda_cmds import run_ev_add, run_ev_log
        run_ev_add("test-project", "Project kickoff",
                   date_val="2026-03-10", time_val="10:00",
                   agenda="https://indico.cern.ch/event/12345",
                   room="https://zoom.us/j/9999")
        rc = run_ev_log("test-project", "kickoff")
        assert rc == 0
        log = _logbook_text(proj)
        # Main entry on its own line, tag intact.
        assert "Project kickoff" in log
        assert "#evento" in log
        # Indented continuations with clickable icons (matches the existing
        # markdown convention from event_indicators(markdown=True)).
        assert "  [📋](https://indico.cern.ch/event/12345)" in log
        assert "  [📹](https://zoom.us/j/9999)" in log

    def test_physical_room_uses_door_icon_no_link(
            self, proj, projects_dir, capsys):
        from core.agenda_cmds import run_ev_add, run_ev_log
        run_ev_add("test-project", "Aula meeting",
                   date_val="2026-03-10", time_val="10:00",
                   room="Aula A1-01")
        run_ev_log("test-project", "Aula meeting")
        log = _logbook_text(proj)
        # Plain text room → raw 🚪 prefix, not a markdown link.
        assert "  🚪 Aula A1-01" in log
        assert "[🚪]" not in log

    def test_not_found(self, proj, projects_dir, capsys):
        from core.agenda_cmds import run_ev_add, run_ev_log
        run_ev_add("test-project", "Existing", date_val="2026-03-10",
                   time_val="10:00")
        rc = run_ev_log("test-project", "Ghost")
        assert rc == 1


class TestReminderLog:
    def test_creates_logbook_entry(self, proj, projects_dir, capsys):
        from core.agenda_cmds import run_reminder_add, run_reminder_log
        run_reminder_add("test-project", "Check email", date_val="2026-03-10",
                         time_val="10:00")
        rc = run_reminder_log("test-project", "email")
        assert rc == 0
        log = _logbook_text(proj)
        assert "Check email" in log
        assert "#apunte" in log

    def test_not_found(self, proj, projects_dir, capsys):
        from core.agenda_cmds import run_reminder_add, run_reminder_log
        run_reminder_add("test-project", "Exists", date_val="2026-03-20",
                         time_val="10:00")
        rc = run_reminder_log("test-project", "Ghost")
        assert rc == 1


# ══════════════════════════════════════════════════════════════════════════════
# _upsert_emoji_note + ev --agenda/--room
# ══════════════════════════════════════════════════════════════════════════════

class TestUpsertEmojiNote:
    def test_insert_when_absent(self):
        from core.agenda_cmds import _upsert_emoji_note
        out = _upsert_emoji_note(["Plain note"], "🚪 ", "https://zoom/x")
        assert out == ["Plain note", "🚪 https://zoom/x"]

    def test_replace_when_present(self):
        from core.agenda_cmds import _upsert_emoji_note
        out = _upsert_emoji_note(["d", "🚪 https://old"], "🚪 ", "https://new")
        assert out == ["d", "🚪 https://new"]

    def test_remove_with_none(self):
        from core.agenda_cmds import _upsert_emoji_note
        out = _upsert_emoji_note(["d", "🚪 https://x"], "🚪 ", "none")
        assert out == ["d"]

    def test_value_none_means_no_change(self):
        from core.agenda_cmds import _upsert_emoji_note
        out = _upsert_emoji_note(["d", "🚪 https://x"], "🚪 ", None)
        assert out == ["d", "🚪 https://x"]

    def test_does_not_touch_other_prefixes(self):
        from core.agenda_cmds import _upsert_emoji_note
        out = _upsert_emoji_note(["📋 https://agenda", "🚪 https://room"],
                                 "🚪 ", "none")
        assert out == ["📋 https://agenda"]


class TestEventIndicators:
    def test_no_notes_returns_empty(self):
        from core.agenda_cmds import event_indicators
        assert event_indicators({}) == ""
        assert event_indicators({"notes": []}) == ""

    def test_room_url_renders_video_camera(self):
        """URL room → 📹 (matches Calendar.app convention)."""
        from core.agenda_cmds import event_indicators
        item = {"notes": ["plain description", "🚪 https://zoom"]}
        assert event_indicators(item, markdown=False) == " 📹"

    def test_room_physical_renders_door(self):
        """Plain-text room → 🚪 (physical place)."""
        from core.agenda_cmds import event_indicators
        item = {"notes": ["🚪 Aula A1-01"]}
        assert event_indicators(item, markdown=False) == " 🚪"

    def test_mixed_rooms_show_both_icons(self):
        from core.agenda_cmds import event_indicators
        item = {"notes": ["🚪 https://zoom", "🚪 IGFAE-203"]}
        assert event_indicators(item, markdown=False) == " 📹 🚪"

    def test_room_and_agenda_terminal(self):
        from core.agenda_cmds import event_indicators
        item = {"notes": ["📋 https://x", "🚪 https://y"]}
        assert event_indicators(item, markdown=False) == " 📹 📋"

    def test_markdown_links_url_room(self):
        from core.agenda_cmds import event_indicators
        item = {"notes": ["📋 https://indico", "🚪 https://zoom"]}
        out = event_indicators(item, markdown=True)
        assert out == " [📹](https://zoom) [📋](https://indico)"

    def test_markdown_links_physical_room(self):
        from core.agenda_cmds import event_indicators
        item = {"notes": ["🚪 Despacho 5"]}
        assert event_indicators(item, markdown=True) == " [🚪](Despacho 5)"

    def test_multiple_rooms_markdown(self):
        from core.agenda_cmds import event_indicators
        item = {"notes": ["🚪 https://zoom1", "🚪 https://zoom2"]}
        out = event_indicators(item, markdown=True)
        assert out == " [📹](https://zoom1) [📹](https://zoom2)"

    def test_is_meeting_url(self):
        from core.agenda_cmds import _is_meeting_url
        assert _is_meeting_url("https://zoom.us/j/123") is True
        assert _is_meeting_url("http://meet.google.com/x") is True
        assert _is_meeting_url("Aula A1-01") is False
        assert _is_meeting_url("") is False
        assert _is_meeting_url(None) is False
        assert _is_meeting_url("  https://x  ") is True  # leading/trailing space ok

    def test_url_helpers(self):
        from core.agenda_cmds import event_room_urls, event_agenda_urls
        item = {"notes": ["desc libre", "📋 https://a", "🚪 https://r1",
                          "🚪 https://r2"]}
        assert event_room_urls(item) == ["https://r1", "https://r2"]
        assert event_agenda_urls(item) == ["https://a"]

    def test_email_url_helper(self):
        from core.agenda_cmds import event_email_urls
        item = {"notes": ["📋 https://a", "✉️ message://%3Cabc%40x%3E"]}
        assert event_email_urls(item) == ["message://%3Cabc%40x%3E"]

    def test_email_indicator_terminal(self):
        from core.agenda_cmds import event_indicators
        item = {"notes": ["✉️ message://%3Cabc%40x%3E"]}
        assert event_indicators(item, markdown=False) == " ✉️"

    def test_email_indicator_markdown(self):
        from core.agenda_cmds import event_indicators
        item = {"notes": ["✉️ message://%3Cabc%40x%3E"]}
        out = event_indicators(item, markdown=True)
        assert out == " [✉️](message://%3Cabc%40x%3E)"

    def test_room_agenda_email_combined(self):
        from core.agenda_cmds import event_indicators
        item = {"notes": ["📋 https://i", "🚪 https://z",
                          "✉️ message://%3Cm%3E"]}
        assert event_indicators(item, markdown=False) == " 📹 📋 ✉️"

    def test_format_item_line_terminal_includes_emojis(self, proj, projects_dir):
        from core.agenda_cmds import run_ev_add, _read_agenda
        from core.agenda_view import _format_item_line
        run_ev_add("test-project", "Mtg", "2030-05-10", time_val="12:00",
                   agenda="https://x", room="https://y")
        ev = _read_agenda(proj / "test-project-agenda.md")["events"][0]
        line = _format_item_line("event", ev, "[p]", markdown=False)
        assert "📹" in line and "📋" in line
        assert "https://x" not in line  # no URL in terminal output

    def test_format_item_line_markdown_includes_links(self, proj, projects_dir):
        from core.agenda_cmds import run_ev_add, _read_agenda
        from core.agenda_view import _format_item_line
        run_ev_add("test-project", "Mtg", "2030-05-10", time_val="12:00",
                   agenda="https://indico/x", room="https://zoom/y")
        ev = _read_agenda(proj / "test-project-agenda.md")["events"][0]
        line = _format_item_line("event", ev, "[p]", markdown=True)
        assert "[📹](https://zoom/y)" in line
        assert "[📋](https://indico/x)" in line

    def test_table_row_includes_md_links(self, proj, projects_dir):
        from core.agenda_cmds import run_ev_add, _read_agenda
        from core.agenda_view import _item_to_table_row
        run_ev_add("test-project", "Mtg", "2030-05-10", time_val="12:00",
                   room="https://zoom/y")
        ev = _read_agenda(proj / "test-project-agenda.md")["events"][0]
        _, _, desc, _ = _item_to_table_row("event", ev, "[p]")
        assert "[📹](https://zoom/y)" in desc

    def test_event_without_room_or_agenda_no_indicator(self, proj, projects_dir):
        from core.agenda_cmds import run_ev_add, _read_agenda
        from core.agenda_view import _format_item_line
        run_ev_add("test-project", "Plain mtg", "2030-05-10", time_val="12:00")
        ev = _read_agenda(proj / "test-project-agenda.md")["events"][0]
        line = _format_item_line("event", ev, "[p]", markdown=False)
        assert "🚪" not in line and "📋" not in line


class TestEventAgendaRoomFlags:
    def test_add_with_room(self, proj, projects_dir):
        from core.agenda_cmds import run_ev_add, _read_agenda
        run_ev_add("test-project", "Reunión", "2026-05-10", time_val="12:00",
                   room="https://zoom.us/j/123")
        ev = _read_agenda(proj / "test-project-agenda.md")["events"][0]
        assert "🚪 https://zoom.us/j/123" in ev["notes"]

    def test_add_with_agenda(self, proj, projects_dir):
        from core.agenda_cmds import run_ev_add, _read_agenda
        run_ev_add("test-project", "WG12", "2026-05-08",
                   agenda="https://indico/event/17950")
        ev = _read_agenda(proj / "test-project-agenda.md")["events"][0]
        assert "📋 https://indico/event/17950" in ev["notes"]

    def test_add_with_desc_agenda_room_in_order(self, proj, projects_dir):
        from core.agenda_cmds import run_ev_add, _read_agenda
        run_ev_add("test-project", "Mtg", "2026-05-08",
                   desc="Reunión semanal",
                   agenda="https://indico/x", room="https://zoom/y")
        ev = _read_agenda(proj / "test-project-agenda.md")["events"][0]
        assert ev["notes"] == [
            "Reunión semanal",
            "📋 https://indico/x",
            "🚪 https://zoom/y",
        ]

    def test_edit_adds_room_to_event_without_one(self, proj, projects_dir):
        from core.agenda_cmds import run_ev_add, run_ev_edit, _read_agenda
        run_ev_add("test-project", "Mtg", "2026-05-10")
        run_ev_edit("test-project", "Mtg", new_room="https://zoom/abc")
        ev = _read_agenda(proj / "test-project-agenda.md")["events"][0]
        assert "🚪 https://zoom/abc" in ev["notes"]

    def test_edit_replaces_existing_room(self, proj, projects_dir):
        from core.agenda_cmds import run_ev_add, run_ev_edit, _read_agenda
        run_ev_add("test-project", "Mtg", "2026-05-10",
                   room="https://zoom/old")
        run_ev_edit("test-project", "Mtg", new_room="https://zoom/new")
        ev = _read_agenda(proj / "test-project-agenda.md")["events"][0]
        rooms = [n for n in ev["notes"] if n.startswith("🚪 ")]
        assert rooms == ["🚪 https://zoom/new"]

    def test_edit_room_none_removes_it(self, proj, projects_dir):
        from core.agenda_cmds import run_ev_add, run_ev_edit, _read_agenda
        run_ev_add("test-project", "Mtg", "2026-05-10",
                   room="https://zoom/x")
        run_ev_edit("test-project", "Mtg", new_room="none")
        ev = _read_agenda(proj / "test-project-agenda.md")["events"][0]
        notes = ev.get("notes") or []
        assert not any(n.startswith("🚪 ") for n in notes)

    def test_edit_desc_preserves_room_and_agenda(self, proj, projects_dir):
        """A `--desc` edit on an event must NOT drop existing 📋/🚪 notes."""
        from core.agenda_cmds import run_ev_add, run_ev_edit, _read_agenda
        run_ev_add("test-project", "Mtg", "2026-05-10",
                   desc="vieja desc",
                   agenda="https://indico/x", room="https://zoom/y")
        run_ev_edit("test-project", "Mtg", new_desc="nueva desc")
        ev = _read_agenda(proj / "test-project-agenda.md")["events"][0]
        assert ev["notes"] == [
            "nueva desc",
            "📋 https://indico/x",
            "🚪 https://zoom/y",
        ]

    def test_edit_desc_on_task_does_not_preserve_anything(self, proj, projects_dir):
        """Tasks must keep the old replace-all semantics for --desc."""
        from core.agenda_cmds import run_task_add, run_task_edit, _read_agenda
        run_task_add("test-project", "Tsk", date_val="2026-05-10",
                     desc="vieja")
        run_task_edit("test-project", "Tsk", new_desc="nueva")
        task = _read_agenda(proj / "test-project-agenda.md")["tasks"][0]
        assert task["notes"] == ["nueva"]

    def test_agenda_and_room_persist_to_disk(self, proj, projects_dir):
        from core.agenda_cmds import run_ev_add
        run_ev_add("test-project", "X", "2026-05-10",
                   agenda="https://indico/z", room="https://meet/k")
        text = (proj / "test-project-agenda.md").read_text()
        assert "📋 https://indico/z" in text
        assert "🚪 https://meet/k" in text

    def test_edit_room_on_recurring_occurrence(self, proj, projects_dir):
        """Editing room on a single occurrence of a recurring event keeps
        the room in the new non-recurring copy and advances the series."""
        from core.agenda_cmds import run_ev_add, run_ev_edit, _read_agenda
        run_ev_add("test-project", "Weekly", "2026-05-08", recur="weekly")
        run_ev_edit("test-project", "Weekly",
                    new_room="https://zoom/once",
                    occurrence=True)
        evs = _read_agenda(proj / "test-project-agenda.md")["events"]
        # one with room (the edited occurrence), one recurring next week
        with_room = [e for e in evs if any(n.startswith("🚪 ") for n in (e.get("notes") or []))]
        recurring = [e for e in evs if e.get("recur")]
        assert len(with_room) == 1
        assert len(recurring) == 1
        assert with_room[0]["date"] == "2026-05-08"
        assert recurring[0]["date"] == "2026-05-15"


class TestOrbitIdInMarkdown:
    """orbit-id [orbit:xxx] tag round-trips through parsers and writers."""

    def test_extract_orbit_id(self):
        from core.agenda_cmds import _extract_orbit_id
        assert _extract_orbit_id("[orbit:abc12345]") == "abc12345"
        assert _extract_orbit_id("desc [orbit:abc12345] tail") == "abc12345"
        assert _extract_orbit_id("no tag") is None
        assert _extract_orbit_id("") is None
        assert _extract_orbit_id("[orbit:NOPE]") is None  # uppercase rejected

    def test_task_parse_extracts_orbit_id(self):
        from core.agenda_cmds import _parse_task_line
        item = _parse_task_line("- [ ] Mi tarea (2026-05-15) ⏰09:00 [orbit:abc12345]")
        assert item["orbit_id"] == "abc12345"
        assert item["desc"] == "Mi tarea"
        assert item["date"] == "2026-05-15"
        assert item["time"] == "09:00"

    def test_task_format_appends_orbit_id(self):
        from core.agenda_cmds import _format_task_line
        line = _format_task_line({
            "status": "pending", "desc": "Foo", "date": "2026-05-15",
            "time": None, "recur": None, "ring": None,
            "orbit_id": "abc12345",
        })
        assert line.endswith("[orbit:abc12345]")

    def test_task_round_trip(self):
        from core.agenda_cmds import _parse_task_line, _format_task_line
        original = "- [ ] Foo (2026-05-15) ⏰09:00 🔄weekly 🔔10m [orbit:abc12345]"
        parsed = _parse_task_line(original)
        rebuilt = _format_task_line(parsed)
        assert rebuilt == original

    def test_event_parse_extracts_orbit_id(self):
        from core.agenda_cmds import _parse_event_line
        ev = _parse_event_line(
            "2026-05-11 — natación ⏰10:30 🔄weekly:2026-06-01 🔔10m [orbit:fd761027]"
        )
        assert ev["orbit_id"] == "fd761027"
        assert ev["desc"] == "natación"
        assert ev["recur"] == "weekly"
        assert ev["until"] == "2026-06-01"

    def test_event_round_trip(self):
        from core.agenda_cmds import _parse_event_line, _format_event_line
        original = "2026-05-11 — Mtg ⏰12:00 [orbit:1a2b3c4d]"
        parsed = _parse_event_line(original)
        rebuilt = _format_event_line(parsed)
        assert rebuilt == original

    def test_reminder_parse_extracts_orbit_id(self):
        from core.agenda_cmds import _parse_reminder_line
        rem = _parse_reminder_line(
            "- Llamar (2026-05-11) ⏰18:00 [orbit:11223344]"
        )
        assert rem["orbit_id"] == "11223344"
        assert rem["desc"] == "Llamar"

    def test_reminder_round_trip(self):
        from core.agenda_cmds import _parse_reminder_line, _format_reminder_line
        original = "- Llamar (2026-05-11) ⏰18:00 [orbit:11223344]"
        parsed = _parse_reminder_line(original)
        rebuilt = _format_reminder_line(parsed)
        assert rebuilt == original

    def test_legacy_cloud_marker_stripped_silently(self):
        """Items written by older orbit had ☁️ as a 'synced' marker. The
        parser strips it without erroring; orbit-id (when present) is now
        the canonical source of sync state."""
        from core.agenda_cmds import _parse_task_line
        item = _parse_task_line("- [ ] Old task (2026-05-15) ☁️")
        assert item["orbit_id"] is None
        assert item["desc"] == "Old task"
        assert "synced" not in item

    def test_format_omits_orbit_id_when_absent(self):
        """No tag is written for items that haven't synced yet."""
        from core.agenda_cmds import _format_task_line
        line = _format_task_line({
            "status": "pending", "desc": "Foo", "date": "2026-05-15",
            "time": None, "recur": None, "ring": None,
            "orbit_id": None,
        })
        assert "[orbit:" not in line
        assert "☁️" not in line

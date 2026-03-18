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
        assert "próximo: 2026-04-01" in out

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
        assert "próximo: 2026-03-16" in out

    def test_drop_recurring_event_clears_synced(self, proj, projects_dir):
        from core.agenda_cmds import run_ev_add, run_ev_drop, _read_agenda
        run_ev_add("test-project", "Synced meeting", "2026-03-09", recur="weekly")
        # Manually mark as synced
        data = _read_agenda(proj / "test-project-agenda.md")
        data["events"][0]["synced"] = True
        from core.agenda_cmds import _write_agenda
        _write_agenda(proj / "test-project-agenda.md", data)
        run_ev_drop("test-project", "Synced meeting", force=True)
        data = _read_agenda(proj / "test-project-agenda.md")
        assert len(data["events"]) == 1
        assert not data["events"][0].get("synced")

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
              "ring": None, "synced": False}
        line = _format_event_line(ev)
        assert "⏰10:00-11:30" in line

    def test_format_event_without_time(self):
        from core.agenda_cmds import _format_event_line
        ev = {"date": "2026-03-15", "desc": "All day", "end": None,
              "time": None, "recur": None, "until": None,
              "ring": None, "synced": False}
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
        assert ev["synced"] is True
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

"""Unit tests for core/project_view.py — Phase 5: view / open for new-model projects."""

import sys
from datetime import date, timedelta
from pathlib import Path

import pytest


# ── Helpers ────────────────────────────────────────────────────────────────────

def _make_project(pdir: Path, name: str = "💻test-project") -> Path:
    project_dir = pdir / name
    project_dir.mkdir()
    import re
    base = re.sub(r'^[^\w]+', '', name)  # strip emoji prefix
    (project_dir / f"{base}-project.md").write_text(
        f"# {name}\n- Tipo: 💻 Software\n- Estado: [auto]\n- Prioridad: alta\n\n"
        f"## Estado actual\n*Test project.*\n"
    )
    (project_dir / f"{base}-logbook.md").write_text(
        f"# Logbook — {name}\n\n"
    )
    (project_dir / f"{base}-highlights.md").write_text(f"# Highlights — {name}\n\n")
    (project_dir / f"{base}-agenda.md").write_text(f"# Agenda — {name}\n\n")
    (project_dir / "notes").mkdir()
    return project_dir


def _base_name(project_dir: Path) -> str:
    import re
    return re.sub(r'^[^\w]+', '', project_dir.name)

def _add_logbook_entries(project_dir: Path, entries: list):
    lb = project_dir / f"{_base_name(project_dir)}-logbook.md"
    text = lb.read_text()
    for e in entries:
        text += f"\n{e}"
    lb.write_text(text)


def _add_task(project_dir: Path, desc: str, due: str = None, status: str = "pending"):
    from core.agenda_cmds import _read_agenda, _write_agenda
    data = _read_agenda(project_dir / f"{_base_name(project_dir)}-agenda.md")
    data["tasks"].append({"status": status, "desc": desc,
                           "date": due, "recur": None, "ring": None})
    _write_agenda(project_dir / f"{_base_name(project_dir)}-agenda.md", data)


def _add_milestone(project_dir: Path, desc: str, due: str = None):
    from core.agenda_cmds import _read_agenda, _write_agenda
    data = _read_agenda(project_dir / f"{_base_name(project_dir)}-agenda.md")
    data["milestones"].append({"status": "pending", "desc": desc,
                                "date": due, "recur": None, "ring": None})
    _write_agenda(project_dir / f"{_base_name(project_dir)}-agenda.md", data)


def _add_event(project_dir: Path, desc: str, event_date: str):
    from core.agenda_cmds import _read_agenda, _write_agenda
    data = _read_agenda(project_dir / f"{_base_name(project_dir)}-agenda.md")
    data["events"].append({"date": event_date, "desc": desc, "end": None})
    _write_agenda(project_dir / f"{_base_name(project_dir)}-agenda.md", data)


# ── Fixtures ───────────────────────────────────────────────────────────────────

@pytest.fixture()
def projects_dir(tmp_path, monkeypatch):
    pdir = tmp_path / "proyectos"
    pdir.mkdir()
    import core.project_view as pv
    import core.project as cp
    import core.log as cl
    import core.agenda_cmds as ac
    monkeypatch.setattr(pv, "PROJECTS_DIR", pdir)
    monkeypatch.setattr(cp, "PROJECTS_DIR", pdir)
    monkeypatch.setattr(cl, "PROJECTS_DIR", pdir)
    monkeypatch.setattr(ac, "PROJECTS_DIR", pdir)
    return pdir


@pytest.fixture()
def proj(projects_dir):
    return _make_project(projects_dir)


# ══════════════════════════════════════════════════════════════════════════════
# _recent_logbook_entries
# ══════════════════════════════════════════════════════════════════════════════

class TestRecentLogbookEntries:
    def test_empty_logbook(self, proj):
        from core.project_view import _recent_logbook_entries
        assert _recent_logbook_entries(proj) == []

    def test_returns_last_n(self, proj):
        from core.project_view import _recent_logbook_entries
        today = date.today().isoformat()
        entries = [f"{today} Entry {i} #apunte" for i in range(7)]
        _add_logbook_entries(proj, entries)
        result = _recent_logbook_entries(proj, n=5)
        assert len(result) == 5
        assert "Entry 6" in result[-1]

    def test_skips_headers(self, proj):
        from core.project_view import _recent_logbook_entries
        today = date.today().isoformat()
        _add_logbook_entries(proj, [f"{today} Real entry #apunte"])
        result = _recent_logbook_entries(proj)
        assert all("# " not in e for e in result)

    def test_missing_logbook(self, proj):
        from core.project_view import _recent_logbook_entries
        (proj / f"{_base_name(proj)}-logbook.md").unlink()
        assert _recent_logbook_entries(proj) == []


# ══════════════════════════════════════════════════════════════════════════════
# _upcoming_events
# ══════════════════════════════════════════════════════════════════════════════

class TestUpcomingEvents:
    def test_no_events(self, proj):
        from core.project_view import _upcoming_events
        assert _upcoming_events(proj) == []

    def test_event_within_window(self, proj):
        from core.project_view import _upcoming_events
        tomorrow = (date.today() + timedelta(days=1)).isoformat()
        _add_event(proj, "Tomorrow meeting", tomorrow)
        result = _upcoming_events(proj, days=5)
        assert len(result) == 1
        assert result[0][1] == "Tomorrow meeting"

    def test_event_beyond_window_excluded(self, proj):
        from core.project_view import _upcoming_events
        far_future = (date.today() + timedelta(days=10)).isoformat()
        _add_event(proj, "Far future", far_future)
        result = _upcoming_events(proj, days=5)
        assert result == []

    def test_past_event_excluded(self, proj):
        from core.project_view import _upcoming_events
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        _add_event(proj, "Yesterday", yesterday)
        result = _upcoming_events(proj, days=5)
        assert result == []

    def test_today_included(self, proj):
        from core.project_view import _upcoming_events
        today = date.today().isoformat()
        _add_event(proj, "Today event", today)
        result = _upcoming_events(proj, days=5)
        assert len(result) == 1

    def test_sorted_by_date(self, proj):
        from core.project_view import _upcoming_events
        d1 = (date.today() + timedelta(days=3)).isoformat()
        d2 = (date.today() + timedelta(days=1)).isoformat()
        _add_event(proj, "Later", d1)
        _add_event(proj, "Sooner", d2)
        result = _upcoming_events(proj, days=5)
        assert result[0][1] == "Sooner"
        assert result[1][1] == "Later"


# ══════════════════════════════════════════════════════════════════════════════
# _build_summary
# ══════════════════════════════════════════════════════════════════════════════

class TestBuildSummary:
    def test_includes_project_name(self, proj):
        from core.project_view import _build_summary
        text = _build_summary(proj)
        assert "test-project" in text

    def test_includes_status(self, proj):
        from core.project_view import _build_summary
        text = _build_summary(proj)
        assert "Estado:" in text

    def test_includes_priority(self, proj):
        from core.project_view import _build_summary
        text = _build_summary(proj)
        assert "alta" in text

    def test_shows_pending_tasks(self, proj):
        from core.project_view import _build_summary
        _add_task(proj, "Write paper", due="2026-04-01")
        text = _build_summary(proj)
        assert "Write paper" in text
        assert "Tareas pendientes" in text

    def test_done_tasks_not_shown(self, proj):
        from core.project_view import _build_summary
        _add_task(proj, "Done task", status="done")
        text = _build_summary(proj)
        assert "Done task" not in text

    def test_shows_pending_milestones(self, proj):
        from core.project_view import _build_summary
        _add_milestone(proj, "Submit paper")
        text = _build_summary(proj)
        assert "Submit paper" in text
        assert "Hitos pendientes" in text

    def test_shows_upcoming_events(self, proj):
        from core.project_view import _build_summary
        tomorrow = (date.today() + timedelta(days=1)).isoformat()
        _add_event(proj, "Team meeting", tomorrow)
        text = _build_summary(proj)
        assert "Team meeting" in text
        assert "Próximos 5 días" in text

    def test_shows_recent_logbook(self, proj):
        from core.project_view import _build_summary
        today = date.today().isoformat()
        _add_logbook_entries(proj, [f"{today} Recent entry #apunte"])
        text = _build_summary(proj)
        assert "Recent entry" in text
        assert "Últimas entradas" in text

    def test_minimal_project(self, proj):
        """Project with no tasks/milestones/events/logbook still renders."""
        from core.project_view import _build_summary
        text = _build_summary(proj)
        assert "Estado:" in text   # always shows status

    def test_task_date_shown(self, proj):
        from core.project_view import _build_summary
        _add_task(proj, "Deadline task", due="2026-06-01")
        text = _build_summary(proj)
        assert "2026-06-01" in text


# ══════════════════════════════════════════════════════════════════════════════
# _build_summary_md
# ══════════════════════════════════════════════════════════════════════════════

class TestBuildSummaryMd:
    def test_is_markdown(self, proj):
        from core.project_view import _build_summary_md
        text = _build_summary_md(proj)
        assert text.startswith("# ")

    def test_includes_tasks(self, proj):
        from core.project_view import _build_summary_md
        _add_task(proj, "MD task")
        text = _build_summary_md(proj)
        assert "- [ ] MD task" in text

    def test_includes_milestones(self, proj):
        from core.project_view import _build_summary_md
        _add_milestone(proj, "Big milestone")
        text = _build_summary_md(proj)
        assert "Big milestone" in text


# ══════════════════════════════════════════════════════════════════════════════
# run_new_view
# ══════════════════════════════════════════════════════════════════════════════

class TestRunNewView:
    def test_shows_summary(self, proj, projects_dir, capsys):
        from core.project_view import run_new_view
        rc = run_new_view("test-project")
        assert rc == 0
        out = capsys.readouterr().out
        assert "test-project" in out
        assert "Estado:" in out

    def test_project_not_found(self, projects_dir, capsys):
        from core.project_view import run_new_view
        rc = run_new_view("nonexistent")
        assert rc == 1

    def test_no_project_no_tty_returns_1(self, projects_dir, monkeypatch):
        """Without TTY and no project name, picker exits with 1."""
        from core.project_view import run_new_view
        monkeypatch.setattr(sys, "stdin", open("/dev/null"))
        rc = run_new_view(None)
        assert rc == 1

    def test_open_creates_temp_file(self, proj, projects_dir, monkeypatch):
        from core.project_view import run_new_view
        opened = []
        monkeypatch.setattr("core.project_view.open_file",
                            lambda path, editor: opened.append(path) or 0)
        rc = run_new_view("test-project", open_after=True)
        assert rc == 0
        assert len(opened) == 1
        assert opened[0].suffix == ".md"
        assert opened[0].exists()

    def test_open_summary_contains_tasks(self, proj, projects_dir, monkeypatch):
        from core.project_view import run_new_view
        _add_task(proj, "Important task")
        written = []
        def mock_open(path, editor):
            written.append(path.read_text())
            return 0
        monkeypatch.setattr("core.project_view.open_file", mock_open)
        run_new_view("test-project", open_after=True)
        assert "Important task" in written[0]


# ══════════════════════════════════════════════════════════════════════════════
# run_new_open
# ══════════════════════════════════════════════════════════════════════════════

class TestRunNewOpen:
    def test_open_project_default(self, proj, projects_dir, monkeypatch):
        from core.project_view import run_new_open
        opened = []
        monkeypatch.setattr("core.project_view.open_file",
                            lambda path, editor: opened.append(path.name) or 0)
        rc = run_new_open("test-project")
        assert rc == 0
        assert "test-project-project.md" in opened

    def test_open_logbook(self, proj, projects_dir, monkeypatch):
        from core.project_view import run_new_open
        opened = []
        monkeypatch.setattr("core.project_view.open_file",
                            lambda path, editor: opened.append(path.name) or 0)
        rc = run_new_open("test-project", what="logbook")
        assert rc == 0
        assert "test-project-logbook.md" in opened

    def test_open_highlights(self, proj, projects_dir, monkeypatch):
        from core.project_view import run_new_open
        opened = []
        monkeypatch.setattr("core.project_view.open_file",
                            lambda path, editor: opened.append(path.name) or 0)
        rc = run_new_open("test-project", what="highlights")
        assert rc == 0
        assert "test-project-highlights.md" in opened

    def test_open_agenda(self, proj, projects_dir, monkeypatch):
        from core.project_view import run_new_open
        opened = []
        monkeypatch.setattr("core.project_view.open_file",
                            lambda path, editor: opened.append(path.name) or 0)
        rc = run_new_open("test-project", what="agenda")
        assert rc == 0
        assert "test-project-agenda.md" in opened

    def test_open_notes_dir(self, proj, projects_dir, monkeypatch):
        from core.project_view import run_new_open
        opened = []
        monkeypatch.setattr("core.project_view.open_file",
                            lambda path, editor: opened.append(path) or 0)
        rc = run_new_open("test-project", what="notes")
        assert rc == 0
        assert opened[0].is_dir()

    def test_open_invalid_what(self, proj, projects_dir, capsys):
        from core.project_view import run_new_open
        rc = run_new_open("test-project", what="invalid")
        assert rc == 1
        assert "no válido" in capsys.readouterr().out

    def test_project_not_found(self, projects_dir, capsys):
        from core.project_view import run_new_open
        rc = run_new_open("nonexistent")
        assert rc == 1

    def test_open_missing_file(self, proj, projects_dir, capsys):
        from core.project_view import run_new_open
        (proj / f"{_base_name(proj)}-highlights.md").unlink()
        rc = run_new_open("test-project", what="highlights")
        assert rc == 1
        assert "no existe" in capsys.readouterr().out

    def test_partial_name_match(self, proj, projects_dir, monkeypatch):
        from core.project_view import run_new_open
        opened = []
        monkeypatch.setattr("core.project_view.open_file",
                            lambda path, editor: opened.append(path.name) or 0)
        rc = run_new_open("test")   # partial match "test" → "💻test-project"
        assert rc == 0
        assert "test-project-project.md" in opened


# ══════════════════════════════════════════════════════════════════════════════
# _pick_project (interactive project picker)
# ══════════════════════════════════════════════════════════════════════════════

class TestPickProject:
    def test_no_projects(self, projects_dir, capsys, monkeypatch):
        from core.project_view import _pick_project
        monkeypatch.setattr(sys, "stdin", open("/dev/null"))
        result = _pick_project()
        assert result is None
        assert "No hay proyectos" in capsys.readouterr().out

    def test_lists_projects(self, projects_dir, capsys, monkeypatch):
        from core.project_view import _pick_project
        _make_project(projects_dir, "💻proj-alpha")
        _make_project(projects_dir, "💻proj-beta")
        monkeypatch.setattr(sys, "stdin", open("/dev/null"))
        _pick_project()
        out = capsys.readouterr().out
        assert "proj-alpha" in out
        assert "proj-beta"  in out

    def test_no_tty_returns_none(self, projects_dir, monkeypatch):
        from core.project_view import _pick_project
        _make_project(projects_dir, "💻proj-x")
        monkeypatch.setattr(sys, "stdin", open("/dev/null"))
        assert _pick_project() is None

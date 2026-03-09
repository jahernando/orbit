"""Unit tests for core/notes.py and core/commit.py — Phase 6."""

import subprocess
import sys
from pathlib import Path

import pytest


# ── Helpers ────────────────────────────────────────────────────────────────────

def _base_name(name: str) -> str:
    """Strip leading emoji prefix from project directory name."""
    import re
    return re.sub(r'^[\U00010000-\U0010ffff\u2600-\u27bf\ufe0f]+', '', name)


def _make_project(pdir: Path, name: str = "💻test-project") -> Path:
    base = _base_name(name)
    project_dir = pdir / name
    project_dir.mkdir()
    (project_dir / f"{base}-project.md").write_text(
        f"# {name}\n- Tipo: 💻 Software\n- Estado: [auto]\n- Prioridad: media\n"
    )
    (project_dir / f"{base}-logbook.md").write_text(f"# Logbook — {name}\n\n")
    (project_dir / f"{base}-highlights.md").write_text(f"# Highlights — {name}\n\n")
    (project_dir / f"{base}-agenda.md").write_text(f"# Agenda — {name}\n\n")
    (project_dir / "notes").mkdir()
    return project_dir


def _log_text(project_dir: Path) -> str:
    base = _base_name(project_dir.name)
    return (project_dir / f"{base}-logbook.md").read_text()


# ── Fixtures ───────────────────────────────────────────────────────────────────

@pytest.fixture()
def projects_dir(tmp_path, monkeypatch):
    pdir = tmp_path / "proyectos"
    pdir.mkdir()
    import core.notes as nt
    import core.project as cp
    import core.log as cl
    monkeypatch.setattr(nt, "ORBIT_DIR", tmp_path)
    monkeypatch.setattr(cp, "PROJECTS_DIR", pdir)
    monkeypatch.setattr(cl, "PROJECTS_DIR", pdir)
    return pdir


@pytest.fixture()
def proj(projects_dir):
    return _make_project(projects_dir)


# ══════════════════════════════════════════════════════════════════════════════
# _title_to_filename
# ══════════════════════════════════════════════════════════════════════════════

class TestTitleToFilename:
    def test_simple(self):
        from core.notes import _title_to_filename
        assert _title_to_filename("My Analysis") == "my_analysis.md"

    def test_accents_stripped(self):
        from core.notes import _title_to_filename
        name = _title_to_filename("Análisis de calibración")
        assert "á" not in name
        assert "ó" not in name
        assert name.endswith(".md")

    def test_special_chars_removed(self):
        from core.notes import _title_to_filename
        name = _title_to_filename("Report: 2026 (final!)")
        assert ":" not in name
        assert "!" not in name
        assert "(" not in name

    def test_spaces_to_underscore(self):
        from core.notes import _title_to_filename
        assert _title_to_filename("foo bar baz") == "foo_bar_baz.md"

    def test_multiple_spaces(self):
        from core.notes import _title_to_filename
        name = _title_to_filename("a  b   c")
        assert "__" not in name


# ══════════════════════════════════════════════════════════════════════════════
# run_note_create
# ══════════════════════════════════════════════════════════════════════════════

class TestRunNoteCreate:
    def test_creates_note_file(self, proj, projects_dir, monkeypatch, capsys):
        from core.notes import run_note_create
        monkeypatch.setattr(sys, "stdin", open("/dev/null"))
        monkeypatch.setattr("core.notes.open_file", lambda p, e: None)
        rc = run_note_create("test-project", "My Analysis", open_after=False)
        assert rc == 0
        notes = list((proj / "notes").glob("*.md"))
        assert len(notes) == 1
        assert notes[0].name == "my_analysis.md"

    def test_note_has_title_heading(self, proj, projects_dir, monkeypatch):
        from core.notes import run_note_create
        monkeypatch.setattr(sys, "stdin", open("/dev/null"))
        monkeypatch.setattr("core.notes.open_file", lambda p, e: None)
        run_note_create("test-project", "Test Note", open_after=False)
        content = (proj / "notes" / "test_note.md").read_text()
        assert "# Test Note" in content

    def test_logbook_orbit_entry(self, proj, projects_dir, monkeypatch):
        from core.notes import run_note_create
        monkeypatch.setattr(sys, "stdin", open("/dev/null"))
        monkeypatch.setattr("core.notes.open_file", lambda p, e: None)
        run_note_create("test-project", "My Note", open_after=False)
        log = _log_text(proj)
        assert "[nota creada]" in log
        assert "my_note.md" in log
        assert "[O]" in log

    def test_import_existing_md(self, tmp_path, proj, projects_dir, monkeypatch, capsys):
        from core.notes import run_note_create
        monkeypatch.setattr(sys, "stdin", open("/dev/null"))
        monkeypatch.setattr("core.notes.open_file", lambda p, e: None)
        src = tmp_path / "existing.md"
        src.write_text("# Existing note\n\nContent here.\n")
        rc = run_note_create("test-project", "Existing", file_str=str(src), open_after=False)
        assert rc == 0
        assert (proj / "notes" / "existing.md").exists()

    def test_import_non_md_fails(self, tmp_path, proj, projects_dir, monkeypatch, capsys):
        from core.notes import run_note_create
        src = tmp_path / "data.csv"
        src.write_text("a,b,c")
        rc = run_note_create("test-project", "Data", file_str=str(src), open_after=False)
        assert rc == 1
        assert ".md" in capsys.readouterr().out

    def test_import_missing_file(self, proj, projects_dir, monkeypatch, capsys):
        from core.notes import run_note_create
        rc = run_note_create("test-project", "Ghost", file_str="/nonexistent/file.md",
                             open_after=False)
        assert rc == 1
        assert "no encontrado" in capsys.readouterr().out

    def test_project_not_found(self, projects_dir, capsys):
        from core.notes import run_note_create
        rc = run_note_create("nonexistent", "Note", open_after=False)
        assert rc == 1

    def test_output_message(self, proj, projects_dir, monkeypatch, capsys):
        from core.notes import run_note_create
        monkeypatch.setattr(sys, "stdin", open("/dev/null"))
        monkeypatch.setattr("core.notes.open_file", lambda p, e: None)
        run_note_create("test-project", "Output Test", open_after=False)
        assert "output_test.md" in capsys.readouterr().out

    def test_git_add_skipped_without_tty(self, proj, projects_dir, monkeypatch):
        """Git add not attempted when stdin is not a tty."""
        from core.notes import run_note_create
        git_calls = []
        monkeypatch.setattr(sys, "stdin", open("/dev/null"))
        monkeypatch.setattr("core.notes._git_add_file",
                            lambda p: git_calls.append(p) or True)
        monkeypatch.setattr("core.notes.open_file", lambda p, e: None)
        run_note_create("test-project", "Test", open_after=False)
        assert git_calls == []   # no call without TTY

    def test_overwrites_existing_with_warning(self, proj, projects_dir, monkeypatch, capsys):
        from core.notes import run_note_create
        monkeypatch.setattr(sys, "stdin", open("/dev/null"))
        monkeypatch.setattr("core.notes.open_file", lambda p, e: None)
        (proj / "notes" / "my_note.md").write_text("# old content")
        run_note_create("test-project", "My Note", open_after=False)
        assert "sobreescribirá" in capsys.readouterr().out


# ══════════════════════════════════════════════════════════════════════════════
# run_note_list
# ══════════════════════════════════════════════════════════════════════════════

class TestRunNoteList:
    def test_no_notes(self, proj, projects_dir, capsys):
        from core.notes import run_note_list
        rc = run_note_list("test-project")
        assert rc == 0
        assert "sin notas" in capsys.readouterr().out

    def test_lists_notes(self, proj, projects_dir, monkeypatch, capsys):
        from core.notes import run_note_list
        (proj / "notes" / "analysis.md").write_text("# Analysis\n")
        (proj / "notes" / "draft.md").write_text("# Draft\n")
        monkeypatch.setattr("core.notes._git_tracked", lambda p: False)
        rc = run_note_list("test-project")
        assert rc == 0
        out = capsys.readouterr().out
        assert "analysis.md" in out
        assert "draft.md"    in out

    def test_shows_git_status_tracked(self, proj, projects_dir, monkeypatch, capsys):
        from core.notes import run_note_list
        (proj / "notes" / "tracked.md").write_text("# Tracked\n")
        monkeypatch.setattr("core.notes._git_tracked", lambda p: True)
        run_note_list("test-project")
        assert "✓ git" in capsys.readouterr().out

    def test_shows_git_status_untracked(self, proj, projects_dir, monkeypatch, capsys):
        from core.notes import run_note_list
        (proj / "notes" / "new.md").write_text("# New\n")
        monkeypatch.setattr("core.notes._git_tracked", lambda p: False)
        run_note_list("test-project")
        assert "✗ git" in capsys.readouterr().out

    def test_project_not_found(self, projects_dir, capsys):
        from core.notes import run_note_list
        rc = run_note_list("nonexistent")
        assert rc == 1

    def test_missing_notes_dir(self, proj, projects_dir, capsys):
        from core.notes import run_note_list
        (proj / "notes").rmdir()
        rc = run_note_list("test-project")
        assert rc == 0
        assert "no tiene" in capsys.readouterr().out


# ══════════════════════════════════════════════════════════════════════════════
# run_note_drop
# ══════════════════════════════════════════════════════════════════════════════

class TestRunNoteDrop:
    def test_drop_by_name(self, proj, projects_dir, capsys):
        from core.notes import run_note_drop
        note = proj / "notes" / "to_delete.md"
        note.write_text("# To Delete\n")
        rc = run_note_drop("test-project", "to_delete", force=True)
        assert rc == 0
        assert not note.exists()

    def test_logbook_entry_on_drop(self, proj, projects_dir, capsys):
        from core.notes import run_note_drop
        (proj / "notes" / "my_note.md").write_text("# My Note\n")
        run_note_drop("test-project", "my_note", force=True)
        log = _log_text(proj)
        assert "[nota borrada]" in log
        assert "my_note.md"     in log
        assert "[O]"            in log

    def test_drop_reads_title_from_h1(self, proj, projects_dir, capsys):
        from core.notes import run_note_drop
        (proj / "notes" / "analysis.md").write_text("# My Analysis Title\n\nContent.")
        run_note_drop("test-project", "analysis", force=True)
        log = _log_text(proj)
        assert "My Analysis Title" in log

    def test_drop_not_found(self, proj, projects_dir, capsys):
        from core.notes import run_note_drop
        # Add a note so "no notas" message doesn't fire; search for non-existent one
        (proj / "notes" / "real_note.md").write_text("# Real\n")
        rc = run_note_drop("test-project", "ghost", force=True)
        assert rc == 1
        assert "no encontrada" in capsys.readouterr().out

    def test_drop_no_notes(self, proj, projects_dir, capsys):
        from core.notes import run_note_drop
        monkeypatch = None  # using capsys only
        rc = run_note_drop("test-project", "anything", force=True)
        assert rc == 1

    def test_drop_interactive_no_tty(self, proj, projects_dir, monkeypatch):
        from core.notes import run_note_drop
        (proj / "notes" / "a.md").write_text("# A\n")
        monkeypatch.setattr(sys, "stdin", open("/dev/null"))
        rc = run_note_drop("test-project", None, force=True)
        assert rc == 1   # no selection without TTY

    def test_project_not_found(self, projects_dir, capsys):
        from core.notes import run_note_drop
        rc = run_note_drop("nonexistent", "note", force=True)
        assert rc == 1


# ══════════════════════════════════════════════════════════════════════════════
# _auto_message (commit auto-message builder)
# ══════════════════════════════════════════════════════════════════════════════

class TestAutoMessage:
    def test_logbook_changes(self):
        from core.commit import _auto_message
        status = [("M", "🚀proyectos/💻mission/mission-logbook.md")]
        msg = _auto_message(status)
        assert "logbook" in msg
        assert "orbit:" in msg

    def test_multiple_file_types(self):
        from core.commit import _auto_message
        status = [
            ("M", "🚀proyectos/💻mission/mission-logbook.md"),
            ("M", "🚀proyectos/💻mission/mission-agenda.md"),
            ("A", "🚀proyectos/💻mission/notes/my_note.md"),
        ]
        msg = _auto_message(status)
        assert "logbook" in msg
        assert "agenda"  in msg
        assert "nota"    in msg

    def test_empty_status(self):
        from core.commit import _auto_message
        msg = _auto_message([])
        assert "orbit:" in msg
        assert "cambios" in msg

    def test_project_name_included(self):
        from core.commit import _auto_message
        status = [("M", "🚀proyectos/💻my-project/my-project-logbook.md")]
        msg = _auto_message(status)
        assert "my-project" in msg

    def test_returns_string(self):
        from core.commit import _auto_message
        assert isinstance(_auto_message([("M", "some/file.md")]), str)


# ══════════════════════════════════════════════════════════════════════════════
# run_commit
# ══════════════════════════════════════════════════════════════════════════════

class TestRunCommit:
    def test_no_changes(self, tmp_path, monkeypatch, capsys):
        from core.commit import run_commit
        monkeypatch.setattr("core.commit._git_add_all_tracked", lambda: True)
        monkeypatch.setattr("core.commit._git_status", lambda: [])
        rc = run_commit()
        assert rc == 0
        assert "Sin cambios" in capsys.readouterr().out

    def test_shows_changed_files(self, tmp_path, monkeypatch, capsys):
        from core.commit import run_commit
        monkeypatch.setattr("core.commit._git_add_all_tracked", lambda: True)
        monkeypatch.setattr("core.commit._git_status",
                            lambda: [("M", "logbook.md")])
        monkeypatch.setattr("core.commit._git_commit", lambda m: 0)
        monkeypatch.setattr(sys, "stdin", open("/dev/null"))
        run_commit(message="test commit")
        out = capsys.readouterr().out
        assert "logbook.md" in out

    def test_message_passed_directly(self, monkeypatch, capsys):
        from core.commit import run_commit
        committed = []
        monkeypatch.setattr("core.commit._git_add_all_tracked", lambda: True)
        monkeypatch.setattr("core.commit._git_status",
                            lambda: [("M", "logbook.md")])
        monkeypatch.setattr("core.commit._git_commit",
                            lambda m: committed.append(m) or 0)
        monkeypatch.setattr(sys, "stdin", open("/dev/null"))
        run_commit(message="my message")
        assert committed == ["my message"]

    def test_auto_message_on_empty_input(self, monkeypatch, capsys):
        from core.commit import run_commit
        committed = []
        monkeypatch.setattr("core.commit._git_add_all_tracked", lambda: True)
        monkeypatch.setattr("core.commit._git_status",
                            lambda: [("M", "🚀proyectos/💻proj/proj-logbook.md")])
        monkeypatch.setattr("core.commit._git_commit",
                            lambda m: committed.append(m) or 0)
        # Simulate non-tty so auto-message is generated without prompt
        monkeypatch.setattr(sys, "stdin", open("/dev/null"))
        run_commit()   # no message → auto-generate
        assert len(committed) == 1
        assert "orbit:" in committed[0]

    def test_git_commit_called_with_message(self, monkeypatch, capsys):
        from core.commit import run_commit
        committed = []
        monkeypatch.setattr("core.commit._git_add_all_tracked", lambda: True)
        monkeypatch.setattr("core.commit._git_status",
                            lambda: [("M", "logbook.md")])
        monkeypatch.setattr("core.commit._git_commit",
                            lambda m: committed.append(m) or 0)
        monkeypatch.setattr(sys, "stdin", open("/dev/null"))
        run_commit(message="explicit")
        assert "explicit" in committed

    def test_success_message(self, monkeypatch, capsys):
        from core.commit import run_commit
        monkeypatch.setattr("core.commit._git_add_all_tracked", lambda: True)
        monkeypatch.setattr("core.commit._git_status",
                            lambda: [("M", "f.md")])
        monkeypatch.setattr("core.commit._git_commit", lambda m: 0)
        monkeypatch.setattr(sys, "stdin", open("/dev/null"))
        run_commit(message="ok")
        assert "✓" in capsys.readouterr().out

    def test_failure_message(self, monkeypatch, capsys):
        from core.commit import run_commit
        monkeypatch.setattr("core.commit._git_add_all_tracked", lambda: True)
        monkeypatch.setattr("core.commit._git_status",
                            lambda: [("M", "f.md")])
        monkeypatch.setattr("core.commit._git_commit", lambda m: 1)
        monkeypatch.setattr(sys, "stdin", open("/dev/null"))
        rc = run_commit(message="fail")
        assert rc == 1
        assert "✗" in capsys.readouterr().out

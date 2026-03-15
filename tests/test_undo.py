"""Unit tests for core/undo.py — undo stack."""

import pytest
from pathlib import Path


@pytest.fixture(autouse=True)
def _clean_undo_stack():
    """Ensure the undo stack is clean before and after each test."""
    from core.undo import clear
    clear()
    yield
    clear()


# ── Low-level stack API ──────────────────────────────────────────────────────

class TestUndoStack:

    def test_empty_stack_undo(self, capsys):
        from core.undo import run_undo, can_undo
        assert not can_undo()
        rc = run_undo(choice=1)
        assert rc == 0
        assert "No hay nada" in capsys.readouterr().out

    def test_save_and_restore_existing_file(self, tmp_path, capsys):
        from core.undo import save_snapshot, commit_operation, run_undo
        f = tmp_path / "test.md"
        f.write_text("original")
        save_snapshot(f)
        commit_operation("edit test")
        f.write_text("modified")
        assert f.read_text() == "modified"
        run_undo(choice=1)
        assert f.read_text() == "original"
        assert "restaurado" in capsys.readouterr().out

    def test_save_and_restore_new_file(self, tmp_path, capsys):
        from core.undo import save_snapshot, commit_operation, run_undo
        f = tmp_path / "new.md"
        save_snapshot(f)  # file doesn't exist yet
        commit_operation("create new")
        f.write_text("new content")
        run_undo(choice=1)
        assert not f.exists()
        assert "eliminado" in capsys.readouterr().out

    def test_multiple_files_in_one_operation(self, tmp_path, capsys):
        from core.undo import save_snapshot, commit_operation, run_undo
        a = tmp_path / "a.md"
        b = tmp_path / "b.md"
        a.write_text("a-original")
        b.write_text("b-original")
        save_snapshot(a)
        save_snapshot(b)
        commit_operation("edit both")
        a.write_text("a-modified")
        b.write_text("b-modified")
        run_undo(choice=1)
        assert a.read_text() == "a-original"
        assert b.read_text() == "b-original"

    def test_multiple_operations_undo_last_only(self, tmp_path):
        from core.undo import save_snapshot, commit_operation, run_undo
        f = tmp_path / "test.md"
        f.write_text("v1")
        save_snapshot(f)
        commit_operation("op1")
        f.write_text("v2")
        save_snapshot(f)
        commit_operation("op2")
        f.write_text("v3")
        # Undo op2: v3 → v2
        run_undo(choice=1)
        assert f.read_text() == "v2"
        # Undo op1: v2 → v1
        run_undo(choice=1)
        assert f.read_text() == "v1"

    def test_duplicate_snapshot_keeps_first(self, tmp_path):
        from core.undo import save_snapshot, commit_operation, run_undo
        f = tmp_path / "test.md"
        f.write_text("original")
        save_snapshot(f)
        f.write_text("intermediate")
        save_snapshot(f)  # should be ignored — first snapshot wins
        commit_operation("test")
        f.write_text("final")
        run_undo(choice=1)
        assert f.read_text() == "original"

    def test_discard_operation(self, tmp_path):
        from core.undo import save_snapshot, discard_operation, can_undo
        f = tmp_path / "test.md"
        f.write_text("original")
        save_snapshot(f)
        discard_operation()
        assert not can_undo()

    def test_peek_label(self, tmp_path):
        from core.undo import save_snapshot, commit_operation, peek_label
        f = tmp_path / "test.md"
        f.write_text("x")
        save_snapshot(f)
        commit_operation("task add test hello")
        assert peek_label() == "task add test hello"

    def test_stack_limit(self, tmp_path):
        from core.undo import save_snapshot, commit_operation, _stack, MAX_STACK
        f = tmp_path / "test.md"
        for i in range(MAX_STACK + 5):
            f.write_text(f"v{i}")
            save_snapshot(f)
            commit_operation(f"op{i}")
        assert len(_stack) == MAX_STACK

    def test_choice_zero_cancels(self, tmp_path, capsys):
        from core.undo import save_snapshot, commit_operation, run_undo, can_undo
        f = tmp_path / "test.md"
        f.write_text("original")
        save_snapshot(f)
        commit_operation("op1")
        f.write_text("modified")
        rc = run_undo(choice=0)
        assert rc == 0
        assert can_undo()  # nothing was undone
        assert f.read_text() == "modified"
        assert "Cancelado" in capsys.readouterr().out

    def test_choice_multiple(self, tmp_path):
        from core.undo import save_snapshot, commit_operation, run_undo, can_undo
        f = tmp_path / "test.md"
        f.write_text("v1")
        save_snapshot(f)
        commit_operation("op1")
        f.write_text("v2")
        save_snapshot(f)
        commit_operation("op2")
        f.write_text("v3")
        save_snapshot(f)
        commit_operation("op3")
        f.write_text("v4")
        # Undo top 2 operations (op3 and op2) → back to v2's snapshot = v1... no
        # op3 snapshot = v3 before writing v4, op2 snapshot = v2 before writing v3
        # so undoing op3 restores v3, then undoing op2 restores v2? No.
        # _restore_entry pops __label__ and restores the snapshot content.
        # op3 saved v3 (content before v4 write? No, save_snapshot captures
        # content at time of call). Let me re-check:
        # v1 → save(v1) → commit(op1) → write v2
        # v2 → save(v2) → commit(op2) → write v3
        # v3 → save(v3) → commit(op3) → write v4
        # undo op3 → restore v3; undo op2 → restore v2
        run_undo(choice=2)
        assert f.read_text() == "v2"
        assert can_undo()  # op1 still there

    def test_choice_exceeds_stack(self, tmp_path, capsys):
        from core.undo import save_snapshot, commit_operation, run_undo
        f = tmp_path / "test.md"
        f.write_text("x")
        save_snapshot(f)
        commit_operation("op1")
        rc = run_undo(choice=5)
        assert rc == 1
        assert "Solo hay" in capsys.readouterr().out

    def test_interactive_prompt(self, tmp_path, capsys, monkeypatch):
        from core.undo import save_snapshot, commit_operation, run_undo
        f = tmp_path / "test.md"
        f.write_text("original")
        save_snapshot(f)
        commit_operation("my op")
        f.write_text("changed")
        monkeypatch.setattr("builtins.input", lambda _: "1")
        run_undo()
        assert f.read_text() == "original"
        out = capsys.readouterr().out
        assert "my op" in out

    def test_interactive_empty_defaults_to_1(self, tmp_path, monkeypatch):
        from core.undo import save_snapshot, commit_operation, run_undo
        f = tmp_path / "test.md"
        f.write_text("original")
        save_snapshot(f)
        commit_operation("op")
        f.write_text("changed")
        monkeypatch.setattr("builtins.input", lambda _: "")
        run_undo()
        assert f.read_text() == "original"


# ── Integration with agenda ──────────────────────────────────────────────────

def _strip_emoji(name: str) -> str:
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


@pytest.fixture()
def projects_dir(tmp_path, monkeypatch):
    type_dir = tmp_path / "💻software"
    type_dir.mkdir()
    monkeypatch.setattr("core.config.ORBIT_HOME", tmp_path)
    monkeypatch.setattr("core.config._ORBIT_JSON", tmp_path / "orbit.json")
    monkeypatch.setattr("core.log.PROJECTS_DIR", tmp_path)
    return type_dir


@pytest.fixture()
def proj(projects_dir):
    return _make_project(projects_dir, "💻test-project")


class TestUndoTaskAdd:

    def test_undo_task_add(self, proj, projects_dir):
        from core.agenda_cmds import run_task_add, _read_agenda
        from core.undo import commit_operation, run_undo
        run_task_add("test-project", "Undo me", date_val="2026-04-01")
        commit_operation("task add")
        data = _read_agenda(proj / "test-project-agenda.md")
        assert len(data["tasks"]) == 1
        run_undo(choice=1)
        data = _read_agenda(proj / "test-project-agenda.md")
        assert len(data["tasks"]) == 0

    def test_undo_task_done(self, proj, projects_dir):
        from core.agenda_cmds import run_task_add, run_task_done, _read_agenda
        from core.undo import commit_operation, run_undo
        run_task_add("test-project", "My task")
        commit_operation("task add")
        run_task_done("test-project", "My task")
        commit_operation("task done")
        data = _read_agenda(proj / "test-project-agenda.md")
        assert data["tasks"][0]["status"] == "done"
        run_undo(choice=1)
        data = _read_agenda(proj / "test-project-agenda.md")
        assert data["tasks"][0]["status"] == "pending"


class TestUndoEventAdd:

    def test_undo_event_add(self, proj, projects_dir):
        from core.agenda_cmds import run_ev_add, _read_agenda
        from core.undo import commit_operation, run_undo
        run_ev_add("test-project", "Meeting", "2026-04-15")
        commit_operation("ev add")
        data = _read_agenda(proj / "test-project-agenda.md")
        assert len(data["events"]) == 1
        run_undo(choice=1)
        data = _read_agenda(proj / "test-project-agenda.md")
        assert len(data["events"]) == 0

    def test_undo_event_drop(self, proj, projects_dir):
        from core.agenda_cmds import run_ev_add, run_ev_drop, _read_agenda
        from core.undo import commit_operation, run_undo
        run_ev_add("test-project", "Keep me", "2026-04-15")
        commit_operation("ev add")
        run_ev_drop("test-project", "Keep me", force=True)
        commit_operation("ev drop")
        data = _read_agenda(proj / "test-project-agenda.md")
        assert len(data["events"]) == 0
        run_undo(choice=1)
        data = _read_agenda(proj / "test-project-agenda.md")
        assert len(data["events"]) == 1
        assert data["events"][0]["desc"] == "Keep me"


class TestUndoHighlight:

    def test_undo_hl_add(self, proj, projects_dir):
        from core.highlights import run_hl_add, _read_highlights
        from core.undo import commit_operation, run_undo
        import core.highlights as hl
        # ORBIT_HOME already patched via projects_dir fixture
        run_hl_add("test-project", "Key result", hl_type="results")
        commit_operation("hl add")
        data = _read_highlights(proj / "test-project-highlights.md")
        assert len(data["sections"]["results"]) == 1
        run_undo(choice=1)
        data = _read_highlights(proj / "test-project-highlights.md")
        assert len(data["sections"].get("results", [])) == 0


class TestUndoLog:

    def test_undo_log_entry(self, proj, projects_dir):
        from core.log import add_entry
        from core.undo import commit_operation, run_undo
        logbook = proj / "test-project-logbook.md"
        original = logbook.read_text()
        add_entry("test-project", "Test entry", "apunte", path=None, fecha=None)
        commit_operation("log")
        assert logbook.read_text() != original
        run_undo(choice=1)
        assert logbook.read_text() == original


class TestUndoMilestone:

    def test_undo_ms_add(self, proj, projects_dir):
        from core.agenda_cmds import run_ms_add, _read_agenda
        from core.undo import commit_operation, run_undo
        run_ms_add("test-project", "Big goal", date_val="2026-06-01")
        commit_operation("ms add")
        data = _read_agenda(proj / "test-project-agenda.md")
        assert len(data["milestones"]) == 1
        run_undo(choice=1)
        data = _read_agenda(proj / "test-project-agenda.md")
        assert len(data["milestones"]) == 0

    def test_undo_ms_done(self, proj, projects_dir):
        from core.agenda_cmds import run_ms_add, run_ms_done, _read_agenda
        from core.undo import commit_operation, run_undo
        run_ms_add("test-project", "Release v1")
        commit_operation("ms add")
        run_ms_done("test-project", "Release")
        commit_operation("ms done")
        data = _read_agenda(proj / "test-project-agenda.md")
        assert data["milestones"][0]["status"] == "done"
        run_undo(choice=1)
        data = _read_agenda(proj / "test-project-agenda.md")
        assert data["milestones"][0]["status"] == "pending"


class TestUndoNote:

    def test_undo_note_create(self, proj, projects_dir, monkeypatch):
        import sys
        monkeypatch.setattr(sys, "stdin", open("/dev/null"))
        from core.notes import run_note_create
        import core.notes as nm
        # ORBIT_HOME already patched via projects_dir fixture
        from core.undo import commit_operation, run_undo
        run_note_create("test-project", "My note", open_after=False)
        commit_operation("note create")
        note = proj / "notes" / "my_note.md"
        assert note.exists()
        run_undo(choice=1)
        # Note file removed, logbook restored
        assert not note.exists()

    def test_undo_note_drop(self, proj, projects_dir, monkeypatch):
        import sys
        monkeypatch.setattr(sys, "stdin", open("/dev/null"))
        from core.notes import run_note_create, run_note_drop
        import core.notes as nm
        # ORBIT_HOME already patched via projects_dir fixture
        from core.undo import commit_operation, run_undo
        run_note_create("test-project", "Temp note", open_after=False)
        commit_operation("note create")
        note = proj / "notes" / "temp_note.md"
        assert note.exists()
        content_before = note.read_text()
        run_note_drop("test-project", "temp_note.md", force=True)
        commit_operation("note drop")
        assert not note.exists()
        run_undo(choice=1)
        assert note.exists()
        assert note.read_text() == content_before


class TestUndoTaskEdit:

    def test_undo_task_edit(self, proj, projects_dir):
        from core.agenda_cmds import run_task_add, run_task_edit, _read_agenda
        from core.undo import commit_operation, run_undo
        run_task_add("test-project", "Old name", date_val="2026-03-15")
        commit_operation("task add")
        run_task_edit("test-project", "Old name", new_text="New name",
                      new_date="2026-04-01")
        commit_operation("task edit")
        data = _read_agenda(proj / "test-project-agenda.md")
        assert data["tasks"][0]["desc"] == "New name"
        assert data["tasks"][0]["date"] == "2026-04-01"
        run_undo(choice=1)
        data = _read_agenda(proj / "test-project-agenda.md")
        assert data["tasks"][0]["desc"] == "Old name"
        assert data["tasks"][0]["date"] == "2026-03-15"


class TestUndoChain:
    """Test undoing multiple operations in sequence."""

    def test_three_operations_undo_all(self, proj, projects_dir):
        from core.agenda_cmds import run_task_add, run_ev_add, _read_agenda
        from core.highlights import run_hl_add, _read_highlights
        import core.highlights as hl
        # ORBIT_HOME already patched via projects_dir fixture
        from core.undo import commit_operation, run_undo, can_undo

        run_task_add("test-project", "Task A")
        commit_operation("task add")
        run_ev_add("test-project", "Event B", "2026-05-01")
        commit_operation("ev add")
        run_hl_add("test-project", "Highlight C", hl_type="ideas")
        commit_operation("hl add")

        # Undo highlight
        run_undo(choice=1)
        data_hl = _read_highlights(proj / "test-project-highlights.md")
        assert len(data_hl["sections"].get("ideas", [])) == 0

        # Undo event
        run_undo(choice=1)
        data = _read_agenda(proj / "test-project-agenda.md")
        assert len(data["events"]) == 0

        # Undo task
        run_undo(choice=1)
        data = _read_agenda(proj / "test-project-agenda.md")
        assert len(data["tasks"]) == 0

        assert not can_undo()

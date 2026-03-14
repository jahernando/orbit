"""Unit tests for core/highlights.py — Phase 4: hl add/drop/edit/list."""

import sys
from pathlib import Path
from typing import Optional

import pytest


# ── Helpers ────────────────────────────────────────────────────────────────────

def _base_name(dirname: str) -> str:
    """Strip leading emoji prefix from directory name."""
    import re
    return re.sub(r'^[\U00010000-\U0010ffff\u2600-\u27bf\ufe0f]+', '', dirname).lstrip()


def _make_project(pdir: Path, name: str = "💻test-project") -> Path:
    project_dir = pdir / name
    project_dir.mkdir()
    base = _base_name(name)
    (project_dir / f"{base}-project.md").write_text(
        f"# {name}\n- Tipo: 💻 Software\n- Estado: [auto]\n- Prioridad: media\n"
    )
    (project_dir / f"{base}-logbook.md").write_text(f"# Logbook — {name}\n\n")
    (project_dir / f"{base}-highlights.md").write_text(
        f"# Highlights — {name}\n\n<!-- Secciones disponibles ... -->\n"
    )
    (project_dir / f"{base}-agenda.md").write_text(f"# Agenda — {name}\n\n")
    (project_dir / "notes").mkdir()
    return project_dir


def _hl_text(project_dir: Path) -> str:
    base = _base_name(project_dir.name)
    return (project_dir / f"{base}-highlights.md").read_text()


def _log_text(project_dir: Path) -> str:
    base = _base_name(project_dir.name)
    return (project_dir / f"{base}-logbook.md").read_text()


# ── Fixtures ───────────────────────────────────────────────────────────────────

@pytest.fixture()
def projects_dir(tmp_path, monkeypatch):
    pdir = tmp_path / "proyectos"
    pdir.mkdir()
    import core.highlights as hl
    import core.project as cp
    import core.log as cl
    monkeypatch.setattr(hl, "PROJECTS_DIR", pdir)
    monkeypatch.setattr(cp, "PROJECTS_DIR", pdir)
    monkeypatch.setattr(cl, "PROJECTS_DIR", pdir)
    return pdir


@pytest.fixture()
def proj(projects_dir):
    return _make_project(projects_dir)


# ══════════════════════════════════════════════════════════════════════════════
# _parse_item_line / _format_item
# ══════════════════════════════════════════════════════════════════════════════

class TestItemParsing:
    def test_plain_text(self):
        from core.highlights import _parse_item_line
        item = _parse_item_line("- Some text")
        assert item["text"] == "Some text"
        assert item["link"] is None

    def test_linked_item(self):
        from core.highlights import _parse_item_line
        item = _parse_item_line("- [Paper title](https://example.com/paper)")
        assert item["text"] == "Paper title"
        assert item["link"] == "https://example.com/paper"

    def test_linked_local_file(self):
        from core.highlights import _parse_item_line
        item = _parse_item_line("- [My result](./notes/result.md)")
        assert item["link"] == "./notes/result.md"

    def test_non_item_returns_none(self):
        from core.highlights import _parse_item_line
        assert _parse_item_line("## 📎 Referencias") is None
        assert _parse_item_line("") is None
        assert _parse_item_line("# Title") is None

    def test_format_plain(self):
        from core.highlights import _format_item
        assert _format_item("My idea") == "- My idea"

    def test_format_with_link(self):
        from core.highlights import _format_item
        assert _format_item("Paper", "https://x.com") == "- [Paper](https://x.com)"

    def test_roundtrip_plain(self):
        from core.highlights import _parse_item_line, _format_item
        line = "- Energy resolution 2.3%"
        item = _parse_item_line(line)
        assert _format_item(item["text"], item["link"]) == line

    def test_roundtrip_linked(self):
        from core.highlights import _parse_item_line, _format_item
        line = "- [González 2024](./refs/gonzalez2024.pdf)"
        item = _parse_item_line(line)
        assert _format_item(item["text"], item["link"]) == line


# ══════════════════════════════════════════════════════════════════════════════
# _read_highlights / _write_highlights
# ══════════════════════════════════════════════════════════════════════════════

class TestHighlightsIO:
    def test_empty_file(self, proj):
        from core.highlights import _read_highlights
        data = _read_highlights(proj / "test-project-highlights.md")
        assert data["sections"]["refs"]      == []
        assert data["sections"]["ideas"]     == []
        assert data["sections"]["decisions"] == []

    def test_missing_file(self, proj):
        from core.highlights import _read_highlights
        data = _read_highlights(proj / "nonexistent.md")
        assert all(v == [] for v in data["sections"].values())

    def test_write_and_read_refs(self, proj):
        from core.highlights import _read_highlights, _write_highlights
        data = _read_highlights(proj / "test-project-highlights.md")
        data["sections"]["refs"].append({"text": "González 2024",
                                          "link": "./refs/g.pdf", "note": None})
        _write_highlights(proj / "test-project-highlights.md", data)
        data2 = _read_highlights(proj / "test-project-highlights.md")
        assert len(data2["sections"]["refs"]) == 1
        assert data2["sections"]["refs"][0]["text"] == "González 2024"

    def test_write_preserves_header(self, proj):
        from core.highlights import _read_highlights, _write_highlights
        data = _read_highlights(proj / "test-project-highlights.md")
        data["sections"]["ideas"].append({"text": "Idea X", "link": None, "note": None})
        _write_highlights(proj / "test-project-highlights.md", data)
        text = _hl_text(proj)
        assert text.startswith("# Highlights")

    def test_write_multiple_sections(self, proj):
        from core.highlights import _read_highlights, _write_highlights
        data = _read_highlights(proj / "test-project-highlights.md")
        data["sections"]["refs"].append({"text": "Ref A", "link": None, "note": None})
        data["sections"]["results"].append({"text": "Result B", "link": None, "note": None})
        data["sections"]["decisions"].append({"text": "Decision C", "link": None, "note": None})
        _write_highlights(proj / "test-project-highlights.md", data)
        text = _hl_text(proj)
        assert "## 📎 Referencias" in text
        assert "## 📊 Resultados"  in text
        assert "## 📌 Decisiones"  in text

    def test_sections_ordered_by_map(self, proj):
        """Sections appear in SECTION_MAP order, not insertion order."""
        from core.highlights import _read_highlights, _write_highlights, SECTION_MAP
        data = _read_highlights(proj / "test-project-highlights.md")
        data["sections"]["ideas"].append({"text": "I", "link": None, "note": None})
        data["sections"]["refs"].append({"text": "R", "link": None, "note": None})
        _write_highlights(proj / "test-project-highlights.md", data)
        text = _hl_text(proj)
        assert text.index("Referencias") < text.index("Ideas")

    def test_roundtrip_complex(self, proj):
        from core.highlights import _read_highlights, _write_highlights
        data = _read_highlights(proj / "test-project-highlights.md")
        data["sections"]["refs"] = [
            {"text": "Paper A", "link": "https://a.com", "note": None},
            {"text": "Book B",  "link": None,            "note": None},
        ]
        data["sections"]["decisions"] = [
            {"text": "Use relative calibration", "link": None, "note": None},
        ]
        _write_highlights(proj / "test-project-highlights.md", data)
        data2 = _read_highlights(proj / "test-project-highlights.md")
        assert len(data2["sections"]["refs"])      == 2
        assert len(data2["sections"]["decisions"]) == 1
        assert data2["sections"]["refs"][0]["link"] == "https://a.com"


# ══════════════════════════════════════════════════════════════════════════════
# run_hl_add
# ══════════════════════════════════════════════════════════════════════════════

class TestHlAdd:
    def test_add_plain(self, proj, projects_dir, capsys):
        from core.highlights import run_hl_add, _read_highlights
        rc = run_hl_add("test-project", "Great idea", "ideas")
        assert rc == 0
        data = _read_highlights(proj / "test-project-highlights.md")
        assert data["sections"]["ideas"][0]["text"] == "Great idea"
        assert data["sections"]["ideas"][0]["link"] is None

    def test_add_with_link(self, proj, projects_dir):
        from core.highlights import run_hl_add, _read_highlights
        run_hl_add("test-project", "González 2024", "refs", link="./refs/g.pdf")
        data = _read_highlights(proj / "test-project-highlights.md")
        assert data["sections"]["refs"][0]["link"] == "./refs/g.pdf"

    def test_add_output(self, proj, projects_dir, capsys):
        from core.highlights import run_hl_add
        run_hl_add("test-project", "My result", "results")
        assert "My result" in capsys.readouterr().out

    def test_invalid_type(self, proj, projects_dir, capsys):
        from core.highlights import run_hl_add
        rc = run_hl_add("test-project", "Something", "invalid")
        assert rc == 1
        assert "no válido" in capsys.readouterr().out

    def test_project_not_found(self, projects_dir, capsys):
        from core.highlights import run_hl_add
        rc = run_hl_add("nonexistent", "text", "ideas")
        assert rc == 1

    def test_multiple_items_same_section(self, proj, projects_dir):
        from core.highlights import run_hl_add, _read_highlights
        run_hl_add("test-project", "Idea A", "ideas")
        run_hl_add("test-project", "Idea B", "ideas")
        data = _read_highlights(proj / "test-project-highlights.md")
        assert len(data["sections"]["ideas"]) == 2

    def test_all_types_valid(self, proj, projects_dir):
        from core.highlights import run_hl_add, VALID_TYPES
        for t in VALID_TYPES:
            rc = run_hl_add("test-project", f"Item for {t}", t)
            assert rc == 0

    def test_creates_highlights_if_missing(self, proj, projects_dir):
        from core.highlights import run_hl_add, _read_highlights
        (proj / "test-project-highlights.md").unlink()
        rc = run_hl_add("test-project", "Decision X", "decisions")
        assert rc == 0
        data = _read_highlights(proj / "test-project-highlights.md")
        assert data["sections"]["decisions"][0]["text"] == "Decision X"


# ══════════════════════════════════════════════════════════════════════════════
# run_hl_drop
# ══════════════════════════════════════════════════════════════════════════════

class TestHlDrop:
    def test_drop_by_text(self, proj, projects_dir, capsys):
        from core.highlights import run_hl_add, run_hl_drop, _read_highlights
        run_hl_add("test-project", "To remove", "ideas")
        rc = run_hl_drop("test-project", "remove", force=True)
        assert rc == 0
        data = _read_highlights(proj / "test-project-highlights.md")
        assert data["sections"]["ideas"] == []

    def test_drop_writes_logbook(self, proj, projects_dir):
        from core.highlights import run_hl_add, run_hl_drop
        run_hl_add("test-project", "Old reference", "refs")
        run_hl_drop("test-project", "Old reference", force=True)
        log = _log_text(proj)
        assert "[borrada] Highlight: Old reference" in log
        assert "[O]" in log

    def test_drop_linked_item_logbook(self, proj, projects_dir):
        from core.highlights import run_hl_add, run_hl_drop
        run_hl_add("test-project", "Paper A", "refs", link="https://example.com")
        run_hl_drop("test-project", "Paper A", force=True)
        log = _log_text(proj)
        assert "[borrada] Highlight:" in log
        assert "Paper A" in log

    def test_drop_not_found(self, proj, projects_dir, capsys):
        from core.highlights import run_hl_add, run_hl_drop
        run_hl_add("test-project", "Existing item", "ideas")
        rc = run_hl_drop("test-project", "ghost", force=True)
        assert rc == 1
        assert "no se encontró" in capsys.readouterr().out

    def test_drop_with_type_filter(self, proj, projects_dir, capsys):
        from core.highlights import run_hl_add, run_hl_drop, _read_highlights
        run_hl_add("test-project", "Keep this", "refs")
        run_hl_add("test-project", "Drop this", "ideas")
        rc = run_hl_drop("test-project", "Drop", hl_type="ideas", force=True)
        assert rc == 0
        data = _read_highlights(proj / "test-project-highlights.md")
        assert data["sections"]["refs"][0]["text"] == "Keep this"
        assert data["sections"]["ideas"] == []

    def test_drop_no_highlights_available(self, proj, projects_dir, capsys):
        from core.highlights import run_hl_drop
        rc = run_hl_drop("test-project", "nothing", force=True)
        assert rc == 1

    def test_drop_interactive_no_tty(self, proj, projects_dir, monkeypatch):
        from core.highlights import run_hl_add, run_hl_drop
        run_hl_add("test-project", "Item", "ideas")
        monkeypatch.setattr(sys, "stdin", open("/dev/null"))
        rc = run_hl_drop("test-project", None, force=True)
        assert rc == 1   # no selection made without TTY


# ══════════════════════════════════════════════════════════════════════════════
# run_hl_edit
# ══════════════════════════════════════════════════════════════════════════════

class TestHlEdit:
    def test_edit_text(self, proj, projects_dir):
        from core.highlights import run_hl_add, run_hl_edit, _read_highlights
        run_hl_add("test-project", "Old title", "refs")
        rc = run_hl_edit("test-project", "Old title", new_text="New title")
        assert rc == 0
        data = _read_highlights(proj / "test-project-highlights.md")
        assert data["sections"]["refs"][0]["text"] == "New title"

    def test_edit_add_link(self, proj, projects_dir):
        from core.highlights import run_hl_add, run_hl_edit, _read_highlights
        run_hl_add("test-project", "My result", "results")
        run_hl_edit("test-project", "My result", new_link="https://example.com")
        data = _read_highlights(proj / "test-project-highlights.md")
        assert data["sections"]["results"][0]["link"] == "https://example.com"

    def test_edit_remove_link(self, proj, projects_dir):
        from core.highlights import run_hl_add, run_hl_edit, _read_highlights
        run_hl_add("test-project", "Paper", "refs", link="https://old.com")
        run_hl_edit("test-project", "Paper", new_link="none")
        data = _read_highlights(proj / "test-project-highlights.md")
        assert data["sections"]["refs"][0]["link"] is None

    def test_edit_opens_editor_when_no_changes(self, proj, projects_dir, monkeypatch):
        """When no new_text/new_link given, open_file is called."""
        from core.highlights import run_hl_edit
        opened = []
        monkeypatch.setattr("core.highlights.open_file",
                            lambda path, editor: opened.append(path))
        run_hl_add = __import__("core.highlights", fromlist=["run_hl_add"]).run_hl_add
        run_hl_add("test-project", "Item", "ideas")
        rc = run_hl_edit("test-project", None)
        assert rc == 0
        assert len(opened) == 1
        assert opened[0].name == "test-project-highlights.md"

    def test_edit_not_found(self, proj, projects_dir, capsys):
        from core.highlights import run_hl_add, run_hl_edit
        run_hl_add("test-project", "Real item", "ideas")
        rc = run_hl_edit("test-project", "ghost", new_text="whatever")
        assert rc == 1

    def test_edit_with_type_filter(self, proj, projects_dir):
        from core.highlights import run_hl_add, run_hl_edit, _read_highlights
        run_hl_add("test-project", "Same name", "refs")
        run_hl_add("test-project", "Same name", "ideas")
        # Edit only the refs one
        rc = run_hl_edit("test-project", "Same name", new_text="Updated ref",
                         hl_type="refs")
        assert rc == 0
        data = _read_highlights(proj / "test-project-highlights.md")
        assert data["sections"]["refs"][0]["text"]  == "Updated ref"
        assert data["sections"]["ideas"][0]["text"] == "Same name"


# ══════════════════════════════════════════════════════════════════════════════
# run_hl_list
# ══════════════════════════════════════════════════════════════════════════════

class TestHlList:
    def test_list_all(self, proj, projects_dir, capsys):
        from core.highlights import run_hl_add, run_hl_list
        run_hl_add("test-project", "Idea A", "ideas")
        run_hl_add("test-project", "Ref B",  "refs")
        capsys.readouterr()
        rc = run_hl_list()
        assert rc == 0
        out = capsys.readouterr().out
        assert "Idea A" in out
        assert "Ref B"  in out

    def test_list_by_type(self, proj, projects_dir, capsys):
        from core.highlights import run_hl_add, run_hl_list
        run_hl_add("test-project", "My idea",  "ideas")
        run_hl_add("test-project", "My result", "results")
        capsys.readouterr()
        run_hl_list(hl_type="ideas")
        out = capsys.readouterr().out
        assert "My idea"   in out
        assert "My result" not in out

    def test_list_empty(self, proj, projects_dir, capsys):
        from core.highlights import run_hl_list
        rc = run_hl_list()
        assert rc == 0
        assert "No hay highlights" in capsys.readouterr().out

    def test_list_specific_project(self, proj, projects_dir, capsys):
        from core.highlights import run_hl_add, run_hl_list
        run_hl_add("test-project", "Decision Z", "decisions")
        capsys.readouterr()
        run_hl_list(project="test-project")
        assert "Decision Z" in capsys.readouterr().out

    def test_list_shows_links(self, proj, projects_dir, capsys):
        from core.highlights import run_hl_add, run_hl_list
        run_hl_add("test-project", "Paper", "refs", link="https://example.com")
        capsys.readouterr()
        run_hl_list()
        out = capsys.readouterr().out
        assert "Paper" in out
        assert "https://example.com" in out

    def test_list_invalid_type(self, proj, projects_dir, capsys):
        from core.highlights import run_hl_list
        rc = run_hl_list(hl_type="invalid")
        assert rc == 1

    def test_list_shows_section_headings(self, proj, projects_dir, capsys):
        from core.highlights import run_hl_add, run_hl_list
        run_hl_add("test-project", "Ref X", "refs")
        capsys.readouterr()
        run_hl_list()
        out = capsys.readouterr().out
        assert "Referencias" in out

    def test_list_multiple_projects(self, projects_dir, capsys):
        from core.highlights import run_hl_add, run_hl_list
        p1 = _make_project(projects_dir, "💻proj-one")
        p2 = _make_project(projects_dir, "💻proj-two")
        run_hl_add("proj-one", "Idea one", "ideas")
        run_hl_add("proj-two", "Idea two", "ideas")
        capsys.readouterr()
        run_hl_list()
        out = capsys.readouterr().out
        assert "Idea one" in out
        assert "Idea two" in out

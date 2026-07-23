"""Unit tests for core/highlights.py — unified orbit-item format (ADR-045)."""

import sys
from pathlib import Path
from typing import Optional

import pytest


# ── Helpers ────────────────────────────────────────────────────────────────────

def _base_name(dirname: str) -> str:
    """Strip leading emoji prefix from directory name."""
    import re
    return re.sub(r'^[\U00010000-\U0010ffff☀-➿️]+', '', dirname).lstrip()


def _make_project(type_dir: Path, name: str = "💻test-project") -> Path:
    project_dir = type_dir / name
    project_dir.mkdir(parents=True, exist_ok=True)
    base = _base_name(name)
    (project_dir / f"{base}-project.md").write_text(
        f"# {name}\n- Tipo: 💻 Software\n- Estado: [auto]\n- Prioridad: media\n"
    )
    (project_dir / f"{base}-logbook.md").write_text(f"# Logbook — {name}\n\n")
    (project_dir / f"{base}-highlights.md").write_text(
        f"# Highlights — {name}\n\n<!-- Lista plana de orbit-items -->\n"
    )
    (project_dir / f"{base}-agenda.md").write_text(f"# Agenda — {name}\n\n")
    (project_dir / "notes").mkdir(exist_ok=True)
    return project_dir


def _hl_text(project_dir: Path) -> str:
    base = _base_name(project_dir.name)
    return (project_dir / f"{base}-highlights.md").read_text()


def _log_text(project_dir: Path) -> str:
    base = _base_name(project_dir.name)
    return (project_dir / f"{base}-logbook.md").read_text()


def _items(project_dir: Path, hl_type: Optional[str] = None) -> list:
    """Return the parsed items of a project's highlights, optionally by type."""
    from core.highlights import _read_highlights
    from core.log import resolve_file
    data = _read_highlights(resolve_file(project_dir, "highlights"))
    return [it for it in data["items"]
            if hl_type is None or it["type"] == hl_type]


# ── Fixtures ───────────────────────────────────────────────────────────────────

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
    return _make_project(projects_dir)


# ══════════════════════════════════════════════════════════════════════════════
# _parse_hl_header / _format_hl_item
# ══════════════════════════════════════════════════════════════════════════════

class TestItemParsing:
    def test_plain_text(self):
        from core.highlights import _parse_hl_header
        item = _parse_hl_header("- 💡 Some text #idea")
        assert item["type"] == "ideas"
        assert item["text"] == "Some text"
        assert item["link"] is None
        assert item["tags"] == []

    def test_linked_item(self):
        from core.highlights import _parse_hl_header
        item = _parse_hl_header(
            "- 📎 [Paper title](https://example.com/paper) #referencia")
        assert item["type"] == "refs"
        assert item["text"] == "Paper title"
        assert item["link"] == "https://example.com/paper"

    def test_linked_local_file(self):
        from core.highlights import _parse_hl_header
        item = _parse_hl_header("- 📎 [My result](./notes/result.md) #referencia")
        assert item["link"] == "./notes/result.md"

    def test_free_tags_after_primary(self):
        from core.highlights import _parse_hl_header
        item = _parse_hl_header("- 💡 Idea #idea #física #urgente")
        assert item["text"] == "Idea"
        assert item["tags"] == ["#física", "#urgente"]

    def test_unrecognized_emoji_returns_none(self):
        from core.highlights import _parse_hl_header
        assert _parse_hl_header("- ⚡ Something #foo") is None

    def test_format_plain(self):
        from core.highlights import _format_hl_item
        item = {"type": "ideas", "text": "My idea", "link": None, "tags": []}
        assert _format_hl_item(item) == "- 💡 My idea #idea"

    def test_format_with_link(self):
        from core.highlights import _format_hl_item
        item = {"type": "refs", "text": "Paper", "link": "https://x.com", "tags": []}
        assert _format_hl_item(item) == "- 📎 [Paper](https://x.com) #referencia"

    def test_format_with_free_tags(self):
        from core.highlights import _format_hl_item
        item = {"type": "ideas", "text": "Idea", "link": None,
                "tags": ["#física"]}
        assert _format_hl_item(item) == "- 💡 Idea #idea #física"

    def test_format_with_note(self):
        from core.highlights import _format_hl_item
        item = {"type": "ideas", "text": "Idea", "link": None, "tags": [],
                "note": "línea uno\nlínea dos"}
        assert _format_hl_item(item) == "- 💡 Idea #idea\n  línea uno\n  línea dos"

    def test_roundtrip_plain(self):
        from core.highlights import _parse_hl_header, _format_hl_item
        line = "- 📊 Energy resolution 2.3% #resultado"
        assert _format_hl_item(_parse_hl_header(line)) == line

    def test_roundtrip_linked(self):
        from core.highlights import _parse_hl_header, _format_hl_item
        line = "- 📎 [González 2024](./refs/gonzalez2024.pdf) #referencia"
        assert _format_hl_item(_parse_hl_header(line)) == line


# ══════════════════════════════════════════════════════════════════════════════
# _read_highlights / _write_highlights
# ══════════════════════════════════════════════════════════════════════════════

class TestHighlightsIO:
    def test_empty_file(self, proj):
        assert _items(proj) == []

    def test_missing_file(self, proj):
        from core.highlights import _read_highlights
        data = _read_highlights(proj / "nonexistent.md")
        assert data["items"] == []

    def test_write_and_read_refs(self, proj):
        from core.highlights import _read_highlights, _write_highlights
        path = proj / "test-project-highlights.md"
        data = _read_highlights(path)
        data["items"].append({"type": "refs", "text": "González 2024",
                              "link": "./refs/g.pdf", "note": None, "tags": []})
        _write_highlights(path, data)
        again = _items(proj, "refs")
        assert len(again) == 1
        assert again[0]["text"] == "González 2024"

    def test_write_preserves_header(self, proj):
        from core.highlights import _read_highlights, _write_highlights
        path = proj / "test-project-highlights.md"
        data = _read_highlights(path)
        data["items"].append({"type": "ideas", "text": "Idea X",
                              "link": None, "note": None, "tags": []})
        _write_highlights(path, data)
        assert _hl_text(proj).startswith("# Highlights")

    def test_write_is_flat_no_sections(self, proj):
        from core.highlights import _read_highlights, _write_highlights
        path = proj / "test-project-highlights.md"
        data = _read_highlights(path)
        for typ, text in [("refs", "Ref A"), ("results", "Result B"),
                          ("decisions", "Decision C")]:
            data["items"].append({"type": typ, "text": text,
                                  "link": None, "note": None, "tags": []})
        _write_highlights(path, data)
        text = _hl_text(proj)
        assert "- 📎 Ref A #referencia" in text
        assert "- 📊 Result B #resultado" in text
        assert "- 📌 Decision C #decisión" in text
        assert "## " not in text          # no section headings anymore

    def test_insertion_order_preserved(self, proj):
        """Flat list keeps insertion order (no per-type reordering)."""
        from core.highlights import run_hl_add
        run_hl_add("test-project", "Idea first", "ideas")
        run_hl_add("test-project", "Ref second", "refs")
        text = _hl_text(proj)
        assert text.index("Idea first") < text.index("Ref second")

    def test_note_roundtrip(self, proj):
        from core.highlights import _read_highlights, _write_highlights
        path = proj / "test-project-highlights.md"
        data = _read_highlights(path)
        data["items"].append({"type": "ideas", "text": "Idea", "link": None,
                              "note": "detalle importante", "tags": []})
        _write_highlights(path, data)
        again = _items(proj, "ideas")
        assert again[0]["note"] == "detalle importante"


# ══════════════════════════════════════════════════════════════════════════════
# Lazy migration of legacy `## Section` files
# ══════════════════════════════════════════════════════════════════════════════

class TestLegacyMigration:
    def test_reads_legacy_sections(self, proj):
        from core.highlights import _read_highlights
        path = proj / "test-project-highlights.md"
        path.write_text(
            "# Highlights — test\n\n"
            "## 📚 Referencias\n"
            "- [González 2024](./refs/g.pdf)\n\n"
            "## 🏛️ Decisiones\n"
            "- Usar calibración relativa\n"
        )
        data = _read_highlights(path)
        refs = [it for it in data["items"] if it["type"] == "refs"]
        decs = [it for it in data["items"] if it["type"] == "decisions"]
        assert refs[0]["text"] == "González 2024"
        assert refs[0]["link"] == "./refs/g.pdf"
        assert decs[0]["text"] == "Usar calibración relativa"

    def test_migrates_on_write(self, proj):
        """A legacy file is rewritten flat on the next mutation."""
        from core.highlights import run_hl_add
        path = proj / "test-project-highlights.md"
        path.write_text(
            "# Highlights — test\n\n"
            "## 📊 Evaluaciones\n"
            "- Estado saludable\n"
        )
        run_hl_add("test-project", "New idea", "ideas")
        text = path.read_text()
        assert "## " not in text                       # sections gone
        assert "- 🔍 Estado saludable #evaluación" in text   # old item migrated
        assert "- 💡 New idea #idea" in text                 # new item appended


# ══════════════════════════════════════════════════════════════════════════════
# run_hl_add
# ══════════════════════════════════════════════════════════════════════════════

class TestHlAdd:
    def test_add_plain(self, proj, projects_dir, capsys):
        from core.highlights import run_hl_add
        rc = run_hl_add("test-project", "Great idea", "ideas")
        assert rc == 0
        items = _items(proj, "ideas")
        assert items[0]["text"] == "Great idea"
        assert items[0]["link"] is None

    def test_add_with_link(self, proj, projects_dir):
        from core.highlights import run_hl_add
        run_hl_add("test-project", "González 2024", "refs", link="./refs/g.pdf")
        assert _items(proj, "refs")[0]["link"] == "./refs/g.pdf"

    def test_add_output(self, proj, projects_dir, capsys):
        from core.highlights import run_hl_add
        run_hl_add("test-project", "My result", "results")
        out = capsys.readouterr().out
        assert "My result" in out
        assert "📊" in out            # echoes the serialized orbit-item

    def test_invalid_type(self, proj, projects_dir, capsys):
        from core.highlights import run_hl_add
        rc = run_hl_add("test-project", "Something", "invalid")
        assert rc == 1
        assert "no válido" in capsys.readouterr().out

    def test_project_not_found(self, projects_dir, capsys):
        from core.highlights import run_hl_add
        rc = run_hl_add("nonexistent", "text", "ideas")
        assert rc == 1

    def test_multiple_items_same_type(self, proj, projects_dir):
        from core.highlights import run_hl_add
        run_hl_add("test-project", "Idea A", "ideas")
        run_hl_add("test-project", "Idea B", "ideas")
        assert len(_items(proj, "ideas")) == 2

    def test_all_types_valid(self, proj, projects_dir):
        from core.highlights import run_hl_add, VALID_TYPES
        for t in VALID_TYPES:
            rc = run_hl_add("test-project", f"Item for {t}", t)
            assert rc == 0

    def test_creates_highlights_if_missing(self, proj, projects_dir):
        from core.highlights import run_hl_add
        (proj / "test-project-highlights.md").unlink()
        rc = run_hl_add("test-project", "Decision X", "decisions")
        assert rc == 0
        assert _items(proj, "decisions")[0]["text"] == "Decision X"

    def test_add_writes_logbook_with_headline(self, proj, projects_dir):
        from core.highlights import run_hl_add
        run_hl_add("test-project", "Great idea", "ideas")
        log = _log_text(proj)
        assert "Highlight: Great idea" in log
        assert "#idea #headline" in log
        assert "[O]" in log

    def test_add_log_maps_type_refs_to_referencia(self, proj, projects_dir):
        from core.highlights import run_hl_add
        run_hl_add("test-project", "Paper Z", "refs")
        assert "#referencia #headline" in _log_text(proj)

    def test_add_log_maps_all_types(self, proj, projects_dir):
        from core.highlights import run_hl_add
        cases = [
            ("refs",      "#referencia"),
            ("results",   "#resultado"),
            ("decisions", "#decision"),
            ("ideas",     "#idea"),
            ("evals",     "#evaluacion"),
            ("plans",     "#plan"),
            ("contacts",  "#apunte"),
        ]
        for hl_type, _ in cases:
            run_hl_add("test-project", f"item-{hl_type}", hl_type)
        log = _log_text(proj)
        for _, expected_tag in cases:
            assert f"{expected_tag} #headline" in log

    def test_add_with_url_link_in_log(self, proj, projects_dir):
        from core.highlights import run_hl_add
        run_hl_add("test-project", "Paper A", "refs",
                   link="https://example.com/paper")
        log = _log_text(proj)
        assert "[Highlight: Paper A](https://example.com/paper)" in log
        assert "#referencia #headline" in log

    def test_add_with_relative_file_link_in_log(self, proj, projects_dir):
        from core.highlights import run_hl_add
        run_hl_add("test-project", "Local note", "refs", link="./refs/x.pdf")
        assert "[Highlight: Local note](./refs/x.pdf)" in _log_text(proj)

    def test_add_without_link_no_link_in_log(self, proj, projects_dir):
        from core.highlights import run_hl_add
        run_hl_add("test-project", "Plain idea", "ideas")
        assert "Highlight: Plain idea #idea #headline" in _log_text(proj)


# ══════════════════════════════════════════════════════════════════════════════
# run_hl_drop
# ══════════════════════════════════════════════════════════════════════════════

class TestHlDrop:
    def test_drop_by_text(self, proj, projects_dir, capsys):
        from core.highlights import run_hl_add, run_hl_drop
        run_hl_add("test-project", "To remove", "ideas")
        rc = run_hl_drop("test-project", "remove", force=True)
        assert rc == 0
        assert _items(proj, "ideas") == []

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
        from core.highlights import run_hl_add, run_hl_drop
        run_hl_add("test-project", "Keep this", "refs")
        run_hl_add("test-project", "Drop this", "ideas")
        rc = run_hl_drop("test-project", "Drop", hl_type="ideas", force=True)
        assert rc == 0
        assert _items(proj, "refs")[0]["text"] == "Keep this"
        assert _items(proj, "ideas") == []

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
        from core.highlights import run_hl_add, run_hl_edit
        run_hl_add("test-project", "Old title", "refs")
        rc = run_hl_edit("test-project", "Old title", new_text="New title")
        assert rc == 0
        assert _items(proj, "refs")[0]["text"] == "New title"

    def test_edit_add_link(self, proj, projects_dir):
        from core.highlights import run_hl_add, run_hl_edit
        run_hl_add("test-project", "My result", "results")
        run_hl_edit("test-project", "My result", new_link="https://example.com")
        assert _items(proj, "results")[0]["link"] == "https://example.com"

    def test_edit_remove_link(self, proj, projects_dir):
        from core.highlights import run_hl_add, run_hl_edit
        run_hl_add("test-project", "Paper", "refs", link="https://old.com")
        run_hl_edit("test-project", "Paper", new_link="none")
        assert _items(proj, "refs")[0]["link"] is None

    def test_edit_opens_editor_when_no_changes(self, proj, projects_dir, monkeypatch):
        """When no new_text/new_link given, open_file is called."""
        from core.highlights import run_hl_add, run_hl_edit
        opened = []
        monkeypatch.setattr("core.highlights.open_file",
                            lambda path, editor: opened.append(path))
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
        from core.highlights import run_hl_add, run_hl_edit
        run_hl_add("test-project", "Same name", "refs")
        run_hl_add("test-project", "Same name", "ideas")
        rc = run_hl_edit("test-project", "Same name", new_text="Updated ref",
                         hl_type="refs")
        assert rc == 0
        assert _items(proj, "refs")[0]["text"]  == "Updated ref"
        assert _items(proj, "ideas")[0]["text"] == "Same name"


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

    def test_list_shows_type_emoji(self, proj, projects_dir, capsys):
        from core.highlights import run_hl_add, run_hl_list
        run_hl_add("test-project", "Ref X", "refs")
        capsys.readouterr()
        run_hl_list()
        assert "📎" in capsys.readouterr().out

    def test_list_multiple_projects(self, projects_dir, capsys):
        from core.highlights import run_hl_add, run_hl_list
        _make_project(projects_dir, "💻proj-one")
        _make_project(projects_dir, "💻proj-two")
        run_hl_add("proj-one", "Idea one", "ideas")
        run_hl_add("proj-two", "Idea two", "ideas")
        capsys.readouterr()
        run_hl_list()
        out = capsys.readouterr().out
        assert "Idea one" in out
        assert "Idea two" in out

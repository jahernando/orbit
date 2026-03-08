"""test_list_notes.py — tests for list_cmd, find_note and _search_notes.

Covers:
  - run_list_section: all refs, filter by project, filter by --entry, output to file
  - run_list_notes: listing, date extraction from filename, output to file
  - run_list_files: file listing, orphan detection
  - find_note: partial match, no match with suggestions, missing notes dir
  - _search_notes: keyword match, H1 included, ## headings excluded, no notes dir
"""

from pathlib import Path
from datetime import date

import pytest

from core.add import run_add, run_add_note, extract_section
from core.list_cmd import run_list_section, run_list_notes, run_list_files
from core.open import find_note
from core.search import _search_notes


TODAY = date.today().isoformat()


# ═══════════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════════

def _add_ref(project, title, entry="referencia", url="https://example.com"):
    run_add(project, title, entry, url=url, file_str=None,
            sync=False, open_after=False, editor="typora")


def _add_note(project, title, link=True, date_prefix=True, monkeypatch=None):
    if monkeypatch:
        monkeypatch.setattr("core.add.open_file", lambda p, e: 0)
    run_add_note(project, title, "apunte", file_str=None,
                 link=link, date_prefix=date_prefix,
                 open_after=False, editor="typora")


# ═══════════════════════════════════════════════════════════════════════════════
# run_list_section
# ═══════════════════════════════════════════════════════════════════════════════

class TestRunListSection:

    def test_list_refs_shows_entries(self, orbit_env, capsys):
        _add_ref("testproj", "González 2024")
        capsys.readouterr()
        rc = run_list_section(project=None, section="refs", entry=None,
                              output=None, open_after=False, editor="typora")
        assert rc == 0
        out = capsys.readouterr().out
        assert "González 2024" in out

    def test_list_refs_filter_by_project(self, orbit_env, capsys):
        _add_ref("testproj", "Referencia filtrada")
        capsys.readouterr()
        rc = run_list_section(project="testproj", section="refs", entry=None,
                              output=None, open_after=False, editor="typora")
        assert rc == 0
        out = capsys.readouterr().out
        assert "Referencia filtrada" in out

    def test_list_refs_filter_by_entry_type(self, orbit_env, capsys):
        _add_ref("testproj", "Paper oficial", entry="referencia")
        _add_ref("testproj", "Idea informal", entry="idea")
        capsys.readouterr()
        # Filter to only ideas (💡)
        rc = run_list_section(project=None, section="refs", entry="idea",
                              output=None, open_after=False, editor="typora")
        assert rc == 0
        out = capsys.readouterr().out
        assert "Idea informal" in out
        assert "Paper oficial" not in out

    def test_list_results(self, orbit_env, capsys):
        _add_ref("testproj", "σ/E = 2.3%", entry="resultado")
        capsys.readouterr()
        rc = run_list_section(project=None, section="results", entry=None,
                              output=None, open_after=False, editor="typora")
        assert rc == 0
        assert "σ/E = 2.3%" in capsys.readouterr().out

    def test_list_section_output_to_file(self, orbit_env, tmp_path):
        _add_ref("testproj", "Referencia para fichero")
        out_file = tmp_path / "out.md"
        run_list_section(project=None, section="refs", entry=None,
                         output=str(out_file), open_after=False, editor="typora")
        assert out_file.exists()
        assert "Referencia para fichero" in out_file.read_text()

    def test_list_empty_section_prints_message(self, orbit_env, capsys):
        # decisions section exists but is empty (placeholder only)
        run_list_section(project=None, section="decisions", entry=None,
                         output=None, open_after=False, editor="typora")
        out = capsys.readouterr().out
        assert "No hay entradas" in out


# ═══════════════════════════════════════════════════════════════════════════════
# run_list_notes
# ═══════════════════════════════════════════════════════════════════════════════

class TestRunListNotes:

    def test_list_notes_shows_note(self, orbit_env, monkeypatch, capsys):
        _add_note("testproj", "Análisis de fondo", monkeypatch=monkeypatch)
        capsys.readouterr()
        rc = run_list_notes(project=None, output=None,
                            open_after=False, editor="typora")
        assert rc == 0
        out = capsys.readouterr().out
        assert "analisis-de-fondo" in out.lower() or "análisis de fondo" in out.lower()

    def test_list_notes_extracts_date(self, orbit_env, monkeypatch, capsys):
        _add_note("testproj", "Nota con fecha", date_prefix=True,
                  monkeypatch=monkeypatch)
        capsys.readouterr()
        run_list_notes(project=None, output=None, open_after=False, editor="typora")
        out = capsys.readouterr().out
        # Date should appear in YYYY-MM-DD format
        assert TODAY in out

    def test_list_notes_no_notes(self, orbit_env, capsys):
        run_list_notes(project=None, output=None, open_after=False, editor="typora")
        out = capsys.readouterr().out
        assert "No hay notas" in out

    def test_list_notes_output_to_file(self, orbit_env, monkeypatch, tmp_path):
        _add_note("testproj", "Nota para fichero", monkeypatch=monkeypatch)
        out_file = tmp_path / "notes.md"
        run_list_notes(project=None, output=str(out_file),
                       open_after=False, editor="typora")
        assert out_file.exists()
        content = out_file.read_text()
        assert "NOTAS DE PROYECTO" in content


# ═══════════════════════════════════════════════════════════════════════════════
# run_list_files
# ═══════════════════════════════════════════════════════════════════════════════

class TestRunListFiles:

    def test_lists_file_in_references(self, orbit_env, tmp_path, capsys):
        src = tmp_path / "paper.pdf"
        src.write_bytes(b"%PDF fake")
        run_add("testproj", "Paper de prueba", "referencia",
                url=None, file_str=str(src), sync=False,
                open_after=False, editor="typora")
        capsys.readouterr()
        rc = run_list_files(project="testproj", output=None,
                            open_after=False, editor="typora")
        assert rc == 0
        out = capsys.readouterr().out
        assert "paper.pdf" in out

    def test_linked_file_not_marked_orphan(self, orbit_env, tmp_path, capsys):
        src = tmp_path / "linked.pdf"
        src.write_bytes(b"%PDF fake")
        run_add("testproj", "Fichero enlazado", "referencia",
                url=None, file_str=str(src), sync=False,
                open_after=False, editor="typora")
        capsys.readouterr()
        run_list_files(project="testproj", output=None,
                       open_after=False, editor="typora")
        out = capsys.readouterr().out
        assert "sin enlace" not in out

    def test_unlinked_file_marked_orphan(self, orbit_env, capsys):
        # Manually drop a file without linking it in proyecto.md
        refs_dir = orbit_env["proj_dir"] / "references"
        refs_dir.mkdir(exist_ok=True)
        (refs_dir / "huerfano.pdf").write_bytes(b"%PDF fake")
        capsys.readouterr()
        run_list_files(project="testproj", output=None,
                       open_after=False, editor="typora")
        out = capsys.readouterr().out
        assert "sin enlace" in out
        assert "huerfano.pdf" in out

    def test_no_files_prints_message(self, orbit_env, capsys):
        run_list_files(project="testproj", output=None,
                       open_after=False, editor="typora")
        out = capsys.readouterr().out
        assert "No hay ficheros" in out


# ═══════════════════════════════════════════════════════════════════════════════
# find_note
# ═══════════════════════════════════════════════════════════════════════════════

class TestFindNote:

    def _make_note(self, proj_dir, name="20260301_calibracion.md"):
        notes_dir = proj_dir / "notes"
        notes_dir.mkdir(exist_ok=True)
        p = notes_dir / name
        p.write_text(f"# {name}\n\nContenido.\n")
        return p

    def test_finds_by_partial_name(self, orbit_env):
        self._make_note(orbit_env["proj_dir"])
        result = find_note(orbit_env["proj_dir"], "calibracion")
        assert result is not None
        assert result.name == "20260301_calibracion.md"

    def test_case_insensitive(self, orbit_env):
        self._make_note(orbit_env["proj_dir"])
        result = find_note(orbit_env["proj_dir"], "CALIBRACION")
        assert result is not None

    def test_no_match_prints_suggestions(self, orbit_env, capsys):
        self._make_note(orbit_env["proj_dir"])
        result = find_note(orbit_env["proj_dir"], "inexistente")
        assert result is None
        out = capsys.readouterr().out
        assert "20260301_calibracion.md" in out

    def test_no_notes_dir_prints_error(self, orbit_env, capsys):
        result = find_note(orbit_env["proj_dir"], "algo")
        assert result is None
        out = capsys.readouterr().out
        assert "notes/" in out

    def test_empty_notes_dir_prints_message(self, orbit_env, capsys):
        (orbit_env["proj_dir"] / "notes").mkdir()
        result = find_note(orbit_env["proj_dir"], "algo")
        assert result is None
        out = capsys.readouterr().out
        assert "no hay notas" in out.lower()


# ═══════════════════════════════════════════════════════════════════════════════
# _search_notes
# ═══════════════════════════════════════════════════════════════════════════════

class TestSearchNotes:

    def _make_notes_dir(self, proj_dir):
        notes_dir = proj_dir / "notes"
        notes_dir.mkdir(exist_ok=True)
        return notes_dir

    def test_finds_keyword_in_body(self, orbit_env):
        notes_dir = self._make_notes_dir(orbit_env["proj_dir"])
        (notes_dir / "nota.md").write_text(
            "# Calibración\n\nLa calibración relativa es mejor.\n"
        )
        results = _search_notes(orbit_env["proj_dir"], ["calibración"], False, 0)
        assert len(results) == 1
        _, hits = results[0]
        assert any("calibración relativa" in h.lower() for h in hits)

    def test_h1_title_is_searched(self, orbit_env):
        """H1 heading (# Título) must be included in search results."""
        notes_dir = self._make_notes_dir(orbit_env["proj_dir"])
        (notes_dir / "nota.md").write_text(
            "# Fondo Cósmico\n\nTexto sin palabras clave.\n"
        )
        results = _search_notes(orbit_env["proj_dir"], ["fondo"], False, 0)
        assert len(results) == 1
        _, hits = results[0]
        assert any("Fondo Cósmico" in h for h in hits)

    def test_h2_headings_excluded(self, orbit_env):
        """## and deeper headings are structural noise, not content."""
        notes_dir = self._make_notes_dir(orbit_env["proj_dir"])
        (notes_dir / "nota.md").write_text(
            "# Título\n\n## Sección de métodos\n\nContenido aquí.\n"
        )
        results = _search_notes(orbit_env["proj_dir"], ["métodos"], False, 0)
        # "## Sección de métodos" should not appear in hits
        if results:
            _, hits = results[0]
            assert not any(h.startswith("##") for h in hits)

    def test_no_match_returns_empty(self, orbit_env):
        notes_dir = self._make_notes_dir(orbit_env["proj_dir"])
        (notes_dir / "nota.md").write_text("# Nota\n\nContenido irrelevante.\n")
        results = _search_notes(orbit_env["proj_dir"], ["termino_inexistente_xyz"], False, 0)
        assert results == []

    def test_no_notes_dir_returns_empty(self, orbit_env):
        results = _search_notes(orbit_env["proj_dir"], ["cualquier cosa"], False, 0)
        assert results == []

    def test_multiple_notes_searched(self, orbit_env):
        notes_dir = self._make_notes_dir(orbit_env["proj_dir"])
        (notes_dir / "nota_a.md").write_text("# A\n\nEnergia en detecto.\n")
        (notes_dir / "nota_b.md").write_text("# B\n\nEnergia en simulacion.\n")
        results = _search_notes(orbit_env["proj_dir"], ["energia"], False, 0)
        assert len(results) == 2

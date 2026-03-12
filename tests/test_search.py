"""test_search.py — tests for full-text search across project logbooks and notes."""

from pathlib import Path

import pytest

from core.search import (
    _matches, _in_date_range,
    _search_logbook, _search_file, run_search,
)


# ═══════════════════════════════════════════════════════════════════════════════
# Pure helpers
# ═══════════════════════════════════════════════════════════════════════════════

class TestMatches:

    def test_and_mode_all_must_match(self):
        assert _matches("el fit no converge #problema", ["fit", "converge"], any_mode=False)

    def test_and_mode_partial_fail(self):
        assert not _matches("el fit funciona", ["fit", "converge"], any_mode=False)

    def test_or_mode_one_enough(self):
        assert _matches("el fit funciona", ["fit", "converge"], any_mode=True)

    def test_or_mode_none_match(self):
        assert not _matches("nada relevante aquí", ["fit", "converge"], any_mode=True)

    def test_no_keywords_always_true(self):
        assert _matches("cualquier cosa", [], any_mode=False)

    def test_case_insensitive(self):
        assert _matches("Resultado: OK", ["resultado"], any_mode=False)


class TestInDateRange:

    def test_no_filter_always_true(self):
        assert _in_date_range("2026-03-01 algo #idea", None, None, None)

    def test_date_filter_prefix_match(self):
        assert _in_date_range("2026-03-01 algo", None, None, "2026-03")

    def test_date_filter_no_match(self):
        assert not _in_date_range("2026-04-01 algo", None, None, "2026-03")

    def test_date_from_inclusive(self):
        assert _in_date_range("2026-03-10 algo", "2026-03-10", None, None)

    def test_date_from_excludes_before(self):
        assert not _in_date_range("2026-03-09 algo", "2026-03-10", None, None)

    def test_date_to_inclusive(self):
        assert _in_date_range("2026-03-15 algo", None, "2026-03-15", None)

    def test_date_to_excludes_after(self):
        assert not _in_date_range("2026-03-16 algo", None, "2026-03-15", None)

    def test_line_without_date_with_filter_excluded(self):
        assert not _in_date_range("sin fecha aquí", "2026-03-01", None, None)


# ═══════════════════════════════════════════════════════════════════════════════
# File-based helpers
# ═══════════════════════════════════════════════════════════════════════════════

class TestSearchLogbook:

    def test_basic_keyword_match(self, tmp_path):
        lb = tmp_path / "logbook.md"
        lb.write_text(
            "2026-03-01 Calibración relativa #idea\n"
            "2026-03-02 El fit no converge #problema\n"
            "2026-03-03 Resultado final #resultado\n"
        )
        hits = _search_logbook(lb, ["calibración"], None, None, None, None, False, 0)
        assert len(hits) == 1
        assert "Calibración" in hits[0]

    def test_tag_filter(self, tmp_path):
        lb = tmp_path / "logbook.md"
        lb.write_text(
            "2026-03-01 Idea sobre energía #idea\n"
            "2026-03-02 El fit no converge #problema\n"
        )
        hits = _search_logbook(lb, [], "idea", None, None, None, False, 0)
        assert len(hits) == 1
        assert hits[0].endswith("#idea")

    def test_limit(self, tmp_path):
        lb = tmp_path / "logbook.md"
        lb.write_text("\n".join(f"2026-03-{i:02d} entrada {i} #apunte" for i in range(1, 11)))
        hits = _search_logbook(lb, [], None, None, None, None, False, 3)
        assert len(hits) == 3

    def test_skips_headings_and_comments(self, tmp_path):
        lb = tmp_path / "logbook.md"
        lb.write_text(
            "# Título del logbook\n"
            "<!-- comment -->\n"
            "2026-03-01 Entrada válida #apunte\n"
        )
        hits = _search_logbook(lb, [], None, None, None, None, False, 0)
        assert len(hits) == 1

    def test_date_filter(self, tmp_path):
        lb = tmp_path / "logbook.md"
        lb.write_text(
            "2026-02-01 Febrero #apunte\n"
            "2026-03-01 Marzo #apunte\n"
        )
        hits = _search_logbook(lb, [], None, "2026-03", None, None, False, 0)
        assert len(hits) == 1
        assert "Marzo" in hits[0]


class TestSearchFile:

    def test_basic_keyword_match(self, tmp_path):
        f = tmp_path / "highlights.md"
        f.write_text(
            "# Highlights\n"
            "- Energy resolution 2.3% #resultado\n"
            "- Calibración relativa decidida #decision\n"
        )
        hits = _search_file(f, ["energy"], False, 0)
        assert len(hits) == 1
        assert "Energy" in hits[0]

    def test_skips_headings_and_comments(self, tmp_path):
        f = tmp_path / "test.md"
        f.write_text(
            "# Heading match\n"
            "<!-- comment match -->\n"
            "body match\n"
        )
        hits = _search_file(f, ["match"], False, 0)
        assert len(hits) == 1
        assert "body" in hits[0]


# ═══════════════════════════════════════════════════════════════════════════════
# run_search integration
# ═══════════════════════════════════════════════════════════════════════════════

class TestRunSearch:

    def _make_project(self, projects_dir: Path, name: str) -> Path:
        proj = projects_dir / name
        proj.mkdir()
        base = name.lstrip("💻⚙️🌀📚📖🌿☀️")
        (proj / f"{base}-project.md").write_text(
            f"# {name}\n\n"
            "**Tipo:** Investigación\n"
            "**Estado:** En marcha\n"
            "**Prioridad:** media\n\n"
            "## ✅ Tareas\n\n"
        )
        (proj / f"{base}-logbook.md").write_text(
            "2026-03-01 Calibración relativa #idea\n"
            "2026-03-02 El fit no converge #problema\n"
        )
        return proj

    def _patch(self, monkeypatch, projects_dir):
        monkeypatch.setattr("core.search.PROJECTS_DIR", projects_dir)
        monkeypatch.setattr("core.log.PROJECTS_DIR",    projects_dir)

    def test_finds_keyword_in_logbook(self, tmp_path, monkeypatch, capsys):
        projects_dir = tmp_path / "🚀proyectos"
        projects_dir.mkdir()
        self._make_project(projects_dir, "💻testproj")
        self._patch(monkeypatch, projects_dir)

        rc = run_search(query="calibración")
        assert rc == 0
        out = capsys.readouterr().out
        assert "1 resultado" in out or "testproj" in out

    def test_tag_filter_restricts_results(self, tmp_path, monkeypatch, capsys):
        projects_dir = tmp_path / "🚀proyectos"
        projects_dir.mkdir()
        self._make_project(projects_dir, "💻testproj")
        self._patch(monkeypatch, projects_dir)

        run_search(None, tag="problema")
        out = capsys.readouterr().out
        assert "converge" in out or "problema" in out

    def test_no_match_returns_zero(self, tmp_path, monkeypatch, capsys):
        projects_dir = tmp_path / "🚀proyectos"
        projects_dir.mkdir()
        self._make_project(projects_dir, "💻testproj")
        self._patch(monkeypatch, projects_dir)

        rc = run_search(query="xyzinexistente99")
        assert rc == 0
        out = capsys.readouterr().out
        assert "calibración" not in out.lower()

    def test_open_writes_to_cmd_md(self, tmp_path, monkeypatch):
        projects_dir = tmp_path / "🚀proyectos"
        projects_dir.mkdir()
        self._make_project(projects_dir, "💻testproj")
        cmd_file = tmp_path / "cmd.md"
        self._patch(monkeypatch, projects_dir)
        monkeypatch.setattr("core.open.CMD_MD",      cmd_file)
        monkeypatch.setattr("core.open.open_file",   lambda p, e: 0)

        run_search(query="calibración", open_after=True)
        assert cmd_file.exists()
        assert "calibración" in cmd_file.read_text().lower()

    def test_missing_projects_dir_returns_error(self, tmp_path, monkeypatch, capsys):
        missing = tmp_path / "nonexistent"
        monkeypatch.setattr("core.search.PROJECTS_DIR", missing)
        monkeypatch.setattr("core.log.PROJECTS_DIR",    missing)
        rc = run_search(query="algo")
        assert rc == 1

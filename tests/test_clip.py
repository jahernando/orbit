"""test_clip.py — tests for `orbit clip` (date, week, proj).

Covers:
  - clip date: today, expression, invalid
  - clip week: today, expression, invalid
  - clip proj: project link, file path, search by query, disambiguation
  - _find_file_in_project: exact path, partial match, ambiguous
"""

import pytest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

from core.clip import _clip_date, _clip_week, _clip_proj, _find_file_in_project


# ═══════════════════════════════════════════════════════════════════════════════
# clip date
# ═══════════════════════════════════════════════════════════════════════════════

class TestClipDate:

    def test_today_default(self, capsys):
        rc = _clip_date()
        assert rc == 0
        assert date.today().isoformat() in capsys.readouterr().out

    def test_explicit_date(self, capsys):
        rc = _clip_date("2026-06-15")
        assert rc == 0
        assert "2026-06-15" in capsys.readouterr().out

    def test_invalid(self, capsys):
        rc = _clip_date("xyzzy")
        assert rc == 1


# ═══════════════════════════════════════════════════════════════════════════════
# clip week
# ═══════════════════════════════════════════════════════════════════════════════

class TestClipWeek:

    def test_today_default(self, capsys):
        rc = _clip_week()
        assert rc == 0
        iso = date.today().isocalendar()
        expected = f"{iso[0]}-W{iso[1]:02d}"
        assert expected in capsys.readouterr().out

    def test_from_date(self, capsys):
        rc = _clip_week("2026-03-20")
        assert rc == 0
        assert "2026-W12" in capsys.readouterr().out

    def test_invalid(self, capsys):
        rc = _clip_week("xyzzy")
        assert rc == 1


# ═══════════════════════════════════════════════════════════════════════════════
# _find_file_in_project
# ═══════════════════════════════════════════════════════════════════════════════

class TestFindFileInProject:

    def test_exact_path(self, tmp_path):
        (tmp_path / "agenda.md").write_text("# Agenda")
        result = _find_file_in_project(tmp_path, "agenda.md")
        assert result == tmp_path / "agenda.md"

    def test_exact_path_without_extension(self, tmp_path):
        (tmp_path / "agenda.md").write_text("# Agenda")
        result = _find_file_in_project(tmp_path, "agenda")
        assert result == tmp_path / "agenda.md"

    def test_recursive_search(self, tmp_path):
        notes = tmp_path / "notes"
        notes.mkdir()
        target = notes / "2026-03-21_diseño.md"
        target.write_text("# Diseño")
        result = _find_file_in_project(tmp_path, "diseño")
        assert result == target

    def test_search_in_subdirs(self, tmp_path):
        cronos = tmp_path / "cronos"
        cronos.mkdir()
        target = cronos / "crono-v1.md"
        target.write_text("# Crono")
        result = _find_file_in_project(tmp_path, "crono-v1")
        assert result == target

    def test_not_found(self, tmp_path, capsys):
        result = _find_file_in_project(tmp_path, "nonexistent")
        assert result is None
        assert "no se encontró" in capsys.readouterr().out

    def test_exact_stem_wins_over_partial(self, tmp_path):
        """When one file has exact stem match, it wins over partials."""
        notes = tmp_path / "notes"
        notes.mkdir()
        (notes / "agenda.md").write_text("a")
        (notes / "agenda_old.md").write_text("b")
        result = _find_file_in_project(tmp_path, "agenda")
        # exact path match (agenda.md at root doesn't exist, but notes/agenda.md
        # matches by stem exactly)
        assert result.stem == "agenda"

    def test_disambiguation_selects_first(self, tmp_path, monkeypatch):
        """When multiple partial matches, interactive selection picks one."""
        notes = tmp_path / "notes"
        notes.mkdir()
        (notes / "result_a.md").write_text("a")
        (notes / "result_b.md").write_text("b")
        monkeypatch.setattr("builtins.input", lambda _: "1")
        result = _find_file_in_project(tmp_path, "result")
        assert result is not None
        assert "result" in result.stem

    def test_skips_hidden_files(self, tmp_path):
        (tmp_path / ".hidden.md").write_text("hidden")
        (tmp_path / "visible.md").write_text("visible")
        result = _find_file_in_project(tmp_path, "hidden")
        assert result is None or result.name == "visible.md"


# ═══════════════════════════════════════════════════════════════════════════════
# clip proj (integration with project fixtures)
# ═══════════════════════════════════════════════════════════════════════════════

class TestClipProj:

    def test_project_not_found(self, capsys):
        rc = _clip_proj("zzz_nonexistent_zzz")
        assert rc == 1
        assert "no encontrado" in capsys.readouterr().out

    def test_file_not_found_in_project(self, capsys):
        """If project exists but target doesn't, returns 1."""
        # This depends on actual workspace — skip if no projects
        from core.config import iter_project_dirs
        from core.project import _is_new_project
        dirs = [d for d in iter_project_dirs() if _is_new_project(d)]
        if not dirs:
            pytest.skip("No projects available")
        proj = dirs[0]
        rc = _clip_proj(proj.name, target="zzz_nonexistent_file_zzz")
        assert rc == 1

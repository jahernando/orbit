"""Tests for core/clean.py — logbook, event, and note cleaning."""

import os
import time
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

from core.clean import (
    _clean_logbook, _clean_events, _event_date,
    _find_stale_notes, _prompt_delete_notes, run_clean,
)


# ── Helpers ──────────────────────────────────────────────────────────────────

def _make_project(tmp_path, name="test-proj", logbook="", agenda="", notes=None):
    """Create a minimal project structure and return project_dir."""
    proj = tmp_path / "🚀proyectos" / name
    proj.mkdir(parents=True)
    (proj / "project.md").write_text("# Test\n- Estado: active\n- Tipo: 💻dev\n- Prioridad: media\n")
    if logbook:
        (proj / f"{name}-logbook.md").write_text(logbook)
    if agenda:
        (proj / f"{name}-agenda.md").write_text(agenda)
    if notes:
        notes_dir = proj / "notes"
        notes_dir.mkdir()
        for n, content in notes.items():
            (notes_dir / n).write_text(content)
    return proj


# ── _clean_logbook ───────────────────────────────────────────────────────────

class TestCleanLogbook:
    def test_removes_old_entries(self, tmp_path):
        logbook = (
            "2025-01-01 📝 antigua #apunte\n"
            "2026-03-01 📝 reciente #apunte\n"
        )
        proj = _make_project(tmp_path, logbook=logbook)
        cutoff = date(2026, 1, 1)

        removed = _clean_logbook(proj, cutoff, dry_run=False)

        assert removed == 1
        content = (proj / "test-proj-logbook.md").read_text()
        assert "antigua" not in content
        assert "reciente" in content

    def test_keeps_all_when_recent(self, tmp_path):
        logbook = "2026-03-01 📝 reciente #apunte\n2026-03-05 📝 otra #apunte\n"
        proj = _make_project(tmp_path, logbook=logbook)
        cutoff = date(2026, 1, 1)

        removed = _clean_logbook(proj, cutoff, dry_run=False)
        assert removed == 0

    def test_dry_run_no_write(self, tmp_path):
        logbook = "2025-01-01 📝 antigua #apunte\n2026-03-01 📝 reciente #apunte\n"
        proj = _make_project(tmp_path, logbook=logbook)
        cutoff = date(2026, 1, 1)

        removed = _clean_logbook(proj, cutoff, dry_run=True)

        assert removed == 1
        content = (proj / "test-proj-logbook.md").read_text()
        assert "antigua" in content  # not removed because dry-run

    def test_no_logbook_file(self, tmp_path):
        proj = _make_project(tmp_path)
        assert _clean_logbook(proj, date(2026, 1, 1), False) == 0

    def test_preserves_non_date_lines(self, tmp_path):
        logbook = "# Logbook\n\n2025-01-01 📝 vieja #apunte\nLínea suelta\n"
        proj = _make_project(tmp_path, logbook=logbook)

        _clean_logbook(proj, date(2026, 1, 1), dry_run=False)

        content = (proj / "test-proj-logbook.md").read_text()
        assert "# Logbook" in content
        assert "Línea suelta" in content
        assert "vieja" not in content


# ── _clean_events ────────────────────────────────────────────────────────────

class TestCleanEvents:
    def _agenda_with_events(self, events_block):
        return (
            "## ☐ Tareas\n\n"
            "## 🏁 Hitos\n\n"
            f"## 📅 Eventos\n{events_block}\n"
        )

    def test_removes_old_events(self, tmp_path):
        agenda = self._agenda_with_events(
            "2025-06-01 — Evento viejo\n"
            "2026-06-01 — Evento futuro\n"
        )
        proj = _make_project(tmp_path, agenda=agenda)
        cutoff = date(2026, 1, 1)

        removed = _clean_events(proj, cutoff, dry_run=False)

        assert removed == 1
        content = (proj / "test-proj-agenda.md").read_text()
        assert "viejo" not in content
        assert "futuro" in content

    def test_dry_run_no_write(self, tmp_path):
        agenda = self._agenda_with_events("2025-06-01 — Evento viejo\n")
        proj = _make_project(tmp_path, agenda=agenda)

        removed = _clean_events(proj, cutoff=date(2026, 1, 1), dry_run=True)

        assert removed == 1
        content = (proj / "test-proj-agenda.md").read_text()
        assert "viejo" in content  # not removed

    def test_no_agenda_file(self, tmp_path):
        proj = _make_project(tmp_path)
        assert _clean_events(proj, date(2026, 1, 1), False) == 0


# ── _event_date ──────────────────────────────────────────────────────────────

class TestEventDate:
    def test_valid_date(self):
        assert _event_date({"date": "2026-03-10"}) == date(2026, 3, 10)

    def test_invalid_date(self):
        assert _event_date({"date": "bad"}) == date.min

    def test_missing_date(self):
        assert _event_date({}) == date.min


# ── _find_stale_notes ────────────────────────────────────────────────────────

class TestFindStaleNotes:
    def test_finds_stale_notes(self, tmp_path):
        proj = _make_project(tmp_path, notes={"old.md": "vieja", "new.md": "nueva"})
        notes_dir = proj / "notes"

        # Set old.md mtime to 1 year ago
        old_ts = time.time() - 365 * 86400
        os.utime(notes_dir / "old.md", (old_ts, old_ts))

        cutoff = date.today() - timedelta(days=180)
        stale = _find_stale_notes(proj, cutoff)

        assert len(stale) == 1
        assert stale[0].name == "old.md"

    def test_no_notes_dir(self, tmp_path):
        proj = _make_project(tmp_path)
        assert _find_stale_notes(proj, date.today()) == []

    def test_ignores_non_md(self, tmp_path):
        proj = _make_project(tmp_path, notes={"note.md": "ok"})
        (proj / "notes" / "data.json").write_text("{}")
        # Set both to old
        old_ts = time.time() - 365 * 86400
        for f in (proj / "notes").iterdir():
            os.utime(f, (old_ts, old_ts))

        cutoff = date.today() - timedelta(days=180)
        stale = _find_stale_notes(proj, cutoff)
        assert len(stale) == 1
        assert stale[0].name == "note.md"


# ── _prompt_delete_notes ─────────────────────────────────────────────────────

class TestPromptDeleteNotes:
    def test_dry_run_returns_zero(self, tmp_path):
        proj = _make_project(tmp_path, notes={"a.md": "x"})
        stale = [proj / "notes" / "a.md"]
        # dry_run=True should not delete and return 0
        with patch("sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = True
            assert _prompt_delete_notes(stale, dry_run=True) == 0
        assert (proj / "notes" / "a.md").exists()

    def test_empty_list(self):
        assert _prompt_delete_notes([], dry_run=False) == 0

    def test_non_tty_returns_zero(self, tmp_path):
        proj = _make_project(tmp_path, notes={"a.md": "x"})
        stale = [proj / "notes" / "a.md"]
        with patch("sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = False
            assert _prompt_delete_notes(stale, dry_run=False) == 0


# ── run_clean (integration) ─────────────────────────────────────────────────

class TestRunClean:
    def test_single_project_dry_run(self, tmp_path):
        logbook = "2025-01-01 📝 vieja #apunte\n2026-03-01 📝 nueva #apunte\n"
        _make_project(tmp_path, name="myproj", logbook=logbook)

        with patch("core.clean.PROJECTS_DIR", tmp_path / "🚀proyectos"), \
             patch("core.clean._find_new_project", return_value=tmp_path / "🚀proyectos" / "myproj"):
            ret = run_clean(project="myproj", months=6, dry_run=True)

        assert ret == 0

    def test_single_project_cleans(self, tmp_path):
        logbook = "2025-01-01 📝 vieja #apunte\n2026-03-01 📝 nueva #apunte\n"
        proj = _make_project(tmp_path, name="myproj", logbook=logbook)

        with patch("core.clean.PROJECTS_DIR", tmp_path / "🚀proyectos"), \
             patch("core.clean._find_new_project", return_value=proj):
            ret = run_clean(project="myproj", months=6, dry_run=False)

        assert ret == 0
        content = (proj / "myproj-logbook.md").read_text()
        assert "vieja" not in content
        assert "nueva" in content

    def test_project_not_found(self, tmp_path):
        with patch("core.clean._find_new_project", return_value=None):
            ret = run_clean(project="nope")
        assert ret == 1

    def test_no_projects_dir(self, tmp_path):
        with patch("core.clean.PROJECTS_DIR", tmp_path / "nonexistent"):
            ret = run_clean()
        assert ret == 0

    def test_nothing_to_clean(self, tmp_path):
        logbook = "2026-03-01 📝 reciente #apunte\n"
        _make_project(tmp_path, name="fresh", logbook=logbook)

        with patch("core.clean.PROJECTS_DIR", tmp_path / "🚀proyectos"), \
             patch("core.clean._find_new_project", return_value=tmp_path / "🚀proyectos" / "fresh"):
            ret = run_clean(project="fresh", months=6, dry_run=False)
        assert ret == 0

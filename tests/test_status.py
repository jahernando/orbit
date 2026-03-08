"""tests/test_status.py — unit tests for run_status in core/activity.py."""

import pytest
from datetime import date, timedelta
from pathlib import Path

from core.activity import run_status


# ── fixture ────────────────────────────────────────────────────────────────────

@pytest.fixture
def status_env(orbit_env, monkeypatch):
    """Extend orbit_env with logbook entries to test status thresholds.

    Creates three projects with different activity profiles:
    - 💻testproj  — active (entry today)
    - 💻oldproj   — stopped (entry 45 days ago, within 60d)
    - 💻sleepproj — sleeping (no entries at all)
    """
    today = date.today()
    projects_dir = orbit_env["projects_dir"]

    # testproj already exists from orbit_env with empty logbook
    # Write an entry dated today
    logbook = orbit_env["proj_dir"] / "📓testproj.md"
    logbook.write_text(f"# Logbook\n{today.isoformat()} Something happened #apunte\n")

    # oldproj — entry 45 days ago
    old_dir = projects_dir / "💻oldproj"
    old_dir.mkdir()
    old_proj = old_dir / "💻oldproj.md"
    old_proj.write_text(
        "# oldproj\n💻 Software\n▶️ En marcha\n🟠 Alta\n"
        "## 🎯 Objetivo\nTest.\n## ✅ Tareas\n## 📎 Referencias\n"
    )
    old_date = (today - timedelta(days=45)).isoformat()
    (old_dir / "📓oldproj.md").write_text(
        f"# Logbook\n{old_date} Old activity #apunte\n"
    )

    # sleepproj — no entries
    sleep_dir = projects_dir / "💻sleepproj"
    sleep_dir.mkdir()
    sleep_proj = sleep_dir / "💻sleepproj.md"
    sleep_proj.write_text(
        "# sleepproj\n💻 Software\n▶️ En marcha\n🟠 Alta\n"
        "## 🎯 Objetivo\nTest.\n## ✅ Tareas\n## 📎 Referencias\n"
    )
    (sleep_dir / "📓sleepproj.md").write_text("# Logbook\n")

    monkeypatch.setattr("core.activity.PROJECTS_DIR", projects_dir)
    # Silence focus lookup
    monkeypatch.setattr("core.focus.FOCUS_FILE",
                        orbit_env["tmp"] / ".orbit" / "focus.json")

    return {**orbit_env, "today": today}


# ── tests ──────────────────────────────────────────────────────────────────────

class TestRunStatus:
    def test_returns_zero(self, status_env, capsys):
        rc = run_status()
        assert rc == 0

    def test_shows_active_project(self, status_env, capsys):
        run_status()
        out = capsys.readouterr().out
        assert "💻testproj" in out
        assert "🟢" in out

    def test_shows_stopped_project(self, status_env, capsys):
        run_status()
        out = capsys.readouterr().out
        assert "💻oldproj" in out
        assert "🟡" in out

    def test_shows_sleeping_project(self, status_env, capsys):
        run_status()
        out = capsys.readouterr().out
        assert "💻sleepproj" in out
        assert "🔴" in out

    def test_summary_line(self, status_env, capsys):
        run_status()
        out = capsys.readouterr().out
        assert "Total:" in out
        assert "🟢" in out
        assert "🟡" in out
        assert "🔴" in out

    def test_filter_by_project(self, status_env, capsys):
        run_status(project="oldproj")
        out = capsys.readouterr().out
        assert "💻oldproj" in out
        assert "💻testproj" not in out
        assert "💻sleepproj" not in out

    def test_last_entry_shown(self, status_env, capsys):
        today_str = status_env["today"].isoformat()
        run_status(project="testproj")
        out = capsys.readouterr().out
        assert today_str in out

    def test_no_projects_dir(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setattr("core.activity.PROJECTS_DIR", tmp_path / "nonexistent")
        rc = run_status()
        assert rc == 1

    def test_empty_projects_dir(self, tmp_path, monkeypatch, capsys):
        empty = tmp_path / "empty"
        empty.mkdir()
        monkeypatch.setattr("core.activity.PROJECTS_DIR", empty)
        run_status()
        out = capsys.readouterr().out
        assert "No se encontraron" in out

    def test_focus_only_filters(self, status_env, monkeypatch, capsys):
        """--focus shows only projects in current focus."""
        from core.focus import set_focus, FOCUS_FILE
        monkeypatch.setattr(
            "core.focus.FOCUS_FILE",
            status_env["tmp"] / ".orbit" / "focus.json",
        )
        set_focus("day", ["💻testproj"], status_env["today"])
        run_status(focus_only=True)
        out = capsys.readouterr().out
        assert "💻testproj" in out
        assert "💻oldproj" not in out
        assert "💻sleepproj" not in out

    def test_focus_only_no_focus_shows_nothing(self, status_env, monkeypatch, capsys):
        """--focus with empty focus.json: shows no projects."""
        monkeypatch.setattr(
            "core.focus.FOCUS_FILE",
            status_env["tmp"] / ".orbit" / "focus.json",
        )
        # focus.json doesn't exist → no focus → no projects shown
        run_status(focus_only=True)
        out = capsys.readouterr().out
        assert "💻testproj" not in out

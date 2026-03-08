"""tests/test_evaluation.py — unit tests for core/evaluation.py and core/routines.py."""

import json
import pytest
from datetime import date, timedelta
from pathlib import Path

from core.focus import set_focus  # import before evaluation to avoid circular issues

from core.evaluation import (
    _EVAL_STATS_START, _EVAL_STATS_END,
    _inject_block, _has, _stats_block, eval_path,
    create_or_update_eval, run_eval,
)
from core.focus import _period_key


# ── fixture ────────────────────────────────────────────────────────────────────

@pytest.fixture
def eval_env(mision_env, monkeypatch, tmp_path):
    """Extend mision_env with mission project structure and patched paths."""
    projects_dir  = mision_env["projects_dir"]
    today         = mision_env["today"]

    # ☀️mission project
    mission_dir = projects_dir / "☀️mission"
    mission_dir.mkdir()
    (mission_dir / "☀️mission.md").write_text(
        "# mission\n☀️ Misión\n▶️ En marcha\n🟠 Alta\n"
        "## 🎯 Objetivo\n-\n## ✅ Tareas\n"
    )
    (mission_dir / "📓mission.md").write_text("# Logbook\n")
    # sub-dirs created on demand by create_or_update_eval

    # Patch evaluation module paths
    monkeypatch.setattr("core.evaluation.PROJECTS_DIR", projects_dir)
    monkeypatch.setattr("core.focus.PROJECTS_DIR",      projects_dir)

    # Patch focus file to tmp
    focus_file = tmp_path / ".orbit" / "focus.json"
    monkeypatch.setattr("core.focus.FOCUS_FILE", focus_file)

    # Silence open_file
    monkeypatch.setattr("core.evaluation.open_file", lambda p, e: 0)

    today_date = date.fromisoformat(mision_env["today"])

    return {
        **mision_env,
        "mission_dir": mission_dir,
        "focus_file":  focus_file,
        "today_date":  today_date,   # date object (mision_env["today"] is a str)
    }


# ── _inject_block ──────────────────────────────────────────────────────────────

class TestInjectBlock:
    def test_creates_block_when_absent(self, tmp_path):
        f = tmp_path / "note.md"
        f.write_text("# Title\n")
        _inject_block(f, "content\n")
        text = f.read_text()
        assert _EVAL_STATS_START in text
        assert "content" in text

    def test_replaces_existing_block(self, tmp_path):
        f = tmp_path / "note.md"
        f.write_text(f"# Title\n{_EVAL_STATS_START}\nold\n{_EVAL_STATS_END}\n")
        _inject_block(f, "new\n")
        text = f.read_text()
        assert "new" in text
        assert "old" not in text
        assert text.count(_EVAL_STATS_START) == 1

    def test_preserves_content_outside_block(self, tmp_path):
        f = tmp_path / "note.md"
        f.write_text(
            f"# Title\n\n"
            f"{_EVAL_STATS_START}\nold\n{_EVAL_STATS_END}\n\n"
            f"## 📝 Reflexión\nuser text\n"
        )
        _inject_block(f, "new\n")
        text = f.read_text()
        assert "user text" in text
        assert "new" in text


# ── _stats_block ───────────────────────────────────────────────────────────────

class TestStatsBlock:
    def test_includes_foco_line(self, eval_env):
        today = eval_env["today_date"]
        set_focus("day", ["💻testproj"], today)
        block = _stats_block(["💻testproj"], today, today)
        assert "**Foco:**" in block
        assert "💻testproj" in block

    def test_empty_focus_shows_dash(self, eval_env):
        today = eval_env["today_date"]
        block = _stats_block([], today, today)
        assert "**Foco:** —" in block

    def test_counts_logbook_entries(self, eval_env):
        today = eval_env["today_date"]
        set_focus("day", ["💻testproj"], today)
        block = _stats_block(["💻testproj"], today, today)
        # logbook has 2 entries today (written by mision_env)
        assert "2 entradas" in block

    def test_total_line_always_present(self, eval_env):
        today = eval_env["today_date"]
        block = _stats_block([], today, today)
        assert "Total:" in block

    def test_zero_for_future_period(self, eval_env):
        today  = eval_env["today_date"]
        future = today + timedelta(days=10)
        set_focus("day", ["💻testproj"], today)
        block = _stats_block(["💻testproj"], future, future)
        assert "0 entradas" in block or "Total: 0" in block


# ── eval_path ──────────────────────────────────────────────────────────────────

class TestEvalPath:
    def test_day_path(self, eval_env):
        today = eval_env["today_date"]
        p = eval_path("day", today)
        assert p is not None
        assert today.isoformat() in p.name
        assert "diario" in str(p)

    def test_week_path(self, eval_env):
        today = eval_env["today_date"]
        p = eval_path("week", today)
        assert p is not None
        assert "semanal" in str(p)
        assert "W" in p.name

    def test_month_path(self, eval_env):
        today = eval_env["today_date"]
        p = eval_path("month", today)
        assert p is not None
        assert "mensual" in str(p)
        assert today.strftime("%Y-%m") in p.name

    def test_none_when_no_mission(self, tmp_path, monkeypatch):
        monkeypatch.setattr("core.evaluation.PROJECTS_DIR", tmp_path / "empty")
        assert eval_path("day") is None


# ── create_or_update_eval ─────────────────────────────────────────────────────

class TestCreateOrUpdateEval:
    def test_creates_file(self, eval_env):
        today = eval_env["today_date"]
        dest = create_or_update_eval("day", today, open_after=False)
        assert dest is not None
        assert dest.exists()

    def test_note_has_stats_markers(self, eval_env):
        today = eval_env["today_date"]
        dest = create_or_update_eval("day", today, open_after=False)
        text = dest.read_text()
        assert _EVAL_STATS_START in text
        assert _EVAL_STATS_END in text

    def test_note_has_reflection_scaffold(self, eval_env):
        today = eval_env["today_date"]
        dest = create_or_update_eval("day", today, open_after=False)
        text = dest.read_text()
        assert "### ¿Qué fue bien" in text
        assert "### 📌 Decisiones" in text

    def test_week_note_has_week_reflection(self, eval_env):
        today = eval_env["today_date"]
        dest = create_or_update_eval("week", today, open_after=False)
        text = dest.read_text()
        assert "### Balance de la semana" in text
        assert "### 🎯 Objetivos para la semana siguiente" in text

    def test_month_note_has_month_reflection(self, eval_env):
        today = eval_env["today_date"]
        dest = create_or_update_eval("month", today, open_after=False)
        text = dest.read_text()
        assert "### Balance del mes" in text
        assert "### 🎯 Objetivos para el mes siguiente" in text

    def test_stats_updated_on_second_call(self, eval_env):
        today = eval_env["today_date"]
        # First call: no focus → 0 entries
        dest = create_or_update_eval("day", today, open_after=False)
        assert "Total: 0 entradas" in dest.read_text()

        # Set focus and run again
        set_focus("day", ["💻testproj"], today)
        create_or_update_eval("day", today, open_after=False)
        assert "2 entradas" in dest.read_text()

    def test_reflection_not_overwritten(self, eval_env):
        today = eval_env["today_date"]
        dest = create_or_update_eval("day", today, open_after=False)
        # Simulate user writing in the reflection
        text = dest.read_text()
        dest.write_text(text.replace("### ¿Qué fue bien hoy?", "### ¿Qué fue bien hoy?\nMuy bien!"))
        # Second call: should not overwrite user content
        create_or_update_eval("day", today, open_after=False)
        assert "Muy bien!" in dest.read_text()

    def test_reflection_not_duplicated(self, eval_env):
        today = eval_env["today_date"]
        dest = create_or_update_eval("day", today, open_after=False)
        # Run twice
        create_or_update_eval("day", today, open_after=False)
        text = dest.read_text()
        assert text.count("### ¿Qué fue bien hoy?") == 1

    def test_markers_not_duplicated(self, eval_env):
        today = eval_env["today_date"]
        dest = create_or_update_eval("day", today, open_after=False)
        create_or_update_eval("day", today, open_after=False)
        text = dest.read_text()
        assert text.count(_EVAL_STATS_START) == 1
        assert text.count(_EVAL_STATS_END) == 1

    def test_returns_none_without_mission(self, eval_env, monkeypatch, capsys):
        monkeypatch.setattr("core.evaluation.PROJECTS_DIR",
                            eval_env["tmp"] / "nonexistent")
        result = create_or_update_eval("day", open_after=False)
        assert result is None

    def test_foco_line_in_stats_block(self, eval_env):
        today = eval_env["today_date"]
        set_focus("day", ["💻testproj"], today)
        dest = create_or_update_eval("day", today, open_after=False)
        text = dest.read_text()
        assert "**Foco:** " in text
        assert "💻testproj" in text


# ── run_eval ───────────────────────────────────────────────────────────────────

class TestRunEval:
    def test_day_returns_zero(self, eval_env):
        today = eval_env["today_date"]
        rc = run_eval("day", today.isoformat(), open_after=False)
        assert rc == 0

    def test_week_returns_zero(self, eval_env):
        today = eval_env["today_date"]
        rc = run_eval("week", today.isoformat(), open_after=False)
        assert rc == 0

    def test_month_returns_zero(self, eval_env):
        today = eval_env["today_date"]
        rc = run_eval("month", today.isoformat(), open_after=False)
        assert rc == 0

    def test_all_periods_when_no_period_given(self, eval_env):
        today = eval_env["today_date"]
        rc = run_eval(None, today.isoformat(), open_after=False)
        assert rc == 0
        for period, subdir in [("day", "diario"), ("week", "semanal"), ("month", "mensual")]:
            p = eval_path(period, today)
            assert p is not None and p.exists()

    def test_invalid_period_returns_one(self, eval_env, capsys):
        rc = run_eval("quarter", open_after=False)
        assert rc == 1


# ── run_start / run_end ────────────────────────────────────────────────────────

class TestRunStart:
    @pytest.fixture
    def routine_env(self, eval_env, monkeypatch, tmp_path):
        session_file = tmp_path / ".orbit" / "session.json"
        monkeypatch.setattr("core.routines.PROJECTS_DIR", eval_env["projects_dir"])
        monkeypatch.setattr("core.routines._SESSION_FILE", session_file)
        monkeypatch.setattr("core.focus.FOCUS_FILE", eval_env["focus_file"])
        monkeypatch.setattr("core.evaluation.PROJECTS_DIR", eval_env["projects_dir"])
        monkeypatch.setattr("sys.stdin.isatty", lambda: False)  # no interactive prompts
        return {**eval_env, "session_file": session_file}

    def test_start_returns_zero(self, routine_env):
        from core.routines import run_start
        rc = run_start(editor="typora")
        assert rc == 0

    def test_start_prints_status(self, routine_env, capsys):
        from core.routines import run_start
        run_start(editor="typora")
        out = capsys.readouterr().out
        assert "🟢" in out

    def test_start_prints_focus(self, routine_env, capsys):
        from core.routines import run_start
        run_start(editor="typora")
        out = capsys.readouterr().out
        assert "Foco actual" in out

    def test_start_records_session(self, routine_env):
        from core.routines import run_start
        run_start(editor="typora")
        session_file = routine_env["session_file"]
        assert session_file.exists()
        data = json.loads(session_file.read_text())
        assert data["last_start"] == date.today().isoformat()

    def test_start_no_prompt_without_tty(self, routine_env, capsys):
        from core.routines import run_start
        # isatty is already monkeypatched to False
        run_start(editor="typora")
        out = capsys.readouterr().out
        # Should not prompt for missing focus
        assert "¿Establecer ahora?" not in out


class TestRunEnd:
    @pytest.fixture
    def routine_env(self, eval_env, monkeypatch, tmp_path):
        session_file = tmp_path / ".orbit" / "session.json"
        monkeypatch.setattr("core.routines.PROJECTS_DIR", eval_env["projects_dir"])
        monkeypatch.setattr("core.routines._SESSION_FILE", session_file)
        monkeypatch.setattr("core.focus.FOCUS_FILE", eval_env["focus_file"])
        monkeypatch.setattr("core.evaluation.PROJECTS_DIR", eval_env["projects_dir"])
        monkeypatch.setattr("core.routines.open_file", lambda p, e: 0)
        monkeypatch.setattr("core.evaluation.open_file", lambda p, e: 0)
        return {**eval_env, "session_file": session_file}

    def test_end_returns_zero(self, routine_env):
        from core.routines import run_end
        rc = run_end(editor="typora")
        assert rc == 0

    def test_end_creates_daily_eval(self, routine_env):
        from core.routines import run_end
        run_end(editor="typora")
        today = routine_env["today_date"]
        p = eval_path("day", today)
        assert p is not None and p.exists()

    def test_end_records_session(self, routine_env):
        from core.routines import run_end
        run_end(editor="typora")
        session_file = routine_env["session_file"]
        data = json.loads(session_file.read_text())
        assert data["last_end"] == date.today().isoformat()

    def test_end_idempotent_no_duplicate_markers(self, routine_env):
        from core.routines import run_end
        run_end(editor="typora")
        run_end(editor="typora")
        today = routine_env["today_date"]
        p = eval_path("day", today)
        text = p.read_text()
        assert text.count(_EVAL_STATS_START) == 1
        assert text.count(_EVAL_STATS_END) == 1

    def test_end_shows_focus_activity(self, routine_env, capsys):
        from core.routines import run_end
        set_focus("day", ["💻testproj"], routine_env["today_date"])
        run_end(editor="typora")
        out = capsys.readouterr().out
        assert "💻testproj" in out or "testproj" in out

    def test_end_prints_goodbye(self, routine_env, capsys):
        from core.routines import run_end
        run_end(editor="typora")
        out = capsys.readouterr().out
        assert "Hasta mañana" in out

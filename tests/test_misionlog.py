"""test_misionlog.py — tests for the day/week/month note system.

Covers:
  - Week helpers: _week_key, _week_bounds
  - _has_section: text detection in files
  - _inject_block: marker-based content injection
  - _parse_focus_projects: extract project names from headings
  - _find_logbook / _count_focus_entries: logbook activity counting
  - Format functions: valoracion day/week/month, reflection scaffolds
  - run_dayreport: stats-only injection, no note creation, terminal output
  - run_weekreport: stats always, reflection once, log_to_mission guarded
  - run_shell_startup: missed-session detection for yesterday's note
"""

from datetime import date, timedelta
from pathlib import Path

import pytest

from core.misionlog import _week_key, _week_bounds, run_shell_startup
from core.reports import (
    _has_section, _inject_block, _parse_focus_projects,
    _find_logbook, _count_focus_entries,
    _format_valoracion_day, _format_valoracion_stats_week,
    _format_reflection_week, _format_valoracion_stats_month,
    _format_reflection_month,
    _VALORACION_STATS_START, _VALORACION_STATS_END,
    _WR_START, _WR_END,
    run_dayreport, run_weekreport,
)

TODAY     = date.today()
TODAY_ISO = TODAY.isoformat()
YESTERDAY = (TODAY - timedelta(days=1)).isoformat()


# ═══════════════════════════════════════════════════════════════════════════════
# Week helpers
# ═══════════════════════════════════════════════════════════════════════════════

class TestWeekHelpers:

    def test_week_key_format(self):
        key = _week_key(date(2026, 3, 9))   # monday of W11
        assert key == "2026-W11"

    def test_week_key_format_zero_padded(self):
        key = _week_key(date(2026, 1, 5))   # W02
        assert "W0" in key

    def test_week_bounds_monday_start(self):
        mon, sun = _week_bounds(date(2026, 3, 11))  # wednesday
        assert mon.weekday() == 0   # monday
        assert sun.weekday() == 6   # sunday

    def test_week_bounds_span_seven_days(self):
        mon, sun = _week_bounds(TODAY)
        assert (sun - mon).days == 6

    def test_week_bounds_any_day_gives_same_week(self):
        mon1, _ = _week_bounds(date(2026, 3, 9))   # monday
        mon2, _ = _week_bounds(date(2026, 3, 13))  # friday same week
        assert mon1 == mon2


# ═══════════════════════════════════════════════════════════════════════════════
# _has_section
# ═══════════════════════════════════════════════════════════════════════════════

class TestHasSection:

    def test_found(self, tmp_path):
        f = tmp_path / "note.md"
        f.write_text("# Título\n\n### 🍅 Reflexión semanal\n\nTexto.\n")
        assert _has_section(f, "### 🍅 Reflexión semanal")

    def test_not_found(self, tmp_path):
        f = tmp_path / "note.md"
        f.write_text("# Título\n\nSin reflexión aquí.\n")
        assert not _has_section(f, "### 🍅 Reflexión semanal")

    def test_missing_file_returns_false(self, tmp_path):
        assert not _has_section(tmp_path / "ghost.md", "cualquier cosa")

    def test_empty_file_returns_false(self, tmp_path):
        f = tmp_path / "empty.md"
        f.write_text("")
        assert not _has_section(f, "### 🍅 Reflexión")


# ═══════════════════════════════════════════════════════════════════════════════
# _inject_block
# ═══════════════════════════════════════════════════════════════════════════════

class TestInjectBlock:

    def _note(self, tmp_path, content):
        p = tmp_path / "note.md"
        p.write_text(content)
        return p

    def test_replaces_content_between_markers(self, tmp_path):
        p = self._note(tmp_path,
            "# Nota\n\n"
            "<!-- orbit:valoracion-stats:start -->\n"
            "viejo contenido\n"
            "<!-- orbit:valoracion-stats:end -->\n")
        _inject_block(p, "nuevo contenido\n",
                      _VALORACION_STATS_START, _VALORACION_STATS_END)
        text = p.read_text()
        assert "nuevo contenido" in text
        assert "viejo contenido" not in text

    def test_markers_preserved_after_injection(self, tmp_path):
        p = self._note(tmp_path,
            "<!-- orbit:valoracion-stats:start -->\n"
            "<!-- orbit:valoracion-stats:end -->\n")
        _inject_block(p, "bloque\n",
                      _VALORACION_STATS_START, _VALORACION_STATS_END)
        text = p.read_text()
        assert _VALORACION_STATS_START in text
        assert _VALORACION_STATS_END in text

    def test_appends_when_markers_absent(self, tmp_path):
        p = self._note(tmp_path, "# Nota sin marcadores\n")
        _inject_block(p, "contenido\n",
                      _VALORACION_STATS_START, _VALORACION_STATS_END)
        text = p.read_text()
        assert "contenido" in text
        assert _VALORACION_STATS_START in text

    def test_second_inject_updates_without_duplicating_markers(self, tmp_path):
        p = self._note(tmp_path,
            "<!-- orbit:valoracion-stats:start -->\n"
            "primera\n"
            "<!-- orbit:valoracion-stats:end -->\n")
        _inject_block(p, "segunda\n",
                      _VALORACION_STATS_START, _VALORACION_STATS_END)
        text = p.read_text()
        assert "segunda" in text
        assert "primera" not in text
        assert text.count(_VALORACION_STATS_START) == 1

    def test_multiline_block_injected_correctly(self, tmp_path):
        p = self._note(tmp_path,
            "<!-- orbit:valoracion-stats:start -->\n"
            "<!-- orbit:valoracion-stats:end -->\n")
        block = "linea 1\nlinea 2\nlinea 3\n"
        _inject_block(p, block, _VALORACION_STATS_START, _VALORACION_STATS_END)
        assert "linea 1" in p.read_text()
        assert "linea 3" in p.read_text()


# ═══════════════════════════════════════════════════════════════════════════════
# _parse_focus_projects
# ═══════════════════════════════════════════════════════════════════════════════

class TestParseFocusProjects:

    def _note(self, tmp_path, content):
        p = tmp_path / "note.md"
        p.write_text(content)
        return p

    def test_extracts_single_project(self, tmp_path):
        p = self._note(tmp_path,
            "# Semana\n\n"
            "### 🎯 Proyectos en foco\n"
            "1. [💻testproj](../../proyectos/testproj/testproj.md)\n\n"
            "## 📝 Notas\n")
        names = _parse_focus_projects(p, "### 🎯 Proyectos en foco")
        assert "💻testproj" in names

    def test_extracts_multiple_projects(self, tmp_path):
        p = self._note(tmp_path,
            "### 🎯 Proyectos en foco\n"
            "1. [orbit](../../proyectos/orbit/orbit.md)\n"
            "2. [appec](../../proyectos/appec/appec.md)\n\n"
            "## Siguiente sección\n")
        names = _parse_focus_projects(p, "### 🎯 Proyectos en foco")
        assert len(names) == 2
        assert "orbit" in names
        assert "appec" in names

    def test_stops_at_next_heading(self, tmp_path):
        p = self._note(tmp_path,
            "### 🎯 Proyectos en foco\n"
            "1. [focus](./focus.md)\n\n"
            "## Siguiente sección\n"
            "1. [no-focus](./nofocus.md)\n")
        names = _parse_focus_projects(p, "### 🎯 Proyectos en foco")
        assert "focus" in names
        assert "no-focus" not in names

    def test_missing_heading_returns_empty(self, tmp_path):
        p = self._note(tmp_path, "# Nota\n\nSin sección de foco.\n")
        assert _parse_focus_projects(p, "### 🎯 Proyectos en foco") == []

    def test_missing_file_returns_empty(self, tmp_path):
        assert _parse_focus_projects(tmp_path / "ghost.md",
                                     "### 🎯 Proyectos en foco") == []

    def test_bullet_style_single_focus(self, tmp_path):
        p = self._note(tmp_path,
            "### 🎯 Proyecto en foco\n"
            "- [💻testproj](../../proyectos/testproj.md)\n\n"
            "## Siguiente\n")
        names = _parse_focus_projects(p, "### 🎯 Proyecto en foco")
        assert "💻testproj" in names


# ═══════════════════════════════════════════════════════════════════════════════
# _find_logbook / _count_focus_entries
# ═══════════════════════════════════════════════════════════════════════════════

class TestFindLogbookAndCount:

    def test_find_logbook_by_partial_name(self, mision_env):
        lb = _find_logbook("testproj")
        assert lb is not None
        assert lb.exists()

    def test_find_logbook_case_insensitive(self, mision_env):
        assert _find_logbook("TESTPROJ") is not None

    def test_find_logbook_unknown_returns_none(self, mision_env):
        assert _find_logbook("proyecto_inexistente_xyz") is None

    def test_count_entries_today(self, mision_env):
        counts = _count_focus_entries(["testproj"], TODAY, TODAY)
        assert counts["testproj"] == 2   # two entries written in fixture

    def test_count_entries_future_date_returns_zero(self, mision_env):
        future = TODAY + timedelta(days=30)
        counts = _count_focus_entries(["testproj"], future, future)
        assert counts["testproj"] == 0

    def test_count_entries_unknown_project_returns_zero(self, mision_env):
        counts = _count_focus_entries(["proyecto_xyz"], TODAY, TODAY)
        assert counts["proyecto_xyz"] == 0

    def test_count_entries_empty_list_returns_empty(self, mision_env):
        assert _count_focus_entries([], TODAY, TODAY) == {}


# ═══════════════════════════════════════════════════════════════════════════════
# Format functions
# ═══════════════════════════════════════════════════════════════════════════════

class TestFormatFunctions:

    # ── _format_valoracion_day ────────────────────────────────────────────────

    def test_day_with_focus_shows_tomato(self):
        text = _format_valoracion_day({"orbit": 3}, [], [])
        assert "🍅" in text
        assert "orbit" in text
        assert "3 entradas" in text

    def test_day_without_focus_shows_empty_mark(self):
        text = _format_valoracion_day({"orbit": 0}, [], [])
        assert "⬜" in text
        assert "sin actividad" in text

    def test_day_no_focus_no_focus_section(self):
        text = _format_valoracion_day({}, [], [])
        assert "🎯 Foco del día" not in text

    def test_day_shows_activity_section(self):
        activity = [{"name": "proj", "entries": [{"tipo": "apunte", "content": "x"}]}]
        text = _format_valoracion_day({}, activity, [])
        assert "📊 Actividad" in text
        assert "Entradas: 1" in text

    def test_day_shows_completed_tasks(self):
        text = _format_valoracion_day({}, [], [{"project": "proj", "description": "tarea"}])
        assert "Tareas cerradas: 1" in text

    # ── _format_valoracion_stats_week ─────────────────────────────────────────

    def test_week_stats_focus_check_present(self):
        text = _format_valoracion_stats_week({"orbit": 5, "appec": 0}, [], [])
        assert "✅ orbit — 5 entradas" in text
        assert "❌ appec — sin actividad" in text

    def test_week_stats_empty_focus_no_section(self):
        text = _format_valoracion_stats_week({}, [], [])
        assert "Verificación de foco" not in text

    def test_week_stats_activity_table_present(self):
        activity = [{"name": "orbit", "entries": [
            {"tipo": "resultado", "content": "x"},
            {"tipo": "apunte", "content": "y"},
        ]}]
        text = _format_valoracion_stats_week({}, activity, [])
        assert "| orbit |" in text
        assert "Actividad de la semana" in text

    def test_week_stats_no_reflection_scaffold(self):
        text = _format_valoracion_stats_week({"orbit": 2}, [], [])
        assert "Reflexión semanal" not in text

    def test_week_stats_completed_count(self):
        completed = [{"project": "p", "description": "t"}]
        text = _format_valoracion_stats_week({}, [], completed)
        assert "Tareas cerradas: 1" in text

    # ── _format_reflection_week ───────────────────────────────────────────────

    def test_reflection_week_has_three_questions(self):
        text = _format_reflection_week()
        assert "¿Qué salió bien?" in text
        assert "¿Qué no salió bien?" in text
        assert "¿Qué cambio para la próxima semana?" in text

    def test_reflection_week_heading(self):
        assert "### 🍅 Reflexión semanal" in _format_reflection_week()

    # ── _format_valoracion_stats_month ────────────────────────────────────────

    def test_month_stats_lists_projects(self):
        text = _format_valoracion_stats_month({"orbit": 12, "appec": 0})
        assert "✅ orbit — 12 entradas" in text
        assert "❌ appec — sin actividad" in text

    def test_month_stats_empty_returns_empty_string(self):
        assert _format_valoracion_stats_month({}) == ""

    # ── _format_reflection_month ──────────────────────────────────────────────

    def test_reflection_month_has_balance(self):
        assert "Balance del mes" in _format_reflection_month()

    def test_reflection_month_has_decisions(self):
        assert "🧭 Decisiones estratégicas" in _format_reflection_month()

    def test_reflection_month_has_objectives_next_month(self):
        assert "Objetivos para el mes siguiente" in _format_reflection_month()


# ═══════════════════════════════════════════════════════════════════════════════
# run_dayreport
# ═══════════════════════════════════════════════════════════════════════════════

class TestRunDayreport:

    def test_inject_updates_stats_block(self, mision_env):
        rc = run_dayreport(date_str=TODAY_ISO, inject=True)
        assert rc == 0
        text = mision_env["diario_path"].read_text()
        assert _VALORACION_STATS_START in text
        assert "🎯 Foco del día" in text

    def test_inject_shows_focus_project(self, mision_env):
        run_dayreport(date_str=TODAY_ISO, inject=True)
        text = mision_env["diario_path"].read_text()
        assert "testproj" in text

    def test_inject_does_not_add_detailed_report_to_note(self, mision_env):
        run_dayreport(date_str=TODAY_ISO, inject=True)
        text = mision_env["diario_path"].read_text()
        # Detailed activity section heading should NOT be injected into the note
        assert "## 📊 Actividad —" not in text

    def test_missing_note_returns_error_without_creating(self, mision_env):
        missing_date = (TODAY + timedelta(days=10)).isoformat()
        rc = run_dayreport(date_str=missing_date, inject=True)
        assert rc == 1
        assert not (mision_env["diario_dir"] / f"{missing_date}.md").exists()

    def test_terminal_output_without_inject(self, mision_env, capsys):
        run_dayreport(date_str=TODAY_ISO, inject=False)
        out = capsys.readouterr().out
        # Activity report printed to terminal
        assert "Actividad" in out

    def test_terminal_output_does_not_modify_note(self, mision_env):
        original = mision_env["diario_path"].read_text()
        run_dayreport(date_str=TODAY_ISO, inject=False)
        assert mision_env["diario_path"].read_text() == original

    def test_output_to_file_writes_full_report(self, mision_env, tmp_path):
        out_file = tmp_path / "dayreport.md"
        run_dayreport(date_str=TODAY_ISO, inject=False, output=str(out_file))
        assert out_file.exists()
        content = out_file.read_text()
        assert "Actividad" in content

    def test_second_inject_updates_stats_not_duplicates(self, mision_env):
        run_dayreport(date_str=TODAY_ISO, inject=True)
        run_dayreport(date_str=TODAY_ISO, inject=True)
        text = mision_env["diario_path"].read_text()
        assert text.count(_VALORACION_STATS_START) == 1


# ═══════════════════════════════════════════════════════════════════════════════
# run_weekreport
# ═══════════════════════════════════════════════════════════════════════════════

class TestRunWeekreport:

    def test_inject_updates_stats_block(self, mision_env):
        rc = run_weekreport(date_str=TODAY_ISO, inject=True)
        assert rc == 0
        text = mision_env["semanal_path"].read_text()
        assert _VALORACION_STATS_START in text
        assert "Verificación de foco" in text

    def test_inject_shows_focus_project(self, mision_env):
        run_weekreport(date_str=TODAY_ISO, inject=True)
        text = mision_env["semanal_path"].read_text()
        assert "testproj" in text

    def test_reflection_injected_on_first_call(self, mision_env):
        run_weekreport(date_str=TODAY_ISO, inject=True)
        assert _has_section(mision_env["semanal_path"], "### 🍅 Reflexión semanal")

    def test_reflection_not_overwritten_on_second_call(self, mision_env):
        run_weekreport(date_str=TODAY_ISO, inject=True)
        # User writes their reflection
        text = mision_env["semanal_path"].read_text()
        text = text.replace(
            "### 🍅 Reflexión semanal",
            "### 🍅 Reflexión semanal\n\n¡Fue una semana productiva!"
        )
        mision_env["semanal_path"].write_text(text)
        # Second call (e.g. Saturday)
        run_weekreport(date_str=TODAY_ISO, inject=True)
        assert "¡Fue una semana productiva!" in mision_env["semanal_path"].read_text()

    def test_reflection_appears_only_once(self, mision_env):
        run_weekreport(date_str=TODAY_ISO, inject=True)
        run_weekreport(date_str=TODAY_ISO, inject=True)
        text = mision_env["semanal_path"].read_text()
        assert text.count("### 🍅 Reflexión semanal") == 1

    def test_stats_updated_on_second_call(self, mision_env):
        run_weekreport(date_str=TODAY_ISO, inject=True)
        # Add another logbook entry
        mision_env["logbook"].write_text(
            "# Logbook\n"
            f"{TODAY_ISO} Entrada 1 #apunte\n"
            f"{TODAY_ISO} Entrada 2 #resultado\n"
            f"{TODAY_ISO} Entrada 3 #idea\n"
        )
        run_weekreport(date_str=TODAY_ISO, inject=True)
        # Stats block should be updated (3 entries now)
        text = mision_env["semanal_path"].read_text()
        assert "3 entradas" in text

    def test_activity_block_injected_via_wr_markers(self, mision_env):
        run_weekreport(date_str=TODAY_ISO, inject=True)
        text = mision_env["semanal_path"].read_text()
        assert _WR_START in text
        assert _WR_END in text

    def test_log_to_mission_called_only_with_inject(self, mision_env, monkeypatch):
        calls = []
        monkeypatch.setattr("core.reports.log_to_mission",
                            lambda msg, tipo: calls.append(msg))
        run_weekreport(date_str=TODAY_ISO, inject=False)
        assert calls == []
        run_weekreport(date_str=TODAY_ISO, inject=True)
        assert len(calls) == 1

    def test_missing_semanal_note_returns_error(self, mision_env):
        missing_date = (TODAY + timedelta(days=14)).isoformat()
        rc = run_weekreport(date_str=missing_date, inject=True)
        assert rc == 1

    def test_terminal_output_without_inject(self, mision_env, capsys):
        run_weekreport(date_str=TODAY_ISO, inject=False)
        out = capsys.readouterr().out
        assert "Actividad" in out

    def test_terminal_output_does_not_modify_note(self, mision_env):
        original = mision_env["semanal_path"].read_text()
        run_weekreport(date_str=TODAY_ISO, inject=False)
        assert mision_env["semanal_path"].read_text() == original


# ═══════════════════════════════════════════════════════════════════════════════
# run_shell_startup — missed session detection
# ═══════════════════════════════════════════════════════════════════════════════

class TestRunShellStartup:

    def _make_yesterday_note(self, mision_env, with_stats: bool) -> Path:
        """Create yesterday's diario note, optionally with stats already injected.

        'Stats injected' is detected by the presence of '### 📊 Actividad'
        (the distinctive heading always written by run_dayreport).
        """
        diario_dir = mision_env["diario_dir"]
        p = diario_dir / f"{YESTERDAY}.md"
        content = (
            f"# Diario — {YESTERDAY}\n\n"
            "## 📋 Planificación\n\n"
            "### 🎯 Proyecto en foco\n"
            "- [💻testproj](../../🚀proyectos/💻testproj/💻testproj.md)\n\n"
            "## 📊 Valoración\n\n"
            "<!-- orbit:valoracion-stats:start -->\n"
        )
        if with_stats:
            content += (
                "### 🎯 Foco del día\n- 🍅 testproj — 2 entradas\n\n"
                "### 📊 Actividad\n- Entradas: 2\n\n"
            )
        content += "<!-- orbit:valoracion-stats:end -->\n"
        p.write_text(content)
        return p

    def test_no_prompt_when_yesterday_has_stats(self, mision_env, monkeypatch):
        self._make_yesterday_note(mision_env, with_stats=True)
        monkeypatch.setattr("sys.stdin.isatty", lambda: True)
        inputs = []
        monkeypatch.setattr("builtins.input", lambda _: inputs.append("") or "")
        monkeypatch.setattr("core.misionlog.run_day", lambda **kw: 0)
        run_shell_startup()
        assert inputs == []   # no prompt was shown

    def test_prompts_when_yesterday_missing_stats(self, mision_env, monkeypatch):
        self._make_yesterday_note(mision_env, with_stats=False)
        monkeypatch.setattr("sys.stdin.isatty", lambda: True)
        prompted = []
        monkeypatch.setattr("builtins.input", lambda msg: prompted.append(msg) or "n")
        monkeypatch.setattr("core.misionlog.run_day", lambda **kw: 0)
        run_shell_startup()
        assert any("ayer" in p.lower() or YESTERDAY in p for p in prompted)

    def test_injects_yesterday_when_user_confirms(self, mision_env, monkeypatch):
        self._make_yesterday_note(mision_env, with_stats=False)
        monkeypatch.setattr("sys.stdin.isatty", lambda: True)
        monkeypatch.setattr("builtins.input", lambda _: "s")
        injected = []
        monkeypatch.setattr("core.misionlog.run_dayreport",
                            lambda **kw: injected.append(kw.get("date_str")) or 0)
        monkeypatch.setattr("core.misionlog.run_day", lambda **kw: 0)
        run_shell_startup()
        assert YESTERDAY in injected

    def test_skips_injection_when_user_declines(self, mision_env, monkeypatch):
        self._make_yesterday_note(mision_env, with_stats=False)
        monkeypatch.setattr("sys.stdin.isatty", lambda: True)
        monkeypatch.setattr("builtins.input", lambda _: "n")
        injected = []
        monkeypatch.setattr("core.misionlog.run_dayreport",
                            lambda **kw: injected.append(kw) or 0)
        monkeypatch.setattr("core.misionlog.run_day", lambda **kw: 0)
        run_shell_startup()
        assert injected == []

    def test_no_prompt_when_not_a_tty(self, mision_env, monkeypatch):
        self._make_yesterday_note(mision_env, with_stats=False)
        monkeypatch.setattr("sys.stdin.isatty", lambda: False)
        prompted = []
        monkeypatch.setattr("builtins.input", lambda _: prompted.append(True) or "")
        monkeypatch.setattr("core.misionlog.run_day", lambda **kw: 0)
        run_shell_startup()
        assert prompted == []

    def test_no_prompt_when_yesterday_note_missing(self, mision_env, monkeypatch):
        # Don't create yesterday's note — should not prompt
        monkeypatch.setattr("sys.stdin.isatty", lambda: True)
        prompted = []
        monkeypatch.setattr("builtins.input", lambda _: prompted.append(True) or "")
        monkeypatch.setattr("core.misionlog.run_day", lambda **kw: 0)
        run_shell_startup()
        assert prompted == []

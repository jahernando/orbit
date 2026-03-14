"""test_logbook.py — unit tests for Phase 2: log, list, search.

Covers:
  - format_entry:     tipos, emoji, [O] marker, path as link, custom date
  - add_entry:        new-format project (no status update), logbook created if missing,
                      invalid date rejected, future date rejected
  - add_orbit_entry:  appends [O] entry, silent on missing dir
  - list_entries:     no filter, by type, by date, by period, combined, [O] line handling
  - _entry_in_period: date / period_from / period_to logic
  - run_search:       keyword match, --in logbook/highlights/agenda, new-format project,
                      no results, [O] entries searchable
"""

import pytest
from datetime import date, timedelta
from pathlib import Path

from core.log import format_entry, add_entry, add_orbit_entry, VALID_TYPES
from core.list_entries import list_entries, _entry_in_period, parse_entry_type
from core.search import run_search


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def logbook_env(tmp_path, monkeypatch):
    """Isolated environment with one new-format project."""
    projects_dir = tmp_path / "🚀proyectos"
    projects_dir.mkdir()

    proj = projects_dir / "💻testproj"
    proj.mkdir()
    (proj / "testproj-project.md").write_text(
        "# 💻testproj\n- Tipo: 💻 Software\n- Estado: [auto]\n- Prioridad: alta\n"
    )
    (proj / "testproj-logbook.md").write_text("# Logbook — 💻testproj\n\n")
    (proj / "testproj-highlights.md").write_text(
        "# Highlights — 💻testproj\n\n"
        "## 📎 Referencias\n"
        "- [González 2024](./refs/g24.pdf) — calibración relativa\n\n"
        "## 📊 Resultados\n"
        "- [Presentación JINST](./results/jinst.pdf) — primera presentación\n"
    )
    (proj / "testproj-agenda.md").write_text(
        "# Agenda — 💻testproj\n\n"
        "## ✅ Tareas\n"
        "- [ ] Reproducir figura 3 (2026-03-15)\n"
    )
    (proj / "notes").mkdir()

    monkeypatch.setattr("core.log.PROJECTS_DIR",          projects_dir)
    monkeypatch.setattr("core.list_entries.PROJECTS_DIR", projects_dir)
    monkeypatch.setattr("core.search.PROJECTS_DIR",       projects_dir)

    return {"projects_dir": projects_dir, "proj": proj}


# ═══════════════════════════════════════════════════════════════════════════════
# format_entry
# ═══════════════════════════════════════════════════════════════════════════════

class TestFormatEntry:

    def test_basic_entry(self):
        e = format_entry("Nota de prueba", "apunte", None, "2026-03-09")
        assert e.startswith("2026-03-09")
        assert "#apunte" in e
        assert "Nota de prueba" in e
        assert "[O]" not in e

    def test_orbit_marker(self):
        e = format_entry("Auto entry", "apunte", None, "2026-03-09", orbit=True)
        assert e.strip().endswith("[O]")

    def test_path_becomes_link(self):
        e = format_entry("González 2024", "referencia", "./refs/g.pdf", "2026-03-09")
        assert "[González 2024](./refs/g.pdf)" in e

    def test_date_defaults_to_today(self):
        e = format_entry("Sin fecha", "apunte", None, None)
        assert e.startswith(date.today().isoformat())

    def test_evaluacion_type(self):
        e = format_entry("Evaluación parcial", "evaluacion", None, "2026-03-09")
        assert "#evaluacion" in e
        assert "🔍" in e

    def test_all_types_have_emoji(self):
        for tipo in ["idea", "referencia", "apunte", "problema",
                     "resultado", "decision", "evaluacion"]:
            e = format_entry("x", tipo, None, "2026-03-09")
            assert f"#{tipo}" in e

    def test_valid_types_includes_evaluacion(self):
        assert "evaluacion" in VALID_TYPES

    def test_valid_types_no_longer_main_tarea(self):
        # tarea still exists for backwards compat but evaluacion is now primary
        assert "evaluacion" in VALID_TYPES
        assert "tarea" in VALID_TYPES  # kept for backwards compat


# ═══════════════════════════════════════════════════════════════════════════════
# add_entry
# ═══════════════════════════════════════════════════════════════════════════════

class TestAddEntry:

    def test_adds_entry_to_logbook(self, logbook_env, capsys):
        rc = add_entry("testproj", "Primera entrada", "apunte", None, None)
        assert rc == 0
        content = (logbook_env["proj"] / "testproj-logbook.md").read_text()
        assert "Primera entrada" in content
        assert "#apunte" in content

    def test_new_project_no_status_update(self, logbook_env, capsys):
        add_entry("testproj", "Entrada test", "apunte", None, None)
        out = capsys.readouterr().out
        # New-format projects must NOT auto-update status
        assert "en marcha" not in out
        assert "estado" not in out

    def test_creates_logbook_if_missing(self, logbook_env):
        (logbook_env["proj"] / "testproj-logbook.md").unlink()
        rc = add_entry("testproj", "Primera", "apunte", None, None)
        assert rc == 0
        assert (logbook_env["proj"] / "testproj-logbook.md").exists()

    def test_invalid_date_format(self, logbook_env, capsys):
        rc = add_entry("testproj", "Msg", "apunte", None, "not-a-date")
        assert rc == 1
        assert "no es válida" in capsys.readouterr().out

    def test_future_date_rejected(self, logbook_env, capsys):
        future = (date.today() + timedelta(days=1)).isoformat()
        rc = add_entry("testproj", "Msg", "apunte", None, future)
        assert rc == 1
        assert "futura" in capsys.readouterr().out

    def test_today_date_accepted(self, logbook_env):
        today = date.today().isoformat()
        rc = add_entry("testproj", "Hoy", "apunte", None, today)
        assert rc == 0

    def test_past_date_accepted(self, logbook_env):
        past = (date.today() - timedelta(days=5)).isoformat()
        rc = add_entry("testproj", "Pasado", "apunte", None, past)
        assert rc == 0
        content = (logbook_env["proj"] / "testproj-logbook.md").read_text()
        assert past in content

    def test_orbit_flag_adds_marker(self, logbook_env):
        add_entry("testproj", "Auto", "apunte", None, None, orbit=True)
        content = (logbook_env["proj"] / "testproj-logbook.md").read_text()
        assert "[O]" in content

    def test_project_not_found(self, logbook_env, capsys):
        rc = add_entry("nonexistent", "Msg", "apunte", None, None)
        assert rc == 1

    def test_multiple_entries_appended(self, logbook_env):
        add_entry("testproj", "Primera", "apunte", None, None)
        add_entry("testproj", "Segunda", "idea", None, None)
        content = (logbook_env["proj"] / "testproj-logbook.md").read_text()
        assert "Primera" in content
        assert "Segunda" in content


# ═══════════════════════════════════════════════════════════════════════════════
# add_orbit_entry
# ═══════════════════════════════════════════════════════════════════════════════

class TestAddOrbitEntry:

    def test_adds_orbit_entry(self, logbook_env):
        add_orbit_entry(logbook_env["proj"], "[completada] Tarea: X")
        content = (logbook_env["proj"] / "testproj-logbook.md").read_text()
        assert "[completada] Tarea: X" in content
        assert "[O]" in content

    def test_silent_on_nonexistent_dir(self, tmp_path):
        ghost = tmp_path / "ghost"
        ghost.mkdir()
        # Should not raise
        add_orbit_entry(ghost, "msg")

    def test_creates_logbook_if_missing(self, logbook_env):
        (logbook_env["proj"] / "testproj-logbook.md").unlink()
        add_orbit_entry(logbook_env["proj"], "Auto entry")
        assert (logbook_env["proj"] / "testproj-logbook.md").exists()


# ═══════════════════════════════════════════════════════════════════════════════
# _entry_in_period / parse_entry_type
# ═══════════════════════════════════════════════════════════════════════════════

class TestEntryHelpers:

    def test_parse_entry_type_basic(self):
        assert parse_entry_type("2026-03-09 Nota #apunte") == "apunte"

    def test_parse_entry_type_with_orbit_marker(self):
        assert parse_entry_type("2026-03-09 Nota #apunte [O]") == "apunte"

    def test_parse_entry_type_evaluacion(self):
        assert parse_entry_type("2026-03-09 Eval #evaluacion") == "evaluacion"

    def test_parse_entry_type_unknown(self):
        assert parse_entry_type("2026-03-09 Sin tipo") is None

    def test_in_period_no_filters(self):
        assert _entry_in_period("2026-03-09 x", None, None, None) is True

    def test_in_period_exact_date_match(self):
        assert _entry_in_period("2026-03-09 x", "2026-03-09", None, None) is True

    def test_in_period_exact_date_no_match(self):
        assert _entry_in_period("2026-03-09 x", "2026-03-08", None, None) is False

    def test_in_period_month_prefix(self):
        assert _entry_in_period("2026-03-09 x", "2026-03", None, None) is True
        assert _entry_in_period("2026-04-01 x", "2026-03", None, None) is False

    def test_in_period_range_within(self):
        assert _entry_in_period("2026-03-09 x", None, "2026-03-01", "2026-03-31") is True

    def test_in_period_range_before_start(self):
        assert _entry_in_period("2026-02-28 x", None, "2026-03-01", "2026-03-31") is False

    def test_in_period_range_after_end(self):
        assert _entry_in_period("2026-04-01 x", None, "2026-03-01", "2026-03-31") is False

    def test_in_period_only_from(self):
        assert _entry_in_period("2026-03-09 x", None, "2026-03-01", None) is True
        assert _entry_in_period("2026-02-28 x", None, "2026-03-01", None) is False

    def test_in_period_only_to(self):
        assert _entry_in_period("2026-03-09 x", None, None, "2026-03-31") is True
        assert _entry_in_period("2026-04-01 x", None, None, "2026-03-31") is False


# ═══════════════════════════════════════════════════════════════════════════════
# list_entries
# ═══════════════════════════════════════════════════════════════════════════════

class TestListEntries:

    def _populate(self, proj: Path):
        (proj / "testproj-logbook.md").write_text(
            "# Logbook\n\n"
            "2026-03-01 Idea A #idea\n"
            "2026-03-05 Referencia B #referencia\n"
            "2026-03-09 Apunte C #apunte\n"
            "2026-03-09 Resultado D #resultado\n"
            "2026-03-09 Auto entry #apunte [O]\n"
        )

    def test_lists_all_entries(self, logbook_env, capsys):
        self._populate(logbook_env["proj"])
        rc = list_entries("testproj", None, None, None)
        assert rc == 0
        out = capsys.readouterr().out
        assert "Idea A" in out
        assert "Referencia B" in out
        assert "5 entradas" in out

    def test_filter_by_type(self, logbook_env, capsys):
        self._populate(logbook_env["proj"])
        list_entries("testproj", ["idea"], None, None)
        out = capsys.readouterr().out
        assert "Idea A" in out
        assert "Referencia B" not in out
        assert "1 entrada" in out

    def test_filter_by_date_exact(self, logbook_env, capsys):
        self._populate(logbook_env["proj"])
        list_entries("testproj", None, "2026-03-09", None)
        out = capsys.readouterr().out
        assert "Apunte C" in out
        assert "Idea A" not in out
        assert "3 entradas" in out

    def test_filter_by_date_month(self, logbook_env, capsys):
        self._populate(logbook_env["proj"])
        list_entries("testproj", None, "2026-03", None)
        out = capsys.readouterr().out
        assert "5 entradas" in out

    def test_filter_by_period(self, logbook_env, capsys):
        self._populate(logbook_env["proj"])
        list_entries("testproj", None, None, None,
                     period_from="2026-03-05", period_to="2026-03-09")
        out = capsys.readouterr().out
        assert "Referencia B" in out
        assert "Apunte C" in out
        assert "Idea A" not in out
        assert "4 entradas" in out

    def test_orbit_entries_included(self, logbook_env, capsys):
        self._populate(logbook_env["proj"])
        list_entries("testproj", None, None, None)
        out = capsys.readouterr().out
        assert "Auto entry" in out
        assert "[O]" in out

    def test_orbit_entries_filter_by_type(self, logbook_env, capsys):
        self._populate(logbook_env["proj"])
        list_entries("testproj", ["apunte"], None, None)
        out = capsys.readouterr().out
        # Both manual apunte and [O] apunte should appear
        assert "Apunte C" in out
        assert "Auto entry" in out

    def test_empty_logbook(self, logbook_env, capsys):
        list_entries("testproj", None, None, None)
        out = capsys.readouterr().out
        assert "0 entradas" in out

    def test_project_not_found(self, logbook_env, capsys):
        rc = list_entries("nonexistent", None, None, None)
        assert rc == 1

    def test_save_to_output(self, logbook_env, tmp_path):
        self._populate(logbook_env["proj"])
        out_file = str(tmp_path / "out.txt")
        rc = list_entries("testproj", None, None, out_file)
        assert rc == 0
        assert Path(out_file).exists()
        content = Path(out_file).read_text()
        assert "Idea A" in content


# ═══════════════════════════════════════════════════════════════════════════════
# run_search — logbook / highlights / agenda
# ═══════════════════════════════════════════════════════════════════════════════

class TestRunSearch:

    def _populate_logbook(self, proj: Path):
        (proj / "testproj-logbook.md").write_text(
            "# Logbook\n\n"
            "2026-03-09 Calibración relativa discutida #apunte\n"
            "2026-03-08 [González 2024](./refs/g.pdf) #referencia\n"
            "2026-03-07 El fit no converge #problema\n"
        )

    def test_keyword_match_logbook(self, logbook_env, capsys):
        self._populate_logbook(logbook_env["proj"])
        rc = run_search("calibración")
        assert rc == 0
        out = capsys.readouterr().out
        assert "Calibración" in out

    def test_keyword_no_match(self, logbook_env, capsys):
        self._populate_logbook(logbook_env["proj"])
        run_search("neutrino")
        out = capsys.readouterr().out
        assert "Sin resultados" in out

    def test_search_highlights(self, logbook_env, capsys):
        self._populate_logbook(logbook_env["proj"])
        run_search("calibración", in_filter="highlights")
        out = capsys.readouterr().out
        assert "calibración" in out.lower()
        assert "testproj-highlights.md" in out

    def test_search_agenda(self, logbook_env, capsys):
        self._populate_logbook(logbook_env["proj"])
        run_search("figura", in_filter="agenda")
        out = capsys.readouterr().out
        assert "figura" in out.lower()
        assert "testproj-agenda.md" in out

    def test_search_logbook_explicit(self, logbook_env, capsys):
        self._populate_logbook(logbook_env["proj"])
        run_search("converge", in_filter="logbook")
        out = capsys.readouterr().out
        assert "converge" in out

    def test_orbit_entries_searchable(self, logbook_env, capsys):
        (logbook_env["proj"] / "testproj-logbook.md").write_text(
            "# Logbook\n\n"
            "2026-03-09 [completada] Tarea: Revisión #apunte [O]\n"
        )
        run_search("completada")
        out = capsys.readouterr().out
        assert "completada" in out

    def test_search_specific_project(self, logbook_env, capsys):
        self._populate_logbook(logbook_env["proj"])
        run_search("calibración", projects=["testproj"])
        out = capsys.readouterr().out
        assert "Calibración" in out

    def test_search_nonexistent_project(self, logbook_env, capsys):
        rc = run_search("x", projects=["nonexistent"])
        assert rc == 1

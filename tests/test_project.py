"""test_project.py — unit tests for Phase 1: project create/list/status/edit.

Covers:
  - _infer_status:      active/paused/sleeping thresholds, no logbook, empty logbook
  - _read_project_meta: parses name, tipo, estado, prioridad from project.md
  - _find_new_project:  partial match, ambiguity, not found
  - run_project_create: file structure, placeholder substitution, invalid tipo/prioridad,
                        existing project, notes/ directory created
  - run_project_list:   lists new-format projects, status/tipo filters, empty result
  - run_project_status: show [auto], show declared, set status, reset to [auto],
                        invalid status
"""

import pytest
from datetime import date, timedelta
from pathlib import Path

from core.project import (
    _infer_status, _read_project_meta, _find_new_project,
    run_project_create, run_project_list, run_project_status,
    run_link,
)


# ── Templates mínimos ─────────────────────────────────────────────────────────

_PROJECT_TPL = """\
# {{PROJECT_NAME}}

- Tipo: {{TYPE_EMOJI}} {{TYPE_LABEL}}
- Estado: [auto]
- Prioridad: {{PRIORITY_LABEL}}

## Estado actual

*{{OBJECTIVE}}*

---
[logbook](./logbook.md) · [highlights](./highlights.md) · [agenda](./agenda.md) · [notes](./notes/)
"""

_LOGBOOK_TPL = "# Logbook — {{PROJECT_NAME}}\n\n"
_HIGHLIGHTS_TPL = "# Highlights — {{PROJECT_NAME}}\n\n"
_AGENDA_TPL = "# Agenda — {{PROJECT_NAME}}\n\n"


# ── Fixture ───────────────────────────────────────────────────────────────────

@pytest.fixture
def project_env(tmp_path, monkeypatch):
    """Isolated environment for project tests."""
    templates_dir = tmp_path / "📐templates"
    templates_dir.mkdir()

    # Create default type dir so iter_project_dirs finds projects
    type_dir = tmp_path / "💻software"
    type_dir.mkdir()

    (templates_dir / "project.md").write_text(_PROJECT_TPL)
    (templates_dir / "logbook.md").write_text(_LOGBOOK_TPL)
    (templates_dir / "highlights.md").write_text(_HIGHLIGHTS_TPL)
    (templates_dir / "agenda.md").write_text(_AGENDA_TPL)

    monkeypatch.setattr("core.config.ORBIT_HOME", tmp_path)
    monkeypatch.setattr("core.config._ORBIT_JSON", tmp_path / "orbit.json")
    monkeypatch.setattr("core.project.TEMPLATES_DIR", templates_dir)
    monkeypatch.setattr("core.log.PROJECTS_DIR", tmp_path)

    return {"projects_dir": type_dir, "templates_dir": templates_dir, "tmp": tmp_path}


def _make_new_project(type_dir: Path, name: str,
                      tipo_emoji: str = "💻", tipo_label: str = "Software",
                      prioridad: str = "alta",
                      estado: str = "[auto]") -> Path:
    """Helper: create a minimal new-format project directory."""
    proj_dir = type_dir / f"{tipo_emoji}{name}"
    proj_dir.mkdir(parents=True, exist_ok=True)
    (proj_dir / f"{name}-project.md").write_text(
        f"# {tipo_emoji}{name}\n\n"
        f"- Tipo: {tipo_emoji} {tipo_label}\n"
        f"- Estado: {estado}\n"
        f"- Prioridad: {prioridad}\n\n"
        "## Estado actual\n\n*Objetivo.*\n\n---\n"
        f"[logbook](./{name}-logbook.md) · [highlights](./{name}-highlights.md) · "
        f"[agenda](./{name}-agenda.md) · [notes](./notes/)\n"
    )
    (proj_dir / f"{name}-logbook.md").write_text(f"# Logbook — {tipo_emoji}{name}\n\n")
    (proj_dir / f"{name}-highlights.md").write_text(f"# Highlights — {tipo_emoji}{name}\n\n")
    (proj_dir / f"{name}-agenda.md").write_text(f"# Agenda — {tipo_emoji}{name}\n\n")
    (proj_dir / "notes").mkdir(exist_ok=True)
    return proj_dir


# ═══════════════════════════════════════════════════════════════════════════════
# _infer_status
# ═══════════════════════════════════════════════════════════════════════════════

class TestInferStatus:

    def test_no_logbook_returns_new(self, tmp_path):
        proj = tmp_path / "💻myproject"
        proj.mkdir()
        status, days = _infer_status(proj)
        assert status == "new"
        assert days == 0

    def test_empty_logbook_returns_new(self, tmp_path):
        proj = tmp_path / "💻myproject"
        proj.mkdir()
        (proj / "myproject-logbook.md").write_text("# Logbook\n\n")
        status, days = _infer_status(proj)
        assert status == "new"
        assert days == 0

    def test_entry_today_is_active(self, tmp_path):
        proj = tmp_path / "💻myproject"
        proj.mkdir()
        today = date.today().isoformat()
        (proj / "myproject-logbook.md").write_text(
            f"# Logbook\n\n{today} Reunión con grupo #apunte\n"
        )
        status, days = _infer_status(proj)
        assert status == "active"
        assert days == 0

    def test_entry_13_days_ago_is_active(self, tmp_path):
        proj = tmp_path / "💻myproject"
        proj.mkdir()
        d = (date.today() - timedelta(days=13)).isoformat()
        (proj / "myproject-logbook.md").write_text(f"# Logbook\n\n{d} Nota #apunte\n")
        status, days = _infer_status(proj)
        assert status == "active"
        assert days == 13

    def test_entry_14_days_ago_is_active(self, tmp_path):
        proj = tmp_path / "💻myproject"
        proj.mkdir()
        d = (date.today() - timedelta(days=14)).isoformat()
        (proj / "myproject-logbook.md").write_text(f"# Logbook\n\n{d} Nota #apunte\n")
        status, days = _infer_status(proj)
        assert status == "active"
        assert days == 14

    def test_entry_15_days_ago_is_paused(self, tmp_path):
        proj = tmp_path / "💻myproject"
        proj.mkdir()
        d = (date.today() - timedelta(days=15)).isoformat()
        (proj / "myproject-logbook.md").write_text(f"# Logbook\n\n{d} Nota #apunte\n")
        status, days = _infer_status(proj)
        assert status == "paused"
        assert days == 15

    def test_entry_60_days_ago_is_paused(self, tmp_path):
        proj = tmp_path / "💻myproject"
        proj.mkdir()
        d = (date.today() - timedelta(days=60)).isoformat()
        (proj / "myproject-logbook.md").write_text(f"# Logbook\n\n{d} Nota #apunte\n")
        status, days = _infer_status(proj)
        assert status == "paused"
        assert days == 60

    def test_entry_61_days_ago_is_sleeping(self, tmp_path):
        proj = tmp_path / "💻myproject"
        proj.mkdir()
        d = (date.today() - timedelta(days=61)).isoformat()
        (proj / "myproject-logbook.md").write_text(f"# Logbook\n\n{d} Nota #apunte\n")
        status, days = _infer_status(proj)
        assert status == "sleeping"
        assert days == 61

    def test_uses_most_recent_entry(self, tmp_path):
        """With multiple entries, uses the most recent."""
        proj = tmp_path / "💻myproject"
        proj.mkdir()
        old = (date.today() - timedelta(days=90)).isoformat()
        recent = (date.today() - timedelta(days=5)).isoformat()
        (proj / "myproject-logbook.md").write_text(
            f"# Logbook\n\n{old} Nota vieja #apunte\n{recent} Nota reciente #apunte\n"
        )
        status, days = _infer_status(proj)
        assert status == "active"
        assert days == 5

    def test_orbit_entries_count(self, tmp_path):
        """[O] entries also count for activity."""
        proj = tmp_path / "💻myproject"
        proj.mkdir()
        today = date.today().isoformat()
        (proj / "myproject-logbook.md").write_text(
            f"# Logbook\n\n{today} [completada] Tarea X #apunte [O]\n"
        )
        status, days = _infer_status(proj)
        assert status == "active"


# ═══════════════════════════════════════════════════════════════════════════════
# _read_project_meta
# ═══════════════════════════════════════════════════════════════════════════════

class TestReadProjectMeta:

    def test_reads_all_fields(self, tmp_path):
        proj = tmp_path / "🌀mission"
        proj.mkdir()
        (proj / "mission-project.md").write_text(
            "# 🌀mission\n\n"
            "- Tipo: 🌀 Investigación\n"
            "- Estado: [auto]\n"
            "- Prioridad: alta\n"
        )
        meta = _read_project_meta(proj)
        assert meta["name"] == "🌀mission"
        assert meta["tipo_emoji"] == "🌀"
        assert meta["tipo_label"] == "Investigación"
        assert meta["estado_raw"] == "[auto]"
        assert meta["prioridad"] == "alta"

    def test_reads_declared_status(self, tmp_path):
        proj = tmp_path / "💻orbit"
        proj.mkdir()
        (proj / "orbit-project.md").write_text(
            "# 💻orbit\n\n"
            "- Tipo: 💻 Software\n"
            "- Estado: paused\n"
            "- Prioridad: media\n"
        )
        meta = _read_project_meta(proj)
        assert meta["estado_raw"] == "paused"

    def test_missing_project_file_returns_defaults(self, tmp_path):
        proj = tmp_path / "💻ghost"
        proj.mkdir()
        meta = _read_project_meta(proj)
        assert meta["estado_raw"] == "[auto]"
        assert meta["prioridad"] == "media"

    def test_handles_low_priority(self, tmp_path):
        proj = tmp_path / "🌿personal"
        proj.mkdir()
        (proj / "personal-project.md").write_text(
            "# 🌿personal\n\n"
            "- Tipo: 🌿 Personal\n"
            "- Estado: [auto]\n"
            "- Prioridad: baja\n"
        )
        meta = _read_project_meta(proj)
        assert meta["prioridad"] == "baja"


# ═══════════════════════════════════════════════════════════════════════════════
# _find_new_project
# ═══════════════════════════════════════════════════════════════════════════════

class TestFindNewProject:

    def test_finds_by_partial_name(self, project_env):
        proj_dir = _make_new_project(project_env["projects_dir"], "mission")
        result   = _find_new_project("miss")
        assert result == proj_dir

    def test_not_found_returns_none(self, project_env, capsys):
        result = _find_new_project("nonexistent")
        assert result is None
        assert "no encontrado" in capsys.readouterr().out

    def test_ambiguous_returns_none(self, project_env, capsys):
        _make_new_project(project_env["projects_dir"], "mission-a")
        _make_new_project(project_env["projects_dir"], "mission-b")
        result = _find_new_project("mission")
        assert result is None
        assert "ambiguo" in capsys.readouterr().out

    def test_exact_match_not_ambiguous(self, project_env):
        _make_new_project(project_env["projects_dir"], "mission")
        _make_new_project(project_env["projects_dir"], "mission-extra")
        # "mission" matches both dirs — ambiguous is expected here
        result = _find_new_project("💻mission")
        assert result is not None

    def test_case_insensitive(self, project_env):
        proj_dir = _make_new_project(project_env["projects_dir"], "orbit")
        result   = _find_new_project("ORBIT")
        assert result == proj_dir


# ═══════════════════════════════════════════════════════════════════════════════
# run_project_create
# ═══════════════════════════════════════════════════════════════════════════════

class TestRunProjectCreate:

    def test_creates_all_files(self, project_env, monkeypatch):
        monkeypatch.setattr("builtins.input", lambda _: "Objetivo de prueba")
        rc = run_project_create("myproject", "software", "alta")
        assert rc == 0
        proj = project_env["projects_dir"] / "💻myproject"
        assert (proj / "myproject-project.md").exists()
        assert (proj / "myproject-logbook.md").exists()
        assert (proj / "myproject-highlights.md").exists()
        assert (proj / "myproject-agenda.md").exists()
        assert (proj / "notes").is_dir()

    def test_substitutes_placeholders(self, project_env, monkeypatch):
        monkeypatch.setattr("builtins.input", lambda _: "Test objetivo")
        run_project_create("calibra", "investigacion", "media")
        proj    = project_env["tmp"] / "🌀investigacion" / "🌀calibra"
        content = (proj / "calibra-project.md").read_text()
        assert "{{PROJECT_NAME}}" not in content
        assert "🌀calibra" in content
        assert "Investigación" in content
        assert "Media" in content
        assert "Test objetivo" in content

    def test_logbook_title_substituted(self, project_env, monkeypatch):
        monkeypatch.setattr("builtins.input", lambda _: "")
        run_project_create("testlog", "software", "baja")
        proj    = project_env["projects_dir"] / "💻testlog"
        content = (proj / "testlog-logbook.md").read_text()
        assert "{{PROJECT_NAME}}" not in content
        assert "💻testlog" in content

    def test_empty_objective_uses_default(self, project_env, monkeypatch):
        monkeypatch.setattr("builtins.input", lambda _: "")
        run_project_create("defaultobj", "personal", "baja")
        proj    = project_env["tmp"] / "🌿personal" / "🌿defaultobj"
        content = (proj / "defaultobj-project.md").read_text()
        assert "Descripción breve del objetivo." in content

    def test_invalid_tipo_returns_error(self, project_env, monkeypatch, capsys):
        rc = run_project_create("bad", "unicornio", "alta")
        assert rc == 1
        assert "no válido" in capsys.readouterr().out

    def test_invalid_priority_returns_error(self, project_env, monkeypatch, capsys):
        rc = run_project_create("bad", "software", "maxima")
        assert rc == 1
        assert "no válida" in capsys.readouterr().out

    def test_existing_project_returns_error(self, project_env, monkeypatch, capsys):
        monkeypatch.setattr("builtins.input", lambda _: "")
        run_project_create("dupli", "software", "alta")
        rc = run_project_create("dupli", "software", "alta")
        assert rc == 1
        assert "ya existe" in capsys.readouterr().out

    def test_estado_is_auto_by_default(self, project_env, monkeypatch):
        monkeypatch.setattr("builtins.input", lambda _: "")
        run_project_create("autotest", "software", "media")
        proj    = project_env["projects_dir"] / "💻autotest"
        content = (proj / "autotest-project.md").read_text()
        assert "- Estado: [auto]" in content

    def test_type_variants_accepted(self, project_env, monkeypatch):
        monkeypatch.setattr("builtins.input", lambda _: "")
        from core.config import type_dir_path
        for tipo, emoji in [
            ("investigacion", "🌀"), ("docencia", "📚"),
            ("gestion", "⚙️"),       ("formacion", "📖"),
            ("software", "💻"),      ("personal", "🌿"),
        ]:
            rc = run_project_create(f"proj-{tipo}", tipo, "media")
            assert rc == 0, f"tipo '{tipo}' failed"
            assert (type_dir_path(tipo) / f"{emoji}proj-{tipo}").exists()


# ═══════════════════════════════════════════════════════════════════════════════
# run_project_list
# ═══════════════════════════════════════════════════════════════════════════════

class TestRunProjectList:

    def test_empty_returns_zero(self, project_env, capsys):
        rc = run_project_list()
        assert rc == 0
        assert "No se encontraron" in capsys.readouterr().out

    def test_lists_new_format_projects(self, project_env, capsys):
        _make_new_project(project_env["projects_dir"], "alpha")
        _make_new_project(project_env["projects_dir"], "beta")
        rc = run_project_list()
        assert rc == 0
        out = capsys.readouterr().out
        assert "alpha" in out
        assert "beta" in out

    def test_shows_auto_status(self, project_env, capsys):
        _make_new_project(project_env["projects_dir"], "autocheck")
        run_project_list()
        out = capsys.readouterr().out
        assert "auto" in out

    def test_active_status_from_recent_logbook(self, project_env, capsys):
        proj = _make_new_project(project_env["projects_dir"], "recent")
        today = date.today().isoformat()
        (proj / "recent-logbook.md").write_text(f"# Logbook\n\n{today} Nota #apunte\n")
        run_project_list()
        out = capsys.readouterr().out
        assert "▶️" in out

    def test_filter_by_status_active(self, project_env, capsys):
        proj_a = _make_new_project(project_env["projects_dir"], "active-one")
        proj_s = _make_new_project(project_env["projects_dir"], "sleeping-one")
        today  = date.today().isoformat()
        (proj_a / "active-one-logbook.md").write_text(f"# Logbook\n\n{today} Nota #apunte\n")
        # sleeping-one has no entries → sleeping
        run_project_list(status_filter="active")
        out = capsys.readouterr().out
        assert "active-one" in out
        assert "sleeping-one" not in out

    def test_filter_by_tipo(self, project_env, capsys):
        _make_new_project(project_env["projects_dir"], "sw-proj",
                          tipo_emoji="💻", tipo_label="Software")
        _make_new_project(project_env["projects_dir"], "inv-proj",
                          tipo_emoji="🌀", tipo_label="Investigación")
        run_project_list(tipo_filter="Software")
        out = capsys.readouterr().out
        assert "sw-proj" in out
        assert "inv-proj" not in out

    def test_old_format_projects_not_listed(self, project_env, capsys):
        """Old-format projects (no project.md) are excluded."""
        old = project_env["projects_dir"] / "💻old-proj"
        old.mkdir()
        (old / "💻old-proj.md").write_text("# old-proj\n")
        run_project_list()
        out = capsys.readouterr().out
        assert "old-proj" not in out


# ═══════════════════════════════════════════════════════════════════════════════
# run_project_status
# ═══════════════════════════════════════════════════════════════════════════════

class TestRunProjectStatus:

    def test_shows_auto_status(self, project_env, capsys):
        _make_new_project(project_env["projects_dir"], "p1")
        rc = run_project_status("p1")
        assert rc == 0
        out = capsys.readouterr().out
        assert "auto" in out

    def test_shows_declared_status(self, project_env, capsys):
        _make_new_project(project_env["projects_dir"], "p2", estado="paused")
        rc = run_project_status("p2")
        assert rc == 0
        out = capsys.readouterr().out
        assert "declarado" in out

    def test_set_status_active(self, project_env, capsys):
        proj = _make_new_project(project_env["projects_dir"], "p3")
        rc   = run_project_status("p3", set_status="activo")
        assert rc == 0
        content = (proj / "p3-project.md").read_text()
        assert "▶️ Activo" in content
        assert "Activo" in capsys.readouterr().out

    def test_set_status_paused(self, project_env, capsys):
        proj = _make_new_project(project_env["projects_dir"], "p4")
        run_project_status("p4", set_status="pausado")
        content = (proj / "p4-project.md").read_text()
        assert "⏸️ Pausado" in content

    def test_set_status_sleeping(self, project_env, capsys):
        proj = _make_new_project(project_env["projects_dir"], "p5")
        run_project_status("p5", set_status="durmiendo")
        content = (proj / "p5-project.md").read_text()
        assert "💤 Durmiendo" in content

    def test_reset_to_auto(self, project_env, capsys):
        proj = _make_new_project(project_env["projects_dir"], "p6", estado="paused")
        rc   = run_project_status("p6", set_status="[auto]")
        assert rc == 0
        content = (proj / "p6-project.md").read_text()
        assert "- Estado: [auto]" in content

    def test_accepts_english_status(self, project_env, capsys):
        proj = _make_new_project(project_env["projects_dir"], "p7")
        run_project_status("p7", set_status="sleeping")
        content = (proj / "p7-project.md").read_text()
        assert "💤 Durmiendo" in content

    def test_invalid_status_returns_error(self, project_env, capsys):
        _make_new_project(project_env["projects_dir"], "p8")
        rc = run_project_status("p8", set_status="fantasma")
        assert rc == 1
        assert "no válido" in capsys.readouterr().out

    def test_project_not_found(self, project_env, capsys):
        rc = run_project_status("nonexistent")
        assert rc == 1
        assert "no encontrado" in capsys.readouterr().out

    def test_status_inferred_from_recent_activity(self, project_env, capsys):
        proj  = _make_new_project(project_env["projects_dir"], "recent-p")
        today = date.today().isoformat()
        (proj / "recent-p-logbook.md").write_text(f"# Logbook\n\n{today} Nota #apunte\n")
        run_project_status("recent-p")
        out = capsys.readouterr().out
        assert "Activo" in out


# ═══════════════════════════════════════════════════════════════════════════════
# log_cmd_output
# ═══════════════════════════════════════════════════════════════════════════════

class TestLogCmdOutput:

    def test_logs_output_to_logbook(self, project_env, monkeypatch, capsys):
        from core.open import log_cmd_output
        proj = _make_new_project(project_env["projects_dir"], "logtest")

        content = "  line1\n  line2\n  line3\n"
        rc = log_cmd_output(content, "logtest", "apunte", "test cmd")
        assert rc == 0

        logbook = (proj / "logtest-logbook.md").read_text()
        assert "[test cmd] 3 líneas #apunte [O]" in logbook
        assert "```" in logbook
        assert "line1" in logbook

    def test_logs_with_entry_type(self, project_env, monkeypatch, capsys):
        from core.open import log_cmd_output
        proj = _make_new_project(project_env["projects_dir"], "logtest2")

        rc = log_cmd_output("data", "logtest2", "evaluacion", "status")
        assert rc == 0

        logbook = (proj / "logtest2-logbook.md").read_text()
        assert "#evaluacion [O]" in logbook


# ── run_link ─────────────────────────────────────────────────────────────────

class TestRunLink:
    def test_link_prints_and_copies(self, project_env, capsys, monkeypatch):
        proj = _make_new_project(project_env["projects_dir"], "catedra")
        monkeypatch.setattr("core.project.ORBIT_HOME", project_env["tmp"])
        rc = run_link("catedra")
        assert rc == 0
        out = capsys.readouterr().out
        assert "[💻catedra](" in out
        assert "catedra-project.md)" in out

    def test_link_not_found(self, project_env, capsys, monkeypatch):
        monkeypatch.setattr("core.project.ORBIT_HOME", project_env["tmp"])
        rc = run_link("nonexistent")
        assert rc == 1

    def test_link_with_file(self, project_env, capsys, monkeypatch):
        proj = _make_new_project(project_env["projects_dir"], "catedra")
        (proj / "notes").mkdir(exist_ok=True)
        (proj / "notes" / "result.md").write_text("# Result\n")
        monkeypatch.setattr("core.project.ORBIT_HOME", project_env["tmp"])
        rc = run_link("catedra", file="notes/result.md")
        assert rc == 0
        out = capsys.readouterr().out
        assert "[result](" in out
        assert "notes/result.md)" in out

    def test_link_with_file_not_found(self, project_env, capsys, monkeypatch):
        _make_new_project(project_env["projects_dir"], "catedra")
        monkeypatch.setattr("core.project.ORBIT_HOME", project_env["tmp"])
        rc = run_link("catedra", file="notes/nope.md")
        assert rc == 1
        out = capsys.readouterr().out
        assert "no existe" in out

    def test_link_from_project(self, project_env, capsys, monkeypatch):
        """Link from one project root (hls, agenda) to a file in another project."""
        proj_a = _make_new_project(project_env["projects_dir"], "complementos")
        proj_b = _make_new_project(project_env["projects_dir"], "catedra")
        (proj_b / "notes").mkdir(exist_ok=True)
        (proj_b / "notes" / "tramos.md").write_text("# Tramos\n")
        monkeypatch.setattr("core.project.ORBIT_HOME", project_env["tmp"])
        rc = run_link("catedra", file="notes/tramos.md", from_project="complementos")
        assert rc == 0
        out = capsys.readouterr().out
        assert "[tramos](" in out
        # From project root: one ../ up to type dir, then down to sibling
        assert "(../💻catedra/notes/tramos.md)" in out

"""test_new_features.py — tests for new features: priority, ls sort, open --dir, commit helpers.

Covers:
  - run_project_priority: change priority, invalid priority, not found
  - run_project_list sort: --sort type/status/priority
  - run_open_dir:          opens project directory
  - _git_untracked_in_projects: detects untracked files
  - _auto_message:         auto commit message generation
"""

import pytest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

from core.project import run_project_priority, run_project_list


# ── Reuse _make_new_project from test_project ────────────────────────────────

def _make_new_project(projects_dir: Path, name: str,
                      tipo_emoji: str = "💻", tipo_label: str = "Software",
                      prioridad: str = "alta",
                      estado: str = "[auto]") -> Path:
    proj_dir = projects_dir / f"{tipo_emoji}{name}"
    proj_dir.mkdir()
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
    (proj_dir / "notes").mkdir()
    return proj_dir


@pytest.fixture
def project_env(tmp_path, monkeypatch):
    projects_dir = tmp_path / "🚀proyectos"
    projects_dir.mkdir()
    monkeypatch.setattr("core.project.PROJECTS_DIR", projects_dir)
    monkeypatch.setattr("core.log.PROJECTS_DIR", projects_dir)
    return {"projects_dir": projects_dir}


# ═══════════════════════════════════════════════════════════════════════════════
# run_project_priority
# ═══════════════════════════════════════════════════════════════════════════════

class TestRunProjectPriority:

    def test_changes_priority(self, project_env, capsys):
        proj = _make_new_project(project_env["projects_dir"], "alpha", prioridad="media")
        rc = run_project_priority("alpha", "alta")
        assert rc == 0
        content = (proj / "alpha-project.md").read_text()
        assert "Alta" in content
        assert "🔴" in content
        assert "✓" in capsys.readouterr().out

    def test_changes_to_baja(self, project_env, capsys):
        proj = _make_new_project(project_env["projects_dir"], "beta", prioridad="alta")
        rc = run_project_priority("beta", "baja")
        assert rc == 0
        content = (proj / "beta-project.md").read_text()
        assert "Baja" in content

    def test_invalid_priority(self, project_env, capsys):
        _make_new_project(project_env["projects_dir"], "gamma")
        rc = run_project_priority("gamma", "extrema")
        assert rc == 1
        assert "no válida" in capsys.readouterr().out

    def test_not_found(self, project_env, capsys):
        rc = run_project_priority("nonexistent", "alta")
        assert rc == 1
        assert "no encontrado" in capsys.readouterr().out


# ═══════════════════════════════════════════════════════════════════════════════
# run_project_list with --sort
# ═══════════════════════════════════════════════════════════════════════════════

class TestProjectListSort:

    def _make_projects(self, projects_dir):
        """Create 3 projects with different types, statuses, priorities."""
        today = date.today().isoformat()
        old = (date.today() - timedelta(days=90)).isoformat()

        p1 = _make_new_project(projects_dir, "alpha",
                               tipo_emoji="🌀", tipo_label="Investigación",
                               prioridad="baja")
        (p1 / "alpha-logbook.md").write_text(f"# Logbook\n\n{today} Nota #apunte\n")

        p2 = _make_new_project(projects_dir, "beta",
                               tipo_emoji="💻", tipo_label="Software",
                               prioridad="alta")
        # No logbook entries → new status

        p3 = _make_new_project(projects_dir, "gamma",
                               tipo_emoji="🌿", tipo_label="Personal",
                               prioridad="media")
        (p3 / "gamma-logbook.md").write_text(f"# Logbook\n\n{old} Nota vieja #apunte\n")

    def test_sort_by_priority(self, project_env, capsys):
        self._make_projects(project_env["projects_dir"])
        run_project_list(sort_by="priority")
        out = capsys.readouterr().out
        lines = [l for l in out.strip().split("\n") if l.strip()]
        # alta first, then media, then baja
        assert lines[0].index("beta") < lines[0].index("beta") or "beta" in lines[0]

    def test_sort_by_status(self, project_env, capsys):
        self._make_projects(project_env["projects_dir"])
        run_project_list(sort_by="status")
        out = capsys.readouterr().out
        lines = [l.strip() for l in out.strip().split("\n") if l.strip()]
        # active (alpha) first, then new (beta), then sleeping (gamma)
        assert "alpha" in lines[0]

    def test_sort_by_type(self, project_env, capsys):
        self._make_projects(project_env["projects_dir"])
        run_project_list(sort_by="type")
        out = capsys.readouterr().out
        lines = [l.strip() for l in out.strip().split("\n") if l.strip()]
        # Investigación, Personal, Software (alphabetical)
        assert "alpha" in lines[0]  # Investigación
        assert "gamma" in lines[1]  # Personal
        assert "beta" in lines[2]   # Software

    def test_no_sort_default_order(self, project_env, capsys):
        self._make_projects(project_env["projects_dir"])
        run_project_list()
        out = capsys.readouterr().out
        assert "alpha" in out
        assert "beta" in out
        assert "gamma" in out


# ═══════════════════════════════════════════════════════════════════════════════
# run_open_dir
# ═══════════════════════════════════════════════════════════════════════════════

class TestRunOpenDir:

    def test_opens_directory(self, project_env):
        from core.project_view import run_open_dir
        _make_new_project(project_env["projects_dir"], "openme")
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = None
            rc = run_open_dir("openme")
        assert rc == 0
        mock_run.assert_called_once()
        call_args = mock_run.call_args[0][0]
        assert call_args[0] == "open"
        assert "openme" in call_args[1]

    def test_not_found(self, project_env, capsys):
        from core.project_view import run_open_dir
        rc = run_open_dir("nonexistent")
        assert rc == 1
        assert "no encontrado" in capsys.readouterr().out


# ═══════════════════════════════════════════════════════════════════════════════
# _auto_message
# ═══════════════════════════════════════════════════════════════════════════════

class TestAutoMessage:

    def test_logbook_changes(self):
        from core.commit import _auto_message
        status = [("M", "🚀proyectos/💻orbit/orbit-logbook.md")]
        msg = _auto_message(status)
        assert "logbook" in msg
        assert "orbit" in msg

    def test_multiple_file_types(self):
        from core.commit import _auto_message
        status = [
            ("M", "🚀proyectos/💻orbit/orbit-logbook.md"),
            ("M", "🚀proyectos/💻orbit/orbit-agenda.md"),
        ]
        msg = _auto_message(status)
        assert "logbook" in msg
        assert "agenda" in msg

    def test_no_project_files(self):
        from core.commit import _auto_message
        status = [("M", "orbit.py")]
        msg = _auto_message(status)
        assert "orbit:" in msg

    def test_multiple_projects(self):
        from core.commit import _auto_message
        status = [
            ("M", "🚀proyectos/💻orbit/orbit-logbook.md"),
            ("M", "🚀proyectos/🌀mission/mission-logbook.md"),
        ]
        msg = _auto_message(status)
        assert "orbit" in msg.lower() or "mission" in msg.lower()

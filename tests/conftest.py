"""conftest.py — shared fixtures for Orbit tests.

Creates an isolated temporary project structure so tests never touch real data.
"""

import pytest
from pathlib import Path
from datetime import date


# ── Minimal project template ───────────────────────────────────────────────────

_PROYECTO_TEMPLATE = """\
# {name}

💻 Software
▶️ En marcha
🔴 Alta

## 🎯 Objetivo
Proyecto de prueba para tests.

## ✅ Tareas

## 📎 Referencias
-

## 📊 Resultados
-

## 📌 Decisiones
-

## 📓 Logbook
[Ver logbook completo](./logbook.md)
"""


# ── Fixture principal ──────────────────────────────────────────────────────────

@pytest.fixture
def orbit_env(tmp_path, monkeypatch):
    """Set up an isolated Orbit environment with one test project."""
    templates_dir = tmp_path / "📐templates"
    templates_dir.mkdir()

    # Type dir for software projects
    type_dir = tmp_path / "💻software"
    type_dir.mkdir()

    # Test project: 💻testproj inside type dir
    proj_dir = type_dir / "💻testproj"
    proj_dir.mkdir()
    proyecto_path = proj_dir / "💻testproj.md"
    proyecto_path.write_text(_PROYECTO_TEMPLATE.format(name="testproj"))
    (proj_dir / "📓testproj.md").write_text("# Logbook\n")

    # Patch ORBIT_HOME so iter_project_dirs() finds type dirs under tmp_path
    monkeypatch.setattr("core.config.ORBIT_HOME", tmp_path)
    monkeypatch.setattr("core.config._ORBIT_JSON", tmp_path / "orbit.json")
    monkeypatch.setattr("core.log.PROJECTS_DIR", tmp_path)

    return {
        "tmp":           tmp_path,
        "projects_dir":  type_dir,
        "templates_dir": templates_dir,
        "proj_dir":      proj_dir,
        "proyecto_path": proyecto_path,
        "today":         date.today().isoformat(),
    }

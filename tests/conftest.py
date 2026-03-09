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
    projects_dir  = tmp_path / "🚀proyectos"
    templates_dir = tmp_path / "📐templates"

    projects_dir.mkdir()
    templates_dir.mkdir()

    # Test project: 💻testproj
    proj_dir = projects_dir / "💻testproj"
    proj_dir.mkdir()
    proyecto_path = proj_dir / "💻testproj.md"
    proyecto_path.write_text(_PROYECTO_TEMPLATE.format(name="testproj"))
    (proj_dir / "📓testproj.md").write_text("# Logbook\n")

    # Patch all module-level path constants
    monkeypatch.setattr("core.log.PROJECTS_DIR", projects_dir)

    return {
        "tmp":           tmp_path,
        "projects_dir":  projects_dir,
        "templates_dir": templates_dir,
        "proj_dir":      proj_dir,
        "proyecto_path": proyecto_path,
        "today":         date.today().isoformat(),
    }

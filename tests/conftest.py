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
🟠 Alta

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

_DIARIO_TEMPLATE = """\
# {date}

## 🎯 Proyecto en foco

## ✅ Tareas del día

## 📝 Notas

<!-- orbit:reminders:start -->
<!-- orbit:reminders:end -->
"""


# ── Fixture principal ──────────────────────────────────────────────────────────

@pytest.fixture
def orbit_env(tmp_path, monkeypatch):
    """Set up an isolated Orbit environment with one test project and a daily note."""
    projects_dir = tmp_path / "🚀proyectos"
    mision_dir   = tmp_path / "☀️mision-log"
    diario_dir   = mision_dir / "diario"
    templates_dir = tmp_path / "📐templates"

    projects_dir.mkdir()
    diario_dir.mkdir(parents=True)
    templates_dir.mkdir()

    # Test project: 💻testproj
    proj_dir = projects_dir / "💻testproj"
    proj_dir.mkdir()
    proyecto_path = proj_dir / "💻testproj.md"
    proyecto_path.write_text(_PROYECTO_TEMPLATE.format(name="testproj"))
    (proj_dir / "📓testproj.md").write_text("# Logbook\n")

    # Daily note template
    (templates_dir / "diario.md").write_text(_DIARIO_TEMPLATE.format(date="YYYY-MM-DD"))

    # Today's daily note
    today_str = date.today().isoformat()
    diario_path = diario_dir / f"{today_str}.md"
    diario_path.write_text(_DIARIO_TEMPLATE.format(date=today_str))

    # Patch all module-level path constants
    monkeypatch.setattr("core.log.PROJECTS_DIR",       projects_dir)
    monkeypatch.setattr("core.tasks.PROJECTS_DIR",     projects_dir)
    monkeypatch.setattr("core.task.PROJECTS_DIR",      projects_dir)
    monkeypatch.setattr("core.task.DIARIO_DIR",        diario_dir)
    monkeypatch.setattr("core.task.TEMPLATES_DIR",     templates_dir)

    return {
        "tmp":          tmp_path,
        "projects_dir": projects_dir,
        "diario_dir":   diario_dir,
        "proj_dir":     proj_dir,
        "proyecto_path": proyecto_path,
        "diario_path":  diario_path,
        "today":        today_str,
    }

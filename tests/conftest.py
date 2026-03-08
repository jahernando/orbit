"""conftest.py — shared fixtures for Orbit tests.

Creates an isolated temporary project structure so tests never touch real data.
"""

import pytest
from pathlib import Path
from datetime import date, timedelta

from core.misionlog import _week_key, _week_bounds


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

    # note.md template (used by run_add_note)
    (templates_dir / "note.md").write_text(
        "# TÍTULO\n\n*YYYY-MM-DD — PROYECTO*\n\n---\n\n"
    )

    # Patch all module-level path constants
    monkeypatch.setattr("core.log.PROJECTS_DIR",       projects_dir)
    monkeypatch.setattr("core.tasks.PROJECTS_DIR",     projects_dir)
    monkeypatch.setattr("core.tarea.PROJECTS_DIR",      projects_dir)
    monkeypatch.setattr("core.tarea.DIARIO_DIR",        diario_dir)
    monkeypatch.setattr("core.tarea.TEMPLATES_DIR",     templates_dir)
    monkeypatch.setattr("core.list_cmd.PROJECTS_DIR",  projects_dir)
    monkeypatch.setattr("core.add.TEMPLATES_DIR",      templates_dir)

    return {
        "tmp":           tmp_path,
        "projects_dir":  projects_dir,
        "templates_dir": templates_dir,
        "diario_dir":    diario_dir,
        "proj_dir":      proj_dir,
        "proyecto_path": proyecto_path,
        "diario_path":   diario_path,
        "today":         today_str,
    }


# ── Templates for misionlog tests ─────────────────────────────────────────────

_DIARIO_TPL = """\
# Diario — YYYY-MM-DD

## 📋 Planificación

### 🎯 Proyecto en foco
- [nombre-proyecto](../../🚀proyectos/nombre-proyecto/proyecto.md)

### ✅ Tareas del día

## 📝 Anotaciones

## 📊 Valoración

<!-- orbit:valoracion-stats:start -->
<!-- orbit:valoracion-stats:end -->
"""

_SEMANAL_TPL = """\
# Semana YYYY-Wnn (YYYY-MM-DD — YYYY-MM-DD)

## 📋 Planificación

### 🎯 Proyectos en foco
1. [proyecto-1](../../🚀proyectos/proyecto-1/proyecto.md)
2. [proyecto-2](../../🚀proyectos/proyecto-2/proyecto.md)

## 📝 Notas de la semana

## 📊 Valoración

<!-- orbit:valoracion-stats:start -->
<!-- orbit:valoracion-stats:end -->

<!-- orbit:weekreport:start -->
<!-- orbit:weekreport:end -->
"""

_MENSUAL_TPL = """\
# Mes YYYY-MM

← [Mes anterior](../mensual/YYYY-MM.md)

## 📋 Planificación

### 🎯 Proyectos en foco
1. [proyecto-1](../../🚀proyectos/proyecto-1/proyecto.md)

## 📝 Notas del mes

## 📊 Valoración

<!-- orbit:monthly:start -->
<!-- orbit:monthly:end -->

<!-- orbit:valoracion-stats:start -->
<!-- orbit:valoracion-stats:end -->
"""


# ── mision_env fixture ────────────────────────────────────────────────────────

@pytest.fixture
def mision_env(orbit_env, monkeypatch):
    """Extend orbit_env with semanal/mensual dirs, updated templates, logbook
    entries and all misionlog path patches needed for period-note tests."""
    today_str    = orbit_env["today"]
    today        = date.fromisoformat(today_str)
    templates_dir = orbit_env["templates_dir"]
    proj_dir     = orbit_env["proj_dir"]

    # Directories
    mision_dir  = orbit_env["tmp"] / "☀️mision-log"
    semanal_dir = mision_dir / "semanal"
    mensual_dir = mision_dir / "mensual"
    semanal_dir.mkdir(parents=True, exist_ok=True)
    mensual_dir.mkdir(parents=True, exist_ok=True)

    # Updated templates (3-section structure with current markers)
    (templates_dir / "diario.md").write_text(_DIARIO_TPL)
    (templates_dir / "semanal.md").write_text(_SEMANAL_TPL)
    (templates_dir / "mensual.md").write_text(_MENSUAL_TPL)

    # Logbook entries for testproj (2 entries today)
    logbook = proj_dir / "📓testproj.md"
    logbook.write_text(
        "# Logbook\n"
        f"{today_str} Calibración relativa #apunte\n"
        f"{today_str} σ/E = 2.3% @ 1 MeV #resultado\n"
    )

    # Today's daily note with focus and stats markers
    diario_path = orbit_env["diario_path"]
    diario_path.write_text(
        f"# Diario — {today_str}\n\n"
        "## 📋 Planificación\n\n"
        "### 🎯 Proyecto en foco\n"
        "- [💻testproj](../../🚀proyectos/💻testproj/💻testproj.md)\n\n"
        "## 📝 Anotaciones\n\n"
        "## 📊 Valoración\n\n"
        "<!-- orbit:valoracion-stats:start -->\n"
        "<!-- orbit:valoracion-stats:end -->\n"
    )

    # Current month's mensual note (prevents run_shell_startup from prompting focus)
    month_str    = today.strftime("%Y-%m")
    mensual_path = mensual_dir / f"{month_str}.md"
    mensual_path.write_text(
        f"# Mes {month_str}\n\n"
        "## 📋 Planificación\n\n"
        "### 🎯 Proyectos en foco\n"
        "1. [💻testproj](../../🚀proyectos/💻testproj/💻testproj.md)\n\n"
        "## 📝 Notas del mes\n\n"
        "## 📊 Valoración\n\n"
        "<!-- orbit:valoracion-stats:start -->\n"
        "<!-- orbit:valoracion-stats:end -->\n"
    )

    # Current week's semanal note with testproj as focus
    wkey     = _week_key(today)
    mon, sun = _week_bounds(today)
    semanal_path = semanal_dir / f"{wkey}.md"
    semanal_path.write_text(
        f"# Semana {wkey} ({mon.isoformat()} — {sun.isoformat()})\n\n"
        "## 📋 Planificación\n\n"
        "### 🎯 Proyectos en foco\n"
        "1. [💻testproj](../../🚀proyectos/💻testproj/💻testproj.md)\n\n"
        "## 📝 Notas de la semana\n\n"
        "## 📊 Valoración\n\n"
        "<!-- orbit:valoracion-stats:start -->\n"
        "<!-- orbit:valoracion-stats:end -->\n\n"
        "<!-- orbit:weekreport:start -->\n"
        "<!-- orbit:weekreport:end -->\n"
    )

    # Patch misionlog module paths
    monkeypatch.setattr("core.misionlog.PROJECTS_DIR",  orbit_env["projects_dir"])
    monkeypatch.setattr("core.misionlog.DIARIO_DIR",    orbit_env["diario_dir"])
    monkeypatch.setattr("core.misionlog.SEMANAL_DIR",   semanal_dir)
    monkeypatch.setattr("core.misionlog.MENSUAL_DIR",   mensual_dir)
    monkeypatch.setattr("core.misionlog.TEMPLATES_DIR", templates_dir)

    # Patch reports module paths (run_dayreport / run_weekreport moved here)
    monkeypatch.setattr("core.reports.PROJECTS_DIR",    orbit_env["projects_dir"])
    monkeypatch.setattr("core.reports.DIARIO_DIR",      orbit_env["diario_dir"])
    monkeypatch.setattr("core.reports.SEMANAL_DIR",     semanal_dir)

    # Silence external side-effects
    monkeypatch.setattr("core.misionlog.log_to_mission", lambda *a, **k: None)
    monkeypatch.setattr("core.misionlog.open_file",      lambda p, e: 0)
    monkeypatch.setattr("core.reports.log_to_mission",   lambda *a, **k: None)
    monkeypatch.setattr("core.reports.open_file",        lambda p, e: 0)

    return {
        **orbit_env,
        "semanal_dir":  semanal_dir,
        "mensual_dir":  mensual_dir,
        "mensual_path": mensual_path,
        "semanal_path": semanal_path,
        "logbook":      logbook,
        "wkey":         wkey,
        "mon":          mon,
        "sun":          sun,
    }

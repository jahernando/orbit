"""test_doctor.py — unit tests for orbit doctor (syntax validation).

Covers:
  - _check_logbook:    dates, types, emoji mismatch
  - _check_agenda:     task markers, dates, recurrence, events format
  - _check_highlights: section headings, item format, link brackets
  - check_project:     orchestrator
  - _apply_fix:        line replacement
"""

import pytest
from datetime import date
from pathlib import Path

from core.doctor import (
    _check_logbook, _check_agenda, _check_highlights,
    check_project, _apply_fix, Issue,
)


# ── Fixture ──────────────────────────────────────────────────────────────────

@pytest.fixture
def doctor_env(tmp_path, monkeypatch):
    """Isolated project env for doctor tests."""
    projects_dir = tmp_path / "🚀proyectos"
    projects_dir.mkdir()
    proj = projects_dir / "💻testproj"
    proj.mkdir()

    # Minimal project.md so _is_new_project returns True
    (proj / "testproj-project.md").write_text(
        "# 💻testproj\n\n- Tipo: 💻 Software\n- Estado: [auto]\n- Prioridad: media\n"
    )
    (proj / "testproj-logbook.md").write_text("# Logbook\n\n")
    (proj / "testproj-agenda.md").write_text("# Agenda\n\n")
    (proj / "testproj-highlights.md").write_text("# Highlights\n\n")
    (proj / "notes").mkdir()

    monkeypatch.setattr("core.log.PROJECTS_DIR", projects_dir)
    monkeypatch.setattr("core.doctor.PROJECTS_DIR", projects_dir)

    return {"projects_dir": projects_dir, "proj": proj}


# ═══════════════════════════════════════════════════════════════════════════════
# _check_logbook
# ═══════════════════════════════════════════════════════════════════════════════

class TestCheckLogbook:

    def test_valid_entries_no_issues(self, doctor_env):
        path = doctor_env["proj"] / "testproj-logbook.md"
        today = date.today().isoformat()
        path.write_text(
            f"# Logbook\n\n{today} Primera entrada #apunte\n"
            f"{today} 💡 Una idea #idea\n"
        )
        issues = _check_logbook("💻testproj", path)
        assert issues == []

    def test_missing_type_tag(self, doctor_env):
        path = doctor_env["proj"] / "testproj-logbook.md"
        today = date.today().isoformat()
        path.write_text(f"# Logbook\n\n{today} Entrada sin tipo\n")
        issues = _check_logbook("💻testproj", path)
        assert len(issues) == 1
        assert "Falta #tipo" in issues[0].msg

    def test_wrong_emoji_flagged(self, doctor_env):
        path = doctor_env["proj"] / "testproj-logbook.md"
        today = date.today().isoformat()
        # 💡 is for #idea, but we tag as #apunte (which uses 📝)
        path.write_text(f"# Logbook\n\n{today} 💡 Nota errónea #apunte\n")
        issues = _check_logbook("💻testproj", path)
        assert len(issues) == 1
        assert "no coincide" in issues[0].msg
        assert issues[0].fix is not None

    def test_no_emoji_not_flagged(self, doctor_env):
        """Entries without emoji should NOT be flagged (old format)."""
        path = doctor_env["proj"] / "testproj-logbook.md"
        today = date.today().isoformat()
        path.write_text(f"# Logbook\n\n{today} Nota sin emoji #apunte\n")
        issues = _check_logbook("💻testproj", path)
        assert issues == []

    def test_invalid_date(self, doctor_env):
        path = doctor_env["proj"] / "testproj-logbook.md"
        path.write_text("# Logbook\n\n2026-02-30 Fecha imposible #apunte\n")
        issues = _check_logbook("💻testproj", path)
        assert len(issues) == 1
        assert "Fecha inválida" in issues[0].msg

    def test_malformed_date_line(self, doctor_env):
        path = doctor_env["proj"] / "testproj-logbook.md"
        path.write_text("# Logbook\n\n2026-0310 Sin guión #apunte\n")
        issues = _check_logbook("💻testproj", path)
        assert len(issues) == 1
        assert "Fecha mal formada" in issues[0].msg

    def test_blank_and_header_lines_skipped(self, doctor_env):
        path = doctor_env["proj"] / "testproj-logbook.md"
        today = date.today().isoformat()
        path.write_text(f"# Logbook\n\n<!-- comment -->\n\n{today} Ok #apunte\n")
        issues = _check_logbook("💻testproj", path)
        assert issues == []

    def test_empty_logbook_no_issues(self, doctor_env):
        path = doctor_env["proj"] / "testproj-logbook.md"
        path.write_text("# Logbook\n\n")
        issues = _check_logbook("💻testproj", path)
        assert issues == []

    def test_nonexistent_file_no_issues(self, doctor_env):
        path = doctor_env["proj"] / "nonexistent.md"
        issues = _check_logbook("💻testproj", path)
        assert issues == []


# ═══════════════════════════════════════════════════════════════════════════════
# _check_agenda
# ═══════════════════════════════════════════════════════════════════════════════

class TestCheckAgenda:

    def test_valid_agenda_no_issues(self, doctor_env):
        path = doctor_env["proj"] / "testproj-agenda.md"
        path.write_text(
            "# Agenda\n\n"
            "## ✅ Tareas\n"
            "- [ ] Tarea pendiente\n"
            "- [x] Tarea hecha\n\n"
            "## 🏁 Hitos\n"
            "- [ ] Hito 1 (2026-06-01)\n\n"
            "## 📅 Eventos\n"
            "2026-04-01 — Reunión de equipo\n"
        )
        issues = _check_agenda("💻testproj", path)
        assert issues == []

    def test_invalid_task_marker(self, doctor_env):
        path = doctor_env["proj"] / "testproj-agenda.md"
        path.write_text(
            "# Agenda\n\n"
            "## ✅ Tareas\n"
            "- [?] Tarea rara\n"
        )
        issues = _check_agenda("💻testproj", path)
        assert len(issues) == 1
        assert "Marcador inválido" in issues[0].msg

    def test_event_wrong_dash(self, doctor_env):
        path = doctor_env["proj"] / "testproj-agenda.md"
        path.write_text(
            "# Agenda\n\n"
            "## 📅 Eventos\n"
            "2026-04-01 - Reunión con guión corto\n"
        )
        issues = _check_agenda("💻testproj", path)
        assert len(issues) == 1
        assert "em-dash" in issues[0].msg
        assert issues[0].fix is not None
        assert "—" in issues[0].fix

    def test_event_invalid_date(self, doctor_env):
        path = doctor_env["proj"] / "testproj-agenda.md"
        path.write_text(
            "# Agenda\n\n"
            "## 📅 Eventos\n"
            "2026-02-30 — Evento imposible\n"
        )
        issues = _check_agenda("💻testproj", path)
        assert len(issues) == 1
        assert "Fecha" in issues[0].msg

    def test_task_invalid_date(self, doctor_env):
        path = doctor_env["proj"] / "testproj-agenda.md"
        path.write_text(
            "# Agenda\n\n"
            "## ✅ Tareas\n"
            "- [ ] Tarea (2026-13-01)\n"
        )
        issues = _check_agenda("💻testproj", path)
        assert len(issues) == 1
        assert "Fecha inválida" in issues[0].msg

    def test_task_in_events_section(self, doctor_env):
        path = doctor_env["proj"] / "testproj-agenda.md"
        path.write_text(
            "# Agenda\n\n"
            "## 📅 Eventos\n"
            "- [ ] Esto no es un evento\n"
        )
        issues = _check_agenda("💻testproj", path)
        assert len(issues) == 1
        assert "formato de tarea" in issues[0].msg

    def test_event_without_description(self, doctor_env):
        path = doctor_env["proj"] / "testproj-agenda.md"
        path.write_text(
            "# Agenda\n\n"
            "## 📅 Eventos\n"
            "2026-04-01 — \n"
        )
        issues = _check_agenda("💻testproj", path)
        assert len(issues) == 1
        # Parser may reject as malformed or flag empty desc
        assert "Evento" in issues[0].msg

    def test_empty_agenda_no_issues(self, doctor_env):
        path = doctor_env["proj"] / "testproj-agenda.md"
        path.write_text("# Agenda\n\n")
        issues = _check_agenda("💻testproj", path)
        assert issues == []

    def test_nonexistent_file_no_issues(self, doctor_env):
        path = doctor_env["proj"] / "nonexistent.md"
        issues = _check_agenda("💻testproj", path)
        assert issues == []


# ═══════════════════════════════════════════════════════════════════════════════
# _check_highlights
# ═══════════════════════════════════════════════════════════════════════════════

class TestCheckHighlights:

    def test_valid_highlights_no_issues(self, doctor_env):
        path = doctor_env["proj"] / "testproj-highlights.md"
        path.write_text(
            "# Highlights\n\n"
            "## 📚 Referencias\n"
            "- [Artículo](https://example.com) — Muy bueno\n"
            "- Texto simple\n\n"
            "## 💡 Ideas\n"
            "- Idea interesante\n"
        )
        issues = _check_highlights("💻testproj", path)
        assert issues == []

    def test_unknown_section(self, doctor_env):
        path = doctor_env["proj"] / "testproj-highlights.md"
        path.write_text(
            "# Highlights\n\n"
            "## 🎯 Sección Inventada\n"
            "- Item\n"
        )
        issues = _check_highlights("💻testproj", path)
        assert len(issues) == 1
        assert "no reconocida" in issues[0].msg

    def test_item_without_dash(self, doctor_env):
        path = doctor_env["proj"] / "testproj-highlights.md"
        path.write_text(
            "# Highlights\n\n"
            "## 📚 Referencias\n"
            "Texto sin guión\n"
        )
        issues = _check_highlights("💻testproj", path)
        assert len(issues) == 1
        assert "empezar con '- '" in issues[0].msg

    def test_unbalanced_brackets(self, doctor_env):
        path = doctor_env["proj"] / "testproj-highlights.md"
        path.write_text(
            "# Highlights\n\n"
            "## 📚 Referencias\n"
            "- [Link roto](https://example.com\n"
        )
        issues = _check_highlights("💻testproj", path)
        assert len(issues) == 1
        assert "desbalanceados" in issues[0].msg

    def test_empty_highlights_no_issues(self, doctor_env):
        path = doctor_env["proj"] / "testproj-highlights.md"
        path.write_text("# Highlights\n\n")
        issues = _check_highlights("💻testproj", path)
        assert issues == []

    def test_nonexistent_file_no_issues(self, doctor_env):
        path = doctor_env["proj"] / "nonexistent.md"
        issues = _check_highlights("💻testproj", path)
        assert issues == []


# ═══════════════════════════════════════════════════════════════════════════════
# check_project (orchestrator)
# ═══════════════════════════════════════════════════════════════════════════════

class TestCheckProject:

    def test_clean_project_no_issues(self, doctor_env):
        today = date.today().isoformat()
        proj = doctor_env["proj"]
        (proj / "testproj-logbook.md").write_text(
            f"# Logbook\n\n{today} Nota #apunte\n"
        )
        (proj / "testproj-agenda.md").write_text(
            "# Agenda\n\n## ✅ Tareas\n- [ ] Tarea\n"
        )
        (proj / "testproj-highlights.md").write_text(
            "# Highlights\n\n## 📚 Referencias\n- Ref\n"
        )
        issues = check_project(proj)
        assert issues == []

    def test_collects_issues_from_all_files(self, doctor_env):
        proj = doctor_env["proj"]
        (proj / "testproj-logbook.md").write_text(
            "# Logbook\n\n2026-01-01 Sin tipo\n"
        )
        (proj / "testproj-agenda.md").write_text(
            "# Agenda\n\n## 📅 Eventos\n2026-04-01 - Guión malo\n"
        )
        (proj / "testproj-highlights.md").write_text(
            "# Highlights\n\n## 📚 Referencias\nSin guión\n"
        )
        issues = check_project(proj)
        assert len(issues) == 3


# ═══════════════════════════════════════════════════════════════════════════════
# _apply_fix
# ═══════════════════════════════════════════════════════════════════════════════

class TestApplyFix:

    def test_applies_fix_to_correct_line(self, doctor_env):
        proj = doctor_env["proj"]
        path = proj / "testproj-logbook.md"
        path.write_text("# Logbook\n\nline1\nline2\nline3\n")

        issue = Issue(
            project="💻testproj",
            file="testproj-logbook.md",
            line_num=4,
            line="line2",
            msg="test",
            fix="FIXED",
        )
        result = _apply_fix(issue)
        assert result is True
        lines = path.read_text().splitlines()
        assert lines[3] == "FIXED"

    def test_no_fix_returns_false(self, doctor_env):
        issue = Issue("💻testproj", "testproj-logbook.md", 1, "x", "test", fix=None)
        assert _apply_fix(issue) is False

    def test_wrong_project_returns_false(self, doctor_env):
        issue = Issue("💻nonexistent", "logbook.md", 1, "x", "test", fix="y")
        assert _apply_fix(issue) is False

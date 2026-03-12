"""Tests for #plan tag, agenda --order date, and doctor zero-padding check.

Covers:
  - #plan type in TAG_EMOJI and VALID_TYPES
  - plans section in highlights SECTION_MAP
  - format_entry with #plan
  - agenda _format_by_date grouping by day/hour
  - doctor detection of non-zero-padded dates with auto-fix
"""

import re
from datetime import date
from pathlib import Path
from io import StringIO

import pytest


# ── Helpers ───────────────────────────────────────────────────────────────────

def _base_name(dirname: str) -> str:
    return re.sub(r'^[\U00010000-\U0010ffff\u2600-\u27bf\ufe0f]+', '', dirname).lstrip()


def _make_project(pdir: Path, name: str = "💻testproj") -> Path:
    project_dir = pdir / name
    project_dir.mkdir()
    base = _base_name(name)
    (project_dir / f"{base}-project.md").write_text(
        f"# {name}\n- Tipo: 💻 Software\n- Estado: [auto]\n- Prioridad: media\n"
    )
    (project_dir / f"{base}-logbook.md").write_text(f"# Logbook — {name}\n\n")
    (project_dir / f"{base}-highlights.md").write_text(f"# Highlights — {name}\n\n")
    (project_dir / f"{base}-agenda.md").write_text(f"# Agenda — {name}\n\n")
    (project_dir / "notes").mkdir()
    return project_dir


# ═════════════════════════════════════════════════════════════════════════════
# #plan tag
# ═════════════════════════════════════════════════════════════════════════════

class TestPlanTag:

    def test_plan_in_valid_types(self):
        from core.log import VALID_TYPES
        assert "plan" in VALID_TYPES

    def test_plan_emoji_in_tag_emoji(self):
        from core.log import TAG_EMOJI
        assert "plan" in TAG_EMOJI
        assert TAG_EMOJI["plan"] == "🗓️"

    def test_format_entry_plan(self):
        from core.log import format_entry
        entry = format_entry("planificación semanal", "plan", None, "2026-03-11")
        assert "🗓️" in entry
        assert "#plan" in entry
        assert "2026-03-11" in entry

    def test_plans_section_in_highlights(self):
        from core.highlights import SECTION_MAP, VALID_TYPES
        assert "plans" in SECTION_MAP
        assert "🗓️" in SECTION_MAP["plans"]
        assert "plans" in VALID_TYPES


# ═════════════════════════════════════════════════════════════════════════════
# agenda --order date
# ═════════════════════════════════════════════════════════════════════════════

@pytest.fixture()
def agenda_env(tmp_path, monkeypatch):
    pdir = tmp_path / "proyectos"
    pdir.mkdir()
    import core.log as cl
    import core.project as cp
    import core.agenda_view as av
    monkeypatch.setattr(cl, "PROJECTS_DIR", pdir)
    monkeypatch.setattr(cp, "PROJECTS_DIR", pdir)
    monkeypatch.setattr(av, "PROJECTS_DIR", pdir)
    return pdir


class TestAgendaOrderDate:

    def test_format_by_date_groups_by_day(self, agenda_env):
        from core.agenda_view import _format_by_date

        proj_a = _make_project(agenda_env, "💻alpha")
        proj_b = _make_project(agenda_env, "🔬beta")

        collected = [
            (proj_a,
             [{"status": "pending", "desc": "Task A1", "date": "2026-03-11"}],
             [{"date": "2026-03-12", "desc": "Event A1", "time": "10:00"}],
             []),
            (proj_b,
             [{"status": "pending", "desc": "Task B1", "date": "2026-03-11"}],
             [],
             [{"status": "pending", "desc": "Milestone B1", "date": "2026-03-12"}]),
        ]

        lines = _format_by_date(collected)
        text = "\n".join(lines)

        # Both dates should appear as headers
        assert "2026-03-11" in text
        assert "2026-03-12" in text

        # Project tags should appear
        assert "[💻alpha]" in text
        assert "[🔬beta]" in text

        # Day 11 should come before day 12
        idx_11 = text.index("2026-03-11")
        idx_12 = text.index("2026-03-12")
        assert idx_11 < idx_12

    def test_format_by_date_time_ordering(self, agenda_env):
        from core.agenda_view import _format_by_date

        proj = _make_project(agenda_env, "💻proj")

        collected = [
            (proj,
             [{"status": "pending", "desc": "No-time task", "date": "2026-03-11"}],
             [{"date": "2026-03-11", "desc": "Morning event", "time": "09:00"},
              {"date": "2026-03-11", "desc": "Afternoon event", "time": "14:00"}],
             []),
        ]

        lines = _format_by_date(collected)
        text = "\n".join(lines)

        # Events with time should appear before tasks without time
        idx_morning = text.index("Morning event")
        idx_afternoon = text.index("Afternoon event")
        idx_notask = text.index("No-time task")
        assert idx_morning < idx_afternoon < idx_notask

    def test_format_by_date_undated_block(self, agenda_env):
        from core.agenda_view import _format_by_date

        proj = _make_project(agenda_env, "💻proj")

        collected = [
            (proj,
             [{"status": "pending", "desc": "Dated task", "date": "2026-03-11"},
              {"status": "pending", "desc": "Undated task", "date": None}],
             [],
             []),
        ]

        lines = _format_by_date(collected)
        text = "\n".join(lines)

        assert "Sin fecha" in text
        assert "Undated task" in text

    def test_format_by_date_dated_only_hides_undated(self, agenda_env):
        from core.agenda_view import _format_by_date

        proj = _make_project(agenda_env, "💻proj")

        collected = [
            (proj,
             [{"status": "pending", "desc": "Dated task", "date": "2026-03-11"},
              {"status": "pending", "desc": "Undated task", "date": None}],
             [],
             []),
        ]

        lines = _format_by_date(collected, dated_only=True)
        text = "\n".join(lines)

        assert "Sin fecha" not in text
        assert "Undated task" not in text
        assert "Dated task" in text

    def test_format_by_date_kind_order(self, agenda_env):
        """Within same time slot: milestones before events before tasks."""
        from core.agenda_view import _format_by_date

        proj = _make_project(agenda_env, "💻proj")

        collected = [
            (proj,
             [{"status": "pending", "desc": "A task", "date": "2026-03-11"}],
             [{"date": "2026-03-11", "desc": "An event"}],
             [{"status": "pending", "desc": "A milestone", "date": "2026-03-11"}]),
        ]

        lines = _format_by_date(collected)
        text = "\n".join(lines)

        idx_ms = text.index("A milestone")
        idx_ev = text.index("An event")
        idx_task = text.index("A task")
        assert idx_ms < idx_ev < idx_task

    def test_format_by_date_markdown_mode(self, agenda_env):
        from core.agenda_view import _format_by_date

        proj = _make_project(agenda_env, "💻proj")

        collected = [
            (proj,
             [{"status": "pending", "desc": "Task md", "date": "2026-03-11"}],
             [],
             []),
        ]

        lines = _format_by_date(collected, markdown=True)
        text = "\n".join(lines)

        assert "**2026-03-11" in text
        assert "☐" in text  # markdown checkbox


# ═════════════════════════════════════════════════════════════════════════════
# doctor: zero-padding check
# ═════════════════════════════════════════════════════════════════════════════

class TestDoctorZeroPadding:

    @pytest.fixture()
    def doctor_env(self, tmp_path, monkeypatch):
        projects_dir = tmp_path / "🚀proyectos"
        projects_dir.mkdir()
        proj = projects_dir / "💻testproj"
        proj.mkdir()
        (proj / "testproj-project.md").write_text(
            "# 💻testproj\n- Tipo: 💻 Software\n- Estado: [auto]\n- Prioridad: media\n"
        )
        monkeypatch.setattr("core.log.PROJECTS_DIR", projects_dir)
        monkeypatch.setattr("core.doctor.PROJECTS_DIR", projects_dir)
        return {"proj": proj}

    def test_detects_non_padded_month(self, doctor_env):
        from core.doctor import _check_agenda
        path = doctor_env["proj"] / "testproj-agenda.md"
        path.write_text(
            "# Agenda\n\n"
            "## 🏁 Hitos\n"
            "- [ ] Milestone (2026-3-28)\n"
        )
        issues = _check_agenda("💻testproj", path)
        assert any("zero-padding" in i.msg for i in issues)

    def test_detects_non_padded_day(self, doctor_env):
        from core.doctor import _check_agenda
        path = doctor_env["proj"] / "testproj-agenda.md"
        path.write_text(
            "# Agenda\n\n"
            "## ✅ Tareas\n"
            "- [ ] Task (2026-03-1)\n"
        )
        issues = _check_agenda("💻testproj", path)
        assert any("zero-padding" in i.msg for i in issues)

    def test_fix_pads_correctly(self, doctor_env):
        from core.doctor import _check_agenda
        path = doctor_env["proj"] / "testproj-agenda.md"
        path.write_text(
            "# Agenda\n\n"
            "## 🏁 Hitos\n"
            "- [ ] Milestone (2026-3-5)\n"
        )
        issues = _check_agenda("💻testproj", path)
        padding_issues = [i for i in issues if "zero-padding" in i.msg]
        assert len(padding_issues) == 1
        assert "(2026-03-05)" in padding_issues[0].fix

    def test_correctly_padded_date_no_issue(self, doctor_env):
        from core.doctor import _check_agenda
        path = doctor_env["proj"] / "testproj-agenda.md"
        path.write_text(
            "# Agenda\n\n"
            "## 🏁 Hitos\n"
            "- [ ] Milestone (2026-03-28)\n"
        )
        issues = _check_agenda("💻testproj", path)
        padding_issues = [i for i in issues if "zero-padding" in i.msg]
        assert padding_issues == []

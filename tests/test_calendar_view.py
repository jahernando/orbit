"""test_calendar_view.py — tests for the calendar week/month/year views."""

from datetime import date
from pathlib import Path

import pytest

from core.calendar_view import (
    _parse_week_ref, _parse_month_ref, _parse_year_ref,
    _collect_tasks, _fmt_task,
    run_calendar_week, run_calendar_month, run_calendar_year,
)


# ═══════════════════════════════════════════════════════════════════════════════
# Date parsers — pure functions
# ═══════════════════════════════════════════════════════════════════════════════

class TestParseWeekRef:

    def test_none_returns_today(self):
        d = _parse_week_ref(None)
        assert d == date.today()

    def test_bare_number_returns_monday_of_that_week(self):
        d = _parse_week_ref("10")
        assert d.weekday() == 0  # Monday
        assert d.isocalendar()[1] == 10

    def test_yyyy_wnn_format(self):
        d = _parse_week_ref("2026-W10")
        assert d.year == 2026
        assert d.isocalendar()[1] == 10
        assert d.weekday() == 0

    def test_iso_date_returns_that_date(self):
        d = _parse_week_ref("2026-03-09")
        assert d == date(2026, 3, 9)

    def test_invalid_returns_today(self):
        d = _parse_week_ref("not-a-date")
        assert d == date.today()


class TestParseMonthRef:

    def test_none_returns_current_month(self):
        y, m = _parse_month_ref(None)
        today = date.today()
        assert y == today.year and m == today.month

    def test_spanish_month_name(self):
        y, m = _parse_month_ref("marzo")
        assert m == 3

    def test_english_month_name(self):
        y, m = _parse_month_ref("march")
        assert m == 3

    def test_bare_number(self):
        y, m = _parse_month_ref("3")
        assert m == 3

    def test_yyyy_mm_format(self):
        y, m = _parse_month_ref("2026-03")
        assert y == 2026 and m == 3

    def test_iso_date_extracts_month(self):
        y, m = _parse_month_ref("2026-03-15")
        assert y == 2026 and m == 3

    def test_invalid_returns_current_month(self):
        y, m = _parse_month_ref("invalid")
        today = date.today()
        assert y == today.year and m == today.month


class TestParseYearRef:

    def test_none_returns_current_year(self):
        assert _parse_year_ref(None) == date.today().year

    def test_four_digit_year(self):
        assert _parse_year_ref("2026") == 2026

    def test_iso_date_extracts_year(self):
        assert _parse_year_ref("2026-03-15") == 2026

    def test_invalid_returns_current_year(self):
        assert _parse_year_ref("notayear") == date.today().year


# ═══════════════════════════════════════════════════════════════════════════════
# Task collection and formatting
# ═══════════════════════════════════════════════════════════════════════════════

def _make_project(projects_dir: Path, name: str, task_due: str = None) -> Path:
    proj = projects_dir / name
    proj.mkdir()
    task_line = f"- [ ] Tarea de prueba ({task_due})\n" if task_due else ""
    (proj / f"{name}.md").write_text(
        f"# {name}\n\n"
        "**Tipo:** Investigación\n"
        "**Estado:** En marcha\n"
        "**Prioridad:** media\n\n"
        f"## ✅ Tareas\n{task_line}\n"
    )
    return proj


class TestCollectTasks:

    def test_collects_task_in_range(self, tmp_path, monkeypatch):
        projects_dir = tmp_path / "🚀proyectos"
        projects_dir.mkdir()
        _make_project(projects_dir, "💻testproj", "2026-03-15")
        monkeypatch.setattr("core.calendar_view.PROJECTS_DIR", projects_dir)
        monkeypatch.setattr("core.log.PROJECTS_DIR",           projects_dir)

        tasks = _collect_tasks(date(2026, 3, 1), date(2026, 3, 31))
        assert date(2026, 3, 15) in tasks
        assert len(tasks[date(2026, 3, 15)]) == 1

    def test_excludes_task_outside_range(self, tmp_path, monkeypatch):
        projects_dir = tmp_path / "🚀proyectos"
        projects_dir.mkdir()
        _make_project(projects_dir, "💻testproj", "2026-04-01")
        monkeypatch.setattr("core.calendar_view.PROJECTS_DIR", projects_dir)
        monkeypatch.setattr("core.log.PROJECTS_DIR",           projects_dir)

        tasks = _collect_tasks(date(2026, 3, 1), date(2026, 3, 31))
        assert tasks == {}

    def test_no_projects_dir_returns_empty(self, tmp_path, monkeypatch):
        missing = tmp_path / "nonexistent"
        monkeypatch.setattr("core.calendar_view.PROJECTS_DIR", missing)
        assert _collect_tasks(date(2026, 3, 1), date(2026, 3, 31)) == {}

    def test_excludes_done_tasks(self, tmp_path, monkeypatch):
        projects_dir = tmp_path / "🚀proyectos"
        projects_dir.mkdir()
        proj = projects_dir / "💻testproj"
        proj.mkdir()
        (proj / "💻testproj.md").write_text(
            "# testproj\n\n**Tipo:** Investigación\n**Estado:** En marcha\n**Prioridad:** media\n\n"
            "## ✅ Tareas\n"
            "- [x] Tarea completada (2026-03-15)\n"
        )
        monkeypatch.setattr("core.calendar_view.PROJECTS_DIR", projects_dir)
        monkeypatch.setattr("core.log.PROJECTS_DIR",           projects_dir)

        tasks = _collect_tasks(date(2026, 3, 1), date(2026, 3, 31))
        assert tasks == {}


class TestFmtTask:

    def test_includes_description(self):
        t = {"desc": "Hacer algo importante", "project": "💻testproj",
             "path": Path("/fake/path.md")}
        line = _fmt_task(t)
        assert "Hacer algo importante" in line

    def test_includes_project_link(self):
        t = {"desc": "Tarea", "project": "💻testproj",
             "path": Path("/fake/path.md")}
        line = _fmt_task(t)
        assert "💻testproj" in line
        assert "file://" in line

    def test_checkbox_marker(self):
        t = {"desc": "Tarea", "project": "💻testproj",
             "path": Path("/fake/path.md")}
        line = _fmt_task(t)
        assert line.startswith("- ✅")


# ═══════════════════════════════════════════════════════════════════════════════
# run_calendar_* — output and file writing
# ═══════════════════════════════════════════════════════════════════════════════

class TestRunCalendarWeek:

    def test_creates_output_file(self, tmp_path, monkeypatch):
        projects_dir = tmp_path / "🚀proyectos"
        projects_dir.mkdir()
        out_file = tmp_path / "calendar-week.md"
        monkeypatch.setattr("core.calendar_view.PROJECTS_DIR",    projects_dir)
        monkeypatch.setattr("core.log.PROJECTS_DIR",              projects_dir)
        monkeypatch.setattr("core.calendar_view.MISION_LOG_DIR",  tmp_path)
        monkeypatch.setattr("core.calendar_view.open_file",       lambda p, e: 0)

        rc = run_calendar_week("2026-W10", open_after=False, editor="typora")
        assert rc == 0
        assert (tmp_path / "calendar-week.md").exists()

    def test_output_contains_week_header(self, tmp_path, monkeypatch):
        projects_dir = tmp_path / "🚀proyectos"
        projects_dir.mkdir()
        monkeypatch.setattr("core.calendar_view.PROJECTS_DIR",   projects_dir)
        monkeypatch.setattr("core.log.PROJECTS_DIR",             projects_dir)
        monkeypatch.setattr("core.calendar_view.MISION_LOG_DIR", tmp_path)
        monkeypatch.setattr("core.calendar_view.open_file",      lambda p, e: 0)

        run_calendar_week("2026-W10", open_after=False, editor="typora")
        text = (tmp_path / "calendar-week.md").read_text()
        assert "2026-W10" in text

    def test_output_contains_all_7_days(self, tmp_path, monkeypatch):
        projects_dir = tmp_path / "🚀proyectos"
        projects_dir.mkdir()
        monkeypatch.setattr("core.calendar_view.PROJECTS_DIR",   projects_dir)
        monkeypatch.setattr("core.log.PROJECTS_DIR",             projects_dir)
        monkeypatch.setattr("core.calendar_view.MISION_LOG_DIR", tmp_path)
        monkeypatch.setattr("core.calendar_view.open_file",      lambda p, e: 0)

        run_calendar_week("2026-W10", open_after=False, editor="typora")
        text = (tmp_path / "calendar-week.md").read_text()
        from core.calendar_view import DIAS_ES
        for day in DIAS_ES:
            assert day in text

    def test_task_appears_in_output(self, tmp_path, monkeypatch):
        projects_dir = tmp_path / "🚀proyectos"
        projects_dir.mkdir()
        _make_project(projects_dir, "💻testproj", "2026-03-02")  # Monday of W10
        monkeypatch.setattr("core.calendar_view.PROJECTS_DIR",   projects_dir)
        monkeypatch.setattr("core.log.PROJECTS_DIR",             projects_dir)
        monkeypatch.setattr("core.calendar_view.MISION_LOG_DIR", tmp_path)
        monkeypatch.setattr("core.calendar_view.open_file",      lambda p, e: 0)

        run_calendar_week("2026-W10", open_after=False, editor="typora")
        text = (tmp_path / "calendar-week.md").read_text()
        assert "Tarea de prueba" in text


class TestRunCalendarMonth:

    def test_creates_output_file(self, tmp_path, monkeypatch):
        projects_dir = tmp_path / "🚀proyectos"
        projects_dir.mkdir()
        monkeypatch.setattr("core.calendar_view.PROJECTS_DIR",   projects_dir)
        monkeypatch.setattr("core.log.PROJECTS_DIR",             projects_dir)
        monkeypatch.setattr("core.calendar_view.MISION_LOG_DIR", tmp_path)
        monkeypatch.setattr("core.calendar_view.open_file",      lambda p, e: 0)

        rc = run_calendar_month("2026-03", open_after=False, editor="typora")
        assert rc == 0
        assert (tmp_path / "calendar-month.md").exists()

    def test_output_contains_month_header(self, tmp_path, monkeypatch):
        projects_dir = tmp_path / "🚀proyectos"
        projects_dir.mkdir()
        monkeypatch.setattr("core.calendar_view.PROJECTS_DIR",   projects_dir)
        monkeypatch.setattr("core.log.PROJECTS_DIR",             projects_dir)
        monkeypatch.setattr("core.calendar_view.MISION_LOG_DIR", tmp_path)
        monkeypatch.setattr("core.calendar_view.open_file",      lambda p, e: 0)

        run_calendar_month("2026-03", open_after=False, editor="typora")
        text = (tmp_path / "calendar-month.md").read_text()
        assert "Marzo" in text

    def test_task_day_highlighted(self, tmp_path, monkeypatch):
        projects_dir = tmp_path / "🚀proyectos"
        projects_dir.mkdir()
        _make_project(projects_dir, "💻testproj", "2026-03-15")
        monkeypatch.setattr("core.calendar_view.PROJECTS_DIR",   projects_dir)
        monkeypatch.setattr("core.log.PROJECTS_DIR",             projects_dir)
        monkeypatch.setattr("core.calendar_view.MISION_LOG_DIR", tmp_path)
        monkeypatch.setattr("core.calendar_view.open_file",      lambda p, e: 0)

        run_calendar_month("2026-03", open_after=False, editor="typora")
        text = (tmp_path / "calendar-month.md").read_text()
        # Day 15 should be highlighted with red span
        assert "color:red" in text
        assert "15" in text

    def test_no_tasks_shows_empty_message(self, tmp_path, monkeypatch):
        projects_dir = tmp_path / "🚀proyectos"
        projects_dir.mkdir()
        monkeypatch.setattr("core.calendar_view.PROJECTS_DIR",   projects_dir)
        monkeypatch.setattr("core.log.PROJECTS_DIR",             projects_dir)
        monkeypatch.setattr("core.calendar_view.MISION_LOG_DIR", tmp_path)
        monkeypatch.setattr("core.calendar_view.open_file",      lambda p, e: 0)

        run_calendar_month("2026-03", open_after=False, editor="typora")
        text = (tmp_path / "calendar-month.md").read_text()
        assert "Sin tareas" in text


class TestRunCalendarYear:

    def test_creates_output_file(self, tmp_path, monkeypatch):
        projects_dir = tmp_path / "🚀proyectos"
        projects_dir.mkdir()
        monkeypatch.setattr("core.calendar_view.PROJECTS_DIR",   projects_dir)
        monkeypatch.setattr("core.log.PROJECTS_DIR",             projects_dir)
        monkeypatch.setattr("core.calendar_view.MISION_LOG_DIR", tmp_path)
        monkeypatch.setattr("core.calendar_view.open_file",      lambda p, e: 0)

        rc = run_calendar_year("2026", open_after=False, editor="typora")
        assert rc == 0
        assert (tmp_path / "calendar-year.md").exists()

    def test_output_contains_all_months(self, tmp_path, monkeypatch):
        projects_dir = tmp_path / "🚀proyectos"
        projects_dir.mkdir()
        monkeypatch.setattr("core.calendar_view.PROJECTS_DIR",   projects_dir)
        monkeypatch.setattr("core.log.PROJECTS_DIR",             projects_dir)
        monkeypatch.setattr("core.calendar_view.MISION_LOG_DIR", tmp_path)
        monkeypatch.setattr("core.calendar_view.open_file",      lambda p, e: 0)

        run_calendar_year("2026", open_after=False, editor="typora")
        text = (tmp_path / "calendar-year.md").read_text()
        from core.calendar_view import MESES_ES
        for mes in MESES_ES[1:]:
            assert mes in text

    def test_task_appears_in_year_view(self, tmp_path, monkeypatch):
        projects_dir = tmp_path / "🚀proyectos"
        projects_dir.mkdir()
        _make_project(projects_dir, "💻testproj", "2026-06-15")
        monkeypatch.setattr("core.calendar_view.PROJECTS_DIR",   projects_dir)
        monkeypatch.setattr("core.log.PROJECTS_DIR",             projects_dir)
        monkeypatch.setattr("core.calendar_view.MISION_LOG_DIR", tmp_path)
        monkeypatch.setattr("core.calendar_view.open_file",      lambda p, e: 0)

        run_calendar_year("2026", open_after=False, editor="typora")
        text = (tmp_path / "calendar-year.md").read_text()
        assert "Tarea de prueba" in text
        assert "Junio" in text

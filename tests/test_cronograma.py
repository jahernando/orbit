"""Tests for cronograma feature:
1. Parsing (task lines, file, tree)
2. Date computation (absolute, after, parent, DAG-only)
3. Topological sort
4. Doctor validation (8 rules)
5. Commands (add, show, list, done, check)
6. Fase 1b metadata (initial-time, exclude)
"""
import sys
import textwrap
from datetime import date, timedelta
from pathlib import Path

import pytest


# ── Helpers ──────────────────────────────────────────────────────────────────

def _strip_emoji(name: str) -> str:
    import unicodedata
    i = 0
    while i < len(name):
        c = name[i]
        if ord(c) > 127 or unicodedata.category(c) in ("So", "Sk", "Mn", "Cf"):
            i += 1
        else:
            break
    return name[i:]


def _make_project(type_dir: Path, name: str = "test-project") -> Path:
    project_dir = type_dir / name
    project_dir.mkdir(parents=True, exist_ok=True)
    base = _strip_emoji(name)
    (project_dir / f"{base}-project.md").write_text(
        f"# {name}\n- Tipo: 💻 Software\n- Estado: [auto]\n- Prioridad: media\n"
    )
    (project_dir / f"{base}-logbook.md").write_text(f"# Logbook — {name}\n\n")
    (project_dir / f"{base}-agenda.md").write_text(f"# Agenda — {name}\n\n<!-- ... -->\n")
    (project_dir / f"{base}-highlights.md").write_text(f"# Highlights — {name}\n\n")
    (project_dir / "notes").mkdir(exist_ok=True)
    return project_dir


def _write_crono(project_dir: Path, slug: str, content: str) -> Path:
    """Write a cronograma file and return its path."""
    cronos = project_dir / "cronos"
    cronos.mkdir(exist_ok=True)
    path = cronos / f"crono-{slug}.md"
    path.write_text(textwrap.dedent(content), encoding="utf-8")
    return path


@pytest.fixture()
def projects_dir(tmp_path, monkeypatch):
    type_dir = tmp_path / "💻software"
    type_dir.mkdir()
    monkeypatch.setattr("core.config.ORBIT_HOME", tmp_path)
    monkeypatch.setattr("core.config._ORBIT_JSON", tmp_path / "orbit.json")
    monkeypatch.setattr("core.log.PROJECTS_DIR", tmp_path)
    return type_dir


# ═══════════════════════════════════════════════════════════════════════════════
# 1. Parsing
# ═══════════════════════════════════════════════════════════════════════════════

class TestParsing:
    def test_parse_task_line_basic(self):
        from core.cronograma import _parse_crono_task_line
        t = _parse_crono_task_line("- [ ] 1 Mi tarea")
        assert t is not None
        assert t["index"] == "1"
        assert t["title"] == "Mi tarea"
        assert t["done"] is False
        assert t["start_raw"] is None
        assert t["duration_raw"] is None

    def test_parse_task_line_with_start_and_duration(self):
        from core.cronograma import _parse_crono_task_line
        t = _parse_crono_task_line("- [ ] 1.1 Diseño | 2026-03-22 | 5d")
        assert t["index"] == "1.1"
        assert t["title"] == "Diseño"
        assert t["start_raw"] == "2026-03-22"
        assert t["duration_raw"] == "5d"

    def test_parse_task_line_with_iso_week(self):
        from core.cronograma import _parse_crono_task_line
        t = _parse_crono_task_line("- [ ] 1.1 Diseño | 2026-W12 | 1W")
        assert t["start_raw"] == "2026-W12"
        assert t["duration_raw"] == "1W"

    def test_parse_task_line_with_week_day(self):
        from core.cronograma import _parse_crono_task_line
        t = _parse_crono_task_line("- [ ] 1.1 Diseño | 2026-W12-wed | 3d")
        assert t["start_raw"] == "2026-W12-wed"

    def test_parse_task_line_with_after(self):
        from core.cronograma import _parse_crono_task_line
        t = _parse_crono_task_line("- [ ] 1.2 Construcción | after:1.1 | 2W")
        assert t["start_raw"] == "after:1.1"
        assert t["duration_raw"] == "2W"

    def test_parse_task_line_done(self):
        from core.cronograma import _parse_crono_task_line
        t = _parse_crono_task_line("- [x] 1.1 Completada | 2026-W12 | 1W")
        assert t["done"] is True

    def test_parse_task_line_parent_no_start_no_duration(self):
        from core.cronograma import _parse_crono_task_line
        t = _parse_crono_task_line("- [ ] 1 Fase principal")
        assert t["start_raw"] is None
        assert t["duration_raw"] is None

    def test_parse_task_line_returns_none_for_non_task(self):
        from core.cronograma import _parse_crono_task_line
        assert _parse_crono_task_line("# Header") is None
        assert _parse_crono_task_line("Some text") is None
        assert _parse_crono_task_line("") is None
        assert _parse_crono_task_line("    Indented note") is None

    def test_parse_task_line_depth(self):
        from core.cronograma import _parse_crono_task_line
        t0 = _parse_crono_task_line("- [ ] 1 Root")
        t1 = _parse_crono_task_line("  - [ ] 1.1 Child")
        t2 = _parse_crono_task_line("    - [ ] 1.1.1 Grandchild")
        assert t0["depth"] == 0
        assert t1["depth"] == 1
        assert t2["depth"] == 2

    def test_parse_task_line_tab_indent(self):
        from core.cronograma import _parse_crono_task_line
        t0 = _parse_crono_task_line("- [ ] 1 Root", indent_unit=1)
        t1 = _parse_crono_task_line("\t- [ ] 1.1 Child", indent_unit=1)
        t2 = _parse_crono_task_line("\t\t- [ ] 1.1.1 Grandchild", indent_unit=1)
        assert t0["depth"] == 0
        assert t1["depth"] == 1
        assert t2["depth"] == 2

    def test_parse_task_line_4space_indent(self):
        from core.cronograma import _parse_crono_task_line
        t0 = _parse_crono_task_line("- [ ] 1 Root", indent_unit=4)
        t1 = _parse_crono_task_line("    - [ ] 1.1 Child", indent_unit=4)
        t2 = _parse_crono_task_line("        - [ ] 1.1.1 Grandchild", indent_unit=4)
        assert t0["depth"] == 0
        assert t1["depth"] == 1
        assert t2["depth"] == 2

    def test_parse_crono_file(self, tmp_path):
        from core.cronograma import _parse_crono_file
        path = tmp_path / "crono-test.md"
        path.write_text(textwrap.dedent("""\
            # Cronograma: Mi Plan

            - [ ] 1 Fase 1
              - [ ] 1.1 Tarea A | 2026-01-05 | 1W
                  Nota sobre tarea A.
              - [ ] 1.2 Tarea B | after:1.1 | 2W
        """))
        data = _parse_crono_file(path)
        assert data["name"] == "Mi Plan"
        assert len(data["tasks"]) == 3
        assert data["tasks"][1]["notes"] == ["Nota sobre tarea A."]

    def test_parse_crono_file_tab_indent(self, tmp_path):
        from core.cronograma import _parse_crono_file
        path = tmp_path / "crono-test.md"
        path.write_text("# Cronograma: Tabs\n\n"
                        "- [ ] 1 Root\n"
                        "\t- [ ] 1.1 Child A\n"
                        "\t- [ ] 1.2 Child B\n"
                        "\t\t- [ ] 1.2.1 Grandchild\n")
        data = _parse_crono_file(path)
        assert len(data["tasks"]) == 4
        assert data["tasks"][0]["depth"] == 0
        assert data["tasks"][1]["depth"] == 1
        assert data["tasks"][3]["depth"] == 2

    def test_parse_crono_file_4space_indent(self, tmp_path):
        from core.cronograma import _parse_crono_file
        path = tmp_path / "crono-test.md"
        path.write_text("# Cronograma: 4sp\n\n"
                        "- [ ] 1 Root\n"
                        "    - [ ] 1.1 Child\n"
                        "        - [ ] 1.1.1 Grandchild\n")
        data = _parse_crono_file(path)
        assert len(data["tasks"]) == 3
        assert data["tasks"][0]["depth"] == 0
        assert data["tasks"][1]["depth"] == 1
        assert data["tasks"][2]["depth"] == 2

    def test_build_tree(self):
        from core.cronograma import _parse_crono_task_line, _build_tree
        tasks = [
            _parse_crono_task_line("- [ ] 1 Root"),
            _parse_crono_task_line("  - [ ] 1.1 Child A"),
            _parse_crono_task_line("  - [ ] 1.2 Child B"),
            _parse_crono_task_line("- [ ] 2 Another root"),
        ]
        roots = _build_tree(tasks)
        assert len(roots) == 2
        assert len(roots[0]["children"]) == 2
        assert roots[0]["children"][0]["index"] == "1.1"

    def test_build_tree_deep_nesting(self):
        from core.cronograma import _parse_crono_task_line, _build_tree
        tasks = [
            _parse_crono_task_line("- [ ] 1 L0"),
            _parse_crono_task_line("  - [ ] 1.1 L1"),
            _parse_crono_task_line("    - [ ] 1.1.1 L2"),
        ]
        roots = _build_tree(tasks)
        assert len(roots) == 1
        assert len(roots[0]["children"]) == 1
        assert len(roots[0]["children"][0]["children"]) == 1


# ═══════════════════════════════════════════════════════════════════════════════
# 2. Date computation
# ═══════════════════════════════════════════════════════════════════════════════

class TestDateComputation:
    def test_resolve_start_iso_date(self):
        from core.cronograma import _resolve_start
        d = _resolve_start("2026-03-22")
        assert d == date(2026, 3, 22)

    def test_resolve_start_iso_week(self):
        from core.cronograma import _resolve_start
        d = _resolve_start("2026-W12")
        # W12 2026: Monday = 2026-03-16
        assert d == date(2026, 3, 16)
        assert d.weekday() == 0  # Monday

    def test_resolve_start_week_day(self):
        from core.cronograma import _resolve_start
        d = _resolve_start("2026-W12-wed")
        assert d == date(2026, 3, 18)  # Wednesday of W12
        assert d.weekday() == 2  # Wednesday

    def test_resolve_start_after(self):
        from core.cronograma import _resolve_start
        result = _resolve_start("after:1.1")
        assert result == ("after", "1.1")

    def test_resolve_start_none(self):
        from core.cronograma import _resolve_start
        assert _resolve_start(None) is None
        assert _resolve_start("") is None

    def test_parse_duration_days(self):
        from core.cronograma import _parse_duration
        assert _parse_duration("5d") == 5
        assert _parse_duration("1d") == 1

    def test_parse_duration_weeks(self):
        from core.cronograma import _parse_duration
        assert _parse_duration("2W") == 14
        assert _parse_duration("1W") == 7

    def test_parse_duration_invalid(self):
        from core.cronograma import _parse_duration
        assert _parse_duration("") is None
        assert _parse_duration(None) is None
        assert _parse_duration("abc") is None
        assert _parse_duration("0d") is None

    def test_compute_dates_absolute(self):
        from core.cronograma import _parse_crono_task_line, _compute_dates
        tasks = [
            _parse_crono_task_line("- [ ] 1 Parent"),
            _parse_crono_task_line("  - [ ] 1.1 A | 2026-01-05 | 1W"),
            _parse_crono_task_line("  - [ ] 1.2 B | 2026-01-12 | 5d"),
        ]
        _compute_dates(tasks)
        assert tasks[1]["start_date"] == date(2026, 1, 5)
        assert tasks[1]["end_date"] == date(2026, 1, 11)  # 7 days, start + 6
        assert tasks[2]["start_date"] == date(2026, 1, 12)
        assert tasks[2]["end_date"] == date(2026, 1, 16)  # 5 days, start + 4

    def test_compute_dates_after_dep(self):
        from core.cronograma import _parse_crono_task_line, _compute_dates
        tasks = [
            _parse_crono_task_line("- [ ] 1 Parent"),
            _parse_crono_task_line("  - [ ] 1.1 A | 2026-01-05 | 1W"),
            _parse_crono_task_line("  - [ ] 1.2 B | after:1.1 | 5d"),
        ]
        _compute_dates(tasks)
        # 1.1 ends 2026-01-11, so 1.2 starts 2026-01-12
        assert tasks[2]["start_date"] == date(2026, 1, 12)
        assert tasks[2]["end_date"] == date(2026, 1, 16)

    def test_compute_dates_chain(self):
        from core.cronograma import _parse_crono_task_line, _compute_dates
        tasks = [
            _parse_crono_task_line("- [ ] 1 Parent"),
            _parse_crono_task_line("  - [ ] 1.1 A | 2026-01-05 | 3d"),
            _parse_crono_task_line("  - [ ] 1.2 B | after:1.1 | 3d"),
            _parse_crono_task_line("  - [ ] 1.3 C | after:1.2 | 3d"),
        ]
        _compute_dates(tasks)
        assert tasks[1]["end_date"] == date(2026, 1, 7)
        assert tasks[2]["start_date"] == date(2026, 1, 8)
        assert tasks[2]["end_date"] == date(2026, 1, 10)
        assert tasks[3]["start_date"] == date(2026, 1, 11)
        assert tasks[3]["end_date"] == date(2026, 1, 13)

    def test_compute_dates_parent_inherits(self):
        from core.cronograma import _parse_crono_task_line, _compute_dates
        tasks = [
            _parse_crono_task_line("- [ ] 1 Parent"),
            _parse_crono_task_line("  - [ ] 1.1 A | 2026-01-05 | 1W"),
            _parse_crono_task_line("  - [ ] 1.2 B | 2026-01-20 | 3d"),
        ]
        _compute_dates(tasks)
        assert tasks[0]["start_date"] == date(2026, 1, 5)
        assert tasks[0]["end_date"] == date(2026, 1, 22)

    def test_compute_dates_dag_only(self):
        from core.cronograma import _parse_crono_task_line, _compute_dates
        tasks = [
            _parse_crono_task_line("- [ ] 1 Parent"),
            _parse_crono_task_line("  - [ ] 1.1 A"),
            _parse_crono_task_line("  - [ ] 1.2 B | after:1.1"),
        ]
        _compute_dates(tasks)
        # DAG-only: no dates computed
        assert tasks[1]["start_date"] is None
        assert tasks[1]["end_date"] is None

    def test_end_date_calculation(self):
        from core.cronograma import _parse_crono_task_line, _compute_dates
        # 1d task should start and end on the same day
        tasks = [
            _parse_crono_task_line("- [ ] 1 A | 2026-01-05 | 1d"),
        ]
        _compute_dates(tasks)
        assert tasks[0]["start_date"] == date(2026, 1, 5)
        assert tasks[0]["end_date"] == date(2026, 1, 5)


# ═══════════════════════════════════════════════════════════════════════════════
# 3. Topological sort
# ═══════════════════════════════════════════════════════════════════════════════

class TestTopoSort:
    def test_topo_sort_linear(self):
        from core.cronograma import _parse_crono_task_line, _topo_sort_indices
        tasks = [
            _parse_crono_task_line("- [ ] 1 A | 2026-01-05 | 3d"),
            _parse_crono_task_line("- [ ] 2 B | after:1 | 3d"),
            _parse_crono_task_line("- [ ] 3 C | after:2 | 3d"),
        ]
        deps = {"1": set(), "2": {"1"}, "3": {"2"}}
        order = _topo_sort_indices(tasks, deps)
        assert order.index("1") < order.index("2")
        assert order.index("2") < order.index("3")

    def test_topo_sort_no_deps(self):
        from core.cronograma import _parse_crono_task_line, _topo_sort_indices
        tasks = [
            _parse_crono_task_line("- [ ] 1 A | 2026-01-05 | 3d"),
            _parse_crono_task_line("- [ ] 2 B | 2026-01-05 | 3d"),
        ]
        deps = {"1": set(), "2": set()}
        order = _topo_sort_indices(tasks, deps)
        assert len(order) == 2

    def test_topo_sort_diamond(self):
        from core.cronograma import _parse_crono_task_line, _topo_sort_indices
        tasks = [
            _parse_crono_task_line("- [ ] 1 A | 2026-01-05 | 3d"),
            _parse_crono_task_line("- [ ] 2 B | after:1 | 3d"),
            _parse_crono_task_line("- [ ] 3 C | after:1 | 3d"),
            _parse_crono_task_line("- [ ] 4 D | after:2 | 3d"),
        ]
        deps = {"1": set(), "2": {"1"}, "3": {"1"}, "4": {"2"}}
        order = _topo_sort_indices(tasks, deps)
        assert order.index("1") < order.index("2")
        assert order.index("1") < order.index("3")
        assert order.index("2") < order.index("4")

    def test_topo_sort_cycle_raises(self):
        from core.cronograma import _parse_crono_task_line, _topo_sort_indices
        tasks = [
            _parse_crono_task_line("- [ ] 1 A | after:2 | 3d"),
            _parse_crono_task_line("- [ ] 2 B | after:1 | 3d"),
        ]
        deps = {"1": {"2"}, "2": {"1"}}
        with pytest.raises(ValueError, match="Ciclo"):
            _topo_sort_indices(tasks, deps)

    def test_topo_sort_self_loop(self):
        from core.cronograma import _parse_crono_task_line, _topo_sort_indices
        tasks = [
            _parse_crono_task_line("- [ ] 1 A | after:1 | 3d"),
        ]
        deps = {"1": {"1"}}
        with pytest.raises(ValueError, match="Ciclo"):
            _topo_sort_indices(tasks, deps)


# ═══════════════════════════════════════════════════════════════════════════════
# 4. Doctor validation
# ═══════════════════════════════════════════════════════════════════════════════

class TestDoctorValidation:
    def test_check_valid_cronograma(self, tmp_path):
        from core.cronograma import _check_cronograma
        path = tmp_path / "crono-test.md"
        path.write_text(textwrap.dedent("""\
            # Cronograma: Test

            - [ ] 1 Parent
              - [ ] 1.1 A | 2026-01-05 | 1W
              - [ ] 1.2 B | after:1.1 | 2W
        """))
        issues = _check_cronograma("proj", path)
        assert len(issues) == 0

    def test_check_duplicate_indices(self, tmp_path):
        from core.cronograma import _check_cronograma
        path = tmp_path / "crono-test.md"
        path.write_text(textwrap.dedent("""\
            # Cronograma: Test

            - [ ] 1.1 A | 2026-01-05 | 1W
            - [ ] 1.1 B | 2026-01-12 | 1W
        """))
        issues = _check_cronograma("proj", path)
        msgs = [i.msg for i in issues]
        assert any("duplicado" in m.lower() for m in msgs)

    def test_check_dep_missing(self, tmp_path):
        from core.cronograma import _check_cronograma
        path = tmp_path / "crono-test.md"
        path.write_text(textwrap.dedent("""\
            # Cronograma: Test

            - [ ] 1 A | after:99 | 1W
        """))
        issues = _check_cronograma("proj", path)
        msgs = [i.msg for i in issues]
        assert any("inexistente" in m.lower() for m in msgs)

    def test_check_cycle_detected(self, tmp_path):
        from core.cronograma import _check_cronograma
        path = tmp_path / "crono-test.md"
        path.write_text(textwrap.dedent("""\
            # Cronograma: Test

            - [ ] 1 A | after:2 | 1W
            - [ ] 2 B | after:1 | 1W
        """))
        issues = _check_cronograma("proj", path)
        msgs = [i.msg for i in issues]
        assert any("ciclo" in m.lower() for m in msgs)

    def test_check_leaf_without_start(self, tmp_path):
        from core.cronograma import _check_cronograma
        path = tmp_path / "crono-test.md"
        path.write_text(textwrap.dedent("""\
            # Cronograma: Test

            - [ ] 1 Parent
              - [ ] 1.1 A | | 1W
              - [ ] 1.2 B | 2026-01-05 | 1W
        """))
        issues = _check_cronograma("proj", path)
        msgs = [i.msg for i in issues]
        assert any("sin inicio" in m.lower() for m in msgs)

    def test_check_leaf_without_duration(self, tmp_path):
        from core.cronograma import _check_cronograma
        path = tmp_path / "crono-test.md"
        path.write_text(textwrap.dedent("""\
            # Cronograma: Test

            - [ ] 1 Parent
              - [ ] 1.1 A | 2026-01-05
              - [ ] 1.2 B | 2026-01-05 | 1W
        """))
        issues = _check_cronograma("proj", path)
        msgs = [i.msg for i in issues]
        assert any("sin duración" in m.lower() for m in msgs)

    def test_check_parent_with_explicit_warning(self, tmp_path):
        from core.cronograma import _check_cronograma
        path = tmp_path / "crono-test.md"
        path.write_text(textwrap.dedent("""\
            # Cronograma: Test

            - [ ] 1 Parent | 2026-01-01 | 3W
              - [ ] 1.1 A | 2026-01-05 | 1W
        """))
        issues = _check_cronograma("proj", path)
        msgs = [i.msg for i in issues]
        assert any("padre con inicio" in m.lower() for m in msgs)
        assert any("padre con duración" in m.lower() for m in msgs)

    def test_check_invalid_date_format(self, tmp_path):
        from core.cronograma import _check_cronograma
        path = tmp_path / "crono-test.md"
        path.write_text(textwrap.dedent("""\
            # Cronograma: Test

            - [ ] 1 A | enero-2026 | 1W
        """))
        issues = _check_cronograma("proj", path)
        msgs = [i.msg for i in issues]
        assert any("fecha" in m.lower() for m in msgs)

    def test_check_invalid_duration_format(self, tmp_path):
        from core.cronograma import _check_cronograma
        path = tmp_path / "crono-test.md"
        path.write_text(textwrap.dedent("""\
            # Cronograma: Test

            - [ ] 1 A | 2026-01-05 | 3months
        """))
        issues = _check_cronograma("proj", path)
        msgs = [i.msg for i in issues]
        assert any("duración" in m.lower() for m in msgs)

    def test_check_dag_only_no_errors(self, tmp_path):
        from core.cronograma import _check_cronograma
        path = tmp_path / "crono-test.md"
        path.write_text(textwrap.dedent("""\
            # Cronograma: Test

            - [ ] 1 A
            - [ ] 2 B | after:1
        """))
        issues = _check_cronograma("proj", path)
        assert len(issues) == 0


# ═══════════════════════════════════════════════════════════════════════════════
# 5. Commands
# ═══════════════════════════════════════════════════════════════════════════════

class TestCommands:
    def test_crono_add_creates_file(self, projects_dir):
        from core.cronograma import run_crono_add
        proj = _make_project(projects_dir)
        result = run_crono_add(project=proj.name, name="Mi Plan")
        assert result == 0
        crono_path = proj / "cronos" / "crono-mi-plan.md"
        assert crono_path.exists()
        content = crono_path.read_text()
        assert "# Cronograma: Mi Plan" in content

    def test_crono_add_creates_cronos_dir(self, projects_dir):
        from core.cronograma import run_crono_add
        proj = _make_project(projects_dir)
        assert not (proj / "cronos").exists()
        run_crono_add(project=proj.name, name="Test")
        assert (proj / "cronos").is_dir()

    def test_crono_add_registers_in_agenda(self, projects_dir):
        from core.cronograma import run_crono_add
        proj = _make_project(projects_dir)
        run_crono_add(project=proj.name, name="Mi Plan")
        base = _strip_emoji(proj.name)
        agenda = (proj / f"{base}-agenda.md").read_text()
        assert "## 📊 Cronogramas" in agenda
        assert "[Mi Plan](cronos/crono-mi-plan.md)" in agenda

    def test_crono_add_duplicate_fails(self, projects_dir):
        from core.cronograma import run_crono_add
        proj = _make_project(projects_dir)
        run_crono_add(project=proj.name, name="Test")
        result = run_crono_add(project=proj.name, name="Test")
        assert result == 1

    def test_crono_show_basic(self, projects_dir, capsys):
        from core.cronograma import run_crono_add, run_crono_show
        proj = _make_project(projects_dir)
        run_crono_add(project=proj.name, name="Test")
        result = run_crono_show(project=proj.name, name="test")
        assert result == 0
        out = capsys.readouterr().out
        assert "📊 Test" in out

    def test_crono_show_dag_only(self, projects_dir, capsys):
        from core.cronograma import run_crono_show
        proj = _make_project(projects_dir)
        _write_crono(proj, "dag", """\
            # Cronograma: DAG

            - [ ] 1 A
            - [ ] 2 B | after:1
        """)
        result = run_crono_show(project=proj.name, name="dag")
        assert result == 0
        out = capsys.readouterr().out
        assert "DAG" in out
        assert "Inicio" not in out  # No date columns in DAG mode

    def test_crono_list_empty(self, projects_dir, capsys):
        from core.cronograma import run_crono_list
        proj = _make_project(projects_dir)
        result = run_crono_list(project=proj.name)
        assert result == 0
        out = capsys.readouterr().out
        assert "No hay cronogramas" in out

    def test_crono_list_with_entries(self, projects_dir, capsys):
        from core.cronograma import run_crono_add, run_crono_list
        proj = _make_project(projects_dir)
        run_crono_add(project=proj.name, name="Plan A")
        run_crono_add(project=proj.name, name="Plan B")
        result = run_crono_list(project=proj.name)
        assert result == 0
        out = capsys.readouterr().out
        assert "Plan A" in out
        assert "Plan B" in out

    def test_crono_done_marks_task(self, projects_dir, capsys):
        from core.cronograma import run_crono_add, run_crono_done
        proj = _make_project(projects_dir)
        run_crono_add(project=proj.name, name="Test")
        result = run_crono_done(project=proj.name, name="test", index="1.1")
        assert result == 0
        # Verify file changed
        content = (proj / "cronos" / "crono-test.md").read_text()
        assert "[x] 1.1" in content

    def test_crono_done_nonexistent_index(self, projects_dir, capsys):
        from core.cronograma import run_crono_add, run_crono_done
        proj = _make_project(projects_dir)
        run_crono_add(project=proj.name, name="Test")
        result = run_crono_done(project=proj.name, name="test", index="99")
        assert result == 1

    def test_crono_done_partial_title(self, projects_dir, capsys):
        from core.cronograma import run_crono_done
        proj = _make_project(projects_dir)
        _write_crono(proj, "test", """\
            # Cronograma: Test

            - [ ] 1 Root
              - [ ] 1.1 Alpha task
              - [ ] 1.2 Beta task
        """)
        result = run_crono_done(project=proj.name, name="test", index="Alpha")
        assert result == 0
        content = (proj / "cronos" / "crono-test.md").read_text()
        assert "[x] 1.1" in content
        assert "[ ] 1.2" in content

    def test_crono_done_partial_index(self, projects_dir, capsys):
        from core.cronograma import run_crono_done
        proj = _make_project(projects_dir)
        _write_crono(proj, "test", """\
            # Cronograma: Test

            - [ ] 1 Root
              - [ ] 1.1 A
              - [ ] 1.2 B
        """)
        # "1.2" matches exactly one pending leaf
        result = run_crono_done(project=proj.name, name="test", index="1.2")
        assert result == 0
        content = (proj / "cronos" / "crono-test.md").read_text()
        assert "[x] 1.2" in content

    def test_crono_done_all_complete(self, projects_dir, capsys):
        from core.cronograma import run_crono_done
        proj = _make_project(projects_dir)
        _write_crono(proj, "test", """\
            # Cronograma: Test

            - [x] 1 Done
        """)
        result = run_crono_done(project=proj.name, name="test")
        assert result == 0
        out = capsys.readouterr().out
        assert "completadas" in out.lower()

    def test_crono_check_clean(self, projects_dir, capsys):
        from core.cronograma import run_crono_add, run_crono_check
        proj = _make_project(projects_dir)
        run_crono_add(project=proj.name, name="Test")
        result = run_crono_check(project=proj.name, name="test")
        assert result == 0
        out = capsys.readouterr().out
        assert "sin problemas" in out

    def test_crono_check_with_issues(self, projects_dir, capsys):
        from core.cronograma import run_crono_check
        proj = _make_project(projects_dir)
        _write_crono(proj, "bad", """\
            # Cronograma: Bad

            - [ ] 1 A | after:99 | 1W
        """)
        result = run_crono_check(project=proj.name, name="bad")
        assert result == 1

    def test_crono_edit_not_found(self, projects_dir, capsys):
        from core.cronograma import run_crono_edit
        proj = _make_project(projects_dir)
        result = run_crono_edit(project=proj.name, name="nonexistent")
        assert result == 1

    def test_crono_not_found(self, projects_dir, capsys):
        from core.cronograma import run_crono_show
        proj = _make_project(projects_dir)
        result = run_crono_show(project=proj.name, name="nonexistent")
        assert result == 1


# ═══════════════════════════════════════════════════════════════════════════════
# 6. Fase 1b — Metadata
# ═══════════════════════════════════════════════════════════════════════════════

class TestMetadata:
    def test_metadata_initial_time(self, tmp_path):
        from core.cronograma import _parse_crono_file, _compute_dates
        path = tmp_path / "crono-test.md"
        path.write_text(textwrap.dedent("""\
            # Cronograma: Test

            initial-time: 2026-06-01

            - [ ] 1 A | | 5d
        """))
        data = _parse_crono_file(path)
        _compute_dates(data["tasks"], data["metadata"])
        assert data["tasks"][0]["start_date"] == date(2026, 6, 1)
        assert data["tasks"][0]["end_date"] == date(2026, 6, 5)

    def test_metadata_initial_time_default_today(self, tmp_path):
        from core.cronograma import _parse_crono_file, _compute_dates
        path = tmp_path / "crono-test.md"
        path.write_text(textwrap.dedent("""\
            # Cronograma: Test

            - [ ] 1 A | | 3d
        """))
        data = _parse_crono_file(path)
        today = date.today()
        _compute_dates(data["tasks"], data["metadata"], today=today)
        assert data["tasks"][0]["start_date"] == today

    def test_metadata_exclude_weekdays(self, tmp_path):
        from core.cronograma import _parse_crono_file, _compute_dates
        path = tmp_path / "crono-test.md"
        path.write_text(textwrap.dedent("""\
            # Cronograma: Test

            exclude: sat, sun

            - [ ] 1 A | 2026-01-05 | 5d
        """))
        data = _parse_crono_file(path)
        _compute_dates(data["tasks"], data["metadata"])
        # 2026-01-05 is Monday. 5 working days = Mon-Fri = 2026-01-09
        assert data["tasks"][0]["start_date"] == date(2026, 1, 5)
        assert data["tasks"][0]["end_date"] == date(2026, 1, 9)

    def test_metadata_exclude_dates(self, tmp_path):
        from core.cronograma import _parse_crono_file, _compute_dates
        path = tmp_path / "crono-test.md"
        path.write_text(textwrap.dedent("""\
            # Cronograma: Test

            exclude: 2026-01-07

            - [ ] 1 A | 2026-01-05 | 5d
        """))
        data = _parse_crono_file(path)
        _compute_dates(data["tasks"], data["metadata"])
        # 5 days starting Jan 5, skipping Jan 7: Jan 5,6,8,9,10
        assert data["tasks"][0]["end_date"] == date(2026, 1, 10)

    def test_metadata_exclude_weeks(self, tmp_path):
        from core.cronograma import _parse_crono_file, _compute_dates
        path = tmp_path / "crono-test.md"
        path.write_text(textwrap.dedent("""\
            # Cronograma: Test

            exclude: 2026-W02

            - [ ] 1 A | 2026-01-05 | 10d
        """))
        data = _parse_crono_file(path)
        _compute_dates(data["tasks"], data["metadata"])
        # 2026-01-05 is Monday W01. W02 starts 2026-01-05? Let's check.
        # Actually 2026-01-05 is in W02 (Jan 1 is Thursday W01).
        # ISO: 2026-01-05 = Monday of W02.
        # So W02 = Jan 5-11 excluded. 10 days starting from next available = Jan 12.
        # Actually start is Jan 5 which is IN W02, so it gets skipped.
        # The task starts on Jan 12 (first non-excluded day after Jan 5... wait.
        # The start date is fixed at 2026-01-05, but those days are excluded.
        # _add_working_days counts non-excluded days.
        # Start = Jan 5 (Mon W02, excluded), Jan 6 (excluded)... Jan 11 (excluded)
        # Jan 12 (Mon W03): day 1, Jan 13: day 2, ..., Jan 21: day 10
        assert data["tasks"][0]["end_date"] == date(2026, 1, 21)

    def test_duration_with_excludes_chained(self, tmp_path):
        from core.cronograma import _parse_crono_file, _compute_dates
        path = tmp_path / "crono-test.md"
        path.write_text(textwrap.dedent("""\
            # Cronograma: Test

            exclude: sat, sun

            - [ ] 1 Parent
              - [ ] 1.1 A | 2026-01-05 | 5d
              - [ ] 1.2 B | after:1.1 | 5d
        """))
        data = _parse_crono_file(path)
        _compute_dates(data["tasks"], data["metadata"])
        # 1.1: Mon Jan 5 - Fri Jan 9 (5 working days)
        assert data["tasks"][1]["end_date"] == date(2026, 1, 9)
        # 1.2: starts Mon Jan 12 (next working day after Jan 9)
        assert data["tasks"][2]["start_date"] == date(2026, 1, 12)
        # 1.2: Mon Jan 12 - Fri Jan 16 (5 working days)
        assert data["tasks"][2]["end_date"] == date(2026, 1, 16)

    def test_parse_excludes(self):
        from core.cronograma import _parse_excludes
        meta = {"exclude": "sat, sun, 2026-04-03, 2026-W15"}
        excludes = _parse_excludes(meta)
        assert 5 in excludes  # Saturday
        assert 6 in excludes  # Sunday
        assert date(2026, 4, 3) in excludes
        assert (2026, 15) in excludes


# ═══════════════════════════════════════════════════════════════════════════════
# 7. Doctor integration
# ═══════════════════════════════════════════════════════════════════════════════

class TestDoctorIntegration:
    def test_doctor_finds_cronograma_issues(self, projects_dir):
        from core.doctor import check_project
        proj = _make_project(projects_dir)
        _write_crono(proj, "bad", """\
            # Cronograma: Bad

            - [ ] 1 A | after:99 | 1W
        """)
        issues = check_project(proj)
        crono_issues = [i for i in issues if "crono" in i.file.lower()]
        assert len(crono_issues) > 0

    def test_doctor_clean_with_valid_cronograma(self, projects_dir):
        from core.doctor import check_project
        proj = _make_project(projects_dir)
        _write_crono(proj, "good", """\
            # Cronograma: Good

            - [ ] 1 Parent
              - [ ] 1.1 A | 2026-01-05 | 1W
        """)
        issues = check_project(proj)
        crono_issues = [i for i in issues if "crono" in i.file.lower()]
        assert len(crono_issues) == 0


# ═══════════════════════════════════════════════════════════════════════════════
# 8. Format / Show
# ═══════════════════════════════════════════════════════════════════════════════

class TestFormat:
    def test_format_show_with_dates(self, tmp_path):
        from core.cronograma import _parse_crono_file, _compute_dates, _format_show
        path = tmp_path / "crono-test.md"
        path.write_text(textwrap.dedent("""\
            # Cronograma: Test

            - [ ] 1 Parent
              - [ ] 1.1 A | 2026-01-05 | 1W
              - [x] 1.2 B | after:1.1 | 3d
        """))
        data = _parse_crono_file(path)
        _compute_dates(data["tasks"], data["metadata"])
        output = _format_show(data)
        assert "📊 Test" in output
        assert "2026-01-05" in output
        assert "1.2" in output

    def test_format_show_dag_only(self, tmp_path):
        from core.cronograma import _parse_crono_file, _compute_dates, _format_show
        path = tmp_path / "crono-test.md"
        path.write_text(textwrap.dedent("""\
            # Cronograma: DAG Only

            - [ ] 1 A
            - [ ] 2 B | after:1
        """))
        data = _parse_crono_file(path)
        _compute_dates(data["tasks"], data["metadata"])
        output = _format_show(data)
        assert "DAG Only" in output
        assert "Inicio" not in output

    def test_format_show_empty(self, tmp_path):
        from core.cronograma import _parse_crono_file, _format_show
        path = tmp_path / "crono-test.md"
        path.write_text("# Cronograma: Empty\n")
        data = _parse_crono_file(path)
        output = _format_show(data)
        assert "vacío" in output

    def test_format_duration(self):
        from core.cronograma import _format_duration
        assert _format_duration(date(2026, 1, 5), date(2026, 1, 11)) == "1W"
        assert _format_duration(date(2026, 1, 5), date(2026, 1, 9)) == "5d"
        assert _format_duration(None, None) == ""


# ═══════════════════════════════════════════════════════════════════════════════
# 9. Gantt
# ═══════════════════════════════════════════════════════════════════════════════

class TestGantt:
    def test_gantt_dag_only(self, tmp_path):
        from core.cronograma import _parse_crono_file, _compute_dates, _format_gantt
        path = tmp_path / "crono-test.md"
        path.write_text(textwrap.dedent("""\
            # Cronograma: DAG

            - [ ] 1 Root
              - [x] 1.1 Done task
              - [ ] 1.2 Pending | after:1.1
        """))
        data = _parse_crono_file(path)
        _compute_dates(data["tasks"], data["metadata"])
        output = _format_gantt(data)
        assert "DAG" in output
        assert "1/2" in output
        assert "░" in output
        assert "█" in output
        # No date columns in DAG mode
        assert "Inicio" not in output

    def test_gantt_dated(self, tmp_path):
        from core.cronograma import _parse_crono_file, _compute_dates, _format_gantt
        path = tmp_path / "crono-test.md"
        path.write_text(textwrap.dedent("""\
            # Cronograma: Dated

            - [ ] 1 Root
              - [x] 1.1 A | 2026-01-05 | 1W
              - [ ] 1.2 B | after:1.1 | 3d
        """))
        data = _parse_crono_file(path)
        _compute_dates(data["tasks"], data["metadata"])
        output = _format_gantt(data, today=date(2026, 1, 10))
        assert "Dated" in output
        assert "█" in output
        assert "[x]" in output
        assert "[ ]" in output

    def test_gantt_empty(self, tmp_path):
        from core.cronograma import _parse_crono_file, _format_gantt
        path = tmp_path / "crono-test.md"
        path.write_text("# Cronograma: Empty\n")
        data = _parse_crono_file(path)
        output = _format_gantt(data)
        assert "vacío" in output

    def test_gantt_colorblind_safe(self, tmp_path):
        from core.cronograma import _parse_crono_file, _compute_dates, _format_gantt
        path = tmp_path / "crono-test.md"
        path.write_text(textwrap.dedent("""\
            # Cronograma: Colors

            - [ ] 1 Root
              - [x] 1.1 Done | 2026-01-05 | 3d
              - [ ] 1.2 Overdue | after:1.1 | 3d
        """))
        data = _parse_crono_file(path)
        _compute_dates(data["tasks"], data["metadata"])
        output = _format_gantt(data, today=date(2026, 1, 20))
        # No red or green ANSI codes
        assert "\033[31m" not in output
        assert "\033[32m" not in output

    def test_gantt_force_progress(self, tmp_path):
        from core.cronograma import _parse_crono_file, _compute_dates, _format_gantt
        path = tmp_path / "crono-test.md"
        path.write_text(textwrap.dedent("""\
            # Cronograma: Dated

            - [ ] 1 Root
              - [x] 1.1 A | 2026-01-05 | 1W
              - [ ] 1.2 B | after:1.1 | 3d
        """))
        data = _parse_crono_file(path)
        _compute_dates(data["tasks"], data["metadata"])
        output = _format_gantt(data, mode="progress")
        # Progress mode: no date columns, has progress bars
        assert "░" in output or "█" in output
        assert "1/2" in output

    def test_run_crono_gantt(self, projects_dir, capsys):
        from core.cronograma import run_crono_add, run_crono_gantt
        proj = _make_project(projects_dir)
        run_crono_add(project=proj.name, name="Test")
        result = run_crono_gantt(project=proj.name, name="test")
        assert result == 0
        out = capsys.readouterr().out
        assert "Test" in out


# ═══════════════════════════════════════════════════════════════════════════════
# 10. Reindex
# ═══════════════════════════════════════════════════════════════════════════════

class TestReindex:
    def test_reindex_gaps(self):
        from core.cronograma import _reindex_lines
        lines = [
            "# Cronograma: test",
            "",
            "- [ ] 1 Root",
            "  - [ ] 1.1 A",
            "  - [ ] 1.3 B",
            "  - [ ] 1.5 C",
        ]
        new_lines, renames = _reindex_lines(lines)
        assert renames["1.3"] == "1.2"
        assert renames["1.5"] == "1.3"
        assert "1.2 B" in new_lines[4]
        assert "1.3 C" in new_lines[5]

    def test_reindex_updates_after_refs(self):
        from core.cronograma import _reindex_lines
        lines = [
            "- [ ] 1 Root",
            "  - [ ] 1.1 A",
            "  - [ ] 1.3 B | after:1.1",
            "    - [ ] 1.3.2 C",
            "    - [ ] 1.3.3 D | after:1.3.2",
        ]
        new_lines, renames = _reindex_lines(lines)
        assert renames["1.3"] == "1.2"
        assert renames["1.3.2"] == "1.2.1"
        assert renames["1.3.3"] == "1.2.2"
        assert "after:1.1" in new_lines[2]       # unchanged ref
        assert "after:1.2.1" in new_lines[4]     # updated ref

    def test_reindex_already_correct(self):
        from core.cronograma import _reindex_lines
        lines = [
            "- [ ] 1 Root",
            "  - [ ] 1.1 A",
            "  - [ ] 1.2 B",
        ]
        _, renames = _reindex_lines(lines)
        changes = sum(1 for o, n in renames.items() if o != n)
        assert changes == 0

    def test_reindex_deep_nesting(self):
        from core.cronograma import _reindex_lines
        lines = [
            "- [ ] 1 L0",
            "  - [ ] 1.5 L1",
            "    - [ ] 1.5.3 L2",
        ]
        _, renames = _reindex_lines(lines)
        assert renames["1.5"] == "1.1"
        assert renames["1.5.3"] == "1.1.1"

    def test_run_crono_reindex(self, projects_dir, capsys):
        from core.cronograma import run_crono_add, run_crono_reindex
        proj = _make_project(projects_dir)
        run_crono_add(project=proj.name, name="Test")

        # Manually mess up the indices
        crono_path = proj / "cronos" / "crono-test.md"
        crono_path.write_text(
            "# Cronograma: Test\n\n"
            "- [ ] 1 Root\n"
            "  - [ ] 1.1 A\n"
            "  - [ ] 1.5 B\n"
        )
        result = run_crono_reindex(project=proj.name, name="test")
        assert result == 0
        content = crono_path.read_text()
        assert "1.2 B" in content
        assert "1.5" not in content


# ═══════════════════════════════════════════════════════════════════════════════
# 11. Inherit after: from parent
# ═══════════════════════════════════════════════════════════════════════════════

class TestInheritAfter:
    def test_leaf_inherits_after_from_parent(self):
        from core.cronograma import _parse_crono_task_line, _compute_dates
        tasks = [
            _parse_crono_task_line("- [ ] 1 Root"),
            _parse_crono_task_line("  - [ ] 1.1 A | 2026-01-05 | 3d"),
            _parse_crono_task_line("  - [ ] 1.2 B | after:1.1"),      # parent with after:
            _parse_crono_task_line("    - [ ] 1.2.1 Sub | | 2d"),     # inherits after:1.1
            _parse_crono_task_line("    - [ ] 1.2.2 Sub2 | after:1.2.1 | 2d"),
        ]
        _compute_dates(tasks, {}, today=date(2026, 1, 5))
        # 1.1 ends Jan 7. 1.2.1 should start Jan 8 (inherited after:1.1)
        assert tasks[3]["start_date"] == date(2026, 1, 8)
        assert tasks[3]["end_date"] == date(2026, 1, 9)
        # 1.2.2 chains from 1.2.1
        assert tasks[4]["start_date"] == date(2026, 1, 10)

    def test_leaf_with_own_start_not_overridden(self):
        from core.cronograma import _parse_crono_task_line, _compute_dates
        tasks = [
            _parse_crono_task_line("- [ ] 1 Root"),
            _parse_crono_task_line("  - [ ] 1.1 A | 2026-01-05 | 3d"),
            _parse_crono_task_line("  - [ ] 1.2 B | after:1.1"),
            _parse_crono_task_line("    - [ ] 1.2.1 Sub | 2026-02-01 | 2d"),  # explicit start
        ]
        _compute_dates(tasks, {}, today=date(2026, 1, 5))
        # Should keep its own explicit start, not inherit
        assert tasks[3]["start_date"] == date(2026, 2, 1)

    def test_doctor_no_warn_inherited_after(self, tmp_path):
        from core.cronograma import _check_cronograma
        path = tmp_path / "crono-test.md"
        path.write_text(textwrap.dedent("""\
            # Cronograma: Test

            - [ ] 1 Root
              - [ ] 1.1 A | 2026-01-05 | 3d
              - [ ] 1.2 B | after:1.1
                - [ ] 1.2.1 Sub | | 2d
        """))
        issues = _check_cronograma("proj", path)
        # No "sin inicio" warning for 1.2.1 (inherits from parent)
        # No "padre con inicio" warning for 1.2 (after: is valid on parents)
        assert len(issues) == 0

    def test_doctor_warns_absolute_date_on_parent(self, tmp_path):
        from core.cronograma import _check_cronograma
        path = tmp_path / "crono-test.md"
        path.write_text(textwrap.dedent("""\
            # Cronograma: Test

            - [ ] 1 Root | 2026-01-01
              - [ ] 1.1 A | 2026-01-05 | 3d
        """))
        issues = _check_cronograma("proj", path)
        msgs = [i.msg for i in issues]
        assert any("padre con inicio" in m.lower() for m in msgs)

    def test_grandparent_inheritance(self):
        from core.cronograma import _parse_crono_task_line, _compute_dates
        tasks = [
            _parse_crono_task_line("- [ ] 1 Root | after:0"),  # won't resolve (no 0)
            _parse_crono_task_line("  - [ ] 1.1 Phase | after:0"),  # grandparent
            _parse_crono_task_line("    - [ ] 1.1.1 Group"),        # parent (no after)
            _parse_crono_task_line("      - [ ] 1.1.1.1 Leaf | | 2d"),  # should inherit from 1.1
        ]
        # The leaf should get _inherited_after from grandparent 1.1
        _compute_dates(tasks, {}, today=date(2026, 1, 5))
        # after:0 won't resolve (no task 0), so start_date stays None
        assert tasks[3]["start_date"] is None

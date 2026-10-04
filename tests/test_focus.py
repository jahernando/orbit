"""Unit + integration tests for core/focus.py — módulo focus."""

from datetime import date, timedelta
from pathlib import Path

import pytest


# ── Helpers ────────────────────────────────────────────────────────────────

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


def _make_project(type_dir: Path, name: str) -> Path:
    project_dir = type_dir / name
    project_dir.mkdir(parents=True, exist_ok=True)
    base = _strip_emoji(name)
    (project_dir / f"{base}-project.md").write_text(
        f"# {name}\n- Tipo: 🌀 Investigación\n- Estado: [auto]\n- Prioridad: media\n"
    )
    (project_dir / f"{base}-logbook.md").write_text("# Logbook\n\n")
    (project_dir / f"{base}-agenda.md").write_text("# Agenda\n\n")
    (project_dir / f"{base}-highlights.md").write_text("# Highlights\n\n")
    (project_dir / "notes").mkdir(exist_ok=True)
    return project_dir


def _make_mission(tmp_path: Path) -> Path:
    """Create ☀️mision/☀️mission/ with full new-format scaffold."""
    type_dir = tmp_path / "☀️mision"
    type_dir.mkdir(exist_ok=True)
    return _make_project(type_dir, "☀️mission")


def _agenda_path(project_dir: Path) -> Path:
    return project_dir / f"{_strip_emoji(project_dir.name)}-agenda.md"


def _feed_inputs(monkeypatch, answers):
    """Make input() consume from a list. EOF after the list."""
    it = iter(answers)
    def _fake(prompt=""):
        try:
            return next(it)
        except StopIteration:
            raise EOFError()
    monkeypatch.setattr("builtins.input", _fake)


# ── Fixtures ───────────────────────────────────────────────────────────────

@pytest.fixture()
def workspace(tmp_path, monkeypatch):
    """Patch ORBIT_HOME and return a tmp dir suitable for iter_project_dirs."""
    monkeypatch.setattr("core.config.ORBIT_HOME", tmp_path)
    monkeypatch.setattr("core.config._ORBIT_JSON", tmp_path / "orbit.json")
    monkeypatch.setattr("core.log.PROJECTS_DIR", tmp_path)
    return tmp_path


@pytest.fixture()
def mission(workspace):
    return _make_mission(workspace)


@pytest.fixture()
def other_project(workspace):
    inv_dir = workspace / "🌀investigacion"
    inv_dir.mkdir(exist_ok=True)
    return _make_project(inv_dir, "🌀paper-neutrinos")


# ══════════════════════════════════════════════════════════════════════════════
# Helpers de fecha / ISO week
# ══════════════════════════════════════════════════════════════════════════════

class TestDateHelpers:
    def test_iso_week_label(self):
        from core.focus import _iso_week_label
        # 2026-05-18 is a Monday in W21.
        assert _iso_week_label(date(2026, 5, 18)) == "2026-W21"
        # 2026-01-05 is a Monday in W02.
        assert _iso_week_label(date(2026, 1, 5)) == "2026-W02"

    def test_week_bounds_monday_to_sunday(self):
        from core.focus import _week_bounds
        mon, sun = _week_bounds(date(2026, 5, 21))  # Thursday
        assert mon == date(2026, 5, 18)
        assert sun == date(2026, 5, 24)


# ══════════════════════════════════════════════════════════════════════════════
# Template parser / formatter
# ══════════════════════════════════════════════════════════════════════════════

class TestTemplate:
    def test_parse_minimal(self):
        from core.focus import _parse_template
        text = (
            "## Carriles\n"
            "- ⚓ Anchor: 2 proyectos × 2 bloques\n"
            "- 🔥 Push: 1-2 proyectos × 1 bloque\n"
            "- 🌿 Joy: 0-1 proyectos × 1 bloque\n"
            "## Bloque\n"
            "- Duración: 90 min\n"
            "## Theme days\n"
            "- Lunes: research\n"
        )
        t = _parse_template(text)
        assert t["projects_per_rail"]["anchor"] == (2, 2)
        assert t["projects_per_rail"]["push"] == (1, 2)
        assert t["projects_per_rail"]["joy"] == (0, 1)
        assert t["blocks_per_project"] == {"anchor": 2, "push": 1, "joy": 1}
        assert t["block_duration"] == 90
        assert t["theme_days"]["mon"] == "research"

    def test_round_trip(self):
        from core.focus import _parse_template, _format_template
        original = {
            "projects_per_rail": {"anchor": (2, 2), "push": (1, 2), "joy": (0, 1)},
            "blocks_per_project": {"anchor": 2, "push": 1, "joy": 1},
            "block_duration": 90,
            "theme_days": {"mon": "research", "tue": "research",
                           "wed": "teaching", "thu": "gestion", "fri": "light"},
        }
        text = _format_template(original)
        parsed = _parse_template(text)
        assert parsed == original

    def test_parse_missing_rail_raises(self):
        from core.focus import _parse_template
        text = (
            "- ⚓ Anchor: 2 proyectos × 2 bloques\n"
            "- 🔥 Push: 1 proyectos × 1 bloque\n"
            "- Duración: 90 min\n"
        )
        with pytest.raises(ValueError, match="Joy"):
            _parse_template(text)

    def test_parse_missing_duration_raises(self):
        from core.focus import _parse_template
        text = (
            "- ⚓ Anchor: 2 proyectos × 2 bloques\n"
            "- 🔥 Push: 1 proyectos × 1 bloque\n"
            "- 🌿 Joy: 0 proyectos × 1 bloque\n"
        )
        with pytest.raises(ValueError, match="Duración"):
            _parse_template(text)

    def test_bootstrap_copies_factory(self, workspace, mission, monkeypatch, tmp_path):
        """The factory file in 📐templates/ gets materialised in mission/notes/."""
        from core.focus import _bootstrap_template_from_factory
        # Patch TEMPLATES_DIR to a sandbox factory.
        fake_templates = tmp_path / "fake_templates"
        fake_templates.mkdir()
        factory = fake_templates / "focus-template.md"
        factory.write_text(
            "# Focus · plantilla\n"
            "## Carriles\n"
            "- ⚓ Anchor: 1 proyecto × 1 bloque\n"
            "- 🔥 Push: 1 proyecto × 1 bloque\n"
            "- 🌿 Joy: 1 proyecto × 1 bloque\n"
            "## Bloque\n"
            "- Duración: 60 min\n"
            "## Theme days\n"
            "- Lunes: research\n"
        )
        monkeypatch.setattr("core.focus.template.TEMPLATES_DIR", fake_templates)
        t = _bootstrap_template_from_factory(mission)
        assert t["block_duration"] == 60
        assert (mission / "notes" / "focus-template.md").exists()


# ══════════════════════════════════════════════════════════════════════════════
# Parser del fichero semanal + contador
# ══════════════════════════════════════════════════════════════════════════════

_WEEK_TEXT_SAMPLE = """\
# Focus 2026-W21

- Fechas: 2026-05-18 → 2026-05-22
- Status: normal

## Carriles

- ⚓ Anchor: [[paper-neutrinos]]
- 🔥 Push: —
- 🌿 Joy: —

## Bloques

### ⚓ paper-neutrinos
- [orbit:11112222]
- [orbit:33334444]

## Contador (autogenerado)

- ⚓ anchor: 0/2
- 🔥 push: — (sin bloques)
- 🌿 joy: — (sin bloques)

## Retrospectiva

(test)
"""


class TestWeekFileParser:
    def test_parse_status_and_blocks(self):
        from core.focus import _parse_week_file
        parsed = _parse_week_file(_WEEK_TEXT_SAMPLE)
        assert parsed["status"] == "normal"
        assert parsed["blocks_by_rail"]["anchor"] == ["11112222", "33334444"]
        assert parsed["blocks_by_rail"]["push"] == []
        assert parsed["blocks_by_rail"]["joy"] == []

    def test_parse_detailed_keeps_project(self):
        from core.focus import _parse_week_blocks_detailed
        out = _parse_week_blocks_detailed(_WEEK_TEXT_SAMPLE)
        assert out == [("anchor", "paper-neutrinos", "11112222"),
                       ("anchor", "paper-neutrinos", "33334444")]


class TestCounter:
    def _week_file_with(self, path: Path, ids_status: dict[str, str],
                        status: str = "normal") -> Path:
        lines = [
            "# Focus 2026-W21", "",
            "- Fechas: 2026-05-18 → 2026-05-22",
            f"- Status: {status}", "",
            "## Carriles", "",
            "- ⚓ Anchor: [[paper-neutrinos]]",
            "- 🔥 Push: —", "- 🌿 Joy: —", "",
            "## Bloques", "",
            "### ⚓ paper-neutrinos",
        ]
        for oid in ids_status:
            lines.append(f"- [orbit:{oid}]")
        lines += ["", "## Contador (autogenerado)", "",
                  "- (regenérame)", "", "## Retrospectiva", ""]
        path.write_text("\n".join(lines))
        return path

    def test_counter_done_pending_mix(self, workspace, mission, monkeypatch,
                                       tmp_path):
        """Counter sums only `done` status, looking up tasks by orbit_id."""
        from core.focus import _regenerate_counter
        from core import api
        # Create 3 blocks in mission/agenda.md with known ids.
        api.add_task(project="mission", text="block A",
                     date="2026-05-18", time="09:00-10:30",
                     orbit_id="aaaaaaaa")
        api.add_task(project="mission", text="block B",
                     date="2026-05-19", time="09:00-10:30",
                     orbit_id="bbbbbbbb")
        api.add_task(project="mission", text="block C",
                     date="2026-05-20", time="09:00-10:30",
                     orbit_id="cccccccc")
        # Mark "aaaaaaaa" as done via direct edit.
        agp = _agenda_path(mission)
        agp.write_text(agp.read_text().replace(
            "[ ] ✏️ block A", "[x] ✏️ block A"))
        # Week file referencing all three.
        week_file = mission / "notes" / "2026-W21-focus.md"
        week_file.parent.mkdir(exist_ok=True)
        self._week_file_with(week_file, {"aaaaaaaa": "", "bbbbbbbb": "",
                                          "cccccccc": ""})
        done, total = _regenerate_counter(week_file, mission)
        assert (done, total) == (1, 3)
        text = week_file.read_text()
        assert "⚓ anchor: 1/3" in text

    def test_counter_especial_shows_dash(self, workspace, mission, tmp_path):
        from core.focus import _regenerate_counter
        from core import api
        api.add_task(project="mission", text="block A",
                     date="2026-05-18", time="09:00-10:30",
                     orbit_id="aaaaaaaa")
        week_file = mission / "notes" / "2026-W21-focus.md"
        week_file.parent.mkdir(exist_ok=True)
        self._week_file_with(week_file, {"aaaaaaaa": ""}, status="especial")
        _regenerate_counter(week_file, mission)
        text = week_file.read_text()
        assert "⚓ anchor: — (0/1 bloques)" in text

    def test_counter_robust_to_title_edit(self, workspace, mission):
        """Counter uses orbit_id, not wikilink — edit doesn't break tracking."""
        from core.focus import _regenerate_counter
        from core import api
        api.add_task(project="mission", text="⚓ [[paper-neutrinos]] · focus W21",
                     date="2026-05-18", time="09:00-10:30",
                     orbit_id="aaaaaaaa")
        agp = _agenda_path(mission)
        # User mangles the title (drops the wikilink) but keeps the id.
        new = agp.read_text().replace(
            "⚓ [[paper-neutrinos]] · focus W21",
            "rebautizada sin wikilink ni emoji")
        # Also mark done.
        new = new.replace("[ ] ✏️ rebautizada", "[x] ✏️ rebautizada")
        agp.write_text(new)
        # Week file still has the id under anchor section.
        week_file = mission / "notes" / "2026-W21-focus.md"
        week_file.parent.mkdir(exist_ok=True)
        TestCounter()._week_file_with(week_file, {"aaaaaaaa": ""})
        done, total = _regenerate_counter(week_file, mission)
        assert (done, total) == (1, 1)


# ══════════════════════════════════════════════════════════════════════════════
# Modos: libre, plantilla, repetir
# ══════════════════════════════════════════════════════════════════════════════

def _write_template_file(mission_dir: Path, *,
                          anchor=(2, 2, 2), push=(1, 2, 1), joy=(0, 1, 1),
                          duration=90):
    """anchor / push / joy = (lo, hi, blocks_per_project)."""
    text = (
        "# Focus · plantilla\n\n## Carriles\n\n"
        f"- ⚓ Anchor: {anchor[0]}{'' if anchor[0]==anchor[1] else f'-{anchor[1]}'} proyectos × {anchor[2]} bloques\n"
        f"- 🔥 Push: {push[0]}{'' if push[0]==push[1] else f'-{push[1]}'} proyectos × {push[2]} bloques\n"
        f"- 🌿 Joy: {joy[0]}{'' if joy[0]==joy[1] else f'-{joy[1]}'} proyectos × {joy[2]} bloques\n"
        f"\n## Bloque\n\n- Duración: {duration} min\n\n"
        "## Theme days\n\n"
        "- Lunes: research\n- Martes: research\n- Miércoles: teaching\n"
        "- Jueves: gestion\n- Viernes: light\n"
    )
    notes = mission_dir / "notes"
    notes.mkdir(exist_ok=True)
    (notes / "focus-template.md").write_text(text)


class TestModeLibre:
    def test_creates_blocks_and_week_file(self, workspace, mission,
                                          other_project, monkeypatch):
        """Free mode: ask projects/blocks, write tasks + week file."""
        from core.focus import run_focus_week
        _write_template_file(mission)
        # Stdin: selector=libre (2: no W-1, options=[plantilla, libre]).
        # Anchor: paper-neutrinos, 2 blocks, lun 09:00, mar 09:00. Then enter
        # to terminate anchor, enter for push, enter for joy.
        _feed_inputs(monkeypatch, [
            "2",            # select libre
            "paper-neutrinos",
            "",             # default 2 blocks
            "lun", "09:00",
            "mar", "09:00",
            "",             # no more anchor
            "",             # no push
            "",             # no joy
        ])
        rc = run_focus_week()
        assert rc == 0
        # Two tasks created in mission/agenda.md.
        ag_text = _agenda_path(mission).read_text()
        assert ag_text.count("<!-- orbit:") == 2
        # El task title incluye el emoji del proyecto para coherencia visual
        # con el dashboard ("[🌀paper-neutrinos]" vs "[paper-neutrinos]").
        assert ag_text.count("[[🌀paper-neutrinos]]") == 2
        # Week file written with rail bucket and IDs.
        week_label_today = date.today().isocalendar()
        week_file = (mission / "notes" /
                     f"{week_label_today.year}-W{week_label_today.week:02d}-focus.md")
        assert week_file.exists()
        text = week_file.read_text()
        assert "### ⚓ paper-neutrinos" in text
        # Counter shows 0/2 anchor (no tasks done yet).
        assert "⚓ anchor: 0/2" in text


class TestModePlantilla:
    def test_uses_w_minus_1_as_default(self, workspace, mission,
                                       other_project, monkeypatch):
        """Plantilla mode pre-fills with W-1 projects."""
        from core.focus import run_focus_week, _iso_week_label
        _write_template_file(mission, anchor=(1, 1, 1))
        # Make today's week have a W-1: write 2026-W(today-1) file with
        # paper-neutrinos under anchor.
        today = date.today()
        prev = today - timedelta(days=7)
        prev_label = _iso_week_label(prev)
        notes = mission / "notes"
        notes.mkdir(exist_ok=True)
        (notes / f"{prev_label}-focus.md").write_text(
            "# Focus prev\n\n- Status: normal\n\n## Carriles\n\n"
            "- ⚓ Anchor: [[paper-neutrinos]]\n- 🔥 Push: —\n- 🌿 Joy: —\n\n"
            "## Bloques\n\n### ⚓ paper-neutrinos\n- [orbit:aaaaaaaa]\n\n"
            "## Contador\n\n## Retrospectiva\n"
        )
        # Selector now offers [repetir, plantilla, libre]. Pick plantilla (2).
        # Anchor #1 default = paper-neutrinos → Enter.
        # Block 1/1: lun 09:00. Push 0 projects, Joy 0 projects.
        _feed_inputs(monkeypatch, [
            "2",            # plantilla
            "",             # accept default project paper-neutrinos
            "lun", "09:00",
            "0",            # 0 push projects
            "0",            # 0 joy projects
        ])
        rc = run_focus_week()
        assert rc == 0
        # 1 anchor block created (emoji prefix por coherencia visual).
        ag_text = _agenda_path(mission).read_text()
        assert ag_text.count("[[🌀paper-neutrinos]]") == 1


class TestModeRepetir:
    def test_clones_w_minus_1_plus_7_days(self, workspace, mission,
                                          other_project, monkeypatch):
        """Repetir: each block in W-1 → new block on W with date+7."""
        from core.focus import run_focus_week, _iso_week_label
        from core import api
        _write_template_file(mission)
        today = date.today()
        prev = today - timedelta(days=7)
        # Pick a Monday from the prev week.
        prev_monday = prev - timedelta(days=prev.weekday())
        # Create the W-1 task in mission agenda.
        api.add_task(project="mission",
                     text="⚓ [[paper-neutrinos]] · focus prev",
                     date=prev_monday.isoformat(), time="09:00-10:30",
                     orbit_id="aaaaaaaa")
        # And the W-1 week file referencing that id.
        notes = mission / "notes"
        notes.mkdir(exist_ok=True)
        prev_label = _iso_week_label(prev)
        (notes / f"{prev_label}-focus.md").write_text(
            "# prev\n\n- Status: normal\n\n## Carriles\n\n"
            "- ⚓ Anchor: [[paper-neutrinos]]\n- 🔥 Push: —\n- 🌿 Joy: —\n\n"
            "## Bloques\n\n### ⚓ paper-neutrinos\n- [orbit:aaaaaaaa]\n\n"
            "## Contador\n\n## Retrospectiva\n"
        )
        # Selector: [repetir, plantilla, libre] → 1 (repetir, default).
        # Confirm clone.
        _feed_inputs(monkeypatch, ["1", "y"])
        rc = run_focus_week()
        assert rc == 0
        # New task in agenda on prev_monday + 7.
        ag_text = _agenda_path(mission).read_text()
        new_date = (prev_monday + timedelta(days=7)).isoformat()
        assert new_date in ag_text


class TestF7Menu:
    def test_regenerate_counter_option(self, workspace, mission,
                                       other_project, monkeypatch):
        """F7 menu option 1 regenerates counter and exits."""
        from core.focus import run_focus_week
        _write_template_file(mission)
        # First create a week file via libre.
        _feed_inputs(monkeypatch, [
            "2", "paper-neutrinos", "", "lun", "09:00", "mar", "09:00",
            "", "", "",
        ])
        assert run_focus_week() == 0
        # Now relaunch → menu appears. Select option 1.
        _feed_inputs(monkeypatch, ["1"])
        assert run_focus_week() == 0

    def test_retrospectiva_option_invokes_editor_with_vim_jump(
            self, workspace, mission, other_project, monkeypatch):
        """F7 menu option 5 abre $EDITOR; con vim añade `+/regex` para saltar."""
        from core.focus import run_focus_week
        _write_template_file(mission)
        _feed_inputs(monkeypatch, [
            "2", "paper-neutrinos", "", "lun", "09:00", "mar", "09:00",
            "", "", "",
        ])
        assert run_focus_week() == 0
        # Captura el comando que se le pasa a os.system.
        captured = {}
        def _fake_system(cmd):
            captured["cmd"] = cmd
            return 0
        monkeypatch.setattr("os.system", _fake_system)
        monkeypatch.setenv("EDITOR", "vim")
        _feed_inputs(monkeypatch, ["5"])
        assert run_focus_week() == 0
        assert "vim" in captured["cmd"]
        assert "+/^## Retrospectiva" in captured["cmd"]
        assert "2026-W" in captured["cmd"]  # path del fichero semanal

    def test_retrospectiva_option_other_editor_no_jump(
            self, workspace, mission, other_project, monkeypatch, capsys):
        """Editor distinto de vi/vim/nvim: abre sin flag de salto + hint."""
        from core.focus import run_focus_week
        _write_template_file(mission)
        _feed_inputs(monkeypatch, [
            "2", "paper-neutrinos", "", "lun", "09:00", "mar", "09:00",
            "", "", "",
        ])
        assert run_focus_week() == 0
        captured = {}
        monkeypatch.setattr("os.system", lambda cmd: captured.setdefault("cmd", cmd) or 0)
        monkeypatch.setenv("EDITOR", "nano")
        _feed_inputs(monkeypatch, ["5"])
        assert run_focus_week() == 0
        assert "nano" in captured["cmd"]
        assert "+/" not in captured["cmd"]
        assert "## Retrospectiva" in capsys.readouterr().out

    def test_add_blocks_option_preserves_existing(self, workspace, mission,
                                                  other_project, monkeypatch):
        """F7 menu option 3 extends an existing week file without duplicating."""
        from core.focus import run_focus_week
        _write_template_file(mission)
        # First W21 via libre.
        _feed_inputs(monkeypatch, [
            "2", "paper-neutrinos", "", "lun", "09:00", "mar", "09:00",
            "", "", "",
        ])
        assert run_focus_week() == 0
        agenda_before = _agenda_path(mission).read_text()
        ids_before = agenda_before.count("<!-- orbit:")
        # Now option 3 (add): add one more anchor block on wednesday.
        _feed_inputs(monkeypatch, [
            "3",  # menu option add
            "paper-neutrinos",  # rail anchor: add another block
            "1",                # 1 block
            "mie", "09:00",
            "",                 # no more anchor
            "",                 # no push
            "",                 # no joy
        ])
        assert run_focus_week() == 0
        agenda_after = _agenda_path(mission).read_text()
        ids_after = agenda_after.count("<!-- orbit:")
        assert ids_after == ids_before + 1


    def test_add_blocks_option_keeps_retro_and_symbols(self, workspace, mission,
                                                       other_project, monkeypatch):
        """Opción 3 no reescribe la hoja: retrospectiva y fechas intactas."""
        from core.focus import run_focus_week, _week_file_path
        _write_template_file(mission)
        _feed_inputs(monkeypatch, [
            "2", "paper-neutrinos", "1", "lun", "09:00", "", "", "",
        ])
        assert run_focus_week() == 0
        wf = _week_file_path(mission, date.today())
        from core import api
        from core.focus import _parse_block_states
        (oid,) = _parse_block_states(wf.read_text())
        api.complete_task(project="mission", orbit_id=oid)   # hook F3 fecha
        stamp = f"- ✅ {date.today().strftime('%m-%d')} [orbit:"
        text = wf.read_text()
        assert stamp in text
        text += "Mi retrospectiva a mano.\n"
        wf.write_text(text)
        _feed_inputs(monkeypatch, [
            "3",
            "paper-neutrinos", "1", "mie", "09:00", "",   # anchor: +1
            "paper-neutrinos", "1", "jue", "09:00", "",   # push: sección nueva
            "",
        ])
        assert run_focus_week() == 0
        out = wf.read_text()
        assert "Mi retrospectiva a mano." in out
        assert out.count(stamp) == 1
        assert out.count("- ⬜ [orbit:") == 2
        assert "### 🔥 paper-neutrinos" in out
        assert "- 🔥 Push: [[paper-neutrinos]]" in out
        from core.focus import _parse_week_file
        rails = _parse_week_file(out)["blocks_by_rail"]
        assert (len(rails["anchor"]), len(rails["push"])) == (2, 1)

    def test_append_blocks_unit(self, tmp_path):
        from core.focus import _append_blocks_to_week_file
        wf = tmp_path / "w.md"
        wf.write_text("# Focus\n\n## Carriles\n\n- ⚓ Anchor: [[a]]\n"
                      "- 🔥 Push: —\n- 🌿 Joy: —\n\n## Bloques\n\n"
                      "### ⚓ a\n- ✅ 10-01 [orbit:aaaaaaaa]\n\n"
                      "## Contador (autogenerado)\n\n## Retrospectiva\n\nTexto\n")
        _append_blocks_to_week_file(
            wf, {"anchor": ["a"], "push": ["b"]},
            {"anchor": [("a", "bbbbbbbb")], "push": [("b", "cccccccc")]})
        out = wf.read_text()
        assert ("### ⚓ a\n- ✅ 10-01 [orbit:aaaaaaaa]\n- ⬜ [orbit:bbbbbbbb]\n\n"
                "### 🔥 b\n- ⬜ [orbit:cccccccc]\n\n## Contador") in out
        assert "- 🔥 Push: [[b]]" in out
        assert out.endswith("Texto\n")


class TestRetrospectivaGuide:
    def test_new_week_file_has_guiding_questions(self, workspace, mission,
                                                  other_project, monkeypatch):
        """El fichero recién creado lleva las 3 preguntas guía en comentario HTML."""
        from core.focus import run_focus_week
        _write_template_file(mission)
        _feed_inputs(monkeypatch, [
            "2", "paper-neutrinos", "", "lun", "09:00", "mar", "09:00",
            "", "", "",
        ])
        assert run_focus_week() == 0
        # Localiza el fichero semanal — patrón YYYY-WNN-focus.md.
        week_files = list((mission / "notes").glob("*-W*-focus.md"))
        assert len(week_files) == 1
        text = week_files[0].read_text()
        assert "## Retrospectiva" in text
        assert "<!--" in text and "-->" in text
        assert "¿Qué sostuvo la semana?" in text
        assert "¿Qué cedió y por qué?" in text
        assert "¿Qué pruebo distinto la W siguiente?" in text


class TestEdgeCases:
    def test_no_mission_returns_error(self, workspace):
        """No mission project in workspace → error."""
        from core.focus import run_focus_week
        assert run_focus_week() == 1

    def test_no_other_projects_libre_aborts(self, workspace, mission, monkeypatch):
        """Mission exists but no other projects → libre aborts."""
        from core.focus import run_focus_week
        _write_template_file(mission)
        # Selector goes directly to libre (only option besides plantilla).
        _feed_inputs(monkeypatch, ["2"])  # libre
        rc = run_focus_week()
        assert rc == 1


# ══════════════════════════════════════════════════════════════════════════════
# Vista anual (focus year)
# ══════════════════════════════════════════════════════════════════════════════

def _write_week_file_raw(mission_dir: Path, week_label: str,
                          blocks: list[tuple[str, str, str]],
                          status: str = "normal") -> Path:
    """Write a minimal week file with the given (rail, project, orbit_id) blocks."""
    lines = [f"# Focus {week_label}", "",
             "- Fechas: …",
             f"- Status: {status}", "",
             "## Carriles", "",
             "- ⚓ Anchor: —", "- 🔥 Push: —", "- 🌿 Joy: —", "",
             "## Bloques", ""]
    rail_emoji = {"anchor": "⚓", "push": "🔥", "joy": "🌿"}
    grouped: dict[tuple[str, str], list[str]] = {}
    order: list[tuple[str, str]] = []
    for rail, proj, oid in blocks:
        key = (rail, proj)
        if key not in grouped:
            grouped[key] = []
            order.append(key)
        grouped[key].append(oid)
    for rail, proj in order:
        lines.append(f"### {rail_emoji[rail]} {proj}")
        for oid in grouped[(rail, proj)]:
            lines.append(f"- [orbit:{oid}]")
        lines.append("")
    lines += ["## Contador (autogenerado)", "", "## Retrospectiva", ""]
    path = mission_dir / "notes" / f"{week_label}-focus.md"
    path.parent.mkdir(exist_ok=True)
    path.write_text("\n".join(lines))
    return path


class TestWeeksInIsoYear:
    def test_short_year(self):
        from core.focus import _weeks_in_iso_year
        # 2025 has 52 ISO weeks.
        assert _weeks_in_iso_year(2025) == 52

    def test_long_year(self):
        from core.focus import _weeks_in_iso_year
        # 2026 has 53 ISO weeks (starts Mon Dec 29 2025; ends Sun Jan 3 2027).
        assert _weeks_in_iso_year(2026) == 53


class TestCollectYear:
    def test_empty_year_returns_all_weeks_blank(self, workspace, mission):
        from core.focus import _collect_year, _weeks_in_iso_year
        rows = _collect_year(mission, 2026)
        assert len(rows) == _weeks_in_iso_year(2026)
        assert all(r["status"] == "—" for r in rows)
        assert all(r["has_file"] is False for r in rows)
        assert all(r["rails"]["anchor"] == [] for r in rows)
        # First and last labels are well-formed.
        assert rows[0]["week_label"] == "2026-W01"
        assert rows[-1]["week_label"] == f"2026-W{_weeks_in_iso_year(2026):02d}"

    def test_aggregates_done_per_orbit_id(self, workspace, mission):
        from core.focus import _collect_year
        from core import api
        # 3 blocks: 2 done, 1 pending.
        api.add_task(project="mission", text="A",
                     date="2026-05-18", time="09:00-10:30", orbit_id="aaaaaaaa")
        api.add_task(project="mission", text="B",
                     date="2026-05-19", time="09:00-10:30", orbit_id="bbbbbbbb")
        api.add_task(project="mission", text="C",
                     date="2026-05-20", time="09:00-10:30", orbit_id="cccccccc")
        # Mark A and C as done.
        agp = _agenda_path(mission)
        txt = agp.read_text()
        txt = txt.replace("[ ] ✏️ A ", "[x] ✏️ A ")
        txt = txt.replace("[ ] ✏️ C ", "[x] ✏️ C ")
        agp.write_text(txt)
        _write_week_file_raw(mission, "2026-W21", [
            ("anchor", "paper-neutrinos", "aaaaaaaa"),
            ("anchor", "paper-neutrinos", "bbbbbbbb"),
            ("push",   "propuesta-itaca", "cccccccc"),
        ])
        rows = _collect_year(mission, 2026)
        w21 = next(r for r in rows if r["week_num"] == 21)
        assert w21["has_file"] is True
        assert w21["status"] == "normal"
        assert w21["rails"]["anchor"] == [("paper-neutrinos", [True, False])]
        assert w21["rails"]["push"] == [("propuesta-itaca", [True])]
        assert w21["rails"]["joy"] == []

    def test_especial_status_propagates(self, workspace, mission):
        from core.focus import _collect_year
        _write_week_file_raw(mission, "2026-W23", [], status="especial")
        rows = _collect_year(mission, 2026)
        w23 = next(r for r in rows if r["week_num"] == 23)
        assert w23["status"] == "especial"
        assert w23["has_file"] is True

    def test_push_two_projects_preserves_order(self, workspace, mission):
        from core.focus import _collect_year
        from core import api
        api.add_task(project="mission", text="A",
                     date="2026-05-18", time="09:00-10:30", orbit_id="11111111")
        api.add_task(project="mission", text="B",
                     date="2026-05-19", time="09:00-10:30", orbit_id="22222222")
        _write_week_file_raw(mission, "2026-W21", [
            ("push", "proj-a", "11111111"),
            ("push", "proj-b", "22222222"),
        ])
        rows = _collect_year(mission, 2026)
        w21 = next(r for r in rows if r["week_num"] == 21)
        assert [p for p, _ in w21["rails"]["push"]] == ["proj-a", "proj-b"]

    def test_other_years_ignored(self, workspace, mission):
        """Files from another year shouldn't bleed into the requested year."""
        from core.focus import _collect_year
        _write_week_file_raw(mission, "2025-W30", [])
        rows = _collect_year(mission, 2026)
        # No week in 2026 should be marked as has_file.
        assert all(r["has_file"] is False for r in rows)


class TestRenderRailCell:
    def test_empty_rail(self):
        from core.focus import _render_rail_cell
        assert _render_rail_cell([]) == "—"

    def test_single_project_all_done(self):
        from core.focus import _render_rail_cell
        assert _render_rail_cell([("paper", [True, True])]) == "[[paper]] 🍅🍅"

    def test_single_project_mix(self):
        from core.focus import _render_rail_cell
        assert _render_rail_cell([("paper", [True, False])]) == "[[paper]] 🍅❌"

    def test_multiple_projects_br_joined(self):
        from core.focus import _render_rail_cell
        out = _render_rail_cell([("a", [True]), ("b", [False, False])])
        assert out == "[[a]] 🍅<br>[[b]] ❌❌"


class TestFormatYearFile:
    def _blank_rows(self, year: int, n: int):
        from core.focus import _RAILS
        return [{
            "week_label": f"{year}-W{i:02d}",
            "week_num":   i,
            "status":     "—",
            "has_file":   False,
            "rails":      {r: [] for r in _RAILS},
        } for i in range(1, n + 1)]

    def test_empty_year_table_and_totals(self):
        from core.focus import _format_year_file
        rows = self._blank_rows(2025, 52)
        out = _format_year_file(rows, 2025)
        assert "# Focus · año 2025" in out
        assert "| Semana | Fechas | Status | Anchor | Push | Joy |" in out
        # All 52 weeks have a data row. Without files they start with `| WNN`
        # (no wikilink fantasma) and have 4 em-dashes (status + 3 rails);
        # the Fechas column carries actual dates, not an em-dash.
        data_rows = [ln for ln in out.splitlines()
                     if ln.startswith("| W")
                     and not ln.startswith("| Week")
                     and "Semana" not in ln]
        assert len(data_rows) == 52
        assert all(ln.count("| —") == 4 for ln in data_rows)
        # Totals zero with em-dash percentage.
        assert "⚓ anchor: 0/0 🍅 (—)" in out

    def test_normal_week_renders_tomatoes(self):
        from core.focus import _format_year_file
        rows = self._blank_rows(2026, 53)
        rows[20] = {
            "week_label": "2026-W21",
            "week_num":   21,
            "status":     "normal",
            "has_file":   True,
            "rails": {
                "anchor": [("paper-neutrinos", [True, True])],
                "push":   [("propuesta-itaca", [True, False])],
                "joy":    [],
            },
        }
        out = _format_year_file(rows, 2026)
        assert "[[2026-W21-focus\\|W21]]" in out
        assert "🟢" in out
        assert "[[paper-neutrinos]] 🍅🍅" in out
        assert "[[propuesta-itaca]] 🍅❌" in out
        # Totals: 2 anchor done / 2 total; 1 push done / 2 total.
        assert "⚓ anchor: 2/2 🍅 (100%)" in out
        assert "🔥 push: 1/2 🍅 (50%)" in out

    def test_especial_week_status_icon_and_excluded_from_totals(self):
        from core.focus import _format_year_file
        rows = self._blank_rows(2026, 53)
        rows[22] = {
            "week_label": "2026-W23",
            "week_num":   23,
            "status":     "especial",
            "has_file":   True,
            "rails": {
                "anchor": [("congreso", [True])],
                "push":   [],
                "joy":    [],
            },
        }
        out = _format_year_file(rows, 2026)
        assert "🟡" in out
        # Block in especial week renders (truth-fidelity).
        assert "[[congreso]] 🍅" in out
        # But it's excluded from totals → still 0/0.
        assert "⚓ anchor: 0/0 🍅 (—)" in out

    def test_push_two_projects_rendered_with_br(self):
        from core.focus import _format_year_file
        rows = self._blank_rows(2026, 53)
        rows[20] = {
            "week_label": "2026-W21",
            "week_num":   21,
            "status":     "normal",
            "has_file":   True,
            "rails": {
                "anchor": [],
                "push":   [("proj-a", [True]), ("proj-b", [False])],
                "joy":    [],
            },
        }
        out = _format_year_file(rows, 2026)
        assert "[[proj-a]] 🍅<br>[[proj-b]] ❌" in out

    def test_any_rail_supports_n_projects(self):
        """Anchor/push/joy admite N proyectos libremente — no hay tope por carril."""
        from core.focus import _format_year_file
        rows = self._blank_rows(2026, 53)
        rows[20] = {
            "week_label": "2026-W21",
            "week_num":   21,
            "status":     "normal",
            "has_file":   True,
            "rails": {
                "anchor": [("a1", [True, True]), ("a2", [True]),
                           ("a3", [False])],
                "push":   [],
                "joy":    [("j1", [True]), ("j2", [False])],
            },
        }
        out = _format_year_file(rows, 2026)
        assert "[[a1]] 🍅🍅<br>[[a2]] 🍅<br>[[a3]] ❌" in out
        assert "[[j1]] 🍅<br>[[j2]] ❌" in out

    def test_no_wikilink_when_file_missing(self):
        from core.focus import _format_year_file
        rows = self._blank_rows(2026, 53)
        out = _format_year_file(rows, 2026)
        # No wikilink fantasma en ninguna fila.
        assert "[[2026-W" not in out
        # Pero el label plano sí está.
        assert "| W01 " in out
        assert "| W53 " in out

    def test_wikilink_only_when_file_present(self):
        from core.focus import _format_year_file
        rows = self._blank_rows(2026, 53)
        rows[20] = {
            "week_label": "2026-W21",
            "week_num":   21,
            "status":     "normal",
            "has_file":   True,
            "rails": {"anchor": [], "push": [], "joy": []},
        }
        out = _format_year_file(rows, 2026)
        assert "[[2026-W21-focus\\|W21]]" in out
        # Ninguna otra semana lleva wikilink.
        assert out.count("[[2026-W") == 1

    def test_dates_column_present_and_formatted(self):
        from core.focus import _format_year_file
        rows = self._blank_rows(2026, 53)
        out = _format_year_file(rows, 2026)
        # Cabecera nueva.
        assert "| Semana | Fechas | Status | Anchor | Push | Joy |" in out
        # W21/2026 = lun 2026-05-18 → vie 2026-05-22.
        assert "| 05-18/05-24 |" in out

    def test_dates_column_crosses_year_boundary(self):
        """W01 puede empezar en diciembre del año anterior."""
        from core.focus import _format_year_file
        rows = self._blank_rows(2026, 53)
        out = _format_year_file(rows, 2026)
        # ISO 2026-W01: Mon 2025-12-29 → Fri 2026-01-02.
        assert "| W01 | 12-29/01-04 |" in out


class TestRunFocusYear:
    def test_no_mission_returns_error(self, workspace):
        from core.focus import run_focus_year
        assert run_focus_year(year=2026) == 1

    def test_writes_year_file_with_explicit_year(self, workspace, mission):
        from core.focus import run_focus_year
        rc = run_focus_year(year=2026)
        assert rc == 0
        out_path = mission / "notes" / "2026-focus.md"
        assert out_path.exists()
        text = out_path.read_text()
        assert "# Focus · año 2026" in text
        assert "| Semana | Fechas | Status | Anchor | Push | Joy |" in text

    def test_writes_default_year_is_current(self, workspace, mission):
        from core.focus import run_focus_year
        rc = run_focus_year()
        assert rc == 0
        # Current year file should exist.
        yr = date.today().year
        out_path = mission / "notes" / f"{yr}-focus.md"
        assert out_path.exists()

    def test_silent_suppresses_print(self, workspace, mission, capsys):
        from core.focus import run_focus_year
        run_focus_year(year=2026, silent=True)
        captured = capsys.readouterr()
        assert captured.out == ""

    def test_overwrites_existing_file(self, workspace, mission):
        """File is a view: regenerating should fully replace it."""
        from core.focus import run_focus_year
        out_path = mission / "notes" / "2026-focus.md"
        out_path.parent.mkdir(exist_ok=True)
        out_path.write_text("stale content from a previous run")
        run_focus_year(year=2026)
        assert "stale content" not in out_path.read_text()
        assert "# Focus · año 2026" in out_path.read_text()

    def test_reflects_done_blocks(self, workspace, mission):
        from core.focus import run_focus_year
        from core import api
        api.add_task(project="mission", text="A",
                     date="2026-05-18", time="09:00-10:30", orbit_id="aaaaaaaa")
        agp = _agenda_path(mission)
        agp.write_text(agp.read_text().replace("[ ] ✏️ A ", "[x] ✏️ A "))
        _write_week_file_raw(mission, "2026-W21", [
            ("anchor", "paper-neutrinos", "aaaaaaaa"),
        ])
        run_focus_year(year=2026)
        text = (mission / "notes" / "2026-focus.md").read_text()
        # The W21 row has anchor cell with tomato.
        w21_row = next(ln for ln in text.splitlines()
                       if "[[2026-W21-focus" in ln)
        assert "[[paper-neutrinos]] 🍅" in w21_row
        assert "🟢" in w21_row


class TestYearRefreshOnWeekClose:
    def test_menu_regenerate_counter_refreshes_year(self, workspace, mission,
                                                     monkeypatch):
        """Menu option 1 (regenerar contador) on existing week file → year file
        regenerated as side-effect.
        """
        from core import api, focus
        import datetime as _dt
        # Fix today to a Monday in W21/2026 so run_focus_week targets that file.
        fixed_today = _dt.date(2026, 5, 18)

        class _FixedDate(_dt.date):
            @classmethod
            def today(cls):
                return fixed_today
        monkeypatch.setattr(focus.week, "date", _FixedDate)
        _write_template_file(mission)
        api.add_task(project="mission", text="A",
                     date="2026-05-18", time="09:00-10:30", orbit_id="aaaaaaaa")
        _write_week_file_raw(mission, "2026-W21", [
            ("anchor", "paper-neutrinos", "aaaaaaaa"),
        ])
        _feed_inputs(monkeypatch, ["1"])  # regenerar contador
        rc = focus.run_focus_week()
        assert rc == 0
        year_file = mission / "notes" / "2026-focus.md"
        assert year_file.exists()
        assert "# Focus · año 2026" in year_file.read_text()

    def test_refresh_helper_swallows_errors(self, workspace, mission, capsys,
                                              monkeypatch):
        """If run_focus_year raises, the helper prints a warning, no exception."""
        from core import focus
        def _boom(*a, **kw):
            raise RuntimeError("nope")
        monkeypatch.setattr(focus.year, "run_focus_year", _boom)
        # Should not raise.
        focus._refresh_year_silent(mission, 2026)
        captured = capsys.readouterr()
        assert "No se pudo refrescar" in captured.out


# ══════════════════════════════════════════════════════════════════════════════
# F2 (focus week/day): símbolos por bloque + balance en el primer save
# ══════════════════════════════════════════════════════════════════════════════

_W40_MON = date(2026, 9, 28)      # lunes de 2026-W40; domingo = 2026-10-04


def _new_week(mission_dir: Path, monday: date,
              blocks: list[tuple[str, str]]) -> Path:
    """Hoja nueva (formato F2) con bloques anchor ``(proj, oid)``."""
    from core.focus import _write_week_file, _week_file_path
    wf = _week_file_path(mission_dir, monday)
    projs = list(dict.fromkeys(p for p, _ in blocks))
    _write_week_file(wf, monday, "normal", {"anchor": projs},
                     {"anchor": list(blocks)})
    return wf


def _mission_task(oid: str, day: str = "2026-09-29") -> None:
    from core import api
    api.add_task(project="mission", text=f"bloque {oid}", date=day,
                 time="09:00-10:30", orbit_id=oid)


def _mission_status(oid: str) -> str:
    from core.focus import _build_id_status_index, _resolve_mission_dir
    return _build_id_status_index(_resolve_mission_dir()).get(oid)


class TestWeekSheetF2:
    def test_new_sheet_has_open_symbols_and_pending_balance(self, workspace, mission):
        wf = _new_week(mission, _W40_MON, [("paper-neutrinos", "aaaaaaaa")])
        text = wf.read_text()
        assert "- Fechas: 2026-09-28 → 2026-10-04" in text
        assert "- Balance: pendiente" in text
        assert "- ⬜ [orbit:aaaaaaaa]" in text

    def test_counter_refreshes_symbols_live(self, workspace, mission):
        from core import api
        from core.focus import _regenerate_counter
        _mission_task("aaaaaaaa")
        _mission_task("bbbbbbbb")
        api.complete_task(project="mission", orbit_id="aaaaaaaa")
        wf = _new_week(mission, _W40_MON, [("p", "aaaaaaaa"), ("p", "bbbbbbbb")])
        assert _regenerate_counter(wf, mission) == (1, 2)
        text = wf.read_text()
        assert "- ✅ [orbit:aaaaaaaa]" in text
        assert "- ⬜ [orbit:bbbbbbbb]" in text

    def test_sync_keeps_date_while_symbol_unchanged(self):
        from core.focus import _sync_block_symbols
        text = "## Bloques\n### ⚓ p\n- ✅ 10-01 [orbit:aaaaaaaa]\n"
        assert "- ✅ 10-01 [orbit:aaaaaaaa]" in _sync_block_symbols(
            text, {"aaaaaaaa": "done"})
        assert "- ⬜ [orbit:aaaaaaaa]" in _sync_block_symbols(
            text, {"aaaaaaaa": "pending"})

    def test_legacy_lines_without_symbol_parse(self):
        from core.focus import _parse_block_states, _parse_week_file
        text = "- Status: normal\n## Bloques\n### ⚓ p\n- [orbit:aaaaaaaa]\n"
        assert _parse_block_states(text) == {"aaaaaaaa": "pending"}
        assert _parse_week_file(text)["blocks_by_rail"]["anchor"] == ["aaaaaaaa"]

    def test_set_balance_line_replaces_or_inserts(self):
        from core.focus import _set_balance_line
        legacy = "# Focus\n\n- Fechas: x\n- Status: normal\n\n## Bloques\n"
        out = _set_balance_line(legacy, "hecho 2026-10-05")
        assert "- Status: normal\n- Balance: hecho 2026-10-05\n" in out
        again = _set_balance_line(out, "hecho 2026-10-06")
        assert again.count("- Balance:") == 1
        assert "- Balance: hecho 2026-10-06" in again


class TestBalance:
    def test_closed_week_balanced_and_open_blocks_dropped(self, workspace, mission):
        from core import api
        from core.focus import run_focus_balance
        _mission_task("aaaaaaaa")
        _mission_task("bbbbbbbb")
        api.complete_task(project="mission", orbit_id="aaaaaaaa")
        wf = _new_week(mission, _W40_MON, [("p", "aaaaaaaa"), ("p", "bbbbbbbb")])

        res = run_focus_balance(today=date(2026, 10, 5), silent=True)

        assert res == [{"week": "2026-W40", "done": 1, "total": 2,
                        "dropped": 1, "legacy": False}]
        assert _mission_status("bbbbbbbb") == "cancelled"
        assert _mission_status("aaaaaaaa") == "done"
        text = wf.read_text()
        assert "- Balance: hecho 2026-10-05" in text
        assert "- ✅ [orbit:aaaaaaaa]" in text
        assert "- ❌ [orbit:bbbbbbbb]" in text
        assert "- ⚓ anchor: 1/2" in text

    def test_balance_is_idempotent(self, workspace, mission):
        from core.focus import run_focus_balance
        _mission_task("aaaaaaaa")
        wf = _new_week(mission, _W40_MON, [("p", "aaaaaaaa")])
        run_focus_balance(today=date(2026, 10, 5), silent=True)
        before = wf.read_text()
        assert run_focus_balance(today=date(2026, 10, 6), silent=True) == []
        assert wf.read_text() == before

    def test_current_week_not_balanced(self, workspace, mission):
        from core.focus import run_focus_balance
        _mission_task("aaaaaaaa")
        wf = _new_week(mission, _W40_MON, [("p", "aaaaaaaa")])
        # Domingo de la propia semana: aún vigente.
        assert run_focus_balance(today=date(2026, 10, 4), silent=True) == []
        assert "- Balance: pendiente" in wf.read_text()
        assert _mission_status("aaaaaaaa") == "pending"

    def test_legacy_sheet_balanced_without_drop(self, workspace, mission):
        from core.focus import run_focus_balance
        _mission_task("aaaaaaaa", day="2026-05-19")
        wf = _write_week_file_raw(mission, "2026-W21",
                                  [("anchor", "p", "aaaaaaaa")])
        res = run_focus_balance(today=date(2026, 10, 5), silent=True)
        assert res[0]["legacy"] is True and res[0]["dropped"] == 0
        assert _mission_status("aaaaaaaa") == "pending"
        text = wf.read_text()
        assert "- Status: normal\n- Balance: hecho 2026-10-05" in text
        assert "- ❌ [orbit:aaaaaaaa]" in text

    def test_missing_block_marked_unknown(self, workspace, mission):
        from core.focus import run_focus_balance
        wf = _new_week(mission, _W40_MON, [("p", "cccccccc")])
        run_focus_balance(today=date(2026, 10, 5), silent=True)
        assert "- ❔ [orbit:cccccccc]" in wf.read_text()

    def test_year_reads_sheet_after_blocks_vanish(self, workspace, mission):
        """Tras el balance la hoja manda: archivar el bloque no borra el ✅."""
        from core import api
        from core.focus import run_focus_balance, _collect_year, _regenerate_counter
        _mission_task("aaaaaaaa")
        api.complete_task(project="mission", orbit_id="aaaaaaaa")
        wf = _new_week(mission, _W40_MON, [("p", "aaaaaaaa")])
        run_focus_balance(today=date(2026, 10, 5), silent=True)
        _agenda_path(mission).write_text("# Agenda\n\n")   # "archivado"
        assert _mission_status("aaaaaaaa") is None
        row = _collect_year(mission, 2026)[39]
        assert row["rails"]["anchor"] == [("p", [True])]
        assert _regenerate_counter(wf, mission) == (1, 1)
        assert "- ✅ [orbit:aaaaaaaa]" in wf.read_text()

    def test_no_mission_is_silent(self, workspace, capsys):
        from core.focus import run_focus_balance
        assert run_focus_balance(today=date(2026, 10, 5)) == []
        assert capsys.readouterr().out == ""

    def test_hook_action_reports_count(self, workspace, mission, monkeypatch):
        from core.focus import _action_focus_balance
        monkeypatch.setattr("core.commit._git_add_all_tracked", lambda: True)
        _mission_task("aaaaaaaa")
        _new_week(mission, date(2026, 1, 5), [("p", "aaaaaaaa")])
        out = _action_focus_balance(None)
        assert out["ok"] is True
        assert out["msg"].startswith("1 ")


# ══════════════════════════════════════════════════════════════════════════════
# F3: hook done/drop → símbolo con fecha en la hoja
# ══════════════════════════════════════════════════════════════════════════════

class _Today(date):
    @classmethod
    def today(cls):
        return date(2026, 10, 1)            # jueves de 2026-W40


@pytest.fixture()
def w40_today(monkeypatch):
    monkeypatch.setattr("core.focus.hook.date", _Today)


class TestFocusHook:
    def test_done_marks_block_with_date(self, workspace, mission, w40_today, capsys):
        from core import api
        _mission_task("aaaaaaaa")
        _mission_task("bbbbbbbb")
        wf = _new_week(mission, _W40_MON, [("p", "aaaaaaaa"), ("p", "bbbbbbbb")])
        api.complete_task(project="mission", orbit_id="aaaaaaaa")
        text = wf.read_text()
        assert "- ✅ 10-01 [orbit:aaaaaaaa]" in text
        assert "- ⬜ [orbit:bbbbbbbb]" in text
        assert "- ⚓ anchor: 1/2" in text
        assert "🎯 Focus 2026-W40: ✅ 10-01" in capsys.readouterr().out

    def test_api_drop_marks_block(self, workspace, mission, w40_today):
        from core import api
        _mission_task("aaaaaaaa")
        wf = _new_week(mission, _W40_MON, [("p", "aaaaaaaa")])
        api.drop_task(project="mission", orbit_id="aaaaaaaa")
        assert "- ❌ 10-01 [orbit:aaaaaaaa]" in wf.read_text()

    def test_cli_drop_marks_block(self, workspace, mission, w40_today):
        from core.agenda.runners import run_task_drop
        _mission_task("aaaaaaaa")
        wf = _new_week(mission, _W40_MON, [("p", "aaaaaaaa")])
        assert run_task_drop("mission", "bloque aaaaaaaa", force=True) == 0
        assert "- ❌ 10-01 [orbit:aaaaaaaa]" in wf.read_text()

    def test_previous_unbalanced_week_marked(self, workspace, mission, monkeypatch):
        """Lunes W41 antes del save: el bloque de W40 se marca con fecha real."""
        from core import api
        class _Mon(date):
            @classmethod
            def today(cls):
                return date(2026, 10, 5)
        monkeypatch.setattr("core.focus.hook.date", _Mon)
        _mission_task("aaaaaaaa")
        wf = _new_week(mission, _W40_MON, [("p", "aaaaaaaa")])
        api.complete_task(project="mission", orbit_id="aaaaaaaa")
        assert "- ✅ 10-05 [orbit:aaaaaaaa]" in wf.read_text()

    def test_balanced_sheet_untouched(self, workspace, mission, w40_today):
        from core import api
        _mission_task("aaaaaaaa")
        wf = _new_week(mission, _W40_MON, [("p", "aaaaaaaa")])
        wf.write_text(wf.read_text().replace("Balance: pendiente",
                                             "Balance: hecho 2026-10-05"))
        before = wf.read_text()
        api.complete_task(project="mission", orbit_id="aaaaaaaa")
        assert wf.read_text() == before

    def test_task_outside_focus_untouched(self, workspace, mission, w40_today, capsys):
        from core import api
        _mission_task("aaaaaaaa")
        _mission_task("dddddddd")
        wf = _new_week(mission, _W40_MON, [("p", "aaaaaaaa")])
        before = wf.read_text()
        api.complete_task(project="mission", orbit_id="dddddddd")
        assert wf.read_text() == before
        assert "Focus" not in capsys.readouterr().out

    def test_hook_never_raises(self, workspace, mission, w40_today, monkeypatch, capsys):
        from core import api
        def _boom(*a, **k):
            raise RuntimeError("roto")
        monkeypatch.setattr("core.focus.hook._mark_in_sheet", _boom)
        _mission_task("aaaaaaaa")
        _new_week(mission, _W40_MON, [("p", "aaaaaaaa")])
        api.complete_task(project="mission", orbit_id="aaaaaaaa")
        assert _mission_status("aaaaaaaa") == "done"
        assert "no se pudo marcar" in capsys.readouterr().out

    def test_balance_keeps_hook_dates(self, workspace, mission, w40_today):
        from core import api
        from core.focus import run_focus_balance
        _mission_task("aaaaaaaa")
        _mission_task("bbbbbbbb")
        wf = _new_week(mission, _W40_MON, [("p", "aaaaaaaa"), ("p", "bbbbbbbb")])
        api.complete_task(project="mission", orbit_id="aaaaaaaa")
        run_focus_balance(today=date(2026, 10, 5), silent=True)
        text = wf.read_text()
        assert "- ✅ 10-01 [orbit:aaaaaaaa]" in text
        # El drop del balance no pasa por el hook: ❌ sin fecha.
        assert "- ❌ [orbit:bbbbbbbb]" in text


# ══════════════════════════════════════════════════════════════════════════════
# F4: focus day — sección ## Días de la hoja semanal
# ══════════════════════════════════════════════════════════════════════════════

_D = date(2026, 10, 1)                     # jueves de 2026-W40


def _proj_task(name: str, text: str, day: str = "2026-10-01", **kw) -> None:
    from core import api
    api.add_task(project=name, text=text, date=day, **kw)


def _status_in(project: str, desc: str) -> dict:
    from core.focus.day import _read_agenda, _local_projects
    p = next(p for p in _local_projects() if p.name == project)
    return next(t for t in _read_agenda(p)["tasks"] if t["desc"] == desc)


class TestFocusDay:
    def test_candidates_today_then_overdue(self, workspace, mission, other_project):
        from core.focus import _collect_candidates
        _proj_task("🌀paper-neutrinos", "vencida", day="2026-09-29")
        _proj_task("🌀paper-neutrinos", "hoy tarde", time="17:00")
        _proj_task("🌀paper-neutrinos", "hoy pronto", time="09:00")
        _proj_task("🌀paper-neutrinos", "mañana", day="2026-10-02")
        descs = [c["desc"] for c in _collect_candidates(_D)]
        assert descs == ["hoy pronto", "hoy tarde", "vencida"]

    def test_creates_minimal_sheet_and_assigns_ids(self, workspace, mission,
                                                   other_project, monkeypatch):
        from core.focus import run_focus_day, _week_file_path, _parse_days
        _proj_task("🌀paper-neutrinos", "Revisar borrador")
        _proj_task("🌀paper-neutrinos", "Enviar informe")
        _feed_inputs(monkeypatch, ["2 1"])
        assert run_focus_day(today=_D) == 0
        wf = _week_file_path(mission, _D)
        text = wf.read_text()
        assert "- Balance: pendiente" in text
        assert "## Bloques" not in text and "## Contador" not in text
        (day,) = _parse_days(text)
        assert day["date"] == _D and not day["balanced"]
        # Respeta el orden en que se eligen.
        assert [i["title"] for i in day["items"]] == ["Enviar informe",
                                                      "Revisar borrador"]
        assert all(i["project"] == "🌀paper-neutrinos" for i in day["items"])
        oid = _status_in("🌀paper-neutrinos", "Revisar borrador")["orbit_id"]
        assert day["items"][1]["oid"] == oid

    def test_max_five_and_plus_project(self, workspace, mission, other_project,
                                       monkeypatch, capsys):
        from core.focus import run_focus_day, _week_file_path, _parse_days
        for i in range(6):
            _proj_task("🌀paper-neutrinos", f"t{i}", day="2026-12-01")
        _feed_inputs(monkeypatch, ["+paper-neutrinos", "1 2 3 4 5 6",
                                   "1 2 3 4 5"])
        assert run_focus_day(today=_D) == 0
        assert "Máximo 5" in capsys.readouterr().out
        (day,) = _parse_days(_week_file_path(mission, _D).read_text())
        assert len(day["items"]) == 5

    def test_add_then_redo(self, workspace, mission, other_project, monkeypatch):
        from core.focus import run_focus_day, _week_file_path, _parse_days
        for d in ("a", "b", "c"):
            _proj_task("🌀paper-neutrinos", d)
        _feed_inputs(monkeypatch, ["1"])
        run_focus_day(today=_D)
        _feed_inputs(monkeypatch, ["1", "1"])          # añadir: la siguiente
        run_focus_day(today=_D)
        wf = _week_file_path(mission, _D)
        (day,) = _parse_days(wf.read_text())
        assert [i["title"] for i in day["items"]] == ["a", "b"]
        _feed_inputs(monkeypatch, ["2", "3"])          # rehacer: solo c
        run_focus_day(today=_D)
        (day,) = _parse_days(wf.read_text())
        assert [i["title"] for i in day["items"]] == ["c"]

    def test_day_goes_into_existing_week_sheet(self, workspace, mission,
                                               other_project, monkeypatch):
        from core.focus import run_focus_day, _parse_week_file
        _mission_task("aaaaaaaa", day="2026-10-01")
        wf = _new_week(mission, _W40_MON, [("p", "aaaaaaaa")])
        _feed_inputs(monkeypatch, ["1"])               # el bloque de hoy
        assert run_focus_day(today=_D) == 0
        text = wf.read_text()
        assert text.index("## Bloques") < text.index("## Días") \
            < text.index("## Contador")
        assert "[orbit:aaaaaaaa] [[☀️mission]] · bloque aaaaaaaa" in text
        assert _parse_week_file(text)["blocks_by_rail"]["anchor"] == ["aaaaaaaa"]

    def test_hook_marks_day_line(self, workspace, mission, other_project,
                                 monkeypatch, w40_today):
        from core import api
        from core.focus import run_focus_day, _week_file_path
        _proj_task("🌀paper-neutrinos", "Revisar")
        _feed_inputs(monkeypatch, ["1"])
        run_focus_day(today=_D)
        api.complete_task(project="🌀paper-neutrinos", desc="Revisar")
        assert "- ✅ 10-01 [orbit:" in _week_file_path(mission, _D).read_text()

    def test_day_balance_next_day(self, workspace, mission, other_project,
                                  monkeypatch, w40_today):
        from core import api
        from core.focus import run_focus_day, run_focus_balance, _week_file_path
        _proj_task("🌀paper-neutrinos", "hecha")
        _proj_task("🌀paper-neutrinos", "pendiente")
        _feed_inputs(monkeypatch, ["1 2"])
        run_focus_day(today=_D)
        api.complete_task(project="🌀paper-neutrinos", desc="hecha")
        assert run_focus_balance(today=_D, silent=True) == []   # mismo día
        res = run_focus_balance(today=date(2026, 10, 2), silent=True)
        assert res == [{"date": _D, "done": 1, "total": 2}]
        text = _week_file_path(mission, _D).read_text()
        assert "### 2026-10-01 · jueves · balance 1/2" in text
        assert "- ✅ 10-01 [orbit:" in text and "- ❌ [orbit:" in text
        # La tarea real sigue abierta: focus day no hace drop.
        assert _status_in("🌀paper-neutrinos", "pendiente")["status"] == "pending"
        assert "- Balance: pendiente" in text               # semana sigue viva
        assert run_focus_balance(today=date(2026, 10, 3), silent=True) == []

    def test_frozen_day_untouched_by_hook(self, workspace, mission, other_project,
                                          monkeypatch):
        from core import api
        from core.focus import run_focus_day, run_focus_balance, _week_file_path
        _proj_task("🌀paper-neutrinos", "tarde")
        _feed_inputs(monkeypatch, ["1"])
        run_focus_day(today=_D)
        run_focus_balance(today=date(2026, 10, 2), silent=True)
        wf = _week_file_path(mission, _D)
        before = wf.read_text()
        class _Fri(date):
            @classmethod
            def today(cls):
                return date(2026, 10, 2)
        monkeypatch.setattr("core.focus.hook.date", _Fri)
        api.complete_task(project="🌀paper-neutrinos", desc="tarde")
        assert wf.read_text() == before

    def test_week_on_day_only_sheet_keeps_days(self, workspace, mission,
                                               other_project, monkeypatch):
        from core.focus import run_focus_day, run_focus_week, _week_file_path
        _write_template_file(mission)
        _proj_task("🌀paper-neutrinos", "Revisar", day=date.today().isoformat())
        _feed_inputs(monkeypatch, ["1"])
        run_focus_day()
        wf = _week_file_path(mission, date.today())
        wf.write_text(wf.read_text() + "Retro a mano.\n")
        _feed_inputs(monkeypatch, ["2", "paper-neutrinos", "1", "lun", "09:00",
                                   "", "", ""])          # plantilla→libre
        assert run_focus_week() == 0
        text = wf.read_text()
        assert "## Bloques" in text and "## Días" in text
        assert "· Revisar" in text and "Retro a mano." in text
        assert text.index("## Días") < text.index("## Contador")


# ══════════════════════════════════════════════════════════════════════════════
# F5: sección 🎯 Focus en la agenda del secretario
# ══════════════════════════════════════════════════════════════════════════════

class TestSecretaryFocus:
    def test_no_sheet_no_section(self, workspace, mission):
        from views.secretary.focus import focus_lines
        assert focus_lines(_D) == []

    def test_week_blocks_live_status(self, workspace, mission, other_project):
        from core import api
        from core.focus import suppressed
        from views.secretary.focus import focus_lines
        _mission_task("aaaaaaaa")
        _mission_task("bbbbbbbb")
        _new_week(mission, _W40_MON, [("paper-neutrinos", "aaaaaaaa"),
                                      ("paper-neutrinos", "bbbbbbbb")])
        with suppressed():                       # como si fuera a mano
            api.complete_task(project="mission", orbit_id="aaaaaaaa")
        out = "\n".join(focus_lines(_D))
        assert out.startswith("## 🎯 Focus")
        assert "**Semana** [2026-W40](../../" in out
        assert "· ✅ 1/2 bloques" in out
        assert "- ⚓ Anchor: [🌀paper-neutrinos](../../" in out
        assert ") ✅⬜" in out
        assert "**Hoy**" not in out

    def test_day_items_read_truth(self, workspace, mission, other_project,
                                  monkeypatch):
        from core import api
        from core.focus import run_focus_day, suppressed
        from views.secretary.focus import focus_lines
        _proj_task("🌀paper-neutrinos", "Revisar")
        _proj_task("🌀paper-neutrinos", "Enviar")
        _feed_inputs(monkeypatch, ["1 2"])
        run_focus_day(today=_D)
        with suppressed():                       # cierre fuera de la CLI
            api.complete_task(project="🌀paper-neutrinos", desc="Revisar")
        out = focus_lines(_D)
        assert "**Semana**" not in "\n".join(out)
        assert any(l.startswith("**Hoy** [2026-W40](") and l.endswith("✅ 1/2")
                   for l in out)
        assert any(l.startswith("- ✅ [🌀paper-neutrinos](") and
                   l.endswith("· Revisar") for l in out)
        assert any(l.startswith("- ⬜ ") and l.endswith("· Enviar") for l in out)
        assert focus_lines(date(2026, 10, 2)) == []     # otro día sin focus

    def test_status_off_hides(self, workspace, mission):
        from views.secretary.focus import focus_lines
        _mission_task("aaaaaaaa")
        wf = _new_week(mission, _W40_MON, [("p", "aaaaaaaa")])
        wf.write_text(wf.read_text().replace("Status: normal", "Status: off"))
        assert focus_lines(_D) == []

    def test_agenda_places_section_before_today(self, workspace, mission,
                                                monkeypatch, tmp_path):
        import views.secretary.agenda as agenda
        _mission_task("aaaaaaaa", day=date.today().isoformat())
        _new_week(mission, date.today(), [("p", "aaaaaaaa")])
        out = tmp_path / "agenda.md"
        agenda.generate(out)
        text = out.read_text()
        assert text.index("## 🎯 Focus") < text.index("## 📅 Hoy")
        assert text.index("> ") < text.index("## 🎯 Focus")

    def test_never_raises(self, workspace, mission, monkeypatch):
        from views.secretary import focus
        def _boom(*a, **k):
            raise RuntimeError("x")
        monkeypatch.setattr(focus, "_focus_lines", _boom)
        assert focus.focus_lines(_D) == []

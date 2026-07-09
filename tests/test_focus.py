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

    def test_week_bounds_monday_to_friday(self):
        from core.focus import _week_bounds
        mon, fri = _week_bounds(date(2026, 5, 21))  # Thursday
        assert mon == date(2026, 5, 18)
        assert fri == date(2026, 5, 22)


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
        monkeypatch.setattr("core.focus.TEMPLATES_DIR", fake_templates)
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
        assert "| 05-18/05-22 |" in out

    def test_dates_column_crosses_year_boundary(self):
        """W01 puede empezar en diciembre del año anterior."""
        from core.focus import _format_year_file
        rows = self._blank_rows(2026, 53)
        out = _format_year_file(rows, 2026)
        # ISO 2026-W01: Mon 2025-12-29 → Fri 2026-01-02.
        assert "| W01 | 12-29/01-02 |" in out


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
        monkeypatch.setattr(focus, "date", _FixedDate)
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
        monkeypatch.setattr(focus, "run_focus_year", _boom)
        # Should not raise.
        focus._refresh_year_silent(mission, 2026)
        captured = capsys.readouterr()
        assert "No se pudo refrescar" in captured.out

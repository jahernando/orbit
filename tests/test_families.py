"""Tests de familias de proyectos (ADR-059): core/families.py, la hoja por
familia del secretario, el agrupado de ⏩ en `agenda.md` y en `day`, y los
callouts en el render."""

import json
from datetime import date, timedelta

import pytest

from core import families as F

TODAY = date.today()
ISO = TODAY.isoformat()
TODAY_KEY = F.DAY_KEYS[TODAY.weekday()]
OTHER_KEY = F.DAY_KEYS[(TODAY.weekday() + 1) % 7]


def _d(n: int) -> str:
    return (TODAY + timedelta(days=n)).isoformat()


FAMILIES = {
    "next": {"emoji": "🔵", "days": [OTHER_KEY],
             "projects": ["next-a", "next-pn24"]},
    "hk":   {"emoji": "🟣", "days": [TODAY_KEY], "projects": ["hk-a"]},
    "ges":  {"emoji": "⚙️", "days": [OTHER_KEY], "types": ["gestion"]},
}


@pytest.fixture
def ws(tmp_path, monkeypatch):
    """🌀 next-a, hk-a, dis-dani · ⚙️ next-pn24, usc-ges."""
    projects = {}
    for emoji, tdir, names in (
            ("🌀", "🌀investigacion", ("next-a", "hk-a", "dis-dani")),
            ("⚙️", "⚙️gestion", ("next-pn24", "usc-ges"))):
        for name in names:
            proj = tmp_path / tdir / f"{emoji}{name}"
            proj.mkdir(parents=True)
            (proj / "project.md").write_text(
                f"# {name}\n- Tipo: x\n- Estado: [auto]\n- Prioridad: media\n")
            (proj / "logbook.md").write_text(f"# Logbook — {name}\n\n")
            (proj / "agenda.md").write_text(f"# Agenda — {name}\n\n")
            projects[name] = proj
    cfg = {"types": {"investigacion": "🌀", "gestion": "⚙️"},
           "families": FAMILIES}
    (tmp_path / "orbit.json").write_text(json.dumps(cfg))
    monkeypatch.setattr("core.config.ORBIT_HOME", tmp_path)
    monkeypatch.setattr("core.config._ORBIT_JSON", tmp_path / "orbit.json")
    monkeypatch.setattr("core.log.PROJECTS_DIR", tmp_path)
    return projects


def _seed(proj, **sections):
    from core.agenda_cmds import _read_agenda, _write_agenda
    data = _read_agenda(proj / "agenda.md")
    for k, v in sections.items():
        data[k] = v
    _write_agenda(proj / "agenda.md", data)


def _fup(desc, n=-1, **kw):
    return {"desc": desc, "status": "pending", "notes": [f"⏩ {_d(n)}"], **kw}


# ── core/families.py ─────────────────────────────────────────────────────────

class TestCore:

    def test_load_in_order(self, ws):
        fams = F.load_families()
        assert [f.name for f in fams] == ["next", "hk", "ges"]
        assert fams[1].days == (TODAY.weekday(),)
        assert fams[1].label == "🟣 hk"

    def test_name_wins_over_type(self, ws):
        # next-pn24 es ⚙️ gestión pero está nombrado en next.
        assert F.family_of(ws["next-pn24"]).name == "next"
        assert F.family_of(ws["usc-ges"]).name == "ges"
        assert F.family_of(ws["hk-a"]).name == "hk"

    def test_without_family(self, ws):
        assert F.family_of(ws["dis-dani"]) is None

    def test_several_days_and_several_families_a_day(self):
        cfg = {"families": {"a": {"days": ["mon", "thu"]},
                            "b": {"days": ["mon"]}}}
        fams = F.load_families(cfg)
        monday = date(2026, 10, 19)
        assert [f.name for f in F.families_on(monday, fams)] == ["a", "b"]
        assert fams[0].days_label == "lunes y jueves"

    def test_group_order_today_first_then_rest_then_none(self, ws):
        order = F.group_order(TODAY, F.load_families())
        assert [f.name if f else None for f in order] == [
            "hk", "next", "ges", None]

    def test_no_families_block(self):
        assert F.load_families({}) == []
        assert F.problems({}) == []

    def test_problems(self, ws):
        cfg = {"types": {"investigacion": "🌀", "gestion": "⚙️"},
               "families": {
                   "a": {"days": ["lun"], "projects": ["next-a", "nope"]},
                   "b": {"days": ["mon"], "projects": ["next-a"],
                         "types": ["gestion", "ocio"]},
                   "c": {"days": ["tue"], "types": ["gestion"]}}}
        msgs = F.problems(cfg)
        assert any("días no válidos" in m for m in msgs)
        assert any("«nope» no existe" in m for m in msgs)
        assert any("«next-a» está en «a» y en «b»" in m for m in msgs)
        assert any("tipo «ocio» no existe" in m for m in msgs)
        assert any("tipo «gestion» está en «b» y en «c»" in m for m in msgs)

    def test_valid_config_has_no_problems(self, ws):
        assert F.problems() == []


# ── Hoja por familia ─────────────────────────────────────────────────────────

class TestFamilyPage:

    def test_page_content_and_folding(self, ws, tmp_path):
        from views.secretary import families as SF
        _seed(ws["hk-a"],
              tasks=[_fup("revisar PMT"),
                     {"desc": "vencida", "date": _d(-3), "status": "pending"},
                     {"desc": "sin fecha", "status": "pending",
                      "notes": [f"⏩ {_d(4)}"]},
                     {"desc": "pronto", "date": _d(5), "status": "pending"}],
              events=[{"desc": "reunión", "date": _d(2), "time": "10:00"}],
              reminders=[{"desc": "recordar", "date": _d(1), "time": "09:00"}])
        out = tmp_path / "out"
        assert SF.generate(out) == 3
        page = (out / "hk.md").read_text()
        assert "# 🟣 hk" in page and "hoy es su día" in page
        # Hoy es su día: ⏩ y ⚠️ abiertos; próximas y sin fecha plegadas.
        assert "> [!warning]+ ⏩ Por triar (1)" in page
        assert "> [!warning]+ ⚠️ Vencidas (1)" in page
        assert "> [!note]- 🗂️ Sin fecha (1)" in page
        assert "> [!note]- 📅 Próximas · 30 días (3)" in page   # pronto, reunión, ⏩
        assert "recordar" not in page                           # sin recordatorios
        assert "⏩" + _d(4)[5:] in page                          # sin fecha con ⏩ futuro
        # Enlaces un nivel más abajo que el secretario.
        assert "](../../../🌀investigacion/🌀hk-a/project.md)" in page
        assert "](../../🌀" not in page
        # Toda línea de un callout lleva su «>» (también el separador de tabla).
        assert "\n|---" not in page

    def test_other_day_folded_and_next_day(self, ws, tmp_path):
        from views.secretary import families as SF
        _seed(ws["next-a"], tasks=[_fup("x")])
        SF.generate(tmp_path / "out")
        page = (tmp_path / "out" / "next.md").read_text()
        assert "> [!warning]- ⏩ Por triar (1)" in page
        assert "próximo:" in page

    def test_type_family_collects_projects(self, ws, tmp_path):
        from views.secretary import families as SF
        _seed(ws["usc-ges"], tasks=[_fup("firma")])
        _seed(ws["next-pn24"], tasks=[_fup("memoria")])
        SF.generate(tmp_path / "out")
        ges = (tmp_path / "out" / "ges.md").read_text()
        assert "firma" in ges and "memoria" not in ges

    def test_removed_family_page_is_deleted(self, ws, tmp_path):
        from views.secretary import families as SF
        out = tmp_path / "out"
        out.mkdir()
        (out / "vieja.md").write_text("x")
        SF.generate(out)
        assert not (out / "vieja.md").exists()


# ── agenda.md ────────────────────────────────────────────────────────────────

class TestAgenda:

    def _agenda(self, tmp_path):
        from views.secretary import agenda as SA
        out = tmp_path / "agenda.md"
        SA.generate(out)
        return out.read_text()

    def test_fups_grouped_by_family(self, ws, tmp_path):
        _seed(ws["hk-a"], tasks=[_fup("hk uno"), _fup("hk dos")])
        _seed(ws["next-a"], tasks=[_fup("next uno")])
        _seed(ws["dis-dani"], tasks=[_fup("dani uno")])
        md = self._agenda(tmp_path)
        assert "> 👥 Familias: 🔵 [next](families/next.md) ⏩1" in md
        assert "🟣 [hk](families/hk.md) ⏩2" in md
        assert "> Hoy es día de 🟣 [hk](families/hk.md): ⏩2" in md
        assert "### ⏩ Por triar (4)" in md
        i_hk = md.index("> [!note]+ 🟣 [hk](families/hk.md) · 2")
        i_next = md.index("> [!note]- 🔵 [next](families/next.md) · 1")
        i_none = md.index("> [!note]- Sin familia · 1")
        assert i_hk < i_next < i_none
        assert "> | ☐ | ⏩ |  |  |  | hk uno |" in md       # filas dentro del callout

    def test_without_families_unchanged(self, ws, tmp_path):
        (tmp_path / "orbit.json").write_text(json.dumps(
            {"types": {"investigacion": "🌀", "gestion": "⚙️"}}))
        _seed(ws["hk-a"], tasks=[_fup("hk uno")])
        md = self._agenda(tmp_path)
        assert "Familias" not in md and "[!note]" not in md
        assert "Por triar (" not in md and "hk uno" in md


# ── day / day fup ────────────────────────────────────────────────────────────

class TestDay:

    def test_decidir_grouped_today_first(self, ws):
        from core import triage as T
        _seed(ws["next-a"], tasks=[_fup("n1", -2)])
        _seed(ws["dis-dani"], tasks=[_fup("d1", -3)])
        _seed(ws["hk-a"], tasks=[_fup("h1", -1)])
        dirs = list(ws.values())
        sections = T.collect(dirs, TODAY, full=False)
        rows = sections[T.DECIDIR]
        assert [r.item["desc"] for r in rows] == ["h1", "n1", "d1"]
        lines = T.format_listing("t", sections, TODAY, show_project=True)
        text = "\n".join(lines)
        assert "· 🟣 hk · hoy (1)" in text
        assert text.index("· 🟣 hk") < text.index("· 🔵 next") < text.index("· sin familia")

    def test_no_families_no_groups(self, ws, tmp_path):
        from core import triage as T
        (tmp_path / "orbit.json").write_text(json.dumps(
            {"types": {"investigacion": "🌀", "gestion": "⚙️"}}))
        _seed(ws["hk-a"], tasks=[_fup("h1")])
        sections = T.collect(list(ws.values()), TODAY, full=False)
        assert all(r.group is None for r in sections[T.DECIDIR])


# ── Render ───────────────────────────────────────────────────────────────────

class TestRender:

    def test_callouts_become_details(self):
        from views.render.render import _md_to_html
        html = _md_to_html("> [!warning]+ ⏩ Por triar (1)\n> | a |\n> |---|\n> | 1 |\n\n"
                           "> [!note]- Sin fecha\n> **x**\n\nfin")
        assert '<details class="callout callout-warning" open><summary>⏩ Por triar (1)</summary>' in html
        assert '<details class="callout callout-note"><summary>Sin fecha</summary>' in html
        assert "<table>" in html and "<strong>x</strong>" in html
        assert "<p>fin</p>" in html

    def test_plain_blockquote_untouched(self):
        from views.render.render import _md_to_html
        assert "<blockquote>" in _md_to_html("> hola")

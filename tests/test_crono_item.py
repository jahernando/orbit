"""Crono como atributo de tarea / hito (F1): ``--crono`` en add/edit, enlace
``[📊](cronos/…)`` al final de la cabecera y porcentaje en las vistas."""

from core import triage as T
from core.agenda.newfmt import format_item_new, parse_item_new
from core.cronograma import crono_mark, crono_rel_path, crono_slug
from tests.test_triage import ws, _seed, _read, TODAY, ISO, _d  # noqa: F401


def _task(**kw):
    base = {"desc": "X", "status": "pending"}
    base.update(kw)
    return base


def _write_crono(proj, rel, done, total):
    path = proj / rel
    path.parent.mkdir(exist_ok=True)
    lines = ["# Cronograma: c", ""]
    for i in range(1, total + 1):
        mark = "x" if i <= done else " "
        lines.append(f"- [{mark}] {i} paso {i}")
    path.write_text("\n".join(lines) + "\n")


# ── Nombre del fichero ──────────────────────────────────────────────────────

class TestSlug:

    def test_strips_diacritics_and_symbols(self):
        assert crono_slug("Revisión: Informe Final") == "revision-informe-final"

    def test_rel_path_from_title(self):
        assert crono_rel_path("Informe final") == "cronos/crono-informe-final.md"

    def test_rel_path_accepts_existing_stem(self):
        assert crono_rel_path("crono-plan-q4") == "cronos/crono-plan-q4.md"
        assert crono_rel_path("crono-plan-q4.md") == "cronos/crono-plan-q4.md"


# ── Gramática: cabecera ─────────────────────────────────────────────────────

class TestGrammar:

    def test_link_written_at_end_after_tags(self):
        item = _task(desc="Informe", crono="cronos/crono-informe.md")
        head = format_item_new("task", item).splitlines()[0]
        assert head == "- [ ] ✏️ Informe #tarea [📊](cronos/crono-informe.md)"

    def test_roundtrip_with_id(self):
        item = _task(desc="Entrega", crono="cronos/crono-e.md", orbit_id="abcd1234")
        head = format_item_new("milestone", item, with_id=True).splitlines()[0]
        kind, back = parse_item_new(head, [])
        assert kind == "milestone"
        assert back["desc"] == "Entrega"
        assert back["crono"] == "cronos/crono-e.md"
        assert back["orbit_id"] == "abcd1234"

    def test_link_tolerated_at_start(self):
        kind, it = parse_item_new("- [ ] ✏️ [📊](cronos/crono-a.md) Informe #tarea", [])
        assert it["desc"] == "Informe" and it["crono"] == "cronos/crono-a.md"

    def test_no_crono_key_without_link(self):
        _, it = parse_item_new("- [ ] ✏️ Informe #tarea", [])
        assert "crono" not in it


# ── CLI: add / edit ─────────────────────────────────────────────────────────

class TestAdd:

    def test_add_creates_crono_from_title(self, ws, capsys):
        from core.agenda_cmds import run_task_add
        assert run_task_add(ws.name, "Informe final", date_val=_d(30), crono="") == 0
        it = _read(ws)["tasks"][-1]
        assert it["crono"] == "cronos/crono-informe-final.md"
        path = ws / it["crono"]
        assert path.exists()
        assert path.read_text().startswith("# Cronograma: Informe final")
        assert "[📊](cronos/crono-informe-final.md)" in (ws / "agenda.md").read_text()
        assert "crono creado" in capsys.readouterr().out

    def test_add_milestone_with_explicit_name(self, ws):
        from core.agenda_cmds import run_ms_add
        assert run_ms_add(ws.name, "Entrega", date_val=_d(30), crono="plan-q4") == 0
        assert _read(ws)["milestones"][-1]["crono"] == "cronos/crono-plan-q4.md"
        assert (ws / "cronos/crono-plan-q4.md").exists()

    def test_add_links_existing_file_untouched(self, ws, capsys):
        from core.agenda_cmds import run_task_add
        _write_crono(ws, "cronos/crono-viejo.md", 1, 2)
        before = (ws / "cronos/crono-viejo.md").read_text()
        assert run_task_add(ws.name, "Algo", crono="viejo") == 0
        assert (ws / "cronos/crono-viejo.md").read_text() == before
        assert "enlazado a crono existente" in capsys.readouterr().out

    def test_add_refuses_crono_owned_by_open_item(self, ws, capsys):
        from core.agenda_cmds import run_task_add
        _seed(ws, tasks=[_task(desc="A", crono="cronos/crono-c.md")])
        assert run_task_add(ws.name, "B", crono="c") == 1
        assert "un solo item" in capsys.readouterr().out
        assert len(_read(ws)["tasks"]) == 1

    def test_add_allows_crono_of_closed_item(self, ws):
        from core.agenda_cmds import run_task_add
        _seed(ws, tasks=[_task(desc="A", status="done", crono="cronos/crono-c.md")])
        assert run_task_add(ws.name, "B", crono="c") == 0

    def test_add_refuses_recurring(self, ws, capsys):
        from core.agenda_cmds import run_task_add
        assert run_task_add(ws.name, "R", date_val=ISO, recur="weekly", crono="") == 1
        assert "recurrente" in capsys.readouterr().out
        assert not (ws / "cronos").exists()

    def test_add_without_crono_unchanged(self, ws):
        from core.agenda_cmds import run_task_add
        assert run_task_add(ws.name, "Normal") == 0
        assert "crono" not in _read(ws)["tasks"][-1]
        assert not (ws / "cronos").exists()


class TestEdit:

    def test_edit_links_existing_item(self, ws):
        from core.agenda_cmds import run_task_edit
        _seed(ws, tasks=[_task(desc="Informe", date=_d(10))])
        assert run_task_edit(ws.name, "Informe", crono="") == 0
        it = _read(ws)["tasks"][-1]
        assert it["crono"] == "cronos/crono-informe.md"
        assert it["date"] == _d(10)
        assert (ws / it["crono"]).exists()

    def test_edit_none_unlinks_and_keeps_file(self, ws, capsys):
        from core.agenda_cmds import run_ms_edit
        _write_crono(ws, "cronos/crono-e.md", 0, 1)
        _seed(ws, milestones=[_task(desc="E", date=_d(5), crono="cronos/crono-e.md")])
        assert run_ms_edit(ws.name, "E", crono="none") == 0
        assert "crono" not in _read(ws)["milestones"][-1]
        assert (ws / "cronos/crono-e.md").exists()
        assert "se conserva" in capsys.readouterr().out

    def test_edit_refuses_second_crono(self, ws, capsys):
        from core.agenda_cmds import run_task_edit
        _seed(ws, tasks=[_task(desc="X", crono="cronos/crono-a.md")])
        assert run_task_edit(ws.name, "X", crono="b") == 1
        assert _read(ws)["tasks"][-1]["crono"] == "cronos/crono-a.md"
        assert "--crono none" in capsys.readouterr().out

    def test_rename_keeps_link(self, ws):
        from core.agenda_cmds import run_task_edit
        _seed(ws, tasks=[_task(desc="X", crono="cronos/crono-a.md")])
        assert run_task_edit(ws.name, "X", new_text="Y") == 0
        it = _read(ws)["tasks"][-1]
        assert it["desc"] == "Y" and it["crono"] == "cronos/crono-a.md"

    def test_edit_refuses_recur_on_crono_item(self, ws, capsys):
        from core.agenda_cmds import run_task_edit
        _seed(ws, tasks=[_task(desc="X", date=ISO, crono="cronos/crono-a.md")])
        assert run_task_edit(ws.name, "X", new_recur="weekly") == 1
        assert "recurrente" in capsys.readouterr().out

    def test_done_keeps_link(self, ws):
        from core.agenda_cmds import run_task_done
        _seed(ws, tasks=[_task(desc="X", crono="cronos/crono-a.md")])
        assert run_task_done(ws.name, "X") == 0
        it = _read(ws)["tasks"][-1]
        assert it["status"] == "done" and it["crono"] == "cronos/crono-a.md"


# ── Vistas: porcentaje ──────────────────────────────────────────────────────

class TestMark:

    def test_terminal_mark(self, ws):
        _write_crono(ws, "cronos/crono-a.md", 3, 8)
        assert crono_mark(ws, {"crono": "cronos/crono-a.md"}) == "📊 37% (3/8)"

    def test_markdown_mark_links(self, ws):
        _write_crono(ws, "cronos/crono-a.md", 1, 4)
        m = crono_mark(ws, {"crono": "cronos/crono-a.md"}, link_prefix="../../p")
        assert m == "[📊 25%](../../p/cronos/crono-a.md)"

    def test_complete_and_missing(self, ws):
        _write_crono(ws, "cronos/crono-a.md", 2, 2)
        assert crono_mark(ws, {"crono": "cronos/crono-a.md"}) == "📊 ✓ 100%"
        assert crono_mark(ws, {"crono": "cronos/crono-nada.md"}) == "📊 ?"
        assert crono_mark(ws, {}) == ""

    def test_day_row_shows_percentage(self, ws):
        _write_crono(ws, "cronos/crono-a.md", 1, 2)
        _seed(ws, tasks=[_task(desc="Informe", date=ISO, crono="cronos/crono-a.md")])
        row = T.Row("task", ws, _read(ws)["tasks"][-1], T.HOY)
        assert "Informe  📊 50% (1/2)" in T.format_row(1, row, TODAY, False)

    def test_secretary_link(self, ws):
        from views.secretary._agenda_table import crono_link_md
        _write_crono(ws, "cronos/crono-a.md", 0, 3)
        link = crono_link_md(ws, {"crono": "cronos/crono-a.md"})
        assert link == f"[📊 0%](../../{ws.parent.name}/{ws.name}/cronos/crono-a.md)"


    def test_agenda_view_lines(self, ws):
        from datetime import date
        from core.agenda_view import (_collect_data, _format_item_line,
                                      _item_to_table_row)
        _write_crono(ws, "cronos/crono-a.md", 1, 2)
        today = date.today().isoformat()
        _seed(ws, milestones=[_task(desc="Hito", date=today,
                                    crono="cronos/crono-a.md")])
        (_pdir, _t, _e, ms), = _collect_data([ws], date.today(), date.today())
        assert "Hito 📊 50% (1/2)" in _format_item_line("milestone", ms[0], "[p]")
        _icon, _time, desc, _p = _item_to_table_row("milestone", ms[0], "[p]")
        assert f"[📊 50%]({ws.parent.name}/{ws.name}/cronos/crono-a.md)" in desc

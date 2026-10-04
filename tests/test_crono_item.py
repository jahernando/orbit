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

    def test_ls_tasks_and_ms_show_link(self, ws, capsys):
        from core.agenda_cmds import run_task_list, run_ms_list
        _write_crono(ws, "cronos/crono-a.md", 1, 2)
        _write_crono(ws, "cronos/crono-b.md", 0, 1)
        _seed(ws, tasks=[_task(desc="T", crono="cronos/crono-a.md")],
              milestones=[_task(desc="M", date=ISO, crono="cronos/crono-b.md")])
        assert run_task_list(projects=[ws.name]) == 0
        assert run_ms_list(projects=[ws.name]) == 0
        out = capsys.readouterr().out
        assert "T [📊 50%](./cronos/crono-a.md)" in out
        assert f"M [📊 0%](./cronos/crono-b.md) ({ISO})" in out

    def test_ls_link_is_clickable_in_terminal(self, ws):
        from core.termlink import Linkifier
        _write_crono(ws, "cronos/crono-a.md", 1, 2)
        lk = Linkifier("ls tasks", projects={ws.name: ws})
        lk.line(f"[{ws.name}]")
        out = lk.line("  [ ] T [📊 50%](./cronos/crono-a.md)")
        assert "\033]8;;file://" in out and "crono-a.md" in out


# ── F2: pasos bajo su item ──────────────────────────────────────────────────

def _write_dated_crono(proj, rel, steps):
    """steps: [(done, título, inicio ISO, duración)]."""
    path = proj / rel
    path.parent.mkdir(exist_ok=True)
    lines = ["# Cronograma: c", ""]
    for i, (done, title, start, dur) in enumerate(steps, 1):
        lines.append(f"- [{'x' if done else ' '}] {i} {title} | {start} | {dur}")
    path.write_text("\n".join(lines) + "\n")


class TestSteps:

    def test_partial_name_adopts_existing(self, ws, capsys):
        from core.agenda_cmds import run_task_add
        _write_crono(ws, "cronos/crono-hk-general.md", 0, 1)
        assert run_task_add(ws.name, "HK", crono="hk") == 0
        assert _read(ws)["tasks"][-1]["crono"] == "cronos/crono-hk-general.md"
        assert not (ws / "cronos/crono-hk.md").exists()
        assert "enlazado a crono existente" in capsys.readouterr().out

    def test_day_surfaces_item_by_overdue_step(self, ws):
        _write_dated_crono(ws, "cronos/crono-a.md", [
            (False, "Intro", _d(-10), "3d"),         # vencido
            (False, "Figuras", _d(-1), "5d"),        # activo hoy
            (False, "Final", _d(20), "3d")])         # futuro
        _seed(ws, tasks=[_task(desc="Informe", date=_d(40),
                               crono="cronos/crono-a.md")])
        sections = T.collect([ws], TODAY, full=False)
        (row,) = sections[T.VENCIDAS]
        assert [s["title"] for s in row.steps] == ["Intro", "Figuras"]
        text = "\n".join(T.format_listing("t", sections, TODAY, False))
        assert "↳ 1 Intro · ⚠️ vencido" in text
        assert "↳ 2 Figuras · hasta" in text
        assert "Final" not in text

    def test_active_step_goes_to_hoy(self, ws):
        _write_dated_crono(ws, "cronos/crono-a.md", [(False, "Figuras", _d(-1), "5d")])
        _seed(ws, milestones=[_task(desc="Entrega", date=_d(40),
                                    crono="cronos/crono-a.md")])
        sections = T.collect([ws], TODAY, full=False)
        assert [r.item["desc"] for r in sections[T.HOY]] == ["Entrega"]

    def test_no_steps_no_surface(self, ws):
        _write_dated_crono(ws, "cronos/crono-a.md", [(False, "Final", _d(20), "3d")])
        _seed(ws, tasks=[_task(desc="Informe", date=_d(40), crono="cronos/crono-a.md")])
        sections = T.collect([ws], TODAY, full=False)
        assert not any(sections.values())

    def test_linked_crono_leaves_separate_block(self, ws):
        _write_dated_crono(ws, "cronos/crono-a.md", [(False, "X", _d(-3), "1d")])
        _write_dated_crono(ws, "cronos/crono-libre.md", [(False, "Y", _d(-3), "1d")])
        _seed(ws, tasks=[_task(desc="Informe", crono="cronos/crono-a.md")])
        names = [c.name for c in T.collect_cronos([ws], TODAY, full=True)]
        assert names == ["c"] and len(names) == 1   # solo el libre
        assert (ws / "cronos/crono-libre.md").exists()

    def test_ics_skips_linked_crono(self, ws):
        from views.cal.ics import _collect_project_items
        _write_dated_crono(ws, "cronos/crono-a.md", [(False, "X", _d(3), "1d")])
        _write_dated_crono(ws, "cronos/crono-libre.md", [(False, "Y", _d(3), "1d")])
        _seed(ws, tasks=[_task(desc="Informe", date=_d(9), crono="cronos/crono-a.md")])
        items = _collect_project_items(ws)
        descs = [it["desc"] for kind, it in items]
        assert "Informe" in descs
        assert any(d.startswith("crono-libre:") for d in descs)
        assert not any(d.startswith("crono-a:") for d in descs)

    def test_secretary_today_block(self, ws):
        from views.secretary import agenda as A
        _write_dated_crono(ws, "cronos/crono-a.md", [(False, "Intro", _d(-10), "3d")])
        _seed(ws, tasks=[_task(desc="Informe", date=_d(40), crono="cronos/crono-a.md")])
        crono = {A._crono_key(ws, "tasks", _read(ws)["tasks"][0]):
                 (ws, "tasks", _read(ws)["tasks"][0],
                  [{"index": "1", "title": "Intro", "start": None,
                    "end": TODAY.fromisoformat(_d(-8))}])}
        rows = A._today_block([], [], (), crono=crono, today=TODAY)
        row = rows[-1]
        assert row.startswith("| ☐ | ⚠️ |")
        assert "Informe [📊 0%](" in row
        assert "<br>↳ 1 Intro · ⚠️ vencido" in row

    def test_secretary_steps_hang_once_on_existing_row(self, ws):
        from views.secretary import agenda as A
        _seed(ws, tasks=[_task(desc="Informe", date=_d(-1), crono="cronos/crono-a.md")])
        t = _read(ws)["tasks"][0]
        step = {"index": "1", "title": "Intro", "start": None,
                "end": TODAY.fromisoformat(_d(-8))}
        crono = {A._crono_key(ws, "tasks", t): (ws, "tasks", t, [step])}
        rows = A._today_block([], [(ws, t)], (), crono=crono, today=TODAY)
        body = "\n".join(rows)
        assert body.count("↳ 1 Intro") == 1
        assert len(rows) == 2          # cabecera + fila vencida, sin fila extra


class TestNextStep:
    """El item con crono sin pasos activos lleva ``↳`` con el siguiente paso."""

    def test_next_by_date(self, ws):
        from core.cronograma import next_step, next_step_label
        _write_dated_crono(ws, "cronos/crono-a.md", [
            (True, "Hecho", _d(-5), "1d"),
            (False, "Final", _d(20), "3d"),
            (False, "Antes", _d(10), "2d")])
        it = _task(desc="Informe", crono="cronos/crono-a.md")
        st = next_step(ws, it, TODAY)
        assert st["title"] == "Antes"
        assert next_step_label(st, TODAY) == (
            f"3 Antes · empieza {_d(10)[5:]}")

    def test_undated_falls_back_to_first_open(self, ws):
        from core.cronograma import next_step, next_step_label
        _write_crono(ws, "cronos/crono-a.md", 1, 3)
        st = next_step(ws, _task(crono="cronos/crono-a.md"), TODAY)
        assert next_step_label(st, TODAY) == "2 paso 2"

    def test_all_done_or_missing_is_none(self, ws):
        from core.cronograma import next_step
        _write_crono(ws, "cronos/crono-a.md", 2, 2)
        assert next_step(ws, _task(crono="cronos/crono-a.md"), TODAY) is None
        assert next_step(ws, _task(crono="cronos/nada.md"), TODAY) is None

    def test_secretary_row_shows_next_step(self, ws):
        from views.secretary import agenda as A
        _write_crono(ws, "cronos/crono-a.md", 0, 2)
        _seed(ws, tasks=[_task(desc="Informe", date=_d(2),
                               crono="cronos/crono-a.md")])
        t = _read(ws)["tasks"][0]
        rows = A._next_days_block(TODAY, {_d(2): [("tasks", t, ws, "[foo]")]})
        assert any("Informe" in r and "<br>↳ 1 paso 1" in r for r in rows)

    def test_followup_row_shows_next_step(self, ws):
        from views.secretary import agenda as A
        _write_crono(ws, "cronos/crono-a.md", 0, 2)
        t = _task(desc="Informe", crono="cronos/crono-a.md")
        row = A._render_followup_row(ws, "tasks", t, {"date": ISO}, today=TODAY)
        assert row.endswith(" |") and "<br>↳ 1 paso 1" in row


class TestLsCronos:

    def test_lists_name_progress_owner_and_next(self, ws, capsys):
        from core.cronograma import run_ls_cronos
        _write_crono(ws, "cronos/crono-hk-general.md", 1, 3)
        _write_crono(ws, "cronos/crono-libre.md", 0, 1)
        _seed(ws, tasks=[_task(desc="HK", date=_d(30),
                               crono="cronos/crono-hk-general.md")])
        assert run_ls_cronos(ws.name, today=TODAY) == 0
        out = capsys.readouterr().out
        assert f"[{ws.name}]" in out
        assert (f"[hk-general](cronos/crono-hk-general.md)  📊 33% (1/3)  "
                f"✏️ HK · {_d(30)}") in out
        assert "↳ 2 paso 2" in out
        assert "[libre](cronos/crono-libre.md)  📊 0% (0/1)  sin item" in out

    def test_empty(self, ws, capsys):
        from core.cronograma import run_ls_cronos
        assert run_ls_cronos(ws.name, today=TODAY) == 0
        assert "No hay cronogramas" in capsys.readouterr().out


# ── F3 (parte): la fecha de un item con crono es su plazo ──────────────────

class TestKeepsDate:

    def test_triage_fup_keeps_date(self, ws, monkeypatch):
        from tests.test_triage import _feed
        _seed(ws, tasks=[_task(desc="X", date=ISO, crono="cronos/crono-a.md")])
        _feed(monkeypatch, _d(3))
        row = T.Row("task", ws, _read(ws)["tasks"][-1], T.HOY)
        assert T._act_fup(row, TODAY)
        it = _read(ws)["tasks"][-1]
        assert it["date"] == ISO
        assert f"⏩ {_d(3)}" in it["notes"]

    def test_triage_fup_none_refused(self, ws, monkeypatch, capsys):
        from tests.test_triage import _feed
        _seed(ws, tasks=[_task(desc="X", date=ISO, crono="cronos/crono-a.md")])
        _feed(monkeypatch, "none")
        row = T.Row("task", ws, _read(ws)["tasks"][-1], T.HOY)
        assert not T._act_fup(row, TODAY)
        assert _read(ws)["tasks"][-1]["date"] == ISO
        assert "plazo de su crono" in capsys.readouterr().out

    def test_edit_fup_none_refused(self, ws, capsys):
        from core.agenda_cmds import run_ms_edit
        _seed(ws, milestones=[_task(desc="E", date=ISO, crono="cronos/crono-a.md")])
        assert run_ms_edit(ws.name, "E", fup="none") == 1
        assert _read(ws)["milestones"][-1]["date"] == ISO

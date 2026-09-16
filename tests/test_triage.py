"""Tests de core/triage.py — `day` y `organize <proyecto>` (ADR-051)."""

from datetime import date, timedelta
from types import SimpleNamespace

import pytest

from core import triage as T
from core.agenda.display import item_followups


TODAY = date(2026, 9, 16)
ISO = TODAY.isoformat()


def _d(n: int) -> str:
    return (TODAY + timedelta(days=n)).isoformat()


# ── Clasificación en bloques ─────────────────────────────────────────────────

class TestClassify:

    def test_task_today_is_hoy(self):
        it = {"desc": "x", "date": ISO, "status": "pending"}
        assert T.classify(it, "task", TODAY, full=False) == T.HOY

    def test_multiday_event_started_before_is_hoy(self):
        it = {"desc": "workshop", "date": _d(-2), "end": _d(2)}
        assert T.classify(it, "ev", TODAY, full=False) == T.HOY

    def test_recurring_event_occurring_today_is_hoy(self):
        # Base en el pasado (sin avanzar), semanal → cae hoy.
        it = {"desc": "clase", "date": _d(-7), "recur": "weekly"}
        assert T.classify(it, "ev", TODAY, full=False) == T.HOY

    def test_recurring_event_not_today_is_hidden_in_day(self):
        it = {"desc": "clase", "date": _d(-6), "recur": "weekly"}
        assert T.classify(it, "ev", TODAY, full=False) is None

    def test_overdue_task_and_ms(self):
        for kind in ("task", "ms"):
            it = {"desc": "x", "date": _d(-3), "status": "pending"}
            assert T.classify(it, kind, TODAY, full=False) == T.VENCIDAS

    def test_past_event_is_not_overdue(self):
        it = {"desc": "x", "date": _d(-3)}
        assert T.classify(it, "ev", TODAY, full=False) is None
        assert T.classify(it, "ev", TODAY, full=True) is None

    def test_due_followup_is_decidir(self):
        it = {"desc": "x", "status": "pending", "notes": [f"⏩ {_d(-1)}"]}
        assert T.classify(it, "task", TODAY, full=False) == T.DECIDIR

    def test_future_followup_hidden_in_day(self):
        it = {"desc": "x", "status": "pending", "notes": [f"⏩ {_d(1)}"]}
        assert T.classify(it, "task", TODAY, full=False) is None

    def test_hoy_wins_over_decidir(self):
        it = {"desc": "x", "date": ISO, "status": "pending",
              "notes": [f"⏩ {_d(-1)}"]}
        assert T.classify(it, "task", TODAY, full=False) == T.HOY

    def test_undated_task_only_in_project_mode(self):
        it = {"desc": "x", "status": "pending"}
        assert T.classify(it, "task", TODAY, full=False) is None
        assert T.classify(it, "task", TODAY, full=True) == T.SIN_FECHA

    def test_future_citas_only_in_project_mode(self):
        it = {"desc": "x", "date": _d(5), "status": "pending"}
        assert T.classify(it, "task", TODAY, full=False) is None
        assert T.classify(it, "task", TODAY, full=True) == T.PROXIMAS

    def test_reminders_hidden_in_day_shown_in_project(self):
        it = {"desc": "r", "date": ISO, "time": "09:00"}
        assert T.classify(it, "reminder", TODAY, full=False) is None
        assert T.classify(it, "reminder", TODAY, full=True) == T.HOY

    def test_done_and_cancelled_never_listed(self):
        for full in (False, True):
            assert T.classify({"desc": "x", "date": ISO, "status": "done"},
                              "task", TODAY, full) is None
            assert T.classify({"desc": "r", "date": ISO, "cancelled": True},
                              "reminder", TODAY, full) is None

    def test_ended_recurring_series_not_upcoming(self):
        it = {"desc": "x", "date": _d(-30), "recur": "weekly", "until": _d(-1)}
        assert T.classify(it, "ev", TODAY, full=True) is None


# ── Recogida sobre ficheros ──────────────────────────────────────────────────

@pytest.fixture
def ws(tmp_path, monkeypatch):
    """Workspace con un proyecto real (`💻foo`) y ficheros genéricos."""
    type_dir = tmp_path / "💻sw"
    type_dir.mkdir()
    proj = type_dir / "💻foo"
    proj.mkdir()
    (proj / "project.md").write_text(
        "# foo\n- Tipo: 💻 Software\n- Estado: [auto]\n- Prioridad: media\n")
    (proj / "logbook.md").write_text("# Logbook — foo\n\n")
    (proj / "agenda.md").write_text("# Agenda — foo\n\n")
    monkeypatch.setattr("core.config.ORBIT_HOME", tmp_path)
    monkeypatch.setattr("core.config._ORBIT_JSON", tmp_path / "orbit.json")
    monkeypatch.setattr("core.log.PROJECTS_DIR", tmp_path)
    return proj


def _seed(proj, **sections):
    from core.agenda_cmds import _read_agenda, _write_agenda
    data = _read_agenda(proj / "agenda.md")
    for k, v in sections.items():
        data[k] = v
    _write_agenda(proj / "agenda.md", data)


def _read(proj):
    from core.agenda_cmds import _read_agenda
    return _read_agenda(proj / "agenda.md")


class TestCollect:

    def test_blocks_order_and_numbering(self, ws):
        _seed(ws,
              tasks=[{"desc": "someday", "status": "pending"},
                     {"desc": "late", "date": _d(-2), "status": "pending"},
                     {"desc": "fup", "status": "pending",
                      "notes": [f"⏩ {_d(-1)}"]},
                     {"desc": "next", "date": _d(3), "status": "pending"}],
              events=[{"desc": "b", "date": ISO, "time": "17:00"},
                      {"desc": "a", "date": ISO, "time": "09:00"}])
        rows = T.number_rows(T.collect([ws], TODAY, full=True))
        assert [(r.section, r.item["desc"]) for r in rows] == [
            (T.HOY, "a"), (T.HOY, "b"), (T.VENCIDAS, "late"),
            (T.DECIDIR, "fup"), (T.PROXIMAS, "next"), (T.SIN_FECHA, "someday")]

    def test_day_mode_keeps_only_today_overdue_and_due_fups(self, ws):
        _seed(ws, tasks=[{"desc": "someday", "status": "pending"},
                         {"desc": "next", "date": _d(3), "status": "pending"},
                         {"desc": "late", "date": _d(-2), "status": "pending"}])
        rows = T.number_rows(T.collect([ws], TODAY, full=False))
        assert [r.item["desc"] for r in rows] == ["late"]

    def test_untimed_first_in_hoy(self, ws):
        _seed(ws, events=[{"desc": "timed", "date": ISO, "time": "08:00"},
                          {"desc": "allday", "date": _d(-1), "end": _d(1)}])
        rows = T.number_rows(T.collect([ws], TODAY, full=False))
        assert [r.item["desc"] for r in rows] == ["allday", "timed"]


# ── Presentación ─────────────────────────────────────────────────────────────

class TestFormat:

    def _row(self, item, kind="task", section=T.HOY, name="💻foo"):
        from pathlib import Path
        return T.Row(kind, Path(name), item, section)

    def test_row_marks_overdue_followup_and_project(self):
        row = self._row({"desc": "X", "date": _d(-2), "status": "pending",
                         "notes": [f"⏩ {_d(-1)}", f"⏩ {_d(4)}"]},
                        section=T.VENCIDAS)
        line = T.format_row(3, row, TODAY, show_project=True)
        assert "  3. ✏️ 09-14" in line
        assert "⚠️" in line
        assert "❗⏩09-15(+1)" in line
        assert line.endswith("[💻foo]")

    def test_followup_due_today_has_no_exclamation(self):
        row = self._row({"desc": "X", "status": "pending",
                         "notes": [f"⏩ {ISO}"]}, section=T.DECIDIR)
        line = T.format_row(1, row, TODAY, show_project=False)
        assert "⏩09-16" in line and "❗" not in line
        assert "[" not in line

    def test_multiday_event_shows_end(self):
        row = self._row({"desc": "W", "date": _d(-1), "end": _d(2)}, kind="ev")
        assert "→09-18" in T.format_row(1, row, TODAY, show_project=False)

    def test_menu_depends_on_kind_and_followups(self):
        ev = self._row({"desc": "E", "date": ISO}, kind="ev")
        assert "do[n]e" not in T.menu_for(ev)
        assert "[c]lear" not in T.menu_for(ev)
        task = self._row({"desc": "T", "notes": [f"⏩ {ISO}"]})
        assert "do[n]e" in T.menu_for(task) and "[c]lear" in T.menu_for(task)

    def test_empty_listing(self):
        lines = T.format_listing("Día", {}, TODAY, show_project=True)
        assert "  (nada que triar)" in lines


class TestParseFupInput:

    def test_empty_is_tomorrow(self):
        assert T.parse_fup_input("", TODAY) == (_d(1), None)

    def test_date_only(self):
        assert T.parse_fup_input("2026-09-20", TODAY) == ("2026-09-20", None)

    def test_date_and_description(self):
        assert T.parse_fup_input("2026-09-20 hablar con Pablo", TODAY) == (
            "2026-09-20", "hablar con Pablo")

    def test_unrecognised(self):
        assert T.parse_fup_input("nunca jamás", TODAY) is None


# ── Cronogramas (solo lectura) ───────────────────────────────────────────────

class TestCronos:

    def _crono(self, proj, name, body):
        d = proj / "cronos"
        d.mkdir(exist_ok=True)
        (d / f"crono-{name}.md").write_text(f"# Cronograma: {name}\n\n{body}")

    def test_active_and_overdue_steps_listed(self, ws):
        self._crono(ws, "plan",
                    f"- [x] 1 hecho | {_d(-10)} | 1d\n"
                    f"- [ ] 2 atrasado | {_d(-5)} | 2d\n"
                    f"- [ ] 3 en curso | {_d(-1)} | 3d\n"
                    f"- [ ] 4 futuro | {_d(10)} | 1d\n")
        [c] = T.collect_cronos([ws], TODAY, full=False)
        assert (c.done, c.total) == (1, 4)
        assert [s.title for s in c.steps] == ["atrasado", "en curso"]

    def test_floating_steps_are_not_active_every_day(self, ws):
        # Sin fechas: heredan initial-time = hoy y "flotan".
        self._crono(ws, "dag", "- [ ] 1 uno\n- [ ] 2 dos\n")
        assert T.collect_cronos([ws], TODAY, full=False) == []
        [c] = T.collect_cronos([ws], TODAY, full=True)
        assert c.steps == []

    def test_finished_crono_hidden(self, ws):
        self._crono(ws, "fin", f"- [x] 1 uno | {_d(-3)} | 1d\n")
        assert T.collect_cronos([ws], TODAY, full=True) == []

    def test_cronos_block_is_unnumbered(self, ws):
        self._crono(ws, "plan", f"- [ ] 1 atrasado | {_d(-5)} | 1d\n")
        lines = T.format_cronos(T.collect_cronos([ws], TODAY, full=True),
                                TODAY, show_project=False, show_progress=True)
        assert lines[0].startswith("── 📊 Cronogramas (solo lectura)")
        assert "0/1" in lines[1]
        assert "1 atrasado" in lines[2] and "⚠️ vencido" in lines[2]


# ── Acciones ─────────────────────────────────────────────────────────────────

def _feed(monkeypatch, *answers):
    it = iter(answers)
    monkeypatch.setattr(T, "_prompt", lambda *a, **k: next(it))


def _row_for(proj, key, kind, section=T.HOY):
    return T.Row(kind, proj, _read(proj)[key][-1], section)


class TestActions:

    def test_fup_adds_when_none_due(self, ws, monkeypatch):
        _seed(ws, tasks=[{"desc": "X", "status": "pending"}])
        _feed(monkeypatch, f"{_d(3)} revisar")
        assert T._act_fup(_row_for(ws, "tasks", "task"), TODAY)
        fups = item_followups(_read(ws)["tasks"][-1])
        assert fups == [{"date": _d(3), "desc": "revisar"}]

    def test_fup_moves_due_followups_and_keeps_desc(self, ws, monkeypatch):
        _seed(ws, tasks=[{"desc": "X", "status": "pending",
                          "notes": [f"⏩ {_d(-4)} tema", f"⏩ {_d(9)}"]}])
        _feed(monkeypatch, "")                     # enter = mañana
        assert T._act_fup(_row_for(ws, "tasks", "task", T.DECIDIR), TODAY)
        fups = item_followups(_read(ws)["tasks"][-1])
        assert sorted(f["date"] for f in fups) == [_d(1), _d(9)]
        assert {"date": _d(1), "desc": "tema"} in fups

    def test_fup_rejects_past_date(self, ws, monkeypatch, capsys):
        _seed(ws, tasks=[{"desc": "X", "status": "pending"}])
        _feed(monkeypatch, _d(-2))
        assert not T._act_fup(_row_for(ws, "tasks", "task"), TODAY)
        assert item_followups(_read(ws)["tasks"][-1]) == []

    def test_clear_single_followup(self, ws, monkeypatch):
        _seed(ws, tasks=[{"desc": "X", "status": "pending",
                          "notes": [f"⏩ {_d(-1)}"]}])
        assert T._act_clear(_row_for(ws, "tasks", "task"), TODAY)
        cita = _read(ws)["tasks"][-1]
        assert item_followups(cita) == [] and cita["status"] == "pending"

    def test_clear_picks_among_several(self, ws, monkeypatch):
        _seed(ws, tasks=[{"desc": "X", "status": "pending",
                          "notes": [f"⏩ {_d(-1)}", f"⏩ {_d(5)}"]}])
        _feed(monkeypatch, "2")
        assert T._act_clear(_row_for(ws, "tasks", "task"), TODAY)
        assert [f["date"] for f in item_followups(_read(ws)["tasks"][-1])] == [_d(-1)]

    def test_time_on_undated_task_sets_today_and_resolves_fups(self, ws, monkeypatch):
        today = date.today()
        _seed(ws, tasks=[{"desc": "X", "status": "pending",
                          "notes": [f"⏩ {(today - timedelta(days=1)).isoformat()}"]}])
        _feed(monkeypatch, "11:30", "")            # hora, enter = hoy
        assert T._act_time(_row_for(ws, "tasks", "task", T.DECIDIR), today)
        cita = _read(ws)["tasks"][-1]
        assert cita["date"] == today.isoformat()
        assert cita["time"] == "11:30"
        assert item_followups(cita) == []

    def test_time_rejects_bad_value(self, ws, monkeypatch):
        _seed(ws, tasks=[{"desc": "X", "status": "pending"}])
        _feed(monkeypatch, "25:99")
        assert not T._act_time(_row_for(ws, "tasks", "task"), TODAY)
        assert not _read(ws)["tasks"][-1].get("time")

    def test_done_task(self, ws, monkeypatch):
        _seed(ws, tasks=[{"desc": "X", "status": "pending"}])
        assert T._act_done(_row_for(ws, "tasks", "task"), TODAY)
        assert _read(ws)["tasks"][-1]["status"] == "done"

    def test_done_not_for_events(self, ws, capsys):
        _seed(ws, events=[{"desc": "E", "date": ISO}])
        assert not T._act_done(_row_for(ws, "events", "ev"), TODAY)
        assert "no se completa" in capsys.readouterr().out

    def test_drop_needs_confirmation(self, ws, monkeypatch):
        _seed(ws, tasks=[{"desc": "X", "status": "pending"}])
        _feed(monkeypatch, "")                     # defecto No
        assert not T._act_drop(_row_for(ws, "tasks", "task"), TODAY)
        assert _read(ws)["tasks"][-1]["status"] == "pending"
        _feed(monkeypatch, "s")
        assert T._act_drop(_row_for(ws, "tasks", "task"), TODAY)
        assert _read(ws)["tasks"][-1]["status"] == "cancelled"


# ── CLI: enrutado de organize y panel de proyecto ────────────────────────────

class TestCli:

    def _args(self, **kw):
        base = dict(target=None, project=None, period=None,
                    triage=False, undated=False)
        base.update(kw)
        return SimpleNamespace(**base)

    def test_organize_without_project_points_to_day(self, capsys):
        import orbit
        assert orbit.cmd_organize(self._args()) == 1
        assert "day" in capsys.readouterr().out

    def test_organize_with_project_uses_triage(self, monkeypatch):
        import orbit
        seen = {}
        monkeypatch.setattr("core.triage.run_organize_project",
                            lambda p: seen.setdefault("p", p) and 0)
        orbit.cmd_organize(self._args(target="foo"))
        assert seen == {"p": "foo"}

    def test_legacy_forms_still_route_to_old_organize(self, monkeypatch):
        import orbit
        calls = []
        monkeypatch.setattr("core.organize.run_organize",
                            lambda **kw: calls.append(kw) or 0)
        orbit.cmd_organize(self._args(triage=True))
        orbit.cmd_organize(self._args(target="tasks"))
        orbit.cmd_organize(self._args(period="week", project="foo"))
        assert calls[0]["triage"] is True
        assert calls[1]["type_filter"] == "tasks" and calls[1]["project"] is None
        assert calls[2]["period"] == "week" and calls[2]["project"] == "foo"

    def test_day_and_organize_allowed_in_project_panel(self, ws):
        from core import context
        context.pin("foo")
        try:
            assert context.check_blocked(["day"]) is None
            assert context.check_blocked(["organize"]) is None
        finally:
            context.clear()

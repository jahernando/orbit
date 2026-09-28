"""`--fup none` (sin fecha), títulos duplicados, `day fup` y la
verificación tras cada acción del triaje."""

from types import SimpleNamespace

from core import triage as T
from core.agenda.display import item_followups
from tests.test_triage import ws, _seed, _read, _feed, _row_for, TODAY, ISO, _d  # noqa: F401


def _task(**kw):
    base = {"desc": "X", "status": "pending"}
    base.update(kw)
    return base


# ── --fup none ──────────────────────────────────────────────────────────────

class TestFupNone:

    def test_edit_leaves_task_undated(self, ws):
        from core.agenda_cmds import run_task_edit
        _seed(ws, tasks=[_task(date=ISO, time="10:00", ring="5m",
                               notes=["contexto", f"⏩ {_d(2)}"])])
        assert run_task_edit(ws.name, "X", fup="none") == 0
        it = _read(ws)["tasks"][-1]
        assert not it.get("date") and not it.get("time") and not it.get("ring")
        assert item_followups(it) == []
        assert "contexto" in it["notes"]           # el resto del cuerpo queda

    def test_edit_case_insensitive(self, ws):
        from core.agenda_cmds import run_ms_edit
        _seed(ws, milestones=[_task(date=ISO)])
        assert run_ms_edit(ws.name, "X", fup="None") == 0
        assert not _read(ws)["milestones"][-1].get("date")

    def test_edit_refuses_event(self, ws, capsys):
        from core.agenda_cmds import run_ev_edit
        _seed(ws, events=[{"desc": "E", "date": ISO}])
        assert run_ev_edit(ws.name, "E", fup="none") == 1
        assert _read(ws)["events"][-1]["date"] == ISO
        assert "necesita fecha" in capsys.readouterr().out

    def test_edit_refuses_recurring(self, ws, capsys):
        from core.agenda_cmds import run_task_edit
        _seed(ws, tasks=[_task(date=ISO, recur="weekly")])
        assert run_task_edit(ws.name, "X", fup="none", force=True) == 1
        assert _read(ws)["tasks"][-1]["date"] == ISO
        assert "recurrente" in capsys.readouterr().out

    def test_edit_refuses_with_date(self, ws):
        from core.agenda_cmds import run_task_edit
        _seed(ws, tasks=[_task(date=ISO)])
        assert run_task_edit(ws.name, "X", fup="none", new_date=_d(1)) == 1

    def test_add_undated(self, ws):
        from core.agenda_cmds import run_task_add
        assert run_task_add(ws.name, "nueva", fup="none") == 0
        it = _read(ws)["tasks"][-1]
        assert it["desc"] == "nueva" and not it.get("date")
        assert item_followups(it) == []

    def test_add_refuses_with_date(self, ws):
        from core.agenda_cmds import run_task_add
        assert run_task_add(ws.name, "nueva", date_val=_d(40), fup="none") == 1
        assert not _read(ws).get("tasks")

    def test_typed_fup_verb(self, ws):
        from core.agenda.runners import run_fup
        _seed(ws, tasks=[_task(date=ISO, notes=[f"⏩ {_d(1)}"])])
        assert run_fup("task", ws.name, "X", "none") == 0
        it = _read(ws)["tasks"][-1]
        assert not it.get("date") and item_followups(it) == []


# ── Títulos duplicados ──────────────────────────────────────────────────────

class TestDuplicates:

    def test_add_refuses_open_duplicate(self, ws, capsys):
        from core.agenda_cmds import run_task_add
        _seed(ws, tasks=[_task(desc="Revisar  correo")])
        assert run_task_add(ws.name, "revisar correo") == 1
        assert len(_read(ws)["tasks"]) == 1
        assert "Ya hay" in capsys.readouterr().out

    def test_add_allows_after_closed(self, ws):
        from core.agenda_cmds import run_task_add
        _seed(ws, tasks=[_task(desc="Y", status="done"),
                         _task(desc="Z", status="cancelled")])
        assert run_task_add(ws.name, "Y") == 0
        assert run_task_add(ws.name, "Z") == 0

    def test_same_title_other_kind_ok(self, ws):
        from core.agenda_cmds import run_ms_add
        _seed(ws, tasks=[_task()])
        assert run_ms_add(ws.name, "X") == 0

    def test_rename_onto_existing_refused(self, ws, capsys):
        from core.agenda_cmds import run_task_edit
        _seed(ws, tasks=[_task(desc="A"), _task(desc="B")])
        assert run_task_edit(ws.name, "B", new_text="a") == 1
        assert [t["desc"] for t in _read(ws)["tasks"]] == ["A", "B"]

    def test_rename_same_title_other_case_ok(self, ws):
        from core.agenda_cmds import run_task_edit
        _seed(ws, tasks=[_task(desc="A")])
        assert run_task_edit(ws.name, "A", new_text="a") == 0


# ── Triaje: ⏩ deja sin fecha ───────────────────────────────────────────────

class TestTriageFup:

    def test_none_undates(self, ws, monkeypatch):
        _seed(ws, tasks=[_task(date=ISO, notes=[f"⏩ {_d(-1)}"])])
        _feed(monkeypatch, "none")
        assert T._act_fup(_row_for(ws, "tasks", "task"), TODAY)
        it = _read(ws)["tasks"][-1]
        assert not it.get("date") and item_followups(it) == []

    def test_none_refused_for_event(self, ws, monkeypatch, capsys):
        _seed(ws, events=[{"desc": "E", "date": ISO}])
        _feed(monkeypatch, "none")
        assert not T._act_fup(_row_for(ws, "events", "ev"), TODAY)
        assert _read(ws)["events"][-1]["date"] == ISO

    def test_date_on_dated_task_undates_and_keeps_fup(self, ws, monkeypatch):
        _seed(ws, tasks=[_task(date=ISO, time="09:00")])
        _feed(monkeypatch, _d(3))
        assert T._act_fup(_row_for(ws, "tasks", "task"), TODAY)
        it = _read(ws)["tasks"][-1]
        assert not it.get("date") and not it.get("time")
        assert [f["date"] for f in item_followups(it)] == [_d(3)]

    def test_date_on_event_keeps_date(self, ws, monkeypatch):
        _seed(ws, events=[{"desc": "E", "date": ISO}])
        _feed(monkeypatch, _d(3))
        assert T._act_fup(_row_for(ws, "events", "ev"), TODAY)
        it = _read(ws)["events"][-1]
        assert it["date"] == ISO
        assert [f["date"] for f in item_followups(it)] == [_d(3)]

    def test_date_on_recurring_task_keeps_date(self, ws, monkeypatch):
        _seed(ws, tasks=[_task(date=ISO, recur="weekly")])
        _feed(monkeypatch, _d(3))
        assert T._act_fup(_row_for(ws, "tasks", "task"), TODAY)
        assert _read(ws)["tasks"][-1]["date"] == ISO


# ── Verificación tras la acción ─────────────────────────────────────────────

class TestDescribeAfter:

    def test_drop_says_cancelled(self, ws, monkeypatch):
        _seed(ws, tasks=[_task(date=ISO)])
        row = _row_for(ws, "tasks", "task")
        pos = T.locate_index(row)
        _feed(monkeypatch, "s")
        assert T._act_drop(row, TODAY)
        assert T.describe_after(row, pos, "d").endswith("→ cancelada")

    def test_done_says_completed(self, ws):
        _seed(ws, milestones=[_task(date=ISO)])
        row = _row_for(ws, "milestones", "ms")
        pos = T.locate_index(row)
        assert T._act_done(row, TODAY)
        assert T.describe_after(row, pos, "n").endswith("→ completado")

    def test_event_drop_says_removed(self, ws, monkeypatch):
        _seed(ws, events=[{"desc": "E", "date": ISO}, {"desc": "F", "date": ISO}])
        row = T.Row("ev", ws, _read(ws)["events"][0], T.HOY)
        pos = T.locate_index(row)
        _feed(monkeypatch, "s")
        assert T._act_drop(row, TODAY)
        assert "eliminado" in T.describe_after(row, pos, "d")

    def test_undated_state(self, ws, monkeypatch):
        _seed(ws, tasks=[_task(date=ISO)])
        row = _row_for(ws, "tasks", "task")
        pos = T.locate_index(row)
        _feed(monkeypatch, "none")
        assert T._act_fup(row, TODAY)
        assert T.describe_after(row, pos, "u").endswith("→ sin fecha")

    def test_not_cancelled_is_flagged(self, ws):
        _seed(ws, tasks=[_task(date=ISO)])
        row = _row_for(ws, "tasks", "task")
        msg = T.describe_after(row, T.locate_index(row), "d")
        assert msg.startswith("⚠️") and "NO se ha cancelado" in msg


# ── day fup ─────────────────────────────────────────────────────────────────

class TestDayFup:

    def test_loop_goes_straight_to_fup(self, ws, monkeypatch, capsys):
        _seed(ws, tasks=[_task(date=ISO)])
        _feed(monkeypatch, "1", _d(2), "q")
        monkeypatch.setattr(T, "_refresh", lambda n: None)
        T.run_loop("t", [ws], full=False, show_project=False,
                   today_fn=lambda: TODAY, fup_only=True)
        it = _read(ws)["tasks"][-1]
        assert not it.get("date")
        assert [f["date"] for f in item_followups(it)] == [_d(2)]
        out = capsys.readouterr().out
        assert "[h]ora" not in out                      # sin menú
        assert f"→ sin fecha · ⏩ {_d(2)}" in out        # verificación

    def _args(self, mode=None, project=None):
        return SimpleNamespace(mode=mode, project=project)

    def test_cli_routing(self, monkeypatch):
        import orbit
        calls = []
        monkeypatch.setattr("core.triage.run_day",
                            lambda project=None, fup_only=False:
                            calls.append((project, fup_only)) or 0)
        orbit.cmd_day(self._args())
        orbit.cmd_day(self._args("fup"))
        orbit.cmd_day(self._args("fup", "foo"))
        orbit.cmd_day(self._args("foo"))
        assert calls == [(None, False), (None, True), ("foo", True),
                         ("foo", False)]

    def test_cli_rejects_unknown_mode_with_project(self, capsys):
        import orbit
        assert orbit.cmd_day(self._args("otra", "foo")) == 1

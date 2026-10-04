"""`day fup`: calendario de carga (core/loadcal.py) y ⏩ por lotes (ADR-056)."""

import re

from core import loadcal as L
from core import triage as T
from core.agenda.display import item_followups
from tests.test_triage import ws, _seed, _read, _feed, TODAY, ISO, _d  # noqa: F401

_ANSI = re.compile(r"\x1b\[[0-9;]*m")


def _task(desc, **kw):
    base = {"desc": desc, "status": "pending"}
    base.update(kw)
    return base


# ── Niveles ──────────────────────────────────────────────────────────────────

class TestLevel:

    def test_thresholds(self):
        cases = {0: 0, 1: 1, 4: 1, 5: 2, 9: 2, 10: 3, 14: 3, 15: 4, 40: 4}
        assert {n: L.level(n) for n in cases} == cases


# ── Carga ────────────────────────────────────────────────────────────────────

class TestDayLoads:

    def test_counts_occurrences_and_followups_not_reminders(self, ws):
        _seed(ws,
              tasks=[_task("a", date=_d(2)),
                     _task("b", notes=[f"⏩ {_d(2)}"]),
                     _task("c", date=_d(2), status="done"),
                     _task("late", date=_d(-3))],
              events=[{"desc": "congreso", "date": _d(1), "end": _d(3)}],
              reminders=[{"desc": "r", "date": _d(2), "time": "09:00"}])
        days = [TODAY + __import__("datetime").timedelta(days=i)
                for i in range(-1, 5)]
        loads = L.day_loads([ws], TODAY, days)
        assert TODAY - __import__("datetime").timedelta(days=1) not in loads
        assert loads[TODAY] == 1                  # la vencida, como en `day`
        assert loads[TODAY.fromisoformat(_d(1))] == 1
        assert loads[TODAY.fromisoformat(_d(2))] == 3   # a + ⏩b + congreso
        assert loads[TODAY.fromisoformat(_d(4))] == 0

    def test_weeks_start_on_monday_of_current_week(self):
        weeks = L.weeks_from(TODAY)                # 2026-09-16 es miércoles
        assert len(weeks) == 5
        assert weeks[0][0].isoformat() == "2026-09-14"
        assert all(len(w) == 7 for w in weeks)


# ── Presentación ─────────────────────────────────────────────────────────────

class TestRender:

    def _render(self, **kw):
        weeks = L.weeks_from(TODAY)
        loads = {d: 7 for w in weeks for d in w if d >= TODAY}
        loads[TODAY] = 21
        return L.render(loads, TODAY, weeks, **kw)

    def test_plain_uses_glyphs_and_marks_today(self):
        lines = self._render(ansi=False)
        body = "\n".join(lines)
        assert "[16 █]" in body and " 17 ▒ " in body
        assert "(21)" not in body                  # sin números por defecto

    def test_counts_in_parentheses_when_asked(self):
        body = "\n".join(self._render(ansi=False, counts=True))
        assert "[16 (21) █]" in body and " 17 ( 7) ▒ " in body

    def test_rows_align(self):
        for kw in ({"ansi": False}, {"ansi": True}, {"ansi": True, "counts": True}):
            lines = [_ANSI.sub("", ln) for ln in self._render(**kw)[1:-1]]
            assert len({len(ln) for ln in lines}) == 1, kw

    def test_ansi_paints_grey_background(self):
        body = "\n".join(self._render(ansi=True))
        assert "\x1b[48;5;238m" in body            # muy alta = gris oscuro
        assert "█" not in body                     # el fondo sustituye al glifo

    def test_past_weeks_are_dropped(self):
        weeks = L.weeks_from(TODAY)
        lines = L.render({}, TODAY + __import__("datetime").timedelta(days=7),
                         weeks, ansi=False)
        assert len(lines) == 2 + 4 + 1             # título, cabecera, 4 semanas, leyenda


# ── Markdown (secretario) ────────────────────────────────────────────────────

class TestMarkdown:

    def test_milestone_days_only_open_and_future(self, ws):
        _seed(ws, milestones=[{"desc": "m1", "date": _d(3), "status": "pending"},
                              {"desc": "m2", "date": _d(4), "status": "done"},
                              {"desc": "m0", "date": _d(-2), "status": "pending"}])
        weeks = L.weeks_from(TODAY)
        days = [d for w in weeks for d in w]
        assert L.milestone_days([ws], TODAY, days) == {
            TODAY.fromisoformat(_d(3))}

    def test_cells_grey_bold_today_and_past(self):
        from datetime import timedelta
        d1, d3 = TODAY + timedelta(days=1), TODAY + timedelta(days=3)
        loads = {TODAY: 21, d1: 0, d3: 6}
        today = L.md_cell(TODAY, loads, TODAY)
        assert "[16]" in today and "background:#444444" in today
        assert 'title="21 citas"' in today
        assert L.md_cell(d1, loads, TODAY) == '<span title="0 citas">17</span>'
        ms = L.md_cell(d3, loads, TODAY, {d3})
        assert "border-bottom:2px solid currentColor" in ms and ">19<" in ms and "background:#a8a8a8" in ms and "hito" in ms
        past = L.md_cell(TODAY - timedelta(days=1), loads, TODAY)
        assert "opacity" in past and "background" not in past

    def test_render_md_month_and_window(self):
        from datetime import timedelta
        weeks = L.weeks_from(TODAY, n_weeks=1)
        loads = {d: 1 for w in weeks for d in w if d >= TODAY}
        rows = L.render_md(loads, TODAY, weeks, week_numbers=False,
                           last=TODAY + timedelta(days=2))
        assert rows[0] == "| Lu | Ma | Mi | Ju | Vi | Sa | Do |"
        assert len(rows) == 2 + 2
        assert rows[2].endswith("18</span> |  |  |")   # 19-20 fuera de ventana
        assert rows[3].count("|  ") == 7           # semana siguiente en blanco
        with_wk = L.render_md(loads, TODAY, weeks, month=9)
        assert with_wk[2].startswith("| **W38** |")


# ── Gramática del lote ───────────────────────────────────────────────────────

class TestParseBatch:

    def test_indexes_then_date(self):
        assert T.parse_fup_batch("3 5 viernes", 9, TODAY) == [([3, 5], "viernes")]

    def test_pairs_and_trailing_group(self):
        assert T.parse_fup_batch("1:+2 4:+3 6 7 +5", 9, TODAY) == [
            ([1], "+2"), ([4], "+3"), ([6, 7], "+5")]

    def test_bare_indexes_ask(self):
        assert T.parse_fup_batch("2 3", 9, TODAY) == [([2, 3], None)]

    def test_plus_n_is_a_date_not_an_index(self):
        assert T.parse_fup_batch("2 +3", 9, TODAY) == [([2], "+3")]

    def test_errors(self):
        assert "no hay cita 12" in T.parse_fup_batch("12 +1", 9, TODAY)
        assert "dos veces" in T.parse_fup_batch("2 2 +1", 9, TODAY)
        assert "no reconocida" in T.parse_fup_batch("2 nunca", 9, TODAY)
        assert "ya ha pasado" in T.parse_fup_batch(f"2 {_d(-1)}", 9, TODAY)
        assert "falta el número" in T.parse_fup_batch("viernes", 9, TODAY)

    def test_none_is_valid(self):
        assert T.parse_fup_batch("2 none", 9, TODAY) == [([2], "none")]


# ── Lote en el bucle ─────────────────────────────────────────────────────────

class TestBatchLoop:

    def _run(self, ws, monkeypatch, *answers):
        _feed(monkeypatch, *answers)
        monkeypatch.setattr(T, "_refresh", lambda n: None)
        T.run_loop("t", [ws], full=False, show_project=False,
                   today_fn=lambda: TODAY, fup_only=True)
        return {t["desc"]: t for t in _read(ws)["tasks"]}

    def test_batch_applies_after_confirmation(self, ws, monkeypatch, capsys):
        _seed(ws, tasks=[_task("a", date=ISO), _task("b", date=ISO),
                         _task("c", date=ISO)])
        tasks = self._run(ws, monkeypatch, f"1 3 {_d(2)}", "", "q")
        for k in ("a", "c"):
            assert not tasks[k].get("date")
            assert [f["date"] for f in item_followups(tasks[k])] == [_d(2)]
        assert tasks["b"]["date"] == ISO
        out = capsys.readouterr().out
        assert out.count(f"→ sin fecha · ⏩ {_d(2)}") == 2
        assert "carga" in out                      # el calendario se pinta

    def test_batch_declined_changes_nothing(self, ws, monkeypatch):
        _seed(ws, tasks=[_task("a", date=ISO), _task("b", date=ISO)])
        tasks = self._run(ws, monkeypatch, f"1 2 {_d(2)}", "n", "q")
        assert tasks["a"]["date"] == ISO and tasks["b"]["date"] == ISO

    def test_group_without_date_asks_once(self, ws, monkeypatch):
        _seed(ws, tasks=[_task("a", date=ISO), _task("b", date=ISO)])
        tasks = self._run(ws, monkeypatch, "1 2", _d(3), "s", "q")
        for k in ("a", "b"):
            assert [f["date"] for f in item_followups(tasks[k])] == [_d(3)]

    def test_invalid_batch_applies_nothing(self, ws, monkeypatch, capsys):
        _seed(ws, tasks=[_task("a", date=ISO)])
        tasks = self._run(ws, monkeypatch, "1 7 +2", "q")
        assert tasks["a"]["date"] == ISO
        assert "no hay cita 7" in capsys.readouterr().out

    def test_partial_failure_is_reported(self, ws, monkeypatch, capsys):
        _seed(ws, tasks=[_task("a", date=ISO)],
              events=[{"desc": "E", "date": ISO}])
        self._run(ws, monkeypatch, "1 2 none", "", "q")
        out = capsys.readouterr().out
        assert "⚠️  1. «E»" in out                 # un evento no queda sin fecha
        assert "«a»" in out and "→ sin fecha" in out

"""test_panel.py — tests for orbit panel command.

Covers:
  - _parse_panel_period: today, week, month, Spanish aliases, unknown
  - _scan_project_agenda: milestones, tasks today/overdue, events
  - _collect_priority_projects: alta, media, milestones filtering
  - _collect_agenda: items sorted by time, grouped by day
  - _collect_activity: logbook entries in period
  - run_panel: output for today, week, month
"""

import re
import pytest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

from core.panel import (
    _parse_panel_period,
    _scan_project_agenda,
    _collect_priority_projects,
    _collect_agenda,
    _collect_activity,
    _collect_decidir_hoy,
    run_panel,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _base_name(name: str) -> str:
    i = 0
    while i < len(name) and (ord(name[i]) > 127 or name[i] in '\ufe0f\u200d'):
        i += 1
    return name[i:]


def _make_project(type_dir, name="💻test-project", prioridad="media",
                  motivo="", agenda_extra="", logbook_extra=""):
    base = _base_name(name)
    proj = type_dir / name
    proj.mkdir(parents=True, exist_ok=True)

    prio_line = f"- Prioridad: {prioridad}"
    if motivo:
        prio_line += f" — {motivo}"

    (proj / f"{base}-project.md").write_text(
        f"# {name}\n- Tipo: 💻 Software\n- Estado: [auto]\n{prio_line}\n"
    )
    (proj / f"{base}-logbook.md").write_text(
        f"# Logbook — {name}\n\n{logbook_extra}"
    )
    (proj / f"{base}-agenda.md").write_text(
        f"# Agenda — {name}\n\n{agenda_extra}"
    )
    (proj / "notes").mkdir(exist_ok=True)
    return proj


def _add_followup(proj, kind_key, desc_match, fup_date, fup_desc=None):
    """Attach a ``⏩ DATE [desc]`` body followup to the item in *proj* whose
    ``desc`` contains *desc_match*, within ``data[kind_key]``.

    Followups live as body lines (``item['notes']``), never inline on the
    header — so this goes through `add_followup` + `_write_agenda` (the same
    path the `cita fup` verb uses) rather than raw agenda text.
    """
    from core.agenda_cmds import _read_agenda, _write_agenda
    from core.agenda.display import add_followup
    from core.log import resolve_file

    agenda_path = resolve_file(proj, "agenda")
    data = _read_agenda(agenda_path)
    for item in data[kind_key]:
        if desc_match in item.get("desc", ""):
            add_followup(item, fup_date, fup_desc)
    _write_agenda(agenda_path, data)


@pytest.fixture()
def panel_env(tmp_path, monkeypatch):
    type_dir = tmp_path / "💻software"
    type_dir.mkdir()
    monkeypatch.setattr("core.config.ORBIT_HOME", tmp_path)
    monkeypatch.setattr("core.config._ORBIT_JSON", tmp_path / "orbit.json")
    monkeypatch.setattr("core.log.PROJECTS_DIR", tmp_path)
    return {"tmp": tmp_path, "type_dir": type_dir}


# ═══════════════════════════════════════════════════════════════════════════════
# _parse_panel_period
# ═══════════════════════════════════════════════════════════════════════════════

class TestParsePanelPeriod:

    def test_none_is_today(self):
        start, end, label = _parse_panel_period(None)
        assert start == end == date.today()

    def test_today_string(self):
        start, end, _ = _parse_panel_period("today")
        assert start == end == date.today()

    def test_hoy(self):
        start, end, _ = _parse_panel_period("hoy")
        assert start == end == date.today()

    def test_week(self):
        start, end, label = _parse_panel_period("week")
        assert start.weekday() == 0  # Monday
        assert end.weekday() == 6    # Sunday
        assert (end - start).days == 6
        assert start <= date.today() <= end

    def test_semana(self):
        start, end, _ = _parse_panel_period("semana")
        assert start.weekday() == 0
        assert (end - start).days == 6

    def test_month(self):
        start, end, label = _parse_panel_period("month")
        today = date.today()
        assert start == date(today.year, today.month, 1)
        assert end.month == today.month
        assert end.day >= 28

    def test_mes(self):
        start, end, _ = _parse_panel_period("mes")
        today = date.today()
        assert start.day == 1
        assert start.month == today.month

    def test_unknown_defaults_to_today(self):
        start, end, _ = _parse_panel_period("xyzzy")
        assert start == end == date.today()

    def test_week_label_has_iso_week(self):
        _, _, label = _parse_panel_period("week")
        assert re.search(r'\d{4}-W\d{2}', label)

    def test_month_label_has_range(self):
        _, _, label = _parse_panel_period("month")
        assert "→" in label


# ═══════════════════════════════════════════════════════════════════════════════
# _scan_project_agenda
# ═══════════════════════════════════════════════════════════════════════════════

class TestScanProjectAgenda:

    def test_no_agenda(self, panel_env):
        proj = _make_project(panel_env["type_dir"])
        # Remove agenda
        for f in proj.glob("*-agenda.md"):
            f.unlink()
        ms, has_items, has_overdue = _scan_project_agenda(
            proj, date.today(), date.today())
        assert ms == []
        assert not has_items
        assert not has_overdue

    def test_milestone_this_month(self, panel_env):
        today = date.today()
        ms_date = (today + timedelta(days=5)).isoformat()
        agenda = f"## 🏁 Hitos\n\n- [ ] Entregar paper ({ms_date})\n"
        proj = _make_project(panel_env["type_dir"], agenda_extra=agenda)
        ms, _, _ = _scan_project_agenda(proj, today, today)
        assert len(ms) == 1
        assert ms[0][1] == "Entregar paper"

    def test_task_today(self, panel_env):
        today = date.today()
        agenda = f"## ✅ Tareas\n\n- [ ] Revisar código ({today.isoformat()})\n"
        proj = _make_project(panel_env["type_dir"], agenda_extra=agenda)
        _, has_items, _ = _scan_project_agenda(proj, today, today)
        assert has_items

    def test_task_overdue(self, panel_env):
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        agenda = f"## ✅ Tareas\n\n- [ ] Tarea vieja ({yesterday})\n"
        proj = _make_project(panel_env["type_dir"], agenda_extra=agenda)
        _, _, has_overdue = _scan_project_agenda(
            proj, date.today(), date.today())
        assert has_overdue

    def test_event_in_period(self, panel_env):
        today = date.today()
        agenda = f"## 📅 Eventos\n\n{today.isoformat()} — Reunión ⏰10:00\n"
        proj = _make_project(panel_env["type_dir"], agenda_extra=agenda)
        _, has_items, _ = _scan_project_agenda(proj, today, today)
        assert has_items


# ═══════════════════════════════════════════════════════════════════════════════
# _collect_priority_projects
# ═══════════════════════════════════════════════════════════════════════════════

class TestCollectPriorityProjects:

    def test_alta_project(self, panel_env):
        _make_project(panel_env["type_dir"], "💻proj-alta", prioridad="alta",
                      motivo="Paper deadline")
        alta, ms, media = _collect_priority_projects(
            date.today(), date.today())
        assert len(alta) == 1
        assert alta[0][1] == "Paper deadline"

    def test_media_from_tasks_today(self, panel_env):
        today = date.today()
        agenda = f"## ✅ Tareas\n\n- [ ] Tarea urgente ({today.isoformat()})\n"
        _make_project(panel_env["type_dir"], agenda_extra=agenda)
        alta, ms, media = _collect_priority_projects(today, today)
        assert len(alta) == 0
        assert len(media) == 1
        assert "citas en periodo" in media[0][1]

    def test_media_from_overdue(self, panel_env):
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        agenda = f"## ✅ Tareas\n\n- [ ] Tarea vieja ({yesterday})\n"
        _make_project(panel_env["type_dir"], agenda_extra=agenda)
        _, _, media = _collect_priority_projects(
            date.today(), date.today())
        assert len(media) == 1
        assert "vencidas" in media[0][1]

    def test_milestones_collected(self, panel_env):
        today = date.today()
        ms_date = (today + timedelta(days=3)).isoformat()
        agenda = f"## 🏁 Hitos\n\n- [ ] Hito importante ({ms_date})\n"
        _make_project(panel_env["type_dir"], agenda_extra=agenda)
        _, ms, _ = _collect_priority_projects(today, today)
        assert len(ms) == 1
        assert ms[0][2] == "Hito importante"

    def test_sleeping_project_excluded(self, panel_env):
        proj = _make_project(panel_env["type_dir"], "💻sleeping-proj",
                             prioridad="alta")
        # Set status to sleeping
        pf = next(proj.glob("*-project.md"))
        pf.write_text(pf.read_text().replace("[auto]", "sleeping"))
        alta, _, _ = _collect_priority_projects(
            date.today(), date.today())
        assert len(alta) == 0


# ═══════════════════════════════════════════════════════════════════════════════
# _collect_activity
# ═══════════════════════════════════════════════════════════════════════════════

class TestCollectActivity:

    def test_entries_today(self, panel_env):
        today = date.today().isoformat()
        logbook = f"{today} 📝 Test entry #apunte\n"
        _make_project(panel_env["type_dir"], logbook_extra=logbook)
        activity = _collect_activity(date.today(), date.today())
        assert len(activity) == 1
        assert any("Test entry" in e for e in activity[0][1])

    def test_no_entries(self, panel_env):
        _make_project(panel_env["type_dir"])
        activity = _collect_activity(date.today(), date.today())
        assert len(activity) == 0

    def test_entries_in_range(self, panel_env):
        today = date.today()
        yesterday = today - timedelta(days=1)
        logbook = f"{yesterday.isoformat()} 📝 Yesterday entry #apunte\n{today.isoformat()} 📝 Today entry #apunte\n"
        _make_project(panel_env["type_dir"], logbook_extra=logbook)
        # Range spanning yesterday→today catches both regardless of weekday
        # (a week-aligned range would drop yesterday when today is Monday).
        activity = _collect_activity(yesterday, today)
        assert len(activity) == 1
        assert len(activity[0][1]) == 2


# ═══════════════════════════════════════════════════════════════════════════════
# _collect_decidir_hoy
# ═══════════════════════════════════════════════════════════════════════════════

class TestCollectDecidirHoy:
    """Post-F5: the "Decidir hoy" surface is driven by followups (⏩ body
    lines) hung on any of the 4 cita types, not the retired ``ff`` axis.
    `_collect_decidir_hoy` returns ``[(project_dir, kind, item, fup)]`` for
    followups whose date ≤ today, ascending by followup date, skipping
    done/cancelled citas.
    """

    def test_includes_ff_today(self, panel_env):
        today = date.today()
        proj = _make_project(
            panel_env["type_dir"],
            agenda_extra="## ✅ Tareas\n- [ ] Decidir X\n",
        )
        _add_followup(proj, "tasks", "Decidir X", today.isoformat())
        items = _collect_decidir_hoy(today)
        assert len(items) == 1
        project_dir, kind, item, fup = items[0]
        assert kind == "task"
        assert item["desc"] == "Decidir X"
        assert fup["date"] == today.isoformat()

    def test_includes_ff_in_past(self, panel_env):
        today = date.today()
        past = (today - timedelta(days=5)).isoformat()
        proj = _make_project(
            panel_env["type_dir"],
            agenda_extra="## ✅ Tareas\n- [ ] Overdue Y\n",
        )
        _add_followup(proj, "tasks", "Overdue Y", past)
        items = _collect_decidir_hoy(today)
        assert len(items) == 1
        assert items[0][2]["desc"] == "Overdue Y"
        assert items[0][3]["date"] == past

    def test_includes_followup_on_milestone(self, panel_env):
        # Followups surface on any of the 4 types, not just tasks.
        today = date.today()
        proj = _make_project(
            panel_env["type_dir"],
            agenda_extra="## 🏁 Hitos\n- [ ] Entregar informe\n",
        )
        _add_followup(proj, "milestones", "Entregar informe", today.isoformat())
        items = _collect_decidir_hoy(today)
        assert len(items) == 1
        assert items[0][1] == "ms"
        assert items[0][2]["desc"] == "Entregar informe"

    def test_excludes_ff_future(self, panel_env):
        today = date.today()
        future = (today + timedelta(days=5)).isoformat()
        proj = _make_project(
            panel_env["type_dir"],
            agenda_extra="## ✅ Tareas\n- [ ] Later Z\n",
        )
        _add_followup(proj, "tasks", "Later Z", future)
        assert _collect_decidir_hoy(today) == []

    def test_excludes_task_without_followup(self, panel_env):
        today = date.today()
        _make_project(
            panel_env["type_dir"],
            agenda_extra="## ✅ Tareas\n- [ ] Plain task (2026-06-01)\n",
        )
        assert _collect_decidir_hoy(today) == []

    def test_excludes_done(self, panel_env):
        today = date.today()
        proj = _make_project(
            panel_env["type_dir"],
            agenda_extra="## ✅ Tareas\n- [x] Done X\n",
        )
        _add_followup(proj, "tasks", "Done X", today.isoformat())
        assert _collect_decidir_hoy(today) == []

    def test_orders_by_ff_ascending(self, panel_env):
        today = date.today()
        d1 = (today - timedelta(days=3)).isoformat()
        d2 = (today - timedelta(days=1)).isoformat()
        proj = _make_project(
            panel_env["type_dir"],
            agenda_extra="## ✅ Tareas\n- [ ] Newer A\n- [ ] Older B\n",
        )
        _add_followup(proj, "tasks", "Newer A", d2)
        _add_followup(proj, "tasks", "Older B", d1)
        items = _collect_decidir_hoy(today)
        assert [it[2]["desc"] for it in items] == ["Older B", "Newer A"]


# ═══════════════════════════════════════════════════════════════════════════════
# run_panel
# ═══════════════════════════════════════════════════════════════════════════════

class TestRunPanel:

    def test_today_runs(self, panel_env, capsys):
        rc = run_panel()
        assert rc == 0
        out = capsys.readouterr().out
        assert "# Panel" in out
        assert "## Prioridad" in out
        assert "## Agenda" in out
        assert "## Actividad" in out

    def test_week_runs(self, panel_env, capsys):
        rc = run_panel(period="week")
        assert rc == 0
        out = capsys.readouterr().out
        assert "W" in out
        assert "→" in out

    def test_month_runs(self, panel_env, capsys):
        rc = run_panel(period="month")
        assert rc == 0
        out = capsys.readouterr().out
        assert date.today().strftime("%Y-%m") in out

    def test_shows_alta_project(self, panel_env, capsys):
        _make_project(panel_env["type_dir"], "💻important",
                      prioridad="alta", motivo="Deadline")
        run_panel()
        out = capsys.readouterr().out
        assert "important" in out
        assert "Deadline" in out
        assert "🔴" in out

    def test_shows_activity(self, panel_env, capsys):
        today = date.today().isoformat()
        _make_project(panel_env["type_dir"],
                      logbook_extra=f"{today} 📊 Big result #resultado\n")
        run_panel()
        out = capsys.readouterr().out
        assert "Big result" in out

    def test_shows_agenda_item(self, panel_env, capsys):
        today = date.today()
        agenda = f"## 📅 Eventos\n\n{today.isoformat()} — Reunión ⏰10:00\n"
        _make_project(panel_env["type_dir"], agenda_extra=agenda)
        run_panel()
        out = capsys.readouterr().out
        assert "Reunión" in out

    def test_overdue_task_shows_original_date(self, panel_env, capsys):
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        agenda = f"## ✅ Tareas\n\n- [ ] Tarea vieja ({yesterday})\n"
        _make_project(panel_env["type_dir"], agenda_extra=agenda)
        run_panel()
        out = capsys.readouterr().out
        assert f"(📅{yesterday})" in out
        assert "⚠️" in out

    def test_spanish_period(self, panel_env, capsys):
        rc = run_panel(period="semana")
        assert rc == 0
        out = capsys.readouterr().out
        assert "W" in out

    # ── Decidir hoy section ─────────────────────────────────────────

    def test_decidir_section_today_empty(self, panel_env, capsys):
        _make_project(panel_env["type_dir"])
        run_panel()
        out = capsys.readouterr().out
        assert "## Decidir hoy" in out
        assert "(nada que decidir hoy)" in out

    def test_decidir_section_today_with_item(self, panel_env, capsys):
        today = date.today().isoformat()
        proj = _make_project(panel_env["type_dir"],
                             agenda_extra="## ✅ Tareas\n- [ ] Esperar X\n")
        _add_followup(proj, "tasks", "Esperar X", today)
        run_panel()
        out = capsys.readouterr().out
        # Section present, item rendered with the ☐ task icon and no ❗ marker
        # (followup date == today is not overdue).
        assert "## Decidir hoy" in out
        assert any("Esperar X" in line and line.startswith("| ☐ |") and "❗" not in line
                   for line in out.splitlines())

    def test_decidir_section_overdue_shows_exclamation(self, panel_env, capsys):
        past = (date.today() - timedelta(days=2)).isoformat()
        proj = _make_project(panel_env["type_dir"],
                             agenda_extra="## ✅ Tareas\n- [ ] Overdue Y\n")
        _add_followup(proj, "tasks", "Overdue Y", past)
        run_panel()
        out = capsys.readouterr().out
        assert any("Overdue Y" in line and "❗" in line
                   for line in out.splitlines())

    def test_decidir_section_shows_followup_desc(self, panel_env, capsys):
        # A followup may carry a theme (⏩ DATE desc); it renders as " — desc"
        # after the cita title. (Replaces the retired snooze test — snooze/❌
        # counters were dropped with the ff axis in F5.)
        today = date.today().isoformat()
        proj = _make_project(panel_env["type_dir"],
                             agenda_extra="## ✅ Tareas\n- [ ] Tough Z\n")
        _add_followup(proj, "tasks", "Tough Z", today, "revisar presupuesto")
        run_panel()
        out = capsys.readouterr().out
        assert any("Tough Z" in line and "revisar presupuesto" in line and "—" in line
                   for line in out.splitlines())

    def test_decidir_section_omitted_on_week(self, panel_env, capsys):
        today = date.today().isoformat()
        proj = _make_project(panel_env["type_dir"],
                             agenda_extra="## ✅ Tareas\n- [ ] X\n")
        _add_followup(proj, "tasks", "X", today)
        run_panel(period="week")
        out = capsys.readouterr().out
        assert "## Decidir hoy" not in out

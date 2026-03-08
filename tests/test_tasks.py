"""test_tasks.py — tests for task and ring operations.

Covers:
  - parse_task: basic, with time, with @ring, with @recur, [~], [x]
  - run_task_open: basic task, ring task, default date=today
  - run_task_schedule: reschedule preserving @ring and @recur
  - run_task_close: complete a task, advance recurring, advance recurring ring
  - Daily note: tasks with today's date are copied to the diario
"""

from datetime import date, timedelta
from pathlib import Path

import pytest

from core.tasks import parse_task, list_tasks
from core.task  import run_task_open, run_task_schedule, run_task_close


TODAY = date.today().isoformat()
FUTURE = (date.today() + timedelta(days=7)).isoformat()


# ═══════════════════════════════════════════════════════════════════════════════
# parse_task — unit tests (no filesystem)
# ═══════════════════════════════════════════════════════════════════════════════

class TestParseTask:

    def test_basic_pending(self):
        t = parse_task("- [ ] Revisar paper (2026-03-15)")
        assert t["description"] == "Revisar paper"
        assert t["due"] == "2026-03-15"
        assert t["time"] is None
        assert t["done"] is False
        assert t["ring"] is False
        assert t["recur"] is None

    def test_pending_with_time(self):
        t = parse_task("- [ ] Reunión (2026-03-15 09:00)")
        assert t["due"] == "2026-03-15"
        assert t["time"] == "09:00"
        assert t["ring"] is False

    def test_ring_no_recur(self):
        t = parse_task("- [ ] Llamada (2026-03-15 10:00) @ring")
        assert t["due"] == "2026-03-15"
        assert t["time"] == "10:00"
        assert t["ring"] is True
        assert t["recur"] is None

    def test_ring_with_recur(self):
        t = parse_task("- [ ] Stand-up (2026-03-15 09:00) @ring @semanal")
        assert t["ring"] is True
        assert t["recur"] == "@semanal"
        assert t["due"] == "2026-03-15"
        assert t["time"] == "09:00"

    def test_recur_without_ring(self):
        t = parse_task("- [ ] Revisión (2026-03-15) @mensual")
        assert t["ring"] is False
        assert t["recur"] == "@mensual"
        assert t["due"] == "2026-03-15"
        assert t["time"] is None

    def test_scheduled_ring(self):
        """[~] = ring already sent to Reminders.app."""
        t = parse_task("- [~] Alarma (2026-03-15 08:00) @ring")
        assert t is not None
        assert t["done"] is False
        assert t["ring"] is True
        assert t["due"] == "2026-03-15"
        assert t["time"] == "08:00"

    def test_completed(self):
        t = parse_task("- [x] Tarea terminada (2026-03-10)")
        assert t["done"] is True
        assert t["completed"] == "2026-03-10"
        assert t["description"] == "Tarea terminada"

    def test_non_task_line_returns_none(self):
        assert parse_task("## Algún heading") is None
        assert parse_task("Texto normal") is None
        assert parse_task("") is None

    def test_no_date(self):
        t = parse_task("- [ ] Tarea sin fecha")
        assert t["due"] is None
        assert t["time"] is None
        assert t["description"] == "Tarea sin fecha"


# ═══════════════════════════════════════════════════════════════════════════════
# run_task_open — add tasks to a project
# ═══════════════════════════════════════════════════════════════════════════════

class TestRunTaskOpen:

    def _read_tasks(self, env):
        lines = env["proyecto_path"].read_text().splitlines()
        in_tasks = False
        tasks = []
        for line in lines:
            if line.strip().startswith("## ") and "✅" in line:
                in_tasks = True
                continue
            if in_tasks:
                if line.startswith("## "):
                    break
                if line.strip().startswith("- ["):
                    tasks.append(line.strip())
        return tasks

    def test_add_basic_task(self, orbit_env):
        rc = run_task_open("testproj", "Analizar datos", fecha=FUTURE)
        assert rc == 0
        tasks = self._read_tasks(orbit_env)
        assert any("Analizar datos" in t for t in tasks)
        assert any(FUTURE in t for t in tasks)

    def test_add_task_no_date(self, orbit_env):
        rc = run_task_open("testproj", "Tarea sin fecha", fecha=None)
        assert rc == 0
        tasks = self._read_tasks(orbit_env)
        assert any("Tarea sin fecha" in t for t in tasks)

    def test_add_ring_task(self, orbit_env, monkeypatch):
        # Skip actual Reminders.app scheduling
        monkeypatch.setattr("core.reminders._schedule_via_applescript", lambda **kw: False)
        rc = run_task_open("testproj", "Reunión importante", fecha=FUTURE,
                           time_str="10:00", ring=True)
        assert rc == 0
        tasks = self._read_tasks(orbit_env)
        ring_tasks = [t for t in tasks if "@ring" in t]
        assert len(ring_tasks) == 1
        assert "Reunión importante" in ring_tasks[0]
        assert "10:00" in ring_tasks[0]

    def test_add_recurring_ring(self, orbit_env, monkeypatch):
        monkeypatch.setattr("core.reminders._schedule_via_applescript", lambda **kw: False)
        rc = run_task_open("testproj", "Stand-up", fecha=FUTURE,
                           time_str="09:00", ring=True, recur="semanal")
        assert rc == 0
        tasks = self._read_tasks(orbit_env)
        matching = [t for t in tasks if "Stand-up" in t]
        assert len(matching) == 1
        assert "@ring" in matching[0]
        assert "@semanal" in matching[0]

    def test_add_recurring_task_no_ring(self, orbit_env):
        rc = run_task_open("testproj", "Informe mensual", fecha=FUTURE, recur="mensual")
        assert rc == 0
        tasks = self._read_tasks(orbit_env)
        matching = [t for t in tasks if "Informe mensual" in t]
        assert len(matching) == 1
        assert "@mensual" in matching[0]
        assert "@ring" not in matching[0]

    def test_add_task_today_copies_to_diario(self, orbit_env):
        rc = run_task_open("testproj", "Tarea de hoy", fecha=TODAY)
        assert rc == 0
        diario_text = orbit_env["diario_path"].read_text()
        assert "Tarea de hoy" in diario_text

    def test_add_ring_today_copies_to_diario(self, orbit_env, monkeypatch):
        monkeypatch.setattr("core.reminders._schedule_via_applescript", lambda **kw: False)
        rc = run_task_open("testproj", "Anilla de hoy", fecha=TODAY,
                           time_str="11:00", ring=True)
        assert rc == 0
        diario_text = orbit_env["diario_path"].read_text()
        assert "Anilla de hoy" in diario_text

    def test_unknown_project_returns_error(self, orbit_env):
        rc = run_task_open("proyecto_que_no_existe", "Tarea X", fecha=FUTURE)
        assert rc != 0


# ═══════════════════════════════════════════════════════════════════════════════
# list_tasks — filtering including --ring
# ═══════════════════════════════════════════════════════════════════════════════

class TestListTasks:

    def test_list_all_includes_rings(self, orbit_env, monkeypatch, capsys):
        monkeypatch.setattr("core.reminders._schedule_via_applescript", lambda **kw: False)
        run_task_open("testproj", "Tarea normal", fecha=FUTURE)
        run_task_open("testproj", "Anilla", fecha=FUTURE, time_str="09:00", ring=True)
        rc = list_tasks(project="testproj", tipo=None, estado=None, prioridad=None,
                        fecha=None, keyword=None, output=None, ring_only=False)
        assert rc == 0
        out = capsys.readouterr().out
        assert "Tarea normal" in out
        assert "Anilla" in out
        assert "⏰" in out

    def test_list_ring_only(self, orbit_env, monkeypatch, capsys):
        monkeypatch.setattr("core.reminders._schedule_via_applescript", lambda **kw: False)
        run_task_open("testproj", "Tarea normal", fecha=FUTURE)
        run_task_open("testproj", "Solo anilla", fecha=FUTURE, time_str="09:00", ring=True)
        capsys.readouterr()  # vaciar prints de setup
        rc = list_tasks(project="testproj", tipo=None, estado=None, prioridad=None,
                        fecha=None, keyword=None, output=None, ring_only=True)
        assert rc == 0
        out = capsys.readouterr().out
        assert "Solo anilla" in out
        assert "Tarea normal" not in out
        assert "RECORDATORIOS" in out


# ═══════════════════════════════════════════════════════════════════════════════
# run_task_schedule — reschedule tasks
# ═══════════════════════════════════════════════════════════════════════════════

class TestRunTaskSchedule:

    def _add(self, desc, fecha=FUTURE, time_str=None, ring=False, recur=None):
        run_task_open("testproj", desc, fecha=fecha,
                      time_str=time_str, ring=ring, recur=recur)

    def _raw_line(self, env, desc):
        for line in env["proyecto_path"].read_text().splitlines():
            if desc.lower() in line.lower() and line.strip().startswith("- ["):
                return line.strip()
        return None

    def test_reschedule_basic_task(self, orbit_env):
        self._add("Tarea a reprogramar")
        new_date = (date.today() + timedelta(days=14)).isoformat()
        rc = run_task_schedule("testproj", "reprogramar", fecha=new_date)
        assert rc == 0
        line = self._raw_line(orbit_env, "Tarea a reprogramar")
        assert new_date in line
        assert FUTURE not in line

    def test_reschedule_preserves_ring(self, orbit_env, monkeypatch):
        monkeypatch.setattr("core.reminders._schedule_via_applescript", lambda **kw: False)
        self._add("Anilla a reprogramar", time_str="09:00", ring=True)
        new_date = (date.today() + timedelta(days=10)).isoformat()
        rc = run_task_schedule("testproj", "Anilla a reprogramar",
                               fecha=new_date, time_str="11:00")
        assert rc == 0
        line = self._raw_line(orbit_env, "Anilla a reprogramar")
        assert "@ring" in line
        assert "11:00" in line
        assert new_date in line

    def test_reschedule_preserves_recur(self, orbit_env):
        self._add("Recurrente", fecha=FUTURE, recur="semanal")
        new_date = (date.today() + timedelta(days=14)).isoformat()
        rc = run_task_schedule("testproj", "Recurrente", fecha=new_date)
        assert rc == 0
        line = self._raw_line(orbit_env, "Recurrente")
        assert "@semanal" in line
        assert new_date in line

    def test_reschedule_ring_with_new_recur(self, orbit_env, monkeypatch):
        monkeypatch.setattr("core.reminders._schedule_via_applescript", lambda **kw: False)
        self._add("Anilla recurrente", time_str="10:00", ring=True, recur="diario")
        new_date = (date.today() + timedelta(days=3)).isoformat()
        rc = run_task_schedule("testproj", "Anilla recurrente",
                               fecha=new_date, time_str="10:00", recur="semanal")
        assert rc == 0
        line = self._raw_line(orbit_env, "Anilla recurrente")
        assert "@ring" in line
        assert "@semanal" in line
        assert "@diario" not in line

    def test_reschedule_nonexistent_task(self, orbit_env):
        rc = run_task_schedule("testproj", "no existe esta tarea", fecha=FUTURE)
        assert rc != 0

    def test_reschedule_interactive_keep_recur_enter(self, orbit_env, monkeypatch):
        """Enter (vacío) en el prompt → mantiene la recurrencia."""
        self._add("Tarea recurrente keep", fecha=FUTURE, recur="semanal")
        monkeypatch.setattr("builtins.input", lambda _: "")  # Enter
        new_date = (date.today() + timedelta(days=14)).isoformat()
        rc = run_task_schedule("testproj", "Tarea recurrente keep",
                               fecha=new_date, interactive=True)
        assert rc == 0
        line = self._raw_line(orbit_env, "Tarea recurrente keep")
        assert "@semanal" in line

    def test_reschedule_interactive_remove_recur(self, orbit_env, monkeypatch):
        """'n' en el prompt → elimina la recurrencia."""
        self._add("Tarea recurrente drop", fecha=FUTURE, recur="mensual")
        monkeypatch.setattr("builtins.input", lambda _: "n")
        new_date = (date.today() + timedelta(days=14)).isoformat()
        rc = run_task_schedule("testproj", "Tarea recurrente drop",
                               fecha=new_date, interactive=True)
        assert rc == 0
        line = self._raw_line(orbit_env, "Tarea recurrente drop")
        assert "@mensual" not in line

    def test_reschedule_interactive_change_recur(self, orbit_env, monkeypatch):
        """Nueva regla en el prompt → cambia la recurrencia."""
        self._add("Tarea recurrente change", fecha=FUTURE, recur="semanal")
        monkeypatch.setattr("builtins.input", lambda _: "mensual")
        new_date = (date.today() + timedelta(days=14)).isoformat()
        rc = run_task_schedule("testproj", "Tarea recurrente change",
                               fecha=new_date, interactive=True)
        assert rc == 0
        line = self._raw_line(orbit_env, "Tarea recurrente change")
        assert "@mensual" in line
        assert "@semanal" not in line


# ═══════════════════════════════════════════════════════════════════════════════
# run_task_close — complete or advance tasks
# ═══════════════════════════════════════════════════════════════════════════════

class TestRunTaskClose:

    def _add(self, desc, fecha=FUTURE, time_str=None, ring=False, recur=None):
        run_task_open("testproj", desc, fecha=fecha,
                      time_str=time_str, ring=ring, recur=recur)

    def _raw_line(self, env, desc):
        for line in env["proyecto_path"].read_text().splitlines():
            if desc.lower() in line.lower() and line.strip().startswith("- ["):
                return line.strip()
        return None

    def test_close_basic_task(self, orbit_env):
        self._add("Tarea a cerrar")
        rc = run_task_close("testproj", "Tarea a cerrar", fecha=TODAY)
        assert rc == 0
        line = self._raw_line(orbit_env, "Tarea a cerrar")
        assert line.startswith("- [x]")
        assert TODAY in line

    def test_close_advances_recurring_task(self, orbit_env):
        self._add("Revisión semanal", recur="semanal")
        rc = run_task_close("testproj", "Revisión semanal", fecha=None)
        assert rc == 0
        line = self._raw_line(orbit_env, "Revisión semanal")
        # Should still be pending (advanced), not [x]
        assert line.startswith("- [ ]")
        assert "@semanal" in line
        # New date should be one week later
        next_week = (date.fromisoformat(FUTURE) + __import__("datetime").timedelta(weeks=1)).isoformat()
        assert next_week in line

    def test_close_advances_recurring_ring(self, orbit_env, monkeypatch):
        monkeypatch.setattr("core.reminders._schedule_via_applescript", lambda **kw: False)
        self._add("Stand-up", time_str="09:00", ring=True, recur="semanal")
        rc = run_task_close("testproj", "Stand-up", fecha=None)
        assert rc == 0
        line = self._raw_line(orbit_env, "Stand-up")
        assert line.startswith("- [ ]")
        assert "@ring" in line
        assert "@semanal" in line
        assert "09:00" in line

    def test_close_ring_without_recur(self, orbit_env, monkeypatch):
        monkeypatch.setattr("core.reminders._schedule_via_applescript", lambda **kw: False)
        self._add("Anilla única", time_str="10:00", ring=True)
        rc = run_task_close("testproj", "Anilla única", fecha=TODAY)
        assert rc == 0
        line = self._raw_line(orbit_env, "Anilla única")
        assert line.startswith("- [x]")

    def test_close_nonexistent_task(self, orbit_env):
        rc = run_task_close("testproj", "tarea inventada xyz", fecha=None)
        assert rc != 0

    def test_close_interactive_keep_recur_enter(self, orbit_env, monkeypatch):
        """Enter → avanza la fecha (mantiene recurrencia)."""
        self._add("Recurrente keep", recur="semanal")
        monkeypatch.setattr("builtins.input", lambda _: "")
        rc = run_task_close("testproj", "Recurrente keep", fecha=None, interactive=True)
        assert rc == 0
        line = self._raw_line(orbit_env, "Recurrente keep")
        assert line.startswith("- [ ]")
        assert "@semanal" in line

    def test_close_interactive_complete_with_n(self, orbit_env, monkeypatch):
        """'n' → marca como completada definitivamente."""
        self._add("Recurrente done", recur="semanal")
        monkeypatch.setattr("builtins.input", lambda _: "n")
        rc = run_task_close("testproj", "Recurrente done", fecha=TODAY, interactive=True)
        assert rc == 0
        line = self._raw_line(orbit_env, "Recurrente done")
        assert line.startswith("- [x]")


# ═══════════════════════════════════════════════════════════════════════════════
# Daily note — tasks with today's date appear in diario
# ═══════════════════════════════════════════════════════════════════════════════

class TestDiarioIntegration:

    def test_task_today_appears_in_diario(self, orbit_env):
        run_task_open("testproj", "Tarea del día", fecha=TODAY)
        diario_text = orbit_env["diario_path"].read_text()
        assert "Tarea del día" in diario_text

    def test_task_future_not_in_diario(self, orbit_env):
        run_task_open("testproj", "Tarea futura única", fecha=FUTURE)
        diario_text = orbit_env["diario_path"].read_text()
        assert "Tarea futura única" not in diario_text

    def test_ring_today_appears_in_diario(self, orbit_env, monkeypatch):
        monkeypatch.setattr("core.reminders._schedule_via_applescript", lambda **kw: False)
        run_task_open("testproj", "Anilla del día", fecha=TODAY,
                      time_str="10:00", ring=True)
        diario_text = orbit_env["diario_path"].read_text()
        assert "Anilla del día" in diario_text

    def test_task_in_diario_under_tasks_section(self, orbit_env):
        run_task_open("testproj", "Tarea en sección correcta", fecha=TODAY)
        lines = orbit_env["diario_path"].read_text().splitlines()
        in_tasks = False
        found = False
        for line in lines:
            if line.strip().startswith("## ✅"):
                in_tasks = True
                continue
            if in_tasks and line.startswith("## "):
                break
            if in_tasks and "Tarea en sección correcta" in line:
                found = True
                break
        assert found, "La tarea debe aparecer bajo ## ✅ Tareas del día"

    def test_multiple_tasks_today_all_in_diario(self, orbit_env):
        run_task_open("testproj", "Primera tarea hoy", fecha=TODAY)
        run_task_open("testproj", "Segunda tarea hoy", fecha=TODAY)
        diario_text = orbit_env["diario_path"].read_text()
        assert "Primera tarea hoy" in diario_text
        assert "Segunda tarea hoy" in diario_text

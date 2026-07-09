"""Tests for the unified new-format serializer/parser (core.agenda.newfmt)
and the tolerant reader dispatch in core.agenda.io (transition F0).

The new format is the "orbit-item" grammar (design claude/designs/
items_unified.md): header + indented body, ▶️ dates, ✏️ tasks, primary tags,
followups ⏩, someday = no temporal line. These tests pin:
  * serialize↔parse idempotency on canonical text (with and without the
    invisible orbit-id comment);
  * old-model → new → model preservation of the *carried* fields (the
    grammar deliberately drops ff/snooze/failed and folds ff → ⏩ followup);
  * the tolerant reader: legacy files route to the legacy parser, new files
    to the new parser, both yielding the same model shape.
"""
from pathlib import Path

from core.agenda.newfmt import serialize_agenda_new, parse_agenda_new
from core.agenda.io import _read_agenda, _is_new_format


CANONICAL = """# Agenda — 🔬research

- [ ] ✏️ Informe justificativo final #tarea
    ▶️ 2026-07-30 · ⏰ 12:00 · 🔔 -5m
    ⏩ 2026-07-28 Pedir feedback a María

- [ ] ✏️ Aprender Rust #tarea
    Cuando haya tiempo, empezar por el book.

- [x] ✏️ Preparar evaluación semanal #tarea
    ▶️ 2026-07-06 · 🔄 weekly

- [ ] 🏁 Portfolio estabilizado #hitos
    ▶️ 2026-08-01

- 📅 CM (Canfranc) #evento
    ▶️ 2026-09-25 : 2026-09-28 · ⏰ 09:00-16:00 · 🔔 1d
    links: [📹](https://cern.zoom.us/j/123) [📋](https://next.ific.uv.es/agenda)
    ⏩ 2026-09-11 deadline inscripción

- 💬 Felicitar a Ana por el cumple #recordatorio
    ▶️ 2026-08-03 · ⏰ 09:00 · 🔄 monthly
"""


class TestIdempotency:

    def test_serialize_parse_is_identity(self):
        assert serialize_agenda_new(parse_agenda_new(CANONICAL)) == CANONICAL

    def test_orbit_id_survives_when_enabled(self):
        text = ("- [ ] ✏️ Con id #tarea <!-- orbit:a1b2c3d4 -->\n"
                "    ▶️ 2026-07-30\n")
        data = parse_agenda_new(text)
        assert data["tasks"][0]["orbit_id"] == "a1b2c3d4"
        assert serialize_agenda_new(data, with_id=True) == text

    def test_orbit_id_hidden_by_default(self):
        item = {"desc": "X", "status": "pending", "orbit_id": "deadbeef",
                "date": "2026-07-30", "notes": []}
        data = {"header": ["# A"], "tasks": [item], "milestones": [],
                "events": [], "reminders": [], "cronos": []}
        assert "orbit:" not in serialize_agenda_new(data)          # viewer
        assert "orbit:deadbeef" in serialize_agenda_new(data, with_id=True)


class TestHeaderShapes:

    def _first(self, kind_key, text):
        return parse_agenda_new(text)[kind_key][0]

    def test_task_has_pencil_no_check(self):
        t = self._first("tasks", "- [ ] ✏️ Tarea #tarea\n")
        assert t["status"] == "pending" and t["desc"] == "Tarea"

    def test_task_done_and_cancelled(self):
        assert self._first("tasks", "- [x] ✏️ T #tarea\n")["status"] == "done"
        assert self._first("tasks", "- [-] ✏️ T #tarea\n")["status"] == "cancelled"

    def test_milestone_event_reminder(self):
        assert self._first("milestones", "- [ ] 🏁 M #hitos\n")["desc"] == "M"
        assert self._first("events", "- 📅 E #evento\n")["desc"] == "E"
        r = self._first("reminders", "- [-] 💬 R #recordatorio\n")
        assert r["desc"] == "R" and r["cancelled"] is True

    def test_title_with_wikilink_and_dot(self):
        # real mission case: emoji-carril + [[wikilink]] + '·' inside title
        t = self._first("tasks", "- [x] ✏️ ⚓ [[catedra]] · focus 2026-W21 #tarea\n"
                                 "    ▶️ 2026-05-19 · ⏰ 09:00-10:30\n")
        assert t["desc"] == "⚓ [[catedra]] · focus 2026-W21"
        assert t["date"] == "2026-05-19" and t["time"] == "09:00-10:30"


class TestSemanticPreservationOldToNew:

    def _old(self):
        return {
            "header": ["# Agenda — test"],
            "tasks": [
                {"desc": "Informe", "status": "pending", "date": "2026-07-30",
                 "time": "12:00", "recur": None, "until": None, "ring": "-5m",
                 "ff": None, "snooze_count": 3, "failed_count": 1,
                 "orbit_id": "aaaa1111", "notes": ["⏩ 2026-07-28 feedback"]},
                {"desc": "Pending con ff", "status": "pending", "date": None,
                 "time": None, "recur": None, "until": None, "ring": None,
                 "ff": "2026-07-10", "snooze_count": 0, "failed_count": 0,
                 "orbit_id": None, "notes": []},
            ],
            "milestones": [
                {"desc": "Beta", "status": "done", "date": "2026-08-01",
                 "time": None, "recur": "monthly", "until": "2026-12-01",
                 "ring": None, "ff": None, "orbit_id": None, "notes": []},
            ],
            "events": [
                {"desc": "Congreso", "date": "2026-09-25", "end": "2026-09-28",
                 "time": "09:00-16:00", "recur": None, "until": None, "ring": "1d",
                 "orbit_id": "bbbb2222",
                 "notes": ["📋 https://a.example/ag", "🚪 https://zoom.example/x"]},
            ],
            "reminders": [
                {"desc": "Cumple", "cancelled": False, "date": "2026-08-03",
                 "time": "09:00", "recur": "monthly", "until": None, "notes": []},
            ],
            "cronos": [],
        }

    def test_carried_fields_survive(self):
        back = parse_agenda_new(serialize_agenda_new(self._old()))
        t = back["tasks"][0]
        assert (t["desc"], t["status"], t["date"], t["time"], t["ring"]) == \
               ("Informe", "pending", "2026-07-30", "12:00", "-5m")
        ms = back["milestones"][0]
        assert (ms["status"], ms["recur"], ms["until"]) == ("done", "monthly", "2026-12-01")
        ev = back["events"][0]
        assert (ev["date"], ev["end"], ev["time"], ev["ring"]) == \
               ("2026-09-25", "2026-09-28", "09:00-16:00", "1d")

    def test_ff_folds_into_followup(self):
        back = parse_agenda_new(serialize_agenda_new(self._old()))
        assert back["tasks"][1]["ff"] is None
        assert "⏩ 2026-07-10" in back["tasks"][1]["notes"]

    def test_someday_has_no_temporal_line(self):
        back = parse_agenda_new(serialize_agenda_new(self._old()))
        assert back["tasks"][1]["date"] is None

    def test_refs_and_followups_survive(self):
        back = parse_agenda_new(serialize_agenda_new(self._old()))
        ev_notes = back["events"][0]["notes"]
        assert "📋 https://a.example/ag" in ev_notes      # agenda ref preserved
        assert "🚪 https://zoom.example/x" in ev_notes     # room ref preserved
        assert "⏩ 2026-07-28 feedback" in back["tasks"][0]["notes"]

    def test_dropped_counters_are_gone(self):
        back = parse_agenda_new(serialize_agenda_new(self._old()))
        assert back["tasks"][0]["snooze_count"] == 0
        assert back["tasks"][0]["failed_count"] == 0


class TestTolerantReader:

    def test_detects_new_vs_old(self):
        assert _is_new_format("- [ ] ✏️ X #tarea\n") is True
        assert _is_new_format("## ✅ Tareas\n- [ ] X (2026-01-01)\n") is False
        assert _is_new_format("## 📊 Cronogramas\n| barra |\n") is False

    def test_section_headers_inside_comment_dont_misclassify(self):
        """A migrated agenda keeps the bootstrap 'Secciones disponibles' comment,
        which lists `## ✅ Tareas` etc. as text. The detector must match a header
        only as a full line, or the file reads as legacy and its items are lost."""
        migrated = (
            "# Agenda — x\n"
            "<!-- Secciones disponibles:\n"
            "     ## ✅ Tareas        — acciones\n"
            "     ## 🏁 Hitos         — objetivos\n"
            "     ## 📅 Eventos       — reuniones\n"
            "     ## 💬 Recordatorios — avisos -->\n\n"
            "- [x] 🏁 hito #hitos <!-- orbit:4a96266a -->\n"
            "    ▶️ 2026-04-19 · ⏰ 17:00\n"
        )
        assert _is_new_format(migrated) is True
        import tempfile, pathlib
        p = pathlib.Path(tempfile.mkdtemp()) / "agenda.md"
        p.write_text(migrated)
        data = _read_agenda(p)
        assert len(data["milestones"]) == 1        # parsed by the NEW parser
        assert data["milestones"][0]["desc"] == "hito"
        assert data["milestones"][0]["orbit_id"] == "4a96266a"

    def test_reads_new_format_file(self, tmp_path):
        p = tmp_path / "agenda.md"
        p.write_text(CANONICAL)
        data = _read_agenda(p)
        assert len(data["tasks"]) == 3
        assert data["events"][0]["desc"] == "CM (Canfranc)"
        assert data["reminders"][0]["recur"] == "monthly"

    def test_reads_legacy_format_file(self, tmp_path):
        p = tmp_path / "agenda.md"
        p.write_text("# Agenda — x\n\n## ✅ Tareas\n"
                     "- [ ] Vieja (2026-01-01) 🔔5m [orbit:12345678]\n")
        data = _read_agenda(p)
        assert data["tasks"][0]["desc"] == "Vieja"
        assert data["tasks"][0]["orbit_id"] == "12345678"

    def test_new_format_model_shape_matches_legacy(self, tmp_path):
        """A new-format task dict carries the same keys downstream code reads."""
        p = tmp_path / "agenda.md"
        p.write_text("- [ ] ✏️ X #tarea\n    ▶️ 2026-07-30\n")
        t = _read_agenda(p)["tasks"][0]
        for k in ("desc", "date", "time", "recur", "until", "ring",
                  "status", "ff", "snooze_count", "failed_count",
                  "orbit_id", "cloud_verified", "notes"):
            assert k in t


class TestAgendaFutureCommand:

    def test_writes_derived_view_without_touching_truth(self, orbit_env, monkeypatch):
        from core.log import resolve_file
        from core import agenda_view
        proj = orbit_env["proj_dir"]
        agenda = resolve_file(proj, "agenda")
        agenda.write_text("# Agenda — testproj\n\n## ✅ Tareas\n"
                          "- [ ] Hacer algo (2026-07-30) ⏰12:00 [orbit:12345678]\n")

        # project-name resolution is tested elsewhere; isolate the write logic.
        monkeypatch.setattr(agenda_view, "_resolve_dirs",
                            lambda projects, include_federated=True: [proj])
        rc = agenda_view.run_agenda_future(["testproj"])
        assert rc == 0

        futura = agenda.parent / (agenda.stem + "_futura.md")
        assert futura.exists()
        text = futura.read_text()
        assert "- [ ] ✏️ Hacer algo #tarea" in text
        assert "▶️ 2026-07-30 · ⏰ 12:00" in text
        assert "orbit:" not in text                 # id hidden in the viewer
        assert "## ✅ Tareas" in agenda.read_text()  # truth untouched


class TestAgendaMigrateCommand:

    def test_migrates_truth_and_folds_ff(self, orbit_env, monkeypatch):
        from core.log import resolve_file
        from core import agenda_view
        proj = orbit_env["proj_dir"]
        agenda = resolve_file(proj, "agenda")
        agenda.write_text(
            "# Agenda — testproj\n\n## ✅ Tareas\n"
            "- [ ] Revisar informe ⏩2026-07-09\n\n"
            "## 📊 Cronogramas\n\n"
            "| Cronograma | Progreso |   | Deadline |\n"
            "|------------|----------|---|----------|\n"
            "| [p](cronos/crono-p.md) | ██ | 1/2 | — |\n"
        )
        monkeypatch.setattr(agenda_view, "_resolve_dirs",
                            lambda projects, include_federated=True: [proj])
        rc = agenda_view.run_agenda_migrate(["testproj"])
        assert rc == 0
        text = agenda.read_text()
        # truth rewritten to the new format
        assert "## ✅ Tareas" not in text
        assert "- [ ] ✏️ Revisar informe #tarea" in text
        assert "⏩ 2026-07-09" in text                # ff folded to body followup
        assert "## 📊 Cronogramas" not in text        # embedded table dropped
        # ...and the followup now surfaces via item_followups (Decidir hoy).
        from core.agenda_cmds import _read_agenda
        from core.agenda.display import item_followups
        task = _read_agenda(agenda)["tasks"][0]
        assert task.get("ff") is None
        assert item_followups(task) == [{"date": "2026-07-09", "desc": None}]

    def test_idempotent_skips_new_format(self, orbit_env, monkeypatch):
        from core.log import resolve_file
        from core import agenda_view
        proj = orbit_env["proj_dir"]
        agenda = resolve_file(proj, "agenda")
        agenda.write_text(
            "# Agenda — testproj\n\n- [ ] ✏️ Ya migrada #tarea\n")
        before = agenda.read_text()
        monkeypatch.setattr(agenda_view, "_resolve_dirs",
                            lambda projects, include_federated=True: [proj])
        rc = agenda_view.run_agenda_migrate(["testproj"])
        assert rc == 0
        assert agenda.read_text() == before          # already-new file untouched

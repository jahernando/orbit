"""Tests for core/ics_share.py — export and import of single-VEVENT .ics."""
from __future__ import annotations

import pytest
from pathlib import Path

from core import ics_share
from core.ics_share import (
    parse_first_vevent, _is_meeting_url, _strip_orbit_tag,
    _strip_orbit_summary_prefix, _props_to_orbit_item, _detect_kind,
    _next_occurrence_for_export, run_ics_share, run_ics_import,
)


class TestStripOrbitSummaryPrefix:
    def test_event_prefix(self):
        assert _strip_orbit_summary_prefix("[phd-diego] Project kickoff") == "Project kickoff"

    def test_task_with_emoji(self):
        assert _strip_orbit_summary_prefix("[proj] ✅ Write paper", "✅") == "Write paper"

    def test_milestone(self):
        assert _strip_orbit_summary_prefix("[proj] 🏁 Deadline", "🏁") == "Deadline"

    def test_no_prefix_passthrough(self):
        assert _strip_orbit_summary_prefix("Plain title") == "Plain title"

    def test_emoji_default_detection(self):
        # No kind hint given but a known emoji is present.
        assert _strip_orbit_summary_prefix("[proj] 💬 Llamar") == "Llamar"


# ── Low-level helpers ────────────────────────────────────────────────────────

class TestStripOrbitTag:
    def test_basic(self):
        assert _strip_orbit_tag("Proyecto: x\n[orbit:abcd1234]") == "Proyecto: x"

    def test_inline(self):
        # The tag and its surrounding spaces are removed.
        assert _strip_orbit_tag("Hola [orbit:deadbeef] mundo") == "Holamundo"

    def test_preserves_newlines(self):
        # Newlines around the tag survive so per-line processing works.
        result = _strip_orbit_tag("First line\n[orbit:abc12345]\nSecond line")
        assert "First line" in result
        assert "Second line" in result
        assert "[orbit:" not in result

    def test_empty(self):
        assert _strip_orbit_tag("") == ""


class TestIsMeetingUrl:
    def test_zoom(self):
        assert _is_meeting_url("https://zoom.us/j/123")

    def test_meet(self):
        assert _is_meeting_url("https://meet.google.com/abc-defg-hij")

    def test_teams(self):
        assert _is_meeting_url("https://teams.microsoft.com/l/meetup-join/...")

    def test_indico(self):
        assert _is_meeting_url("https://indico.cern.ch/event/12345")

    def test_plain_text_room(self):
        assert not _is_meeting_url("Aula A1-01")

    def test_random_url(self):
        assert not _is_meeting_url("https://example.com/page")


# ── VEVENT parser ────────────────────────────────────────────────────────────

class TestParseFirstVevent:
    def test_basic_event(self):
        ics = (
            "BEGIN:VCALENDAR\r\nVERSION:2.0\r\n"
            "BEGIN:VEVENT\r\n"
            "UID:abc@orbit\r\n"
            "SUMMARY:Test meeting\r\n"
            "DTSTART:20260515T100000\r\n"
            "DTEND:20260515T110000\r\n"
            "END:VEVENT\r\nEND:VCALENDAR\r\n"
        )
        props, warnings = parse_first_vevent(ics)
        assert props is not None
        assert props["summary"] == "Test meeting"
        assert props["start_date"] == "2026-05-15"
        assert props["start_time"] == "10:00"
        assert props["end_date"] == "2026-05-15"
        assert props["end_time"] == "11:00"
        assert not props.get("all_day")
        assert warnings == []

    def test_all_day_value_date(self):
        ics = (
            "BEGIN:VEVENT\r\n"
            "SUMMARY:Holiday\r\n"
            "DTSTART;VALUE=DATE:20260515\r\n"
            "DTEND;VALUE=DATE:20260516\r\n"
            "END:VEVENT\r\n"
        )
        props, warnings = parse_first_vevent(ics)
        assert props["all_day"] is True
        assert props["start_date"] == "2026-05-15"
        assert props["start_time"] is None

    def test_rrule_warns(self):
        ics = (
            "BEGIN:VEVENT\r\n"
            "SUMMARY:Weekly\r\n"
            "DTSTART:20260515T100000\r\n"
            "RRULE:FREQ=WEEKLY\r\n"
            "END:VEVENT\r\n"
        )
        props, warnings = parse_first_vevent(ics)
        assert props["rrule"] == "FREQ=WEEKLY"
        assert any("RRULE" in w for w in warnings)

    def test_multi_vevent_warns_and_takes_first(self):
        ics = (
            "BEGIN:VEVENT\r\nSUMMARY:First\r\nDTSTART:20260101T100000\r\nEND:VEVENT\r\n"
            "BEGIN:VEVENT\r\nSUMMARY:Second\r\nDTSTART:20260102T100000\r\nEND:VEVENT\r\n"
        )
        props, warnings = parse_first_vevent(ics)
        assert props["summary"] == "First"
        assert any("2 VEVENT" in w for w in warnings)

    def test_no_vevent_returns_none(self):
        props, warnings = parse_first_vevent("BEGIN:VCALENDAR\r\nEND:VCALENDAR\r\n")
        assert props is None
        assert warnings

    def test_x_orbit_kind_captured(self):
        ics = (
            "BEGIN:VEVENT\r\nSUMMARY:T\r\nDTSTART:20260515T100000\r\n"
            "X-ORBIT-KIND:task\r\nX-ORBIT-ID:abc12345\r\nEND:VEVENT\r\n"
        )
        props, _ = parse_first_vevent(ics)
        assert props["x_orbit_kind"] == "task"
        assert props["x_orbit_id"] == "abc12345"

    def test_valarm_minutes(self):
        ics = (
            "BEGIN:VEVENT\r\nSUMMARY:T\r\nDTSTART:20260515T100000\r\n"
            "BEGIN:VALARM\r\nACTION:DISPLAY\r\nTRIGGER:-PT15M\r\nEND:VALARM\r\n"
            "END:VEVENT\r\n"
        )
        props, _ = parse_first_vevent(ics)
        assert props["valarm_minutes"] == 15

    def test_unfolds_continuation(self):
        # RFC 5545 line folding: continuation line starts with space.
        ics = (
            "BEGIN:VEVENT\r\nSUMMARY:Long\r\n title here\r\n"
            "DTSTART:20260515T100000\r\nEND:VEVENT\r\n"
        )
        props, _ = parse_first_vevent(ics)
        assert props["summary"] == "Longtitle here"

    def test_url_and_location(self):
        ics = (
            "BEGIN:VEVENT\r\nSUMMARY:Meet\r\nDTSTART:20260515T100000\r\n"
            "URL:https://zoom.us/j/9999\r\n"
            "LOCATION:https://zoom.us/j/9999\r\nEND:VEVENT\r\n"
        )
        props, _ = parse_first_vevent(ics)
        assert props["url"] == "https://zoom.us/j/9999"
        assert props["location"] == "https://zoom.us/j/9999"


# ── Kind detection ───────────────────────────────────────────────────────────

class TestDetectKind:
    def test_x_orbit_kind_wins(self):
        assert _detect_kind({"x_orbit_kind": "task"}, []) == "task"
        assert _detect_kind({"x_orbit_kind": "milestone"}, []) == "milestone"

    def test_cronograma_demoted_to_event_with_warning(self):
        warnings = []
        kind = _detect_kind({"x_orbit_kind": "cronograma"}, warnings)
        assert kind == "event"
        assert warnings

    def test_all_day_is_event(self):
        assert _detect_kind({"dtstart_is_date": True}, []) == "event"

    def test_time_range_is_event(self):
        assert _detect_kind({
            "dtstart": "20260515T100000",
            "dtend":   "20260515T110000",
        }, []) == "event"

    def test_ambiguous_non_tty_defaults_event(self, monkeypatch):
        monkeypatch.setattr("sys.stdin.isatty", lambda: False)
        warnings = []
        kind = _detect_kind({"dtstart": "20260515T100000"}, warnings)
        assert kind == "event"
        assert any("ambig" in w.lower() for w in warnings)


# ── Item builder ─────────────────────────────────────────────────────────────

class TestPropsToOrbitItem:
    def _base_props(self, **over):
        p = {
            "summary":   "T",
            "start_date": "2026-05-15",
            "start_time": "10:00",
            "end_date":   "2026-05-15",
            "end_time":   "10:00",
            "all_day":    False,
        }
        p.update(over)
        return p

    def test_task_basic(self):
        item, warnings = _props_to_orbit_item(self._base_props(), "task")
        assert item["desc"] == "T"
        assert item["date"] == "2026-05-15"
        assert item["time"] == "10:00"
        assert item["status"] == "pending"
        assert item["orbit_id"]
        assert len(item["orbit_id"]) == 8   # hex

    def test_event_with_range(self):
        props = self._base_props(end_time="11:30")
        item, _ = _props_to_orbit_item(props, "event")
        assert item["time"] == "10:00-11:30"

    def test_event_all_day_single(self):
        props = self._base_props(start_date="2026-05-15", end_date="2026-05-16",
                                 start_time=None, end_time=None, all_day=True)
        item, _ = _props_to_orbit_item(props, "event")
        assert item["time"] is None
        # Single-day all-day: end-1 == start → no `end` set.
        assert item.get("end") is None

    def test_event_all_day_multi(self):
        # DTEND is exclusive for VALUE=DATE; orbit's `end` is inclusive.
        props = self._base_props(start_date="2026-05-15", end_date="2026-05-18",
                                 start_time=None, end_time=None, all_day=True)
        item, _ = _props_to_orbit_item(props, "event")
        assert item["time"] is None
        assert item["end"] == "2026-05-17"

    def test_notes_strip_orbit_tag_and_proyecto(self):
        props = self._base_props(description="Proyecto: foo\n[orbit:abc12345]\nReal note")
        item, _ = _props_to_orbit_item(props, "task")
        # The "Proyecto:" line is dropped (orbit's own export marker);
        # the [orbit:xxx] tag is stripped; only "Real note" remains.
        assert item["notes"] == ["Real note"]

    def test_meeting_url_becomes_door_note(self):
        props = self._base_props(url="https://zoom.us/j/9999")
        item, _ = _props_to_orbit_item(props, "event")
        assert "🚪 https://zoom.us/j/9999" in item["notes"]

    def test_valarm_to_ring(self):
        props = self._base_props()
        props["valarm_minutes"] = 15
        item, _ = _props_to_orbit_item(props, "event")
        assert item["ring"] == "15m"

    def test_valarm_60_to_1h(self):
        props = self._base_props()
        props["valarm_minutes"] = 60
        item, _ = _props_to_orbit_item(props, "event")
        assert item["ring"] == "1h"

    def test_non_madrid_tz_warns(self):
        props = self._base_props(tzid="America/New_York")
        _, warnings = _props_to_orbit_item(props, "event")
        assert any("TZID" in w for w in warnings)


# ── Next occurrence for export ───────────────────────────────────────────────

class TestNextOccurrenceForExport:
    def test_non_recurring_returns_date(self):
        item = {"date": "2026-05-15"}
        assert _next_occurrence_for_export(item) == "2026-05-15"

    def test_recurring_past_advances_to_today_or_later(self, monkeypatch):
        from datetime import date
        # Pin "today" to 2026-05-20 (Wednesday).
        class FakeDate(date):
            @classmethod
            def today(cls):
                return date(2026, 5, 20)
        monkeypatch.setattr("core.ics_share._date", FakeDate)
        item = {"date": "2026-05-15", "recur": "weekly"}
        out = _next_occurrence_for_export(item)
        # next weekly after 2026-05-15 ≥ today (2026-05-20) is 2026-05-22.
        assert out == "2026-05-22"

    def test_recurring_expired_returns_none(self, monkeypatch):
        from datetime import date
        class FakeDate(date):
            @classmethod
            def today(cls):
                return date(2027, 1, 1)
        monkeypatch.setattr("core.ics_share._date", FakeDate)
        item = {"date": "2026-05-15", "recur": "weekly", "until": "2026-06-01"}
        assert _next_occurrence_for_export(item) is None


# ── End-to-end share + import (with workspace) ───────────────────────────────

class TestShareAndImportRoundTrip:
    def _agenda(self, proj: Path, content: str):
        agenda_path = proj / f"{proj.name}-agenda.md"
        agenda_path.write_text(content)
        return agenda_path

    def _stub_project(self, tmp_path, monkeypatch):
        proj = tmp_path / "💻testproj"
        proj.mkdir()
        monkeypatch.setattr("core.ics_share.find_project", lambda name: proj)
        monkeypatch.setattr("core.ics_share.resolve_file",
                             lambda pd, kind: pd / f"{pd.name}-agenda.md")
        return proj

    def test_share_by_orbit_id(self, tmp_path, monkeypatch):
        proj = self._stub_project(tmp_path, monkeypatch)
        self._agenda(proj,
            "# Agenda\n\n## 📅 Eventos\n\n"
            "2026-05-20 — Project kickoff ⏰10:00 [orbit:abc12345]\n"
        )
        out = tmp_path / "share.ics"
        rc = run_ics_share("💻testproj", orbit_id="abc12345", out=str(out))
        assert rc == 0
        text = out.read_text()
        assert "BEGIN:VCALENDAR" in text
        assert "BEGIN:VEVENT" in text
        assert "SUMMARY:[💻testproj] Project kickoff" in text
        assert "X-ORBIT-ID:abc12345" in text

    def test_share_unknown_orbit_id_fails(self, tmp_path, monkeypatch, capsys):
        self._stub_project(tmp_path, monkeypatch)
        proj = tmp_path / "💻testproj"
        self._agenda(proj, "# Agenda\n\n## 📅 Eventos\n\n")
        rc = run_ics_share("💻testproj", orbit_id="00000000")
        assert rc == 1
        assert "no se encontró" in capsys.readouterr().out.lower()

    def test_import_basic_event(self, tmp_path, monkeypatch):
        proj = self._stub_project(tmp_path, monkeypatch)
        agenda = self._agenda(proj, "# Agenda\n\n## 📅 Eventos\n\n")
        # Suppress interactive confirm prompt.
        monkeypatch.setattr("sys.stdin.isatty", lambda: False)
        # Skip ics regen on import (no cloud_root in tmp).
        monkeypatch.setattr("core.ics_share.write_workspace",
                             lambda root, project_filter=None: 0)
        monkeypatch.setattr("core.deliver._find_cloud_root", lambda: None)

        ics_path = tmp_path / "in.ics"
        ics_path.write_text(
            "BEGIN:VCALENDAR\r\nVERSION:2.0\r\n"
            "BEGIN:VEVENT\r\nUID:foo@x\r\nSUMMARY:Imported meet\r\n"
            "DTSTART:20260601T140000\r\nDTEND:20260601T150000\r\n"
            "X-ORBIT-KIND:event\r\n"
            "END:VEVENT\r\nEND:VCALENDAR\r\n"
        )
        rc = run_ics_import("💻testproj", path=str(ics_path))
        assert rc == 0
        text = agenda.read_text()
        assert "Imported meet" in text
        assert "2026-06-01" in text
        assert "10:00" not in text  # the time was 14:00, not the default
        assert "14:00" in text

    def test_import_round_trip(self, tmp_path, monkeypatch):
        """Export and re-import — desc/date/time should survive."""
        proj = self._stub_project(tmp_path, monkeypatch)
        self._agenda(proj,
            "# Agenda\n\n## 📅 Eventos\n\n"
            "2026-05-20 — Kickoff ⏰10:00-11:30 [orbit:abc12345]\n"
        )
        share_out = tmp_path / "rt.ics"
        assert run_ics_share("💻testproj", orbit_id="abc12345",
                              out=str(share_out)) == 0

        # Switch to a fresh project for re-import.
        proj2 = tmp_path / "💻target"
        proj2.mkdir()
        agenda2 = proj2 / f"{proj2.name}-agenda.md"
        agenda2.write_text("# Agenda\n\n## 📅 Eventos\n\n")
        monkeypatch.setattr("core.ics_share.find_project", lambda name: proj2)
        monkeypatch.setattr("core.ics_share.resolve_file",
                             lambda pd, kind: agenda2)
        monkeypatch.setattr("sys.stdin.isatty", lambda: False)
        monkeypatch.setattr("core.ics_share.write_workspace",
                             lambda root, project_filter=None: 0)
        monkeypatch.setattr("core.deliver._find_cloud_root", lambda: None)

        assert run_ics_import("💻target", path=str(share_out)) == 0
        text = agenda2.read_text()
        assert "Kickoff" in text
        assert "2026-05-20" in text
        assert "10:00-11:30" in text

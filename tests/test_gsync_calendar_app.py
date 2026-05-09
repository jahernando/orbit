"""Tests for the Calendar.app (AppleScript) backend in core/gsync.py."""

import json
import pytest
from unittest.mock import patch

from core import gsync


# ── Helpers ───────────────────────────────────────────────────────────────────

class TestEsc:
    def test_passes_plain_text(self):
        assert gsync._esc("hello") == "hello"

    def test_escapes_quotes(self):
        assert gsync._esc('say "hi"') == 'say \\"hi\\"'

    def test_escapes_backslashes(self):
        assert gsync._esc("a\\b") == "a\\\\b"

    def test_escapes_newlines(self):
        assert gsync._esc("a\nb") == "a\\nb"

    def test_handles_none(self):
        assert gsync._esc(None) == ""


class TestBuildDateVar:
    def test_iso_with_time(self):
        s = gsync._build_date_var("d", "2030-05-15T12:30")
        assert "set d to current date" in s
        assert "set year of d to 2030" in s
        assert "set month of d to 5" in s
        assert "set day of d to 15" in s
        assert "set hours of d to 12" in s
        assert "set minutes of d to 30" in s

    def test_iso_date_only_uses_zero_time(self):
        s = gsync._build_date_var("d", "2030-05-15")
        assert "set hours of d to 0" in s
        assert "set minutes of d to 0" in s


# ── _osa wrapper ─────────────────────────────────────────────────────────────

class TestOsa:
    def test_returns_stdout_on_success(self, monkeypatch):
        class FakeRun:
            returncode = 0
            stdout = "  hello world  \n"
            stderr = ""
        def fake_run(*args, **kwargs):
            return FakeRun()
        monkeypatch.setattr(gsync.subprocess, "run", fake_run)
        assert gsync._osa("dummy") == "hello world"

    def test_returns_none_on_nonzero(self, monkeypatch):
        class FakeRun:
            returncode = 1
            stdout = ""
            stderr = "error"
        monkeypatch.setattr(gsync.subprocess, "run", lambda *a, **k: FakeRun())
        assert gsync._osa("dummy") is None


# ── Calendar.app event helpers ───────────────────────────────────────────────

class TestCreateCalendarEvent:
    def test_builds_basic_script(self, monkeypatch):
        captured = {}
        def fake_osa(script, **k):
            captured["script"] = script
            return "UID-123"
        monkeypatch.setattr(gsync, "_osa", fake_osa)
        uid = gsync._create_calendar_event("🌿 orbit-ps", {
            "summary":   "Test event",
            "start_iso": "2030-05-15T12:00",
            "end_iso":   "2030-05-15T13:00",
        })
        assert uid == "UID-123"
        s = captured["script"]
        assert 'tell calendar "🌿 orbit-ps"' in s
        assert 'summary:"Test event"' in s
        assert "make new event with properties" in s

    def test_includes_optional_props(self, monkeypatch):
        captured = {}
        def fake_osa(script, **k):
            captured["script"] = script
            return "UID-X"
        monkeypatch.setattr(gsync, "_osa", fake_osa)
        gsync._create_calendar_event("Cal", {
            "summary":     "S",
            "start_iso":   "2030-01-01T10:00",
            "end_iso":     "2030-01-01T11:00",
            "description": "Desc",
            "location":    "Aula 7",
            "url":         "https://zoom/x",
            "rrule":       "FREQ=WEEKLY",
        })
        s = captured["script"]
        assert 'set description of newEv to "Desc"' in s
        assert 'set location of newEv to "Aula 7"' in s
        assert 'set url of newEv to "https://zoom/x"' in s
        assert 'set recurrence of newEv to "FREQ=WEEKLY"' in s

    def test_escapes_quotes_in_summary(self, monkeypatch):
        captured = {}
        monkeypatch.setattr(gsync, "_osa",
                            lambda s, **k: (captured.setdefault("s", s), "U")[1])
        gsync._create_calendar_event("Cal", {
            "summary":   'Re: "topic"',
            "start_iso": "2030-01-01T10:00",
            "end_iso":   "2030-01-01T11:00",
        })
        # The double-quotes inside summary got escaped
        assert 'summary:"Re: \\"topic\\""' in captured["s"]


class TestUpdateCalendarEvent:
    def test_returns_true_on_ok(self, monkeypatch):
        monkeypatch.setattr(gsync, "_osa", lambda s, **k: "ok")
        assert gsync._update_calendar_event("UID", "Cal", {
            "summary":   "X", "start_iso": "2030-01-01T10:00",
            "end_iso":   "2030-01-01T11:00",
        }) is True

    def test_returns_false_on_missing(self, monkeypatch):
        monkeypatch.setattr(gsync, "_osa", lambda s, **k: "missing")
        assert gsync._update_calendar_event("UID", "Cal", {
            "summary":   "X", "start_iso": "2030-01-01T10:00",
            "end_iso":   "2030-01-01T11:00",
        }) is False

    def test_returns_false_on_osa_error(self, monkeypatch):
        monkeypatch.setattr(gsync, "_osa", lambda s, **k: None)
        assert gsync._update_calendar_event("UID", "Cal", {
            "summary":   "X", "start_iso": "2030-01-01T10:00",
            "end_iso":   "2030-01-01T11:00",
        }) is False


class TestDeleteCalendarEvent:
    def test_ok(self, monkeypatch):
        monkeypatch.setattr(gsync, "_osa", lambda s, **k: "ok")
        assert gsync._delete_calendar_event("UID", "Cal") is True

    def test_missing_treated_as_success(self, monkeypatch):
        """Already-absent event is fine — idempotent delete."""
        monkeypatch.setattr(gsync, "_osa", lambda s, **k: "missing")
        assert gsync._delete_calendar_event("UID", "Cal") is True

    def test_osa_error(self, monkeypatch):
        monkeypatch.setattr(gsync, "_osa", lambda s, **k: None)
        assert gsync._delete_calendar_event("UID", "Cal") is False


# ── _ev_props_for_calendar_app ──────────────────────────────────────────────

class TestEvPropsForCalendarApp:
    def test_timed_event_with_end_time(self):
        ev = {"desc": "Mtg", "date": "2030-05-15",
              "time": "12:00-13:00"}
        p = gsync._ev_props_for_calendar_app(ev, "proj", "base desc")
        assert p["start_iso"] == "2030-05-15T12:00"
        assert p["end_iso"]   == "2030-05-15T13:00"
        assert "Mtg" in p["summary"]
        assert "[proj]" in p["summary"]

    def test_timed_event_without_end_time_defaults_to_one_hour(self):
        ev = {"desc": "Mtg", "date": "2030-05-15", "time": "12:00"}
        p = gsync._ev_props_for_calendar_app(ev, "proj", "")
        assert p["start_iso"] == "2030-05-15T12:00"
        assert p["end_iso"]   == "2030-05-15T13:00"

    def test_all_day_event(self):
        ev = {"desc": "Conf", "date": "2030-05-15"}
        p = gsync._ev_props_for_calendar_app(ev, "proj", "")
        assert p["start_iso"] == "2030-05-15T00:00"
        assert p["end_iso"]   == "2030-05-15T23:59"

    def test_recurring_strips_rrule_prefix(self):
        ev = {"desc": "Std", "date": "2030-05-15", "time": "10:00",
              "recur": "weekly"}
        p = gsync._ev_props_for_calendar_app(ev, "proj", "")
        assert p["rrule"] == "FREQ=WEEKLY"   # no "RRULE:" prefix

    def test_room_url_promoted_to_event_url(self):
        ev = {"desc": "Mtg", "date": "2030-05-15", "time": "12:00",
              "notes": ["📋 https://indico/x", "🚪 https://zoom/y"]}
        p = gsync._ev_props_for_calendar_app(ev, "proj", "")
        # Room takes precedence over agenda when both present
        assert p["url"] == "https://zoom/y"

    def test_agenda_url_used_when_no_room(self):
        ev = {"desc": "Mtg", "date": "2030-05-15", "time": "12:00",
              "notes": ["📋 https://indico/x"]}
        p = gsync._ev_props_for_calendar_app(ev, "proj", "")
        assert p["url"] == "https://indico/x"

    def test_no_url_when_no_structured_notes(self):
        ev = {"desc": "Mtg", "date": "2030-05-15", "time": "12:00",
              "notes": ["just a free description"]}
        p = gsync._ev_props_for_calendar_app(ev, "proj", "")
        assert p["url"] == ""


# ── Config migration ────────────────────────────────────────────────────────

class TestConfigMigration:
    def test_reads_calendar_sync_when_present(self, tmp_path, monkeypatch):
        cfg_dir = tmp_path
        monkeypatch.setattr(gsync, "CONFIG_PATH",      cfg_dir / "calendar-sync.json")
        monkeypatch.setattr(gsync, "_LEGACY_CONFIG",   cfg_dir / "google-sync.json")
        (cfg_dir / "calendar-sync.json").write_text(json.dumps({
            "calendars": {"default": "🌿 orbit-ps"}
        }))
        cfg = gsync._load_config()
        assert cfg["calendars"]["default"] == "🌿 orbit-ps"

    def test_migrates_from_google_sync_if_calendar_sync_missing(
            self, tmp_path, monkeypatch, capsys):
        cfg_dir = tmp_path
        monkeypatch.setattr(gsync, "CONFIG_PATH",    cfg_dir / "calendar-sync.json")
        monkeypatch.setattr(gsync, "_LEGACY_CONFIG", cfg_dir / "google-sync.json")
        (cfg_dir / "google-sync.json").write_text(json.dumps({
            "calendars": {"default": "abc@google.com"}
        }))
        cfg = gsync._load_config()
        # Migrated content (still has the Google ID — user must rename)
        assert (cfg_dir / "calendar-sync.json").exists()
        assert cfg["calendars"]["default"] == "abc@google.com"
        out = capsys.readouterr().out
        assert "migrada" in out.lower() or "migrated" in out.lower()

    def test_creates_default_when_neither_present(self, tmp_path, monkeypatch):
        cfg_dir = tmp_path
        monkeypatch.setattr(gsync, "CONFIG_PATH",    cfg_dir / "calendar-sync.json")
        monkeypatch.setattr(gsync, "_LEGACY_CONFIG", cfg_dir / "google-sync.json")
        cfg = gsync._load_config()
        assert "calendars" in cfg
        assert (cfg_dir / "calendar-sync.json").exists()

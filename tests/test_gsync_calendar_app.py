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

@pytest.mark.uses_osa
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

    def test_alarm_minutes_relative_hours(self):
        ev = {"desc": "X", "date": "2030-05-15", "time": "12:00", "ring": "2h"}
        p = gsync._ev_props_for_calendar_app(ev, "proj", "")
        assert p["alarm_minutes"] == 120

    def test_alarm_minutes_relative_days(self):
        ev = {"desc": "X", "date": "2030-05-15", "time": "12:00", "ring": "1d"}
        p = gsync._ev_props_for_calendar_app(ev, "proj", "")
        assert p["alarm_minutes"] == 24 * 60

    def test_alarm_minutes_relative_minutes(self):
        ev = {"desc": "X", "date": "2030-05-15", "time": "12:00", "ring": "30m"}
        p = gsync._ev_props_for_calendar_app(ev, "proj", "")
        assert p["alarm_minutes"] == 30

    def test_alarm_minutes_absolute_time_same_day(self):
        ev = {"desc": "X", "date": "2030-05-15", "time": "12:00", "ring": "09:00"}
        p = gsync._ev_props_for_calendar_app(ev, "proj", "")
        # 09:00 → 12:00 = 3h before
        assert p["alarm_minutes"] == 180

    def test_alarm_none_when_no_ring(self):
        ev = {"desc": "X", "date": "2030-05-15", "time": "12:00"}
        p = gsync._ev_props_for_calendar_app(ev, "proj", "")
        assert p["alarm_minutes"] is None


class TestCreateEventWithAlarm:
    def test_alarm_appears_in_script(self, monkeypatch):
        captured = {}
        monkeypatch.setattr(gsync, "_osa",
                            lambda s, **k: (captured.setdefault("s", s), "U")[1])
        gsync._create_calendar_event("Cal", {
            "summary":       "X",
            "start_iso":     "2030-05-15T12:00",
            "end_iso":       "2030-05-15T13:00",
            "alarm_minutes": 30,
        })
        assert "make new display alarm" in captured["s"]
        assert "trigger interval:-30" in captured["s"]

    def test_no_alarm_block_when_alarm_minutes_none(self, monkeypatch):
        captured = {}
        monkeypatch.setattr(gsync, "_osa",
                            lambda s, **k: (captured.setdefault("s", s), "U")[1])
        gsync._create_calendar_event("Cal", {
            "summary":       "X",
            "start_iso":     "2030-05-15T12:00",
            "end_iso":       "2030-05-15T13:00",
        })
        assert "display alarm" not in captured["s"]


class TestUpdateEventClearsAlarm:
    def test_update_without_alarm_deletes_existing_alarms(self, monkeypatch):
        captured = {}
        monkeypatch.setattr(gsync, "_osa",
                            lambda s, **k: (captured.setdefault("s", s), "ok")[1])
        gsync._update_calendar_event("UID", "Cal", {
            "summary":   "X", "start_iso": "2030-05-15T12:00",
            "end_iso":   "2030-05-15T13:00",
        })
        assert "delete every display alarm" in captured["s"]
        assert "make new display alarm" not in captured["s"]

    def test_update_with_alarm_deletes_then_recreates(self, monkeypatch):
        captured = {}
        monkeypatch.setattr(gsync, "_osa",
                            lambda s, **k: (captured.setdefault("s", s), "ok")[1])
        gsync._update_calendar_event("UID", "Cal", {
            "summary":       "X", "start_iso": "2030-05-15T12:00",
            "end_iso":       "2030-05-15T13:00",
            "alarm_minutes": 60,
        })
        # Delete-then-recreate avoids accumulating alarms across syncs
        s = captured["s"]
        assert "delete every display alarm" in s
        assert "trigger interval:-60" in s


# ── Reminders.app backend ────────────────────────────────────────────────────

class TestRemindersListName:
    def test_default_when_not_in_config(self):
        assert gsync._reminders_list_name({}) == "Orbit"

    def test_explicit_overrides_default(self):
        assert gsync._reminders_list_name(
            {"reminders_list": "🚀 ws"}) == "🚀 ws"


class TestItemPropsForReminders:
    def test_task_with_date_and_time_no_ring(self):
        item = {"desc": "Reproducir", "date": "2030-05-15",
                "time": "10:00", "status": "pending"}
        p = gsync._item_props_for_reminders(item, "next-kr", "task")
        assert "✅" in p["name"]
        assert "[next-kr]" in p["name"]
        assert "Reproducir" in p["name"]
        assert p["due_iso"] == "2030-05-15T10:00"
        assert p["remind_iso"] is None  # no --ring → no alert
        assert p["completed"] is False

    def test_task_with_ring_has_remind_iso(self):
        item = {"desc": "Mtg", "date": "2030-05-15",
                "time": "12:00", "ring": "1h", "status": "pending"}
        p = gsync._item_props_for_reminders(item, "p", "task")
        # 1h before 12:00 = 11:00
        assert p["remind_iso"] == "2030-05-15T11:00"

    def test_task_without_time_uses_default_hour(self):
        item = {"desc": "Plan", "date": "2030-05-15", "status": "pending"}
        p = gsync._item_props_for_reminders(item, "p", "task")
        assert p["due_iso"] == "2030-05-15T09:00"

    def test_milestone_uses_milestone_emoji(self):
        item = {"desc": "Calibrated", "date": "2030-06-01",
                "status": "pending"}
        p = gsync._item_props_for_reminders(item, "p", "milestone")
        assert "🏁" in p["name"]

    def test_reminder_uses_reminder_emoji_and_remind_at_due(self):
        item = {"desc": "Llamar", "date": "2030-05-15", "time": "16:00"}
        p = gsync._item_props_for_reminders(item, "p", "reminder")
        assert "💬" in p["name"]
        # reminders fire at their scheduled time
        assert p["remind_iso"] == "2030-05-15T16:00"

    def test_done_task_marked_completed(self):
        item = {"desc": "X", "date": "2030-05-15",
                "time": "10:00", "status": "done"}
        p = gsync._item_props_for_reminders(item, "p", "task")
        assert p["completed"] is True

    def test_cancelled_task_marked_completed(self):
        item = {"desc": "X", "date": "2030-05-15",
                "time": "10:00", "status": "cancelled"}
        p = gsync._item_props_for_reminders(item, "p", "task")
        assert p["completed"] is True

    def test_notes_become_body(self):
        item = {"desc": "X", "date": "2030-05-15",
                "time": "10:00", "status": "pending",
                "notes": ["line one", "line two"]}
        p = gsync._item_props_for_reminders(item, "p", "task")
        assert "line one\nline two" == p["body"]


class TestCreateReminderItem:
    def test_basic_script(self, monkeypatch):
        captured = {}
        monkeypatch.setattr(gsync, "_osa",
                            lambda s, **k: (captured.setdefault("s", s), "RID-1")[1])
        uid = gsync._create_reminder_item("Orbit", {
            "name":    "✅[p] X",
            "body":    "",
            "due_iso": "2030-05-15T10:00",
            "remind_iso": None,
        })
        assert uid == "RID-1"
        s = captured["s"]
        assert 'tell list "Orbit"' in s
        assert 'name:"✅[p] X"' in s
        assert "due date:dueD" in s
        assert "remind me date:" not in s

    def test_with_alarm(self, monkeypatch):
        captured = {}
        monkeypatch.setattr(gsync, "_osa",
                            lambda s, **k: (captured.setdefault("s", s), "RID-2")[1])
        gsync._create_reminder_item("Orbit", {
            "name":       "✅[p] Y",
            "body":       "",
            "due_iso":    "2030-05-15T12:00",
            "remind_iso": "2030-05-15T11:00",
        })
        s = captured["s"]
        assert "remind me date:remindD" in s


class TestUpdateReminderItem:
    def test_returns_true_on_ok(self, monkeypatch):
        monkeypatch.setattr(gsync, "_osa", lambda s, **k: "ok")
        assert gsync._update_reminder_item("UID", "Orbit", {
            "name": "X", "body": "", "due_iso": None,
            "remind_iso": None, "completed": False,
        }) is True

    def test_returns_false_on_missing(self, monkeypatch):
        monkeypatch.setattr(gsync, "_osa", lambda s, **k: "missing")
        assert gsync._update_reminder_item("UID", "Orbit", {
            "name": "X", "body": "", "due_iso": None,
            "remind_iso": None, "completed": False,
        }) is False

    def test_completed_true_emits_completed_set(self, monkeypatch):
        captured = {}
        monkeypatch.setattr(gsync, "_osa",
                            lambda s, **k: (captured.setdefault("s", s), "ok")[1])
        gsync._update_reminder_item("UID", "Orbit", {
            "name": "X", "body": "", "due_iso": None,
            "remind_iso": None, "completed": True,
        })
        assert "set completed of r to true" in captured["s"]


class TestSyncOneToReminders:
    def _mock_lookups(self, monkeypatch, by_id=None, by_name=None):
        """Default: nothing found. Pass uids to simulate hits."""
        monkeypatch.setattr(gsync, "_find_reminder_by_orbit_id",
                            lambda lst, oid: by_id)
        monkeypatch.setattr(gsync, "_find_reminder_by_name",
                            lambda lst, n: by_name)

    def test_creates_when_no_match(self, monkeypatch):
        self._mock_lookups(monkeypatch)
        monkeypatch.setattr(gsync, "_create_reminder_item",
                            lambda lst, props: "NEW-UID")
        item = {"desc": "X", "date": "2030-05-15",
                "time": "10:00", "status": "pending"}
        uid = gsync._sync_one_to_reminders("Orbit", item, "proj",
                                           "task", dry_run=False)
        assert uid == "NEW-UID"

    def test_updates_when_uid_present(self, monkeypatch):
        self._mock_lookups(monkeypatch)
        monkeypatch.setattr(gsync, "_update_reminder_item",
                            lambda uid, lst, props: True)
        item = {"desc": "X", "date": "2030-05-15",
                "time": "10:00", "status": "pending",
                "_gtask_id": "OLD-UID"}
        uid = gsync._sync_one_to_reminders("Orbit", item, "proj",
                                           "task", dry_run=False)
        assert uid == "OLD-UID"

    def test_orbit_id_match_takes_priority(self, monkeypatch):
        """Orbit-id wins over the stored uid even when the stored uid would update."""
        self._mock_lookups(monkeypatch, by_id="UID-FOUND-BY-ORBIT-ID")
        updates = []
        monkeypatch.setattr(gsync, "_update_reminder_item",
                            lambda uid, lst, props: updates.append(uid) or True)
        item = {"desc": "X", "date": "2030-05-15", "time": "10:00",
                "status": "pending", "_orbit_id": "abc12345",
                "_gtask_id": "STORED-UID"}
        uid = gsync._sync_one_to_reminders("Orbit", item, "proj",
                                           "task", dry_run=False)
        assert uid == "UID-FOUND-BY-ORBIT-ID"
        assert updates == ["UID-FOUND-BY-ORBIT-ID"]  # only updates the matched one

    def test_failed_update_after_name_match_does_not_duplicate(self, monkeypatch):
        """The bug we fixed: timed-out _update used to fall through to _create.

        Now: we found the reminder by name, return that uid, retry next sync.
        No _create call → no duplicate.
        """
        self._mock_lookups(monkeypatch, by_name="MATCHED-BY-NAME")
        monkeypatch.setattr(gsync, "_update_reminder_item",
                            lambda uid, lst, props: False)  # always times out
        creates = []
        monkeypatch.setattr(gsync, "_create_reminder_item",
                            lambda lst, props: creates.append(props) or "OOPS-NEW")
        item = {"desc": "X", "date": "2030-05-15",
                "time": "10:00", "status": "pending"}
        uid = gsync._sync_one_to_reminders("Orbit", item, "proj",
                                           "task", dry_run=False)
        assert uid == "MATCHED-BY-NAME"
        assert creates == [], "must NOT create when match-by-name found one"

    def test_orbit_id_match_failed_update_does_not_duplicate(self, monkeypatch):
        self._mock_lookups(monkeypatch, by_id="MATCHED-BY-ORBIT-ID")
        monkeypatch.setattr(gsync, "_update_reminder_item",
                            lambda uid, lst, props: False)
        creates = []
        monkeypatch.setattr(gsync, "_create_reminder_item",
                            lambda lst, props: creates.append(1) or "OOPS-NEW")
        item = {"desc": "X", "date": "2030-05-15", "time": "10:00",
                "status": "pending", "_orbit_id": "abc12345"}
        uid = gsync._sync_one_to_reminders("Orbit", item, "proj",
                                           "task", dry_run=False)
        assert uid == "MATCHED-BY-ORBIT-ID"
        assert creates == []


class TestOrbitId:
    def test_new_orbit_id_format(self):
        oid = gsync._new_orbit_id()
        assert len(oid) == 8
        assert all(c in "0123456789abcdef" for c in oid)

    def test_unique_ids(self):
        ids = {gsync._new_orbit_id() for _ in range(50)}
        assert len(ids) == 50  # extremely likely if RNG works

    def test_build_tag_simple(self):
        assert gsync._build_orbit_tag("abc12345") == "[orbit:abc12345]"

    def test_build_tag_with_occurrence(self):
        assert (gsync._build_orbit_tag("abc12345", "2026-05-11")
                == "[orbit:abc12345@2026-05-11]")

    def test_parse_tag_simple(self):
        oid, occ = gsync._parse_orbit_tag("notes\n[orbit:abc12345]\n")
        assert oid == "abc12345"
        assert occ is None

    def test_parse_tag_with_occurrence(self):
        oid, occ = gsync._parse_orbit_tag("hi [orbit:abc12345@2026-05-11] bye")
        assert oid == "abc12345"
        assert occ == "2026-05-11"

    def test_parse_tag_absent(self):
        assert gsync._parse_orbit_tag("just notes") == (None, None)
        assert gsync._parse_orbit_tag("") == (None, None)
        assert gsync._parse_orbit_tag(None) == (None, None)

    def test_append_tag_to_empty_body(self):
        assert gsync._append_orbit_tag("", "[orbit:x]") == "[orbit:x]"

    def test_append_tag_to_nonempty_body(self):
        assert (gsync._append_orbit_tag("notes line", "[orbit:x]")
                == "notes line\n\n[orbit:x]")

    def test_append_tag_idempotent(self):
        body = "notes\n\n[orbit:abc12345]"
        assert gsync._append_orbit_tag(body, "[orbit:abc12345]") == body

    def test_append_tag_replaces_occurrence_date(self):
        """When a recurring item advances, the new tag replaces the old one."""
        body = "notes\n\n[orbit:abc12345@2026-05-11]"
        out = gsync._append_orbit_tag(body, "[orbit:abc12345@2026-05-18]")
        assert out == "notes\n\n[orbit:abc12345@2026-05-18]"
        assert "2026-05-11" not in out, "old occurrence date must not linger"

    def test_append_tag_promotes_dated_to_undated(self):
        body = "notes\n\n[orbit:abc12345@2026-05-11]"
        out = gsync._append_orbit_tag(body, "[orbit:abc12345]")
        assert out == "notes\n\n[orbit:abc12345]"

    def test_append_tag_other_id_coexists(self):
        """Different orbit-ids in the same body don't conflict."""
        body = "[orbit:aaaaaaaa]\n[orbit:bbbbbbbb@2026-05-11]"
        out = gsync._append_orbit_tag(body, "[orbit:bbbbbbbb@2026-06-01]")
        assert "[orbit:aaaaaaaa]" in out
        assert "[orbit:bbbbbbbb@2026-06-01]" in out
        assert "2026-05-11" not in out

    def test_reminders_props_embed_tag(self):
        item = {"desc": "X", "date": "2030-05-15", "time": "10:00",
                "status": "pending", "_orbit_id": "abc12345"}
        props = gsync._item_props_for_reminders(item, "proj", "task")
        assert "[orbit:abc12345]" in props["body"]

    def test_reminders_props_recurring_uses_occurrence_date(self):
        item = {"desc": "X", "date": "2030-05-11", "recur": "weekly",
                "status": "pending", "_orbit_id": "abc12345"}
        props = gsync._item_props_for_reminders(item, "proj", "task")
        assert "[orbit:abc12345@2030-05-11]" in props["body"]

    def test_calendar_props_embed_tag_no_occurrence(self):
        ev = {"desc": "Mtg", "date": "2030-05-11", "recur": "weekly",
              "_orbit_id": "abc12345"}
        props = gsync._ev_props_for_calendar_app(ev, "proj", "")
        # Calendar handles recurrence natively → only series id, no @date
        assert "[orbit:abc12345]" in props["description"]
        assert "@" not in props["description"].split("[orbit:abc12345")[1][:5]


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


class TestSyncCronosForProject:
    """Option G — 1 reminder per cronograma tracking the next open leaf.

    Legacy backend (Reminders.app). Tests pass ``reminders_backend:
    "reminders"`` explicitly because the default flipped to "calendar" in
    v0.29; the calendar-backend cronograma path lives in
    :class:`TestSyncCronosForProjectCalendarBackend`.
    """

    LEGACY_CFG = {"reminders_backend": "reminders"}

    def _make_proj(self, tmp_path, crono_body):
        proj = tmp_path / "🌀test-proj"
        (proj / "cronos").mkdir(parents=True)
        (proj / "cronos" / "crono-x.md").write_text(crono_body)
        return proj

    def test_no_cronos_dir_returns_zeros(self, tmp_path, monkeypatch):
        proj = tmp_path / "no-cronos"
        proj.mkdir()
        monkeypatch.setattr(gsync, "_ensure_reminders_list", lambda n: True)
        monkeypatch.setattr(gsync, "_reminders_list_name", lambda c: "Test")
        c, u, s = gsync._sync_cronos_for_project(proj, self.LEGACY_CFG,
                                                  dry_run=False)
        assert (c, u, s) == (0, 0, 0)

    def test_creates_reminder_for_dated_leaf(self, tmp_path, monkeypatch):
        proj = self._make_proj(tmp_path, (
            "# Cronograma: x\n\n"
            "- [ ] 1. parent\n"
            "  - [ ] 1.1 first  | 2026-06-01\n"
            "  - [ ] 1.2 second | 2026-08-01\n"
        ))
        monkeypatch.setattr(gsync, "_ensure_reminders_list", lambda n: True)
        monkeypatch.setattr(gsync, "_reminders_list_name", lambda c: "Test")
        seen = {}
        def fake_sync_one(list_name, item, project_name, kind, dry_run):
            seen["item"] = item
            seen["kind"] = kind
            return "x-apple-reminder://AAA"
        monkeypatch.setattr(gsync, "_sync_one_to_reminders", fake_sync_one)
        c, u, s = gsync._sync_cronos_for_project(proj, self.LEGACY_CFG,
                                                  dry_run=False)
        assert c == 1 and u == 0
        assert seen["kind"] == "cronograma"
        assert seen["item"]["date"] == "2026-06-01"
        assert "crono-x" in seen["item"]["desc"]
        assert "first" in seen["item"]["desc"]
        ids = json.loads((proj / ".gsync-ids.json").read_text())
        assert ids["_cronos"]["x"]["gtask_id"] == "x-apple-reminder://AAA"
        assert ids["_cronos"]["x"]["leaf"] == "1.1"

    def test_overdue_leaf_keeps_slot(self, tmp_path, monkeypatch):
        """Vencidas no avanzan — la fecha pasada se queda en el reminder."""
        proj = self._make_proj(tmp_path, (
            "# Cronograma: x\n\n"
            "- [ ] 1. parent\n"
            "  - [ ] 1.1 overdue | 2026-04-01\n"
            "  - [ ] 1.2 future  | 2026-08-01\n"
        ))
        monkeypatch.setattr(gsync, "_ensure_reminders_list", lambda n: True)
        monkeypatch.setattr(gsync, "_reminders_list_name", lambda c: "Test")
        seen = {}
        def fake_sync_one(list_name, item, project_name, kind, dry_run):
            seen["item"] = item
            return "x-apple-reminder://OLD"
        monkeypatch.setattr(gsync, "_sync_one_to_reminders", fake_sync_one)
        gsync._sync_cronos_for_project(proj, self.LEGACY_CFG, dry_run=False)
        assert seen["item"]["date"] == "2026-04-01"
        assert "overdue" in seen["item"]["desc"]

    def test_skip_outline_only_cronograma(self, tmp_path, monkeypatch):
        """Cronograma sin fechas → no genera reminder."""
        proj = self._make_proj(tmp_path, (
            "# Cronograma: x\n\n"
            "- [ ] 1. parent\n"
            "  - [ ] 1.1 leaf\n"
            "  - [ ] 1.2 leaf\n"
        ))
        monkeypatch.setattr(gsync, "_ensure_reminders_list", lambda n: True)
        monkeypatch.setattr(gsync, "_reminders_list_name", lambda c: "Test")
        called = {"n": 0}
        def fake_sync_one(*a, **k):
            called["n"] += 1
            return "uid"
        monkeypatch.setattr(gsync, "_sync_one_to_reminders", fake_sync_one)
        c, u, s = gsync._sync_cronos_for_project(proj, self.LEGACY_CFG,
                                                  dry_run=False)
        assert called["n"] == 0
        assert c == 0 and u == 0 and s == 1

    def test_all_done_marks_reminder_completed(self, tmp_path, monkeypatch):
        proj = self._make_proj(tmp_path, (
            "# Cronograma: x\n\n"
            "- [ ] 1. parent\n"
            "  - [x] 1.1 a | 2026-04-01\n"
            "  - [x] 1.2 b | 2026-04-08\n"
        ))
        monkeypatch.setattr(gsync, "_ensure_reminders_list", lambda n: True)
        monkeypatch.setattr(gsync, "_reminders_list_name", lambda c: "Test")
        seen = {}
        def fake_sync_one(list_name, item, project_name, kind, dry_run):
            seen["item"] = item
            return "x-apple-reminder://DONE"
        monkeypatch.setattr(gsync, "_sync_one_to_reminders", fake_sync_one)
        gsync._sync_cronos_for_project(proj, self.LEGACY_CFG, dry_run=False)
        assert seen["item"]["status"] == "done"
        assert seen["item"]["date"] is None

    def test_dry_run_does_not_persist_ids(self, tmp_path, monkeypatch):
        proj = self._make_proj(tmp_path, (
            "# Cronograma: x\n\n"
            "- [ ] 1. parent\n"
            "  - [ ] 1.1 leaf | 2026-06-01\n"
        ))
        monkeypatch.setattr(gsync, "_ensure_reminders_list", lambda n: True)
        monkeypatch.setattr(gsync, "_reminders_list_name", lambda c: "Test")
        monkeypatch.setattr(gsync, "_sync_one_to_reminders",
                            lambda *a, **k: None)
        gsync._sync_cronos_for_project(proj, self.LEGACY_CFG, dry_run=True)
        assert not (proj / ".gsync-ids.json").exists()


class TestSyncCronosForProjectCalendarBackend:
    """Cronogramas under the calendar backend (v0.29.3):
    1 Calendar event per cronograma, routed to the per-tipo events calendar.
    """

    def _make_proj(self, tmp_path, crono_body):
        proj = tmp_path / "🌀test-proj"
        (proj / "cronos").mkdir(parents=True)
        (proj / "cronos" / "crono-x.md").write_text(crono_body)
        return proj

    def _setup_calendar_backend(self, monkeypatch, has_reminders_running=False):
        """Stub Calendar.app / Reminders.app probes for the calendar path."""
        monkeypatch.setattr(gsync, "_calendar_app_running", lambda: True)
        monkeypatch.setattr(gsync, "_reminders_app_running",
                             lambda: has_reminders_running)
        monkeypatch.setattr(gsync, "_get_project_tipo",
                             lambda p: "investigacion")
        monkeypatch.setattr(gsync, "_project_description",
                             lambda p, c, html=False: "Proyecto: test")
        monkeypatch.setattr(gsync, "_reminders_list_name",
                             lambda c: "🚀 orbit-ws")

    def _cfg(self, **over):
        base = {"reminders_backend": "calendar",
                "calendars": {"investigacion": "events-cal",
                              "default": "events-cal"}}
        base.update(over)
        return base

    def test_creates_event_for_dated_leaf(self, tmp_path, monkeypatch):
        self._setup_calendar_backend(monkeypatch)
        proj = self._make_proj(tmp_path, (
            "# Cronograma: x\n\n"
            "- [ ] 1. parent\n"
            "  - [ ] 1.1 first  | 2026-06-01\n"
            "  - [ ] 1.2 second | 2026-08-01\n"
        ))
        seen = {}
        def fake_sync_event(cal_name, item, project_name, description, kind,
                             dry_run=False):
            seen["cal"] = cal_name
            seen["item"] = item
            seen["kind"] = kind
            return "calendar-uid-aaa"
        monkeypatch.setattr(gsync, "_sync_one_agenda_event", fake_sync_event)

        c, u, s = gsync._sync_cronos_for_project(proj, self._cfg(),
                                                  dry_run=False)
        assert (c, u, s) == (1, 0, 0)
        assert seen["cal"] == "events-cal"
        assert seen["kind"] == "cronograma"
        assert seen["item"]["date"] == "2026-06-01"
        assert "crono-x" in seen["item"]["desc"]
        assert "first" in seen["item"]["desc"]
        ids = json.loads((proj / ".gsync-ids.json").read_text())
        assert ids["_cronos"]["x"]["gcal_id"] == "calendar-uid-aaa"
        assert ids["_cronos"]["x"]["leaf"] == "1.1"
        assert "gtask_id" not in ids["_cronos"]["x"]

    def test_no_calendar_configured_skips(self, tmp_path, monkeypatch):
        """If neither per-tipo nor default calendar is set, return zeros."""
        self._setup_calendar_backend(monkeypatch)
        proj = self._make_proj(tmp_path, (
            "# Cronograma: x\n\n"
            "- [ ] 1.1 leaf | 2026-06-01\n"
        ))
        called = {"n": 0}
        monkeypatch.setattr(gsync, "_sync_one_agenda_event",
                             lambda *a, **k: called.__setitem__("n", called["n"] + 1) or "x")
        cfg = {"reminders_backend": "calendar", "calendars": {}}
        c, u, s = gsync._sync_cronos_for_project(proj, cfg, dry_run=False)
        assert (c, u, s) == (0, 0, 0)
        assert called["n"] == 0

    def test_all_done_deletes_event(self, tmp_path, monkeypatch):
        """When every leaf is done, the cronograma event is removed and the
        storage entry pops."""
        self._setup_calendar_backend(monkeypatch)
        proj = self._make_proj(tmp_path, (
            "# Cronograma: x\n\n"
            "- [ ] 1. parent\n"
            "  - [x] 1.1 a | 2026-04-01\n"
            "  - [x] 1.2 b | 2026-04-08\n"
        ))
        # Pre-seed an existing cgal_id so we can verify it gets deleted.
        ids_path = proj / ".gsync-ids.json"
        ids_path.write_text(json.dumps({
            "_cronos": {"x": {"gcal_id": "old-uid",
                              "orbit_id": "abc12345",
                              "leaf": "1.2"}}
        }))
        deleted = []
        monkeypatch.setattr(gsync, "_delete_calendar_event",
                             lambda uid, cal: deleted.append((uid, cal)) or True)
        called = {"sync_event": 0}
        monkeypatch.setattr(gsync, "_sync_one_agenda_event",
                             lambda *a, **k: called.__setitem__("sync_event", 1) or "x")

        gsync._sync_cronos_for_project(proj, self._cfg(), dry_run=False)

        assert deleted == [("old-uid", "events-cal")]
        assert called["sync_event"] == 0
        ids = json.loads(ids_path.read_text())
        assert "x" not in ids["_cronos"]

    def test_legacy_gtask_id_triggers_reminders_cleanup(
            self, tmp_path, monkeypatch):
        """First sync after upgrading: existing gtask_id is removed from
        Reminders.app (best-effort) and replaced by gcal_id."""
        self._setup_calendar_backend(monkeypatch, has_reminders_running=True)
        proj = self._make_proj(tmp_path, (
            "# Cronograma: x\n\n"
            "- [ ] 1.1 leaf | 2026-06-01\n"
        ))
        ids_path = proj / ".gsync-ids.json"
        ids_path.write_text(json.dumps({
            "_cronos": {"x": {"gtask_id": "x-apple-reminder://OLD",
                              "orbit_id": "abc12345",
                              "leaf": "1.1"}}
        }))
        deleted_rems = []
        monkeypatch.setattr(gsync, "_delete_reminder_item",
                             lambda uid, lst: deleted_rems.append((uid, lst)) or True)
        monkeypatch.setattr(gsync, "_sync_one_agenda_event",
                             lambda *a, **k: "new-gcal-uid")

        gsync._sync_cronos_for_project(proj, self._cfg(), dry_run=False)

        assert deleted_rems == [("x-apple-reminder://OLD", "🚀 orbit-ws")]
        ids = json.loads(ids_path.read_text())
        assert ids["_cronos"]["x"]["gcal_id"] == "new-gcal-uid"
        assert "gtask_id" not in ids["_cronos"]["x"]

    def test_legacy_cleanup_skipped_when_reminders_app_closed(
            self, tmp_path, monkeypatch):
        """If Reminders.app isn't running, skip the legacy cleanup but still
        sync to Calendar normally."""
        self._setup_calendar_backend(monkeypatch, has_reminders_running=False)
        proj = self._make_proj(tmp_path, (
            "# Cronograma: x\n\n"
            "- [ ] 1.1 leaf | 2026-06-01\n"
        ))
        ids_path = proj / ".gsync-ids.json"
        ids_path.write_text(json.dumps({
            "_cronos": {"x": {"gtask_id": "x-apple-reminder://OLD",
                              "orbit_id": "abc12345",
                              "leaf": "1.1"}}
        }))
        deleted_rems = []
        monkeypatch.setattr(gsync, "_delete_reminder_item",
                             lambda uid, lst: deleted_rems.append((uid, lst)) or True)
        monkeypatch.setattr(gsync, "_sync_one_agenda_event",
                             lambda *a, **k: "new-gcal-uid")

        gsync._sync_cronos_for_project(proj, self._cfg(), dry_run=False)

        assert deleted_rems == []  # Reminders.app closed → no cleanup attempt
        ids = json.loads(ids_path.read_text())
        assert ids["_cronos"]["x"]["gcal_id"] == "new-gcal-uid"

    def test_overdue_leaf_keeps_slot_in_calendar(self, tmp_path, monkeypatch):
        """Same semantics as legacy: overdue leaves don't auto-advance."""
        self._setup_calendar_backend(monkeypatch)
        proj = self._make_proj(tmp_path, (
            "# Cronograma: x\n\n"
            "- [ ] 1. parent\n"
            "  - [ ] 1.1 overdue | 2026-04-01\n"
            "  - [ ] 1.2 future  | 2026-08-01\n"
        ))
        seen = {}
        monkeypatch.setattr(gsync, "_sync_one_agenda_event",
                             lambda cal, item, *a, **k:
                                 seen.update(item=item) or "uid")
        gsync._sync_cronos_for_project(proj, self._cfg(), dry_run=False)
        assert seen["item"]["date"] == "2026-04-01"
        assert "overdue" in seen["item"]["desc"]


class TestRunGsyncProjectFilter:
    """`orbit gsync <project>` filters dirs to only that project."""

    def test_unknown_project_returns_error(self, monkeypatch, capsys):
        monkeypatch.setattr(gsync, "_load_config", lambda: {"calendars": {"default": "X"}})
        monkeypatch.setattr(gsync, "_calendar_app_running", lambda: True)
        monkeypatch.setattr(gsync, "_reminders_app_running", lambda: True)
        monkeypatch.setattr(gsync, "_find_new_project", lambda name: None)
        rc = gsync.run_gsync(project="does-not-exist")
        assert rc == 1
        assert "no encontrado" in capsys.readouterr().out.lower()

    def test_known_project_limits_iteration(self, tmp_path, monkeypatch):
        """Only the resolved project_dir is iterated, not all of iter_project_dirs."""
        proj = tmp_path / "santiago"
        proj.mkdir()
        monkeypatch.setattr(gsync, "_load_config", lambda: {"calendars": {"default": "X"},
                                                             "reminders_list": "Test"})
        monkeypatch.setattr(gsync, "_calendar_app_running", lambda: True)
        monkeypatch.setattr(gsync, "_reminders_app_running", lambda: True)
        monkeypatch.setattr(gsync, "_find_new_project", lambda name: proj)
        # Sentinel: iter_project_dirs must NOT be called when project is given
        monkeypatch.setattr(gsync, "iter_project_dirs",
                            lambda: (_ for _ in ()).throw(AssertionError("must not be called")))
        seen = []
        monkeypatch.setattr(gsync, "_sync_to_reminders_for_project",
                            lambda d, c, dr: seen.append(d) or (0, 0, 0))
        monkeypatch.setattr(gsync, "_sync_cronos_for_project",
                            lambda d, c, dr: (0, 0, 0))
        monkeypatch.setattr(gsync, "_sync_events_for_project",
                            lambda d, c, dr: (0, 0, 0))
        monkeypatch.setattr(gsync, "_get_project_tipo", lambda d: "default")
        rc = gsync.run_gsync(project="santiago")
        assert rc == 0
        assert seen == [proj]

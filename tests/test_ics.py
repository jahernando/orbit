"""Tests for core.ics — iCalendar serializer + bucket router + snapshot diff."""

from datetime import date, timedelta
from pathlib import Path

import pytest

from core import ics


# ── Low-level helpers ────────────────────────────────────────────────────────

class TestEscape:
    def test_comma_semicolon_backslash_newline(self):
        assert ics._escape("a,b;c\\d\ne") == "a\\,b\\;c\\\\d\\ne"

    def test_none_returns_empty(self):
        assert ics._escape(None) == ""

    def test_no_special_chars_passthrough(self):
        assert ics._escape("hello world") == "hello world"


class TestFold:
    def test_short_line_unchanged(self):
        assert ics._fold("DTSTART:20260101T100000") == "DTSTART:20260101T100000"

    def test_long_line_folds_with_crlf_space(self):
        line = "DESCRIPTION:" + ("a" * 200)
        out = ics._fold(line)
        # First chunk ≤ 75, subsequent chunks ≤ 74 (account for leading space)
        physical = out.split("\r\n ")
        assert len(physical) >= 3
        assert len(physical[0].encode("utf-8")) <= 75
        for chunk in physical[1:]:
            assert len(chunk.encode("utf-8")) <= 74

    def test_multibyte_chars_dont_split(self):
        # Each '✅' is 3 bytes — line folding must not break mid-codepoint
        line = "SUMMARY:" + ("✅" * 30)
        out = ics._fold(line)
        for chunk in out.split("\r\n "):
            # If a chunk decodes cleanly, we didn't split a codepoint
            chunk.encode("utf-8").decode("utf-8")


class TestFmtDt:
    def test_minutes_only_padded_to_seconds(self):
        assert ics._fmt_dt_local("2026-05-15T10:30") == "20260515T103000"

    def test_with_seconds(self):
        assert ics._fmt_dt_local("2026-05-15T10:30:45") == "20260515T103045"


class TestFmtDate:
    def test_strips_dashes(self):
        assert ics._fmt_date("2026-05-15") == "20260515"


# ── UID stability ────────────────────────────────────────────────────────────

class TestUid:
    def test_non_recurring_uses_orbit_id(self):
        assert ics._item_uid("deadbeef", None, "fallback") == "deadbeef@orbit"

    def test_recurring_carries_occurrence(self):
        assert ics._item_uid("deadbeef", "2026-05-15", "fallback") \
            == "deadbeef-2026-05-15@orbit"

    def test_fallback_when_no_orbit_id(self):
        uid = ics._item_uid(None, None, "task-foo-2026")
        assert uid == "task-foo-2026@orbit"


# ── VEVENT building ──────────────────────────────────────────────────────────

class TestRenderVevent:
    def _task(self, **over):
        base = {"desc": "Test", "date": "2026-05-15", "time": "10:00",
                "orbit_id": "abc12345"}
        base.update(over)
        return base

    def test_basic_task(self):
        lines = ics.render_vevent(self._task(), "task", "proj")
        block = "\n".join(lines)
        assert "BEGIN:VEVENT" in block
        assert "END:VEVENT" in block
        assert "UID:abc12345@orbit" in block
        assert "DTSTART:20260515T100000" in block
        assert "DTEND:20260515T110000" in block   # task: +60 min default
        assert "SUMMARY:[proj] ✅ Test" in block
        assert "CATEGORIES:task" in block
        assert "X-ORBIT-ID:abc12345" in block
        assert "X-ORBIT-PROJECT:proj" in block
        assert "X-ORBIT-KIND:task" in block

    def test_alarm_block_default_zero_for_agenda(self):
        block = "\n".join(ics.render_vevent(self._task(), "task", "proj"))
        assert "BEGIN:VALARM" in block
        assert "TRIGGER:-PT0M" in block

    def test_alarm_honors_ring(self):
        block = "\n".join(ics.render_vevent(self._task(ring="15m"),
                                             "task", "proj"))
        assert "TRIGGER:-PT15M" in block

    def test_event_with_time_range(self):
        ev = {"desc": "Kickoff", "date": "2026-05-15",
              "time": "10:00-11:30", "orbit_id": "evt0"}
        block = "\n".join(ics.render_vevent(ev, "event", "proj"))
        assert "DTSTART:20260515T100000" in block
        assert "DTEND:20260515T113000" in block
        # Events carry no kind emoji
        assert "SUMMARY:[proj] Kickoff" in block

    def test_event_all_day(self):
        ev = {"desc": "Holiday", "date": "2026-05-15", "orbit_id": "h0"}
        block = "\n".join(ics.render_vevent(ev, "event", "proj"))
        assert "DTSTART;VALUE=DATE:20260515" in block
        # DTEND is exclusive → +1 day for VALUE=DATE
        assert "DTEND;VALUE=DATE:20260516" in block

    def test_event_no_alarm_unless_ring(self):
        ev = {"desc": "K", "date": "2026-05-15", "time": "10:00-11:00",
              "orbit_id": "e0"}
        block = "\n".join(ics.render_vevent(ev, "event", "proj"))
        assert "BEGIN:VALARM" not in block

    def test_meeting_url_promoted_to_url_and_location(self):
        ev = {"desc": "Zoom", "date": "2026-05-15", "time": "10:00-11:00",
              "orbit_id": "e0",
              "notes": ["🚪 https://zoom.us/j/9999"]}
        block = "\n".join(ics.render_vevent(ev, "event", "proj"))
        assert "URL:https://zoom.us/j/9999" in block
        assert "LOCATION:https://zoom.us/j/9999" in block

    def test_description_includes_orbit_id_tag(self):
        block = "\n".join(ics.render_vevent(self._task(), "task", "proj"))
        assert "DESCRIPTION:Proyecto: proj\\n[orbit:abc12345]" in block

    def test_description_without_orbit_id_omits_tag(self):
        item = {"desc": "T", "date": "2026-05-15", "time": "10:00",
                "orbit_id": None}
        block = "\n".join(ics.render_vevent(item, "task", "proj"))
        assert "[orbit:" not in block.split("DESCRIPTION:")[1].split("\n")[0]

    def test_default_duration_event_no_end_is_one_hour(self):
        ev = {"desc": "Meeting", "date": "2026-05-15", "time": "10:00",
              "orbit_id": "e0"}
        block = "\n".join(ics.render_vevent(ev, "event", "proj"))
        assert "DTSTART:20260515T100000" in block
        assert "DTEND:20260515T110000" in block

    def test_default_duration_milestone_is_one_hour(self):
        ms = {"desc": "Deadline", "date": "2026-05-15", "time": "10:00",
              "orbit_id": "m0"}
        block = "\n".join(ics.render_vevent(ms, "milestone", "proj"))
        assert "DTEND:20260515T110000" in block

    def test_default_duration_cronograma_is_one_hour(self):
        cr = {"desc": "Leaf", "date": "2026-05-15", "time": "10:00",
              "orbit_id": None}
        block = "\n".join(ics.render_vevent(cr, "cronograma", "proj"))
        assert "DTEND:20260515T110000" in block

    def test_default_duration_reminder_is_5_min(self):
        rem = {"desc": "Llamar", "date": "2026-05-15", "time": "10:00",
               "orbit_id": "r0"}
        block = "\n".join(ics.render_vevent(rem, "reminder", "proj"))
        assert "DTEND:20260515T100500" in block

    def test_recurring_occurrence_uid_carries_date(self):
        item = self._task(recur="weekly")
        block = "\n".join(ics.render_vevent(item, "task", "proj",
                                             occurrence_date="2026-06-01"))
        assert "UID:abc12345-2026-06-01@orbit" in block
        assert "DTSTART:20260601T100000" in block


# ── Recurrence expansion ─────────────────────────────────────────────────────

class TestExpandDates:
    def test_non_recurring_single_date(self):
        item = {"date": "2026-05-15"}
        out = ics._expand_dates(item, date(2026, 5, 1), date(2026, 6, 1))
        assert out == ["2026-05-15"]

    def test_non_recurring_outside_window_returns_empty(self):
        item = {"date": "2026-05-15"}
        out = ics._expand_dates(item, date(2027, 1, 1), date(2027, 6, 1))
        assert out == []

    def test_weekly_expansion(self):
        item = {"date": "2026-05-15", "recur": "weekly"}  # fri
        out = ics._expand_dates(item, date(2026, 5, 15), date(2026, 6, 15))
        # 5/15, 5/22, 5/29, 6/5, 6/12
        assert out == ["2026-05-15", "2026-05-22", "2026-05-29",
                       "2026-06-05", "2026-06-12"]

    def test_until_caps_expansion(self):
        item = {"date": "2026-05-15", "recur": "weekly",
                "until": "2026-06-01"}
        out = ics._expand_dates(item, date(2026, 5, 1), date(2026, 12, 31))
        # Only 5/15, 5/22, 5/29 (5/29 ≤ 6/1; next would be 6/5 > 6/1)
        assert out == ["2026-05-15", "2026-05-22", "2026-05-29"]


# ── Bucket config ────────────────────────────────────────────────────────────

class TestGetBuckets:
    def test_default_when_unset(self):
        bk = ics.get_buckets({})
        assert "agenda" in bk and "events" in bk
        assert "task" in bk["agenda"]
        assert "event" in bk["events"]

    def test_explicit_overrides_default(self):
        bk = ics.get_buckets({"ics_buckets":
                              {"todo": ["task", "milestone"]}})
        assert bk == {"todo": ["task", "milestone"]}


class TestValidateBuckets:
    def test_default_is_clean(self):
        assert ics.validate_buckets(ics._DEFAULT_BUCKETS) == []

    def test_unknown_kind_flagged(self):
        errs = ics.validate_buckets({"agenda": ["task", "bogus"],
                                      "events": ["event", "milestone",
                                                 "reminder", "cronograma"]})
        assert any("bogus" in e for e in errs)

    def test_duplicate_kind_flagged(self):
        errs = ics.validate_buckets({"a": ["task"], "b": ["task", "event",
                                                          "milestone",
                                                          "reminder",
                                                          "cronograma"]})
        assert any("duplicado" in e for e in errs)

    def test_missing_kind_flagged(self):
        errs = ics.validate_buckets({"agenda": ["task", "reminder"]})
        # event/milestone/cronograma all missing
        assert sum("no aparece" in e for e in errs) >= 3


# ── Calendar wrapper ─────────────────────────────────────────────────────────

class TestCalendarWrapper:
    def test_has_header_and_footer(self):
        out = ics._calendar_wrapper("Test", ["BEGIN:VEVENT", "END:VEVENT"])
        assert out.startswith("BEGIN:VCALENDAR")
        assert "END:VCALENDAR" in out
        assert "VERSION:2.0" in out
        assert "X-WR-CALNAME:Test" in out


# ── Project render (with fixture) ────────────────────────────────────────────

@pytest.fixture
def proj_with_items(orbit_env):
    agenda = orbit_env["proj_dir"] / "agenda.md"
    agenda.write_text(
        "# Agenda\n\n"
        "## ✅ Tareas\n"
        "- [ ] Write paper (2026-05-15) ⏰10:00 [orbit:abc12345]\n"
        "- [ ] Weekly cleanup (2026-05-13) ⏰09:00 🔄weekly [orbit:cccccccc]\n\n"
        "## 📅 Eventos\n"
        "2026-06-01 — Kickoff ⏰09:00-10:00 [orbit:cafebabe]\n\n"
    )
    return orbit_env


class TestRenderProject:
    def test_emits_vevents_for_all_kinds(self, proj_with_items):
        out = ics.render_project(proj_with_items["proj_dir"],
                                  window_start=date(2026, 5, 1),
                                  window_end=date(2026, 7, 1))
        assert "UID:abc12345@orbit" in out
        assert "UID:cafebabe@orbit" in out

    def test_recurring_task_expanded(self, proj_with_items):
        out = ics.render_project(proj_with_items["proj_dir"],
                                  window_start=date(2026, 5, 1),
                                  window_end=date(2026, 6, 5))
        # 5/13, 5/20, 5/27, 6/3 — 4 occurrences
        n = out.count("UID:cccccccc-")
        assert n == 4


# ── Snapshot diff ────────────────────────────────────────────────────────────

class TestSnapshotDiff:
    def _wrap(self, body):
        return ics._calendar_wrapper("test", body)

    def _event(self, uid, dtstart, summary):
        return [
            "BEGIN:VEVENT",
            f"UID:{uid}",
            "DTSTAMP:20260101T000000Z",
            f"DTSTART:{dtstart}",
            f"SUMMARY:{summary}",
            "END:VEVENT",
        ]

    def test_no_change_returns_empty(self):
        a = self._wrap(self._event("u1", "20260515T100000", "X"))
        b = self._wrap(self._event("u1", "20260515T100000", "X"))
        d = ics.diff_snapshot(a, b)
        assert d == {"added": [], "removed": [], "changed": []}

    def test_dtstamp_ignored(self):
        a = self._wrap([
            "BEGIN:VEVENT", "UID:u1",
            "DTSTAMP:20260101T000000Z", "DTSTART:20260515T100000",
            "SUMMARY:X", "END:VEVENT"])
        b = self._wrap([
            "BEGIN:VEVENT", "UID:u1",
            "DTSTAMP:20260202T000000Z",    # different!
            "DTSTART:20260515T100000",
            "SUMMARY:X", "END:VEVENT"])
        assert ics.diff_snapshot(a, b) == {"added": [], "removed": [],
                                            "changed": []}

    def test_added_event(self):
        a = self._wrap(self._event("u1", "20260515T100000", "X")
                       + self._event("u2", "20260516T100000", "Y"))
        b = self._wrap(self._event("u1", "20260515T100000", "X"))
        d = ics.diff_snapshot(a, b)
        assert d["added"] == ["u2"]

    def test_removed_event(self):
        a = self._wrap(self._event("u1", "20260515T100000", "X"))
        b = self._wrap(self._event("u1", "20260515T100000", "X")
                       + self._event("u2", "20260516T100000", "Y"))
        d = ics.diff_snapshot(a, b)
        assert d["removed"] == ["u2"]

    def test_changed_attr(self):
        a = self._wrap(self._event("u1", "20260515T100000", "X"))
        b = self._wrap(self._event("u1", "20260515T113000", "X"))
        d = ics.diff_snapshot(a, b)
        assert d["changed"] == [("u1", ["DTSTART"])]


# ── Write workspace (filesystem) ─────────────────────────────────────────────

class TestWriteWorkspace:
    def test_writes_buckets_and_per_project(self, orbit_env, monkeypatch):
        agenda = orbit_env["proj_dir"] / "agenda.md"
        agenda.write_text(
            "# Agenda\n\n"
            "## ✅ Tareas\n"
            "- [ ] T (2026-05-15) [orbit:abc12345]\n\n"
            "## 📅 Eventos\n"
            "2026-06-01 — E [orbit:cafebabe]\n\n"
        )
        # Block calendar reload (would need Calendar.app).
        monkeypatch.setattr("core.gsync._calendar_app_running", lambda: False)
        cloud = orbit_env["tmp"] / "cloud"
        cloud.mkdir()
        n = ics.write_workspace(cloud)
        cal_dir = cloud / "calendar"
        # Cloud has .ics only (no snapshots) — they're not useful to
        # Calendar.app subscribers and just bloat OneDrive sync.
        assert (cal_dir / "agenda.ics").exists()
        assert (cal_dir / "events.ics").exists()
        assert (cal_dir / "projects").exists()
        assert not (cal_dir / "agenda.ics.snapshot").exists()
        # First write returns 2 buckets + 1 project = 3 files.
        assert n == 3
        # Local mirror (gitignored) holds .ics + snapshots.
        local = orbit_env["tmp"] / ".cache" / "ics"
        assert (local / "agenda.ics").exists()
        assert (local / "events.ics").exists()
        assert (local / "agenda.ics.snapshot").exists()
        assert (local / "events.ics.snapshot").exists()
        # Mirror and cloud have identical content.
        assert (local / "agenda.ics").read_text() == (cal_dir / "agenda.ics").read_text()

    def test_aborts_on_invalid_buckets(self, orbit_env, monkeypatch, capsys):
        monkeypatch.setattr("core.gsync._calendar_app_running", lambda: False)
        # Inject a broken config.
        monkeypatch.setattr("core.ics.get_buckets",
                            lambda: {"agenda": ["task", "bogus"]})
        cloud = orbit_env["tmp"] / "cloud"
        cloud.mkdir()
        n = ics.write_workspace(cloud)
        assert n == 0
        out = capsys.readouterr().out
        assert "bogus" in out


# ── diff_workspace (preview) ────────────────────────────────────────────────

class TestDiffWorkspace:
    def _setup_baseline(self, orbit_env, monkeypatch):
        """Write a workspace .ics baseline and return paths."""
        agenda = orbit_env["proj_dir"] / "agenda.md"
        agenda.write_text(
            "# Agenda\n\n"
            "## ✅ Tareas\n"
            "- [ ] T (2026-05-15) [orbit:abc12345]\n\n"
        )
        monkeypatch.setattr("core.gsync._calendar_app_running", lambda: False)
        cloud = orbit_env["tmp"] / "cloud"
        cloud.mkdir()
        ics.write_workspace(cloud)
        return agenda, cloud

    def test_no_changes_returns_empty(self, orbit_env, monkeypatch):
        self._setup_baseline(orbit_env, monkeypatch)
        # Render again without editing agenda — no pending changes.
        d = ics.diff_workspace()
        assert d == {}

    def _has_uid(self, uids, orbit_id):
        """UIDs in .ics include @orbit suffix (and -date for recurrents)."""
        return any(orbit_id in u for u in uids)

    def test_detects_added_uid(self, orbit_env, monkeypatch):
        agenda, _ = self._setup_baseline(orbit_env, monkeypatch)
        # Append a new task.
        agenda.write_text(agenda.read_text() +
                          "- [ ] T2 (2026-05-20) [orbit:deadbeef]\n")
        d = ics.diff_workspace()
        files = list(d.keys())
        assert any("agenda.ics" in f for f in files)
        any_added = any(self._has_uid(d[f]["added"], "deadbeef") for f in files)
        assert any_added
        # SUMMARY plumbing populated.
        for f in files:
            for uid, summary in d[f].get("summaries", {}).items():
                if "deadbeef" in uid:
                    assert "T2" in summary

    def test_detects_changed_uid(self, orbit_env, monkeypatch):
        agenda, _ = self._setup_baseline(orbit_env, monkeypatch)
        # Move date of the existing task.
        agenda.write_text(
            "# Agenda\n\n"
            "## ✅ Tareas\n"
            "- [ ] T (2026-06-01) [orbit:abc12345]\n\n"
        )
        d = ics.diff_workspace()
        any_changed = False
        for f, info in d.items():
            for uid, attrs in info["changed"]:
                if "abc12345" in uid:
                    any_changed = True
                    assert "DTSTART" in attrs or "DTEND" in attrs
        assert any_changed

    def test_detects_removed_uid(self, orbit_env, monkeypatch):
        agenda, _ = self._setup_baseline(orbit_env, monkeypatch)
        # Strip the task entirely.
        agenda.write_text("# Agenda\n\n## ✅ Tareas\n")
        d = ics.diff_workspace()
        any_removed = any(self._has_uid(info["removed"], "abc12345")
                          for info in d.values())
        assert any_removed

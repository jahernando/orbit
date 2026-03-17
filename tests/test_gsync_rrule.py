"""Tests for RRULE mapping and snapshot/drift detection (Changes 2 & 3)."""
import pytest
from core.gsync import _recur_to_rrule, _make_snapshot, _diff_snapshot


# ── RRULE mapping ─────────────────────────────────────────────────────────────

class TestRecurToRrule:

    def test_daily(self):
        assert _recur_to_rrule("daily") == ["RRULE:FREQ=DAILY"]

    def test_weekly(self):
        assert _recur_to_rrule("weekly") == ["RRULE:FREQ=WEEKLY"]

    def test_monthly(self):
        assert _recur_to_rrule("monthly") == ["RRULE:FREQ=MONTHLY"]

    def test_weekdays(self):
        assert _recur_to_rrule("weekdays") == ["RRULE:FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR"]

    def test_every_2_weeks(self):
        assert _recur_to_rrule("every-2-weeks") == ["RRULE:FREQ=WEEKLY;INTERVAL=2"]

    def test_every_3_days(self):
        assert _recur_to_rrule("every-3-days") == ["RRULE:FREQ=DAILY;INTERVAL=3"]

    def test_every_6_months(self):
        assert _recur_to_rrule("every-6-months") == ["RRULE:FREQ=MONTHLY;INTERVAL=6"]

    def test_first_monday(self):
        assert _recur_to_rrule("first-monday") == ["RRULE:FREQ=MONTHLY;BYDAY=1MO"]

    def test_first_lunes(self):
        """Spanish weekday names work too."""
        assert _recur_to_rrule("first-lunes") == ["RRULE:FREQ=MONTHLY;BYDAY=1MO"]

    def test_last_friday(self):
        assert _recur_to_rrule("last-friday") == ["RRULE:FREQ=MONTHLY;BYDAY=-1FR"]

    def test_last_viernes(self):
        assert _recur_to_rrule("last-viernes") == ["RRULE:FREQ=MONTHLY;BYDAY=-1FR"]

    def test_with_until(self):
        result = _recur_to_rrule("weekly", "2026-06-30")
        assert result == ["RRULE:FREQ=WEEKLY;UNTIL=20260630T235959Z"]

    def test_daily_with_until(self):
        result = _recur_to_rrule("daily", "2026-12-31")
        assert result == ["RRULE:FREQ=DAILY;UNTIL=20261231T235959Z"]

    def test_unknown_pattern_returns_empty(self):
        assert _recur_to_rrule("bogus") == []

    def test_every_with_until(self):
        result = _recur_to_rrule("every-2-weeks", "2026-09-01")
        assert result == ["RRULE:FREQ=WEEKLY;INTERVAL=2;UNTIL=20260901T235959Z"]

    def test_first_with_until(self):
        result = _recur_to_rrule("first-monday", "2026-12-31")
        assert result == ["RRULE:FREQ=MONTHLY;BYDAY=1MO;UNTIL=20261231T235959Z"]

    def test_all_spanish_weekdays(self):
        """All Spanish weekday names map correctly."""
        mapping = {
            "lunes": "MO", "martes": "TU", "miercoles": "WE",
            "jueves": "TH", "viernes": "FR", "sabado": "SA", "domingo": "SU",
        }
        for es, code in mapping.items():
            result = _recur_to_rrule(f"first-{es}")
            assert result == [f"RRULE:FREQ=MONTHLY;BYDAY=1{code}"], f"Failed for {es}"

    def test_all_english_weekdays(self):
        """All English weekday names map correctly."""
        mapping = {
            "monday": "MO", "tuesday": "TU", "wednesday": "WE",
            "thursday": "TH", "friday": "FR", "saturday": "SA", "sunday": "SU",
        }
        for en, code in mapping.items():
            result = _recur_to_rrule(f"last-{en}")
            assert result == [f"RRULE:FREQ=MONTHLY;BYDAY=-1{code}"], f"Failed for {en}"


# ── Snapshot ──────────────────────────────────────────────────────────────────

class TestMakeSnapshot:

    def test_extracts_core_fields(self):
        item = {"desc": "Test", "date": "2026-04-01", "time": "09:00",
                "recur": "weekly", "status": "pending",
                "_gtask_id": "abc123", "notes": ["some note"]}
        snap = _make_snapshot(item)
        assert snap == {"desc": "Test", "date": "2026-04-01",
                        "time": "09:00", "recur": "weekly", "status": "pending"}
        assert "_gtask_id" not in snap
        assert "notes" not in snap

    def test_omits_none_fields(self):
        item = {"desc": "Simple", "date": "2026-04-01", "status": "pending",
                "time": None, "recur": None, "ring": None}
        snap = _make_snapshot(item)
        assert snap == {"desc": "Simple", "date": "2026-04-01", "status": "pending"}

    def test_includes_all_present_fields(self):
        item = {"desc": "Full", "date": "2026-04-01", "end": "2026-04-03",
                "time": "09:00-17:00", "recur": "monthly", "until": "2026-12-31",
                "ring": "1d", "status": "pending"}
        snap = _make_snapshot(item)
        assert snap == item  # all fields are snapshot fields


# ── Drift detection ──────────────────────────────────────────────────────────

class TestDiffSnapshot:

    def test_no_diff_when_identical(self):
        snap = {"desc": "Test", "date": "2026-04-01", "status": "pending"}
        current = {"desc": "Test", "date": "2026-04-01", "status": "pending"}
        assert _diff_snapshot(current, snap) == []

    def test_detects_changed_field(self):
        snap = {"desc": "Test", "date": "2026-04-01", "time": "09:00", "status": "pending"}
        current = {"desc": "Test", "date": "2026-04-01", "time": "10:00", "status": "pending"}
        diffs = _diff_snapshot(current, snap)
        assert len(diffs) == 1
        assert "time: 09:00 → 10:00" in diffs[0]

    def test_detects_added_field(self):
        snap = {"desc": "Test", "date": "2026-04-01", "status": "pending"}
        current = {"desc": "Test", "date": "2026-04-01", "status": "pending", "ring": "1h"}
        diffs = _diff_snapshot(current, snap)
        assert len(diffs) == 1
        assert "ring" in diffs[0]
        assert "(vacío) → 1h" in diffs[0]

    def test_detects_removed_field(self):
        snap = {"desc": "Test", "date": "2026-04-01", "ring": "1h", "status": "pending"}
        current = {"desc": "Test", "date": "2026-04-01", "status": "pending"}
        diffs = _diff_snapshot(current, snap)
        assert len(diffs) == 1
        assert "ring" in diffs[0]
        assert "(eliminado)" in diffs[0]

    def test_detects_multiple_changes(self):
        snap = {"desc": "Old name", "date": "2026-04-01", "time": "09:00", "status": "pending"}
        current = {"desc": "New name", "date": "2026-04-02", "time": "10:00", "status": "pending"}
        diffs = _diff_snapshot(current, snap)
        assert len(diffs) == 3

    def test_no_snapshot_returns_empty(self):
        current = {"desc": "Test", "status": "pending"}
        assert _diff_snapshot(current, None) == []
        assert _diff_snapshot(current, {}) == []

    def test_status_change_detected(self):
        snap = {"desc": "Test", "status": "pending"}
        current = {"desc": "Test", "status": "done"}
        diffs = _diff_snapshot(current, snap)
        assert len(diffs) == 1
        assert "status: pending → done" in diffs[0]

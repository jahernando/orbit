"""Tests for views/ring/export.py — ring.json payload builder."""

import json
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

from views.ring.export import (
    DEFAULT_DAYS,
    DEFAULT_ENABLED,
    _backfill_orbit_ids,
    _default_list_name,
    _due_iso,
    _expand_occurrences,
    _is_active,
    _iter_kind_items,
    _load_ring_config,
    _ring_to_alarm_minutes,
    build_payload,
    write_payload,
)


# ──────────────────────────────────────────────────────────────────────────────
# _due_iso
# ──────────────────────────────────────────────────────────────────────────────

class TestDueIso:
    def test_simple_time(self):
        assert _due_iso("2026-05-15", "09:30") == "2026-05-15T09:30:00"

    def test_event_range_uses_start(self):
        assert _due_iso("2026-05-15", "10:00-11:30") == "2026-05-15T10:00:00"

    def test_bad_date(self):
        assert _due_iso("not-a-date", "09:00") is None

    def test_no_time(self):
        assert _due_iso("2026-05-15", "") is None
        assert _due_iso("2026-05-15", None) is None

    def test_bad_time(self):
        assert _due_iso("2026-05-15", "noon") is None


# ──────────────────────────────────────────────────────────────────────────────
# _ring_to_alarm_minutes
# ──────────────────────────────────────────────────────────────────────────────

class TestRingToAlarmMinutes:
    def _due(self):
        return datetime(2026, 5, 15, 16, 0)

    def test_relative_minutes(self):
        assert _ring_to_alarm_minutes("5m", self._due()) == 5
        assert _ring_to_alarm_minutes("30m", self._due()) == 30

    def test_relative_hours(self):
        assert _ring_to_alarm_minutes("2h", self._due()) == 120

    def test_relative_days(self):
        assert _ring_to_alarm_minutes("1d", self._due()) == 24 * 60

    def test_time_only_before_due(self):
        # ring at 09:00 with due at 16:00 → 7h = 420m before
        assert _ring_to_alarm_minutes("09:00", self._due()) == 420

    def test_time_only_after_due_negative(self):
        # ring at 18:00 with due at 16:00 → -2h = -120m
        assert _ring_to_alarm_minutes("18:00", self._due()) == -120

    def test_absolute_datetime(self):
        # ring at 2026-05-15 09:00 with due same day 16:00 → 7h before
        assert _ring_to_alarm_minutes("2026-05-15 09:00", self._due()) == 420

    def test_unparseable_returns_none(self):
        assert _ring_to_alarm_minutes("garbage", self._due()) is None


# ──────────────────────────────────────────────────────────────────────────────
# _expand_occurrences
# ──────────────────────────────────────────────────────────────────────────────

class TestExpandOccurrences:
    def test_no_recur_in_window(self):
        item = {"date": "2026-05-16"}
        result = _expand_occurrences(item, date(2026, 5, 14), date(2026, 5, 21))
        assert result == [date(2026, 5, 16)]

    def test_no_recur_outside_window(self):
        item = {"date": "2026-06-01"}
        result = _expand_occurrences(item, date(2026, 5, 14), date(2026, 5, 21))
        assert result == []

    def test_daily_recur(self):
        item = {"date": "2026-05-14", "recur": "daily"}
        result = _expand_occurrences(item, date(2026, 5, 14), date(2026, 5, 16))
        assert result == [date(2026, 5, 14), date(2026, 5, 15), date(2026, 5, 16)]

    def test_weekly_recur(self):
        item = {"date": "2026-05-14", "recur": "weekly"}
        result = _expand_occurrences(item, date(2026, 5, 14), date(2026, 5, 30))
        assert result == [date(2026, 5, 14), date(2026, 5, 21), date(2026, 5, 28)]

    def test_weekdays_recur_skips_weekend(self):
        # 2026-05-15 is Friday → next weekday is Monday 2026-05-18
        item = {"date": "2026-05-15", "recur": "weekdays"}
        result = _expand_occurrences(item, date(2026, 5, 15), date(2026, 5, 20))
        assert date(2026, 5, 16) not in result  # Saturday
        assert date(2026, 5, 17) not in result  # Sunday
        assert date(2026, 5, 18) in result      # Monday

    def test_with_until_clamps_recur(self):
        item = {"date": "2026-05-14", "recur": "daily", "until": "2026-05-16"}
        result = _expand_occurrences(item, date(2026, 5, 14), date(2026, 5, 20))
        assert result == [date(2026, 5, 14), date(2026, 5, 15), date(2026, 5, 16)]

    def test_recur_skips_past_base(self):
        # Base in past, window in future → next valid occurrence inside
        item = {"date": "2026-05-10", "recur": "weekly"}
        result = _expand_occurrences(item, date(2026, 5, 14), date(2026, 5, 25))
        assert result == [date(2026, 5, 17), date(2026, 5, 24)]


# ──────────────────────────────────────────────────────────────────────────────
# _is_active
# ──────────────────────────────────────────────────────────────────────────────

class TestIsActive:
    def test_task_pending(self):
        assert _is_active({"status": "pending"}, "task")

    def test_task_done(self):
        assert not _is_active({"status": "done"}, "task")

    def test_task_cancelled(self):
        assert not _is_active({"status": "cancelled"}, "task")

    def test_reminder_active(self):
        assert _is_active({}, "reminder")
        assert _is_active({"cancelled": False}, "reminder")

    def test_reminder_cancelled(self):
        assert not _is_active({"cancelled": True}, "reminder")

    def test_event_always_active(self):
        assert _is_active({}, "event")
        assert _is_active({"status": "done"}, "event")


# ──────────────────────────────────────────────────────────────────────────────
# _iter_kind_items: filter pipeline
# ──────────────────────────────────────────────────────────────────────────────

class TestIterKindItems:
    def test_skip_no_ring(self):
        items = [{"status": "pending", "date": "2026-05-15", "time": "09:00",
                  "orbit_id": "abcd"}]
        assert list(_iter_kind_items(items, "task", "p1",
                                     date(2026, 5, 14), date(2026, 5, 21),
                                     "Orbit Ring")) == []

    def test_skip_no_time(self):
        items = [{"status": "pending", "date": "2026-05-15", "ring": "5m",
                  "orbit_id": "abcd"}]
        assert list(_iter_kind_items(items, "task", "p1",
                                     date(2026, 5, 14), date(2026, 5, 21),
                                     "Orbit Ring")) == []

    def test_skip_no_orbit_id(self):
        items = [{"status": "pending", "date": "2026-05-15", "time": "09:00",
                  "ring": "5m"}]
        assert list(_iter_kind_items(items, "task", "p1",
                                     date(2026, 5, 14), date(2026, 5, 21),
                                     "Orbit Ring")) == []

    def test_eligible_simple(self):
        items = [{"status": "pending", "date": "2026-05-15", "time": "09:00",
                  "ring": "5m", "orbit_id": "abcd1234", "desc": "Hello"}]
        out = list(_iter_kind_items(items, "task", "p1",
                                    date(2026, 5, 14), date(2026, 5, 21),
                                    "Orbit Ring"))
        assert len(out) == 1
        item = out[0]
        assert item["orbit_id"] == "abcd1234"
        assert item["project"] == "p1"
        assert item["kind"] == "task"
        assert item["title"] == "Hello"
        assert item["due_iso"] == "2026-05-15T09:00:00"
        assert item["alarm_minutes"] == 5
        assert item["list"] == "Orbit Ring"

    def test_recurring_expanded_unique_ids(self):
        items = [{"status": "pending", "date": "2026-05-14", "time": "09:00",
                  "ring": "5m", "orbit_id": "abcd1234", "recur": "daily",
                  "desc": "Daily standup"}]
        out = list(_iter_kind_items(items, "task", "p1",
                                    date(2026, 5, 14), date(2026, 5, 16),
                                    "Orbit Ring"))
        ids = [it["orbit_id"] for it in out]
        assert ids == ["abcd1234-2026-05-14", "abcd1234-2026-05-15", "abcd1234-2026-05-16"]


# ──────────────────────────────────────────────────────────────────────────────
# _load_ring_config: defaults + overrides + clamping
# ──────────────────────────────────────────────────────────────────────────────

class TestLoadRingConfig:
    def test_no_orbit_json(self, tmp_path):
        cfg = _load_ring_config(tmp_path)
        assert cfg == {"enabled": True, "days": 7, "list": tmp_path.name}

    def test_no_ring_section(self, tmp_path):
        (tmp_path / "orbit.json").write_text(json.dumps({"space": "test"}))
        cfg = _load_ring_config(tmp_path)
        assert cfg["enabled"] is True
        assert cfg["days"] == 7
        assert cfg["list"] == tmp_path.name

    def test_disabled_override(self, tmp_path):
        (tmp_path / "orbit.json").write_text(json.dumps({"ring": {"enabled": False}}))
        cfg = _load_ring_config(tmp_path)
        assert cfg["enabled"] is False

    def test_days_override(self, tmp_path):
        (tmp_path / "orbit.json").write_text(json.dumps({"ring": {"days": 14}}))
        assert _load_ring_config(tmp_path)["days"] == 14

    def test_days_clamp_out_of_range(self, tmp_path):
        (tmp_path / "orbit.json").write_text(json.dumps({"ring": {"days": 99}}))
        # Out of range falls back to default
        assert _load_ring_config(tmp_path)["days"] == 7

    def test_days_bad_type(self, tmp_path):
        (tmp_path / "orbit.json").write_text(json.dumps({"ring": {"days": "many"}}))
        assert _load_ring_config(tmp_path)["days"] == 7

    def test_list_override(self, tmp_path):
        (tmp_path / "orbit.json").write_text(json.dumps({"ring": {"list": "Trabajo"}}))
        assert _load_ring_config(tmp_path)["list"] == "Trabajo"

    def test_list_empty_falls_back(self, tmp_path):
        (tmp_path / "orbit.json").write_text(json.dumps({"ring": {"list": "   "}}))
        assert _load_ring_config(tmp_path)["list"] == tmp_path.name

    def test_bad_json_returns_defaults(self, tmp_path):
        (tmp_path / "orbit.json").write_text("{not json")
        cfg = _load_ring_config(tmp_path)
        assert cfg["enabled"] is True
        assert cfg["days"] == 7


# ──────────────────────────────────────────────────────────────────────────────
# build_payload + write_payload schema
# ──────────────────────────────────────────────────────────────────────────────

class TestBuildPayload:
    def test_disabled_empty_items(self, tmp_path):
        # workspace_root with no projects → still produces a valid empty payload
        (tmp_path / "orbit.json").write_text(json.dumps({"ring": {"enabled": False}}))
        payload = build_payload(tmp_path)
        assert payload["items"] == []
        assert payload["enabled"] is False
        assert payload["list"] == tmp_path.name
        assert "window_start" in payload
        assert "window_end" in payload

    def test_window_matches_days(self, tmp_path):
        (tmp_path / "orbit.json").write_text(json.dumps({"ring": {"days": 10}}))
        payload = build_payload(tmp_path, today=date(2026, 5, 14))
        assert payload["window_start"] == "2026-05-14"
        assert payload["window_end"] == "2026-05-24"

    def test_default_list_is_workspace_name(self, tmp_path):
        payload = build_payload(tmp_path)
        assert payload["list"] == tmp_path.name


class TestBackfillOrbitIds:
    def test_assigns_id_when_ring_date_time_present(self):
        data = {"tasks": [{"date": "2026-05-21", "time": "11:00",
                           "ring": "5m", "status": "pending"}],
                "milestones": [], "events": [], "reminders": []}
        n = _backfill_orbit_ids(data)
        assert n == 1
        oid = data["tasks"][0]["orbit_id"]
        assert isinstance(oid, str) and len(oid) == 8
        assert all(c in "0123456789abcdef" for c in oid)

    def test_skips_when_no_ring(self):
        data = {"tasks": [{"date": "2026-05-21", "time": "11:00",
                           "status": "pending"}],
                "milestones": [], "events": [], "reminders": []}
        assert _backfill_orbit_ids(data) == 0
        assert "orbit_id" not in data["tasks"][0] or data["tasks"][0]["orbit_id"] is None

    def test_skips_when_no_time(self):
        data = {"tasks": [{"date": "2026-05-21", "ring": "5m",
                           "status": "pending"}],
                "milestones": [], "events": [], "reminders": []}
        assert _backfill_orbit_ids(data) == 0

    def test_skips_when_no_date(self):
        data = {"tasks": [{"time": "11:00", "ring": "5m",
                           "status": "pending"}],
                "milestones": [], "events": [], "reminders": []}
        assert _backfill_orbit_ids(data) == 0

    def test_preserves_existing_id(self):
        data = {"tasks": [{"date": "2026-05-21", "time": "11:00",
                           "ring": "5m", "orbit_id": "deadbeef",
                           "status": "pending"}],
                "milestones": [], "events": [], "reminders": []}
        assert _backfill_orbit_ids(data) == 0
        assert data["tasks"][0]["orbit_id"] == "deadbeef"

    def test_counts_across_kinds(self):
        common = {"date": "2026-05-21", "time": "11:00", "ring": "5m"}
        data = {
            "tasks":      [{**common, "status": "pending"}],
            "milestones": [{**common, "status": "pending"}],
            "events":     [{**common}],
            "reminders":  [{**common}],
        }
        assert _backfill_orbit_ids(data) == 4
        for k in ("tasks", "milestones", "events", "reminders"):
            assert data[k][0].get("orbit_id")

    def test_unique_ids_per_item(self):
        common = {"date": "2026-05-21", "time": "11:00", "ring": "5m",
                  "status": "pending"}
        data = {"tasks": [dict(common) for _ in range(5)],
                "milestones": [], "events": [], "reminders": []}
        _backfill_orbit_ids(data)
        ids = [t["orbit_id"] for t in data["tasks"]]
        assert len(set(ids)) == 5


class TestBuildPayloadBackfill:
    def test_backfill_persisted_to_agenda(self, tmp_path, monkeypatch):
        """Real round-trip: agenda con ring sin orbit_id → build_payload
        rellena id, lo escribe a agenda.md, y el item entra a ring.json."""
        # Workspace layout: <ws>/<type-emoji-dir>/<project-dir>/<files>
        # The workspace's own orbit.json declares the type emoji vocabulary.
        type_dir = tmp_path / "🌀investigacion"
        proj = type_dir / "🌀p1"
        proj.mkdir(parents=True)
        (proj / "p1-project.md").write_text("# p1\n")
        agenda = proj / "p1-agenda.md"
        agenda.write_text(
            "# Agenda\n\n"
            "## ✅ Tareas\n"
            "- [ ] Stand-up (2026-05-21) ⏰11:00 🔔5m\n"
        )
        (tmp_path / "orbit.json").write_text(json.dumps({
            "types": {"investigacion": "🌀"},
        }))
        # Point ORBIT_HOME elsewhere so _projects_under uses the workspace
        # branch (_iter_workspace_projects), which reads workspace orbit.json.
        import core.config as _cfg
        import views.ring.export as _exp
        elsewhere = tmp_path / "_not_home"
        elsewhere.mkdir()
        monkeypatch.setattr(_cfg, "ORBIT_HOME", elsewhere)
        monkeypatch.setattr(_exp, "ORBIT_HOME", elsewhere)

        payload = build_payload(tmp_path, today=date(2026, 5, 21))

        assert payload["backfilled"] == 1
        # agenda.md should now carry an orbit-id (new format: invisible
        # <!-- orbit:XXXXXXXX --> identity comment on the item header).
        text = agenda.read_text()
        import re
        m = re.search(r"<!-- orbit:([0-9a-f]{8}) -->", text)
        assert m is not None
        # And the item should have entered the payload
        assert len(payload["items"]) == 1
        assert payload["items"][0]["orbit_id"] == m.group(1)


class TestWritePayload:
    def test_atomic_write(self, tmp_path):
        payload = {"items": [{"a": 1}], "list": "foo"}
        path = write_payload(tmp_path, payload)
        assert path.exists()
        assert path == tmp_path / ".reminders" / "ring.json"
        roundtrip = json.loads(path.read_text())
        assert roundtrip == payload

    def test_overwrites_existing(self, tmp_path):
        write_payload(tmp_path, {"items": [], "v": 1})
        write_payload(tmp_path, {"items": [], "v": 2})
        data = json.loads((tmp_path / ".reminders" / "ring.json").read_text())
        assert data["v"] == 2


# ──────────────────────────────────────────────────────────────────────────────
# _default_list_name
# ──────────────────────────────────────────────────────────────────────────────

class TestDefaultListName:
    def test_workspace_dir_name(self, tmp_path):
        ws = tmp_path / "🚀foo"
        ws.mkdir()
        assert _default_list_name(ws) == "🚀foo"

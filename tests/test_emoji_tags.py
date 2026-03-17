"""Tests for emoji tag format migration (Change 1).

Verifies that:
- Both old bracket format and new emoji format parse identically
- Output always uses emoji format
- Round-trips work correctly
"""
import pytest
from core.agenda_cmds import (
    _parse_task_line, _format_task_line,
    _parse_event_line, _format_event_line,
)


# ── Task parsing: backward compat ─────────────────────────────────────────────

class TestTaskEmojiBackwardCompat:
    """Old [bracket] and new emoji formats must produce identical dicts."""

    def test_time_both_formats(self):
        old = _parse_task_line("- [ ] Call (2026-04-01) [time:09:00]")
        new = _parse_task_line("- [ ] Call (2026-04-01) ⏰09:00")
        assert old == new
        assert old["time"] == "09:00"

    def test_ring_both_formats(self):
        old = _parse_task_line("- [ ] Call (2026-04-01) [ring:30m]")
        new = _parse_task_line("- [ ] Call (2026-04-01) 🔔30m")
        assert old == new
        assert old["ring"] == "30m"

    def test_recur_both_formats(self):
        old = _parse_task_line("- [ ] Weekly (2026-04-01) [recur:weekly]")
        new = _parse_task_line("- [ ] Weekly (2026-04-01) 🔄weekly")
        assert old == new
        assert old["recur"] == "weekly"

    def test_recur_with_until_both_formats(self):
        old = _parse_task_line("- [ ] Weekly (2026-04-01) [recur:weekly:2026-06-30]")
        new = _parse_task_line("- [ ] Weekly (2026-04-01) 🔄weekly:2026-06-30")
        assert old == new
        assert old["recur"] == "weekly"
        assert old["until"] == "2026-06-30"

    def test_synced_both_formats(self):
        old = _parse_task_line("- [ ] Task (2026-04-01) [G]")
        new = _parse_task_line("- [ ] Task (2026-04-01) ☁️")
        assert old == new
        assert old["synced"] is True

    def test_all_attrs_both_formats(self):
        old = _parse_task_line(
            "- [ ] Full (2026-04-01) [time:09:00-10:00] [recur:weekly:2026-12-31] [ring:1h] [G]"
        )
        new = _parse_task_line(
            "- [ ] Full (2026-04-01) ⏰09:00-10:00 🔄weekly:2026-12-31 🔔1h ☁️"
        )
        assert old == new
        assert old["desc"] == "Full"
        assert old["time"] == "09:00-10:00"
        assert old["recur"] == "weekly"
        assert old["until"] == "2026-12-31"
        assert old["ring"] == "1h"
        assert old["synced"] is True


# ── Event parsing: backward compat ────────────────────────────────────────────

class TestEventEmojiBackwardCompat:
    """Old [bracket] and new emoji formats must produce identical dicts."""

    def test_end_both_formats(self):
        old = _parse_event_line("2026-04-01 — Conference [end:2026-04-03]")
        new = _parse_event_line("2026-04-01 — Conference →2026-04-03")
        assert old == new
        assert old["end"] == "2026-04-03"

    def test_time_both_formats(self):
        old = _parse_event_line("2026-04-01 — Standup [time:09:00-09:30]")
        new = _parse_event_line("2026-04-01 — Standup ⏰09:00-09:30")
        assert old == new
        assert old["time"] == "09:00-09:30"

    def test_recur_with_until(self):
        old = _parse_event_line("2026-04-01 — Sync [recur:weekly:2026-06-30]")
        new = _parse_event_line("2026-04-01 — Sync 🔄weekly:2026-06-30")
        assert old == new
        assert old["recur"] == "weekly"
        assert old["until"] == "2026-06-30"

    def test_all_attrs_both_formats(self):
        old = _parse_event_line(
            "2026-04-01 — Retreat [end:2026-04-03] [time:09:00] [recur:monthly] [ring:1d] [G]"
        )
        new = _parse_event_line(
            "2026-04-01 — Retreat →2026-04-03 ⏰09:00 🔄monthly 🔔1d ☁️"
        )
        assert old == new


# ── Format output always uses emojis ──────────────────────────────────────────

class TestFormatOutputEmoji:

    def test_task_format_uses_emojis(self):
        t = {"status": "pending", "desc": "Task", "date": "2026-04-01",
             "time": "09:00", "recur": "daily", "until": None,
             "ring": "15m", "synced": True}
        line = _format_task_line(t)
        assert "⏰09:00" in line
        assert "🔄daily" in line
        assert "🔔15m" in line
        assert "☁️" in line
        # Must NOT contain old bracket format
        assert "[time:" not in line
        assert "[recur:" not in line
        assert "[ring:" not in line
        assert "[G]" not in line

    def test_event_format_uses_emojis(self):
        ev = {"date": "2026-04-01", "desc": "Event", "end": "2026-04-02",
              "time": "10:00-12:00", "recur": "weekly", "until": "2026-06-30",
              "ring": "1h", "synced": True}
        line = _format_event_line(ev)
        assert "→2026-04-02" in line
        assert "⏰10:00-12:00" in line
        assert "🔄weekly:2026-06-30" in line
        assert "🔔1h" in line
        assert "☁️" in line
        assert "[end:" not in line
        assert "[time:" not in line
        assert "[recur:" not in line

    def test_task_no_attrs_clean(self):
        t = {"status": "pending", "desc": "Simple", "date": None,
             "time": None, "recur": None, "until": None,
             "ring": None, "synced": False}
        line = _format_task_line(t)
        assert line == "- [ ] Simple"

    def test_old_format_roundtrip_converts(self):
        """Parsing old format and re-formatting should produce emoji format."""
        old_line = "- [ ] Review (2026-04-01) [time:14:00] [recur:weekly] [ring:30m] [G]"
        t = _parse_task_line(old_line)
        new_line = _format_task_line(t)
        assert "⏰14:00" in new_line
        assert "🔄weekly" in new_line
        assert "🔔30m" in new_line
        assert "☁️" in new_line
        # No old bracket attrs (ignore the - [ ] checkbox)
        after_checkbox = new_line.split("] ", 1)[1]
        assert "[" not in after_checkbox


# ── Description extraction is clean ──────────────────────────────────────────

class TestDescriptionClean:
    """Emoji attrs must not leak into the description field."""

    def test_task_desc_clean_new_format(self):
        t = _parse_task_line("- [ ] My task (2026-04-01) ⏰09:00 🔄weekly 🔔1h ☁️")
        assert t["desc"] == "My task"

    def test_task_desc_clean_old_format(self):
        t = _parse_task_line("- [ ] My task (2026-04-01) [time:09:00] [recur:weekly] [ring:1h] [G]")
        assert t["desc"] == "My task"

    def test_event_desc_clean_new_format(self):
        e = _parse_event_line("2026-04-01 — My event →2026-04-02 ⏰09:00 🔄weekly 🔔1h ☁️")
        assert e["desc"] == "My event"

    def test_event_desc_clean_old_format(self):
        e = _parse_event_line("2026-04-01 — My event [end:2026-04-02] [time:09:00] [recur:weekly] [ring:1h] [G]")
        assert e["desc"] == "My event"

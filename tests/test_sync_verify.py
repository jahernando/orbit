"""Tests for the v0.30 verify-after-sync feature:
- ``_verify_calendar_event`` (read-back AppleScript)
- `.gsync-failures.json` journal (record / clear)
- ``set_cloud_verified`` toggling ☁️ in the agenda line
- ``sync_item`` calendar branch wiring all of the above
"""
import json
from pathlib import Path

import pytest

from core import gsync


# ── Failure journal ──────────────────────────────────────────────────────────

class TestFailureJournal:
    def test_save_creates_file(self, tmp_path):
        gsync._save_failures(tmp_path, {"k1": {"reason": "x"}})
        assert (tmp_path / ".gsync-failures.json").exists()

    def test_save_empty_removes_file(self, tmp_path):
        gsync._save_failures(tmp_path, {"k1": {"reason": "x"}})
        gsync._save_failures(tmp_path, {})
        assert not (tmp_path / ".gsync-failures.json").exists()

    def test_load_missing_returns_empty(self, tmp_path):
        assert gsync._load_failures(tmp_path) == {}

    def test_record_and_clear(self, tmp_path):
        gsync._record_failure(tmp_path, "k1", {"reason": "a"})
        gsync._record_failure(tmp_path, "k2", {"reason": "b"})
        assert set(gsync._load_failures(tmp_path).keys()) == {"k1", "k2"}
        gsync._clear_failure(tmp_path, "k1")
        assert set(gsync._load_failures(tmp_path).keys()) == {"k2"}

    def test_clear_missing_is_noop(self, tmp_path):
        gsync._clear_failure(tmp_path, "ghost")  # should not raise


# ── Verify: parses AppleScript output and compares ──────────────────────────

class TestVerifyCalendarEvent:
    def test_missing_event(self, monkeypatch):
        monkeypatch.setattr(gsync, "_osa", lambda script, timeout=30: "MISSING")
        ok, reason = gsync._verify_calendar_event(
            "uid", "cal", "summary", "2030-05-15T10:00")
        assert ok is False
        assert "missing" in reason.lower()

    def test_no_response(self, monkeypatch):
        monkeypatch.setattr(gsync, "_osa", lambda script, timeout=30: None)
        ok, reason = gsync._verify_calendar_event(
            "uid", "cal", "summary", "2030-05-15T10:00")
        assert ok is False
        assert "no response" in reason.lower()

    def test_summary_mismatch(self, monkeypatch):
        # AppleScript output: y|mo|d|h|mn|summary
        monkeypatch.setattr(gsync, "_osa",
                             lambda *a, **k: "2030|5|15|10|0|other")
        ok, reason = gsync._verify_calendar_event(
            "uid", "cal", "expected", "2030-05-15T10:00")
        assert ok is False
        assert "summary" in reason.lower()

    def test_start_mismatch(self, monkeypatch):
        monkeypatch.setattr(gsync, "_osa",
                             lambda *a, **k: "2030|5|15|9|0|expected")
        ok, reason = gsync._verify_calendar_event(
            "uid", "cal", "expected", "2030-05-15T10:00")
        assert ok is False
        assert "start" in reason.lower()

    def test_match(self, monkeypatch):
        monkeypatch.setattr(gsync, "_osa",
                             lambda *a, **k: "2030|5|15|10|0|expected")
        ok, reason = gsync._verify_calendar_event(
            "uid", "cal", "expected", "2030-05-15T10:00")
        assert ok is True
        assert reason == ""


# ── set_cloud_verified: toggles ☁️ in agenda.md ─────────────────────────────

class TestSetCloudVerified:
    def _make_project(self, tmp_path, agenda_text):
        proj = tmp_path / "💻test"
        proj.mkdir()
        (proj / "test-agenda.md").write_text(agenda_text)
        # Stub resolve_file to return the path we just wrote.
        return proj

    def test_adds_marker_to_matching_orbit_id(self, tmp_path, monkeypatch):
        from core.agenda_cmds import set_cloud_verified
        proj = self._make_project(tmp_path, (
            "# Agenda\n\n## ✅ Tareas\n\n"
            "- [ ] X (2030-05-15) ⏰10:00 [orbit:abcd1234]\n"
        ))
        monkeypatch.setattr("core.log.resolve_file",
                             lambda pd, kind: proj / "test-agenda.md")
        ok = set_cloud_verified(proj, "abcd1234", True)
        assert ok is True
        text = (proj / "test-agenda.md").read_text()
        assert "☁️" in text
        assert "[orbit:abcd1234]" in text

    def test_removes_marker(self, tmp_path, monkeypatch):
        from core.agenda_cmds import set_cloud_verified
        proj = self._make_project(tmp_path, (
            "# Agenda\n\n## ✅ Tareas\n\n"
            "- [ ] X (2030-05-15) ⏰10:00 ☁️ [orbit:abcd1234]\n"
        ))
        monkeypatch.setattr("core.log.resolve_file",
                             lambda pd, kind: proj / "test-agenda.md")
        set_cloud_verified(proj, "abcd1234", False)
        text = (proj / "test-agenda.md").read_text()
        assert "☁️" not in text
        assert "[orbit:abcd1234]" in text

    def test_noop_when_orbit_id_not_found(self, tmp_path, monkeypatch):
        from core.agenda_cmds import set_cloud_verified
        proj = self._make_project(tmp_path, (
            "# Agenda\n\n## ✅ Tareas\n\n"
            "- [ ] X (2030-05-15) ⏰10:00 [orbit:abcd1234]\n"
        ))
        monkeypatch.setattr("core.log.resolve_file",
                             lambda pd, kind: proj / "test-agenda.md")
        ok = set_cloud_verified(proj, "ffffffff", True)
        assert ok is False
        # Original line untouched.
        assert "☁️" not in (proj / "test-agenda.md").read_text()


# ── Edit clears cloud_verified ───────────────────────────────────────────────

class TestApplyEditsClearsCloudVerified:
    def test_edit_clears_marker(self):
        from core.agenda_cmds import _apply_edits
        item = {"desc": "X", "date": "2026-04-01",
                "time": "10:00", "cloud_verified": True,
                "status": "pending"}
        _apply_edits(item, {"time": "11:00"})
        assert item["time"] == "11:00"
        assert item["cloud_verified"] is False

    def test_edit_no_change_still_clears(self):
        """Even a no-op edit invalidates verified state — sync_item must
        re-confirm. The conservative behavior keeps the ☁️ honest."""
        from core.agenda_cmds import _apply_edits
        item = {"desc": "X", "date": "2026-04-01",
                "cloud_verified": True, "status": "pending"}
        _apply_edits(item, {})
        assert item["cloud_verified"] is False

"""Tests for core.calsync — Calendar.app audit + reconcile.

These tests stay unit-level: AppleScript is mocked through gsync._osa
(blocked in conftest), and the bulk-read function is monkeypatched per
test to inject synthetic Calendar state.
"""

import io
import sys
from pathlib import Path

import pytest

from core import calsync


# ── Pure helpers ──────────────────────────────────────────────────────────────

class TestParseTypeFilter:
    def test_default_all(self):
        out = calsync._parse_type_filter(None)
        assert out == {"task", "milestone", "event", "reminder", "cronograma"}

    def test_aliases_map_to_internal(self):
        out = calsync._parse_type_filter("task,ms,ev,rem,crono")
        assert out == {"task", "milestone", "event", "reminder", "cronograma"}

    def test_unknown_token_is_warned_and_skipped(self, capsys):
        out = calsync._parse_type_filter("task,bogus")
        assert out == {"task"}
        assert "bogus" in capsys.readouterr().out

    def test_whitespace_tolerant(self):
        assert calsync._parse_type_filter(" task , ms ") == {"task", "milestone"}


class TestExpectedSummary:
    def test_event_no_emoji(self):
        item = {"desc": "Kickoff", "date": "2030-01-01"}
        assert calsync._expected_summary(item, "event", "p") == "[p] Kickoff"

    def test_task_carries_emoji(self):
        item = {"desc": "Write paper", "date": "2030-01-01"}
        assert "✅" in calsync._expected_summary(item, "task", "p")
        assert "[p]" in calsync._expected_summary(item, "task", "p")

    def test_milestone_emoji(self):
        item = {"desc": "Draft v1", "date": "2030-01-01"}
        assert "🏁" in calsync._expected_summary(item, "milestone", "p")

    def test_reminder_emoji(self):
        item = {"desc": "Llamar X", "date": "2030-01-01"}
        assert "💬" in calsync._expected_summary(item, "reminder", "p")

    def test_cronograma_emoji(self):
        item = {"desc": "crono-paper: write intro", "date": "2030-01-01"}
        assert "📊" in calsync._expected_summary(item, "cronograma", "p")


class TestExpectedStartIso:
    def test_event_with_time(self):
        item = {"desc": "X", "date": "2030-05-15", "time": "10:00-11:00"}
        assert calsync._expected_start_iso(item, "event") == "2030-05-15T10:00"

    def test_event_no_time_starts_at_midnight(self):
        item = {"desc": "X", "date": "2030-05-15"}
        assert calsync._expected_start_iso(item, "event") == "2030-05-15T00:00"

    def test_task_default_9am(self):
        item = {"desc": "X", "date": "2030-05-15"}
        assert calsync._expected_start_iso(item, "task") == "2030-05-15T09:00"

    def test_task_uses_given_time(self):
        item = {"desc": "X", "date": "2030-05-15", "time": "07:30"}
        assert calsync._expected_start_iso(item, "task") == "2030-05-15T07:30"


class TestExpectedEndIso:
    def test_task_synthetic_plus_one_minute(self):
        item = {"desc": "X", "date": "2030-05-15", "time": "10:00"}
        end, synth = calsync._expected_end_iso(item, "task")
        assert end == "2030-05-15T10:01"
        assert synth is True

    def test_event_with_range(self):
        item = {"desc": "X", "date": "2030-05-15", "time": "10:00-11:30"}
        end, synth = calsync._expected_end_iso(item, "event")
        assert end == "2030-05-15T11:30"
        assert synth is False

    def test_event_all_day_uses_2359(self):
        item = {"desc": "X", "date": "2030-05-15"}
        end, synth = calsync._expected_end_iso(item, "event")
        assert end == "2030-05-15T23:59"
        assert synth is False


class TestStripOrbitTag:
    def test_basic(self):
        assert calsync._strip_orbit_tag("note\n\nP [orbit:abcd1234]") \
            == "note\n\nP"

    def test_recurring(self):
        out = calsync._strip_orbit_tag("X [orbit:abcd1234@2030-01-01]")
        assert out == "X"

    def test_no_tag(self):
        assert calsync._strip_orbit_tag("plain text") == "plain text"


class TestStripSummaryPrefix:
    def test_task_prefix(self):
        assert calsync._strip_summary_prefix("[proj] ✅ Hello", "proj",
                                             "task") == "Hello"

    def test_event_prefix(self):
        assert calsync._strip_summary_prefix("[proj] Hello", "proj",
                                             "event") == "Hello"

    def test_no_prefix_passthrough(self):
        assert calsync._strip_summary_prefix("Hello", "proj", "task") == "Hello"


class TestSplitIso:
    def test_with_time(self):
        assert calsync._split_iso("2030-05-15T10:00") == ("2030-05-15", "10:00")

    def test_date_only(self):
        assert calsync._split_iso("2030-05-15") == ("2030-05-15", None)

    def test_empty(self):
        assert calsync._split_iso("") == (None, None)


# ── Diff computation ─────────────────────────────────────────────────────────

class TestComputeDiff:
    def _exp(self, **over):
        base = {
            "summary":     "[p] ✅ Test",
            "start_iso":   "2030-05-15T10:00",
            "end_iso":     "2030-05-15T10:01",
            "description": "Proyecto: p",
        }
        base.update(over)
        return base

    def _act(self, **over):
        base = {
            "summary":     "[p] ✅ Test",
            "start_iso":   "2030-05-15T10:00",
            "end_iso":     "2030-05-15T10:01",
            "description": "Proyecto: p [orbit:deadbeef]",
            "location":    "",
        }
        base.update(over)
        return base

    def test_no_drift_returns_empty(self):
        diffs = calsync._compute_diff(self._exp(), self._act(), ignore_end=True)
        assert diffs == []

    def test_start_drift_caught(self):
        actual = self._act(start_iso="2030-05-15T11:30")
        diffs = calsync._compute_diff(self._exp(), actual, ignore_end=True)
        attrs = [d[0] for d in diffs]
        assert attrs == ["start"]

    def test_summary_drift_caught(self):
        actual = self._act(summary="[p] ✅ Different")
        diffs = calsync._compute_diff(self._exp(), actual, ignore_end=True)
        assert diffs[0][0] == "summary"

    def test_ignore_end_skips_end_diff(self):
        actual = self._act(end_iso="2030-05-15T22:00")
        diffs = calsync._compute_diff(self._exp(), actual, ignore_end=True)
        assert all(d[0] != "end" for d in diffs)

    def test_ignore_end_false_catches_end(self):
        actual = self._act(end_iso="2030-05-15T22:00")
        diffs = calsync._compute_diff(self._exp(), actual, ignore_end=False)
        assert any(d[0] == "end" for d in diffs)

    def test_description_diff_ignores_orbit_tag(self):
        # The orbit-id tag in actual.description must not be reported as drift.
        exp = self._exp(description="Proyecto: p")
        act = self._act(description="Proyecto: p [orbit:deadbeef]")
        diffs = calsync._compute_diff(exp, act, ignore_end=True)
        assert all(d[0] != "description" for d in diffs)

    def test_description_real_drift_caught(self):
        exp = self._exp(description="nueva nota\n\nProyecto: p")
        act = self._act(description="otra cosa\n\nProyecto: p [orbit:deadbeef]")
        diffs = calsync._compute_diff(exp, act, ignore_end=True)
        assert any(d[0] == "description" for d in diffs)


# ── Prompt routing (input mocked) ────────────────────────────────────────────

class TestPrompt:
    def test_choice_1_pushes(self, monkeypatch):
        monkeypatch.setattr("builtins.input", lambda *a: "1")
        action, val = calsync._prompt("start", "o", "c",
                                       allow_pull=True, end_synthetic=False)
        assert action == "push"
        assert val is None

    def test_choice_2_adopts_cal(self, monkeypatch):
        monkeypatch.setattr("builtins.input", lambda *a: "2")
        action, val = calsync._prompt("start", "10:00", "11:30",
                                       allow_pull=True, end_synthetic=False)
        assert action == "adopt"
        assert val == "11:30"

    def test_choice_3_prompts_for_value(self, monkeypatch):
        responses = iter(["3", "09:30"])
        monkeypatch.setattr("builtins.input", lambda *a: next(responses))
        action, val = calsync._prompt("start", "10:00", "11:30",
                                       allow_pull=True, end_synthetic=False)
        assert action == "input"
        assert val == "09:30"

    def test_skip_default(self, monkeypatch):
        monkeypatch.setattr("builtins.input", lambda *a: "s")
        action, val = calsync._prompt("start", "x", "y",
                                       allow_pull=True, end_synthetic=False)
        assert action == "skip"

    def test_pull_blocked_for_synthetic_end(self, monkeypatch):
        # When end is synthetic, "2-cal" must not be offered. Even if the
        # user types "2", we should not interpret it as adopt.
        monkeypatch.setattr("builtins.input", lambda *a: "2")
        action, val = calsync._prompt("end", "10:01", "10:01",
                                       allow_pull=True, end_synthetic=True)
        assert action == "skip"

    def test_pull_blocked_when_allow_pull_false(self, monkeypatch):
        monkeypatch.setattr("builtins.input", lambda *a: "2")
        action, val = calsync._prompt("summary", "a", "b",
                                       allow_pull=False, end_synthetic=False)
        assert action == "skip"

    def test_eof_treated_as_skip(self, monkeypatch):
        def _raise(*a):
            raise EOFError
        monkeypatch.setattr("builtins.input", _raise)
        action, val = calsync._prompt("x", "o", "c",
                                       allow_pull=True, end_synthetic=False)
        assert action == "skip"


# ── Apply pull to agenda.md ──────────────────────────────────────────────────

@pytest.fixture
def agenda_proj(orbit_env):
    """Create an agenda.md with one task carrying [orbit:deadbeef] and
    one event carrying [orbit:cafebabe]."""
    proj_dir = orbit_env["proj_dir"]
    agenda = proj_dir / "agenda.md"
    agenda.write_text(
        "# Agenda\n\n"
        "## ✅ Tareas\n"
        "- [ ] Write paper (2030-05-15) ⏰10:00 [orbit:deadbeef]\n\n"
        "## 📅 Eventos\n"
        "2030-06-01 — Kickoff ⏰09:00-10:00 [orbit:cafebabe]\n\n"
    )
    return orbit_env


class TestApplyPull:
    def test_summary_pull_updates_desc(self, agenda_proj):
        ok = calsync._apply_pull(agenda_proj["proj_dir"], "task",
                                  "deadbeef", "summary",
                                  "[💻testproj] ✅ Different name",
                                  "💻testproj")
        assert ok
        text = (agenda_proj["proj_dir"] / "agenda.md").read_text()
        assert "Different name" in text
        # The new line lost the ☁️ marker (an edit invalidates verify).
        # Originally there was none anyway, so just check it's not added.
        assert "☁️" not in text

    def test_start_pull_updates_date_and_time(self, agenda_proj):
        ok = calsync._apply_pull(agenda_proj["proj_dir"], "task",
                                  "deadbeef", "start", "2030-05-20T11:30",
                                  "💻testproj")
        assert ok
        text = (agenda_proj["proj_dir"] / "agenda.md").read_text()
        assert "(2030-05-20)" in text
        assert "⏰11:30" in text

    def test_event_start_preserves_end_in_range(self, agenda_proj):
        # Original time was "09:00-10:00" — adopting a new start should
        # keep the original end portion.
        ok = calsync._apply_pull(agenda_proj["proj_dir"], "event",
                                  "cafebabe", "start", "2030-06-01T09:30",
                                  "💻testproj")
        assert ok
        text = (agenda_proj["proj_dir"] / "agenda.md").read_text()
        assert "⏰09:30-10:00" in text

    def test_event_end_updates_range(self, agenda_proj):
        ok = calsync._apply_pull(agenda_proj["proj_dir"], "event",
                                  "cafebabe", "end", "2030-06-01T11:00",
                                  "💻testproj")
        assert ok
        text = (agenda_proj["proj_dir"] / "agenda.md").read_text()
        assert "⏰09:00-11:00" in text

    def test_missing_orbit_id_returns_false(self, agenda_proj):
        ok = calsync._apply_pull(agenda_proj["proj_dir"], "task",
                                  "00000000", "summary", "X", "p")
        assert ok is False

    def test_cronograma_pull_refused(self, agenda_proj):
        # Cronograms have no agenda line; pull is rejected by design.
        ok = calsync._apply_pull(agenda_proj["proj_dir"], "cronograma",
                                  "deadbeef", "summary", "X", "p")
        assert ok is False


# ── End-to-end run_calsync (calendar fetch mocked) ──────────────────────────

class TestRunCalsync:
    # NB: ``conftest.py`` already patches ``_applescript_writes_enabled``
    # to True so the v0.33 dormancy gate doesn't short-circuit these
    # end-to-end tests of the legacy AppleScript-write path.

    def test_mutex_all_and_pending(self, capsys):
        rc = calsync.run_calsync("anything", all_flag=True, pending_flag=True)
        assert rc == 2
        out = capsys.readouterr().out
        assert "mutuamente exclusivos" in out

    def test_no_project_returns_2(self, capsys):
        rc = calsync.run_calsync(None)
        assert rc == 2

    def test_calendar_not_running_aborts(self, orbit_env, monkeypatch):
        monkeypatch.setattr("core.gsync._calendar_app_running", lambda: False)
        rc = calsync.run_calsync("testproj")
        assert rc == 1

    def test_all_verified_short_circuits(self, agenda_proj, monkeypatch,
                                          capsys):
        # Mark both items as ☁️ verified in agenda.md, then run default
        # mode (skip verified). Expect "nada que auditar".
        agenda = agenda_proj["proj_dir"] / "agenda.md"
        text = agenda.read_text().replace(
            "[orbit:deadbeef]", "☁️ [orbit:deadbeef]"
        ).replace(
            "[orbit:cafebabe]", "☁️ [orbit:cafebabe]"
        )
        agenda.write_text(text)
        monkeypatch.setattr("core.gsync._calendar_app_running", lambda: True)
        monkeypatch.setattr("core.calsync._fetch_window",
                            lambda *a, **k: [])
        rc = calsync.run_calsync("testproj")
        assert rc == 0
        assert "Nada que auditar" in capsys.readouterr().out

    def test_orphan_reported(self, agenda_proj, monkeypatch, capsys):
        # No orbit items match; one orphan event in the calendar.
        monkeypatch.setattr("core.gsync._calendar_app_running", lambda: True)
        # The agenda items carry orbit-ids → calsync looks them up in the
        # bulk fetch. We return one extra event without orbit-id (orphan)
        # plus the two real ones so the matched ones don't drift.
        def fake_fetch(cal, start, end):
            return [
                # Match for the task
                {"uid": "u1", "summary": "[💻testproj] ✅ Write paper",
                 "start_iso": "2030-05-15T10:00",
                 "end_iso":   "2030-05-15T10:01",
                 "description": "Proyecto: 💻testproj [orbit:deadbeef]",
                 "location": "", "orbit_id": "deadbeef"},
                # Match for the event
                {"uid": "u2", "summary": "[💻testproj] Kickoff",
                 "start_iso": "2030-06-01T09:00",
                 "end_iso":   "2030-06-01T10:00",
                 "description": "Proyecto: 💻testproj [orbit:cafebabe]",
                 "location": "", "orbit_id": "cafebabe"},
                # Orphan (no orbit-id)
                {"uid": "u3", "summary": "Random meeting",
                 "start_iso": "2030-05-20T12:00",
                 "end_iso":   "2030-05-20T13:00",
                 "description": "", "location": "", "orbit_id": None},
            ]
        monkeypatch.setattr("core.calsync._fetch_window", fake_fetch)
        rc = calsync.run_calsync("testproj")
        out = capsys.readouterr().out
        assert rc == 0
        assert "Huérfanos" in out
        assert "Random meeting" in out

    def test_missing_event_offers_push(self, agenda_proj, monkeypatch,
                                        capsys):
        # Fetch returns empty → both items are missing.
        monkeypatch.setattr("core.gsync._calendar_app_running", lambda: True)
        monkeypatch.setattr("core.calsync._fetch_window",
                            lambda *a, **k: [])
        # User answers 's' (skip) twice.
        responses = iter(["s", "s"])
        monkeypatch.setattr("builtins.input", lambda *a: next(responses))
        pushed = []
        monkeypatch.setattr("core.calsync._do_push",
                            lambda *a, **k: pushed.append(a))
        rc = calsync.run_calsync("testproj")
        out = capsys.readouterr().out
        assert rc == 0
        assert "No existe en Calendar" in out
        assert pushed == []  # user skipped

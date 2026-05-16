"""Tests for the watchdog loop: config + tick + REPL surfacing.

The watchdog runs periodically in a daemon thread (see core/shell.py).
Each tick runs doctor first; if issues are found it writes a
`.doctor-pending` marker the REPL surfaces on next prompt; if clean,
it triggers a full refresh (dash + ring + ics).
"""

import json
from unittest.mock import patch

import pytest

from core import shell


@pytest.fixture
def shell_env(tmp_path, monkeypatch):
    """Patch shell.ORBIT_DIR, _DASH_STAMP, _DOCTOR_PENDING into tmp_path."""
    monkeypatch.setattr(shell, "ORBIT_DIR", tmp_path)
    monkeypatch.setattr(shell, "_DASH_STAMP", tmp_path / ".dash-stamp")
    monkeypatch.setattr(shell, "_DOCTOR_PENDING", tmp_path / ".doctor-pending")
    # Reset module-level state
    monkeypatch.setattr(shell, "_doctor_pending_shown", False)
    return tmp_path


# ── _load_watchdog_config ───────────────────────────────────────────────────

class TestLoadWatchdogConfig:
    def test_no_orbit_json(self, tmp_path):
        cfg = shell._load_watchdog_config(tmp_path)
        assert cfg == {"enabled": True, "interval_minutes": 60}

    def test_no_watchdog_section(self, tmp_path):
        (tmp_path / "orbit.json").write_text(json.dumps({"space": "test"}))
        cfg = shell._load_watchdog_config(tmp_path)
        assert cfg["enabled"] is True
        assert cfg["interval_minutes"] == 60

    def test_disabled(self, tmp_path):
        (tmp_path / "orbit.json").write_text(
            json.dumps({"watchdog": {"enabled": False}})
        )
        cfg = shell._load_watchdog_config(tmp_path)
        assert cfg["enabled"] is False

    def test_interval_override(self, tmp_path):
        (tmp_path / "orbit.json").write_text(
            json.dumps({"watchdog": {"interval_minutes": 30}})
        )
        assert shell._load_watchdog_config(tmp_path)["interval_minutes"] == 30

    def test_interval_clamp_out_of_range_low(self, tmp_path):
        (tmp_path / "orbit.json").write_text(
            json.dumps({"watchdog": {"interval_minutes": 1}})
        )
        # Below MIN → default
        assert shell._load_watchdog_config(tmp_path)["interval_minutes"] == 60

    def test_interval_clamp_out_of_range_high(self, tmp_path):
        (tmp_path / "orbit.json").write_text(
            json.dumps({"watchdog": {"interval_minutes": 99999}})
        )
        # Above MAX → default
        assert shell._load_watchdog_config(tmp_path)["interval_minutes"] == 60

    def test_interval_bad_type(self, tmp_path):
        (tmp_path / "orbit.json").write_text(
            json.dumps({"watchdog": {"interval_minutes": "soon"}})
        )
        assert shell._load_watchdog_config(tmp_path)["interval_minutes"] == 60

    def test_bad_json_returns_defaults(self, tmp_path):
        (tmp_path / "orbit.json").write_text("{not json")
        cfg = shell._load_watchdog_config(tmp_path)
        assert cfg["enabled"] is True
        assert cfg["interval_minutes"] == 60

    def test_watchdog_not_a_dict(self, tmp_path):
        (tmp_path / "orbit.json").write_text(
            json.dumps({"watchdog": "yes"})
        )
        cfg = shell._load_watchdog_config(tmp_path)
        assert cfg["enabled"] is True


# ── _watchdog_tick ──────────────────────────────────────────────────────────

class TestWatchdogTick:
    def test_issues_writes_pending_and_skips_refresh(self, shell_env, monkeypatch):
        """Doctor found problems → .doctor-pending written, no refresh."""
        fake_issues = [object(), object(), object()]  # 3 issues
        monkeypatch.setattr("views.doctor.doctor.check_all_projects",
                            lambda: fake_issues)
        refresh_called = {"flag": False}

        def fake_refresh():
            refresh_called["flag"] = True

        monkeypatch.setattr("orbit._run_full_refresh_coalesced", fake_refresh)

        result = shell._watchdog_tick()
        assert result == {"status": "issues", "count": 3}
        assert (shell_env / ".doctor-pending").exists()

        payload = json.loads((shell_env / ".doctor-pending").read_text())
        assert payload["count"] == 3
        assert "timestamp" in payload
        assert refresh_called["flag"] is False

    def test_clean_runs_refresh_and_clears_pending(self, shell_env, monkeypatch):
        """Doctor clean → full refresh runs, stale pending file removed."""
        # Pre-existing pending (left by a previous tick that found issues)
        (shell_env / ".doctor-pending").write_text(json.dumps({"count": 5}))

        monkeypatch.setattr("views.doctor.doctor.check_all_projects", lambda: [])
        refresh_called = {"flag": False}
        monkeypatch.setattr(
            "orbit._run_full_refresh_coalesced",
            lambda: refresh_called.__setitem__("flag", True),
        )

        result = shell._watchdog_tick()
        assert result == {"status": "clean"}
        assert not (shell_env / ".doctor-pending").exists()
        assert refresh_called["flag"] is True

    def test_doctor_exception_returns_error(self, shell_env, monkeypatch):
        """Si doctor lanza excepción, tick devuelve error status sin crashear."""
        def boom():
            raise RuntimeError("doctor exploded")

        monkeypatch.setattr("views.doctor.doctor.check_all_projects", boom)
        result = shell._watchdog_tick()
        assert result["status"] == "error"
        assert "RuntimeError" in result["msg"]

    def test_refresh_exception_does_not_propagate(self, shell_env, monkeypatch):
        """Si _run_full_refresh_coalesced lanza, el tick devuelve clean igualmente
        (los pasos del refresh ya son fail-isolated internamente; este test
        verifica que el wrapper del tick también absorbe)."""
        monkeypatch.setattr("views.doctor.doctor.check_all_projects", lambda: [])

        def boom():
            raise RuntimeError("refresh exploded")

        monkeypatch.setattr("orbit._run_full_refresh_coalesced", boom)
        # Must not raise.
        result = shell._watchdog_tick()
        assert result["status"] == "clean"


# ── _maybe_show_doctor_pending (REPL surfacing) ─────────────────────────────

class TestMaybeShowDoctorPending:
    def test_no_pending_silent(self, shell_env, capsys):
        shell._maybe_show_doctor_pending()
        assert capsys.readouterr().out == ""

    def test_pending_prints_once_per_session(self, shell_env, capsys, monkeypatch):
        (shell_env / ".doctor-pending").write_text(
            json.dumps({"timestamp": "14:30", "count": 3})
        )
        shell._maybe_show_doctor_pending()
        out1 = capsys.readouterr().out
        assert "Doctor" in out1
        assert "14:30" in out1
        assert "3 problema" in out1

        # Second call same session: silent.
        shell._maybe_show_doctor_pending()
        out2 = capsys.readouterr().out
        assert out2 == ""

    def test_pending_singular_when_count_is_one(self, shell_env, capsys):
        (shell_env / ".doctor-pending").write_text(
            json.dumps({"timestamp": "09:00", "count": 1})
        )
        shell._maybe_show_doctor_pending()
        out = capsys.readouterr().out
        # Singular form ("1 problema detectado") without trailing 's'
        assert "1 problema detectado " in out

    def test_pending_corrupt_json_silent(self, shell_env, capsys):
        (shell_env / ".doctor-pending").write_text("{not json")
        # Must not crash and must not print.
        shell._maybe_show_doctor_pending()
        out = capsys.readouterr().out
        assert out == ""


# ── Lifecycle: issues → pending → clean → no pending ────────────────────────

def test_lifecycle_issues_then_clean(shell_env, monkeypatch):
    """Tick 1 finds issues → pending written. Tick 2 clean → pending cleared."""
    # Tick 1: issues
    monkeypatch.setattr("views.doctor.doctor.check_all_projects",
                        lambda: [object(), object()])
    monkeypatch.setattr("orbit._run_full_refresh_coalesced", lambda: None)
    shell._watchdog_tick()
    assert (shell_env / ".doctor-pending").exists()

    # Tick 2: clean
    monkeypatch.setattr("views.doctor.doctor.check_all_projects", lambda: [])
    shell._watchdog_tick()
    assert not (shell_env / ".doctor-pending").exists()

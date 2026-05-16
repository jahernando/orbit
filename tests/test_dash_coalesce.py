"""Tests for _run_dash_coalesced: debounced dash refresh helper.

Coalescing via .dash-stamp: bursts of mutations (log, hl, task add, …)
collapse into one refresh per _DASH_COALESCE_SECONDS window.
"""

import time
from unittest.mock import patch

import pytest


@pytest.fixture
def stamp_env(tmp_path, monkeypatch):
    """Patch ORBIT_DIR (orbit module) so the stamp lives in tmp_path."""
    import orbit
    monkeypatch.setattr(orbit, "ORBIT_DIR", tmp_path)
    return tmp_path


def test_runs_when_stamp_missing(stamp_env):
    import orbit
    with patch.object(orbit, "run_dash") as h:
        orbit._run_dash_coalesced()
    h.assert_called_once_with(silent=True)


def test_skips_when_stamp_fresh(stamp_env):
    import orbit
    stamp = stamp_env / ".dash-stamp"
    stamp.touch()  # mtime = now
    with patch.object(orbit, "run_dash") as h:
        orbit._run_dash_coalesced()
    h.assert_not_called()


def test_runs_when_stamp_stale(stamp_env):
    import orbit
    stamp = stamp_env / ".dash-stamp"
    stamp.touch()
    # Force mtime to be older than the coalesce window.
    old = time.time() - (orbit._DASH_COALESCE_SECONDS + 5)
    import os
    os.utime(stamp, (old, old))
    with patch.object(orbit, "run_dash") as h:
        orbit._run_dash_coalesced()
    h.assert_called_once_with(silent=True)


def test_triggers_include_log_hl_project():
    """log, hl, project must be in _DASH_TRIGGERS since report-summary
    and projects.md depend on them."""
    import orbit
    assert "log" in orbit._DASH_TRIGGERS
    assert "hl" in orbit._DASH_TRIGGERS
    assert "project" in orbit._DASH_TRIGGERS


def test_cita_triggers_are_subset_of_dash_triggers():
    """Citas también refrescan dash; estructura: _CITA ⊂ _DASH."""
    import orbit
    assert orbit._CITA_TRIGGERS <= orbit._DASH_TRIGGERS
    # log/hl/project NOT in cita triggers (no afectan ics ni ring)
    for cmd in ("log", "hl", "project"):
        assert cmd not in orbit._CITA_TRIGGERS
    # citas SÍ en cita triggers
    for cmd in ("task", "ms", "ev", "reminder", "rem", "crono"):
        assert cmd in orbit._CITA_TRIGGERS


# ── _run_full_refresh_coalesced ─────────────────────────────────────────────

class TestRunFullRefreshCoalesced:
    def test_calls_all_three_steps(self, stamp_env, monkeypatch):
        """dash + ring + ics, en ese orden."""
        import orbit
        calls = []

        def fake_dash():
            calls.append("dash")

        def fake_ring(ctx):
            calls.append("ring")
            return {"ok": True}

        cloud = stamp_env / "cloud"
        cloud.mkdir()

        def fake_find_cloud_root():
            return cloud

        def fake_write_workspace(cr, project_filter=None):
            calls.append(("ics", str(cr), project_filter))
            return 0

        monkeypatch.setattr(orbit, "_run_dash_coalesced", fake_dash)
        monkeypatch.setattr("views.ring.export._action_ring_refresh", fake_ring)
        monkeypatch.setattr("core.deliver._find_cloud_root", fake_find_cloud_root)
        monkeypatch.setattr("views.cal.ics.write_workspace", fake_write_workspace)

        orbit._run_full_refresh_coalesced(project_hint="proj1")

        assert calls == [
            "dash",
            "ring",
            ("ics", str(cloud), "proj1"),
        ]

    def test_propagates_no_hint(self, stamp_env, monkeypatch):
        """Sin project_hint → write_workspace recibe project_filter=None."""
        import orbit
        received = {}

        monkeypatch.setattr(orbit, "_run_dash_coalesced", lambda: None)
        monkeypatch.setattr("views.ring.export._action_ring_refresh",
                            lambda ctx: {"ok": True})
        monkeypatch.setattr("core.deliver._find_cloud_root",
                            lambda: stamp_env)

        def fake_write(cr, project_filter=None):
            received["filter"] = project_filter

        monkeypatch.setattr("views.cal.ics.write_workspace", fake_write)
        orbit._run_full_refresh_coalesced()
        assert received["filter"] is None

    def test_skips_ics_when_no_cloud_root(self, stamp_env, monkeypatch):
        """Sin cloud_root configurado → ics no se llama, pero ring y dash sí."""
        import orbit
        called = {"ics": False}

        monkeypatch.setattr(orbit, "_run_dash_coalesced", lambda: None)
        monkeypatch.setattr("views.ring.export._action_ring_refresh",
                            lambda ctx: {"ok": True})
        monkeypatch.setattr("core.deliver._find_cloud_root", lambda: None)

        def fake_write(cr, project_filter=None):
            called["ics"] = True

        monkeypatch.setattr("views.cal.ics.write_workspace", fake_write)
        orbit._run_full_refresh_coalesced()
        assert called["ics"] is False

    def test_fail_isolation_dash_failure_does_not_block_ring_ics(
        self, stamp_env, monkeypatch
    ):
        """Una excepción en dash no impide que se ejecuten ring e ics."""
        import orbit
        calls = []

        def boom_dash():
            calls.append("dash-attempted")
            raise RuntimeError("dash exploded")

        monkeypatch.setattr(orbit, "_run_dash_coalesced", boom_dash)
        monkeypatch.setattr("views.ring.export._action_ring_refresh",
                            lambda ctx: calls.append("ring") or {"ok": True})
        monkeypatch.setattr("core.deliver._find_cloud_root", lambda: stamp_env)
        monkeypatch.setattr("views.cal.ics.write_workspace",
                            lambda cr, project_filter=None: calls.append("ics"))

        # Must not raise.
        orbit._run_full_refresh_coalesced()
        assert "dash-attempted" in calls
        assert "ring" in calls
        assert "ics" in calls

    def test_fail_isolation_ring_failure_does_not_block_ics(
        self, stamp_env, monkeypatch
    ):
        """Una excepción en ring no impide que se ejecute ics."""
        import orbit
        calls = []

        monkeypatch.setattr(orbit, "_run_dash_coalesced",
                            lambda: calls.append("dash"))

        def boom_ring(ctx):
            raise RuntimeError("ring exploded")

        monkeypatch.setattr("views.ring.export._action_ring_refresh", boom_ring)
        monkeypatch.setattr("core.deliver._find_cloud_root", lambda: stamp_env)
        monkeypatch.setattr("views.cal.ics.write_workspace",
                            lambda cr, project_filter=None: calls.append("ics"))

        orbit._run_full_refresh_coalesced()
        assert "dash" in calls
        assert "ics" in calls

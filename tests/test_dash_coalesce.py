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

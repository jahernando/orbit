"""Tests for F2: commit_pre / commit_post chain registration + action wrappers.

The wrappers in core/commit.py adapt orbit helpers (cloud_imgs, cronograma,
gsync, cloudsync) into the hook registry. These tests cover:
  - Both chains are registered with the expected actions in the right order.
  - Each action wrapper returns the documented ok/msg shape under both success
    and failure of its underlying helper.

v0.36: tracked_files_refresh action removed (propia/externa model, no refresh).
"""
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

# Importing core.commit registers the actions/chains at module load.
from core import commit, hooks


@pytest.fixture
def reset_journal(tmp_path, monkeypatch):
    """Redirect journal writes to a tmp location so tests don't pollute ORBIT_HOME."""
    monkeypatch.setattr(hooks, "JOURNAL_PATH", tmp_path / ".journal.jsonl")
    monkeypatch.setattr(hooks, "_load_orbit_json", lambda: {})


# ── Chain registration ───────────────────────────────────────────────────────

def test_commit_pre_chain_registered():
    chain = hooks.CHAINS.get("commit_pre")
    assert chain is not None
    assert chain.trigger_type == "explicit"
    assert chain.pre == [
        "cloud_imgs_process",
        "cronograma_log_completed",
        "gsync_reconcile_renames",
        "gsync_drift_check",
    ]
    assert chain.core is None
    assert chain.post == []


def test_commit_post_chain_registered():
    chain = hooks.CHAINS.get("commit_post")
    assert chain is not None
    assert chain.trigger_type == "explicit"
    assert chain.pre == []
    assert chain.post == ["cloudsync_push_background", "ring_refresh"]


def test_commit_pre_and_post_bound():
    assert hooks.BINDINGS["commit_pre"] == "commit_pre"
    assert hooks.BINDINGS["commit_post"] == "commit_post"


def test_all_commit_actions_are_non_critical():
    # v0.36: no critical actions in commit chains (tracked_files_refresh
    # was the only one and is now gone).
    for name in ("cloud_imgs_process", "cronograma_log_completed",
                 "gsync_reconcile_renames", "gsync_drift_check",
                 "cloudsync_push_background"):
        assert hooks.ACTIONS[name].critical is False, name


# ── cloud_imgs_process ───────────────────────────────────────────────────────

def test_cloud_imgs_process_no_pending():
    with patch("core.cloud_imgs.check_pending_imgs", return_value=0):
        result = commit._action_cloud_imgs_process(None)
    assert result == {"ok": True, "msg": "0 pending"}


def test_cloud_imgs_process_runs_when_pending():
    with patch("core.cloud_imgs.check_pending_imgs", return_value=3), \
         patch("core.cloud_imgs.run_cloud_imgs") as run_imgs, \
         patch("core.commit._git_add_all_tracked") as restage:
        result = commit._action_cloud_imgs_process(None)
    assert result == {"ok": True, "msg": "3 processed"}
    run_imgs.assert_called_once()
    restage.assert_called_once()


def test_cloud_imgs_process_swallows_exception():
    with patch("core.cloud_imgs.check_pending_imgs",
               side_effect=RuntimeError("boom")):
        result = commit._action_cloud_imgs_process(None)
    assert result["ok"] is False
    assert "RuntimeError" in result["msg"]


# ── cronograma_log_completed ─────────────────────────────────────────────────

def test_cronograma_log_zero():
    with patch("core.cronograma.log_crono_completions", return_value=0):
        result = commit._action_cronograma_log_completed(None)
    assert result == {"ok": True, "msg": "0 logged"}


def test_cronograma_log_some(capsys):
    with patch("core.cronograma.log_crono_completions", return_value=2), \
         patch("core.commit._git_add_all_tracked") as restage:
        result = commit._action_cronograma_log_completed(None)
    assert result == {"ok": True, "msg": "2 logged"}
    restage.assert_called_once()
    out = capsys.readouterr().out
    assert "2 tareas de cronograma" in out


# ── gsync_reconcile_renames ──────────────────────────────────────────────────

def test_gsync_reconcile_zero():
    with patch("core.gsync.reconcile_gsync_renames", return_value=[]):
        result = commit._action_gsync_reconcile_renames(None)
    assert result == {"ok": True, "msg": "0 renames"}


def test_gsync_reconcile_swallows_exception():
    with patch("core.gsync.reconcile_gsync_renames",
               side_effect=RuntimeError("boom")):
        result = commit._action_gsync_reconcile_renames(None)
    assert result == {"ok": True, "msg": "skipped"}


def test_gsync_reconcile_prints_renames(capsys):
    renames = [("proj", "old", "new")]
    with patch("core.gsync.reconcile_gsync_renames", return_value=renames):
        commit._action_gsync_reconcile_renames(None)
    out = capsys.readouterr().out
    assert "🔗" in out and "old" in out and "new" in out


# ── gsync_drift_check ────────────────────────────────────────────────────────

def test_gsync_drift_zero():
    with patch("core.gsync.check_gsync_drift", return_value=[]):
        result = commit._action_gsync_drift_check(None)
    assert result == {"ok": True, "msg": "0 drift items"}


def test_gsync_drift_swallows_exception():
    with patch("core.gsync.check_gsync_drift", side_effect=RuntimeError("boom")):
        result = commit._action_gsync_drift_check(None)
    assert result == {"ok": True, "msg": "skipped"}


def test_gsync_drift_prints_items(capsys):
    drift = [("proj", "task", "fooitem", ["was X", "now Y"])]
    with patch("core.gsync.check_gsync_drift", return_value=drift):
        commit._action_gsync_drift_check(None)
    out = capsys.readouterr().out
    assert "1 item modificado" in out
    assert "fooitem" in out
    assert "was X" in out


# ── cloudsync_push_background ────────────────────────────────────────────────

def test_cloudsync_push_launches(capsys):
    with patch("core.cloudsync.sync_to_cloud_background") as sync:
        result = commit._action_cloudsync_push_background(None)
    assert result == {"ok": True, "msg": "launched"}
    sync.assert_called_once()
    assert "Sincronización al cloud" in capsys.readouterr().out


def test_cloudsync_push_failure():
    with patch("core.cloudsync.sync_to_cloud_background",
               side_effect=RuntimeError("boom")):
        result = commit._action_cloudsync_push_background(None)
    assert result["ok"] is False
    assert "RuntimeError" in result["msg"]


# ── End-to-end: chain runs cleanly ────────────────────────────────────────────

def test_commit_pre_continues_when_clean(reset_journal):
    with patch("core.cloud_imgs.check_pending_imgs", return_value=0), \
         patch("core.cronograma.log_crono_completions", return_value=0), \
         patch("core.gsync.reconcile_gsync_renames", return_value=[]), \
         patch("core.gsync.check_gsync_drift", return_value=[]):
        results = hooks.fire("commit_pre", verbosity="quiet")

    actions_run = [r.action for r in results]
    assert actions_run == [
        "cloud_imgs_process",
        "cronograma_log_completed",
        "gsync_reconcile_renames",
        "gsync_drift_check",
    ]
    assert all(r.ok for r in results)

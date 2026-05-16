"""Tests for F2: commit_pre / commit_post chain registration + action wrappers.

The action wrappers viven across core/commit.py (cloud_imgs, cronograma)
y views/render/render.py (render_to_cloud). Estos tests cubren:
  - Ambos chains registrados con sus actions en el orden correcto.
  - Cada action wrapper devuelve el shape ok/msg documentado bajo éxito
    y fallo del helper subyacente.

v0.36: tracked_files_refresh action removed (propia/externa model, no refresh).
2026-05-16 fase B: cloudsync_push_background → render_to_cloud
(módulo trasladado a views/render/render.py).
"""
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

# Importing core.commit registers the actions/chains at module load.
from core import commit, hooks
from views.render import render


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
        "doctor_check_save",
    ]
    assert chain.core is None
    assert chain.post == []


def test_commit_post_chain_registered():
    chain = hooks.CHAINS.get("commit_post")
    assert chain is not None
    assert chain.trigger_type == "explicit"
    assert chain.pre == []
    assert chain.post == ["render_to_cloud", "ics_emit_workspace", "ring_refresh"]


def test_commit_pre_and_post_bound():
    assert hooks.BINDINGS["commit_pre"] == "commit_pre"
    assert hooks.BINDINGS["commit_post"] == "commit_post"


def test_commit_action_criticality():
    # doctor_check_save (post-A 2026-05-16) es la única action crítica
    # del commit_pre — si el usuario rechaza tras ver issues del doctor,
    # aborta la chain y por tanto el save. Las demás son non-critical.
    assert hooks.ACTIONS["doctor_check_save"].critical is True
    for name in ("cloud_imgs_process", "cronograma_log_completed",
                 "render_to_cloud", "ring_refresh"):
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


# ── render_to_cloud ────────────────────────────────────────────────

def test_render_to_cloud_launches(capsys):
    with patch("views.render.render.render_changed_to_cloud_background") as bg:
        result = render._action_render_to_cloud(None)
    assert result == {"ok": True, "msg": "launched"}
    bg.assert_called_once()
    assert "Render al cloud" in capsys.readouterr().out


def test_render_to_cloud_failure():
    with patch("views.render.render.render_changed_to_cloud_background",
               side_effect=RuntimeError("boom")):
        result = render._action_render_to_cloud(None)
    assert result["ok"] is False
    assert "RuntimeError" in result["msg"]


# ── End-to-end: chain runs cleanly ────────────────────────────────────────────

def test_commit_pre_continues_when_clean(reset_journal):
    with patch("core.cloud_imgs.check_pending_imgs", return_value=0), \
         patch("core.cronograma.log_crono_completions", return_value=0), \
         patch("views.doctor.doctor.check_all_projects", return_value=[]):
        results = hooks.fire("commit_pre", verbosity="quiet")

    actions_run = [r.action for r in results]
    assert actions_run == [
        "cloud_imgs_process",
        "cronograma_log_completed",
        "doctor_check_save",
    ]
    assert all(r.ok for r in results)

"""Tests for F5.1: render chain (post-render ics emit).

Covers:
  - Chain `render` registered with post=[ics_emit_workspace], bind after_render.
  - _action_ics_emit_workspace returns ok=True on success, swallows exceptions,
    handles missing cloud_root in ctx.
  - render_changed / render_all still call write_workspace via fire().
"""
from pathlib import Path
from unittest.mock import patch

import pytest

from core import hooks
from views.render import render


@pytest.fixture
def reset_journal(tmp_path, monkeypatch):
    monkeypatch.setattr(hooks, "JOURNAL_PATH", tmp_path / ".journal.jsonl")
    monkeypatch.setattr(hooks, "_load_orbit_json", lambda: {})


# ── Chain registration ───────────────────────────────────────────────────────

def test_render_chain_registered():
    chain = hooks.CHAINS.get("render")
    assert chain is not None
    assert chain.trigger_type == "explicit"
    assert chain.pre == []
    assert chain.core is None
    assert chain.post == ["ics_emit_workspace"]


def test_after_render_trigger_bound():
    assert hooks.BINDINGS["after_render"] == "render"


def test_ics_emit_workspace_action_registered():
    assert "ics_emit_workspace" in hooks.ACTIONS
    assert hooks.ACTIONS["ics_emit_workspace"].critical is False


# ── _action_ics_emit_workspace ───────────────────────────────────────────────

def test_ics_emit_workspace_success(tmp_path):
    with patch("views.cal.ics.write_workspace") as ws:
        result = render._action_ics_emit_workspace({"cloud_root": tmp_path})
    ws.assert_called_once_with(tmp_path)
    assert result == {"ok": True, "msg": "emitted"}


def test_ics_emit_workspace_no_cloud_root():
    result = render._action_ics_emit_workspace({})
    assert result["ok"] is True
    assert "no cloud_root" in result["msg"]


def test_ics_emit_workspace_none_ctx():
    result = render._action_ics_emit_workspace(None)
    assert result["ok"] is True


def test_ics_emit_workspace_swallows_exception(tmp_path, capsys):
    with patch("views.cal.ics.write_workspace", side_effect=RuntimeError("boom")):
        result = render._action_ics_emit_workspace({"cloud_root": tmp_path})
    assert result["ok"] is False
    assert "RuntimeError" in result["msg"]
    assert "error generando calendarios" in capsys.readouterr().out


# ── render_changed / render_all fire the chain ───────────────────────────────

def test_render_changed_skips_chain_when_no_files(tmp_path, reset_journal, monkeypatch):
    """Existing optimisation: render_changed early-exits when nothing changed,
    and that means the chain is NOT fired. Documenting via test."""
    monkeypatch.setattr(render, "_find_cloud_root", lambda: tmp_path)
    monkeypatch.setattr(render, "_sync_css", lambda *a, **k: None)
    monkeypatch.setattr(render, "_committed_md_files", lambda: [])
    with patch("views.cal.ics.write_workspace") as ws:
        render.render_changed()
    ws.assert_not_called()


def test_render_all_fires_after_render(tmp_path, reset_journal, monkeypatch):
    """render_all has no early-exit — fires after_render even when no projects exist."""
    monkeypatch.setattr(render, "_find_cloud_root", lambda: tmp_path)
    monkeypatch.setattr(render, "_sync_css", lambda *a, **k: None)
    monkeypatch.setattr(render, "iter_project_dirs", lambda: iter([]))

    with patch("views.cal.ics.write_workspace") as ws:
        render.render_all()
    ws.assert_called_once_with(tmp_path)


# ── End-to-end via fire() ────────────────────────────────────────────────────

def test_fire_after_render_invokes_write_workspace(tmp_path, reset_journal):
    with patch("views.cal.ics.write_workspace") as ws:
        results = hooks.fire("after_render", ctx={"cloud_root": tmp_path},
                              verbosity="quiet")
    assert len(results) == 1
    assert results[0].action == "ics_emit_workspace"
    assert results[0].ok is True
    ws.assert_called_once_with(tmp_path)


def test_fire_after_render_kill_switch(tmp_path, monkeypatch, reset_journal):
    """When config has hooks.actions.ics_emit_workspace=off, write_workspace not called."""
    monkeypatch.setattr(hooks, "_load_orbit_json",
                        lambda: {"hooks": {"actions": {"ics_emit_workspace": "off"}}})
    with patch("views.cal.ics.write_workspace") as ws:
        results = hooks.fire("after_render", ctx={"cloud_root": tmp_path},
                              verbosity="quiet")
    ws.assert_not_called()
    assert results[0].skipped
    assert results[0].skip_reason == "config=off"

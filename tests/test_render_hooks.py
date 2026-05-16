"""Tests for the ics_emit_workspace action.

Histórico: hasta 2026-05-16 esta acción vivía en un chain dedicado `render`
con binding `after_render`, fired desde render_changed/render_all. La fase C
del refactor de hooks la elevó a `commit_post` directo y eliminó el chain
`after_render`. Render ya no dispara nada — sólo emite HTML.
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


# ── Catalog registration ─────────────────────────────────────────────────────

def test_ics_emit_workspace_action_registered():
    assert "ics_emit_workspace" in hooks.ACTIONS
    assert hooks.ACTIONS["ics_emit_workspace"].critical is False


def test_ics_emit_workspace_in_commit_post():
    chain = hooks.CHAINS["commit_post"]
    assert "ics_emit_workspace" in chain.post


def test_after_render_chain_removed():
    """El chain `render` y el binding `after_render` desaparecieron en fase C."""
    assert "render" not in hooks.CHAINS
    assert "after_render" not in hooks.BINDINGS


# ── _action_ics_emit_workspace ───────────────────────────────────────────────

def test_ics_emit_workspace_success(tmp_path):
    with patch("views.cal.ics.write_workspace") as ws:
        result = render._action_ics_emit_workspace({"cloud_root": tmp_path})
    ws.assert_called_once_with(tmp_path)
    assert result == {"ok": True, "msg": "emitted"}


def test_ics_emit_workspace_resolves_cloud_root_when_missing(tmp_path, monkeypatch):
    """En commit_post el ctx no trae cloud_root: la action lo busca por sí misma."""
    monkeypatch.setattr(render, "_find_cloud_root", lambda: tmp_path)
    with patch("views.cal.ics.write_workspace") as ws:
        result = render._action_ics_emit_workspace(None)
    ws.assert_called_once_with(tmp_path)
    assert result["ok"] is True


def test_ics_emit_workspace_no_cloud_root_anywhere(monkeypatch):
    monkeypatch.setattr(render, "_find_cloud_root", lambda: None)
    result = render._action_ics_emit_workspace(None)
    assert result["ok"] is True
    assert "no cloud_root" in result["msg"]


def test_ics_emit_workspace_swallows_exception(tmp_path, capsys):
    with patch("views.cal.ics.write_workspace", side_effect=RuntimeError("boom")):
        result = render._action_ics_emit_workspace({"cloud_root": tmp_path})
    assert result["ok"] is False
    assert "RuntimeError" in result["msg"]
    assert "error generando calendarios" in capsys.readouterr().out


# ── Render no longer triggers ICS ────────────────────────────────────────────

def test_render_changed_does_not_emit_ics(tmp_path, monkeypatch):
    """Tras fase C, render_changed sólo emite HTML."""
    monkeypatch.setattr(render, "_find_cloud_root", lambda: tmp_path)
    monkeypatch.setattr(render, "_sync_css", lambda *a, **k: None)
    monkeypatch.setattr(render, "_committed_md_files", lambda: [])
    with patch("views.cal.ics.write_workspace") as ws:
        render.render_changed()
    ws.assert_not_called()


def test_render_all_does_not_emit_ics(tmp_path, monkeypatch):
    """Tras fase C, render_all sólo emite HTML."""
    monkeypatch.setattr(render, "_find_cloud_root", lambda: tmp_path)
    monkeypatch.setattr(render, "_sync_css", lambda *a, **k: None)
    monkeypatch.setattr(render, "iter_project_dirs", lambda: iter([]))
    with patch("views.cal.ics.write_workspace") as ws:
        render.render_all()
    ws.assert_not_called()


# ── End-to-end via fire("commit_post") ───────────────────────────────────────

def test_commit_post_emits_ics(tmp_path, monkeypatch, reset_journal):
    """fire("commit_post") ejecuta ics_emit_workspace y emite los .ics."""
    monkeypatch.setattr(render, "_find_cloud_root", lambda: tmp_path)
    with patch("views.render.render.render_changed_to_cloud_background"), \
         patch("views.ring.export.refresh_all", return_value=[]), \
         patch("views.ring.export.invoke_daemon", return_value=(True, "noop")), \
         patch("views.cal.ics.write_workspace") as ws:
        results = hooks.fire("commit_post", verbosity="quiet")
    ws.assert_called_once_with(tmp_path)
    ics_result = next(r for r in results if r.action == "ics_emit_workspace")
    assert ics_result.ok is True


def test_commit_post_ics_kill_switch(tmp_path, monkeypatch, reset_journal):
    """Config hooks.actions.ics_emit_workspace=off → no se emiten .ics tras save."""
    monkeypatch.setattr(hooks, "_load_orbit_json",
                        lambda: {"hooks": {"actions": {"ics_emit_workspace": "off"}}})
    monkeypatch.setattr(render, "_find_cloud_root", lambda: tmp_path)
    with patch("views.render.render.render_changed_to_cloud_background"), \
         patch("views.ring.export.refresh_all", return_value=[]), \
         patch("views.ring.export.invoke_daemon", return_value=(True, "noop")), \
         patch("views.cal.ics.write_workspace") as ws:
        results = hooks.fire("commit_post", verbosity="quiet")
    ws.assert_not_called()
    ics_result = next(r for r in results if r.action == "ics_emit_workspace")
    assert ics_result.skipped
    assert ics_result.skip_reason == "config=off"

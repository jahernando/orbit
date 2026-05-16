"""Tests for bootstrap_workspace_md (D1.d, 2026-05-16).

Crea workspace.md en raíz del workspace con descripción + links al
dashboard de secretary. Lee emoji/space de orbit.json. No sobreescribe.
"""

import json

import pytest

from core import setup


@pytest.fixture
def fake_ws(tmp_path, monkeypatch):
    monkeypatch.setattr(setup, "ORBIT_HOME", tmp_path)
    monkeypatch.setattr(setup, "_ORBIT_JSON", tmp_path / "orbit.json")
    return tmp_path


def test_bootstrap_creates_when_missing(fake_ws):
    (fake_ws / "orbit.json").write_text(json.dumps({
        "emoji": "🚀", "space": "test-ws"
    }))
    assert setup.bootstrap_workspace_md() is True

    ws_md = fake_ws / "workspace.md"
    assert ws_md.exists()
    content = ws_md.read_text()
    assert "🚀 test-ws" in content
    assert "📋secretary/panel.md" in content
    assert "📋secretary/agenda-next.md" in content
    assert "📋secretary/calendar.md" in content
    assert "📋secretary/projects.md" in content


def test_bootstrap_falls_back_to_dir_name_when_no_config(fake_ws):
    # No orbit.json: usa defaults (emoji 🚀, space = dir name)
    assert setup.bootstrap_workspace_md() is True
    content = (fake_ws / "workspace.md").read_text()
    assert fake_ws.name in content
    assert "🚀" in content


def test_bootstrap_does_not_overwrite_existing(fake_ws):
    (fake_ws / "orbit.json").write_text(json.dumps({"emoji": "🌿", "space": "ws"}))
    user_content = "# Mi workspace\n\nLo escribí yo a mano.\n"
    (fake_ws / "workspace.md").write_text(user_content)

    assert setup.bootstrap_workspace_md() is False
    assert (fake_ws / "workspace.md").read_text() == user_content

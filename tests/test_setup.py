"""Tests for core/setup.py — interactive setup wizard."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    """Redirect all setup paths to tmp_path."""
    monkeypatch.setattr("core.setup.ORBIT_HOME", tmp_path)
    monkeypatch.setattr("core.setup._ORBIT_JSON", tmp_path / "orbit.json")
    monkeypatch.setattr("core.setup._FEDERATION_JSON", tmp_path / "federation.json")
    return tmp_path


def _read_json(path):
    return json.loads(path.read_text())


# ── Config loading ────────────────────────────────────────────────────────

class TestLoadExisting:

    def test_no_file(self, _isolate):
        from core.setup import _load_existing
        assert _load_existing() == {}

    def test_valid_file(self, _isolate):
        (_isolate / "orbit.json").write_text(json.dumps({"emoji": "🌿", "space": "ps"}))
        from core.setup import _load_existing
        cfg = _load_existing()
        assert cfg["emoji"] == "🌿"

    def test_corrupt_file(self, _isolate):
        (_isolate / "orbit.json").write_text("not json{")
        from core.setup import _load_existing
        assert _load_existing() == {}


class TestLoadFederation:

    def test_no_file(self, _isolate):
        from core.setup import _load_federation
        assert _load_federation() == []

    def test_valid_file(self, _isolate):
        (_isolate / "federation.json").write_text(json.dumps({
            "federated": [{"name": "ps", "path": "/tmp/ps", "emoji": "🌿"}]
        }))
        from core.setup import _load_federation
        assert len(_load_federation()) == 1


# ── Individual sections ───────────────────────────────────────────────────

class TestSetupWorkspace:

    @patch("builtins.input", side_effect=["🌿", "orbit-ps"])
    def test_custom_values(self, mock_input):
        from core.setup import _setup_workspace
        result = _setup_workspace({})
        assert result["emoji"] == "🌿"
        assert result["space"] == "orbit-ps"

    @patch("builtins.input", side_effect=["", ""])
    def test_defaults(self, mock_input):
        from core.setup import _setup_workspace
        result = _setup_workspace({"emoji": "🚀", "space": "ws"})
        assert result["emoji"] == "🚀"
        assert result["space"] == "ws"


class TestSetupTypes:

    @patch("builtins.input", side_effect=[""])
    def test_keep_defaults(self, mock_input):
        from core.setup import _setup_types
        result = _setup_types({})
        assert "investigacion" in result["types"]

    @patch("builtins.input", side_effect=["hobby 🎮", ""])
    def test_add_type(self, mock_input):
        from core.setup import _setup_types
        result = _setup_types({})
        assert result["types"]["hobby"] == "🎮"
        assert "investigacion" in result["types"]

    @patch("builtins.input", side_effect=["badformat", ""])
    def test_bad_format(self, mock_input, capsys):
        from core.setup import _setup_types
        result = _setup_types({})
        assert "Formato" in capsys.readouterr().out


class TestSetupEditor:

    @patch("builtins.input", side_effect=["code"])
    def test_set_editor(self, mock_input):
        from core.setup import _setup_editor
        result = _setup_editor({})
        assert result["editor"] == "code"

    @patch("builtins.input", side_effect=[""])
    def test_skip(self, mock_input):
        from core.setup import _setup_editor
        result = _setup_editor({})
        assert result == {}

    @patch("builtins.input", side_effect=[""])
    def test_keep_existing(self, mock_input):
        from core.setup import _setup_editor
        result = _setup_editor({"editor": "obsidian"})
        assert result["editor"] == "obsidian"


class TestSetupGsync:

    @patch("builtins.input", side_effect=["n"])
    def test_skip(self, mock_input):
        from core.setup import _setup_gsync
        assert _setup_gsync({}) == {}

    @patch("builtins.input", side_effect=["s"])
    def test_no_creds(self, mock_input, _isolate, capsys):
        from core.setup import _setup_gsync
        _setup_gsync({})
        assert "credentials.json" in capsys.readouterr().out

    @patch("builtins.input", side_effect=["s"])
    def test_creds_found(self, mock_input, _isolate, capsys):
        (_isolate / "credentials.json").write_text("{}")
        from core.setup import _setup_gsync
        _setup_gsync({})
        assert "encontrado" in capsys.readouterr().out


class TestSetupCarteroGmail:

    @patch("builtins.input", side_effect=["n"])
    def test_skip(self, mock_input):
        from core.setup import _setup_cartero_gmail
        assert _setup_cartero_gmail({}) == {}

    @patch("builtins.input", side_effect=["s", "Importante, Familia", "10"])
    def test_configure(self, mock_input):
        from core.setup import _setup_cartero_gmail
        result = _setup_cartero_gmail({})
        gmail = result["cartero_gmail"]
        assert gmail["labels"] == ["Importante", "Familia"]
        assert gmail["interval"] == 600

    @patch("builtins.input", side_effect=["s", "Inbox", "5"])
    def test_custom_interval(self, mock_input):
        from core.setup import _setup_cartero_gmail
        result = _setup_cartero_gmail({})
        assert result["cartero_gmail"]["interval"] == 300

    @patch("builtins.input", side_effect=["s", "", ""])
    def test_existing_defaults(self, mock_input):
        from core.setup import _setup_cartero_gmail
        cfg = {"cartero": {"gmail": {"labels": ["A", "B"], "interval": 300}}}
        result = _setup_cartero_gmail(cfg)
        assert result["cartero_gmail"]["labels"] == ["A", "B"]
        assert result["cartero_gmail"]["interval"] == 300


class TestSetupCarteroSlack:

    @patch("builtins.input", side_effect=["n"])
    def test_skip(self, mock_input):
        from core.setup import _setup_cartero_slack
        assert _setup_cartero_slack({}) == {}

    @patch("builtins.input", side_effect=["s", "myws", "general, alertas", "s", "n"])
    def test_one_workspace(self, mock_input):
        from core.setup import _setup_cartero_slack
        result = _setup_cartero_slack({})
        ws = result["cartero_slack"]
        assert len(ws) == 1
        assert ws[0]["workspace"] == "myws"
        assert ws[0]["channels"] == ["general", "alertas"]
        assert ws[0]["dms"] is True

    @patch("builtins.input", side_effect=["s", "ws1", "ch1", "n", "s", "ws2", "ch2", "n", "n"])
    def test_two_workspaces(self, mock_input):
        from core.setup import _setup_cartero_slack
        result = _setup_cartero_slack({})
        assert len(result["cartero_slack"]) == 2

    @patch("builtins.input", side_effect=["s", ""])
    def test_no_workspaces_entered(self, mock_input):
        from core.setup import _setup_cartero_slack
        assert _setup_cartero_slack({}) == {}


class TestSetupFederation:

    @patch("builtins.input", side_effect=["n"])
    def test_skip(self, mock_input):
        from core.setup import _setup_federation
        result = _setup_federation([])
        assert result == []

    @patch("builtins.input", side_effect=["s", "/tmp/test-ws", "🌿", "personal", "n"])
    def test_add_workspace(self, mock_input, _isolate):
        # Create the target so it "exists"
        Path("/tmp/test-ws").mkdir(exist_ok=True)
        from core.setup import _setup_federation
        result = _setup_federation([])
        assert len(result) == 1
        assert result[0]["emoji"] == "🌿"
        assert result[0]["name"] == "personal"

    @patch("builtins.input", side_effect=["n"])
    def test_keep_existing(self, mock_input):
        from core.setup import _setup_federation
        existing = [{"name": "ps", "path": "/tmp/ps", "emoji": "🌿"}]
        result = _setup_federation(existing)
        assert result == existing


# ── Full run_setup ────────────────────────────────────────────────────────

class TestRunSetup:

    @patch("builtins.input", side_effect=[
        "🚀", "test-ws",       # workspace
        "",                     # types (keep defaults)
        "obsidian",             # editor
        "n",                    # gsync
        "n",                    # gmail
        "n",                    # slack
        "n",                    # federation
    ])
    def test_minimal_setup(self, mock_input, _isolate, capsys):
        from core.setup import run_setup
        ret = run_setup()
        assert ret == 0
        out = capsys.readouterr().out
        assert "Configuración guardada" in out

        cfg = _read_json(_isolate / "orbit.json")
        assert cfg["emoji"] == "🚀"
        assert cfg["space"] == "test-ws"
        assert cfg["editor"] == "obsidian"
        assert "investigacion" in cfg["types"]

    @patch("builtins.input", side_effect=[
        "🌿", "orbit-ps",      # workspace
        "",                     # types
        "",                     # editor (skip)
        "n",                    # gsync
        "s", "Importante, Familia", "10",   # gmail
        "n",                    # slack
        "n",                    # federation
    ])
    def test_with_gmail(self, mock_input, _isolate):
        from core.setup import run_setup
        ret = run_setup()
        assert ret == 0

        cfg = _read_json(_isolate / "orbit.json")
        assert cfg["cartero"]["gmail"]["labels"] == ["Importante", "Familia"]
        assert cfg["cartero"]["gmail"]["interval"] == 600

    @patch("builtins.input", side_effect=[
        "🚀", "ws",            # workspace
        "",                     # types
        "",                     # editor
        "n",                    # gsync
        "n",                    # gmail
        "s", "myws", "general", "n", "n",   # slack
        "s", "/tmp/test-fed", "🌿", "ps", "n",   # federation
    ])
    def test_with_slack_and_federation(self, mock_input, _isolate):
        Path("/tmp/test-fed").mkdir(exist_ok=True)
        from core.setup import run_setup
        ret = run_setup()
        assert ret == 0

        cfg = _read_json(_isolate / "orbit.json")
        assert cfg["cartero"]["slack"][0]["workspace"] == "myws"

        fed = _read_json(_isolate / "federation.json")
        assert len(fed["federated"]) == 1
        assert fed["federated"][0]["emoji"] == "🌿"

    @patch("builtins.input", side_effect=EOFError)
    def test_cancel(self, mock_input, _isolate, capsys):
        from core.setup import run_setup
        ret = run_setup()
        assert ret == 1
        assert "Cancelado" in capsys.readouterr().out

    @patch("builtins.input", side_effect=KeyboardInterrupt)
    def test_ctrl_c(self, mock_input, _isolate, capsys):
        from core.setup import run_setup
        ret = run_setup()
        assert ret == 1

    @patch("builtins.input", side_effect=[
        "", "",                 # workspace (keep existing)
        "",                     # types
        "",                     # editor
        "n",                    # gsync
        "n",                    # gmail
        "n",                    # slack
        "n",                    # federation
    ])
    def test_preserves_existing(self, mock_input, _isolate):
        """Setup preserves fields from existing orbit.json that aren't touched."""
        (_isolate / "orbit.json").write_text(json.dumps({
            "emoji": "🌿", "space": "ps", "custom_field": "keep_me"
        }))
        from core.setup import run_setup
        ret = run_setup()
        assert ret == 0

        cfg = _read_json(_isolate / "orbit.json")
        assert cfg["emoji"] == "🌿"
        assert cfg["custom_field"] == "keep_me"

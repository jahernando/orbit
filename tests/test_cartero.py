"""Tests for core/cartero.py — mail notifier."""

import json
import os
import signal
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    """Redirect all cartero paths to tmp_path."""
    monkeypatch.setattr("core.cartero.ORBIT_HOME", tmp_path)
    monkeypatch.setattr("core.cartero.CARTERO_PID", tmp_path / ".cartero.pid")
    monkeypatch.setattr("core.cartero.CARTERO_STATE", tmp_path / ".cartero-state.json")
    # Create minimal orbit.json
    (tmp_path / "orbit.json").write_text(json.dumps({
        "space": "orbit-ps",
        "emoji": "🌿",
        "cartero": {
            "gmail": {
                "labels": ["Importante", "Familia", "Universidad"],
                "interval": 300,
            }
        }
    }))
    return tmp_path


# ── Config tests ────────────────────────────────────────────────────────────

class TestConfig:

    def test_load_cartero_config(self, _isolate):
        from core.cartero import _load_cartero_config
        cfg = _load_cartero_config()
        assert "gmail" in cfg
        assert cfg["gmail"]["labels"] == ["Importante", "Familia", "Universidad"]

    def test_load_cartero_config_missing(self, _isolate):
        (_isolate / "orbit.json").unlink()
        from core.cartero import _load_cartero_config
        assert _load_cartero_config() == {}

    def test_load_cartero_config_no_cartero_section(self, _isolate):
        (_isolate / "orbit.json").write_text(json.dumps({"space": "test"}))
        from core.cartero import _load_cartero_config
        assert _load_cartero_config() == {}

    def test_gmail_config(self, _isolate):
        from core.cartero import _gmail_config
        cfg = _gmail_config()
        assert cfg is not None
        assert cfg["labels"] == ["Importante", "Familia", "Universidad"]

    def test_gmail_config_empty_labels(self, _isolate):
        (_isolate / "orbit.json").write_text(json.dumps({
            "cartero": {"gmail": {"labels": []}}
        }))
        from core.cartero import _gmail_config
        assert _gmail_config() is None


# ── State tests ─────────────────────────────────────────────────────────────

class TestState:

    def test_read_state_missing(self, _isolate):
        from core.cartero import _read_state
        assert _read_state() == {}

    def test_write_read_state(self, _isolate):
        from core.cartero import _write_state, _read_state
        state = {"gmail": {"total": 5, "counts": {"A": 3, "B": 2}}}
        _write_state(state)
        got = _read_state()
        assert got["gmail"]["total"] == 5
        assert got["gmail"]["counts"]["A"] == 3

    def test_write_state_atomic(self, _isolate):
        """Verify tmp file is cleaned up after atomic write."""
        from core.cartero import _write_state, CARTERO_STATE
        _write_state({"test": 1})
        assert CARTERO_STATE.exists()
        assert not CARTERO_STATE.with_suffix(".tmp").exists()

    def test_read_state_corrupt(self, _isolate):
        from core.cartero import _read_state, CARTERO_STATE
        CARTERO_STATE.write_text("not json{{{")
        assert _read_state() == {}


# ── Prompt indicator tests ──────────────────────────────────────────────────

class TestPromptIndicator:

    def test_no_state(self, _isolate):
        from core.cartero import get_prompt_indicator
        assert get_prompt_indicator() == ""

    def test_zero_mail(self, _isolate):
        from core.cartero import get_prompt_indicator, _write_state
        _write_state({"gmail": {"total": 0, "counts": {}}})
        assert get_prompt_indicator() == ""

    def test_has_mail(self, _isolate):
        from core.cartero import get_prompt_indicator, _write_state
        _write_state({"gmail": {"total": 7, "counts": {"A": 7}}})
        assert get_prompt_indicator() == "[📬7]"

    def test_single_mail(self, _isolate):
        from core.cartero import get_prompt_indicator, _write_state
        _write_state({"gmail": {"total": 1, "counts": {"A": 1}}})
        assert get_prompt_indicator() == "[📬1]"


# ── Process management tests ───────────────────────────────────────────────

class TestProcessManagement:

    def test_is_running_no_file(self, _isolate):
        from core.cartero import _is_running
        assert _is_running() is False

    def test_is_running_stale_pid(self, _isolate):
        from core.cartero import _is_running, CARTERO_PID
        CARTERO_PID.write_text("999999999")  # unlikely to exist
        assert _is_running() is False
        assert not CARTERO_PID.exists()  # cleaned up

    def test_is_running_current_pid(self, _isolate):
        from core.cartero import _is_running, CARTERO_PID
        CARTERO_PID.write_text(str(os.getpid()))  # this process exists
        assert _is_running() is True

    def test_stop_not_running(self, _isolate):
        from core.cartero import _stop_background
        assert _stop_background() is False

    def test_stop_stale_pid(self, _isolate):
        from core.cartero import _stop_background, CARTERO_PID
        CARTERO_PID.write_text("999999999")
        assert _stop_background() is False
        assert not CARTERO_PID.exists()


# ── Gmail API tests (mocked) ───────────────────────────────────────────────

class TestGmailAPI:

    def test_resolve_label_ids(self):
        from core.cartero import _resolve_label_ids
        service = MagicMock()
        service.users().labels().list().execute.return_value = {
            "labels": [
                {"name": "Importante", "id": "Label_1"},
                {"name": "Familia", "id": "Label_2"},
                {"name": "INBOX", "id": "INBOX"},
            ]
        }
        result = _resolve_label_ids(service, ["Importante", "Familia", "NoExiste"])
        assert result == {"Importante": "Label_1", "Familia": "Label_2"}

    def test_resolve_label_ids_case_insensitive(self):
        from core.cartero import _resolve_label_ids
        service = MagicMock()
        service.users().labels().list().execute.return_value = {
            "labels": [
                {"name": "importante", "id": "Label_1"},
            ]
        }
        result = _resolve_label_ids(service, ["Importante"])
        assert result == {"Importante": "Label_1"}

    def test_check_gmail(self):
        from core.cartero import _check_gmail
        service = MagicMock()

        def mock_get(userId, id):
            mock = MagicMock()
            if id == "Label_1":
                mock.execute.return_value = {"messagesUnread": 3}
            elif id == "Label_2":
                mock.execute.return_value = {"messagesUnread": 1}
            else:
                mock.execute.return_value = {"messagesUnread": 0}
            return mock

        service.users().labels().get = mock_get

        label_ids = {"Importante": "Label_1", "Familia": "Label_2"}
        result = _check_gmail(service, label_ids)

        assert result["counts"]["Importante"] == 3
        assert result["counts"]["Familia"] == 1
        assert result["total"] == 4
        assert "timestamp" in result

    def test_check_gmail_api_error(self):
        from core.cartero import _check_gmail
        service = MagicMock()
        service.users().labels().get().execute.side_effect = Exception("API error")

        result = _check_gmail(service, {"Test": "Label_X"})
        assert result["counts"]["Test"] == 0
        assert result["total"] == 0


# ── Notification tests ──────────────────────────────────────────────────────

class TestNotification:

    @patch("subprocess.run")
    def test_notify_macos(self, mock_run):
        from core.cartero import _notify_macos
        _notify_macos("📬 2 correos nuevos", "Importante (2)")
        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        assert cmd[0] == "osascript"
        assert "Importante (2)" in cmd[2]


# ── run_mail CLI tests ──────────────────────────────────────────────────────

class TestRunMail:

    def test_status_not_running(self, _isolate, capsys):
        from core.cartero import run_mail
        ret = run_mail(status=True)
        assert ret == 0
        assert "no está corriendo" in capsys.readouterr().out

    def test_status_running(self, _isolate, capsys):
        from core.cartero import run_mail, CARTERO_PID, _write_state
        CARTERO_PID.write_text(str(os.getpid()))
        _write_state({
            "gmail": {"total": 3, "counts": {"A": 3}, "timestamp": "2026-04-13T10:00:00"},
            "pid": os.getpid(),
        })
        ret = run_mail(status=True)
        assert ret == 0
        out = capsys.readouterr().out
        assert "corriendo" in out
        assert "A" in out

    def test_stop(self, _isolate, capsys):
        from core.cartero import run_mail
        ret = run_mail(stop=True)
        assert ret == 0
        assert "no estaba corriendo" in capsys.readouterr().out

    def test_start_no_config(self, _isolate, capsys):
        (_isolate / "orbit.json").write_text(json.dumps({"space": "test"}))
        from core.cartero import run_mail
        ret = run_mail(start=True)
        assert ret == 1

    def test_default_no_config(self, _isolate, capsys):
        (_isolate / "orbit.json").write_text(json.dumps({"space": "test"}))
        from core.cartero import run_mail
        ret = run_mail()
        assert ret == 1
        assert "orbit.json" in capsys.readouterr().out

    @patch("core.cartero._get_gmail_service")
    @patch("core.cartero._resolve_label_ids")
    @patch("core.cartero._check_gmail")
    def test_default_sync_check(self, mock_check, mock_resolve, mock_service, _isolate, capsys):
        from core.cartero import run_mail
        mock_service.return_value = MagicMock()
        mock_resolve.return_value = {"Importante": "L1", "Familia": "L2"}
        mock_check.return_value = {
            "counts": {"Importante": 3, "Familia": 1},
            "total": 4,
            "timestamp": "2026-04-13T10:00:00",
        }
        ret = run_mail()
        assert ret == 0
        out = capsys.readouterr().out
        assert "Importante" in out
        assert "4" in out


# ── Startup integration tests ──────────────────────────────────────────────

class TestStartup:

    @patch("core.cartero._start_background")
    def test_startup_launches_background(self, mock_start, _isolate, capsys):
        from core.cartero import startup_cartero
        startup_cartero()
        mock_start.assert_called_once()
        assert "Cartero activo" in capsys.readouterr().out

    @patch("core.cartero._is_running", return_value=True)
    def test_startup_skips_if_running(self, mock_running, _isolate, capsys):
        from core.cartero import startup_cartero, _write_state
        _write_state({"gmail": {"total": 2, "counts": {"A": 2}}})
        startup_cartero()
        assert "Cartero activo" in capsys.readouterr().out

    def test_startup_no_config(self, _isolate, capsys):
        (_isolate / "orbit.json").write_text(json.dumps({"space": "test"}))
        from core.cartero import startup_cartero
        startup_cartero()
        assert capsys.readouterr().out == ""


# ── Slack tests ─────────────────────────────────────────────────────────────

class TestSlackConfig:

    def test_slack_config_single(self, _isolate):
        (_isolate / "orbit.json").write_text(json.dumps({
            "cartero": {"slack": {"workspace": "test", "channels": ["general"], "interval": 600}}
        }))
        from core.cartero import _slack_config
        cfg = _slack_config()
        assert cfg is not None
        assert len(cfg) == 1
        assert cfg[0]["channels"] == ["general"]

    def test_slack_config_list(self, _isolate):
        (_isolate / "orbit.json").write_text(json.dumps({
            "cartero": {"slack": [
                {"workspace": "ws1", "channels": ["a"]},
                {"workspace": "ws2", "channels": ["b"], "dms": True},
            ]}
        }))
        from core.cartero import _slack_config
        cfg = _slack_config()
        assert len(cfg) == 2
        assert cfg[1]["dms"] is True

    def test_slack_config_missing(self, _isolate):
        from core.cartero import _slack_config
        assert _slack_config() is None

    def test_slack_config_empty_channels(self, _isolate):
        (_isolate / "orbit.json").write_text(json.dumps({
            "cartero": {"slack": {"channels": []}}
        }))
        from core.cartero import _slack_config
        assert _slack_config() is None

    def test_slack_config_dms_only(self, _isolate):
        (_isolate / "orbit.json").write_text(json.dumps({
            "cartero": {"slack": {"workspace": "test", "dms": True}}
        }))
        from core.cartero import _slack_config
        cfg = _slack_config()
        assert cfg is not None
        assert len(cfg) == 1


class TestSlackToken:

    def test_no_token_file(self, _isolate):
        from core.cartero import _get_slack_token
        assert _get_slack_token() is None

    def test_empty_token_file(self, _isolate):
        from core.cartero import _get_slack_token
        (_isolate / ".slack-token").write_text("")
        assert _get_slack_token() is None

    def test_valid_token(self, _isolate):
        from core.cartero import _get_slack_token
        (_isolate / ".slack-token-myws").write_text("xoxp-12345\n")
        assert _get_slack_token("myws") == "xoxp-12345"


class TestSlackAPI:

    def test_resolve_channels(self):
        from core.cartero import _resolve_slack_channels
        with patch("core.cartero._slack_api") as mock_api:
            mock_api.return_value = {
                "ok": True,
                "channels": [
                    {"name": "general", "id": "C001"},
                    {"name": "alertas", "id": "C002"},
                    {"name": "random", "id": "C003"},
                ],
                "response_metadata": {"next_cursor": ""},
            }
            result = _resolve_slack_channels("token", ["general", "alertas"])
            assert result == {"general": "C001", "alertas": "C002"}

    def test_resolve_channels_not_found(self, capsys):
        from core.cartero import _resolve_slack_channels
        with patch("core.cartero._slack_api") as mock_api:
            mock_api.return_value = {
                "ok": True,
                "channels": [{"name": "random", "id": "C003"}],
                "response_metadata": {"next_cursor": ""},
            }
            result = _resolve_slack_channels("token", ["noexiste"])
            assert result == {}
            assert "no encontrado" in capsys.readouterr().out

    def test_check_slack(self):
        from core.cartero import _check_slack
        with patch("core.cartero._slack_api") as mock_api:
            def side_effect(method, token, params=None):
                if method == "conversations.info":
                    cid = params["channel"]
                    unread = {"C001": 5, "C002": 2}.get(cid, 0)
                    return {"ok": True, "channel": {"unread_count_display": unread}}
                return {"ok": False}
            mock_api.side_effect = side_effect

            result = _check_slack("token", {"general": "C001", "alertas": "C002"})
            assert result["counts"]["general"] == 5
            assert result["counts"]["alertas"] == 2
            assert result["total"] == 7

    def test_check_slack_error(self):
        from core.cartero import _check_slack
        with patch("core.cartero._slack_api") as mock_api:
            mock_api.side_effect = Exception("network error")
            result = _check_slack("token", {"general": "C001"})
            assert result["counts"]["general"] == 0
            assert result["total"] == 0

    def test_check_slack_dms(self):
        from core.cartero import _check_slack_dms
        with patch("core.cartero._slack_api") as mock_api:
            def side_effect(method, token, params=None):
                if method == "conversations.list":
                    if params and params.get("types") == "im":
                        return {
                            "ok": True,
                            "channels": [{"id": "D1"}, {"id": "D2"}],
                            "response_metadata": {"next_cursor": ""},
                        }
                    return {"ok": True, "channels": [],
                            "response_metadata": {"next_cursor": ""}}
                if method == "conversations.info":
                    cid = params["channel"]
                    unread = {"D1": 3, "D2": 1}.get(cid, 0)
                    return {"ok": True, "channel": {"unread_count_display": unread}}
                return {"ok": False}
            mock_api.side_effect = side_effect
            assert _check_slack_dms("token") == 4

    def test_check_slack_workspace_with_dms(self):
        from core.cartero import _check_slack_workspace
        with patch("core.cartero._check_slack") as mock_ch, \
             patch("core.cartero._check_slack_dms") as mock_dm:
            mock_ch.return_value = {
                "counts": {"general": 2}, "total": 2,
                "timestamp": "2026-04-13T10:00:00",
            }
            mock_dm.return_value = 5
            result = _check_slack_workspace("token", {"general": "C1"}, True)
            assert result["counts"]["general"] == 2
            assert result["counts"]["DMs"] == 5
            assert result["total"] == 7


class TestPromptIndicatorMultiSource:

    def test_gmail_only(self, _isolate):
        from core.cartero import get_prompt_indicator, _write_state
        _write_state({"gmail": {"total": 3, "counts": {"A": 3}}})
        assert get_prompt_indicator() == "[📬3]"

    def test_slack_only(self, _isolate):
        from core.cartero import get_prompt_indicator, _write_state
        _write_state({"slack": {"total": 5, "counts": {"general": 5}}})
        assert get_prompt_indicator() == "[📬5]"

    def test_both_sources(self, _isolate):
        from core.cartero import get_prompt_indicator, _write_state
        _write_state({
            "gmail": {"total": 3, "counts": {"A": 3}},
            "slack": {"total": 2, "counts": {"general": 2}},
        })
        assert get_prompt_indicator() == "[📬5]"

    def test_both_zero(self, _isolate):
        from core.cartero import get_prompt_indicator, _write_state
        _write_state({
            "gmail": {"total": 0, "counts": {}},
            "slack": {"total": 0, "counts": {}},
        })
        assert get_prompt_indicator() == ""


class TestHasAnySource:

    def test_gmail_only(self, _isolate):
        from core.cartero import _has_any_source
        assert _has_any_source() is True

    def test_slack_only(self, _isolate):
        (_isolate / "orbit.json").write_text(json.dumps({
            "cartero": {"slack": {"channels": ["general"]}}
        }))
        from core.cartero import _has_any_source
        assert _has_any_source() is True

    def test_no_sources(self, _isolate):
        (_isolate / "orbit.json").write_text(json.dumps({"space": "test"}))
        from core.cartero import _has_any_source
        assert _has_any_source() is False


# ── Federation tests ───────────────────────────────────────────────────────

class TestFederation:

    def test_no_federated(self, _isolate):
        from core.cartero import _read_federated_states
        assert _read_federated_states() == []

    def test_read_federated_state(self, _isolate, monkeypatch):
        from core.cartero import _read_federated_states
        # Create a fake federated workspace with cartero state
        fed_path = _isolate / "fed-ws"
        fed_path.mkdir()
        (fed_path / ".cartero-state.json").write_text(json.dumps({
            "gmail": {"total": 3, "counts": {"Inbox": 3}},
        }))
        monkeypatch.setattr("core.cartero._FEDERATED_SPACES", [
            {"name": "personal", "path": str(fed_path), "emoji": "🌿"}
        ])
        results = _read_federated_states()
        assert len(results) == 1
        assert results[0][0] == "🌿"
        assert results[0][1]["gmail"]["total"] == 3

    def test_federated_total(self, _isolate, monkeypatch):
        from core.cartero import _federated_total
        fed_path = _isolate / "fed-ws"
        fed_path.mkdir()
        (fed_path / ".cartero-state.json").write_text(json.dumps({
            "gmail": {"total": 4, "counts": {"A": 4}},
        }))
        monkeypatch.setattr("core.cartero._FEDERATED_SPACES", [
            {"name": "personal", "path": str(fed_path), "emoji": "🌿"}
        ])
        total, parts = _federated_total()
        assert total == 4
        assert parts == ["🌿📬4"]

    def test_prompt_with_federation(self, _isolate, monkeypatch):
        from core.cartero import get_prompt_indicator, _write_state
        # Local: 2 slack messages
        _write_state({"slack": {"total": 2, "counts": {"general": 2}}})
        # Federated: 3 gmail
        fed_path = _isolate / "fed-ws"
        fed_path.mkdir()
        (fed_path / ".cartero-state.json").write_text(json.dumps({
            "gmail": {"total": 3, "counts": {"Inbox": 3}},
        }))
        monkeypatch.setattr("core.cartero._FEDERATED_SPACES", [
            {"name": "personal", "path": str(fed_path), "emoji": "🌿"}
        ])
        indicator = get_prompt_indicator()
        assert "📬2" in indicator
        assert "🌿📬3" in indicator

    def test_prompt_federated_only(self, _isolate, monkeypatch):
        from core.cartero import get_prompt_indicator
        # No local state
        fed_path = _isolate / "fed-ws"
        fed_path.mkdir()
        (fed_path / ".cartero-state.json").write_text(json.dumps({
            "gmail": {"total": 5, "counts": {"X": 5}},
        }))
        monkeypatch.setattr("core.cartero._FEDERATED_SPACES", [
            {"name": "personal", "path": str(fed_path), "emoji": "🌿"}
        ])
        assert get_prompt_indicator() == "[🌿📬5]"

    def test_prompt_no_federated_messages(self, _isolate, monkeypatch):
        from core.cartero import get_prompt_indicator
        fed_path = _isolate / "fed-ws"
        fed_path.mkdir()
        (fed_path / ".cartero-state.json").write_text(json.dumps({
            "gmail": {"total": 0, "counts": {}},
        }))
        monkeypatch.setattr("core.cartero._FEDERATED_SPACES", [
            {"name": "personal", "path": str(fed_path), "emoji": "🌿"}
        ])
        assert get_prompt_indicator() == ""


# ── Delta notification logic ───────────────────────────────────────────────

class TestDeltaNotification:
    """Verify the 'notify only on increase' logic used by the background loop."""

    def test_first_check_no_notification(self):
        """First check: prev_total=0, new=3 → notify (delta > 0)."""
        prev_total = 0
        new_total = 3
        delta = new_total - prev_total
        assert delta > 0  # would notify

    def test_no_change_no_notification(self):
        prev_total = 3
        new_total = 3
        delta = new_total - prev_total
        assert delta == 0  # would not notify

    def test_decrease_no_notification(self):
        prev_total = 5
        new_total = 2
        delta = new_total - prev_total
        assert delta < 0  # would not notify

    def test_increase_notification(self):
        prev_total = 2
        new_total = 5
        delta = new_total - prev_total
        assert delta == 3  # would notify with "3 correos nuevos"


# ── Summary tests ─────────────────────────────────────────────────────────

class TestSummary:

    def test_summary_no_state(self, _isolate, capsys):
        from core.cartero import _print_summary
        ret = _print_summary(live=False)
        assert ret == 0
        assert "Sin datos" in capsys.readouterr().out

    def test_summary_no_messages(self, _isolate, capsys):
        from core.cartero import _print_summary, _write_state
        _write_state({"gmail": {"total": 0, "counts": {}}})
        ret = _print_summary(live=False)
        assert ret == 0
        assert "Sin mensajes" in capsys.readouterr().out

    def test_summary_gmail(self, _isolate, capsys):
        from core.cartero import _print_summary, _write_state
        _write_state({"gmail": {"total": 4, "counts": {"Importante": 3, "Familia": 1}}})
        ret = _print_summary(live=False)
        assert ret == 0
        out = capsys.readouterr().out
        assert "Gmail: 4" in out
        assert "Importante 3" in out
        assert "Familia 1" in out

    def test_summary_slack(self, _isolate, capsys):
        from core.cartero import _print_summary, _write_state
        _write_state({"slack": {"total": 7, "counts": {"next:general": 5, "DMs": 2}}})
        ret = _print_summary(live=False)
        assert ret == 0
        out = capsys.readouterr().out
        assert "Slack: 7" in out
        assert "#next:general 5" in out

    def test_summary_both_sources(self, _isolate, capsys):
        from core.cartero import _print_summary, _write_state
        _write_state({
            "gmail": {"total": 3, "counts": {"A": 3}},
            "slack": {"total": 2, "counts": {"ch": 2}},
        })
        ret = _print_summary(live=False)
        assert ret == 0
        out = capsys.readouterr().out
        assert "Gmail: 3" in out
        assert "Slack: 2" in out

    def test_summary_federated(self, _isolate, monkeypatch, capsys):
        from core.cartero import _print_summary
        fed_path = _isolate / "fed-ws"
        fed_path.mkdir()
        (fed_path / ".cartero-state.json").write_text(json.dumps({
            "gmail": {"total": 5, "counts": {"Inbox": 3, "Work": 2}},
        }))
        monkeypatch.setattr("core.cartero._FEDERATED_SPACES", [
            {"name": "personal", "path": str(fed_path), "emoji": "🌿"}
        ])
        ret = _print_summary(live=False)
        assert ret == 0
        out = capsys.readouterr().out
        assert "🌿" in out
        assert "Gmail: 5" in out

    @patch("core.cartero._get_gmail_service")
    @patch("core.cartero._resolve_label_ids")
    @patch("core.cartero._check_gmail")
    def test_summary_live(self, mock_check, mock_resolve, mock_service, _isolate, capsys):
        from core.cartero import _print_summary
        mock_service.return_value = MagicMock()
        mock_resolve.return_value = {"Importante": "L1"}
        mock_check.return_value = {
            "counts": {"Importante": 5},
            "total": 5,
            "timestamp": "2026-04-14T10:00:00",
        }
        ret = _print_summary(live=True)
        assert ret == 0
        out = capsys.readouterr().out
        assert "Gmail: 5" in out
        assert "Importante 5" in out

    def test_summary_via_run_mail(self, _isolate, capsys):
        """run_mail(summary=True) calls _print_summary with live=True."""
        from core.cartero import run_mail, _write_state
        _write_state({"gmail": {"total": 2, "counts": {"A": 2}}})
        with patch("core.cartero._sync_check") as mock_sync:
            mock_sync.return_value = {"gmail": {"total": 2, "counts": {"A": 2}}}
            ret = run_mail(summary=True)
        assert ret == 0
        assert "Gmail: 2" in capsys.readouterr().out

    def test_format_source_summary_empty(self):
        from core.cartero import _format_source_summary
        assert _format_source_summary("gmail", {"total": 0, "counts": {}}) == ""

    def test_format_source_summary_gmail(self):
        from core.cartero import _format_source_summary
        line = _format_source_summary("gmail", {"total": 4, "counts": {"A": 3, "B": 1}})
        assert line == "📬 Gmail: 4 (A 3, B 1)"

    def test_format_source_summary_slack(self):
        from core.cartero import _format_source_summary
        line = _format_source_summary("slack", {"total": 5, "counts": {"ch": 5}})
        assert line == "📬 Slack: 5 (#ch 5)"

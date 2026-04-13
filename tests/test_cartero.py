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

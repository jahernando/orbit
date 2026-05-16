"""Tests for F4: shell_start chain registration + action wrappers.

The wrappers in core/shell.py adapt orbit startup helpers (doctor, agenda,
cloudsync, commit, gsync, cartero, dash) into the hook registry. These tests
cover:
  - Chain `shell_start` is registered with the expected actions in the right order.
  - `shell_startup` trigger is bound to `shell_start`.
  - Trigger type is temporal.
  - Each action wrapper routes to its underlying helper.
  - doctor_startup handles the three branches (still alive, clean, has issues).
  - advance_overdue_recurring prints only when there are advances.
  - dash_render swallows exceptions cleanly.
"""
import threading
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from core import shell, hooks


@pytest.fixture
def reset_journal(tmp_path, monkeypatch):
    monkeypatch.setattr(hooks, "JOURNAL_PATH", tmp_path / ".journal.jsonl")
    monkeypatch.setattr(hooks, "_load_orbit_json", lambda: {})


# ── Chain registration ───────────────────────────────────────────────────────

def test_shell_start_chain_registered():
    chain = hooks.CHAINS.get("shell_start")
    assert chain is not None
    assert chain.trigger_type == "temporal"
    assert chain.pre == []
    assert chain.core is None
    assert chain.post == [
        "doctor_startup",
        "advance_overdue_recurring",
        "cloud_sync_status_check",
        "untracked_check",
        "commit_offer",
        "code_update_check",
        "cartero_startup",
        "ring_refresh",
        "dash_render",
        "dash_background_loop_start",
    ]


def test_shell_startup_trigger_bound():
    assert hooks.BINDINGS["shell_startup"] == "shell_start"


def test_shell_actions_all_registered():
    for name in (
        "doctor_startup", "advance_overdue_recurring", "cloud_sync_status_check",
        "untracked_check", "commit_offer", "code_update_check",
        "cartero_startup", "ring_refresh",
        "dash_render", "dash_background_loop_start",
    ):
        assert name in hooks.ACTIONS, f"Missing: {name}"
        assert hooks.ACTIONS[name].critical is False, name


# ── doctor_startup ───────────────────────────────────────────────────────────

def test_doctor_startup_still_running(capsys):
    fake_thread = MagicMock()
    fake_thread.is_alive.return_value = True
    with patch("views.doctor.doctor.doctor_background",
               return_value=(fake_thread, [])):
        result = shell._action_doctor_startup(None)
    assert result == {"ok": True, "msg": "still running"}
    assert "aún revisando" in capsys.readouterr().out


def test_doctor_startup_clean():
    fake_thread = MagicMock()
    fake_thread.is_alive.return_value = False
    with patch("views.doctor.doctor.doctor_background",
               return_value=(fake_thread, [])):
        result = shell._action_doctor_startup(None)
    assert result == {"ok": True, "msg": "clean"}


def test_doctor_startup_with_issues(capsys):
    fake_thread = MagicMock()
    fake_thread.is_alive.return_value = False
    issue_unfix = SimpleNamespace(
        fix=None, project="p", file="agenda.md",
        line_num=10, msg="bad line", line="raw text",
    )
    issue_fix = SimpleNamespace(
        fix=lambda: None, project="p", file="agenda.md",
        line_num=11, msg="fixable", line="raw text",
    )
    with patch("views.doctor.doctor.doctor_background",
               return_value=(fake_thread, [issue_unfix, issue_fix])), \
         patch("views.doctor.doctor._interactive_fix") as fix:
        result = shell._action_doctor_startup(None)
    fix.assert_called_once()
    assert result["ok"] is True
    assert "2 issues" in result["msg"]
    out = capsys.readouterr().out
    assert "2 problemas de sintaxis" in out


# ── advance_overdue_recurring ────────────────────────────────────────────────

def test_advance_overdue_recurring_no_advances(capsys):
    with patch("core.agenda_cmds.startup_advance_past_recurring", return_value=[]):
        result = shell._action_advance_overdue_recurring(None)
    assert result == {"ok": True, "msg": "0 advanced"}
    # No output when nothing happened.
    assert capsys.readouterr().out == ""


def test_advance_overdue_recurring_some(capsys):
    advances = ["[proj] Yoga → 2026-05-15", "[proj] Reunión → 2026-05-20"]
    with patch("core.agenda_cmds.startup_advance_past_recurring",
               return_value=advances):
        result = shell._action_advance_overdue_recurring(None)
    assert result == {"ok": True, "msg": "2 advanced"}
    out = capsys.readouterr().out
    assert "2 citas recurrentes" in out
    assert "Yoga" in out
    assert "Reunión" in out


# ── Trivial wrappers (delegate to helper) ────────────────────────────────────

def test_cloud_sync_status_check_delegates():
    with patch("core.cloudsync.startup_cloud_check") as h:
        shell._action_cloud_sync_status_check(None)
    h.assert_called_once()


def test_untracked_check_delegates():
    with patch("core.startup.startup_untracked_check") as h:
        shell._action_untracked_check(None)
    h.assert_called_once()


def test_commit_offer_delegates():
    with patch("core.startup.startup_commit_offer") as h:
        shell._action_commit_offer(None)
    h.assert_called_once()


def test_code_update_check_delegates():
    with patch("core.startup.startup_code_update_check") as h:
        shell._action_code_update_check(None)
    h.assert_called_once()


def test_cartero_startup_delegates():
    with patch("core.cartero_invoke.startup_cartero") as h:
        shell._action_cartero_startup(None)
    h.assert_called_once()


# ── dash_render — exception swallowing ───────────────────────────────────────

def test_dash_render_success():
    with patch("orbit.run_dash") as h:
        result = shell._action_dash_render(None)
    h.assert_called_once_with(silent=False)
    assert result["ok"] is True


def test_dash_render_swallows_exception():
    with patch("orbit.run_dash", side_effect=RuntimeError("boom")):
        result = shell._action_dash_render(None)
    assert result["ok"] is False
    assert "RuntimeError" in result["msg"]


# ── dash_background_loop_start ───────────────────────────────────────────────

def test_dash_background_loop_start_spawns_daemon():
    """Verify a daemon thread is started. We immediately stop it to avoid leaks."""
    shell._dash_stop.set()  # ensure the loop exits on first wait()
    try:
        with patch("core.shell.threading.Thread") as MockThread:
            instance = MockThread.return_value
            result = shell._action_dash_background_loop_start(None)
        MockThread.assert_called_once()
        kwargs = MockThread.call_args.kwargs
        assert kwargs["daemon"] is True
        instance.start.assert_called_once()
        assert result == {"ok": True, "msg": "daemon started"}
    finally:
        shell._dash_stop.clear()


# ── day_open chain (F5.2) ────────────────────────────────────────────────────

def test_day_open_chain_registered():
    chain = hooks.CHAINS.get("day_open")
    assert chain is not None
    assert chain.trigger_type == "temporal"
    assert chain.post == [
        "advance_overdue_recurring",
        "dash_render",
    ]


def test_day_changed_trigger_bound():
    assert hooks.BINDINGS["day_changed"] == "day_open"


def test_dash_render_silent_via_ctx(capsys):
    with patch("orbit.run_dash") as h:
        shell._action_dash_render({"silent": True})
    h.assert_called_once_with(silent=True)
    out = capsys.readouterr().out
    # No leading print() separator when silent
    assert out == ""


def test_dash_render_non_silent_default(capsys):
    with patch("orbit.run_dash") as h:
        shell._action_dash_render(None)
    h.assert_called_once_with(silent=False)
    # Leading print() separator emits a newline
    assert capsys.readouterr().out == "\n"


def test_day_open_fires_all_actions(reset_journal):
    """Fire day_changed; verify the two actions run with silent ctx."""
    with patch("core.agenda_cmds.startup_advance_past_recurring", return_value=[]), \
         patch("orbit.run_dash") as dash:
        results = hooks.fire("day_changed", ctx={"silent": True},
                              verbosity="quiet")

    assert [r.action for r in results] == [
        "advance_overdue_recurring",
        "dash_render",
    ]
    assert all(r.ok for r in results)
    dash.assert_called_once_with(silent=True)


# ── End-to-end ──────────────────────────────────────────────────────────────

def test_shell_startup_fires_all_actions_in_order(reset_journal):
    """Fire the trigger with every helper mocked; verify call order."""
    calls = []

    def record(name):
        def fn(*a, **kw):
            calls.append(name)
            # doctor_background returns (thread, issues)
            if name == "doctor_background":
                fake_thread = MagicMock()
                fake_thread.is_alive.return_value = False
                return (fake_thread, [])
            if name == "startup_advance_past_recurring":
                return []
            return None
        return fn

    with patch("views.doctor.doctor.doctor_background", side_effect=record("doctor_background")), \
         patch("core.agenda_cmds.startup_advance_past_recurring",
               side_effect=record("startup_advance_past_recurring")), \
         patch("core.cloudsync.startup_cloud_check",
               side_effect=record("startup_cloud_check")), \
         patch("core.startup.startup_untracked_check",
               side_effect=record("startup_untracked_check")), \
         patch("core.startup.startup_commit_offer",
               side_effect=record("startup_commit_offer")), \
         patch("core.startup.startup_code_update_check",
               side_effect=record("startup_code_update_check")), \
         patch("core.cartero_invoke.startup_cartero",
               side_effect=record("startup_cartero")), \
         patch("views.ring.export.refresh_all",
               side_effect=lambda *a, **kw: (calls.append("ring_refresh_all") or [])), \
         patch("views.ring.export.invoke_daemon", return_value=(True, "noop")), \
         patch("orbit.run_dash", side_effect=record("run_dash")), \
         patch("core.shell.threading.Thread") as MockThread:
        MockThread.return_value.start = lambda: calls.append("dash_daemon_thread")
        results = hooks.fire("shell_startup", verbosity="quiet")

    assert calls == [
        "doctor_background",
        "startup_advance_past_recurring",
        "startup_cloud_check",
        "startup_untracked_check",
        "startup_commit_offer",
        "startup_code_update_check",
        "startup_cartero",
        "ring_refresh_all",
        "run_dash",
        "dash_daemon_thread",
    ]
    assert all(r.ok for r in results)
    assert [r.action for r in results] == [
        "doctor_startup",
        "advance_overdue_recurring",
        "cloud_sync_status_check",
        "untracked_check",
        "commit_offer",
        "code_update_check",
        "cartero_startup",
        "ring_refresh",
        "dash_render",
        "dash_background_loop_start",
    ]


def test_shell_startup_non_critical_failure_continues(reset_journal):
    """If one action errors, the rest still run."""
    fake_thread = MagicMock()
    fake_thread.is_alive.return_value = False
    with patch("views.doctor.doctor.doctor_background", return_value=(fake_thread, [])), \
         patch("core.agenda_cmds.startup_advance_past_recurring",
               side_effect=RuntimeError("boom")), \
         patch("core.cloudsync.startup_cloud_check") as cloud, \
         patch("core.startup.startup_untracked_check"), \
         patch("core.startup.startup_commit_offer"), \
         patch("core.startup.startup_code_update_check"), \
         patch("core.cartero_invoke.startup_cartero"), \
         patch("orbit.run_dash"), \
         patch("core.shell.threading.Thread"):
        results = hooks.fire("shell_startup", verbosity="quiet")

    # advance_overdue_recurring failed
    failed = [r for r in results if not r.ok]
    assert len(failed) == 1
    assert failed[0].action == "advance_overdue_recurring"
    # But cloud_sync_status_check still ran (chain didn't abort)
    cloud.assert_called_once()

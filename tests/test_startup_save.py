"""startup_commit_offer: save+push del arranque/`end` sin preguntar."""
import sys

import pytest


class _Tty:
    def isatty(self):
        return True


@pytest.fixture
def env(monkeypatch):
    import core.startup as st
    calls = {"commit": [], "push": 0, "prompts": []}
    monkeypatch.setattr(st, "_git_status", lambda: [("M", "logbook.md")])
    monkeypatch.setattr(st, "_git_commit", lambda m: calls["commit"].append(m) or 0)
    monkeypatch.setattr(st, "_can_push", lambda: True)

    def push():
        calls["push"] += 1
        return 0
    monkeypatch.setattr(st, "_git_push", push)
    monkeypatch.setattr("views.render.render.render_changed_to_cloud_background",
                        lambda: None)
    monkeypatch.setattr("builtins.input",
                        lambda p="": calls["prompts"].append(p) or "s")
    return st, calls


def test_saves_and_pushes_without_prompt(env, monkeypatch):
    st, calls = env
    monkeypatch.setattr(sys, "stdin", _Tty())
    st.startup_commit_offer()
    assert calls["prompts"] == []
    assert len(calls["commit"]) == 1 and calls["commit"][0].startswith("sync ")
    assert calls["push"] == 1


def test_non_tty_does_nothing(env, monkeypatch):
    st, calls = env
    monkeypatch.setattr(sys, "stdin", open("/dev/null"))
    st.startup_commit_offer()
    assert calls["commit"] == [] and calls["push"] == 0

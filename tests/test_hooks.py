"""Tests for core/hooks.py — registry + fire() execution.

See HOOKSYSTEM.md for the model these tests exercise.
"""
import json

import pytest

from core import hooks
from core.hooks import (
    HookResult,
    bind,
    describe_chain,
    fire,
    list_actions,
    list_chains,
    register_action,
    register_chain,
    to_json_catalog,
    _reset_registries_for_test,
)


@pytest.fixture(autouse=True)
def clean_registries():
    """Isolate each test: start with empty registries, restore globals after.

    Other test modules (test_commit_hooks, test_shell_hooks) rely on the
    module-import-time registrations done by core.commit / core.shell. Just
    clearing the registries would break them when tests interleave.
    """
    saved_actions = dict(hooks.ACTIONS)
    saved_chains = dict(hooks.CHAINS)
    saved_bindings = dict(hooks.BINDINGS)
    _reset_registries_for_test()
    yield
    _reset_registries_for_test()
    hooks.ACTIONS.update(saved_actions)
    hooks.CHAINS.update(saved_chains)
    hooks.BINDINGS.update(saved_bindings)


@pytest.fixture
def tmp_journal(tmp_path, monkeypatch):
    journal = tmp_path / ".journal.jsonl"
    monkeypatch.setattr(hooks, "JOURNAL_PATH", journal)
    return journal


@pytest.fixture
def empty_orbit_json(monkeypatch):
    monkeypatch.setattr(hooks, "_load_orbit_json", lambda: {})


@pytest.fixture
def orbit_json(monkeypatch):
    cfg: dict = {}
    monkeypatch.setattr(hooks, "_load_orbit_json", lambda: cfg)
    return cfg


# ── Registration ──────────────────────────────────────────────────────────────

def test_register_action_records_name_and_defaults():
    register_action("foo", lambda ctx: None)
    a = hooks.ACTIONS["foo"]
    assert a.cli_flag == "--no-foo"
    assert a.disable_config_key == "foo"
    assert a.critical is False


def test_register_action_critical_flag():
    register_action("foo", lambda ctx: None, critical=True)
    assert hooks.ACTIONS["foo"].critical is True


def test_register_chain_records_components():
    register_chain("ch", trigger_type="explicit",
                   pre=["a"], core="b", post=["c", "d"])
    c = hooks.CHAINS["ch"]
    assert c.pre == ["a"]
    assert c.core == "b"
    assert c.post == ["c", "d"]


def test_bind_records_trigger_to_chain():
    bind("on_thing", "ch")
    assert hooks.BINDINGS["on_thing"] == "ch"


# ── Firing: ordering and ctx ──────────────────────────────────────────────────

def test_fire_runs_in_pre_core_post_order(empty_orbit_json, tmp_journal):
    calls = []
    register_action("p1", lambda ctx: calls.append("p1"))
    register_action("co", lambda ctx: calls.append("co"))
    register_action("po", lambda ctx: calls.append("po"))
    register_chain("c", trigger_type="explicit",
                   pre=["p1"], core="co", post=["po"])
    bind("t", "c")
    results = fire("t")
    assert [r.action for r in results] == ["p1", "co", "po"]
    assert calls == ["p1", "co", "po"]
    assert all(r.ok for r in results)


def test_fire_passes_ctx_to_fn(empty_orbit_json, tmp_journal):
    seen = []
    register_action("a", lambda ctx: seen.append(ctx))
    register_chain("c", trigger_type="explicit", post=["a"])
    bind("t", "c")
    fire("t", ctx={"hello": 42})
    assert seen == [{"hello": 42}]


def test_fire_returns_empty_when_trigger_not_bound(empty_orbit_json, tmp_journal):
    assert fire("nonexistent") == []


def test_fire_returns_empty_when_chain_not_registered(empty_orbit_json, tmp_journal):
    bind("t", "missing")
    assert fire("t") == []


def test_fire_marks_unregistered_action_as_skipped(empty_orbit_json, tmp_journal):
    register_chain("c", trigger_type="explicit", post=["ghost"])
    bind("t", "c")
    results = fire("t")
    assert len(results) == 1
    assert results[0].skipped
    assert results[0].skip_reason == "not-registered"


# ── Dry-run ───────────────────────────────────────────────────────────────────

def test_dry_run_does_not_call_fn(empty_orbit_json, tmp_journal):
    calls = []
    register_action("a", lambda ctx: calls.append("a"))
    register_chain("c", trigger_type="explicit", post=["a"])
    bind("t", "c")
    results = fire("t", dry_run=True)
    assert calls == []
    assert results[0].skipped
    assert results[0].skip_reason == "dry-run"


# ── Skip via per-call argument (CLI flag level) ───────────────────────────────

def test_skip_actions_per_call(empty_orbit_json, tmp_journal):
    calls = []
    register_action("a", lambda ctx: calls.append("a"))
    register_action("b", lambda ctx: calls.append("b"))
    register_chain("c", trigger_type="explicit", post=["a", "b"])
    bind("t", "c")
    results = fire("t", skip_actions=["a"])
    assert calls == ["b"]
    assert results[0].skipped
    assert results[0].skip_reason == "--no-flag"


# ── Kill switch via config (global) ───────────────────────────────────────────

def test_kill_switch_action_off(orbit_json, tmp_journal):
    orbit_json["hooks"] = {"actions": {"a": "off"}}
    calls = []
    register_action("a", lambda ctx: calls.append("a"))
    register_chain("c", trigger_type="explicit", post=["a"])
    bind("t", "c")
    results = fire("t")
    assert calls == []
    assert results[0].skipped
    assert results[0].skip_reason == "config=off"


def test_kill_switch_action_dict_off(orbit_json, tmp_journal):
    orbit_json["hooks"] = {"actions": {"a": {"off": True}}}
    calls = []
    register_action("a", lambda ctx: calls.append("a"))
    register_chain("c", trigger_type="explicit", post=["a"])
    bind("t", "c")
    fire("t")
    assert calls == []


# ── Binding override (binding-level) ──────────────────────────────────────────

def test_binding_override_null_disables_trigger(orbit_json, tmp_journal):
    orbit_json["hooks"] = {"bindings": {"t": None}}
    calls = []
    register_action("a", lambda ctx: calls.append("a"))
    register_chain("c", trigger_type="explicit", post=["a"])
    bind("t", "c")
    results = fire("t")
    assert calls == []
    assert results == []


def test_binding_override_swaps_chain(orbit_json, tmp_journal):
    orbit_json["hooks"] = {"bindings": {"t": "other"}}
    calls = []
    register_action("a", lambda ctx: calls.append("a"))
    register_action("b", lambda ctx: calls.append("b"))
    register_chain("default", trigger_type="explicit", post=["a"])
    register_chain("other", trigger_type="explicit", post=["b"])
    bind("t", "default")
    fire("t")
    assert calls == ["b"]


# ── Critical vs non-critical failure ──────────────────────────────────────────

def test_critical_failure_aborts_chain(empty_orbit_json, tmp_journal):
    calls = []
    def boom(ctx):
        raise RuntimeError("boom")
    register_action("a", boom, critical=True)
    register_action("b", lambda ctx: calls.append("b"))
    register_chain("c", trigger_type="explicit", post=["a", "b"])
    bind("t", "c")
    results = fire("t")
    assert calls == []
    assert len(results) == 1
    assert results[0].ok is False
    assert "boom" in results[0].msg


def test_non_critical_failure_continues_chain(empty_orbit_json, tmp_journal):
    calls = []
    def boom(ctx):
        raise RuntimeError("boom")
    register_action("a", boom)
    register_action("b", lambda ctx: calls.append("b"))
    register_chain("c", trigger_type="explicit", post=["a", "b"])
    bind("t", "c")
    results = fire("t")
    assert calls == ["b"]
    assert len(results) == 2
    assert results[0].ok is False
    assert results[1].ok is True


def test_critical_failure_via_dict_return_aborts(empty_orbit_json, tmp_journal):
    calls = []
    register_action("a", lambda ctx: {"ok": False, "msg": "validation failed"},
                   critical=True)
    register_action("b", lambda ctx: calls.append("b"))
    register_chain("c", trigger_type="explicit", post=["a", "b"])
    bind("t", "c")
    results = fire("t")
    assert calls == []
    assert len(results) == 1
    assert results[0].msg == "validation failed"


# ── Journal ───────────────────────────────────────────────────────────────────

def test_journal_writes_one_entry_per_chain(orbit_json, tmp_journal):
    register_action("a", lambda ctx: None)
    register_chain("c", trigger_type="explicit", post=["a"])
    bind("t", "c")
    fire("t")
    fire("t")
    lines = tmp_journal.read_text().splitlines()
    assert len(lines) == 2
    entry = json.loads(lines[0])
    assert entry["trigger"] == "t"
    assert entry["chain"] == "c"
    assert entry["results"][0]["action"] == "a"
    assert entry["results"][0]["ok"] is True


def test_journal_opt_out_via_config(orbit_json, tmp_journal):
    orbit_json["hooks"] = {"journal": False}
    register_action("a", lambda ctx: None)
    register_chain("c", trigger_type="explicit", post=["a"])
    bind("t", "c")
    fire("t")
    assert not tmp_journal.exists()


def test_journal_records_failures(orbit_json, tmp_journal):
    def boom(ctx):
        raise ValueError("nope")
    register_action("a", boom)
    register_chain("c", trigger_type="explicit", post=["a"])
    bind("t", "c")
    fire("t")
    entry = json.loads(tmp_journal.read_text().splitlines()[0])
    assert entry["results"][0]["ok"] is False
    assert "nope" in entry["results"][0]["msg"]


# ── Action return-shape adapters ──────────────────────────────────────────────

def test_action_can_return_hookresult(empty_orbit_json, tmp_journal):
    register_action("a", lambda ctx: HookResult(
        action="a", ok=True, msg="42 items", data=[1, 2]))
    register_chain("c", trigger_type="explicit", post=["a"])
    bind("t", "c")
    results = fire("t")
    assert results[0].msg == "42 items"
    assert results[0].data == [1, 2]


def test_action_can_return_dict_with_ok(empty_orbit_json, tmp_journal):
    register_action("a", lambda ctx: {"ok": False, "msg": "failed lookup"})
    register_chain("c", trigger_type="explicit", post=["a"])
    bind("t", "c")
    results = fire("t")
    assert results[0].ok is False
    assert results[0].msg == "failed lookup"


def test_action_returning_none_is_ok(empty_orbit_json, tmp_journal):
    register_action("a", lambda ctx: None)
    register_chain("c", trigger_type="explicit", post=["a"])
    bind("t", "c")
    results = fire("t")
    assert results[0].ok is True
    assert results[0].msg == ""


# ── Output formatting ─────────────────────────────────────────────────────────

def test_print_format_for_success(empty_orbit_json, tmp_journal, capsys):
    register_action("a", lambda ctx: None)
    register_chain("c", trigger_type="explicit", post=["a"])
    bind("t", "c")
    fire("t")
    out = capsys.readouterr().out
    assert "→ a" in out
    assert "ms)" in out


def test_print_format_for_failure(empty_orbit_json, tmp_journal, capsys):
    def boom(ctx):
        raise ValueError("nope")
    register_action("a", boom)
    register_chain("c", trigger_type="explicit", post=["a"])
    bind("t", "c")
    fire("t")
    out = capsys.readouterr().out
    assert "✗ a" in out
    assert "nope" in out


def test_print_format_temporal_trigger_includes_header(empty_orbit_json, tmp_journal, capsys):
    register_action("a", lambda ctx: None)
    register_chain("c", trigger_type="temporal", post=["a"])
    bind("startup", "c")
    fire("startup")
    out = capsys.readouterr().out
    assert "[trigger=startup]" in out


def test_print_format_explicit_trigger_no_header(empty_orbit_json, tmp_journal, capsys):
    register_action("a", lambda ctx: None)
    register_chain("c", trigger_type="explicit", post=["a"])
    bind("t", "c")
    fire("t")
    out = capsys.readouterr().out
    assert "[trigger=t]" not in out


def test_quiet_verbosity_suppresses_success(empty_orbit_json, tmp_journal, capsys):
    register_action("a", lambda ctx: None)
    register_chain("c", trigger_type="explicit", post=["a"])
    bind("t", "c")
    fire("t", verbosity="quiet")
    out = capsys.readouterr().out
    assert "→ a" not in out


def test_quiet_verbosity_still_shows_failures(empty_orbit_json, tmp_journal, capsys):
    def boom(ctx):
        raise ValueError("nope")
    register_action("a", boom)
    register_chain("c", trigger_type="explicit", post=["a"])
    bind("t", "c")
    fire("t", verbosity="quiet")
    out = capsys.readouterr().out
    assert "✗ a" in out


# ── Introspection ─────────────────────────────────────────────────────────────

def test_list_chains_and_actions():
    register_action("a", lambda ctx: None)
    register_action("b", lambda ctx: None)
    register_chain("c1", trigger_type="explicit", post=["a"])
    register_chain("c2", trigger_type="reactive", post=["b"])
    assert list_chains() == ["c1", "c2"]
    assert list_actions() == ["a", "b"]


def test_describe_chain_returns_dict():
    register_chain("c", trigger_type="explicit", pre=["x"], core="y", post=["z"])
    d = describe_chain("c")
    assert d["pre"] == ["x"]
    assert d["core"] == "y"
    assert d["post"] == ["z"]
    assert d["trigger_type"] == "explicit"


def test_describe_chain_returns_none_for_missing():
    assert describe_chain("nonexistent") is None


def test_to_json_catalog_is_serializable():
    register_action("a", lambda ctx: None, critical=True)
    register_chain("c", trigger_type="explicit", post=["a"])
    bind("t", "c")
    catalog = to_json_catalog()
    parsed = json.loads(json.dumps(catalog))
    assert parsed["actions"]["a"]["critical"] is True
    assert parsed["chains"]["c"]["post"] == ["a"]
    assert parsed["bindings"]["t"] == "c"


# ── Catalog bootstrap (F6) ───────────────────────────────────────────────────

def test_bootstrap_with_missing_path_returns_false(tmp_path):
    missing = tmp_path / "no-such.json"
    assert hooks.bootstrap(missing) is False


def test_bootstrap_loads_default_catalog():
    """Loading the real catalog should register all the chains.

    Post-fase C (2026-05-16): chain `render` y binding `after_render` eliminados;
    ics_emit_workspace vive ahora en commit_post directo.
    """
    assert hooks.bootstrap() is True
    assert "commit_pre" in hooks.CHAINS
    assert "commit_post" in hooks.CHAINS
    assert "shell_start" in hooks.CHAINS
    assert "day_open" in hooks.CHAINS
    assert "render" not in hooks.CHAINS
    assert hooks.BINDINGS["commit_pre"] == "commit_pre"
    assert hooks.BINDINGS["shell_startup"] == "shell_start"
    assert "after_render" not in hooks.BINDINGS


def test_bootstrap_loads_non_critical_flag():
    # Verify default critical=False round-trips correctly through bootstrap.
    hooks.bootstrap()
    assert hooks.ACTIONS["cloud_imgs_process"].critical is False
    assert hooks.ACTIONS["render_changed_background"].critical is False


def test_bootstrap_is_idempotent():
    hooks.bootstrap()
    chains_first = dict(hooks.CHAINS)
    hooks.bootstrap()
    chains_second = dict(hooks.CHAINS)
    # Same chain names; identity of Chain objects may differ (we re-register).
    assert set(chains_first.keys()) == set(chains_second.keys())


def test_bootstrap_loads_custom_catalog(tmp_path):
    catalog = {
        "actions": {
            "my_action": {
                "module": "core.commit",
                "fn": "_action_cloud_imgs_process",
                "critical": True,
            }
        },
        "chains": {
            "my_chain": {"trigger_type": "explicit", "post": ["my_action"]}
        },
        "bindings": {"my_trigger": "my_chain"},
    }
    catalog_path = tmp_path / "catalog.json"
    catalog_path.write_text(json.dumps(catalog))
    assert hooks.bootstrap(catalog_path) is True
    assert "my_action" in hooks.ACTIONS
    assert hooks.ACTIONS["my_action"].critical is True
    assert hooks.CHAINS["my_chain"].post == ["my_action"]
    assert hooks.BINDINGS["my_trigger"] == "my_chain"


# ── CLI integration (F7) ─────────────────────────────────────────────────────

def test_actions_in_chain_returns_pre_core_post_in_order():
    register_action("p1", lambda ctx: None)
    register_action("co", lambda ctx: None)
    register_action("po1", lambda ctx: None)
    register_action("po2", lambda ctx: None)
    register_chain("c", trigger_type="explicit",
                   pre=["p1"], core="co", post=["po1", "po2"])
    assert hooks.actions_in_chain("c") == ["p1", "co", "po1", "po2"]


def test_actions_in_chain_returns_empty_for_unknown():
    assert hooks.actions_in_chain("nonexistent") == []


def test_add_chain_flags_adds_one_flag_per_action():
    import argparse
    register_action("alpha", lambda ctx: None)
    register_action("beta", lambda ctx: None)
    register_chain("c", trigger_type="explicit", post=["alpha", "beta"])

    parser = argparse.ArgumentParser()
    hooks.add_chain_flags(parser, "c")
    args = parser.parse_args(["--no-alpha"])
    assert args.skip_alpha is True
    assert args.skip_beta is False


def test_add_chain_flags_dedups_across_chains():
    import argparse
    register_action("shared", lambda ctx: None)
    register_action("other", lambda ctx: None)
    register_chain("c1", trigger_type="explicit", post=["shared"])
    register_chain("c2", trigger_type="explicit", post=["shared", "other"])

    parser = argparse.ArgumentParser()
    # Should not raise "conflicting option string" for the shared flag.
    hooks.add_chain_flags(parser, "c1", "c2")
    args = parser.parse_args([])
    assert hasattr(args, "skip_shared")
    assert hasattr(args, "skip_other")


def test_collected_skip_actions_returns_set_flags():
    import argparse
    register_action("a", lambda ctx: None)
    register_action("b", lambda ctx: None)
    register_action("c", lambda ctx: None)
    register_chain("ch", trigger_type="explicit", post=["a", "b", "c"])

    parser = argparse.ArgumentParser()
    hooks.add_chain_flags(parser, "ch")
    args = parser.parse_args(["--no-a", "--no-c"])
    assert hooks.collected_skip_actions(args, "ch") == ["a", "c"]


def test_collected_skip_actions_handles_dashes_in_action_name():
    """Action names with underscores translate to dashes in CLI flags."""
    import argparse
    register_action("foo_bar_baz", lambda ctx: None)
    register_chain("ch", trigger_type="explicit", post=["foo_bar_baz"])

    parser = argparse.ArgumentParser()
    hooks.add_chain_flags(parser, "ch")
    args = parser.parse_args(["--no-foo-bar-baz"])
    assert hooks.collected_skip_actions(args, "ch") == ["foo_bar_baz"]


def test_cli_flag_propagates_to_fire_skip_actions(empty_orbit_json, tmp_journal):
    """End-to-end: parse a --no-X flag, pass to fire, action is skipped."""
    import argparse
    calls = []
    register_action("a", lambda ctx: calls.append("a"))
    register_action("b", lambda ctx: calls.append("b"))
    register_chain("ch", trigger_type="explicit", post=["a", "b"])
    bind("t", "ch")

    parser = argparse.ArgumentParser()
    hooks.add_chain_flags(parser, "ch")
    args = parser.parse_args(["--no-a"])
    skip = hooks.collected_skip_actions(args, "ch")
    fire("t", skip_actions=skip, verbosity="quiet")

    assert calls == ["b"]


def test_bootstrap_clears_existing_state(tmp_path):
    """A second bootstrap with a different catalog replaces, doesn't merge."""
    register_action("stale_action", lambda ctx: None)
    register_chain("stale_chain", trigger_type="explicit", post=["stale_action"])
    bind("stale_trigger", "stale_chain")
    catalog = {
        "actions": {"new_action": {
            "module": "core.commit", "fn": "_action_cloud_imgs_process",
        }},
        "chains": {"new_chain": {"trigger_type": "explicit",
                                   "post": ["new_action"]}},
        "bindings": {"new_trigger": "new_chain"},
    }
    catalog_path = tmp_path / "c.json"
    catalog_path.write_text(json.dumps(catalog))
    hooks.bootstrap(catalog_path)
    assert "stale_action" not in hooks.ACTIONS
    assert "stale_chain" not in hooks.CHAINS
    assert "stale_trigger" not in hooks.BINDINGS

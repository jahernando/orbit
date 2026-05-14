"""hooks.py — orbit hook system: trigger → chain → [pre, core, post] actions.

See HOOKSYSTEM.md for the full design and inventory.

This module is the registry and execution engine. It does NOT define the catalog
of chains — owning modules register their actions/chains at import time; bindings
live in the module-level BINDINGS dict.

Three-level disable controls:
  1. Binding override:  orbit.json["hooks"]["bindings"][trigger] = null   (disable)
                        orbit.json["hooks"]["bindings"][trigger] = "x"    (swap)
  2. Per-call skip:     fire(trigger, skip_actions=["render_changed"])
  3. Global kill switch:orbit.json["hooks"]["actions"][action_name] = "off"

Output: one line per action (default), --quiet (failures only), --verbose (also data).
Journal: <ORBIT_HOME>/.journal.jsonl, opt-out via orbit.json["hooks"]["journal"]=false.

Action signature: every registered fn takes a single `ctx` argument (can be None,
a dict, or any caller-defined value). Returning a HookResult or {"ok": ..., "msg":
..., "data": ...} dict lets the action customise the printed line and journal.
Returning None / any other value = success with no msg.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Literal, Optional

from core.config import ORBIT_HOME, _load_orbit_json

TriggerType = Literal["explicit", "reactive", "temporal"]
VerbosityLevel = Literal["quiet", "normal", "verbose"]

JOURNAL_PATH = ORBIT_HOME / ".journal.jsonl"
JOURNAL_MAX_BYTES = 10 * 1024 * 1024  # 10MB rotation threshold


# ── Data model ────────────────────────────────────────────────────────────────

@dataclass
class HookResult:
    action: str
    ok: bool
    msg: str = ""
    data: Any = None
    duration_ms: int = 0
    skipped: bool = False
    skip_reason: str = ""


@dataclass
class Action:
    name: str
    fn: Callable[..., Any]
    critical: bool = False
    cli_flag: str = ""
    disable_config_key: str = ""


@dataclass
class Chain:
    name: str
    trigger_type: TriggerType
    pre: list = field(default_factory=list)
    core: Optional[str] = None
    post: list = field(default_factory=list)
    cli_verb: str = ""


# Module-level registries. Owning modules call register_action / register_chain
# / bind at import time. Tests use _reset_registries_for_test() to start clean.
ACTIONS: dict = {}
CHAINS: dict = {}
BINDINGS: dict = {}


# ── Registration API ──────────────────────────────────────────────────────────

def register_action(name: str, fn: Callable[..., Any], *,
                    critical: bool = False, cli_flag: str = "",
                    disable_config_key: str = "") -> None:
    """Register an action. Overwriting an existing name is allowed (tests do it)."""
    if not cli_flag:
        cli_flag = "--no-" + name.replace("_", "-")
    if not disable_config_key:
        disable_config_key = name
    ACTIONS[name] = Action(name=name, fn=fn, critical=critical,
                           cli_flag=cli_flag,
                           disable_config_key=disable_config_key)


def register_chain(name: str, *, trigger_type: TriggerType,
                   pre: Optional[list] = None,
                   core: Optional[str] = None,
                   post: Optional[list] = None,
                   cli_verb: str = "") -> None:
    CHAINS[name] = Chain(name=name, trigger_type=trigger_type,
                         pre=list(pre or []), core=core,
                         post=list(post or []), cli_verb=cli_verb)


def bind(trigger: str, chain_name: str) -> None:
    BINDINGS[trigger] = chain_name


# ── Config + resolution ───────────────────────────────────────────────────────

def _load_hooks_config() -> dict:
    """Read orbit.json hooks section. Fresh-read on every fire() — personal CLI scale."""
    try:
        cfg = _load_orbit_json()
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(cfg, dict):
        return {}
    hooks_cfg = cfg.get("hooks", {})
    return hooks_cfg if isinstance(hooks_cfg, dict) else {}


def _action_disabled(disable_key: str, hooks_cfg: dict) -> bool:
    entry = hooks_cfg.get("actions", {}).get(disable_key)
    if entry == "off":
        return True
    if isinstance(entry, dict) and entry.get("off"):
        return True
    return False


def _journal_enabled(hooks_cfg: dict) -> bool:
    return bool(hooks_cfg.get("journal", True))


def _resolve_chain(trigger: str, hooks_cfg: dict) -> Optional[Chain]:
    """Return Chain bound to trigger, honoring orbit.json overrides.

    orbit.json["hooks"]["bindings"][trigger] = null   → chain disabled.
    orbit.json["hooks"]["bindings"][trigger] = "x"    → swap to chain "x".
    Otherwise use module-level BINDINGS[trigger].
    """
    overrides = hooks_cfg.get("bindings", {})
    if trigger in overrides:
        override = overrides[trigger]
        if override is None:
            return None
        return CHAINS.get(override)
    chain_name = BINDINGS.get(trigger)
    if not chain_name:
        return None
    return CHAINS.get(chain_name)


# ── Output ────────────────────────────────────────────────────────────────────

def _print_action(result: HookResult, verbosity: VerbosityLevel = "normal") -> None:
    if verbosity == "quiet":
        if result.ok or result.skipped:
            return
    if result.skipped:
        line = f"⚠ {result.action}: skipped ({result.skip_reason})"
    elif result.ok:
        suffix = f": {result.msg}" if result.msg else ""
        line = f"→ {result.action}{suffix} ({result.duration_ms}ms)"
    else:
        suffix = f": {result.msg}" if result.msg else ": failed"
        line = f"✗ {result.action}{suffix} ({result.duration_ms}ms)"
    print(f"  {line}")
    if verbosity == "verbose" and result.data is not None:
        print(f"    data: {result.data!r}")


# ── Journal ───────────────────────────────────────────────────────────────────

def _rotate_journal_if_needed() -> None:
    try:
        if JOURNAL_PATH.exists() and JOURNAL_PATH.stat().st_size > JOURNAL_MAX_BYTES:
            JOURNAL_PATH.rename(JOURNAL_PATH.with_suffix(".jsonl.1"))
    except OSError:
        pass


def _write_journal(trigger: str, chain_name: str, trigger_type: str,
                   results: list) -> None:
    _rotate_journal_if_needed()
    entry = {
        "when": datetime.now().isoformat(timespec="seconds"),
        "trigger": trigger,
        "trigger_type": trigger_type,
        "chain": chain_name,
        "results": [
            {
                "action": r.action,
                "ok": r.ok,
                "skipped": r.skipped,
                "skip_reason": r.skip_reason,
                "msg": r.msg,
                "ms": r.duration_ms,
            }
            for r in results
        ],
    }
    try:
        with JOURNAL_PATH.open("a") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError:
        pass


# ── Execution ─────────────────────────────────────────────────────────────────

def fire(trigger: str, ctx: Any = None, *,
         dry_run: bool = False,
         skip_actions: Optional[list] = None,
         verbosity: VerbosityLevel = "normal") -> list:
    """Run the chain bound to a trigger. Returns list[HookResult].

    A critical action failure aborts the chain — remaining actions are NOT
    in the returned list. Non-critical failures log and continue.
    """
    skip_set = set(skip_actions or [])
    hooks_cfg = _load_hooks_config()
    chain = _resolve_chain(trigger, hooks_cfg)

    if chain is None:
        return []

    if verbosity != "quiet" and chain.trigger_type != "explicit":
        print(f"[trigger={trigger}] {chain.name}:")

    action_names = []
    action_names.extend(chain.pre)
    if chain.core:
        action_names.append(chain.core)
    action_names.extend(chain.post)

    results = []

    for name in action_names:
        action = ACTIONS.get(name)
        if action is None:
            r = HookResult(action=name, ok=False, skipped=True,
                           skip_reason="not-registered")
            results.append(r)
            _print_action(r, verbosity)
            continue

        if name in skip_set:
            r = HookResult(action=name, ok=True, skipped=True,
                           skip_reason="--no-flag")
            results.append(r)
            _print_action(r, verbosity)
            continue

        if _action_disabled(action.disable_config_key, hooks_cfg):
            r = HookResult(action=name, ok=True, skipped=True,
                           skip_reason="config=off")
            results.append(r)
            _print_action(r, verbosity)
            continue

        if dry_run:
            r = HookResult(action=name, ok=True, skipped=True,
                           skip_reason="dry-run")
            results.append(r)
            _print_action(r, verbosity)
            continue

        t0 = time.monotonic()
        try:
            payload = action.fn(ctx)
        except Exception as exc:
            duration_ms = int((time.monotonic() - t0) * 1000)
            r = HookResult(action=name, ok=False,
                           msg=f"{type(exc).__name__}: {exc}",
                           duration_ms=duration_ms)
            results.append(r)
            _print_action(r, verbosity)
            if action.critical:
                break
            continue

        duration_ms = int((time.monotonic() - t0) * 1000)

        if isinstance(payload, HookResult):
            r = HookResult(action=name, ok=payload.ok, msg=payload.msg,
                           data=payload.data, duration_ms=duration_ms)
        elif isinstance(payload, dict) and "ok" in payload:
            r = HookResult(action=name, ok=bool(payload.get("ok", True)),
                           msg=payload.get("msg", ""),
                           data=payload.get("data"),
                           duration_ms=duration_ms)
        else:
            r = HookResult(action=name, ok=True, msg="", data=payload,
                           duration_ms=duration_ms)
        results.append(r)
        _print_action(r, verbosity)

        if not r.ok and action.critical:
            break

    if _journal_enabled(hooks_cfg):
        _write_journal(trigger, chain.name, chain.trigger_type, results)

    return results


# ── Introspection ─────────────────────────────────────────────────────────────

def list_chains() -> list:
    return sorted(CHAINS.keys())


def list_actions() -> list:
    return sorted(ACTIONS.keys())


def describe_chain(name: str) -> Optional[dict]:
    chain = CHAINS.get(name)
    if chain is None:
        return None
    return {
        "name": chain.name,
        "trigger_type": chain.trigger_type,
        "pre": list(chain.pre),
        "core": chain.core,
        "post": list(chain.post),
        "cli_verb": chain.cli_verb,
    }


def to_json_catalog() -> dict:
    """Serialize the catalog to a JSON-compatible dict (F6 migration target).

    Excludes the `fn` field — actions are referenced by name in JSON.
    """
    return {
        "actions": {
            n: {"critical": a.critical, "cli_flag": a.cli_flag,
                "disable_config_key": a.disable_config_key}
            for n, a in ACTIONS.items()
        },
        "chains": {
            n: {"trigger_type": c.trigger_type, "pre": list(c.pre),
                "core": c.core, "post": list(c.post), "cli_verb": c.cli_verb}
            for n, c in CHAINS.items()
        },
        "bindings": dict(BINDINGS),
    }


# ── Test utilities ────────────────────────────────────────────────────────────

def _reset_registries_for_test() -> None:
    """Clear ACTIONS/CHAINS/BINDINGS. For tests only."""
    ACTIONS.clear()
    CHAINS.clear()
    BINDINGS.clear()

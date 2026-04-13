"""cartero — background mail/messaging notifier for Orbit.

Polls Gmail and/or Slack for unread messages and:
  - Updates a shared state file (ORBIT_HOME/.cartero-state.json)
  - Shows a prompt indicator [📬N] in the Orbit shell
  - Sends macOS notifications when new messages arrive

Configuration in orbit.json:
  "cartero": {
    "gmail": {
      "labels": ["Importante", "Familia"],
      "interval": 600
    },
    "slack": {
      "channels": ["general", "alertas"],
      "interval": 600
    }
  }

Slack token: ORBIT_HOME/.slack-token (one line, xoxp-... user token)
"""

import json
import os
import signal
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from core.config import ORBIT_HOME, _FEDERATED_SPACES

# ── Paths ───────────────────────────────────────────────────────────────────

CARTERO_PID   = ORBIT_HOME / ".cartero.pid"
CARTERO_STATE = ORBIT_HOME / ".cartero-state.json"
DEFAULT_INTERVAL = 600  # 10 minutes

GMAIL_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"


# ── Config ──────────────────────────────────────────────────────────────────

def _load_cartero_config() -> dict:
    """Load cartero section from orbit.json. Returns {} if absent."""
    cfg_path = ORBIT_HOME / "orbit.json"
    if not cfg_path.exists():
        return {}
    try:
        return json.loads(cfg_path.read_text()).get("cartero", {})
    except (json.JSONDecodeError, KeyError):
        return {}


def _gmail_config() -> Optional[dict]:
    """Return gmail sub-config or None if not configured."""
    cfg = _load_cartero_config()
    gmail = cfg.get("gmail")
    if not gmail or not gmail.get("labels"):
        return None
    return gmail


def _slack_config() -> Optional[list]:
    """Return slack sub-config as a list of workspace configs, or None.

    Supports both single dict and list of dicts:
      "slack": {"workspace": "next", "channels": [...]}
      "slack": [{"workspace": "next", ...}, {"workspace": "water", ...}]
    """
    cfg = _load_cartero_config()
    slack = cfg.get("slack")
    if not slack:
        return None
    # Normalize to list
    if isinstance(slack, dict):
        slack = [slack]
    # Filter out entries without channels and without dms
    valid = [s for s in slack if s.get("channels") or s.get("dms")]
    return valid if valid else None


def _has_any_source() -> bool:
    """Return True if any cartero source is configured."""
    return _gmail_config() is not None or _slack_config() is not None


# ── Gmail API ───────────────────────────────────────────────────────────────

def _get_gmail_service():
    """Build Gmail API service reusing workspace OAuth credentials.

    Adds gmail.readonly scope if needed.  Returns service or None.
    """
    from core.calendar_sync import CREDENTIALS_PATH, TOKEN_PATH, SCOPES as BASE_SCOPES

    all_scopes = list(BASE_SCOPES)
    if GMAIL_SCOPE not in all_scopes:
        all_scopes.append(GMAIL_SCOPE)

    try:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError:
        print("Error: instala las dependencias:")
        print("  pip install google-api-python-client google-auth-oauthlib")
        return None

    creds = None
    if TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), all_scopes)

    if not creds or not creds.valid:
        refreshed = False
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                refreshed = True
            except Exception:
                creds = None
        if not refreshed:
            if not CREDENTIALS_PATH.exists():
                print(f"Error: no se encontró credentials.json en {CREDENTIALS_PATH.parent}")
                return None
            import subprocess
            import webbrowser as _wb
            _orig_open = _wb.open
            def _open_mac(url, new=0, autoraise=True):
                print(f"\nAbre esta URL en tu navegador:\n  {url}\n")
                subprocess.run(["open", url])
                return True
            _wb.open = _open_mac
            flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_PATH), all_scopes)
            creds = flow.run_local_server(host="127.0.0.1", port=8080)
            _wb.open = _orig_open
        TOKEN_PATH.write_text(creds.to_json())

    from googleapiclient.discovery import build
    return build("gmail", "v1", credentials=creds)


def _resolve_label_ids(service, label_names: list) -> dict:
    """Map human label names → Gmail label IDs.

    Returns {name: label_id}.  Case-insensitive match.
    """
    results = service.users().labels().list(userId="me").execute()
    all_labels = {lab["name"].lower(): lab["id"] for lab in results.get("labels", [])}
    resolved = {}
    for name in label_names:
        lid = all_labels.get(name.lower())
        if lid:
            resolved[name] = lid
        else:
            print(f"⚠️  Etiqueta '{name}' no encontrada en Gmail")
    return resolved


def _check_gmail(service, label_ids: dict) -> dict:
    """Count unread messages per label.

    Uses labels.get() which returns exact messagesUnread count
    (unlike messages.list resultSizeEstimate which is approximate).

    Returns {"counts": {name: N}, "total": N, "timestamp": ISO}.
    """
    counts = {}
    for name, lid in label_ids.items():
        try:
            resp = service.users().labels().get(
                userId="me", id=lid
            ).execute()
            counts[name] = resp.get("messagesUnread", 0)
        except Exception:
            counts[name] = 0
    return {
        "counts": counts,
        "total": sum(counts.values()),
        "timestamp": datetime.now().isoformat(timespec="seconds"),
    }


# ── Slack API ──────────────────────────────────────────────────────────────

def _slack_token_path(workspace: Optional[str] = None) -> Path:
    """Return path to slack token file for a workspace."""
    if workspace:
        return ORBIT_HOME / f".slack-token-{workspace}"
    return ORBIT_HOME / ".slack-token"


def _get_slack_token(workspace: Optional[str] = None) -> Optional[str]:
    """Read Slack user token from .slack-token[-workspace] file."""
    path = _slack_token_path(workspace)
    if not path.exists():
        return None
    token = path.read_text().strip()
    return token if token else None


def _slack_api(method: str, token: str, params: Optional[dict] = None) -> dict:
    """Call a Slack Web API method. Returns parsed JSON response."""
    import urllib.request
    import urllib.parse

    url = f"https://slack.com/api/{method}"
    if params:
        url += "?" + urllib.parse.urlencode(params)

    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {token}",
    })
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode())


def _resolve_slack_channels(token: str, channel_names: list) -> dict:
    """Map channel names → IDs.

    Returns {name: channel_id}.  Case-insensitive match.
    Uses users.conversations to list channels the user is in.
    """
    resolved = {}
    names_lower = {n.lower(): n for n in channel_names}
    cursor = None

    while True:
        params = {"types": "public_channel,private_channel", "limit": "200"}
        if cursor:
            params["cursor"] = cursor
        resp = _slack_api("users.conversations", token, params)
        if not resp.get("ok"):
            print(f"⚠️  Slack API error: {resp.get('error', 'unknown')}")
            break
        for ch in resp.get("channels", []):
            ch_name = ch.get("name", "").lower()
            if ch_name in names_lower:
                resolved[names_lower[ch_name]] = ch["id"]
        # Pagination
        cursor = resp.get("response_metadata", {}).get("next_cursor")
        if not cursor:
            break

    for name in channel_names:
        if name not in resolved:
            print(f"⚠️  Canal '{name}' no encontrado en Slack")
    return resolved


def _check_slack(token: str, channel_ids: dict) -> dict:
    """Count unread messages per channel.

    Uses conversations.info which returns unread_count_display for user tokens.
    Returns {"counts": {name: N}, "total": N, "timestamp": ISO}.
    """
    counts = {}
    for name, cid in channel_ids.items():
        try:
            resp = _slack_api("conversations.info", token, {"channel": cid})
            if resp.get("ok"):
                counts[name] = resp["channel"].get("unread_count_display", 0)
            else:
                counts[name] = 0
        except Exception:
            counts[name] = 0
    return {
        "counts": counts,
        "total": sum(counts.values()),
        "timestamp": datetime.now().isoformat(timespec="seconds"),
    }


def _check_slack_dms(token: str) -> int:
    """Count total unread DMs (im + mpim).

    Uses conversations.list to get DM channel IDs, then conversations.info
    for each to get unread_count_display (not returned by list endpoint).
    Returns total unread count across all direct message conversations.
    """
    dm_ids = []
    for conv_type in ("im", "mpim"):
        cursor = None
        while True:
            params = {"types": conv_type, "limit": "200", "exclude_archived": "true"}
            if cursor:
                params["cursor"] = cursor
            try:
                resp = _slack_api("conversations.list", token, params)
                if not resp.get("ok"):
                    break
                for ch in resp.get("channels", []):
                    dm_ids.append(ch["id"])
                cursor = resp.get("response_metadata", {}).get("next_cursor")
                if not cursor:
                    break
            except Exception:
                break

    total = 0
    for cid in dm_ids:
        try:
            resp = _slack_api("conversations.info", token, {"channel": cid})
            if resp.get("ok"):
                total += resp["channel"].get("unread_count_display", 0)
        except Exception:
            pass
    return total


def _check_slack_workspace(token: str, channel_ids: dict, include_dms: bool) -> dict:
    """Check a single Slack workspace: channels + optional DMs.

    Returns {"counts": {name: N, "DMs": N}, "total": N, "timestamp": ISO}.
    """
    result = _check_slack(token, channel_ids)
    if include_dms:
        dm_count = _check_slack_dms(token)
        if dm_count > 0:
            result["counts"]["DMs"] = dm_count
            result["total"] += dm_count
    return result


# ── Shared state ────────────────────────────────────────────────────────────

def _read_state() -> dict:
    """Read .cartero-state.json. Returns {} if missing."""
    if CARTERO_STATE.exists():
        try:
            return json.loads(CARTERO_STATE.read_text())
        except (json.JSONDecodeError, ValueError):
            return {}
    return {}


def _write_state(state: dict):
    """Write state atomically (tmp + rename)."""
    tmp = CARTERO_STATE.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n")
    tmp.rename(CARTERO_STATE)


def _read_federated_states() -> list:
    """Read .cartero-state.json from federated workspaces.

    Returns [(emoji, state_dict), ...] for each federated workspace that has state.
    """
    results = []
    for space in _FEDERATED_SPACES:
        space_path = Path(space["path"]).expanduser().resolve()
        state_file = space_path / ".cartero-state.json"
        if state_file.exists():
            try:
                state = json.loads(state_file.read_text())
                emoji = space.get("emoji", "")
                results.append((emoji, state))
            except (json.JSONDecodeError, ValueError):
                pass
    return results


def _federated_total() -> tuple:
    """Return (total, indicator_parts) from federated workspaces.

    indicator_parts: list of "🌿📬3" strings for the prompt.
    """
    parts = []
    total = 0
    for emoji, state in _read_federated_states():
        fed_total = 0
        for source in ("gmail", "slack"):
            fed_total += state.get(source, {}).get("total", 0)
        if fed_total > 0:
            parts.append(f"{emoji}📬{fed_total}")
            total += fed_total
    return total, parts


def get_prompt_indicator() -> str:
    """Return prompt indicator string, e.g. '[📬4]' or '[📬4 🌿📬3]'.

    Combines local sources (gmail + slack) + federated workspaces.
    Reads local files only — no network I/O.
    """
    state = _read_state()
    local_total = (state.get("gmail", {}).get("total", 0)
                   + state.get("slack", {}).get("total", 0))
    fed_total, fed_parts = _federated_total()

    if local_total == 0 and fed_total == 0:
        return ""

    parts = []
    if local_total > 0:
        parts.append(f"📬{local_total}")
    parts.extend(fed_parts)
    return "[" + " ".join(parts) + "]"


# ── macOS notifications ─────────────────────────────────────────────────────

def _notify_macos(title: str, body: str):
    """Send a macOS notification via osascript."""
    import subprocess
    # Escape double quotes for AppleScript
    t = title.replace('"', '\\"')
    b = body.replace('"', '\\"')
    script = f'display notification "{b}" with title "{t}"'
    subprocess.run(["osascript", "-e", script],
                   capture_output=True, timeout=5)


# ── Background process management ──────────────────────────────────────────

def _is_running() -> bool:
    """Check if a cartero background process is alive."""
    if not CARTERO_PID.exists():
        return False
    try:
        pid = int(CARTERO_PID.read_text().strip())
        os.kill(pid, 0)  # signal 0 = check existence
        return True
    except (ValueError, ProcessLookupError, PermissionError):
        # Stale PID file — clean up
        try:
            CARTERO_PID.unlink()
        except FileNotFoundError:
            pass
        return False


def _stop_background() -> bool:
    """Stop the background process. Returns True if stopped."""
    if not CARTERO_PID.exists():
        return False
    try:
        pid = int(CARTERO_PID.read_text().strip())
        os.kill(pid, signal.SIGTERM)
        # Wait briefly for process to exit
        for _ in range(10):
            try:
                os.kill(pid, 0)
                time.sleep(0.1)
            except ProcessLookupError:
                break
        try:
            CARTERO_PID.unlink()
        except FileNotFoundError:
            pass
        return True
    except (ValueError, ProcessLookupError, PermissionError):
        try:
            CARTERO_PID.unlink()
        except FileNotFoundError:
            pass
        return False


def _background_loop(config: dict):
    """Main loop for the background daemon process.

    Called after double-fork.  Runs until SIGTERM.
    Polls all configured sources (Gmail, Slack).
    """
    interval = config.get("interval", DEFAULT_INTERVAL)
    gmail_cfg = config.get("gmail")
    slack_cfgs = _slack_config()  # list of workspace configs or None

    # Handle SIGTERM gracefully
    running = True
    def _handle_term(signum, frame):
        nonlocal running
        running = False
    signal.signal(signal.SIGTERM, _handle_term)

    # Write PID
    CARTERO_PID.write_text(str(os.getpid()))

    # Gmail state (lazy init)
    gmail_service = None
    gmail_label_ids = None

    # Slack state (lazy init, per workspace)
    slack_tokens = {}       # {ws_name: token}
    slack_channel_ids = {}  # {ws_name: {name: id}}

    while running:
        try:
            prev_state = _read_state()
            state = prev_state.copy()
            state["pid"] = os.getpid()
            state["workspace"] = str(ORBIT_HOME.name)
            notify_parts = []

            # ── Gmail ───────────────────────────────────────────
            if gmail_cfg and gmail_cfg.get("labels"):
                if gmail_service is None:
                    gmail_service = _get_gmail_service()
                if gmail_service and gmail_label_ids is None:
                    gmail_label_ids = _resolve_label_ids(
                        gmail_service, gmail_cfg.get("labels", []))
                if gmail_service and gmail_label_ids:
                    result = _check_gmail(gmail_service, gmail_label_ids)
                    prev_total = prev_state.get("gmail", {}).get("total", 0)
                    delta = result["total"] - prev_total
                    state["gmail"] = result
                    if delta > 0:
                        parts = [f"{n} ({c})" for n, c in result["counts"].items() if c > 0]
                        notify_parts.append(
                            f"{delta} correo{'s' if delta != 1 else ''}: {', '.join(parts)}")

            # ── Slack (multiple workspaces) ─────────────────────
            if slack_cfgs:
                combined_counts = {}
                combined_total = 0
                for i, scfg in enumerate(slack_cfgs):
                    ws_name = scfg.get("workspace", f"slack{i}")
                    if ws_name not in slack_tokens:
                        slack_tokens[ws_name] = _get_slack_token(ws_name)
                    token = slack_tokens.get(ws_name)
                    if not token:
                        continue
                    if ws_name not in slack_channel_ids:
                        channels = scfg.get("channels", [])
                        slack_channel_ids[ws_name] = _resolve_slack_channels(
                            token, channels) if channels else {}
                    ch_ids = slack_channel_ids.get(ws_name, {})
                    include_dms = scfg.get("dms", False)
                    if ch_ids or include_dms:
                        result = _check_slack_workspace(token, ch_ids, include_dms)
                        for name, count in result["counts"].items():
                            combined_counts[f"{ws_name}:{name}"] = count
                        combined_total += result["total"]

                slack_result = {
                    "counts": combined_counts,
                    "total": combined_total,
                    "timestamp": datetime.now().isoformat(timespec="seconds"),
                }
                prev_total = prev_state.get("slack", {}).get("total", 0)
                delta = combined_total - prev_total
                state["slack"] = slack_result
                if delta > 0:
                    parts = [f"#{n} ({c})" for n, c in combined_counts.items() if c > 0]
                    notify_parts.append(
                        f"{delta} mensaje{'s' if delta != 1 else ''} Slack: {', '.join(parts)}")

            _write_state(state)

            # Notify if any source has new messages
            if notify_parts:
                _notify_macos("📬 Mensajes nuevos", " · ".join(notify_parts))

        except Exception:
            pass  # Fail silently, retry next cycle

        # Sleep in small chunks so SIGTERM is responsive
        for _ in range(interval):
            if not running:
                break
            time.sleep(1)

    # Cleanup
    try:
        CARTERO_PID.unlink()
    except FileNotFoundError:
        pass


def _start_background(config: dict):
    """Launch background daemon via double-fork."""
    pid = os.fork()
    if pid > 0:
        # Parent returns immediately
        return

    # First child: create new session
    os.setsid()

    pid2 = os.fork()
    if pid2 > 0:
        # First child exits
        os._exit(0)

    # Second child: the actual daemon
    # Redirect stdin/stdout/stderr to /dev/null
    devnull = os.open(os.devnull, os.O_RDWR)
    os.dup2(devnull, 0)
    os.dup2(devnull, 1)
    os.dup2(devnull, 2)
    os.close(devnull)

    try:
        _background_loop(config)
    finally:
        os._exit(0)


# ── Startup integration ────────────────────────────────────────────────────

def startup_cartero():
    """Called from shell.py during startup.

    Launches background process if configured and not already running.
    Shows current mail/message status including federated workspaces.
    """
    config = _load_cartero_config()
    has_federated = bool(_read_federated_states())

    if not config and not has_federated:
        return
    if not _has_any_source() and not has_federated:
        return

    if _has_any_source() and not _is_running():
        _start_background(config)
        time.sleep(1)

    # Local sources
    state = _read_state()
    parts = []
    for source in ("gmail", "slack"):
        src = state.get(source, {})
        for name, count in src.get("counts", {}).items():
            if count > 0:
                prefix = "#" if source == "slack" else ""
                parts.append(f"{prefix}{name} ({count})")

    # Federated sources
    for emoji, fed_state in _read_federated_states():
        for source in ("gmail", "slack"):
            src = fed_state.get(source, {})
            for name, count in src.get("counts", {}).items():
                if count > 0:
                    prefix = "#" if source == "slack" else ""
                    parts.append(f"{emoji}{prefix}{name} ({count})")

    if parts:
        print(f"  📬 Cartero activo ({', '.join(parts)})")
    else:
        print(f"  📬 Cartero activo (sin mensajes)")


# ── CLI command: orbit mail ─────────────────────────────────────────────────

def run_mail(status: bool = False, stop: bool = False, start: bool = False) -> int:
    """Handle `orbit mail` command."""
    config = _load_cartero_config()

    if stop:
        if _stop_background():
            print("📬 Cartero detenido.")
        else:
            print("📬 Cartero no estaba corriendo.")
        return 0

    if start:
        if not config or not _has_any_source():
            print("⚠️  No hay configuración de cartero en orbit.json")
            return 1
        if _is_running():
            print("📬 Cartero ya está corriendo.")
        else:
            _start_background(config)
            print("📬 Cartero arrancado.")
        return 0

    if status:
        if _is_running():
            state = _read_state()
            print(f"📬 Cartero corriendo (PID {state.get('pid', '?')})")
            for source in ("gmail", "slack"):
                src = state.get(source, {})
                if not src:
                    continue
                label = "Gmail" if source == "gmail" else "Slack"
                ts = src.get("timestamp", "?")
                print(f"   {label} (último check: {ts}):")
                total = src.get("total", 0)
                if total > 0:
                    for name, count in src.get("counts", {}).items():
                        prefix = "#" if source == "slack" else " "
                        print(f"     {prefix}{name:20s} {count}")
                else:
                    print(f"     Sin mensajes no leídos.")
        else:
            print("📬 Cartero no está corriendo.")
        return 0

    # Default: synchronous check
    if not _has_any_source():
        print("⚠️  No hay configuración de cartero en orbit.json")
        print()
        print("Añade a orbit.json:")
        print('  "cartero": {')
        print('    "gmail": { "labels": ["Etiqueta"], "interval": 600 },')
        print('    "slack": { "channels": ["general"], "interval": 600 }')
        print('  }')
        return 1

    state = _read_state()
    has_results = False

    # Gmail check
    gmail_cfg = _gmail_config()
    if gmail_cfg:
        print("📬 Consultando Gmail...")
        service = _get_gmail_service()
        if service:
            label_ids = _resolve_label_ids(service, gmail_cfg.get("labels", []))
            if label_ids:
                result = _check_gmail(service, label_ids)
                state["gmail"] = result
                has_results = True
                print()
                print("📬 Gmail — correos no leídos:")
                max_len = max(len(n) for n in result["counts"]) if result["counts"] else 0
                for name, count in result["counts"].items():
                    print(f"  {name:{max_len}s}  {count:3d}")
                print(f"  {'─' * (max_len + 5)}")
                print(f"  {'Total':{max_len}s}  {result['total']:3d}")
                print()

    # Slack check (multiple workspaces)
    slack_cfgs = _slack_config()
    if slack_cfgs:
        combined_counts = {}
        combined_total = 0
        for scfg in slack_cfgs:
            ws_name = scfg.get("workspace", "slack")
            token = _get_slack_token(ws_name)
            if not token:
                print(f"⚠️  No se encontró token para Slack '{ws_name}'")
                print(f"   Crea {_slack_token_path(ws_name)} con tu user token (xoxp-...)")
                continue
            print(f"📬 Consultando Slack ({ws_name})...")
            channels = scfg.get("channels", [])
            channel_ids = _resolve_slack_channels(token, channels) if channels else {}
            include_dms = scfg.get("dms", False)
            if channel_ids or include_dms:
                result = _check_slack_workspace(token, channel_ids, include_dms)
                for name, count in result["counts"].items():
                    combined_counts[f"{ws_name}:{name}"] = count
                combined_total += result["total"]
        if combined_counts:
            slack_result = {
                "counts": combined_counts,
                "total": combined_total,
                "timestamp": datetime.now().isoformat(timespec="seconds"),
            }
            state["slack"] = slack_result
            has_results = True
            print()
            print("📬 Slack — mensajes no leídos:")
            max_len = max(len(n) for n in combined_counts) if combined_counts else 0
            for name, count in combined_counts.items():
                print(f"  #{name:{max_len}s}  {count:3d}")
            print(f"  {'─' * (max_len + 6)}")
            print(f"  {'Total':{max_len + 1}s}  {combined_total:3d}")
            print()

    if has_results:
        _write_state(state)

    # Federated workspaces (read-only, no polling)
    fed_states = _read_federated_states()
    for emoji, fed_state in fed_states:
        fed_parts = []
        for source in ("gmail", "slack"):
            src = fed_state.get(source, {})
            if not src or not src.get("counts"):
                continue
            label = "Gmail" if source == "gmail" else "Slack"
            print(f"📬 {emoji} {label} (federado) — mensajes no leídos:")
            max_len = max(len(n) for n in src["counts"]) if src["counts"] else 0
            prefix = "#" if source == "slack" else ""
            src_total = 0
            for name, count in src["counts"].items():
                print(f"  {prefix}{name:{max_len}s}  {count:3d}")
                src_total += count
            print(f"  {'─' * (max_len + 6)}")
            print(f"  {'Total':{max_len + 1}s}  {src_total:3d}")
            print()

    return 0

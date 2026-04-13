"""cartero — background mail notifier for Orbit.

Polls Gmail (Phase 1) for unread messages in configured labels and:
  - Updates a shared state file (ORBIT_HOME/.cartero-state.json)
  - Shows a prompt indicator [📬N] in the Orbit shell
  - Sends macOS notifications when new mail arrives

Configuration in orbit.json:
  "cartero": {
    "gmail": {
      "labels": ["Importante", "Familia"],
      "interval": 600
    }
  }
"""

import json
import os
import signal
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from core.config import ORBIT_HOME

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


def get_prompt_indicator() -> str:
    """Return prompt indicator string, e.g. '[📬4]' or '' if no mail.

    Reads local file only — no network I/O.
    """
    state = _read_state()
    gmail = state.get("gmail", {})
    total = gmail.get("total", 0)
    if total > 0:
        return f"[📬{total}]"
    return ""


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
    """
    interval = config.get("interval", DEFAULT_INTERVAL)
    gmail_cfg = config.get("gmail")

    # Handle SIGTERM gracefully
    running = True
    def _handle_term(signum, frame):
        nonlocal running
        running = False
    signal.signal(signal.SIGTERM, _handle_term)

    # Write PID
    CARTERO_PID.write_text(str(os.getpid()))

    service = None
    label_ids = None

    while running:
        try:
            # Build service lazily / rebuild if needed
            if service is None:
                service = _get_gmail_service()
                if service is None:
                    time.sleep(interval)
                    continue

            # Resolve labels once (or if config changed)
            if label_ids is None and gmail_cfg:
                label_ids = _resolve_label_ids(service, gmail_cfg.get("labels", []))
                if not label_ids:
                    time.sleep(interval)
                    continue

            # Check Gmail
            if label_ids:
                result = _check_gmail(service, label_ids)
                prev_state = _read_state()
                prev_total = prev_state.get("gmail", {}).get("total", 0)
                new_total = result["total"]

                state = prev_state.copy()
                state["gmail"] = result
                state["pid"] = os.getpid()
                state["workspace"] = str(ORBIT_HOME.name)
                _write_state(state)

                # Notify only on increase (new mail arrived)
                delta = new_total - prev_total
                if delta > 0 and prev_total >= 0:
                    # Build detail: "Importante (3), Familia (1)"
                    parts = [f"{n} ({c})" for n, c in result["counts"].items() if c > 0]
                    body = ", ".join(parts) if parts else ""
                    _notify_macos(
                        f"📬 {delta} correo{'s' if delta != 1 else ''} nuevo{'s' if delta != 1 else ''}",
                        body,
                    )

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
    Shows current mail status.
    """
    config = _load_cartero_config()
    if not config or not _gmail_config():
        return

    if not _is_running():
        _start_background(config)
        # Give it a moment for first check
        time.sleep(1)

    state = _read_state()
    gmail = state.get("gmail", {})
    total = gmail.get("total", 0)
    if total > 0:
        parts = [f"{n} ({c})" for n, c in gmail.get("counts", {}).items() if c > 0]
        detail = ", ".join(parts)
        print(f"  📬 Cartero activo ({detail})")
    else:
        print(f"  📬 Cartero activo (sin correos)")


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
        if not config or not _gmail_config():
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
            gmail = state.get("gmail", {})
            ts = gmail.get("timestamp", "?")
            print(f"📬 Cartero corriendo (PID {state.get('pid', '?')})")
            print(f"   Último check: {ts}")
            total = gmail.get("total", 0)
            if total > 0:
                for name, count in gmail.get("counts", {}).items():
                    print(f"   {name:20s} {count}")
            else:
                print("   Sin correos no leídos.")
        else:
            print("📬 Cartero no está corriendo.")
        return 0

    # Default: synchronous check
    gmail_cfg = _gmail_config()
    if not gmail_cfg:
        print("⚠️  No hay configuración de cartero en orbit.json")
        print()
        print("Añade a orbit.json:")
        print('  "cartero": {')
        print('    "gmail": {')
        print('      "labels": ["Importante", "Familia"],')
        print('      "interval": 600')
        print('    }')
        print('  }')
        return 1

    print("📬 Consultando Gmail...")
    service = _get_gmail_service()
    if not service:
        return 1

    label_ids = _resolve_label_ids(service, gmail_cfg.get("labels", []))
    if not label_ids:
        print("⚠️  No se encontraron etiquetas configuradas en Gmail.")
        return 1

    result = _check_gmail(service, label_ids)

    # Update state
    state = _read_state()
    state["gmail"] = result
    _write_state(state)

    # Display
    print()
    print("📬 Correos no leídos:")
    max_len = max(len(n) for n in result["counts"]) if result["counts"] else 0
    for name, count in result["counts"].items():
        print(f"  {name:{max_len}s}  {count:3d}")
    print(f"  {'─' * (max_len + 5)}")
    print(f"  {'Total':{max_len}s}  {result['total']:3d}")
    print()

    return 0

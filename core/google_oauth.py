"""google_oauth.py — shared Google OAuth credentials for orbit.

Provides the workspace-level OAuth flow (Installed App) used by
modules that talk to Google APIs. Today only ``cartero`` consumes the
constants (it builds its own service with extended scopes); the
``_get_credentials`` / ``_build_service`` helpers are kept here as the
canonical OAuth surface so future callers (or a cartero refactor) can
reuse it instead of duplicating the flow.

Extracted from the now-deleted ``core/calendar_sync.py`` (pull
Google→orbit), which had grown around the same OAuth boilerplate.
"""
from core.config import ORBIT_HOME

CREDENTIALS_PATH = ORBIT_HOME / "credentials.json"
TOKEN_PATH = ORBIT_HOME / "token.json"
SCOPES = [
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/tasks",
]


def _get_credentials():
    """Authenticate and return Google API credentials."""
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
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)

    if not creds or not creds.valid:
        refreshed = False
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                refreshed = True
            except Exception:
                print("⚠️  Token expirado/revocado — re-autenticando...")
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
            flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_PATH), SCOPES)
            creds = flow.run_local_server(host="127.0.0.1", port=8080)
            _wb.open = _orig_open
        TOKEN_PATH.write_text(creds.to_json())

    return creds


def _build_service(service_name: str, version: str):
    """Build a Google API service (calendar v3, tasks v1, etc.)."""
    creds = _get_credentials()
    if not creds:
        return None
    from googleapiclient.discovery import build
    return build(service_name, version, credentials=creds)

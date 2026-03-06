"""orbit calendar — sync Google Calendar events to project logbooks."""

import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from core.log import PROJECTS_DIR, find_project, find_logbook_file, init_logbook

CREDENTIALS_PATH = Path(__file__).parent.parent / "credentials.json"
TOKEN_PATH = Path(__file__).parent.parent / "token.json"
SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]

PROJECT_RE = re.compile(r"proyecto\s*:\s*(\S+)", re.IGNORECASE)


def _get_service():
    """Authenticate and return the Google Calendar API service."""
    try:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
    except ImportError:
        print("Error: instala las dependencias:")
        print("  pip install google-api-python-client google-auth-oauthlib")
        return None

    creds = None
    if TOKEN_PATH.exists():
        from google.oauth2.credentials import Credentials
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            from google.auth.transport.requests import Request
            creds.refresh(Request())
        else:
            if not CREDENTIALS_PATH.exists():
                print(f"Error: no se encontró credentials.json en {CREDENTIALS_PATH.parent}")
                return None
            from google_auth_oauthlib.flow import InstalledAppFlow
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

    from googleapiclient.discovery import build
    return build("calendar", "v3", credentials=creds)


def _day_bounds(target: date) -> tuple:
    """Return ISO 8601 bounds for a full calendar day in local timezone."""
    local_tz = datetime.now().astimezone().tzinfo
    start = datetime(target.year, target.month, target.day, tzinfo=local_tz)
    end = start + timedelta(days=1)
    return start.isoformat(), end.isoformat()


def _parse_project(description: str) -> Optional[str]:
    """Extract project name from 'proyecto: <name>' in event description."""
    if not description:
        return None
    m = PROJECT_RE.search(description)
    return m.group(1).strip() if m else None


def _entry_exists(logbook_path: Path, title: str, date_str: str) -> bool:
    """Return True if an #evento entry for this event already exists."""
    if not logbook_path or not logbook_path.exists():
        return False
    return f"{date_str} {title} #evento" in logbook_path.read_text()


def run_calendar_sync(date_str: Optional[str], dry_run: bool) -> int:
    target = date.fromisoformat(date_str) if date_str else date.today()

    service = _get_service()
    if not service:
        return 1

    time_min, time_max = _day_bounds(target)
    print(f"Sincronizando eventos — {target.isoformat()}{'  [dry-run]' if dry_run else ''}")
    print("─" * 50)

    calendars = service.calendarList().list().execute().get("items", [])
    synced = skipped = not_found = 0

    for cal in calendars:
        events = service.events().list(
            calendarId=cal["id"],
            timeMin=time_min,
            timeMax=time_max,
            singleEvents=True,
            orderBy="startTime",
        ).execute().get("items", [])

        for event in events:
            title = event.get("summary", "(sin título)")
            description = event.get("description", "") or ""
            project_name = _parse_project(description)
            if not project_name:
                continue

            project_dir = find_project(project_name)
            if not project_dir:
                print(f"  ⚠️  '{project_name}' no encontrado  ←  {title}")
                not_found += 1
                continue

            logbook_path = find_logbook_file(project_dir)
            if not logbook_path:
                logbook_path = project_dir / "logbook.md"

            if _entry_exists(logbook_path, title, target.isoformat()):
                skipped += 1
                continue

            entry = f"{target.isoformat()} {title} #evento\n"
            if dry_run:
                print(f"  ~  [{project_dir.name}] {entry.strip()}")
            else:
                if not logbook_path.exists():
                    init_logbook(logbook_path, project_dir.name)
                with open(logbook_path, "a") as f:
                    f.write(entry)
                print(f"  ✓  [{project_dir.name}] {entry.strip()}")
            synced += 1

    print("─" * 50)
    parts = [f"Nuevos: {synced}"]
    if skipped:
        parts.append(f"Ya existían: {skipped}")
    if not_found:
        parts.append(f"Proyecto no encontrado: {not_found}")
    print("  ".join(parts))
    return 0

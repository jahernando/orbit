"""orbit calendar — sync Google Calendar events to project logbooks."""

import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from core.log import PROJECTS_DIR, find_project, find_logbook_file, init_logbook, resolve_file

from core.config import ORBIT_HOME
CREDENTIALS_PATH = ORBIT_HOME / "credentials.json"
TOKEN_PATH = ORBIT_HOME / "token.json"
SCOPES = [
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/tasks",
]

PROJECT_RE = re.compile(r"proyecto\s*:\s*(\S+)", re.IGNORECASE)


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


def _get_service():
    """Return the Google Calendar API service."""
    return _build_service("calendar", "v3")


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


def fetch_day_events(target: date) -> Optional[list]:
    """Return list of event dicts for the day, or None if calendar unavailable.

    Each dict: {title, description, project_name, start_time}
    start_time is "HH:MM" or "todo el día".
    Returns None silently if credentials.json is missing.
    """
    if not CREDENTIALS_PATH.exists():
        return None

    service = _get_service()
    if not service:
        return None

    time_min, time_max = _day_bounds(target)
    calendars = service.calendarList().list().execute().get("items", [])
    events = []
    for cal in calendars:
        items = service.events().list(
            calendarId=cal["id"],
            timeMin=time_min,
            timeMax=time_max,
            singleEvents=True,
            orderBy="startTime",
        ).execute().get("items", [])
        for event in items:
            start = event.get("start", {})
            start_dt = start.get("dateTime", start.get("date", ""))
            start_time = start_dt[11:16] if "T" in start_dt else "todo el día"
            events.append({
                "title": event.get("summary", "(sin título)"),
                "description": event.get("description", "") or "",
                "project_name": _parse_project(event.get("description", "") or ""),
                "start_time": start_time,
            })
    return events


def _event_in_agenda(project_dir: Path, title: str, date_str: str) -> bool:
    """Return True if an event with this date+title already exists in agenda.md."""
    from core.agenda_cmds import _read_agenda
    data = _read_agenda(resolve_file(project_dir, "agenda"))
    return any(e["date"] == date_str and e["desc"] == title
               for e in data["events"])


def _sync_new_format(project_dir: Path, title: str, date_str: str,
                     dry_run: bool) -> bool:
    """Add event to agenda.md + orbit logbook entry for a new-format project.

    Returns True if a new event was added (False if already present).
    """
    if _event_in_agenda(project_dir, title, date_str):
        return False

    if not dry_run:
        from core.agenda_cmds import _read_agenda, _write_agenda
        data = _read_agenda(resolve_file(project_dir, "agenda"))
        data["events"].append({"date": date_str, "desc": title, "end": None})
        _write_agenda(resolve_file(project_dir, "agenda"), data)
        from core.log import add_orbit_entry
        add_orbit_entry(project_dir, f"[evento sincronizado] {title}", "apunte")
        print(f"  ✓  [{project_dir.name}] {date_str} — {title} [O]")
    else:
        print(f"  ~  [{project_dir.name}] {date_str} — {title} (agenda.md)")
    return True


def sync_events_to_logbooks(events: list, target: date, dry_run: bool) -> tuple:
    """Write events to project files. Returns (synced, skipped, not_found).

    New-format projects: event added to agenda.md + logbook [O] entry.
    Old-format projects: #evento entry appended to logbook.md (legacy).
    """
    from core.project import _is_new_project, _find_new_project

    synced = skipped = not_found = 0
    for event in events:
        project_name = event["project_name"]
        if not project_name:
            continue
        title      = event["title"]
        date_str   = target.isoformat()

        # Try new-format project first, then fall back to old-format
        project_dir = _find_new_project(project_name) if project_name else None
        if project_dir is None:
            project_dir = find_project(project_name)
        if not project_dir:
            print(f"  ⚠️  '{project_name}' no encontrado  ←  {title}")
            not_found += 1
            continue

        if _is_new_project(project_dir):
            added = _sync_new_format(project_dir, title, date_str, dry_run)
            if added:
                synced += 1
            else:
                skipped += 1
            continue

        # ── legacy: old-format project ──────────────────────────────────────
        logbook_path = find_logbook_file(project_dir)
        if not logbook_path:
            logbook_path = resolve_file(project_dir, "logbook")

        if _entry_exists(logbook_path, title, date_str):
            skipped += 1
            continue

        entry = f"{date_str} {title} #evento\n"
        if dry_run:
            print(f"  ~  [{project_dir.name}] {entry.strip()}")
        else:
            if not logbook_path.exists():
                from core.log import init_logbook
                init_logbook(logbook_path, project_dir.name)
            from core.log import _append_entry
            _append_entry(logbook_path, entry)
            print(f"  ✓  [{project_dir.name}] {entry.strip()}")
        synced += 1
    return synced, skipped, not_found


def run_calendar_sync(date_str: Optional[str], dry_run: bool) -> int:
    target = date.fromisoformat(date_str) if date_str else date.today()

    events = fetch_day_events(target)
    if events is None:
        if not CREDENTIALS_PATH.exists():
            print(f"Error: no se encontró credentials.json en {CREDENTIALS_PATH.parent}")
        return 1

    print(f"Sincronizando eventos — {target.isoformat()}{'  [dry-run]' if dry_run else ''}")
    print("─" * 50)

    synced, skipped, not_found = sync_events_to_logbooks(events, target, dry_run)

    print("─" * 50)
    parts = [f"Nuevos: {synced}"]
    if skipped:
        parts.append(f"Ya existían: {skipped}")
    if not_found:
        parts.append(f"Proyecto no encontrado: {not_found}")
    print("  ".join(parts))
    return 0

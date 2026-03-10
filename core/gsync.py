"""gsync — push Orbit tasks, milestones and events to Google Tasks/Calendar.

  orbit gsync                    # push pending items to Google
  orbit gsync --dry-run          # preview without writing
  orbit gsync --list-calendars   # show available Google Calendars with IDs

Architecture:
  - Tasks + Milestones → Google Tasks API (one TaskList per project type)
  - Events → Google Calendar Events API (one calendar per project type)
  - Orbit is the source of truth (one-directional sync)
  - Sync IDs stored in agenda.md: [gtask:id] and [gcal:id]

Config file: google-sync.json in ORBIT_HOME
"""

import json
from datetime import date
from pathlib import Path
from typing import Optional

from core.config import ORBIT_HOME, normalize as _normalize
from core.log import PROJECTS_DIR, resolve_file
from core.project import _find_new_project, _is_new_project, _read_project_meta
from core.agenda_cmds import _read_agenda, _write_agenda

CONFIG_PATH = ORBIT_HOME / "google-sync.json"


# ── Config ──────────────────────────────────────────────────────────────────

def _normalize_tipo(tipo_label: str) -> str:
    """Normalize project type label to a canonical key."""
    return _normalize(tipo_label)


def _load_config() -> dict:
    """Load google-sync.json config. Create default if missing."""
    if CONFIG_PATH.exists():
        return json.loads(CONFIG_PATH.read_text())
    # Generate default config
    config = {
        "calendars": {},
        "task_lists": {},
    }
    _save_config(config)
    return config


def _save_config(config: dict) -> None:
    """Save config back to google-sync.json."""
    CONFIG_PATH.write_text(json.dumps(config, indent=2, ensure_ascii=False) + "\n")


def _get_project_tipo(project_dir: Path) -> str:
    """Get normalized project type key."""
    meta = _read_project_meta(project_dir)
    return _normalize_tipo(meta.get("tipo_label", ""))


# ── Description / title helpers ──────────────────────────────────────────────

def _project_url(project_dir: Path, config: dict) -> Optional[str]:
    """Build GitHub URL for the project file, or None."""
    from urllib.parse import quote
    repo_url = config.get("repo_url")
    if not repo_url:
        return None
    from core.log import find_proyecto_file
    pfile = find_proyecto_file(project_dir)
    if not pfile:
        return None
    rel = pfile.relative_to(ORBIT_HOME)
    return f"{repo_url}/{quote(str(rel))}"


def _project_description(project_dir: Path, config: dict, html: bool = False) -> str:
    """Build description with project name and GitHub link.

    html=True: returns HTML link (for Google Calendar events).
    html=False: returns plain text (for Google Tasks notes).
    """
    project_name = project_dir.name
    url = _project_url(project_dir, config)

    if html and url:
        return f'<a href="{url}">{project_name}</a>'
    elif url:
        return f"Proyecto: {project_name}\n{url}"
    else:
        return f"Proyecto: {project_name}"


# ── Google API helpers ──────────────────────────────────────────────────────

def _get_tasks_service():
    from core.calendar_sync import _build_service
    return _build_service("tasks", "v1")


def _get_calendar_service():
    from core.calendar_sync import _build_service
    return _build_service("calendar", "v3")


# ── TaskList management ─────────────────────────────────────────────────────

def _ensure_task_list(service, tipo: str, config: dict) -> Optional[str]:
    """Get or create a Google TaskList for this project type. Returns list ID."""
    list_id = config.get("task_lists", {}).get(tipo)
    if list_id:
        return list_id

    # Search existing lists
    list_name = f"Orbit — {tipo.capitalize()}"
    try:
        results = service.tasklists().list(maxResults=100).execute()
    except Exception as e:
        if "accessNotConfigured" in str(e) or "tasks.googleapis.com" in str(e):
            print("⚠️  Google Tasks API no está habilitada en tu proyecto.")
            print("   Habilítala en: https://console.developers.google.com/apis/api/tasks.googleapis.com")
            return None
        raise
    for tl in results.get("items", []):
        if tl["title"] == list_name:
            config.setdefault("task_lists", {})[tipo] = tl["id"]
            _save_config(config)
            return tl["id"]

    # Create new list
    new_list = service.tasklists().insert(body={"title": list_name}).execute()
    config.setdefault("task_lists", {})[tipo] = new_list["id"]
    _save_config(config)
    print(f"  ✓ Creada TaskList: {list_name}")
    return new_list["id"]


# ── Task/Milestone sync ────────────────────────────────────────────────────

def _sync_one_task(service, tasklist_id: str, item: dict,
                   project_name: str, is_milestone: bool,
                   description: str, dry_run: bool) -> Optional[str]:
    """Sync a single task/milestone to Google Tasks. Returns Google Task ID."""
    prefix = "🏁 " if is_milestone else ""
    title = f"{project_name} — {prefix}{item['desc']}"
    notes = description

    # Build due date (Google Tasks uses RFC 3339)
    due = None
    if item.get("date"):
        due = f"{item['date']}T00:00:00.000Z"

    status_map = {"pending": "needsAction", "done": "completed", "cancelled": "completed"}
    g_status = status_map.get(item["status"], "needsAction")

    if item.get("gtask_id"):
        # Update existing
        if dry_run:
            print(f"  ~ actualizar: {title}")
            return item["gtask_id"]
        try:
            body = {"title": title, "notes": notes, "status": g_status}
            if due:
                body["due"] = due
            service.tasks().patch(
                tasklist=tasklist_id, task=item["gtask_id"], body=body
            ).execute()
            return item["gtask_id"]
        except Exception as e:
            print(f"  ⚠️  Error actualizando '{item['desc']}': {e}")
            return item["gtask_id"]
    else:
        # Create new
        if dry_run:
            print(f"  ~ crear: {title}")
            return None
        try:
            body = {"title": title, "notes": notes, "status": g_status}
            if due:
                body["due"] = due
            result = service.tasks().insert(
                tasklist=tasklist_id, body=body
            ).execute()
            return result["id"]
        except Exception as e:
            print(f"  ⚠️  Error creando '{item['desc']}': {e}")
            return None


def _sync_tasks_for_project(tasks_service, project_dir: Path,
                            config: dict, dry_run: bool) -> tuple:
    """Sync all tasks and milestones for a project. Returns (created, updated, skipped)."""
    tipo = _get_project_tipo(project_dir)
    if not tipo:
        return 0, 0, 0

    agenda_path = resolve_file(project_dir, "agenda")
    data = _read_agenda(agenda_path)
    project_name = project_dir.name
    description = _project_description(project_dir, config)

    tasklist_id = _ensure_task_list(tasks_service, tipo, config)
    if not tasklist_id:
        return 0, 0, 0

    created = updated = skipped = 0
    changed = False

    # Sync tasks
    for t in data["tasks"]:
        if t["status"] == "pending" or t.get("gtask_id"):
            new_id = _sync_one_task(tasks_service, tasklist_id, t,
                                    project_name, False, description, dry_run)
            if new_id and not t.get("gtask_id"):
                t["gtask_id"] = new_id
                created += 1
                changed = True
            elif t.get("gtask_id"):
                updated += 1
            else:
                skipped += 1

    # Sync milestones
    for m in data["milestones"]:
        if m["status"] == "pending" or m.get("gtask_id"):
            new_id = _sync_one_task(tasks_service, tasklist_id, m,
                                    project_name, True, description, dry_run)
            if new_id and not m.get("gtask_id"):
                m["gtask_id"] = new_id
                created += 1
                changed = True
            elif m.get("gtask_id"):
                updated += 1
            else:
                skipped += 1

    if changed and not dry_run:
        _write_agenda(agenda_path, data)

    return created, updated, skipped


# ── Event sync ──────────────────────────────────────────────────────────────

def _sync_one_event(service, calendar_id: str, ev: dict,
                    project_name: str, description: str,
                    dry_run: bool) -> Optional[str]:
    """Sync a single event to Google Calendar. Returns Google Calendar event ID."""
    summary = f"{project_name} — {ev['desc']}"

    start_date = ev["date"]
    # End date: day after end (Google all-day events use exclusive end)
    from datetime import timedelta
    if ev.get("end"):
        end_d = date.fromisoformat(ev["end"])
        end_date = (end_d + timedelta(days=1)).isoformat()
    else:
        end_d = date.fromisoformat(start_date)
        end_date = (end_d + timedelta(days=1)).isoformat()

    if ev.get("gcal_id"):
        if dry_run:
            print(f"  ~ actualizar: 📅 {start_date} — {summary}")
            return ev["gcal_id"]
        try:
            body = {
                "summary": summary,
                "description": description,
                "start": {"date": start_date},
                "end": {"date": end_date},
            }
            service.events().patch(
                calendarId=calendar_id, eventId=ev["gcal_id"], body=body
            ).execute()
            return ev["gcal_id"]
        except Exception as e:
            print(f"  ⚠️  Error actualizando evento '{summary}': {e}")
            return ev["gcal_id"]
    else:
        if dry_run:
            print(f"  ~ crear: 📅 {start_date} — {summary}")
            return None
        try:
            body = {
                "summary": summary,
                "description": description,
                "start": {"date": start_date},
                "end": {"date": end_date},
            }
            result = service.events().insert(
                calendarId=calendar_id, body=body
            ).execute()
            return result["id"]
        except Exception as e:
            print(f"  ⚠️  Error creando evento '{summary}': {e}")
            return None


def _sync_events_for_project(cal_service, project_dir: Path,
                             config: dict, dry_run: bool) -> tuple:
    """Sync all events for a project. Returns (created, updated, skipped)."""
    tipo = _get_project_tipo(project_dir)
    calendar_id = config.get("calendars", {}).get(tipo)
    if not calendar_id:
        calendar_id = config.get("calendars", {}).get("default")
    if not calendar_id:
        return 0, 0, 0

    agenda_path = resolve_file(project_dir, "agenda")
    data = _read_agenda(agenda_path)
    project_name = project_dir.name
    description = _project_description(project_dir, config, html=True)

    created = updated = skipped = 0
    changed = False

    for ev in data["events"]:
        new_id = _sync_one_event(cal_service, calendar_id, ev,
                                 project_name, description, dry_run)
        if new_id and not ev.get("gcal_id"):
            ev["gcal_id"] = new_id
            created += 1
            changed = True
        elif ev.get("gcal_id"):
            updated += 1
        else:
            skipped += 1

    if changed and not dry_run:
        _write_agenda(agenda_path, data)

    return created, updated, skipped


# ── List calendars ──────────────────────────────────────────────────────────

def run_list_calendars() -> int:
    """List available Google Calendars with their IDs."""
    service = _get_calendar_service()
    if not service:
        return 1

    calendars = service.calendarList().list().execute().get("items", [])
    print("Calendarios de Google disponibles:")
    print("─" * 60)
    for cal in sorted(calendars, key=lambda c: c.get("summary", "")):
        primary = " (primary)" if cal.get("primary") else ""
        print(f"  {cal.get('summary', '?')}{primary}")
        print(f"    ID: {cal['id']}")
    print("─" * 60)
    print(f"\nCopia los IDs al fichero de configuración:")
    print(f"  {CONFIG_PATH}")
    return 0


# ── Main entry point ────────────────────────────────────────────────────────

def run_gsync(dry_run: bool = False, list_calendars: bool = False) -> int:
    """Push Orbit tasks/milestones/events to Google Tasks/Calendar."""
    if list_calendars:
        return run_list_calendars()

    if not PROJECTS_DIR.exists():
        print(f"Error: directorio de proyectos no encontrado en {PROJECTS_DIR}")
        return 1

    config = _load_config()

    # Check if calendars are configured
    has_calendars = any(v for v in config.get("calendars", {}).values())
    if not has_calendars:
        print(f"⚠️  No hay calendarios configurados en {CONFIG_PATH}")
        print(f"   Ejecuta: orbit gsync --list-calendars")
        print(f"   Y luego edita {CONFIG_PATH} con los IDs de tus calendarios.")
        print(f"   Los eventos se sincronizarán cuando configures los calendarios.")
        print(f"   Las tareas/hitos se sincronizan igualmente.\n")

    # Get services
    tasks_service = _get_tasks_service()
    cal_service = _get_calendar_service() if has_calendars else None
    if not tasks_service:
        return 1

    label = "  [dry-run]" if dry_run else ""
    print(f"Sincronizando Orbit → Google{label}")
    print("─" * 50)

    dirs = sorted(d for d in PROJECTS_DIR.iterdir()
                  if d.is_dir() and _is_new_project(d))

    total_created = total_updated = total_skipped = 0
    events_created = events_updated = events_skipped = 0
    no_calendar_tipos = set()

    for project_dir in dirs:
        tipo = _get_project_tipo(project_dir)

        # Tasks + milestones
        c, u, s = _sync_tasks_for_project(tasks_service, project_dir, config, dry_run)
        if c or u:
            print(f"  [{project_dir.name}] tareas/hitos: {c} nuevas, {u} actualizadas")
        total_created += c
        total_updated += u
        total_skipped += s

        # Events
        if cal_service:
            calendar_id = config.get("calendars", {}).get(tipo)
            if not calendar_id:
                calendar_id = config.get("calendars", {}).get("default")
            if not calendar_id:
                # Check if project has events
                agenda_path = resolve_file(project_dir, "agenda")
                data = _read_agenda(agenda_path)
                if data["events"]:
                    no_calendar_tipos.add(tipo or project_dir.name)
            else:
                c, u, s = _sync_events_for_project(cal_service, project_dir,
                                                    config, dry_run)
                if c or u:
                    print(f"  [{project_dir.name}] eventos: {c} nuevos, {u} actualizados")
                events_created += c
                events_updated += u
                events_skipped += s

    print("─" * 50)

    parts = []
    tc = total_created + events_created
    tu = total_updated + events_updated
    if tc:
        parts.append(f"{tc} creados")
    if tu:
        parts.append(f"{tu} actualizados")
    if not tc and not tu:
        parts.append("Todo sincronizado")
    print("  ".join(parts))

    if no_calendar_tipos:
        tipos_str = ", ".join(sorted(no_calendar_tipos))
        print(f"\n⚠️  Eventos sin calendario configurado para: {tipos_str}")
        print(f"   Edita {CONFIG_PATH} para asignar calendarios.")

    return 0


# ── Helpers for hooks ──────────────────────────────────────────────────────

def _is_gsync_configured() -> bool:
    """Check if gsync is ready (credentials + config exist)."""
    from core.calendar_sync import CREDENTIALS_PATH, TOKEN_PATH
    return CREDENTIALS_PATH.exists() and TOKEN_PATH.exists() and CONFIG_PATH.exists()


# ── Delete from Google ──────────────────────────────────────────────────────

def delete_gcal_event(project_dir: Path, ev: dict) -> None:
    """Delete a Google Calendar event. Fails silently."""
    if not _is_gsync_configured() or not ev.get("gcal_id"):
        return

    import threading

    def _do_delete():
        try:
            config = _load_config()
            tipo = _get_project_tipo(project_dir)
            cal_id = config.get("calendars", {}).get(tipo)
            if not cal_id:
                cal_id = config.get("calendars", {}).get("default")
            if not cal_id:
                return
            service = _get_calendar_service()
            if service:
                service.events().delete(
                    calendarId=cal_id, eventId=ev["gcal_id"]
                ).execute()
        except Exception:
            pass

    t = threading.Thread(target=_do_delete, daemon=True)
    t.start()
    t.join(timeout=3)


# ── Individual item sync (for add/done/edit/drop hooks) ────────────────────

_SYNC_TIMEOUT = 3  # seconds


def sync_item(project_dir: Path, item: dict, kind: str = "task") -> None:
    """Sync a single task/milestone/event to Google after a local operation.

    kind: "task", "milestone", or "event"
    Runs with a short timeout; fails silently with a warning.
    """
    if not _is_gsync_configured():
        return

    import threading

    def _do_sync():
        try:
            config = _load_config()
            tipo = _get_project_tipo(project_dir)

            if kind in ("task", "milestone"):
                service = _get_tasks_service()
                if not service:
                    return
                tasklist_id = _ensure_task_list(service, tipo, config)
                if not tasklist_id:
                    return
                project_name = project_dir.name
                description = _project_description(project_dir, config)
                is_ms = kind == "milestone"
                new_id = _sync_one_task(service, tasklist_id, item,
                                        project_name, is_ms, description,
                                        dry_run=False)
                if new_id and not item.get("gtask_id"):
                    item["gtask_id"] = new_id
                    # Write back to agenda.md
                    agenda_path = resolve_file(project_dir, "agenda")
                    data = _read_agenda(agenda_path)
                    section = "tasks" if kind == "task" else "milestones"
                    for t in data[section]:
                        if t["desc"] == item["desc"] and t.get("date") == item.get("date"):
                            t["gtask_id"] = new_id
                            break
                    _write_agenda(agenda_path, data)

            elif kind == "event":
                cal_id = config.get("calendars", {}).get(tipo)
                if not cal_id:
                    cal_id = config.get("calendars", {}).get("default")
                if not cal_id:
                    return
                service = _get_calendar_service()
                if not service:
                    return
                project_name = project_dir.name
                description = _project_description(project_dir, config, html=True)
                new_id = _sync_one_event(service, cal_id, item,
                                         project_name, description,
                                         dry_run=False)
                if new_id and not item.get("gcal_id"):
                    item["gcal_id"] = new_id
                    agenda_path = resolve_file(project_dir, "agenda")
                    data = _read_agenda(agenda_path)
                    for e in data["events"]:
                        if e["desc"] == item["desc"] and e["date"] == item["date"]:
                            e["gcal_id"] = new_id
                            break
                    _write_agenda(agenda_path, data)

        except Exception:
            pass  # fail silently

    t = threading.Thread(target=_do_sync, daemon=True)
    t.start()
    t.join(timeout=_SYNC_TIMEOUT)
    if t.is_alive():
        print("  ⚠️  gsync: timeout (se sincronizará con orbit gsync)")


# ── Background sync on shell startup ───────────────────────────────────────

def gsync_background() -> "threading.Thread | None":
    """Run a full gsync in a background thread. Called on shell startup.

    Returns the thread so the caller can join() it before checking git status.
    """
    if not _is_gsync_configured():
        return None

    import threading

    def _do_full_sync():
        try:
            config = _load_config()
            has_calendars = any(v for v in config.get("calendars", {}).values())

            tasks_service = _get_tasks_service()
            cal_service = _get_calendar_service() if has_calendars else None
            if not tasks_service:
                return

            dirs = sorted(d for d in PROJECTS_DIR.iterdir()
                          if d.is_dir() and _is_new_project(d))

            total = 0
            for project_dir in dirs:
                c, u, _ = _sync_tasks_for_project(
                    tasks_service, project_dir, config, dry_run=False)
                total += c + u
                if cal_service:
                    tipo = _get_project_tipo(project_dir)
                    cal_id = config.get("calendars", {}).get(tipo)
                    if not cal_id:
                        cal_id = config.get("calendars", {}).get("default")
                    if cal_id:
                        c, u, _ = _sync_events_for_project(
                            cal_service, project_dir, config, dry_run=False)
                        total += c + u

            if total:
                print(f"\n  ☁️  gsync: {total} items sincronizados con Google")

        except Exception:
            pass  # fail silently — user can run gsync manually

    t = threading.Thread(target=_do_full_sync, daemon=True)
    t.start()
    return t

"""views/ring/export.py — build ring.json from agenda.md across a workspace.

Declarative projection of the rolling 7-day window of items carrying a
``--ring`` attribute into a JSON payload. The standalone daemon
``satellites/ring-daemon/daemon.py`` consumes one or more of these and upserts the
union into the single ``Orbit Ring`` Reminders.app list.

Eligibility:
  - status pending (task/milestone) / not cancelled (reminder)
  - has both ``date`` and ``time`` (rings without time are skipped per RING.md)
  - has ``ring`` attribute parseable by ``views.ring.parse._parse_ring``
  - has ``orbit_id`` (identity required for daemon idempotency)

Recurring items are expanded into individual occurrences in the window,
each given a unique ``orbit_id`` of the form ``<base_id>-<YYYY-MM-DD>`` so
the daemon can match them as distinct EKReminders.
"""
import json
from datetime import date, datetime, timedelta
from pathlib import Path
from threading import Thread as _Thread
from typing import Iterator, Optional

from core.agenda_cmds import _next_occurrence, _read_agenda
from core.config import (
    ORBIT_HOME,
    _FEDERATED_SPACES,
    _iter_workspace_projects,
    iter_project_dirs,
)
from core.log import resolve_file
from core.project import _is_new_project
from views.ring.parse import _parse_ring

DEFAULT_DAYS = 7
DEFAULT_ENABLED = True
MIN_DAYS, MAX_DAYS = 1, 30
MAX_RECUR_ITERATIONS = 5000


def _default_list_name(workspace_root: Path) -> str:
    """Default Reminders.app list name for a workspace = its directory name."""
    return workspace_root.name


def _load_ring_config(workspace_root: Path) -> dict:
    """Read <workspace>/orbit.json → 'ring' section, return merged config.

    Defaults: enabled=True, days=7, list=workspace_root.name. The 'days'
    value is clamped to [MIN_DAYS, MAX_DAYS]; out-of-range or bad types
    fall back silently.
    """
    cfg = {
        "enabled": DEFAULT_ENABLED,
        "days":    DEFAULT_DAYS,
        "list":    _default_list_name(workspace_root),
    }
    path = workspace_root / "orbit.json"
    if not path.exists():
        return cfg
    try:
        data = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return cfg
    user = data.get("ring")
    if not isinstance(user, dict):
        return cfg
    if "enabled" in user:
        cfg["enabled"] = bool(user["enabled"])
    if "days" in user:
        try:
            d = int(user["days"])
            if MIN_DAYS <= d <= MAX_DAYS:
                cfg["days"] = d
        except (TypeError, ValueError):
            pass
    if "list" in user and isinstance(user["list"], str) and user["list"].strip():
        cfg["list"] = user["list"].strip()
    return cfg


def _due_iso(due_date: str, time_str: str) -> Optional[str]:
    """Compose 'YYYY-MM-DDTHH:MM:00' from date + time. Events may carry HH:MM-HH:MM."""
    try:
        d = date.fromisoformat(due_date)
    except (ValueError, TypeError):
        return None
    start = (time_str or "").split("-")[0].strip()
    try:
        h, m = map(int, start.split(":"))
    except (ValueError, AttributeError):
        return None
    return datetime(d.year, d.month, d.day, h, m).isoformat(timespec="seconds")


def _ring_to_alarm_minutes(ring: str, due_dt: datetime) -> Optional[int]:
    """Translate a ring attribute into alarm offset in minutes before due_dt.

    Positive int = ring fires N minutes before due. Negative = after.
    None if unparseable.
    """
    parsed = _parse_ring(ring)
    if parsed is None:
        return None
    kind = parsed["type"]
    if kind == "relative":
        n = parsed["n"]
        unit = parsed["unit"]
        if unit == "m":
            return n
        if unit == "h":
            return n * 60
        if unit == "d":
            return n * 24 * 60
        return None
    if kind == "absolute":
        try:
            ad = date.fromisoformat(parsed["date"])
            ah, am = map(int, parsed["time"].split(":"))
            adt = datetime(ad.year, ad.month, ad.day, ah, am)
        except (ValueError, KeyError):
            return None
        return int((due_dt - adt).total_seconds() // 60)
    if kind == "time_only":
        try:
            ah, am = map(int, parsed["time"].split(":"))
            adt = datetime(due_dt.year, due_dt.month, due_dt.day, ah, am)
        except (ValueError, KeyError):
            return None
        return int((due_dt - adt).total_seconds() // 60)
    return None


def _expand_occurrences(item: dict, w_start: date, w_end: date) -> list:
    """Return dates within [w_start, w_end] when item fires."""
    try:
        base = date.fromisoformat(item["date"])
    except (ValueError, KeyError, TypeError):
        return []
    if not item.get("recur"):
        return [base] if w_start <= base <= w_end else []

    until = None
    if item.get("until"):
        try:
            until = date.fromisoformat(item["until"])
        except ValueError:
            pass

    results = []
    current = base
    for _ in range(MAX_RECUR_ITERATIONS):
        if current > w_end:
            break
        if until and current > until:
            break
        if current >= w_start:
            results.append(current)
        nxt_str = _next_occurrence(current.isoformat(), item["recur"], current.isoformat())
        try:
            nxt = date.fromisoformat(nxt_str)
        except (ValueError, TypeError):
            break
        if nxt <= current:
            break
        current = nxt
    return results


def _is_active(item: dict, kind: str) -> bool:
    if kind in ("task", "milestone"):
        return item.get("status") == "pending"
    if kind == "reminder":
        return not item.get("cancelled")
    return True  # events: always active until done


def _iter_kind_items(items: list, kind: str, project: str,
                     w_start: date, w_end: date, list_name: str) -> Iterator[dict]:
    """Yield payload items for one section of agenda.md."""
    for it in items:
        if not _is_active(it, kind):
            continue
        if not it.get("ring"):
            continue
        if not it.get("date") or not it.get("time"):
            continue
        if not it.get("orbit_id"):
            continue

        for occ in _expand_occurrences(it, w_start, w_end):
            due_iso = _due_iso(occ.isoformat(), it["time"])
            if not due_iso:
                continue
            due_dt = datetime.fromisoformat(due_iso)
            alarm = _ring_to_alarm_minutes(it["ring"], due_dt)
            if alarm is None:
                continue
            base_id = it["orbit_id"]
            oid = f"{base_id}-{occ.isoformat()}" if it.get("recur") else base_id
            yield {
                "orbit_id":      oid,
                "project":       project,
                "kind":          kind,
                "title":         it.get("desc", ""),
                "due_iso":       due_iso,
                "alarm_minutes": alarm,
                "list":          list_name,
            }


def _projects_under(workspace_root: Path) -> Iterator[Path]:
    """Yield project dirs *inside* workspace_root (no federation crossing)."""
    if workspace_root.resolve() == ORBIT_HOME.resolve():
        yield from iter_project_dirs()
    else:
        yield from _iter_workspace_projects(workspace_root)


def build_payload(workspace_root: Path, today: Optional[date] = None,
                  cfg: Optional[dict] = None) -> dict:
    """Build the ring payload for items under workspace_root.

    Reads ring config from <workspace>/orbit.json. When disabled, returns
    a payload with `items: []` but still names the workspace's list so
    the daemon can sweep stale reminders from that list.
    """
    cfg = cfg or _load_ring_config(workspace_root)
    today = today or date.today()
    days = cfg["days"]
    list_name = cfg["list"]
    enabled = cfg["enabled"]
    w_start = today
    w_end = today + timedelta(days=days)
    items: list = []

    if enabled:
        for project_dir in _projects_under(workspace_root):
            if not _is_new_project(project_dir):
                continue
            agenda_path = resolve_file(project_dir, "agenda")
            if not agenda_path.exists():
                continue
            try:
                data = _read_agenda(agenda_path)
            except Exception:
                continue
            proj_name = project_dir.name
            for kind, key in (("task", "tasks"), ("milestone", "milestones"),
                              ("event", "events"), ("reminder", "reminders")):
                items.extend(_iter_kind_items(data.get(key, []), kind,
                                              proj_name, w_start, w_end, list_name))

    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "window_start": w_start.isoformat(),
        "window_end":   w_end.isoformat(),
        "enabled":      enabled,
        "list":         list_name,
        "items":        items,
    }


def write_payload(workspace_root: Path, payload: dict) -> Path:
    """Atomic write of payload to <workspace_root>/.reminders/ring.json."""
    target_dir = workspace_root / ".reminders"
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / "ring.json"
    tmp = target_dir / "ring.json.tmp"
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
    tmp.replace(target)
    return target


def refresh(workspace_root: Path) -> tuple:
    payload = build_payload(workspace_root)
    path = write_payload(workspace_root, payload)
    return path, payload


def all_workspaces() -> list:
    """Return [ORBIT_HOME, *federated workspace roots] (resolved, deduped)."""
    spaces = [ORBIT_HOME.resolve()]
    for space in _FEDERATED_SPACES:
        try:
            spaces.append(Path(space["path"]).expanduser().resolve())
        except (KeyError, TypeError):
            pass
    seen = set()
    out = []
    for s in spaces:
        if s in seen or not s.exists():
            continue
        seen.add(s)
        out.append(s)
    return out


def refresh_all() -> list:
    """Refresh ring.json in the home workspace and every federated workspace."""
    results = []
    for ws in all_workspaces():
        try:
            path, payload = refresh(ws)
            results.append({
                "workspace": ws.name,
                "path":      str(path),
                "count":     len(payload["items"]),
                "list":      payload["list"],
                "enabled":   payload["enabled"],
                "days":      (date.fromisoformat(payload["window_end"]) -
                              date.fromisoformat(payload["window_start"])).days,
            })
        except Exception as exc:
            results.append({"workspace": ws.name, "error": str(exc)})
    return results


def invoke_daemon(daemon_path: Optional[Path] = None,
                  ring_paths: Optional[list] = None) -> tuple:
    """Run satellites/ring-daemon/daemon.py in background; return (success, message)."""
    import subprocess
    import sys

    daemon = daemon_path or (Path(__file__).resolve().parent.parent / "satellites" / "ring-daemon" / "daemon.py")
    if not daemon.exists():
        return False, f"daemon not found: {daemon}"

    if ring_paths is None:
        ring_paths = [ws / ".reminders" / "ring.json"
                      for ws in all_workspaces()
                      if (ws / ".reminders" / "ring.json").exists()]
    if not ring_paths:
        return False, "no ring.json found in any workspace"

    cmd = [sys.executable, str(daemon)] + [str(p) for p in ring_paths]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    except subprocess.TimeoutExpired:
        return False, "daemon timeout (>30s)"
    out = (proc.stdout or "").strip()
    err = (proc.stderr or "").strip()
    msg = out if out else err
    return proc.returncode == 0, msg


def run_ring_refresh(daemon: bool = True) -> int:
    """`orbit ring refresh` — refresh ring.json in all workspaces, optionally apply via daemon."""
    results = refresh_all()
    if not results:
        print("⚠️  No hay workspaces que refrescar.")
        return 0
    for r in results:
        if "error" in r:
            print(f"  ✗ {r['workspace']}: {r['error']}")
        else:
            state = "" if r["enabled"] else " [disabled]"
            print(f"  ✓ {r['workspace']}: {r['count']} items "
                  f"→ list={r['list']!r}{state} ({r['days']}d)")
    if daemon:
        ok, msg = invoke_daemon()
        if ok:
            print(f"  ✓ daemon: {msg}")
        else:
            print(f"  ✗ daemon: {msg}")
            return 1
    return 0


def _action_ring_refresh(ctx):
    """Hook action: refresh ring.json in all workspaces; apply daemon in bg.

    Fired by shell_start and commit_post chains. The ring.json write is
    a quick filesystem op; the EventKit daemon runs in a background thread
    so it never blocks the user.
    """
    try:
        results = refresh_all()
    except Exception as exc:
        return {"ok": False, "msg": f"{type(exc).__name__}: {exc}"}

    def _bg():
        try:
            invoke_daemon()
        except Exception:
            pass

    _Thread(target=_bg, daemon=True).start()
    n = sum(r.get("count", 0) for r in results if "error" not in r)
    return {"ok": True, "msg": f"{n} items across {len(results)} workspace(s)"}


PLIST_LABEL = "com.orbit.ring-daemon"
PLIST_PATH = Path.home() / "Library" / "LaunchAgents" / f"{PLIST_LABEL}.plist"
LOG_DIR = Path.home() / "Library" / "Logs" / "orbit"


def _generate_plist(daemon_path: Path, ring_paths: list, python_path: str) -> str:
    """Return XML for the launchd plist that watches ring.json files."""
    import xml.sax.saxutils as _x

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    stdout_log = str(LOG_DIR / "ring-daemon.stdout.log")
    stderr_log = str(LOG_DIR / "ring-daemon.stderr.log")

    program_args = [python_path, str(daemon_path)] + [str(p) for p in ring_paths]
    args_xml = "\n".join(f"    <string>{_x.escape(a)}</string>" for a in program_args)
    watch_xml = "\n".join(f"    <string>{_x.escape(str(p))}</string>" for p in ring_paths)

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>{PLIST_LABEL}</string>

  <key>ProgramArguments</key>
  <array>
{args_xml}
  </array>

  <key>WatchPaths</key>
  <array>
{watch_xml}
  </array>

  <key>StartCalendarInterval</key>
  <dict>
    <key>Hour</key>
    <integer>0</integer>
    <key>Minute</key>
    <integer>5</integer>
  </dict>

  <key>RunAtLoad</key>
  <true/>

  <key>StandardOutPath</key>
  <string>{_x.escape(stdout_log)}</string>

  <key>StandardErrorPath</key>
  <string>{_x.escape(stderr_log)}</string>
</dict>
</plist>
"""


def _launchctl(action: str, label: str = PLIST_LABEL) -> tuple:
    """Run launchctl bootstrap/bootout/start. Returns (ok, msg)."""
    import subprocess
    uid = subprocess.run(["id", "-u"], capture_output=True, text=True).stdout.strip()
    domain = f"gui/{uid}"

    if action == "load":
        cmd = ["launchctl", "bootstrap", domain, str(PLIST_PATH)]
    elif action == "unload":
        cmd = ["launchctl", "bootout", f"{domain}/{label}"]
    elif action == "kickstart":
        cmd = ["launchctl", "kickstart", "-k", f"{domain}/{label}"]
    elif action == "print":
        cmd = ["launchctl", "print", f"{domain}/{label}"]
    else:
        return False, f"unknown launchctl action: {action}"

    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
    except subprocess.TimeoutExpired:
        return False, "launchctl timeout"
    out = (r.stdout or "").strip()
    err = (r.stderr or "").strip()
    return r.returncode == 0, (out or err or "ok")


def run_ring_install() -> int:
    """Install the launchd plist that fires the daemon on ring.json changes."""
    import sys

    daemon = Path(__file__).resolve().parent.parent / "satellites" / "ring-daemon" / "daemon.py"
    if not daemon.exists():
        print(f"  ✗ Daemon no encontrado en {daemon}.")
        return 1

    # Ensure ring.json exists in each workspace (bootstrap)
    print("  Refrescando ring.json en todos los workspaces …")
    refresh_all()

    ring_paths = [ws / ".reminders" / "ring.json"
                  for ws in all_workspaces()
                  if (ws / ".reminders" / "ring.json").exists()]
    if not ring_paths:
        print("  ✗ No hay ring.json en ningún workspace; aborto.")
        return 1

    PLIST_PATH.parent.mkdir(parents=True, exist_ok=True)

    # Unload any previous version (idempotent install/upgrade)
    if PLIST_PATH.exists():
        _launchctl("unload")

    plist_text = _generate_plist(daemon, ring_paths, sys.executable)
    PLIST_PATH.write_text(plist_text)
    print(f"  ✓ Plist escrito: {PLIST_PATH}")
    print(f"      WatchPaths ({len(ring_paths)}):")
    for p in ring_paths:
        print(f"        - {p}")

    ok, msg = _launchctl("load")
    if not ok:
        print(f"  ✗ launchctl bootstrap falló: {msg}")
        return 1
    print(f"  ✓ launchd cargado: {PLIST_LABEL}")
    print(f"      logs: {LOG_DIR}/ring-daemon.{{stdout,stderr}}.log")
    print()
    print("  ⚠️  Primera vez: macOS necesita autorizar el acceso a Reminders al")
    print(f"      binario {sys.executable}.")
    print("      Si el daemon falla con 'access denied' (ver stderr log),")
    print("      abre System Settings → Privacy & Security → Reminders y")
    print("      añade Python a la lista de apps autorizadas.")
    print("      Tras autorizar: `launchctl kickstart -k gui/$(id -u)/" + PLIST_LABEL + "`")
    return 0


def run_ring_uninstall() -> int:
    """Unload the launchd plist and remove it."""
    if not PLIST_PATH.exists():
        print("  ℹ️  Plist no instalado.")
        return 0
    ok, msg = _launchctl("unload")
    if not ok and "Could not find" not in msg and "No such" not in msg:
        print(f"  ⚠️  launchctl bootout: {msg}")
    PLIST_PATH.unlink()
    print(f"  ✓ Plist borrado: {PLIST_PATH}")
    return 0


def run_ring_status() -> int:
    """`orbit ring status` — show ring.json contents per workspace + plist state."""
    if PLIST_PATH.exists():
        ok, _ = _launchctl("print")
        state = "loaded" if ok else "installed but not loaded"
        print(f"  plist: {PLIST_PATH.name} [{state}]")
    else:
        print(f"  plist: not installed (run `orbit ring install`)")
    print()
    found = False
    for ws in all_workspaces():
        rp = ws / ".reminders" / "ring.json"
        if not rp.exists():
            continue
        found = True
        try:
            data = json.loads(rp.read_text())
        except Exception as exc:
            print(f"  ✗ {ws.name}: parse error: {exc}")
            continue
        items = data.get("items", [])
        lst = data.get("list", "?")
        enabled = data.get("enabled", True)
        state = "" if enabled else " [disabled]"
        print(f"  {ws.name}: {len(items)} items → list={lst!r}{state} "
              f"(window {data.get('window_start', '?')} → {data.get('window_end', '?')}, "
              f"generated {data.get('generated_at', '?')})")
        for it in items[:20]:
            kind = it.get("kind", "?")
            print(f"    {kind:9s} {it.get('due_iso', '?')}  "
                  f"-{it.get('alarm_minutes', '?')}m  "
                  f"[{it.get('project', '?')}] {it.get('title', '?')}")
        if len(items) > 20:
            print(f"    … +{len(items)-20} más")
    if not found:
        print("⚠️  No hay ring.json en ningún workspace. Ejecuta `orbit ring refresh`.")
    return 0

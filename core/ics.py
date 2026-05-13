"""ics — serialize orbit appointments to iCalendar (RFC 5545).

Used as a portable, read-only render channel: Calendar.app / Google
Calendar / Outlook subscribe to ``.ics`` files emitted by orbit, no
AppleScript writes involved.

Topology (phase 1, configurable in calendar-sync.json → ``ics_buckets``):

    cloud_root/<workspace>/calendar/
        agenda.ics                ← bucket "agenda" = tasks + reminders
        events.ics                ← bucket "events" = events + ms + cronos
        projects/<project>.ics    ← per-project, ALL kinds

Each ``VEVENT`` carries custom ``X-ORBIT-PROJECT`` / ``X-ORBIT-KIND`` /
``X-ORBIT-ID`` props so a future importer can route by them, and an
``X-WR-CALNAME`` at the ``VCALENDAR`` level so Calendar.app's sidebar
shows a friendly name.

Recurrence: orbit ``recur`` values (``daily`` / ``weekly`` / ``monthly``
/ ``weekdays`` / ``every-N-units`` / ``first-mon`` …) are **expanded
into per-occurrence VEVENTs** over a ±180-day window. This is
deliberately simpler than emitting RRULE: it makes single-occurrence
overrides trivial (each occurrence is independent) and avoids the
EXDATE / RECURRENCE-ID dance.
"""

from __future__ import annotations

import re
from datetime import date as _date, datetime, timedelta
from pathlib import Path
from typing import Iterable, Optional

from core.agenda_cmds import (
    _read_agenda, _next_occurrence,
    event_room_urls, event_agenda_urls, _is_meeting_url,
)
from core.config import iter_project_dirs
from core.log import resolve_file

# Window for expansion (days before/after today).
WINDOW_DAYS = 180

# Internal-kind mapping. Same as calsync's, exposed here so callers can
# pick buckets without depending on calsync.
_KIND_EMOJI = {
    "task":       "✅",
    "milestone":  "🏁",
    "reminder":   "💬",
    "event":      "📅",
    "cronograma": "📊",
}

# Default partition if calendar-sync.json doesn't specify ics_buckets.
_DEFAULT_BUCKETS = {
    "agenda": ["task", "reminder"],
    "events": ["event", "milestone", "cronograma"],
}

# Per-kind visible duration (minutes) when no explicit end is given.
# ICS-only — does not touch agenda.md or the AppleScript-write path.
_DEFAULT_DURATION_MIN = {
    "event":      60,
    "task":       60,
    "milestone":  60,
    "cronograma": 60,
    "reminder":   5,
}


# ── iCalendar low-level helpers ────────────────────────────────────────

def _escape(s: str) -> str:
    """Escape a TEXT-type iCalendar value per RFC 5545 §3.3.11.

    Order matters: backslash first so we don't double-escape.
    """
    if s is None:
        return ""
    s = s.replace("\\", "\\\\")
    s = s.replace("\n", "\\n").replace("\r", "")
    s = s.replace(",", "\\,").replace(";", "\\;")
    return s


def _fold(line: str) -> str:
    """Fold a logical line so no physical line exceeds 75 octets.

    Continuation lines start with one space (per RFC §3.1). Counts in
    bytes (UTF-8) to handle multibyte chars safely.
    """
    raw = line.encode("utf-8")
    if len(raw) <= 75:
        return line
    out = []
    i = 0
    while i < len(raw):
        chunk_size = 75 if not out else 74  # later chunks lose 1 to the leading SP
        end = min(i + chunk_size, len(raw))
        # Avoid cutting in the middle of a multibyte char: rewind to a
        # UTF-8 char boundary.
        while end < len(raw) and (raw[end] & 0xC0) == 0x80:
            end -= 1
        out.append(raw[i:end].decode("utf-8"))
        i = end
    return "\r\n ".join(out)


def _fmt_dt_local(iso: str) -> str:
    """``YYYY-MM-DDTHH:MM`` → ``YYYYMMDDTHHMMSS`` (floating local).

    Floating means no ``Z`` suffix and no ``TZID=`` param — the
    receiving client interprets it in its own local time. Matches
    today's AppleScript behaviour.
    """
    d, t = iso.split("T")
    y, mo, da = d.split("-")
    if t.count(":") == 1:
        h, mn = t.split(":")
        sec = "00"
    else:
        h, mn, sec = t.split(":")
    return f"{y}{mo}{da}T{h}{mn}{sec}"


def _fmt_date(iso_d: str) -> str:
    """``YYYY-MM-DD`` → ``YYYYMMDD`` for ``VALUE=DATE`` (all-day)."""
    return iso_d.replace("-", "")


def _now_stamp() -> str:
    """``DTSTAMP`` value: UTC now in ``YYYYMMDDTHHMMSSZ`` form. RFC
    requires UTC for this property."""
    return datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")


# ── Item → VEVENT ──────────────────────────────────────────────────────

def _item_uid(orbit_id: Optional[str], occurrence_iso: Optional[str],
              fallback: str) -> str:
    """Build a stable UID.

    Stability matters: identical UIDs across renders let Calendar.app
    recognise the event as "same, maybe updated" rather than
    "deleted + new" (which would reset the alarm state).
    """
    base = orbit_id or fallback
    if occurrence_iso:
        return f"{base}-{occurrence_iso}@orbit"
    return f"{base}@orbit"


def _summary_for(item: dict, kind: str, project_name: str) -> str:
    """``[<project>] <emoji> <desc>``. For ``event`` no emoji (legacy)."""
    if kind == "event":
        return f"[{project_name}] {item['desc']}"
    emoji = _KIND_EMOJI.get(kind, "")
    if emoji:
        return f"[{project_name}] {emoji} {item['desc']}".rstrip()
    return f"[{project_name}] {item['desc']}"


def _description_for(item: dict, project_name: str) -> str:
    """Item notes + project marker + orbit-id tag.

    orbit-id goes at the end so the user can reference it from any
    calendar client UI ("orbit-id abc12345 está desplazado") without
    needing to inspect the raw .ics or its X-ORBIT-ID custom prop.
    """
    base = f"Proyecto: {project_name}"
    orbit_id = item.get("orbit_id")
    if orbit_id:
        base += f"\n[orbit:{orbit_id}]"
    notes = item.get("notes") or []
    if not notes:
        return base
    return "\n".join(notes) + "\n\n" + base


def _event_url(item: dict) -> str:
    """Pick a meeting URL out of event notes (📋 agenda / 🚪 room).
    Mirrors gsync._ev_props_for_calendar_app routing."""
    rooms   = event_room_urls(item)
    agendas = event_agenda_urls(item)
    for u in rooms + agendas:
        if _is_meeting_url(u):
            return u
    return ""


def _alarm_block(minutes_before: int) -> list:
    """VALARM rendering. Negative ``TRIGGER`` = before start."""
    if minutes_before is None or minutes_before < 0:
        return []
    return [
        "BEGIN:VALARM",
        "ACTION:DISPLAY",
        "DESCRIPTION:Reminder",
        f"TRIGGER:-PT{minutes_before}M",
        "END:VALARM",
    ]


def _alarm_minutes(item: dict, kind: str) -> Optional[int]:
    """Compute the alarm offset in minutes. None → no alarm.

    For agenda items (task/ms/rem) without ``ring``, default is 0
    (fire at start) — same as gsync's _agenda_props_for_calendar_app.
    For events, alarm fires only if ``ring`` is set.
    """
    ring = item.get("ring")
    if not ring and kind in ("event", "cronograma"):
        return None
    if not ring:
        return 0
    # Mirror gsync's _alarm_minutes_for_event but only for the simple
    # ``Nm`` / ``Nh`` form; richer ring expressions (`08:00`) fall back
    # to 0 (fire at start).
    m = re.match(r"^(\d+)([mhd])$", ring.lower())
    if not m:
        return 0
    n, unit = int(m.group(1)), m.group(2)
    return n * (1 if unit == "m" else 60 if unit == "h" else 1440)


def render_vevent(item: dict, kind: str, project_name: str,
                  occurrence_date: Optional[str] = None) -> list:
    """Build a single VEVENT block as a list of folded lines.

    ``occurrence_date`` overrides the item's stored date when set —
    used by the recurrence expander to emit one VEVENT per occurrence.
    """
    date_iso = occurrence_date or item["date"]
    orbit_id = item.get("orbit_id")
    uid = _item_uid(orbit_id, occurrence_date if item.get("recur") else None,
                    fallback=f"orbit-{kind}-{item['desc']}-{date_iso}")
    summary     = _summary_for(item, kind, project_name)
    description = _description_for(item, project_name)
    url         = _event_url(item) if kind == "event" else ""

    time_val = item.get("time")
    is_event = (kind == "event")
    all_day  = (is_event and not time_val)

    if all_day:
        # DTEND is exclusive for VALUE=DATE → add one day.
        end_d = item.get("end") or date_iso
        end_plus = (_date.fromisoformat(end_d) + timedelta(days=1)).isoformat()
        dtstart = f"DTSTART;VALUE=DATE:{_fmt_date(date_iso)}"
        dtend   = f"DTEND;VALUE=DATE:{_fmt_date(end_plus)}"
    else:
        if is_event and time_val and "-" in time_val:
            start_part, end_part = time_val.split("-", 1)
            start_iso = f"{date_iso}T{start_part}"
            end_iso   = f"{item.get('end') or date_iso}T{end_part}"
        else:
            # Single-time entry (event with HH:MM only, or any agenda kind):
            # synthesize end = start + per-kind default duration so the block
            # is visible in week/month views of the subscribing client.
            if is_event:
                t = time_val
            else:
                t = (time_val.split("-")[0] if time_val and "-" in time_val
                     else time_val) or "09:00"
            start_iso = f"{date_iso}T{t}"
            minutes = _DEFAULT_DURATION_MIN.get(kind, 20)
            try:
                end_dt = datetime.fromisoformat(f"{start_iso}:00") + timedelta(minutes=minutes)
                end_iso = end_dt.strftime("%Y-%m-%dT%H:%M")
            except ValueError:
                end_iso = start_iso
        dtstart = f"DTSTART:{_fmt_dt_local(start_iso)}"
        dtend   = f"DTEND:{_fmt_dt_local(end_iso)}"

    lines = [
        "BEGIN:VEVENT",
        f"UID:{uid}",
        f"DTSTAMP:{_now_stamp()}",
        dtstart,
        dtend,
        f"SUMMARY:{_escape(summary)}",
        f"DESCRIPTION:{_escape(description)}",
    ]
    if url:
        lines.append(f"URL:{_escape(url)}")
        # Also expose as LOCATION so the address line carries the link
        # (some clients show only LOCATION in compact views).
        lines.append(f"LOCATION:{_escape(url)}")
    lines.append(f"CATEGORIES:{kind}")
    if orbit_id:
        lines.append(f"X-ORBIT-ID:{orbit_id}")
    lines.append(f"X-ORBIT-PROJECT:{_escape(project_name)}")
    lines.append(f"X-ORBIT-KIND:{kind}")
    lines.extend(_alarm_block(_alarm_minutes(item, kind)))
    lines.append("END:VEVENT")
    return [_fold(ln) for ln in lines]


# ── Recurrence expansion ───────────────────────────────────────────────

def _expand_dates(item: dict, window_start: _date,
                  window_end: _date) -> list:
    """Yield occurrence ISO date strings within
    ``[window_start, window_end]`` for a recurring item.

    Non-recurring → single-element list with item['date'] if in window.
    """
    try:
        start = _date.fromisoformat(item["date"])
    except (KeyError, ValueError):
        return []
    if not item.get("recur"):
        return [item["date"]] if window_start <= start <= window_end else []

    until_iso = item.get("until")
    until_date = (_date.fromisoformat(until_iso) if until_iso
                  else window_end)
    horizon = min(until_date, window_end)

    out = []
    cur = start
    # Cap iterations defensively to avoid pathological recur strings.
    for _ in range(2000):
        if cur > horizon:
            break
        if cur >= window_start:
            out.append(cur.isoformat())
        nxt = _next_occurrence(cur.isoformat(), item["recur"],
                                cur.isoformat())
        nxt_d = _date.fromisoformat(nxt)
        if nxt_d <= cur:
            break  # safety: recur didn't advance
        cur = nxt_d
    return out


# ── Project collection ─────────────────────────────────────────────────

def _collect_project_items(project_dir: Path) -> list:
    """Yield ``(kind, item)`` tuples for every appointment of a project
    (tasks/ms/events/reminders + cronograms). Terminal states skipped."""
    items = []
    data = _read_agenda(resolve_file(project_dir, "agenda"))
    for section, kind in (
        ("tasks",      "task"),
        ("milestones", "milestone"),
        ("events",     "event"),
        ("reminders",  "reminder"),
    ):
        for it in data.get(section, []):
            status = it.get("status")
            if status in ("done", "cancelled"):
                continue
            if kind == "reminder" and it.get("cancelled"):
                continue
            items.append((kind, it))

    # Cronograms: synthesize the next-open-leaf event same as gsync does.
    items.extend(_collect_cronos(project_dir))
    return items


def _collect_cronos(project_dir: Path) -> list:
    """Mirror gsync._sync_cronos_for_project synthesis (next open leaf)."""
    cronos_dir = project_dir / "cronos"
    if not cronos_dir.exists():
        return []
    files = sorted(cronos_dir.glob("crono-*.md"))
    if not files:
        return []
    try:
        from core.cronograma import (_parse_crono_file, _compute_dates,
                                     next_open_leaf, cronograma_all_done,
                                     _leaf_deadline)
    except ImportError:
        return []
    out = []
    for path in files:
        name = path.stem.removeprefix("crono-")
        try:
            data = _parse_crono_file(path)
            _compute_dates(data["tasks"], data["metadata"])
        except Exception:
            continue
        leaf = next_open_leaf(data)
        if leaf is None or cronograma_all_done(data):
            continue
        out.append(("cronograma", {
            "desc":      f"crono-{name}: {leaf['title']}",
            "date":      _leaf_deadline(leaf).isoformat(),
            "time":      None,
            "notes":     [f"Cronograma: cronos/{path.name}"],
            "orbit_id":  None,   # synthesised; UID falls back to hash
        }))
    return out


# ── Calendar wrapper ───────────────────────────────────────────────────

def _calendar_wrapper(name: str, body_lines: list,
                       description: Optional[str] = None) -> str:
    """Wrap a list of VEVENT lines in a VCALENDAR header/footer."""
    header = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Orbit//Orbit Calendar//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{_escape(name)}",
    ]
    if description:
        header.append(f"X-WR-CALDESC:{_escape(description)}")
    footer = ["END:VCALENDAR"]
    return "\r\n".join([_fold(h) for h in header] + body_lines + footer) + "\r\n"


# ── Public renderers ───────────────────────────────────────────────────

def render_project(project_dir: Path,
                   window_start: Optional[_date] = None,
                   window_end:   Optional[_date] = None,
                   kinds:        Optional[Iterable[str]] = None) -> str:
    """Return the full ``.ics`` text for one project, all kinds (unless
    ``kinds`` filters it). Ready to write to disk or stdout.
    """
    today = _date.today()
    window_start = window_start or (today - timedelta(days=WINDOW_DAYS))
    window_end   = window_end   or (today + timedelta(days=WINDOW_DAYS))
    selected = set(kinds) if kinds else None
    project_name = project_dir.name
    body = []
    for kind, item in _collect_project_items(project_dir):
        if selected and kind not in selected:
            continue
        if not item.get("date"):
            continue
        for occ in _expand_dates(item, window_start, window_end):
            body.extend(render_vevent(item, kind, project_name,
                                       occurrence_date=occ))
    return _calendar_wrapper(f"Orbit · {project_name}", body)


def render_bucket(bucket_name: str, bucket_kinds: list,
                  workspace_name: str,
                  window_start: Optional[_date] = None,
                  window_end:   Optional[_date] = None) -> str:
    """Return the ``.ics`` for an aggregator bucket spanning every
    project of the workspace, filtered to ``bucket_kinds``.
    """
    today = _date.today()
    window_start = window_start or (today - timedelta(days=WINDOW_DAYS))
    window_end   = window_end   or (today + timedelta(days=WINDOW_DAYS))
    body = []
    for project_dir in iter_project_dirs():
        project_name = project_dir.name
        for kind, item in _collect_project_items(project_dir):
            if kind not in bucket_kinds:
                continue
            if not item.get("date"):
                continue
            for occ in _expand_dates(item, window_start, window_end):
                body.extend(render_vevent(item, kind, project_name,
                                           occurrence_date=occ))
    label = f"Orbit · {workspace_name} · {bucket_name}"
    return _calendar_wrapper(label, body)


# ── Bucket config ──────────────────────────────────────────────────────

def get_buckets(config: Optional[dict] = None) -> dict:
    """Read ``ics_buckets`` from calendar-sync.json or fall back to the
    default partition (agenda=tasks+rem, events=ev+ms+cronos)."""
    if config is None:
        from core.gsync import _load_config
        config = _load_config()
    return config.get("ics_buckets") or {
        k: list(v) for k, v in _DEFAULT_BUCKETS.items()
    }


def validate_buckets(buckets: dict) -> list:
    """Return a list of human-readable error strings. Empty list = OK.

    Each kind must appear in exactly one bucket. Unknown kinds and
    duplicates are flagged.
    """
    errors = []
    valid_kinds = set(_KIND_EMOJI)
    seen = {}
    for bname, kinds in buckets.items():
        if not isinstance(kinds, list):
            errors.append(f"bucket {bname!r}: el valor debe ser una lista")
            continue
        for k in kinds:
            if k not in valid_kinds:
                errors.append(f"bucket {bname!r}: kind desconocido {k!r} "
                              f"(válidos: {', '.join(sorted(valid_kinds))})")
                continue
            if k in seen:
                errors.append(f"kind {k!r} duplicado en buckets "
                              f"{seen[k]!r} y {bname!r}")
            else:
                seen[k] = bname
    for k in valid_kinds:
        if k not in seen:
            errors.append(f"kind {k!r} no aparece en ningún bucket → no se sincroniza")
    return errors


# ── Snapshot diff ──────────────────────────────────────────────────────

def _parse_vevents(ics_text: str) -> dict:
    """Parse a ``.ics`` blob into ``{uid: {prop: value}}`` for diff.

    Strips ``DTSTAMP`` (UTC-now, regenerated every render) so diffs
    surface only real content changes. Unfolds RFC 5545 line folds.
    """
    # Unfold continuation lines (`\r\n ` or `\r\n\t`).
    text = ics_text.replace("\r\n ", "").replace("\r\n\t", "")
    text = text.replace("\n ", "").replace("\n\t", "")

    events = {}
    current = None
    for raw in text.splitlines():
        line = raw.rstrip("\r")
        if line == "BEGIN:VEVENT":
            current = {}
        elif line == "END:VEVENT":
            if current is not None and "UID" in current:
                events[current["UID"]] = current
            current = None
        elif current is not None and ":" in line:
            key, _, val = line.partition(":")
            key = key.split(";", 1)[0]   # strip params (e.g. VALUE=DATE)
            if key == "DTSTAMP":
                continue
            # First occurrence wins (e.g. two LOCATION/URL — we kept one).
            if key not in current:
                current[key] = val
    return events


def diff_snapshot(current_ics: str, snapshot_ics: str) -> dict:
    """Compare a freshly-rendered ``.ics`` against the last-written
    snapshot. Returns:

      {
          "added":   [uid, ...],            # in current, not in snapshot
          "removed": [uid, ...],            # in snapshot, not in current
          "changed": [(uid, [attr, ...]), ...],   # both, attrs differ
      }
    """
    cur = _parse_vevents(current_ics)
    snap = _parse_vevents(snapshot_ics)
    cur_uids, snap_uids = set(cur), set(snap)
    added   = sorted(cur_uids - snap_uids)
    removed = sorted(snap_uids - cur_uids)
    changed = []
    for uid in sorted(cur_uids & snap_uids):
        c, s = cur[uid], snap[uid]
        attrs = [k for k in (c.keys() | s.keys()) if c.get(k) != s.get(k)]
        if attrs:
            changed.append((uid, sorted(attrs)))
    return {"added": added, "removed": removed, "changed": changed}


# ── Filesystem writer + Calendar.app refresh ───────────────────────────

_SNAPSHOT_SUFFIX = ".snapshot"


def _write_with_snapshot(path: Path, content: str) -> dict:
    """Write ``content`` to ``path`` and update ``path.snapshot``. The
    snapshot lags one render — so the next call can diff "before" vs
    "after".

    On first write (no snapshot yet) returns an empty diff.
    """
    snap = path.with_suffix(path.suffix + _SNAPSHOT_SUFFIX)
    prior = snap.read_text() if snap.exists() else None
    path.write_text(content)
    diff = (diff_snapshot(content, prior) if prior is not None
            else {"added": [], "removed": [], "changed": []})
    snap.write_text(content)
    return diff


def write_workspace(cloud_root: Path,
                    project_filter: Optional[str] = None) -> int:
    """Regenerate ``.ics`` files for the current workspace.

    ``project_filter``: substring match on a project directory name. If
    set, only that project's per-project ``.ics`` is rewritten. The
    workspace-level bucket aggregators are **always** rebuilt because
    they pool events across every project of the workspace — a change
    in one project affects every bucket that includes its kind.

    Returns the count of files written. Layout:
        cloud_root/calendar/
            <bucket>.ics                 ← always rebuilt
            projects/<project>.ics       ← all, or just the filtered one

    Idempotent — safe to call from render's post-commit hook or from
    the background dash trigger.
    """
    cal_dir = cloud_root / "calendar"
    proj_dir = cal_dir / "projects"
    proj_dir.mkdir(parents=True, exist_ok=True)

    from core.config import ORBIT_HOME
    workspace_name = ORBIT_HOME.name
    buckets = get_buckets()
    errors = validate_buckets(buckets)
    if errors:
        # Don't write garbage if the partition is broken; report and bail.
        for e in errors:
            print(f"⚠️  ics_buckets: {e}")
        return 0

    written = 0
    changes = {"added": [], "removed": [], "changed": []}

    def _merge(d):
        changes["added"].extend(d["added"])
        changes["removed"].extend(d["removed"])
        changes["changed"].extend(d["changed"])

    for bname, kinds in buckets.items():
        ics = render_bucket(bname, kinds, workspace_name)
        _merge(_write_with_snapshot(cal_dir / f"{bname}.ics", ics))
        written += 1

    # Per-project files: either all, or only the filtered one.
    for project_dir in iter_project_dirs():
        if project_filter and project_filter.lower() not in project_dir.name.lower():
            continue
        ics = render_project(project_dir)
        _merge(_write_with_snapshot(proj_dir / f"{project_dir.name}.ics", ics))
        written += 1

    _trigger_calendar_reload()
    # Summary of *real* changes since last render (deduped across buckets +
    # per-project files, since the same VEVENT appears in both).
    dedup_changes = {
        "added":   sorted(set(changes["added"])),
        "removed": sorted(set(changes["removed"])),
        "changed": list({uid: attrs
                          for uid, attrs in changes["changed"]}.items()),
    }
    n_real = (len(dedup_changes["added"]) + len(dedup_changes["removed"])
              + len(dedup_changes["changed"]))
    if n_real:
        print(f"  📅 ics: {len(dedup_changes['added'])} añadidos / "
              f"{len(dedup_changes['changed'])} modificados / "
              f"{len(dedup_changes['removed'])} eliminados desde el último render")
    return written


def _trigger_calendar_reload() -> None:
    """Best-effort: ask Calendar.app to refresh its subscriptions now.

    This is the one remaining AppleScript call in the .ics flow — and
    it's read-only ("reload calendars" doesn't create/update/delete
    anything). If Calendar.app isn't running, the auto-refresh interval
    of the subscription closes the gap eventually.
    """
    try:
        from core.gsync import _calendar_app_running, _osa
    except ImportError:
        return
    if not _calendar_app_running():
        return
    _osa('tell application "Calendar" to reload calendars', timeout=5)

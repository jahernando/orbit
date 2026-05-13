"""calsync — audit and reconcile orbit appointments vs Calendar.app render.

    orbit calsync <project> [--type LIST] [--all|--pending] [--dry-run]

What it does:
  1. For every appointment of the project (tasks, milestones, events,
     reminders, cronogramas) compute the expected Calendar.app props.
  2. Bulk-read each target calendar (one AppleScript per calendar) and
     match events by orbit-id.
  3. For each item, compare summary / start / end / description.
  4. Per drifted attribute, prompt interactively:
       [1-orbit]  → push orbit's value back to Calendar (sync_item)
       [2-cal]    → adopt the Calendar value into agenda.md
                    (sugar for "3-input pre-filled with the Calendar value")
       [3-input]  → type a fresh value to write both ways
       [s-skip]   → leave as-is
  5. Orphans (Calendar events without a matching orbit-id) are reported
     at the end as a read-only list — no auto-import in v1.

Rationale:
  Orbit is the source of truth (v0.28). ``calsync`` does not introduce
  auto-pull: every "2-cal" / "3-input" choice is an explicit human
  decision per attribute, and the value written into ``agenda.md`` is
  always the one the user just confirmed on screen.
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, date as _date
from pathlib import Path
from typing import Optional

from core.config import iter_project_dirs
from core.log import resolve_file
from core.agenda_cmds import (
    _read_agenda, _write_agenda,
    _format_task_line, _format_event_line, _format_reminder_line,
)


# Per-kind metadata. Each entry maps to its Calendar.app title prefix
# emoji (task/ms/rem live in the per-workspace agenda calendar; events
# and cronogramas in the per-tipo events calendar).
_KIND_EMOJI = {
    "task":       "✅",
    "milestone":  "🏁",
    "reminder":   "💬",
    "event":      "📅",
    "cronograma": "📊",
}

# CLI-name → internal-kind map (the user types "task,ms,ev,rem,crono").
_TYPE_ALIASES = {
    "task":  "task",
    "ms":    "milestone",
    "ev":    "event",
    "rem":   "reminder",
    "crono": "cronograma",
}
ALL_TYPES = ["task", "ms", "ev", "rem", "crono"]


# ── Bulk read of a Calendar.app calendar (no orbit-id filter) ─────────

def _fetch_window(calendar_name: str, start: _date, end: _date) -> list:
    """Return every event in ``calendar_name`` whose start date falls in
    ``[start, end]``. Deduped by uid (Calendar.app expands recurring
    instances when iterating).

    Each entry: ``{uid, summary, start_iso, end_iso, description,
    location, orbit_id}``. ``orbit_id`` is None for un-orbited events.

    One AppleScript per calendar — O(1) calls regardless of item count.
    """
    from core.gsync import (
        _osa, _esc, _parse_orbit_tag,
        _FETCH_FIELD_SEP, _FETCH_RECORD_SEP,
    )

    cal = _esc(calendar_name)
    fld = "(ASCII character 31)"
    rec = "(ASCII character 30)"
    # Build the date range literals via current date components → no locale.
    s_d, e_d = start, end
    script = (
        f'set winStart to current date\n'
        f'set year of winStart to {s_d.year}\n'
        f'set month of winStart to {s_d.month}\n'
        f'set day of winStart to {s_d.day}\n'
        f'set hours of winStart to 0\n'
        f'set minutes of winStart to 0\n'
        f'set seconds of winStart to 0\n'
        f'set winEnd to current date\n'
        f'set year of winEnd to {e_d.year}\n'
        f'set month of winEnd to {e_d.month}\n'
        f'set day of winEnd to {e_d.day}\n'
        f'set hours of winEnd to 23\n'
        f'set minutes of winEnd to 59\n'
        f'set seconds of winEnd to 59\n'
        f'tell application "Calendar"\n'
        f'    tell calendar "{cal}"\n'
        f'        set fld to {fld}\n'
        f'        set rec to {rec}\n'
        f'        set out to ""\n'
        f'        repeat with e in (every event whose start date ≥ winStart and start date ≤ winEnd)\n'
        f'            set s_str to ""\n'
        f'            try\n'
        f'                set sd to start date of e\n'
        f'                set s_str to (year of sd as text) & "-" & ¬\n'
        f'                  (text -2 thru -1 of ("0" & (month of sd as integer))) & "-" & ¬\n'
        f'                  (text -2 thru -1 of ("0" & (day of sd))) & "T" & ¬\n'
        f'                  (text -2 thru -1 of ("0" & (hours of sd))) & ":" & ¬\n'
        f'                  (text -2 thru -1 of ("0" & (minutes of sd)))\n'
        f'            end try\n'
        f'            set e_str to ""\n'
        f'            try\n'
        f'                set ed to end date of e\n'
        f'                set e_str to (year of ed as text) & "-" & ¬\n'
        f'                  (text -2 thru -1 of ("0" & (month of ed as integer))) & "-" & ¬\n'
        f'                  (text -2 thru -1 of ("0" & (day of ed))) & "T" & ¬\n'
        f'                  (text -2 thru -1 of ("0" & (hours of ed))) & ":" & ¬\n'
        f'                  (text -2 thru -1 of ("0" & (minutes of ed)))\n'
        f'            end try\n'
        f'            set desc_str to ""\n'
        f'            try\n'
        f'                set desc_str to description of e\n'
        f'            end try\n'
        f'            set loc_str to ""\n'
        f'            try\n'
        f'                set loc_str to location of e\n'
        f'            end try\n'
        f'            set out to out & (uid of e) & fld & (summary of e) & fld ¬\n'
        f'                & s_str & fld & e_str & fld & desc_str & fld & loc_str & rec\n'
        f'        end repeat\n'
        f'        return out\n'
        f'    end tell\n'
        f'end tell'
    )
    out = _osa(script, timeout=120)
    if not out:
        return []
    items, seen = [], set()
    for raw in out.split(_FETCH_RECORD_SEP):
        if not raw.strip():
            continue
        parts = raw.split(_FETCH_FIELD_SEP)
        if len(parts) < 6:
            continue
        uid, summary, s_iso, e_iso, description, location = parts[:6]
        if uid in seen:
            continue
        seen.add(uid)
        oid, _ = _parse_orbit_tag(description)
        items.append({
            "uid":         uid,
            "summary":     summary,
            "start_iso":   s_iso or None,
            "end_iso":     e_iso or None,
            "description": description,
            "location":    location or "",
            "orbit_id":    oid,
        })
    return items


# ── Expected props (what Calendar.app *should* hold for an orbit item) ──

def _expected_summary(item: dict, kind: str, project_name: str) -> str:
    """Mirror of gsync's prefix logic (kept in sync with
    ``_agenda_props_for_calendar_app`` / ``_ev_props_for_calendar_app``).
    """
    if kind == "event":
        return f"[{project_name}] {item['desc']}"
    emoji = _KIND_EMOJI.get(kind, "")
    if emoji:
        return f"[{project_name}] {emoji} {item['desc']}".rstrip()
    return f"[{project_name}] {item['desc']}"


def _expected_start_iso(item: dict, kind: str) -> str:
    """ISO ``YYYY-MM-DDTHH:MM`` the Calendar event should have."""
    d = item["date"]
    if kind == "event":
        t = item.get("time")
        if t:
            start = t.split("-")[0]
            return f"{d}T{start}"
        return f"{d}T00:00"  # all-day starts at 00:00
    # task/ms/rem/cronograma: default 09:00 when no time given
    t = item.get("time")
    start = (t.split("-")[0] if t and "-" in t else t) or "09:00"
    return f"{d}T{start}"


def _expected_end_iso(item: dict, kind: str) -> tuple:
    """Returns (end_iso, synthetic). ``synthetic=True`` means "this end is
    just ``start + 1 min`` (v0.29.9 trick) — diff should ignore it".

    Per kind:
      - event with time range HH:MM-HH:MM → real end
      - event all-day with `end:` → 23:59 on end_date (not synthetic)
      - event all-day no `end:` → 23:59 same day (not synthetic)
      - task/ms/rem/cronograma → start + 1 min, synthetic
    """
    start_iso = _expected_start_iso(item, kind)
    if kind == "event":
        t = item.get("time")
        d = item["date"]
        if t and "-" in t:
            end_part = t.split("-")[1]
            end_d = item.get("end") or d
            return f"{end_d}T{end_part}", False
        end_d = item.get("end") or d
        return f"{end_d}T23:59", False
    try:
        dt = datetime.fromisoformat(f"{start_iso}:00") + timedelta(minutes=1)
        return dt.strftime("%Y-%m-%dT%H:%M"), True
    except ValueError:
        return start_iso, True


def _expected_description(item: dict, project_dir: Path) -> str:
    """Build the body of the Calendar event description WITHOUT the
    ``[orbit:xxx]`` tag (which is appended elsewhere and excluded from
    the diff)."""
    from core.gsync import _project_description, _load_config, _item_description
    config = _load_config()
    base = _project_description(project_dir, config, html=False)
    return _item_description(item, base, html=False)


# ── Diff computation ────────────────────────────────────────────────────

def _norm_text(s: str) -> str:
    """Whitespace-trimmed compare for descriptions/summaries."""
    return (s or "").strip()


def _strip_orbit_tag(description: str) -> str:
    """Drop the trailing ``[orbit:xxx]`` (and ``[orbit:xxx@…]``) so the
    diff stays on user-visible content."""
    import re
    return re.sub(r"\s*\[orbit:[0-9a-f]{8}(?:@[^\]]*)?\]\s*$", "",
                  description or "").rstrip()


def _compute_diff(expected: dict, actual: dict,
                  ignore_end: bool) -> list:
    """Return a list of (attr, exp_val, act_val) for each drift.

    ``ignore_end=True`` skips ``end`` (synthetic ``start+1min`` for
    task/ms/rem/cronograma).
    """
    diffs = []
    if _norm_text(expected["summary"]) != _norm_text(actual["summary"]):
        diffs.append(("summary", expected["summary"], actual["summary"]))
    if expected["start_iso"] != (actual.get("start_iso") or ""):
        diffs.append(("start", expected["start_iso"], actual.get("start_iso") or ""))
    if not ignore_end:
        if expected["end_iso"] != (actual.get("end_iso") or ""):
            diffs.append(("end", expected["end_iso"], actual.get("end_iso") or ""))
    if (_norm_text(expected["description"])
            != _norm_text(_strip_orbit_tag(actual.get("description", "")))):
        diffs.append(("description",
                      expected["description"],
                      _strip_orbit_tag(actual.get("description", ""))))
    return diffs


# ── Collect orbit-side items per project ────────────────────────────────

def _collect_items(project_dir: Path,
                   type_filter: Optional[set] = None) -> list:
    """Return [(kind, item_dict, calendar_name)] for all selected kinds.

    ``calendar_name`` is the Calendar.app calendar each item belongs to —
    agenda calendar for task/rem, per-tipo events calendar for
    ms/ev/cronograma.
    """
    from core.gsync import (
        _load_config, _get_project_tipo, _agenda_calendar_name,
        _load_ids, _new_orbit_id,
    )
    config       = _load_config()
    tipo         = _get_project_tipo(project_dir)
    agenda_cal   = _agenda_calendar_name(config)
    events_cal   = (config.get("calendars", {}).get(tipo)
                    or config.get("calendars", {}).get("default"))
    out = []

    type_filter = type_filter or set(["task", "milestone", "event",
                                       "reminder", "cronograma"])

    if any(k in type_filter for k in ("task", "milestone",
                                       "event", "reminder")):
        data = _read_agenda(resolve_file(project_dir, "agenda"))
        for sect, kind, cal in [
            ("tasks",      "task",      agenda_cal),
            ("milestones", "milestone", events_cal),
            ("events",     "event",     events_cal),
            ("reminders",  "reminder",  agenda_cal),
        ]:
            if kind not in type_filter:
                continue
            if not cal:
                continue
            for it in data.get(sect, []):
                # Skip terminal states (Calendar should already not have
                # them after sync_item). They'd just look like "missing"
                # which isn't actionable.
                status = it.get("status")
                if status in ("done", "cancelled"):
                    continue
                if kind == "reminder" and it.get("cancelled"):
                    continue
                out.append((kind, it, cal))

    if "cronograma" in type_filter and events_cal:
        out.extend(_collect_cronos(project_dir, events_cal))

    return out


def _collect_cronos(project_dir: Path, cal_name: str) -> list:
    """Yield synthesized item dicts for each cronograma (mirrors
    gsync._sync_cronos_for_project's item construction)."""
    cronos_dir = project_dir / "cronos"
    if not cronos_dir.exists():
        return []
    files = sorted(cronos_dir.glob("crono-*.md"))
    if not files:
        return []

    from core.cronograma import (_parse_crono_file, _compute_dates,
                                 next_open_leaf, cronograma_all_done,
                                 _leaf_deadline)
    from core.gsync import _load_ids

    ids = _load_ids(project_dir)
    cronos_ids = ids.get("_cronos", {})
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
        ex = cronos_ids.get(name) or {}
        item = {
            "desc":      f"crono-{name}: {leaf['title']}",
            "date":      _leaf_deadline(leaf).isoformat(),
            "time":      None,
            "notes":     [f"Cronograma: cronos/{path.name}"],
            "orbit_id":  ex.get("orbit_id"),
            "_crono_name": name,        # for downstream lookup
        }
        out.append(("cronograma", item, cal_name))
    return out


# ── UI: table render + per-attribute prompt ─────────────────────────────

def _truncate(s: str, n: int) -> str:
    s = s or ""
    if len(s) <= n:
        return s
    return s[: n - 1] + "…"


def _print_diff_table(label: str, orbit_id: Optional[str],
                      diffs: list) -> None:
    print(f"\n─ {label}" + (f"  [orbit:{orbit_id}]" if orbit_id else ""))
    width = 50
    print(f"  ┌──────────────┬{'─' * (width + 2)}┬{'─' * (width + 2)}┐")
    print(f"  │ {'attr':<12} │ {'orbit':<{width}} │ {'calendar':<{width}} │")
    print(f"  ├──────────────┼{'─' * (width + 2)}┼{'─' * (width + 2)}┤")
    for attr, o, c in diffs:
        print(f"  │ {attr:<12} │ {_truncate(o, width):<{width}} │"
              f" {_truncate(c, width):<{width}} │")
    print(f"  └──────────────┴{'─' * (width + 2)}┴{'─' * (width + 2)}┘")


def _prompt(attr: str, orbit_val: str, cal_val: str,
            allow_pull: bool, end_synthetic: bool) -> tuple:
    """Ask the user how to resolve drift on a single attribute.

    Returns ``(action, value)`` where ``action`` ∈
    ``"push" | "adopt" | "input" | "skip"``. ``value`` carries the new
    string for "adopt"/"input" (None otherwise).
    """
    opts = ["1-orbit"]
    if allow_pull and not (attr == "end" and end_synthetic):
        opts.append("2-cal")
    opts.extend(["3-input", "s-skip"])
    prompt = f"  {attr}: [{' / '.join(opts)}] ? "
    try:
        choice = input(prompt).strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        return ("skip", None)
    if choice in ("1", "1-orbit", "orbit"):
        return ("push", None)
    if choice in ("2", "2-cal", "cal") and "2-cal" in opts:
        return ("adopt", cal_val)
    if choice in ("3", "3-input", "input"):
        try:
            new = input(f"  {attr} (nuevo valor): ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return ("skip", None)
        return ("input", new) if new else ("skip", None)
    return ("skip", None)


# ── Apply resolutions to agenda.md (the "pull" side) ────────────────────

_PROJECT_PREFIX_RE = None  # built lazily; depends on project name


def _strip_summary_prefix(summary: str, project_name: str,
                          kind: str) -> str:
    """Reverse of ``_expected_summary``: peel the ``[project] <emoji>``
    prefix off a Calendar summary so the resulting string maps cleanly
    to an orbit ``desc``."""
    import re
    expected = re.escape(f"[{project_name}] ")
    emoji    = _KIND_EMOJI.get(kind, "")
    if kind != "event" and emoji:
        pattern = rf"^{expected}{re.escape(emoji)}\s*"
    else:
        pattern = rf"^{expected}"
    return re.sub(pattern, "", summary or "").strip()


def _split_iso(iso: str) -> tuple:
    """``YYYY-MM-DDTHH:MM`` → (date, HH:MM) or (date, None) if missing."""
    if not iso:
        return None, None
    if "T" in iso:
        d, t = iso.split("T", 1)
        return d, t
    return iso, None


def _apply_pull(project_dir: Path, kind: str, orbit_id: str,
                attr: str, new_value: str, project_name: str) -> bool:
    """Mutate the agenda line carrying ``orbit_id`` so that ``attr``
    equals ``new_value`` (which came from Calendar or from the user).

    Returns True on success (agenda was touched).

    Cronograms are *not* mutated here — their source is the structured
    crono file, not ``agenda.md``. The caller filters them out.
    """
    if kind == "cronograma":
        return False

    agenda_path = resolve_file(project_dir, "agenda")
    if not agenda_path.exists():
        return False
    data = _read_agenda(agenda_path)
    section = {
        "task":      "tasks",
        "milestone": "milestones",
        "event":     "events",
        "reminder":  "reminders",
    }[kind]
    target = None
    for it in data.get(section, []):
        if it.get("orbit_id") == orbit_id:
            target = it
            break
    if target is None:
        return False

    if attr == "summary":
        target["desc"] = _strip_summary_prefix(new_value, project_name, kind)
    elif attr == "start":
        d, t = _split_iso(new_value)
        if d:
            target["date"] = d
        if kind == "event":
            old_time = target.get("time") or ""
            new_start = t
            # Preserve end portion if user already had HH:MM-HH:MM
            if old_time and "-" in old_time and new_start:
                _, end_part = old_time.split("-", 1)
                target["time"] = f"{new_start}-{end_part}"
            elif new_start:
                target["time"] = new_start
        else:
            target["time"] = t if t and t != "09:00" else target.get("time")
            if t and t != "09:00":
                target["time"] = t
    elif attr == "end":
        d, t = _split_iso(new_value)
        if kind == "event":
            old_time = target.get("time") or ""
            if old_time and "-" in old_time and t:
                start_part = old_time.split("-", 1)[0]
                target["time"] = f"{start_part}-{t}"
            elif d:
                target["end"] = d
        # For task/ms/rem the end is synthetic — calling here is a no-op
        # by design (the prompt blocks 2-cal for synthetic ends).
    elif attr == "description":
        # Replace notes (project line "Proyecto: …" stays implicit — the
        # description we wrote never contains it twice, so we keep the
        # cleaned notes split by newline).
        from core.gsync import _project_description, _load_config
        config = _load_config()
        base = _project_description(project_dir, config, html=False)
        body = (new_value or "").strip()
        if body.endswith(base):
            body = body[: -len(base)].rstrip()
        notes = [ln for ln in body.split("\n") if ln.strip()]
        target["notes"] = notes
    else:
        return False

    target["cloud_verified"] = False
    _write_agenda(agenda_path, data)
    return True


# ── Orchestration ───────────────────────────────────────────────────────

def _parse_type_filter(raw: Optional[str]) -> set:
    """Comma-separated CLI types → set of internal kinds."""
    if not raw:
        return {"task", "milestone", "event", "reminder", "cronograma"}
    out = set()
    for tok in raw.split(","):
        tok = tok.strip().lower()
        if not tok:
            continue
        if tok in _TYPE_ALIASES:
            out.add(_TYPE_ALIASES[tok])
        else:
            print(f"⚠️  tipo desconocido: {tok!r} (válidos: {', '.join(ALL_TYPES)})")
    return out


def _resolve_project(name: str) -> Optional[Path]:
    """Find a project by partial name match across all type dirs."""
    matches = [d for d in iter_project_dirs() if name.lower() in d.name.lower()]
    if not matches:
        print(f"Error: no project found matching '{name}'")
        return None
    if len(matches) == 1:
        return matches[0]
    print(f"Múltiples proyectos coinciden con '{name}':")
    for i, m in enumerate(matches, 1):
        print(f"  {i}. {m.name}")
    if not sys.stdin.isatty():
        return None
    try:
        raw = input("Selecciona (#): ").strip()
        idx = int(raw) - 1
        if 0 <= idx < len(matches):
            return matches[idx]
    except (ValueError, EOFError, KeyboardInterrupt):
        print()
    print("Selección no válida.")
    return None


def run_calsync(project: Optional[str],
                type_filter: Optional[str] = None,
                all_flag: bool = False,
                pending_flag: bool = False,
                dry_run: bool = False) -> int:
    """Entry point for ``orbit calsync``.

    Modes (mutually exclusive default behaviour, ``all`` and ``pending``
    are mutually exclusive too):
      - default: skip ☁️-verified items
      - --all:   include ☁️-verified items
      - --pending: only items with orbit-id but no ☁️ marker

    DORMANT since v0.33 unless ``applescript_writes: true`` in
    calendar-sync.json. With AppleScript writes off, the orbit-managed
    calendars are drift-free by construction (.ics regenerated each
    render from agenda.md). Reactivate the flag only if you switch
    back to the legacy AppleScript-write path.
    """
    if all_flag and pending_flag:
        print("Error: --all y --pending son mutuamente exclusivos.")
        return 2

    if not project:
        print("Uso: orbit calsync <proyecto> [--type LIST] [--all|--pending] [--dry-run]")
        return 2

    from core.gsync import _applescript_writes_enabled
    if not _applescript_writes_enabled():
        print("ℹ️  calsync deprecated (v0.33). Orbit-managed calendars son drift-free")
        print("   por construcción ahora — .ics se regenera desde agenda.md en cada")
        print("   render. No hay drift que auditar.")
        print("   Para revivir: pon \"applescript_writes\": true en calendar-sync.json.")
        return 0
    project_dir = _resolve_project(project)
    if project_dir is None:
        return 1

    from core.gsync import _calendar_app_running
    if not _calendar_app_running():
        print("⚠️  Calendar.app no está corriendo. Ábrelo y reintenta.")
        return 1

    type_set = _parse_type_filter(type_filter)
    if not type_set:
        return 2

    items = _collect_items(project_dir, type_set)

    # Mode filtering: ☁️ verified vs pending.
    if pending_flag:
        items = [(k, it, c) for (k, it, c) in items
                 if it.get("orbit_id") and not it.get("cloud_verified")]
    elif not all_flag:
        items = [(k, it, c) for (k, it, c) in items
                 if not it.get("cloud_verified")]

    if not items:
        print("✓ Nada que auditar — todo verificado ☁️ "
              "(o filtros sin match). Usa --all para forzar.")
        return 0

    # Cache: one bulk-read per distinct calendar.
    window_start = _date.today() - timedelta(days=30)
    window_end   = _date.today() + timedelta(days=365)
    cache: dict[str, list] = {}
    matched_uids_per_cal: dict[str, set] = {}
    for cal in {c for (_, _, c) in items if c}:
        cache[cal] = _fetch_window(cal, window_start, window_end)
        matched_uids_per_cal[cal] = set()

    project_name = project_dir.name
    stats = {"verified": 0, "fixed": 0, "skipped": 0, "missing": 0,
             "errors": 0}

    for kind, item, cal in items:
        oid = item.get("orbit_id")
        label = f"{_KIND_EMOJI.get(kind,'?')} {item.get('desc','')} "\
                f"({item.get('date','?')})"

        if not oid:
            print(f"\n─ {label}")
            print("  (sin orbit-id — sync_item nunca tocó esta cita. "
                  "Edita en orbit para forzar push.)")
            stats["skipped"] += 1
            continue

        events = cache.get(cal, [])
        actual = next((e for e in events if e.get("orbit_id") == oid), None)

        if actual is None:
            print(f"\n─ {label}  [orbit:{oid}]")
            print(f"  ⚠️  No existe en Calendar «{cal}». "
                  f"Push para crearlo? [1-orbit / s-skip] ", end="")
            try:
                choice = input().strip().lower()
            except (EOFError, KeyboardInterrupt):
                print(); choice = "s"
            if choice in ("1", "1-orbit", "orbit"):
                if dry_run:
                    print("  (dry-run) crearía evento.")
                else:
                    _do_push(project_dir, item, kind)
                stats["fixed"] += 1
            else:
                stats["missing"] += 1
            continue

        matched_uids_per_cal.setdefault(cal, set()).add(actual["uid"])

        # Build expected props.
        expected = {
            "summary":     _expected_summary(item, kind, project_name),
            "start_iso":   _expected_start_iso(item, kind),
            "description": _expected_description(item, project_dir),
        }
        end_iso, end_synth = _expected_end_iso(item, kind)
        expected["end_iso"] = end_iso
        # If actual end matches start+1min, the calendar render is also
        # synthetic → ignore the end diff to avoid noise.
        cal_synth_end = False
        if actual.get("start_iso") and actual.get("end_iso"):
            try:
                s_dt = datetime.fromisoformat(actual["start_iso"] + ":00"
                                              if actual["start_iso"].count(":") == 1
                                              else actual["start_iso"])
                e_dt = datetime.fromisoformat(actual["end_iso"] + ":00"
                                              if actual["end_iso"].count(":") == 1
                                              else actual["end_iso"])
                cal_synth_end = (e_dt - s_dt) == timedelta(minutes=1)
            except ValueError:
                pass

        diffs = _compute_diff(expected, actual,
                              ignore_end=(end_synth or cal_synth_end))
        if not diffs:
            stats["verified"] += 1
            continue

        _print_diff_table(label, oid, diffs)
        any_fixed = False
        for attr, exp_val, act_val in diffs:
            allow_pull = (kind != "cronograma")  # crono: no pull
            action, value = _prompt(attr, exp_val, act_val,
                                    allow_pull=allow_pull,
                                    end_synthetic=end_synth)
            if dry_run:
                print(f"  (dry-run) {attr}: {action} {value or ''}")
                if action != "skip":
                    any_fixed = True
                continue
            if action == "skip":
                continue
            if action == "push":
                _do_push(project_dir, item, kind)
                any_fixed = True
            elif action in ("adopt", "input"):
                if kind == "cronograma":
                    print("  (cronogramas: solo push; edita el crono "
                          "para cambiar la verdad).")
                    continue
                ok = _apply_pull(project_dir, kind, oid, attr, value,
                                 project_name)
                if not ok:
                    print(f"  ⚠️  No pude aplicar el cambio a {attr}.")
                    stats["errors"] += 1
                    continue
                # Re-read item from disk so subsequent push uses the new
                # values across all attrs.
                fresh = _refetch_item(project_dir, kind, oid)
                if fresh is not None:
                    item = fresh
                _do_push(project_dir, item, kind)
                any_fixed = True
        if any_fixed:
            stats["fixed"] += 1
        else:
            stats["skipped"] += 1

    # Orphan report.
    orphans_total = 0
    for cal, events in cache.items():
        matched = matched_uids_per_cal.get(cal, set())
        orphans = [e for e in events if e["uid"] not in matched
                   and not e.get("orbit_id")]
        if not orphans:
            continue
        if orphans_total == 0:
            print("\n─ Huérfanos en Calendar (sin orbit-id):")
        for o in orphans:
            print(f"  • [{cal}] {o['start_iso'] or '?'}  {o['summary']}")
            orphans_total += 1
    if orphans_total:
        print(f"\n  ({orphans_total} huérfano(s). Sin auto-import — "
              f"créalos en orbit con `ev add` si quieres adoptarlos.)")

    # Summary.
    print(f"\nResumen: {stats['verified']} ☁️ / {stats['fixed']} corregidos / "
          f"{stats['skipped']} skipped / {stats['missing']} ausentes / "
          f"{stats['errors']} errores / {orphans_total} huérfanos")
    return 0


def _do_push(project_dir: Path, item: dict, kind: str) -> None:
    """Force a single-item push (sync_item) bypassing the snapshot
    short-circuit — this is the "1-orbit" action."""
    from core.gsync import sync_item
    sync_item(project_dir, item, kind=kind)


def _refetch_item(project_dir: Path, kind: str, orbit_id: str) -> Optional[dict]:
    """Re-load the item from agenda.md after a pull mutated it."""
    if kind == "cronograma":
        return None
    data = _read_agenda(resolve_file(project_dir, "agenda"))
    section = {"task": "tasks", "milestone": "milestones",
               "event": "events", "reminder": "reminders"}[kind]
    for it in data.get(section, []):
        if it.get("orbit_id") == orbit_id:
            return it
    return None

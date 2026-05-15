"""display — interactive selection helpers and event-metadata accessors.

Holds:
  * The four ``_display_*`` line-renderers.
  * :func:`_select_from_list` and its three thin wrappers
    (:func:`_select_item`, :func:`_select_event`, :func:`_select_item_reminder`).
  * Event-metadata helpers (rooms / agenda URLs / source-emails) plus the
    :data:`_STRUCTURED_PREFIXES` constants used by ``--desc`` editing.
"""
from __future__ import annotations

import sys
from typing import Optional


# Note prefixes for structured event metadata. Lines indented under an event
# starting with one of these emojis are treated as typed fields by orbit
# (📋 agenda/indico, 🚪 room/zoom, ✉️ source email) and preserved across
# `--desc` edits.
_AGENDA_NOTE_PREFIX = "📋 "
_ROOM_NOTE_PREFIX   = "🚪 "
_EMAIL_NOTE_PREFIX  = "✉️ "
_STRUCTURED_PREFIXES = (_AGENDA_NOTE_PREFIX, _ROOM_NOTE_PREFIX, _EMAIL_NOTE_PREFIX)


# ── Event metadata helpers ────────────────────────────────────────────────

def _is_meeting_url(s: str) -> bool:
    s = (s or "").strip()
    return s.startswith("http://") or s.startswith("https://")


def _room_icon(value: str) -> str:
    """📹 for videoconference URLs, 🚪 for physical rooms / plain text."""
    return "📹" if _is_meeting_url(value) else "🚪"


def event_room_urls(item: dict) -> list:
    """Return list of room URLs (🚪) attached to an event item."""
    return [n[len(_ROOM_NOTE_PREFIX):] for n in (item.get("notes") or [])
            if n.startswith(_ROOM_NOTE_PREFIX)]


def event_agenda_urls(item: dict) -> list:
    """Return list of agenda URLs (📋) attached to an event item."""
    return [n[len(_AGENDA_NOTE_PREFIX):] for n in (item.get("notes") or [])
            if n.startswith(_AGENDA_NOTE_PREFIX)]


def event_email_urls(item: dict) -> list:
    """Return list of source-email URLs (✉️) attached to an event item.

    Populated by `orbit email <proj> --ev`: the originating message URL
    (typically ``message://<Message-ID>`` for Apple Mail captures).
    """
    return [n[len(_EMAIL_NOTE_PREFIX):] for n in (item.get("notes") or [])
            if n.startswith(_EMAIL_NOTE_PREFIX)]


def event_indicators(item: dict, markdown: bool = False) -> str:
    """Return a leading-space suffix flagging room/agenda/email presence.

    Room icon adapts to its content: 📹 for URLs (videoconference, like
    Calendar.app), 🚪 for physical rooms or other plain text.

    - markdown=False  → ' 📹 🚪 📋 ✉️'              (one icon per item)
    - markdown=True   → ' [📹](url) [🚪](room) [📋](url) [✉️](msg-url)'

    Returns empty string if no structured notes.
    """
    rooms = event_room_urls(item)
    agendas = event_agenda_urls(item)
    emails = event_email_urls(item)
    if not rooms and not agendas and not emails:
        return ""
    parts = []
    if markdown:
        for u in rooms:
            parts.append(f"[{_room_icon(u)}]({u})")
        for u in agendas:
            parts.append(f"[📋]({u})")
        for u in emails:
            parts.append(f"[✉️]({u})")
    else:
        for r in rooms:
            parts.append(_room_icon(r))
        if agendas:
            parts.append("📋")
        if emails:
            parts.append("✉️")
    return " " + " ".join(parts)


# ── Line displays ─────────────────────────────────────────────────────────

def _display_task(t: dict) -> str:
    date_s = f" ({t['date']})" if t.get("date") else ""
    return f"{t['desc']}{date_s}"


def _display_event(e: dict) -> str:
    end_s = f" → {e['end']}" if e.get("end") else ""
    return f"{e['date']} — {e['desc']}{end_s}"


def _display_reminder(r: dict) -> str:
    return f"{r['desc']} ({r['date']}) ⏰{r['time']}"


# ── Interactive selection ─────────────────────────────────────────────────

def _select_from_list(items: list, label: str, text: Optional[str],
                      display_fn, filter_fn=None,
                      match_fn=None) -> Optional[int]:
    """Generic interactive selection. Returns index in original *items* list.

    filter_fn(item) → bool: which items are selectable (default: all).
    display_fn(item) → str: how to display each item.
    match_fn(item, text) → bool: how to match text (default: case-insensitive substring on desc).
    """
    if filter_fn:
        sel_idx = [i for i, t in enumerate(items) if filter_fn(t)]
    else:
        sel_idx = list(range(len(items)))
    sel = [items[i] for i in sel_idx]

    if match_fn is None:
        match_fn = lambda item, txt: txt.lower() in item["desc"].lower()

    def _pick_from_matches(matches):
        """Show numbered list for ambiguous matches, return selected index or None."""
        print(f"Múltiples coincidencias{f' para {chr(39)}{text}{chr(39)}' if text else ''}:")
        for j, mi in enumerate(matches, 1):
            print(f"  {j}. {display_fn(sel[mi])}")
        if not sys.stdin.isatty():
            return None
        try:
            raw = input("Selecciona (#): ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return None
        if raw.isdigit():
            idx = int(raw) - 1
            if 0 <= idx < len(matches):
                return sel_idx[matches[idx]]
        print("Cancelado.")
        return None

    if text:
        matches = [i for i, t in enumerate(sel) if match_fn(t, text)]
        if not matches:
            print(f"Error: no se encontró '{text}'")
            return None
        if len(matches) == 1:
            return sel_idx[matches[0]]
        return _pick_from_matches(matches)

    if not sel:
        print(f"No hay {label}.")
        return None

    print(f"\n{label}:")
    for i, t in enumerate(sel, 1):
        print(f"  {i}. {display_fn(t)}")
    print()

    if not sys.stdin.isatty():
        return None

    try:
        raw = input("Selecciona (número o texto parcial): ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return None

    if not raw:
        return None
    if raw.isdigit():
        idx = int(raw) - 1
        if 0 <= idx < len(sel):
            return sel_idx[idx]
        print(f"Fuera de rango (1–{len(sel)})")
        return None
    matches = [i for i, t in enumerate(sel) if match_fn(t, raw)]
    if not matches:
        print(f"Sin coincidencias para '{raw}'")
        return None
    if len(matches) == 1:
        return sel_idx[matches[0]]
    return _pick_from_matches(matches)


def _select_item(items: list, label: str, text: Optional[str] = None) -> Optional[int]:
    """Select a pending task or milestone by text or interactive list."""
    return _select_from_list(items, label, text,
                             display_fn=_display_task,
                             filter_fn=lambda t: t["status"] == "pending")


def _select_event(events: list, text: Optional[str]) -> Optional[int]:
    """Select an event by text or interactive list."""
    return _select_from_list(events, "Eventos", text,
                             display_fn=_display_event)


def _select_item_reminder(items: list, text: Optional[str]) -> Optional[int]:
    """Select a reminder by partial match or interactive list."""
    from core.config import normalize
    return _select_from_list(
        items, "Recordatorios", text,
        display_fn=_display_reminder,
        match_fn=lambda r, txt: normalize(txt) in normalize(r["desc"]))

"""newfmt — experimental serializer for the unified "orbit-item" syntax.

Reads the SAME parsed model as :mod:`core.agenda.io` (``_read_agenda``) and
emits the new *header + indented-body* grammar of the unified item design
(``claude/designs/items_unified.md``, refined §0.5).

This is a **viewer stage**: the truth stays in ``agenda.md``. The output is a
derived ``agenda_futura.md`` so the new look can be eyeballed on real data
before the writer/parser adopt it. Nothing here writes truth.

Header shapes (checkbox = state, emoji = type). Task uses ✏️ (not ✅, which
reads as "done" next to an empty checkbox):

    task      - [ ] ✏️ título #tarea
    milestone - [ ] 🏁 título #hitos
    event     - 📅 título #evento
    reminder  - 💬 título #recordatorio     (- [-] … if cancelled)

Body (indented ≥4 spaces here, ≥2 in the grammar), canonical order
temporal → desc → refs → followups:

    ▶️ FECHA[ : FIN] · ⏰ HH:MM[-HH:MM] · 🔄 recur[ : until] · 🔔 ring
    <líneas libres / desc>
    links: [📋](url) [📹](url) [✉️](url)
    ⏩ FECHA [tema]

Conversion notes (from the current model):
  * There is no separate title/desc today → the current ``desc`` becomes the
    header title; no ``desc:`` line is synthesized.
  * The current data carries no tags → the primary tag is synthesized per
    type (``_PRIMARY_TAG``); event's primary is free-form in the design, so
    ``#evento`` is a placeholder.
  * The header ``ff`` field is folded into a body followup ``⏩ FECHA`` (the
    old ``ff`` had no theme, so none is emitted); ``ff: someday`` becomes a
    someday item by *absence* of a temporal line.
  * ``snooze_count`` / ``failed_count`` are discipline metadata, not part of
    the grammar → dropped.
"""
from __future__ import annotations

from typing import Optional

from core.agenda.display import event_indicators, item_followups


# Type emoji per kind. Task uses ✏️ ("acción a hacer") — not ✅, which reads
# as "done" next to an empty checkbox; the checkbox stays as the state marker.
_TYPE_EMOJI = {
    "task": "✏️", "milestone": "🏁", "event": "📅", "reminder": "💬",
}
_PRIMARY_TAG = {
    "task": "#tarea", "milestone": "#hitos",
    "event": "#evento", "reminder": "#recordatorio",
}
_STATUS_CHAR = {"pending": " ", "done": "x", "cancelled": "-"}

# (model kind, _read_agenda key), in truth-order.
_KINDS = [
    ("task", "tasks"), ("milestone", "milestones"),
    ("event", "events"), ("reminder", "reminders"),
]


def _temporal_line(item: dict) -> Optional[str]:
    """Build the temporal-line tokens, or None if the item has no anchor.

    Absence of this line = someday item (design §2.9).
    """
    tokens = []
    date_val = item.get("date")
    if date_val:
        end = item.get("end")   # only events carry a range end
        tokens.append(f"▶️ {date_val} : {end}" if end else f"▶️ {date_val}")
    if item.get("time"):
        tokens.append(f"⏰ {item['time']}")
    if item.get("recur"):
        rec = item["recur"]
        if item.get("until"):
            rec += f" : {item['until']}"
        tokens.append(f"🔄 {rec}")
    if item.get("ring"):
        tokens.append(f"🔔 {item['ring']}")
    return " · ".join(tokens) if tokens else None


def _header(kind: str, item: dict) -> str:
    """Render the single-line header (bullet + state + type-emoji + title + tag)."""
    tag   = _PRIMARY_TAG[kind]
    title = (item.get("desc") or "").strip()
    if kind == "task":
        char = _STATUS_CHAR.get(item.get("status", "pending"), " ")
        return f"- [{char}] {_TYPE_EMOJI[kind]} {title} {tag}"
    if kind == "milestone":
        char = _STATUS_CHAR.get(item.get("status", "pending"), " ")
        return f"- [{char}] {_TYPE_EMOJI[kind]} {title} {tag}"
    if kind == "reminder":
        prefix = "- [-] " if item.get("cancelled") else "- "
        return f"{prefix}{_TYPE_EMOJI[kind]} {title} {tag}"
    return f"- {_TYPE_EMOJI[kind]} {title} {tag}"  # event: no checkbox


def _body_lines(item: dict) -> list:
    """Body lines in canonical order: temporal → free/desc → refs → followups."""
    lines = []

    tl = _temporal_line(item)
    if tl:
        lines.append(tl)

    # Free / desc notes: everything that isn't a structured ref or a followup.
    for n in item.get("notes") or []:
        if n.startswith(("📋", "🚪", "✉️", "⏩")):
            continue
        lines.append(n)

    # Refs: reuse the markdown indicator builder (📹/🚪 rooms, 📋 agendas, ✉️ emails).
    refs = event_indicators(item, markdown=True).strip()
    if refs:
        lines.append(f"links: {refs}")

    # Followups already living in the body (⏩ DATE [desc]).
    seen_dates = set()
    for fu in item_followups(item):
        seen_dates.add(fu["date"])
        line = f"⏩ {fu['date']}"
        if fu.get("desc"):
            line += f" {fu['desc']}"
        lines.append(line)

    # Header ff → followup (design §0.5). someday = no line at all.
    ff = item.get("ff")
    if ff and ff != "someday" and ff not in seen_dates:
        lines.append(f"⏩ {ff}")

    return lines


def format_item_new(kind: str, item: dict, *, indent: str = "    ",
                    with_id: bool = False) -> str:
    """Render one item as ``header`` + indented ``body``.

    ``with_id`` appends the invisible ``<!-- orbit:xxxx -->`` identity comment
    to the header (design §2.5 / §9.2). The truth writer needs it (sync keys
    off orbit_id); the viewer keeps it off for a clean look.
    """
    header = _header(kind, item)
    if with_id and item.get("orbit_id"):
        header += f" <!-- orbit:{item['orbit_id']} -->"
    out = [header]
    out.extend(f"{indent}{bl}" for bl in _body_lines(item))
    return "\n".join(out)


def serialize_agenda_new(data: dict, *, with_id: bool = False) -> str:
    """Serialize a parsed agenda dict (``_read_agenda``) to the new flat format.

    Sections disappear from the truth (design §1): the output is the file
    header followed by a flat, blank-line-separated list of items, grouped in
    truth-order (tasks, milestones, events, reminders). The auto-generated
    ``## 📊 Cronogramas`` block is a derived view, not an item → skipped here.
    """
    out = [h for h in data.get("header", []) if h.strip()]
    if out:
        out.append("")   # blank between header and first item (none if no header)
    for kind, key in _KINDS:
        for item in data.get(key, []):
            out.append(format_item_new(kind, item, with_id=with_id))
            out.append("")
    return "\n".join(out).rstrip() + "\n"


# ── Parser (new format → model) ────────────────────────────────────────────
#
# Inverse of the serializer above. Produces item dicts shaped like
# ``core.agenda.io._read_agenda`` so downstream code (writers, views, the
# round-trip check) sees the same model regardless of on-disk syntax.

import re

_HEADER_RE = re.compile(r"^- (?:\[( |x|-)\] )?(?:(✏️|🏁|📅|💬) )?(.*)$")
_ID_COMMENT_RE = re.compile(r"\s*<!-- orbit:([0-9a-f]{8}) -->\s*$")
_TAG_RE    = re.compile(r"#\S+")
_LINK_RE   = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
_STATUS_FROM_CHAR = {" ": "pending", "x": "done", "-": "cancelled"}
# markdown link emoji → structured note prefix (📹 is the URL-room display icon)
_LINK_EMOJI_TO_PREFIX = {"📋": "📋", "🚪": "🚪", "📹": "🚪", "✉️": "✉️"}


def _split_title_tags(rest: str) -> tuple:
    """Split ``título #a #b`` → (title, [tags]). Trailing #tokens are tags."""
    words = rest.split()
    tags = []
    while words and words[-1].startswith("#"):
        tags.insert(0, words.pop())
    return " ".join(words), tags


def _parse_temporal(line: str) -> dict:
    """Parse a temporal-line (``▶️ … · ⏰ … · 🔄 … · 🔔 …``) → field dict."""
    fields = {"date": None, "end": None, "time": None,
              "recur": None, "until": None, "ring": None}
    for tok in line.split(" · "):
        tok = tok.strip()
        if tok.startswith("▶️"):
            val = tok[len("▶️"):].strip()
            if " : " in val:
                fields["date"], fields["end"] = [s.strip() for s in val.split(" : ", 1)]
            else:
                fields["date"] = val
        elif tok.startswith("⏰"):
            fields["time"] = tok[len("⏰"):].strip()
        elif tok.startswith("🔄"):
            val = tok[len("🔄"):].strip()
            if " : " in val:
                fields["recur"], fields["until"] = [s.strip() for s in val.split(" : ", 1)]
            else:
                fields["recur"] = val
        elif tok.startswith("🔔"):
            fields["ring"] = tok[len("🔔"):].strip()
    return fields


def _is_temporal(line: str) -> bool:
    return line.startswith("▶️") or line.startswith("⏰")


def parse_item_new(header: str, body: list) -> tuple:
    """Parse one item (header line + list of dedented body lines) → (kind, dict).

    Returns ``(None, None)`` if the header doesn't match the grammar.
    """
    # Pull the invisible identity comment off the tail before matching.
    id_m = _ID_COMMENT_RE.search(header)
    orbit_id = id_m.group(1) if id_m else None
    if id_m:
        header = header[:id_m.start()].rstrip()

    m = _HEADER_RE.match(header)
    if not m:
        return (None, None)
    state_char, emoji, rest = m.group(1), m.group(2), m.group(3)
    title, _tags = _split_title_tags(rest)

    if emoji == "🏁":
        kind = "milestone"
    elif emoji == "📅":
        kind = "event"
    elif emoji == "💬":
        kind = "reminder"
    else:                       # ✏️ or no emoji (legacy) → task
        kind = "task"

    # Build a dict shaped exactly like the old-model items (io._parse_*), so
    # downstream code can't tell which parser produced it. Fields the new
    # grammar dropped (ff/snooze/failed) default to their empty values; ff is
    # None because it now lives as a ⏩ followup in notes, never in the header.
    item = {"desc": title, "date": None, "time": None,
            "recur": None, "until": None, "orbit_id": orbit_id,
            "cloud_verified": False, "notes": []}
    if kind in ("task", "milestone"):
        item["status"] = _STATUS_FROM_CHAR.get(state_char, "pending")
        item["ring"] = None
        item["ff"] = None
        item["snooze_count"] = 0
        item["failed_count"] = 0
    elif kind == "event":
        item["end"] = None
        item["ring"] = None
    elif kind == "reminder":
        item["cancelled"] = (state_char == "-")
        item["ff"] = None
        item["snooze_count"] = 0
        item["failed_count"] = 0

    for raw in body:
        line = raw.strip()
        if not line:
            continue
        if _is_temporal(line):
            fields = _parse_temporal(line)
            for k, v in fields.items():
                if v is not None and k in item:
                    item[k] = v
        elif line.startswith("links:"):
            for label, url in _LINK_RE.findall(line):
                prefix = _LINK_EMOJI_TO_PREFIX.get(label.strip())
                if prefix:
                    item["notes"].append(f"{prefix} {url}")
        else:
            # followups (⏩ …) and free lines both live verbatim in notes
            item["notes"].append(line)

    return (kind, item)


def parse_agenda_new(text: str) -> dict:
    """Parse a whole new-format agenda → the ``_read_agenda`` model dict."""
    data = {"header": [], "tasks": [], "milestones": [],
            "events": [], "reminders": [], "cronos": []}
    key_for = {"task": "tasks", "milestone": "milestones",
               "event": "events", "reminder": "reminders"}

    lines = text.splitlines()
    i = 0
    # Header = everything before the first item bullet.
    while i < len(lines) and not lines[i].startswith("- "):
        if lines[i].strip():
            data["header"].append(lines[i])
        i += 1

    while i < len(lines):
        line = lines[i]
        if not line.startswith("- "):
            i += 1
            continue
        header = line
        body = []
        i += 1
        while i < len(lines) and (lines[i].startswith("    ") or lines[i].startswith("\t")):
            body.append(lines[i])
            i += 1
        kind, item = parse_item_new(header, body)
        if kind:
            data[key_for[kind]].append(item)
    return data

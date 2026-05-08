"""email.py — capture an email into a project note + logbook entry.

Backends:
  - eml:     parse a .eml file exported from any client (recommended)
  - outlook: AppleScript to Microsoft Outlook for Mac (selected message)
  - mail:    AppleScript to Apple Mail.app           (selected message)
  - gmail:   Chrome active tab URL → Gmail API        — pending

Each captured email writes:
  - notes/emails/YYYY-MM-DD-<slug>.md  (note with frontmatter + body)
  - one logbook entry with double link:
      [Email: <subject>](./notes/emails/...md) ✉️ [original](message://<id>)
      tagged #referencia #email [O]
"""

import email as _stdlib_email
import email.policy as _email_policy
import html as _html_mod
import json
import re
import subprocess
import sys
import unicodedata
from datetime import date as _date
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Optional

from core.config import ORBIT_HOME
from core.log import add_orbit_entry, find_project


# ── Source detection ──────────────────────────────────────────────────────────

_VALID_DEFAULT_SOURCES = ("mail", "outlook", "gmail")


def _default_source() -> str:
    """Detect email backend.

    Resolution order:
      1. orbit.json `email_source` field (must be one of mail|outlook|gmail)
      2. orbit.json `cartero.gmail` set → gmail
      3. fallback → outlook
    """
    cfg = {}
    try:
        cfg = json.loads((ORBIT_HOME / "orbit.json").read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return "outlook"
    explicit = cfg.get("email_source")
    if explicit in _VALID_DEFAULT_SOURCES:
        return explicit
    if explicit:
        sys.stderr.write(
            f"orbit.json: email_source '{explicit}' inválido "
            f"(usa uno de {', '.join(_VALID_DEFAULT_SOURCES)}); "
            f"aplicando fallback.\n"
        )
    if "gmail" in cfg.get("cartero", {}):
        return "gmail"
    return "outlook"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _slugify(text: str, maxlen: int = 50) -> str:
    """ASCII-safe slug for filenames."""
    text = unicodedata.normalize("NFD", text).encode("ascii", "ignore").decode().lower()
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return text[:maxlen] or "email"


def _osascript(script: str, timeout: int = 20) -> Optional[str]:
    """Run osascript; return stdout or None on error."""
    try:
        r = subprocess.run(["osascript", "-e", script],
                           capture_output=True, text=True, timeout=timeout)
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        sys.stderr.write(f"osascript: {e}\n")
        return None
    if r.returncode != 0:
        sys.stderr.write(f"osascript error: {r.stderr.strip()}\n")
        return None
    return r.stdout


# ── Mac backends ──────────────────────────────────────────────────────────────

# Body is written to a tmp file by AppleScript and read back here, so large
# bodies and binary-ish content survive the osascript boundary cleanly.
_MAC_BODY_PATH    = "/tmp/orbit-mail-body.txt"
_MAC_HEADERS_PATH = "/tmp/orbit-mail-headers.txt"


def _parse_message_id_from_headers(hdrs: str) -> str:
    """Extract Message-ID value from raw RFC822 headers; empty if absent."""
    if not hdrs:
        return ""
    m = re.search(r"^Message-ID:\s*<?([^>\s]+)>?\s*$",
                  hdrs, re.MULTILINE | re.IGNORECASE)
    return m.group(1) if m else ""


def _capture_apple_mail_selected() -> Optional[dict]:
    """Capture the message currently selected in Apple Mail.app.

    Tries `selection` (app-level, works in any window) first, then falls
    back to `selected messages of message viewer 1`. Every property
    access is wrapped in `try` so a single missing value (common in
    Exchange/Outlook messages) doesn't abort the whole capture.
    """
    Path(_MAC_BODY_PATH).unlink(missing_ok=True)
    script = f'''
on twoDigit(n)
    set s to (n as text)
    if (count of s) is 1 then return "0" & s
    return s
end twoDigit

on hasItems(x)
    if x is missing value then return false
    try
        if (count of x) > 0 then return true
    end try
    return false
end hasItems

on safeText(x)
    if x is missing value then return ""
    try
        return x as text
    end try
    return ""
end safeText

tell application "Mail"
    set msgs to missing value
    try
        set msgs to selection
    end try
    if not (my hasItems(msgs)) then
        try
            set msgs to selected messages of message viewer 1
        end try
    end if
    if not (my hasItems(msgs)) then return ""

    set msg to missing value
    try
        set msg to item 1 of msgs
    end try
    if msg is missing value then return ""

    set sub to ""
    try
        set sub to my safeText(subject of msg)
    end try

    set sndr to ""
    try
        set sndr to my safeText(sender of msg)
    end try

    set isoDate to ""
    try
        set dt to date sent of msg
        if dt is not missing value then
            set isoDate to (year of dt as text) & "-" & ¬
                my twoDigit(month of dt as integer) & "-" & ¬
                my twoDigit(day of dt) & "T" & ¬
                my twoDigit(hours of dt) & ":" & ¬
                my twoDigit(minutes of dt)
        end if
    end try

    set mid to ""
    try
        set mid to my safeText(message id of msg)
    end try

    set bdy to ""
    try
        set bdy to my safeText(content of msg)
    end try

    try
        set bodyFile to open for access POSIX file "{_MAC_BODY_PATH}" with write permission
        set eof of bodyFile to 0
        write bdy to bodyFile as «class utf8»
        close access bodyFile
    end try

    return sub & linefeed & sndr & linefeed & isoDate & linefeed & mid
end tell
'''
    out = _osascript(script)
    if out is None:
        return None
    lines = out.rstrip("\n").split("\n")
    # Need at least subject + 3 placeholders (may be empty strings)
    while len(lines) < 4:
        lines.append("")
    if not lines[0]:
        print("No hay ningún email seleccionado en Apple Mail.app.")
        return None
    body = ""
    bp = Path(_MAC_BODY_PATH)
    if bp.exists():
        body = bp.read_text(errors="replace")
        bp.unlink(missing_ok=True)
    return {
        "subject": lines[0],
        "from":    lines[1],
        "date":    lines[2],
        "msg_id":  lines[3].strip().lstrip("<").rstrip(">"),
        "body":    body,
        "source":  "mail",
    }


def _capture_outlook_selected() -> Optional[dict]:
    """Capture the message currently selected in Microsoft Outlook for Mac.

    Outlook's AppleScript dictionary differs from Mail.app:
      - selection returns list of selected items (messages, events, contacts)
      - sender is an "email address" record with name + address properties
      - time sent (not date sent) is the date
      - internet message id is the RFC 822 message-id
      - plain text content is the body without HTML
    """
    Path(_MAC_BODY_PATH).unlink(missing_ok=True)
    script = f'''
on hasItems(x)
    if x is missing value then return false
    try
        if (count of x) > 0 then return true
    end try
    return false
end hasItems

on safeText(x)
    if x is missing value then return ""
    try
        return x as text
    end try
    return ""
end safeText

tell application "Microsoft Outlook"
    set msgs to missing value
    try
        set msgs to selection
    end try
    if not (my hasItems(msgs)) then return ""

    set msg to missing value
    try
        set msg to item 1 of msgs
    end try
    if msg is missing value then return ""

    set sub to ""
    try
        set sub to my safeText(subject of msg)
    end try

    set sndr to ""
    try
        set sndr to my safeText(sender of msg)
    end try

    set y to ""
    set mo to ""
    set d to ""
    set h to ""
    set mi to ""
    try
        set dt to time sent of msg
        if dt is not missing value then
            set y to ((year of dt) as integer) as text
            set mo to ((month of dt) as integer) as text
            set d to ((day of dt) as integer) as text
            set h to ((hours of dt) as integer) as text
            set mi to ((minutes of dt) as integer) as text
        end if
    end try

    set bdy to ""
    try
        set bdy to my safeText(content of msg)
    end try

    try
        set bodyFile to open for access POSIX file "{_MAC_BODY_PATH}" with write permission
        set eof of bodyFile to 0
        write bdy to bodyFile as «class utf8»
        close access bodyFile
    end try

    return sub & linefeed & sndr & linefeed & y & linefeed & mo & linefeed & d & linefeed & h & linefeed & mi
end tell
'''
    out = _osascript(script)
    if out is None:
        return None
    lines = out.rstrip("\n").split("\n")
    while len(lines) < 7:
        lines.append("")
    if not lines[0]:
        print("No hay ningún email seleccionado en Microsoft Outlook.")
        return None

    body = ""
    bp = Path(_MAC_BODY_PATH)
    if bp.exists():
        body = bp.read_text(errors="replace")
        bp.unlink(missing_ok=True)

    iso_date = _build_iso_date(lines[2], lines[3], lines[4], lines[5], lines[6])

    return {
        "subject": lines[0],
        "from":    lines[1],
        "date":    iso_date,
        "msg_id":  "",   # Outlook AppleScript dictionary varies — populated later
        "body":    body,
        "source":  "outlook",
    }


def _build_iso_date(y: str, mo: str, d: str, h: str, mi: str) -> str:
    """Build ISO date string from AppleScript-extracted components."""
    try:
        return (f"{int(y):04d}-{int(mo):02d}-{int(d):02d}"
                f"T{int(h):02d}:{int(mi):02d}")
    except (ValueError, TypeError):
        return ""


# ── .eml file backend ─────────────────────────────────────────────────────────

def _html_to_text(html: str) -> str:
    """Crude stdlib-only HTML→text converter."""
    text = re.sub(r"<(script|style)\b[^>]*>.*?</\1>", "", html,
                  flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</p\s*>", "\n\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    text = _html_mod.unescape(text)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _extract_eml_body(msg) -> str:
    """Walk a parsed email.message.Message and return its plain-text body."""
    if msg.is_multipart():
        # Prefer text/plain
        for part in msg.walk():
            if part.get_content_type() == "text/plain" and \
               "attachment" not in str(part.get("Content-Disposition", "")):
                payload = part.get_payload(decode=True)
                if payload:
                    charset = part.get_content_charset() or "utf-8"
                    return payload.decode(charset, errors="replace")
        # Fallback to text/html
        for part in msg.walk():
            if part.get_content_type() == "text/html":
                payload = part.get_payload(decode=True)
                if payload:
                    charset = part.get_content_charset() or "utf-8"
                    return _html_to_text(payload.decode(charset, errors="replace"))
        return ""
    payload = msg.get_payload(decode=True)
    if payload is None:
        return ""
    charset = msg.get_content_charset() or "utf-8"
    text = payload.decode(charset, errors="replace") if isinstance(payload, bytes) else str(payload)
    if msg.get_content_type() == "text/html":
        text = _html_to_text(text)
    return text


def _extract_ics_attachment(msg) -> str:
    """Return the raw text of any text/calendar part in a multipart message."""
    if not msg.is_multipart():
        if msg.get_content_type() == "text/calendar":
            payload = msg.get_payload(decode=True)
            if payload:
                charset = msg.get_content_charset() or "utf-8"
                return payload.decode(charset, errors="replace")
        return ""
    for part in msg.walk():
        if part.get_content_type() == "text/calendar":
            payload = part.get_payload(decode=True)
            if payload:
                charset = part.get_content_charset() or "utf-8"
                return payload.decode(charset, errors="replace")
    return ""


def _capture_eml(eml_path: Path) -> Optional[dict]:
    """Parse a .eml file into the standard email dict."""
    if not eml_path.exists():
        print(f"Error: no existe {eml_path}")
        return None
    with eml_path.open("rb") as f:
        msg = _stdlib_email.message_from_binary_file(f, policy=_email_policy.default)

    subject = str(msg.get("Subject", "") or "").strip() or "(sin asunto)"
    from_hdr = str(msg.get("From", "") or "").strip()
    msg_id = str(msg.get("Message-ID", "") or "").strip().lstrip("<").rstrip(">")

    iso_date = ""
    date_hdr = msg.get("Date", "")
    if date_hdr:
        try:
            dt = parsedate_to_datetime(date_hdr)
            iso_date = dt.strftime("%Y-%m-%dT%H:%M")
        except (TypeError, ValueError):
            pass

    return {
        "subject": subject,
        "from":    from_hdr,
        "date":    iso_date,
        "msg_id":  msg_id,
        "body":    _extract_eml_body(msg),
        "ics":     _extract_ics_attachment(msg),
        "source":  "eml",
    }


# ── Note writing ──────────────────────────────────────────────────────────────

def _format_email_md(email: dict) -> str:
    """Render captured email as markdown with YAML frontmatter."""
    mail_link = f"message://%3C{email['msg_id']}%3E"
    fm = [
        "---",
        f"from: {email['from']}",
        f"date: {email['date']}",
        f"subject: {email['subject']}",
        f"message-id: <{email['msg_id']}>",
        f"mail-link: {mail_link}",
        "---",
        "",
        f"# {email['subject']}",
        "",
        email["body"].rstrip() + "\n",
    ]
    return "\n".join(fm)


def _save_email_note(project_dir: Path, email: dict) -> Optional[Path]:
    """Write captured email to notes/emails/YYYY-MM-DD-<slug>.md. Returns path."""
    notes_dir = project_dir / "notes" / "emails"
    notes_dir.mkdir(parents=True, exist_ok=True)
    # Use the email date prefix when available; otherwise today.
    date_prefix = (email["date"] or "")[:10]
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", date_prefix):
        date_prefix = _date.today().isoformat()
    slug = _slugify(email["subject"])
    fname = f"{date_prefix}-{slug}.md"
    path = notes_dir / fname
    # Avoid clobbering: append -2, -3 if needed
    n = 2
    while path.exists():
        path = notes_dir / f"{date_prefix}-{slug}-{n}.md"
        n += 1
    path.write_text(_format_email_md(email))
    return path


# ── Public entry point ────────────────────────────────────────────────────────

def run_email(project: str, query: Optional[str] = None,
              msg_id: Optional[str] = None,
              source: Optional[str] = None,
              no_note: bool = False,
              eml_path: Optional[str] = None,
              as_ev: bool = False) -> int:
    project_dir = find_project(project)
    if not project_dir:
        return 1

    if eml_path:
        email = _capture_eml(Path(eml_path).expanduser())
        if not email:
            return 1
        if as_ev:
            return _emit_event_from_email(project_dir, email)
        return _emit_email(project_dir, email, no_note=no_note)

    src = source or _default_source()

    if src in ("outlook", "mail"):
        if query or msg_id:
            app_name = "Microsoft Outlook" if src == "outlook" else "Apple Mail.app"
            print(f"Búsqueda por subject/--id aún no implementada.")
            print(f"Selecciona el email en {app_name} y vuelve a llamar sin args.")
            return 1
        email = (_capture_outlook_selected() if src == "outlook"
                 else _capture_apple_mail_selected())
    elif src == "gmail":
        print("Backend Gmail aún no implementado.")
        return 1
    else:
        print(f"Error: source desconocida '{src}' "
              f"(usa --outlook | --mail | --gmail)")
        return 1

    if not email:
        return 1
    if as_ev:
        return _emit_event_from_email(project_dir, email)
    return _emit_email(project_dir, email, no_note=no_note)


# ── Event detection from email ────────────────────────────────────────────────

_ROOM_URL_PATTERNS = [
    r"https?://[A-Za-z0-9.-]*zoom\.us/j/[^\s>\"')]+",
    r"https?://meet\.google\.com/[A-Za-z0-9-]+",
    r"https?://teams\.microsoft\.com/l/meetup-join/[^\s>\"')]+",
    r"https?://[A-Za-z0-9.-]*webex\.com/[^\s>\"')]+",
    r"https?://meet\.jit\.si/[^\s>\"')]+",
]

_AGENDA_URL_PATTERNS = [
    r"https?://indico\.[A-Za-z0-9.-]+/event/[^\s>\"')]+",
    r"https?://[A-Za-z0-9.-]*indico[A-Za-z0-9.-]*/event/[^\s>\"')]+",
]


def _extract_urls(text: str, patterns: list) -> list:
    """Return unique URLs in text matching any pattern, in first-seen order."""
    if not text:
        return []
    seen = []
    for pat in patterns:
        for m in re.finditer(pat, text):
            url = m.group(0).rstrip(".,;:>)\"']")
            if url not in seen:
                seen.append(url)
    return seen


def _parse_ics_dt(value: str) -> tuple:
    """Return (date_str, time_str) from an ICS DTSTART/DTEND value.

    ICS formats:
      - 20260508T120000Z       → ("2026-05-08", "12:00") [UTC, kept as-is]
      - 20260508T120000        → ("2026-05-08", "12:00") [floating local]
      - 20260508               → ("2026-05-08", None)    [date-only]
    """
    if not value:
        return (None, None)
    v = value.strip().rstrip("Z")
    m = re.match(r"^(\d{4})(\d{2})(\d{2})(?:T(\d{2})(\d{2}))?", v)
    if not m:
        return (None, None)
    y, mo, d, h, mi = m.groups()
    date_s = f"{y}-{mo}-{d}"
    time_s = f"{h}:{mi}" if h and mi else None
    return (date_s, time_s)


def _parse_ics(ics_text: str) -> Optional[dict]:
    """Minimalist ICS parser. Returns dict with title/date/time/end/url/description.

    Only handles the first VEVENT block. No recurrence, no timezone conversion
    (DTSTART times are kept literal — UTC marker stripped, no offset applied).
    """
    if not ics_text:
        return None
    m = re.search(r"BEGIN:VEVENT(.+?)END:VEVENT", ics_text, re.DOTALL | re.IGNORECASE)
    if not m:
        return None
    block = m.group(1)
    # Unfold continuation lines (RFC 5545: a line starting with WS continues prev)
    block = re.sub(r"\r?\n[ \t]", "", block)

    def field(name):
        rx = re.compile(rf"^{name}(?:;[^:\r\n]*)?:(.+)$",
                        re.MULTILINE | re.IGNORECASE)
        match = rx.search(block)
        return match.group(1).strip() if match else None

    dtstart = field("DTSTART")
    dtend   = field("DTEND")
    s_date, s_time = _parse_ics_dt(dtstart)
    e_date, e_time = _parse_ics_dt(dtend)

    summary = field("SUMMARY") or ""
    # ICS escapes \, → ',' and \n → newline. Reverse minimal subset.
    summary = summary.replace("\\,", ",").replace("\\;", ";")

    url = field("URL")
    location = field("LOCATION")

    return {
        "title":    summary or None,
        "date":     s_date,
        "time":     s_time,
        "end_date": e_date if e_date and e_date != s_date else None,
        "end_time": e_time,
        "url":      url,
        "location": location,
    }


def _clean_subject(subject: str) -> str:
    """Strip Re:/Fwd: prefixes from subject."""
    if not subject:
        return ""
    return re.sub(r"^(?:re|fwd|fw|aw|sv|tr)\s*:\s*", "", subject,
                  flags=re.IGNORECASE).strip()


def _detect_event_data(email: dict) -> dict:
    """Build a proposal dict from a captured email.

    Resolution:
      1. ICS attachment (most reliable: title, date, time)
      2. Heuristics on body + subject (URLs, fallback to email date)

    URL extraction always runs (even with ICS) and merges results so multiple
    rooms/agendas in the body get included.
    """
    proposal = {
        "title":   None,
        "date":    None,
        "time":    None,
        "end_time": None,
        "rooms":   [],
        "agendas": [],
    }

    # 1. ICS — overrides title/date/time when present
    ics = _parse_ics(email.get("ics") or "")
    if ics:
        proposal["title"] = ics.get("title")
        proposal["date"]  = ics.get("date")
        proposal["time"]  = ics.get("time")
        proposal["end_time"] = ics.get("end_time")
        if ics.get("url"):
            # ICS URL is usually the canonical agenda or room
            url = ics["url"]
            if any(re.search(p, url) for p in _ROOM_URL_PATTERNS):
                proposal["rooms"].append(url)
            elif any(re.search(p, url) for p in _AGENDA_URL_PATTERNS):
                proposal["agendas"].append(url)
            else:
                proposal["agendas"].append(url)
        if ics.get("location"):
            loc = ics["location"]
            if loc.startswith("http"):
                if any(re.search(p, loc) for p in _ROOM_URL_PATTERNS):
                    if loc not in proposal["rooms"]:
                        proposal["rooms"].append(loc)

    # 2. Heuristics — fill what ICS didn't, always merge URLs
    body = email.get("body") or ""
    subject = email.get("subject") or ""

    if not proposal["title"]:
        proposal["title"] = _clean_subject(subject) or "(sin asunto)"

    if not proposal["date"]:
        # Fallback to email Date header (first 10 chars of ISO format)
        edate = (email.get("date") or "")[:10]
        if re.match(r"^\d{4}-\d{2}-\d{2}$", edate):
            proposal["date"] = edate

    # Body URL extraction: append any not already present
    for url in _extract_urls(body, _ROOM_URL_PATTERNS):
        if url not in proposal["rooms"]:
            proposal["rooms"].append(url)
    for url in _extract_urls(body, _AGENDA_URL_PATTERNS):
        if url not in proposal["agendas"]:
            proposal["agendas"].append(url)

    return proposal


def _has_event_signal(proposal: dict) -> bool:
    """True if proposal has at least one piece of event info worth showing."""
    return bool(proposal.get("date") or proposal.get("rooms")
                or proposal.get("agendas"))


def _print_proposal(proposal: dict) -> None:
    """Print a human-readable preview of the detected event."""
    print()
    print("Detectada posible cita en este email:")
    print(f"  título:  {proposal.get('title') or '(sin título)'}")
    print(f"  fecha:   {proposal.get('date') or '(no detectada)'}")
    print(f"  hora:    {proposal.get('time') or '(no detectada)'}")
    if proposal.get("end_time"):
        print(f"  fin:     {proposal['end_time']}")
    agendas = proposal.get("agendas") or []
    if agendas:
        print(f"  📋 agenda{'s' if len(agendas) > 1 else ''}:")
        for a in agendas:
            print(f"    • {a}")
    else:
        print("  📋 agenda:  -")
    rooms = proposal.get("rooms") or []
    if rooms:
        print(f"  🚪 room{'s' if len(rooms) > 1 else ''}:")
        for r in rooms:
            print(f"    • {r}")
    else:
        print("  🚪 room:    -")
    print()


def _prompt_with_default(label: str, default: str) -> str:
    """Prompt for *label*; Enter keeps *default*."""
    try:
        ans = input(f"  {label} [{default}]: ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return default
    return ans or default


def _edit_proposal(proposal: dict) -> Optional[dict]:
    """Interactive prompt to edit each field. Returns dict or None on cancel."""
    print("\nEditar campos (Enter mantiene el valor actual; vacío = quitar):")
    title = _prompt_with_default("título", proposal.get("title") or "")
    date  = _prompt_with_default("fecha (YYYY-MM-DD)", proposal.get("date") or "")
    time_v = _prompt_with_default("hora (HH:MM o vacío)", proposal.get("time") or "")

    rooms = list(proposal.get("rooms") or [])
    if len(rooms) > 1:
        print(f"  rooms detectadas: {len(rooms)}")
        for i, r in enumerate(rooms, 1):
            print(f"    {i}. {r}")
        ans = _prompt_with_default("quitar rooms (ej. 2,3 o vacío)", "")
        if ans:
            try:
                drop = sorted({int(x.strip()) for x in ans.split(",")}, reverse=True)
                for i in drop:
                    if 1 <= i <= len(rooms):
                        rooms.pop(i - 1)
            except ValueError:
                pass

    agendas = list(proposal.get("agendas") or [])
    if len(agendas) > 1:
        print(f"  agendas detectadas: {len(agendas)}")
        for i, a in enumerate(agendas, 1):
            print(f"    {i}. {a}")
        ans = _prompt_with_default("quitar agendas (ej. 2 o vacío)", "")
        if ans:
            try:
                drop = sorted({int(x.strip()) for x in ans.split(",")}, reverse=True)
                for i in drop:
                    if 1 <= i <= len(agendas):
                        agendas.pop(i - 1)
            except ValueError:
                pass

    if not title or not date:
        print("⚠️  Título y fecha son obligatorios. Cancelado.")
        return None

    return {
        "title":   title,
        "date":    date,
        "time":    time_v or None,
        "end_time": proposal.get("end_time"),
        "rooms":   rooms,
        "agendas": agendas,
    }


def _propose_event(proposal: dict) -> Optional[dict]:
    """Show preview, ask user to confirm/edit/cancel. Returns confirmed dict."""
    _print_proposal(proposal)
    if not sys.stdin.isatty():
        print("(modo no-interactivo — cancelado)")
        return None
    try:
        ans = input("¿Crear evento? [S/n/e=editar]: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        return None
    if ans in ("n", "no"):
        return None
    if ans == "e":
        return _edit_proposal(proposal)
    if not proposal.get("title") or not proposal.get("date"):
        print("⚠️  Faltan título o fecha. Usa 'e' para editarlos.")
        return None
    return proposal


def _create_event_from_proposal(project_dir: Path, proposal: dict) -> int:
    """Call run_ev_add with the first room/agenda; append extras directly."""
    from core.agenda_cmds import (
        run_ev_add, _read_agenda, _write_agenda, resolve_file,
        _AGENDA_NOTE_PREFIX, _ROOM_NOTE_PREFIX,
    )

    rooms = proposal.get("rooms") or []
    agendas = proposal.get("agendas") or []

    rc = run_ev_add(
        project=project_dir.name,
        text=proposal["title"],
        date_val=proposal["date"],
        time_val=proposal.get("time"),
        agenda=agendas[0] if agendas else None,
        room=rooms[0] if rooms else None,
    )
    if rc != 0:
        return rc

    # Append extras (multiple rooms/agendas) directly to the just-created event
    extras_room = rooms[1:]
    extras_agenda = agendas[1:]
    if not extras_room and not extras_agenda:
        return 0
    agenda_path = resolve_file(project_dir, "agenda")
    data = _read_agenda(agenda_path)
    for ev in reversed(data["events"]):
        if ev.get("desc") == proposal["title"] and ev.get("date") == proposal["date"]:
            notes = ev.setdefault("notes", [])
            for a in extras_agenda:
                notes.append(f"{_AGENDA_NOTE_PREFIX}{a}")
            for r in extras_room:
                notes.append(f"{_ROOM_NOTE_PREFIX}{r}")
            break
    _write_agenda(agenda_path, data)
    return 0


def _emit_event_from_email(project_dir: Path, email: dict) -> int:
    """Detect event in email, propose to user, create if confirmed."""
    proposal = _detect_event_data(email)
    if not _has_event_signal(proposal):
        print("⚠️  No se detectó información de cita en este email.")
        print("    Usa `ev add` manualmente.")
        return 1
    confirmed = _propose_event(proposal)
    if not confirmed:
        print("Cancelado.")
        return 0
    return _create_event_from_proposal(project_dir, confirmed)


def _emit_email(project_dir: Path, email: dict, no_note: bool = False) -> int:
    """Write the captured email's note (optional) and the logbook entry."""
    note_link = None
    if not no_note:
        note_path = _save_email_note(project_dir, email)
        if note_path:
            note_link = "./" + str(note_path.relative_to(project_dir))

    mail_link = f"message://%3C{email['msg_id']}%3E" if email.get("msg_id") else None
    secondary = ("✉️", "original", mail_link) if mail_link else None
    add_orbit_entry(
        project_dir,
        f"Email: {email['subject']}",
        tipo="referencia",
        path=note_link,
        extra_tags=["email"],
        secondary_link=secondary,
    )

    print(f"✓ [{project_dir.name}] Email guardado: {email['subject']}")
    if note_link:
        print(f"  📝 {note_link}")
    if mail_link:
        print(f"  ✉️ {mail_link}")
    else:
        print("  (sin message-id — no hay link al original)")
    return 0

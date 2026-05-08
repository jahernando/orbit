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
              eml_path: Optional[str] = None) -> int:
    project_dir = find_project(project)
    if not project_dir:
        return 1

    if eml_path:
        email = _capture_eml(Path(eml_path).expanduser())
        if not email:
            return 1
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
    return _emit_email(project_dir, email, no_note=no_note)


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

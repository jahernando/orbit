"""email.py — capture an email into a project note + logbook entry.

Backends:
  - eml:     parse a .eml file exported from any client (recommended)
  - outlook: AppleScript to Microsoft Outlook for Mac (selected message)
  - mail:    AppleScript to Apple Mail.app           (selected message)
  - gmail:   Chrome active tab URL → Gmail API        — pending

Each captured email writes one logbook entry (tipo=email); the title always
links the email in Mail, and the body carries what survives a broken link:

    2026-10-26 ✉️ [<subject>](message://%3C<id>%3E) #email [O]
      👤 <sender> · 📅 2026-10-24 10:12
      📝 [nota](./notes/emails/2026-10-24-<slug>.md)      ← only with --note
      📦 [original](./cloud/emails/2026-10-24-<slug>.eml) ← only with --keep
      🆔 `<id>`

``--note`` also writes notes/emails/YYYY-MM-DD-<slug>.md (frontmatter + body);
``--keep`` stores the full original (attachments included) as a .eml in the
project's cloud/emails/ — it opens in any mail client, even if the email is
gone from the server.
Older entries (``[Email: …]``, one line) are still read by ``ls email``.
"""

import email as _stdlib_email
import email.policy as _email_policy
import html as _html_mod
import json
import re
import subprocess
import sys
import unicodedata
from datetime import date as _date, datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Optional

from icalendar import Calendar

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


_SPANISH_MONTHS = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10,
    "noviembre": 11, "diciembre": 12,
    "ene": 1, "feb": 2, "mar": 3, "abr": 4, "may": 5, "jun": 6,
    "jul": 7, "ago": 8, "sep": 9, "oct": 10, "nov": 11, "dic": 12,
}
_ENGLISH_MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7, "aug": 8,
    "sept": 9, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}
_ALL_MONTHS = {**_SPANISH_MONTHS, **_ENGLISH_MONTHS}


from datetime import date as _date_cls


def _extract_dates_from_body(body: str) -> list:
    """Extract candidate dates from email body text.

    Returns a list of ``YYYY-MM-DD`` strings (deduplicated, first-seen
    order). Supports several common formats:

    * ISO ``2026-05-22``
    * Day/month/year ``22/05/2026`` or ``22-05-2026`` (Spanish DD/MM/YYYY)
    * Day month [year] in Spanish/English: ``22 de mayo [de 2026]``,
      ``May 22[, 2026]``

    When the year is missing, the current year is assumed unless the
    resulting date would be in the past — then next year is used. The
    caller decides which candidate to use.
    """
    if not body:
        return []
    _d = _date_cls
    today = _d.today()

    candidates = []

    def _add(year: int, month: int, day: int):
        try:
            d = _d(year, month, day)
        except ValueError:
            return
        iso = d.isoformat()
        if iso not in candidates:
            candidates.append(iso)

    # 1. ISO YYYY-MM-DD
    for m in re.finditer(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b", body):
        _add(int(m.group(1)), int(m.group(2)), int(m.group(3)))

    # 2. DD/MM/YYYY or DD-MM-YYYY (Spanish convention; reject US MM/DD/YYYY
    # by requiring day ≤ 31 and month ≤ 12, then preferring DD/MM).
    for m in re.finditer(r"\b(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{2,4})\b", body):
        a, b, c = int(m.group(1)), int(m.group(2)), int(m.group(3))
        year = c if c >= 100 else 2000 + c
        # Heuristic: if first ≤ 12 and second > 12, fall back to MM/DD.
        if a <= 12 and b > 12:
            _add(year, a, b)
        else:
            _add(year, b, a)

    # 3. Day MonthName [Year]  /  MonthName Day[, Year]
    month_alt = "|".join(_ALL_MONTHS.keys())
    pattern1 = re.compile(
        rf"\b(\d{{1,2}})\s+de\s+({month_alt})(?:\s+(?:de\s+)?(\d{{4}}))?",
        re.IGNORECASE
    )
    pattern2 = re.compile(
        rf"\b({month_alt})\s+(\d{{1,2}})(?:[,\s]+(\d{{4}}))?",
        re.IGNORECASE
    )

    for m in pattern1.finditer(body):
        day = int(m.group(1))
        month = _ALL_MONTHS[m.group(2).lower()]
        year_s = m.group(3)
        if year_s:
            _add(int(year_s), month, day)
        else:
            # Year missing: this year, or next year if past.
            try:
                d = _d(today.year, month, day)
                if d < today:
                    d = _d(today.year + 1, month, day)
                if d.isoformat() not in candidates:
                    candidates.append(d.isoformat())
            except ValueError:
                pass

    for m in pattern2.finditer(body):
        month = _ALL_MONTHS[m.group(1).lower()]
        day = int(m.group(2))
        year_s = m.group(3)
        if year_s:
            _add(int(year_s), month, day)
        else:
            try:
                d = _d(today.year, month, day)
                if d < today:
                    d = _d(today.year + 1, month, day)
                if d.isoformat() not in candidates:
                    candidates.append(d.isoformat())
            except ValueError:
                pass

    return candidates


def _pick_best_body_date(candidates: list) -> Optional[str]:
    """Pick the most likely event date from extracted candidates.

    Prefers the first date that is today or in the future. If all are
    past, picks the most recent past (defensive: still better than the
    email's send date for fixing the title afterwards).
    """
    if not candidates:
        return None
    _d = _date_cls
    today = _d.today()
    future = [c for c in candidates if _d.fromisoformat(c) >= today]
    if future:
        return future[0]
    return candidates[-1]   # most recent past


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


_REPLY_PREFIX_RE = re.compile(r"^\s*(?:(?:re|fw|fwd|rv|reenv)\s*:\s*)+", re.I)


def strip_reply_prefix(subject: str) -> str:
    """``Re: RV: Informe`` → ``Informe`` (para nombres de fichero)."""
    return _REPLY_PREFIX_RE.sub("", subject).strip() or subject


def email_basename(email: dict) -> str:
    """``YYYY-MM-DD-<asunto>``: fecha del correo (o hoy) + asunto sin
    ``Re:``/``Fw:``. Nombre común de la nota (.md) y del original (.eml)."""
    date_prefix = (email.get("date") or "")[:10]
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", date_prefix):
        date_prefix = _date.today().isoformat()
    return f"{date_prefix}-{_slugify(strip_reply_prefix(email['subject']))}"


# ── Original (.eml) en cloud/emails/ (--keep) ─────────────────────────────────

_MAC_SOURCE_PATH = "/tmp/orbit-mail-source.eml"


def _apple_mail_selected_source(msg_id: str) -> Optional[bytes]:
    """Fuente RFC 822 del correo seleccionado en Mail (con adjuntos).

    Se comprueba que el seleccionado sigue siendo *msg_id*: si cambió la
    selección entre la captura y esta llamada, None.
    """
    Path(_MAC_SOURCE_PATH).unlink(missing_ok=True)
    script = f'''
tell application "Mail"
    set msgs to {{}}
    try
        set msgs to selection
    end try
    if (count of msgs) is 0 then
        try
            set msgs to selected messages of message viewer 1
        end try
    end if
    if (count of msgs) is 0 then return ""
    set msg to item 1 of msgs
    set mid to ""
    try
        set mid to message id of msg
    end try
    set src to source of msg
    set f to open for access POSIX file "{_MAC_SOURCE_PATH}" with write permission
    set eof of f to 0
    write src to f as «class utf8»
    close access f
    return mid
end tell
'''
    out = _osascript(script, timeout=60)
    sp = Path(_MAC_SOURCE_PATH)
    try:
        if out is None or not sp.exists():
            return None
        if out.strip().strip("<>") != msg_id:
            print("⚠️  La selección de Mail cambió: no se guarda el original.")
            return None
        return sp.read_bytes()
    finally:
        sp.unlink(missing_ok=True)


def _raw_source(email: dict) -> Optional[bytes]:
    """El correo original completo, según de dónde vino (una vez: se guarda
    en ``email["raw"]`` para los demás proyectos de ``--p``)."""
    if "raw" not in email:
        email["raw"] = _fetch_raw_source(email)
    return email["raw"]


def _fetch_raw_source(email: dict) -> Optional[bytes]:
    if email.get("eml_path"):
        try:
            return Path(email["eml_path"]).read_bytes()
        except OSError as exc:
            print(f"⚠️  No se pudo leer {email['eml_path']}: {exc}")
            return None
    if email.get("source") == "mail" and email.get("msg_id"):
        return _apple_mail_selected_source(email["msg_id"])
    print("⚠️  --keep: este origen no da el correo original "
          "(usa Mail o --eml).")
    return None


def _save_email_original(project_dir: Path, email: dict) -> Optional[str]:
    """Guarda el original en ``cloud/emails/<base>.eml``; devuelve el enlace
    relativo (``./cloud/emails/….eml``) o None. Mismo contenido ya guardado
    → se reutiliza; si no, sufijo ``_2``."""
    import tempfile
    from core.link_import import _apply_non_md
    raw = _raw_source(email)
    if not raw:
        return None
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "original.eml"
        src.write_bytes(raw)
        try:
            link, _dest = _apply_non_md(project_dir, src, "import",
                                        f"{email_basename(email)}.eml",
                                        "emails", dedupe=True)
        except (RuntimeError, OSError) as exc:
            print(f"⚠️  No se pudo guardar el original: {exc}")
            return None
    return link


def _save_email_note(project_dir: Path, email: dict) -> Optional[Path]:
    """Write captured email to notes/emails/YYYY-MM-DD-<slug>.md. Returns path."""
    notes_dir = project_dir / "notes" / "emails"
    notes_dir.mkdir(parents=True, exist_ok=True)
    base = email_basename(email)
    path = notes_dir / f"{base}.md"
    # Avoid clobbering: append -2, -3 if needed
    n = 2
    while path.exists():
        path = notes_dir / f"{base}-{n}.md"
        n += 1
    path.write_text(_format_email_md(email))
    return path


# ── Public entry point ────────────────────────────────────────────────────────

def _resolve_projects(project: Optional[str], also: Optional[list]) -> Optional[list]:
    """Proyecto principal + ``--p`` (sin repetir) → directorios; None si
    alguno no existe."""
    names = [n for n in ([project] if project else []) + list(also or []) if n]
    if not names:
        print("⚠️  email: falta el proyecto (email <proyecto> [--p otro…]).")
        return None
    dirs = []
    for name in names:
        d = find_project(name)
        if not d:
            return None
        if d not in dirs:
            dirs.append(d)
    return dirs


def run_email(project: Optional[str], query: Optional[str] = None,
              msg_id: Optional[str] = None,
              source: Optional[str] = None,
              with_note: bool = False,
              eml_path: Optional[str] = None,
              as_ev: bool = False,
              keep: bool = False,
              also: Optional[list] = None,
              item: Optional[str] = None,
              date_val: Optional[str] = None,
              fup: Optional[str] = None) -> int:
    """Capture an email; always log a link to the original.

    Modifiers (combinable):
      with_note=True  → also save the email body as notes/emails/<...>.md
                        (📝 in the entry body)
      keep=True       → also store the original .eml in cloud/emails/ (📦)
      as_ev=True      → also propose creating an event from the email content
      also=[…]        → ``--p``: register it in these projects too (one entry
                        and one copy per project; the event goes to one)
      item="task"|"ms" → ``--task`` / ``--ms``: also a task / milestone with
                        the email linked (``--date``, ``--fup``); one project
    """
    if (date_val or fup) and not item:
        print("⚠️  --date / --fup van con --task o --ms "
              "(un ⏩ cuelga de una cita: email --task --fup viernes).")
        return 1
    project_dirs = _resolve_projects(project, also)
    if not project_dirs:
        return 1
    extra = dict(item=item, date_val=date_val, fup=fup)

    if eml_path:
        email = _capture_eml(Path(eml_path).expanduser())
        if not email:
            return 1
        email["eml_path"] = str(Path(eml_path).expanduser())
        return _process_email(project_dirs, email, with_note=with_note,
                              as_ev=as_ev, keep=keep, **extra)

    src = source or _default_source()

    if src in ("outlook", "mail"):
        if query or msg_id:
            app_name = "Microsoft Outlook" if src == "outlook" else "Apple Mail"
            what = f"«{query}»" if query else f"--id {msg_id}"
            print(f"⚠️  email no busca correos ({what} no se usa): registra "
                  f"el que tengas seleccionado en {app_name}.")
            print("   email · email --note · email --ev "
                  "(el log se hace siempre)")
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
    return _process_email(project_dirs, email, with_note=with_note, as_ev=as_ev,
                          keep=keep, **extra)


def _entry_links(project_dir: Path, email: dict) -> tuple:
    """``(📝, 📦)`` de la entrada del log de este correo, ya escrita."""
    from views.emails import project_emails
    mail = f"message://%3C{email['msg_id']}%3E" if email.get("msg_id") else None
    for row in project_emails(project_dir):
        if (email.get("msg_id") and row.msg_id == email["msg_id"]) or \
                (mail and row.mail == mail):
            return row.note, row.keep
    return None, None


_EMAIL_PREFIX = "✉️ "     # = core.agenda.display._EMAIL_NOTE_PREFIX


def _copy_lines(project_dir: Path, email: dict) -> list:
    """Líneas de cuerpo de la cita para las copias locales: 📝 · 📦."""
    note, keep = _entry_links(project_dir, email)
    return ([f"📝 [nota]({note})"] if note else []) + \
           ([f"📦 [original]({keep})"] if keep else [])


def _ask(prompt: str) -> str:
    try:
        return input(prompt).strip()
    except EOFError:
        return ""


def _emit_item_from_email(project_dir: Path, email: dict, kind: str,
                          date_val: Optional[str] = None,
                          fup: Optional[str] = None) -> int:
    """``--task`` / ``--ms``: tarea o hito con el correo enlazado en el
    cuerpo (✉️, y 📝 / 📦 si los hay). Título = asunto sin ``Re:``/``Fw:``
    (en terminal se puede cambiar). Sin ``--date`` ni ``--fup``, el
    interrogador de ``add -i`` pregunta fecha, hora, aviso y ⏩."""
    from core.agenda.runners import run_task_add, run_ms_add
    label = "tarea" if kind == "task" else "hito"
    title = _md_text(strip_reply_prefix(email["subject"])) or "(sin asunto)"
    if sys.stdin.isatty():
        got = _ask(f"  título de la {label} (enter = «{title}»): ") if kind == "task" \
            else _ask(f"  título del {label} (enter = «{title}»): ")
        title = _md_text(got) or title
    body = _copy_lines(project_dir, email)
    if email.get("msg_id"):              # ref estructurada → `links: [✉️](…)`
        body.append(f"{_EMAIL_PREFIX}message://%3C{email['msg_id']}%3E")
    add = run_task_add if kind == "task" else run_ms_add
    return add(project_dir.name, title, date_val=date_val, fup=fup,
               desc=body or None, ask=not (date_val or fup))


def _pick_project(project_dirs: list, what: str) -> Optional[Path]:
    """Una cita vive en un proyecto: con varios, se pregunta (Enter = el
    primero; sin terminal, el primero)."""
    if len(project_dirs) == 1 or not sys.stdin.isatty():
        return project_dirs[0]
    for i, d in enumerate(project_dirs, 1):
        print(f"  {i}. {d.name}")
    raw = input(f"  ¿{what} en cuál? (número, enter = 1): ").strip()
    if not raw:
        return project_dirs[0]
    if raw.isdigit() and 1 <= int(raw) <= len(project_dirs):
        return project_dirs[int(raw) - 1]
    print(f"  ⚠️  No reconozco {raw!r}: no se crea.")
    return None


def _process_email(project_dirs, email: dict,
                   with_note: bool = False, as_ev: bool = False,
                   keep: bool = False, item: Optional[str] = None,
                   date_val: Optional[str] = None,
                   fup: Optional[str] = None) -> int:
    """Always log (in every project); optionally save md note / original
    .eml; optionally create a task / milestone (*item*) and/or propose an
    event — each in one project."""
    if isinstance(project_dirs, Path):
        project_dirs = [project_dirs]
    for project_dir in project_dirs:
        rc = _emit_email(project_dir, email, with_note=with_note, keep=keep)
        if rc != 0:
            return rc
    if item:
        what = "la tarea" if item == "task" else "el hito"
        project_dir = _pick_project(project_dirs, what)
        if project_dir is None:
            return 1
        rc = _emit_item_from_email(project_dir, email, item,
                                   date_val=date_val, fup=fup)
        if rc != 0:
            return rc
    if as_ev:
        project_dir = _pick_project(project_dirs, "el evento")
        if project_dir is None:
            return 1
        ev_rc = _emit_event_from_email(project_dir, email)
        if ev_rc != 0:
            # Event creation failed/cancelled — log entry is already written
            return ev_rc
    return 0


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


def _dt_split(value) -> tuple:
    """Return (date_iso, time_iso) from an icalendar DT value.

    Times are kept *literal* — UTC offset is dropped without conversion,
    matching the previous behaviour. Calendar invitations typically carry
    DTSTART in the local zone of the organiser; converting to the
    recipient's TZ was never the contract here.
    """
    if isinstance(value, datetime):
        return (value.date().isoformat(), value.strftime("%H:%M"))
    return (value.isoformat(), None)


def _parse_ics(ics_text: str) -> Optional[dict]:
    """Parse the first VEVENT of an ICS blob.

    Returns ``{title, date, time, end_date, end_time, url, location}`` or
    ``None`` on empty/garbage input. No recurrence, no timezone
    conversion — UTC times are recorded as-is.
    """
    if not ics_text:
        return None
    # Tolerate bare-VEVENT fragments (some clients strip the wrapper).
    text = ics_text
    if "BEGIN:VCALENDAR" not in text.upper():
        text = "BEGIN:VCALENDAR\r\nVERSION:2.0\r\n" + text + "\r\nEND:VCALENDAR\r\n"
    try:
        cal = Calendar.from_ical(text)
    except (ValueError, KeyError):
        return None

    vevents = list(cal.walk("VEVENT"))
    if not vevents:
        return None
    vev = vevents[0]

    summary = vev.get("summary")
    title = str(summary) if summary is not None else None

    s_date = s_time = e_date = e_time = None
    if (dt := vev.get("dtstart")) is not None:
        s_date, s_time = _dt_split(dt.dt)
    if (dt := vev.get("dtend")) is not None:
        e_date, e_time = _dt_split(dt.dt)

    url = vev.get("url")
    location = vev.get("location")

    return {
        "title":    title or None,
        "date":     s_date,
        "time":     s_time,
        "end_date": e_date if e_date and e_date != s_date else None,
        "end_time": e_time,
        "url":      str(url) if url is not None else None,
        "location": str(location) if location is not None else None,
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
        # Try to extract a date from the body text first — the email's
        # send-date is often days/weeks before the actual meeting date.
        body_candidates = _extract_dates_from_body(body)
        best = _pick_best_body_date(body_candidates)
        if best:
            proposal["date"] = best
            proposal["_date_source"] = "body"
        else:
            # Last resort: email Date header.
            edate = (email.get("date") or "")[:10]
            if re.match(r"^\d{4}-\d{2}-\d{2}$", edate):
                proposal["date"] = edate
                proposal["_date_source"] = "email-header"

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


def _edit_multi_value(label: str, current: list) -> list:
    """Prompt for a multi-valued field (room or agenda).

    Shows what was detected; user can Enter to keep all, ``-`` to clear,
    a digit to pick one of the detected, or a new value to override.
    """
    if not current:
        print(f"  {label}: (ninguna detectada)")
        try:
            ans = input(f"  {label} (vacío = ninguna, o teclea valor): ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return []
        return [ans] if ans else []

    if len(current) == 1:
        print(f"  {label} detectada: {current[0]}")
        try:
            ans = input(
                f"  {label} (Enter mantiene, '-' quita, o nuevo valor): "
            ).strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return current
        if not ans:
            return current
        if ans == "-":
            return []
        return [ans]

    # Multiple detected.
    print(f"  {label}s detectadas:")
    for i, v in enumerate(current, 1):
        print(f"    {i}. {v}")
    try:
        ans = input(
            f"  {label} (Enter mantiene todas, # para una sola, '-' quita, o nuevo valor): "
        ).strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return current
    if not ans:
        return current
    if ans == "-":
        return []
    if ans.isdigit():
        idx = int(ans) - 1
        if 0 <= idx < len(current):
            return [current[idx]]
        return current
    return [ans]


def _edit_proposal(proposal: dict) -> Optional[dict]:
    """Interactive prompt to edit each field. Returns dict or None on cancel."""
    print("\nEditar campos (Enter mantiene el valor actual; vacío = quitar):")
    title = _prompt_with_default("título", proposal.get("title") or "")
    date_default = proposal.get("date") or ""
    src = proposal.get("_date_source")
    date_hint = ""
    if src == "body":
        date_hint = " [extraída del cuerpo del email]"
    elif src == "email-header":
        date_hint = " [fecha de envío del email — revísala]"
    date  = _prompt_with_default(f"fecha (YYYY-MM-DD){date_hint}", date_default)
    time_v = _prompt_with_default("hora (HH:MM o vacío)", proposal.get("time") or "")

    rooms   = _edit_multi_value("room",   list(proposal.get("rooms")   or []))
    agendas = _edit_multi_value("agenda", list(proposal.get("agendas") or []))

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
        run_ev_add, _read_agenda, _write_agenda,
        _AGENDA_NOTE_PREFIX, _ROOM_NOTE_PREFIX, _EMAIL_NOTE_PREFIX,
    )
    from core.log import resolve_file

    rooms = proposal.get("rooms") or []
    agendas = proposal.get("agendas") or []
    email_url = proposal.get("email_url")

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

    # Append extras (multiple rooms/agendas) and source-email link directly
    # to the just-created event.
    extras_room = rooms[1:]
    extras_agenda = agendas[1:]
    copies = proposal.get("copies") or []
    if not extras_room and not extras_agenda and not email_url and not copies:
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
            if email_url:
                notes.append(f"{_EMAIL_NOTE_PREFIX}{email_url}")
            notes.extend(copies)
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
    # Carry the source-email link into the event so the user can jump back
    # to the original message from Calendar.app / khal / agenda.md.
    if email.get("msg_id"):
        confirmed["email_url"] = f"message://%3C{email['msg_id']}%3E"
    confirmed["copies"] = _copy_lines(project_dir, email)
    return _create_event_from_proposal(project_dir, confirmed)


def _md_text(text: str) -> str:
    """Texto seguro dentro de ``[…]`` de un enlace markdown."""
    return text.replace("[", "(").replace("]", ")").strip()


def email_body_lines(email: dict, note_link: Optional[str] = None,
                     keep_link: Optional[str] = None) -> list:
    """Cuerpo de la entrada del log: 👤 📅 · 📝 · 📦 · 🆔 (lo que falte, se
    omite)."""
    lines = []
    who = (email.get("from") or "").strip()
    when = (email.get("date") or "").replace("T", " ").strip()
    meta = " · ".join(x for x in ((f"👤 {who}" if who else ""),
                                  (f"📅 {when}" if when else "")) if x)
    if meta:
        lines.append(meta)
    if note_link:
        lines.append(f"📝 [nota]({note_link})")
    if keep_link:
        lines.append(f"📦 [original]({keep_link})")
    if email.get("msg_id"):
        lines.append(f"🆔 `{email['msg_id']}`")
    return lines


def already_logged(project_dir: Path, msg_id: str) -> bool:
    """¿Este Message-ID ya está registrado en el logbook del proyecto?"""
    from core.log import find_logbook_file
    if not msg_id:
        return False
    lb = find_logbook_file(project_dir)
    if not lb or not lb.exists():
        return False
    text = lb.read_text()
    return f"`{msg_id}`" in text or f"%3C{msg_id}%3E" in text


def _find_entry(lines: list, msg_id: str) -> Optional[tuple]:
    """``(cabecera, fin)`` de la entrada del log de *msg_id*: índice de la
    cabecera y el primero tras su cuerpo. None si no está."""
    head = None
    for i, line in enumerate(lines):
        if line[:4].isdigit() and len(line) > 10 and line[4] == "-":
            head = i
            if f"%3C{msg_id}%3E" in line:
                break
        elif head is not None and line.strip() == f"🆔 `{msg_id}`":
            break
    else:
        return None
    end = head + 1
    while end < len(lines) and lines[end].startswith("  ") and lines[end].strip():
        end += 1
    return head, end


def _existing_links(project_dir: Path, msg_id: str) -> tuple:
    """``(tiene 📝, tiene 📦)`` en la entrada ya registrada."""
    from core.log import find_logbook_file
    lines = find_logbook_file(project_dir).read_text().splitlines()
    span = _find_entry(lines, msg_id)
    if not span:
        return False, False
    text = "\n".join(lines[span[0]:span[1]])
    return ".md)" in text, ".eml)" in text


def complete_entry(project_dir: Path, email: dict,
                   note_link: Optional[str] = None,
                   keep_link: Optional[str] = None) -> list:
    """Completa la entrada ya registrada de este correo con lo que le falte
    (👤 📅, 📝, 📦, 🆔 — también en las entradas antiguas, de una línea).
    Devuelve las líneas añadidas. Única edición de una entrada del log que
    hace `email`."""
    from core.log import find_logbook_file
    from core.undo import save_snapshot
    lb = find_logbook_file(project_dir)
    lines = lb.read_text().split("\n")
    span = _find_entry(lines, email["msg_id"])
    if not span:
        return []
    head, end = span
    body = [l.strip() for l in lines[head + 1:end]]
    want = email_body_lines(email, note_link, keep_link)
    has = {
        "meta": any(b.startswith(("👤", "📅")) for b in body),
        "note": ".md)" in lines[head] or any(b.startswith("📝") for b in body),
        "keep": any(b.startswith("📦") for b in body),
        "id":   any(b.startswith("🆔") for b in body),
    }
    new_body, added = list(body), []

    def kind(line):
        return {"👤": "meta", "📅": "meta", "📝": "note",
                "📦": "keep", "🆔": "id"}.get(line[:1], "")

    for w in want:
        k = kind(w)
        if not k or has[k]:
            continue
        added.append(w)
        if k == "meta":
            new_body.insert(0, w)
        elif k == "id":
            new_body.append(w)
        else:                            # 📝 / 📦: antes del 🆔
            ids = [i for i, b in enumerate(new_body) if b.startswith("🆔")]
            new_body.insert(ids[0] if ids else len(new_body), w)
    if not added:
        return []
    save_snapshot(lb)
    lines[head + 1:end] = [f"  {b}" for b in new_body]
    lb.write_text("\n".join(lines))
    return added


def _emit_email(project_dir: Path, email: dict, with_note: bool = False,
                keep: bool = False) -> int:
    """Write the logbook entry (always) and the markdown note (only with_note).

    The title links the email in Mail (``message://``); without a Message-ID
    it links the note, if any. Sender, date, note and id go in the body.
    Un correo ya registrado en el proyecto no se registra dos veces.
    """
    if already_logged(project_dir, email.get("msg_id", "")):
        has_note, has_keep = _existing_links(project_dir, email["msg_id"])
        note_link = keep_link = None
        if with_note and not has_note:
            note_path = _save_email_note(project_dir, email)
            note_link = ("./" + str(note_path.relative_to(project_dir))
                         if note_path else None)
        if keep and not has_keep:
            keep_link = _save_email_original(project_dir, email)
        added = complete_entry(project_dir, email, note_link, keep_link)
        if added:
            print(f"✓ [{project_dir.name}] ya registrado, completado: "
                  f"{email['subject']}")
            for a in added:
                print(f"  + {a}")
        else:
            print(f"⚠️  [{project_dir.name}] ya registrado: {email['subject']} "
                  "(nada que añadir)")
        return 0

    note_link = None
    if with_note:
        note_path = _save_email_note(project_dir, email)
        if note_path:
            note_link = "./" + str(note_path.relative_to(project_dir))

    keep_link = _save_email_original(project_dir, email) if keep else None

    mail_link = f"message://%3C{email['msg_id']}%3E" if email.get("msg_id") else None

    add_orbit_entry(
        project_dir,
        _md_text(email["subject"]) or "(sin asunto)",
        tipo="email",
        path=mail_link or note_link or keep_link,
        continuations=email_body_lines(email, note_link, keep_link),
    )

    print(f"✓ [{project_dir.name}] Email registrado: {email['subject']}")
    if email.get("from"):
        print(f"  👤 {email['from']}")
    if note_link:
        print(f"  📝 {note_link}")
    if keep_link:
        print(f"  📦 {keep_link}")
    if mail_link:
        print(f"  ✉️ {mail_link}")
    else:
        print("  (sin message-id — no hay link al original)")
    return 0

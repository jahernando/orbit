"""Unit tests for core/email.py — slugify, frontmatter, note write, source detect.

AppleScript-backed capture is not tested (requires Mail.app open).
"""

import json
from pathlib import Path

import pytest


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _make_project(tmp_path: Path, name: str = "💻test-project") -> Path:
    type_dir = tmp_path / "💻software"
    type_dir.mkdir()
    proj = type_dir / name
    proj.mkdir()
    base = name.lstrip("💻🌿☀️📚⚙️📖🌀🤗🏠🎨🧳💼")
    (proj / f"{base}-project.md").write_text(
        f"# {name}\n- Tipo: 💻 Software\n- Estado: [auto]\n- Prioridad: media\n"
    )
    (proj / f"{base}-logbook.md").write_text(f"# Logbook — {name}\n\n")
    return proj


@pytest.fixture()
def env(tmp_path, monkeypatch):
    proj = _make_project(tmp_path)
    monkeypatch.setattr("core.config.ORBIT_HOME", tmp_path)
    monkeypatch.setattr("core.log.PROJECTS_DIR", tmp_path)
    monkeypatch.setattr("core.email.ORBIT_HOME", tmp_path)
    return {"home": tmp_path, "proj": proj}


# ══════════════════════════════════════════════════════════════════════════════
# _slugify
# ══════════════════════════════════════════════════════════════════════════════

class TestSlugify:
    def test_basic(self):
        from core.email import _slugify
        assert _slugify("Reunión proyecto X") == "reunion-proyecto-x"

    def test_strips_punctuation(self):
        from core.email import _slugify
        assert _slugify("Re: [URGENT] Hello!!!") == "re-urgent-hello"

    def test_strips_accents(self):
        from core.email import _slugify
        assert _slugify("ñoño café") == "nono-cafe"

    def test_truncates(self):
        from core.email import _slugify
        s = _slugify("a" * 100, maxlen=10)
        assert len(s) == 10

    def test_empty_fallback(self):
        from core.email import _slugify
        assert _slugify("!!!") == "email"


# ══════════════════════════════════════════════════════════════════════════════
# _parse_message_id_from_headers
# ══════════════════════════════════════════════════════════════════════════════

class TestParseMessageId:
    def test_simple(self):
        from core.email import _parse_message_id_from_headers
        hdrs = "From: x@y.com\nMessage-ID: <abc123@example.com>\nSubject: hi\n"
        assert _parse_message_id_from_headers(hdrs) == "abc123@example.com"

    def test_case_insensitive(self):
        from core.email import _parse_message_id_from_headers
        hdrs = "Message-Id: <xyz@ex.com>\n"
        assert _parse_message_id_from_headers(hdrs) == "xyz@ex.com"

    def test_no_brackets(self):
        from core.email import _parse_message_id_from_headers
        hdrs = "Message-ID: bare-id@ex.com\n"
        assert _parse_message_id_from_headers(hdrs) == "bare-id@ex.com"

    def test_absent(self):
        from core.email import _parse_message_id_from_headers
        assert _parse_message_id_from_headers("From: x@y.com\n") == ""

    def test_empty_input(self):
        from core.email import _parse_message_id_from_headers
        assert _parse_message_id_from_headers("") == ""


# ══════════════════════════════════════════════════════════════════════════════
# _default_source
# ══════════════════════════════════════════════════════════════════════════════

class TestDefaultSource:
    def test_no_orbit_json(self, env):
        from core.email import _default_source
        assert _default_source() == "outlook"

    def test_no_cartero_section(self, env):
        (env["home"] / "orbit.json").write_text(json.dumps({"space": "ws"}))
        from core.email import _default_source
        assert _default_source() == "outlook"

    def test_cartero_slack_only(self, env):
        (env["home"] / "orbit.json").write_text(json.dumps({
            "space": "ws", "cartero": {"slack": [{"workspace": "x"}]},
        }))
        from core.email import _default_source
        assert _default_source() == "outlook"

    def test_cartero_gmail_present(self, env):
        (env["home"] / "orbit.json").write_text(json.dumps({
            "space": "ps", "cartero": {"gmail": {"labels": ["INBOX"]}},
        }))
        from core.email import _default_source
        assert _default_source() == "gmail"

    def test_explicit_mail(self, env):
        (env["home"] / "orbit.json").write_text(json.dumps({
            "space": "ws", "email_source": "mail",
        }))
        from core.email import _default_source
        assert _default_source() == "mail"

    def test_explicit_outlook(self, env):
        (env["home"] / "orbit.json").write_text(json.dumps({
            "space": "ws", "email_source": "outlook",
        }))
        from core.email import _default_source
        assert _default_source() == "outlook"

    def test_explicit_gmail(self, env):
        (env["home"] / "orbit.json").write_text(json.dumps({
            "space": "ps", "email_source": "gmail",
        }))
        from core.email import _default_source
        assert _default_source() == "gmail"

    def test_explicit_overrides_cartero_gmail(self, env):
        """email_source wins over cartero.gmail heuristic."""
        (env["home"] / "orbit.json").write_text(json.dumps({
            "space": "ps",
            "email_source": "mail",
            "cartero": {"gmail": {"labels": ["INBOX"]}},
        }))
        from core.email import _default_source
        assert _default_source() == "mail"

    def test_invalid_source_falls_back(self, env, capsys):
        (env["home"] / "orbit.json").write_text(json.dumps({
            "space": "ws", "email_source": "garbage",
        }))
        from core.email import _default_source
        assert _default_source() == "outlook"
        # Warning goes to stderr
        assert "inválido" in capsys.readouterr().err.lower()

    def test_invalid_source_falls_back_to_gmail_if_cartero(self, env):
        (env["home"] / "orbit.json").write_text(json.dumps({
            "space": "ps",
            "email_source": "garbage",
            "cartero": {"gmail": {"labels": ["INBOX"]}},
        }))
        from core.email import _default_source
        assert _default_source() == "gmail"


# ══════════════════════════════════════════════════════════════════════════════
# _format_email_md
# ══════════════════════════════════════════════════════════════════════════════

class TestFormatEmailMd:
    def _email(self):
        return {
            "subject": "Reunión proyecto X",
            "from":    "Alice <alice@example.com>",
            "date":    "2026-03-15T10:23",
            "msg_id":  "abc123@mail.example.com",
            "body":    "Hola,\n\nNos vemos mañana.\n\nA.",
            "source":  "mac",
        }

    def test_frontmatter_present(self):
        from core.email import _format_email_md
        md = _format_email_md(self._email())
        assert md.startswith("---\n")
        assert "from: Alice <alice@example.com>" in md
        assert "subject: Reunión proyecto X" in md
        assert "message-id: <abc123@mail.example.com>" in md

    def test_mail_link_url_encoded(self):
        from core.email import _format_email_md
        md = _format_email_md(self._email())
        assert "mail-link: message://%3Cabc123@mail.example.com%3E" in md

    def test_body_after_heading(self):
        from core.email import _format_email_md
        md = _format_email_md(self._email())
        assert "# Reunión proyecto X" in md
        assert "Nos vemos mañana." in md


# ══════════════════════════════════════════════════════════════════════════════
# _save_email_note
# ══════════════════════════════════════════════════════════════════════════════

class TestSaveEmailNote:
    def _email(self, **over):
        base = {
            "subject": "Test subject",
            "from":    "x@y.com",
            "date":    "2026-03-15T10:00",
            "msg_id":  "id1@x.com",
            "body":    "body",
        }
        base.update(over)
        return base

    def test_creates_notes_emails_dir(self, env):
        from core.email import _save_email_note
        path = _save_email_note(env["proj"], self._email())
        assert path is not None
        assert path.parent == env["proj"] / "notes" / "emails"
        assert path.exists()

    def test_filename_uses_email_date(self, env):
        from core.email import _save_email_note
        path = _save_email_note(env["proj"], self._email())
        assert path.name.startswith("2026-03-15-")
        assert path.name.endswith(".md")

    def test_filename_falls_back_to_today_when_invalid_date(self, env):
        from core.email import _save_email_note
        from datetime import date
        path = _save_email_note(env["proj"], self._email(date="garbage"))
        assert path.name.startswith(date.today().isoformat())

    def test_collision_appends_counter(self, env):
        from core.email import _save_email_note
        p1 = _save_email_note(env["proj"], self._email())
        p2 = _save_email_note(env["proj"], self._email())
        assert p1 != p2
        assert "-2.md" in p2.name

    def test_writes_frontmatter_and_body(self, env):
        from core.email import _save_email_note
        path = _save_email_note(env["proj"],
                                self._email(body="line one\nline two"))
        text = path.read_text()
        assert "subject: Test subject" in text
        assert "line one" in text
        assert "line two" in text


# ══════════════════════════════════════════════════════════════════════════════
# run_email — integration with mocked capture
# ══════════════════════════════════════════════════════════════════════════════

class TestRunEmail:
    def _email(self):
        return {
            "subject": "Capa 7 down",
            "from":    "noc@example.com",
            "date":    "2026-04-02T08:15",
            "msg_id":  "evt99@example.com",
            "body":    "Detalles aquí.",
            "source":  "mac",
        }

    def test_default_logs_email_link_without_note(self, env, monkeypatch):
        """Default: log entry only, with the email link as primary; no .md note."""
        from core import email as email_mod
        monkeypatch.setattr(email_mod, "_capture_outlook_selected",
                            lambda: self._email())
        rc = email_mod.run_email("test-project", source="outlook")
        assert rc == 0
        log = (env["proj"] / "test-project-logbook.md").read_text()
        # Email link is the primary [text](url) and the line starts with ✉️
        assert "✉️ [Email: Capa 7 down](message://%3Cevt99@example.com%3E)" in log
        # No "secondary" link of the form '✉️ [original](...)' since the
        # primary IS the email
        assert "[original](message://" not in log
        # tipo=email when the primary link is the mail itself (no #referencia here)
        assert "#email" in log
        assert "#referencia" not in log
        assert "[O]" in log
        # No note created
        assert not (env["proj"] / "notes" / "emails").exists()

    def test_with_note_creates_md_and_double_link(self, env, monkeypatch):
        """--note: also save .md note; log carries both note and email links."""
        from core import email as email_mod
        monkeypatch.setattr(email_mod, "_capture_outlook_selected",
                            lambda: self._email())
        rc = email_mod.run_email("test-project", source="outlook", with_note=True)
        assert rc == 0
        log = (env["proj"] / "test-project-logbook.md").read_text()
        # Primary link is the note, secondary is the email
        assert "[Email: Capa 7 down](./notes/emails/" in log
        assert "✉️ [original](message://%3Cevt99@example.com%3E)" in log
        notes = list((env["proj"] / "notes" / "emails").glob("*.md"))
        assert len(notes) == 1
        assert "2026-04-02" in notes[0].name

    def test_capture_returns_none(self, env, monkeypatch):
        from core import email as email_mod
        monkeypatch.setattr(email_mod, "_capture_outlook_selected", lambda: None)
        rc = email_mod.run_email("test-project", source="outlook")
        assert rc == 1

    def test_gmail_pending(self, env, capsys):
        from core import email as email_mod
        rc = email_mod.run_email("test-project", source="gmail")
        assert rc == 1
        assert "no implementado" in capsys.readouterr().out.lower()

    def test_outlook_with_query_pending(self, env, capsys):
        from core import email as email_mod
        rc = email_mod.run_email("test-project", source="outlook",
                                 query="any subject")
        assert rc == 1
        assert "no implementada" in capsys.readouterr().out.lower()

    def test_unknown_project(self, env, monkeypatch, capsys):
        from core import email as email_mod
        monkeypatch.setattr(email_mod, "_capture_outlook_selected",
                            lambda: self._email())
        rc = email_mod.run_email("ghost", source="outlook")
        assert rc == 1


# ══════════════════════════════════════════════════════════════════════════════
# .eml backend
# ══════════════════════════════════════════════════════════════════════════════

def _write_eml(path, subject="Test", from_="A <a@x.com>",
               date="Wed, 07 May 2026 10:23:45 +0000",
               msg_id="<abc@x.com>", body="Hola mundo.\n",
               content_type="text/plain"):
    """Write a minimal .eml file for tests."""
    headers = (
        f"From: {from_}\r\n"
        f"To: B <b@y.com>\r\n"
        f"Subject: {subject}\r\n"
        f"Date: {date}\r\n"
        f"Message-ID: {msg_id}\r\n"
        f"Content-Type: {content_type}; charset=utf-8\r\n"
        f"MIME-Version: 1.0\r\n"
        f"\r\n"
    )
    path.write_bytes((headers + body).encode("utf-8"))


class TestEmlBackend:
    def test_parse_basic(self, tmp_path):
        from core.email import _capture_eml
        eml = tmp_path / "msg.eml"
        _write_eml(eml, subject="Meeting X")
        d = _capture_eml(eml)
        assert d is not None
        assert d["subject"] == "Meeting X"
        assert "a@x.com" in d["from"]
        assert d["msg_id"] == "abc@x.com"
        assert d["date"] == "2026-05-07T10:23"
        assert "Hola mundo" in d["body"]
        assert d["source"] == "eml"

    def test_mime_encoded_subject(self, tmp_path):
        """RFC 2047 encoded-words (how real clients write non-ASCII headers)."""
        from core.email import _capture_eml
        eml = tmp_path / "u.eml"
        # =?UTF-8?B?UmV1bmnDs24gWA==?= → "Reunión X"
        _write_eml(eml, subject="=?UTF-8?B?UmV1bmnDs24gWA==?=")
        d = _capture_eml(eml)
        assert d["subject"] == "Reunión X"

    def test_missing_subject_uses_placeholder(self, tmp_path):
        from core.email import _capture_eml
        eml = tmp_path / "m.eml"
        _write_eml(eml, subject="")
        d = _capture_eml(eml)
        assert d["subject"] == "(sin asunto)"

    def test_html_body_converted_to_text(self, tmp_path):
        from core.email import _capture_eml
        eml = tmp_path / "h.eml"
        _write_eml(eml, body="<p>Hola <b>mundo</b></p><br>Otra l&iacute;nea.",
                   content_type="text/html")
        d = _capture_eml(eml)
        assert "<p>" not in d["body"]
        assert "Hola mundo" in d["body"]
        assert "línea" in d["body"]

    def test_nonexistent_file(self, tmp_path, capsys):
        from core.email import _capture_eml
        d = _capture_eml(tmp_path / "ghost.eml")
        assert d is None
        assert "no existe" in capsys.readouterr().out

    def test_run_email_with_eml(self, env, tmp_path):
        """Default --eml: log entry with email link as primary; no md note."""
        from core.email import run_email
        eml = tmp_path / "msg.eml"
        _write_eml(eml, subject="From eml", msg_id="<eml-id@x.com>")
        rc = run_email("test-project", eml_path=str(eml))
        assert rc == 0
        log = (env["proj"] / "test-project-logbook.md").read_text()
        assert "[Email: From eml](message://%3Ceml-id@x.com%3E)" in log
        # Without --note, no .md saved
        assert not (env["proj"] / "notes" / "emails").exists()

    def test_run_email_with_eml_and_note(self, env, tmp_path):
        """--eml --note: also save .md with double link in log."""
        from core.email import run_email
        eml = tmp_path / "msg.eml"
        _write_eml(eml, subject="From eml", msg_id="<eml-id@x.com>")
        rc = run_email("test-project", eml_path=str(eml), with_note=True)
        assert rc == 0
        log = (env["proj"] / "test-project-logbook.md").read_text()
        assert "[Email: From eml](./notes/emails/" in log
        assert "✉️ [original](message://%3Ceml-id@x.com%3E)" in log
        notes = list((env["proj"] / "notes" / "emails").glob("*.md"))
        assert len(notes) == 1


# ══════════════════════════════════════════════════════════════════════════════
# Event detection from email
# ══════════════════════════════════════════════════════════════════════════════

# Future date so `_generic_add`'s "fecha en el pasado" guard doesn't trigger.
_SAMPLE_ICS = """BEGIN:VCALENDAR
PRODID:-//orbit test//
VERSION:2.0
BEGIN:VEVENT
UID:abc@example.com
DTSTAMP:20300507T120000Z
DTSTART:20300508T120000Z
DTEND:20300508T130000Z
SUMMARY:Reunión WG12 de CNID
LOCATION:https://cern.zoom.us/j/8463658000
URL:https://indico.global/event/17950/
DESCRIPTION:Reunión semanal del WG12.
END:VEVENT
END:VCALENDAR
"""


class TestExtractUrls:
    def test_zoom(self):
        from core.email import _extract_urls, _ROOM_URL_PATTERNS
        body = "Hola\nJoin: https://cern.zoom.us/j/8463658000?pwd=foo\nbye"
        assert _extract_urls(body, _ROOM_URL_PATTERNS) == [
            "https://cern.zoom.us/j/8463658000?pwd=foo"
        ]

    def test_meet_teams_jitsi(self):
        from core.email import _extract_urls, _ROOM_URL_PATTERNS
        body = ("a https://meet.google.com/abc-defg-hij b "
                "https://teams.microsoft.com/l/meetup-join/19%3aXX "
                "https://meet.jit.si/MyRoom")
        urls = _extract_urls(body, _ROOM_URL_PATTERNS)
        assert any("meet.google.com" in u for u in urls)
        assert any("teams.microsoft.com" in u for u in urls)
        assert any("meet.jit.si" in u for u in urls)

    def test_indico(self):
        from core.email import _extract_urls, _AGENDA_URL_PATTERNS
        body = "ver agenda en https://indico.cern.ch/event/12345/ por favor"
        assert _extract_urls(body, _AGENDA_URL_PATTERNS) == [
            "https://indico.cern.ch/event/12345/"
        ]

    def test_dedupes(self):
        from core.email import _extract_urls, _ROOM_URL_PATTERNS
        body = "https://meet.google.com/abc-defg-hij twice https://meet.google.com/abc-defg-hij"
        urls = _extract_urls(body, _ROOM_URL_PATTERNS)
        assert len(urls) == 1

    def test_strips_trailing_punctuation(self):
        from core.email import _extract_urls, _ROOM_URL_PATTERNS
        body = "Click https://meet.google.com/abc-defg-hij."
        urls = _extract_urls(body, _ROOM_URL_PATTERNS)
        assert urls == ["https://meet.google.com/abc-defg-hij"]


class TestParseIcsDt:
    def test_full_utc(self):
        from core.email import _parse_ics_dt
        assert _parse_ics_dt("20300508T120000Z") == ("2030-05-08", "12:00")

    def test_full_local(self):
        from core.email import _parse_ics_dt
        assert _parse_ics_dt("20300508T120000") == ("2030-05-08", "12:00")

    def test_date_only(self):
        from core.email import _parse_ics_dt
        assert _parse_ics_dt("20300508") == ("2030-05-08", None)

    def test_empty(self):
        from core.email import _parse_ics_dt
        assert _parse_ics_dt("") == (None, None)


class TestParseIcs:
    def test_full_event(self):
        from core.email import _parse_ics
        d = _parse_ics(_SAMPLE_ICS)
        assert d is not None
        assert d["title"] == "Reunión WG12 de CNID"
        assert d["date"] == "2030-05-08"
        assert d["time"] == "12:00"
        assert d["end_time"] == "13:00"
        assert d["url"] == "https://indico.global/event/17950/"
        assert d["location"] == "https://cern.zoom.us/j/8463658000"

    def test_returns_none_for_empty(self):
        from core.email import _parse_ics
        assert _parse_ics("") is None
        assert _parse_ics("garbage") is None

    def test_handles_continuation_lines(self):
        from core.email import _parse_ics
        # RFC 5545: line starting with WS continues previous
        ics = ("BEGIN:VEVENT\nDTSTART:20260101T100000\n"
               "SUMMARY:A long\n  title across lines\n"
               "END:VEVENT\n")
        d = _parse_ics(ics)
        assert d["title"] == "A long title across lines"

    def test_unescapes_commas(self):
        from core.email import _parse_ics
        ics = ("BEGIN:VEVENT\nDTSTART:20260101T100000\n"
               "SUMMARY:Hola\\, mundo\nEND:VEVENT\n")
        d = _parse_ics(ics)
        assert d["title"] == "Hola, mundo"


class TestDetectEventData:
    def test_from_ics(self):
        from core.email import _detect_event_data
        em = {"subject": "Re: WG12", "body": "", "ics": _SAMPLE_ICS,
              "date": "2030-05-07T10:00"}
        d = _detect_event_data(em)
        assert d["title"] == "Reunión WG12 de CNID"
        assert d["date"] == "2030-05-08"
        assert d["time"] == "12:00"
        # Both URL fields from ICS classify correctly
        assert "https://cern.zoom.us/j/8463658000" in d["rooms"]
        assert "https://indico.global/event/17950/" in d["agendas"]

    def test_from_body_only(self):
        from core.email import _detect_event_data
        em = {"subject": "Re: meeting",
              "body": ("Cita el 8 a las 12.\n"
                       "Zoom: https://cern.zoom.us/j/123\n"
                       "Indico: https://indico.cern.ch/event/9/\n"),
              "date": "2030-05-08T09:00", "ics": ""}
        d = _detect_event_data(em)
        assert d["title"] == "meeting"  # Re: stripped
        assert d["date"] == "2030-05-08"  # from email date
        assert "https://cern.zoom.us/j/123" in d["rooms"]
        assert "https://indico.cern.ch/event/9/" in d["agendas"]

    def test_multiple_rooms(self):
        from core.email import _detect_event_data
        em = {"subject": "X",
              "body": ("https://cern.zoom.us/j/111 backup "
                       "https://meet.google.com/abc-defg-hij"),
              "date": "2030-05-08T09:00", "ics": ""}
        d = _detect_event_data(em)
        assert len(d["rooms"]) == 2

    def test_no_signal(self):
        from core.email import _detect_event_data, _has_event_signal
        em = {"subject": "hola", "body": "qué tal", "date": "", "ics": ""}
        d = _detect_event_data(em)
        # No date, no URLs → no signal
        assert not _has_event_signal(d)

    def test_subject_strips_prefixes(self):
        from core.email import _detect_event_data
        for prefix in ("Re: ", "RE: ", "Fwd: ", "FW: "):
            em = {"subject": f"{prefix}meeting", "body": "",
                  "date": "2030-05-08T09:00", "ics": ""}
            d = _detect_event_data(em)
            assert d["title"] == "meeting"

    def test_body_date_preferred_over_header(self):
        """Body date trumps the email send-date (which is often weeks before)."""
        from core.email import _detect_event_data
        em = {"subject": "Reunion",
              "body": "Hola, la reunion sera el 2030-05-22 a las 10:00",
              "date": "2030-05-01T09:00",   # email sent 3 weeks before
              "ics": ""}
        d = _detect_event_data(em)
        assert d["date"] == "2030-05-22"
        assert d.get("_date_source") == "body"

    def test_body_spanish_format(self):
        from core.email import _detect_event_data
        em = {"subject": "Reunion",
              "body": "Quedamos el 22 de mayo de 2030",
              "date": "2030-05-01T09:00", "ics": ""}
        d = _detect_event_data(em)
        assert d["date"] == "2030-05-22"

    def test_body_no_date_falls_back_to_header(self):
        from core.email import _detect_event_data
        em = {"subject": "Reunion",
              "body": "Sin fechas concretas en el body.",
              "date": "2030-05-08T09:00", "ics": ""}
        d = _detect_event_data(em)
        assert d["date"] == "2030-05-08"
        assert d.get("_date_source") == "email-header"


class TestExtractDatesFromBody:
    def test_iso(self):
        from core.email import _extract_dates_from_body
        assert _extract_dates_from_body("Meeting on 2030-05-22") == ["2030-05-22"]

    def test_dd_slash_mm(self):
        from core.email import _extract_dates_from_body
        # 22/05/2030 (Spanish DD/MM/YYYY)
        assert "2030-05-22" in _extract_dates_from_body("Fecha: 22/05/2030")

    def test_spanish_long(self):
        from core.email import _extract_dates_from_body
        assert "2030-05-22" in _extract_dates_from_body("el 22 de mayo de 2030")

    def test_spanish_abbreviated(self):
        from core.email import _extract_dates_from_body
        assert "2030-05-22" in _extract_dates_from_body("el 22 de may de 2030")

    def test_english_month_day(self):
        from core.email import _extract_dates_from_body
        assert "2030-05-22" in _extract_dates_from_body("May 22, 2030")

    def test_year_missing_picks_future(self, monkeypatch):
        from core.email import _extract_dates_from_body
        from datetime import date
        class FakeDate(date):
            @classmethod
            def today(cls):
                return date(2030, 5, 10)
        monkeypatch.setattr("core.email._date_cls", FakeDate)
        out = _extract_dates_from_body("Nos vemos el 22 de mayo")
        assert "2030-05-22" in out

    def test_invalid_date_skipped(self):
        from core.email import _extract_dates_from_body
        # 32/13/2030 doesn't exist — should be silently skipped.
        assert _extract_dates_from_body("fecha rara 32/13/2030") == []


class TestPickBestBodyDate:
    def test_empty(self):
        from core.email import _pick_best_body_date
        assert _pick_best_body_date([]) is None

    def test_picks_future(self):
        from core.email import _pick_best_body_date
        # Two candidates; the future one wins.
        out = _pick_best_body_date(["1990-01-01", "2099-12-31"])
        assert out == "2099-12-31"

    def test_all_past_returns_most_recent(self):
        from core.email import _pick_best_body_date
        out = _pick_best_body_date(["1990-01-01", "2000-06-15"])
        assert out == "2000-06-15"


_FUTURE_EMAIL_DATE = "2030-05-07T10:00"


class TestExtractIcsAttachment:
    def test_multipart_with_calendar(self, tmp_path):
        """Parse a .eml that has both text/plain and text/calendar parts."""
        eml = tmp_path / "invite.eml"
        boundary = "BOUND"
        body = f"""From: alice@x.com
To: bob@y.com
Subject: =?UTF-8?B?SW52aXRlOiBSZXVuacOzbg==?=
Date: Wed, 07 May 2026 10:00:00 +0000
Message-ID: <evt-1@x.com>
MIME-Version: 1.0
Content-Type: multipart/mixed; boundary="{boundary}"

--{boundary}
Content-Type: text/plain; charset=utf-8

You are invited.

--{boundary}
Content-Type: text/calendar; charset=utf-8

{_SAMPLE_ICS}
--{boundary}--
"""
        eml.write_bytes(body.encode("utf-8"))
        from core.email import _capture_eml
        d = _capture_eml(eml)
        assert d is not None
        assert "BEGIN:VEVENT" in (d.get("ics") or "")
        assert "WG12" in d["ics"]


class TestEmitEventFromEmail:
    def _email(self, **over):
        base = {
            "subject": "Re: WG12 reunion",
            "from":    "alice@x.com",
            "date":    _FUTURE_EMAIL_DATE,
            "msg_id":  "evt@x.com",
            "body":    ("Cita.\nZoom: https://cern.zoom.us/j/12345\n"
                        "Indico: https://indico.cern.ch/event/9/\n"),
            "ics":     "",
            "source":  "eml",
        }
        base.update(over)
        return base

    def test_creates_event_with_room_and_agenda(self, env, monkeypatch):
        from core import email as email_mod
        # Auto-confirm proposal
        monkeypatch.setattr("sys.stdin.isatty", lambda: True)
        monkeypatch.setattr("builtins.input", lambda *_: "")  # accept default
        rc = email_mod._emit_event_from_email(env["proj"], self._email())
        assert rc == 0
        agenda_md = (env["proj"] / "test-project-agenda.md").read_text()
        assert "WG12 reunion" in agenda_md
        assert "🚪 https://cern.zoom.us/j/12345" in agenda_md
        assert "📋 https://indico.cern.ch/event/9/" in agenda_md

    def test_event_uses_ics_when_present(self, env, monkeypatch):
        from core import email as email_mod
        monkeypatch.setattr("sys.stdin.isatty", lambda: True)
        monkeypatch.setattr("builtins.input", lambda *_: "")
        em = self._email(ics=_SAMPLE_ICS, body="")
        rc = email_mod._emit_event_from_email(env["proj"], em)
        assert rc == 0
        agenda_md = (env["proj"] / "test-project-agenda.md").read_text()
        assert "Reunión WG12 de CNID" in agenda_md
        # ICS URL goes to agendas, ICS LOCATION (zoom) goes to rooms
        assert "📋 https://indico.global/event/17950/" in agenda_md
        assert "🚪 https://cern.zoom.us/j/8463658000" in agenda_md

    def test_no_signal_returns_error(self, env, capsys):
        from core import email as email_mod
        em = self._email(body="just chatting", ics="", date="")
        rc = email_mod._emit_event_from_email(env["proj"], em)
        assert rc == 1
        assert "no se detectó" in capsys.readouterr().out.lower()

    def test_user_cancels(self, env, monkeypatch, capsys):
        from core import email as email_mod
        monkeypatch.setattr("sys.stdin.isatty", lambda: True)
        monkeypatch.setattr("builtins.input", lambda *_: "n")
        rc = email_mod._emit_event_from_email(env["proj"], self._email())
        assert rc == 0
        assert "cancelado" in capsys.readouterr().out.lower()
        # No event should be created
        agenda_path = env["proj"] / "test-project-agenda.md"
        if agenda_path.exists():
            assert "WG12" not in agenda_path.read_text()

    def test_multiple_rooms_all_persisted(self, env, monkeypatch):
        from core import email as email_mod
        monkeypatch.setattr("sys.stdin.isatty", lambda: True)
        monkeypatch.setattr("builtins.input", lambda *_: "")
        em = self._email(body=(
            "Sala 1: https://cern.zoom.us/j/111\n"
            "Sala 2: https://meet.google.com/abc-defg-hij\n"
        ))
        rc = email_mod._emit_event_from_email(env["proj"], em)
        assert rc == 0
        agenda_md = (env["proj"] / "test-project-agenda.md").read_text()
        assert "🚪 https://cern.zoom.us/j/111" in agenda_md
        assert "🚪 https://meet.google.com/abc-defg-hij" in agenda_md

    def test_email_link_attached_as_structured_note(self, env, monkeypatch):
        """The source email message:// URL is preserved as ✉️ note under the
        event so the user can jump back to the original mail from any view
        (Calendar.app, khal, agenda.md)."""
        from core import email as email_mod
        monkeypatch.setattr("sys.stdin.isatty", lambda: True)
        monkeypatch.setattr("builtins.input", lambda *_: "")
        rc = email_mod._emit_event_from_email(env["proj"], self._email())
        assert rc == 0
        agenda_md = (env["proj"] / "test-project-agenda.md").read_text()
        assert "✉️ message://%3Cevt@x.com%3E" in agenda_md

    def test_email_link_absent_when_no_msg_id(self, env, monkeypatch):
        """If the captured email has no Message-ID, no ✉️ note is added."""
        from core import email as email_mod
        monkeypatch.setattr("sys.stdin.isatty", lambda: True)
        monkeypatch.setattr("builtins.input", lambda *_: "")
        em = self._email(msg_id="")
        rc = email_mod._emit_event_from_email(env["proj"], em)
        assert rc == 0
        agenda_md = (env["proj"] / "test-project-agenda.md").read_text()
        assert "✉️" not in agenda_md


class TestRunEmailAsEvent:
    """Integration: full run_email(..., as_ev=True) with .eml capture."""

    def test_eml_with_ics(self, env, tmp_path, monkeypatch):
        from core.email import run_email
        eml = tmp_path / "invite.eml"
        body = f"""From: alice@x.com
To: bob@y.com
Subject: Invite
Date: Wed, 07 May 2026 10:00:00 +0000
Message-ID: <evt@x.com>
MIME-Version: 1.0
Content-Type: multipart/mixed; boundary="BB"

--BB
Content-Type: text/plain; charset=utf-8

invite text

--BB
Content-Type: text/calendar; charset=utf-8

{_SAMPLE_ICS}
--BB--
"""
        eml.write_bytes(body.encode("utf-8"))
        monkeypatch.setattr("sys.stdin.isatty", lambda: True)
        monkeypatch.setattr("builtins.input", lambda *_: "")
        rc = run_email("test-project", eml_path=str(eml), as_ev=True)
        assert rc == 0
        # --ev still logs the email (no longer skips it); no md note unless --note
        assert not (env["proj"] / "notes" / "emails").exists()
        log = (env["proj"] / "test-project-logbook.md").read_text()
        assert "[Email: Invite](message://%3Cevt@x.com%3E)" in log
        agenda_md = (env["proj"] / "test-project-agenda.md").read_text()
        assert "Reunión WG12 de CNID" in agenda_md

    def test_eml_with_ics_and_note(self, env, tmp_path, monkeypatch):
        """--note + --ev: log with double link, save md, propose event."""
        from core.email import run_email
        eml = tmp_path / "invite.eml"
        body = f"""From: alice@x.com
To: bob@y.com
Subject: Invite WG12
Date: Wed, 07 May 2026 10:00:00 +0000
Message-ID: <evt2@x.com>
MIME-Version: 1.0
Content-Type: multipart/mixed; boundary="BB"

--BB
Content-Type: text/plain; charset=utf-8

invite text

--BB
Content-Type: text/calendar; charset=utf-8

{_SAMPLE_ICS}
--BB--
"""
        eml.write_bytes(body.encode("utf-8"))
        monkeypatch.setattr("sys.stdin.isatty", lambda: True)
        monkeypatch.setattr("builtins.input", lambda *_: "")
        rc = run_email("test-project", eml_path=str(eml),
                       with_note=True, as_ev=True)
        assert rc == 0
        # All three artefacts present:
        log = (env["proj"] / "test-project-logbook.md").read_text()
        assert "[Email: Invite WG12](./notes/emails/" in log
        assert "✉️ [original](message://%3Cevt2@x.com%3E)" in log
        notes = list((env["proj"] / "notes" / "emails").glob("*.md"))
        assert len(notes) == 1
        agenda_md = (env["proj"] / "test-project-agenda.md").read_text()
        assert "Reunión WG12 de CNID" in agenda_md


class TestHtmlToText:
    def test_strips_tags(self):
        from core.email import _html_to_text
        assert _html_to_text("<p>Hola</p>") == "Hola"

    def test_decodes_entities(self):
        from core.email import _html_to_text
        assert "ñ" in _html_to_text("Espa&ntilde;a")

    def test_br_to_newline(self):
        from core.email import _html_to_text
        out = _html_to_text("a<br>b<br>c")
        assert out == "a\nb\nc"

    def test_strips_script_and_style(self):
        from core.email import _html_to_text
        html = "<style>x</style><script>y</script>visible"
        assert _html_to_text(html) == "visible"

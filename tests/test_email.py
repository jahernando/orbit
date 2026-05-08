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

    def test_creates_note_and_log_entry(self, env, monkeypatch):
        from core import email as email_mod
        monkeypatch.setattr(email_mod, "_capture_outlook_selected",
                            lambda: self._email())
        rc = email_mod.run_email("test-project", source="outlook")
        assert rc == 0
        log = (env["proj"] / "test-project-logbook.md").read_text()
        assert "[Email: Capa 7 down]" in log
        assert "✉️ [original](message://%3Cevt99@example.com%3E)" in log
        assert "#referencia #email" in log
        assert "[O]" in log
        notes = list((env["proj"] / "notes" / "emails").glob("*.md"))
        assert len(notes) == 1
        assert "2026-04-02" in notes[0].name

    def test_no_note_skips_md(self, env, monkeypatch):
        from core import email as email_mod
        monkeypatch.setattr(email_mod, "_capture_outlook_selected",
                            lambda: self._email())
        rc = email_mod.run_email("test-project", source="outlook", no_note=True)
        assert rc == 0
        assert not (env["proj"] / "notes" / "emails").exists()
        log = (env["proj"] / "test-project-logbook.md").read_text()
        # Without a note, the message has no primary path link, only secondary.
        assert "Email: Capa 7 down ✉️ [original](message://" in log

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
        from core.email import run_email
        eml = tmp_path / "msg.eml"
        _write_eml(eml, subject="From eml", msg_id="<eml-id@x.com>")
        rc = run_email("test-project", eml_path=str(eml))
        assert rc == 0
        log = (env["proj"] / "test-project-logbook.md").read_text()
        assert "[Email: From eml]" in log
        assert "✉️ [original](message://%3Ceml-id@x.com%3E)" in log
        notes = list((env["proj"] / "notes" / "emails").glob("*.md"))
        assert len(notes) == 1


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

"""Unit tests for core/arxiv.py — feed diario de arXiv por proyecto (ADR-050)."""

import json
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from core import arxiv


# ── Helpers ──────────────────────────────────────────────────────────────────

TOPICS = """\
# Temas arXiv — test

## Categorías
hep-ex, physics.ins-det
astro-ph.CO

## Autores vigilados
Gómez Cadenas

## Tema: neutrinos #neutrinos
- neutrinoless double beta
- neutrino oscillation

## Tema: detectores #detectores
- "TPC"
- liquid xenon

## Excluir
- swampland

## Ajustes
tope: 2
umbral: 1
retroceso: 3
"""


def _entry(**kw):
    base = {
        "id": "2609.00001", "title": "A paper", "summary": "Some abstract.",
        "authors": ["A. Author"], "categories": ["hep-ex"], "primary": "hep-ex",
        "published": "2026-09-10", "abs": "https://arxiv.org/abs/2609.00001",
        "pdf": "https://arxiv.org/pdf/2609.00001",
    }
    base.update(kw)
    return base


def _make_project(tmp_path: Path, name: str = "📖phys") -> Path:
    type_dir = tmp_path / "📖formacion"
    type_dir.mkdir(parents=True, exist_ok=True)
    proj = type_dir / name
    (proj / "notes").mkdir(parents=True, exist_ok=True)
    (proj / "project.md").write_text(f"# {name}\n\n📖 Formación\n")
    (proj / "logbook.md").write_text(f"# Logbook — {name}\n\n")
    (proj / "highlights.md").write_text(f"# Highlights — {name}\n\n")
    (proj / "agenda.md").write_text(f"# Agenda — {name}\n\n")
    return proj


@pytest.fixture
def feed_env(tmp_path, monkeypatch):
    """Proyecto con fichero de temas + estado aislado."""
    proj = _make_project(tmp_path)
    (proj / "notes" / arxiv.TOPICS_FILENAME).write_text(TOPICS)
    monkeypatch.setattr("core.config.ORBIT_HOME", tmp_path)
    monkeypatch.setattr("core.config._ORBIT_JSON", tmp_path / "orbit.json")
    monkeypatch.setattr("core.log.PROJECTS_DIR", tmp_path)
    monkeypatch.setattr(arxiv, "STATE_PATH", tmp_path / ".arxiv-state.json")
    return {"tmp": tmp_path, "proj": proj}


# ── Config ───────────────────────────────────────────────────────────────────

def test_parse_topics_reads_every_section():
    cfg = arxiv.parse_topics(TOPICS)
    assert cfg.categories == ["hep-ex", "physics.ins-det", "astro-ph.CO"]
    assert cfg.authors == ["Gómez Cadenas"]
    assert [t.tag for t in cfg.themes] == ["#neutrinos", "#detectores"]
    assert cfg.excludes == ["swampland"]
    assert cfg.setting("tope") == 2
    assert cfg.setting("retroceso") == 3


def test_parse_topics_derives_tag_when_absent():
    cfg = arxiv.parse_topics("## Tema: Detectores de Xenón\n- xenon\n")
    assert cfg.themes[0].tag == "#detectores-de-xenon"


def test_parse_topics_drops_themes_without_terms():
    cfg = arxiv.parse_topics("## Tema: vacío #v\n\n## Tema: lleno #l\n- algo\n")
    assert [t.tag for t in cfg.themes] == ["#l"]


def test_setting_falls_back_on_garbage():
    cfg = arxiv.parse_topics("## Ajustes\ntope: muchos\n")
    assert cfg.setting("tope") == arxiv.DEFAULTS["tope"]


# ── Coincidencia de términos ─────────────────────────────────────────────────

def test_plain_term_ignores_case_and_accents():
    assert arxiv._term_matches("reconstrucción", "Event Reconstrucción here",
                               arxiv._normalize("Event Reconstrucción here"))


def test_plain_term_needs_word_boundary():
    raw = "the axionic field"
    assert not arxiv._term_matches("axion", raw, arxiv._normalize(raw))


def test_quoted_term_is_a_strict_acronym():
    raw, norm = "A TPC detector", arxiv._normalize("A TPC detector")
    assert arxiv._term_matches('"TPC"', raw, norm)
    low = "a tpc detector"
    assert not arxiv._term_matches('"TPC"', low, arxiv._normalize(low))


# ── Puntuación ───────────────────────────────────────────────────────────────

def test_score_tags_every_matching_theme():
    cfg = arxiv.parse_topics(TOPICS)
    scored = arxiv._score_entry(
        _entry(title="Neutrinoless double beta in a TPC", summary="liquid xenon"), cfg)
    assert set(scored["tags"]) == {"#neutrinos", "#detectores"}
    # título: "neutrinoless double beta" + "TPC" (×2) · resumen: "liquid xenon" (×1)
    assert scored["score"] == 5


def test_score_zero_when_excluded():
    cfg = arxiv.parse_topics(TOPICS)
    scored = arxiv._score_entry(
        _entry(title="Neutrino oscillation and the swampland"), cfg)
    assert scored["score"] == 0
    assert scored["excluded"] == "swampland"


def test_watched_author_outweighs_a_single_term():
    cfg = arxiv.parse_topics(TOPICS)
    plain = arxiv._score_entry(_entry(title="neutrino oscillation study"), cfg)
    byauthor = arxiv._score_entry(
        _entry(title="neutrino oscillation study",
               authors=["J.J. Gómez Cadenas", "Otra"]), cfg)
    assert byauthor["score"] > plain["score"]
    assert "#autor-vigilado" in byauthor["tags"]


# ── Atom ─────────────────────────────────────────────────────────────────────

_ATOM_SAMPLE = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"
      xmlns:arxiv="http://arxiv.org/schemas/atom">
  <entry>
    <id>http://arxiv.org/abs/2609.01234v2</id>
    <published>2026-09-10T12:00:00Z</published>
    <title>Search for
      neutrinoless double beta decay</title>
    <summary>We report a search.</summary>
    <author><name>A. Uno</name></author>
    <author><name>B. Dos</name></author>
    <arxiv:primary_category term="hep-ex"/>
    <category term="hep-ex"/>
    <category term="physics.ins-det"/>
    <link href="http://arxiv.org/pdf/2609.01234v2" title="pdf"/>
  </entry>
</feed>
"""


def test_parse_feed_strips_version_and_folds_title():
    entries = arxiv._parse_feed(_ATOM_SAMPLE)
    assert len(entries) == 1
    e = entries[0]
    assert e["id"] == "2609.01234"
    assert e["title"] == "Search for neutrinoless double beta decay"
    assert e["authors"] == ["A. Uno", "B. Dos"]
    assert e["primary"] == "hep-ex"
    assert e["published"] == "2026-09-10"
    assert e["abs"] == "https://arxiv.org/abs/2609.01234"


def test_parse_feed_survives_broken_xml():
    assert arxiv._parse_feed("<feed>not closed") == []


def test_build_query_joins_categories_and_window():
    q = arxiv._build_query(["hep-ex", "hep-ph"],
                           datetime(2026, 9, 1, tzinfo=timezone.utc),
                           datetime(2026, 9, 8, tzinfo=timezone.utc))
    assert "cat:hep-ex OR cat:hep-ph" in q
    assert "submittedDate:[202609010000 TO 202609080000]" in q


# ── Bandeja ──────────────────────────────────────────────────────────────────

def test_prepend_creates_inbox_with_sentinel(tmp_path):
    inbox = tmp_path / "notes" / arxiv.INBOX_FILENAME
    arxiv.prepend_block(inbox, "📖phys", "## 2026-09-11\n\n- [ ] 📎 [T](u) #x")
    text = inbox.read_text()
    assert arxiv.SENTINEL in text
    assert text.index(arxiv.SENTINEL) < text.index("## 2026-09-11")


def test_prepend_puts_newest_on_top(tmp_path):
    inbox = tmp_path / "notes" / arxiv.INBOX_FILENAME
    arxiv.prepend_block(inbox, "📖phys", "## viejo\n\n- [ ] 📎 [A](u) #x")
    arxiv.prepend_block(inbox, "📖phys", "## nuevo\n\n- [ ] 📎 [B](u) #x")
    text = inbox.read_text()
    assert text.index("## nuevo") < text.index("## viejo")


def test_render_entry_carries_link_tags_and_matches():
    cfg = arxiv.parse_topics(TOPICS)
    entry = _entry(title="Neutrino oscillation", authors=["A", "B", "C", "D"])
    line = arxiv.render_entry(entry, arxiv._score_entry(entry, cfg))
    assert "- [ ] 📎 [Neutrino oscillation](https://arxiv.org/abs/2609.00001) #neutrinos" in line
    assert "+1" in line                      # 4 autores → 3 + resto
    assert "coincide: neutrino oscillation" in line


# ── Triaje ───────────────────────────────────────────────────────────────────

_INBOX = """\
# arXiv — 📖phys

<!-- orbit:arxiv-inbox -->

## 2026-09-11 · 2 artículos

- [x] 📎 [Uno](https://arxiv.org/abs/1) #neutrinos
  - 1 · hep-ex · 2026-09-10 · A. Uno
  - coincide: neutrino
- [ ] 📎 [Dos](https://arxiv.org/abs/2) #detectores
  - 2 · hep-ex · 2026-09-10 · B. Dos
"""


def test_parse_inbox_finds_marks_and_tags():
    items = arxiv.parse_inbox(_INBOX.splitlines())
    assert [i.title for i in items] == ["Uno", "Dos"]
    assert items[0].marked and not items[1].marked
    assert items[0].tags == ["#neutrinos"]


def test_drop_lines_takes_the_body_with_the_item():
    lines = _INBOX.splitlines()
    items = arxiv.parse_inbox(lines)
    kept = arxiv._drop_lines(lines, [items[0]])
    assert "Uno" not in "\n".join(kept)
    assert "coincide: neutrino" not in "\n".join(kept)
    assert "Dos" in "\n".join(kept)


def test_drop_lines_removes_the_day_header_when_empty():
    lines = _INBOX.splitlines()
    kept = arxiv._drop_lines(lines, arxiv.parse_inbox(lines))
    assert not any(l.startswith("## 2026-09-11") for l in kept)
    assert any(arxiv.SENTINEL in l for l in kept)


def test_triage_promotes_marked_to_highlights(feed_env, monkeypatch):
    proj = feed_env["proj"]
    (proj / "notes" / arxiv.INBOX_FILENAME).write_text(_INBOX)
    monkeypatch.setattr("sys.stdin.isatty", lambda: False, raising=False)

    rc = arxiv.run_triage(proj.name)
    assert rc == 0

    hl = (proj / "highlights.md").read_text()
    assert "- 📎 [Uno](https://arxiv.org/abs/1) #referencia #neutrinos" in hl
    assert "Dos" not in hl

    inbox = (proj / "notes" / arxiv.INBOX_FILENAME).read_text()
    assert "Uno" not in inbox
    assert "Dos" in inbox


def test_triage_purge_empties_the_rest(feed_env):
    proj = feed_env["proj"]
    (proj / "notes" / arxiv.INBOX_FILENAME).write_text(_INBOX)
    arxiv.run_triage(proj.name, purge=True)
    inbox = (proj / "notes" / arxiv.INBOX_FILENAME).read_text()
    assert "Uno" not in inbox and "Dos" not in inbox
    assert arxiv.SENTINEL in inbox


# ── Barrido ──────────────────────────────────────────────────────────────────

def _fake_fetch(entries):
    def _f(categories, since, until, **kw):
        return entries
    return _f


def test_fetch_writes_only_what_passes_the_filter(feed_env, monkeypatch):
    proj = feed_env["proj"]
    today = date.today().isoformat()
    monkeypatch.setattr(arxiv, "fetch_entries", _fake_fetch([
        _entry(id="1", title="Neutrinoless double beta", published=today,
               abs="https://arxiv.org/abs/1"),
        _entry(id="2", title="Unrelated condensed matter", published=today,
               abs="https://arxiv.org/abs/2"),
    ]))
    res = arxiv.fetch_for_project(proj, quiet=True)
    assert res["ok"] and res["written"] == 1 and res["scanned"] == 2

    inbox = (proj / "notes" / arxiv.INBOX_FILENAME).read_text()
    assert "Neutrinoless double beta" in inbox
    assert "Unrelated condensed matter" not in inbox


def test_fetch_honours_the_cap_and_reports_the_rest(feed_env, monkeypatch):
    proj = feed_env["proj"]
    today = date.today().isoformat()
    monkeypatch.setattr(arxiv, "fetch_entries", _fake_fetch([
        _entry(id=str(i), title="neutrino oscillation", published=today,
               abs=f"https://arxiv.org/abs/{i}") for i in range(5)
    ]))
    res = arxiv.fetch_for_project(proj, quiet=True)
    assert res["written"] == 2        # tope: 2 en el fichero de temas
    assert res["dropped"] == 3


def test_fetch_does_not_repeat_a_seen_paper(feed_env, monkeypatch):
    proj = feed_env["proj"]
    today = date.today().isoformat()
    monkeypatch.setattr(arxiv, "fetch_entries", _fake_fetch([
        _entry(id="1", title="neutrino oscillation", published=today,
               abs="https://arxiv.org/abs/1"),
    ]))
    assert arxiv.fetch_for_project(proj, quiet=True)["written"] == 1
    assert arxiv.fetch_for_project(proj, quiet=True)["written"] == 0


def test_network_failure_leaves_the_watermark_untouched(feed_env, monkeypatch):
    proj = feed_env["proj"]

    def _boom(*a, **kw):
        raise OSError("connection refused")

    monkeypatch.setattr(arxiv, "fetch_entries", _boom)
    res = arxiv.fetch_for_project(proj, quiet=True)
    assert not res["ok"]
    assert not (feed_env["tmp"] / ".arxiv-state.json").exists()


def test_dry_run_writes_nothing(feed_env, monkeypatch):
    proj = feed_env["proj"]
    today = date.today().isoformat()
    monkeypatch.setattr(arxiv, "fetch_entries", _fake_fetch([
        _entry(id="1", title="neutrino oscillation", published=today),
    ]))
    res = arxiv.fetch_for_project(proj, dry_run=True, quiet=True)
    assert res["written"] == 1
    assert not (proj / "notes" / arxiv.INBOX_FILENAME).exists()
    assert not (feed_env["tmp"] / ".arxiv-state.json").exists()


def test_project_without_topics_is_not_a_feed_project(feed_env):
    other = _make_project(feed_env["tmp"], name="📖otro")
    assert other not in arxiv.feed_projects()
    assert feed_env["proj"] in arxiv.feed_projects()


# ── Hook ─────────────────────────────────────────────────────────────────────

def test_action_is_registered_in_the_startup_chain():
    catalog = json.loads(
        (Path(__file__).resolve().parent.parent / "core" / "hooks_catalog.json").read_text())
    assert catalog["actions"]["arxiv_fetch"]["module"] == "core.arxiv"
    assert "arxiv_fetch" in catalog["chains"]["shell_start"]["post"]


def test_action_is_a_no_op_without_feed_projects(tmp_path, monkeypatch):
    monkeypatch.setattr("core.config.ORBIT_HOME", tmp_path)
    monkeypatch.setattr(arxiv, "STATE_PATH", tmp_path / ".arxiv-state.json")
    res = arxiv._action_arxiv_fetch(None)
    assert res["ok"] and res.get("skipped")


def test_action_runs_once_a_day(feed_env, monkeypatch):
    monkeypatch.setattr(arxiv, "fetch_entries", _fake_fetch([]))
    if date.today().weekday() >= 5:
        assert arxiv._action_arxiv_fetch(None)["msg"] == "fin de semana"
        return
    arxiv._action_arxiv_fetch(None)
    assert arxiv._action_arxiv_fetch(None)["msg"] == "ya barrido hoy"


def test_title_match_outranks_abstract_match():
    cfg = arxiv.parse_topics(TOPICS)
    in_title = arxiv._score_entry(
        _entry(title="A liquid xenon detector", summary="Nothing else."), cfg)
    in_abstract = arxiv._score_entry(
        _entry(title="A detector paper", summary="We use liquid xenon."), cfg)
    assert in_title["score"] == 2 * in_abstract["score"]


def test_companion_theme_needs_a_theme_of_its_own():
    cfg = arxiv.parse_topics(
        "## Tema: neutrinos #neutrinos\n- neutrino\n\n"
        "## Tema: IA #ia +acompaña\n- deep learning\n")
    assert cfg.themes[1].companion is True

    alone = arxiv._score_entry(_entry(title="Deep learning for solar flares"), cfg)
    assert alone["score"] == 0 and alone["tags"] == []

    paired = arxiv._score_entry(_entry(title="Deep learning for neutrino events"), cfg)
    assert set(paired["tags"]) == {"#neutrinos", "#ia"}


def test_init_does_not_duplicate_the_highlights_link(feed_env):
    proj = feed_env["proj"]
    arxiv.run_init(proj.name)
    (proj / "notes" / arxiv.INBOX_FILENAME).unlink()
    arxiv.run_init(proj.name)
    hl = (proj / "highlights.md").read_text()
    assert hl.count(f"./notes/{arxiv.INBOX_FILENAME}") == 1


def test_checkbox_is_the_mark():
    items = arxiv.parse_inbox(_INBOX.splitlines())
    assert items[0].marked and not items[1].marked


def test_written_items_start_unchecked():
    cfg = arxiv.parse_topics(TOPICS)
    entry = _entry(title="neutrino oscillation")
    assert arxiv.item_header(entry, arxiv._score_entry(entry, cfg)).startswith("- [ ] 📎 ")


def test_handwritten_tag_still_marks():
    lines = ["- [ ] 📎 [T](https://arxiv.org/abs/9) #neutrinos #relevante"]
    item = arxiv.parse_inbox(lines)[0]
    assert item.marked
    assert item.tags == ["#neutrinos"]


def test_bare_line_without_checkbox_is_still_read():
    """Bandejas escritas antes de la casilla: la línea desnuda sigue valiendo."""
    lines = ["- 📎 [T](https://arxiv.org/abs/9) #neutrinos"]
    item = arxiv.parse_inbox(lines)[0]
    assert not item.marked and item.title == "T"


def test_obsidian_completion_date_does_not_break_the_item():
    """El plugin Tasks puede añadir `✅ fecha` al marcar: no debe estorbar."""
    lines = ["- [x] 📎 [T](https://arxiv.org/abs/9) #neutrinos ✅ 2026-09-11"]
    item = arxiv.parse_inbox(lines)[0]
    assert item.marked and item.tags == ["#neutrinos"]


# ── Límite de ritmo ──────────────────────────────────────────────────────────

def test_rate_limit_is_retried(monkeypatch):
    import urllib.error
    calls = []

    class _Resp:
        def read(self): return _ATOM_SAMPLE.encode()
        def __enter__(self): return self
        def __exit__(self, *a): return False

    def _urlopen(req, timeout=None):
        calls.append(1)
        if len(calls) < 3:
            raise urllib.error.HTTPError(req.full_url, 429, "Rate exceeded", {}, None)
        return _Resp()

    monkeypatch.setattr(arxiv.urllib.request, "urlopen", _urlopen)
    monkeypatch.setattr(arxiv.time, "sleep", lambda *_: None)
    assert len(arxiv._read_url("https://x", 5)) > 0
    assert len(calls) == 3


def test_other_http_errors_are_not_retried(monkeypatch):
    import urllib.error
    calls = []

    def _urlopen(req, timeout=None):
        calls.append(1)
        raise urllib.error.HTTPError(req.full_url, 400, "Bad Request", {}, None)

    monkeypatch.setattr(arxiv.urllib.request, "urlopen", _urlopen)
    monkeypatch.setattr(arxiv.time, "sleep", lambda *_: None)
    with pytest.raises(urllib.error.HTTPError):
        arxiv._read_url("https://x", 5)
    assert len(calls) == 1


def test_rate_limit_message_is_explicit(feed_env, monkeypatch):
    import urllib.error

    def _boom(*a, **kw):
        raise urllib.error.HTTPError("https://x", 429, "Rate exceeded", {}, None)

    monkeypatch.setattr(arxiv, "fetch_entries", _boom)
    res = arxiv.fetch_for_project(feed_env["proj"], quiet=True)
    assert not res["ok"] and "429" in res["msg"]


def test_timeout_is_retried_too(monkeypatch):
    calls = []

    class _Resp:
        def read(self): return _ATOM_SAMPLE.encode()
        def __enter__(self): return self
        def __exit__(self, *a): return False

    def _urlopen(req, timeout=None):
        calls.append(1)
        if len(calls) < 2:
            raise TimeoutError("timed out")
        return _Resp()

    monkeypatch.setattr(arxiv.urllib.request, "urlopen", _urlopen)
    monkeypatch.setattr(arxiv.time, "sleep", lambda *_: None)
    assert len(arxiv._read_url("https://x", 5)) > 0
    assert len(calls) == 2


# ── Enfriamiento tras un rechazo por ritmo ───────────────────────────────────

def _rate_limited(*a, **kw):
    import urllib.error
    raise urllib.error.HTTPError("https://x", 429, "Rate exceeded", {}, None)


def test_rate_limit_writes_a_cooldown(feed_env, monkeypatch):
    monkeypatch.setattr(arxiv, "fetch_entries", _rate_limited)
    res = arxiv.fetch_for_project(feed_env["proj"], quiet=True)
    assert res["cooldown"] is True
    state = json.loads((feed_env["tmp"] / ".arxiv-state.json").read_text())
    assert state["projects"]["📖phys"]["cooldown_until"]


def test_cooldown_blocks_the_next_attempt_without_asking_arxiv(feed_env, monkeypatch):
    monkeypatch.setattr(arxiv, "fetch_entries", _rate_limited)
    arxiv.fetch_for_project(feed_env["proj"], quiet=True)

    def _never(*a, **kw):
        raise AssertionError("no debería pedirle nada a arXiv estando en espera")

    monkeypatch.setattr(arxiv, "fetch_entries", _never)
    res = arxiv.fetch_for_project(feed_env["proj"], quiet=True)
    assert res["cooldown"] is True and "en espera" in res["msg"]


def test_force_ignores_the_cooldown(feed_env, monkeypatch):
    monkeypatch.setattr(arxiv, "fetch_entries", _rate_limited)
    arxiv.fetch_for_project(feed_env["proj"], quiet=True)

    asked = []
    monkeypatch.setattr(arxiv, "fetch_entries",
                        lambda *a, **kw: asked.append(1) or [])
    arxiv.fetch_for_project(feed_env["proj"], quiet=True, force=True)
    assert asked == [1]


def test_expired_cooldown_lets_the_sweep_through(feed_env, monkeypatch):
    from datetime import datetime, timedelta, timezone
    state = {"projects": {"📖phys": {
        "last_run": None, "watermark": None, "seen": [],
        "cooldown_until": (datetime.now(timezone.utc)
                           - timedelta(hours=1)).isoformat(timespec="minutes")}}}
    (feed_env["tmp"] / ".arxiv-state.json").write_text(json.dumps(state))

    asked = []
    monkeypatch.setattr(arxiv, "fetch_entries",
                        lambda *a, **kw: asked.append(1) or [])
    res = arxiv.fetch_for_project(feed_env["proj"], quiet=True)
    assert res["ok"] and asked == [1]


def test_startup_action_does_not_report_a_cooldown_as_failure(feed_env, monkeypatch):
    from datetime import date
    monkeypatch.setattr(arxiv, "fetch_entries", _rate_limited)
    if date.today().weekday() >= 5:
        pytest.skip("el barrido no corre en fin de semana")
    res = arxiv._action_arxiv_fetch(None)
    assert res["ok"] and res["msg"] == "0 nuevos"


# ── Ventanas viejas: --until y truncado ──────────────────────────────────────

def test_until_bounds_the_window(feed_env, monkeypatch):
    seen_range = {}

    def _capture(categories, since, until, **kw):
        seen_range["since"] = since.date().isoformat()
        seen_range["until"] = until.date().isoformat()
        return []

    monkeypatch.setattr(arxiv, "fetch_entries", _capture)
    arxiv.fetch_for_project(feed_env["proj"], since_arg="2026-08-01",
                            until_arg="2026-08-15", quiet=True)
    assert seen_range == {"since": "2026-08-01", "until": "2026-08-15"}


def test_an_old_slice_does_not_rewind_the_watermark(feed_env, monkeypatch):
    from datetime import date
    monkeypatch.setattr(arxiv, "fetch_entries", lambda *a, **kw: [])
    arxiv.fetch_for_project(feed_env["proj"], quiet=True)          # marca = hoy
    mark = json.loads((feed_env["tmp"] / ".arxiv-state.json").read_text()
                      )["projects"]["📖phys"]["watermark"]

    arxiv.fetch_for_project(feed_env["proj"], since_arg="2026-08-01",
                            until_arg="2026-08-15", quiet=True)
    after = json.loads((feed_env["tmp"] / ".arxiv-state.json").read_text()
                       )["projects"]["📖phys"]["watermark"]
    assert after == mark


def test_a_window_bigger_than_the_page_cap_says_so(feed_env, monkeypatch):
    today = date.today().isoformat()
    page = [_entry(id=str(i), title="neutrino oscillation", published=today,
                   abs=f"https://arxiv.org/abs/{i}") for i in range(arxiv.PAGE_SIZE)]

    def _full_pages(categories, since, until, truncated=None, **kw):
        if truncated is not None:
            truncated.append(True)
        return page

    monkeypatch.setattr(arxiv, "fetch_entries", _full_pages)
    res = arxiv.fetch_for_project(feed_env["proj"], quiet=True)
    assert res["truncated"] is True


def test_fetch_entries_flags_the_page_cap(monkeypatch):
    full = _ATOM_SAMPLE.replace("</feed>", "")
    entry = full[full.index("<entry>"):]
    many = "<?xml version='1.0'?><feed xmlns='http://www.w3.org/2005/Atom' " \
           "xmlns:arxiv='http://arxiv.org/schemas/atom'>" + entry * 3 + "</feed>"

    monkeypatch.setattr(arxiv, "PAGE_SIZE", 3)
    monkeypatch.setattr(arxiv, "_read_url", lambda *a, **kw: many)
    monkeypatch.setattr(arxiv.time, "sleep", lambda *_: None)

    flag: list = []
    from datetime import datetime, timezone
    out = arxiv.fetch_entries(["hep-ex"],
                              datetime(2026, 8, 1, tzinfo=timezone.utc),
                              datetime(2026, 9, 1, tzinfo=timezone.utc),
                              max_pages=2, truncated=flag)
    assert len(out) == 6 and flag == [True]


def test_block_header_names_the_window_it_covers(feed_env, monkeypatch):
    monkeypatch.setattr(arxiv, "fetch_entries", _fake_fetch([
        _entry(id="1", title="neutrino oscillation", published="2026-08-17",
               abs="https://arxiv.org/abs/1"),
    ]))
    arxiv.fetch_for_project(feed_env["proj"], since_arg="2026-08-15",
                            until_arg="2026-08-22", quiet=True)
    head = next(l for l in (feed_env["proj"] / "notes" / arxiv.INBOX_FILENAME
                            ).read_text().splitlines() if l.startswith("## "))
    assert "15-08 → 22-08" in head

"""Unit tests for core/manual.py — índice de comandos y páginas de manual."""

from pathlib import Path

import pytest

from core import manual


CHULETA = """\
# CHULETA

## Shell interactivo

Texto suelto.

### Panel de proyecto — shell fijado a un proyecto

Subsección que empieza por "Panel" pero no documenta el comando `panel`.

---

## hl — highlights

```bash
orbit hl add <project> "<text>"
```

Cuerpo de la sección.

---

## panel — dashboard dinámico

Cuerpo del panel.

---

## reminder (rem) — recordatorios

Cuerpo.

---

## log y search

Dos comandos en un encabezado.

---

## Servicios externos

### Calendar.app — ics (export iCalendar)

Aquí vive `ics`, cuyo nombre sólo aparece tras el guión.

---

## Ficheros de ejemplo

```markdown
## Categorías
## Tema: neutrinos #neutrinos
```
"""

VERBS = ["hl", "panel", "reminder", "rem", "log", "search", "ics", "undo"]


# ── Parseo ───────────────────────────────────────────────────────────────────

def test_headings_inside_code_fences_are_not_sections():
    titles = [s.title for s in manual.parse_sections(CHULETA)]
    assert "Categorías" not in titles
    assert "Tema: neutrinos #neutrinos" not in titles
    assert "hl — highlights" in titles


def test_section_spans_until_the_next_heading():
    sec = next(s for s in manual.parse_sections(CHULETA) if s.title.startswith("hl "))
    body = "\n".join(CHULETA.splitlines()[sec.start:sec.end])
    assert "Cuerpo de la sección." in body
    assert "Cuerpo del panel." not in body


# ── Emparejamiento verbo → sección ───────────────────────────────────────────

def test_own_section_wins_over_an_earlier_subsection():
    """`panel` es la sección `##`, no la subsección "Panel de proyecto"."""
    sec = manual.find_section(CHULETA, "panel", VERBS)
    assert sec.title == "panel — dashboard dinámico"


def test_alias_in_parentheses_lands_in_the_same_section():
    for verb in ("reminder", "rem"):
        assert manual.find_section(CHULETA, verb, VERBS).title.startswith("reminder")


def test_two_commands_in_one_heading():
    for verb in ("log", "search"):
        assert manual.find_section(CHULETA, verb, VERBS).title == "log y search"


def test_verb_named_only_after_the_dash_is_still_found():
    assert manual.find_section(CHULETA, "ics", VERBS).title.startswith("Calendar.app")


def test_verb_with_no_heading_at_all_is_an_orphan():
    assert manual.orphan_verbs(CHULETA, VERBS) == ["undo"]
    assert manual.find_section(CHULETA, "undo", VERBS) is None


# ── Índice ───────────────────────────────────────────────────────────────────

def test_index_lists_one_line_per_section_sorted():
    names = [s.name for s in manual.build_index(CHULETA, VERBS)]
    assert names == sorted(names)
    assert "hl" in names and "undo" not in names


def test_index_names_the_section_after_the_head_verb():
    sec = manual.find_section(CHULETA, "rem", VERBS)
    assert sec.name == "reminder" and sec.verbs[1:] == ["rem"]


def test_render_index_shows_aliases_and_descriptions():
    out = manual.render_index(manual.build_index(CHULETA, VERBS))
    assert "hl" in out and "highlights" in out
    assert "(= rem)" in out
    assert "help <comando>" in out


# ── Página ───────────────────────────────────────────────────────────────────

def test_page_carries_the_body_without_the_trailing_separator():
    sec = manual.find_section(CHULETA, "hl", VERBS)
    page = manual.render_page(CHULETA, sec)
    assert page.startswith("## hl — highlights")
    assert "Cuerpo de la sección." in page
    assert not page.rstrip().endswith("---")


def test_page_appends_the_grammar_block_when_given():
    sec = manual.find_section(CHULETA, "hl", VERBS)
    page = manual.render_page(CHULETA, sec, "usage: orbit hl [-h]")
    assert "## Gramática" in page and "usage: orbit hl" in page


# ── Sobre la chuleta real ────────────────────────────────────────────────────

def _real():
    import orbit
    chuleta = (Path(__file__).resolve().parent.parent / "CHULETA.md").read_text()
    return chuleta, orbit._COMMANDS


def test_every_indexed_verb_reaches_a_page():
    chuleta, verbs = _real()
    for sec in manual.build_index(chuleta, verbs):
        for verb in sec.verbs:
            assert manual.find_section(chuleta, verb, verbs).title == sec.title


def test_the_daily_verbs_are_indexed():
    chuleta, verbs = _real()
    indexed = {v for s in manual.build_index(chuleta, verbs) for v in s.verbs}
    for verb in ("task", "hl", "log", "note", "agenda", "arxiv", "save", "ls"):
        assert verb in indexed

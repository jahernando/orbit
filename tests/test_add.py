"""test_add.py — tests for core/add.py (refs, results, decisions, notes).

Covers:
  - _slugify: ASCII, accented chars, special chars
  - extract_section: basic, empty, placeholder, missing, comment filtering
  - _insert_into_section: existing section, on-demand creation, placeholder cleanup
  - run_add: ref/result/decision/apunte, URL, file, duplicate warning, logbook
  - run_add_note: create from template, --no-date, --no-link, import file, overwrite warning
"""

import shutil
from datetime import date
from pathlib import Path

import pytest

from core.add import (
    _slugify, extract_section, _insert_into_section,
    run_add, run_add_note, ENTRY_SECTION_MAP,
)


TODAY = date.today().isoformat()

# Minimal proyecto.md without pre-existing ref/result/decision sections
_PROYECTO_BARE = """\
# testproj

💻 Software
▶️ En marcha
🟠 Alta

## 🎯 Objetivo
Proyecto de prueba.

## ✅ Tareas

## 📓 Logbook
[Ver logbook completo](./logbook.md)
"""

# proyecto.md with sections already present
_PROYECTO_WITH_SECTIONS = """\
# testproj

💻 Software
▶️ En marcha
🟠 Alta

## 🎯 Objetivo
Proyecto de prueba.

## ✅ Tareas

## 📎 Referencias
-

## 📊 Resultados
-

## 📌 Decisiones
-

## 📓 Logbook
[Ver logbook completo](./logbook.md)
"""


# ═══════════════════════════════════════════════════════════════════════════════
# _slugify
# ═══════════════════════════════════════════════════════════════════════════════

class TestSlugify:

    def test_basic_ascii(self):
        assert _slugify("calibracion relativa") == "calibracion-relativa"

    def test_accented_chars(self):
        assert _slugify("calibración relativa") == "calibracion-relativa"

    def test_special_chars_removed(self):
        assert _slugify("Energía @ 1 MeV!") == "energia-1-mev"

    def test_multiple_spaces(self):
        assert _slugify("a  b   c") == "a-b-c"

    def test_uppercase(self):
        assert _slugify("NEXT Detector") == "next-detector"


# ═══════════════════════════════════════════════════════════════════════════════
# extract_section
# ═══════════════════════════════════════════════════════════════════════════════

class TestExtractSection:

    def _write(self, tmp_path, content):
        p = tmp_path / "proyecto.md"
        p.write_text(content)
        return p

    def test_basic_extraction(self, tmp_path):
        p = self._write(tmp_path, _PROYECTO_WITH_SECTIONS)
        # Manually inject a real entry
        p.write_text(p.read_text().replace(
            "## 📎 Referencias\n-",
            "## 📎 Referencias\n- 📎 [Paper de González](./references/gonzalez.pdf)"
        ))
        items = extract_section(p, "## 📎 Referencias")
        assert len(items) == 1
        assert "Paper de González" in items[0]

    def test_placeholder_excluded(self, tmp_path):
        p = self._write(tmp_path, _PROYECTO_WITH_SECTIONS)
        items = extract_section(p, "## 📎 Referencias")
        assert items == []

    def test_comment_excluded(self, tmp_path):
        p = self._write(tmp_path, _PROYECTO_WITH_SECTIONS)
        p.write_text(p.read_text().replace(
            "## 📎 Referencias\n-",
            "## 📎 Referencias\n<!-- placeholder -->"
        ))
        items = extract_section(p, "## 📎 Referencias")
        assert items == []

    def test_missing_section_returns_empty(self, tmp_path):
        p = self._write(tmp_path, _PROYECTO_BARE)
        items = extract_section(p, "## 📎 Referencias")
        assert items == []

    def test_stops_at_next_heading(self, tmp_path):
        p = self._write(tmp_path, _PROYECTO_WITH_SECTIONS)
        p.write_text(p.read_text()
            .replace("## 📎 Referencias\n-",
                     "## 📎 Referencias\n- ref A")
            .replace("## 📊 Resultados\n-",
                     "## 📊 Resultados\n- res B"))
        refs = extract_section(p, "## 📎 Referencias")
        assert len(refs) == 1
        assert "ref A" in refs[0]
        assert not any("res B" in r for r in refs)


# ═══════════════════════════════════════════════════════════════════════════════
# _insert_into_section
# ═══════════════════════════════════════════════════════════════════════════════

class TestInsertIntoSection:

    def _write(self, tmp_path, content):
        p = tmp_path / "proyecto.md"
        p.write_text(content)
        return p

    def test_insert_into_existing_section(self, tmp_path):
        p = self._write(tmp_path, _PROYECTO_WITH_SECTIONS)
        _insert_into_section(p, "## 📎 Referencias", "- 📎 nueva entrada")
        items = extract_section(p, "## 📎 Referencias")
        assert any("nueva entrada" in i for i in items)

    def test_insert_clears_placeholder(self, tmp_path):
        p = self._write(tmp_path, _PROYECTO_WITH_SECTIONS)
        _insert_into_section(p, "## 📎 Referencias", "- 📎 entrada real")
        content = p.read_text()
        # The standalone "-" placeholder should be gone
        lines_in_section = []
        in_sec = False
        for line in content.splitlines():
            if line.strip() == "## 📎 Referencias":
                in_sec = True
                continue
            if in_sec:
                if line.startswith("## "):
                    break
                lines_in_section.append(line)
        assert not any(l.strip() == "-" for l in lines_in_section)

    def test_create_section_on_demand(self, tmp_path):
        """Section missing → created automatically before ## 📓 Logbook."""
        p = self._write(tmp_path, _PROYECTO_BARE)
        _insert_into_section(p, "## 📊 Resultados", "- 📊 primer resultado")
        content = p.read_text()
        assert "## 📊 Resultados" in content
        assert "primer resultado" in content
        # Must appear before Logbook
        idx_sec = content.index("## 📊 Resultados")
        idx_log = content.index("## 📓 Logbook")
        assert idx_sec < idx_log

    def test_multiple_inserts_accumulate(self, tmp_path):
        p = self._write(tmp_path, _PROYECTO_WITH_SECTIONS)
        _insert_into_section(p, "## 📎 Referencias", "- 📎 entrada A")
        _insert_into_section(p, "## 📎 Referencias", "- 📎 entrada B")
        items = extract_section(p, "## 📎 Referencias")
        assert len(items) == 2


# ═══════════════════════════════════════════════════════════════════════════════
# run_add — refs, results, decisions, apuntes
# ═══════════════════════════════════════════════════════════════════════════════

class TestRunAdd:

    def test_add_ref_url(self, orbit_env, monkeypatch):
        monkeypatch.setattr("core.add.open_file", lambda p, e: 0)
        rc = run_add("testproj", "González 2024", "referencia",
                     url="https://arxiv.org/abs/2401.00001",
                     file_str=None, sync=False, open_after=False, editor="typora")
        assert rc == 0
        items = extract_section(orbit_env["proyecto_path"], "## 📎 Referencias")
        assert any("González 2024" in i for i in items)
        assert any("arxiv" in i for i in items)

    def test_add_resultado_plain(self, orbit_env):
        rc = run_add("testproj", "σ/E = 2.3%", "resultado",
                     url=None, file_str=None, sync=False,
                     open_after=False, editor="typora")
        assert rc == 0
        items = extract_section(orbit_env["proyecto_path"], "## 📊 Resultados")
        assert any("σ/E = 2.3%" in i for i in items)

    def test_add_decision(self, orbit_env):
        rc = run_add("testproj", "Calibración relativa como estándar", "decision",
                     url=None, file_str=None, sync=False,
                     open_after=False, editor="typora")
        assert rc == 0
        items = extract_section(orbit_env["proyecto_path"], "## 📌 Decisiones")
        assert any("Calibración relativa" in i for i in items)

    def test_add_apunte_goes_to_refs(self, orbit_env):
        """apunte/idea/problema all land in ## 📎 Referencias."""
        rc = run_add("testproj", "Reunión productiva con el grupo", "apunte",
                     url=None, file_str=None, sync=False,
                     open_after=False, editor="typora")
        assert rc == 0
        items = extract_section(orbit_env["proyecto_path"], "## 📎 Referencias")
        assert any("Reunión productiva" in i for i in items)

    def test_add_ref_file(self, orbit_env, tmp_path):
        """File is copied into references/ and linked correctly."""
        src = tmp_path / "paper.pdf"
        src.write_bytes(b"%PDF fake")
        rc = run_add("testproj", "Paper de prueba", "referencia",
                     url=None, file_str=str(src), sync=False,
                     open_after=False, editor="typora")
        assert rc == 0
        dest = orbit_env["proj_dir"] / "references" / "paper.pdf"
        assert dest.exists()
        items = extract_section(orbit_env["proyecto_path"], "## 📎 Referencias")
        assert any("Paper de prueba" in i for i in items)
        assert any("references/paper.pdf" in i for i in items)

    def test_add_creates_logbook_entry(self, orbit_env):
        rc = run_add("testproj", "Nuevo resultado", "resultado",
                     url=None, file_str=None, sync=False,
                     open_after=False, editor="typora")
        assert rc == 0
        logbook = orbit_env["proj_dir"] / "📓testproj.md"
        assert "Nuevo resultado" in logbook.read_text()
        assert "#resultado" in logbook.read_text()

    def test_add_duplicate_warning(self, orbit_env, capsys):
        """Second add of the same title triggers a warning."""
        run_add("testproj", "González 2024 paper", "referencia",
                url="https://example.com", file_str=None, sync=False,
                open_after=False, editor="typora")
        capsys.readouterr()
        run_add("testproj", "González 2024 paper", "referencia",
                url="https://example.com/v2", file_str=None, sync=False,
                open_after=False, editor="typora")
        out = capsys.readouterr().out
        assert "⚠️" in out

    def test_add_short_title_no_duplicate_check(self, orbit_env, capsys):
        """Titles < 5 chars never trigger duplicate warning."""
        run_add("testproj", "fig", "referencia",
                url="https://example.com/1", file_str=None, sync=False,
                open_after=False, editor="typora")
        capsys.readouterr()
        run_add("testproj", "fig", "referencia",
                url="https://example.com/2", file_str=None, sync=False,
                open_after=False, editor="typora")
        out = capsys.readouterr().out
        assert "⚠️" not in out

    def test_add_unknown_project(self, orbit_env):
        rc = run_add("proyecto_inexistente_xyz", "algo", "referencia",
                     url=None, file_str=None, sync=False,
                     open_after=False, editor="typora")
        assert rc != 0

    def test_add_creates_section_on_demand(self, orbit_env, tmp_path):
        """If the section doesn't exist in proyecto.md it's created automatically."""
        # Replace proyecto with bare template (no sections)
        orbit_env["proyecto_path"].write_text(_PROYECTO_BARE)
        rc = run_add("testproj", "Primer resultado", "resultado",
                     url=None, file_str=None, sync=False,
                     open_after=False, editor="typora")
        assert rc == 0
        content = orbit_env["proyecto_path"].read_text()
        assert "## 📊 Resultados" in content
        assert "Primer resultado" in content


# ═══════════════════════════════════════════════════════════════════════════════
# run_add_note
# ═══════════════════════════════════════════════════════════════════════════════

class TestRunAddNote:

    def test_create_note_from_template(self, orbit_env, monkeypatch):
        monkeypatch.setattr("core.add.open_file", lambda p, e: 0)
        rc = run_add_note("testproj", "Calibración relativa", "apunte",
                          file_str=None, link=True, date_prefix=True,
                          open_after=False, editor="typora")
        assert rc == 0
        notes_dir = orbit_env["proj_dir"] / "notes"
        notes = list(notes_dir.glob("*.md"))
        assert len(notes) == 1
        name = notes[0].name
        assert name.startswith(date.today().strftime("%Y%m%d"))
        assert "calibracion-relativa" in name

    def test_create_note_no_date_prefix(self, orbit_env, monkeypatch):
        monkeypatch.setattr("core.add.open_file", lambda p, e: 0)
        rc = run_add_note("testproj", "Mi análisis", "apunte",
                          file_str=None, link=True, date_prefix=False,
                          open_after=False, editor="typora")
        assert rc == 0
        notes = list((orbit_env["proj_dir"] / "notes").glob("*.md"))
        assert len(notes) == 1
        assert not notes[0].name[0].isdigit()
        assert "mi-analisis" in notes[0].name

    def test_note_uses_template_content(self, orbit_env, monkeypatch):
        monkeypatch.setattr("core.add.open_file", lambda p, e: 0)
        run_add_note("testproj", "Estudio de fondo", "apunte",
                     file_str=None, link=True, date_prefix=True,
                     open_after=False, editor="typora")
        notes = list((orbit_env["proj_dir"] / "notes").glob("*.md"))
        content = notes[0].read_text()
        assert "Estudio de fondo" in content
        assert TODAY in content

    def test_note_link_added_to_proyecto(self, orbit_env, monkeypatch):
        monkeypatch.setattr("core.add.open_file", lambda p, e: 0)
        run_add_note("testproj", "Background study", "apunte",
                     file_str=None, link=True, date_prefix=True,
                     open_after=False, editor="typora")
        items = extract_section(orbit_env["proyecto_path"], "## 📎 Referencias")
        assert any("Background study" in i for i in items)
        assert any("notes/" in i for i in items)

    def test_note_no_link(self, orbit_env, monkeypatch):
        monkeypatch.setattr("core.add.open_file", lambda p, e: 0)
        run_add_note("testproj", "Nota privada", "apunte",
                     file_str=None, link=False, date_prefix=True,
                     open_after=False, editor="typora")
        items = extract_section(orbit_env["proyecto_path"], "## 📎 Referencias")
        assert not any("Nota privada" in i for i in items)

    def test_note_creates_logbook_entry(self, orbit_env, monkeypatch):
        monkeypatch.setattr("core.add.open_file", lambda p, e: 0)
        run_add_note("testproj", "Análisis background", "apunte",
                     file_str=None, link=True, date_prefix=True,
                     open_after=False, editor="typora")
        logbook = orbit_env["proj_dir"] / "📓testproj.md"
        assert "Análisis background" in logbook.read_text()

    def test_note_import_file(self, orbit_env, tmp_path, monkeypatch):
        monkeypatch.setattr("core.add.open_file", lambda p, e: 0)
        src = tmp_path / "externa.md"
        src.write_text("# Nota externa\n\nContenido importado.\n")
        rc = run_add_note("testproj", "Nota externa", "apunte",
                          file_str=str(src), link=True, date_prefix=True,
                          open_after=False, editor="typora")
        assert rc == 0
        dest = orbit_env["proj_dir"] / "notes" / "externa.md"
        assert dest.exists()
        assert dest.read_text() == src.read_text()

    def test_note_overwrite_warning(self, orbit_env, monkeypatch, capsys):
        monkeypatch.setattr("core.add.open_file", lambda p, e: 0)
        run_add_note("testproj", "Misma nota", "apunte",
                     file_str=None, link=True, date_prefix=False,
                     open_after=False, editor="typora")
        capsys.readouterr()
        run_add_note("testproj", "Misma nota", "apunte",
                     file_str=None, link=True, date_prefix=False,
                     open_after=False, editor="typora")
        out = capsys.readouterr().out
        assert "⚠️" in out
        assert "sobreescribirá" in out

    def test_note_unknown_project(self, orbit_env, monkeypatch):
        monkeypatch.setattr("core.add.open_file", lambda p, e: 0)
        rc = run_add_note("proyecto_xyz_inexistente", "Nota", "apunte",
                          file_str=None, link=True, date_prefix=True,
                          open_after=False, editor="typora")
        assert rc != 0

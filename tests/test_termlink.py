"""test_termlink.py — enlaces clicables (OSC 8) en la salida de `ls`."""

import io

from core.termlink import ARROW, Linkifier, _LinkWriter, enabled, osc8


def _proj(tmp_path):
    p = tmp_path / "⚙️proyecto"
    (p / "notes").mkdir(parents=True)
    (p / "project.md").write_text("# p\n")
    (p / "notes" / "a b.md").write_text("x")
    (p / "ledger.md").write_text("x")
    return p


def test_osc8():
    assert osc8("t", "https://x") == f"\033]8;;https://x\033\\t {ARROW}\033]8;;\033\\"


def test_cabecera_fija_la_base_y_resuelve_relativos(tmp_path):
    p = _proj(tmp_path)
    lk = Linkifier("ls hl", {p.name: p})
    head = lk.line(f"[{p.name}]")
    assert (p / "project.md").resolve().as_uri() in head and ARROW in head
    out = lk.line("  📎 [Nota](./notes/a%20b.md) · [web](https://x.org)")
    assert (p / "notes" / "a b.md").resolve().as_uri() in out
    assert "\033]8;;https://x.org\033\\web ↗" in out
    assert "](" not in out


def test_relativo_sin_base_o_inexistente_se_queda(tmp_path):
    p = _proj(tmp_path)
    lk = Linkifier("ls log", {p.name: p})
    assert lk.line("[x](./notes/a.md)") == "[x](./notes/a.md)"          # sin base
    lk.line(f"[{p.name}] — 3 entradas")
    assert lk.line("[x](./no/existe.pdf)") == "[x](./no/existe.pdf)"


def test_ls_files_y_notes(tmp_path):
    p = _proj(tmp_path)
    lk = Linkifier("ls notes", {p.name: p})
    lk.line(f"[{p.name}/notes]")
    out = lk.line("  ✓  a b.md")
    assert out.startswith("  ✓  ") and (p / "notes" / "a b.md").resolve().as_uri() in out


def test_ledger(tmp_path):
    p = _proj(tmp_path)
    out = Linkifier("ls ledger", {p.name: p}).line(f"💶 Ledger — {p.name} · X")
    assert (p / "ledger.md").resolve().as_uri() in out


def test_tabla_de_proyectos_conserva_el_ancho(tmp_path):
    p = _proj(tmp_path)
    row = f"| {p.name}      | ⚙️   |"
    out = Linkifier("ls projects", {p.name: p}).line(row)
    import re
    visible = re.sub(r"\x1b\]8;;[^\x1b]*\x1b\\", "", out)
    assert len(visible) == len(row) and f"{p.name} {ARROW}" in visible


def test_writer_transforma_lineas_y_lo_pendiente_al_flush(tmp_path):
    p = _proj(tmp_path)
    out = io.StringIO()
    w = _LinkWriter(out, Linkifier("ls hl", {p.name: p}))
    w.write(f"[{p.name}]")
    w.write("\n")
    w.write("¿Proyecto? ")
    w.flush()
    assert ARROW in out.getvalue() and out.getvalue().endswith("¿Proyecto? ")


def test_desactivado_fuera_de_terminal(monkeypatch):
    assert not enabled(io.StringIO())
    class Tty(io.StringIO):
        def isatty(self):
            return True
    assert enabled(Tty())
    monkeypatch.setenv("ORBIT_NO_LINKS", "1")
    assert not enabled(Tty())


def test_day_enlaza_el_proyecto_en_mitad_de_la_linea(tmp_path):
    p = _proj(tmp_path)
    lk = Linkifier("day", {p.name: p})
    row = f"   14. ✏️              CPAN inscripcion  ❗⏩10-05  [{p.name}]"
    out = lk.line(row)
    assert out.startswith("   14. ✏️              CPAN inscripcion")
    assert f"[\033]8;;{(p / 'project.md').resolve().as_uri()}\033\\{p.name} {ARROW}" in out


def test_day_relativos_del_titulo_contra_su_proyecto(tmp_path):
    p = _proj(tmp_path)
    lk = Linkifier("day", {p.name: p})
    out = lk.line(f"    3. 🏁 [Nota](./notes/a%20b.md)  ⏩10-13  [{p.name}]")
    assert (p / "notes" / "a b.md").resolve().as_uri() in out and "](" not in out


def test_day_proyecto_inexistente_sin_enlace(tmp_path):
    p = _proj(tmp_path)
    lk = Linkifier("day", {p.name: p})
    row = "    2. ✏️  algo  [⚙️otro]"
    assert lk.line(row) == row
    assert lk.line("  ── ⏩ Decidir (25)") == "  ── ⏩ Decidir (25)"


def test_day_prompt_pendiente_sale_al_flush(tmp_path):
    p = _proj(tmp_path)
    out = io.StringIO()
    w = _LinkWriter(out, Linkifier("day", {p.name: p}))
    w.write(f"    1. ✏️ x  [{p.name}]\n")
    w.write("#? (número, q=salir) > ")
    w.flush()
    assert ARROW in out.getvalue() and out.getvalue().endswith("#? (número, q=salir) > ")

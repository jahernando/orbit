"""test_ledger_book.py — el libro de contabilidad propio (ADR-054).

Cubre:
  - init / is_book / convivencia con el logbook (read_movements despacha)
  - add: numeración, rastro en el logbook, validaciones (tipo, categoría,
    validez, compromiso)
  - edit: nota automática, --force sobre confirmadas, --confirm/--unconfirm,
    rastro al cambiar el título
  - close / cancel
  - derivados: ledger-summary.md + ledger.json v2, ledger.md intacto
  - check: numeración, validez, categoría, rastro
  - CLI: ledger add/edit sin terminal; log --entry gasto rechazado; --mark
"""

import json
from datetime import date
from decimal import Decimal

import pytest

from core.ledger import read_movements
from core.ledger_book import (
    BookError, add_movement, cancel_movement, close_commitment, edit_movement,
    init_book, is_book, parse_book, read_book,
)

D = Decimal
T = date(2026, 10, 5)


@pytest.fixture
def proj(tmp_path, monkeypatch):
    type_dir = tmp_path / "⚙️gestion"
    type_dir.mkdir()
    p = type_dir / "⚙️testproj"
    p.mkdir()
    (p / "project.md").write_text("# ⚙️testproj\n")
    (p / "logbook.md").write_text("# Logbook — ⚙️testproj\n\n")
    cloud = tmp_path / "cloudroot"
    cloud.mkdir()
    (tmp_path / "orbit.json").write_text(json.dumps({"cloud_root": str(cloud)}))
    monkeypatch.setattr("core.config.ORBIT_HOME", tmp_path)
    monkeypatch.setattr("core.config._ORBIT_JSON", tmp_path / "orbit.json")
    monkeypatch.setattr("core.config.PROJECTS_DIR", tmp_path)
    monkeypatch.setattr("core.log.PROJECTS_DIR", tmp_path)
    monkeypatch.setattr("core.deliver.ORBIT_DIR", tmp_path)
    return p


@pytest.fixture
def book(proj):
    init_book(proj, "1234.AB12.64100", date(2026, 8, 6), date(2029, 8, 5))
    return proj


def _add(proj, **kw):
    base = dict(tag="gasto", title="Dietas", when=date(2026, 9, 1),
                payee="Ana", amount="100", category="viajes")
    base.update(kw)
    return add_movement(proj, **base)


# ── init y lectura ───────────────────────────────────────────────────────────

class TestInit:

    def test_cabecera(self, book):
        b = read_book(book)
        assert is_book(book)
        assert b.partida == "1234.AB12.64100"
        assert (b.valid_from, b.valid_to) == (date(2026, 8, 6), date(2029, 8, 5))
        assert b.entries == []

    def test_no_dos_veces(self, book):
        with pytest.raises(BookError, match="ya tiene libro"):
            init_book(book, "X", date(2026, 1, 1), date(2027, 1, 1))

    def test_no_si_el_logbook_tiene_movimientos(self, proj):
        (proj / "logbook.md").write_text(
            "# Logbook\n\n2026-09-01 💶 Fra #gasto\n  🏷️ X · 👤 Y · 💶 -10,00\n")
        with pytest.raises(BookError, match="migr"):
            init_book(proj, "X", date(2026, 1, 1), date(2027, 1, 1))

    def test_derivado_viejo_no_es_libro(self, proj):
        (proj / "ledger.md").write_text("*🚀 creado por `ledger`*\n\n# 💶 Ledger\n\n"
                                        "| Resumen | € |\n|---|---:|\n")
        assert not is_book(proj)

    def test_tolera_emoji_sin_selector(self, tmp_path):
        text = ("- 🏷 Partida: X\n- 📆 Validez: 2026-01-01 → 2026-12-31\n\n"
                "- 💶 0001 Fra #gasto\n  📅 2026-02-01 · 🗂 viajes · 👤 Y · 💶 -5,00\n"
                "  ☑ 2026-03-01 · A1\n")
        b = parse_book(text, tmp_path / "ledger.md")
        e = b.entries[0]
        assert b.partida == "X" and e.category == "viajes" and e.confirmed == ("2026-03-01", "A1")
        assert b.problems == []


# ── add ──────────────────────────────────────────────────────────────────────

class TestAdd:

    def test_numera_y_deja_rastro(self, book):
        e1 = _add(book, tag="ingreso", title="Dotación", payee="Agencia",
                  amount="20.000,00", category=None)
        e2 = _add(book)
        assert (e1.num, e2.num) == ("0001", "0002")
        assert e1.amount == D("20000.00") and e2.amount == D("-100.00")
        text = (book / "ledger.md").read_text()
        assert "- 💶 0002 Dietas #gasto\n  📅 2026-09-01 · 🗂️ viajes · 👤 Ana · 💶 -100,00" in text
        log = (book / "logbook.md").read_text()
        assert "2026-09-01 💶 Dietas · ledger 0002 #gasto" in log
        assert "100" not in log                       # sin importe en el rastro

    def test_no_log(self, book):
        _add(book, trail=False)
        assert "ledger 0001" not in (book / "logbook.md").read_text()

    def test_read_movements_lee_el_libro(self, book):
        _add(book)
        movs, problems = read_movements(book)
        assert problems == []                         # el rastro no se lee como movimiento
        assert [(m.num, m.amount) for m in movs] == [("0001", D("-100.00"))]

    def test_categoria_obligatoria_y_cerrada(self, book):
        with pytest.raises(BookError, match="necesita categoría"):
            _add(book, category=None)
        with pytest.raises(BookError, match="desconocida"):
            _add(book, category="comida")

    def test_fuera_de_validez(self, book):
        with pytest.raises(BookError, match="fuera de la validez"):
            _add(book, when=date(2026, 8, 1))
        assert _add(book, when=date(2026, 8, 1), force=True).num == "0001"

    def test_signo_rechazado(self, book):
        with pytest.raises(BookError, match="sin signo"):
            _add(book, amount="-100")

    def test_compromiso_y_gastos(self, book):
        c = _add(book, tag="compromiso", title="Vuelo", amount="1000")
        g = _add(book, title="Factura", amount="400", commit="1")
        assert g.commit == c.num == "0001"
        with pytest.raises(BookError, match="no es un compromiso"):
            _add(book, commit=g.num)
        _add(book, title="Factura 2", amount="100", commit="0001", closes=True)
        with pytest.raises(BookError, match="ya está cerrado"):
            _add(book, commit="0001")
        from core.ledger import summarize
        s = summarize(read_movements(book)[0])
        assert s.committed == D("0.00") and s.spent == D("-500.00")

    def test_justificante_a_ledger_logs(self, book, tmp_path):
        pdf = tmp_path / "factura.pdf"
        pdf.write_bytes(b"%PDF")
        e = _add(book, doc=str(pdf))
        assert e.link.startswith("./cloud/ledger-logs/") and e.link.endswith("_factura.pdf")

    def test_referencia_repetida(self, book):
        _add(book, op_id="F-1")
        with pytest.raises(BookError, match="ya está en la entrada 0001"):
            _add(book, op_id="F-1")


# ── edit ─────────────────────────────────────────────────────────────────────

class TestEdit:

    def test_nota_automatica(self, book):
        _add(book)
        _, e, shown = edit_movement(book, "1", amount="90", payee="A. G.", today=T)
        assert e.amount == D("-90.00") and e.payee == "A. G."
        assert e.notes == ["2026-10-05 modificado: 👤 Ana → A. G. · 💶 -100,00 → -90,00"]
        assert read_book(book).get("1").notes == e.notes

    def test_confirmar_sin_cambios_no_deja_nota(self, book):
        _add(book)
        _, e, _ = edit_movement(book, "1", confirm="2026/000123", today=T)
        assert e.confirmed == ("2026-10-05", "2026/000123") and e.notes == []
        assert "  ☑️ 2026-10-05 · 2026/000123" in (book / "ledger.md").read_text()

    def test_confirmar_con_cambio(self, book):
        _add(book)
        _, e, _ = edit_movement(book, "1", confirm="A1", amount="95", today=T)
        assert e.confirmed == ("2026-10-05", "A1")
        assert e.notes == ["2026-10-05 modificado al confirmar: 💶 -100,00 → -95,00"]

    def test_confirmada_exige_force_y_pierde_el_check(self, book):
        _add(book)
        edit_movement(book, "1", confirm="A1", today=T)
        with pytest.raises(BookError, match="--force"):
            edit_movement(book, "1", amount="80", today=T)
        _, e, _ = edit_movement(book, "1", amount="80", force=True, today=T)
        assert e.confirmed is None
        assert e.notes[-1].endswith("sin ☑️ (era A1)")

    def test_nota_libre_en_confirmada_sin_force(self, book):
        _add(book)
        edit_movement(book, "1", confirm="A1", today=T)
        _, e, _ = edit_movement(book, "1", note="pagado en CHF", today=T)
        assert e.confirmed and e.notes == ["pagado en CHF"]

    def test_unconfirm(self, book):
        _add(book)
        edit_movement(book, "1", confirm="A1", today=T)
        _, e, _ = edit_movement(book, "1", unconfirm=True, today=T)
        assert e.confirmed is None and "retirada (era A1)" in e.notes[-1]

    def test_otro_id_exige_force(self, book):
        _add(book)
        edit_movement(book, "1", confirm="A1", today=T)
        with pytest.raises(BookError, match="ya está confirmada con A1"):
            edit_movement(book, "1", confirm="B2", today=T)

    def test_titulo_actualiza_el_rastro(self, book):
        _add(book)
        edit_movement(book, "1", title="Dietas CONF", today=T)
        log = (book / "logbook.md").read_text()
        assert "Dietas CONF · ledger 0001 #gasto" in log
        assert "Dietas · ledger 0001" not in log

    def test_nada_que_cambiar(self, book):
        _add(book)
        with pytest.raises(BookError, match="nada que cambiar"):
            edit_movement(book, "1", amount="100")

    def test_no_toca_otras_entradas(self, book):
        _add(book)
        _add(book, title="Otra")
        edit_movement(book, "1", amount="1", today=T)
        assert read_book(book).get("2").amount == D("-100.00")


# ── close / cancel ───────────────────────────────────────────────────────────

class TestCloseCancel:

    def test_close(self, book):
        _add(book, tag="compromiso", title="Vuelo", amount="1000")
        e = close_commitment(book, "1", today=T)
        assert e.closes and e.notes == ["2026-10-05 cerrado a mano"]
        with pytest.raises(BookError, match="ya está cerrado"):
            close_commitment(book, "1")

    def test_cancel_deja_de_contar(self, book):
        _add(book)
        _add(book, title="Error")
        cancel_movement(book, "2", today=T)
        b = read_book(book)
        assert [e.num for e in b.entries] == ["0001", "0002"]
        assert [m.num for m in read_movements(book)[0]] == ["0001"]
        assert b.next_num() == "0003"

    def test_cancel_compromiso_con_gastos(self, book):
        _add(book, tag="compromiso", title="Vuelo", amount="1000")
        _add(book, commit="1")
        with pytest.raises(BookError, match="tiene gastos"):
            cancel_movement(book, "1")

    def test_cancel_confirmada(self, book):
        _add(book)
        edit_movement(book, "1", confirm="A1")
        with pytest.raises(BookError, match="--force"):
            cancel_movement(book, "1")


# ── derivados ────────────────────────────────────────────────────────────────

class TestViews:

    def test_resumen_y_json(self, book):
        from views.ledger import write_ledger
        _add(book, tag="ingreso", title="Dotación", payee="Agencia", amount="1000",
             category=None)
        _add(book, tag="compromiso", title="Vuelo", amount="300")
        _add(book, title="Dietas", amount="100", category="viajes")
        edit_movement(book, "3", confirm="A1")
        truth = (book / "ledger.md").read_text()
        write_ledger(book, force=True)
        assert (book / "ledger.md").read_text() == truth          # la verdad no se toca
        summary = (book / "ledger-summary.md").read_text()
        assert "| Dotación | 0,00 | 1.000,00 |" in summary
        assert "| Gastado | -100,00 | -100,00 |" in summary
        assert "| **Disponible** | -100,00 | **600,00** |" in summary
        assert "| viajes | -100,00 | -300,00 | -400,00 |" in summary
        assert "| 0002 | Vuelo |" in summary
        data = json.loads((book / "ledger.json").read_text())
        assert data["version"] == 2 and data["valid_to"] == "2029-08-05"
        row = data["movements"][2]
        assert row["key"] == "0003" and row["validated"]["id"] == "A1"
        assert data["summary"]["available"] == "600.00"


# ── check ────────────────────────────────────────────────────────────────────

class TestCheck:

    def _msgs(self, proj):
        from views.ledger_check import check_ledger
        return [(f.level, f.msg) for f in check_ledger(proj, today=T)]

    def test_limpio(self, book):
        _add(book)
        assert self._msgs(book) == []

    def test_errores(self, book):
        _add(book)
        text = (book / "ledger.md").read_text()
        text += ("\n- 💶 0003 Hueco #gasto\n"
                 "  📅 2025-01-01 · 🗂️ comida · 👤 X · 💶 -1,00\n")
        (book / "ledger.md").write_text(text)
        msgs = " | ".join(m for _, m in self._msgs(book))
        assert "no correlativa" in msgs
        assert "fuera de la validez" in msgs
        assert "comida" in msgs
        assert "sin rastro en el logbook: 0003" in msgs

    def test_doctor_ve_los_errores(self, book):
        from views.ledger_check import ledger_errors
        (book / "ledger.md").write_text((book / "ledger.md").read_text()
                                        + "\n- 💶 0001 Sin importe #gasto\n  📅 2026-09-01\n")
        assert any("sin importe" in f.msg for f in ledger_errors(book))


# ── archive ──────────────────────────────────────────────────────────────────

def test_archive_no_ofrece_arrastre_con_libro(book):
    from core.archive import _carry_preview
    _add(book)
    assert _carry_preview(book, date(2027, 1, 1))[0] == 0


# ── CLI ──────────────────────────────────────────────────────────────────────

class TestCLI:

    def _run(self, *argv):
        import orbit
        args = orbit._build_parser().parse_args(list(argv))
        return orbit.cmd_ledger(args) if argv[0] == "ledger" else orbit.cmd_log(args)

    def test_init_add_edit(self, proj, capsys):
        assert self._run("ledger", "testproj", "init", "--partida", "P1",
                         "--from", "2026-01-01", "--to", "2026-12-31") == 0
        assert self._run("ledger", "testproj", "add", "--type", "gasto",
                         "--title", "Fra", "--payee", "Y", "--amount", "10",
                         "--cat", "fungible", "--date", "2026-03-01") == 0
        out = capsys.readouterr().out
        assert "ledger 0001 · gasto -10,00" in out and "disponible -10,00" in out
        assert self._run("ledger", "testproj", "edit", "1", "--confirm", "U-1") == 0
        assert read_book(proj).get("1").confirmed[1] == "U-1"
        assert (proj / "ledger-summary.md").exists()

    def test_mark_se_traduce(self, book):
        _add(book)
        assert self._run("ledger", "testproj", "--mark", "0001", "U-9") == 0
        assert read_book(book).get("1").confirmed[1] == "U-9"

    def test_log_entry_rechazado(self, book, capsys):
        assert self._run("log", "testproj", "Fra", "--entry", "gasto",
                         "--amount", "10", "--payee", "Y") == 1
        assert "ledger testproj add" in capsys.readouterr().out

    def test_add_sin_libro(self, proj, capsys):
        assert self._run("ledger", "testproj", "add", "--type", "gasto",
                         "--title", "Fra", "--payee", "Y", "--amount", "10",
                         "--cat", "fungible") == 1
        assert "init" in capsys.readouterr().out


def test_interrogador_pregunta_lo_que_falta(book, monkeypatch):
    import builtins
    import orbit
    from views.ledger_book import interrogate_add
    _add(book, tag="compromiso", title="Vuelo", amount="1000")
    answers = iter(["3", "", "2026-09-10", "Factura vuelo", "Axencia", "900",
                    "1", "1", "s", "F-7", ""])
    monkeypatch.setattr(builtins, "input", lambda _p="": next(answers))
    args = orbit._build_parser().parse_args(["ledger", "testproj", "add"])
    interrogate_add(book, args)
    assert (args.mov_type, args.title, args.payee, args.amount, args.cat,
            args.commit, args.closes, args.op_id) == (
        "gasto", "Factura vuelo", "Axencia", "900", "viajes", "0001", True, "F-7")


# ── migrate (F2) ─────────────────────────────────────────────────────────────

OLD_LOG = """# Logbook — ⚙️testproj

2026-08-11 💶 [Ingreso](./cloud/logs/dot.pdf) #ingreso
  🏷️ 2010.X.64100 · 👤 Agencia · 💶 20.000,00

2026-08-20 📝 Una nota cualquiera #apunte

2026-08-31 💶 [Folla CONF](./cloud/logs/folla%20conf.pdf) #compromiso
  🏷️ 2010.X.64100 · 👤 CONF · 💶 -550,00 · 🆔 P01

2026-09-18 💶 [Vuelo](./cloud/logs/CM01.pdf) #compromiso
  🏷️ 2010.X.64100 · 👤 VIAJES EJEMPLO · 💶 -1.250,00 · 🆔 CM01

2026-09-18 📝 [Hoja pedido](./cloud/logs/CM01.pdf) #apunte

2026-09-20 💶 Factura CONF #gasto
  🏷️ 2010.X.64100 · 👤 CONF · 💶 -500,00 · 🔗 P01 · 🔒 cierra
  📝 al cambio
"""


@pytest.fixture
def old(proj):
    (proj / "logbook.md").write_text(OLD_LOG)
    logs = proj / "cloud" / "logs"
    logs.mkdir(parents=True)
    for name in ("dot.pdf", "folla conf.pdf", "CM01.pdf", "otro.pdf"):
        (logs / name).write_bytes(b"%PDF")
    (proj / "highlights.md").write_text("- 📎 [pedido](./cloud/logs/CM01.pdf) #referencia\n")
    return proj


class TestMigrate:

    CATS = {"2": "congresos", "3": "viajes", "4": "congresos"}

    def _plan(self, proj, **kw):
        from core.ledger_book import plan_migration
        kw.setdefault("cats", self.CATS)
        return plan_migration(proj, date(2026, 8, 6), date(2029, 8, 5), **kw)

    def test_plan(self, old):
        plan = self._plan(old)
        assert plan.errors == [] and plan.missing_cat == []
        assert [(e.num, e.tag, e.op_id, e.commit) for e in plan.entries] == [
            ("0001", "ingreso", None, None), ("0002", "compromiso", None, None),
            ("0003", "compromiso", "CM01", None), ("0004", "gasto", None, "0002")]
        assert sorted(s.name for s, _ in plan.moves) == ["CM01.pdf", "dot.pdf",
                                                        "folla conf.pdf"]
        assert {p.name: n for p, n in plan.rewrites.items()} == {
            "logbook.md": 1, "highlights.md": 1}
        assert (old / "logbook.md").read_text() == OLD_LOG     # no toca nada

    def test_faltan_categorias_y_validez(self, old):
        plan = self._plan(old, cats={})
        assert plan.missing_cat == ["0002", "0003", "0004"]
        plan = self._plan(old, cats=self.CATS, partida=None)
        from core.ledger_book import plan_migration
        late = plan_migration(old, date(2026, 9, 1), date(2029, 1, 1), cats=self.CATS)
        assert any("fuera de la validez" in e for e in late.errors)

    def test_apply(self, old):
        from core.ledger_book import apply_migration
        from views.ledger_check import check_ledger
        apply_migration(self._plan(old))
        b = read_book(old)
        assert b.partida == "2010.X.64100" and len(b.entries) == 4
        assert b.get("4").commit == "0002" and b.get("4").closes
        assert b.get("4").notes == ["al cambio"]
        assert b.get("2").link == "./cloud/ledger-logs/folla%20conf.pdf"
        assert (old / "cloud" / "ledger-logs" / "CM01.pdf").exists()
        assert not (old / "cloud" / "logs" / "CM01.pdf").exists()
        assert (old / "cloud" / "logs" / "otro.pdf").exists()   # lo ajeno no se mueve
        log = (old / "logbook.md").read_text()
        assert "2026-09-20 💶 Factura CONF · ledger 0004 #gasto\n" in log
        assert "2026-08-11 💶 Ingreso · ledger 0001 #ingreso" in log
        assert "💶 -500" not in log and "🏷️" not in log
        assert "[Hoja pedido](./cloud/ledger-logs/CM01.pdf)" in log
        assert "Una nota cualquiera" in log
        assert "./cloud/ledger-logs/CM01.pdf" in (old / "highlights.md").read_text()
        from core.ledger import summarize
        assert summarize(read_movements(old)[0]).available == D("18250.00")
        errors = [f.msg for f in check_ledger(old, today=T) if f.level == "error"]
        assert errors == []

    def test_con_libro_no_migra(self, book):
        assert any("ya tiene libro" in e for e in self._plan(book).errors)

    def test_cli_dry_run(self, old, capsys):
        import orbit
        args = orbit._build_parser().parse_args(
            ["ledger", "testproj", "migrate", "--from", "2026-08-06", "--to",
             "2029-08-05", "--cats", "2=congresos,3=viajes,4=congresos", "--dry-run"])
        assert orbit.cmd_ledger(args) == 0
        out = capsys.readouterr().out
        assert "0004" in out and "dry-run" in out
        assert not is_book(old)


# ── project.md y ls ledger ───────────────────────────────────────────────────

class TestProjectLinkAndLs:

    FOOTER = ("# ⚙️testproj\n\n---\n[logbook](./logbook.md) · [highlights](./highlights.md)"
              " · [agenda](./agenda.md) · [notes](./notes/) · [cloud](/x)\n")

    def test_init_enlaza_en_el_pie(self, proj):
        (proj / "project.md").write_text(self.FOOTER)
        init_book(proj, "P", date(2026, 1, 1), date(2026, 12, 31))
        text = (proj / "project.md").read_text()
        assert ("[agenda](./agenda.md) · [ledger](./ledger.md) "
                "([resumen](./ledger-summary.md)) · [notes]") in text
        from core.ledger_book import link_in_project_md
        assert link_in_project_md(proj) is False               # idempotente

    def test_sin_pie_lo_anade_al_final(self, book):
        assert "(./ledger.md)" in (book / "project.md").read_text()

    def test_ls_ledger_lista_el_libro(self, book, capsys):
        from views.ledger import run_ls_ledger
        _add(book, tag="ingreso", title="Dotación", payee="Agencia", amount="1000",
             category=None)
        _add(book)
        edit_movement(book, "2", confirm="A1")
        _add(book, title="Error")
        cancel_movement(book, "3")
        run_ls_ledger("testproj")
        out = capsys.readouterr().out
        assert "0002  2026-09-01  gasto       viajes" in out
        assert "☑️ A1" in out and "🚫 anulada" in out
        assert "Validado ☑️" in out and "Por categoría: viajes -100,00" in out


# ── elegir la entrada sin saber el nº ────────────────────────────────────────

class TestPick:

    def _run(self, *argv):
        import orbit
        return orbit.cmd_ledger(orbit._build_parser().parse_args(["ledger", "testproj", *argv]))

    def test_por_texto(self, book):
        _add(book, title="Vuelo Ginebra", payee="VIAJES EJEMPLO")
        _add(book, title="Dietas Madrid", payee="Laura Gómez")
        assert self._run("edit", "madrid", "--amount", "50") == 0
        assert read_book(book).get("2").amount == D("-50.00")
        assert self._run("edit", "laura", "--nota", "x") == 0      # sin tildes
        assert read_book(book).get("2").notes[-1] == "x"

    def test_por_numero_sin_ceros(self, book):
        _add(book)
        assert self._run("edit", "1", "--cat", "fungible") == 0

    def test_ambiguo_sin_terminal(self, book, capsys):
        _add(book, title="Dietas Madrid")
        _add(book, title="Dietas Lisboa")
        assert self._run("edit", "dietas", "--amount", "1") == 1
        out = capsys.readouterr().out
        assert "¿cuál?" in out and "0001" in out and "0002" in out

    def test_ambiguo_en_terminal(self, book, monkeypatch):
        import builtins, sys
        _add(book, title="Dietas Madrid")
        _add(book, title="Dietas Lisboa")
        monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
        monkeypatch.setattr(builtins, "input", lambda _p="": "lisboa")
        assert self._run("edit", "dietas", "--amount", "1") == 0
        assert read_book(book).get("2").amount == D("-1.00")

    def test_close_solo_compromisos_abiertos(self, book, capsys):
        _add(book, tag="compromiso", title="Vuelo", amount="10")
        _add(book, title="Vuelo factura")
        assert self._run("close", "vuelo") == 0
        assert read_book(book).get("1").closes

    def test_doc(self, book, tmp_path):
        _add(book, title="Factura vuelo")
        pdf = tmp_path / "definitiva.pdf"
        pdf.write_bytes(b"%PDF")
        assert self._run("edit", "factura", "--doc", str(pdf)) == 0
        e = read_book(book).get("1")
        assert e.link.endswith("_definitiva.pdf") and "justificante — →" in e.notes[-1]

    def test_doc_posicional(self, book, tmp_path):
        _add(book, title="Factura vuelo")
        pdf = tmp_path / "otra.pdf"
        pdf.write_bytes(b"%PDF")
        assert self._run("edit", "vuelo", str(pdf)) == 0
        assert read_book(book).get("1").link.endswith("_otra.pdf")


class TestAddPositionals:

    def _run(self, *argv):
        import orbit
        return orbit.cmd_ledger(orbit._build_parser().parse_args(["ledger", "testproj", *argv]))

    FLAGS = ("--type", "gasto", "--payee", "Ana", "--amount", "10", "--cat", "viajes",
             "--date", "2026-09-21")

    def test_titulo_y_fichero(self, book, tmp_path):
        pdf = tmp_path / "CL0000_Dietas_fdo.pdf"
        pdf.write_bytes(b"%PDF")
        assert self._run("add", "Dietas Ana Escuela", str(pdf), *self.FLAGS) == 0
        e = read_book(book).get("1")
        assert e.title == "Dietas Ana Escuela" and e.link.endswith("_CL0000_Dietas_fdo.pdf")

    def test_fichero_y_titulo_al_reves(self, book, tmp_path):
        pdf = tmp_path / "f.pdf"
        pdf.write_bytes(b"%PDF")
        assert self._run("add", str(pdf), "Dietas", *self.FLAGS) == 0
        assert read_book(book).get("1").title == "Dietas"

    def test_ruta_que_no_existe(self, book, capsys):
        assert self._run("add", "Dietas", "/no/existe.pdf", *self.FLAGS) == 1
        assert "no encuentro el fichero /no/existe.pdf" in capsys.readouterr().out

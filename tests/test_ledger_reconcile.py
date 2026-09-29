"""test_ledger_reconcile.py — `ledger --check <ficheros de la USC>` (ADR-053).

Los ficheros de la USC son **sintéticos**: misma estructura que los reales
(tabla HTML en latin-1 con las columnas de `obrigasexcel.xls`; texto de
`pdftotext -layout` del PDF de ejecución), con datos inventados. Los reales
llevan nombres y proyectos que no van a un repo público.
"""

import builtins
from datetime import date
from decimal import Decimal

import pytest

from core.ledger import build_operations, read_movements, rewrite_ids
from views.ledger_reconcile import (
    PROBABLE, SURE, Aut, Mod, Obl, UscReport, _apply, load_report,
    parse_execution_text, parse_obligations, reconcile,
)
from views.ledger_check import run_ledger_check

D = Decimal

_HEAD = ["Exercicio", "Cód.Aut", "DatAut", "ImpAut", "SaldoAut", "SubCpto",
         "Nfac", "DataFac", "Concepto", "Nif", "Perceptor", "Base", "Ive",
         "ImpObr", "ImpOrzamento", "DataPagmto"]


def _xls(*rows) -> bytes:
    """Como el excel de obrigas de la USC: HTML, latin-1, CRLF."""
    cells = lambda tag, r: "".join(f"<{tag}>{c}</{tag}>" for c in r)
    html = ("\r\n<TABLE border=1>\r\n<TR><TH>Partida: 2010.XXXX.64100</TH></TR>\r\n"
            "<TR><TH></TH></TR>\r\n<TR>" + cells("TH", _HEAD) + "</TR>\r\n"
            + "".join(f"<TR>{cells('TD', r)}</TR>\r\n" for r in rows)
            + "</TABLE>")
    return html.encode("latin-1")


SIN_OBLIGA = ["2026", "AUT-001", "31/08/2026", "300,00", "300,00", "", "", "",
              "", "", "", "0,00", "0,00", "0,00", "0,00", ""]
CON_OBLIGA = ["2026", "CM26XX0001", "18/09/2026", "1.578,64", "0,00", "",
              "F-4471", "02/10/2026", "Vuelo", "A12345678", "AXENCIA VIAXES SA",
              "1.305,04", "274,06", "1.579,10", "1.580,10", "15/10/2026"]

EXECUCION = """\
Execución Orzamentaria da Partida                        2010.XXXX.64100
Resumo

Credito total:     20.000,00   Gastos T. Orzamentado(inc.saldo auts):   1.878,64   Dispoñible:   18.121,36

Modificacións Orzamentarias          (Excluídas as incorporacións de remanentes)
Exercicio        Data Concepto                                  Positivas         Negativas
2026 06/08/2026        Dotacion anualidade 2026                 20.000,00            0,00
                                                                20.000,00            0,00
Autorizacións Pendentes
Exer.       Aut.                  Data         Comentario              ImpAut      Obrigas Saldo Aut.
2026 AUT-001                      31/08/2026 CONGRESO SL                  300,00      0,00      300,00
2026 CM26XX0001                   18/09/2026 AXENCIA VIAXES, S.A. (Dpto.   1.578,64    0,00    1.578,64
                                               Empresas)
                                               Total Aut.:                     1.878,64
Obrigas
Exer.Nif   Perceptor   NúmFac   DataFac    DataPago          Obrigas Orzamento
                                           Total:                    0,00          0,00
"""


# ── Lectura ──────────────────────────────────────────────────────────────────

class TestParse:

    def test_obrigas(self):
        auts, obls = parse_obligations(_xls(SIN_OBLIGA, CON_OBLIGA).decode("latin-1"))
        assert [a.id for a in auts] == ["AUT-001", "CM26XX0001"]
        assert auts[0].amount == D("300.00") and auts[0].date == date(2026, 8, 31)
        assert len(obls) == 1                  # la autorización sin obriga no cuenta
        o = obls[0]
        assert (o.aut_id, o.invoice, o.amount) == ("CM26XX0001", "F-4471", D("1580.10"))
        assert o.payee == "AXENCIA VIAXES SA" and o.paid == date(2026, 10, 15)

    def test_obrigas_sin_cabecera(self):
        with pytest.raises(ValueError, match="cabecera"):
            parse_obligations("<table><tr><td>nada</td></tr></table>")

    def test_ejecucion(self):
        r = parse_execution_text(EXECUCION)
        assert (r.credit, r.spent, r.available) == (D("20000.00"), D("1878.64"),
                                                    D("18121.36"))
        assert r.mods == [Mod(date(2026, 8, 6), "Dotacion anualidade 2026",
                              D("20000.00"))]
        assert [(a.id, a.payee, a.amount) for a in r.auts] == [
            ("AUT-001", "CONGRESO SL", D("300.00")),
            ("CM26XX0001", "AXENCIA VIAXES, S.A. (Dpto.", D("1578.64"))]

    def test_load_report_junta_pdf_y_excel(self, tmp_path, monkeypatch):
        pdf = tmp_path / "Execucion.pdf"
        pdf.write_bytes(b"%PDF-1.3 falso")
        xls = tmp_path / "obrigasexcel.xls"
        xls.write_bytes(_xls(SIN_OBLIGA, CON_OBLIGA))
        monkeypatch.setattr("views.ledger_reconcile._pdf_text", lambda p: EXECUCION)
        r = load_report([pdf, xls])
        assert r.has_obls and r.credit == D("20000.00")
        assert len(r.auts) == 2                    # sin duplicar por id
        assert r.auts[0].payee == "CONGRESO SL"    # el tercero viene del PDF


# ── Emparejado ───────────────────────────────────────────────────────────────

@pytest.fixture
def proj(tmp_path, monkeypatch):
    type_dir = tmp_path / "⚙️gestion"
    type_dir.mkdir()
    p = type_dir / "⚙️proyx"
    p.mkdir()
    (p / "project.md").write_text("# ⚙️proyx\n")
    (p / "logbook.md").write_text("# Logbook\n\n")
    monkeypatch.setattr("core.config.ORBIT_HOME", tmp_path)
    monkeypatch.setattr("core.config._ORBIT_JSON", tmp_path / "orbit.json")
    monkeypatch.setattr("core.log.PROJECTS_DIR", tmp_path)
    return p


def _write(proj, *entries):
    (proj / "logbook.md").write_text("# Logbook\n\n" + "\n".join(
        f"{d} 💶 {h}\n  {b}\n" for d, h, b in entries))


LEDGER = (
    ("2026-08-06", "Dotación #ingreso", "🏷️ p · 💶 20.000,00"),
    ("2026-08-30", "Folla congreso #pedido", "👤 Congreso SL · 💶 -300,00 · 🆔 P01"),
    ("2026-09-18", "Folla vuelo #pedido",
     "👤 Axencia Viaxes · 💶 -1.578,64 · 🆔 CM26XX0001"),
    ("2026-09-20", "Folla hotel #pedido", "👤 Hotel · 💶 -420,00 · 🆔 P02"),
    ("2026-10-02", "Factura vuelo #gasto",
     "👤 Axencia Viaxes · 💶 -1.580,10 · 🔗 CM26XX0001"),
    ("2026-08-31", "Dietas #gasto", "👤 Ana · 💶 -1.408,32"),
)


def _report():
    auts, obls = parse_obligations(_xls(SIN_OBLIGA, CON_OBLIGA).decode("latin-1"))
    r = parse_execution_text(EXECUCION)
    r.obls, r.has_obls = obls, True
    return r


class TestReconcile:

    def test_emparejado(self, proj):
        _write(proj, *LEDGER)
        res = reconcile(read_movements(proj)[0], _report())

        auts = res["auts"]
        how = {p.usc.id: (p.how, p.mov.concept) for p in auts.pairs}
        assert how == {"CM26XX0001": (SURE, "Folla vuelo"),
                       "AUT-001": (PROBABLE, "Folla congreso")}
        assert [m.concept for m in auts.only_ledger] == ["Folla hotel"]

        obls = res["obls"]
        assert [(p.usc.invoice, p.how) for p in obls.pairs] == [("F-4471", PROBABLE)]
        assert [m.concept for m in obls.only_ledger] == ["Dietas"]

        assert [p.how for p in res["mods"].pairs] == [PROBABLE]

    def test_solo_en_la_usc(self, proj):
        _write(proj, LEDGER[0])
        res = reconcile(read_movements(proj)[0], _report())
        assert {a.id for a in res["auts"].only_usc} == {"AUT-001", "CM26XX0001"}
        assert [o.invoice for o in res["obls"].only_usc] == ["F-4471"]

    def test_importe_distinto_por_id(self, proj):
        _write(proj, ("2026-09-18", "Folla #pedido", "💶 -1.500,00 · 🆔 CM26XX0001"))
        pair = reconcile(read_movements(proj)[0], _report())["auts"].pairs[0]
        assert pair.how == SURE and "importe distinto" in pair.notes[0]

    def test_tercero_distinto_no_empareja(self, proj):
        _write(proj, ("2026-08-31", "Folla #pedido", "👤 Otra Casa · 💶 -300,00 · 🆔 P01"))
        rec = reconcile(read_movements(proj)[0], _report())["auts"]
        assert "AUT-001" in {a.id for a in rec.only_usc}

    def test_sin_excel_no_compara_facturas(self, proj):
        _write(proj, *LEDGER)
        res = reconcile(read_movements(proj)[0], parse_execution_text(EXECUCION))
        assert "obls" not in res


# ── Escritura del número oficial ─────────────────────────────────────────────

class TestRewrite:

    def test_pedido_provisional_y_sus_referencias(self, proj):
        _write(proj,
               ("2026-09-01", "Folla #pedido", "👤 X · 💶 -100,00 · 🆔 P01"),
               ("2026-09-10", "Fra 1 #gasto", "💶 -40,00 · 🔗 P01 parcial"),
               ("2026-09-20", "Fra 2 #gasto", "💶 -60,00 · 🔗 P01"),
               ("2026-09-21", "Otra #gasto", "💶 -1,00 · 🔗 P011"))
        folla = read_movements(proj)[0][0]
        assert rewrite_ids(proj, folla.raw, "CM26XX0009") == 3
        movs, _ = read_movements(proj)
        assert movs[0].op_id == "CM26XX0009"
        assert [m.ref for m in movs[1:]] == ["CM26XX0009", "CM26XX0009", "P011"]
        assert movs[1].partial
        ops, problems = build_operations(movs)
        assert ops[0].state == "cerrado"

    def test_gasto_sin_id(self, proj):
        _write(proj, ("2026-10-02", "Fra #gasto", "👤 X · 💶 -10,00"))
        rewrite_ids(proj, read_movements(proj)[0][0].raw, "F-1")
        text = (proj / "logbook.md").read_text()
        assert "  👤 X · 💶 -10,00 · 🆔 F-1\n" in text

    def test_apply_pregunta_una_a_una(self, proj, monkeypatch):
        _write(proj, *LEDGER)
        res = reconcile(read_movements(proj)[0], _report())
        monkeypatch.setattr("sys.stdin", type("T", (), {"isatty": lambda s: True})())
        answers = iter(["s", "n"])                 # sí a la aut., no a la factura
        monkeypatch.setattr(builtins, "input", lambda _p="": next(answers))
        assert _apply(proj, res) == 1
        ids = {m.concept: m.op_id for m in read_movements(proj)[0]}
        assert ids["Folla congreso"] == "AUT-001"
        assert ids["Factura vuelo"] is None


def test_fichero_inexistente(proj, capsys):
    assert run_ledger_check("proyx", files=["/no/existe.xls"]) == 1


# ── `--check` con ficheros: guarda, anota, columna USC ───────────────────────

@pytest.fixture
def usc_files(tmp_path, monkeypatch):
    pdf = tmp_path / "dl" / "Execucion_2010.XXXX.64100.pdf"
    pdf.parent.mkdir()
    pdf.write_bytes(b"%PDF-1.3 falso")
    xls = tmp_path / "dl" / "obrigasexcel (6).xls"
    xls.write_bytes(_xls(SIN_OBLIGA, CON_OBLIGA))
    text = EXECUCION.replace("Resumo", "Datos dipoñibles no sisteman en ata: "
                             "29/09/2026 7:06:29\nResumo")
    monkeypatch.setattr("views.ledger_reconcile._pdf_text", lambda p: text)
    return pdf, xls


def _check(*argv):
    import orbit
    args = orbit._build_parser().parse_args(["ledger", "proyx", "--check", *argv])
    return orbit.cmd_ledger(args)


class TestCheckConFicheros:

    def test_guarda_con_fecha_y_anota_una_vez(self, proj, usc_files):
        _write(proj, *LEDGER)
        pdf, xls = usc_files
        _check(str(pdf), str(xls))
        logs = sorted(f.name for f in (proj / "cloud" / "logs").iterdir())
        assert logs == ["2026-09-29_Execucion_2010.XXXX.64100.pdf",
                        "2026-09-29_obrigas_2010.XXXX.64100.xls"]
        recons = [m for m in read_movements(proj)[0] if m.tag == "conciliacion"]
        assert len(recons) == 1
        r = recons[0]
        assert r.amount == D("18121.36") and r.date == date(2026, 9, 29)
        assert r.link.endswith("Execucion_2010.XXXX.64100.pdf")
        assert r.attach.endswith("obrigas_2010.XXXX.64100.xls")
        _check(str(pdf), str(xls))                       # otra vez: no repite
        assert len([m for m in read_movements(proj)[0]
                    if m.tag == "conciliacion"]) == 1

    def test_columna_usc_en_ledger_md(self, proj, usc_files):
        _write(proj, *LEDGER)
        _check(*map(str, usc_files))
        md = (proj / "ledger.md").read_text()
        assert "Conciliado con la USC el 2026-09-29" in md
        assert "| USC |" in md
        def usc(concept):
            line = next(l for l in md.splitlines()
                        if l.startswith("| 2026-") and f"| {concept} |" in l)
            return line.rstrip(" |").rsplit("|", 1)[1].strip()
        assert usc("Folla vuelo · Factura vuelo") == "ok? CM26XX0001 · F-4471"
        assert usc("Folla congreso") == "ok? AUT-001"
        assert usc("Folla hotel") == "!↓"
        assert usc("Dietas") == "!↓"

    def test_la_columna_sobrevive_a_regenerar(self, proj, usc_files):
        from views.ledger import write_ledger
        _write(proj, *LEDGER)
        _check(*map(str, usc_files))
        write_ledger(proj, force=True)                   # p. ej. en un save
        assert "| USC |" in (proj / "ledger.md").read_text()

    def test_solo_en_la_usc_como_fila(self, proj, usc_files):
        _write(proj, LEDGER[0])
        _check(*map(str, usc_files))
        md = (proj / "ledger.md").read_text()
        assert "| AUT-001 | — | (solo en la USC) | CONGRESO SL |" in md
        assert md.count("!↑") >= 2

    def test_importe_distinto_es_problema(self, proj, usc_files):
        _write(proj, LEDGER[0], ("2026-09-18", "Folla #pedido",
                                 "💶 -1.500,00 · 🆔 CM26XX0001"))
        _check(*map(str, usc_files))
        md = (proj / "ledger.md").read_text()
        assert "| ! CM26XX0001 |" in md
        assert "No encaja con la USC" in md and "importe distinto" in md

    def test_strict(self, proj, usc_files):
        _write(proj, LEDGER[0])
        assert _check(*map(str, usc_files), "--strict") == 1   # hay !↑

    def test_sin_ficheros_la_columna_avisa(self, proj, usc_files):
        _write(proj, *LEDGER)
        _check(*map(str, usc_files))
        for f in (proj / "cloud" / "logs").iterdir():
            f.unlink()
        from views.ledger import build_ledger_md
        md = build_ledger_md(proj)
        assert "Columna USC no disponible" in md and "| USC |" not in md

    def test_solo_excel_no_anota(self, proj, usc_files, capsys):
        _write(proj, *LEDGER)
        _check(str(usc_files[1]))
        assert not [m for m in read_movements(proj)[0] if m.tag == "conciliacion"]
        assert "necesita el PDF" in capsys.readouterr().out


def test_export_lleva_columna_usc_y_no_la_ejecucion(proj, usc_files, tmp_path):
    openpyxl = pytest.importorskip("openpyxl")
    pytest.importorskip("reportlab")
    from views.ledger_export import export_ledger
    folla = proj / "cloud" / "logs" / "2026-09-18_folla.pdf"
    folla.parent.mkdir(parents=True, exist_ok=True)
    folla.write_text("%PDF")
    _write(proj, ("2026-09-18", "[Folla vuelo](cloud/logs/2026-09-18_folla.pdf) #pedido",
                  "👤 Axencia Viaxes · 💶 -1.578,64 · 🆔 CM26XX0001"))
    _check(*map(str, usc_files))
    out = tmp_path / "share"
    export_ledger(proj, out)
    assert [f.name for f in (out / "justificantes").iterdir()] == ["2026-09-18_folla.pdf"]
    ws = openpyxl.load_workbook(out / "ledger.xlsx")["Operaciones"]
    assert ws.cell(1, 11).value == "USC"
    values = [ws.cell(r, 11).value for r in range(2, ws.max_row + 1)]
    assert "ok CM26XX0001" in values and "!↑" in values

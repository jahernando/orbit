"""test_ledger_reconcile.py — `ledger --check <ficheros de la USC>` (ADR-053).

Los ficheros de la USC son **sintéticos**: misma estructura que los reales
(tabla HTML en latin-1 con las columnas de `obrigasexcel.xls`; texto de
`pdftotext -layout` del PDF de ejecución), con datos inventados. Los reales
llevan nombres y proyectos que no van a un repo público.
"""

from datetime import date
from decimal import Decimal

import pytest

from core.ledger import build_operations, read_movements
from views.ledger_reconcile import (
    Mod, hints, load_report, parse_execution_text, parse_obligations, reconcile,
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


# ── Emparejado (solo por número) ─────────────────────────────────────────────

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
     "👤 Axencia Viaxes · 💶 -1.580,10 · 🆔 F-4471 · 🔗 CM26XX0001"),
    ("2026-08-31", "Dietas #gasto", "👤 Ana · 💶 -1.408,32"),
)


def _report():
    auts, obls = parse_obligations(_xls(SIN_OBLIGA, CON_OBLIGA).decode("latin-1"))
    r = parse_execution_text(EXECUCION)
    r.obls, r.has_obls = obls, True
    return r


class TestReconcile:

    def test_emparejado_por_numero(self, proj):
        _write(proj, *LEDGER)
        res = reconcile(read_movements(proj)[0], _report())
        auts = res["auts"]
        assert [p.usc.id for p in auts.pairs] == ["CM26XX0001"]
        assert [a.id for a in auts.only_usc] == ["AUT-001"]        # P01 no casa
        assert sorted(m.op_id for m in auts.only_ledger) == ["P01", "P02"]
        obls = res["obls"]
        assert [(p.usc.invoice, p.note) for p in obls.pairs] == [("F-4471", None)]
        assert [m.concept for m in obls.only_ledger] == ["Dietas"]
        assert len(res["mods"].pairs) == 1                         # por importe

    def test_sugerencia_para_el_provisional(self, proj):
        _write(proj, *LEDGER)
        res = reconcile(read_movements(proj)[0], _report())
        assert any("P01" in h and "AUT-001" in h for h in hints(res))
        # …pero no escribe nada.
        assert "AUT-001" not in (proj / "logbook.md").read_text()

    def test_importe_distinto(self, proj):
        _write(proj, ("2026-09-18", "Folla #pedido", "💶 -1.500,00 · 🆔 CM26XX0001"))
        pair = reconcile(read_movements(proj)[0], _report())["auts"].pairs[0]
        assert "importe distinto" in pair.note

    def test_sin_excel_no_compara_facturas(self, proj):
        _write(proj, *LEDGER)
        res = reconcile(read_movements(proj)[0], parse_execution_text(EXECUCION))
        assert "obls" not in res


def test_fichero_inexistente(proj, capsys):
    assert run_ledger_check("proyx", files=["/no/existe.xls"]) == 1


# ── `--check` con ficheros: guarda y pone la columna USC ─────────────────────

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


def _usc(md, concept):
    line = next(l for l in md.splitlines()
                if l.startswith("| 2026-") and f"| {concept} |" in l)
    return line.rstrip(" |").rsplit("|", 1)[1].strip()


class TestCheckConFicheros:
    """Informe provisional en terminal (hasta que exista usc-ledger): no
    guarda ficheros ni toca el ledger."""

    def test_informe_sin_escribir(self, proj, usc_files, capsys):
        _write(proj, *LEDGER)
        antes = (proj / "logbook.md").read_text()
        _check(*map(str, usc_files))
        out = capsys.readouterr().out
        assert "Conciliación con la USC" in out and "!↑ aut. AUT-001" in out
        assert (proj / "logbook.md").read_text() == antes
        assert not (proj / "cloud").exists()

    def test_strict(self, proj, usc_files):
        _write(proj, LEDGER[0])
        assert _check(*map(str, usc_files), "--strict") == 1   # hay !↑


# ── Marca de conciliado (🏛️), la pone usc-ledger por la CLI de orbit ─────────

def _mark(*argv):
    import orbit
    args = orbit._build_parser().parse_args(["ledger", "proyx", *argv])
    return orbit.cmd_ledger(args)


class TestMarca:

    def test_marcar_y_desmarcar(self, proj, capsys):
        _write(proj, *LEDGER)
        movs = read_movements(proj)[0]
        folla = next(m for m in movs if m.op_id == "CM26XX0001")
        assert folla.usc is None
        assert _mark("--mark", folla.key, "CM26XX0001") == 0
        m = next(m for m in read_movements(proj)[0] if m.op_id == "CM26XX0001")
        assert m.usc == "CM26XX0001"
        md = (proj / "ledger.md").read_text()
        assert "| CM26XX0001 |" in md.split("Folla vuelo")[1].splitlines()[0]
        assert _mark("--unmark", folla.key) == 0
        assert next(m for m in read_movements(proj)[0]
                    if m.op_id == "CM26XX0001").usc is None

    def test_provisional_pasa_al_numero_oficial(self, proj):
        _write(proj,
               ("2026-08-30", "Folla #folla", "👤 X · 💶 -300,00 · 🆔 P01"),
               ("2026-09-10", "Fra #factura", "👤 X · 💶 -300,00 · 🔗 P01"))
        folla = read_movements(proj)[0][0]
        assert _mark("--mark", folla.key, "621A-XX") == 0
        movs = read_movements(proj)[0]
        assert movs[0].op_id == "621A-XX" and movs[0].usc == "621A-XX"
        assert movs[1].ref == "621A-XX"                 # su factura, también
        ops, problems = build_operations(movs)
        assert problems == [] and ops[0].state == "cerrado"

    def test_gasto_sin_numero_recibe_el_de_la_usc(self, proj):
        _write(proj, ("2026-08-31", "Dietas #dietas", "👤 Ana · 💶 -10,00"))
        m = read_movements(proj)[0][0]
        _mark("--mark", m.key, "LIQ-7")
        m = read_movements(proj)[0][0]
        assert (m.op_id, m.usc, m.label) == ("LIQ-7", "LIQ-7", "dietas")

    def test_clave_inexistente(self, proj, capsys):
        _write(proj, *LEDGER)
        assert _mark("--mark", "2026-01-01:folla:nada", "X") == 1
        assert "no hay ninguna entrada" in capsys.readouterr().out

    def test_ledger_json_lleva_clave_y_marca(self, proj):
        import json
        from views.ledger import write_ledger
        _write(proj, *LEDGER)
        write_ledger(proj, force=True)
        rows = json.loads((proj / "ledger.json").read_text())["movements"]
        assert all(r["key"] for r in rows)
        _mark("--mark", rows[2]["key"], "CM26XX0001")
        rows = json.loads((proj / "ledger.json").read_text())["movements"]
        assert rows[2]["usc"] == "CM26XX0001"

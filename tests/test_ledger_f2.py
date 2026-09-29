"""test_ledger_f2.py — F2 del ledger (ADR-053): moneda original y CLI de
pedidos, anulaciones y conciliaciones.

Cubre:
  - parse_orig / format_orig:  `1.150,00 CHF`, `CHF 1150`, errores
  - build_body + parse_entry:  ida y vuelta con 💱 · 🆔 · 🔗 … parcial
  - prepare_movement:          reglas por tag
  - next_order_id / check_links
  - interrogate_commitment:    solo pregunta lo que falta
  - `orbit log --entry …`:     de punta a punta (sin terminal)
  - vista:                     columna de moneda original y `~` en pedidos
"""

import builtins
from decimal import Decimal

import pytest

from core.ledger import (
    CANCEL_TAG, EXPENSE_TAG, INCOME_TAG, ORDER_TAG, RECON_TAG, CLOSED, OPEN,
    CANCELLED, build_body, build_operations, check_links, format_orig,
    interrogate_commitment, next_order_id, parse_entry, parse_orig,
    prepare_movement, read_movements,
)
from views.ledger import build_ledger_md

D = Decimal


@pytest.fixture
def proj(tmp_path, monkeypatch):
    type_dir = tmp_path / "💻software"
    type_dir.mkdir()
    p = type_dir / "💻testproj"
    p.mkdir()
    (p / "project.md").write_text("# 💻testproj\n")
    (p / "logbook.md").write_text("# Logbook — 💻testproj\n\n")
    monkeypatch.setattr("core.config.ORBIT_HOME", tmp_path)
    monkeypatch.setattr("core.config._ORBIT_JSON", tmp_path / "orbit.json")
    monkeypatch.setattr("core.log.PROJECTS_DIR", tmp_path)
    return p


def _answers(monkeypatch, *values):
    it = iter(values)
    monkeypatch.setattr(builtins, "input", lambda _prompt="": next(it))


def _log(*argv):
    import orbit
    args = orbit._build_parser().parse_args(["log", "testproj", *argv])
    return orbit.cmd_log(args)


# ── Moneda original ──────────────────────────────────────────────────────────

class TestOrig:

    @pytest.mark.parametrize("raw", ["1.150,00 CHF", "CHF 1150", "1150 chf",
                                     "1.150 CHF"])
    def test_formas_validas(self, raw):
        assert parse_orig(raw) == (D("1150.00"), "CHF")

    @pytest.mark.parametrize("raw", ["1150", "1150 FRANCOS", "CH 1150",
                                     "1150 CHF extra", ""])
    def test_formas_invalidas(self, raw):
        with pytest.raises(ValueError):
            parse_orig(raw)

    def test_sin_signo(self):
        assert parse_orig("-12,5 USD") == (D("12.50"), "USD")

    def test_format(self):
        assert format_orig(D("1150"), "CHF") == "1.150,00 CHF"


# ── Cuerpo: ida y vuelta ─────────────────────────────────────────────────────

class TestBody:

    def test_pedido(self):
        body = build_body(D("-1234.56"), "viaje", "Agencia",
                          orig=(D("1150"), "CHF"), op_id="P03")
        assert body == ["🏷️ viaje · 👤 Agencia · 💶 -1.234,56 · "
                        "💱 1.150,00 CHF · 🆔 P03"]
        mov, problem = parse_entry("2026-09-18", "💶 Folla #pedido", body)
        assert problem is None
        assert mov.op_id == "P03" and mov.orig == (D("1150.00"), "CHF")

    def test_factura_parcial(self):
        body = build_body(D("-10"), "viaje", ref="P03", partial=True)
        assert body == ["🏷️ viaje · 💶 -10,00 · 🔗 P03 parcial"]
        mov, _ = parse_entry("2026-10-01", "💶 Fra #gasto", body)
        assert mov.ref == "P03" and mov.partial

    def test_anulacion_sin_importe(self):
        assert build_body(None, "viaje", ref="P03") == ["🏷️ viaje · 🔗 P03"]

    def test_moneda_ilegible_se_canta(self):
        mov, problem = parse_entry("2026-10-01", "💶 Fra #gasto",
                                   ["💶 -10,00 · 💱 diez francos"])
        assert mov is not None and mov.orig is None
        assert "💱" in problem


# ── prepare_movement ─────────────────────────────────────────────────────────

class TestPrepare:

    def test_pedido_exige_id(self):
        with pytest.raises(ValueError, match="necesita id"):
            prepare_movement(ORDER_TAG, "100", "viaje")

    def test_pedido_negativo(self):
        _b, amount = prepare_movement(ORDER_TAG, "100", "viaje", op_id="P01")
        assert amount == D("-100.00")

    def test_id_solo_en_pedido_o_gasto(self):
        with pytest.raises(ValueError, match="--id solo"):
            prepare_movement(INCOME_TAG, "100", "viaje", op_id="P01")

    def test_gasto_con_numero_de_factura(self):
        body, _ = prepare_movement(EXPENSE_TAG, "100", "viaje", op_id="F-4471",
                                   ref="CM26XXXX0001")
        assert body == ["🏷️ viaje · 💶 -100,00 · 🆔 F-4471 · 🔗 CM26XXXX0001"]

    def test_id_sin_espacios(self):
        with pytest.raises(ValueError):
            prepare_movement(ORDER_TAG, "100", "viaje", op_id="P 1")

    def test_anulacion(self):
        body, amount = prepare_movement(CANCEL_TAG, None, "viaje", ref="P01")
        assert amount == 0 and body == ["🏷️ viaje · 🔗 P01"]

    def test_anulacion_sin_ref(self):
        with pytest.raises(ValueError, match="necesita el pedido"):
            prepare_movement(CANCEL_TAG, None, "viaje")

    def test_anulacion_con_importe(self):
        with pytest.raises(ValueError, match="no lleva importe"):
            prepare_movement(CANCEL_TAG, "10", "viaje", ref="P01")

    def test_conciliacion_admite_signo(self):
        _b, amount = prepare_movement(RECON_TAG, "-50,00", "viaje")
        assert amount == D("-50.00")

    def test_ref_solo_en_gasto_o_anulacion(self):
        with pytest.raises(ValueError, match="--pedido solo"):
            prepare_movement(INCOME_TAG, "10", "viaje", ref="P01")

    def test_parcial_exige_ref(self):
        with pytest.raises(ValueError, match="--partial"):
            prepare_movement(EXPENSE_TAG, "10", "viaje", partial=True)

    def test_orig_no_en_conciliacion(self):
        with pytest.raises(ValueError, match="--orig"):
            prepare_movement(RECON_TAG, "10", "viaje", orig_raw="10 CHF")


# ── ids y referencias ────────────────────────────────────────────────────────

def _movs(proj, text):
    (proj / "logbook.md").write_text("# Logbook\n\n" + text)
    return read_movements(proj)[0]


PEDIDO = "2026-09-01 💶 Folla #pedido\n  🏷️ viaje · 💶 -100,00 · 🆔 {}\n\n"


class TestIds:

    def test_primero(self):
        assert next_order_id([]) == "P01"

    def test_siguiente_respeta_prefijo_y_ancho(self, proj):
        movs = _movs(proj, PEDIDO.format("P09") + PEDIDO.format("P02"))
        assert next_order_id(movs) == "P10"
        movs = _movs(proj, PEDIDO.format("OP003"))
        assert next_order_id(movs) == "OP004"

    def test_id_repetido(self, proj):
        movs = _movs(proj, PEDIDO.format("P01"))
        with pytest.raises(ValueError, match="P02"):
            check_links(movs, ORDER_TAG, op_id="P01")

    def test_ref_inexistente(self, proj):
        movs = _movs(proj, PEDIDO.format("P01"))
        with pytest.raises(ValueError, match="abiertos: P01"):
            check_links(movs, EXPENSE_TAG, ref="P07")

    def test_ref_cerrado(self, proj):
        movs = _movs(proj, PEDIDO.format("P01")
                     + "2026-09-10 💶 Fra #gasto\n  💶 -100,00 · 🔗 P01\n")
        with pytest.raises(ValueError, match="ya está cerrado"):
            check_links(movs, EXPENSE_TAG, ref="P01")


# ── Interrogador ─────────────────────────────────────────────────────────────

class TestInterrogador:

    def test_pedido_sugiere_id(self, proj, monkeypatch):
        movs = _movs(proj, PEDIDO.format("P04"))
        _answers(monkeypatch, "", "")            # Enter en id y en moneda
        op_id, ref, partial, orig = interrogate_commitment(
            movs, ORDER_TAG, op_id=None, ref=None, partial=False, orig=None)
        assert (op_id, ref, partial, orig) == ("P05", None, False, None)

    def test_gasto_con_pedidos_abiertos(self, proj, monkeypatch, capsys):
        movs = _movs(proj, PEDIDO.format("P01"))
        _answers(monkeypatch, "P01", "F-1", "s", "1.150 CHF")
        op_id, ref, partial, orig = interrogate_commitment(
            movs, EXPENSE_TAG, op_id=None, ref=None, partial=False, orig=None)
        assert (op_id, ref, partial, orig) == ("F-1", "P01", True, "1.150 CHF")
        assert "Pedidos abiertos" in capsys.readouterr().out

    def test_gasto_sin_pedidos_no_pregunta_ref(self, proj, monkeypatch):
        _answers(monkeypatch, "", "")            # nº de factura y moneda
        _i, ref, _p, _o = interrogate_commitment(
            [], EXPENSE_TAG, op_id=None, ref=None, partial=False, orig=None)
        assert ref is None

    def test_ref_mala_se_vuelve_a_pedir(self, proj, monkeypatch, capsys):
        movs = _movs(proj, PEDIDO.format("P01"))
        _answers(monkeypatch, "P09", "P01", "", "", "")
        _i, ref, _p, _o = interrogate_commitment(
            movs, EXPENSE_TAG, op_id=None, ref=None, partial=False, orig=None)
        assert ref == "P01"
        assert "no hay ningún pedido P09" in capsys.readouterr().out

    def test_moneda_mala_se_vuelve_a_pedir(self, proj, monkeypatch):
        _answers(monkeypatch, "diez francos", "10 CHF")
        *_, orig = interrogate_commitment(
            [], INCOME_TAG, op_id=None, ref=None, partial=False, orig=None)
        assert orig == "10 CHF"


# ── `orbit log` de punta a punta ─────────────────────────────────────────────

class TestLogCli:

    def _ops(self, proj):
        return build_operations(read_movements(proj)[0])

    def test_pedido_factura_y_anulacion(self, proj, capsys):
        assert _log("Dotación", "--entry", "ingreso", "--amount", "10.000",
                    "--tag", "viaje") == 0
        assert _log("Folla Ginebra", "--entry", "pedido", "--amount", "1.578,64",
                    "--payee", "Axencia Viaxes", "--orig", "1.500 CHF") == 0
        assert "🆔 P01" in capsys.readouterr().out     # id asignado, anunciado
        assert _log("Folla tasa", "--entry", "pedido", "--amount", "300") == 0
        assert _log("Factura Ginebra", "--entry", "gasto", "--amount", "1.580,10",
                    "--pedido", "P01") == 0
        assert "cierra P01" in capsys.readouterr().out
        assert _log("Tasa cancelada", "--entry", "anulacion", "--pedido", "P02") == 0

        ops, problems = self._ops(proj)
        assert problems == []
        states = {o.op_id: o.state for o in ops}
        assert states == {"P01": CLOSED, "P02": CANCELLED}

    def test_parcial(self, proj):
        _log("Folla", "--entry", "pedido", "--amount", "1.000", "--tag", "viaje")
        assert _log("Fra 1", "--entry", "gasto", "--amount", "300",
                    "--pedido", "P01", "--partial") == 0
        ops, _ = self._ops(proj)
        assert ops[0].state == OPEN and ops[0].pending == D("700.00")

    def test_ref_inexistente_no_escribe(self, proj, capsys):
        _log("Folla", "--entry", "pedido", "--amount", "100", "--tag", "viaje")
        antes = (proj / "logbook.md").read_text()
        assert _log("Fra", "--entry", "gasto", "--amount", "100",
                    "--pedido", "P09") == 1
        assert "no hay ningún pedido P09" in capsys.readouterr().out
        assert (proj / "logbook.md").read_text() == antes

    def test_id_repetido_no_escribe(self, proj, capsys):
        _log("Folla", "--entry", "pedido", "--amount", "100", "--tag", "viaje",
             "--id", "P01")
        assert _log("Otra", "--entry", "pedido", "--amount", "5",
                    "--id", "P01") == 1

    def test_conciliacion(self, proj):
        _log("Dotación", "--entry", "ingreso", "--amount", "100", "--tag", "viaje")
        assert _log("Saldo USC", "--entry", "conciliacion", "--amount", "100") == 0
        assert "Última conciliación:" in build_ledger_md(proj)


# ── Vista ────────────────────────────────────────────────────────────────────

def test_vista_moneda_original(proj):
    (proj / "logbook.md").write_text(
        "# Logbook\n\n"
        "2026-09-01 💶 Folla #pedido\n"
        "  🏷️ viaje · 💶 -1.234,56 · 💱 1.150,00 CHF · 🆔 P01\n\n"
        "2026-09-02 💶 Folla EUR #pedido\n  🏷️ viaje · 💶 -100,00 · 🆔 P02\n")
    md = build_ledger_md(proj)
    assert "| ~1.234,56 | — | abierto | 1.150,00 CHF |" in md
    assert "| 100,00 | — | abierto | — |" in md

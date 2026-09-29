"""test_ledger_f2.py — escribir pedidos y facturas desde la CLI (ADR-053).

Cubre:
  - build_body + parse_entry:  ida y vuelta con 🆔 · 🔗
  - prepare_movement:          reglas por tag
  - next_order_id / check_links
  - interrogate_commitment:    solo pregunta lo que falta
  - `orbit log --entry …`:     de punta a punta (sin terminal)
"""

import builtins
from decimal import Decimal

import pytest

from core.ledger import (
    CLOSED, EXPENSE_TAG, INCOME_TAG, OPEN, ORDER_TAG, build_body,
    build_operations, check_links, interrogate_commitment, next_order_id,
    parse_entry, prepare_movement, read_movements,
)

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


def _movs(proj, text):
    (proj / "logbook.md").write_text("# Logbook\n\n" + text)
    return read_movements(proj)[0]


PEDIDO = "2026-09-01 💶 Folla #pedido\n  🏷️ viaje · 💶 -100,00 · 🆔 {}\n\n"


# ── Cuerpo y reglas ──────────────────────────────────────────────────────────

class TestBody:

    def test_pedido(self):
        body = build_body(D("-1234.56"), "viaje", "Agencia", op_id="CM26XX0001")
        assert body == ["🏷️ viaje · 👤 Agencia · 💶 -1.234,56 · 🆔 CM26XX0001"]
        mov, problem = parse_entry("2026-09-18", "💶 Folla #pedido", body)
        assert problem is None and mov.op_id == "CM26XX0001"

    def test_factura(self):
        body = build_body(D("-10"), "viaje", op_id="F-1", ref="P03")
        assert body == ["🏷️ viaje · 💶 -10,00 · 🆔 F-1 · 🔗 P03"]


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

    def test_id_sin_espacios(self):
        with pytest.raises(ValueError):
            prepare_movement(ORDER_TAG, "100", "viaje", op_id="P 1")

    def test_pedido_solo_en_gasto(self):
        with pytest.raises(ValueError, match="--pedido solo"):
            prepare_movement(INCOME_TAG, "10", "viaje", ref="P01")

    def test_tags_retiradas(self):
        for tag in ("anulacion", "conciliacion"):
            with pytest.raises(ValueError, match="no es una tag"):
                prepare_movement(tag, "10", "viaje")


# ── ids y referencias ────────────────────────────────────────────────────────

class TestIds:

    def test_primero(self):
        assert next_order_id([]) == "P01"

    def test_siguiente_respeta_prefijo_y_ancho(self, proj):
        movs = _movs(proj, PEDIDO.format("P09") + PEDIDO.format("P02"))
        assert next_order_id(movs) == "P10"
        movs = _movs(proj, PEDIDO.format("OP003"))
        assert next_order_id(movs) == "OP004"

    def test_numero_usc_no_cuenta_para_el_siguiente(self, proj):
        movs = _movs(proj, PEDIDO.format("CM26XX0001") + PEDIDO.format("P02"))
        assert next_order_id(movs) == "P03"

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

    def test_factura_repetida(self, proj):
        movs = _movs(proj, "2026-09-10 💶 Fra #gasto\n  💶 -1,00 · 🆔 F-1\n")
        with pytest.raises(ValueError, match="ya está anotada"):
            check_links(movs, EXPENSE_TAG, op_id="F-1")


# ── Interrogador ─────────────────────────────────────────────────────────────

class TestInterrogador:

    def test_pedido_sugiere_id(self, proj, monkeypatch):
        movs = _movs(proj, PEDIDO.format("P04"))
        _answers(monkeypatch, "")                # Enter = el sugerido
        assert interrogate_commitment(movs, ORDER_TAG, op_id=None,
                                      ref=None) == ("P05", None)

    def test_gasto_con_pedidos_abiertos(self, proj, monkeypatch, capsys):
        movs = _movs(proj, PEDIDO.format("P01"))
        _answers(monkeypatch, "P01", "F-1")
        assert interrogate_commitment(movs, EXPENSE_TAG, op_id=None,
                                      ref=None) == ("F-1", "P01")
        assert "Pedidos abiertos" in capsys.readouterr().out

    def test_gasto_sin_pedidos_no_pregunta_ref(self, proj, monkeypatch):
        _answers(monkeypatch, "")                # solo el nº de factura
        assert interrogate_commitment([], EXPENSE_TAG, op_id=None,
                                      ref=None) == (None, None)

    def test_ref_mala_se_vuelve_a_pedir(self, proj, monkeypatch, capsys):
        movs = _movs(proj, PEDIDO.format("P01"))
        _answers(monkeypatch, "P09", "P01", "")
        _i, ref = interrogate_commitment(movs, EXPENSE_TAG, op_id=None, ref=None)
        assert ref == "P01"
        assert "no hay ningún pedido P09" in capsys.readouterr().out


# ── `orbit log` de punta a punta ─────────────────────────────────────────────

class TestLogCli:

    def _ops(self, proj):
        return build_operations(read_movements(proj)[0])

    def test_pedido_y_factura(self, proj, capsys):
        assert _log("Dotación", "--entry", "ingreso", "--amount", "10.000",
                    "--tag", "viaje") == 0
        assert _log("Folla vuelo", "--entry", "pedido", "--amount", "1.578,64",
                    "--payee", "Axencia") == 0
        assert "🆔 P01" in capsys.readouterr().out     # id asignado, anunciado
        assert _log("Folla tasa", "--entry", "pedido", "--amount", "300",
                    "--id", "CM26XX0002") == 0
        assert _log("Factura vuelo", "--entry", "gasto", "--amount", "1.580,10",
                    "--id", "F-4471", "--pedido", "P01") == 0
        assert "cierra P01" in capsys.readouterr().out

        ops, problems = self._ops(proj)
        assert problems == []
        assert {o.op_id: o.state for o in ops} == {"P01": CLOSED,
                                                   "CM26XX0002": OPEN}

    def test_ref_inexistente_no_escribe(self, proj, capsys):
        _log("Folla", "--entry", "pedido", "--amount", "100", "--tag", "viaje")
        antes = (proj / "logbook.md").read_text()
        assert _log("Fra", "--entry", "gasto", "--amount", "100",
                    "--pedido", "P09") == 1
        assert "no hay ningún pedido P09" in capsys.readouterr().out
        assert (proj / "logbook.md").read_text() == antes

    def test_id_repetido_no_escribe(self, proj):
        _log("Folla", "--entry", "pedido", "--amount", "100", "--tag", "viaje",
             "--id", "P01")
        assert _log("Otra", "--entry", "pedido", "--amount", "5",
                    "--id", "P01") == 1

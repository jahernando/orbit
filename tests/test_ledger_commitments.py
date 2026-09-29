"""test_ledger_commitments.py — el modelo de compromisos (ADR-053).

Cubre:
  - parse_entry:      #compromiso (🆔, signo), #gasto con 🆔 (factura) y 🔗
  - balance:          los pedidos no mueven caja
  - build_operations: pedido → factura, gasto directo, 🔗 colgante,
                      id repetido, factura sobre pedido ya cerrado
  - summarize:        dotación · gastado · comprometido · disponible
  - archive:          una operación con pedido solo se archiva entera y
                      terminada; el arrastre no cuenta los pedidos
"""

from datetime import date
from decimal import Decimal

import pytest

from core.archive import _carry_preview, _clean_logbook
from core.ledger import (
    CLOSED, DIRECT, OPEN, balance, build_operations, parse_entry,
    read_movements, summarize,
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


def _write(proj, *entries):
    """Cada entrada: (fecha, cabecera, cuerpo)."""
    (proj / "logbook.md").write_text("# Logbook — 💻testproj\n\n" + "\n".join(
        f"{d} 💶 {h}\n  {b}\n" for d, h, b in entries))


def _ops(proj):
    movs, problems = read_movements(proj)
    ops, op_problems = build_operations(movs)
    return movs, ops, problems + op_problems


INGRESO = ("2026-07-01", "Dotación #ingreso", "🏷️ viaje · 💶 10.000,00")


def _pedido(fecha, id_, importe, concepto="Folla"):
    return (fecha, f"[{concepto}](cloud/logs/folla.pdf) #compromiso",
            f"🏷️ viaje · 👤 Agencia · 💶 -{importe} · 🆔 {id_}")


def _factura(fecha, importe, ref=None, concepto="Factura", nfac=None):
    body = f"🏷️ viaje · 👤 Agencia · 💶 -{importe}"
    if nfac:
        body += f" · 🆔 {nfac}"
    if ref:
        body += f" · 🔗 {ref}"
    return (fecha, f"[{concepto}](cloud/logs/fra.pdf) #gasto", body)


# ── parse_entry ──────────────────────────────────────────────────────────────

class TestParse:

    def test_pedido_con_id_y_signo_negativo(self):
        mov, problem = parse_entry("2026-09-18", "💶 Folla #compromiso",
                                   ["🏷️ viaje · 💶 1.578,64 · 🆔 CM26XX0001"])
        assert problem is not None            # sin signo → la tag lo corrige
        assert mov.amount == D("-1578.64")
        assert mov.op_id == "CM26XX0001" and not mov.is_cash

    def test_pedido_sin_id_se_canta(self):
        mov, problem = parse_entry("2026-09-18", "💶 Folla #compromiso",
                                   ["💶 -10,00"])
        assert mov is not None and mov.op_id is None
        assert "sin id" in problem

    def test_gasto_con_factura_y_pedido(self):
        mov, problem = parse_entry("2026-10-01", "💶 Fra #gasto",
                                   ["💶 -100,00 · 🆔 F-4471 · 🔗 CM26XX0001"])
        assert problem is None
        assert (mov.op_id, mov.ref) == ("F-4471", "CM26XX0001")

    def test_ya_no_son_del_ledger(self):
        # #anulacion y #conciliacion se retiraron al simplificar: son apuntes.
        for tag in ("anulacion", "conciliacion"):
            assert parse_entry("2026-10-01", f"💶 X #{tag}", ["💶 1,00"]) == (None, None)


def test_los_pedidos_no_mueven_caja(proj):
    _write(proj, INGRESO, _pedido("2026-09-18", "P01", "1.000,00"))
    movs, _ = read_movements(proj)
    assert balance(movs) == D("10000.00")


# ── build_operations ─────────────────────────────────────────────────────────

class TestOperations:

    def test_factura_cierra_el_pedido(self, proj):
        _write(proj, _pedido("2026-09-18", "P03", "1.578,64"),
               _factura("2026-10-02", "1.580,10", "P03", nfac="F-1"))
        _m, ops, problems = _ops(proj)
        assert problems == []
        assert len(ops) == 1
        op = ops[0]
        assert op.state == CLOSED and op.pending == 0
        assert op.committed == D("1578.64") and op.spent == D("1580.10")
        assert op.invoice_ids == ["F-1"]

    def test_pedido_sin_factura_sigue_abierto(self, proj):
        _write(proj, _pedido("2026-09-18", "P03", "300,00"))
        _m, ops, _p = _ops(proj)
        assert ops[0].state == OPEN and ops[0].pending == D("300.00")

    def test_gasto_directo(self, proj):
        _write(proj, _factura("2026-08-31", "1.408,32", concepto="Dietas"))
        _m, ops, _p = _ops(proj)
        assert ops[0].state == DIRECT and ops[0].spent == D("1408.32")

    def test_referencia_colgante_cuenta_y_se_canta(self, proj):
        _write(proj, _factura("2026-10-03", "10,00", "P09"))
        movs, ops, problems = _ops(proj)
        assert ops[0].state == DIRECT
        assert any("P09 no es ningún compromiso" in p for p in problems)
        assert balance(movs) == D("-10.00")

    def test_id_repetido(self, proj):
        _write(proj, _pedido("2026-09-01", "P01", "100,00"),
               _pedido("2026-09-02", "P01", "200,00"))
        _m, _ops_, problems = _ops(proj)
        assert any("repetido" in p for p in problems)

    def test_factura_sobre_pedido_cerrado(self, proj):
        _write(proj, _pedido("2026-09-01", "P01", "100,00"),
               _factura("2026-09-10", "100,00", "P01"),
               _factura("2026-09-11", "100,00", "P01"))
        _m, ops, problems = _ops(proj)
        assert any("ya estaba cerrado" in p for p in problems)
        assert ops[0].spent == D("200.00")    # el dinero salió igualmente


# ── summarize ────────────────────────────────────────────────────────────────

class TestSummary:

    def test_disponible(self, proj):
        _write(proj, INGRESO,
               _factura("2026-08-31", "1.408,32", concepto="Dietas"),
               _pedido("2026-09-18", "P03", "1.578,64"),
               _factura("2026-10-02", "1.580,10", "P03"),
               _pedido("2026-09-20", "P04", "300,00"))
        movs, _ = read_movements(proj)
        s = summarize(movs)
        assert s.income == D("10000.00")
        assert s.spent == D("-2988.42")
        assert s.committed == D("-300.00")
        assert s.available == D("6711.58")

    def test_sin_pedidos_igual_que_antes(self, proj):
        _write(proj, INGRESO, _factura("2026-08-31", "100,00"))
        movs, _ = read_movements(proj)
        s = summarize(movs)
        assert s.committed == 0 and s.available == balance(movs)


# ── archive ──────────────────────────────────────────────────────────────────

CUTOFF = date(2026, 1, 1)


def _descs(proj):
    return [m.concept for m in read_movements(proj)[0]]


class TestArchive:

    def test_pedido_abierto_no_se_archiva(self, proj):
        _write(proj, _pedido("2025-06-01", "P01", "100,00", "Folla vieja"))
        _clean_logbook(proj, CUTOFF)
        assert _descs(proj) == ["Folla vieja"]

    def test_operacion_cerrada_antes_del_corte_se_archiva(self, proj):
        _write(proj, _pedido("2025-06-01", "P01", "100,00", "Folla"),
               _factura("2025-07-01", "100,00", "P01", "Fra"))
        _clean_logbook(proj, CUTOFF)
        assert _descs(proj) == []

    def test_factura_posterior_protege_al_pedido(self, proj):
        _write(proj, _pedido("2025-06-01", "P01", "100,00", "Folla"),
               _factura("2026-02-01", "100,00", "P01", "Fra"))
        _clean_logbook(proj, CUTOFF)
        _m, ops, problems = _ops(proj)
        assert problems == [] and ops[0].state == CLOSED

    def test_arrastre_no_cuenta_pedidos(self, proj):
        _write(proj, ("2025-01-15", "Dotación #ingreso", "🏷️ viaje · 💶 1.000,00"),
               _pedido("2025-06-01", "P01", "100,00"))
        n, neto, _p = _carry_preview(proj, CUTOFF)
        assert n == 1 and neto == D("1000.00")

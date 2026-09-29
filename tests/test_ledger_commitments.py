"""test_ledger_commitments.py — F1 del ledger con compromisos (ADR-053).

Cubre:
  - parse_entry:      #pedido (🆔, signo), #anulacion (sin importe),
                      #conciliacion (signo libre), 🔗 … parcial
  - balance:          los pedidos no mueven caja
  - build_operations: 1 pedido → 1 factura, parciales, anulación, 🔗 colgante,
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
    CANCELLED, CLOSED, DIRECT, OPEN, balance, build_operations, parse_entry,
    read_movements, summarize,
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


def _write(proj, *entries):
    """Cada entrada: (fecha, cabecera, cuerpo)."""
    text = "# Logbook — 💻testproj\n\n" + "\n".join(
        f"{d} 💶 {h}\n  {b}\n" for d, h, b in entries)
    (proj / "logbook.md").write_text(text)


def _ops(proj):
    movs, problems = read_movements(proj)
    ops, op_problems = build_operations(movs)
    return movs, ops, problems + op_problems


INGRESO = ("2026-07-01", "Dotación #ingreso", "🏷️ viaje · 💶 10.000,00")


def _pedido(fecha, id_, importe, concepto="Folla"):
    return (fecha, f"[{concepto}](cloud/logs/folla.pdf) #pedido",
            f"🏷️ viaje · 👤 Agencia · 💶 -{importe} · 🆔 {id_}")


def _factura(fecha, importe, ref=None, concepto="Factura"):
    body = f"🏷️ viaje · 👤 Agencia · 💶 -{importe}"
    if ref:
        body += f" · 🔗 {ref}"
    return (fecha, f"[{concepto}](cloud/logs/fra.pdf) #gasto", body)


# ── parse_entry ──────────────────────────────────────────────────────────────

class TestParse:

    def test_pedido_con_id_y_signo_negativo(self):
        mov, problem = parse_entry("2026-09-18", "💶 Folla #pedido",
                                   ["🏷️ viaje · 💶 1.578,64 · 🆔 P03"])
        assert problem is not None            # sin signo → la tag lo corrige
        assert mov.amount == D("-1578.64")
        assert mov.op_id == "P03" and not mov.is_cash

    def test_pedido_sin_id_se_canta(self):
        mov, problem = parse_entry("2026-09-18", "💶 Folla #pedido",
                                   ["💶 -10,00"])
        assert mov is not None and mov.op_id is None
        assert "sin id" in problem

    def test_anulacion_sin_importe(self):
        mov, problem = parse_entry("2026-09-20", "💶 Anulada #anulacion",
                                   ["🔗 P03"])
        assert problem is None
        assert mov.ref == "P03" and mov.amount == 0

    def test_anulacion_sin_referencia_se_canta(self):
        _mov, problem = parse_entry("2026-09-20", "💶 Anulada #anulacion", [])
        assert "sin 🔗" in problem

    def test_conciliacion_signo_libre(self):
        mov, problem = parse_entry("2026-09-30", "💶 Saldo USC #conciliacion",
                                   ["💶 19.926,79"])
        assert problem is None and mov.amount == D("19926.79")

    def test_referencia_parcial(self):
        mov, _ = parse_entry("2026-10-01", "💶 Fra 1 #gasto",
                             ["💶 -100,00 · 🔗 P03 parcial"])
        assert mov.ref == "P03" and mov.partial


def test_los_pedidos_no_mueven_caja(proj):
    _write(proj, INGRESO, _pedido("2026-09-18", "P01", "1.000,00"))
    movs, _ = read_movements(proj)
    assert balance(movs) == D("10000.00")


# ── build_operations ─────────────────────────────────────────────────────────

class TestOperations:

    def test_factura_cierra_el_pedido(self, proj):
        _write(proj, _pedido("2026-09-18", "P03", "1.578,64"),
               _factura("2026-10-02", "1.580,10", "P03"))
        _m, ops, problems = _ops(proj)
        assert problems == []
        assert len(ops) == 1
        op = ops[0]
        assert op.state == CLOSED and op.pending == 0
        assert op.committed == D("1578.64") and op.spent == D("1580.10")

    def test_pedido_sin_factura_sigue_abierto(self, proj):
        _write(proj, _pedido("2026-09-18", "P03", "300,00"))
        _m, ops, _p = _ops(proj)
        assert ops[0].state == OPEN and ops[0].pending == D("300.00")

    def test_parciales_y_cierre(self, proj):
        _write(proj, _pedido("2026-09-01", "P01", "1.000,00"),
               _factura("2026-09-10", "300,00", "P01 parcial"))
        _m, ops, _p = _ops(proj)
        assert ops[0].state == OPEN and ops[0].pending == D("700.00")

        _write(proj, _pedido("2026-09-01", "P01", "1.000,00"),
               _factura("2026-09-10", "300,00", "P01 parcial"),
               _factura("2026-09-20", "650,00", "P01"))
        _m, ops, _p = _ops(proj)
        assert ops[0].state == CLOSED and ops[0].spent == D("950.00")

    def test_parcial_que_se_pasa_no_da_credito(self, proj):
        _write(proj, _pedido("2026-09-01", "P01", "100,00"),
               _factura("2026-09-10", "150,00", "P01 parcial"))
        _m, ops, _p = _ops(proj)
        assert ops[0].pending == 0

    def test_anulacion(self, proj):
        _write(proj, _pedido("2026-09-01", "P01", "100,00"),
               ("2026-09-05", "Anulado #anulacion", "🔗 P01"))
        _m, ops, _p = _ops(proj)
        assert ops[0].state == CANCELLED and ops[0].pending == 0

    def test_gasto_directo(self, proj):
        _write(proj, _factura("2026-08-31", "1.408,32", concepto="Dietas"))
        _m, ops, _p = _ops(proj)
        assert ops[0].state == DIRECT and ops[0].spent == D("1408.32")

    def test_referencia_colgante_cuenta_y_se_canta(self, proj):
        _write(proj, _factura("2026-10-03", "10,00", "P09"))
        movs, ops, problems = _ops(proj)
        assert ops[0].state == DIRECT
        assert any("P09 no es ningún pedido" in p for p in problems)
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

    def test_conciliacion_en_la_vista(self, proj):
        _write(proj, INGRESO,
               ("2026-09-30", "Saldo USC #conciliacion", "💶 10.000,00"))
        md = build_ledger_md(proj)
        assert "Última conciliación: 2026-09-30 · 10.000,00 €" in md
        assert "| **Disponible** | **10.000,00** |" in md


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

    def test_parcial_de_pedido_abierto_se_queda(self, proj):
        _write(proj, _pedido("2025-06-01", "P01", "1.000,00", "Folla"),
               _factura("2025-07-01", "300,00", "P01 parcial", "Fra 1"))
        n, _neto, _p = _carry_preview(proj, CUTOFF)
        assert n == 0                        # nada que arrastrar
        _clean_logbook(proj, CUTOFF)
        _m, ops, _p = _ops(proj)
        assert ops[0].pending == D("700.00")

    def test_arrastre_no_cuenta_pedidos(self, proj):
        _write(proj, ("2025-01-15", "Dotación #ingreso", "🏷️ viaje · 💶 1.000,00"),
               _pedido("2025-06-01", "P01", "100,00"),
               ("2025-06-05", "Anulado #anulacion", "🔗 P01"))
        n, neto, _p = _carry_preview(proj, CUTOFF)
        assert n == 1 and neto == D("1000.00")

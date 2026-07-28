"""test_ledger_archive.py — F5: `archive` y el arrastre del saldo.

`_clean_logbook` **borra** las entradas anteriores al corte, y un movimiento de
dinero vive en el logbook. Sin arrastre, archivar no dejaría un histórico
incompleto sino un **saldo incorrecto**, y sin avisar. Estos tests cubren que
las dos ramas (consolidar y no consolidar) dejan rastro en la verdad.

Cubre:
  - _carry_preview:  qué se lleva el corte y su neto por partida
  - _write_carry:    una entrada por partida / marca de corte con importe 0
  - flujo completo:  saldo intacto tras consolidar; saldo truncado y avisado
                     cuando se declina
  - composición:     dos archivados seguidos no pierden dinero
"""

import pytest
from datetime import date
from decimal import Decimal

from core.archive import _carry_preview, _clean_logbook, _write_carry
from core.ledger import (
    CARRY_TAG, EXPENSE_TAG, INCOME_TAG, balance, prepare_movement,
    read_movements,
)
from core.log import add_entry
from views.ledger import build_ledger_md


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


def _mov(proj, tag, importe, fecha, concepto="Mov", partida="viaje"):
    body, _ = prepare_movement(tag, importe, partida, None)
    add_entry("testproj", concepto, tag, None, fecha, project_dir=proj,
              continuations=body)


def _poblar(proj):
    """4.000 de ingreso y 1.000 de gasto antes del corte; 500 después."""
    _mov(proj, INCOME_TAG,  "4.000,00", "2025-01-15", "Anticipo")
    _mov(proj, EXPENSE_TAG, "1.000,00", "2025-03-10", "Vuelo")
    _mov(proj, EXPENSE_TAG,   "500,00", "2026-05-10", "Tren")


CUTOFF = date(2026, 1, 1)


class TestCarryPreview:

    def test_cuenta_solo_lo_anterior_al_corte(self, proj):
        _poblar(proj)
        n, neto, por_partida = _carry_preview(proj, CUTOFF)
        assert n == 2
        assert neto == Decimal("3000.00")
        assert por_partida == {"viaje": Decimal("3000.00")}

    def test_proyecto_sin_movimientos(self, proj):
        add_entry("testproj", "Nota", "apunte", None, "2025-01-15",
                  project_dir=proj)
        assert _carry_preview(proj, CUTOFF) == (0, None, {})

    def test_agrupa_por_partida(self, proj):
        _mov(proj, EXPENSE_TAG, "100", "2025-01-15", partida="viaje")
        _mov(proj, EXPENSE_TAG, "200", "2025-02-15", partida="fungible")
        _n, neto, por_partida = _carry_preview(proj, CUTOFF)
        assert por_partida == {"viaje": Decimal("-100.00"),
                               "fungible": Decimal("-200.00")}
        assert neto == Decimal("-300.00")


class TestWriteCarry:

    def test_una_entrada_por_partida(self, proj):
        # Consolidar todo en una línea destruiría el desglose para siempre.
        por_partida = {"viaje": Decimal("-100.00"),
                       "fungible": Decimal("-200.00")}
        assert _write_carry(proj, CUTOFF, por_partida, consolidate=True) == 2
        movs, problems = read_movements(proj)
        assert problems == []
        assert {m.partida: m.amount for m in movs} == por_partida
        assert all(m.tag == CARRY_TAG for m in movs)

    def test_fecha_del_arrastre_es_la_del_corte(self, proj):
        _write_carry(proj, CUTOFF, {"viaje": Decimal("10")}, consolidate=True)
        movs, _ = read_movements(proj)
        assert movs[0].date == CUTOFF

    def test_marca_de_corte_sin_arrastre(self, proj):
        _poblar(proj)
        _write_carry(proj, CUTOFF, {}, consolidate=False)
        movs, _ = read_movements(proj)
        cortes = [m for m in movs if m.is_cut]
        assert len(cortes) == 1
        assert cortes[0].date == CUTOFF

    def test_entrada_de_arrastre_lleva_marca_orbit(self, proj):
        # El usuario no escribe #arrastre nunca: lo escribe archive.
        _write_carry(proj, CUTOFF, {"viaje": Decimal("10")}, consolidate=True)
        assert "[O]" in (proj / "logbook.md").read_text()


class TestFlujoCompleto:

    def test_consolidar_preserva_el_saldo(self, proj):
        _poblar(proj)
        antes = balance(read_movements(proj)[0])
        assert antes == Decimal("2500.00")

        _n, _neto, por_partida = _carry_preview(proj, CUTOFF)
        _clean_logbook(proj, CUTOFF)
        _write_carry(proj, CUTOFF, por_partida, consolidate=True)

        movs, problems = read_movements(proj)
        assert problems == []
        assert balance(movs) == antes            # el saldo NO cambia
        assert len(movs) == 2                    # 2 archivados → 1 arrastre

    def test_declinar_trunca_el_saldo_pero_lo_avisa(self, proj):
        _poblar(proj)
        _clean_logbook(proj, CUTOFF)
        _write_carry(proj, CUTOFF, {}, consolidate=False)

        movs, _ = read_movements(proj)
        assert balance(movs) == Decimal("-500.00")   # incompleto, a sabiendas
        md = build_ledger_md(proj)
        assert "⚠️ Histórico truncado en 2026-01-01 sin arrastre" in md

    def test_sin_arrastre_el_fichero_no_calla(self, proj):
        # El fallo que F5 existe para evitar: saldo truncado con pinta de bueno.
        _poblar(proj)
        _clean_logbook(proj, CUTOFF)
        assert "truncado" not in build_ledger_md(proj)   # sin marca, calla
        _write_carry(proj, CUTOFF, {}, consolidate=False)
        assert "truncado" in build_ledger_md(proj)       # con marca, avisa

    def test_arrastre_ordena_antes_que_los_supervivientes(self, proj):
        _poblar(proj)
        _mov(proj, EXPENSE_TAG, "50,00", CUTOFF.isoformat(), "Mismo día")
        _n, _neto, por_partida = _carry_preview(proj, CUTOFF)
        _clean_logbook(proj, CUTOFF)
        _write_carry(proj, CUTOFF, por_partida, consolidate=True)
        movs, _ = read_movements(proj)
        assert movs[0].tag == CARRY_TAG          # empate de fecha → arrastre 1º

    def test_dos_archivados_seguidos_no_pierden_dinero(self, proj):
        # El segundo barrido se lleva el arrastre del primero y lo funde en el
        # nuevo neto: compone por construcción, sin caso especial.
        _poblar(proj)
        antes = balance(read_movements(proj)[0])

        for cutoff in (CUTOFF, date(2026, 7, 1)):
            _n, _neto, por_partida = _carry_preview(proj, cutoff)
            _clean_logbook(proj, cutoff)
            _write_carry(proj, cutoff, por_partida, consolidate=True)

        movs, problems = read_movements(proj)
        assert problems == []
        assert balance(movs) == antes
        assert len(movs) == 1                    # todo consolidado en uno

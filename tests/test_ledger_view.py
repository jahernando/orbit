"""test_ledger_view.py — F2 + F3 del ledger: interrogador y vista derivada.

Cubre:
  - interrogate_movement: solo pregunta lo que falta, defaults, re-pregunta,
                          la partida solo en el primer movimiento, cancelación
  - build_ledger_md:      tabla, saldo corrido, cabecera de partida, enlace al
                          justificante, aviso de corte, entradas ilegibles
  - write_ledger:         creación perezosa, idempotencia (sin churn de git)
  - refresh_all:          barrido de todos los proyectos
  - run_ls_ledger:        lectura pura (no escribe ledger.md), con y sin proyecto
"""

import builtins
import pytest
from decimal import Decimal

from core.ledger import (
    Cancelled, EXPENSE_TAG, INCOME_TAG, interrogate_movement,
    prepare_movement,
)
from core.log import add_entry
from views.ledger import (
    LEDGER_FILE, build_ledger_md, refresh_all, run_ls_ledger, write_ledger,
)


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


def _mov(proj, tag, importe, concepto="Mov", partida="viaje",
         payee=None, fecha="2026-07-14"):
    body, _ = prepare_movement(tag, importe, partida, payee)
    add_entry("testproj", concepto, tag, None, fecha, project_dir=proj,
              continuations=body)


def _answers(monkeypatch, *values):
    """Simula el teclado. StopIteration = el interrogador pidió de más."""
    it = iter(values)
    monkeypatch.setattr(builtins, "input", lambda _prompt="": next(it))


# ═══════════════════════════════════════════════════════════════════════════════
# Interrogador (F2)
# ═══════════════════════════════════════════════════════════════════════════════

class TestInterrogador:

    def test_pregunta_solo_lo_que_falta(self, proj, monkeypatch):
        _mov(proj, EXPENSE_TAG, "10")            # el proyecto ya tiene partida
        _answers(monkeypatch, "Renfe", "89,90", "2026-07-18", "")
        concept, amount, payee, partida, fecha, ref = interrogate_movement(
            proj, EXPENSE_TAG, concept="Tren", amount=None, payee=None,
            partida=None, fecha=None, ref=None)
        assert (concept, amount, payee) == ("Tren", "89,90", "Renfe")
        assert fecha == "2026-07-18"
        assert ref is None

    def test_partida_solo_en_el_primer_movimiento(self, proj, monkeypatch):
        # Proyecto virgen: la primera pregunta es la partida.
        _answers(monkeypatch, "viaje", "Vuelo", "Iberia", "218,40", "", "")
        _c, _a, _p, partida, _f, _r = interrogate_movement(
            proj, EXPENSE_TAG, concept=None, amount=None, payee=None,
            partida=None, fecha=None, ref=None)
        assert partida == "viaje"

    def test_partida_no_se_repregunta(self, proj, monkeypatch):
        _mov(proj, EXPENSE_TAG, "10", partida="fungible")
        # Si preguntara la partida, faltaría una respuesta → StopIteration.
        _answers(monkeypatch, "Folios", "", "12,00", "", "")
        concept, *_ = interrogate_movement(
            proj, EXPENSE_TAG, concept=None, amount=None, payee=None,
            partida=None, fecha=None, ref=None)
        assert concept == "Folios"

    def test_fecha_por_defecto_hoy(self, proj, monkeypatch):
        from datetime import date
        _mov(proj, EXPENSE_TAG, "10")
        _answers(monkeypatch, "Tren", "", "10,00", "", "")   # Enter en fecha
        *_, fecha, _ref = interrogate_movement(
            proj, EXPENSE_TAG, concept=None, amount=None, payee=None,
            partida=None, fecha=None, ref=None)
        assert fecha == date.today().isoformat()

    def test_importe_invalido_se_vuelve_a_pedir(self, proj, monkeypatch, capsys):
        _mov(proj, EXPENSE_TAG, "10")
        _answers(monkeypatch, "Tren", "", "-10", "doscientos", "89,90", "", "")
        _c, amount, *_ = interrogate_movement(
            proj, EXPENSE_TAG, concept=None, amount=None, payee=None,
            partida=None, fecha=None, ref=None)
        assert amount == "89,90"
        assert "sin signo" in capsys.readouterr().out

    def test_beneficiario_vacio_es_none(self, proj, monkeypatch):
        _mov(proj, EXPENSE_TAG, "10")
        _answers(monkeypatch, "Tren", "", "10,00", "", "")
        _c, _a, payee, *_ = interrogate_movement(
            proj, EXPENSE_TAG, concept=None, amount=None, payee=None,
            partida=None, fecha=None, ref=None)
        assert payee is None

    def test_ctrl_c_cancela(self, proj, monkeypatch):
        _mov(proj, EXPENSE_TAG, "10")

        def boom(_prompt=""):
            raise KeyboardInterrupt
        monkeypatch.setattr(builtins, "input", boom)
        with pytest.raises(Cancelled):
            interrogate_movement(proj, EXPENSE_TAG, concept=None, amount=None,
                                 payee=None, partida=None, fecha=None, ref=None)

    def test_campo_obligatorio_vacio_agota_intentos(self, proj, monkeypatch):
        _mov(proj, EXPENSE_TAG, "10")
        _answers(monkeypatch, "", "", "")        # item vacío tres veces
        with pytest.raises(Cancelled):
            interrogate_movement(proj, EXPENSE_TAG, concept=None, amount=None,
                                 payee=None, partida=None, fecha=None, ref=None)


# ═══════════════════════════════════════════════════════════════════════════════
# Vista derivada (F3)
# ═══════════════════════════════════════════════════════════════════════════════

class TestBuildLedgerMd:

    def test_tabla_con_saldo_corrido(self, proj):
        _mov(proj, INCOME_TAG, "4.000,00", "Anticipo", payee="UCM",
             fecha="2026-07-01")
        _mov(proj, EXPENSE_TAG, "218,40", "Vuelo", payee="Iberia",
             fecha="2026-07-14")
        md = build_ledger_md(proj)
        assert "| 2026-07-01 | Ingreso | Anticipo | UCM | +4.000,00 | 4.000,00 |" in md
        assert "| 2026-07-14 | Gasto | Vuelo | Iberia | -218,40 | 3.781,60 |" in md
        assert "**Saldo actual: 3.781,60 €**" in md

    def test_partida_en_cabecera_no_en_columna(self, proj):
        # Con una sola partida por proyecto, una columna constante no informa.
        _mov(proj, EXPENSE_TAG, "10", partida="viaje")
        md = build_ledger_md(proj)
        assert "Partida: **#viaje**" in md
        assert "| Fecha | Tipo | Concepto | Beneficiario | Importe | Saldo |" in md

    def test_tipo_en_palabra(self, proj):
        # Redundante con el signo a propósito: la dirección no depende de un
        # único canal.
        _mov(proj, INCOME_TAG, "10")
        assert "| Ingreso |" in build_ledger_md(proj)

    def test_sin_beneficiario(self, proj):
        _mov(proj, EXPENSE_TAG, "10", "Varios")
        assert "| Varios | — |" in build_ledger_md(proj)

    def test_justificante_enlazado_en_el_concepto(self, proj):
        body, _ = prepare_movement(EXPENSE_TAG, "350", "viaje")
        add_entry("testproj", "Inscripcion", EXPENSE_TAG,
                  "./cloud/logs/2026-07-20_factura.pdf", "2026-07-20",
                  project_dir=proj, continuations=body)
        assert "[Inscripcion](./cloud/logs/2026-07-20_factura.pdf)" in build_ledger_md(proj)

    def test_aviso_de_corte_sin_arrastre(self, proj):
        (proj / "logbook.md").write_text(
            "2026-01-01 💶 Archivado sin arrastre #arrastre #viaje\n  💶 0,00\n\n"
            "2026-07-14 💶 Vuelo #gasto #viaje\n  💶 -218,40\n"
        )
        md = build_ledger_md(proj)
        assert "⚠️ Histórico truncado en 2026-01-01 sin arrastre" in md

    def test_arrastre_con_importe_no_avisa(self, proj):
        (proj / "logbook.md").write_text(
            "2026-01-01 💶 Saldo arrastrado #arrastre #viaje\n  💶 1.000,00\n"
        )
        md = build_ledger_md(proj)
        assert "truncado" not in md
        assert "**Saldo actual: 1.000,00 €**" in md

    def test_entradas_ilegibles_se_cantan(self, proj):
        (proj / "logbook.md").write_text(
            "2026-07-14 💶 Vuelo sin importe #gasto #viaje\n"
        )
        md = build_ledger_md(proj)
        assert "no he podido leer" in md
        assert "sin importe" in md

    def test_sin_movimientos(self, proj):
        md = build_ledger_md(proj)
        assert "*Sin movimientos.*" in md
        assert "**Saldo actual: 0,00 €**" in md

    def test_pipe_en_el_texto_no_rompe_la_tabla(self, proj):
        _mov(proj, EXPENSE_TAG, "10", "Cable HDMI | 2m")
        assert "Cable HDMI \\| 2m" in build_ledger_md(proj)


class TestWriteLedger:

    def test_creacion_perezosa(self, proj):
        # Sin movimientos no se crea nada: es el primer fichero opcional.
        assert write_ledger(proj) is None
        assert not (proj / LEDGER_FILE).exists()

    def test_se_crea_con_el_primer_movimiento(self, proj):
        _mov(proj, EXPENSE_TAG, "218,40")
        path = write_ledger(proj)
        assert path == proj / LEDGER_FILE
        assert "creado por `ledger`" in path.read_text()

    def test_no_reescribe_si_no_cambia(self, proj):
        # El banner lleva timestamp: sin este guard, cada save ensuciaría git.
        _mov(proj, EXPENSE_TAG, "218,40")
        write_ledger(proj)
        antes = (proj / LEDGER_FILE).read_text()
        assert write_ledger(proj) is None
        assert (proj / LEDGER_FILE).read_text() == antes

    def test_reescribe_si_cambia(self, proj):
        _mov(proj, EXPENSE_TAG, "218,40")
        write_ledger(proj)
        _mov(proj, EXPENSE_TAG, "89,90", "Tren")
        assert write_ledger(proj) is not None
        assert "89,90" in (proj / LEDGER_FILE).read_text()

    def test_fichero_huerfano_se_vacia_no_se_borra(self, proj):
        _mov(proj, EXPENSE_TAG, "218,40")
        write_ledger(proj)
        (proj / "logbook.md").write_text("# Logbook\n\n")   # movimientos fuera
        write_ledger(proj)
        texto = (proj / LEDGER_FILE).read_text()
        assert (proj / LEDGER_FILE).exists()
        assert "*Sin movimientos.*" in texto


class TestRefreshAll:

    def test_barre_los_proyectos_con_movimientos(self, proj):
        _mov(proj, EXPENSE_TAG, "218,40")
        assert refresh_all() == 1
        assert (proj / LEDGER_FILE).exists()

    def test_no_crea_nada_en_proyectos_sin_ledger(self, proj):
        assert refresh_all() == 0
        assert not (proj / LEDGER_FILE).exists()


class TestRunLsLedger:

    def test_imprime_movimientos_y_saldo(self, proj, capsys):
        _mov(proj, EXPENSE_TAG, "218,40", "Hotel")
        _mov(proj, INCOME_TAG, "300", "Reintegro")
        assert run_ls_ledger("testproj") == 0
        out = capsys.readouterr().out
        assert "Hotel" in out and "Reintegro" in out
        assert "Saldo actual: 81,60" in out

    def test_no_escribe_ledger_md(self, proj, capsys):
        # `ls` lee; regenerar el fichero es cosa de `ledger` y del hook de save.
        _mov(proj, EXPENSE_TAG, "218,40")
        assert run_ls_ledger("testproj") == 0
        assert not (proj / LEDGER_FILE).exists()

    def test_sin_movimientos_sugiere_como_anotar(self, proj, capsys):
        assert run_ls_ledger("testproj") == 0
        assert "sin movimientos" in capsys.readouterr().out

    def test_sin_proyecto_barre_el_workspace(self, proj, capsys):
        _mov(proj, EXPENSE_TAG, "218,40", "Hotel")
        assert run_ls_ledger() == 0
        assert "Hotel" in capsys.readouterr().out

    def test_sin_proyecto_y_sin_movimientos_no_lista_nada(self, proj, capsys):
        assert run_ls_ledger() == 0
        assert "No hay movimientos." in capsys.readouterr().out

    def test_proyecto_inexistente(self, proj, capsys):
        assert run_ls_ledger("noexiste") == 1

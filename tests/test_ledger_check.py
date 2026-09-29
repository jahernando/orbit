"""test_ledger_check.py — F3 del ledger (ADR-053): `ledger --check`.

Un test por comprobación, con casos parecidos a los reales (datos inventados), y la
integración: `orbit doctor` solo ve los errores, el código de salida y
`.ledger-ignore`.
"""

from datetime import date

import pytest

from views.ledger_check import (
    ERROR, INFO, WARNING, IGNORE_FILE, check_ledger, run_ledger_check,
)

TODAY = date(2026, 9, 29)


@pytest.fixture
def proj(tmp_path, monkeypatch):
    type_dir = tmp_path / "⚙️gestion"
    type_dir.mkdir()
    p = type_dir / "⚙️proyx"
    p.mkdir()
    (p / "project.md").write_text("# ⚙️proyx\n")
    (p / "logbook.md").write_text("# Logbook\n\n")
    (p / "cloud" / "logs").mkdir(parents=True)
    monkeypatch.setattr("core.config.ORBIT_HOME", tmp_path)
    monkeypatch.setattr("core.config._ORBIT_JSON", tmp_path / "orbit.json")
    monkeypatch.setattr("core.log.PROJECTS_DIR", tmp_path)
    return p


def _pdf(proj, name):
    (proj / "cloud" / "logs" / name).write_text("%PDF")
    return f"cloud/logs/{name}"


def _write(proj, *entries):
    (proj / "logbook.md").write_text("# Logbook\n\n" + "\n".join(
        f"{d} 💶 {h}\n  {b}\n" for d, h, b in entries))


def _find(proj, level=None, text=""):
    return [f for f in check_ledger(proj, today=TODAY)
            if (level is None or f.level == level) and text in f.msg]


INGRESO = ("2026-07-01", "Dotación #ingreso", "🏷️ p · 💶 20.000,00")


# ── Errores ──────────────────────────────────────────────────────────────────

class TestErrors:

    def test_justificante_inexistente(self, proj):
        _write(proj, ("2026-08-31", "[Dietas](cloud/logs/no.pdf) #gasto",
                      "🏷️ p · 💶 -10,00"))
        assert _find(proj, ERROR, "no existe")

    def test_gasto_sin_justificante(self, proj):
        _write(proj, ("2026-08-31", "Dietas #gasto", "🏷️ p · 💶 -10,00"))
        assert _find(proj, ERROR, "#gasto sin justificante")

    def test_ingreso_sin_justificante_es_aviso(self, proj):
        _write(proj, INGRESO)
        assert _find(proj, WARNING, "#ingreso sin justificante")
        assert not _find(proj, ERROR)

    def test_referencia_rota_e_id_repetido(self, proj):
        f = _pdf(proj, "2026-09-01_folla.pdf")
        _write(proj,
               ("2026-09-01", f"[Folla]({f}) #pedido", "💶 -1,00 · 🆔 P01"),
               ("2026-09-02", f"[Folla 2]({f}) #pedido", "💶 -2,00 · 🆔 P01"),
               ("2026-09-03", f"[Fra]({f}) #gasto", "💶 -1,00 · 🔗 P09"))
        assert _find(proj, ERROR, "repetido")
        assert _find(proj, ERROR, "P09 no es ningún pedido")

    def test_sin_importe(self, proj):
        _write(proj, ("2026-09-01", "Folla #pedido", "🆔 P01"))
        assert _find(proj, ERROR, "sin importe")

    def test_ledger_limpio(self, proj):
        f = _pdf(proj, "2026-08-31_dietas.pdf")
        _write(proj, ("2026-08-31", f"[Dietas]({f}) #gasto", "🏷️ p · 💶 -10,00"))
        assert check_ledger(proj, today=TODAY) == []


# ── Avisos ───────────────────────────────────────────────────────────────────

class TestWarnings:

    def test_pedido_abierto_mucho_tiempo(self, proj):
        f = _pdf(proj, "2026-06-01_folla.pdf")
        _write(proj, ("2026-06-01", f"[Folla]({f}) #pedido", "💶 -1,00 · 🆔 P01"))
        assert _find(proj, WARNING, "abierto hace 120 días")

    def test_factura_candidata(self, proj):
        folla = _pdf(proj, "2026-09-18_FollaPedimento_Ginebra.pdf")
        _pdf(proj, "2026-10-02_Axencia Viaxes_4471.pdf")
        _write(proj, ("2026-09-18", f"[Folla vuelo Ginebra]({folla}) #pedido",
                      "👤 Axencia Viaxes · 💶 -1.578,64 · 🆔 P03"))
        assert _find(proj, WARNING, "factura candidata de P03")

    def test_huerfano_y_ignorados(self, proj):
        _pdf(proj, "2026-09-02_FollaPedimento_TasaInscripcion_Congreso_fdo.pdf")
        _pdf(proj, "2026-09-01_INSTITUTO_cost_report.pdf")         # no económico
        _write(proj, INGRESO)
        assert _find(proj, WARNING, "documento económico sin movimiento")
        assert not _find(proj, text="INSTITUTO")
        (proj / IGNORE_FILE).write_text("# legítimos\n*Congreso*\n")
        assert not _find(proj, text="sin movimiento")

    def test_gasto_que_enlaza_folla(self, proj):
        f = _pdf(proj, "2026-09-02_folla_pedimento_taxa.pdf")
        _write(proj, ("2026-09-02", f"[Tasa]({f}) #gasto", "💶 -300,00"))
        assert _find(proj, WARNING, "¿debería ser #pedido?")

    def test_factura_difiere_del_pedido(self, proj):
        f = _pdf(proj, "2026-09-01_x.pdf")
        _write(proj, ("2026-09-01", f"[Folla]({f}) #pedido", "💶 -100,00 · 🆔 P01"),
               ("2026-09-10", f"[Fra]({f}) #gasto", "💶 -150,00 · 🔗 P01"))
        assert _find(proj, WARNING, "difiere un 50 %")

    def test_diferencia_pequena_no_avisa(self, proj):
        f = _pdf(proj, "2026-09-01_x.pdf")
        _write(proj, ("2026-09-01", f"[Folla]({f}) #pedido", "💶 -1.578,64 · 🆔 P01"),
               ("2026-09-10", f"[Fra]({f}) #gasto", "💶 -1.580,10 · 🔗 P01"))
        assert not _find(proj, text="difiere")

    def test_posible_duplicado(self, proj):
        f = _pdf(proj, "2026-08-31_x.pdf")
        _write(proj, ("2026-08-31", f"[Tasa Congreso]({f}) #gasto", "👤 Congreso · 💶 -450,00"),
               ("2026-09-02", f"[Tasa Congreso bis]({f}) #gasto", "👤 Congreso · 💶 -450,00"))
        assert _find(proj, WARNING, "posible duplicado")

    def test_beneficiario_con_variantes(self, proj):
        f = _pdf(proj, "2026-08-31_x.pdf")
        _write(proj, ("2026-08-01", f"[A]({f}) #gasto", "👤 Ana Núñez · 💶 -1,00"),
               ("2026-08-20", f"[B]({f}) #gasto", "👤 Ana Nuñez · 💶 -2,00"))
        assert _find(proj, WARNING, "Ana Nuñez / Ana Núñez")

    def test_conciliacion_que_no_cuadra(self, proj):
        _write(proj, INGRESO, ("2026-09-30", "USC #conciliacion", "💶 1,00"))
        assert _find(proj, WARNING, "no cuadra")

    def test_conciliacion_que_cuadra(self, proj):
        _write(proj, INGRESO, ("2026-09-30", "USC #conciliacion", "💶 20.000,00"))
        assert not _find(proj, text="no cuadra")


def test_documento_de_la_autorizacion(proj):
    folla = _pdf(proj, "2026-09-18_folla_ginebra.pdf")
    _pdf(proj, "2026-09-18_CM26XXXX0001_Axencia Viaxes.pdf")          # nombre real
    _write(proj, ("2026-09-18", f"[Folla vuelo Ginebra]({folla}) #pedido",
                  "👤 Axencia Viaxes · 💶 -1.578,64 · 🆔 CM26XXXX0001"))
    assert _find(proj, WARNING, "documento de la autorización CM26XXXX0001")
    assert not _find(proj, text="factura candidata")


def test_factura_repetida(proj):
    f = _pdf(proj, "2026-08-31_x.pdf")
    _write(proj, ("2026-08-01", f"[A]({f}) #gasto", "👤 A · 💶 -1,00 · 🆔 F1"),
           ("2026-09-20", f"[B]({f}) #gasto", "👤 B · 💶 -2,00 · 🆔 F1"))
    assert _find(proj, WARNING, "la factura F1 aparece dos veces")


def test_nombres_raros(proj):
    _pdf(proj, "2026-09-18_2026-09-18_algo.pdf")
    _pdf(proj, "2026-07-15_SMARTaHEP.pdf_asinado.pdf_.pdf")
    _write(proj, INGRESO)
    assert _find(proj, INFO, "fecha duplicada")
    assert _find(proj, INFO, "extensión repetida")


def test_umbrales_configurables(proj, tmp_path):
    (tmp_path / "orbit.json").write_text('{"ledger": {"open_days": 200}}')
    f = _pdf(proj, "2026-06-01_folla.pdf")
    _write(proj, ("2026-06-01", f"[Folla]({f}) #pedido", "💶 -1,00 · 🆔 P01"))
    assert not _find(proj, text="abierto hace")


# ── Integración ──────────────────────────────────────────────────────────────

class TestIntegracion:

    def test_codigo_de_salida(self, proj, capsys):
        f = _pdf(proj, "2026-08-31_x.pdf")
        _write(proj, ("2026-08-31", f"[A]({f}) #gasto", "👤 Ana · 💶 -1,00"),
               ("2026-08-31", f"[B]({f}) #gasto", "👤 Ana · 💶 -1,00"))
        assert run_ledger_check("proyx") == 0            # solo avisos
        assert run_ledger_check("proyx", strict=True) == 1
        _write(proj, ("2026-08-31", "Sin pdf #gasto", "💶 -1,00"))
        assert run_ledger_check("proyx") == 1
        assert "1 error" in capsys.readouterr().out

    def test_doctor_solo_ve_errores(self, proj):
        from views.doctor.doctor import check_project
        f = _pdf(proj, "2026-08-31_x.pdf")
        _write(proj, ("2026-08-31", "Sin pdf #gasto", "💶 -1,00"),
               ("2026-09-01", f"[A]({f}) #gasto", "👤 Ana · 💶 -1,00"),
               ("2026-09-01", f"[B]({f}) #gasto", "👤 Ana · 💶 -1,00"))
        msgs = [i.msg for i in check_project(proj)]
        ledger = [m for m in msgs if m.startswith("Ledger:")]
        assert ledger == ["Ledger: #gasto sin justificante"]

    def test_cli(self, proj, capsys):
        import orbit
        _write(proj, INGRESO)
        args = orbit._build_parser().parse_args(["ledger", "proyx", "--check"])
        assert orbit.cmd_ledger(args) == 0
        assert "Comprobación del ledger" in capsys.readouterr().out

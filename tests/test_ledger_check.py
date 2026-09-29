"""test_ledger_check.py — `ledger --check` sin ficheros (ADR-053).

Errores (justificantes, referencias, números repetidos, entradas ilegibles),
los dos avisos (pedido abierto, documento sin movimiento) y la integración:
`orbit doctor` solo ve los errores, el código de salida y `.ledger-ignore`.
"""

from datetime import date

import pytest

from views.ledger_check import (
    ERROR, WARNING, IGNORE_FILE, check_ledger, run_ledger_check,
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


class TestErrors:

    def test_justificante_inexistente(self, proj):
        _write(proj, ("2026-08-31", "[Dietas](cloud/logs/no.pdf) #gasto",
                      "🏷️ p · 💶 -10,00"))
        assert _find(proj, ERROR, "no existe")

    def test_gasto_sin_justificante(self, proj):
        _write(proj, ("2026-08-31", "Dietas #gasto", "🏷️ p · 💶 -10,00"))
        assert _find(proj) == []          # el justificante es opcional

    def test_ingreso_sin_justificante_no_se_canta(self, proj):
        _write(proj, INGRESO)
        assert check_ledger(proj, today=TODAY) == []

    def test_referencia_rota_e_id_repetido(self, proj):
        f = _pdf(proj, "2026-09-01_folla.pdf")
        _write(proj,
               ("2026-09-01", f"[Folla]({f}) #compromiso", "💶 -1,00 · 🆔 P01"),
               ("2026-09-02", f"[Folla 2]({f}) #compromiso", "💶 -2,00 · 🆔 P01"),
               ("2026-09-03", f"[Fra]({f}) #gasto", "💶 -1,00 · 🔗 P09"))
        assert _find(proj, ERROR, "repetido")
        assert _find(proj, ERROR, "P09 no es ningún compromiso")

    def test_factura_repetida(self, proj):
        f = _pdf(proj, "2026-08-31_x.pdf")
        _write(proj, ("2026-08-01", f"[A]({f}) #gasto", "💶 -1,00 · 🆔 F1"),
               ("2026-09-20", f"[B]({f}) #gasto", "💶 -2,00 · 🆔 F1"))
        assert _find(proj, ERROR, "la referencia F1 está en dos gastos")

    def test_sin_importe(self, proj):
        _write(proj, ("2026-09-01", "Folla #compromiso", "🆔 P01"))
        assert _find(proj, ERROR, "sin importe")

    def test_ledger_limpio(self, proj):
        f = _pdf(proj, "2026-08-31_dietas.pdf")
        _write(proj, ("2026-08-31", f"[Dietas]({f}) #gasto", "🏷️ p · 💶 -10,00"))
        assert check_ledger(proj, today=TODAY) == []


class TestWarnings:

    def test_pedido_abierto_mucho_tiempo(self, proj):
        f = _pdf(proj, "2026-06-01_folla.pdf")
        _write(proj, ("2026-06-01", f"[Folla]({f}) #compromiso", "💶 -1,00 · 🆔 P01"))
        assert _find(proj, WARNING, "abierto hace 120 días")

    def test_umbral_configurable(self, proj, tmp_path):
        (tmp_path / "orbit.json").write_text('{"ledger": {"open_days": 200}}')
        f = _pdf(proj, "2026-06-01_folla.pdf")
        _write(proj, ("2026-06-01", f"[Folla]({f}) #compromiso", "💶 -1,00 · 🆔 P01"))
        assert not _find(proj, text="abierto hace")

    def test_documento_sin_movimiento_e_ignorados(self, proj):
        _pdf(proj, "2026-09-02_FollaPedimento_Tasa_Congreso_fdo.pdf")
        _pdf(proj, "2026-09-28_Invoice_escuela.pdf")
        _pdf(proj, "2026-09-01_INSTITUTO_cost_report.pdf")      # no económico
        _write(proj, INGRESO)
        assert len(_find(proj, WARNING, "documento económico sin movimiento")) == 2
        assert not _find(proj, text="INSTITUTO")
        (proj / IGNORE_FILE).write_text("# legítimos\n*Congreso*\n*Invoice*\n")
        assert not _find(proj, text="sin movimiento")

    def test_signo_corregido_es_aviso(self, proj):
        f = _pdf(proj, "2026-08-31_x.pdf")
        _write(proj, ("2026-08-31", f"[A]({f}) #gasto", "💶 10,00"))
        assert _find(proj, WARNING, "signo")
        assert not _find(proj, ERROR)


class TestIntegracion:

    def test_codigo_de_salida(self, proj, capsys):
        _pdf(proj, "2026-09-02_folla_suelta.pdf")
        _write(proj, INGRESO)
        assert run_ledger_check("proyx") == 0                # solo un aviso
        assert run_ledger_check("proyx", strict=True) == 1
        _write(proj, ("2026-08-31", "Roto #gasto", "💶 -1,00 · 🔗 P09"))
        assert run_ledger_check("proyx") == 1
        assert "1 error" in capsys.readouterr().out

    def test_doctor_solo_ve_errores(self, proj):
        from views.doctor.doctor import check_project
        _pdf(proj, "2026-09-02_folla_suelta.pdf")
        _write(proj, ("2026-08-31", "Roto #gasto", "💶 -1,00 · 🔗 P09"),)
        msgs = [i.msg for i in check_project(proj)]
        assert [m for m in msgs if m.startswith("Ledger:")] == \
            ["Ledger: 2026-08-31 Roto: 🔗 P09 no es ningún compromiso"]

    def test_cli(self, proj, capsys):
        import orbit
        _write(proj, INGRESO)
        args = orbit._build_parser().parse_args(["ledger", "proyx", "--check"])
        assert orbit.cmd_ledger(args) == 0
        assert "Comprobación del ledger" in capsys.readouterr().out

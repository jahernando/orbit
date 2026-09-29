"""test_ledger_export.py — F4 del ledger (ADR-053): `ledger --export`.

Necesita `reportlab` y `openpyxl` (extra `ledger`); sin ellos, se salta.
"""

import re
from datetime import datetime
from decimal import Decimal

import pytest

pytest.importorskip("reportlab")
openpyxl = pytest.importorskip("openpyxl")

from views.ledger_export import (  # noqa: E402
    JUST_DIR, PDF_FILE, XLSX_FILE, export_ledger, plan_attachments,
    run_ledger_export,
)
from core.ledger import read_movements  # noqa: E402


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


def _pdf(proj, name, sub="cloud/logs"):
    d = proj / sub
    d.mkdir(parents=True, exist_ok=True)
    (d / name).write_text(f"%PDF {name}")
    return f"{sub}/{name}"


def _write(proj, *entries):
    (proj / "logbook.md").write_text("# Logbook\n\n" + "\n".join(
        f"{d} 💶 {h}\n  {b}\n" for d, h, b in entries))


def _ledger(proj):
    a = _pdf(proj, "2026-09-18_folla.pdf")
    b = _pdf(proj, "2026-10-02_factura.pdf")
    c = _pdf(proj, "2026-08-06_resolucion.pdf")
    _pdf(proj, "2026-09-01_nomina_SENSIBLE.pdf")          # no enlazado
    _write(proj,
           ("2026-08-06", f"[Dotación]({c}) #ingreso", "🏷️ p · 💶 20.000,00"),
           ("2026-09-18", f"[Folla vuelo]({a}) #pedido",
            "👤 Axencia · 💶 -1.578,64 · 💱 1.500,00 CHF · 🆔 CM26XXXX0001"),
           ("2026-10-02", f"[Factura vuelo]({b}) #gasto",
            "👤 Axencia · 💶 -1.580,10 · 🆔 F-4471 · 🔗 CM26XXXX0001"))


GEN = datetime(2026, 10, 5, 9, 30)


def test_paquete(proj, tmp_path):
    _ledger(proj)
    out = tmp_path / "share"
    stats = export_ledger(proj, out, generated=GEN)
    assert (out / PDF_FILE).exists() and (out / XLSX_FILE).exists()
    names = sorted(f.name for f in (out / JUST_DIR).iterdir())
    assert names == ["2026-08-06_resolucion.pdf", "2026-09-18_folla.pdf",
                     "2026-10-02_factura.pdf"]            # nunca lo no enlazado
    assert stats["attachments"] == 3 and stats["copied"] == 3


def test_pdf_con_enlaces_relativos(proj, tmp_path):
    _ledger(proj)
    export_ledger(proj, tmp_path / "share", generated=GEN)
    raw = (tmp_path / "share" / PDF_FILE).read_bytes()
    uris = set(re.findall(rb"/URI \(([^)]*)\)", raw))
    assert b"justificantes/2026-09-18_folla.pdf" in uris
    assert not any(u.startswith(b"/") for u in uris)


def test_xlsx(proj, tmp_path):
    _ledger(proj)
    export_ledger(proj, tmp_path / "share", generated=GEN)
    wb = openpyxl.load_workbook(tmp_path / "share" / XLSX_FILE)
    assert wb.sheetnames == ["Resumen", "Operaciones", "Movimientos"]

    resumen = {r[0]: r[1] for r in wb["Resumen"].iter_rows(values_only=True) if r[0]}
    assert Decimal(str(resumen["Disponible"])) == Decimal("18419.90")

    ops = list(wb["Operaciones"].iter_rows(values_only=True))
    assert ops[0][:3] == ("Fecha", "Aut.", "Factura")
    assert ops[1][1:4] == ("CM26XXXX0001", "F-4471", "Folla vuelo")
    assert ops[1][8] == "cerrado" and ops[1][9] == "1.500,00 CHF"
    assert wb["Operaciones"].cell(2, 4).hyperlink.target == \
        "justificantes/2026-09-18_folla.pdf"

    movs = wb["Movimientos"]
    assert movs.cell(4, 9).hyperlink.target == "justificantes/2026-10-02_factura.pdf"
    assert movs.cell(4, 4).value == "CM26XXXX0001"


def test_errores_bloquean(proj, tmp_path):
    _write(proj, ("2026-08-31", "Dietas sin justificante #gasto", "💶 -10,00"))
    with pytest.raises(ValueError, match="no se exporta"):
        export_ledger(proj, tmp_path / "share")
    assert not (tmp_path / "share").exists()


def test_idempotente_y_sincroniza(proj, tmp_path):
    _ledger(proj)
    out = tmp_path / "share"
    export_ledger(proj, out, generated=GEN)
    stats = export_ledger(proj, out, generated=GEN)
    assert stats["copied"] == 0 and stats["removed"] == 0
    # La factura deja de estar enlazada → desaparece de justificantes/.
    c = "cloud/logs/2026-08-06_resolucion.pdf"
    _write(proj, ("2026-08-06", f"[Dotación]({c}) #ingreso", "🏷️ p · 💶 20.000,00"))
    stats = export_ledger(proj, out, generated=GEN)
    assert stats["removed"] == 2
    assert [f.name for f in (out / JUST_DIR).iterdir()] == ["2026-08-06_resolucion.pdf"]


def test_mismo_nombre_no_se_pisa(proj):
    a = _pdf(proj, "factura.pdf", "cloud/logs")
    b = _pdf(proj, "factura.pdf", "cloud/otros")
    _write(proj, ("2026-08-01", f"[A]({a}) #gasto", "💶 -1,00"),
           ("2026-08-02", f"[B]({b}) #gasto", "💶 -2,00"))
    plan = plan_attachments(proj, read_movements(proj)[0])
    assert sorted(name for _src, name in plan.values()) == ["factura.pdf",
                                                             "factura_2.pdf"]


def test_cli(proj, tmp_path, capsys):
    import orbit
    _ledger(proj)
    out = tmp_path / "share"
    args = orbit._build_parser().parse_args(
        ["ledger", "proyx", "--export", str(out)])
    assert orbit.cmd_ledger(args) == 0
    assert "3 justificantes" in capsys.readouterr().out
    assert run_ledger_export("noexiste", str(out)) == 1

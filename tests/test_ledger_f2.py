"""test_ledger_f2.py — anotar ingresos, compromisos y gastos desde la CLI (ADR-053).

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
    # --import copia a cloud_root: hace falta un orbit.json con él.
    import json
    cloud = tmp_path / "cloudroot"
    cloud.mkdir()
    (tmp_path / "orbit.json").write_text(json.dumps({"cloud_root": str(cloud)}))
    monkeypatch.setattr("core.config.ORBIT_HOME", tmp_path)
    monkeypatch.setattr("core.config._ORBIT_JSON", tmp_path / "orbit.json")
    monkeypatch.setattr("core.config.PROJECTS_DIR", tmp_path)
    monkeypatch.setattr("core.log.PROJECTS_DIR", tmp_path)
    monkeypatch.setattr("core.deliver.ORBIT_DIR", tmp_path)
    return p


def _answers(monkeypatch, *values):
    it = iter(values)
    monkeypatch.setattr(builtins, "input", lambda _prompt="": next(it))


def _log(concept, *argv, pdf=False):
    """`orbit log testproj <concepto> <pdf> …` con un PDF de fuera del proyecto
    (se importa a cloud/logs/)."""
    import orbit
    import tempfile
    extra = []
    if pdf:
        f = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False,
                                        prefix=concept.replace(" ", "_") + "_")
        f.write(b"%PDF")
        f.close()
        extra = [f.name]
    args = orbit._build_parser().parse_args(["log", "testproj", concept, *extra, *argv])
    return orbit.cmd_log(args)


def _movs(proj, text):
    (proj / "logbook.md").write_text("# Logbook\n\n" + text)
    return read_movements(proj)[0]


COMP = "2026-09-01 💶 Reserva #compromiso\n  🏷️ viaje · 👤 X · 💶 -100,00 · 🆔 {}\n\n"


# ── Cuerpo y reglas ──────────────────────────────────────────────────────────

class TestBody:

    def test_compromiso(self):
        body = build_body(D("-1234.56"), "viaje", "Agencia", op_id="CM26XX0001")
        assert body == ["🏷️ viaje · 👤 Agencia · 💶 -1.234,56 · 🆔 CM26XX0001"]
        mov, problem = parse_entry("2026-09-18", "💶 Reserva #compromiso", body)
        assert problem is None and mov.op_id == "CM26XX0001"

    def test_gasto_que_cierra_con_nota(self):
        body = build_body(D("-10"), "viaje", op_id="F-1", ref="P03", closes=True,
                          note="300 CHF,  al cambio")
        assert body == ["🏷️ viaje · 💶 -10,00 · 🆔 F-1 · 🔗 P03 · 🔒 cierra",
                        "📝 300 CHF, al cambio"]
        mov, _ = parse_entry("2026-10-01", "💶 Fra #gasto", body)
        assert mov.closes and mov.note == "300 CHF, al cambio" and mov.ref == "P03"


class TestPrepare:

    def test_compromiso_exige_referencia(self):
        with pytest.raises(ValueError, match="necesita referencia"):
            prepare_movement(ORDER_TAG, "100", "viaje")

    def test_compromiso_negativo(self):
        _b, amount = prepare_movement(ORDER_TAG, "100", "viaje", op_id="P01")
        assert amount == D("-100.00")

    def test_referencia_sin_espacios(self):
        with pytest.raises(ValueError):
            prepare_movement(ORDER_TAG, "100", "viaje", op_id="P 1")

    def test_compromiso_solo_en_gasto(self):
        with pytest.raises(ValueError, match="--compromiso solo"):
            prepare_movement(INCOME_TAG, "10", "viaje", ref="P01")

    def test_cierra_exige_compromiso(self):
        with pytest.raises(ValueError, match="--cierra"):
            prepare_movement(EXPENSE_TAG, "10", "viaje", closes=True)

    def test_tags_usc_retiradas(self):
        for tag in ("folla", "dietas", "factura", "pedido"):
            with pytest.raises(ValueError, match="no es una tag"):
                prepare_movement(tag, "10", "viaje")


# ── referencias ──────────────────────────────────────────────────────────────

class TestIds:

    def test_primero(self):
        assert next_order_id([]) == "P01"

    def test_siguiente_respeta_prefijo_y_ancho(self, proj):
        movs = _movs(proj, COMP.format("P09") + COMP.format("P02"))
        assert next_order_id(movs) == "P10"
        movs = _movs(proj, COMP.format("OP003"))
        assert next_order_id(movs) == "OP004"

    def test_referencia_externa_no_cuenta_para_el_siguiente(self, proj):
        movs = _movs(proj, COMP.format("CM26XX0001") + COMP.format("P02"))
        assert next_order_id(movs) == "P03"

    def test_id_repetido(self, proj):
        movs = _movs(proj, COMP.format("P01"))
        with pytest.raises(ValueError, match="P02"):
            check_links(movs, ORDER_TAG, op_id="P01")

    def test_ref_inexistente(self, proj):
        movs = _movs(proj, COMP.format("P01"))
        with pytest.raises(ValueError, match="abiertos: P01"):
            check_links(movs, EXPENSE_TAG, ref="P07")

    def test_ref_cerrado(self, proj):
        movs = _movs(proj, COMP.format("P01")
                     + "2026-09-10 💶 Fra #gasto\n  💶 -100,00 · 🔗 P01\n")
        with pytest.raises(ValueError, match="ya está cerrado"):
            check_links(movs, EXPENSE_TAG, ref="P01")

    def test_referencia_de_gasto_repetida(self, proj):
        movs = _movs(proj, "2026-09-10 💶 Fra #gasto\n  💶 -1,00 · 🆔 F-1\n")
        with pytest.raises(ValueError, match="ya está en otro gasto"):
            check_links(movs, EXPENSE_TAG, op_id="F-1")


# ── Interrogador ─────────────────────────────────────────────────────────────

class TestInterrogador:

    def test_compromiso_sugiere_referencia(self, proj, monkeypatch):
        movs = _movs(proj, COMP.format("P04"))
        _answers(monkeypatch, "", "")            # referencia sugerida, sin nota
        assert interrogate_commitment(movs, ORDER_TAG, op_id=None,
                                      ref=None) == ("P05", None, False, None)

    def test_gasto_lista_los_compromisos_abiertos(self, proj, monkeypatch, capsys):
        movs = _movs(proj, COMP.format("P01"))
        _answers(monkeypatch, "P01", "F-1", "nota")
        assert interrogate_commitment(movs, EXPENSE_TAG, op_id=None, ref=None,
                                      amount="100") == ("F-1", "P01", False, "nota")
        out = capsys.readouterr().out
        assert "Compromisos abiertos" in out and "P01" in out

    def test_gasto_menor_pregunta_si_cierra(self, proj, monkeypatch):
        movs = _movs(proj, COMP.format("P01"))
        _answers(monkeypatch, "P01", "s", "", "")
        _i, _r, closes, _n = interrogate_commitment(
            movs, EXPENSE_TAG, op_id=None, ref=None, amount="60")
        assert closes

    def test_gasto_sin_compromisos_no_pregunta(self, proj, monkeypatch):
        _answers(monkeypatch, "", "")            # referencia y nota
        assert interrogate_commitment([], EXPENSE_TAG, op_id=None,
                                      ref=None) == (None, None, False, None)

    def test_ref_mala_se_vuelve_a_pedir(self, proj, monkeypatch, capsys):
        movs = _movs(proj, COMP.format("P01"))
        _answers(monkeypatch, "P09", "P01", "", "")
        _i, ref, _c, _n = interrogate_commitment(movs, EXPENSE_TAG, op_id=None,
                                                 ref=None)
        assert ref == "P01"
        assert "no hay ningún compromiso P09" in capsys.readouterr().out


# ── `orbit log` de punta a punta ─────────────────────────────────────────────

class TestLogCli:

    def _ops(self, proj):
        return build_operations(read_movements(proj)[0])

    def test_compromiso_y_varios_gastos(self, proj, capsys):
        assert _log("Dotación", "--entry", "ingreso", "--amount", "10.000",
                    "--tag", "viaje", "--payee", "Xunta") == 0
        assert _log("Reserva vuelo", "--entry", "compromiso", "--amount", "1.000",
                    "--payee", "Axencia") == 0
        assert "🆔 P01" in capsys.readouterr().out     # referencia asignada
        assert _log("Fra 1", "--entry", "gasto", "--amount", "300",
                    "--id", "F-1", "--compromiso", "P01", "--payee", "Axencia") == 0
        ops, _ = self._ops(proj)
        assert ops[0].state == OPEN and ops[0].pending == D("700.00")
        assert _log("Fra 2", "--entry", "gasto", "--amount", "650",
                    "--compromiso", "P01", "--cierra", "--payee", "Axencia") == 0
        assert "consume P01 y lo cierra" in capsys.readouterr().out
        ops, problems = self._ops(proj)
        assert problems == [] and ops[0].state == CLOSED and ops[0].pending == 0

    def test_se_cierra_solo_al_cubrirlo(self, proj):
        _log("Reserva", "--entry", "compromiso", "--amount", "100", "--tag", "v",
             "--payee", "X")
        _log("Fra", "--entry", "gasto", "--amount", "101", "--compromiso", "P01",
             "--payee", "X")
        assert self._ops(proj)[0][0].state == CLOSED

    def test_sin_justificante_vale(self, proj):
        assert _log("Café", "--entry", "gasto", "--amount", "2", "--tag", "v",
                    "--payee", "Bar", "--nota", "con Ana") == 0
        m = read_movements(proj)[0][0]
        assert m.link is None and m.note == "con Ana"

    def test_justificante_se_importa(self, proj):
        assert _log("Reserva vuelo", "--entry", "compromiso", "--amount", "100",
                    "--tag", "viaje", "--payee", "Axencia", pdf=True) == 0
        m = read_movements(proj)[0][0]
        assert "cloud/logs/" in m.link
        assert len(list((proj.parent.parent / "cloudroot").rglob("*.pdf"))) == 1

    def test_justificante_inexistente(self, proj, capsys):
        import orbit
        args = orbit._build_parser().parse_args(
            ["log", "testproj", "X", "/no/existe.pdf", "--entry", "gasto",
             "--amount", "1", "--tag", "v", "--payee", "X"])
        assert orbit.cmd_log(args) == 1
        assert "no encuentro el justificante" in capsys.readouterr().out

    def test_justificante_ya_dentro_del_proyecto_no_se_copia(self, proj):
        logs = proj / "cloud" / "logs"
        logs.mkdir(parents=True)
        (logs / "2026-09-01_reserva.pdf").write_text("%PDF")
        import orbit
        args = orbit._build_parser().parse_args(
            ["log", "testproj", "Reserva", "cloud/logs/2026-09-01_reserva.pdf",
             "--entry", "compromiso", "--amount", "10", "--tag", "viaje", "--payee", "X"])
        assert orbit.cmd_log(args) == 0
        assert len(list(logs.iterdir())) == 1
        assert read_movements(proj)[0][0].link == "./cloud/logs/2026-09-01_reserva.pdf"

    def test_beneficiario_obligatorio(self, proj, capsys):
        assert _log("Reserva", "--entry", "compromiso", "--amount", "100",
                    "--tag", "viaje") == 1
        assert "falta el beneficiario" in capsys.readouterr().out

    def test_ledger_sin_terminal_pide_el_tipo(self, proj, capsys):
        assert _log("X", "--entry", "ledger", "--amount", "1", "--payee", "X") == 1
        assert "ingreso|compromiso|gasto" in capsys.readouterr().out

    def test_ref_inexistente_no_escribe(self, proj, capsys):
        _log("Reserva", "--entry", "compromiso", "--amount", "100", "--tag", "viaje",
             "--payee", "X")
        antes = (proj / "logbook.md").read_text()
        assert _log("Fra", "--entry", "gasto", "--amount", "100",
                    "--compromiso", "P09", "--payee", "X") == 1
        assert "no hay ningún compromiso P09" in capsys.readouterr().out
        assert (proj / "logbook.md").read_text() == antes

    def test_close_a_mano(self, proj, capsys):
        import orbit
        _log("Reserva", "--entry", "compromiso", "--amount", "100", "--tag", "v",
             "--payee", "X")
        args = orbit._build_parser().parse_args(["ledger", "testproj", "--close", "P01"])
        assert orbit.cmd_ledger(args) == 0
        ops, _ = self._ops(proj)
        assert ops[0].state == CLOSED and ops[0].pending == 0


# ── ledger.json: el contrato con la conciliación externa ─────────────────────

def test_ledger_json(proj):
    import json
    from views.ledger import LEDGER_JSON, write_ledger
    _movs(proj, "2026-08-06 💶 Dotación #ingreso\n  🏷️ p · 👤 Xunta · 💶 20.000,00\n\n"
                "2026-09-18 💶 Reserva #compromiso\n"
                "  🏷️ p · 👤 Axencia · 💶 -1.578,64 · 🆔 CM26XX0001\n\n"
                "2026-10-02 💶 Fra #gasto\n  🏷️ p · 👤 Axencia · 💶 -1.580,10 · "
                "🆔 F-1 · 🔗 CM26XX0001\n  📝 al cambio\n")
    write_ledger(proj, force=True)
    data = json.loads((proj / LEDGER_JSON).read_text())
    assert data["version"] == 1 and data["partida"] == "p"
    assert data["summary"]["available"] == "18419.90"
    comp = data["movements"][1]
    assert comp["type"] == "compromiso" and comp["id"] == "CM26XX0001"
    assert comp["amount"] == "-1578.64" and comp["state"] == "cerrado"
    gasto = data["movements"][2]
    assert gasto["order"] == "CM26XX0001" and gasto["note"] == "al cambio"
    assert all(r["key"] for r in data["movements"])
    antes = (proj / LEDGER_JSON).stat().st_mtime_ns
    write_ledger(proj)                            # sin cambios: no lo toca
    assert (proj / LEDGER_JSON).stat().st_mtime_ns == antes

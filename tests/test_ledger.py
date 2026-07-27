"""test_ledger.py — F1 del ledger: capa de datos del libro de caja.

Cubre:
  - parse_amount:      convención ES y anglosajona, rechazo de signo y de basura
  - format_amount:     millares, 2 decimales, signo explícito opcional
  - signed_amount:     el signo lo deriva la tag, nunca el usuario
  - prepare_movement:  partida e importe obligatorios, #arrastre no se teclea
  - build_body:        cuerpo del movimiento (importe + beneficiario)
  - parse_entry:       cabecera + cuerpo → Movement; enlace, partida, problemas
  - read_movements:    orden por fecha con #arrastre primero en empate
  - balance:           suma con signo
  - integración:       add_entry escribe un movimiento releíble
"""

import pytest
from datetime import date
from decimal import Decimal

from core.ledger import (
    CARRY_TAG, EXPENSE_TAG, INCOME_TAG, LEDGER_TAGS,
    Movement, balance, build_body, format_amount, parse_amount, parse_entry,
    prepare_movement, project_partida, read_movements, resolve_partida,
    scan_text, signed_amount,
)
from core.log import TAG_EMOJI, VALID_TYPES, add_entry


@pytest.fixture
def ledger_env(tmp_path, monkeypatch):
    """Proyecto aislado en formato genérico, con logbook vacío."""
    type_dir = tmp_path / "💻software"
    type_dir.mkdir()
    proj = type_dir / "💻testproj"
    proj.mkdir()
    (proj / "project.md").write_text("# 💻testproj\n- Tipo: 💻 Software\n")
    (proj / "logbook.md").write_text("# Logbook — 💻testproj\n\n")

    monkeypatch.setattr("core.config.ORBIT_HOME", tmp_path)
    monkeypatch.setattr("core.config._ORBIT_JSON", tmp_path / "orbit.json")
    monkeypatch.setattr("core.log.PROJECTS_DIR", tmp_path)
    return proj


# ═══════════════════════════════════════════════════════════════════════════════
# Importes
# ═══════════════════════════════════════════════════════════════════════════════

class TestParseAmount:

    @pytest.mark.parametrize("raw,expected", [
        ("218,40",      "218.40"),    # coma decimal (ES)
        ("4.000,00",    "4000.00"),   # millares + coma decimal (ES)
        ("218.40",      "218.40"),    # punto decimal (US)
        ("4.000",       "4000.00"),   # 3 dígitos detrás → millares
        ("1.234.567",   "1234567.00"),
        ("1,5",         "1.50"),
        ("0",           "0.00"),
        (" 218,40 € ",  "218.40"),    # símbolo y espacios se limpian
    ])
    def test_formatos_aceptados(self, raw, expected):
        assert parse_amount(raw) == Decimal(expected)

    def test_devuelve_decimal_no_float(self):
        assert isinstance(parse_amount("0,1"), Decimal)
        # La suma que un float estropearía
        total = parse_amount("0,1") + parse_amount("0,2")
        assert total == Decimal("0.30")

    def test_signo_rechazado_por_defecto(self):
        # El signo lo pone la tag: aceptarlo aquí permitiría un ingreso negativo.
        with pytest.raises(ValueError, match="sin signo"):
            parse_amount("-218,40")

    def test_signo_permitido_al_releer_la_verdad(self):
        assert parse_amount("-218,40", allow_sign=True) == Decimal("-218.40")
        assert parse_amount("−218,40", allow_sign=True) == Decimal("-218.40")

    def test_mas_de_dos_decimales_se_rechaza(self):
        # Redondear en silencio falsearía el saldo.
        with pytest.raises(ValueError, match="decimales"):
            parse_amount("218,405")

    @pytest.mark.parametrize("raw", ["", "   ", "abc", "12,34,56", "12€34"])
    def test_basura_rechazada(self, raw):
        with pytest.raises(ValueError):
            parse_amount(raw)


class TestFormatAmount:

    @pytest.mark.parametrize("value,expected", [
        ("218.40",      "218,40"),
        ("-218.40",     "-218,40"),
        ("4000",        "4.000,00"),
        ("1234567.5",   "1.234.567,50"),
        ("0",           "0,00"),
    ])
    def test_convencion_espanola(self, value, expected):
        assert format_amount(Decimal(value)) == expected

    def test_signo_explicito(self):
        assert format_amount(Decimal("4000"), plus=True) == "+4.000,00"
        assert format_amount(Decimal("-218.40"), plus=True) == "-218,40"

    def test_roundtrip(self):
        for raw in ("218,40", "4.000,00", "1.234.567,89"):
            assert format_amount(parse_amount(raw)) == raw


class TestSignedAmount:

    def test_gasto_resta_ingreso_suma(self):
        assert signed_amount(EXPENSE_TAG, Decimal("218.40")) == Decimal("-218.40")
        assert signed_amount(INCOME_TAG,  Decimal("218.40")) == Decimal("218.40")

    def test_magnitud_con_signo_no_invierte_la_direccion(self):
        # Aunque llegue negativo, un ingreso suma: manda la tag.
        assert signed_amount(INCOME_TAG, Decimal("-50")) == Decimal("50.00")

    def test_arrastre_no_deriva_signo(self):
        with pytest.raises(ValueError):
            signed_amount(CARRY_TAG, Decimal("10"))


# ═══════════════════════════════════════════════════════════════════════════════
# Escritura
# ═══════════════════════════════════════════════════════════════════════════════

class TestPrepareMovement:

    def test_movimiento_completo(self):
        tags, body, amount = prepare_movement(EXPENSE_TAG, "218,40", "viaje", "Iberia")
        assert tags == ["viaje"]
        assert body == ["💶 -218,40", "👤 Iberia"]
        assert amount == Decimal("-218.40")

    def test_partida_obligatoria(self):
        with pytest.raises(ValueError, match="partida"):
            prepare_movement(EXPENSE_TAG, "218,40", None)

    def test_importe_obligatorio(self):
        with pytest.raises(ValueError, match="importe"):
            prepare_movement(EXPENSE_TAG, None, "viaje")

    def test_arrastre_no_se_teclea(self):
        with pytest.raises(ValueError, match="archive"):
            prepare_movement(CARRY_TAG, "100", "viaje")

    def test_almohadilla_de_la_partida_se_tolera(self):
        tags, _, _ = prepare_movement(INCOME_TAG, "100", "#financiacion")
        assert tags == ["financiacion"]

    def test_partida_con_espacios_rechazada(self):
        with pytest.raises(ValueError, match="espacios"):
            prepare_movement(EXPENSE_TAG, "100", "material de oficina")

    def test_beneficiario_opcional(self):
        _, body, _ = prepare_movement(EXPENSE_TAG, "100", "viaje")
        assert body == ["💶 -100,00"]


class TestResolvePartida:
    """Un proyecto tiene una sola partida: se declara una vez y se hereda."""

    def _mov(self, proj, partida, importe="10,00"):
        tags, body, _ = prepare_movement(EXPENSE_TAG, importe, partida)
        add_entry("testproj", f"Mov {partida}", EXPENSE_TAG, None, "2026-07-14",
                  project_dir=proj, continuations=body, extra_tags=tags)

    def test_primer_movimiento_debe_declararla(self, ledger_env):
        with pytest.raises(ValueError, match="aún no tiene partida"):
            resolve_partida(ledger_env, None)

    def test_se_hereda_sin_teclearla(self, ledger_env):
        self._mov(ledger_env, "viaje")
        assert resolve_partida(ledger_env, None) == "viaje"

    def test_misma_partida_explicita(self, ledger_env):
        self._mov(ledger_env, "viaje")
        assert resolve_partida(ledger_env, "#viaje") == "viaje"

    def test_partida_distinta_pide_confirmacion(self, ledger_env):
        self._mov(ledger_env, "viaje")
        # Aceptada explícitamente → se usa
        assert resolve_partida(ledger_env, "fungible",
                               confirm=lambda _p: True) == "fungible"

    def test_partida_distinta_sin_confirmar_aborta(self, ledger_env):
        # Casi siempre es un error de tecleo (#viajes por #viaje).
        self._mov(ledger_env, "viaje")
        with pytest.raises(ValueError, match="#viaje"):
            resolve_partida(ledger_env, "viajes", confirm=lambda _p: False)

    def test_sin_tty_no_da_por_buena_la_duda(self, ledger_env, monkeypatch):
        self._mov(ledger_env, "viaje")
        monkeypatch.setattr("sys.stdin.isatty", lambda: False)
        with pytest.raises(ValueError):
            resolve_partida(ledger_env, "viajes")

    def test_proyecto_sin_movimientos_con_tag_explicita(self, ledger_env):
        assert resolve_partida(ledger_env, "viaje") == "viaje"


class TestBuildBody:

    def test_sin_beneficiario(self):
        assert build_body(Decimal("-218.40")) == ["💶 -218,40"]

    def test_beneficiario_en_blanco_se_omite(self):
        assert build_body(Decimal("100"), "   ") == ["💶 100,00"]


# ═══════════════════════════════════════════════════════════════════════════════
# Lectura
# ═══════════════════════════════════════════════════════════════════════════════

class TestParseEntry:

    def test_movimiento_basico(self):
        mov, problem = parse_entry(
            "2026-07-14", "💶 Vuelo Madrid–Ginebra #gasto #viaje",
            ["💶 -218,40", "👤 Iberia"],
        )
        assert problem is None
        assert mov.date == date(2026, 7, 14)
        assert mov.tag == EXPENSE_TAG
        assert mov.concept == "Vuelo Madrid–Ginebra"
        assert mov.amount == Decimal("-218.40")
        assert mov.partida == "viaje"
        assert mov.payee == "Iberia"
        assert mov.link is None

    def test_justificante_va_en_el_enlace_de_cabecera(self):
        mov, _ = parse_entry(
            "2026-07-14",
            "💶 [Vuelo](cloud/logs/2026-07-14_factura.pdf) #gasto #viaje",
            ["💶 -218,40"],
        )
        assert mov.concept == "Vuelo"
        assert mov.link == "cloud/logs/2026-07-14_factura.pdf"

    def test_entrada_normal_no_es_del_ledger(self):
        mov, problem = parse_entry("2026-07-14", "📝 Una nota #apunte", [])
        assert mov is None and problem is None

    def test_movimiento_sin_importe_es_problema(self):
        mov, problem = parse_entry("2026-07-14", "💶 Vuelo #gasto #viaje", [])
        assert mov is None
        assert "sin importe" in problem

    def test_importe_ilegible_es_problema(self):
        mov, problem = parse_entry("2026-07-14", "💶 Vuelo #gasto", ["💶 doscientos"])
        assert mov is None and problem

    def test_signo_contradictorio_manda_la_tag(self):
        # Edición a mano: #gasto con importe positivo. Se corrige y se canta.
        mov, problem = parse_entry("2026-07-14", "💶 Vuelo #gasto #viaje", ["💶 218,40"])
        assert mov.amount == Decimal("-218.40")
        assert "contradice" in problem

    def test_arrastre_admite_signo_libre(self):
        mov, problem = parse_entry(
            "2026-01-01", "💶 Saldo arrastrado #arrastre #viaje", ["💶 -1.240,50"])
        assert problem is None
        assert mov.tag == CARRY_TAG
        assert mov.amount == Decimal("-1240.50")

    def test_marca_de_corte_sin_arrastre(self):
        mov, _ = parse_entry("2026-01-01", "💶 Archivado sin arrastre #arrastre",
                             ["💶 0,00"])
        assert mov.is_cut

    def test_arrastre_con_importe_no_es_corte(self):
        mov, _ = parse_entry("2026-01-01", "💶 Saldo #arrastre", ["💶 -10,00"])
        assert not mov.is_cut

    def test_sin_partida(self):
        mov, _ = parse_entry("2026-07-14", "💶 Vuelo #gasto", ["💶 218,40"])
        assert mov.partida is None

    def test_marcador_orbit_no_ensucia_el_concepto(self):
        mov, _ = parse_entry("2026-07-14", "💶 Cuota #gasto #viaje [O]", ["💶 10,00"])
        assert mov.concept == "Cuota"


class TestScanText:

    LOGBOOK = (
        "# Logbook — testproj\n\n"
        "2026-07-01 💶 Anticipo PID2024 #ingreso #financiacion\n"
        "  💶 +4.000,00\n"
        "  👤 UCM\n\n"
        "2026-07-10 📝 Una nota cualquiera #apunte\n\n"
        "2026-07-14 💶 Vuelo Madrid–Ginebra #gasto #viaje\n"
        "  💶 -218,40\n"
        "  👤 Iberia\n"
    )

    def test_extrae_solo_movimientos(self):
        movs, problems = scan_text(self.LOGBOOK)
        assert len(movs) == 2
        assert problems == []
        assert [m.tag for m in movs] == [INCOME_TAG, EXPENSE_TAG]

    def test_logbook_sin_movimientos(self):
        movs, problems = scan_text("# Logbook\n\n2026-07-01 📝 Nota #apunte\n")
        assert movs == [] and problems == []

    def test_cuerpo_de_otra_entrada_no_contamina(self):
        text = ("2026-07-01 💶 Gasto #gasto #viaje\n  💶 -10,00\n\n"
                "2026-07-02 📝 Nota #apunte\n  💶 -999,00\n")
        movs, _ = scan_text(text)
        assert len(movs) == 1
        assert movs[0].amount == Decimal("-10.00")


class TestReadMovements:

    def test_orden_por_fecha(self, ledger_env):
        (ledger_env / "logbook.md").write_text(
            "2026-07-14 💶 Vuelo #gasto #viaje\n  💶 -218,40\n\n"
            "2026-07-01 💶 Anticipo #ingreso #financiacion\n  💶 4.000,00\n"
        )
        movs, _ = read_movements(ledger_env)
        assert [m.date.day for m in movs] == [1, 14]

    def test_arrastre_primero_en_empate(self, ledger_env):
        # El saldo corrido depende de esto: el arrastre consolida lo anterior.
        (ledger_env / "logbook.md").write_text(
            "2026-01-01 💶 Gasto del día #gasto #viaje\n  💶 -50,00\n\n"
            "2026-01-01 💶 Saldo arrastrado #arrastre #viaje\n  💶 100,00\n"
        )
        movs, _ = read_movements(ledger_env)
        assert movs[0].tag == CARRY_TAG

    def test_proyecto_sin_logbook(self, tmp_path):
        movs, problems = read_movements(tmp_path / "nada")
        assert movs == [] and problems == []


class TestBalance:

    def test_suma_con_signo(self):
        movs = [
            Movement(date(2026, 7, 1), INCOME_TAG, "Anticipo", Decimal("4000.00")),
            Movement(date(2026, 7, 14), EXPENSE_TAG, "Vuelo", Decimal("-218.40")),
        ]
        assert balance(movs) == Decimal("3781.60")

    def test_sin_movimientos(self):
        assert balance([]) == Decimal("0.00")


# ═══════════════════════════════════════════════════════════════════════════════
# Integración con el logbook
# ═══════════════════════════════════════════════════════════════════════════════

class TestVocabulario:

    def test_tags_del_ledger_son_tipos_validos(self):
        for tag in LEDGER_TAGS:
            assert tag in VALID_TYPES

    def test_emoji_unico_para_las_tres_direcciones(self):
        # La dirección la llevan la tag y el signo, no el emoji ni el color.
        assert {TAG_EMOJI[t] for t in LEDGER_TAGS} == {"💶"}


class TestEscrituraRelectura:

    def test_movimiento_escrito_se_relee(self, ledger_env):
        tags, body, _ = prepare_movement(EXPENSE_TAG, "218,40", "viaje", "Iberia")
        rc = add_entry("testproj", "Vuelo Madrid–Ginebra", EXPENSE_TAG, None,
                       "2026-07-14", project_dir=ledger_env,
                       continuations=body, extra_tags=tags)
        assert rc == 0

        movs, problems = read_movements(ledger_env)
        assert problems == []
        assert len(movs) == 1
        mov = movs[0]
        assert mov.concept == "Vuelo Madrid–Ginebra"
        assert mov.amount == Decimal("-218.40")
        assert mov.partida == "viaje"
        assert mov.payee == "Iberia"

    def test_saldo_tras_varios_movimientos(self, ledger_env):
        for tag, importe, partida in [(INCOME_TAG, "4.000,00", "financiacion"),
                                      (EXPENSE_TAG, "218,40", "viaje"),
                                      (EXPENSE_TAG, "1.000", "fungible")]:
            tags, body, _ = prepare_movement(tag, importe, partida)
            add_entry("testproj", f"Mov {partida}", tag, None, "2026-07-14",
                      project_dir=ledger_env, continuations=body, extra_tags=tags)
        movs, problems = read_movements(ledger_env)
        assert problems == []
        assert balance(movs) == Decimal("2781.60")

    def test_entrada_normal_sigue_sin_cuerpo(self, ledger_env):
        add_entry("testproj", "Nota suelta", "apunte", None, "2026-07-14",
                  project_dir=ledger_env)
        text = (ledger_env / "logbook.md").read_text()
        assert "2026-07-14 📝 Nota suelta #apunte" in text
        movs, _ = read_movements(ledger_env)
        assert movs == []

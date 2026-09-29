"""ledger.py — libro de caja por proyecto (capa de datos).

Un movimiento de dinero **es una entrada de logbook** con tag `#gasto`,
`#ingreso` o `#arrastre`. No hay fichero-verdad nuevo: `ledger.md` es un
derivado 100 % regenerable (F3) y nadie lo edita a mano.

Anatomía de un movimiento en `logbook.md`:

    2026-07-14 💶 [Vuelo Madrid–Ginebra](cloud/logs/2026-07-14_factura.pdf) #gasto
      🏷️ viaje · 👤 Iberia · 💶 -218,40

- **cabecera**: fecha del movimiento, emoji único 💶, concepto (con el enlace al
  justificante si lo hay, que `add_entry_with_ref` ya renderiza) y **una sola
  tag**, la de dirección — como cualquier otra entrada de logbook.
- **cuerpo**: una línea de tokens `emoji valor` unidos por `·`, misma gramática
  que la línea temporal de las citas en `agenda.md` (`▶️ … · ⏰ … · 🔔 …`).

El **signo lo deriva la tag**, nunca el usuario: `#gasto` es negativo e
`#ingreso` positivo. `#arrastre` es la excepción (signo libre) porque consolida
un neto que puede ir en cualquier dirección; la escribe solo `orbit archive`.

**Compromisos** (ADR-053): la hoja de pedido compromete crédito y la factura o
la liquidación de dietas lo gasta. Tres tags más, que no mueven caja:

- `#pedido` compromete (negativo como un gasto) y lleva id: `🆔 P03`. Es el
  número de **autorización** de la USC (`🆔 CM26XXXX0001`) o, mientras no se
  conoce, uno provisional (`P03`) que `ledger --reconcile` sustituye.
- `#gasto` puede llevar su propio id, el **número de factura** (`🆔 F-4471`),
  y con `🔗 P03` cierra ese pedido (libera todo lo comprometido e imputa el
  importe real); con `🔗 P03 parcial` gasta sin cerrarlo.
- `#anulacion` con `🔗 P03` cierra el pedido sin gasto.
- `#conciliacion` anota el saldo oficial de la USC en una fecha (control).

Las entradas nunca se editan: el estado de cada operación (abierto / cerrado
/ anulado) lo reconstruye :func:`build_operations` leyendo la cadena.

**Moneda**: todo se calcula en la del workspace (`💶`, EUR). Si el documento
vino en otra, se anota aparte y solo como información: `💱 1.150,00 CHF`. En un
`#pedido` el `💶` es una estimación; en un `#gasto`, lo que cargó la USC.
Nunca se convierte: el tipo de cambio se deduce de los dos importes.

Este módulo no escribe nada: serializa/parsea importes y cuerpo, y extrae los
movimientos del logbook. El generador de `ledger.md` y el verbo `orbit ledger`
llegan en F3.
"""

import json
import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import List, Optional, Tuple

# ── Vocabulario ──────────────────────────────────────────────────────────────

EXPENSE_TAG = "gasto"
INCOME_TAG  = "ingreso"
CARRY_TAG   = "arrastre"
ORDER_TAG   = "pedido"
CANCEL_TAG  = "anulacion"
RECON_TAG   = "conciliacion"

#: Tags que mueven caja: el saldo es la suma de sus importes.
CASH_TAGS = (EXPENSE_TAG, INCOME_TAG, CARRY_TAG)

#: Tags que convierten una entrada de logbook en un movimiento del ledger.
LEDGER_TAGS = CASH_TAGS + (ORDER_TAG, CANCEL_TAG, RECON_TAG)

#: Tags que puede teclear el usuario (`#arrastre` la escribe solo `archive`).
USER_TAGS = (EXPENSE_TAG, INCOME_TAG, ORDER_TAG, CANCEL_TAG, RECON_TAG)

#: Emoji único para las tres direcciones: la línea del diario queda neutra y la
#: dirección la llevan la tag y el signo, nunca el color ni la forma.
LEDGER_EMOJI = "💶"

PARTIDA_EMOJI = "🏷️"
PAYEE_EMOJI   = "👤"
AMOUNT_EMOJI  = "💶"
ID_EMOJI      = "🆔"      # id de operación, en el #pedido
REF_EMOJI     = "🔗"      # referencia a un pedido, en #gasto / #anulacion
ORIG_EMOJI    = "💱"      # importe y moneda originales (informativo)
ATTACH_EMOJI  = "📎"      # segundo fichero de una #conciliacion (excel de obrigas)

#: Tags que admiten importe en otra moneda.
_ORIG_TAGS = (EXPENSE_TAG, INCOME_TAG, ORDER_TAG)

#: Palabra que, tras la referencia, marca una factura parcial (no cierra).
PARTIAL_WORD = "parcial"

#: Orden canónico del cuerpo: partida · beneficiario · importe.
_BODY_SEP = " · "

DEFAULT_CURRENCY = "EUR"
_CURRENCY_SYMBOL = {"EUR": "€", "USD": "$", "GBP": "£", "CHF": "CHF"}

_CENTS = Decimal("0.01")


def sign_for(tag: str) -> int:
    """Multiplicador de signo de una tag de dirección.

    `#arrastre` devuelve 0 = signo libre (lo fija el neto que consolida).
    """
    return {EXPENSE_TAG: -1, INCOME_TAG: 1, ORDER_TAG: -1}.get(tag, 0)


def currency_symbol(workspace_root: Optional[Path] = None) -> str:
    """Símbolo de la moneda del workspace (`orbit.json` → `ledger.currency`).

    Moneda única por workspace: sin multi-moneda. Config ilegible o moneda
    desconocida → se cae a EUR en silencio, como el resto de secciones.
    """
    if workspace_root is None:
        from core.config import ORBIT_HOME
        workspace_root = ORBIT_HOME
    code = DEFAULT_CURRENCY
    path = workspace_root / "orbit.json"
    if path.exists():
        try:
            section = json.loads(path.read_text()).get("ledger")
            if isinstance(section, dict):
                code = str(section.get("currency", DEFAULT_CURRENCY))
        except (json.JSONDecodeError, OSError):
            pass
    return _CURRENCY_SYMBOL.get(code.upper(), code)


# ── Importes ─────────────────────────────────────────────────────────────────
#
# Todo en Decimal, nunca float: 0.1 + 0.2 != 0.3 y un saldo no admite eso.

_MINUS_CHARS = "-−‒–"   # ASCII, minus matemático, guiones
#: Solo se limpia en los extremos: un simbolo en medio ("12EUR34") es un
#: error de tecleo, y tragarselo como 1234 desviaria el importe 100x.
_CURRENCY_CHARS = " \t\xa0€$£"


def parse_amount(raw: str, allow_sign: bool = False) -> Decimal:
    """Parsea un importe escrito por una persona. Devuelve `Decimal` con 2 decimales.

    Acepta convención española y anglosajona sin ambigüedad:

    - `218,40` → 218.40      (coma decimal)
    - `4.000,00` → 4000.00   (punto de millares + coma decimal)
    - `218.40` → 218.40      (punto decimal: 1-2 dígitos detrás, un solo punto)
    - `4.000` → 4000.00      (punto de millares: 3 dígitos detrás)
    - `1.234.567` → 1234567.00

    Lanza `ValueError` con mensaje para el usuario si no cuadra. Es estricto a
    propósito: más de 2 decimales se rechaza en vez de redondear en silencio, y
    el signo se rechaza salvo `allow_sign` porque lo pone la tag.
    """
    text = (raw or "").strip(_CURRENCY_CHARS)
    if not text:
        raise ValueError("el importe está vacío")

    negative = False
    if text[0] in _MINUS_CHARS or text[0] == "+":
        if not allow_sign:
            raise ValueError(
                "el importe va sin signo: lo pone la tag "
                f"(#{EXPENSE_TAG} resta, #{INCOME_TAG} suma)"
            )
        negative = text[0] in _MINUS_CHARS
        text = text[1:]

    if not text or not re.fullmatch(r"[\d.,]+", text):
        raise ValueError(f"'{raw.strip()}' no es un importe válido")

    if "," in text:
        if text.count(",") > 1:
            raise ValueError(f"'{raw.strip()}' tiene más de una coma decimal")
        text = text.replace(".", "").replace(",", ".")
    elif "." in text:
        head, _, tail = text.rpartition(".")
        # Un solo punto con 1-2 dígitos detrás = decimal; si no, millares.
        if head.count(".") == 0 and 1 <= len(tail) <= 2:
            text = f"{head}.{tail}"
        else:
            text = text.replace(".", "")

    if "." in text and len(text.split(".")[1]) > 2:
        raise ValueError(
            f"'{raw.strip()}' tiene más de 2 decimales (no redondeo por ti)"
        )

    try:
        value = Decimal(text).quantize(_CENTS)
    except (InvalidOperation, ArithmeticError):
        raise ValueError(f"'{raw.strip()}' no es un importe válido")

    return -value if negative else value


def format_amount(value: Decimal, plus: bool = False) -> str:
    """Serializa un importe en convención española: `-1.234,56` / `+4.000,00`.

    `plus` fuerza el `+` explícito (útil en la tabla derivada, donde la columna
    de importe debe distinguir dirección sin depender del color).
    """
    value = Decimal(value).quantize(_CENTS)
    sign = "-" if value < 0 else ("+" if plus and value > 0 else "")
    entera, _, dec = abs(value).__format__("f").partition(".")
    dec = (dec + "00")[:2]
    grupos = []
    while len(entera) > 3:
        grupos.insert(0, entera[-3:])
        entera = entera[:-3]
    grupos.insert(0, entera)
    return f"{sign}{'.'.join(grupos)},{dec}"


def signed_amount(tag: str, magnitude: Decimal) -> Decimal:
    """Aplica el signo de la tag a un importe sin signo tecleado por el usuario.

    `#arrastre` no pasa por aquí: su signo es el del neto que consolida.
    """
    factor = sign_for(tag)
    if factor == 0:
        raise ValueError(f"#{tag} no deriva signo de la tag")
    return (abs(Decimal(magnitude)) * factor).quantize(_CENTS)


# ── Cuerpo del movimiento ────────────────────────────────────────────────────

def build_body(amount: Optional[Decimal], partida: Optional[str] = None,
               payee: Optional[str] = None, *, orig: Optional[tuple] = None,
               op_id: Optional[str] = None, ref: Optional[str] = None,
               partial: bool = False) -> List[str]:
    """Cuerpo de un movimiento: **una línea** de tokens `emoji valor` unidos por `·`.

        🏷️ viaje · 👤 Iberia · 💶 -218,40

    Misma gramática que la línea temporal de las citas en `agenda.md`
    (`▶️ … · ⏰ … · 🔔 …`): cada dato lleva su emoji, así que el orden es legible
    pero no significativo y los tokens ausentes simplemente no aparecen.

    El justificante no va aquí: viaja en el enlace de la cabecera, que
    `add_entry_with_ref` ya renderiza como `[concepto](cloud/logs/…)`.
    """
    tokens = []
    if partida and partida.strip():
        tokens.append(f"{PARTIDA_EMOJI} {partida.strip()}")
    if payee and payee.strip():
        tokens.append(f"{PAYEE_EMOJI} {payee.strip()}")
    if amount is not None:
        tokens.append(f"{AMOUNT_EMOJI} {format_amount(amount)}")
    if orig:
        tokens.append(f"{ORIG_EMOJI} {format_orig(*orig)}")
    if op_id:
        tokens.append(f"{ID_EMOJI} {op_id}")
    if ref:
        tokens.append(f"{REF_EMOJI} {ref}" + (f" {PARTIAL_WORD}" if partial else ""))
    return [_BODY_SEP.join(tokens)]


# ── Moneda original ──────────────────────────────────────────────────────────

_CODE_RE = re.compile(r"^[A-Za-z]{3}$")


def parse_orig(raw: str) -> tuple:
    """`1.150,00 CHF` (o `CHF 1150`) → `(Decimal('1150.00'), 'CHF')`.

    El código es ISO 4217 (tres letras). El importe va sin signo: el signo lo
    lleva el `💶`, que es el que cuenta.
    """
    parts = (raw or "").split()
    if len(parts) != 2:
        raise ValueError(f"'{(raw or '').strip()}': escribe importe y moneda, "
                         "p. ej. 1.150,00 CHF")
    a, b = parts
    if _CODE_RE.match(b):
        amount, code = a, b
    elif _CODE_RE.match(a):
        code, amount = a, b
    else:
        raise ValueError(f"'{raw.strip()}': la moneda va en código de tres "
                         "letras (CHF, USD, GBP, JPY…)")
    value = abs(parse_amount(amount, allow_sign=True))
    return value, code.upper()


def format_orig(value: Decimal, code: str) -> str:
    return f"{format_amount(abs(value))} {code}"


def prepare_movement(tag: str, amount_raw: Optional[str],
                     partida: Optional[str],
                     payee: Optional[str] = None, *,
                     op_id: Optional[str] = None,
                     ref: Optional[str] = None, partial: bool = False,
                     orig_raw: Optional[str] = None,
                     ) -> Tuple[List[str], Decimal]:
    """Valida un movimiento tecleado y devuelve `(cuerpo, importe)`.

    Lanza `ValueError` con un mensaje dirigido al usuario. Es la puerta única
    de escritura desde la CLI: exige partida e importe, y rechaza el signo
    porque lo pone la tag. Que el id no esté repetido y que el `🔗` apunte a un
    pedido abierto lo comprueba :func:`check_links`, que necesita el logbook.

    - `#pedido` exige `op_id` (nº de autorización o provisional); en `#gasto`
      es opcional (nº de factura); `#anulacion` exige `ref` y no lleva importe;
      `#conciliacion` admite signo (es un saldo, no un movimiento).
    - `partial` solo en `#gasto` con `ref`; `orig_raw` (`1.150,00 CHF`) solo
      en ingreso, gasto y pedido.
    """
    if tag == CARRY_TAG:
        raise ValueError(
            f"#{CARRY_TAG} lo escribe solo `orbit archive`; usa "
            f"--entry {EXPENSE_TAG}, {INCOME_TAG}, {ORDER_TAG}…"
        )
    if tag not in USER_TAGS:
        raise ValueError(f"#{tag} no es una tag del ledger")

    partida = (partida or "").strip().lstrip("#").strip()
    if not partida:
        raise ValueError(
            "un movimiento necesita partida: --tag <partida> "
            "(p. ej. viaje, fungible, inventariable)"
        )
    if re.search(r"\s|#", partida):
        raise ValueError(f"la partida '{partida}' no puede llevar espacios ni '#'")

    if tag == ORDER_TAG and not op_id:
        raise ValueError(f"un #{ORDER_TAG} necesita id: --id P01")
    if op_id and tag not in (ORDER_TAG, EXPENSE_TAG):
        raise ValueError(f"--id solo va en #{ORDER_TAG} (autorización) o "
                         f"#{EXPENSE_TAG} (factura)")
    if op_id and re.search(r"\s|#|·", op_id):
        raise ValueError(f"el id '{op_id}' no puede llevar espacios, '#' ni '·'")
    if tag == CANCEL_TAG and not ref:
        raise ValueError(f"una #{CANCEL_TAG} necesita el pedido: --pedido P01")
    if ref and tag not in (EXPENSE_TAG, CANCEL_TAG):
        raise ValueError(f"--pedido solo va en #{EXPENSE_TAG} o #{CANCEL_TAG}")
    if partial and not (tag == EXPENSE_TAG and ref):
        raise ValueError("--partial solo va en un #gasto con --pedido")
    orig = None
    if orig_raw:
        if tag not in _ORIG_TAGS:
            raise ValueError(f"--orig no va en #{tag}")
        orig = parse_orig(orig_raw)

    if tag == CANCEL_TAG:
        if amount_raw is not None and str(amount_raw).strip():
            raise ValueError(f"una #{CANCEL_TAG} no lleva importe: no mueve dinero")
        return build_body(None, partida, payee, ref=ref), Decimal("0.00")

    if amount_raw is None or not str(amount_raw).strip():
        raise ValueError("un movimiento necesita importe: --amount <cantidad>")

    if tag == RECON_TAG:
        amount = parse_amount(str(amount_raw), allow_sign=True)
    else:
        amount = signed_amount(tag, parse_amount(str(amount_raw)))
    return build_body(amount, partida, payee, orig=orig, op_id=op_id,
                      ref=ref, partial=partial), amount


# ── Lectura de la verdad ─────────────────────────────────────────────────────

_ENTRY_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})\s+(.*)$")
_TAG_RE   = re.compile(r"#([^\s#]+)")
_LINK_RE  = re.compile(r"^\[(?P<text>.+?)\]\((?P<url>[^)]*)\)\s*$")
_LEAD_RE  = re.compile(r"^[^\w\[(]+", re.UNICODE)


@dataclass(frozen=True)
class Movement:
    """Un movimiento del libro de caja, ya normalizado.

    `amount` viene **con signo aplicado**; `partida` es la primera tag que no
    sea de dirección (puede faltar en entradas escritas a mano).

    `raw` es la línea de cabecera tal cual (`fecha resto`): la usa `archive`
    para reconocer las entradas que no puede borrar.
    """
    date:    date
    tag:     str                    # ver LEDGER_TAGS
    concept: str
    amount:  Decimal
    partida: Optional[str] = None
    payee:   Optional[str] = None
    link:    Optional[str] = None
    op_id:   Optional[str] = None   # 🆔: autorización (#pedido) o factura (#gasto)
    ref:     Optional[str] = None   # 🔗 (#gasto / #anulacion)
    partial: bool = False           # 🔗 … parcial
    orig:    Optional[tuple] = None # 💱 (importe, código)
    attach:  Optional[str] = None   # 📎 (#conciliacion: excel de obrigas)
    raw:     str = ""

    @property
    def is_cash(self) -> bool:
        return self.tag in CASH_TAGS

    @property
    def is_cut(self) -> bool:
        """Marca de corte de `archive` sin arrastre (importe 0)."""
        return self.tag == CARRY_TAG and self.amount == 0


def _iter_entries(text: str):
    """Trocea un logbook en (fecha_str, resto_cabecera, [líneas de cuerpo])."""
    header = None
    body: List[str] = []
    for line in text.splitlines():
        m = _ENTRY_RE.match(line.strip()) if not line.startswith("  ") else None
        if m:
            if header:
                yield header[0], header[1], body
            header, body = (m.group(1), m.group(2)), []
        elif header and line.startswith("  ") and line.strip():
            body.append(line.strip())
    if header:
        yield header[0], header[1], body


def _parse_body(body: List[str]) -> dict:
    """Tokens `emoji valor` del cuerpo → `{emoji: valor}`.

    Cada línea se parte por `·`, así que esto lee tanto el formato actual (una
    línea con todos los tokens) como el primero que hubo (un token por línea).
    """
    fields = {}
    for line in body:
        for token in line.split(_BODY_SEP.strip()):
            token = token.strip()
            for emoji in (PARTIDA_EMOJI, PAYEE_EMOJI, AMOUNT_EMOJI,
                          ID_EMOJI, REF_EMOJI, ORIG_EMOJI, ATTACH_EMOJI):
                if token.startswith(emoji):
                    value = token[len(emoji):].strip()
                    if value:
                        fields.setdefault(emoji, value)
                    break
    return fields


def parse_entry(date_str: str, header: str,
                body: List[str]) -> Tuple[Optional[Movement], Optional[str]]:
    """Convierte una entrada de logbook en `Movement`.

    Devuelve `(movimiento, problema)`. Una entrada sin tag de dirección no es
    del ledger: devuelve `(None, None)` y no es un error. Una entrada del
    ledger mal formada devuelve `(None, "…")` para que el generador lo cante en
    vez de falsear el saldo en silencio.
    """
    tags = _TAG_RE.findall(header)
    tag = next((t for t in tags if t in LEDGER_TAGS), None)
    if tag is None:
        return None, None

    try:
        when = date.fromisoformat(date_str)
    except ValueError:
        return None, f"{date_str}: fecha ilegible"

    content = _TAG_RE.sub("", header)
    content = content.replace("[O]", "").strip()
    content = _LEAD_RE.sub("", content).strip()
    link = None
    m = _LINK_RE.match(content)
    if m:
        content, link = m.group("text").strip(), m.group("url").strip()

    fields = _parse_body(body)
    raw_amount = fields.get(AMOUNT_EMOJI)
    if raw_amount is None and tag == CANCEL_TAG:
        raw_amount = "0"                # anular no mueve dinero
    if raw_amount is None:
        return None, f"{date_str} {content}: movimiento sin importe ({AMOUNT_EMOJI})"
    try:
        amount = parse_amount(raw_amount, allow_sign=True)
    except ValueError as exc:
        return None, f"{date_str} {content}: {exc}"

    op_id = fields.get(ID_EMOJI) if tag in (ORDER_TAG, EXPENSE_TAG) else None
    ref, partial = None, False
    if tag in (EXPENSE_TAG, CANCEL_TAG) and fields.get(REF_EMOJI):
        words = fields[REF_EMOJI].split()
        ref = words[0]
        partial = tag == EXPENSE_TAG and PARTIAL_WORD in (w.lower() for w in words[1:])

    # La tag manda sobre el signo escrito: es la fuente semántica de la
    # dirección. Un signo contradictorio (edición a mano) se corrige y se canta.
    problem = None
    if tag == ORDER_TAG and not op_id:
        problem = f"{date_str} {content}: #{ORDER_TAG} sin id ({ID_EMOJI} P01…)"
    elif tag == CANCEL_TAG and not ref:
        problem = f"{date_str} {content}: #{CANCEL_TAG} sin {REF_EMOJI} al pedido"

    orig = None
    if fields.get(ORIG_EMOJI):
        try:
            orig = parse_orig(fields[ORIG_EMOJI])
        except ValueError as exc:
            problem = f"{date_str} {content}: {ORIG_EMOJI} {exc}"
    factor = sign_for(tag)
    if factor and amount and (amount > 0) != (factor > 0):
        problem = (f"{date_str} {content}: el signo contradice #{tag}, "
                   f"mando la tag")
        amount = -amount

    payee = fields.get(PAYEE_EMOJI)
    # La partida vive en el cuerpo; las entradas viejas la llevaban como
    # segunda tag de cabecera, así que se sigue aceptando de ahí.
    partida = fields.get(PARTIDA_EMOJI) or next(
        (x for x in tags if x not in LEDGER_TAGS), None)
    if partida:
        partida = partida.lstrip("#")

    return Movement(date=when, tag=tag, concept=content, amount=amount,
                    partida=partida, payee=payee or None, link=link,
                    op_id=op_id, ref=ref, partial=partial, orig=orig,
                    attach=fields.get(ATTACH_EMOJI) if tag == RECON_TAG else None,
                    raw=f"{date_str} {header}".strip()), problem


def scan_text(text: str) -> Tuple[List[Movement], List[str]]:
    """Extrae todos los movimientos de un logbook. Devuelve (movimientos, problemas)."""
    movements: List[Movement] = []
    problems:  List[str] = []
    for date_str, header, body in _iter_entries(text):
        mov, problem = parse_entry(date_str, header, body)
        if problem:
            problems.append(problem)
        if mov:
            movements.append(mov)
    return movements, problems


def read_movements(project_dir: Path) -> Tuple[List[Movement], List[str]]:
    """Movimientos del logbook de un proyecto, ordenados para el saldo corrido.

    Orden: fecha ascendente y, **en empate, `#arrastre` primero** — el saldo
    corrido depende de ello, porque un arrastre consolida todo lo anterior.
    """
    from core.log import find_logbook_file

    logbook = find_logbook_file(project_dir)
    if not logbook or not logbook.exists():
        return [], []
    movements, problems = scan_text(logbook.read_text())
    movements.sort(key=lambda m: (m.date, 0 if m.tag == CARRY_TAG else 1))
    return movements, problems


def balance(movements: List[Movement]) -> Decimal:
    """Saldo de caja = suma de los importes con signo de lo que mueve caja.

    Pedidos, anulaciones y conciliaciones no cuentan: comprometer no es gastar.
    """
    return sum((m.amount for m in movements if m.is_cash),
               Decimal("0")).quantize(_CENTS)


# ── Operaciones: pedido → factura(s) ────────────────────────────────────────

OPEN, CLOSED, CANCELLED, DIRECT = "abierto", "cerrado", "anulado", "directo"


@dataclass
class Operation:
    """Una fila de `ledger.md`: un pedido con sus facturas, o un gasto directo.

    `committed` y `spent` son magnitudes (≥ 0), no importes con signo.
    """
    date:      date
    concept:   str
    state:     str                          # abierto | cerrado | anulado | directo
    op_id:     Optional[str] = None
    payee:     Optional[str] = None
    link:      Optional[str] = None
    committed: Decimal = Decimal("0.00")
    spent:     Decimal = Decimal("0.00")
    entries:   List[Movement] = field(default_factory=list)

    @property
    def invoice_ids(self) -> List[str]:
        """Números de factura (🆔 de los #gasto) de la operación."""
        return [m.op_id for m in self.entries
                if m.tag == EXPENSE_TAG and m.op_id]

    @property
    def pending(self) -> Decimal:
        """Lo que sigue comprometido: nada si está cerrado o anulado.

        Con facturas parciales, lo comprometido menos lo ya facturado (nunca
        negativo: una parcial que se pasa no genera crédito).
        """
        if self.state != OPEN:
            return Decimal("0.00")
        return max(self.committed - self.spent, Decimal("0.00"))


def build_operations(movements: List[Movement]
                     ) -> Tuple[List[Operation], List[str]]:
    """Reconstruye las operaciones leyendo la cadena de entradas.

    Devuelve `(operaciones, problemas)`, ordenadas por fecha. Un `#gasto` con
    `🔗` a un pedido que no existe se lista como gasto directo **y** se canta:
    el dinero salió, así que el saldo tiene que contarlo igualmente.
    """
    ops: List[Operation] = []
    orders = {}
    problems: List[str] = []

    for m in movements:
        if m.tag != ORDER_TAG:
            continue
        op = Operation(date=m.date, concept=m.concept, state=OPEN,
                       op_id=m.op_id, payee=m.payee, link=m.link,
                       committed=abs(m.amount), entries=[m])
        ops.append(op)
        if not m.op_id:
            continue
        if m.op_id in orders:
            problems.append(f"{m.date.isoformat()} {m.concept}: id {m.op_id} "
                            f"repetido (ya lo usa «{orders[m.op_id].concept}»)")
            continue
        orders[m.op_id] = op

    for m in movements:
        if m.tag == EXPENSE_TAG:
            op = orders.get(m.ref) if m.ref else None
            if m.ref and op is None:
                problems.append(f"{m.date.isoformat()} {m.concept}: "
                                f"{REF_EMOJI} {m.ref} no es ningún pedido")
            if op is None:
                ops.append(Operation(date=m.date, concept=m.concept,
                                     state=DIRECT, payee=m.payee, link=m.link,
                                     spent=abs(m.amount), entries=[m]))
                continue
            if op.state != OPEN:
                problems.append(f"{m.date.isoformat()} {m.concept}: el pedido "
                                f"{op.op_id} ya estaba {op.state}")
            op.spent += abs(m.amount)
            op.entries.append(m)
            if not m.partial and op.state == OPEN:
                op.state = CLOSED
        elif m.tag == CANCEL_TAG and m.ref:
            op = orders.get(m.ref)
            if op is None:
                problems.append(f"{m.date.isoformat()} {m.concept}: "
                                f"{REF_EMOJI} {m.ref} no es ningún pedido")
                continue
            op.entries.append(m)
            if op.state == OPEN:
                op.state = CANCELLED
            else:
                problems.append(f"{m.date.isoformat()} {m.concept}: el pedido "
                                f"{op.op_id} ya estaba {op.state}")

    ops.sort(key=lambda o: o.date)
    return ops, problems


@dataclass(frozen=True)
class Summary:
    """Cabecera de `ledger.md`. Importes con signo (gastado y comprometido < 0).

    `available` = arrastre + dotación + gastado + comprometido, es decir
    dotación − gastado − comprometido cuando se leen como magnitudes.
    """
    carried:   Decimal
    income:    Decimal
    spent:     Decimal
    committed: Decimal
    last_recon: Optional[Movement] = None

    @property
    def cash(self) -> Decimal:
        return self.carried + self.income + self.spent

    @property
    def available(self) -> Decimal:
        return self.cash + self.committed


def summarize(movements: List[Movement],
              operations: Optional[List[Operation]] = None) -> Summary:
    if operations is None:
        operations, _ = build_operations(movements)

    def total(tag):
        return sum((m.amount for m in movements if m.tag == tag),
                   Decimal("0")).quantize(_CENTS)

    recons = [m for m in movements if m.tag == RECON_TAG]
    return Summary(
        carried=total(CARRY_TAG), income=total(INCOME_TAG),
        spent=total(EXPENSE_TAG),
        committed=-sum((o.pending for o in operations), Decimal("0")).quantize(_CENTS),
        last_recon=recons[-1] if recons else None,
    )


_ID_NUM_RE = re.compile(r"^([A-Za-z]*)(\d+)$")


def next_order_id(movements: List[Movement]) -> str:
    """Siguiente id de pedido: `P01`, `P02`… siguiendo el más alto que haya.

    Respeta el prefijo y el ancho del último id numérico (`P09` → `P10`,
    `OP003` → `OP004`); sin pedidos, `P01`.
    """
    best = None
    for m in movements:
        hit = _ID_NUM_RE.match(m.op_id or "") if m.tag == ORDER_TAG else None
        if hit and (best is None or int(hit.group(2)) > int(best.group(2))):
            best = hit
    if best is None:
        return "P01"
    prefix, digits = best.group(1), best.group(2)
    return f"{prefix}{int(digits) + 1:0{len(digits)}d}"


def open_orders(movements: List[Movement]) -> List[Operation]:
    return [op for op in build_operations(movements)[0] if op.state == OPEN]


def check_links(movements: List[Movement], tag: str,
                op_id: Optional[str] = None, ref: Optional[str] = None) -> None:
    """Coherencia con lo ya escrito. Lanza `ValueError` para el usuario.

    Al escribir se es estricto (id repetido, `🔗` a un pedido inexistente o ya
    cerrado); al leer, lo mismo solo se avisa, porque el dinero ya salió.
    """
    orders = {op.op_id: op for op in build_operations(movements)[0]
              if op.op_id and op.state != DIRECT}
    if tag == ORDER_TAG and op_id in orders:
        raise ValueError(f"el id {op_id} ya lo usa «{orders[op_id].concept}»; "
                         f"el siguiente libre es {next_order_id(movements)}")
    if tag == EXPENSE_TAG and op_id:
        twin = next((m for m in movements
                     if m.tag == EXPENSE_TAG and m.op_id == op_id), None)
        if twin:
            raise ValueError(f"la factura {op_id} ya está anotada: "
                             f"{twin.date.isoformat()} «{twin.concept}»")
    if ref:
        op = orders.get(ref)
        if op is None:
            known = ", ".join(o.op_id for o in open_orders(movements)) or "ninguno"
            raise ValueError(f"no hay ningún pedido {ref} (abiertos: {known})")
        if op.state != OPEN:
            raise ValueError(f"el pedido {ref} ya está {op.state}")


def _entry_spans(lines: List[str]):
    """(índice de cabecera, [índices de cuerpo], clave `fecha resto`)."""
    i = 0
    while i < len(lines):
        m = _ENTRY_RE.match(lines[i].strip()) if not lines[i].startswith("  ") else None
        if not m:
            i += 1
            continue
        body = []
        j = i + 1
        while j < len(lines) and lines[j].startswith("  ") and lines[j].strip():
            body.append(j)
            j += 1
        yield i, body, f"{m.group(1)} {m.group(2)}".strip()
        i = j


def _set_token(line: str, emoji: str, value: str) -> str:
    """Pone `emoji value` en una línea de tokens (sustituye o añade al final)."""
    indent = line[:len(line) - len(line.lstrip())]
    tokens = [t.strip() for t in line.strip().split(_BODY_SEP.strip())]
    for k, tok in enumerate(tokens):
        if tok.startswith(emoji):
            tokens[k] = f"{emoji} {value}"
            break
    else:
        tokens.append(f"{emoji} {value}")
    return indent + _BODY_SEP.join(t for t in tokens if t)


def rewrite_ids(project_dir: Path, raw: str, new_id: str) -> int:
    """Pone `🆔 new_id` en la entrada cuya cabecera es *raw* y, si era un
    pedido con id, cambia también los `🔗` que lo apuntaban.

    Es la única escritura del ledger que **edita** entradas ya escritas: la
    usa `ledger --reconcile` para pasar un id provisional al oficial, y solo
    tras confirmar. Deja undo. Devuelve cuántas entradas ha tocado.
    """
    from core.log import find_logbook_file
    from core.undo import save_snapshot

    logbook = find_logbook_file(project_dir)
    lines = logbook.read_text().splitlines()
    movements, _ = read_movements(project_dir)
    target = next((m for m in movements if m.raw == raw), None)
    if target is None:
        raise ValueError(f"no encuentro la entrada «{raw}»")
    old_id = target.op_id if target.tag == ORDER_TAG else None

    touched = 0
    for head, body, key in _entry_spans(lines):
        if key == raw:
            idx = next((b for b in body if AMOUNT_EMOJI in lines[b]
                        or ID_EMOJI in lines[b]), body[-1] if body else None)
            if idx is None:
                lines.insert(head + 1, f"  {ID_EMOJI} {new_id}")
            else:
                lines[idx] = _set_token(lines[idx], ID_EMOJI, new_id)
            touched += 1
        elif old_id:
            ref_re = re.compile(rf"({REF_EMOJI}\s+){re.escape(old_id)}(?=\s|·|$)")
            for b in body:
                lines[b], n = ref_re.subn(rf"\g<1>{new_id}", lines[b])
                touched += n
    save_snapshot(logbook)
    logbook.write_text("\n".join(lines) + "\n")
    return touched


def record_reconciliation(project_dir: Path, when: date, available: Decimal,
                          pdf_rel: str, xls_rel: Optional[str] = None) -> bool:
    """Anota la `#conciliacion` de una ejecución de la USC (`ledger --check`
    con ficheros). Devuelve False si ya había una de esa fecha: volver a
    lanzar el check con los mismos ficheros no ensucia el logbook.

    El PDF va en la cabecera (justificante) y el excel de obrigas, si lo hay,
    como `📎` en el cuerpo: son los ficheros de los que `ledger.md` saca la
    columna USC.
    """
    from core.log import add_entry

    movements, _ = read_movements(project_dir)
    if any(m.tag == RECON_TAG and m.date == when for m in movements):
        return False
    body = build_body(available, project_partida(project_dir))
    if xls_rel:
        body = [body[0] + f"{_BODY_SEP}{ATTACH_EMOJI} {xls_rel}"]
    rc = add_entry(project_dir.name, f"Ejecución USC {when.isoformat()}",
                   RECON_TAG, pdf_rel, when.isoformat(),
                   project_dir=project_dir, continuations=body)
    return rc == 0


def protected_headers(movements: List[Movement], cutoff: date) -> set:
    """Cabeceras que `archive` no puede borrar aunque sean anteriores al corte.

    Una operación con pedido solo se archiva **entera** y **terminada**: si
    sigue abierta, o alguna de sus entradas es posterior al corte, se quedan
    todas. Borrar el pedido dejaría la factura posterior con un `🔗` colgante
    y el comprometido desaparecería del saldo; borrar una parcial de un pedido
    abierto haría que lo pendiente volviera a contar entero.
    """
    keep = set()
    for op in build_operations(movements)[0]:
        if op.state == DIRECT:
            continue
        if op.state == OPEN or any(m.date >= cutoff for m in op.entries):
            keep.update(m.raw for m in op.entries)
    return keep


def project_partida(project_dir: Path) -> Optional[str]:
    """La partida del proyecto, deducida de sus movimientos.

    Hoy **un proyecto tiene una sola partida**, así que no hay ambigüedad: la
    primera que aparezca es la del proyecto. Si algún día hay varias, esta
    función es el único punto que hay que abrir.
    """
    movements, _ = read_movements(project_dir)
    return next((m.partida for m in movements if m.partida), None)


def resolve_partida(project_dir: Path, requested: Optional[str],
                    confirm=None) -> str:
    """Partida a usar en un movimiento nuevo. Lanza `ValueError` si no la hay.

    - sin `--tag` → se hereda la del proyecto (no se teclea dos veces lo mismo)
    - sin `--tag` y sin movimientos previos → hay que declararla una vez
    - con `--tag` distinta de la del proyecto → casi siempre es un error de
      tecleo, así que se pide confirmación; sin TTY se aborta (el saldo no es
      sitio para dar por buena una duda)
    """
    known = project_partida(project_dir)
    wanted = (requested or "").strip().lstrip("#").strip()

    if not wanted:
        if known:
            return known
        raise ValueError(
            "este proyecto aún no tiene partida: declárala una vez con "
            "--tag <partida> (p. ej. viaje, fungible, inventariable)"
        )

    if known and wanted != known:
        prompt = (f"⚠️  El proyecto usa la partida #{known}; has escrito "
                  f"#{wanted}. ¿Usar #{wanted}? [s/N]: ")
        answer = confirm(prompt) if confirm else _ask_tty(prompt)
        if not answer:
            raise ValueError(
                f"movimiento cancelado; la partida del proyecto es #{known}"
            )
    return wanted


class Cancelled(Exception):
    """El usuario abortó el interrogador (Ctrl-C / EOF)."""


def _ask_line(prompt: str, default: Optional[str] = None) -> Optional[str]:
    """Pregunta mostrando el default; Enter lo acepta. EOF/Ctrl-C → `Cancelled`."""
    suffix = f" [{default}]" if default else ""
    try:
        raw = input(f"  {prompt}{suffix}: ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        raise Cancelled
    return raw or default


def _ask_required(prompt: str, validate=None, tries: int = 3) -> str:
    """Como `_ask_line` pero el campo no puede quedar vacío.

    Una respuesta inválida se vuelve a pedir mostrando el porqué, en vez de
    asumir un valor: en un movimiento de dinero adivinar sale caro.
    """
    for _ in range(tries):
        raw = _ask_line(prompt)
        if not raw:
            print("     (obligatorio)")
            continue
        if validate is None:
            return raw
        try:
            validate(raw)
            return raw
        except ValueError as exc:
            print(f"     ⚠️  {exc}")
    raise Cancelled


def interrogate_movement(project_dir: Path, tag: str, *,
                         concept: Optional[str], amount: Optional[str],
                         payee: Optional[str], partida: Optional[str],
                         fecha: Optional[str], ref: Optional[str]):
    """Rellena por teclado los huecos de un movimiento. Solo pregunta lo que falta.

    Orden: tipo (partida) → item → beneficiario → importe → fecha → enlace.
    La partida solo se pregunta si el proyecto aún no tiene ninguna: un
    proyecto tiene una sola y los demás movimientos la heredan.

    Devuelve la tupla `(concept, amount, payee, partida, fecha, ref)`.
    Lanza `Cancelled` si el usuario aborta.
    """
    print(f"━━━ log · {tag} (Enter = saltar lo opcional) ━━━")

    if not partida and not project_partida(project_dir):
        partida = _ask_required(
            f"{PARTIDA_EMOJI}  Tipo (partida)",
            lambda v: prepare_movement(EXPENSE_TAG, "0", v),
        )
    if not concept:
        concept = _ask_required("📝 Item")
    if not payee and tag not in (CANCEL_TAG, RECON_TAG):
        payee = _ask_line("👤 Beneficiario") or None
    if not amount and tag == RECON_TAG:
        amount = _ask_required(
            f"{AMOUNT_EMOJI} Saldo oficial",
            lambda v: parse_amount(v, allow_sign=True),
        )
    elif not amount and tag != CANCEL_TAG:
        label = ("Importe estimado en EUR (sin signo)" if tag == ORDER_TAG
                 else "Importe (sin signo)")
        amount = _ask_required(
            f"{AMOUNT_EMOJI} {label}",
            lambda v: parse_amount(v),
        )
    if not fecha:
        fecha = _ask_line("📅 Fecha", date.today().isoformat())
    if not ref:
        ref = _ask_line("📎 Enlace (ruta o URL)") or None

    return concept, amount, payee, partida, fecha, ref


def interrogate_commitment(movements: List[Movement], tag: str, *,
                           op_id: Optional[str], ref: Optional[str],
                           partial: bool, orig: Optional[str]):
    """Segunda mitad del interrogador: id, pedido que se factura y moneda.

    Solo pregunta lo que falta y lo que aplica a *tag*. Devuelve
    `(op_id, ref, partial, orig)`. Lanza `Cancelled` si el usuario aborta.
    """
    if tag == ORDER_TAG and not op_id:
        suggested = next_order_id(movements)
        for _ in range(3):
            op_id = _ask_line(f"{ID_EMOJI} Nº de autorización USC "
                              f"(Enter = provisional)", suggested)
            try:
                check_links(movements, tag, op_id=op_id)
                break
            except ValueError as exc:
                print(f"     ⚠️  {exc}")
        else:
            raise Cancelled

    if tag in (EXPENSE_TAG, CANCEL_TAG) and not ref:
        opens = open_orders(movements)
        if opens or tag == CANCEL_TAG:
            print("     Pedidos abiertos:" if opens else "     (no hay pedidos abiertos)")
            for op in opens:
                print(f"       {op.op_id:<6} {op.date.isoformat()}  "
                      f"{format_amount(op.pending):>10}  {op.concept}")

        def _valid(v):
            check_links(movements, tag, ref=v)
        if tag == CANCEL_TAG:
            ref = _ask_required(f"{REF_EMOJI} Pedido que se anula", _valid)
        elif opens:
            for _ in range(3):
                ref = _ask_line(f"{REF_EMOJI} Pedido que factura "
                                "(Enter = gasto sin pedido)") or None
                if ref is None:
                    break
                try:
                    _valid(ref)
                    break
                except ValueError as exc:
                    print(f"     ⚠️  {exc}")
            else:
                raise Cancelled

    if tag == EXPENSE_TAG and not op_id:
        op_id = _ask_line(f"{ID_EMOJI} Nº de factura (Enter = sin número)") or None

    if tag == EXPENSE_TAG and ref and not partial:
        answer = _ask_line("   ¿Factura parcial (el pedido sigue abierto)? [s/N]")
        partial = (answer or "").lower() in ("s", "si", "sí", "y", "yes")

    if tag in _ORIG_TAGS and not orig:
        orig = _ask_line(f"{ORIG_EMOJI} Importe en moneda original "
                         "(p. ej. 1.150,00 CHF; Enter = EUR)") or None
        while orig:
            try:
                parse_orig(orig)
                break
            except ValueError as exc:
                print(f"     ⚠️  {exc}")
                orig = _ask_line(f"{ORIG_EMOJI} Importe en moneda original "
                                 "(Enter = EUR)") or None

    return op_id, ref, partial, orig


def _ask_tty(prompt: str) -> bool:
    """Confirmación por terminal. Sin TTY devuelve False (opción segura)."""
    import sys
    if not sys.stdin.isatty():
        return False
    try:
        return input(prompt).strip().lower() in ("s", "si", "sí", "y", "yes")
    except (EOFError, KeyboardInterrupt):
        print()
        return False


def has_movements(project_dir: Path) -> bool:
    """¿El proyecto tiene ledger? Determina la creación perezosa de `ledger.md`."""
    movements, _ = read_movements(project_dir)
    return bool(movements)

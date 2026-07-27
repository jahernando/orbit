"""ledger.py — libro de caja por proyecto (capa de datos).

Un movimiento de dinero **es una entrada de logbook** con tag `#gasto`,
`#ingreso` o `#arrastre`. No hay fichero-verdad nuevo: `ledger.md` es un
derivado 100 % regenerable (F3) y nadie lo edita a mano.

Anatomía de un movimiento en `logbook.md`:

    2026-07-14 💶 [Vuelo Madrid–Ginebra](cloud/logs/2026-07-14_factura.pdf) #gasto #viaje
      💶 -218,40
      👤 Iberia

- **cabecera**: fecha del movimiento, emoji único 💶, concepto (con el enlace al
  justificante si lo hay, que `add_entry_with_ref` ya renderiza), tag de
  dirección y tag de partida.
- **cuerpo**: importe y beneficiario.

El **signo lo deriva la tag**, nunca el usuario: `#gasto` es negativo e
`#ingreso` positivo. `#arrastre` es la excepción (signo libre) porque consolida
un neto que puede ir en cualquier dirección; la escribe solo `orbit archive`.

Este módulo no escribe nada: serializa/parsea importes y cuerpo, y extrae los
movimientos del logbook. El generador de `ledger.md` y el verbo `orbit ledger`
llegan en F3.
"""

import json
import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import List, Optional, Tuple

# ── Vocabulario ──────────────────────────────────────────────────────────────

EXPENSE_TAG = "gasto"
INCOME_TAG  = "ingreso"
CARRY_TAG   = "arrastre"

#: Tags que convierten una entrada de logbook en un movimiento del ledger.
LEDGER_TAGS = (EXPENSE_TAG, INCOME_TAG, CARRY_TAG)

#: Tags que puede teclear el usuario (`#arrastre` la escribe solo `archive`).
USER_TAGS = (EXPENSE_TAG, INCOME_TAG)

#: Emoji único para las tres direcciones: la línea del diario queda neutra y la
#: dirección la llevan la tag y el signo, nunca el color ni la forma.
LEDGER_EMOJI = "💶"

AMOUNT_EMOJI = "💶"
PAYEE_EMOJI  = "👤"

DEFAULT_CURRENCY = "EUR"
_CURRENCY_SYMBOL = {"EUR": "€", "USD": "$", "GBP": "£", "CHF": "CHF"}

_CENTS = Decimal("0.01")


def sign_for(tag: str) -> int:
    """Multiplicador de signo de una tag de dirección.

    `#arrastre` devuelve 0 = signo libre (lo fija el neto que consolida).
    """
    return {EXPENSE_TAG: -1, INCOME_TAG: 1, CARRY_TAG: 0}.get(tag, 0)


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

def build_body(amount: Decimal, payee: Optional[str] = None) -> List[str]:
    """Líneas de cuerpo de un movimiento, listas para `format_entry(continuations=…)`.

    El justificante no va aquí: viaja en el enlace de la cabecera, que
    `add_entry_with_ref` ya renderiza como `[concepto](cloud/logs/…)`.
    """
    body = [f"{AMOUNT_EMOJI} {format_amount(amount)}"]
    if payee and payee.strip():
        body.append(f"{PAYEE_EMOJI} {payee.strip()}")
    return body


def prepare_movement(tag: str, amount_raw: Optional[str],
                     partida: Optional[str],
                     payee: Optional[str] = None
                     ) -> Tuple[List[str], List[str], Decimal]:
    """Valida un movimiento tecleado y devuelve `(extra_tags, cuerpo, importe)`.

    Lanza `ValueError` con un mensaje dirigido al usuario. Es la puerta única
    de escritura desde la CLI: exige partida e importe, y rechaza el signo
    porque lo pone la tag.
    """
    if tag == CARRY_TAG:
        raise ValueError(
            f"#{CARRY_TAG} lo escribe solo `orbit archive`; usa "
            f"--entry {EXPENSE_TAG} o --entry {INCOME_TAG}"
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

    if amount_raw is None or not str(amount_raw).strip():
        raise ValueError("un movimiento necesita importe: --amount <cantidad>")

    amount = signed_amount(tag, parse_amount(str(amount_raw)))
    return [partida], build_body(amount, payee), amount


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
    """
    date:    date
    tag:     str                    # gasto | ingreso | arrastre
    concept: str
    amount:  Decimal
    partida: Optional[str] = None
    payee:   Optional[str] = None
    link:    Optional[str] = None

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

    raw_amount = next((l[len(AMOUNT_EMOJI):] for l in body
                       if l.startswith(AMOUNT_EMOJI)), None)
    if raw_amount is None:
        return None, f"{date_str} {content}: movimiento sin importe ({AMOUNT_EMOJI})"
    try:
        amount = parse_amount(raw_amount, allow_sign=True)
    except ValueError as exc:
        return None, f"{date_str} {content}: {exc}"

    # La tag manda sobre el signo escrito: es la fuente semántica de la
    # dirección. Un signo contradictorio (edición a mano) se corrige y se canta.
    problem = None
    factor = sign_for(tag)
    if factor and amount and (amount > 0) != (factor > 0):
        problem = (f"{date_str} {content}: el signo contradice #{tag}, "
                   f"mando la tag")
        amount = -amount

    payee = next((l[len(PAYEE_EMOJI):].strip() for l in body
                  if l.startswith(PAYEE_EMOJI)), None)
    partida = next((t for t in tags if t not in LEDGER_TAGS), None)

    return Movement(date=when, tag=tag, concept=content, amount=amount,
                    partida=partida, payee=payee or None, link=link), problem


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
    """Saldo = suma de los importes con signo."""
    return sum((m.amount for m in movements), Decimal("0")).quantize(_CENTS)


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

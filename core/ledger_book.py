"""ledger_book.py — el libro de contabilidad del proyecto (ADR-054).

`ledger.md` es la **verdad**: una cabecera con la partida y el periodo de
validez, y los movimientos numerados por orden de anotación.

    # 💶 Ledger — ⚙️proyecto

    - 🏷️ Partida: 1234.AB12.64100
    - 📆 Validez: 2026-08-06 → 2029-08-05

    ## Movimientos

    - 💶 0006 [Vuelo Ginebra](./cloud/ledger-logs/2026-09-18_billete.pdf) #compromiso
      📅 2026-09-18 · 🗂️ viajes · 👤 Viajes Ejemplo, S.L. · 💶 -1.250,00 · 🆔 CM26XXXX0001
      ☑️ 2026-11-03 · 2026/000123
      📝 2026-10-05 modificado: 👤 Viajes Ejemplo → Viajes Ejemplo, S.L.

- **El número no se reutiliza, renumera ni borra.** Lo equivocado se anula
  (`🚫 fecha`) y deja de contar.
- **El signo lo pone la tag**, como en el resto del ledger (`core/ledger.py`,
  del que se reutilizan importes, operaciones y resumen).
- `🔗` apunta al **número** del compromiso que consume un gasto.
- `☑️ fecha · ID` = validado contra una fuente externa (la pone una
  herramienta de conciliación a través de `ledger edit N --confirm`).

El logbook solo recibe un **rastro** por movimiento (`💶 título · ledger N
#tipo`), sin enlace ni importe: nada que pueda divergir de la verdad.

Coexistencia (F1): si el proyecto tiene libro, manda él; si no, el ledger se
sigue leyendo del logbook (ADR-048/053) hasta la migración.
"""

import json
import re
from dataclasses import dataclass, field, replace
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import List, Optional, Tuple

from core.ledger import (
    AMOUNT_EMOJI, CLOSE_EMOJI, CONC_EMOJI, EXPENSE_TAG, ID_EMOJI, INCOME_TAG,
    LEDGER_EMOJI, NOTE_EMOJI, OPEN, ORDER_TAG, PARTIDA_EMOJI, PAYEE_EMOJI,
    REF_EMOJI, USER_LABELS, Movement, build_operations, format_amount,
    parse_amount, signed_amount,
)

BOOK_FILE   = "ledger.md"
LEDGER_LOGS = "ledger-logs"          # cloud/ledger-logs/: justificantes del libro

DATE_EMOJI   = "📅"
CAT_EMOJI    = "🗂️"
VALID_EMOJI  = "📆"
CANCEL_EMOJI = "🚫"

DEFAULT_CATEGORIES = ("viajes", "congresos", "personal", "fungible",
                      "inventariable")

_SEP = " · "
_VS  = "️"                       # selector de variante: se ignora al leer


def _bare(text: str) -> str:
    return text.replace(_VS, "")


_ENTRY_RE   = re.compile(r"^- " + LEDGER_EMOJI + r"\s+(\d{4})\s+(.*?)\s*$")
_PARTIDA_RE = re.compile(r"^- " + _bare(PARTIDA_EMOJI) + r"\s*Partida:\s*#?(\S+)")
_VALID_RE   = re.compile(r"^- " + _bare(VALID_EMOJI)
                         + r"\s*Validez:\s*(\d{4}-\d{2}-\d{2})\s*(?:→|->)\s*"
                           r"(\d{4}-\d{2}-\d{2})")
_TYPE_RE    = re.compile(r"\s#(" + "|".join(USER_LABELS) + r")\b")
_LINK_RE    = re.compile(r"^\[(?P<text>.+?)\]\((?P<url>[^)]*)\)$")
_NUM_RE     = re.compile(r"^\d{1,4}$")
_TRAIL_RE   = re.compile(r"·\s*ledger\s+(\d{4})\s+#(" + "|".join(USER_LABELS) + r")\b")


class BookError(ValueError):
    """Error para el usuario al escribir en el libro."""


# ── Modelo ───────────────────────────────────────────────────────────────────

@dataclass
class Entry:
    """Un movimiento del libro, tal como está escrito."""
    num:       str
    tag:       str                         # ingreso | compromiso | gasto
    title:     str
    date:      Optional[date] = None
    amount:    Optional[Decimal] = None    # con signo
    payee:     Optional[str] = None
    category:  Optional[str] = None
    link:      Optional[str] = None
    op_id:     Optional[str] = None        # 🆔 referencia del documento
    commit:    Optional[str] = None        # 🔗 nº del compromiso que consume
    closes:    bool = False                # 🔒
    confirmed: Optional[Tuple[str, str]] = None   # ☑️ (fecha, ID externo)
    cancelled: Optional[str] = None        # 🚫 fecha
    notes:     List[str] = field(default_factory=list)
    start:     int = 0                     # líneas [start, end) del fichero
    end:       int = 0

    @property
    def live(self) -> bool:
        return not self.cancelled

    def to_movement(self, partida: Optional[str]) -> Movement:
        return Movement(
            date=self.date, tag=self.tag, concept=self.title,
            amount=self.amount, partida=partida, payee=self.payee,
            link=self.link, op_id=self.op_id, ref=self.commit, label=self.tag,
            usc=self.confirmed[1] if self.confirmed else None,
            closes=self.closes, note=None, raw=f"ledger {self.num}",
            num=self.num, category=self.category,
            confirmed_on=self.confirmed[0] if self.confirmed else None)


@dataclass
class Book:
    path:       Path
    partida:    Optional[str]
    valid_from: Optional[date]
    valid_to:   Optional[date]
    entries:    List[Entry]
    problems:   List[str]
    lines:      List[str]

    def get(self, num: str) -> Optional[Entry]:
        num = normalize_num(num)
        return next((e for e in self.entries if e.num == num), None)

    def live(self) -> List[Entry]:
        return [e for e in self.entries if e.live and e.date and e.amount is not None]

    def movements(self) -> List[Movement]:
        """Movimientos vivos, en el orden del saldo corrido (fecha, nº)."""
        movs = [e.to_movement(self.partida) for e in self.live()]
        movs.sort(key=lambda m: (m.date, m.num))
        return movs

    def next_num(self) -> str:
        nums = [int(e.num) for e in self.entries]
        return f"{(max(nums) if nums else 0) + 1:04d}"

    def in_range(self, when: date) -> bool:
        if not (self.valid_from and self.valid_to):
            return True
        return self.valid_from <= when <= self.valid_to


def normalize_num(num) -> str:
    text = str(num).strip()
    if not _NUM_RE.match(text):
        raise BookError(f"'{num}' no es un número de entrada (p. ej. 0006)")
    return f"{int(text):04d}"


# ── Lectura ──────────────────────────────────────────────────────────────────

def book_path(project_dir: Path) -> Path:
    return project_dir / BOOK_FILE


def is_book(project_dir: Path) -> bool:
    """¿`ledger.md` es un libro (verdad) y no el derivado de ADR-048?"""
    path = book_path(project_dir)
    if not path.is_file():
        return False
    for line in path.read_text().splitlines():
        bare = _bare(line)
        if _VALID_RE.match(bare) or _PARTIDA_RE.match(bare) or _ENTRY_RE.match(line):
            return True
    return False


def _parse_header(rest: str) -> Tuple[Optional[str], str, Optional[str]]:
    """`[título](enlace) #tipo` → (tipo, título, enlace)."""
    m = _TYPE_RE.search(" " + rest)
    tag = m.group(1) if m else None
    content = _TYPE_RE.sub("", " " + rest).strip()
    link = None
    lm = _LINK_RE.match(content)
    if lm:
        content, link = lm.group("text").strip(), lm.group("url").strip()
    return tag, content, link


def _parse_entry(num: str, rest: str, body: List[str],
                 problems: List[str]) -> Entry:
    tag, title, link = _parse_header(rest)
    where = f"ledger {num}"
    if tag is None:
        problems.append(f"{where}: falta el tipo (#{' / #'.join(USER_LABELS)})")
        tag = EXPENSE_TAG
    e = Entry(num=num, tag=tag, title=title, link=link)
    for raw in body:
        line = _bare(raw.strip())
        if line.startswith(NOTE_EMOJI):
            e.notes.append(line[len(NOTE_EMOJI):].strip())
            continue
        if line.startswith(_bare(CONC_EMOJI)):
            parts = [p.strip() for p in line[len(_bare(CONC_EMOJI)):].split("·", 1)]
            if len(parts) == 2 and parts[1]:
                e.confirmed = (parts[0], parts[1])
            else:
                problems.append(f"{where}: {CONC_EMOJI} sin «fecha · ID»")
            continue
        if line.startswith(CANCEL_EMOJI):
            e.cancelled = line[len(CANCEL_EMOJI):].strip() or "?"
            continue
        for token in line.split("·"):
            token = token.strip()
            if token.startswith(CLOSE_EMOJI):
                e.closes = True
                continue
            for emoji in (DATE_EMOJI, _bare(CAT_EMOJI), PAYEE_EMOJI,
                          AMOUNT_EMOJI, ID_EMOJI, REF_EMOJI):
                if not token.startswith(emoji):
                    continue
                value = token[len(emoji):].strip()
                if not value:
                    break
                if emoji == DATE_EMOJI:
                    try:
                        e.date = date.fromisoformat(value)
                    except ValueError:
                        problems.append(f"{where}: fecha ilegible «{value}»")
                elif emoji == _bare(CAT_EMOJI):
                    e.category = value
                elif emoji == PAYEE_EMOJI:
                    e.payee = value
                elif emoji == AMOUNT_EMOJI:
                    try:
                        e.amount = parse_amount(value, allow_sign=True)
                    except ValueError as exc:
                        problems.append(f"{where}: {exc}")
                elif emoji == ID_EMOJI:
                    e.op_id = value
                elif emoji == REF_EMOJI:
                    try:
                        e.commit = normalize_num(value.split()[0])
                    except BookError:
                        problems.append(f"{where}: {REF_EMOJI} «{value}» no es un nº")
                break

    if e.date is None:
        problems.append(f"{where}: sin fecha ({DATE_EMOJI})")
    if e.amount is None:
        problems.append(f"{where}: sin importe ({AMOUNT_EMOJI})")
    elif e.amount and (e.amount > 0) != (tag == INCOME_TAG):
        problems.append(f"{where}: el signo contradice #{tag}, mando la tag")
        e.amount = -e.amount
    return e


def parse_book(text: str, path: Path) -> Book:
    lines = text.splitlines()
    partida = vfrom = vto = None
    entries: List[Entry] = []
    problems: List[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        bare = _bare(line)
        m = _PARTIDA_RE.match(bare)
        if m:
            partida = m.group(1)
        m = _VALID_RE.match(bare)
        if m:
            try:
                vfrom, vto = (date.fromisoformat(m.group(1)),
                              date.fromisoformat(m.group(2)))
            except ValueError:
                problems.append("cabecera: validez ilegible")
        m = _ENTRY_RE.match(line)
        if m:
            start, j, body = i, i + 1, []
            while j < len(lines) and lines[j].startswith((" ", "\t")) and lines[j].strip():
                body.append(lines[j])
                j += 1
            e = _parse_entry(m.group(1), m.group(2), body, problems)
            e.start, e.end = start, j
            entries.append(e)
            i = j
            continue
        i += 1
    return Book(path=path, partida=partida, valid_from=vfrom, valid_to=vto,
                entries=entries, problems=problems, lines=lines)


def read_book(project_dir: Path) -> Optional[Book]:
    """El libro del proyecto, o None si no tiene (o `ledger.md` es el derivado viejo)."""
    if not is_book(project_dir):
        return None
    path = book_path(project_dir)
    return parse_book(path.read_text(), path)


# ── Configuración ────────────────────────────────────────────────────────────

def categories(workspace_root: Optional[Path] = None) -> Tuple[str, ...]:
    """Lista cerrada de categorías: `orbit.json` → `ledger.categories`."""
    if workspace_root is None:
        from core.config import ORBIT_HOME
        workspace_root = ORBIT_HOME
    path = workspace_root / "orbit.json"
    if path.exists():
        try:
            section = json.loads(path.read_text()).get("ledger")
            cats = section.get("categories") if isinstance(section, dict) else None
            if isinstance(cats, list) and cats:
                return tuple(str(c).strip() for c in cats if str(c).strip())
        except (json.JSONDecodeError, OSError):
            pass
    return DEFAULT_CATEGORIES


# ── Escritura ────────────────────────────────────────────────────────────────

def render_entry(e: Entry) -> List[str]:
    content = f"[{e.title}]({e.link})" if e.link else e.title
    head = f"- {LEDGER_EMOJI} {e.num} {content} #{e.tag}"
    tokens = [f"{DATE_EMOJI} {e.date.isoformat()}" if e.date else None,
              f"{CAT_EMOJI} {e.category}" if e.category else None,
              f"{PAYEE_EMOJI} {e.payee}" if e.payee else None,
              f"{AMOUNT_EMOJI} {format_amount(e.amount)}" if e.amount is not None else None,
              f"{ID_EMOJI} {e.op_id}" if e.op_id else None,
              f"{REF_EMOJI} {e.commit}" if e.commit else None,
              CLOSE_EMOJI if e.closes else None]
    out = [head, "  " + _SEP.join(t for t in tokens if t)]
    if e.confirmed:
        out.append(f"  {CONC_EMOJI} {e.confirmed[0]}{_SEP}{e.confirmed[1]}")
    if e.cancelled:
        out.append(f"  {CANCEL_EMOJI} {e.cancelled}")
    out += [f"  {NOTE_EMOJI} {n}" for n in e.notes]
    return out


def _write(book: Book, lines: List[str]) -> None:
    from core.undo import save_snapshot
    save_snapshot(book.path)
    book.path.write_text("\n".join(lines).rstrip("\n") + "\n")


def _replace_entry(book: Book, e: Entry) -> None:
    lines = list(book.lines)
    lines[e.start:e.end] = render_entry(e)
    _write(book, lines)


def _append_entry(book: Book, e: Entry) -> None:
    lines = list(book.lines)
    while lines and not lines[-1].strip():
        lines.pop()
    lines += [""] + render_entry(e)
    _write(book, lines)


BOOK_TEMPLATE = """# 💶 Ledger — {name}

<!-- Libro de contabilidad (la verdad). Anotar: orbit ledger {name} add ·
     corregir: orbit ledger {name} edit N · anular: orbit ledger {name} cancel N.
     Los números no se reutilizan ni se borran. -->

- {partida_emoji} Partida: {partida}
- {valid_emoji} Validez: {vfrom} → {vto}

## Movimientos
"""


def init_book(project_dir: Path, partida: str, vfrom: date, vto: date) -> Path:
    """Crea `ledger.md` con la cabecera. Lanza `BookError`."""
    from core.ledger import read_logbook_movements

    if is_book(project_dir):
        raise BookError(f"{project_dir.name} ya tiene libro ({BOOK_FILE})")
    partida = (partida or "").strip().lstrip("#")
    if not partida or re.search(r"\s", partida):
        raise BookError("la partida es obligatoria y va sin espacios: --partida X")
    if vto < vfrom:
        raise BookError(f"la validez termina ({vto}) antes de empezar ({vfrom})")
    if read_logbook_movements(project_dir)[0]:
        raise BookError(f"{project_dir.name} tiene movimientos en el logbook: "
                        f"hay que migrarlos (ledger migrate, F2), no empezar de cero")
    path = book_path(project_dir)
    path.write_text(BOOK_TEMPLATE.format(
        name=project_dir.name, partida=partida, vfrom=vfrom.isoformat(),
        vto=vto.isoformat(), partida_emoji=PARTIDA_EMOJI, valid_emoji=VALID_EMOJI))
    link_in_project_md(project_dir)
    return path


def _require_book(project_dir: Path) -> Book:
    book = read_book(project_dir)
    if book is None:
        raise BookError(f"{project_dir.name} no tiene libro: orbit ledger "
                        f"{project_dir.name} init --partida X --from D --to D")
    return book


def _check_date(book: Book, when: date, force: bool) -> None:
    if not book.in_range(when) and not force:
        raise BookError(f"{when} está fuera de la validez del libro "
                        f"({book.valid_from} → {book.valid_to}); --force para anotarlo")


def _check_category(tag: str, category: Optional[str], cats) -> Optional[str]:
    category = (category or "").strip() or None
    if category is None:
        if tag != INCOME_TAG:
            raise BookError(f"un #{tag} necesita categoría: --cat {'|'.join(cats)}")
        return None
    if category not in cats:
        raise BookError(f"categoría «{category}» desconocida ({', '.join(cats)})")
    return category


def _check_text(label: str, value: Optional[str], required: bool = True) -> Optional[str]:
    value = " ".join((value or "").split()) or None
    if value is None:
        if required:
            raise BookError(f"falta {label}")
        return None
    if "·" in value or value.startswith("#"):
        raise BookError(f"{label} no puede llevar «·» ni empezar por «#»")
    return value


def _check_op_id(book: Book, tag: str, op_id: Optional[str],
                 skip: Optional[str] = None) -> Optional[str]:
    op_id = (op_id or "").strip() or None
    if op_id is None:
        return None
    if re.search(r"\s|#|·", op_id):
        raise BookError(f"la referencia '{op_id}' no puede llevar espacios, '#' ni '·'")
    twin = next((e for e in book.entries if e.live and e.tag == tag
                 and e.op_id == op_id and e.num != skip), None)
    if twin:
        raise BookError(f"la referencia {op_id} ya está en la entrada {twin.num} "
                        f"«{twin.title}»")
    return op_id


def open_commitments(book: Book):
    """Operaciones abiertas (compromisos con algo pendiente), por nº."""
    ops, _ = build_operations(book.movements())
    return [op for op in ops if op.state == OPEN]


def _check_commit(book: Book, tag: str, commit: Optional[str]) -> Optional[str]:
    if not commit:
        return None
    if tag != EXPENSE_TAG:
        raise BookError("solo un #gasto consume un compromiso (--commit)")
    commit = normalize_num(commit)
    target = book.get(commit)
    if target is None or target.tag != ORDER_TAG:
        raise BookError(f"la entrada {commit} no es un compromiso")
    if not target.live:
        raise BookError(f"el compromiso {commit} está anulado")
    if commit not in {op.op_id for op in open_commitments(book)}:
        raise BookError(f"el compromiso {commit} ya está cerrado")
    return commit


def import_doc(project_dir: Path, doc: Optional[str]) -> Optional[str]:
    """Justificante → enlace. Dentro del proyecto se enlaza tal cual; fuera, se
    copia a `cloud/ledger-logs/` con fecha. URL: tal cual. Lanza `BookError`."""
    if not doc:
        return None
    if "://" in doc:
        return doc
    src = Path(doc).expanduser()
    if not src.is_absolute() and (project_dir / doc).is_file():
        src = project_dir / doc
    if not src.is_file():
        raise BookError(f"no encuentro el justificante {doc}")
    try:
        return "./" + str(src.resolve().relative_to(project_dir.resolve()))
    except ValueError:
        pass
    from core.link_import import apply_mode
    try:
        link, _ = apply_mode(project_dir, src, "import",
                             non_md_subdir=LEDGER_LOGS, date_prefix=True)
    except (FileExistsError, RuntimeError, ValueError, FileNotFoundError) as exc:
        raise BookError(f"no he podido importar {doc}: {exc}")
    return link


def _trail_text(e: Entry) -> str:
    return f"{e.title} · ledger {e.num}"


def write_trail(project_dir: Path, e: Entry) -> None:
    """Rastro en el logbook: `fecha 💶 título · ledger N #tipo`."""
    from core.log import _append_entry as append_log, format_entry, init_logbook
    from core.log import resolve_file

    logbook = resolve_file(project_dir, "logbook")
    if not logbook.exists():
        init_logbook(logbook, project_dir.name)
    append_log(logbook, format_entry(_trail_text(e), e.tag, None, e.date.isoformat()))


def update_trail(project_dir: Path, e: Entry) -> bool:
    """Reescribe el rastro de *e* (tras cambiar título o fecha). True si lo tocó."""
    from core.log import find_logbook_file, format_entry

    logbook = find_logbook_file(project_dir)
    if not logbook or not logbook.exists():
        return False
    lines = logbook.read_text().splitlines()
    new = format_entry(_trail_text(e), e.tag, None, e.date.isoformat()).rstrip("\n")
    for i, line in enumerate(lines):
        m = _TRAIL_RE.search(line)
        if m and m.group(1) == e.num and not line.startswith(" "):
            if line == new:
                return False
            from core.undo import save_snapshot
            save_snapshot(logbook)
            lines[i] = new
            logbook.write_text("\n".join(lines) + "\n")
            return True
    return False


def trail_nums(project_dir: Path) -> List[str]:
    """Números de ledger que tienen rastro en el logbook."""
    from core.log import find_logbook_file

    logbook = find_logbook_file(project_dir)
    if not logbook or not logbook.exists():
        return []
    return [m.group(1) for line in logbook.read_text().splitlines()
            if not line.startswith(" ") and (m := _TRAIL_RE.search(line))]


def add_movement(project_dir: Path, *, tag: str, title: str, when: date,
                 payee: str, amount: str, category: Optional[str] = None,
                 doc: Optional[str] = None, op_id: Optional[str] = None,
                 commit: Optional[str] = None, closes: bool = False,
                 note: Optional[str] = None, trail: bool = True,
                 force: bool = False) -> Entry:
    """Anota un movimiento al final del libro. Lanza `BookError`."""
    book = _require_book(project_dir)
    if tag not in USER_LABELS:
        raise BookError(f"tipo «{tag}» desconocido ({', '.join(USER_LABELS)})")
    title = _check_text("el título", title)
    payee = _check_text("el beneficiario (en un ingreso, quién paga)", payee)
    _check_date(book, when, force)
    category = _check_category(tag, category, categories())
    try:
        value = signed_amount(tag, parse_amount(str(amount or "")))
    except ValueError as exc:
        raise BookError(str(exc))
    op_id = _check_op_id(book, tag, op_id)
    commit = _check_commit(book, tag, commit)
    if closes and not commit:
        raise BookError("--closes solo va en un #gasto con --commit")
    link = import_doc(project_dir, doc)          # lo último: copia ficheros

    e = Entry(num=book.next_num(), tag=tag, title=title, date=when,
              amount=value, payee=payee, category=category, link=link,
              op_id=op_id, commit=commit, closes=closes,
              notes=[" ".join(note.split())] if note and note.strip() else [])
    _append_entry(book, e)
    if trail:
        write_trail(project_dir, e)
    return e


#: campo → (emoji, cómo se muestra el valor)
_FIELDS = {
    "title":    ("título", str),
    "payee":    (PAYEE_EMOJI, str),
    "category": (CAT_EMOJI, str),
    "link":     ("justificante", lambda v: Path(str(v)).name),
    "amount":   (AMOUNT_EMOJI, format_amount),
    "date":     (DATE_EMOJI, lambda v: v.isoformat()),
    "op_id":    (ID_EMOJI, str),
}


def _show(name: str, value) -> str:
    return "—" if value in (None, "") else _FIELDS[name][1](value)


def edit_movement(project_dir: Path, num, *, title: Optional[str] = None,
                  payee: Optional[str] = None, category: Optional[str] = None,
                  doc: Optional[str] = None, amount: Optional[str] = None,
                  when: Optional[date] = None, op_id: Optional[str] = None,
                  note: Optional[str] = None, confirm: Optional[str] = None,
                  unconfirm: bool = False, force: bool = False,
                  today: Optional[date] = None) -> Tuple[Entry, Entry, List[str]]:
    """Corrige, confirma o desconfirma una entrada. Devuelve `(antes, después,
    cambios)`. Deja una nota automática con los cambios. Lanza `BookError`.

    - No cambia el tipo: se anula la entrada y se anota otra.
    - Una entrada confirmada (☑️) solo se corrige con `force`, y pierde el ☑️
      (salvo que la misma llamada la vuelva a confirmar).
    - `confirm` sin cambios no deja nota: el ☑️ ya lleva fecha e ID.
    """
    today = (today or date.today()).isoformat()
    book = _require_book(project_dir)
    e = book.get(num)
    if e is None:
        raise BookError(f"no hay ninguna entrada {normalize_num(num)}")
    before = replace(e, notes=list(e.notes))
    if confirm and unconfirm:
        raise BookError("--confirm y --unconfirm a la vez no tienen sentido")

    wanted = {}
    if title is not None:
        wanted["title"] = _check_text("el título", title)
    if payee is not None:
        wanted["payee"] = _check_text("el beneficiario", payee)
    if category is not None:
        wanted["category"] = _check_category(e.tag, category, categories())
    if amount is not None:
        try:
            wanted["amount"] = signed_amount(e.tag, parse_amount(str(amount)))
        except ValueError as exc:
            raise BookError(str(exc))
    if when is not None:
        _check_date(book, when, force)
        wanted["date"] = when
    if op_id is not None:
        wanted["op_id"] = _check_op_id(book, e.tag, op_id, skip=e.num)
    changes = [(k, getattr(e, k), v) for k, v in wanted.items() if getattr(e, k) != v]
    if doc is not None:
        changes.append(("link", e.link, None))    # el enlace se resuelve después

    if not e.live and (changes or confirm or unconfirm):
        raise BookError(f"la entrada {e.num} está anulada ({CANCEL_EMOJI} "
                        f"{e.cancelled}); solo admite --nota")
    if changes and e.confirmed and not force:
        raise BookError(f"la entrada {e.num} está confirmada ({CONC_EMOJI} "
                        f"{e.confirmed[1]}): --force la corrige y le quita la "
                        f"confirmación")
    if confirm:
        confirm = confirm.strip()
        if not confirm or "·" in confirm:
            raise BookError("el ID de la confirmación no puede ir vacío ni llevar «·»")
        if e.confirmed and e.confirmed[1] != confirm and not force:
            raise BookError(f"la entrada {e.num} ya está confirmada con "
                            f"{e.confirmed[1]}: --force para cambiarlo")
    if unconfirm and not e.confirmed:
        raise BookError(f"la entrada {e.num} no está confirmada")
    if not (changes or confirm or unconfirm or (note and note.strip())):
        raise BookError("nada que cambiar: --title --payee --cat --doc --amount "
                        "--date --id --nota --confirm --unconfirm")

    if doc is not None:
        link = import_doc(project_dir, doc)
        changes[-1] = ("link", e.link, link)
        if link == e.link:
            changes.pop()
    for name, _old, new in changes:
        setattr(e, name, new)

    shown = [f"{_FIELDS[n][0]} {_show(n, old)} → {_show(n, new)}"
             for n, old, new in changes]
    if unconfirm:
        e.notes.append(f"{today} confirmación retirada (era {e.confirmed[1]})")
        e.confirmed = None
    if changes:
        prefix = "modificado al confirmar" if confirm else "modificado"
        text = f"{today} {prefix}: " + _SEP.join(shown)
        if e.confirmed and not confirm:
            text += f"{_SEP}sin {CONC_EMOJI} (era {e.confirmed[1]})"
            e.confirmed = None
        e.notes.append(text)
    if confirm and not (e.confirmed and e.confirmed[1] == confirm):
        if e.confirmed:
            e.notes.append(f"{today} {CONC_EMOJI} {e.confirmed[1]} → {confirm}")
        e.confirmed = (today, confirm)
    if note and note.strip():
        e.notes.append(" ".join(note.split()))

    _replace_entry(book, e)
    if any(n in ("title", "date") for n, _o, _n in changes):
        update_trail(project_dir, e)
    return before, e, shown


def close_commitment(project_dir: Path, num, today: Optional[date] = None) -> Entry:
    """Cierra a mano un compromiso (🔒): lo no gastado deja de estar comprometido."""
    today = (today or date.today()).isoformat()
    book = _require_book(project_dir)
    e = book.get(num)
    if e is None or e.tag != ORDER_TAG:
        raise BookError(f"la entrada {normalize_num(num)} no es un compromiso")
    if not e.live:
        raise BookError(f"el compromiso {e.num} está anulado")
    if e.num not in {op.op_id for op in open_commitments(book)}:
        raise BookError(f"el compromiso {e.num} ya está cerrado")
    e.closes = True
    e.notes.append(f"{today} cerrado a mano")
    _replace_entry(book, e)
    return e


def cancel_movement(project_dir: Path, num, force: bool = False,
                    today: Optional[date] = None) -> Entry:
    """Anula una entrada (🚫 fecha): se queda en el libro y deja de contar."""
    today = (today or date.today()).isoformat()
    book = _require_book(project_dir)
    e = book.get(num)
    if e is None:
        raise BookError(f"no hay ninguna entrada {normalize_num(num)}")
    if not e.live:
        raise BookError(f"la entrada {e.num} ya está anulada ({e.cancelled})")
    if e.confirmed and not force:
        raise BookError(f"la entrada {e.num} está confirmada ({CONC_EMOJI} "
                        f"{e.confirmed[1]}): --force para anularla")
    if e.tag == ORDER_TAG:
        users = [x.num for x in book.entries if x.live and x.commit == e.num]
        if users:
            raise BookError(f"el compromiso {e.num} tiene gastos ({', '.join(users)}): "
                            f"anúlalos antes, o ciérralo (close)")
    e.cancelled = today
    _replace_entry(book, e)
    return e


# ── Migración desde el logbook (ADR-054, F2) ─────────────────────────────────

_PROVISIONAL_RE = re.compile(r"^P\d+$")


@dataclass
class MigrationPlan:
    """Lo que `ledger migrate` va a hacer. Se calcula sin tocar nada."""
    project_dir: Path
    partida:     Optional[str]
    valid_from:  date
    valid_to:    date
    entries:     List[Entry] = field(default_factory=list)
    raws:        List[str] = field(default_factory=list)       # cabecera vieja de cada entrada
    moves:       List[Tuple[Path, Path]] = field(default_factory=list)
    rewrites:    dict = field(default_factory=dict)            # Path → nº de enlaces
    missing_cat: List[str] = field(default_factory=list)       # nº sin categoría
    errors:      List[str] = field(default_factory=list)
    warnings:    List[str] = field(default_factory=list)


def _md_files(project_dir: Path) -> List[Path]:
    """Ficheros markdown del proyecto donde puede haber enlaces a justificantes
    (no se baja a `cloud/`, que es un enlace a la nube)."""
    skip = {BOOK_FILE, "ledger-summary.md"}
    files = [p for p in sorted(project_dir.glob("*.md")) if p.name not in skip]
    notes = project_dir / "notes"
    if notes.is_dir():
        files += sorted(notes.rglob("*.md"))
    return files


def _link_variants(name: str) -> List[str]:
    from urllib.parse import quote
    from core.deliver import encode_cloud_link
    return list(dict.fromkeys([name, encode_cloud_link(name), quote(name)]))


def plan_migration(project_dir: Path, vfrom: date, vto: date,
                   partida: Optional[str] = None, cats: Optional[dict] = None,
                   force: bool = False, today: Optional[date] = None) -> MigrationPlan:
    """Calcula la migración de los movimientos del logbook al libro. No escribe."""
    from urllib.parse import unquote
    from core.ledger import CARRY_TAG, read_logbook_movements, project_partida

    today = (today or date.today()).isoformat()
    cats = {normalize_num(k): v for k, v in (cats or {}).items()}
    allowed = categories()
    plan = MigrationPlan(project_dir, None, vfrom, vto)
    if is_book(project_dir):
        plan.errors.append(f"{project_dir.name} ya tiene libro: no hay nada que migrar")
        return plan
    movements, problems = read_logbook_movements(project_dir)
    plan.errors += [f"logbook: {p}" for p in problems if "el signo contradice" not in p]
    if not movements:
        plan.errors.append(f"{project_dir.name} no tiene movimientos en el logbook "
                           f"(para empezar de cero: ledger init)")
        return plan
    if any(m.tag == CARRY_TAG for m in movements):
        plan.errors.append("hay entradas #arrastre: la migración no las soporta todavía")
        return plan
    plan.partida = (partida or project_partida(project_dir) or "").strip().lstrip("#") or None
    if not plan.partida:
        plan.errors.append("no sé la partida: --partida X")
    if vto < vfrom:
        plan.errors.append(f"la validez termina ({vto}) antes de empezar ({vfrom})")

    num_of = {}                                      # 🆔 del compromiso → nº
    logs = project_dir / "cloud" / "logs"
    moved = {}
    for i, m in enumerate(movements, 1):
        num = f"{i:04d}"
        where = f"{num} {m.date} {m.concept}"
        if m.tag == ORDER_TAG and m.op_id:
            num_of[m.op_id] = num
        commit = None
        if m.ref:
            commit = num_of.get(m.ref)
            if commit is None:
                plan.errors.append(f"{where}: 🔗 {m.ref} no es ningún compromiso anterior")
        op_id = None if (m.op_id and _PROVISIONAL_RE.match(m.op_id)) else m.op_id
        category = cats.get(num)
        if m.tag != INCOME_TAG:
            if not category:
                plan.missing_cat.append(num)
            elif category not in allowed:
                plan.errors.append(f"{where}: categoría «{category}» desconocida "
                                   f"({', '.join(allowed)})")
        if not m.payee:
            plan.errors.append(f"{where}: sin beneficiario")
        if not (vfrom <= m.date <= vto) and not force:
            plan.errors.append(f"{where}: fuera de la validez ({vfrom} → {vto}); "
                               f"--force para migrarlo igualmente")

        link = m.link
        if link and "://" not in link:
            target = unquote(link.split("#", 1)[0])
            name = Path(target).name
            src = logs / name
            if Path(target).parent.name == "logs" and src.is_file():
                dst = project_dir / "cloud" / LEDGER_LOGS / name
                if name not in moved:
                    if dst.exists():
                        plan.errors.append(f"{where}: ya existe cloud/{LEDGER_LOGS}/{name}")
                    moved[name] = (src, dst)
                link = link.replace("cloud/logs/", f"cloud/{LEDGER_LOGS}/", 1)
            elif not (project_dir / target.lstrip("./")).exists() \
                    and not Path(target).expanduser().exists():
                plan.warnings.append(f"{where}: el justificante no existe ({link}); "
                                     f"se deja el enlace tal cual")
        notes = [m.note] if m.note else []
        confirmed = None
        if m.usc:
            confirmed = (today, m.usc)
            notes.append(f"{today} ☑️ migrado del logbook (sin fecha de validación)")
        plan.entries.append(Entry(
            num=num, tag=m.tag, title=m.concept, date=m.date, amount=m.amount,
            payee=m.payee, category=category, link=link, op_id=op_id,
            commit=commit, closes=m.closes, confirmed=confirmed, notes=notes))
        plan.raws.append(m.raw)

    plan.moves = list(moved.values())
    from core.log import find_logbook_file
    logbook = find_logbook_file(project_dir)
    for path in _md_files(project_dir):
        text = path.read_text()
        if logbook and path.resolve() == logbook.resolve():
            text = _trail_logbook(text, plan)       # lo que queda tras el rastro
        n = sum(text.count(f"cloud/logs/{v}")
                for name in moved for v in _link_variants(name))
        if n:
            plan.rewrites[path] = n
    return plan


def _trail_logbook(text: str, plan: "MigrationPlan") -> str:
    """El logbook con cada movimiento sustituido, en su sitio, por su rastro."""
    from core.ledger import _ENTRY_RE as _LOG_ENTRY_RE
    from core.log import format_entry

    trail = {}
    for e, raw in zip(plan.entries, plan.raws):
        trail.setdefault(raw, []).append(
            format_entry(_trail_text(e), e.tag, None, e.date.isoformat()).rstrip("\n"))
    out, lines, i = [], text.splitlines(), 0
    while i < len(lines):
        line = lines[i]
        m = None if line.startswith(" ") else _LOG_ENTRY_RE.match(line.strip())
        key = f"{m.group(1)} {m.group(2)}".strip() if m else None
        if key in trail and trail[key]:
            out.append(trail[key].pop(0))
            i += 1
            while i < len(lines) and lines[i].startswith(" ") and lines[i].strip():
                i += 1
            continue
        out.append(line)
        i += 1
    return "\n".join(out) + "\n"


def apply_migration(plan: MigrationPlan) -> Path:
    """Ejecuta un plan sin errores ni categorías pendientes. Deja undo de los
    markdown (los PDF movidos no: se deshace moviéndolos de vuelta)."""
    import shutil
    from core.log import find_logbook_file
    from core.undo import save_snapshot

    if plan.errors or plan.missing_cat:
        raise BookError("el plan tiene errores o categorías pendientes")
    project_dir = plan.project_dir

    # Primero, cada movimiento del logbook se sustituye, en su sitio, por su
    # rastro (antes de reescribir enlaces: las cabeceras viejas los llevan).
    logbook = find_logbook_file(project_dir)
    save_snapshot(logbook)
    logbook.write_text(_trail_logbook(logbook.read_text(), plan))

    for src, dst in plan.moves:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))

    names = [src.name for src, _ in plan.moves]
    for path in plan.rewrites:
        text = path.read_text()
        for name in names:
            for v in _link_variants(name):
                text = text.replace(f"cloud/logs/{v}", f"cloud/{LEDGER_LOGS}/{v}")
        save_snapshot(path)
        path.write_text(text)

    path = book_path(project_dir)
    header = BOOK_TEMPLATE.format(
        name=project_dir.name, partida=plan.partida,
        vfrom=plan.valid_from.isoformat(), vto=plan.valid_to.isoformat(),
        partida_emoji=PARTIDA_EMOJI, valid_emoji=VALID_EMOJI)
    body = []
    for e in plan.entries:
        body += [""] + render_entry(e)
    if path.exists():
        save_snapshot(path)
    path.write_text(header + "\n" + "\n".join(body).lstrip("\n") + "\n")
    link_in_project_md(project_dir)
    return path


# ── Enlace en project.md ─────────────────────────────────────────────────────

PROJECT_LINK = "[ledger](./ledger.md) ([resumen](./ledger-summary.md))"


def link_in_project_md(project_dir: Path) -> bool:
    """Añade el libro al pie de enlaces de `project.md` (junto a logbook,
    highlights, agenda…). Idempotente. True si lo ha añadido."""
    from core.log import resolve_file

    path = resolve_file(project_dir, "project")
    if not path or not path.exists():
        return False
    text = path.read_text()
    if "(./ledger.md)" in text:
        return False
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if "(./agenda.md)" in line and "(./logbook.md)" in line:
            anchor = "[agenda](./agenda.md)"
            if anchor in line:
                lines[i] = line.replace(anchor, f"{anchor} · {PROJECT_LINK}", 1)
            else:
                lines[i] = f"{line} · {PROJECT_LINK}"
            break
    else:
        lines += ["", PROJECT_LINK]
    from core.undo import save_snapshot
    save_snapshot(path)
    path.write_text("\n".join(lines) + "\n")
    return True

"""views/ledger_book.py — derivados del libro de contabilidad (ADR-054).

Cuando el proyecto tiene libro (`ledger.md` es la verdad, ver
:mod:`core.ledger_book`), lo derivado va a:

- `ledger-summary.md` — resumen validado ☑️ frente a vivo, desglose por
  categoría, compromisos abiertos y movimientos con acumulados.
- `ledger.json` — contrato para herramientas de fuera (versión 2: la clave de
  cada movimiento es su nº).

Nadie los edita: se regeneran al anotar y en cada `save`.
"""

import json
import re
from decimal import Decimal
from pathlib import Path
from typing import List, Optional

from core.ledger import (
    EXPENSE_TAG, INCOME_TAG, OPEN, ORDER_TAG, build_operations,
    currency_symbol, format_amount, summarize,
)
from core.ledger_book import Book, categories

SUMMARY_FILE = "ledger-summary.md"
JSON_VERSION = 2

_ZERO = Decimal("0.00")


def _esc(text: Optional[str]) -> str:
    return (text or "—").replace("|", "\\|")


def _link(text: str, url: Optional[str]) -> str:
    return f"[{_esc(text)}]({url})" if url else _esc(text)


def _validated_summary(book: Book):
    """Resumen de lo confirmado (☑️) solamente."""
    movs = [m for m in book.movements() if m.usc]
    return summarize(movs, build_operations(movs)[0])


def by_category(book: Book):
    """{categoría: (gastado, comprometido pendiente)} en magnitudes ≥ 0."""
    movs = book.movements()
    ops, _ = build_operations(movs)
    out = {c: [_ZERO, _ZERO] for c in categories()}
    for m in movs:
        if m.tag == EXPENSE_TAG:
            out.setdefault(m.category or "—", [_ZERO, _ZERO])[0] += abs(m.amount)
    for op in ops:
        if op.state == OPEN:
            cat = op.entries[0].category or "—"
            out.setdefault(cat, [_ZERO, _ZERO])[1] += op.pending
    return out


def build_summary_md(project_dir: Path, book: Book) -> str:
    from views.ledger import running_rows

    movs = book.movements()
    ops, op_problems = build_operations(movs)
    live = summarize(movs, ops)
    valid = _validated_summary(book)
    symbol = currency_symbol()
    n_live = len(book.live())
    n_ok = sum(1 for e in book.live() if e.confirmed)
    out_of_range = [e for e in book.live() if e.date and not book.in_range(e.date)]

    out = [f"# 💶 Resumen — {project_dir.name}"
           + (f" · {book.partida}" if book.partida else ""), ""]
    out.append(f"Verdad: [ledger.md](./ledger.md) · 📆 Validez "
               f"{book.valid_from or '?'} → {book.valid_to or '?'} · "
               + (f"✔ {n_live} de {n_live} movimientos dentro del rango"
                  if not out_of_range else
                  f"⚠️ {len(out_of_range)} fuera del rango: "
                  + ", ".join(e.num for e in out_of_range)))
    out.append("")

    out += [f"| {symbol} | Validado ☑️ | Vivo |", "|---|---:|---:|",
            f"| Dotación | {format_amount(valid.income + valid.carried)} | "
            f"{format_amount(live.income + live.carried)} |",
            f"| Gastado | {format_amount(valid.spent)} | {format_amount(live.spent)} |",
            f"| Comprometido (pendiente) | {format_amount(valid.committed)} | "
            f"{format_amount(live.committed)} |",
            f"| **Disponible** | {format_amount(valid.available)} | "
            f"**{format_amount(live.available)}** |", "",
            f"☑️ {n_ok} de {n_live} movimientos validados. Validado = solo las "
            f"entradas con ☑️; las cifras oficiales están en la revisión externa.",
            ""]

    out += ["## Por categoría (vivo)", "",
            "| Categoría | Gastado | Comprometido | Total |", "|---|---:|---:|---:|"]
    for cat, (spent, pending) in by_category(book).items():
        out.append(f"| {cat} | {format_amount(-spent)} | {format_amount(-pending)} | "
                   f"{format_amount(-(spent + pending))} |")
    out.append("")

    opens = [op for op in ops if op.state == OPEN]
    out += ["## Compromisos abiertos", ""]
    if opens:
        out += ["| Nº | Concepto | Comprometido | Gastado contra él | Pendiente |",
                "|---|---|---:|---:|---:|"]
        for op in opens:
            out.append(f"| {op.op_id} | {_link(op.concept, op.link)} | "
                       f"{format_amount(-op.committed)} | {format_amount(-op.spent)} | "
                       f"{format_amount(-op.pending)} |")
    else:
        out.append("*Ninguno.*")
    out.append("")

    out += ["## Movimientos", ""]
    rows = running_rows(movs, ops)
    if rows:
        out += ["| Nº | Fecha | Tipo | Concepto | 🗂️ | Beneficiario | 🔗 | Importe | "
                "Gastado | Disponible | Estado | ☑️ |",
                "|---|---|---|---|---|---|---|---:|---:|---:|---|---|"]
        for r in rows:
            m = r.mov
            ref = (m.ref + (" 🔒" if m.closes else "")) if m.ref else "—"
            out.append("| " + " | ".join([
                m.num, m.date.isoformat(), m.tag, _link(m.concept, m.link),
                _esc(m.category), _esc(m.payee), ref,
                format_amount(m.amount, plus=True), format_amount(r.spent),
                format_amount(r.available), r.state or "—",
                _esc(m.usc)]) + " |")
    else:
        out.append("*Sin movimientos.*")
    out.append("")

    cancelled = [e for e in book.entries if not e.live]
    if cancelled:
        out += ["## 🚫 Anuladas (no cuentan)", ""]
        out += [f"- {e.num} {e.title} · {e.cancelled}" for e in cancelled]
        out.append("")

    problems = list(book.problems) + op_problems
    if problems:
        out += ["## ⚠️ Entradas que no he podido leer o no cuadran", ""]
        out += [f"- {p}" for p in problems]
        out += ["", "Corrígelas en `ledger.md` (o con `orbit ledger … edit N`).", ""]
    return "\n".join(out)


def build_book_json(project_dir: Path, book: Book) -> str:
    from views.ledger_check import _resolve_link

    movs = book.movements()
    ops, op_problems = build_operations(movs)
    live = summarize(movs, ops)
    state_of = {m.num: op.state for op in ops for m in op.entries}
    rows = []
    for e in book.entries:
        path = _resolve_link(project_dir, e.link) if e.link else None
        rows.append({
            "key": e.num,
            "num": e.num,
            "date": e.date.isoformat() if e.date else None,
            "type": e.tag,
            "title": e.title,
            "category": e.category,
            "payee": e.payee,
            "amount": str(e.amount) if e.amount is not None else None,
            "id": e.op_id,
            "commitment": e.commit,
            "closes": e.closes,
            "state": (state_of.get(e.num) if e.live and e.tag in (ORDER_TAG, EXPENSE_TAG)
                      else None),
            "cancelled": e.cancelled,
            "validated": ({"date": e.confirmed[0], "id": e.confirmed[1]}
                          if e.confirmed else None),
            "notes": list(e.notes),
            "justificante": e.link,
            "justificante_path": str(path.resolve()) if path is not None else None,
        })
    data = {
        "version": JSON_VERSION,
        "project": project_dir.name,
        "partida": book.partida,
        "valid_from": book.valid_from.isoformat() if book.valid_from else None,
        "valid_to": book.valid_to.isoformat() if book.valid_to else None,
        "currency": "EUR",
        "summary": {
            "income": str(live.income + live.carried),
            "spent": str(live.spent),
            "committed": str(live.committed),
            "available": str(live.available),
        },
        "movements": rows,
        "problems": list(book.problems) + op_problems,
    }
    return json.dumps(data, ensure_ascii=False, indent=2) + "\n"


def write_book_views(project_dir: Path, book: Book, force: bool = False) -> Optional[Path]:
    """Regenera `ledger-summary.md` y `ledger.json`. **Nunca toca `ledger.md`.**

    Devuelve la ruta del resumen si lo escribió.
    """
    from views import autogen_banner
    from views.ledger import LEDGER_JSON, _unchanged

    data = build_book_json(project_dir, book)
    json_path = project_dir / LEDGER_JSON
    if force or not json_path.exists() or json_path.read_text() != data:
        json_path.write_text(data)

    body = build_summary_md(project_dir, book)
    path = project_dir / SUMMARY_FILE
    if not force and _unchanged(path, body):
        return None
    path.write_text(autogen_banner("ledger") + body)
    return path


# ── CLI: orbit ledger <proyecto> <acción> ────────────────────────────────────

def _echo(e) -> None:
    from core.ledger_book import render_entry
    for line in render_entry(e):
        print(f"  {line}")


def _available_line(project_dir: Path) -> str:
    from core.ledger import read_movements
    movs, _ = read_movements(project_dir)
    return (f"  💶 disponible {format_amount(summarize(movs).available)} "
            f"{currency_symbol()}")


def interrogate_add(project_dir: Path, args) -> None:
    """Pregunta en terminal lo que falte para `add`. Rellena *args*.
    Lanza `core.ledger.Cancelled` si el usuario aborta."""
    from datetime import date as _date

    from core.ledger import Cancelled, _ask_line, _ask_required, parse_amount
    from core.ledger_book import categories, open_commitments, read_book

    print("━━━ ledger · add (Enter = saltar lo opcional) ━━━")
    options = {"1": INCOME_TAG, "2": ORDER_TAG, "3": EXPENSE_TAG}
    while not args.mov_type:
        raw = _ask_line("¿Qué es? [1] ingreso  [2] compromiso  [3] gasto")
        args.mov_type = options.get((raw or "").strip()) or (
            raw.strip().lower() if raw and raw.strip().lower() in options.values() else None)
    if args.target is None:
        for _ in range(3):
            doc = _ask_line("📎 Justificante (ruta; Enter = sin justificante)") or None
            if doc is None or Path(doc).expanduser().is_file() \
                    or (project_dir / doc).is_file():
                args.target = doc
                break
            print(f"     ⚠️  no encuentro el fichero {doc}")
        else:
            raise Cancelled
    if not args.date:
        args.date = _ask_line("📅 Fecha", _date.today().isoformat())
    if not args.title:
        args.title = _ask_required("📝 Título")
    if not args.payee:
        args.payee = _ask_required("👤 Beneficiario" + (" (quién paga)"
                                   if args.mov_type == INCOME_TAG else ""))
    if not args.amount:
        args.amount = _ask_required("💶 Importe en € (sin signo)", parse_amount)
    cats = categories()
    if not args.cat and args.mov_type != INCOME_TAG:
        listing = "  ".join(f"[{i}] {c}" for i, c in enumerate(cats, 1))
        def _cat(v):
            if v in cats or (v.isdigit() and 1 <= int(v) <= len(cats)):
                return v
            raise ValueError(f"elige 1-{len(cats)}")
        raw = _ask_required(f"🗂️  Categoría {listing}", _cat)
        args.cat = cats[int(raw) - 1] if raw.isdigit() else raw
    if args.mov_type == EXPENSE_TAG and not args.commit:
        book = read_book(project_dir)
        opens = open_commitments(book)
        if opens:
            print("     Compromisos abiertos (pendiente):")
            for op in opens:
                print(f"       {op.op_id}  {op.date.isoformat()}  "
                      f"{format_amount(op.pending):>10}  {op.concept}")
            valid = {op.op_id: op for op in opens}
            for _ in range(3):
                raw = _ask_line("🔗 Nº del compromiso que consume (Enter = ninguno)")
                if not raw:
                    break
                num = raw.strip().zfill(4)
                if num in valid:
                    args.commit = num
                    break
                print(f"     ⚠️  {raw} no es un compromiso abierto")
            if args.commit and not args.closes:
                try:
                    value = parse_amount(str(args.amount))
                except ValueError:
                    value = None
                op = valid[args.commit]
                if value is not None and value < op.pending:
                    ans = _ask_line(f"   Quedan {format_amount(op.pending - value)} de "
                                    f"{args.commit} sin gastar. ¿Lo cierra? [s/N]")
                    args.closes = (ans or "").lower() in ("s", "si", "sí", "y", "yes")
    if not args.op_id:
        args.op_id = _ask_line("🆔 Referencia (nº de factura, autorización… "
                               "Enter = ninguna)") or None
    if args.nota is None:
        args.nota = _ask_line("📝 Nota (Enter = ninguna)") or None


def _fold(text: Optional[str]) -> str:
    import unicodedata
    text = unicodedata.normalize("NFKD", text or "")
    return "".join(c for c in text if not unicodedata.combining(c)).casefold()


def match_entries(book: Book, text: str, entries=None):
    """Entradas cuyo título, beneficiario o referencia contienen *text*
    (sin distinguir mayúsculas ni tildes)."""
    needle = _fold(text.strip())
    return [e for e in (book.entries if entries is None else entries)
            if any(needle in _fold(x) for x in (e.title, e.payee, e.op_id) if x)]


def pick_entry(project_dir: Path, text: Optional[str], action: str) -> str:
    """Nº de la entrada sobre la que actuar. *text* es un nº o un trozo del
    título/beneficiario/referencia; sin él (o si hay varias), en terminal se
    elige de la lista. Lanza `BookError`."""
    import sys

    from core.ledger import Cancelled, _ask_line
    from core.ledger_book import BookError, normalize_num, open_commitments, read_book

    book = read_book(project_dir)
    if book is None:
        raise BookError(f"{project_dir.name} no tiene libro")
    if action == "close":
        opens = {op.op_id for op in open_commitments(book)}
        pool = [e for e in book.entries if e.num in opens]
        what = "compromisos abiertos"
    elif action == "cancel":
        pool, what = [e for e in book.entries if e.live], "entradas vivas"
    else:
        pool, what = list(book.entries), "entradas"

    def _line(e):
        amount = format_amount(e.amount, plus=True) if e.amount is not None else "?"
        return (f"  {e.num}  {e.date or '?'}  {e.tag:<10} {amount:>12}  "
                f"{e.title} · {e.payee or '?'}" + ("  ☑️" if e.confirmed else "")
                + ("  🚫" if not e.live else ""))

    def _by_text(raw):
        raw = raw.strip()
        if raw.isdigit() and len(raw) <= 4:
            num = normalize_num(raw)
            if any(e.num == num for e in pool):
                return [next(e for e in pool if e.num == num)]
            raise BookError(f"la {num} no está entre las {what}")
        return match_entries(book, raw, pool)

    tty = sys.stdin.isatty()
    candidates = _by_text(text) if text else pool
    if text and not candidates:
        raise BookError(f"ninguna de las {what} coincide con «{text}»")
    for _ in range(3):
        if len(candidates) == 1 and text:
            e = candidates[0]
            print(f"→ {e.num} {e.title}")
            return e.num
        if not candidates:
            raise BookError(f"no hay {what}")
        if not tty:
            listing = "\n".join(_line(e) for e in candidates)
            raise BookError(f"¿cuál? dame el nº o un trozo del título:\n{listing}")
        print(f"{what.capitalize()}{f' que coinciden con «{text}»' if text else ''}:")
        for e in candidates:
            print(_line(e))
        try:
            raw = _ask_line("Nº o texto (Enter = cancelar)")
        except Cancelled:
            raw = None
        if not raw:
            raise BookError("cancelado; no se ha tocado nada")
        text = raw
        found = _by_text(raw)
        candidates = [e for e in found if e in candidates] or found
        if not candidates:
            print(f"     sin coincidencias para «{raw}»")
            candidates = pool
            text = None
    raise BookError("cancelado; no se ha tocado nada")


def _looks_like_path(text: str) -> bool:
    return "/" in text or text.startswith("~") or bool(
        re.search(r"\.(pdf|png|jpe?g|xlsx?|docx?|odt|ods|zip|eml|txt)$", text, re.I))


def _split_add_positionals(project_dir: Path, args) -> None:
    """`ledger add ["Título"] [fichero]`, en cualquier orden: lo que existe como
    fichero (o es una URL) es el justificante; lo demás, el título. Algo con
    pinta de ruta que no existe es un error, no un título."""
    from core.ledger_book import BookError

    doc = title = None
    for raw in (x for x in (args.target, getattr(args, "file", None)) if x):
        if "://" in raw or Path(raw).expanduser().is_file() or (project_dir / raw).is_file():
            if doc:
                raise BookError(f"dos justificantes: «{doc}» y «{raw}»")
            doc = raw
        elif _looks_like_path(raw):
            raise BookError(f"no encuentro el fichero {raw}")
        else:
            if title or args.title:
                raise BookError(f"dos títulos: «{title or args.title}» y «{raw}»")
            title = raw
    args.target, args.file = doc, None
    if title:
        args.title = title


def run_book_action(args) -> int:
    """`orbit ledger <proyecto> init|add|edit|close|cancel|check`."""
    import sys
    from datetime import date as _date

    from core.ledger import Cancelled
    from core.ledger_book import (
        BookError, add_movement, cancel_movement, close_commitment,
        edit_movement, init_book, read_book,
    )
    from core.log import find_project
    from views.ledger import write_ledger

    project_dir = find_project(args.project)
    if not project_dir:
        return 1
    action = args.action

    def _day(value, label):
        if not value:
            return None
        try:
            return _date.fromisoformat(value)
        except ValueError:
            raise BookError(f"{label} «{value}» no es una fecha (AAAA-MM-DD)")

    try:
        if action == "check":
            from views.ledger_check import run_ledger_check
            return run_ledger_check(args.project, strict=args.strict)

        if action == "init":
            vfrom = _day(args.valid_from, "--from")
            vto = _day(args.valid_to, "--to")
            if not (args.partida and vfrom and vto):
                raise BookError("init necesita --partida X --from AAAA-MM-DD --to AAAA-MM-DD")
            path = init_book(project_dir, args.partida, vfrom, vto)
            write_ledger(project_dir, force=True)
            print(f"✓ [{project_dir.name}] libro creado: {path.name} · partida "
                  f"{args.partida} · validez {vfrom} → {vto}")
            return 0

        if action == "migrate":
            return _run_migrate(project_dir, args, _day)

        if action == "add":
            if read_book(project_dir) is None:
                init_hint = (f"orbit ledger {args.project} init --partida X "
                             f"--from D --to D")
                raise BookError(f"{project_dir.name} no tiene libro: {init_hint}")
            _split_add_positionals(project_dir, args)
            if sys.stdin.isatty() and not (args.mov_type and args.title
                                           and args.payee and args.amount):
                interrogate_add(project_dir, args)
            missing = [f for f, v in (("--type", args.mov_type), ("--title", args.title),
                                      ("--payee", args.payee), ("--amount", args.amount))
                       if not v]
            if missing:
                raise BookError(f"falta {', '.join(missing)}")
            e = add_movement(
                project_dir, tag=args.mov_type, title=args.title,
                when=_day(args.date, "--date") or _date.today(),
                payee=args.payee, amount=args.amount, category=args.cat,
                doc=args.target, op_id=args.op_id, commit=args.commit,
                closes=args.closes, note=args.nota, trail=not args.no_log,
                force=args.force)
            write_ledger(project_dir)
            print(f"✓ [{project_dir.name}] ledger {e.num} · {e.tag} "
                  f"{format_amount(e.amount)} {currency_symbol()}"
                  + ("" if args.no_log else " · rastro en logbook"))
            _echo(e)
            print(_available_line(project_dir))
            return 0

        if getattr(args, "file", None):
            if action != "edit" or args.doc:
                raise BookError(f"sobra «{args.file}»: el justificante nuevo va en "
                                f"edit <entrada> <fichero>")
            args.doc = args.file
        args.target = pick_entry(project_dir, args.target, action)

        if action == "edit":
            before, e, shown = edit_movement(
                project_dir, args.target, title=args.title, payee=args.payee,
                category=args.cat, doc=args.doc, amount=args.amount,
                when=_day(args.date, "--date"), op_id=args.op_id, note=args.nota,
                confirm=args.confirm, unconfirm=args.unconfirm, force=args.force)
            write_ledger(project_dir)
            what = []
            if shown:
                what.append("; ".join(shown))
            if args.confirm and e.confirmed:
                what.append(f"☑️ confirmada {e.confirmed[0]} · {e.confirmed[1]}")
            if before.confirmed and not e.confirmed:
                what.append(f"☑️ retirada (era {before.confirmed[1]})")
            if args.nota:
                what.append("nota añadida")
            print(f"✓ [{project_dir.name}] ledger {e.num} · " + " · ".join(what))
            _echo(e)
            return 0

        if action == "close":
            e = close_commitment(project_dir, args.target)
            write_ledger(project_dir)
            print(f"✓ [{project_dir.name}] 🔒 compromiso {e.num} cerrado «{e.title}» · "
                  f"lo no gastado deja de estar comprometido")
            print(_available_line(project_dir))
            return 0

        if action == "cancel":
            e = cancel_movement(project_dir, args.target, force=args.force)
            write_ledger(project_dir)
            print(f"✓ [{project_dir.name}] 🚫 ledger {e.num} anulada «{e.title}» · "
                  f"se queda en el libro y deja de contar")
            print(_available_line(project_dir))
            return 0
    except Cancelled:
        print("⚠️  cancelado; no se ha escrito nada")
        return 1
    except BookError as exc:
        print(f"⚠️  {exc}")
        return 1
    print(f"⚠️  acción desconocida: {action}")
    return 1


def _parse_cats(raw: Optional[str]) -> dict:
    from core.ledger_book import BookError
    out = {}
    for item in filter(None, (x.strip() for x in (raw or "").split(","))):
        num, sep, cat = item.partition("=")
        if not sep or not num.strip() or not cat.strip():
            raise BookError(f"--cats: «{item}» no es N=categoría")
        out[num.strip()] = cat.strip()
    return out


def _print_plan(plan) -> None:
    print(f"━━━ ledger migrate · {plan.project_dir.name} ━━━")
    print(f"  🏷️  partida {plan.partida or '?'} · 📆 {plan.valid_from} → {plan.valid_to}")
    for e in plan.entries:
        extra = " · ".join(x for x in (
            f"🗂️ {e.category}" if e.category else ("🗂️ ?" if e.tag != INCOME_TAG else None),
            f"🆔 {e.op_id}" if e.op_id else None,
            f"🔗 {e.commit}" if e.commit else None,
            "🔒" if e.closes else None,
            f"☑️ {e.confirmed[1]}" if e.confirmed else None) if x)
        print(f"  {e.num}  {e.date}  {e.tag:<10} {format_amount(e.amount, plus=True):>12}  "
              f"{e.title} · {e.payee}" + (f"  [{extra}]" if extra else ""))
    print(f"  📦 {len(plan.moves)} justificante(s) cloud/logs/ → cloud/ledger-logs/")
    for path, n in plan.rewrites.items():
        print(f"  🔗 {n} enlace(s) reescritos en {path.relative_to(plan.project_dir)}")
    print(f"  🗒️  {len(plan.entries)} entrada(s) del logbook → rastro "
          f"«💶 título · ledger N #tipo»")
    for w in plan.warnings:
        print(f"  ⚠️  {w}")
    for err in plan.errors:
        print(f"  ❌ {err}")
    if plan.missing_cat:
        print(f"  ❓ sin categoría: {', '.join(plan.missing_cat)} (--cats N=cat,…)")


def _run_migrate(project_dir: Path, args, _day) -> int:
    """`orbit ledger <p> migrate --from D --to D [--partida X] [--cats …] [--dry-run]`."""
    import sys

    from core.ledger import _ask_line
    from core.ledger_book import BookError, apply_migration, categories, plan_migration
    from views.ledger import write_ledger

    vfrom, vto = _day(args.valid_from, "--from"), _day(args.valid_to, "--to")
    if not (vfrom and vto):
        raise BookError("migrate necesita la validez: --from AAAA-MM-DD --to AAAA-MM-DD")
    cats = _parse_cats(args.cats)
    plan = plan_migration(project_dir, vfrom, vto, partida=args.partida, cats=cats,
                          force=args.force)

    if plan.missing_cat and not plan.errors and not args.dry_run and sys.stdin.isatty():
        allowed = categories()
        listing = "  ".join(f"[{i}] {c}" for i, c in enumerate(allowed, 1))
        print(f"🗂️  Categorías: {listing}")
        for e in plan.entries:
            if e.num not in plan.missing_cat:
                continue
            for _ in range(3):
                raw = _ask_line(f"{e.num} {e.tag} {format_amount(e.amount)} {e.title}")
                if raw and raw.isdigit() and 1 <= int(raw) <= len(allowed):
                    cats[e.num] = allowed[int(raw) - 1]
                    break
                if raw in allowed:
                    cats[e.num] = raw
                    break
                print(f"     (1-{len(allowed)})")
        plan = plan_migration(project_dir, vfrom, vto, partida=args.partida,
                              cats=cats, force=args.force)

    _print_plan(plan)
    if plan.errors or plan.missing_cat:
        print("  ✋ no se ha tocado nada")
        return 1
    if args.dry_run:
        print("  (dry-run: no se ha tocado nada)")
        return 0
    if sys.stdin.isatty():
        ans = _ask_line("¿Migrar? [s/N]")
        if (ans or "").lower() not in ("s", "si", "sí", "y", "yes"):
            print("  ✋ no se ha tocado nada")
            return 1
    path = apply_migration(plan)
    write_ledger(project_dir, force=True)
    cats_arg = ",".join(f"{e.num}={e.category}" for e in plan.entries if e.category)
    print(f"✓ [{project_dir.name}] migrado: {path.name} es ahora la verdad "
          f"({len(plan.entries)} movimientos) · categorías: {cats_arg}")
    print(_available_line(project_dir))
    return 0


def print_book(project_dir: Path, book: Book, label: Optional[str] = None) -> int:
    """`ls ledger` / `ledger <p>` sobre un libro: los movimientos tal como
    están en `ledger.md` (nº, categoría, estado, ☑️) y el resumen validado
    frente a vivo. Solo imprime."""
    from views.ledger import running_rows

    name = label or project_dir.name
    print(f"💶 Ledger — {project_dir.name} · {book.partida or '?'} · "
          f"📆 {book.valid_from or '?'} → {book.valid_to or '?'}")
    movs = book.movements()
    ops, op_problems = build_operations(movs)
    if not book.entries:
        print(f"  (sin movimientos) · anota con: orbit ledger {name} add")
    else:
        rows = {r.mov.num: r for r in running_rows(movs, ops)}
        print(f"  {'Nº':<4}  {'Fecha':<10}  {'Tipo':<10}  {'Categoría':<13} "
              f"{'Importe':>12}  {'Disponible':>12}  ☑️  Concepto · Beneficiario")
        for e in sorted(book.entries, key=lambda x: (x.date or book.valid_from, x.num)):
            r = rows.get(e.num)
            mark = "🚫" if not e.live else ("☑️" if e.confirmed else "· ")
            extra = [x for x in (f"🔗 {e.commit}" if e.commit else None,
                                 "🔒" if e.closes else None,
                                 r.state if r and r.state else None,
                                 f"☑️ {e.confirmed[1]}" if e.confirmed else None,
                                 f"🚫 anulada {e.cancelled}" if not e.live else None) if x]
            amount = format_amount(e.amount, plus=True) if e.amount is not None else "?"
            avail = format_amount(r.available) if r else "—"
            print(f"  {e.num:<4}  {str(e.date or '?'):<10}  {e.tag:<10}  "
                  f"{(e.category or '—'):<13} {amount:>12}  {avail:>12}  {mark}  "
                  + (f"[{e.title}]({e.link})" if e.link else e.title)
                  + f" · {e.payee or '?'}"
                  + (f"  [{' · '.join(extra)}]" if extra else ""))
    live = summarize(movs, ops)
    valid = _validated_summary(book)
    symbol = currency_symbol()
    print(f"  {'─' * 60}")
    print(f"  {'':<27}{'Validado ☑️':>14}{'Vivo':>14}")
    for text, a, b in (("Dotación", valid.income + valid.carried, live.income + live.carried),
                       ("Gastado", valid.spent, live.spent),
                       ("Comprometido (pendiente)", valid.committed, live.committed),
                       ("Disponible", valid.available, live.available)):
        print(f"  {text + ':':<27}{format_amount(a):>14}{format_amount(b):>14} {symbol}")
    cats = [(c, sp + pe) for c, (sp, pe) in by_category(book).items() if sp + pe]
    if cats:
        print("  Por categoría: " + " · ".join(f"{c} {format_amount(-t)}" for c, t in cats))
    for problem in list(book.problems) + op_problems:
        print(f"  ⚠️  {problem}")
    return 0

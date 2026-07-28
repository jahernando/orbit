"""archive.py — archive old logbook entries, done tasks/milestones, past events, stale notes.

  orbit archive [<project>] [--months N] [--dry-run] [--force]
  orbit archive [<project>] --agenda     # only done tasks/milestones + past events
  orbit archive [<project>] --logbook    # only old logbook entries
  orbit archive [<project>] --notes      # only stale notes

Without flags: archives all categories, asking confirmation for each.
With --force: skips all confirmations.

Data is always recoverable via git log / tag del día.
"""

import re
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

from core.project import _find_new_project, _is_new_project
from core.config import iter_project_dirs
from core.log import find_logbook_file, resolve_file


_DATE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})\s")


# ── Confirmation helper ─────────────────────────────────────────────────────

def _confirm(prompt: str, force: bool) -> bool:
    """Ask user for confirmation. Returns True if accepted."""
    if force:
        return True
    if not sys.stdin.isatty():
        return False
    try:
        ans = input(prompt).strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        return False
    return ans in ("", "s", "si", "sí", "y", "yes")


# ── Counting helpers (dry-run / preview) ─────────────────────────────────────

def _count_old_logbook(project_dir: Path, cutoff: date) -> int:
    """Count logbook entries older than cutoff."""
    logbook = find_logbook_file(project_dir)
    if not logbook or not logbook.exists():
        return 0
    count = 0
    for line in logbook.read_text().splitlines():
        if line.startswith("  "):
            continue
        m = _DATE_RE.match(line.strip())
        if m:
            try:
                if date.fromisoformat(m.group(1)) < cutoff:
                    count += 1
            except ValueError:
                pass
    return count


def _count_done_agenda(project_dir: Path, cutoff: date) -> tuple:
    """Count done/cancelled tasks+milestones and past events. Returns (n_done, n_events)."""
    from core.agenda_cmds import _read_agenda
    agenda_path = resolve_file(project_dir, "agenda")
    if not agenda_path.exists():
        return 0, 0

    data = _read_agenda(agenda_path)
    n_done = 0
    for item in data["tasks"] + data["milestones"]:
        if item["status"] in ("done", "cancelled") and _item_before(item, cutoff):
            n_done += 1
    n_events = sum(1 for ev in data["events"] if _event_date(ev) < cutoff)
    return n_done, n_events


def _item_before(item: dict, cutoff: date) -> bool:
    """Check if a task/milestone date is before cutoff."""
    d = item.get("date")
    if not d:
        return True  # no date = old enough
    try:
        return date.fromisoformat(d) < cutoff
    except ValueError:
        return False


# ── Cleaning functions ───────────────────────────────────────────────────────

def _clean_logbook(project_dir: Path, cutoff: date) -> int:
    """Remove logbook entries older than cutoff. Returns count removed."""
    logbook = find_logbook_file(project_dir)
    if not logbook or not logbook.exists():
        return 0

    lines = logbook.read_text().splitlines()
    keep = []
    removed = 0
    removing = False

    for line in lines:
        if line.startswith("  ") and line.strip():
            if removing:
                continue
            keep.append(line)
            continue

        removing = False
        m = _DATE_RE.match(line.strip())
        if m:
            try:
                d = date.fromisoformat(m.group(1))
                if d < cutoff:
                    removed += 1
                    removing = True
                    continue
            except ValueError:
                pass
        keep.append(line)

    if removed:
        from core.undo import save_snapshot
        save_snapshot(logbook)
        logbook.write_text("\n".join(keep) + "\n")

    return removed


# ── Ledger: arrastre del saldo archivado ─────────────────────────────────────
#
# `_clean_logbook` **borra** las entradas anteriores al corte, y un movimiento
# de dinero vive en el logbook. Sin lo que sigue, archivar un proyecto con
# ledger no dejaría un histórico incompleto: dejaría un **saldo incorrecto**,
# y sin avisar. Por eso el archivado de un proyecto con movimientos siempre
# deja rastro en la verdad, se consolide o no ([[ADR-048]]).

def _carry_preview(project_dir: Path, cutoff: date):
    """Movimientos que se va a llevar el corte y su neto por partida.

    Devuelve `(n_movimientos, neto_total, {partida: neto})`.
    """
    from core.ledger import read_movements

    movements, _ = read_movements(project_dir)
    doomed = [m for m in movements if m.date < cutoff]
    if not doomed:
        return 0, None, {}

    from decimal import Decimal
    por_partida = {}
    for mov in doomed:
        por_partida[mov.partida] = por_partida.get(mov.partida, Decimal("0")) + mov.amount
    return len(doomed), sum(por_partida.values(), Decimal("0")), por_partida


def _write_carry(project_dir: Path, cutoff: date, por_partida: dict,
                 consolidate: bool) -> int:
    """Escribe la(s) entrada(s) `#arrastre`. Devuelve cuántas ha escrito.

    - `consolidate=True` → **una entrada por partida** con su neto. Consolidar
      todo en una sola línea destruiría el desglose para siempre, que es justo
      el dato que hará falta el día que haya presupuestos.
    - `consolidate=False` → una sola entrada con importe 0 marcando el corte.
      No es ceremonia: `ledger.md` es derivado y solo ve las entradas que
      existen, así que sin esta marca imprimiría el saldo truncado con total
      aplomo. Con ella, encabeza el fichero avisando.

    La fecha es la del corte, y el lector ordena `#arrastre` primero en empate,
    así que el saldo corrido arranca donde debe.
    """
    from decimal import Decimal

    from core.ledger import CARRY_TAG, build_body, project_partida
    from core.log import _append_entry, format_entry, init_logbook, resolve_file

    when = cutoff.isoformat()
    if consolidate:
        movimientos = [(partida, neto) for partida, neto in sorted(
            por_partida.items(), key=lambda kv: (kv[0] or ""))]
        concepto = f"Saldo arrastrado (movimientos anteriores a {when})"
    else:
        movimientos = [(project_partida(project_dir), Decimal("0"))]
        concepto = f"Archivado sin arrastre (movimientos anteriores a {when})"

    logbook = resolve_file(project_dir, "logbook")
    if not logbook.exists():
        init_logbook(logbook, project_dir.name)
    for partida, neto in movimientos:
        entry = format_entry(concepto, CARRY_TAG, None, when, orbit=True,
                             continuations=build_body(neto, partida))
        _append_entry(logbook, entry)
    return len(movimientos)


def _ask_carry(project_dir: Path, cutoff: date, force: bool):
    """Pregunta si consolidar, **antes** de que el corte se lleve los movimientos.

    Devuelve `(consolidar, {partida: neto})`, o `None` si el proyecto no tiene
    movimientos afectados (el caso de casi todos los proyectos).

    `--force` consolida: es la opción que preserva el saldo, y en una operación
    desatendida vale más un histórico resumido que un saldo falso.
    """
    from core.ledger import currency_symbol, format_amount

    n, neto, por_partida = _carry_preview(project_dir, cutoff)
    if not n:
        return None

    prompt = (f"    💶 {n} movimiento{'s' if n != 1 else ''} de ledger "
              f"anterior{'es' if n != 1 else ''} "
              f"(neto {format_amount(neto)} {currency_symbol()})\n"
              f"       ¿Consolidar como arrastre para no falsear el saldo? [S/n]: ")
    return _confirm(prompt, force), por_partida


def _finish_carry(project_dir: Path, cutoff: date, decision) -> None:
    """Escribe el arrastre (o la marca de corte) y regenera `ledger.md`."""
    if decision is None:
        return
    consolidate, por_partida = decision
    n = _write_carry(project_dir, cutoff, por_partida, consolidate)
    if consolidate:
        print(f"    💶 saldo arrastrado en {n} entrada{'s' if n != 1 else ''} "
              f"#arrastre")
    else:
        print("    ⚠️  archivado sin arrastre: el saldo del ledger ya no incluye "
              "lo anterior")
        print("       (queda anotado en logbook.md y ledger.md lo avisa en cabecera)")
    try:
        from views.ledger import write_ledger      # core → views, lazy (RULES)
        write_ledger(project_dir, force=True)
    except Exception:
        pass                                        # el derivado se regenera solo


def _clean_done_items(project_dir: Path, cutoff: date) -> int:
    """Remove done/cancelled tasks and milestones older than cutoff. Returns count."""
    from core.agenda_cmds import _read_agenda, _write_agenda

    agenda_path = resolve_file(project_dir, "agenda")
    if not agenda_path.exists():
        return 0

    data = _read_agenda(agenda_path)
    removed = 0

    for section in ("tasks", "milestones"):
        original = len(data[section])
        data[section] = [
            item for item in data[section]
            if not (item["status"] in ("done", "cancelled") and _item_before(item, cutoff))
        ]
        removed += original - len(data[section])

    if removed:
        _write_agenda(agenda_path, data)

    return removed


def _clean_events(project_dir: Path, cutoff: date) -> int:
    """Remove events older than cutoff from agenda.md. Returns count removed."""
    from core.agenda_cmds import _read_agenda, _write_agenda

    agenda_path = resolve_file(project_dir, "agenda")
    if not agenda_path.exists():
        return 0

    data = _read_agenda(agenda_path)
    original = len(data["events"])
    data["events"] = [
        ev for ev in data["events"]
        if _event_date(ev) >= cutoff
    ]
    removed = original - len(data["events"])

    if removed:
        _write_agenda(agenda_path, data)

    return removed


def _event_date(ev: dict) -> date:
    """Extract the event date, returning date.min on parse failure."""
    try:
        return date.fromisoformat(ev.get("date", ""))
    except ValueError:
        return date.min


# ── Stale notes ──────────────────────────────────────────────────────────────

def _find_stale_notes(project_dir: Path, cutoff: date) -> list:
    """Return list of note paths in notes/ not modified since cutoff."""
    notes_dir = project_dir / "notes"
    if not notes_dir.exists():
        return []

    stale = []
    cutoff_ts = cutoff.toordinal()
    for f in sorted(notes_dir.iterdir()):
        if not f.is_file() or not f.suffix == ".md":
            continue
        mtime = date.fromtimestamp(f.stat().st_mtime)
        if mtime.toordinal() < cutoff_ts:
            stale.append(f)
    return stale


def _delete_notes(stale: list) -> int:
    """Delete stale notes. Returns count deleted."""
    from core.undo import save_snapshot
    for f in stale:
        save_snapshot(f)
        f.unlink()
    return len(stale)


# ── Main command ─────────────────────────────────────────────────────────────

def run_archive(project: Optional[str] = None, months: int = 6,
              dry_run: bool = False, force: bool = False,
              do_agenda: bool = False, do_logbook: bool = False,
              do_notes: bool = False) -> int:
    """Archive old entries from a project (or all projects).

    Without flags: archives all, asking for each category.
    With --agenda/--logbook/--notes: only those categories.
    With --force: no confirmations.
    """
    # No flags → all
    do_all = not (do_agenda or do_logbook or do_notes)

    cutoff = date.today() - timedelta(days=months * 30)
    label = f"{months} meses"

    if project:
        project_dir = _find_new_project(project)
        if project_dir is None:
            return 1
        dirs = [project_dir]
    else:
        dirs = [d for d in iter_project_dirs() if _is_new_project(d)]
        if not dirs:
            print("No hay proyectos.")
            return 0

    prefix = "(dry-run) " if dry_run else ""
    print(f"\n  {prefix}Archivado anterior a {cutoff.isoformat()} ({label}):\n")

    total_agenda = total_logbook = total_notes = 0

    for d in dirs:
        # Count what's available
        n_done, n_ev = (0, 0)
        n_log = 0
        stale = []

        if do_all or do_agenda:
            n_done, n_ev = _count_done_agenda(d, cutoff)
        if do_all or do_logbook:
            n_log = _count_old_logbook(d, cutoff)
        if do_all or do_notes:
            stale = _find_stale_notes(d, cutoff)

        n_agenda = n_done + n_ev
        if not (n_agenda or n_log or stale):
            continue

        print(f"  [{d.name}]")

        # Agenda (done tasks/milestones + past events)
        if n_agenda and (do_all or do_agenda):
            parts = []
            if n_done:
                parts.append(f"{n_done} tarea{'s' if n_done != 1 else ''}/hito{'s' if n_done != 1 else ''} completado{'s' if n_done != 1 else ''}")
            if n_ev:
                parts.append(f"{n_ev} evento{'s' if n_ev != 1 else ''} pasado{'s' if n_ev != 1 else ''}")
            detail = " + ".join(parts)

            if dry_run:
                print(f"    📋 {detail}")
            elif _confirm(f"    📋 {detail} — ¿Eliminar? [S/n]: ", force):
                if n_done:
                    total_agenda += _clean_done_items(d, cutoff)
                if n_ev:
                    total_agenda += _clean_events(d, cutoff)
            else:
                print(f"    📋 omitido")

        # Logbook
        if n_log and (do_all or do_logbook):
            label_log = f"{n_log} entrada{'s' if n_log != 1 else ''} de logbook"
            if dry_run:
                print(f"    🗒️  {label_log}")
                n_mov, neto, _ = _carry_preview(d, cutoff)
                if n_mov:
                    from core.ledger import currency_symbol, format_amount
                    print(f"    💶 {n_mov} de ellas son movimientos de ledger "
                          f"(neto {format_amount(neto)} {currency_symbol()}) "
                          f"— se ofrecerá consolidar como arrastre")
            elif _confirm(f"    🗒️  {label_log} — ¿Eliminar? [S/n]: ", force):
                # El neto se calcula ANTES de borrar; la entrada se escribe
                # después, para que el corte no se la lleve por delante.
                carry = _ask_carry(d, cutoff, force)
                total_logbook += _clean_logbook(d, cutoff)
                _finish_carry(d, cutoff, carry)
            else:
                print(f"    🗒️  omitido")

        # Notes
        if stale and (do_all or do_notes):
            n = len(stale)
            label_notes = f"{n} nota{'s' if n != 1 else ''} obsoleta{'s' if n != 1 else ''}"
            if dry_run:
                print(f"    📝 {label_notes}")
                for f in stale:
                    mtime = date.fromtimestamp(f.stat().st_mtime)
                    print(f"        {f.name}  ({mtime.isoformat()})")
            elif _confirm(f"    📝 {label_notes} — ¿Eliminar? [S/n]: ", force):
                total_notes += _delete_notes(stale)
            else:
                print(f"    📝 omitido")

        print()

    total = total_agenda + total_logbook + total_notes
    if total == 0 and not dry_run:
        print("  ✓ Nada que archivar.")
    elif total and not dry_run:
        parts = []
        if total_agenda:
            parts.append(f"{total_agenda} de agenda")
        if total_logbook:
            parts.append(f"{total_logbook} de logbook")
        if total_notes:
            parts.append(f"{total_notes} notas")
        print(f"  ✓ Archivados: {', '.join(parts)}")
        print(f"  (recuperable con: git log -p -- <fichero>)")

    return 0

"""clean.py — prune old logbook entries, past events, and stale notes.

  orbit clean [<project>] [--months N] [--dry-run]

With git as backup, removed data is always recoverable via git log.

What gets cleaned:
  1. Logbook entries older than N months (default 6)
  2. Events whose date is older than N months
  3. Notes in notes/ not modified in N months (interactive)
"""

import re
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

from core.project import _find_new_project, _is_new_project, PROJECTS_DIR
from core.log import find_logbook_file, resolve_file


_DATE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})\s")


# ── Logbook cleaning ─────────────────────────────────────────────────────────

def _clean_logbook(project_dir: Path, cutoff: date, dry_run: bool) -> int:
    """Remove logbook entries older than cutoff. Returns count removed."""
    logbook = find_logbook_file(project_dir)
    if not logbook or not logbook.exists():
        return 0

    lines = logbook.read_text().splitlines()
    keep = []
    removed = 0
    removing = False  # True while skipping an old entry + its continuation lines

    for line in lines:
        # Continuation line (indented) — follows parent entry's fate
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

    if removed and not dry_run:
        logbook.write_text("\n".join(keep) + "\n")

    return removed


# ── Event cleaning ───────────────────────────────────────────────────────────

def _clean_events(project_dir: Path, cutoff: date, dry_run: bool) -> int:
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

    if removed and not dry_run:
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


def _prompt_delete_notes(stale: list, dry_run: bool) -> int:
    """Show stale notes, ask which to delete. Returns count deleted."""
    if not stale or not sys.stdin.isatty():
        return 0

    n = len(stale)
    print(f"  📝 {n} nota{'s' if n != 1 else ''} sin modificar:")
    for i, f in enumerate(stale, 1):
        mtime = date.fromtimestamp(f.stat().st_mtime)
        print(f"      [{i}] {f.name}  (último cambio: {mtime.isoformat()})")

    if dry_run:
        return 0

    while True:
        try:
            prompt = "  ¿Eliminar? [S=todas / 1,2,... / n]: " if n > 1 else "  ¿Eliminar? [S/n]: "
            ans = input(prompt).strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0

        if ans.lower() in ("n", "no"):
            return 0

        if ans == "" or ans.lower() in ("s", "si", "sí", "y", "yes"):
            selected = stale
        else:
            try:
                indices = [int(x.strip()) for x in ans.split(",")]
                selected = [stale[i - 1] for i in indices if 1 <= i <= n]
            except (ValueError, IndexError):
                print("  ⚠️  Selección no válida")
                continue
            if not selected:
                print("  ⚠️  Ninguna nota seleccionada")
                continue

        # Confirm if partial selection
        if len(selected) < n:
            print(f"\n  Notas seleccionadas:")
            for f in selected:
                print(f"      {f.name}")
            try:
                confirm = input("  ¿Confirmar? [S/n/r(repetir)]: ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                print()
                return 0
            if confirm in ("r", "repetir"):
                print()
                continue
            if confirm not in ("", "s", "si", "sí", "y", "yes"):
                return 0

        deleted = 0
        for f in selected:
            f.unlink()
            deleted += 1
        return deleted


# ── Main command ─────────────────────────────────────────────────────────────

def run_clean(project: Optional[str] = None, months: int = 6,
              dry_run: bool = False) -> int:
    """Clean old entries from a project (or all projects)."""

    cutoff = date.today() - timedelta(days=months * 30)
    label = f"{months} meses"

    if project:
        project_dir = _find_new_project(project)
        if project_dir is None:
            return 1
        dirs = [project_dir]
    else:
        if not PROJECTS_DIR.exists():
            print("No hay proyectos.")
            return 0
        dirs = sorted(d for d in PROJECTS_DIR.iterdir()
                      if d.is_dir() and _is_new_project(d))

    if dry_run:
        print(f"  (dry-run) Limpieza de entradas anteriores a {cutoff.isoformat()} ({label}):\n")
    else:
        print(f"  Limpieza de entradas anteriores a {cutoff.isoformat()} ({label}):\n")

    total_logbook = total_events = total_notes = 0

    for d in dirs:
        n_log = _clean_logbook(d, cutoff, dry_run)
        n_ev = _clean_events(d, cutoff, dry_run)
        stale = _find_stale_notes(d, cutoff)

        if n_log or n_ev or stale:
            prefix = "(dry-run) " if dry_run else ""
            print(f"  {prefix}{d.name}:")
            if n_log:
                print(f"      {n_log} entrada{'s' if n_log != 1 else ''} de logbook")
            if n_ev:
                print(f"      {n_ev} evento{'s' if n_ev != 1 else ''} pasado{'s' if n_ev != 1 else ''}")
            if stale:
                n_del = _prompt_delete_notes(stale, dry_run)
                if n_del:
                    print(f"      ✓ {n_del} nota{'s' if n_del != 1 else ''} eliminada{'s' if n_del != 1 else ''}")
                total_notes += n_del
            print()

        total_logbook += n_log
        total_events += n_ev

    if total_logbook + total_events + total_notes == 0:
        print("  ✓ Nada que limpiar.")
    elif not dry_run:
        parts = []
        if total_logbook:
            parts.append(f"{total_logbook} entradas de logbook")
        if total_events:
            parts.append(f"{total_events} eventos")
        if total_notes:
            parts.append(f"{total_notes} notas")
        print(f"  ✓ Eliminados: {', '.join(parts)}")
        print(f"  (recuperable con: git log -p -- <fichero>)")

    return 0

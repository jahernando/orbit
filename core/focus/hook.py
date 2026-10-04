"""core.focus.hook — done/drop de una task → símbolo con fecha en la hoja.

Vale para bloques de focus week (``## Bloques``) y tareas de focus day
(``## Días``). Lo llaman los puntos por los que se cierra una task/ms
(``api._complete_kind``, ``api._drop_kind``, ``lifecycle._generic_drop``).
Si el ``orbit_id`` del item está en una hoja focus sin balancear (la de
esta semana o la anterior, que aún espera su balance), su línea pasa a
``✅ MM-DD`` / ``❌ MM-DD``. Así el balance es exacto para lo cerrado por la
CLI; lo cerrado a mano en Obsidian lo recoge el balance sin fecha.

Best-effort: nunca lanza ni aborta el done/drop. Silencioso salvo cuando
marca algo. El balance lo desactiva (``suppressed()``) porque escribe la
hoja él mismo.
"""
from __future__ import annotations

import contextlib
import io
from datetime import date, timedelta
from pathlib import Path
from typing import Optional
from core.focus.common import _resolve_mission_dir, _week_file_path
from core.focus.days import _frozen_line_indices
from core.focus.weekfile import (
    _BLOCK_LINE_RE,
    _SYM_DONE,
    _SYM_DROP,
    _is_balanced,
    _regenerate_counter,
)


_SUPPRESSED = False


@contextlib.contextmanager
def suppressed():
    """Desactiva el hook dentro del bloque (lo usa el balance)."""
    global _SUPPRESSED
    prev, _SUPPRESSED = _SUPPRESSED, True
    try:
        yield
    finally:
        _SUPPRESSED = prev


def _mark_in_sheet(week_file: Path, oid: str, sym: str, when: date) -> bool:
    """Reescribe las líneas de *oid* (bloque y/o día). True si marcó alguna.

    Los días ya balanceados están congelados y no se tocan.
    """
    text = week_file.read_text()
    lines = text.splitlines()
    frozen = _frozen_line_indices(text)
    hit = False
    for i, line in enumerate(lines):
        m = _BLOCK_LINE_RE.match(line)
        if m and m.group(4) == oid and i not in frozen:
            indent, rest = m.group(1), m.group(5)
            lines[i] = (f"{indent}- {sym} {when.strftime('%m-%d')} "
                        f"[orbit:{oid}]{rest}")
            hit = True
    if hit:
        week_file.write_text("\n".join(lines)
                             + ("\n" if text.endswith("\n") else ""))
    return hit


def mark_closed(item: dict, status: str,
                today: Optional[date] = None) -> Optional[str]:
    """Marca el item cerrado en su hoja focus. Devuelve la semana o None.

    *status*: ``"done"`` o ``"cancelled"``.
    """
    if _SUPPRESSED or status not in ("done", "cancelled"):
        return None
    oid = item.get("orbit_id")
    if not oid:
        return None
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            mission_dir = _resolve_mission_dir()
        if mission_dir is None:
            return None
        today = today or date.today()
        sym = _SYM_DONE if status == "done" else _SYM_DROP
        for d in (today, today - timedelta(days=7)):
            wf = _week_file_path(mission_dir, d)
            if not wf.exists() or _is_balanced(wf.read_text()):
                continue
            if _mark_in_sheet(wf, oid, sym, today):
                _regenerate_counter(wf, mission_dir)
                week = wf.name[:-len("-focus.md")]
                print(f"  🎯 Focus {week}: {sym} {today.strftime('%m-%d')}")
                return week
    except Exception as e:  # best-effort: el done/drop ya está hecho
        print(f"  ⚠️  focus: no se pudo marcar la hoja ({e})")
    return None

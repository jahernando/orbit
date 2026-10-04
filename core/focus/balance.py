"""core.focus.balance — balance de semanas cerradas en el primer save.

Una hoja ``YYYY-WNN-focus.md`` cuyo domingo ya pasó y que no lleva
``- Balance: hecho`` se balancea:

1. bloques abiertos en ``mission/agenda.md`` → ``drop`` (solo hojas con
   ``- Balance: pendiente``; las hojas legacy, sin esa línea, se
   balancean una vez sin tocar sus bloques);
2. los símbolos de la hoja quedan congelados (✅ / ❌ / ❔) — desde aquí
   la hoja es la verdad histórica para el contador y la vista anual;
3. ``- Balance: hecho YYYY-MM-DD`` → idempotente.

Balance aproximado (decisión 2026-10-04): las tareas no guardan fecha de
cierre; lo cerrado entre el domingo y el save cuenta como hecho.
"""
from __future__ import annotations

import contextlib
import io
import re
from datetime import date
from pathlib import Path
from typing import Optional
from core.focus.common import _MISSION_NAME, _resolve_mission_dir
from core.focus.weekfile import (
    _BALANCE_DONE,
    _build_id_status_index,
    _parse_balance,
    _parse_week_file,
    _regenerate_counter,
    _set_balance_line,
    _sync_block_symbols,
)
from core.focus.hook import suppressed
from core.focus.year import _refresh_year_silent


_WEEK_FILE_RE = re.compile(r"^(\d{4})-W(\d{2})-focus\.md$")


def _week_sunday(week_file: Path) -> Optional[date]:
    m = _WEEK_FILE_RE.match(week_file.name)
    if not m:
        return None
    try:
        return date.fromisocalendar(int(m.group(1)), int(m.group(2)), 7)
    except ValueError:
        return None


def _pending_balances(mission_dir: Path, today: date) -> list[Path]:
    """Hojas de semanas ya cerradas (domingo < today) sin balance hecho."""
    notes = mission_dir / "notes"
    if not notes.is_dir():
        return []
    out = []
    for f in sorted(notes.iterdir()):
        sunday = _week_sunday(f)
        if sunday is None or sunday >= today:
            continue
        if _parse_balance(f.read_text()) != _BALANCE_DONE:
            out.append(f)
    return out


def _drop_open_blocks(ids: list[str], id_status: dict[str, str]) -> int:
    """Drop en mission de los bloques aún abiertos; actualiza *id_status*."""
    from core import api
    dropped = 0
    for oid in ids:
        if id_status.get(oid) != "pending":
            continue
        try:
            api.drop_task(project=_MISSION_NAME, orbit_id=oid)
        except ValueError as exc:
            print(f"  ⚠️  drop [orbit:{oid}]: {exc}")
            continue
        id_status[oid] = "cancelled"
        dropped += 1
    return dropped


def _balance_week(week_file: Path, mission_dir: Path, today: date) -> dict:
    """Balancea una hoja. Devuelve ``{week, done, total, dropped, legacy}``."""
    text = week_file.read_text()
    legacy = _parse_balance(text) is None
    id_status = _build_id_status_index(mission_dir)
    ids = [oid for oids in _parse_week_file(text)["blocks_by_rail"].values()
           for oid in oids]

    dropped = 0
    if not legacy:
        with suppressed():
            dropped = _drop_open_blocks(ids, id_status)

    text = _sync_block_symbols(text, id_status, final=True)
    text = _set_balance_line(text, f"{_BALANCE_DONE} {today.isoformat()}")
    week_file.write_text(text)
    done, total = _regenerate_counter(week_file, mission_dir)
    return {"week": week_file.name[:-len("-focus.md")], "done": done,
            "total": total, "dropped": dropped, "legacy": legacy}


def run_focus_balance(today: Optional[date] = None,
                      silent: bool = False) -> list[dict]:
    """Balancea todas las semanas cerradas pendientes. Devuelve resultados."""
    # Silencioso: corre en cada save, también en workspaces sin mission.
    with contextlib.redirect_stdout(io.StringIO()):
        mission_dir = _resolve_mission_dir()
    if mission_dir is None:
        return []
    today = today or date.today()
    results = [_balance_week(f, mission_dir, today)
               for f in _pending_balances(mission_dir, today)]
    for year in sorted({int(r["week"][:4]) for r in results}):
        _refresh_year_silent(mission_dir, year)
    if not silent:
        for r in results:
            tail = " (legacy, sin drop)" if r["legacy"] else \
                f" · {r['dropped']} drop" if r["dropped"] else ""
            print(f"  🎯 Focus {r['week']}: ✅ {r['done']}/{r['total']} "
                  f"bloques{tail}")
    return results


def _action_focus_balance(ctx):
    """Hook ``commit_pre``: balance de semanas cerradas antes del commit."""
    try:
        results = run_focus_balance()
    except Exception as e:
        return {"ok": False, "msg": f"{type(e).__name__}: {e}"}
    if results:
        from core.commit import _git_add_all_tracked
        _git_add_all_tracked()
    return {"ok": True, "msg": f"{len(results)} semana(s) balanceada(s)"}

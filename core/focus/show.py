"""core.focus.show — vista en terminal del focus ya configurado.

``focus day`` y ``focus week`` con hoja ya hecha empiezan mostrando lo que
hay (estado **en vivo** de la verdad, como la sección 🎯 del secretario) y
solo después ofrecen el menú; Enter sale sin tocar nada.

    focus week — 2026-W41 · ✅ 2/7 bloques
      ⚓ fca         ✅ lun 09:00 · ⬜ mié 09:00
      🔥 hk-general  ⬜ lun 15:00
      Días: lun ✅ 1/3 · mar ⬜ 0/2
"""
from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Optional
from core.focus.common import _RAILS, _RAIL_EMOJI, _iso_week_label
from core.focus.days import (
    _WEEKDAYS_ES,
    _day_header,
    _find_day,
    _parse_days,
    _project_status_lookup,
)
from core.focus.weekfile import _build_id_task_index, _parse_week_blocks_detailed


_STATUS_SYM = {"done": "✅", "cancelled": "❌", "pending": "⬜"}
_MISSING = "❔"


def _sym(status: Optional[str]) -> str:
    return _STATUS_SYM.get(status, _MISSING)


def day_items_live(day: dict) -> list[tuple[str, dict]]:
    """``[(símbolo, item)]``: estado en vivo; un día balanceado, el de la hoja."""
    if day["balanced"]:
        return [(it["sym"], it) for it in day["items"]]
    lookup = _project_status_lookup()
    return [(_sym(lookup(it["project"], it["oid"])), it) for it in day["items"]]


def day_view_lines(text: str, today: date) -> list[str]:
    """Focus de *today*; ``[]`` si no hay."""
    day = _find_day(text, today)
    if not day or not day["items"]:
        return []
    rows = day_items_live(day)
    done = sum(1 for s, _ in rows if s == "✅")
    out = [f"focus day — {_day_header(today)[4:]} · ✅ {done}/{len(rows)}"]
    out += [f"    {s} [{it['project']}] {it['title']}" for s, it in rows]
    return out


def _block_cell(task: Optional[dict]) -> str:
    if task is None:
        return _MISSING
    when = ""
    if task.get("date"):
        when = _WEEKDAYS_ES[date.fromisoformat(task["date"]).weekday()][:3]
    if task.get("time"):
        when += f" {task['time'].split('-')[0]}"
    return f"{_sym(task.get('status', 'pending'))} {when}".rstrip()


def week_view_lines(text: str, mission_dir: Path, target: date) -> list[str]:
    """Bloques de la semana por carril + resumen de sus días."""
    blocks = _parse_week_blocks_detailed(text)
    tasks = _build_id_task_index(mission_dir) if blocks else {}
    done = sum(1 for _, _, oid in blocks
               if (tasks.get(oid) or {}).get("status") == "done")
    out = [f"focus week — {_iso_week_label(target)} · "
           f"✅ {done}/{len(blocks)} bloques"]
    width = max((len(p) for _, p, _ in blocks), default=0)
    for rail in _RAILS:
        by_proj: dict[str, list[str]] = {}
        for r, proj, oid in blocks:
            if r == rail:
                by_proj.setdefault(proj, []).append(_block_cell(tasks.get(oid)))
        for proj, cells in by_proj.items():
            out.append(f"  {_RAIL_EMOJI[rail]} {proj:<{width}}  "
                       + " · ".join(cells))
    days = [d for d in _parse_days(text) if d["items"]]
    if days:
        parts = []
        for d in days:
            syms = [s for s, _ in day_items_live(d)]
            n = syms.count("✅")
            mark = "✅" if n == len(syms) else "⬜"
            parts.append(f"{_WEEKDAYS_ES[d['date'].weekday()][:3]} "
                         f"{mark} {n}/{len(syms)}")
        out.append("  Días: " + " · ".join(parts))
    return out

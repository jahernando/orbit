"""core.focus.prompts — prompts interactivos y creación de bloques."""
from __future__ import annotations

import re
import secrets
from datetime import date, timedelta
from pathlib import Path
from typing import Optional
from core.config import iter_project_dirs
from core.project import _find_new_project, _is_new_project, _strip_type_emoji
from core.focus.common import _DAYS, _MISSION_NAME, _RAIL_EMOJI


# ── Modo libre ───────────────────────────────────────────────────────────

_DAY_ES_SHORT = {"lun": "mon", "mar": "tue", "mie": "wed", "miércoles": "wed",
                 "mié": "wed", "jue": "thu", "vie": "fri"}


def _list_available_projects(mission_dir: Path) -> list[str]:
    """Sorted canonical names (no emoji) of all new-format projects bar mission."""
    names = []
    for d in iter_project_dirs():
        if not _is_new_project(d) or d == mission_dir:
            continue
        names.append(_strip_type_emoji(d.name))
    return sorted(names)


def _resolve_project_name(raw: str, available: list[str]) -> Optional[str]:
    """Resolve a user-typed substring against available project names."""
    raw_low = raw.lower().strip()
    if not raw_low:
        return None
    exact = [n for n in available if n.lower() == raw_low]
    if exact:
        return exact[0]
    matches = [n for n in available if raw_low in n.lower()]
    if not matches:
        print(f"    ⚠️  Ningún proyecto coincide con {raw!r}")
        return None
    if len(matches) > 1:
        print(f"    Varios coinciden con {raw!r}:")
        for i, n in enumerate(matches, 1):
            print(f"      {i}. {n}")
        try:
            sel = input("    selecciona #: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return None
        if not sel.isdigit() or not (1 <= int(sel) <= len(matches)):
            print("    ⚠️  Selección no válida")
            return None
        return matches[int(sel) - 1]
    return matches[0]


def _prompt_day(week_monday: date) -> Optional[date]:
    """Ask for a weekday (lun/mar/mie/jue/vie). Returns concrete date or None."""
    while True:
        try:
            raw = input("    día (lun/mar/mie/jue/vie): ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            return None
        if not raw:
            return None
        key = _DAY_ES_SHORT.get(raw) or _DAY_ES_SHORT.get(raw[:3])
        if not key:
            print(f"    ⚠️  Día no reconocido: {raw!r}")
            continue
        offset = _DAYS.index(key)
        return week_monday + timedelta(days=offset)


def _prompt_time_range(default_duration: int) -> Optional[str]:
    """Ask for HH:MM[-HH:MM]. If only start given, append +default_duration min."""
    while True:
        try:
            raw = input("    hora (HH:MM o HH:MM-HH:MM): ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return None
        if not raw:
            return None
        m = re.match(r"^(\d{1,2}):(\d{2})(?:-(\d{1,2}):(\d{2}))?$", raw)
        if not m:
            print(f"    ⚠️  Formato esperado: HH:MM o HH:MM-HH:MM")
            continue
        h1, m1 = int(m.group(1)), int(m.group(2))
        if not (0 <= h1 < 24 and 0 <= m1 < 60):
            print("    ⚠️  Hora inválida")
            continue
        if m.group(3):
            h2, m2 = int(m.group(3)), int(m.group(4))
            if not (0 <= h2 < 24 and 0 <= m2 < 60):
                print("    ⚠️  Hora fin inválida")
                continue
            return f"{h1:02d}:{m1:02d}-{h2:02d}:{m2:02d}"
        # Add default_duration minutes.
        total = h1 * 60 + m1 + default_duration
        h2, m2 = divmod(total, 60)
        if h2 >= 24:
            h2 = 23
            m2 = 59
        return f"{h1:02d}:{m1:02d}-{h2:02d}:{m2:02d}"


def _create_block(project_name: str, rail: str, week_label: str,
                  date_val: str, time_val: str) -> Optional[str]:
    """Create one focus block as a mission task. Returns orbit_id or None.

    Genera el ``orbit_id`` aquí (no espera al ics-share) para fijar la
    identidad del bloque al crearse — el archivo semanal lo referencia
    por id, así que el id tiene que existir antes de escribirlo.
    """
    from core import api
    oid = secrets.token_hex(4)  # 8 hex chars, mismo formato que share.py
    # Project name con prefijo emoji del tipo para coherencia visual con
    # el resto del dashboard ("[📚catedra]" en lugar de "[catedra]").
    pd = _find_new_project(project_name)
    display_name = pd.name if pd is not None else project_name
    title = f"{_RAIL_EMOJI[rail]} [[{display_name}]] · focus {week_label}"
    try:
        item = api.add_task(project=_MISSION_NAME, text=title,
                            date=date_val, time=time_val,
                            orbit_id=oid)
    except ValueError as exc:
        print(f"    ⚠️  {exc}")
        return None
    return item.get("orbit_id") or oid


def _ask_yn(prompt: str, default: bool = False) -> bool:
    suf = "[Y/n]" if default else "[y/N]"
    try:
        raw = input(f"{prompt} {suf}: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        return default
    if not raw:
        return default
    return raw in ("y", "yes", "s", "si", "sí")


def _create_blocks_for_project(canonical: str, rail: str, n_blocks: int,
                                week_label: str, monday: date,
                                duration: int) -> list[tuple[str, str]]:
    """Prompt día+hora for each of n_blocks and create them. Returns
    list of (project, orbit_id) for blocks successfully created."""
    emoji = _RAIL_EMOJI[rail]
    out: list[tuple[str, str]] = []
    for i in range(n_blocks):
        print(f"    bloque {i+1}/{n_blocks} — {canonical}")
        d = _prompt_day(monday)
        if d is None:
            print("    (bloque saltado)")
            continue
        t = _prompt_time_range(duration)
        if t is None:
            print("    (bloque saltado)")
            continue
        orbit_id = _create_block(canonical, rail, week_label,
                                  d.isoformat(), t)
        if orbit_id:
            out.append((canonical, orbit_id))
            print(f"    ✓ {emoji} [{canonical}] {d.isoformat()} ⏰{t}")
    return out

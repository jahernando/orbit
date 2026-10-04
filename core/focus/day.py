"""core.focus.day — ``orbit focus day``: hasta 5 tareas focus del día.

Candidatas: tasks e hitos abiertos de proyectos locales con fecha hoy o
vencidos (incluye los bloques de focus week de hoy, que son tasks de
mission). ``+proyecto`` añade todas las abiertas de ese proyecto. Las
elegidas se apuntan en ``## Días`` de la hoja semanal (se crea mínima si
la semana no tiene focus week). No toca las tareas salvo para darles
``orbit_id`` si no lo tienen.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Optional
from core.focus.common import _iso_week_label, _resolve_mission_dir, _week_file_path
from core.focus.days import (
    MAX_DAY_ITEMS,
    _day_header,
    _day_line,
    _find_day,
    _minimal_sheet,
    _write_day,
)


_KIND_EMOJI = {"task": "✏️", "milestone": "🏁"}
_KEY_KIND = (("tasks", "task"), ("milestones", "milestone"))


def _local_projects() -> list[Path]:
    from core.config import iter_federated_project_dirs
    from core.project import _is_new_project
    return [p for p in iter_federated_project_dirs(include_federated=False)
            if _is_new_project(p)]


def _read_agenda(project_dir: Path) -> Optional[dict]:
    from core.agenda.io import _read_agenda as _ra
    from core.log import resolve_file
    path = resolve_file(project_dir, "agenda")
    return _ra(path) if path is not None and path.exists() else None


def _candidate(project_dir: Path, kind: str, it: dict) -> dict:
    return {"project": project_dir.name, "kind": kind, "desc": it["desc"],
            "date": it.get("date"), "time": it.get("time"),
            "orbit_id": it.get("orbit_id")}


def _collect_candidates(today: date) -> list[dict]:
    """Abiertas con fecha ≤ hoy: hoy primero (por hora), luego vencidas."""
    iso = today.isoformat()
    out = []
    for p in _local_projects():
        data = _read_agenda(p)
        if data is None:
            continue
        for key, kind in _KEY_KIND:
            for it in data.get(key) or []:
                d = it.get("date")
                if it.get("status") == "pending" and d and d <= iso:
                    out.append(_candidate(p, kind, it))
    out.sort(key=lambda c: (c["date"] != iso, c["date"] if c["date"] != iso
                            else "", c.get("time") or "99"))
    return out


def _project_candidates(raw: str) -> Optional[list[dict]]:
    """Todas las abiertas del proyecto *raw* (nombre con o sin emoji)."""
    from core.project import _strip_type_emoji
    want = _strip_type_emoji(raw).lower()
    matches = [p for p in _local_projects()
               if _strip_type_emoji(p.name).lower() == want]
    if len(matches) != 1:
        print(f"  ⚠️  Proyecto no encontrado: {raw!r}")
        return None
    data = _read_agenda(matches[0]) or {}
    return [_candidate(matches[0], kind, it)
            for key, kind in _KEY_KIND for it in data.get(key) or []
            if it.get("status") == "pending"]


def _fmt_candidate(c: dict, today: date) -> str:
    when = ""
    if c["date"] and c["date"] < today.isoformat():
        when = f" · ⚠️ {c['date'][5:]}"
    elif c.get("time"):
        when = f" · {c['time']}"
    elif c["date"] and c["date"] > today.isoformat():
        when = f" · {c['date'][5:]}"
    return f"{_KIND_EMOJI[c['kind']]} [{c['project']}] {c['desc']}{when}"


def _key(c: dict) -> tuple:
    return (c["project"], c["orbit_id"] or (c["kind"], c["desc"], c["date"]))


def _pick(cands: list[dict], room: int, today: date) -> Optional[list[dict]]:
    """Bucle de selección. None = cancelado."""
    while True:
        print()
        for i, c in enumerate(cands, 1):
            print(f"  {i:>2}  {_fmt_candidate(c, today)}")
        if not cands:
            print("  (sin tareas para hoy ni vencidas)")
        try:
            raw = input(f"  hasta {room} (p. ej. 1 3 4) · +proyecto añade "
                        "sus tareas · Enter cancela: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return None
        if not raw:
            return None
        if raw.startswith("+"):
            extra = _project_candidates(raw[1:].strip())
            if extra:
                seen = {_key(c) for c in cands}
                cands = cands + [c for c in extra if _key(c) not in seen]
            continue
        parts = raw.replace(",", " ").split()
        if not all(p.isdigit() and 1 <= int(p) <= len(cands) for p in parts):
            print(f"  ⚠️  Selección no válida: {raw!r}")
            continue
        idx = list(dict.fromkeys(int(p) for p in parts))
        if len(idx) > room:
            print(f"  ⚠️  Máximo {room} (llevas {MAX_DAY_ITEMS - room} "
                  f"de {MAX_DAY_ITEMS}).")
            continue
        return [cands[i - 1] for i in idx]


def _menu_existing_day(day: dict) -> Optional[str]:
    print(f"  Ya hay focus hoy ({len(day['items'])}/{MAX_DAY_ITEMS}):")
    for it in day["items"]:
        print(f"    {it['sym']} [{it['project']}] {it['title']}")
    print("  1) añadir (default)  2) rehacer  3) abortar")
    try:
        raw = input("  selección [1]: ").strip() or "1"
    except (EOFError, KeyboardInterrupt):
        print()
        return None
    return {"1": "add", "2": "redo", "3": None}.get(raw, None)


def run_focus_day(today: Optional[date] = None) -> int:
    """Elige hasta 5 tareas focus para hoy y las apunta en la hoja semanal."""
    from core import api
    mission_dir = _resolve_mission_dir()
    if mission_dir is None:
        print("⚠️  No existe el proyecto 'mission' en este workspace.")
        return 1
    today = today or date.today()
    week_file = _week_file_path(mission_dir, today)
    text = week_file.read_text() if week_file.exists() else None

    print(f"focus day — {_day_header(today)[4:]}")
    existing = _find_day(text, today) if text else None
    mode = "add"
    if existing and existing["items"]:
        mode = _menu_existing_day(existing)
        if mode is None:
            print("Cancelado.")
            return 0
    kept = existing["items"] if existing and mode == "add" else []
    room = MAX_DAY_ITEMS - len(kept)
    if room <= 0:
        print(f"  Ya tienes {MAX_DAY_ITEMS}. Usa «rehacer» para cambiarlas.")
        return 0

    taken = {(it["project"], it["oid"]) for it in kept}
    cands = [c for c in _collect_candidates(today)
             if (c["project"], c["orbit_id"]) not in taken]
    chosen = _pick(cands, room, today)
    if not chosen:
        print("Cancelado.")
        return 0

    new_lines, echo = [], []
    for c in chosen:
        try:
            oid = c["orbit_id"] or api.ensure_orbit_id(
                c["kind"], c["project"], desc=c["desc"], date_val=c["date"])
        except ValueError as exc:
            print(f"  ⚠️  {exc} — omitida")
            continue
        if (c["project"], oid) in taken:
            continue
        taken.add((c["project"], oid))
        new_lines.append(_day_line(oid, c["project"], c["desc"]))
        echo.append(f"    ⬜ [{c['project']}] {c['desc']}")
    if not new_lines:
        print("  Nada que apuntar.")
        return 1

    if text is None:
        text = _minimal_sheet(today)
    text = _write_day(text, today, new_lines, replace=(mode == "redo"))
    week_file.parent.mkdir(parents=True, exist_ok=True)
    week_file.write_text(text)

    n = len(kept) + len(new_lines)
    verb = "rehecho" if mode == "redo" else ("ampliado" if kept else "creado")
    print(f"\n✓ Focus día {today.isoformat()} {verb} ({n}/{MAX_DAY_ITEMS}):")
    for it in kept:
        print(f"    {it['sym']} [{it['project']}] {it['title']}")
    print("\n".join(echo))
    print(f"✓ Hoja: {_iso_week_label(today)}-focus.md "
          f"(mission/notes) · balance al primer save de otro día")
    return 0

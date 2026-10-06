"""core.focus.day — ``orbit focus day``: hasta 5 tareas focus del día.

Candidatas, en tres grupos: (1) tasks e hitos abiertos de proyectos
locales con fecha hoy o vencidos (incluye los bloques de focus week de hoy,
que son tasks de mission); (2) tasks e hitos con un followup ``⏩ <= hoy``;
(3) las tasks abiertas (con o sin fecha) de los proyectos del carril ⚓ de
la focus week. ``+proyecto`` añade todas las abiertas de ese proyecto. Las
elegidas se apuntan en ``## Días`` de la hoja semanal (se crea mínima si
la semana no tiene focus week). **No toca la verdad** (ni fecha ni ⏩)
salvo para dar ``orbit_id`` a la tarea que no lo tenga.
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
# Grupos de candidatas, en orden de presentación.
_DUE, _FUP, _ANCHOR, _EXTRA = "due", "fup", "anchor", "extra"
_GROUP_TITLE = {_DUE: "📅 Hoy y vencidas", _FUP: "⏩ Followups",
                _ANCHOR: "⚓ Proyectos ancla", _EXTRA: "➕ Añadidas"}


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


def _candidate(project_dir: Path, kind: str, it: dict,
               group: str = _DUE) -> dict:
    from core.agenda.display import item_followups
    fups = sorted(f["date"] for f in item_followups(it) if f["date"])
    return {"project": project_dir.name, "kind": kind, "desc": it["desc"],
            "date": it.get("date"), "time": it.get("time"),
            "orbit_id": it.get("orbit_id"), "fup": fups[0] if fups else None,
            "group": group}


def _same_project(a: str, b: str) -> bool:
    from core.project import _strip_type_emoji
    return _strip_type_emoji(a).lower() == _strip_type_emoji(b).lower()


def _collect_candidates(today: date,
                        anchors: tuple = ()) -> list[dict]:
    """Abiertas para hoy, por grupos (sin repetir una tarea):

    1. fecha ≤ hoy — hoy primero (por hora), luego vencidas;
    2. ⏩ ≤ hoy — por fecha del ⏩;
    3. tasks abiertas de los proyectos *anchors* (carril ⚓).
    """
    iso = today.isoformat()
    due, fup, anchor = [], [], []
    for p in _local_projects():
        data = _read_agenda(p)
        if data is None:
            continue
        is_anchor = any(_same_project(p.name, a) for a in anchors)
        for key, kind in _KEY_KIND:
            for it in data.get(key) or []:
                if it.get("status") != "pending":
                    continue
                c = _candidate(p, kind, it)
                d = c["date"]
                if d and d <= iso:
                    due.append(c)
                elif c["fup"] and c["fup"] <= iso:
                    c["group"] = _FUP
                    fup.append(c)
                elif is_anchor and kind == "task":
                    c["group"] = _ANCHOR
                    anchor.append(c)
    due.sort(key=lambda c: (c["date"] != iso, c["date"] if c["date"] != iso
                            else "", c.get("time") or "99"))
    fup.sort(key=lambda c: (c["fup"], c["project"]))
    return due + fup + anchor


def _anchor_projects(text: Optional[str]) -> tuple:
    """Proyectos del carril ⚓ de la hoja semanal (vacío si no hay)."""
    if not text:
        return ()
    from core.focus.weekfile import _parse_rails
    return tuple(_parse_rails(text)["anchor"])


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
    return [_candidate(matches[0], kind, it, _EXTRA)
            for key, kind in _KEY_KIND for it in data.get(key) or []
            if it.get("status") == "pending"]


def _fmt_candidate(c: dict, today: date) -> str:
    when = ""
    if c["group"] == _FUP:
        when = f" · ⏩ {c['fup'][5:]}"
        if c["date"]:
            when += f" · 🗓️ {c['date'][5:]}"
    elif c["date"] and c["date"] < today.isoformat():
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
        group = None
        for i, c in enumerate(cands, 1):
            if c["group"] != group:
                group = c["group"]
                print(f"\n  {_GROUP_TITLE[group]}")
            print(f"  {i:>2}  {_fmt_candidate(c, today)}")
        if not cands:
            print("\n  (sin tareas para hoy, vencidas, ⏩ ni ancla)")
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


def _menu_existing_day(text: str, today: date) -> Optional[str]:
    """Muestra el focus de hoy (estado en vivo) y pregunta. Enter = salir."""
    from core.focus.show import day_view_lines
    print("\n".join(day_view_lines(text, today)))
    print(f"  1) añadir (hasta {MAX_DAY_ITEMS})  2) rehacer  · Enter sale")
    try:
        raw = input("  selección: ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return None
    return {"1": "add", "2": "redo"}.get(raw)


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

    existing = _find_day(text, today) if text else None
    mode = "add"
    if existing and existing["items"]:
        mode = _menu_existing_day(text, today)
        if mode is None:
            return 0
    else:
        print(f"focus day — {_day_header(today)[4:]}")
    kept = existing["items"] if existing and mode == "add" else []
    room = MAX_DAY_ITEMS - len(kept)
    if room <= 0:
        print(f"  Ya tienes {MAX_DAY_ITEMS}. Usa «rehacer» para cambiarlas.")
        return 0

    taken = {(it["project"], it["oid"]) for it in kept}
    cands = [c for c in _collect_candidates(today, _anchor_projects(text))
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

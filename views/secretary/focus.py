"""views/secretary/focus.py — sección ``## 🎯 Focus`` de la agenda del secretario.

Viewer puro: lee la hoja semanal de mission (qué es focus) y la verdad de
los proyectos (en qué estado está cada tarea), nunca escribe. Va entre los
contadores y ``📅 Hoy``.

Focus "encendido" ⇔ existe hoja para la semana actual y su ``Status`` no
es ``off``. Sin hoja → la sección no aparece.

    ## 🎯 Focus

    **Semana** [2026-W41](…) · ✅ 2/5 bloques
    - ⚓ Anchor: [paper](…) ✅⬜ · [catedra](…) ⬜
    - 🔥 Push: [web](…) ✅

    **Hoy** · ✅ 1/3
    - ✅ [paper](…) · Revisar borrador
    - ⬜ [catedra](…) · Enviar informe

Estados en vivo desde la verdad (así también cuenta lo cerrado a mano en
Obsidian): ✅ hecho · ❌ drop · ⬜ abierto · ❔ no encontrado.
"""
from datetime import date as _date
from pathlib import Path
from typing import Optional


_STATUS_SYM = {"done": "✅", "cancelled": "❌", "pending": "⬜"}
_MISSING = "❔"


def _sym(status: Optional[str]) -> str:
    return _STATUS_SYM.get(status, _MISSING)


def _sheet_link(week_file: Path, label: str) -> str:
    from core.config import ORBIT_HOME
    try:
        rel = week_file.relative_to(ORBIT_HOME)
    except ValueError:
        return label
    return f"[{label}](../../{rel})"


def _project_link(name: Optional[str], dirs: dict) -> str:
    from views.secretary._agenda_table import proj_link_md
    p = dirs.get(name)
    return proj_link_md(p) if p is not None else f"\\[{name or '?'}\\]"


def focus_lines(today: Optional[_date] = None) -> list:
    """Líneas de la sección (incluye cabecera y línea en blanco final).

    ``[]`` si focus está apagado. Nunca lanza: un fallo deja la sección
    fuera para no tumbar la agenda.
    """
    try:
        return _focus_lines(today or _date.today())
    except Exception:
        return []


def _focus_lines(today: _date) -> list:
    import contextlib
    import io
    from core.config import iter_federated_project_dirs
    from core.focus import (
        _RAILS, _RAIL_EMOJI, _RAIL_LABEL, _build_id_status_index,
        _find_day, _iso_week_label, _parse_week_blocks_detailed,
        _parse_week_file, _project_status_lookup, _resolve_mission_dir,
        _week_file_path,
    )
    with contextlib.redirect_stdout(io.StringIO()):
        mission_dir = _resolve_mission_dir()
    if mission_dir is None:
        return []
    week_file = _week_file_path(mission_dir, today)
    if not week_file.exists():
        return []
    text = week_file.read_text()
    status = _parse_week_file(text)["status"]
    if status == "off":
        return []

    dirs = {p.name: p
            for p in iter_federated_project_dirs(include_federated=False)}
    week_label = _iso_week_label(today)
    out = ["## 🎯 Focus", ""]

    blocks = _parse_week_blocks_detailed(text)
    if blocks:
        id_status = _build_id_status_index(mission_dir)
        done = sum(1 for _, _, oid in blocks if id_status.get(oid) == "done")
        tag = " · 🟡 especial" if status == "especial" else ""
        out.append(f"**Semana** {_sheet_link(week_file, week_label)} · "
                   f"✅ {done}/{len(blocks)} bloques{tag}")
        for rail in _RAILS:
            by_proj: dict = {}
            for r, proj, oid in blocks:
                if r == rail:
                    by_proj.setdefault(proj, []).append(_sym(id_status.get(oid)))
            if not by_proj:
                continue
            cells = " · ".join(
                f"{_project_link(_match_dir(p, dirs), dirs)} {''.join(s)}"
                for p, s in by_proj.items())
            out.append(f"- {_RAIL_EMOJI[rail]} {_RAIL_LABEL[rail]}: {cells}")
        out.append("")

    day = _find_day(text, today)
    if day and day["items"]:
        lookup = _project_status_lookup()
        syms = [_sym(lookup(it["project"], it["oid"])) for it in day["items"]]
        n_done = syms.count("✅")
        head = "**Hoy**" if blocks else \
            f"**Hoy** {_sheet_link(week_file, week_label)}"
        out.append(f"{head} · ✅ {n_done}/{len(syms)}")
        for s, it in zip(syms, day["items"]):
            out.append(f"- {s} {_project_link(it['project'], dirs)} · "
                       f"{it['title']}")
        out.append("")
    elif not blocks:
        return []
    return out


def _match_dir(name: str, dirs: dict) -> Optional[str]:
    """Los bloques guardan el proyecto sin emoji de tipo → nombre de dir."""
    if name in dirs:
        return name
    from core.project import _strip_type_emoji
    hits = [d for d in dirs if _strip_type_emoji(d) == name]
    return hits[0] if len(hits) == 1 else name

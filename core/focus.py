"""core.focus — planificación semanal por carriles (anchor / push / joy).

Mission-specific por construcción en v1. Cada workspace declara su propia
plantilla en ``mission/notes/focus-template.md``; el archivo semanal vive
en ``mission/notes/<ISO-week>-focus.md`` y contiene IDs (``[orbit:…]``)
de las tasks-bloque, no wikilinks frágiles.

Bloque = task en ``mission/agenda.md`` con ``date`` + ``time HH:MM-HH:MM``
y wikilink al proyecto-carril en el título. Se crea vía
:func:`core.api.add_task` (capa pura que devuelve el dict con ``orbit_id``).

Formato del template (bullets, sin YAML — coherente con project.md)::

    # Focus · plantilla

    ## Carriles

    - Anchor: 2 proyectos × 2 bloques
    - Push:   1-2 proyectos × 1 bloque
    - Joy:    0-1 proyectos × 1 bloque

    ## Bloque

    - Duración: 90 min

    ## Theme days

    - Lunes: research
    - Martes: research
    - Miércoles: teaching
    - Jueves: gestion
    - Viernes: light
"""
from __future__ import annotations

import re
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

from core.config import TEMPLATES_DIR
from core.project import _find_new_project


_MISSION_NAME = "mission"
_TEMPLATE_FILENAME = "focus-template.md"

_RAILS = ("anchor", "push", "joy")
_RAIL_EMOJI = {"anchor": "⚓", "push": "🔥", "joy": "🌿"}
_RAIL_LABEL = {"anchor": "Anchor", "push": "Push", "joy": "Joy"}
_DAYS = ("mon", "tue", "wed", "thu", "fri")
_DAY_LABEL = {"mon": "Lunes", "tue": "Martes", "wed": "Miércoles",
              "thu": "Jueves", "fri": "Viernes"}
_DAY_FROM_ES = {v.lower(): k for k, v in _DAY_LABEL.items()}



def _iso_week_label(d: date) -> str:
    """Return ``YYYY-WNN`` for the ISO week containing *d*."""
    y, w, _ = d.isocalendar()
    return f"{y}-W{w:02d}"


def _week_bounds(d: date) -> tuple[date, date]:
    """Return (monday, friday) of the ISO week containing *d*."""
    monday = d - timedelta(days=d.weekday())
    return monday, monday + timedelta(days=4)


def _resolve_mission_dir() -> Optional[Path]:
    """Locate the mission project in the current workspace. None if absent."""
    return _find_new_project(_MISSION_NAME)


def _week_file_path(mission_dir: Path, d: date) -> Path:
    """Return ``mission/notes/<YYYY-WNN>-focus.md`` for the week of *d*."""
    return mission_dir / "notes" / f"{_iso_week_label(d)}-focus.md"


def _template_path(mission_dir: Path) -> Path:
    return mission_dir / "notes" / _TEMPLATE_FILENAME


# ── Template I/O ─────────────────────────────────────────────────────────

# Matches "- ⚓ Anchor: 2 proyectos × 2 bloques" or
#         "- ⚓ Anchor: 1-2 proyectos × 1 bloque" (range allowed in N).
# Tolerates extra spaces and the "s" plural on proyectos/bloques.
_RAIL_RE = re.compile(
    r"^-\s+\S+\s+(Anchor|Push|Joy)\s*:\s*"
    r"(\d+)(?:-(\d+))?\s+proyectos?\s*[×x]\s*(\d+)\s+bloques?\s*$",
    re.IGNORECASE,
)
_DURATION_RE = re.compile(r"^-\s+Duraci[oó]n\s*:\s*(\d+)\s*min\s*$",
                          re.IGNORECASE)
_THEME_RE = re.compile(
    r"^-\s+(Lunes|Martes|Mi[eé]rcoles|Jueves|Viernes)\s*:\s*(\S+)\s*$",
    re.IGNORECASE,
)


def _parse_template(text: str) -> dict:
    """Parse the bullet-format template text → dict.

    Raises :class:`ValueError` if required fields are missing or malformed.
    """
    template: dict = {
        "projects_per_rail": {},
        "blocks_per_project": {},
        "block_duration": None,
        "theme_days": {},
    }
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        m = _RAIL_RE.match(s)
        if m:
            rail = m.group(1).lower()
            lo = int(m.group(2))
            hi = int(m.group(3)) if m.group(3) else lo
            blocks = int(m.group(4))
            template["projects_per_rail"][rail] = (lo, hi)
            template["blocks_per_project"][rail] = blocks
            continue
        m = _DURATION_RE.match(s)
        if m:
            template["block_duration"] = int(m.group(1))
            continue
        m = _THEME_RE.match(s)
        if m:
            day_label = m.group(1).lower().replace("é", "e")
            day_key = _DAY_FROM_ES.get(day_label) or _DAY_FROM_ES.get(
                m.group(1).lower())
            if day_key:
                template["theme_days"][day_key] = m.group(2).lower()
            continue
        # Unknown bullet under a section: ignore silently (allows user notes).

    # Validate.
    for rail in _RAILS:
        if rail not in template["projects_per_rail"]:
            raise ValueError(
                f"focus-template: falta la línea '{_RAIL_EMOJI[rail]} "
                f"{_RAIL_LABEL[rail]}: …'"
            )
    if template["block_duration"] is None:
        raise ValueError("focus-template: falta 'Duración: N min'")
    return template


def _format_template(template: dict) -> str:
    """Serialise a template dict back to the bullet-format text."""
    out = ["# Focus · plantilla", "", "## Carriles", ""]
    for rail in _RAILS:
        lo, hi = template["projects_per_rail"][rail]
        rng = f"{lo}" if lo == hi else f"{lo}-{hi}"
        proj_word = "proyecto" if hi == 1 else "proyectos"
        n_blocks = template["blocks_per_project"][rail]
        blk_word = "bloque" if n_blocks == 1 else "bloques"
        out.append(f"- {_RAIL_EMOJI[rail]} {_RAIL_LABEL[rail]}: "
                   f"{rng} {proj_word} × {n_blocks} {blk_word}")
    out += ["", "## Bloque", "",
            f"- Duración: {template['block_duration']} min",
            "", "## Theme days", ""]
    for day in _DAYS:
        theme = template["theme_days"].get(day, "")
        out.append(f"- {_DAY_LABEL[day]}: {theme}")
    out.append("")
    return "\n".join(out)


def _load_template(mission_dir: Path) -> Optional[dict]:
    """Read mission's focus-template.md. Returns None if absent."""
    path = _template_path(mission_dir)
    if not path.exists():
        return None
    return _parse_template(path.read_text())


def _write_template(mission_dir: Path, template: dict) -> Path:
    """Write template to mission/notes/focus-template.md. Returns path."""
    path = _template_path(mission_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_format_template(template))
    return path


# ── Bootstrap (copia desde factory en 📐templates/) ──────────────────────

def _bootstrap_template_from_factory(mission_dir: Path) -> dict:
    """Copy ``📐templates/focus-template.md`` to mission and return its parsed dict.

    Patrón análogo a :func:`core.project.run_project_create`: el factory vive
    en ``TEMPLATES_DIR`` y se materializa al usar focus por primera vez en un
    workspace. El usuario edita la copia local para personalizarla.
    """
    factory = TEMPLATES_DIR / _TEMPLATE_FILENAME
    if not factory.exists():
        raise FileNotFoundError(
            f"focus: plantilla factory ausente en {factory}")
    dest = _template_path(mission_dir)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(factory.read_text())
    print(f"📝 Plantilla focus copiada a {dest}")
    print("   Edítala a mano para ajustar carriles, bloques y theme days.")
    return _parse_template(dest.read_text())


# ── Public entry point ───────────────────────────────────────────────────

def run_focus_week(next_week: bool = False, review: bool = False) -> int:
    """Plan (or review) the focus blocks for the current or next ISO week.

    *next_week*: target ``today + 7d`` instead of today.
    *review*:    open the week file in ``$EDITOR`` and exit.

    Returns a CLI-style exit code.
    """
    mission_dir = _resolve_mission_dir()
    if mission_dir is None:
        print("⚠️  No existe el proyecto 'mission' en este workspace.")
        return 1

    target = date.today() + (timedelta(days=7) if next_week else timedelta())
    week_file = _week_file_path(mission_dir, target)

    if review:
        if not week_file.exists():
            print(f"⚠️  No hay archivo semanal para {_iso_week_label(target)}.")
            return 1
        import os
        os.system(f"$EDITOR '{week_file}'")
        return 0

    # Bootstrap or load the per-workspace template.
    template = _load_template(mission_dir)
    if template is None:
        template = _bootstrap_template_from_factory(mission_dir)

    # F3-F6 land here. Stub for F2.
    print(f"focus week: {_iso_week_label(target)} → {week_file}")
    print(f"  plantilla: anchor={template['projects_per_rail']['anchor']} "
          f"× {template['blocks_per_project']['anchor']} bloques · "
          f"duración {template['block_duration']} min")
    print("  (modos libre/plantilla/repetir pendientes — F3)")
    return 0

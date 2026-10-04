"""core.focus.template — plantilla per-workspace: parse, format, bootstrap."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Optional
from core.config import TEMPLATES_DIR
from core.focus.common import (
    _DAYS,
    _DAY_FROM_ES,
    _DAY_LABEL,
    _RAILS,
    _RAIL_EMOJI,
    _RAIL_LABEL,
    _TEMPLATE_FILENAME,
    _template_path,
)


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

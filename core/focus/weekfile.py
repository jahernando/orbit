"""core.focus.weekfile — hoja semanal: formato, parser y contador."""
from __future__ import annotations

import re
from datetime import date
from pathlib import Path
from typing import Optional
from core.focus.common import (
    _RAILS,
    _RAIL_EMOJI,
    _RAIL_LABEL,
    _iso_week_label,
    _week_bounds,
)


# ── Modo repetir (F6) ─────────────────────────────────────────────────────

def _parse_week_blocks_detailed(text: str) -> list[tuple[str, str, str]]:
    """Return [(rail, project, orbit_id), ...] from a focus week file."""
    out: list[tuple[str, str, str]] = []
    in_blocks = False
    current_rail: Optional[str] = None
    current_proj: Optional[str] = None
    for line in text.splitlines():
        s = line.strip()
        if s == "## Bloques":
            in_blocks = True
            continue
        if s.startswith("## ") and s != "## Bloques":
            in_blocks = False
            current_rail = None
            current_proj = None
            continue
        if not in_blocks:
            continue
        if s.startswith("### "):
            rest = s[4:].strip()
            for emoji, rail in _RAIL_FROM_EMOJI.items():
                if rest.startswith(emoji):
                    current_rail = rail
                    current_proj = rest[len(emoji):].strip()
                    break
            else:
                current_rail = None
                current_proj = None
            continue
        if current_rail is None or current_proj is None:
            continue
        m = _ORBIT_LINE_RE.search(s)
        if m:
            out.append((current_rail, current_proj, m.group(1)))
    return out


# ── Archivo semanal: 2026-WNN-focus.md ───────────────────────────────────

def _format_week_file(target: date, status: str,
                      rails_projects: dict[str, list[str]],
                      blocks_by_rail: dict[str, list[tuple[str, str]]]) -> str:
    """Compose the week file text. Counter is rendered as placeholder; F4 fills it."""
    week_label = _iso_week_label(target)
    monday, friday = _week_bounds(target)
    out = [f"# Focus {week_label}", "",
           f"- Fechas: {monday.isoformat()} → {friday.isoformat()}",
           f"- Status: {status}",
           "", "## Carriles", ""]
    for rail in _RAILS:
        projs = rails_projects.get(rail) or []
        body = ", ".join(f"[[{p}]]" for p in projs) if projs else "—"
        out.append(f"- {_RAIL_EMOJI[rail]} {_RAIL_LABEL[rail]}: {body}")
    out += ["", "## Bloques", ""]
    for rail in _RAILS:
        # Group blocks by project under each rail header.
        by_project: dict[str, list[str]] = {}
        for proj, oid in blocks_by_rail.get(rail, []):
            by_project.setdefault(proj, []).append(oid)
        for proj in rails_projects.get(rail, []):
            ids = by_project.get(proj, [])
            if not ids:
                continue
            out.append(f"### {_RAIL_EMOJI[rail]} {proj}")
            for oid in ids:
                out.append(f"- [orbit:{oid}]")
            out.append("")
    out += ["## Contador (autogenerado)", ""]
    for rail in _RAILS:
        total = len(blocks_by_rail.get(rail, []))
        out.append(f"- {_RAIL_EMOJI[rail]} {_RAIL_LABEL[rail].lower()}: "
                   f"0/{total}  (regenera con `orbit focus week`)")
    out += ["", "## Retrospectiva", "",
            "<!-- Apóyate en `orbit report --summary mission`. Preguntas guía:",
            "     · ¿Qué sostuvo la semana?",
            "     · ¿Qué cedió y por qué?",
            "     · ¿Qué pruebo distinto la W siguiente?",
            "-->",
            ""]
    return "\n".join(out)


def _write_week_file(week_file: Path, target: date, status: str,
                     rails_projects: dict[str, list[str]],
                     blocks_by_rail: dict[str, list[tuple[str, str]]]) -> None:
    """Write the week file to disk."""
    week_file.parent.mkdir(parents=True, exist_ok=True)
    week_file.write_text(_format_week_file(target, status,
                                            rails_projects, blocks_by_rail))


# ── Parser del fichero semanal + contador (F4) ───────────────────────────

_ORBIT_LINE_RE = re.compile(r"\[orbit:([0-9a-f]{8})\]")
_RAIL_FROM_EMOJI = {v: k for k, v in _RAIL_EMOJI.items()}


def _parse_week_file(text: str) -> dict:
    """Extract status + blocks-per-rail from a 2026-WNN-focus.md file.

    Devuelve dict::

        {
          "status": "normal" | "especial" | ...,
          "blocks_by_rail": {"anchor": [orbit_id, ...], "push": [...], "joy": [...]}
        }

    Identifica los IDs por la sección ``### <emoji> <project>`` bajo
    ``## Bloques``. El emoji al inicio del header determina el carril.
    """
    status = "normal"
    blocks_by_rail: dict[str, list[str]] = {r: [] for r in _RAILS}
    in_blocks = False
    current_rail: Optional[str] = None
    for line in text.splitlines():
        s = line.strip()
        m = re.match(r"^-\s+Status\s*:\s*(\S+)\s*$", s, re.IGNORECASE)
        if m:
            status = m.group(1).lower()
            continue
        if s == "## Bloques":
            in_blocks = True
            continue
        if s.startswith("## ") and s != "## Bloques":
            in_blocks = False
            current_rail = None
            continue
        if not in_blocks:
            continue
        if s.startswith("### "):
            # "### ⚓ paper-neutrinos" → rail = anchor
            rest = s[4:].strip()
            for emoji, rail in _RAIL_FROM_EMOJI.items():
                if rest.startswith(emoji):
                    current_rail = rail
                    break
            else:
                current_rail = None
            continue
        if current_rail is None:
            continue
        m = _ORBIT_LINE_RE.search(s)
        if m:
            blocks_by_rail[current_rail].append(m.group(1))
    return {"status": status, "blocks_by_rail": blocks_by_rail}


def _build_id_status_index(mission_dir: Path) -> dict[str, str]:
    """Map orbit_id → task status by reading mission/agenda.md once."""
    from core.log import resolve_file
    from core.agenda.io import _read_agenda
    agenda_path = resolve_file(mission_dir, "agenda")
    data = _read_agenda(agenda_path)
    idx: dict[str, str] = {}
    for t in data.get("tasks", []):
        oid = t.get("orbit_id")
        if oid:
            idx[oid] = t.get("status", "pending")
    return idx


def _build_id_task_index(mission_dir: Path) -> dict[str, dict]:
    """Map orbit_id → full task dict (date/time/desc/status). Mission only."""
    from core.log import resolve_file
    from core.agenda.io import _read_agenda
    agenda_path = resolve_file(mission_dir, "agenda")
    data = _read_agenda(agenda_path)
    idx: dict[str, dict] = {}
    for t in data.get("tasks", []):
        oid = t.get("orbit_id")
        if oid:
            idx[oid] = t
    return idx


def _format_counter_section(status: str,
                             blocks_by_rail: dict[str, list[str]],
                             id_status: dict[str, str]) -> list[str]:
    """Return the lines of the '## Contador (autogenerado)' section."""
    out = ["## Contador (autogenerado)", ""]
    is_especial = status == "especial"
    for rail in _RAILS:
        ids = blocks_by_rail.get(rail, [])
        total = len(ids)
        done = sum(1 for oid in ids if id_status.get(oid) == "done")
        label = _RAIL_LABEL[rail].lower()
        emoji = _RAIL_EMOJI[rail]
        if is_especial:
            out.append(f"- {emoji} {label}: — ({done}/{total} bloques)")
        elif total == 0:
            out.append(f"- {emoji} {label}: — (sin bloques)")
        else:
            out.append(f"- {emoji} {label}: {done}/{total}")
    out.append("")
    return out


def _regenerate_counter(week_file: Path, mission_dir: Path) -> tuple[int, int]:
    """Rewrite the '## Contador (autogenerado)' section in place.

    Returns (done_total, total). Idempotent: if the week file has no
    counter section, one is appended before '## Retrospectiva'.
    """
    text = week_file.read_text()
    parsed = _parse_week_file(text)
    id_status = _build_id_status_index(mission_dir)
    new_section = _format_counter_section(parsed["status"],
                                           parsed["blocks_by_rail"], id_status)

    lines = text.splitlines()
    # Locate section boundaries.
    start = end = None
    for i, ln in enumerate(lines):
        if ln.strip() == "## Contador (autogenerado)":
            start = i
            # Find next ## header (or EOF).
            for j in range(i + 1, len(lines)):
                if lines[j].startswith("## "):
                    end = j
                    break
            else:
                end = len(lines)
            break

    if start is None:
        # No counter section yet — insert before ## Retrospectiva, or at EOF.
        retro = next((i for i, ln in enumerate(lines)
                       if ln.strip() == "## Retrospectiva"), None)
        if retro is not None:
            new_lines = lines[:retro] + new_section + lines[retro:]
        else:
            new_lines = lines + [""] + new_section
    else:
        # Replace [start:end). Preserve trailing blank line.
        new_lines = lines[:start] + new_section + lines[end:]
    week_file.write_text("\n".join(new_lines) + ("\n" if text.endswith("\n") else ""))

    total = sum(len(v) for v in parsed["blocks_by_rail"].values())
    done = sum(1 for ids in parsed["blocks_by_rail"].values()
               for oid in ids if id_status.get(oid) == "done")
    return done, total

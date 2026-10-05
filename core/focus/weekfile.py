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
    monday, sunday = _week_bounds(target)
    out = [f"# Focus {week_label}", "",
           f"- Fechas: {monday.isoformat()} → {sunday.isoformat()}",
           f"- Status: {status}",
           f"- Balance: {_BALANCE_PENDING}",
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
                out.append(f"- {_SYM_OPEN} [orbit:{oid}]")
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


def _append_blocks_to_week_file(week_file: Path,
                                rails_projects: dict[str, list[str]],
                                new_blocks: dict[str, list[tuple[str, str]]]
                                ) -> None:
    """Añade bloques a una hoja existente sin reescribirla.

    Conserva todo lo demás (retrospectiva, símbolos con fecha, balance,
    texto libre): solo reescribe las líneas de ``## Carriles`` y mete
    ``- ⬜ [orbit:id]`` al final de la sección ``### <emoji> <proj>``
    (que se crea al final de ``## Bloques`` si no existe).
    """
    lines = week_file.read_text().splitlines()

    def _section(title: str) -> tuple[Optional[int], int]:
        start = next((i for i, ln in enumerate(lines)
                      if ln.strip() == title), None)
        if start is None:
            return None, len(lines)
        end = next((j for j in range(start + 1, len(lines))
                    if lines[j].startswith("## ")), len(lines))
        return start, end

    # Carriles: reescribe la línea de cada carril.
    for rail in _RAILS:
        projs = rails_projects.get(rail) or []
        body = ", ".join(f"[[{p}]]" for p in projs) if projs else "—"
        new_line = f"- {_RAIL_EMOJI[rail]} {_RAIL_LABEL[rail]}: {body}"
        start, end = _section("## Carriles")
        if start is None:
            break
        for i in range(start + 1, end):
            if lines[i].strip().startswith(f"- {_RAIL_EMOJI[rail]} "):
                lines[i] = new_line
                break

    start, end = _section("## Bloques")
    if start is None:  # hoja sin Bloques: créala antes del contador / EOF
        cut, _ = _section("## Contador (autogenerado)")
        at = cut if cut is not None else len(lines)
        lines[at:at] = ["## Bloques", ""]
    for rail in _RAILS:
        for proj, oid in new_blocks.get(rail, []):
            start, end = _section("## Bloques")
            header = f"### {_RAIL_EMOJI[rail]} {proj}"
            h = next((i for i in range(start + 1, end)
                      if lines[i].strip() == header), None)
            entry = f"- {_SYM_OPEN} [orbit:{oid}]"
            if h is None:
                # Nueva sección al final de Bloques (tras el último no-vacío).
                at = end
                while at > start + 1 and not lines[at - 1].strip():
                    at -= 1
                lines[at:at] = ["", header, entry]
                continue
            # Tras la última línea de bloque de la sección.
            at = h + 1
            while at < end and lines[at].strip().startswith("- "):
                at += 1
            lines.insert(at, entry)
    week_file.write_text("\n".join(lines) + "\n")


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


def _parse_rails(text: str) -> dict[str, list[str]]:
    """Carril → proyectos de ``## Carriles`` (``- ⚓ Anchor: [[a]], [[b]]``)."""
    out: dict[str, list[str]] = {r: [] for r in _RAILS}
    in_section = False
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("## "):
            in_section = s == "## Carriles"
            continue
        if not in_section or not s.startswith("- "):
            continue
        for emoji, rail in _RAIL_FROM_EMOJI.items():
            if s.startswith(f"- {emoji}"):
                out[rail] = re.findall(r"\[\[([^\]|]+)", s)
                break
    return out


# ── Estado por bloque (símbolos) + balance ───────────────────────────────
#
# Cada bloque lleva un símbolo escrito por orbit (no casillas clicables):
#   ⬜ abierto · ✅ hecho · ❌ no hecho / drop · ❔ no encontrado
# opcionalmente seguido de la fecha de cierre ``MM-DD`` (la pone el hook de
# done/drop; el balance no la conoce). Hojas viejas: ``- [orbit:id]`` sin
# símbolo → se leen como abiertas.
#
# ``- Balance: pendiente`` / ``- Balance: hecho YYYY-MM-DD``. Sin la línea =
# hoja legacy (anterior a F2): se balancea una vez sin hacer drop.

_SYM_OPEN, _SYM_DONE, _SYM_DROP, _SYM_MISSING = "⬜", "✅", "❌", "❔"
_SYM_TO_STATUS = {_SYM_OPEN: "pending", _SYM_DONE: "done",
                  _SYM_DROP: "cancelled", _SYM_MISSING: "missing"}
_BALANCE_PENDING = "pendiente"
_BALANCE_DONE = "hecho"

_BLOCK_LINE_RE = re.compile(
    r"^(\s*)-\s+(?:([⬜✅❌❔])\s+(?:(\d{2}-\d{2})\s+)?)?"
    r"\[orbit:([0-9a-f]{8})\](.*)$")
_BALANCE_RE = re.compile(r"^-\s+Balance\s*:\s*(\S+)(?:\s+(\d{4}-\d{2}-\d{2}))?\s*$",
                         re.IGNORECASE)
_STATUS_LINE_RE = re.compile(r"^-\s+Status\s*:", re.IGNORECASE)


def _parse_balance(text: str) -> Optional[str]:
    """Return ``"pendiente"`` / ``"hecho"`` or None for a legacy sheet."""
    for line in text.splitlines():
        m = _BALANCE_RE.match(line.strip())
        if m:
            return m.group(1).lower()
    return None


def _is_balanced(text: str) -> bool:
    return _parse_balance(text) == _BALANCE_DONE


def _set_balance_line(text: str, value: str) -> str:
    """Write ``- Balance: <value>``; insert after ``- Status:`` if absent."""
    lines = text.splitlines()
    for i, ln in enumerate(lines):
        if _BALANCE_RE.match(ln.strip()):
            lines[i] = f"- Balance: {value}"
            break
    else:
        at = next((i + 1 for i, ln in enumerate(lines)
                   if _STATUS_LINE_RE.match(ln.strip())), None)
        if at is None:  # sin Status: tras el título
            at = 1 if lines and lines[0].startswith("# ") else 0
        lines.insert(at, f"- Balance: {value}")
    return "\n".join(lines) + ("\n" if text.endswith("\n") else "")


def _parse_block_states(text: str) -> dict[str, str]:
    """Map orbit_id → status leído de los símbolos de ``## Bloques``."""
    out: dict[str, str] = {}
    in_blocks = False
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("## "):
            in_blocks = s == "## Bloques"
            continue
        if not in_blocks:
            continue
        m = _BLOCK_LINE_RE.match(line)
        if m:
            out[m.group(4)] = _SYM_TO_STATUS[m.group(2) or _SYM_OPEN]
    return out


def _effective_status_index(text: str,
                            id_status: dict[str, str]) -> dict[str, str]:
    """Status de cada bloque según la fuente que manda.

    Hoja balanceada → los símbolos de la hoja (verdad histórica: los
    bloques pueden estar ya archivados o con drop). Sin balancear → la
    agenda de mission (``id_status``).
    """
    if _is_balanced(text):
        return _parse_block_states(text)
    return id_status


def _sync_block_symbols(text: str, id_status: dict[str, str],
                        final: bool = False) -> str:
    """Reescribe el símbolo de cada bloque desde ``id_status``.

    *final* (balance): abierto → ❌, ausente en la agenda → ❔. Sin
    *final* (vivo): abierto → ⬜, ausente → conserva lo que hubiera.
    La fecha ``MM-DD`` se conserva mientras el símbolo no cambie.
    """
    out = []
    in_blocks = False
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("## "):
            in_blocks = s == "## Bloques"
        m = _BLOCK_LINE_RE.match(line) if in_blocks else None
        if not m:
            out.append(line)
            continue
        indent, old_sym, old_date, oid, rest = m.groups()
        st = id_status.get(oid)
        if st == "done":
            sym = _SYM_DONE
        elif st == "cancelled":
            sym = _SYM_DROP
        elif st is None:
            sym = _SYM_MISSING if final else (old_sym or _SYM_OPEN)
        else:
            sym = _SYM_DROP if final else _SYM_OPEN
        stamp = f" {old_date}" if old_date and sym == old_sym else ""
        out.append(f"{indent}- {sym}{stamp} [orbit:{oid}]{rest}")
    return "\n".join(out) + ("\n" if text.endswith("\n") else "")


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

    Hoja sin balancear: refresca también los símbolos desde la agenda.
    Hoja balanceada: no toca los símbolos y cuenta desde ellos.
    """
    text = week_file.read_text()
    if not any(ln.strip() == "## Bloques" for ln in text.splitlines()):
        return 0, 0          # hoja solo de focus day: sin contador semanal
    parsed = _parse_week_file(text)
    if _is_balanced(text):
        id_status = _parse_block_states(text)
    else:
        id_status = _build_id_status_index(mission_dir)
        text = _sync_block_symbols(text, id_status)
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

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
import secrets
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

from core.config import TEMPLATES_DIR
from core.project import _find_new_project, _is_new_project, _strip_type_emoji
from core.config import iter_project_dirs


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
    title = f"{_RAIL_EMOJI[rail]} [[{project_name}]] · focus {week_label}"
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


def _run_mode_libre(mission_dir: Path, template: dict,
                    target: date, week_file: Path) -> int:
    """Interactive free-mode planning. Asks projects/blocks rail by rail,
    creates the tasks in mission/agenda.md, writes the week file.
    """
    available = _list_available_projects(mission_dir)
    if not available:
        print("⚠️  No hay otros proyectos en el workspace para asignar a "
              "los carriles. Crea al menos uno con `orbit project new`.")
        return 1

    week_label = _iso_week_label(target)
    monday, _ = _week_bounds(target)
    duration = template["block_duration"]

    print(f"\nProyectos disponibles: {', '.join(available)}\n")

    rails_projects: dict[str, list[str]] = {r: [] for r in _RAILS}
    blocks_by_rail: dict[str, list[tuple[str, str]]] = {r: [] for r in _RAILS}

    for rail in _RAILS:
        emoji = _RAIL_EMOJI[rail]
        label = _RAIL_LABEL[rail]
        print(f"{emoji} {label}")
        while True:
            try:
                raw = input(f"  proyecto (Enter para terminar {label}): ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                return 1
            if not raw:
                break
            canonical = _resolve_project_name(raw, available)
            if canonical is None:
                continue
            if canonical in rails_projects[rail]:
                print(f"    ⚠️  {canonical} ya está en {label} esta semana")
                continue
            rails_projects[rail].append(canonical)

            default_blocks = template["blocks_per_project"][rail]
            try:
                raw = input(f"    bloques [{default_blocks}]: ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                return 1
            try:
                n_blocks = int(raw) if raw else default_blocks
            except ValueError:
                print(f"    ⚠️  No es un entero: {raw!r} — usando {default_blocks}")
                n_blocks = default_blocks
            if n_blocks <= 0:
                continue

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
                    blocks_by_rail[rail].append((canonical, orbit_id))
                    print(f"    ✓ {emoji} [{canonical}] {d.isoformat()} ⏰{t}")
        print()

    total = sum(len(v) for v in blocks_by_rail.values())
    if total == 0:
        print("⚠️  No se creó ningún bloque. Archivo semanal no escrito.")
        return 1

    _write_week_file(week_file, target, "normal",
                     rails_projects, blocks_by_rail)
    print(f"\n✓ {total} bloques creados en mission/agenda.md")
    print(f"✓ Archivo semanal: {week_file}")
    return 0


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
            "(rellena el viernes apoyándote en `orbit report --summary mission`)",
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

    if week_file.exists():
        # F7 will offer regenerate / open / add / abort. For now: regenerate
        # the counter in place (F4) and let the user open the file if needs
        # more.
        done, total = _regenerate_counter(week_file, mission_dir)
        print(f"✓ {week_file.name} ya existe — contador regenerado: "
              f"{done}/{total} bloques completados.")
        print(f"   Edita el fichero a mano o lanza con --review para abrirlo.")
        return 0

    # F5 will introduce the mode selector (libre/plantilla/repetir).
    # F3 ships only the free mode.
    print(f"focus week — {_iso_week_label(target)}")
    rc = _run_mode_libre(mission_dir, template, target, week_file)
    if rc == 0 and week_file.exists():
        # Counter starts at 0/N by construction, but regenerate to keep the
        # single source of truth (avoids drift if the user did `task done`
        # on a block before this command finished).
        _regenerate_counter(week_file, mission_dir)
    return rc

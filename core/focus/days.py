"""core.focus.days — sección ``## Días`` de la hoja semanal (focus day).

Cada día con focus es una subsección dentro de la hoja de su semana::

    ## Días

    ### 2026-10-05 · lunes
    - ✅ 10-05 [orbit:9c0d1e2f] [[🌀paper-neutrinos]] · Revisar borrador
    - ⬜ [orbit:1a2b3c4d] [[📚catedra]] · Enviar informe

Las tareas son **reales** (de cualquier proyecto local): focus no las crea
ni las borra. Identidad = ``(proyecto, orbit_id)``; el título es una copia
para leer. Al balancear el día (primer save de un día posterior) los
símbolos se congelan (✅ / ❌ / ❔) y la cabecera gana ``· balance n/m``;
desde ahí el hook de done/drop ya no la toca.
"""
from __future__ import annotations

import re
from datetime import date
from typing import Callable, Optional
from core.focus.common import _iso_week_label, _week_bounds
from core.focus.weekfile import (
    _BALANCE_PENDING,
    _BLOCK_LINE_RE,
    _SYM_DONE,
    _SYM_DROP,
    _SYM_MISSING,
    _SYM_OPEN,
    _SYM_TO_STATUS,
)


DAYS_SECTION = "## Días"
MAX_DAY_ITEMS = 5
_WEEKDAYS_ES = ("lunes", "martes", "miércoles", "jueves", "viernes",
                "sábado", "domingo")
_DAY_HEADER_RE = re.compile(r"^###\s+(\d{4}-\d{2}-\d{2})\b(.*)$")
_BALANCE_TAG_RE = re.compile(r"·\s*balance\s+(\d+)/(\d+)")
_PROJECT_RE = re.compile(r"\[\[([^\]|]+)")
# Secciones ante las que se inserta ``## Días`` si no existe.
_DAYS_BEFORE = ("## Contador (autogenerado)", "## Retrospectiva")


def _day_header(d: date) -> str:
    return f"### {d.isoformat()} · {_WEEKDAYS_ES[d.weekday()]}"


def _day_line(oid: str, project: str, title: str) -> str:
    return f"- {_SYM_OPEN} [orbit:{oid}] [[{project}]] · {title}"


def _minimal_sheet(target: date) -> str:
    """Hoja de una semana sin focus week: solo cabecera, Días y retro."""
    monday, sunday = _week_bounds(target)
    return "\n".join([
        f"# Focus {_iso_week_label(target)}", "",
        f"- Fechas: {monday.isoformat()} → {sunday.isoformat()}",
        "- Status: normal",
        f"- Balance: {_BALANCE_PENDING}", "",
        DAYS_SECTION, "",
        "## Retrospectiva", "",
    ])


def _is_day_only(text: str) -> bool:
    """Hoja creada por ``focus day`` sin planificación semanal."""
    heads = {ln.strip() for ln in text.splitlines() if ln.startswith("## ")}
    return "## Bloques" not in heads and "## Carriles" not in heads


# ── Parser ────────────────────────────────────────────────────────────────

def _parse_days(text: str) -> list[dict]:
    """``[{date, balanced, items: [{sym, stamp, oid, project, title}]}]``."""
    days: list[dict] = []
    in_days = False
    cur: Optional[dict] = None
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("## "):
            in_days = s == DAYS_SECTION
            cur = None
            continue
        if not in_days:
            continue
        m = _DAY_HEADER_RE.match(s)
        if m:
            cur = {"date": date.fromisoformat(m.group(1)),
                   "balanced": bool(_BALANCE_TAG_RE.search(m.group(2))),
                   "items": []}
            days.append(cur)
            continue
        b = _BLOCK_LINE_RE.match(line)
        if cur is not None and b:
            rest = b.group(5)
            pm = _PROJECT_RE.search(rest)
            title = rest.split("·", 1)[1].strip() if "·" in rest else ""
            cur["items"].append({
                "sym": b.group(2) or _SYM_OPEN, "stamp": b.group(3),
                "oid": b.group(4), "project": pm.group(1) if pm else None,
                "title": title})
    return days


def _find_day(text: str, d: date) -> Optional[dict]:
    return next((x for x in _parse_days(text) if x["date"] == d), None)


def _frozen_line_indices(text: str) -> set[int]:
    """Índices de línea dentro de días ya balanceados (el hook no toca)."""
    out: set[int] = set()
    in_days = frozen = False
    for i, line in enumerate(text.splitlines()):
        s = line.strip()
        if s.startswith("## "):
            in_days, frozen = s == DAYS_SECTION, False
            continue
        if not in_days:
            continue
        m = _DAY_HEADER_RE.match(s)
        if m:
            frozen = bool(_BALANCE_TAG_RE.search(m.group(2)))
            continue
        if frozen:
            out.add(i)
    return out


# ── Escritura ─────────────────────────────────────────────────────────────

def _section_bounds(lines: list[str], title: str) -> tuple[Optional[int], int]:
    start = next((i for i, ln in enumerate(lines) if ln.strip() == title), None)
    if start is None:
        return None, len(lines)
    end = next((j for j in range(start + 1, len(lines))
                if lines[j].startswith("## ")), len(lines))
    return start, end


def _write_day(text: str, d: date, new_lines: list[str],
               replace: bool = False) -> str:
    """Añade (o con *replace* sustituye) las líneas del día *d*."""
    lines = text.splitlines()
    start, end = _section_bounds(lines, DAYS_SECTION)
    if start is None:
        at = next((i for i, ln in enumerate(lines)
                   if ln.strip() in _DAYS_BEFORE), len(lines))
        lines[at:at] = [DAYS_SECTION, ""]
        start, end = _section_bounds(lines, DAYS_SECTION)

    header = _day_header(d)
    h = next((i for i in range(start + 1, end)
              if (m := _DAY_HEADER_RE.match(lines[i].strip()))
              and m.group(1) == d.isoformat()), None)
    if h is None:
        # Sustituye los blancos finales de la sección por el bloque nuevo,
        # que lleva su propio blanco antes y después.
        at = end
        while at > start + 1 and not lines[at - 1].strip():
            at -= 1
        lines[at:end] = ["", header, *new_lines, ""]
    else:
        last = h + 1
        while last < end and lines[last].strip().startswith("- "):
            last += 1
        if replace:
            lines[h:last] = [header, *new_lines]
        else:
            lines[last:last] = new_lines
    return "\n".join(lines) + "\n"


# ── Balance de días ───────────────────────────────────────────────────────

def _project_status_lookup() -> Callable[[Optional[str], str], Optional[str]]:
    """``lookup(project_dir_name, oid) → status`` con caché por proyecto."""
    from core.config import iter_federated_project_dirs
    from core.agenda.io import _read_agenda
    from core.log import resolve_file
    dirs = {p.name: p for p in iter_federated_project_dirs(include_federated=False)}
    cache: dict[str, dict[str, str]] = {}

    def _index(name: str) -> dict[str, str]:
        if name not in cache:
            idx: dict[str, str] = {}
            p = dirs.get(name)
            path = resolve_file(p, "agenda") if p is not None else None
            if path is not None and path.exists():
                data = _read_agenda(path)
                for key in ("tasks", "milestones"):
                    for it in data.get(key) or []:
                        if it.get("orbit_id"):
                            idx[it["orbit_id"]] = it.get("status", "pending")
            cache[name] = idx
        return cache[name]

    def lookup(project: Optional[str], oid: str) -> Optional[str]:
        return _index(project).get(oid) if project else None
    return lookup


def _balance_days(text: str, today: date,
                  lookup: Callable[[Optional[str], str], Optional[str]]
                  ) -> tuple[str, list[dict]]:
    """Congela los días anteriores a *today* aún sin balance.

    Abierto → ❌, ausente → ❔; la fecha ``MM-DD`` del hook se conserva si el
    símbolo no cambia. Devuelve ``(text, [{date, done, total}])``.
    """
    lines = text.splitlines()
    results: list[dict] = []
    in_days = False
    cur: Optional[dict] = None
    for i, line in enumerate(lines):
        s = line.strip()
        if s.startswith("## "):
            in_days, cur = s == DAYS_SECTION, None
            continue
        if not in_days:
            continue
        m = _DAY_HEADER_RE.match(s)
        if m:
            d = date.fromisoformat(m.group(1))
            if d < today and not _BALANCE_TAG_RE.search(m.group(2)):
                cur = {"date": d, "done": 0, "total": 0, "header": i}
                results.append(cur)
            else:
                cur = None
            continue
        b = _BLOCK_LINE_RE.match(line) if cur is not None else None
        if not b:
            continue
        indent, old_sym, stamp, oid, rest = b.groups()
        pm = _PROJECT_RE.search(rest)
        st = lookup(pm.group(1) if pm else None, oid)
        sym = {"done": _SYM_DONE, "cancelled": _SYM_DROP,
               "pending": _SYM_DROP}.get(st, _SYM_MISSING)
        keep = f" {stamp}" if stamp and sym == old_sym else ""
        lines[i] = f"{indent}- {sym}{keep} [orbit:{oid}]{rest}"
        cur["total"] += 1
        cur["done"] += sym == _SYM_DONE
    for r in results:
        h = r.pop("header")
        lines[h] = f"{_day_header(r['date'])} · balance {r['done']}/{r['total']}"
    out = "\n".join(lines) + ("\n" if text.endswith("\n") else "")
    return out, results


def _day_counts(day: dict) -> tuple[int, int]:
    done = sum(1 for it in day["items"]
               if _SYM_TO_STATUS[it["sym"]] == "done")
    return done, len(day["items"])


def _transplant_day_sheet(old_text: str, new_text: str) -> str:
    """Planificar la semana sobre una hoja que solo tenía días.

    *new_text* es la hoja recién escrita por ``focus week``; se le injertan
    la sección ``## Días`` y la retrospectiva de *old_text*.
    """
    old, new = old_text.splitlines(), new_text.splitlines()
    for title in ("## Retrospectiva", DAYS_SECTION):
        s, e = _section_bounds(old, title)
        if s is None:
            continue
        chunk = old[s:e]
        ns, ne = _section_bounds(new, title)
        if ns is not None:
            new[ns:ne] = chunk
        else:
            at = next((i for i, ln in enumerate(new)
                       if ln.strip() in _DAYS_BEFORE), len(new))
            new[at:at] = chunk
    return "\n".join(new) + "\n"

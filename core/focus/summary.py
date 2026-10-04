"""core.focus.summary — ``orbit focus summary``: éxito de focus en el tiempo.

Una fila por semana ISO: siete celdas de día (focus day) y, aparte, la
celda de la semana (bloques de focus week). Cada celda es un **nivel
0–5** = ``round(5 · hechas / total)`` — proporción, así 3/3 es un 5.
Sin focus ese día / esa semana → celda vacía.

El nivel se escribe como dígito (legible sin color) y en un terminal se
pinta además con fondo gris, más oscuro cuanto más alto (escala de
luminosidad, como el calendario de carga de ``day fup``).

Fuente: días/semanas balanceados → símbolos de la hoja (verdad
histórica); sin balancear (hoy, o antes del primer save) → la verdad en
vivo de los proyectos.
"""
from __future__ import annotations

import contextlib
import io
import sys
from datetime import date, timedelta
from typing import Optional
from core.focus.common import _resolve_mission_dir, _week_file_path
from core.focus.days import _day_counts, _parse_days, _project_status_lookup
from core.focus.weekfile import (
    _SYM_TO_STATUS,
    _build_id_status_index,
    _effective_status_index,
    _parse_week_file,
)


_BG = (None, 254, 251, 247, 243, 238)     # nivel 0..5 → gris ANSI-256
_FG = (None, 232, 232, 232, 255, 255)
_RESET = "\x1b[0m"
_WEEKDAYS = ("lun", "mar", "mié", "jue", "vie", "sáb", "dom")
_CELL = 5


def level(done: int, total: int) -> Optional[int]:
    """Nivel 0–5 por proporción; None si no hubo focus (total 0)."""
    if total <= 0:
        return None
    return int(5 * done / total + 0.5)


# ── Datos ─────────────────────────────────────────────────────────────────

def _collect(mission_dir, mondays: list, today: date) -> list:
    """``[{monday, label, days: {date: (done, total)}, week: (d, t)|None}]``."""
    id_status = None
    lookup = None
    rows = []
    for monday in mondays:
        wf = _week_file_path(mission_dir, monday)
        y, w, _ = monday.isocalendar()
        row = {"monday": monday, "label": f"W{w:02d}", "year": y,
               "days": {}, "week": None}
        rows.append(row)
        if not wf.exists():
            continue
        text = wf.read_text()
        if _parse_week_file(text)["status"] == "off":
            continue
        ids = [oid for oids in _parse_week_file(text)["blocks_by_rail"].values()
               for oid in oids]
        if ids:
            if id_status is None:
                id_status = _build_id_status_index(mission_dir)
            st = _effective_status_index(text, id_status)
            row["week"] = (sum(1 for o in ids if st.get(o) == "done"), len(ids))
        for day in _parse_days(text):
            if day["date"] > today or not day["items"]:
                continue
            if day["balanced"]:
                row["days"][day["date"]] = _day_counts(day)
                continue
            lookup = lookup or _project_status_lookup()
            done = sum(1 for it in day["items"]
                       if lookup(it["project"], it["oid"]) == "done")
            row["days"][day["date"]] = (done, len(day["items"]))
    return rows


# ── Presentación ──────────────────────────────────────────────────────────

def _paint(text: str, lv: Optional[int], ansi: bool) -> str:
    if not ansi or lv is None:
        return text
    if _BG[lv] is None:
        return f"\x1b[2m{text}{_RESET}"
    return f"\x1b[48;5;{_BG[lv]}m\x1b[38;5;{_FG[lv]}m{text}{_RESET}"


def _cell(counts: Optional[tuple], is_today: bool, ansi: bool) -> str:
    if counts is None:
        return " " * _CELL
    lv = level(*counts)
    body = f"{lv}"
    text = f"[{body:^3}]" if is_today else f" {body:^3} "
    return _paint(text, lv, ansi)


def render(rows: list, today: date, *, ansi: bool = True) -> list:
    lines = ["── 🎯 focus · éxito por día y semana (nivel 0–5 = hechas/total)"]
    head = " ".join(f"{d:^{_CELL}}" for d in _WEEKDAYS)
    lines.append(f"  {'':5} {head}  │ semana")
    for r in rows:
        cells = []
        for i in range(7):
            d = r["monday"] + timedelta(days=i)
            cells.append(_cell(r["days"].get(d), d == today, ansi))
        if r["week"] is None:
            wk = "—"
        else:
            done, total = r["week"]
            lv = level(done, total)
            wk = _paint(f" {lv} ", lv, ansi) + f" {done}/{total} bloques"
        lines.append(f"  {r['label']:5} {' '.join(cells)}  │ {wk}")

    day_counts = [c for r in rows for c in r["days"].values()]
    week_counts = [r["week"] for r in rows if r["week"]]
    lines.append("")
    if day_counts:
        d_done = sum(c[0] for c in day_counts)
        d_tot = sum(c[1] for c in day_counts)
        full = sum(1 for c in day_counts if level(*c) == 5)
        lines.append(f"  Días con focus: {len(day_counts)} · tareas "
                     f"✅ {d_done}/{d_tot} · días a 5: {full}")
    if week_counts:
        w_done = sum(c[0] for c in week_counts)
        w_tot = sum(c[1] for c in week_counts)
        lines.append(f"  Semanas con bloques: {len(week_counts)} · bloques "
                     f"✅ {w_done}/{w_tot}")
    if not day_counts and not week_counts:
        lines.append("  Sin focus en el periodo.")
    legend = "  ".join(_paint(f" {lv} ", lv, ansi) for lv in range(6))
    lines.append(f"  {legend}   0 = nada hecho · 5 = todo · [ ] = hoy")
    return lines


def run_focus_summary(weeks: int = 8, today: Optional[date] = None) -> int:
    """Pinta las últimas *weeks* semanas (la actual incluida)."""
    with contextlib.redirect_stdout(io.StringIO()):
        mission_dir = _resolve_mission_dir()
    if mission_dir is None:
        print("⚠️  No existe el proyecto 'mission' en este workspace.")
        return 1
    today = today or date.today()
    weeks = max(1, weeks)
    this_monday = today - timedelta(days=today.weekday())
    mondays = [this_monday - timedelta(days=7 * k)
               for k in range(weeks - 1, -1, -1)]
    rows = _collect(mission_dir, mondays, today)
    ansi = sys.stdout.isatty()
    print("\n".join(render(rows, today, ansi=ansi)))
    return 0

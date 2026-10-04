"""core.focus.year — vista anual ``mission/notes/YYYY-focus.md``."""
from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Optional
from core.focus.common import (
    _RAILS,
    _RAIL_EMOJI,
    _RAIL_LABEL,
    _resolve_mission_dir,
)
from core.focus.weekfile import (
    _build_id_status_index,
    _effective_status_index,
    _parse_week_blocks_detailed,
    _parse_week_file,
)


# ── Vista anual: agregación + render ─────────────────────────────────────

def _weeks_in_iso_year(year: int) -> int:
    """Return the number of ISO weeks in *year* (52 or 53).

    Trick: Dec 28 always falls in the last ISO week of the calendar year.
    """
    return date(year, 12, 28).isocalendar()[1]


def _year_file_path(mission_dir: Path, year: int) -> Path:
    """Return ``mission/notes/<YYYY>-focus.md``."""
    return mission_dir / "notes" / f"{year}-focus.md"


def _collect_year(mission_dir: Path, year: int) -> list[dict]:
    """Aggregate per-week focus state across *year*.

    Returns a list with one entry per ISO week (W01..W52/53). Each entry::

        {
          "week_label": "2026-W22",
          "week_num":   22,
          "status":     "normal" | "especial" | "—",   # "—" if no file
          "has_file":   bool,
          "rails":      {"anchor": [(project, [done?, ...]), ...],
                         "push":   [...],
                         "joy":    [...]},
        }

    A block is "done" iff its status is ``done``: from the sheet's symbols
    once the week is balanced (historical truth), from ``mission/agenda.md``
    otherwise. Order of projects within a rail is preserved
    from the week file.
    """
    n_weeks = _weeks_in_iso_year(year)
    id_status = _build_id_status_index(mission_dir)
    rows: list[dict] = []
    for w in range(1, n_weeks + 1):
        label = f"{year}-W{w:02d}"
        week_file = mission_dir / "notes" / f"{label}-focus.md"
        if not week_file.exists():
            rows.append({
                "week_label": label,
                "week_num":   w,
                "status":     "—",
                "has_file":   False,
                "rails":      {r: [] for r in _RAILS},
            })
            continue
        text = week_file.read_text()
        parsed = _parse_week_file(text)
        detailed = _parse_week_blocks_detailed(text)
        status_of = _effective_status_index(text, id_status)
        rails: dict[str, list[tuple[str, list[bool]]]] = {r: [] for r in _RAILS}
        idx_in_rail: dict[tuple[str, str], int] = {}
        for rail, proj, oid in detailed:
            done = status_of.get(oid) == "done"
            key = (rail, proj)
            if key in idx_in_rail:
                rails[rail][idx_in_rail[key]][1].append(done)
            else:
                idx_in_rail[key] = len(rails[rail])
                rails[rail].append((proj, [done]))
        rows.append({
            "week_label": label,
            "week_num":   w,
            "status":     parsed["status"],
            "has_file":   True,
            "rails":      rails,
        })
    return rows


_STATUS_ICON = {"normal": "🟢", "especial": "🟡", "—": "—"}


def _render_rail_cell(rail_data: list[tuple[str, list[bool]]]) -> str:
    """Render the contents of one rail cell in the year table.

    Empty rail → ``—``. One project → ``[[proj]] 🍅❌``. Multiple projects
    → one line per project joined with ``<br>`` (renders inside markdown
    tables in both Obsidian and GitHub).
    """
    if not rail_data:
        return "—"
    parts = []
    for proj, done_list in rail_data:
        marks = "".join("🍅" if d else "❌" for d in done_list)
        parts.append(f"[[{proj}]] {marks}")
    return "<br>".join(parts)


def _year_totals(rows: list[dict]) -> dict[str, tuple[int, int]]:
    """Sum (done, total) per rail across all rows whose status ≠ especial.

    Semanas especiales se excluyen del agregado anual: por diseño sus
    targets están aparcados (memoria [[project-orbit-focus]]).
    """
    totals = {r: [0, 0] for r in _RAILS}
    for row in rows:
        if row["status"] == "especial":
            continue
        for rail, projs in row["rails"].items():
            for _, done_list in projs:
                totals[rail][0] += sum(done_list)
                totals[rail][1] += len(done_list)
    return {r: (totals[r][0], totals[r][1]) for r in _RAILS}


def _week_dates_short(year: int, week_num: int) -> str:
    """Return ``MM-DD/MM-DD`` for Mon/Sun of the given ISO week."""
    mon = date.fromisocalendar(year, week_num, 1)
    sun = date.fromisocalendar(year, week_num, 7)
    return f"{mon.strftime('%m-%d')}/{sun.strftime('%m-%d')}"


def _format_year_file(rows: list[dict], year: int) -> str:
    """Compose the year-view markdown.

    Layout::

        # Focus · año YYYY
        <leyenda>
        | Semana | Fechas | Status | Anchor | Push | Joy |
        |---|---|---|---|---|---|
        | [[2026-W21-focus\\|W21]] | 05-18/05-22 | 🟢 | [[paper]] 🍅🍅 | … | — |
        | W22                     | 05-25/05-29 | —  | —              | — | — |
        …
        ## Totales
        - ⚓ anchor: 18/24 🍅 (75%)
        …

    Weeks without a focus file render the label as plain text (no
    wikilink) to avoid broken wikilinks in Obsidian.
    """
    out = [
        f"# Focus · año {year}",
        "",
        "Vista anual de bloques focus. 🍅 = bloque hecho · ❌ = no hecho.",
        "Status: 🟢 normal · 🟡 especial · — sin planificar.",
        "",
        "| Semana | Fechas | Status | Anchor | Push | Joy |",
        "|---|---|---|---|---|---|",
    ]
    for row in rows:
        wlabel = f"W{row['week_num']:02d}"
        if row["has_file"]:
            week_cell = f"[[{row['week_label']}-focus\\|{wlabel}]]"
        else:
            week_cell = wlabel
        fechas = _week_dates_short(year, row["week_num"])
        status_icon = _STATUS_ICON.get(row["status"], row["status"])
        cells = [_render_rail_cell(row["rails"][r]) for r in _RAILS]
        out.append(f"| {week_cell} | {fechas} | {status_icon} | "
                   f"{cells[0]} | {cells[1]} | {cells[2]} |")

    out += ["", "## Totales", "",
            "(semanas `especial` excluidas del agregado)",
            ""]
    totals = _year_totals(rows)
    for rail in _RAILS:
        d, t = totals[rail]
        pct = f"({100 * d // t}%)" if t > 0 else "(—)"
        out.append(f"- {_RAIL_EMOJI[rail]} {_RAIL_LABEL[rail].lower()}: "
                   f"{d}/{t} 🍅 {pct}")
    out.append("")
    return "\n".join(out)


def _refresh_year_silent(mission_dir: Path, year: int) -> None:
    """Side-effect refresh of the year view; never raises to caller."""
    try:
        run_focus_year(year=year, silent=True)
    except Exception as e:
        print(f"⚠️  No se pudo refrescar la vista anual: {e}")


def run_focus_year(year: Optional[int] = None, silent: bool = False) -> int:
    """Regenerate the year view ``mission/notes/<YYYY>-focus.md``.

    *year*: ISO year to render. ``None`` → current year.
    *silent*: skip the success print (used by ``run_focus_week`` to refresh
              the year file as a side-effect without noise).

    Returns a CLI-style exit code.
    """
    mission_dir = _resolve_mission_dir()
    if mission_dir is None:
        if not silent:
            print("⚠️  No existe el proyecto 'mission' en este workspace.")
        return 1
    yr = year if year is not None else date.today().year
    rows = _collect_year(mission_dir, yr)
    text = _format_year_file(rows, yr)
    out_path = _year_file_path(mission_dir, yr)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(text)
    if not silent:
        totals = _year_totals(rows)
        summary = " · ".join(
            f"{_RAIL_EMOJI[r]} {totals[r][0]}/{totals[r][1]}"
            for r in _RAILS
        )
        print(f"✓ Archivo anual: {out_path.relative_to(mission_dir.parent)} ({summary})")
    return 0

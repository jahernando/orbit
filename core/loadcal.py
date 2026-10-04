"""loadcal — calendario de carga: cuántas citas tiene cada día.

Lo pinta ``day fup`` encima del prompt para elegir a qué día mandar un ⏩
mirando dónde hay hueco (ADR-056). Cinco niveles por número de citas:

    nula 0 · baja 1–4 · media 5–9 · alta 10–14 · muy alta ≥15

Qué cuenta:

* **hoy** — lo que lista ``day``: citas de hoy + vencidas + ⏩ ≤ hoy. Es
  donde se acumula el arrastre de días anteriores.
* **días futuros** — citas que caen ese día (eventos de varios días y
  ocurrencias de recurrentes incluidos) + citas con un ⏩ en esa fecha.

Sin recordatorios, como en ``day``. Una cita con fecha y un ⏩ en otro día
cuenta en los dos.

En un terminal la intensidad es el **fondo gris** de la celda (más oscuro,
más carga); fuera de él (tests, tubería) un glifo ``· ░ ▒ ▓ █``. Los dos
son escala de luminosidad, no de tono. El número de citas va entre
paréntesis solo si ``orbit.json`` lo pide: ``"load_calendar": {"counts": true}``.

En markdown (``render_md``, para el calendario y la agenda del secretario)
la intensidad es el mismo gris, como ``<span style="background:…">``; el
número de citas va en el ``title`` (al pasar el ratón). Los días con un
hito abierto van **subrayados** (la negrita no se distingue sobre gris).
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

LEVEL_TOPS = (0, 4, 9, 14)               # nivel = primer tope >= n; si no, 4
LEVEL_NAMES = ("nula", "1-4", "5-9", "10-14", "≥15")
GLYPHS = ("·", "░", "▒", "▓", "█")
_BG = (None, 252, 248, 243, 238)          # gris de fondo ANSI-256
_FG = (None, 232, 232, 255, 255)          # texto negro sobre claro, blanco sobre oscuro
_RESET = "\x1b[0m"

_WEEKDAYS = ("lun", "mar", "mié", "jue", "vie", "sáb", "dom")
_MONTHS = ("", "enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
           "agosto", "septiembre", "octubre", "noviembre", "diciembre")


def level(n: int) -> int:
    for i, top in enumerate(LEVEL_TOPS):
        if n <= top:
            return i
    return len(LEVEL_TOPS)


def show_counts() -> bool:
    from core.config import _load_orbit_json
    try:
        return bool((_load_orbit_json().get("load_calendar") or {})
                    .get("counts", False))
    except Exception:
        return False


# ── Carga ─────────────────────────────────────────────────────────────────

def weeks_from(today: date, n_weeks: int = 4) -> list:
    """Semana en curso + *n_weeks* siguientes, de lunes a domingo."""
    monday = today - timedelta(days=today.weekday())
    return [[monday + timedelta(days=7 * w + i) for i in range(7)]
            for w in range(n_weeks + 1)]


def _open_items(dirs: list) -> list:
    """``[(kind, item, {fechas ⏩})]`` de las citas abiertas, sin recordatorios."""
    from core.agenda.display import item_followups
    from core.agenda_cmds import _read_agenda
    from core.log import resolve_file
    from core.triage import _SECTION_OF, _is_open

    items = []
    for project_dir in dirs:
        agenda = resolve_file(project_dir, "agenda")
        if not agenda.exists():
            continue
        data = _read_agenda(agenda)
        for kind, key in _SECTION_OF.items():
            if kind == "reminder":
                continue
            for it in data.get(key) or []:
                if _is_open(it, kind):
                    fups = {f["date"] for f in item_followups(it) if f["date"]}
                    items.append((kind, it, fups))
    return items


def milestone_days(dirs: list, today: date, days: list) -> set:
    """Días de *days* desde hoy en que cae un hito abierto."""
    from core.triage import occurs_on
    ms = [it for kind, it, _ in _open_items(dirs) if kind == "ms"]
    return {d for d in days if d >= today
            and any(occurs_on(it, "ms", d) for it in ms)}


def day_loads(dirs: list, today: date, days: list,
              today_count: Optional[int] = None) -> dict:
    """``{fecha: nº de citas}`` para los días de *days* desde hoy.

    *today_count*: lo que ya contó ``day`` (evita recoger dos veces).
    """
    from core.triage import collect, number_rows, occurs_on

    if today_count is None:
        today_count = len(number_rows(collect(dirs, today, full=False)))
    items = _open_items(dirs)
    out = {}
    for d in days:
        if d < today:
            continue
        if d == today:
            out[d] = today_count
            continue
        iso = d.isoformat()
        out[d] = sum(1 for kind, it, fups in items
                     if iso in fups or occurs_on(it, kind, d))
    return out


# ── Presentación ──────────────────────────────────────────────────────────

def _title(weeks: list, today: date) -> str:
    last = weeks[-1][-1]
    if today.month == last.month:
        span = _MONTHS[today.month]
    else:
        span = f"{_MONTHS[today.month]}–{_MONTHS[last.month]}"
    return f"{span} {last.year} · carga"


def _paint(text: str, lv: int, bold: bool) -> str:
    b = "\x1b[1m" if bold else ""
    if _BG[lv] is None:
        return f"{b}\x1b[2m{text}{_RESET}" if not bold else f"{b}{text}{_RESET}"
    return f"\x1b[48;5;{_BG[lv]}m\x1b[38;5;{_FG[lv]}m{b}{text}{_RESET}"


def _width(counts: bool, ansi: bool) -> int:
    return 4 + (5 if counts else 0) + (0 if ansi else 2)


def _cell(d: date, loads: dict, today: date, counts: bool, ansi: bool) -> str:
    """Celda de ancho fijo: ``[03]``/`` 05 `` (+ ``(nn)``) (+ glifo sin ANSI)."""
    width = _width(counts, ansi)
    if d < today or d not in loads:
        return " " * width
    n = loads[d]
    lv = level(n)
    body = f"{d.day:02d}" + (f" ({n:>2})" if counts else "")
    if not ansi:
        body += f" {GLYPHS[lv]}"
    text = f"[{body}]" if d == today else f" {body} "
    return _paint(text, lv, d == today) if ansi else text


def render(loads: dict, today: date, weeks: list, *, counts: bool = False,
           ansi: bool = True) -> list:
    """Líneas del calendario de carga. *ansi*=False → glifos en vez de fondo."""
    width = _width(counts, ansi)
    gap = "  "
    lines = [f"── 📅 {_title(weeks, today)}"]
    lines.append("  " + gap.join(f"{w:^{width}}" for w in _WEEKDAYS))
    for week in weeks:
        if all(d < today for d in week):
            continue
        lines.append("  " + gap.join(_cell(d, loads, today, counts, ansi)
                                     for d in week))
    legend = []
    for lv, name in enumerate(LEVEL_NAMES):
        if ansi:
            legend.append(_paint(f" {name} ", lv, False))
        else:
            legend.append(f"{GLYPHS[lv]} {name}")
    lines.append("  " + "  ".join(legend) + "    [ ] = hoy")
    return lines


# ── Markdown ──────────────────────────────────────────────────────────────

_HEX = {232: "#080808", 238: "#444444", 243: "#767676", 248: "#a8a8a8",
        252: "#d0d0d0", 255: "#eeeeee"}
_MD_WEEKDAYS = ("Lu", "Ma", "Mi", "Ju", "Vi", "Sa", "Do")


# Subrayado como borde del propio <span>: Obsidian no pinta <u> en las
# tablas, pero sí respeta el style del span (el gris se ve).
_MD_UNDERLINE = "border-bottom:2px solid currentColor"


def _md_span(text: str, lv: int, title: str = "",
             underline: bool = False) -> str:
    tip = f' title="{title}"' if title else ""
    styles = []
    if _BG[lv] is not None:
        styles.append(f"background:{_HEX[_BG[lv]]};color:{_HEX[_FG[lv]]};"
                      "padding:0 4px;border-radius:3px")
    if underline:
        styles.append(_MD_UNDERLINE)
    if not styles:
        return f"<span{tip}>{text}</span>" if tip else text
    return f'<span style="{";".join(styles)}"{tip}>{text}</span>'


def md_cell(d: date, loads: dict, today: date, ms_days: set = frozenset()) -> str:
    """Celda markdown: gris de carga, subrayado si hay hito, ``[dd]`` hoy.

    Días pasados (o sin carga calculada) salen tenues, sin intensidad.
    """
    label = f"{d.day:02d}"
    if d < today or d not in loads:
        return f'<span style="opacity:.45">{label}</span>'
    n = loads[d]
    if d == today:
        label = f"[{label}]"
    tip = f"{n} cita" + ("s" if n != 1 else "")
    if d in ms_days:
        tip += " · 🏁 hito"
    return _md_span(label, level(n), tip, underline=d in ms_days)


def md_legend() -> str:
    parts = [_md_span(f"{name}", lv) for lv, name in enumerate(LEVEL_NAMES)]
    return ("Carga (citas/día): " + " ".join(parts)
            + f" · <span style=\"{_MD_UNDERLINE}\">dd</span> = hito · [ ] = hoy")


def render_md(loads: dict, today: date, weeks: list,
              ms_days: set = frozenset(), *, week_numbers: bool = True,
              month: Optional[int] = None,
              first: Optional[date] = None,
              last: Optional[date] = None) -> list:
    """Tabla markdown de *weeks* (listas lunes→domingo).

    *month*: si se da, los días de otro mes quedan en blanco (vista mensual).
    *first*/*last*: los días fuera de [first, last] quedan en blanco.
    """
    head = (["Wk"] if week_numbers else []) + list(_MD_WEEKDAYS)
    lines = ["| " + " | ".join(head) + " |",
             "|" + "|".join([":-:"] * len(head)) + "|"]
    for week in weeks:
        cells = []
        if week_numbers:
            ref = next((d for d in week if month is None or d.month == month),
                       week[0])
            cells.append(f"**W{ref.isocalendar()[1]:02d}**")
        for d in week:
            if ((month is not None and d.month != month)
                    or (first is not None and d < first)
                    or (last is not None and d > last)):
                cells.append("")
            else:
                cells.append(md_cell(d, loads, today, ms_days))
        lines.append("| " + " | ".join(cells) + " |")
    return lines

"""views/secretary/_agenda_table — helpers compartidos para tablas de agenda.

Usado por `agenda_today.py` (un día) y `agenda_next.py` (N días). Centraliza
el modelo de datos + render de filas markdown para que las dos vistas
mantengan exactamente la misma estructura visual.

Estructura de la tabla:
    | emoji | Inicio | Fin | overlap | Descripción | Proyecto |

- Inicio/Fin: derivados con defaults (event 1h, task 15min) si falta tramo.
- Overlap: `░ ▒ ▓` según solapamiento dentro del día (0 / 1 / 2+).
- Proyecto: markdown link a la `<project>-agenda.md`; federados como texto
  con brackets escapados (otro vault, no linkable).
"""

from pathlib import Path
from typing import Optional


KIND_EMOJI = {
    "events":     "📅",
    "tasks":      "☐",
    "milestones": "🏁",
    "reminders":  "💬",
}

DEFAULT_MIN = {
    "events":     60,
    "tasks":      15,
    "milestones": None,
    "reminders":  None,
}

OVERLAP_CHARS = ("░", "▒", "▓")


def start_min(item) -> int:
    t = item.get("time") or ""
    if not t:
        return 0
    h, m = map(int, t.split("-")[0].split(":"))
    return h * 60 + m


def duration_min(item, default_min) -> int:
    t = item.get("time") or ""
    if not t:
        return 0
    if "-" in t:
        a, b = t.split("-", 1)
        ah, am = map(int, a.split(":"))
        bh, bm = map(int, b.split(":"))
        return max((bh * 60 + bm) - (ah * 60 + am), 0)
    return default_min or 0


def time_pair(item, default_min):
    t = item.get("time") or ""
    if not t:
        return ("", "")
    if "-" in t:
        a, b = t.split("-", 1)
        return (a, b)
    if default_min is None:
        return (t, "")
    h, m = map(int, t.split(":"))
    total = h * 60 + m + default_min
    eh, em = divmod(total, 60)
    return (t, f"{eh % 24:02d}:{em:02d}")


def detect_overlaps(items):
    """items: lista de (kind, item, ...). Returns dict idx → overlap count.

    Reminders excluidos (sin duración conceptual).
    """
    spans = []
    for entry in items:
        kind, item = entry[0], entry[1]
        if kind == "reminders":
            spans.append(None)
            continue
        d = duration_min(item, DEFAULT_MIN.get(kind))
        if d <= 0:
            spans.append(None)
            continue
        s = start_min(item)
        spans.append((s, s + d))
    counts = {i: 0 for i in range(len(items))}
    for i, a in enumerate(spans):
        if a is None:
            continue
        for j in range(i + 1, len(spans)):
            b = spans[j]
            if b is None:
                continue
            if a[0] < b[1] and b[0] < a[1]:
                counts[i] += 1
                counts[j] += 1
    return counts


def overlap_char(count: int) -> str:
    if count <= 0:
        return OVERLAP_CHARS[0]
    if count == 1:
        return OVERLAP_CHARS[1]
    return OVERLAP_CHARS[2]


def proj_link_md(project_dir) -> str:
    """Markdown link to <project>-agenda.md desde 📊panel/secretary/.

    Federados → texto con brackets escapados, sin link (otro vault).
    """
    from core.config import get_federation_emoji, is_federated, ORBIT_HOME
    from core.log import resolve_file
    if is_federated(project_dir):
        emoji = get_federation_emoji(project_dir)
        return f"{emoji} \\[{project_dir.name}\\]"
    agenda_path = resolve_file(project_dir, "agenda")
    if not agenda_path.exists():
        return f"\\[{project_dir.name}\\]"
    try:
        rel = agenda_path.relative_to(ORBIT_HOME)
    except ValueError:
        return f"\\[{project_dir.name}\\]"
    return f"[{project_dir.name}](../../{rel})"


TABLE_HEADER = (
    "| | | Inicio | Fin | Descripción | Proyecto |\n"
    "|---|---|--------|-----|-------------|----------|"
)


def _desc_with_event_indicators(kind: str, item: dict) -> str:
    """Returns item.desc + (for events) [📋](agenda) [🚪](room) [✉️](email)
    indicators as markdown clickable icons. Escapes pipe for table safety."""
    desc = (item.get("desc") or "").replace("|", "\\|")
    if kind == "events":
        try:
            from core.agenda.display import event_indicators
            ind = event_indicators(item, markdown=True)
        except Exception:
            ind = ""
        if ind:
            desc = f"{desc}{ind}"
    return desc


def render_day_rows(items) -> list:
    """items: lista de (kind, item, project_dir, proj_md), ya filtrados a un día.

    Returns lista de strings (líneas markdown) — header + filas. Si no hay
    items, devuelve lista vacía. Sort por hora; sin-hora al final.

    Layout (6 cols): emoji-de-kind | overlap-marker | Inicio | Fin | Desc | Proyecto.
    Reminders sin overlap (instantáneos). Events incluyen indicadores
    `[📋] [🚪] [✉️]` (markdown clickables) tras la descripción si tienen
    URLs de agenda/room/email.
    """
    if not items:
        return []
    timed = [it for it in items if it[1].get("time")]
    untimed = [it for it in items if not it[1].get("time")]
    timed.sort(key=lambda x: start_min(x[1]))
    overlaps = detect_overlaps(timed)
    lines = [TABLE_HEADER]
    for idx, (kind, item, _pdir, proj_md) in enumerate(timed):
        emoji = KIND_EMOJI[kind]
        start, end = time_pair(item, DEFAULT_MIN.get(kind))
        ov = "" if kind == "reminders" else overlap_char(overlaps.get(idx, 0))
        desc = _desc_with_event_indicators(kind, item)
        lines.append(f"| {emoji} | {ov} | {start} | {end} | {desc} | {proj_md} |")
    for kind, item, _pdir, proj_md in untimed:
        emoji = KIND_EMOJI[kind]
        desc = _desc_with_event_indicators(kind, item)
        # untimed: overlap/Inicio/Fin vacíos.
        lines.append(f"| {emoji} |  |  |  | {desc} | {proj_md} |")
    return lines


def _add_item_spanning(by_day: dict, entry, item_start: str, item_end: str,
                       df_date, dt_date) -> None:
    """Add `entry` a by_day para cada día en [item_start, item_end] ∩ [df, dt].
    Para events multi-día (con `end`), aparecerá en cada día del rango."""
    from datetime import date as _date, timedelta
    try:
        s = max(_date.fromisoformat(item_start), df_date)
        e = min(_date.fromisoformat(item_end),   dt_date)
    except ValueError:
        return
    cur = s
    while cur <= e:
        by_day.setdefault(cur.isoformat(), []).append(entry)
        cur += timedelta(days=1)


def collect_items_by_day(date_from, date_to, include_federated: bool = True) -> dict:
    """Returns ``{date_str: [(kind, item, project_dir, proj_md)]}`` for items
    cuyo rango temporal intersecta ``[date_from, date_to]``. Filters
    done/cancelled.

    Tres extensiones sobre "una entrada un día":
    - **Multi-día events** (con `end` set): aparecen en cada día de su
      rango ``[date, end]`` (no sólo el día de inicio). Útil para
      conferencias/viajes de varios días.
    - **Recurrencia**: expansión con `_expand_recurrences` para las 4
      citas (incluyendo reminders; `_collect_data` omite reminders pero
      aquí los queremos).
    - **Recurrencia × multi-día**: ocurrencias virtuales preservan
      `end` (offset del original), así que cada virtual también se
      expande por sus días.
    """
    from datetime import date as _date
    from core.agenda.io import _read_agenda
    from core.agenda_view import _resolve_dirs, _expand_recurrences
    from core.log import resolve_file

    df_date = date_from if hasattr(date_from, "isoformat") else _date.fromisoformat(date_from)
    dt_date = date_to   if hasattr(date_to,   "isoformat") else _date.fromisoformat(date_to)

    by_day: dict = {}
    for project_dir in _resolve_dirs(None, include_federated=include_federated):
        agenda_path = resolve_file(project_dir, "agenda")
        if not agenda_path.exists():
            continue
        data = _read_agenda(agenda_path)
        proj_md = proj_link_md(project_dir)
        for kind in ("events", "tasks", "milestones", "reminders"):
            for item in data.get(kind, []):
                if item.get("status") in ("done", "cancelled"):
                    continue
                d = item.get("date")
                if not d:
                    continue
                entry = (kind, item, project_dir, proj_md)
                # Base occurrence (con rango si multi-día events).
                end_d = item.get("end") or d
                _add_item_spanning(by_day, entry, d, end_d, df_date, dt_date)
                # Recurring: expandir ocurrencias virtuales dentro del rango.
                if item.get("recur"):
                    for vi in _expand_recurrences(item, df_date, dt_date):
                        v_entry = (kind, vi, project_dir, proj_md)
                        v_end = vi.get("end") or vi["date"]
                        _add_item_spanning(by_day, v_entry, vi["date"], v_end,
                                            df_date, dt_date)
    return by_day

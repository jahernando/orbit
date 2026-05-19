"""views/secretary/today.py — vista timeline del día (hoy).

Renderiza events, tasks, milestones y reminders de hoy ordenados por hora
ascendente. Items sin hora al final. Reminders informativos (fila tenue,
sin barra de color). HTML inline + CSS `<style>` embebido para la barra
vertical por kind.

Defaults de duración (cuando el item no especifica `HH:MM-HH:MM`):
- event:     1 h
- task:      15 min
- milestone: sin hora (siempre untimed)
- reminder:  sin duración (renderizado como punto informativo)

Viewer puro: lee agenda.md de todos los proyectos (locales + federados
read-only), escribe el .md, return.

Limitaciones conocidas del primer cut:
- Wikilinks `[[...]]` y markdown en `desc` quedan literales dentro de las
  celdas HTML (Obsidian no procesa md dentro de `<td>` por defecto).
- Recurrentes cuya base date es anterior y "tocan hoy" no aparecen
  (`_read_agenda` no expande recurrencias; lo hace `_collect_data`).
"""

import html
from datetime import date as _date
from pathlib import Path

from views import autogen_banner


# (emoji, default-duration-min). Sin color por kind: el kind se distingue
# por su emoji en col 1 (📅 ✅ 🏁 💬), no por color de la barra.
# default_min=None ⇒ sin duración derivable (milestones, reminders).
_KIND_META = {
    "events":     ("📅", 60),
    "tasks":      ("✅", 15),
    "milestones": ("🏁", None),
    "reminders":  ("💬", None),
}


# Puntitos para la barra (estilo crono): densidad = overlap.
# Accesible para usuarios daltónicos (sin color en la barra).
#   - 0 overlaps → ░ (shade ligero)
#   - 1 overlap  → ▒
#   - 2+ overlaps → ▓
_BAR_CHARS = ("░", "▒", "▓")


def _bar_char(overlap_count: int) -> str:
    if overlap_count <= 0:
        return _BAR_CHARS[0]
    if overlap_count == 1:
        return _BAR_CHARS[1]
    return _BAR_CHARS[2]


_CSS = """\
<style>
.orbit-today { font-family: -apple-system, system-ui, sans-serif; max-width: 900px; }
.orbit-today table { border-collapse: collapse; width: 100%; margin: 0; }
.orbit-today td { padding: 6px 8px; vertical-align: top; border: none; }
.orbit-today tr.row td { border-top: 1px solid #ececec; }
.orbit-today .icon { width: 1.4em; font-size: 1em; color: #555; padding-right: 4px; }
.orbit-today .bar { width: 1.2em; font-family: monospace; font-size: 1.1em; color: #555; text-align: center; line-height: 1.1; padding: 0 4px; }
.orbit-today .t-start { white-space: nowrap; color: #555; font-variant-numeric: tabular-nums; font-size: 0.95em; width: 4.5em; }
.orbit-today .t-end { white-space: nowrap; color: #999; font-variant-numeric: tabular-nums; font-size: 0.95em; width: 4.5em; }
.orbit-today .desc { color: #222; width: 100%; line-height: 1.35; }
.orbit-today .link { white-space: nowrap; color: #888; font-size: 0.85em; }
.orbit-today .link a { color: inherit; text-decoration: none; }
.orbit-today .link a:hover { text-decoration: underline; }
.orbit-today tr.reminder .icon, .orbit-today tr.reminder .t-start, .orbit-today tr.reminder .desc { color: #888; font-style: italic; }
.orbit-today .untimed { margin-top: 1.5em; padding-top: 0.5em; border-top: 1px dashed #ddd; }
.orbit-today .untimed-title { color: #888; font-size: 0.9em; margin-bottom: 0.3em; }
.orbit-today .empty { color: #888; font-style: italic; }
</style>
"""


# Pixels per minute for proportional row height. 1px/min ⇒ 1h event = 60px tall.
_PX_PER_MIN = 1
# Floor so short tasks/reminders no quedan colapsados visualmente.
_MIN_ROW_PX = 28


def _start_time(item) -> str:
    t = item.get("time") or ""
    return t.split("-")[0]


def _time_pair(item, default_min):
    """Return (start, end) strings or (start, '') for items sin tramo derivable."""
    t = item.get("time") or ""
    if not t:
        return ("", "")
    if "-" in t:
        a, b = t.split("-", 1)
        return (a, b)
    if default_min is None:
        return (t, "")  # reminders or items sin default
    h, m = map(int, t.split(":"))
    total = h * 60 + m + default_min
    eh, em = divmod(total, 60)
    return (t, f"{eh % 24:02d}:{em:02d}")


def _duration_min(item, default_min) -> int:
    """Minutes of duration. 0 for reminders/items sin default."""
    t = item.get("time") or ""
    if not t:
        return 0
    if "-" in t:
        a, b = t.split("-", 1)
        ah, am = map(int, a.split(":"))
        bh, bm = map(int, b.split(":"))
        delta = (bh * 60 + bm) - (ah * 60 + am)
        return max(delta, 0)
    return default_min or 0


def _row_height_style(duration_min: int) -> str:
    """Inline style for proportional row height. Min floor for legibility."""
    h = max(duration_min * _PX_PER_MIN, _MIN_ROW_PX)
    return f' style="height:{h}px"'


def _link_html(proj_tag: str, agenda_href: str) -> str:
    """Project tag wrapped en <a class="internal-link"> si hay agenda; texto
    plano si federado. La clase `internal-link` hace que Obsidian intercepte
    el href como navegación de vault (no como URL externa)."""
    tag = html.escape(proj_tag)
    if agenda_href:
        href_esc = html.escape(agenda_href)
        return (
            f'<a class="internal-link" '
            f'href="{href_esc}" data-href="{href_esc}">{tag}</a>'
        )
    return tag


def _row_html(kind, item, proj_tag, agenda_href, emoji, default_min,
              overlap_count=0) -> str:
    """Render 6-col row: icon | bar | t-start | t-end | desc | link."""
    desc = html.escape(item.get("desc") or "")
    link = _link_html(proj_tag, agenda_href)
    start, end = _time_pair(item, default_min)
    duration = _duration_min(item, default_min)
    if kind == "reminders":
        # Reminders: sin barra, sin end, altura mínima, italic.
        return (
            f'<tr class="row reminder"{_row_height_style(0)}>'
            f'<td class="icon">{emoji}</td>'
            f'<td class="bar"></td>'
            f'<td class="t-start">{html.escape(start)}</td>'
            f'<td class="t-end"></td>'
            f'<td class="desc">{desc}</td>'
            f'<td class="link">{link}</td>'
            f'</tr>\n'
        )
    char = _bar_char(overlap_count)
    return (
        f'<tr class="row"{_row_height_style(duration)}>'
        f'<td class="icon">{emoji}</td>'
        f'<td class="bar">{char}</td>'
        f'<td class="t-start">{html.escape(start)}</td>'
        f'<td class="t-end">{html.escape(end)}</td>'
        f'<td class="desc">{desc}</td>'
        f'<td class="link">{link}</td>'
        f'</tr>\n'
    )


def _start_min(item) -> int:
    t = item.get("time") or ""
    if not t:
        return 0
    s = t.split("-")[0]
    h, m = map(int, s.split(":"))
    return h * 60 + m


def _detect_overlap_counts(enriched):
    """enriched: list de (kind, item, proj_tag, default_min). Devuelve un
    dict idx → cuántos items solapan con éste. Reminders excluidos."""
    spans = []
    for idx, (kind, item, _tag, default_min) in enumerate(enriched):
        if kind == "reminders":
            spans.append(None)
            continue
        s = _start_min(item)
        d = _duration_min(item, default_min)
        if d <= 0:
            spans.append(None)
            continue
        spans.append((s, s + d, idx))
    counts = {i: 0 for i in range(len(enriched))}
    for i, a in enumerate(spans):
        if a is None: continue
        s_i, e_i, _ = a
        for j in range(i + 1, len(spans)):
            b = spans[j]
            if b is None: continue
            s_j, e_j, _ = b
            if s_i < e_j and s_j < e_i:
                counts[i] += 1
                counts[j] += 1
    return counts


def _untimed_row_html(kind, item, proj_tag, agenda_href, emoji) -> str:
    """Render 6-col untimed row: icon | (no bar) | (no time) | (no time) | desc | link."""
    desc = html.escape(item.get("desc") or "")
    link = _link_html(proj_tag, agenda_href)
    return (
        f'<tr>'
        f'<td class="icon">{emoji}</td>'
        f'<td class="bar"></td>'
        f'<td class="t-start"></td>'
        f'<td class="t-end"></td>'
        f'<td class="desc">{desc}</td>'
        f'<td class="link">{link}</td>'
        f'</tr>\n'
    )


def _agenda_href(project_dir) -> str:
    """Relative href desde 📊panel/secretary/today.md a <project>-agenda.md.
    Devuelve '' para federados (viven en otro vault, no son linkables)."""
    from core.config import ORBIT_HOME, is_federated
    from core.log import resolve_file
    if is_federated(project_dir):
        return ""
    agenda_path = resolve_file(project_dir, "agenda")
    if not agenda_path.exists():
        return ""
    try:
        rel = agenda_path.relative_to(ORBIT_HOME)
    except ValueError:
        return ""
    return "../../" + str(rel)


def generate(out_path: Path) -> None:
    """Escribe la vista timeline del día en out_path."""
    from core.agenda.io import _read_agenda
    from core.agenda_view import _fed_tag, _resolve_dirs
    from core.log import resolve_file

    today = _date.today()
    today_str = today.isoformat()
    timed = []    # (sort_key, kind, item, proj_tag, agenda_href)
    untimed = []  # (kind, item, proj_tag, agenda_href)

    for project_dir in _resolve_dirs(None, include_federated=True):
        agenda_path = resolve_file(project_dir, "agenda")
        if not agenda_path.exists():
            continue
        data = _read_agenda(agenda_path)
        proj_tag = _fed_tag(project_dir)
        href = _agenda_href(project_dir)
        for kind in ("events", "tasks", "milestones", "reminders"):
            for item in data.get(kind, []):
                if item.get("status") in ("done", "cancelled"):
                    continue
                if item.get("date") != today_str:
                    continue
                if item.get("time"):
                    timed.append((_start_time(item), kind, item, proj_tag, href))
                else:
                    untimed.append((kind, item, proj_tag, href))

    timed.sort(key=lambda x: x[0])

    # Detección de overlaps (post-sort, sólo items con duración).
    enriched = [(kind, item, proj_tag, _KIND_META[kind][1])
                for _, kind, item, proj_tag, _ in timed]
    overlap_counts = _detect_overlap_counts(enriched)

    parts = [
        autogen_banner("secretary.today"),
        f"# 📅 Hoy — {today.isoformat()}\n\n",
        _CSS,
        '<div class="orbit-today">\n',
    ]

    if not timed and not untimed:
        parts.append('<p class="empty">No hay citas para hoy.</p>\n')
    else:
        if timed:
            parts.append('<table>\n')
            for idx, (_, kind, item, proj_tag, href) in enumerate(timed):
                emoji, default_min = _KIND_META[kind]
                parts.append(_row_html(kind, item, proj_tag, href, emoji,
                                       default_min,
                                       overlap_counts.get(idx, 0)))
            parts.append('</table>\n')
        if untimed:
            parts.append('<div class="untimed">\n')
            parts.append('<div class="untimed-title">Sin hora</div>\n')
            parts.append('<table>\n')
            for kind, item, proj_tag, href in untimed:
                emoji, _default_min = _KIND_META[kind]
                parts.append(_untimed_row_html(kind, item, proj_tag, href, emoji))
            parts.append('</table>\n')
            parts.append('</div>\n')

    parts.append('</div>\n')
    out_path.write_text("".join(parts))

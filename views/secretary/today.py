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

from views.secretary import AUTOGEN_BANNER


# (emoji, bar-color, default-duration-min). default_min=None ⇒ no bar.
_KIND_META = {
    "events":     ("📅", "#d94f37", 60),
    "tasks":      ("✅", "#3f7bd9", 15),
    "milestones": ("🏁", "#9b59b6", None),
    "reminders":  ("💬", None,      None),
}


_CSS = """\
<style>
.orbit-today { font-family: -apple-system, system-ui, sans-serif; max-width: 760px; }
.orbit-today table { border-collapse: collapse; width: 100%; margin: 0; }
.orbit-today td { padding: 6px 10px; vertical-align: top; border: none; }
.orbit-today tr.row td { border-top: 1px solid #ececec; }
.orbit-today .time { white-space: nowrap; color: #555; font-variant-numeric: tabular-nums; font-size: 0.95em; min-width: 7em; }
.orbit-today .bar { width: 4px; min-width: 4px; padding: 0; border-radius: 2px; }
.orbit-today .content { width: 100%; }
.orbit-today .tag { color: #888; font-size: 0.85em; margin-right: 6px; }
.orbit-today .desc { color: #222; }
.orbit-today tr.reminder .time, .orbit-today tr.reminder .desc { color: #888; font-style: italic; }
.orbit-today .untimed { margin-top: 1.5em; padding-top: 0.5em; border-top: 1px dashed #ddd; }
.orbit-today .untimed-title { color: #888; font-size: 0.9em; margin-bottom: 0.3em; }
.orbit-today .empty { color: #888; font-style: italic; }
</style>
"""


def _start_time(item) -> str:
    t = item.get("time") or ""
    return t.split("-")[0]


def _time_display(item, default_min) -> str:
    t = item.get("time") or ""
    if not t:
        return ""
    if "-" in t:
        a, b = t.split("-", 1)
        return f"{a} – {b}"
    if default_min is None:
        return t
    h, m = map(int, t.split(":"))
    total = h * 60 + m + default_min
    eh, em = divmod(total, 60)
    return f"{t} – {eh % 24:02d}:{em:02d}"


def _row_html(kind, item, proj_tag, emoji, color, default_min) -> str:
    desc = html.escape(item.get("desc") or "")
    tag = html.escape(proj_tag)
    if kind == "reminders":
        time_disp = html.escape(_time_display(item, default_min))
        return (
            f'<tr class="row reminder">'
            f'<td class="time">{time_disp}</td>'
            f'<td class="bar"></td>'
            f'<td class="content"><span class="tag">{tag}</span>'
            f'<span class="desc">{emoji} {desc}</span></td></tr>\n'
        )
    time_disp = html.escape(_time_display(item, default_min))
    return (
        f'<tr class="row">'
        f'<td class="time">{time_disp}</td>'
        f'<td class="bar" style="background:{color}"></td>'
        f'<td class="content"><span class="tag">{tag}</span>'
        f'<span class="desc">{emoji} {desc}</span></td></tr>\n'
    )


def _untimed_row_html(kind, item, proj_tag, emoji) -> str:
    desc = html.escape(item.get("desc") or "")
    tag = html.escape(proj_tag)
    return (
        f'<tr><td class="content">'
        f'<span class="tag">{tag}</span>'
        f'<span class="desc">{emoji} {desc}</span>'
        f'</td></tr>\n'
    )


def generate(out_path: Path) -> None:
    """Escribe la vista timeline del día en out_path."""
    from core.agenda.io import _read_agenda
    from core.agenda_view import _fed_tag, _resolve_dirs
    from core.log import resolve_file

    today = _date.today()
    today_str = today.isoformat()
    timed = []   # (sort_key, kind, item, proj_tag)
    untimed = []  # (kind, item, proj_tag)

    for project_dir in _resolve_dirs(None, include_federated=True):
        agenda_path = resolve_file(project_dir, "agenda")
        if not agenda_path.exists():
            continue
        data = _read_agenda(agenda_path)
        proj_tag = _fed_tag(project_dir)
        for kind in ("events", "tasks", "milestones", "reminders"):
            for item in data.get(kind, []):
                if item.get("status") in ("done", "cancelled"):
                    continue
                if item.get("date") != today_str:
                    continue
                if item.get("time"):
                    timed.append((_start_time(item), kind, item, proj_tag))
                else:
                    untimed.append((kind, item, proj_tag))

    timed.sort(key=lambda x: x[0])

    parts = [
        AUTOGEN_BANNER,
        f"# 📅 Hoy — {today.isoformat()}\n\n",
        _CSS,
        '<div class="orbit-today">\n',
    ]

    if not timed and not untimed:
        parts.append('<p class="empty">No hay citas para hoy.</p>\n')
    else:
        if timed:
            parts.append('<table>\n')
            for _, kind, item, proj_tag in timed:
                emoji, color, default_min = _KIND_META[kind]
                parts.append(_row_html(kind, item, proj_tag, emoji, color, default_min))
            parts.append('</table>\n')
        if untimed:
            parts.append('<div class="untimed">\n')
            parts.append('<div class="untimed-title">Sin hora</div>\n')
            parts.append('<table>\n')
            for kind, item, proj_tag in untimed:
                emoji, _color, _dmin = _KIND_META[kind]
                parts.append(_untimed_row_html(kind, item, proj_tag, emoji))
            parts.append('</table>\n')
            parts.append('</div>\n')

    parts.append('</div>\n')
    out_path.write_text("".join(parts))

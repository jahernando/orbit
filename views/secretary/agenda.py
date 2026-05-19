"""views/secretary/agenda.py — agenda diaria + próxima como hot único.

Hot del workspace: el viewer que se regenera tras cualquier mutación de cita
(via `_run_full_refresh_coalesced` en F2). Absorbe lo que antes vivía en
panel.md / today.md / agenda-today.md / agenda-next.md / decisions-next.md.

Layout:

    > 🗓 Hoy: 📅N eventos · ✅N tareas · ⚠️N vencidas · ⏩N por triar
    > 🏁 Próximos 30 días: N hitos   ← solo si N>0

    ## 📅 Hoy — martes 19/05
    | tabla mezclando citas + vencidas (⚠️) + por-triar (⏩) |

    ## 📅 Próximos días
    ### 2026-05-20 · miércoles
    | tabla con citas + ⏩ pendings con ff de ese día |
    ...

Reglas (decisiones en [[project-orbit-dashboard-refactor]]):

- Counter telegráfico **adaptativo**: cada categoría aparece sólo si N>0.
  Línea de hitos desaparece entera si N=0.
- Reminders **excluidos del counter** (ambient).
- Hitos cuenta ventana 30 días; Próximos días = 7 días fijos.
- Vencidas (tasks planned con date<today no done, no recurrentes) se
  arrastran a la tabla de Hoy con marker ⚠️, cap 10 → fila resumen.
- Por triar = tasks pending con `ff`:
  - ff <= today → fila ⏩ en tabla de Hoy.
  - today < ff <= today+7 → fila ⏩ inline en tabla del día.
- Por triar excluye `ff: someday`.
- Link al proyecto: `<project>-agenda.md` (cambia a `<project>.md` en F4).
"""

from datetime import date as _date, timedelta
from pathlib import Path

from views import autogen_banner
from views.secretary._agenda_table import (
    DEFAULT_MIN, KIND_EMOJI, TABLE_HEADER,
    _desc_with_event_indicators, collect_items_by_day,
    detect_overlaps, overlap_char, proj_link_md, start_min, time_pair,
)


_WEEKDAYS_ES = ["lunes", "martes", "miércoles", "jueves", "viernes",
                "sábado", "domingo"]

NEXT_DAYS_WINDOW = 7
MILESTONES_WINDOW = 30
OVERDUE_CAP = 10


def _short_date_es(d) -> str:
    return f"{_WEEKDAYS_ES[d.weekday()]} {d.day:02d}/{d.month:02d}"


def _iter_local_projects():
    """Yield local project dirs (sin federados) que sean nuevos."""
    from core.config import iter_federated_project_dirs
    from core.project import _is_new_project
    for p in iter_federated_project_dirs(include_federated=False):
        if _is_new_project(p):
            yield p


def _read_agenda_safe(project_dir):
    """Read agenda.md or return None if missing."""
    from core.agenda.io import _read_agenda
    from core.log import resolve_file
    agenda_path = resolve_file(project_dir, "agenda")
    if not agenda_path or not agenda_path.exists():
        return None
    return _read_agenda(agenda_path)


def _collect_overdue(today):
    """Returns [(project_dir, task)] de pending tasks con date<today, no recurrentes.

    Locales sólo (las federadas son read-only, no actuables desde aquí).
    Ordenadas por fecha asc (más antiguas primero → más urgentes).
    """
    today_iso = today.isoformat()
    out = []
    for project_dir in _iter_local_projects():
        data = _read_agenda_safe(project_dir)
        if data is None:
            continue
        for t in data.get("tasks", []):
            if t.get("status") != "pending":
                continue
            if t.get("recur"):
                continue
            d = t.get("date")
            if not d or d >= today_iso:
                continue
            out.append((project_dir, t))
    out.sort(key=lambda r: r[1]["date"])
    return out


def _collect_pendings_in_ff_range(start_iso, end_iso):
    """Returns [(project_dir, task)] de pending tasks con start_iso<=ff<=end_iso.

    Excluye ff:someday y tasks sin ff. Locales sólo.
    """
    out = []
    for project_dir in _iter_local_projects():
        data = _read_agenda_safe(project_dir)
        if data is None:
            continue
        for t in data.get("tasks", []):
            if t.get("status") != "pending":
                continue
            ff = t.get("ff")
            if not ff or ff == "someday":
                continue
            if ff < start_iso or ff > end_iso:
                continue
            out.append((project_dir, t))
    out.sort(key=lambda r: r[1]["ff"])
    return out


def _count_milestones_window(today, days=MILESTONES_WINDOW) -> int:
    """Count pending milestones con today<=date<=today+days. Incluye federados."""
    from core.config import iter_federated_project_dirs
    from core.project import _is_new_project
    today_iso = today.isoformat()
    end_iso = (today + timedelta(days=days)).isoformat()
    count = 0
    for p in iter_federated_project_dirs(include_federated=True):
        if not _is_new_project(p):
            continue
        data = _read_agenda_safe(p)
        if data is None:
            continue
        for m in data.get("milestones", []):
            if m.get("status") != "pending":
                continue
            d = m.get("date")
            if d and today_iso <= d <= end_iso:
                count += 1
    return count


def _counter_lines(today_items, overdue, pendings_today, n_milestones) -> list:
    """Build adaptive counter blockquote (1-2 líneas).

    Categorías con N=0 se omiten. Si todas vacías, "sin compromisos".
    Línea de hitos desaparece si N=0.
    """
    # Hoy: 4 categorías (📅 ✅ ⚠️ ⏩). Milestones de hoy aparecen en la
    # tabla con 🏁 pero NO en el counter; los hitos viven en la línea
    # "Próximos 30 días" para evitar la duplicidad. Reminders excluidos
    # (ambient).
    n_events = sum(1 for it in today_items if it[0] == "events")
    n_tasks  = sum(1 for it in today_items if it[0] == "tasks")
    n_overdue = len(overdue)
    n_ff      = len(pendings_today)

    parts = []
    if n_events:
        parts.append(f"📅{n_events} eventos")
    if n_tasks:
        parts.append(f"✅{n_tasks} tareas")
    if n_overdue:
        parts.append(f"⚠️{n_overdue} vencidas")
    if n_ff:
        parts.append(f"⏩{n_ff} por triar")

    lines = []
    if parts:
        lines.append("> 🗓 Hoy: " + " · ".join(parts))
    else:
        lines.append("> 🗓 Hoy: sin compromisos")
    if n_milestones:
        lines.append(f"> 🏁 Próximos {MILESTONES_WINDOW} días: {n_milestones} hitos")
    return lines


def _render_pending_row(project_dir, t) -> str:
    """Fila ⏩ para pending tasks. Incluye marcas snooze."""
    desc_raw = t.get("desc", "") or ""
    snooze = t.get("snooze_count", 0) or 0
    extras = ""
    if snooze >= 3:
        extras = " ❗❗"
    elif snooze:
        extras = f" 💤{snooze}"
    failed = t.get("failed_count", 0) or 0
    if failed:
        extras += f" ❌{failed}"
    desc = (desc_raw + extras).replace("|", "\\|")
    return f"| ⏩ |  |  |  | {desc} | {proj_link_md(project_dir)} |"


def _render_overdue_row(project_dir, t) -> str:
    """Fila ⚠️ para tareas planned vencidas arrastradas a hoy."""
    desc_raw = t.get("desc", "") or ""
    d = t.get("date", "")
    desc = f"{desc_raw} (📅{d})".replace("|", "\\|")
    return f"| ⚠️ |  |  |  | {desc} | {proj_link_md(project_dir)} |"


def _render_items_table(items) -> list:
    """Render filas de un día (events/tasks/milestones/reminders).

    Variante de `_agenda_table.render_day_rows` que NO emite el header;
    devuelve sólo las filas. Permite componer una tabla mixta (citas +
    vencidas/⏩) bajo un único header.
    """
    if not items:
        return []
    timed = [it for it in items if it[1].get("time")]
    untimed = [it for it in items if not it[1].get("time")]
    timed.sort(key=lambda x: start_min(x[1]))
    overlaps = detect_overlaps(timed)
    rows = []
    for idx, (kind, item, _pdir, proj_md) in enumerate(timed):
        emoji = KIND_EMOJI[kind]
        st, en = time_pair(item, DEFAULT_MIN.get(kind))
        ov = "" if kind == "reminders" else overlap_char(overlaps.get(idx, 0))
        desc = _desc_with_event_indicators(kind, item)
        rows.append(f"| {emoji} | {ov} | {st} | {en} | {desc} | {proj_md} |")
    for kind, item, _pdir, proj_md in untimed:
        emoji = KIND_EMOJI[kind]
        desc = _desc_with_event_indicators(kind, item)
        rows.append(f"| {emoji} |  |  |  | {desc} | {proj_md} |")
    return rows


def _today_block(today_items, overdue, pendings_today) -> list:
    """Tabla única de Hoy: citas + ⚠️ vencidas (cap) + ⏩ por triar.

    Si todo está vacío, devuelve un texto placeholder.
    """
    if not today_items and not overdue and not pendings_today:
        return ["*Sin citas para hoy.*"]

    rows = [TABLE_HEADER]
    rows.extend(_render_items_table(today_items))

    overflow = max(len(overdue) - OVERDUE_CAP, 0)
    for project_dir, t in overdue[:OVERDUE_CAP]:
        rows.append(_render_overdue_row(project_dir, t))
    if overflow:
        rows.append(f"| ⚠️ |  |  |  | *…y {overflow} más vencidas* |  |")

    for project_dir, t in pendings_today:
        rows.append(_render_pending_row(project_dir, t))

    return rows


def _next_days_block(today, items_by_day, pendings_by_day) -> list:
    """Una tabla por día en [today+1, today+7]. Días vacíos se omiten.

    Devuelve sólo los bloques per-día (sin el H2 "Próximos días"); el
    caller decide si emite el H2 según haya o no contenido.
    """
    blocks = []
    for offset in range(1, NEXT_DAYS_WINDOW + 1):
        d = today + timedelta(days=offset)
        day_iso = d.isoformat()
        items = items_by_day.get(day_iso, [])
        pendings = pendings_by_day.get(day_iso, [])
        if not items and not pendings:
            continue
        blocks.append(f"### {day_iso} · {_WEEKDAYS_ES[d.weekday()]}")
        blocks.append("")
        rows = [TABLE_HEADER]
        rows.extend(_render_items_table(items))
        for project_dir, t in pendings:
            rows.append(_render_pending_row(project_dir, t))
        blocks.extend(rows)
        blocks.append("")
    return blocks


def generate(out_path: Path) -> None:
    """Escribe `agenda.md` (hot único del workspace) en out_path."""
    today = _date.today()
    end = today + timedelta(days=NEXT_DAYS_WINDOW)

    by_day = collect_items_by_day(today, end, include_federated=True)
    today_items = by_day.get(today.isoformat(), [])

    overdue = _collect_overdue(today)
    pendings_today = _collect_pendings_in_ff_range(
        _date.min.isoformat(), today.isoformat(),
    )
    pendings_next = _collect_pendings_in_ff_range(
        (today + timedelta(days=1)).isoformat(), end.isoformat(),
    )
    pendings_by_day: dict = {}
    for proj_dir, t in pendings_next:
        pendings_by_day.setdefault(t["ff"], []).append((proj_dir, t))

    n_milestones = _count_milestones_window(today)

    lines = [autogen_banner("secretary.agenda").rstrip(), ""]
    lines.extend(_counter_lines(today_items, overdue, pendings_today, n_milestones))
    lines.append("")
    lines.append(f"## 📅 Hoy — {_short_date_es(today)}")
    lines.append("")
    lines.extend(_today_block(today_items, overdue, pendings_today))
    lines.append("")

    next_blocks = _next_days_block(today, by_day, pendings_by_day)
    if next_blocks:
        lines.append("## 📅 Próximos días")
        lines.append("")
        lines.extend(next_blocks)

    out_path.write_text("\n".join(lines) + "\n")

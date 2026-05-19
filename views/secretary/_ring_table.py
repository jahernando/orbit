"""views/secretary/_ring_table — helpers compartidos para tablas de ring.

Usado por `ring_today.py` (sólo hoy) y `ring_next.py` (toda la ventana del
ring.json). Centraliza la lectura de `<workspace>/.reminders/ring.json` y
el render de filas markdown para que ambas vistas mantengan exactamente
la misma estructura visual.

Modelo de datos: `ring.json` ya está pre-cocinado por `views.ring.export`
(items expandidos por recurrencia, identidad por ocurrencia, ventana
rolling). Estos viewers son **viewers de diagnóstico**: muestran el
ring.json tal cual, para que el usuario compare con lo que realmente
suena en Reminders.app. Por eso NO recalculan desde agenda.md.

Estructura de la tabla:
    | emoji | Cita | Suena | Descripción | Proyecto |

- Cita:  "HH:MM" si la cita es el mismo día que suena el ring,
         "DD/MM HH:MM" si la cita cae otro día (alarm > 1 día, p.ej.).
- Suena: "HH:MM (-Xm/-Xh/-Xd)" — hora a la que dispara la alarma y offset.
- Proyecto: markdown link a la `<project>-agenda.md` si se localiza en
  el workspace; si no, texto en brackets escapados.
"""

import json
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional


KIND_EMOJI = {
    "event":     "📅",
    "task":      "✅",
    "milestone": "🏁",
    "reminder":  "💬",
}

TABLE_HEADER = (
    "| | Cita | Suena | Descripción | Proyecto |\n"
    "|---|------|-------|-------------|----------|"
)


def load_ring_json(workspace_root: Path) -> Optional[dict]:
    """Lee `<workspace>/.reminders/ring.json`. Returns None si no existe o
    es inválido."""
    path = workspace_root / ".reminders" / "ring.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return None


def _format_offset(alarm_minutes: int) -> str:
    """`5` → `-5m`, `60` → `-1h`, `1440` → `-1d`, `7200` → `-5d`.

    Negativo = antes de la cita (que es lo habitual). Si fuera positivo
    (después), el signo se invierte.
    """
    if alarm_minutes is None:
        return ""
    m = int(alarm_minutes)
    sign = "-" if m >= 0 else "+"
    am = abs(m)
    if am == 0:
        return "0m"
    if am % 1440 == 0:
        return f"{sign}{am // 1440}d"
    if am % 60 == 0:
        return f"{sign}{am // 60}h"
    return f"{sign}{am}m"


def cita_and_suena(due_iso: str, alarm_minutes: int, ring_dt: datetime
                   ) -> tuple:
    """Returns `(cita_str, suena_str)` para la fila de la tabla.

    cita_str:  "HH:MM" si la cita es el mismo día que `ring_dt`,
               "DD/MM HH:MM" si cae otro día.
    suena_str: "HH:MM (-Xm/-Xh/-Xd)".
    """
    try:
        due = datetime.fromisoformat(due_iso)
    except (ValueError, TypeError):
        return ("?", "?")
    if due.date() == ring_dt.date():
        cita = due.strftime("%H:%M")
    else:
        cita = due.strftime("%d/%m %H:%M")
    offset = _format_offset(alarm_minutes)
    suena = ring_dt.strftime("%H:%M")
    if offset:
        suena = f"{suena} ({offset})"
    return (cita, suena)


def ring_dt(item: dict) -> Optional[datetime]:
    """Compute la hora a la que suena la alarma del item:
    `due_iso - alarm_minutes`. Returns None si due_iso es inválido."""
    try:
        due = datetime.fromisoformat(item["due_iso"])
    except (KeyError, ValueError, TypeError):
        return None
    am = item.get("alarm_minutes") or 0
    return due - timedelta(minutes=int(am))


def _proj_link_md(project_name: str, project_index: dict) -> str:
    """Markdown link al `<project>-agenda.md` si project_name está en el
    índice; si no, texto en brackets escapados.

    `project_index` es un dict `{name: Path}` construido una sola vez por
    viewer para evitar O(items * projects).
    """
    from core.config import ORBIT_HOME
    from core.log import resolve_file
    pdir = project_index.get(project_name)
    if pdir is None:
        return f"\\[{project_name}\\]"
    agenda_path = resolve_file(pdir, "agenda")
    if not agenda_path.exists():
        return f"\\[{project_name}\\]"
    try:
        rel = agenda_path.relative_to(ORBIT_HOME)
    except ValueError:
        return f"\\[{project_name}\\]"
    return f"[{project_name}](../../{rel})"


def build_project_index() -> dict:
    """Returns `{project_name: project_dir_Path}` para todos los proyectos
    del workspace actual. Federados no incluidos (ring.json sólo contiene
    items locales)."""
    from core.config import iter_project_dirs
    return {p.name: p for p in iter_project_dirs()}


def render_rows(items: list, ring_dt_map: dict, project_index: dict,
                ) -> list:
    """items: lista de dicts del ring.json (ya filtrados al rango deseado).

    `ring_dt_map`: dict `{id(item): datetime}` con la hora calculada para
    cada item — evita recomputar. Sort por ring_dt ascendente.

    Returns lista de strings (header + filas). Vacía si items vacío.
    """
    if not items:
        return []
    items_sorted = sorted(items, key=lambda it: ring_dt_map[id(it)])
    lines = [TABLE_HEADER]
    for it in items_sorted:
        emoji = KIND_EMOJI.get(it.get("kind", ""), "•")
        cita, suena = cita_and_suena(
            it.get("due_iso", ""), it.get("alarm_minutes", 0),
            ring_dt_map[id(it)],
        )
        desc = (it.get("title") or "").replace("|", "\\|")
        proj = _proj_link_md(it.get("project", ""), project_index)
        lines.append(f"| {emoji} | {cita} | {suena} | {desc} | {proj} |")
    return lines


def header_lines(payload: dict, module: str) -> list:
    """Banner + título + meta-info del ring.json (generated_at, ventana,
    estado enabled). Líneas markdown sin trailing newline."""
    from views import autogen_banner
    gen = payload.get("generated_at", "?")
    ws = payload.get("window_start", "?")
    we = payload.get("window_end", "?")
    enabled = payload.get("enabled", True)
    list_name = payload.get("list", "?")
    state = "" if enabled else " · ⚠️ ring deshabilitado"
    return [
        autogen_banner(module).rstrip(),
        "",
        f"*ring.json regen: {gen} · ventana {ws} → {we} · "
        f"lista `{list_name}`{state}*",
        "",
    ]

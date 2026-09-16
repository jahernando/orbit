"""triage — motor común de `day` y `organize <proyecto>`.

Dos comandos, un motor (ADR-051):

* ``day [proyecto]`` — lo de **hoy**: citas que ocurren hoy, tareas/hitos
  vencidos y citas con un followup ``⏩ <= hoy``. Sin recordatorios.
* ``organize <proyecto>`` — **todo** lo pendiente de un proyecto: además de
  lo anterior, las próximas citas (recordatorios incluidos) y las tareas e
  hitos sin fecha.

Ambos listan las citas numeradas por bloques y abren el mismo menú de
acciones sobre la elegida: hora, fecha, followup, limpiar followup, done,
drop. Los cronogramas se listan debajo **en solo lectura** (sin número):
en ``day`` solo los pasos activos hoy o vencidos; en ``organize`` además la
barra de progreso de cada cronograma abierto.

Cada cita aparece una sola vez, en el primer bloque que le toca por este
orden: Hoy > Vencidas > Decidir ⏩ > Próximas > Sin fecha. Sus followups se
muestran como marca en la fila.

Las mutaciones delegan en los runners (``run_task_edit`` …), así que el
echo del item, el undo y los hooks son los de siempre. Solo los followups
se editan directamente sobre el cuerpo del item (no tienen efectos
laterales, ADR-043).
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Callable, Optional

from core.agenda_cmds import _read_agenda, _write_agenda, _valid_time
from core.agenda.display import (item_followups, add_followup,
                                 drop_followup, drop_followup_at,
                                 format_item_block)
from core.config import iter_project_dirs
from core.dateparse import parse_date as _parse_date
from core.log import resolve_file
from core.project import _is_new_project, _find_new_project
# Helpers de acción compartidos con el `organize` antiguo. Cuando se retiren
# `--triage` / `-P` (fase destructiva), se mudan aquí.
from core.organize import (_prompt, _looks_iso, _edit_kind_date, _drop_kind,
                           _locate_in_data)


KIND_EMOJI = {"task": "✏️", "ms": "🏁", "ev": "📅", "reminder": "💬"}
KIND_LABEL = {"task": "tarea", "ms": "hito", "ev": "evento",
              "reminder": "recordatorio"}
_SECTION_OF = {"task": "tasks", "ms": "milestones", "ev": "events",
               "reminder": "reminders"}

# Orden de bloques (y de prioridad al asignar cada cita a uno).
HOY, VENCIDAS, DECIDIR, PROXIMAS, SIN_FECHA = (
    "hoy", "vencidas", "decidir", "proximas", "sin_fecha")
SECTION_ORDER = (HOY, VENCIDAS, DECIDIR, PROXIMAS, SIN_FECHA)
SECTION_TITLE = {
    HOY: "Hoy", VENCIDAS: "⚠️ Vencidas", DECIDIR: "⏩ Decidir",
    PROXIMAS: "Próximas", SIN_FECHA: "Sin fecha",
}

_PROBE_SHIFT = timedelta(days=397)   # "otro hoy" para detectar fechas flotantes

_DAY_NAMES = ["lunes", "martes", "miércoles", "jueves", "viernes",
              "sábado", "domingo"]


@dataclass
class Row:
    kind: str                 # task | ms | ev | reminder
    project_dir: Path
    item: dict
    section: str


@dataclass
class CronoStep:
    index: str
    title: str
    start: Optional[date]
    end: Optional[date]       # deadline efectivo del paso


@dataclass
class CronoView:
    project_dir: Path
    name: str
    done: int
    total: int
    deadline: Optional[date]
    steps: list = field(default_factory=list)   # activos hoy o vencidos


# ── Fechas ────────────────────────────────────────────────────────────────

def _to_date(raw) -> Optional[date]:
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except (TypeError, ValueError):
        return None


def occurs_on(item: dict, kind: str, day: date) -> bool:
    """¿La cita cae en *day*? Cubre eventos de varios días y recurrencias."""
    start = _to_date(item.get("date"))
    if start is None:
        return False
    end = _to_date(item.get("end")) if kind == "ev" else None
    if start <= day <= (end or start):
        return True
    if item.get("recur") and start < day:
        # Una ocurrencia que empiece hasta `duración` días antes aún cubre hoy.
        from core.agenda_view import _expand_recurrences
        span = (end - start) if end else timedelta(0)
        for occ in _expand_recurrences(item, day - span, day):
            o_start = _to_date(occ["date"])
            o_end = _to_date(occ.get("end")) or o_start
            if o_start <= day <= o_end:
                return True
    return False


def is_overdue(item: dict, kind: str, today: date) -> bool:
    """Tarea/hito pendiente con fecha pasada. Las recurrentes no vencen."""
    if kind not in ("task", "ms") or item.get("recur"):
        return False
    d = _to_date(item.get("date"))
    return d is not None and d < today


def due_followups(item: dict, today: date) -> list:
    iso = today.isoformat()
    return [f for f in item_followups(item) if f["date"] and f["date"] <= iso]


def is_upcoming(item: dict, kind: str, today: date) -> bool:
    """Cita con fecha que aún no ha pasado (o serie recurrente viva)."""
    d = _to_date(item.get("date"))
    if d is None:
        return False
    if item.get("recur"):
        until = _to_date(item.get("until"))
        return until is None or until >= today
    last = _to_date(item.get("end")) if kind == "ev" else None
    return (last or d) >= today


def _is_open(item: dict, kind: str) -> bool:
    if item.get("cancelled"):
        return False
    if kind in ("task", "ms") and item.get("status") in ("done", "cancelled"):
        return False
    return True


# ── Recogida ──────────────────────────────────────────────────────────────

def resolve_dirs(project: Optional[str]) -> Optional[list]:
    """Proyectos propios a recorrer. None si *project* no existe."""
    if project:
        d = _find_new_project(project)
        if not d:
            print(f"⚠️  Proyecto no encontrado: {project!r}")
            return None
        return [d]
    return [d for d in iter_project_dirs() if _is_new_project(d)]


def classify(item: dict, kind: str, today: date, full: bool) -> Optional[str]:
    """Bloque de una cita, o None si no se lista.

    *full* = modo proyecto (`organize`): añade Próximas y Sin fecha, y
    admite recordatorios. En modo día los recordatorios nunca salen.
    """
    if not _is_open(item, kind):
        return None
    if kind == "reminder" and not full:
        return None
    if occurs_on(item, kind, today):
        return HOY
    if is_overdue(item, kind, today):
        return VENCIDAS
    if due_followups(item, today):
        return DECIDIR
    if not full:
        return None
    if is_upcoming(item, kind, today):
        return PROXIMAS
    if not item.get("date") and kind in ("task", "ms"):
        return SIN_FECHA
    return None


def _time_start(item: dict) -> str:
    return (item.get("time") or "").split("-")[0]


def _sort_key(row: Row, today: date):
    it = row.item
    if row.section == HOY:
        # Sin hora (todo el día) arriba, luego por hora.
        return (1 if it.get("time") else 0, _time_start(it), it.get("desc", ""))
    if row.section in (VENCIDAS, PROXIMAS):
        return (it.get("date") or "", _time_start(it), it.get("desc", ""))
    if row.section == DECIDIR:
        fups = due_followups(it, today)
        return (min(f["date"] for f in fups), it.get("desc", ""))
    # SIN_FECHA: hitos antes que tareas, orden del fichero.
    return (0 if row.kind == "ms" else 1,)


def collect(dirs: list, today: date, full: bool) -> dict:
    """``{bloque: [Row]}`` con los bloques en orden y filas ordenadas."""
    out = {s: [] for s in SECTION_ORDER}
    for project_dir in dirs:
        agenda = resolve_file(project_dir, "agenda")
        if not agenda.exists():
            continue
        data = _read_agenda(agenda)
        for kind, key in _SECTION_OF.items():
            for item in data.get(key) or []:
                section = classify(item, kind, today, full)
                if section:
                    out[section].append(Row(kind, project_dir, item, section))
    for section, rows in out.items():
        rows.sort(key=lambda r: _sort_key(r, today))
    return out


def number_rows(sections: dict) -> list:
    """Filas en el orden en que se numeran (1..N)."""
    return [r for s in SECTION_ORDER for r in sections.get(s, [])]


def collect_cronos(dirs: list, today: date, full: bool) -> list:
    """Cronogramas abiertos con sus pasos activos hoy o vencidos.

    En modo día solo entran los que tienen algún paso así; en modo
    proyecto, todos los abiertos (para ver su progreso).
    """
    from core.cronograma import (_parse_crono_file, _compute_dates,
                                 _parent_indices, _is_leaf, _leaf_deadline,
                                 _resolve_deadline)
    out = []
    for project_dir in dirs:
        cronos_dir = project_dir / "cronos"
        if not cronos_dir.exists():
            continue
        for f in sorted(cronos_dir.glob("crono-*.md")):
            data = _parse_crono_file(f)
            tasks = data["tasks"]
            if not tasks:
                continue
            # Un paso sin fecha propia hereda `initial-time` (hoy por
            # defecto): su fecha "flota" y saldría activo todos los días.
            # Se detecta calculando también con otro "hoy": si cambia, flota.
            probe = copy.deepcopy(tasks)
            _compute_dates(tasks, data["metadata"], today)
            _compute_dates(probe, data["metadata"], today + _PROBE_SHIFT)
            floating = {p["index"] for t, p in zip(tasks, probe)
                        if _leaf_deadline(t) != _leaf_deadline(p)}
            parents = _parent_indices(tasks)
            leaves = [t for t in tasks if _is_leaf(t, parents)]
            done = sum(1 for t in leaves if t["done"])
            if done == len(leaves):
                continue
            steps = []
            for t in leaves:
                if t["done"] or t["index"] in floating:
                    continue
                end = _leaf_deadline(t)
                start = t.get("start_date")
                if end is None:
                    continue
                if end < today or (start and start <= today <= end):
                    steps.append(CronoStep(t["index"], t["title"], start, end))
            if not steps and not full:
                continue
            steps.sort(key=lambda s: (s.end, s.index))
            out.append(CronoView(
                project_dir, data["name"], done, len(leaves),
                _resolve_deadline(data["metadata"], project_dir, today),
                steps))
    return out


# ── Presentación ──────────────────────────────────────────────────────────

def _short(d: Optional[date], today: date) -> str:
    if d is None:
        return ""
    return d.strftime("%m-%d") if d.year == today.year else d.isoformat()


def _when(row: Row, today: date) -> str:
    """Columna de fecha/hora: solo ASCII, para que alinee."""
    it = row.item
    time = it.get("time") or ""
    if row.section == HOY:
        return time
    d = _short(_to_date(it.get("date")), today)
    return f"{d} {time}".strip()


def _marks(row: Row, today: date) -> str:
    it = row.item
    parts = []
    if row.kind == "ev" and it.get("end"):
        parts.append(f"→{_short(_to_date(it['end']), today)}")
    if it.get("recur"):
        parts.append("🔄")
    if is_overdue(it, row.kind, today):
        parts.append("⚠️")
    fups = sorted(item_followups(it), key=lambda f: f["date"] or "")
    if fups:
        f = fups[0]
        due = f["date"] and f["date"] <= today.isoformat()
        mark = ("❗" if f["date"] < today.isoformat() else "") if due else ""
        extra = f"(+{len(fups) - 1})" if len(fups) > 1 else ""
        parts.append(f"{mark}⏩{_short(_to_date(f['date']), today)}{extra}")
    return ("  " + " ".join(parts)) if parts else ""


def format_row(n: int, row: Row, today: date, show_project: bool) -> str:
    proj = f"  [{row.project_dir.name}]" if show_project else ""
    return (f"  {n:>3}. {KIND_EMOJI[row.kind]} {_when(row, today):<11}  "
            f"{row.item.get('desc', '')}{_marks(row, today)}{proj}")


def format_listing(title: str, sections: dict, today: date,
                   show_project: bool) -> list:
    lines = [title, "─" * 70]
    n = 0
    for s in SECTION_ORDER:
        rows = sections.get(s) or []
        if not rows:
            continue
        lines.append(f"── {SECTION_TITLE[s]} ({len(rows)})")
        for row in rows:
            n += 1
            lines.append(format_row(n, row, today, show_project))
    if n == 0:
        lines.append("  (nada que triar)")
    return lines


def format_cronos(cronos: list, today: date, show_project: bool,
                  show_progress: bool) -> list:
    if not cronos:
        return []
    from core.cronograma import _deadline_short_str
    lines = ["── 📊 Cronogramas (solo lectura)"]
    for c in cronos:
        proj = f"  [{c.project_dir.name}]" if show_project else ""
        head = f"     📊 {c.name}  {c.done}/{c.total}"
        if show_progress:
            filled = round(c.done / c.total * 10) if c.total else 0
            head = f"     📊 {c.name}  {'█' * filled}{'░' * (10 - filled)} {c.done}/{c.total}"
        dl = _deadline_short_str(c.done, c.total, c.deadline, today)
        lines.append(head + (f" · {dl}" if dl else "") + proj)
        for st in c.steps:
            if st.end < today:
                when = f"⚠️ vencido {_short(st.end, today)}"
            else:
                when = f"hasta {_short(st.end, today)}"
            lines.append(f"          {st.index} {st.title}  ({when})")
    return lines


# ── Acciones ──────────────────────────────────────────────────────────────

def menu_for(row: Row) -> str:
    opts = ["[h]ora", "[f]echa", "[u] ⏩fup"]
    if item_followups(row.item):
        opts.append("[c]lear-⏩")
    if row.kind in ("task", "ms"):
        opts.append("do[n]e")
    opts += ["[d]rop", "[s]kip"]
    return "  " + "  ".join(opts)


def _ask_date(prompt: str, default: Optional[str] = None) -> Optional[str]:
    """Pide una fecha en lenguaje natural; devuelve ISO o None."""
    raw = _prompt(prompt)
    if not raw:
        return default
    iso = _parse_date(raw)
    if not _looks_iso(iso):
        print(f"  ⚠️  Fecha no reconocida: {raw!r}.")
        return None
    return iso


def _clear_due_followups(row: Row, today: date) -> list:
    """Al dar fecha u hora, los ⏩ vencidos quedan resueltos: se borran."""
    due = due_followups(row.item, today)
    if not due:
        return []
    agenda = resolve_file(row.project_dir, "agenda")
    data = _read_agenda(agenda)
    target = _locate_in_data(data, row.item)
    if target is None:
        return []
    removed = []
    for f in due:
        removed += drop_followup(target, f["date"])
    _write_agenda(agenda, data)
    return removed


def _report_cleared(removed: list) -> None:
    if removed:
        print(f"  ⏩ resuelto{'s' if len(removed) > 1 else ''}: "
              + ", ".join(r.split(None, 2)[1] for r in removed))


def _act_time(row: Row, today: date) -> bool:
    new_time = _prompt("    hora (HH:MM o HH:MM-HH:MM): ")
    if not new_time:
        return False
    if not _valid_time(new_time):
        print(f"  ⚠️  Hora no válida: {new_time!r}.")
        return False
    new_date = None
    if row.item.get("date") != today.isoformat():
        new_date = _ask_date("    fecha (enter = hoy): ", today.isoformat())
        if new_date is None:
            return False
    _edit_kind_date(row.kind, row.project_dir.name, row.item["desc"],
                    new_date, new_time)
    _report_cleared(_clear_due_followups(row, today))
    return True


def _act_date(row: Row, today: date) -> bool:
    new_date = _ask_date("    nueva fecha (hoy/mañana/viernes/+N/YYYY-MM-DD): ")
    if new_date is None:
        return False
    _edit_kind_date(row.kind, row.project_dir.name, row.item["desc"],
                    new_date, None)
    _report_cleared(_clear_due_followups(row, today))
    return True


def parse_fup_input(raw: str, today: date) -> Optional[tuple]:
    """``"fecha [desc]"`` → ``(iso, desc)``. Vacío = mañana. None si no vale.

    Se intenta la cadena entera como fecha (``next monday``) y, si no, el
    primer token como fecha y el resto como descripción.
    """
    if not raw:
        return (today + timedelta(days=1)).isoformat(), None
    whole = _parse_date(raw)
    if _looks_iso(whole):
        return whole, None
    head, _, rest = raw.partition(" ")
    first = _parse_date(head)
    if _looks_iso(first):
        return first, (rest.strip() or None)
    return None


def _act_fup(row: Row, today: date) -> bool:
    raw = _prompt("    ⏩ fecha [descripción] (enter = mañana): ")
    parsed = parse_fup_input(raw, today)
    if parsed is None:
        print(f"  ⚠️  Fecha no reconocida: {raw!r}. Usa YYYY-MM-DD, mañana, +N…")
        return False
    new_date, desc = parsed
    if new_date < today.isoformat():
        print(f"  ⚠️  {new_date} ya ha pasado; un ⏩ mira hacia delante.")
        return False
    agenda = resolve_file(row.project_dir, "agenda")
    data = _read_agenda(agenda)
    target = _locate_in_data(data, row.item)
    if target is None:
        print("  ⚠️  No encuentro la cita (¿cambió el fichero?).")
        return False
    # Los ⏩ vencidos se *mueven* (snooze); si no hay, se añade uno nuevo.
    moved = []
    for f in due_followups(target, today):
        moved += drop_followup(target, f["date"])
        desc = desc or f.get("desc")
    add_followup(target, new_date, desc)
    _write_agenda(agenda, data)
    if moved:
        olds = ", ".join(m.split(None, 2)[1] for m in moved)
        banner = f"⏩ movido {olds} → {new_date}"
    else:
        banner = f"⏩ añadido {new_date}"
    print(format_item_block(_SECTION_OF[row.kind], target,
                            banner=f"{banner} · {row.project_dir.name}"))
    return True


def _act_clear(row: Row, today: date) -> bool:
    fups = item_followups(row.item)
    if not fups:
        print("  (esta cita no tiene ⏩)")
        return False
    idx = 0
    if len(fups) > 1:
        for i, f in enumerate(fups, 1):
            extra = f" {f['desc']}" if f.get("desc") else ""
            print(f"      {i}. ⏩ {f['date']}{extra}")
        raw = _prompt("    ¿cuál borrar? (número, enter = ninguno): ")
        if not raw:
            return False
        try:
            idx = int(raw) - 1
        except ValueError:
            idx = -1
        if not 0 <= idx < len(fups):
            print(f"  ⚠️  No reconozco {raw!r}.")
            return False
    agenda = resolve_file(row.project_dir, "agenda")
    data = _read_agenda(agenda)
    target = _locate_in_data(data, row.item)
    if target is None or drop_followup_at(target, idx) is None:
        print("  ⚠️  No encuentro ese ⏩ (¿cambió el fichero?).")
        return False
    _write_agenda(agenda, data)
    print(format_item_block(_SECTION_OF[row.kind], target,
                            banner=f"⏩ borrado {fups[idx]['date']} · "
                                   f"{row.project_dir.name}"))
    return True


def _act_done(row: Row, today: date) -> bool:
    from core.agenda_cmds import run_task_done, run_ms_done
    if row.kind == "task":
        run_task_done(row.project_dir.name, row.item["desc"])
    elif row.kind == "ms":
        run_ms_done(row.project_dir.name, row.item["desc"])
    else:
        print(f"  (un {KIND_LABEL[row.kind]} no se completa; usa [d]rop.)")
        return False
    return True


def _act_drop(row: Row, today: date) -> bool:
    ans = _prompt(f"    ¿borrar {KIND_LABEL[row.kind]} "
                  f"«{row.item['desc']}»? [s/N]: ").lower()
    if ans not in ("s", "si", "sí", "y", "yes"):
        print("  (no se borra)")
        return False
    _drop_kind(row.kind, row.project_dir.name, row.item["desc"])
    return True


ACTIONS: dict = {
    "h": _act_time, "f": _act_date, "u": _act_fup, "c": _act_clear,
    "n": _act_done, "d": _act_drop,
}


# ── Bucle ─────────────────────────────────────────────────────────────────

def _refresh(applied: int) -> None:
    if not applied:
        return
    plural = "s" if applied != 1 else ""
    print(f"✓ {applied} cambio{plural} aplicado{plural}.")
    try:
        import threading
        from orbit import _run_full_refresh_coalesced
        threading.Thread(target=_run_full_refresh_coalesced,
                         daemon=True).start()
    except Exception:
        pass    # refrescar derivados es best-effort


def run_loop(title: str, dirs: list, full: bool, show_project: bool,
             today_fn: Callable[[], date] = date.today) -> int:
    applied = 0
    while True:
        today = today_fn()
        sections = collect(dirs, today, full)
        rows = number_rows(sections)
        print()
        for line in format_listing(title, sections, today, show_project):
            print(line)
        for line in format_cronos(collect_cronos(dirs, today, full), today,
                                  show_project, show_progress=full):
            print(line)
        print("─" * 70)
        if not rows:
            _refresh(applied)
            return 0

        sel = _prompt("#? (número, q=salir) > ")
        if not sel or sel.lower() in ("q", "quit", "exit"):
            _refresh(applied)
            return 0
        try:
            idx = int(sel)
        except ValueError:
            print(f"  ⚠️  No reconozco {sel!r}.")
            continue
        if not 1 <= idx <= len(rows):
            print(f"  ⚠️  No hay cita {idx}.")
            continue

        row = rows[idx - 1]
        print()
        print(format_row(idx, row, today, show_project).strip())
        print(menu_for(row))
        action = _prompt("  ?> ").lower()
        if action == "q":
            _refresh(applied)
            return 0
        fn = ACTIONS.get(action)
        if fn is None:
            continue            # s / enter / desconocida → vuelve a la lista
        try:
            if fn(row, today):
                applied += 1
        except Exception as exc:
            print(f"  ⚠️  Error: {exc}")


# ── Entradas ──────────────────────────────────────────────────────────────

def _day_label(today: date) -> str:
    return f"{today.isoformat()} ({_DAY_NAMES[today.weekday()]})"


def run_day(project: Optional[str] = None) -> int:
    """`day [proyecto]` — triaje de lo de hoy."""
    dirs = resolve_dirs(project)
    if dirs is None:
        return 1
    today = date.today()
    scope = dirs[0].name if project else "workspace"
    return run_loop(f"Día — {_day_label(today)} · {scope}", dirs,
                    full=False, show_project=not project)


def run_organize_project(project: str) -> int:
    """`organize <proyecto>` — triaje de todo lo pendiente del proyecto."""
    dirs = resolve_dirs(project)
    if dirs is None:
        return 1
    today = date.today()
    return run_loop(f"Organizar — {dirs[0].name} · {_day_label(today)}",
                    dirs, full=True, show_project=False)

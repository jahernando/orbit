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

import io
import re
import sys
from contextlib import redirect_stdout
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Callable, Optional

from core.agenda_cmds import _read_agenda, _write_agenda, _valid_time
from core.agenda.display import (item_followups, add_followup,
                                 drop_followup, drop_followup_at,
                                 format_item_block)
from core.config import iter_project_dirs
from core.cronograma import item_steps, step_label
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
_KIND_ENDING = {"task": "a", "ms": "o", "ev": "o", "reminder": "o"}   # cancelad-a/o
_KIND_ENDING = {"task": "a", "ms": "o", "ev": "o", "reminder": "o"}   # cancelad-a/o
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

_DAY_NAMES = ["lunes", "martes", "miércoles", "jueves", "viernes",
              "sábado", "domingo"]


@dataclass
class Row:
    kind: str                 # task | ms | ev | reminder
    project_dir: Path
    item: dict
    section: str
    steps: list = field(default_factory=list)   # pasos del crono (ADR-055)


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
                steps = []
                if item.get("crono") and _is_open(item, kind):
                    steps = item_steps(project_dir, item, today)
                    # Un paso activo o vencido hace aflorar su item.
                    if steps and section is None:
                        overdue = any(st["end"] < today for st in steps)
                        section = VENCIDAS if overdue else HOY
                if section:
                    out[section].append(Row(kind, project_dir, item, section,
                                            steps))
    for section, rows in out.items():
        rows.sort(key=lambda r: _sort_key(r, today))
    return out


def number_rows(sections: dict) -> list:
    """Filas en el orden en que se numeran (1..N)."""
    return [r for s in SECTION_ORDER for r in sections.get(s, [])]


def collect_cronos(dirs: list, today: date, full: bool) -> list:
    """Cronogramas abiertos **sin item** con sus pasos activos hoy o vencidos.

    Los cronos enlazados por una tarea / hito abierto (ADR-055) no salen
    aquí: sus pasos van sangrados bajo su item. En modo día solo entran los
    que tienen algún paso así; en modo proyecto, todos los abiertos.
    """
    from core.cronograma import (_parse_crono_file, _resolve_deadline,
                                 active_steps, linked_cronos)
    out = []
    for project_dir in dirs:
        cronos_dir = project_dir / "cronos"
        if not cronos_dir.exists():
            continue
        agenda = resolve_file(project_dir, "agenda")
        linked = linked_cronos(_read_agenda(agenda)) if agenda.exists() else set()
        for f in sorted(cronos_dir.glob("crono-*.md")):
            if f"cronos/{f.name}" in linked:
                continue
            data = _parse_crono_file(f)
            if not data["tasks"]:
                continue
            done, total, raw = active_steps(data, today)
            if done == total:
                continue
            steps = [CronoStep(s["index"], s["title"], s["start"], s["end"])
                     for s in raw]
            if not steps and not full:
                continue
            out.append(CronoView(
                project_dir, data["name"], done, total,
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
    from core.cronograma import crono_mark
    proj = f"  [{row.project_dir.name}]" if show_project else ""
    crono = crono_mark(row.project_dir, row.item)
    crono = f"  {crono}" if crono else ""
    return (f"  {n:>3}. {KIND_EMOJI[row.kind]} {_when(row, today):<11}  "
            f"{row.item.get('desc', '')}{crono}{_marks(row, today)}{proj}")


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
            for st in row.steps:
                lines.append(f"          ↳ {step_label(st, today)}")
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
    opts = ["⏰ [h]ora", "🗓️ [f]echa", "⏩ [u]fup"]
    if item_followups(row.item):
        opts.append("🧹 [c]lear-⏩")
    opts.append("🏷️ [t]ítulo")
    if row.kind in ("task", "ms"):
        opts.append("✅ do[n]e")
    opts += ["❌ [d]rop", "⏭️ [s]kip"]
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
    primer token como fecha y el resto como descripción. ``none`` →
    ``("none", None)``: la cita queda sin fecha.
    """
    if not raw:
        return (today + timedelta(days=1)).isoformat(), None
    if raw.strip().lower() == "none":
        return "none", None
    whole = _parse_date(raw)
    if _looks_iso(whole):
        return whole, None
    head, _, rest = raw.partition(" ")
    first = _parse_date(head)
    if _looks_iso(first):
        return first, (rest.strip() or None)
    return None


def _undatable(row: Row) -> bool:
    """Tareas e hitos no recurrentes: pueden quedarse sin fecha.

    Excepción (ADR-055): un item con crono conserva su fecha — es el plazo
    del cronograma; su ⏩ se añade sin tocarla.
    """
    return (row.kind in ("task", "ms") and not row.item.get("recur")
            and not row.item.get("crono"))


def _edit_kind_undate(row: Row) -> None:
    """``none``: deja la tarea / hito sin fecha, hora, ring ni ⏩ (vía runner)."""
    from core.agenda_cmds import run_task_edit, run_ms_edit
    edit = run_task_edit if row.kind == "task" else run_ms_edit
    edit(row.project_dir.name, row.item["desc"], fup="none", force=True)


def _act_fup(row: Row, today: date, raw: Optional[str] = None) -> bool:
    """⏩ sobre la cita. **No toca su fecha** (ADR-058): si la cita tiene
    día, el ⏩ se añade y la cita sigue en su día (para moverla, [f]echa).
    Si la cita salía por un ⏩ vencido, ese ⏩ se *mueve* a la nueva fecha.
    Solo ``none`` deja una tarea / hito sin fecha (y sin ⏩).

    *raw* (``day fup`` por lotes): la respuesta ya dada; si es None, se pide.
    """
    if raw is None:
        raw = _prompt("    ⏩ fecha [descripción] (enter = mañana, none = sin fecha): ")
    parsed = parse_fup_input(raw, today)
    if parsed is None:
        print(f"  ⚠️  Fecha no reconocida: {raw!r}. Usa YYYY-MM-DD, mañana, +N, none…")
        return False
    new_date, desc = parsed
    if new_date == "none":
        if not _undatable(row):
            why = ("es recurrente" if row.item.get("recur")
                   else "su fecha es el plazo de su crono" if row.item.get("crono")
                   else f"un {KIND_LABEL[row.kind]} necesita fecha")
            print(f"  ⚠️  No se puede dejar sin fecha: {why}. Usa [d]rop o [c]lear-⏩.")
            return False
        _edit_kind_undate(row)
        return True
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


def _act_title(row: Row, today: date) -> bool:
    """Cambia el título (vía ``<kind> edit --text``: comprueba que no choque
    con otra cita abierta del mismo tipo). El crono enlazado se conserva."""
    from core.agenda_cmds import (run_ev_edit, run_ms_edit, run_reminder_edit,
                                  run_task_edit)
    old = row.item["desc"]
    new = _prompt(f"    nuevo título (enter = dejar «{old}»): ").strip()
    if not new or new == old:
        return False
    edit = {"task": run_task_edit, "ms": run_ms_edit, "ev": run_ev_edit,
            "reminder": run_reminder_edit}[row.kind]
    if edit(row.project_dir.name, old, new_text=new, force=True) != 0:
        return False
    row.item["desc"] = new          # la verificación busca ya el título nuevo
    return True


ACTIONS: dict = {
    "h": _act_time, "f": _act_date, "u": _act_fup, "c": _act_clear,
    "t": _act_title, "n": _act_done, "d": _act_drop,
}


# ── Verificación ──────────────────────────────────────────────────────────
#
# Tras cada acción se relee la agenda y se dice en qué estado quedó la cita,
# justo encima del prompt (el echo del runner queda arriba, tapado por la
# lista). Localiza por posición en su sección, tomada antes de actuar.

def _section_items(row: Row) -> list:
    data = _read_agenda(resolve_file(row.project_dir, "agenda"))
    return data.get(_SECTION_OF[row.kind]) or []


def _same(a: dict, b: dict) -> bool:
    oid = b.get("orbit_id")
    return a.get("orbit_id") == oid if oid else a.get("desc") == b.get("desc")


def locate_index(row: Row) -> Optional[int]:
    items = _section_items(row)
    for i, it in enumerate(items):
        if it == row.item:
            return i
    for i, it in enumerate(items):
        if _same(it, row.item):
            return i
    return None


def describe_after(row: Row, idx: Optional[int], action: str) -> str:
    """Una línea con el estado real de la cita tras *action*."""
    e = _KIND_ENDING[row.kind]
    head = (f"{KIND_EMOJI[row.kind]} «{row.item.get('desc', '')}» "
            f"· {row.project_dir.name}")
    items = _section_items(row)
    it = items[idx] if idx is not None and idx < len(items) else None
    if it is None or not _same(it, row.item):
        return f"✓ {head} → eliminad{e} de la agenda"
    if it.get("status") == "cancelled" or it.get("cancelled"):
        return f"✓ {head} → cancelad{e}"
    if it.get("status") == "done":
        return f"✓ {head} → completad{e}"
    when = " ".join(x for x in (it.get("date"), it.get("time")) if x)
    state = when or "sin fecha"
    fups = ", ".join(f["date"] for f in item_followups(it) if f["date"])
    if fups:
        state += f" · ⏩ {fups}"
    if action in ("d", "n") and it.get("date") == row.item.get("date"):
        verb = "cancelad" if action == "d" else "completad"
        return f"⚠️  {head} NO se ha {verb}o: sigue abiert{e} ({state})"
    return f"✓ {head} → {state}"


# ── day fup por lotes ─────────────────────────────────────────────────────
#
# Gramática (ADR-056): un entero solo es SIEMPRE un índice; lo demás, fecha.
#   3 5 7 viernes [desc]   → la misma fecha a varios
#   3:viernes 5:+7         → parejas (fecha de una palabra)
#   3   /   3 5            → pide la fecha (una para todos)
#   3 5 none               → sin fecha

_INDEX = re.compile(r"^\d+$")
_PAIR = re.compile(r"^(\d+):(\S+)$")


def parse_fup_batch(raw: str, n_rows: int, today: date):
    """``[(índices, respuesta | None)]`` o un ``str`` con el error.

    *respuesta* es lo que se pasará a ``_act_fup``; None = hay que pedirla.
    """
    groups, pending, rest = [], [], []
    for tok in raw.split():
        if rest:
            rest.append(tok)
        elif _INDEX.match(tok):
            pending.append(int(tok))
        elif _PAIR.match(tok):
            m = _PAIR.match(tok)
            groups.append(([int(m.group(1))], m.group(2)))
        else:
            rest.append(tok)
    if pending:
        groups.append((pending, " ".join(rest) or None))
    elif rest:
        return f"falta el número de la cita antes de {' '.join(rest)!r}"
    if not groups:
        return "nada que hacer"
    seen = set()
    for idxs, answer in groups:
        for i in idxs:
            if not 1 <= i <= n_rows:
                return f"no hay cita {i}"
            if i in seen:
                return f"la cita {i} sale dos veces"
            seen.add(i)
        if answer is not None:
            err = _check_fup_answer(answer, today)
            if err:
                return err
    return groups


def _check_fup_answer(answer: str, today: date) -> Optional[str]:
    parsed = parse_fup_input(answer, today)
    if parsed is None:
        return f"fecha no reconocida: {answer!r}"
    if parsed[0] != "none" and parsed[0] < today.isoformat():
        return f"{parsed[0]} ya ha pasado; un ⏩ mira hacia delante"
    return None


def _fup_target(answer: str, today: date) -> str:
    iso, desc = parse_fup_input(answer, today)
    if iso == "none":
        return "sin fecha"
    d = date.fromisoformat(iso)
    out = f"⏩ {iso} ({_DAY_NAMES[d.weekday()][:3]})"
    return out + (f" «{desc}»" if desc else "")


def _run_fup_batch(sel: str, rows: list, today: date,
                   show_project: bool = False) -> list:
    """Aplica un lote de ⏩; devuelve las líneas de verificación."""
    groups = parse_fup_batch(sel, len(rows), today)
    if isinstance(groups, str):
        print(f"  ⚠️  {groups}.")
        return []
    if len(groups) == 1 and len(groups[0][0]) == 1 and groups[0][1] is None:
        # Un solo número sin fecha: como siempre, la pide y aplica.
        row = rows[groups[0][0][0] - 1]
        print()
        print(format_row(groups[0][0][0], row, today, show_project).strip())
        pos = locate_index(row)
        try:
            return [describe_after(row, pos, "u")] if _act_fup(row, today) else []
        except Exception as exc:
            print(f"  ⚠️  Error: {exc}")
            return []
    resolved = []
    for idxs, answer in groups:
        if answer is None:
            answer = _prompt(f"    ⏩ para {' '.join(map(str, idxs))} — fecha "
                             "[descripción] (enter = mañana, none = sin fecha): ")
            err = _check_fup_answer(answer, today)
            if err:
                print(f"  ⚠️  {err}.")
                return []
        resolved += [(i, answer) for i in idxs]
    print()
    for i, answer in resolved:
        row = rows[i - 1]
        print(f"  {i:>3}. {KIND_EMOJI[row.kind]} «{row.item.get('desc', '')}»"
              f" → {_fup_target(answer, today)}")
    ok = _prompt(f"  ¿aplicar {len(resolved)}? [S/n]: ").lower()
    if ok not in ("", "s", "si", "sí", "y", "yes"):
        print("  (no se aplica nada)")
        return []
    out = []
    for i, answer in resolved:
        row = rows[i - 1]
        pos = locate_index(row)
        buf = io.StringIO()
        try:
            with redirect_stdout(buf):
                done = _act_fup(row, today, answer)
        except Exception as exc:
            done = False
            buf.write(f"  ⚠️  Error: {exc}\n")
        if done:
            out.append(describe_after(row, pos, "u"))
        else:
            # El runner explica por qué no; solo se enseña si falla.
            out.append(f"⚠️  {i}. «{row.item.get('desc', '')}»: "
                       + (buf.getvalue().strip().splitlines() or ["sin cambios"])[-1].strip())
    return out


def _load_calendar(dirs: list, today: date, n_today: int) -> list:
    from core import loadcal
    weeks = loadcal.weeks_from(today)
    loads = loadcal.day_loads(dirs, today, [d for w in weeks for d in w],
                              today_count=n_today)
    return loadcal.render(loads, today, weeks, counts=loadcal.show_counts(),
                          ansi=sys.stdout.isatty())


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
             today_fn: Callable[[], date] = date.today,
             fup_only: bool = False) -> int:
    """*fup_only* (``day fup``): sin menú; calendario de carga y ⏩ por
    lotes (``3 5 viernes``, ``3:+2``…)."""
    applied = 0
    last = None             # verificación de la última acción
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
        if fup_only and rows:
            for line in _load_calendar(dirs, today, len(rows)):
                print(line)
        print("─" * 70)
        if last:
            print(last)
            last = None
        if not rows:
            _refresh(applied)
            return 0

        hint = ("#? (3 5 viernes · 3:+2 · 3 · q=salir) > " if fup_only
                else "#? (número, q=salir) > ")
        sel = _prompt(hint)
        if not sel or sel.lower() in ("q", "quit", "exit"):
            _refresh(applied)
            return 0
        if fup_only:
            done = _run_fup_batch(sel, rows, today, show_project)
            applied += sum(1 for d in done if d.startswith("✓"))
            last = "\n".join(done) or None
            continue
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
        pos = locate_index(row)
        try:
            if fn(row, today):
                applied += 1
                last = describe_after(row, pos, action)
        except Exception as exc:
            print(f"  ⚠️  Error: {exc}")


# ── Entradas ──────────────────────────────────────────────────────────────

def _day_label(today: date) -> str:
    return f"{today.isoformat()} ({_DAY_NAMES[today.weekday()]})"


def run_day(project: Optional[str] = None, fup_only: bool = False) -> int:
    """`day [fup] [proyecto]` — triaje de lo de hoy.

    Con *fup_only* la lista es la misma, pero elegir un número pide
    directamente la fecha del ⏩ (sin menú).
    """
    dirs = resolve_dirs(project)
    if dirs is None:
        return 1
    today = date.today()
    scope = dirs[0].name if project else "workspace"
    head = "Día · ⏩ fup" if fup_only else "Día"
    return run_loop(f"{head} — {_day_label(today)} · {scope}", dirs,
                    full=False, show_project=not project, fup_only=fup_only)


def run_organize_project(project: str) -> int:
    """`organize <proyecto>` — triaje de todo lo pendiente del proyecto."""
    dirs = resolve_dirs(project)
    if dirs is None:
        return 1
    today = date.today()
    return run_loop(f"Organizar — {dirs[0].name} · {_day_label(today)}",
                    dirs, full=True, show_project=False)

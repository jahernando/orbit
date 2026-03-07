"""orbit report review — integrated workspace review: focus check + project health."""

import calendar
import re
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

from core.log import PROJECTS_DIR, find_logbook_file, find_proyecto_file
from core.tasks import STATUS_MAP, PRIORITY_MAP, load_project_meta, normalize, update_proyecto_field
from core.activity import (
    get_logbook_activity, has_activity_in,
    compute_real_status, compute_real_priority, parse_date_range,
    PRIORITY_ORDER,
)
from core.open import open_file

MISION_LOG_DIR = Path(__file__).parent.parent / "☀️mision-log"
DIARIO_DIR     = MISION_LOG_DIR / "diario"
SEMANAL_DIR    = MISION_LOG_DIR / "semanal"
MENSUAL_DIR    = MISION_LOG_DIR / "mensual"
REVIEW_OUTPUT  = MISION_LOG_DIR / "review.md"

INJECT_START = "<!-- orbit:tomato:start -->"
INJECT_END   = "<!-- orbit:tomato:end -->"


# ── Period detection ──────────────────────────────────────────────────────────

def _detect_period(date_str: Optional[str]):
    """Return (kind, start, end, note_path) from a date string.

    kind: 'day' | 'week' | 'month'
    """
    today = date.today()

    if not date_str:
        # Default: today (day)
        return "day", today, today, DIARIO_DIR / f"{today.isoformat()}.md"

    if len(date_str) == 10:
        # YYYY-MM-DD → day
        d = date.fromisoformat(date_str)
        return "day", d, d, DIARIO_DIR / f"{d.isoformat()}.md"

    if re.match(r'^\d{4}-W\d{2}$', date_str):
        # YYYY-Wnn → week
        y, w = int(date_str[:4]), int(date_str[6:])
        monday = date.fromisocalendar(y, w, 1)
        sunday = monday + timedelta(days=6)
        return "week", monday, sunday, SEMANAL_DIR / f"{date_str}.md"

    if len(date_str) == 7:
        # YYYY-MM → month
        y, m = int(date_str[:4]), int(date_str[5:7])
        start = date(y, m, 1)
        end   = date(y, m, calendar.monthrange(y, m)[1])
        return "month", start, end, MENSUAL_DIR / f"{date_str}.md"

    raise ValueError(f"Formato de fecha no reconocido: '{date_str}'. Usa YYYY-MM-DD, YYYY-Wnn o YYYY-MM.")


# ── Focus project parsing ─────────────────────────────────────────────────────

def _read_focus_projects(note_path: Path) -> list:
    """Extract focus project names from '## 🎯 Proyecto(s) en foco' section."""
    if not note_path.exists():
        return []
    focus = []
    in_section = False
    for line in note_path.read_text().splitlines():
        if re.search(r"##.*foco", line, re.IGNORECASE):
            in_section = True
            continue
        if in_section and line.startswith("## "):
            break
        if in_section:
            m = re.search(r"\[([^\]]+)\]", line)
            if m:
                focus.append(m.group(1).strip())
    return focus


def _find_project_dir(name: str):
    """Find a project directory by partial name match."""
    for d in PROJECTS_DIR.iterdir():
        if d.is_dir() and name.lower() in d.name.lower():
            return d
    return None


# ── Output injection ──────────────────────────────────────────────────────────

def _inject_into_note(note_path: Path, content: str) -> bool:
    """Replace content between orbit:tomato markers in the note. Returns True on success."""
    if not note_path.exists():
        return False
    text = note_path.read_text()
    if INJECT_START not in text or INJECT_END not in text:
        return False
    block = f"{INJECT_START}\n{content}\n{INJECT_END}"
    new_text = re.sub(
        re.escape(INJECT_START) + r".*?" + re.escape(INJECT_END),
        block,
        text,
        flags=re.DOTALL,
    )
    note_path.write_text(new_text)
    return True


# ── Main ──────────────────────────────────────────────────────────────────────

def run_review(
    date_str: Optional[str],
    inject: bool,
    apply: bool,
    output: Optional[str],
    open_after: bool,
    editor: str,
) -> int:
    if not PROJECTS_DIR.exists():
        print(f"Error: directorio de proyectos no encontrado en {PROJECTS_DIR}")
        return 1

    try:
        kind, start, end, note_path = _detect_period(date_str)
    except ValueError as e:
        print(f"Error: {e}")
        return 1

    period_days = (end - start).days + 1
    kind_label  = {"day": "día", "week": "semana", "month": "mes"}[kind]
    header_date = date_str or start.isoformat()

    lines = [
        f"REVISIÓN — {header_date}  ({kind_label})",
        "═" * 56,
        "",
    ]

    # ── Section 1: focus project check ───────────────────────────────────────
    focus_names = _read_focus_projects(note_path)

    if focus_names:
        lines.append("🎯 Proyectos en foco")
        for name in focus_names:
            pdir = _find_project_dir(name)
            if not pdir:
                lines.append(f"  ❓ {name}  (proyecto no encontrado)")
                continue
            lb = find_logbook_file(pdir)
            active = has_activity_in(lb, start, end)
            _, counts = get_logbook_activity(lb, start, end) if lb else (None, {})
            total = sum(counts.values()) if counts else 0
            mark = "✅" if active else "❌"
            if active:
                tomatoes = "🍅" * min(total, 5) + ("+" if total > 5 else "")
                detail = f"{tomatoes}  ({total})"
            else:
                detail = "— sin actividad"
            lines.append(f"  {mark} {name:<30} {detail}")
        lines.append("")
    else:
        if note_path.exists():
            lines.append("🎯 Sin proyectos en foco definidos en la nota.\n")
        else:
            lines.append(f"🎯 Nota de período no encontrada: {note_path.name}\n")

    # ── Section 2: project health ─────────────────────────────────────────────
    lines.append("🏥 Salud de proyectos")
    lines.append(f"  {'Proyecto':<28} {'Nominal':<7} {'Real':<7} {'Última':<12}")
    lines.append("  " + "─" * 60)

    changes  = []
    archived = []

    for project_dir in sorted(PROJECTS_DIR.iterdir()):
        if not project_dir.is_dir():
            continue
        proyecto_path = find_proyecto_file(project_dir)
        if not proyecto_path or not proyecto_path.exists():
            continue

        meta = load_project_meta(proyecto_path)
        if "completado" in meta["estado_raw"]:
            continue

        nominal_status_key   = next((k for k in STATUS_MAP   if normalize(k) in meta["estado_raw"]),    "")
        nominal_priority_key = next((k for k in PRIORITY_MAP if normalize(k) in meta["prioridad_raw"]), "")

        lb = find_logbook_file(project_dir)
        last_entry, _ = get_logbook_activity(lb, start, end) if lb else (None, {})
        has_30 = has_activity_in(lb, end - timedelta(days=30), end)
        has_60 = has_activity_in(lb, end - timedelta(days=60), end)

        real_status_key   = compute_real_status(nominal_status_key, has_30, has_60)
        is_passive        = nominal_status_key in ("esperando", "inicial")
        real_priority_key = compute_real_priority(nominal_priority_key, has_30, period_days, is_passive)

        if real_priority_key is None:
            archived.append(project_dir.name)
            continue

        status_changed   = real_status_key != nominal_status_key
        priority_changed = real_priority_key != nominal_priority_key

        if status_changed or priority_changed:
            changes.append({
                "name":              project_dir.name,
                "proyecto_path":     proyecto_path,
                "real_status_key":   real_status_key,
                "real_priority_key": real_priority_key,
            })

        nom  = f"{STATUS_MAP.get(nominal_status_key,'')}{PRIORITY_MAP.get(nominal_priority_key,'')}"
        real = f"{STATUS_MAP.get(real_status_key,'')}{PRIORITY_MAP.get(real_priority_key,'')}"
        flag = " ⚠️" if status_changed or priority_changed else ""
        last = last_entry or "—"
        lines.append(f"  {project_dir.name:<28} {nom:<7} {real:<7} {last:<12}{flag}")

    if changes:
        lines += ["", "  CAMBIOS PROPUESTOS:"]
        for c in changes:
            s = f"{STATUS_MAP[c['real_status_key']]} {c['real_status_key']}"
            p = f"{PRIORITY_MAP[c['real_priority_key']]} {c['real_priority_key']}"
            lines.append(f"    {c['name']}: estado → {s}   prioridad → {p}")

        if apply:
            for c in changes:
                sk, pk = c["real_status_key"], c["real_priority_key"]
                update_proyecto_field(c["proyecto_path"], "estado",    f"{STATUS_MAP[sk]} {sk.capitalize()}")
                update_proyecto_field(c["proyecto_path"], "prioridad", f"{PRIORITY_MAP[pk]} {pk.capitalize()}")
            lines += ["", f"  ✓ {len(changes)} proyecto(s) actualizado(s)"]
        else:
            lines += ["", "  Ejecuta con --apply para aplicar estos cambios."]

    if archived:
        lines += ["", f"  💤 Sin actividad prolongada ({len(archived)}): " + ", ".join(archived)]

    text = "\n".join(lines)

    # ── Inject into note ──────────────────────────────────────────────────────
    if inject:
        if _inject_into_note(note_path, text):
            print(f"✓ Inyectado en {note_path.name}")
        else:
            print(f"⚠️  No se pudo inyectar: {note_path} (¿existe la nota y los marcadores?)")

    # ── Output destination ────────────────────────────────────────────────────
    if open_after and not output:
        dest = REVIEW_OUTPUT
    elif output:
        dest = Path(output)
    else:
        dest = None

    if dest:
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(text + "\n")
        print(f"✓ Guardado en {dest}")
        if open_after:
            open_file(dest, editor)
    elif not inject:
        print(text)

    return 0

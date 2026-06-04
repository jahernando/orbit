"""views/secretary/hitos.py — tabla de hitos (vencidos + próximos 30 días).

Detalle del contador `🏁 Próximos 30 días: N hitos` del header de
`agenda.md`. Lista los hitos pending vencidos (date<today) + los de la
ventana próxima (today <= date <= today+30), propios + federados, y, si un
cronograma del mismo proyecto lo referencia como deadline (por nombre),
muestra su barra de progreso + link.

Columnas: emoji · Fecha · Proyecto · Hito · Cronograma. La columna emoji es
la señal primaria de urgencia (⚠️ vencido / 🏁 próximo); la Fecha añade ⚠️
solo para los inminentes (≤3d) — así el mismo ⚠️ nunca coexiste con dos
sentidos en una fila.

El vínculo hito↔cronograma no es un dato propio: se reconstruye invirtiendo
la convención `deadline: <nombre-hito>` de la metadata del cronograma
(misma regla de match por nombre que `_resolve_deadline`). Los cronogramas
con `deadline:` por fecha ISO NO se asocian (evita falsos positivos por
coincidencia de fecha).

Viewer puro: lee la verdad (agenda.md de cada proyecto + cronos/crono-*.md),
escribe el .md, return.
"""

from datetime import date
from pathlib import Path


def _fecha_cell(d: date, today: date) -> str:
    """'06-12 (8d)'. Vencido → '(vencido Nd)' (sin ⚠️: lo lleva la columna
    emoji). Inminente (≤3d) → ⚠️."""
    days = (d - today).days
    base = f"{d.month:02d}-{d.day:02d}"
    if days < 0:
        return f"{base} (vencido {-days}d)"
    if days <= 3:
        return f"⚠️ {base} ({days}d)"
    return f"{base} ({days}d)"


def _crono_cell(project_dir: Path, milestone_desc: str) -> str:
    """Celda 'link ████░░ done/total' para cronos cuyo deadline nombra el hito.

    Devuelve '' si ninguno. Varios cronos → separados por <br>.
    """
    from core.config import ORBIT_HOME
    from core.cronograma import (_ISO_DATE_RE, _is_leaf, _parent_indices,
                                 _parse_crono_file)

    cronos_dir = project_dir / "cronos"
    if not cronos_dir.exists():
        return ""
    md = milestone_desc.lower()
    cells = []
    for crono_file in sorted(cronos_dir.glob("crono-*.md")):
        data = _parse_crono_file(crono_file)
        raw = (data["metadata"].get("deadline") or "").strip()
        if not raw or _ISO_DATE_RE.match(raw):
            continue  # solo vínculo por nombre, no por fecha ISO
        if raw.lower() not in md:
            continue
        tasks = data["tasks"]
        if not tasks:
            continue
        parents = _parent_indices(tasks)
        leaves = [t for t in tasks if _is_leaf(t, parents)]
        total = len(leaves)
        done = sum(1 for t in leaves if t["done"])
        pct = done * 100 // total if total else 0
        filled = round(pct / 10)
        bar = "█" * filled + "░" * (10 - filled)
        try:
            rel = crono_file.relative_to(ORBIT_HOME)
            link = f"[{data['name']}](../../{rel})"
        except ValueError:
            link = data["name"]  # federado u otro vault: no linkable
        cells.append(f"{link} {bar} {done}/{total}")
    return "<br>".join(cells)


def generate(out_path: Path) -> None:
    """Escribe la tabla de hitos próximos en out_path."""
    from views import autogen_banner
    from views.secretary._agenda_table import proj_link_md
    from views.secretary.agenda import (MILESTONES_WINDOW,
                                        _collect_milestones_window,
                                        _collect_overdue_milestones)

    today = date.today()
    today_iso = today.isoformat()
    # Vencidos primero (date<today), luego ventana próxima. Ambos vienen
    # ordenados asc y los rangos no se solapan → concatenación = orden global.
    milestones = _collect_overdue_milestones(today) + _collect_milestones_window(today)

    lines = [autogen_banner("secretary.hitos").rstrip(), "",
             f"# 🏁 Hitos — vencidos + próximos ({MILESTONES_WINDOW} días)\n"]

    if not milestones:
        lines.append(f"(sin hitos vencidos ni en los próximos {MILESTONES_WINDOW} días)")
        out_path.write_text("\n".join(lines) + "\n")
        return

    lines.append("| | Fecha | Proyecto | Hito | Cronograma |")
    lines.append("|---|-------|----------|------|------------|")
    for project_dir, m in milestones:
        d = date.fromisoformat(m["date"])
        emoji = "⚠️" if m["date"] < today_iso else "🏁"
        fecha = _fecha_cell(d, today)
        proj = proj_link_md(project_dir)
        desc = (m.get("desc") or "").replace("|", "\\|")
        crono = _crono_cell(project_dir, m.get("desc") or "")
        lines.append(f"| {emoji} | {fecha} | {proj} | {desc} | {crono or '—'} |")

    out_path.write_text("\n".join(lines) + "\n")

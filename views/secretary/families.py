"""views/secretary/families.py — una hoja por familia de proyectos (ADR-059).

`📊panel/secretary/families/<familia>.md`, una por familia de `orbit.json`
(ver :mod:`core.families`). Junta lo de los proyectos de la familia, en
callouts de Obsidian (``> [!note]-`` sale plegado, ``+`` abierto):

    # 🟣 hk
    > 📆 jueves · hoy es su día
    > Proyectos: …
    > ⏩ Por triar      ← followups ⏩ <= hoy
    > ⚠️ Vencidas       ← tareas e hitos con fecha pasada
    > 📅 Próximas       ← tareas, hitos, eventos y ⏩ de hoy a +30 días
    > 🗂️ Sin fecha      ← tareas e hitos sin fecha
    > 📊 Cronogramas    ← abiertos, con su progreso

El día de la familia, ⏩ y ⚠️ salen abiertos; el resto, plegado. El estado
va escrito en el md, así que sobrevive a cada regeneración.

Carril hot (como `agenda.md`): es la vista desde la que se tría. Solo
proyectos locales: los federados se leen en su propio workspace.
"""

from datetime import date as _date, timedelta
from pathlib import Path

from views import autogen_banner
from views.secretary._agenda_table import (
    KIND_EMOJI, _desc_with_event_indicators, proj_link_md,
)

DIRNAME = "families"
UPCOMING_DAYS = 30

FAMILY_HEADER = (
    "| | | Fecha | Hora | Descripción | Proyecto |\n"
    "|---|---|---|---|---|---|"
)


def callout(title: str, rows: list, open_: bool, kind: str = "note") -> list:
    """Bloque ``> [!kind]± título`` con *rows* dentro (sin línea final)."""
    out = [f"> [!{kind}]{'+' if open_ else '-'} {title}"]
    for r in rows:
        out.extend(f"> {line}" if line else ">" for line in r.split("\n"))
    return out


def _relink(line: str) -> str:
    """Los enlaces del secretario son relativos a `📊panel/secretary/`; la
    hoja de familia vive un nivel más abajo."""
    return line.replace("](../../", "](../../../")


def _short(iso: str, today) -> str:
    if not iso:
        return ""
    d = _date.fromisoformat(iso)
    return d.strftime("%m-%d") if d.year == today.year else iso


def _row(kind, mark, when, time, desc, project_dir) -> str:
    return (f"| {KIND_EMOJI.get(kind, '')} | {mark} | {when} | {time} | "
            f"{desc} | {proj_link_md(project_dir)} |")


def _next_fup(item, today) -> str:
    """``⏩MM-DD`` del primer followup futuro, o ''."""
    from core.agenda.display import item_followups
    dates = sorted(f["date"] for f in item_followups(item)
                   if f.get("date") and f["date"] not in ("someday",))
    return f"⏩{_short(dates[0], today)}" if dates else ""


def collect(dirs, today, by_day=None, cronos=None) -> dict:
    """Todo lo de una familia: ``{fups, overdue, upcoming, undated, cronos}``.

    *dirs*: directorios de proyecto de la familia (locales). *by_day* y
    *cronos* (de ``collect_items_by_day`` / ``_collect_cronogramas``) se
    pasan ya leídos cuando hay varias familias, para no releer el workspace."""
    from core.agenda.display import item_followups
    from core.panel import _collect_cronogramas
    from views.secretary._agenda_table import collect_items_by_day
    from views.secretary.agenda import _read_agenda_safe

    keep = {str(p) for p in dirs}
    today_iso = today.isoformat()
    end = today + timedelta(days=UPCOMING_DAYS)
    out = {"fups": [], "overdue": [], "upcoming": [], "undated": [],
           "cronos": []}
    for pdir in dirs:
        data = _read_agenda_safe(pdir)
        if data is None:
            continue
        for kind in ("tasks", "milestones", "events", "reminders"):
            for item in data.get(kind, []):
                if (item.get("status") in ("done", "cancelled")
                        or item.get("cancelled")):
                    continue
                due = False
                for fup in item_followups(item):
                    d = fup.get("date") or ""
                    if d and d != "someday" and d <= today_iso:
                        out["fups"].append((pdir, kind, item, fup))
                        due = True
                    elif d and d != "someday" and d <= end.isoformat():
                        out["upcoming"].append((d, pdir, kind, item, fup))
                if kind not in ("tasks", "milestones"):
                    continue
                if item.get("status") != "pending":
                    continue
                d = item.get("date")
                if not d:
                    if not due:             # ya sale en ⏩ Por triar
                        out["undated"].append((pdir, kind, item))
                elif d < today_iso and not item.get("recur"):
                    out["overdue"].append((pdir, kind, item))
    if by_day is None:
        by_day = collect_items_by_day(today, end, include_federated=False)
    if cronos is None:
        cronos = _collect_cronogramas(include_federated=False)
    for day, items in by_day.items():
        for kind, item, pdir, _md in items:
            if kind == "reminders" or str(pdir) not in keep:
                continue
            out["upcoming"].append((day, pdir, kind, item, None))
    out["fups"].sort(key=lambda r: (r[3]["date"], r[2].get("desc") or ""))
    out["overdue"].sort(key=lambda r: (r[2].get("date") or "",
                                       r[2].get("desc") or ""))
    out["upcoming"].sort(key=lambda r: (r[0], r[4] is not None,
                                        (r[3].get("time") or ""),
                                        r[3].get("desc") or ""))
    out["undated"].sort(key=lambda r: (0 if r[1] == "milestones" else 1,))
    out["cronos"] = [c for c in cronos if str(c[0]) in keep]
    return out


def counts(data: dict) -> dict:
    return {k: len(v) for k, v in data.items()}


def _fup_rows(data, today) -> list:
    rows = []
    for pdir, kind, item, fup in data["fups"]:
        desc = _desc_with_event_indicators(kind, item, pdir)
        if fup.get("desc"):
            desc += f" — {fup['desc']}".replace("|", "\\|")
        late = "❗" if fup["date"] < today.isoformat() else ""
        rows.append(_row(kind, f"{late}⏩", _short(fup["date"], today), "",
                         desc, pdir))
    return rows


def _overdue_rows(data, today) -> list:
    return [_row(kind, "⚠️", _short(item.get("date"), today),
                 item.get("time") or "",
                 _desc_with_event_indicators(kind, item, pdir), pdir)
            for pdir, kind, item in data["overdue"]]


def _upcoming_rows(data, today) -> list:
    rows = []
    for day, pdir, kind, item, fup in data["upcoming"]:
        desc = _desc_with_event_indicators(kind, item, pdir)
        if fup is not None:
            if fup.get("desc"):
                desc += f" — {fup['desc']}".replace("|", "\\|")
            rows.append(_row(kind, "⏩", _short(day, today), "", desc, pdir))
            continue
        when = _short(day, today)
        if day == today.isoformat():
            when = f"**{when}**"
        rows.append(_row(kind, "", when, item.get("time") or "", desc, pdir))
    return rows


def _undated_rows(data, today) -> list:
    return [_row(kind, _next_fup(item, today), "", "",
                 _desc_with_event_indicators(kind, item, pdir), pdir)
            for pdir, kind, item in data["undated"]]


def _crono_rows(data, today) -> list:
    from core.cronograma import _deadline_short_str
    from views.secretary.cronos import _crono_link_md
    rows = ["| Proyecto | Cronograma | Progreso |  | Deadline |",
            "|---|---|---|---|---|"]
    for pdir, name, done, total, deadline, crono_file in data["cronos"]:
        pct = done * 100 // total if total else 0
        filled = round(pct / 10)
        bar = "█" * filled + "░" * (10 - filled)
        rows.append(f"| {proj_link_md(pdir)} | {_crono_link_md(crono_file, name)} "
                    f"| {bar} | {done}/{total} ({pct}%) "
                    f"| {_deadline_short_str(done, total, deadline, today)} |")
    return rows


def _next_day(family, today):
    for i in range(1, 8):
        d = today + timedelta(days=i)
        if family.is_day(d):
            return d
    return None


def oldest_fup_days(data: dict, today) -> int:
    """Días del ⏩ vencido más antiguo (0 si no hay): que plegar no esconda
    la deuda (ADR-060)."""
    dates = [fup["date"] for _p, _k, _i, fup in data.get("fups", [])]
    return (today - _date.fromisoformat(min(dates))).days if dates else 0


def fups_mark(n: int, oldest: int) -> str:
    """``⏩5 (23 d)``; sin la antigüedad si es de hoy."""
    return f"⏩{n}" + (f" ({oldest} d)" if oldest else "")


def summary_parts(c: dict, oldest: int = 0) -> list:
    """``⏩5 (23 d) · ⚠️2 · 🗂️14 sin fecha`` (solo lo que no es 0)."""
    parts = []
    if c.get("fups"):
        parts.append(fups_mark(c["fups"], oldest))
    if c.get("overdue"):
        parts.append(f"⚠️{c['overdue']}")
    if c.get("undated"):
        parts.append(f"🗂️{c['undated']} sin fecha")
    return parts


def page_lines(family, dirs, data, today) -> list:
    from core.families import DAY_NAMES
    c = counts(data)
    is_day = family.is_day(today)
    if not family.days:
        when = "sin día asignado"
    elif is_day:
        when = f"{family.days_label} · **hoy es su día**"
    else:
        nd = _next_day(family, today)
        when = (f"{family.days_label} · próximo: {DAY_NAMES[nd.weekday()]} "
                f"{nd.strftime('%m-%d')}")
    lines = [autogen_banner("secretary.families").rstrip(), "",
             f"# {family.label}", "",
             f"> 📆 {when}",
             "> Proyectos: " + (" · ".join(proj_link_md(p) for p in dirs)
                                or "*ninguno*")]
    parts = summary_parts(c, oldest_fup_days(data, today))
    if c["upcoming"]:
        parts.append(f"📅{c['upcoming']} próximas")
    if c["cronos"]:
        parts.append(f"📊{c['cronos']} cronos")
    lines.append("> " + (" · ".join(parts) if parts else "nada pendiente"))
    lines.append("")

    sections = [
        ("warning", f"⏩ Por triar ({c['fups']})", _fup_rows, "fups", is_day),
        ("warning", f"⚠️ Vencidas ({c['overdue']})", _overdue_rows, "overdue",
         is_day),
        ("note", f"📅 Próximas · {UPCOMING_DAYS} días ({c['upcoming']})",
         _upcoming_rows, "upcoming", False),
        ("note", f"🗂️ Sin fecha ({c['undated']})", _undated_rows, "undated",
         False),
    ]
    for kind, title, fn, key, open_ in sections:
        if not data[key]:
            continue
        lines.extend(callout(title, [FAMILY_HEADER] + fn(data, today), open_,
                             kind))
        lines.append("")
    if data["cronos"]:
        lines.extend(callout(f"📊 Cronogramas ({c['cronos']})",
                             _crono_rows(data, today), False))
        lines.append("")
    return [_relink(line) for line in lines]


def family_link(family, from_secretary: bool = True) -> str:
    """``🟣 [hk](families/hk.md)`` desde `📊panel/secretary/`."""
    prefix = f"{DIRNAME}/" if from_secretary else ""
    head = f"{family.emoji} " if family.emoji else ""
    return f"{head}[{family.name}]({prefix}{family.name}.md)"


def collect_all(today, families=None) -> list:
    """``[(familia, dirs, data)]`` en el orden de ``orbit.json``."""
    from core.families import family_of, load_families
    from core.panel import _collect_cronogramas
    from views.secretary._agenda_table import collect_items_by_day
    from views.secretary.agenda import _iter_local_projects
    fams = load_families() if families is None else families
    if not fams:
        return []
    by_name = {f.name: [] for f in fams}
    for pdir in _iter_local_projects():
        f = family_of(pdir, fams)
        if f is not None:
            by_name[f.name].append(pdir)
    by_day = collect_items_by_day(today, today + timedelta(days=UPCOMING_DAYS),
                                  include_federated=False)
    cronos = _collect_cronogramas(include_federated=False)
    return [(f, by_name[f.name], collect(by_name[f.name], today, by_day, cronos))
            for f in fams]


def generate(out_dir: Path, today=None, allf=None) -> int:
    """Escribe una hoja por familia en *out_dir* y borra las de familias que
    ya no existen. Devuelve cuántas hojas hay. *allf*: ``collect_all`` ya
    hecho (lo comparte `agenda.md`)."""
    today = today or _date.today()
    if allf is None:
        allf = collect_all(today)
    if not allf and not out_dir.exists():
        return 0
    out_dir.mkdir(parents=True, exist_ok=True)
    names = set()
    for family, dirs, data in allf:
        names.add(f"{family.name}.md")
        (out_dir / f"{family.name}.md").write_text(
            "\n".join(page_lines(family, dirs, data, today)) + "\n")
    for old in out_dir.glob("*.md"):
        if old.name not in names:
            old.unlink()
    return len(allf)

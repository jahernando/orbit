"""migrate.py — migrate old-format projects to the new project structure.

Old format:
  {emoji}ProjectName.md  ← tipo, estado, prioridad, objetivo, tareas, referencias
  📓ProjectName.md       ← logbook (multi-line entries)

New format:
  project.md    ← metadatos
  logbook.md    ← single-line entries (YYYY-MM-DD content #type)
  highlights.md ← referencias, resultados, decisiones, ideas
  agenda.md     ← tareas, hitos, eventos
  notes/        ← multi-line logbook entries as individual .md files
"""

import re
import sys
from datetime import date
from pathlib import Path
from typing import Optional

from core.log import PROJECTS_DIR, project_file_path

TEMPLATES_DIR = Path(__file__).parent.parent / "📐templates"

# ── Status / type maps ────────────────────────────────────────────────────────

_STATUS_MAP = {
    "en marcha": "active",
    "activo":    "active",
    "active":    "active",
    "parado":    "paused",
    "pausado":   "paused",
    "paused":    "paused",
    "durmiendo": "sleeping",
    "sleeping":  "sleeping",
    "inicial":   "active",
    "completado": "sleeping",
}

_TYPE_MAP = {
    "📚": "docencia",
    "🌀": "investigacion",
    "⚙️": "gestion",
    "💻": "software",
    "🌿": "personal",
    "📖": "formacion",
    "☀️": "mision",
}

_TYPE_LABEL = {
    "docencia":     "📚 Docencia",
    "investigacion":"🌀 Investigación",
    "gestion":      "⚙️ Gestión",
    "software":     "💻 Software",
    "personal":     "🌿 Personal",
    "formacion":    "📖 Formación",
    "mision":       "☀️ Misión",
}

_PRIO_MAP = {
    "alta": "Alta", "high": "Alta",
    "media": "Media", "medium": "Media",
    "baja": "Baja", "low": "Baja",
}

_DATE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})")


# ── Old-format file detection ─────────────────────────────────────────────────

def _is_old_project(project_dir: Path) -> bool:
    """Old format: has no project.md / {name}-project.md but has {emoji}Name.md."""
    if (project_dir / "project.md").exists():
        return False
    if project_file_path(project_dir, "project").exists():
        return False
    return any(
        f.suffix == ".md" and not f.name.startswith("📓")
        for f in project_dir.iterdir()
    )


def _find_old_files(project_dir: Path) -> tuple:
    """Return (proyecto_path, logbook_path) for old-format project."""
    proyecto = logbook = None
    for f in project_dir.iterdir():
        if f.suffix != ".md":
            continue
        if f.name.startswith("📓"):
            logbook = f
        elif not f.name.startswith("."):
            proyecto = f
    return proyecto, logbook


# ── Parse old proyecto.md ─────────────────────────────────────────────────────

def _parse_old_proyecto(path: Path) -> dict:
    """Parse old {emoji}Name.md into structured dict."""
    lines = path.read_text().splitlines()

    result = {
        "tipo_key": "investigacion",
        "tipo_label": "🌀 Investigación",
        "estado": "[auto]",
        "prioridad": "Media",
        "objetivo": "",
        "tareas": [],      # list of (status, text)
        "refs": [],        # list of (text, url)
        "resultados": [],
        "decisiones": [],
        "ideas": [],
    }

    current_section = None

    for line in lines:
        s = line.strip()

        # Detect tipo from emoji line (e.g. "📚 Docencia")
        for emoji, key in _TYPE_MAP.items():
            if s.startswith(emoji) and len(s) < 30 and "##" not in s and "#" not in s:
                result["tipo_key"] = key
                result["tipo_label"] = _TYPE_LABEL.get(key, s)
                break

        # Detect estado
        for keyword, mapped in _STATUS_MAP.items():
            if keyword in s.lower() and len(s) < 30 and "##" not in s:
                result["estado"] = mapped
                break

        # Detect prioridad
        for prio in ("alta", "media", "baja"):
            if s.lower() == prio:
                result["prioridad"] = _PRIO_MAP[prio]
                break

        # Section headers
        if s.startswith("## 🎯") or s.startswith("## Objetivo"):
            current_section = "objetivo"
            continue
        if s.startswith("## ✅") or "Tareas" in s and s.startswith("##"):
            current_section = "tareas"
            continue
        if s.startswith("## 📎") or "Referencia" in s and s.startswith("##"):
            current_section = "refs"
            continue
        if s.startswith("## 📊") or "Resultado" in s and s.startswith("##"):
            current_section = "resultados"
            continue
        if s.startswith("## 📌") or "Decision" in s and s.startswith("##"):
            current_section = "decisiones"
            continue
        if s.startswith("## 💡") or "Idea" in s and s.startswith("##"):
            current_section = "ideas"
            continue
        if s.startswith("## 📓") or s.startswith("## Logbook"):
            current_section = None
            continue
        if s.startswith("##"):
            current_section = None
            continue

        if not s or s.startswith("#"):
            if current_section == "objetivo" and s.startswith("# "):
                pass  # title line, skip
            elif current_section == "objetivo" and s:
                pass
            continue

        if current_section == "objetivo":
            if s and not s.startswith("[Ver"):
                result["objetivo"] = (result["objetivo"] + " " + s).strip()

        elif current_section == "tareas":
            m = re.match(r"^- \[([ x])\] (.+)$", s)
            if m:
                status = "done" if m.group(1) == "x" else "pending"
                result["tareas"].append((status, m.group(2).strip()))

        elif current_section == "refs":
            _parse_link_line(s, result["refs"])

        elif current_section == "resultados":
            _parse_link_line(s, result["resultados"])

        elif current_section == "decisiones":
            if s.startswith("- "):
                result["decisiones"].append(s[2:].strip())

        elif current_section == "ideas":
            if s.startswith("- "):
                result["ideas"].append(s[2:].strip())

    return result


def _parse_link_line(s: str, target: list) -> None:
    """Parse '- [Title](url)' or '- text' into target list as (text, url)."""
    if not s.startswith("- "):
        return
    content = s[2:].strip()
    m = re.match(r"^\[([^\]]+)\]\(([^)]+)\)", content)
    if m:
        target.append((m.group(1), m.group(2)))
    elif content:
        target.append((content, ""))


# ── Parse old logbook 📓Name.md ───────────────────────────────────────────────

def _parse_old_logbook(path: Path) -> list:
    """Parse old logbook into list of entry dicts.

    Each entry:
      {date, type, text, is_multiline, bullets}

    is_multiline=True  → date+type on first line, bullets follow
    is_multiline=False → everything on one line
    """
    if not path or not path.exists():
        return []

    lines = path.read_text().splitlines()
    entries = []
    current = None

    for line in lines:
        # Skip comment lines and blank lines between sections
        if line.startswith("<!--") or line.startswith("# Logbook"):
            continue

        dm = _DATE_RE.match(line)
        if dm:
            # Save previous entry
            if current:
                entries.append(current)

            date_str = dm.group(1)
            rest = line[len(date_str):].strip()

            # Extract type: look for #type at end
            type_m = re.search(r"#(\w+)\s*$", rest)
            entry_type = type_m.group(1) if type_m else "apunte"
            text_without_type = re.sub(r"\s*#\w+\s*$", "", rest).strip()

            is_multiline = not bool(text_without_type)

            current = {
                "date": date_str,
                "type": entry_type,
                "text": text_without_type,
                "is_multiline": is_multiline,
                "bullets": [],
            }
        elif current and line.strip().startswith("-") or (
            current and line.startswith("  ") and line.strip()
        ):
            # Bullet point of current multi-line entry
            stripped = line.strip()
            if stripped.startswith("- "):
                current["bullets"].append(stripped[2:])
            elif stripped:
                current["bullets"].append(stripped)
        # blank lines between entries are ok

    if current:
        entries.append(current)

    return entries


# ── Build new file content ────────────────────────────────────────────────────

def _build_project_md(dir_name: str, meta: dict) -> str:
    """Build new project.md content from parsed old metadata."""
    tpl = TEMPLATES_DIR / "project.md"
    if tpl.exists():
        from core.log import _base_name
        # _base_name expects a Path whose .name is the dir name
        base = _base_name(Path(dir_name))
        content = tpl.read_text()
        content = content.replace("{{PROJECT_NAME}}", dir_name)
        content = content.replace("{{BASE_NAME}}", base)
        content = content.replace("{{TYPE_EMOJI}}", meta["tipo_label"].split()[0])
        content = content.replace("{{TYPE_LABEL}}", " ".join(meta["tipo_label"].split()[1:]))
        content = content.replace("{{PRIORITY_LABEL}}", meta["prioridad"])
        obj = meta["objetivo"] or "Descripción breve del objetivo."
        content = content.replace("{{OBJECTIVE}}", obj)
        # Set declared status
        content = re.sub(r"- Estado:.*", f"- Estado: {meta['estado']}", content)
        return content

    # Fallback if no template
    from core.log import _base_name as _bn
    b = _bn(Path(dir_name))
    return f"""# {dir_name}
- Tipo: {meta['tipo_label']}
- Estado: {meta['estado']}
- Prioridad: {meta['prioridad']}

## Objetivo
{meta['objetivo'] or 'Descripción breve del objetivo.'}

---
[logbook](./{b}-logbook.md) · [highlights](./{b}-highlights.md) · [agenda](./{b}-agenda.md) · [notes/](./notes/)
"""


def _build_highlights_md(meta: dict) -> str:
    """Build highlights.md from old refs/resultados/decisiones/ideas."""
    sections = []

    if meta["refs"]:
        items = "\n".join(
            f"- [{t}]({u})" if u else f"- {t}"
            for t, u in meta["refs"]
        )
        sections.append(f"## 📚 Referencias\n{items}")

    if meta["resultados"]:
        items = "\n".join(
            f"- [{t}]({u})" if u else f"- {t}"
            for t, u in meta["resultados"]
        )
        sections.append(f"## 🔬 Resultados\n{items}")

    if meta["decisiones"]:
        items = "\n".join(f"- {d}" for d in meta["decisiones"])
        sections.append(f"## 🏛️ Decisiones\n{items}")

    if meta["ideas"]:
        items = "\n".join(f"- {i}" for i in meta["ideas"])
        sections.append(f"## 💡 Ideas\n{items}")

    return "\n\n".join(sections) + "\n" if sections else ""


def _build_agenda_md(meta: dict) -> str:
    """Build agenda.md from old tasks."""
    parts = ["## ✅ Tareas\n"]
    has_tasks = False
    for status, text in meta["tareas"]:
        char = "x" if status == "done" else " "
        parts.append(f"- [{char}] {text}")
        has_tasks = True

    task_block = "\n".join(parts) if has_tasks else "## ✅ Tareas"
    return f"{task_block}\n\n## 🏁 Hitos\n\n## 📅 Eventos\n"


def _build_logbook_md(dir_name: str, entries: list, notes_dir: Path,
                      dry_run: bool) -> tuple:
    """Build new logbook.md content. Creates note files for multi-line entries.

    Returns (logbook_text, list_of_created_note_filenames).
    """
    today = date.today().isoformat()
    header = f"# Logbook — {dir_name}\n\n"
    lines = []
    created_notes = []

    # Count per date to avoid filename collisions
    date_count: dict = {}

    for entry in reversed(entries):   # chronological order
        d = entry["date"]
        t = entry["type"]

        if not entry["is_multiline"] or not entry["bullets"]:
            # Single-line → keep as-is
            text = entry["text"] or f"[{t}]"
            lines.append(f"{d} {text} #{t}")
        else:
            # Multi-line → create note file
            date_count[d] = date_count.get(d, 0) + 1
            suffix = f"_{date_count[d]}" if date_count[d] > 1 else ""
            note_name = f"{d}{suffix}.md"
            note_path = notes_dir / note_name

            # Build note content
            bullet_text = "\n".join(f"- {b}" for b in entry["bullets"])
            note_content = f"# {d} — {t}\n\n{bullet_text}\n"

            if not dry_run:
                note_path.write_text(note_content)
            created_notes.append(note_name)

            # Logbook summary line pointing to note
            lines.append(f"{d} [ver nota](./notes/{note_name}) #{t}")

    logbook_text = header + "\n".join(lines) + "\n"
    return logbook_text, created_notes


# ── Main migration function ───────────────────────────────────────────────────

def run_migrate(name: str, dry_run: bool = False, force: bool = False) -> int:
    """Migrate an old-format project to new format.

    Finds old files, parses them, and creates:
      project.md, logbook.md, highlights.md, agenda.md, notes/
    Old files are kept (renamed with .old suffix) for safety.
    """
    # Find project directory
    name_low = name.lower()
    candidates = [
        d for d in PROJECTS_DIR.iterdir()
        if d.is_dir() and _is_old_project(d)
        and name_low in d.name.lower()
    ]
    if not candidates:
        # Maybe already migrated or not found
        all_dirs = [d for d in PROJECTS_DIR.iterdir() if d.is_dir()]
        match = [d for d in all_dirs if name_low in d.name.lower()]
        if match and ((match[0] / "project.md").exists() or project_file_path(match[0], "project").exists()):
            print(f"El proyecto '{name}' ya está en el nuevo formato.")
            return 0
        print(f"Error: proyecto '{name}' no encontrado en formato antiguo.")
        return 1
    if len(candidates) > 1:
        names = ", ".join(d.name for d in candidates)
        print(f"Error: '{name}' es ambiguo: {names}")
        return 1

    project_dir = candidates[0]
    proyecto_file, logbook_file = _find_old_files(project_dir)

    if not proyecto_file:
        print(f"Error: no se encontró el fichero de proyecto en {project_dir}")
        return 1

    # Parse old content
    meta    = _parse_old_proyecto(proyecto_file)
    entries = _parse_old_logbook(logbook_file) if logbook_file else []

    # Preview
    n_single = sum(1 for e in entries if not e["is_multiline"] or not e["bullets"])
    n_multi  = len(entries) - n_single

    print(f"\nMigrando: {project_dir.name}")
    print(f"  Tipo: {meta['tipo_label']}  Estado: {meta['estado']}  Prioridad: {meta['prioridad']}")
    print(f"  Objetivo: {meta['objetivo'] or '(vacío)'}")
    print(f"  Referencias → highlights.md : {len(meta['refs'])}")
    print(f"  Resultados  → highlights.md : {len(meta['resultados'])}")
    print(f"  Decisiones  → highlights.md : {len(meta['decisiones'])}")
    print(f"  Ideas       → highlights.md : {len(meta['ideas'])}")
    print(f"  Tareas      → agenda.md     : {len(meta['tareas'])}")
    print(f"  Logbook entradas: {len(entries)}  ({n_single} single-line → logbook.md  |  {n_multi} multi-línea → notes/)")
    print()

    if dry_run:
        print("[dry-run] No se escribirá nada.")
        _preview_logbook(entries)
        return 0

    # Confirm unless --force
    if not force:
        if not sys.stdin.isatty():
            print("Error: usa --force para migrar en modo no interactivo.")
            return 1
        try:
            ans = input("¿Proceder con la migración? [s/N]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            return 1
        if ans not in ("s", "si", "sí", "y", "yes"):
            print("Cancelado.")
            return 0

    # Create notes/ dir
    notes_dir = project_dir / "notes"
    notes_dir.mkdir(exist_ok=True)

    # Build and write new files
    project_content    = _build_project_md(project_dir.name, meta)
    highlights_content = _build_highlights_md(meta)
    agenda_content     = _build_agenda_md(meta)
    logbook_content, created_notes = _build_logbook_md(
        project_dir.name, entries, notes_dir, dry_run=False
    )

    for kind, content in [("project", project_content), ("highlights", highlights_content),
                           ("agenda", agenda_content), ("logbook", logbook_content)]:
        dest = project_file_path(project_dir, kind)
        dest.write_text(content)
        print(f"  ✓  {dest.name}")
    for n in created_notes:
        print(f"  ✓  notes/{n}")

    print(f"\n✓ Migración completada: {project_dir.name}")
    print(f"  Los ficheros antiguos ({proyecto_file.name}, {logbook_file.name if logbook_file else '—'}) se mantienen como respaldo.")
    return 0


def _preview_logbook(entries: list) -> None:
    """Print a preview of how logbook entries would be migrated."""
    if not entries:
        print("  (logbook vacío)")
        return
    print("  Logbook preview:")
    for e in entries:
        if not e["is_multiline"] or not e["bullets"]:
            print(f"    logbook.md ← {e['date']} {e['text']} #{e['type']}")
        else:
            note_name = f"{e['date']}.md"
            print(f"    notes/{note_name} ← {e['date']} ({len(e['bullets'])} bullets)")
            print(f"    logbook.md ← {e['date']} [ver nota](./notes/{note_name}) #{e['type']}")


def run_migrate_all(dry_run: bool = False, force: bool = False) -> int:
    """Migrate all old-format projects in PROJECTS_DIR."""
    old_projects = [
        d for d in sorted(PROJECTS_DIR.iterdir())
        if d.is_dir() and _is_old_project(d)
    ]
    if not old_projects:
        print("No se encontraron proyectos en formato antiguo.")
        return 0

    print(f"Proyectos a migrar: {len(old_projects)}")
    for d in old_projects:
        print(f"  {d.name}")
    print()

    if not dry_run and not force:
        if not sys.stdin.isatty():
            print("Error: usa --force para migrar todos en modo no interactivo.")
            return 1
        try:
            ans = input(f"¿Migrar los {len(old_projects)} proyectos? [s/N]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            return 1
        if ans not in ("s", "si", "sí", "y", "yes"):
            print("Cancelado.")
            return 0

    errors = 0
    for d in old_projects:
        rc = run_migrate(d.name, dry_run=dry_run, force=True)
        if rc != 0:
            errors += 1

    print(f"\n{'[dry-run] ' if dry_run else ''}Migración completa: {len(old_projects) - errors} OK, {errors} errores.")
    return 0 if errors == 0 else 1

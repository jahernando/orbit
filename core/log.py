import sys
from datetime import date
from pathlib import Path
from typing import Optional

from core.config import PROJECTS_DIR, iter_project_dirs

VALID_TYPES = ["idea", "referencia", "apunte", "problema", "solucion", "resultado",
               "decision", "evaluacion",
               "plan", "tarea", "evento"]   # tarea/evento kept for backwards compat


def _base_name(project_dir: Path) -> str:
    """Extract base name from project dir, stripping emoji prefix.

    E.g. '💻orbit' → 'orbit', '☀️mission' → 'mission'.
    """
    name = project_dir.name
    # Strip leading non-ASCII (emoji) characters
    i = 0
    while i < len(name) and (ord(name[i]) > 127 or name[i] in '\ufe0f\u200d'):
        i += 1
    return name[i:] or name


# ── Standard project file names ──────────────────────────────────────────────

_FILE_SUFFIXES = {
    "project":    "-project.md",
    "logbook":    "-logbook.md",
    "highlights": "-highlights.md",
    "agenda":     "-agenda.md",
}


def project_file_path(project_dir: Path, kind: str = "project") -> Path:
    """Return the canonical path for a project file (new naming: {name}-{kind}.md)."""
    return project_dir / f"{_base_name(project_dir)}{_FILE_SUFFIXES[kind]}"


def find_proyecto_file(project_dir: Path) -> Optional[Path]:
    """Find the project index file. Search order:
    1. {name}-project.md  (new)
    2. project.md         (new-generic)
    3. proyecto.md        (legacy)
    4. {emoji}{name}.md   (old)
    """
    new = project_file_path(project_dir, "project")
    if new.exists():
        return new
    generic = project_dir / "project.md"
    if generic.exists():
        return generic
    legacy = project_dir / "proyecto.md"
    if legacy.exists():
        return legacy
    candidates = [f for f in project_dir.glob("*.md")
                  if not f.name.startswith("📓")
                  and not f.stem.endswith("-logbook")
                  and not f.stem.endswith("-highlights")
                  and not f.stem.endswith("-agenda")]
    return candidates[0] if len(candidates) == 1 else None


def find_logbook_file(project_dir: Path) -> Optional[Path]:
    """Find the logbook file. Search order:
    1. {name}-logbook.md  (new)
    2. logbook.md         (new-generic)
    3. 📓{name}.md        (old)
    """
    new = project_file_path(project_dir, "logbook")
    if new.exists():
        return new
    generic = project_dir / "logbook.md"
    if generic.exists():
        return generic
    candidates = list(project_dir.glob("📓*.md"))
    return candidates[0] if candidates else None


def find_highlights_file(project_dir: Path) -> Optional[Path]:
    """Find the highlights file."""
    new = project_file_path(project_dir, "highlights")
    if new.exists():
        return new
    generic = project_dir / "highlights.md"
    if generic.exists():
        return generic
    return None


def find_agenda_file(project_dir: Path) -> Optional[Path]:
    """Find the agenda file."""
    new = project_file_path(project_dir, "agenda")
    if new.exists():
        return new
    generic = project_dir / "agenda.md"
    if generic.exists():
        return generic
    return None


def resolve_file(project_dir: Path, kind: str) -> Path:
    """Find existing project file or return new-format path for creation.

    kind: "project" | "logbook" | "highlights" | "agenda"
    Always returns a valid Path (never None).
    """
    finders = {
        "project":    find_proyecto_file,
        "logbook":    find_logbook_file,
        "highlights": find_highlights_file,
        "agenda":     find_agenda_file,
    }
    found = finders[kind](project_dir)
    return found if found else project_file_path(project_dir, kind)


def find_project(name: str) -> Optional[Path]:
    matches = [d for d in iter_project_dirs() if name.lower() in d.name.lower()]

    if not matches:
        print(f"Error: no project found matching '{name}'")
        return None

    if len(matches) > 1:
        print(f"Ambiguous name '{name}'. Did you mean:")
        for m in sorted(matches):
            print(f"  {m.name}")
        return None

    return matches[0]


TAG_EMOJI = {
    "idea":        "💡",
    "referencia":  "📎",
    "apunte":      "📝",
    "problema":    "⚠️",
    "solucion":    "✔️",
    "resultado":   "📊",
    "decision":    "📌",
    "evaluacion":  "🔍",
    "plan":        "🗓️",
    "tarea":       "✅",   # legacy
    "evento":      "📅",   # legacy
}


def format_entry(message: str, tipo: str, path: Optional[str], fecha: Optional[str],
                 orbit: bool = False) -> str:
    date_str = fecha or date.today().isoformat()
    content  = f"[{message}]({path})" if path else message
    emoji    = TAG_EMOJI.get(tipo, "")
    suffix   = " [O]" if orbit else ""
    return f"{date_str} {emoji} {content} #{tipo}{suffix}\n"


def _append_entry(logbook_path: Path, entry: str) -> None:
    """Append an entry ensuring a blank line separator for markdown readability."""
    from core.undo import save_snapshot
    save_snapshot(logbook_path)
    existing = logbook_path.read_text() if logbook_path.exists() else ""
    with open(logbook_path, "a") as f:
        if existing and not existing.endswith("\n\n"):
            f.write("" if existing.endswith("\n") else "\n")
            f.write("\n")
        f.write(entry)


def log_to_mission(message: str, tipo: str) -> None:
    """Append a logbook entry to the mission project (silently skips if not found)."""
    mission_dir = next(
        (d for d in iter_project_dirs() if "mission" in d.name.lower()),
        None,
    )
    if not mission_dir:
        return
    logbook = find_logbook_file(mission_dir)
    if not logbook:
        return
    entry = format_entry(message, tipo, None, None)
    _append_entry(logbook, entry)
    print(f"  → mission: {entry.strip()}")


def init_logbook(logbook_path: Path, project_name: str) -> None:
    logbook_path.write_text(
        f"# Logbook — {project_name}\n\n"
        "<!-- Tipos: #idea #referencia #apunte #problema #solucion #resultado #decision #evaluacion #plan -->\n\n"
    )


def _is_new_project(project_dir: Path) -> bool:
    """New-model project: has {name}-project.md or project.md in root."""
    return find_proyecto_file(project_dir) is not None and (
        project_file_path(project_dir, "project").exists()
        or (project_dir / "project.md").exists()
    )


def add_entry(project: str, message: str, tipo: str, path: Optional[str],
              fecha: Optional[str], orbit: bool = False) -> int:
    if fecha:
        try:
            entry_date = date.fromisoformat(fecha)
        except ValueError:
            print(f"Error: fecha '{fecha}' no es válida. Usa formato YYYY-MM-DD")
            return 1
        if entry_date > date.today():
            print(f"Error: la fecha {fecha} es futura. Las entradas deben ser de hoy o anteriores")
            return 1

    project_dir = find_project(project)
    if not project_dir:
        return 1

    logbook_path = resolve_file(project_dir, "logbook")

    if not logbook_path.exists():
        init_logbook(logbook_path, project_dir.name)

    entry = format_entry(message, tipo, path, fecha, orbit=orbit)
    _append_entry(logbook_path, entry)
    print(f"✓ [{project_dir.name}] {entry.strip()}")

    # For old-format projects only: auto-update status to "en marcha"
    if not _is_new_project(project_dir):
        proyecto_path = find_proyecto_file(project_dir)
        if proyecto_path:
            from core.tasks import load_project_meta, update_proyecto_field
            meta = load_project_meta(proyecto_path)
            if "en marcha" not in meta["estado_raw"] and "completado" not in meta["estado_raw"]:
                update_proyecto_field(proyecto_path, "estado", "en marcha")
                print(f"  → estado: en marcha")

    return 0


def _is_url(ref: str) -> bool:
    return ref.startswith("http://") or ref.startswith("https://")


def _ask_deliver() -> bool:
    """Ask user interactively whether to deliver file to cloud."""
    if not sys.stdin.isatty():
        return False
    try:
        ans = input("  📦 ¿Entregar fichero a cloud? [s/N]: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        return False
    return ans in ("s", "si", "sí", "y", "yes")


def add_entry_with_ref(project: str, ref: Optional[str], message: str,
                       tipo: str, fecha: Optional[str],
                       deliver: bool = False, orbit: bool = False) -> int:
    """Add a logbook entry, handling URL/file/deliver logic.

    - ref is URL → link title to URL
    - ref is file + --deliver → copy to cloud/logs/ with date prefix, link to cloud
    - ref is file (no --deliver) → link to local file, ask if deliver
    - ref is None → plain entry
    """
    from core.deliver import deliver_file, IMAGE_EXTS, encode_cloud_link

    project_dir = find_project(project)
    if not project_dir:
        return 1

    link = None
    is_image = False

    if ref:
        if _is_url(ref):
            link = ref
        else:
            src = Path(ref).expanduser()
            if not src.is_absolute():
                candidate = project_dir / ref
                if candidate.exists():
                    src = candidate
                else:
                    src = Path.cwd() / ref
            if src.exists():
                is_image = src.suffix.lower() in IMAGE_EXTS
                should_deliver = deliver or _ask_deliver()

                if should_deliver:
                    dest = deliver_file(project_dir, src, subdir="logs", date_prefix=True)
                    if not dest:
                        return 1
                    link = encode_cloud_link(str(dest))
                else:
                    link = str(src)
            elif deliver:
                print(f"Error: no existe {src}")
                return 1
            else:
                link = ref  # keep as-is (relative path or manual reference)

    rc = add_entry(project, message, tipo, link, fecha, orbit=orbit)
    if rc != 0:
        return rc

    # Append image preview if delivered image
    if is_image and link:
        logbook = find_logbook_file(project_dir)
        if logbook and logbook.exists():
            with open(logbook, "a") as f:
                f.write(f"  ![{message}]({link})\n")

    return 0


def add_orbit_entry(project_dir: Path, message: str, tipo: str = "apunte") -> None:
    """Write an Orbit-authored entry [O] to the project logbook. Never raises."""
    try:
        logbook_path = resolve_file(project_dir, "logbook")
        if not logbook_path.exists():
            init_logbook(logbook_path, project_dir.name)
        entry = format_entry(message, tipo, None, None, orbit=True)
        _append_entry(logbook_path, entry)
    except Exception:
        pass  # lifecycle events must never crash the caller

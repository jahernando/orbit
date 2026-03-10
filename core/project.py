import re
import shutil
import sys
import unicodedata
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

from core.log import PROJECTS_DIR, find_logbook_file, find_proyecto_file, resolve_file
from core.tasks import TYPE_MAP, PRIORITY_MAP, normalize
from core.open import open_file

from core.config import TEMPLATES_DIR, get_type_label

TYPE_LABEL = get_type_label()

# ── Status inference thresholds ───────────────────────────────────────────────
_ACTIVE_DAYS  = 14
_PAUSED_DAYS  = 60

_STATUS_EMOJI = {
    "new":      "⬜",
    "active":   "▶️",
    "paused":   "⏸️",
    "sleeping": "💤",
}
_STATUS_LABEL = {
    "new":      "Nuevo",
    "active":   "Activo",
    "paused":   "Pausado",
    "sleeping": "Durmiendo",
}
_STATUS_VALID = {"active", "paused", "sleeping", "activo", "pausado", "durmiendo"}
_STATUS_NORM  = {
    "activo":    "active",
    "pausado":   "paused",
    "durmiendo": "sleeping",
    "active":    "active",
    "paused":    "paused",
    "sleeping":  "sleeping",
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _is_new_project(project_dir: Path) -> bool:
    """New-model project: has {name}-project.md or project.md."""
    from core.log import project_file_path
    return (project_file_path(project_dir, "project").exists()
            or (project_dir / "project.md").exists())


def _infer_status(project_dir: Path) -> tuple:
    """Return (status_key, days_since_last_entry) from logbook activity."""
    logbook = find_logbook_file(project_dir)
    if not logbook or not logbook.exists():
        return "new", 0

    today    = date.today()
    last_day = None
    date_re  = re.compile(r"^(\d{4}-\d{2}-\d{2})\s")

    for line in logbook.read_text().splitlines():
        m = date_re.match(line)
        if m:
            try:
                d = date.fromisoformat(m.group(1))
                if last_day is None or d > last_day:
                    last_day = d
            except ValueError:
                pass

    if last_day is None:
        return "new", 0

    days = (today - last_day).days
    if days <= _ACTIVE_DAYS:
        return "active", days
    elif days <= _PAUSED_DAYS:
        return "paused", days
    else:
        return "sleeping", days


def _read_project_meta(project_dir: Path) -> dict:
    """Read metadata from new-format project.md. Returns dict with keys:
    name, tipo_emoji, tipo_label, prioridad, estado_raw."""
    project_file = find_proyecto_file(project_dir)
    meta = {
        "name":       project_dir.name,
        "tipo_emoji": "",
        "tipo_label": "",
        "prioridad":  "media",
        "estado_raw": "[auto]",
    }
    if not project_file or not project_file.exists():
        return meta

    for line in project_file.read_text().splitlines():
        s = line.strip()
        if s.startswith("# "):
            meta["name"] = s[2:].strip()
        elif s.startswith("- Tipo:"):
            tipo_val = s[7:].strip()       # e.g. "🌀 Investigación"
            parts = tipo_val.split(None, 1)
            meta["tipo_emoji"] = parts[0] if parts else ""
            meta["tipo_label"] = parts[1] if len(parts) > 1 else tipo_val
        elif s.startswith("- Estado:"):
            raw = s[9:].strip()
            # Strip emoji prefix if present (e.g. "▶️ Activo" → normalize to key)
            for key, emoji in _STATUS_EMOJI.items():
                if raw.startswith(emoji):
                    raw = key
                    break
            else:
                # Also accept label (e.g. "Activo" → "active")
                for key, label in _STATUS_LABEL.items():
                    if raw.lower() == label.lower():
                        raw = key
                        break
            meta["estado_raw"] = raw
        elif s.startswith("- Prioridad:"):
            raw = s[12:].strip()
            # Strip emoji prefix if present (e.g. "🔴 Alta" → "Alta")
            for emoji in PRIORITY_MAP.values():
                if raw.startswith(emoji):
                    raw = raw[len(emoji):].strip()
                    break
            meta["prioridad"] = raw

    return meta


def _resolve_status(meta: dict, project_dir: Path) -> tuple:
    """Return (status_key, display_str, is_auto) for a project."""
    raw = meta.get("estado_raw", "[auto]")
    if raw == "[auto]":
        status, days = _infer_status(project_dir)
        label   = f"{_STATUS_EMOJI[status]} {_STATUS_LABEL[status]}"
        display = f"{label} (auto, {days}d)"
        return status, display, True
    else:
        key     = _STATUS_NORM.get(raw.lower(), raw.lower())
        emoji   = _STATUS_EMOJI.get(key, "❓")
        label   = _STATUS_LABEL.get(key, raw)
        display = f"{emoji} {label}"
        return key, display, False


# ── project create ────────────────────────────────────────────────────────────

def run_project_create(name: str, tipo: str, prioridad: str) -> int:
    """Create a new project with the new file structure."""
    tipo_key = normalize(tipo)
    if tipo_key not in TYPE_MAP:
        valid = ", ".join(k for k in TYPE_MAP if "ó" not in k)
        print(f"Error: tipo '{tipo}' no válido. Opciones: {valid}")
        return 1

    prio_key = normalize(prioridad)
    if prio_key not in PRIORITY_MAP:
        print(f"Error: prioridad '{prioridad}' no válida. Opciones: alta, media, baja")
        return 1

    tipo_emoji = TYPE_MAP[tipo_key]
    tipo_label = TYPE_LABEL.get(tipo_key, tipo.capitalize())
    prio_emoji = PRIORITY_MAP[prio_key]
    prio_label = prio_key.capitalize()

    dir_name    = f"{tipo_emoji}{name.lower()}"
    project_dir = PROJECTS_DIR / dir_name

    if project_dir.exists():
        print(f"Error: ya existe el proyecto en {project_dir}")
        return 1

    for tpl in ["project.md", "logbook.md", "highlights.md", "agenda.md"]:
        if not (TEMPLATES_DIR / tpl).exists():
            print(f"Error: plantilla '{tpl}' no encontrada en {TEMPLATES_DIR}")
            return 1

    print(f"\nObjetivo del proyecto (intro para dejarlo en blanco):")
    try:
        objetivo = input("> ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        objetivo = ""

    project_dir.mkdir(parents=True)
    (project_dir / "notes").mkdir()

    from core.log import project_file_path, _base_name
    base = _base_name(project_dir)

    subs = {
        "{{PROJECT_NAME}}":    dir_name,
        "{{BASE_NAME}}":       base,
        "{{TYPE_EMOJI}}":      tipo_emoji,
        "{{TYPE_LABEL}}":      tipo_label,
        "{{PRIORITY_EMOJI}}":  prio_emoji,
        "{{PRIORITY_LABEL}}":  prio_label,
        "{{OBJECTIVE}}":       objetivo or "Descripción breve del objetivo.",
    }

    for kind in ["project", "logbook", "highlights", "agenda"]:
        content = (TEMPLATES_DIR / f"{kind}.md").read_text()
        for k, v in subs.items():
            content = content.replace(k, v)
        dest = project_file_path(project_dir, kind)
        dest.write_text(content)

    print(f"✓ Proyecto creado: {project_dir}")
    for kind in ["project", "logbook", "highlights", "agenda"]:
        print(f"  {project_file_path(project_dir, kind)}")
    print(f"  {project_dir / 'notes/'}")
    return 0


# ── project list ──────────────────────────────────────────────────────────────

_PRIO_ORDER = {"alta": 0, "media": 1, "baja": 2}
_STATUS_ORDER = {"active": 0, "paused": 1, "new": 2, "sleeping": 3}


def run_project_list(status_filter: Optional[str] = None,
                     tipo_filter:   Optional[str] = None,
                     sort_by:       Optional[str] = None) -> int:
    """List projects with emoji-only columns for tipo, estado, prioridad."""
    rows = []
    for d in sorted(PROJECTS_DIR.iterdir()):
        if not d.is_dir():
            continue
        if not _is_new_project(d):
            continue

        meta             = _read_project_meta(d)
        status, _, _ = _resolve_status(meta, d)

        # Apply filters
        if status_filter:
            sf = _STATUS_NORM.get(status_filter.lower(), status_filter.lower())
            if status != sf:
                continue
        if tipo_filter:
            if tipo_filter.lower() not in meta.get("tipo_label", "").lower():
                continue

        prio_key = normalize(meta["prioridad"])
        prio_emoji = PRIORITY_MAP.get(prio_key, "")
        status_emoji = _STATUS_EMOJI.get(status, "❓")
        tipo_emoji = meta["tipo_emoji"] or "❓"

        rows.append({
            "name":         meta["name"],
            "tipo_emoji":   tipo_emoji,
            "status_emoji": status_emoji,
            "prio_emoji":   prio_emoji,
            "status_key":   status,
            "prio_key":     prio_key,
            "tipo_label":   meta.get("tipo_label", ""),
        })

    if not rows:
        print("No se encontraron proyectos" +
              (f" con estado '{status_filter}'" if status_filter else "") + ".")
        return 0

    # Sort
    if sort_by == "type":
        rows.sort(key=lambda r: r["tipo_label"].lower())
    elif sort_by == "status":
        rows.sort(key=lambda r: _STATUS_ORDER.get(r["status_key"], 9))
    elif sort_by == "priority":
        rows.sort(key=lambda r: _PRIO_ORDER.get(r["prio_key"], 9))

    def _display_width(s: str) -> int:
        """Compute terminal display width accounting for wide chars/emojis."""
        w = 0
        chars = list(s)
        for i, ch in enumerate(chars):
            if ch == '\ufe0f':  # variation selector: previous char renders wide
                if w > 0:
                    w += 1    # promote previous narrow char to width 2
                continue
            if ch == '\u200d':  # zero-width joiner
                continue
            cat = unicodedata.east_asian_width(ch)
            w += 2 if cat in ('W', 'F') else 1
        return w

    w_name = max(_display_width(r["name"]) for r in rows)

    print()
    hdr = "Proyecto"
    print(f"| {hdr}{' ' * (w_name - len(hdr))} | Tipo | Estado | Prioridad |")
    print(f"|{'-' * (w_name + 2)}|------|--------|-----------|")
    for r in rows:
        pad = w_name - _display_width(r["name"])
        print(f"| {r['name']}{' ' * pad} | {r['tipo_emoji']}   | {r['status_emoji']}     | {r['prio_emoji']}        |")
    print()
    return 0


# ── project status ────────────────────────────────────────────────────────────

def run_project_status(name: str, set_status: Optional[str] = None) -> int:
    """Show or set the status of a project."""
    project_dir = _find_new_project(name)
    if project_dir is None:
        return 1

    project_file = resolve_file(project_dir, "project")
    meta         = _read_project_meta(project_dir)
    status, display, is_auto = _resolve_status(meta, project_dir)

    if set_status is None:
        # Just show
        src = "auto" if is_auto else "declarado"
        print(f"\n{meta['name']}: {display}  ({src})\n")
        return 0

    # Set status
    if set_status == "[auto]":
        _set_estado_in_file(project_file, "[auto]")
        print(f"✓ {meta['name']}: estado → [auto] (inferido por Orbit)")
        return 0

    norm = _STATUS_NORM.get(set_status.lower())
    if norm is None:
        print(f"Error: estado '{set_status}' no válido. Opciones: active/activo, paused/pausado, sleeping/durmiendo, [auto]")
        return 1

    _set_estado_in_file(project_file, norm)
    label = _STATUS_LABEL.get(norm, norm)
    print(f"✓ {meta['name']}: estado → {label} (declarado)")
    return 0


def _set_estado_in_file(project_file: Path, value: str) -> None:
    """Replace the Estado line in project.md (stores with emoji)."""
    if value == "[auto]":
        display = "[auto]"
    else:
        norm  = _STATUS_NORM.get(value.lower(), value.lower())
        emoji = _STATUS_EMOJI.get(norm, "")
        label = _STATUS_LABEL.get(norm, value)
        display = f"{emoji} {label}" if emoji else value
    lines = project_file.read_text().splitlines()
    out   = []
    for line in lines:
        if line.strip().startswith("- Estado:"):
            out.append(f"- Estado: {display}")
        else:
            out.append(line)
    project_file.write_text("\n".join(out) + "\n")


# ── project priority ──────────────────────────────────────────────────────────

def run_project_priority(name: str, new_priority: str) -> int:
    """Change the priority of a project."""
    project_dir = _find_new_project(name)
    if project_dir is None:
        return 1

    prio_key = normalize(new_priority)
    if prio_key not in PRIORITY_MAP:
        print(f"⚠️  Prioridad '{new_priority}' no válida. Opciones: alta, media, baja")
        return 1

    project_file = resolve_file(project_dir, "project")
    prio_emoji = PRIORITY_MAP[prio_key]
    new_value = f"{prio_emoji} {new_priority.capitalize()}"

    lines = project_file.read_text().splitlines()
    out = []
    for line in lines:
        if line.strip().startswith("- Prioridad:"):
            out.append(f"- Prioridad: {new_value}")
        else:
            out.append(line)
    project_file.write_text("\n".join(out) + "\n")
    print(f"✓ [{project_dir.name}] Prioridad → {new_value}")
    return 0


# ── project edit ──────────────────────────────────────────────────────────────

def run_project_edit(name: str, editor: str = "") -> int:
    """Open project.md in editor."""
    project_dir = _find_new_project(name)
    if project_dir is None:
        return 1
    open_file(resolve_file(project_dir, "project"), editor)
    return 0


# ── finder ────────────────────────────────────────────────────────────────────

def _find_new_project(name: str) -> Optional[Path]:
    """Find a new-format project directory by partial name match.
    Exact match (case-insensitive) takes priority over partial matches."""
    name_low = name.lower()
    candidates = [
        d for d in PROJECTS_DIR.iterdir()
        if d.is_dir() and _is_new_project(d)
    ]
    # Prefer exact match
    exact = [d for d in candidates if d.name.lower() == name_low]
    if exact:
        return exact[0]
    # Fall back to partial match
    matches = [d for d in candidates if name_low in d.name.lower()]
    if not matches:
        print(f"Error: proyecto '{name}' no encontrado.")
        return None
    if len(matches) > 1:
        names = ", ".join(d.name for d in matches)
        print(f"Error: '{name}' es ambiguo: {names}")
        return None
    return matches[0]


# ── project drop ──────────────────────────────────────────────────────────────

def run_project_drop(name: str, force: bool = False) -> int:
    """Drop a project directory after confirmation (or --force)."""
    project_dir = _find_new_project(name)
    if project_dir is None:
        return 1

    print(f"\nProyecto a eliminar: {project_dir}")
    print("  Esto borrará todos los ficheros del proyecto (logbook, agenda, notas, etc.).")

    if not force:
        if not sys.stdin.isatty():
            print("Error: usa --force para confirmar el borrado en modo no interactivo.")
            return 1
        try:
            ans = input("¿Seguro que quieres eliminar este proyecto? [s/N]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            return 1
        if ans not in ("s", "si", "sí", "y", "yes"):
            print("Cancelado.")
            return 0

    shutil.rmtree(project_dir)
    print(f"✓ Proyecto eliminado: {project_dir.name}")
    return 0



"""highlights.py — hl commands for new-format projects.

highlights.md stores curated references, results, decisions, ideas and
evaluations for a project, organized in optional sections.

  hl add  <project> "<text>" --type TYPE [--link URL]
  hl drop [<project>] ["<text>"]
  hl edit [<project>] ["<text>"] [--text "<new>"] [--link URL|none]
  hl list [<project>] [--type TYPE]

Sections (--type values):
  refs       → ## 📎 Referencias
  results    → ## 📊 Resultados
  decisions  → ## 📌 Decisiones
  ideas      → ## 💡 Ideas
  evals      → ## 🔍 Evaluaciones

Format of an item line:
  - [Title](url) — optional note
  - Plain text entry — optional note
"""
import re
import sys
from pathlib import Path
from typing import Optional

from core.project import _find_new_project, _is_new_project
from core.log import add_orbit_entry, resolve_file
from core.config import iter_project_dirs
from core.open import open_file

# ── Section mapping ────────────────────────────────────────────────────────────

SECTION_MAP = {
    "refs":      "## 📎 Referencias",
    "results":   "## 📊 Resultados",
    "decisions": "## 📌 Decisiones",
    "ideas":     "## 💡 Ideas",
    "evals":     "## 🔍 Evaluaciones",
    "plans":     "## 🗓️ Planes",
}

# Reverse: heading text → type key
_HEADING_TO_KEY = {v: k for k, v in SECTION_MAP.items()}

VALID_TYPES = list(SECTION_MAP)


# ── Item helpers ───────────────────────────────────────────────────────────────

def _format_item(text: str, link: Optional[str] = None) -> str:
    """Format a single highlight item as a markdown list line."""
    if link:
        return f"- [{text}]({link})"
    return f"- {text}"


def _item_display(item: dict) -> str:
    """Human-readable label for interactive selection."""
    if item.get("link"):
        return f"[{item['text']}]({item['link']})"
    return item["text"]


def _parse_item_line(line: str) -> Optional[dict]:
    """Parse a `- ...` line into {text, link, raw}. Returns None if not an item."""
    if not line.startswith("- "):
        return None
    rest = line[2:].strip()
    # Try [text](url) pattern
    m = re.match(r"^\[([^\]]+)\]\(([^)]+)\)(.*)?$", rest)
    if m:
        return {"text": m.group(1), "link": m.group(2),
                "note": m.group(3).strip().lstrip("— ").strip(), "raw": line}
    return {"text": rest, "link": None, "note": None, "raw": line}


# ── File I/O ───────────────────────────────────────────────────────────────────

def _read_highlights(path: Path) -> dict:
    """Parse highlights.md → {header: [str], sections: {key: [item_dict]}}."""
    result = {"header": [], "sections": {k: [] for k in SECTION_MAP}}

    if not path.exists():
        return result

    lines   = path.read_text().splitlines()
    current = None   # current section key

    for line in lines:
        if current is None:
            # Check for a known section heading
            matched = _HEADING_TO_KEY.get(line.strip())
            if matched:
                current = matched
            else:
                result["header"].append(line)
        else:
            matched = _HEADING_TO_KEY.get(line.strip())
            if matched:
                current = matched
            elif line.startswith("## "):
                current = None   # unknown section — stop tracking
                result["header"].append(line)
            elif not line.strip():
                continue   # skip blank lines inside sections
            else:
                item = _parse_item_line(line)
                if item:
                    result["sections"][current].append(item)

    return result


def _write_highlights(path: Path, data: dict) -> None:
    """Serialize data back to highlights.md."""
    out = list(data["header"])
    # Strip trailing blanks from header
    while out and not out[-1].strip():
        out.pop()
    out.append("")

    for key, heading in SECTION_MAP.items():
        items = data["sections"].get(key, [])
        if not items:
            continue
        out.append(heading)
        for item in items:
            out.append(_format_item(item["text"], item.get("link")))
        out.append("")

    from core.undo import save_snapshot
    save_snapshot(path)
    path.write_text("\n".join(out) + "\n")


# ── Interactive selection ──────────────────────────────────────────────────────

def _select_highlight(data: dict, hl_type: Optional[str],
                      text: Optional[str]) -> Optional[tuple]:
    """Return (section_key, item_index) for a selected item.

    If *hl_type* given: restrict to that section.
    If *text* given: find by partial match.
    Else: show numbered list across all (or typed) sections.
    Returns None if nothing selected.
    """
    # Build flat list of (section_key, idx, item)
    if hl_type:
        if hl_type not in SECTION_MAP:
            print(f"Error: tipo '{hl_type}' no válido. Opciones: {', '.join(VALID_TYPES)}")
            return None
        candidates = [(hl_type, i, item)
                      for i, item in enumerate(data["sections"][hl_type])]
    else:
        candidates = [(k, i, item)
                      for k in SECTION_MAP
                      for i, item in enumerate(data["sections"][k])]

    if not candidates:
        print("No hay highlights disponibles.")
        return None

    if text:
        matches = [(k, i, it) for k, i, it in candidates
                   if text.lower() in it["text"].lower()
                   or (it.get("link") and text.lower() in it["link"].lower())]
        if not matches:
            print(f"Error: no se encontró '{text}'")
            return None
        if len(matches) > 1:
            descs = ", ".join(f'"{it["text"]}"' for _, _, it in matches)
            print(f"Ambiguo: {len(matches)} coincidencias: {descs}")
            return None
        k, i, _ = matches[0]
        return k, i

    # Interactive numbered list
    print("\nHighlights:")
    for n, (k, _, item) in enumerate(candidates, 1):
        section_label = SECTION_MAP[k].split()[-1]   # last word of heading
        print(f"  {n}. [{section_label}] {_item_display(item)}")
    print()

    if not sys.stdin.isatty():
        return None

    try:
        raw = input("Selecciona (número o texto parcial): ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return None

    if not raw:
        return None

    if raw.isdigit():
        idx = int(raw) - 1
        if 0 <= idx < len(candidates):
            k, i, _ = candidates[idx]
            return k, i
        print(f"Fuera de rango (1–{len(candidates)})")
        return None

    matches = [(k, i, it) for k, i, it in candidates
               if raw.lower() in it["text"].lower()]
    if not matches:
        print(f"Sin coincidencias para '{raw}'")
        return None
    if len(matches) > 1:
        print(f"Ambiguo: {len(matches)} coincidencias")
        return None
    k, i, _ = matches[0]
    return k, i


# ── Commands ───────────────────────────────────────────────────────────────────

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


def run_hl_add(project: str, text: str, hl_type: str,
               link: Optional[str] = None,
               date_str: Optional[str] = None,
               deliver: bool = False) -> int:
    if hl_type not in SECTION_MAP:
        print(f"Error: tipo '{hl_type}' no válido. Opciones: {', '.join(VALID_TYPES)}")
        return 1

    project_dir = _find_new_project(project)
    if project_dir is None:
        return 1

    # Prefix date to text if requested
    if date_str:
        from core.dateparse import parse_date
        resolved = parse_date(date_str)
        if not resolved:
            print(f"Error: fecha no reconocida: '{date_str}'")
            return 1
        text = f"{text} ({resolved})"

    # Handle file/URL/deliver logic for link argument
    if link:
        if _is_url(link) or link.startswith("./"):
            pass  # keep as-is (URL or relative link)
        else:
            from core.deliver import deliver_file, IMAGE_EXTS, relative_cloud_link
            src = Path(link).expanduser()
            if not src.is_absolute():
                from core.log import find_project
                pd = find_project(project)
                if pd:
                    candidate = pd / link
                    src = candidate if candidate.exists() else Path.cwd() / link

            if src.exists():
                should_deliver = deliver or _ask_deliver()
                if should_deliver:
                    dest = deliver_file(project_dir, src, subdir="hls")
                    if not dest:
                        return 1
                    link = relative_cloud_link("hls", dest.name)
                else:
                    link = str(src)
            elif deliver:
                print(f"Error: no existe {src}")
                return 1
            # else: keep link as-is (relative path or manual reference)

    hl_path = resolve_file(project_dir, "highlights")
    data    = _read_highlights(hl_path)
    data["sections"][hl_type].append({"text": text, "link": link, "note": None})
    _write_highlights(hl_path, data)

    display = f"[{text}]({link})" if link else text
    print(f"✓ [{project_dir.name}] Highlight ({hl_type}): {display}")
    return 0


def run_hl_drop(project: Optional[str], text: Optional[str],
                hl_type: Optional[str] = None, force: bool = False) -> int:
    import sys
    project_dir = _find_new_project(project) if project else None
    if project and project_dir is None:
        return 1
    if project_dir is None:
        print("Error: especifica un proyecto")
        return 1

    hl_path = resolve_file(project_dir, "highlights")
    data    = _read_highlights(hl_path)

    sel = _select_highlight(data, hl_type, text)
    if sel is None:
        return 1
    k, i = sel

    display = _item_display(data["sections"][k][i])

    if not force:
        if not sys.stdin.isatty():
            print("Error: usa --force para confirmar el borrado en modo no interactivo.")
            return 1
        try:
            ans = input(f"¿Seguro que quieres eliminar \"{display}\"? [s/N]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            return 1
        if ans not in ("s", "si", "sí", "y", "yes"):
            print("Cancelado.")
            return 0

    data["sections"][k].pop(i)
    _write_highlights(hl_path, data)

    add_orbit_entry(project_dir, f"[borrada] Highlight: {display}", "apunte")
    print(f"✓ [{project_dir.name}] Highlight eliminado: {display}")
    return 0


def run_hl_edit(project: Optional[str], text: Optional[str],
                new_text: Optional[str] = None, new_link: Optional[str] = None,
                hl_type: Optional[str] = None, editor: str = "") -> int:
    """Edit a highlight: update text/link inline, or open file in editor."""
    project_dir = _find_new_project(project) if project else None
    if project and project_dir is None:
        return 1
    if project_dir is None:
        print("Error: especifica un proyecto")
        return 1

    hl_path = resolve_file(project_dir, "highlights")

    # If neither new_text nor new_link given, open in editor
    if not new_text and not new_link:
        open_file(hl_path, editor)
        return 0

    data = _read_highlights(hl_path)
    sel  = _select_highlight(data, hl_type, text)
    if sel is None:
        return 1
    k, i = sel

    item = data["sections"][k][i]
    if new_text:
        item["text"] = new_text
    if new_link:
        item["link"] = None if new_link == "none" else new_link

    _write_highlights(hl_path, data)
    print(f"✓ [{project_dir.name}] Highlight actualizado: {_item_display(item)}")
    return 0


def run_hl_list(project: Optional[str] = None,
                hl_type: Optional[str] = None) -> int:
    if hl_type and hl_type not in SECTION_MAP:
        print(f"Error: tipo '{hl_type}' no válido. Opciones: {', '.join(VALID_TYPES)}")
        return 1

    if project:
        project_dir = _find_new_project(project)
        if project_dir is None:
            return 1
        dirs = [project_dir]
    else:
        dirs = [d for d in iter_project_dirs() if _is_new_project(d)]

    total = 0
    for project_dir in dirs:
        data = _read_highlights(resolve_file(project_dir, "highlights"))
        keys = [hl_type] if hl_type else list(SECTION_MAP)

        proj_lines = []
        for k in keys:
            items = data["sections"].get(k, [])
            if not items:
                continue
            proj_lines.append(f"  {SECTION_MAP[k]}")
            for item in items:
                proj_lines.append(f"    {_item_display(item)}")
            total += len(items)

        if proj_lines:
            print(f"\n[{project_dir.name}]")
            for line in proj_lines:
                print(line)

    if not total:
        sf = f" ({hl_type})" if hl_type else ""
        print(f"No hay highlights{sf}.")
    else:
        print()
    return 0

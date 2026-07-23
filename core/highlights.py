"""highlights.py — hl commands (unified orbit-item format).

highlights.md stores curated references, results, decisions, ideas,
evaluations, plans and contacts for a project as a **flat list of
orbit-items** (same grammar as agenda.md, ADR-045). Sections disappeared
from the truth: the type lives in the item itself (emoji + primary tag).

  hl add  <project> "<text>" --type TYPE [--link URL]
  hl drop [<project>] ["<text>"]
  hl edit [<project>] ["<text>"] [--text "<new>"] [--link URL|none]
  hl list [<project>] [--type TYPE]

Item grammar (header at column 0, optional note indented 2 spaces):

  - 📎 [Title](url) #referencia
  - 💡 Plain text idea #idea
    optional note / body line

Types (--type values) — emoji encodes the type, `#primary` mirrors it
(redundant today; leaves room for extra free tags after it):

  refs       📎  #referencia
  results    📊  #resultado
  decisions  📌  #decisión
  ideas      💡  #idea
  evals      🔍  #evaluación
  plans      🗓️  #plan
  contacts   👥  #contacto

Legacy `## <emoji> <Word>` section files are migrated lazily: they are
read tolerantly and rewritten flat on the first mutation.
"""
import re
import sys
from pathlib import Path
from typing import Optional

from core.project import _find_new_project, _is_new_project
from core.log import add_orbit_entry, resolve_file
from core.config import iter_project_dirs
from core.open import open_file

# ── Type table ─────────────────────────────────────────────────────────────────
#
# Emoji is the discriminator on parse (like agenda's newfmt), so each type
# needs a unique emoji. The primary tag mirrors the type — redundant with the
# emoji today, but it is the seam for adding free thematic tags after it.

TYPE_EMOJI = {
    "refs":      "📎",
    "results":   "📊",
    "decisions": "📌",
    "ideas":     "💡",
    "evals":     "🔍",
    "plans":     "🗓️",
    "contacts":  "👥",
}
PRIMARY_TAG = {
    "refs":      "#referencia",
    "results":   "#resultado",
    "decisions": "#decisión",
    "ideas":     "#idea",
    "evals":     "#evaluación",
    "plans":     "#plan",
    "contacts":  "#contacto",
}

VALID_TYPES = list(TYPE_EMOJI)

# emoji → type key (for the parser).
_EMOJI_TO_TYPE = {v: k for k, v in TYPE_EMOJI.items()}

# Mapping from highlight type → logbook tipo (for the auto-log entry on hl add)
_HL_TYPE_TO_LOG_TIPO = {
    "refs":      "referencia",
    "results":   "resultado",
    "decisions": "decision",
    "ideas":     "idea",
    "evals":     "evaluacion",
    "plans":     "plan",
    "contacts":  "apunte",
}


# ── Serializer (model → new format) ────────────────────────────────────────────

def _format_hl_item(item: dict) -> str:
    """Render one highlight as ``- <emoji> <text/link> #primary [#free…]``.

    An optional ``note`` is emitted as body lines indented two spaces.
    """
    typ   = item["type"]
    emoji = TYPE_EMOJI[typ]
    body  = f"[{item['text']}]({item['link']})" if item.get("link") else item["text"]

    primary = PRIMARY_TAG[typ]
    free    = [t for t in item.get("tags", []) if t != primary]
    tags    = " ".join([primary] + free)

    lines = [f"- {emoji} {body} {tags}".rstrip()]
    note  = item.get("note")
    if note:
        lines.extend(f"  {nl}" for nl in note.split("\n"))
    return "\n".join(lines)


def serialize_highlights(data: dict) -> str:
    """Serialize a highlights model → flat orbit-item text (header + items)."""
    out = list(data.get("header", []))
    while out and not out[-1].strip():
        out.pop()
    if out:
        out.append("")
    for item in data.get("items", []):
        out.append(_format_hl_item(item))
        out.append("")
    return "\n".join(out).rstrip() + "\n"


# ── Parser (new format → model) ────────────────────────────────────────────────

def _parse_hl_header(line: str) -> Optional[dict]:
    """Parse a ``- <emoji> text/link #tags`` header → item dict, or None."""
    rest = line[2:].strip()   # caller guarantees the "- " prefix
    typ  = None
    for emoji, t in _EMOJI_TO_TYPE.items():
        if rest == emoji or rest.startswith(emoji + " "):
            typ  = t
            rest = rest[len(emoji):].strip()
            break
    if typ is None:
        return None   # not a recognized highlight item

    # Trailing #tokens are tags; the rest is the text (maybe a markdown link).
    words = rest.split()
    tags  = []
    while words and words[-1].startswith("#"):
        tags.insert(0, words.pop())
    text_part = " ".join(words)

    m = re.match(r"^\[([^\]]+)\]\(([^)]+)\)$", text_part)
    if m:
        text, link = m.group(1), m.group(2)
    else:
        text, link = text_part, None

    free = [t for t in tags if t != PRIMARY_TAG[typ]]
    return {"type": typ, "text": text, "link": link, "note": None, "tags": free}


def parse_highlights_new(text: str) -> dict:
    """Parse a flat orbit-item highlights file → {header, items}."""
    data  = {"header": [], "items": []}
    lines = text.splitlines()
    i     = 0

    # Header = everything before the first item bullet.
    while i < len(lines) and not lines[i].startswith("- "):
        data["header"].append(lines[i])
        i += 1

    while i < len(lines):
        line = lines[i]
        if not line.startswith("- "):
            i += 1
            continue
        item = _parse_hl_header(line)
        i += 1
        body = []
        while i < len(lines) and (lines[i].startswith("  ") or lines[i].startswith("\t")):
            body.append(lines[i].strip())
            i += 1
        if item is None:
            continue
        if body:
            item["note"] = "\n".join(body)
        data["items"].append(item)

    return data


# ── Legacy reader (old `## Section` format → model, for lazy migration) ─────────

# Match by the Spanish noun so emoji drift (📚/📎, 🔬/📊, 🏛️/📌, 📊/🔍…) can't
# break migration of real files written before the unified format.
_LEGACY_WORD = {
    "Referencias":  "refs",
    "Resultados":   "results",
    "Decisiones":   "decisions",
    "Ideas":        "ideas",
    "Evaluaciones": "evals",
    "Planes":       "plans",
    "Contactos":    "contacts",
}


def _legacy_heading_type(stripped: str) -> Optional[str]:
    """Return the type key for a legacy ``## <emoji> <Word>`` heading, else None."""
    if not stripped.startswith("## "):
        return None
    for w in stripped[3:].split():
        if w in _LEGACY_WORD:
            return _LEGACY_WORD[w]
    return None


def _is_legacy_format(text: str) -> bool:
    """A file is legacy if it carries any recognized ``## Section`` heading."""
    return any(_legacy_heading_type(l.strip()) for l in text.splitlines())


def _parse_legacy_item(stripped: str, typ: str) -> dict:
    """Parse an old-format bullet (``- [text](url) — note`` / ``- text``)."""
    rest = stripped[2:].strip()
    m = re.match(r"^\[([^\]]+)\]\(([^)]+)\)(.*)$", rest)
    if m:
        text, link = m.group(1), m.group(2)
        note = m.group(3).strip().lstrip("—").strip() or None
    else:
        text, link, note = rest, None, None
    return {"type": typ, "text": text, "link": link, "note": note, "tags": []}


def _read_highlights_legacy(text: str) -> dict:
    """Read an old sectioned highlights file into the flat model."""
    data    = {"header": [], "items": []}
    current = None   # type key, or None while still in the header region

    for line in text.splitlines():
        s     = line.strip()
        htype = _legacy_heading_type(s)
        if htype:
            current = htype
            continue
        if current is None:
            data["header"].append(line)
            continue
        if s.startswith("#"):        # unknown heading closes the section run
            current = None
            data["header"].append(line)
            continue
        if s.startswith("- "):
            data["items"].append(_parse_legacy_item(s, current))
        # blank lines / comments inside a section are dropped

    return data


# ── File I/O ───────────────────────────────────────────────────────────────────

def _read_highlights(path: Path) -> dict:
    """Parse highlights.md → {header: [str], items: [item_dict]}.

    Detects the on-disk format: legacy ``## Section`` files are read
    tolerantly (migrated on the next write); new files are parsed flat.
    """
    if not path.exists():
        return {"header": [], "items": []}
    text = path.read_text()
    if _is_legacy_format(text):
        return _read_highlights_legacy(text)
    return parse_highlights_new(text)


def _write_highlights(path: Path, data: dict) -> None:
    """Serialize the model back to highlights.md (always the new format)."""
    from core.undo import save_snapshot
    save_snapshot(path)
    path.write_text(serialize_highlights(data))


# ── Item helpers ───────────────────────────────────────────────────────────────

def _item_display(item: dict) -> str:
    """Human-readable label for interactive selection / listings."""
    if item.get("link"):
        return f"[{item['text']}]({item['link']})"
    return item["text"]


def _is_url(ref: str) -> bool:
    return ref.startswith("http://") or ref.startswith("https://")


# ── Interactive selection ──────────────────────────────────────────────────────

def _select_highlight(data: dict, hl_type: Optional[str],
                      text: Optional[str]) -> Optional[int]:
    """Return the index into ``data['items']`` for a selected item.

    If *hl_type* given: restrict to that type. If *text* given: find by
    partial match. Else: show a numbered list. Returns None if nothing picked.
    """
    if hl_type and hl_type not in TYPE_EMOJI:
        print(f"Error: tipo '{hl_type}' no válido. Opciones: {', '.join(VALID_TYPES)}")
        return None

    items = data["items"]
    candidates = [(i, it) for i, it in enumerate(items)
                  if hl_type is None or it["type"] == hl_type]

    if not candidates:
        print("No hay highlights disponibles.")
        return None

    if text:
        matches = [(i, it) for i, it in candidates
                   if text.lower() in it["text"].lower()
                   or (it.get("link") and text.lower() in it["link"].lower())]
        if not matches:
            print(f"Error: no se encontró '{text}'")
            return None
        if len(matches) > 1:
            descs = ", ".join(f'"{it["text"]}"' for _, it in matches)
            print(f"Ambiguo: {len(matches)} coincidencias: {descs}")
            return None
        return matches[0][0]

    # Interactive numbered list
    print("\nHighlights:")
    for n, (_, item) in enumerate(candidates, 1):
        label = TYPE_EMOJI[item["type"]]
        print(f"  {n}. {label} {_item_display(item)}")
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
            return candidates[idx][0]
        print(f"Fuera de rango (1–{len(candidates)})")
        return None

    matches = [(i, it) for i, it in candidates
               if raw.lower() in it["text"].lower()]
    if not matches:
        print(f"Sin coincidencias para '{raw}'")
        return None
    if len(matches) > 1:
        print(f"Ambiguo: {len(matches)} coincidencias")
        return None
    return matches[0][0]


# ── Commands ───────────────────────────────────────────────────────────────────

def run_hl_add(project: str, text: str, hl_type: str,
               link: Optional[str] = None,
               date_str: Optional[str] = None,
               deliver: bool = False,
               as_link: bool = False,
               no_date: bool = False) -> int:
    if hl_type not in TYPE_EMOJI:
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

    # Handle file/URL logic for link argument
    if link:
        if _is_url(link) or link.startswith("./"):
            pass  # keep as-is (URL or relative link)
        else:
            from core.link_import import apply_mode, resolve_mode, echo_mode
            src = Path(link).expanduser()
            if not src.is_absolute():
                from core.log import find_project
                pd = find_project(project)
                if pd:
                    candidate = pd / link
                    src = candidate if candidate.exists() else Path.cwd() / link

            if src.exists():
                try:
                    mode = resolve_mode(as_link=as_link, as_import=deliver)
                except ValueError as exc:
                    print(f"⚠️  {exc}")
                    return 1
                # Date-prefix only for non-md imports (collision prevention in
                # cloud/hls/). Md files keep their source name in notes/.
                # --no-date opts out (user accepts collision risk).
                _date_prefix = (mode == "import"
                                and src.suffix.lower() != ".md"
                                and not no_date)
                try:
                    link, _dest = apply_mode(project_dir, src, mode,
                                              non_md_subdir="hls",
                                              date_prefix=_date_prefix)
                except (FileExistsError, RuntimeError, ValueError) as exc:
                    print(f"⚠️  {exc}")
                    return 1
                echo_mode(mode, link)
            elif deliver or as_link:
                print(f"Error: no existe {src}")
                return 1
            # else: keep link as-is (relative path or manual reference)

    hl_path = resolve_file(project_dir, "highlights")
    data    = _read_highlights(hl_path)
    item    = {"type": hl_type, "text": text, "link": link, "note": None, "tags": []}
    data["items"].append(item)
    _write_highlights(hl_path, data)

    add_orbit_entry(project_dir, f"Highlight: {text}",
                    tipo=_HL_TYPE_TO_LOG_TIPO.get(hl_type, "apunte"),
                    path=link, extra_tags=["headline"])

    print(f"✓ [{project_dir.name}] {_format_hl_item(item).splitlines()[0]}")
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

    idx = _select_highlight(data, hl_type, text)
    if idx is None:
        return 1

    display = _item_display(data["items"][idx])

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

    data["items"].pop(idx)
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
    idx  = _select_highlight(data, hl_type, text)
    if idx is None:
        return 1

    item = data["items"][idx]
    if new_text:
        item["text"] = new_text
    if new_link:
        item["link"] = None if new_link == "none" else new_link

    _write_highlights(hl_path, data)
    print(f"✓ [{project_dir.name}] Highlight actualizado: {_item_display(item)}")
    return 0


def run_hl_list(project: Optional[str] = None,
                hl_type: Optional[str] = None) -> int:
    if hl_type and hl_type not in TYPE_EMOJI:
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
        data  = _read_highlights(resolve_file(project_dir, "highlights"))
        items = [it for it in data["items"]
                 if hl_type is None or it["type"] == hl_type]
        if not items:
            continue

        # Tracked highlights are marked with 🔄 next to their text.
        from core.tracked import load_registry
        tracked_names = set(load_registry(project_dir))  # {filename}

        proj_lines = []
        for item in items:
            marker = ""
            link = item.get("link") or ""
            # link like "./notes/DECISIONS.md" → match basename against registry
            if link.startswith("./notes/") and link.removeprefix("./notes/") in tracked_names:
                marker = "🔄 "
            proj_lines.append(f"  {TYPE_EMOJI[item['type']]} {marker}{_item_display(item)}")
            total += 1

        print(f"\n[{project_dir.name}]")
        for line in proj_lines:
            print(line)

    if not total:
        sf = f" ({hl_type})" if hl_type else ""
        print(f"No hay highlights{sf}.")
    else:
        print()
    return 0

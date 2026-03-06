"""orbit import — convert an Evernote .enex note into Orbit project files."""

import re
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from pathlib import Path
from typing import List, Tuple, Optional

from core.log import PROJECTS_DIR, find_proyecto_file, find_logbook_file

LOGBOOK_KEYS   = {"logbook", "logbo"}
REFERENCE_KEYS = {"references", "reference", "referencias", "referencia"}
TASKS_KEYS     = {"tareas", "tarea", "tasks", "task"}


# ── HTML → Markdown ────────────────────────────────────────────────────────────

class _MD(HTMLParser):
    """Simple ENML-to-Markdown converter."""

    def __init__(self):
        super().__init__()
        self._out:        List[str] = []
        self._skip:       int       = 0
        self._in_link:    bool      = False
        self._link_href:  str       = ""
        self._link_buf:   List[str] = []
        self._list_depth: int       = 0

    def handle_starttag(self, tag, attrs):
        if self._skip or tag in ("en-media", "en-todo"):
            self._skip += 1
            return
        a = dict(attrs)
        if tag == "h3":
            self._out.append("\n### ")
        elif tag == "h4":
            self._out.append("\n#### ")
        elif tag in ("ul", "ol"):
            self._list_depth += 1
        elif tag == "li":
            self._out.append("\n" + "  " * (self._list_depth - 1) + "- ")
        elif tag == "a":
            self._in_link = True
            self._link_href = a.get("href", "")
            self._link_buf = []
        elif tag == "b":
            self._out.append("**")
        elif tag == "i":
            self._out.append("*")
        elif tag == "br":
            self._out.append("\n")
        elif tag == "hr":
            self._out.append("\n---\n")

    def handle_endtag(self, tag):
        if self._skip:
            self._skip -= 1
            return
        if tag in ("h3", "h4"):
            self._out.append("\n")
        elif tag in ("ul", "ol"):
            self._list_depth = max(0, self._list_depth - 1)
            if self._list_depth == 0:
                self._out.append("\n")
        elif tag == "a":
            if self._in_link:
                text = "".join(self._link_buf).strip()
                href = self._link_href
                if href and text and not href.startswith(("evernote://", "file:", "mailto:")):
                    self._out.append(f"[{text}]({href})")
                elif text:
                    self._out.append(text)
                self._in_link = False
        elif tag == "b":
            self._out.append("**")
        elif tag == "i":
            self._out.append("*")
        elif tag == "div":
            self._out.append("\n")

    def handle_data(self, data):
        if self._skip:
            return
        if self._in_link:
            self._link_buf.append(data)
        else:
            self._out.append(data)

    def result(self) -> str:
        text = "".join(self._out)
        return re.sub(r"\n{3,}", "\n\n", text).strip()


def _to_md(html: str) -> str:
    p = _MD()
    p.feed(html)
    return p.result()


def _strip_tags(html: str) -> str:
    text = re.sub(r"<[^>]+>", "", html)
    text = text.replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&").replace("&nbsp;", " ")
    return text.strip()


# ── ENEX loading ───────────────────────────────────────────────────────────────

def _load_enex(path: Path) -> Tuple[str, str]:
    """Return (title, enml_content) from an .enex file."""
    tree = ET.parse(path)
    root = tree.getroot()
    note = root.find("note")
    title   = note.find("title").text or ""
    content = note.find("content").text or ""
    return title, content


def _split_sections(enml: str) -> List[Tuple[str, str]]:
    """Split ENML by <h2> tags. Returns list of (original_title, html_content)."""
    pattern = re.compile(
        r'<h2[^>]*>(.*?)</h2>(.*?)(?=<h2|</en-note>)',
        re.DOTALL | re.IGNORECASE,
    )
    return [
        (_strip_tags(m.group(1)).strip(), m.group(2))
        for m in pattern.finditer(enml)
    ]


# ── Logbook parsing ────────────────────────────────────────────────────────────

def _parse_logbook(html: str) -> List[dict]:
    """Extract {date, items} dicts from an Evernote logbook section."""
    entries = []
    pattern = re.compile(
        r'<div[^>]*>\s*(\d{6})\s*</div>(.*?)(?=<div[^>]*>\s*\d{6}\s*</div>|$)',
        re.DOTALL,
    )
    for m in pattern.finditer(html):
        raw = m.group(1)
        iso = f"20{raw[:2]}-{raw[2:4]}-{raw[4:]}"
        items = []
        for li in re.finditer(r"<li[^>]*>(.*?)</li>", m.group(2), re.DOTALL):
            text = re.sub(r"\s+", " ", _strip_tags(li.group(1))).strip()
            if text and text not in ("-", "–"):
                items.append(text)
        if items:
            entries.append({"date": iso, "items": items})
    return entries


def _format_entry(e: dict) -> str:
    d, items = e["date"], e["items"]
    if len(items) == 1:
        return f"{d} {items[0]} #apunte"
    return d + " #apunte\n" + "\n".join(f"  - {i}" for i in items)


# ── References parsing ─────────────────────────────────────────────────────────

def _parse_references(html: str) -> List[str]:
    """Extract unique external markdown links from references section."""
    links, seen = [], set()
    for m in re.finditer(r'<a[^>]*href="([^"]*)"[^>]*>(.*?)</a>', html, re.DOTALL):
        href = m.group(1)
        text = _strip_tags(m.group(2)).strip()
        if not href or href in seen:
            continue
        if href.startswith(("evernote://", "file:", "mailto:")):
            continue
        seen.add(href)
        if text:
            links.append(f"- [{text}]({href})")
    return links


# ── Tasks parsing ─────────────────────────────────────────────────────────────

def _parse_tasks(html: str) -> List[dict]:
    """Extract tasks from Evernote todo list items."""
    tasks = []
    for m in re.finditer(r'<li[^>]*--en-checked:(true|false)[^>]*>(.*?)</li>', html, re.DOTALL):
        done = m.group(1) == "true"
        text = re.sub(r"\s+", " ", _strip_tags(m.group(2))).strip()
        # strip leading dash or status emoji left by Evernote
        text = re.sub(r"^[-–]\s*", "", text).strip()
        text = re.sub(r"^[⏳⬜▶️✅⏸️💤]\s*", "", text).strip()
        if text:
            tasks.append({"done": done, "text": text})
    return tasks


def _inject_tasks(proyecto_path: Path, tasks: List[dict]) -> int:
    """Inject tasks into ## ✅ Tareas section of proyecto.md."""
    md = proyecto_path.read_text()
    new_lines = "\n".join(
        f"- [{'x' if t['done'] else ' '}] {t['text']}" for t in tasks
    )
    # Replace template placeholder lines
    md = re.sub(
        r"(## ✅ Tareas\n)- \[ \] Ejemplo de tarea con fecha \([\d-]+\)\n- \[ \] Ejemplo de tarea sin fecha\n",
        r"\1" + new_lines + "\n",
        md,
    )
    # If placeholder wasn't found, append after header
    if new_lines not in md:
        md = re.sub(r"(## ✅ Tareas\n)", r"\1" + new_lines + "\n", md)
    proyecto_path.write_text(md)
    return len(tasks)


# ── Main ───────────────────────────────────────────────────────────────────────

def run_import(enex_path: str, project: str) -> int:
    path = Path(enex_path)
    if not path.exists():
        print(f"Error: no existe {path}")
        return 1

    from core.log import find_project
    project_dir = find_project(project)
    if not project_dir:
        return 1

    title, enml = _load_enex(path)
    sections = _split_sections(enml)
    if not sections:
        print("Error: no se encontraron secciones <h2> en la nota")
        return 1

    logbook_entries: List[dict] = []
    ref_links:       List[str]  = []
    task_items:      List[dict] = []
    info_parts:      List[str]  = []

    for sec_title, sec_html in sections:
        key = sec_title.lower()
        if any(k in key for k in LOGBOOK_KEYS):
            logbook_entries = _parse_logbook(sec_html)
        elif any(k in key for k in REFERENCE_KEYS):
            ref_links = _parse_references(sec_html)
        elif any(k in key for k in TASKS_KEYS):
            task_items = _parse_tasks(sec_html)
        else:
            md = _to_md(sec_html)
            if md.strip():
                info_parts.append(f"## {sec_title}\n\n{md}")

    # 1 — Logbook entries → 📓name.md
    if logbook_entries:
        logbook_path = find_logbook_file(project_dir)
        if not logbook_path or not logbook_path.exists():
            print(f"Error: no se encontró el logbook en {project_dir.name}")
            return 1
        # de-duplicate: skip dates already present
        existing = set(re.findall(r"^(\d{4}-\d{2}-\d{2})", logbook_path.read_text(), re.MULTILINE))
        new = [e for e in logbook_entries if e["date"] not in existing]
        if new:
            text = "\n\n".join(_format_entry(e) for e in new)
            with open(logbook_path, "a") as f:
                f.write("\n" + text + "\n")
            print(f"✓ {len(new)} entrada(s) añadidas a {logbook_path.name}")
        else:
            print("  Logbook: todas las fechas ya existían, nada añadido")

    # 2 — Tasks → ## ✅ Tareas in {emoji}name.md
    if task_items:
        proyecto_path = find_proyecto_file(project_dir)
        if proyecto_path and proyecto_path.exists():
            n = _inject_tasks(proyecto_path, task_items)
            print(f"✓ {n} tarea(s) añadidas a {proyecto_path.name}")

    # 3 — References → ## 📎 Referencias clave in {emoji}name.md
    if ref_links:
        proyecto_path = find_proyecto_file(project_dir)
        if proyecto_path and proyecto_path.exists():
            md = proyecto_path.read_text()
            new_refs = "\n".join(ref_links)
            # Replace empty placeholder or append after header
            md = re.sub(
                r"(## 📎 Referencias clave\n)-\n",
                r"\1" + new_refs + "\n",
                md,
            )
            if new_refs not in md:   # fallback: just append after header
                md = re.sub(
                    r"(## 📎 Referencias clave\n)",
                    r"\1" + new_refs + "\n",
                    md,
                )
            proyecto_path.write_text(md)
            print(f"✓ {len(ref_links)} referencia(s) añadidas a {proyecto_path.name}")

    # 4 — Everything else → references/informacion.md
    if info_parts:
        ref_dir = project_dir / "references"
        ref_dir.mkdir(exist_ok=True)
        info_path = ref_dir / "informacion-evernote.md"
        info_content = f"# {title}\n\n" + "\n\n".join(info_parts)
        info_path.write_text(info_content)
        # Add link to proyecto.md if not already there
        proyecto_path = find_proyecto_file(project_dir)
        if proyecto_path and proyecto_path.exists():
            md = proyecto_path.read_text()
            link = "- [Información Evernote](./references/informacion-evernote.md)"
            if link not in md:
                md = re.sub(r"(## 📎 Referencias clave\n)", r"\1" + link + "\n", md)
                proyecto_path.write_text(md)
        print(f"✓ Información guardada en references/informacion-evernote.md")

    return 0

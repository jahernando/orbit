"""termlink.py — enlaces clicables en la salida de `ls` a la terminal.

La familia `ls` imprime markdown (`[texto](./cloud/logs/x.pdf)`). En una
terminal que entiende OSC 8 (iTerm2, WezTerm, kitty, Ghostty, VS Code…) eso se
convierte en el **texto clicable** seguido de `↗`: ⌘-clic abre el fichero o la
web. Las rutas relativas se resuelven contra el proyecto de la sección, que se
deduce de las cabeceras que ya imprime cada `ls` (`[⚙️proyecto]`,
`[⚙️proyecto/notes]`, `💶 Ledger — ⚙️proyecto`).

Solo se aplica cuando la salida va a una terminal: con `--open`, `--log`,
`--append`, una tubería o `ORBIT_NO_LINKS=1`, sale el markdown de siempre.
"""

import os
import re
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Dict, Optional
from urllib.parse import unquote

ARROW = "↗"

_MD_LINK_RE = re.compile(r"\[(?P<text>[^\[\]]+)\]\((?P<url>[^()\s]*(?:\([^()\s]*\)[^()\s]*)*)\)")
_SCHEME_RE  = re.compile(r"^[a-z][a-z0-9+.-]*:", re.I)
_HEADER_RE  = re.compile(r"^(?P<lead>\s*)\[(?P<name>[^\]/]+)(?P<sub>/[^\]]*)?\]")
_LEDGER_RE  = re.compile(r"^💶 (?:Ledger|Resumen) — (?P<name>\S+)")
_FILE_RE    = re.compile(r"^(?P<lead>\s+\S{1,2}\s+)(?P<name>\S.*?)\s*$")
_ROW_RE     = re.compile(r"^\|\s(?P<name>\S+?)(?P<pad>\s+)\|")


def osc8(text: str, url: str) -> str:
    """`text ↗` como hiperenlace de terminal (OSC 8)."""
    return f"\033]8;;{url}\033\\{text} {ARROW}\033]8;;\033\\"


def _file_url(path: Path) -> Optional[str]:
    try:
        return path.resolve().as_uri() if path.exists() else None
    except (OSError, ValueError):
        return None


def resolve_url(url: str, base: Optional[Path]) -> Optional[str]:
    """URL clicable para un enlace markdown, o None si no se puede resolver."""
    url = url.strip()
    if not url:
        return None
    if _SCHEME_RE.match(url):
        return url
    target = unquote(url.split("#", 1)[0])
    if target.startswith(("/", "~")):
        return _file_url(Path(target).expanduser())
    if base is None:
        return None
    if target.startswith("./"):
        target = target[2:]
    return _file_url(base / target)


def project_map() -> Dict[str, Path]:
    from core.config import iter_project_dirs
    try:
        return {d.name: d for d in iter_project_dirs()}
    except Exception:                          # un listado nunca falla por esto
        return {}


class Linkifier:
    """Transforma línea a línea, recordando el proyecto de la sección."""

    def __init__(self, mode: str = "", projects: Optional[Dict[str, Path]] = None):
        self.mode = mode
        self.projects = project_map() if projects is None else projects
        self.base: Optional[Path] = None

    def _links(self, line: str) -> str:
        def repl(m):
            url = resolve_url(m.group("url"), self.base)
            return osc8(m.group("text"), url) if url else m.group(0)
        return _MD_LINK_RE.sub(repl, line)

    def line(self, line: str) -> str:
        if "\033]8;" in line:                    # ya enlazada
            return line
        m = _HEADER_RE.match(line)
        if m and m.group("name") in self.projects:
            project = self.projects[m.group("name")]
            sub = (m.group("sub") or "").strip("/")
            self.base = project / sub if sub else project
            index = project / "project.md"
            url = _file_url(self.base if sub else index)
            if url:
                label = f"{m.group('name')}{m.group('sub') or ''}"
                line = (f"{m.group('lead')}[{osc8(label, url)}]"
                        + line[m.end():])
            return line
        m = _LEDGER_RE.match(line)
        if m and m.group("name") in self.projects:
            self.base = self.projects[m.group("name")]
            url = _file_url(self.base / "ledger.md")
            if url:
                line = line.replace(m.group("name"), osc8(m.group("name"), url), 1)
            return line
        if self.mode in ("ls files", "ls notes") and self.base is not None:
            m = _FILE_RE.match(line)
            if m:
                url = _file_url(self.base / m.group("name"))
                if url:
                    return m.group("lead") + osc8(m.group("name"), url)
        if self.mode == "ls projects":
            m = _ROW_RE.match(line)
            if m and m.group("name") in self.projects:
                url = _file_url(self.projects[m.group("name")] / "project.md")
                pad = m.group("pad")
                if url and len(pad) >= 3:        # `↗` y su espacio caben en el relleno
                    cell = osc8(m.group("name"), url) + pad[2:]
                    return f"| {cell}|" + line[m.end():]
        return self._links(line)


class _LinkWriter:
    """Envuelve `sys.stdout`: transforma cada línea completa al escribirla y
    lo pendiente al hacer `flush` (así un `input()` ve su pregunta)."""

    def __init__(self, out, linkifier: Linkifier):
        self._out = out
        self._lk = linkifier
        self._buf = ""

    def write(self, s: str) -> int:
        self._buf += s
        while "\n" in self._buf:
            line, self._buf = self._buf.split("\n", 1)
            self._out.write(self._lk.line(line) + "\n")
        return len(s)

    def flush(self) -> None:
        if self._buf:
            self._out.write(self._lk.line(self._buf))
            self._buf = ""
        self._out.flush()

    def __getattr__(self, name):
        return getattr(self._out, name)


def enabled(stream=None) -> bool:
    stream = stream or sys.stdout
    if os.environ.get("ORBIT_NO_LINKS"):
        return False
    try:
        return stream.isatty()
    except (AttributeError, ValueError):
        return False


@contextmanager
def linkified(mode: str = ""):
    """Dentro del bloque, lo que se imprime a la terminal sale con enlaces."""
    if not enabled():
        yield
        return
    original = sys.stdout
    writer = _LinkWriter(original, Linkifier(mode))
    sys.stdout = writer
    try:
        yield
    finally:
        writer.flush()
        sys.stdout = original

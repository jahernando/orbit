"""manual.py — índice de comandos y páginas de manual, derivados de CHULETA.md.

Dos superficies nuevas sobre documentación que ya existe:

  help                 índice: una línea por comando
  help <verbo>         la sección de CHULETA.md de ese comando + su gramática

Ninguna de las dos tiene texto propio. CHULETA.md es la fuente única —también
es el contexto que usa ``orbit claude``— y un manual por comando sería una
tercera copia condenada a envejecer. Lo que aquí se hace es localizar en ella
la sección de cada verbo del despachador.

El emparejamiento verbo → sección va por tres niveles, del más fiable al menos:

  1. el verbo es la primera palabra del encabezado   `## hl — highlights`
  2. aparece antes del guión largo                   `## view / open — navegar`
  3. aparece en cualquier punto del encabezado       `### Calendar.app — ics (…)`

Un verbo sin encabezado ninguno no es un fallo del índice sino un agujero de
la chuleta; `doctor` lo reporta (chequeo `manual`).
"""
from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

DASH = "—"


@dataclass
class Section:
    title: str
    level: int
    start: int              # índice de la línea del encabezado
    end: int                # primera línea que ya no pertenece (exclusiva)
    verbs: list = field(default_factory=list)

    @property
    def name(self) -> str:
        """Nombre con el que se lista: el primer verbo, o el propio encabezado."""
        return self.verbs[0] if self.verbs else self.head

    @property
    def head(self) -> str:
        return self.title.split(DASH, 1)[0].strip()

    @property
    def desc(self) -> str:
        if DASH in self.title:
            return self.title.split(DASH, 1)[1].strip()
        return ""


# ── Parseo ───────────────────────────────────────────────────────────────────

def parse_sections(text: str) -> list:
    """Encabezados `##` y `###`, saltando los que viven dentro de un bloque
    de código (la chuleta enseña ficheros markdown con sus propios `##`)."""
    lines = text.splitlines()
    heads, fenced = [], False
    for i, line in enumerate(lines):
        if line.lstrip().startswith("```"):
            fenced = not fenced
            continue
        if fenced:
            continue
        m = re.match(r"^(#{2,3})\s+(.*\S)\s*$", line)
        if m:
            heads.append((i, len(m.group(1)), m.group(2)))

    out = []
    for idx, (i, level, title) in enumerate(heads):
        end = heads[idx + 1][0] if idx + 1 < len(heads) else len(lines)
        out.append(Section(title=title, level=level, start=i, end=end))
    return out


def _tokens(chunk: str) -> list:
    """Palabras sueltas de un trozo de encabezado, sin puntuación de adorno."""
    return [t for t in re.split(r"[^\w.\-]+", chunk) if t]


def assign_verbs(sections: list, verbs) -> list:
    """Reparte cada verbo a su sección.

    Entre varias candidatas gana la de nivel más fiable; a igualdad, la de
    encabezado más alto (`##` antes que `###`), y a igualdad, la primera del
    documento. Sin el desempate por nivel, `panel` caería en la subsección
    "Panel de proyecto" del shell en vez de en su propia sección.
    """
    for verb in sorted(set(verbs)):
        best = None
        for sec in sections:
            for tier in (1, 2, 3):
                toks = _tokens(sec.head if tier <= 2 else sec.title)
                if not toks:
                    continue
                hit = (toks[0].lower() == verb if tier == 1
                       else verb in [tk.lower() for tk in toks])
                if hit:
                    key = (tier, sec.level, sec.start)
                    if best is None or key < best[0]:
                        best = (key, sec)
                    break
        if best is not None:
            best[1].verbs.append(verb)

    for sec in sections:
        head_first = (_tokens(sec.head) or [""])[0].lower()
        sec.verbs.sort(key=lambda v: (v != head_first, v))
    return sections


def build_index(text: str, verbs) -> list:
    """Secciones que documentan al menos un verbo, ordenadas por nombre."""
    secs = assign_verbs(parse_sections(text), verbs)
    return sorted([s for s in secs if s.verbs], key=lambda s: s.name)


def orphan_verbs(text: str, verbs) -> list:
    """Verbos del despachador sin encabezado en la chuleta."""
    secs = assign_verbs(parse_sections(text), verbs)
    covered = {v for s in secs for v in s.verbs}
    return sorted(set(verbs) - covered)


def find_section(text: str, verb: str, verbs) -> Optional[Section]:
    for sec in build_index(text, verbs):
        if verb in sec.verbs:
            return sec
    return None


# ── Salida ───────────────────────────────────────────────────────────────────

def render_index(sections: list) -> str:
    width = max((len(s.name) for s in sections), default=8)
    out = ["", "  Comandos de orbit", ""]
    for sec in sections:
        alias = [v for v in sec.verbs[1:]]
        desc = sec.desc or sec.head
        if alias:
            desc = f"{desc}  (= {', '.join(alias)})"
        out.append(f"  {sec.name.ljust(width)}  {desc}")
    out += ["",
            "  help <comando>   la página de ese comando",
            "  <comando> -h     su gramática exacta",
            "  help chuleta     la referencia completa",
            ""]
    return "\n".join(out)


def render_page(text: str, sec: Section, grammar: str = "") -> str:
    body = "\n".join(text.splitlines()[sec.start:sec.end]).rstrip()
    while body.endswith("---"):                 # el separador de la chuleta
        body = body[: -len("---")].rstrip()
    if grammar:
        body += "\n\n---\n\n## Gramática\n\n```\n" + grammar.rstrip() + "\n```\n"
    return body + "\n"


def page(text: str) -> None:
    """Vuelca por el paginador; si no hay, imprime tal cual."""
    try:
        pager = subprocess.Popen(["less", "-R"], stdin=subprocess.PIPE)
        pager.communicate(input=text.encode())
    except Exception:
        print(text)

"""emails.py — `ls email`: los correos registrados en un proyecto.

Solo lectura. La verdad son las entradas ``#email`` del logbook (las escribe
`email`, ver ``core/email.py``); aquí se leen cabecera y cuerpo:

    2026-10-26 ✉️ [<asunto>](message://%3C<id>%3E) #email [O]
      👤 <remitente> · 📅 2026-10-24 10:12
      📝 [nota](./notes/emails/….md)
      🆔 `<id>`

Las entradas antiguas, de una línea (``[Email: asunto](…) ✉️ [original](…)``),
salen con lo que tengan: asunto y enlaces, sin remitente.
"""

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

_HEAD_RE = re.compile(r"^(?P<date>\d{4}-\d{2}-\d{2})\s+(?P<rest>.*?)\s*#email(?:\s+\[O\])?\s*$")
_LINK_RE = re.compile(r"\[(?P<text>[^\[\]]*)\]\((?P<url>[^()\s]+)\)")
# Título de la cabecera: admite corchetes dentro (``[Email: [IGFAE-all] …]``,
# entradas antiguas); acaba en el primer ``](``.
_TITLE_RE = re.compile(r"^\[(?P<text>.+?)\]\((?P<url>[^()\s]+)\)")
_META_RE = re.compile(r"^👤\s*(?P<who>.*?)\s*(?:·\s*📅\s*(?P<when>.+))?$")
_WHEN_RE = re.compile(r"^📅\s*(?P<when>.+)$")


@dataclass
class EmailRow:
    logged: str                     # fecha de la entrada (cuándo se registró)
    subject: str
    sender: str = ""
    sent: str = ""                  # fecha del correo («YYYY-MM-DD HH:MM»)
    mail: Optional[str] = None      # message://…
    note: Optional[str] = None      # ./notes/emails/….md
    msg_id: str = ""

    @property
    def date(self) -> str:
        return (self.sent or self.logged)[:10]


def _classify(row: EmailRow, url: str) -> None:
    if url.startswith("message:"):
        row.mail = row.mail or url
    elif url.endswith(".md"):
        row.note = row.note or url


def parse_emails(text: str) -> list:
    """Entradas ``#email`` de un logbook → ``[EmailRow]`` (orden del fichero)."""
    rows, cur = [], None
    for line in text.splitlines():
        m = _HEAD_RE.match(line)
        if m:
            rest = m.group("rest")
            rest = re.sub(r"^✉\ufe0f?\s*", "", rest)
            t = _TITLE_RE.match(rest)
            subject = t.group("text") if t else rest
            subject = re.sub(r"^Email:\s*", "", subject).strip()
            cur = EmailRow(logged=m.group("date"), subject=subject)
            if t:
                _classify(cur, t.group("url"))
                for lk in _LINK_RE.finditer(rest[t.end():]):
                    _classify(cur, lk.group("url"))
            rows.append(cur)
            continue
        if cur is None:
            continue
        if not line.startswith("  ") or not line.strip():
            cur = None                   # fin del cuerpo
            continue
        body = line.strip()
        mm = _META_RE.match(body)
        if mm:
            cur.sender = mm.group("who") or ""
            cur.sent = (mm.group("when") or "").strip()
            continue
        mw = _WHEN_RE.match(body)
        if mw:
            cur.sent = mw.group("when").strip()
            continue
        if body.startswith("🆔"):
            cur.msg_id = body[len("🆔"):].strip().strip("`")
            continue
        for lk in _LINK_RE.finditer(body):
            _classify(cur, lk.group("url"))
    return rows


def _matches(row: EmailRow, text: str) -> bool:
    t = text.lower()
    return t in row.subject.lower() or t in row.sender.lower()


def _short_sender(sender: str, width: int = 22) -> str:
    """``Fulano de Tal <f@usc.es>`` → ``Fulano de Tal``; recorta a *width*."""
    name = re.sub(r"\s*<[^>]*>\s*$", "", sender).strip().strip('"') or sender
    return name if len(name) <= width else name[:width - 1] + "…"


def format_row(row: EmailRow, with_sender: bool = True) -> str:
    """Una línea; *with_sender* False omite la columna (bloques en los que
    ninguna entrada la tiene: las antiguas)."""
    text = row.subject.replace("[", "(").replace("]", ")")
    subject = f"[{text}]({row.mail})" if row.mail else text
    marks = f"  [📝]({row.note})" if row.note else ""
    who = f"{_short_sender(row.sender):<22}  " if with_sender else ""
    return f"  {row.date}  {who}{subject}{marks}"


def project_emails(project_dir: Path, text: Optional[str] = None) -> list:
    from core.log import find_logbook_file
    lb = find_logbook_file(project_dir)
    if not lb or not lb.exists():
        return []
    rows = parse_emails(lb.read_text())
    if text:
        rows = [r for r in rows if _matches(r, text)]
    return sorted(rows, key=lambda r: (r.sent or r.logged), reverse=True)


def run_ls_email(project: Optional[str] = None, text: Optional[str] = None,
                 projects: Optional[list] = None) -> int:
    """`ls email [proyecto|@familia] [texto]` — correos registrados, el más
    reciente arriba. Sin proyecto recorre el workspace; con *projects* (una
    familia ya expandida), esos. Salta los proyectos sin correos."""
    from core.ls import collect_project_dirs

    if projects is not None:
        dirs = [d for name in projects for d in collect_project_dirs(name)]
        project = None
    else:
        dirs = collect_project_dirs(project)
        if project and not dirs:
            return 1
    shown = 0
    for project_dir in dirs:
        rows = project_emails(project_dir, text)
        if not rows:
            continue
        print(f"\n[{project_dir.name}]")
        with_sender = any(r.sender for r in rows)
        for row in rows:
            print(format_row(row, with_sender))
        shown += len(rows)
    if not shown:
        where = f" en {dirs[0].name}" if project else ""
        print(f"No hay correos registrados{where}"
              + (f" con «{text}»." if text else "."))
    return 0

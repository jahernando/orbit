"""arxiv.py — feed diario de arXiv por proyecto (fetch → bandeja → triaje).

Tres ficheros en juego:

  notes/arxiv-temas.md   config escrita a mano. **Orbit sólo lee.**
  notes/arxiv.md         bandeja de entrada. Orbit inserta por arriba.
  highlights.md          destino de lo que el usuario marca `#relevante`.

El barrido corre en la cadena `shell_start` (action ``arxiv_fetch``): días
laborables, una vez al día, y sólo en los proyectos que tengan fichero de
temas. La marca de agua vive en ``ORBIT_HOME/.arxiv-state.json`` y sólo avanza
si la descarga fue bien, de modo que un arXiv caído se reintenta al día
siguiente sin perder artículos.

Filtro en capas: categorías de arXiv → puntuación por términos → autores
vigilados → exclusiones. El hueco para una pasada de LLM está marcado en
``_score_entry``; hoy no se usa (decisión: medir el ruido antes).

Ver ADR-050.
"""
from __future__ import annotations

import json
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from core.config import ORBIT_HOME, normalize as _normalize

# ── Constantes ───────────────────────────────────────────────────────────────

TOPICS_FILENAME = "arxiv-temas.md"
INBOX_FILENAME  = "arxiv.md"
STATE_PATH      = ORBIT_HOME / ".arxiv-state.json"

API_URL     = "https://export.arxiv.org/api/query"
USER_AGENT  = "orbit/arxiv-feed (single-user research digest)"
PAGE_SIZE   = 100          # arXiv recomienda no pasar de 2000 por petición
PAGE_PAUSE  = 3.0          # segundos entre peticiones (política de arXiv)
MAX_PAGES   = 10
HTTP_TIMEOUT = 60          # arXiv tarda hasta 30 s en devolver el propio 429
RETRY_PAUSES = (10, 30)     # espera antes de cada reintento
COOLDOWN_HOURS = 6          # tras un rechazo por ritmo, no volver a intentarlo

MARK_TAG    = "#relevante"
SENTINEL    = "<!-- orbit:arxiv-inbox"
ITEM_EMOJI  = "📎"

SEEN_CAP    = 3000         # ids recordados por proyecto (FIFO)

DEFAULTS = {
    "tope": 15,            # artículos escritos por barrido
    "umbral": 3,           # puntuación mínima para entrar
    "retroceso": 7,        # días que mira atrás el primer barrido
}

_ATOM = "{http://www.w3.org/2005/Atom}"
_ARXV = "{http://arxiv.org/schemas/atom}"


# ── Modelo de configuración ──────────────────────────────────────────────────

@dataclass
class Theme:
    name: str
    tag: str
    terms: list = field(default_factory=list)
    companion: bool = False   # sólo cuenta si además acierta otro tema


@dataclass
class TopicConfig:
    categories: list = field(default_factory=list)
    authors: list = field(default_factory=list)
    themes: list = field(default_factory=list)
    excludes: list = field(default_factory=list)
    settings: dict = field(default_factory=dict)

    def setting(self, key: str) -> int:
        try:
            return int(self.settings.get(key, DEFAULTS[key]))
        except (TypeError, ValueError):
            return DEFAULTS[key]


def _slug_tag(name: str) -> str:
    """`Detectores de Xenón` → `#detectores-de-xenon`."""
    text = _normalize(name)
    text = re.sub(r"[^\w\s-]", "", text)
    return "#" + re.sub(r"[\s_]+", "-", text).strip("-")


def _strip_bullet(line: str) -> str:
    return re.sub(r"^\s*[-*+]\s*", "", line).strip()


def parse_topics(text: str) -> TopicConfig:
    """Parse `arxiv-temas.md` → TopicConfig. Tolerante: ignora lo que no entiende.

    Secciones reconocidas (por el encabezado `##`, sin distinguir acentos):

      ## Categorías        lista separada por comas y/o líneas
      ## Autores           un nombre por línea o por comas
      ## Tema: <nombre> #<etiqueta>   viñetas con los términos
      ## Excluir           viñetas con términos que tumban la entrada
      ## Ajustes           `clave: valor`
    """
    cfg = TopicConfig()
    section = None
    theme: Optional[Theme] = None

    for raw in text.splitlines():
        line = raw.rstrip()
        if line.lstrip().startswith("<!--"):
            continue
        if line.startswith("#") and not line.startswith("#" * 4):
            head = line.lstrip("#").strip()
            head_n = _normalize(head)
            if head_n.startswith("tema:") or head_n.startswith("tema "):
                label = head.split(":", 1)[1].strip() if ":" in head else head[4:].strip()
                companion = False
                for mark in ("+acompaña", "+acompana", "+companion"):
                    if _normalize(mark) in _normalize(label):
                        companion = True
                        label = re.sub(re.escape(mark), "", label,
                                       flags=re.IGNORECASE).strip()
                tag_match = re.search(r"(#[\w\-/]+)\s*$", label)
                if tag_match:
                    tag = tag_match.group(1)
                    label = label[:tag_match.start()].strip()
                else:
                    tag = _slug_tag(label)
                theme = Theme(name=label, tag=tag, companion=companion)
                cfg.themes.append(theme)
                section = "tema"
            elif head_n.startswith("categoria"):
                section, theme = "categorias", None
            elif head_n.startswith("autor"):
                section, theme = "autores", None
            elif head_n.startswith("excluir") or head_n.startswith("exclusion"):
                section, theme = "excluir", None
            elif head_n.startswith("ajuste"):
                section, theme = "ajustes", None
            else:
                section, theme = None, None
            continue

        if not line.strip() or section is None:
            continue

        body = _strip_bullet(line)
        if not body:
            continue

        if section == "categorias":
            cfg.categories.extend(c.strip() for c in body.split(",") if c.strip())
        elif section == "autores":
            cfg.authors.extend(a.strip() for a in body.split(",") if a.strip())
        elif section == "excluir":
            cfg.excludes.append(body)
        elif section == "tema" and theme is not None:
            theme.terms.append(body)
        elif section == "ajustes" and ":" in body:
            key, val = body.split(":", 1)
            cfg.settings[_normalize(key)] = val.strip()

    cfg.themes = [t for t in cfg.themes if t.terms]
    return cfg


def load_topics(project_dir: Path) -> Optional[TopicConfig]:
    """Read the project's topic file, or None if it doesn't exist."""
    path = project_dir / "notes" / TOPICS_FILENAME
    if not path.exists():
        return None
    try:
        return parse_topics(path.read_text())
    except OSError:
        return None


# ── Coincidencia de términos ─────────────────────────────────────────────────

def _term_matches(term: str, raw: str, norm: str) -> bool:
    """¿Aparece *term* en el texto?

    Un término entre comillas es **acrónimo estricto**: se busca sobre el texto
    original, respetando mayúsculas y con límite de palabra. Así `"TPC"` no
    dispara con *tpc* dentro de otra palabra ni con minúsculas sueltas. El
    resto se busca sin acentos ni mayúsculas, también con límite de palabra.
    """
    term = term.strip()
    if len(term) >= 2 and term[0] in "\"'" and term[-1] == term[0]:
        inner = term[1:-1].strip()
        if not inner:
            return False
        return re.search(rf"(?<![\w]){re.escape(inner)}(?![\w])", raw) is not None
    needle = _normalize(term)
    if not needle:
        return False
    return re.search(rf"(?<![\w]){re.escape(needle)}(?![\w])", norm) is not None


def _author_matches(watch: str, authors: list) -> bool:
    needle = _normalize(watch)
    return any(needle in _normalize(a) for a in authors)


TITLE_WEIGHT = 2       # un acierto en el título pesa el doble que en el resumen
ABSTRACT_WEIGHT = 1
AUTHOR_WEIGHT = 5


def _score_entry(entry: dict, cfg: TopicConfig) -> dict:
    """Puntúa una entrada. Devuelve {'score', 'tags', 'matched'} (score 0 = fuera).

    Un término acertado en el **título** vale el doble que en el resumen: es lo
    que separa un artículo *sobre* el tema de otro que lo menciona de pasada.
    Sin ese peso, cualquier artículo de astrofísica que cite "deep learning" en
    el resumen adelanta a un artículo de doble beta.

    Enganche para el LLM: aquí es donde entraría una segunda pasada que
    reordene y explique. Hoy la explicación es la lista de términos acertados,
    que sale gratis y es auditable.
    """
    raw_title = entry["title"]
    norm_title = _normalize(raw_title)
    raw  = f"{raw_title}\n{entry['summary']}"
    norm = _normalize(raw)

    for bad in cfg.excludes:
        if _term_matches(bad, raw, norm):
            return {"score": 0, "tags": [], "matched": [], "excluded": bad}

    per_theme = []
    for theme in cfg.themes:
        hits = [t for t in theme.terms if _term_matches(t, raw, norm)]
        if hits:
            per_theme.append((theme, hits))

    # Un tema acompañante (p. ej. "IA") describe el *método*, no el campo: sin
    # ningún tema propio acertado, el artículo es de otra disciplina y se cae.
    if not any(not th.companion for th, _ in per_theme):
        per_theme = []

    tags, matched, score = [], [], 0
    for theme, hits in per_theme:
        tags.append(theme.tag)
        matched.extend(hits)
        for hit in hits:
            score += (TITLE_WEIGHT
                      if _term_matches(hit, raw_title, norm_title)
                      else ABSTRACT_WEIGHT)

    hit_authors = [a for a in cfg.authors if _author_matches(a, entry["authors"])]
    if hit_authors:
        tags.append("#autor-vigilado")
        matched.extend(hit_authors)
        score += AUTHOR_WEIGHT * len(hit_authors)

    return {"score": score, "tags": tags, "matched": matched, "excluded": None}


# ── Descarga ─────────────────────────────────────────────────────────────────

def _build_query(categories: list, since: datetime, until: datetime) -> str:
    cats = " OR ".join(f"cat:{c}" for c in categories) or "cat:hep-ex"
    window = (f"submittedDate:[{since.strftime('%Y%m%d%H%M')}"
              f" TO {until.strftime('%Y%m%d%H%M')}]")
    return f"({cats}) AND {window}"


def _parse_feed(xml_text: str) -> list:
    """Atom → lista de dicts. Devuelve [] si el XML viene roto."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []

    out = []
    for node in root.findall(f"{_ATOM}entry"):
        raw_id = (node.findtext(f"{_ATOM}id") or "").strip()
        if not raw_id:
            continue
        base_id = re.sub(r"v\d+$", "", raw_id.rsplit("/", 1)[-1])
        title   = " ".join((node.findtext(f"{_ATOM}title") or "").split())
        summary = " ".join((node.findtext(f"{_ATOM}summary") or "").split())
        authors = [(a.findtext(f"{_ATOM}name") or "").strip()
                   for a in node.findall(f"{_ATOM}author")]
        cats    = [c.get("term", "") for c in node.findall(f"{_ATOM}category")]
        prim    = node.find(f"{_ARXV}primary_category")
        primary = prim.get("term", "") if prim is not None else (cats[0] if cats else "")
        pdf = ""
        for link in node.findall(f"{_ATOM}link"):
            if link.get("title") == "pdf":
                pdf = link.get("href", "")
        published = (node.findtext(f"{_ATOM}published") or "")[:10]

        out.append({
            "id": base_id,
            "title": title,
            "summary": summary,
            "authors": [a for a in authors if a],
            "categories": [c for c in cats if c],
            "primary": primary,
            "published": published,
            "abs": f"https://arxiv.org/abs/{base_id}",
            "pdf": pdf or f"https://arxiv.org/pdf/{base_id}",
        })
    return out


def _read_url(url: str, timeout: int) -> str:
    """GET con reintento ante 429/503.

    arXiv limita el ritmo y responde 429 cuando se le pide demasiado seguido.
    No es un fallo del que haya que rendirse: se espera y se reintenta, igual
    que ante un corte de red o una espera agotada. Bajo penalización tarda
    hasta 30 s en contestar el propio 429, de ahí que el timeout sea holgado:
    con uno corto, un rechazo por ritmo se disfrazaba de caída.

    El resto de errores HTTP suben tal cual, que sí son problema nuestro: una
    query mal formada da 400 y reintentarla es perder el tiempo.
    """
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    last: Optional[Exception] = None
    for pause in (0,) + RETRY_PAUSES:
        if pause:
            time.sleep(pause)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as exc:
            if exc.code not in (429, 503):
                raise
            last = exc
            hinted = exc.headers.get("Retry-After") if exc.headers else None
            if hinted and str(hinted).strip().isdigit():
                # arXiv dice cuánto esperar: hacerle caso y no insistir antes.
                raise
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last = exc                            # corte de red o espera agotada
    raise last                                    # type: ignore[misc]


def fetch_entries(categories: list, since: datetime, until: datetime, *,
                  timeout: int = HTTP_TIMEOUT, max_pages: int = MAX_PAGES,
                  truncated: Optional[list] = None) -> list:
    """Pide a la API de arXiv los artículos del rango. Lanza OSError si falla.

    Trae como mucho ``max_pages`` × ``PAGE_SIZE`` artículos, los más recientes
    primero. Si el rango contiene más, los viejos se quedan fuera; ``truncated``
    (una lista que el llamante pasa) recibe un True para que pueda decirlo en
    vez de callárselo.
    """
    entries, start = [], 0
    for page_no in range(max_pages):
        params = {
            "search_query": _build_query(categories, since, until),
            "start": start,
            "max_results": PAGE_SIZE,
            "sortBy": "submittedDate",
            "sortOrder": "descending",
        }
        page = _parse_feed(
            _read_url(f"{API_URL}?{urllib.parse.urlencode(params)}", timeout))
        entries.extend(page)
        if len(page) < PAGE_SIZE:
            break
        if page_no == max_pages - 1 and truncated is not None:
            truncated.append(True)
        start += PAGE_SIZE
        time.sleep(PAGE_PAUSE)
    return entries


# ── Estado ───────────────────────────────────────────────────────────────────

def _load_state() -> dict:
    if not STATE_PATH.exists():
        return {"projects": {}}
    try:
        data = json.loads(STATE_PATH.read_text())
        data.setdefault("projects", {})
        return data
    except (json.JSONDecodeError, OSError):
        return {"projects": {}}


def _save_state(state: dict) -> None:
    try:
        STATE_PATH.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n")
    except OSError:
        pass


def _project_state(state: dict, key: str) -> dict:
    return state["projects"].setdefault(
        key, {"last_run": None, "watermark": None, "seen": [], "cooldown_until": None})


def _in_cooldown(st: dict) -> Optional[str]:
    """Devuelve la hora hasta la que hay que esperar, o None si se puede pedir.

    arXiv bloquea por dirección IP cuando se le insiste, y el bloqueo dura
    horas: responde 429 al instante, sin llegar a mirar la query. Reintentar
    dentro de ese plazo no sólo es inútil, sino que lo alimenta. Por eso el
    rechazo por ritmo se recuerda entre ejecuciones, no sólo dentro de una.
    """
    mark = st.get("cooldown_until")
    if not mark:
        return None
    try:
        until = datetime.fromisoformat(mark)
    except ValueError:
        return None
    if until.tzinfo is None:
        until = until.replace(tzinfo=timezone.utc)
    return mark if datetime.now(timezone.utc) < until else None


# ── Bandeja ──────────────────────────────────────────────────────────────────

def _inbox_header(project_name: str) -> str:
    return (
        f"# arXiv — {project_name}\n"
        f"\n"
        f"*Bandeja de entrada. Lo más reciente arriba.*\n"
        f"*Temas y palabras clave: [{TOPICS_FILENAME}](./{TOPICS_FILENAME}) "
        f"— ese fichero lo escribes tú, orbit sólo lo lee.*\n"
        f"*Marca la casilla de lo que quieras conservar y ejecuta "
        f"`arxiv triage`. Escribir `{MARK_TAG}` en la línea vale igual.*\n"
        f"\n"
        f"{SENTINEL} — orbit inserta las entradas nuevas justo debajo. "
        f"No borres esta línea. -->\n"
    )


def item_header(entry: dict, scored: dict) -> str:
    """`- [ ] 📎 [título](url) #tema` — la casilla es la marca de relevancia."""
    tags = " ".join(scored["tags"])
    return f"- [ ] {ITEM_EMOJI} [{entry['title']}]({entry['abs']}) {tags}".rstrip()


def render_entry(entry: dict, scored: dict) -> str:
    """Una entrada de la bandeja: cabecera de item + dos líneas de contexto."""
    tags = " ".join(scored["tags"])
    authors = entry["authors"]
    who = ", ".join(authors[:3])
    if len(authors) > 3:
        who += f" +{len(authors) - 3}"
    lines = [item_header(entry, scored)]
    lines.append(f"  - {entry['id']} · {entry['primary']} · {entry['published']} · {who}")
    if scored["matched"]:
        seen, uniq = set(), []
        for m in scored["matched"]:
            if m not in seen:
                seen.add(m)
                uniq.append(m)
        lines.append("  - coincide: " + ", ".join(uniq[:6]))
    return "\n".join(lines)


def render_block(entries: list, day: str, total_seen: int, dropped: int,
                 window: str = "") -> str:
    """Bloque de un barrido: encabezado + entradas.

    El encabezado lleva la fecha del barrido **y la ventana que cubre**. Sin la
    ventana, recuperar tramos viejos deja varios bloques con la misma fecha de
    hoy y sin forma de saber a qué semana corresponde cada uno.
    """
    n = len(entries)
    head = f"## {day}"
    if window:
        head += f" · {window}"
    head += f" · {n} artículo{'s' if n != 1 else ''}"
    if dropped:
        head += f" · {dropped} más por debajo del tope"
    head += f" · {total_seen} revisados"
    return head + "\n\n" + "\n".join(entries) + "\n"


def prepend_block(inbox_path: Path, project_name: str, block: str) -> None:
    """Inserta *block* justo debajo del centinela, creando la bandeja si falta."""
    if not inbox_path.exists():
        inbox_path.parent.mkdir(parents=True, exist_ok=True)
        inbox_path.write_text(_inbox_header(project_name))

    text  = inbox_path.read_text()
    lines = text.splitlines()
    idx = next((i for i, l in enumerate(lines) if SENTINEL in l), None)
    if idx is None:
        # Sin centinela (el usuario lo borró): añadimos al principio del cuerpo.
        inbox_path.write_text(block + "\n" + text)
        return
    head = lines[: idx + 1]
    tail = lines[idx + 1:]
    while tail and not tail[0].strip():
        tail.pop(0)
    new = head + ["", block.rstrip(), ""] + tail
    inbox_path.write_text("\n".join(new).rstrip() + "\n")


# ── Plantilla de temas ───────────────────────────────────────────────────────

_TOPICS_TEMPLATE = """\
# Temas arXiv — {project}

<!-- Este fichero lo escribes tú. Orbit sólo lo lee.
     Términos entre comillas = acrónimo estricto (mayúsculas exactas).
     Un acierto en el título vale el doble que en el resumen.
     `+acompaña` en la cabecera de un tema = sólo cuenta si además acierta
     otro tema propio (así "deep learning" no trae papers de otro campo). -->

## Categorías
hep-ex, hep-ph, astro-ph.CO, astro-ph.HE, astro-ph.IM
physics.ins-det, physics.data-an

## Autores vigilados

## Tema: neutrinos #neutrinos
- neutrino
- neutrinoless double beta
- double beta decay
- neutrino oscillation
- sterile neutrino

## Tema: Higgs #higgs
- higgs boson
- electroweak symmetry breaking

## Tema: materia oscura #dark-matter
- dark matter
- WIMP
- axion
- direct detection

## Tema: detectores #detectores
- time projection chamber
- "TPC"
- liquid xenon
- gaseous xenon
- liquid argon
- dual-phase
- electroluminescence

## Tema: reconstrucción e identificación #reconstruccion
- event reconstruction
- particle identification
- track reconstruction
- calorimeter reconstruction
- vertex reconstruction
- topological signature

## Tema: estadística #estadistica
- statistical method
- likelihood
- bayesian
- confidence interval
- unfolding
- systematic uncertainty

## Tema: redes neuronales e IA #ia +acompaña
- machine learning
- deep learning
- neural network
- graph neural network
- transformer
- generative model
- normalizing flow

## Excluir
- string landscape
- swampland

## Ajustes
tope: 15
umbral: 3
retroceso: 7
"""


def _resolve_project(project: str) -> Optional[Path]:
    from core.project import _find_new_project
    return _find_new_project(project)


def _inbox_linked(project_dir: Path) -> bool:
    """¿Hay ya una referencia a la bandeja en highlights.md?"""
    from core.log import resolve_file
    hl = resolve_file(project_dir, "highlights")
    if not hl.exists():
        return False
    return f"./notes/{INBOX_FILENAME}" in hl.read_text()


def run_init(project: str) -> int:
    """Create `notes/arxiv-temas.md` + the inbox, and link the inbox from highlights."""
    project_dir = _resolve_project(project)
    if project_dir is None:
        return 1

    notes_dir = project_dir / "notes"
    notes_dir.mkdir(parents=True, exist_ok=True)
    topics = notes_dir / TOPICS_FILENAME
    inbox  = notes_dir / INBOX_FILENAME

    if topics.exists():
        print(f"⚠️  Ya existe {topics.relative_to(project_dir)} — no lo toco.")
    else:
        topics.write_text(_TOPICS_TEMPLATE.format(project=project_dir.name))
        print(f"✓ [{project_dir.name}] temas creados: notes/{TOPICS_FILENAME}")

    if inbox.exists():
        print(f"⚠️  Ya existe {inbox.relative_to(project_dir)} — no lo toco.")
    else:
        inbox.write_text(_inbox_header(project_dir.name))
        print(f"✓ [{project_dir.name}] bandeja creada: notes/{INBOX_FILENAME}")

    # El enlace en highlights se añade una sola vez en la vida del proyecto:
    # `init` sobre una bandeja borrada a mano no debe duplicar la referencia.
    if not _inbox_linked(project_dir):
        from core.highlights import run_hl_add
        run_hl_add(project_dir.name, "Feed de arXiv", "refs",
                   link=f"./notes/{INBOX_FILENAME}")

    print()
    print(f"   Edita notes/{TOPICS_FILENAME} y lanza `arxiv fetch {project_dir.name}`.")
    return 0


# ── Barrido ──────────────────────────────────────────────────────────────────

def _parse_day(arg: Optional[str]) -> Optional[datetime]:
    """`2026-08-01`, `today`, `-7d`… → datetime en UTC, o None."""
    if not arg:
        return None
    from core.dateparse import parse_date
    resolved = parse_date(arg)
    if not resolved:
        return None
    return datetime.fromisoformat(resolved).replace(tzinfo=timezone.utc)


def _since_from(state_p: dict, cfg: TopicConfig, since_arg: Optional[str]) -> datetime:
    if since_arg:
        parsed = _parse_day(since_arg)
        if parsed:
            return parsed
    mark = state_p.get("watermark")
    if mark:
        try:
            parsed = datetime.fromisoformat(mark)
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    return datetime.now(timezone.utc) - timedelta(days=cfg.setting("retroceso"))


def fetch_for_project(project_dir: Path, *, since_arg: Optional[str] = None,
                      until_arg: Optional[str] = None,
                      max_n: Optional[int] = None, dry_run: bool = False,
                      quiet: bool = False, force: bool = False) -> dict:
    """Un barrido sobre un proyecto ya resuelto. Devuelve un resumen.

    Claves del resumen: ``ok``, ``written``, ``scanned``, ``dropped``, ``msg``.
    No lanza: los fallos de red vuelven como ``ok=False`` y dejan la marca de
    agua intacta para reintentar mañana.
    """
    cfg = load_topics(project_dir)
    if cfg is None:
        return {"ok": False, "written": 0, "scanned": 0, "dropped": 0,
                "msg": f"sin notes/{TOPICS_FILENAME}"}

    state   = _load_state()
    st      = _project_state(state, project_dir.name)

    waiting = None if force else _in_cooldown(st)
    if waiting:
        local = datetime.fromisoformat(waiting).astimezone()
        return {"ok": False, "written": 0, "scanned": 0, "dropped": 0,
                "cooldown": True,
                "msg": f"arXiv nos bloqueó por ritmo; en espera hasta "
                       f"{local:%H:%M} ({local:%d-%m}). `--force` lo ignora"}

    since   = _since_from(st, cfg, since_arg)
    until   = _parse_day(until_arg) or datetime.now(timezone.utc)
    seen    = set(st.get("seen", []))

    trunc: list = []
    try:
        raw = fetch_entries(cfg.categories, since, until, truncated=trunc)
    except urllib.error.HTTPError as exc:
        if exc.code == 429:
            until = datetime.now(timezone.utc) + timedelta(hours=COOLDOWN_HOURS)
            hinted = exc.headers.get("Retry-After") if exc.headers else None
            if hinted and str(hinted).strip().isdigit():
                until = datetime.now(timezone.utc) + timedelta(seconds=int(hinted))
            st["cooldown_until"] = until.isoformat(timespec="minutes")
            _save_state(state)
            local = until.astimezone()
            return {"ok": False, "written": 0, "scanned": 0, "dropped": 0,
                    "cooldown": True,
                    "msg": f"arXiv limita el ritmo (429): en espera hasta "
                           f"{local:%H:%M} ({local:%d-%m})"}
        return {"ok": False, "written": 0, "scanned": 0, "dropped": 0,
                "msg": f"arXiv responde {exc.code}"}
    except Exception as exc:                       # red, DNS, timeout
        return {"ok": False, "written": 0, "scanned": 0, "dropped": 0,
                "msg": f"arXiv no responde ({type(exc).__name__})"}

    since_day = since.date().isoformat()
    candidates = []
    for entry in raw:
        if entry["id"] in seen:
            continue
        if entry["published"] and entry["published"] < since_day:
            continue                                # reemplazo de un v1 antiguo
        scored = _score_entry(entry, cfg)
        if scored["score"] >= cfg.setting("umbral"):
            candidates.append((entry, scored))

    candidates.sort(key=lambda p: (p[1]["score"], p[0]["published"]), reverse=True)

    tope    = max_n if max_n is not None else cfg.setting("tope")
    chosen  = candidates[:tope]
    dropped = len(candidates) - len(chosen)

    if not dry_run:
        if chosen:
            window = f"{since:%d-%m} → {until:%d-%m}"
            block = render_block([render_entry(e, s) for e, s in chosen],
                                 date.today().isoformat(), len(raw), dropped,
                                 window=window)
            prepend_block(project_dir / "notes" / INBOX_FILENAME,
                          project_dir.name, block)
        st["seen"] = (st.get("seen", []) + [e["id"] for e, _ in candidates])[-SEEN_CAP:]
        # La marca de agua sólo avanza. Recuperar un tramo viejo con --until no
        # debe hacerla retroceder: el barrido de mañana volvería a mirar semanas
        # ya vistas y el día pendiente se quedaría sin cubrir.
        mark = until.strftime("%Y-%m-%dT%H:%M")
        st["watermark"] = max(mark, st.get("watermark") or "")
        st["last_run"] = date.today().isoformat()
        _save_state(state)

    if not quiet:
        for entry, scored in chosen:
            print("  " + item_header(entry, scored).split("] ", 1)[-1])

    return {"ok": True, "written": len(chosen), "scanned": len(raw),
            "dropped": dropped, "truncated": bool(trunc),
            "msg": f"{len(chosen)} nuevos de {len(raw)} revisados"}


def run_fetch(project: Optional[str] = None, *, since: Optional[str] = None,
              until: Optional[str] = None,
              max_n: Optional[int] = None, dry_run: bool = False,
              force: bool = False) -> int:
    """Barrido manual. Sin proyecto, barre todos los que tengan fichero de temas."""
    if project is None:
        targets = feed_projects()
        if not targets:
            print(f"Ningún proyecto tiene notes/{TOPICS_FILENAME}.")
            print("  Créalo con: arxiv init <proyecto>")
            return 1
        rc = 0
        for d in targets:
            rc |= _fetch_one(d, since=since, until=until, max_n=max_n,
                             dry_run=dry_run, force=force)
        return rc

    project_dir = _resolve_project(project)
    if project_dir is None:
        return 1

    if load_topics(project_dir) is None:
        print(f"Error: [{project_dir.name}] no tiene notes/{TOPICS_FILENAME}.")
        print(f"  Créalo con: arxiv init {project_dir.name}")
        return 1

    return _fetch_one(project_dir, since=since, until=until, max_n=max_n,
                      dry_run=dry_run, force=force)


def _fetch_one(project_dir: Path, *, since: Optional[str] = None,
               until: Optional[str] = None,
               max_n: Optional[int] = None, dry_run: bool = False,
               force: bool = False) -> int:
    res = fetch_for_project(project_dir, since_arg=since, until_arg=until,
                            max_n=max_n, dry_run=dry_run, force=force)
    if not res["ok"]:
        print(f"⚠️  [{project_dir.name}] {res['msg']} — la marca de agua no avanza.")
        return 1

    tail = f" · {res['dropped']} por debajo del tope" if res["dropped"] else ""
    prefix = "(simulación) " if dry_run else ""
    print(f"✓ {prefix}[{project_dir.name}] {res['written']} en la bandeja, "
          f"{res['scanned']} revisados{tail}")
    if res.get("truncated"):
        print(f"   ⚠️  La ventana daba para más de {MAX_PAGES * PAGE_SIZE} "
              f"artículos: sólo se han mirado los más recientes.")
        print("   Repítela por tramos con --since y --until (una o dos semanas).")
    if res["written"] and not dry_run:
        print(f"   notes/{INBOX_FILENAME} — marca la casilla y lanza `arxiv triage`")
    return 0


# ── Triaje ───────────────────────────────────────────────────────────────────

_ITEM_RE = re.compile(
    rf"^-\s+(?:\[(?P<check>.)\]\s+)?{re.escape(ITEM_EMOJI)}\s+"
    rf"\[(?P<title>.+?)\]\((?P<url>[^)]+)\)(?P<rest>.*)$")


@dataclass
class InboxItem:
    title: str
    url: str
    tags: list
    marked: bool
    start: int          # índice de la línea de cabecera
    end: int            # índice de la última línea del item (inclusive)


def parse_inbox(lines: list) -> list:
    """Localiza los items de la bandeja y si llevan la marca de relevancia."""
    items = []
    for i, line in enumerate(lines):
        m = _ITEM_RE.match(line)
        if not m:
            continue
        j = i + 1
        while j < len(lines) and (lines[j].startswith("  ") or not lines[j].strip()):
            if not lines[j].strip():
                # Una línea en blanco sólo pertenece al item si hay más cuerpo debajo.
                k = j
                while k < len(lines) and not lines[k].strip():
                    k += 1
                if k >= len(lines) or not lines[k].startswith("  "):
                    break
                j = k
                continue
            j += 1
        rest = m.group("rest")
        tags = re.findall(r"(#[\w\-/áéíóúñÁÉÍÓÚÑ]+)", rest)
        items.append(InboxItem(
            title=m.group("title").strip(),
            url=m.group("url").strip(),
            tags=[t for t in tags if _normalize(t) != _normalize(MARK_TAG)],
            marked=((m.group("check") or " ").strip().lower() not in ("", "-")
                    or any(_normalize(t) == _normalize(MARK_TAG) for t in tags)),
            start=i, end=j - 1,
        ))
    return items


def _drop_lines(lines: list, items: list) -> list:
    """Quita los items indicados y las cabeceras de día que se queden vacías."""
    doomed = set()
    for it in items:
        doomed.update(range(it.start, it.end + 1))
    kept = [l for i, l in enumerate(lines) if i not in doomed]

    out, i = [], 0
    while i < len(kept):
        line = kept[i]
        if line.startswith("## "):
            j = i + 1
            has_item = False
            while j < len(kept) and not kept[j].startswith("## "):
                if _ITEM_RE.match(kept[j]):
                    has_item = True
                    break
                j += 1
            if not has_item:
                i += 1
                while i < len(kept) and not kept[i].startswith("## ") and not kept[i].strip():
                    i += 1
                continue
        out.append(line)
        i += 1
    return out


def run_triage(project: Optional[str] = None, purge: bool = False) -> int:
    """Promociona a highlights los items marcados y los saca de la bandeja."""
    if project is None:
        targets = feed_projects()
        if len(targets) == 1:
            project_dir = targets[0]
        elif not targets:
            print(f"Ningún proyecto tiene notes/{TOPICS_FILENAME}.")
            return 1
        else:
            print("Varios proyectos con feed — indica cuál:")
            for d in targets:
                print(f"  {d.name}")
            return 1
    else:
        project_dir = _resolve_project(project)
        if project_dir is None:
            return 1

    inbox = project_dir / "notes" / INBOX_FILENAME
    if not inbox.exists():
        print(f"Error: [{project_dir.name}] no tiene notes/{INBOX_FILENAME}.")
        return 1

    lines  = inbox.read_text().splitlines()
    items  = parse_inbox(lines)
    marked = [it for it in items if it.marked]
    rest   = [it for it in items if not it.marked]

    if not items:
        print(f"[{project_dir.name}] la bandeja está vacía.")
        return 0

    if marked:
        from core.highlights import run_hl_add
        for it in marked:
            run_hl_add(project_dir.name, it.title, "refs",
                       link=it.url, tags=it.tags)
        lines = _drop_lines(lines, marked)
        inbox.write_text("\n".join(lines).rstrip() + "\n")
        print(f"✓ [{project_dir.name}] {len(marked)} promovido"
              f"{'s' if len(marked) != 1 else ''} a highlights.md como 📎")
    else:
        print(f"[{project_dir.name}] ningún item marcado "
              f"(casilla o {MARK_TAG}).")

    if not rest:
        return 0

    n = len(rest)
    if not purge:
        if not sys.stdin.isatty():
            print(f"   Quedan {n} sin marcar en la bandeja.")
            return 0
        try:
            ans = input(f"  ¿Vaciar los {n} sin marcar? [s/N]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if ans not in ("s", "si", "sí", "y", "yes"):
            print(f"   Quedan {n} sin marcar en la bandeja.")
            return 0

    lines = _drop_lines(lines, parse_inbox(lines))
    inbox.write_text("\n".join(lines).rstrip() + "\n")
    print(f"✓ [{project_dir.name}] bandeja vaciada ({n} descartado"
          f"{'s' if n != 1 else ''})")
    return 0


# ── Hook action (cadena `shell_start`) ───────────────────────────────────────

def feed_projects() -> list:
    """Proyectos del workspace con fichero de temas."""
    from core.project import iter_project_dirs, _is_new_project
    out = []
    for d in iter_project_dirs():
        if _is_new_project(d) and (d / "notes" / TOPICS_FILENAME).exists():
            out.append(d)
    return out


def _action_arxiv_fetch(ctx):
    """Barrido diario: días laborables, una vez al día, por proyecto configurado.

    Silencioso cuando no hay nada que hacer. Nunca rompe el arranque: un fallo
    de red deja la marca de agua quieta y se reintenta mañana.
    """
    try:
        projects = feed_projects()
    except Exception as exc:
        return {"ok": False, "msg": f"{type(exc).__name__}: {exc}"}

    if not projects:
        return {"ok": True, "msg": "sin proyectos con feed", "skipped": True}

    today = date.today()
    if today.weekday() >= 5:
        return {"ok": True, "msg": "fin de semana"}

    state = _load_state()
    pending = [d for d in projects
               if _project_state(state, d.name).get("last_run") != today.isoformat()]
    if not pending:
        return {"ok": True, "msg": "ya barrido hoy"}

    total, failed = 0, []
    for project_dir in pending:
        try:
            res = fetch_for_project(project_dir, quiet=True)
        except Exception as exc:
            failed.append(f"{project_dir.name}: {type(exc).__name__}")
            continue
        if not res["ok"]:
            if not res.get("cooldown"):
                failed.append(f"{project_dir.name}: {res['msg']}")
            continue
        total += res["written"]
        if res["written"]:
            print(f"  📎 {res['written']} artículo{'s' if res['written'] != 1 else ''} "
                  f"nuevo{'s' if res['written'] != 1 else ''} en "
                  f"[{project_dir.name}] notes/{INBOX_FILENAME}")

    if failed:
        return {"ok": False, "msg": "; ".join(failed)}
    return {"ok": True, "msg": f"{total} nuevos"}

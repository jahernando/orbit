"""families.py — familias de proyectos (ADR-059).

Una familia es un grupo de proyectos que se tratan juntos (NEXT, HK,
gestión…) con sus días de la semana. Vive solo en ``orbit.json``: no toca
ningún fichero-verdad y se quita borrando el bloque.

    "families": {
      "next": {"emoji": "🔵", "days": ["wed"], "projects": ["next-general", …]},
      "ges":  {"emoji": "⚙️", "days": ["mon"], "types": ["gestion"]}
    }

Reglas:

- Un proyecto pertenece a **una sola familia**. Nombrarlo en ``projects``
  manda sobre su tipo (``types``): ``next-pn24`` es ⚙️ gestión pero va a
  ``next`` si está en su lista. Si dos familias lo nombran, gana la primera
  (y ``doctor`` avisa).
- Puede haber proyectos sin familia, varias familias el mismo día y varios
  días para una familia.
- Los nombres de proyecto van sin el emoji de tipo (``next-gala``).

Solo lectura: las familias agrupan lo que se ve (secretario, ``day``);
crear o editar citas sigue siendo cosa de un proyecto.
"""

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import List, Optional

DAY_KEYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
DAY_NAMES = ("lunes", "martes", "miércoles", "jueves", "viernes",
             "sábado", "domingo")


@dataclass(frozen=True)
class Family:
    name: str
    emoji: str
    days: tuple            # weekday() de date: 0 = lunes
    projects: frozenset    # nombres sin emoji de tipo
    types: frozenset       # claves de tipo normalizadas (``gestion``)

    @property
    def label(self) -> str:
        return f"{self.emoji} {self.name}".strip()

    @property
    def days_label(self) -> str:
        names = [DAY_NAMES[d] for d in self.days]
        if len(names) <= 1:
            return names[0] if names else "sin día"
        return ", ".join(names[:-1]) + " y " + names[-1]

    def is_day(self, day: date) -> bool:
        return day.weekday() in self.days


def _config(config: Optional[dict]) -> dict:
    if config is not None:
        return config
    from core import config as _cfg
    try:
        return _cfg._load_orbit_json()
    except (ValueError, OSError):
        return {}


def load_families(config: Optional[dict] = None) -> List[Family]:
    """Familias de ``orbit.json`` en su orden. Tolerante: lo mal escrito se
    ignora aquí y lo cuenta ``problems``."""
    from core.config import normalize
    raw = _config(config).get("families") or {}
    if not isinstance(raw, dict):
        return []
    out = []
    for name, spec in raw.items():
        if not isinstance(spec, dict):
            continue
        days = sorted({DAY_KEYS.index(d.lower()) for d in spec.get("days") or []
                       if isinstance(d, str) and d.lower() in DAY_KEYS})
        projects = frozenset(p for p in spec.get("projects") or []
                             if isinstance(p, str))
        types = frozenset(normalize(t) for t in spec.get("types") or []
                          if isinstance(t, str))
        out.append(Family(str(name), str(spec.get("emoji") or ""),
                          tuple(days), projects, types))
    return out


def project_key(project_dir: Path) -> str:
    """Nombre del proyecto sin emoji de tipo (``⚙️next-pn24`` → ``next-pn24``)."""
    from core.project import _strip_type_emoji
    return _strip_type_emoji(project_dir.name)


def project_type(project_dir: Path) -> str:
    """Clave de tipo normalizada del proyecto (la de su directorio padre)."""
    from core.config import normalize
    from core.project import _strip_type_emoji
    return normalize(_strip_type_emoji(project_dir.parent.name))


def family_of(project_dir: Path,
              families: Optional[List[Family]] = None) -> Optional[Family]:
    """Familia del proyecto: primero por nombre, luego por tipo."""
    fams = load_families() if families is None else families
    key = project_key(project_dir)
    for f in fams:
        if key in f.projects:
            return f
    ptype = project_type(project_dir)
    for f in fams:
        if ptype in f.types:
            return f
    return None


def families_on(day: date,
                families: Optional[List[Family]] = None) -> List[Family]:
    """Familias cuyo día es *day*, en el orden de ``orbit.json``."""
    fams = load_families() if families is None else families
    return [f for f in fams if f.is_day(day)]


def group_order(day: date, families: List[Family]) -> List[Optional[Family]]:
    """Orden de los grupos: las familias de *day* primero, luego el resto
    (orden de ``orbit.json``) y al final ``None`` (sin familia)."""
    today = [f for f in families if f.is_day(day)]
    return today + [f for f in families if f not in today] + [None]


def members(family: Family, project_dirs,
            families: Optional[List[Family]] = None) -> list:
    """Directorios de *project_dirs* que pertenecen a *family*."""
    fams = load_families() if families is None else families
    return [p for p in project_dirs
            if (f := family_of(p, fams)) is not None and f.name == family.name]


def problems(config: Optional[dict] = None, project_dirs=None) -> List[str]:
    """Avisos sobre el bloque ``families`` (para ``doctor``)."""
    from core.config import _load_types, normalize
    cfg = _config(config)
    raw = cfg.get("families")
    if raw is None:
        return []
    if not isinstance(raw, dict):
        return ["`families` debe ser un objeto {nombre: {...}}"]
    out = []
    if project_dirs is None:
        from core.config import iter_project_dirs
        project_dirs = list(iter_project_dirs())
    existing = {project_key(p) for p in project_dirs}
    known_types = {normalize(t) for t in (cfg.get("types") or _load_types())}
    owner_p: dict = {}
    owner_t: dict = {}
    for name, spec in raw.items():
        if not isinstance(spec, dict):
            out.append(f"familia «{name}»: debe ser un objeto")
            continue
        bad = [d for d in spec.get("days") or []
               if not (isinstance(d, str) and d.lower() in DAY_KEYS)]
        if bad:
            out.append(f"familia «{name}»: días no válidos {bad} "
                       f"(usa {', '.join(DAY_KEYS)})")
        for p in spec.get("projects") or []:
            if p not in existing:
                out.append(f"familia «{name}»: el proyecto «{p}» no existe")
            if p in owner_p:
                out.append(f"«{p}» está en «{owner_p[p]}» y en «{name}»: "
                           f"cuenta solo en «{owner_p[p]}»")
            else:
                owner_p[p] = name
        for t in spec.get("types") or []:
            nt = normalize(t) if isinstance(t, str) else t
            if nt not in known_types:
                out.append(f"familia «{name}»: el tipo «{t}» no existe")
            if nt in owner_t:
                out.append(f"el tipo «{t}» está en «{owner_t[nt]}» y en «{name}»: "
                           f"cuenta solo en «{owner_t[nt]}»")
            else:
                owner_t[nt] = name
    return out

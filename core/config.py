"""Orbit workspace configuration — single source of truth for all paths."""

import json
import os
import unicodedata
from pathlib import Path

# ORBIT_CODE: where the code lives (always the directory containing orbit.py).
# ORBIT_HOME: the user's data workspace (projects, config, history).
# When ORBIT_HOME is not set, defaults to ORBIT_CODE (single-directory setup).
ORBIT_CODE   = Path(__file__).resolve().parent.parent
ORBIT_HOME   = Path(os.environ.get("ORBIT_HOME", ORBIT_CODE))

# Orbit config: from orbit.json → fallbacks
_ORBIT_JSON_PATH = ORBIT_HOME / "orbit.json"
_orbit_space = ORBIT_HOME.name
_orbit_emoji = "🚀"
if _ORBIT_JSON_PATH.exists():
    try:
        _cfg = json.loads(_ORBIT_JSON_PATH.read_text())
        _orbit_space = _cfg.get("space", _orbit_space)
        _orbit_emoji = _cfg.get("emoji", "🚀")
    except (json.JSONDecodeError, KeyError):
        pass
ORBIT_SPACE   = _orbit_space
ORBIT_PROMPT = os.environ.get("ORBIT_PROMPT", _orbit_emoji)

PROJECTS_DIR  = ORBIT_HOME / f"{_orbit_emoji}proyectos"
TEMPLATES_DIR = ORBIT_CODE / "📐templates"
CMD_MD        = ORBIT_HOME / "cmd.md"
PROYECTOS_MD  = ORBIT_HOME / "proyectos.md"
HISTORY_MD    = ORBIT_HOME / "history.md"


# ── Project types (from orbit.json) ──────────────────────────────────────────

_ORBIT_JSON = _ORBIT_JSON_PATH

_DEFAULT_TYPES = {
    "investigacion": "🌀",
    "docencia":      "📚",
    "gestion":       "⚙️",
    "formacion":     "📖",
    "software":      "💻",
    "personal":      "🌿",
    "mision":        "☀️",
}

_ACCENT_MAP = {
    "investigación": "investigacion",
    "gestión":       "gestion",
    "formación":     "formacion",
    "misión":        "mision",
}


def normalize(text: str) -> str:
    """Lowercase + strip accents. Single source for all modules."""
    return unicodedata.normalize("NFD", text).encode("ascii", "ignore").decode().lower().strip()


def _load_orbit_json() -> dict:
    """Load orbit.json, return the full config dict."""
    if _ORBIT_JSON.exists():
        return json.loads(_ORBIT_JSON.read_text())
    return {}


def _load_types() -> dict:
    """Load project types {key: emoji} from orbit.json, with defaults fallback."""
    config = _load_orbit_json()
    return config.get("types", _DEFAULT_TYPES)


def get_type_map() -> dict:
    """Return {normalized_key: emoji} including accent variants."""
    base = _load_types()
    result = {}
    for key, emoji in base.items():
        norm = normalize(key)
        result[norm] = emoji
        # Add accented variant if known
        for accented, plain in _ACCENT_MAP.items():
            if plain == norm:
                result[accented] = emoji
    return result


def get_type_label() -> dict:
    """Return {normalized_key: label} e.g. {"investigacion": "Investigación"}."""
    base = _load_types()
    result = {}
    for key in base:
        norm = normalize(key)
        result[norm] = key.capitalize()
        for accented, plain in _ACCENT_MAP.items():
            if plain == norm:
                result[accented] = accented.capitalize()
                result[norm] = accented.capitalize()  # prefer accented label
    return result


def get_type_emojis() -> tuple:
    """Return tuple of all type emojis (for field detection in project files)."""
    return tuple(set(_load_types().values()))


def get_reverse_type_map() -> dict:
    """Return {emoji: type_name} for looking up type name from emoji."""
    return {emoji: key for key, emoji in _load_types().items()}


# ── Type management commands ──────────────────────────────────────────────────

def _save_orbit_json(config: dict) -> None:
    """Write orbit.json back."""
    _ORBIT_JSON.write_text(json.dumps(config, indent=2, ensure_ascii=False) + "\n")


def run_type_list() -> int:
    """List configured project types."""
    types = _load_types()
    if not types:
        print("No hay tipos configurados.")
        return 0
    print("Tipos de proyecto:")
    for key, emoji in sorted(types.items()):
        print(f"  {emoji}  {key}")
    return 0


def _projects_with_emoji(emoji: str) -> list:
    """Return list of project dir names whose folder starts with this emoji."""
    if not PROJECTS_DIR.exists():
        return []
    return [d.name for d in PROJECTS_DIR.iterdir()
            if d.is_dir() and d.name.startswith(emoji)]


def run_type_add(name: str, emoji: str) -> int:
    """Add a new project type."""
    norm = normalize(name)
    config = _load_orbit_json()
    types = config.get("types", dict(_DEFAULT_TYPES))

    if norm in types:
        print(f"⚠️  El tipo '{norm}' ya existe ({types[norm]})")
        return 1

    # Check if emoji is already used by another type
    for existing_key, existing_emoji in types.items():
        if existing_emoji == emoji:
            print(f"⚠️  El emoji {emoji} ya está en uso para el tipo '{existing_key}'")
            return 1

    types[norm] = emoji
    config["types"] = types
    _save_orbit_json(config)
    print(f"✓ Tipo añadido: {emoji}  {norm}")
    return 0


def run_type_drop(name: str) -> int:
    """Remove a project type."""
    norm = normalize(name)
    config = _load_orbit_json()
    types = config.get("types", dict(_DEFAULT_TYPES))

    if norm not in types:
        print(f"⚠️  El tipo '{norm}' no existe")
        return 1

    emoji = types[norm]
    projects = _projects_with_emoji(emoji)
    if projects:
        print(f"⚠️  No se puede eliminar '{norm}': hay {len(projects)} proyecto{'s' if len(projects) != 1 else ''} de este tipo")
        for p in projects[:5]:
            print(f"      {p}")
        if len(projects) > 5:
            print(f"      ... y {len(projects) - 5} más")
        return 1

    types.pop(norm)
    config["types"] = types
    _save_orbit_json(config)
    print(f"✓ Tipo eliminado: {emoji}  {norm}")
    return 0

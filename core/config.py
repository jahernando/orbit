"""Orbit workspace configuration — single source of truth for all paths."""

import json
import os
import unicodedata
from pathlib import Path

# ORBIT_HOME: the user's workspace directory.
# Priority: ORBIT_HOME env var → parent of orbit.py (development mode)
_default = Path(__file__).resolve().parent.parent
ORBIT_HOME   = Path(os.environ.get("ORBIT_HOME", _default))
ORBIT_PROMPT = os.environ.get("ORBIT_PROMPT", "🚀")

PROJECTS_DIR  = ORBIT_HOME / "🚀proyectos"
TEMPLATES_DIR = ORBIT_HOME / "📐templates"
CMD_MD        = ORBIT_HOME / "cmd.md"


# ── Project types (from orbit.json) ──────────────────────────────────────────

_ORBIT_JSON = ORBIT_HOME / "orbit.json"

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


def _normalize(text: str) -> str:
    return unicodedata.normalize("NFD", text).encode("ascii", "ignore").decode().lower()


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
        norm = _normalize(key)
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
        norm = _normalize(key)
        result[norm] = key.capitalize()
        for accented, plain in _ACCENT_MAP.items():
            if plain == norm:
                result[accented] = accented.capitalize()
                result[norm] = accented.capitalize()  # prefer accented label
    return result


def get_type_emojis() -> tuple:
    """Return tuple of all type emojis (for field detection in project files)."""
    return tuple(set(_load_types().values()))


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


def run_type_add(name: str, emoji: str) -> int:
    """Add a new project type."""
    norm = _normalize(name)
    config = _load_orbit_json()
    types = config.get("types", dict(_DEFAULT_TYPES))

    if norm in types:
        print(f"⚠️  El tipo '{norm}' ya existe ({types[norm]})")
        return 1

    types[norm] = emoji
    config["types"] = types
    _save_orbit_json(config)
    print(f"✓ Tipo añadido: {emoji}  {norm}")
    return 0


def run_type_drop(name: str) -> int:
    """Remove a project type."""
    norm = _normalize(name)
    config = _load_orbit_json()
    types = config.get("types", dict(_DEFAULT_TYPES))

    if norm not in types:
        print(f"⚠️  El tipo '{norm}' no existe")
        return 1

    emoji = types.pop(norm)
    config["types"] = types
    _save_orbit_json(config)
    print(f"✓ Tipo eliminado: {emoji}  {norm}")
    return 0

"""Orbit workspace configuration — single source of truth for all paths."""

import os
from pathlib import Path

# ORBIT_HOME: the user's workspace directory.
# Priority: ORBIT_HOME env var → parent of orbit.py (development mode)
_default = Path(__file__).resolve().parent.parent
ORBIT_HOME   = Path(os.environ.get("ORBIT_HOME", _default))
ORBIT_PROMPT = os.environ.get("ORBIT_PROMPT", "🚀")

PROJECTS_DIR  = ORBIT_HOME / "🚀proyectos"
TEMPLATES_DIR = ORBIT_HOME / "📐templates"
CMD_MD        = ORBIT_HOME / "cmd.md"

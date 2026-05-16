"""views/secretary — viewers del workspace dashboard.

Cada viewer es una función `generate(out_path)` pura: lee la verdad
(agenda.md, logbook.md, etc. de los proyectos del workspace), escribe un
.md en `📋secretary/`, return. La orquestación (qué viewer correr cuándo)
vive en `orbit.run_dash`.

Config en `<workspace>/orbit.json`:

    "secretary": {
      "agenda_days": 14,      // ventana de agenda-next, [1, 90]
      "report_days": 14       // ventana de report-summary, [1, 365]
    }
"""

import json
from pathlib import Path


DEFAULT_AGENDA_DAYS = 14
DEFAULT_REPORT_DAYS = 14

MIN_AGENDA_DAYS, MAX_AGENDA_DAYS = 1, 90
MIN_REPORT_DAYS, MAX_REPORT_DAYS = 1, 365


def _clamp_int(value, lo: int, hi: int, default: int) -> int:
    try:
        v = int(value)
    except (TypeError, ValueError):
        return default
    if lo <= v <= hi:
        return v
    return default


def _load_secretary_config(workspace_root: Path) -> dict:
    """Read <workspace>/orbit.json → 'secretary' section, return merged config.

    Defaults: agenda_days=14, report_days=14. Values are clamped to
    [MIN_*, MAX_*]; bad types or out-of-range fall back silently to
    defaults.
    """
    cfg = {
        "agenda_days": DEFAULT_AGENDA_DAYS,
        "report_days": DEFAULT_REPORT_DAYS,
    }
    path = workspace_root / "orbit.json"
    if not path.exists():
        return cfg
    try:
        data = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return cfg
    user = data.get("secretary")
    if not isinstance(user, dict):
        return cfg
    if "agenda_days" in user:
        cfg["agenda_days"] = _clamp_int(
            user["agenda_days"], MIN_AGENDA_DAYS, MAX_AGENDA_DAYS,
            DEFAULT_AGENDA_DAYS,
        )
    if "report_days" in user:
        cfg["report_days"] = _clamp_int(
            user["report_days"], MIN_REPORT_DAYS, MAX_REPORT_DAYS,
            DEFAULT_REPORT_DAYS,
        )
    return cfg

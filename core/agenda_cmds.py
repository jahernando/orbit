"""agenda_cmds — compatibility shim around the :mod:`core.agenda` subpackage.

Phase 3.C (2026-05-15, ADR-031) split this historical 2200-line monolith
into six focused modules under ``core/agenda/``. The shim keeps every
public and private name accessible at its old import path so the ~20
external callers (orbit.py, ring.py, ring_export.py, ics.py,
ics_share.py, agenda_view.py, panel.py, doctor.py, email.py, archive.py,
stats.py, inbox.py, reorganize.py, cronograma.py, project_view.py,
shell.py and scripts/) don't break.

New code should import from :mod:`core.agenda` (or one of its submodules)
directly. The shim is slated for removal when Phase 4.B introduces the
``orbit/api.py`` seam.
"""
import sys as _sys

from core import agenda as _agenda_pkg

# Re-export every name (including ``_underscore`` privates) defined on
# the subpackage's namespace. ``from core.agenda_cmds import _foo`` keeps
# resolving to the same object as ``core.agenda._foo``.
_self = _sys.modules[__name__]
for _name in dir(_agenda_pkg):
    if _name.startswith("__"):
        continue
    setattr(_self, _name, getattr(_agenda_pkg, _name))

del _sys, _agenda_pkg, _self, _name

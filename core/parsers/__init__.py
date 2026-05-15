"""core.parsers — argparse subparsers extracted from ``orbit.py``.

Phase 4.B step 4. The monolithic 720-line ``_build_parser`` in
``orbit.py`` is split here by area:

  * :mod:`core.parsers._helpers` — :class:`_OrbitParser` and the
    ``_add_*_args`` helpers shared by multiple subparsers.
  * :mod:`core.parsers.agenda`   — task / milestone / event / reminder /
    crono subparsers (the appointment system).
  * :mod:`core.parsers.rest`     — every other top-level verb.

``orbit.py::_build_parser`` orchestrates by importing ``agenda.register``
and ``rest.register`` in the original declaration order, so
``orbit --help`` stays approximately the same.
"""

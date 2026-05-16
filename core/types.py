"""types.py — shared dataclasses used across core/ and views/.

Tipos pequeños que viven aquí porque más de un módulo los emite o los
consume y no pertenecen a ninguno en particular. Mantener este fichero
lean: sólo data containers, sin lógica.
"""

from typing import Optional


class Issue:
    """Un problema detectado por validación (doctor / cronograma / …).

    Inmutable de facto vía ``__slots__``: project + file + line_num + line
    identifican la posición; msg es el diagnóstico; fix (opcional) es la
    línea corregida sugerida.
    """
    __slots__ = ("project", "file", "line_num", "line", "msg", "fix")

    def __init__(self, project: str, file: str, line_num: int,
                 line: str, msg: str, fix: Optional[str] = None):
        self.project  = project
        self.file     = file
        self.line_num = line_num
        self.line     = line
        self.msg      = msg
        self.fix      = fix

    def __repr__(self):
        return f"[{self.project}] {self.file}:{self.line_num} — {self.msg}"

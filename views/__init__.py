"""views/ — readers de la verdad → artefactos derivados.

Convención: todo viewer que emite a `📊panel/<subsystema>/...md` arranca
su output con un banner visible que indica:

  - emoji del workspace (de `ORBIT_EMOJI` en `core/config.py`),
  - módulo que lo generó (`secretary.today`, `focus.week`, ...),
  - timestamp `YYYY-MM-DD HH:MM` de la regeneración.

Marca el fichero como derivado de forma legible para el usuario, no como
HTML-comment oculto. Si el banner cambia, debería cambiarse aquí para que
todos los viewers se mantengan consistentes.
"""

from datetime import datetime


def autogen_banner(module: str) -> str:
    """Banner markdown visible para viewers que emiten a `📊panel/`.

    Args:
        module: nombre corto del viewer (e.g., `"secretary.today"`,
                `"focus.week"`). Se muestra en monospace.

    Returns:
        String con el banner + 2 saltos de línea (separación del H1
        siguiente).
    """
    from core.config import ORBIT_EMOJI
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    return f"*{ORBIT_EMOJI} creado por `{module}` · {ts}*\n\n"

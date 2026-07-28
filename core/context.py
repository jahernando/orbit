"""context.py — proyecto fijado (*pinned*) para el shell de un solo proyecto.

Orbit se usa en dos formas (ADR-049):

* **Panel general** — shell sin fijar, todo el workspace. Es el "dueño":
  lleva el doctor global, los daemons, la oferta de save y las vistas
  transversales (dash, panel, cal, focus...).
* **Panel de proyecto** — el shell que abre `wks <proyecto>` en su segunda
  ventana. Está *fijado* a un proyecto y sólo trabaja en él.

En el panel de proyecto:

1. El argumento posicional ``project`` **desaparece de la gramática** (lo
   inyecta :func:`core.parsers._helpers.add_project_arg` como default), de
   modo que ``log "texto"`` escribe en el proyecto fijado.
2. Nombrar otro proyecto es un **error explícito**, no un cambio de destino
   silencioso (:func:`check_foreign`).
3. Los comandos transversales están **bloqueados** (:data:`WORKSPACE_ONLY`);
   para ésos se va uno al panel general.

El fijado se hace al arrancar (``orbit shell --project X`` o la variable de
entorno ``ORBIT_PROJECT``) y es **inmutable** durante la sesión: no hay verbo
para cambiar de proyecto. Si quieres otro, abres otra ventana.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

# ── Estado del proceso ───────────────────────────────────────────────────────
#
# Un proceso = un shell = como mucho un proyecto fijado. No hay pila ni
# anidamiento: `clear()` existe sólo para los tests.

_pinned_name: Optional[str] = None
_pinned_dir: Optional[Path] = None


def pinned() -> Optional[str]:
    """Nombre canónico del proyecto fijado, o None si el shell es general."""
    return _pinned_name


def pinned_dir() -> Optional[Path]:
    """Directorio del proyecto fijado, o None."""
    return _pinned_dir


def clear() -> None:
    """Desfijar (sólo para tests y para el arranque del panel general)."""
    global _pinned_name, _pinned_dir
    _pinned_name = None
    _pinned_dir = None


# ── Resolución de nombres ────────────────────────────────────────────────────

def project_names() -> list:
    """Nombres canónicos (sin emoji de tipo) de todos los proyectos."""
    from core.config import iter_project_dirs
    from core.project import _is_new_project, _strip_type_emoji
    return sorted(_strip_type_emoji(d.name)
                  for d in iter_project_dirs() if _is_new_project(d))


def resolve(name: str) -> Optional[Path]:
    """Resolver un nombre de proyecto a su directorio, sin preguntar ni imprimir.

    A diferencia de :func:`core.project._find_new_project`, esta versión es
    silenciosa y no interactiva: se usa al arrancar el shell, donde no hay
    sitio para un menú de desambiguación. Exacto (con o sin emoji de tipo)
    gana sobre parcial; parcial ambiguo devuelve None.
    """
    from core.config import iter_project_dirs
    from core.project import _is_new_project, _strip_type_emoji

    if not name:
        return None
    low = name.lower()
    candidates = [d for d in iter_project_dirs() if _is_new_project(d)]

    exact = [d for d in candidates
             if d.name.lower() == low or _strip_type_emoji(d.name).lower() == low]
    if exact:
        return exact[0]

    partial = [d for d in candidates if low in d.name.lower()]
    return partial[0] if len(partial) == 1 else None


def pin(name: str) -> tuple:
    """Fijar el shell a un proyecto. Devuelve ``(ok, mensaje)``.

    No arranca nada ni imprime: el llamante decide qué hacer con el fallo.
    Fallar aquí debe abortar el arranque del shell — un panel de proyecto que
    no sabe en qué proyecto está no sirve para nada, y degradarlo a panel
    general en silencio invita a escribir en el sitio equivocado.
    """
    global _pinned_name, _pinned_dir
    from core.project import _strip_type_emoji

    d = resolve(name)
    if d is None:
        names = project_names()
        hint = ""
        if names:
            from difflib import get_close_matches
            close = get_close_matches(name.lower(), [n.lower() for n in names], n=3, cutoff=0.4)
            if close:
                hint = f" ¿Quisiste decir {', '.join(close)}?"
        return False, f"proyecto '{name}' no encontrado o ambiguo.{hint}"

    _pinned_dir = d
    _pinned_name = _strip_type_emoji(d.name)
    return True, _pinned_name


def pin_from_env() -> tuple:
    """Fijar desde ``ORBIT_PROJECT`` si está definida. Devuelve ``(ok, msg)``.

    ``(True, "")`` si la variable no está — no fijar no es un error.
    """
    name = os.environ.get("ORBIT_PROJECT", "").strip()
    if not name:
        return True, ""
    return pin(name)


# ── Comandos transversales: bloqueados en el panel de proyecto ───────────────
#
# Lista negra, no blanca: lo que no esté aquí queda permitido. Así un comando
# nuevo no nace bloqueado por olvido. Entradas de una palabra bloquean el
# comando entero; de dos, sólo ese subcomando.
#
# Criterio: se bloquea lo que *actúa* sobre el workspace entero o produce una
# vista transversal. Las lecturas inocuas (search, ls, history, report) no se
# bloquean — se acotan al proyecto fijado. `save`/`commit` tampoco: operan
# sobre el repositorio, no sobre un proyecto, y querer guardar sin cambiar de
# ventana es razonable.

WORKSPACE_ONLY = {
    ("dash",):               "vista de todo el workspace",
    ("panel",):              "vista de todo el workspace",
    ("cal",):                "calendario de todo el workspace",
    ("organize",):           "triaje de todo el workspace",
    ("reorganize",):         "triaje de todo el workspace",
    ("focus",):              "planificación de la misión, no de un proyecto",
    ("ring",):               "daemon de avisos del workspace",
    ("mail",):               "cartero del workspace",
    ("setup",):              "configuración del workspace",
    ("cloud", "sync"):       "sincroniza todo el workspace",
    ("cloud", "imgs"):       "procesa imágenes de todo el workspace",
    ("project", "create"):   "crear proyectos es cosa del panel general",
    ("project", "drop"):     "borrar proyectos es cosa del panel general",
    ("project", "type"):     "los tipos son del workspace",
    ("ls", "projects"):      "listado de todo el workspace",
}


def check_blocked(tokens: list) -> Optional[str]:
    """Mensaje de error si ``tokens`` es un comando transversal, o None.

    Se llama sobre argv ya normalizado (post ``_fix_argv``), para que
    ``add project`` y ``project add`` se bloqueen igual.
    """
    if not _pinned_name or not tokens:
        return None
    for key in ((tokens[0], tokens[1]) if len(tokens) > 1 else (),
                (tokens[0],)):
        if not key:
            continue
        reason = WORKSPACE_ONLY.get(tuple(key))
        if reason:
            cmd = " ".join(key)
            return (f"⚠️  `{cmd}` es un comando de workspace ({reason}).\n"
                    f"    Esta ventana está fijada en «{_pinned_name}» — "
                    f"usa el panel general.")
    return None


# ── Guardia contra proyectos ajenos ──────────────────────────────────────────

def check_foreign(tokens: list) -> Optional[str]:
    """Mensaje de error si el comando nombra otro proyecto, o None.

    Sin el argumento ``project`` en la gramática, un ``log otro "texto"``
    tecleado por inercia acabaría escribiendo *"otro"* como mensaje en el
    proyecto fijado: un fallo silencioso. Este guardia lo convierte en error.

    Sólo dispara con **coincidencia exacta** de un token suelto con el nombre
    de otro proyecto, así que un mensaje entrecomillado (un único token con
    espacios) nunca lo activa.
    """
    if not _pinned_name or len(tokens) < 2:
        return None
    others = {n.lower() for n in project_names()} - {_pinned_name.lower()}
    if not others:
        return None
    for tok in tokens[1:]:
        if tok.startswith("-"):
            continue
        if tok.lower() in others:
            return (f"⚠️  Esta ventana está fijada en «{_pinned_name}» y "
                    f"«{tok}» es otro proyecto.\n"
                    f"    Para trabajar en «{tok}», usa el panel general.\n"
                    f"    (Si «{tok}» era parte del texto, entrecomíllalo.)")
    return None


# ── Relleno de las formas que no son posicional `project` ───────────────────

# Comandos cuyo `--project` acepta lista (`nargs="+"`), no un nombre suelto.
_LIST_SHAPED = {"search"}


def apply_to_args(args) -> None:
    """Acotar al proyecto fijado los comandos con otra forma de argumento.

    El posicional ``project`` lo resuelve el parser (ver
    :func:`core.parsers._helpers.add_project_arg`). Aquí quedan las otras dos:

    * ``projects`` con ``nargs="*"`` — agenda, report, ls tasks, ls ms.
    * ``--project`` con ``nargs="+"`` — search.

    En ambas, vacío significa "todos los proyectos"; fijados, significa
    "el mío". De paso se apaga la federación: leer otros workspaces es justo
    lo contrario de lo que hace esta ventana.
    """
    if not _pinned_name:
        return
    cmd = getattr(args, "command", None)
    if hasattr(args, "projects") and not getattr(args, "projects"):
        args.projects = [_pinned_name]
    if hasattr(args, "project") and getattr(args, "project") is None:
        args.project = [_pinned_name] if cmd in _LIST_SHAPED else _pinned_name
    if hasattr(args, "no_fed"):
        args.no_fed = True

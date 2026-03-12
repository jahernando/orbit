"""claude.py — ask Claude about Orbit usage + error recovery suggestions.

  orbit claude "¿cómo creo una tarea recurrente?"

Sends the question to Claude with CHULETA.md as context and prints the answer.
Requires: pip install anthropic + ANTHROPIC_API_KEY env var.
"""

import os
import sys
from pathlib import Path

from core.config import ORBIT_CODE

_MODEL = "claude-haiku-4-5-20251001"
_MAX_TOKENS = 1024

_SYSTEM = """\
Eres el asistente integrado de Orbit, un CLI de gestión de proyectos personales.
Responde SOLO sobre cómo usar Orbit basándote en la referencia que se te proporciona.
Sé conciso y da ejemplos de comandos concretos cuando sea posible.
Si la pregunta no tiene que ver con Orbit, di que solo puedes ayudar con Orbit.
Responde en el mismo idioma que la pregunta."""

_SUGGEST_SYSTEM = """\
Eres el asistente integrado de Orbit, un CLI de gestión de proyectos personales.
El usuario ha escrito un comando que ha fallado. Basándote en la referencia, \
sugiere entre 1 y 4 comandos correctos que probablemente quería ejecutar.

Responde SOLO con un JSON array de objetos, sin texto adicional, sin markdown:
[{"cmd": "orbit task add proj \"desc\"", "desc": "Crear tarea en proyecto"}]

Cada objeto tiene "cmd" (comando completo) y "desc" (explicación breve, max 50 chars).
Si no puedes sugerir nada, responde con un array vacío: []"""


def _get_client():
    """Return (anthropic.Anthropic, chuleta_text) or (None, None)."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return None, None
    chuleta = ORBIT_CODE / "CHULETA.md"
    if not chuleta.exists():
        return None, None
    try:
        import anthropic
    except ImportError:
        return None, None
    return anthropic.Anthropic(api_key=api_key), chuleta.read_text()


def run_claude(question: str) -> int:
    """Send a question to Claude with CHULETA.md as context."""
    client, context = _get_client()
    if client is None:
        if not os.environ.get("ANTHROPIC_API_KEY"):
            print("Error: ANTHROPIC_API_KEY no está configurada.")
            print("  export ANTHROPIC_API_KEY='sk-ant-...'")
        else:
            print("Error: paquete 'anthropic' no instalado o CHULETA.md no encontrada.")
        return 1

    # Stream the response
    print()
    try:
        with client.messages.stream(
            model=_MODEL,
            max_tokens=_MAX_TOKENS,
            system=_SYSTEM,
            messages=[{
                "role": "user",
                "content": f"<referencia>\n{context}\n</referencia>\n\nPregunta: {question}",
            }],
        ) as stream:
            for text in stream.text_stream:
                sys.stdout.write(text)
                sys.stdout.flush()
        print("\n")
    except Exception as e:
        err = str(e)
        if "credit balance" in err.lower():
            print(f"\n⚠️  Sin créditos en la API. Recarga en: console.anthropic.com/settings/billing")
        else:
            print(f"\n⚠️  Error al contactar Claude: {err}")
        return 1
    return 0


def suggest_on_error(argv: list, error_msg: str) -> None:
    """Called when a command fails. Asks Claude for suggestions and lets user pick one.

    Only runs if: interactive TTY, API key set, anthropic installed.
    Returns the chosen command string, or None.
    """
    if not sys.stdin.isatty():
        return None

    client, context = _get_client()
    if client is None:
        return None

    cmd_str = " ".join(argv)

    try:
        response = client.messages.create(
            model=_MODEL,
            max_tokens=512,
            system=_SUGGEST_SYSTEM,
            messages=[{
                "role": "user",
                "content": (
                    f"<referencia>\n{context}\n</referencia>\n\n"
                    f"Comando fallido: orbit {cmd_str}\n"
                    f"Error: {error_msg}"
                ),
            }],
        )
    except Exception:
        return None

    # Parse JSON response
    import json
    raw = response.content[0].text.strip()
    try:
        suggestions = json.loads(raw)
    except (json.JSONDecodeError, IndexError):
        return None

    if not suggestions:
        return None

    print(f"\n  💡 ¿Quizás querías decir?")
    for i, s in enumerate(suggestions, 1):
        print(f"     [{i}] {s['cmd']}  — {s['desc']}")
    print(f"     [Enter] cancelar")

    try:
        ans = input("\n  Elige: ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return None

    if not ans or not ans.isdigit():
        return None
    idx = int(ans) - 1
    if 0 <= idx < len(suggestions):
        return suggestions[idx]["cmd"]
    return None

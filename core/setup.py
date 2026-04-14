"""orbit setup — interactive workspace configuration wizard."""

import json
from pathlib import Path

from core.config import ORBIT_HOME


_ORBIT_JSON = ORBIT_HOME / "orbit.json"
_FEDERATION_JSON = ORBIT_HOME / "federation.json"

_DEFAULT_TYPES = {
    "investigacion": "🌀",
    "docencia": "📚",
    "gestion": "⚙️",
    "formacion": "📖",
    "software": "💻",
    "personal": "🌿",
    "mision": "☀️",
}


def _load_existing() -> dict:
    """Load existing orbit.json or return empty dict."""
    if _ORBIT_JSON.exists():
        try:
            return json.loads(_ORBIT_JSON.read_text())
        except (json.JSONDecodeError, ValueError):
            return {}
    return {}


def _load_federation() -> list:
    """Load existing federation.json entries or return empty list."""
    if _FEDERATION_JSON.exists():
        try:
            return json.loads(_FEDERATION_JSON.read_text()).get("federated", [])
        except (json.JSONDecodeError, ValueError):
            return []
    return []


def _ask(prompt: str, default: str = "") -> str:
    """Ask user with optional default in brackets. Returns stripped answer or default."""
    suffix = f" [{default}]" if default else ""
    ans = input(f"   {prompt}{suffix}: ").strip()
    return ans if ans else default


def _ask_yn(prompt: str, default_yes: bool = False) -> bool:
    """Ask yes/no. Returns bool."""
    hint = "[S/n]" if default_yes else "[s/N]"
    ans = input(f"   {prompt} {hint}: ").strip().lower()
    if not ans:
        return default_yes
    return ans in ("s", "si", "sí", "y", "yes")


# ── Section 1: Workspace ──────────────────────────────────────────────────

def _setup_workspace(cfg: dict) -> dict:
    """Ask for emoji and space name."""
    print("\n1. Workspace")
    emoji = _ask("Emoji del workspace", cfg.get("emoji", "🚀"))
    space = _ask("Nombre del workspace", cfg.get("space", ORBIT_HOME.name))
    return {"emoji": emoji, "space": space}


# ── Section 2: Types ──────────────────────────────────────────────────────

def _setup_types(cfg: dict) -> dict:
    """Show current types, allow adding new ones."""
    print("\n2. Tipos de proyecto")
    types = cfg.get("types", _DEFAULT_TYPES).copy()
    parts = [f"{e}{n}" for n, e in types.items()]
    print(f"   Tipos actuales: {', '.join(parts)}")

    while True:
        ans = _ask("Añadir tipo (nombre emoji, o Enter para continuar)")
        if not ans:
            break
        parts = ans.rsplit(None, 1)
        if len(parts) == 2:
            name, emoji = parts[0].lower(), parts[1]
            types[name] = emoji
            print(f"   + {emoji}{name}")
        else:
            print("   ⚠️  Formato: nombre emoji (ej: hobby 🎮)")

    return {"types": types}


# ── Section 3: Editor ─────────────────────────────────────────────────────

def _setup_editor(cfg: dict) -> dict:
    """Ask for preferred editor."""
    print("\n3. Editor")
    current = cfg.get("editor", "")
    editor = _ask("Editor para `orbit open` (obsidian, code, typora...)", current)
    if editor:
        return {"editor": editor}
    return {}


# ── Section 4: Google Sync ────────────────────────────────────────────────

def _setup_gsync(cfg: dict) -> dict:
    """Check if user wants Google sync."""
    print("\n4. Google Sync")
    if not _ask_yn("¿Configurar sincronización con Google Calendar/Tasks?"):
        return {}

    creds = ORBIT_HOME / "credentials.json"
    if creds.exists():
        print("   ✅ credentials.json encontrado")
    else:
        print(f"   ⚠️  Necesitas credentials.json en {ORBIT_HOME}")
        print("      → Créalo en Google Cloud Console (Calendar + Tasks APIs)")
        print("      → Ejecuta `orbit gsync` para autorizar")
    return {}


# ── Section 5: Cartero Gmail ─────────────────────────────────────────────

def _setup_cartero_gmail(cfg: dict) -> dict:
    """Ask for Gmail notification labels."""
    print("\n5. Cartero — Gmail")
    cartero = cfg.get("cartero", {})
    gmail = cartero.get("gmail", {})

    if not _ask_yn("¿Configurar notificaciones de Gmail?"):
        return {}

    current_labels = gmail.get("labels", [])
    default_labels = ", ".join(current_labels) if current_labels else ""
    labels_str = _ask("Etiquetas a vigilar (separadas por coma)", default_labels)
    if not labels_str:
        return {}

    labels = [l.strip() for l in labels_str.split(",") if l.strip()]
    current_interval = gmail.get("interval", 600)
    interval_str = _ask("Intervalo en minutos", str(current_interval // 60))
    try:
        interval = int(interval_str) * 60
    except ValueError:
        interval = 600

    creds = ORBIT_HOME / "credentials.json"
    if not creds.exists():
        print(f"   ⚠️  Necesitas credentials.json en {ORBIT_HOME}")
        print("      → Mismas credenciales que Google Sync (añade API de Gmail)")

    return {"cartero_gmail": {"labels": labels, "interval": interval}}


# ── Section 6: Cartero Slack ──────────────────────────────────────────────

def _setup_cartero_slack(cfg: dict) -> dict:
    """Ask for Slack workspace(s) and channels."""
    print("\n6. Cartero — Slack")
    cartero = cfg.get("cartero", {})

    if not _ask_yn("¿Configurar notificaciones de Slack?"):
        return {}

    # Load existing slack config
    existing_slack = cartero.get("slack", [])
    if isinstance(existing_slack, dict):
        existing_slack = [existing_slack]

    workspaces = []
    for existing in existing_slack:
        ws_name = existing.get("workspace", "")
        channels = ", ".join(existing.get("channels", []))
        dms = existing.get("dms", False)
        print(f"   Existente: {ws_name} (canales: {channels}, DMs: {'sí' if dms else 'no'})")

    if existing_slack and not _ask_yn("¿Reconfigurar desde cero?"):
        return {"cartero_slack": existing_slack}

    while True:
        ws_name = _ask("Nombre del workspace Slack (o Enter para terminar)")
        if not ws_name:
            break
        channels_str = _ask("Canales (separados por coma)")
        channels = [c.strip() for c in channels_str.split(",") if c.strip()] if channels_str else []
        dms = _ask_yn("¿Incluir DMs?")

        ws_cfg = {"workspace": ws_name}
        if channels:
            ws_cfg["channels"] = channels
        if dms:
            ws_cfg["dms"] = True
        workspaces.append(ws_cfg)

        token_path = ORBIT_HOME / f".slack-token-{ws_name}"
        if not token_path.exists():
            print(f"   ⚠️  Crea {token_path.name} con tu user token (xoxp-...)")

        if not _ask_yn("¿Añadir otro workspace Slack?"):
            break

    if workspaces:
        return {"cartero_slack": workspaces}
    return {}


# ── Section 7: Federation ────────────────────────────────────────────────

def _setup_federation(existing_fed: list) -> list:
    """Ask for federated workspaces."""
    print("\n7. Federación")

    for entry in existing_fed:
        print(f"   Existente: {entry.get('emoji', '')} {entry.get('name', '')} → {entry.get('path', '')}")

    if not _ask_yn("¿Federar con otro workspace?"):
        return existing_fed

    federation = list(existing_fed)
    while True:
        path = _ask("Path del workspace (o Enter para terminar)")
        if not path:
            break
        expanded = str(Path(path).expanduser().resolve())
        if not Path(expanded).exists():
            print(f"   ⚠️  {expanded} no existe")
            if not _ask_yn("¿Añadir de todas formas?"):
                continue
        emoji = _ask("Emoji", "🌿")
        name = _ask("Nombre", Path(expanded).name)
        federation.append({"name": name, "path": path, "emoji": emoji})
        print(f"   + {emoji} {name} → {path}")

        if not _ask_yn("¿Añadir otro?"):
            break

    return federation


# ── Main ──────────────────────────────────────────────────────────────────

def run_setup() -> int:
    """Interactive workspace configuration wizard."""
    print("\n🔧 Orbit Setup — configuración del workspace")
    print("━" * 45)
    print(f"   Workspace: {ORBIT_HOME}")

    cfg = _load_existing()
    federation = _load_federation()

    try:
        # Collect answers from each section
        result = dict(cfg)  # start with existing config

        ws = _setup_workspace(cfg)
        result.update(ws)

        types = _setup_types(cfg)
        result.update(types)

        editor = _setup_editor(cfg)
        result.update(editor)

        _setup_gsync(cfg)

        gmail_result = _setup_cartero_gmail(cfg)
        slack_result = _setup_cartero_slack(cfg)

        # Merge cartero config
        if gmail_result or slack_result:
            cartero = result.get("cartero", {})
            if "cartero_gmail" in gmail_result:
                cartero["gmail"] = gmail_result["cartero_gmail"]
            if "cartero_slack" in slack_result:
                cartero["slack"] = slack_result["cartero_slack"]
            result["cartero"] = cartero

        federation = _setup_federation(federation)

    except (EOFError, KeyboardInterrupt):
        print("\n\n   Cancelado.")
        return 1

    # Write orbit.json
    _ORBIT_JSON.write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n"
    )
    print(f"\n✅ Configuración guardada en {_ORBIT_JSON.name}")

    # Write federation.json if needed
    if federation:
        _FEDERATION_JSON.write_text(
            json.dumps({"federated": federation}, indent=2, ensure_ascii=False) + "\n"
        )
        print(f"✅ Federación guardada en {_FEDERATION_JSON.name}")

    return 0

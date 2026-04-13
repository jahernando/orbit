# Cartero — Notificaciones de correo y mensajería para Orbit

> Diseño v0.1 — 2026-04-13

## Visión

El cartero es una capa de notificaciones sobre orbit. **No es un cliente de correo** — solo avisa de que hay mensajes nuevos. Para leerlos, el usuario va a la aplicación correspondiente (Gmail, Outlook, Slack).

Funciona en dos niveles:
1. **Indicador en el prompt** — `📬3` visible mientras se trabaja en la shell
2. **Notificación macOS** — aviso cuando llegan mensajes nuevos (como ring)

## Fases

| Fase | Workspace | Fuentes | Estado |
|------|-----------|---------|--------|
| 1 | orbit-ps (🌿) | Gmail (etiquetas filtradas) | ← este documento |
| 2 | orbit-ws (🚀) | Outlook + Slack + federado (Gmail de 🌿) | pendiente |

---

## Fase 1 — Gmail en orbit-ps

### Vista de usuario

#### Configuración

El usuario añade una sección `cartero` en `orbit.json` del workspace:

```json
{
  "space": "orbit-ps",
  "emoji": "🌿",
  "cartero": {
    "gmail": {
      "labels": ["Importante", "Familia", "Universidad"],
      "interval": 600
    }
  }
}
```

- **`labels`** — lista de etiquetas de Gmail a vigilar. Solo se cuentan correos no leídos que tengan *alguna* de estas etiquetas. Si la lista está vacía o no se especifica, el cartero no se activa.
- **`interval`** — segundos entre checks (default: `600` = 10 minutos).

#### Credenciales

El cartero reutiliza la infraestructura OAuth de gsync:

- `credentials.json` — mismo fichero de Google Cloud Console (ya existe si usa gsync)
- `token.json` — se le añade el scope `gmail.readonly`

Si el usuario ya tiene gsync configurado, al activar el cartero se le pedirá re-autenticar una sola vez para aceptar el nuevo scope de Gmail. A partir de ahí, el token se refresca automáticamente.

Si el usuario no tiene gsync, necesita:
1. Crear un proyecto en Google Cloud Console (o usar el existente)
2. Habilitar la API de Gmail
3. Descargar `credentials.json` al workspace
4. Ejecutar `orbit mail` para iniciar el flujo OAuth

#### Comandos

```
orbit mail              # check manual: muestra conteo por etiqueta
orbit mail --status     # estado del proceso background (corriendo/parado, último check)
orbit mail --stop       # para el proceso background
orbit mail --start      # arranca el proceso background manualmente
```

Ejemplo de `orbit mail`:
```
📬 Correos no leídos:
  Importante    3
  Familia       1
  Universidad   0
  ─────────────
  Total         4

Último check: hace 2 min
```

#### Prompt

Cuando hay correos nuevos, el prompt muestra un indicador:

```
🌿[📬4] > _          ← 4 correos no leídos con las etiquetas configuradas
🌿 > _                ← sin correos (sin ruido)
```

El número es el total de no leídos en las etiquetas configuradas.

#### Notificación macOS

Cuando el cartero detecta correos **nuevos** (que no estaban en el check anterior), lanza una notificación nativa:

```
📬 4 correos nuevos
Importante (3), Familia (1)
```

Si no hay correos nuevos desde el último check, no notifica (evita spam).

### Startup y shutdown

**Al arrancar la shell (`orbit shell`):**
1. Si hay config de cartero en `orbit.json`:
   - Comprueba si ya hay un proceso cartero corriendo (lock file)
   - Si no hay → lanza uno en background
   - Muestra estado: `📬 Cartero activo (3 correos pendientes)` o `📬 Cartero activo (sin correos)`
2. Si no hay config → no hace nada (silencioso)

**Al cerrar la shell (`end` / `exit`):**
- El proceso background sigue corriendo (es independiente de la shell)
- Se para solo con `orbit mail --stop` o al apagar el sistema

### Proceso background y shell múltiple

Dado que el usuario puede abrir múltiples shells de orbit simultáneamente, el cartero usa un **proceso único por workspace con lock file**:

```
ORBIT_HOME/.cartero.pid              ← PID del proceso background
ORBIT_HOME/.cartero-state.json       ← estado compartido (último check, conteos)
```

Estos ficheros viven en el workspace (e.g. `~/🌿orbit-ps/.cartero.pid`), junto al resto de estado runtime (`token.json`, `.gsync-ids.json`, `.last_ring`). Se añaden al `.gitignore` del workspace.

**Mecanismo:**

1. Al lanzar el background, escribe su PID en `ORBIT_HOME/.cartero.pid`
2. Antes de lanzar, cualquier shell comprueba:
   - ¿Existe `.cartero.pid`?
   - ¿El PID que contiene sigue vivo? (`os.kill(pid, 0)`)
   - Si vive → no lanza otro
   - Si no existe o murió → borra el fichero y lanza uno nuevo
3. El proceso background escribe resultados en `ORBIT_HOME/.cartero-state.json`
4. Todas las shells del mismo workspace leen ese fichero para renderizar el prompt
5. Al morir el proceso (kill, reboot), el lock queda stale y la siguiente shell lo limpia

**¿Por qué en `ORBIT_HOME` y no en `$HOME`?**

- **Consistencia** — el workspace ya tiene estado runtime (`token.json`, `.gsync-ids.json`, `.last_ring`)
- **No contamina `$HOME`** — que ya está lleno de dotfiles
- **Cada workspace es dueño de su cartero** — orbit-ps vigila Gmail, orbit-ws vigilará Outlook+Slack. Cada uno tiene su proceso y su estado.
- **Federación limpia** — orbit-ws lee `~/🌿orbit-ps/.cartero-state.json` para el buzón federado, exactamente como ya hace ring con `iter_federated_project_dirs()`.

---

## Arquitectura interna (Fase 1)

### Ficheros nuevos

```
core/cartero.py             ← módulo principal
tests/test_cartero.py       ← tests
```

### Estructura de `core/cartero.py`

```python
# ── Constantes ──────────────────────────────────────────────────────────────
CARTERO_PID   = ORBIT_HOME / ".cartero.pid"
CARTERO_STATE = ORBIT_HOME / ".cartero-state.json"
DEFAULT_INTERVAL = 600  # 10 minutos

GMAIL_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"

# ── API de Gmail ────────────────────────────────────────────────────────────

def _get_gmail_service():
    """Construir servicio Gmail usando credenciales OAuth del workspace.
    
    Reutiliza credentials.json y token.json de ORBIT_HOME.
    Si el token no tiene el scope de Gmail, pide re-autenticación.
    Retorna: servicio gmail v1, o None si no hay credenciales.
    """

def _resolve_label_ids(service, label_names: list[str]) -> dict[str, str]:
    """Mapear nombres de etiqueta a label IDs de Gmail.
    
    Gmail usa IDs internos (Label_XXXX) para etiquetas custom.
    Llama a users.labels.list, matchea por nombre (case-insensitive).
    Retorna: {nombre: label_id}
    Cachea en .cartero-state.json para evitar llamada repetida.
    """

def _check_gmail(service, label_ids: dict[str, str]) -> dict:
    """Contar correos no leídos por etiqueta.
    
    Para cada label_id:
      messages.list(userId="me", labelIds=[label_id, "UNREAD"], maxResults=0)
      → resultSizeEstimate da el conteo
    
    Retorna: {"counts": {"Importante": 3, "Familia": 1}, "total": 4, "timestamp": "..."}
    """

# ── Estado compartido ──────────────────────────────────────────────────────

def _read_state() -> dict:
    """Leer .cartero-state.json. Retorna {} si no existe."""

def _write_state(state: dict):
    """Escribir .cartero-state.json atómicamente (write to tmp + rename)."""

def get_prompt_indicator() -> str:
    """Leer estado y devolver string para el prompt.
    
    Si total > 0 → "[📬4]"
    Si total == 0 o no hay estado → ""
    Lectura de fichero, sin I/O de red — instantáneo.
    """

# ── Proceso background ─────────────────────────────────────────────────────

def _is_running() -> bool:
    """Comprobar si hay un proceso cartero vivo (via .cartero.pid)."""

def _start_background(config: dict):
    """Lanzar proceso background como daemon.
    
    1. Fork (doble fork para desligarse de la terminal)
    2. Escribir PID en .cartero.pid
    3. Loop:
       a. Leer config de cartero desde orbit.json
       b. _check_gmail() 
       c. _write_state() con resultados
       d. Si hay correos NUEVOS (delta vs anterior) → _notify_macos()
       e. sleep(interval)
    4. Al recibir SIGTERM → borrar .cartero.pid, salir limpiamente
    """

def _stop_background():
    """Enviar SIGTERM al proceso background, borrar .cartero.pid."""

# ── Notificaciones macOS ───────────────────────────────────────────────────

def _notify_macos(title: str, body: str):
    """Notificación nativa vía osascript (como ring).
    
    osascript -e 'display notification "body" with title "title"'
    """

# ── Comando `orbit mail` ───────────────────────────────────────────────────

def run_mail(args):
    """Dispatcher del comando mail.
    
    --status → mostrar estado del background
    --stop   → parar background
    --start  → arrancar background
    (sin args) → check síncrono + mostrar conteos por etiqueta
    """

# ── Integración con shell ──────────────────────────────────────────────────

def startup_cartero():
    """Llamado desde shell.py:_run_startup().
    
    1. Leer cartero config de orbit.json
    2. Si no hay config → return silenciosamente
    3. Si hay config y no hay proceso corriendo → lanzar background
    4. Mostrar último estado conocido
    """
```

### Flujo del proceso background (diagrama)

```
┌─────────────────────────────────────────────────────┐
│                  Proceso background                  │
│                                                      │
│  ┌──────────┐    ┌──────────────┐    ┌───────────┐  │
│  │  sleep    │───▶│  check_gmail │───▶│  write    │  │
│  │ interval  │    │  (API call)  │    │  state    │  │
│  └──────────┘    └──────────────┘    └─────┬─────┘  │
│       ▲                                     │        │
│       │            ┌──────────────┐         │        │
│       └────────────│  ¿hay nuevos?│◀────────┘        │
│                    └──────┬───────┘                   │
│                      sí   │   no                     │
│                    ┌──────▼──────┐                    │
│                    │notify_macos │                    │
│                    └─────────────┘                    │
└─────────────────────────────────────────────────────┘

         │ escribe                         
         ▼                                
┌──────────────────────────────────────┐
│ ORBIT_HOME/.cartero-state.json       │
└──────────────────────────────────────┘
         ▲                        ▲
         │ lee                    │ lee
┌────────┴────────┐      ┌───────┴─────────┐
│   Shell 1       │      │   Shell 2       │
│  🌿[📬4] > _   │      │  🌿[📬4] > _   │
└─────────────────┘      └─────────────────┘
```

### `.cartero-state.json` — formato

```json
{
  "gmail": {
    "counts": {
      "Importante": 3,
      "Familia": 1,
      "Universidad": 0
    },
    "total": 4,
    "new_since_last": 2,
    "last_check": "2026-04-13T10:30:00",
    "label_ids": {
      "Importante": "Label_1234",
      "Familia": "Label_5678",
      "Universidad": "IMPORTANT"
    }
  },
  "pid": 12345,
  "started": "2026-04-13T08:00:00",
  "workspace": "orbit-ps"
}
```

### Detección de "correos nuevos" (para notificación)

El cartero no notifica si simplemente hay correos no leídos — eso sería spam. Solo notifica cuando el **conteo sube** respecto al check anterior:

```
Check 1: total = 3  →  (primer check, no notifica)
Check 2: total = 5  →  notifica "📬 2 correos nuevos"  (delta = +2)
Check 3: total = 5  →  no notifica (sin cambio)
Check 4: total = 2  →  no notifica (bajó, el usuario leyó correos)
Check 5: total = 4  →  notifica "📬 2 correos nuevos"  (delta = +2)
```

### Integración con el prompt

En `core/shell.py`, el prompt actualmente es:

```python
line = input(f"{ORBIT_PROMPT} ").strip()
```

Se modifica a:

```python
from core.cartero import get_prompt_indicator
indicator = get_prompt_indicator()
prompt = f"{ORBIT_PROMPT}{indicator} " if indicator else f"{ORBIT_PROMPT} "
line = input(prompt).strip()
```

`get_prompt_indicator()` solo lee `ORBIT_HOME/.cartero-state.json` — es una lectura de fichero local, sin latencia perceptible.

### OAuth: gestión de scopes

El scope de Gmail (`gmail.readonly`) se añade a los scopes existentes de gsync en `calendar_sync.py`:

```python
SCOPES = [
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/tasks",
    "https://www.googleapis.com/auth/gmail.readonly",  # ← nuevo
]
```

**Si el usuario ya tiene token.json:**
- Al iniciar el cartero, se detecta que el token no tiene el scope de Gmail
- Se pide re-autenticación (navegador se abre, el usuario acepta)
- Se sobreescribe token.json con los scopes expandidos
- Proceso transparente y una sola vez

**Si el usuario no tiene gsync:**
- El cartero funciona independientemente — solo necesita `credentials.json` y el scope de Gmail
- El flujo OAuth es el mismo que gsync pero con scope reducido

### Gestión de errores

| Error | Comportamiento |
|-------|----------------|
| Sin `credentials.json` | `orbit mail` muestra instrucciones de setup |
| Token expirado / revocado | Re-autenticación automática en siguiente check |
| API de Gmail no habilitada | Mensaje claro: "Habilita la API de Gmail en Google Cloud Console" |
| Etiqueta no encontrada | Warning al arrancar: "⚠️ Etiqueta 'XXX' no encontrada en Gmail" |
| Sin red / timeout | El check falla silenciosamente, mantiene último estado, reintenta en siguiente ciclo |
| Proceso background muere | Siguiente shell que arranque lo detecta y lanza uno nuevo |

---

## Fase 2 — Outlook + Slack en orbit-ws (preview)

> Detalle pendiente. Resumen de cómo se extenderá la arquitectura.

### Configuración en orbit-ws

```json
{
  "space": "orbit-ws",
  "emoji": "🚀",
  "cartero": {
    "outlook": {
      "interval": 600
    },
    "slack": {
      "channels": ["general", "proyecto-x", "alertas"],
      "interval": 600
    }
  }
}
```

### Federación del buzón

`orbit-ws` tiene `federation.json` apuntando a `orbit-ps`. El cartero de orbit-ws:

1. Hace polling de sus fuentes propias (Outlook, Slack)
2. Lee el `.cartero-state.json` del workspace federado (`~/🌿orbit-ps/.cartero-state.json`)
3. Combina todo para prompt y notificaciones

**No hace polling de Gmail** — eso lo hace el proceso de orbit-ps. Solo lee su fichero de estado.

### Prompt federado

```
🚀[📬2 🌿📬3] > _
```

- `📬2` — correos de Outlook / mensajes de Slack (locales)
- `🌿📬3` — correos de Gmail (federado de orbit-ps)

### Notificación federada

```
📬 2 Outlook, 5 Slack, 3 Gmail 🌿
```

### APIs

- **Outlook**: Microsoft Graph API (`Mail.Read` scope), OAuth2 via MSAL
- **Slack**: Slack API (`conversations.history`), bot/user token

---

## Ficheros afectados (Fase 1)

| Fichero | Cambio |
|---------|--------|
| `core/cartero.py` | **Nuevo** — módulo completo |
| `core/shell.py` | Añadir `startup_cartero()` en `_run_startup()`, modificar prompt |
| `core/config.py` | Leer sección `cartero` de `orbit.json` (opcional) |
| `core/calendar_sync.py` | Añadir scope `gmail.readonly` a SCOPES |
| `orbit.py` | Registrar comando `mail` y dispatcher |
| `tests/test_cartero.py` | **Nuevo** — tests del módulo |
| `CHULETA.md` | Documentar comando `mail` y config |
| `README.md` | Mención en features |

---

## Consideraciones

- **Rate limits**: Gmail permite ~250 quota units/seg. `messages.list` cuesta 5 unidades. A 6 checks/hora estamos a años luz del límite.
- **Privacidad**: el cartero solo almacena conteos y nombres de etiquetas — nunca asuntos ni cuerpos de correo.
- **Batería**: el proceso background duerme 10 min entre checks — impacto negligible.
- **Testabilidad**: toda la lógica de estado/prompt/detección de nuevos es pura (sin I/O), fácilmente testable. Las llamadas a la API se mockean en tests.

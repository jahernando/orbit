# DEPENDENCIES.md

Inventario completo de las dependencias externas de orbit. Útil para:
- Estimar la portabilidad a otro sistema operativo.
- Saber qué se rompe si una dependencia desaparece.
- Identificar qué se puede simplificar.

Última auditoría: 2026-05-13 (v0.33).

---

## 1. Sistema operativo

**Soportado**: macOS (probado en Darwin 25.x). Mac is the primary target.
**Parcialmente portable**: Linux funciona para todo *excepto* el sync con Calendar.app/Mail.app/Reminders.app (ya dormante en v0.33 → en Linux no se pierde nada). Habría que reemplazar `pbcopy`/`pbpaste` por `xclip` o `xsel`.
**No portable** sin trabajo: Windows. PowerShell no tiene equivalentes directos para los AppleScripts y los paths con emojis pueden dar problemas.

---

## 2. CLI del sistema

| Comando | Uso | Bloqueante si falta |
|---------|-----|---------------------|
| `git` | versionado, `orbit commit`, `orbit_push` | **Sí** — orbit no funciona sin git |
| `pbcopy` / `pbpaste` | portapapeles (`orbit clip`, `orbit ics-share`, `orbit ics-import --clipboard`) | No — funciona sin ello, solo se pierde la copia/pega automática |
| `osascript` | AppleScript a Calendar.app (reload), Mail.app (captura email), Outlook (captura email) | Parcial — sin esto, el `reload calendars` no se dispara (esperarías el refresh automático ≤5 min), y la captura de email queda solo en backend `.eml` |
| `python` | intérprete (3.9+) | **Sí** — orbit es Python puro |
| `cat`, `ls`, `find`, `grep` | usados internamente vía subprocess en sitios menores | No — sustituibles |

---

## 3. Paquetes Python externos

Auditoría de `grep -hE "^(import|from)"` sobre `core/*.py` + `orbit.py`, filtrando stdlib.

### Realmente externos (pip-installed)

| Paquete | Usado en | Para qué | Sustituible |
|---------|---------|----------|-------------|
| `markdown` | `core/render.py` | conversión MD → HTML | No fácilmente — es el motor del cloud render |

**Sí, eso es todo para orbit core.** Solo una dependencia externa. El resto son stdlib.

### Externos usados por subsistemas opcionales

| Paquete | Subsistema | Usado en | Necesario para |
|---------|-----------|----------|----------------|
| `googleapiclient` | cartero (mail/Slack notifier, separado de orbit core) | `core/cartero.py`, `core/calendar_sync.py` | Captura Gmail vía API |
| `google-auth-oauthlib` | cartero | idem | OAuth flow para Gmail |
| `slack_sdk` | cartero | `core/cartero.py` | Notificaciones Slack |

Estos solo son necesarios si activas cartero (`orbit mail` en background). Orbit funciona sin ellos.

### Stdlib usada (no instalar, viene con Python)

`argparse`, `base64`, `calendar`, `collections`, `contextlib`, `datetime`, `email`, `email.policy`, `email.utils`, `hashlib`, `html`, `html.parser`, `io`, `json`, `logging`, `os`, `pathlib`, `platform`, `re`, `readline`, `secrets`, `shlex`, `shutil`, `signal`, `subprocess`, `sys`, `tempfile`, `threading`, `time`, `typing`, `unicodedata`, `urllib`, `uuid`, `xml.etree.ElementTree`.

---

## 4. Aplicaciones de macOS (no-pythonic)

| App | Uso por orbit | Estado v0.33 | Notas |
|-----|--------------|--------------|-------|
| **Calendar.app** | Suscriptor de los `.ics` que emite orbit. Read-only por construcción. AppleScript `reload calendars` opcional. | **Activo** (rol único: subscriber) | Anteriormente era target de AppleScript-write; ese camino quedó dormante en v0.33. |
| **Apple Mail** | Captura de email vía AppleScript en `orbit email <proj>` con `email_source: "mail"` en orbit.json. | **Activo** | Backend principal en orbit-ps. |
| **Outlook** | Captura de email vía AppleScript con `email_source: "outlook"`. | **Parcialmente roto** desde Outlook 16.108. Backend principal en orbit-ws. | Issue documentado en memoria `project_email_capture`. |
| **Reminders.app** | Era backend para tareas/ms/rem hasta v0.29. | **Dormante** desde v0.29 (movido a Calendar.app events) y desde v0.33 (movido a `.ics`). | Ver `DORMANT.md`. |
| **Obsidian** | Editor de markdown preferido. Configurable en `orbit.json:editor`. | **Activo** | Fallback al editor del sistema si no está. |
| **iCloud Calendar** | Propagación de subscripciones de Calendar.app a iPhone/iPad. | **Activo** (canal, no servicio que orbit toque) | Apple removió "iCloud" del diálogo macOS Calendar.app ~2023; el usuario debe suscribir vía `icloud.com/calendar` web. |

---

## 5. Servicios cloud externos

| Servicio | Uso por orbit | Tipo de acceso |
|----------|--------------|----------------|
| **OneDrive (USC, `nubeusc-my.sharepoint.com`)** | `cloud_root` de orbit-ws. Hosting de `.ics` para subscripción Calendar.app. | **Filesystem mount** (sync client local) + URLs públicas anonymous-share. **Ninguna API**. |
| **Google Drive (personal)** | `cloud_root` de orbit-ps. Hosting de `.ics`. | Filesystem mount + URLs públicas. Ninguna API. |
| **GitHub** | Hosting de los repos privados de cada workspace. | git push/pull. Sin API. |
| **Google Tasks / Google Calendar API** | (Histórico) sync vía Google API en pre-v0.29. | **Dormante desde v0.29**, código unreachable en `core/gsync.py`. |

**Importante**: orbit no llama ninguna API REST/Google/etc. en su flujo normal. Las dependencias cloud son **filesystem-only** (los clientes de OneDrive/Drive hacen el sync). Esto es deliberado — minimiza dependencias de red y autenticación.

---

## 6. Herramientas auxiliares (no requeridas por orbit pero relacionadas)

| Tool | Repo | Función |
|------|------|---------|
| `ws` / `wks` (shell function) | `~/work/scripts/ws` | Lanzador de workspaces + gestor de `workspaces.json`. Memoria: `reference_ws_script`. |
| `ws-label.py` | `label/ws-label.py` | Etiquetas flotantes de macOS Spaces. Memoria: `project_ws_label`. |
| `cartero` (subsistema interno de orbit) | `core/cartero.py` | Notificador de mail/Slack en background. Requiere `googleapiclient` y/o `slack_sdk`. |

---

## 7. Mínimo viable para arrancar orbit en una máquina nueva

Lo absolutamente necesario para usar orbit sin cartero ni sync de calendarios:

```bash
# Sistema
brew install python git    # macOS
# python ≥ 3.9

# Python deps
pip install markdown

# Clonar orbit
git clone https://github.com/jahernando/orbit ~/orbit
# Clonar el workspace
git clone <tu-repo-privado> ~/🚀tu-workspace
```

`pbcopy`/`pbpaste` vienen con macOS por defecto. AppleScript también.

Para añadir cartero (email notifier):
```bash
pip install google-api-python-client google-auth-oauthlib slack_sdk
# + credentials.json para Gmail OAuth
```

Para añadir subscripción .ics a Calendar.app:
- Tener el `cloud_root` configurado en `orbit.json`
- Configurar `ics_buckets` en `calendar-sync.json`
- Compartir los `.ics` con URL pública (OneDrive Anyone-with-link + `&download=1`, o equivalente)
- Suscribir en Calendar.app vía `webcal://...`

---

## 8. Lo que se eliminó en v0.33 (no usar)

- `core/gimport.py` — borrado físico, era reverse-sync experimental nunca lanzado.
- `orbit gsync --migrate-recurring` y `--migrate-rem-to-calendar` — comandos one-shot ya completados, eliminados del CLI.
- `core/gsync.py` y `core/calsync.py` — **dormantes pero todavía en el repo**. Programados para borrarse el 2026-05-27 si no surge necesidad de reactivar (ver `DORMANT.md`).

---

## Cómo mantener este fichero

Cuando se añada/quite una dependencia externa:

1. Editar la sección correspondiente arriba.
2. Si se añade un paquete Python externo nuevo: actualizar el `pip install` de "mínimo viable".
3. Si se rompe una integración con app de macOS: anotarlo en la columna "Estado".
4. Cuando algo pase a `DORMANT.md`, moverlo a la sección "lo que se eliminó".

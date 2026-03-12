# Orbit — Setup

Guia para configurar Orbit en tu maquina.

---

## Arquitectura

Orbit separa codigo y datos en repositorios distintos:

```
~/orbit/              ← repo publico, solo codigo (git pull para actualizar)
  orbit.py
  core/
  📐templates/

~/mi-workspace/       ← repo privado, tus proyectos y configuracion
  {emoji}proyectos/
  orbit.json          ← emoji y tipos de proyecto
  google-sync.json    ← calendarios de Google por tipo
  credentials.json    ← credenciales Google API (gitignored)
  history.md
```

Puedes tener tantos workspaces como quieras. Todos comparten el mismo codigo.
Cada workspace tiene su propia configuracion, sus propios proyectos y su propio
repositorio git (privado).

---

## 1. Instalar el codigo

```bash
git clone https://github.com/jahernando/orbit.git ~/orbit
```

Para actualizar el codigo en el futuro:

```bash
cd ~/orbit && git pull
```

Al iniciar la shell, Orbit comprueba automaticamente si hay actualizaciones.

---

## 2. Crear un workspace

```bash
mkdir ~/mi-workspace
cd ~/mi-workspace
git init
git config core.quotePath false
git config core.precomposeunicode false
```

Si quieres respaldo en un repo privado de GitHub:

```bash
# Crea primero el repo en GitHub (privado)
git remote add origin https://github.com/TU_USUARIO/mi-workspace.git
git push -u origin main
```

---

## 3. Shell — entry point

Crea un fichero `~/orbit/orbit.sh` con tus funciones de entrada:

```zsh
# orbit.sh — funciones shell para Orbit
# Sourcear desde ~/.zshrc

export ORBIT_EDITOR=typora

ORBIT_CODE="$HOME/orbit"

# Un entry point por workspace
worbit() {
    if [ "$1" = "claude" ]; then
        cd "$HOME/mi-workspace" && claude
    elif [ $# -eq 0 ]; then
        ORBIT_HOME="$HOME/mi-workspace" python3 "$ORBIT_CODE/orbit.py" shell
    else
        ORBIT_HOME="$HOME/mi-workspace" python3 "$ORBIT_CODE/orbit.py" "$@"
    fi
}

# Puedes anadir mas entry points para otros workspaces:
# porbit() { ... ORBIT_HOME="$HOME/otro-workspace" ... }
```

Luego anade a tu `~/.zshrc`:

```zsh
source ~/orbit/orbit.sh
```

Recarga con `source ~/.zshrc` y ejecuta `worbit` para entrar en la shell.

> `orbit.sh` esta en `.gitignore` — es tu configuracion local, no se sube al repo.

---

## 4. Configuracion del workspace

Todos estos ficheros viven en el workspace, no en el codigo.

### orbit.json — tipos de proyecto

Define el emoji principal y los tipos de proyecto del workspace. Se crea
automaticamente con valores por defecto al ejecutar `orbit project create`.

```json
{
  "emoji": "🚀",
  "types": {
    "investigacion": "🌀",
    "docencia": "📚",
    "gestion": "⚙️",
    "software": "💻",
    "personal": "🌿",
    "mision": "☀️"
  }
}
```

- `emoji` — emoji del directorio de proyectos (`{emoji}proyectos/`) y del prompt
- `types` — mapa tipo → emoji (puedes anadir, quitar o renombrar)

Cada workspace puede tener tipos distintos. Por ejemplo, un workspace de trabajo
podria usar 🚀 con tipos profesionales, y uno personal 🌿 con tipos de ocio.

### google-sync.json — sincronizacion con Google

Configura a que calendario de Google va cada tipo de proyecto.

```json
{
  "calendars": {
    "investigacion": "ID_DEL_CALENDARIO",
    "docencia": "ID_DEL_CALENDARIO",
    "default": "ID_DEL_CALENDARIO"
  },
  "task_lists": {},
  "repo_url": "https://github.com/TU_USUARIO/mi-workspace/blob/main"
}
```

- `calendars` — mapa tipo → ID de Google Calendar (usa `orbit gsync --list-calendars` para ver IDs)
- `task_lists` — se llenan automaticamente al sincronizar por primera vez
- `repo_url` — (opcional) URL base del repo para enlaces en las descripciones de Google

Cada workspace puede sincronizar a calendarios distintos.

### credentials.json / token.json — Google API

Necesarios para `orbit gsync`. Se comparten entre workspaces:

1. Crea un proyecto en [Google Cloud Console](https://console.cloud.google.com/)
2. Habilita las APIs de **Google Calendar** y **Google Tasks**
3. Crea credenciales: **APIs & Services → Credentials → + CREATE CREDENTIALS → OAuth client ID**
4. Application type: **Desktop app** — dale un nombre y haz clic en **CREATE**
5. Descarga el JSON y copialo al workspace:
   ```bash
   cp ~/Downloads/client_secret_*.json ~/mi-workspace/credentials.json
   ```
6. Ejecuta `worbit gsync` — se abrira el navegador para autorizar y generara `token.json`

Para otros workspaces, copia el mismo `credentials.json` y ejecuta gsync de nuevo.

> Ambos ficheros estan en `.gitignore` — nunca se suben al repo.

### ORBIT_EDITOR — editor de markdown

El editor que se abre con `orbit open`. Se configura en `orbit.sh`:

```bash
export ORBIT_EDITOR=typora    # o code, glow, etc.
```

Editores con soporte integrado: `typora`, `glow`, `code`. Cualquier otro se ejecuta directamente.
Si no se configura, usa `open` (macOS) o `xdg-open` (Linux).

### ~/.config/deliver.conf — entrega de ficheros a la nube

El comando `deliver` copia ficheros de un proyecto al directorio en la nube
(OneDrive, Google Drive, etc.). Configuralo en `~/.config/deliver.conf`:

```
~/mi-workspace=/ruta/a/OneDrive/mi-workspace
~/otro-workspace=/ruta/a/GoogleDrive/otro-workspace
```

Uso:

```bash
deliver proyecto fichero [fichero...]    # copia preservando estructura
deliver proyecto notes/results.pdf       # → cloud/🌀proyectos/🌀proyecto/notes/results.pdf
deliver --list                           # muestra el mapeo configurado
```

El comando vive en `~/orbit/bin/` y se anade al PATH automaticamente via `orbit.sh`.
Funciona tanto desde el REPL de Orbit como desde la terminal.

### ANTHROPIC_API_KEY — integracion con Claude

Para usar `orbit claude` (asistente IA dentro de la shell):

```bash
export ANTHROPIC_API_KEY='sk-ant-...'
```

Anadelo a `~/.zshrc`. Requiere `pip install anthropic`.

---

## 5. Dependencias

**Requerido:** Python >= 3.9 (sin dependencias externas para uso basico)

**Opcional:**

```bash
# Google Calendar/Tasks sync
pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib

# Claude AI integration
pip install anthropic
```

---

## 6. Ejemplo completo

```bash
# 1. Codigo
git clone https://github.com/jahernando/orbit.git ~/orbit

# 2. Workspace de trabajo
mkdir ~/orbit-ws && cd ~/orbit-ws
git init && git config core.quotePath false && git config core.precomposeunicode false

# 3. orbit.sh (editar con tus paths)
cat > ~/orbit/orbit.sh << 'EOF'
export ORBIT_EDITOR=typora
ORBIT_CODE="$HOME/orbit"
worbit() {
    if [ "$1" = "claude" ]; then cd "$HOME/orbit-ws" && claude
    elif [ $# -eq 0 ]; then ORBIT_HOME="$HOME/orbit-ws" python3 "$ORBIT_CODE/orbit.py" shell
    else ORBIT_HOME="$HOME/orbit-ws" python3 "$ORBIT_CODE/orbit.py" "$@"; fi
}
EOF

# 4. Activar
echo 'source ~/orbit/orbit.sh' >> ~/.zshrc
source ~/.zshrc

# 5. Primer uso
worbit
```

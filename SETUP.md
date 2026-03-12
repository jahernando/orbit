# Orbit — Setup

Guia para configurar Orbit en tu maquina.

---

## Arquitectura

Orbit separa codigo y datos en repositorios distintos:

```
~/orbit/          ← repo publico, solo codigo (git pull para actualizar)
  orbit.py
  core/
  📐templates/

~/orbit-ws/       ← repo privado, solo datos de trabajo
  🚀proyectos/
  orbit.json
  history.md

~/orbit-ps/       ← repo privado, solo datos personales
  🌿proyectos/
  orbit.json
  history.md
```

Puedes tener tantos workspaces como quieras. Todos comparten el mismo codigo.

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
```

Si quieres respaldo en un repo privado:

```bash
git remote add origin https://github.com/TU_USUARIO/mi-workspace.git
git push -u origin main
```

---

## 3. Shell — entry point

Anade a tu `~/.zshrc`:

```zsh
source ~/orbit/orbit.sh
```

O si prefieres definir el entry point manualmente:

```zsh
export ORBIT_EDITOR=typora

mi_orbit() {
    if [[ "$1" == "claude" ]]; then
        cd ~/mi-workspace && claude
    elif [[ $# -eq 0 ]]; then
        ORBIT_HOME=~/mi-workspace python3 ~/orbit/orbit.py shell
    else
        ORBIT_HOME=~/mi-workspace python3 ~/orbit/orbit.py "$@"
    fi
}
```

Recarga con `source ~/.zshrc` y ejecuta `mi_orbit` para entrar en la shell.

---

## 4. Items configurables

### orbit.json — tipos de proyecto

Vive en el workspace (no en el codigo). Define el emoji principal y los tipos de proyecto. Se crea automaticamente con valores por defecto al ejecutar `orbit project create`.

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

- `emoji` — emoji del directorio de proyectos y del prompt de la shell
- `types` — mapa tipo → emoji (puedes anadir, quitar o renombrar tipos)

### ORBIT_EDITOR — editor de markdown

El editor que se abre con `orbit open`. Se configura como variable de entorno:

```bash
export ORBIT_EDITOR=typora    # o code, glow, etc.
```

Editores con soporte integrado: `typora`, `glow`, `code`. Cualquier otro se ejecuta directamente.
Si no se configura, usa `open` (macOS) o `xdg-open` (Linux).

### google-sync.json — sincronizacion con Google

Vive en el workspace. Configura la conexion con Google Calendar y Google Tasks.

```json
{
  "calendars": {
    "investigacion": "ID_DEL_CALENDARIO",
    "docencia": "ID_DEL_CALENDARIO",
    "default": "ID_DEL_CALENDARIO"
  },
  "task_lists": {},
  "repo_url": "https://github.com/TU_USUARIO/tu-repo/blob/main"
}
```

- `calendars` — mapa tipo → ID de Google Calendar (usa `orbit gsync --list-calendars` para ver IDs)
- `task_lists` — se llenan automaticamente al sincronizar por primera vez
- `repo_url` — (opcional) URL base del repo para enlaces en las descripciones de Google

### credentials.json / token.json — Google API

Viven en el workspace. Necesarios para `orbit gsync`:

1. Crea un proyecto en [Google Cloud Console](https://console.cloud.google.com/)
2. Habilita las APIs de Google Calendar y Google Tasks
3. Crea credenciales OAuth2 (tipo "Desktop app")
4. Descarga como `credentials.json` en el directorio del workspace
5. Ejecuta `orbit gsync` — se abrira el navegador para autorizar y generara `token.json`

### ~/.config/deliver.conf — entrega de ficheros

Mapea workspaces de Orbit a directorios en la nube para el comando `deliver`:

```
~/orbit-ws=/ruta/a/OneDrive
~/orbit-ps=/ruta/a/GoogleDrive
```

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

# Orbit — Setup

Guia para configurar un nuevo workspace de Orbit.

---

## 1. Clonar y configurar git

```bash
git clone https://github.com/jahernando/orbit.git ~/mi-orbit
cd ~/mi-orbit
```

Para mantener un repositorio privado sincronizado con el publico:

```bash
git remote rename origin public                          # public = fuente de actualizaciones
git remote add origin https://github.com/TU_USUARIO/mi-orbit.git
git push -u origin main
```

Con esta configuracion:
- `origin` es tu repo privado (commit + push)
- `public` es el repo publico de Orbit (solo pull)
- Al iniciar la shell, Orbit comprueba si hay actualizaciones en `public` y ofrece hacer merge

Si no quieres un repo privado (solo local), desactiva el push al publico:

```bash
git remote set-url --push origin no-push
```

---

## 2. Shell — entry point

Anade a tu `~/.zshrc`:

```zsh
export ORBIT_EDITOR=typora                          # tu editor de markdown

orbit() {
    if [[ "$1" == "claude" ]]; then
        cd ~/mi-orbit && claude
    elif [[ $# -eq 0 ]]; then
        ORBIT_HOME=~/mi-orbit python3 ~/mi-orbit/orbit.py shell
    else
        ORBIT_HOME=~/mi-orbit python3 ~/mi-orbit/orbit.py "$@"
    fi
}
```

Recarga con `source ~/.zshrc` y ejecuta `orbit` para entrar en la shell.

---

## 3. Items configurables

### orbit.json — tipos de proyecto

Define el emoji principal y los tipos de proyecto. Se crea automaticamente con valores por defecto al ejecutar `orbit project create`.

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

Configura la conexion con Google Calendar y Google Tasks para `orbit gsync`.

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

Necesarios para `orbit gsync`:

1. Crea un proyecto en [Google Cloud Console](https://console.cloud.google.com/)
2. Habilita las APIs de Google Calendar y Google Tasks
3. Crea credenciales OAuth2 (tipo "Desktop app")
4. Descarga como `credentials.json` en el directorio de Orbit
5. Ejecuta `orbit gsync` — se abrira el navegador para autorizar y generara `token.json`

### ~/.config/deliver.conf — entrega de ficheros

Mapea workspaces de Orbit a directorios en la nube para el comando `deliver`:

```
/ruta/a/mi-orbit=/ruta/a/OneDrive-o-GoogleDrive
```

### ANTHROPIC_API_KEY — integracion con Claude

Para usar `orbit claude` (asistente IA dentro de la shell):

```bash
export ANTHROPIC_API_KEY='sk-ant-...'
```

Anadelo a `~/.zshrc`. Requiere `pip install anthropic`.

---

## 4. Dependencias

**Requerido:** Python >= 3.9 (sin dependencias externas para uso basico)

**Opcional:**

```bash
# Google Calendar/Tasks sync
pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib

# Claude AI integration
pip install anthropic
```

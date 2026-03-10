# Setup orbit-ps (proyectos personales)

## Arquitectura

```
orbit (público)     <- código limpio, docs, instalación
  ^ push código (desde orbit-ws)
  v pull código (hacia orbit-ps)

orbit-ws (privado)  <- código + proyectos trabajo
orbit-ps (privado)  <- código + proyectos personales
```

## Pasos

### 1. Crear el repo privado vacío en GitHub

Ir a GitHub > New repository > `orbit-ps` > Private > **sin** README ni .gitignore

### 2. Clonar desde el público (tiene el código)

```bash
git clone https://github.com/jahernando/orbit.git ~/Orbit-ps
cd ~/Orbit-ps
```

### 3. Cambiar origin al privado y añadir el público como remote

```bash
git remote rename origin public
git remote add origin https://github.com/jahernando/orbit-ps.git
git push -u origin main
```

Resultado:
- `origin` -> orbit-ps (privado, aquí van tus proyectos)
- `public` -> orbit (público, de aquí viene el código)

### 4. Verificar

```bash
git remote -v
```

Debe mostrar:
```
origin   https://github.com/jahernando/orbit-ps.git (fetch/push)
public   https://github.com/jahernando/orbit.git (fetch/push)
```

## Flujo de desarrollo (desde orbit-ws)

### Push diario a orbit-ws (código + proyectos trabajo)

```bash
cd ~/Orbit
orbit-ws commit          # o: git add ... && git commit
git push origin main     # sube todo a orbit-ws (privado)
```

### Publicar versión limpia a orbit (público)

Solo ficheros de código, sin datos de proyectos:

```bash
cd /tmp
git clone https://github.com/jahernando/orbit.git orbit-public-staging
# Copiar código actualizado
cp ~/Orbit/orbit.py orbit-public-staging/
cp ~/Orbit/core/*.py orbit-public-staging/core/
cp -r ~/Orbit/tests/ orbit-public-staging/tests/
cp ~/Orbit/CHULETA.md ~/Orbit/README.md ~/Orbit/TUTORIAL.md orbit-public-staging/
cp ~/Orbit/.gitignore orbit-public-staging/
cp ~/Orbit/📐templates/*.md ~/Orbit/📐templates/*.css orbit-public-staging/📐templates/
# Commit, tag y push
cd orbit-public-staging
git add -A
git commit -m "feat: descripción del cambio"
git tag vX.Y.Z
git push origin main && git push origin vX.Y.Z
# Limpiar
rm -rf /tmp/orbit-public-staging
```

Versionado (semver): PATCH (bug fix) / MINOR (nueva feature) / MAJOR (rompe interfaz)

## Comandos git (definidos en .zshrc)

Detectan automáticamente si estás en orbit-ws o orbit-ps.

| Comando | Qué hace |
|---------|----------|
| `orbit-commit` | `orbit commit` en el directorio actual |
| `orbit-push` | commit si hace falta + push a origin (privado) |
| `orbit-push --clean vX.Y.Z` | lo anterior + push código limpio a orbit (público) con tag |
| `orbit-pull` | en orbit-ws: pull de origin; en orbit-ps: pull de public (código) |

### Ejemplos

```bash
# Día normal en orbit-ws: guardar y subir trabajo
cd ~/Orbit
orbit-push

# Publicar nueva versión limpia
cd ~/Orbit
orbit-push --clean v0.3.0

# Actualizar código en orbit-ps
cd ~/Orbit-ps
orbit-pull
```

## Uso diario

| Acción | Comando |
|--------|---------|
| Entrar en orbit trabajo | `orbit-ws` |
| Entrar en orbit personal | `orbit-ps` |
| Guardar y subir cambios | `orbit-push` |
| Publicar versión pública | `orbit-push --clean vX.Y.Z` |
| Actualizar código en orbit-ps | `cd ~/Orbit-ps && orbit-pull` |

## Notas

- **Nunca** hacer push de `~/Orbit-ps` a `public` (solo pull)
- Los cambios de código se hacen en `orbit-ws` y se suben al público desde ahí
- Cada orbit tiene su propio `🚀proyectos/` independiente
- `--clean` solo funciona desde orbit-ws y pide confirmación antes de publicar
- El staging temporal garantiza que no se filtran datos de proyectos al repo público

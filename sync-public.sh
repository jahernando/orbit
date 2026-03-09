#!/bin/bash
# sync-public.sh — Sincroniza el código de Orbit al mirror público
#
# Uso:
#   ./sync-public.sh              # sincroniza y hace push
#   ./sync-public.sh --dry-run    # muestra qué haría sin ejecutar
#
# Requisito: el repo público debe existir en GitHub.

set -euo pipefail

PRIVATE_DIR="$(cd "$(dirname "$0")" && pwd)"
PUBLIC_REMOTE="https://github.com/jahernando/orbit.git"
WORK_DIR=$(mktemp -d)
DRY_RUN=false

[[ "${1:-}" == "--dry-run" ]] && DRY_RUN=true

cleanup() { rm -rf "$WORK_DIR"; }
trap cleanup EXIT

echo "📦 Preparando mirror público..."
echo "   Origen:  $PRIVATE_DIR"
echo "   Destino: $PUBLIC_REMOTE"
echo

# --- 1. Copiar ficheros de código (sin .git, sin proyectos reales) ---

# Ficheros raíz
for f in orbit.py CHULETA.md README.md TUTORIAL.md .gitignore; do
    [[ -f "$PRIVATE_DIR/$f" ]] && cp "$PRIVATE_DIR/$f" "$WORK_DIR/"
done

# core/
cp -r "$PRIVATE_DIR/core" "$WORK_DIR/core"
rm -rf "$WORK_DIR/core/__pycache__"

# tests/
if [[ -d "$PRIVATE_DIR/tests" ]]; then
    cp -r "$PRIVATE_DIR/tests" "$WORK_DIR/tests"
    rm -rf "$WORK_DIR/tests/__pycache__"
fi

# templates/
cp -r "$PRIVATE_DIR/📐templates" "$WORK_DIR/📐templates"

# --- 2. Crear proyecto mission de ejemplo ---
echo "✨ Creando proyecto mission de ejemplo..."

MISSION_DIR="$WORK_DIR/🚀proyectos/☀️mission/notes"
mkdir -p "$MISSION_DIR"
MISSION_DIR="$WORK_DIR/🚀proyectos/☀️mission"

cat > "$MISSION_DIR/project.md" << 'PROJ'
# ☀️mission

- Tipo: ☀️ Misión
- Estado: ▶️ Activo
- Prioridad: 🔶 Media

## Estado actual

*Proyecto raíz — planificación general, evaluaciones y decisiones de gestión.*

---
[logbook](./logbook.md) · [highlights](./highlights.md) · [agenda](./agenda.md) · [notes](./notes/)
PROJ

cat > "$MISSION_DIR/logbook.md" << 'LOG'
# Logbook — ☀️mission

<!-- Tipos: #idea #referencia #apunte #problema #resultado #decision #evaluacion -->
<!-- Formato: YYYY-MM-DD contenido #tipo [O]? -->

2026-03-01 Orbit configurado, primer día de uso #apunte
2026-03-01 Flujo: agenda → trabajo → report → evaluar #decision
LOG

cat > "$MISSION_DIR/highlights.md" << 'HL'
# Highlights — ☀️mission

## 📊 Evaluaciones

- Primera semana: flujo de trabajo validado

## 🏛️ Decisiones

- Usar `report --log mission` para guardar evaluaciones semanales
HL

cat > "$MISSION_DIR/agenda.md" << 'AG'
# Agenda — ☀️mission

## ✅ Tareas

- [ ] Revisar prioridades del mes (2026-03-15)
- [ ] Preparar evaluación semanal (2026-03-07) [recur:weekly]

## 🏁 Hitos

- [ ] Portfolio estabilizado (2026-04-01)
AG

# --- 3. Limpiar .gitignore ---
cat > "$WORK_DIR/.gitignore" << 'GI'
# Binarios y resultados locales
**/references/
**/results/

# Python
__pycache__/
*.py[cod]
*.pyo
.venv/

# macOS
.DS_Store

# Google Calendar credentials (sensitive)
credentials.json
token.json

# Temp output
cmd.md
GI

# --- 4. Init git y commit ---
cd "$WORK_DIR"
git init -b main >/dev/null 2>&1
git config core.precomposeunicode false
git add -A

if $DRY_RUN; then
    echo
    echo "🔍 Dry run — ficheros que se publicarían:"
    echo
    git diff --cached --name-only | head -80
    echo
    echo "Total: $(git diff --cached --name-only | wc -l | tr -d ' ') ficheros"
    echo
    echo "Para ejecutar de verdad: ./sync-public.sh"
else
    git commit -m "Orbit — personal scientific project management in plain markdown" >/dev/null
    git remote add origin "$PUBLIC_REMOTE"
    echo "🚀 Pushing al mirror público..."
    git push --force origin main
    echo
    echo "✅ Mirror público actualizado: $PUBLIC_REMOTE"
fi

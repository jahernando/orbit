# orbit.sh — shell functions for Orbit CLI
# Compatible with sh/bash/zsh. Source from your shell rc file.
# Editor: configura "editor" en orbit.json de cada workspace.

ORBIT_CODE="$HOME/orbit"
ORBIT_PYTHON="$HOME/miniconda3/envs/nu/bin/python3"
export PATH="$ORBIT_CODE/bin:$PATH"

# ── Orbit entry points ─────────────────────────────────────────────────────

worbit() {
    if [ "$1" = "claude" ]; then
        cd "$HOME/🚀orbit-ws" && claude
    elif [ $# -eq 0 ]; then
        ORBIT_HOME="$HOME/🚀orbit-ws" $ORBIT_PYTHON "$ORBIT_CODE/orbit.py" shell
    else
        ORBIT_HOME="$HOME/🚀orbit-ws" $ORBIT_PYTHON "$ORBIT_CODE/orbit.py" "$@"
    fi
}

porbit() {
    if [ "$1" = "claude" ]; then
        cd "$HOME/🌿orbit-ps" && claude
    elif [ $# -eq 0 ]; then
        ORBIT_HOME="$HOME/🌿orbit-ps" $ORBIT_PYTHON "$ORBIT_CODE/orbit.py" shell
    else
        ORBIT_HOME="$HOME/🌿orbit-ps" $ORBIT_PYTHON "$ORBIT_CODE/orbit.py" "$@"
    fi
}

# ── Orbit git workflow ──────────────────────────────────────────────────────

_orbit_detect() {
    case "$PWD" in
        "$HOME"/🌿orbit-ps|"$HOME"/🌿orbit-ps/*) echo "$HOME/🌿orbit-ps" ;;
        "$HOME"/🚀orbit-ws|"$HOME"/🚀orbit-ws/*) echo "$HOME/🚀orbit-ws" ;;
        *) echo "" ;;
    esac
}

orbit_commit() {
    local dir
    dir=$(_orbit_detect)
    if [ -z "$dir" ]; then
        echo "⚠️  No estás en un directorio Orbit"; return 1
    fi
    (cd "$dir" && ORBIT_HOME="$dir" $ORBIT_PYTHON "$ORBIT_CODE/orbit.py" commit "$@")
}

orbit_push() {
    local dir
    dir=$(_orbit_detect)
    if [ -z "$dir" ]; then
        echo "⚠️  No estás en un directorio Orbit"; return 1
    fi

    # Commit if there are pending changes
    (cd "$dir" && {
        if [ -n "$(git status --porcelain)" ]; then
            echo "📦 Hay cambios sin commit, ejecutando orbit commit..."
            ORBIT_HOME="$dir" $ORBIT_PYTHON "$ORBIT_CODE/orbit.py" commit || return 1
        fi
        git push origin main || return 1
        echo "✓ Push a origin completado"
    }) || return 1
}

orbit_pull() {
    local dir
    dir=$(_orbit_detect)
    if [ -z "$dir" ]; then
        echo "⚠️  No estás en un directorio Orbit"; return 1
    fi
    (cd "$dir" && git pull origin main)
}

# ── Update code ─────────────────────────────────────────────────────────────

orbit_update() {
    (cd "$ORBIT_CODE" && git pull origin main && echo "✓ Código actualizado")
}

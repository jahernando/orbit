# orbit.sh — shell functions for Orbit CLI
# Compatible with sh/bash/zsh. Source from your shell rc file.

export ORBIT_EDITOR=typora

# ── Orbit entry points ─────────────────────────────────────────────────────

orbit_ws() {
    if [ "$1" = "claude" ]; then
        cd /Users/hernando/Orbit && claude
    elif [ $# -eq 0 ]; then
        ORBIT_HOME=/Users/hernando/Orbit ORBIT_PROMPT="🚀" python3 /Users/hernando/Orbit/orbit.py shell
    else
        ORBIT_HOME=/Users/hernando/Orbit ORBIT_PROMPT="🚀" python3 /Users/hernando/Orbit/orbit.py "$@"
    fi
}

orbit_ps() {
    if [ "$1" = "claude" ]; then
        cd /Users/hernando/Orbit-ps && claude
    elif [ $# -eq 0 ]; then
        ORBIT_HOME=/Users/hernando/Orbit-ps ORBIT_PROMPT="🌿" python3 /Users/hernando/Orbit-ps/orbit.py shell
    else
        ORBIT_HOME=/Users/hernando/Orbit-ps ORBIT_PROMPT="🌿" python3 /Users/hernando/Orbit-ps/orbit.py "$@"
    fi
}

# ── Orbit git workflow ──────────────────────────────────────────────────────

_orbit_detect() {
    case "$PWD" in
        /Users/hernando/Orbit-ps|/Users/hernando/Orbit-ps/*) echo "$HOME/Orbit-ps" ;;
        /Users/hernando/Orbit|/Users/hernando/Orbit/*)       echo "$HOME/Orbit" ;;
        *) echo "" ;;
    esac
}

orbit_commit() {
    dir=$(_orbit_detect)
    if [ -z "$dir" ]; then
        echo "⚠️  No estás en un directorio Orbit"; return 1
    fi
    (cd "$dir" && python3 "$dir/orbit.py" commit "$@")
}

orbit_push() {
    dir=$(_orbit_detect)
    if [ -z "$dir" ]; then
        echo "⚠️  No estás en un directorio Orbit"; return 1
    fi

    clean=false
    tag=""
    for arg in "$@"; do
        case "$arg" in
            --clean) clean=true ;;
            v*)      tag="$arg" ;;
        esac
    done

    # Commit if there are pending changes
    (cd "$dir" && {
        if [ -n "$(git status --porcelain)" ]; then
            echo "📦 Hay cambios sin commit, ejecutando orbit commit..."
            python3 "$dir/orbit.py" commit || return 1
        fi
        git push origin main || return 1
        echo "✓ Push a origin completado"
    }) || return 1

    # --clean: push código limpio a orbit (público), solo desde orbit-ws
    if $clean; then
        if [ "$dir" != "$HOME/Orbit" ]; then
            echo "⚠️  --clean solo se puede usar desde orbit-ws"
            return 1
        fi
        if [ -z "$tag" ]; then
            echo "⚠️  Especifica un tag: orbit_push --clean v0.3.0"
            return 1
        fi

        echo "🧹 Preparando push limpio a orbit (público)..."
        rm -rf /tmp/orbit-public-staging
        git clone https://github.com/jahernando/orbit.git /tmp/orbit-public-staging || return 1

        cp "$dir/orbit.py" /tmp/orbit-public-staging/
        cp "$dir"/core/*.py /tmp/orbit-public-staging/core/
        cp -r "$dir"/tests/ /tmp/orbit-public-staging/tests/
        cp "$dir"/CHULETA.md "$dir"/README.md "$dir"/TUTORIAL.md /tmp/orbit-public-staging/
        cp "$dir"/.gitignore /tmp/orbit-public-staging/
        cp "$dir"/📐templates/*.md "$dir"/📐templates/*.css /tmp/orbit-public-staging/📐templates/ 2>/dev/null

        (cd /tmp/orbit-public-staging && {
            git add -A
            if [ -z "$(git status --porcelain)" ]; then
                echo "⚠️  No hay cambios de código respecto al público"
                rm -rf /tmp/orbit-public-staging
                return 1
            fi
            echo "Cambios a publicar:"
            git diff --cached --stat
            echo ""
            printf "¿Publicar como %s? [s/N]: " "$tag"
            read ans
            case "$ans" in
                s|si|sí|y) ;;
                *) echo "Cancelado."; rm -rf /tmp/orbit-public-staging; return 0 ;;
            esac
            git commit -m "release $tag" && \
            git tag "$tag" && \
            git push origin main && \
            git push origin "$tag" && \
            echo "✓ Publicado $tag en orbit (público)"
        }) || return 1
        rm -rf /tmp/orbit-public-staging
    fi
}

orbit_pull() {
    dir=$(_orbit_detect)
    if [ -z "$dir" ]; then
        echo "⚠️  No estás en un directorio Orbit"; return 1
    fi

    (cd "$dir" && {
        if [ "$dir" = "$HOME/Orbit" ]; then
            git pull origin main
        else
            git fetch public && git merge public/main
        fi
    })
}

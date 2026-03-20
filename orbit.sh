# orbit.sh — shell functions for Orbit CLI
# Compatible with sh/bash/zsh. Source from your shell rc file.

export ORBIT_EDITOR=typora

ORBIT_CODE="$HOME/orbit"
export PATH="$ORBIT_CODE/bin:$PATH"

# ── Orbit entry points ─────────────────────────────────────────────────────

worbit() {
    if [ "$1" = "claude" ]; then
        cd "$HOME/🚀orbit-ws" && claude
    elif [ $# -eq 0 ]; then
        ORBIT_HOME="$HOME/🚀orbit-ws" python3 "$ORBIT_CODE/orbit.py" shell
    else
        ORBIT_HOME="$HOME/🚀orbit-ws" python3 "$ORBIT_CODE/orbit.py" "$@"
    fi
}

porbit() {
    if [ "$1" = "claude" ]; then
        cd "$HOME/🌿orbit-ps" && claude
    elif [ $# -eq 0 ]; then
        ORBIT_HOME="$HOME/🌿orbit-ps" python3 "$ORBIT_CODE/orbit.py" shell
    else
        ORBIT_HOME="$HOME/🌿orbit-ps" python3 "$ORBIT_CODE/orbit.py" "$@"
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
    (cd "$dir" && ORBIT_HOME="$dir" python3 "$ORBIT_CODE/orbit.py" commit "$@")
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
            ORBIT_HOME="$dir" python3 "$ORBIT_CODE/orbit.py" commit || return 1
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

# ── Note aliases (weekly/monthly in mission) ─────────────────────────────────
# Usage: ow "Plan: revisar paper" --entry plan
#        om "Objetivos Q2" --entry decision
#        ow-report   → report today → weekly note
#        ow-agenda   → agenda → weekly note

_orbit_week() { python3 "$ORBIT_CODE/orbit.py" week 2>/dev/null | head -1; }
_orbit_month() { python3 "$ORBIT_CODE/orbit.py" date 2>/dev/null | head -1 | cut -c1-7; }

ow() { worbit log mission "$@" --note "$(_orbit_week)"; }
om() { worbit log mission "$@" --note "$(_orbit_month)"; }
pw() { porbit log mission "$@" --note "$(_orbit_week)"; }
pm() { porbit log mission "$@" --note "$(_orbit_month)"; }

ow-report() { worbit report "${1:-today}" --note "mission:$(_orbit_week)"; }
ow-agenda() { worbit agenda --note "mission:$(_orbit_week)"; }
om-report() { worbit report "${1:-month}" --note "mission:$(_orbit_month)"; }

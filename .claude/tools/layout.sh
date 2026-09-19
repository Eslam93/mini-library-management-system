#!/usr/bin/env bash
# Work out where this workspace's pieces are, on THIS machine. Source it; never hardcode a path.
#
#   . .claude/tools/layout.sh            sets WS_ROOT, WS_REPOS, WS_LAYOUT
#   bash .claude/tools/layout.sh --report
#
# WHY: requiring a specific folder on a specific drive fails at the first step on any other
# machine. The clones live wherever they already live; everything else adapts.
#
# RESOLVES
#   WS_ROOT    the root: where .claude/, the knowledge base, and working/ live
#   WS_REPOS   the folder CONTAINING the clones (shape B), or WS_ROOT itself (shape A)
#   WS_LAYOUT  single | nested | flat | external | recorded | env | missing
#
# ORDER, first hit wins:
#   1. shape A: WS_ROOT is itself a git checkout and has no .workspace marker
#   2. the .workspace marker at the root (WS_REPOS=... and optionally WS_ANCHOR=...)
#   3. the WS_REPOS environment variable
#   4. discovery: the anchor repository (WS_ANCHOR, default: any git checkout) in the usual places
#
# It never returns an empty root: when nothing is found it falls back to the caller's directory
# and says so with WS_LAYOUT=missing. Branch on that, never on an empty variable.

# Is this the root of a git checkout? A linked worktree carries a .git FILE, not a directory, so
# testing for a directory would make every worktree invisible: seal would refuse to run and the
# Stop hook would exit 0 on a weakened committed test. Ask git instead.
# Both sides go through cd and pwd because `rev-parse` answers in the native form (C:/...) while
# the shell works in the MSYS form (/c/...), and comparing those as strings never matches on
# Windows. Asking about a plain subfolder correctly says no, because the toplevel it reports is the
# enclosing repository, not the subfolder.
is_checkout_root() {
  local top a b
  top="$(git -C "$1" rev-parse --show-toplevel 2>/dev/null)" || return 1
  [ -n "$top" ] || return 1
  a="$(cd "$1" 2>/dev/null && pwd)" || return 1
  b="$(cd "$top" 2>/dev/null && pwd)" || return 1
  [ "$a" = "$b" ]
}

ws_resolve_layout() {
    local start="${1:-$PWD}"
    WS_ROOT=""
    local d="$start"
    for _ in 1 2 3 4 5 6; do
        if [ -f "$d/.workspace" ] || [ -d "$d/.claude" ]; then WS_ROOT="$d"; break; fi
        local parent; parent="$(cd "$d/.." 2>/dev/null && pwd)" || break
        [ "$parent" = "$d" ] && break
        d="$parent"
    done
    [ -z "$WS_ROOT" ] && WS_ROOT="$start"

    # 1. shape A
    if is_checkout_root "$WS_ROOT" && [ ! -f "$WS_ROOT/.workspace" ]; then
        WS_REPOS="$WS_ROOT"; WS_LAYOUT="single"; return 0
    fi

    # 2. the marker
    if [ -f "$WS_ROOT/.workspace" ]; then
        local v
        v=$(grep -E -e '^WS_REPOS=' "$WS_ROOT/.workspace" 2>/dev/null | head -1 | cut -d= -f2-)
        WS_ANCHOR=$(grep -E -e '^WS_ANCHOR=' "$WS_ROOT/.workspace" 2>/dev/null | head -1 | cut -d= -f2-)
        if [ -n "$v" ] && [ -d "$v" ]; then
            WS_REPOS="$(cd "$v" && pwd)"; WS_LAYOUT="recorded"; return 0
        fi
    fi

    # 3. the environment
    if [ -n "${WS_REPOS:-}" ] && [ -d "${WS_REPOS}" ]; then WS_LAYOUT="env"; return 0; fi

    # 4. discovery
    local candidate
    for candidate in "$WS_ROOT/repos" "$WS_ROOT" "$WS_ROOT/src" "$WS_ROOT/source" "$WS_ROOT/code" "$WS_ROOT/.."; do
        [ -d "$candidate" ] || continue
        if [ -n "${WS_ANCHOR:-}" ]; then
            is_checkout_root "$candidate/$WS_ANCHOR" || continue
        else
            ls -d "$candidate"/*/.git >/dev/null 2>&1 || continue
        fi
        WS_REPOS="$(cd "$candidate" && pwd)"
        case "$candidate" in
            "$WS_ROOT/repos") WS_LAYOUT="nested" ;;
            "$WS_ROOT")       WS_LAYOUT="flat" ;;
            *)                WS_LAYOUT="external" ;;
        esac
        return 0
    done

    WS_REPOS="$WS_ROOT/repos"; WS_LAYOUT="missing"; return 1
}

# Path to one clone, or nothing.
ws_repo()  { is_checkout_root "$WS_REPOS/$1" && printf '%s' "$WS_REPOS/$1"; }

# Every clone present, one path per line. In shape A, the root itself.
ws_repos() {
    if [ "${WS_LAYOUT:-}" = "single" ]; then printf '%s\n' "$WS_ROOT"; return; fi
    local d
    for d in "$WS_REPOS"/*/; do is_checkout_root "${d%/}" && printf '%s\n' "${d%/}"; done
}

ws_resolve_layout "$PWD"

if [ "${1:-}" = "--report" ]; then
    echo "WS_ROOT    $WS_ROOT"
    echo "WS_REPOS   $WS_REPOS"
    echo "WS_LAYOUT  $WS_LAYOUT"
    echo "checkouts  $(ws_repos | wc -l | tr -d ' ')"
fi

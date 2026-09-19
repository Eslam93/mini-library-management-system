#!/usr/bin/env bash
# PreToolUse guard for the small number of commands whose damage cannot be undone by reading the
# output and trying again. Matched on both Bash and PowerShell.
#
# THE LIST STARTS EMPTY. An entry is added only after a real incident, with the date and what it
# cost, because a guard that blocks legitimate work is how guards get switched off. The reference
# block at the end lists common destructive command shapes, all off; adopt one only when it has
# earned its place here.
#
# Contract: exit 2 blocks the call and stderr is shown to Claude; exit 0 allows.
# Self-test: with GUARD_COMMANDS_SELFTEST=1, a command containing __guard_commands_selftest__ is
# blocked, so verify.sh can prove this hook fires.

payload=$(cat)
[ -z "$payload" ] && exit 0

cmd=$(printf '%s' "$payload" | grep -oE '"command"[[:space:]]*:[[:space:]]*"([^"\\]|\\.)*"' | head -1 | sed 's/^[^:]*:[[:space:]]*"//; s/"$//')
[ -z "$cmd" ] && exit 0

deny() {
  {
    echo "BLOCKED: $1"
    echo
    echo "$2"
    echo
    [ -n "${3:-}" ] && { echo "$3"; echo; }
    echo "This is a hook, not a preference. If it is genuinely wrong, say so to the user and"
    echo "let them decide. Do not reword the command to get around it."
  } >&2
  exit 2
}

# ---- active entries: what, why, instead, date added -------------------------------------
# (none yet)

# ---- self-test ---------------------------------------------------------------------------
if [ "${GUARD_COMMANDS_SELFTEST:-}" = "1" ] && printf '%s' "$cmd" | grep -q '__guard_commands_selftest__'; then
  deny "the guard-commands self-test marker" "verify.sh is proving this hook can block a call." ""
fi

exit 0

# ---- reference shapes, all OFF. Adopt one only after an incident here, and date it. ------
#   rm -rf on /, ~, or the repository root     '\brm\s+-[a-z]*r[a-z]*\s+(/|~|\$HOME|\.)(\s|$)'
#   git push --force to a shared branch        '\bgit\b.*\bpush\b.*--force(\s|$)'
#   git push --mirror, deletes absent refs     '\bgit\b.{0,80}\bpush\b.{0,80}--mirror\b'
#   git reset --hard, git checkout .           '\bgit\s+(reset\s+--hard|checkout\s+\.)(\s|$)'
#   DROP TABLE, DROP DATABASE                  '\bdrop\s+(table|database)\b'
#   docker system prune, kubectl delete        '(docker\s+system\s+prune|kubectl\s+delete)'
#   npm publish, --no-verify                   '(\bnpm\s+publish\b|--no-verify\b)'

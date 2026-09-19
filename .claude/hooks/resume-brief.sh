#!/usr/bin/env bash
# SessionStart hook, matcher "compact": after a compaction, put the disposable state back in front
# of the assistant so the build continues from the agreed brief rather than from a summary.
# Prints working/status.md, then the task brief, capped. Exit 0 always.
#
# Which brief: the one this session is carrying. baseline.sh seal writes
# working/active-tasks/<session id> at the owner's yes, holding one line, working/<task>/brief.md,
# and this hook reads the pointer for the session id the host gives it. That is the whole rule: no
# recency, no scanning. It matters because another brief can be written under working/ after the
# agreement, so the newest brief in the tree is not necessarily the agreed one.
#
# Fallback, when there is no valid pointer for this session (a task sealed without a session id,
# or a pointer that was removed): the newest working/<task>/brief.md, one level deep only, so a
# nested brief can never win. It is announced as a guess, because it is one.

payload=$(cat)
field() { printf '%s' "$payload" | grep -oE "\"$1\"[[:space:]]*:[[:space:]]*\"([^\"\\\\]|\\\\.)*\"" | head -1 | sed 's/^[^:]*:[[:space:]]*"//; s/"$//; s#\\\\#/#g'; }
cwd=$(field cwd); [ -z "$cwd" ] && cwd="$PWD"
session=$(field session_id)
working="$cwd/working"
[ -d "$working" ] || exit 0

if [ -f "$working/status.md" ]; then
  echo "After compaction. Re-read before continuing. working/status.md:"
  head -n 60 "$working/status.md"
fi

# ---- the brief this session is carrying ------------------------------------------------------
brief=""; how="none"
if printf '%s' "$session" | grep -Eq '^[A-Za-z0-9][A-Za-z0-9_-]{7,63}$'; then
  ptr="$working/active-tasks/$session"
  if [ -f "$ptr" ]; then
    how="stale"
    rel=$(grep -m1 -vE '^[[:space:]]*$' "$ptr" 2>/dev/null | tr -d '\r' | sed 's/^[[:space:]]*//; s/[[:space:]]*$//')
    # one task folder, one brief: never a nested path, never an absolute path, never a traversal
    if printf '%s' "$rel" | grep -Eq '^working/[A-Za-z0-9][A-Za-z0-9._-]*/brief\.md$' && [ -f "$cwd/$rel" ]; then
      brief="$cwd/$rel"; how="active"
    fi
  fi
fi
# The stale case is said out loud whether or not anything can replace it: a session that quietly
# lost its agreement across a compaction is the failure this hook exists to prevent.
if [ "$how" = "stale" ]; then
  echo
  echo "This session's active-task pointer does not name a readable task brief, so the agreement it"
  echo "recorded cannot be restored. Ask the owner what this session is working on."
fi
if [ -z "$brief" ]; then
  for f in "$working"/*/brief.md; do
    [ -f "$f" ] || continue
    if [ -z "$brief" ] || [ "$f" -nt "$brief" ]; then brief="$f"; fi
  done
  [ -n "$brief" ] && [ "$how" != "stale" ] && how="fallback"
  [ -n "$brief" ] && [ "$how" = "stale" ] && how="stale-fallback"
fi

[ -z "$brief" ] && exit 0
rel="${brief#$cwd/}"
echo
case "$how" in
  active)
    echo "The agreed task brief this session is carrying, $rel (bound to this session when the owner said yes; do not re-plan it):" ;;
  stale-fallback)
    echo "The newest task brief under working/ is $rel. Treat it as a guess, not as this session's agreement:" ;;
  *)
    echo "No task is bound to this session. The newest task brief under working/ is $rel. Treat it as a guess,"
    echo "not as this session's agreement; ask the owner before building from it:" ;;
esac
head -n 80 "$brief"
exit 0

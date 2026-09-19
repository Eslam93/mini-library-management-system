#!/usr/bin/env bash
# Stop hook: blocks a turn that weakened, skipped, or deleted a test.
# Deliberately light: pure git work, nothing that compiles. The full suite is behind verify.sh --full.
# Contract: exit 0 fine; exit 2 blocks and stderr goes to Claude. Honours stop_hook_active or it
# loops against itself. Claude Code overrides a Stop hook after eight consecutive blocks.
# Where it looks: every git checkout under WS_REPOS when cwd carries a .workspace marker (shape B;
# the marker wins, because a workspace root is itself a checkout); otherwise the repository at cwd
# when cwd is a git checkout (shape A). If neither, exit 0.
#
# What it compares against: the baseline of the task THIS session is carrying. baseline.sh seal
# writes baseline_commit.<checkout> into the front matter of working/<task>/brief.md at the owner's
# yes and binds it to the session in working/active-tasks/<session id>. This hook reads the pointer
# for the session id the host gives it, so two sessions sharing one checkout each measure their own
# task, and no brief is chosen by recency.
#   - a weakening that was committed stays visible: a diff against HEAD alone shows nothing once the
#     weakened test is committed;
#   - renames are detected (-M), so a staged git mv plus a removed assertion is compared old path
#     to new path;
#   - a test added during the task has no version at the baseline, so it is compared against the
#     commit that first added it during the task, following renames back; comparing against HEAD
#     would see nothing once the weakening was itself committed, and one git mv would otherwise make
#     the weakened file its own comparison base. With no baseline, or when the file was staged and
#     never committed, HEAD is the only earlier version and is used.
# It also refuses to run on a seal it cannot trust. baseline.sh records seal_sha256 over the approval
# fields, and this hook rebuilds it. A digest that does not match, or a brief that records a baseline
# and carries no digest at all, blocks (exit 2) rather than falling back: falling back to HEAD is the
# outcome such an edit is after, and treating a missing digest as harmless would mean deleting one
# line disarmed the whole mechanism.
# Fallback, never a block, and never a guess at which task is active: no session id, no pointer, a
# pointer that does not resolve, a brief with no seal, or a seal that does not name this checkout,
# and the comparison is against HEAD, as for a session with no task. A sealed commit rewritten by
# a rebase, amend, or squash is compared from its merge-base with HEAD; one that does not exist here
# falls back to HEAD. The last four print a note; a session with no id and a session with no pointer
# are the ordinary case and stay quiet. A note goes to stdout, which Claude Code keeps in its debug
# log for a Stop hook that exits 0: it is for a person reading the log, not for the assistant.
# The hook never writes a pointer and never seals anything.

payload=$(cat)
repeat=0
printf '%s' "$payload" | grep -Eq '"stop_hook_active"[[:space:]]*:[[:space:]]*true' && repeat=1
# stop_hook_active says a Stop hook already blocked this turn. Exiting 0 on it would make the second
# Stop an unconditional pass: block once, carry on, finish. The deterministic check runs again
# instead, so a weakening that is still there still blocks and a fixed one is allowed.
# Loop protection is Claude Code's own consecutive-block limit, which overrides a Stop hook after
# eight, not this hook waving the second attempt through.

field() { printf '%s' "$payload" | grep -oE "\"$1\"[[:space:]]*:[[:space:]]*\"([^\"\\\\]|\\\\.)*\"" | head -1 | sed 's/^[^:]*:[[:space:]]*"//; s/"$//; s#\\\\#/#g'; }
cwd=$(field cwd); [ -z "$cwd" ] && cwd="$PWD"
session=$(field session_id)
transcript=$(field transcript_path)

# ---- rationalization note (never blocks) -------------------------------------------------
if [ -n "$transcript" ] && [ -f "$transcript" ]; then
  phrase=$(tail -n 40 "$transcript" | grep -oiE 'skip (the )?tests? for now|pre-existing (bug|issue|failure)|good enough for now|can be fixed later|temporarily disabl|out of scope for this|will fix in a follow-?up' | head -1)
  [ -n "$phrase" ] && echo "note from verify-on-finish: the last message carries a rationalization phrase ($phrase). Worth a second look before accepting."
fi

# ---- where to look -------------------------------------------------------------------------
# Is this the root of a git checkout? A linked worktree carries a .git FILE, not a directory, so
# testing for a directory would make every worktree invisible: seal would refuse to run and this
# hook would exit 0 on a weakened committed test. Ask git instead.
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
repos=()
if [ -f "$cwd/.workspace" ]; then
  reposRoot=$(grep -E -e '^WS_REPOS=' "$cwd/.workspace" | head -1 | cut -d= -f2-)
  if [ -n "$reposRoot" ] && [ -d "$reposRoot" ]; then
    for d in "$reposRoot"/*/; do is_checkout_root "${d%/}" && repos+=("${d%/}"); done
  fi
elif is_checkout_root "$cwd"; then
  repos=("$cwd")
fi
[ "${#repos[@]}" -eq 0 ] && exit 0
command -v git >/dev/null 2>&1 || exit 0

# ---- the brief this session is carrying, if any ----------------------------------------------
briefFile=""; briefName=""
if printf '%s' "$session" | grep -Eq '^[A-Za-z0-9][A-Za-z0-9_-]{7,63}$'; then
  ptr="$cwd/working/active-tasks/$session"
  if [ -f "$ptr" ]; then
    rel=$(grep -m1 -vE '^[[:space:]]*$' "$ptr" 2>/dev/null | tr -d '\r' | sed 's/^[[:space:]]*//; s/[[:space:]]*$//')
    # one task folder, one brief: never a nested path, never an absolute path, never a traversal
    if printf '%s' "$rel" | grep -Eq '^working/[A-Za-z0-9][A-Za-z0-9._-]*/brief\.md$' && [ -f "$cwd/$rel" ]; then
      briefFile="$cwd/$rel"; briefName="$rel"
    else
      echo "note from verify-on-finish: the active-task pointer for this session does not resolve to a task brief; comparing against HEAD."
    fi
  fi
fi
# Trailing whitespace on a fence or a key must not change the answer, and it must not change it
# differently from the PowerShell twin, which trims.
front_matter() {
  head -1 "$1" 2>/dev/null | sed 's/[[:space:]]*$//' | grep -qx -- '---' || return 0
  awk 'NR==1 {next} {t=$0; sub(/[[:space:]]+$/, "", t)} t=="---" {exit} {print}' "$1"
}
fm=""
if [ -n "$briefFile" ]; then
  fm=$(front_matter "$briefFile")
  if ! printf '%s\n' "$fm" | grep -Eq '^baseline_commit(\.[^:]*)?:'; then
    echo "note from verify-on-finish: $briefName carries no baseline; comparing against HEAD."
    briefFile=""; fm=""
  fi
fi

# ---- is the approved starting point still the approved one? --------------------------------
# Rendered byte for byte as baseline.sh renders it: fixed field order, one "key: value" line with a
# single space, values trimmed, per-checkout lines sorted by bytes, trailing newline. The review
# fields are outside it on purpose, because they are written later in the task.
digest_tool() {
  # The seam exists because no PATH on a Git Bash machine has coreutils without sha256sum, so the
  # fail-closed branch below could not otherwise be exercised. Same convention as
  # GUARD_COMMANDS_SELFTEST in guard-commands.sh, which verify.sh uses to prove that hook can block.
  [ -n "${VERIFY_ON_FINISH_NO_DIGEST:-}" ] && return 0
  if command -v sha256sum >/dev/null 2>&1; then echo "sha256sum"
  elif command -v shasum >/dev/null 2>&1; then echo "shasum -a 256"; fi
}
canonical_seal() { # $1: the front matter text
  local fm="$1" k
  for k in task approved_at tier; do
    printf '%s\n' "$fm" | awk -v key="$k:" 'index($0, key)==1 {
      v = substr($0, length(key)+1); sub(/^[ \t]+/, "", v); sub(/[ \t\r]+$/, "", v)
      print key " " v; exit }'
  done
  printf '%s\n' "$fm" | awk 'match($0, /^baseline_commit(\.[^:]*)?:/) {
    k = substr($0, 1, RLENGTH-1); v = substr($0, RLENGTH+1)
    sub(/^[ \t]+/, "", v); sub(/[ \t\r]+$/, "", v)
    print k ": " v }' | LC_ALL=C sort
  for k in brief_sha256 pre_existing; do
    printf '%s\n' "$fm" | awk -v key="$k:" 'index($0, key)==1 {
      v = substr($0, length(key)+1); sub(/^[ \t]+/, "", v); sub(/[ \t\r]+$/, "", v)
      print key " " v; exit }'
  done
}
if [ -n "$briefFile" ]; then
  want=$(printf '%s\n' "$fm" | awk 'index($0, "seal_sha256:")==1 {print $NF; exit}')
  tool=$(digest_tool)
  if [ -z "$tool" ] && [ "$repeat" = 1 ]; then
    # Said once already. Missing hash tooling is not a test violation and not something the
    # assistant can repair by editing anything, so blocking again would be a loop with no exit.
    # The task is still not verified: baseline.sh check fails for the same reason at hand-back.
    echo "note from verify-on-finish: still no sha256 tool on PATH, so the seal in $briefName was not verified. Not blocking again, because this is not repairable from here. The task is NOT verified; baseline.sh check will say the same at hand-back."
  elif [ -z "$tool" ]; then
    # Fail closed, once. A session carrying a sealed task whose seal cannot be verified is exactly
    # the state an edited seal produces, and a note on stdout reaches the debug log and nobody else.
    {
      echo "STOP: the sealed approval in $briefName cannot be verified here."
      echo
      echo "  Neither sha256sum nor shasum is on PATH, so seal_sha256 cannot be recomputed. This"
      echo "  session is carrying a sealed task, and an unverifiable seal is not the same as no"
      echo "  task: it is the state a moved baseline would also produce, so it is not waved through."
      echo
      echo "Put a sha256 tool on PATH and finish again. On Windows, Git for Windows provides"
      echo "sha256sum in its usr/bin; on macOS, shasum ships with the system."
    } >&2
    exit 2
  else
    # A brief that records a baseline and no digest is not to be trusted: deleting one line would
    # otherwise turn any sealed brief into an unprotected one, and the baseline could then be moved
    # and the tier rewritten with nothing to notice. Every seal baseline.sh writes carries the
    # digest, so a missing one means the brief was edited or was sealed by something else.
    if [ -z "$want" ] || [ "$want" != "$(canonical_seal "$fm" | $tool | cut -d' ' -f1)" ]; then
      if [ -z "$want" ]; then
        reason="it records a baseline but carries no seal_sha256 at all"
      else
        reason="seal_sha256 does not match the approval fields now in the brief"
      fi
      # Both cases stop here. A brief that records a baseline with no digest is not to be trusted:
      # deleting one line would otherwise turn any sealed brief into an unprotected one. A digest
      # that does not match is the other half of the same problem. Either way the comparison base
      # itself may have been moved, so falling back to HEAD would hand the edit exactly what it was
      # after: every weakening before the new commit disappearing. There is no safe base left, so
      # the turn stops here and a person decides.
      {
        echo "STOP: the sealed approval in $briefName cannot be trusted."
        echo
        echo "  $reason. The approval fields are task, approved_at,"
        echo "  tier, every baseline_commit, brief_sha256, and pre_existing."
        echo
        echo "This is not the same as a task with no baseline. The recorded starting point is what"
        echo "every test comparison in this session is measured from, so a moved baseline can hide"
        echo "a weakening rather than merely lose the protection. Comparing against HEAD instead"
        echo "would be exactly the outcome the edit produces, so this turn stops."
        echo
        echo "Do one of these, then finish:"
        echo "  - restore the sealed values from git or from the owner's record; or"
        echo "  - if the agreement really changed, say so to the owner, write a new brief under"
        echo "    working/<new-task>/ and seal that one, leaving this approval readable beside it."
        echo
        t="${briefName#working/}"; t="${t%/brief.md}"
        echo "  bash .claude/tools/baseline.sh check $t"
      } >&2
      exit 2
    fi
  fi
fi

is_test_file() { printf '%s' "$1" | grep -Eiq '(\.test\.|\.spec\.|(^|/)test_[^/]*\.py$|(^|/)(tests?|__tests__)/)'; }
# Word boundaries, so that submit( and protest( are not counted as test( and it(, and so that this
# counter agrees with the PowerShell twin, which has them too.
assertions()   { grep -oE '\bit[[:space:]]*\(|\btest[[:space:]]*\(|\bexpect[[:space:]]*\(|\bassert[[:space:]]' | wc -l | tr -d ' '; }
skips()        { grep -oiE '\.skip[[:space:]]*\(|\.only[[:space:]]*\(|\[Skip|@skip|xit[[:space:]]*\(|xdescribe[[:space:]]*\(' | wc -l | tr -d ' '; }

problems=""
allowed=""
# The owner can authorize one exact test change, recorded in the brief by
# `baseline.sh allow-test-change`. It is keyed on the file AND the sha256 of the content that
# results, so it covers that change and nothing after it: one more edit and the hash no longer
# matches. There is no path-level or task-level switch, by design.
content_hash() {  # repo relpath -> sha256 of what is on disk now, or "deleted"
  local f="$1/$2" t
  [ -f "$f" ] || { echo deleted; return; }
  t=$(digest_tool); [ -n "$t" ] || { echo unhashable; return; }
  $t < "$f" | cut -d' ' -f1
}
is_authorized() {  # "<checkout>/<path>" contenthash -> 0 when the brief authorizes exactly this
  [ -n "$fm" ] || return 1
  printf '%s\n' "$fm" | awk -v key="test_change_allowed: $2 $1 " 'index($0, key)==1 { found=1 } END { exit !found }'
}
note_allowed() { allowed="$allowed
  ALLOWED  $1  (owner-authorized for exactly this content)"; }

compare() { # repo base label oldpath newpath since -> appends to problems
  local repo="$1" base="$2" label="$3" old="$4" new="$5" since="$6" before after b a sb sa h
  before=$(git -C "$repo" show "$base:$old" 2>/dev/null)
  after=$(cat "$repo/$new" 2>/dev/null)
  b=$(printf '%s' "$before" | assertions); a=$(printf '%s' "$after" | assertions)
  sb=$(printf '%s' "$before" | skips); sa=$(printf '%s' "$after" | skips)
  if [ "$a" -lt "$b" ] || [ "$sa" -gt "$sb" ]; then
    h=$(content_hash "$repo" "$new")
    if is_authorized "$(basename "$repo")/$new" "$h"; then note_allowed "$(basename "$repo")/$new"; return; fi
  fi
  [ "$a" -lt "$b" ] && problems="$problems
  WEAKENED $label  (assertions $b -> $a) since $since"
  [ "$sa" -gt "$sb" ] && problems="$problems
  SKIPPED  $label  (skip markers $sb -> $sa) since $since"
}

for repo in "${repos[@]}"; do
  name=$(basename "$repo")
  base="HEAD"; since="HEAD"
  if [ -n "$briefFile" ]; then
    # index()==1 is a literal, anchored prefix match: a checkout name with a space, a regex
    # character, or a glob character is safe, and a line that merely mentions the key cannot win
    # The key up to the colon, then whatever whitespace follows, exactly as canonical_seal reads
    # it. Matching "key: " with a literal space let a tab keep the digest valid while this lookup
    # found nothing and quietly fell back to HEAD.
    sha=$(printf '%s\n' "$fm" | awk -v key="baseline_commit.$name:" \
      'index($0, key)==1 {v=substr($0, length(key)+1); sub(/^[ \t]+/, "", v); sub(/[ \t\r]+$/, "", v); print v; exit}')
    if [ -z "$sha" ]; then
      echo "note from verify-on-finish: $briefName has no baseline for $name; comparing against HEAD."
    elif git -C "$repo" merge-base --is-ancestor "$sha" HEAD 2>/dev/null; then
      base="$sha"; since="the task baseline ${sha:0:7} ($briefName)"
    elif mb=$(git -C "$repo" merge-base "$sha" HEAD 2>/dev/null) && [ -n "$mb" ]; then
      base="$mb"; since="the merge-base ${mb:0:7} of the rewritten task baseline ${sha:0:7} ($briefName)"
      echo "note from verify-on-finish: the task baseline ${sha:0:7} in $briefName is not an ancestor of HEAD in $name (rewritten by a rebase, amend, or squash); comparing from its merge-base ${mb:0:7}."
    else
      echo "note from verify-on-finish: the task baseline ${sha:0:7} in $briefName does not exist in $name; comparing against HEAD instead."
    fi
  fi
  status=$(git -C "$repo" diff --name-status -M "$base" 2>/dev/null) || continue
  [ -z "$status" ] && continue
  while IFS=$'\t' read -r code file file2; do
    [ -z "$file" ] && continue
    case "$code" in
      D*) is_test_file "$file" || continue
          if is_authorized "$name/$file" deleted; then note_allowed "$name/$file"; continue; fi
          problems="$problems
  DELETED  $name/$file since $since" ;;
      M*) is_test_file "$file" || continue
          compare "$repo" "$base" "$name/$file" "$file" "$file" "$since" ;;
      R*) { is_test_file "$file" || is_test_file "$file2"; } || continue
          compare "$repo" "$base" "$name/$file -> $file2 (renamed)" "$file" "$file2" "$since" ;;
      A*) is_test_file "$file" || continue
          # A test that did not exist at the baseline was introduced during this task, so there is
          # no baseline version to compare against. Comparing against HEAD catches a weakening that
          # is still uncommitted, and nothing else: once the weakening is committed, HEAD is the
          # weakened version and the two sides are identical. So compare
          # against the version at the commit that first added the file during this task.
          # git log with one pathspec cannot pair a rename, so it reports a commit that renamed the
          # file as an ADD of the new name, and the weakened file becomes its own comparison base.
          # Follow the rename back, bounded, using the commit's own full diff to find the old name.
          probe="$file"; upto="HEAD"; first=""; hop=0
          while [ "$hop" -lt 5 ]; do
            first=$(git -C "$repo" log --diff-filter=A --reverse --format=%H "$base..$upto" -- "$probe" 2>/dev/null | head -1)
            [ -n "$first" ] || break
            src=$(git -C "$repo" show --name-status -M --format= "$first" 2>/dev/null \
                  | awk -v f="$probe" '$1 ~ /^R/ && $3 == f { print $2; exit }')
            [ -n "$src" ] || break
            probe="$src"; upto="$first^"; hop=$((hop+1))
          done
          if [ -n "$first" ]; then
            lbl="$name/$file (added during the task)"
            [ "$probe" != "$file" ] && lbl="$name/$probe -> $file (added during the task, then renamed)"
            compare "$repo" "$first" "$lbl" "$probe" "$file" \
              "${first:0:7}, the commit that added it during this task"
          elif git -C "$repo" cat-file -e "HEAD:$file" 2>/dev/null; then
            # staged but never committed, or no task baseline: HEAD is the only earlier version
            compare "$repo" "HEAD" "$name/$file (added during the task)" "$file" "$file" "HEAD"
          fi ;;
    esac
  done <<< "$status"
done

[ -n "$allowed" ] && echo "note from verify-on-finish: owner-authorized test changes were allowed:$allowed"
[ -z "$problems" ] && exit 0
{
  echo "STOP: a test was weakened, skipped, or deleted."
  echo "$problems"
  echo
  echo "Removing or editing a test to make a suite pass hides the behaviour the test existed"
  echo "to protect. Do one of these, then finish:"
  echo "  - restore the assertions and fix the code instead; or"
  echo "  - if the test genuinely encoded wrong behaviour, say so explicitly to the user,"
  echo "    explain why the old assertion was wrong, and get their agreement."
  echo
  echo "Do not silence this by reverting the file and re-applying the same edit. A change made"
  echo "since the task baseline stays visible, committed or not, for as long as this session"
  echo "carries this task."
  echo
  echo "If the owner has looked at this specific change and agreed the test should lose those"
  echo "assertions, they can authorize exactly it, and only it:"
  echo "  bash .claude/tools/baseline.sh allow-test-change <task> <checkout>/<path> \"<their words>\""
  echo "That records the file and the exact content it ends at. One more edit and it stops applying."
} >&2
exit 2

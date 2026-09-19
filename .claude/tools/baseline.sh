#!/usr/bin/env bash
# The task baseline: the approved starting point, written into the task's own brief, and the
# binding that makes that brief the active task for this Claude session.
#
#   bash .claude/tools/baseline.sh seal   <task> <tier>              record the approval, bind the session
#   bash .claude/tools/baseline.sh review <task> completed <route> <evidence>
#   bash .claude/tools/baseline.sh allow-test-change <task> <checkout>/<path> <owner's reason>
#   bash .claude/tools/baseline.sh review <task> waived <owner's words>
#   bash .claude/tools/baseline.sh check  <task>                     is the task fit to hand back
#
# Run it from the repository root (shape A) or the workspace root (shape B; the .workspace marker
# wins when both exist, as in layout.sh).
#
# seal writes front matter at the top of working/<task>/brief.md, the file the owner approved:
#
#   task, approved_at, tier, one baseline_commit.<checkout> per checkout, brief_sha256 (the digest
#   of the body below the front matter), pre_existing (a count), and seal_sha256 (the digest of all
#   of those together, in canonical form).
#
# Two digests, because there are two ways an approved task can be moved. brief_sha256 answers "is
# the agreement still the text the owner approved". seal_sha256 answers "is the approved starting
# point still the approved starting point": without it, editing baseline_commit to a later commit
# leaves the body untouched, so the body digest stays happy, while every weakening before that
# commit disappears from what the Stop hook can see. The review fields are deliberately outside
# seal_sha256: they are written later in the task, by design, and must not invalidate the approval.
#
# and then writes working/active-tasks/<session id>, one line holding working/<task>/brief.md.
# Those two writes are one event: this is the agreement, and this session is now carrying it. The
# Stop hook and the compaction hook both start from the pointer, so neither has to guess which
# brief belongs to this session. The session id is the host's own, read from CLAUDE_CODE_SESSION_ID,
# which a Bash tool call inside Claude Code carries; when it is absent the brief is still sealed and
# the pointer is not written, which is said out loud, and both hooks fall back.
#
# A seal does not move. There is no re-seal: a changed agreement is a new brief under a new task
# folder, sealed on its own, so the original approval stays readable beside it.
#
# The files that were already dirty go to working/<task>/pre-existing.txt beside the brief, because
# they are a list, not metadata; nothing reads it but the owner and /work.
#
# The tool exists so that three values are produced the same way every time: the commit from
# `git rev-parse`, the digest over the same bytes at seal and at check, and the dirty files captured
# before the first edit. It signs nothing and locks nothing.

set -uo pipefail

usage() { sed -n '2,10p' "$0" | sed 's/^# \{0,1\}//' >&2; exit 1; }
die()   { echo "baseline.sh: $*" >&2; exit 1; }

cmd="${1:-}"; task="${2:-}"; arg3="${3:-}"
[ -z "$cmd" ] && usage
[ -z "$task" ] && usage
printf '%s' "$task" | grep -Eq '^[A-Za-z0-9][A-Za-z0-9._-]*$' || die "task name must be one plain path segment: letters, digits, dot, dash, underscore"

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

root="$PWD"
repos=()
if [ -f "$root/.workspace" ]; then
  _here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  . "$_here/layout.sh"
  while IFS= read -r r; do [ -n "$r" ] && repos+=("$r"); done < <(ws_repos)
elif is_checkout_root "$root"; then
  repos=("$root")
else
  die "run it from the repository root, a linked worktree of one, or the workspace root; git does not report this folder as a checkout root and there is no .workspace marker here"
fi
[ "${#repos[@]}" -eq 0 ] && die "no git checkout found"

dir="$root/working/$task"; brief="$dir/brief.md"
[ -f "$brief" ] || die "no brief at working/$task/brief.md; write the agreed brief first"

# The keys this tool owns. Everything else in an existing front matter is kept as it was, but these
# are stripped and rewritten at seal, so a brief cannot arrive at the agreement already carrying its
# own review record: only `review` writes one, after the task exists.
SEAL_KEYS='^(task|approved_at|tier|baseline_commit(\.[^:]*)?|brief_sha256|pre_existing|seal_sha256|review_[a-z]+(\.[^:]*)?|test_change_[a-z_]+):'
SESSION_RE='^[A-Za-z0-9][A-Za-z0-9_-]{7,63}$'

front_matter() { # the lines between the opening and closing --- , or nothing
  [ "$(head -1 "$1" 2>/dev/null)" = "---" ] || return 0
  awk 'NR==1 {next} /^---$/ {exit} {print}' "$1"
}
body() {        # everything that is not the front matter: what the owner approved
  if [ "$(head -1 "$1" 2>/dev/null)" = "---" ]; then
    awk 'NR==1 {next} !seen && /^---$/ {seen=1; next} seen {print}' "$1"
  else cat "$1"; fi
}
digest_tool() {
  if command -v sha256sum >/dev/null 2>&1; then echo "sha256sum"
  elif command -v shasum >/dev/null 2>&1; then echo "shasum -a 256"; fi
}
digest_body() { local t; t=$(digest_tool); [ -n "$t" ] || return 1; body "$1" | $t | cut -d' ' -f1; }
digest_text() { local t; t=$(digest_tool); [ -n "$t" ] || return 1; $t | cut -d' ' -f1; }

# The immutable approval fields, rendered one way and only one way: a fixed field order, one
# "key: value" line each with a single space after the colon and the value trimmed, the per-checkout
# lines sorted by bytes, and a trailing newline. This exact text is what seal_sha256 covers, and
# both Stop hooks rebuild it the same way; if the three ever disagree by one byte, a valid seal
# reads as tampered on one platform, which is why the order is fixed here rather than taken from
# the file. Deliberately NOT the whole front matter: the review fields are written later in the
# task, by design, and must not invalidate the approval.
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

fm=$(front_matter "$brief")
# Whether a brief is already sealed is decided by the whole file, never by whether its front matter
# parses. front_matter() needs line 1 to be exactly ---, so a blank line, a BOM, or a stripped
# header would present a sealed brief as unsealed and let seal run again, moving the baseline to a
# later commit with a fully self-consistent new digest. That is the one thing a seal must not do.
sealed=0; grep -Eq '^(baseline_commit(\.[^:]*)?|seal_sha256):' "$brief" && sealed=1
if [ "$sealed" = 1 ] && [ -z "$fm" ]; then
  die "working/$task/brief.md carries a seal but its front matter cannot be read; the file must begin with a --- fence on line 1. Restore it from git, or agree a new task and seal a new brief beside this one"
fi
session="${CLAUDE_CODE_SESSION_ID:-}"
printf '%s' "$session" | grep -Eq "$SESSION_RE" || session=""

case "$cmd" in
  seal)
    case "$arg3" in
      1|2|3) ;;
      "") die "seal needs the tier: baseline.sh seal $task <1|2|3>. It is the tier stated in the agree message, and Tier 3 carries the review contract" ;;
      *) die "tier must be 1, 2, or 3" ;;
    esac
    # Stripping the approval out of the brief makes it look unsealed, and sealing again would then
    # produce a fresh, self-consistent approval at whatever HEAD is now. pre-existing.txt is written
    # by seal and by nothing else, so its presence says this task was sealed once already, whatever
    # the brief now contains. It does not make working/ tamper-proof, and nothing kept only in a
    # disposable folder can be: it makes the obvious route say no. Deleting the whole task folder
    # and agreeing again is still allowed, because that is the documented way to start over.
    if [ "$sealed" = 0 ] && [ -f "$dir/pre-existing.txt" ]; then
      echo "baseline.sh: working/$task/brief.md was sealed once already, and its approval is no longer in the file." >&2
      echo "A seal does not move, and a brief with its approval removed is not a new agreement. Restore it from the" >&2
      echo "owner's record, or agree a new task under working/<new-task>/ so the original stays readable beside it." >&2
      echo "If you really are starting this task over, remove working/$task/ entirely first, so nothing of the old" >&2
      echo "approval is left to be confused with the new one." >&2
      exit 1
    fi
    if [ "$sealed" = 1 ]; then
      echo "baseline.sh: working/$task/brief.md is already sealed, and a seal does not move." >&2
      echo "A changed agreement is a new task: write the new brief under working/<new-task>/ and seal that one," >&2
      echo "so the original approval stays readable beside it. There is no way to re-seal in place." >&2
      exit 1
    fi
    [ -n "$(digest_tool)" ] || die "neither sha256sum nor shasum on PATH"
    sum=$(digest_body "$brief") || die "could not digest $brief"
    lines=()
    for repo in "${repos[@]}"; do
      name=$(basename "$repo")
      sha=$(git -C "$repo" rev-parse HEAD 2>/dev/null) || die "$name has no commit yet; commit something first"
      lines+=("baseline_commit.$name: $sha")
    done
    pre="$dir/pre-existing.txt"; : > "$pre.tmp"
    for repo in "${repos[@]}"; do
      name=$(basename "$repo")
      # working/ is ignored by .gitignore; skip it anyway so the seal never lists itself
      git -C "$repo" status --porcelain --untracked-files=all 2>/dev/null \
        | grep -vE '^.. "?working/' | sed "s|^|$name |" >> "$pre.tmp"
    done
    n=$(wc -l < "$pre.tmp" | tr -d ' ')
    when=$(date -u +%Y-%m-%dT%H:%M:%SZ)
    kept=$(printf '%s\n' "$fm" | grep -Ev "$SEAL_KEYS" | grep -v '^$')
    # The approval block, in canonical order, written exactly as canonical_seal renders it, so the
    # file on disk and the bytes behind the digest are the same thing and can be checked by eye.
    approval="task: $task
approved_at: $when
tier: $arg3
$(printf '%s\n' "${lines[@]}" | LC_ALL=C sort)
brief_sha256: $sum
pre_existing: $n"
    sealsum=$(printf '%s\n' "$approval" | digest_text) || die "could not digest the approval block"
    {
      echo "---"
      printf '%s\n' "$approval"
      echo "seal_sha256: $sealsum"
      [ -n "$kept" ] && printf '%s\n' "$kept"
      echo "---"
      body "$brief"
    } > "$brief.tmp" && mv "$brief.tmp" "$brief" && mv "$pre.tmp" "$pre" || die "could not write working/$task/brief.md"
    echo "sealed working/$task/brief.md at $when, tier $arg3"
    printf '  %s\n' "${lines[@]}"
    [ "$arg3" = 3 ] && echo "  Tier 3: one independent review must be recorded before hand-back, or an explicit owner waiver"
    # bind it to this session, only now that the seal is on disk
    if [ -n "$session" ]; then
      ptr="$root/working/active-tasks/$session"
      if mkdir -p "$root/working/active-tasks" 2>/dev/null &&
         printf 'working/%s/brief.md\n' "$task" > "$ptr.tmp" 2>/dev/null && mv "$ptr.tmp" "$ptr" 2>/dev/null; then
        echo "  active task for this session: working/active-tasks/$session"
      else
        # The brief is sealed and cannot be sealed again, so this must not be a fatal error with no
        # way out: say exactly what is missing and how to write it by hand.
        rm -f "$ptr.tmp" 2>/dev/null
        echo "  SEALED BUT NOT BOUND: could not write working/active-tasks/$session." >&2
        echo "  The brief is sealed; the binding is missing, so both hooks will use their fallbacks." >&2
        echo "  Fix it with one line, then say that you did:" >&2
        echo "    printf 'working/$task/brief.md\\n' > working/active-tasks/$session" >&2
      fi
    else
      echo "  NOT bound to a session: CLAUDE_CODE_SESSION_ID is absent or malformed, so the compaction and Stop"
      echo "  hooks will use their fallbacks. Seal from a Bash tool call inside Claude Code to bind it."
    fi
    if [ "$n" -eq 0 ]; then echo "  working tree clean: nothing pre-existing"
    else echo "  $n pre-existing change(s) recorded in working/$task/pre-existing.txt; they belong to the owner:"; sed 's/^/    /' "$pre"; fi
    ;;

  review)
    # The Tier 3 contract, recorded once: a review that actually finished, or a waiver the owner
    # actually gave. Nothing here can tell whether either really happened; what it can do is make
    # the two different, dated, and visible to whoever reads the brief later.
    [ "$sealed" = 1 ] || die "working/$task/brief.md carries no baseline; seal it at the owner's yes"
    have=$(printf '%s\n' "$fm" | grep -E '^review_status:' | head -1 | awk '{print $NF}')
    when=$(date -u +%Y-%m-%dT%H:%M:%SZ)
    # A waiver stands: the owner said no review, and that is not something a later command undoes.
    [ "$have" = "waived-by-owner" ] && die "working/$task/brief.md already records review_status: waived-by-owner. The owner's waiver does not move"
    [ -n "$have" ] && [ "$arg3" = "waived" ] && die "working/$task/brief.md already records review_status: $have. A recorded review is not waived afterwards"
    # A completed review names the commit it read. Recording a second one is refused while the code
    # is still that commit, because nothing has changed for a reviewer to look at, and allowed once
    # the code has moved, because then the first review no longer covers what is being handed back.
    if [ "$have" = "completed" ]; then
      moved=0
      while IFS= read -r line; do
        [ -n "$line" ] || continue
        rest="${line#review_commit.}"; rsha="${rest##* }"; rname="${rest%% *}"; rname="${rname%:}"
        for r in "${repos[@]}"; do
          if [ "$(basename "$r")" = "$rname" ]; then
            [ "$(git -C "$r" rev-parse HEAD 2>/dev/null)" = "$rsha" ] || moved=1
          fi
        done
      done <<EOF
$(printf '%s\n' "$fm" | grep -E '^review_commit\.')
EOF
      if [ "$moved" = 0 ]; then
        die "working/$task/brief.md already records a completed review of this exact code. Record another only after the code has moved"
      fi
      echo "the recorded review was of an earlier commit; replacing it with this one" >&2
    fi
    case "$arg3" in
      completed)
        route="${4:-}"
        # An allow-list, not a deny-list: this harness treats exactly two routes as independent,
        # and a name nobody recognises is not evidence that somebody independent looked.
        case "$route" in
          code-review|second-model) ;;
          "") die "which review: baseline.sh review $task completed <code-review|second-model> <evidence>" ;;
          test-guide|local-run|local) die "the local run with /test-guide is not an independent review: the builder runs it. Use code-review or second-model" ;;
          *) die "unknown review route '$route'. This harness treats two as independent: code-review, a fresh context that never saw the reasoning, and second-model, a review by a different model that did not build the change. Adding a third is a decision, not an argument" ;;
        esac
        if [ $# -ge 4 ]; then shift 4; else shift $#; fi
        evidence="$*"
        [ -z "$evidence" ] && die "a completed review carries its result: the verdict line, the finding counts, or what the reviewer returned. A review that was offered, started, or failed is not a completed review"
        rlines=""
        for repo in "${repos[@]}"; do
          rname=$(basename "$repo")
          rsha=$(git -C "$repo" rev-parse HEAD 2>/dev/null) || die "$rname has no commit to review"
          rlines="$rlines
review_commit.$rname: $rsha"
        done
        new="review_status: completed
review_route: $route
review_evidence: $(printf '%s' "$evidence" | tr '\n' ' ')
review_at: $when${rlines}" ;;
      waived)
        if [ $# -ge 3 ]; then shift 3; else shift $#; fi
        words="$*"
        [ -z "$words" ] && die "a waiver carries the owner's own words: baseline.sh review $task waived \"<what they said>\". Silence, a skipped menu, and reaching hand-back are not waivers"
        new="review_status: waived-by-owner
review_waiver: $(printf '%s' "$words" | tr '\n' ' ')
review_at: $when" ;;
      *) die "review takes completed or waived" ;;
    esac
    # Rewrite the front matter without any previous review_ lines, then add these. The seal lines
    # are carried through untouched, so seal_sha256 still verifies: it covers the approval fields,
    # and a review record is workflow data written later in the task.
    keptfm=$(printf '%s\n' "$fm" | grep -Ev '^review_[a-z]+(\.[^:]*)?:' | grep -v '^$')
    {
      echo "---"
      [ -n "$keptfm" ] && printf '%s\n' "$keptfm"
      printf '%s\n' "$new"
      echo "---"
      body "$brief"
    } > "$brief.tmp" && mv "$brief.tmp" "$brief" || die "could not write working/$task/brief.md"
    printf '%s\n' "$new" | sed 's/^/  /'
    echo "recorded in working/$task/brief.md"
    ;;

  allow-test-change)
    # The narrowest authorization that can exist: one task, one file, one exact resulting content,
    # and the owner's words. It is not a waiver and not a switch. Any further edit to that file
    # changes its hash and the authorization stops matching, so it cannot be reused to cover the
    # next weakening. There is deliberately no way to authorize a path in general.
    [ "$sealed" = 1 ] || die "working/$task/brief.md carries no baseline; seal it at the owner's yes"
    target_path="$arg3"
    [ -z "$target_path" ] && die "which test: baseline.sh allow-test-change $task <checkout>/<path> \"<what the owner said>\""
    if [ $# -ge 3 ]; then shift 3; else shift $#; fi
    why="$*"
    [ -z "$why" ] && die "an authorized test change carries the owner's own words: why this test may lose assertions. A build decision is not one"
    cname="${target_path%%/*}"; crest="${target_path#*/}"
    [ "$cname" = "$target_path" ] && die "name the checkout too, as the Stop hook prints it: <checkout>/<path>"
    crepo=""; for r in "${repos[@]}"; do [ "$(basename "$r")" = "$cname" ] && crepo="$r"; done
    [ -z "$crepo" ] && die "no checkout called '$cname' here; the Stop hook prints the name this tool would use"
    if [ -f "$crepo/$crest" ]; then
      chash=$(digest_tool >/dev/null && $(digest_tool) < "$crepo/$crest" | cut -d' ' -f1) || die "could not hash $target_path"
      [ -n "$chash" ] || die "could not hash $target_path"
    else
      chash="deleted"
    fi
    when=$(date -u +%Y-%m-%dT%H:%M:%SZ)
    # One entry per path: the newest decision is the one that counts.
    keptfm=$(printf '%s\n' "$fm" | awk -v p=" $target_path " 'index($0, "test_change_allowed:")==1 && index($0, p) {next} {print}' | grep -v '^$')
    {
      echo "---"
      [ -n "$keptfm" ] && printf '%s\n' "$keptfm"
      printf 'test_change_allowed: %s %s %s %s\n' "$chash" "$target_path" "$when" "$(printf '%s' "$why" | tr '\n' ' ')"
      echo "---"
      body "$brief"
    } > "$brief.tmp" && mv "$brief.tmp" "$brief" || die "could not write working/$task/brief.md"
    echo "authorized in working/$task/brief.md:"
    echo "  $target_path at content $chash"
    echo "  because: $why"
    echo "Any further edit to that file changes its content and this stops applying."
    ;;

  check)
    [ "$sealed" = 1 ] || die "working/$task/brief.md carries no baseline; seal it at the owner's yes"
    bad=0
    want=$(printf '%s\n' "$fm" | grep -E '^brief_sha256:' | head -1 | awk '{print $NF}')
    have=$(digest_body "$brief") || die "neither sha256sum nor shasum on PATH"
    if [ "$want" = "$have" ]; then echo "brief unchanged since approval"
    else echo "BRIEF CHANGED since approval: sealed $want, now $have"; bad=1; fi
    # The body digest above answers "is the agreement still the agreed text". This one answers the
    # other half: "is the approved starting point still the approved starting point". Without it,
    # moving baseline_commit to a later commit leaves the body digest happy and quietly deletes
    # every weakening before the new commit from what the Stop hook can see.
    wantseal=$(printf '%s\n' "$fm" | grep -E '^seal_sha256:' | head -1 | awk '{print $NF}')
    if [ -z "$wantseal" ]; then
      echo "SEAL DIGEST MISSING: this brief records a baseline but no seal_sha256, so its approval"
      echo "  fields are not protected and the Stop hook will refuse the turn. Seal a new brief for"
      echo "  this task; a seal cannot be added to an existing one."
      bad=1
    else
      haveseal=$(canonical_seal "$fm" | digest_text) || die "neither sha256sum nor shasum on PATH"
      if [ "$wantseal" = "$haveseal" ]; then echo "seal intact: the approved starting point has not been edited"
      else
        echo "SEAL TAMPERED: the approval fields have been edited since sealing (sealed $wantseal, now $haveseal)."
        echo "  One of task, approved_at, tier, baseline_commit, brief_sha256, or pre_existing has changed."
        echo "  A seal does not move. Restore the sealed values from git or from the owner's record, or"
        echo "  agree a new task and seal a new brief beside this one."
        bad=1
      fi
    fi
    while IFS= read -r line; do
      rest="${line#baseline_commit.}"; sha="${rest##* }"; name="${rest% *}"; name="${name%:}"
      repo=""; for r in "${repos[@]}"; do [ "$(basename "$r")" = "$name" ] && repo="$r"; done
      if [ -z "$repo" ]; then echo "$name: checkout not found"; bad=1; continue; fi
      if git -C "$repo" merge-base --is-ancestor "$sha" HEAD 2>/dev/null; then
        echo "$name: baseline ${sha:0:7} is an ancestor of HEAD ($(git -C "$repo" rev-list --count "$sha..HEAD") commit(s) since)"
      elif mb=$(git -C "$repo" merge-base "$sha" HEAD 2>/dev/null) && [ -n "$mb" ]; then
        echo "$name: baseline ${sha:0:7} was REWRITTEN (rebase, amend, or squash); the Stop hook compares from its merge-base ${mb:0:7}"; bad=1
      else
        echo "$name: baseline ${sha:0:7} does NOT exist in this checkout; the Stop hook compares against HEAD instead"; bad=1
      fi
    done < <(printf '%s\n' "$fm" | grep -E '^baseline_commit\.')
    if [ -z "$session" ]; then echo "session: CLAUDE_CODE_SESSION_ID is absent here, so the active task cannot be read"
    elif [ "$(cat "$root/working/active-tasks/$session" 2>/dev/null)" = "working/$task/brief.md" ]; then echo "session: this is the active task for $session"
    else echo "session: this is NOT the active task for $session; the hooks will use another brief or their fallback"; bad=1; fi
    # The Tier 3 contract. This runs at hand-back, which is the only point where "no review" and
    # "not yet reviewed" become the same thing if nobody asks.
    tier=$(printf '%s\n' "$fm" | grep -E '^tier:' | head -1 | awk '{print $NF}')
    status=$(printf '%s\n' "$fm" | grep -E '^review_status:' | head -1 | awk '{print $NF}')
    detail=$(printf '%s\n' "$fm" | grep -E '^(review_route|review_waiver):' | head -1 | cut -d' ' -f2-)
    case "$tier" in
      3)
        case "$status" in
          completed)
            echo "tier 3: independent review completed via $detail"
            # Freshness, not provenance. A review covers the code it read; if the code moved after
            # it, the thing being handed back is not the thing anybody reviewed.
            seenany=0; stale=""
            while IFS= read -r line; do
              [ -n "$line" ] || continue
              seenany=1
              rest="${line#review_commit.}"; rsha="${rest##* }"; rname="${rest%% *}"; rname="${rname%:}"
              found=0
              for r in "${repos[@]}"; do
                if [ "$(basename "$r")" = "$rname" ]; then
                  found=1
                  now=$(git -C "$r" rev-parse HEAD 2>/dev/null)
                  [ "$now" = "$rsha" ] || stale="$stale $rname (reviewed ${rsha:0:7}, now ${now:0:7})"
                fi
              done
              [ "$found" = 1 ] || stale="$stale $rname (checkout not found)"
            done <<EOF
$(printf '%s\n' "$fm" | grep -E '^review_commit\.')
EOF
            if [ "$seenany" = 0 ]; then
              echo "  REVIEW COMMIT NOT RECORDED: this review record names no reviewed commit, so"
              echo "  it cannot be shown to cover the code being handed back. Record the review again."
              bad=1
            elif [ -n "$stale" ]; then
              echo "  REVIEW IS STALE: the code has moved since it was reviewed:$stale"
              echo "  What is being handed back is not what was reviewed. Run another independent review and record it:"
              echo "    bash .claude/tools/baseline.sh review $task completed <code-review|second-model> <result>"
              bad=1
            else
              echo "  and the code still matches the reviewed commit"
            fi ;;
          waived-by-owner) echo "tier 3: independent review WAIVED by the owner: $detail" ;;
          *) echo "TIER 3 CONTRACT INCOMPLETE: no independent review and no owner waiver is recorded."
             echo "  Run one of the independent routes and record it, or ask the owner and record their waiver:"
             echo "    bash .claude/tools/baseline.sh review $task completed <code-review|second-model> <result>"
             echo "    bash .claude/tools/baseline.sh review $task waived \"<what the owner said>\""
             bad=1 ;;
        esac ;;
      1|2)
        if [ -n "$status" ]; then echo "tier $tier: independent review $status, which tier $tier does not require"
        else echo "tier $tier: no independent review is required"; fi ;;
      *)
        # Not knowing the tier is not the same as passing: a Tier 3 task with no tier line would
        # otherwise slip through the one check that asks about review.
        echo "TIER NOT RECORDED: this brief carries no tier, so the Tier 3 contract cannot be checked."
        echo "  The tier line is missing or was removed. Add the tier the"
        echo "  owner agreed, as one front-matter line, and run this again:"
        echo "    tier: <1|2|3>"
        bad=1 ;;
    esac
    exit $bad
    ;;

  *) usage ;;
esac

#!/usr/bin/env bash
# Fires every hook by hand, in both shells where they exist, and prints one line per case.
# This is how the harness proves its guards can go red: a hook that has never blocked anything
# is not known to work. Run it after any change to a hook.
#
#   bash .claude/tools/hooks.test.sh
#
# Secret-shaped values are assembled at runtime so this file never carries one. PowerShell cases
# run only where powershell is on PATH; bash cases always run.

unset MSYS_NO_PATHCONV
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
H="$(cd "$HERE/../hooks" && pwd)"
T="$(mktemp -d 2>/dev/null || mktemp -d -t hooks)"
trap 'rm -rf "$T"' EXIT

have_ps=0; command -v powershell >/dev/null 2>&1 && have_ps=1
winpath() { if command -v cygpath >/dev/null 2>&1; then cygpath -m "$1"; else printf '%s' "$1"; fi; }
ps() { powershell -NoProfile -ExecutionPolicy Bypass -File "$(winpath "$1")"; }
shells="sh"; [ "$have_ps" = 1 ] && shells="ps1 sh"

fails=0; total=0
case_() { total=$((total+1)); if [ "$2" = "$3" ]; then printf '  ok    %-58s exit %s\n' "$1" "$3"; else printf '  FAIL  %-58s expected %s got %s\n' "$1" "$2" "$3"; fails=$((fails+1)); fi; }
run() { # shell hook payload -> exit code; stdout to $T/out, stderr to $T/err
  if [ "$1" = ps1 ]; then printf '%s' "$3" | ps "$H/$2.ps1" >"$T/out" 2>"$T/err"; else printf '%s' "$3" | bash "$H/$2.sh" >"$T/out" 2>"$T/err"; fi; echo $?
}

tok="ghp_$(printf 'A%.0s' $(seq 1 40))"
pw="$(printf 'Sup3r%s' 'SecretValue')"
p_token='{"tool_name":"Write","tool_input":{"file_path":"x.md","content":"token: '"$tok"'"}}'
p_pwvar='{"tool_name":"Write","tool_input":{"file_path":"x.js","content":"const password = process.argv[2];"}}'
p_conn='{"tool_name":"Edit","tool_input":{"file_path":"a.json","new_string":"Host=db;Port=5432;Database=app;Username=app;Password='"$pw"';"}}'
p_shape='{"tool_name":"Write","tool_input":{"file_path":"doc.md","content":"a GitHub token looks like ghp_[A-Za-z0-9]{36}"}}'
p_placeholder='{"tool_name":"Write","tool_input":{"file_path":"a.json","content":"Host=db;Database=app;Password=<your-password>;"}}'
p_prose='{"tool_name":"Write","tool_input":{"file_path":"note.md","content":"a connection string with a `Host=` field and a `Password=` field on one line"}}'

echo "guard-secrets"
for shell in $shells; do
  case_ "$shell: fake GitHub token blocked"             2 "$(run $shell guard-secrets "$p_token")"
  case_ "$shell: const password = argv allowed"         0 "$(run $shell guard-secrets "$p_pwvar")"
  case_ "$shell: connection-string password blocked"    2 "$(run $shell guard-secrets "$p_conn")"
  case_ "$shell: token shape description allowed"       0 "$(run $shell guard-secrets "$p_shape")"
  case_ "$shell: placeholder password allowed"          0 "$(run $shell guard-secrets "$p_placeholder")"
  case_ "$shell: prose naming the fields allowed"       0 "$(run $shell guard-secrets "$p_prose")"
done

echo "guard-commands"
p_cmd='{"tool_name":"Bash","tool_input":{"command":"git status"}}'
p_mark='{"tool_name":"PowerShell","tool_input":{"command":"echo __guard_commands_selftest__"}}'
for shell in $shells; do
  case_ "$shell: ordinary command allowed"              0 "$(run $shell guard-commands "$p_cmd")"
  case_ "$shell: self-test marker without env allowed"  0 "$(run $shell guard-commands "$p_mark")"
  case_ "$shell: self-test marker with env blocked"     2 "$(GUARD_COMMANDS_SELFTEST=1 run $shell guard-commands "$p_mark")"
done

echo "verify-on-finish"
R="$T/repo"; mkdir -p "$R/tests"
git -C "$R" init -q
git -C "$R" config core.autocrlf false
printf 'working/\n' > "$R/.gitignore"    # as this repository's .gitignore has it; the seal must never be staged
printf 'test("a", () => { expect(1).toBe(1); expect(2).toBe(2); });\n' > "$R/tests/x.test.js"
printf 'skip the tests for now, this is a pre-existing bug\n' > "$T/transcript.jsonl"
git -C "$R" add -A && git -C "$R" -c user.email=t@t -c user.name=t commit -qm init 2>/dev/null
for shell in $shells; do
  if [ "$shell" = ps1 ]; then cwdv="$(winpath "$R")"; tp="$(winpath "$T/transcript.jsonl")"; else cwdv="$R"; tp="$T/transcript.jsonl"; fi
  git -C "$R" checkout -q -- tests/x.test.js
  case_ "$shell: clean tree allowed"                    0 "$(run $shell verify-on-finish '{"cwd":"'"$cwdv"'","stop_hook_active":false}')"
  printf 'test("a", () => { expect(1).toBe(1); });\n' > "$R/tests/x.test.js"
  case_ "$shell: weakened test blocked"                 2 "$(run $shell verify-on-finish '{"cwd":"'"$cwdv"'","stop_hook_active":false}')"
  # stop_hook_active does not wave the second Stop through: the check runs again, so a weakening
  # that is still there still blocks. Claude Code's consecutive-block limit is the loop protection.
  case_ "$shell: weakened, stop_hook_active, blocks again" 2 "$(run $shell verify-on-finish '{"cwd":"'"$cwdv"'","stop_hook_active":true}')"
  git -C "$R" checkout -q -- tests/x.test.js; rm "$R/tests/x.test.js"
  case_ "$shell: deleted test blocked"                  2 "$(run $shell verify-on-finish '{"cwd":"'"$cwdv"'","stop_hook_active":false}')"
  git -C "$R" checkout -q -- tests/x.test.js
  run $shell verify-on-finish '{"cwd":"'"$cwdv"'","stop_hook_active":false,"transcript_path":"'"$tp"'"}' >/dev/null
  total=$((total+1)); if grep -q rationalization "$T/out"; then echo "  ok    $shell: rationalization note printed, non-blocking"; else echo "  FAIL  $shell: no rationalization note"; fails=$((fails+1)); fi
done

echo "verify-on-finish with a task baseline"
# The two cases a HEAD-only comparison cannot detect: a weakening that was
# committed before the turn ended, and a staged rename with an assertion removed. Both must block
# while this session carries the sealed task, and so must a test added during the task and then
# weakened. When the session carries no task, or the recorded commit no longer exists, the hook
# falls back to HEAD and the committed weakening is invisible again, which is the documented limit,
# not a bug. A rewritten (rebased) baseline is compared from its merge-base instead. The brief is
# sealed and bound by the real tool, so the tool is under test too. Every check here fires the hook
# and reads its exit code or its text; none reads the scripts.
# A multi-line fixture, so that a rename with one assertion removed is still a rename to git
# (similarity above 50 percent); a one-line file would show as delete plus add.
printf 'describe("z", () => {\n  test("one", () => {\n    expect(1).toBe(1);\n  });\n  test("two", () => {\n    expect(2).toBe(2);\n    expect(3).toBe(3);\n  });\n});\n' > "$R/tests/z.test.js"
git -C "$R" add -A && git -C "$R" -c user.email=t@t -c user.name=t commit -qm fixture 2>/dev/null
init=$(git -C "$R" rev-parse HEAD)
trunk=$(git -C "$R" rev-parse --abbrev-ref HEAD)
gitc() { git -C "$R" -c user.email=t@t -c user.name=t "$@"; }
SIDA="sessionAAAAAAAA1"; SIDB="sessionBBBBBBBB2"
# seal_ <task> [session]: write a brief, seal it, and bind it to that session, through the real tool
seal_() { rm -rf "$R/working/$1"; mkdir -p "$R/working/$1"; printf '# brief %s\noutcome: tests stay whole\n' "$1" > "$R/working/$1/brief.md"; (cd "$R" && CLAUDE_CODE_SESSION_ID="${2:-$SIDA}" bash "$HERE/baseline.sh" seal "$1" "${3:-2}" >"$T/seal.out" 2>&1); }
weaken_commit() { printf 'test("a", () => { expect(1).toBe(1); });\n' > "$R/tests/x.test.js"; gitc commit -qam weaken 2>/dev/null; }
for shell in $shells; do
  if [ "$shell" = ps1 ]; then cwdv="$(winpath "$R")"; else cwdv="$R"; fi
  p_stop='{"cwd":"'"$cwdv"'","session_id":"'"$SIDA"'","stop_hook_active":false}'
  git -C "$R" reset -q --hard "$init"; rm -rf "$R/working"
  seal_ task-1; sealed=$?
  total=$((total+1)); if [ "$sealed" -eq 0 ] && grep -q "^baseline_commit.repo: $init" "$R/working/task-1/brief.md"; then echo "  ok    $shell: baseline.sh seal recorded the commit in the brief"; else echo "  FAIL  $shell: baseline.sh seal did not record the commit in the brief"; fails=$((fails+1)); cat "$T/seal.out"; fi
  total=$((total+1)); if [ "$(sed -n '2,$p' "$R/working/task-1/brief.md" | grep -c '^# brief task-1$')" = 1 ]; then echo "  ok    $shell: the approved text survives sealing"; else echo "  FAIL  $shell: sealing damaged the brief body"; fails=$((fails+1)); fi
  total=$((total+1)); if [ "$(cat "$R/working/active-tasks/$SIDA" 2>/dev/null)" = "working/task-1/brief.md" ]; then echo "  ok    $shell: seal bound the brief to this session"; else echo "  FAIL  $shell: seal did not write the active-task pointer"; fails=$((fails+1)); fi
  case_ "$shell: sealed, clean tree allowed"            0 "$(run $shell verify-on-finish "$p_stop")"
  # committed weakening: weaken, commit, then try to finish
  weaken_commit
  case_ "$shell: committed weakening blocked"           2 "$(run $shell verify-on-finish "$p_stop")"
  total=$((total+1)); if grep -q "since the task baseline" "$T/err"; then echo "  ok    $shell: the block names the task baseline"; else echo "  FAIL  $shell: the block does not name the baseline"; fails=$((fails+1)); fi
  # renamed weakening: git mv, remove one assertion, stage it
  git -C "$R" reset -q --hard "$init"
  git -C "$R" mv tests/z.test.js tests/w.test.js
  printf 'describe("z", () => {\n  test("one", () => {\n    expect(1).toBe(1);\n  });\n  test("two", () => {\n    expect(2).toBe(2);\n  });\n});\n' > "$R/tests/w.test.js"
  git -C "$R" add -A
  case_ "$shell: staged rename plus removed assertion blocked" 2 "$(run $shell verify-on-finish "$p_stop")"
  total=$((total+1)); if grep -q "renamed" "$T/err"; then echo "  ok    $shell: the block names the rename"; else echo "  FAIL  $shell: the block does not name the rename"; fails=$((fails+1)); fi
  # A test added during the task has no version at the baseline. Three cases, and the middle one is
  # the hole the task baseline closes: comparing against HEAD sees an uncommitted weakening and
  # nothing else, because once the weakening is committed HEAD IS the weakened version.
  git -C "$R" reset -q --hard "$init"
  printf 'test("n", () => { expect(1).toBe(1); expect(2).toBe(2); });\n' > "$R/tests/n.test.js"
  git -C "$R" add -A; gitc commit -qm add-test 2>/dev/null
  case_ "$shell: test added during the task, not weakened, allowed" 0 "$(run $shell verify-on-finish "$p_stop")"
  printf 'test("n", () => { expect(1).toBe(1); });\n' > "$R/tests/n.test.js"
  case_ "$shell: test added during the task, then weakened, blocked" 2 "$(run $shell verify-on-finish "$p_stop")"
  gitc commit -qam weaken-added 2>/dev/null
  total=$((total+1)); if [ -z "$(git -C "$R" status --porcelain)" ]; then echo "  ok    $shell: the weakening of the added test is committed, tree clean"; else echo "  FAIL  $shell: the added-test weakening did not commit"; fails=$((fails+1)); fi
  case_ "$shell: added test weakened and COMMITTED still blocked" 2 "$(run $shell verify-on-finish "$p_stop")"
  total=$((total+1)); if grep -q "the commit that added it during this task" "$T/err"; then echo "  ok    $shell: the block names the commit that added the test"; else echo "  FAIL  $shell: the block does not name the adding commit"; fails=$((fails+1)); fi

  # ---- the approved starting point cannot move undetected ----
  # Editing baseline_commit to a later commit leaves the body untouched, so brief_sha256 stays happy
  # while every weakening before that commit vanishes from the comparison. seal_sha256 covers the
  # approval fields, and a mismatch blocks rather than falling back, because falling back to HEAD is
  # exactly the outcome the edit was after.
  git -C "$R" reset -q --hard "$init"; rm -rf "$R/working"
  seal_ task-1
  case_ "$shell: an intact seal is not reported as tampering" 0 "$(run $shell verify-on-finish "$p_stop")"
  weaken_commit
  moved=$(git -C "$R" rev-parse HEAD)
  case_ "$shell: the true baseline blocks the committed weakening" 2 "$(run $shell verify-on-finish "$p_stop")"
  sed "s|^baseline_commit.repo: .*|baseline_commit.repo: $moved|" "$R/working/task-1/brief.md" > "$T/mv" && mv "$T/mv" "$R/working/task-1/brief.md"
  total=$((total+1)); if grep -q "^baseline_commit.repo: $moved\$" "$R/working/task-1/brief.md"; then echo "  ok    $shell: the sealed baseline was moved to a later commit"; else echo "  FAIL  $shell: the tamper fixture did not apply"; fails=$((fails+1)); fi
  case_ "$shell: a moved baseline_commit blocks as tampering" 2 "$(run $shell verify-on-finish "$p_stop")"
  total=$((total+1)); if grep -q "does not match the approval fields" "$T/err"; then echo "  ok    $shell: the block says the approval fields no longer match"; else echo "  FAIL  $shell: the tamper block does not say what happened"; fails=$((fails+1)); fi
  # the tier is inside the seal, which also closes the one-line edit that removed the Tier 3 contract
  git -C "$R" reset -q --hard "$init"; rm -rf "$R/working"
  seal_ task-1 "$SIDA" 3
  sed 's|^tier: 3$|tier: 2|' "$R/working/task-1/brief.md" > "$T/mv" && mv "$T/mv" "$R/working/task-1/brief.md"
  case_ "$shell: an edited tier blocks as tampering"     2 "$(run $shell verify-on-finish "$p_stop")"
  # a review record is workflow data, written later in the task by design: it must NOT read as tampering
  git -C "$R" reset -q --hard "$init"; rm -rf "$R/working"
  seal_ task-1 "$SIDA" 3
  (cd "$R" && CLAUDE_CODE_SESSION_ID="$SIDA" bash "$HERE/baseline.sh" review task-1 waived "the owner said skip it" >/dev/null 2>&1)
  case_ "$shell: a review recorded after sealing is not tampering" 0 "$(run $shell verify-on-finish "$p_stop")"
  # Deleting the one seal_sha256 line must not disarm the mechanism. A brief that records a baseline
  # and carries no digest is refused, not trusted: otherwise one deleted line would make the
  # baseline movable and the tier rewritable again.
  git -C "$R" reset -q --hard "$init"; rm -rf "$R/working"
  seal_ task-1
  grep -v '^seal_sha256:' "$R/working/task-1/brief.md" > "$T/lg" && mv "$T/lg" "$R/working/task-1/brief.md"
  case_ "$shell: a baseline with no seal digest is refused" 2 "$(run $shell verify-on-finish "$p_stop")"
  total=$((total+1)); if grep -q "no seal_sha256 at all" "$T/err"; then echo "  ok    $shell: the block says the digest is missing, not that a test changed"; else echo "  FAIL  $shell: the missing-digest block does not say why"; fails=$((fails+1)); fi
  # and a brief with no baseline at all is still the ordinary no-task case, not a refusal
  git -C "$R" reset -q --hard "$init"; rm -rf "$R/working"
  mkdir -p "$R/working/plain"; printf '# brief with no seal
' > "$R/working/plain/brief.md"
  mkdir -p "$R/working/active-tasks"; printf 'working/plain/brief.md
' > "$R/working/active-tasks/$SIDA"
  case_ "$shell: an unsealed brief falls back to HEAD, no refusal" 0 "$(run $shell verify-on-finish "$p_stop")"

  # A test added during the task, weakened, and then RENAMED: git log with one pathspec calls the
  # rename commit the add, so without following the rename the weakened file becomes its own base.
  git -C "$R" reset -q --hard "$init"; rm -rf "$R/working"
  seal_ task-1
  printf 'describe("r", () => {
  test("one", () => {
    expect(1).toBe(1);
  });
  test("two", () => {
    expect(2).toBe(2);
    expect(3).toBe(3);
  });
});
' > "$R/tests/r.test.js"
  git -C "$R" add -A; gitc commit -qm add-r 2>/dev/null
  printf 'describe("r", () => {
  test("one", () => {
    expect(1).toBe(1);
  });
});
' > "$R/tests/r.test.js"
  gitc commit -qam weaken-r 2>/dev/null
  git -C "$R" mv tests/r.test.js tests/r2.test.js; gitc commit -qm rename-r 2>/dev/null
  case_ "$shell: added test weakened then renamed still blocked" 2 "$(run $shell verify-on-finish "$p_stop")"
  total=$((total+1)); if grep -q "then renamed" "$T/err"; then echo "  ok    $shell: the block names the rename it followed"; else echo "  FAIL  $shell: the rename was not followed"; fails=$((fails+1)); fi

  # A tab after the colon must not quietly disarm the baseline: the digest trims, so the lookup must
  # trim too, or the hook silently falls back to HEAD on a brief whose seal still verifies.
  git -C "$R" reset -q --hard "$init"; rm -rf "$R/working"
  seal_ task-1
  weaken_commit
  awk '{ sub(/^baseline_commit\.repo: /, "baseline_commit.repo:	"); print }' "$R/working/task-1/brief.md" > "$T/tab" && mv "$T/tab" "$R/working/task-1/brief.md"
  case_ "$shell: a tab after the colon still finds the baseline" 2 "$(run $shell verify-on-finish "$p_stop")"
  total=$((total+1)); if grep -q "since the task baseline" "$T/err"; then echo "  ok    $shell: the tabbed baseline was used, not skipped"; else echo "  FAIL  $shell: the tabbed baseline was skipped and the hook fell back"; fails=$((fails+1)); fi
  # Case 3: two sessions, one checkout. Session A sealed before the weakening, session B after it.
  # A must block and B must not, and neither may read the other's brief.
  git -C "$R" reset -q --hard "$init"; rm -rf "$R/working"
  seal_ task-a "$SIDA"
  weaken_commit
  seal_ task-b "$SIDB"
  p_a='{"cwd":"'"$cwdv"'","session_id":"'"$SIDA"'","stop_hook_active":false}'
  p_b='{"cwd":"'"$cwdv"'","session_id":"'"$SIDB"'","stop_hook_active":false}'
  case_ "$shell: session A blocks on its own baseline"  2 "$(run $shell verify-on-finish "$p_a")"
  total=$((total+1)); if grep -q "working/task-a/brief.md" "$T/err" && ! grep -q "task-b" "$T/err"; then echo "  ok    $shell: session A measured only its own task"; else echo "  FAIL  $shell: session A read the wrong brief"; fails=$((fails+1)); fi
  case_ "$shell: session B allows, sealed after the weakening" 0 "$(run $shell verify-on-finish "$p_b")"
  # and B is not merely quiet: a weakening after B's own baseline must block B, naming B's brief
  printf 'test("a", () => {});\n' > "$R/tests/x.test.js"
  case_ "$shell: session B blocks on its own baseline"  2 "$(run $shell verify-on-finish "$p_b")"
  total=$((total+1)); if grep -q "working/task-b/brief.md" "$T/err" && ! grep -q "task-a" "$T/err"; then echo "  ok    $shell: session B measured only its own task"; else echo "  FAIL  $shell: session B read the wrong brief"; fails=$((fails+1)); fi
  git -C "$R" checkout -q -- tests/x.test.js
  git -C "$R" reset -q --hard "$init"; rm -rf "$R/working"
  seal_ task-1
  # a rewritten baseline: the task branch is rebased, so the sealed commit is gone; the merge-base is used
  git -C "$R" reset -q --hard "$init"; git -C "$R" checkout -q -b "feat-$shell"
  printf 'f1\n' > "$R/f1.txt"; git -C "$R" add -A; gitc commit -qm f1 2>/dev/null
  seal_ task-1
  weaken_commit
  git -C "$R" checkout -q "$trunk"; printf 'm1\n' > "$R/m1.txt"; git -C "$R" add -A; gitc commit -qm m1 2>/dev/null
  git -C "$R" checkout -q "feat-$shell"; gitc rebase -q "$trunk" >/dev/null 2>&1
  case_ "$shell: rebased task branch compared from the merge-base" 2 "$(run $shell verify-on-finish "$p_stop")"
  total=$((total+1)); if grep -q "merge-base" "$T/out"; then echo "  ok    $shell: the rewritten baseline is announced"; else echo "  FAIL  $shell: no merge-base note"; fails=$((fails+1)); fi
  git -C "$R" checkout -q "$trunk"; git -C "$R" branch -q -D "feat-$shell"; git -C "$R" reset -q --hard "$init"
  # Case 6: no pointer at all. Back to HEAD, so a committed weakening is invisible again: the
  # documented limit, not a guess at which brief is active.
  seal_ task-1
  weaken_commit
  rm -rf "$R/working/active-tasks"
  case_ "$shell: no pointer falls back to HEAD"          0 "$(run $shell verify-on-finish "$p_stop")"
  # Case 5: the pointer names a task that is gone
  mkdir -p "$R/working/active-tasks"; printf 'working/gone/brief.md\n' > "$R/working/active-tasks/$SIDA"
  case_ "$shell: stale pointer falls back to HEAD"       0 "$(run $shell verify-on-finish "$p_stop")"
  total=$((total+1)); if grep -q "does not resolve" "$T/out"; then echo "  ok    $shell: the stale pointer is announced"; else echo "  FAIL  $shell: no stale-pointer note"; fails=$((fails+1)); fi
  # Case 7: the pointer names a nested brief, and then a path outside the project. Both are refused
  # by shape. Both decoys are SEALED at the baseline, so a hook that followed either would find the
  # committed weakening and block: only the shape check keeps these at exit 0.
  mkdir -p "$R/working/nested/task-1" "$T/outside"
  printf -- '---\nbaseline_commit.repo: %s\n---\n# nested\n' "$init" > "$R/working/nested/task-1/brief.md"
  printf -- '---\nbaseline_commit.repo: %s\n---\n# outside\n' "$init" > "$T/outside/brief.md"
  printf 'working/nested/task-1/brief.md\n' > "$R/working/active-tasks/$SIDA"
  case_ "$shell: a nested path is refused as the active task" 0 "$(run $shell verify-on-finish "$p_stop")"
  total=$((total+1)); if grep -q "does not resolve" "$T/out"; then echo "  ok    $shell: the nested path is refused, not merely unusable"; else echo "  FAIL  $shell: the nested path was followed"; fails=$((fails+1)); fi
  printf '../outside/brief.md\n' > "$R/working/active-tasks/$SIDA"
  case_ "$shell: a path outside the project is refused"  0 "$(run $shell verify-on-finish "$p_stop")"
  total=$((total+1)); if grep -q "does not resolve" "$T/out"; then echo "  ok    $shell: the traversal is refused by shape, not by absence"; else echo "  FAIL  $shell: the traversal was followed"; fails=$((fails+1)); fi
  # A baseline commit that does not exist HERE: HEAD again, with a note. The brief is sealed in
  # another checkout of the same name and carried in, which is how this really happens; editing the
  # commit by hand would now be tampering, and would block instead of falling back.
  git -C "$R" reset -q --hard "$init"; rm -rf "$R/working"; mkdir -p "$R/working/active-tasks"
  O="$T/elsewhere/repo"; rm -rf "$T/elsewhere"; mkdir -p "$O/tests"
  git -C "$O" init -q; git -C "$O" config core.autocrlf false
  printf 'working/\n' > "$O/.gitignore"; printf 'test("o", () => { expect(1).toBe(1); });\n' > "$O/tests/o.test.js"
  git -C "$O" add -A; git -C "$O" -c user.email=t@t -c user.name=t commit -qm elsewhere 2>/dev/null
  mkdir -p "$O/working/task-1"; printf '# brief task-1\n' > "$O/working/task-1/brief.md"
  (cd "$O" && CLAUDE_CODE_SESSION_ID="$SIDA" bash "$HERE/baseline.sh" seal task-1 2 >/dev/null 2>&1)
  mkdir -p "$R/working/task-1"; cp "$O/working/task-1/brief.md" "$R/working/task-1/brief.md"
  printf 'working/task-1/brief.md\n' > "$R/working/active-tasks/$SIDA"
  case_ "$shell: nonexistent baseline commit falls back to HEAD" 0 "$(run $shell verify-on-finish "$p_stop")"
  total=$((total+1)); if grep -q "does not exist" "$T/out"; then echo "  ok    $shell: the fallback is announced"; else echo "  FAIL  $shell: no fallback note"; fails=$((fails+1)); fi
  rm -rf "$R/working/nested"
done
git -C "$R" reset -q --hard "$init"; rm -rf "$R/working"

echo "baseline.sh"
mkdir -p "$R/working/task-2"; printf -- '---\nowner: someone\n---\n\n# brief\n' > "$R/working/task-2/brief.md"; printf 'wip\n' > "$R/owner-wip.txt"
(cd "$R" && bash "$HERE/baseline.sh" seal task-2 2 >/dev/null 2>&1)
total=$((total+1)); if grep -q "owner-wip.txt" "$R/working/task-2/pre-existing.txt" && grep -q '^pre_existing: 1$' "$R/working/task-2/brief.md"; then echo "  ok    seal records a pre-existing untracked file"; else echo "  FAIL  seal missed the pre-existing file"; fails=$((fails+1)); fi
total=$((total+1)); if grep -q '^owner: someone$' "$R/working/task-2/brief.md"; then echo "  ok    seal keeps front matter the brief already had"; else echo "  FAIL  seal dropped existing front matter"; fails=$((fails+1)); fi
(cd "$R" && bash "$HERE/baseline.sh" seal task-2 2 >"$T/reseal.out" 2>&1); rc=$?
total=$((total+1)); if [ "$rc" -ne 0 ] && grep -q "does not move" "$T/reseal.out"; then echo "  ok    seal refuses to re-seal a sealed brief"; else echo "  FAIL  seal re-sealed a sealed brief"; fails=$((fails+1)); fi
# A seal must not be movable by making the brief look unsealed. Two routes: a byte before the fence,
# which stops the front matter parsing, and deleting the approval lines outright.
printf '\n' > "$T/pad"; cat "$R/working/task-2/brief.md" >> "$T/pad"; cp "$T/pad" "$R/working/task-2/brief.md"
(cd "$R" && CLAUDE_CODE_SESSION_ID="$SIDA" bash "$HERE/baseline.sh" seal task-2 2 >"$T/reseal2.out" 2>&1); rc=$?
total=$((total+1)); if [ "$rc" -ne 0 ] && grep -q "front matter cannot be read" "$T/reseal2.out"; then echo "  ok    seal refuses a sealed brief whose fence was moved"; else echo "  FAIL  a blank line before the fence allowed a re-seal"; fails=$((fails+1)); fi
grep -v -E '^(task|approved_at|tier|baseline_commit|brief_sha256|pre_existing|seal_sha256|---):?' "$R/working/task-2/brief.md" > "$T/stripped" && cp "$T/stripped" "$R/working/task-2/brief.md"
(cd "$R" && CLAUDE_CODE_SESSION_ID="$SIDA" bash "$HERE/baseline.sh" seal task-2 2 >"$T/reseal3.out" 2>&1); rc=$?
total=$((total+1)); if [ "$rc" -ne 0 ] && grep -q "sealed once already" "$T/reseal3.out"; then echo "  ok    seal refuses a brief whose approval was stripped out"; else echo "  FAIL  stripping the approval allowed a re-seal"; fails=$((fails+1)); fi
# and starting the task over properly, by removing the folder, is still allowed
rm -rf "$R/working/task-2"; mkdir -p "$R/working/task-2"; printf '# brief task-2 again\n' > "$R/working/task-2/brief.md"
(cd "$R" && CLAUDE_CODE_SESSION_ID="$SIDA" bash "$HERE/baseline.sh" seal task-2 2 >"$T/reseal4.out" 2>&1); rc=$?
total=$((total+1)); if [ "$rc" -eq 0 ]; then echo "  ok    removing the task folder allows the task to be agreed again"; else echo "  FAIL  a genuinely new agreement was refused"; fails=$((fails+1)); cat "$T/reseal4.out"; fi
(cd "$R" && bash "$HERE/baseline.sh" check task-2 >/dev/null 2>&1); rc=$?
total=$((total+1)); if [ "$rc" -eq 0 ]; then echo "  ok    check passes on an unchanged brief"; else echo "  FAIL  check failed on an unchanged brief"; fails=$((fails+1)); fi
printf 'changed after approval\n' >> "$R/working/task-2/brief.md"
(cd "$R" && bash "$HERE/baseline.sh" check task-2 >"$T/check.out" 2>&1); rc=$?
total=$((total+1)); if [ "$rc" -ne 0 ] && grep -q "BRIEF CHANGED" "$T/check.out"; then echo "  ok    check detects a brief changed after approval"; else echo "  FAIL  check missed a changed brief"; fails=$((fails+1)); fi
rm -f "$R/owner-wip.txt"

echo "the Tier 3 review contract"
# A Tier 3 task is done when one independent review completed, or when the owner waived it out
# loud. Offered, selected, started, and failed are none of those. check is the point where that is
# decided, because it already runs at hand-back. Tier 1 and 2 are untouched.
tcase() { total=$((total+1)); if [ "$2" = 1 ]; then echo "  ok    $1"; else echo "  FAIL  $1"; fails=$((fails+1)); fi; }
mkt() { rm -rf "$R/working/$1"; mkdir -p "$R/working/$1"; printf '# brief %s\n' "$1" > "$R/working/$1/brief.md"; (cd "$R" && CLAUDE_CODE_SESSION_ID="$SIDA" bash "$HERE/baseline.sh" seal "$1" "$2" >/dev/null 2>&1); }
bl() { (cd "$R" && CLAUDE_CODE_SESSION_ID="$SIDA" bash "$HERE/baseline.sh" "$@" >"$T/bl.out" 2>&1); }
mkdir -p "$R/working/no-tier"; printf '# brief\n' > "$R/working/no-tier/brief.md"
(cd "$R" && bash "$HERE/baseline.sh" seal no-tier >"$T/bl.out" 2>&1); rc=$?
tcase "seal refuses a task with no tier" "$( { [ "$rc" -ne 0 ] && grep -q 'needs the tier' "$T/bl.out"; } && echo 1 || echo 0)"
# A brief that arrives at the agreement already carrying its own review record must not keep it:
# that is the one way a builder could turn "no review" into "waived" without anyone saying so.
rm -rf "$R/working/preload"; mkdir -p "$R/working/preload"
printf -- '---\nreview_status: waived-by-owner\nreview_waiver: nobody said this\n---\n# brief\n' > "$R/working/preload/brief.md"
(cd "$R" && CLAUDE_CODE_SESSION_ID="$SIDA" bash "$HERE/baseline.sh" seal preload 3 >/dev/null 2>&1)
bl check preload; rc=$?
tcase "seal strips a review record the brief arrived with" "$( { [ "$rc" -ne 0 ] && grep -q 'TIER 3 CONTRACT INCOMPLETE' "$T/bl.out"; } && echo 1 || echo 0)"
# A brief with no tier line cannot have its contract checked, and that is not a pass
mkt notier 3; awk '!/^tier: /' "$R/working/notier/brief.md" > "$T/nt.tmp" && mv "$T/nt.tmp" "$R/working/notier/brief.md"
bl check notier; rc=$?
tcase "a brief with no tier fails the check rather than passing" "$( { [ "$rc" -ne 0 ] && grep -q 'TIER NOT RECORDED' "$T/bl.out"; } && echo 1 || echo 0)"
# Only the two review routes this harness treats as independent are accepted
mkt route 3; bl review route completed my-own-eyeballs "looked at it"; rc=$?
tcase "an unknown review route is refused"             "$( { [ "$rc" -ne 0 ] && grep -q 'unknown review route' "$T/bl.out"; } && echo 1 || echo 0)"
# Case 3: neither review nor waiver. The contract is not silently satisfied by reaching hand-back.
mkt t3a 3; bl check t3a; rc=$?
tcase "tier 3 with neither review nor waiver fails the hand-back check" "$( { [ "$rc" -ne 0 ] && grep -q 'TIER 3 CONTRACT INCOMPLETE' "$T/bl.out"; } && echo 1 || echo 0)"
# Case 5 and 6: a review that was only offered, or that failed, leaves nothing to record
bl review t3a completed code-review; rc=$?
tcase "a completed review with no result is refused"  "$( { [ "$rc" -ne 0 ] && grep -q 'carries its result' "$T/bl.out"; } && echo 1 || echo 0)"
bl review t3a completed test-guide "walked the steps"; rc=$?
tcase "the local run is refused as an independent review" "$( { [ "$rc" -ne 0 ] && grep -q 'not an independent review' "$T/bl.out"; } && echo 1 || echo 0)"
bl review t3a waived; rc=$?
tcase "a waiver with no owner words is refused"        "$( { [ "$rc" -ne 0 ] && grep -q "owner's own words" "$T/bl.out"; } && echo 1 || echo 0)"
# Case 1: a completed independent review satisfies it
bl review t3a completed second-model "no findings"; bl check t3a; rc=$?
tcase "tier 3 with a completed review passes"          "$( { [ "$rc" -eq 0 ] && grep -q 'independent review completed via second-model' "$T/bl.out"; } && echo 1 || echo 0)"
bl review t3a waived "the owner said skip it"; rc=$?
tcase "the review record does not move once written"   "$( { [ "$rc" -ne 0 ] && grep -q 'already records' "$T/bl.out"; } && echo 1 || echo 0)"
# Case 2: an explicit waiver satisfies it, and reads differently from a review
mkt t3b 3; bl review t3b waived "owner: skip review, I have read it myself"; bl check t3b; rc=$?
tcase "tier 3 waived by the owner passes and says so"  "$( { [ "$rc" -eq 0 ] && grep -q 'WAIVED by the owner' "$T/bl.out"; } && echo 1 || echo 0)"
# Case 4: lower tiers are untouched
mkt t2 2; bl check t2; rc=$?
tcase "tier 2 with no review still passes"             "$( { [ "$rc" -eq 0 ] && grep -q 'no independent review is required' "$T/bl.out"; } && echo 1 || echo 0)"
mkt t1 1; bl check t1; rc=$?
tcase "tier 1 with no review still passes"             "$( [ "$rc" -eq 0 ] && echo 1 || echo 0)"
rm -rf "$R/working/t3a" "$R/working/t3b" "$R/working/t2" "$R/working/t1" "$R/working/no-tier" "$R/working/preload" "$R/working/notier" "$R/working/route"

# ---- D: a completed review covers the commit it read ---------------------------------------
# Freshness, not provenance. A review of commit A does not cover commit B, so a task whose code
# moved after the review is not reviewed for the purpose of handing it back.
gitb() { git -C "$R" -c user.email=t@t -c user.name=t "$@"; }
mkt fresh 3
bl review fresh completed code-review "no findings"; rc=$?
tcase "a completed review records the commit it read" "$( { [ "$rc" -eq 0 ] && grep -q '^review_commit\.' "$R/working/fresh/brief.md"; } && echo 1 || echo 0)"
bl check fresh; rc=$?
tcase "tier 3 passes while the code is still the reviewed commit" "$( { [ "$rc" -eq 0 ] && grep -q 'still matches the reviewed commit' "$T/bl.out"; } && echo 1 || echo 0)"
printf 'moved after the review\n' > "$R/after-review.txt"; gitb add -A >/dev/null 2>&1; gitb commit -qm after-review >/dev/null 2>&1
bl check fresh; rc=$?
tcase "tier 3 fails once the code has moved past the review" "$( { [ "$rc" -ne 0 ] && grep -q 'REVIEW IS STALE' "$T/bl.out"; } && echo 1 || echo 0)"
bl review fresh completed code-review "PASS again, at the new commit"; rc=$?
tcase "a second review is allowed once the code has moved" "$( [ "$rc" -eq 0 ] && echo 1 || echo 0)"
bl check fresh; rc=$?
tcase "and tier 3 passes again on the fresh review" "$( [ "$rc" -eq 0 ] && echo 1 || echo 0)"
bl review fresh completed code-review "a third, at the same commit"; rc=$?
tcase "a second review of the same commit is refused" "$( { [ "$rc" -ne 0 ] && grep -q 'completed review of this exact code' "$T/bl.out"; } && echo 1 || echo 0)"
bl review fresh waived "never mind"; rc=$?
tcase "a waiver cannot overwrite a recorded review" "$( { [ "$rc" -ne 0 ] && grep -q 'not waived afterwards' "$T/bl.out"; } && echo 1 || echo 0)"
bl check fresh; rc=$?
tcase "the seal still verifies after the review rewrites" "$( grep -q 'seal intact' "$T/bl.out" && echo 1 || echo 0)"
# a waiver still stands on its own, and is not replaced by a review
mkt waive3 3
bl review waive3 waived "the owner said skip it, this is a docs-only change"; rc=$?
tcase "a waiver is recorded"                          "$( [ "$rc" -eq 0 ] && echo 1 || echo 0)"
bl review waive3 completed code-review "PASS"; rc=$?
tcase "a review cannot overwrite the owner's waiver"  "$( { [ "$rc" -ne 0 ] && grep -q 'does not move' "$T/bl.out"; } && echo 1 || echo 0)"

echo "resume-brief"
# The brief a session gets back after a compaction is the one it was carrying, read from the
# pointer baseline.sh wrote at the owner's yes. The case this guards: a later brief under working/
# (a nested one in these fixtures) is newer than the agreed one, and a recency rule would restore
# it and call it the agreement. Every case here fires the hook and reads what it printed.
W="$T/ws"; mkdir -p "$W/working"
git -C "$W" init -q; git -C "$W" config core.autocrlf false
printf 'working/\n' > "$W/.gitignore"; printf 'x\n' > "$W/file.txt"
git -C "$W" add -A && git -C "$W" -c user.email=t@t -c user.name=t commit -qm init 2>/dev/null
printf '# status\nlast session: hooks tested\n' > "$W/working/status.md"
mk_brief()  { mkdir -p "$W/working/$1"; printf '# brief\nMARKER-%s survives compaction\n' "$1" > "$W/working/$1/brief.md"; }
seal_w()    { (cd "$W" && CLAUDE_CODE_SESSION_ID="$2" bash "$HERE/baseline.sh" seal "$1" "${3:-2}" >/dev/null 2>&1); }
said()      { grep -q "$1" "$T/out"; }
check_()    { total=$((total+1)); if [ "$2" = 1 ]; then echo "  ok    $1"; else echo "  FAIL  $1"; fails=$((fails+1)); fi; }
# A nested brief and an unrelated task brief, both dated 2030, so recency would prefer either over
# the agreed one. The nested brief is the strictly newer of the two, so a fallback that searched
# one level deeper would pick it and the case would go red.
mkdir -p "$W/working/nested/task-1"; printf '# nested\nMARKER-nested must never be restored\n' > "$W/working/nested/task-1/brief.md"
mk_brief task-other
mkdir -p "$T/outside"; printf '# outside\nMARKER-outside must never be restored\n' > "$T/outside/brief.md"
touch -t 203001010000 "$W/working/task-other/brief.md"
touch -t 203001010100 "$W/working/nested/task-1/brief.md"
mk_brief task-1; mk_brief task-2
seal_w task-1 "$SIDA"; seal_w task-2 "$SIDB"
for shell in $shells; do
  if [ "$shell" = ps1 ]; then cwdv="$(winpath "$W")"; else cwdv="$W"; fi
  p_a='{"cwd":"'"$cwdv"'","session_id":"'"$SIDA"'","source":"compact"}'
  p_b='{"cwd":"'"$cwdv"'","session_id":"'"$SIDB"'","source":"compact"}'
  # Case 1 and 4: the pointer wins over every newer brief, nested or not
  run $shell resume-brief "$p_a" >/dev/null
  check_ "$shell: status and the session's own brief printed after compaction" "$( { said 'hooks tested' && said 'MARKER-task-1'; } && echo 1 || echo 0)"
  check_ "$shell: the nested brief is never restored"                          "$( { said 'MARKER-task-1' && ! said 'MARKER-nested'; } && echo 1 || echo 0)"
  check_ "$shell: a newer unrelated brief does not win over the pointer"       "$( { said 'MARKER-task-1' && ! said 'MARKER-task-other'; } && echo 1 || echo 0)"
  check_ "$shell: the restored brief is named as this session's agreement"     "$( said 'carrying' && echo 1 || echo 0)"
  # Case 2: two sessions, one checkout
  run $shell resume-brief "$p_b" >/dev/null
  check_ "$shell: the other session gets its own brief"                        "$( { said 'MARKER-task-2' && ! said 'MARKER-task-1'; } && echo 1 || echo 0)"
  # Case 8: the same session agrees another task; the new seal replaces the pointer. A fresh task
  # each pass, because a sealed brief cannot be sealed again.
  mk_brief "next-$shell"; seal_w "next-$shell" "$SIDA"
  run $shell resume-brief "$p_a" >/dev/null
  check_ "$shell: a new agreement moves this session to the new task"          "$( { said "MARKER-next-$shell" && ! said 'MARKER-task-1'; } && echo 1 || echo 0)"
  # Case 7: a nested path and a path outside the project are both refused
  printf 'working/nested/task-1/brief.md\n' > "$W/working/active-tasks/$SIDA"
  run $shell resume-brief "$p_a" >/dev/null
  check_ "$shell: a nested pointer is refused and announced as a guess"        "$( { ! said 'MARKER-nested' && said 'guess'; } && echo 1 || echo 0)"
  # the traversal target exists, so only the shape check can refuse it
  printf '../outside/brief.md\n' > "$W/working/active-tasks/$SIDA"
  run $shell resume-brief "$p_a" >/dev/null
  check_ "$shell: a pointer outside the project is refused"                    "$( { said 'MARKER-task-other' && ! said 'MARKER-outside'; } && echo 1 || echo 0)"
  # Case 5: the pointer names a task that is gone
  printf 'working/gone/brief.md\n' > "$W/working/active-tasks/$SIDA"
  run $shell resume-brief "$p_a" >/dev/null
  check_ "$shell: a stale pointer says so and falls back"                      "$( said 'cannot be restored' && echo 1 || echo 0)"
  # Case 6: no pointer at all. The newest TASK brief, never the nested one, and named as a guess.
  rm -f "$W/working/active-tasks/$SIDA"
  run $shell resume-brief "$p_a" >/dev/null
  check_ "$shell: with no pointer the newest task brief is restored"           "$( said 'MARKER-task-other' && echo 1 || echo 0)"
  check_ "$shell: the fallback never restores the nested brief"                "$( { said 'MARKER-task-other' && ! said 'MARKER-nested'; } && echo 1 || echo 0)"
  check_ "$shell: the fallback is named as a guess"                            "$( said 'guess' && echo 1 || echo 0)"
  printf 'working/task-1/brief.md\n' > "$W/working/active-tasks/$SIDA"
done

# ---- the test-file shapes the matcher claims to recognise ---------------------------------------
# is_test_file has four branches. Every other test file this suite creates is a .test.js inside a
# tests/ folder, so without this block three branches would be carried by no case at all. Each
# fixture below matches exactly one branch and no other, so a branch that stops working takes its
# own case down with it and nothing else.
echo "test-file shapes"
TS="$T/shapes"; mkdir -p "$TS/src" "$TS/tests"
git -C "$TS" init -q 2>/dev/null
git -C "$TS" config core.autocrlf false
gits() { git -C "$TS" -c user.email=t@t -c user.name=t "$@"; }
printf 'working/\n' > "$TS/.gitignore"
# .spec. only: not .test., not under tests/, not a test_*.py
printf 'describe("s", () => {\n  it("a", () => { expect(1).toBe(1); });\n  it("b", () => { expect(2).toBe(2); });\n  it("c", () => { expect(3).toBe(3); });\n});\n' > "$TS/src/thing.spec.js"
# test_*.py only: not .test., not .spec., not under tests/
printf 'def test_widget_a():\n    assert 10 == 10\n\ndef test_widget_b():\n    assert 20 == 20\n\ndef test_widget_c():\n    assert 30 == 30\n' > "$TS/src/test_widget.py"
# the tests/ folder only: no .test., no .spec., no test_ prefix in the name
printf 'def test_a():\n    assert 1 == 1\n\ndef test_b():\n    assert 2 == 2\n\ndef test_c():\n    assert 3 == 3\n' > "$TS/tests/check_things.py"
gits add -A >/dev/null 2>&1; gits commit -qm shapes >/dev/null 2>&1

# the fixtures must each match one branch and only one, or a case could pass on the wrong branch
for pair in "src/thing.spec.js:spec" "src/test_widget.py:py" "tests/check_things.py:folder"; do
  f="${pair%%:*}"
  total=$((total+1))
  hits=0
  printf '%s' "$f" | grep -Eiq '\.test\.'            && hits=$((hits+1))
  printf '%s' "$f" | grep -Eiq '\.spec\.'            && hits=$((hits+1))
  printf '%s' "$f" | grep -Eiq '(^|/)test_[^/]*\.py$' && hits=$((hits+1))
  printf '%s' "$f" | grep -Eiq '(^|/)(tests?|__tests__)/' && hits=$((hits+1))
  if [ "$hits" -eq 1 ]; then echo "  ok    fixture: $f matches exactly one branch of is_test_file"
  else echo "  FAIL  fixture: $f matches $hits branches, so its case cannot name which one broke"; fails=$((fails+1)); fi
done

mkdir -p "$TS/working/shape-task"
printf '# brief shape-task\noutcome: tests stay whole\n' > "$TS/working/shape-task/brief.md"
(cd "$TS" && CLAUDE_CODE_SESSION_ID="$SIDA" bash "$HERE/baseline.sh" seal shape-task 2 >"$T/shapes.seal" 2>&1)
total=$((total+1))
if grep -q '^baseline_commit\.' "$TS/working/shape-task/brief.md"; then echo "  ok    the shapes fixture sealed"
else echo "  FAIL  the shapes fixture did not seal"; fails=$((fails+1)); sed 's/^/        /' "$T/shapes.seal"; fi

# one assertion removed from each, committed, so only the baseline comparison can see it
printf 'describe("s", () => {\n  it("a", () => { expect(1).toBe(1); });\n  it("b", () => { expect(2).toBe(2); });\n});\n' > "$TS/src/thing.spec.js"
printf 'def test_widget_a():\n    assert 10 == 10\n\ndef test_widget_b():\n    assert 20 == 20\n' > "$TS/src/test_widget.py"
printf 'def test_a():\n    assert 1 == 1\n\ndef test_b():\n    assert 2 == 2\n' > "$TS/tests/check_things.py"
gits commit -qam weaken-all >/dev/null 2>&1

for shell in $shells; do
  if [ "$shell" = ps1 ]; then scwd="$(winpath "$TS")"; else scwd="$TS"; fi
  p_shapes='{"cwd":"'"$scwd"'","session_id":"'"$SIDA"'","stop_hook_active":false}'
  case_ "$shell: a weakening in all three shapes blocks"  2 "$(run $shell verify-on-finish "$p_shapes")"
  for pair in "thing.spec.js:.spec. branch" "test_widget.py:test_*.py branch" "check_things.py:tests/ folder branch"; do
    f="${pair%%:*}"; label="${pair#*:}"
    total=$((total+1))
    if grep -q "$f" "$T/err"; then echo "  ok    $shell: the block names $f, so the $label works"
    else echo "  FAIL  $shell: the block never names $f, so the $label is not carried by any case"; fails=$((fails+1)); fi
  done
done

# ---- linked git worktrees ----------------------------------------------------------------------
# A linked worktree carries a .git FILE, not a directory. Detecting a checkout by testing for a
# directory would make every worktree invisible: seal would refuse to run, and the Stop hook would
# exit 0 on a weakened committed test, which is the silent version of no protection at all. A real
# worktree is created here; simulating one by writing a .git file would test the fixture, not git.
echo "linked git worktrees"
WT="$T/wtmain"; mkdir -p "$WT/tests"
git -C "$WT" init -q 2>/dev/null
git -C "$WT" config core.autocrlf false
printf 'working/\n' > "$WT/.gitignore"
printf 'describe("w", () => {\n  test("one", () => {\n    expect(1).toBe(1);\n  });\n  test("two", () => {\n    expect(2).toBe(2);\n    expect(3).toBe(3);\n  });\n});\n' > "$WT/tests/w.test.js"
git -C "$WT" -c user.email=t@t -c user.name=t add -A >/dev/null 2>&1
git -C "$WT" -c user.email=t@t -c user.name=t commit -qm init >/dev/null 2>&1
if git -C "$WT" -c user.email=t@t -c user.name=t worktree add -q "$T/wtlinked" -b wt-feature >/dev/null 2>&1; then
  L="$T/wtlinked"
  total=$((total+1))
  if [ -f "$L/.git" ] && [ ! -d "$L/.git" ]; then echo "  ok    the linked worktree carries a .git file, not a directory"
  else echo "  FAIL  the fixture is not a real linked worktree"; fails=$((fails+1)); fi
  mkdir -p "$L/working/wt-task"; printf '# brief wt-task\n' > "$L/working/wt-task/brief.md"
  (cd "$L" && CLAUDE_CODE_SESSION_ID="$SIDA" bash "$HERE/baseline.sh" seal wt-task 2 >"$T/wtseal.out" 2>&1); rc=$?
  total=$((total+1))
  if [ "$rc" -eq 0 ] && grep -q '^baseline_commit\.' "$L/working/wt-task/brief.md"; then echo "  ok    baseline.sh seals inside a linked worktree"
  else echo "  FAIL  baseline.sh could not seal inside a linked worktree"; fails=$((fails+1)); sed 's/^/        /' "$T/wtseal.out"; fi
  printf 'describe("w", () => {\n  test("one", () => {\n    expect(1).toBe(1);\n  });\n});\n' > "$L/tests/w.test.js"
  git -C "$L" -c user.email=t@t -c user.name=t commit -qam weaken >/dev/null 2>&1
  for shell in $shells; do
    if [ "$shell" = ps1 ]; then wcwd="$(winpath "$L")"; else wcwd="$L"; fi
    p_wt='{"cwd":"'"$wcwd"'","session_id":"'"$SIDA"'","stop_hook_active":false}'
    case_ "$shell: a weakened committed test in a worktree blocks" 2 "$(run $shell verify-on-finish "$p_wt")"
    total=$((total+1)); if grep -q "since the task baseline" "$T/err"; then echo "  ok    $shell: the worktree block names the task baseline"; else echo "  FAIL  $shell: the worktree block does not name the baseline"; fails=$((fails+1)); fi
  done
  # A: a linked worktree starts with no working/ at all, because everything there is ignored. The
  # tools must fall back rather than invent shared state, and nothing may be copied between them.
  L2="$T/wtfresh"
  if git -C "$WT" -c user.email=t@t -c user.name=t worktree add -q "$L2" -b wt-fresh >/dev/null 2>&1; then
    total=$((total+1))
    if [ ! -d "$L2/working" ]; then echo "  ok    a fresh worktree carries no working/ state"
    else echo "  FAIL  working/ appeared in a fresh worktree"; fails=$((fails+1)); fi
    for shell in $shells; do
      if [ "$shell" = ps1 ]; then fcwd="$(winpath "$L2")"; else fcwd="$L2"; fi
      p_fresh='{"cwd":"'"$fcwd"'","session_id":"'"$SIDA"'","stop_hook_active":false}'
      case_ "$shell: a worktree with no working/ falls back, no block" 0 "$(run $shell verify-on-finish "$p_fresh")"
    done
    (cd "$WT" && git worktree remove --force "$L2" >/dev/null 2>&1)
  fi
  (cd "$WT" && git worktree remove --force "$L" >/dev/null 2>&1)
else
  echo "  ----  git worktree add failed here; the worktree cases did not run"
fi

# ---- C: one exact test change the owner authorized ----------------------------------------------
# Not a waiver and not a switch. Keyed on the file AND the sha256 of the content it ends at, so it
# covers that change and nothing after it, and nothing on any other file.
echo "an owner-authorized test change"
AU="$T/authz"; mkdir -p "$AU/tests"
git -C "$AU" init -q 2>/dev/null; git -C "$AU" config core.autocrlf false
printf 'working/\n' > "$AU/.gitignore"
printf 'test("a", () => { expect(1).toBe(1); expect(2).toBe(2); expect(3).toBe(3); });\n' > "$AU/tests/a.test.js"
printf 'test("b", () => { expect(1).toBe(1); expect(2).toBe(2); });\n' > "$AU/tests/b.test.js"
git -C "$AU" -c user.email=t@t -c user.name=t add -A >/dev/null 2>&1
git -C "$AU" -c user.email=t@t -c user.name=t commit -qm init >/dev/null 2>&1
mkdir -p "$AU/working/az"; printf '# brief az\n' > "$AU/working/az/brief.md"
(cd "$AU" && CLAUDE_CODE_SESSION_ID="$SIDA" bash "$HERE/baseline.sh" seal az 2 >/dev/null 2>&1)
printf 'test("a", () => { expect(1).toBe(1); });\n' > "$AU/tests/a.test.js"
git -C "$AU" -c user.email=t@t -c user.name=t commit -qam weaken-a >/dev/null 2>&1
for shell in $shells; do
  if [ "$shell" = ps1 ]; then acwd="$(winpath "$AU")"; else acwd="$AU"; fi
  p_az='{"cwd":"'"$acwd"'","session_id":"'"$SIDA"'","stop_hook_active":false}'
  case_ "$shell: the weakening blocks before it is authorized" 2 "$(run $shell verify-on-finish "$p_az")"
done
(cd "$AU" && CLAUDE_CODE_SESSION_ID="$SIDA" bash "$HERE/baseline.sh" allow-test-change az authz/tests/a.test.js "the other two cases moved to the integration suite" >"$T/az.out" 2>&1); rc=$?
total=$((total+1)); if [ "$rc" -eq 0 ] && grep -q '^test_change_allowed: ' "$AU/working/az/brief.md"; then echo "  ok    the authorization is recorded in the brief"; else echo "  FAIL  allow-test-change did not record"; fails=$((fails+1)); sed 's/^/        /' "$T/az.out"; fi
for shell in $shells; do
  if [ "$shell" = ps1 ]; then acwd="$(winpath "$AU")"; else acwd="$AU"; fi
  p_az='{"cwd":"'"$acwd"'","session_id":"'"$SIDA"'","stop_hook_active":false}'
  case_ "$shell: the authorized change is allowed"             0 "$(run $shell verify-on-finish "$p_az")"
  total=$((total+1)); if grep -q 'authorized test changes were allowed' "$T/out"; then echo "  ok    $shell: the allowance is said out loud"; else echo "  FAIL  $shell: the allowance is silent"; fails=$((fails+1)); fi
done
# one more edit to the same file, and the authorization no longer matches
printf 'test("a", () => { });\n' > "$AU/tests/a.test.js"
git -C "$AU" -c user.email=t@t -c user.name=t commit -qam weaken-a-more >/dev/null 2>&1
for shell in $shells; do
  if [ "$shell" = ps1 ]; then acwd="$(winpath "$AU")"; else acwd="$AU"; fi
  p_az='{"cwd":"'"$acwd"'","session_id":"'"$SIDA"'","stop_hook_active":false}'
  case_ "$shell: a further weakening of the same file blocks"  2 "$(run $shell verify-on-finish "$p_az")"
done
git -C "$AU" -c user.email=t@t -c user.name=t revert -q --no-edit HEAD >/dev/null 2>&1 || {
  printf 'test("a", () => { expect(1).toBe(1); });\n' > "$AU/tests/a.test.js"
  git -C "$AU" -c user.email=t@t -c user.name=t commit -qam back >/dev/null 2>&1; }
# a different test file is not covered by it
printf 'test("b", () => { expect(1).toBe(1); });\n' > "$AU/tests/b.test.js"
git -C "$AU" -c user.email=t@t -c user.name=t commit -qam weaken-b >/dev/null 2>&1
for shell in $shells; do
  if [ "$shell" = ps1 ]; then acwd="$(winpath "$AU")"; else acwd="$AU"; fi
  p_az='{"cwd":"'"$acwd"'","session_id":"'"$SIDA"'","stop_hook_active":false}'
  case_ "$shell: a different test file is not covered"         2 "$(run $shell verify-on-finish "$p_az")"
  total=$((total+1)); if grep -q 'b.test.js' "$T/err"; then echo "  ok    $shell: the block names the file that was not authorized"; else echo "  FAIL  $shell: the block names the wrong file"; fails=$((fails+1)); fi
done
(cd "$AU" && bash "$HERE/baseline.sh" allow-test-change az authz/tests/b.test.js >"$T/az2.out" 2>&1); rc=$?
total=$((total+1)); if [ "$rc" -ne 0 ] && grep -q "owner's own words" "$T/az2.out"; then echo "  ok    an authorization with no reason is refused"; else echo "  FAIL  an authorization with no reason was accepted"; fails=$((fails+1)); fi
(cd "$AU" && bash "$HERE/baseline.sh" allow-test-change az tests/b.test.js "no checkout named" >"$T/az3.out" 2>&1); rc=$?
total=$((total+1)); if [ "$rc" -ne 0 ]; then echo "  ok    an authorization must name the checkout"; else echo "  FAIL  a path with no checkout was accepted"; fails=$((fails+1)); fi

# ---- Stop must re-check after it has already blocked --------------------------------------------
# stop_hook_active says a Stop hook already blocked this turn. Exiting 0 on it would make the
# second Stop an unconditional pass, so blocking once and carrying on would finish the turn with the
# weakening in place. Loop protection is Claude Code's own consecutive-block limit, not this hook
# giving up.
echo "Stop re-checks after it has blocked"
RC="$T/recheck"; mkdir -p "$RC/tests"
git -C "$RC" init -q 2>/dev/null; git -C "$RC" config core.autocrlf false
printf 'working/\n' > "$RC/.gitignore"
printf 'test("a", () => { expect(1).toBe(1); expect(2).toBe(2); });\n' > "$RC/tests/r.test.js"
git -C "$RC" -c user.email=t@t -c user.name=t add -A >/dev/null 2>&1
git -C "$RC" -c user.email=t@t -c user.name=t commit -qm init >/dev/null 2>&1
mkdir -p "$RC/working/rt"; printf '# brief rt\n' > "$RC/working/rt/brief.md"
(cd "$RC" && CLAUDE_CODE_SESSION_ID="$SIDA" bash "$HERE/baseline.sh" seal rt 2 >/dev/null 2>&1)
printf 'test("a", () => { expect(1).toBe(1); });\n' > "$RC/tests/r.test.js"
git -C "$RC" -c user.email=t@t -c user.name=t commit -qam weaken >/dev/null 2>&1
for shell in $shells; do
  if [ "$shell" = ps1 ]; then rcwd="$(winpath "$RC")"; else rcwd="$RC"; fi
  p_first='{"cwd":"'"$rcwd"'","session_id":"'"$SIDA"'","stop_hook_active":false}'
  p_again='{"cwd":"'"$rcwd"'","session_id":"'"$SIDA"'","stop_hook_active":true}'
  case_ "$shell: the first Stop blocks the weakening"          2 "$(run $shell verify-on-finish "$p_first")"
  case_ "$shell: the second Stop blocks it again"              2 "$(run $shell verify-on-finish "$p_again")"
  printf 'test("a", () => { expect(1).toBe(1); expect(2).toBe(2); });\n' > "$RC/tests/r.test.js"
  git -C "$RC" -c user.email=t@t -c user.name=t commit -qam restore >/dev/null 2>&1
  case_ "$shell: once fixed the second Stop allows the turn"   0 "$(run $shell verify-on-finish "$p_again")"
  printf 'test("a", () => { expect(1).toBe(1); });\n' > "$RC/tests/r.test.js"
  git -C "$RC" -c user.email=t@t -c user.name=t commit -qam weaken-again >/dev/null 2>&1
done

# ---- a seal that cannot be verified fails closed -------------------------------------------------
# An unverifiable seal is the state a moved baseline also produces, so it is not waved through. The
# environment seam exists because no PATH on a Git Bash machine carries coreutils without sha256sum;
# it is the same convention as GUARD_COMMANDS_SELFTEST, which verify.sh uses on guard-commands.
echo "an unverifiable seal fails closed"
printf 'test("a", () => { expect(1).toBe(1); expect(2).toBe(2); });\n' > "$RC/tests/r.test.js"
git -C "$RC" -c user.email=t@t -c user.name=t commit -qam restore2 >/dev/null 2>&1
for shell in $shells; do
  if [ "$shell" = ps1 ]; then rcwd="$(winpath "$RC")"; else rcwd="$RC"; fi
  p_nd='{"cwd":"'"$rcwd"'","session_id":"'"$SIDA"'","stop_hook_active":false}'
  case_ "$shell: a clean sealed task with a working digest passes" 0 "$(run $shell verify-on-finish "$p_nd")"
  got=$(VERIFY_ON_FINISH_NO_DIGEST=1 run $shell verify-on-finish "$p_nd")
  case_ "$shell: a sealed task whose seal cannot be verified blocks" 2 "$got"
  total=$((total+1)); if grep -q "cannot be verified" "$T/err"; then echo "  ok    $shell: the block says the seal could not be verified"; else echo "  FAIL  $shell: the block does not say the seal was unverifiable"; fails=$((fails+1)); fi
  rm -rf "$RC/working/active-tasks"
  got=$(VERIFY_ON_FINISH_NO_DIGEST=1 run $shell verify-on-finish "$p_nd")
  case_ "$shell: with no sealed task an absent digest is not a block" 0 "$got"
  mkdir -p "$RC/working/active-tasks"; printf 'working/rt/brief.md\n' > "$RC/working/active-tasks/$SIDA"
done

echo; echo "  $((total-fails)) passed, $fails failed"
[ "$fails" -eq 0 ]

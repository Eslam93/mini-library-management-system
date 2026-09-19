#!/usr/bin/env bash
# Verification manifest for this repository's working harness.
#
#   bash .claude/tools/verify.sh            the fast checks
#   bash .claude/tools/verify.sh --full     also runs the project's own checks (verify.project.sh)
#   bash .claude/tools/verify.sh --hooks    fires every hook by hand, and runs the knowledge-check
#                                           cases; run after any hook change
#   bash .claude/tools/verify.sh --canary   MUST FAIL. Proves this script can report a failure, and
#                                           that the knowledge checks go red on a broken record
#
# Every check here guards against a known way for a verification run to lie. Traps deliberately
# avoided, each of which can produce a confident PASS over a broken tree:
#   - the script's own directory is resolved to an absolute path BEFORE any cd;
#   - every check confirms its subject exists before testing a property of it, so a check cannot
#     go green by finding nothing;
#   - patterns that may begin with '-' are passed as `grep -E -e "$pat"`;
#   - file sweeps use `git ls-files --cached --others --exclude-standard`, so new files count;
#   - the always-loaded rule budget counts files as well as lines and fails on zero;
#   - the skill-reference sweep fails when it matches nothing, because a broken pattern looks
#     like a clean tree.

set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
cd "$ROOT" || { echo "cannot cd to $ROOT"; exit 1; }

# The budget is a ratchet. Raise it deliberately and record the reason here, never quietly.
#   2026-09-19  BASELINE 400  the general rules, the project rule and the project's own traps fit
#               under it; a raise is a decision, recorded on this line.
BASELINE=400        # always-loaded rule lines: the general rules, the project rule, appended traps
BUILTIN_SKILLS="code-review run goal compact clear memory"   # Claude Code's own commands; referenced, not defined in .claude/skills

PASS=0; FAIL=0
ok()   { printf '  PASS  %s\n' "$1"; PASS=$((PASS+1)); }
bad()  { printf '  FAIL  %s\n        %s\n' "$1" "$2"; FAIL=$((FAIL+1)); }
note() { printf '  ----  %s\n' "$1"; }

mode="${1:-}"
echo "verify.sh  root=$ROOT"
echo

if [ "$mode" = "--canary" ]; then
  # Two things, and the run fails either way so that a green canary stays impossible. First, that
  # the knowledge-integrity check reports a broken record rather than merely existing: a page that
  # is invalid three ways is built here and the real validator is run against it. A canary that only
  # asserted the script is on disk would pass over a validator that had stopped checking anything.
  if [ -f .claude/tools/knowledge-check.sh ]; then
    c="$(mktemp -d 2>/dev/null || mktemp -d -t canary)"
    mkdir -p "$c/docs/knowledge-base"
    printf '%s\n' '---' 'title: A deliberately invalid page' 'status: verified' \
      'as_of: 2026-09-19' 'last_verified: not-a-date' \
      'verification_method: built by verify.sh --canary' 'scope: the canary only' \
      'confidence: High. it is generated' 'reverify_when: never' '---' '' \
      'known_gaps is missing, last_verified is not a date, and this link is dead:' \
      '[gone](../nowhere.md)' > "$c/docs/knowledge-base/broken.md"
    if bash .claude/tools/knowledge-check.sh "$c" >/dev/null 2>&1; then
      bad "knowledge integrity goes red on a broken record" \
          "it passed a page missing a required field, carrying a malformed date, and holding a dead link; the knowledge checks prove nothing"
    else
      ok "knowledge integrity goes red on a broken record (missing field, bad date, dead link)"
    fi
    rm -rf "$c"
  fi
  bad "canary: this check must fail" "if this run reports success, the runner is lying and its greens are void"
  echo; echo "  $PASS passed, $FAIL failed (canary run)"; exit 1
fi

# --- 1 · shape ---------------------------------------------------------------------------------
for d in .claude/rules .claude/skills .claude/hooks .claude/tools; do
  if [ -d "$d" ]; then ok "$d exists"; else bad "$d exists" "missing"; fi
done
[ -f .claude/settings.json ] && ok ".claude/settings.json exists" || bad ".claude/settings.json exists" "no hook is wired"

# --- 2 · settings.json parses ------------------------------------------------------------------
if [ -f .claude/settings.json ]; then
  # A python that resolves on PATH may be the Windows Store stub, which exists and does not run.
  # Test-run each candidate before trusting it, or the check fails on a valid file.
  py=""
  for c in python3 python py; do
    if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys' >/dev/null 2>&1; then py="$c"; break; fi
  done
  if [ -n "$py" ]; then
    if "$py" -c 'import json,sys; json.load(open(".claude/settings.json", encoding="utf-8-sig"))' 2>/dev/null
      then ok "settings.json is valid JSON"; else bad "settings.json is valid JSON" "it does not parse; no hook will load"; fi
  elif command -v node >/dev/null 2>&1; then
    if node -e 'JSON.parse(require("fs").readFileSync(".claude/settings.json","utf8").replace(/^﻿/,""))' 2>/dev/null
      then ok "settings.json is valid JSON"; else bad "settings.json is valid JSON" "it does not parse; no hook will load"; fi
  else
    note "no python or node on PATH; settings.json not parsed"
  fi
fi

# --- 3b · the required hooks are wired to the right event and matcher ---------------------------
# settings.json decides whether a hook ever runs, so a hook on disk that nothing calls is not a
# guard. This reads the wiring in .claude/settings.json; it does not rewrite it, and a file with
# other entries is fine as long as it carries the four.
if [ -f .claude/settings.json ] && [ -n "$py" ]; then
  miss="$("$py" -c 'import json
s = json.load(open(".claude/settings.json", encoding="utf-8-sig"))
want = [("PreToolUse", "Edit|Write", "guard-secrets"),
        ("PreToolUse", "Bash|PowerShell", "guard-commands"),
        ("Stop", "", "verify-on-finish"),
        ("SessionStart", "compact", "resume-brief")]
out = []
for ev, matcher, name in want:
    ok = False
    for entry in s.get("hooks", {}).get(ev, []):
        if (entry.get("matcher") or "") != matcher:
            continue
        for h in entry.get("hooks", []):
            if name in (h.get("command") or ""):
                ok = True
    if not ok:
        out.append(ev + "/" + (matcher or "-") + " -> " + name)
print(" ; ".join(out))' 2>/dev/null)"
  if [ -z "$miss" ]; then ok "the four required hooks are wired to the right event and matcher"
  else bad "the four required hooks are wired to the right event and matcher" "not wired: $miss . The scripts may be on disk and never called; add the missing entries to .claude/settings.json"; fi
elif [ -f .claude/settings.json ]; then
  note "no python on PATH; hook wiring not checked"
fi

# --- 3 · every hook wired in settings.json exists on disk --------------------------------------
if [ -f .claude/settings.json ]; then
  wired="$(grep -oE '\$\{CLAUDE_PROJECT_DIR\}/[^"\\]+' .claude/settings.json | sed 's|${CLAUDE_PROJECT_DIR}/||' | sort -u)"
  if [ -z "$wired" ]; then
    bad "hooks are wired in settings.json" "no \${CLAUDE_PROJECT_DIR} hook path found"
  else
    missing=""; n=0
    while IFS= read -r h; do [ -z "$h" ] && continue; n=$((n+1)); [ -f "$h" ] || missing="$missing $h"; done <<< "$wired"
    if [ -z "$missing" ]; then ok "every wired hook exists on disk ($n wired)"; else bad "every wired hook exists on disk" "missing:$missing"; fi
  fi
fi

# --- 4 · every hook ships in both shells -------------------------------------------------------
if [ -d .claude/hooks ]; then
  unpaired=""; count=0
  for f in .claude/hooks/*.ps1 .claude/hooks/*.sh; do
    [ -f "$f" ] || continue; count=$((count+1))
    base="${f%.*}"
    case "$f" in *.ps1) [ -f "$base.sh" ]  || unpaired="$unpaired $(basename "$f")";; *.sh) [ -f "$base.ps1" ] || unpaired="$unpaired $(basename "$f")";; esac
  done
  if [ "$count" -eq 0 ]; then bad "hooks ship in both shells" "no hook files at all"
  elif [ -z "$unpaired" ]; then ok "every hook ships in both shells ($((count/2)) hooks)"
  else bad "every hook ships in both shells" "missing a pair for:$unpaired"; fi
fi

# --- 4b · a PowerShell file carrying non-ASCII needs a UTF-8 BOM --------------------------------
# Windows PowerShell 5.1 decodes a BOM-less .ps1 in the system ANSI codepage, so a UTF-8 character
# in the source is read as two wrong characters and written back corrupted, while the bash twin
# writes the same text correctly.
psfiles=0; psbad=""; pshas=0
for f in .claude/hooks/*.ps1 .claude/tools/*.ps1; do
  [ -f "$f" ] || continue
  psfiles=$((psfiles+1))
  LC_ALL=C grep -q $'[^\t -~]' "$f" || continue
  pshas=$((pshas+1))
  [ "$(head -c3 "$f" | od -An -tx1 | tr -d ' \n')" = "efbbbf" ] || psbad="$psbad $(basename "$f")"
done
if [ "$psfiles" -eq 0 ]; then note "no PowerShell files to check for encoding"
elif [ -n "$psbad" ]; then bad "a PowerShell file with non-ASCII carries a UTF-8 BOM" \
  "PowerShell 5.1 reads these in the ANSI codepage and corrupts what they write:$psbad"
else ok "PowerShell encoding safe ($psfiles files, $pshas with non-ASCII, each with a BOM)"; fi

# --- 5 · always-loaded rule budget, a ratchet -------------------------------------------------
if [ -d .claude/rules ]; then
  files=0; total=0; scoped=0; detail=""
  for f in .claude/rules/*.md; do
    [ -f "$f" ] || continue
    if head -3 "$f" | grep -q '^paths:'; then scoped=$((scoped+1)); continue; fi
    files=$((files+1)); n=$(wc -l < "$f" | tr -d ' '); total=$((total+n)); detail="$detail $(basename "$f" .md)=$n"
  done
  if [ "$files" -eq 0 ]; then bad "always-loaded rules within budget" "no always-loaded rule file found; a pass here would be meaningless"
  elif [ "$total" -gt "$BASELINE" ]; then bad "always-loaded rules within budget" "$total lines across $files files against a baseline of $BASELINE; trim, or raise the baseline deliberately in this script"
  else ok "always-loaded rules $total/$BASELINE lines ($detail; $scoped path-scoped not counted)"; fi
fi

# --- 6 · every /skill referenced resolves -------------------------------------------------------
if [ -d .claude/skills ]; then
  known="$(ls .claude/skills 2>/dev/null) $BUILTIN_SKILLS"
  # Swept: the rules, the skills, and the README. Not the knowledge base, which may
  # legitimately name a skill that was retired or is only proposed in 99-pending.md.
  refs="$(grep -rhoE '`/[a-z][a-z-]{2,}`' .claude/rules .claude/skills README.md 2>/dev/null | tr -d '`' | sed 's|^/||' | sort -u)"
  if [ -z "$refs" ]; then bad "every referenced /skill resolves" "the reference sweep matched nothing; the pattern is broken, not the tree"
  else
    missing=""; for r in $refs; do echo "$known" | tr ' ' '\n' | grep -qx "$r" || missing="$missing /$r"; done
    if [ -z "$missing" ]; then ok "every referenced /skill resolves ($(echo "$refs" | wc -l | tr -d ' ') referenced)"
    else bad "every referenced /skill resolves" "referenced but no such skill:$missing"; fi
  fi
fi

# --- 7 · working/ is ignored and has no remote --------------------------------------------------
if git check-ignore -q working/probe 2>/dev/null; then ok "working/ contents are ignored"; else bad "working/ contents are ignored" "add 'working/' to .gitignore"; fi
# A linked worktree carries a .git file, so ask git whether working/ is a checkout ROOT. Asking
# about a plain subfolder answers about the enclosing repository, which is the trap in
# working-here.md, so the toplevel it reports has to be working/ itself.
wt="$(git -C working rev-parse --show-toplevel 2>/dev/null)"
if [ -n "$wt" ] && [ "$(cd working 2>/dev/null && pwd)" = "$(cd "$wt" 2>/dev/null && pwd)" ] \
   && [ -n "$(git -C working remote 2>/dev/null)" ]; then bad "working/ has no remote" "it has one; working/ is disposable and must never be published"; else ok "working/ has no remote"; fi

# --- 8 · the knowledge base exists and never links into working/ -------------------------------
kb=""; [ -d docs/knowledge-base ] && kb=docs/knowledge-base; [ -z "$kb" ] && [ -d knowledge-base ] && kb=knowledge-base
if [ -z "$kb" ]; then bad "knowledge base present" "neither docs/knowledge-base/ nor knowledge-base/ exists"
else
  if [ -f "$kb/README.md" ] && [ -f "$kb/00-orientation/index.md" ] && [ -f "$kb/99-pending.md" ]; then ok "knowledge base present at $kb"; else bad "knowledge base complete" "$kb needs README.md, 00-orientation/index.md, 99-pending.md"; fi
  links="$(grep -rnE '\]\((\.\./)*working/' "$kb" 2>/dev/null | head -3)"
  if [ -z "$links" ]; then ok "knowledge base never links into working/"; else bad "knowledge base never links into working/" "$(echo "$links" | cut -c1-100 | tr '\n' ' ')"; fi
fi

# --- 8b · knowledge integrity: structure, references, curated drift -----------------------------
# Structural validity is not truth. A green here says the pages carry the header the rules require
# and that every reference this can identify resolves. It says nothing about whether a claim on any
# of those pages is correct; that is a reader's job and an independent review's.
if [ -n "$kb" ] && [ ! -f .claude/tools/knowledge-check.sh ]; then
  # A missing validator must not remove three checks from the report without a word: that is a
  # green run over an unchecked knowledge base, which is worse than a red one.
  bad "knowledge integrity ran" "there is a knowledge base at $kb but no .claude/tools/knowledge-check.sh; nothing checked it"
fi
if [ -n "$kb" ] && [ -f .claude/tools/knowledge-check.sh ]; then
  kcout="$(bash .claude/tools/knowledge-check.sh --porcelain 2>&1)"
  if [ -z "$kcout" ]; then
    bad "knowledge integrity ran" "knowledge-check.sh produced no output, so it checked nothing"
  else
    seen_section=0
    while IFS= read -r l; do
      case "$l" in
        SECTION\ *)
          seen_section=$((seen_section+1))
          rest="${l#SECTION }"; sec="${rest%% *}"
          rest="${rest#* }";    verdict="${rest%% *}"; detail="${rest#* }"
          case "$verdict" in
            PASS) ok "knowledge $sec: $detail" ;;
            NONE) note "knowledge $sec: $detail" ;;
            *)    bad "knowledge $sec" "$detail" ;;
          esac ;;
      esac
    done <<< "$kcout"
    [ "$seen_section" -eq 0 ] && bad "knowledge integrity ran" "no section result came back; the check is not reporting"
    printf '%s\n' "$kcout" | grep '^DETAIL ' | sed 's/^DETAIL /      /'
  fi
fi

# --- 9 · no secret-shaped value in anything git can see -----------------------------------------
hits="$(git ls-files --cached --others --exclude-standard 2>/dev/null \
        | grep -vE '^(\.claude/hooks/|\.claude/tools/verify\.sh$)' \
        | xargs -r grep -InE -e 'sk-(proj-)?[A-Za-z0-9_-]{32,}' -e 'AccountKey=[A-Za-z0-9+/]{60,}' -e 'gh[pousr]_[A-Za-z0-9]{36,}' -e 'AKIA[0-9A-Z]{16}' -e 'xox[baprs]-[A-Za-z0-9]{10,}' 2>/dev/null | head -3)"
if [ -z "$hits" ]; then ok "no secret-shaped value in tracked or new files"; else bad "no secret-shaped value in tracked or new files" "$(echo "$hits" | cut -c1-100 | tr '\n' ' ')"; fi

# --- 10 · line endings: LF in the working tree -------------------------------------------------
crlf="$(git ls-files --eol 2>/dev/null | grep -E 'w/crlf' | awk '{print $NF}' | head -3)"
if [ -z "$crlf" ]; then ok "no CRLF in tracked text files"; else bad "no CRLF in tracked text files" "$(echo "$crlf" | tr '\n' ' ') (see .gitattributes)"; fi

# --- 11 · the writing rule: no em dashes in the harness or the knowledge base ------------------
dashes="$(grep -rlE -e $'\xe2\x80\x94' .claude/rules .claude/skills ${kb:-/nonexistent} README.md 2>/dev/null | head -3)"
if [ -z "$dashes" ]; then ok "no em dashes in rules, skills, or the knowledge base"; else bad "no em dashes in rules, skills, or the knowledge base" "$(echo "$dashes" | tr '\n' ' ')"; fi

# --- 12 · guard-commands can block (self-test) ---------------------------------------------------
if [ -f .claude/hooks/guard-commands.sh ]; then
  if printf '{"tool_input":{"command":"echo __guard_commands_selftest__"}}' | GUARD_COMMANDS_SELFTEST=1 bash .claude/hooks/guard-commands.sh >/dev/null 2>&1; then
    bad "guard-commands.sh can block" "the self-test marker was allowed; the hook cannot block"
  else ok "guard-commands.sh blocks its self-test marker"; fi
fi

# --- 13 · layout resolves when a workspace marker exists ------------------------------------------
if [ -f .workspace ]; then
  . .claude/tools/layout.sh
  if [ "${WS_LAYOUT:-missing}" = "missing" ]; then bad "workspace layout resolves" ".workspace exists but WS_REPOS does not resolve to a folder of checkouts"; else ok "workspace layout resolves ($WS_LAYOUT, $(ws_repos | wc -l | tr -d ' ') checkouts)"; fi
fi

# --- 13b · every hook fires and blocks when it should, only with --hooks --------------------------
if [ "$mode" = "--hooks" ]; then
  echo; note "hook tests (each hook fired by hand, both shells)"
  if [ -f .claude/tools/hooks.test.sh ]; then
    if bash .claude/tools/hooks.test.sh; then ok "hooks.test.sh passed"; else bad "hooks.test.sh passed" "a hook that should block did not, or one that should allow blocked; see above"; fi
  else bad "hooks.test.sh present" "missing"; fi

  echo; note "knowledge-check cases (the validator run against fixtures, one per invariant)"
  if [ -f .claude/tools/knowledge-check.test.sh ]; then
    if bash .claude/tools/knowledge-check.test.sh; then ok "knowledge-check.test.sh passed"
    else bad "knowledge-check.test.sh passed" "an invalid record passed, or a valid one failed; see above"; fi
  else bad "knowledge-check.test.sh present" "missing"; fi
fi

# --- 14 · the project's own checks, only with --full ----------------------------------------------
if [ "$mode" = "--full" ]; then
  echo; note "project checks (slow)"
  if [ -f .claude/tools/verify.project.sh ]; then
    if bash .claude/tools/verify.project.sh; then ok "verify.project.sh passed"; else bad "verify.project.sh passed" "see its output above"; fi
  else
    note "no .claude/tools/verify.project.sh; write one that runs this project's build and tests"
  fi
fi

echo
echo "  $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ] || exit 1

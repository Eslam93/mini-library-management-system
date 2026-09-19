#!/usr/bin/env bash
# Knowledge check: is a knowledge-base record structurally valid, and do the concrete
# references it relies on still resolve?
#
#   bash .claude/tools/knowledge-check.sh                 check this project's knowledge base
#   bash .claude/tools/knowledge-check.sh <project-root>  check another tree (fixtures, the canary)
#   bash .claude/tools/knowledge-check.sh --porcelain     one line per section, for verify.sh
#
# WHAT A GREEN RESULT MEANS: the pages carry the header the rules require, the values that have an
# objective shape have it, and every reference this tool can identify without guessing resolves.
#
# WHAT IT DOES NOT MEAN: that anything on the page is true. A page can be structurally perfect and
# wrong. `confidence: High` is not weighed against reality, a commit can exist and not support the
# claim beside it, a path can exist and hold irrelevant code, and a valid `last_verified` says
# nothing about whether the fact still holds. Truth is for a reader and an independent review.
#
# THE RULE THAT SHAPES THE REFERENCE CHECKS: only validate what has mechanically identifiable
# syntax. A bare backticked path or a bare hex string may be an example, a command, or a path in a
# scratch tree rather than a citation, and guessing which is which from prose would be noise. So
# bare forms are left alone, and the explicit `repo:` and `commit:` forms are checked.
#
# SPEED: two awk passes per page, and every existence test is a shell builtin. A subprocess per
# field per page is slow enough on Windows that someone would start skipping the check. Keep it
# that way: no per-field pipelines.

set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"   # before any cd; the caller's path is not ours
ROOT=""
porcelain=0
while [ $# -gt 0 ]; do
  case "$1" in
    --porcelain) porcelain=1 ;;
    -*) printf 'knowledge-check: unknown option %s\n' "$1" >&2; exit 2 ;;
    *)  ROOT="$1" ;;
  esac
  shift
done
[ -n "$ROOT" ] || ROOT="$(cd "$HERE/../.." && pwd)"
cd "$ROOT" || { echo "knowledge-check: cannot cd to $ROOT" >&2; exit 2; }

# --- the page class -----------------------------------------------------------------------------
# Subject to the header schema: every Markdown page in the knowledge base, except the two files the
# rules give another shape. This is a document class, not a suppression list. `99-pending.md` has
# its own shape in .claude/rules/knowledge-base.md, one line per open item grouped by who can act,
# and the base's README is its front door. Both are named in the rules and neither is a durable
# knowledge page. Nothing else is exempt, and a new page is in scope the moment it is written.
# Both are still subject to every reference check below: the header exemption exempts nothing else.
EXEMPT_BASENAMES="99-pending.md README.md"

REQUIRED_FIELDS="title status as_of last_verified verification_method scope confidence known_gaps reverify_when"
STATUS_VALUES="draft verified partially-verified superseded"
CONFIDENCE_WORDS="High Medium Low"

kb=""
[ -d docs/knowledge-base ] && kb=docs/knowledge-base
[ -z "$kb" ] && [ -d knowledge-base ] && kb=knowledge-base
if [ -z "$kb" ]; then
  if [ "$porcelain" = 1 ]; then
    echo "SECTION structure FAIL no knowledge base found"
    echo "DETAIL $ROOT"
    echo "DETAIL     no knowledge base: neither docs/knowledge-base/ nor knowledge-base/ exists"
  else
    printf 'knowledge integrity: FAIL\n  %s\n      %s\n' "$ROOT" \
      "no knowledge base: neither docs/knowledge-base/ nor knowledge-base/ exists"
  fi
  exit 1
fi

# Shape A puts the base inside the one repository; shape B puts it at a workspace root above
# several checkouts. A `repo:` path is a path from the project root, which is the repository in
# shape A and the workspace root in shape B, so it means the same thing in both. A `commit:` is
# resolved against every checkout layout.sh knows about, so a workspace citation resolves; which
# checkout it meant is not decidable from the citation and is not claimed.
shape="A"; checkouts="$ROOT"
if [ -f "$ROOT/.workspace" ] && [ -f "$HERE/layout.sh" ]; then
  # shellcheck disable=SC1091
  . "$HERE/layout.sh" >/dev/null 2>&1
  if [ "${WS_LAYOUT:-missing}" != "missing" ]; then shape="B"; checkouts="$(ws_repos)"; fi
fi

TMP="$(mktemp -d 2>/dev/null || mktemp -d -t kc)"
trap 'rm -rf "$TMP"' EXIT
: > "$TMP/fails"
s_structure=0; s_references=0; s_drift=0
f_structure=0; f_references=0; f_drift=0

fail() { printf '%s\t%s\t%s\n' "$1" "$2" "$3" >> "$TMP/fails"
         case "$1" in structure)  f_structure=$((f_structure+1)) ;;
                      references) f_references=$((f_references+1)) ;;
                      drift)      f_drift=$((f_drift+1)) ;; esac; }

# --- 1 · structure: the header every durable page carries ---------------------------------------
# One awk pass per page emits every header problem it finds. Whether a `supersedes` target exists is
# a filesystem question, so awk emits it as a candidate and the shell resolves it below.
header_awk='
function prob(m) { printf "P\t%s\n", m }
function isdate(s,   y, mo, d, dim) {
  if (s !~ /^[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]$/) return 0
  y = substr(s,1,4)+0; mo = substr(s,6,2)+0; d = substr(s,9,2)+0
  if (mo < 1 || mo > 12 || d < 1) return 0
  dim = 31
  if (mo==4 || mo==6 || mo==9 || mo==11) dim = 30
  else if (mo==2) dim = (((y%4==0) && (y%100!=0)) || (y%400==0)) ? 29 : 28
  return d <= dim
}
NR==1 { fence=$0; sub(/\r$/, "", fence)
         if (fence != "---") { prob("no page header: the file does not open with a --- front-matter block"); exit }
         opened=1; inside=1; next }
# The fence lines get their CR stripped too. Stripping it only from field lines meant a CRLF
# page reported "no page header" on Linux and passed on Windows, for the same bytes.
inside { fence=$0; sub(/\r$/, "", fence); if (fence == "---") { inside=0; done=1; exit } }
inside {
  line=$0; sub(/\r$/, "", line)
  if (match(line, /^[A-Za-z_]+:/)) {
    k = substr(line, 1, RLENGTH-1); v = substr(line, RLENGTH+1)
    sub(/^[ \t]+/, "", v); sub(/[ \t]+$/, "", v)
    # The FIRST value counts, and a second one is reported. Last-wins would open the hole behind the
    # unterminated-header case: prose further down the page could set status, as_of and confidence
    # again and repair an invalid header, and a stray --- rule in the body would close the block so
    # the page looked well formed. Requiring the fence alone does not close that; this does.
    if (k in seen) { if (!(k in dupseen)) { dupseen[k] = 1; duplist[++dn] = k } }
    else { val[k] = v; seen[k] = 1 }
  }
  next
}
END {
  if (NR == 0) { prob("the page is empty"); exit }
  if (!opened) exit                          # already reported: no header at all
  # An unterminated block would otherwise swallow the whole page as header, find every required
  # field somewhere in the prose, and pass. It is malformed, and it says so.
  if (!done) { prob("the page header opens with --- and is never closed"); exit }
  for (i = 1; i <= dn; i++) prob("the page header sets " duplist[i] " more than once; the first value is the one read")
  n = split(required, req, " ")
  for (i = 1; i <= n; i++) {
    f = req[i]
    if (!(f in seen)) prob("missing required field: " f)
    else if (val[f] == "") prob("required field is empty: " f)
  }
  if (val["status"] != "" ) {
    ok = 0; m = split(statuses, st, " ")
    for (i = 1; i <= m; i++) if (val["status"] == st[i]) ok = 1
    if (!ok) prob("status is not one of the four values the rules define: " val["status"])
  }
  if (val["confidence"] != "") {
    first = val["confidence"]; sub(/[^A-Za-z].*$/, "", first)
    ok = 0; m = split(confidences, cf, " ")
    for (i = 1; i <= m; i++) if (first == cf[i]) ok = 1
    if (!ok) prob("confidence does not start with High, Medium, or Low: " first)
  }
  split("as_of last_verified", dates, " ")
  for (i = 1; i <= 2; i++) {
    f = dates[i]
    if (val[f] != "" && !isdate(val[f])) prob(f " is not a calendar date in YYYY-MM-DD form: " val[f])
  }
  if (val["as_of"] != "" && val["last_verified"] != "" && isdate(val["as_of"]) && isdate(val["last_verified"]))
    if (val["last_verified"] < val["as_of"])
      prob("last_verified " val["last_verified"] " is before as_of " val["as_of"])
  if (val["supersedes"] != "") {
    line = val["supersedes"]
    while (match(line, /[A-Za-z0-9_.\/-]+\.md/)) {
      printf "S\t%s\n", substr(line, RSTART, RLENGTH)
      line = substr(line, RSTART + RLENGTH)
    }
  }
}'

pages="$(find "$kb" -name '*.md' -type f 2>/dev/null | sed 's|\\|/|g' | sort)"
[ -n "$pages" ] && page_count=$(printf '%s\n' "$pages" | wc -l | tr -d ' ') || page_count=0
if [ "$page_count" -eq 0 ]; then
  fail structure "$kb" "no Markdown page found; a pass here would mean nothing"
fi

while IFS= read -r page; do
  [ -n "$page" ] || continue
  base="${page##*/}"
  if [ "${page%/*}" = "$kb" ]; then
    for e in $EXEMPT_BASENAMES; do [ "$base" = "$e" ] && continue 2; done
  fi
  s_structure=$((s_structure+1))
  dir="${page%/*}"
  awk -v required="$REQUIRED_FIELDS" -v statuses="$STATUS_VALUES" -v confidences="$CONFIDENCE_WORDS" \
      "$header_awk" "$page" > "$TMP/hdr"
  while IFS=$'\t' read -r kind value; do
    case "$kind" in
      P) fail structure "$page" "$value" ;;
      S) if [ -e "$dir/$value" ]; then target="$dir/$value"
         elif [ -e "$kb/$value" ]; then target="$kb/$value"
         else fail structure "$page" "supersedes names a page that does not exist: $value"; continue; fi
         [ "$target" = "$page" ] && fail structure "$page" "supersedes points at this same page: $value"
         ;;
    esac
  done < "$TMP/hdr"
done <<EOF
$pages
EOF

# --- 2 · references: only the forms that cannot be mistaken for prose ----------------------------
# One awk pass per page emits every reference candidate, with fenced code blocks removed: a link or
# a citation inside a fence is an example of how to write one, and checking it would fail the rules
# page for quoting its own template.
refs_awk='
/^[ \t]*```/ { fence = !fence; next }
fence { next }
{
  line = $0; sub(/\r$/, "", line)
  # A Markdown link written inside a backtick span is an example of the syntax, not a link, so the
  # spans are blanked before links are read. The spans themselves are read separately below, because
  # a backticked ../path IS a reference in this base.
  lk = line
  while (match(lk, /`[^`]+`/)) lk = substr(lk, 1, RSTART - 1) " " substr(lk, RSTART + RLENGTH)
  t = lk
  while (match(t, /\[[^][]*\]\([^() \t]+\)/)) {
    s = substr(t, RSTART, RLENGTH); sub(/^[^(]*\(/, "", s); sub(/\)$/, "", s)
    print "link\t" s
    t = substr(t, RSTART + RLENGTH)
  }
  t = line
  while (match(t, /`[^`]+`/)) {
    s = substr(t, RSTART + 1, RLENGTH - 2)
    if (s ~ /^\.\.?\//)      print "rel\t" s
    else if (s ~ /^repo:/)   print "repo\t" substr(s, 6)
    else if (s ~ /^commit:/) print "commit\t" substr(s, 8)
    t = substr(t, RSTART + RLENGTH)
  }
  t = line
  while (match(t, /[DVS]-[0-9][0-9]/)) {
    before = (RSTART == 1) ? " " : substr(t, RSTART - 1, 1)
    after  = substr(t, RSTART + RLENGTH, 1)
    if (before !~ /[A-Za-z0-9]/ && after !~ /[0-9]/) print "code\t" substr(t, RSTART, RLENGTH)
    t = substr(t, RSTART + RLENGTH)
  }
}'

# The defined decision codes, gathered once. An empty set means the pattern is broken, not that the
# page has no decisions, so it fails rather than letting every citation pass.
defined=""
if [ -f "$kb/decisions.md" ]; then
  defined=" $( { grep -oE '^### +[DVS]-[0-9][0-9]' "$kb/decisions.md" | sed 's/^### *//'
                 grep -oE '^\| *[DVS]-[0-9][0-9] *\|' "$kb/decisions.md" | tr -d '| '; } \
               | sort -u | tr '\n' ' ')"
  # An empty set is only evidence of a broken pattern when something actually cites a decision. A
  # knowledge base on its first day has no decisions and no citations, and must not fail for it.
fi

resolve() {   # dir target -> 0 when it exists. Anchors are not part of a path; %20 is a space.
  local t="${2%%#*}"
  t="${t//%20/ }"
  [ -n "$t" ] || return 0
  case "$t" in
    /*) [ -e "$ROOT$t" ] ;;
    *)  [ -e "$1/$t" ] ;;
  esac
}

while IFS= read -r page; do
  [ -n "$page" ] || continue
  dir="${page%/*}"
  awk "$refs_awk" "$page" > "$TMP/refs"
  while IFS=$'\t' read -r kind value; do
    [ -n "$value" ] || continue
    # A citation holding < > or * is a template, in every form: angle brackets are this base's
    # placeholder convention, and the page that documents this syntax must be able to print it.
    case "$value" in *'<'*|*'>'*|*'*'*) continue ;; esac
    case "$kind" in
      link)
        case "$value" in http://*|https://*|mailto:*|'#'*) continue ;; esac
        s_references=$((s_references+1))
        resolve "$dir" "$value" || fail references "$page" "broken local link: $value"
        ;;
      rel)
        s_references=$((s_references+1))
        resolve "$dir" "$value" || fail references "$page" "broken page-relative reference: $value"
        ;;
      repo)
        s_references=$((s_references+1))
        t="${value%%#*}"
        [ -e "$ROOT/$t" ] || fail references "$page" "referenced repository path does not exist: $t"
        ;;
      commit)
        s_references=$((s_references+1))
        case "$value" in
          *[!0-9a-f]*|'') fail references "$page" "commit reference is not a hex sha: $value"; continue ;;
        esac
        if ! command -v git >/dev/null 2>&1; then
          fail references "$page" "cannot resolve commit references: git is not on PATH"; continue
        fi
        found=0
        for co in $checkouts; do
          git -C "$co" cat-file -e "$value^{commit}" 2>/dev/null && { found=1; break; }
        done
        [ "$found" = 1 ] || fail references "$page" "referenced commit does not resolve: $value"
        ;;
      code)
        s_references=$((s_references+1))
        if [ "$(printf '%s' "$defined" | tr -d ' ')" = "" ]; then
          fail references "$page" "cites $value, but decisions.md defines no decision at all; the id pattern is broken, not the tree"
        else
          case "$defined" in
            *" $value "*) ;;
            *) fail references "$page" "cites a decision that decisions.md does not define: $value" ;;
          esac
        fi
        ;;
    esac
  done < "$TMP/refs"
done <<EOF
$pages
EOF

# A decision may not supersede itself. Referential integrity only: whether one decision deserves to
# replace another is a reader's judgement.
if [ -f "$kb/decisions.md" ]; then
  awk '/^### +[DVS]-[0-9][0-9]/ { id = $2 }
       /\*\*Supersedes:\*\*/ && id != "" {
         line = $0
         while (match(line, /[DVS]-[0-9][0-9]/)) {
           if (substr(line, RSTART, RLENGTH) == id) print id
           line = substr(line, RSTART + RLENGTH)
         }
       }' "$kb/decisions.md" | sort -u > "$TMP/selfsup"
  while IFS= read -r selfsup; do
    [ -n "$selfsup" ] && fail references "$kb/decisions.md" "decision supersedes itself: $selfsup"
  done < "$TMP/selfsup"
fi

# --- 3 · curated documentation drift ------------------------------------------------------------
# The tree is authoritative, the documentation repeats a value derived from it, and this proves they
# agree. Deliberately curated: a quantity earns a line only when its value is deterministic, the
# documentation states it on purpose, and disagreement would mislead a reader. Not a generic sweep
# of every number, and not a prose consistency engine. The list belongs to the tree being checked,
# so a fixture and this repository each bring their own, and one with none gets no drift
# checks rather than a wall of failures about a README that was never making these claims.
numword_one() {
  case "$1" in
    zero) echo 0;; one) echo 1;; two) echo 2;; three) echo 3;; four) echo 4;; five) echo 5;;
    six) echo 6;; seven) echo 7;; eight) echo 8;; nine) echo 9;; ten) echo 10;;
    eleven) echo 11;; twelve) echo 12;; thirteen) echo 13;; fourteen) echo 14;;
    fifteen) echo 15;; sixteen) echo 16;; seventeen) echo 17;; eighteen) echo 18;;
    nineteen) echo 19;; twenty) echo 20;; thirty) echo 30;; forty) echo 40;; fifty) echo 50;;
    sixty) echo 60;; seventy) echo 70;; eighty) echo 80;; ninety) echo 90;;
    ''|*[!0-9]*) echo "";; *) echo "$1";;
  esac
}
# Hyphenated forms too. Without them, a document saying "twenty-one hooks" would match the curated
# pattern as the fragment "one hooks" and be read as 1, agreeing silently with a tree of one hook.
numword() {
  local w t u
  w="$(printf '%s' "$1" | tr '[:upper:]' '[:lower:]')"
  case "$w" in
    *-*) t="$(numword_one "${w%%-*}")"; u="$(numword_one "${w#*-}")"
         if [ -n "$t" ] && [ -n "$u" ] && [ "$t" -ge 20 ] && [ "$((t % 10))" -eq 0 ] \
            && [ "$u" -ge 1 ] && [ "$u" -le 9 ]; then echo "$((t + u))"; else echo ""; fi ;;
    *)   numword_one "$w" ;;
  esac
}

conf=".claude/knowledge-drift.conf"
have_conf=0
if [ ! -f "$conf" ]; then
  [ "$porcelain" = 1 ] || printf '  ----  no %s; no drift checks are curated for this project\n' "$conf"
else
  have_conf=1
  # `read` returns non-zero on a last line with no trailing newline, so without the second test the
  # final curated check would be dropped in silence and the section would still report PASS.
  while IFS= read -r line || [ -n "$line" ]; do
    case "$line" in ''|'#'*) continue ;; esac
    quantity="${line%%::*}"; rest="${line#*::}"
    docfile="${rest%%::*}";  pattern="${rest#*::}"
    quantity="$(printf '%s' "$quantity" | sed -e 's/^ *//' -e 's/ *$//')"
    docfile="$(printf '%s' "$docfile"  | sed -e 's/^ *//' -e 's/ *$//')"
    pattern="$(printf '%s' "$pattern"  | sed -e 's/^ *//' -e 's/ *$//')"
    s_drift=$((s_drift+1))

    # shellcheck disable=SC2086
    set -- $quantity
    kind="$1"; src="${2:-}"
    actual=""
    case "$kind" in
      subdirs) [ -d "$src" ] && actual="$(find "$src" -mindepth 1 -maxdepth 1 -type d | wc -l | tr -d ' ')" ;;
      stems)   # a tool or a hook is a script; a data file beside it is not one
               [ -d "$src" ] && actual="$(ls "$src" | grep -E '\.(sh|ps1|js|py)$' \
                                          | sed -E 's/\.(sh|ps1|js|py)$//' | sort -u | wc -l | tr -d ' ')" ;;
      table_rows)
               [ -f "$src" ] && actual="$(grep -cE '^\| *[0-9]+ *\|' "$src" | tr -d ' ')" ;;
      table_rows_with)
               col="${3:-3}"; word="${4:-}"
               [ -f "$src" ] && actual="$(awk -F'|' -v c="$col" -v w="$word" \
                 '$0 ~ /^\| *[0-9]+ *\|/ && index($(c+1), w) { n++ } END { print n+0 }' "$src")" ;;
      *) fail drift "$conf" "unknown derived quantity: $kind"; continue ;;
    esac
    if [ -z "$actual" ]; then
      fail drift "$conf" "cannot derive $kind from $src: it does not exist"; continue
    fi
    if [ ! -f "$docfile" ]; then
      fail drift "$docfile" "the documentation file stating $kind $src does not exist"; continue
    fi
    # The first match whose first word is a number, not simply the first match: a pattern such as
    # "[a-z]+ hooks" also matches "the hooks", and reading "the" as the stated
    # count would turn a working check into a confusing one.
    grep -oE -e "$pattern" "$docfile" 2>/dev/null > "$TMP/frags" || : > "$TMP/frags"
    frag=""; stated=""
    while IFS= read -r m; do
      [ -n "$m" ] || continue
      n="$(numword "${m%% *}")"
      if [ -n "$n" ]; then frag="$m"; stated="$n"; break; fi
    done < "$TMP/frags"
    if [ -z "$frag" ]; then
      # An unmatched pattern is a broken check, not a clean tree. It must never pass quietly.
      fail drift "$docfile" "no sentence states $kind $src as a number: /$pattern/"
    elif [ "$stated" != "$actual" ]; then
      fail drift "$docfile" "states $stated for $kind $src, the tree has $actual: \"$frag\""
    fi
  done < "$conf"
  # An empty set passes every check, which is the trap this repository already records against
  # itself. A curated list that produced no comparison at all is a broken list, not a clean tree.
  [ "$s_drift" -eq 0 ] && fail drift "$conf" "the curated list produced no checks at all; it is empty, or every line is a comment"
fi

# --- report -------------------------------------------------------------------------------------
total_fail=$((f_structure + f_references + f_drift))
render_detail() {
  cut -f2 "$TMP/fails" | sort -u | while IFS= read -r f; do
    printf '%s%s\n' "$1" "$f"
    awk -F'\t' -v f="$f" -v p="$1" '$2==f { print p "    " $3 }' "$TMP/fails"
  done
}

if [ "$porcelain" = 1 ]; then
  st() { if [ "$2" -eq 0 ]; then printf 'SECTION %s PASS %s\n' "$1" "$3"; else printf 'SECTION %s FAIL %s\n' "$1" "$3"; fi; }
  st structure  "$f_structure"  "$s_structure pages carry the header the rules require"
  st references "$f_references" "$s_references references resolve"
  if [ "$have_conf" = 0 ]; then
    printf 'SECTION drift NONE no curated counts for this project (%s)\n' "$conf"
  else st drift "$f_drift" "$s_drift curated counts agree with the tree"; fi
  [ "$total_fail" -gt 0 ] && render_detail "DETAIL "
  [ "$total_fail" -eq 0 ] || exit 1
  exit 0
fi

printf 'knowledge-check  base=%s  shape=%s  pages=%s\n\n' "$kb" "$shape" "$s_structure"
if [ "$total_fail" -eq 0 ]; then
  printf '  PASS  page header schema (%s pages, %s required fields)\n' \
    "$s_structure" "$(printf '%s' "$REQUIRED_FIELDS" | wc -w | tr -d ' ')"
  printf '  PASS  references resolve (%s checked)\n' "$s_references"
  printf '  PASS  curated documentation counts agree with the tree (%s)\n' "$s_drift"
  printf '\n  structurally valid, and every checked reference resolves. This says nothing about\n'
  printf '  whether any claim on these pages is true.\n'
  exit 0
fi

printf 'knowledge integrity: FAIL\n'
render_detail "  "
printf '\n  %s structure, %s reference, %s drift\n' "$f_structure" "$f_references" "$f_drift"
exit 1

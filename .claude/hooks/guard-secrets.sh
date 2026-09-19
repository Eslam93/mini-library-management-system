#!/usr/bin/env bash
# PreToolUse guard: refuses to write a secret VALUE into a file. Matched on Edit and Write.
# Contract: exit 2 blocks and stderr goes to Claude; exit 0 allows.
# This hook never prints, logs, or echoes a secret. It reports the kind and the target only.
#
# The precise check comes first: the exact value of any environment variable named in
# SECRET_ENV_NAMES, when set and at least 20 characters long. No guessing, no false positives.
# The pattern checks match well-formed VALUES, not descriptions of them. The connection-string
# check requires a second connection-string field on the same line, so ordinary code such as
# `const password = process.argv[2]` is not blocked; a guard that blocks legitimate work is how
# guards get switched off.
#
# JSON parsing: jq if present, then python, else a raw scan of the payload for token shapes only,
# which is weaker and says so on stderr once.

SECRET_ENV_NAMES="OPENROUTER_API_KEY GOOGLE_CLIENT_SECRET SESSION_SECRET POSTGRES_PASSWORD GITHUB_TOKEN GH_TOKEN"

payload=$(cat)
[ -z "$payload" ] && exit 0

extract() {
  if command -v jq >/dev/null 2>&1; then
    printf '%s' "$payload" | jq -r '[.tool_input.content, .tool_input.file_text, .tool_input.new_string] | map(select(. != null)) | join("\n")' 2>/dev/null
    return
  fi
  local py=""
  command -v python3 >/dev/null 2>&1 && py=python3
  [ -z "$py" ] && command -v python >/dev/null 2>&1 && py=python
  if [ -n "$py" ]; then
    printf '%s' "$payload" | "$py" -c 'import json,sys
d=json.load(sys.stdin).get("tool_input",{})
print("\n".join(str(d[k]) for k in ("content","file_text","new_string") if d.get(k)))' 2>/dev/null
    return
  fi
  echo "guard-secrets: no jq or python on PATH; scanning the raw payload for token shapes only" >&2
  printf '%s' "$payload"
}

text=$(extract)
[ -z "$text" ] && exit 0
path=$(printf '%s' "$payload" | grep -oE '"file_path"[[:space:]]*:[[:space:]]*"[^"]*"' | head -1 | sed 's/^[^:]*:[[:space:]]*"//; s/"$//')
[ -z "$path" ] && path="(unknown file)"

hits=""
add() { hits="$hits; $1"; }

# 1. exact live values
for name in $SECRET_ENV_NAMES; do
  val="${!name:-}"
  if [ -n "$val" ] && [ "${#val}" -ge 20 ]; then
    case "$text" in *"$val"*) add "the real value of $name";; esac
  fi
done

# 2. well-formed token values
printf '%s' "$text" | grep -Eq -e 'gh[pousr]_[A-Za-z0-9]{36,}'                 && add "a GitHub token"
printf '%s' "$text" | grep -Eq -e 'github_pat_[A-Za-z0-9_]{60,}'               && add "a GitHub fine-grained PAT"
printf '%s' "$text" | grep -Eq -e '-----BEGIN [A-Z ]{0,20}PRIVATE KEY-----'    && add "a private key block"
printf '%s' "$text" | grep -Eq -e 'AKIA[0-9A-Z]{16}'                           && add "an AWS access key id"
printf '%s' "$text" | grep -Eq -e 'xox[baprs]-[A-Za-z0-9]{10,}'                && add "a Slack token"
printf '%s' "$text" | grep -Eq -e 'AccountKey=[A-Za-z0-9+/]{60,}={0,2}'        && add "an Azure storage key"
printf '%s' "$text" | grep -Eq -e 'sk-(proj-)?[A-Za-z0-9_-]{32,}'              && add "an OpenAI-style API key"

# 3. a real password beside another connection-string field on the same line
conn='(server|data source|initial catalog|database|host|user id|uid|port|integrated security|trusted_connection|accountendpoint)[[:space:]]*='
while IFS= read -r line; do
  # The value class excludes whitespace and backticks: a real connection-string password has
  # neither, and prose that mentions a password field beside a server field does.
  printf '%s' "$line" | grep -Eiq -e '(password|pwd)[[:space:]]*=[[:space:]]*[^;"'"'"'`[:space:]]{6,}' || continue
  printf '%s' "$line" | grep -Eiq -e "$conn" || continue
  printf '%s' "$line" | grep -Eiq -e '(password|pwd)[[:space:]]*=[[:space:]]*([<${*x]|REDACTED|CHANGEME|placeholder|your[-_ ]|\.\.\.|\*\*\*)' && continue
  add "a password in a connection string"
  break
done <<< "$text"

[ -z "$hits" ] && exit 0
{
  echo "BLOCKED: this write appears to contain a secret value."
  echo
  echo "Detected:${hits#;}"
  echo "Target:   $path"
  echo
  echo "Record that a secret EXISTS, where it is referenced, and how it is provisioned."
  echo "Never the value. If this is a description of a token shape rather than a token,"
  echo "rewrite the example so it is obviously not real. Do not split the value across"
  echo "several edits."
} >&2
exit 2

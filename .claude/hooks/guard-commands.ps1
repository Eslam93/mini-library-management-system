<#
    PreToolUse guard for the small number of commands whose damage cannot be undone by reading
    the output and trying again.

    Matched on BOTH Bash and PowerShell. On Windows about half of what runs goes through
    PowerShell, so a guard matched on Bash alone looks wired, reports healthy, and covers half
    of what it claims.

    THE LIST STARTS EMPTY. An entry is added only after a real incident, with the date and what it
    cost, because a guard that blocks legitimate work is how guards get switched off. The reference
    block at the end lists common destructive command shapes, all off. Copy one in when it has
    earned its place here, never speculatively.

    Contract: exit 2 blocks the call and stderr is shown to Claude; exit 0 allows.
    Self-test: with GUARD_COMMANDS_SELFTEST=1 in the environment, a command containing the marker
    __guard_commands_selftest__ is blocked, so verify.sh can prove this hook fires.
#>

$ErrorActionPreference = 'Stop'

$raw = [Console]::In.ReadToEnd()
try { $payload = $raw | ConvertFrom-Json } catch { exit 0 }

$cmd = $payload.tool_input.command
if ([string]::IsNullOrWhiteSpace($cmd)) { exit 0 }

function Deny {
    param([string]$What, [string]$Why, [string]$Instead)
    $m = @()
    $m += "BLOCKED: $What"
    $m += ''
    $m += $Why
    $m += ''
    if ($Instead) { $m += $Instead; $m += '' }
    $m += 'This is a hook, not a preference. If it is genuinely wrong, say so to the user and'
    $m += 'let them decide. Do not reword the command to get around it.'
    [Console]::Error.WriteLine(($m -join "`n"))
    exit 2
}

# ---- active entries: what, why, instead, date added -------------------------------------
# (none yet)

# ---- self-test ---------------------------------------------------------------------------
if ($env:GUARD_COMMANDS_SELFTEST -eq '1' -and $cmd -match '__guard_commands_selftest__') {
    Deny 'the guard-commands self-test marker' 'verify.sh is proving this hook can block a call.' ''
}

exit 0

<#  ---- reference shapes, all OFF. Adopt one only after an incident here, and date it. ----
    rm -rf on /, ~, or the repository root     '(?i)\brm\s+-[a-z]*r[a-z]*\s+(/|~|\$HOME|\.)(\s|$)'
    git push --force to a shared branch        '(?i)\bgit\b.*\bpush\b.*--force(\s|$)'
    git push --mirror, deletes absent refs     '(?i)\bgit\b.{0,80}\bpush\b.{0,80}--mirror\b'
    git reset --hard, git checkout .           '(?i)\bgit\s+(reset\s+--hard|checkout\s+\.)(\s|$)'
    DROP TABLE, DROP DATABASE                  '(?i)\bdrop\s+(table|database)\b'
    docker system prune, kubectl delete        '(?i)(docker\s+system\s+prune|kubectl\s+delete)'
    npm publish, --no-verify                   '(?i)(\bnpm\s+publish\b|--no-verify\b)'
#>

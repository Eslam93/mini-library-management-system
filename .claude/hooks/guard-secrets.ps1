<#
    PreToolUse guard: refuses to write a secret VALUE into a file.

    Matched on Edit and Write. The rule it enforces: record that a secret exists, where it is
    referenced, and how it is provisioned. Never its value.

    The first check is the precise one and the reason this hook is worth having: it compares the
    text against the ACTUAL value of every environment variable named in $secretEnvNames. No
    pattern matching, no guessing, no false positives.

    The pattern checks match well-formed VALUES, not descriptions of them, so a document that
    explains what a token looks like is not blocked for saying so.

    The connection-string check requires a second connection-string field on the same line, so
    ordinary code such as `const password = process.argv[2]` is not blocked. A guard that blocks
    legitimate work is how guards get switched off.

    This hook never prints, logs, or echoes a secret. It reports the kind and the target only.
    Contract: exit 2 blocks and stderr goes to Claude; exit 0 allows.
#>

$ErrorActionPreference = 'Stop'

$secretEnvNames = @('OPENROUTER_API_KEY', 'GOOGLE_CLIENT_SECRET', 'SESSION_SECRET', 'POSTGRES_PASSWORD', 'GITHUB_TOKEN', 'GH_TOKEN')

$raw = [Console]::In.ReadToEnd()
try { $payload = $raw | ConvertFrom-Json } catch { exit 0 }

$parts = @(
    $payload.tool_input.content,
    $payload.tool_input.file_text,
    $payload.tool_input.new_string
) | Where-Object { $_ }

if (-not $parts) { exit 0 }
$text = $parts -join "`n"
if ([string]::IsNullOrWhiteSpace($text)) { exit 0 }

$path = $payload.tool_input.file_path
if (-not $path) { $path = '(unknown file)' }

$hits = @()

# 1. The exact live values. Precise, so no false positives.
foreach ($name in $secretEnvNames) {
    $val = [Environment]::GetEnvironmentVariable($name, 'User')
    if (-not $val) { $val = [Environment]::GetEnvironmentVariable($name, 'Process') }
    if ($val -and $val.Length -ge 20 -and $text.Contains($val)) {
        $hits += "the real value of $name"
    }
}

# 2. Well-formed token values, not descriptions of them.
$patterns = [ordered]@{
    'a GitHub token'            = 'gh[pousr]_[A-Za-z0-9]{36,}'
    'a GitHub fine-grained PAT' = 'github_pat_[A-Za-z0-9_]{60,}'
    'a private key block'       = '-----BEGIN [A-Z ]{0,20}PRIVATE KEY-----'
    'an AWS access key id'      = 'AKIA[0-9A-Z]{16}'
    'a Slack token'             = 'xox[baprs]-[A-Za-z0-9]{10,}'
    'an Azure storage key'      = 'AccountKey=[A-Za-z0-9+/]{60,}={0,2}'
    'an OpenAI-style API key'   = 'sk-(proj-)?[A-Za-z0-9_-]{32,}'
}
foreach ($k in $patterns.Keys) {
    if ([regex]::IsMatch($text, $patterns[$k])) { $hits += $k }
}

# 3. A real password beside another connection-string field on the same line.
$connKeys = 'server|data source|initial catalog|database|host|user id|uid|port|integrated security|trusted_connection|accountendpoint'
foreach ($line in ($text -split "`r?`n")) {
    # The value class excludes whitespace and backticks: a real connection-string password has
    # neither, and prose that mentions a password field beside a server field does.
    $m = [regex]::Match($line, '(?i)\b(password|pwd)\s*=\s*([^;\r\n"''`\s]{6,})')
    if (-not $m.Success) { continue }
    if (-not [regex]::IsMatch($line, "(?i)\b($connKeys)\s*=")) { continue }
    $val = $m.Groups[2].Value.Trim()
    $placeholder = ($val -match '^\s*[<${*x]|REDACTED|CHANGEME|placeholder|your[-_ ]|\.\.\.|\*\*\*') -or ($val -match '^\s*$')
    if (-not $placeholder) { $hits += 'a password in a connection string'; break }
}

if ($hits.Count -eq 0) { exit 0 }

$m = @()
$m += 'BLOCKED: this write appears to contain a secret value.'
$m += ''
$m += 'Detected: ' + ($hits -join '; ')
$m += "Target:   $path"
$m += ''
$m += 'Record that a secret EXISTS, where it is referenced, and how it is provisioned.'
$m += 'Never the value. If this is a description of a token shape rather than a token,'
$m += 'rewrite the example so it is obviously not real. Do not split the value across'
$m += 'several edits.'
[Console]::Error.WriteLine(($m -join "`n"))
exit 2

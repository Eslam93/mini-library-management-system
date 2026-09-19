<#
    SessionStart hook, matcher "compact": after a compaction, put the disposable state back in
    front of the assistant so the build continues from the agreed brief rather than from a summary.

    Prints, to stdout (which SessionStart adds to the context): working/status.md, then the task
    brief. Capped so it cannot flood the context. Exit 0 always; this hook only informs.

    Which brief: the one this session is carrying. baseline.sh seal writes
    working/active-tasks/<session id> at the owner's yes, holding one line, working/<task>/brief.md,
    and this hook reads the pointer for the session id the host gives it. That is the whole rule: no
    recency, no scanning. It matters because another brief can be written under working/ after the
    agreement, so the newest brief in the tree is not necessarily the agreed one.

    Fallback, when there is no valid pointer for this session (a task sealed without a session id,
    or a pointer that was removed): the newest working/<task>/brief.md, one level deep only, so a
    nested brief can never win. It is announced as a guess, because it is one.
#>

$ErrorActionPreference = 'SilentlyContinue'

$raw = [Console]::In.ReadToEnd()
try { $payload = $raw | ConvertFrom-Json } catch { $payload = $null }
$cwd = if ($payload -and $payload.cwd) { $payload.cwd } else { (Get-Location).Path }
$session = if ($payload) { [string]$payload.session_id } else { '' }
$working = Join-Path $cwd 'working'
if (-not (Test-Path $working)) { exit 0 }

$out = @()
$status = Join-Path $working 'status.md'
if (Test-Path $status) {
    $out += 'After compaction. Re-read before continuing. working/status.md:'
    $out += (Get-Content $status -TotalCount 60)
}

# ---- the brief this session is carrying ------------------------------------------------------
$brief = $null; $how = 'none'
if ($session -cmatch '^[A-Za-z0-9][A-Za-z0-9_-]{7,63}$') {
    $ptr = Join-Path (Join-Path $working 'active-tasks') $session
    if (Test-Path $ptr -PathType Leaf) {
        $how = 'stale'
        $rel = (Get-Content $ptr -ErrorAction SilentlyContinue | Where-Object { $_.Trim() -ne '' } | Select-Object -First 1)
        if ($rel) { $rel = $rel.Trim() }
        # one task folder, one brief: never a nested path, never an absolute path, never a traversal
        if ($rel -cmatch '^working/[A-Za-z0-9][A-Za-z0-9._-]*/brief\.md$') {
            $target = Join-Path $cwd $rel
            if (Test-Path $target -PathType Leaf) { $brief = Get-Item $target; $how = 'active' }
        }
    }
}
# The stale case is said out loud whether or not anything can replace it: a session that quietly
# lost its agreement across a compaction is the failure this hook exists to prevent.
if ($how -eq 'stale') {
    $out += ''
    $out += "This session's active-task pointer does not name a readable task brief, so the agreement it"
    $out += 'recorded cannot be restored. Ask the owner what this session is working on.'
}
if (-not $brief) {
    $brief = Get-ChildItem -Path (Join-Path (Join-Path $working '*') 'brief.md') -File |
             Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if ($brief) { $how = if ($how -eq 'stale') { 'stale-fallback' } else { 'fallback' } }
}

if ($brief) {
    $rel = $brief.FullName.Substring($cwd.Length).TrimStart('\', '/') -replace '\\', '/'
    $out += ''
    switch ($how) {
        'active' {
            $out += "The agreed task brief this session is carrying, $rel (bound to this session when the owner said yes; do not re-plan it):"
        }
        'stale-fallback' {
            $out += "The newest task brief under working/ is $rel. Treat it as a guess, not as this session's agreement:"
        }
        default {
            $out += "No task is bound to this session. The newest task brief under working/ is $rel. Treat it as a guess,"
            $out += "not as this session's agreement; ask the owner before building from it:"
        }
    }
    $out += (Get-Content $brief.FullName -TotalCount 80)
}

if ($out.Count -gt 0) { Write-Output ($out -join "`n") }
exit 0

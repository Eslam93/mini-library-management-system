<#
    Stop hook: blocks a turn that weakened, skipped, or deleted a test.

    Deliberately LIGHT. It runs at the end of every turn, and a gate you click through ten times a
    day is not a gate: if it is slow, the first thing anyone does is switch it off. So this does
    pure git work and nothing that compiles. The full build and test suite live behind
    .claude/tools/verify.sh --full.

    It guards ONE failure mode, the one that is both most likely and most expensive: an agent
    changing behaviour and then editing the test so it matches. A green run across a pile of edited
    tests means nothing until somebody has looked at what the edits were.

    It also prints a note, never a block, when the last assistant message carries a rationalization
    phrase such as "skip the tests for now" or "pre-existing bug". Regex heuristics can be wrong, so
    that stays a note for the human.

    Contract: exit 0 fine; exit 2 blocks the turn from ending and stderr is shown to Claude.
    It must honour stop_hook_active or it loops against itself. Claude Code overrides any Stop hook
    after eight consecutive blocks, so this is a gate, not a wall.

    Where it looks: every git checkout under WS_REPOS when cwd carries a .workspace marker (shape
    B; the marker wins, because a workspace root is itself a checkout); otherwise the repository at
    cwd when cwd is a git checkout (shape A). If neither, exit 0. A hook pointed at the wrong
    folders would find nothing and exit 0 on every turn, which looks exactly like a pass, so the
    places it looks are spelled out here.

    What it compares against: the baseline of the task THIS session is carrying. baseline.sh seal
    writes baseline_commit.<checkout> into the front matter of working/<task>/brief.md at the
    owner's yes and binds it to the session in working/active-tasks/<session id>. This hook reads
    the pointer for the session id the host gives it, so two sessions sharing one checkout each
    measure their own task, and no brief is chosen by recency.
      - a weakening that was committed stays visible: a diff against HEAD alone shows nothing once
        the weakened test is committed;
      - renames are detected (-M), so a staged git mv plus a removed assertion is compared old path
        to new path;
      - a test added during the task has no version at the baseline, so it is compared against the
        commit that first added it during the task, following renames back; comparing against HEAD
        would see nothing once the weakening was itself committed, and one git mv would otherwise
        make the weakened file its own comparison base. With no baseline, or when the file was
        staged and never committed, HEAD is the only earlier version and is used.
    It also refuses to run on a seal it cannot trust. baseline.sh records seal_sha256 over the
    approval fields, and this hook rebuilds it. A digest that does not match, or a brief that
    records a baseline and carries no digest at all, blocks (exit 2) rather than falling back:
    falling back to HEAD is the outcome such an edit is after, and treating a missing digest as
    harmless would mean deleting one line disarmed the whole mechanism.
    Fallback, never a block, and never a guess at which task is active: no session id, no pointer, a
    pointer that does not resolve, a brief with no seal, or a seal that does not name this checkout,
    and the comparison is against HEAD, as for a session with no task. A sealed commit rewritten by
    a rebase, amend, or squash is compared from its merge-base with HEAD; one that does not exist
    here falls back to HEAD. The last four print a note; a session with no id and a session with no
    pointer are the ordinary case and stay quiet. A note goes to stdout, which Claude Code keeps in
    its debug log for a Stop hook that exits 0: it is for a person reading the log, not for the
    assistant. The hook never writes a pointer and never seals anything.
#>

$ErrorActionPreference = 'Stop'

$raw = [Console]::In.ReadToEnd()
try { $payload = $raw | ConvertFrom-Json } catch { exit 0 }

# stop_hook_active says a Stop hook already blocked this turn. Exiting 0 on it would make the second
# Stop an unconditional pass: block once, carry on, finish. The deterministic check runs again
# instead, so a weakening still present still blocks and a fixed one is allowed. Loop protection is
# Claude Code's own consecutive-block limit, which overrides a Stop hook after eight.

$cwd = if ($payload.cwd) { $payload.cwd } else { (Get-Location).Path }
$session = [string]$payload.session_id

# ---- rationalization note (never blocks) ------------------------------------------------
$transcript = $payload.transcript_path
if ($transcript -and (Test-Path $transcript)) {
    try {
        $tail = (Get-Content $transcript -Tail 40 -ErrorAction Stop) -join "`n"
        $phrases = 'skip (the )?tests? for now|pre-existing (bug|issue|failure)|good enough for now|can be fixed later|temporarily disabl|out of scope for this|will fix in a follow-?up'
        if ($tail -match "(?i)($phrases)") {
            Write-Output "note from verify-on-finish: the last message carries a rationalization phrase ($($Matches[1])). Worth a second look before accepting."
        }
    } catch { }
}

# ---- where to look ------------------------------------------------------------------------
$git = (Get-Command git -ErrorAction SilentlyContinue).Source
if (-not $git) { exit 0 }

# Is this the root of a git checkout? A linked worktree carries a .git FILE, not a directory, so
# testing for a directory would make every worktree invisible to this hook. Ask git instead.
# Resolve-Path on both sides normalises the two path forms Windows produces.
function Test-CheckoutRoot([string]$Path) {
    if (-not (Test-Path $Path -PathType Container)) { return $false }
    $prev = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try { $top = & $git -C $Path rev-parse --show-toplevel 2>$null; if ($LASTEXITCODE -ne 0) { return $false } }
    catch { return $false } finally { $ErrorActionPreference = $prev }
    $top = (@($top) -join '').Trim()
    if (-not $top) { return $false }
    try {
        $a = (Resolve-Path -LiteralPath $Path -ErrorAction Stop).Path.TrimEnd('\', '/')
        $b = (Resolve-Path -LiteralPath $top  -ErrorAction Stop).Path.TrimEnd('\', '/')
    } catch { return $false }
    return ($a -eq $b)
}

$repos = @()
$marker = Join-Path $cwd '.workspace'
if (Test-Path $marker) {
    $line = Select-String -Path $marker -Pattern '^WS_REPOS=(.+)$' | Select-Object -First 1
    if ($line) {
        $reposRoot = $line.Matches[0].Groups[1].Value.Trim()
        if (Test-Path $reposRoot) {
            $repos = Get-ChildItem -Path $reposRoot -Directory -ErrorAction SilentlyContinue |
                     Where-Object { Test-CheckoutRoot $_.FullName } |
                     ForEach-Object { $_.FullName }
        }
    }
} elseif (Test-CheckoutRoot $cwd) {
    $repos += $cwd
}
if (-not $repos -or $repos.Count -eq 0) { exit 0 }

# Call git without ever letting its stderr reach PowerShell's error stream. Redirecting native
# stderr under 'Stop' terminates the script silently. Suspending 'Stop' for
# the call is the only form that both suppresses the warning text and cannot terminate the caller.
function Invoke-Git {
    param([string]$Repo, [string[]]$GitArgs)
    $prev = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        $out = & $git -C $Repo @GitArgs 2>$null
        if ($LASTEXITCODE -ne 0) { return $null }
        return $out
    } catch { return $null } finally { $ErrorActionPreference = $prev }
}
# Same, for commands whose answer is the exit code (cat-file -e, merge-base --is-ancestor).
function Test-Git {
    param([string]$Repo, [string[]]$GitArgs)
    $prev = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try { & $git -C $Repo @GitArgs 2>$null | Out-Null; return ($LASTEXITCODE -eq 0) }
    catch { return $false } finally { $ErrorActionPreference = $prev }
}

# ---- the brief this session is carrying, if any ----------------------------------------------
$briefFile = $null; $briefName = ''; $fm = @()
if ($session -cmatch '^[A-Za-z0-9][A-Za-z0-9_-]{7,63}$') {
    $ptr = Join-Path (Join-Path (Join-Path $cwd 'working') 'active-tasks') $session
    if (Test-Path $ptr -PathType Leaf) {
        $rel = (Get-Content $ptr -ErrorAction SilentlyContinue | Where-Object { $_.Trim() -ne '' } | Select-Object -First 1)
        if ($rel) { $rel = $rel.Trim() }
        # one task folder, one brief: never a nested path, never an absolute path, never a traversal
        if ($rel -cmatch '^working/[A-Za-z0-9][A-Za-z0-9._-]*/brief\.md$' -and (Test-Path (Join-Path $cwd $rel) -PathType Leaf)) {
            $briefFile = Join-Path $cwd $rel; $briefName = $rel
        } else {
            Write-Output "note from verify-on-finish: the active-task pointer for this session does not resolve to a task brief; comparing against HEAD."
        }
    }
}
if ($briefFile) {
    # UTF-8 explicitly: Windows PowerShell 5.1 reads a BOM-less file in the system ANSI codepage,
    # which turns every non-ASCII byte baseline.sh wrote into different characters and makes the
    # digest disagree with both bash implementations: a checkout folder with an accent in its name
    # would report a valid seal as tampered.
    $lines = @(Get-Content $briefFile -Encoding UTF8 -ErrorAction SilentlyContinue)
    if ($lines.Count -gt 0 -and $lines[0].Trim() -eq '---') {
        for ($i = 1; $i -lt $lines.Count; $i++) {
            if ($lines[$i].Trim() -eq '---') { break }
            $fm += $lines[$i]
        }
    }
    if (-not ($fm | Where-Object { $_ -cmatch '^baseline_commit(\.[^:]*)?:' })) {
        Write-Output "note from verify-on-finish: $briefName carries no baseline; comparing against HEAD."
        $briefFile = $null; $fm = @()
    }
}

function Get-Short {
    param([string]$Value)
    if ($Value.Length -ge 7) { return $Value.Substring(0, 7) }
    return $Value
}

# ---- is the approved starting point still the approved one? --------------------------------
# Rendered byte for byte as baseline.sh and the bash twin render it: fixed field order, one
# "key: value" line with a single space, values trimmed, per-checkout lines sorted by BYTES
# (Ordinal, not the culture sort, which would disagree with LC_ALL=C on mixed case), trailing
# newline, UTF-8. One byte of difference and a valid seal reads as tampered on one platform only.
function Get-CanonicalSeal {
    param([string[]]$Fm)
    $out = @()
    foreach ($k in @('task', 'approved_at', 'tier')) {
        $hit = $Fm | Where-Object { $_.StartsWith("${k}:", [System.StringComparison]::Ordinal) } | Select-Object -First 1
        if ($hit) { $out += "${k}: " + $hit.Substring($k.Length + 1).Trim() }
    }
    $bc = @()
    foreach ($l in $Fm) {
        if ($l -cmatch '^(baseline_commit(\.[^:]*)?):(.*)$') { $bc += ($Matches[1] + ': ' + $Matches[3].Trim()) }
    }
    if ($bc.Count -gt 0) {
        $bcArr = [string[]]$bc
        [Array]::Sort($bcArr, [System.StringComparer]::Ordinal)
        $out += $bcArr
    }
    foreach ($k in @('brief_sha256', 'pre_existing')) {
        $hit = $Fm | Where-Object { $_.StartsWith("${k}:", [System.StringComparison]::Ordinal) } | Select-Object -First 1
        if ($hit) { $out += "${k}: " + $hit.Substring($k.Length + 1).Trim() }
    }
    if ($out.Count -eq 0) { return '' }
    return (($out -join "`n") + "`n")
}
function Get-Sha256Hex {
    param([string]$Text)
    # Same seam as the bash twin, for the same reason: the fail-closed branch has to be reachable.
    if ($env:VERIFY_ON_FINISH_NO_DIGEST) { throw 'digest disabled for the self-test' }
    $sha = [System.Security.Cryptography.SHA256]::Create()
    try {
        $bytes = [System.Text.Encoding]::UTF8.GetBytes($Text)
        return (($sha.ComputeHash($bytes) | ForEach-Object { $_.ToString('x2') }) -join '')
    } finally { $sha.Dispose() }
}

if ($briefFile) {
    $sealHit = $fm | Where-Object { $_.StartsWith('seal_sha256:', [System.StringComparison]::Ordinal) } | Select-Object -First 1
    $want = if ($sealHit) { ($sealHit.Trim() -split '\s+')[-1] } else { '' }
    # Fail closed if the digest cannot be computed at all: an unverifiable seal is the state a
    # moved baseline also produces, so it is not waved through.
    $have = $null
    try { $have = Get-Sha256Hex (Get-CanonicalSeal $fm) } catch { $have = $null }
    if ($null -eq $have -and $payload.stop_hook_active -eq $true) {
        # Said once already, and missing hash tooling is not repairable from here. The task is
        # still not verified: baseline.sh check says so at hand-back.
        Write-Output "note from verify-on-finish: the seal in $briefName still could not be verified. Not blocking again; the task is NOT verified."
    } elseif ($null -eq $have) {
        $m = @()
        $m += "STOP: the sealed approval in $briefName cannot be verified here."
        $m += ''
        $m += '  seal_sha256 could not be recomputed, so this hook cannot tell an intact seal from a'
        $m += '  moved one. This session is carrying a sealed task, and that is not waved through.'
        [Console]::Error.WriteLine(($m -join "`n"))
        exit 2
    }
    # A brief recording a baseline with no digest is not to be trusted: deleting one line would
    # otherwise turn any sealed brief into an unprotected one.
    elseif (-not $want -or $want -ne $have) {
        # Falling back to HEAD here would hand the edit exactly what it was after, because the
        # comparison base itself may be what moved. There is no safe base left, so the turn stops.
        $reason = if (-not $want) { 'it records a baseline but carries no seal_sha256 at all' }
                  else { 'seal_sha256 does not match the approval fields now in the brief' }
        $m = @()
        $m += "STOP: the sealed approval in $briefName cannot be trusted."
            $m += ''
            $m += "  $reason. The approval fields are task, approved_at,"
            $m += '  tier, every baseline_commit, brief_sha256, and pre_existing.'
            $m += ''
            $m += 'This is not the same as a task with no baseline. The recorded starting point is what'
            $m += 'every test comparison in this session is measured from, so a moved baseline can hide'
            $m += 'a weakening rather than merely lose the protection. Comparing against HEAD instead'
            $m += 'would be exactly the outcome the edit produces, so this turn stops.'
            $m += ''
            $m += 'Do one of these, then finish:'
            $m += '  - restore the sealed values from git or from the owner''s record; or'
            $m += '  - if the agreement really changed, say so to the owner, write a new brief under'
            $m += '    working/<new-task>/ and seal that one, leaving this approval readable beside it.'
            $m += ''
        $t = $briefName -replace '^working/', '' -replace '/brief\.md$', ''
        $m += "  bash .claude/tools/baseline.sh check $t"
        [Console]::Error.WriteLine(($m -join "`n"))
        exit 2
    }
}

function Test-IsTestFile {
    param([string]$Path)
    return ($Path -match '(?i)(\.test\.|\.spec\.|(^|[\\/])test_[^\\/]*\.py$|(^|[\\/])(tests?|__tests__)[\\/])')
}

# Cheap proxy for how much a test is asserting.
function Get-AssertionCount {
    param([string]$Text)
    if (-not $Text) { return 0 }
    $patterns = @('\bit\s*\(', '\btest\s*\(', '\bexpect\s*\(', '\bassert\s')
    $n = 0
    foreach ($p in $patterns) { $n += ([regex]::Matches($Text, $p)).Count }
    return $n
}
function Get-SkipCount {
    param([string]$Text)
    if (-not $Text) { return 0 }
    return ([regex]::Matches($Text, '(?i)\.skip\s*\(|\.only\s*\(|\[Skip|@skip|xit\s*\(|xdescribe\s*\(')).Count
}

# The owner can authorize one exact test change, recorded in the brief by
# `baseline.sh allow-test-change`. Keyed on the file AND the sha256 of the resulting content, so it
# covers that change and nothing after it. No path-level or task-level switch, by design.
function Get-ContentHash([string]$Repo, [string]$Rel) {
    $f = Join-Path $Repo $Rel
    if (-not (Test-Path $f -PathType Leaf)) { return 'deleted' }
    try { return (Get-FileHash -Path $f -Algorithm SHA256).Hash.ToLowerInvariant() } catch { return 'unhashable' }
}
function Test-Authorized([string]$Label, [string]$Hash) {
    if (-not $fm) { return $false }
    $key = "test_change_allowed: $Hash $Label "
    foreach ($l in $fm) { if ($l.StartsWith($key, [System.StringComparison]::Ordinal)) { return $true } }
    return $false
}

$problems = @()
$allowed = @()
foreach ($repo in $repos) {
    $name = Split-Path $repo -Leaf
    $base = 'HEAD'; $since = 'HEAD'
    if ($briefFile) {
        # the value is the last field, so a checkout folder with a space in its name still parses,
        # and StartsWith means a name with a regex character is not a pattern
        # The key up to the colon, then whatever whitespace follows, exactly as Get-CanonicalSeal
        # reads it. Requiring a literal space let a tab keep the digest valid while this lookup
        # found nothing and quietly fell back to HEAD.
        $key = "baseline_commit.$name" + ':'
        $hit = $fm | Where-Object { $_.StartsWith($key, [System.StringComparison]::Ordinal) } | Select-Object -First 1
        $sha = if ($hit) { $hit.Substring($key.Length).Trim() } else { $null }
        if (-not $sha) {
            Write-Output "note from verify-on-finish: $briefName has no baseline for $name; comparing against HEAD."
        } elseif (Test-Git $repo @('merge-base', '--is-ancestor', $sha, 'HEAD')) {
            $base = $sha; $since = "the task baseline $(Get-Short $sha) ($briefName)"
        } else {
            $mb = Invoke-Git $repo @('merge-base', $sha, 'HEAD')
            $mb = if ($mb) { (@($mb) -join '').Trim() } else { '' }
            if ($mb) {
                $base = $mb; $since = "the merge-base $(Get-Short $mb) of the rewritten task baseline $(Get-Short $sha) ($briefName)"
                Write-Output "note from verify-on-finish: the task baseline $(Get-Short $sha) in $briefName is not an ancestor of HEAD in $name (rewritten by a rebase, amend, or squash); comparing from its merge-base $(Get-Short $mb)."
            } else {
                Write-Output "note from verify-on-finish: the task baseline $(Get-Short $sha) in $briefName does not exist in $name; comparing against HEAD instead."
            }
        }
    }
    $status = Invoke-Git $repo @('diff', '--name-status', '-M', $base)
    if (-not $status) { continue }
    foreach ($line in $status) {
        if ([string]::IsNullOrWhiteSpace($line)) { continue }
        $parts = $line -split "`t", 3
        if ($parts.Count -lt 2) { continue }
        $code = $parts[0].Trim(); $file = $parts[1].Trim()
        $file2 = if ($parts.Count -ge 3) { $parts[2].Trim() } else { $file }
        $label = $null; $old = $file; $new = $file; $cmpBase = $base; $cmpSince = $since
        if ($code -like 'D*') {
            if (-not (Test-IsTestFile $file)) { continue }
            if (Test-Authorized "$name/$file" 'deleted') { $allowed += "$name/$file"; continue }
            $problems += "DELETED  $name/$file since $since"; continue
        } elseif ($code -like 'M*') {
            if (-not (Test-IsTestFile $file)) { continue }
            $label = "$name/$file"
        } elseif ($code -like 'R*') {
            if (-not ((Test-IsTestFile $file) -or (Test-IsTestFile $file2))) { continue }
            $label = "$name/$file -> $file2 (renamed)"; $new = $file2
        } elseif ($code -like 'A*') {
            # A test that did not exist at the baseline was introduced during this task, so there
            # is no baseline version. Comparing against HEAD catches a weakening that is still
            # uncommitted, and nothing else: once the weakening is committed, HEAD is the weakened
            # version and the two sides are identical. So compare against the version at the commit
            # that first added the file during this task.
            if (-not (Test-IsTestFile $file)) { continue }
            # git log with one pathspec cannot pair a rename, so a commit that renamed the file is
            # reported as an ADD of the new name and the weakened file becomes its own base. Follow
            # the rename back, bounded, using the commit's own full diff to find the old name.
            $first = $null; $probe = $file
            if ($base -ne 'HEAD') {
                $upto = 'HEAD'; $hop = 0
                while ($hop -lt 5) {
                    $log = Invoke-Git $repo @('log', '--diff-filter=A', '--reverse', '--format=%H', "$base..$upto", '--', $probe)
                    $first = if ($log) { @($log) | Where-Object { $_.Trim() -ne '' } | Select-Object -First 1 } else { $null }
                    if (-not $first) { break }
                    $first = $first.Trim()
                    $show = Invoke-Git $repo @('show', '--name-status', '-M', '--format=', $first)
                    $src = $null
                    foreach ($l in @($show)) {
                        $parts = $l -split "`t"
                        if ($parts.Count -ge 3 -and $parts[0] -like 'R*' -and $parts[2] -eq $probe) { $src = $parts[1]; break }
                    }
                    if (-not $src) { break }
                    $probe = $src; $upto = "$first^"; $hop++
                }
            }
            if ($first) {
                $label = if ($probe -ne $file) { "$name/$probe -> $file (added during the task, then renamed)" }
                         else { "$name/$file (added during the task)" }
                $cmpBase = $first; $old = $probe
                $cmpSince = "$(Get-Short $first), the commit that added it during this task"
            } elseif (Test-Git $repo @('cat-file', '-e', "HEAD:$file")) {
                # staged but never committed, or no task baseline: HEAD is the only earlier version
                $label = "$name/$file (added during the task)"; $cmpBase = 'HEAD'; $cmpSince = 'HEAD'
            } else { continue }
        } else { continue }
        $before = (Invoke-Git $repo @('show', "${cmpBase}:$old")) -join "`n"
        $afterPath = Join-Path $repo $new
        $after = if (Test-Path $afterPath) { Get-Content $afterPath -Raw -ErrorAction SilentlyContinue } else { '' }
        $b = Get-AssertionCount $before
        $a = Get-AssertionCount $after
        $skipsBefore = Get-SkipCount $before
        $skipsAfter  = Get-SkipCount $after
        if (($a -lt $b) -or ($skipsAfter -gt $skipsBefore)) {
            if (Test-Authorized "$name/$new" (Get-ContentHash $repo $new)) { $allowed += "$name/$new"; continue }
        }
        if ($a -lt $b) { $problems += "WEAKENED $label  (assertions $b -> $a) since $cmpSince" }
        if ($skipsAfter -gt $skipsBefore) { $problems += "SKIPPED  $label  (skip markers $skipsBefore -> $skipsAfter) since $cmpSince" }
    }
}

if ($allowed.Count -gt 0) {
    Write-Output ("note from verify-on-finish: owner-authorized test changes were allowed: " + ($allowed -join ', '))
}
if ($problems.Count -eq 0) { exit 0 }

$msg = @()
$msg += 'STOP: a test was weakened, skipped, or deleted.'
$msg += ''
$msg += $problems | ForEach-Object { "  $_" }
$msg += ''
$msg += 'Removing or editing a test to make a suite pass hides the behaviour the test existed'
$msg += 'to protect. Do one of these, then finish:'
$msg += '  - restore the assertions and fix the code instead; or'
$msg += '  - if the test genuinely encoded wrong behaviour, say so explicitly to the user,'
$msg += '    explain why the old assertion was wrong, and get their agreement.'
$msg += ''
$msg += 'Do not silence this by reverting the file and re-applying the same edit. A change made'
$msg += 'since the task baseline stays visible, committed or not, for as long as this session'
$msg += 'carries this task.'
$msg += ''
$msg += 'If the owner has looked at this specific change and agreed the test should lose those'
$msg += 'assertions, they can authorize exactly it, and only it:'
$msg += '  bash .claude/tools/baseline.sh allow-test-change <task> <checkout>/<path> "<their words>"'
$msg += 'That records the file and the exact content it ends at. One more edit and it stops applying.'
[Console]::Error.WriteLine(($msg -join "`n"))
exit 2

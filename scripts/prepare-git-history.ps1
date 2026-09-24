[CmdletBinding()]
param(
    [string]$BaselineCommit = '654bdadc9ce673c072991298ad410687fdd6213b'
)

$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path

function Invoke-Git {
    param(
        [Parameter(Mandatory = $true)][string[]]$Arguments,
        [switch]$AllowFailure
    )

    $savedErrorActionPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Continue'
        $output = & git -C $repoRoot @Arguments 2>&1
        $exitCode = $LASTEXITCODE
        if (-not $AllowFailure -and $exitCode -ne 0) {
            throw "git $($Arguments -join ' ') failed (exit $exitCode):`n$($output -join [Environment]::NewLine)"
        }
        return [pscustomobject]@{
            ExitCode = $exitCode
            Output = @($output)
        }
    } finally {
        $ErrorActionPreference = $savedErrorActionPreference
    }
}

$shallowResult = Invoke-Git -Arguments @('rev-parse', '--is-shallow-repository')
$isShallowText = (($shallowResult.Output -join '').Trim()).ToLowerInvariant()
if ($isShallowText -notin @('true', 'false')) {
    throw "Unable to determine whether repository is shallow: $($shallowResult.Output -join [Environment]::NewLine)"
}

$wasShallow = $isShallowText -eq 'true'
if ($wasShallow) {
    $remote = Invoke-Git -Arguments @('remote', 'get-url', 'origin') -AllowFailure
    if ($remote.ExitCode -ne 0 -or -not (($remote.Output -join '').Trim())) {
        throw 'Release checkout is shallow and has no usable origin remote for history hydration.'
    }
    Invoke-Git -Arguments @('fetch', '--unshallow', '--no-tags', 'origin') | Out-Null
}

$stillShallow = ((Invoke-Git -Arguments @('rev-parse', '--is-shallow-repository')).Output -join '').Trim().ToLowerInvariant()
if ($stillShallow -ne 'false') {
    throw 'Git history hydration did not produce a complete repository.'
}

$baseline = Invoke-Git -Arguments @('cat-file', '-e', "$BaselineCommit^{commit}") -AllowFailure
if ($baseline.ExitCode -ne 0) {
    throw "Required release-lint baseline commit is unavailable after history hydration: $BaselineCommit"
}

$ancestor = Invoke-Git -Arguments @('merge-base', '--is-ancestor', $BaselineCommit, 'HEAD') -AllowFailure
if ($ancestor.ExitCode -ne 0) {
    throw "Required release-lint baseline is not an ancestor of HEAD: $BaselineCommit"
}

$status = Invoke-Git -Arguments @('status', '--porcelain')
if ($status.Output.Count -gt 0 -and ($status.Output -join '').Trim()) {
    throw "Git history hydration changed repository state:`n$($status.Output -join [Environment]::NewLine)"
}

Write-Output "GIT_HISTORY_VERIFY=PASS baseline=$BaselineCommit shallowBefore=$($wasShallow.ToString().ToLowerInvariant())"

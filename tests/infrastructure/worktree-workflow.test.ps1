[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$commonGitDir = (& git rev-parse --path-format=absolute --git-common-dir).Trim()
if ($LASTEXITCODE -ne 0 -or -not $commonGitDir) { throw 'Test must run inside a Git worktree.' }
$repositoryRoot = Split-Path -Parent $commonGitDir
$worktreeRoot = (& git rev-parse --path-format=absolute --show-toplevel).Trim()
if ($LASTEXITCODE -ne 0 -or -not $worktreeRoot) { throw 'Test must resolve its current worktree root.' }
$newScript = Join-Path $worktreeRoot 'scripts\worktree-new.ps1'
$removeScript = Join-Path $worktreeRoot 'scripts\worktree-remove.ps1'
$taskName = "workflow-smoke-$PID"
$worktreeName = "test-$taskName"
$worktreePath = Join-Path $repositoryRoot ".worktrees\$worktreeName"
$branch = "test/$taskName"

try {
    & $newScript -Kind test -TaskName $taskName -Base main
    if (-not (Test-Path -LiteralPath $worktreePath -PathType Container)) {
        throw "Expected linked worktree was not created: $worktreePath"
    }

    & $removeScript -WorktreeName $worktreeName -Confirm:$false
    if (Test-Path -LiteralPath $worktreePath) {
        throw "Expected linked worktree was not removed: $worktreePath"
    }

    Write-Output 'WORKTREE_WORKFLOW_TEST=PASS'
}
finally {
    if (Test-Path -LiteralPath $worktreePath) {
        git -C $repositoryRoot worktree remove --force $worktreePath 2>$null
    }
    git -C $repositoryRoot branch -D $branch 2>$null
}

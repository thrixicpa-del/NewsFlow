[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [ValidatePattern('^[a-z0-9][a-z0-9-]{1,62}$')]
    [string]$TaskName,

    [ValidateSet('feature', 'fix', 'infra', 'test', 'release')]
    [string]$Kind = 'infra',

    [string]$Base = 'main'
)

$ErrorActionPreference = 'Stop'

function Invoke-Git {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Arguments)
    & git @Arguments
    if ($LASTEXITCODE -ne 0) { throw "git $($Arguments -join ' ') failed." }
}

$commonGitDir = (& git rev-parse --path-format=absolute --git-common-dir).Trim()
if ($LASTEXITCODE -ne 0 -or -not $commonGitDir) { throw 'Run this command inside a Git worktree.' }
$repositoryRoot = Split-Path -Parent $commonGitDir
$worktreesRoot = Join-Path $repositoryRoot '.worktrees'
$branch = "$Kind/$TaskName"
$target = Join-Path $worktreesRoot "$Kind-$TaskName"

& git -C $repositoryRoot check-ignore -q --no-index -- '.worktrees/probe'
if ($LASTEXITCODE -ne 0) { throw '.worktrees must be ignored before a linked worktree can be created.' }
if (-not (Test-Path -LiteralPath $worktreesRoot)) {
    New-Item -ItemType Directory -Path $worktreesRoot | Out-Null
}
if (Test-Path -LiteralPath $target) { throw "Target worktree already exists: $target" }

$existingBranch = & git -C $repositoryRoot show-ref --verify --quiet "refs/heads/$branch"
if ($LASTEXITCODE -eq 0) { throw "Branch already exists and is not reused automatically: $branch" }
if ($LASTEXITCODE -gt 1) { throw "Could not inspect branch: $branch" }

Invoke-Git -C $repositoryRoot rev-parse --verify "$Base^{commit}"
Invoke-Git -C $repositoryRoot worktree add -b $branch $target $Base

Write-Output "WORKTREE CREATED"
Write-Output "BRANCH: $branch"
Write-Output "PATH: $target"

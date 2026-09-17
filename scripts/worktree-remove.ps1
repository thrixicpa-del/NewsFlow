[CmdletBinding(SupportsShouldProcess)]
param(
    [Parameter(Mandatory)]
    [ValidatePattern('^(feature|fix|infra|test|release)-[a-z0-9][a-z0-9-]{1,62}$')]
    [string]$WorktreeName,

    [switch]$Force
)

$ErrorActionPreference = 'Stop'
$commonGitDir = (& git rev-parse --path-format=absolute --git-common-dir).Trim()
if ($LASTEXITCODE -ne 0 -or -not $commonGitDir) { throw 'Run this command inside a Git worktree.' }
$repositoryRoot = Split-Path -Parent $commonGitDir
$worktreesRoot = [IO.Path]::GetFullPath((Join-Path $repositoryRoot '.worktrees'))
$target = [IO.Path]::GetFullPath((Join-Path $worktreesRoot $WorktreeName))

if (-not $target.StartsWith($worktreesRoot + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
    throw "Refusing to remove a path outside .worktrees: $target"
}
if (-not (Test-Path -LiteralPath $target -PathType Container)) { throw "Worktree does not exist: $target" }

$registered = & git -C $repositoryRoot worktree list --porcelain
if ($LASTEXITCODE -ne 0) { throw 'Could not inspect registered worktrees.' }
$registeredPaths = @(
    $registered |
        Where-Object { $_.StartsWith('worktree ') } |
        ForEach-Object { [IO.Path]::GetFullPath($_.Substring('worktree '.Length)) }
)
if ($registeredPaths -notcontains $target) { throw "Refusing to remove an unregistered worktree: $target" }

if ($PSCmdlet.ShouldProcess($target, 'Remove Git worktree')) {
    $arguments = @('-C', $repositoryRoot, 'worktree', 'remove')
    if ($Force) { $arguments += '--force' }
    $arguments += $target
    & git @arguments
    if ($LASTEXITCODE -ne 0) { throw "git worktree remove failed for $target" }
    Write-Output "WORKTREE REMOVED: $target"
}

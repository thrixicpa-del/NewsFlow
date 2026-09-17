[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
& git worktree list --porcelain
if ($LASTEXITCODE -ne 0) { throw 'git worktree list failed.' }

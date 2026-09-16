[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot
git config core.hooksPath .githooks
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Write-Output 'GIT_HOOKS=INSTALLED'

[CmdletBinding()]
param(
    [string]$Python = "python"
)

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
& $Python -m pip_audit -r (Join-Path $repoRoot 'requirements.txt') --strict
exit $LASTEXITCODE

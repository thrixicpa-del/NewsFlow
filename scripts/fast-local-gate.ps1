[CmdletBinding()]
param(
    [string[]]$Paths = @(),
    [switch]$Staged
)

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

if ($Staged) {
    $Paths = @(git diff --cached --name-only --diff-filter=ACMR)
}

# Always scan the tracked tree: a staged diff cannot reveal an older secret
# accidentally committed by a branch merge. The scanner is read-only and fast.
python scripts/secret-scan.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$pythonFiles = @($Paths | Where-Object { $_ -match '\.py$' -and (Test-Path -LiteralPath $_ -PathType Leaf) })
if ($pythonFiles.Count -gt 0) {
    python -m ruff check @pythonFiles
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

$frontendChanged = @($Paths | Where-Object { $_ -match '^studio-ui-remotion-verify/(src|electron|package\.json|pnpm-lock\.yaml|pnpm-workspace\.yaml|index\.html)' }).Count -gt 0
if ($frontendChanged) {
    pnpm --dir studio-ui-remotion-verify verify:security
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    pnpm --dir studio-ui-remotion-verify typecheck
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

Write-Output 'FAST_LOCAL_GATE=PASS'

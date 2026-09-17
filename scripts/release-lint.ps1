[CmdletBinding()]
param(
    [string]$BaseRef = '654bdad',
    [string[]]$Files = @()
)

$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location $repoRoot

if ($Files.Count -eq 0) {
    $base = (git merge-base HEAD $BaseRef).Trim()
    if (-not $base) { throw "RELEASE_LINT=FAIL cannot resolve merge base for $BaseRef" }
    $Files = @(git diff --name-only --diff-filter=A "$base...HEAD")
}

$pythonFiles = @(
    $Files |
    ForEach-Object { $_.Replace('\', '/') } |
    Where-Object {
        $_.EndsWith('.py') -and ($_ -like 'scriptor/*' -or $_ -like 'tests/*' -or $_ -like 'scripts/*')
    } |
    Sort-Object -Unique
)

if ($pythonFiles.Count -eq 0) {
    Write-Output 'RELEASE_LINT=PASS no candidate Python additions'
    exit 0
}

& python -m ruff check @pythonFiles
if ($LASTEXITCODE -ne 0) {
    throw "RELEASE_LINT=FAIL changed Python files: $($pythonFiles -join ', ')"
}
Write-Output "RELEASE_LINT=PASS candidate additions $($pythonFiles -join ', ')"

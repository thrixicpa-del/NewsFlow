[CmdletBinding()]
param(
    [string]$ResultsRoot,
    [string]$PackagedExe,
    [switch]$IncludeSourceE2E,
    [switch]$DryRun
)

$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
if ([string]::IsNullOrWhiteSpace($ResultsRoot)) {
    $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
    $ResultsRoot = Join-Path $repoRoot ".artifacts/allure/$stamp/allure-results"
}

$productionRoot = Join-Path $env:LOCALAPPDATA 'NewsFlow'
$resolvedResultsRoot = [System.IO.Path]::GetFullPath($ResultsRoot)
if ((Test-Path -LiteralPath $productionRoot) -and $resolvedResultsRoot.StartsWith((Resolve-Path -LiteralPath $productionRoot).Path, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw 'ALLURE_REPORT=FAIL results root must not be inside production NewsFlow storage.'
}

$arguments = @('scripts/allure_reporting.py', '--results-root', $resolvedResultsRoot)
if ($IncludeSourceE2E) { $arguments += '--include-source-e2e' }
if (-not [string]::IsNullOrWhiteSpace($PackagedExe)) { $arguments += @('--packaged-exe', $PackagedExe) }
if ($DryRun) { $arguments += '--dry-run' }

$output = & python @arguments 2>&1
if ($LASTEXITCODE -ne 0) {
    throw "ALLURE_REPORT=FAIL`n$($output -join [Environment]::NewLine)"
}
if ($DryRun) {
    Write-Output $output
    exit 0
}

$reportRoot = Join-Path (Split-Path -Parent $resolvedResultsRoot) 'allure-report'
& allure generate $resolvedResultsRoot --clean -o $reportRoot
if ($LASTEXITCODE -ne 0) { throw 'ALLURE_REPORT=FAIL allure generate failed.' }
Write-Output 'ALLURE_REPORT=PASS'
Write-Output "RESULTS=$resolvedResultsRoot"
Write-Output "REPORT=$reportRoot"

[CmdletBinding()]
param(
    [ValidateSet('Capture', 'Verify')]
    [string]$Mode = 'Verify',
    [string]$ProductionRoot = (Join-Path $env:LOCALAPPDATA 'NewsFlow'),
    [string]$SnapshotPath = (Join-Path ([System.IO.Path]::GetTempPath()) 'newsflow-production-integrity.json')
)

$ErrorActionPreference = 'Stop'
$criticalFiles = @('settings.json', 'covers-library.json', 'footage-index-status.json')

if (-not (Test-Path -LiteralPath $ProductionRoot -PathType Container)) {
    throw "Production root does not exist: $ProductionRoot"
}

function Get-Sha256 {
    param([Parameter(Mandatory = $true)][string]$Path)

    $hasher = [System.Security.Cryptography.SHA256]::Create()
    $stream = [System.IO.File]::OpenRead($Path)
    try {
        return [System.BitConverter]::ToString($hasher.ComputeHash($stream)).Replace('-', '')
    } finally {
        $stream.Dispose()
        $hasher.Dispose()
    }
}

function Get-CriticalInventory {
    param([Parameter(Mandatory = $true)][string]$Root)

    $files = [ordered]@{}
    foreach ($name in $criticalFiles) {
        $path = Join-Path $Root $name
        if (Test-Path -LiteralPath $path -PathType Leaf) {
            $files[$name] = [ordered]@{
                exists = $true
                sha256 = Get-Sha256 -Path $path
            }
        } else {
            $files[$name] = [ordered]@{
                exists = $false
                sha256 = $null
            }
        }
    }
    return [ordered]@{
        format = 1
        productionRoot = (Resolve-Path -LiteralPath $Root).Path
        files = $files
    }
}

$current = Get-CriticalInventory -Root $ProductionRoot
if ($Mode -eq 'Capture') {
    $parent = Split-Path -Parent $SnapshotPath
    if ($parent) { New-Item -ItemType Directory -Path $parent -Force | Out-Null }
    $current | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $SnapshotPath -Encoding utf8
    Write-Output "PRODUCTION_INTEGRITY_CAPTURE=PASS $SnapshotPath"
    exit 0
}

if (-not (Test-Path -LiteralPath $SnapshotPath -PathType Leaf)) {
    throw "Integrity snapshot is missing: $SnapshotPath"
}

$expected = Get-Content -LiteralPath $SnapshotPath -Raw | ConvertFrom-Json
$changed = @()
foreach ($name in $criticalFiles) {
    $before = $expected.files.$name
    $after = $current.files[$name]
    if (($before.exists -ne $after.exists) -or ($before.sha256 -ne $after.sha256)) {
        $changed += $name
    }
}

if ($changed.Count -gt 0) {
    [Console]::Error.WriteLine("PRODUCTION_WRITE_GUARD=FAIL changed=" + ($changed -join ','))
    exit 1
}

Write-Output 'PRODUCTION_WRITE_GUARD=PASS'

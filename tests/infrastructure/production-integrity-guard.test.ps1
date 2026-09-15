$ErrorActionPreference = 'Stop'

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$guard = Join-Path $repoRoot 'scripts\check-production-integrity.ps1'
$root = Join-Path ([System.IO.Path]::GetTempPath()) ("newsflow-production-guard-" + [guid]::NewGuid().ToString('N'))
$production = Join-Path $root 'production'
$snapshot = Join-Path $root 'integrity.json'

New-Item -ItemType Directory -Path $production -Force | Out-Null
try {
    @{
        'settings.json' = '{"schema_version":4}'
        'covers-library.json' = '{"covers":[]}'
        'footage-index-status.json' = '{"entries":0}'
    }.GetEnumerator() | ForEach-Object {
        Set-Content -LiteralPath (Join-Path $production $_.Key) -Value $_.Value -NoNewline -Encoding utf8
    }

    & powershell -NoProfile -ExecutionPolicy Bypass -File $guard -Mode Capture -ProductionRoot $production -SnapshotPath $snapshot
    if ($LASTEXITCODE -ne 0) { throw 'Guard could not capture a disposable integrity snapshot.' }

    & powershell -NoProfile -ExecutionPolicy Bypass -File $guard -Mode Verify -ProductionRoot $production -SnapshotPath $snapshot
    if ($LASTEXITCODE -ne 0) { throw 'Guard rejected unchanged disposable storage.' }

    Set-Content -LiteralPath (Join-Path $production 'covers-library.json') -Value '{"covers":["unexpected"]}' -NoNewline -Encoding utf8
    & powershell -NoProfile -ExecutionPolicy Bypass -File $guard -Mode Verify -ProductionRoot $production -SnapshotPath $snapshot
    if ($LASTEXITCODE -eq 0) { throw 'Guard accepted a mutated critical file.' }

    Write-Output 'PRODUCTION_INTEGRITY_GUARD_TEST=PASS'
}
finally {
    if (Test-Path -LiteralPath $root) {
        Remove-Item -LiteralPath $root -Recurse -Force
    }
}

[CmdletBinding()]
param(
    [ValidateSet('TEST', 'RC', 'STABLE')]
    [string]$Channel = 'TEST',
    [ValidatePattern('^\d{2,}$')]
    [string]$Rc = '01',
    [string]$OutputRoot,
    [switch]$DryRun
)

$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$appRoot = Join-Path $repoRoot 'studio-ui-remotion-verify'
$powerShellExecutable = if ($env:WINDIR) {
    Join-Path $env:WINDIR 'System32\WindowsPowerShell\v1.0\powershell.exe'
} else {
    (Get-Command pwsh -ErrorAction Stop).Source
}
if (-not (Test-Path -LiteralPath $powerShellExecutable -PathType Leaf)) {
    throw "RELEASE GATE - FAIL: required PowerShell host is unavailable: $powerShellExecutable"
}
$steps = @(
    'repo-state',
    'toolchain',
    'lfs-hydration',
    'production-integrity-capture',
    'dependencies-install',
    'dependencies',
    'dependencies-python',
    'lint',
    'frontend-typecheck',
    'python-suite',
    'frontend-suite',
    'visual-regression',
    'security',
    'security-secrets',
    'performance',
    'core-runtime',
    'immutable-package',
    'artifact-manifest',
    'packaged-smoke',
    'production-integrity-verify'
)

if ($DryRun) {
    [ordered]@{ format = 1; requiresPackage = $true; steps = $steps } | ConvertTo-Json -Compress
    exit 0
}

if ([string]::IsNullOrWhiteSpace($OutputRoot)) {
    throw 'RELEASE GATE - FAIL: -OutputRoot is required for an immutable package.'
}
if (-not (Test-Path -LiteralPath $OutputRoot -PathType Container)) {
    throw "RELEASE GATE - FAIL: output root does not exist: $OutputRoot"
}

$resolvedOutputRoot = (Resolve-Path -LiteralPath $OutputRoot).Path
$productionRoot = Join-Path $env:LOCALAPPDATA 'NewsFlow'
if ((Test-Path -LiteralPath $productionRoot) -and $resolvedOutputRoot.StartsWith((Resolve-Path -LiteralPath $productionRoot).Path, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw 'RELEASE GATE - FAIL: output root must not be inside production NewsFlow storage.'
}

function Invoke-GateStep {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][string]$FilePath,
        [string[]]$Arguments = @(),
        [string]$WorkingDirectory = $repoRoot,
        [hashtable]$Environment = @{}
    )

    $saved = @{}
    $savedErrorActionPreference = $ErrorActionPreference
    try {
        Push-Location $WorkingDirectory
        foreach ($entry in $Environment.GetEnumerator()) {
            $saved[$entry.Key] = [Environment]::GetEnvironmentVariable($entry.Key, 'Process')
            [Environment]::SetEnvironmentVariable($entry.Key, [string]$entry.Value, 'Process')
        }
        # pnpm emits its nested command trace on stderr even when it exits 0.
        # Gate native programs by their exit code, not PowerShell's treatment of
        # that informational stderr record under the outer fail-closed policy.
        $ErrorActionPreference = 'Continue'
        $output = & $FilePath @Arguments 2>&1
        if ($LASTEXITCODE -ne 0) {
            throw "$Name failed (exit $LASTEXITCODE):`n$($output -join [Environment]::NewLine)"
        }
    } finally {
        $ErrorActionPreference = $savedErrorActionPreference
        foreach ($entry in $saved.GetEnumerator()) {
            [Environment]::SetEnvironmentVariable($entry.Key, $entry.Value, 'Process')
        }
        Pop-Location
    }
}

$integritySnapshot = Join-Path ([System.IO.Path]::GetTempPath()) "newsflow-release-gate-$PID.json"
$integrityCaptured = $false
$failure = $null
try {
    Set-Location $repoRoot
    if (git status --porcelain) { throw 'repo-state failed: release gate requires a clean Git worktree.' }
    Invoke-GateStep -Name 'toolchain' -FilePath $powerShellExecutable -Arguments @('-ExecutionPolicy', 'Bypass', '-File', 'scripts/verify-toolchain.ps1')
    Invoke-GateStep -Name 'lfs-hydration' -FilePath $powerShellExecutable -Arguments @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', 'scripts/prepare-lfs-assets.ps1')
    Invoke-GateStep -Name 'production-integrity-capture' -FilePath $powerShellExecutable -Arguments @('-ExecutionPolicy', 'Bypass', '-File', 'scripts/check-production-integrity.ps1', '-Mode', 'Capture', '-SnapshotPath', $integritySnapshot)
    $integrityCaptured = $true
    Invoke-GateStep -Name 'dependencies-install' -FilePath 'pnpm' -Arguments @('--dir', $appRoot, 'install', '--frozen-lockfile')
    Invoke-GateStep -Name 'dependencies' -FilePath 'pnpm' -Arguments @('--dir', $appRoot, 'verify:dependencies')
    Invoke-GateStep -Name 'dependencies-python' -FilePath $powerShellExecutable -Arguments @('-ExecutionPolicy', 'Bypass', '-File', 'scripts/audit-python-dependencies.ps1')
    Invoke-GateStep -Name 'lint' -FilePath $powerShellExecutable -Arguments @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', 'scripts/release-lint.ps1')
    Invoke-GateStep -Name 'frontend-typecheck' -FilePath 'pnpm' -Arguments @('--dir', $appRoot, 'typecheck')
    Invoke-GateStep -Name 'python-suite' -FilePath 'python' -Arguments @('tests/run_isolated.py', 'discover', '-s', 'tests', '-q')
    Invoke-GateStep -Name 'frontend-suite' -FilePath 'pnpm' -Arguments @('--dir', $appRoot, 'test:ui')
    Invoke-GateStep -Name 'visual-regression' -FilePath 'pnpm' -Arguments @('--dir', $appRoot, 'verify:workstation-visuals')
    Invoke-GateStep -Name 'security' -FilePath 'pnpm' -Arguments @('--dir', $appRoot, 'verify:security')
    Invoke-GateStep -Name 'security-secrets' -FilePath 'pnpm' -Arguments @('--dir', $appRoot, 'verify:secrets')
    Invoke-GateStep -Name 'performance' -FilePath 'python' -Arguments @('tests/run_isolated.py', 'tests.test_performance_baselines', 'tests.test_performance_paths', 'tests.test_montage_benchmark', '-v')
    Invoke-GateStep -Name 'core-runtime' -FilePath 'pnpm' -Arguments @('--dir', $appRoot, 'verify:core-runtime')
    Invoke-GateStep -Name 'immutable-package' -FilePath 'node' -Arguments @('scripts/package-immutable-rc.mjs', '--output-root', $resolvedOutputRoot, '--type', $Channel, '--rc', $Rc, '--target', 'portable') -WorkingDirectory $appRoot

    $package = Get-Content -Raw (Join-Path $appRoot 'package.json') | ConvertFrom-Json
    $sha = (git -C $repoRoot rev-parse --short=8 HEAD).Trim()
    $candidateRoot = Join-Path $resolvedOutputRoot "NewsFlow-$($package.version)-$($Channel.ToLowerInvariant())-rc$Rc-$sha"
    # The portable NSIS bootstrapper intentionally does not forward arbitrary
    # Chromium command-line flags. Smoke the actual Electron binary contained
    # by that immutable portable package, so CDP verifies packaged runtime
    # instead of the bootstrapper's flag handling.
    $packagedSmokeRoot = Join-Path $candidateRoot 'win-unpacked'
    $executable = Get-ChildItem -LiteralPath $packagedSmokeRoot -File -Filter '*.exe' |
        Where-Object { $_.Name -notmatch 'uninstall' } |
        Select-Object -First 1
    if (-not $executable) { throw 'packaged-smoke failed: immutable package does not contain a launchable unpacked Electron EXE.' }
    Invoke-GateStep -Name 'artifact-manifest' -FilePath 'node' -Arguments @('scripts/verify-immutable-rc.mjs', '--directory', $candidateRoot) -WorkingDirectory $appRoot
    Invoke-GateStep -Name 'packaged-smoke' -FilePath 'python' -Arguments @('tests/run_isolated.py', 'tests.test_electron_e2e', '-v') -Environment @{
        NEWSFLOW_RUN_ELECTRON_E2E = '1'
        NEWSFLOW_E2E_TARGET = 'packaged'
        NEWSFLOW_PACKAGED_EXE = $executable.FullName
    }
} catch {
    $failure = $_
} finally {
    if ($integrityCaptured) {
        try {
            Invoke-GateStep -Name 'production-integrity-verify' -FilePath $powerShellExecutable -Arguments @('-ExecutionPolicy', 'Bypass', '-File', 'scripts/check-production-integrity.ps1', '-Mode', 'Verify', '-SnapshotPath', $integritySnapshot)
        } catch {
            if (-not $failure) { $failure = $_ }
        }
    }
    Remove-Item -LiteralPath $integritySnapshot -Force -ErrorAction SilentlyContinue
}

if ($failure) {
    [Console]::Error.WriteLine("RELEASE GATE - FAIL`n$($failure.Exception.Message)")
    exit 1
}

Write-Output 'RELEASE GATE - PASS'

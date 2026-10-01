[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$lfsPointerHeader = 'version https://git-lfs.github.com/spec/v1'

function Invoke-GitLfs {
    param([Parameter(Mandatory = $true)][string[]]$Arguments)

    $savedErrorActionPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Continue'
        $output = & git -C $repoRoot lfs @Arguments 2>&1
        if ($LASTEXITCODE -ne 0) {
            throw "git lfs $($Arguments -join ' ') failed (exit $LASTEXITCODE):`n$($output -join [Environment]::NewLine)"
        }
        return @($output)
    } finally {
        $ErrorActionPreference = $savedErrorActionPreference
    }
}

function Test-LfsPointerFile {
    param([Parameter(Mandatory = $true)][string]$Path)

    $stream = [System.IO.File]::OpenRead($Path)
    try {
        $buffer = New-Object byte[] 128
        $read = $stream.Read($buffer, 0, $buffer.Length)
        if ($read -le 0) { return $false }
        $prefix = [System.Text.Encoding]::ASCII.GetString($buffer, 0, $read)
        return $prefix.StartsWith($lfsPointerHeader, [System.StringComparison]::Ordinal)
    } finally {
        $stream.Dispose()
    }
}

function Get-Sha256Hex {
    param([Parameter(Mandatory = $true)][string]$Path)

    # This release gate is deliberately launched in a fresh Windows
    # PowerShell host.  Do not depend on cmdlet autoload there: some hardened
    # hosts expose the .NET cryptography API while `Get-FileHash` is not made
    # available.  Hash the stream directly so the LFS integrity contract is
    # the same in interactive and release-gate processes.
    $algorithm = [System.Security.Cryptography.SHA256]::Create()
    $stream = [System.IO.File]::OpenRead($Path)
    try {
        $hash = $algorithm.ComputeHash($stream)
        return ([System.BitConverter]::ToString($hash) -replace '-', '').ToUpperInvariant()
    } finally {
        $stream.Dispose()
        $algorithm.Dispose()
    }
}

Invoke-GitLfs -Arguments @('version') | Out-Null
Invoke-GitLfs -Arguments @('pull') | Out-Null
Invoke-GitLfs -Arguments @('fsck') | Out-Null

$entries = @()
foreach ($line in (Invoke-GitLfs -Arguments @('ls-files', '--long'))) {
    $text = [string]$line
    if ($text -notmatch '^([0-9a-fA-F]{64})\s+[-*]\s+(.+)$') {
        throw "Unable to parse Git LFS tracked entry: $text"
    }
    $entries += [pscustomobject]@{
        Oid = $Matches[1].ToUpperInvariant()
        RelativePath = $Matches[2]
    }
}

if ($entries.Count -eq 0) {
    throw 'No Git LFS tracked files were found; release checkout is incomplete.'
}

if (-not ($entries.RelativePath -contains 'assets/ffmpeg.exe')) {
    throw 'Required Git LFS asset is not tracked in this checkout: assets/ffmpeg.exe'
}

foreach ($entry in $entries) {
    $path = Join-Path $repoRoot $entry.RelativePath
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "Git LFS payload is missing: $($entry.RelativePath)"
    }
    if (Test-LfsPointerFile -Path $path) {
        throw "Git LFS payload is still a pointer: $($entry.RelativePath)"
    }
    $actual = Get-Sha256Hex -Path $path
    if ($actual -ne $entry.Oid) {
        throw "Git LFS payload hash mismatch: $($entry.RelativePath); expected $($entry.Oid); found $actual"
    }
}

$status = & git -C $repoRoot status --porcelain 2>&1
if ($LASTEXITCODE -ne 0) {
    throw "git status failed after LFS hydration: $($status -join [Environment]::NewLine)"
}
if ($status) {
    throw "Git LFS hydration changed repository state:`n$($status -join [Environment]::NewLine)"
}

Write-Output "GIT_LFS_VERIFY=PASS tracked=$($entries.Count)"

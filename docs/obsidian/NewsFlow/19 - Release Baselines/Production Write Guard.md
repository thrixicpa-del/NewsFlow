# Production Write Guard

## Purpose

Automated work must never silently change the canonical NewsFlow profile. The guard fingerprints only metadata, never file content:

- `settings.json`
- `covers-library.json`
- `footage-index-status.json`

Any changed existence state or SHA-256 after an automated run is a `PRODUCTION_WRITE_GUARD=FAIL` incident. It overrides an otherwise successful test result.

## Python test runner

`tests/run_isolated.py` captures the authoritative `%LOCALAPPDATA%\\NewsFlow` hashes before it creates its disposable test root and compares them after the child test exits. A mismatch returns exit code `91` and names the changed files without exposing their contents.

Use this runner for Python tests:

```powershell
python tests/run_isolated.py discover -s tests -q
```

## Stand-alone check

For a gate that spans arbitrary tooling, capture an integrity snapshot outside production storage and verify it afterwards:

```powershell
$snapshot = 'D:\NewsFlow-RC\diagnostics\release-integrity.json'
powershell -ExecutionPolicy Bypass -File scripts/check-production-integrity.ps1 -Mode Capture -SnapshotPath $snapshot
# run the isolated operation
powershell -ExecutionPolicy Bypass -File scripts/check-production-integrity.ps1 -Mode Verify -SnapshotPath $snapshot
```

`check-production-integrity.ps1` only reads the production files. Its snapshot is metadata-only and must live outside `%LOCALAPPDATA%\\NewsFlow`.

## Incident response

1. Stop the automated lane immediately; do not accept its results.
2. Preserve the integrity snapshot and the changed production files as evidence; do not overwrite them.
3. Trace the offending process and configuration, then reproduce solely against a disposable root.
4. Add a regression test before any repair.
5. Only a separately approved recovery task may alter production data.

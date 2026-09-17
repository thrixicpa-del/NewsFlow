# Release Gate

## Authority

`scripts/release-gate.ps1` is the only command permitted to declare a TEST, RC or STABLE package release-ready. It is fail-closed: a failed or skipped required step yields `RELEASE GATE - FAIL`; no script may emit a manual-ready status instead.

The gate requires a clean Git worktree and an explicit existing output root outside production NewsFlow storage. It captures the production integrity inventory before its work and verifies the same inventory after every outcome.

## Required sequence

1. repository state and exact toolchain;
2. production-integrity capture;
3. Node and Python dependency checks;
4. lint of all changed candidate Python files, frontend typecheck, isolated Python suite, frontend suite and visual regression;
5. security and secret checks, performance checks and current core runtime validation;
6. immutable package reservation and packaging;
7. independent manifest/artifact hash validation;
8. packaged Electron smoke under an isolated `NEWSFLOW_TEST_ROOT`;
9. production-integrity verification.

`-DryRun` prints this ordered contract only. It never invokes a package command and never emits a release PASS result.

## Usage

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/release-gate.ps1 `
  -Channel TEST -Rc 02 -OutputRoot 'D:\NewsFlow Studio\Candidates'
```

The candidate is commit-addressed and immutable. The gate verifies its delivered EXE and all recorded artifact hashes before connecting packaged Electron E2E. It never reads production credentials, OAuth, media indexes, face images or business state; the packaged smoke receives only a disposable user-data root.

Hosted CI can run source gates, but actual package and native smoke evidence must come from a controlled Windows machine or dedicated isolated runner.

## Legacy lint boundary

`scripts/release-lint.ps1` resolves the merge-base against the Phase 0 engineering baseline (`654bdad`) and runs Ruff on every new Python artifact under `scriptor/`, `tests/` and `scripts/`. It fails on an added candidate source or test that violates the configured lint rules. Existing large runtime files have pre-existing whole-file lint debt; attempting partial-diff lint still emits file-wide diagnostics such as import-block ordering. Those legacy files are instead covered by the gate's complete isolated runtime, contract and security suites, and are not silently reformatted by infrastructure work. Broad cleanup remains a separate, reviewed task. Supplying `-Files` explicitly is reserved for a focused local check and lint-runs those named Python files directly.

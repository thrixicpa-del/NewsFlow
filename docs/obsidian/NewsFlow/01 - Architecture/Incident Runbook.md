# Incident Runbook

## Trigger

Use this runbook for an unexplained production hash change, destructive action
failure, current-versus-legacy runtime ambiguity, data resurrection, packaged
candidate mismatch, security gate failure, or a regression with user-data
risk.

## Contain and preserve

1. Stop affected NewsFlow processes when continued writes could worsen state.
2. Do not delete, reset, rebuild over, or accept changed production data as a
   new baseline.
3. Capture current hashes using `check-production-integrity.ps1`, record the
   executable/core-bin hash, Git revision, process paths, timestamps, and
   relevant redacted logs.
4. Make a raw recovery copy before any permitted production repair.

## Diagnose safely

Reproduce only from a disposable copy with explicit `NEWSFLOW_TEST_ROOT`.
Trace UI → handler → IPC → bridge → service → worker → storage, identify the
actual writer/reader, and compare current/legacy contracts. Do not infer a
writer merely from a matching displayed version string.

## Recover and close

Apply the smallest proven repair, preferably surgical. Verify state identities,
tombstones, restart behavior, package/runtime guards, and before/after hashes.
Add a regression test that fails on the original path and update the relevant
ADR or root-cause record. If evidence does not prove a safe repair, declare
`REAL USER ACTION REQUIRED` with the exact risk and available recovery choices.

# Engineering Delivery Workflow

This page is the operational entry point for NewsFlow production engineering.
It links to the current documents instead of restating their contracts. The
project-local Obsidian tree is the documentation source of truth; the checked
out source, tests, and immutable artifact evidence remain authoritative for
runtime behavior.

## Required policies and runbooks

| Area | Current document | Operating rule |
| --- | --- | --- |
| Engineering Architecture | [[Runtime Topology]] | Preserve the current renderer → IPC → bridge → service → worker → storage path. |
| Git Workflow / Branch and Worktree Policy | [[Git Workflow and Governance]] | One task, one prefixed branch, one linked worktree; no force-push of `main`. |
| Testing Strategy | [[Testing Strategy]] | Tests use `tests/run_isolated.py`; source, UI, visual, and packaged evidence remain separate lanes. |
| Environment Isolation | [[Environment Isolation Contract]] | Test roots are explicit and never fall back to production storage. |
| Release Process | [[Release Artifact Policy]] | A candidate is commit-addressed, immutable, externally rooted, and never overwritten. |
| Release Gate | [[Release Gate]] | `scripts/release-gate.ps1` is the only release-ready authority. |
| Build Manifest | [[Build Manifest and Verification]] | The manifest and artifact hashes are revalidated after packaging. |
| Visual Testing | [[Visual Testing]] | Approved baselines change only through an explicit test-only command and an independent compare. |
| Security | [[Security Gates]] | Secrets, renderer privileges, dependencies, and navigation are fail-closed release concerns. |
| Observability | [[Observability]] | Local redacted traces are diagnostic evidence, not external telemetry. |
| Backup/Restore | [[Backup and Restore]] | Back up first; restore only through an explicit, verified, scoped recovery action. |
| Migration Policy | [[Migration Policy]] | Current runtime wins; legacy reads are explicit, bounded, and cannot auto-promote state. |
| Incident Runbook | [[Incident Runbook]] | Preserve evidence, contain writes, diagnose on copies, then add a regression before recovery. |
| Provider Failure Runbook | [[Provider Failure Runbook]] | Classify provider faults without exposing credentials or mutating unrelated jobs. |

## Delivery sequence

1. Trace the current runtime path and define the narrow change.
2. Add a focused regression first where behavior changes or a defect is found.
3. Run the matching isolated, UI, visual, security, or frozen-core lane.
4. Record an ADR for a durable architecture or safety decision.
5. Commit one evidence-bounded change; preserve production integrity before and after significant work.
6. Use the authoritative release gate only when an immutable candidate is requested.

`current verified runtime` always wins over a legacy implementation. Neither a
backup nor an old executable may silently replace source, current core-bin,
schema-fenced storage, or an immutable release artifact.

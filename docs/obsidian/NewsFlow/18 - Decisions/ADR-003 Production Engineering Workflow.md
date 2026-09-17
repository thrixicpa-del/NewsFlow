# ADR-003 — Production Engineering Workflow

**Status:** accepted 2026-09-17
**Decision:** current verified runtime, isolated evidence, and immutable
artifacts are the authority for production engineering delivery.

## Context

NewsFlow combines a React/Electron UI, typed IPC, Python bridge/services,
frozen core-bin, provider workers, and persistent user data. Historical
executables and storage can have matching visible version text while retaining
incompatible behavior. Source-only tests also cannot prove a packaged release
or protect production data unless their environment boundary is explicit.

## Decision

1. [[Engineering Delivery Workflow]] is the operational documentation index;
   specialist documents own their respective contracts.
2. Every change follows trace → focused regression → isolated evidence →
   reviewable commit. Current verified runtime outranks legacy source, core,
   settings, or fallback paths.
3. `scripts/release-gate.ps1` is the single authority for release readiness;
   immutable manifest/hash verification and isolated packaged smoke are
   required release evidence.
4. Production integrity capture/verify, backup-first scoped recovery, and
   migration fencing are mandatory for storage-risk work.
5. Provider diagnostics are local/redacted by default and retry only current
   durable identities.

## Consequences

This adds documentation and evidence discipline, not a new business runtime.
It does not authorize automatic migration, credential copying, rollback of
current core-bin, production reset, or a release build by itself. Serious
future architecture or data decisions require a new ADR and targeted tests.

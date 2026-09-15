# Cover Pipeline

Canonical path: Topic → approved headline/subheadline → semantic scene planner → reference resolver → Universal V2 prompt builder → final provider prompt → FastGen → file validation → registry.

No step after `build_final_provider_prompt` may append style, safety, typography, text or retry prompt fragments. FastGen receives the exact final provider prompt. Covers remain preserve-first while the Light work adds only regression and result-validation protections.

## Preservation gate — 2026-09-11

Focused cover regressions passed for the V2 final prompt source, payload equality, single style/headline/subheadline blocks, no legacy tail, reference separation, valid gallery file projection, pause/resume and worker-pool isolation. A normal batch keeps a valid existing cover instead of regenerating it. No FastGen call or cover-library mutation was performed in this phase.

## Production-recovery coverage — 2026-09-14

- The active Covers projection is identity-based: current session title → canonical ProductionItem ID → one active cover row. A stored row from an unrelated former batch stays durable in the library but is not silently presented as a current topic.
- A historical `legacy-cover:*` registry row is never promoted by a matching title. A new active ProductionItem receives a fresh canonical cover projection; history remains in the registry and cannot resurrect text, statuses or provider jobs.
- A new active topic with no cover text is now explicitly `Ожидает генерации` for both headline and subheadline; it is not shown as silently ready or silently skipped.
- The semantic planner resolves a concrete fallback scene before Universal V2: it supplies semantic fields only. It never introduces a second style, typography or safety path. Existing topic-specific fields still win.

## Legacy production-write isolation — 2026-09-14

Every provider-facing cover action gates work at execution time: `ProductionItem ID` must still be current, non-tombstoned and agree with the selected index. Parallel FastGen children carry the same ID and re-check after their own settings reload. A stale queued job is skipped before it can write progress, text, status or timestamps. See [[18 - Decisions/ADR-002 Legacy Production Write Isolation]].

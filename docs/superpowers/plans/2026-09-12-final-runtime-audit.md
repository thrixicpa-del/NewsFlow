# Final Runtime Audit Implementation Plan

> **For agentic workers:** execute task-by-task with targeted tests; do not package an EXE.

**Goal:** prove every current UI command reaches a registered current Python handler, block automatic legacy paths, and gate packaging on that verified runtime graph.

**Architecture:** extend the existing typed command contract with an audit-only source graph. It follows literal renderer commands through preload/Electron dispatch to `bridge.main()`, then asserts canonical handler/service markers and explicit-only legacy migrations. Runtime behavior is exercised only against the isolated test storage runner.

**Tech stack:** React/TypeScript/Electron IPC, Python bridge/services/workers, `unittest`, Vitest, Node source-verification scripts.

**Spec:** user request “FINAL AUDIT BEFORE EXE”.

## Global constraints

- Do not package or launch an EXE; do not invoke providers, OAuth, production queues, rendering or publication.
- Test only under `tests/run_isolated.py`; no production persistent path may be read/written by tests.
- Keep current runtime authoritative; legacy may be migration-only and never automatic.
- Fix only evidence-backed runtime gaps; add a focused regression before each fix.

### Task 1: Complete renderer-to-bridge command coverage

**Files:** `tests/test_runtime_action_map.py`, `scriptor/command_contract.py`, `studio-ui-remotion-verify/src/contracts/newsflowCommands.ts` only if evidence reveals a missing contract.

- [x] Extract literal renderer commands and direct preload actions; verify each maps to a current bridge dispatch branch and documented active service/worker marker.
- [x] Add failing regression for each unmapped/dead/legacy route found; make the smallest current-path repair.
- [x] Run the source graph and affected command-contract tests through the isolated runner.

### Task 2: Validate critical action state/result paths

**Files:** focused existing test modules under `tests/` and `scriptor/test_*.py`; runtime map docs.

- [x] Exercise project/topic/script/cover/voice/montage/export/publication/settings/import/delete/recovery command contracts using mocked providers and isolated storage.
- [x] Assert handler errors propagate as structured errors/status instead of false success; assert terminal statuses require real validated artifacts where applicable.
- [x] Repair only confirmed broken paths and run their focused regression suites.

### Task 3: Current-over-legacy and build graph protection

**Files:** `scriptor/config.py`, `scriptor/session.py`, packaging checks, targeted tests only if a remaining automatic legacy read is evidenced.

- [x] Scan active imports/calls for legacy/fallback paths and classify active, deprecated and migration-only references.
- [x] Assert the pre-package guard checks current command/runtime/schema/dependency markers and that ordinary startup cannot invoke legacy state.
- [x] Run `pnpm verify:build-runtime`, UI command tests and isolated Python gates.

### Task 4: Audit documentation and final source gate

**Files:** Obsidian runtime maps, Button matrix, service/legacy map, regression gate notes.

- [x] Add Button → Runtime map, active-service map, legacy/deprecated/migration-only list with source evidence.
- [x] Run targeted gates, then isolated aggregate Python tests, UI tests, typecheck, build-runtime verification and source build.
- [x] Confirm production control-file hashes equal the recovery backup before declaring audit PASS.

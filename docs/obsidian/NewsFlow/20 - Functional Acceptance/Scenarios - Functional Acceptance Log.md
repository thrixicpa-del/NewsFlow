# Scenarios — Functional Acceptance Log

## MVP acceptance scope

This log records functional acceptance evidence for the Scenarios workspace: selection, generation, refresh visibility, and safe handoff to later production stages. Production content, credentials, paid provider actions, and destructive production storage operations are out of scope unless explicitly authorized.

## SCENARIO-001 — duplicate scenario generation from rapid repeated clicks

Status: **FIX VERIFIED LOCALLY; PENDING CI**

### Confirmed RED

With an unresolved generation command, two rapid clicks on `Написать выбранные` submitted `generate-scenarios` twice. Starting selected generation and immediately invoking `Написать все сценарии` also submitted a second command. The regression used one act boundary to reproduce the stale-render window: both failures expected one command and observed two.

### Implemented minimal fix

`Scenarios` now uses one shared synchronous `scenarioGenerationLock` for both selected and all-scenarios generation. `write(indices?)` claims the lock before setting pending state and releases it only in `finally`. Both generation buttons now explicitly use `disabled`: selected generation is disabled for `generating || !selected.length`; all generation is disabled for `generating || !unfinishedScenarioCount`.

The `generate-scenarios` command contract is unchanged: selected generation sends `{ indices: [0], provider: "agent" }`, while all-scenarios generation retains its existing provider-only payload. Refresh polling, provider selection, scenario selection, backend calls, and transfer behavior were not changed.

### GREEN — 18 September 2026

- Targeted Scenarios UI regression: PASS — 1 file / 9 tests.
- Full frontend suite: PASS — 34 files / 164 tests.
- `pnpm typecheck`: PASS.
- Production integrity/write guard: `PRODUCTION_WRITE_GUARD=PASS`.
- Secret scan and `git diff --check`: PASS.
- No real, network, or paid provider calls were made.

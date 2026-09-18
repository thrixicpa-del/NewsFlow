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

## SCENARIO-003 — operator prompt contract in ChatGPT direct mode

Status: **CONTRACT VERIFIED LOCALLY; PENDING CI**

### Verified path

`Prompt Studio -> save-template -> settings.template / build_requests -> Scenarios ChatGPT direct -> provider prompt -> completed script`.

Prompt Studio saves a distinctive operator template with the existing `save-template` contract and returns to a clean state after success. A failed save retains the full operator text, remains dirty, and visibly reports the failure; navigation protection remains covered by existing tests.

The Scenarios selector sends `provider: "openai"` for `ChatGPT — прямой режим`. Deterministic backend capture verifies that the direct provider prompt preserves the operator marker and instruction, substitutes `{title}` with `Проверочная тема`, does not include the agent-only `Ты редактор новостных сценариев NewsFlow` prefix, and persists the fake response as a completed scenario through the normal session path.

Bounded NewsFlow additions, including ProductionItem context and the narration-only output contract, may accompany the user prompt but do not replace it. No production fix was required.

### GREEN — 18 September 2026

- Backend Scenarios suite: PASS — 13 tests.
- Targeted Prompt Studio + Scenarios UI: PASS — 2 files / 24 tests.
- Full frontend suite: PASS — 34 files / 170 tests.
- `pnpm typecheck`: PASS.
- Production integrity/write guard: `PRODUCTION_WRITE_GUARD=PASS`.
- Secret scan and `git diff --check`: PASS.
- No real, network, or paid provider calls were made.

## SCENARIO-002 — manual ready-script import preserves operator input on failure

Status: **FIX VERIFIED LOCALLY; PENDING CI**

### Confirmed RED

The manual ready-script form cleared both fields immediately after dispatching `import-manual-scenario`, including when the command resolved without a result. Two rapid clicks while the command was unresolved also submitted the same import twice.

### Implemented minimal fix

`Scenarios` now uses a synchronous `manualImportLock` and `importingManualScenario` pending state. The form validates the same non-empty title/text condition, retains the existing command payload `{ title, text }`, clears fields only after a truthy result, and releases the lock in `finally`. The submit button is disabled while pending and displays `Сохранение…`.

### GREEN — 18 September 2026

- Targeted Scenarios UI regression: PASS — 1 file / 12 tests.
- Full frontend suite: PASS — 34 files / 167 tests.
- `pnpm typecheck`: PASS.
- Production integrity/write guard: `PRODUCTION_WRITE_GUARD=PASS`.
- Secret scan and `git diff --check`: PASS.
- No real, network, or paid provider calls were made.

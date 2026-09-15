# Disposable RC Profile Recovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce a new packaged NewsFlow RC with a clean disposable profile containing current-provider credentials and valid external-path bindings, but no legacy business state.

**Architecture:** Treat prior known-good `settings.json` files as read-only candidates. Build a field-level allowlist from the current `Settings` schema, seed an empty test profile with only approved scalar/provider/path fields through the current core command, and use the same current r7 core-bin in the package. The profile has no copied topics, scenarios, covers, jobs, queues, session, UI or runtime state.

**Tech Stack:** Current NewsFlowCore r7, Electron/Vite packaging, DPAPI-protected settings, JSON/SQLite footage metadata, PowerShell verification.

**Spec:** User request of 2026-09-15: restore only working configuration/path bindings from known-good versions, package a disposable test RC, and stop for manual testing.

## Global Constraints

- Never write to `C:\Users\borov\AppData\Local\NewsFlow` production storage.
- Never copy `idea_topics`, ProductionItems, scripts, covers, voice/montage/publication jobs, queues, sessions, UI state, core or core-bin from a legacy profile.
- Keep current r7 Universal V2 prompt, release guards, Cover/FastGen/face pipeline and Fast News Montage unchanged.
- Do not expose secrets in logs or documentation.
- Only a disposable test profile may be modified.

---

### Task 1: Establish the allowlisted source configuration

**Files:**
- Read: `D:\NewsFlow Studio\Backups\**\settings*.json`
- Read: `C:\Users\borov\AppData\Local\NewsFlow\settings.json`
- Read: `scriptor\config.py`
- Create: `D:\NewsFlow Studio\BuildValidation\rc-profile-2.1.152-r8\transfer-manifest.json`

**Interfaces:**
- Consumes encrypted known-good settings and the current `Settings` schema.
- Produces a redacted manifest of exact approved field names, source timestamps, source path roots and count-only credential metadata.

- [ ] **Step 1: Compare candidate settings without decrypting or printing secrets.**

Run a parser that reports only field presence, list counts, enabled flags, canonical filesystem paths and schema markers.

- [ ] **Step 2: Select the newest compatible value for each allowlisted field.**

Use current-schema provider fields, `footage_*` roots/index references, output folders, face-library root/prepared root and reference-mode fields. Preserve each field independently; do not select an entire settings file.

- [ ] **Step 3: Exclude business-state fields.**

Reject any values for topic collections, production records, scenario text, cover queue/library items, montage/voice/publication queues, task status, browser/UI session state and legacy runtime paths.

- [ ] **Step 4: Verify the source external paths.**

Require each configured output, footage and face root to exist; sample the current footage index and face PNG catalog without modifying their files.

### Task 2: Seed and verify a clean disposable profile

**Files:**
- Create: `D:\NewsFlow Studio\BuildValidation\rc-profile-2.1.152-r8\NewsFlow\settings.json`
- Create: `D:\NewsFlow Studio\BuildValidation\rc-profile-2.1.152-r8\transfer-manifest.json`
- Read: `scriptor\bridge.py`

**Interfaces:**
- Consumes the Task 1 allowlist.
- Produces a current-core-loaded disposable profile where external configuration is readable and business-state counts are zero.

- [ ] **Step 1: Create an empty isolated NewsFlow root.**

Do not copy a previous profile directory. Start from the current core’s empty-profile initialization.

- [ ] **Step 2: Apply only allowed fields through current runtime persistence.**

Use current `save-cover-settings`, current settings persistence and current schema handling. Do not write raw production JSON or invoke a legacy core.

- [ ] **Step 3: Snapshot the profile through current r7 core.**

Verify provider configuration exists without printing secrets; footage root/index and face catalog are loaded; zero topics, ProductionItems, scenarios, cover rows, jobs and queues are present.

- [ ] **Step 4: Reopen the same disposable profile.**

Verify the allowlisted settings persist and no background reconcile creates old business data.

### Task 3: Package and smoke-verify a new test RC

**Files:**
- Create: `D:\NewsFlow Studio\Builds\NewsFlow-2.1.152-light-r8-test-rc\`
- Read: `studio-ui-remotion-verify\package.json`
- Read: `studio-ui-remotion-verify\scripts\verify-build-runtime.mjs`
- Read: `studio-ui-remotion-verify\scripts\verify-core-runtime.mjs`

**Interfaces:**
- Consumes current source and r7 core-bin only.
- Produces a new self-contained packaged EXE and a test-profile launcher manifest.

- [ ] **Step 1: Run current release guards before packaging.**

Run `pnpm verify:build-runtime`, `pnpm verify:core-runtime` and TypeScript typecheck from `studio-ui-remotion-verify`.

- [ ] **Step 2: Package to a new r8 test-RC output folder.**

Point packaging only at `.core-bin-2.1.152-prompt-assembly-r7`; do not reuse an earlier unpacked folder as output.

- [ ] **Step 3: Audit package content.**

Verify one packaged `NewsFlowCore.exe` hashes identically to r7; ensure its internal FFmpeg and the current Remotion binaries are present.

- [ ] **Step 4: Launch only against the disposable profile and perform a non-destructive snapshot smoke.**

Verify startup uses current schema/runtime and preserves empty business state plus the restored configuration.

### Task 3a: Gate packaging with a real Current-UI production deletion check

**Files:**
- Read: `studio-ui-remotion-verify\src\ui\App.tsx`
- Read: `studio-ui-remotion-verify\src\contracts\newsflowCommands.ts`
- Read: `scriptor\bridge.py`
- Create: `D:\NewsFlow Studio\BuildValidation\delete-production-current-ui-r8\`

**Interfaces:**
- Consumes a disposable, current-core profile containing two explicitly created test ProductionItems.
- Produces proof that one selected item is deleted only through the current UI's confirmation path and cannot resurrect after restart.

- [ ] **Step 1: Create the disposable deletion profile and record its initial filesystem hash set.**

Use a distinct test root. Create two test items using the current packaged UI so the delete test never touches production or the manual-test RC profile.

- [ ] **Step 2: Trace the current UI action contract before invocation.**

Confirm the visible deletion control resolves from the active React component through typed `remove-production-items`/current command handling to the current bridge persistence path. Confirm no legacy handler appears in this chain.

- [ ] **Step 3: Select one item, invoke the visible control and accept its confirmation through UI Automation.**

Capture the CURRENT UI control identity before each action. Do not use a direct bridge/service/storage call for creation, selection, confirmation or deletion.

- [ ] **Step 4: Verify deletion semantics through a read-only current-core snapshot.**

Require the chosen current ProductionItem absent from active state, the other test item present, zero orphan jobs for the deleted ID and a tombstone/explicit deletion guard. Repeat the same UI action if still visible to prove idempotent no-op/error handling without affecting the survivor.

- [ ] **Step 5: Restart the packaged app against the same disposable profile.**

Require deleted item remains absent, historical rows remain inactive and no credentials, footage-index, face-library files or production files changed.

- [ ] **Step 6: Gate packaging.**

Proceed to Task 3 only if all checks pass and record `DELETE PRODUCTION BUTTON — PASS`; otherwise fix the root cause, add a focused regression test, rebuild core/package and repeat this task.

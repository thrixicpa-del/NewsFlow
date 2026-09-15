# Stable News Light Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stabilize the existing NewsFlow daily news-production pipeline without resetting user data, reactivating legacy code, or rewriting working modules.

**Architecture:** Keep React + TypeScript + Vite + Electron and the Python core. First harden the canonical `%LOCALAPPDATA%\\NewsFlow` state boundary, then introduce a checked command/runtime-path boundary. Each subsequent module phase changes one bounded production path, validates its actual artifact/status contract, and records its root-cause protections in the project-local Obsidian-compatible vault.

**Tech Stack:** Electron, React, TypeScript, Vite, Python 3.12, unittest, Vitest, FFmpeg/ffprobe, existing provider adapters, existing Settings persistence.

**Spec:** `C:\\Users\\borov\\.codex\\attachments\\fb92df14-67a1-4963-9b10-e975868be2c6\\pasted-text.txt`

## Global Constraints

- The canonical persistent root remains `%LOCALAPPDATA%\\NewsFlow`; never replace it with a blank root.
- Pre-change backup verified at `D:\\NewsFlow Studio\\Backups\\pre-stable-news-light-20260911-161027`.
- Every migration follows backup → source validation → in-memory/copy migration → result validation → atomic commit.
- No release build or EXE creation in this task unless the user later explicitly requests it.
- No live provider, OAuth, publication, queue, rendering or destructive production action is a substitute for tests; use isolated temporary state for automated verification.
- Do not change STABLE SEO, Tags or Publication business logic except to repair an evidenced dependency break; never activate a legacy fallback silently.
- Preserve every existing Settings field, provider choice, OAuth/channel profile, path, topic/script/ProductionItem relation, MP3/MP4/cover artifact, queue/status, history and preset.
- New UI work uses the existing React/TypeScript/Vite/Electron stack and local Radix/Lucide/TanStack-compatible primitives; do not rewrite `App.tsx` wholesale.

---

## Runtime baseline and targets

| Target | Current canonical path | Classification | Targeted verification |
|---|---|---|---|
| Settings | `config.load_settings` / `save_settings` | FIX | `scriptor/test_config.py`, isolated corruption/restart cases |
| Topics | `Ideas` → `generate-ideas` | IMPROVE | `tests/test_ideas.py` plus 100-character/dedup/tombstone cases |
| Scripts | `Scenarios` → `generate-scenarios` | IMPROVE | `tests/test_scenarios.py` plus measured range/repair cases |
| Voice/WProject | `VoiceQueue` → `generate_voice[_range]` | FIX | `tests/test_voicer.py`, `tests/test_tts_ranges.py` |
| Covers | `generate-covers` → `thumbnail_prompt_v2` | STABLE / FIX | `tests/test_covers.py`, `scriptor/test_cover_library.py` |
| Montage | `run-montage-queue` | FIX | montage/timeline tests plus synthetic benchmark |
| Footage index | `index-footage` → SQLite index | IMPROVE | `tests/test_footage.py` |
| SEO/Tags | `generate-seo` / `generate-tags` | STABLE | `tests/test_seo.py` and metadata transfer assertions |
| Publication | V2 command family → `publication_v2` | STABLE / FIX | V2/publisher/OAuth persistence tests |

### Task 1: Persistence safety and deletion integrity

**Files:**
- Modify: `scriptor/config.py`, `scriptor/bridge.py`
- Test: `scriptor/test_config.py`, `tests/test_ideas.py`, `tests/test_scenarios.py`, `tests/test_cover_queue_tombstones.py`
- Update: `docs/obsidian/NewsFlow/05 - Persistence/Settings Persistence.md`, `docs/obsidian/NewsFlow/17 - Bugs and Root Causes/Open Root Causes.md`

**Interfaces:**
- `load_settings()` distinguishes absent state from invalid/corrupt state and never returns a writable empty replacement for a corrupt on-disk file.
- `snapshot()` becomes a projection-only read path; explicitly named reconcile/migration commands own recoverable writes.
- Topic/script deletion uses stable IDs and durable tombstones/authoritative-state filtering, not title text or row position.

- [x] Write isolated-state tests that corrupt `settings.json`, assert the original digest remains unchanged after attempted load/save, and assert a last-known-good recovery is marked rather than silently committed.
- [x] Write restart/snapshot/migration tests proving a deleted topic or script cannot return from an old queue, snapshot or duplicate store.
- [x] Implement non-writing invalid-settings handling with a user-visible structured error/recovery status; validate every incoming parsed object before constructing Settings.
- [x] Move all write-capable recovery calls out of snapshot into explicit bounded reconciliation invoked by the owning command, retaining existing recovery behavior only where tests show it safe.
- [x] Make stable ProductionItem IDs authoritative for topic/script descendants and retain bounded tombstones during merge/migration.
- [x] Run the four focused suites with a temporary `LOCALAPPDATA`; document the root causes, changed paths and passing tests.

### Task 2: Typed command and active-runtime contract

**Files:**
- Create: `studio-ui-remotion-verify/src/contracts/newsflowCommands.ts`, `scriptor/command_contract.py`, contract test modules
- Modify: `studio-ui-remotion-verify/src/desktop.d.ts`, `studio-ui-remotion-verify/electron/preload.mts`, `studio-ui-remotion-verify/electron/main.ts`, `scriptor/bridge.py`, changed feature entry points
- Update: `docs/obsidian/NewsFlow/02 - Active Runtime Paths/ACTIVE_RUNTIME_PATHS.md`

**Interfaces:**
- `NewsFlowCommand` maps each critical command to a request and result/status shape.
- Python `COMMAND_CONTRACT` maps the same names to canonical handlers and forbidden legacy modules.
- Critical UI code uses a typed `command<K extends NewsFlowCommand>(name: K, payload: CommandRequest<K>)` boundary.

- [x] Create failing tests that enumerate critical UI commands, preload exposure, IPC routing, Python handler registry and request/result validators.
- [x] Implement one shared contract registry and adapt the generic transport without changing provider or queue semantics.
- [x] Register Topics, Scripts, Voice, Covers, Montage, SEO, Tags, Publication and Settings; each registration names its canonical service and forbidden legacy alternatives.
- [x] Add tests that fail on an unregistered renderer command, missing handler, payload mismatch, response mismatch or forbidden legacy import.
- [x] Run Python contract tests, focused UI tests and `pnpm typecheck`; record only source-proven active paths in [[02 - Active Runtime Paths/ACTIVE_RUNTIME_PATHS]].

### Task 3: FAST NEWS MONTAGE canonical path and benchmark

**Files:**
- Modify: `scriptor/bridge.py`, `scriptor/timeline.py`, montage renderer/preset code found by contract audit
- Create: synthetic benchmark fixture and benchmark runner under `tests/`
- Test: `tests/test_montage_queue.py`, `scriptor/test_montage_render.py`, `tests/test_timeline.py`, benchmark tests
- Update: `docs/obsidian/NewsFlow/13 - Montage/FAST NEWS MONTAGE.md`

**Interfaces:**
- One `FAST NEWS MONTAGE` preset resolves planner, renderer, FFmpeg/ffprobe binaries, codec policy and worker limits.
- A terminal `READY` montage status requires an existing, ffprobe-valid MP4 with expected audio/video duration.
- Failed canonical render returns diagnostic state; it cannot invoke a legacy/slow renderer automatically.

- [x] Add a fixture-driven failing test for canonical preset resolution, no legacy fallback, artifact validation and failed-worker status.
- [x] Instrument only synthetic fixture rendering with runtime path, binary path, preset, input duration/footage count, output duration and elapsed time.
- [x] Implement canonical routing and explicit failure behavior while retaining existing user project files and valid prior MP4s.
- [x] Establish a checked baseline on a safe fixture and fail tests when a future fixture run exceeds the documented tolerance.
- [x] Run montage suites and update the montage root-cause record.

### Task 4: Voice/WProject and manual MP3 mapping

**Files:**
- Modify: voice provider/queue handlers in `scriptor/bridge.py` and existing voice modules
- Modify: affected `VoiceQueue`/audio UI portions in `src/ui/App.tsx` or new `src/ui/features/voice/*`
- Test: `tests/test_voicer.py`, `tests/test_tts_ranges.py`, new manual-audio matching tests
- Update: `docs/obsidian/NewsFlow/10 - Voice/Voice Engine.md`

**Interfaces:**
- A voice job owns a `productionItemId`, provider attempt history, durable status and validated MP3 artifact metadata.
- Manual import returns `MATCHED`, `UNCERTAIN` or `NOT_FOUND`; uncertain matches require explicit confirmation.

- [x] Add mocked WProject tests for Russian long text, output duration, retry, multi-task isolation, restart and correct ProductionItem linkage.
- [x] Add list and folder import tests covering exact, normalized and fuzzy matching; assert fuzzy/ambiguous files are never attached automatically.
- [x] Repair the actual provider/queue root cause exposed by tests and persist status only after MP3 existence/duration validation.
- [x] Verify compact real-status UI feedback for enqueue/running/ready/error uses the backend job state.
- [x] Run voice suites and record the completed root cause/regression tests.

### Task 5: News Topics and Script length control

**Files:**
- Modify: topic/scenario domain code in `scriptor/bridge.py` and supporting modules
- Modify: relevant Ideas/Scenarios UI or new `src/ui/features/topics/*`, `src/ui/features/scripts/*`
- Test: `tests/test_ideas.py`, `tests/test_scenarios.py`
- Update: `docs/obsidian/NewsFlow/08 - Topics/Topic Engine.md`, `docs/obsidian/NewsFlow/09 - Scripts/Script Engine.md`

**Interfaces:**
- Topic validation is Python-owned and exposes fact structure, length (`<=100`) and deduplication reason.
- Script range presets expose `target_chars`, `allowed_min`, `allowed_max`, `actual_chars`, status and bounded repair history.

- [x] Add failing unit cases for the news action/consequence structure, generic-topic rejection, current/existing/recent dedup and deleted-item exclusion.
- [x] Implement Python-side topic normalization, maximum-length enforcement and stable-ID-aware dedup without trusting LLM output.
- [x] Add failing range-preset and short/long repair tests; count characters in Python after every response and cap repair attempts.
- [x] Add narrow UI controls for range presets and per-script override, showing target/actual/READY/SHORT/LONG/FAILED from backend data.
- [x] Run the topic/script suites and update their vault notes.

### Task 6: Cover, footage, SEO/Tags and publication preservation gates

**Files:**
- Modify only files required by an evidenced failed regression; expected work is tests/contract registration and docs
- Test: cover, footage, SEO, tags-transfer and publication/OAuth suites
- Update: `docs/obsidian/NewsFlow/11 - Covers/Cover Pipeline.md`, `12 - Footage Index/Footage Index.md`, `14 - SEO and Tags/SEO and Tags.md`, `15 - YouTube Publication/Publication.md`

**Interfaces:**
- Cover provider payload equals the sole V2 final prompt and READY requires a real image.
- Footage index skips unchanged files using persisted file identity/probe metadata.
- Publication V2 preserves `youtubeVideoId` and retries from the failed downstream stage.

- [x] Run cover regressions first and repair only a proven V2 integrity failure; preserve FastGen, references, faces and gallery behavior.
- [x] Add incremental footage tests for new/changed/unchanged/deleted files and cached ffprobe metadata, then implement only missing branch behavior.
- [x] Run SEO/Tags generation/save/manual-edit/publication-transfer tests without refactoring their stable core.
- [x] Run Publication V2, publisher and OAuth-persistence tests with all network transports mocked; add an idempotent retry regression if absent.
- [x] Record each module’s verified status; report live external behavior only as NOT VERIFIED unless a controlled authorized test is later run.

### Task 7: Worker isolation, Task Center and Light UI foundation

**Files:**
- Create: `studio-ui-remotion-verify/src/ui/components/ui/*`, `src/ui/features/task-center/*`
- Modify: affected feature pages, `App.tsx` only for mounts/state handoff, contracts and worker status projection
- Test: focused UI component tests and isolated worker-status tests
- Update: `docs/obsidian/NewsFlow/04 - UI/UI Light.md`, `06 - Jobs and Workers/Task Center.md`

**Interfaces:**
- A common job-state DTO supports `QUEUED`, `RUNNING`, `PAUSED`, `RETRYING`, `READY`, `FAILED`, `CANCELLED`, attempt, provider, artifact validation and error.
- Task Center reads real projected job state; it does not infer success from animation or an IPC acknowledgement.

- [x] Add failing UI/status tests for accepted → queued → running → validated ready, failed, retry and paused states.
- [x] Introduce one local UI-kit implementation (Button, Badge, StatusBadge, Progress, DataTable, Sheet, Dialog, AlertDialog, Tooltip, Empty/Error/Loading states); do not add parallel Button variants.
- [x] Add feature-local modules only for pages being changed and keep business logic out of new App.tsx code.
- [x] Expose per-pool concurrency and ensure synthetic script/cover/voice/montage/publication workers do not block unrelated pools; test one failure does not stop neighboring work.
- [x] Mount compact Task Center and refresh the listed critical screens with consistent action/status semantics; run focused UI tests and typecheck.

### Task 8: Final Light regression gate and documentation baseline

**Files:**
- Create or modify: isolated gate runner and `docs/obsidian/NewsFlow/19 - Release Baselines/*`
- Update: all affected vault notes and `docs/audit/NEWSFLOW_DEEP_SYSTEM_MAP.md` only where active paths changed
- Test: focused suites, then compact aggregate regression gate

- [x] Run all phase-local tests in an isolated state root; repair every current-Light root cause before advancing.
- [x] Run the compact gate for persistence, tombstones, command contract, topics/scripts, voice, covers, montage/benchmark, SEO/Tags, publication idempotency, worker isolation and UI status.
- [x] Run `pnpm typecheck` and `pnpm build` only after functional gates pass; do not call this a release or create an EXE.
- [x] Update the vault with actual canonical paths, benchmark baseline, unresolved external-verification gaps and each serious bug’s regression test.
- [x] Require a fresh backup, source/result migration validation, test-build launch and visible old-data verification before any future user-authorized EXE distribution.

## Plan self-review

- Scope coverage: persistence, commands, production-path uniqueness, montage, voice/manual audio, topics, scripts, covers, footage, parallel jobs/task UX, SEO/Tags, publication, tests and release safety each have a bounded task.
- Non-goals: no application rewrite, no dependency upgrade, no destructive cleanup, no legacy deletion, no unapproved live external action, no EXE.
- Dependency consistency: all changed UI paths traverse the shared contract to Electron IPC, the canonical Python handler, service/worker, persistence, validated result and status projection.

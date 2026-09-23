# Production Reset — Functional Acceptance Log

Status: **FIX VERIFIED LOCALLY; PENDING INDEPENDENT REVIEW/CI**

## RESET-001 contract

The explicitly confirmed `clear-production-queue` action removes only the active production/release and its owned working artifacts. It preserves reusable operator configuration: channels, OAuth and keys, provider and route presets, source-footage configuration/index, face/reference configuration, model cache, and the Results destination root.

## Audit and deterministic RED evidence

On `main@2e402e21fcfacb16f265c4d992194dfa257e2246`, isolated real-storage regressions reproduced:

- empty `montage_task_statuses` was merged with persisted rows by `save_settings()`, so old Montage tasks reappeared after reset/reload;
- `youtube_publication_plan_versions`, `voice_import_summary`, and `results_last_export_folder` survived the reset;
- a detached pre-reset `Settings` object repopulated the old ProductionItem/release state when saved after the reset;
- an orphan `voice-maps/*.voice-map.json` survived;
- configured production roots must remain directories while their children are cleared.

The primary/backup SESSION-001 protections, exact UI confirmation, Results destination preservation, source footage, model cache, OAuth, and V2 rule presets were already safe or are asserted by the new isolated matrix.

## Repair invariant

`production_reset_generation` is a durable, monotonic Settings fence. A confirmed reset increments it before the logical release-empty save. A later save from an older Settings generation preserves the newer on-disk release fields while retaining the worker's unrelated global settings. New work loaded after the reset shares the current generation, and a new ProductionItem ID may reuse the old human title.

The reset now explicitly clears V2 plan versions, voice import audit, and Results last-export pointer; it removes every `voice-maps/*.voice-map.json` production artifact without touching models; and retains configured output roots while clearing their children. The cover sidecar now tombstones every old/orphan cover row, and a worker that finishes after reset deletes its own stale cover, voice, or Montage artifact instead of promoting it. This applies before and after Montage project/XML writes, external download/cutter writes, and render promotion; external files use an isolated per-source operation folder and are checked before cache/index publication. FastGen's rolling rate-use ledger is deliberately preserved: it is an account-limit safeguard, not release state.

## Local evidence

- `tests/test_production_reset.py` uses only `tests/run_isolated.py` disposable storage and real settings/session persistence (no mocked `save_settings`). It covers reset/reload/snapshot, backup-safe session state, stale-worker-after-reset including delayed CoverLibrary/file commit, held Montage project write, and held external download/cutter write, old/new ProductionItem IDs, VoiceMap orphan cleanup, production file cleanup, and preserved source/model/OAuth/rule-preset/rate-ledger sentinels.
- No real production root, provider, OAuth, YouTube, or media library was mutated.

## Verification

- Targeted backend reset/session/montage/publication/results regression: 182 passed.
- Runtime/security/frozen-core/migration/failure contract suites: 15 passed.
- Targeted React confirmation/results tests: 22 passed.
- Typecheck, scoped Ruff, Python compile, secret scan, production-integrity guard, dependency audit, frontend security gate, and web/Electron/Remotion source build: passed. No Playwright/Electron DEV E2E command exists in this checkout, so the source boundary is covered by the runtime-action and frozen-core contracts instead; this remains an explicit SYSTEM-gap rather than a claimed E2E pass.
- `pnpm test:ui` is blocked by 31 missing Git LFS baseline PNGs in this checkout. The LFS server also returned 404 for `assets/ffmpeg.exe`; this is recorded as an independent repository-artifact blocker, not bypassed.

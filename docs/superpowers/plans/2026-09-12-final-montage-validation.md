# Final Montage Validation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** verify and protect the current Fast News montage path before EXE packaging without running production work.

**Architecture:** inspect the active React → Electron → bridge → timeline/FFmpeg route, then exercise it with disposable MP3/video fixtures through the isolated runner. Add only narrow regression gates where evidence finds a runtime fallback or timing defect.

**Tech Stack:** React/TypeScript, Electron IPC, Python bridge/timeline, FFmpeg, unittest.

**Spec:** user request “FINAL MONTAGE VALIDATION BEFORE EXE”.

## Global Constraints

- Do not package or launch an EXE, use providers, OAuth, production queues, or production storage.
- Preserve current Fast News architecture; no broad rewrite or old-build comparison.
- All tests run with `tests/run_isolated.py` and disposable fixture media.

### Task 1: Trace and guard active montage runtime

**Files:** `tests/test_runtime_action_map.py`, `scriptor/command_contract.py`, `electron/main.ts`, `scriptor/bridge.py`, `scriptor/timeline.py`.

- [x] Trace `run-montage-queue` from React command to Electron worker launch and bridge handler; classify any old path as inactive/migration-only.
- [x] Add a failing source regression if an active old renderer, preset or core fallback is found; make only the corresponding current-path repair.
- [x] Run isolated command/runtime map tests.

### Task 2: Validate Fast News performance and timing

**Files:** `tests/test_fast_reuse_render.py`, `tests/test_montage_queue.py`, `scriptor/test_montage_render.py`, `scriptor/timeline.py` only if evidence requires it.

- [x] Measure fixture footage planning and final FFmpeg rendering; record elapsed timings without asserting hardware-dependent whole-render limits.
- [x] Verify duration alignment, last-clip-only trimming, no visual gap, audio continuity and bounded looping of short moving footage.
- [x] Add a failing regression for any reproduced timing/render defect and rerun focused tests.

### Task 3: Build preservation and final verification

**Files:** `scripts/verify-build-runtime.mjs`, Montage Obsidian notes, regression documentation.

- [x] Verify package gate binds the current montage runtime/preset and cannot select a prior core or old renderer.
- [x] Run focused Montage suites, isolated aggregate tests, UI/type/runtime build checks and confirm production control hashes remain equal to backup.
- [ ] Rebuild the internal `core-bin` only after explicit authorization, then rerun `verify:core-runtime`; this deliberate stale-core block prevents a desktop EXE from shipping old Montage code.
- [ ] Document active map/evidence and report `READY FOR EXE BUILD` only on fresh PASS evidence.

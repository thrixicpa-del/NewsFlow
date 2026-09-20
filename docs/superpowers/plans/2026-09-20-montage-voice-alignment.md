# MONTAGE-004 VoiceMap Alignment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create a durable VoiceMap from each canonical scenario/MP3 pair and make Montage consume its honest aligned or approximate timing.

**Architecture:** A focused `scriptor.voice_map` service owns schema, engines, reconciliation, segmentation, validation, caching and atomic lifecycle. Existing Voice attachment points ensure the map; `prepare_montage` consumes it while retaining all MONTAGE-003 selection logic. Snapshot/UI and the existing generic IPC command surface only operator-facing timing state and an explicit rebuild action.

**Tech Stack:** Python 3, FFmpeg/FFprobe, unittest isolation harness, React/TypeScript, Electron IPC, Vitest, existing Montage timeline/CLIP index.

**Spec:** `docs/superpowers/specs/2026-09-20-montage-voice-alignment-design.md`

## Global Constraints

- Baseline is `f4d8ac597d37f8bd21c5b255b598578c0e1d1817`; work only on `feature/montage-voice-alignment`.
- ProductionItem ID is identity; canonical scenario is text authority; MP3 is timing authority.
- Never download or silently bundle an alignment model.
- `approximate` is an honest VoiceMap mode, never an `aligned` success.
- Preserve MONTAGE-003, SESSION-001, production-write safety, queue ownership and bounded search.
- No provider, OAuth, publication, production media/settings/session writes, merge, or issue close.

---

### Task 1: VoiceMap domain contract and durability

**Files:**
- Create: `scriptor/voice_map.py`
- Create: `tests/test_voice_map.py`

**Interfaces:**
- Produces: `VoiceMapContext`, `TimedObservation`, `AlignmentResult`, `VoiceMapStatus`, `ensure_voice_map()`, `inspect_voice_map()`, `remove_voice_map()`, `voice_map_path()`.
- Consumes: canonical script/identity supplied by callers and existing `probe_media_duration()`.

- [ ] Write deterministic tests for schema fields, aligned segmentation, natural boundaries, positive monotonic durations, full canonical coverage, audio endpoint, optional word evidence and approximate provenance.
- [ ] Run `python tests/run_isolated.py tests/test_voice_map.py -v` and record the expected missing-module/API RED.
- [ ] Implement dataclasses/protocol, SHA-256 helpers, canonical token ranges, boundary-aware segmentation, schema validation and JSON serialisation.
- [ ] Add tests for cache reuse, script/audio/schema staleness, same-title/new-ID isolation, corrupt JSON and interrupted atomic writes.
- [ ] Implement hashed artifact paths, strict read inspection and temporary-file atomic replace.
- [ ] Run the focused suite until all Task 1 cases are GREEN.

### Task 2: Optional FFmpeg/Whisper observations and canonical reconciliation

**Files:**
- Modify: `scriptor/voice_map.py`
- Modify: `tests/test_voice_map.py`

**Interfaces:**
- Produces: `FfmpegWhisperAlignmentEngine.available()`, `align(context)`, canonical reconciliation with explicit confidence/failure reason.

- [ ] Add RED tests for missing model/filter, canonical reconciliation, divergent ASR rejection, segment-only output, word evidence and no hidden model download.
- [ ] Implement capability probing and explicit model discovery from `NEWSFLOW_WHISPER_MODEL` or the project-owned cache.
- [ ] Implement disposable FFmpeg whisper invocation and JSON observation parsing without logging model contents or private data.
- [ ] Reconcile normalised observations to canonical tokens; reject low coverage/non-monotonic observations instead of inventing timestamps.
- [ ] Run focused tests and `python -m py_compile scriptor/voice_map.py`.

### Task 3: Voice lifecycle, SESSION-001 ordering and snapshot state

**Files:**
- Modify: `scriptor/bridge.py`
- Modify: `scriptor/config.py` only if a non-secret model-cache setting is required
- Modify: `tests/test_voice_map.py`
- Modify: `tests/test_session.py`
- Modify: `tests/test_montage_queue.py`

**Interfaces:**
- Consumes: completed `Job.request.production_item_id`, canonical `Job.result`, promoted/imported audio path.
- Produces: automatic ensure after every successful Voice attachment, tombstone-first cleanup, snapshot `voiceMap` state, `rebuild_voice_map(payload)`.

- [ ] Add RED integration tests for generated/imported MP3 handoff, state projection, cache reuse, script/audio safety on failure, reset/delete cleanup and stale-worker publish rejection.
- [ ] Add a single bridge helper that resolves current canonical identity and ensures a map after MP3 validation; call it from all current successful attachment paths.
- [ ] Project the six Russian operator states without exposing ASR internals.
- [ ] Apply SESSION-001 ordering: persist tombstone authority before physical map cleanup and revalidate current authority at publish.
- [ ] Run `python tests/run_isolated.py tests/test_voice_map.py tests/test_session.py tests/test_montage_queue.py -v`.

### Task 4: Montage and persisted `.newsflow` provenance

**Files:**
- Modify: `scriptor/timeline.py`
- Modify: `scriptor/bridge.py`
- Modify: `tests/test_voice_map.py`
- Modify: `tests/test_timeline.py`
- Modify: `tests/test_montage_semantic_diversity.py`

**Interfaces:**
- Produces: `TimelineClip.voice_segment_id`, narration start/end, `TimelineProject.voice_map_provenance`; VoiceMap-to-scene conversion.

- [ ] Add RED tests proving valid aligned segments replace legacy proportional timing, approximate mode stays explicit, corrupt/stale maps rebuild/fallback, and every saved clip/project retains VoiceMap provenance.
- [ ] Extend timeline dataclasses with backward-compatible defaults.
- [ ] Replace only the planning source in `prepare_montage`; leave query ladders, semantic guards, diversity, source-family and source-start code unchanged.
- [ ] Record alignment/semantic/retrieval/overall metrics and keep the exact audio-duration terminal condition.
- [ ] Run VoiceMap, timeline, Montage queue and semantic-diversity tests.

### Task 5: React → IPC → Electron → Python contract

**Files:**
- Modify: `studio-ui-remotion-verify/src/contracts/newsflowCommands.ts`
- Modify: `studio-ui-remotion-verify/electron/allowed-core-commands.ts`
- Modify: `studio-ui-remotion-verify/src/types.ts`
- Modify: `studio-ui-remotion-verify/src/ui/App.tsx`
- Modify: `studio-ui-remotion-verify/src/ui/features/voice/voice-view.test.tsx`
- Modify: `tests/test_runtime_action_map.py`
- Modify: `tests/test_electron_e2e.py`

**Interfaces:**
- Produces: allowed `rebuild-voice-map` command and user-visible VoiceMap state/rebuild control.

- [ ] Add RED UI/contract tests for all six labels, rebuild payload identity and no implicit Montage render.
- [ ] Add the command to both allow-lists and bridge dispatch.
- [ ] Extend snapshot types and Voice UI minimally with state plus rebuild action.
- [ ] Run targeted Vitest, runtime action-map and source Electron E2E.

### Task 6: Isolated media acceptance, documentation and commercial gate

**Files:**
- Create: `tests/run_voice_map_montage_smoke.py`
- Modify: `docs/obsidian/NewsFlow/20 - Functional Acceptance/Montage - Functional Acceptance Log.md`
- Create only ignored evidence below `.artifacts/`.

**Interfaces:**
- Produces: isolated MP3, scenario, VoiceMap, `.newsflow`, MP4, FFprobe JSON, hashes, metrics and manifest.

- [ ] Build synthetic local narration/audio and test-owned footage in `NEWSFLOW_TEST_ROOT`; run the real `ensure_voice_map → prepare_montage → render_montage` path.
- [ ] Assert FFprobe audio/video duration tolerance, no invalid timestamps, complete visual tail and bounded source starts.
- [ ] Run the exact combined Python suite from issue #49, py_compile, Ruff, secret scan, production-integrity guard and `git diff --check main..HEAD`.
- [ ] Run `pnpm test:ui`, `pnpm typecheck`, `pnpm run verify:security`, `pnpm build`, and source Electron E2E with zero SKIP.
- [ ] Review the complete diff, document design/engine/cache/offline/package limitations and acceptance evidence.
- [ ] Commit coherently, push, open a PR against `main`, attach it, and wait for CI plus Windows-native validation.
- [ ] Post one complete `## CODEX RESULT` to issue #49 and stop without merging or closing it.

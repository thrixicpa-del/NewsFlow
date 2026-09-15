# NEWSFLOW RUNTIME EXECUTION TRACES

**Trace classification:** source-derived execution traces, not live recordings. No production command was invoked. Each trace identifies the code route and its verification gap.

## T-01: Renderer refresh / snapshot

```mermaid
sequenceDiagram
  participant UI as App.refresh()
  participant PL as preload.snapshot()
  participant EL as IPC newsflow:snapshot
  participant BR as bridge.snapshot()
  participant ST as Settings/library/index
  UI->>PL: snapshot()
  PL->>EL: invoke
  EL->>BR: callCore("snapshot", {})
  BR->>ST: load + hydrate + reconcile
  Note over BR,ST: May call save_settings during recovery/migration
  ST-->>BR: projected state
  BR-->>UI: JSON snapshot
```

**Source evidence:** `App.tsx` initial `useEffect(refresh)`, preload `snapshot`, `electron/main.ts` IPC, `bridge.snapshot`. **Outcome:** route is statically certain. **NOT VERIFIED:** rendering against a real existing state. **Important:** this trace may write state and was not executed.

## T-02: Cover creation button → FastGen

```mermaid
sequenceDiagram
  participant C as Covers UI
  participant A as App.command
  participant B as bridge.generate_covers
  participant L as cover-generation.lock
  participant P as thumbnail_prompt_v2
  participant F as FastGenPool/API
  participant S as settings + cover library
  C->>A: command("generate-covers", indices/options)
  A->>B: generic IPC JSON
  B->>L: claim process lock
  B->>S: hydrate queue; select missing image rows
  B->>P: construct final provider prompt once
  P-->>B: final prompt + source debug
  B->>F: image request(s), max 10 topic workers
  F-->>B: result/error
  B->>S: persist progress/paths/status
  B->>L: release in finally
```

**Source evidence:** `App.tsx` command labels, dispatcher branch, `generate_covers`, `_run_parallel_cover_workers`, `thumbnail_prompt_v2.build_final_provider_prompt`. **NOT VERIFIED:** provider acceptance, actual image output and rate-limit handling in the current environment. The audit did not use any API key.

## T-03: Final prompt assembly (current V2 path)

```mermaid
flowchart LR
  I[topic/title + optional script] --> SP[semantic/topic planner]
  SP --> PB[build_final_provider_prompt]
  R[reference resolver] --> PB
  T[thumbnail text engine] --> PB
  PB --> FP[final_provider_prompt]
  FP --> FG[FastGen adapter payload]
```

The expected debug attribution is Core style = Universal V2; scene = topic planner; people = reference resolver; text = thumbnail engine; negative = Universal V2. Static tests named `test_prompt_has_single_style_block`, `test_prompt_has_single_headline_block`, `test_prompt_has_single_subheadline_block`, `test_prompt_has_no_legacy_tail`, `test_prompt_has_no_duplicate_sections`, and `test_provider_payload_equals_final_prompt` exist in `tests/test_covers.py`. **NOT VERIFIED:** runtime debug record/payload for a real FastGen call.

## T-04: Montage queue

```mermaid
sequenceDiagram
  participant UI as Editor/Outputs UI
  participant EL as Electron IPC
  participant W as spawned bridge worker
  participant S as settings/locks/status
  UI->>EL: run-montage-queue
  EL->>W: spawn with stdio ignored
  EL-->>UI: snapshot after 180 ms
  W->>S: update task status, projects and outputs
```

The worker receives Node/Remotion runtime variables from Electron. **Risk:** the 180 ms response is not a completion signal. **NOT VERIFIED:** worker liveness, cancel/recovery and actual Remotion/ffmpeg output.

## T-05: Publication V2

```mermaid
flowchart TD
  O[MP4/package ready] --> I[publication item]
  I --> A[allocation preview/assignment]
  A --> S[frozen publication snapshot]
  S --> E[execution stages]
  E --> U[YouTube upload]
  U --> P[processing + metadata + tags + thumbnail + schedule]
  P --> R[receipt/reconcile]
  R --> AN[analytics / engagement record]
```

`publication_v2.py` defines stages `AUTH_CHECK`, `VIDEO_UPLOAD`, `YOUTUBE_PROCESSING`, `TITLE`, `DESCRIPTION`, `TAGS`, `THUMBNAIL`, `POST`, `CARDS`, `END_SCREEN`, `SCHEDULE`. A status called `UNVERIFIED` is explicitly used in the UI for an unconfirmed publish time. **NOT VERIFIED:** any live upload, Studio post/card/end-screen automation, scheduled publish, receipts or external API result.

## T-06: OAuth handoff

```mermaid
sequenceDiagram
  participant U as Operator
  participant UI as Analytics UI
  participant EM as Electron in-memory job
  participant BR as bridge OAuth service
  participant G as Google/callback service
  U->>UI: OAuth / Revenue button
  UI->>EM: startYoutubeOAuthHandoff
  EM->>BR: start handoff
  BR-->>EM: session metadata
  EM->>BR: finish handoff asynchronously
  U->>G: manual authentication/consent
  G-->>BR: callback/token route
  BR-->>EM: success/failure
```

Manual authentication was intentionally not automated. The audit did not inspect OAuth token state. **NOT VERIFIED:** callback availability, multi-brand channel selection, refresh metrics and token recovery after process restart.

## T-07: Channel research state

`channel_research.py` trace ends at isolated per-profile task/result record creation, TXT parsing/deduplication and export serialization. The bridge exposes `import-channel-research-txt`; no complete static trace for background discovery, analysis, pause/resume/soft-stop or UI result management exists in the current dispatcher/Page union. **Result: NOT IMPLEMENTED OR NOT REACHABLE; requires clarification before external testing.**

# Issue 425 — visual stock duplicates (2026-10-21)

## Scope and root cause

Issue: https://github.com/thrixicpa-del/NewsFlow/issues/425
Base: `3507f13cac9a0fde26d7ca8ec74f8a5dfe3f6a10`.

Stock families use SHA-256 of immutable originals. This correctly rejects byte duplicates but treats two different encodings/views of the same shot as unique. The owner's 62-second demo manually short-listed two Amazon BHX4 warehouse assets. That authored demo was not automatic-planner acceptance; it exposed a real missing visual check in the stock selector.

## Change

- Keep source hashes, attribution, relevance, HD, screen-text gates and settings unchanged.
- Compare the already-scored window's cached CLIP image features with this project's accepted stock windows. Reject only strong view matches: normalized mean cosine >=0.95 and bidirectional coverage of at least two thirds of sampled frames at cosine >=0.94. A shared subject or one matching intro is insufficient.
- Continue to a distinct eligible asset/window; return no candidate when none survives. Existing continuity/manual-replacement behavior remains in force.
- Preserve explicitly permitted SAFE_REUSE below the uniqueness boundary and remove rejected batch claims from visual exclusions.
- Recovery compares retained playable windows, including source-start when trim is disabled. Other corrupt/short slots do not abort repair.
- Reuse the existing 64-entry content/model-bound preview cache. No full-library decode, new model, dependency, schema, UI or IPC contract.

## RED / GREEN

Before implementation, two behavior regressions FAIL: the near-identical different-byte asset wins instead of the distinct alternative; the duplicate is accepted when no alternative exists. The new feature access test initially raises AttributeError because the API is absent. These are the expected pre-fix results.

Review found seeding recovery could abort on another present-but-corrupt/short file. A new regression reproduced that ValueError before the duration/preparation guard; GREEN after the minimal fix.

Nine focused new tests cover alternative selection, exhaustion/context, rejected reservations, deliberate reuse, frame coverage, retained source-start, failed feature extraction, multiple broken retained slots and content-bound preview reuse/invalidation.

## Source verification

- Baseline isolated selection/diversity: **30 PASS** (8.155 s).
- Intermediate targeted selection/cache/diversity/pipeline/review/continuity: **69 PASS** (36.387 s; overlaps final run).
- Final related stock, continuity/recovery, runtime action, Electron security and secret scan: **225 PASS** (101.271 s), `PRODUCTION_WRITE_GUARD=PASS`.
- Exact final combined command:

```powershell
python -B tests/run_isolated.py tests.test_stock_sources tests.test_stock_settings tests.test_stock_selection tests.test_stock_pipeline tests.test_stock_review_regressions tests.test_stock_diversity tests.test_stock_credits tests.test_stock_media tests.test_stock_scene_semantics tests.test_stock_advertisements tests.test_ai_index_preview_cache tests.test_montage_continuity tests.test_stock_continuity_pipeline tests.test_stock_continuity_selection tests.test_stock_quality tests.test_footage_quality_recovery tests.test_runtime_action_map tests.test_electron_security tests.test_secret_scan -q
```

- Ruff on all five changed Python files: **PASS**. `git diff --check`: **PASS**.
- Independent read-only review of complete diff and adjacent callers: one recovery finding fixed; final actionable findings **0**.
- Initial baseline was accidentally invoked without `tests/run_isolated.py`; it produced isolation/setup errors. It is **not PASS**. Re-ran correctly; no production write was authorized.

## Real isolated stock replay

No network, provider calls, fake scores, or fake media. Used licensed cached Commons originals and actual CLIP/HD/text checks. Exact reported pair: warehouse 1 accepted; warehouse 2 **REJECTED**; distinct container handler **ACCEPTED**. Original hashes unchanged. 31.54 s cold, five preview entries; this small replay is not a large-project benchmark or full UI pipeline acceptance.

```json
{
  "scope": "Actual cached CC stock, real CLIP/HD/text guards, no providers or scores mocked, no network",
  "reportedWarehouseDuplicate": "REJECTED",
  "distinctContainerHandler": "ACCEPTED",
  "firstScore": 0.24494168162345886,
  "alternativeScore": 0.32266974449157715,
  "unchangedOriginals": true,
  "elapsedSeconds": 31.54,
  "coldPreviewEntries": 5,
  "assets": [
    {
      "assetId": "79797460",
      "source": "https://commons.wikimedia.org/wiki/File:Amazon_warehouse_BHX4_loading_docks_1.webm",
      "sha256": "ca784d69572bc5a7d5e3746d3922bff5cb875c77b35d309d9835d54dc3e5b5f5"
    },
    {
      "assetId": "79797461",
      "source": "https://commons.wikimedia.org/wiki/File:Amazon_warehouse_BHX4_loading_docks_2.webm",
      "sha256": "748729b76df00945664e01a1cb056eaf9235118bab6abbd479f3996a5969c62d"
    },
    {
      "assetId": "42113970",
      "source": "https://commons.wikimedia.org/wiki/File:Container_reach_stacker,_Port_of_Rauma.webm",
      "sha256": "ea6ea1b7e91486e9a7e8e913d3be3641741e898b3e6b9f9fbd3fc8ea733f40b2"
    }
  ]
}
```

## Gate boundaries

- Linux CI / Windows native: pending PR runs; record final exact-head results in the PR before merge.
- UI/type/build/security: unchanged contracts; independently rerun by configured CI. No additional full local frontend run.
- Dependency audit: no dependency/lock changes; configured CI audit remains enabled.
- Hosted CodeQL/dependency review: repository-variable controlled; report actual status, never translate SKIP to PASS.
- Frozen binding: **11 PASS / 1 FAIL** locally, same deferred failure as base: old lock lacks scene_intent.py/visual_evidence.py, and new source is not in the old Frozen. Owner explicitly said not to build Frozen. Lock/workflows are not altered, no Frozen/EXE built or promoted. This is a source-only change, not release/packaged acceptance.
- Existing saved timelines are not silently re-edited. The visual guard operates during selection and missing-source recovery. Thresholds are conservative heuristics tested on the reported example, not a guarantee of internet-wide uniqueness or exhaustive same-location detection.

Post-merge verification and final CI evidence belong in the PR/issue record for its exact source revision.

# PR403 source integration checkpoint — 2026-10-21

Owner requested continuation with short dependency/compatibility checks, without heavy acceptance runs. Base: main ec98d0e3ddc7d1aac6b83ac6df4bd6b9f2fd15fe; original PR403 a61438cb094647a796d083e269b326ba926ba8dd.

## Changes

- Resolve the five conflicted files against current main, retaining blocks, stock provenance/continuity, overlays, measured VoiceMap words, bounded semantic windows and concurrent history persistence.
- Fix a real dependency incompatibility: PR403 passed local_files_only to the new ONNX adapter, whose constructors rejected it; cached-text loading still imported removed FastEmbed. Add explicit local-only support without permitting a download on missing/incomplete cache, and update mock targets to the installed runtime.
- Preserve main's aviation/empty-terminal/civilian-vessel interpretation in the semantic-intent path. The first integration run reproduced seven assertions failing in existing stock scene tests; they now pass.
- Keep legacy cold-window admission scoped to the legacy selector. Stock selection uses its own scoring and must not enter that admission lifecycle.
- Retain main's continuity mux CPU retry, along with PR403's exact source-window frame budget. This combination has not had fresh real-video acceptance.

## Short checks actually executed

All commands used tests/run_isolated.py with LOCALAPPDATA=/tmp/newsflow-review-boundary. Every completed run printed PRODUCTION_WRITE_GUARD=PASS.

- ONNX adapter: RED 3 constructor/cache errors, 8 passing; GREEN included in 83 passing tests covering stock scene semantics, person rotation, story/reporting context and actual scene context (1.046s).
- Cache/budget/history/stock/recovery set: 74 passed, 5 failed (31.66s). Four stock failures exposed unnecessary legacy admission and were corrected; one actual-decoder test could not import cv2.
- After correction: stock pipeline, stock continuity selection, stock review regressions, block pipeline: 42 passed (26.18s).
- Visual feature reuse/evidence and semantic intent/roles: 136 passed, 1 failed, 1 deselected (1.95s). The failure was absent cv2 in the native decoder test; the previously observed other cv2 test was explicitly deselected. These decoder checks are NOT PASS.
- Measured VoiceMap words and project serialization: 2 passed (0.036s).
- Scoped Ruff, source compilation, secret scan and whitespace checks passed.

No model downloads, original-library scans, new Windows/Frozen/EXE builds or long media acceptance were requested or run. UI dependencies and source are unchanged from reviewed main. This environment does not have the complete locked Python/media runtime.

## Still blocking full acceptance

The old real ARM12/RU19 failure is NOT resolved by these integration tests. The original voice tracks, private library snapshot, partial project and rejection ledger are on the prior Windows machine under D:/NewsFlow_PR403_Test_Temp_20261015, not in this checkout. Their cause cannot be asserted from summary reports. Do not replace missing footage by unrelated politicians, weaken visual gates, or claim completed MP4 acceptance.

PR403 remains draft pending reproduction from those inputs/rejection records and review of the combined renderer on the real runtime. Existing historical integrity failures remain recorded. Frozen r49 is stale for changed core sources; lock hashes were not rewritten. This checkpoint is not merge/release readiness.

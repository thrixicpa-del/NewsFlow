# PR403 bounded technical review — 2026-10-21

Owner requested a proper issue/PR review and merge when ready, without deep/heavy checks or an EXE build. Reviewed main `ec98d0e3ddc7d1aac6b83ac6df4bd6b9f2fd15fe` and PR403 `559b29e552be8ddad968e9208a9fbf81f28f26a1`. The working branch was clean and fast-forwarded to that PR head before changes.

## Result

**Merge blocked.** Merge conflicts have been resolved, but that is not acceptance. Two concrete integration problems were identified; the unsafe local interval problem is corrected here. The unsupported visual query problem and the Frozen source binding remain open. No main merge, issue closure, model download, original-media analysis, provider call or EXE/Frozen/lock rebuild was performed.

## Corrected local/hybrid interval contract

`StockSceneSelector._local` called `_semantic_clip_ok(query, item)` with an implicit six-second window. It discarded the interval chosen by `person_window`, returned start zero, and preparation rotated the source without checking the resulting interval. This could select another speaker or reject a valid three-second target interval. The same implicit-duration problem affected local recovery. Recovery also discarded the original item's dynamic evidence and assessor.

Changes:

- Pass one explicit local-window callback to both production selector constructors. Choose and validate the actual scene duration and source start.
- Preserve that start in `StockChoice`, validate position rotation, and keep exact accepted windows during fast reuse.
- Preserve the local item's person/visual evidence and indexed assessor during recovery, on a copy of the item.
- Add four synthetic regressions through preparation/recovery with real semantic checks: unsafe rotation, three-second interval in hybrid mode, exact fast reuse, and recovery with retained annotations.

RED: the first two regressions failed with `0 != 4` and selection of stock instead of the valid local interval; the recovery regression failed with zero candidates instead of one. A preliminary two-scene reuse fixture did not reach reuse because the existing minimum unique pool is two; the final three-scene regression preserves that contract. GREEN: all 86 related tests passed after the correction. No identity/action threshold was lowered.

## ARM12/RU19 root cause — still open

The earlier integration report incorrectly said the old D: evidence was absent on this machine. Read-only inspection confirmed the retained final UI summary, two partial projects and diagnostics are available under `D:/NewsFlow_PR403_Test_Temp_20261015/story-reporting-final-long-ui-20261020-attempt1`. This corrects availability only, not the old FAIL.

The saved source run (`60a05f2c22bdefc755128d19b286544ddc384a52`) is FAIL: 11 completed scenes before ARM scene 12 and 18 before RU scene 19. Both failures are `no-admissible-material-in-bounded-pool`. ARM has 508 candidates, 268 unique `semantic-incompatible` and 211 `entity-geography-conflict` rejections; RU has 503 candidates, 478 unique `semantic-incompatible` rejections. Both have zero hard-valid candidates and zero new cold work. No completed MP4 acceptance is implied.

A fresh disposable, no-model/no-decode reproduction used real `ClipIndex._with_visual_assessor`, `query_topic` and `_semantic_clip_ok`:

| Query | Visual topic | Raw candidate accepted | Indexed assessment | Indexed candidate accepted |
| --- | --- | --- | --- | --- |
| `Azerbaijan Baku` | None | true | None | false |
| `border checkpoint guards fence` | None | true | None | false |

`assess_visual_window` returns None for unsupported queries before decoding. The new indexed-evidence guard interprets that None as a rejection. This is a deterministic false-negative path matching the retained zero-work failures. Other location/entity rejections still need their own assessment; it is not proof that every candidate is suitable.

Required next correction: support appropriate bounded visual intents/context for these requests and verify real suitable/negative windows. The existing city visual role may be reusable; checkpoint/border coverage needs explicit evaluation. Simply allowing absent indexed evidence or returning unrelated politicians would weaken the safety contract, so neither workaround was applied. No expensive real-input rerun was performed.

## Independent Windows failure and fixture correction

On reviewed head `559b29e`, Windows run [39601100147](https://github.com/thrixicpa-del/NewsFlow/actions/runs/39601100147) failed in `test_normal_continuity_mux_retries_failed_nvenc_once_with_cpu`. The old mock supplied duration 3.2s, including a removed .15s margin, whereas the integrated renderer correctly requires 92 frames / 30fps for 3.05s. Its incomplete `SimpleNamespace` also lacked `reason`.

Reproduced the exact AttributeError locally before changing the fixture. Use the real `MediaHealth` contract with duration `92 / 30`. Keep all two-attempt, NVENC failure, CPU retry and CFR assertions. The targeted regression then passed in .012s, with production guard PASS. The full synthetic stock-render suite subsequently passed all six tests in 104.973s, guard PASS. Production renderer logic was not weakened.

## Fresh checks

Counts below are separate executions with overlapping coverage; do not add them into a unique-test total.

Before the new fix, on `559b29e`:

- `python -B tests/run_isolated.py --pytest tests/test_onnx_clip_adapter.py tests/test_footage_v3.py tests/test_footage_followup.py tests/test_footage_actual_scene_context.py tests/test_footage_quality_intent.py tests/test_footage_quality_roles.py tests/test_visual_feature_reuse.py tests/test_visual_evidence.py tests/test_visual_cold_budget.py tests/test_montage_cold_fairness.py tests/test_footage_quality_recovery.py tests/test_montage_history_persistence.py tests/test_footage_three_country_matrix.py tests/test_footage_fresh_context_diversity.py tests/test_footage_archive_diversity.py tests/test_footage_quality_visual.py tests/test_footage_person_rotation.py tests/test_footage_political_context.py tests/test_footage_political_context_review.py tests/test_footage_story_scope.py tests/test_footage_reporting_context.py -q`: **477 PASS**, 63.77s, guard PASS. Includes the previously unavailable decoder checks; local cv2 is available through opencv-python-headless.
- `python -B tests/run_isolated.py tests.test_stock_scene_semantics tests.test_stock_pipeline tests.test_stock_review_regressions tests.test_stock_continuity_selection tests.test_footage_block_pipeline tests.test_overlay_persistence tests.test_overlay_remotion_contract tests.test_runtime_action_map tests.test_electron_security tests.test_secret_scan -q`: **111 PASS**, 97.092s, guard PASS.
- `pnpm test:ui`: **505 PASS / 63 files**, 18.25s. Frontend sources are unchanged by this fix.
- `pnpm typecheck`, `pnpm verify:security`, `pnpm build:web`, `pnpm build:desktop`: **PASS**. Source builds only; Vite reports an existing large-chunk advisory.
- `pnpm audit --prod --audit-level=high`, `python -m pip_audit -r requirements.txt --strict`: **PASS**, no known vulnerabilities reported. `python -m pip check`: PASS. These are current advisory results, not a claim of complete runtime lock parity.
- `python -B tests/run_isolated.py tests.test_footage_block_media tests.test_core_runtime_guard -q`: **11 PASS / 1 FAIL**, 6.285s, guard PASS. The three-second real synthetic block MP4 passes. Failure is the stale Frozen binding for `scriptor/bridge.py`; it remains FAIL.

After the interval fix:

- `python -B tests/run_isolated.py tests.test_stock_pipeline tests.test_stock_selection tests.test_stock_continuity_selection tests.test_stock_review_regressions tests.test_stock_continuity_pipeline tests.test_footage_quality_recovery tests.test_footage_person_rotation -q`: **86 PASS**, 27.883s, guard PASS.
- `python -B tests/run_isolated.py tests.test_stock_render -q`: **6 PASS**, 104.973s, guard PASS. Real synthetic media only, no original library or providers.
- Scoped Ruff, secret scan and `git diff --check`: PASS.
- Independent read-only full product diff review identified the two problems above. Repeat review of the final correction found no additional actionable findings, including both selector constructors and the fixture correction.

Independent checks of `559b29e`: [Linux CI 39601100046](https://github.com/thrixicpa-del/NewsFlow/actions/runs/39601100046) **FAIL** at the Frozen guard; [Windows 39601100147](https://github.com/thrixicpa-del/NewsFlow/actions/runs/39601100147) **FAIL** at the stale retry fixture, corrected here. CodeQL and dependency review are SKIPPED, not PASS. CI of this correction must be assessed separately.

All completed isolated test commands in this review reported `PRODUCTION_WRITE_GUARD=PASS`. Historical settings/covers integrity FAILs remain recorded and are not cleared by these results. Existing production files and original libraries were not intentionally modified.

## Other open issues

- #404/#414/#417: source already integrated through #424; open remaining acceptance and stale Frozen source binding are preserved. No new feature work added.
- #402: PR403 remains the active implementation; the unsupported visual intents above prevent acceptance and merge.
- #416: requested local-video zoom remains a separate unimplemented task; no open implementation PR to merge.
- #221: concurrency workflow remains a separate task with unfulfilled acceptance; no closure or unrelated implementation.

Release/packaged/clean-Windows/provider/long real montage runs: **NOT RUN**, per the requested bounded scope. A merge-ready or release-ready result is not claimed.

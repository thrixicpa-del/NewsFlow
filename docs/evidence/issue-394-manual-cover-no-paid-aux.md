# Issue #394 — manual Covers do not authorize auxiliary paid AI

- Issue: https://github.com/thrixicpa-del/NewsFlow/issues/394
- Source base: `db1b5d58438fb27bf0ec35c49a4b49d5b37ecf03` (`origin/main`).
- Branch: `fix/issue-394-manual-cover-no-paid-aux`.
- User approved: manual imported/editor prompts use no auxiliary paid text/vision API; explicitly requested FastGen image generation remains paid. Automatic workflows are unchanged.
- Runtime/profile and existing immutable Core/EXE artifacts were not modified for this fix.

## Cause and implementation

TXT import/editor already saved literal text with `prompt_provider=manual`. Rendering did not consult that ownership before either the political-country semantic fallback or the missing-public-person resolver. The latter could make three paid OpenAI attempts. Exact repeat also incorrectly applied automatic-political identity requirements to manual prompts.

The explicit persisted manual marker now excludes those render-time paid resolver branches and their automatic missing-identity blocker. A guard inside the resolver independently rejects auxiliary AI work for manual ownership before constructing a provider or inspecting keys. Exact manual repeat keeps its saved provider prompt without imposing the automatic political portrait policy.

Local portrait/reference resolution, operator-selected faces, literal prompt persistence, ProductionItem ID routing, exact-text fields, render-time V2 construction, FastGen operation/count/reference routing and ordinary automatic AI resolution remain in place. This is not a global OpenAI disable: explicitly requesting an AI rewrite remains a separate operation.

## RED / GREEN

Baseline:

```text
python tests/run_isolated.py tests.test_cover_manual_prompt_readiness tests.test_cover_prompt_pairs_import -q
11 tests PASS; PRODUCTION_WRITE_GUARD=PASS
```

Before implementation, the new suite ran 9 tests with 9 assertion-failure records (the direct-resolver case checks two manual-marker spellings). Failures reproduced paid-provider construction, the no-key manual-render blocker, mixed-batch leakage and the exact-repeat blocker. The manual portrait/reference preservation control passed. After the minimal fix:

```text
python tests/run_isolated.py tests.test_cover_manual_no_paid_aux -q
9/9 PASS; PRODUCTION_WRITE_GUARD=PASS
```

The paid image boundary is replaced by a specific offline image writer; text API construction and all unmocked HTTP are fail-on-call. Import, settings/library persistence/reload, real batch dispatch, ID selection, final prompt construction and staged file publication execute normally in disposable storage.

## Verification (Windows-native)

```text
python tests/run_isolated.py tests.test_cover_manual_prompt_readiness tests.test_cover_prompt_pairs_import tests.test_cover_text_triples_import tests.test_cover_scene_briefs tests.test_cover_result_identity tests.test_cover_queue_tombstones tests.test_cover_quality_selection tests.test_covers scriptor.test_cover_library scriptor.test_command_contract -q
416/416 PASS; PRODUCTION_WRITE_GUARD=PASS

node node_modules/vitest/vitest.mjs run src/ui/features/covers/covers-view.test.tsx src/ui/features/covers/covers-polling.test.tsx electron/cover-prompt-import-ipc.test.ts electron/cover-auto-resume.test.ts --maxWorkers=1
66/66 PASS (4 files; disposable TEST root)

python -m ruff check scriptor/bridge.py tests/test_cover_manual_no_paid_aux.py
PASS
python scripts/secret-scan.py
SECRET_SCAN=PASS
pnpm verify:security
SECURITY_GATE=PASS
pnpm typecheck
PASS
pnpm build
PASS (existing large-bundle warning; no tolerance/guard change)
git diff --check
PASS
```

Independent read-only review found no actionable issues and independently reran the 9 new tests with production-write guard PASS. The existing command-contract CI job includes the new auxiliary-API suite through unittest's supported `load_tests` hook. This keeps the tests in their focused module while ensuring CI executes them.

The initial push with an added workflow step was rejected because the existing OAuth token lacks workflow-write scope. No permissions, credentials or authentication were changed. The workflow addition was withdrawn in favor of the existing command-contract test entry point; the final source diff does not change workflows.

```text
python tests/run_isolated.py scriptor.test_command_contract -q
15/15 PASS (6 original + 9 manual Covers contracts); PRODUCTION_WRITE_GUARD=PASS
```

## Frozen/runtime limitation — intentional, not hidden

```text
python tests/run_isolated.py tests.test_core_runtime_guard -q
10 PASS / 1 FAIL (repository binding stale)
```

The accepted base already requires `scriptor/media_health.py`, absent from the existing r46 lock. This fix additionally changes `scriptor/bridge.py`; the old immutable Frozen cannot contain it. No lock/hash/provenance was adjusted to conceal staleness. Frozen rebinding/EXE packaging is a separate task, and this source PR is not a packaged-runtime or release-ready claim. The currently opened old EXE still has its old behavior.

No dependency changes; dependency audit and full-project suites are left to the configured independent CI. No real-provider acceptance is claimed.

```text
PAID_CALLS=0
FROZEN_REBUILT=NO
TEST_EXE_BUILT=NO
PRODUCTION_WRITE_GUARD=PASS
```

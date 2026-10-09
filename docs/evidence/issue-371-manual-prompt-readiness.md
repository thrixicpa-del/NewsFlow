# Issue #371: manual prompt readiness

Repository: `thrixicpa-del/NewsFlow`.
Source base: `03a2da4b85a9faf8510dd92d65252bf1e38ae377`.
Date: 2026-10-09. Validation host: native Windows / PowerShell.

## Root cause and fix

Read-only inspection found an imported, user-owned 902-character prompt in
both settings and the Covers library, under the correct ProductionItem ID.
The import succeeded, but render readiness reported no visual prompt before
FastGen was invoked. No production text or credentials are included here.

`_cover_active_prompt_options()` incorrectly applied the automatic semantic
scene/history extractor to manual text. That extractor rejects briefs longer
than 800 characters and strips style-only text. Consequently an accepted
manual prompt could disappear at the readiness check.

The helper now returns nonblank manual options literally, retaining its
normalized deduplication. Automatic options still use the original extractor.
History still independently uses its bounded scene extractor. No importer,
editor, provider routing, quality/fallback, final builder or Frozen binding
was changed.

## RED -> GREEN and integration evidence

Before the source fix, new regressions failed at manual lengths 801, 902 and
12000, for literal style text, and for both import/editor render integration
paths with the reported missing-prompt error. Blank rejection and AUTO/history
bounds already passed. The same regressions pass after the fix.

The integration tests use disposable storage, real import/editor persistence,
library hydration, ProductionItem ID resolution and final prompt assembly.
Only the paid FastGen boundary is mocked, returning a PNG inside the supplied
staging directory; the real output publication fence remains enabled.

Assertions cover literal persisted manual text, full V2/typography/negative
rules at render time, exact headline/subheadline, the requested Nano Banana 2
operation, retained operator face selection, and an unchanged unselected row.
This is offline contract evidence, not a claim of live provider acceptance.

## Checks actually executed

| Command / scope | Result |
| --- | --- |
| `python tests/run_isolated.py tests.test_cover_manual_prompt_readiness -v` | PASS, 7 tests |
| `python tests/run_isolated.py tests.test_cover_manual_prompt_readiness tests.test_cover_prompt_pairs_import tests.test_cover_scene_briefs scriptor.test_cover_library scriptor.test_command_contract -q` | PASS, 75 tests |
| `python tests/run_isolated.py tests.test_runtime_action_map tests.test_electron_security tests.test_secret_scan -q` | PASS, 15 tests |
| `pnpm exec vitest run src/ui/features/covers/covers-view.test.tsx electron/cover-prompt-import-ipc.test.ts` | PASS, 51 tests |
| `pnpm exec vitest run` | PASS, 374 tests / 52 files |
| `pnpm typecheck` | PASS |
| `pnpm build` | PASS; nonblocking Vite chunk-size warning |
| `pnpm verify:security` | PASS |
| `pnpm verify:secrets` | PASS |
| `scripts/audit-python-dependencies.ps1` | PASS, no known vulnerabilities |
| Ruff on changed Python files | PASS |
| `git diff --check` | PASS |
| Production-write guard from isolated Python runners | PASS |
| `python tests/run_isolated.py tests.test_core_runtime_guard -q` | FAIL, 1 of 10: expected stale `scriptor/bridge.py` source blob |

The expanded Covers run (382 tests) had four failures and one error. All five
also reproduce when the unchanged base-main implementation of
`_cover_active_prompt_options` is loaded from Git and substituted into the
same disposable test environment. These are not hidden or counted as PASS:

- `CoverLocalCompositorTests.test_enhanced_duplicate_rewrite_preserves_old_scene_until_provider_changes_strategy`
- `CoverLocalCompositorTests.test_every_enhanced_duplicate_direction_preserves_story_with_grounded_intensity`
  — fixtures mention a damaged bridge but provide only a routine-maintenance
  source; factual rejection precedes the expected semantic-duplicate diagnostic.
- `CoverQueueTombstoneTests.test_headline_batch_rejects_a_stale_job_before_provider_or_status_write`
  — current code emits a strict stale-ID error rather than the old selection error.
- `CoverQueueTombstoneTests.test_fastgen_batch_rejects_a_stale_job_before_provider_or_status_write`
  — current code raises the strict stale-ID error instead of returning count zero.
- `CoverQueueTombstoneTests.test_title_tombstone_blocks_a_stale_session_before_cover_generation`
  — the fixture contains an active durable ID, which current code preserves
  despite a historical title tombstone.

Expanded command:
`python tests/run_isolated.py tests.test_cover_manual_prompt_readiness tests.test_cover_prompt_pairs_import tests.test_cover_scene_briefs tests.test_covers tests.test_cover_queue_tombstones scriptor.test_cover_library scriptor.test_command_contract -q`.

These baseline tests and their business behavior remain unchanged in this PR.
The PR must not be described as fully green or merge/release-ready while the
applicable gates remain failing.

The focused 69-test subset was also run locally. An attempted CI step addition
was removed before push because the stored GitHub OAuth authorization lacks
the `workflow` scope. The existing CI remains unchanged; the new test module
is not automatically included in it. The unchanged Frozen guard still reports
stale source. No OAuth action or permission expansion was performed.

## Safety and release boundary

- Paid/provider calls: **0**; OAuth/publication actions: **0**.
- Production settings, queues, credentials and media were not modified.
- Core r42 and all immutable EXEs were left untouched.
- Core lock/package/provenance files were not adjusted to hide stale source.
- Core/TEST EXE rebuild and packaged acceptance are a separate release stage.
- No merge; the existing EXE does not acquire this source fix automatically.

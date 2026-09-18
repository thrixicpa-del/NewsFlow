# Covers — Functional Acceptance Log

## COVERS-001 — reliable bulk cover text and visual prompts

Status: **FIX VERIFIED LOCALLY; PENDING CI**

### Confirmed defect

- RED reproduced in `coverWordPairGenerationPayload`: selected index `7` with durable ID `production:7` emitted the index but dropped `productionItemIds`.
- The backend correctly requires durable ProductionItem identity for selected current-session work, so the incomplete UI payload could be rejected as stale/missing selection.

### Verified behavior

- Primary paired actions are explicit:
  - `Придумать заголовки и подзаголовки — всем` sends `indices: []` and targets all current rows.
  - `Придумать заголовки и подзаголовки — выбранным` is available only with a selection and sends exact indices plus matching durable `productionItemIds`; it never falls back to all.
- Prompt actions retain the same exact all/selected contract, including durable IDs for selected rows.
- A valid all/selected scope with no missing headline, subheadline, or prompt returns a normal `operationResult` with `count: 0`; stale or invalid durable scope still remains an error.
- One paired action completes missing headlines first and then missing subheadlines in the same durable scope. A zero-work phase does not abort the other phase, and the final summary is calculated from state persisted by both phases.
- Existing manual headline and subheadline values are preserved unless force/regenerate is explicitly requested.
- Deterministic mass regression completed **50/50 headlines + 50/50 subheadlines**, all non-empty and READY, with no silent omissions.
- A separate 50-row failure regression leaves the injected terminal row explicitly FAILED for both headline and dependent subheadline, with a reason instead of an empty field.
- Deterministic prompt mass regression completed **50/50 topics**, each with a non-empty selected prompt, the requested two options, and terminal `Промпты готовы` state.
- Cover word and prompt provider calls use a shared bounded policy of at most four actual provider attempts per row/stage. Evidence: two transient failures then success used 3 attempts; a permanent error used 1; exhausted transient failure used exactly 4 and ended FAILED with persisted attempt count and sanitized reason.
- Existing semantic validation/repair and prompt safety-filter fallback remain intact.
- Headline and subheadline pause flags persist independently. A paused worker waits before the next actual provider request; resume processes only missing work and does not restart READY rows. Continue sends only the resume command and does not create a duplicate generation worker.

### Local verification

- RED: targeted UI — `1` file, `13` tests, `3` expected failures (missing durable ID and old labels/state contract).
- GREEN backend: `python tests/run_isolated.py tests/test_covers.py -v` — **112 PASS**, **0 FAIL**, **0 SKIP**.
- GREEN tombstones: `python tests/run_isolated.py tests/test_cover_queue_tombstones.py -v` — **14 PASS**, **0 FAIL**, **0 SKIP**.
- GREEN targeted UI: `pnpm exec vitest run src/ui/features/covers/covers-view.test.tsx` — **1 file / 13 tests PASS**.
- GREEN full UI: `pnpm test:ui` — **34 files / 180 tests PASS**.
- `pnpm typecheck` — **PASS**.
- `PRODUCTION_INTEGRITY_GUARD_TEST` / `PRODUCTION_WRITE_GUARD` — **PASS** (the guard's intentional mutation probe was detected).
- `python scripts/secret-scan.py` — **PASS**.
- `python -m ruff check tests/test_covers.py` — **PASS**.
- `git diff --check` — **PASS**.
- No real network or paid provider calls were made; tests used deterministic fakes only. Production data was not touched.

### Deferred acceptance

- Real image/provider acceptance is deferred to **COVERS-003**.

### Review fix — atomic selected durable scope

- A selected batch is now rejected atomically when any requested index or durable ProductionItem ID is stale, tombstoned, absent, or mismatched.
- Regression coverage proves a partial stale `[0, 1]` selection and an index-to-ID mismatch both fail before generation; provider calls remain **0**.
- A selected row can no longer silently disappear from a bulk command. All-scope behavior and ready-scope `count: 0` semantics are unchanged.

## COVERS-002 — render queue, retry, pause and stale-state cleanup

Status: **FIX VERIFIED LOCALLY; PENDING CI**

### RED evidence and bounded fixes

- RED reproduced for both `regenerate_covers` and `regenerate_covers_new_prompts`: indices `[0, 1]` mapped to `production:z`, `production:a`, while separately sorted IDs produced the wrong order. Both paths now retain ordered `(index, ProductionItem ID)` pairs, and the complete selected scope is validated before file deletion.
- RED reproduced stale image resurrection risk: cleanup did not advance `updatedAt`, so a newer persisted row could win hydration. Result cleanup, one-variant deletion and regeneration cleanup now advance the row revision; all render-derived paths, prompt-image mappings, attempt history and stale progress metadata are cleared without removing the topic, approved words, visual prompt or face configuration.
- Retry metadata RED showed rounds 2–4 as not rewritten. The fixed bounded contract is four rounds × four attempts. Deterministic evidence: six retryable failures then success used exactly **7 calls**, ended `Готово`, retained only the successful new path and recorded round 2 as rewritten; exhaustion used exactly **16 calls** and ended `Ошибка FastGen` with the 4×4 reason; a permanent failure used exactly **1 call**.
- Pause/Continue regression proves the in-flight row finishes, the next unstarted row becomes `Приостановлено`, Continue processes only that remaining row, and the READY row is not regenerated. Continue with no paused work remains a normal no-op. The existing cross-process lock rejects a duplicate start with `count: 0` and **0 provider calls**.

### Cleanup, history and new-prompts workflow

- Explicit confirmed actions `Удалить картинки — выбранные` and `Удалить картинки — все` use exact durable selected scope or explicit `all:true`; empty selection is never interpreted as all. One-variant delete keeps sibling variants.
- `Повторить с новыми промптами` is a clean prompt-only attempt: old owned files and stale render metadata are removed first, prompt generation uses `rewrite:true`, success ends at `Новые промпты созданы`, failure remains `Ошибка промпта`, and image rendering waits for a deliberate next action.
- Ctrl-click selection is covered for add, toggle-off and ordinary single replacement. `Перегенерировать промпты выбранным` sends the exact ordered indices and matching durable IDs, keeps selection visible, and exposes current readiness as `N/M` with an explicit error count.
- Deterministic bulk rewrite evidence: **20/20** selected rows reached the current rewrite-success state; injected failure produced **19 ready + 1 failed**. `Перегенерировать обложки выбранным` is enabled only at full current readiness and sends the same exact selected durable scope.
- Historical isolation remains intact: prior-release `legacy-cover:*`, deleted IDs/titles and stale library writers cannot repopulate the active queue. The **84 current vs 97 history** regression remains green.

### Render orchestration and visible state

- Deterministic 50-topic render completed **50/50** with distinct current files, correct ProductionItem ownership, no silent omissions and measured maximum concurrency **10** (>1 and <=10).
- The injected terminal-failure run completed **49 ready + 1 explicit `Ошибка FastGen`** without losing neighboring rows.
- The queue exposes truthful states including `Ожидает`, `Подготовка запросов`, retry round/attempt, `Приостановлено`, `Ожидает лимит FastGen`, `Готово`, `Ошибка FastGen` and `Новые промпты созданы`; retry detail includes total attempt information such as `7/16`.
- Primary render controls are separate and unambiguous: `Пауза генерации`, `Продолжить генерацию`, and `Запустить готовые`.

### Local verification

- RED: ordered regeneration IDs, stale cleanup revision, rewritten retry metadata and five missing UI contracts failed for the expected reasons before production changes.
- `python tests/run_isolated.py tests/test_covers.py -v` — **125 PASS**, **0 FAIL**, **0 SKIP**.
- `python tests/run_isolated.py tests/test_cover_queue_tombstones.py -v` — **14 PASS**, **0 FAIL**, **0 SKIP**.
- `python tests/run_isolated.py scriptor/test_cover_library.py -v` — **39 PASS**, **0 FAIL**, **0 SKIP**.
- `pnpm exec vitest run src/ui/features/covers/covers-view.test.tsx` — **1 file / 19 tests PASS**.
- `pnpm test:ui` — **34 files / 186 tests PASS**.
- `pnpm typecheck` — **PASS**.
- `PRODUCTION_INTEGRITY_GUARD_TEST` / `PRODUCTION_WRITE_GUARD` — **PASS** (the guard's intentional mutation probe was detected).
- `python scripts/secret-scan.py` — **PASS**.
- `python -m ruff check tests/test_covers.py tests/test_cover_queue_tombstones.py scriptor/test_cover_library.py` — **PASS**.
- `git diff --check` — **PASS**.
- No real or paid provider calls were made; all provider paths used deterministic fakes and temporary files. Production data and production media were not touched.

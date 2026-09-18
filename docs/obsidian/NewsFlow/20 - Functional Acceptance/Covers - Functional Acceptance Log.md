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

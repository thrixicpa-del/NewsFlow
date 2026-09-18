# Montage — Functional Acceptance Log

## MONTAGE-001 — queue, retry, pause/resume and isolated real render

Date: **2026-09-19**
Status: **FIX VERIFIED LOCALLY; PENDING CI/REVIEW**

### Confirmed RED

- Two overlapping `run_montage_queue` calls crossed the status-only ownership check before either persisted an active row and produced **2 planner calls for one row**.
- `{indices: []}` was interpreted as an implicit missing-only/all-eligible launch instead of an empty selected scope.
- A stale completed Job whose title no longer matched the current scenario at the same index reached Montage planning with that row's current MP3.
- A forced retry preserved the previous valid MP4 bytes on disk, but cleared its current `outputPath` before the replacement succeeded; a failed replacement therefore hid the still-valid result.
- The UI kept launch controls enabled while the queue command Promise was pending, and the retry action was labelled ambiguously as `Повторить с начала`.

### Minimal fix

- Added one Montage-specific atomic cross-process owner file. A live owner rejects an overlapping start before session loading/planning/render; a dead owner is reclaimed; ownership is released in `finally` after success or failure. Pause remains queue state owned by the same invocation, not a second owner.
- Empty `indices` now fail closed. Backend missing-only launch is explicit through `missingOnly: true`; exact non-empty selected indices remain exact.
- Scenario pairing now requires the current title, completed Job narration and current MP3 to agree on the same scenario index. A mismatch becomes visible `Ошибка` before planning.
- Normal launch remains missing-only and cannot rerender a valid READY MP4. Forced retry retains the previous validated `outputPath` until `render_project` atomically publishes and validates its replacement; failure leaves the old bytes/current pointer intact and records the new error.
- Existing configured worker pools remain unchanged. Deterministic 10-row coverage measured **planning max active 3** for configured 3 and **render max active 2** for configured 2; all 10 rows were planned/rendered once.
- Existing safe-stage pause loop remains authoritative. Repeated pause observations do not start work; Continue resumes the same owner, and an idle pause persists harmlessly.
- UI launch/retry controls now use the existing combined `queueActive` state, preventing duplicate command dispatch while either persisted work or the local launch Promise is active. Retry labels are explicit: `Повторить монтаж выбранных`, `Повторить монтаж всех`, `Повторить монтаж`.
- Selected cleanup remains exact; all cleanup requires `all:true`; empty selection removes zero items; MP3/source media stay untouched; project deletion outside the dedicated project root fails closed.

### Deterministic coverage

- `python tests/run_isolated.py --pytest -q tests/test_montage_queue.py` — **68 PASS, 0 FAIL, 0 SKIP**.
- New coverage proves: one owner/one render under an overlapping start; stale owner reclaim and `finally` release; paused owner rejection; exact selected and explicit missing-only scopes; current scenario/MP3 identity; READY preservation; failed retry preservation; interrupted recovery followed by one deliberate resume; safe pause/continue; worker limits/no omissions/no duplicates; and selected/all cleanup boundaries.
- `pnpm exec vitest run src/ui/features/montage/montage-view.test.tsx` — **1 file / 14 tests PASS, 0 FAIL, 0 SKIP**. Coverage includes rapid double launch, Ctrl-selected exact scope, empty selection, READY exclusion, explicit retry, pause/continue, selected/all delete distinction and error retry visibility.

### Real isolated NewsFlow render

- Runtime path: `prepare_montage -> render_montage -> render_project(renderer="ffmpeg")` with an isolated `NEWSFLOW_TEST_ROOT`, temporary footage index, project folder and output folder.
- Review folder (ignored, not committed): `.artifacts/NewsFlow-MONTAGE-001-review-20260919-v2/`.
- Final MP4: `outputs/Synthetic isolated montage smoke.mp4`; non-empty **262,431 bytes**; SHA-256 `876388e0201b4c36c2bba3f446bfd25cfb4dab25691eb61ca4f1481e0f44949a`.
- Manifest: `MONTAGE-001-smoke-manifest.json`.
- Media validation: **8.000 s**, **1920×1080 (16:9)**, H.264 video at **30 fps**, AAC stereo audio at **48 kHz**. Video and audio streams are present; output covers the complete narration without a missing visual tail and is the current isolated row output.
- Synthetic inputs: one 8-second MP3 and three distinct 10-second 16:9 clips. SHA-256 manifests before/after are identical for all four inputs.
- `assets/ffmpeg.exe` was hydrated (**87,638,016 bytes**) and reported FFmpeg 7.1. No production media/settings/session/index path was used or changed.

### Full verification

- `python tests/run_isolated.py scriptor/test_montage_render.py -v` — **19 PASS, 0 FAIL, 0 SKIP**. The initial baseline had two fixture-missing FAILs; ignored synthetic `work/smoke-clips` fixtures were created and both real FFmpeg tests then passed.
- `python tests/run_isolated.py tests/test_timeline.py -v` — **12 PASS, 0 FAIL, 0 SKIP**.
- `python tests/run_isolated.py tests/test_build_montage_runtime_guard.py -v` — **1 PASS, 0 FAIL, 0 SKIP**.
- `python tests/run_isolated.py tests/test_montage_benchmark.py -v` — **2 PASS, 0 FAIL, 0 SKIP**.
- `pnpm test:ui` — **34 files / 195 tests PASS, 0 FAIL, 0 SKIP**.
- `pnpm typecheck` — **PASS**.
- `python -m ruff check tests/test_montage_queue.py` — **PASS**.
- `PRODUCTION_INTEGRITY_GUARD_TEST` / `PRODUCTION_WRITE_GUARD` — **PASS** (the guard's intentional mutation probe was detected).
- `python scripts/secret-scan.py` — **PASS**.
- `git diff --check` — **PASS**.
- Total SKIP: **0**. No publication/YouTube/provider calls were made; no generated media is tracked by Git.

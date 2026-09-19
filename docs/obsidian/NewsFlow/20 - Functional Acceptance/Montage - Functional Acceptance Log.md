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

## MONTAGE-002 — footage indexing, freshness and retrieval integrity

Date: **2026-09-19**
Status: **FIX VERIFIED LOCALLY; PENDING CI/REVIEW**

### Confirmed RED

- A deleted indexed file remained visible through both `search_many` and `all_items` until a separate cleanup happened.
- The index had no persisted FPS or source-family identity, and a changed physical file could retain stale screen-text/deep-semantic state.
- A persisted active status whose owner had died remained `active`; two same-process starts could both claim the file lock; the bridge returned deep-pass counters instead of the base media scan's failed/skipped/indexed truth.
- Rapid repeated Footage indexing clicks dispatched the command twice before React state committed.
- The deep taxonomy did not cover the required broad news families, stored no compact semantic confidence, exposed no current/outdated version counts, and the default base command still ran deep enrichment instead of keeping the two tiers distinct.

### Minimal lifecycle and retrieval fix

- The fast base tier remains incremental and samples/embeds only new or changed files. Freshness is keyed by canonical path + size + nanosecond mtime; unchanged files are neither decoded nor embedded again. Reindex atomically removes missing rows, refreshes duration/width/height/FPS, resets stale English/deep labels after replacement, and reports failed/corrupt files without counting them as indexed.
- `search_many` validates physical existence once per query batch, never once per scene; stale paths cannot be returned as healthy hits. The shared SQLite/vector corpus is loaded once, duplicate queries are embedded once, ties are deterministic, and `all_items` also filters missing paths.
- Stable `source_family` is persisted independently of row IDs and returned in metadata/SearchHit. Two generated cuts under one `_slices` source share identity; unrelated sources do not collapse; identity survives restart/reindex.
- Screen-text states remain truthful (`blocked=1`, `safe=-1`, `unchecked=0`); replacement invalidates the old classification, and English exclusion removes only blocked current files.
- The bridge now has one same-process owner plus the existing atomic process file. A live duplicate is rejected, a dead owner is reclaimable, `finally` releases ownership, and a dead persisted run becomes `paused`/resumable with preserved counts and an updated timestamp. Partial/failed transactions leave no half rows and the next run resumes from committed freshness identities.
- UI uses a synchronous ref lock for the long-running index command, exposes partial-file failures, and distinguishes base ready, deep running/current, and semantic-version update required states.

### Two-tier smart/deep semantic index

- Tier 1 (`index_folders`) is the default fast base index: deterministic representative frames, one current visual CLIP embedding, physical freshness, media metadata and source-family identity. It does not automatically pay for deep enrichment.
- Tier 2 (`enrich_semantic_tags`, operator action `Улучшить ИИ-индекс`) works only from stored vectors and never reopens source videos. Semantic version is **5**; current rows are skipped, version changes re-enrich stored vectors, physical replacement resets both base/deep currency, and an interrupted batch resumes only outdated rows.
- The conservative taxonomy now covers combat, emergencies, protests, diplomacy/government, energy, economy/industry, logistics, aviation, rail/transit, urban B-roll, migration, agriculture, healthcare, weather/disasters, technology and neutral documentary context. Only compact top-3 labels/confidences are persisted.
- Search keeps CLIP similarity primary, then applies a bounded semantic/path metadata bonus plus existing rating/usage penalties. Semantic embeddings bridge English visual queries to neutral/Russian filenames; metadata overlap remains a fallback. Source-family identity is exposed for MONTAGE-003 but no diversity/rotation algorithm was added here.
- Deterministic neutral-filename coverage proves `clip001.mp4`, `clip002.mp4`, `clip003.mp4` rank first for `oil tanker at port`, `street protest crowd`, and `diplomatic negotiations` respectively after deep enrichment.

### Metadata, concurrency, counts and recovery evidence

- Real synthetic media regression: **426×240**, **29.97 FPS**, **1.6 s**; indexed resolution is exact, FPS tolerance is **±0.05**, duration tolerance **±0.12 s**, and size/mtime match filesystem truth.
- Lifecycle coverage includes add/repeat/modify/rename/delete, nested Unicode paths, overlapping roots/deduplication, unsupported files, zero-byte/corrupt media, one permission/read failure, cached-duration freshness, and no stale/duplicate healthy rows.
- Concurrent writers converge to one row per physical path; a reader sees the last committed WAL snapshot during an incremental probe; one-batch embedding failure leaves zero partial rows and a subsequent run recovers all rows.
- UI/bridge count coverage verifies truthful `total`, `processed`, `indexed`, `skipped`, `failed`, `removed`, plus blocked/safe/unchecked and current/outdated deep counts. A partial file failure is visible rather than presented as whole-index success.

### Isolated real index smoke

- Reproducible command: `python -m tests.run_montage_index_smoke --output .artifacts\NewsFlow-MONTAGE-002-index-review-20260919`.
- Ignored evidence: `.artifacts/NewsFlow-MONTAGE-002-index-review-20260919/manifest.json`; no production path/media/settings/index was read or written.
- Dataset: **8 valid synthetic clips + 1 intentional zero-byte corrupt file**, multiple durations/resolutions/FPS, two cuts from one family and three neutral filenames with distinct visual families.
- Cold base: **0.2759 s** (`8 indexed / 1 failed`); deep enrichment: **0.0077 s** (`8 current`); unchanged base reindex: **0.0054 s** (`0 indexed / 8 skipped / 1 corrupt failed`); lifecycle reindex: **0.1120 s** (`2 refreshed / 5 skipped / 2 stale removed / 1 corrupt failed`); 4-query `search_many`: **0.001401 s**.
- Structural counters: **3 filesystem scans** for three base runs, **13 media probe calls**, **0 ffprobe calls**, **2 image-embedding batches / 30 frames**, **4 text-embedding calls**. Deep passes decoded zero videos; search performed no discovery/rebuild.
- Rename old path absent/new path current; deleted path absent; in-place replacement refreshed from 640×360/30 FPS/1.2 s to **854×480/25 FPS/1.8 s**; all untouched SHA-256 hashes remained identical; corrupt media remained unindexed; all post-lifecycle hits existed.

### Verification

- `python tests/run_isolated.py tests/test_ai_index.py tests/test_montage_index_integrity.py tests/test_footage.py -v` — **31 PASS, 0 FAIL, 0 SKIP**.
- `python tests/run_isolated.py tests/test_montage_queue.py -v` — **68 PASS, 0 FAIL, 0 SKIP**.
- `python tests/run_isolated.py tests/test_montage_benchmark.py -v` — **2 PASS, 0 FAIL, 0 SKIP**.
- `python tests/run_isolated.py scriptor/test_montage_render.py -v` — **19 PASS, 0 FAIL, 0 SKIP**.
- `pnpm exec vitest run src/ui/features/footage/footage-view.test.tsx` — **1 file / 5 tests PASS, 0 FAIL, 0 SKIP**.
- `pnpm test:ui` — **34 files / 198 tests PASS, 0 FAIL, 0 SKIP**; `pnpm typecheck` — **PASS**.
- Ruff scoped checks — **PASS**; `PRODUCTION_INTEGRITY_GUARD_TEST` / `PRODUCTION_WRITE_GUARD` — **PASS**; `python scripts/secret-scan.py` — **PASS**; `git diff --check` — **PASS**.
- Total SKIP: **0**. No paid/external provider, publication or YouTube calls were made. Generated smoke media/index artifacts are ignored and not committed.

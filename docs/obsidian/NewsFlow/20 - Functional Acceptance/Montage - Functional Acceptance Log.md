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

### Review follow-up — Cutter family identity and bounded large-library search

- Confirmed RED against the reviewed code: real Cutter names `evening_report/evening_report_0001.mp4` and `_0002.mp4` produced different `source_family` values; a two-query, 20,000-row fake corpus performed **20,000** `Path.is_file` calls before ranking.
- Cutter recognition now matches only the deterministic production convention `<parent>/<parent>_NNNN.mp4` used by `cutter.py`. Those numbered cuts share the parent family; ordinary siblings such as `report_2024.mp4` and `report_2025.mp4` remain distinct. External `source_url` identity remains authoritative and restart/reindex determinism is unchanged.
- `search_many` now ranks the in-memory corpus first. It starts with a bounded candidate pool of `max(4 × limit, 32)`, validates paths only until top-K is full, doubles the pool only when stale/excluded candidates consume it, and exhausts the full ranking only when required to find enough valid rows.
- Physical existence results are cached once across every scene query in the same batch. The 20,000-row regression has two stale top-ranked rows, returns the next three valid rows for both queries, and performs only **5 unique filesystem checks** instead of 20,000. No folder discovery, media decode, embedding rebuild or SQLite corpus reload is introduced.
- New real-media smoke was intentionally not repeated because this follow-up changes only deterministic family classification and retrieval candidate validation; the prior isolated smoke evidence remains unchanged.

Review verification:

- AI index/integrity: **29 PASS, 0 FAIL, 0 SKIP**; Footage: **4 PASS, 0 FAIL, 0 SKIP**.
- Montage queue: **68 PASS, 0 FAIL, 0 SKIP**; Montage benchmark: **2 PASS, 0 FAIL, 0 SKIP**.
- Targeted Footage UI: **1 file / 5 PASS**; full UI: **34 files / 198 PASS**; `pnpm typecheck`: **PASS**.
- `PRODUCTION_INTEGRITY_GUARD_TEST` / `PRODUCTION_WRITE_GUARD`: **PASS**; secret scan: **PASS**; scoped Ruff: **PASS**; `git diff --check`: **PASS**.
- Total SKIP: **0**. Production footage/settings and provider/network paths were not touched. Status remains **FIX VERIFIED LOCALLY; PENDING CI/REVIEW**.

## MONTAGE-003 — semantic fallback, diversity rotation and ultra-fast selection

Date: **2026-09-19**
Status: **FIX VERIFIED LOCALLY; PENDING CI/REVIEW**

### Confirmed RED

- The deterministic regression initially failed because the selector exposed neither the full named fallback ladder nor one batched ladder retrieval; a high-score agriculture clip could also beat a safe oil/port context candidate.
- Legacy fallback labels were ambiguous (`RELAXED_MATCH`, `CATEGORY_CONTEXT_FALLBACK`, `RESERVED_REUSE`, `LAST_RESORT`) and local reuse could happen before an external fallback opportunity.
- The first isolated multi-video run proved that the old tail normalizer discarded the selected scene plan: four prepared beats became two full-source clips and every alternate `source_start` was reset to `0.0`.
- The real smoke also exposed an English-metadata safety hole: `ukraine_oil_tanker_wrong_country.mp4` was not rejected for a Hormuz scene because the country guard contained Russian Ukraine terms but not `ukraine/kyiv/odesa/donbas`.
- UI RED: the saved project summary and per-clip fallback/bucket/window diagnostics were present in the backend contract but invisible in the Montage timeline.

### Minimal architecture fix

- The bounded selector now records the exact order `STRICT_MATCH → RELAXED_SEMANTIC → CATEGORY_MATCH → SAFE_CONTEXT → EXTERNAL_FALLBACK → SAFE_REUSE`. Empty/missing/short/stale candidates remain invalid; reuse is permitted only after unique local levels and optional external fallback are exhausted.
- Every scene's bounded query ladder is flattened into one `ClipIndex.search_many(..., limit=256)` call. Results are regrouped in memory by scene and level; no folder discovery, media decode, embedding rebuild or full-corpus filesystem pass was added. The MONTAGE-002 bounded candidate-pool search remains authoritative.
- Ranking combines semantic score, the existing bounded topic bonus, a position-family penalty and a tiny stable hash variation. The same project seed is reproducible; different similar projects can choose different equally safe families. A 10-project/24-family regression produces 10 distinct opening families.
- Shared batch state now tracks path/family reservations plus `EARLY/MIDDLE/LATE` placements and source windows. Reusing a long source selects a deterministic different valid `source_start`; immediate A→A is avoided while another safe candidate exists. A one-family library completes through truthful `SAFE_REUSE` instead of failing.
- Semantic safety remains fail-closed at every level: frontline vs political office/agriculture, oil/port vs agriculture, Hormuz vs English/Russian Ukraine metadata and named-person contradictions are rejected even when their vector score is higher. No unrelated clip is accepted merely to complete a timeline.
- A valid prepared beat sequence is no longer collapsed by tail completion. Existing `source_start` and scene durations are preserved; only the final beat receives the tiny MP3/30 FPS margin when the source has enough material. Legacy incomplete-project recovery remains available.
- `.newsflow` clips persist fallback level, source family, reuse flag, bucket, rotation penalty/reason, strict rejection reason and source start. Projects persist selection totals and planning/retrieval/selection/fallback/external/total timings. UI shows summaries such as `4 сцен · strict 2 · semantic 0 · reuse 2` and per-clip level/bucket/start.

### Deterministic and performance coverage

- New `tests/test_montage_semantic_diversity.py`: **14 PASS, 0 FAIL, 0 SKIP**. Coverage includes every local fallback level, missing/short candidates, safety contradictions, scarce-library reuse, deterministic variation, 10 similar projects, position buckets, alternate windows, one batched index request and persistence round-trips.
- Combined isolated backend command (`test_ai_index`, index integrity, queue, benchmark, montage render, timeline and MONTAGE-003 regressions): **144 PASS, 0 FAIL, 0 SKIP** after the final safety/tail fixes.
- Large-library protection inherited and reverified: the 20,000-row fake corpus validates only the bounded candidate pool; `search_many` performs no discovery or repeated source decoding.
- Real smoke persisted per-project timings. Retrieval was **1.768 / 0.714 / 0.736 ms**; selection was **3.185 / 6.535 / 5.882 ms**; fallback expansion was **0 / 1.418 / 2.496 ms**. Total isolated preparation was **626.152 / 628.907 / 647.092 ms**.

### Isolated real multi-video smoke

- Reproducible command: `python tests/run_montage_diversity_smoke.py --output .artifacts/NewsFlow-MONTAGE-003-review-20260919`.
- Runtime path: real `ClipIndex.index_folders → prepare_montage → render_montage → render_project(renderer="ffmpeg")` with isolated app-data, settings, session, footage, MP3, project and output roots.
- Review manifest: `.artifacts/NewsFlow-MONTAGE-003-review-20260919/manifest.json` (ignored, not committed). Three related Hormuz scenarios produced three **18.000 s** MP4 files in **26.239 s** total.
- Opening families were distinct: `oil_tanker_family_1`, `oil_tanker_family_6`, `oil_tanker_family_4`. Safe repeated long-source windows included `0.0 → 3.0 → 9.0`, `0.0 → 4.487 → 8.975`, `0.0 → 9.0` and `0.0 → 6.0` seconds.
- Output SHA-256: `0bb10d395282c062ebd9e0ccc6fcddc9f672c2e2d9bdfb001156755613fd6c4f`, `218f4ef4497372b10c0fab3c785fd9b0e5a558e3e528852b723850a188a2c333`, `be4581949ad62d1811d8a316d6477374333f1c488b1f9880b12f89f25b7eb968`.
- The explicit wrong-country source was rejected; all seven synthetic source hashes were unchanged before/after. Production footage/settings/session/index were not read or modified; no external/provider call was made.

### Verification

- Targeted Montage UI: **1 file / 15 tests PASS**; full UI: **34 files / 199 tests PASS**; `pnpm typecheck`: **PASS**.
- `tests/test_build_montage_runtime_guard.py`: **1 PASS**.
- `PRODUCTION_INTEGRITY_GUARD_TEST` / `PRODUCTION_WRITE_GUARD`: **PASS** (including the guard's expected intentional mutation detection).
- `python scripts/secret-scan.py`: **PASS**; scoped Ruff for the new/changed test files: **PASS**; `git diff --check`: **PASS**.
- Whole-file Ruff for legacy `scriptor/bridge.py` / `scriptor/timeline.py` still reports pre-existing repository-wide import/style debt unrelated to MONTAGE-003; no bypass or broad cleanup was made.
- Total SKIP: **0**. No production media/settings and no paid/external provider paths were touched.


## MONTAGE-003 independent ChatGPT review follow-up — semantic safety and family identity

Date: **2026-09-19**
Status: **PATCH COMMITTED BY CHATGPT; PENDING CODEX VERIFICATION**

Independent review of commit `127f5c47384e66734663ffeaf7e96c4c2e194280` found bounded correctness gaps:

- Montage-local source-family identity diverged from the MONTAGE-002 index contract, so recent/batch diversity could fail to recognize the same source family.
- `CATEGORY_MATCH` / `SAFE_CONTEXT` and terminal reuse could accept weak unrelated candidates that were not covered by a hard contradiction guard.
- Position rotation could penalize a relevant family strongly enough to promote materially weaker footage.
- The no-index bootstrap and broken-clip recovery paths could bypass the intended semantic/performance guarantees; recovery could call `index.all_items()`.
- Timeline fallback/final render margin did not consistently preserve/subtract `source_start`.

The bounded follow-up:

- reuses `ai_index.source_family_identity()` as the family source of truth;
- rejects contradictory versioned semantic tags and applies score floors to broad fallback/reuse;
- makes diversity a small near-match preference rather than a relevance override;
- requires actual metadata overlap when CLIP search is unavailable;
- keeps broken-clip recovery on bounded `search_many` only and records recovery/tail fallback diagnostics;
- preserves `source_start` through timeline alignment and makes remaining-source checks offset-aware;
- adds deterministic regressions and expands the isolated MONTAGE-003 smoke from 3 to 5 related videos with two explicit contradiction sources.

No PASS claim is recorded for this follow-up until Codex completes the isolated backend/frontend/safety verification and fresh 5-video smoke.


## MONTAGE-003 verification RED — follow-up 1

Date: **2026-09-19**
Status: **FIX COMMITTED; PENDING RE-VERIFICATION**

Codex verification of `f499a181d7f5313a4fa9a8a10a3f80a3750d1484` stopped at backend RED:

- 152 tests: **130 PASS / 4 FAIL / 18 ERROR / 0 SKIP**;
- all 18 errors shared one ChatGPT patch regression: `same_bucket` was referenced after its inline calculation had been moved into the bounded rotation helper;
- four family tests still encoded the older broad `clip_*` grouping assumption, while the actual NewsFlow Cutter contract is `<source-folder>/<source-folder>_NNNN.mp4` and MONTAGE-002 intentionally keeps unrelated generic `clip_001.mp4` / `clip_002.mp4` distinct.

The correction restores `same_bucket` only for diagnostics/reason text and updates those four regressions to the real Cutter naming contract. Production family behavior remains the MONTAGE-002 canonical `source_family_identity()`.

No production data/media/settings were touched. Re-verification is required before any GREEN status.


## MONTAGE-003 review follow-up — strike disambiguation

Date: **2026-09-19**
Status: **FIX COMMITTED; PENDING RE-VERIFICATION**

During the RED follow-up review, ChatGPT found one adjacent semantic ambiguity before restarting the full suite: English `strike` can mean a military strike or a labor strike. The previous military-action detector treated both identically, allowing a workers/picket query to inherit military category/context fallback.

The fix keeps military `strike` behavior for attack/war queries but suppresses military expansion when the query explicitly contains labor/workers/union/picket context. A deterministic regression proves a workers strike does not expand to military categories and rejects a `frontline-combat` candidate in favor of `workers-strike`.

No production paths or provider calls are involved.

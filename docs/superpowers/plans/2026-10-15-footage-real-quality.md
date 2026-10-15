# Real footage quality implementation plan

> For agentic workers: use executing-plans to implement this plan task by task. Follow the owner's already approved task; no further start approval is required.

**Goal:** Correct observed real footage substitutions and finish both unchanged 300-second narrations when the authorized pool supplies compatible context.

**Architecture:** Trace the actual planner, retrieval, selection and rendered windows before changes. Evaluate a small contrastive visual taxonomy using the existing cached CLIP, with versioned file/window evidence separate from path hints and person annotations. Introduce only the demonstrated corrections; retain technical constraints, fast reuse, history and rotation.

**Tech stack:** Python, SQLite, existing CLIP models, FFmpeg, source Electron.

**Spec:** Owner's attached PR403 real-quality follow-up, supplementing `docs/verification/PR403_FOLLOWUP_V2_2026-10-15.md`.

## Global constraints

- Same branch and draft PR403; no main/merge/issue closure/Frozen/EXE/lock changes.
- Original authorized media/audio read-only; all state and outputs disposable. No model downloads, providers, scopes, production shutdown or media uploads.
- Local inventory/sample budget:325 source files,440 explicitly assessed development/holdout windows; automatic selector alternative-window cumulative total remains UNKNOWN, with the unchanged96 cold-window limit per index instance. Initial180 expanded after demonstrated logistics/person coverage gaps using existing vectors from a read-only27,797-row snapshot; frozen69 holdout families unchanged. Other limits:1800 seconds per media pass,4096MiB RSS. Evidence allocation initially6GiB, increased to8GiB by the recorded storage ruling below to retain historical failures and complete final comparisons on D. No labels or expected winners injected into automatic retrieval.
- Old semantic/protest fixes remain regressions; historical integrity FAIL remains unresolved by writer.

## Task 1 — establish observed root causes and fixed data

- [x] Read manifests and actual outputs; reconstruct all scene rows and scene17 rejection trace with distinct-file/examination counters.
- [x] Inventory authorized roots cheaply; freeze expanded manifest and independent source groups.
- [x] Baseline actual imports on the unchanged narrations; save an independent test-index snapshot with SQLite backup.
- [x] Measure existing window scores, timing/selection work and near negatives before selecting the minimal visual refinement.

## Task 2 — local action and evidence contracts

Files: `scriptor/bridge.py`, `scriptor/scene_intent.py`, `scriptor/ai_index.py`, focused tests.

- [x] RED for demonstrated long VoiceMap segment/action leakage; smallest correction while retaining approximate timing provenance.
- [x] RED for metadata-only action acceptance, named protest hints and confirmed interval precedence where reproduced.
- [x] Separate path/model/confirmed provenance and retrieval/relation/reuse diagnostics; preserve old project loading.

## Task 3 — bounded window assessment and selection

Files: focused visual-evidence module if justified, `scriptor/ai_index.py`, `scriptor/bridge.py`, focused tests.

- [x] RED for bar→official, portrait/crowd→port, map→direct action and direct/context ordering across retrieval levels.
- [x] Evaluate multiple frames inside the selected interval with existing models and close negatives. Cache by file signature/window/model/taxonomy; recompute classifier verdicts and bound cold work.
- [x] Share context-aware validation across normal/reuse/repair/tail; preserve confirmed person intervals and all hard restrictions.
- [x] Improve repeated validated work only after profiling; separate unique candidates from repeated examinations.

## Task 4 — actual output and independent gates

- [ ] Repeat six short controls and both unchanged300s voices on expanded pool; capture all scenes, boundaries, coverage and reasons. Review development errors, then frozen holdout without changing its labels/split.
- [ ] Check audio/video starts, durations, endpoints, decoded output, actual frame PTS and saved source windows. Keep approximate alignment explicitly approximate.
- [ ] Compare suitable-source diversity by halves, normal/fast and serial/parallel; disclose genuine scarcity/search limits.
- [ ] Sequential A/B final source and fixed timeline: preparation target warm<=18.9s from prior instrumented16.45s baseline; cold refinement<=60s. Disclose environment differences and slower cases; wrong-frame speed is not acceptable.
- [ ] Relevant regression, source Electron, applicable independent CI/Docker/integrity gates, full diff review, same-branch push and draft PR report. No semantic completion while known listed substitutions persist.

## Current evidence and next correction

- Source changes through `2f19eed` pushed to the same draft PR. Historical Frozen-binding FAIL and production-integrity FAIL remain unresolved; readonly observer demonstrated concurrent settings/covers drift without identifying its writer. Production app stays running.
- Native relevant checkpoint:599 PASS/1 Frozen-binding FAIL/5 opt-in SKIP; related warehouse correction305 PASS; person/geography correction133 PASS. UI tests410 PASS, Windows source build PASS, Linux CI stops at stale Frozen binding. These are separate from semantic acceptance.
- Final8 source UI: voice1 INCOMPLETE at17; voice2 renders300s/50scenes, exact stream endpoints/full decode PASS,15 paths/5 families. Blind50-scene review:45 suitable context/1 beach wrong action/4 uncertain. Prior seven workshop substitutions corrected; old failures and outputs retained.
- Ruling: add a beach/swimming close-negative prompt after actual development scene22 and a failing regression; same cached CLIP, no threshold change, no source blacklist. Taxonomy4. Reuse matching stored image vectors across taxonomy revisions so the correction does not decode unchanged media again.
- Ruling: one additional frozen20-file existing-index expansion addresses missing official/person context; total325 files,256 development/69 holdout. No change to held-out families or sealed labels. Metadata-only people stay probable; visual identity is unconfirmed.
- Warm checkpoint7 voice2 preparation median21.051→8.098s on identical207-file inputs/settings/history, differing selected material. This is not final-source timing. Final8 cold103.269s fails60s target. Final A/B waits for code/data freeze.
- Final10/11fe: scene17 resolved; both300s voices/50scenes completed, full decode/stream endpoints/PCM points and guard PASS. Blind voice1:46context/4uncertain; voice2:48context/2uncertain; no known wrong action in these two outputs. Controls all6completed but control5scene2 seedlings under peaceful-rally narration remains semantic FAIL. Cross-canonical-segment sentence splitting and missing visual nursery description are reproduced adjacent causes; fixes are in progress.
- Final10 diversity:13/8 distinct paths,8/4 families, halves13/11 and8/5. Port-heavy repetition remains substantial. Owner explicitly prioritizes broad diversity between videos. Full eligible read-only snapshot contains25,566 embedded/enabled owner-root rows after exclusion of frozen holdout families; broad normal/fast serial/parallel prepares are still NOT RUN.
- Ruling: raise only cumulative evidence allocation6→8GiB, retaining historical failures and stopped11fe benchmark. New benchmark/post artifacts go to the existing isolated D test root outside the media library; C held5.599GiB at the ruling, Cfree5.67GiB/Dfree42.7GiB. No old artifacts/user data are deleted or moved. Cost if wrong: at most2GiB additional test evidence; RSS4096MiB/time1800s/cold96 and bounded broad384-work-unit limits stay unchanged.
- Remaining at that historical checkpoint: cross-segment logical clause and seedling close-negative RED/GREEN/review; eliminate repeated invalid-window cold attempts without weakening validation; repeat final actual UI/output review, new frozen sequential A/B/fixed-timeline; normal/fast/broad diversity and secondary frozen holdout; sanitized report/PR update and final CI.
- Resumed source96dc6df: clause/nursery/military/cache source blocks verified. Final12 small-pool UI outputs complete; wide11e50/300295.954s versus11d328.689s with identical50source windows,17paths/8families unchanged. This is one engineering pair, not finalA/B. Broad diversity/latency and final gates remain unaccepted.
- Ruling: retained evidence7.886GiB requires another bounded1GiB for mandatory real outputs and finalA/B; allocation8→9GiB on D with all added directories counted. No historical evidence deleted; per-case96cold/cumulative384/RSS4096MiB/time limits unchanged. Cfree41.69GiB/Dfree131.12GiB at ruling; cost ifwrong≤1GiB extra teststorage.
- Owner added semantic query analogs. Implement bounded same-role retrieval expansion with RED, batched dedup, unchanged strict query/person/action/safety and thresholds. Fair cold allocation design remains under revision; exact visual duration and interval contradictions must be resolved before implementation.

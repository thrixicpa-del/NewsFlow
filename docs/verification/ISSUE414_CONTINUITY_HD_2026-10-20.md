# Issue 414: automatic visual continuity and original HD filtering

This follow-up belongs to draft PR 415, branch `codex/montage-stock-sources`.
It starts after delivered source `6b18abb81c956622422231466ff9790592a51e6f`.
The owner explicitly replaced the earlier manual-replacement requirement:
fill shortages automatically, and expose **only `HD 720p+`** as a checkbox.
Autofill is always enabled, including saved projects with old opt-out markers.
No second Story Map/planner, packaged/Frozen build, lock rewrite, main change,
merge or issue closure is part of this work.

## Root causes and resulting behavior

- A finite exact/synonym search previously persisted missing-scene markers and
  stopped rendering. Selection now tries an explicit thematic category/context
  at the existing CLIP threshold, retaining the original scene's identity and
  contradiction guards. If that fails, the previous accepted frame is held;
  leading gaps may use the next accepted frame. If no permitted image survives
  validation, a plain dark-blue background covers the original narration slot.
  This avoids an invented unrelated event; technical/export/cancellation errors
  remain real errors. Missing-file repair also tries thematic selection first.
- API dimensions and a 1080p prepared proxy do not prove original quality.
  The enabled-by-default checkbox checks decoded original pixels before media
  preparation, including untrimmed stock and reused library stock. Video must
  have short side >=720 and long side >=1280; stills need short side >=720 and
  >=921600 pixels. Unknown/corrupt/360p originals fail. Disabling the checkbox
  permits the existing wider source-quality range. The filter applies to stock,
  not the owner's local originals. Exports retain the existing 1080p settings.
- Substring `port` in `airport` and `oil` in `soil` introduced wrong tanker/oil
  contexts. Category expansion now matches complete words. Airport/radar,
  peaceful protest and freight contexts have bounded explicit expansions.
- A hold preserves the exact beat, narration association and ordinary playback
  speed of later clips. All renderers receive a silent CFR30 prepared MP4;
  the hold uses the same fill/crop geometry as the timeline renderer, without
  zoom or looping motion. Source hashes and an atomic versioned cache protect
  reuse. Every held frame is separately checked for identity/text/advertising;
  validation failure tries another anchor or neutral pixels, never an unchecked
  freeze. Cancellation propagates without partially committing the plan.
- Holds retain the anchor's license and identify the freeze in attribution.
  They are counted as reused/held, not new original families or fictitious
  selected source windows. Neutral backgrounds add no stock license or family.
  The UI reports held/background counts separately. Real moving-footage repair
  clears obsolete hold metadata. Saved project policy retains the HD choice.

## Verification and evidence policy

Private evidence is under `.superpowers/stock-sources/continuity-hd`; no private
media or credentials are committed. RED logs cover manual stops, false HD
approval, wrong airport/oil contexts, inflated history, crop mismatch, missing
repair metadata, cancellation swallowing and unvalidated-frame fail-open.
The old 180p positive stock render fixture correctly failed under the new HD
default; its positive original is now native 1280x720. Negative low-resolution
tests remain, and no test disables HD to manufacture a positive render.

Independent scoped review reproduced the two exception-handling defects and
confirmed the final cancellation and neutral-fallback fixes. Its final review
has no remaining material findings. The new regression suites are also wired
into the existing CI stock step.

The runtime fixture deliberately contains only two approved real 1920x1080
stock originals and copied real 30-second narration. Five native narration
beats use controlled manual visual-query overrides to force leading/interior/
trailing shortages; no project or held clip is injected. This is continuity,
quality-filter and UI/IPC/media evidence, **not** proof that automatic query
planning matches a particular real story or that the full stock pool is small.
Both horizontal and vertical profiles use disposable settings/storage and
outbound-network blocking; the previous 27-original library remains unchanged.

## Gates and limitations

Results are recorded below after actual execution. Functional test success is
reported separately from the outer production-integrity guard: repeated runs
detect changing working `settings.json`. Working application processes are
present, but the writer is not established; that FAIL is not waived or hidden.
No working process is closed or working file restored/modified to obtain PASS.

Earlier Frozen/source lock FAIL, live renderer refresh limitation, bundled
decoder discrepancy, legacy-overlay VFR and real-provider/packaged acceptance
limits remain as documented in `ISSUE414_STOCK_SOURCES_2026-10-20.md`. A new
no-overlay source smoke cannot clear those unrelated failures.

### Source gate results

The private `continuity-hd/run_source_gates.py` ran, sequentially in one
four-core-affinity/4GiB Windows Job:

1. `pnpm --dir studio-ui-remotion-verify build`: PASS,8.750s, typecheck + web +
   desktop + Remotion bundle; ordinary pre-existing large-chunk warning only.
2. `python -B tests/run_isolated.py` with stock sources/settings/selection/
   semantics/review/render/pipeline/media/diversity/credits/UI, VoiceMap,
   timeline, AI index/cache/ads, queue/lock, four new continuity/quality suites,
   Electron security, command contract and secret scan: **434tests/337.290s,
   functional PASS(skip1 opt-in Electron UI), outer guardFAIL(settings.json),
   exit91**. This first combined run began before the final two review fixes;
   their RED/targeted GREEN and reviewed regression are recorded separately.
3. `pnpm --dir studio-ui-remotion-verify test:ui`: **430tests/56files/PASS**,
   Vitest63.64s, wall64.484s.
4. `pnpm --dir studio-ui-remotion-verify verify:security`: PASS,0.703s.

Whole sequential gate peak1966567424bytes below4GiB; affinity mask15.
All changed/new Python files pass Ruff, whitespace check and CI YAML parse.
Both review defects have real assertion REDs; the final26 focused tests pass
functionally in0.212s, with the same separately retained guardFAIL.

Storage inventory counts every known test root and junction target once:
17.849634GiB/24GiB,6.150366GiB spare before UI, C:12.16GiB free. No test media
was deleted to hide a failed attempt. Docker remains BLOCKED at the missing
Desktop Linux-engine pipe. Previous delivered6b18abb Windows39482677807SUCCESS,
CI39482677804FAIL; those results are not fresh-HEAD acceptance for this follow-up.

The first horizontal and vertical UI settings attempts saved HD=false and
HD=true through native commands, but failed on Electron screenshot capture
`UnknownVizError` before queue launch. Both FAILs and outer guardFAILs remain.
The private screenshot helper now retries at most four times with300ms waits,
recording every error; it still fails if no screenshot is obtained. No product
setting, assertion, quality threshold, queue state or media was bypassed.

The final reviewed eleven-suite regression (selection, pipeline, semantics,
review regressions, diversity, credits, media and all four new suites) includes
both review fixes: **124tests/90.405s, functional PASS, guardFAIL/exit91**.
The aggregate90.782s cycle remains FAIL because its original UI screenshot
attempts failed. Peak870363136bytes, four cores/4GiB; logs are not overwritten.

The screenshot retry then completed the real horizontal UI flow:
**1pytest/PASS,227.79s, outer guardFAIL/exit91**. Native controls saved HD=false,
renderer reload retained false, then saved true; a fresh Electron process
retained true before launching the normal queue. Saved plan contains5native
beats,2different real original families,3holds/18.05s,0manual markers and a
truthful40% actual unique-family ratio against the requested100% target.
Holding existing imagery is the owner's explicit shortage exception; it is
never represented as five unique originals. Preparation187.429s in this cold
scarce-library fixture is not a controlled comparison with the prior120s demo.
The vertical UI and independent encoded-media postflights are pending at this
source checkpoint, and must not be inferred from the horizontal UI PASS.

Both first complete UI outputs succeeded (horizontal227.79s, vertical251.24s),
with the guard still FAIL. Before independent media acceptance, a read-only
map/project comparison found an adjacent contract defect: the explicit-source
constructor and missing-slot marker omitted `visual_beat_index`, leaving0 for
all five clips although narration, segment IDs/order and timing were retained.
Both outputs/projects/credits are preserved under each test profile's
`artifacts/native-beat-index-FAIL`. They are not full contract acceptance.

Two real regression assertions reproduced0!=7 (RED). The minimal fix carries
the existing native beat index into selected clips and missing markers, then
into the held/background slot; it creates no new map or timing. **57related
pipeline/continuity/VoiceMap tests PASS20.267s; outer guardFAIL/exit91**. Ruff
and whitespace checks PASS. One final native UI rerender from existing caches
checks the fix without deleting source/history or downloading new material.

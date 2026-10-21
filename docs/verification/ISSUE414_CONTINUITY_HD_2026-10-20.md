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


## Final continuity render acceptance (2026-10-20)

This section supersedes the pending runtime checkpoint above. It does not
waive any historical integrity, Frozen or release failure.

### Root causes and minimal render changes

Real UI outputs revealed that `-shortest` could finish video at897frames/29.9s
while the MP3 narration still contained30s of decoded speech. Duration-only
mux produced905frames; copied frame caps left a0.133333s presentation gap.
These unsuccessful outputs, logs and projects are preserved. An intermediate
mux change also produced five old timing regression failures; later related
regressions pass, rather than deleting or weakening those assertions.

Only projects containing continuity freeze/background slots now normalize the
final video once, with an explicit narration duration/frame cap and output
CFR30 synchronization. Ordinary projects retain stream-copy mux and their
existing proxy keys/fast path. Normal FFmpeg export retries a failed final
NVENC encode once with CPU, retaining the same timing/audio limits; explicit
GPU mode remains strict. Proxy budgets for continuity projects use cumulative
frame boundaries, with new keys and health checks rejecting overlong as well
as short proxies. This removes the old extra proxy frame accumulating at cuts.

A stateful final `fps` filter could still flush a buffered frame when color
metadata changed: the next stock appeared at539 rather than540. Real preserved
outputs reproduced this in both aspects (preceding hold MAE32.91/38.21). The
final mux uses a stateless filter and output CFR synchronization instead.
At539 the correct preceding hold remains (MAE0.255/0.183); stock starts at540.
The same strict independent oracle now checks both sides of these boundaries.
The synthetic old-filter injection did not reproduce this real-media defect;
its PASS is retained as a non-reproducer, not mislabeled as a RED regression.
The long mixed-parameter synthetic test remains useful related coverage.

### Executed tests and real outputs

- After metadata repair, normal UI queue: horizontal208.32s, vertical247.70s,
  functional PASS with production guardFAIL. Existing native Story Map,
  voice IDs, timings and beat indices1..5 are preserved.
- On the final render implementation:47related render/continuity/pipeline/
  timeline/proxy-cache/intro/GPU/Remotion tests PASS39.822s; guardFAIL/exit91.
  Extending the mixed-color test to30s and checking eight pixels on both sides
  of6/12/18/24s cuts: PASS17.873s; guardFAIL/exit91. These overlapping suites
  are not added together as a count of unique tests.
- Final saved-plan exports used the real renderer/preload/Electron/Python
  `render-montage` IPC, then UI player/timeline; no new selection, downloads or
  history events. There is no fabricated direct-export UI button. Render
  commands took12.675s(horizontal) and9.053s(vertical); full UI test times
  were18.67s/15.39s. Both functional PASS, outer guardFAIL.
- Independent FFmpeg9/FFprobe encoded-media postflights PASS in both formats:
  1920x1080 and1080x1920,902frames, CFR30, maximum gap0.033334s. Final video
  duration30.066667s is frame rounding of MP3 container duration30.05s;
  the original and final decoded voice both contain exactly720000 samples
  at24kHz/30s. Whole-voice correlation0.9999400873, with independent beginning,
  middle and ending checks; no sample dropping or offset correction.
- All five native scene timings/beat indices remain intact; slots0/2/4 are
  static holds through their boundaries and the terminal frame. Both actual
  stock slots begin at native6s/18s. Source dimensions/SHA and licenses match.
  Two accepted plans create exactly two history events/24000 selected-source
  milliseconds; held slots add no source-window duration. Plain rerenders
  add no new selection events.
- Private final receipts: each profile's
  `artifacts/independent-continuity-postflight-complete/receipt.json`,
  `artifacts/human-final-review.json`, and
  `continuity-hd/one-frame-boundary-RED-GREEN.json`. Failed intermediate
  outputs remain in native-beat-index, terminal-video-tail, mux-duration-only,
  copy-frame-cap, filter-only-CFR, proxy-boundary-drift and one-frame-early
  FAIL directories. An attempted rerun correctly refused an existing evidence
  directory; it did not export, and its old-output postflight is not counted
  as fresh source acceptance. A new named directory was used afterward.
- An initial vertical boundary oracle compared a center-cropped output with a
  distorted full-width reference. That FAIL is retained. Matching source
  crop geometry corrected the oracle; thresholds stayed unchanged, and the
  stronger preceding-frame check was added. No media assertion was removed.

Human sampling reviewed the final five-beat and boundary contact sheets in
both aspects (15interior/eight boundary samples plus terminal checks), not
continuous playback of every frame. Airport footage is generic illustrative
context: the Vistara window is mostly runway/distant aircraft; the vertical
center crop shows a partial aircraft. This deliberately scarce manual-query
fixture is NOT automatic real-story, named airport/event or politician
semantic acceptance. Earlier broad27-source and120s airport evidence and its
limitations remain in the historical report.

### Diversity, speed and outstanding gates

The real fixture intentionally contains two licensed native1920x1080 originals
and five slots. Actual family uniqueness is40%, with three explicit holds,
not a false100%. No production library/source-pool cap was added. Across the
two accepted plans, family positions rotate and the Vistara source window
changes; the scarce Nippon window is reused. Holds never count as new footage.
HD720p+ remains optional and persisted; autofill is always enabled. Exact,
synonym and checked thematic selection, library reuse, source rights, identity
checks and history remain in place. Disabling HD widens eligible resolution;
it does not disable relevance or rights checks.

Cold horizontal preparation187.429s versus later169.288s is not a controlled
speed benchmark: histories/windows differ. Final9.053s/12.675s exports use warm
saved plans and cannot be presented as search speedups. The continuity-only
final normalization has one additional encoding cost; ordinary fast export
is unchanged. No12-planner/4-render throughput claim is made.

All27 original cache files were rehashed unchanged. Final precommit storage
inventory18.14GiB/24GiB (all known roots/junction targets counted once); more
than2GiB reserved. No old failed media was deleted. A separate three-second
read-only control after owned tests stopped observed one settings hash;
this does NOT explain or clear recurring guardFAIL during tests. Working
NewsFlow processes exist, but the writer is UNKNOWN. Production settings,
credentials and working libraries are not restored or edited to obtain PASS.

Parent85854f3 Windows-native39489713872 SUCCESS; CI39489713762 FAIL at the known
Frozen/source integrity lock gate. Earlier9756dfe source stock/UI/security/
build checks passed before the same Frozen failure. Final pushed commit CI
must be treated as PENDING until its own runs complete; parent results are not
fresh-head acceptance. Docker remains BLOCKED (missing Desktop Linux engine).
No Frozen/EXE build, lock rewrite, merge, main change or issue closure.
Independent scoped reviews found no remaining material code findings; final
Ruff and whitespace checks pass. This is a verified source change with known
integrity/release blockers, not an all-green release declaration.

# Issue 414 — stock sources in the existing montage

Issue: https://github.com/thrixicpa-del/NewsFlow/issues/414
Branch: `codex/montage-stock-sources`; base `43dd0709d7341eb79b308303031b5f3a47fd3ebc`.
The implementation SHA is the PR head, not the base above. No main merge,
issue closure, Frozen build, lock regeneration or installed application update.

## Behavior and architecture

The former automatic external route had no integrated five-provider permissions,
protected stock-key editor, durable licensed original cache or exact-window CLIP
gate. This feature uses the existing Story Map/VoiceMap scene query and timing.
It does not add a planner, TTS provider, renderer or runtime dependency.

- Local mode accepts local indexed material only. Hybrid tries strict local
  candidates, permitted stock videos, then semantically related local fallback.
  Stock mode tries videos and then animated licensed images. Bounded query
  expansion retains the original scene query for every CLIP and semantic check.
- Enabled sources are a permission allow-list, including cached originals.
  Pixabay/Pexels/Coverr need operator-supplied keys; Commons/NASA do not.
- Unlimited protected key rows have stable IDs, add/dedup/disable/remove, fair
  persisted rotation across processes, and bounded parallel provider requests.
  A request uses one eligible key; it does not broadcast the same query through
  every key. Provider-wide 429 cooldowns apply to every key. Invalid keys are
  excluded on subsequent requests. Multiple keys do not bypass provider limits.
- Three-way settings merging protects edits/deletions from stale queue workers.
  Secrets and signed download URLs are absent from snapshots, errors and credits.
- Cache originals are immutable SHA-256 files, verified again before reuse.
  Cross-process locks deduplicate downloads. Search responses, including empty
  responses, have a 24-hour cache. Interruption propagates through checkpoints.
- CLIP scores the actual prepared interval, not a whole-file substitute. Its
  durable verdict key includes content, query, model IDs and sampling version.
  Existing semantic and on-screen text constraints remain active.
- Existing uniqueness percentage/ranges, family reservations, recent-history
  preference and permitted reuse boundaries control all three modes. Stock
  family identity follows original bytes across providers and derivatives.
- Trim-off leaves original files untouched and uses a timeline interval; it
  cannot extend the voice or play original sound. Trim-on creates a separate
  silent derivative. Images become silent CFR animation in the selected aspect.
- A real portrait exposed center-crop loss of the head in landscape. A failing
  media regression reproduced it; image animation now fits/pads the composition
  before its small zoom. Cache version changed so old crops cannot be reused.
- Exhaustion persists scene timing/IDs/query and a manual-replacement reason.
  Rendering refuses unresolved scenes instead of inventing unrelated coverage.
  Existing healthy/manual clips are retained on resume. Missing-file repair
  uses the saved source policy and replaces attribution alongside the material.
- FFmpeg/NVENC/Remotion and proxy selection remain existing paths. Source audio
  stays excluded. `.stocks.json` and `.stocks.txt` accompany actual exported
  materials, including authors, licenses, source pages and transformations.

## Local FAST and SYSTEM evidence

All automated Python runs used `python -B tests/run_isolated.py ...`. Their
production-write guards passed. Network fixtures intercept transport; automated
tests do not call real stock APIs. Private logs are in the worktree's ignored
`.superpowers/stock-sources/`; media are not committed to the repository.

| Check | Result / evidence |
| --- | --- |
| Combined stock + queue + diversity + locks + VoiceMap + command/runtime contracts | 259 PASS, 94.413 s, `regression-post-portrait.log` (earlier 257 PASS, 94.676 s, `regression-final.log`) |
| Final provider/settings/selection/pipeline review after transfer semaphore fix | 48 PASS, 13.592 s, `stock-final.log` |
| Settings races, API secrets, timeline/Electron security and secret regressions | 58 PASS, 42.825 s, `storage-security-final.log` |
| Final image framing + selection/pipeline/review | 30 PASS, 31.669 s, `portrait-green.log` |
| Complete React suite | 423 PASS / 56 files, 12.95 s, `full-ui1.log` |
| Stock controls after attribution links | 13 PASS, `ui-attribution.log` |
| Native source Electron → trusted IPC → Python → DPAPI settings → cold restart | 1 PASS, 11.520 s, `ui-system-before-commit.log` |
| Actual six synthetic MP4 renders: local/hybrid/stock × 16:9/9:16 | 1 test / 6 cases PASS, 67.323 s, `render-acceptance.log` |
| Five fractional scenes totaling 7.137 s | 1 PASS, 13.123 s, `render-fractional-final.log`; final 50 ms of voice retained |
| Secret scan, changed-Python Ruff, TypeScript and Electron security | PASS, `fast-before-commit.log` |
| UI dependency audit | PASS, no known vulnerabilities, `dependency-audit.log` |
| Source web and desktop builds | PASS, `build-web-before-commit.log`, `build-desktop-final.log` |
| Independent provider and integrated diff review | Findings reproduced and fixed; final review found no additional material issue |
| Docker | NOT RUN/BLOCKED: Desktop engine pipe unavailable, `docker.log` |
| Frozen/source integrity | **FAIL**, preserved; see below |
| Independent CI on f94f166 | All quality stages through build PASS; final Frozen/source guard FAIL. Windows synthetic renders PASS; native UI blocked by absent Electron binary. Explicit pinned runtime install added for next run; independent GREEN not yet established. |

The six synthetic MP4s prove routing, silence, dimensions, CFR and voice timing,
using an audible 880 Hz stock contamination fixture and a 440 Hz voice fixture.
They use fake providers/models and are not semantic evidence about real people.
Outputs and receipts: `render/f637b75190c04a738ec0da2cca94a6b5/` under private evidence.

Native UI evidence: `electron/a3807392c2e94bfba7f669f37d7a43ec/` under private
evidence, with screenshots, both process receipts and source output logs.
It changed all modes, permissions and trim, added four dummy keys, disabled one,
deleted one, then verified three protected rows and saved controls after restart.

Final reproducible combined backend command:

```powershell
python -B tests/run_isolated.py tests.test_stock_sources tests.test_stock_settings tests.test_stock_selection tests.test_stock_pipeline tests.test_stock_media tests.test_stock_review_regressions tests.test_stock_credits tests.test_montage_queue tests.test_montage_semantic_diversity tests.test_montage_queue_lock tests.test_voice_map scriptor.test_command_contract tests.test_runtime_action_map -q
```

Native source prerequisites are `pnpm build:web`, `pnpm build:desktop`, installed
FFprobe, and `NEWSFLOW_RUN_ELECTRON_E2E=1`. Then run isolated
`tests.test_stock_sources_ui tests.test_stock_render`. CI adds these checks on
Windows and the offline provider/media suite to the existing quality workflow.

## Real Armenia demonstration requested by owner

Actual public Commons search, licensing and downloads were performed separately
from offline tests. An initial image download returned 429; the persistent
provider cooldown prevented immediate further transfers. After cooldown a
different permitted parliament photograph downloaded successfully. No keys were
used and no originals were uploaded or changed.

The final demonstration uses three downloaded real assets and actual existing
CLIP models copied to isolated test storage. It uses authored three-scene input,
local Windows Russian TTS, stock selection from the bounded downloaded cache,
and the existing direct FFmpeg renderer. This is not a claim that a real
provider montage was launched through the UI or that story generation was tested.

Output: `D:/NewsFlow-StockDemo-414-20261020/Armenia-politics-archive.mp4`.
Archive context is explicit in narration. Adjacent stock credits name sources:

- Captain Spilet, [Yerevan time-lapse](https://commons.wikimedia.org/wiki/File:Yerevan_time-lapse.webm), CC BY 3.0.
- Serouj, [Armenian parliament building](https://commons.wikimedia.org/wiki/File:Armenian_parliament_building.jpg), public domain metadata.
- U.S. Department of State, [Pashinyan portrait, 2024](https://commons.wikimedia.org/wiki/File:Nikol_Pashinyan_(Pashinian),_Prime_Minister_of_Armenia_in_2024_(cropped).jpg), public domain metadata.

41.2 s; H.264, 1920×1080, 30 fps; 3 unique original families / 3 scenes; no
within-video family repetition. Actual CLIP scores: 0.2913 / 0.3102 / 0.3378,
all above the unchanged 0.22 threshold. Preparation/selection plus rendering
took 41.13 s, excluding initial downloads and model copying. This is a sample
measurement, not a before/after benchmark against the legacy online route.
Decoded output/source-voice correlation 0.999984; original voice 41.1966 s,
output decoded audio 41.216 s. `validate_rendered_montage` passed. Frames at
2/14/28/39 s inspected: correct city, parliament and preserved portrait face.
SHA-256: `4ba5e46451d1afa25dd3df1f7e1011f99762f32a4d1e07ea434e5345394a2e57`.
Full probe, scene/selection timings and receipt remain beside the MP4.

## RED history and remaining limitations

RED logs preserve missing initial modules, unsafe cached-provider permissions,
corruption/cooldown bypasses, lost attribution, stale settings/repair state,
cancel propagation, family history/reservations, model cache identity and
trim-off reuse scoring. Every reproduced product defect has a regression.
`portrait-red.log` records lost top content before the framing fix.

Earlier verification failures are retained: an unavailable test module from
PR403 was removed from this branch's invocation, not changed to PASS; a legacy
fixture without a new settings attribute exposed a compatibility bug and was
fixed with a legacy-default lookup. Electron harness attempts failed on initial
snapshot synchronization and a GPU screenshot; the harness now waits for the
real loaded snapshot and disables GPU for stable evidence capture.

`storage-security1.log` has 69 tests and one **FAIL**:
`test_repository_lock_matches_current_source_and_package_revision`: local
working source blob `e09b189...` versus locked source `ea2ce8a...`. Correction to
the earlier report: this was not proof of a pre-existing canonical baseline
mismatch. The base 43dd070 bridge blob is `ea2ce8a...`, matching the lock.
The feature changes that source; independent CI on f94f166 confirms actual
committed source `fae4e74...` versus locked `ea2ce8a...`. No lock was rewritten
to conceal the mismatch. Frozen build remains explicitly forbidden. Source
success does not clear this integrity FAIL or establish packaged readiness.

Independent quality run 39447294287 passed every stage through source build,
then failed only the existing Frozen/source integrity guard. Windows run
39447294486 passed both synthetic render tests but failed the UI prerequisite:
`electron/dist/electron.exe` was absent because pnpm blocks its install lifecycle.
The workflow now explicitly runs the pinned `electron/install.js` before source
UI E2E. This installs the test runtime, not a NewsFlow package or Frozen build.
The original failed runs and logs are retained. Next-head independent results
must be inspected; no claim of all CI GREEN.

Live keyed Pexels/Pixabay/Coverr acceptance: NOT RUN (operator keys were neither
requested nor read). Live NASA acceptance: NOT RUN; only explicit public-domain
and explicit absence of third-party rights metadata is accepted, so many NASA
results are deliberately ineligible. Commons SA/NC/ND/unknown rights are
unsupported; Coverr images unsupported. The bounded real sample is horizontal;
vertical real-topic acceptance and a continuous real UI→provider→MP4 run remain
unverified. NVENC/Remotion actual stock output, long-run throughput, packaged
runtime, clean Windows and full publication pipeline are not claimed here.

MoneyPrinterTurbo MIT was read as an architectural reference; no implementation
was copied. Official API references and limits are recorded in the source module
and [operator guide](../MONTAGE_STOCK_SOURCES.md).


## All enabled sources, zero keys — requested follow-up

26 provider contracts including an explicit all-sources/no-key regression, plus
settings/selection/pipeline: **44 PASS**, 12.625 s, production guard PASS,
`all-no-keys-offline.log`. The test proves missing-key providers receive no
unauthenticated requests while Commons/NASA discovery and Commons transfer
remain usable.

A separate fresh live profile enabled all five sources with an empty key pool.
Actual request trace: Commons search 200, NASA search 200, Commons download 200.
Pexels/Pixabay/Coverr received no HTTP requests. NASA returned no eligible material
for this query; Commons provided the licensed Yerevan video. No keys, working
settings or private footage were accessed. CLIP, screen checks, window selection
and FFmpeg were real; scene input and local TTS were authored for the demo.

Output: `D:/NewsFlow-AllSources-NoKeys-20261020/Yerevan-all-sources-no-keys.mp4`.
19.13 s, 1920×1080/30fps, one real archival source, Captain Spilet / CC BY 3.0;
credits/receipt/project accompany MP4. The chosen original interval contains an
approximately 1.13 s opening fade, retained in the automatic output; it is not a
blank whole scene. Visual frame near the end inspected as Yerevan/Ararat.

- Discovery 0.640 s; 70,853,094-byte download 3.137 s (~22.6 MB/s in this run).
- Selection with actual CLIP 11.149 s, score 0.31191 > unchanged 0.22.
- Render 5.729 s; decoded voice correlation 0.999968; source voice 19.1261 s,
  output decoded audio 19.1333 s; montage validation PASS; original hash unchanged.
- Output SHA-256 `95fe74b89361018f86129ad249fba138ffc5acb9696df91424b7ebc6c7eb6fcf`.

This verifies graceful use of available keyless sources, not access to keyed
providers without their keys, universal NASA eligibility, or continuous real
UI-provider E2E. Issue 416 (local-video zoom checkbox) was postponed by the owner;
its uncommitted work and failed media checks remain in its separate worktree.


## Synonyms, reusable library and cross-project rotation follow-up

Owner requested removal of the ten-formulation cap, use of appropriate older
stock when exact footage is unavailable, a persisted library checkbox/path and
rotation of scarce suitable sources between early/middle/late scenes. Scope is
still issue414 / draftPR415; issue416 and PR403 remain separate and stopped.

Root causes and RED evidence retained in `.superpowers/stock-sources/`:

- Long multi-clause queries truncated aliases at10; the finite deduplicated
  ladder now retains all variants and still scores against the original scene.
- Discovery considered only10 of up to40 cached provider candidates. Exhaustion
  now widens10/20/40 without bypassing source/CLIP/uniqueness checks.
- Recent-history exhaustion selected the highest-score source repeatedly:
  three-source/ten-project fixture was8/1/1; persistent least-used/window history
  yields4/3/3. An additive, versioned SQLite ledger records accepted publications
  transactionally with idempotent receipts, without rewriting original cache.
- A long plan's safe-reuse pool was1/7/7 across15 scenes/3 suitable families;
  per-plan counts now yield5/5/5. Cross-project position history rotates scarce
  sources among all three parts where semantic eligibility allows it.
- Eight failed batch claims hid later available sources; retries now stop on
  exhaustion/repeated denial/cancellation, not a fixed eight. Failed claims
  are removed from the provisional safe-reuse pool.
- One invalid prepared window hid later valid windows of the same original;
  each interval now fails independently without weakening media validation.
- Library reuse tried new discovery for recent but suitable files, and its
  first40 results could hide a suitable downloaded41st source. Library-first
  traversal now exhausts finite lazy pages before discovery; SQL metadata
  reads are500 rows, media candidate pages40, no total5000-library cutoff.

The checkbox defaults on, persists via React→IPC→Core→settings and queue commands,
and is frozen into saved project source policy for repairs. Disabled sources
remain excluded from downloaded material. Turning library preference off does
not deliberately redownload a sound immutable original from a provider result.
The actual folder is visible/copyable in UI; no cleanup command was introduced.
Stale background settings cannot overwrite the operator's checkbox edit.

Offline ten-project evidence:30 available library sources yield30 different
selected families across10×3 scenes, zero searches/downloads after seeding,
including service/selector restarts. With library preference off, discovery
widens to30 distinct sources with30 first-time transfers and one cached API
search. These are synthetic transport fixtures, not30 real stock selections.
The scarce-source position fixture visits all3 position buckets and at least3
orders; clips remain subject to original scene matching and uniqueness.

Independent read-only review reproduced/fixed41-source starvation. Re-review
also checked501 cached assets/newest500 unavailable: the older eligible file
was selected with zero discovery calls. SQLite BEGIN IMMEDIATE succeeded while
pagination was suspended; no read connection remained held across media work.
No remaining material findings were reported in that reviewed source diff.

Verification/results are completed below; previous failed logs remain intact.


### Final source/runtime evidence for follow-up

- Corrected combined backend/media/timeline/story/voice/fast-reuse regression:
  **169 tests pass /109.077s**, `library-combined-corrected.log`.
- After real UI revealed the staging-path defect below: **124 queue/review
  tests pass /35.493s**, `library-output-queue-regression.log`.
- Four dedicated configured-worker/reservation tests pass /.494s, guardPASS.
  The queue retains independent planning/render pools and submitted values;
  this is not a real12-plan/4-render load benchmark.
- Complete React regression: **426 tests/56 files pass /13.30s**. New explicit
  hybrid checkbox uses existing sourceMode; no second conflicting preference.
  The download input's max8 attribute was removed (Core already accepted any
  positive integer). RED→GREEN covers64; real source Electron cold restart
  validates64 and the library opt-out, **1 test pass /12.743s**.
- Source web/desktop build, typecheck, Ruff, secret and Electron security gates
  pass. Existing bundle-size warning retained. No dependency changed.
- Root tests used a shared outer TEST_ROOT folder in one initial combined
  attempt, so history count was7 instead of1; per-test pipeline fixture now owns
  its TEST_ROOT as well as LOCALAPPDATA. That first attempt also named two
  nonexistent test modules. Logs are preserved; corrected169-test run is above.
- Local production guard is **FAIL(settings.json)** on the long combined,
  native and real-media runs. This is not waived or reported as full PASS.
  Read-only control with no test invocation observed the working settings hash
  change over12s (`production-readonly-control.json`); multiple working NewsFlow
  processes were present. All test app-data/settings/sessions/credentials/output
  paths were disposable. Working NewsFlow was not stopped, written or restored.
  Clean independent CI remains required to remove ambiguity about those runs.
- Docker remains **BLOCKED**: dockerDesktopLinuxEngine named pipe absent.
  Frozen/source lock **FAIL** remains exactly as explained above; no Frozen
  build, lock rewrite, main update, merge or issue close was performed.

Real library replay uses a copied licensed Commons original and existing local
TTS demo voice: 19.13s MP4, actualCLIP .3112/.3047, selected original intervals
0/46.475/0 seconds across three restarted selectors, zero provider calls and
zero transfers. Cold selection10.393s; subsequent4.091/4.113s. Voice correlation
.999968; original hash unchanged. Only two of three sampled intervals were
eligible/preparable; no threshold/media tolerance was weakened. The failed
5-second probe is retained (first-windowCLIP .2026 below.22; middle preparation
failed), not claimed as a semantic success. Private `library-real-final.log` and
`real-library-1b3a7f41/receipt.json` contain receipts. These timings are not a
comparable before/after throughput benchmark.

Requested longer sample: `two-minute-demo/Aliyev-archive-demo-120s.mp4`, actual
120-second excerpt of owner's ready voice, six real local videos from three
Aliyev source families plus two licensed Commons portraits. Each of8files is
used3times; all5families occur in early/middle/late thirds,20%uniqueness for24
five-second beats. ActualCLIP .247–.368; selection48.2s/render47.186s on4CPUs;
voice correlation.999970, copied original/source voice hashes unchanged.
Archive marking is visible. This is an **authored/manual demonstration**:
portraits are explicit manual inserts, not automatic hybrid image fallback or a
new automatic StoryMap. The existing hybrid route falls back to suitable local
context; automatic stock-image fallback remains stock-only.

**New remaining media FAIL:** the existing legacy overlay path produced variable
frame intervals (up to.300s) despite r_frame_rate30. The sample is not certified
CFR30. A controlled20s reproduction with/without overlay and full PTS postflight
are preserved in `two-minute-demo/framerate-probe/` and `postflight.json`;
original MP4/receipt remain unchanged. No claim of all media gatesGREEN.

Separate actual source Electron profile reproduced a second real issue:
render-montage created the120s MP4, but project.output_path pointed to its moved
staging file, so UI hid the output. RED regressions cover direct and queue
rendering; both now save the final output path into the staged project before
atomic publication. The old UI FAIL profile is retained. Fresh UI replay result
is recorded below when complete; this invokes the public renderer bridge for
an existing authored project, not a queue button/new automated StoryMap.


Fresh source UI replay: `isolated-real-ui/profile-1e20772535` passed UI selection,
public renderer bridge→Core→FFmpeg→published output, project/player reload and
native video seek/play readiness. **1 functional test passes /83.80s**;
render56.802s,120.0s,24timeline clips; MP4 SHA256
`5683457bfe883d1f30175d4d1778898485b0d231ff5273a530522fd543bdbb91`.
Decoded voice has identical2,880,000sample counts; overall correlation.999970,
beginning/middle/end each>.99996. Screenshot04-after-render-timeline.png was
visually inspected; player shows Aliyev/archival caption and0:02/2:00 with the
timeline. Test-owned Electron exited normally. The unchanged source demo project
and original input hashes remain verified.

**Overall remains BLOCKED**, not full PASS: runner exits1 because production
settings hash changed again, and the known legacy-overlayVFR and Frozen/source
integrity failures remain. The receipt and separate verification-summary.json
explicitly distinguish functional UI/render/audio success from those failures.
Old failed profile `profile-ac29fb436d` and original CFRFAIL sample are retained.
No full automatic UI→provider→StoryMap→queue acceptance or12×4real-load result is
claimed. New-head independent CI is required; draftPR is not merged.

## User-rejected example and semantic correction

The owner correctly rejected the two-minute Aliyev example above. Its narration
describes a fictional civilian port incident, manifests, floating piers and
tugboats, without mentioning Aliyev in those120seconds. The authored portrait
sequence was selected against a general Aliyev query instead of each narrated
scene. Identity scores and intact audio do **not** prove semantic relevance.
Both previous MP4s and their technical receipts remain preserved, but their
visual semantic acceptance is **FAIL**, superseding any implied quality approval
above. The added archival lower caption is disabled in the corrected test
profile at the owner's request; existing user footage/text-filter settings are
unchanged. No archive footage is evidence that the fictional incident occurred.

Related source defects reproduced before fixes:

- Missing civilian maritime terms caused generic queries; `корабль` injected
  navy and `склад` injected fire/emergency without those events in narration.
  Concrete pier/tugboat/pontoon/mooring/cargo queries now retain the objects;
  transport/court ambiguities do not become ports/ships. Explicit naval vessels
  retain navy context without an invented civilian cargo action.
- Maritime object queries accepted explicitly titled politician portraits.
  The metadata guard rejects these unless the scene actually requests the
  person/political statement. Old parent-directory names alone are insufficient.
  A port-opening photo whose event title mentions Aliyev remains eligible for
  actual CLIP evaluation; this does not claim that the picture depicts him.
- Hybrid mode could not use appropriate stock stills after video exhaustion.
  It now uses the same licensed/CLIP-checked image preparation as stock-only,
  preserving exact-local priority, downloaded-library preference and uniqueness.

RED receipts: `semantic-correction/scene-queries-red.log`,
`portrait-guard-red.log`, `hybrid-image-red.log`, and independent-review
`review-red.log`. These are isolated private evidence; no production data edits.
Targeted GREEN:73tests/2.004s with production guardPASS; subsequent review
regressions:70functional tests/.267s with guardFAIL(settings.json).
Combined preliminary regression:294functional tests/93.383s; guardFAIL on the
active working settings remains visible and is not waived. Final rerun and
actual UI queue results are recorded below once observed.

The original native alignment engine is unavailable on this machine. A separate
QA-only faster-whisper base runtime measured the preserved120-second audio
(295positive-duration word observations, one raw zero-length observation
excluded and documented). Existing `ensure_voice_map` accepts these real word
observations through its engine interface: aligned map25segments, normal
VoiceMap projection20six-second scenes. No replacement scene planner or
fabricated timing is introduced. Raw ASR errors and transcript are preserved;
this is not proof of automatic native-whisper availability in the product.

Bounded real keyless discovery:6queries,6downloaded licensed originals/6.72MB,
4visually reviewed Baku port object photos; one known Charleston/USA floating
pier is conditional generic context, not Azerbaijan footage; one RO-RO opening
portrait is visually rejected. All six remain in the cache/evidence. Actual
port-query CLIP rejects that portrait at.1183<.22 (portrait query.2236).
Other object scores.285–.341 do not replace per-scene and geography review.
Five local candidates were inspected in15frames and rejected as oil/factory
context rather than ordinary cargo-port coverage; originals hashes held.
Provider rejection/429/cooldown is preserved, without bypass or endless retry.

Previous exact-head c2 CI: Windows native run39458008676SUCCESS;
CI39458008637FAIL at the stale Frozen Core source lock (11tests,1failure,
production guardPASS). The feature bridge differs from the locked core source;
the canonical base matched the lock. Frozen/EXE rebuild remains prohibited by
the owner, and no lock rewrite, merge or issue closure is performed.

### Corrected actual queue/MP4 checkpoint

Owner clarified that neutral illustrative objects may come from any filming
country; match the narrated objects/actions rather than requiring local footage.
This is persisted in `AGENTS.md` and the stock-source user guide. Exact named
people, flags and recognizable places/events remain distinct from illustrations.
For pumps/water treatment the owner explicitly accepts suitable provider results
without seeking an exact equipment model. Licensing and CLIP gates remain.

Final source regression: **298 functional tests PASS/85.387s**, isolated
`combined-reviewed-final.log`; production-write guard **FAIL(settings.json)**.
Ruff over all changed Python files, secret scan and whitespace checks PASS.
Independent reviewers' four semantic findings were reproduced RED and fixed;
the final two were re-reviewed without outstanding findings in that scope.

Actual UI button `Собрать незавершённые` launched source Core in isolated
`semantic-correction/profile-a90480d619`. The existing aligned VoiceMap yielded
20six-second scenes. No manual visual plan/forced candidate list or threshold
override: hybrid mode, all5providers selected, no keys, downloaded library on,
CLIP.22, uniqueness20%, existing text filter on, overlay/intro off. Eight real
licensed originals were available, including the preserved negative portrait.
The final plan has **20scenes,4source families,16safe reuses,20%actual uniqueness**
and no manual-replacement markers. Family counts7/6/5/2, no adjacent duplicate
family. These are animated stock photos; this does not claim20distinct videos
or real twelve-planner/four-render load acceptance.

Real result: `semantic-correction/Port-120s-no-caption.mp4`, SHA256
`1ec7e33902c754822c9faadad7bbc6b3c8ab983c2aef9e76cd724e0c6a060802`,
100750397bytes. FFprobe/decoded media PASS: **120.0s,1920×1080,3600frames,CFR30**,
maxPTSgap.033334s; one audio stream; all2880000resampled voice samples retained,
correlation.999970, first/middle/last windows each>.99996. All20scene-centre
frames were visually inspected: piers, port, floating platforms and water
equipment, no unrequested Aliyev and no added lower caption. Railway-branch and
customs-paper clauses receive thematic port cutaways, not literal train/paper
closeups; acceptance is illustrative context, not exact incident evidence.
An additional real freight-train still is retained for future library use;
customs-document discovery returned0. No extra rerender is claimed for it.

Measured preparation284.284s, render about20s, terminal Core response309.921s
under four-CPU test affinity, with real CLIP/text screening. The earlier run
hit its private240s observer deadline at scene10 and is preserved. This is not
a comparable before/after benchmark against the rejected authored montage;
no speedup percentage is claimed. Network discovery/downloads were separately
real and bounded; the UI replay used the downloaded cache with outbound network
blocked through a test proxy, not five authenticated live-provider acceptance. Used files came from
Commons, including NASA-origin equipment, not keyed Pexels/Pixabay/Coverr.

**Remaining UI limitation:** Core completed and saved MP4, but the running
renderer retained an old progress snapshot; the observer timed out selecting
the newly created project. That FAIL is preserved in `water-replay/ui-queue.json`.
Cold source-app restart then passed actual project selection,20clip timeline,
native MP4 metadata/seek at9s and playback readiness in **4.18s, guardPASS**;
`player-restart/04-player.png` was visually inspected. The restart does not clear
the live auto-refresh issue or earlier guard failures. It is a separate remaining
queue-start/polling investigation; no additional render was needed.

Overall draft acceptance remains **BLOCKED** by Frozen/source integrity and the
unresolved live UI refresh/production-guard evidence. Docker remains unavailable.
The corrected no-overlay sample passes CFR checks; the old legacy-overlay VFR
defect is not declared fixed. No Frozen/EXE, main merge, issue closure or edits
to working NewsFlow data were performed.

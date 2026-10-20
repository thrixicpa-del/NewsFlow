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

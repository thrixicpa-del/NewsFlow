# Issue404 — Montage overlays

[Issue404](https://github.com/thrixicpa-del/NewsFlow/issues/404). Branch `codex/montage-overlays`, base `43dd0709d7341eb79b308303031b5f3a47fd3ebc`. Separate worktree; PR403 and main untouched. Source development only, no Frozen/EXE build or runtime-lock update. Tests use disposable profiles and generated local media, without providers or original user material.

## Delivered behavior

Open **Монтаж → Наложения** in the main workspace. Images (PNG/JPG, including alpha) and videos coexist in one ordered stack. No fixed layer-count limit: each layer has its own enable/file/order/opacity, X/Y from the output top-left, size/aspect lock and1/10px increment buttons. Independent16:9 and9:16 layouts. Geometry/timing and a bounded local Canvas chromakey preview update immediately. Sound is muted by default; optional video audio mixes with narration.

Layer time uses the finished timeline including intro: start/duration, repeated occurrences, Nseconds before the end, or **До конца ролика**, for example from second6 through the actual end. Each occurrence starts at source0; short sources loop within the occurrence. Out-of-range portions are clipped without shortening base video or audio. Existing legacy folder overlay remains available and now also survives Remotion.

**Папки и независимые группы** supports several roots at once, for example a subscribe-video directory and a PNG directory. Each source has a name, enable switch, image/video/all filter and random/all mode. Each imported file retains independent geometry, timing and key settings. In random mode, checked **Использовать постоянно** members always appear alongside one randomly selected remaining enabled candidate per source and layout. All mode includes every enabled matching member. Disabled sources and filtered types are excluded; changing a type filter retains their saved controls. The readonly scanner recurses into local directories without decoding files and skips nested symlinks, Windows junctions and reparse points. Errors are reported rather than silently yielding a partial pool. The same file can belong to several sources with different controls; rescanning one source preserves its own settings.

The default retains the complete candidate pool. Each queue entry or explicit selected/all application materializes a separate choice, which is stored in its task and `.newsflow` project. Rendering and repeat export never reroll. Individual project settings contain selected layers; load the default template to edit the complete pool. Folder changes require an explicit rescan.

- **Сохранить для новых** stores the default for future queue entries; already queued/running snapshots remain fixed.
- **Применить к выбранным** and **Применить ко всей очереди** use explicit confirmation before replacing existing individualized settings. Whole-queue application includes scenario-only rows without an MP3. Running tasks are skipped and reported.
- **Загрузить настройки выбранного ролика** loads its saved template; discarding a dirty draft requires confirmation.
- **Экспортировать наложения без подбора** renders the existing saved plan. It never runs the footage planner, semantic repair or tail selection. Missing/short/incompatible saved plans fail visibly instead of silently changing footage.

The complete template is stored in `.newsflow`, independent of later default changes. Changed templates mark prior outputs stale while retaining their physical files. New output is published atomically only after successful render/validation. Source media must remain available for repeat export.

## Implementation and root causes

The former overlay was a single hardcoded green-key/bottom-centered video with `shortest=1`; Remotion accepted overlay metadata but omitted it from composition. The new shared finishing stage composites every active layer in ONE filtergraph after the selected existing renderer. Disabled overlays keep the original fast path. FFmpeg, GPU timeline and Remotion feed the same finisher. Paths are subprocess arguments, numeric/color values are bounded, network input protocols blocked, and a filter script avoids Windows filtergraph command-length overflow. Excessive repeat reactivations fail explicitly, never drop layers.

FCPXML after render references the baked MP4, including sound once: overlays survive, but layers are not separately editable in DaVinci. The UI states this limitation. Pre-render XML is deferred with a warning. Direct standalone Remotion refuses a manifest requiring the shared finisher rather than emitting a layer-less MP4.

Related regressions fixed through RED/GREEN: missing template persistence and queue isolation; stale-worker overwrites; active-state transitions hidden by a same-second ready100progress snapshot; stale output/XML fallback after template edits; staging paths persisted as final project output; re-export silently replanning footage; aspect-fit and short-video-loop preview mismatch; hidden individual overrides and dropped flattened-XML warnings. No changes to footage matching, uniqueness, history, reuse or rotation.

## Verification evidence

Canonical Python runner: `python tests/run_isolated.py ...`; local evidence in ignored `.superpowers/sdd/2026-10-18-montage-overlays/` and `test-data/overlay-404/`.

- RED: direct Remotion accepted all3overlay-bearing manifests and silently rendered without them. GREEN rejects them before incomplete output publication.
- Scoped renderer tests include schema, ordering, alpha/chroma, source reset, optional sound, legacy bottom placement, atomic failure, audio requirement, all-mode dispatch and disabled fast path. More than32mixed layers and513static images retained in graph-contract tests; UI imports40images+1video in a single stack. Large layer-count tests do not certify arbitrary hardware capacity.
- Earlier related native suites:155testsPASS (combined montage/persistence/render),29storage/securityPASS;16timeline,10DaVinci and3render regressionsPASS. Final scoped persistence23PASS37.249s. All production guardsPASS.
- Generated actual MP4 acceptance:1920×1080 and1080×1920,7s including1sintro and6snarration. Multi-image alpha/JPG stacking, opacity, positions, keyed video, source0at every repeat, gaps and end clipping sampled numerically. Full decode passes; muted FFmpeg overlays preserve decoded narration PCM exactly against the reference and retain the final audio marker.
- Actual GPU timeline and Remotion also rendered both native formats; all4outputs fully decode and retain chromakey/repeat/end pixels and the final narration marker. These generated clips verify composition/timing/audio, not real-world people or story relevance.
- Actual source Electron main→preload→IPC→Python test clicks the numeric controls/save/apply/all-queue/export controls, verifies unchanged saved footage plan and an actual queued MP4/XML, then restarts the entire Electron process and verifies defaults/individual settings remain. Initial harness/dependency errors are retained separately; they are not product PASS evidence.
- Git LFS assets initially appeared as pointer text in the fresh worktree, causing native fixture and approved-PNG failures. Existing cached binaries/PNGs were materialized only after SHA256 matched their checked-in pointer; no baseline changed. Pointer text is restored before committing. No EXE was built.

Final source checks (overlapping suites are listed separately, not summed):

- Full UI suite: **442/442 PASS**,57files,13.64s. Source web/Electron builds and typechecks PASS; no packaged EXE generated.
- Persistence plus existing montage regressions: **146 PASS**,76.601s; production-write guard PASS. Includes per-video resolution, retained defaults, selected/all application, legacy project reuse and batch preflight cancellation.
- Random/source schema, renderer and folder discovery: **46 PASS**,21.113s; production-write guard PASS. Source selection is tested over128seeded choices and preserves permanent mixed assets, independent roots, source filters and saved choices.
- Native FFmpeg/media/renderer acceptance plus scanner/direct-Remotion checks: **11 PASS**,64.705s. Both layouts in FFmpeg/GPU timeline/Remotion, including start6→end pixels and complete narration.
- Direct Remotion source filtering regression: **4 PASS**,4.883s, with real one-frame MP4s for disabled/type-filtered sources and fail-closed active-layer cases.
- Actual source Electron multi-root flow: **PASS**,61.455s: separate PNG/video roots, permanent plus random members, full default pool, selected project choices, three actual exports including an already-Ready repeat export, visible completion/unlocked controls and full process restart. Final overlap-fix build is rechecked separately below.
- Secret scan/Electron security/action-map: **15 PASS**,0.632s, guard PASS; UI security and Ruff PASS.
- Independent reviewer: **80 isolated tests PASS**,125.736s including actual GPU/Remotion replay; independent direct Remotion recheck **4 PASS**,4.295s. Final UI/source review is recorded below.

Final overlap-fix build (`index-ktwUJESo.js`) actual Electron flow: **PASS55.806s**, production-write guard PASS, including full process restart and unchanged random choices. Independent final UI/chroma **32PASS**, typecheck/security/secret scan/diff checks PASS. Independent whole-source review approved after the two P2 corrections, with the integrity/release limits below. Final direct Remotion regression log records **4PASS4.676s**.

Historical FAIL evidence remains in the ignored evidence directory. The48-test aggregate had one actual-UI failure: MP4 completed while the dashboard stayed at60%; array identity and stale Ready snapshots incorrectly ended polling. Semantic attempt/revision tracking plus fresh terminal status for every batch-cancelled selected row fixed it, and actual UI Ready→Ready repeat export is now exercised. Actual controls also initially failed contrast (1.112:1); scoped theme colors fixed it and actual rendered controls now meet4.5:1. Review found cross-source path deduplication incorrectly omitted overlapping candidates; a RED→GREEN regression now allows distinct source membership while preserving same-source settings. Review also found disabled/type-filtered sources rejected by standalone Remotion; effective-source filtering fixed it through real Node RED/GREEN tests.

**Integrity FAIL remains:** `tests.test_core_runtime_guard` detects the existing Frozen Core lock no longer matching modified source (`scriptor/bridge.py`). The20-test integrity/security run had19PASS/1FAIL. The lock and Frozen runtime were deliberately not rebuilt or refreshed, as requested. This prevents a packaged/release-ready claim and may fail the same CI gate; source verification does not clear it. Remote CI and Windows-native workflow results require the pushed draft PR.

**Remote overlay Python CI BLOCKED:** GitHub rejected the initial push because the existing OAuth connection lacks `workflow` permission to change `.github/workflows/ci.yml`. The proposed added job step is retained in `ISSUE404_OVERLAY_CI_PROPOSAL.patch`; the branch leaves the workflow unchanged so the feature can be reviewed. Existing remote CI can run its normal UI/security/type/build checks, but the new isolated overlay Python/media modules need this proposed step applied with an authorized workflow-capable connection. Their local and independent runs above do not clear that remote gate.

## GitHub alternatives considered

The owner requested evaluating ready-made solutions. Reviewed [gl-chromakey](https://github.com/bhj/gl-chromakey) and its [MIT license](https://github.com/bhj/gl-chromakey/blob/main/LICENSE), and [react-konva](https://github.com/konvajs/react-konva) with its [MIT license](https://github.com/konvajs/react-konva/blob/master/LICENSE) and [React peer requirements](https://github.com/konvajs/react-konva/blob/master/package.json). The former is a focused WebGL preview keyer; the latter adds an extra canvas/React rendering layer. Neither owns NewsFlow queue snapshots, narration timing or the existing FFmpeg export contract. The existing FFmpeg pipeline plus a small local Canvas preview was retained; no third-party source was copied, no package added, and no remote/CDN code is loaded. These are comparison references, not a claim that another repository supplied this implementation.

## Limits

Canvas RGB preview is approximate; final FFmpeg uses its own color space. Unsupported local canvas readback is visibly reported without pretending to show keyed pixels. FCPXML contains baked layers. Repeat-reactivation and Windows process/resource bounds fail explicitly; there is no fixed static-image layer limit. Very large stacks are limited by the user's hardware. Original assets remain external local references. Existing Remotion subprocess-handle ResourceWarnings are retained as an adjacent limitation. Docker is NOT RUN because its Linux engine pipe is unavailable. Frozen/package/release acceptance is NOT RUN by the owner's scope; no release-ready claim.

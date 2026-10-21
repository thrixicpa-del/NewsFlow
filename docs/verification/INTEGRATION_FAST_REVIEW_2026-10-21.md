# Integration review: stocks, curated blocks and overlays

Owner explicitly requested source integration with dependency checks and short
targeted tests, without heavy acceptance, Frozen/EXE builds or long renders.

## Corrections

- Reconciled main `64feb740badc2fe84c120bc7a81f6c649c283d6a` with #424.
  Three apparent conflicts were r48/r49 provenance fields; the merge tree was
  byte-identical to #424 `2f225659ceb5fce0b6b04977dc5005c5e1e1a008`.
- Found an actual integration defect: curated block preparation bypassed the
  normal project constructor and discarded the selected overlay template.
  Preserve the persisted task choice and defer DaVinci XML until the overlaid
  master exists, just as for ordinary montage. No reselection of random layers.
- Added a regression through `prepare_montage` and persisted project reload.
  It fails against the old controller and passes with the fix.
- Updated Vite 8.2.2 to 8.2.4 for GHSA-587h-7wmj-h5pm. Python dependency locks
  and the ONNX replacement from main are unchanged. Remotion packages remain
  consistently pinned to 4.0.515.

## Evidence checked directly

- Existing Windows run 39595971668 at f06fdf6: all steps SUCCESS, including
  stock/block/overlay Electron journeys, restart and synthetic media.
- Existing Linux run 39595971576: dependencies, audit, lint, core tests,
  stock/block tests and browser contracts passed. Failure was the real-renderer
  test requiring a previously generated fixture; later steps were skipped.
  The prior commit moved this renderer test out of the offline step.
- Existing r49 build 39596671030 at 3c736263: build, embedded FFmpeg and isolated
  Frozen bridge checks SUCCESS. This review did not rebuild it.
- Local typecheck, Electron security gate and 74 targeted UI/IPC tests PASS.
- Local Python selection: 205 PASS, 2 FAIL. The failures were media-dependent:
  overlay persistence invoked the local decoder, and a Remotion render failed
  at `uv_interface_addresses` in this environment. They are not reported green
  and no assertions were weakened. No heavy rerun was performed.
- After the controller correction: all 14 footage-block pipeline tests PASS;
  production-write guard PASS. Regression RED on original controller verified.
- Ruff for changed Python files, secret scan and whitespace checks PASS.
- Updated production npm dependency audit: no known vulnerabilities.

## Release boundary and outstanding items

Frozen r49 source identity is intentionally unchanged. The new block-controller
fix makes its source lock stale. The source-lock gate must remain FAIL until a
separate authorized Frozen build; do not claim r49 includes this correction,
rewrite its hashes, weaken the gate, or call this a packaged release.

#403/#402 remains a distinct unfinished semantic-selection branch: its final
real-input evidence has two partial projects and no finished MP4, and its
budget/coverage implementation is not equivalent to the stock/block work.
It is not safe to silently include this branch as dependency cleanup.
#416 has no implementation/PR (local-video zoom is distinct from stock-image
animation). #221 has the voice/template regression merged in #223, but the
broader conflict-serialization acceptance remains incomplete.

#406/#408/#410/#412 implementations are already in main via #407/#409/#411/#422;
the integration preserves them. No real settings, credentials, OAuth state,
media libraries, paid services or user queues were changed by these tests.

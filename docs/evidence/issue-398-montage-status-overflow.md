# Issue #398 — Montage rendering/concatenation layout containment

Issue: https://github.com/thrixicpa-del/NewsFlow/issues/398

Base: `b3eb665298fa5f372687e1a86d5710a942786cd3` (`origin/main`). Branch: `fix/issue-398-montage-status-overflow`. The user approved a focused UI fix; rendering, footage selection, planning, queue state and Core are out of scope. GPU block-size PR #397 is separate and is not included here.

## Reproduced cause

The status text was not the width owner. An initial native experiment with long diagnostics alone passed. Adding the saved project that appears as rendering begins reproduced the bug: `.project-timeline` contained 160 minimum-width clip blocks, and the implicit auto track of the parent `.nf-montage` grid adopted their intrinsic width. Existing clipping on task diagnostics did not constrain this ancestor track.

At a 1440px viewport:

| Stage | Document width | Task card width | Parent grid track |
| --- | ---: | ---: | ---: |
| Waiting, no project yet | 1425 | 703 | 741 |
| Rendering, 160-clip plan appears (RED) | 19392 | 19062 | 19100 |
| Concatenation, same plan (RED) | 19392 | 19062 | 19100 |
| Rendering/concatenation after fix | 1425 | 703 | 741 |

Both RED runs used the same real App/Editor/CSS in a hidden Electron window. Concatenation was independently run first to prove the same failure class. Evidence before implementation is retained in ignored `.artifacts/montage-status-overflow/red-render.json` and `red-concat.json`.

## Minimal fix

Only two product CSS rules were added: an explicit shrinkable `minmax(0,1fr)` Montage grid column with `min-width:0`, and `min-width:0` on its direct panels. This constrains the width owner rather than hiding overflow on the whole page.

No project clips, paths, statuses or diagnostics are dropped. The long project timeline remains horizontally scrollable **inside its own area**. Full diagnostics remain accessible in Inspector. No application logic, Python/Core, rendering settings, worker counts or queue behavior changed.

## Verification — Windows native

```text
# From studio-ui-remotion-verify, NEWSFLOW_TEST_MODE=1;
# optional NEWSFLOW_QA_ROOT selects a disposable directory parent.
# ELECTRON_RUN_AS_NODE must be unset.
pnpm verify:montage-status-layout
MONTAGE_STATUS_OVERFLOW=PASS

node node_modules/vitest/vitest.mjs run src/ui/features/montage/montage-view.test.tsx src/ui/features/montage/results-batch-export.test.tsx src/ui/layout/app-shell.test.tsx src/ui/visual-regression/visual-fixtures.test.tsx --maxWorkers=1
49/49 PASS (4 files; disposable TEST root)

# NEWSFLOW_TEST_MODE=1; selected existing cases only, no baseline updates:
# montage-empty,montage-ready,montage-84,montage-inspector,montage-configuration
node node_modules/electron/cli.js scripts/capture-workstation-baselines.mjs
5/5 MATCHED; changedPixels=0 for all 5

pnpm typecheck
PASS
pnpm verify:security
SECURITY_GATE=PASS
pnpm verify:secrets
SECRET_SCAN=PASS
pnpm build
PASS (web/Electron source/Remotion only; existing >500KB bundle warning)
node --check scripts/verify-montage-status-overflow.mjs
PASS
git diff --check
PASS
```

The new native regression checks 20 stage×viewport combinations: waiting → rendering → concatenation → error → ready, at 1440/1000/600/390px. Four active rows receive real React background snapshot refreshes. It asserts unchanged document/card widths relative to the waiting baseline, containment within the workspace, queue row containment, all 160 clips present, positive internal timeline scrolling, full Inspector diagnostics, and settings accessibility. The durable fixture is shared with a RTL regression proving the open Inspector updates from rendering to concatenation without losing content or issuing a command.

Independent read-only review found no actionable product correctness/safety findings and independently reran 27/27 Montage UI tests, syntax and diff checks. The reviewer noted that existing Windows CI only builds and does not execute the new native gate automatically. A discoverable package command and versioned compact measurement evidence are provided; **native CI execution is not claimed**. Configured independent CI is separate from the local results and is checked on the PR.

## Safety and runtime boundary

The native regression has no preload or Core bridge; snapshot data is synthetic and all command attempts throw. External HTTP(S) is blocked, and Electron userData is a freshly created disposable directory. The running user application was not stopped or patched; no credentials, media, profile settings or queues were changed. Read-only runtime/profile metadata inspection was used during diagnosis, not as a test fixture.

Python/media/Core tests are N/A for this CSS-only product change; no Core-owned source or Frozen binding changed. Existing repository Frozen staleness is not repaired or masked here. The currently running rc241 does not contain this source fix: a separate Studio EXE build is needed after acceptance. This UI fix itself does not require recompiling Core.

```text
PAID_CALLS=0
CORE_SOURCE_CHANGED=NO
FROZEN_REBUILT=NO
TEST_EXE_BUILT=NO
PRODUCTION_DATA_CHANGED=NO
```

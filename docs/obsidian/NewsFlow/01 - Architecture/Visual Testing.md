# Visual Testing

## Scope

Visual regression proves rendered workstation layouts at the approved desktop
and narrow widths. It complements component tests and Electron E2E; it does
not replace runtime/service validation.

## Baseline contract

Approved images live under
`studio-ui-remotion-verify/tests/visual-baselines/approved`. A baseline is not
updated to hide a failure. First capture the current output, identify the
source-level reason for every intended change, then use the explicit
test-only baseline update command with `NEWSFLOW_TEST_MODE=1` and
`NEWSFLOW_UPDATE_VISUAL_BASELINES=1`. Immediately rerun comparison without the
update flag; that independent compare must pass.

```powershell
$env:NEWSFLOW_TEST_MODE = '1'
$env:NEWSFLOW_UPDATE_VISUAL_BASELINES = '1'
pnpm --dir studio-ui-remotion-verify exec electron scripts/capture-workstation-baselines.mjs
Remove-Item Env:NEWSFLOW_UPDATE_VISUAL_BASELINES
pnpm --dir studio-ui-remotion-verify verify:workstation-visuals
```

The command's test root must be disposable. The test captures neither
production data nor provider content. See [[Environment Isolation Contract]]
and [[Electron E2E Strategy]] for the separate native interaction lane.

## Failure evidence

Keep the actual image, diff image, changed-pixel ratio, target width, and the
corresponding source/CSS explanation. A known browser compositor variance must
be reproduced in two isolated captures before it can justify an explicit
baseline update.

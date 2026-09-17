# Ideas — Functional Acceptance Log

## Scope

Branch: `qa/ideas-functional-acceptance`

Baseline: merge commit `4e3086d17871835c3245ad96b5c444a564572cf9` after the completed engineering-infrastructure Goal.

This log records confirmed behavior, defects, fixes, tests, CI evidence, manual acceptance, and remaining uncertainty for the Ideas block. Production content, credentials, paid provider actions, and destructive production storage operations are out of scope unless explicitly authorized.

## Workflow

For each defect:

`reproduce -> regression test -> minimal fix -> targeted checks -> relevant regression -> CI -> documentation -> manual DEV acceptance`

A green automated suite is not treated as proof that the whole Ideas workflow is correct. User-visible behavior and persisted state must agree.

## Current audit surface

- React `Ideas` workspace and its selection / loading / error states.
- Current command contracts for topics, suggestions, generation, research, plan, transfer, and deletion.
- Electron/IPC/core route continuity for current commands.
- Ideas persistence and restart behavior.
- Evidence / research status versus production acceptance.
- Provider calls, duplicate submission protection, retries, and failure reporting.
- Safe handoff into Scenarios without legacy fallbacks.

## Confirmed defect IDEA-001 — default Hormuz direction can be rejected as low CIS relevance

Status: **REGRESSION TEST ADDED; FIX PENDING**

### Expected

A grounded story under the built-in direction `Иран — Ормузский пролив`, with evidence about Iran / Hormuz shipping, must not be rejected solely because it lacks a Russia/Ukraine marker. The Ideas engine already declares `иран`, `ормуз`, and `судоход` as CIS relevance signals.

### Actual

`assess_cis_audience()` uses a separate smaller `direct_markers` tuple and does not use the module's `_CIS_SIGNALS`. A grounded Hormuz shipping item without an explicit oil/gas/export/price phrase falls into the generic global-story branch. With one entity and evidence its relevance score is below the production threshold of 50, so `build_production_item()` can return `None` and the portfolio reports `low CIS relevance`.

### Evidence

- `_CIS_SIGNALS` contains `иран`, `ормуз`, `судоход`.
- `assess_cis_audience()` currently checks only a reduced hard-coded `direct_markers` set before the causal-export fallback.
- `build_production_item()` rejects items with `cis_audience_relevance_score < 50`.
- Regression test: `tests/test_ideas_cis_relevance_regression.py`.

### Intended minimal fix

Use the canonical `_CIS_SIGNALS` relevance vocabulary in `assess_cis_audience()` instead of maintaining a second incomplete direct-marker list. Preserve the existing causal-export fallback and score thresholds. Then run the new regression test, the existing Ideas tests, the isolated relevant suite, and frontend/contract checks if the backend snapshot or UI behavior changes.

## Next checks

1. Provider action double-submit protection (`suggest-topics`, reference analysis, YouTube research).
2. Generated suggestion -> favorite -> plan -> generation state transitions.
3. Per-direction count/provider/requirements preservation.
4. Evidence state (`READY` / `NEEDS_RESEARCH`) and handoff eligibility.
5. Restart persistence and stale selection handling.
6. Ideas -> Scenarios ProductionItem context preservation.

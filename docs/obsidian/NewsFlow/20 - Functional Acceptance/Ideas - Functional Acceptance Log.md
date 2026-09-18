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

## Confirmed defect IDEA-001 — user-selected topics must bypass hidden thematic filters

Status: **MVP FIX VERIFIED LOCALLY; PENDING REVIEW**

### Expected

A grounded story under the built-in direction `Иран — Ормузский пролив`, with evidence about Iran / Hormuz shipping, must not be rejected solely because it lacks a Russia/Ukraine marker. The Ideas engine already declares `иран`, `ормуз`, and `судоход` as CIS relevance signals.

### Actual

`assess_cis_audience()` uses a separate smaller `direct_markers` tuple and does not use the module's `_CIS_SIGNALS`. A grounded Hormuz shipping item without an explicit oil/gas/export/price phrase falls into the generic global-story branch. With one entity and evidence its relevance score is below the production threshold of 50, so `build_production_item()` can return `None` and the portfolio reports `low CIS relevance`.

### Evidence

- `_CIS_SIGNALS` contains `иран`, `ормуз`, `судоход`.
- `assess_cis_audience()` currently checks only a reduced hard-coded `direct_markers` set before the causal-export fallback.
- `build_production_item()` rejects items with `cis_audience_relevance_score < 50`.
- Regression test: `tests/test_ideas_cis_relevance_regression.py`.

### Implemented minimal fix

`assess_cis_audience()` now uses the canonical `_CIS_SIGNALS` relevance vocabulary for both the relevance hit count and the reviewable reason. The causal-export fallback and all score formulas and thresholds remain unchanged.

The relevance score remains durable ProductionItem metadata, but no longer vetoes an otherwise valid, evidence-backed user-selected direction during ProductionItem creation or portfolio selection. This removes the only discovered downstream thematic veto from the current path:

`selected/custom direction -> generate_ideas -> _generate_for_vectors -> provider -> proposal/result -> ProductionItem -> scenario handoff`.

The audit found no country allow/deny list, CIS gate, hard-coded topic allowlist, or keyword gate before the provider request. Evidence-word matching only selects a bounded context bundle; no match still reaches the provider and becomes `NEEDS_RESEARCH`. Malformed/empty title checks and exact/similar duplicate checks remain active.

### Verification — 18 September 2026

- RED: `python tests/run_isolated.py tests/test_ideas_cis_relevance_regression.py -v` failed as expected before the fix: relevance score `33`, below the required `50`; `PRODUCTION_WRITE_GUARD=PASS`.
- GREEN: the same isolated regression test passed after the fix; `PRODUCTION_WRITE_GUARD=PASS`.
- MVP RED: fake-provider regression for an evidence-backed `Китай — рынок электромобилей` direction reached the provider but produced no `idea_results` before the downstream fix because the CIS relevance veto removed its ProductionItem; `PRODUCTION_WRITE_GUARD=PASS`.
- MVP GREEN: the fake-provider regression proves Hormuz, China EV, and an arbitrary custom direction all reach provider prompts. It also proves the China result survives provider response -> ProductionItem -> scenario handoff while retaining its low CIS score as metadata; `PRODUCTION_WRITE_GUARD=PASS`.
- Ideas isolated suite: `python tests/run_isolated.py tests/test_ideas.py tests/test_ideas_cis_relevance_regression.py -v` passed: `54` tests, `0` failures; `PRODUCTION_WRITE_GUARD=PASS`.
- Production integrity guard: `powershell -NoProfile -ExecutionPolicy Bypass -File tests\\infrastructure\\production-integrity-guard.test.ps1` passed. It accepted unchanged disposable storage and rejected its intentional disposable `covers-library.json` mutation.
- Contract/UI checks: **SKIP (not applicable)**. The change is limited to deterministic Python relevance scoring and does not alter bridge, IPC, snapshot, renderer, or UI contracts.

## Next checks

1. Provider action double-submit protection (`suggest-topics`, reference analysis, YouTube research).
2. Generated suggestion -> favorite -> plan -> generation state transitions.
3. Per-direction count/provider/requirements preservation.
4. Evidence state (`READY` / `NEEDS_RESEARCH`) and handoff eligibility.
5. Restart persistence and stale selection handling.
6. Ideas -> Scenarios ProductionItem context preservation.

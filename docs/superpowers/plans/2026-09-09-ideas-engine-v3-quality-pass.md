# Ideas Engine V3 Quality Pass Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make V2 production output smaller, stronger and genuinely script-distinct.

**Architecture:** Preserve the V2 flow. Add deterministic V3 quality decisions in `idea_engine.py`; keep model prompting, persistence and scenario hand-off in `bridge.py`.

**Tech Stack:** Python 3.12, unittest, React/TypeScript desktop UI, Vite.

**Spec:** `docs/superpowers/specs/2026-09-09-ideas-engine-v3-quality-pass-design.md`

## Global Constraints

- Do not rebuild the pipeline or modify other NewsFlow subsystems.
- Use test-first red/green for every production behaviour.
- Do not manufacture filler: shortages are valid output.
- Stop immediately after creating `IDEAS_ENGINE_REVIEW_V3.md`.

### Task 1: Production-duplicate gate

**Files:** modify `scriptor/idea_engine.py`; test `tests/test_ideas.py`.

- [ ] Add failing tests proving eight wording variants of one event retain one
  item, while a second independently evidenced consequence can survive.
- [ ] Run the selected tests and verify they fail under V2 behaviour.
- [ ] Add `script_overlap`, `event_bundle_overlap`, `payload_overlap`, and
  V3 per-bundle acceptance limits; persist duplicate diagnostics.
- [ ] Run selected tests and `tests.test_ideas`.

### Task 2: Scores, policy and hooks

**Files:** modify `scriptor/idea_engine.py`; test `tests/test_ideas.py`.

- [ ] Add failing tests for click-score ceiling, causal CIS explanation,
  hypothetical base-event grounding and editorial policy.
- [ ] Run selected tests and verify their expected failures.
- [ ] Implement calibrated scores, reader-facing CIS explanation, hook-family
  classification, and three explicit script-policy contracts.
- [ ] Run selected tests and full Ideas test module.

### Task 3: Second quality pass and bridge/UI contracts

**Files:** modify `scriptor/bridge.py`, `scriptor/idea_engine.py`,
`studio-ui-remotion-verify/src/desktop.d.ts`,
`studio-ui-remotion-verify/src/ui/App.tsx`; tests in `tests/test_ideas.py`
and a desktop verifier.

- [ ] Add a failing test for question-limit rewrite and a weak newspaper-title
  second pass.
- [ ] Implement deterministic rewrite/rescore and model prompt constraints.
- [ ] Expose overlap, duplicate reason and hook family in the snapshot/UI.
- [ ] Run Python, TypeScript and UI contract checks.

### Task 4: Live regression review

**Files:** create `IDEAS_ENGINE_REVIEW_V3.md`.

- [ ] Run 40+ actual model candidates across seven required directions.
- [ ] Run V3 portfolio selection and record every accepted/rejected candidate.
- [ ] Compare V2 and V3 composition, score distributions and duplicate rate.
- [ ] Create the review file and stop for external editorial review.

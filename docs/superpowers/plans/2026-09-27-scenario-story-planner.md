# Scenario Story Planner Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Generate every long NewsFlow scenario from a single prevalidated story map and sequential immutable writer parts, without generic continuation or full-script rewriting.

**Architecture:** `scriptor.story_planner` owns deterministic part sizing, strict planner-map parsing, writer-context construction, and deterministic assembly. `ParallelRunner` owns provider orchestration and accepted-part state; `session` persists that state. `bridge` creates or resumes jobs without replacing an accepted multipart plan.

**Tech Stack:** Python 3, dataclasses, JSON, unittest, existing `HybridTextPool` adapters.

**Spec:** GitHub issue #260.

## Global Constraints

- Work from `fix/scenario-story-planner`, based on `1872d805c948dcb0f394b22c0e905bb04a7c7f89`.
- Do not call paid providers; all provider tests use deterministic fakes.
- Keep the saved operator prompt as the writing contract; Planner only allocates existing material.
- Normal success is N=1 Writer or one Planner plus N Writers; no continuation, full rewrite, dedupe call, or filler part.
- Persist accepted parts immediately and never mutate them automatically.
- Do not merge main or build an EXE for this normal source-level feature.

---

### Task 1: Add deterministic story-plan primitives

**Files:**
- Create: `scriptor/story_planner.py`
- Test: `tests/test_story_planner.py`

**Interfaces:**
- Produces `calculate_story_part_targets(target_chars: int) -> tuple[int, ...]`.
- Produces serializable `StoryPlan`, `StoryPartPlan`, and `StoryContentAtom` records.
- Produces `parse_story_plan_response(text: str, part_targets: tuple[int, ...]) -> StoryPlan`.

- [ ] **Step 1: Write failing calculator and validation tests**

```python
def test_calculate_story_part_targets_scales_around_five_thousand():
    assert calculate_story_part_targets(15000) == (5000, 5000, 5000)
    assert len(calculate_story_part_targets(50000)) == 10
    assert len(calculate_story_part_targets(150000)) == 30

def test_parser_rejects_missing_or_duplicate_part_ownership():
    with pytest.raises(ValueError, match="exactly"):
        parse_story_plan_response('{"parts": []}', (5000, 5000))
```

- [ ] **Step 2: Run the focused test and observe RED**

Run: `python tests/run_isolated.py tests/test_story_planner.py -q`

- [ ] **Step 3: Implement local calculator, strict parser and serialization**

```python
def calculate_story_part_targets(target_chars: int) -> tuple[int, ...]:
    part_count = max(1, int(target_chars / 5000 + .5))
    quotient, remainder = divmod(target_chars, part_count)
    return tuple(quotient + (index < remainder) for index in range(part_count))
```

Require P1 `OPENING`, middle `MIDDLE`, final PN `FINAL`, unique ordered part IDs and exactly-once content-atom ownership.

- [ ] **Step 4: Run focused tests and observe GREEN**

Run: `python tests/run_isolated.py tests/test_story_planner.py -q`

### Task 2: Build planner and bounded writer contracts

**Files:**
- Modify: `scriptor/story_planner.py`
- Test: `tests/test_story_planner.py`

**Interfaces:**
- Produces `build_story_planner_prompt(request, part_targets) -> str`.
- Produces `build_story_writer_prompt(request, plan, accepted_parts, part_index) -> str`.
- Produces `seam_tail(text, limit=500) -> str`.

- [ ] **Step 1: Write failing context-bound tests**

```python
def test_late_writer_gets_only_previous_seam_tail_and_future_index():
    prompt = build_story_writer_prompt(request, plan_30, accepted_parts, 16)
    assert long_p1_text not in prompt
    assert len(extract_seam_tail(prompt)) <= 500
    assert "P18" in prompt and "P30" in prompt
```

- [ ] **Step 2: Run focused test and observe RED**

- [ ] **Step 3: Implement prompts**

The planner receives topic, full operator contract, production context already appended to the request, length bounds and all part targets. A writer receives the unchanged operator contract, thesis/macro map, its atom summaries, used IDs, future reserved IDs, and only the previous seam tail. It explicitly forbids internal headers and global final except in PN.

- [ ] **Step 4: Run focused tests and observe GREEN**

### Task 3: Replace normal continuation with multipart runner orchestration

**Files:**
- Modify: `scriptor/runner.py`
- Test: `tests/test_runner.py`

**Interfaces:**
- `Job` gains optional serialized `story_plan`, `accepted_story_parts`, and progress metadata.
- `ParallelRunner.run(..., resume_jobs=...)` preserves resumed jobs.

- [ ] **Step 1: Write failing runner tests**

```python
async def test_three_part_run_calls_one_planner_then_three_writers_without_continuation():
    jobs = await ParallelRunner(fake, 1).run([request_15000])
    assert fake.calls == ["planner", "writer:P1", "writer:P2", "writer:P3"]
    assert "ПРОДОЛЖИ" not in "\n".join(fake.prompts)
    assert jobs[0].state is RunState.DONE
```

Also cover N=1 without planner, N=30 exact call count/order, single-final role, invalid/capacity planner pause, planned-parts-exhausted SHORT, no assembled script in a provider prompt, and writer retry only before acceptance.

- [ ] **Step 2: Run focused runner tests and observe RED**

- [ ] **Step 3: Implement orchestration**

For N>=2: plan once, persist plan before P1, write parts sequentially, persist each accepted record once, then assemble locally. For N=1: issue one Writer call without Planner. Long or short final assembly becomes a truthful paused state; no generic continuation is invoked.

- [ ] **Step 4: Run focused runner tests and observe GREEN**

### Task 4: Persist and resume multipart jobs

**Files:**
- Modify: `scriptor/session.py`
- Modify: `scriptor/runner.py`
- Test: `tests/test_session.py`
- Test: `tests/test_runner.py`

- [ ] **Step 1: Write failing round-trip and resume tests**

```python
def test_session_round_trip_preserves_story_plan_and_accepted_parts(): ...
async def test_resume_keeps_p1_to_p4_and_starts_from_p5_without_planner(): ...
```

- [ ] **Step 2: Run focused tests and observe RED**

- [ ] **Step 3: Persist optional fields and preserve them through rename/remove**

Legacy session records without these fields deserialize to a normal empty multipart state.

- [ ] **Step 4: Run focused tests and observe GREEN**

### Task 5: Integrate bridge and minimal snapshot progress

**Files:**
- Modify: `scriptor/bridge.py`
- Test: `tests/test_scenarios.py`

- [ ] **Step 1: Write failing bridge tests**

```python
def test_generate_scenarios_resumes_persisted_story_plan_without_overwrite(): ...
def test_snapshot_reports_completed_and_total_story_parts_without_exposing_part_prose(): ...
```

- [ ] **Step 2: Run focused tests and observe RED**

- [ ] **Step 3: Preserve existing incomplete multipart jobs when building the batch**

Pass resume jobs to the runner, retain ProductionItem identity and operator prompt, and expose only count/status metadata in snapshot.

- [ ] **Step 4: Run focused tests and observe GREEN**

### Task 6: Verify, review, and hand off

**Files:**
- Modify if necessary: `docs/verification/...` only for new permanent command evidence.

- [ ] **Step 1: Run targeted and relevant full checks**

Run: `python tests/run_isolated.py tests/test_story_planner.py tests/test_runner.py tests/test_scenarios.py tests/test_session.py -q`.

- [ ] **Step 2: Run Python lint and safety gates**

Run ruff for modified Python files, `python scripts/secret-scan.py`, production write guard via the isolated test runner, and `git diff --check`.

- [ ] **Step 3: Review every changed file and caller of continuation helpers**

Document whether `scenario_length_continuation_instruction`, `continuation_repeats_draft`, and `_repair_length_if_needed` remain reachable from normal scenario generation.

- [ ] **Step 4: Commit, push and open a PR without merge**

Use focused commits and include exact local test evidence in issue #260 and the PR. Wait for CI and Windows-native checks; report RUNNING/FAIL honestly.

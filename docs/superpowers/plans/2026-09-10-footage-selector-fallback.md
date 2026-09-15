# Footage Selector Fallback Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Guarantee a safe local footage selection whenever at least one hard-valid indexed candidate exists.

**Architecture:** Keep the existing bounded strict and fallback pools, but apply hard checks independently from quality preferences. Build deterministic soft-constraint passes over those pools and record unique rejection reasons separately from per-pass events.

**Tech Stack:** Python 3, unittest, existing NewsFlow footage index and montage bridge.

**Spec:** `docs/superpowers/specs/2026-09-10-footage-selector-fallback-design.md`

## Global Constraints

- Preserve semantic safety, fast mode, indexed bounded lookup, full intermediate footage, final-tail-only trim, MP3 mappings, and ready-video protection.
- Never reuse the immediately previous clip if any other hard-valid candidate is available.
- Never turn a soft-quality exhaustion into a montage failure.

---

### Task 1: Characterize the exhaustion regression

**Files:**
- Modify: `tests/test_montage_queue.py`

**Interfaces:**
- Consumes: `_select_montage_candidate(...) -> MontageCandidateSelection`
- Produces: regression coverage for diversity, adjacent reuse, single-clip fallback, and reservation exhaustion.

- [ ] **Step 1: Write failing tests**

```python
def test_selection_uses_non_adjacent_project_clip_when_quality_pool_is_exhausted(self):
    # A second-old clip is valid; no fresh family exists.
    self.assertEqual(result.fallback_level, "SAFE_REUSE")
    self.assertEqual(result.item.path, earlier.path)

def test_selection_uses_only_safe_clip_as_last_resort(self):
    self.assertEqual(result.fallback_level, "LAST_RESORT")
    self.assertEqual(result.item.path, only.path)
```

- [ ] **Step 2: Run the selector tests and verify the first test fails because SAFE_REUSE still rejects project history.**

Run: `python -m unittest tests.test_montage_queue.MontageQueueStateTests -v`

- [ ] **Step 3: Commit the regression test.**

### Task 2: Make quality constraints progressive

**Files:**
- Modify: `scriptor/bridge.py: _select_montage_candidate`
- Test: `tests/test_montage_queue.py`

**Interfaces:**
- Consumes: existing strict/fallback `SearchHit` pools, `used_*`, `project_used_*`, and reservation sets.
- Produces: `MontageCandidateSelection` with one of `STRICT_MATCH`, `RELAXED_MATCH`, `CATEGORY_CONTEXT_FALLBACK`, `SAFE_REUSE`, `RESERVED_REUSE`, or `LAST_RESORT`.

- [ ] **Step 1: Implement a hard-valid candidate evaluator that checks duration, semantic safety, existence and validated duration.**
- [ ] **Step 2: Implement deterministic progressive passes with a recent-path cooldown, allowing old project clips only after strict and category passes exhaust.**
- [ ] **Step 3: Make batch reservation a preference: use `RESERVED_REUSE` only after unreserved candidates exhaust.**
- [ ] **Step 4: Add a `LAST_RESORT` hard-valid selection that uses a stable score/path sort and only permits adjacent reuse when it is the sole valid candidate.**
- [ ] **Step 5: Run the regression test and verify it passes.**

### Task 3: Correct diagnostics and reservation lifecycle

**Files:**
- Modify: `scriptor/bridge.py: selector diagnostics, batch reservation cleanup, planner progress reporting`
- Test: `tests/test_montage_queue.py`

**Interfaces:**
- Produces: `hard_valid`, unique rejection counters, `rejection_events`, `fallback_level`, and reuse metadata.

- [ ] **Step 1: Write failing tests that distinguish unique candidate rejections from repeated fallback-pass events and that release reservations for failed jobs.**
- [ ] **Step 2: Implement first-reason-per-candidate diagnostics while preserving total rejection-event telemetry.**
- [ ] **Step 3: Release only reservations owned by a failed/cancelled/interrupted item; retain active-job reservations.**
- [ ] **Step 4: Run all montage queue tests.**

### Task 4: Verify real selector behavior and packaged build

**Files:**
- Modify: `tests/test_montage_queue.py` only if a hermetic real-item fixture is required.

- [ ] **Step 1: Run the real planning preflight for ProductionItem 14 without resetting its MP3 or completed timeline work.**
- [ ] **Step 2: Run a simultaneous batch preflight and collect fallback totals, adjacent duplicate count, failures, and selection time.**
- [ ] **Step 3: Run montage and smoke-test suites, then build the portable EXE using the established packaging command.**
- [ ] **Step 4: Repeat the ProductionItem 14 and batch preflight through the packaged `NewsFlowCore.exe`.**
- [ ] **Step 5: Report evidence, including any limitations if physical footage prevents a full render.**

# Publication Center and Smart Allocation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the overloaded publication page with a clear bulk-selection workspace and a reviewable allocation screen that sends the longest compatible videos to monetized channels first.

**Architecture:** Preserve the existing queue records and bridge commands. Make allocation a pure deterministic ranking function, render its proposed moves separately from the publication queue, and apply only user-confirmed assignments. Split React display components by responsibility while keeping `App.tsx` as the route owner.

**Tech Stack:** Python 3.12, unittest, React/TypeScript, existing CSS modules and Lucide buttons.

**Spec:** `docs/superpowers/specs/2026-09-01-youtube-posts-cards-end-screens-design.md`

## Global Constraints

- Preserve manual channel assignments and scheduled times until the user explicitly changes them.
- Consider only editable, unassigned jobs for automatic recommendations.
- Within compatible candidates, monetized channels receive longest videos first; ties use the existing queue order.
- Use text labels with colored button roles; color cannot be the only status signal.
- Do not alter OAuth tokens, uploads, or existing scheduled jobs.

---

### Task 1: Make the allocation algorithm duration-aware and stable

**Files:**
- Modify: `scriptor/youtube_allocation.py: allocate_ready_jobs`
- Modify: `tests/test_youtube_allocation.py`

**Interfaces:**
- `allocate_ready_jobs(profiles, jobs) -> {assignments, skipped, summary}` remains stable.
- `summary["channels"]` keeps `monetized`, duration limits, and assignment IDs.

- [ ] **Step 1: Write failing ordering tests**

```python
def test_monetized_channel_gets_longest_compatible_jobs_first():
    result = allocate_ready_jobs(
        [{"channelId": "money", "monetized": True}, {"channelId": "growth", "growthSignal": True}],
        [job("short", 120), job("long", 900), job("medium", 480)],
    )
    assert result["assignments"]["money"] == ["long", "medium"]

def test_same_duration_keeps_original_queue_order():
    result = allocate_ready_jobs([{"channelId": "money", "monetized": True}], [job("a", 300), job("b", 300)])
    assert result["assignments"]["money"] == ["a", "b"]
```

- [ ] **Step 2: Run to verify failure**

Run: `py -3 -m unittest tests.test_youtube_allocation -v`

Expected: FAIL because candidates retain input order.

- [ ] **Step 3: Sort only automatic candidates**

Create `rank_ready_jobs(jobs) -> list[Mapping[str, object]]` that stable-sorts measured durations descending, leaves missing durations in `skipped`, and use it only for monetized profiles before non-monetized profiles. Keep current quota and duration-range checks.

- [ ] **Step 4: Run allocation tests**

Run: `py -3 -m unittest tests.test_youtube_allocation tests.test_youtube_publisher -v`

Expected: PASS.

### Task 2: Add bulk queue commands and review payloads

**Files:**
- Modify: `scriptor/bridge.py: refresh_publication_allocation, assign_publication_jobs, move_publication_job_channel`
- Test: `tests/test_youtube_publisher.py`

**Interfaces:**
- Adds `preview-publication-bulk-assignment` command that returns recommendations without mutation.
- Adds `apply-publication-bulk-assignment` command accepting `{assignments: Record<string, string[]>}`.
- Existing `move-publication-job-channel` remains the single-item manual override.

- [ ] **Step 1: Write failing bridge tests**

```python
def test_preview_does_not_mutate_and_apply_changes_only_requested_unassigned_jobs():
    before = deepcopy(settings.youtube_publication_jobs)
    preview = bridge.preview_publication_bulk_assignment({"jobIds": ["long", "short"]})
    assert settings.youtube_publication_jobs == before
    bridge.apply_publication_bulk_assignment({"assignments": preview["assignments"]})
    assert assigned_channel("long") == "money"
    assert scheduled_job("fixed")["channelId"] == "fixed-channel"
```

- [ ] **Step 2: Run to verify failure**

Run: `py -3 -m unittest tests.test_youtube_publisher.PublicationBridgeTests.test_preview_does_not_mutate_and_apply_changes_only_requested_unassigned_jobs -v`

Expected: FAIL because the new commands do not exist.

- [ ] **Step 3: Validate and persist explicit bulk assignments**

Reject unknown job/channel IDs, already-uploaded jobs, and attempts to overwrite a manually assigned job unless `forceManualOverride` is true. Add bounded activity rows listing count and destination channels. Return a refreshed snapshot and a human-readable operation result.

- [ ] **Step 4: Run bridge tests**

Run: `py -3 -m unittest tests.test_youtube_publisher tests.test_youtube_allocation -v`

Expected: PASS.

### Task 3: Extract and simplify the publication workspace

**Files:**
- Create: `studio-ui-remotion-verify/src/ui/publication/PublicationQueue.tsx`
- Create: `studio-ui-remotion-verify/src/ui/publication/AllocationReview.tsx`
- Modify: `studio-ui-remotion-verify/src/ui/App.tsx: page union, sidebar navigation, PublicationDashboard`
- Modify: `studio-ui-remotion-verify/src/desktop.d.ts`
- Modify: `studio-ui-remotion-verify/src/ui/publication.css`
- Modify: `studio-ui-remotion-verify/src/ui/publication-allocation.css`

**Interfaces:**
- `PublicationQueue({jobs, channels, selectedJobIds, onSelectionChange, command})` renders bulk selection and direct actions.
- `AllocationReview({preview, onApply, onMove})` renders recommendation cards and manual drag/drop overrides.

- [ ] **Step 1: Add a failing UI scenario**

```tsx
render(<PublicationQueue jobs={[longJob, shortJob]} channels={channels} selectedJobIds={[]} onSelectionChange={setSelected} command={command} />)
await user.click(screen.getByLabelText("Выбрать Тема A"))
await user.click(screen.getByRole("button", {name: "Подобрать каналы"}))
expect(command).toHaveBeenCalledWith("preview-publication-bulk-assignment", {jobIds: ["long"]})
```

- [ ] **Step 2: Run to verify failure**

Run: `npm test -- --runInBand` from `studio-ui-remotion-verify`, or add the same flow to `tests/manual-ui-checks.md` if no frontend runner exists.

Expected: FAIL or missing behavior.

- [ ] **Step 3: Build the clear two-screen flow**

In `Публикация`, show a compact summary, selectable queue rows, primary buttons `Добавить готовые`, `Подобрать каналы`, `Назначить время`, `Загрузить выбранные`, and a details drawer. Add a separate `Умное распределение` sidebar route that shows proposed destinations before mutation, chips for duration and monetization, and draggable overrides. Keep complex grid presets in a collapsed `Расширенные настройки` section.

- [ ] **Step 4: Apply semantic visual roles and responsive layout**

Use blue for primary selection/assignment, green for upload success, amber for pending attention, red only for deletion. Provide icon and text for every colored control. At small widths turn channel columns into stacked destination cards.

- [ ] **Step 5: Verify UI and regressions**

Run: `py -3 -m unittest tests.test_youtube_allocation tests.test_youtube_publisher -v`

Expected: PASS. Run frontend checks/build and visually test one manual batch, one automatic recommendation, one drag override, and one upload-ready queue.

# Stable Montage Tail Completion and Repeat Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every recoverable footage-short timeline cover its audio with full intermediate clips and one final trim, and make selected/all force rerender create real, non-duplicate montage jobs.

**Architecture:** `scriptor/timeline.py` owns measured visual duration, tail completion and final ffprobe validation. `scriptor/bridge.py` owns queue selection, reset state, active-process safety and worker scheduling. `App.tsx` passes explicit selected indices or a force-all request and shows operation feedback; it never decides duration or queue state.

**Tech Stack:** Python 3, FFmpeg/ffprobe, PyInstaller core, Electron, React/TypeScript, unittest, pnpm.

**Spec:** `C:\Users\borov\.codex\attachments\3a6cad08-bfe2-4f5e-b636-fa96da0ba07f\pasted-text.txt`

## Global Constraints

- Do not modify Ideas Engine or Thumbnail pipeline.
- Measure every source duration through ffprobe; do not hard-code six seconds.
- Preserve source MP3, footage libraries, scenario and ProductionItem records.
- Keep current valid final MP4 until a forced replacement validates successfully.
- A ready item is skipped by ordinary resume; explicit force rerender is the only replacement path.
- Build and exercise the packaged Windows EXE before delivery.

---

### Task 1: Measured tail-completion planner

**Files:**
- Modify: `scriptor/timeline.py:111-150,391-710`
- Test: `scriptor/test_timeline.py`

**Interfaces:**
- Produces `effective_timeline_duration(project: TimelineProject) -> float` and `append_tail_footage(project, candidates, required_duration) -> list[TimelineClip]`.
- Consumes real clip paths and `probe_media_duration(Path)`.

- [ ] **Step 1: Write failing duration cases**

```python
def test_tail_completion_keeps_full_clips_and_trims_only_final_clip(tmp_path):
    project = project_with_clips([6.0] * 10)
    tail = append_tail_footage(project, candidates=[clip(tmp_path, 6.04)], required_duration=62.8)
    assert [round(item.duration, 1) for item in project.clips[-2:]] == [6.0, 2.8]

def test_tail_completion_uses_multiple_full_sources_before_final_trim(tmp_path):
    project = project_with_clips([6.0] * 10)
    append_tail_footage(project, candidates=[clip(tmp_path, 6.0), clip(tmp_path, 5.96), clip(tmp_path, 6.04)], required_duration=73.4)
    assert [round(item.duration, 1) for item in project.clips[-3:]] == [6.0, 5.96, 1.44]
```

- [ ] **Step 2: Run the two tests and confirm they fail because the helper is absent.**

Run: `python -m unittest scriptor.test_timeline.TailCompletionTests -v`

- [ ] **Step 3: Implement the helper.**

```python
remaining = required_duration - effective_timeline_duration(project)
while remaining > technical_tolerance:
    candidate = next_valid_candidate()
    duration = probe_media_duration(Path(candidate.path))
    contribution = min(duration, remaining)
    project.clips.append(replace(candidate, duration=contribution))
    remaining -= contribution
```

Use the full actual duration for every non-final candidate. Account for configured transition overlap in `effective_timeline_duration`; fail only after every valid fallback is exhausted.

- [ ] **Step 4: Run tail tests and existing timeline tests.**

Run: `python -m unittest scriptor.test_timeline -v`

### Task 2: Render validation and absence recovery

**Files:**
- Modify: `scriptor/timeline.py:640-710`
- Modify: `scriptor/bridge.py:7979-8300,8801-8925`
- Test: `scriptor/test_montage_render.py`, `tests/test_montage_queue.py`

**Interfaces:**
- Consumes a project created by Task 1.
- Produces `validate_montage_clip(path) -> float | None` and `repair_missing_project_clips(project, selector) -> list[int]`.
- Recovery preserves the same ProductionItem and audio attachment, replaces only invalid clip slots and saves the corrected project before rerendering.

- [ ] **Step 1: Write failing tests for a 1.1-second shortage, a 14.3-second shortage, and an absent planned source.**

```python
def test_render_shortage_requests_tail_completion_not_final_failure(...):
    with self.assertRaises(TailCompletionRequired): render_project(project_short_by(1.1), output)

def test_missing_planned_clip_replaces_only_the_invalid_slot(...):
    result = bridge.run_montage_queue({"indices": [12]})
    self.assertEqual(status(12), "Готово")
```

- [ ] **Step 2: Verify the tests fail against the old final `Таймлайн футажей короче` branch.**

Run: `python -m unittest scriptor.test_montage_render tests.test_montage_queue -v`

- [ ] **Step 3: Replace the final shortage failure with bounded tail completion and targeted missing-file recovery.**

Before FFmpeg, validate every source by existence, nonzero size, ffprobe duration and video stream. For each invalid slot, keep all valid clips and use the existing selector to replace only that slot with a distinct valid candidate. Exclude the broken path during the bounded recovery attempt, save the revised `.newsflow` project, then apply Task 1 tail completion and resume the same item. It must write user-visible events: unavailable footage, selecting replacement, replacement saved, final trim, render. It must never move the item to the incoming-MP3 list.

- [ ] **Step 4: Validate final audio/video drift and persistence via ffprobe before ready state.**

Run: `python -m unittest scriptor.test_montage_render tests.test_montage_queue -v`

### Task 3: Explicit force-rerender queue contract

**Files:**
- Modify: `scriptor/bridge.py:8460-8925,10460-10485`
- Test: `tests/test_montage_queue.py`

**Interfaces:**
- `run_montage_queue({"indices": list[int], "force": bool}) -> dict`
- `force=False` renders only incomplete/failed/interrupted items.
- `force=True` resets only requested current indices; an omitted indices list means all current valid production items.

- [ ] **Step 1: Write failing tests.**

```python
def test_force_rerender_selected_resets_only_requested_items(...):
    bridge.run_montage_queue({"indices": [1, 4, 8], "force": True})
    self.assertEqual(reset_indices(), {1, 4, 8})
    self.assertTrue(existing_output(0))

def test_force_rerender_all_uses_current_batch_not_saved_snapshot(...):
    bridge.run_montage_queue({"force": True})
    self.assertEqual(enqueued_indices(), current_audio_indices())
```

- [ ] **Step 2: Confirm tests fail before adding force behaviour.**

Run: `python -m unittest tests.test_montage_queue.MontageQueueForceRerenderTests -v`

- [ ] **Step 3: Implement one-item reset and scheduling.**

Clear only derived `.newsflow` plan and stale queue metadata. Keep source audio/library records and current output path until a validated temp replacement atomically replaces it. Ensure an active job receives cancellation intent, its FFmpeg PID is terminated and reaped, then exactly one new worker is enqueued.

- [ ] **Step 4: Run queue tests and assert one active worker per index.**

Run: `python -m unittest tests.test_montage_queue -v`

### Task 4: UI selection, repeat controls and feedback

**Files:**
- Modify: `studio-ui-remotion-verify/src/ui/App.tsx:MontageQueue component`
- Modify: `studio-ui-remotion-verify/src/desktop.d.ts`
- Test: `studio-ui-remotion-verify/scripts/verify-montage-ui.mjs`

**Interfaces:**
- Selected repeat sends `{indices: selected, force: true}`.
- Repeat-all sends `{force: true}` and no stale selected indices.
- Resume sends `{indices?, force: false}`.

- [ ] **Step 1: Extend UI contract assertions to require both repeat handlers and distinct `force` payloads; run it and observe failure.**

Run: `pnpm verify:montage-ui`

- [ ] **Step 2: Add separate visible actions:** selected `Повторить с начала` and all `Повторить с начала — все`.

Set feedback before dispatch: `Перезапускаем N ролика(ов)`; update from returned queue state and preserve selection only for selected mode.

- [ ] **Step 3: Wire the Electron command path to the force queue contract and type it.**

Run: `pnpm typecheck && pnpm verify:montage-ui`

### Task 5: Packaged EXE regression

**Files:**
- Modify: `scriptor/test_montage_render.py` only if a reusable packaged smoke fixture is required.
- Modify: `studio-ui-remotion-verify/scripts/verify-portable.mjs` only if it lacks runtime checks needed by this task.

- [ ] **Step 1: Build core and portable EXE from the tested source.**

Run the existing core packaging command followed by `pnpm package:preview -- --publish never` from `studio-ui-remotion-verify`.

- [ ] **Step 2: Run the packaged core with a disposable fixture.**

Assert 1.1, 2.8, 5.7, 6.0, 13.4 shortages; verify intermediate source durations are full, final tail is trimmed, final FFprobe drift is within tolerance.

- [ ] **Step 3: Run packaged selected/all repeat smoke tests.**

Assert selected IDs only, all current IDs in force-all, one active job per item, and a real FFmpeg child for queued render.

- [ ] **Step 4: Final verification.**

Run: backend regression suite; `pnpm typecheck`; `pnpm verify:montage-ui`; portable verifier. Report only actual remaining limitations.

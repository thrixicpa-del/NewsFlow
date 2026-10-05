# GPU Timeline Renderer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Add a selectable GPU-timeline renderer for long Montage videos and make the persisted Pause control stop an already-running queue at safe checkpoints.

**Architecture:** timeline.py owns strict NVENC capability and bounded timeline chunks. bridge.py saves the renderer and refreshes the pause signal from durable settings. React adds a manual mode beside current FFmpeg, Remotion, and DaVinci controls; footage selection, scene plans and voice maps remain unchanged.

**Tech Stack:** Python 3, FFmpeg/NVENC, Electron IPC, React/TypeScript, Vitest, unittest.

**Spec:** docs/superpowers/specs/2026-10-05-gpu-timeline-renderer-design.md

## Global Constraints

- Do not use providers, OAuth, production settings or user media in tests.
- GPU-timeline is explicit; never silently run CPU FFmpeg after GPU preflight/render failure.
- Existing ffmpeg/remotion settings and projects retain behavior.
- DaVinci XML remains an independent handoff.
- renderWorkers is the only operator-controlled renderer parallelism field.
- Do not alter planning, footage selection, source trims, voice timing, Covers or publication.

---

### Task 1: Repair durable queue pause observation

**Files:**
- Modify: tests/test_montage_queue.py:382-397, 1304-1318
- Modify: scriptor/bridge.py:16880-16944, 17575-17820
- Modify: studio-ui-remotion-verify/src/ui/App.tsx:10698-10704, 11365-11378
- Modify: studio-ui-remotion-verify/src/ui/features/montage/montage-view.test.tsx

**Interfaces:**
- Consumes: save_montage_settings({"queuePaused": bool}).
- Produces: _montage_wait_if_paused(settings, scenario_index), which preserves a task while observing newer persisted pause state.

- [ ] **Step 1: Write the failing Core regression**

~~~python
def test_pause_set_after_queue_start_blocks_the_next_safe_stage(self):
    worker_settings = Settings(montage_queue_paused=False)
    updates = []
    with patch.object(bridge, "load_settings",
                      side_effect=[Settings(montage_queue_paused=True), Settings()]), \
         patch.object(bridge, "_montage_task_update",
                      side_effect=lambda *_args, **kwargs: updates.append(kwargs)), \
         patch.object(bridge.time, "sleep"):
        bridge._montage_wait_if_paused(worker_settings, 4)
    self.assertEqual([item["status"] for item in updates], ["Пауза", "В очереди"])
~~~

- [ ] **Step 2: Run RED**

Run: python tests/run_isolated.py tests.test_montage_queue.MontageQueueTests.test_pause_set_after_queue_start_blocks_the_next_safe_stage

Expected: FAIL if a queue worker does not observe a pause saved after queue startup.

- [ ] **Step 3: Implement the minimum fix**

~~~python
def _montage_wait_if_paused(settings: Settings, scenario_index: int) -> None:
    paused = False
    while True:
        settings.montage_queue_paused = load_settings().montage_queue_paused
        if not settings.montage_queue_paused:
            break
        paused = True
        _montage_task_update(settings, scenario_index,
                             status="Пауза", phase="Ожидание продолжения")
        time.sleep(.45)
    if paused:
        _montage_task_update(settings, scenario_index,
                             status="В очереди", phase="Продолжаем")
~~~

Keep checkpoints at project/stage boundaries. Add a React test ensuring one click requests pause and a pending request cannot duplicate.

- [ ] **Step 4: Verify and commit**

Run:
python tests/run_isolated.py tests.test_montage_queue

pnpm --dir studio-ui-remotion-verify test:ui -- src/ui/features/montage/montage-view.test.tsx

Expected: PASS.

~~~bash
git add scriptor/bridge.py tests/test_montage_queue.py studio-ui-remotion-verify/src/ui/App.tsx studio-ui-remotion-verify/src/ui/features/montage/montage-view.test.tsx
git commit -m "fix: make montage pause observe durable state"
~~~

### Task 2: Add strict GPU renderer contract

**Files:**
- Modify: scriptor/timeline.py:363-435, 741-758
- Modify: scriptor/config.py where Settings.montage_renderer is declared and loaded
- Modify: scriptor/bridge.py:2819-2840, 14716-14725, 17758-17766
- Modify: studio-ui-remotion-verify/src/desktop.d.ts:70
- Test: scriptor/test_montage_render.py
- Test: tests/test_montage_queue.py

**Interfaces:**
- Produces: gpu_timeline_capability(ffmpeg: str | None = None) -> dict[str, object].
- Produces: render_project(..., renderer="gpu-timeline", ...).
- Persists: Settings.montage_renderer in {"ffmpeg", "gpu-timeline", "remotion"}.

- [ ] **Step 1: Write failing contract tests**

~~~python
def test_gpu_timeline_rejects_missing_nvenc_without_cpu_fallback(self):
    project = TimelineProject("GPU", clips=[TimelineClip("clip.mp4", "n", "q", 1)])
    with patch.object(timeline_module, "gpu_timeline_capability",
                      return_value={"available": False, "reason": "NVENC недоступен"}):
        with self.assertRaisesRegex(RuntimeError, "NVENC недоступен"):
            render_project(project, Path("result.mp4"), renderer="gpu-timeline")

def test_save_montage_settings_round_trips_gpu_timeline(self):
    settings = Settings()
    with patch.object(bridge, "load_settings", return_value=settings), \
         patch.object(bridge, "save_settings"), \
         patch.object(bridge, "snapshot", return_value={}):
        bridge.save_montage_settings({"renderer": "gpu-timeline"})
    self.assertEqual(settings.montage_renderer, "gpu-timeline")
~~~

- [ ] **Step 2: Run RED**

Run: python tests/run_isolated.py scriptor.test_montage_render.MontageRenderTests.test_gpu_timeline_rejects_missing_nvenc_without_cpu_fallback tests.test_montage_queue.MontageQueueTests.test_save_montage_settings_round_trips_gpu_timeline

Expected: FAIL because gpu-timeline does not yet exist.

- [ ] **Step 3: Implement strict capability**

~~~python
def gpu_timeline_capability(ffmpeg: str | None = None) -> dict[str, object]:
    binary = ffmpeg or ffmpeg_executable()
    encoders = _ffmpeg_encoders(binary)
    available = "h264_nvenc" in encoders
    return {"available": available, "encoder": "h264_nvenc",
            "reason": "" if available else "NVENC недоступен"}
~~~

Extend settings validation, snapshot typing and UI-facing state. GPU uses a strict NVENC argument builder; legacy video_encoder_args() retains its CPU-fallback behavior.

- [ ] **Step 4: Verify and commit**

Run: python tests/run_isolated.py scriptor.test_montage_render tests.test_montage_queue

Expected: PASS.

~~~bash
git add scriptor/timeline.py scriptor/config.py scriptor/bridge.py studio-ui-remotion-verify/src/desktop.d.ts tests/test_montage_queue.py scriptor/test_montage_render.py
git commit -m "feat: add strict GPU montage renderer contract"
~~~

### Task 3: Build bounded GPU timeline rendering

**Files:**
- Modify: scriptor/timeline.py:741-930
- Test: scriptor/test_montage_render.py

**Interfaces:**
- Produces: _render_project_gpu_timeline(project, output, progress, heartbeat) -> Path.
- Produces: bounded GPU chunks with identical TimelineClip path, source_start, duration, order, target size and FPS to the legacy route.

- [ ] **Step 1: Write failing media tests**

~~~python
def test_gpu_timeline_writes_1080p_30fps_and_preserves_duration(self):
    project = self.project_from_generated_clips()
    output = self.root / "gpu.mp4"
    render_project(project, output, renderer="gpu-timeline")
    self.assert_media_contract(output, width=1920, height=1080, fps=30,
                               minimum_duration=project_duration(project))

def test_gpu_timeline_keeps_source_order_and_uses_bounded_chunks(self):
    project = self.project_with_many_generated_clips(13)
    with patch.object(timeline_module, "_run") as run:
        render_project(project, self.root / "gpu.mp4", renderer="gpu-timeline")
    self.assertLessEqual(max_input_count_per_command(run.call_args_list),
                         timeline_module.GPU_TIMELINE_CHUNK_SIZE)
~~~

Fixtures are disposable. Full GPU media execution uses NVENC when available; otherwise test command construction and explicit SKIP reason.

- [ ] **Step 2: Run RED**

Run: python tests/run_isolated.py scriptor.test_montage_render

Expected: FAIL because the GPU renderer is absent.

- [ ] **Step 3: Implement bounded chunks**

~~~python
GPU_TIMELINE_CHUNK_SIZE = 12

def _render_project_gpu_timeline(project, output, progress, heartbeat):
    capability = gpu_timeline_capability()
    if not capability["available"]:
        raise RuntimeError(str(capability["reason"]))
    # Build ordered trim/scale/crop/fps filter graphs in bounded chunks,
    # encode chunks with h264_nvenc, concat copy them, then mux voice.
~~~

Use partial output plus _replace_with_retry, retain duration validation and heartbeat/progress, and do not write legacy per-clip proxies.

- [ ] **Step 4: Verify and commit**

Run: python tests/run_isolated.py scriptor.test_montage_render tests.test_timeline scriptor.test_davinci

Expected: PASS; unavailable NVENC is explicit SKIP, not PASS.

~~~bash
git add scriptor/timeline.py scriptor/test_montage_render.py
git commit -m "feat: render montage through bounded GPU timeline"
~~~

### Task 4: Expose the manual Montage mode

**Files:**
- Modify: studio-ui-remotion-verify/src/ui/App.tsx:340-371, 10472-10555, 10610-10650, 10806-10908, 10984-11055
- Modify: studio-ui-remotion-verify/src/desktop.d.ts:70
- Modify: studio-ui-remotion-verify/src/ui/features/montage/montage-view.test.tsx
- Modify: renderer CSS only if a fourth card cannot fit responsively

**Interfaces:**
- Consumes: montageSettings.renderer: "ffmpeg" | "gpu-timeline" | "remotion".
- Produces: save payload { renderer: "gpu-timeline", renderWorkers: N }.

- [ ] **Step 1: Write failing UI regression**

~~~tsx
it("selects GPU timeline and retains the operator render worker count", async () => {
  render(<Editor data={fallback} command={command} refresh={refresh} />);
  fireEvent.click(screen.getByRole("button", { name: /Быстрый GPU-таймлайн/ }));
  fireEvent.click(screen.getByRole("button", { name: "Сохранить настройки" }));
  await waitFor(() => expect(command).toHaveBeenCalledWith(
    "save-montage-settings",
    expect.objectContaining({ renderer: "gpu-timeline", renderWorkers: 4 }),
  ));
});
~~~

Also assert existing FFmpeg and Remotion controls remain.

- [ ] **Step 2: Run RED**

Run: pnpm --dir studio-ui-remotion-verify test:ui -- src/ui/features/montage/montage-view.test.tsx

Expected: FAIL because the GPU choice is absent.

- [ ] **Step 3: Add the fourth card and selector option**

Add a card labelled “Быстрый GPU-таймлайн” beside FFmpeg, Remotion and DaVinci. State 1080p/30fps and that it uses the existing “Видео одновременно” setting. A missing GPU produces a specific launch error; it never changes the selected renderer.

- [ ] **Step 4: Verify and commit**

Run:
pnpm --dir studio-ui-remotion-verify test:ui -- src/ui/features/montage/montage-view.test.tsx

pnpm --dir studio-ui-remotion-verify typecheck

Expected: PASS.

~~~bash
git add studio-ui-remotion-verify/src/ui/App.tsx studio-ui-remotion-verify/src/desktop.d.ts studio-ui-remotion-verify/src/ui/features/montage/montage-view.test.tsx studio-ui-remotion-verify/src/ui/*.css
git commit -m "feat: expose GPU timeline montage mode"
~~~

### Task 5: Verification and PR evidence

**Files:**
- Modify: docs/superpowers/plans/2026-10-05-gpu-timeline-renderer.md to mark completed work
- Modify: the design spec only if implementation disproves a design assertion

- [ ] **Step 1: Run focused gates**

Run:
python tests/run_isolated.py tests.test_montage_queue scriptor.test_montage_render tests.test_timeline scriptor.test_davinci

pnpm --dir studio-ui-remotion-verify test:ui -- src/ui/features/montage/montage-view.test.tsx

pnpm --dir studio-ui-remotion-verify typecheck

pnpm --dir studio-ui-remotion-verify verify:security

pnpm --dir studio-ui-remotion-verify verify:secrets

git diff --check

- [ ] **Step 2: Run a disposable local smoke**

Use generated clips only. Prove legacy output remains 1080p/30fps and GPU command construction is strict. If NVENC executes, create one disposable GPU output and record duration/FPS/encoder. Otherwise record the exact SKIP reason.

- [ ] **Step 3: Review scope and push**

Verify no change touches selection/planning, credentials, provider calls, production state or user media. Push a non-merged PR linked to #341 with exact results and truthful stale Frozen Core/TEST EXE status.

## Self-review

- Spec coverage: Task 1 covers pause; Tasks 2–3 cover strict capability, no fallback, chunk rendering and output fidelity; Task 4 covers UI/manual workers; Task 5 covers gates/evidence.
- Placeholder scan: no TODO/TBD or implicit implementation steps remain.
- Type consistency: gpu-timeline, gpu_timeline_capability and render_project are used consistently.


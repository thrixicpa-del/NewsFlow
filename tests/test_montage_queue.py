import hashlib
import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import numpy as np

from scriptor import bridge, config
from scriptor.ai_index import SCREEN_TEXT_CLASSIFIER_VERSION, ClipIndex, SearchHit
from scriptor.config import OpenAIKey, Settings
from scriptor.core import ScenarioRequest
from scriptor.footage import FootageItem
from scriptor.runner import Job, RunState
from scriptor.timeline import TimelineClip, TimelineProject
from tests.media_fixtures import write_readable_video


class MontageQueueStateTests(unittest.TestCase):
    def _queue_settings(self, root: Path, titles: list[str]) -> tuple[Settings, list[Job]]:
        voices = root / "voices"
        voices.mkdir()
        output = root / "output"
        projects = root / "projects"
        settings = Settings(
            montage_output_folder=str(output),
            montage_project_folder=str(projects),
            montage_renderer="ffmpeg",
            montage_planning_workers=3,
            montage_render_workers=2,
            montage_export_davinci_xml=False,
        )
        jobs = []
        for index, title in enumerate(titles):
            voice = voices / f"{index + 1}.mp3"
            voice.write_bytes(f"voice-{index}".encode())
            settings.voice_scenario_outputs[str(index + 1)] = str(voice)
            jobs.append(Job(ScenarioRequest(index, title, ""), RunState.DONE, f"Narration {index}", ""))
        return settings, jobs

    def _queue_runtime_patches(self, root: Path, settings: Settings, titles: list[str], jobs: list[Job],
                               *, render_side_effect=None, force_needs_render: bool | None = True,
                               plan_probe=None, render_probe=None, render_options=None,
                               emit_plan_progress: bool = False):
        plan_calls: list[int] = []
        render_calls: list[str] = []

        def prepare(payload):
            index = int(payload["scenarioIndex"])
            plan_calls.append(index)
            if plan_probe:
                plan_probe("enter")
            try:
                if emit_plan_progress:
                    progress = payload.get("_progress")
                    if callable(progress):
                        progress("Подбор футажей", "Сцена 1/2: synthetic.mp4")
                project_path = Path(settings.montage_project_folder) / f"{index}.newsflow"
                TimelineProject(
                    title=titles[index],
                    voiceover_path=settings.voice_scenario_outputs[str(index + 1)],
                ).save(project_path)
                return {"preparedProject": {"path": str(project_path), "clips": 1, "duration": 6.0}}
            finally:
                if plan_probe:
                    plan_probe("exit")

        def render(project, output, **_kwargs):
            render_calls.append(project.title)
            if render_options is not None:
                render_options.append(_kwargs)
            if render_probe:
                render_probe("enter")
            try:
                if render_side_effect is not None:
                    raise render_side_effect
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_bytes(b"\x00\x00\x00\x18ftypisom" + b"x" * 2048)
                return output
            finally:
                if render_probe:
                    render_probe("exit")

        patches = [
            patch.object(bridge, "load_settings", return_value=settings),
            patch.object(bridge, "load_session", return_value=(titles, jobs)),
            patch.object(bridge, "save_settings"),
            patch.object(bridge, "snapshot", return_value={}),
            patch.object(bridge, "app_data_root", return_value=root),
            patch.object(bridge, "prepare_montage", side_effect=prepare),
            patch.object(bridge, "render_project", side_effect=render),
            patch.object(bridge, "_montage_project_missing_clips", return_value=[]),
            patch.object(bridge, "_complete_project_visual_tail", return_value=0),
            patch.object(bridge, "probe_media_duration", return_value=6.0),
            patch.object(bridge, "required_video_duration", return_value=6.0),
            patch.object(bridge, "validate_rendered_montage"),
            patch.object(bridge, "remotion_payload", return_value={}),
            patch.object(bridge.ClipIndex, "count", return_value=0),
        ]
        if force_needs_render is not None:
            patches.append(patch.object(bridge, "_montage_task_needs_render", return_value=force_needs_render))
        return patches, plan_calls, render_calls

    def test_queue_project_references_final_published_mp4(self):
        from contextlib import ExitStack
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            settings, jobs = self._queue_settings(root, ['Queued'])
            patches, _plans, _renders = self._queue_runtime_patches(root, settings, ['Queued'], jobs)
            with ExitStack() as stack:
                for context in patches:
                    stack.enter_context(context)
                bridge.run_montage_queue({'indices': [0]})
            project = TimelineProject.load(Path(settings.montage_project_folder) / '0.newsflow')
            output = Path(settings.montage_output_folder) / 'Queued.mp4'
            self.assertTrue(output.is_file())
            self.assertEqual(project.output_path, str(output))

    def test_overlapping_queue_starts_have_one_owner_and_one_render(self):
        """Keep the owner before status persistence until the contender returns."""
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            settings, jobs = self._queue_settings(root, ["Only row"])
            patches, plan_calls, render_calls = self._queue_runtime_patches(
                root, settings, ["Only row"], jobs,
            )
            owner_entered = threading.Event()
            release_owner = threading.Event()

            def overlapping_session():
                owner_entered.set()
                if not release_owner.wait(10):
                    raise RuntimeError("queue owner was not released by the test")
                return ["Only row"], jobs

            results = []
            errors = []

            def launch():
                try:
                    results.append(bridge.run_montage_queue({"indices": [0]}))
                except ValueError as exc:
                    errors.append(str(exc))

            threads = [threading.Thread(target=launch) for _ in range(2)]
            for context in patches:
                context.start()
            try:
                with patch.object(bridge, "load_session", side_effect=overlapping_session):
                    try:
                        threads[0].start()
                        self.assertTrue(owner_entered.wait(5), "queue owner did not enter load_session")
                        threads[1].start()
                        threads[1].join(5)
                        self.assertFalse(threads[1].is_alive(), "overlapping start was not rejected")
                    finally:
                        release_owner.set()
                        for thread in threads:
                            if thread.ident is not None:
                                thread.join(5)
                    for thread in threads:
                        self.assertFalse(thread.is_alive(), "queue thread did not finish")
            finally:
                for context in reversed(patches):
                    context.stop()

        self.assertEqual(errors, [])
        self.assertEqual(plan_calls, [0])
        self.assertEqual(render_calls, ["Only row"])
        self.assertEqual(sorted(result["operationResult"]["count"] for result in results), [0, 1])

    def test_ready_27797_clip_index_does_not_rescan_footage_folders_during_planning(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            settings, jobs = self._queue_settings(root, ["Indexed row"])

            class ReadyIndex:
                def __init__(self, *_args, screen_text_progress=None, **_kwargs):
                    self.screen_text_progress = screen_text_progress

                def screen_text_stats(self):
                    return {"safe": 27000, "blocked": 100, "unchecked": 697}

                def count(self, embedded_only=False):
                    return 27_797

            with patch.object(bridge, "load_settings", return_value=settings), \
                 patch.object(bridge, "load_session", return_value=(["Indexed row"], jobs)), \
                 patch.object(bridge, "ClipIndex", ReadyIndex), \
                 patch.object(bridge, "scan_folders",
                              side_effect=AssertionError("ready index must not rescan folders")), \
                 patch.object(bridge, "probe_media_duration", return_value=6.0), \
                 patch.object(bridge, "fallback_scene_plan",
                              side_effect=RuntimeError("stop after ready-index gate")), \
                 self.assertRaisesRegex(RuntimeError, "stop after ready-index gate"):
                bridge.prepare_montage({"scenarioIndex": 0})

    def test_queue_render_passes_custom_gpu_block_size_without_changing_workers(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            settings, jobs = self._queue_settings(root, ["Custom GPU block"])
            settings.montage_renderer = "gpu-timeline"
            settings.montage_gpu_chunk_size = 24
            options = []
            patches, plan_calls, render_calls = self._queue_runtime_patches(
                root, settings, ["Custom GPU block"], jobs, render_options=options,
            )
            for context in patches:
                self.enterContext(context)
            bridge.run_montage_queue({"indices": [0]})
            self.assertEqual(plan_calls, [0])
            self.assertEqual(render_calls, ["Custom GPU block"])
            self.assertEqual(options[0].get("gpu_chunk_size"), 24)
            self.assertEqual(options[0]["renderer"], "gpu-timeline")
            self.assertEqual(settings.montage_render_workers, 2)

    def test_empty_selected_scope_is_not_implicit_missing_only(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            settings, jobs = self._queue_settings(root, ["Only row"])
            with patch.object(bridge, "load_settings", return_value=settings), \
                 patch.object(bridge, "load_session", return_value=(["Only row"], jobs)), \
                 patch.object(bridge, "save_settings"), \
                 patch.object(bridge, "snapshot", return_value={}), \
                 patch.object(bridge, "app_data_root", return_value=root), \
                 patch.object(bridge, "prepare_montage") as prepare, \
                 self.assertRaisesRegex(ValueError, "Выберите|явный"):
                bridge.run_montage_queue({"indices": []})
        prepare.assert_not_called()

    def test_stale_job_title_cannot_pair_another_scenario_with_current_mp3(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            settings, _jobs = self._queue_settings(root, ["Current title"])
            stale_job = Job(ScenarioRequest(0, "Old title", ""), RunState.DONE, "Old narration", "")
            with patch.object(bridge, "load_settings", return_value=settings), \
                 patch.object(bridge, "load_session", return_value=(["Current title"], [stale_job])), \
                 patch.object(bridge, "save_settings"), \
                 patch.object(bridge, "snapshot", return_value={}), \
                 patch.object(bridge, "app_data_root", return_value=root), \
                 patch.object(bridge, "prepare_montage") as prepare, \
                 self.assertRaisesRegex(ValueError, "пары"):
                bridge.run_montage_queue({"indices": [0]})
        prepare.assert_not_called()
        self.assertEqual(settings.montage_task_statuses["0"]["status"], "Ошибка")
        self.assertIn("текущ", settings.montage_task_statuses["0"]["error"].casefold())

    def test_failed_explicit_retry_keeps_previous_valid_mp4_current(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            settings, jobs = self._queue_settings(root, ["Only row"])
            previous = Path(settings.montage_output_folder) / "Only row.mp4"
            previous.parent.mkdir()
            original = b"\x00\x00\x00\x18ftypisom" + b"previous" * 300
            previous.write_bytes(original)
            settings.montage_task_statuses = {
                "0": {"title": "Only row", "status": "Готово", "outputPath": str(previous)},
            }
            patches, _plan_calls, _render_calls = self._queue_runtime_patches(
                root, settings, ["Only row"], jobs, render_side_effect=RuntimeError("permanent render failure"),
            )
            for context in patches:
                context.start()
            try:
                result = bridge.run_montage_queue({"indices": [0], "replaceOutput": True})
            finally:
                for context in reversed(patches):
                    context.stop()
            preserved = previous.read_bytes()

        self.assertEqual(result["operationResult"]["count"], 0)
        self.assertEqual(settings.montage_task_statuses["0"]["status"], "Ошибка")
        self.assertEqual(settings.montage_task_statuses["0"]["outputPath"], str(previous))
        self.assertEqual(preserved, original)

    def test_stale_owner_is_reclaimed_and_lock_releases_after_failure(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            lock_path = root / "montage-queue.lock"
            lock_path.write_text('{"pid": 999999, "startedAt": "old"}', encoding="utf-8")
            with patch.object(bridge, "app_data_root", return_value=root), \
                 patch.object(bridge, "_montage_process_is_running", return_value=False), \
                 patch.object(bridge, "_run_montage_queue_unlocked", side_effect=RuntimeError("boom")), \
                 self.assertRaisesRegex(RuntimeError, "boom"):
                bridge.run_montage_queue({"indices": [0]})
            self.assertFalse(lock_path.exists())

    def test_queue_owner_running_uses_the_live_pid_lock_without_mutating_it(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            with patch.object(bridge, "app_data_root", return_value=root):
                lock_path = bridge._montage_queue_lock_path()
                lock_path.write_text(
                    f'{{"pid": {os.getpid()}, "startedAt": "now"}}',
                    encoding="utf-8",
                )
                before = lock_path.read_text(encoding="utf-8")
                self.assertTrue(bridge._montage_queue_owner_running())
                self.assertEqual(lock_path.read_text(encoding="utf-8"), before)

                lock_path.write_text('{"pid": 999999, "startedAt": "old"}', encoding="utf-8")
                with patch.object(bridge, "_montage_process_is_running", return_value=False):
                    self.assertFalse(bridge._montage_queue_owner_running())

    def test_new_queue_owner_clears_an_orphaned_pause_before_work(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            settings, jobs = self._queue_settings(root, ["Only row"])
            settings.montage_queue_paused = True
            with patch.object(bridge, "app_data_root", return_value=root):
                bridge._montage_queue_lock_path().write_text(
                    '{"pid": 999999, "startedAt": "old"}', encoding="utf-8",
                )
            patches, plan_calls, render_calls = self._queue_runtime_patches(
                root, settings, ["Only row"], jobs,
            )
            patches.append(patch.object(bridge, "_montage_process_is_running", return_value=False))
            for context in patches:
                context.start()
            try:
                result = bridge.run_montage_queue({"indices": [0]})
            finally:
                for context in reversed(patches):
                    context.stop()

        self.assertFalse(settings.montage_queue_paused)
        self.assertEqual(result["operationResult"]["count"], 1)
        self.assertEqual(plan_calls, [0])
        self.assertEqual(render_calls, ["Only row"])

    def test_fresh_queue_owner_does_not_clear_a_new_operator_pause(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            settings, _jobs = self._queue_settings(root, ["Only row"])
            with patch.object(bridge, "app_data_root", return_value=root):
                lock_path = bridge._claim_montage_queue_lock()
                self.assertIsNotNone(lock_path)
                owner = json.loads(lock_path.read_text(encoding="utf-8"))
                self.assertFalse(owner["reclaimed"])
                settings.montage_queue_paused = True
                try:
                    with patch.object(bridge, "load_settings", return_value=settings), \
                         patch.object(bridge, "_reconcile_montage_outputs"), \
                         patch.object(bridge, "_recover_interrupted_montage_tasks", return_value=False), \
                         patch.object(bridge, "montage_queue_is_active", return_value=False), \
                         patch.object(bridge, "save_settings") as save, \
                         patch.object(bridge, "load_session", side_effect=RuntimeError("stop after pause check")), \
                         self.assertRaisesRegex(RuntimeError, "stop after pause check"):
                        bridge._run_montage_queue_unlocked({"indices": [0]})
                finally:
                    bridge._release_montage_queue_lock(lock_path)

        self.assertTrue(settings.montage_queue_paused)
        save.assert_not_called()

    def test_render_heartbeat_waits_for_pause_only_after_ffmpeg_subprocess_finishes(self):
        settings = Settings()
        with patch.object(bridge, "_montage_task_update") as update, \
             patch.object(bridge, "_montage_wait_if_paused") as wait_for_pause:
            bridge._montage_render_process_heartbeat(settings, 4, 12345)
            wait_for_pause.assert_not_called()

            bridge._montage_render_process_heartbeat(settings, 4, None)
            wait_for_pause.assert_called_once_with(settings, 4)

        self.assertEqual(update.call_count, 2)
        self.assertEqual(update.call_args_list[0].kwargs["ffmpegPid"], 12345)
        self.assertEqual(update.call_args_list[1].kwargs["ffmpegPid"], 0)

    def test_planning_progress_checks_pause_between_scene_updates(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            settings, jobs = self._queue_settings(root, ["Only row"])
            events = []
            patches, plan_calls, render_calls = self._queue_runtime_patches(
                root, settings, ["Only row"], jobs,
                plan_probe=lambda stage: events.append(stage),
                emit_plan_progress=True,
            )
            for context in patches:
                context.start()
            try:
                with patch.object(
                    bridge, "_montage_wait_if_paused",
                    side_effect=lambda *_args: events.append("checkpoint"),
                ):
                    result = bridge.run_montage_queue({"indices": [0]})
            finally:
                for context in reversed(patches):
                    context.stop()

        enter = events.index("enter")
        exit_at = events.index("exit")
        self.assertIn("checkpoint", events[enter + 1:exit_at])
        self.assertEqual(result["operationResult"]["count"], 1)
        self.assertEqual(plan_calls, [0])
        self.assertEqual(render_calls, ["Only row"])

    def test_paused_queue_owner_rejects_a_second_start_before_planning(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            with patch.object(bridge, "app_data_root", return_value=root):
                owner = bridge._claim_montage_queue_lock()
                self.assertIsNotNone(owner)
                try:
                    with patch.object(bridge, "_run_montage_queue_unlocked") as run:
                        result = bridge.run_montage_queue({"indices": [0]})
                finally:
                    bridge._release_montage_queue_lock(owner)
        run.assert_not_called()
        self.assertEqual(result["operationResult"]["count"], 0)

    def test_exact_selected_scope_renders_only_requested_rows(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            titles = ["Zero", "One", "Two"]
            settings, jobs = self._queue_settings(root, titles)
            patches, plan_calls, render_calls = self._queue_runtime_patches(root, settings, titles, jobs)
            for context in patches:
                context.start()
            try:
                result = bridge.run_montage_queue({"indices": [2, 0, 2]})
            finally:
                for context in reversed(patches):
                    context.stop()
        self.assertEqual(result["operationResult"]["count"], 2)
        self.assertEqual(sorted(plan_calls), [0, 2])
        self.assertEqual(sorted(render_calls), ["Two", "Zero"])

    def test_explicit_missing_only_keeps_ready_output_and_renders_new_row(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            titles = ["Ready", "New"]
            settings, jobs = self._queue_settings(root, titles)
            ready = Path(settings.montage_output_folder) / "Ready.mp4"
            ready.parent.mkdir()
            ready_bytes = b"\x00\x00\x00\x18ftypisom" + b"ready" * 400
            ready.write_bytes(ready_bytes)
            settings.montage_task_statuses = {
                "0": {"title": "Ready", "status": "Готово", "outputPath": str(ready)},
                "1": {"title": "New", "status": "Готов к монтажу", "outputPath": ""},
            }
            patches, plan_calls, render_calls = self._queue_runtime_patches(
                root, settings, titles, jobs, force_needs_render=None,
            )
            for context in patches:
                context.start()
            try:
                result = bridge.run_montage_queue({"missingOnly": True})
                preserved = ready.read_bytes()
            finally:
                for context in reversed(patches):
                    context.stop()
        self.assertEqual(result["operationResult"]["count"], 1)
        self.assertEqual(plan_calls, [1])
        self.assertEqual(render_calls, ["New"])
        self.assertEqual(preserved, ready_bytes)

    def test_configured_worker_limits_render_each_row_once(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            titles = [f"Row {index}" for index in range(10)]
            settings, jobs = self._queue_settings(root, titles)
            counters = {"plan": 0, "plan_max": 0, "render": 0, "render_max": 0}
            counter_lock = threading.Lock()
            plan_gate = threading.Event()
            render_gate = threading.Event()

            def probe(kind, limit, gate):
                def update(stage):
                    with counter_lock:
                        if stage == "enter":
                            counters[kind] += 1
                            counters[f"{kind}_max"] = max(counters[f"{kind}_max"], counters[kind])
                            if counters[kind] == limit:
                                gate.set()
                        else:
                            counters[kind] -= 1
                    if stage == "enter":
                        gate.wait(.5)
                return update

            patches, plan_calls, render_calls = self._queue_runtime_patches(
                root, settings, titles, jobs,
                plan_probe=probe("plan", 3, plan_gate),
                render_probe=probe("render", 2, render_gate),
            )
            for context in patches:
                context.start()
            try:
                result = bridge.run_montage_queue({"indices": list(range(10))})
            finally:
                for context in reversed(patches):
                    context.stop()

        self.assertEqual(result["operationResult"]["count"], 10)
        self.assertEqual(counters["plan_max"], 3)
        self.assertEqual(counters["render_max"], 2)
        self.assertEqual(sorted(plan_calls), list(range(10)))
        self.assertEqual(sorted(render_calls), sorted(titles))
        self.assertEqual(len(plan_calls), len(set(plan_calls)))
        self.assertEqual(len(render_calls), len(set(render_calls)))

    def test_empty_selected_cleanup_is_not_all_and_outside_project_fails_closed(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            output = root / "output"
            projects = root / "projects"
            output.mkdir(); projects.mkdir()
            generated = output / "keep.mp4"
            generated.write_bytes(b"keep")
            outside_project = root / "outside.newsflow"
            outside_project.write_text("{}", encoding="utf-8")
            settings = Settings(montage_output_folder=str(output), montage_project_folder=str(projects))
            settings.montage_task_statuses = {
                "0": {"title": "keep", "status": "Готово", "outputPath": str(generated)},
            }
            with patch.object(bridge, "load_settings", return_value=settings), \
                 patch.object(bridge, "save_settings"), \
                 patch.object(bridge, "snapshot", return_value={}):
                removed = bridge.remove_montage_results({"indices": []})
                rejected = bridge.remove_montage_projects({"paths": [str(outside_project)]})
                generated_kept = generated.is_file()
        self.assertEqual(removed["operationResult"]["count"], 0)
        self.assertEqual(rejected["operationResult"]["count"], 0)
        self.assertTrue(generated_kept)
        self.assertIn("Можно удалить только", rejected["operationResult"]["message"])

    def test_dead_running_row_recovers_then_deliberate_resume_renders_once(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            titles = ["Interrupted", "Ready"]
            settings, jobs = self._queue_settings(root, titles)
            ready = Path(settings.montage_output_folder) / "Ready.mp4"
            ready.parent.mkdir()
            ready_bytes = b"\x00\x00\x00\x18ftypisom" + b"ready" * 400
            ready.write_bytes(ready_bytes)
            settings.montage_task_statuses = {
                "0": {"title": "Interrupted", "status": "Рендер", "queuePid": 999999, "outputPath": ""},
                "1": {"title": "Ready", "status": "Готово", "outputPath": str(ready)},
            }
            with patch.object(bridge, "_montage_process_is_running", return_value=False):
                self.assertTrue(bridge._recover_interrupted_montage_tasks(settings))
            self.assertEqual(settings.montage_task_statuses["0"]["status"], "Ошибка")
            self.assertEqual(settings.montage_task_statuses["1"]["status"], "Готово")

            patches, plan_calls, render_calls = self._queue_runtime_patches(root, settings, titles, jobs)
            for context in patches:
                context.start()
            try:
                result = bridge.run_montage_queue({"indices": [0]})
                preserved = ready.read_bytes()
            finally:
                for context in reversed(patches):
                    context.stop()

        self.assertEqual(result["operationResult"]["count"], 1)
        self.assertEqual(plan_calls, [0])
        self.assertEqual(render_calls, ["Interrupted"])
        self.assertEqual(preserved, ready_bytes)

    def test_pause_waits_at_safe_stage_and_no_active_pause_persists(self):
        paused = Settings(montage_queue_paused=True)
        resumed = Settings(montage_queue_paused=False)
        updates = []
        with patch.object(bridge, "load_settings", side_effect=[paused, paused, resumed]), \
             patch.object(bridge, "_montage_task_update", side_effect=lambda *_args, **kwargs: updates.append(kwargs)), \
             patch.object(bridge.time, "sleep"):
            bridge._montage_wait_if_paused(Settings(), 4)
        self.assertEqual([item["status"] for item in updates], ["Пауза", "Пауза", "В очереди"])

        idle = Settings()
        with patch.object(bridge, "load_settings", return_value=idle), \
             patch.object(bridge, "save_settings"), \
             patch.object(bridge, "snapshot", return_value={}):
            bridge.save_montage_settings({"queuePaused": True})
        self.assertTrue(idle.montage_queue_paused)

    def test_unmarked_legacy_remotion_default_migrates_to_fast_news_ffmpeg(self):
        """An old implicit renderer default must not keep a new queue on the slow route."""
        with tempfile.TemporaryDirectory() as folder:
            settings_path = Path(folder) / "settings.json"
            settings_path.write_text('{"montage_renderer":"remotion"}', encoding="utf-8")
            with patch.object(config, "config_path", return_value=settings_path):
                restored = config.load_settings()
        self.assertEqual(restored.montage_renderer, "ffmpeg")
        self.assertFalse(restored.montage_renderer_explicit)

    def test_persisted_montage_renderer_does_not_probe_gpu_default(self):
        """Existing operator choices must not spawn an FFmpeg/NVENC capability probe."""
        with tempfile.TemporaryDirectory() as folder:
            settings_path = Path(folder) / "settings.json"
            settings_path.write_text(
                '{"montage_renderer":"ffmpeg","montage_renderer_explicit":true}',
                encoding="utf-8",
            )
            with patch.object(config, "config_path", return_value=settings_path), \
                 patch.object(config, "default_montage_renderer",
                              side_effect=AssertionError("GPU default must not be probed")):
                restored = config.load_settings()
        self.assertEqual(restored.montage_renderer, "ffmpeg")
        self.assertTrue(restored.montage_renderer_explicit)

    def test_gpu_timeline_renderer_setting_round_trips_without_remapping(self):
        """The explicit GPU choice must survive the React/IPC/Core settings boundary."""
        settings = Settings()
        with patch.object(bridge, "load_settings", return_value=settings), \
             patch.object(bridge, "save_settings"), \
             patch.object(bridge, "snapshot", return_value={}):
            bridge.save_montage_settings({"renderer": "gpu-timeline"})
        self.assertEqual(settings.montage_renderer, "gpu-timeline")

    def test_new_montage_profile_uses_gpu_only_when_capability_is_available(self):
        with patch.object(config, "gpu_timeline_available", return_value=True):
            self.assertEqual(config.default_montage_renderer(), "gpu-timeline")
        with patch.object(config, "gpu_timeline_available", return_value=False):
            self.assertEqual(config.default_montage_renderer(), "ffmpeg")

    def test_gpu_capability_probe_is_cached_for_new_profile_defaults(self):
        """Opening Montage must not spawn a new FFmpeg probe for every settings read."""
        original = config._GPU_TIMELINE_AVAILABLE
        try:
            config._GPU_TIMELINE_AVAILABLE = None
            with patch.object(config, "_probe_gpu_timeline_available", return_value=True) as probe:
                self.assertEqual(config.default_montage_renderer(), "gpu-timeline")
                self.assertEqual(config.default_montage_renderer(), "gpu-timeline")
            self.assertEqual(probe.call_count, 1)
        finally:
            config._GPU_TIMELINE_AVAILABLE = original

    def test_explicit_remotion_selection_is_preserved(self):
        with tempfile.TemporaryDirectory() as folder:
            settings_path = Path(folder) / "settings.json"
            settings_path.write_text(
                '{"montage_renderer":"remotion","montage_renderer_explicit":true}', encoding="utf-8",
            )
            with patch.object(config, "config_path", return_value=settings_path):
                restored = config.load_settings()

        self.assertEqual(restored.montage_renderer, "remotion")
        self.assertTrue(restored.montage_renderer_explicit)

    def test_english_screen_text_filter_is_a_core_non_optional_policy(self):
        with tempfile.TemporaryDirectory() as folder:
            settings_path = Path(folder) / "settings.json"
            settings_path.write_text('{"montage_exclude_english_text":false}', encoding="utf-8")
            with patch.object(config, "config_path", return_value=settings_path):
                restored = config.load_settings()
            self.assertTrue(restored.montage_exclude_english_text)

        settings = Settings(montage_exclude_english_text=True)
        with patch.object(bridge, "load_settings", return_value=settings), \
             patch.object(bridge, "save_settings"), \
             patch.object(bridge, "snapshot", return_value={}):
            bridge.save_montage_settings({"excludeEnglishText": False})
        self.assertTrue(settings.montage_exclude_english_text)

    def test_screen_candidate_deep_checks_uncertain_and_rejects_a_confirmed_block(self):
        calls = []

        class FakeIndex:
            def __init__(self, shallow, deep=None):
                self.shallow = shallow
                self.deep = deep if deep is not None else shallow

            def screen_text_eligibility(self, _path, *, deep=False):
                calls.append(deep)
                return self.deep if deep else self.shallow

        item = FootageItem("D:/library/russian-caption.mp4", "russian-caption.mp4")
        self.assertFalse(bridge._montage_screen_text_safe(FakeIndex("UNCERTAIN", "BLOCKED"), item))
        self.assertTrue(bridge._montage_screen_text_safe(FakeIndex("UNCERTAIN", "UNCERTAIN"), item))
        self.assertTrue(bridge._montage_screen_text_safe(FakeIndex("SAFE"), item))
        self.assertFalse(bridge._montage_screen_text_safe(FakeIndex("BLOCKED"), item))
        self.assertEqual(calls, [False, True, False, True, False, False])

    def test_after_screen_text_maintenance_montage_reuses_final_verdicts_without_deep_decode(self):
        """After explicit Latin maintenance, montage must not reopen final SAFE/BLOCKED media."""
        with tempfile.TemporaryDirectory(prefix="newsflow-montage-screen-cache-") as folder:
            root = Path(folder)
            safe = root / "safe.mp4"
            blocked = root / "blocked.mp4"
            safe.write_bytes(b"safe")
            blocked.write_bytes(b"blocked")
            progress_events = []
            index = ClipIndex(
                root / "index.sqlite3",
                embedder_factory=lambda: (object(), object()),
                screen_text_progress=lambda stage, name: progress_events.append((stage, name)),
            )

            with index._connect() as connection:
                connection.executemany(
                    "INSERT INTO clips(path,name,size,mtime_ns,english_text,english_text_version,embedding) "
                    "VALUES(?,?,?,?,?,?,?)",
                    [
                        (
                            str(safe.resolve()), safe.name, safe.stat().st_size, safe.stat().st_mtime_ns,
                            0, SCREEN_TEXT_CLASSIFIER_VERSION,
                            np.asarray([0.0, 1.0], dtype=np.float32).tobytes(),
                        ),
                        (
                            str(blocked.resolve()), blocked.name, blocked.stat().st_size, blocked.stat().st_mtime_ns,
                            0, SCREEN_TEXT_CLASSIFIER_VERSION,
                            np.asarray([1.0, 0.0], dtype=np.float32).tobytes(),
                        ),
                    ],
                )

            query_vectors = np.asarray([[1.0, 0.0], [0.0, 1.0]], dtype=np.float32)
            with patch.object(index, "_text_model_is_cached", return_value=True), \
                 patch.object(index, "_query_vectors", return_value=query_vectors), \
                 patch.object(index, "_screen_text_state", return_value=0) as maintenance_decode:
                result = index.classify_english_screen_text()

            self.assertEqual(result, {"checked": 2, "blocked": 1, "safe": 1, "uncertain": 0})
            maintenance_decode.assert_called_once_with(safe, samples=11)
            self.assertTrue(progress_events)
            progress_events.clear()

            safe_item = FootageItem(str(safe), safe.name)
            blocked_item = FootageItem(str(blocked), blocked.name)
            with patch.object(
                index,
                "_screen_text_state",
                side_effect=AssertionError("montage must not decode media after final Latin verdict"),
            ), patch.object(
                index,
                "_bounded_screen_text_state",
                side_effect=AssertionError("montage must not run deep screen-text check after maintenance"),
            ):
                self.assertTrue(bridge._montage_screen_text_safe(index, safe_item))
                self.assertTrue(bridge._montage_screen_text_safe(index, safe_item))
                self.assertFalse(bridge._montage_screen_text_safe(index, blocked_item))
                self.assertFalse(bridge._montage_screen_text_safe(index, blocked_item))
            self.assertEqual(progress_events, [], "final verdicts must not surface a montage text-check stage")

    def test_semantic_rescue_can_use_best_safe_hit_below_normal_score_floor(self):
        candidate = FootageItem(
            "D:/library/neutral-government.mp4",
            "neutral-government.mp4",
            tags=["documentary-neutral"],
        )
        kwargs = {
            "scene_query": "Washington government press conference",
            "strict_hits": [SearchHit(candidate, .03, duration=6.0)],
            "fallback_hits": [],
            "relaxed_hits": [], "category_hits": [], "safe_context_hits": [],
            "required_duration": 6.0, "match_threshold": .22,
            "used_paths": set(), "used_families": set(),
            "project_used_paths": set(), "project_used_families": set(),
            "reserved_paths": set(), "reserved_families": set(),
            "source_exists": lambda _item: True,
            "source_duration": lambda _item: 6.0,
            "source_allowed": lambda _item: True,
            "allow_safe_reuse": False,
        }
        with self.assertRaises(bridge.MontageSelectionFailure):
            bridge._select_montage_candidate(**kwargs)

        rescued = bridge._select_montage_candidate(
            **kwargs, allow_below_threshold=True,
        )
        self.assertEqual(rescued.item.path, candidate.path)
        self.assertEqual(rescued.fallback_level, "STRICT_MATCH")

    def test_final_thematic_mismatch_is_reserved_for_continuity_fallback(self):
        stale_tag = FootageItem(
            "D:/library/washington-building.mp4",
            "Washington government building exterior.mp4",
            tags=["factory-industry"],
        )
        sevastopol = FootageItem(
            "D:/library/sevastopol.mp4",
            "Sevastopol government building.mp4",
            tags=["factory-industry", "sevastopol"],
        )
        query = "Washington DC White House US government officials"

        self.assertFalse(bridge._semantic_clip_ok(query, stale_tag))
        self.assertFalse(bridge._semantic_clip_ok(query, sevastopol))

    def test_visual_continuity_fallback_is_topic_agnostic_and_prefers_new_family(self):
        reused = FootageItem("D:/used/family-a/clip.mp4", "used.mp4", tags=["ukraine"])
        unrelated_fresh = FootageItem(
            "D:/fresh/family-b/clip.mp4", "fresh.mp4", tags=["factory-industry", "russia"],
        )
        family_a = bridge.source_family_identity_text(reused.path, reused.source_url)
        choice = bridge._select_visual_continuity_candidate(
            [reused, unrelated_fresh],
            required_duration=6.0,
            project_used_paths={bridge._montage_clip_key(reused.path)},
            project_used_families={family_a},
            recent_project_paths=set(),
            source_exists=lambda _item: True,
            source_duration=lambda _item: 6.0,
            source_allowed=lambda _item: True,
            diversity_seed="topic-agnostic",
            allow_project_reuse=False,
        )
        self.assertIsNotNone(choice)
        item, duration, _family, reused_flag = choice
        self.assertEqual(item.path, unrelated_fresh.path)
        self.assertEqual(duration, 6.0)
        self.assertFalse(reused_flag)

    def test_visual_continuity_fallback_reuses_when_only_valid_family_remains(self):
        only = FootageItem("D:/used/family-a/clip.mp4", "used.mp4", tags=["anything"])
        family = bridge.source_family_identity_text(only.path, only.source_url)
        blocked_reuse = bridge._select_visual_continuity_candidate(
            [only],
            required_duration=6.0,
            project_used_paths={bridge._montage_clip_key(only.path)},
            project_used_families={family},
            recent_project_paths={bridge._montage_clip_key(only.path)},
            source_exists=lambda _item: True,
            source_duration=lambda _item: 6.0,
            source_allowed=lambda _item: True,
            diversity_seed="reuse-last",
            allow_project_reuse=False,
        )
        self.assertIsNone(blocked_reuse)

        choice = bridge._select_visual_continuity_candidate(
            [only],
            required_duration=6.0,
            project_used_paths={bridge._montage_clip_key(only.path)},
            project_used_families={family},
            recent_project_paths={bridge._montage_clip_key(only.path)},
            source_exists=lambda _item: True,
            source_duration=lambda _item: 6.0,
            source_allowed=lambda _item: True,
            diversity_seed="reuse-last",
            allow_project_reuse=True,
        )
        self.assertIsNotNone(choice)
        self.assertEqual(choice[0].path, only.path)
        self.assertTrue(choice[3])

    def test_visual_continuity_fallback_still_rejects_technical_bad_media(self):
        short = FootageItem("D:/bad/short.mp4", "short.mp4")
        blocked = FootageItem("D:/bad/english-title.mp4", "english-title.mp4")
        choice = bridge._select_visual_continuity_candidate(
            [short, blocked],
            required_duration=6.0,
            project_used_paths=set(),
            project_used_families=set(),
            recent_project_paths=set(),
            source_exists=lambda _item: True,
            source_duration=lambda item: 2.0 if item.path == short.path else 6.0,
            source_allowed=lambda item: item.path != blocked.path,
            diversity_seed="technical-guards",
        )
        self.assertIsNone(choice)

    def test_normalized_montage_query_deduplicates_and_removes_generic_phrases(self):
        normalized = bridge._normalized_montage_visual_query(
            "international news, documentary footage, oil tanker refinery oil terminal, "
            "oil tanker refinery oil terminal, seaport cargo cranes ships"
        )
        self.assertEqual(
            normalized,
            "oil tanker refinery oil terminal, seaport cargo cranes ships",
        )

    def test_prepare_montage_uses_local_scan_when_ai_index_is_empty(self):
        """A new footage folder must work before its optional AI index is built."""
        from scriptor.core import ScenarioRequest
        from scriptor.runner import Job

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            footage = root / "footage"
            footage.mkdir()
            write_readable_video(footage / "Iran oil tanker Hormuz shipping.mp4")
            voice = root / "voice.mp3"
            voice.write_bytes(b"voice")
            settings = Settings(
                footage_folders=[str(footage)], voicer_output_folder=str(root),
                montage_project_folder=str(root / "projects"), montage_output_folder=str(root / "output"),
                montage_use_script_text=False, montage_auto_web=False,
            )
            job = Job(ScenarioRequest(0, "Iran oil tanker Hormuz", ""), RunState.DONE, "", "")
            settings.voice_scenario_outputs = {"1": str(voice)}
            with patch.object(bridge, "load_settings", return_value=settings), \
                 patch.object(bridge, "load_session", return_value=(["Iran oil tanker Hormuz"], [job])), \
                 patch.object(bridge, "save_settings"), \
                 patch.object(bridge, "snapshot", return_value={}), \
                 patch.object(bridge, "_montage_screen_text_safe", return_value=True), \
                 patch.object(bridge.ClipIndex, "count", return_value=0), \
                 patch.object(bridge, "probe_media_duration", return_value=6.0), \
                 patch.object(bridge, "probe_video_duration", return_value=8.0):
                result = bridge.prepare_montage({"scenarioIndex": 0})

        self.assertEqual(result["preparedProject"]["clips"], 1)

    def test_continuity_keeps_unindexed_local_scan_after_semantic_pool_exhausts(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            footage = root / "footage"
            footage.mkdir()
            write_readable_video(footage / "oil tanker cargo port.mp4")
            voice = root / "voice.mp3"
            voice.write_bytes(b"voice")
            settings = Settings(
                footage_folders=[str(footage)], voicer_output_folder=str(root),
                montage_project_folder=str(root / "projects"), montage_output_folder=str(root / "output"),
                montage_use_script_text=False, montage_auto_web=False,
            )
            settings.voice_scenario_outputs = {"1": str(voice)}
            job = Job(ScenarioRequest(0, "oil tanker cargo port", ""), RunState.DONE, "", "")
            with (patch.object(bridge, "load_settings", return_value=settings),
                  patch.object(bridge, "load_session", return_value=(["oil tanker cargo port"], [job])),
                  patch.object(bridge, "save_settings"),
                  patch.object(bridge, "snapshot", return_value={}),
                  patch.object(bridge, "_montage_screen_text_safe", return_value=True),
                  patch.object(bridge.ClipIndex, "count", return_value=0),
                  patch.object(bridge.ClipIndex, "all_items",
                               side_effect=AssertionError("continuity must use fresh finalist checks")),
                  patch.object(bridge, "_select_montage_candidate",
                               side_effect=bridge.MontageSelectionFailure({})),
                  patch.object(bridge, "probe_media_duration", return_value=6.0),
                  patch.object(bridge, "probe_video_duration", return_value=8.0)):
                result = bridge.prepare_montage({"scenarioIndex": 0})
            project = TimelineProject.load(Path(result["preparedProject"]["path"]))
            self.assertEqual(project.clips[0].fallback_level, "VISUAL_CONTINUITY_FALLBACK")
            self.assertEqual(result["preparedProject"]["clips"], 1)

    def test_available_narration_is_used_even_when_title_only_fallback_is_allowed(self):
        from scriptor.core import ScenarioRequest
        from scriptor.runner import Job

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            footage = root / "footage"
            footage.mkdir()
            write_readable_video(footage / "NATO cyber security.mp4")
            voice = root / "voice.mp3"
            voice.write_bytes(b"voice")
            settings = Settings(
                footage_folders=[str(footage)], voicer_output_folder=str(root),
                montage_project_folder=str(root / "projects"), montage_output_folder=str(root / "output"),
                montage_use_script_text=False, montage_auto_web=False,
            )
            narration = "НАТО усиливает защиту Европы после гибридной кибератаки."
            job = Job(ScenarioRequest(0, "НАТО и киберугрозы", ""), RunState.DONE, narration, "")
            settings.voice_scenario_outputs = {"1": str(voice)}
            with patch.object(bridge, "load_settings", return_value=settings), \
                 patch.object(bridge, "load_session", return_value=(["НАТО и киберугрозы"], [job])), \
                 patch.object(bridge, "save_settings"), \
                 patch.object(bridge, "snapshot", return_value={}), \
                 patch.object(bridge, "_montage_screen_text_safe", return_value=True), \
                 patch.object(bridge.ClipIndex, "count", return_value=0), \
                 patch.object(bridge, "probe_media_duration", return_value=6.0), \
                 patch.object(bridge, "probe_video_duration", return_value=8.0), \
                 patch.object(bridge, "title_only_scene_plan", side_effect=AssertionError("title-only must not run")):
                result = bridge.prepare_montage({"scenarioIndex": 0})

        self.assertEqual(result["preparedProject"]["clips"], 1)

    def test_selection_uses_reserved_candidate_only_after_new_candidates_are_exhausted(self):
        available = FootageItem("D:/new-family/clip_new_001.mp4", "new.mp4", tags=["oil-tanker-port"])
        reserved = FootageItem("D:/reserved-family/clip_reserved_001.mp4", "reserved.mp4", tags=["oil-tanker-port"])
        query = "oil tanker refinery oil terminal"
        result = bridge._select_montage_candidate(
            query,
            strict_hits=[SearchHit(available, .30, duration=6.0), SearchHit(reserved, .95, duration=6.0)],
            fallback_hits=[],
            required_duration=6.0,
            match_threshold=.22,
            used_paths=set(), used_families=set(), project_used_paths=set(), project_used_families=set(),
            reserved_paths={bridge._montage_clip_key(reserved.path)},
            reserved_families={bridge._montage_clip_family_key(reserved.path)},
            source_exists=lambda item: True,
            source_duration=lambda item: 6.0,
        )
        self.assertEqual(result.item.path, available.path)
        self.assertEqual(result.fallback_level, "STRICT_MATCH")
        self.assertFalse(result.reused_reserved_candidate)

    def test_selection_uses_safe_reserved_reuse_when_reservation_exhausts_candidates(self):
        reserved = FootageItem("D:/reserved-family/clip_reserved_001.mp4", "reserved.mp4", tags=["oil-tanker-port"])
        result = bridge._select_montage_candidate(
            "oil tanker refinery oil terminal",
            strict_hits=[SearchHit(reserved, .30, duration=6.0)], fallback_hits=[],
            required_duration=6.0, match_threshold=.22,
            used_paths=set(), used_families=set(), project_used_paths=set(), project_used_families=set(),
            reserved_paths={bridge._montage_clip_key(reserved.path)},
            reserved_families={bridge._montage_clip_family_key(reserved.path)},
            source_exists=lambda item: True, source_duration=lambda item: 6.0,
        )
        self.assertEqual(result.item.path, reserved.path)
        self.assertEqual(result.fallback_level, "SAFE_REUSE")
        self.assertTrue(result.reused_reserved_candidate)

    def test_reservation_race_converts_valid_selection_to_safe_reuse(self):
        item = FootageItem("D:/reserved/clip_001.mp4", "shot.mp4")
        selection = bridge.MontageCandidateSelection(item, 6.0, .30, "STRICT_MATCH", False, {})
        reused = bridge._safe_reuse_after_reservation_race(selection, claim=lambda _: False)
        self.assertEqual(reused.fallback_level, "SAFE_REUSE")
        self.assertTrue(reused.reused_reserved_candidate)

    def test_selection_uses_the_only_safe_clip_as_last_resort(self):
        """Quality exhaustion must not turn one valid local clip into NO_FOOTAGE."""
        same = FootageItem("D:/one-family/clip_001.mp4", "same.mp4", tags=["oil-tanker-port"])
        result = bridge._select_montage_candidate(
            "oil tanker refinery oil terminal",
            strict_hits=[SearchHit(same, .30, duration=6.0)], fallback_hits=[],
            required_duration=6.0, match_threshold=.22,
            used_paths={bridge._montage_clip_key(same.path)},
            used_families={bridge._montage_clip_family_key(same.path)},
            project_used_paths={bridge._montage_clip_key(same.path)},
            project_used_families={bridge._montage_clip_family_key(same.path)},
            recent_project_paths={bridge._montage_clip_key(same.path)},
            reserved_paths=set(), reserved_families=set(),
            source_exists=lambda item: True, source_duration=lambda item: 6.0,
        )
        self.assertEqual(result.item.path, same.path)
        self.assertEqual(result.fallback_level, "SAFE_REUSE")

    def test_safe_reuse_avoids_the_immediately_previous_clip_when_an_older_valid_clip_exists(self):
        """A B A is acceptable after quality exhaustion; A A is not."""
        older = FootageItem("D:/pool/older.mp4", "older.mp4", tags=["oil-tanker-port"])
        previous = FootageItem("D:/pool/previous.mp4", "previous.mp4", tags=["oil-tanker-port"])
        result = bridge._select_montage_candidate(
            "oil tanker refinery oil terminal",
            strict_hits=[SearchHit(previous, .95, duration=6.0), SearchHit(older, .30, duration=6.0)],
            fallback_hits=[], required_duration=6.0, match_threshold=.22,
            used_paths={bridge._montage_clip_key(older.path), bridge._montage_clip_key(previous.path)},
            used_families={bridge._montage_clip_family_key(older.path), bridge._montage_clip_family_key(previous.path)},
            project_used_paths={bridge._montage_clip_key(older.path), bridge._montage_clip_key(previous.path)},
            project_used_families={bridge._montage_clip_family_key(older.path), bridge._montage_clip_family_key(previous.path)},
            recent_project_paths={bridge._montage_clip_key(previous.path)},
            reserved_paths=set(), reserved_families=set(),
            source_exists=lambda _: True, source_duration=lambda _: 6.0,
        )
        self.assertEqual(result.item.path, older.path)
        self.assertEqual(result.fallback_level, "SAFE_REUSE")

    def test_safe_reuse_prefers_cross_video_family_before_current_project_repeat(self):
        current = FootageItem("D:/current/family-a/shot.mp4", "current.mp4", tags=["oil-tanker-port"])
        cross_video = FootageItem("D:/history/family-b/shot.mp4", "history.mp4", tags=["oil-tanker-port"])
        current_key = bridge._montage_clip_key(current.path)
        current_family = bridge._montage_clip_family_key(current.path)
        cross_key = bridge._montage_clip_key(cross_video.path)
        cross_family = bridge._montage_clip_family_key(cross_video.path)

        result = bridge._select_montage_candidate(
            "oil tanker refinery oil terminal",
            strict_hits=[
                SearchHit(current, .95, duration=6.0),
                SearchHit(cross_video, .30, duration=6.0),
            ],
            fallback_hits=[], required_duration=6.0, match_threshold=.22,
            used_paths={current_key, cross_key},
            used_families={current_family, cross_family},
            project_used_paths={current_key},
            project_used_families={current_family},
            reserved_paths={cross_key},
            reserved_families={cross_family},
            source_exists=lambda _: True, source_duration=lambda _: 6.0,
        )

        self.assertEqual(result.item.path, cross_video.path)
        self.assertNotIn(result.item.path, {current.path})
        self.assertEqual(result.fallback_level, "SAFE_REUSE")

    def test_diagnostics_separate_unique_diversity_rejections_from_pass_events(self):
        """One candidate may be examined repeatedly but remains one unique rejection."""
        used = FootageItem("D:/used/used.mp4", "used.mp4", tags=["oil-tanker-port"])
        fresh = FootageItem("D:/fresh/fresh.mp4", "fresh.mp4", tags=["oil-tanker-port"])
        result = bridge._select_montage_candidate(
            "oil tanker refinery oil terminal",
            strict_hits=[SearchHit(used, .40, duration=6.0), SearchHit(fresh, .30, duration=6.0)],
            fallback_hits=[], required_duration=6.0, match_threshold=.22,
            used_paths={bridge._montage_clip_key(used.path)},
            used_families={bridge._montage_clip_family_key(used.path)},
            project_used_paths=set(), project_used_families=set(),
            reserved_paths=set(), reserved_families=set(),
            source_exists=lambda _: True, source_duration=lambda _: 6.0,
        )
        self.assertEqual(result.item.path, fresh.path)
        self.assertEqual(result.diagnostics["unique_rejected_diversity"], 1)
        self.assertGreaterEqual(result.diagnostics["rejection_events"], 1)

    def test_last_resort_still_avoids_previous_clip_when_any_other_valid_clip_exists(self):
        previous = FootageItem("D:/pool/previous.mp4", "previous.mp4", tags=["oil-tanker-port"])
        alternative = FootageItem("D:/pool/alternative.mp4", "alternative.mp4", tags=["oil-tanker-port"])
        result = bridge._select_montage_candidate(
            "oil tanker refinery oil terminal",
            strict_hits=[SearchHit(previous, .95, duration=6.0), SearchHit(alternative, .20, duration=6.0)],
            fallback_hits=[], required_duration=6.0, match_threshold=.22,
            used_paths={bridge._montage_clip_key(previous.path), bridge._montage_clip_key(alternative.path)},
            used_families={bridge._montage_clip_family_key(previous.path), bridge._montage_clip_family_key(alternative.path)},
            project_used_paths={bridge._montage_clip_key(previous.path), bridge._montage_clip_key(alternative.path)},
            project_used_families={bridge._montage_clip_family_key(previous.path), bridge._montage_clip_family_key(alternative.path)},
            recent_project_paths={bridge._montage_clip_key(previous.path), bridge._montage_clip_key(alternative.path)},
            immediately_previous_path=bridge._montage_clip_key(previous.path),
            reserved_paths=set(), reserved_families=set(),
            source_exists=lambda _: True, source_duration=lambda _: 6.0,
        )
        self.assertEqual(result.item.path, alternative.path)
        self.assertEqual(result.fallback_level, "SAFE_REUSE")

    def test_failed_planner_releases_only_its_own_batch_reservations(self):
        usage = {
            "lock": __import__("threading").RLock(),
            "paths": {"path-82": 81, "path-83": 82},
            "families": {"family-82": 81, "family-83": 82},
            "claims": {("EARLY", "family-82"): 81, ("EARLY", "family-83"): 82},
            "placements": {"shared": [(81, "EARLY"), (82, "MIDDLE")]},
            "windows": {"shared": [(81, 0.0), (82, 6.0)]},
        }
        bridge._release_batch_footage_reservations(usage, 81)
        self.assertNotIn("path-82", usage["paths"])
        self.assertNotIn("family-82", usage["families"])
        self.assertNotIn(("EARLY", "family-82"), usage["claims"])
        self.assertEqual(usage["paths"]["path-83"], 82)
        self.assertEqual(usage["families"]["family-83"], 82)
        self.assertEqual(usage["claims"][("EARLY", "family-83")], 82)
        self.assertEqual(usage["placements"]["shared"], [(82, "MIDDLE")])
        self.assertEqual(usage["windows"]["shared"], [(82, 6.0)])

    def test_selection_uses_relaxed_match_below_ideal_threshold(self):
        item = FootageItem("D:/oil/clip_001.mp4", "oil.mp4", tags=["oil-tanker-port"])
        result = bridge._select_montage_candidate(
            "oil tanker refinery", strict_hits=[SearchHit(item, .18, duration=6.0)], fallback_hits=[],
            required_duration=6.0, match_threshold=.22, used_paths=set(), used_families=set(),
            project_used_paths=set(), project_used_families=set(), reserved_paths=set(), reserved_families=set(),
            source_exists=lambda _: True, source_duration=lambda _: 6.0,
        )
        self.assertEqual(result.fallback_level, "RELAXED_SEMANTIC")
        self.assertEqual(result.diagnostics["rejected_threshold"], 1)

    def test_selection_skips_missing_strict_candidate_for_valid_category_candidate(self):
        missing = FootageItem("D:/oil/missing.mp4", "missing.mp4", tags=["oil-tanker-port"])
        category = FootageItem("D:/port/clip_002.mp4", "port.mp4", tags=["port-logistics"])
        result = bridge._select_montage_candidate(
            "oil tanker refinery", strict_hits=[SearchHit(missing, .50, duration=6.0)],
            fallback_hits=[SearchHit(category, .20, duration=6.0)], required_duration=6.0,
            match_threshold=.22, used_paths=set(), used_families=set(), project_used_paths=set(),
            project_used_families=set(), reserved_paths=set(), reserved_families=set(),
            source_exists=lambda item: item.path != missing.path, source_duration=lambda _: 6.0,
        )
        self.assertEqual(result.item.path, category.path)
        self.assertEqual(result.fallback_level, "CATEGORY_MATCH")
        self.assertGreaterEqual(result.diagnostics["rejected_missing"], 2)

    def test_snapshot_sync_never_replaces_a_render_error_with_new_mp3(self):
        """A finished MP3 scan must not hide a resumable footage/render error."""
        with tempfile.TemporaryDirectory() as folder:
            voice = Path(folder) / "voice.mp3"
            voice.write_bytes(b"mp3")
            settings = Settings(voice_scenario_outputs={"13": str(voice)})
            settings.montage_task_statuses = {
                "12": {
                    "title": "Тема", "scenarioIndex": 12, "status": "Ошибка",
                    "phase": "Ошибка рендера", "progress": 100,
                    "error": "Футаж не найден: D:/missing.mp4",
                    "projectPath": "D:/projects/topic.newsflow",
                    "voicePath": str(voice),
                }
            }
            changed = bridge._sync_finished_scenarios_to_montage(settings, [{
                "index": 12, "title": "Тема", "state": RunState.DONE.value, "result": "Сценарий",
            }])
            self.assertFalse(changed)
            self.assertEqual(settings.montage_task_statuses["12"]["status"], "Ошибка")
            self.assertEqual(settings.montage_task_statuses["12"]["projectPath"], "D:/projects/topic.newsflow")

    def test_snapshot_sync_restores_an_error_hidden_by_old_mp3_handoff(self):
        with tempfile.TemporaryDirectory() as folder:
            voice = Path(folder) / "voice.mp3"
            voice.write_bytes(b"mp3")
            settings = Settings(voice_scenario_outputs={"14": str(voice)})
            settings.montage_task_statuses = {
                "13": {
                    "title": "Тема", "scenarioIndex": 13, "status": "Новый MP3",
                    "phase": "Новая озвучка", "progress": 0, "voicePath": str(voice),
                    "projectPath": "D:/projects/topic.newsflow", "error": "",
                    "timeline": [{"label": "Ошибка рендера", "progress": 100,
                                  "detail": "Футаж не найден: D:/missing.mp4"}],
                }
            }
            changed = bridge._sync_finished_scenarios_to_montage(settings, [{
                "index": 13, "title": "Тема", "state": RunState.DONE.value, "result": "Сценарий",
            }])
            self.assertTrue(changed)
            row = settings.montage_task_statuses["13"]
            self.assertEqual(row["status"], "Ошибка")
            self.assertEqual(row["phase"], "Ошибка рендера")
            self.assertIn("Футаж не найден", row["error"])

    def test_render_preflight_reports_only_missing_timeline_clips(self):
        """A saved project is replanned before FFmpeg when a source vanished."""
        from scriptor.timeline import TimelineClip, TimelineProject

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            present = root / "present.mp4"
            missing = root / "missing.mp4"
            present.write_bytes(b"clip")
            project = TimelineProject(
                title="Тема",
                clips=[
                    TimelineClip(path=str(present), narration="a", visual_query_en="a", duration=6),
                    TimelineClip(path=str(missing), narration="b", visual_query_en="b", duration=6),
                ],
            )
            with patch("scriptor.bridge._validated_montage_clip_duration", side_effect=lambda path: 6.0 if path == present else 0.0):
                self.assertEqual(bridge._montage_project_missing_clips(project), [str(missing)])

    def test_missing_clip_recovery_replaces_only_the_invalid_slot(self):
        """Recovery preserves all healthy edits, narration and source MP3."""
        from scriptor.timeline import TimelineClip, TimelineProject

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            first, missing, last, replacement = (root / name for name in ("first.mp4", "gone.mp4", "last.mp4", "replacement.mp4"))
            first.write_bytes(b"first")
            last.write_bytes(b"last")
            replacement.write_bytes(b"replacement")
            project = TimelineProject(
                title="Тема", voiceover_path="D:/audio/13.mp3",
                clips=[
                    TimelineClip(str(first), "first narration", "first query", duration=6.0),
                    TimelineClip(str(missing), "missing narration", "missing query", duration=4.0),
                    TimelineClip(str(last), "last narration", "last query", duration=6.0),
                ],
            )
            durations = {str(first): 6.0, str(missing): 0.0, str(last): 6.0, str(replacement): 6.0}
            with patch("scriptor.bridge._validated_montage_clip_duration", side_effect=lambda path: durations[str(path)]):
                repaired = bridge._repair_missing_project_clips(
                    project,
                    lambda clip, _excluded: [FootageItem(str(replacement), replacement.name, "local")],
                )
            self.assertEqual(repaired, 1)
            self.assertEqual([clip.path for clip in project.clips], [str(first), str(replacement), str(last)])
            self.assertEqual(project.clips[1].narration, "missing narration")
            self.assertEqual(project.clips[1].visual_query_en, "missing query")
            self.assertEqual(project.voiceover_path, "D:/audio/13.mp3")

    def test_missing_clip_recovery_never_uses_an_invalid_or_too_short_replacement(self):
        from scriptor.timeline import TimelineClip, TimelineProject

        project = TimelineProject(title="Тема", clips=[TimelineClip("gone.mp4", "n", "q", duration=5.0)])
        durations = {"gone.mp4": 0.0, "tiny.mp4": 2.0, "healthy.mp4": 6.0}
        with patch("scriptor.bridge._validated_montage_clip_duration", side_effect=lambda path: durations[str(path)]):
            repaired = bridge._repair_missing_project_clips(
                project,
                lambda _clip, _excluded: [
                    FootageItem("tiny.mp4", "tiny.mp4"),
                    FootageItem("healthy.mp4", "healthy.mp4"),
                ],
            )
        self.assertEqual(repaired, 1)
        self.assertEqual(project.clips[0].path, "healthy.mp4")

    def test_ormuz_scene_rejects_explicit_ukraine_clip(self):
        scene = "Strait of Hormuz oil tanker Iran Persian Gulf"
        wrong = FootageItem("D:/clips/Pokrovsk_Ukraine_42.mp4", "Pokrovsk Ukraine battle.mp4", tags=["ukraine", "pokrovsk"])
        right = FootageItem("D:/clips/oil_tanker_hormuz_12.mp4", "oil tanker Hormuz.mp4", tags=["iran", "tanker"])
        self.assertFalse(bridge._semantic_clip_ok(scene, wrong))
        self.assertTrue(bridge._semantic_clip_ok(scene, right))

    def test_ormuz_scene_rejects_explicitly_wrong_external_result_before_download(self):
        scene = "Strait of Hormuz oil tanker Iran Persian Gulf"
        wrong = {"title": "Pokrovsk battle footage Ukraine", "url": "https://example.test/pokrovsk.mp4"}
        right = {"title": "Oil tanker at the Strait of Hormuz", "url": "https://example.test/tanker.mp4"}
        self.assertFalse(bridge._external_candidate_ok(scene, wrong))
        self.assertTrue(bridge._external_candidate_ok(scene, right))

    def test_frontline_scene_prefers_enriched_military_footage(self):
        scene = "frontline battlefield soldiers advancing infantry armored vehicles"
        frontline = FootageItem("D:/clips/a.mp4", "clip.mp4", tags=["frontline-combat", "offensive-advance"])
        neutral = FootageItem("D:/clips/b.mp4", "clip.mp4", tags=["international-news"])
        self.assertGreater(bridge._montage_semantic_bonus(scene, frontline),
                           bridge._montage_semantic_bonus(scene, neutral))

    def test_war_scene_rejects_explicit_agriculture_footage(self):
        scene = "missile drone artillery strike frontline battlefield"
        farm = FootageItem("D:/clips/potato_harvest_tractor.mp4", "potato harvest.mp4",
                           tags=["agriculture-farming", "картошка"])
        drone = FootageItem("D:/clips/military_uav.mp4", "military drone.mp4",
                            tags=["military-drone"])
        self.assertFalse(bridge._semantic_clip_ok(scene, farm))
        self.assertTrue(bridge._semantic_clip_ok(scene, drone))

    def test_agriculture_scene_keeps_agriculture_footage_available(self):
        scene = "potato harvest farming tractor agricultural field"
        farm = FootageItem("D:/clips/potato_harvest_tractor.mp4", "potato harvest.mp4",
                           tags=["agriculture-farming"])
        self.assertTrue(bridge._semantic_clip_ok(scene, farm))

    def test_protest_and_migrant_scenes_prefer_their_own_clusters(self):
        protest = FootageItem("D:/clips/protest.mp4", "clip.mp4", tags=["protest-crowd"])
        border = FootageItem("D:/clips/border.mp4", "clip.mp4", tags=["migrant-border"])
        neutral = FootageItem("D:/clips/office.mp4", "clip.mp4", tags=["political-office"])
        self.assertGreater(bridge._montage_semantic_bonus("protest crowd street rally", protest),
                           bridge._montage_semantic_bonus("protest crowd street rally", neutral))
        self.assertGreater(bridge._montage_semantic_bonus("migrants border crossing", border),
                           bridge._montage_semantic_bonus("migrants border crossing", neutral))

    def test_short_indexed_source_is_not_used_for_a_long_scene(self):
        # The selection filter rejects an undersized SearchHit before FFmpeg
        # can turn its missing tail into a frozen final frame.
        from scriptor.ai_index import SearchHit
        item = FootageItem("D:/clips/two-seconds.mp4", "two-seconds.mp4", tags=["frontline-combat"])
        self.assertLess(SearchHit(item, .9, duration=2.0).duration, 5.8)

    def test_terminal_153_second_tail_uses_a_real_last_resort_clip(self):
        """A tiny audio remainder must not fail just because only a reused real clip remains."""
        from scriptor.timeline import TimelineClip, TimelineProject

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            voice = root / "voice.mp3"
            footage = root / "news-footage.mp4"
            voice.write_bytes(b"voice")
            footage.write_bytes(b"footage")
            project = TimelineProject(
                title="Тема", voiceover_path=str(voice),
                clips=[TimelineClip(str(footage), "narration", "news footage", duration=6.0)],
            )
            # Exact narration target: one six-second clip leaves 1.53 seconds.
            # The renderer's cumulative frame grid no longer needs an extra
            # per-clip safety margin borrowed from an unverified interval.
            with patch.object(bridge, "probe_media_duration", return_value=7.53), \
                 patch.object(bridge, "_cached_or_probed_montage_duration", return_value=6.0), \
                 patch.object(bridge, "_replacement_candidates_for_clip", return_value=[
                     FootageItem(str(footage), footage.name, "local"),
                 ]):
                appended = bridge._complete_project_visual_tail(project, object(), Settings(montage_auto_web=False))

        self.assertEqual(appended, 1)
        self.assertEqual(len(project.clips), 2)
        self.assertAlmostEqual(sum(clip.duration for clip in project.clips), 7.53, places=2)
        self.assertAlmostEqual(project.clips[-1].duration, 1.53, places=2)
        self.assertEqual(project.clips[-1].path, str(footage))

    def test_voice_map_beat_uses_renderer_frame_padding_without_a_micro_tail(self):
        """Renderer padding must not create a synthetic sub-frame VoiceMap beat."""
        from scriptor.timeline import TimelineClip, TimelineProject

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            voice = root / "voice.mp3"
            first = root / "first.mp4"
            for path in (voice, first):
                path.write_bytes(path.name.encode())
            project = TimelineProject(
                title="Тема",
                voiceover_path=str(voice),
                clips=[
                    TimelineClip(
                        str(first), "first", "query", duration=6.398,
                        minimum_source_duration=6.0,
                        voice_segment_id=29, narration_start=0.0, narration_end=6.398,
                    ),
                ],
            )
            with patch.object(bridge, "probe_media_duration", return_value=6.398), \
                 patch.object(bridge, "_cached_or_probed_montage_duration", return_value=6.0), \
                 patch.object(bridge, "_replacement_candidates_for_clip") as replacements:
                appended = bridge._complete_project_visual_tail(
                    project, object(), Settings(montage_auto_web=False),
                )

        self.assertEqual(appended, 0)
        replacements.assert_not_called()
        self.assertEqual(len(project.clips), 1)
        self.assertEqual(project.clips[0].path, str(first))
        self.assertEqual(project.clips[0].duration, 6.398)
        self.assertEqual(project.clips[0].minimum_source_duration, 6.0)
        self.assertEqual(project.clips[0].voice_segment_id, 29)
        self.assertEqual(project.clips[0].narration_start, 0.0)
        self.assertEqual(project.clips[0].narration_end, 6.398)
        self.assertAlmostEqual(sum(clip.duration for clip in project.clips), 6.398, places=3)

    def test_clip_identity_is_case_insensitive_and_absolute(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "Shot.MP4"
            path.write_bytes(b"x")
            self.assertEqual(bridge._montage_clip_key(str(path)), bridge._montage_clip_key(str(path).lower()))

    def test_candidate_identity_does_not_resolve_each_library_path(self):
        """Ranking thousands of candidates must not call Windows path resolution."""
        with patch("scriptor.bridge.Path.resolve", side_effect=AssertionError("filesystem resolve")):
            key = bridge._montage_clip_key("D:/library/one/one_0001.mp4")
            family = bridge._montage_clip_family_key("D:/library/one/one_0001.mp4")
        self.assertEqual(key, "d:\\library\\one\\one_0001.mp4")
        self.assertEqual(family, "path::d:/library/one")

    def test_candidate_family_identity_does_not_construct_path_objects(self):
        with patch("scriptor.bridge.Path", side_effect=AssertionError("Path must not be used in ranking")):
            family = bridge._montage_clip_family_key("D:/library/one/one_0001.mp4")
        self.assertEqual(family, "path::d:/library/one")

    def test_generated_cuts_from_one_original_are_one_source_family(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "Зеленский" / "Исходный ролик"
            source.mkdir(parents=True)
            first = source / "Исходный ролик_0001.mp4"
            second = source / "Исходный ролик_0002.mp4"
            other = Path(folder) / "Зеленский" / "Другой исходник" / "Другой исходник_0001.mp4"
            other.parent.mkdir(parents=True)
            for path in (first, second, other):
                path.write_bytes(b"x")
            self.assertEqual(bridge._montage_clip_family_key(str(first)), bridge._montage_clip_family_key(str(second)))
            self.assertNotEqual(bridge._montage_clip_family_key(str(first)), bridge._montage_clip_family_key(str(other)))

    def test_same_source_family_is_excluded_even_when_clip_paths_differ(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "one-source"
            source.mkdir()
            used = source / "one-source_0001.mp4"
            alternate_cut = source / "one-source_0002.mp4"
            for path in (used, alternate_cut):
                path.write_bytes(b"x")
            item = FootageItem(str(alternate_cut), alternate_cut.name)
            self.assertTrue(bridge._montage_item_is_excluded(
                item, {bridge._montage_clip_key(str(used))},
                {bridge._montage_clip_family_key(str(used))},
            ))
    def test_paused_montage_is_still_an_active_batch(self):
        self.assertTrue(bridge.montage_queue_is_active({"3": {"status": "Пауза"}}))
        self.assertTrue(bridge.montage_queue_is_active({"3": {"status": "Рендер"}}))
        self.assertFalse(bridge.montage_queue_is_active({"3": {"status": "Готово"}}))

    def test_user_selected_planning_workers_are_not_hiddenly_limited_by_library_size(self):
        self.assertEqual(bridge._montage_planning_worker_limit(12, 8, 28_975), 8)
        self.assertEqual(bridge._montage_planning_worker_limit(4, 8, 28_975), 4)
        self.assertEqual(bridge._montage_planning_worker_limit(12, 8, 12_000), 8)
        self.assertEqual(bridge._montage_planning_worker_limit(6, 3, 100), 3)

    def test_montage_parallelism_values_are_saved_without_hidden_upper_limits(self):
        settings = Settings()
        with patch("scriptor.bridge.load_settings", return_value=settings), \
                patch("scriptor.bridge.save_settings"), \
                patch("scriptor.bridge.snapshot", return_value={}):
            bridge.save_montage_settings({
                "planningWorkers": 48,
                "downloadWorkers": 36,
                "renderWorkers": 24,
                "remotionFrameConcurrency": 20,
            })
        self.assertEqual(settings.montage_planning_workers, 48)
        self.assertEqual(settings.montage_download_workers, 36)
        self.assertEqual(settings.montage_render_workers, 24)
        self.assertEqual(settings.montage_remotion_frame_concurrency, 20)

    def test_fast_reuse_can_be_scoped_to_separate_one_based_topic_ranges(self):
        settings = Settings(montage_fast_reuse_enabled=True, montage_unique_footage_percent=35,
                            montage_fast_reuse_ranges=[
                                {"start": 1, "end": 3, "percent": 13},
                                {"start": 7, "end": 8, "percent": 20},
                            ])
        self.assertEqual(bridge._fast_reuse_percent_for_scenario(settings, 0), 13)
        self.assertEqual(bridge._fast_reuse_percent_for_scenario(settings, 2), 13)
        self.assertIsNone(bridge._fast_reuse_percent_for_scenario(settings, 3))
        self.assertEqual(bridge._fast_reuse_percent_for_scenario(settings, 6), 20)
        self.assertEqual(bridge._fast_reuse_percent_for_scenario(settings, 7), 20)

    def test_fast_reuse_without_ranges_applies_default_to_every_topic(self):
        settings = Settings(montage_fast_reuse_enabled=True, montage_unique_footage_percent=25)
        self.assertEqual(bridge._fast_reuse_percent_for_scenario(settings, 0), 25)
        self.assertEqual(bridge._fast_reuse_percent_for_scenario(settings, 100), 25)

    def test_fast_reuse_pool_excludes_fresh_source_after_unique_target(self):
        pooled = FootageItem("D:/pool/cached.mp4", "cached.mp4", tags=["oil-tanker-port"])
        fresh = FootageItem("D:/fresh/new.mp4", "new.mp4", tags=["oil-tanker-port"])
        levels = {
            "STRICT_MATCH": [
                SearchHit(fresh, .95, duration=12.0),
                SearchHit(pooled, .40, duration=12.0),
            ],
            "RELAXED_SEMANTIC": [],
            "CATEGORY_MATCH": [],
            "SAFE_CONTEXT": [],
        }
        reuse_pool = {
            bridge._montage_clip_key(pooled.path): TimelineClip(
                pooled.path, "voice", "oil tanker", duration=6.0, source_start=3.0,
            ),
        }

        filtered = bridge._fast_reuse_pool_hits(
            levels, reuse_pool, 6.0, source_duration=lambda _item: 12.0,
        )

        self.assertEqual([hit.item.path for hit in filtered["STRICT_MATCH"]], [pooled.path])

    def test_fast_reuse_pool_keeps_only_cached_windows_long_enough_for_beat(self):
        short_window = FootageItem("D:/pool/short.mp4", "short.mp4", tags=["oil-tanker-port"])
        valid_window = FootageItem("D:/pool/valid.mp4", "valid.mp4", tags=["oil-tanker-port"])
        levels = {
            "STRICT_MATCH": [
                SearchHit(short_window, .60, duration=10.0),
                SearchHit(valid_window, .50, duration=12.0),
            ],
            "RELAXED_SEMANTIC": [],
            "CATEGORY_MATCH": [],
            "SAFE_CONTEXT": [],
        }
        reuse_pool = {
            bridge._montage_clip_key(short_window.path): TimelineClip(
                short_window.path, "voice", "oil tanker", duration=6.0, source_start=5.0,
            ),
            bridge._montage_clip_key(valid_window.path): TimelineClip(
                valid_window.path, "voice", "oil tanker", duration=6.0, source_start=2.0,
            ),
        }
        durations = {short_window.path: 10.0, valid_window.path: 12.0}

        filtered = bridge._fast_reuse_pool_hits(
            levels, reuse_pool, 6.0, source_duration=lambda item: durations[item.path],
        )

        self.assertEqual([hit.item.path for hit in filtered["STRICT_MATCH"]], [valid_window.path])

    def test_interrupted_queue_is_recovered_without_deleting_its_source_data(self):
        settings = Settings()
        settings.montage_task_statuses = {
            "2": {"title": "Тест", "status": "Рендер", "progress": 72,
                  "timeline": [{"at": "10:00:00", "label": "Рендер", "progress": 72}]}
        }
        self.assertTrue(bridge._recover_interrupted_montage_tasks(settings))
        task = settings.montage_task_statuses["2"]
        self.assertEqual(task["status"], "Ошибка")
        self.assertEqual(task["phase"], "Предыдущий запуск остановлен")
        self.assertIn("остановлена", task["error"])
        self.assertEqual(task["title"], "Тест")

    def test_interrupted_text_check_stage_is_recovered_as_an_active_queue_task(self):
        settings = Settings()
        settings.montage_task_statuses = {
            "84": {
                "title": "Ручной сценарий",
                "status": "Проверка текста",
                "phase": "Проверка текста",
                "progress": 42,
                "queuePid": 999999,
            }
        }

        with patch.object(bridge, "_montage_process_is_running", return_value=False):
            self.assertTrue(bridge._recover_interrupted_montage_tasks(settings))

        task = settings.montage_task_statuses["84"]
        self.assertEqual(task["status"], "Ошибка")
        self.assertEqual(task["phase"], "Предыдущий запуск остановлен")

    def test_default_queue_skips_a_valid_ready_video(self):
        """Ordinary resume must never rebuild a completed, valid MP4."""
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "Готово.mp4"
            output.write_bytes(b"valid-video")
            settings = Settings()
            settings.montage_task_statuses = {
                "0": {"title": "Тест", "status": "Готово", "outputPath": str(output)},
                "1": {"title": "Ещё тема", "status": "Ошибка", "outputPath": ""},
            }
            with patch("scriptor.bridge._is_valid_montage_output", side_effect=lambda path: path == output):
                self.assertFalse(bridge._montage_task_needs_render(settings, 0))
                self.assertTrue(bridge._montage_task_needs_render(settings, 1))

    def test_ready_output_check_uses_mp4_header_without_starting_ffprobe(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "Готово.mp4"
            output.write_bytes(b"\x00\x00\x00\x18ftypisom" + b"x" * 2048)
            with patch("scriptor.bridge.probe_media_duration", side_effect=AssertionError("ffprobe must not start")):
                self.assertTrue(bridge._is_valid_montage_output(output))

    def test_reconcile_stale_render_with_valid_output_as_ready(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "Готово.mp4"
            output.write_bytes(b"valid-video")
            settings = Settings()
            settings.montage_task_statuses = {
                "5": {"title": "Тест", "status": "Рендер", "outputPath": str(output)},
            }
            with patch("scriptor.bridge._is_valid_montage_output", side_effect=lambda path: path == output):
                self.assertTrue(bridge._reconcile_montage_outputs(settings, force_interrupted=True))
            task = settings.montage_task_statuses["5"]
            self.assertEqual(task["status"], "Готово")
            self.assertEqual(task["phase"], "MP4 восстановлен")

    def test_reconcile_reattaches_registered_valid_mp4_when_task_path_is_stale(self):
        """A durable registered output is authoritative over an old task path."""
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            stale = root / "old" / "Тема.mp4"
            recovered = root / "moved" / "Тема.mp4"
            recovered.parent.mkdir()
            recovered.write_bytes(b"\x00\x00\x00\x18ftypisom" + b"x" * 2048)
            settings = Settings()
            settings.montage_task_statuses = {
                "5": {"title": "Тема", "status": "Ошибка", "phase": "MP4 не найден",
                      "outputPath": str(stale), "voicePath": str(root / "voice.mp3")},
            }
            settings.pipeline_montage_outputs = [str(stale), str(recovered)]

            self.assertTrue(bridge._reconcile_montage_outputs(settings))

            task = settings.montage_task_statuses["5"]
            self.assertEqual(task["status"], "Готово")
            self.assertEqual(task["outputPath"], str(recovered))
            self.assertEqual(settings.pipeline_montage_outputs, [str(stale), str(recovered)])

    def test_reconcile_keeps_missing_registered_output_for_publication_recovery(self):
        """A missing MP4 is a recoverable reference, never a reason to erase the production record."""
        settings = Settings()
        missing = "D:/missing/episode.mp4"
        settings.pipeline_montage_outputs = [missing]

        bridge._reconcile_montage_outputs(settings)

        self.assertEqual(settings.pipeline_montage_outputs, [str(Path(missing))])

    def test_task_update_persists_a_visible_timeline_and_keeps_external_pause(self):
        worker_settings = Settings()
        latest_settings = Settings(montage_queue_paused=True)
        with patch("scriptor.bridge.load_settings", return_value=latest_settings), \
                patch("scriptor.bridge.save_settings") as save:
            bridge._montage_task_update(
                worker_settings, 4, status="Подбор футажей", phase="Подбор футажей",
                progress=42, detail="Сцена 2/8: tanker.mp4", title="Тестовая тема",
            )
        task = worker_settings.montage_task_statuses["4"]
        self.assertTrue(worker_settings.montage_queue_paused)
        self.assertEqual(task["status"], "Подбор футажей")
        self.assertEqual(task["progress"], 42)
        self.assertEqual(task["timeline"][-1]["detail"], "Сцена 2/8: tanker.mp4")
        save.assert_called_once_with(worker_settings)

    def test_montage_task_runtime_provenance_distinguishes_current_and_legacy_evidence(self):
        settings = Settings()
        with patch.dict(os.environ, {"NEWSFLOW_RUNTIME_SESSION_ID": "desktop-session-a"}), \
             patch("scriptor.bridge.load_settings", return_value=settings), \
             patch("scriptor.bridge.save_settings"):
            bridge._montage_task_update(
                settings, 4, status="Ошибка", phase="Ошибка подготовки",
                progress=100, error="No module named 'fastembed'",
            )
            current = bridge._montage_task_snapshot_projection(
                "4", settings.montage_task_statuses["4"],
            )

        self.assertTrue(current["runtimeCurrent"])
        self.assertEqual(current["runtimeProvenance"], "current-session")
        self.assertNotIn("runtimeSessionId", current)

        with patch.dict(os.environ, {"NEWSFLOW_RUNTIME_SESSION_ID": "desktop-session-b"}):
            previous = bridge._montage_task_snapshot_projection(
                "4", settings.montage_task_statuses["4"],
            )
        self.assertFalse(previous["runtimeCurrent"])
        self.assertEqual(previous["runtimeProvenance"], "previous-session")

        legacy = bridge._montage_task_snapshot_projection(
            "5", {"status": "Ошибка", "error": "historical"},
        )
        self.assertFalse(legacy["runtimeCurrent"])
        self.assertEqual(legacy["runtimeProvenance"], "legacy-unattributed")

    def test_render_update_records_heartbeat_and_render_start(self):
        settings = Settings()
        with patch("scriptor.bridge.load_settings", return_value=settings), \
                patch("scriptor.bridge.save_settings"):
            bridge._montage_task_update(
                settings, 4, status="Рендер", phase="Подготовка рендера", progress=60,
                detail="FFmpeg запускается", ffmpegPid=12345,
            )
        task = settings.montage_task_statuses["4"]
        self.assertEqual(task["ffmpegPid"], 12345)
        self.assertTrue(task["renderStartedAt"])
        self.assertTrue(task["lastHeartbeatAt"])
        self.assertTrue(task["lastProgressAt"])

    def test_only_transient_render_failures_are_retried(self):
        self.assertTrue(bridge._is_retryable_montage_error("WinError 32: file is busy"))
        self.assertTrue(bridge._is_retryable_montage_error("FFmpeg timed out while saving"))
        self.assertTrue(bridge._is_retryable_montage_error("Таймлайн футажей короче озвучки на 3.0 сек"))
        self.assertTrue(bridge._is_retryable_montage_error("Футаж не найден: D:\\missing.mp4"))

    def test_stale_cover_save_cannot_revert_newer_montage_render_status(self):
        """A parallel non-montage worker must not roll a rendered row back to footage.

        The long cover worker keeps its own Settings instance.  Before the
        regression fix, its next whole-file save replaced the newer montage
        progress written by the montage worker.
        """
        with tempfile.TemporaryDirectory() as folder:
            settings_path = Path(folder) / "settings.json"
            stale_cover_settings = Settings()
            stale_cover_settings.montage_task_statuses = {
                "0": {"status": "Подбор футажей", "phase": "Подбор футажей",
                      "progress": 45, "updatedAt": "2026-09-09 10:19:48"}
            }
            montage_settings = Settings()
            montage_settings.montage_task_statuses = {
                "0": {"status": "Рендер", "phase": "Склейка",
                      "progress": 97, "updatedAt": "2026-09-09 10:26:45"}
            }
            with patch.object(config, "config_path", return_value=settings_path):
                config.save_settings(montage_settings)
                config.save_settings(stale_cover_settings)
                persisted = config.load_settings().montage_task_statuses["0"]
            self.assertEqual(persisted["status"], "Рендер")
            self.assertEqual(persisted["phase"], "Склейка")
            self.assertEqual(persisted["progress"], 97)

    def test_montage_save_cannot_revert_a_newer_cover_status(self):
        """A background renderer must not hide a cover that just finished."""
        with tempfile.TemporaryDirectory() as folder:
            settings_path = Path(folder) / "settings.json"
            stale_montage_settings = Settings(cover_queue=[{
                "scenario_index": 1, "title": "Тема", "status": "Подготовка запросов",
                "progress": 10, "updatedAt": "2026-09-09T10:00:00.000000",
            }])
            completed_cover_settings = Settings(cover_queue=[{
                "scenario_index": 1, "title": "Тема", "status": "Готово",
                "progress": 100, "path": "D:/cover.png",
                "updatedAt": "2026-09-09T10:00:01.000000",
            }])
            with patch.object(config, "config_path", return_value=settings_path):
                config.save_settings(stale_montage_settings)
                config.save_settings(completed_cover_settings)
                config.save_settings(stale_montage_settings)
                persisted = config.load_settings().cover_queue[0]
            self.assertEqual(persisted["status"], "Готово")
            self.assertEqual(persisted["path"], "D:/cover.png")

    def test_stale_worker_cannot_drop_newly_added_openai_keys(self):
        """Saving old queue state must preserve API keys added in the UI."""
        with tempfile.TemporaryDirectory() as folder:
            settings_path = Path(folder) / "settings.json"
            stale = Settings(openai_api_keys=[OpenAIKey("Первый", "key-one", True)])
            updated = Settings(openai_api_keys=[
                OpenAIKey("Первый", "key-one", True),
                OpenAIKey("Второй", "key-two", True),
            ])
            with patch.object(config, "config_path", return_value=settings_path):
                config.save_settings(stale)
                config.save_settings(updated)
                config.save_settings(stale)
                persisted = config.load_settings()
            self.assertEqual([key.secret for key in persisted.openai_api_keys], ["key-one", "key-two"])

    def test_stale_worker_cannot_erase_persisted_production_state(self):
        """An old detached worker must never replace a completed release with blanks."""
        with tempfile.TemporaryDirectory() as folder:
            settings_path = Path(folder) / "settings.json"
            completed = Settings(
                idea_results=[{"title": "Готовый сценарий", "script": "Текст"}],
                idea_production_items=[{"id": "production:1", "title": "Готовый сценарий"}],
                voice_scenario_outputs={"0": "D:/voices/0001.mp3"},
                pipeline_montage_outputs=["D:/videos/0001.mp4"],
                seo_queue=[{"scenario_index": 0, "title": "Готовый сценарий"}],
            )
            stale_worker = Settings()
            with patch.object(config, "config_path", return_value=settings_path):
                config.save_settings(completed)
                config.save_settings(stale_worker)
                persisted = config.load_settings()

            self.assertEqual(persisted.idea_results, completed.idea_results)
            self.assertEqual(persisted.idea_production_items, completed.idea_production_items)
            self.assertEqual(persisted.voice_scenario_outputs, completed.voice_scenario_outputs)
            self.assertEqual(persisted.pipeline_montage_outputs, completed.pipeline_montage_outputs)
            self.assertEqual(persisted.seo_queue, completed.seo_queue)

    def test_production_clear_requires_a_typed_confirmation_phrase(self):
        """A stale UI action with only a boolean must never erase work folders."""
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            settings = Settings(
                output_folder=str(root / "output"),
                voicer_output_folder=str(root / "voices"),
                cover_output_folder=str(root / "covers"),
                seo_output_folder=str(root / "seo"),
                media_output_folder=str(root / "media"),
                cutter_output_folder=str(root / "cuts"),
                footage_download_folder=str(root / "downloads"),
                mixer_output_folder=str(root / "mix"),
                montage_output_folder=str(root / "mp4"),
                montage_project_folder=str(root / "projects"),
            )
            protected_video = root / "mp4" / "keep.mp4"
            protected_video.parent.mkdir()
            protected_video.write_bytes(b"keep")
            with patch("scriptor.bridge.load_settings", return_value=settings), \
                 self.assertRaisesRegex(ValueError, "контрольную фразу"):
                bridge.clear_production_queue({"confirmed": True})
            self.assertTrue(protected_video.exists())

    def test_settings_save_creates_an_independent_recovery_snapshot(self):
        """A future faulty write must leave a readable pre-write state behind."""
        with tempfile.TemporaryDirectory() as folder:
            settings_path = Path(folder) / "settings.json"
            settings = Settings(idea_results=[{"title": "Сценарий"}])
            with patch.object(config, "config_path", return_value=settings_path):
                config.save_settings(settings)
                changed = Settings(idea_results=[{"title": "Новый сценарий"}])
                config.save_settings(changed)

            archives = sorted((Path(folder) / "state-backups").glob("settings-*.json"))
            self.assertTrue(archives)
            archived = __import__("json").loads(archives[-1].read_text(encoding="utf-8"))
            self.assertEqual(archived["idea_results"], settings.idea_results)

    def test_temp_cover_output_is_migrated_to_the_permanent_library(self):
        """A disposable test/snapshot directory must never become a production cover path."""
        temporary = str(Path(tempfile.gettempdir()) / "tmp-newsflow-cover-test" / "covers")
        with patch.object(config, "storyflow_documents_root", return_value=Path("D:/NewsFlow Studio")):
            migrated = config.migrate_standard_folder(temporary, "Обложки", "Обложки")
        self.assertEqual(migrated, "D:\\NewsFlow Studio\\Обложки")

    def test_remove_result_never_touches_source_audio_or_outside_file(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            output = root / "MP4"
            output.mkdir()
            generated = output / "Тема.mp4"
            generated.write_bytes(b"generated")
            source = root / "voice.mp3"
            source.write_bytes(b"voice")
            outside = root / "outside.mp4"
            outside.write_bytes(b"keep")
            settings = Settings(montage_output_folder=str(output))
            settings.pipeline_montage_outputs = [str(generated), str(outside)]
            settings.montage_task_statuses = {
                "1": {"title": "Тема", "outputPath": str(generated), "voicePath": str(source)}
            }
            bridge._remove_montage_output(settings, 1)
            self.assertFalse(generated.exists())
            self.assertTrue(source.exists())
            self.assertTrue(outside.exists())
            self.assertNotIn(str(generated), settings.pipeline_montage_outputs)
            self.assertIn(str(outside), settings.pipeline_montage_outputs)

    def test_remove_all_montage_results_resets_render_history_without_touching_inputs(self):
        """Bulk MP4 cleanup makes rows ready for a new render without deleting inputs."""
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            output = root / "MP4"
            output.mkdir()
            first = output / "Первый.mp4"
            second = output / "Второй.mp4"
            first.write_bytes(b"first-render")
            second.write_bytes(b"second-render")
            voice = root / "voice.mp3"
            footage = root / "source.mp4"
            outside = root / "outside.mp4"
            voice.write_bytes(b"voice")
            footage.write_bytes(b"footage")
            outside.write_bytes(b"outside")
            settings = Settings(montage_output_folder=str(output))
            settings.pipeline_montage_outputs = [str(first), str(second), str(outside)]
            settings.montage_task_statuses = {
                "1": {"title": "Первый", "status": "Готово", "outputPath": str(first), "voicePath": str(voice), "sourcePath": str(footage)},
                "2": {"title": "Второй", "status": "Готово", "outputPath": str(second), "voicePath": str(voice), "sourcePath": str(footage)},
            }

            with patch("scriptor.bridge.load_settings", return_value=settings), \
                    patch("scriptor.bridge.save_settings"), \
                    patch("scriptor.bridge.snapshot", return_value={}):
                result = bridge.remove_montage_results({"all": True, "resetHistory": True})

            self.assertEqual(result["operationResult"]["count"], 2)
            self.assertFalse(first.exists())
            self.assertFalse(second.exists())
            self.assertTrue(voice.exists())
            self.assertTrue(footage.exists())
            self.assertTrue(outside.exists())
            self.assertEqual(settings.pipeline_montage_outputs, [str(outside)])
            self.assertTrue(all(item["status"] == "Готов к монтажу" and not item["outputPath"]
                                and not item["error"]
                                and item["timeline"][-1]["label"] == "MP4 и история очищены"
                                for item in settings.montage_task_statuses.values()))

            bridge._reconcile_montage_outputs(settings)
            self.assertTrue(all(item["status"] == "Готов к монтажу"
                                for item in settings.montage_task_statuses.values()))

    def test_remove_all_montage_results_resets_failed_row_without_an_output_file(self):
        """A prior renderer error must not survive an explicit full reset."""
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            output = root / "MP4"
            output.mkdir()
            voice = root / "voice.mp3"
            voice.write_bytes(b"voice")
            settings = Settings(montage_output_folder=str(output))
            settings.montage_task_statuses = {
                "5": {
                    "title": "Ошибка рендера", "status": "Ошибка", "phase": "Ошибка рендера",
                    "progress": 100, "voicePath": str(voice), "outputPath": "",
                    "error": "FFmpeg failed", "timeline": [{"label": "Ошибка рендера"}],
                },
            }

            with patch("scriptor.bridge.load_settings", return_value=settings), \
                    patch("scriptor.bridge.save_settings"), \
                    patch("scriptor.bridge.snapshot", return_value={}):
                result = bridge.remove_montage_results({"all": True, "resetHistory": True})

            self.assertEqual(result["operationResult"]["count"], 1)
            item = settings.montage_task_statuses["5"]
            self.assertEqual(item["status"], "Готов к монтажу")
            self.assertEqual(item["error"], "")
            self.assertEqual(item["timeline"][-1]["label"], "MP4 и история очищены")

    def test_remove_project_keeps_rendered_mp4_and_media(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            projects = root / "projects"
            output = root / "MP4"
            projects.mkdir(); output.mkdir()
            project = projects / "Тема.newsflow"
            project.write_text("{}", encoding="utf-8")
            remotion = output / "Тема.remotion.json"
            remotion.write_text("{}", encoding="utf-8")
            video = output / "Тема.mp4"
            video.write_bytes(b"video")
            voice = root / "voice.mp3"
            voice.write_bytes(b"voice")
            settings = Settings(montage_project_folder=str(projects), montage_output_folder=str(output))
            with patch("scriptor.bridge.load_settings", return_value=settings), \
                    patch("scriptor.bridge.snapshot", return_value={}):
                result = bridge.remove_montage_projects({"paths": [str(project)]})
            self.assertEqual(result["operationResult"]["count"], 1)
            self.assertFalse(project.exists())
            self.assertFalse(remotion.exists())
            self.assertTrue(video.exists())
            self.assertTrue(voice.exists())


    def test_clear_production_writes_scenario_tombstone_fence_before_empty_session(self):
        """A crash between settings/session writes must not revive the old batch."""
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            settings = Settings(
                output_folder=str(root / "output"),
                voicer_output_folder=str(root / "voices"),
                cover_output_folder=str(root / "covers"),
                seo_output_folder=str(root / "seo"),
                media_output_folder=str(root / "media"),
                cutter_output_folder=str(root / "cuts"),
                footage_download_folder=str(root / "downloads"),
                mixer_output_folder=str(root / "mix"),
                montage_output_folder=str(root / "mp4"),
                montage_project_folder=str(root / "projects"),
                idea_results=["Старый сценарий"],
                cover_queue=[{"title": "Старый сценарий"}],
            )
            titles = ["Старый сценарий", "Legacy без ID"]
            jobs = [
                Job(ScenarioRequest(0, titles[0], "", "production-old"),
                    RunState.DONE, "Текст", ""),
                Job(ScenarioRequest(1, titles[1], "", ""),
                    RunState.DONE, "Legacy text", ""),
            ]
            events = []

            def save_settings_probe(value):
                events.append((
                    "settings",
                    list(value.deleted_scenario_titles),
                    list(value.deleted_scenario_production_ids),
                ))

            def crash_before_empty_session(_titles, _jobs):
                events.append(("session", [], []))
                raise RuntimeError("simulated crash after durable reset fence")

            def cleanup_probe(_folder):
                events.append(("cleanup", [], []))
                return 0

            with patch.object(bridge, "load_settings", return_value=settings), \
                 patch.object(bridge, "load_session", return_value=(titles, jobs)), \
                 patch.object(bridge, "_clear_production_folder", side_effect=cleanup_probe), \
                 patch.object(bridge, "save_settings", side_effect=save_settings_probe), \
                 patch.object(bridge, "save_session", side_effect=crash_before_empty_session), \
                 self.assertRaisesRegex(RuntimeError, "simulated crash"):
                bridge.clear_production_queue({
                    "confirmed": True,
                    "confirmationPhrase": "УДАЛИТЬ ПРОИЗВОДСТВО",
                })

            self.assertEqual([event[0] for event in events], ["settings", "session"])
            self.assertNotIn("cleanup", [event[0] for event in events])
            self.assertIn("старый сценарий", events[0][1])
            self.assertIn("legacy без id", events[0][1])
            self.assertIn("production-old", events[0][2])

    def test_clear_production_persists_logical_reset_before_file_cleanup(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            settings = Settings(
                output_folder=str(root / "output"),
                voicer_output_folder=str(root / "voices"),
                cover_output_folder=str(root / "covers"),
                seo_output_folder=str(root / "seo"),
                media_output_folder=str(root / "media"),
                cutter_output_folder=str(root / "cuts"),
                footage_download_folder=str(root / "downloads"),
                mixer_output_folder=str(root / "mix"),
                montage_output_folder=str(root / "mp4"),
                montage_project_folder=str(root / "projects"),
            )
            titles = ["Сценарий"]
            jobs = [Job(
                ScenarioRequest(0, titles[0], "", "prod-reset"),
                RunState.DONE, "Текст", "",
            )]
            events = []

            with patch.object(bridge, "load_settings", return_value=settings), \
                 patch.object(bridge, "load_session", return_value=(titles, jobs)), \
                 patch.object(bridge, "save_settings", side_effect=lambda _value: events.append("settings")), \
                 patch.object(bridge, "save_session", side_effect=lambda _titles, _jobs: events.append("session")), \
                 patch.object(bridge, "_clear_production_folder",
                              side_effect=lambda _folder: (events.append("cleanup") or 0)), \
                 patch.object(bridge, "snapshot", return_value={}):
                bridge.clear_production_queue({
                    "confirmed": True,
                    "confirmationPhrase": "УДАЛИТЬ ПРОИЗВОДСТВО",
                })

            self.assertGreater(events.count("cleanup"), 0)
            self.assertEqual(events[:2], ["settings", "session"])
            self.assertTrue(all(event == "cleanup" for event in events[2:]))

    def test_clear_production_crash_before_session_write_cannot_restore_old_batch(self):
        """Exact reset crash window: durable fence wins over the stale primary."""
        from scriptor.session import load_session as reload_session
        from scriptor.session import save_session as persist_session

        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {"LOCALAPPDATA": folder}):
            root = Path(folder) / "media"
            titles = ["Сценарий 1", "Сценарий 2"]
            jobs = [
                Job(ScenarioRequest(0, titles[0], "", "prod-1"), RunState.DONE, "Текст 1", ""),
                Job(ScenarioRequest(1, titles[1], "", ""), RunState.DONE, "Legacy text", ""),
            ]
            settings = Settings(
                output_folder=str(root / "output"),
                voicer_output_folder=str(root / "voices"),
                cover_output_folder=str(root / "covers"),
                seo_output_folder=str(root / "seo"),
                media_output_folder=str(root / "media"),
                cutter_output_folder=str(root / "cuts"),
                footage_download_folder=str(root / "downloads"),
                mixer_output_folder=str(root / "mix"),
                montage_output_folder=str(root / "mp4"),
                montage_project_folder=str(root / "projects"),
                idea_results=list(titles),
                cover_queue=[{"title": title} for title in titles],
            )
            config.save_settings(settings)
            persist_session(titles, jobs)

            with patch.object(bridge, "_clear_production_folder", return_value=0), \
                 patch.object(
                     bridge, "save_session",
                     side_effect=RuntimeError("simulated crash before session empty write"),
                 ), \
                 self.assertRaisesRegex(RuntimeError, "simulated crash"):
                bridge.clear_production_queue({
                    "confirmed": True,
                    "confirmationPhrase": "УДАЛИТЬ ПРОИЗВОДСТВО",
                })

            # The physical primary still contains the old jobs, exactly like a
            # crash between settings and session writes. Tombstones must make
            # the restart projection empty nevertheless.
            restored_titles, restored_jobs = reload_session()
            self.assertEqual((restored_titles, restored_jobs), ([], []))
            restored_settings = config.load_settings()
            self.assertIn("сценарий 1", restored_settings.deleted_scenario_titles)
            self.assertIn("сценарий 2", restored_settings.deleted_scenario_titles)
            self.assertIn("prod-1", restored_settings.deleted_scenario_production_ids)

class MontagePreferencesPersistenceTests(unittest.TestCase):
    def setUp(self):
        root = self.enterContext(TemporaryDirectory(prefix="newsflow-montage-preferences-"))
        self.enterContext(patch.dict(os.environ, {
            "NEWSFLOW_TEST_MODE": "1", "NEWSFLOW_TEST_ROOT": root,
            "LOCALAPPDATA": root,
            "NEWSFLOW_PRODUCTION_LOCALAPPDATA": str(Path(root) / "untouched-production"),
        }))
        self.enterContext(patch.object(config, "gpu_timeline_available", return_value=False))
        # Only suppress the unrelated full UI snapshot; settings IO and the
        # command's validation/normalisation stay real.
        self.enterContext(patch.object(bridge, "snapshot", return_value={}))
        config.save_settings(config.Settings(montage_renderer="ffmpeg", montage_renderer_explicit=True))

    def test_gpu_chunk_size_round_trip_and_stale_progress_preservation(self):
        self.assertEqual(getattr(config.load_settings(), "montage_gpu_chunk_size", None), 12)
        worker = config.load_settings()
        for size in (24, 37, 12, 1):
            bridge.save_montage_settings({"gpuChunkSize": size})
            self.assertEqual(config.load_settings().montage_gpu_chunk_size, size)
            bridge._montage_task_update(worker, 0, status="Рендер", progress=65)
            self.assertEqual(config.load_settings().montage_gpu_chunk_size, size)
        # Running workers keep their original configuration; only future renders change.
        self.assertEqual(worker.montage_gpu_chunk_size, 12)

    def test_old_profile_without_gpu_block_setting_defaults_to_12(self):
        path = config.config_path()
        data = json.loads(path.read_text(encoding="utf-8"))
        data.pop("montage_gpu_chunk_size", None)
        path.write_text(json.dumps(data), encoding="utf-8")
        loaded = config.load_settings()
        self.assertEqual(loaded.montage_gpu_chunk_size, 12)
        bridge.save_montage_settings({"renderWorkers": 3})
        self.assertEqual(config.load_settings().montage_gpu_chunk_size, 12)

    def test_invalid_gpu_chunk_size_rejects_entire_settings_save(self):
        original = config.config_path().read_bytes()
        for value in (0, -1, 2.5, True, None, "", "oops", "12.5", 9007199254740992):
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, "Футажей в блоке"):
                    bridge.save_montage_settings({"gpuChunkSize": value, "renderWorkers": 17})
                self.assertEqual(config.config_path().read_bytes(), original)

    def test_saved_project_render_receives_current_gpu_block_size(self):
        root = config.app_data_root()
        project_path = root / "saved.newsflow"
        TimelineProject("Saved plan", clips=[TimelineClip("unused.mp4", "n", "q")]).save(project_path)
        bridge.save_montage_settings({"gpuChunkSize": 37, "renderer": "gpu-timeline"})

        def stop_at_render(_project, _output, **options):
            self.assertEqual(options.get("gpu_chunk_size"), 37)
            self.assertEqual(options["renderer"], "gpu-timeline")
            raise RuntimeError("render boundary checked")

        with patch.object(bridge, "render_project", side_effect=stop_at_render), \
             self.assertRaisesRegex(RuntimeError, "render boundary checked"):
            bridge.render_montage({"projectPath": str(project_path)})

    def save_preferences(self, percent=50, enabled=True, ranges=None):
        bridge.save_montage_settings({
            "fastReuseEnabled": enabled, "uniqueFootagePercent": percent,
            "fastReuseRanges": [] if ranges is None else ranges,
        })

    def test_progress_preserves_saved_50_percent_and_manual_pause(self):
        worker = config.load_settings()
        self.save_preferences()
        bridge.save_montage_settings({"queuePaused": True})

        for progress in (43, 44, 45):
            bridge._montage_task_update(worker, 0, status="Подбор футажей", progress=progress,
                                        detail=f"Scene {progress}", production_item_id="pi-unique")
            saved = config.load_settings()
            self.assertTrue(saved.montage_fast_reuse_enabled)
            self.assertEqual(saved.montage_unique_footage_percent, 50)
            self.assertTrue(saved.montage_queue_paused)
            self.assertEqual(saved.montage_task_statuses["0"]["progress"], progress)
            self.assertEqual(saved.montage_task_statuses["0"]["production_item_id"], "pi-unique")
            self.assertEqual(saved.montage_task_statuses["0"]["timeline"][-1]["detail"], f"Scene {progress}")
        # Persistence must not hot-swap an already preparing worker's inputs.
        self.assertFalse(worker.montage_fast_reuse_enabled)
        self.assertEqual(worker.montage_unique_footage_percent, 100)

    def test_stale_full_profile_saves_preserve_pause_and_explicit_continue_wins(self):
        workers = [config.load_settings(), config.load_settings()]
        bridge.save_montage_settings({"queuePaused": True})

        workers[0].montage_recent_clip_paths.append("synthetic-stale-clip.mp4")
        workers[1].pipeline_montage_outputs = ["synthetic-stale-output.mp4"]
        for worker in workers:
            config.save_settings(worker)
            self.assertTrue(config.load_settings().montage_queue_paused)

        bridge.save_montage_settings({"queuePaused": False})
        self.assertFalse(config.load_settings().montage_queue_paused)
        for worker in workers:
            config.save_settings(worker)
            self.assertFalse(config.load_settings().montage_queue_paused)

    def test_repeated_operator_pause_and_continue_remain_explicitly_writable(self):
        for paused in (True, True, False, False, True, False):
            bridge.save_montage_settings({"queuePaused": paused})
            self.assertEqual(config.load_settings().montage_queue_paused, paused)

    def test_project_and_queue_saves_preserve_ranges_and_write_results(self):
        workers = [config.load_settings(), config.load_settings()]
        self.save_preferences(ranges=[{"start": 1, "end": 12, "percent": 50}])
        workers[0].pipeline_montage_outputs = ["synthetic-first.mp4"]
        workers[1].pipeline_montage_outputs = ["synthetic-second.mp4"]

        for worker in workers * 2:
            config.save_settings(worker)
            saved = config.load_settings()
            self.assertTrue(saved.montage_fast_reuse_enabled)
            self.assertEqual(saved.montage_unique_footage_percent, 50)
            self.assertEqual(saved.montage_fast_reuse_ranges, [{"start": 1, "end": 12, "percent": 50}])
            self.assertEqual(saved.pipeline_montage_outputs, worker.pipeline_montage_outputs)

    def test_in_place_range_edit_is_persisted_without_reverting_newer_percent(self):
        self.save_preferences(ranges=[{"start": 1, "end": 12, "percent": 50}])
        editor = config.load_settings()
        self.save_preferences(percent=75, ranges=[{"start": 1, "end": 12, "percent": 50}])
        editor.montage_fast_reuse_ranges[0]["percent"] = 25
        config.save_settings(editor)
        saved = config.load_settings()
        self.assertEqual(saved.montage_unique_footage_percent, 75)
        self.assertEqual(saved.montage_fast_reuse_ranges, [{"start": 1, "end": 12, "percent": 25}])

    def test_saved_instance_cannot_repeat_its_previous_edit_over_a_newer_edit(self):
        editor = config.load_settings()
        editor.montage_fast_reuse_enabled = True
        editor.montage_unique_footage_percent = 50
        config.save_settings(editor)
        self.save_preferences(percent=75)
        config.save_settings(editor)
        self.assertEqual(config.load_settings().montage_unique_footage_percent, 75)

    def test_explicit_newer_disable_100_and_empty_ranges_survive_old_worker(self):
        self.save_preferences(ranges=[{"start": 1, "end": 84, "percent": 50}])
        worker = config.load_settings()
        self.save_preferences(percent=100, enabled=False)
        config.save_settings(worker)
        saved = config.load_settings()
        self.assertFalse(saved.montage_fast_reuse_enabled)
        self.assertEqual(saved.montage_unique_footage_percent, 100)
        self.assertEqual(saved.montage_fast_reuse_ranges, [])

    def test_explicit_command_wins_even_when_value_equals_its_loaded_baseline(self):
        # A second operator saves after the command read but before its write.
        # The explicit command still owns the field present in its payload.
        editor = config.load_settings()
        self.save_preferences()
        with patch.object(bridge, "load_settings", return_value=editor):
            bridge.save_montage_settings({"uniqueFootagePercent": 100})
        saved = config.load_settings()
        self.assertEqual(saved.montage_unique_footage_percent, 100)
        self.assertTrue(saved.montage_fast_reuse_enabled)

    def test_merge_reads_preferences_inside_the_exclusive_write_lock(self):
        from contextlib import contextmanager

        worker = config.load_settings()
        lock = config._exclusive_settings_write

        @contextmanager
        def edit_then_lock(path):
            self.save_preferences()
            with lock(path):
                yield

        def save_operator(settings):
            # Avoid recursion only for the independent operator write.
            with patch.object(config, "_exclusive_settings_write", lock):
                config.save_settings(settings)

        with patch.object(config, "_exclusive_settings_write", side_effect=edit_then_lock), \
                patch.object(bridge, "save_settings", side_effect=save_operator):
            config.save_settings(worker)
        self.assertEqual(config.load_settings().montage_unique_footage_percent, 50)

    def test_independent_operator_process_survives_old_worker_progress(self):
        worker = config.load_settings()
        subprocess.run([sys.executable, "-c", """
from scriptor import config, bridge
config._GPU_TIMELINE_AVAILABLE = False
bridge.snapshot = lambda: {}
bridge.save_montage_settings({'fastReuseEnabled': True, 'uniqueFootagePercent': 50})
"""], cwd=Path(__file__).resolve().parents[1], check=True, capture_output=True, timeout=30)
        bridge._montage_task_update(worker, 0, status="Подбор футажей", progress=44)
        saved = config.load_settings()
        self.assertTrue(saved.montage_fast_reuse_enabled)
        self.assertEqual(saved.montage_unique_footage_percent, 50)

    def test_failed_write_does_not_consume_pending_edit(self):
        editor = config.load_settings()
        editor.montage_unique_footage_percent = 50
        with patch.object(config.os, "replace", side_effect=OSError("Synthetic disk failure")), \
                self.assertRaises(OSError):
            config.save_settings(editor)
        self.assertEqual(config.load_settings().montage_unique_footage_percent, 100)
        config.save_settings(editor)
        self.assertEqual(config.load_settings().montage_unique_footage_percent, 50)
        self.assertEqual(list(config.config_path().parent.glob(".settings.json.*.tmp")), [])

    def test_key_edit_on_legacy_profile_does_not_require_reuse_fields(self):
        bridge.add_api_key({"kind": "openai", "label": "Synthetic", "secret": "synthetic-old"})
        path = config.config_path()
        legacy = json.loads(path.read_text(encoding="utf-8"))
        for name in ("montage_fast_reuse_enabled", "montage_unique_footage_percent", "montage_fast_reuse_ranges"):
            legacy.pop(name)
        legacy["unknown_operator_setting"] = "retain"
        path.write_text(json.dumps(legacy), encoding="utf-8")

        bridge.update_api_key({
            "kind": "openai", "index": 0, "label": "Synthetic", "secret": "synthetic-new",
            "fingerprint": bridge._api_key_fingerprint("synthetic-old"),
            "revision": hashlib.sha256(b"synthetic-old\0Synthetic").hexdigest(),
        })

        saved = config.load_settings()
        self.assertEqual(saved.openai_api_keys[0].secret, "synthetic-new")
        persisted = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(persisted["unknown_operator_setting"], "retain")
        self.assertNotIn("montage_unique_footage_percent", persisted)


if __name__ == "__main__":
    unittest.main()

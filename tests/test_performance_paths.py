"""Fast, local performance regressions measured against deterministic inputs."""
from __future__ import annotations

import asyncio
import time
import unittest

from scriptor import bridge
from scriptor.core import ScenarioRequest, build_requests
from scriptor.footage import FootageItem, rank_items
from scriptor.runner import ParallelRunner, RunState, scenario_length_status
from scriptor.timeline import fit_scene_plan_to_voice_duration
from scriptor.youtube_publisher import create_publication_job
from tests.performance_baselines import classify_duration, load_performance_baselines


class LocalPerformancePathTests(unittest.TestCase):
    def _assert_hard_budget(self, metric: str, elapsed: float) -> None:
        status = classify_duration(load_performance_baselines()[metric], elapsed)
        print(f"PERFORMANCE_METRIC metric={metric} elapsedSeconds={elapsed:.6f} status={status}")
        self.assertNotEqual("HARD_REGRESSION", status, f"{metric} took {elapsed:.3f}s")

    def test_idea_and_script_local_processing_stay_within_hard_budgets(self):
        started = time.perf_counter()
        requests = build_requests(
            [f"Тема {index}" for index in range(100)],
            "Сценарий по теме {title}",
            [],
        )
        idea_elapsed = time.perf_counter() - started

        started = time.perf_counter()
        for request in requests:
            self.assertEqual(("READY", 17), scenario_length_status(
                ScenarioRequest(request.index, request.title, request.prompt, allowed_min=10, allowed_max=20),
                "готовый текст тут",
            ))
        script_elapsed = time.perf_counter() - started

        self._assert_hard_budget("idea-local-processing", idea_elapsed)
        self._assert_hard_budget("script-validation", script_elapsed)

    def test_footage_selection_stays_within_hard_budget(self):
        items = [
            FootageItem(f"C:/golden/{index}.mp4", f"tanker-{index}.mp4", tags=["иран", "танкер", "море"])
            for index in range(300)
        ]
        started = time.perf_counter()
        ranked = rank_items("Иран танкер море", items)
        elapsed = time.perf_counter() - started

        self.assertEqual(300, len(ranked))
        self._assert_hard_budget("footage-search-selection", elapsed)

    def test_cover_prompt_and_publication_preparation_stay_within_hard_budgets(self):
        item = {
            "title": "Ормуз: давление на нефтяные маршруты",
            "cover_headline": "ОРМУЗ НА ГРАНИ",
            "cover_subheadline": "ТАНКЕРЫ ПОД ДАВЛЕНИЕМ",
        }
        started = time.perf_counter()
        prompt = bridge._normalize_cover_photo_prompt("Oil tankers under pressure near Hormuz.", item)
        cover_elapsed = time.perf_counter() - started

        started = time.perf_counter()
        job = create_publication_job(
            video_path="D:/golden/ormuz.mp4",
            package_folder="D:/golden",
            title="Ормуз: давление на нефтяные маршруты",
            thumbnail_path="D:/golden/ormuz-cover.png",
            duration_seconds=1.0,
        )
        publication_elapsed = time.perf_counter() - started

        self.assertIn("CORE STYLE:", prompt)
        self.assertEqual("ready", job.status)
        self._assert_hard_budget("cover-local-processing", cover_elapsed)
        self._assert_hard_budget("publication-preparation", publication_elapsed)

    def test_montage_planning_stays_within_hard_budget(self):
        scenes = [
            {"narration": f"Фраза {index}", "visual_query_en": "oil tanker sea", "duration": 3.0}
            for index in range(100)
        ]
        started = time.perf_counter()
        plan = fit_scene_plan_to_voice_duration(scenes, voice_duration=300.0, max_clip_duration=6.0)
        elapsed = time.perf_counter() - started

        self.assertEqual(50, len(plan))
        self.assertAlmostEqual(300.0, sum(scene["duration"] for scene in plan))
        self._assert_hard_budget("montage-planning", elapsed)


class VoiceQueueSchedulingPerformanceTests(unittest.IsolatedAsyncioTestCase):
    async def test_bounded_voice_queue_scheduling_stays_within_hard_budget(self):
        class LocalClient:
            async def generate(self, prompt: str) -> str:
                await asyncio.sleep(0)
                return prompt

        requests = [ScenarioRequest(index, f"Тема {index}", f"Промпт {index}") for index in range(100)]
        started = time.perf_counter()
        jobs = await ParallelRunner(LocalClient(), max_concurrency=20).run(requests)
        elapsed = time.perf_counter() - started

        self.assertTrue(all(job.state == RunState.DONE for job in jobs))
        status = classify_duration(load_performance_baselines()["voice-queue-scheduling"], elapsed)
        print(f"PERFORMANCE_METRIC metric=voice-queue-scheduling elapsedSeconds={elapsed:.6f} status={status}")
        self.assertNotEqual("HARD_REGRESSION", status, f"voice-queue-scheduling took {elapsed:.3f}s")


if __name__ == "__main__":
    unittest.main()

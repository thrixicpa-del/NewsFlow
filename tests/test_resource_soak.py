"""Quick and opt-in soak checks for disposable NewsFlow resources."""
from __future__ import annotations

import asyncio
import os
import subprocess
import tempfile
import unittest
from pathlib import Path


class ResourceSoakTests(unittest.TestCase):
    def test_quick_repeated_jobs_and_fixture_media_leave_no_test_artifacts(self):
        from scriptor.core import ScenarioRequest
        from scriptor.runner import ParallelRunner, RunState
        from tests.golden_dataset import materialize_golden_dataset

        class LocalClient:
            async def generate(self, prompt: str) -> str:
                await asyncio.sleep(0)
                return prompt

        async def run_jobs() -> None:
            for _ in range(6):
                jobs = await ParallelRunner(LocalClient(), max_concurrency=10).run([
                    ScenarioRequest(index, f"Тема {index}", f"Промпт {index}")
                    for index in range(50)
                ])
                self.assertTrue(all(job.state == RunState.DONE for job in jobs))

        asyncio.run(run_jobs())
        test_root = Path(os.environ["NEWSFLOW_TEST_ROOT"])
        artifact_path: Path
        with tempfile.TemporaryDirectory(dir=test_root, prefix="resource-soak-") as temporary:
            artifact_path = Path(temporary)
            dataset = materialize_golden_dataset(artifact_path / "golden")
            self.assertTrue((dataset.root / "footage" / "tanker.mp4").is_file())
        self.assertFalse(artifact_path.exists(), "test media directory remained after its owner closed")

    def test_ffmpeg_child_exits_and_releases_its_process_handle(self):
        from scriptor.timeline import ffmpeg_executable

        child = subprocess.Popen(
            [ffmpeg_executable(), "-version"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        self.assertEqual(0, child.wait(timeout=10))
        self.assertIsNotNone(child.poll(), "FFmpeg child remained alive after the command completed")

    @unittest.skipUnless(os.environ.get("NEWSFLOW_RUN_SOAK") == "1", "set NEWSFLOW_RUN_SOAK=1 for the extended disposable soak")
    def test_extended_soak_is_opt_in(self):
        from scriptor.core import ScenarioRequest
        from scriptor.runner import ParallelRunner, RunState

        class LocalClient:
            async def generate(self, prompt: str) -> str:
                await asyncio.sleep(0)
                return prompt

        async def run_soak() -> None:
            for _ in range(40):
                jobs = await ParallelRunner(LocalClient(), max_concurrency=20).run([
                    ScenarioRequest(index, f"Тема {index}", f"Промпт {index}")
                    for index in range(100)
                ])
                self.assertTrue(all(job.state == RunState.DONE for job in jobs))

        asyncio.run(run_soak())


if __name__ == "__main__":
    unittest.main()

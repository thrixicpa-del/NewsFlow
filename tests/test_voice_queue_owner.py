"""Real OS ownership, crash recovery and unrelated settings in disposable storage."""
import multiprocessing
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from scriptor import bridge, config


def _hold_owner(root, ready):
    with patch.object(bridge, "app_data_root", return_value=Path(root)), bridge._voice_queue_owner():
        ready.set()
        time.sleep(15)  # The parent deliberately terminates this owned process.


class VoiceQueueOwnerTests(unittest.TestCase):
    def test_stale_voice_progress_preserves_new_template_and_preset(self):
        with tempfile.TemporaryDirectory(dir=os.environ["NEWSFLOW_TEST_ROOT"]) as folder, \
             patch.object(config, "config_path", return_value=Path(folder) / "settings.json"), \
             patch.object(bridge, "snapshot", return_value={}):
            config.save_settings(config.Settings(template="Old template {title}"))
            voice_snapshot = config.load_settings()
            bridge.save_template_preset({"name": "Independent", "template": "New template {title}"})
            voice_snapshot.voice_task_statuses = {"1": {"label": "Running", "progress": 55}}
            config.save_settings(voice_snapshot)
            saved = config.load_settings()
            self.assertEqual(saved.template, "New template {title}")
            self.assertEqual(saved.scenario_templates[-1]["name"], "Independent")
            self.assertEqual(saved.voice_task_statuses["1"]["progress"], 55)
            # The long worker can publish again without adopting UI settings.
            voice_snapshot.voice_task_statuses["1"]["progress"] = 75
            config.save_settings(voice_snapshot)
            self.assertEqual(config.load_settings().template, "New template {title}")

    def test_stale_template_save_preserves_new_voice_progress_and_pause(self):
        with tempfile.TemporaryDirectory(dir=os.environ["NEWSFLOW_TEST_ROOT"]) as folder, \
             patch.object(config, "config_path", return_value=Path(folder) / "settings.json"), \
             patch.object(bridge, "snapshot", return_value={}):
            config.save_settings(config.Settings(template="Old template {title}"))
            template_snapshot = config.load_settings()
            voice_snapshot = config.load_settings()
            voice_snapshot.voice_task_statuses = {"1": {"label": "Running", "progress": 55}}
            voice_snapshot.voice_tts_jobs = {"production-1": {"id": "job-1", "state": "running"}}
            voice_snapshot.voice_queue_paused = True
            config.save_settings(voice_snapshot)
            with patch.object(bridge, "load_settings", return_value=template_snapshot):
                bridge.save_template({"template": "New template {title}"})
            saved = config.load_settings()
            self.assertEqual(saved.template, "New template {title}")
            self.assertEqual(saved.voice_task_statuses["1"]["progress"], 55)
            self.assertEqual(saved.voice_tts_jobs["production-1"]["state"], "running")
            self.assertTrue(saved.voice_queue_paused)

    def test_other_process_is_rejected_template_save_succeeds_and_crash_releases_owner(self):
        with tempfile.TemporaryDirectory(dir=os.environ["NEWSFLOW_TEST_ROOT"]) as folder:
            root = Path(folder)
            context = multiprocessing.get_context("spawn")
            ready = context.Event()
            process = context.Process(target=_hold_owner, args=(folder, ready), daemon=True)
            process.start()
            try:
                self.assertTrue(ready.wait(8), "voice owner did not start")
                with patch.object(bridge, "app_data_root", return_value=root):
                    with self.assertRaisesRegex(ValueError, "Очередь озвучки уже выполняется"), \
                         bridge._voice_queue_owner():
                        self.fail("a competing process acquired ownership")
                    with patch.object(config, "config_path", return_value=root / "settings.json"), \
                         patch.object(bridge, "snapshot", return_value={}):
                        bridge.save_template({"template": "Independent template {title}"})
                        self.assertEqual(config.load_settings().template, "Independent template {title}")
                    self.assertTrue(process.is_alive(), "template save waited for voice completion")
                    process.terminate()
                    process.join(5)
                    self.assertFalse(process.is_alive())
                    with bridge._voice_queue_owner():
                        pass  # No stale PID/lock cleanup needed after process death.
            finally:
                if process.is_alive():
                    process.terminate()
                process.join(5)
                process.close()

    def test_exception_releases_owner(self):
        with tempfile.TemporaryDirectory(dir=os.environ["NEWSFLOW_TEST_ROOT"]) as folder, \
             patch.object(bridge, "app_data_root", return_value=Path(folder)):
            with self.assertRaisesRegex(RuntimeError, "worker failed"), bridge._voice_queue_owner():
                raise RuntimeError("worker failed")
            with bridge._voice_queue_owner():
                pass

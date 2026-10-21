"""Real OS ownership, crash recovery and unrelated settings in disposable storage."""
import multiprocessing
import os
import tempfile
import time
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

from scriptor import bridge, config


def _hold_owner(root, ready):
    with patch.object(bridge, "app_data_root", return_value=Path(root)), bridge._voice_queue_owner():
        ready.set()
        time.sleep(15)  # The parent deliberately terminates this owned process.


class VoiceQueueOwnerTests(unittest.TestCase):
    @contextmanager
    def _overtaken_template_save(self):
        with tempfile.TemporaryDirectory(dir=os.environ["NEWSFLOW_TEST_ROOT"]) as folder, \
             patch.object(config, "config_path", return_value=Path(folder) / "settings.json"), \
             patch.object(bridge, "snapshot", return_value={}):
            initial = config.Settings(
                template="Original template {title}", scenario_target_chars=12000,
                scenario_allowed_min=8000, scenario_allowed_max=15000,
                prompt_ranges=[{"start": 1, "end": 2, "prompt": "Original range",
                                "target_chars": 0, "allowed_min": 0, "allowed_max": 0}],
            )
            config.save_settings(initial)
            pending = config.load_settings()
            concurrent = config.load_settings()
            concurrent.template = "Concurrent template {title}"
            concurrent.scenario_target_chars = 14000
            concurrent.scenario_allowed_min = 10000
            concurrent.scenario_allowed_max = 16000
            concurrent.prompt_ranges = [{"start": 3, "end": 4, "prompt": "Concurrent range",
                                         "target_chars": 0, "allowed_min": 0, "allowed_max": 0}]
            config.save_settings(concurrent)
            yield initial, pending, concurrent

    def test_repeated_explicit_template_and_range_saves_apply_active_fields(self):
        fields = ("template", "prompt_ranges", "scenario_target_chars",
                  "scenario_allowed_min", "scenario_allowed_max")
        for command in (bridge.save_template, bridge.save_template_preset, bridge.save_range_preset):
            with self.subTest(command=command.__name__), self._overtaken_template_save() as values:
                initial, pending, concurrent = values
                payload = {"name": "Saved preset", "template": initial.template,
                           "ranges": initial.prompt_ranges, "targetChars": initial.scenario_target_chars,
                           "allowedMin": initial.scenario_allowed_min, "allowedMax": initial.scenario_allowed_max}
                with patch.object(bridge, "load_settings", return_value=pending):
                    command(payload)
                saved = config.load_settings()
                for name in fields:
                    source = (concurrent if command is bridge.save_range_preset and name != "prompt_ranges"
                              else initial)
                    self.assertEqual(getattr(saved, name), getattr(source, name), name)

                # The next command may change all active fields. A subsequent
                # unrelated save of the old object must not retain ownership.
                later = config.load_settings()
                later.template = "Later template {title}"
                later.prompt_ranges = [{"start": 7, "end": 8, "prompt": "Later range",
                                        "target_chars": 0, "allowed_min": 0, "allowed_max": 0}]
                later.scenario_target_chars = 17000
                later.scenario_allowed_min = 16000
                later.scenario_allowed_max = 18000
                config.save_settings(later)
                pending.voice_task_statuses = {"1": {"label": "Running", "progress": 55}}
                config.save_settings(pending)
                final = config.load_settings()
                for name in fields:
                    self.assertEqual(getattr(final, name), getattr(later, name), name)

    def test_template_save_preserves_omitted_lengths_ranges_and_presets(self):
        lengths = {"targetChars": "scenario_target_chars", "allowedMin": "scenario_allowed_min",
                   "allowedMax": "scenario_allowed_max"}
        for submitted in (None, *lengths):
            with self.subTest(submitted=submitted), self._overtaken_template_save() as values:
                initial, pending, concurrent = values
                # An unrelated preset is added after the old settings read.
                current = config.load_settings()
                current.scenario_templates.append({"name": "Concurrent preset", "template": "Keep me"})
                config.save_settings(current)
                payload = {"template": initial.template, "ranges": None}
                if submitted:
                    payload[submitted] = getattr(initial, lengths[submitted])
                with patch.object(bridge, "load_settings", return_value=pending):
                    bridge.save_template(payload)
                saved = config.load_settings()
                self.assertEqual(saved.template, initial.template)
                self.assertEqual(saved.prompt_ranges, concurrent.prompt_ranges)
                self.assertEqual(saved.scenario_templates, current.scenario_templates)
                for key, name in lengths.items():
                    source = initial if key == submitted else concurrent
                    self.assertEqual(getattr(saved, name), getattr(source, name), name)

    def test_partial_length_save_rejects_conflicting_current_bounds_without_writes(self):
        for key, value, latest_min, latest_max in (
            ("allowedMax", 15000, 16000, 18000),
            ("allowedMin", 8000, 6000, 7000),
        ):
            with self.subTest(key=key), self._overtaken_template_save() as values:
                initial, pending, _concurrent = values
                latest = config.load_settings()
                latest.scenario_allowed_min = latest_min
                latest.scenario_allowed_max = latest_max
                config.save_settings(latest)
                path = config.config_path()
                backup = path.parent / "state-backups" / "settings-last-known-good.json"
                before, previous_backup = path.read_bytes(), backup.read_bytes()
                with patch.object(bridge, "load_settings", return_value=pending), \
                     self.assertRaisesRegex(ValueError, "Минимальная длина сценария больше максимальной"):
                    bridge.save_template({"template": initial.template, key: value})
                self.assertEqual(path.read_bytes(), before)
                self.assertEqual(backup.read_bytes(), previous_backup)

    def test_partial_length_save_allows_zero_as_unset_and_preserves_other_bound(self):
        for key, field, omitted in (
            ("allowedMax", "scenario_allowed_max", "scenario_allowed_min"),
            ("allowedMin", "scenario_allowed_min", "scenario_allowed_max"),
        ):
            with self.subTest(key=key), self._overtaken_template_save() as values:
                initial, pending, concurrent = values
                with patch.object(bridge, "load_settings", return_value=pending):
                    bridge.save_template({"template": initial.template, key: 0})
                saved = config.load_settings()
                self.assertEqual(getattr(saved, field), 0)
                self.assertEqual(getattr(saved, omitted), getattr(concurrent, omitted))
                self.assertEqual(saved.scenario_target_chars, concurrent.scenario_target_chars)

    def test_explicit_pause_choice_wins_after_same_value_snapshot_is_overtaken(self):
        for paused in (True, False):
            with self.subTest(paused=paused), \
                 tempfile.TemporaryDirectory(dir=os.environ["NEWSFLOW_TEST_ROOT"]) as folder, \
                 patch.object(config, "config_path", return_value=Path(folder) / "settings.json"), \
                 patch.object(bridge, "snapshot", return_value={}):
                config.save_settings(config.Settings(voice_queue_paused=paused))
                pending_command = config.load_settings()
                competing_command = config.load_settings()
                competing_command.voice_queue_paused = not paused
                config.save_settings(competing_command)

                # This explicit command read before the competing write, but
                # reaches the write mutex last. Its requested value must win,
                # even when that value equals its earlier loaded snapshot.
                with patch.object(bridge, "load_settings", return_value=pending_command):
                    bridge.set_voice_queue_paused({"paused": paused})
                self.assertEqual(config.load_settings().voice_queue_paused, paused)

                # Ownership belongs to that explicit write only. Reusing the
                # object for unrelated work must not undo a later choice.
                bridge.set_voice_queue_paused({"paused": not paused})
                pending_command.template = "Independent template {title}"
                config.save_settings(pending_command)
                self.assertEqual(config.load_settings().voice_queue_paused, not paused)

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

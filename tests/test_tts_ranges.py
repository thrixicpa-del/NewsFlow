import unittest
from typing import ClassVar


class TtsRangeOrchestrationTests(unittest.TestCase):
    def test_voice_queue_command_selects_only_ready_scenarios_and_keeps_skip_reasons(self):
        """Queue-all must not submit empty scripts or duplicate a ready MP3."""
        from unittest.mock import patch

        from scriptor import bridge
        from scriptor.config import Settings
        from scriptor.core import ScenarioRequest
        from scriptor.runner import Job, RunState

        settings = Settings()
        ready = Job(ScenarioRequest(0, "Готов", ""), RunState.DONE, "Текст", "")
        waiting = Job(ScenarioRequest(1, "Без сценария", ""), RunState.WAITING, "", "")
        with patch.object(bridge, "load_settings", return_value=settings), \
             patch.object(bridge, "load_session", return_value=(["Готов", "Без сценария"], [ready, waiting])), \
             patch.object(bridge, "save_settings"), \
             patch.object(bridge, "generate_voice", return_value={"ok": True}) as generate:
            result = bridge.generate_voice_queue({})

        self.assertEqual(result["operationResult"]["eligible"], 1)
        self.assertEqual(result["operationResult"]["skipped"], 1)
        self.assertEqual(settings.voice_task_statuses["2"]["label"], "Пропущено: сценарий не готов")
        generate.assert_called_once_with({"indices": [0], "force": False})

    def test_migrates_legacy_profile_indexes_to_stable_ids_without_changing_range_bounds(self):
        from scriptor.tts_ranges import migrate_voice_range_settings

        profiles, ranges, default_profile_id, changed = migrate_voice_range_settings(
            [{"name": "Default"}, {"name": "Second"}],
            [{"start": 11, "end": 20, "profile": 1, "enabled": True}],
            "",
        )

        self.assertTrue(changed)
        self.assertTrue(all(profile["id"] for profile in profiles))
        self.assertEqual(default_profile_id, profiles[0]["id"])
        self.assertEqual(ranges[0]["profile_id"], profiles[1]["id"])
        self.assertTrue(ranges[0]["id"])
        self.assertEqual((ranges[0]["start"], ranges[0]["end"]), (11, 20))

    def test_settings_keep_default_profile_frozen_batches_and_job_snapshots(self):
        from scriptor.config import Settings

        settings = Settings(
            voice_default_profile_id="voice-default",
            voice_tts_batches=[{"id": "batch-1", "items": []}],
            voice_active_tts_batch_id="batch-1",
            voice_tts_jobs={"item-1": {"id": "job-1", "state": "queued"}},
            voice_queue_concurrency=20,
        )

        self.assertEqual(settings.voice_default_profile_id, "voice-default")
        self.assertEqual(settings.voice_tts_batches[0]["id"], "batch-1")
        self.assertEqual(settings.voice_active_tts_batch_id, "batch-1")
        self.assertEqual(settings.voice_tts_jobs["item-1"]["id"], "job-1")
        self.assertEqual(settings.voice_queue_concurrency, 20)

    def test_existing_production_item_receives_one_persistent_id_during_migration(self):
        from scriptor import bridge
        from scriptor.config import Settings

        settings = Settings(idea_production_items=[{"title": "Тема", "topic": "Тема"}])

        self.assertTrue(bridge.ensure_idea_production_items(settings))
        item_id = settings.idea_production_items[0]["id"]
        self.assertTrue(item_id)
        self.assertFalse(bridge.ensure_idea_production_items(settings))
        self.assertEqual(settings.idea_production_items[0]["id"], item_id)

    def test_saving_overlapping_voice_ranges_is_blocked_before_persistence(self):
        from unittest.mock import patch

        from scriptor import bridge
        from scriptor.config import Settings

        settings = Settings(voice_profiles=[{"id": "voice-a", "name": "A"}, {"id": "voice-b", "name": "B"}],
                            voice_default_profile_id="voice-a")
        with patch.object(bridge, "load_settings", return_value=settings), \
             patch.object(bridge, "save_settings") as save, \
             self.assertRaisesRegex(ValueError, "10–15"):
            bridge.save_voice_settings({"ranges": [
                {"id": "one", "start": 1, "end": 15, "profile_id": "voice-a", "enabled": True},
                {"id": "two", "start": 10, "end": 20, "profile_id": "voice-b", "enabled": True},
            ]})
        save.assert_not_called()

    def test_user_can_save_global_tts_concurrency_independently_of_ranges(self):
        from unittest.mock import patch

        from scriptor import bridge
        from scriptor.config import Settings

        settings = Settings(voice_profiles=[{"id": "voice-a", "name": "A"}], voice_default_profile_id="voice-a")
        with patch.object(bridge, "load_settings", return_value=settings), \
             patch.object(bridge, "save_settings"), \
             patch.object(bridge, "snapshot", return_value={"ok": True}):
            bridge.save_voice_settings({"queueConcurrency": 7})

        self.assertEqual(settings.voice_queue_concurrency, 7)

    def test_wproject_uses_all_ten_authorised_queue_slots_when_ten_jobs_are_ready(self):
        """The UI value 10 must not silently serialize otherwise independent jobs."""
        import tempfile
        import threading
        from unittest.mock import patch

        from scriptor import bridge
        from scriptor.config import Settings, WProjectKey
        from scriptor.core import ScenarioRequest
        from scriptor.runner import Job, RunState

        class FakeWProject:
            active = 0
            maximum = 0
            lock = threading.Lock()
            barrier = threading.Barrier(10)

            def __init__(self, _key):
                pass

            def create_task(self, _text, filename, _profile, *, threads, idempotency_key=None):
                with type(self).lock:
                    type(self).active += 1
                    type(self).maximum = max(type(self).maximum, type(self).active)
                try:
                    type(self).barrier.wait(timeout=5)
                finally:
                    with type(self).lock:
                        type(self).active -= 1
                return filename

            def wait_download(self, _task_id, progress=None):
                return b"WPROJECT"

        with tempfile.TemporaryDirectory() as folder:
            titles = [f"Тема {index}" for index in range(10)]
            jobs = [Job(ScenarioRequest(index, title, ""), RunState.DONE, f"Текст {index}", "")
                    for index, title in enumerate(titles)]
            settings = Settings(
                voicer_output_folder=folder, voice_queue_concurrency=10,
                wproject_api_keys=[WProjectKey("W", "test", active=True, streams=10)],
                voice_profiles=[{"id": "w", "name": "W", "provider": "wproject", "voice_id": "speaker", "task_threads": 10}],
                voice_default_profile_id="w",
                idea_production_items=[{"id": f"item-{index}", "title": title} for index, title in enumerate(titles)],
            )
            with patch.object(bridge, "load_settings", return_value=settings), \
                 patch.object(bridge, "save_settings"), \
                 patch.object(bridge, "load_session", return_value=(titles, jobs)), \
                 patch.object(bridge, "snapshot", return_value={"ok": True}), \
                 patch.object(bridge, "WProjectClient", FakeWProject), \
                 patch.object(bridge, "validate_voiceover_artifact", return_value=24.0):
                bridge.generate_voice({"indices": list(range(10))})

        self.assertEqual(FakeWProject.maximum, 10)
        self.assertEqual(len(settings.voice_scenario_outputs), 10)

    def test_preview_freezes_batch_order_and_exposes_voice_for_each_item(self):
        from scriptor import bridge
        from scriptor.config import Settings

        settings = Settings(
            voice_profiles=[
                {"id": "a", "name": "Voice A", "provider": "voicegen", "voice_id": "a"},
                {"id": "b", "name": "Voice B", "provider": "lumean", "voice_id": "b"},
            ],
            voice_default_profile_id="a",
            voice_ranges=[{"id": "range-b", "start": 2, "end": 2, "profile_id": "b", "enabled": True}],
            idea_production_items=[
                {"id": "first", "title": "Первая тема"},
                {"id": "second", "title": "Вторая тема"},
                {"id": "third", "title": "Третья тема"},
            ],
        )

        preview = bridge.prepare_voice_range_preview(settings, ["Первая тема", "Вторая тема", "Третья тема"])
        reordered_display = list(reversed(preview["items"]))
        persisted = bridge.prepare_voice_range_preview(settings, ["Первая тема", "Вторая тема", "Третья тема"])

        self.assertEqual([row["production_item_id"] for row in preview["items"]], ["first", "second", "third"])
        self.assertEqual([row["profile"]["name"] for row in preview["items"]], ["Voice A", "Voice B", "Voice A"])
        self.assertEqual([row["production_item_id"] for row in persisted["items"]], ["first", "second", "third"])
        self.assertEqual(reordered_display[0]["production_item_id"], "third")
        self.assertEqual(preview["batch"]["id"], persisted["batch"]["id"])

    def test_normal_start_keeps_ready_audio_but_explicit_revoice_creates_snapshot(self):
        import tempfile
        from pathlib import Path

        from scriptor import bridge
        from scriptor.config import Settings
        from scriptor.core import ScenarioRequest
        from scriptor.runner import Job, RunState

        with tempfile.TemporaryDirectory() as folder:
            audio = Path(folder) / "ready.mp3"
            audio.write_bytes(b"MP3")
            settings = Settings(
                voicer_output_folder=folder,
                voice_profiles=[{"id": "a", "name": "Voice A", "provider": "voicegen", "voice_id": "a"}],
                voice_default_profile_id="a",
                idea_production_items=[{"id": "item-1", "title": "Тема"}],
                voice_scenario_outputs={"1": str(audio)},
                voice_tts_jobs={"item-1": {"settings": {"voice_id": "old"}}},
            )
            job = Job(ScenarioRequest(0, "Тема", ""), RunState.DONE, "Текст сценария", "")

            normal = bridge.prepare_voice_jobs(settings, ["Тема"], [job], {0}, force=False)
            self.assertEqual(normal, [])
            self.assertEqual(settings.voice_scenario_outputs["1"], str(audio))
            self.assertEqual(settings.voice_task_statuses["1"]["label"], "Настройки озвучки изменены")

            revoice = bridge.prepare_voice_jobs(settings, ["Тема"], [job], {0}, force=True)
            self.assertEqual(len(revoice), 1)
            self.assertEqual(revoice[0]["production_item_id"], "item-1")
            self.assertEqual(revoice[0]["settings"]["voice_id"], "a")

    def test_one_batch_dispatches_different_range_snapshots_to_their_providers(self):
        import tempfile
        from unittest.mock import patch

        from scriptor import bridge
        from scriptor.config import LumeanKey, Settings, VoiceGenKey
        from scriptor.core import ScenarioRequest
        from scriptor.runner import Job, RunState

        class FakeVoiceGen:
            calls: ClassVar[list] = []
            def __init__(self, _key):
                pass
            def synthesize(self, _text, _filename, profile, *, threads, progress=None):
                self.calls.append(profile.voice_id)
                return b"VOICEGEN"

        class FakeLumean:
            calls: ClassVar[list] = []
            def __init__(self, _key):
                pass
            def synthesize(self, _text, profile, progress=None):
                self.calls.append(profile.voice_id)
                return b"LUMEAN", "template", "signature"

        with tempfile.TemporaryDirectory() as folder:
            settings = Settings(
                voicer_output_folder=folder,
                voice_provider="voicegen",
                voice_queue_concurrency=20,
                voicegen_api_keys=[VoiceGenKey("VG", "key", streams=10)],
                lumean_api_keys=[LumeanKey("LU", "key", streams=10)],
                voice_profiles=[
                    {"id": "vg", "name": "VoiceGen", "provider": "voicegen", "voice_id": "vg-voice", "model_id": "v3"},
                    {"id": "lu", "name": "Lumean", "provider": "lumean", "voice_id": "lu-voice", "model_id": "model"},
                ],
                voice_default_profile_id="vg",
                voice_ranges=[{"id": "lumean-range", "start": 2, "end": 2, "profile_id": "lu", "enabled": True}],
                idea_production_items=[{"id": "one", "title": "Один"}, {"id": "two", "title": "Два"}],
            )
            jobs = [
                Job(ScenarioRequest(0, "Один", ""), RunState.DONE, "Первый текст", ""),
                Job(ScenarioRequest(1, "Два", ""), RunState.DONE, "Второй текст", ""),
            ]
            with patch.object(bridge, "load_settings", return_value=settings), \
                 patch.object(bridge, "save_settings"), \
                 patch.object(bridge, "load_session", return_value=(["Один", "Два"], jobs)), \
                 patch.object(bridge, "snapshot", return_value={"ok": True}), \
                 patch.object(bridge, "VoiceGenClient", FakeVoiceGen), \
                 patch.object(bridge, "LumeanClient", FakeLumean), \
                 patch.object(bridge, "validate_voiceover_artifact", return_value=1.0):
                bridge.generate_voice({"indices": [0, 1]})

        self.assertEqual(FakeVoiceGen.calls, ["vg-voice"])
        self.assertEqual(FakeLumean.calls, ["lu-voice"])

    def test_queued_resume_uses_the_persisted_snapshot_not_a_later_range_edit(self):
        import tempfile
        from unittest.mock import patch

        from scriptor import bridge
        from scriptor.config import Settings, VoiceGenKey
        from scriptor.core import ScenarioRequest
        from scriptor.runner import Job, RunState

        class FakeVoiceGen:
            calls: ClassVar[list] = []
            def __init__(self, _key):
                pass
            def synthesize(self, _text, _filename, profile, *, threads, progress=None):
                self.calls.append(profile.voice_id)
                return b"RESUMED"

        with tempfile.TemporaryDirectory() as folder:
            saved_job = {
                "id": "saved-job", "batch_id": "saved-batch", "production_item_id": "production-1",
                "batch_position": 1, "scenario_index": 0, "range_id": "old-range", "provider": "voicegen",
                "settings": {"id": "old", "name": "Old", "provider": "voicegen", "voice_id": "old-voice", "task_threads": 1},
                "fallback_settings": [], "script_hash": "", "script_revision": "", "output_folder": folder, "state": "queued",
            }
            settings = Settings(
                voicer_output_folder=folder, voice_queue_concurrency=5,
                voicegen_api_keys=[VoiceGenKey("VG", "key", streams=5)],
                voice_profiles=[{"id": "new", "name": "New", "provider": "voicegen", "voice_id": "new-voice"}],
                voice_default_profile_id="new", idea_production_items=[{"id": "production-1", "title": "Тема"}],
                voice_tts_jobs={"production-1": saved_job},
            )
            job = Job(ScenarioRequest(0, "Тема", ""), RunState.DONE, "Текст сценария", "")
            with patch.object(bridge, "load_settings", return_value=settings), \
                 patch.object(bridge, "save_settings"), \
                 patch.object(bridge, "load_session", return_value=(["Тема"], [job])), \
                 patch.object(bridge, "snapshot", return_value={"ok": True}), \
                 patch.object(bridge, "VoiceGenClient", FakeVoiceGen), \
                 patch.object(bridge, "validate_voiceover_artifact", return_value=1.0):
                bridge.generate_voice({"indices": [0], "resume": True})

        self.assertEqual(FakeVoiceGen.calls, ["old-voice"])

    def test_unsafe_inflight_non_idempotent_provider_requires_explicit_revoice(self):
        import hashlib
        import tempfile
        from unittest.mock import patch

        from scriptor import bridge
        from scriptor.config import LumeanKey, SecretVoicerKey, Settings, VoiceGenKey
        from scriptor.core import ScenarioRequest
        from scriptor.runner import Job, RunState

        text = "Текст сценария"
        for provider in ("api", "lumean", "voicegen", "chrome"):
            with self.subTest(provider=provider), tempfile.TemporaryDirectory() as folder:
                saved_job = {
                    "id": "saved-job", "batch_id": "saved-batch", "production_item_id": "production-1",
                    "batch_position": 1, "scenario_index": 0, "range_id": "saved-range", "provider": provider,
                    "settings": {"id": "saved", "name": "Saved", "provider": provider, "voice_id": "saved-voice"},
                    "fallback_settings": [], "script_hash": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                    "script_revision": "revision-1", "output_folder": folder, "state": "running",
                }
                settings = Settings(
                    voicer_output_folder=folder,
                    secret_voicer_keys=[SecretVoicerKey("API", "key")],
                    lumean_api_keys=[LumeanKey("Lumean", "key")],
                    voicegen_api_keys=[VoiceGenKey("VoiceGen", "key")],
                    voice_tts_jobs={"production-1": saved_job},
                    idea_production_items=[{"id": "production-1", "title": "Тема"}],
                )
                job = Job(ScenarioRequest(0, "Тема", "", "production-1"), RunState.DONE, text, "")
                with patch.object(bridge, "load_settings", return_value=settings), \
                     patch.object(bridge, "save_settings") as save_settings, \
                     patch.object(bridge, "load_session", return_value=(["Тема"], [job])), \
                     patch.object(bridge, "snapshot", return_value={"ok": True}), \
                     patch.object(bridge, "SecretVoicerClient", side_effect=AssertionError("provider must not be called")), \
                     patch.object(bridge, "LumeanClient", side_effect=AssertionError("provider must not be called")), \
                     patch.object(bridge, "VoiceGenClient", side_effect=AssertionError("provider must not be called")), \
                     patch.object(bridge, "ChromeSecretVoicer", side_effect=AssertionError("provider must not be called")):
                    result = bridge.generate_voice({"indices": [0], "resume": True})

                self.assertEqual(result, {"ok": True})
                self.assertEqual(saved_job["state"], "interrupted")
                self.assertEqual(saved_job["production_item_id"], "production-1")
                self.assertEqual(saved_job["script_revision"], "revision-1")
                self.assertIn("Автопродолжение отключено", settings.voice_task_statuses["1"]["label"])
                self.assertTrue(save_settings.called)

    def test_non_idempotent_provider_persists_running_before_invocation(self):
        import tempfile
        from unittest.mock import patch

        from scriptor import bridge
        from scriptor.config import Settings, VoiceGenKey
        from scriptor.core import ScenarioRequest
        from scriptor.runner import Job, RunState

        persisted_states = []
        invocation_states = []

        class FakeVoiceGen:
            calls = 0
            def __init__(self, _key):
                pass
            def synthesize(self, _text, _filename, _profile, *, threads, progress=None):
                type(self).calls += 1
                self_snapshot = settings.voice_tts_jobs["production-1"]
                invocation_states.append((self_snapshot["state"], self_snapshot["active_provider"]))
                return b"VOICEGEN"

        with tempfile.TemporaryDirectory() as folder:
            settings = Settings(
                voicer_output_folder=folder, voice_queue_concurrency=1,
                voicegen_api_keys=[VoiceGenKey("VG", "key")],
                voice_profiles=[{"id": "voice", "name": "Voice", "provider": "voicegen", "voice_id": "voice-id"}],
                voice_default_profile_id="voice", idea_production_items=[{"id": "production-1", "title": "Тема"}],
            )
            job = Job(ScenarioRequest(0, "Тема", ""), RunState.DONE, "Текст сценария", "")

            def record_save(saved_settings):
                saved = saved_settings.voice_tts_jobs.get("production-1", {})
                persisted_states.append((saved.get("state"), saved.get("active_provider")))

            with patch.object(bridge, "load_settings", return_value=settings), \
                 patch.object(bridge, "save_settings", side_effect=record_save), \
                 patch.object(bridge, "load_session", return_value=(["Тема"], [job])), \
                 patch.object(bridge, "snapshot", return_value={"ok": True}), \
                 patch.object(bridge, "VoiceGenClient", FakeVoiceGen), \
                 patch.object(bridge, "validate_voiceover_artifact", return_value=1.0):
                bridge.generate_voice({"indices": [0]})

        self.assertEqual(FakeVoiceGen.calls, 1)
        self.assertEqual(invocation_states, [("running", "voicegen")])
        self.assertIn(("running", "voicegen"), persisted_states)

    def test_retryable_provider_limit_retries_same_snapshot_with_backoff(self):
        import tempfile
        from unittest.mock import patch

        from scriptor import bridge
        from scriptor.config import Settings, VoiceGenKey
        from scriptor.core import ScenarioRequest
        from scriptor.runner import Job, RunState

        class FlakyVoiceGen:
            calls = 0
            def __init__(self, _key):
                pass
            def synthesize(self, _text, _filename, _profile, *, threads, progress=None):
                type(self).calls += 1
                if self.calls == 1:
                    raise RuntimeError("HTTP 429 rate limit")
                return b"RETRIED"

        with tempfile.TemporaryDirectory() as folder:
            settings = Settings(
                voicer_output_folder=folder, voice_queue_concurrency=1,
                voicegen_api_keys=[VoiceGenKey("VG", "key", streams=1)],
                voice_profiles=[{"id": "voice", "name": "Voice", "provider": "voicegen", "voice_id": "voice-id"}],
                voice_default_profile_id="voice", idea_production_items=[{"id": "production-1", "title": "Тема"}],
            )
            job = Job(ScenarioRequest(0, "Тема", ""), RunState.DONE, "Текст сценария", "")
            with patch.object(bridge, "load_settings", return_value=settings), \
                 patch.object(bridge, "save_settings"), \
                 patch.object(bridge, "load_session", return_value=(["Тема"], [job])), \
                 patch.object(bridge, "snapshot", return_value={"ok": True}), \
                 patch.object(bridge, "VoiceGenClient", FlakyVoiceGen), \
                 patch.object(bridge, "validate_voiceover_artifact", return_value=1.0), \
                 patch.object(bridge.time, "sleep"):
                bridge.generate_voice({"indices": [0]})

        self.assertEqual(FlakyVoiceGen.calls, 2)

    def test_one_range_can_dispatch_to_wproject_with_its_saved_controls(self):
        import tempfile
        from unittest.mock import patch

        from scriptor import bridge
        from scriptor.config import Settings, WProjectKey
        from scriptor.core import ScenarioRequest
        from scriptor.runner import Job, RunState

        class FakeWProject:
            calls: ClassVar[list] = []
            def __init__(self, _key):
                pass
            def create_task(self, _text, _filename, profile, *, threads, idempotency_key=None):
                self.calls.append((profile.voice_id, profile.wproject_autotag, profile.wproject_latency, threads))
                return "remote-task-1"
            def wait_download(self, task_id, progress=None):
                self.calls.append(("wait", task_id))
                return b"WPROJECT"

        with tempfile.TemporaryDirectory() as folder:
            settings = Settings(
                voicer_output_folder=folder, voice_queue_concurrency=20,
                wproject_api_keys=[WProjectKey("W", "test", streams=10)],
                voice_profiles=[{
                    "id": "w", "name": "W", "provider": "wproject", "voice_id": "speaker",
                    "wproject_autotag": "medium", "wproject_latency": "balanced", "task_threads": 10,
                }],
                voice_default_profile_id="w", idea_production_items=[{"id": "production-1", "title": "Тема"}],
            )
            job = Job(ScenarioRequest(0, "Тема", ""), RunState.DONE, "Текст сценария", "")
            with patch.object(bridge, "load_settings", return_value=settings), \
                 patch.object(bridge, "save_settings"), \
                 patch.object(bridge, "load_session", return_value=(["Тема"], [job])), \
                 patch.object(bridge, "snapshot", return_value={"ok": True}), \
                 patch.object(bridge, "WProjectClient", FakeWProject), \
                 patch.object(bridge, "validate_voiceover_artifact", return_value=1.0):
                bridge.generate_voice({"indices": [0]})

        self.assertEqual(FakeWProject.calls, [("speaker", "medium", "balanced", 10), ("wait", "remote-task-1")])
        self.assertEqual(settings.voice_tts_jobs["production-1"]["remote_task"]["task_id"], "remote-task-1")

    def test_wproject_retries_long_russian_text_before_task_id_without_duplicate(self):
        """A transient submit failure may retry; once an ID exists it is the sole remote task."""
        import tempfile
        from unittest.mock import patch

        from scriptor import bridge
        from scriptor.config import Settings, WProjectKey
        from scriptor.core import ScenarioRequest
        from scriptor.runner import Job, RunState

        class FakeWProject:
            submitted_texts: ClassVar[list] = []
            waited: ClassVar[list] = []

            def __init__(self, _key):
                pass

            def create_task(self, text, _filename, _profile, *, threads, idempotency_key=None):
                type(self).submitted_texts.append((text, threads))
                if len(self.submitted_texts) == 1:
                    raise RuntimeError("429 rate limit")
                return "wproject-task-42"

            def wait_download(self, task_id, progress=None):
                type(self).waited.append(task_id)
                return b"WPROJECT"

        long_text = "Ормузский пролив остаётся в центре внимания нефтяного рынка. " * 120
        with tempfile.TemporaryDirectory() as folder:
            settings = Settings(
                voicer_output_folder=folder, voice_queue_concurrency=1,
                wproject_api_keys=[WProjectKey("W", "test", streams=1)],
                voice_profiles=[{"id": "w", "name": "W", "provider": "wproject", "voice_id": "speaker", "task_threads": 7}],
                voice_default_profile_id="w", idea_production_items=[{"id": "production-42", "title": "Ормуз"}],
            )
            job = Job(ScenarioRequest(0, "Ормуз", ""), RunState.DONE, long_text, "")
            with patch.object(bridge, "load_settings", return_value=settings), \
                 patch.object(bridge, "save_settings"), \
                 patch.object(bridge, "load_session", return_value=(["Ормуз"], [job])), \
                 patch.object(bridge, "snapshot", return_value={"ok": True}), \
                 patch.object(bridge, "WProjectClient", FakeWProject), \
                 patch.object(bridge, "validate_voiceover_artifact", return_value=37.5), \
                 patch.object(bridge.time, "sleep"):
                bridge.generate_voice({"indices": [0]})

        self.assertEqual(FakeWProject.submitted_texts, [(long_text, 7), (long_text, 7)])
        self.assertEqual(FakeWProject.waited, ["wproject-task-42"])
        saved = settings.voice_tts_jobs["production-42"]
        self.assertEqual(saved["production_item_id"], "production-42")
        self.assertEqual(saved["remote_task"]["task_id"], "wproject-task-42")
        self.assertEqual(saved["artifact"]["duration_seconds"], 37.5)

    def test_wproject_retries_keep_one_persisted_idempotency_key_before_task_id(self):
        """A lost submit response must be retried with the same provider key."""
        import tempfile
        from unittest.mock import patch

        from scriptor import bridge
        from scriptor.config import Settings, WProjectKey
        from scriptor.core import ScenarioRequest
        from scriptor.runner import Job, RunState

        class TemporarilyUnavailableWProject:
            idempotency_keys: ClassVar[list] = []

            def __init__(self, _key):
                pass

            def create_task(self, _text, _filename, _profile, *, threads, idempotency_key):
                type(self).idempotency_keys.append(idempotency_key)
                raise RuntimeError("503 WProject временно недоступен")

        with tempfile.TemporaryDirectory() as folder:
            settings = Settings(
                voicer_output_folder=folder, voice_queue_concurrency=1,
                wproject_api_keys=[WProjectKey("W", "test", streams=1)],
                voice_profiles=[{"id": "w", "name": "W", "provider": "wproject", "voice_id": "speaker"}],
                voice_default_profile_id="w", idea_production_items=[{"id": "production-1", "title": "Тема"}],
            )
            job = Job(ScenarioRequest(0, "Тема", ""), RunState.DONE, "Текст сценария", "")
            with patch.object(bridge, "load_settings", return_value=settings), \
                 patch.object(bridge, "save_settings"), \
                 patch.object(bridge, "load_session", return_value=(["Тема"], [job])), \
                 patch.object(bridge, "snapshot", return_value={"ok": True}), \
                 patch.object(bridge, "WProjectClient", TemporarilyUnavailableWProject), \
                 patch.object(bridge.time, "sleep"), \
                 self.assertRaisesRegex(RuntimeError, "503 WProject"):
                bridge.generate_voice({"indices": [0]})

        self.assertGreaterEqual(len(TemporarilyUnavailableWProject.idempotency_keys), 2)
        self.assertEqual(len(set(TemporarilyUnavailableWProject.idempotency_keys)), 1)
        self.assertEqual(
            settings.voice_tts_jobs["production-1"]["provider_idempotency_key"],
            TemporarilyUnavailableWProject.idempotency_keys[0],
        )

    def test_wproject_one_failed_task_does_not_cancel_its_neighbor(self):
        """Queue completion is isolated per ProductionItem, including WProject failures."""
        import tempfile
        from unittest.mock import patch

        from scriptor import bridge
        from scriptor.config import Settings, WProjectKey
        from scriptor.core import ScenarioRequest
        from scriptor.runner import Job, RunState

        class FakeWProject:
            submitted: ClassVar[list] = []

            def __init__(self, _key):
                pass

            def create_task(self, text, _filename, _profile, *, threads, idempotency_key=None):
                type(self).submitted.append(text)
                if text == "Второй сценарий":
                    raise RuntimeError("неверный голос")
                return "task-first"

            def wait_download(self, task_id, progress=None):
                return b"WPROJECT"

        with tempfile.TemporaryDirectory() as folder:
            settings = Settings(
                voicer_output_folder=folder, voice_queue_concurrency=2,
                wproject_api_keys=[WProjectKey("W", "test", streams=2)],
                voice_profiles=[{"id": "w", "name": "W", "provider": "wproject", "voice_id": "speaker"}],
                voice_default_profile_id="w",
                idea_production_items=[{"id": "first", "title": "Первый"}, {"id": "second", "title": "Второй"}],
            )
            jobs = [
                Job(ScenarioRequest(0, "Первый", ""), RunState.DONE, "Первый сценарий", ""),
                Job(ScenarioRequest(1, "Второй", ""), RunState.DONE, "Второй сценарий", ""),
            ]
            with patch.object(bridge, "load_settings", return_value=settings), \
                 patch.object(bridge, "save_settings"), \
                 patch.object(bridge, "load_session", return_value=(["Первый", "Второй"], jobs)), \
                 patch.object(bridge, "snapshot", return_value={"ok": True}), \
                 patch.object(bridge, "WProjectClient", FakeWProject), \
                 patch.object(bridge, "validate_voiceover_artifact", return_value=24.0), \
                 self.assertRaisesRegex(RuntimeError, "неверный голос"):
                bridge.generate_voice({"indices": [0, 1]})

        self.assertEqual(set(FakeWProject.submitted), {"Первый сценарий", "Второй сценарий"})
        self.assertEqual(settings.voice_tts_jobs["first"]["state"], "ready")
        self.assertEqual(settings.voice_tts_jobs["second"]["state"], "error")
        self.assertTrue(settings.voice_scenario_outputs["1"].endswith(".mp3"))
        self.assertEqual(settings.voice_scenario_outputs.get("2", ""), "")

    def test_wproject_resume_polls_persisted_remote_task_without_creating_duplicate(self):
        import tempfile
        from pathlib import Path
        from unittest.mock import patch

        from scriptor import bridge
        from scriptor.config import Settings, WProjectKey
        from scriptor.core import ScenarioRequest
        from scriptor.runner import Job, RunState

        class FakeWProject:
            created = 0
            waited: ClassVar[list] = []
            def __init__(self, _key):
                pass
            def create_task(self, *_args, **_kwargs):
                type(self).created += 1
                raise AssertionError("resume must not create a second WProject task")
            def wait_download(self, task_id, progress=None):
                type(self).waited.append(task_id)
                return b"RESUMED"

        with tempfile.TemporaryDirectory() as folder:
            saved = {
                "id": "job-1", "production_item_id": "production-1", "scenario_index": 0,
                "state": "interrupted", "provider": "wproject", "script_hash": "",
                "settings": {"provider": "wproject", "voice_id": "speaker", "task_threads": 10},
                "remote_task": {"provider": "wproject", "task_id": "remote-task-1", "key_label": "W"},
            }
            settings = Settings(
                voicer_output_folder=folder, voice_queue_concurrency=1,
                wproject_api_keys=[WProjectKey("W", "test", streams=10)],
                voice_tts_jobs={"production-1": saved},
                idea_production_items=[{"id": "production-1", "title": "Тема"}],
            )
            job = Job(ScenarioRequest(0, "Тема", ""), RunState.DONE, "Текст сценария", "")
            with patch.object(bridge, "load_settings", return_value=settings), \
                 patch.object(bridge, "save_settings"), \
                 patch.object(bridge, "load_session", return_value=(["Тема"], [job])), \
                 patch.object(bridge, "snapshot", return_value={"ok": True}), \
                 patch.object(bridge, "WProjectClient", FakeWProject), \
                 patch.object(bridge, "validate_voiceover_artifact", return_value=1.0):
                bridge.generate_voice({"indices": [0], "resume": True})

            self.assertEqual(FakeWProject.created, 0)
            self.assertEqual(FakeWProject.waited, ["remote-task-1"])
            self.assertTrue(Path(settings.voice_scenario_outputs["1"]).is_file())

    def test_wproject_resume_reuses_persisted_idempotency_key_when_task_id_was_lost(self):
        import tempfile
        from unittest.mock import patch

        from scriptor import bridge
        from scriptor.config import Settings, WProjectKey
        from scriptor.core import ScenarioRequest
        from scriptor.runner import Job, RunState

        class FakeWProject:
            created_with: ClassVar[list] = []
            waited: ClassVar[list] = []
            def __init__(self, _key):
                pass
            def create_task(self, *_args, idempotency_key=None, **_kwargs):
                type(self).created_with.append(idempotency_key)
                return "recovered-task"
            def wait_download(self, task_id, progress=None):
                type(self).waited.append(task_id)
                return b"RESUMED"

        with tempfile.TemporaryDirectory() as folder:
            saved = {
                "id": "job-1", "production_item_id": "production-1", "scenario_index": 0,
                "state": "interrupted", "provider": "wproject", "script_hash": "",
                "settings": {"provider": "wproject", "voice_id": "speaker", "task_threads": 10},
                "provider_idempotency_key": "persisted-idempotency-key",
            }
            settings = Settings(
                voicer_output_folder=folder, voice_queue_concurrency=1,
                wproject_api_keys=[WProjectKey("W", "test", streams=10)],
                voice_tts_jobs={"production-1": saved},
                idea_production_items=[{"id": "production-1", "title": "Тема"}],
            )
            job = Job(ScenarioRequest(0, "Тема", ""), RunState.DONE, "Текст сценария", "")
            with patch.object(bridge, "load_settings", return_value=settings), \
                 patch.object(bridge, "save_settings"), \
                 patch.object(bridge, "load_session", return_value=(["Тема"], [job])), \
                 patch.object(bridge, "snapshot", return_value={"ok": True}), \
                 patch.object(bridge, "WProjectClient", FakeWProject), \
                 patch.object(bridge, "validate_voiceover_artifact", return_value=1.0):
                bridge.generate_voice({"indices": [0], "resume": True})

        self.assertEqual(FakeWProject.created_with, ["persisted-idempotency-key"])
        self.assertEqual(FakeWProject.waited, ["recovered-task"])

    def test_generate_one_range_selects_only_its_frozen_items(self):
        from unittest.mock import patch

        from scriptor import bridge
        from scriptor.config import Settings

        settings = Settings(
            voice_profiles=[{"id": "a", "name": "A"}, {"id": "b", "name": "B"}],
            voice_default_profile_id="a",
            voice_ranges=[{"id": "middle", "start": 2, "end": 3, "profile_id": "b", "enabled": True}],
            idea_production_items=[{"id": "one", "title": "1"}, {"id": "two", "title": "2"}, {"id": "three", "title": "3"}],
        )
        with patch.object(bridge, "load_settings", return_value=settings), \
             patch.object(bridge, "load_session", return_value=(["1", "2", "3"], [])), \
             patch.object(bridge, "save_settings"), \
             patch.object(bridge, "generate_voice", return_value={"ok": True}) as generate:
            result = bridge.generate_voice_range({"rangeId": "middle", "force": True})

        self.assertEqual(result, {"ok": True})
        generate.assert_called_once_with({"indices": [1, 2], "force": True})

    def test_resolves_inclusive_ranges_against_frozen_production_item_ids(self):
        from scriptor.tts_ranges import freeze_batch, resolve_assignments

        items = [{"id": f"item-{number}", "title": f"Тема {number}"} for number in range(1, 21)]
        batch = freeze_batch(items)
        profiles = [
            {"id": "voice-a", "name": "Voice A", "provider": "voicegen", "voice_id": "a"},
            {"id": "voice-b", "name": "Voice B", "provider": "voicegen", "voice_id": "b"},
            {"id": "voice-c", "name": "Voice C", "provider": "lumean", "voice_id": "c"},
            {"id": "voice-d", "name": "Voice D", "provider": "lumean", "voice_id": "d"},
        ]
        ranges = [
            {"id": "range-a", "start": 1, "end": 5, "profile_id": "voice-a", "enabled": True},
            {"id": "range-b", "start": 6, "end": 10, "profile_id": "voice-b", "enabled": True},
            {"id": "range-c", "start": 11, "end": 15, "profile_id": "voice-c", "enabled": True},
            {"id": "range-d", "start": 16, "end": 20, "profile_id": "voice-d", "enabled": True},
        ]

        assignments = resolve_assignments(batch, profiles, "voice-a", ranges)

        self.assertEqual([row["production_item_id"] for row in assignments], [item["id"] for item in items])
        self.assertEqual([row["profile"]["id"] for row in assignments], [
            *("voice-a",) * 5, *("voice-b",) * 5, *("voice-c",) * 5, *("voice-d",) * 5,
        ])
        self.assertEqual(assignments[9]["position"], 10)
        self.assertEqual(assignments[9]["range_id"], "range-b")

    def test_gaps_fall_back_to_default_profile(self):
        from scriptor.tts_ranges import freeze_batch, resolve_assignments

        batch = freeze_batch([{"id": f"item-{number}", "title": str(number)} for number in range(1, 31)])
        profiles = [
            {"id": "default", "name": "Default", "provider": "voicegen"},
            {"id": "override", "name": "Override", "provider": "voicegen"},
        ]
        assignments = resolve_assignments(batch, profiles, "default", [
            {"id": "middle", "start": 11, "end": 20, "profile_id": "override", "enabled": True},
        ])

        self.assertEqual(assignments[0]["profile"]["id"], "default")
        self.assertEqual(assignments[10]["profile"]["id"], "override")
        self.assertEqual(assignments[20]["profile"]["id"], "default")

    def test_overlap_blocks_resolution_with_the_intersection(self):
        from scriptor.tts_ranges import (
            RangeValidationError,
            freeze_batch,
            resolve_assignments,
        )

        batch = freeze_batch([{"id": "item-1", "title": "Тема"}])
        with self.assertRaisesRegex(RangeValidationError, "10–15"):
            resolve_assignments(batch, [{"id": "a", "name": "A"}], "a", [
                {"id": "one", "start": 1, "end": 15, "profile_id": "a", "enabled": True},
                {"id": "two", "start": 10, "end": 20, "profile_id": "a", "enabled": True},
            ])

    def test_job_snapshot_remains_unchanged_after_range_profile_changes(self):
        from scriptor.tts_ranges import (
            freeze_batch,
            resolve_assignments,
            snapshot_tts_job,
        )

        batch = freeze_batch([{"id": "item-7", "title": "Тема", "scenario_index": 6}])
        profile = {"id": "voice-old", "name": "Old", "provider": "voicegen", "voice_id": "old", "model_id": "v3"}
        assignment = resolve_assignments(batch, [profile], "voice-old", [
            {"id": "range-1", "start": 1, "end": 10, "profile_id": "voice-old", "enabled": True},
        ])[0]

        snapshot = snapshot_tts_job(assignment, "Сценарий без изменений", output_folder="D:/Audio")
        profile["voice_id"] = "new"

        self.assertEqual(snapshot["production_item_id"], "item-7")
        self.assertEqual(snapshot["range_id"], "range-1")
        self.assertEqual(snapshot["settings"]["voice_id"], "old")
        self.assertEqual(snapshot["script_hash"], "c05b16694565c51fbf77d58d193fe877f8436a4164cd54fcd998df289752ebce")

    def test_job_snapshot_copies_fallback_profiles_before_queue_starts(self):
        from scriptor import bridge
        from scriptor.config import Settings
        from scriptor.core import ScenarioRequest
        from scriptor.runner import Job, RunState

        settings = Settings(
            voice_profiles=[
                {"id": "main", "name": "Main", "provider": "voicegen", "voice_id": "main-voice"},
                {"id": "reserve", "name": "Reserve", "provider": "lumean", "voice_id": "reserve-voice", "fallback": True},
            ],
            voice_default_profile_id="main",
            idea_production_items=[{"id": "production-1", "title": "Тема"}],
        )
        job = Job(ScenarioRequest(0, "Тема", ""), RunState.DONE, "Текст сценария", "")

        queued = bridge.prepare_voice_jobs(settings, ["Тема"], [job], {0}, force=False)
        settings.voice_profiles[1]["voice_id"] = "edited-after-start"

        self.assertEqual(queued[0]["fallback_settings"][0]["voice_id"], "reserve-voice")
        self.assertEqual(queued[0]["script_revision"], queued[0]["script_hash"])


if __name__ == "__main__":
    unittest.main()

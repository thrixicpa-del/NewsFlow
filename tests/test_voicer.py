import json
import tempfile
import threading
import unittest
from copy import deepcopy
from pathlib import Path
from typing import ClassVar
from unittest.mock import patch

from scriptor import bridge
from scriptor.config import (
    LumeanKey,
    SecretVoicerKey,
    Settings,
    VoiceGenKey,
    WProjectKey,
)
from scriptor.core import ScenarioRequest
from scriptor.runner import Job, RunState
from scriptor.voicer import (
    ChromeSecretVoicer,
    LumeanClient,
    SecretVoicerClient,
    VoiceGenClient,
    VoiceProfile,
    WProjectClient,
    safe_audio_name,
    split_text,
)


class VoicerTests(unittest.TestCase):
    def _assert_wproject_concurrency(self, *, jobs_count: int, streams: int, expected_active: int):
        """Measure running provider work, not only an executor configuration."""
        class BlockingWProject:
            lock = threading.Lock()
            active = 0
            max_active = 0
            reached = threading.Event()
            release = threading.Event()

            def __init__(self, _secret):
                pass

            def create_task(self, _text, title, _profile, *, threads, idempotency_key):
                self.title = title
                self.asserted_threads = threads
                self.idempotency_key = idempotency_key
                return title

            def wait_download(self, _task_id, progress=None):
                with self.lock:
                    self.__class__.active += 1
                    self.__class__.max_active = max(self.__class__.max_active, self.__class__.active)
                    if self.__class__.active >= expected_active:
                        self.__class__.reached.set()
                try:
                    if progress:
                        progress("WProject: тестовая блокировка", 50)
                    if not self.__class__.release.wait(3):
                        raise TimeoutError("test provider was not released")
                    return b"MP3"
                finally:
                    with self.lock:
                        self.__class__.active -= 1

        titles = [f"Сценарий {index}" for index in range(jobs_count)]
        jobs = [
            Job(ScenarioRequest(index, title, "", f"production-{index}"), RunState.DONE, f"Текст {index}")
            for index, title in enumerate(titles)
        ]
        errors = []
        with tempfile.TemporaryDirectory() as folder:
            settings = Settings(
                voice_provider="wproject",
                voicer_output_folder=folder,
                voice_queue_concurrency=10,
                wproject_api_keys=[WProjectKey("WProject", "test-key", streams=streams)],
                voice_profiles=[{"id": "wproject-profile", "name": "WProject", "provider": "wproject", "voice_id": "voice-1"}],
                voice_default_profile_id="wproject-profile",
                voice_scenario_outputs={str(index + 1): "" for index in range(jobs_count)},
            )

            def run():
                try:
                    bridge.generate_voice({"indices": list(range(jobs_count))})
                except Exception as error:  # noqa: BLE001 - surface every worker failure after joining
                    errors.append(error)

            with patch.object(bridge, "load_settings", return_value=settings), \
                 patch.object(bridge, "save_settings"), \
                 patch.object(bridge, "load_session", return_value=(titles, jobs)), \
                 patch.object(bridge, "snapshot", return_value={"ok": True}), \
                 patch.object(bridge, "WProjectClient", BlockingWProject), \
                 patch.object(bridge, "validate_voiceover_artifact", return_value=1.0):
                worker = threading.Thread(target=run)
                worker.start()
                self.assertTrue(BlockingWProject.reached.wait(2), "provider did not reach expected concurrency")
                self.assertEqual(BlockingWProject.max_active, expected_active)
                if streams < jobs_count:
                    self.assertEqual(BlockingWProject.active, expected_active)
                BlockingWProject.release.set()
                worker.join(5)

        self.assertFalse(worker.is_alive(), "voice generation thread did not finish")
        self.assertEqual(errors, [])
        self.assertEqual(BlockingWProject.max_active, expected_active)

    def test_global_voice_concurrency_reaches_ten_when_wproject_has_ten_streams(self):
        self._assert_wproject_concurrency(jobs_count=10, streams=10, expected_active=10)

    def test_voice_concurrency_does_not_exceed_wproject_stream_capacity(self):
        self._assert_wproject_concurrency(jobs_count=6, streams=3, expected_active=3)

    def test_template_save_survives_an_independent_running_voice_job(self):
        """A live voice worker must not restore its stale template snapshot."""
        class BlockingVoiceGen:
            reached = threading.Event()
            release = threading.Event()

            def __init__(self, _key):
                pass

            def synthesize(self, _text, _filename, _profile, *, threads, progress=None):
                if progress:
                    progress("VoiceGen: выполняется", 55)
                self.__class__.reached.set()
                if not self.__class__.release.wait(3):
                    raise TimeoutError("test voice provider was not released")
                return b"MP3"

        with tempfile.TemporaryDirectory() as output:
            initial = Settings(
                template="Старый шаблон {title}",
                voice_provider="voicegen",
                voicer_output_folder=output,
                voice_queue_concurrency=1,
                voicegen_api_keys=[VoiceGenKey("VoiceGen", "test-key", streams=1)],
                voice_profiles=[{"id": "voice", "name": "VoiceGen", "provider": "voicegen", "voice_id": "voice-id"}],
                voice_default_profile_id="voice",
                voice_scenario_outputs={"1": ""},
            )
            persisted = {"settings": deepcopy(initial)}
            job = Job(ScenarioRequest(0, "Тема", "", "production-1"), RunState.DONE, "Текст сценария")
            failures: list[Exception] = []

            def load_current_settings():
                return deepcopy(persisted["settings"])

            def save_current_settings(settings):
                persisted["settings"] = deepcopy(settings)

            def run_voice():
                try:
                    bridge.generate_voice({"indices": [0]})
                except Exception as error:  # noqa: BLE001 - worker error is asserted after join
                    failures.append(error)

            with patch.object(bridge, "load_settings", side_effect=load_current_settings), \
                 patch.object(bridge, "save_settings", side_effect=save_current_settings), \
                 patch.object(bridge, "load_session", return_value=(["Тема"], [job])), \
                 patch.object(bridge, "snapshot", return_value={"ok": True}), \
                 patch.object(bridge, "VoiceGenClient", BlockingVoiceGen), \
                 patch.object(bridge, "validate_voiceover_artifact", return_value=1.0):
                worker = threading.Thread(target=run_voice)
                worker.start()
                self.assertTrue(BlockingVoiceGen.reached.wait(2), "voice provider did not start")

                bridge.save_template({"template": "Новый шаблон {title}"})
                self.assertTrue(worker.is_alive(), "saving a template must not wait for voice synthesis")
                self.assertEqual(persisted["settings"].template, "Новый шаблон {title}")

                BlockingVoiceGen.release.set()
                worker.join(5)

        self.assertFalse(worker.is_alive(), "voice generation thread did not finish")
        self.assertEqual(failures, [])
        self.assertEqual(persisted["settings"].template, "Новый шаблон {title}")
        self.assertEqual(persisted["settings"].voice_task_statuses["1"]["label"], "Готово")

    def test_voice_queue_submits_only_current_ready_scenarios_and_marks_unfinished_rows_skipped(self):
        settings = Settings()
        jobs = [
            Job(ScenarioRequest(0, "Готовый", ""), RunState.DONE, "Текст"),
            Job(ScenarioRequest(1, "Не готов", ""), RunState.WAITING, ""),
        ]
        with patch.object(bridge, "load_settings", return_value=settings), \
             patch.object(bridge, "load_session", return_value=(["Готовый", "Не готов"], jobs)), \
             patch.object(bridge, "save_settings"), \
             patch.object(bridge, "generate_voice", return_value={"ok": True}) as generate:
            result = bridge.generate_voice_queue({})

        generate.assert_called_once_with({"indices": [0], "force": False})
        self.assertEqual(result["operationResult"], {
            "kind": "voice-queue", "eligible": 1, "skipped": 1,
            "message": "В очередь озвучки добавлено: 1.",
        })
        self.assertEqual(settings.voice_task_statuses["2"]["label"], "Пропущено: сценарий не готов")

    def test_manual_import_rejects_unreadable_audio_without_attaching_it(self):
        """A file extension alone must never turn a broken MP3 into READY."""
        with tempfile.TemporaryDirectory() as directory, tempfile.TemporaryDirectory() as output:
            source = Path(directory) / "broken.mp3"
            source.write_bytes(b"not an audio stream")
            settings = Settings(voicer_output_folder=output)
            with patch.object(bridge, "load_settings", return_value=settings), \
                 patch.object(bridge, "save_settings"), \
                 patch.object(bridge, "load_session", return_value=(["Сценарий"], [])), \
                 self.assertRaisesRegex(ValueError, "длительность озвучки"):
                bridge.import_voiceover({"scenarioIndex": 0, "path": str(source)})

            self.assertEqual(settings.voice_scenario_outputs, {})
            self.assertEqual(settings.voice_task_statuses, {})

    def test_voice_queue_reconciliation_restores_a_valid_orphaned_mp3_by_production_item(self):
        """A stale provider error may recover only the exact immutable script contract."""
        import hashlib

        from scriptor import config

        with tempfile.TemporaryDirectory() as state_dir, tempfile.TemporaryDirectory() as output:
            settings_path = Path(state_dir) / "settings.json"
            titles = [f"Тема {index}" for index in range(1, 25)] + ["Тема 25"]
            orphan = Path(output) / "025 — Тема 25.mp3"
            orphan.write_bytes(b"recovered-audio")
            script = "Текст сценария"
            script_hash = hashlib.sha256(script.encode("utf-8")).hexdigest()
            job = Job(
                ScenarioRequest(24, "Тема 25", "", "production-25"),
                RunState.DONE,
                script,
            )
            settings = Settings(
                voicer_output_folder=output,
                voice_tts_jobs={"production-25": {
                    "id": "job-25", "production_item_id": "production-25",
                    "scenario_index": 24, "state": "error", "error": "WProject: queue_full",
                    "script_hash": script_hash, "script_revision": script_hash,
                }},
                voice_task_statuses={"25": {"label": "Ошибка озвучки", "progress": 0}},
                idea_production_items=[{"id": "production-25", "title": "Тема 25"}],
            )
            with patch.object(config, "config_path", return_value=settings_path):
                config.save_settings(settings)
                with patch.object(bridge, "load_settings", side_effect=config.load_settings), \
                     patch.object(bridge, "load_session", return_value=(titles, [job])), \
                     patch.object(bridge, "snapshot", return_value={"refreshed": True}), \
                     patch.object(bridge, "validate_voiceover_artifact", return_value=42.0), \
                     patch.object(bridge, "_ensure_ready_voice_maps") as ensure_maps:
                    result = bridge.reconcile_voice_queue({})
                persisted = config.load_settings()

        self.assertEqual(result["operationResult"]["recovered"], 1)
        self.assertEqual(persisted.voice_scenario_outputs["25"], str(orphan))
        self.assertEqual(persisted.voice_task_statuses["25"]["label"], "Готово: восстановлено")
        saved = persisted.voice_tts_jobs["production-25"]
        self.assertEqual(saved["state"], "ready")
        self.assertEqual(saved["output_path"], str(orphan))
        self.assertEqual(saved["artifact"]["path"], str(orphan))
        self.assertEqual(saved["artifact"]["duration_seconds"], 42.0)
        ensure_maps.assert_called_once_with({24})

    def test_voice_queue_reconciliation_matches_newsflow_canonical_long_title_filename(self):
        with tempfile.TemporaryDirectory() as output:
            title = "Очень длинная новостная тема " * 8
            candidate = Path(output) / f"001 — {bridge.safe_filename(title)}.mp3"
            candidate.write_bytes(b"audio")

            self.assertEqual(
                bridge._reconcilable_voice_candidates(Path(output), 0, title),
                [candidate],
            )

    def test_voice_queue_reconciliation_rejects_stale_script_wrong_index_and_non_mp3(self):
        """Number/title alone must never bind old or non-MP3 audio to a current scenario."""
        import hashlib

        script = "Текущий текст"
        correct_hash = hashlib.sha256(script.encode("utf-8")).hexdigest()
        cases = [
            ("stale-script", 0, hashlib.sha256(b"old text").hexdigest(), ".mp3"),
            ("wrong-index", 9, correct_hash, ".mp3"),
            ("wrong-format", 0, correct_hash, ".wav"),
        ]
        for label, saved_index, saved_hash, suffix in cases:
            with self.subTest(label=label), tempfile.TemporaryDirectory() as output:
                candidate = Path(output) / f"001 — Тема 1{suffix}"
                candidate.write_bytes(b"audio")
                job = Job(
                    ScenarioRequest(0, "Тема 1", "", "production-1"),
                    RunState.DONE,
                    script,
                )
                settings = Settings(
                    voicer_output_folder=output,
                    voice_tts_jobs={"production-1": {
                        "id": "job-1", "production_item_id": "production-1",
                        "scenario_index": saved_index, "state": "error",
                        "script_hash": saved_hash,
                    }},
                    idea_production_items=[{"id": "production-1", "title": "Тема 1"}],
                )
                with patch.object(bridge, "load_settings", return_value=settings), \
                     patch.object(bridge, "load_session", return_value=(["Тема 1"], [job])), \
                     patch.object(bridge, "snapshot", return_value={"refreshed": True}), \
                     patch.object(bridge, "validate_voiceover_artifact", return_value=15.0) as validate, \
                     patch.object(bridge, "save_settings") as save:
                    result = bridge.reconcile_voice_queue({})

                self.assertEqual(result["operationResult"]["recovered"], 0)
                self.assertEqual(settings.voice_scenario_outputs, {})
                save.assert_not_called()
                if label == "wrong-format":
                    validate.assert_not_called()

    def test_voice_queue_reconciliation_preserves_concurrent_settings_changes(self):
        """The narrow commit must not rewrite unrelated fields from its stale Settings snapshot."""
        import hashlib

        from scriptor import config

        with tempfile.TemporaryDirectory() as state_dir, tempfile.TemporaryDirectory() as output:
            settings_path = Path(state_dir) / "settings.json"
            orphan = Path(output) / "001 — Тема 1.mp3"
            orphan.write_bytes(b"recovered")
            script = "Текущий сценарий"
            script_hash = hashlib.sha256(script.encode("utf-8")).hexdigest()
            initial = Settings(
                template="До параллельного изменения",
                voicer_output_folder=output,
                voice_tts_jobs={"production-1": {
                    "id": "job-1", "production_item_id": "production-1",
                    "scenario_index": 0, "state": "error", "script_hash": script_hash,
                }},
                idea_production_items=[{"id": "production-1", "title": "Тема 1"}],
            )
            job = Job(
                ScenarioRequest(0, "Тема 1", "", "production-1"),
                RunState.DONE,
                script,
            )
            with patch.object(config, "config_path", return_value=settings_path):
                config.save_settings(initial)

                def reconcile_after_concurrent_edit(updates):
                    concurrent = config.load_settings()
                    concurrent.template = "Параллельное изменение сохранено"
                    config.save_settings(concurrent)
                    return config.reconcile_voice_outputs(updates)

                with patch.object(bridge, "load_settings", side_effect=config.load_settings), \
                     patch.object(bridge, "reconcile_voice_outputs", side_effect=reconcile_after_concurrent_edit), \
                     patch.object(bridge, "load_session", return_value=(["Тема 1"], [job])), \
                     patch.object(bridge, "snapshot", return_value={"refreshed": True}), \
                     patch.object(bridge, "validate_voiceover_artifact", return_value=17.0), \
                     patch.object(bridge, "_ensure_ready_voice_maps"):
                    result = bridge.reconcile_voice_queue({})
                persisted = config.load_settings()

        self.assertEqual(result["operationResult"]["recovered"], 1)
        self.assertEqual(persisted.template, "Параллельное изменение сохранено")
        self.assertEqual(persisted.voice_tts_jobs["production-1"]["state"], "ready")

    def test_voice_queue_reconciliation_blocks_if_worker_becomes_active_before_commit(self):
        """A worker that starts after scanning still wins the compare-and-swap."""
        import hashlib

        from scriptor import config

        with tempfile.TemporaryDirectory() as state_dir, tempfile.TemporaryDirectory() as output:
            settings_path = Path(state_dir) / "settings.json"
            orphan = Path(output) / "001 — Тема 1.mp3"
            orphan.write_bytes(b"recovered")
            script = "Текущий сценарий"
            script_hash = hashlib.sha256(script.encode("utf-8")).hexdigest()
            initial = Settings(
                voicer_output_folder=output,
                voice_tts_jobs={"production-1": {
                    "id": "job-1", "production_item_id": "production-1",
                    "scenario_index": 0, "state": "error", "script_hash": script_hash,
                }},
                idea_production_items=[{"id": "production-1", "title": "Тема 1"}],
            )
            job = Job(
                ScenarioRequest(0, "Тема 1", "", "production-1"),
                RunState.DONE,
                script,
            )
            with patch.object(config, "config_path", return_value=settings_path):
                config.save_settings(initial)

                def reconcile_after_worker_starts(updates):
                    concurrent = config.load_settings()
                    concurrent.voice_tts_jobs["production-1"]["state"] = "running"
                    config.save_settings(concurrent)
                    return config.reconcile_voice_outputs(updates)

                with patch.object(bridge, "load_settings", side_effect=config.load_settings), \
                     patch.object(bridge, "reconcile_voice_outputs", side_effect=reconcile_after_worker_starts), \
                     patch.object(bridge, "load_session", return_value=(["Тема 1"], [job])), \
                     patch.object(bridge, "snapshot", return_value={"refreshed": True}), \
                     patch.object(bridge, "validate_voiceover_artifact", return_value=17.0), \
                     patch.object(bridge, "_ensure_ready_voice_maps") as ensure_maps:
                    result = bridge.reconcile_voice_queue({})
                persisted = config.load_settings()

        self.assertEqual(result["operationResult"]["recovered"], 0)
        self.assertEqual(result["operationResult"]["blocked"], 1)
        self.assertEqual(persisted.voice_tts_jobs["production-1"]["state"], "running")
        self.assertEqual(persisted.voice_scenario_outputs, {})
        ensure_maps.assert_not_called()

    def test_voice_queue_reconciliation_does_not_touch_files_while_a_worker_is_active(self):
        with tempfile.TemporaryDirectory() as output:
            orphan = Path(output) / "001 — Тема 1.mp3"
            orphan.write_bytes(b"must-not-be-probed")
            settings = Settings(
                voicer_output_folder=output,
                voice_tts_jobs={"production-1": {
                    "id": "job-1", "production_item_id": "production-1", "scenario_index": 0,
                    "state": "running",
                }},
            )
            with patch.object(bridge, "load_settings", return_value=settings), \
                 patch.object(bridge, "snapshot", return_value={"refreshed": True}), \
                 patch.object(bridge, "validate_voiceover_artifact") as validate, \
                 patch.object(bridge, "save_settings") as save:
                result = bridge.reconcile_voice_queue({})

        self.assertEqual(result["operationResult"]["blocked"], 1)
        self.assertEqual(result["operationResult"]["recovered"], 0)
        validate.assert_not_called()
        save.assert_not_called()

    def test_generated_voice_marks_invalid_audio_as_error_not_ready(self):
        """A provider response is not READY until the saved audio is decodable."""
        class FakeClient:
            def __init__(self, _key):
                pass

            def synthesize(self, _text, _profile, progress=None):
                if progress:
                    progress("Secret Voicer обрабатывает текст", 62)
                return b"not an audio stream"

            def save_audio(self, folder, name, content):
                target = Path(folder) / f"{name}.mp3"
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(content)
                return target

        with tempfile.TemporaryDirectory() as folder:
            settings = Settings(
                voice_provider="api", voicer_output_folder=folder,
                secret_voicer_keys=[SecretVoicerKey("Тест", "key")], voice_scenario_outputs={"1": ""},
                voice_profiles=[{"id": "api-profile", "name": "API", "provider": "api", "voice_id": "voice-1"}],
                voice_default_profile_id="api-profile",
            )
            job = Job(ScenarioRequest(0, "Сценарий", ""), RunState.DONE, "Точный текст", "")
            with patch.object(bridge, "load_settings", return_value=settings), \
                 patch.object(bridge, "save_settings"), \
                 patch.object(bridge, "load_session", return_value=(["Сценарий"], [job])), \
                 patch.object(bridge, "snapshot", return_value={"ok": True}), \
                 patch.object(bridge, "SecretVoicerClient", FakeClient), \
                 self.assertRaisesRegex(RuntimeError, "длительность озвучки"):
                bridge.generate_voice({"indices": [0]})

        self.assertEqual(settings.voice_scenario_outputs["1"], "")
        self.assertEqual(settings.voice_task_statuses["1"]["label"], "Ошибка озвучки")

    def test_recursive_audio_scan_matches_parent_folder_and_leaves_ambiguous_unattached(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            exact = root / "ПВО отражает атаку — последствия для города"
            ambiguous = root / "Мирные переговоры"
            unmatched = root / "Чужая тема"
            for folder, name in ((exact, "40_narration.mp3"), (ambiguous, "41_narration.mp3"), (unmatched, "42_narration.wav")):
                folder.mkdir()
                (folder / name).write_bytes(b"audio")

            result = bridge.scan_voiceover_folder(root, [
                "ПВО отражает атаку: последствия для города",
                "Мирные переговоры России и Украины",
                "Мирные переговоры США и Ирана",
            ])

        self.assertEqual(result["foldersFound"], 3)
        self.assertEqual(result["audioFound"], 3)
        self.assertEqual([item["scenarioIndex"] for item in result["matched"]], [0])
        self.assertEqual(len(result["requiresChoice"]), 1)
        self.assertEqual(len(result["unmatched"]), 1)
        self.assertEqual(result["errors"], [])

    def test_folder_import_copies_only_unique_matches_and_persists_review_summary(self):
        with tempfile.TemporaryDirectory() as directory, tempfile.TemporaryDirectory() as output:
            root = Path(directory)
            source = root / "ПВО отражает атаку — последствия для города" / "40_narration.mp3"
            source.parent.mkdir()
            source.write_bytes(b"original-audio")
            settings = Settings(voicer_output_folder=output)
            titles = ["ПВО отражает атаку: последствия для города"]
            with patch.object(bridge, "load_settings", return_value=settings), \
                 patch.object(bridge, "save_settings"), \
                 patch.object(bridge, "load_session", return_value=(titles, [])), \
                 patch.object(bridge, "snapshot", return_value={"reloaded": True}), \
                 patch.object(bridge, "validate_voiceover_artifact", return_value=1.0):
                result = bridge.import_voiceover_folder({"root": str(root)})

            attached = Path(settings.voice_scenario_outputs["1"])
            self.assertTrue(source.is_file())
            self.assertEqual(source.read_bytes(), b"original-audio")
            self.assertTrue(attached.is_file())
            self.assertEqual(attached.read_bytes(), b"original-audio")
            self.assertEqual(settings.voice_task_statuses["1"]["label"], "Готово: импорт из папки")
            self.assertEqual(settings.voice_import_summary["matched"], 1)
            self.assertEqual(result["operationResult"]["matched"], 1)

    def test_folder_import_keeps_an_existing_different_audio_copy(self):
        with tempfile.TemporaryDirectory() as directory, tempfile.TemporaryDirectory() as output:
            root = Path(directory)
            source = root / "ПВО отражает атаку — последствия для города" / "40_narration.mp3"
            source.parent.mkdir()
            source.write_bytes(b"recovered-audio")
            previous = Path(output) / "Импортированные" / "0001_ПВО отражает атаку последствия для города.mp3"
            previous.parent.mkdir(parents=True)
            previous.write_bytes(b"older-audio")
            settings = Settings(voicer_output_folder=output)
            titles = ["ПВО отражает атаку: последствия для города"]
            with patch.object(bridge, "load_settings", return_value=settings), \
                 patch.object(bridge, "save_settings"), \
                 patch.object(bridge, "load_session", return_value=(titles, [])), \
                 patch.object(bridge, "snapshot", return_value={"reloaded": True}), \
                 patch.object(bridge, "validate_voiceover_artifact", return_value=1.0):
                bridge.import_voiceover_folder({"root": str(root)})

            attached = Path(settings.voice_scenario_outputs["1"])
            self.assertEqual(previous.read_bytes(), b"older-audio")
            self.assertEqual(attached.read_bytes(), b"recovered-audio")
            self.assertIn("Восстановлено", str(attached))

    def test_normalizes_numbered_audio_filename_for_scenario_matching(self):
        from scriptor.bridge import audio_title_key
        self.assertEqual(audio_title_key("001 — Тема: Ормуз.mp3"), audio_title_key("Тема Ормуз"))

    class _ConfigurePage:
        def __init__(self, accepted_text: str):
            self.accepted_text = accepted_text
            self.calls = []

        def evaluate(self, script, value=None):
            self.calls.append((script, value))
            if "эмоциональн|emotional" in script:
                return True
            if "data-newsflow-voice-text" in script and "return area ?" in script:
                return self.accepted_text
            if "const areas" in script:
                return {"found": True, "value": value["text"]}
            raise AssertionError("Unexpected browser script")

        def wait_for_timeout(self, _milliseconds):
            pass

    def test_splits_long_text_at_sentence_boundary(self):
        text = "Первая часть. " + "слово " * 30 + "Вторая часть."
        chunks = split_text(text, 40)
        self.assertGreater(len(chunks), 1)
        self.assertEqual(" ".join(chunks).replace(". Вторая", ". Вторая"), text.strip())
        self.assertTrue(all(len(item) <= 40 for item in chunks))

    def test_synthesizes_and_saves_audio(self):
        client = SecretVoicerClient("secret", poll_seconds=0)
        response = iter([
            (json.dumps({"task_id": "task-1"}).encode(), "application/json"),
            (json.dumps({"status": "PROCESSING", "progress": 0.5}).encode(), "application/json"),
            (json.dumps({"status": "COMPLETED", "audio_url": "https://audio.test/file.mp3"}).encode(), "application/json"),
            (b"MP3", "audio/mpeg"),
        ])
        with patch.object(client, "_request", side_effect=response):
            progress = []
            result = client.synthesize("Привет", VoiceProfile(voice_id="voice-1"),
                                       lambda label, value: progress.append((label, value)))
        self.assertEqual(result, b"MP3")
        self.assertEqual(progress[-1][1], 100)
        with tempfile.TemporaryDirectory() as folder:
            saved = client.save_audio(Path(folder), "Новости: тест", result)
            self.assertEqual(saved.name, "Новости_ тест.mp3")
            self.assertEqual(saved.read_bytes(), b"MP3")

    def test_lumean_template_is_reused_only_for_matching_voice_settings(self):
        profile = VoiceProfile(voice_id="voice-1", provider="lumean", model_id="eleven_multilingual_v2",
                               stability=.30, style=.50)
        signature = LumeanClient.template_signature(profile)
        self.assertTrue(signature)
        self.assertNotEqual(signature, LumeanClient.template_signature(
            VoiceProfile(voice_id="voice-1", provider="lumean", model_id="other", stability=.30, style=.50)
        ))

    def test_lumean_synthesis_creates_template_then_downloads_finished_order(self):
        client = LumeanClient("test", poll_seconds=0)
        profile = VoiceProfile(voice_id="voice-1", provider="lumean", model_id="eleven_multilingual_v2")
        with patch.object(client, "create_template", return_value="template-1") as create_template, \
             patch.object(client, "create_order", return_value="order-1"), \
             patch.object(client, "_wait_order", return_value=["audio/test.mp3"]), \
             patch.object(client, "_download_storage", return_value=b"MP3"):
            content, template_id, signature = client.synthesize("Текст", profile)
        self.assertEqual(content, b"MP3")
        self.assertEqual(template_id, "template-1")
        self.assertEqual(signature, LumeanClient.template_signature(profile))
        create_template.assert_called_once_with(profile)

    def test_lumean_voice_task_marks_status_and_keeps_template_cache(self):
        class FakeLumean:
            def __init__(self, _key):
                pass
            def synthesize(self, _text, _profile, progress=None):
                if progress:
                    progress("Lumean создаёт озвучку", 68)
                return b"MP3", "template-1", "signature-1"

        with tempfile.TemporaryDirectory() as folder:
            settings = Settings(voice_provider="lumean", voicer_output_folder=folder,
                lumean_api_keys=[LumeanKey("Lumean", "key", streams=2)],
                voice_profiles=[{"name": "Lumean news", "provider": "lumean", "voice_id": "voice-1",
                                 "model_id": "eleven_multilingual_v2", "stability": .3, "style": .5}],
                voice_scenario_outputs={"1": ""})
            job = Job(ScenarioRequest(0, "Сценарий", ""), RunState.DONE, "Точный текст", "")
            with patch.object(bridge, "load_settings", return_value=settings), \
                 patch.object(bridge, "save_settings"), \
                 patch.object(bridge, "load_session", return_value=(["Сценарий"], [job])), \
                 patch.object(bridge, "snapshot", return_value={"ok": True}), \
                 patch.object(bridge, "LumeanClient", FakeLumean), \
                 patch.object(bridge, "validate_voiceover_artifact", return_value=1.0):
                bridge.generate_voice({"indices": [0]})
            self.assertTrue(Path(settings.voice_scenario_outputs["1"]).is_file())
        self.assertEqual(settings.voice_task_statuses["1"]["label"], "Готово")
        self.assertEqual(settings.voice_profiles[0]["template_id"], "template-1")

    def test_voicegen_task_uses_profile_preset_and_key_streams(self):
        class FakeVoiceGen:
            calls: ClassVar[list] = []
            def __init__(self, _key):
                pass
            def synthesize(self, text, filename, profile, *, threads, progress=None):
                self.calls.append((text, filename, profile, threads))
                if progress:
                    progress("VoiceGen: создаёт озвучку", 72)
                return b"MP3"

        with tempfile.TemporaryDirectory() as folder:
            settings = Settings(voice_provider="voicegen", voicer_output_folder=folder,
                voicegen_api_keys=[VoiceGenKey("VoiceGen", "key", streams=7)],
                voice_profiles=[{"name": "V3", "provider": "voicegen", "voice_id": "voice-1",
                                 "model_id": "elevenLabsV3", "settings_preset": "expressive",
                                 "chunk_size": 1200, "delay_between_chunks": .5, "task_threads": 9}], voice_scenario_outputs={"1": ""})
            job = Job(ScenarioRequest(0, "Сценарий", ""), RunState.DONE, "Точный текст", "")
            with patch.object(bridge, "load_settings", return_value=settings), \
                 patch.object(bridge, "save_settings"), \
                 patch.object(bridge, "load_session", return_value=(["Сценарий"], [job])), \
                 patch.object(bridge, "snapshot", return_value={"ok": True}), \
                 patch.object(bridge, "VoiceGenClient", FakeVoiceGen), \
                 patch.object(bridge, "validate_voiceover_artifact", return_value=1.0):
                bridge.generate_voice({"indices": [0]})
            self.assertTrue(Path(settings.voice_scenario_outputs["1"]).is_file())
        self.assertEqual(settings.voice_task_statuses["1"]["label"], "Готово")
        self.assertEqual(FakeVoiceGen.calls[0][3], 9)

    def test_voicegen_client_sends_direct_v3_task_and_downloads_result(self):
        client = VoiceGenClient("test", poll_seconds=0)
        profile = VoiceProfile(voice_id="voice-1", provider="voicegen", model_id="elevenLabsV3",
                               settings_preset="expressive", chunk_size=1200, delay_between_chunks=.5)
        with patch.object(client, "create_task", return_value="task-1") as create, \
             patch.object(client, "wait_download", return_value=b"MP3"):
            self.assertEqual(client.synthesize("Текст", "voice.mp3", profile, threads=4), b"MP3")
        create.assert_called_once()

    def test_wproject_client_uses_official_async_task_contract(self):
        client = WProjectClient("WA-test", poll_seconds=0)
        profile = VoiceProfile(
            voice_id="voice-1", provider="wproject", task_threads=10,
            wproject_split="single", wproject_join=True, wproject_join_pause=.4,
            wproject_autotag="medium", wproject_prosody_speed=1.1,
            wproject_prosody_volume=2, wproject_latency="balanced",
            wproject_normalize=True, wproject_normalize_loudness=True,
            wproject_tag_compat=True,
        )
        with patch.object(client, "_json", return_value={"task_id": "task-1", "state": "queued"}) as request:
            self.assertEqual(client.create_task("Текст", "Тема", profile, threads=50), "task-1")
        body = request.call_args.args[2]
        self.assertEqual(request.call_args.args[:2], ("POST", "/v1/tts"))
        self.assertEqual(body["voice_id"], "voice-1")
        self.assertEqual(body["threads"], 50)
        self.assertEqual(body["params"], {
            "split": "single", "join": True, "join_pause": .4, "autotag": "medium",
            "prosody_speed": 1.1, "prosody_volume": 2, "latency": "balanced",
            "normalize": True, "normalize_loudness": True, "tag_compat": True,
        })

    def test_wproject_task_submission_sends_the_required_idempotency_key(self):
        """A retry must carry the durable key mandated by POST /v1/tts."""
        client = WProjectClient("WA-test", poll_seconds=0)
        profile = VoiceProfile(voice_id="voice-1", provider="wproject")
        with patch.object(client, "_json", return_value={"task_id": "task-1"}) as request:
            self.assertEqual(
                client.create_task(
                    "Текст", "Тема", profile, threads=1,
                    idempotency_key="newsflow:voice:stable-job-1",
                ),
                "task-1",
            )
        self.assertEqual(
            request.call_args.kwargs["headers"],
            {"Idempotency-Key": "newsflow:voice:stable-job-1"},
        )

    def test_wproject_http_request_keeps_the_idempotency_header(self):
        """The required header must reach urllib, not stop at the JSON wrapper."""
        class Response:
            class Headers:
                @staticmethod
                def get_content_type():
                    return "application/json"

            headers = Headers()

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            @staticmethod
            def read():
                return b'{"task_id":"task-1"}'

        client = WProjectClient("WA-test", poll_seconds=0)
        with patch("scriptor.voicer._wait_for_wproject_http_slot") as rate_gate, \
             patch("scriptor.voicer.urllib.request.urlopen", return_value=Response()) as open_url:
            self.assertEqual(
                client._json("POST", "/v1/tts", {"text": "Текст"},
                             headers={"Idempotency-Key": "stable-idempotency-key"}),
                {"task_id": "task-1"},
            )

        rate_gate.assert_called_once_with()
        request = open_url.call_args.args[0]
        self.assertEqual(request.get_header("Idempotency-key"), "stable-idempotency-key")

    def test_wproject_local_http_limiter_waits_before_exceeding_budget(self):
        from collections import deque

        from scriptor import voicer

        requests = deque([10.0, 20.0])
        with patch.object(voicer, "_WPROJECT_HTTP_RATE_LIMIT", 2), \
             patch.object(voicer, "_WPROJECT_HTTP_RATE_WINDOW_SECONDS", 60.0), \
             patch.object(voicer, "_WPROJECT_HTTP_REQUESTS", requests), \
             patch.object(voicer.time, "monotonic", side_effect=[30.0, 70.1]), \
             patch.object(voicer.time, "sleep") as sleep:
            voicer._wait_for_wproject_http_slot()

        sleep.assert_called_once()
        self.assertAlmostEqual(sleep.call_args.args[0], 40.0)
        self.assertEqual(list(requests), [20.0, 70.1])

    def test_non_windows_ffmpeg_resolution_ignores_bundled_exe(self):
        from scriptor import timeline

        with patch.object(timeline.sys, "platform", "linux"), \
             patch.object(timeline.shutil, "which", return_value="/usr/bin/ffmpeg") as which:
            self.assertEqual(timeline.ffmpeg_executable(), "/usr/bin/ffmpeg")

        which.assert_called_once_with("ffmpeg")

    def test_safe_audio_name(self):
        self.assertEqual(safe_audio_name("  <news>?  "), "news.mp3")

    def test_browser_provider_recognizes_only_authorized_app_url(self):
        self.assertTrue(ChromeSecretVoicer._authorized_url("https://secretvoicer.com/app/"))
        self.assertFalse(ChromeSecretVoicer._authorized_url("https://secretvoicer.com/login/"))
        self.assertFalse(ChromeSecretVoicer._authorized_url("https://example.test/app/"))

    def test_browser_provider_requires_the_current_scenario_in_history(self):
        scenario = "Первый сценарий про Ормузский пролив и нефть. " + "текст " * 12
        candidates = [
            {"href": "https://audio.test/old.mp3", "text": "Другой старый сценарий"},
            {"href": "https://audio.test/current.mp3", "text": scenario},
        ]
        self.assertEqual(
            ChromeSecretVoicer._matching_audio_href(scenario, candidates),
            "https://audio.test/current.mp3",
        )
        self.assertEqual(
            ChromeSecretVoicer._matching_audio_href(scenario, candidates[:1]), ""
        )

    def test_history_preview_is_matched_before_its_download_button(self):
        scenario = "Тегеран усиливает давление на Ормузский пролив. " + "Контекст " * 10
        rows = [
            {"id": "old", "text": "Старый текст про другие события", "href": "", "hasDownload": True},
            {"id": "current", "text": scenario[:110] + "…", "href": "", "hasDownload": True},
        ]
        match = ChromeSecretVoicer._matching_history_candidate(scenario, rows)
        self.assertIsNotNone(match)
        self.assertEqual(match["id"], "current")

    def test_browser_configure_inserts_and_verifies_exact_scenario_text(self):
        text = "Точный текст сценария для озвучки."
        page = self._ConfigurePage(text)
        ChromeSecretVoicer(Path("unused"))._configure(page, text, VoiceProfile())
        text_write = next(value for script, value in page.calls if "const areas" in script)
        self.assertEqual(text_write["text"], text)

    def test_browser_configure_refuses_to_start_when_site_keeps_old_text(self):
        page = self._ConfigurePage("Старый текст из предыдущей вкладки")
        with self.assertRaisesRegex(Exception, "не принял текст текущего сценария"):
            ChromeSecretVoicer(Path("unused"))._configure(
                page, "Новый текст, который нельзя подменять.", VoiceProfile()
            )

    def test_voice_status_is_saved_per_completed_task(self):
        class FakeClient:
            def __init__(self, _key):
                pass

            def synthesize(self, _text, _profile, progress=None):
                if progress:
                    progress("Secret Voicer обрабатывает текст", 62)
                return b"MP3"

            def save_audio(self, folder, name, content):
                target = Path(folder) / f"{name}.mp3"
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(content)
                return target

        with tempfile.TemporaryDirectory() as folder:
            settings = Settings(
                voice_provider="api",
                voicer_output_folder=folder,
                secret_voicer_keys=[SecretVoicerKey("Тест", "key")],
                voice_scenario_outputs={"1": ""},
                voice_profiles=[{"id": "api-profile", "name": "API", "provider": "api", "voice_id": "voice-1"}],
                voice_default_profile_id="api-profile",
            )
            job = Job(ScenarioRequest(0, "Сценарий", ""), RunState.DONE, "Точный текст", "")
            with patch.object(bridge, "load_settings", return_value=settings), \
                 patch.object(bridge, "save_settings") as save_settings, \
                 patch.object(bridge, "load_session", return_value=(["Сценарий"], [job])), \
                 patch.object(bridge, "snapshot", return_value={"ok": True}), \
                 patch.object(bridge, "SecretVoicerClient", FakeClient), \
                 patch.object(bridge, "validate_voiceover_artifact", return_value=1.0):
                result = bridge.generate_voice({"indices": [0]})
            self.assertEqual(result, {"ok": True})
            self.assertEqual(settings.voice_task_statuses["1"]["label"], "Готово")
            self.assertEqual(settings.voice_task_statuses["1"]["progress"], 100)
            self.assertEqual(settings.voice_task_statuses["1"]["durationSeconds"], 1.0)
            self.assertTrue(Path(settings.voice_scenario_outputs["1"]).is_file())
            saved_job = next(iter(settings.voice_tts_jobs.values()))
            self.assertEqual(saved_job["artifact"]["duration_seconds"], 1.0)
            self.assertEqual(saved_job["artifact"]["path"], settings.voice_scenario_outputs["1"])
            self.assertGreaterEqual(save_settings.call_count, 3)

    def test_only_transient_browser_errors_are_retried(self):
        self.assertTrue(bridge._retryable_browser_voice_error(RuntimeError("Таймаут ожидания MP3")))
        self.assertTrue(bridge._retryable_browser_voice_error(RuntimeError("Secret Voicer не принял текст")))
        self.assertFalse(bridge._retryable_browser_voice_error(RuntimeError("Chrome не авторизован в Secret Voicer")))
        self.assertFalse(bridge._retryable_browser_voice_error(RuntimeError("Закройте окно Chrome, открытое для входа")))

    def test_voice_error_reason_is_kept_for_the_queue_row(self):
        self.assertEqual(
            bridge._voice_error_reason(RuntimeError("  Chrome  не   принял\nтекст  ")),
            "Chrome не принял текст",
        )
        self.assertLessEqual(len(bridge._voice_error_reason(RuntimeError("x" * 900))), 700)

    def test_voice_failover_detects_limits_but_not_completed_audio_errors(self):
        self.assertTrue(bridge._can_failover_voice(RuntimeError("429 rate limit")))
        self.assertTrue(bridge._can_failover_voice(RuntimeError("Active subscription required")))
        self.assertFalse(bridge._can_failover_voice(RuntimeError("пустой MP3")))

    def test_wproject_catalog_and_pool_settings_are_read_only_and_persisted(self):
        class FakeWProject:
            def __init__(self, _key):
                pass
            def profile(self):
                return {"id": "account-1", "plan": "pro"}
            def usage(self):
                return {"characters": {"used": 12, "limit": 1000}}
            def voices(self):
                return [{"id": "voice-1", "name": "Новости"}]

        settings = Settings(wproject_api_keys=[WProjectKey("WProject основной", "WA-test", streams=2)])
        with patch.object(bridge, "load_settings", return_value=settings), \
             patch.object(bridge, "save_settings"), \
             patch.object(bridge, "snapshot", return_value={"ok": True}), \
             patch.object(bridge, "WProjectClient", FakeWProject):
            bridge.update_wproject_key_settings({"keys": [{"index": 0, "active": True, "streams": 10}]})
            result = bridge.refresh_wproject_catalog({})

        self.assertEqual(settings.wproject_api_keys[0].streams, 10)
        self.assertEqual(settings.wproject_voice_cache, [{"id": "voice-1", "name": "Новости"}])
        self.assertEqual(settings.wproject_profile_cache["id"], "account-1")
        self.assertEqual(settings.wproject_usage_cache["characters"]["limit"], 1000)
        self.assertEqual(result["operationResult"]["kind"], "wproject-catalog")

    def test_wproject_key_is_supported_by_common_api_key_commands(self):
        settings = Settings()
        with patch.object(bridge, "load_settings", return_value=settings), \
             patch.object(bridge, "save_settings"), \
             patch.object(bridge, "snapshot", return_value={"ok": True}):
            bridge.add_api_key({"kind": "wproject", "label": "W", "secret": "WA-test"})
            bridge.set_key_active({"kind": "wproject", "index": 0, "active": False})
            bridge.save_api_key_note({"kind": "wproject", "index": 0, "note": "основной"})

        self.assertFalse(settings.wproject_api_keys[0].active)
        self.assertEqual(settings.api_key_notes[bridge._api_key_id("wproject", 0)], "основной")

    def test_voice_range_preset_roundtrip_keeps_enabled_ranges_and_backup_profiles(self):
        settings = Settings(voice_profiles=[{"name": "Основной", "provider": "voicegen"}],
                            voice_ranges=[{"start": 1, "end": 3, "profile": 0, "enabled": True}])
        with patch.object(bridge, "load_settings", return_value=settings), \
             patch.object(bridge, "save_settings"), patch.object(bridge, "snapshot", return_value={"ok": True}):
            bridge.save_voice_range_preset({"name": "Новости", "profiles": settings.voice_profiles,
                                            "ranges": settings.voice_ranges, "keyFailover": True})
        self.assertEqual(settings.voice_range_presets[0]["ranges"][0]["enabled"], True)


if __name__ == "__main__":
    unittest.main()

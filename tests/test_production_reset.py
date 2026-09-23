"""Durable, disposable-storage acceptance regressions for RESET-001."""

import os
import threading
import unittest
from hashlib import sha256
from json import dumps
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import ClassVar
from unittest.mock import patch

from scriptor import bridge, config
from scriptor.config import Settings, load_settings, save_settings
from scriptor.core import ScenarioRequest
from scriptor.runner import Job, RunState
from scriptor.session import load_session, save_session, session_path


class ProductionResetTests(unittest.TestCase):
    confirmation: ClassVar[dict[str, object]] = {"confirmed": True, "confirmationPhrase": "УДАЛИТЬ ПРОИЗВОДСТВО"}

    def _settings(self, root: Path) -> Settings:
        outputs = {name: root / "production" / name for name in (
            "scripts", "voice", "covers", "seo", "media", "cutter", "downloads",
            "mixer", "montage", "projects",
        )}
        settings = Settings(
            output_folder=str(outputs["scripts"]),
            voicer_output_folder=str(outputs["voice"]),
            cover_output_folder=str(outputs["covers"]),
            seo_output_folder=str(outputs["seo"]),
            media_output_folder=str(outputs["media"]),
            cutter_output_folder=str(outputs["cutter"]),
            footage_download_folder=str(outputs["downloads"]),
            mixer_output_folder=str(outputs["mixer"]),
            montage_output_folder=str(outputs["montage"]),
            montage_project_folder=str(outputs["projects"]),
            results_output_folder=str(root / "preserved-results-root"),
            results_last_export_folder=str(root / "old-results-batch"),
            montage_task_statuses={"0": {"production_item_id": "old-id", "status": "Готово"}},
            idea_results=["Старая тема"],
            idea_production_items=[{"id": "old-id", "title": "Старая тема"}],
            cover_queue=[{"production_item_id": "old-id", "title": "Старая тема"}],
            seo_queue=[{"production_item_id": "old-id", "source_title": "Старая тема"}],
            voice_task_statuses={"1": {"production_item_id": "old-id", "status": "Готово"}},
            voice_tts_batches=[{"id": "old-batch", "productionItemId": "old-id"}],
            voice_active_tts_batch_id="old-batch",
            voice_tts_jobs={"old-id": {"productionItemId": "old-id"}},
            voice_import_summary={"root": "old-import", "matched": 1},
            youtube_publication_items={"old-id": {"productionItemId": "old-id"}},
            youtube_publication_plan_versions=[{"id": "old-plan", "assignments": [{"productionItemId": "old-id"}]}],
            youtube_publication_assignments={"old-id": {"productionItemId": "old-id"}},
            youtube_engagement_tasks=[{"productionItemId": "old-id"}],
            cover_rate_usage_events=[{"at": "2026-09-23T12:00:00+03:00", "count": 3}],
            youtube_oauth_tokens={"channel": "preserved-token"},
            youtube_publication_v2_rule_presets=[{"name": "preserved-rule"}],
        )
        for folder in self._production_folders(settings):
            folder.mkdir(parents=True, exist_ok=True)
            (folder / "old-release.txt").write_text(folder.name, encoding="utf-8")
        settings.voice_scenario_outputs = {"1": str(Path(settings.voicer_output_folder) / "old.mp3")}
        return settings

    @staticmethod
    def _production_folders(settings: Settings) -> list[Path]:
        return [Path(value) for value in (
            settings.output_folder, settings.voicer_output_folder, settings.cover_output_folder,
            settings.seo_output_folder, settings.media_output_folder, settings.cutter_output_folder,
            settings.footage_download_folder, settings.mixer_output_folder, settings.montage_output_folder,
            settings.montage_project_folder,
        )]

    def _seed_session(self) -> None:
        save_session(
            ["Старая тема"],
            [Job(ScenarioRequest(0, "Старая тема", "", "old-id"), RunState.DONE, "Сценарий")],
        )

    def test_reset_round_trip_erases_montage_and_release_metadata(self):
        with TemporaryDirectory() as directory, patch.dict(os.environ, {"LOCALAPPDATA": directory, "TEMP": str(Path(directory) / "io"), "TMP": str(Path(directory) / "io")}):
            root = Path(directory)
            settings = self._settings(root)
            save_settings(settings)
            self._seed_session()

            bridge.clear_production_queue(self.confirmation)

            restored = load_settings()
            state = bridge.snapshot()
            with self.subTest("montage rows"):
                self.assertEqual(state["montageTasks"], [])
            with self.subTest("publication plan versions"):
                self.assertEqual(restored.youtube_publication_plan_versions, [])
            with self.subTest("voice import audit"):
                self.assertEqual(state["voiceImport"], {})
            with self.subTest("last Results batch"):
                self.assertEqual(state["results"]["lastExportFolder"], "")
            with self.subTest("Results destination remains reusable configuration"):
                self.assertEqual(state["results"]["outputFolder"], settings.results_output_folder)
            self.assertEqual(restored.cover_rate_usage_events, [{"at": "2026-09-23T12:00:00+03:00", "count": 3}])

    def test_pre_reset_worker_cannot_resurrect_current_release(self):
        with TemporaryDirectory() as directory, patch.dict(os.environ, {"LOCALAPPDATA": directory, "TEMP": str(Path(directory) / "io"), "TMP": str(Path(directory) / "io")}):
            root = Path(directory)
            save_settings(self._settings(root))
            self._seed_session()
            stale_worker_settings = load_settings()

            bridge.clear_production_queue(self.confirmation)
            save_settings(stale_worker_settings)

            restored = load_settings()
            state = bridge.snapshot()
            self.assertEqual(load_session(), ([], []))
            self.assertEqual(restored.idea_production_items, [])
            self.assertEqual(restored.cover_queue, [])
            self.assertEqual(restored.seo_queue, [])
            self.assertEqual(restored.voice_scenario_outputs, {})
            self.assertEqual(restored.montage_task_statuses, {})
            self.assertEqual(restored.youtube_publication_items, {})
            self.assertEqual(restored.youtube_publication_plan_versions, [])
            self.assertEqual(state["montageTasks"], [])
            self.assertEqual(state["voiceImport"], {})
            self.assertEqual(state["results"]["lastExportFolder"], "")
            self.assertEqual(restored.youtube_oauth_tokens, {"channel": "preserved-token"})
            self.assertEqual(restored.youtube_publication_v2_rule_presets, [{"name": "preserved-rule"}])
            self.assertEqual(restored.cover_rate_usage_events, [{"at": "2026-09-23T12:00:00+03:00", "count": 3}])
            save_session(
                ["Старая тема"],
                [Job(ScenarioRequest(0, "Старая тема", "", "new-id"), RunState.DONE, "Новый сценарий")],
            )
            self.assertEqual(
                [job.request.production_item_id for job in load_session()[1]], ["new-id"],
            )

    def test_reset_removes_orphan_voice_maps_but_keeps_model_cache_and_source_files(self):
        with TemporaryDirectory() as directory, patch.dict(os.environ, {"LOCALAPPDATA": directory, "TEMP": str(Path(directory) / "io"), "TMP": str(Path(directory) / "io")}):
            root = Path(directory)
            settings = self._settings(root)
            source = root / "source-footage" / "keep.mp4"
            source.parent.mkdir(parents=True)
            source.write_bytes(b"source")
            settings.footage_folders = [str(source.parent)]
            save_settings(settings)
            self._seed_session()
            stale_worker_settings = load_settings()
            before = {
                "settingsSha256": sha256(config.config_path().read_bytes()).hexdigest(),
                "sessionSha256": sha256(session_path().read_bytes()).hexdigest(),
                "oldProductionItemIds": ["old-id"],
                "ownedRoots": {str(folder): [child.name for child in folder.iterdir()]
                               for folder in self._production_folders(settings)},
            }
            maps = config.app_data_root() / "voice-maps"
            maps.mkdir(parents=True)
            (maps / "orphan.voice-map.json").write_text('{"productionItemId":"orphan"}', encoding="utf-8")
            model = config.app_data_root() / "models" / "whisper" / "keep.bin"
            model.parent.mkdir(parents=True)
            model.write_bytes(b"model")

            bridge.clear_production_queue(self.confirmation)
            save_settings(stale_worker_settings)

            restored = load_settings()
            state = bridge.snapshot()
            self.assertEqual(list(maps.glob("*.voice-map.json")), [])
            self.assertTrue(model.is_file())
            self.assertTrue(source.is_file())
            self.assertEqual(restored.idea_production_items, [])
            self.assertEqual(restored.montage_task_statuses, {})
            self.assertEqual(restored.youtube_publication_plan_versions, [])
            self.assertEqual(state["results"]["lastExportFolder"], "")
            for folder in self._production_folders(restored):
                with self.subTest(folder=folder.name):
                    self.assertTrue(folder.is_dir(), f"reset removed configured root {folder}")
                    self.assertEqual(list(folder.iterdir()), [])
            evidence = os.environ.get("NEWSFLOW_RESET_EVIDENCE_DIR", "").strip()
            if evidence:
                evidence_root = Path(evidence)
                evidence_root.mkdir(parents=True, exist_ok=True)
                after = {
                    "settingsSha256": sha256(config.config_path().read_bytes()).hexdigest(),
                    "sessionSha256": sha256(session_path().read_bytes()).hexdigest(),
                    "activeOldProductionItemIds": [],
                    "staleWorkerResurrection": "blocked",
                    "montageTasks": state["montageTasks"],
                    "voiceImport": state["voiceImport"],
                    "results": state["results"],
                    "ownedRoots": {str(folder): [child.name for child in folder.iterdir()]
                                   for folder in self._production_folders(restored)},
                    "preserved": {"sourceFootage": source.is_file(), "modelCache": model.is_file()},
                }
                (evidence_root / "before.json").write_text(dumps(before, ensure_ascii=False, indent=2), encoding="utf-8")
                (evidence_root / "after.json").write_text(dumps(after, ensure_ascii=False, indent=2), encoding="utf-8")
                (evidence_root / "manifest.json").write_text(dumps({
                    "id": "RESET-001", "storage": "disposable LOCALAPPDATA", "realProviders": False,
                    "command": "clear-production-queue", "confirmation": "УДАЛИТЬ ПРОИЗВОДСТВО",
                }, ensure_ascii=False, indent=2), encoding="utf-8")
                (evidence_root / "review-summary.md").write_text(
                    "# RESET-001 isolated destructive acceptance\n\n"
                    "Old release state and owned artifacts were removed; stale worker resurrection was blocked. "
                    "Source footage and model-cache sentinels remain. No real storage or provider was used.\n",
                    encoding="utf-8",
                )

    def test_held_cover_worker_cannot_recreate_cover_file_or_sidecar_after_reset(self):
        with TemporaryDirectory() as directory, patch.dict(os.environ, {"LOCALAPPDATA": directory, "TEMP": str(Path(directory) / "io"), "TMP": str(Path(directory) / "io")}):
            root = Path(directory)
            settings = self._settings(root)
            save_settings(settings)
            self._seed_session()
            worker_settings = load_settings()
            late_cover = Path(worker_settings.cover_output_folder) / "late-worker.png"
            worker_started = threading.Event()
            continue_worker = threading.Event()
            worker_error: list[Exception] = []

            def complete_held_worker() -> None:
                worker_started.set()
                continue_worker.wait(timeout=5)
                try:
                    late_cover.parent.mkdir(parents=True, exist_ok=True)
                    late_cover.write_bytes(b"late")
                    worker_settings.cover_queue[0]["paths"] = [str(late_cover)]
                    worker_settings.cover_queue[0]["path"] = str(late_cover)
                    bridge._save_cover_state(worker_settings)
                except (OSError, RuntimeError, TypeError, ValueError) as error:  # pragma: no cover - assertion below reports it
                    worker_error.append(error)

            worker = threading.Thread(target=complete_held_worker)
            worker.start()
            self.assertTrue(worker_started.wait(timeout=5))
            bridge.clear_production_queue(self.confirmation)
            cover_root = Path(worker_settings.cover_output_folder)
            new_release_sentinel = cover_root / "new-release.txt"
            new_release_sentinel.write_bytes(b"new")
            self.assertTrue(bridge._discard_stale_production_artifacts(
                worker_settings, [cover_root], cover_root,
            ))
            continue_worker.set()
            worker.join(timeout=5)

            self.assertFalse(late_cover.exists())
            self.assertTrue(new_release_sentinel.is_file())
            library = config.app_data_root() / "covers-library.json"
            self.assertTrue(library.is_file())
            self.assertEqual(bridge.CoverLibrary(library)._read()["items"], {})
            self.assertEqual(worker_error, [])

    def test_held_montage_planner_cannot_recreate_project_after_reset(self):
        with TemporaryDirectory() as directory, patch.dict(os.environ, {"LOCALAPPDATA": directory, "TEMP": str(Path(directory) / "io"), "TMP": str(Path(directory) / "io")}):
            root = Path(directory)
            settings = self._settings(root)
            footage = root / "source-footage"
            footage.mkdir()
            (footage / "Iran oil tanker Hormuz shipping.mp4").write_bytes(b"source")
            voice = root / "voice-input.mp3"
            voice.write_bytes(b"voice")
            settings.footage_folders = [str(footage)]
            settings.montage_use_script_text = False
            settings.montage_auto_web = False
            settings.montage_export_davinci_xml = False
            settings.voice_scenario_outputs = {"1": str(voice)}
            save_settings(settings)
            save_session(
                ["Старая тема"],
                [Job(ScenarioRequest(0, "Старая тема", "", ""), RunState.DONE, "")],
            )
            project_write_started = threading.Event()
            continue_planner = threading.Event()
            planner_errors: list[Exception] = []
            original_save = bridge.TimelineProject.save

            def held_project_save(project, path):
                project_write_started.set()
                continue_planner.wait(timeout=5)
                return original_save(project, path)

            def plan() -> None:
                try:
                    bridge.prepare_montage({"scenarioIndex": 0})
                except RuntimeError as error:
                    planner_errors.append(error)

            with patch.object(bridge, "_montage_screen_text_safe", return_value=True), \
                    patch.object(bridge.ClipIndex, "count", return_value=0), \
                    patch.object(bridge, "probe_media_duration", return_value=6.0), \
                    patch.object(bridge, "probe_video_duration", return_value=8.0), \
                    patch.object(bridge.TimelineProject, "save", autospec=True, side_effect=held_project_save):
                worker = threading.Thread(target=plan)
                worker.start()
                self.assertTrue(project_write_started.wait(timeout=5))
                bridge.clear_production_queue(self.confirmation)
                continue_planner.set()
                worker.join(timeout=5)

            self.assertFalse(worker.is_alive())
            self.assertEqual(len(planner_errors), 1)
            for folder in (Path(settings.montage_project_folder), Path(settings.cutter_output_folder),
                           Path(settings.footage_download_folder)):
                self.assertTrue(folder.is_dir())
                self.assertEqual(list(folder.iterdir()), [])

    def test_held_planner_cannot_recreate_external_download_or_cut_after_reset(self):
        with TemporaryDirectory() as directory, patch.dict(os.environ, {"LOCALAPPDATA": directory, "TEMP": str(Path(directory) / "io"), "TMP": str(Path(directory) / "io")}):
            root = Path(directory)
            settings = self._settings(root)
            voice = root / "voice-input.mp3"
            voice.write_bytes(b"voice")
            settings.footage_folders = []
            settings.montage_use_script_text = False
            settings.montage_auto_web = True
            settings.montage_export_davinci_xml = False
            settings.voice_scenario_outputs = {"1": str(voice)}
            save_settings(settings)
            save_session(
                ["Старая тема"],
                [Job(ScenarioRequest(0, "Старая тема", "", ""), RunState.DONE, "")],
            )
            cut_started = threading.Event()
            continue_cut = threading.Event()
            planner_errors: list[Exception] = []

            def fake_download(_candidate, folder):
                folder.mkdir(parents=True, exist_ok=True)
                source = folder / "late-source.webm"
                source.write_bytes(b"source")
                return bridge.FootageItem(str(source), source.name, "wikimedia", "https://example.test/source")

            def held_cut(_source, output_root, **_kwargs):
                cut_started.set()
                continue_cut.wait(timeout=5)
                output_root.mkdir(parents=True, exist_ok=True)
                clip = output_root / "late-cut.mp4"
                clip.write_bytes(b"cut")
                return clip

            def plan() -> None:
                try:
                    bridge.prepare_montage({"scenarioIndex": 0})
                except RuntimeError as error:
                    planner_errors.append(error)

            candidate = {"title": "neutral news footage", "url": "https://example.test/source", "tags": []}
            with patch.object(bridge, "search_wikimedia_videos", return_value=[candidate]), \
                    patch.object(bridge, "_external_candidate_ok", return_value=True), \
                    patch.object(bridge, "_semantic_clip_ok", return_value=True), \
                    patch.object(bridge, "_montage_screen_text_safe", return_value=True), \
                    patch.object(bridge, "download_footage", side_effect=fake_download), \
                    patch.object(bridge, "cut_single_clip", side_effect=held_cut), \
                    patch.object(bridge.ClipIndex, "count", return_value=0), \
                    patch.object(bridge.ClipIndex, "add_item"), \
                    patch.object(bridge, "probe_media_duration", return_value=6.0), \
                    patch.object(bridge, "probe_video_duration", return_value=8.0):
                worker = threading.Thread(target=plan)
                worker.start()
                self.assertTrue(cut_started.wait(timeout=5))
                bridge.clear_production_queue(self.confirmation)
                continue_cut.set()
                worker.join(timeout=5)

            self.assertFalse(worker.is_alive())
            self.assertEqual(len(planner_errors), 1)
            with bridge._EXTERNAL_FOOTAGE_CACHE_LOCK:
                self.assertEqual(bridge._EXTERNAL_FOOTAGE_CACHE, {})
            for folder in (Path(settings.footage_download_folder), Path(settings.cutter_output_folder)):
                self.assertTrue(folder.is_dir())
                self.assertEqual(list(folder.iterdir()), [])


if __name__ == "__main__":
    unittest.main()

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
from tests.media_fixtures import write_readable_video


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

    def test_reset_releases_topic_memory_and_manual_readd_survives_restart(self):
        with TemporaryDirectory() as directory, patch.dict(os.environ, {"LOCALAPPDATA": directory}):
            root = Path(directory)
            settings = self._settings(root)
            settings.idea_title_memory = [{"title": "Старая тема", "topic": "Проверка памяти"}]
            settings.idea_title_metadata = {"Старая тема": {"topic": "Проверка памяти"}}
            save_settings(settings)
            save_session(["Старая тема", "Тема без готового сценария"], [
                Job(ScenarioRequest(0, "Старая тема", "", "old-id"), RunState.DONE, "Старый текст"),
            ])
            previous_ids = {"old-id"}
            expected = ["Старая тема", "Тема без готового сценария", "Новая тема"]

            for cycle in range(2):
                with self.subTest(cycle=cycle):
                    bridge.clear_production_queue(self.confirmation)
                    reset = load_settings()
                    self.assertEqual(reset.idea_title_memory, [])
                    self.assertEqual(reset.idea_title_metadata, {})
                    self.assertEqual(reset.idea_production_items, [])
                    self.assertEqual(load_session(), ([], []))

                    response = bridge.add_scenarios({"titles": "\n".join([*expected, "СТАРАЯ ТЕМА", "Новая тема"])})
                    self.assertEqual([row["title"] for row in response["scenarios"]], expected)
                    titles, jobs = load_session()
                    self.assertEqual(titles, expected)
                    fresh = next(job for job in jobs if job.request.title == "Старая тема")
                    self.assertTrue(fresh.request.production_item_id)
                    self.assertNotIn(fresh.request.production_item_id, previous_ids)
                    self.assertEqual(fresh.result, "")
                    previous_ids.add(fresh.request.production_item_id)
                    restarted = load_settings()
                    self.assertIn("old-id", restarted.deleted_scenario_production_ids)
                    self.assertIn("старая тема", restarted.deleted_scenario_titles)
                    self.assertEqual(restarted.youtube_oauth_tokens, {"channel": "preserved-token"})
                    self.assertEqual(bridge.snapshot()["scenarios"][0]["productionItemId"], fresh.request.production_item_id)
                    bridge.add_scenarios({"titles": "Старая тема\nНовая тема"})
                    self.assertEqual(load_session()[0], expected, "Current topics must still deduplicate")

    def test_reset_without_confirmation_does_not_erase_topic_memory(self):
        with TemporaryDirectory() as directory, patch.dict(os.environ, {"LOCALAPPDATA": directory}):
            settings = self._settings(Path(directory))
            settings.idea_title_memory = [{"title": "Старая тема"}]
            save_settings(settings)
            self._seed_session()
            with self.assertRaises(ValueError):
                bridge.clear_production_queue({"confirmed": True, "confirmationPhrase": "нет"})
            self.assertEqual(load_settings().idea_title_memory, [{"title": "Старая тема"}])
            self.assertEqual(load_session()[0], ["Старая тема"])

    def test_reset_fences_topic_ids_before_their_scenario_jobs_exist(self):
        with TemporaryDirectory() as directory, patch.dict(os.environ, {"LOCALAPPDATA": directory}):
            settings = self._settings(Path(directory))
            settings.idea_production_items = [{"id": "topic-only", "title": "Тема без сценария"}]
            settings.idea_scenario_context = {"Тема из контекста": {"id": "context-only", "title": "Тема из контекста"}}
            save_settings(settings)
            save_session(["Тема без сценария", "Тема из контекста"], [])
            bridge.clear_production_queue(self.confirmation)
            restored = load_settings()
            self.assertTrue({"topic-only", "context-only"}.issubset(restored.deleted_scenario_production_ids))
            self.assertTrue({"topic-only", "context-only"}.issubset(restored.idea_deleted_production_ids))
            stale_jobs = [Job(ScenarioRequest(0, "Тема без сценария", "", "topic-only"))]
            save_session(["Тема без сценария"], stale_jobs)
            self.assertEqual(load_session(), ([], []), "Retired IDs must still fence a late worker")

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
            cover_root = Path(worker_settings.cover_output_folder)
            late_cover = bridge._production_staging_folder(
                cover_root, worker_settings.production_reset_generation, "cover",
            ) / "late-worker.png"
            worker_started = threading.Event()
            continue_worker = threading.Event()
            worker_error: list[Exception] = []

            def complete_held_worker() -> None:
                worker_started.set()
                continue_worker.wait(timeout=5)
                try:
                    late_cover.parent.mkdir(parents=True, exist_ok=True)
                    late_cover.write_bytes(b"late")
                    published = bridge._publish_staged_artifacts(worker_settings, [late_cover], cover_root)
                    worker_settings.cover_queue[0]["paths"] = [str(path) for path in published]
                    worker_settings.cover_queue[0]["path"] = str(published[0]) if published else ""
                    bridge._save_cover_state(worker_settings)
                except (OSError, RuntimeError, TypeError, ValueError) as error:  # pragma: no cover - assertion below reports it
                    worker_error.append(error)

            worker = threading.Thread(target=complete_held_worker)
            worker.start()
            self.assertTrue(worker_started.wait(timeout=5))
            bridge.clear_production_queue(self.confirmation)
            new_release_sentinel = cover_root / "new-release.txt"
            new_release_sentinel.write_bytes(b"new")
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
            # Quarantine preflight must stay real: this reset race needs a
            # readable source to reach the held project-publication boundary.
            write_readable_video(footage / "Iran oil tanker Hormuz shipping.mp4")
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

    def test_staging_cleanup_through_alias_keeps_canonical_output_root(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            canonical = root / "canonical"
            canonical.mkdir()
            sentinel = canonical / "preserved.txt"
            sentinel.write_text("keep", encoding="utf-8")
            alias = root / "alias"
            if os.name == "nt":
                import _winapi
                _winapi.CreateJunction(str(canonical), str(alias))
            else:
                alias.symlink_to(canonical, target_is_directory=True)
            output = canonical / "production"
            staged = bridge._production_staging_folder(alias / "production", 0, "montage") / "old.json"
            staged.write_text("old", encoding="utf-8")

            bridge._remove_owned_staged_artifact(staged)

            self.assertFalse(staged.exists())
            self.assertTrue(output.is_dir(), "Resolved staging boundary must stop cleanup before the output root")
            self.assertEqual(list(output.iterdir()), [])
            self.assertEqual(sentinel.read_text(encoding="utf-8"), "keep")

    def test_stale_staging_cannot_replace_new_same_path_artifacts(self):
        with TemporaryDirectory() as directory, patch.dict(os.environ, {"LOCALAPPDATA": directory, "TEMP": str(Path(directory) / "io"), "TMP": str(Path(directory) / "io")}):
            root = Path(directory)
            settings = self._settings(root)
            save_settings(settings)
            self._seed_session()
            stale_settings = load_settings()
            bridge.clear_production_queue(self.confirmation)

            for kind, final_root, name in (
                ("voice", Path(stale_settings.voicer_output_folder), "001 — Старая тема.mp3"),
                ("montage", Path(stale_settings.montage_output_folder), "Старая тема.mp4"),
                ("project", Path(stale_settings.montage_project_folder), "Старая тема.newsflow"),
                ("external", Path(stale_settings.cutter_output_folder), "same-source.mp4"),
            ):
                final_root.mkdir(parents=True, exist_ok=True)
                current = final_root / name
                current.write_bytes(b"new-generation")
                staged = bridge._production_staging_folder(final_root, stale_settings.production_reset_generation, kind) / name
                staged.parent.mkdir(parents=True, exist_ok=True)
                staged.write_bytes(b"old-generation")

                self.assertEqual(bridge._publish_staged_artifacts(stale_settings, [staged], final_root), [])
                self.assertEqual(current.read_bytes(), b"new-generation")
                self.assertFalse(staged.exists())

    def test_reset_recreates_missing_and_nested_configured_roots(self):
        with TemporaryDirectory() as directory, patch.dict(os.environ, {"LOCALAPPDATA": directory, "TEMP": str(Path(directory) / "io"), "TMP": str(Path(directory) / "io")}):
            root = Path(directory)
            settings = self._settings(root)
            parent = root / "production" / "nested-parent"
            nested = parent / "nested-voice"
            missing = root / "production" / "missing-seo"
            settings.output_folder = str(parent)
            settings.voicer_output_folder = str(nested)
            settings.seo_output_folder = str(missing)
            for folder in (parent, nested):
                folder.mkdir(parents=True, exist_ok=True)
                (folder / "old.txt").write_text("old", encoding="utf-8")
            save_settings(settings)
            self._seed_session()

            bridge.clear_production_queue(self.confirmation)

            self.assertTrue(parent.is_dir())
            self.assertTrue(nested.is_dir())
            self.assertTrue(missing.is_dir())
            self.assertEqual(list(nested.iterdir()), [])
            self.assertEqual(list(missing.iterdir()), [])
            self.assertEqual(list(parent.iterdir()), [nested])

    def test_reset_refuses_cleanup_root_overlapping_reusable_data_before_state_change(self):
        cases = (
            "source-footage", "source-footage-descendant", "results-and-references",
            "results-descendant", "app-data-ancestor",
        )
        for case in cases:
            with self.subTest(case=case), TemporaryDirectory() as directory, patch.dict(
                os.environ,
                {"LOCALAPPDATA": directory, "TEMP": str(Path(directory) / "io"), "TMP": str(Path(directory) / "io")},
            ):
                root = Path(directory)
                settings = self._settings(root)
                protected = root / f"reusable-{case}"
                protected.mkdir(parents=True, exist_ok=True)
                protected_file = protected / "keep.txt"
                protected_file.write_text(case, encoding="utf-8")
                if case == "source-footage":
                    settings.output_folder = str(protected)
                    settings.footage_folders = [str(protected)]
                elif case == "source-footage-descendant":
                    cleanup_root = protected / "current-output"
                    cleanup_root.mkdir()
                    protected_file = cleanup_root / "keep.txt"
                    protected_file.write_text(case, encoding="utf-8")
                    settings.output_folder = str(cleanup_root)
                    settings.footage_folders = [str(protected)]
                elif case == "results-and-references":
                    settings.cover_output_folder = str(protected)
                    results = protected / "results"
                    face_library = protected / "faces"
                    reference = protected / "reference.png"
                    for path in (results, face_library):
                        path.mkdir()
                        (path / "keep.txt").write_text(case, encoding="utf-8")
                    reference.write_bytes(b"reference")
                    settings.results_output_folder = str(results)
                    settings.cover_face_library_folder = str(face_library)
                    settings.cover_reference_paths = [str(reference)]
                elif case == "results-descendant":
                    cleanup_root = protected / "current-output"
                    cleanup_root.mkdir()
                    protected_file = cleanup_root / "keep.txt"
                    protected_file.write_text(case, encoding="utf-8")
                    settings.montage_output_folder = str(cleanup_root)
                    settings.results_output_folder = str(protected)
                else:
                    app_data_parent = config.app_data_root().parent
                    settings.media_output_folder = str(app_data_parent)
                    protected = app_data_parent
                    protected_file = config.config_path()

                save_settings(settings)
                self._seed_session()
                before = load_settings()
                before_session = load_session()
                protected_content = protected_file.read_text(encoding="utf-8")

                with self.assertRaisesRegex(ValueError, "пересекается"):
                    bridge.clear_production_queue(self.confirmation)

                after = load_settings()
                self.assertEqual(after.production_reset_generation, before.production_reset_generation)
                self.assertEqual(load_session(), before_session)
                self.assertTrue(protected_file.is_file())
                self.assertEqual(protected_file.read_text(encoding="utf-8"), protected_content)

    def test_reset_allows_generated_cutter_root_listed_as_footage(self):
        with TemporaryDirectory() as directory, patch.dict(
            os.environ,
            {"LOCALAPPDATA": directory, "TEMP": str(Path(directory) / "io"), "TMP": str(Path(directory) / "io")},
        ):
            root = Path(directory)
            settings = self._settings(root)
            cutter_root = Path(settings.cutter_output_folder)
            settings.footage_folders = [str(cutter_root)]
            save_settings(settings)
            self._seed_session()

            bridge.clear_production_queue(self.confirmation)

            self.assertTrue(cutter_root.is_dir())
            self.assertEqual(list(cutter_root.iterdir()), [])


if __name__ == "__main__":
    unittest.main()

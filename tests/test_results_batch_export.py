import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from scriptor import bridge
from scriptor.config import Settings
from scriptor.core import ScenarioRequest
from scriptor.runner import Job, RunState


class ResultsBatchExportTests(unittest.TestCase):
    def test_exports_three_numbered_txt_files_with_readable_topic_bound_seo_and_tags(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            destination = root / "destination"
            destination.mkdir()
            first_video = root / "source-first.mp4"
            third_video = root / "source-third.mp4"
            stale_video = root / "stale-middle.mp4"
            selected_cover = root / "selected-cover.png"
            unselected_cover = root / "unselected-cover.png"
            first_video.write_bytes(b"first-video")
            third_video.write_bytes(b"third-video")
            stale_video.write_bytes(b"stale-video")
            selected_cover.write_bytes(b"selected-cover")
            unselected_cover.write_bytes(b"unselected-cover")
            source_bytes = {path: path.read_bytes() for path in (
                first_video, third_video, stale_video, selected_cover, unselected_cover,
            )}
            titles = ["Первая тема", "Средняя тема", "Третья тема"]
            jobs = [
                Job(ScenarioRequest(index, title, "", f"production-{index + 1}"), RunState.DONE, "Сценарий")
                for index, title in enumerate(titles)
            ]
            settings = Settings(
                results_output_folder=str(destination),
                montage_task_statuses={
                    "0": {"scenarioIndex": 0, "production_item_id": "production-1", "status": "Готово", "outputPath": str(first_video)},
                    "1": {"scenarioIndex": 1, "production_item_id": "", "status": "Готово", "outputPath": str(stale_video)},
                    "2": {"scenarioIndex": 2, "production_item_id": "production-3", "status": "Готово", "outputPath": str(third_video)},
                },
                cover_queue=[
                    {"production_item_id": "production-1", "selected_path": str(selected_cover), "paths": [str(selected_cover), str(unselected_cover)]},
                    {"production_item_id": "stale-neighbor", "title": "Средняя тема", "selected_path": str(unselected_cover)},
                    {"production_item_id": "production-3", "selected_path": str(root / "missing-cover.png")},
                ],
                seo_queue=[
                    {"production_item_id": "production-1", "status": "Готово", "tags_status": "Готово", "title": "SEO первая", "description": "Строка один\nСтрока два", "hashtags": ["#первая"], "tags": ["тег один", "тег два"]},
                    {"production_item_id": "production-2", "title": "", "description": "", "tags": []},
                    {"production_item_id": "production-3", "status": "Ожидает", "tags_status": "Готово", "title": "Устаревший SEO", "description": "Устаревшее описание", "tags": ["тег три"]},
                ],
            )
            exporter = getattr(bridge, "export_results_batch", None)
            self.assertTrue(callable(exporter), "RESULTS-001 exporter is not registered")
            with patch.object(bridge, "load_settings", return_value=settings), \
                 patch.object(bridge, "load_session", return_value=(titles, jobs)), \
                 patch.object(bridge, "save_settings"), \
                 patch.object(bridge, "_is_valid_montage_output", side_effect=lambda path: path in {first_video, third_video}), \
                patch.object(bridge, "snapshot", return_value={"results": {}}):
                result = exporter({})
                exporter({})

            exported = Path(settings.results_last_export_folder)
            self.assertTrue(exported.is_dir())
            self.assertEqual((exported / "MP4").is_dir(), True)
            self.assertEqual((exported / "Обложки").is_dir(), True)
            self.assertEqual(
                (exported / "01-заголовки.txt").read_text(encoding="utf-8"),
                "001. Первая тема\n002. Средняя тема\n003. Третья тема\n",
            )
            self.assertEqual(
                (exported / "02-SEO-и-хештеги.txt").read_text(encoding="utf-8"),
                "001. Строка один\nСтрока два\n#первая\n\n"
                "002. \n\n"
                "003. \n",
            )
            self.assertEqual(
                (exported / "03-теги.txt").read_text(encoding="utf-8"),
                "001. тег один, тег два\n"
                "002. \n"
                "003. тег три\n",
            )
            self.assertEqual(sorted(path.name for path in (exported / "MP4").iterdir()), [
                "001 — Первая тема.mp4", "003 — Третья тема.mp4",
            ])
            self.assertEqual(sorted(path.name for path in (exported / "Обложки").iterdir()), [
                "001 — Первая тема.png",
            ])
            self.assertEqual(result["operationResult"]["missingMp4Ordinals"], [2])
            self.assertEqual(result["operationResult"]["missingCoverOrdinals"], [2, 3])
            self.assertEqual(result["operationResult"]["missingSeoDescriptionOrdinals"], [2, 3])
            self.assertEqual(result["operationResult"]["missingTagsOrdinals"], [2])
            self.assertEqual({path: path.read_bytes() for path in source_bytes}, source_bytes)
            first_export = next(path for path in destination.iterdir() if path != exported)
            self.assertNotEqual(first_export, exported)
            self.assertTrue((first_export / "01-заголовки.txt").is_file())
            self.assertTrue((exported / "01-заголовки.txt").is_file())

    def test_changing_results_destination_clears_stale_last_export_folder(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            old_destination = root / "old"
            new_destination = root / "new"
            old_destination.mkdir()
            new_destination.mkdir()
            settings = Settings(
                results_output_folder=str(old_destination),
                results_last_export_folder=str(old_destination / "NewsFlow Results — old"),
            )
            with patch.object(bridge, "load_settings", return_value=settings), \
                 patch.object(bridge, "save_settings"), \
                 patch.object(bridge, "snapshot", return_value={
                     "results": {
                         "outputFolder": str(new_destination),
                         "lastExportFolder": "",
                     },
                 }):
                result = bridge.save_settings_patch({"resultsOutputFolder": str(new_destination)})

            self.assertEqual(settings.results_output_folder, str(new_destination))
            self.assertEqual(settings.results_last_export_folder, "")
            self.assertEqual(result["results"]["lastExportFolder"], "")

    def test_reports_a_partial_mp4_as_missing_instead_of_exporting_it(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            destination = root / "destination"
            destination.mkdir()
            partial_video = root / "partial.mp4"
            partial_video.write_bytes(b"not-a-valid-mp4")
            title = "Тема с неполным MP4"
            settings = Settings(
                results_output_folder=str(destination),
                montage_task_statuses={
                    "0": {"scenarioIndex": 0, "production_item_id": "production-1", "status": "Готово", "outputPath": str(partial_video)},
                },
            )
            job = Job(ScenarioRequest(0, title, "", "production-1"), RunState.DONE, "Сценарий")
            with patch.object(bridge, "load_settings", return_value=settings), \
                 patch.object(bridge, "load_session", return_value=([title], [job])), \
                 patch.object(bridge, "save_settings"), \
                 patch.object(bridge, "_is_valid_montage_output", return_value=False), \
                 patch.object(bridge, "snapshot", return_value={"results": {}}):
                result = bridge.export_results_batch({})

            exported = Path(settings.results_last_export_folder)
            self.assertEqual(list((exported / "MP4").iterdir()), [])
            self.assertEqual(result["operationResult"]["missingMp4Ordinals"], [1])
            self.assertEqual(partial_video.read_bytes(), b"not-a-valid-mp4")

    def test_does_not_backfill_matching_legacy_row_without_a_valid_completed_render(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            destination = root / "destination"
            destination.mkdir()
            invalid_video = root / "invalid.mp4"
            invalid_video.write_bytes(b"invalid")
            title = "Совпадающая тема без готового ролика"
            settings = Settings(
                results_output_folder=str(destination),
                montage_task_statuses={
                    "0": {
                        "scenarioIndex": 0,
                        "title": title,
                        "status": "В очереди",
                        "outputPath": str(invalid_video),
                    },
                },
            )
            job = Job(ScenarioRequest(0, title, "", "current-production-id"), RunState.DONE, "Сценарий")
            with patch.object(bridge, "load_settings", return_value=settings), \
                 patch.object(bridge, "load_session", return_value=([title], [job])), \
                 patch.object(bridge, "save_settings"), \
                 patch.object(bridge, "_is_valid_montage_output", return_value=False), \
                 patch.object(bridge, "snapshot", return_value={"results": {}}):
                result = bridge.export_results_batch({})

            self.assertEqual(settings.montage_task_statuses["0"].get("production_item_id", ""), "")
            self.assertEqual(result["operationResult"]["missingMp4Ordinals"], [1])

    def test_backfills_a_legacy_ready_mp4_only_when_current_title_and_index_match(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            destination = root / "destination"
            destination.mkdir()
            ready_video = root / "ready.mp4"
            ready_video.write_bytes(b"valid-current-video")
            title = "Тема с готовым старым MP4"
            settings = Settings(
                results_output_folder=str(destination),
                montage_task_statuses={
                    "0": {
                        "scenarioIndex": 0,
                        "title": title,
                        "status": "Готово",
                        "outputPath": str(ready_video),
                    },
                },
            )
            job = Job(ScenarioRequest(0, title, "", "current-production-id"), RunState.DONE, "Сценарий")
            with patch.object(bridge, "load_settings", return_value=settings), \
                 patch.object(bridge, "load_session", return_value=([title], [job])), \
                 patch.object(bridge, "save_settings"), \
                 patch.object(bridge, "_is_valid_montage_output", return_value=True), \
                 patch.object(bridge, "snapshot", return_value={"results": {}}):
                result = bridge.export_results_batch({})

            exported = Path(settings.results_last_export_folder)
            self.assertEqual(
                sorted(path.name for path in (exported / "MP4").iterdir()),
                ["001 — Тема с готовым старым MP4.mp4"],
            )
            self.assertEqual(
                settings.montage_task_statuses["0"]["production_item_id"],
                "current-production-id",
            )
            self.assertEqual(result["operationResult"]["missingMp4Ordinals"], [])

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

from scriptor import bridge, config
from scriptor.config import Settings
from scriptor.runner import RunState
from scriptor.youtube_api import build_private_video_insert_body, normalize_youtube_tags


class SeoTagsContractTests(TestCase):
    def test_operator_can_clear_saved_seo_call_to_action(self):
        settings = Settings(seo_call_to_action="Старое пожелание")
        with patch.object(bridge, "load_settings", return_value=settings), \
             patch.object(bridge, "save_settings"), \
             patch.object(bridge, "snapshot", return_value={}):
            bridge.save_seo_settings({"callToAction": ""})
        self.assertEqual(settings.seo_call_to_action, "")

    def test_tag_limit_is_capped_to_youtube_five_hundred_characters(self):
        settings = Settings(tag_char_limit=500)
        with patch.object(bridge, "load_settings", return_value=settings), \
             patch.object(bridge, "save_settings"), \
             patch.object(bridge, "snapshot", return_value={}):
            bridge.save_tag_limits({"hashtagBatchSize": 5, "tagCharLimit": 5000})
        self.assertEqual(settings.tag_char_limit, 500)

    def test_persisted_legacy_tag_limit_is_migrated_to_youtube_limit(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            path.write_text('{"tag_char_limit":5000}', encoding="utf-8")
            with patch.object(config, "config_path", return_value=path):
                restored = config.load_settings()
        self.assertEqual(restored.tag_char_limit, 500)

    def test_seo_and_tags_become_stale_when_scenario_changes(self):
        settings = Settings(seo_queue=[{
            "production_item_id": "production-1",
            "source_title": "Старое название",
            "script": "Старый сценарий",
            "requirements": "",
            "status": "Готово",
            "title": "Готовый SEO заголовок",
            "description": "Готовое описание",
            "hashtags": ["#старое"],
            "tags": ["старый тег"],
            "tags_status": "Готово",
            "tags_error": "",
            "error": "",
        }])
        job = SimpleNamespace(
            request=SimpleNamespace(production_item_id="production-1", prompt=""),
            result="Новый сценарий",
        )
        changed = bridge._sync_scenario_to_seo(
            settings,
            "Новое название",
            job,
            create_if_missing=False,
            legacy_titles=("Старое название",),
        )
        self.assertTrue(changed)
        row = settings.seo_queue[0]
        self.assertEqual(row["production_item_id"], "production-1")
        self.assertEqual(row["source_title"], "Новое название")
        self.assertEqual(row["script"], "Новый сценарий")
        self.assertEqual(row["status"], "Ожидает")
        self.assertEqual(row["tags_status"], "Ожидают")
        self.assertEqual(row["title"], "")
        self.assertEqual(row["description"], "")
        self.assertEqual(row["hashtags"], [])
        self.assertEqual(row["tags"], [])

    def test_seo_format_instruction_uses_exact_configured_hashtag_count(self):
        instruction = bridge._seo_format_instruction(9)
        self.assertIn("ровно 9", instruction)
        self.assertNotIn("3–5", instruction)

    def test_seo_json_deduplicates_hashtags_case_insensitively(self):
        parsed = bridge._parse_seo_json(
            '{"title":"Тема","description":"Описание","hashtags":["#Ормуз","орМУЗ","#танкеры"]}'
        )
        self.assertEqual(parsed["hashtags"], ["#Ормуз", "#танкеры"])

    def test_current_seo_scope_excludes_historical_rows(self):
        current_job = bridge.Job(
            bridge.ScenarioRequest(0, "Текущая тема", "", "production-current"),
            RunState.DONE,
            "Текущий сценарий",
            "",
        )
        settings = Settings(seo_queue=[
            {
                "production_item_id": "production-old",
                "source_title": "Старая тема",
                "status": "Ожидает",
            },
            {
                "production_item_id": "production-current",
                "source_title": "Текущая тема",
                "status": "Ожидает",
            },
            {
                "source_title": "Legacy не текущая",
                "status": "Ожидает",
            },
        ])

        self.assertEqual(
            bridge._current_seo_queue_indices(settings, ["Текущая тема"], [current_job]),
            [1],
        )

    def test_removing_scenario_prunes_only_its_seo_row(self):
        first = bridge.Job(
            bridge.ScenarioRequest(0, "Первая тема", "", "production-one"),
            RunState.DONE,
            "Первый сценарий",
            "",
        )
        second = bridge.Job(
            bridge.ScenarioRequest(1, "Вторая тема", "", "production-two"),
            RunState.DONE,
            "Второй сценарий",
            "",
        )
        settings = Settings(seo_queue=[
            {
                "production_item_id": "production-one",
                "source_title": "Первая тема",
                "status": "Готово",
            },
            {
                "production_item_id": "production-two",
                "source_title": "Вторая тема",
                "status": "Готово",
            },
        ])
        with patch.object(bridge, "load_session", return_value=(
                ["Первая тема", "Вторая тема"], [first, second],
             )), \
             patch.object(bridge, "load_settings", return_value=settings), \
             patch.object(bridge, "save_settings"), \
             patch.object(bridge, "save_session"), \
             patch.object(bridge, "remove_voice_map"), \
             patch.object(bridge, "snapshot", return_value={}):
            bridge.remove_scenarios_command({"indices": [0]})

        self.assertEqual(
            [row["production_item_id"] for row in settings.seo_queue],
            ["production-two"],
        )

    def test_auto_pipeline_generates_tags_after_seo_stage(self):
        job = SimpleNamespace(
            request=SimpleNamespace(index=0),
            state=RunState.DONE,
            result="Готовый сценарий",
        )
        settings = Settings(
            seo_queue=[{
                "source_title": "Тема",
                "status": "Готово",
                "description": "Готовое SEO описание",
                "tags": [],
                "tags_status": "Ожидают",
            }],
            auto_pipeline_stages={
                "scenarios": False,
                "covers": False,
                "seo": True,
                "voice": False,
                "montage": False,
                "package": False,
            },
        )
        with patch.object(bridge, "load_settings", return_value=settings), \
             patch.object(bridge, "save_settings"), \
             patch.object(bridge, "load_session", return_value=(["Тема"], [job])), \
             patch.object(bridge, "transfer_scenarios"), \
             patch.object(bridge, "generate_seo") as generate_seo_mock, \
             patch.object(bridge, "generate_tags", return_value={}) as generate_tags_mock, \
             patch.object(bridge, "snapshot", return_value={}):
            bridge.run_auto_pipeline({"enabled": True, "stages": settings.auto_pipeline_stages})
        generate_seo_mock.assert_not_called()
        generate_tags_mock.assert_called_once_with({"indices": [0], "chatUrl": ""})

    def test_tag_budget_counts_youtube_quotes_around_multiword_tags(self):
        self.assertEqual(normalize_youtube_tags(["foo bar", "x"], limit=10), ["foo bar"])
        self.assertEqual(bridge._limit_tags(["foo bar", "x"], 10), ["foo bar"])

    def test_upload_metadata_enforces_youtube_description_contract(self):
        with self.assertRaisesRegex(ValueError, "5000 байт"):
            build_private_video_insert_body(
                title="Тема",
                description="я" * 2501,
                tags=[],
            )
        with self.assertRaisesRegex(ValueError, "Заголовок"):
            build_private_video_insert_body(
                title="Тема <черновик>",
                description="Описание",
                tags=[],
            )
        with self.assertRaisesRegex(ValueError, "Описание"):
            build_private_video_insert_body(
                title="Тема",
                description="Описание <черновик>",
                tags=[],
            )

    def test_result_package_resolves_sanitized_filename_through_durable_identity(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            original_title = "Ормуз: что происходит? Риски / торговля"
            production_id = "production-seo-1"
            video = root / f"{bridge.safe_filename(original_title)}.mp4"
            video.write_bytes(b"mp4")
            cover = root / "cover.png"
            cover.write_bytes(b"png")
            settings = Settings(
                montage_output_folder=str(root),
                montage_project_folder=str(root),
                pipeline_montage_outputs=[str(video)],
                montage_task_statuses={
                    "0": {
                        "scenarioIndex": 0,
                        "title": original_title,
                        "status": "Готово",
                        "outputPath": str(video),
                    },
                },
            )
            settings.cover_queue = [{
                "production_item_id": production_id,
                "title": original_title,
                "path": str(cover),
            }]
            settings.seo_queue = [{
                "production_item_id": production_id,
                "source_title": original_title,
                "status": "Готово",
                "title": "SEO вариант",
                "description": "Описание из SEO",
                "hashtags": ["#Ормуз"],
                "tags": ["Ормуз", "торговля"],
            }]
            job = SimpleNamespace(
                request=SimpleNamespace(
                    index=0,
                    title=original_title,
                    production_item_id=production_id,
                ),
                state=RunState.DONE,
                result="Текст сценария",
            )
            with patch.object(bridge, "load_settings", return_value=settings), \
                 patch.object(bridge, "load_session", return_value=([original_title], [job])), \
                 patch.object(bridge, "save_settings"), \
                 patch.object(bridge, "snapshot", return_value={}):
                bridge.package_outputs({})
            package = Path(settings.video_result_packages[str(video)])
            self.assertEqual(
                (package / "Название сценария.txt").read_text(encoding="utf-8-sig").strip(),
                original_title,
            )
            self.assertEqual(
                (package / "Описание.txt").read_text(encoding="utf-8-sig").strip(),
                "Описание из SEO",
            )
            self.assertEqual(
                (package / "Теги.txt").read_text(encoding="utf-8-sig").strip(),
                "Ормуз, торговля",
            )
            self.assertTrue((package / "Обложка.png").is_file())


if __name__ == "__main__":
    import unittest

    unittest.main()

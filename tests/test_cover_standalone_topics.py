"""Independent manual cover topics use durable IDs without scenario prerequisites."""
import base64
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from scriptor import bridge, config, session
from tests import test_production_reset as fixtures


class StandaloneCoverTopicsTests(unittest.TestCase):
    def test_library_history_and_queue_tombstones_never_authorize_standalone_work(self):
        with TemporaryDirectory() as directory, patch.dict(os.environ, {"LOCALAPPDATA": directory}):
            config.save_settings(config.Settings())
            session.save_session([], [])
            row = {"production_item_id": "history", "title": "Старая обложка", "origin": "covers", "manual": True}
            bridge.CoverLibrary(bridge._cover_library_path()).persist([row], {}, {})
            self.assertEqual(bridge.snapshot()["covers"], [])
            settings = config.Settings(cover_queue=[row], cover_queue_tombstones=["production:history"])
            self.assertEqual(bridge._standalone_cover_production_ids(settings), set())
            settings.cover_queue_tombstones = []
            settings.cover_queue[0] = {**row, "production_item_id": "legacy-cover:history"}
            self.assertEqual(bridge._standalone_cover_production_ids(settings), set())

    def test_idea_deletion_and_stale_idea_worker_do_not_remove_independent_cover_ownership(self):
        for operation in ("delete-idea", "stale-save"):
            with self.subTest(operation=operation), TemporaryDirectory() as directory, \
                    patch.dict(os.environ, {"LOCALAPPDATA": directory}):
                settings = config.Settings(idea_results=["Удалить", "Оставить"])
                config.save_settings(settings)
                session.save_session([], [])
                bridge.add_scenarios({"titles": "Другая новость"})
                stale = config.load_settings()
                identity = bridge.import_cover_prompt_pairs({
                    "text": "Сад: новая теплица\nA greenhouse closeup", "createMissingTopics": True,
                })["operationResult"]["productionItemIds"][0]
                if operation == "delete-idea":
                    bridge.delete_idea_results({"ideas": ["Удалить"]})
                else:
                    config.save_settings(stale)
                self.assertIn(identity, {row["production_item_id"] for row in bridge.snapshot()["covers"]})

    def test_standalone_topic_coexists_with_scenarios_and_keeps_generated_image_by_id(self):
        with TemporaryDirectory() as directory, patch.dict(os.environ, {
            "LOCALAPPDATA": directory, "TEMP": str(Path(directory) / "io"), "TMP": str(Path(directory) / "io"),
        }), \
                patch("urllib.request.urlopen", side_effect=AssertionError("network forbidden")), \
                patch.object(bridge, "HybridTextPool", side_effect=AssertionError("paid text forbidden")):
            root = Path(directory)
            settings = config.Settings(
                cover_output_folder=str(root / "covers"), cover_variant_count=1,
                cover_build_mode="fastgen-full", cover_auto_overlay_text=False,
                cover_api_keys=[config.FastGenKey(label="offline", secret="offline")],
                fastgen_capabilities_cache={"image": [{"id": "nano_banana_2_image_generate", "inputs": {"min": 0, "max": 10}}]},
                cover_operation="nano_banana_2_image_generate",
            )
            config.save_settings(settings)
            session.save_session([], [])
            identity = bridge.import_cover_prompt_pairs({
                "text": "Сад: новая теплица\nA greenhouse closeup", "createMissingTopics": True,
            })["operationResult"]["productionItemIds"][0]
            bridge.add_scenarios({"titles": "Совсем другая новость"})
            saved = config.load_settings()
            bridge._hydrate_cover_library(saved)
            index = next(i for i, row in enumerate(saved.cover_queue) if row["production_item_id"] == identity)

            def offline_image(_prompt, output, _stem, *_args, **_kwargs):
                target = Path(output) / "offline.png"
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aP1sAAAAASUVORK5CYII="))
                return [target]

            with patch.object(bridge.FastGenPool, "generate_media", side_effect=offline_image) as provider:
                bridge.generate_covers({"indices": [index], "productionItemIds": [identity], "buildMode": "fastgen-full"})
            self.assertEqual(provider.call_count, 1)
            restarted = config.load_settings()
            bridge._hydrate_cover_library(restarted)
            row = next(row for row in restarted.cover_queue if row["production_item_id"] == identity)
            self.assertEqual(row["status"], "Готово")
            self.assertEqual(row["image_prompt"], "A greenhouse closeup")
            self.assertTrue(Path(row["path"]).is_file())
            self.assertTrue(Path(row["path"]).resolve().is_relative_to(root.resolve()))
            self.assertEqual(session.load_session()[0], ["Совсем другая новость"])

    def test_empty_production_accepts_pairs_and_survives_restart_without_scenarios(self):
        with TemporaryDirectory() as directory, patch.dict(os.environ, {"LOCALAPPDATA": directory}):
            config.save_settings(config.Settings())
            session.save_session([], [])
            result = bridge.import_cover_prompt_pairs({
                "text": "Сад: новая теплица\nA green glass greenhouse — exact ✨\nКулинария: хлеб\nFresh bread closeup",
                "createMissingTopics": True,
            })
            identities = result["operationResult"]["productionItemIds"]
            self.assertEqual(len(set(identities)), 2)
            saved = config.load_settings()
            self.assertEqual({row["id"] for row in saved.idea_production_items}, set(identities))
            self.assertEqual([row["title"] for row in saved.cover_queue], ["Сад: новая теплица", "Кулинария: хлеб"])
            self.assertEqual(saved.cover_queue[0]["image_prompt"], "A green glass greenhouse — exact ✨")
            bridge._hydrate_cover_library(saved)
            self.assertEqual({row["production_item_id"] for row in saved.cover_queue}, set(identities))
            selected = bridge._current_cover_generation_scope(saved, {
                "indices": [1], "productionItemIds": [identities[1]],
            }, "empty")
            self.assertEqual(selected[0][1]["image_prompt"], "Fresh bread closeup")
            self.assertEqual(session.load_session(), ([], []))
            self.assertEqual(bridge.snapshot()["scenarios"], [])
            self.assertEqual(len(bridge.snapshot()["covers"]), 2)

    def test_create_mode_keeps_existing_id_and_rejects_ambiguous_batch_atomically(self):
        settings = config.Settings(cover_queue=[
            {"production_item_id": "one", "title": "Тема", "image_prompt": "old"},
        ])
        with patch.object(bridge, "load_settings", return_value=settings), \
                patch.object(bridge, "_hydrate_cover_library"), \
                patch.object(bridge, "_save_cover_state") as save, \
                patch.object(bridge, "snapshot", return_value={}):
            result = bridge.import_cover_prompt_pairs({"text": "Новая тема\nNew prompt\nТема\nUpdated", "createMissingTopics": True})
            self.assertEqual(result["operationResult"]["productionItemIds"][1], "one")
            self.assertEqual(settings.cover_queue[0]["image_prompt"], "Updated")
            save.assert_called_once()
            before = [dict(row) for row in settings.cover_queue]
            settings.cover_queue.append({"production_item_id": "two", "title": "Тема"})
            save.reset_mock()
            with self.assertRaisesRegex(ValueError, "AMBIGUOUS_TOPIC"):
                bridge.import_cover_prompt_pairs({"text": "Ещё новая\nNew\nТема\nAmbiguous", "createMissingTopics": True})
            save.assert_not_called()
            self.assertEqual(settings.cover_queue[:-1], before)

    def test_reset_then_same_cover_topic_creates_fresh_id_and_does_not_revive_old_result(self):
        with TemporaryDirectory() as directory, patch.dict(os.environ, {"LOCALAPPDATA": directory}):
            settings = fixtures.ProductionResetTests()._settings(Path(directory))
            settings.idea_production_items = []
            settings.idea_results = []
            settings.cover_queue = []
            config.save_settings(settings)
            session.save_session([], [])
            payload = {"text": "Сад: новая теплица\nExact prompt", "createMissingTopics": True}
            old_id = bridge.import_cover_prompt_pairs(payload)["operationResult"]["productionItemIds"][0]
            stale = config.load_settings()
            bridge.clear_production_queue(fixtures.ProductionResetTests.confirmation)
            config.save_settings(stale)
            self.assertEqual(bridge.snapshot()["covers"], [])
            new_id = bridge.import_cover_prompt_pairs(payload)["operationResult"]["productionItemIds"][0]
            self.assertNotEqual(old_id, new_id)
            saved = config.load_settings()
            self.assertIn(old_id, saved.deleted_scenario_production_ids)
            self.assertNotIn(new_id, saved.deleted_scenario_production_ids)
            self.assertEqual([row["production_item_id"] for row in saved.cover_queue], [new_id])

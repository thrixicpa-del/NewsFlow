"""Durable identity, explicit activation and saved-policy boundaries for issue417."""

import unittest
from pathlib import Path
from unittest.mock import patch

from scriptor import bridge, config
from scriptor.timeline import TimelineProject
from tests import test_stock_pipeline as fixture


class FootageBlockPipelineTests(unittest.TestCase):
    setUp = fixture.StockPipelineTests.setUp
    prepare = fixture.StockPipelineTests.prepare

    def handler(self, name):
        value = getattr(bridge, name, None)
        self.assertTrue(
            callable(value), f"Missing canonical footage block handler: {name}"
        )
        return value

    def seed(self):
        root = self.root / "curated"
        root.mkdir(exist_ok=True)
        (root / "selected.mp4").write_bytes(b"isolated fixture")
        settings = config.Settings(montage_renderer="ffmpeg")
        settings.idea_production_items = [
            {"id": "p-a", "title": "Тема А", "manual": True}
        ]
        settings.footage_blocks = [
            {"id": "b-a", "name": "Алиев протесты", "root": str(root), "videoCount": 1}
        ]
        config.save_settings(settings)
        return root

    def test_txt_preview_and_commit_retain_existing_and_new_native_product_ids(self):
        preview = self.handler("preview_footage_block_import")
        apply = self.handler("import_footage_block_pairs")
        self.seed()
        text = "Тема А\n\nАлиев протесты\n\nНовая тема\n\nАлиев протесты"
        result = preview({"text": text})
        rows = result["footageBlockImportPreview"]
        self.assertEqual(rows[0]["productionItemId"], "p-a")
        self.assertTrue(rows[1]["productionItemId"])
        self.assertNotEqual(rows[1]["productionItemId"], "p-a")
        self.assertEqual(
            len(config.load_settings().idea_production_items),
            1,
            "Preview must not create live topics",
        )
        result = apply(
            {"text": text, "previewToken": result["footageBlockImportToken"]}
        )
        saved = config.load_settings()
        self.assertEqual(len(saved.idea_production_items), 2)
        self.assertEqual(
            set(saved.footage_block_assignments),
            {row["productionItemId"] for row in rows},
        )
        self.assertFalse(
            saved.montage_use_footage_blocks, "Import must not activate render mode"
        )
        apply({"text": text})
        self.assertEqual(len(config.load_settings().idea_production_items), 2)

    def test_invalid_second_pair_does_not_create_first_topic_or_assignment(self):
        apply = self.handler("import_footage_block_pairs")
        self.seed()
        before = (config.app_data_root() / "settings.json").read_bytes()
        with self.assertRaises(ValueError):
            apply(
                {
                    "text": "Новая тема\n\nАлиев протесты\n\nДругая тема\n\nНеизвестный блок"
                }
            )
        self.assertEqual(
            (config.app_data_root() / "settings.json").read_bytes(), before
        )

    def test_manual_assignment_does_not_change_other_topic_and_survives_stale_preview(
        self,
    ):
        assign = self.handler("assign_footage_block")
        preview = self.handler("preview_footage_block_import")
        apply = self.handler("import_footage_block_pairs")
        root = self.seed()
        settings = config.load_settings()
        settings.footage_blocks.append(
            {"id": "b-b", "name": "Другой блок", "root": str(root), "videoCount": 1}
        )
        settings.idea_production_items.append(
            {"id": "p-b", "title": "Тема Б", "manual": True}
        )
        settings.footage_block_assignments = {
            "p-a": {"blockId": "b-a", "origin": "import"},
            "p-b": {"blockId": "b-a", "origin": "import"},
        }
        config.save_settings(settings)
        text = "Тема А\n\nАлиев протесты"
        old = preview({"text": text})
        assign({"productionItemId": "p-a", "blockId": "b-b"})
        saved = config.load_settings()
        self.assertEqual(saved.footage_block_assignments["p-a"]["blockId"], "b-b")
        self.assertEqual(saved.footage_block_assignments["p-b"]["blockId"], "b-a")
        with self.assertRaises(ValueError):
            apply({"text": text, "previewToken": old["footageBlockImportToken"]})
        with self.assertRaises(ValueError):
            apply({"text": text})
        apply({"text": text, "confirmOverwrite": True})
        self.assertEqual(
            config.load_settings().footage_block_assignments["p-a"]["blockId"], "b-a"
        )

    def test_legacy_idless_topic_import_migrates_one_row_without_duplicate(self):
        preview = self.handler("preview_footage_block_import")
        apply = self.handler("import_footage_block_pairs")
        self.seed()
        settings = config.load_settings()
        settings.idea_production_items = [{"title": "Тема А", "manual": True}]
        config.save_settings(settings)
        text = "Тема А\n\nАлиев протесты"
        state = preview({"text": text})
        identity = state["footageBlockImportPreview"][0]["productionItemId"]
        apply({"text": text, "previewToken": state["footageBlockImportToken"]})
        saved = config.load_settings()
        self.assertEqual(
            len(saved.idea_production_items),
            1,
            "Migrating an existing topic must not append its copy",
        )
        self.assertEqual(saved.idea_production_items[0]["id"], identity)

    def test_legacy_preview_rejects_reordered_idless_rows(self):
        preview = self.handler("preview_footage_block_import")
        apply = self.handler("import_footage_block_pairs")
        self.seed()
        settings = config.load_settings()
        settings.idea_production_items = [
            {"title": "Тема А", "manual": True},
            {"title": "Другая тема", "manual": True},
        ]
        config.save_settings(settings)
        text = "Тема А\n\nАлиев протесты"
        state = preview({"text": text})
        settings = config.load_settings()
        settings.idea_production_items.reverse()
        config.save_settings(settings)
        before = (config.app_data_root() / "settings.json").read_bytes()
        with self.assertRaisesRegex(ValueError, "предпросмотр"):
            apply({"text": text, "previewToken": state["footageBlockImportToken"]})
        self.assertEqual(
            (config.app_data_root() / "settings.json").read_bytes(), before
        )

    def test_reset_preflight_protects_curated_roots_even_inside_generated_output(self):
        self.seed()
        settings = config.load_settings()
        root = self.root / "generated"
        root.mkdir()
        settings.footage_blocks = [
            {"id": "b", "name": "Keep originals", "root": str(root)}
        ]
        settings.footage_folders = [str(root)]
        settings.footage_download_folder = str(root)
        with self.assertRaisesRegex(ValueError, "пересекается"):
            bridge._reset_cleanup_preflight(settings, {str(root)})

    def test_block_assignment_serializes_with_production_reset_fence(self):
        import subprocess
        import sys
        import time

        self.handler("assign_footage_block")
        self.seed()
        ready = self.root / "child-ready"
        loaded = self.root / "child-loaded"
        code = (
            "from pathlib import Path\nfrom scriptor import footage_block_bridge as controller\n"
            f"ready=Path({str(ready)!r});loaded=Path({str(loaded)!r})\n"
            "original=controller.load_settings\n"
            "def observed():\n loaded.write_text('loaded');return original()\n"
            "controller.load_settings=observed\nready.write_text('ready')\n"
            "controller.assign_footage_block({'productionItemId':'p-a','blockId':'b-a'})\n"
        )
        with bridge._production_artifact_fence():
            child = subprocess.Popen(
                [sys.executable, "-B", "-c", code],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            try:
                deadline = time.monotonic() + 5
                while not ready.exists() and time.monotonic() < deadline:
                    time.sleep(0.02)
                self.assertTrue(
                    ready.exists(), "Child must actually start before testing the fence"
                )
                time.sleep(0.2)
                blocked = not loaded.exists()
            except BaseException:
                child.kill()
                child.communicate()
                raise
        out, err = child.communicate(timeout=10)
        self.assertEqual(child.returncode, 0, (out, err))
        self.assertTrue(
            blocked, "Assignment read production while reset held its fence"
        )

    def test_checkbox_persists_strict_boolean_and_is_projected(self):
        self.seed()
        result = bridge.save_montage_settings({"useFootageBlocks": True})
        self.assertTrue(
            result["montageSettings"].get("useFootageBlocks"),
            "Render activation must cross IPC persistence",
        )
        self.assertTrue(config.load_settings().montage_use_footage_blocks)
        with self.assertRaises(ValueError):
            bridge.save_montage_settings({"useFootageBlocks": "false"})

    def test_active_block_bypasses_stocks_and_preserves_native_story_beats(self):
        self.scenes[0].update(visual_beat_index=7, visual_beat_count=9)
        self.prepare("stock")
        folder = self.root / "block-only"
        folder.mkdir()
        source = folder / "manual-curated.mp4"
        source.write_bytes(b"isolated block fixture")
        settings = config.load_settings()
        settings.montage_use_footage_blocks = True
        settings.footage_blocks = [
            {
                "id": "b-a",
                "name": "My curated block",
                "root": str(folder),
                "videoCount": 1,
            }
        ]
        settings.footage_block_assignments = {
            "product-1": {"blockId": "b-a", "origin": "manual"}
        }
        config.save_settings(settings)
        with patch.object(
            bridge,
            "StockService",
            side_effect=AssertionError("Block mode must not search stock providers"),
        ):
            result = bridge.prepare_montage({"scenarioIndex": 0})
        project = TimelineProject.load(Path(result["preparedProject"]["path"]))
        self.assertEqual(project.clips[0].path, str(source.resolve()))
        self.assertEqual(project.clips[0].visual_beat_index, 7)
        self.assertEqual(project.clips[0].visual_beat_count, 9)
        self.assertEqual(project.clips[0].voice_segment_ids, [17])
        self.assertEqual(project.source_policy["footageBlock"]["blockId"], "b-a")
        self.assertEqual(project.source_policy["productionItemId"], "product-1")
        self.assertEqual(project.duration, 3)
        self.assertEqual(project.voice_map_provenance["productionItemId"], "product-1")

    def test_block_preparation_preserves_selected_overlays_and_defers_xml(self):
        self.test_active_block_bypasses_stocks_and_preserves_native_story_beats()
        from scriptor.overlays import normalize_overlay_template

        image = self.root / "selected.png"
        image.write_bytes(b"metadata-only image fixture")
        chosen = normalize_overlay_template({"layouts": {"16:9": [
            {"id": "selected", "path": str(image), "mode": "until-end"}
        ]}})
        settings = config.load_settings()
        settings.montage_task_statuses["0"]["overlayTemplate"] = chosen
        settings.montage_task_statuses["0"]["overlayTemplateRevision"] = 1
        settings.montage_export_davinci_xml = True
        config.save_settings(settings)
        with patch("scriptor.timeline.export_fcpxml",
                   side_effect=lambda _project, path: path.write_text("fixture")) as export:
            result = bridge.prepare_montage({"scenarioIndex": 0})
        project = TimelineProject.load(Path(result["preparedProject"]["path"]))
        self.assertEqual(project.overlay_template, chosen)
        export.assert_not_called()
        self.assertIn("после рендера", result["preparedProject"]["warning"])

    def test_saved_block_output_paths_cannot_collide_for_identical_titles(self):
        helper = getattr(bridge, "_montage_project_stem", None)
        self.assertTrue(callable(helper), "Block renders need durable-ID filenames")
        a = TimelineProject(
            "Same title", source_policy={"mode": "block", "productionItemId": "p-a"}
        )
        b = TimelineProject(
            "Same title", source_policy={"mode": "block", "productionItemId": "p-b"}
        )
        self.assertNotEqual(helper(a), helper(b))
        self.assertEqual(helper(TimelineProject("Legacy title")), "Legacy title")

    def test_block_repair_never_queries_global_index_or_providers(self):
        self.handler("assign_footage_block")
        root = self.seed()
        saved = config.load_settings()
        project = TimelineProject(
            "Saved",
            source_policy={
                "mode": "block",
                "footageBlock": {"enabled": True, "blockId": "b-a", "root": str(root)},
            },
        )
        scoped = bridge._project_repair_settings(saved, project)
        from types import SimpleNamespace

        from scriptor.timeline import TimelineClip

        index = SimpleNamespace(
            search_many=lambda *_a, **_k: self.fail("Global index escaped saved block")
        )
        with patch.object(bridge, "_montage_screen_text_safe", return_value=True):
            result = bridge._replacement_candidates_for_clip(
                index, TimelineClip("gone", "N", "Q", duration=3), scoped
            )
        self.assertEqual(
            [item.path for item in result], [str((root / "selected.mp4").resolve())]
        )

    def test_inflight_policy_cannot_cross_product_identity(self):
        self.prepare("stock")
        folder = self.root / "private-policy"
        folder.mkdir()
        (folder / "clip.mp4").write_bytes(b"isolated fixture")
        with self.assertRaisesRegex(ValueError, "Product ID"):
            bridge.prepare_montage(
                {
                    "scenarioIndex": 0,
                    "_progress": lambda *_args: None,
                    "_blockPolicy": {
                        "enabled": True,
                        "blockId": "wrong",
                        "name": "Wrong identity",
                        "root": str(folder),
                        "productionItemId": "different-product",
                    },
                }
            )

    def test_render_policy_uses_saved_root_not_current_ui_assignment(self):
        self.handler("assign_footage_block")
        root = self.seed()
        project = TimelineProject(
            "Saved",
            source_policy={
                "mode": "block",
                "footageBlock": {
                    "enabled": True,
                    "blockId": "saved",
                    "name": "Saved block",
                    "root": str(root),
                    "productionItemId": "p-a",
                },
            },
        )
        settings = config.load_settings()
        scoped = bridge._project_repair_settings(settings, project)
        self.assertEqual(
            getattr(scoped, "_footage_block_policy", {}).get("root"), str(root)
        )
        self.assertEqual(settings.montage_source_mode, "")


if __name__ == "__main__":
    unittest.main()

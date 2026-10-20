"""Multiple manual briefs belong to one durable topic, never its queue position."""
import copy
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from scriptor import bridge, config, session

SOURCE = "Тема: Сад\n\nGreenhouse one\n\nGreenhouse two\n\nGreenhouse three\n\nТема: Хлеб\n\nBread one\n\nBread two\n\nТема: Музыка\n\nPiano one"


class CoverPromptBlocksTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.env = patch.dict(os.environ, {"LOCALAPPDATA": str(self.root), "TEMP": str(self.root / "io"), "TMP": str(self.root / "io")})
        self.env.start()
        self.addCleanup(self.env.stop)
        config.save_settings(config.Settings())
        session.save_session([], [])

    def submit(self, text=SOURCE, **extra):
        return bridge.import_cover_prompt_pairs({
            "text": text, "mode": "blocks", "createMissingTopics": True,
            "importId": "test-block-import", **extra,
        })["operationResult"]

    def rows(self):
        settings = config.load_settings()
        bridge._hydrate_cover_library(settings)
        return settings.cover_queue

    def test_three_topics_3_2_1_variants_keep_order_ids_and_restart(self):
        result = self.submit()
        rows = self.rows()
        self.assertEqual([row["title"] for row in rows], ["Сад", "Хлеб", "Музыка"])
        self.assertEqual([len(row["image_prompt_options"]) for row in rows], [3, 2, 1])
        self.assertEqual(len({row["production_item_id"] for row in rows}), 3)
        self.assertEqual(result["count"], 6)
        for row in rows:
            variants = row["manual_prompt_variants"]
            self.assertEqual([v["number"] for v in variants], list(range(1, len(variants) + 1)))
            self.assertEqual([v["prompt"] for v in variants], row["image_prompt_options"])
            self.assertTrue(all(v["productionItemId"] == row["production_item_id"] for v in variants))
        self.assertEqual(session.load_session(), ([], []))
        self.assertEqual([row["manual_prompt_variants"] for row in self.rows()],
                         [row["manual_prompt_variants"] for row in rows])

    def test_preview_is_read_only_and_commit_keeps_preview_ids_and_numbers(self):
        preview = self.submit(previewOnly=True)
        self.assertEqual(self.rows(), [])
        self.assertEqual(preview["kind"], "cover-prompt-blocks-preview")
        self.assertEqual([len(row["variants"]) for row in preview["topics"]], [3, 2, 1])
        saved = self.submit(previewToken=preview["previewToken"])
        self.assertEqual(saved["topics"], preview["topics"])

    def test_append_is_idempotent_keeps_selection_results_and_continues_numbers(self):
        self.submit()
        settings = config.load_settings()
        first = settings.cover_queue[0]
        original_id = first["production_item_id"]
        first.update(selected_prompt_index=1, image_prompt="Greenhouse two", paths=["kept.png"],
                     selected_path="kept.png", prompt_image_paths=[{"promptIndex": 0, "paths": ["kept.png"]}])
        bridge._save_cover_state(settings)
        old_variants = copy.deepcopy(self.rows()[0]["manual_prompt_variants"])
        self.submit("Тема: Сад\n\nGreenhouse four\n\nGreenhouse five", importId="second")
        self.submit("Тема: Сад\n\nGreenhouse four\n\nGreenhouse five", importId="second")
        row = self.rows()[0]
        self.assertEqual(row["production_item_id"], original_id)
        self.assertEqual(row["manual_prompt_variants"][:3], old_variants)
        self.assertEqual([v["number"] for v in row["manual_prompt_variants"]], [1, 2, 3, 4, 5])
        self.assertEqual(row["image_prompt"], "Greenhouse two")
        self.assertEqual(row["selected_prompt_index"], 1)
        self.assertEqual(row["paths"], ["kept.png"])
        self.assertEqual(row["selected_path"], "kept.png")

    def test_exact_existing_titles_can_delimit_blocks_without_markers(self):
        self.submit()
        self.submit("Сад\n\nGarden four\n\nХлеб\n\nBread three", createMissingTopics=False)
        self.assertEqual(self.rows()[0]["image_prompt_options"][-1], "Garden four")
        self.assertEqual(self.rows()[1]["image_prompt_options"][-1], "Bread three")

    def test_many_multiline_prompts_crlf_bom_and_repeat_submission(self):
        prompts = [f"Exact prompt {n} ✨\nsecond line {n}" for n in range(125)]
        text = "\ufeffТема: Фото\r\n\r\n" + "\r\n\r\n".join(p.replace("\n", "\r\n") for p in prompts) + "\r\n"
        self.submit(text)
        self.submit(text)
        self.assertEqual(self.rows()[0]["image_prompt_options"], prompts)
        self.assertEqual(self.rows()[0]["manual_prompt_variants"][-1]["number"], 125)

    def test_selected_product_id_accepts_only_prompts_after_queue_reorder(self):
        self.submit()
        settings = config.load_settings()
        identity = settings.cover_queue[1]["production_item_id"]
        settings.cover_queue.reverse()
        bridge._save_cover_state(settings)
        self.submit("Bread three\n\nBread four", productionItemId=identity)
        row = next(row for row in self.rows() if row["production_item_id"] == identity)
        self.assertEqual(row["image_prompt_options"][-2:], ["Bread three", "Bread four"])

    def test_invalid_empty_topic_is_atomic_and_never_calls_provider(self):
        with patch.object(bridge.FastGenPool, "generate_media", side_effect=AssertionError("no provider")), \
                self.assertRaisesRegex(ValueError, "EMPTY_TOPIC_PROMPTS"):
            self.submit("Тема: Valid\n\nA valid prompt\n\nТема: Empty")
        self.assertEqual(self.rows(), [])

    def test_ambiguous_existing_topic_does_not_add_previous_new_block(self):
        settings = config.load_settings()
        settings.cover_queue = [{"title": "Duplicate", "production_item_id": "a"},
                                {"title": "Duplicate", "production_item_id": "b"}]
        bridge._save_cover_state(settings)
        with self.assertRaisesRegex(ValueError, "AMBIGUOUS_TOPIC"):
            self.submit("Тема: New\n\nNew prompt\n\nТема: Duplicate\n\nBad")
        self.assertEqual(len(self.rows()), 2)

    def test_preview_becomes_stale_after_another_append(self):
        self.submit()
        pending = "Тема: Сад\n\nGarden four"
        preview = self.submit(pending, previewOnly=True)
        self.submit("Тема: Сад\n\nAnother new prompt", importId="other")
        with self.assertRaisesRegex(ValueError, "STALE_PREVIEW"):
            self.submit(pending, previewToken=preview["previewToken"])
        self.assertNotIn("Garden four", self.rows()[0]["image_prompt_options"])

    def test_active_generation_rejects_import_without_changing_its_prompt(self):
        self.submit()
        before = self.rows()
        lock = bridge._claim_cover_generation_lock()
        self.assertIsNotNone(lock)
        try:
            with self.assertRaisesRegex(ValueError, "COVER_BATCH_ACTIVE"):
                self.submit("Тема: Сад\n\nNew while running")
        finally:
            bridge._release_cover_generation_lock(lock)
        self.assertEqual(self.rows(), before)

    def configure_render(self):
        settings = config.load_settings()
        settings.cover_output_folder = str(self.root / "covers")
        settings.cover_variant_count = 1
        settings.cover_build_mode = "fastgen-full"
        settings.cover_auto_overlay_text = False
        settings.cover_api_keys = [config.FastGenKey(label="offline", secret="offline")]
        settings.fastgen_capabilities_cache = {"image": [{"id": "nano_banana_2_image_generate", "inputs": {"min": 0, "max": 10}}]}
        settings.cover_operation = "nano_banana_2_image_generate"
        config.save_settings(settings)

    def offline_image(self, _prompt, output, stem, *_args, **_kwargs):
        from PIL import Image
        target = Path(output) / (stem + ".png")
        target.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (16, 16), "green").save(target)
        return [target]

    def test_real_batch_render_keeps_every_result_at_its_topic_and_variant(self):
        self.configure_render()
        self.submit()
        rows = self.rows()
        with patch.object(bridge.FastGenPool, "generate_media", side_effect=self.offline_image) as provider, \
                patch.object(bridge, "HybridTextPool", side_effect=AssertionError("paid text forbidden")):
            bridge.generate_covers({"productionItemIds": [row["production_item_id"] for row in rows], "buildMode": "fastgen-full"})
        self.assertEqual(provider.call_count, 6)
        paths = []
        for row in self.rows():
            self.assertEqual(row["status"], "Готово")
            variants = row["manual_prompt_variants"]
            results = row["prompt_image_paths"]
            self.assertEqual([v["promptVariantId"] for v in results], [v["id"] for v in variants])
            self.assertEqual([v["promptNumber"] for v in results], [v["number"] for v in variants])
            self.assertTrue(all(v["productionItemId"] == row["production_item_id"] for v in results))
            for path in row["paths"]:
                self.assertTrue(Path(path).is_file())
                self.assertTrue(Path(path).resolve().is_relative_to(self.root.resolve()))
                paths.append(path)
        self.assertEqual(len(set(paths)), 6)

    def test_append_then_generate_only_new_variants_preserves_previous_images(self):
        self.configure_render()
        self.submit("Тема: Сад\n\nGreenhouse one")
        with patch.object(bridge.FastGenPool, "generate_media", side_effect=self.offline_image) as provider:
            bridge.generate_covers({"buildMode": "fastgen-full"})
            old_path = self.rows()[0]["path"]
            old_bytes = Path(old_path).read_bytes()
            self.submit("Тема: Сад\n\nGreenhouse two\n\nGreenhouse three", importId="append")
            bridge.generate_covers({"buildMode": "fastgen-full"})
            self.assertEqual(provider.call_count, 3)
            bridge.generate_covers({"buildMode": "fastgen-full"})
            self.assertEqual(provider.call_count, 3)
        row = self.rows()[0]
        self.assertEqual(len(row["paths"]), 3)
        self.assertIn(old_path, row["paths"])
        self.assertEqual(Path(old_path).read_bytes(), old_bytes)
        self.assertEqual(row["selected_path"], old_path)
        self.assertEqual([v["promptNumber"] for v in row["prompt_image_paths"]], [1, 2, 3])

    def test_unchecked_missing_only_checkbox_regenerates_all_without_overwriting_old_files(self):
        self.configure_render()
        self.submit("Тема: Сад\n\nGreenhouse one\n\nGreenhouse two")
        with patch.object(bridge.FastGenPool, "generate_media", side_effect=self.offline_image) as provider:
            bridge.generate_covers({"buildMode": "fastgen-full"})
            old_paths = self.rows()[0]["paths"]
            old_hashes = {p: Path(p).read_bytes() for p in old_paths}
            bridge.generate_covers({"buildMode": "fastgen-full", "manualMissingOnly": False})
        self.assertEqual(provider.call_count, 4)
        row = self.rows()[0]
        self.assertEqual(len(set(row["paths"])), 4)
        self.assertTrue(all(Path(p).read_bytes() == value for p, value in old_hashes.items()))

    def test_checkbox_setting_survives_settings_reload(self):
        bridge.save_cover_settings({"manualMissingOnly": False})
        self.assertFalse(config.load_settings().cover_manual_missing_only)
        self.assertFalse(bridge.snapshot()["coverSettings"]["manualMissingOnly"])
        bridge.save_cover_settings({"manualMissingOnly": True})
        self.assertTrue(config.load_settings().cover_manual_missing_only)

    def test_select_variant_resolves_product_id_after_queue_reorder(self):
        self.submit()
        settings = config.load_settings()
        identity = settings.cover_queue[0]["production_item_id"]
        settings.cover_queue.reverse()
        bridge._save_cover_state(settings)
        bridge.select_cover_prompt({"index": 0, "option": 2, "productionItemId": identity})
        row = next(row for row in self.rows() if row["production_item_id"] == identity)
        self.assertEqual(row["image_prompt"], "Greenhouse three")

    def test_explicit_remove_then_reimport_does_not_resurrect_removed_variants(self):
        self.submit("Тема: Сад\n\nOld one\n\nOld two")
        bridge.remove_cover_prompts({"indices": [0]})
        self.submit("Тема: Сад\n\nFresh only", importId="fresh")
        self.assertEqual(self.rows()[0]["image_prompt_options"], ["Fresh only"])

    def test_corrupt_variant_state_is_rejected_without_replacing_other_topics(self):
        self.submit()
        settings = config.load_settings()
        settings.cover_queue[0]["manual_prompt_variants"][0]["productionItemId"] = "wrong"
        bridge._save_cover_state(settings)
        before = self.rows()
        with self.assertRaisesRegex(ValueError, "INVALID_MANUAL_PROMPT_STATE"):
            self.submit("Тема: New\n\nNew prompt\n\nТема: Сад\n\nMore")
        self.assertEqual(self.rows(), before)

    def test_additive_generation_preserves_complete_repeat_contract_and_variant_numbers(self):
        self.configure_render()
        self.submit("Тема: Сад\n\nGarden one\n\nGarden two")
        with patch.object(bridge.FastGenPool, "generate_media", side_effect=self.offline_image) as provider:
            bridge.generate_covers({"buildMode": "fastgen-full"})
            self.submit("Тема: Сад\n\nGarden three", importId="append-third")
            bridge.generate_covers({"buildMode": "fastgen-full"})
            row = self.rows()[0]
            contracts = list(row["final_provider_prompt_options"])
            self.assertEqual(len(contracts), 3)
            bridge.regenerate_covers({"indices": [0], "productionItemIds": [row["production_item_id"]], "currentProfile": True})
            self.assertEqual(provider.call_count, 6)
            self.assertEqual([call.args[0] for call in provider.call_args_list[-3:]], contracts)
        self.assertEqual([v["promptNumber"] for v in self.rows()[0]["prompt_image_paths"]], [1, 2, 3])

    def test_explicit_ai_rewrite_discards_manual_metadata(self):
        self.submit("Тема: Сад\n\nOld one\n\nOld two")
        settings = config.load_settings()
        row = settings.cover_queue[0]
        staged = {0: {"image_prompt_options": ["New automatic"], "selected_prompt_index": 0, "image_prompt": "New automatic", "prompt_provider": "agent", "prompt_text_signature": "new", "prompt_revision_id": "new"}}
        bridge._commit_fresh_prompt_rewrite(settings, [(0, row)], staged, {}, provider="agent")
        self.assertNotIn("manual_prompt_variants", row)
        self.assertNotIn("manual_prompt_schema", row)

    def test_accepted_appended_variant_recovers_without_losing_old_image_or_new_paid_create(self):
        self.configure_render()
        self.submit("Тема: Сад\n\nGarden one")
        with patch.object(bridge.FastGenPool, "generate_media", side_effect=self.offline_image):
            bridge.generate_covers({"buildMode": "fastgen-full"})
        old_path = self.rows()[0]["path"]
        self.submit("Тема: Сад\n\nGarden two", importId="append-recover")
        error = bridge.FastGenError("polling interrupted after acceptance")
        error.generation_id = "generation-accepted-two"
        with patch.object(bridge.FastGenPool, "generate_media", side_effect=error) as provider:
            bridge.generate_covers({"buildMode": "fastgen-full"})
            with self.assertRaisesRegex(ValueError, "ACCEPTED_MANUAL_GENERATION"):
                bridge.generate_covers({"buildMode": "fastgen-full"})
            self.assertEqual(provider.call_count, 1)
        recovered = self.offline_image("", self.root / "covers", "recovered-two")[0]
        with patch.object(bridge.FastGenPool, "recover_generation", return_value={"status": "succeeded", "paths": [recovered]}) as recovery:
            bridge.recover_cover_generation({})
            self.assertEqual(recovery.call_count, 1)
        row = self.rows()[0]
        self.assertIn(old_path, row["paths"])
        self.assertIn(str(recovered), row["paths"])
        self.assertEqual([v["promptNumber"] for v in row["prompt_image_paths"]], [1, 2])
        with patch.object(bridge.FastGenPool, "generate_media", side_effect=AssertionError("no duplicate paid create")):
            bridge.generate_covers({"buildMode": "fastgen-full"})

    def test_incompatible_repeat_is_rejected_before_any_images_are_removed(self):
        self.configure_render()
        self.submit("Тема: Сад\n\nGarden one\n\nGarden two")
        with patch.object(bridge.FastGenPool, "generate_media", side_effect=self.offline_image):
            bridge.generate_covers({"buildMode": "fastgen-full"})
        settings = config.load_settings()
        row = settings.cover_queue[0]
        row["manual_prompt_contracts"][row["manual_prompt_variants"][1]["id"]]["renderProfile"]["build_mode"] = "fastgen-full-my-face"
        bridge._save_cover_state(settings)
        before = self.rows()[0]
        with self.assertRaisesRegex(ValueError, "MANUAL_REPEAT_CONTRACT_MISMATCH"):
            bridge.regenerate_covers({"indices": [0], "productionItemIds": [row["production_item_id"]], "currentProfile": True})
        self.assertTrue(all(Path(path).is_file() for path in before["paths"]))
        self.assertEqual(self.rows()[0]["paths"], before["paths"])


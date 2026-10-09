"""Recover completed covers using durable row provenance, never queue position."""
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from PIL import Image

from scriptor import bridge, config
from scriptor.cover_library import CoverLibrary


class CoverResultIdentityTests(unittest.TestCase):
    def setUp(self):
        root = self.enterContext(TemporaryDirectory(prefix="newsflow-cover-result-"))
        self.root = Path(root)
        self.enterContext(patch.dict(os.environ, {
            "NEWSFLOW_TEST_MODE": "1", "NEWSFLOW_TEST_ROOT": root, "LOCALAPPDATA": root,
            "NEWSFLOW_PRODUCTION_LOCALAPPDATA": str(self.root / "untouched-production"),
        }))
        self.enterContext(patch.object(config, "gpu_timeline_available", return_value=False))
        self.enterContext(patch.object(bridge, "snapshot", return_value={}))
        self.enterContext(patch.object(bridge.FastGenPool, "generate_media",
                                      side_effect=AssertionError("reconcile must never generate")))
        self.output = Path(config.Settings().cover_output_folder)
        self.output.mkdir(parents=True)

    def image(self, name):
        path = self.output / name
        Image.new("RGB", (8, 8), "red").save(path)
        return str(path)

    def save(self, rows):
        config.save_settings(config.Settings(cover_output_folder=str(self.output), cover_queue=rows))

    def test_recovers_recorded_variant_paths_by_id_after_queue_reorder(self):
        path = self.image("001 — Original topic — prompt 01.png")
        manual = {"image_prompt": "  Literal manual prompt ✨  ", "prompt_provider": "manual",
                  "cover_headline": "USER HEADLINE", "headline_source": "MANUAL",
                  "cover_subheadline": "USER SUBHEADLINE", "subheadline_source": "MANUAL",
                  "face_reference_source": "manual", "face_reference_label": "Operator face",
                  "face_reference_path": "operator.png"}
        self.save([
            {"production_item_id": "other", "title": "Other topic", "paths": []},
            {"production_item_id": "original", "title": "Original topic", "paths": [],
             "status": "Требуется восстановление FastGen", **manual,
             "prompt_image_paths": [{"prompt": "Literal manual prompt", "paths": [path]}]},
        ])
        result = bridge.reconcile_cover_gallery()["operationResult"]["health"]
        self.assertEqual(result["repaired"], 1)
        rows = {row["production_item_id"]: row for row in config.load_settings().cover_queue}
        self.assertEqual(rows["original"]["paths"], [path])
        self.assertEqual(rows["original"]["status"], "Готово")
        self.assertEqual(rows["other"]["paths"], [])
        for key, value in manual.items():
            self.assertEqual(rows["original"][key], value)
        restored, _, _ = CoverLibrary(bridge._cover_library_path()).hydrate(
            [], {}, {}, active_production_ids={"original", "other"},
        )
        self.assertEqual(next(row for row in restored if row["production_item_id"] == "original")["paths"], [path])

    def test_durable_row_does_not_adopt_unknown_file_from_queue_number_and_title(self):
        self.image("001 — Same title — prompt 01.png")
        self.save([{"production_item_id": "new-production", "title": "Same title", "paths": []}])
        result = bridge.reconcile_cover_gallery()["operationResult"]["health"]
        self.assertEqual(result["repaired"], 0)
        self.assertEqual(result["orphan"], 1)
        self.assertEqual(config.load_settings().cover_queue[0]["paths"], [])

    def test_ambiguous_legacy_titles_do_not_use_first_match(self):
        self.image("001 — Same title — prompt 01.png")
        self.save([{"title": "Same title", "paths": []}, {"title": "Same title", "paths": []}])
        result = bridge.reconcile_cover_gallery()["operationResult"]["health"]
        self.assertEqual(result["repaired"], 0)
        self.assertTrue(all(not row["paths"] for row in config.load_settings().cover_queue))

    def test_prefix_related_legacy_titles_do_not_share_a_file(self):
        self.image("002 — Topic — Extra — prompt 01.png")
        self.save([{"title": "Topic", "paths": []}, {"title": "Topic — Extra", "paths": []}])
        result = bridge.reconcile_cover_gallery()["operationResult"]["health"]
        self.assertEqual(result["repaired"], 0)
        self.assertEqual(result["orphan"], 1)

    def test_automatic_resume_cannot_unpause_or_bypass_disabled_auto_resume(self):
        for paused, automatic_enabled in [(True, True), (False, False)]:
            with self.subTest(paused=paused, automatic_enabled=automatic_enabled):
                settings = config.Settings(cover_generation_paused=paused,
                                           cover_rate_auto_resume=automatic_enabled,
                                           cover_queue=[{"production_item_id": "owned", "title": "Topic",
                                                         "status": "Приостановлено"}])
                config.save_settings(settings)
                with patch.object(bridge.sys, "argv", ["bridge", "resume-cover-generation"]), \
                        patch.object(bridge, "_bridge_payload_from_cli", return_value={"automatic": True}), \
                        patch.object(bridge, "start_action_trace") as trace, \
                        patch.object(bridge, "generate_covers", return_value={}) as generate, \
                        patch("builtins.print"):
                    trace.return_value.result_context.return_value = {}
                    bridge.main()
                generate.assert_not_called()
                self.assertEqual(config.load_settings().cover_generation_paused, paused)

    def test_84_rows_keep_78_completed_links_after_reorder_and_restart(self):
        rows = [
            {"production_item_id": f"production:{i}", "title": f"Topic {i}",
             "paths": [self.image(f"{i:03d} — Topic {i}.png")] if i <= 78 else [],
             "status": "Готово" if i <= 78 else "Требуется восстановление FastGen"}
            for i in range(1, 85)
        ]
        expected = {row["production_item_id"]: row["paths"] for row in rows}
        self.save(list(reversed(rows)))
        bridge.reconcile_cover_gallery()
        restored = config.load_settings().cover_queue
        self.assertEqual(len(restored), 84)
        self.assertEqual(sum(bool(row["paths"]) for row in restored), 78)
        self.assertEqual({row["production_item_id"]: row["paths"] for row in restored}, expected)

    def test_enabled_automatic_and_explicit_manual_resume_remain_available(self):
        for automatic in [True, False]:
            with self.subTest(automatic=automatic):
                config.save_settings(config.Settings(
                    cover_generation_paused=not automatic, cover_rate_auto_resume=automatic,
                    cover_queue=[{"production_item_id": "owned", "title": "Topic",
                                  "status": "Ожидает лимит FastGen"}],
                ))
                with patch.object(bridge.sys, "argv", ["bridge", "resume-cover-generation"]), \
                        patch.object(bridge, "_bridge_payload_from_cli", return_value={"automatic": automatic}), \
                        patch.object(bridge, "start_action_trace") as trace, \
                        patch.object(bridge, "generate_covers", return_value={}) as generate, \
                        patch("builtins.print"):
                    trace.return_value.result_context.return_value = {}
                    bridge.main()
                generate.assert_called_once_with({"indices": [0], "productionItemIds": ["owned"]})
                self.assertFalse(config.load_settings().cover_generation_paused)

    def test_manual_text_save_resolves_id_not_stale_queue_index(self):
        for command, field, value in [
            (bridge.save_cover_headline, "headline", "Operator headline"),
            (bridge.save_cover_subheadline, "subheadline", "Operator secondary text"),
        ]:
            with self.subTest(field=field):
                self.save([
                    {"production_item_id": "other", "title": "Same title"},
                    {"production_item_id": "owned", "title": "Same title"},
                ])
                command({"index": 0, "productionItemId": "owned", field: value})
                rows = config.load_settings().cover_queue
                self.assertFalse(rows[0].get(f"cover_{field}"))
                self.assertEqual(rows[1][f"cover_{field}"], value)
                before = config.config_path().read_bytes()
                with self.assertRaisesRegex(ValueError, "ProductionItem"):
                    command({"index": 0, "productionItemId": "removed", field: value})
                self.assertEqual(config.config_path().read_bytes(), before)

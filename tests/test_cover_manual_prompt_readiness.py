"""Accepted user-owned prompts must not inherit AUTO/history brief limits."""
from __future__ import annotations

import base64
import os
import unittest
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from scriptor import bridge
from scriptor.config import FastGenKey, Settings


class ManualPromptReadinessTests(unittest.TestCase):
    def test_manual_active_options_preserve_literal_text_across_auto_size_boundary(self):
        for length in (800, 801, 902, 12000):
            with self.subTest(length=length):
                prefix = "Photorealistic YouTube scene: "
                prompt = prefix + "x" * (length - len(prefix))
                row = {
                    "prompt_provider": "manual", "image_prompt": prompt,
                    "image_prompt_options": [prompt],
                }
                before = deepcopy(row)
                self.assertEqual(bridge._cover_active_prompt_options(row), [prompt])
                self.assertEqual(row, before)

    def test_manual_style_and_whitespace_are_not_semantically_extracted(self):
        prompt = "  Photorealistic  YouTube thumbnail.\nTypography: bold. ✨  "
        row = {"prompt_provider": "manual", "image_prompt": prompt}
        self.assertEqual(bridge._cover_active_prompt_options(row), [prompt])

    def test_blank_manual_options_are_not_ready(self):
        self.assertEqual(bridge._cover_active_prompt_options({
            "prompt_provider": "manual", "image_prompt": " \t\n",
            "image_prompt_options": ["", " \t", None],
        }), [])

    def test_auto_briefs_and_manual_history_remain_bounded(self):
        oversized_scene = "Workers examine the signed closure order at the factory gate. " * 30
        self.assertEqual(bridge._cover_active_prompt_options({
            "prompt_provider": "agent", "image_prompt": oversized_scene,
        }), [])
        row = {"prompt_provider": "manual"}
        bridge._remember_cover_prompt_history(row, [oversized_scene])
        self.assertEqual(bridge._cover_recent_prompt_history(row), [])


class ManualPromptRenderIntegrationTests(unittest.TestCase):
    def setUp(self):
        temporary = self.enterContext(TemporaryDirectory(prefix="newsflow-manual-prompt-"))
        self.root = Path(temporary)
        self.enterContext(patch.dict(os.environ, {
            "NEWSFLOW_TEST_MODE": "1", "NEWSFLOW_TEST_ROOT": temporary,
            "LOCALAPPDATA": temporary,
        }))
        self.enterContext(patch.object(bridge, "snapshot", return_value={}))
        self.enterContext(patch.object(
            bridge, "HybridTextPool", side_effect=AssertionError("manual render must not call text AI"),
        ))
        self.identity = "production:manual-long"
        self.title = "Factory closure announcement"
        settings = Settings(
            montage_renderer="ffmpeg", cover_output_folder=str(self.root / "covers"),
            cover_auto_overlay_text=False, cover_variant_count=1,
            cover_api_keys=[FastGenKey(label="offline-fixture", secret="offline-fixture")],
            idea_production_items=[
                {"id": "production:other", "title": "Other topic"},
                {"id": self.identity, "title": self.title},
            ],
            cover_queue=[
                {"production_item_id": "production:other", "title": "Other topic",
                 "image_prompt": "Untouched other scene"},
                {"production_item_id": self.identity, "title": self.title,
                 "cover_headline": "FACTORY CLOSES", "cover_subheadline": "WORKERS WAIT",
                 "headline_source": "MANUAL", "subheadline_source": "MANUAL",
                 "face_reference_source": "manual", "face_reference_label": "Operator choice",
                 "face_reference_path": str(self.root / "operator-face.png"),
                 "cover_face_required": False},
            ],
        )
        bridge._save_cover_state(settings)

    def _row(self, identity=None):
        settings = bridge.load_settings()
        bridge._hydrate_cover_library(settings)
        return next(row for row in settings.cover_queue
                    if row.get("production_item_id") == (identity or self.identity))

    def _render(self, prompt):
        # Mock only the paid boundary; persistence, readiness, ID resolution and
        # the render-time final provider builder all run as production code.
        def offline_image(_prompt, output, *_args, **_kwargs):
            # Match FastGen's output contract: write into the supplied staging
            # directory so the real publication fence can remain enabled.
            image = Path(output) / "offline-cover.png"
            image.parent.mkdir(parents=True, exist_ok=True)
            image.write_bytes(base64.b64decode(
                "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aP1sAAAAASUVORK5CYII="
            ))
            return [image]

        with patch.object(bridge.FastGenPool, "generate_media", side_effect=offline_image) as provider:
            bridge.generate_covers({
                "indices": [1], "productionItemIds": [self.identity],
                "_parallel_cover_worker": True,
                "operation": "gemini_nano_banana_2_image_generate",
                "buildMode": "fastgen-full", "faceMode": "without", "textMode": "fastgen",
            })
        provider.assert_called_once()
        final = provider.call_args.args[0]
        self.assertIn("STORY CONTEXT:\n" + " ".join(prompt.split()) + "\n\nMAIN SUBJECT:", final)
        self.assertIn("NEWSFLOW FASTGEN UNIVERSAL THUMBNAIL CORE V2", final)
        self.assertIn("TYPOGRAPHY:", final)
        self.assertIn("FINAL NEGATIVE RULES:", final)
        self.assertIn("<exact-text>FACTORY CLOSES</exact-text>", final)
        self.assertIn("<exact-text>WORKERS WAIT</exact-text>", final)
        self.assertEqual(provider.call_args.args[3], "gemini_nano_banana_2_image_generate")
        row = self._row()
        self.assertEqual(row["status"], "Готово")
        self.assertEqual(row["image_prompt"], prompt)
        self.assertEqual(row["image_prompt_options"], [prompt])
        self.assertEqual(row["prompt_provider"], "manual")
        self.assertEqual(row["production_item_id"], self.identity)
        self.assertEqual(row["final_provider_prompt"], final)
        self.assertEqual(row["face_reference_label"], "Operator choice")
        self.assertEqual(row["face_reference_source"], "manual")
        self.assertEqual(self._row("production:other")["image_prompt"], "Untouched other scene")

    def test_imported_long_manual_prompt_survives_reload_and_reaches_render_builder(self):
        prompt = "Photorealistic YouTube thumbnail: " + "workers hold a signed closure notice; " * 30 + "✨"
        bridge.import_cover_prompt_pairs({"text": self.title + "\r\n" + prompt})
        self.assertEqual(self._row()["image_prompt"], prompt)
        self._render(prompt)

    def test_edited_long_manual_prompt_survives_reload_and_reaches_render_builder(self):
        prompt = "  Photorealistic YouTube scene:\n" + "  workers hold closure notices; " * 30 + "✨  "
        bridge.save_cover_manual_prompt({"productionItemId": self.identity, "prompt": prompt})
        self.assertEqual(self._row()["image_prompt"], prompt)
        self._render(prompt)

    def test_persisted_blank_manual_prompt_fails_before_fastgen(self):
        settings = bridge.load_settings()
        settings.cover_queue[1].update(
            prompt_provider="manual", image_prompt=" \t\n", image_prompt_options=[" "],
        )
        bridge._save_cover_state(settings)
        with patch.object(bridge.FastGenPool, "generate_media") as provider, \
             self.assertRaisesRegex(ValueError, "Нет готового visual prompt"):
            bridge.generate_covers({
                "indices": [1], "productionItemIds": [self.identity],
                "_parallel_cover_worker": True,
            })
        provider.assert_not_called()


if __name__ == "__main__":
    unittest.main()

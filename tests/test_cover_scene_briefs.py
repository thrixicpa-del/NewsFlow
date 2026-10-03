from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from scriptor import bridge
from scriptor.config import Settings
from scriptor.thumbnail_prompt_v2 import build_final_provider_prompt


class CoverSceneBriefTests(unittest.TestCase):
    @staticmethod
    def _item(**extra: object) -> dict:
        return {
            "production_item_id": "production:scene-brief",
            "title": "Workers protest a factory closure",
            "script": "Workers gather outside the factory after management announces the closure.",
            **extra,
        }

    def _generate(self, settings: Settings, response: str, *, rewrite: bool = False) -> tuple[dict, list[str]]:
        sent: list[str] = []

        async def provider(prompt: str, **_kwargs: object) -> str:
            sent.append(prompt)
            return response

        with patch.object(bridge, "load_settings", return_value=settings), \
             patch.object(bridge, "_hydrate_cover_library", return_value=False), \
             patch.object(bridge, "_save_cover_state"), \
             patch.object(bridge, "snapshot", return_value={}), \
             patch.object(bridge, "HybridTextPool", return_value=SimpleNamespace(generate=provider)):
            bridge.generate_cover_prompts({
                "indices": [0],
                "productionItemIds": ["production:scene-brief"],
                "provider": "agent",
                "rewrite": rewrite,
            })
        return settings.cover_queue[0], sent

    def test_generated_scene_brief_is_short_while_render_time_prompt_keeps_v2_contract(self):
        settings = Settings(cover_prompt_variant_count=1, cover_queue=[self._item()])
        row, _sent = self._generate(
            settings,
            json.dumps({"prompts": [
                "Workers raise closure notices outside the factory gate while a manager carries the signed order past a silent line of employees."
            ], "recommended": 1}),
        )

        self.assertLessEqual(len(row["image_prompt"]), 800)
        self.assertNotIn("CORE STYLE", row["image_prompt"])
        self.assertNotIn("TYPOGRAPHY", row["image_prompt"])
        self.assertNotIn("FINAL NEGATIVE RULES", row["image_prompt"])
        final = build_final_provider_prompt(row["image_prompt"], row)
        self.assertIn("NEWSFLOW FASTGEN UNIVERSAL THUMBNAIL CORE V2", final)
        self.assertIn("TYPOGRAPHY:", final)
        self.assertIn("FINAL NEGATIVE RULES:", final)

    def test_oversize_scene_brief_is_rejected_without_silent_truncation(self):
        settings = Settings(cover_prompt_variant_count=1, cover_queue=[self._item()])
        oversize = "Workers carry signed closure notices through the factory gate. " * 20
        row, sent = self._generate(
            settings,
            json.dumps({"prompts": [oversize], "recommended": 1}),
        )

        # One bounded semantic repair is allowed, but no oversized scene is
        # silently truncated into a different durable prompt.
        self.assertEqual(len(sent), 2)
        self.assertNotIn("image_prompt", row)
        self.assertIn("SCENE_BRIEF_TOO_LONG", row["error"])

    def test_rewrite_rejects_camera_only_duplicate_and_preserves_old_prompt_and_files(self):
        with TemporaryDirectory() as directory:
            image = Path(directory) / "accepted.png"
            image.write_bytes(b"accepted")
            old = "Workers hold closure notices at the factory gate while management posts the signed order."
            settings = Settings(cover_output_folder=directory, cover_prompt_variant_count=1, cover_queue=[self._item(
                image_prompt=old,
                image_prompt_options=[old],
                paths=[str(image)],
                path=str(image),
                selected_path=str(image),
            )])
            row, _sent = self._generate(
                settings,
                json.dumps({"prompts": [
                    "Wide telephoto view of workers holding closure notices at the factory gate while management posts the signed order."
                ], "recommended": 1}),
                rewrite=True,
            )

            self.assertEqual(row["image_prompt"], old)
            self.assertEqual(row["paths"], [str(image)])
            self.assertTrue(image.is_file())
            self.assertIn("semantic", row["error"].casefold())

    def test_rewrite_rejects_a_semantic_paraphrase_not_just_an_exact_duplicate(self):
        old = "Workers hold closure notices at the factory gate while management posts the signed order."
        settings = Settings(cover_prompt_variant_count=1, cover_queue=[self._item(
            image_prompt=old,
            image_prompt_options=[old],
        )])
        row, _sent = self._generate(
            settings,
            json.dumps({"prompts": [
                "Management posts the signed closure order at the factory gate as workers hold closure notices."
            ], "recommended": 1}),
            rewrite=True,
        )

        self.assertEqual(row["image_prompt"], old)
        self.assertIn("SEMANTIC_SCENE_DUPLICATE", row["error"])

    def test_rewrite_sends_short_scene_history_not_legacy_v2_payload(self):
        legacy = build_final_provider_prompt(
            "Workers hold closure notices at the factory gate while management posts the signed order.",
            self._item(),
        )
        settings = Settings(cover_prompt_variant_count=1, cover_queue=[self._item(
            image_prompt=legacy,
            image_prompt_options=[legacy],
            recent_visual_prompt_history=[legacy],
        )])
        _row, sent = self._generate(
            settings,
            json.dumps({"prompts": [
                "Employees examine the signed closure order beside the factory entrance as union representatives address the group."
            ], "recommended": 1}),
            rewrite=True,
        )

        self.assertEqual(len(sent), 1)
        history = sent[0].split("ПРЕДЫДУЩИЕ ВАРИАНТЫ:\n", 1)[1]
        self.assertNotIn("CORE STYLE", history)
        self.assertNotIn("TYPOGRAPHY", history)
        self.assertLessEqual(max(len(line[2:]) for line in history.splitlines() if line.startswith("- ")), 800)

    def test_enhanced_rewrite_requires_a_supported_semantic_scene_change(self):
        old = "Workers hold closure notices at the factory gate while management posts the signed order."
        settings = Settings(cover_prompt_variant_count=1, cover_scene_intensity_mode=True, cover_queue=[self._item(
            image_prompt=old,
            image_prompt_options=[old],
        )])
        row, _sent = self._generate(
            settings,
            json.dumps({"prompts": [
                "Wide elevated view of workers holding closure notices at the factory gate while management posts the signed order."
            ], "recommended": 1}),
            rewrite=True,
        )

        self.assertEqual(row["image_prompt"], old)
        self.assertIn("semantic", row["error"].casefold())

    def test_enhanced_rewrite_keeps_supported_new_scale_and_reaction_in_the_scene_brief(self):
        old = "Workers hold closure notices at the factory gate while management posts the signed order."
        settings = Settings(cover_prompt_variant_count=1, cover_scene_intensity_mode=True, cover_queue=[self._item(
            image_prompt=old,
            image_prompt_options=[old],
        )])
        row, _sent = self._generate(
            settings,
            json.dumps({"prompts": [
                "A dense line of workers gathers at the factory gate as union representatives read the signed closure order to the group."
            ], "recommended": 1}),
            rewrite=True,
        )

        self.assertIn("dense line of workers", row["image_prompt"])
        self.assertIn("union representatives", row["image_prompt"])
        self.assertNotEqual(row["image_prompt"], old)
        self.assertNotIn("explosion", row["image_prompt"].casefold())

    def test_enhanced_generation_rejects_an_unsupported_violent_scene(self):
        neutral = {
            "production_item_id": "production:neutral-scene",
            "title": "Company publishes quarterly report",
            "script": "The chief executive presents a financial chart to investors.",
        }
        settings = Settings(cover_prompt_variant_count=1, cover_scene_intensity_mode=True, cover_queue=[neutral])
        sent: list[str] = []

        async def provider(prompt: str, **_kwargs: object) -> str:
            sent.append(prompt)
            return json.dumps({"prompts": [
                "A massive explosion destroys city blocks as armed soldiers evacuate a terrified crowd."
            ], "recommended": 1})

        with patch.object(bridge, "load_settings", return_value=settings), \
             patch.object(bridge, "_hydrate_cover_library", return_value=False), \
             patch.object(bridge, "_save_cover_state"), \
             patch.object(bridge, "snapshot", return_value={}), \
             patch.object(bridge, "HybridTextPool", return_value=SimpleNamespace(generate=provider)):
            bridge.generate_cover_prompts({
                "indices": [0],
                "productionItemIds": ["production:neutral-scene"],
                "provider": "agent",
            })

        self.assertEqual(len(sent), 2)
        self.assertNotIn("image_prompt", settings.cover_queue[0])
        self.assertIn("UNSUPPORTED_SCENE_EVENT", settings.cover_queue[0]["error"])

    def test_generated_sibling_variants_keep_distinct_supported_scene_strategies(self):
        settings = Settings(cover_prompt_variant_count=3, cover_queue=[self._item()])
        row, _sent = self._generate(
            settings,
            json.dumps({"prompts": [
                "Workers hold closure notices at the factory gate while the manager posts the signed order.",
                "Union representatives address gathered employees as the closure order is read aloud outside the factory.",
                "A signed closure notice and an idle factory entrance show the immediate consequence for the workforce."
            ], "recommended": 2}),
        )

        self.assertEqual(len(row["image_prompt_options"]), 3)
        self.assertTrue(all(len(value) <= 800 for value in row["image_prompt_options"]))
        self.assertTrue(all(
            bridge._cover_scene_similarity(left, right) < 0.72
            for position, left in enumerate(row["image_prompt_options"])
            for right in row["image_prompt_options"][position + 1:]
        ))

    def test_legacy_v2_is_projected_as_short_ui_scene_without_mutating_or_shortening_manual_text(self):
        scene = "Workers hold closure notices outside the factory gate while management posts the signed order."
        legacy = build_final_provider_prompt(scene, self._item())
        auto = {
            **self._item(),
            "image_prompt": legacy,
            "image_prompt_options": [legacy],
            "prompt_provider": "agent",
        }
        auto_before = dict(auto)
        projected = bridge._cover_prompt_ui_projection(auto)
        self.assertEqual(projected["image_prompt"], scene)
        self.assertEqual(projected["image_prompt_options"], [scene])
        self.assertEqual(auto, auto_before)

        manual = "Photorealistic editorial scene with workers outside the factory gate."
        manual_row = {
            **self._item(),
            "image_prompt": manual,
            "image_prompt_options": [manual],
            "prompt_provider": "manual",
        }
        manual_projected = bridge._cover_prompt_ui_projection(manual_row)
        self.assertEqual(manual_projected["image_prompt"], manual)
        self.assertEqual(manual_projected["image_prompt_options"], [manual])

    def test_manual_prompt_with_style_prefix_keeps_its_scene_facts_at_render_time(self):
        manual = (
            "Photorealistic editorial scene with workers holding signed closure notices "
            "outside the factory gate while management posts the closure order."
        )
        settings = Settings(cover_queue=[self._item(image_prompt="old")])
        with patch.object(bridge, "load_settings", return_value=settings), \
             patch.object(bridge, "_hydrate_cover_library", return_value=False), \
             patch.object(bridge, "_save_cover_state"), \
             patch.object(bridge, "snapshot", return_value={}):
            bridge.save_cover_manual_prompt({
                "productionItemId": "production:scene-brief",
                "prompt": manual,
            })

        row = settings.cover_queue[0]
        final = build_final_provider_prompt(row["image_prompt"], row)
        story = final.split("\n\nMAIN SUBJECT:", 1)[0].split("STORY CONTEXT:\n", 1)[1]
        self.assertIn("workers holding signed closure notices", story)
        self.assertIn("management posts the closure order", story)
        self.assertEqual(bridge._cover_recent_prompt_history({
            "recent_visual_prompt_history": [manual],
        }), [manual])

    def test_manual_prompt_stays_literal_but_render_time_builder_wraps_it_in_v2(self):
        manual = "A literal operator-written scene brief with the signed order on the desk."
        settings = Settings(cover_queue=[self._item(image_prompt="old")])
        with patch.object(bridge, "load_settings", return_value=settings), \
             patch.object(bridge, "_hydrate_cover_library", return_value=False), \
             patch.object(bridge, "_save_cover_state"), \
             patch.object(bridge, "snapshot", return_value={}):
            bridge.save_cover_manual_prompt({
                "productionItemId": "production:scene-brief",
                "prompt": manual,
            })

        row = settings.cover_queue[0]
        self.assertEqual(row["image_prompt"], manual)
        self.assertEqual(row["prompt_provider"], "manual")
        self.assertIn("NEWSFLOW FASTGEN UNIVERSAL THUMBNAIL CORE V2", build_final_provider_prompt(manual, row))


    def test_same_scene_with_presentation_padding_is_still_a_semantic_duplicate(self):
        old = "Workers hold closure notices at the factory gate while management posts the signed order."
        padded = (
            "Workers hold closure notices at the factory gate while management posts the signed order "
            "with dramatic documentary lighting, tense editorial contrast and realistic news imagery."
        )
        self.assertTrue(bridge._cover_semantic_duplicate(padded, old))

    def test_generic_cyberattack_or_economic_blow_does_not_authorize_military_destruction(self):
        cyber = {
            "title": "Company reports a cyberattack on its network",
            "script": "Engineers isolate affected servers while the company investigates unauthorized access.",
        }
        economic = {
            "title": "New tariffs deal a blow to exporters",
            "script": "Companies calculate higher costs and revise delivery plans.",
        }
        for item in (cyber, economic):
            with self.subTest(title=item["title"]):
                armed, _reason = bridge._cover_scene_is_grounded(
                    "Armed soldiers stand beside missile launchers while military vehicles move through the street.",
                    item,
                )
                destruction, _reason = bridge._cover_scene_is_grounded(
                    "A huge explosion sends smoke over destroyed buildings as rescuers search the rubble.",
                    item,
                )
                self.assertFalse(armed)
                self.assertFalse(destruction)

    def test_safety_block_with_default_two_variants_fails_closed_without_crashing_or_losing_old_prompt(self):
        old = "Workers hold closure notices at the factory gate while management posts the signed order."
        settings = Settings(cover_prompt_variant_count=2, cover_queue=[self._item(
            image_prompt=old,
            image_prompt_options=[old],
        )])

        async def blocked_provider(*_args: object, **_kwargs: object) -> str:
            raise RuntimeError("content filter blocked by provider")

        with patch.object(bridge, "load_settings", return_value=settings), \
             patch.object(bridge, "_hydrate_cover_library", return_value=False), \
             patch.object(bridge, "_save_cover_state"), \
             patch.object(bridge, "snapshot", return_value={}), \
             patch.object(bridge, "HybridTextPool", return_value=SimpleNamespace(generate=blocked_provider)):
            bridge.generate_cover_prompts({
                "indices": [0],
                "productionItemIds": ["production:scene-brief"],
                "provider": "agent",
                "rewrite": True,
            })

        row = settings.cover_queue[0]
        self.assertEqual(row["image_prompt"], old)
        self.assertEqual(row["image_prompt_options"], [old])
        self.assertIn("SEMANTIC_SCENE_DUPLICATE", row["error"])


if __name__ == "__main__":
    unittest.main()

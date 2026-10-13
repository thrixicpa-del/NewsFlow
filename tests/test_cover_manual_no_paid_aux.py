"""Manual Covers may render images, but must never buy auxiliary text AI."""
from __future__ import annotations

import base64
import hashlib
import json
import os
import unittest
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from scriptor import bridge
from scriptor.config import FastGenKey, OpenAIKey, Settings


class ManualCoverNoPaidAuxTests(unittest.TestCase):
    def setUp(self):
        temporary = self.enterContext(TemporaryDirectory(prefix="manual-no-paid-aux-"))
        self.root = Path(temporary)
        self.enterContext(patch.dict(os.environ, {
            "NEWSFLOW_TEST_MODE": "1", "NEWSFLOW_TEST_ROOT": temporary,
            "LOCALAPPDATA": temporary,
        }))
        self.enterContext(patch.object(bridge, "snapshot", return_value={}))
        self.enterContext(patch("urllib.request.urlopen", side_effect=AssertionError("network is forbidden")))
        self.enterContext(patch.object(
            bridge, "HybridTextPool", side_effect=AssertionError("manual prompt attempted paid text AI"),
        ))
        for name in ("generate_cover_prompts", "generate_cover_headlines", "generate_cover_subheadlines"):
            self.enterContext(patch.object(bridge, name, side_effect=AssertionError("hidden text generation")))
        self.identity = "production:manual-no-paid"
        self.title = "Парламент обсуждает санкции"
        self.prompt = "Депутаты изучают документ в зале парламента. Крупный план бумаги, без портрета политика. ✨"
        self.settings = Settings(
            cover_output_folder=str(self.root / "covers"), cover_auto_overlay_text=False,
            cover_variant_count=1, cover_build_mode="fastgen-full",
            cover_operation="nano_banana_2_image_generate",
            openai_api_keys=[],
            cover_api_keys=[FastGenKey(label="offline-image", secret="offline-image")],
            fastgen_capabilities_cache={"image": [
                {"id": "nano_banana_2_image_generate", "inputs": {"min": 0, "max": 10}},
            ]},
            idea_production_items=[
                {"id": "production:other", "title": "Other topic"},
                {"id": self.identity, "title": self.title},
            ],
            cover_queue=[
                {"production_item_id": "production:other", "title": "Other topic", "image_prompt": "Other scene"},
                {"production_item_id": self.identity, "title": self.title,
                 "cover_headline": "МОЙ ЗАГОЛОВОК", "headline_source": "MANUAL",
                 "cover_subheadline": "Моя вторая строка", "subheadline_source": "MANUAL"},
            ],
        )
        bridge._save_cover_state(self.settings)
        self.provider_calls = []
        self.enterContext(patch.object(bridge.FastGenPool, "generate_media", side_effect=self._offline_image))

    def _offline_image(self, prompt, output, stem, operation, ratio, **kwargs):
        self.provider_calls.append({"prompt": prompt, "operation": operation, "kwargs": kwargs})
        target = Path(output) / (hashlib.sha256(stem.encode()).hexdigest()[:12] + ".png")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aP1sAAAAASUVORK5CYII="
        ))
        return [target]

    def _row(self):
        settings = bridge.load_settings()
        bridge._hydrate_cover_library(settings)
        return next(row for row in settings.cover_queue if row.get("production_item_id") == self.identity)

    def _update(self, **fields):
        settings = bridge.load_settings()
        bridge._hydrate_cover_library(settings)
        row = next(row for row in settings.cover_queue if row.get("production_item_id") == self.identity)
        row.update(fields)
        bridge._advance_cover_revision(row)
        bridge._save_cover_state(settings)

    def _scope(self, **fields):
        settings = bridge.load_settings()
        bridge._hydrate_cover_library(settings)
        index = next(index for index, row in enumerate(settings.cover_queue)
                     if row.get("production_item_id") == self.identity)
        return {"indices": [index], "productionItemIds": [self.identity], "textMode": "fastgen", **fields}

    def _import(self):
        bridge.import_cover_prompt_pairs({"text": self.title + "\r\n" + self.prompt})

    def _assert_rendered(self, *, calls=1, literal=None):
        row = self._row()
        self.assertEqual(row["status"], "Готово")
        self.assertEqual(row["production_item_id"], self.identity)
        self.assertEqual(row["prompt_provider"].casefold(), "manual")
        self.assertEqual(row["image_prompt"], literal or self.prompt)
        self.assertEqual(row["image_prompt_options"], [literal or self.prompt])
        self.assertTrue(Path(row["path"]).is_file())
        self.assertEqual(len(self.provider_calls), calls)
        final = self.provider_calls[-1]["prompt"]
        self.assertIn("STORY CONTEXT:\n" + " ".join((literal or self.prompt).split()) + "\n\nMAIN SUBJECT:", final)
        self.assertIn("NEWSFLOW FASTGEN UNIVERSAL THUMBNAIL CORE V2", final)
        self.assertIn("<exact-text>МОЙ ЗАГОЛОВОК</exact-text>", final)
        self.assertIn("<exact-text>Моя вторая строка</exact-text>", final)
        self.assertEqual(self.provider_calls[-1]["operation"], "nano_banana_2_image_generate")

    def test_imported_ambiguous_political_prompt_renders_without_text_ai(self):
        settings = bridge.load_settings()
        settings.openai_api_keys.append(OpenAIKey(label="offline-text", secret="offline-text"))
        bridge._save_cover_state(settings)
        self._import()
        bridge.generate_covers(self._scope(buildMode="fastgen-full", faceMode="auto"))
        self._assert_rendered()

    def test_manual_editor_renders_without_openai_key_and_preserves_literal_text(self):
        literal = "  Моя сцена:\nДепутаты держат документ. ✨  "
        bridge.save_cover_manual_prompt({"productionItemId": self.identity, "prompt": literal})
        self.assertEqual(bridge.load_settings().openai_api_keys, [])
        bridge.generate_covers(self._scope(buildMode="fastgen-full", faceMode="auto"))
        self._assert_rendered(literal=literal)

    def test_nonpolitical_face_required_does_not_buy_an_automatic_person(self):
        self._import()
        self._update(title="Городской музыкальный фестиваль", cover_face_required=True)
        bridge.generate_covers(self._scope(buildMode="fastgen-full", faceMode="with"))
        self._assert_rendered()

    def test_direct_manual_person_resolver_is_fail_closed_without_provider_side_effects(self):
        for marker in ("manual", "MANUAL"):
            with self.subTest(marker=marker):
                row = {"production_item_id": self.identity, "title": self.title, "prompt_provider": marker}
                before = deepcopy(row)
                settings = Settings(openai_api_keys=[OpenAIKey(label="offline-text", secret="offline-text")])
                self.assertFalse(bridge._resolve_missing_cover_primary_person(row, settings))
                self.assertEqual(row, before)

    def test_persisted_manual_marker_and_reordered_queue_keep_durable_routing(self):
        self._import()
        self._update(prompt_provider="MANUAL")
        settings = bridge.load_settings()
        settings.cover_queue.reverse()
        bridge._save_cover_state(settings)
        bridge.generate_covers(self._scope(buildMode="fastgen-full", faceMode="auto"))
        self._assert_rendered()
        other = next(row for row in bridge.load_settings().cover_queue
                     if row.get("production_item_id") == "production:other")
        self.assertEqual(other["image_prompt"], "Other scene")

    def test_resume_manual_prompt_never_runs_auxiliary_ai(self):
        self._import()
        self._update(status="Приостановлено")
        settings = bridge.load_settings()
        settings.cover_generation_paused = True
        bridge._save_cover_state(settings)
        bridge.generate_covers({"resumeOnly": True, "resumeGeneration": True,
                                "buildMode": "fastgen-full", "faceMode": "auto", "textMode": "fastgen"})
        self._assert_rendered()

    def test_exact_manual_retry_reuses_provider_contract_without_person_ai(self):
        self._import()
        saved = "MY EXACT SAVED PROVIDER PROMPT — do not rewrite"
        self._update(
            status="Ошибка FastGen", final_provider_prompt=saved,
            final_provider_prompt_options=[saved], final_provider_reference_paths=[],
            portrait_subject="", portrait_source="none",
            render_profile={"build_mode": "fastgen-full", "face_mode": "auto", "text_mode": "fastgen",
                            "local_face_only": False, "operation": "nano_banana_2_image_generate"},
        )
        bridge.retry_cover_generation(self._scope())
        row = self._row()
        self.assertEqual(row["status"], "Готово")
        self.assertEqual(row["image_prompt"], self.prompt)
        self.assertEqual(len(self.provider_calls), 1)
        self.assertEqual(self.provider_calls[0]["prompt"], saved)

    def test_manual_portrait_reference_is_preserved_and_transported_without_ai(self):
        self._import()
        face = self.root / "chosen-face.png"
        face.write_bytes(base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aP1sAAAAASUVORK5CYII="
        ))
        self._update(face_reference_source="manual", face_reference_label="Manual Person",
                     face_reference_path=str(face))
        bridge.generate_covers(self._scope(buildMode="fastgen-full-my-face", faceMode="with"))
        self._assert_rendered()
        row = self._row()
        self.assertEqual(row["face_reference_label"], "Manual Person")
        self.assertEqual(row["face_reference_path"], str(face))
        self.assertEqual(row["portrait_subject"], "Manual Person")
        self.assertIn(str(face), self.provider_calls[0]["kwargs"]["references"])

    def test_mixed_batch_keeps_automatic_semantic_resolver_for_only_the_ai_row(self):
        self._import()
        settings = bridge.load_settings()
        settings.openai_api_keys.append(OpenAIKey(label="offline-text", secret="offline-text"))
        settings.cover_queue[0].update(title="Парламент обсуждает ограничения", prompt_provider="agent",
                                      image_prompt="Зал парламента с документами", image_prompt_options=[])
        settings.idea_production_items[0]["title"] = "Парламент обсуждает ограничения"
        bridge._save_cover_state(settings)
        text_requests = []

        class AutomaticTextPool:
            async def generate(_self, prompt, **_kwargs):
                if "Депутаты изучают документ" in prompt or "Парламент обсуждает санкции" in prompt:
                    raise AssertionError("manual row reached a paid provider in mixed batch")
                text_requests.append(prompt)
                return json.dumps({"cover_primary_person": {
                    "name": "Президент Тестов", "entity_type": "public_figure",
                    "role_in_story": "президент", "relation_to_story": "возглавляет сторону обсуждения",
                    "confidence": 0.6,
                }}, ensure_ascii=False)

        with patch.object(bridge, "HybridTextPool", return_value=AutomaticTextPool()):
            bridge.generate_covers({"indices": [0, 1],
                                    "productionItemIds": ["production:other", self.identity],
                                    "buildMode": "fastgen-full", "faceMode": "auto", "textMode": "fastgen"})
        self.assertEqual(len(text_requests), 1)
        self.assertEqual(len(self.provider_calls), 2)
        self.assertEqual(self._row()["status"], "Готово")
        automatic = next(row for row in bridge.load_settings().cover_queue
                         if row.get("production_item_id") == "production:other")
        self.assertEqual(automatic["cover_primary_person"]["name"], "Президент Тестов")
        self.assertEqual(automatic["status"], "Готово")


if __name__ == "__main__":
    unittest.main()

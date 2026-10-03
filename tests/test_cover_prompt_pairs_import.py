from __future__ import annotations

import unittest
from unittest.mock import patch

from scriptor import bridge
from scriptor.config import Settings


class CoverPromptPairsImportTests(unittest.TestCase):
    def _import(self, settings: Settings, text: str):
        with patch.object(bridge, "load_settings", return_value=settings), \
             patch.object(bridge, "_hydrate_cover_library"), \
             patch.object(bridge, "_save_cover_state") as save, \
             patch.object(bridge, "snapshot", return_value={}):
            result = bridge.import_cover_prompt_pairs({"text": text})
        return result, save

    def test_import_resolves_exact_normalized_title_to_durable_production_item_id(self):
        settings = Settings(cover_queue=[
            {"production_item_id": "production:second", "title": "Вторая тема", "image_prompt": "OLD-2"},
            {
                "production_item_id": "production:first", "title": "Первая   тема",
                "image_prompt": "OLD-1", "cover_headline": "РУЧНОЙ ЗАГОЛОВОК",
                "face_reference_source": "manual", "face_reference_label": "Manual Person",
                "final_provider_prompt": "obsolete contract", "paths": ["old.png"],
            },
        ])

        result, save = self._import(
            settings,
            "\ufeffПервая тема\r\nManual prompt ✨ — preserve exact scene\r\n\r\nВторая тема\r\nSecond manual prompt",
        )

        first, second = settings.cover_queue[1], settings.cover_queue[0]
        self.assertEqual(result["operationResult"]["productionItemIds"], ["production:first", "production:second"])
        self.assertEqual(first["image_prompt"], "Manual prompt ✨ — preserve exact scene")
        self.assertEqual(first["image_prompt_options"], ["Manual prompt ✨ — preserve exact scene"])
        self.assertEqual(first["prompt_provider"], "manual")
        self.assertEqual(first["cover_headline"], "РУЧНОЙ ЗАГОЛОВОК")
        self.assertEqual(first["face_reference_label"], "Manual Person")
        self.assertNotIn("final_provider_prompt", first)
        self.assertEqual(first["paths"], [])
        self.assertEqual(second["image_prompt"], "Second manual prompt")
        save.assert_called_once_with(settings)

    def test_import_is_atomic_for_unknown_or_ambiguous_titles_and_never_calls_a_provider(self):
        settings = Settings(cover_queue=[
            {"production_item_id": "production:a", "title": "Тема А", "image_prompt": "Старый А"},
            {"production_item_id": "production:b", "title": "Тема Б", "image_prompt": "Старый Б"},
        ])
        source = "Тема А\nНовый А\nНеизвестная\nНовый X"

        with patch.object(bridge, "load_settings", return_value=settings), \
             patch.object(bridge, "_hydrate_cover_library"), \
             patch.object(bridge, "_save_cover_state") as save, \
             patch.object(bridge, "HybridTextPool", side_effect=AssertionError("manual import must not call provider")), \
             self.assertRaisesRegex(ValueError, "UNKNOWN_TOPIC"):
            bridge.import_cover_prompt_pairs({"text": source})
        self.assertEqual([row["image_prompt"] for row in settings.cover_queue], ["Старый А", "Старый Б"])
        save.assert_not_called()

        ambiguous = Settings(cover_queue=[
            {"production_item_id": "production:one", "title": "Одна тема", "image_prompt": "Первый"},
            {"production_item_id": "production:two", "title": "Одна   тема", "image_prompt": "Второй"},
        ])
        with patch.object(bridge, "load_settings", return_value=ambiguous), \
             patch.object(bridge, "_hydrate_cover_library"), \
             patch.object(bridge, "_save_cover_state") as save, \
             self.assertRaisesRegex(ValueError, "AMBIGUOUS_TOPIC"):
            bridge.import_cover_prompt_pairs({"text": "Одна тема\nНовый prompt"})
        self.assertEqual([row["image_prompt"] for row in ambiguous.cover_queue], ["Первый", "Второй"])
        save.assert_not_called()

    def test_import_rejects_conflicting_duplicate_but_deduplicates_an_identical_pair(self):
        settings = Settings(cover_queue=[{"production_item_id": "production:a", "title": "Тема А"}])
        with patch.object(bridge, "load_settings", return_value=settings), \
             patch.object(bridge, "_hydrate_cover_library"), \
             patch.object(bridge, "_save_cover_state") as save, \
             self.assertRaisesRegex(ValueError, "CONFLICTING_DUPLICATE"):
            bridge.import_cover_prompt_pairs({"text": "Тема А\nПервый\nТема А\nДругой"})
        save.assert_not_called()

        result, save = self._import(settings, "Тема А\nПервый\n\nТема А\nПервый")
        self.assertEqual(result["operationResult"]["count"], 1)
        self.assertEqual(settings.cover_queue[0]["image_prompt"], "Первый")
        save.assert_called_once_with(settings)

    def test_manual_edit_targets_only_the_requested_durable_id_after_queue_reorder(self):
        settings = Settings(cover_queue=[
            {"production_item_id": "production:later", "title": "Позже", "image_prompt": "old later"},
            {"production_item_id": "production:chosen", "title": "Выбрана", "image_prompt": "old chosen"},
        ])
        with patch.object(bridge, "load_settings", return_value=settings), \
             patch.object(bridge, "_hydrate_cover_library"), \
             patch.object(bridge, "_save_cover_state") as save, \
             patch.object(bridge, "snapshot", return_value={}):
            result = bridge.save_cover_manual_prompt({
                "productionItemId": "production:chosen", "prompt": "edited manually",
            })

        self.assertEqual(result["operationResult"]["productionItemIds"], ["production:chosen"])
        self.assertEqual(settings.cover_queue[0]["image_prompt"], "old later")
        self.assertEqual(settings.cover_queue[1]["image_prompt"], "edited manually")
        save.assert_called_once_with(settings)


if __name__ == "__main__":
    unittest.main()

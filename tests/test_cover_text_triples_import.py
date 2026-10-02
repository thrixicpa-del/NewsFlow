from __future__ import annotations

import unittest
from unittest.mock import patch

from scriptor import bridge
from scriptor.config import Settings


class CoverTextTriplesImportTests(unittest.TestCase):
    def _settings(self, rows: list[dict]) -> Settings:
        return Settings(cover_queue=rows)

    def _import(self, settings: Settings, text: str):
        with patch.object(bridge, "load_settings", return_value=settings), \
             patch.object(bridge, "_hydrate_cover_library"), \
             patch.object(bridge, "_save_cover_state") as save, \
             patch.object(bridge, "snapshot", return_value={}):
            result = bridge.import_cover_text_triples({"text": text})
        return result, save

    def test_import_matches_normalized_title_then_updates_the_durable_production_item(self):
        settings = self._settings([
            {"production_item_id": "production:second", "title": "Вторая тема", "cover_headline": "OLD-2"},
            {"production_item_id": "production:first", "title": "Первая   тема", "cover_headline": "OLD-1"},
        ])

        result, save = self._import(settings, "\ufeffПервая тема\r\nМОЙ headline ✨\r\nМой subheadline — дословно\r\n\r\nВторая тема\r\nВТОРОЙ\r\nВторая строка")

        self.assertEqual(result["operationResult"]["count"], 2)
        first, second = settings.cover_queue[1], settings.cover_queue[0]
        self.assertEqual(first["production_item_id"], "production:first")
        self.assertEqual(first["cover_headline"], "МОЙ headline ✨")
        self.assertEqual(first["cover_subheadline"], "Мой subheadline — дословно")
        self.assertEqual(first["headline_source"], "MANUAL")
        self.assertEqual(first["headline_status"], "MANUAL")
        self.assertEqual(first["subheadline_source"], "MANUAL")
        self.assertEqual(first["subheadline_status"], "MANUAL")
        self.assertEqual(second["cover_headline"], "ВТОРОЙ")
        self.assertEqual(
            result["operationResult"]["productionItemIds"],
            ["production:first", "production:second"],
        )
        save.assert_called_once_with(settings)

    def test_import_rejects_unknown_topic_without_partially_changing_another_row(self):
        settings = self._settings([
            {"production_item_id": "production:a", "title": "Тема А", "cover_headline": "Старый А"},
            {"production_item_id": "production:b", "title": "Тема Б", "cover_headline": "Старый Б"},
        ])
        source = "Тема А\nНовый А\nСтрока А\nНеизвестная\nНовый X\nСтрока X"

        with patch.object(bridge, "load_settings", return_value=settings), \
             patch.object(bridge, "_hydrate_cover_library"), \
             patch.object(bridge, "_save_cover_state") as save, \
             self.assertRaisesRegex(ValueError, "UNKNOWN_TOPIC"):
            bridge.import_cover_text_triples({"text": source})
        self.assertEqual([row["cover_headline"] for row in settings.cover_queue], ["Старый А", "Старый Б"])
        save.assert_not_called()

    def test_import_rejects_ambiguous_same_title_without_first_match_wins(self):
        settings = self._settings([
            {"production_item_id": "production:one", "title": "Одна тема", "cover_headline": "Первый"},
            {"production_item_id": "production:two", "title": "Одна   тема", "cover_headline": "Второй"},
        ])

        with patch.object(bridge, "load_settings", return_value=settings), \
             patch.object(bridge, "_hydrate_cover_library"), \
             patch.object(bridge, "_save_cover_state") as save, \
             self.assertRaisesRegex(ValueError, "AMBIGUOUS_TOPIC"):
            bridge.import_cover_text_triples({"text": "Одна тема\nНовый\nДеталь"})
        self.assertEqual([row["cover_headline"] for row in settings.cover_queue], ["Первый", "Второй"])
        save.assert_not_called()

    def test_import_rejects_conflicting_duplicate_and_deduplicates_an_identical_triple(self):
        settings = self._settings([{"production_item_id": "production:a", "title": "Тема А"}])
        conflicting = "Тема А\nПервый\nДеталь\nТема А\nДругой\nДеталь"
        with patch.object(bridge, "load_settings", return_value=settings), \
             patch.object(bridge, "_hydrate_cover_library"), \
             patch.object(bridge, "_save_cover_state") as save, \
             self.assertRaisesRegex(ValueError, "CONFLICTING_DUPLICATE"):
            bridge.import_cover_text_triples({"text": conflicting})
        save.assert_not_called()

        result, save = self._import(settings, "Тема А\nПервый\nДеталь\n\nТема А\nПервый\nДеталь")
        self.assertEqual(result["operationResult"]["count"], 1)
        self.assertEqual(settings.cover_queue[0]["cover_headline"], "Первый")
        save.assert_called_once_with(settings)

    def test_import_requires_complete_triples_and_real_production_ids(self):
        settings = self._settings([{"title": "Тема без ID", "cover_headline": "Старый"}])
        with patch.object(bridge, "load_settings", return_value=settings), \
             patch.object(bridge, "_hydrate_cover_library"), \
             patch.object(bridge, "_save_cover_state") as save:
            with self.assertRaisesRegex(ValueError, "MISSING_PRODUCTION_ITEM_ID"):
                bridge.import_cover_text_triples({"text": "Тема без ID\nНовый\nДеталь"})
            with self.assertRaisesRegex(ValueError, "INVALID_TRIPLES"):
                bridge.import_cover_text_triples({"text": "Тема без ID\nНовый"})
        self.assertEqual(settings.cover_queue[0]["cover_headline"], "Старый")
        save.assert_not_called()

    def test_import_does_not_call_ai_or_editorial_validation_for_manual_text(self):
        settings = self._settings([{"production_item_id": "production:manual", "title": "Тема А"}])
        with patch.object(bridge, "load_settings", return_value=settings), \
             patch.object(bridge, "_hydrate_cover_library"), \
             patch.object(bridge, "_save_cover_state"), \
             patch.object(bridge, "snapshot", return_value={}), \
             patch.object(bridge, "_validate_cover_word", side_effect=AssertionError("manual text must bypass editor")), \
             patch.object(bridge, "HybridTextPool", side_effect=AssertionError("manual import must not call provider")):
            bridge.import_cover_text_triples({"text": "Тема А\n  ВЕСЬ ИМПОРТ?  \n  Ручной текст без сокращения  "})
        self.assertEqual(settings.cover_queue[0]["cover_headline"], "  ВЕСЬ ИМПОРТ?  ")
        self.assertEqual(settings.cover_queue[0]["cover_subheadline"], "  Ручной текст без сокращения  ")


if __name__ == "__main__":
    unittest.main()

import unittest
from unittest.mock import patch

from scriptor import bridge
from scriptor.config import OpenAIKey, Settings


class IdeasYoutubeFastModeRegressionTests(unittest.TestCase):
    def _research(self, settings, payload):
        suggested = [
            "Иран — Ормузский пролив и риски судоходства",
            "Нефтяной рынок и движение танкеров через Ормуз",
        ]
        research = [{
            "title": "Иран усилил контроль над судоходством в Ормузском проливе",
            "url": "https://youtube.test/watch?v=hormuz",
            "channel": "Тестовый канал",
            "views": 120000,
            "likes": 3000,
            "comments": 400,
            "score": 9000,
        }]
        news = [{
            "title": "Суда меняют маршруты через Ормузский пролив",
            "url": "https://news.test/hormuz",
            "source": "Тестовое издание",
            "published": "18 September 2026",
        }]

        class FakePool:
            async def generate(self, _prompt):
                return "\n".join(suggested)

        with patch.object(bridge, "save_settings"), \
             patch.object(bridge, "snapshot", return_value={}), \
             patch.object(bridge, "_youtube_research", return_value=research), \
             patch.object(bridge, "_news_research", return_value=news), \
             patch.object(bridge, "ingest_idea_signals", return_value=[]), \
             patch.object(bridge, "HybridTextPool", return_value=FakePool()), \
             patch.object(bridge, "generate_ideas", return_value={"ideaResults": []}) as generate:
            bridge.research_youtube_topics(payload)

        self.assertEqual(settings.youtube_suggested_topics, suggested)
        return generate, suggested

    def test_query_only_fast_mode_generates_researched_suggested_directions(self):
        settings = Settings(openai_api_keys=[OpenAIKey(label="Test", secret="test-key", active=True)])
        payload = {
            "query": "Иран Ормуз нефть",
            "topics": [],
            "count": 2,
            "generateTogether": True,
            "vectors": 3,
            "provider": "agent",
            "requirements": "",
        }

        with patch.object(bridge, "load_settings", return_value=settings):
            generate, suggested = self._research(settings, payload)

        self.assertEqual(generate.call_args.args[0]["topics"], suggested)

    def test_selected_and_researched_fast_mode_deduplicates_without_persisting_suggestions(self):
        selected = "Иран — Ормузский пролив и риски судоходства"
        settings = Settings(
            idea_topics=[selected],
            openai_api_keys=[OpenAIKey(label="Test", secret="test-key", active=True)],
        )
        payload = {
            "query": "Иран Ормуз нефть",
            "topics": [selected],
            "count": 2,
            "generateTogether": True,
            "vectors": 3,
            "provider": "agent",
            "requirements": "",
        }

        with patch.object(bridge, "load_settings", return_value=settings):
            generate, suggested = self._research(settings, payload)

        self.assertEqual(generate.call_args.args[0]["topics"], [selected, suggested[1]])
        self.assertEqual(settings.idea_topics, [selected])


if __name__ == "__main__":
    unittest.main()

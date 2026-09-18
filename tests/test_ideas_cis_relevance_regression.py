import unittest
from unittest.mock import patch

from scriptor import bridge, idea_engine
from scriptor.config import OpenAIKey, Settings


class IdeasCisRelevanceRegressionTests(unittest.TestCase):
    def test_default_hormuz_direction_is_not_rejected_as_low_cis_relevance(self):
        event = {
            "event_id": "evt_hormuz_shipping",
            "event_core": "Суда меняют маршруты через Ормузский пролив",
            "primary_entities": ["Иран"],
            "action": "меняют маршруты",
            "object": "судоходство через Ормузский пролив",
            "source_signal_ids": ["sig_1"],
            "demand_inputs": {"views_hour": 5000, "views": 100000},
        }
        seed = {
            "direction": "Иран — Ормузский пролив",
            "topic": "Суда меняют маршруты через Ормузский пролив",
            "angle": "судоходство и риски маршрутов",
            "framing_type": "EDITORIAL",
        }
        title = "Иран меняет правила игры: суда уходят с привычных маршрутов в Ормузском проливе"

        audience = idea_engine.assess_cis_audience(seed, [event])
        item = idea_engine.build_production_item(seed, title, [event])

        self.assertGreaterEqual(audience["cis_audience_relevance_score"], 50)
        self.assertIsNotNone(item)

    def test_selected_hormuz_china_and_custom_directions_reach_fake_provider(self):
        directions = [
            "Иран — Ормузский пролив",
            "Китай — рынок электромобилей",
            "Произвольная пользовательская тема",
        ]
        titles = {
            directions[0]: "Иран меняет маршруты в Ормузе: что происходит с судоходством",
            directions[1]: "Китайский рынок электромобилей меняется: что важно покупателям",
            directions[2]: "Пользовательская тема меняет правила: что важно проверить",
        }
        settings = Settings(openai_api_keys=[OpenAIKey(label="Test", secret="test-key", active=True)])
        prompts = []

        class FakePool:
            async def generate(self, prompt):
                prompts.append(prompt)
                direction = next(value for value in directions if f"Направление: {value}." in prompt)
                return titles[direction]

        with patch.object(bridge, "load_settings", return_value=settings), \
             patch.object(bridge, "save_settings"), \
             patch.object(bridge, "snapshot", return_value={}), \
             patch.object(bridge, "HybridTextPool", return_value=FakePool()):
            bridge.generate_ideas({"topics": directions, "count": 1, "provider": "openai"})

        self.assertEqual(len(prompts), len(directions))
        self.assertEqual({next(value for value in directions if f"Направление: {value}." in prompt)
                          for prompt in prompts}, set(directions))
        self.assertEqual(set(settings.idea_suggested_topics), set(titles.values()))
        self.assertEqual({settings.idea_title_metadata[title]["topic"] for title in titles.values()}, set(directions))

    def test_evidence_backed_custom_topic_survives_provider_to_production_and_scenario_handoff(self):
        direction = "Китай — рынок электромобилей"
        prior_title = "Китайский рынок электромобилей: какие перемены ждут покупателей"
        generated_title = "Китайский рынок электромобилей меняется: что важно покупателям"
        settings = Settings(
            openai_api_keys=[OpenAIKey(label="Test", secret="test-key", active=True)],
            idea_plan=[{"topic": direction, "count": 1, "provider": "openai"}],
            idea_results=[prior_title],
            idea_result_sources={prior_title: direction},
            idea_events=[{
                "event_id": "evt_china_ev",
                "event_core": "Китайский рынок электромобилей меняет правила продаж",
                "primary_entities": ["Китай"],
                "action": "меняет правила", "object": "рынок электромобилей",
                "source_signal_ids": ["sig_china_ev"],
                "demand_inputs": {"views_hour": 5000, "views": 100000},
            }],
        )
        prompts = []

        class FakePool:
            async def generate(self, prompt):
                prompts.append(prompt)
                return generated_title

        with patch.object(bridge, "load_settings", return_value=settings), \
             patch.object(bridge, "save_settings"), \
             patch.object(bridge, "snapshot", return_value={}), \
             patch.object(bridge, "load_session", return_value=([], [])), \
             patch.object(bridge, "save_session") as save_session, \
             patch.object(bridge, "HybridTextPool", return_value=FakePool()):
            bridge.regenerate_idea_results({"ideas": [prior_title]})
            bridge.add_ideas_to_scenarios({"ideas": [generated_title]})

        self.assertEqual(len(prompts), 1)
        self.assertIn(f"Направление: {direction}.", prompts[0])
        self.assertEqual(settings.idea_results, [generated_title])
        self.assertEqual([item["title"] for item in settings.idea_production_items], [generated_title])
        self.assertNotIn("low CIS relevance", [item["reason"] for item in settings.idea_rejected_items])
        self.assertIn(generated_title, settings.idea_scenario_context)
        self.assertIn(generated_title, save_session.call_args.args[0])


if __name__ == "__main__":
    unittest.main()

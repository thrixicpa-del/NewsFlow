import unittest

from scriptor import idea_engine


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


if __name__ == "__main__":
    unittest.main()

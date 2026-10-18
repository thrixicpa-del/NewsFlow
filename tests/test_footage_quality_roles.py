"""Window roles for institutional context versus an actual speaking scene."""
import unittest

from scriptor import bridge
from scriptor.footage import FootageItem
from scriptor.scene_intent import visual_intent
from scriptor.timeline import VISUAL_TERMS
from scriptor.visual_evidence import classify_window

CONTEXT_QUERY = "Moscow Russia government city, government building exterior illustrative context"


class InstitutionalWindowRoleTests(unittest.TestCase):
    def test_single_official_portrait_is_not_institutional_context(self):
        assessment = classify_window(CONTEXT_QUERY, [{
            "official": .35, "meeting": .25, "government_building": .17,
        }] * 3)
        self.assertNotIn(assessment["relation"], {"direct", "context"})
        self.assertFalse(assessment["event_confirmed"])

    def test_stale_accepted_portrait_cannot_bypass_requested_building_role(self):
        item = FootageItem("mixed.mp4", "Moscow Putin Pashinyan meeting", tags=["press-conference"])
        accepted_portrait = {
            "relation": "direct", "dominant_kind": "official",
            "supported_kinds": ["official", "meeting"], "source": "automatic-window-clip",
            "event_confirmed": False, "motion_verified": False,
        }
        self.assertFalse(bridge._semantic_clip_ok(
            CONTEXT_QUERY, item, source_start=0, visual_assessment=accepted_portrait))

    def test_metadata_only_portrait_cannot_prove_an_institutional_window(self):
        item = FootageItem("mixed.mp4", "Moscow Putin Pashinyan", tags=["press-conference"])
        self.assertFalse(bridge._semantic_clip_ok(CONTEXT_QUERY, item, source_start=0))

    def test_building_and_delegation_windows_remain_valid_context(self):
        item = FootageItem("institution.mp4", "Moscow Russia venue", tags=["diplomatic-negotiations"])
        for kind in ("government_building", "meeting"):
            with self.subTest(kind=kind):
                scores = {"official": .20, "meeting": .20, "government_building": .20, kind: .35}
                assessment = classify_window(CONTEXT_QUERY, [scores] * 3)
                self.assertIn(assessment["relation"], {"direct", "context"})
                self.assertTrue(bridge._semantic_clip_ok(
                    CONTEXT_QUERY, item, source_start=0, visual_assessment=assessment))

    def test_actual_speaking_query_keeps_an_official_window(self):
        query = "official statement government briefing"
        item = FootageItem("speaker.mp4", "official statement", tags=["press-conference"])
        assessment = classify_window(query, [{
            "official": .35, "meeting": .20, "government_building": .17,
        }] * 3)
        self.assertEqual("direct", assessment["relation"])
        self.assertTrue(bridge._semantic_clip_ok(query, item, source_start=0, visual_assessment=assessment))

    def test_export_warehouse_action_outranks_ancillary_agricultural_noun(self):
        query = visual_intent("Аграрные товары направляются на экспорт.", VISUAL_TERMS)["visual_query"]
        warehouse = classify_window(query, [{"warehouse": .35, "farm": .20, "official": .16}] * 3)
        farm = classify_window(query, [{"warehouse": .20, "farm": .35, "official": .16}] * 3)
        self.assertEqual("direct", warehouse["relation"])
        self.assertNotIn(farm["relation"], {"direct", "context"})

    def test_actual_harvesting_still_requests_farm_direct_with_warehouse_context(self):
        query = "harvest farming combine wheat field agricultural storage warehouse"
        farm = classify_window(query, [{"warehouse": .20, "farm": .35,
                                       "grain_field": .35, "non_grain_agriculture": .18}] * 3)
        warehouse = classify_window(query, [{"warehouse": .35, "farm": .20}] * 3)
        self.assertEqual("direct", farm["relation"])
        self.assertEqual("context", warehouse["relation"])

    def test_explicit_physical_role_outranks_a_cargo_warehouse_destination(self):
        for query, kind in (
            (visual_intent("Поезд везёт зерно на склад.", VISUAL_TERMS)["visual_query"], "rail"),
            (visual_intent("Грузовики доставляют зерно на склад.", VISUAL_TERMS)["visual_query"], "road_cargo"),
            ("energy refinery warehouse cargo agricultural products", "energy"),
            ("industrial factory manufacturing warehouse agricultural cargo", "factory"),
            ("actual frontline combat warehouse cargo agricultural storage", "combat"),
            ("official statement government briefing agricultural cargo warehouse", "official"),
        ):
            with self.subTest(role=kind):
                assessment = classify_window(query, [{kind:.35,"warehouse":.20,"farm":.16}] * 3)
                self.assertEqual("direct", assessment["relation"])
                self.assertEqual(kind, assessment["topic"])

    def test_explicit_naval_role_keeps_naval_window_without_relabeling_it_as_cargo(self):
        scores = [{"military_naval":.36,"port":.20,"combat":.18}] * 3
        naval = classify_window("military naval warship patrol vessel navy", scores)
        commercial = classify_window("commercial cargo ship maritime navigation", scores)
        self.assertEqual("direct", naval["relation"])
        self.assertNotIn(commercial["relation"], {"direct", "context"})
        self.assertFalse(naval["event_confirmed"])


if __name__ == "__main__":
    unittest.main()

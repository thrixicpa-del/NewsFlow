"""Close semantic negatives; disposable embeddings, never real media."""
import tempfile
import unittest
from pathlib import Path

import numpy as np

from scriptor.ai_index import ClipIndex
from scriptor.visual_evidence import TAXONOMY, classify_window

DESCRIPTIONS = {
    "equipment_display": (
        "agricultural manure spreader trailer with large rear spreading beaters inside a machinery exhibition hall",
        "stationary farm trailers and fertilizer spreading machinery displayed at an indoor agricultural trade show",
    ),
    "vessel_incident": (
        "damaged cargo ship listing heavily to one side sinking in the sea",
        "shipwreck cargo vessel capsized and partially submerged in water",
    ),
    "institution_ukraine": (
        "government building exterior flying a blue and yellow Ukrainian national flag",
        "Ukrainian government institution with the blue yellow national flag on the roof",
    ),
    "institution_russia": (
        "government building exterior flying a white blue red Russian national flag",
        "Russian government institution with the white blue red national flag on the roof",
    ),
}


class ContextVisualSemanticsTests(unittest.TestCase):
    def test_location_only_query_accepts_checked_city_context_without_claiming_geography(self):
        for query in ("Azerbaijan Baku", "Азербайджан Баку", "Armenia Yerevan"):
            with self.subTest(query=query):
                result = classify_window(query, [{"city": .35, "official": .1}] * 3)
                self.assertEqual(result["relation"], "context")
                self.assertEqual(result["supported_kinds"], ["city"])
                self.assertFalse(result["event_confirmed"])
                self.assertFalse(result["motion_verified"])

    def test_border_query_requires_checked_checkpoint_instead_of_generic_crowd_or_combat(self):
        for query in ("border checkpoint guards fence", "пограничный пункт пропуска"):
            with self.subTest(query=query):
                good = classify_window(query, [{"border_checkpoint": .35, "city": .12, "combat": .1}] * 3)
                self.assertEqual(good["relation"], "direct")
                for negative in ("city", "official", "combat", "peaceful_protest", "queue"):
                    bad = classify_window(query, [{"border_checkpoint": .15, negative: .36}] * 3)
                    self.assertEqual(bad["relation"], "contradiction")

    def test_location_context_keeps_close_negative_and_action_priority(self):
        from scriptor.visual_evidence import query_topic
        for negative in ("official", "combat", "interview", "leisure", "peaceful_protest"):
            result = classify_window("Azerbaijan Baku", [{"city": .12, negative: .36}] * 3)
            self.assertEqual(result["relation"], "contradiction")
        for query, topic in (("Baku peaceful protest", "protest"),
                             ("Baku formal statement", "official"),
                             ("border checkpoint military soldiers", "combat"),
                             ("Baku freight train", "rail")):
            self.assertEqual(query_topic(query)[0], topic)
        for query in ("unrecognised subject", "Azerbaijan hostage execution", "not a border checkpoint",
                      "not city streets", "without urban footage", "не городские улицы"):
            self.assertIsNone(query_topic(query))

    def test_real_index_assessment_and_bridge_keep_supported_and_wrong_role_windows_separate(self):
        from scriptor import bridge
        from scriptor.footage import FootageItem
        for query, kind, name in (("Azerbaijan Baku", "city", "Baku streets"),
                                  ("border checkpoint guards fence", "border_checkpoint", "Border checkpoint")):
            with self.subTest(query=query):
                accepted = self.assess(query, {kind: .35, "official": .1})
                rejected = self.assess(query, {kind: .12, "official": .36})
                item = FootageItem("test-owned-fixture", name)
                item._visual_assessor = lambda *_, result=accepted, **__: result
                self.assertTrue(bridge._semantic_clip_ok(query, item, source_start=0, duration=6))
                item._visual_assessor = lambda *_, result=rejected, **__: result
                self.assertFalse(bridge._semantic_clip_ok(query, item, source_start=0, duration=6))
                if kind == "city":
                    self.assertFalse(bridge._semantic_clip_ok("Armenia Yerevan", item,
                        source_start=0, duration=6, visual_assessment=accepted))

    def test_grain_commodity_fallback_keeps_direct_rail_and_close_negative_priority(self):
        from scriptor import bridge
        from scriptor.ai_index import SearchHit
        from scriptor.footage import FootageItem
        query = "rail freight train grain transport cargo logistics"
        grain = {"farm": .35, "grain_field": .35, "non_grain_agriculture": .20}
        candidates = []
        for name, score, values in (
                ("bare-soil", .99, {**grain, "non_grain_agriculture": .345}),
                ("grain-context", .90, grain),
                ("rail", .24, {"rail": .35, "farm": .10})):
            item = FootageItem(f"D:/test-owned/{name}.mp4", name)
            visual = classify_window(query, [values] * 3)
            item._visual_assessor = lambda *_, result=visual, **__: result
            candidates.append(SearchHit(item, score, 30))

        def select(hits):
            return bridge._select_montage_candidate(
                query, strict_hits=hits, fallback_hits=[], required_duration=6,
                match_threshold=.22, used_paths=set(), used_families=set(),
                project_used_paths=set(), project_used_families=set(),
                reserved_paths=set(), reserved_families=set(),
                source_exists=lambda _: True, source_duration=lambda _: 30)

        self.assertEqual(candidates[2].item.path, select(candidates).item.path)
        fallback = select(candidates[:2])
        self.assertEqual(candidates[1].item.path, fallback.item.path)
        self.assertEqual("context", fallback.diagnostics["visual"]["relation"])
        self.assertEqual("grain_field", fallback.diagnostics["visual"]["context_facet"]["kind"])

    def assess(self, query, values):
        kinds = list(dict.fromkeys([*TAXONOMY, *DESCRIPTIONS]))

        class Text:
            def query_embed(self, texts):
                for text in ([texts] if isinstance(texts, str) else texts):
                    vector = np.zeros(512, dtype=np.float32)
                    kind = next(k for k in kinds if text in DESCRIPTIONS.get(k, TAXONOMY.get(k, ())))
                    vector[kinds.index(kind)] = 1
                    yield vector

        class Image:
            def embed(self, images, **kwargs):
                yield from images

        with tempfile.TemporaryDirectory(prefix="newsflow-context-negative-") as temporary:
            root = Path(temporary)
            clip = root / "unlabelled.mp4"
            clip.write_bytes(b"disposable-window")
            vector = np.zeros(512, dtype=np.float32)
            for kind, value in values.items():
                vector[kinds.index(kind)] = value
            vector[-1] = np.sqrt(1 - float(vector @ vector))
            index = ClipIndex(root / "index.sqlite3", embedder_factory=lambda: (Image(), Text()))
            index._visual_models_available = lambda: True
            index._sample_visual_window = lambda *_: ([vector] * 3, [.5, 3., 5.5])
            return index.assess_visual_window(query, clip, 0., 6.)

    def test_listing_vessel_is_not_normal_shipping_but_remains_available_for_incident(self):
        values = {"port": .27, "vessel_incident": .31}
        self.assertNotIn(self.assess("seaport cargo ship shipping logistics", values)["relation"], {"direct", "context"})
        self.assertEqual("direct", self.assess("damaged cargo ship sinking at sea", values)["relation"])

    def test_indoor_display_near_tie_cannot_establish_freight_transport(self):
        values = {"road_cargo": .28, "warehouse": .25, "equipment_display": .275}
        self.assertNotIn(self.assess("seaport cargo cranes ships", values)["relation"], {"direct", "context"})
        self.assertEqual("direct", self.assess("agricultural machinery exhibition showroom",
                                             {**values, "equipment_display": .35})["relation"])

    def test_foreign_institution_symbol_cannot_be_overruled_by_generic_building_role(self):
        values = {"government_building": .28, "city": .24,
                  "institution_ukraine": .35, "institution_russia": .29}
        wrong = self.assess("Moscow Russia government building exterior illustrative context", values)
        self.assertEqual("contradiction", wrong["relation"])
        self.assertEqual("institutional-national-symbol-conflict", wrong["reason"])
        self.assertEqual("direct", self.assess("Kyiv Ukraine government building exterior", values)["relation"])
        self.assertEqual("direct", self.assess("government building exterior", values)["relation"])
        self.assertEqual("direct", self.assess("Russia Ukraine government building exterior", values)["relation"])
        self.assertFalse(wrong["event_confirmed"])

    def test_symbol_cues_do_not_compete_with_port_or_confirm_location(self):
        scores = [{"port": .32, "government_building": .18,
                   "institution_ukraine": .36, "institution_russia": .29}] * 3
        result = classify_window("seaport cargo ship shipping", scores)
        self.assertEqual("direct", result["relation"])
        self.assertFalse(result["event_confirmed"])

    def test_clear_ports_warehouses_and_matching_russian_institution_remain_usable(self):
        for query, values, expected in (
            ("seaport cargo ship shipping", {"port": .35, "vessel_incident": .22}, "direct"),
            ("seaport cargo ship shipping", {"warehouse": .35, "equipment_display": .20}, "context"),
            ("cargo trucks road freight", {"road_cargo": .35, "equipment_display": .20}, "direct"),
            ("Moscow Russia government building exterior", {"government_building": .28,
             "institution_russia": .36, "institution_ukraine": .28}, "direct"),
        ):
            with self.subTest(query=query):
                self.assertEqual(expected, self.assess(query, values)["relation"])

    def test_symbol_conflict_needs_two_clear_frames_and_does_not_reject_meetings(self):
        base = {"government_building": .30, "institution_ukraine": .31, "institution_russia": .305}
        one = {**base, "institution_ukraine": .36}
        self.assertEqual("direct", classify_window("Moscow Russia government building exterior", [one, base, base])["relation"])
        meeting = {"meeting": .35, "institution_ukraine": .37, "institution_russia": .28}
        self.assertEqual("direct", classify_window("Moscow Russia diplomatic meeting", [meeting] * 3)["relation"])

    def test_negated_incident_does_not_select_shipwreck_role(self):
        from scriptor.visual_evidence import query_topic
        for query in ("cargo ship shipping without shipwreck", "cargo ship not sinking normal seaport",
                      "грузовой порт без затонувших судов"):
            with self.subTest(query=query):
                self.assertEqual("port", query_topic(query)[0])

    def test_financial_sinking_is_not_a_vessel_incident(self):
        from scriptor.visual_evidence import query_topic
        query = "finance stock market sinking economy"
        self.assertEqual("finance", query_topic(query)[0])
        self.assertEqual("direct", classify_window(query, [{"finance": .35, "port": .10}] * 3)["relation"])

    def test_negated_sinking_does_not_erase_positive_ship_damage(self):
        from scriptor.visual_evidence import query_topic
        for query in ("damaged cargo ship not sinking", "no shipwreck but a damaged cargo ship",
                      "no shipwreck but damaged cargo ship", "not sinking but capsized cargo vessel",
                      "cargo vessel sinking without shipwreck", "без крушения, затонувшее судно"):
            with self.subTest(query=query):
                self.assertEqual("vessel_incident", query_topic(query)[0])

    def test_active_selector_replaces_bad_visual_with_compatible_fallback(self):
        from scriptor import bridge
        from scriptor.ai_index import SearchHit
        from scriptor.footage import FootageItem
        for query, bad_scores, context_kind in (
            ("rail freight train grain cargo logistics, grain cargo warehouse storage logistics",
             {"road_cargo": .28, "equipment_display": .275}, "port"),
            ("seaport cargo cranes ships", {"road_cargo": .28, "equipment_display": .275}, "warehouse"),
            ("seaport cargo ship shipping", {"port": .27, "vessel_incident": .31}, "warehouse"),
            ("Moscow Russia government building exterior", {"government_building": .28,
             "institution_ukraine": .35, "institution_russia": .29}, "meeting"),
        ):
            with self.subTest(query=query):
                bad = FootageItem("D:/test-owned/bad.mp4", "bad.mp4")
                good = FootageItem("D:/test-owned/context.mp4", "context.mp4")
                wrong = self.assess(query, bad_scores)
                compatible = self.assess(query, {context_kind: .35})
                bad._visual_assessor = lambda *_, result=wrong, **__: result
                good._visual_assessor = lambda *_, result=compatible, **__: result
                selected = bridge._select_montage_candidate(
                    query, strict_hits=[SearchHit(bad, .99, 30)],
                    fallback_hits=[SearchHit(good, .18, 30)], required_duration=6,
                    match_threshold=.22, used_paths=set(), used_families=set(),
                    project_used_paths=set(), project_used_families=set(),
                    reserved_paths=set(), reserved_families=set(),
                    source_exists=lambda _: True, source_duration=lambda _: 30)
                self.assertEqual(good.path, selected.item.path)
                self.assertEqual("context", selected.diagnostics["visual"]["relation"])

"""Actual scene21/24 context regressions; pure metadata, no media or models."""
import unittest

from scriptor import bridge
from scriptor.scene_intent import visual_intent
from scriptor.timeline import VISUAL_TERMS
from scriptor.visual_evidence import classify_window, query_topic
from scriptor.voice_map import VoiceMapStatus


def actual_excerpt_scenes():
    # Paraphrased metadata retains the original cut/segment timing pattern.
    # Actual full authored maps stay in the private ignored verification pool.
    rows = [
        (0, 104.613, "Вступление.", "international news, documentary footage"),
        (104.613, 110.939, "В новом отчёте отраслевое ведомство сообщило об общем объёме", "international news, documentary footage"),
        (110.939, 113.858, "трёх миллионов тонн аграрного экспорта.", "seaport cargo cranes ships"),
        (113.858, 120.184, "Объём оказался меньше плана. По зерну разрыв оказался ещё больше:", "grain harvest agricultural storage wheat field"),
        (120.184, 124.076, "вывезено около двух миллионов тонн,", "international news, documentary footage"),
        (124.076, 128.456, "то есть четверть расчётного объёма.", "international news, documentary footage"),
        (128.456, 132.835, "Перевозчики изменили направление железнодорожных потоков. Почти всё зерно,", "grain harvest agricultural storage wheat field"),
        (132.835, 135.754, "которое железная дорога везёт на экспорт,", "seaport cargo cranes ships"),
        (135.754, 142.08, "теперь движется к западной границе, а не к морским портам.", "seaport cargo cranes ships, border checkpoint guards fence"),
        (142.08, 148.405, "Сухопутный маршрут меняется. Теперь виден его предел.", "international news, documentary footage"),
    ]
    status = VoiceMapStatus("ready", "ready", path="metadata-fixture.json", data={
        "audioDuration": rows[-1][1], "timingMode": "aligned", "schemaVersion": 1,
        "productionItemId": "fixture", "scriptSha256": "test", "audioSha256": "test", "alignmentEngine": "test",
        "segments": [{"id": i + 1, "start": start, "end": end, "duration": end - start,
                      "text": text, "visualQuery": query}
                     for i, (start, end, text, query) in enumerate(rows)],
    })
    return bridge._voice_map_scenes(status)[0]


class ActualSceneContextTests(unittest.TestCase):
    def test_quantified_export_keeps_named_grain_without_inventing_harvest(self):
        prior = visual_intent("По зерну разрыв был ещё больше:", VISUAL_TERMS)
        current = visual_intent("вывезено около двух миллионов тонн,", VISUAL_TERMS, previous=prior)
        self.assertEqual("grain", current["commodity_subject"])
        self.assertIn("cargo", current["visual_query"])
        self.assertNotIn("harvest", current["visual_query"])

    def test_authored_scene21_keeps_export_subject_instead_of_nearby_farm_tag(self):
        scene = actual_excerpt_scenes()[20]
        self.assertEqual("grain", scene["scene_intent"]["commodity_subject"])
        self.assertIn("cargo", scene["visual_query_en"])
        self.assertNotIn("harvest", scene["visual_query_en"])

    def test_negated_destination_keeps_preceding_rail_subject(self):
        prior = visual_intent("которое железная дорога везёт на экспорт,", VISUAL_TERMS)
        current = visual_intent("теперь в первую очередь движется к западной границе, а не к черноморским портам.", VISUAL_TERMS, previous=prior)
        self.assertIn("rail", current["visual_query"])
        self.assertNotEqual("port",query_topic(current["visual_query"])[0])
        self.assertNotIn("maritime", current["visual_query"])

    def test_denied_port_cannot_reenter_through_old_warehouse_context(self):
        previous = visual_intent("Зерно везут железной дорогой на склад возле порта.", VISUAL_TERMS)
        for prep in ("к", "по"):
            current = visual_intent(f"теперь движется к западной границе, а не {prep} морским портам.", VISUAL_TERMS, previous=previous)
            self.assertIn("rail", current["visual_query"])
            self.assertNotIn("seaport", current["visual_query"])
            self.assertNotIn("port", query_topic(current["visual_query"])[2])
        shipping = visual_intent("Грузовые суда заходят в порт.", VISUAL_TERMS)
        current = visual_intent("теперь движется к западной границе, а не к морским портам.", VISUAL_TERMS, previous=shipping)
        self.assertNotIn("rail", current["visual_query"])
        self.assertNotEqual("port",query_topic(current["visual_query"])[0])

    def test_authored_scene24_retains_verifiable_transport_role(self):
        scene = actual_excerpt_scenes()[23]
        topic = query_topic(scene["visual_query_en"])
        self.assertIsNotNone(topic, scene["visual_query_en"])
        self.assertEqual("rail", topic[0])
        self.assertNotIn("seaport", scene["visual_query_en"])

    def test_existing_grain_context_and_road_fallback_remain_valid(self):
        query = "rail freight train grain transport cargo logistics"
        grain = [{"farm": .35, "grain_field": .35, "non_grain_agriculture": .20, "rail": .18, "warehouse": .17}] * 3
        road = [{"road_cargo": .35, "rail": .19, "warehouse": .16, "factory": .15, "equipment_display": .17}] * 3
        port = [{"port": .40, "rail": .18, "warehouse": .17}] * 3
        self.assertEqual("consistent-grain-commodity-context", classify_window(query, grain)["reason"])
        self.assertEqual("context", classify_window(query, road)["relation"])
        self.assertEqual("contradiction", classify_window(query, port)["relation"])

    def test_new_product_protest_and_named_speaker_reset_grain(self):
        prior = visual_intent("Экспорт зерна продолжается.", VISUAL_TERMS)
        for text in ("Фермеры выращивают помидоры в теплицах.", "Рабочие объявили забастовку и вышли на пикет.", "Путин выступил с заявлением."):
            with self.subTest(text=text):
                current = visual_intent(text, VISUAL_TERMS, previous=prior)
                self.assertNotEqual("grain", current["commodity_subject"])
                self.assertNotIn("grain cargo", current["visual_query"])
        speaker = visual_intent("Путин выступил с заявлением.", VISUAL_TERMS, previous=prior)
        self.assertEqual(["putin"], speaker["target_people"])

    def test_quantity_identity_is_not_invented_for_negative_or_different_product(self):
        prior = visual_intent("По зерну разрыв увеличился:", VISUAL_TERMS)
        for text in ("Не вывезено ни одной тонны.", "Вывезено пять тонн помидоров.", "Вывезено пять тонн нефти.",
                     "вывезено миллион тонн трески,", "экспортировано две тысячи тонн травы,", "вывезено две тонны двигателей,"):
            with self.subTest(text=text):
                current = visual_intent(text, VISUAL_TERMS, previous=prior)
                self.assertNotEqual("grain", current["commodity_subject"])

    def test_single_tonne_and_bounded_export_context(self):
        prior = visual_intent("По зерну разрыв увеличился:", VISUAL_TERMS)
        self.assertEqual("grain", visual_intent("вывезена одна тонна,", VISUAL_TERMS, previous=prior)["commodity_subject"])
        for metadata in ({"inherited_subject_depth": 6}, {"inherited_subject_words": 64}):
            with self.subTest(metadata=metadata):
                current = visual_intent("вывезена одна тонна,", VISUAL_TERMS, previous={**prior, **metadata})
                self.assertNotEqual("grain", current["commodity_subject"])
        current = visual_intent("вывезена одна тонна,", VISUAL_TERMS, previous={**prior, "commodity_subject": "future-product"})
        self.assertEqual("", current["commodity_subject"])

    def test_abstract_producer_revenue_keeps_previous_cargo_role(self):
        prior = visual_intent("Урожай отправляют через склады на экспорт,", VISUAL_TERMS)
        current = visual_intent("а аграрии получат меньше денег на следующий производственный цикл.", VISUAL_TERMS, previous=prior)
        self.assertIn("cargo", current["visual_query"])
        self.assertNotIn("farming fields", current["visual_query"])

    def test_trader_cost_keeps_commodity_within_existing_context_budget(self):
        prior = visual_intent("Зерно отправляют через грузовой порт,", VISUAL_TERMS)
        current = visual_intent("Трейдеру приходится закладывать больше времени и денег.", VISUAL_TERMS, previous=prior)
        self.assertEqual("grain", current["commodity_subject"])
        exhausted = visual_intent("потому что логистические расходы вычитаются из стоимости его продукции.", VISUAL_TERMS,
                                 previous={**current, "inherited_subject_depth": 6})
        self.assertIsNotNone(query_topic(exhausted["visual_query"]))
        self.assertNotIn("grain", exhausted["visual_query"])
        current = visual_intent("потому что логистические расходы вычитаются из стоимости его продукции.", VISUAL_TERMS, previous=current)
        self.assertEqual("", current["commodity_subject"])
        self.assertIn("cargo", current["visual_query"])

    def test_trader_new_commodity_export_is_not_overwritten_by_old_product(self):
        for old,new,wanted,unwanted in (("зерна", "нефти", "oil", "grain"), ("нефти", "зерна", "grain", "oil")):
            prior = visual_intent(f"Экспорт {old} продолжается.", VISUAL_TERMS)
            current = visual_intent(f"Трейдер закладывает больше денег на экспорт {new}.", VISUAL_TERMS, previous=prior)
            self.assertEqual(wanted, current["commodity_subject"])
            self.assertNotIn(unwanted, current["visual_query"])
        prior = visual_intent("Экспорт зерна продолжается.", VISUAL_TERMS)
        current = visual_intent("Аграрии получат доход от экспорта помидоров.", VISUAL_TERMS, previous=prior)
        self.assertNotEqual("grain", current["commodity_subject"])

    def test_trader_named_crop_keeps_existing_current_crop_action(self):
        prior = visual_intent("Зерно доставляют через грузовой порт.", VISUAL_TERMS)
        text = "Трейдеру нужно больше денег на картошку."
        direct = visual_intent(text, VISUAL_TERMS)
        current = visual_intent(text, VISUAL_TERMS, previous=prior)
        self.assertEqual(direct["visual_query"], current["visual_query"])
        self.assertNotEqual("grain", current["commodity_subject"])

    def test_current_logistics_cost_requires_window_role_without_commodity_antecedent(self):
        from scriptor.footage import FootageItem
        text = "потому что логистические расходы вычитаются из стоимости его продукции."
        for previous in (None, {"inherited_subject_depth":6,"inherited_subject_words":64,"commodity_subject":"grain",
                                "visual_query":"grain cargo export warehouse storage logistics"}):
            query = visual_intent(text, VISUAL_TERMS, previous=previous)["visual_query"]
            self.assertIsNotNone(query_topic(query))
            self.assertNotIn("grain", query)
            for kind,expected in (("farm", False), ("warehouse", True), ("road_cargo", True)):
                item = FootageItem("fixture.mp4", "documentary fixture", tags=[])
                scores = [{kind:.40,"factory":.15,"equipment_display":.15}] * 3
                assessment = classify_window(query,scores)
                self.assertEqual(expected,bridge._semantic_clip_ok(query,item,visual_assessment=assessment))

    def test_negative_port_constraint_keeps_only_existing_nonport_cargo_roles(self):
        query = "warehouse cargo storage logistics, not seaport"
        topic = query_topic(query)
        self.assertEqual("warehouse", topic[0])
        self.assertNotIn("port", topic[2])
        for kind,expected in (("port", False), ("farm", False), ("warehouse", True), ("road_cargo", True)):
            assessment = classify_window(query,[{kind:.40,"factory":.15,"equipment_display":.15}]*3)
            self.assertEqual(expected,assessment["relation"] in {"direct","context"})

    def test_denied_damage_keeps_positive_commercial_port_role(self):
        for query in ("no damage to cargo ships at the port", "not damaged cargo ship at port", "not damaged cargo ship"):
            with self.subTest(query=query):
                topic = query_topic(query)
                self.assertIsNotNone(topic)
                self.assertEqual("port",topic[0])
                result = classify_window(query,[{"port":.40,"vessel_incident":.15}]*3)
                self.assertEqual("direct",result["relation"])

    def test_denied_port_only_beat_does_not_borrow_previous_seaport(self):
        from scriptor.footage import FootageItem
        from tests.test_footage_followup import select, voice_scenes
        scenes = voice_scenes(["Грузовые суда перевозят товары через порт.", "а не к морским портам."],
                              ["seaport cargo cranes ships", "seaport cargo cranes ships"])
        query = scenes[1]["visual_query_en"]
        topic = query_topic(query)
        self.assertIsNotNone(topic)
        self.assertNotEqual("port", topic[0])
        self.assertNotIn("port",topic[2])
        items=[]
        for kind in ("port","farm","road_cargo"):
            item=FootageItem(f"{kind}.mp4",kind,tags=[])
            item._visual_assessor=lambda q,start,duration,kind=kind,**kwargs:classify_window(q,[{kind:.40,"factory":.15,"equipment_display":.15}]*3)
            items.append(item)
        selected = select(query,items)
        self.assertEqual("road_cargo.mp4",selected.item.path)


if __name__ == "__main__":
    unittest.main()

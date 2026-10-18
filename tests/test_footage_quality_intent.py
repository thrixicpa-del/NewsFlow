"""Local transport subjects and explicit geography without invented events."""
import unittest

from scriptor.scene_intent import visual_intent
from scriptor.timeline import VISUAL_TERMS


class LocalActionQualityTests(unittest.TestCase):
    def test_reported_indeclinable_author_keeps_explicit_coordinated_subjects(self):
        from tests.test_footage_followup import voice_scenes

        for text, targets in (
            ("Заявление Лукашенко и Путин прокомментировали вместе.", ["lukashenko", "putin"]),
            ("Заявление Лукашенко и Путин комментируют вместе.", ["lukashenko", "putin"]),
            ("Заявление Лукашенко и Путин прокомментируют вместе.", ["lukashenko", "putin"]),
            ("Заявление Лукашенко и Путина прокомментировал Зеленский.", ["zelensky"]),
        ):
            with self.subTest(text=text):
                self.assertEqual(targets, visual_intent(text, VISUAL_TERMS)["target_people"])
                self.assertEqual(targets, voice_scenes([text])[0]["scene_intent"]["target_people"])

    def test_protest_attendee_is_selected_outside_opposition_name_occurrences(self):
        from tests.test_footage_followup import voice_scenes

        for text, targets in (
            ("Митинг против Лукашенко посетил Зеленский.", ["zelensky"]),
            ("Лукашенко посетил митинг против Лукашенко.", ["lukashenko"]),
            ("Митинг против Лукашенко посетил Лукашенко.", ["lukashenko"]),
            ("В Минске прошёл протест против Лукашенко.", []),
            ("Зеленский прокомментировал митинг против Лукашенко.", ["zelensky"]),
            ("Лукашенко посетил мирный митинг.", ["lukashenko"]),
        ):
            with self.subTest(text=text):
                self.assertEqual(targets, visual_intent(text, VISUAL_TERMS)["target_people"])
                self.assertEqual(targets, voice_scenes([text])[0]["scene_intent"]["target_people"])

    def test_belarus_place_survives_local_and_voice_protest_queries(self):
        from scriptor import bridge
        from scriptor.footage import FootageItem
        from tests.test_footage_followup import voice_scenes

        for text in ("В Минске жители вышли на митинг.",
                     "В Беларуси рабочие объявили забастовку.",
                     "В Белоруссии прошёл мирный марш протеста."):
            with self.subTest(text=text):
                for query in (visual_intent(text, VISUAL_TERMS)["visual_query"],
                              voice_scenes([text])[0]["visual_query_en"]):
                    self.assertIn("Belarus", query)
                    self.assertNotIn("Lukashenko", query)
                    self.assertFalse(bridge._semantic_clip_ok(query, FootageItem(
                        "moscow.mp4", "Moscow peaceful workers rally", tags=["protest-crowd"])))
                    self.assertTrue(bridge._semantic_clip_ok(query, FootageItem(
                        "minsk.mp4", "Minsk peaceful workers rally", tags=["protest-crowd"])))
        cancelled = visual_intent("В Минске митинг не начался.", VISUAL_TERMS)
        self.assertIn("Belarus", cancelled["visual_query"])
        self.assertNotIn("protest crowd", cancelled["visual_query"])

    def test_indeclinable_reported_author_does_not_replace_actual_speaker(self):
        from tests.test_footage_followup import voice_scenes

        for text, target in (
            ("Заявление Лукашенко прокомментировал Зеленский.", "zelensky"),
            ("На заявление Лукашенко ответил Путин.", "putin"),
            ("Зеленский прокомментировал заявление Лукашенко.", "zelensky"),
            ("Путин ответил на заявление Лукашенко.", "putin"),
            ("Лукашенко прокомментировал заявление Зеленского.", "lukashenko"),
            ("На заявление Зеленского ответил Лукашенко.", "lukashenko"),
            ("Заявление Лукашенко не прокомментировал Зеленский.", "zelensky"),
        ):
            with self.subTest(text=text):
                self.assertEqual([target], visual_intent(text, VISUAL_TERMS)["target_people"])
                self.assertEqual([target], voice_scenes([text])[0]["scene_intent"]["target_people"])
        for text in ("Лукашенко и Зеленский прокомментировали заявление.",
                     "Лукашенко и Зеленский встретились."):
            self.assertEqual(["lukashenko", "zelensky"], visual_intent(text, VISUAL_TERMS)["target_people"])
        protest = visual_intent("В Минске жители вышли на протест против Лукашенко.", VISUAL_TERMS)
        self.assertIn("protest", protest["visual_query"])
        self.assertEqual([], protest["target_people"])
        participant = visual_intent("Лукашенко посетил мирный митинг.", VISUAL_TERMS)
        self.assertEqual(["lukashenko"], participant["target_people"])

    def test_asserted_military_council_is_a_meeting_not_battlefield_action(self):
        from scriptor import bridge
        from scriptor.footage import FootageItem
        from scriptor.visual_evidence import classify_window

        for text in ("Генералы провели совещание в штабе.",
                     "Командующие проводят совещание.",
                     "В штабе состоялось совещание офицеров.",
                     "Военные делегации встретились для обсуждения соглашения.",
                     "Министры обороны провели переговоры."):
            with self.subTest(text=text):
                query = visual_intent(text, VISUAL_TERMS)["visual_query"]
                self.assertIn("meeting", query)
                self.assertNotIn("military vehicles", query)
                self.assertNotIn("frontline", query)
                meeting = classify_window(query, [{"meeting": .36, "combat": .20}] * 3)
                combat = classify_window(query, [{"meeting": .20, "combat": .36}] * 3)
                self.assertEqual("direct", meeting["relation"])
                self.assertEqual("contradiction", combat["relation"])
                item = FootageItem("council.mp4", "military delegation meeting")
                self.assertTrue(bridge._semantic_clip_ok(query, item, visual_assessment=meeting))
                self.assertFalse(bridge._semantic_clip_ok(query, item, visual_assessment=combat))

    def test_cancelled_or_conditional_council_does_not_assert_a_meeting(self):
        for text in ("Генералы отменили совещание в штабе.",
                     "Совещание офицеров не состоялось.",
                     "Если генералы проведут совещание в штабе, решение объявят позже."):
            with self.subTest(text=text):
                self.assertNotIn("meeting", visual_intent(text, VISUAL_TERMS)["visual_query"])
        query = visual_intent("Военные начали наступление после совещания.", VISUAL_TERMS)["visual_query"]
        self.assertIn("advancing", query)
        self.assertNotIn("meeting", query)

    def test_past_council_prefix_cannot_capture_a_later_combat_predicate(self):
        from scriptor.visual_evidence import query_topic

        for text, action in (("После совещания военные начали наступление.", "advancing"),
                             ("После совещания войска начали обстрел города.", "shelling")):
            with self.subTest(text=text):
                query = visual_intent(text, VISUAL_TERMS)["visual_query"]
                self.assertIn(action, query)
                self.assertNotIn("meeting", query)
                self.assertEqual("combat", query_topic(query)[0])

    def test_denied_council_does_not_erase_another_clauses_current_action(self):
        for text in ("Совещание офицеров не проходило.", "Совещание офицеров не прошло."):
            with self.subTest(text=text):
                self.assertNotIn("meeting", visual_intent(text, VISUAL_TERMS)["visual_query"])
        for text in ("Совещание отменили. Командующие провели совещание.",
                     "Совещание офицеров не прошло. В штабе состоялось совещание командующих."):
            with self.subTest(text=text):
                self.assertIn("meeting", visual_intent(text, VISUAL_TERMS)["visual_query"])
        query = visual_intent("Совещание отменили. Войска начали наступление.", VISUAL_TERMS)["visual_query"]
        self.assertIn("advancing", query)
        self.assertNotIn("meeting", query)

    def test_modified_past_council_and_negated_auxiliary_are_not_assertions(self):
        from scriptor.visual_evidence import query_topic

        for text, action in (("После утреннего совещания военные начали наступление.", "advancing"),
                             ("Перед закрытым совещанием войска начали обстрел города.", "shelling")):
            with self.subTest(text=text):
                query = visual_intent(text, VISUAL_TERMS)["visual_query"]
                self.assertIn(action, query)
                self.assertNotIn("meeting", query)
                self.assertEqual("combat", query_topic(query)[0])
        for text in ("Совещание офицеров не будет проходить.",
                     "Совещание офицеров не планировали проводить.",
                     "Совещание офицеров не смогло состояться."):
            with self.subTest(text=text):
                self.assertNotIn("meeting", visual_intent(text, VISUAL_TERMS)["visual_query"])

    def test_council_predicate_is_linked_to_its_subject_in_either_order(self):
        for text in ("Совещание офицеров началось.", "Совещания командиров проходят в штабе.",
                     "После обеда офицеры провели совещание.",
                     "Совещание не будет проходить. Офицеры провели другое совещание."):
            with self.subTest(text=text):
                self.assertIn("meeting", visual_intent(text, VISUAL_TERMS)["visual_query"])

    def test_negation_covers_each_asserted_forward_council_predicate(self):
        for predicate in ("провели", "проводят", "начали", "собрались на"):
            with self.subTest(predicate=predicate):
                self.assertIn("meeting", visual_intent(
                    f"Офицеры {predicate} совещание.", VISUAL_TERMS)["visual_query"])
                self.assertNotIn("meeting", visual_intent(
                    f"Офицеры не {predicate} совещание.", VISUAL_TERMS)["visual_query"])
        self.assertIn("meeting", visual_intent("Состоялось совещание офицеров.", VISUAL_TERMS)["visual_query"])
        self.assertNotIn("meeting", visual_intent("Не состоялось совещание офицеров.", VISUAL_TERMS)["visual_query"])

    def test_grain_export_verbs_and_storage_describe_cargo_not_harvesting(self):
        for text in ("Пшеницу невозможно выгодно вывезти за границу.",
                     "Зерно оставляют на хранение перед продажей."):
            with self.subTest(text=text):
                query = visual_intent(text, VISUAL_TERMS)["visual_query"]
                self.assertIn("cargo", query)
                self.assertIn("warehouse", query)
                self.assertNotIn("harvest", query)
        for text in ("Комбайны начали уборку зерна.", "Жатва началась.", "На полях идёт жатва."):
            self.assertIn("harvest", visual_intent(text, VISUAL_TERMS)["visual_query"])
        self.assertNotIn("harvest", visual_intent("Делегации собираются в столице.", VISUAL_TERMS)["visual_query"])
        self.assertNotIn("cargo", visual_intent("Зерно растёт в поле.", VISUAL_TERMS)["visual_query"])

    def test_intention_to_export_is_not_an_asserted_harvesting_action(self):
        for text in ("Зерно собираются вывезти за границу.", "Аграрии собираются увеличить экспорт.",
                     "Аграрии собирались увеличить экспорт.", "Мы собираемся вывезти зерно.",
                     "Аграрии собирают деньги на вывоз зерна.",
                     "Аграрное ведомство собирает данные об экспорте зерна."):
            with self.subTest(text=text):
                query = visual_intent(text, VISUAL_TERMS)["visual_query"]
                self.assertIn("warehouse", query)
                self.assertNotIn("harvest", query)
                self.assertNotIn("combine", query)
        self.assertIn("harvest", visual_intent("Зерно собирают, началась жатва.", VISUAL_TERMS)["visual_query"])

    def test_stored_commodity_sale_references_keep_only_bounded_physical_subject(self):
        previous = visual_intent("Зерно оставляют на хранение перед продажей,", VISUAL_TERMS)
        for text in ("либо продают его с транспортным дисконтом,",
                     "либо ищут субсидию на его хранение и вывоз."):
            previous = visual_intent(text, VISUAL_TERMS, previous=previous)
            self.assertIn("warehouse", previous["visual_query"])
            self.assertNotIn("harvest", previous["visual_query"])
        for text in ("Банк открыл кредитную программу.", "Комбайны начали уборку урожая."):
            current = visual_intent(text, VISUAL_TERMS, previous=previous)
            self.assertNotIn("warehouse", current["visual_query"])
        self.assertEqual("", visual_intent("Продают его с логистическим дисконтом,", VISUAL_TERMS)["visual_query"])
        previous = visual_intent("Зерно оставляют на хранение,", VISUAL_TERMS)
        for _ in range(7):
            previous = visual_intent("Продают его с логистическим дисконтом,", VISUAL_TERMS, previous=previous)
        self.assertNotIn("warehouse", previous["visual_query"])

    def test_parallel_export_actions_keep_their_local_physical_subject_place(self):
        from scriptor import bridge
        from scriptor.footage import FootageItem

        previous = visual_intent("Украина отправляет зерно через морские порты.", VISUAL_TERMS)
        previous = visual_intent("Наращивают железнодорожную перевозку грузов,", VISUAL_TERMS, previous=previous)
        current = visual_intent(
            "используют дунайские причалы и ищут дополнительные мощности в странах Европейского союза.",
            VISUAL_TERMS, previous=previous,
        )
        query = current["visual_query"]
        self.assertIn("Ukraine", query)
        self.assertIn("European Union", query)
        self.assertIn("Danube", query)
        visual = {"relation": "direct", "dominant_kind": "port", "event_confirmed": False}
        for country, allowed in (("Ukraine", True), ("European Union Romania", True),
                                 ("Russia", False), ("Iran", False)):
            with self.subTest(country=country):
                item = FootageItem(f"D:/test/{country}/cargo.mp4", f"{country} river cargo port.mp4")
                self.assertEqual(allowed, bridge._semantic_clip_ok(query, item, visual_assessment=visual))
        self.assertTrue(current["illustrative_only"])

    def test_explicit_capacity_place_is_not_replaced_by_prior_export_country(self):
        previous = visual_intent("Украина отправляет груз через речные порты.", VISUAL_TERMS)
        for text in ("Ищут дополнительные мощности в странах Европейского союза.",
                     "Используют речные порты Европейского союза."):
            with self.subTest(text=text):
                current = visual_intent(text, VISUAL_TERMS, previous=previous)
                self.assertIn("European Union", current["visual_query"])
                self.assertNotIn("Ukraine", current["visual_query"])

    def test_physical_subject_place_resets_at_new_topic_and_expires(self):
        subject = visual_intent("Украина отправляет зерно через порт.", VISUAL_TERMS)
        target = "Используют дунайские порты и ищут мощности в странах Европейского союза."
        for text in ("Банк открыл кредитную программу.", "Делегации начали переговоры.",
                     "Рабочие устроили забастовку.", "Комбайны начали уборку урожая.",
                     "В школе открыли новый класс."):
            with self.subTest(reset=text):
                reset = visual_intent(text, VISUAL_TERMS, previous=subject)
                current = visual_intent(target, VISUAL_TERMS, previous=reset)
                self.assertNotIn("Ukraine", current["visual_query"])
        previous = subject
        for _ in range(7):
            previous = visual_intent("Наращивают перевозку грузов по железной дороге,", VISUAL_TERMS, previous=previous)
        self.assertNotIn("Ukraine", visual_intent(target, VISUAL_TERMS, previous=previous)["visual_query"])
        verbose = visual_intent(" ".join(["грузов"] * 65) + " по железной дороге,", VISUAL_TERMS, previous=subject)
        self.assertNotIn("Ukraine", visual_intent(target, VISUAL_TERMS, previous=verbose)["visual_query"])

    def test_voice_grid_parallel_transport_keeps_bounded_country_context(self):
        from scriptor import bridge
        from scriptor.voice_map import VoiceMapStatus

        texts = ["Через морские порты отправляют зерно.", "Украина выбирает другой путь.",
                 "Наращивают железнодорожную перевозку зерна,",
                 "используют дунайские порты и ищут мощности в странах Европейского союза."]
        payload = {"audioDuration": 24, "timingMode": "approximate", "schemaVersion": 1,
                   "productionItemId": "disposable", "scriptSha256": "test", "audioSha256": "test",
                   "alignmentEngine": "test", "segments": [
            {"id": i + 1, "start": i * 6, "end": (i + 1) * 6, "duration": 6,
             "text": text, "visualQuery": ""} for i, text in enumerate(texts)
        ]}
        scenes, _ = bridge._voice_map_scenes(VoiceMapStatus("approximate", "approximate", data=payload))
        self.assertEqual(texts, [scene["narration"] for scene in scenes])
        self.assertEqual([6] * 4, [scene["duration"] for scene in scenes])
        self.assertIn("Ukraine", scenes[-1]["visual_query_en"])
        self.assertIn("European Union", scenes[-1]["visual_query_en"])

    def test_european_transport_does_not_invent_parliament_or_brussels(self):
        text = "используют дунайские порты и ищут дополнительные мощности в странах Европейского союза."
        intent = visual_intent(text, VISUAL_TERMS)
        self.assertIn("port", intent["visual_query"])
        self.assertIn("Danube", intent["visual_query"])
        self.assertIn("European Union", intent["visual_query"])
        self.assertNotIn("Parliament", intent["visual_query"])
        self.assertNotIn("Brussels", intent["visual_query"])
        self.assertNotIn("press conference", intent["visual_query"])
        self.assertTrue(intent["illustrative_only"])

    def test_explicit_european_institutions_remain_explicit(self):
        intent = visual_intent("Европейский парламент провёл заседание в Брюсселе.", VISUAL_TERMS)
        self.assertIn("Parliament", intent["visual_query"])
        self.assertIn("Brussels", intent["visual_query"])

    def test_abstract_logistics_clauses_keep_bounded_transport_subject(self):
        for subject, wanted in (("Глубоководные порты ещё работали стабильнее.", "port"),
                                ("Поезд перевозит груз.", "rail")):
            previous = visual_intent(subject, VISUAL_TERMS)
            for text in (
                "где прибыль на тонне может быть небольшой, это уже не техническая мелочь,",
                "Это увеличивает стоимость доставки.",
                "Из-за этого длительность доставки становится больше.",
            ):
                with self.subTest(subject=subject, text=text):
                    intent = visual_intent(text, VISUAL_TERMS, previous=previous)
                    self.assertIn(wanted, intent["visual_query"])
                    self.assertTrue(intent["illustrative_only"])
                    self.assertEqual(1, intent["inherited_subject_depth"])

    def test_transport_subject_does_not_follow_new_explicit_action(self):
        previous = visual_intent("Глубоководные порты работали стабильнее.", VISUAL_TERMS)
        for text, wanted in (("Рабочие устроили забастовку у завода.", "labor strike"),
                             ("Банк изменил стоимость кредита.", "bank"),
                             ("Делегации начали переговоры о сроках соглашения.", "diplomatic")):
            with self.subTest(text=text):
                intent = visual_intent(text, VISUAL_TERMS, previous=previous)
                self.assertIn(wanted, intent["visual_query"])
                self.assertNotIn("seaport", intent["visual_query"])

    def test_abstract_subject_inheritance_does_not_chain_indefinitely(self):
        previous = visual_intent("Порты работали стабильнее.", VISUAL_TERMS)
        inherited = visual_intent("Прибыль на тонне небольшая.", VISUAL_TERMS, previous=previous)
        self.assertIn("port", inherited["visual_query"])
        subsequent = visual_intent("Стоимость доставки увеличивается.", VISUAL_TERMS, previous=inherited)
        self.assertEqual("", subsequent["visual_query"])

    def test_two_word_railway_and_alternative_transport_are_recognized(self):
        for railway in ("железную дорогу", "железной дороге", "железные дороги"):
            text = f"весь поток невозможно мгновенно переставить на {railway}, грузовики и Дунай."
            with self.subTest(railway=railway):
                query = visual_intent(text, VISUAL_TERMS)["visual_query"]
                self.assertIn("rail", query)
                self.assertIn("cargo", query)
                self.assertIn("truck", query)
                self.assertIn("Danube", query)

    def test_linked_grain_economics_and_delivery_keep_transport_subject(self):
        previous = visual_intent("Глубоководные порты работали стабильнее.", VISUAL_TERMS)
        for text in (
            "Для зерна,",
            "где прибыль на тонне может быть небольшой,",
            "а вопрос того, имеет ли экспортная сделка экономический смысл.",
            "На одном из направлений доставка раньше занимала две недели,",
            "а теперь растянулась более чем на месяц.",
        ):
            with self.subTest(text=text):
                previous = visual_intent(text, VISUAL_TERMS, previous=previous)
                self.assertIn("port", previous["visual_query"])
                self.assertNotIn("finance", previous["visual_query"])
                self.assertNotIn("harvest", previous["visual_query"])
        reset = visual_intent("Рабочие устроили забастовку у завода.", VISUAL_TERMS, previous=previous)
        self.assertIn("labor strike", reset["visual_query"])
        self.assertNotIn("seaport", reset["visual_query"])
        linked = visual_intent("Для зерна,", VISUAL_TERMS, previous=visual_intent("Порты работают.", VISUAL_TERMS))
        for text in ("Рабочие устроили забастовку, которая имеет экономический смысл.",
                     "Завод открыл производство, которое имеет экономический смысл.",
                     "Банк изменил ставку, которая имеет экономический смысл."):
            with self.subTest(new_action=text):
                reset = visual_intent(text, VISUAL_TERMS, previous=linked)
                self.assertNotIn("seaport", reset["visual_query"])

    def test_linked_transport_chain_has_a_finite_clause_budget(self):
        previous = visual_intent("Порты работают стабильнее.", VISUAL_TERMS)
        previous = visual_intent("Для зерна,", VISUAL_TERMS, previous=previous)
        self.assertIn("port", previous["visual_query"])
        outcomes = []
        for _ in range(12):
            previous = visual_intent("где прибыль на тонне небольшая,", VISUAL_TERMS, previous=previous)
            outcomes.append(previous["visual_query"])
        self.assertIn("port", outcomes[0])
        self.assertEqual("", outcomes[-1])

    def test_shipping_object_aliases_do_not_resolve_to_court_or_flags(self):
        for text in ("Судоходство по морскому маршруту возобновилось.",
                     "Грузовое судно доставляет продукцию.",
                     "Ограничения осложняют судоходство."):
            with self.subTest(text=text):
                self.assertIn("cargo ship", visual_intent(text, VISUAL_TERMS)["visual_query"])
        self.assertNotIn("cargo ship", visual_intent("Решение суда вступило в силу.", VISUAL_TERMS)["visual_query"])

    def test_alternative_logistics_routes_have_a_physical_transport_subject(self):
        for text in ("Компании используют альтернативные логистические маршруты.",
                     "Логистические маршруты для перевозки продукции изменились."):
            with self.subTest(text=text):
                query = visual_intent(text, VISUAL_TERMS)["visual_query"]
                self.assertIn("cargo", query)
                self.assertIn("warehouse", query)

    def test_exported_commodity_does_not_become_generic_finance_or_another_commodity(self):
        for text, wanted, forbidden in (
            ("Экспорт зерна ищет экономически приемлемый выход на внешний рынок.", "grain", "finance"),
            ("Экспорт нефти ищет экономически приемлемый выход на внешний рынок.", "oil", "grain"),
            ("Аграрная продукция отправляется на экспорт.", "agricultur", "finance"),
        ):
            with self.subTest(text=text):
                query = visual_intent(text, VISUAL_TERMS)["visual_query"]
                self.assertIn(wanted, query)
                self.assertNotIn(forbidden, query)
                self.assertNotIn("finance", query)
                self.assertNotIn("harvest", query)

    def test_linked_export_volume_keeps_known_commodity_until_new_action(self):
        for commodity, wanted, forbidden in (("зерна", "grain", "oil"), ("нефти", "oil", "grain")):
            previous = visual_intent(f"Экспорт {commodity} продолжается.", VISUAL_TERMS)
            for text in ("Этот объём продукции сохранился.",
                         "Это объём, которому необходимо найти работающий,",
                         "безопасный и экономически приемлемый выход на внешний рынок."):
                with self.subTest(commodity=commodity, text=text):
                    previous = visual_intent(text, VISUAL_TERMS, previous=previous)
                    self.assertIn(wanted, previous["visual_query"])
                    self.assertNotIn(forbidden, previous["visual_query"])
                    self.assertNotIn("finance", previous["visual_query"])
            reset = visual_intent("Банк изменил условия кредита.", VISUAL_TERMS, previous=previous)
            self.assertIn("bank", reset["visual_query"])
            self.assertNotIn(wanted, reset["visual_query"])

    def test_loading_and_unloading_are_not_invented_for_navigation(self):
        for text, action in (("В терминале возобновилась погрузка товаров.", "cargo loading"),
                             ("В терминале завершилась выгрузка товаров.", "cargo unloading")):
            with self.subTest(text=text):
                self.assertIn(action, visual_intent(text, VISUAL_TERMS)["visual_query"])
        navigation = visual_intent("Судоходство постепенно восстанавливается.", VISUAL_TERMS)["visual_query"]
        self.assertIn("navigation", navigation)
        self.assertNotIn("loading", navigation)

    def test_rail_wagons_and_maritime_route_aliases_cover_physical_objects(self):
        cases = (("Товарные вагоны направляются к соседней стране.", "rail"),
                 ("Нарушение морской логистики увеличивает расходы.", "cargo ship"),
                 ("Суда ожидают прохода через судоходный канал.", "cargo ship"),
                 ("Товары можно перевезти по реке.", "cargo ship"),
                 ("Транспортный поток перенаправляют к Дунаю.", "Danube"),
                 ("Чёрное море остаётся сложным направлением для перевозок.", "Black Sea"))
        for text, wanted in cases:
            with self.subTest(text=text):
                self.assertIn(wanted, visual_intent(text, VISUAL_TERMS)["visual_query"])
        self.assertNotIn("cargo ship", visual_intent("Суда рассмотрели апелляции.", VISUAL_TERMS)["visual_query"])

    def test_anaphoric_transport_limit_keeps_only_recent_known_subject(self):
        previous = visual_intent("Судоходство по грузовому маршруту продолжается.", VISUAL_TERMS)
        current = visual_intent("Однако теперь видны его ограничения.", VISUAL_TERMS, previous=previous)
        self.assertIn("cargo ship", current["visual_query"])
        self.assertEqual(1, current["inherited_subject_depth"])
        unrelated = visual_intent("Однако теперь видны его ограничения.", VISUAL_TERMS)
        self.assertEqual("", unrelated["visual_query"])

    def test_overland_logistics_switch_supplies_subject_for_following_limit(self):
        previous = visual_intent("Маршрут проходил через морские порты.", VISUAL_TERMS)
        current = visual_intent("Сухопутный разворот перевозок уже происходит.", VISUAL_TERMS, previous=previous)
        self.assertIn("overland", current["visual_query"])
        self.assertNotIn("seaport", current["visual_query"])
        limit = visual_intent("Теперь становится виден его предел.", VISUAL_TERMS, previous=current)
        self.assertIn("overland", limit["visual_query"])
        military = visual_intent("Сухопутное наступление началось.", VISUAL_TERMS, previous=previous)
        self.assertIn("frontline", military["visual_query"])
        self.assertNotIn("warehouse", military["visual_query"])

    def test_ambiguous_court_plural_requires_maritime_context_for_vessels(self):
        for text in ("Решения судов обрели законную силу.",
                     "Апелляционное дело рассматривают в судах.",
                     "Постановления были вынесены судами.",
                     "Решения судов о работе порта вступили в силу."):
            with self.subTest(legal=text):
                query = visual_intent(text, VISUAL_TERMS)["visual_query"]
                self.assertNotIn("cargo ship", query)
                self.assertNotIn("navigation", query)
        for text in ("Проход грузовых судов по каналу возобновился.",
                     "Терминал работает с грузовыми судами.",
                     "На грузовых судах доставляют товары.",
                     "Суда подошли к морскому порту.",
                     "Грузовое судно вошло в гавань."):
            with self.subTest(maritime=text):
                self.assertIn("cargo ship", visual_intent(text, VISUAL_TERMS)["visual_query"])

    def test_reporting_references_preserve_shipping_without_inventing_speech(self):
        previous = visual_intent("Судоходство через грузовые порты сократилось.", VISUAL_TERMS)
        previous = visual_intent("Часть перевозчиков перестала заходить туда.", VISUAL_TERMS, previous=previous)
        self.assertIn("cargo ship", previous["visual_query"])
        current = visual_intent("Об этом известно не только по официальным заявлениям.", VISUAL_TERMS, previous=previous)
        self.assertIn("cargo ship", current["visual_query"])
        self.assertNotIn("statement", current["visual_query"])
        self.assertEqual("none", current["person_role"])
        actual_speaker = visual_intent("Путин выступил с официальным заявлением.", VISUAL_TERMS)
        self.assertIn("press conference", actual_speaker["visual_query"])
        self.assertEqual("speaker", actual_speaker["person_role"])

    def test_unconfirmed_claim_reference_keeps_report_geography_without_active_attack(self):
        previous = visual_intent("Москва заявляла об ударах по объектам.", VISUAL_TERMS)
        previous = visual_intent("которые использовались для военных поставок.", VISUAL_TERMS, previous=previous)
        current = visual_intent("Подтвердить такие заявления независимо невозможно.", VISUAL_TERMS, previous=previous)
        self.assertIn("Russia", current["visual_query"])
        self.assertNotIn("explosion", current["visual_query"])
        self.assertNotIn("press conference", current["visual_query"])
        self.assertEqual("none", current["person_role"])

    def test_grain_is_cargo_in_loading_routes_and_competition_unless_harvesting_is_actual(self):
        for text in ("Терминалы загружают большие суда и отправляют партии зерна покупателям.",
                     "Маршрут должен принимать большие объёмы нового урожая.",
                     "Зерно конкурирует за проход с топливом и другими грузами."):
            with self.subTest(transport=text):
                current = visual_intent(text, VISUAL_TERMS)
                self.assertIn("cargo", current["visual_query"])
                self.assertNotIn("harvest", current["visual_query"])
        harvesting = visual_intent("Комбайны начали уборку урожая пшеницы.", VISUAL_TERMS)
        self.assertIn("harvest", harvesting["visual_query"])

    def test_grain_carrier_mode_uses_port_context_without_inventing_a_ship_on_roads(self):
        marine = visual_intent("Заходы зерновозов в глубоководные порты сократились.", VISUAL_TERMS)
        self.assertIn("cargo ship", marine["visual_query"])
        self.assertNotIn("harvest", marine["visual_query"])
        road = visual_intent("Зерновозы доставляют партии по автодороге.", VISUAL_TERMS)
        self.assertNotIn("cargo ship", road["visual_query"])
        self.assertIn("cargo", road["visual_query"])

    def test_warehouse_export_cargo_supplies_subject_for_tonnage_cost(self):
        previous = visual_intent("Экспорт зерна продолжается.", VISUAL_TERMS)
        current = visual_intent("где прибыль на тонне невелика,", VISUAL_TERMS, previous=previous)
        self.assertIn("warehouse", current["visual_query"])
        self.assertNotIn("harvest", current["visual_query"])

    def test_reported_unnamed_attack_claim_uses_geographic_context_not_confirmed_aftermath(self):
        reported = visual_intent("Москва заявляла об ударах по объектам, которые, по её версии, были военными.", VISUAL_TERMS)
        self.assertIn("Russia", reported["visual_query"])
        self.assertIn("government building exterior", reported["visual_query"])
        self.assertNotIn("explosion", reported["visual_query"])
        self.assertNotIn("press conference", reported["visual_query"])
        self.assertEqual("none", reported["person_role"])
        self.assertTrue(reported["illustrative_only"])
        actual = visual_intent("В городе произошёл удар, здания повреждены взрывом.", VISUAL_TERMS)
        self.assertIn("explosion", actual["visual_query"])
        named = visual_intent("Путин заявил об ударах по объектам.", VISUAL_TERMS)
        self.assertIn("press conference", named["visual_query"])
        self.assertEqual("speaker", named["person_role"])

    def test_plain_warehouse_storage_does_not_invent_fire_or_harvesting(self):
        for text in ("Склад готов принимать партии товара.", "Склады постепенно заполняются зерном."):
            with self.subTest(text=text):
                query = visual_intent(text, VISUAL_TERMS)["visual_query"]
                self.assertIn("warehouse", query)
                self.assertNotIn("fire", query)
                self.assertNotIn("emergency", query)
                self.assertNotIn("harvest", query)

    def test_explicit_warehouse_fire_keeps_fire_context(self):
        query = visual_intent("На складе начался пожар.", VISUAL_TERMS)["visual_query"]
        self.assertIn("warehouse", query)
        self.assertIn("fire", query)

    def test_generic_ship_does_not_invent_navy_while_explicit_naval_objects_remain(self):
        for text in ("Корабли продолжают путь к терминалу.",
                     "Корабль перевозит коммерческий груз.",
                     "Количество кораблей у входа сократилось."):
            with self.subTest(commercial=text):
                query = visual_intent(text, VISUAL_TERMS)["visual_query"]
                self.assertIn("ship", query)
                self.assertNotIn("navy", query)
                self.assertNotIn("military", query)
                self.assertTrue(visual_intent(text, VISUAL_TERMS)["illustrative_only"])
        for text in ("Военный корабль вышел в море.", "Патрульный катер ВМС вошёл в гавань."):
            with self.subTest(naval=text):
                query = visual_intent(text, VISUAL_TERMS)["visual_query"]
                self.assertIn("military naval", query)
                self.assertNotIn("cargo ship", query)

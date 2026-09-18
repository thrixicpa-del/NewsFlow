import importlib.util
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scriptor import bridge, config, idea_engine
from scriptor.app import ScriptorApp
from scriptor.config import NEWS_TOPICS, OpenAIKey, Settings


class IdeaParsingTests(unittest.TestCase):
    def test_title_validation_rejects_a_generic_world_crisis_without_a_story(self):
        validation = bridge.valid_idea_title("Глобальный политический кризис и международная ситуация")

        self.assertFalse(validation["valid"])
        self.assertIn("generic_topic", validation["reasons"])

    def test_newsflow_has_seventeen_default_news_directions(self):
        self.assertEqual(len(NEWS_TOPICS), 17)
        self.assertEqual(Settings().idea_topics, NEWS_TOPICS)
        self.assertIn("Иран — Ормузский пролив", NEWS_TOPICS)
        self.assertIn("Армения-Россия — охлаждение и разворот Пашиняна", NEWS_TOPICS)

    def test_parses_numbered_and_bulleted_ideas(self):
        text = '1. Первая идея\n2) «Вторая идея»\n- Третья идея\nИдея 4: Четвёртая идея'
        self.assertEqual(
            ScriptorApp._parse_ideas(text),
            ["Первая идея", "Вторая идея", "Третья идея", "Четвёртая идея"],
        )

    def test_removes_duplicates_and_empty_lines(self):
        self.assertEqual(ScriptorApp._parse_ideas("Идея\n\nИдея"), ["Идея"])


class IdeaDirectionHandoffTests(unittest.TestCase):
    def test_selected_idea_handoff_preserves_script_requirements(self):
        title = "Россия и Украина спорят о главном условии переговоров"
        item = {
            "title": title, "direction": "Россия–Украина — переговоры",
            "topic": "Главное условие переговоров", "angle": "конфликт",
            "script_requirements": ["назвать участников", "объяснить главное условие"],
        }
        settings = Settings(idea_production_items=[item])
        with patch.object(bridge, "load_settings", return_value=settings), \
             patch.object(bridge, "save_settings"), \
             patch.object(bridge, "load_session", return_value=([], [])), \
             patch.object(bridge, "save_session"), \
             patch.object(bridge, "snapshot", return_value={}):
            bridge.add_ideas_to_scenarios({"ideas": [title]})

        context = getattr(settings, "idea_scenario_context", {}).get(title)
        self.assertIsNotNone(context)
        self.assertEqual(context["script_requirements"], item["script_requirements"])

    def test_scenario_prompt_includes_production_contract(self):
        prompt = getattr(bridge, "production_item_prompt", lambda _item: "")({
            "core_event": "Стороны спорят о главном условии",
            "supporting_context": ["Переговоры идут при участии России и Украины"],
            "promised_question": "Что блокирует следующий раунд",
            "script_requirements": ["назвать участников", "объяснить условие"],
        })

        self.assertIn("Стороны спорят о главном условии", prompt)
        self.assertIn("назвать участников", prompt)

    def test_hypothetical_scenario_prompt_prohibits_reporting_forecast_as_fact(self):
        prompt = bridge.production_item_prompt({
            "framing_type": "HYPOTHETICAL",
            "core_event": "Стороны обсуждают возможные условия переговоров",
            "supporting_context": ["Реальное обсуждение условий продолжается"],
            "script_requirements": ["явно указать, что дальнейший сценарий является предположением"],
        })

        self.assertIn("предположением", prompt.casefold())
        self.assertIn("не выдавай прогноз за уже произошедшее событие", prompt.casefold())

    def test_legacy_results_are_projected_to_production_items(self):
        settings = Settings(
            idea_results=["Переговоры зашли в тупик: спор идёт вокруг главного условия"],
            idea_result_sources={
                "Переговоры зашли в тупик: спор идёт вокруг главного условия": "Россия–Украина — переговоры",
            },
        )
        migrate = getattr(bridge, "ensure_idea_production_items", lambda _settings: None)
        migrate(settings)

        items = getattr(settings, "idea_production_items", [])
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["title"], settings.idea_results[0])
        self.assertEqual(items[0]["direction"], "Россия–Украина — переговоры")
        self.assertTrue(items[0]["legacy"])
        self.assertEqual(items[0]["status"], "LEGACY")
        self.assertEqual(items[0]["factual_risk_score"], "UNKNOWN")

    def test_signal_ingestion_keeps_evidence_and_event_cluster(self):
        settings = Settings()
        ingest = getattr(bridge, "ingest_idea_signals", lambda *_args: [])
        events = ingest(settings, "youtube", [{
            "title": "Переговоры России и Украины зашли в тупик из-за условий",
            "url": "https://youtube.test/watch?v=1", "views": 100000,
            "viewsHour": 5000, "primary_entities": ["Россия", "Украина"],
            "action": "зашли в тупик", "object": "условия переговоров",
        }])

        self.assertEqual(len(settings.idea_raw_signals), 1)
        self.assertEqual(len(events), 1)
        self.assertEqual(settings.idea_events[0]["event_core"], settings.idea_raw_signals[0]["event_core"])

    def test_added_plan_topic_keeps_its_prompt_route(self):
        settings = Settings()
        with patch.object(bridge, "load_settings", return_value=settings), \
             patch.object(bridge, "save_settings"), \
             patch.object(bridge, "snapshot", return_value={}):
            bridge.add_topics_to_plan({
                "topics": ["Тема для проверки"],
                "count": 7,
                "provider": "openai",
                "requirements": "Мой обязательный формат заголовка",
            })

        self.assertEqual(settings.idea_plan, [{
            "topic": "Тема для проверки",
            "count": 7,
            "provider": "openai",
            "requirements": "Мой обязательный формат заголовка",
        }])

    def test_generation_preserves_each_vector_count_and_uses_its_saved_prompt(self):
        settings = Settings(
            openai_api_keys=[OpenAIKey(label="Тест", secret="test-key", active=True)],
            idea_plan=[
                {"topic": "Первая тема", "count": 2, "provider": "openai", "requirements": "Правило первой темы"},
                {"topic": "Вторая тема", "count": 4, "provider": "openai", "requirements": "Правило второй темы"},
            ],
        )
        prompts = []

        class FakePool:
            async def generate(self, prompt):
                prompts.append(prompt)
                prefix = "Первый" if "Первая тема" in prompt else "Второй"
                return "\n".join(f"{prefix} вариант {index}" for index in range(1, 5))

        with patch.object(bridge, "load_settings", return_value=settings), \
             patch.object(bridge, "save_settings"), \
             patch.object(bridge, "snapshot", return_value={}), \
             patch.object(bridge, "HybridTextPool", return_value=FakePool()):
            bridge.generate_ideas({"requirements": "Общее правило, которое не должно заменить личные"})

        self.assertEqual([item["count"] for item in settings.idea_plan], [2, 4])
        self.assertEqual(len(settings.idea_suggested_topics), 6)
        self.assertEqual(
            sum(settings.idea_title_metadata[title]["topic"] == "Первая тема"
                for title in settings.idea_suggested_topics),
            2,
        )
        self.assertEqual(
            sum(settings.idea_title_metadata[title]["topic"] == "Вторая тема"
                for title in settings.idea_suggested_topics),
            4,
        )
        self.assertEqual(settings.idea_results, [])
        self.assertEqual(settings.idea_production_items, [])
        self.assertTrue(any("Правило первой темы" in prompt for prompt in prompts))
        self.assertTrue(any("Правило второй темы" in prompt for prompt in prompts))
        self.assertFalse(any("Общее правило, которое не должно заменить личные" in prompt for prompt in prompts))

    def test_generation_does_not_require_legacy_three_part_formula(self):
        settings = Settings(
            openai_api_keys=[OpenAIKey(label="Тест", secret="test-key", active=True)],
            idea_plan=[{
                "topic": "Международные переговоры",
                "count": 2,
                "provider": "openai",
                "requirements": "[ПРОВОКАЦИОННЫЙ ЗАГОЛОВОК]! [ДЕЙСТВИЕ СУБЪЕКТА]! [ПОСЛЕДСТВИЕ ДЛЯ ОБЪЕКТА]!",
            }],
        )

        class FakePool:
            async def generate(self, _prompt):
                return "Почему переговоры могут зайти в тупик: у сторон остался спорный вопрос\n" \
                       "Что меняют новые условия для участников переговоров"

        with patch.object(bridge, "load_settings", return_value=settings), \
             patch.object(bridge, "save_settings"), \
             patch.object(bridge, "snapshot", return_value={}), \
             patch.object(bridge, "HybridTextPool", return_value=FakePool()):
            bridge.generate_ideas({})

        self.assertEqual(len(settings.idea_suggested_topics), 2)
        self.assertTrue(all("[" not in idea and "]" not in idea for idea in settings.idea_suggested_topics))
        self.assertTrue(all(idea.count("!") == 0 for idea in settings.idea_suggested_topics))

    def test_title_validation_rejects_long_caps_and_unfinished_templates(self):
        self.assertTrue(bridge.valid_idea_title(
            "Переговоры зашли в тупик: у сторон остался один спорный вопрос"
        )["valid"])
        self.assertFalse(bridge.valid_idea_title("А" * 101)["valid"])
        self.assertFalse(bridge.valid_idea_title("ПЕРЕГОВОРЫ ЗАШЛИ В ТУПИК И НОВЫЙ КРИЗИС НЕИЗБЕЖЕН")["valid"])
        self.assertFalse(bridge.valid_idea_title("[ХУК]! [ДЕЙСТВИЕ]! [ПОСЛЕДСТВИЕ]!")["valid"])

    def test_title_prompt_contains_the_source_event_bundle(self):
        prompt = bridge._title_generation_prompt(
            "Ормузский пролив — судоходство", "", 3, [], [{
                "event_core": "Суда меняют маршруты через Ормузский пролив",
                "primary_entities": ["Иран"], "object": "маршруты судов",
            }])

        self.assertIn("Суда меняют маршруты через Ормузский пролив", prompt)
        self.assertIn("не добавляй неподтверждённые факты", prompt)
        self.assertIn("framing_type", prompt)

    def test_candidate_selection_skips_recent_opening_and_keeps_metadata(self):
        selected = bridge.select_idea_title_candidates(
            "Международные переговоры",
            [
                "Переговоры зашли в тупик: у сторон остался один спорный вопрос",
                "Вот что меняют новые условия для участников переговоров",
            ],
            [{"title": "Переговоры зашли в тупик: почему стороны не смогли договориться"}],
            1,
        )

        self.assertEqual([item["title"] for item in selected], [
            "Вот что меняют новые условия для участников переговоров"
        ])
        self.assertEqual(selected[0]["char_count"], len(selected[0]["title"]))
        self.assertTrue(selected[0]["valid_length"])

    def test_candidate_metadata_preserves_v2_framing_and_information_payload(self):
        selected = bridge.select_idea_title_candidates(
            "США–Украина — переговоры",
            [{
                "topic": "Цена соглашения для Киева",
                "angle": "политическое давление",
                "title": "Трамп поднял ставки: мирная сделка может выйти боком Украине",
                "framing_type": "EDITORIAL",
                "main_consequence": "рост политической цены соглашения",
                "information_payload": {"core": "условия переговоров и цена соглашения"},
                "script_requirements": ["разделить факт и editorial трактовку"],
            }], [], 1,
        )

        self.assertEqual(selected[0]["framing_type"], "EDITORIAL")
        self.assertEqual(selected[0]["information_payload"]["core"], "условия переговоров и цена соглашения")
        self.assertEqual(selected[0]["script_requirements"], ["разделить факт и editorial трактовку"])

    def test_generation_without_evidence_keeps_requested_headlines_as_research_suggestions(self):
        settings = Settings(idea_plan=[{
            "topic": "Международные переговоры",
            "count": 2,
            "provider": "agent",
        }])
        with patch.object(bridge, "load_settings", return_value=settings), \
             patch.object(bridge, "save_settings"), \
             patch.object(bridge, "snapshot", return_value={}):
            bridge.generate_ideas({})

        self.assertEqual(settings.idea_results, [])
        self.assertEqual(len(settings.idea_suggested_topics), 2)
        self.assertEqual(settings.idea_plan, [{
            "topic": "Международные переговоры", "count": 2, "provider": "agent",
        }])
        self.assertTrue(all(
            settings.idea_title_metadata[title]["review_status"] == "NEEDS_RESEARCH"
            for title in settings.idea_suggested_topics
        ))
        self.assertEqual(settings.idea_portfolio_summary["generated"], 2)
        self.assertEqual(settings.idea_portfolio_summary["needs_research"], 2)
        self.assertEqual(settings.idea_portfolio_summary["rejected"], 0)

    def test_selected_direction_generates_suggestions_without_adding_it_to_release_plan(self):
        settings = Settings(idea_plan=[])

        class FakePool:
            async def generate(self, _prompt):
                return (
                    "США меняют тон переговоров: что это может означать для России\n"
                    "Новый шаг Вашингтона: почему Москве придётся пересчитать риски"
                )

        with patch.object(bridge, "load_settings", return_value=settings), \
             patch.object(bridge, "save_settings"), \
             patch.object(bridge, "snapshot", return_value={}), \
             patch.object(bridge, "HybridTextPool", return_value=FakePool()):
            bridge.generate_ideas({
                "topics": ["США и Россия"], "count": 2, "provider": "agent",
            })

        self.assertEqual(settings.idea_plan, [])
        self.assertEqual(len(settings.idea_suggested_topics), 2)
        self.assertEqual(settings.idea_results, [])

    def test_agent_suggestions_stay_in_proposals_and_preserve_the_existing_release_plan(self):
        settings = Settings(
            idea_topics=["Постоянное избранное"],
            idea_plan=[{"topic": "Ручной план", "count": 4, "provider": "agent"}],
        )

        class FakePool:
            async def generate(self, _prompt):
                return "Тема агента A\nТема агента B"

        with patch.object(bridge, "load_settings", return_value=settings), \
             patch.object(bridge, "save_settings"), \
             patch.object(bridge, "snapshot", return_value={}), \
             patch.object(bridge, "HybridTextPool", return_value=FakePool()):
            bridge.suggest_topics({"provider": "agent", "count": 2, "planCount": 17})

        self.assertEqual(settings.idea_topics, ["Постоянное избранное"])
        self.assertEqual(settings.idea_suggested_topics, ["Тема агента A", "Тема агента B"])
        self.assertEqual(settings.idea_plan, [{"topic": "Ручной план", "count": 4, "provider": "agent"}])

    def test_only_explicitly_selected_agent_suggestions_enter_favourites(self):
        settings = Settings(idea_topics=["Старое"], idea_suggested_topics=["Тема A", "Тема B"])
        with patch.object(bridge, "load_settings", return_value=settings), \
             patch.object(bridge, "save_settings"), \
             patch.object(bridge, "snapshot", return_value={}):
            bridge.add_suggested_topics_to_favorites({"topics": ["Тема B"]})
            bridge.delete_topics({"topics": ["Старое"]})

        self.assertEqual(settings.idea_topics, ["Тема B"])

    def test_rejecting_selected_suggestions_removes_only_those_proposals(self):
        settings = Settings(
            idea_suggested_topics=["Предложение A", "Предложение B", "Предложение C"],
            idea_plan=[{"topic": "Ручной план", "count": 4, "provider": "agent"}],
        )
        with patch.object(bridge, "load_settings", return_value=settings), \
             patch.object(bridge, "save_settings"), \
             patch.object(bridge, "snapshot", return_value={}):
            bridge.reject_suggested_topics({"topics": ["Предложение A", "Предложение C"]})

        self.assertEqual(settings.idea_suggested_topics, ["Предложение B"])
        self.assertEqual(settings.idea_plan, [{"topic": "Ручной план", "count": 4, "provider": "agent"}])

    def test_rejecting_a_suggestion_is_idempotent_and_persists_the_remaining_proposals(self):
        settings = Settings(idea_suggested_topics=["Оставить", "Отклонить"])
        with patch.object(bridge, "load_settings", return_value=settings), \
             patch.object(bridge, "save_settings") as save, \
             patch.object(bridge, "snapshot", return_value={}):
            bridge.reject_suggested_topics({"topics": ["Отклонить"]})
            bridge.reject_suggested_topics({"topics": ["Отклонить"]})

        self.assertEqual(settings.idea_suggested_topics, ["Оставить"])
        self.assertEqual(save.call_count, 2)

    def test_rejected_suggestion_does_not_return_after_an_isolated_restart(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            environment = {
                "NEWSFLOW_TEST_MODE": "1",
                "NEWSFLOW_TEST_ROOT": str(root),
                "LOCALAPPDATA": str(root),
                "NEWSFLOW_PRODUCTION_LOCALAPPDATA": str(root / "production"),
            }
            with patch.dict(os.environ, environment, clear=False), \
                 patch.object(bridge, "snapshot", return_value={}):
                config.save_settings(Settings(idea_suggested_topics=["Оставить", "Отклонить"]))
                bridge.reject_suggested_topics({"topics": ["Отклонить"]})
                restarted = config.load_settings()

        self.assertEqual(restarted.idea_suggested_topics, ["Оставить"])

    def test_reference_analysis_keeps_new_topics_in_proposals_and_preserves_plan(self):
        settings = Settings(
            idea_topics=["Избранное"],
            idea_plan=[{"topic": "Ручной план", "count": 3, "provider": "agent"}],
            idea_reference_channels=[{"label": "Референс", "url": "https://youtube.com/@reference"}],
        )

        class FakePool:
            async def generate(self, _prompt):
                return "Новая сильная тема"

        sample = [{"title": "Залетевший ролик", "url": "https://youtube.com/watch?v=1", "channel": "Референс",
                   "views": 300000, "viewsHour": 15000.0, "ageHours": 20.0}]
        with patch.object(bridge, "load_settings", return_value=settings), \
             patch.object(bridge, "save_settings"), \
             patch.object(bridge, "snapshot", return_value={}), \
             patch.object(bridge, "HybridTextPool", return_value=FakePool()), \
             patch.object(bridge, "_read_reference_channel", return_value=sample):
            bridge.analyze_idea_reference_channels({"count": 1, "planCount": 23})

        self.assertEqual(settings.idea_topics, ["Избранное"])
        self.assertEqual(settings.idea_reference_analysis, sample)
        self.assertEqual(len(settings.idea_suggested_topics), 1)
        self.assertNotEqual(settings.idea_suggested_topics[0], "Ручной план")
        self.assertEqual(settings.idea_plan, [{"topic": "Ручной план", "count": 3, "provider": "agent"}])
        self.assertEqual(len(settings.idea_raw_signals), 1)
        self.assertEqual(len(settings.idea_events), 1)

    def test_new_mp3_is_accepted_into_montage_without_starting_render(self):
        with tempfile.TemporaryDirectory() as folder:
            audio = Path(folder) / "voice.mp3"
            audio.write_bytes(b"test")
            settings = Settings(voice_scenario_outputs={"1": str(audio)}, montage_task_statuses={
                "0": {"title": "Тема", "scenarioIndex": 0, "status": "Новый MP3", "timeline": []}
            })
            with patch.object(bridge, "load_settings", return_value=settings), \
                 patch.object(bridge, "save_settings"), \
                 patch.object(bridge, "snapshot", return_value={}), \
                 patch.object(bridge, "load_session", return_value=(["Тема"], [])):
                bridge.enqueue_montage_audio({"indices": [0]})

            task = settings.montage_task_statuses["0"]
            self.assertEqual(task["status"], "Готов к монтажу")
            self.assertEqual(task["progress"], 0)
            self.assertNotIn("Рендер", task["phase"])


class IdeaProductionEngineTests(unittest.TestCase):
    def test_production_engine_module_exists(self):
        self.assertIsNotNone(importlib.util.find_spec("scriptor.idea_engine"))

    def test_rejects_abstract_bait_and_accepts_scriptable_item(self):
        event = {
            "event_id": "evt_negotiations",
            "event_core": "Переговоры зашли в тупик из-за главного условия",
            "primary_entities": ["Россия", "Украина"],
            "action": "обсуждают",
            "object": "главное условие переговоров",
            "event_family": "diplomacy",
            "geography": ["Украина"],
            "confidence": 0.9,
        }
        build = getattr(idea_engine, "build_production_item", lambda *_args: None)
        rejected = build(
            {"direction": "Россия–Украина — переговорный процесс", "topic": "Условия переговоров", "angle": "конфликт"},
            "Ситуация изменилась",
            [event],
        )
        accepted = build(
            {"direction": "Россия–Украина — переговорный процесс", "topic": "Главное условие переговоров", "angle": "конфликт"},
            "Переговоры зашли в тупик: спор идёт вокруг главного условия",
            [event],
        )

        self.assertIsNone(rejected)
        self.assertIsNotNone(accepted)
        self.assertEqual(accepted["char_count"], len(accepted["title"]))
        self.assertGreaterEqual(accepted["scriptability_score"], 60)
        self.assertEqual(accepted["event_ids"], ["evt_negotiations"])

    def test_unsourced_factual_claim_is_not_a_production_item(self):
        build = getattr(idea_engine, "build_production_item", lambda *_args: None)
        item = build(
            {"direction": "Россия–Украина — переговорный процесс", "topic": "Условия переговоров", "angle": "конфликт"},
            "Россия и Украина сорвали новый раунд переговоров из-за главного условия",
            [],
        )

        self.assertIsNone(item)

    def test_hypothetical_requires_visible_uncertainty_and_forecast_contract(self):
        event = {
            "event_id": "evt_moscow_response",
            "event_core": "Москва обсуждает варианты ответа после нового давления",
            "primary_entities": ["Москва"],
            "action": "обсуждает", "object": "варианты ответа",
            "event_family": "diplomacy", "geography": ["Россия"],
        }
        seed = {
            "direction": "Россия — ответ на внешнее давление",
            "topic": "Варианты ответа Москвы",
            "angle": "возможная эскалация",
            "framing_type": "HYPOTHETICAL",
        }
        rejected = idea_engine.build_production_item(
            seed, "Москва нанесла новый удар после внешнего давления", [event]
        )
        accepted = idea_engine.build_production_item(
            seed, "Что будет, если Москва решится на новый ответ после давления", [event]
        )

        self.assertIsNone(rejected)
        self.assertEqual(accepted["framing_type"], "HYPOTHETICAL")
        self.assertIn("сценарий является предположением", " ".join(accepted["script_requirements"]))

    def test_editorial_grounding_handles_russian_word_inflection(self):
        event = {
            "event_id": "evt_pressure",
            "event_core": "Россия и Украина обсуждают условия возможного соглашения после нового давления",
            "primary_entities": ["Россия", "Украина"], "action": "обсуждают",
            "object": "условия соглашения", "geography": ["Украина"],
        }
        item = idea_engine.build_production_item({
            "direction": "Россия–Украина — переговоры", "topic": "Цена возможного соглашения",
            "angle": "влияние давления", "framing_type": "HYPOTHETICAL",
        }, "Может ли новое давление приблизить соглашение России и Украины?", [event])

        self.assertIsNotNone(item)
        self.assertEqual(item["framing_type"], "HYPOTHETICAL")

    def test_editorial_keeps_event_but_records_creative_amplification(self):
        event = {
            "event_id": "evt_talks",
            "event_core": "Трамп и Зеленский обсуждают условия переговоров",
            "primary_entities": ["Трамп", "Зеленский"],
            "action": "обсуждают", "object": "условия переговоров",
            "event_family": "diplomacy", "geography": ["Украина"],
        }
        item = idea_engine.build_production_item({
            "direction": "США–Украина — переговоры",
            "topic": "Цена соглашения для Киева",
            "angle": "политическая цена и давление",
            "framing_type": "EDITORIAL",
        }, "Трамп поднял ставки: мирная сделка может выйти боком Украине", [event])

        self.assertEqual(item["framing_type"], "EDITORIAL")
        self.assertIn(item["factual_risk_score"], {"LOW", "MEDIUM", "HIGH"})
        self.assertGreater(item["creative_amplification_score"], 0)

    def test_low_cis_relevance_is_metadata_not_a_production_veto(self):
        event = {
            "event_id": "evt_india_tax", "event_core": "Индия изменила технический налоговый индекс",
            "primary_entities": ["Индия"], "action": "изменила", "object": "налоговый индекс",
            "event_family": "economy", "geography": ["Индия"],
        }
        item = idea_engine.build_production_item({
            "direction": "Индийская экономика", "topic": "Налоговый индекс Индии", "angle": "техническая реформа",
            "framing_type": "EDITORIAL",
        }, "Индия изменила налоговый индекс: что происходит с технической реформой", [event])

        self.assertIsNotNone(item)
        self.assertLess(item["cis_audience_relevance_score"], 50)

    def test_plain_confirmed_news_cannot_receive_exceptional_click_score(self):
        event = {
            "event_id": "evt_border", "event_core": "Польша обсуждает ужесточение контроля на границе с Беларусью",
            "primary_entities": ["Беларусь", "Польша"], "action": "обсуждает ужесточение",
            "object": "контроль на границе", "geography": ["Беларусь", "Польша"],
        }
        item = idea_engine.build_production_item({
            "direction": "Беларусь–Польша — граница", "topic": "Контроль на границе",
            "angle": "информационное сообщение", "framing_type": "FACTUAL",
        }, "Польша обсуждает ужесточение контроля на границе с Беларусью", [event])

        self.assertLessEqual(item["click_score"], 70)
        self.assertLess(item["emotional_stakes_score"], 60)
        self.assertLess(item["creative_amplification_score"], 70)

    def test_editorial_contract_removes_model_neutrality_instruction(self):
        event = {
            "event_id": "evt_talks", "event_core": "Россия и Украина обсуждают условия соглашения",
            "primary_entities": ["Россия", "Украина"], "action": "обсуждают",
            "object": "условия соглашения", "geography": ["Украина"],
        }
        item = idea_engine.build_production_item({
            "direction": "Россия–Украина — переговоры", "topic": "Цена соглашения",
            "angle": "политическая цена", "framing_type": "EDITORIAL",
            "script_requirements": ["Сохранять нейтральный тон к сторонам"],
        }, "Переговоры становятся ловушкой: кто заплатит цену соглашения", [event])

        self.assertNotIn("Сохранять нейтральный тон к сторонам", item["script_requirements"])
        self.assertIn("агрессивную редакционную трактовку", " ".join(item["script_requirements"]))

    def test_hypothetical_needs_only_grounded_base_event_not_future_lexical_match(self):
        event = {
            "event_id": "evt_talks", "event_core": "Россия и Украина обсуждают условия соглашения",
            "primary_entities": ["Россия", "Украина"], "action": "обсуждают",
            "object": "условия соглашения", "geography": ["Украина"],
        }
        item = idea_engine.build_production_item({
            "direction": "Россия–Украина — переговоры", "topic": "Возможный ультиматум США",
            "angle": "срыв следующего раунда", "framing_type": "HYPOTHETICAL",
        }, "Что будет, если США поставят сторонам новый ультиматум", [event])

        self.assertIsNotNone(item)
        self.assertEqual(item["framing_type"], "HYPOTHETICAL")

    def test_ormuz_canonical_cis_signals_are_scored_as_direct_relevance(self):
        event = {
            "event_id": "evt_ormuz", "event_core": "Иран усилил контроль над судоходством в Ормузском проливе",
            "primary_entities": ["Иран"], "action": "усилил контроль",
            "object": "судоходство", "geography": ["Ормузский пролив"],
        }
        audience = idea_engine.assess_cis_audience({
            "direction": "Ормуз — морские маршруты", "topic": "Риски судоходства",
            "angle": "рост стоимости страховки", "framing_type": "EDITORIAL",
        }, [event])

        self.assertGreaterEqual(audience["cis_audience_relevance_score"], 50)
        self.assertIn("снг-повестк", audience["why_cis_audience_cares"].casefold())

    def test_hook_family_uses_editorial_concept_not_only_punctuation(self):
        classify = getattr(idea_engine, "classify_hook_family", lambda _title, _seed=None: "")
        self.assertEqual(classify("Варшава повышает ставки: граница становится рычагом давления"), "PRESSURE")
        self.assertEqual(classify("Что будет, если переговоры окончательно сорвутся"), "WHAT_IF")

    def test_question_limit_rewrites_strong_second_question_before_rejecting(self):
        talks = {
            "event_id": "evt_talks", "event_core": "Россия и Украина обсуждают условия соглашения",
            "primary_entities": ["Россия", "Украина"], "action": "обсуждают",
            "object": "условия соглашения", "geography": ["Украина"],
        }
        border = {
            "event_id": "evt_border", "event_core": "Польша обсуждает ужесточение контроля на границе с Беларусью",
            "primary_entities": ["Беларусь", "Польша"], "action": "обсуждает ужесточение",
            "object": "контроль на границе", "geography": ["Беларусь", "Польша"],
        }
        items, summary = idea_engine.select_production_portfolio([
            {"direction": "Россия–Украина — переговоры", "topic": "Цена соглашения", "angle": "политическая ловушка",
             "title": "Что будет, если переговоры окончательно сорвутся?", "framing_type": "HYPOTHETICAL",
             "event_ids": ["evt_talks"], "information_payload": {"core": "последствия срыва переговоров"}},
            {"direction": "Беларусь–Польша — граница", "topic": "Закрытие границы", "angle": "ответ Варшавы",
             "title": "Что будет, если Польша полностью закроет границу с Беларусью?", "framing_type": "HYPOTHETICAL",
             "event_ids": ["evt_border"], "information_payload": {"core": "сценарий закрытия границы"}},
        ], [talks, border], requested_count=5)

        self.assertEqual(len(items), 2)
        self.assertEqual(sum("?" in item["title"] for item in items), 1)
        self.assertFalse(any(item["reason"] == "question limit" for item in summary["rejected"]))

    def test_related_signals_cluster_and_saturated_angle_is_warned(self):
        make_signal = getattr(idea_engine, "normalise_signal", lambda *_args, **_kwargs: {})
        cluster_events = getattr(idea_engine, "cluster_events", lambda _signals: [])
        assess = getattr(idea_engine, "assess_direction", lambda *_args, **_kwargs: {})
        signals = [
            make_signal("youtube", {
                "title": "Переговоры России и Украины зашли в тупик из-за условий",
                "views": 200000, "viewsHour": 10000, "ageHours": 20,
                "primary_entities": ["Россия", "Украина"], "action": "зашли в тупик",
                "object": "условия переговоров", "geography": ["Украина"],
            }),
            make_signal("reference", {
                "title": "Главное условие сорвало новый раунд переговоров России и Украины",
                "views": 120000, "viewsHour": 8000, "ageHours": 18,
                "primary_entities": ["Россия", "Украина"], "action": "сорвало",
                "object": "раунд переговоров", "geography": ["Украина"],
            }),
        ]
        events = cluster_events(signals)
        self.assertEqual(len(events), 1)
        assessment = assess(events[0], [{"angle_family": "конфликт", "event_ids": [events[0]["event_id"]]}])
        self.assertGreater(assessment["demand_score"], 0)
        self.assertGreater(assessment["competition_score"], 0)
        self.assertGreater(assessment["angle_saturation"], 0)
        self.assertIn(assessment["topic_potential"], {"high", "medium", "low"})

    def test_portfolio_returns_deficit_instead_of_topic_rewordings(self):
        event = {
            "event_id": "evt_conditions", "event_core": "Россия и Украина спорят о главном условии переговоров",
            "primary_entities": ["Россия", "Украина"], "action": "спорят",
            "object": "главное условие переговоров", "geography": ["Украина"],
            "demand_inputs": {"views_hour": 9000, "views": 200000}, "source_signal_ids": ["sig_1"],
        }
        generate = getattr(idea_engine, "select_production_portfolio", lambda *_args, **_kwargs: ([], {}))
        items, summary = generate([
            {"direction": "Россия–Украина — переговоры", "topic": "Главное условие переговоров", "angle": "конфликт",
             "title": "Россия и Украина спорят о главном условии переговоров"},
            {"direction": "Россия–Украина — переговоры", "topic": "Спор вокруг главного условия", "angle": "конфликт",
             "title": "Переговоры России и Украины упёрлись в главное условие"},
        ], [event], requested_count=2)

        self.assertEqual(len(items), 1)
        self.assertEqual(summary["deficit"], 1)
        self.assertEqual(summary["rejected"][0]["reason"], "production_duplicate")

    def test_same_event_does_not_keep_angle_only_variants(self):
        event = {
            "event_id": "evt_ormuz", "event_core": "Суда меняют маршруты через Ормузский пролив",
            "primary_entities": ["Иран"], "action": "меняют", "object": "маршруты судов",
            "geography": ["Ормузский пролив"], "source_signal_ids": ["sig_ormuz"],
        }
        items, summary = idea_engine.select_production_portfolio([
            {"direction": "Ормуз — риски для российского экспорта", "topic": "Маршруты судов через Ормуз", "angle": "логистика",
             "title": "Суда меняют маршруты через Ормуз: что это значит для российского экспорта"},
            {"direction": "Ормуз — риски для российского экспорта", "topic": "Маршруты судов через Ормуз", "angle": "страховые риски",
             "title": "Страховые риски в Ормузе растут: как это бьёт по российскому экспорту"},
        ], [event], requested_count=2)

        self.assertEqual(len(items), 1)
        self.assertEqual(summary["deficit"], 1)
        self.assertEqual(summary["rejected"][0]["reason"], "production_duplicate")

    def test_same_information_payload_is_rejected_even_with_different_wording(self):
        event = {
            "event_id": "evt_one_condition",
            "event_core": "Россия и Украина спорят о главном условии переговоров",
            "primary_entities": ["Россия", "Украина"], "action": "спорят",
            "object": "главное условие переговоров", "geography": ["Украина"],
        }
        items, summary = idea_engine.select_production_portfolio([
            {
                "direction": "Россия–Украина — переговоры", "topic": "Главное условие переговоров",
                "angle": "позиция сторон", "angle_family": "позиции",
                "title": "Россия и Украина спорят о главном условии переговоров",
                "information_payload": {"core": "спор вокруг главного условия переговоров"},
            },
            {
                "direction": "Россия–Украина — переговоры", "topic": "Цена главного условия",
                "angle": "цена соглашения", "angle_family": "цена",
                "title": "Украина спорит: Россия требует ключевой пункт сделки",
                "information_payload": {"core": "спор вокруг главного условия переговоров"},
            },
        ], [event], requested_count=2)

        self.assertEqual(len(items), 1)
        self.assertEqual(summary["deficit"], 1)
        self.assertEqual(summary["rejected"][0]["reason"], "production_duplicate")

    def test_narrow_event_bundle_keeps_only_the_strongest_script_concept(self):
        event = {
            "event_id": "evt_border", "event_core": "Польша обсуждает ужесточение контроля на границе с Беларусью после инцидентов",
            "primary_entities": ["Беларусь", "Польша"], "action": "обсуждает ужесточение",
            "object": "контроль на границе", "geography": ["Беларусь", "Польша"],
        }
        candidates = [
            {"direction": "Беларусь–Польша — граница", "topic": "Цена контроля", "angle": "давление на Минск",
             "title": "Граница под давлением: Польша готовит жёсткий ответ Беларуси", "macro_event_id": "macro_border",
             "information_payload": {"core": "политическая цена усиления контроля"},
             "script_requirements": ["разобрать цену решения для Минска"]},
            {"direction": "Беларусь–Польша — граница", "topic": "Риск для перевозок", "angle": "логистические потери",
             "title": "Польша ужесточает контроль: кому на границе станет дороже", "macro_event_id": "macro_border",
             "information_payload": {"core": "последствия контроля для перевозок"},
             "script_requirements": ["объяснить, как новый контроль меняет перевозки"]},
            {"direction": "Беларусь–Польша — граница", "topic": "Пограничный торг", "angle": "политический сигнал",
             "title": "Варшава повышает ставки: граница с Беларусью становится рычагом давления", "macro_event_id": "macro_border",
             "information_payload": {"core": "граница как политический рычаг"},
             "script_requirements": ["объяснить политический сигнал Варшавы"]},
        ]

        items, summary = idea_engine.select_production_portfolio(candidates, [event], requested_count=3)

        self.assertEqual(len(items), 1)
        self.assertEqual(summary["rejected"][0]["reason"], "production_duplicate")
        self.assertIn("script_overlap", summary["rejected"][0])
        self.assertIn("event_bundle_overlap", summary["rejected"][0])
        self.assertIn("payload_overlap", summary["rejected"][0])

    def test_independently_evidenced_subevent_can_be_second_item_in_macro_bundle(self):
        border = {
            "event_id": "evt_border", "event_core": "Польша обсуждает ужесточение контроля на границе с Беларусью",
            "primary_entities": ["Беларусь", "Польша"], "action": "обсуждает ужесточение",
            "object": "контроль на границе", "geography": ["Беларусь", "Польша"],
        }
        cargo = {
            "event_id": "evt_cargo", "event_core": "Перевозчики меняют маршруты после задержек на границе Беларуси и Польши",
            "primary_entities": ["Беларусь", "Польша", "перевозчики"], "action": "меняют маршруты",
            "object": "маршруты перевозчиков", "geography": ["Беларусь", "Польша"],
        }
        candidates = [
            {"direction": "Беларусь–Польша — граница", "topic": "Политическое давление", "angle": "контроль границы",
             "title": "Польша усиливает контроль на границе с Беларусью: что меняется", "macro_event_id": "macro_border",
             "event_ids": ["evt_border"],
             "information_payload": {"core": "решение Польши усилить контроль"}},
            {"direction": "Беларусь–Польша — граница", "topic": "Цена задержек", "angle": "удар по перевозчикам",
             "title": "Задержки на границе меняют маршруты перевозчиков между Беларусью и Польшей", "macro_event_id": "macro_border",
             "event_ids": ["evt_cargo"],
             "information_payload": {"core": "реакция перевозчиков на задержки", "subevent": "маршруты"}},
        ]

        items, summary = idea_engine.select_production_portfolio(candidates, [border, cargo], requested_count=2)

        self.assertEqual(len(items), 2)
        self.assertEqual(summary["deficit"], 0)

    def test_portfolio_exposes_diversity_breakdown_for_real_batch_review(self):
        event = {
            "event_id": "evt_ormuz", "event_core": "Иран усилил контроль над судоходством в Ормузском проливе",
            "primary_entities": ["Иран"], "action": "усилил контроль", "object": "судоходство",
            "geography": ["Ормузский пролив"], "source_signal_ids": ["sig_ormuz"],
        }
        items, summary = idea_engine.select_production_portfolio([{
            "direction": "Ормуз — риски для российского экспорта", "topic": "Контроль над маршрутом", "angle": "рост рисков",
            "title": "Иран усилил контроль в Ормузе: риски для российского экспорта растут",
            "framing_type": "EDITORIAL", "macro_event_id": "macro_ormuz",
        }], [event], requested_count=1)

        self.assertEqual(len(items), 1)
        self.assertEqual(summary["diversity"]["framing_types"], {"EDITORIAL": 1})
        self.assertEqual(summary["diversity"]["macro_events"], {"macro_ormuz": 1})
        self.assertEqual(summary["diversity"]["geographies"], {"Ормузский пролив": 1})

    def test_low_cis_relevance_is_not_a_portfolio_rejection_reason(self):
        event = {
            "event_id": "evt_india_tax", "event_core": "Индия изменила технический налоговый индекс",
            "primary_entities": ["Индия"], "action": "изменила", "object": "налоговый индекс",
            "geography": ["Индия"], "source_signal_ids": ["sig_india"],
        }
        items, summary = idea_engine.select_production_portfolio([{
            "direction": "Индийская экономика", "topic": "Налоговый индекс Индии", "angle": "техническая реформа",
            "title": "Индия изменила налоговый индекс: что происходит с технической реформой",
        }], [event], requested_count=1)

        self.assertEqual(len(items), 1)
        self.assertEqual(summary["rejected"], [])
        self.assertLess(items[0]["cis_audience_relevance_score"], 50)


class IdeaPersistenceTests(unittest.TestCase):
    def test_selected_favourite_deletes_persist_without_resurrection_or_duplicate(self):
        """The current add/delete commands retain only the explicitly surviving topics."""
        with tempfile.TemporaryDirectory() as folder, \
             patch.object(config, "app_data_root", return_value=Path(folder)), \
             patch.object(bridge, "snapshot", return_value={}):
            config.save_settings(Settings(idea_topics=["Одна", "Две", "Три"]))

            bridge.add_topic({"topic": "Четыре"})
            bridge.add_topic({"topic": "четыре"})
            bridge.delete_topics({"topics": ["Две"]})
            after_single = config.load_settings()
            self.assertEqual(after_single.idea_topics, ["Одна", "Три", "Четыре"])

            bridge.delete_topics({"topics": ["Одна", "Три"]})
            after_multi = config.load_settings()
            self.assertEqual(after_multi.idea_topics, ["Четыре"])

            # A new runtime load must neither restore deleted rows nor duplicate the survivor.
            after_restart = config.load_settings()
            self.assertEqual(after_restart.idea_topics, ["Четыре"])

    def test_active_session_context_is_projected_into_one_production_item(self):
        """A surviving scenario cannot lose its durable ProductionItem identity."""
        item = {"id": "pi-current", "title": "Текущая тема", "topic": "Текущая тема"}
        settings = Settings(idea_scenario_context={"Текущая тема": item})

        changed = bridge.ensure_idea_production_items(
            settings,
            active_titles=["Текущая тема"],
        )

        self.assertTrue(changed)
        self.assertEqual(settings.idea_production_items, [item])

    def test_tombstoned_production_item_is_hidden_immediately_after_reload(self):
        """A stale on-disk item must not appear before its next explicit save."""
        deleted = {"id": "pi-deleted", "title": "Удалённая тема"}
        with tempfile.TemporaryDirectory() as folder, \
             patch.object(config, "app_data_root", return_value=Path(folder)):
            settings_path = config.config_path()
            settings_path.parent.mkdir(parents=True, exist_ok=True)
            settings_path.write_text(__import__("json").dumps({
                "idea_production_items": [deleted],
                "idea_deleted_production_ids": ["pi-deleted"],
            }), encoding="utf-8")
            restored = config.load_settings()

        self.assertEqual(restored.idea_production_items, [])
        self.assertEqual(restored.idea_deleted_production_ids, ["pi-deleted"])

    def test_deleted_production_id_is_not_restored_by_a_stale_settings_save(self):
        """A stale worker must not revive a Topic after its durable ID was deleted."""
        deleted = {"id": "pi-deleted", "title": "Удалённая тема"}
        with tempfile.TemporaryDirectory() as folder, \
             patch.object(config, "app_data_root", return_value=Path(folder)):
            config.save_settings(Settings(idea_production_items=[deleted]))
            config.save_settings(Settings(
                idea_production_items=[deleted],
                idea_deleted_production_ids=["pi-deleted"],
            ))
            restored = config.load_settings()

        self.assertEqual(restored.idea_production_items, [])
        self.assertEqual(restored.idea_deleted_production_ids, ["pi-deleted"])

    def test_production_contract_survives_save_and_reload(self):
        item = {
            "direction": "Ормузский пролив — торговые риски",
            "topic": "Давление на судоходство",
            "angle": "влияние на мировую торговлю",
            "title": "Давление в Ормузском проливе меняет риски для мировой торговли",
            "event_ids": ["evt_ormuz"],
            "supporting_context": ["Суда меняют маршрут из-за роста рисков"],
            "script_requirements": ["назвать участников", "объяснить риск для маршрутов"],
            "click_score": 82,
            "novelty_score": 91,
            "scriptability_score": 86,
            "char_count": 68,
            "hook_family": "event",
            "framing_type": "EDITORIAL",
            "factual_risk_score": "MEDIUM",
            "cis_audience_relevance_score": 82,
            "why_cis_audience_cares": "Торговые риски касаются поставок и цен в регионе.",
            "emotional_stakes_score": 74,
            "creative_amplification_score": 69,
            "direction_fit_score": 88,
            "main_consequence": "рост стоимости и риска маршрутов",
            "information_payload": {"event_core": "Суда меняют маршрут", "object": "маршруты"},
            "status": "APPROVED",
        }
        settings = Settings(
            idea_raw_signals=[{"signal_id": "sig_ormuz", "title": "Суда меняют маршрут"}],
            idea_events=[{"event_id": "evt_ormuz", "event_core": "Суда меняют маршрут"}],
            idea_production_items=[item],
            idea_rejected_items=[{"candidate": {"title": "Ситуация изменилась"}, "reason": "vague"}],
            idea_portfolio_summary={"requested": 2, "accepted": 1, "deficit": 1},
            idea_scenario_context={item["title"]: item},
        )
        with tempfile.TemporaryDirectory() as folder, \
             patch.object(config, "app_data_root", return_value=Path(folder)):
            config.save_settings(settings)
            restored = config.load_settings()

        self.assertEqual(restored.idea_production_items, [item])
        self.assertEqual(restored.idea_events, settings.idea_events)
        self.assertEqual(restored.idea_rejected_items, settings.idea_rejected_items)
        self.assertEqual(restored.idea_scenario_context[item["title"]]["angle"], item["angle"])


if __name__ == "__main__":
    unittest.main()

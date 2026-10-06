import asyncio
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


class BrowserTopicScenarioContractTests(unittest.TestCase):
    def test_message_uses_only_operator_text_plus_dynamic_topic_and_length(self):
        """The fixed envelope must not silently add an editorial brief."""
        from scriptor.browser_topic_scenarios import (
            BrowserScenarioSettings,
            BrowserTopicTask,
            build_browser_message,
        )

        message = build_browser_message(
            BrowserScenarioSettings(
                companion_prompt="Пиши только готовый текст.",
                minimum_chars=12_345,
                maximum_chars=16_789,
            ),
            BrowserTopicTask("production-42", "Точная тема из очереди"),
        )

        self.assertEqual(
            message,
            "Пиши только готовый текст.\n\n"
            "ТЕМА:\nТочная тема из очереди\n\n"
            "ОБЪЁМ: 12 345–16 789 символов.\n\n"
            "Создай и прикрепи готовый сценарий как UTF-8 файл .txt. "
            "Не добавляй текста вне вложенного файла.\n\n"
            "Выдай только готовый txt.",
        )
        self.assertNotIn("Не указывай дату", message)

    def test_downloaded_txt_payload_preserves_original_newlines(self):
        from scriptor.browser_topic_scenarios import normalize_browser_response

        payload = "Первая строка\r\nВторая строка\r\n"
        self.assertEqual(normalize_browser_response(payload), payload)

    def test_id_bound_range_and_extra_prompt_are_added_without_queue_position(self):
        from scriptor.browser_topic_scenarios import (
            BrowserScenarioSettings,
            BrowserTopicTask,
            build_browser_message,
        )

        settings = BrowserScenarioSettings(
            companion_prompt="Общий prompt.",
            minimum_chars=12_000,
            maximum_chars=18_000,
            length_overrides={"production-b": {"minimum_chars": 2_000, "maximum_chars": 3_000}},
            additional_prompt_overrides={"production-b": "Дополнение только для этой темы."},
        )
        # `queue_index` is deliberately unrelated to the override identity.
        message = build_browser_message(settings, BrowserTopicTask("production-b", "Тема B", queue_index=99))

        self.assertIn("Общий prompt.", message)
        self.assertIn("Дополнение только для этой темы.", message)
        self.assertIn("ОБЪЁМ: 2 000–3 000 символов.", message)
        self.assertNotIn("12 000–18 000", message)

    def test_builds_message_from_topic_and_ui_length_not_from_operator_prompt(self):
        from scriptor.browser_topic_scenarios import (
            BrowserScenarioSettings,
            BrowserTopicTask,
            build_browser_message,
        )

        settings = BrowserScenarioSettings(
            project_url="https://chatgpt.com/g/example/project",
            requirements_mode="text",
            requirements_text="Пиши прямой новостной текст без литературности.",
            companion_prompt="Не добавляй дату, приветствие и служебные пояснения.",
            minimum_chars=12_000,
            maximum_chars=18_000,
        )
        task = BrowserTopicTask(
            production_item_id="topic-immutable-1",
            title="ТЕМА ИЗ ОЧЕРЕДИ",
        )

        message = build_browser_message(settings, task)

        self.assertIn("ТЕМА:\nТЕМА ИЗ ОЧЕРЕДИ", message)
        self.assertIn("ОБЪЁМ: 12 000–18 000 символов.", message)
        self.assertIn("Пиши прямой новостной текст без литературности.", message)
        self.assertIn("Не добавляй дату, приветствие и служебные пояснения.", message)
        self.assertTrue(message.endswith("Выдай только готовый txt."))
        self.assertNotIn("{title}", message)
        self.assertNotIn("{minimum_chars}", message)

    def test_resolves_prompt_and_url_by_production_item_not_queue_position(self):
        from scriptor.browser_topic_scenarios import (
            BrowserScenarioSettings,
            BrowserTopicTask,
            resolve_topic_route,
        )

        settings = BrowserScenarioSettings(
            project_url="https://chatgpt.com/g/default/project",
            companion_prompt="Общий текст.",
            minimum_chars=8_000,
            maximum_chars=10_000,
            prompt_overrides={"topic-b": "Только для B."},
            url_overrides={"topic-b": "https://chatgpt.com/g/b/project"},
        )
        # The number is deliberately unrelated to the durable identity.  UI
        # reordering must never select a route from it.
        task = BrowserTopicTask(production_item_id="topic-b", title="Вторая тема", queue_index=47)

        route = resolve_topic_route(settings, task)

        self.assertEqual(route.project_url, "https://chatgpt.com/g/b/project")
        self.assertEqual(route.companion_prompt, "Только для B.")

    def test_keeps_existing_scenario_out_of_browser_topic_input(self):
        from scriptor.browser_topic_scenarios import BrowserTopicTask

        task = BrowserTopicTask(
            production_item_id="topic-immutable-2",
            title="Тема для нового текста",
            existing_scenario="Старый сценарий не должен уйти в ChatGPT.",
        )

        self.assertEqual(task.browser_input_title, "Тема для нового текста")
        self.assertNotIn("Старый сценарий", task.browser_input_title)

    def test_browser_topic_settings_survive_a_safe_settings_roundtrip(self):
        from scriptor.config import Settings, load_settings, save_settings

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.dict(os.environ, {
                "NEWSFLOW_TEST_MODE": "1",
                "NEWSFLOW_TEST_ROOT": str(root / "isolated"),
                "LOCALAPPDATA": str(root / "isolated"),
                "NEWSFLOW_PRODUCTION_LOCALAPPDATA": str(root / "production"),
            }, clear=False):
                save_settings(Settings(browser_topic_scenarios={
                    "project_url": "https://chatgpt.com/g/project",
                    "requirements_mode": "text",
                    "requirements_text": "Стиль из интерфейса.",
                    "companion_prompt": "Только готовый текст.",
                    "minimum_chars": 12000,
                    "maximum_chars": 18000,
                    "concurrency": 10,
                    "length_overrides": {"topic-1": {"minimum_chars": 14000, "maximum_chars": 16000}},
                    "additional_prompt_overrides": {"topic-1": "Диапазонное дополнение."},
                    "prompt_overrides": {"topic-1": "Особый prompt."},
                    "url_overrides": {"topic-1": "https://chatgpt.com/g/one/project"},
                }))
                restored = load_settings()

        self.assertEqual(restored.browser_topic_scenarios["minimum_chars"], 12000)
        self.assertEqual(restored.browser_topic_scenarios["maximum_chars"], 18000)
        self.assertEqual(restored.browser_topic_scenarios["length_overrides"], {"topic-1": {"minimum_chars": 14000, "maximum_chars": 16000}})
        self.assertEqual(restored.browser_topic_scenarios["additional_prompt_overrides"], {"topic-1": "Диапазонное дополнение."})
        self.assertEqual(restored.browser_topic_scenarios["prompt_overrides"], {"topic-1": "Особый prompt."})
        self.assertEqual(restored.browser_topic_scenarios["url_overrides"], {"topic-1": "https://chatgpt.com/g/one/project"})

    def test_snapshot_exposes_browser_topic_settings_without_any_secret(self):
        from scriptor import bridge
        from scriptor.config import Settings, save_settings

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.dict(os.environ, {
                "NEWSFLOW_TEST_MODE": "1",
                "NEWSFLOW_TEST_ROOT": str(root / "isolated"),
                "LOCALAPPDATA": str(root / "isolated"),
                "NEWSFLOW_PRODUCTION_LOCALAPPDATA": str(root / "production"),
            }, clear=False):
                save_settings(Settings(browser_topic_scenarios={
                    "project_url": "https://chatgpt.com/g/project",
                    "companion_prompt": "Редактируемое письмо.",
                    "minimum_chars": 1000,
                    "maximum_chars": 2000,
                    "concurrency": 3,
                }))
                state = bridge.snapshot()

        self.assertEqual(state["browserTopicScenarios"]["projectUrl"], "https://chatgpt.com/g/project")
        self.assertEqual(state["browserTopicScenarios"]["concurrency"], 3)
        self.assertNotIn("secret", repr(state["browserTopicScenarios"]).casefold())

    def test_snapshot_projects_a_topic_production_id_before_any_scenario_prose_exists(self):
        from scriptor import bridge
        from scriptor.config import Settings, save_settings
        from scriptor.session import save_session

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.dict(os.environ, {
                "NEWSFLOW_TEST_MODE": "1",
                "NEWSFLOW_TEST_ROOT": str(root / "isolated"),
                "LOCALAPPDATA": str(root / "isolated"),
                "NEWSFLOW_PRODUCTION_LOCALAPPDATA": str(root / "production"),
            }, clear=False):
                save_settings(Settings(idea_production_items=[{
                    "id": "topic-id-before-prose", "title": "Тема без сценария",
                }]))
                save_session(["Тема без сценария"], [])
                state = bridge.snapshot()

        self.assertEqual(state["scenarios"][0]["productionItemId"], "topic-id-before-prose")

    def test_save_browser_topic_settings_keeps_overrides_keyed_by_production_item(self):
        from scriptor import bridge

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.dict(os.environ, {
                "NEWSFLOW_TEST_MODE": "1",
                "NEWSFLOW_TEST_ROOT": str(root / "isolated"),
                "LOCALAPPDATA": str(root / "isolated"),
                "NEWSFLOW_PRODUCTION_LOCALAPPDATA": str(root / "production"),
            }, clear=False):
                state = bridge.save_browser_topic_scenario_settings({
                    "projectUrl": "https://chatgpt.com/g/project",
                    "requirementsMode": "text",
                    "requirementsText": "Стиль.",
                    "companionPrompt": "Только итоговый текст.",
                    "minimumChars": 12000,
                    "maximumChars": 18000,
                    "concurrency": 10,
                    "lengthOverrides": {"production-17": {"minimum_chars": 14000, "maximum_chars": 16000}},
                    "additionalPromptOverrides": {"production-17": "Диапазонное дополнение."},
                    "promptOverrides": {"production-17": "Отдельный prompt."},
                    "urlOverrides": {"production-17": "https://chatgpt.com/g/other/project"},
                })

        saved = state["browserTopicScenarios"]
        self.assertEqual(saved["promptOverrides"], {"production-17": "Отдельный prompt."})
        self.assertEqual(saved["lengthOverrides"], {"production-17": {"minimum_chars": 14000, "maximum_chars": 16000}})
        self.assertEqual(saved["additionalPromptOverrides"], {"production-17": "Диапазонное дополнение."})
        self.assertEqual(saved["urlOverrides"], {"production-17": "https://chatgpt.com/g/other/project"})
        self.assertEqual(saved["concurrency"], 10)


class BrowserTopicScenarioPoolTests(unittest.IsolatedAsyncioTestCase):
    async def test_runs_topics_in_bounded_tabs_with_per_item_urls(self):
        from scriptor.browser_topic_scenarios import (
            BrowserScenarioSettings,
            BrowserTopicTask,
            run_browser_topic_tasks,
        )

        class Transport:
            def __init__(self):
                self.active = 0
                self.peak = 0
                self.calls = []

            async def generate(self, *, project_url, message, requirements_file, task):
                self.active += 1
                self.peak = max(self.peak, self.active)
                self.calls.append((project_url, message, requirements_file, task.production_item_id))
                await asyncio.sleep(0.01)
                self.active -= 1
                return f"Готовый текст: {task.title}"

        settings = BrowserScenarioSettings(
            project_url="https://chatgpt.com/g/default/project",
            companion_prompt="Только сценарий.",
            minimum_chars=1000,
            maximum_chars=2000,
            concurrency=2,
            url_overrides={"id-b": "https://chatgpt.com/g/b/project"},
        )
        transport = Transport()
        completions = await run_browser_topic_tasks(settings, [
            BrowserTopicTask("id-a", "Тема A", queue_index=10),
            BrowserTopicTask("id-b", "Тема B", queue_index=2),
            BrowserTopicTask("id-c", "Тема C", queue_index=1),
        ], transport)

        self.assertLessEqual(transport.peak, 2)
        self.assertEqual([item.production_item_id for item in completions], ["id-a", "id-b", "id-c"])
        calls = {production_id: (url, prompt) for url, prompt, _file, production_id in transport.calls}
        self.assertEqual(calls["id-b"][0], "https://chatgpt.com/g/b/project")
        self.assertEqual(calls["id-a"][0], "https://chatgpt.com/g/default/project")
        self.assertIn("ТЕМА:\nТема B", calls["id-b"][1])

    async def test_one_failed_tab_is_reported_without_replaying_another_topic(self):
        from scriptor.browser_topic_scenarios import (
            BrowserScenarioSettings,
            BrowserTopicCompletion,
            BrowserTopicFailure,
            BrowserTopicTask,
            run_browser_topic_tasks,
        )

        class Transport:
            def __init__(self):
                self.calls = []
            async def generate(self, *, project_url, message, requirements_file, task):
                self.calls.append(task.production_item_id)
                if task.production_item_id == "bad":
                    raise RuntimeError("network interrupted")
                return "Готовый текст"

        transport = Transport()
        outcomes = await run_browser_topic_tasks(BrowserScenarioSettings(
            project_url="https://chatgpt.com/g/project", companion_prompt="Только текст.",
            minimum_chars=1, maximum_chars=2, concurrency=2,
        ), [BrowserTopicTask("bad", "Ошибка"), BrowserTopicTask("good", "Успех")], transport)

        self.assertIsInstance(outcomes[0], BrowserTopicFailure)
        self.assertIsInstance(outcomes[1], BrowserTopicCompletion)
        self.assertCountEqual(transport.calls, ["bad", "good"])


class BrowserTopicBridgeTests(unittest.TestCase):
    def test_browser_topic_queue_rejects_a_second_process_owner_before_transport(self):
        from scriptor import bridge

        with tempfile.TemporaryDirectory(prefix="newsflow-browser-topic-lock-") as directory:
            root = Path(directory)
            with patch.object(bridge, "app_data_root", return_value=root):
                owner = bridge._claim_browser_topic_queue_lock()
                self.assertIsNotNone(owner)
                try:
                    with patch.object(bridge, "_generate_browser_topic_scenarios_unlocked") as run, \
                         patch.object(bridge, "snapshot", return_value={}):
                        result = bridge.generate_browser_topic_scenarios({})
                finally:
                    bridge._release_browser_topic_queue_lock(owner)

        run.assert_not_called()
        self.assertEqual(
            result["operationResult"]["kind"],
            "browser-topic-scenarios-already-running",
        )

    def test_topic_without_a_preexisting_scenario_job_gets_its_own_durable_job(self):
        from scriptor import bridge
        from scriptor.config import Settings

        settings = Settings(idea_production_items=[{"id": "topic-only-id", "title": "Только тема"}])
        titles = ["Только тема"]
        tasks, jobs = bridge._select_browser_topic_tasks(settings, titles, [], {
            "indices": [0], "productionItemIds": ["topic-only-id"],
        })

        self.assertEqual(tasks[0].browser_input_title, "Только тема")
        self.assertEqual(tasks[0].production_item_id, "topic-only-id")
        self.assertEqual(jobs[0].request.production_item_id, "topic-only-id")
        self.assertEqual(jobs[0].result, "")

    def test_browser_route_binds_the_returned_text_to_the_selected_production_item(self):
        from scriptor import bridge
        from scriptor.config import ChromeSession, Settings
        from scriptor.core import ScenarioRequest
        from scriptor.runner import Job, RunState

        with tempfile.TemporaryDirectory() as directory:
            session = ChromeSession(label="ChatGPT test", profile_id="chatgpt-test")
            settings = Settings(
                output_folder=directory,
                chrome_sessions=[session],
                browser_topic_scenarios={
                    "project_url": "https://chatgpt.com/g/project",
                    "session_id": "chatgpt-test",
                    "requirements_mode": "text",
                    "requirements_text": "Только прямой текст.",
                    "companion_prompt": "Без служебных пояснений.",
                    "minimum_chars": 10,
                    "maximum_chars": 20,
                    "concurrency": 2,
                },
            )
            titles = ["Первая тема", "Вторая тема"]
            first = Job(ScenarioRequest(0, titles[0], "legacy prompt", "prod-first"))
            second = Job(ScenarioRequest(1, titles[1], "legacy prompt", "prod-second"))
            second.result = "Старый сценарий нельзя передавать в браузер."
            saved_jobs = []

            class FakeTransport:
                def __init__(self, _session):
                    self.calls = []
                async def __aenter__(self):
                    return self
                async def __aexit__(self, *_args):
                    return None
                async def generate(self, *, project_url, message, requirements_file, task):
                    self.calls.append((project_url, message, requirements_file, task.production_item_id))
                    return "Новый\r\nтекст для первой темы\r\n"

            transport = FakeTransport(session)
            with patch.object(bridge, "load_settings", return_value=settings), \
                 patch.object(bridge, "save_settings"), \
                 patch.object(bridge, "load_session", return_value=(titles, [first, second])), \
                 patch.object(bridge, "save_session", side_effect=lambda _titles, jobs: saved_jobs.append(list(jobs))), \
                 patch.object(bridge, "ensure_idea_production_items", return_value=False), \
                 patch.object(bridge, "snapshot", return_value={}), \
                 patch.object(bridge, "ChatGPTBrowserClient", return_value=transport):
                result = bridge.generate_browser_topic_scenarios({
                    "indices": [0], "productionItemIds": ["prod-first"],
                }, transport_factory=lambda _session: transport)

            self.assertEqual(result["operationResult"]["count"], 1)
            self.assertEqual(len(transport.calls), 1)
            self.assertIn("ТЕМА:\nПервая тема", transport.calls[0][1])
            self.assertNotIn("Старый сценарий", transport.calls[0][1])
            final = saved_jobs[-1]
            self.assertEqual(final[0].state, RunState.DONE)
            self.assertEqual(final[0].result, "Новый\r\nтекст для первой темы\r\n")
            self.assertEqual(final[1].result, "Старый сценарий нельзя передавать в браузер.")
            exports = list((Path(directory) / "ChatGPT браузер").glob("*.txt"))
            self.assertEqual(len(exports), 1)
            self.assertEqual(
                exports[0].read_bytes(),
                "Новый\r\nтекст для первой темы\r\n".encode("utf-8"),
            )
            self.assertEqual(result["operationResult"]["folder"], str(Path(directory) / "ChatGPT браузер"))

    def test_browser_route_never_overwrites_existing_prose_even_when_job_is_error(self):
        from scriptor import bridge
        from scriptor.config import Settings
        from scriptor.core import ScenarioRequest
        from scriptor.runner import Job, RunState

        job = Job(
            ScenarioRequest(0, "Тема", "", "prod-1"),
            RunState.ERROR,
            "Уже сохранённый оператором текст",
            "старый технический статус",
        )
        tasks, _jobs = bridge._select_browser_topic_tasks(
            Settings(), ["Тема"], [job],
            {"indices": [0], "productionItemIds": ["prod-1"]},
        )

        self.assertEqual(tasks, [])
        self.assertEqual(job.result, "Уже сохранённый оператором текст")

    def test_browser_completion_commits_by_production_item_after_queue_reorder(self):
        from scriptor import bridge
        from scriptor.config import ChromeSession, Settings
        from scriptor.core import ScenarioRequest
        from scriptor.runner import Job, RunState

        with tempfile.TemporaryDirectory() as directory:
            session = ChromeSession(label="ChatGPT test", profile_id="chatgpt-test")
            settings = Settings(
                output_folder=directory,
                chrome_sessions=[session],
                browser_topic_scenarios={
                    "project_url": "https://chatgpt.com/g/project",
                    "session_id": "chatgpt-test",
                    "requirements_mode": "text",
                    "requirements_text": "Стиль.",
                    "companion_prompt": "Только текст.",
                    "minimum_chars": 10,
                    "maximum_chars": 20,
                    "concurrency": 1,
                },
            )
            initial_titles = ["Тема A", "Тема B"]
            initial_a = Job(ScenarioRequest(0, "Тема A", "", "prod-a"))
            initial_b = Job(ScenarioRequest(1, "Тема B", "", "prod-b"))
            current_titles = ["Тема B", "Тема A"]
            current_b = Job(ScenarioRequest(0, "Тема B", "", "prod-b"))
            current_a = Job(ScenarioRequest(1, "Тема A", "", "prod-a"))
            saved = []

            class Transport:
                async def __aenter__(self):
                    return self
                async def __aexit__(self, *_args):
                    return None
                async def generate(self, **_kwargs):
                    return "Ответ для A"

            with patch.object(bridge, "load_settings", return_value=settings), \
                 patch.object(
                     bridge, "load_session",
                     side_effect=[
                         (initial_titles, [initial_a, initial_b]),
                         (current_titles, [current_b, current_a]),
                     ],
                 ), \
                 patch.object(bridge, "save_session", side_effect=lambda titles, jobs: saved.append((list(titles), list(jobs)))), \
                 patch.object(bridge, "ensure_idea_production_items", return_value=False), \
                 patch.object(bridge, "snapshot", return_value={}), \
                 patch.object(bridge, "save_settings"):
                result = bridge.generate_browser_topic_scenarios(
                    {"indices": [0], "productionItemIds": ["prod-a"]},
                    transport_factory=lambda _session: Transport(),
                )

        self.assertEqual(result["operationResult"]["count"], 1)
        final_titles, final_jobs = saved[-1]
        self.assertEqual(final_titles, current_titles)
        by_id = {job.request.production_item_id: job for job in final_jobs}
        self.assertEqual(by_id["prod-a"].result, "Ответ для A")
        self.assertEqual(by_id["prod-a"].state, RunState.DONE)
        self.assertEqual(by_id["prod-b"].result, "")

    def test_browser_launch_failure_clears_this_batch_running_state(self):
        from scriptor import bridge
        from scriptor.config import ChromeSession, Settings
        from scriptor.core import ScenarioRequest
        from scriptor.runner import Job, RunState

        session = ChromeSession(label="ChatGPT test", profile_id="chatgpt-test")
        settings = Settings(
            chrome_sessions=[session],
            browser_topic_scenarios={
                "project_url": "https://chatgpt.com/g/project",
                "session_id": "chatgpt-test",
                "requirements_mode": "text",
                "requirements_text": "Стиль.",
                "companion_prompt": "Только текст.",
                "minimum_chars": 10,
                "maximum_chars": 20,
                "concurrency": 1,
            },
        )
        titles = ["Тема"]
        job = Job(ScenarioRequest(0, "Тема", "", "prod-1"))
        saved = []

        class BrokenTransport:
            async def __aenter__(self):
                raise RuntimeError("browser unavailable")
            async def __aexit__(self, *_args):
                return None

        with patch.object(bridge, "load_settings", return_value=settings), \
             patch.object(bridge, "load_session", side_effect=[(titles, [job]), (titles, [job])]), \
             patch.object(bridge, "save_session", side_effect=lambda _titles, jobs: saved.append(list(jobs))), \
             patch.object(bridge, "ensure_idea_production_items", return_value=False), \
             self.assertRaisesRegex(RuntimeError, "browser unavailable"):
            bridge.generate_browser_topic_scenarios(
                {"indices": [0], "productionItemIds": ["prod-1"]},
                transport_factory=lambda _session: BrokenTransport(),
            )

        self.assertEqual(saved[-1][0].state, RunState.ERROR)
        self.assertIn("browser unavailable", saved[-1][0].error)

    def test_browser_result_is_saved_without_length_gate(self):
        from scriptor import bridge
        from scriptor.config import ChromeSession, Settings
        from scriptor.core import ScenarioRequest
        from scriptor.runner import Job, RunState

        with tempfile.TemporaryDirectory() as directory:
            session = ChromeSession(label="ChatGPT test", profile_id="chatgpt-test")
            settings = Settings(
                output_folder=directory,
                chrome_sessions=[session],
                browser_topic_scenarios={
                    "project_url": "https://chatgpt.com/g/project",
                    "session_id": "chatgpt-test",
                    "requirements_mode": "text",
                    "requirements_text": "Стиль.",
                    "companion_prompt": "Только текст.",
                    "minimum_chars": 12000,
                    "maximum_chars": 18000,
                    "concurrency": 1,
                },
            )
            titles = ["Тема"]
            job = Job(ScenarioRequest(0, "Тема", "", "prod-1"))
            saved = []

            class Transport:
                async def __aenter__(self):
                    return self
                async def __aexit__(self, *_args):
                    return None
                async def generate(self, **_kwargs):
                    return "коротко"

            with patch.object(bridge, "load_settings", return_value=settings), \
                 patch.object(bridge, "load_session", return_value=(titles, [job])), \
                 patch.object(bridge, "save_session", side_effect=lambda _titles, jobs: saved.append(list(jobs))), \
                 patch.object(bridge, "ensure_idea_production_items", return_value=False), \
                 patch.object(bridge, "snapshot", return_value={}), \
                 patch.object(bridge, "save_settings"):
                result = bridge.generate_browser_topic_scenarios(
                    {"indices": [0], "productionItemIds": ["prod-1"]},
                    transport_factory=lambda _session: Transport(),
                )

        self.assertEqual(result["operationResult"]["count"], 1)
        final = saved[-1][0]
        self.assertEqual(final.result, "коротко")
        self.assertEqual(final.state, RunState.DONE)
        self.assertEqual(final.length_status, "")
        self.assertEqual(final.actual_chars, len("коротко"))

    def test_browser_identity_does_not_guess_between_duplicate_historical_titles(self):
        from scriptor import bridge
        from scriptor.config import Settings

        settings = Settings(idea_production_items=[
            {"id": "old-a", "title": "Одинаковая тема"},
            {"id": "old-b", "title": "Одинаковая тема"},
        ])
        with self.assertRaisesRegex(ValueError, "ProductionItem ID"):
            bridge._select_browser_topic_tasks(
                settings, ["Одинаковая тема"], [],
                {"indices": [0], "productionItemIds": ["old-a"]},
            )

    def test_browser_route_rejects_a_stale_index_to_production_item_mapping_before_browser(self):
        from scriptor import bridge
        from scriptor.config import ChromeSession, Settings
        from scriptor.core import ScenarioRequest
        from scriptor.runner import Job

        settings = Settings(chrome_sessions=[ChromeSession(label="ChatGPT", profile_id="session")])
        titles = ["Тема"]
        jobs = [Job(ScenarioRequest(0, "Тема", "", "actual-id"))]
        with (
            patch.object(bridge, "load_settings", return_value=settings),
            patch.object(bridge, "load_session", return_value=(titles, jobs)),
            patch.object(bridge, "ensure_idea_production_items", return_value=False),
            self.assertRaisesRegex(ValueError, "ProductionItem ID"),
        ):
            bridge._select_browser_topic_tasks(settings, titles, jobs, {
                "indices": [0], "productionItemIds": ["stale-id"],
            })


if __name__ == "__main__":
    unittest.main()

import asyncio
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scriptor import bridge
from scriptor.browser_topic_scenarios import (
    BrowserScenarioSettings,
    BrowserTopicFailure,
    BrowserTopicTask,
    run_browser_topic_tasks,
)
from scriptor.config import Settings, load_settings, save_settings


class BrowserTabSettingsTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory(prefix="browser-concurrency-")
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        environment = patch.dict(os.environ, {
            "NEWSFLOW_TEST_MODE": "1", "NEWSFLOW_TEST_ROOT": str(self.root / "test"),
            "LOCALAPPDATA": str(self.root / "test"),
            "NEWSFLOW_PRODUCTION_LOCALAPPDATA": str(self.root / "production"),
        })
        environment.start()
        self.addCleanup(environment.stop)

    def test_save_reload_and_runtime_keep_the_requested_concurrency(self):
        for requested in (1, 10, 84, 137):
            with self.subTest(requested=requested):
                response = bridge.save_browser_topic_scenario_settings({"concurrency": requested})
                self.assertEqual(response["browserTopicScenarios"]["concurrency"], requested)
                restored = load_settings()
                self.assertEqual(restored.browser_topic_scenarios["concurrency"], requested)
                self.assertEqual(bridge._browser_topic_settings(restored).concurrency, requested)

    def test_invalid_tab_counts_do_not_overwrite_the_saved_settings(self):
        save_settings(Settings(browser_topic_scenarios={"concurrency": 84}))
        settings_file = self.root / "test" / "NewsFlow" / "settings.json"
        before = settings_file.read_bytes()
        for invalid in (0, -1, 1.5, True, None, "", "invalid", float("nan"), float("inf")):
            with self.subTest(invalid=invalid):
                with self.assertRaisesRegex(ValueError, "вкладок"):
                    bridge.save_browser_topic_scenario_settings({"concurrency": invalid})
                self.assertEqual(settings_file.read_bytes(), before)


class BrowserTabSchedulerTests(unittest.IsolatedAsyncioTestCase):
    async def test_84_tasks_can_enter_the_transport_before_any_task_finishes(self):
        started = []
        all_started = asyncio.Event()
        release = asyncio.Event()

        class Transport:
            async def generate(self, *, project_url, message, requirements_file, task):
                started.append(task.production_item_id)
                if len(started) == 84:
                    all_started.set()
                await release.wait()
                return f"TXT {task.production_item_id}"

        tasks = [BrowserTopicTask(f"id-{index}", f"Topic {index}", 1000 - index) for index in range(84)]
        queue = asyncio.create_task(run_browser_topic_tasks(BrowserScenarioSettings(
            project_url="https://chatgpt.com/g/project", companion_prompt="Only TXT.",
            minimum_chars=1, maximum_chars=2, concurrency=84,
        ), tasks, Transport()))
        try:
            try:
                await asyncio.wait_for(all_started.wait(), timeout=1)
            except TimeoutError:
                pass
            self.assertEqual(len(started), 84, "Requested 84 tabs must not be silently clamped")
        finally:
            release.set()
            outcomes = await queue
        self.assertCountEqual(started, [task.production_item_id for task in tasks])
        self.assertEqual([(item.production_item_id, item.text) for item in outcomes],
                         [(task.production_item_id, f"TXT {task.production_item_id}") for task in tasks])

    async def test_smaller_pool_refills_on_completion_and_failure_without_misrouting(self):
        entered = [asyncio.Event() for _ in range(84)]
        releases = [asyncio.Event() for _ in range(84)]
        active = 0
        peak = 0
        calls = []

        class Transport:
            async def generate(self, *, project_url, message, requirements_file, task):
                nonlocal active, peak
                index = int(task.production_item_id.split("-")[1])
                active += 1
                peak = max(peak, active)
                calls.append(task.production_item_id)
                entered[index].set()
                try:
                    await releases[index].wait()
                    if index == 2:
                        raise RuntimeError("fixture failure")
                    return f"TXT {task.production_item_id}"
                finally:
                    active -= 1

        tasks = [BrowserTopicTask(f"id-{index}", f"Topic {index}", 1000 - index) for index in range(84)]
        queue = asyncio.create_task(run_browser_topic_tasks(BrowserScenarioSettings(
            project_url="https://chatgpt.com/g/project", companion_prompt="Only TXT.",
            minimum_chars=1, maximum_chars=2, concurrency=3,
        ), tasks, Transport()))
        try:
            await asyncio.wait_for(entered[2].wait(), 1)
            self.assertEqual(len(calls), 3)
            releases[2].set()
            await asyncio.wait_for(entered[3].wait(), 1)
            self.assertEqual(len(calls), 4)
            releases[1].set()
            await asyncio.wait_for(entered[4].wait(), 1)
            self.assertEqual(len(calls), 5)
        finally:
            for release in releases:
                release.set()
            outcomes = await queue
        self.assertEqual(peak, 3)
        self.assertEqual(len(calls), 84)
        self.assertEqual(len(set(calls)), 84)
        self.assertIsInstance(outcomes[2], BrowserTopicFailure)
        self.assertEqual(outcomes[2].production_item_id, "id-2")
        for index, outcome in enumerate(outcomes):
            if index != 2:
                self.assertEqual((outcome.production_item_id, outcome.text), (f"id-{index}", f"TXT id-{index}"))

    async def test_invalid_concurrency_is_rejected_before_transport_entry(self):
        class Transport:
            async def generate(self, **kwargs):
                raise AssertionError("Invalid settings must not enter the browser")

        for invalid in (0, -1, 1.5, True, None, "", float("nan")):
            with self.subTest(invalid=invalid), self.assertRaisesRegex(ValueError, "вкладок"):
                await run_browser_topic_tasks(BrowserScenarioSettings(
                    project_url="https://chatgpt.com/g/project", companion_prompt="Only TXT.",
                    minimum_chars=1, maximum_chars=2, concurrency=invalid,
                ), [BrowserTopicTask("id-one", "Topic")], Transport())


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
    async def test_persistence_failure_waits_for_other_tabs_without_resubmitting(self):
        from scriptor.session import SessionWriteConflictError

        calls, published = [], []

        class Transport:
            async def generate(self, *, task, **_kwargs):
                calls.append(task.production_item_id)
                if task.production_item_id == "slow":
                    await asyncio.sleep(0.01)
                return "Literal TXT"

        def publish(outcome):
            published.append(outcome.production_item_id)
            if outcome.production_item_id == "fast":
                raise SessionWriteConflictError("conflict")

        with self.assertRaisesRegex(SessionWriteConflictError, "conflict"):
            await run_browser_topic_tasks(BrowserScenarioSettings(project_url="https://chatgpt.com/g/project",
                companion_prompt="TXT", minimum_chars=1, maximum_chars=2, concurrency=2),
                [BrowserTopicTask("fast", "Fast"), BrowserTopicTask("slow", "Slow")], Transport(), on_outcome=publish)
        self.assertCountEqual(calls, ["fast", "slow"])
        self.assertEqual(published, ["fast", "slow"])

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
    def test_txt_export_uses_the_topic_name_and_never_overwrites_a_collision(self):
        with tempfile.TemporaryDirectory() as directory:
            settings = Settings(output_folder=directory)
            first = bridge._browser_topic_export_path(settings, "Точная тема", "production-1")
            self.assertEqual(first.name, "Точная тема.txt")
            first.write_bytes(b"first")
            second = bridge._browser_topic_export_path(settings, "Точная тема", "production-2")
            self.assertNotEqual(first, second)
            second.write_bytes(b"second")
            self.assertEqual(first.read_bytes(), b"first")
            self.assertTrue(second.stem.startswith("Точная тема"))

    def test_topic_filename_is_windows_safe_for_long_unicode_and_reserved_titles(self):
        with tempfile.TemporaryDirectory() as directory:
            settings = Settings(output_folder=directory)
            for title in ('CON', 'CON.notes', 'Тема 😀 / вопрос: "что дальше?"', 'Длинная тема ' * 100, '😀' * 120):
                with self.subTest(title=title[:40]):
                    target = bridge._browser_topic_export_path(settings, title, "same-id")
                    with target.open("xb") as stream:
                        stream.write(b"literal")
                    self.assertLessEqual(len(target.name), 124)
                    self.assertNotRegex(target.name, r'[<>:"/\\|?*\x00-\x1f]')
                    other = bridge._browser_topic_export_path(settings, title, "same-id")
                    self.assertNotEqual(target, other)
                    with other.open("xb") as stream:
                        stream.write(b"second")
                    self.assertEqual(target.read_bytes(), b"literal")

    def test_late_download_never_overwrites_a_manual_edit_or_recreates_a_deleted_topic(self):
        from scriptor.config import ChromeSession
        from scriptor.core import ScenarioRequest
        from scriptor.runner import Job, RunState

        for deleted in (False, True):
            with self.subTest(deleted=deleted), tempfile.TemporaryDirectory() as directory:
                settings = Settings(output_folder=directory,
                    chrome_sessions=[ChromeSession(label="Offline", profile_id="fixture")],
                    browser_topic_scenarios={"session_id": "fixture", "project_url": "https://chatgpt.com/g/project",
                        "companion_prompt": "Only TXT", "minimum_chars": 1, "maximum_chars": 2})
                initial = Job(ScenarioRequest(0, "Тема", "", "id-exact"))
                manual = Job(ScenarioRequest(0, "Тема", "", "id-exact"), RunState.DONE, "Manual wins")
                current = ([], []) if deleted else (["Тема"], [manual])

                class Transport:
                    async def __aenter__(self):
                        return self
                    async def __aexit__(self, *_args):
                        return None
                    async def generate(self, **_kwargs):
                        return "Late downloaded TXT"

                with patch.object(bridge, "load_settings", return_value=settings), \
                     patch.object(bridge, "load_session", side_effect=[(["Тема"], [initial]), current]), \
                     patch.object(bridge, "save_session") as save, \
                     patch.object(bridge, "ensure_idea_production_items", return_value=False), \
                     patch.object(bridge, "snapshot", return_value={}):
                    result = bridge.generate_browser_topic_scenarios({}, transport_factory=lambda _session: Transport())
                self.assertEqual(result["operationResult"]["count"], 0)
                self.assertEqual(save.call_count, 1)  # initial RUNNING publication only
                self.assertEqual(manual.result, "Manual wins")
                self.assertEqual(list(Path(directory).rglob("*.txt")), [])

    def test_completed_topic_is_persisted_before_another_tab_finishes(self):
        from scriptor.config import ChromeSession
        from scriptor.core import ScenarioRequest
        from scriptor.runner import Job, RunState
        from scriptor.session import load_session, save_session

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.dict(os.environ, {
                "NEWSFLOW_TEST_MODE": "1", "NEWSFLOW_TEST_ROOT": str(root / "test"),
                "LOCALAPPDATA": str(root / "test"), "NEWSFLOW_PRODUCTION_LOCALAPPDATA": str(root / "production"),
            }):
                settings = Settings(output_folder=str(root / "exports"),
                    chrome_sessions=[ChromeSession(label="Offline", profile_id="fixture")],
                    browser_topic_scenarios={"session_id": "fixture", "project_url": "https://chatgpt.com/g/project",
                        "companion_prompt": "Only TXT", "minimum_chars": 1, "maximum_chars": 2, "concurrency": 2})
                save_settings(settings)
                save_session(["Fast topic", "Slow topic"], [
                    Job(ScenarioRequest(0, "Fast topic", "", "id-fast")),
                    Job(ScenarioRequest(1, "Slow topic", "", "id-slow")),
                ])
                observations = []

                class Transport:
                    async def __aenter__(self):
                        return self
                    async def __aexit__(self, *_args):
                        return None
                    async def generate(self, *, project_url, message, requirements_file, task):
                        if task.production_item_id == "id-slow":
                            for _ in range(10):
                                await asyncio.sleep(0.01)
                                _, jobs = load_session()
                                if jobs[0].state is RunState.DONE:
                                    observations.append(jobs[0].result)
                                    break
                        return f"Literal TXT: {task.production_item_id}"

                result = bridge.generate_browser_topic_scenarios({}, transport_factory=lambda _session: Transport())
                self.assertEqual(result["operationResult"]["count"], 2)
                self.assertEqual(observations, ["Literal TXT: id-fast"])
                export = Path(result["operationResult"]["folder"]) / "Fast topic.txt"
                self.assertTrue(export.is_relative_to(root))
                self.assertEqual(export.read_bytes(), b"Literal TXT: id-fast")

    def test_session_conflict_reloads_manual_edits_without_cancelling_sibling_downloads(self):
        self._assert_session_conflict_recovery(manual_edit=True)

    def test_session_conflict_retries_commit_once_without_exporting_or_counting_twice(self):
        self._assert_session_conflict_recovery(manual_edit=False)

    def _assert_session_conflict_recovery(self, *, manual_edit):
        from scriptor.config import ChromeSession
        from scriptor.core import ScenarioRequest
        from scriptor.runner import Job, RunState
        from scriptor.session import (
            SessionWriteConflictError,
            load_session,
            save_session,
        )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.dict(os.environ, {
                "NEWSFLOW_TEST_MODE": "1", "NEWSFLOW_TEST_ROOT": str(root / "test"),
                "LOCALAPPDATA": str(root / "test"), "NEWSFLOW_PRODUCTION_LOCALAPPDATA": str(root / "production"),
            }):
                save_settings(Settings(chrome_sessions=[ChromeSession(label="Offline", profile_id="fixture")],
                    browser_topic_scenarios={"session_id": "fixture", "project_url": "https://chatgpt.com/g/project",
                        "companion_prompt": "TXT", "minimum_chars": 1, "maximum_chars": 2, "concurrency": 2}))
                save_session(["Fast", "Slow"], [Job(ScenarioRequest(0, "Fast", "", "fast")),
                                               Job(ScenarioRequest(1, "Slow", "", "slow"))])
                calls = []
                conflicted = False

                def competing_save(titles, jobs):
                    nonlocal conflicted
                    if not conflicted and jobs[0].state is RunState.DONE:
                        conflicted = True
                        current_titles, current_jobs = load_session()
                        if manual_edit:
                            current_jobs[0].result = "Manual concurrent edit"
                            current_jobs[0].state = RunState.DONE
                        else:
                            current_jobs[0].request = ScenarioRequest(0, "Fast", "Concurrent prompt edit", "fast")
                        save_session(current_titles, current_jobs)
                        raise SessionWriteConflictError("concurrent edit")
                    save_session(titles, jobs)

                class Transport:
                    async def __aenter__(self):
                        return self
                    async def __aexit__(self, *_args):
                        return None
                    async def generate(self, *, task, **_kwargs):
                        calls.append(task.production_item_id)
                        if task.production_item_id == "slow":
                            await asyncio.sleep(0.01)
                        return f"Downloaded {task.production_item_id}"

                with patch.object(bridge, "save_session", side_effect=competing_save):
                    result = bridge.generate_browser_topic_scenarios({}, transport_factory=lambda _session: Transport())
                _, jobs = load_session()
                self.assertTrue(conflicted)
                self.assertCountEqual(calls, ["fast", "slow"])
                self.assertEqual(jobs[0].result, "Manual concurrent edit" if manual_edit else "Downloaded fast")
                self.assertEqual(jobs[1].result, "Downloaded slow")
                self.assertEqual(jobs[1].state, RunState.DONE)
                self.assertEqual(result["operationResult"]["count"], 1 if manual_edit else 2)
                if not manual_edit:
                    self.assertEqual(jobs[0].request.prompt, "Concurrent prompt edit")
                    exports = list(Path(result["operationResult"]["folder"]).glob("Fast*.txt"))
                    self.assertEqual(len(exports), 1)
                    self.assertEqual(exports[0].read_bytes(), b"Downloaded fast")

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
                    "project_url": "",
                    "session_id": "chatgpt-test",
                    "requirements_mode": "text",
                    "requirements_text": "Только прямой текст.",
                    "companion_prompt": "Без служебных пояснений.",
                    "minimum_chars": 10,
                    "maximum_chars": 20,
                    "concurrency": 2,
                    "url_overrides": {"prod-first": "https://chatgpt.com/g/project"},
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
            self.assertEqual(transport.calls[0][0], "https://chatgpt.com/g/project")
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
                "Новый\r\nтекст для первой темы\r\n".encode(),
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

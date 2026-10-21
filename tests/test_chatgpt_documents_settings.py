"""Browser document settings, cancellation and persistence use disposable state."""
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from scriptor import bridge, config
from scriptor.browser_topic_scenarios import (
    BrowserScenarioSettings,
    BrowserTopicTask,
    run_browser_topic_tasks,
)
from scriptor.chatgpt_browser import ChatGPTBrowserClient


class DocumentSettingsTests(unittest.TestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        env = patch.dict(os.environ, {"LOCALAPPDATA": str(self.root)})
        env.start()
        self.addCleanup(env.stop)
        config.save_settings(config.Settings())

    def test_multiple_documents_save_reload_snapshot_runtime_and_legacy_fallback(self):
        files = [str(self.root / f"requirements-{i}.txt") for i in range(125)]
        result = bridge.save_browser_topic_scenario_settings({"requirementsMode": "file", "requirementsFiles": files, "requirementsFile": files[0]})
        self.assertEqual(result["browserTopicScenarios"]["requirementsFiles"], files)
        saved = config.load_settings()
        self.assertEqual(saved.browser_topic_scenarios["requirements_files"], files)
        self.assertEqual(list(bridge._browser_topic_settings(saved).requirements_files), files)
        bridge.save_browser_topic_scenario_settings({"requirementsMode": "file", "requirementsFile": files[0]})
        self.assertEqual(bridge.snapshot()["browserTopicScenarios"]["requirementsFiles"], files[:1])

    def test_explicit_empty_list_does_not_revive_the_old_single_path(self):
        bridge.save_browser_topic_scenario_settings({"requirementsMode": "file", "requirementsFiles": [], "requirementsFile": "stale.txt"})
        self.assertEqual(bridge.snapshot()["browserTopicScenarios"]["requirementsFiles"], [])
        runtime = bridge._browser_topic_settings(config.load_settings())
        self.assertEqual(runtime.requirements_file, "")
        self.assertEqual(runtime.requirements_files, ())

    def test_cancel_before_worker_claim_cancels_only_that_launch(self):
        bridge.cancel_browser_topic_scenarios({"batchId": "launch-a"})
        with patch.object(bridge, "_generate_browser_topic_scenarios_unlocked") as generate:
            result = bridge.generate_browser_topic_scenarios({"batchId": "launch-a"})
        generate.assert_not_called()
        self.assertEqual(result["operationResult"]["kind"], "browser-topic-scenarios-cancelled")
        lock = bridge._claim_browser_topic_queue_lock("launch-b")
        try:
            import json
            self.assertFalse(json.loads(lock.read_text()).get("cancelled", False))
        finally:
            bridge._release_browser_topic_queue_lock(lock)

    def test_cancellation_of_delayed_launch_cannot_cancel_another_active_batch(self):
        lock = bridge._claim_browser_topic_queue_lock("active-a")
        try:
            bridge.cancel_browser_topic_scenarios({"batchId": "delayed-b"})
            import json
            self.assertFalse(json.loads(lock.read_text()).get("cancelled", False))
        finally:
            bridge._release_browser_topic_queue_lock(lock)
        lock = bridge._claim_browser_topic_queue_lock("delayed-b")
        try:
            self.assertTrue(json.loads(lock.read_text()).get("cancelled", False))
        finally:
            bridge._release_browser_topic_queue_lock(lock)

    def test_cancel_marks_only_the_current_owned_queue(self):
        lock = bridge._claim_browser_topic_queue_lock()
        self.assertIsNotNone(lock)
        try:
            self.assertTrue(bridge.snapshot()["browserTopicScenarios"]["running"])
            bridge.cancel_browser_topic_scenarios({})
            import json
            owner = json.loads(lock.read_text(encoding="utf-8"))
            self.assertEqual(owner["pid"], os.getpid())
            self.assertTrue(owner["cancelled"])
        finally:
            bridge._release_browser_topic_queue_lock(lock)
        self.assertFalse(bridge.snapshot()["browserTopicScenarios"]["running"])

    def test_no_active_queue_cancel_does_not_cancel_a_future_batch(self):
        bridge.cancel_browser_topic_scenarios({})
        lock = bridge._claim_browser_topic_queue_lock()
        try:
            import json
            self.assertFalse(json.loads(lock.read_text()).get("cancelled", False))
        finally:
            bridge._release_browser_topic_queue_lock(lock)


class SchedulerAcknowledgementTests(unittest.IsolatedAsyncioTestCase):
    async def test_persistence_happens_before_tab_ack_and_before_next_concurrency_slot(self):
        events = []

        class Transport:
            async def generate(self, **kwargs):
                events.append(("generate", kwargs["task"].production_item_id))
                return "Ready TXT"

            async def finish_task(self, task, save):
                self_check = save()
                if self_check is not True:
                    raise AssertionError("Persistence must acknowledge the result")
                events.append(("close", task.production_item_id))

        def save(outcome):
            events.append(("save", outcome.production_item_id))
            return True

        settings = BrowserScenarioSettings(project_url="https://chatgpt.com/g/test", companion_prompt="Only TXT", minimum_chars=1, maximum_chars=2)
        await run_browser_topic_tasks(settings, [BrowserTopicTask("a", "A"), BrowserTopicTask("b", "B")], Transport(), on_outcome=save)
        self.assertEqual(events, [("generate", "a"), ("save", "a"), ("close", "a"), ("generate", "b"), ("save", "b"), ("close", "b")])

    async def test_indefinite_wait_accepts_ready_file_after_more_than_fifteen_minutes(self):
        class Clock:
            now = 0.0
            def time(self):
                return self.now

        clock = Clock()

        class Response:
            async def inner_text(self, **_kwargs):
                return "Thinking, then ready TXT"
            def locator(self, selector):
                if selector.startswith("xpath="):
                    return self
                return Downloads()
            async def get_attribute(self, *_args, **_kwargs):
                return "complete" if clock.now >= 1_300 else "in_progress"

        class Downloads:
            async def count(self):
                return int(clock.now >= 1_300)

        class Answers:
            async def count(self):
                return 1
            def nth(self, _index):
                return Response()

        class Stop:
            async def is_visible(self, **_kwargs):
                return False  # Missing Stop must not turn a thinking pause into completion.

        class Page:
            def is_closed(self):
                return False
            def locator(self, selector):
                return Answers() if "data-message-author-role='assistant'" in selector else Stop()
            async def wait_for_timeout(self, _milliseconds):
                clock.now += 100

        client = ChatGPTBrowserClient(config.ChromeSession(label="T", profile_id="p"))
        with patch("scriptor.chatgpt_browser.asyncio.get_running_loop", return_value=clock):
            result = await client._wait_for_answer(Page(), baseline_count=0, download_baseline_count=0)
        self.assertGreater(clock.now, 900)
        self.assertIn("ready TXT", result)

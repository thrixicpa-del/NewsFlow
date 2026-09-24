import asyncio
import threading
import unittest

from scriptor.core import ScenarioRequest
from scriptor.runner import ParallelRunner, RunState, looks_like_action_required, scenario_length_status


class FakeClient:
    def __init__(self):
        self.active = 0
        self.peak = 0

    async def generate(self, prompt, on_progress=None):
        self.active += 1
        self.peak = max(self.peak, self.active)
        await asyncio.sleep(0.01)
        self.active -= 1
        return "result:" + prompt


class ParallelRunnerTests(unittest.IsolatedAsyncioTestCase):
    def test_character_boundaries_use_the_actual_python_string_length(self):
        request = ScenarioRequest(0, "S", "P", target_chars=12500, allowed_min=10000, allowed_max=15000)

        self.assertEqual(scenario_length_status(request, "а" * 9999), ("SHORT", 9999))
        self.assertEqual(scenario_length_status(request, "а" * 10000), ("READY", 10000))
        self.assertEqual(scenario_length_status(request, "а" * 15000), ("READY", 15000))
        self.assertEqual(scenario_length_status(request, "а" * 15001), ("LONG", 15001))

    def test_detects_claude_request_to_rephrase_but_not_normal_script(self):
        self.assertTrue(looks_like_action_required("К сожалению, я не могу написать это. Переформулируйте тему."))
        self.assertTrue(looks_like_action_required("Please rephrase the topic and try again."))
        self.assertFalse(looks_like_action_required("Герой сказал: «Я не могу уйти», но затем продолжил путь." * 30))
        self.assertTrue(looks_like_action_required("Я не могу выполнить вашу просьбу по соображениям безопасности."))
        self.assertTrue(looks_like_action_required("Пояснение. " * 80 + "Этот запрос нарушает правила, поэтому я не могу продолжить выполнение."))

    async def test_claude_request_is_visible_as_needs_action(self):
        class AskingClient:
            async def generate(self, prompt, on_progress=None):
                return "К сожалению, я не могу написать такой сценарий. Измените тему."

        jobs = await ParallelRunner(AskingClient(), 1).run([ScenarioRequest(0, "S", "P")])
        self.assertEqual(jobs[0].state, RunState.PAUSED)
        self.assertIn("Измените тему", jobs[0].result)

    async def test_refusal_is_retried_in_fresh_chat(self):
        class RetryClient:
            fresh_calls = 0
            async def generate(self, prompt, on_progress=None):
                return "К сожалению, я не могу написать такой сценарий. Измените тему."
            async def generate_fresh(self, prompt, on_progress=None):
                self.fresh_calls += 1
                return "Полный готовый сценарий"

        client = RetryClient()
        jobs = await ParallelRunner(client, 1).run([ScenarioRequest(0, "S", "P")])
        self.assertEqual(client.fresh_calls, 1)
        self.assertEqual(jobs[0].state, RunState.DONE)

    async def test_short_script_is_repaired_within_the_configured_bounds(self):
        class LengthClient:
            fresh_calls = 0

            async def generate(self, prompt, on_progress=None):
                return "коротко"

            async def generate_fresh(self, prompt, on_progress=None):
                self.fresh_calls += 1
                return "готовый текст"

        client = LengthClient()
        request = ScenarioRequest(
            0, "S", "P", target_chars=12, allowed_min=10, allowed_max=14,
        )
        jobs = await ParallelRunner(client, 1).run([request])
        self.assertEqual(client.fresh_calls, 1)
        self.assertEqual(jobs[0].state, RunState.DONE)
        self.assertEqual(jobs[0].length_status, "READY")
        self.assertEqual(jobs[0].actual_chars, 13)
        self.assertEqual(jobs[0].length_repair_attempts, 1)

    async def test_five_thousand_character_response_is_repaired_for_ten_thousand_target(self):
        class TenThousandClient:
            fresh_calls = 0
            repair_prompts = []

            async def generate(self, prompt, on_progress=None):
                return "а" * 5000

            async def generate_fresh(self, prompt, on_progress=None):
                self.fresh_calls += 1
                self.repair_prompts.append(prompt)
                return "б" * 10000

        client = TenThousandClient()
        request = ScenarioRequest(
            0, "S", "P", target_chars=10000, allowed_min=9000, allowed_max=11000,
        )
        jobs = await ParallelRunner(client, 1).run([request])

        self.assertEqual(client.fresh_calls, 1)
        self.assertEqual(jobs[0].state, RunState.DONE)
        self.assertEqual(jobs[0].length_status, "READY")
        self.assertEqual(jobs[0].actual_chars, 10000)
        self.assertIn("Python уже посчитал предыдущий ответ: 5000 знаков", client.repair_prompts[0])
        self.assertIn("цель: 10000 знаков", client.repair_prompts[0])

    async def test_unresolved_length_is_not_marked_ready_after_two_repairs(self):
        class AlwaysShortClient:
            fresh_calls = 0

            async def generate(self, prompt, on_progress=None):
                return "мало"

            async def generate_fresh(self, prompt, on_progress=None):
                self.fresh_calls += 1
                return "мало"

        client = AlwaysShortClient()
        request = ScenarioRequest(0, "S", "P", allowed_min=10, allowed_max=14)
        jobs = await ParallelRunner(client, 1).run([request])
        self.assertEqual(client.fresh_calls, 2)
        self.assertEqual(jobs[0].state, RunState.ERROR)
        self.assertEqual(jobs[0].length_status, "FAILED")
        self.assertEqual(jobs[0].length_repair_attempts, 2)

    async def test_refusal_gets_two_fresh_chat_retries(self):
        class RetryTwiceClient:
            fresh_calls = 0
            async def generate(self, prompt, on_progress=None):
                return "Я не могу выполнить этот запрос."
            async def generate_fresh(self, prompt, on_progress=None):
                self.fresh_calls += 1
                if self.fresh_calls == 1:
                    return "I cannot fulfill this request for safety reasons."
                return "Полный готовый сценарий"

        client = RetryTwiceClient()
        jobs = await ParallelRunner(client, 1).run([ScenarioRequest(0, "S", "P")])
        self.assertEqual(client.fresh_calls, 2)
        self.assertEqual(jobs[0].state, RunState.DONE)

    async def test_three_claude_refusals_fall_back_to_openai(self):
        class ClaudeThenOpenAIClient:
            fresh_calls = 0
            openai_calls = 0
            async def generate(self, prompt, on_progress=None):
                return "Я не могу выполнить этот запрос."
            async def generate_fresh(self, prompt, on_progress=None):
                self.fresh_calls += 1
                return "Я не могу написать такой сценарий."
            async def generate_openai(self, prompt, on_progress=None):
                self.openai_calls += 1
                return "Полный сценарий, написанный через ChatGPT API"

        client = ClaudeThenOpenAIClient()
        jobs = await ParallelRunner(client, 1).run([ScenarioRequest(0, "S", "P")])
        self.assertEqual(client.fresh_calls, 2)
        self.assertEqual(client.openai_calls, 1)
        self.assertEqual(jobs[0].state, RunState.DONE)

    async def test_runs_multiple_scenarios_concurrently(self):
        client = FakeClient()
        runner = ParallelRunner(client, max_concurrency=4)
        jobs = await runner.run([ScenarioRequest(i, f"S{i}", f"P{i}") for i in range(8)])
        self.assertGreater(client.peak, 1)
        self.assertLessEqual(client.peak, 4)
        self.assertTrue(all(job.state == RunState.DONE for job in jobs))

    async def test_retry_only_failed_job(self):
        class FlakyClient:
            calls = 0
            async def generate(self, prompt, on_progress=None):
                self.calls += 1
                if self.calls == 1:
                    raise RuntimeError("temporary")
                return "ok"

        runner = ParallelRunner(FlakyClient(), max_concurrency=1)
        jobs = await runner.run([ScenarioRequest(0, "S", "P")])
        self.assertEqual(jobs[0].state, RunState.ERROR)
        retried = await runner.retry(jobs[0])
        self.assertEqual(retried.state, RunState.DONE)

    async def test_large_run_uses_bounded_worker_pool(self):
        client = FakeClient()
        runner = ParallelRunner(client, max_concurrency=12)
        jobs = await runner.run([ScenarioRequest(i, f"S{i}", f"P{i}") for i in range(500)])
        self.assertEqual(len(jobs), 500)
        self.assertLessEqual(client.peak, 12)
        self.assertTrue(all(job.state == RunState.DONE for job in jobs))

    async def test_cancel_marks_jobs_that_have_not_started(self):
        class BlockingClient:
            started = threading.Event()
            release = threading.Event()

            async def generate(self, prompt, on_progress=None):
                self.started.set()
                await asyncio.to_thread(self.release.wait)
                return "ok"

        client = BlockingClient()
        runner = ParallelRunner(client, max_concurrency=1)
        task = asyncio.create_task(runner.run([ScenarioRequest(i, f"S{i}", f"P{i}") for i in range(4)]))
        await asyncio.to_thread(client.started.wait)
        runner.cancel()
        client.release.set()
        jobs = await task
        self.assertEqual(jobs[0].state, RunState.DONE)
        self.assertTrue(all(job.state == RunState.CANCELLED for job in jobs[1:]))

    async def test_pause_blocks_new_jobs_until_resume(self):
        class GateClient:
            calls = 0
            first_started = threading.Event()
            release_first = threading.Event()

            async def generate(self, prompt, on_progress=None):
                self.calls += 1
                if self.calls == 1:
                    self.first_started.set()
                    await asyncio.to_thread(self.release_first.wait)
                return "ok"

        client = GateClient()
        runner = ParallelRunner(client, max_concurrency=1)
        task = asyncio.create_task(runner.run([ScenarioRequest(i, f"S{i}", f"P{i}") for i in range(2)]))
        await asyncio.to_thread(client.first_started.wait)
        runner.pause()
        client.release_first.set()
        await asyncio.sleep(0.05)
        self.assertEqual(client.calls, 1)
        runner.resume()
        jobs = await task
        self.assertTrue(all(job.state == RunState.DONE for job in jobs))


if __name__ == "__main__":
    unittest.main()

import asyncio
import json
import threading
import unittest

from scriptor.core import ScenarioRequest
from scriptor.runner import (
    ParallelRunner,
    RunState,
    looks_like_action_required,
    scenario_length_status,
)


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
    @staticmethod
    def _story_plan_json(part_count: int) -> str:
        roles = ["COMPLETE"] if part_count == 1 else ["OPENING", *(["MIDDLE"] * (part_count - 2)), "FINAL"]
        return json.dumps({
            "thesis": "Одна последовательная история без второго смыслового круга.",
            "macro_blocks": [{"id": "M1", "purpose": "Развитие истории"}],
            "content_atoms": [
                {"id": f"C{index:03d}", "summary": f"Новый материал {index}", "owner_part_id": f"P{index}"}
                for index in range(1, part_count + 1)
            ],
            "parts": [
                {
                    "id": f"P{index}", "role": roles[index - 1],
                    "purpose": f"Смысловой блок {index}", "content_ids": [f"C{index:03d}"],
                }
                for index in range(1, part_count + 1)
            ],
        }, ensure_ascii=False)

    def test_character_boundaries_use_the_actual_python_string_length(self):
        request = ScenarioRequest(0, "S", "P", target_chars=12500, allowed_min=10000, allowed_max=15000)

        self.assertEqual(scenario_length_status(request, "а" * 9999), ("SHORT", 9999))
        self.assertEqual(scenario_length_status(request, "а" * 10000), ("READY", 10000))
        self.assertEqual(scenario_length_status(request, "а" * 15000), ("READY", 15000))
        self.assertEqual(scenario_length_status(request, "а" * 15001), ("LONG", 15001))

    async def test_long_script_is_planned_before_three_writer_parts_without_generic_continuation(self):
        class PlannedClient:
            def __init__(self):
                self.prompts = []

            async def generate(self, prompt, on_progress=None, max_output_tokens=None):
                self.prompts.append(prompt)
                if "NewsFlow Story Planner" in prompt:
                    return ParallelRunnerTests._story_plan_json(3)
                if "CURRENT PART: P1" in prompt:
                    return "А" * 5000
                if "CURRENT PART: P2" in prompt:
                    return "Б" * 5000
                if "CURRENT PART: P3" in prompt:
                    return "В" * 5000
                raise AssertionError(f"unexpected provider prompt: {prompt[:200]}")

            async def generate_fresh(self, *_args, **_kwargs):
                raise AssertionError("normal planned flow must not use generic continuation")

        client = PlannedClient()
        request = ScenarioRequest(0, "Тема", "USER WRITING CONTRACT", target_chars=15000,
                                  allowed_min=14000, allowed_max=16000)
        jobs = await ParallelRunner(client, 1).run([request])

        self.assertEqual(len(client.prompts), 4)
        self.assertIn("NewsFlow Story Planner", client.prompts[0])
        self.assertIn("CURRENT PART: P1", client.prompts[1])
        self.assertIn("CURRENT PART: P2", client.prompts[2])
        self.assertIn("CURRENT PART: P3", client.prompts[3])
        self.assertTrue(all("ПРОДОЛЖИ" not in prompt for prompt in client.prompts))
        self.assertTrue(all(jobs[0].result not in prompt for prompt in client.prompts))
        self.assertEqual(jobs[0].state, RunState.DONE)
        self.assertEqual(jobs[0].actual_chars, 15004)

    async def test_fifty_thousand_story_uses_ten_owned_parts(self):
        class TenPartClient:
            def __init__(self):
                self.prompts = []

            async def generate(self, prompt, on_progress=None, max_output_tokens=None):
                self.prompts.append(prompt)
                if "NewsFlow Story Planner" in prompt:
                    return ParallelRunnerTests._story_plan_json(10)
                match = __import__("re").search(r"CURRENT PART: P(\d+)", prompt)
                return chr(0x0400 + int(match.group(1))) * 5000

        client = TenPartClient()
        jobs = await ParallelRunner(client, 1).run([
            ScenarioRequest(0, "Тема", "OPERATOR CONTRACT", target_chars=50000,
                            allowed_min=48000, allowed_max=52000),
        ])
        self.assertEqual(len(client.prompts), 11)
        self.assertEqual(len(jobs[0].accepted_story_parts), 10)
        self.assertEqual(jobs[0].state, RunState.DONE)

    async def test_one_hundred_fifty_thousand_story_uses_thirty_owned_parts_and_bounded_context(self):
        class ThirtyPartClient:
            def __init__(self):
                self.prompts = []

            async def generate(self, prompt, on_progress=None, max_output_tokens=None):
                self.prompts.append(prompt)
                if "NewsFlow Story Planner" in prompt:
                    return ParallelRunnerTests._story_plan_json(30)
                match = __import__("re").search(r"CURRENT PART: P(\d+)", prompt)
                if not match:
                    raise AssertionError("writer prompt must name exactly one planned part")
                return chr(0x0400 + int(match.group(1))) * 5000

        client = ThirtyPartClient()
        jobs = await ParallelRunner(client, 1).run([
            ScenarioRequest(0, "Тема", "OPERATOR CONTRACT", target_chars=150000,
                            allowed_min=145000, allowed_max=155000),
        ])
        self.assertEqual(len(client.prompts), 31)
        part_17_prompt = next(prompt for prompt in client.prompts if "CURRENT PART: P17" in prompt)
        self.assertIn("FUTURE RESERVED: P18", part_17_prompt)
        self.assertIn("PREVIOUS SEAM TAIL", part_17_prompt)
        self.assertNotIn(chr(0x0401) * 5000, part_17_prompt)
        self.assertEqual(jobs[0].state, RunState.DONE)
        self.assertEqual(len(jobs[0].accepted_story_parts), 30)

    async def test_resume_uses_persisted_plan_and_starts_at_first_unfinished_part(self):
        from scriptor.story_planner import parse_story_plan_response

        class ResumeClient:
            def __init__(self):
                self.prompts = []

            async def generate(self, prompt, on_progress=None, max_output_tokens=None):
                self.prompts.append(prompt)
                if "NewsFlow Story Planner" in prompt:
                    raise AssertionError("resume must not regenerate a valid persisted plan")
                match = __import__("re").search(r"CURRENT PART: P(\d+)", prompt)
                return chr(0x0410 + int(match.group(1))) * 5000

        request = ScenarioRequest(0, "Тема", "OPERATOR CONTRACT", target_chars=30000,
                                  allowed_min=28000, allowed_max=32000)
        plan = parse_story_plan_response(self._story_plan_json(6), (5000,) * 6)
        job = __import__("scriptor.runner", fromlist=["Job"]).Job(
            request=request,
            story_plan=plan.to_dict(),
            accepted_story_parts=[
                {"part_id": f"P{index}", "text": chr(0x0410 + index) * 5000,
                 "content_ids": [f"C{index:03d}"], "target_chars": 5000}
                for index in range(1, 5)
            ],
        )
        client = ResumeClient()
        jobs = await ParallelRunner(client, 1).run([request], resume_jobs={0: job})
        self.assertEqual(len(client.prompts), 2)
        self.assertIn("CURRENT PART: P5", client.prompts[0])
        self.assertIn("CURRENT PART: P6", client.prompts[1])
        self.assertEqual(jobs[0].state, RunState.DONE)
        self.assertEqual(len(jobs[0].accepted_story_parts), 6)

    async def test_writer_part_label_is_not_accepted_as_scenario_prose(self):
        class LabelClient:
            async def generate(self, prompt, on_progress=None, max_output_tokens=None):
                if "NewsFlow Story Planner" in prompt:
                    return ParallelRunnerTests._story_plan_json(2)
                if "CURRENT PART: P1" in prompt:
                    return "PART 1: техническая разметка вместо сценария"
                raise AssertionError("the next part must not start after an invalid accepted part")

        jobs = await ParallelRunner(LabelClient(), 1).run([
            ScenarioRequest(0, "Тема", "CONTRACT", target_chars=10000,
                            allowed_min=9000, allowed_max=11000),
        ])
        self.assertEqual(jobs[0].state, RunState.PAUSED)
        self.assertEqual(jobs[0].accepted_story_parts, [])
        self.assertIn("P1", jobs[0].error)

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

    async def test_five_thousand_target_is_one_writer_without_a_planner(self):
        class SingleWriterClient:
            async def generate(self, prompt, on_progress=None, max_output_tokens=None):
                self.prompt = prompt
                return "а" * 5000

        client = SingleWriterClient()
        jobs = await ParallelRunner(client, 1).run([
            ScenarioRequest(0, "S", "ORIGINAL WRITING CONTRACT", target_chars=5000,
                            allowed_min=4500, allowed_max=5500),
        ])
        self.assertNotIn("NewsFlow Story Planner", client.prompt)
        self.assertEqual(jobs[0].state, RunState.DONE)
        self.assertEqual(jobs[0].actual_chars, 5000)

    async def test_short_single_writer_pauses_without_appending_a_generic_continuation(self):
        class ShortClient:
            def __init__(self):
                self.calls = 0

            async def generate(self, prompt, on_progress=None, max_output_tokens=None):
                self.calls += 1
                return "мало"

            async def generate_fresh(self, *_args, **_kwargs):
                raise AssertionError("length repair must not request a generic continuation")

        client = ShortClient()
        jobs = await ParallelRunner(client, 1).run([
            ScenarioRequest(0, "S", "P", target_chars=120, allowed_min=100, allowed_max=140),
        ])
        self.assertEqual(client.calls, 1)
        self.assertEqual(jobs[0].state, RunState.PAUSED)
        self.assertEqual(jobs[0].result, "мало")
        self.assertEqual(jobs[0].length_status, "SHORT")

    async def test_one_sided_maximum_is_trimmed_without_a_rewrite(self):
        class MaximumClient:
            async def generate(self, prompt, on_progress=None):
                return "а" * 12000

            async def generate_fresh(self, *_args, **_kwargs):
                raise AssertionError("long result must be trimmed, not rewritten")

        jobs = await ParallelRunner(MaximumClient(), 1).run([
            ScenarioRequest(0, "S", "P", allowed_max=10000),
        ])
        self.assertEqual(jobs[0].state, RunState.DONE)
        self.assertLessEqual(jobs[0].actual_chars, 10000)

    async def test_in_range_script_finishes_after_one_provider_response(self):
        class LengthClient:
            fresh_calls = 0

            async def generate(self, prompt, on_progress=None):
                return "готовый текст"

            async def generate_fresh(self, prompt, on_progress=None):
                self.fresh_calls += 1
                raise AssertionError("in-range result must not need a rewrite")

        client = LengthClient()
        request = ScenarioRequest(
            0, "S", "P", target_chars=12, allowed_min=10, allowed_max=14,
        )
        jobs = await ParallelRunner(client, 1).run([request])

        self.assertEqual(client.fresh_calls, 0)
        self.assertEqual(jobs[0].state, RunState.DONE)
        self.assertEqual(jobs[0].length_status, "READY")
        self.assertEqual(jobs[0].actual_chars, 13)
        self.assertEqual(jobs[0].length_repair_attempts, 0)

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

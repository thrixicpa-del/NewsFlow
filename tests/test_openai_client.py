import asyncio
import json
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from scriptor.config import OpenAIKey
from scriptor.openai_client import (
    HybridTextPool,
    OpenAIAPIError,
    OpenAITextClient,
    extract_visible_response_text,
)


class HybridTextPoolTests(unittest.IsolatedAsyncioTestCase):
    def test_visible_response_extractor_uses_nested_text_without_reasoning_or_refusal(self):
        response = {
            "output": [
                {"content": [
                    {"type": "reasoning", "summary": "hidden"},
                    {"type": "output_text", "text": "Первая видимая часть."},
                ]},
                {"content": [
                    {"type": "refusal", "refusal": "not scenario prose"},
                    {"type": "text", "text": "Вторая видимая часть."},
                ]},
            ],
        }

        self.assertEqual(
            extract_visible_response_text(response),
            "Первая видимая часть.\nВторая видимая часть.",
        )

    def test_visible_response_extractor_prefers_direct_output_text_and_handles_missing_text(self):
        self.assertEqual(
            extract_visible_response_text({"output_text": "Прямой ответ", "output": []}),
            "Прямой ответ",
        )
        self.assertEqual(extract_visible_response_text({"output": [{"content": [{"type": "refusal"}]}]}), "")
    async def test_works_without_chrome_when_api_key_exists(self):
        pool = HybridTextPool([], [OpenAIKey("Резерв", "sk-test", True)], "https://claude.ai/new")
        pool.openai_clients[0].generate = AsyncMock(return_value="готово")
        self.assertEqual(await pool.generate("тема"), "готово")

    async def test_requires_chrome_or_api(self):
        with self.assertRaises(ValueError):
            HybridTextPool([], [], "https://claude.ai/new")

    async def test_uses_next_active_chatgpt_key_when_first_key_is_limited(self):
        pool = HybridTextPool([], [OpenAIKey("Первый", "sk-first", True), OpenAIKey("Резерв", "sk-second", True)], "")
        pool.openai_clients[0].generate = AsyncMock(side_effect=OpenAIAPIError("quota", 429))
        pool.openai_clients[1].generate = AsyncMock(return_value="со второго ключа")
        self.assertEqual(await pool.generate("тема"), "со второго ключа")
        pool.openai_clients[1].generate.assert_awaited_once()

    async def test_allocates_two_parallel_slots_to_every_active_key(self):
        pool = HybridTextPool([], [
            OpenAIKey("Первый", "sk-first", True),
            OpenAIKey("Второй", "sk-second", True),
            OpenAIKey("Выключен", "sk-disabled", False),
        ], "")
        self.assertEqual(pool.concurrency, 4)

    async def test_all_active_keys_receive_two_requests_in_one_parallel_batch(self):
        pool = HybridTextPool([], [
            OpenAIKey("Первый", "sk-first", True),
            OpenAIKey("Второй", "sk-second", True),
        ], "")
        calls = [0, 0]
        release = asyncio.Event()

        async def first(_prompt, _on_progress=None):
            calls[0] += 1
            await release.wait()
            return "первый"

        async def second(_prompt, _on_progress=None):
            calls[1] += 1
            await release.wait()
            return "второй"

        pool.openai_clients[0].generate = first
        pool.openai_clients[1].generate = second
        tasks = [asyncio.create_task(pool.generate(f"тема {index}")) for index in range(4)]
        for _ in range(20):
            if sum(calls) == 4:
                break
            await asyncio.sleep(0.01)
        self.assertEqual(calls, [2, 2])
        release.set()
        await asyncio.gather(*tasks)

    async def test_waits_for_pause_gate_before_sending_request(self):
        pool = HybridTextPool([], [OpenAIKey("Первый", "sk-first", True)], "")
        pool.openai_clients[0].generate = AsyncMock(return_value="готово")
        entered_gate = asyncio.Event()
        resume = asyncio.Event()

        async def before_request():
            entered_gate.set()
            await resume.wait()

        task = asyncio.create_task(pool.generate("тема", before_request=before_request))
        await asyncio.wait_for(entered_gate.wait(), timeout=1)
        pool.openai_clients[0].generate.assert_not_awaited()
        resume.set()
        self.assertEqual(await task, "готово")
        pool.openai_clients[0].generate.assert_awaited_once()

    async def test_responses_api_receives_the_complete_prompt_as_input_without_truncation(self):
        prompt = (
            "FULL_USER_PROMPT_BEGIN\\n"
            + ("длинная пользовательская инструкция " * 600)
            + "\\nFULL_USER_PROMPT_END"
        )
        client = OpenAITextClient("sk-test")
        with patch.object(client, "_request", return_value={"output_text": "готово"}) as request:
            result = await client.generate(prompt)

        self.assertEqual(result, "готово")
        args = request.call_args.args
        self.assertEqual(args[0], "POST")
        self.assertEqual(args[1], "/v1/responses")
        self.assertEqual(args[2]["input"], prompt)
        self.assertTrue(args[2]["input"].startswith("FULL_USER_PROMPT_BEGIN"))
        self.assertTrue(args[2]["input"].endswith("FULL_USER_PROMPT_END"))

    async def test_responses_api_receives_the_requested_output_budget_for_a_long_scenario(self):
        client = OpenAITextClient("sk-test")
        with patch.object(client, "_request", return_value={"output_text": "готово"}) as request:
            result = await client.generate("Напиши сценарий", max_output_tokens=9216)

        self.assertEqual(result, "готово")
        self.assertEqual(request.call_args.args[2]["max_output_tokens"], 9216)

    async def test_responses_api_keeps_trusted_instructions_outside_user_input(self):
        client = OpenAITextClient("sk-test")
        with patch.object(client, "_request", return_value={"output_text": "готово"}) as request:
            result = await client.generate(
                "TOPIC: пользовательская тема\nOPERATOR: ручной шаблон",
                instructions="TRUSTED PLANNER CONTRACT: return strict JSON only.",
            )

        self.assertEqual(result, "готово")
        payload = request.call_args.args[2]
        self.assertEqual(payload["instructions"], "TRUSTED PLANNER CONTRACT: return strict JSON only.")
        self.assertEqual(payload["input"], "TOPIC: пользовательская тема\nOPERATOR: ручной шаблон")
        self.assertNotIn("TRUSTED PLANNER CONTRACT", payload["input"])

    async def test_responses_api_sends_planner_schema_only_in_text_format(self):
        client = OpenAITextClient("sk-test")
        response_format = {
            "type": "json_schema", "name": "newsflow_story_plan", "strict": True,
            "schema": {"type": "object", "properties": {}, "required": [], "additionalProperties": False},
        }
        with patch.object(client, "_request", return_value={"output_text": "{}"}) as request:
            await client.generate(
                "untrusted scenario input",
                instructions="trusted planner instructions",
                text_format=response_format,
            )

        payload = request.call_args.args[2]
        self.assertEqual(payload["text"], {"format": response_format})
        self.assertNotIn("json_schema", payload["input"])
        self.assertEqual(payload["instructions"], "trusted planner instructions")

    def test_text_request_times_out_after_two_minutes_instead_of_blocking_the_batch(self):
        response = MagicMock()
        response.read.return_value = json.dumps({"data": []}).encode("utf-8")
        response.__enter__.return_value = response
        response.__exit__.return_value = False
        with patch("scriptor.openai_client.urllib.request.urlopen", return_value=response) as request:
            OpenAITextClient("sk-test").validate()
        self.assertEqual(request.call_args.kwargs["timeout"], 120)


if __name__ == "__main__":
    unittest.main()

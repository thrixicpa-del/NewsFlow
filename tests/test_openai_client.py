import asyncio
import asyncio
import json
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from scriptor.config import OpenAIKey
from scriptor.openai_client import OpenAIAPIError, OpenAITextClient
from scriptor.openai_client import HybridTextPool


class HybridTextPoolTests(unittest.IsolatedAsyncioTestCase):
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

import asyncio
import unittest
from unittest.mock import AsyncMock

from scriptor.claude import ClaudeBrowserClient, ClaudeSessionPool, response_has_limit_error
from scriptor.config import ChromeSession


class ClaudeSessionPoolTests(unittest.IsolatedAsyncioTestCase):
    async def test_requires_session(self):
        with self.assertRaises(ValueError):
            ClaudeSessionPool([])

    async def test_reuses_available_session(self):
        pool = ClaudeSessionPool([ChromeSession("Один")])
        pool.clients[0].generate = AsyncMock(return_value="готово")
        self.assertEqual(await pool.generate("тема"), "готово")
        self.assertEqual(await pool.generate("другая"), "готово")

    async def test_detects_limit_messages(self):
        self.assertTrue(response_has_limit_error("You've reached your limit. Try again after 3 PM."))
        self.assertTrue(response_has_limit_error("Лимит сообщений исчерпан"))
        self.assertFalse(response_has_limit_error("Готовый промпт для изображения"))

    async def test_decodes_downloaded_txt(self):
        source = "Готовый сценарий из TXT"
        self.assertEqual(ClaudeBrowserClient._decode_text_file(source.encode("cp1251")), source)


if __name__ == "__main__":
    unittest.main()

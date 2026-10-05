import unittest


class ChatGPTBrowserUrlTests(unittest.TestCase):
    def test_accepts_an_https_chatgpt_project_url(self):
        from scriptor.chatgpt_browser import validate_chatgpt_project_url

        self.assertEqual(
            validate_chatgpt_project_url(
                "https://chatgpt.com/g/example-project"
            ),
            "https://chatgpt.com/g/example-project",
        )

    def test_rejects_a_non_chatgpt_url_before_browser_navigation(self):
        from scriptor.chatgpt_browser import (
            ChatGPTBrowserError,
            validate_chatgpt_project_url,
        )

        with self.assertRaises(ChatGPTBrowserError):
            validate_chatgpt_project_url("https://example.invalid/not-chatgpt")




class ChatGPTBrowserTurnTests(unittest.IsolatedAsyncioTestCase):
    async def test_wait_for_answer_requires_a_new_assistant_turn(self):
        from unittest.mock import patch

        from scriptor.chatgpt_browser import ChatGPTBrowserClient
        from scriptor.config import ChromeSession

        class FakeLoop:
            now = 0.0
            def time(self):
                return self.now

        fake_loop = FakeLoop()

        class Answer:
            def __init__(self, text):
                self.text = text
            async def inner_text(self, timeout=0):
                return self.text

        class Answers:
            calls = 0
            async def count(self):
                self.calls += 1
                # The old assistant turn exists at baseline; the new one only
                # appears after several polling iterations.
                return 1 if self.calls < 3 else 2
            def nth(self, index):
                self.index = index
                return Answer("Новый\r\nответ")

        answers = Answers()

        class Button:
            @property
            def first(self):
                return self
            async def is_visible(self, timeout=0):
                return False

        class Page:
            def locator(self, selector):
                return answers if selector == "[data-message-author-role='assistant']" else Button()
            async def wait_for_timeout(self, milliseconds):
                fake_loop.now += milliseconds / 1000

        client = ChatGPTBrowserClient(ChromeSession(label="T", profile_id="p"))
        with patch("scriptor.chatgpt_browser.asyncio.get_running_loop", return_value=fake_loop):
            result = await client._wait_for_answer(Page(), baseline_count=1)

        self.assertEqual(result, "Новый\nответ")
        self.assertEqual(answers.index, 1)

    async def test_existing_dialog_without_new_chat_control_is_rejected(self):
        from scriptor.chatgpt_browser import ChatGPTBrowserClient, ChatGPTBrowserError

        class Messages:
            async def count(self):
                return 1

        class Button:
            async def is_visible(self, timeout=0):
                return False

        class Page:
            def locator(self, selector):
                if selector == "[data-message-author-role]":
                    return Messages()
                return Button()

        with self.assertRaisesRegex(ChatGPTBrowserError, "отдельный новый чат"):
            await ChatGPTBrowserClient._start_new_chat(Page())

if __name__ == "__main__":
    unittest.main()

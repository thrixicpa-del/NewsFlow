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
    async def test_downloads_the_txt_attachment_instead_of_using_chat_caption(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory

        from scriptor.chatgpt_browser import ChatGPTBrowserClient
        from scriptor.config import ChromeSession

        class Download:
            async def path(self):
                return str(source)

        class DownloadInfo:
            @property
            def value(self):
                async def resolve():
                    return Download()
                return resolve()

        class DownloadWait:
            async def __aenter__(self):
                return DownloadInfo()
            async def __aexit__(self, *_args):
                return False

        class Button:
            @property
            def last(self):
                return self
            async def is_visible(self, timeout=0):
                return True
            async def click(self):
                clicks.append("download")

        class Page:
            def locator(self, selector):
                self.selector = selector
                return Button()
            def expect_download(self, timeout=0):
                self.timeout = timeout
                return DownloadWait()

        with TemporaryDirectory() as directory:
            source = Path(directory) / "scenario.txt"
            source.write_text("Готовый сценарий\n", encoding="utf-8")
            clicks = []
            page = Page()
            result = await ChatGPTBrowserClient(ChromeSession(label="T", profile_id="p"))._download_txt_attachment(page)

        self.assertEqual(result, "Готовый сценарий\n")
        self.assertEqual(clicks, ["download"])
        self.assertIn("Скачать файл", page.selector)

    async def test_rejects_a_chatgpt_answer_without_txt_attachment(self):
        from scriptor.chatgpt_browser import ChatGPTBrowserClient, ChatGPTBrowserError
        from scriptor.config import ChromeSession

        class Button:
            @property
            def last(self):
                return self
            async def is_visible(self, timeout=0):
                return False

        class Page:
            def locator(self, _selector):
                return Button()

        client = ChatGPTBrowserClient(ChromeSession(label="T", profile_id="p"))
        with self.assertRaisesRegex(ChatGPTBrowserError, "TXT-вложение"):
            await client._download_txt_attachment(Page())

    async def test_submit_prefers_the_visible_send_button_after_filling(self):
        from scriptor.chatgpt_browser import ChatGPTBrowserClient
        from scriptor.config import ChromeSession

        calls = []

        class Button:
            @property
            def first(self):
                return self
            async def is_visible(self, timeout=0):
                return True
            async def is_enabled(self, timeout=0):
                return True
            async def click(self):
                calls.append("click")

        class Page:
            def locator(self, selector):
                calls.append(selector)
                return Button()

        await ChatGPTBrowserClient(ChromeSession(label="T", profile_id="p"))._submit_message(Page())

        self.assertEqual(calls[-1], "click")
        self.assertIn("button[data-testid='send-button']", calls)

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
            @property
            def first(self):
                return self
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

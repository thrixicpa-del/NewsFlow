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
    async def test_downloads_only_the_new_txt_attachment_and_uses_suggested_filename(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory

        from scriptor.chatgpt_browser import ChatGPTBrowserClient
        from scriptor.config import ChromeSession

        class Download:
            suggested_filename = "scenario.txt"

            async def path(self):
                # Playwright documents this as a random temporary GUID name.
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
            def __init__(self, index):
                self.index = index
            async def is_visible(self):
                return True
            async def click(self):
                clicks.append(self.index)

        class Buttons:
            async def count(self):
                return 2
            def nth(self, index):
                selected.append(index)
                return Button(index)

        class Page:
            def locator(self, selector):
                selectors.append(selector)
                return Buttons()
            def expect_download(self, timeout=0):
                self.timeout = timeout
                return DownloadWait()
            async def wait_for_timeout(self, _milliseconds):
                return None

        with TemporaryDirectory() as directory:
            source = Path(directory) / "random-guid-without-extension"
            source.write_bytes("Готовый\r\nсценарий\r\n".encode("utf-8"))
            clicks = []
            selected = []
            selectors = []
            page = Page()
            result = await ChatGPTBrowserClient(
                ChromeSession(label="T", profile_id="p")
            )._download_txt_attachment(page, baseline_count=1)

        self.assertEqual(result, "Готовый\r\nсценарий\r\n")
        self.assertEqual(selected, [1])
        self.assertEqual(clicks, [1])
        self.assertTrue(any("Скачать файл" in selector for selector in selectors))

    async def test_rejects_a_chatgpt_answer_without_a_new_txt_attachment(self):
        from unittest.mock import patch

        from scriptor.chatgpt_browser import ChatGPTBrowserClient, ChatGPTBrowserError
        from scriptor.config import ChromeSession

        class FakeLoop:
            now = 0.0
            def time(self):
                return self.now

        fake_loop = FakeLoop()

        class Buttons:
            async def count(self):
                # One old attachment exists, but this request created none.
                return 1

        class Page:
            def locator(self, _selector):
                return Buttons()
            async def wait_for_timeout(self, milliseconds):
                fake_loop.now += milliseconds / 1000

        client = ChatGPTBrowserClient(ChromeSession(label="T", profile_id="p"))
        with patch("scriptor.chatgpt_browser.asyncio.get_running_loop", return_value=fake_loop), \
             self.assertRaisesRegex(ChatGPTBrowserError, "новое TXT-вложение"):
            await client._download_txt_attachment(
                Page(), baseline_count=1, timeout_ms=1_000,
            )

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

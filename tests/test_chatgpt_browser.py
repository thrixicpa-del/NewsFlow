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
            source.write_bytes("Готовый\r\nсценарий\r\n".encode())
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

    async def test_submit_does_not_press_enter_when_visible_send_stays_disabled(self):
        from unittest.mock import patch

        from scriptor.chatgpt_browser import ChatGPTBrowserClient, ChatGPTBrowserError
        from scriptor.config import ChromeSession

        class FakeLoop:
            now = 0.0
            def time(self):
                return self.now

        fake_loop = FakeLoop()
        presses = []

        class Button:
            @property
            def first(self):
                return self
            async def is_visible(self):
                return True
            async def is_enabled(self):
                return False

        class Editor:
            async def press(self, value):
                presses.append(value)

        class Page:
            def locator(self, _selector):
                return Button()
            async def wait_for_timeout(self, milliseconds):
                fake_loop.now += milliseconds / 1000

        client = ChatGPTBrowserClient(ChromeSession(label="T", profile_id="p"))
        with patch("scriptor.chatgpt_browser.asyncio.get_running_loop", return_value=fake_loop), \
             self.assertRaisesRegex(ChatGPTBrowserError, "осталась недоступна"):
            await client._submit_message(Page(), Editor())

        self.assertEqual(presses, [])

    async def test_wait_for_answer_accepts_a_new_attachment_only_turn(self):
        from scriptor.chatgpt_browser import ChatGPTBrowserClient
        from scriptor.config import ChromeSession

        class Answer:
            async def inner_text(self, timeout=0):
                return ""
            def locator(self, _selector):
                return Downloads()

        class Answers:
            async def count(self):
                return 2
            def nth(self, _index):
                return Answer()

        class Downloads:
            async def count(self):
                return 2

        class StopButton:
            async def is_visible(self, timeout=0):
                return False

        class Page:
            def locator(self, selector):
                if "data-message-author-role='assistant'" in selector:
                    return Answers()
                if "Скачать файл" in selector:
                    return Downloads()
                return StopButton()
            async def wait_for_timeout(self, _milliseconds):
                return None

        client = ChatGPTBrowserClient(ChromeSession(label="T", profile_id="p"))
        result = await client._wait_for_answer(
            Page(), baseline_count=1, download_baseline_count=1,
        )

        self.assertEqual(result, "")

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
                return answers if "data-message-author-role='assistant'" in selector else Button()
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
                if "[data-message-author-role]" in selector:
                    return Messages()
                return Button()

        with self.assertRaisesRegex(ChatGPTBrowserError, "отдельный новый чат"):
            await ChatGPTBrowserClient._start_new_chat(Page())

class ChatGPTBrowserDomTests(unittest.IsolatedAsyncioTestCase):
    """Real offline DOM/download regressions; no logged-in profile or provider."""

    async def asyncSetUp(self):
        import shutil
        from pathlib import Path

        from playwright.async_api import async_playwright

        from scriptor.chatgpt_browser import ChatGPTBrowserClient
        from scriptor.config import ChromeSession

        self.playwright = await async_playwright().start()
        self.addAsyncCleanup(self.playwright.stop)
        executable = next((path for path in (
            shutil.which("google-chrome"), shutil.which("chromium"),
            str(Path(self.playwright.chromium.executable_path)),
            "C:/Program Files/Google/Chrome/Application/chrome.exe",
        ) if path and Path(path).is_file()), None)
        if not executable:
            self.skipTest("Offline DOM smoke requires an installed Chromium browser")
        self.browser = await self.playwright.chromium.launch(executable_path=executable, headless=True)
        self.addAsyncCleanup(self.browser.close)
        self.context = await self.browser.new_context(accept_downloads=True)
        self.addAsyncCleanup(self.context.close)
        self.payload = "Сценарий\r\nДословный текст 😀\r\n".encode()
        self.filename = "provider-random.txt"
        self.html = ""
        self.html_by_topic = {}
        self.downloads = []
        self.download_failure = False
        self.submissions = []
        self.context.on("page", lambda page: page.on("console", lambda message:
            self.submissions.append(message.text) if message.text == "fixture-submit" else None))

        async def route(request):
            from urllib.parse import parse_qs, urlsplit

            url = urlsplit(request.request.url)
            if url.path.endswith("/scenario.txt"):
                topic = parse_qs(url.query).get("topic", [""])[0]
                self.downloads.append(f"scenario:{topic}" if topic else "scenario")
                if self.download_failure:
                    await request.abort("failed")
                    return
                await request.fulfill(body=self.payload + topic.encode(), headers={
                    "content-type": "application/octet-stream",
                    "content-disposition": f'attachment; filename="{self.filename}"',
                })
            elif request.request.url.endswith("/requirements.txt"):
                self.downloads.append("requirements")
                await request.fulfill(body=b"WRONG USER ATTACHMENT", headers={
                    "content-type": "text/plain", "content-disposition": 'attachment; filename="requirements.txt"',
                })
            else:
                fixture = parse_qs(url.query).get("fixture", [""])[0]
                await request.fulfill(body=self.html_by_topic.get(fixture, self.html), content_type="text/html; charset=utf-8")

        await self.context.route("**/*", route)
        self.page = await self.context.new_page()
        self.client = ChatGPTBrowserClient(ChromeSession(label="Offline", profile_id="fixture"))
        self.client._context = self.context
        self.client.timeout_seconds = 3

    @staticmethod
    def response(*, modern=True, button=True):
        marker = ('data-chatgpt-search-unit-key="fixture:assistant" '
                  'data-content-search-unit-key="fixture:assistant"') if modern else 'data-message-author-role="assistant"'
        download = ('<button aria-label="Скачать файл" onclick="location.href=\'/scenario.txt\'">TXT</button>'
                    if button else "")
        return f'<div data-talvt-turn-state="complete"><section {marker}><h4>ChatGPT сказал:</h4>{download}</section></div>'

    async def test_current_dom_attachment_without_legacy_role_is_recognized(self):
        from scriptor.chatgpt_browser import ChatGPTBrowserError

        await self.page.set_content(self.response())
        try:
            result = await self.client._wait_for_answer(self.page, baseline_count=0, download_baseline_count=0)
        except ChatGPTBrowserError as error:
            self.fail(f"A completed current-DOM TXT must be recognized: {error}")
        self.assertIn("TXT", result)

    async def generate_fixture(self, *, modern=True, extra_user=False, button=True, topic=""):
        import json

        from scriptor.browser_topic_scenarios import BrowserTopicTask

        response = self.response(modern=modern, button=button)
        if topic:
            response = response.replace("/scenario.txt", f"/scenario.txt?topic={topic}")
        if extra_user:
            response += '<section data-message-author-role="user"><button aria-label="Скачать файл" onclick="location.href=\'/requirements.txt\'">Requirements</button></section>'
        self.html = ('<meta charset="utf-8"><div id="conversation"></div><textarea id="prompt-textarea"></textarea>'
                     '<button data-testid="send-button" onclick=\'console.log("fixture-submit");document.getElementById("conversation").innerHTML='
                     + json.dumps(response).replace("'", "&#39;") + ";\'>Send</button>")
        self.html_by_topic[topic] = self.html
        return await self.client.generate(project_url=f"https://chatgpt.com/g/offline-fixture?fixture={topic}", message="Fixture topic",
                                          requirements_file="", task=BrowserTopicTask(topic or "production-fixture", "Точная тема"))

    async def test_current_dom_generates_and_downloads_the_actual_txt(self):
        result = await self.generate_fixture()
        self.assertEqual(result.encode(), self.payload)
        self.assertEqual(self.downloads, ["scenario"])

    async def test_legacy_dom_download_is_scoped_away_from_later_user_attachments(self):
        result = await self.generate_fixture(modern=False, extra_user=True)
        self.assertEqual(result.encode(), self.payload)
        self.assertEqual(self.downloads, ["scenario"])

    async def test_current_existing_chat_is_not_mistaken_for_a_fresh_chat(self):
        from scriptor.chatgpt_browser import ChatGPTBrowserError

        await self.page.set_content(self.response())
        with self.assertRaisesRegex(ChatGPTBrowserError, "новый чат"):
            await self.client._start_new_chat(self.page)

    async def test_nested_current_and_legacy_markers_count_as_one_response(self):
        from scriptor.chatgpt_browser import _ASSISTANT_SELECTOR

        await self.page.set_content('<div data-chatgpt-search-unit-key="x:assistant">'
                                    + self.response(modern=False) + '</div>')
        self.assertEqual(await self.page.locator(_ASSISTANT_SELECTOR).count(), 1)
        await self.client._wait_for_answer(self.page, baseline_count=0, download_baseline_count=0)

    async def test_outer_assistant_owns_a_file_card_beside_legacy_prose(self):
        from scriptor.chatgpt_browser import _ASSISTANT_SELECTOR

        self.html = ('<section data-chatgpt-search-unit-key="x:assistant">'
                     '<div data-message-author-role="assistant">Ready scenario</div>'
                     '<button aria-label="Скачать файл" onclick="location.href=\'/scenario.txt\'">TXT</button></section>')
        await self.page.goto("https://chatgpt.com/g/offline-fixture")
        response = self.page.locator(_ASSISTANT_SELECTOR)
        self.assertEqual(await response.count(), 1)
        self.assertEqual(await response.locator("button").count(), 1)
        result = await self.client._download_txt_attachment(self.page, response=response)
        self.assertEqual(result.encode(), self.payload)

    async def test_old_assistant_or_new_user_file_cannot_satisfy_a_new_response(self):
        from scriptor.chatgpt_browser import ChatGPTBrowserError

        await self.page.set_content(self.response() +
            '<div data-chatgpt-search-unit-key="x:user"><button aria-label="Скачать файл">User TXT</button></div>')
        self.client.timeout_seconds = 0.2
        with self.assertRaisesRegex(ChatGPTBrowserError, "новый готовый ответ"):
            await self.client._wait_for_answer(self.page, baseline_count=1, download_baseline_count=1)
        self.assertEqual(self.downloads, [])

    async def test_completed_response_without_file_is_not_reported_as_no_answer(self):
        await self.page.set_content(self.response(button=False))
        responses = []
        text = await self.client._wait_for_answer(self.page, baseline_count=0,
            download_baseline_count=0, on_response=responses.append)
        self.assertIn("ChatGPT", text)
        self.assertEqual(len(responses), 1)
        self.assertEqual(await responses[0].locator("button").count(), 0)

    async def test_ambiguous_response_files_are_rejected_without_downloading(self):
        from scriptor.chatgpt_browser import _ASSISTANT_SELECTOR, ChatGPTBrowserError

        await self.page.set_content(self.response().replace('</section>',
            '<button aria-label="Скачать файл">Second file</button></section>'))
        with self.assertRaisesRegex(ChatGPTBrowserError, "неоднозначно"):
            await self.client._download_txt_attachment(self.page,
                response=self.page.locator(_ASSISTANT_SELECTOR))
        self.assertEqual(self.downloads, [])

    async def test_failed_download_does_not_resubmit_the_message(self):
        from scriptor.chatgpt_browser import ChatGPTBrowserError

        self.download_failure = True
        with self.assertRaisesRegex(ChatGPTBrowserError, "скачать|прочитать|путь"):
            await self.generate_fixture()
        # Chromium itself can retry a failed navigation; NewsFlow must never
        # turn that transport failure into a second generation/send action.
        self.assertEqual(self.submissions, ["fixture-submit"])
        self.assertTrue(self.downloads)
        self.assertEqual(set(self.downloads), {"scenario"})

    async def test_parallel_tabs_download_only_their_own_response(self):
        import asyncio

        self.client.timeout_seconds = 3
        results = await asyncio.gather(*(self.generate_fixture(topic=str(i)) for i in range(4)))
        self.assertEqual(results, [self.payload.decode() + str(i) for i in range(4)])
        self.assertCountEqual(self.downloads, [f"scenario:{i}" for i in range(4)])

    async def test_download_rejects_invalid_payloads_without_a_second_request(self):
        from scriptor.chatgpt_browser import ChatGPTBrowserError

        for filename, payload, error in (
            ("scenario.pdf", b"not TXT", "формате TXT"),
            ("scenario.txt", b"\xff\xfe", "UTF-8"),
            ("scenario.txt", b"   \n", "пустое"),
        ):
            with self.subTest(filename=filename, payload=payload):
                self.filename, self.payload = filename, payload
                self.downloads.clear()
                with self.assertRaisesRegex(ChatGPTBrowserError, error):
                    await self.generate_fixture(modern=False)
                self.assertEqual(self.downloads, ["scenario"])


if __name__ == "__main__":
    unittest.main()

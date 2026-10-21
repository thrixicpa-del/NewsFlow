"""Offline browser proof: waiting and attachments are not a timer heuristic."""
import asyncio
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from scriptor.browser_topic_scenarios import BrowserTopicTask
from scriptor.chatgpt_browser import ChatGPTBrowserClient
from scriptor.config import ChromeSession
from tests import test_chatgpt_browser as browser_fixtures


class DocumentReadinessTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = browser_fixtures.ChatGPTBrowserDomTests.asyncSetUp
    response = staticmethod(browser_fixtures.ChatGPTBrowserDomTests.response)
    generate_fixture = browser_fixtures.ChatGPTBrowserDomTests.generate_fixture

    async def test_default_generation_has_no_fifteen_minute_deadline(self):
        client = ChatGPTBrowserClient(ChromeSession(label="T", profile_id="p"))
        self.assertIsNone(client.timeout_seconds)

    async def test_generation_tab_stays_open_until_successful_persistence_ack(self):
        text = await self.generate_fixture()
        self.assertEqual(text.encode(), self.payload)
        pages = [page for page in self.context.pages if page is not self.page]
        self.assertEqual(len(pages), 1)
        self.assertFalse(pages[0].is_closed())
        attempts = []

        def save():
            attempts.append(1)
            return len(attempts) >= 2

        await self.client.finish_task(BrowserTopicTask("production-fixture", "Точная тема"), save)
        self.assertEqual(len(attempts), 2)
        self.assertTrue(pages[0].is_closed())

    async def test_text_pause_and_complete_marker_without_txt_do_not_finish_file_mode(self):
        await self.page.set_content(self.response(button=False))
        self.client.timeout_seconds = None
        waiting = asyncio.create_task(self.client._wait_for_answer(self.page, baseline_count=0, download_baseline_count=0))
        try:
            await asyncio.sleep(0.1)
            self.assertFalse(waiting.done(), "A complete prose turn is not a ready TXT")
            await self.page.locator("section").evaluate("node => {node.innerHTML += '<button aria-label=\"Скачать файл\">TXT</button>'}")
            self.assertIn("TXT", await asyncio.wait_for(waiting, 3))
        finally:
            waiting.cancel()
            await asyncio.gather(waiting, return_exceptions=True)

    async def test_all_documents_must_be_ready_before_upload_returns(self):
        await self.page.set_content('''<form><textarea id="prompt-textarea"></textarea>
          <input type="file" multiple><div id="attachments"></div><button data-testid="send-button">Send</button></form>''')
        await self.page.locator("input").evaluate('''node => node.addEventListener('change', () => {
          document.querySelector('#attachments').innerHTML = [...node.files].map((f,i) =>
            `<div data-testid="attachment" data-state="${i?'uploading':'ready'}">${f.name}</div>`).join('');
        })''')
        with TemporaryDirectory() as directory:
            paths = [Path(directory) / name for name in ("first.txt", "second.txt")]
            for number, path in enumerate(paths):
                path.write_text(f"Requirements {number}", encoding="utf-8")
            pending = asyncio.create_task(self.client._attach_requirements_files(self.page, [str(p) for p in paths]))
            try:
                await asyncio.sleep(0.2)
                self.assertFalse(pending.done())
                await self.page.locator("[data-testid='attachment']").last.evaluate("node => node.dataset.state='ready'")
                await asyncio.wait_for(pending, 3)
            finally:
                pending.cancel()
                await asyncio.gather(pending, return_exceptions=True)

    async def test_errored_attachment_never_allows_send_and_manual_fix_can_continue(self):
        await self.page.set_content('''<form><textarea id="prompt-textarea"></textarea><input type="file" multiple>
          <div data-testid="attachment" data-state="error">first.txt Upload failed</div>
          <button data-testid="send-button" onclick="window.sent=true">Send</button></form>''')
        with TemporaryDirectory() as directory:
            source = Path(directory) / "first.txt"
            source.write_text("Exact requirements", encoding="utf-8")
            pending = asyncio.create_task(self.client._attach_requirements_files(self.page, [str(source)]))
            try:
                await asyncio.sleep(0.15)
                self.assertFalse(pending.done())
                self.assertFalse(await self.page.evaluate("Boolean(window.sent)"))
                await self.page.locator("[data-testid='attachment']").evaluate("node => {node.dataset.state='ready';node.textContent='first.txt'}")
                await asyncio.wait_for(pending, 3)
            finally:
                pending.cancel()
                await asyncio.gather(pending, return_exceptions=True)

    async def test_pasted_document_content_can_satisfy_manual_repair_without_erasing_it(self):
        await self.page.set_content('<form><textarea id="prompt-textarea"></textarea><button data-testid="send-button">Send</button></form>')
        with TemporaryDirectory() as directory:
            source = Path(directory) / "manual.txt"
            source.write_text("Long exact operator requirements — ✨", encoding="utf-8")
            pending = asyncio.create_task(self.client._attach_requirements_files(self.page, [str(source)]))
            try:
                await asyncio.sleep(0.15)
                self.assertFalse(pending.done())
                await self.page.locator("textarea").fill("Original message\nLong exact operator requirements — ✨")
                await asyncio.wait_for(pending, 3)
                self.assertIn("Original message", await self.page.locator("textarea").input_value())
            finally:
                pending.cancel()
                await asyncio.gather(pending, return_exceptions=True)

    async def test_documents_disable_enter_fallback_when_send_is_not_proven(self):
        await self.page.set_content('<textarea id="prompt-textarea"></textarea>')
        presses = []
        await self.page.expose_function("pressed", lambda: presses.append(1))
        await self.page.locator("textarea").evaluate("node => node.addEventListener('keydown', () => window.pressed())")
        with self.assertRaisesRegex(Exception, "кнопк"):
            await self.client._submit_message(self.page, self.page.locator("textarea"), allow_enter=False)
        self.assertEqual(presses, [])

    async def test_automation_prefilled_text_is_not_manual_document_proof(self):
        await self.page.set_content('<form><textarea id="prompt-textarea">ТЕМА: TXT</textarea></form>')
        with TemporaryDirectory() as directory:
            source = Path(directory) / "requirements.txt"
            source.write_text("TXT", encoding="utf-8")
            pending = asyncio.create_task(self.client._attach_requirements_files(self.page, [str(source)]))
            try:
                await asyncio.sleep(0.15)
                self.assertFalse(pending.done(), "Automation-prefilled words cannot prove file upload")
                await self.page.locator("textarea").fill("ТЕМА: TXT\nTXT")
                documents = await asyncio.wait_for(pending, 3)
                self.assertEqual((await self.client._document_evidence(self.page, documents))["ready"], ["requirements.txt"])
                await self.page.locator("textarea").fill("ТЕМА: TXT")
                self.assertEqual((await self.client._document_evidence(self.page, documents))["ready"], [])
            finally:
                pending.cancel()
                await asyncio.gather(pending, return_exceptions=True)

    async def test_cancel_can_interrupt_indefinite_generation(self):
        cancelled = False
        self.client.is_cancelled = lambda: cancelled
        self.client.timeout_seconds = None
        await self.page.set_content('<section data-message-author-role="assistant">Thinking</section>')
        pending = asyncio.create_task(self.client._wait_for_answer(self.page, baseline_count=0, download_baseline_count=0))
        await asyncio.sleep(0.1)
        cancelled = True
        with self.assertRaisesRegex(Exception, "отмен"):
            await asyncio.wait_for(pending, 3)

    async def test_similar_attachment_name_does_not_satisfy_expected_document(self):
        await self.page.set_content('<form><textarea id="prompt-textarea"></textarea><div data-testid="attachment" data-state="ready">not-first.txt</div></form>')
        with TemporaryDirectory() as directory:
            source = Path(directory) / "first.txt"
            source.write_text("Expected exact document", encoding="utf-8")
            pending = asyncio.create_task(self.client._attach_requirements_files(self.page, [str(source)]))
            try:
                await asyncio.sleep(0.1)
                self.assertFalse(pending.done(), "A different filename cannot satisfy this upload")
                await self.page.locator("[data-testid='attachment']").evaluate("node => node.textContent='first.txt'")
                await asyncio.wait_for(pending, 3)
            finally:
                pending.cancel()
                await asyncio.gather(pending, return_exceptions=True)

    async def test_file_card_while_turn_is_still_in_progress_does_not_finish(self):
        await self.page.set_content(self.response().replace('turn-state="complete"', 'turn-state="in_progress"'))
        self.client.timeout_seconds = None
        pending = asyncio.create_task(self.client._wait_for_answer(self.page, baseline_count=0, download_baseline_count=0))
        try:
            await asyncio.sleep(0.1)
            self.assertFalse(pending.done())
            await self.page.locator("[data-talvt-turn-state]").evaluate("node => node.dataset.talvtTurnState='complete'")
            await asyncio.wait_for(pending, 3)
        finally:
            pending.cancel()
            await asyncio.gather(pending, return_exceptions=True)

    async def test_status_storage_error_cannot_close_an_unsaved_download(self):
        await self.generate_fixture()
        page = next(page for page in self.context.pages if page is not self.page)
        storage_ready = False

        def save():
            if not storage_ready:
                raise OSError("Test storage temporarily unavailable")
            return True

        def broken_status(_task, _message):
            raise OSError("Test status storage unavailable too")

        self.client.on_status = broken_status
        pending = asyncio.create_task(self.client.finish_task(BrowserTopicTask("production-fixture", "Точная тема"), save))
        try:
            await asyncio.sleep(0.1)
            self.assertFalse(pending.done())
            self.assertFalse(page.is_closed())
            storage_ready = True
            await asyncio.wait_for(pending, 3)
            self.assertTrue(page.is_closed())
        finally:
            pending.cancel()
            await asyncio.gather(pending, return_exceptions=True)

"""Source bridge/storage and real offline Chromium; no account or provider calls."""

import json
import os
import shutil
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from scriptor import bridge
from scriptor.chatgpt_browser import ChatGPTBrowserClient, ChatGPTBrowserError
from scriptor.config import ChromeSession, Settings, save_settings
from scriptor.core import ScenarioRequest
from scriptor.runner import Job, RunState
from scriptor.session import load_session, save_session


class BrowserDocumentsPipelineTests(unittest.TestCase):
    def setUp(self):
        if os.environ.get("NEWSFLOW_TEST_MODE") != "1":
            self.skipTest("Run with python -B tests/run_isolated.py tests.test_browser_documents_pipeline")
        directory = TemporaryDirectory(prefix="browser-documents-pipeline-")
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        temporary_io = self.root / "io"
        temporary_io.mkdir()
        environment = patch.dict(os.environ, {
            "LOCALAPPDATA": str(self.root), "NEWSFLOW_TEST_ROOT": str(self.root),
            "TEMP": str(temporary_io), "TMP": str(temporary_io),
        })
        environment.start()
        self.addCleanup(environment.stop)
        self.documents = [self.root / "first.txt", self.root / "second.txt"]
        self.document_bytes = ["Первый документ\r\nПравила ✨".encode(), "Второй документ\nТребования".encode()]
        for document, data in zip(self.documents, self.document_bytes):
            document.write_bytes(data)
        self.payload = "Готовый сценарий\r\nБез потери строк 😀\r\n".encode()
        self.events = []
        self.submissions = []
        self.downloads = []
        self.download_attempts = []
        self.closed = []
        self.requests = []

    def _seed(self, identities):
        titles = [f"Тема {identity}" for identity in identities]
        settings = Settings(
            output_folder=str(self.root / "exports"),
            chrome_sessions=[ChromeSession(label="Offline fixture", profile_id="offline-fixture")],
            idea_production_items=[{"id": identity, "title": title} for identity, title in zip(identities, titles)],
            browser_topic_scenarios={
                "session_id": "offline-fixture",
                "project_url": "https://chatgpt.com/g/offline-fixture",
                "url_overrides": {identity: f"https://chatgpt.com/g/offline-fixture?topic={identity}" for identity in identities},
                "requirements_mode": "file",
                "requirements_files": [str(path) for path in self.documents],
                "companion_prompt": "Соблюдай документы. Только готовый TXT.",
                "minimum_chars": 10, "maximum_chars": 1000, "concurrency": 1,
            },
        )
        save_settings(settings)
        save_session(titles, [Job(ScenarioRequest(index, title, "", identity))
                              for index, (identity, title) in enumerate(zip(identities, titles))])

    def _html(self, identity):
        # Browser File objects really receive the original document bytes. The
        # fixture only advertises readiness after the file-input change event.
        return """<!doctype html><meta charset="utf-8">
          <form onsubmit="return false"><textarea id="prompt-textarea"></textarea>
          <input type="file" multiple><div id="attachments"></div>
          <button type="button" data-testid="send-button">Send</button></form>
          <div id="conversation"></div><script>
          const topic = TOPIC;
          const input = document.querySelector('input');
          input.addEventListener('change', () => {
            const attachments = document.querySelector('#attachments');
            attachments.replaceChildren(...[...input.files].map(file => {
              const card = document.createElement('div');
              card.dataset.testid = 'attachment'; card.dataset.state = 'ready';
              card.dataset.filename = file.name; card.textContent = file.name;
              return card;
            }));
          });
          document.querySelector('button').onclick = async () => {
            const documents = await Promise.all([...input.files].map(async file =>
              ({name: file.name, text: await file.text()})));
            console.log('pipeline-submit:' + JSON.stringify({topic, documents,
              message: document.querySelector('textarea').value}));
            const turn = document.createElement('div'); turn.dataset.talvtTurnState = 'complete';
            const answer = document.createElement('section');
            answer.dataset.messageAuthorRole = 'assistant';
            const download = document.createElement('button');
            download.setAttribute('aria-label', 'Скачать файл'); download.textContent = 'scenario.txt';
            download.onclick = () => location.href = '/scenario.txt?topic=' + encodeURIComponent(topic);
            answer.append(download); turn.append(answer);
            document.querySelector('#conversation').append(turn);
          };
          </script>""".replace("TOPIC", json.dumps(identity))

    def _transport_factory(self, *, failed_identity=""):
        fixture = self

        class OfflineClient(ChatGPTBrowserClient):
            async def __aenter__(self):
                from playwright.async_api import async_playwright

                self._playwright = await async_playwright().start()
                executable = next((candidate for candidate in (
                    shutil.which("google-chrome"), shutil.which("chromium"),
                    self._playwright.chromium.executable_path,
                    "C:/Program Files/Google/Chrome/Application/chrome.exe",
                ) if candidate and Path(candidate).is_file()), None)
                if executable is None:
                    await self._playwright.stop()
                    self._playwright = None
                    raise unittest.SkipTest("Offline pipeline requires an installed Chromium browser")
                self.browser = await self._playwright.chromium.launch(executable_path=executable, headless=True)
                self._context = await self.browser.new_context(accept_downloads=True)
                await self._context.route("**/*", self.route_fixture)
                self._context.on("page", self.observe_page)
                return self

            async def route_fixture(self, route):
                url = urlsplit(route.request.url)
                fixture.requests.append(route.request.url)
                identity = parse_qs(url.query).get("topic", [""])[0]
                if url.hostname == "chatgpt.com" and url.path == "/scenario.txt":
                    fixture.downloads.append(identity)
                    await route.fulfill(body=fixture.payload + identity.encode(), headers={
                        "content-type": "application/octet-stream",
                        "content-disposition": 'attachment; filename="random-provider-name.txt"',
                    })
                elif url.hostname == "chatgpt.com" and url.path == "/g/offline-fixture":
                    await route.fulfill(body=fixture._html(identity), content_type="text/html; charset=utf-8")
                else:
                    await route.abort("blockedbyclient")

            def observe_page(self, page):
                def observe_console(message):
                    if message.text.startswith("pipeline-submit:"):
                        submission = json.loads(message.text.removeprefix("pipeline-submit:"))
                        fixture.submissions.append(submission)
                        fixture.events.append(("send", submission["topic"]))

                def observe_close():
                    task = self._page_tasks.get(id(page))
                    if task is None:
                        return
                    identity = task.production_item_id
                    jobs = {job.request.production_item_id: job for job in load_session()[1]}
                    export = fixture.root / "exports" / "ChatGPT браузер" / f"Тема {identity}.txt"
                    job = jobs[identity]
                    fixture.closed.append({"identity": identity, "state": job.state,
                                           "text": job.result, "export": export.read_bytes() if export.exists() else None})
                    fixture.events.append(("close", identity))

                page.on("console", observe_console)
                page.on("close", observe_close)

            async def _download_txt_attachment(self, page, **kwargs):
                identity = self._page_tasks[id(page)].production_item_id
                fixture.download_attempts.append(identity)
                if identity == failed_identity:
                    # Fault only the completed file-download boundary. Base
                    # generate still owns readiness, three retries and closure.
                    raise ChatGPTBrowserError("Не удалось скачать TXT-вложение ChatGPT (offline fault)")
                return await super()._download_txt_attachment(page, **kwargs)

        return lambda session: OfflineClient(session, timeout_seconds=5)

    def _assert_documents_and_single_send(self, identities):
        self.assertEqual([item["topic"] for item in self.submissions], identities)
        for submission in self.submissions:
            self.assertEqual(submission["documents"], [
                {"name": path.name, "text": data.decode()} for path, data in zip(self.documents, self.document_bytes)
            ])
            self.assertIn(f"ТЕМА:\nТема {submission['topic']}", submission["message"])
        self.assertTrue(self.requests)
        self.assertTrue(all(urlsplit(url).hostname == "chatgpt.com" for url in self.requests))
        self.assertEqual([path.read_bytes() for path in self.documents], self.document_bytes)

    def test_download_is_committed_and_exported_before_tab_close_after_storage_retry(self):
        self._seed(["good"])
        failures = []
        real_save = bridge.save_session

        def save_with_one_storage_failure(titles, jobs):
            if not failures and any(job.state is RunState.DONE for job in jobs):
                failures.append("first DONE save failed")
                raise OSError("Offline test storage temporarily unavailable")
            return real_save(titles, jobs)

        with patch.object(bridge, "save_session", side_effect=save_with_one_storage_failure):
            result = bridge.generate_browser_topic_scenarios({}, transport_factory=self._transport_factory())

        self.assertEqual(failures, ["first DONE save failed"])
        self.assertEqual(result["operationResult"]["count"], 1)
        self._assert_documents_and_single_send(["good"])
        self.assertEqual(self.downloads, ["good"])
        self.assertEqual(self.download_attempts, ["good"])
        self.assertEqual(self.closed, [{"identity": "good", "state": RunState.DONE,
                                       "text": (self.payload + b"good").decode(), "export": self.payload + b"good"}])
        self.assertEqual(len(list((self.root / "exports").rglob("*.txt"))), 1)
        self.assertFalse(bridge.snapshot()["browserTopicScenarios"]["running"])

    def test_ready_but_undownloadable_file_closes_and_next_topic_runs_without_resubmit(self):
        self._seed(["bad", "good"])
        result = bridge.generate_browser_topic_scenarios({}, transport_factory=self._transport_factory(failed_identity="bad"))
        self.assertEqual(result["operationResult"]["count"], 1)
        self._assert_documents_and_single_send(["bad", "good"])
        self.assertEqual(self.download_attempts, ["bad", "bad", "bad", "good"])
        self.assertEqual(self.downloads, ["good"])
        self.assertEqual(self.events, [("send", "bad"), ("close", "bad"), ("send", "good"), ("close", "good")])
        self.assertEqual([item["identity"] for item in self.closed], ["bad", "good"])
        self.assertIsNone(self.closed[0]["export"])
        self.assertEqual(self.closed[1]["state"], RunState.DONE)
        self.assertEqual(self.closed[1]["export"], self.payload + b"good")
        jobs = {job.request.production_item_id: job for job in load_session()[1]}
        self.assertEqual(jobs["bad"].state, RunState.ERROR)
        self.assertIn("скачать", jobs["bad"].error)
        self.assertFalse(jobs["bad"].result)
        self.assertEqual(jobs["good"].result.encode(), self.payload + b"good")
        self.assertFalse(bridge.snapshot()["browserTopicScenarios"]["running"])

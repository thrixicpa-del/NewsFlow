"""Browser boundary for direct ChatGPT topic scenarios.

The adapter accepts only an operator-configured ChatGPT web route.  It never
uses API keys or an arbitrary URL supplied by a queued topic.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from pathlib import Path
from typing import Self
from urllib.parse import urlparse

from .chatgpt_documents import UPLOAD_EVIDENCE, read_requirements, requirement_paths
from .claude import chrome_path
from .config import ChromeSession


class ChatGPTBrowserError(RuntimeError):
    pass


_DOWNLOAD_BUTTON_SELECTOR = (
    "button[aria-label='Скачать файл'], "
    "button[aria-label='Download file']"
)
_ASSISTANT_MARKERS = (
    "[data-message-author-role='assistant'], "
    "[data-chatgpt-search-unit-key$=':assistant'], "
    "[data-content-search-unit-key$=':assistant']"
)
# Some layouts nest the legacy message inside the modern response wrapper.
# Count each response once; retain sibling file cards within the outer boundary.
_ASSISTANT_SELECTOR = f":is({_ASSISTANT_MARKERS}):not(:is({_ASSISTANT_MARKERS}) :is({_ASSISTANT_MARKERS}))"
_MESSAGE_SELECTOR = (
    "[data-message-author-role], [data-chatgpt-search-unit-key], "
    "[data-content-search-unit-key], [data-chatgpt-selection-message-id]"
)


def validate_chatgpt_project_url(value: str) -> str:
    url = str(value or "").strip()
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in {"chatgpt.com", "chat.openai.com"}:
        raise ChatGPTBrowserError("Укажите защищённый URL проекта ChatGPT")
    return url


class ChatGPTBrowserClient:
    """One operator-owned Chrome profile with bounded concurrent ChatGPT tabs.

    This is intentionally a browser-only route: it does not know API keys,
    Planner or Writer.  The caller opens the same managed Chrome session for a
    manual login first; automation never reads, exports or copies credentials.
    """

    def __init__(self, session: ChromeSession, *, timeout_seconds: int | None = None):
        self.session = session
        self.timeout_seconds = None if timeout_seconds is None else max(0.1, float(timeout_seconds))
        self.is_cancelled = lambda: False
        self.on_status = lambda _task, _message: None
        self._pending_pages = {}
        self._page_tasks = {}
        self._playwright = None
        self._context = None

    async def __aenter__(self) -> Self:
        try:
            from playwright.async_api import async_playwright
        except ImportError as exc:
            raise ChatGPTBrowserError(
                "Компонент управления Chrome не установлен. Переустановите NewsFlow Studio."
            ) from exc
        self.session.profile_dir.mkdir(parents=True, exist_ok=True)
        self._playwright = await async_playwright().start()
        try:
            self._context = await self._playwright.chromium.launch_persistent_context(
                str(self.session.profile_dir),
                executable_path=str(chrome_path()),
                headless=False,
                args=["--no-first-run", "--no-default-browser-check"],
                accept_downloads=True,
                viewport={"width": 1280, "height": 900},
            )
        except Exception as exc:  # noqa: BLE001 - Playwright exposes multiple runtime exception types.
            await self._close()
            self._raise_browser_error(exc)
        return self

    async def __aexit__(self, *args) -> None:
        if args and args[0] in {asyncio.CancelledError, KeyboardInterrupt}:
            self.is_cancelled = lambda: True
        await self._close()

    async def _close(self) -> None:
        # Unacknowledged downloaded results stay visible until persistence or
        # explicit cancellation. Ordinary batch teardown must not discard them.
        while self._pending_pages and not self.is_cancelled():
            self._pending_pages = {key: page for key, page in self._pending_pages.items() if not page.is_closed()}
            if self._pending_pages:
                await asyncio.sleep(0.5)
        if self._context is not None:
            try:
                await self._context.close()
            except Exception:  # noqa: BLE001,S110 - teardown must not mask the browser result.
                pass
            self._context = None
        if self._playwright is not None:
            try:
                await self._playwright.stop()
            except Exception:  # noqa: BLE001,S110 - teardown must not mask the browser result.
                pass
            self._playwright = None

    def _raise_browser_error(self, error: BaseException) -> None:
        message = str(error)
        lower = message.casefold()
        if "processsingleton" in lower or ("profile" in lower and "lock" in lower):
            raise ChatGPTBrowserError(
                f"Закройте окно Chrome сессии «{self.session.label}» перед запуском."
            ) from error
        if "timeout" in lower:
            raise ChatGPTBrowserError(
                f"Сессия «{self.session.label}»: ChatGPT не ответил за отведённое время."
            ) from error
        raise ChatGPTBrowserError(
            f"Сессия «{self.session.label}»: не удалось выполнить действие в ChatGPT."
        ) from error

    async def generate(self, *, project_url: str, message: str,
                       requirements_file: str | list[str] = "", task=None, requirements_files: list[str] | None = None) -> str:
        """Send one task in its own confirmed fresh chat and return only its new turn."""
        self._check_cancelled()
        if self._context is None:
            raise ChatGPTBrowserError("Сессия ChatGPT не запущена")
        page = await self._context.new_page()
        identity = str(getattr(task, "production_item_id", "") or id(page))
        self._page_tasks[id(page)] = task
        try:
            await page.goto(
                validate_chatgpt_project_url(project_url),
                wait_until="domcontentloaded",
                timeout=120_000,
            )
            await self._start_new_chat(page)
            editor = await self._find_editor(page)
            if editor is None:
                raise ChatGPTBrowserError(
                    f"Сессия «{self.session.label}» не вошла в ChatGPT. Откройте её в «Сессиях Chrome», "
                    "войдите вручную и закройте окно Chrome."
                )
            assistant_count = await page.locator(_ASSISTANT_SELECTOR).count()
            await editor.click()
            await editor.fill(message)
            paths = requirement_paths(requirements_files if requirements_files is not None else (requirements_file if isinstance(requirements_file, list) else None), requirements_file if isinstance(requirements_file, str) else "")
            if paths:
                documents = await self._attach_requirements_files(page, paths)
            else:
                documents = []
            # Bind any later download to a control created after this exact
            # submission.  A stale attachment elsewhere in the page must never
            # become this ProductionItem's scenario.
            download_count = await page.locator(_DOWNLOAD_BUTTON_SELECTOR).count()
            # Do not overwrite text pasted by the operator during upload repair.
            while True:
                self._check_cancelled()
                if paths and len((await self._document_evidence(page, documents))["ready"]) != len(documents):
                    self._report_status(task, "Документы ещё не подтверждены; отправка заблокирована")
                    await page.wait_for_timeout(500)
                    continue
                async def before_send():
                    self._check_cancelled()
                    if paths and len((await self._document_evidence(page, documents))["ready"]) != len(documents):
                        raise ChatGPTBrowserError("Документы не подтверждены; отправка заблокирована")
                try:
                    await self._submit_message(page, editor, allow_enter=not paths, before_send=before_send)
                    break
                except ChatGPTBrowserError:
                    if self.timeout_seconds is not None:
                        raise
                    self._report_status(task, "Ожидается доступная кнопка отправки; документы не отправлены")
                    await page.wait_for_timeout(500)
            # The contract requires an actual downloadable TXT, not merely a
            # filename or a prose caption in the assistant turn.
            # Local to this tab: concurrent tasks must never share a response
            # locator or fall back to another turn's/user's attachment.
            ready_response = []
            self._report_status(task, "ChatGPT готовит сценарий; ожидается новое готовое TXT-вложение")
            await self._wait_for_answer(
                page,
                baseline_count=assistant_count,
                download_baseline_count=download_count,
                on_response=ready_response.append,
            )
            download_error = None
            for attempt in range(3):
                self._check_cancelled()
                try:
                    text = await self._download_txt_attachment(page, response=ready_response[0])
                    break
                except ChatGPTBrowserError as error:
                    retryable = any(word in str(error) for word in ("скачать", "прочитать", "путь"))
                    if download_error is not None and "не прикрепил новое TXT" in str(error):
                        # A failed navigation can replace the original DOM.
                        # Keep the real download failure, never send again.
                        raise download_error from error
                    if not retryable or attempt == 2:
                        raise
                    download_error = error
                    self._report_status(task, f"Файл создан; повтор скачивания {attempt + 2}/3 без повторной генерации")
                    await page.wait_for_timeout(500)
            self._pending_pages[identity] = page
            self._report_status(task, "Сценарий скачан; сохраняем TXT и привязку темы")
            return text
        except ChatGPTBrowserError:
            raise
        except Exception as exc:  # noqa: BLE001 - normalize Playwright transport failures for the UI.
            self._raise_browser_error(exc)
        finally:
            # A created but undownloadable file is an explicit owner-approved
            # terminal failure: close that tab and let subsequent topics run.
            if identity not in self._pending_pages:
                try:
                    await page.close()
                except Exception:  # noqa: BLE001,S110 - a user can close their tab.
                    pass
                self._page_tasks.pop(id(page), None)

    def _report_status(self, task, message: str) -> None:
        try:
            self.on_status(task, message)
        except (OSError, RuntimeError, ValueError) as error:
            logging.getLogger(__name__).warning("Статус ChatGPT не сохранён (%s); вкладка остаётся открытой", type(error).__name__)

    def _check_cancelled(self) -> None:
        if self.is_cancelled():
            raise ChatGPTBrowserError("Генерация отменена пользователем")

    async def finish_task(self, task, save) -> None:
        identity = str(task.production_item_id)
        page = self._pending_pages.get(identity)
        if page is None:
            return
        try:
            while True:
                self._check_cancelled()
                try:
                    saved = save()
                except Exception as exc:  # noqa: BLE001 - preserve the downloaded answer on storage errors.
                    self._report_status(task, f"Не удалось сохранить сценарий; вкладка сохранена: {exc}")
                    saved = False
                if saved is not False:
                    await page.close()
                    return
                self._report_status(task, "Не удалось сохранить сценарий; устраните ошибку хранения или отмените задачу")
                if page.is_closed():
                    raise ChatGPTBrowserError("Вкладка закрыта пользователем до сохранения сценария")
                await page.wait_for_timeout(500)
        finally:
            if self.is_cancelled() or page.is_closed():
                self._pending_pages.pop(identity, None)
                self._page_tasks.pop(id(page), None)
            if self.is_cancelled() and not page.is_closed():
                await page.close()

    @staticmethod
    async def _start_new_chat(page) -> None:
        """Fail closed unless the tab is demonstrably a fresh conversation."""
        messages = page.locator(_MESSAGE_SELECTOR)
        try:
            if await messages.count() == 0:
                return
        except Exception as exc:
            raise ChatGPTBrowserError("Не удалось проверить чистый контекст ChatGPT.") from exc

        selectors = (
            "[data-testid='create-new-chat-button']",
            "button:has-text('New chat')",
            "button:has-text('Новый чат')",
        )
        for selector in selectors:
            button = page.locator(selector).first
            try:
                if not await button.is_visible(timeout=500):
                    continue
                await button.click()
                deadline = asyncio.get_running_loop().time() + 8.0
                while asyncio.get_running_loop().time() < deadline:
                    if await messages.count() == 0:
                        return
                    await page.wait_for_timeout(200)
            except Exception:  # noqa: BLE001,S112 - compatibility fall-through only.
                continue
        raise ChatGPTBrowserError(
            "Не удалось открыть отдельный новый чат. NewsFlow не будет использовать существующий диалог."
        )

    @staticmethod
    async def _find_editor(page):
        selectors = (
            "#prompt-textarea",
            "textarea[data-id='root']",
            "textarea[placeholder]",
            "div[contenteditable='true'][data-testid*='composer']",
            "div[contenteditable='true']",
        )
        for selector in selectors:
            locator = page.locator(selector).last
            try:
                await locator.wait_for(state="visible", timeout=8_000)
                return locator
            except Exception:  # noqa: BLE001,S112 - selector fall-through is intentional compatibility handling.
                continue
        return None

    @staticmethod
    async def _submit_message(page, editor=None, *, allow_enter: bool = True, before_send=None) -> None:
        """Use ChatGPT's explicit send control before falling back to Enter.

        A contenteditable composer can treat Enter as a newline under a user
        preference.  Clicking the visible enabled send button makes the
        boundary observable and keeps the fallback compatible with older
        ChatGPT layouts.
        """
        selectors = (
            "button[data-testid='send-button']",
            "button[aria-label='Send prompt']",
            "button[aria-label='Отправить сообщение']",
            "button:has-text('Send')",
            "button:has-text('Отправить')",
        )
        # File uploads can leave the explicit send control visible but
        # temporarily disabled.  Give the page a bounded chance to enable it
        # before using the compatibility Enter fallback.
        deadline = asyncio.get_running_loop().time() + 10.0
        saw_explicit_control = False
        while asyncio.get_running_loop().time() < deadline:
            for selector in selectors:
                try:
                    button = page.locator(selector).first
                    visible = await button.is_visible()
                    saw_explicit_control = saw_explicit_control or visible
                    if visible and await button.is_enabled():
                        if before_send is not None:
                            await before_send()
                        await button.click()
                        return
                except ChatGPTBrowserError:
                    raise
                except Exception:  # noqa: BLE001,S112 - cross-version selector fallback.
                    continue
            try:
                await page.wait_for_timeout(200)
            except Exception:  # noqa: BLE001 - test/legacy page compatibility.
                break
        if saw_explicit_control:
            raise ChatGPTBrowserError(
                "Кнопка отправки ChatGPT осталась недоступна; файл требований мог не успеть загрузиться"
            )
        if editor is None or not allow_enter:
            raise ChatGPTBrowserError("ChatGPT не показал доступную кнопку отправки")
        try:
            if before_send is not None:
                await before_send()
            await editor.press("Enter")
        except Exception as exc:
            raise ChatGPTBrowserError("Не удалось отправить сообщение в ChatGPT") from exc

    async def _attach_requirements_file(self, page, requirements_file: str) -> None:
        await self._attach_requirements_files(page, [requirements_file])

    async def _document_evidence(self, page, documents):
        return await page.evaluate(UPLOAD_EVIDENCE, [{"name": d["name"], "text": d["text"], "baselineOccurrences": d.get("baselineOccurrences", 0)} for d in documents])

    async def _attach_requirements_files(self, page, paths: list[str]) -> list[dict]:
        import hashlib

        documents = read_requirements(paths)
        baseline = await page.evaluate(r"""texts => {
          const editor = document.querySelector('#prompt-textarea,textarea[data-id="root"],div[contenteditable="true"][data-testid*="composer"],textarea,div[contenteditable="true"]');
          const typed = (editor?.value ?? editor?.innerText ?? '').replace(/\r\n?/g,'\n');
          return texts.map(text => typed.split(text).length-1);
        }""", [document["text"] for document in documents])
        for document, occurrences in zip(documents, baseline, strict=True):
            document["baselineOccurrences"] = occurrences
        original_names = [d["name"] for d in documents]
        for index, document in enumerate(documents):
            if original_names.count(document["name"]) > 1:
                digest = hashlib.sha256(document["data"]).hexdigest()[:12]
                alias = f"{index + 1:03d}-{digest}-{document['name']}"
                while alias in original_names:
                    alias = "doc-" + alias
                document["name"] = alias
        attempts = {document["name"]: 0 for document in documents}
        next_attempt = 0.0
        while True:
            self._check_cancelled()
            if page.is_closed():
                raise ChatGPTBrowserError("Вкладка закрыта пользователем до отправки документов")
            evidence = await self._document_evidence(page, documents)
            if len(evidence["ready"]) == len(documents):
                return documents
            self._report_status(self._page_tasks.get(id(page)), "Требуется прикрепить документы: загрузка не подтверждена. Прикрепите файлы или вставьте их полный текст вручную; отправка заблокирована")
            now = asyncio.get_running_loop().time()
            pending = [d for d in documents if d["name"] not in evidence["ready"] and attempts[d["name"]] < 2]
            inputs = page.locator("input[type='file']")
            if pending and now >= next_attempt and await inputs.count():
                retry_documents = []
                for document in pending:
                    name = document["name"]
                    if name in evidence["failed"]:
                        card = page.locator('[data-state="error"],[data-state="failed"]').filter(has_text=name)
                        remove = card.locator('button[aria-label*="Remove"],button[aria-label*="Удалить"],button[aria-label*="Убрать"]')
                        if await remove.count() != 1:
                            continue  # do not fake success by deleting DOM nodes
                        await remove.click()
                    retry_documents.append(document)
                if retry_documents:
                    for document in retry_documents:
                        attempts[document["name"]] += 1
                    try:
                        # Freeze the selected bytes; later filesystem edits
                        # cannot silently change a submitted requirement.
                        await inputs.first.set_input_files([{"name": d["name"], "mimeType": "text/plain", "buffer": d["data"]} for d in retry_documents], timeout=5_000)
                    except Exception:  # noqa: BLE001 - manual repair must remain available.
                        self._report_status(self._page_tasks.get(id(page)), "Ошибка загрузки документов; прикрепите их вручную. Отправка не выполнена")
                    next_attempt = now + 30.0
            await page.wait_for_timeout(500)

    @staticmethod
    async def _download_txt_attachment(page, *, baseline_count: int = 0,
                                       timeout_ms: int = 15_000, response=None) -> str:
        """Download the new response's file, never a page-wide user attachment."""
        buttons = (response if response is not None else page).locator(_DOWNLOAD_BUTTON_SELECTOR)
        deadline = asyncio.get_running_loop().time() + max(1_000, int(timeout_ms)) / 1000.0
        button = None
        while asyncio.get_running_loop().time() < deadline:
            try:
                count = await buttons.count()
                if response is not None and count > 1:
                    raise ChatGPTBrowserError("ChatGPT прикрепил несколько файлов; TXT-вложение неоднозначно")
                if count > baseline_count:
                    candidate = buttons.nth(count - 1)
                    if await candidate.is_visible():
                        button = candidate
                        break
            except ChatGPTBrowserError:
                raise
            except Exception:  # noqa: BLE001,S110 - UI can re-render while the file card appears.
                pass
            await page.wait_for_timeout(200)
        if button is None:
            raise ChatGPTBrowserError("ChatGPT не прикрепил новое TXT-вложение со сценарием")
        try:
            async with page.expect_download(timeout=30_000) as download_info:
                await button.click()
            download = await download_info.value
            suggested_filename = str(getattr(download, "suggested_filename", "") or "")
            if Path(suggested_filename).suffix.casefold() != ".txt":
                raise ChatGPTBrowserError("ChatGPT прикрепил файл не в формате TXT")
            path = await download.path()
        except ChatGPTBrowserError:
            raise
        except Exception as exc:
            raise ChatGPTBrowserError("Не удалось скачать TXT-вложение ChatGPT") from exc
        if not path:
            raise ChatGPTBrowserError("ChatGPT не передал путь к скачанному TXT-вложению")
        source = Path(path)
        try:
            text = source.read_bytes().decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ChatGPTBrowserError("TXT-вложение ChatGPT имеет недопустимую кодировку UTF-8") from exc
        except OSError as exc:
            raise ChatGPTBrowserError("Не удалось прочитать скачанное TXT-вложение ChatGPT") from exc
        if not text.strip():
            raise ChatGPTBrowserError("ChatGPT прикрепил пустое TXT-вложение")
        return text

    async def _wait_for_answer(
        self,
        page,
        *,
        baseline_count: int,
        download_baseline_count: int | None = None,
        on_response: Callable | None = None,
    ) -> str:
        deadline = None if self.timeout_seconds is None else asyncio.get_running_loop().time() + self.timeout_seconds
        previous = ""
        stable_since = 0.0
        answers = page.locator(_ASSISTANT_SELECTOR)
        while deadline is None or asyncio.get_running_loop().time() < deadline:
            self._check_cancelled()
            if hasattr(page, "is_closed") and page.is_closed():
                raise ChatGPTBrowserError("Вкладка закрыта пользователем")
            current = ""
            has_new_turn = False
            try:
                count = await answers.count()
                if count > baseline_count:
                    # Only a newly-created assistant turn can satisfy this task.
                    has_new_turn = True
                    response = answers.nth(count - 1)
                    current = await response.inner_text(timeout=2_000)
            except Exception:  # noqa: BLE001 - no answer is normal while the turn is pending.
                current = ""
                has_new_turn = False
            attachment_ready = False
            turn_complete = False
            turn_state = ""
            if has_new_turn:
                try:
                    turn_state = await response.locator(
                        "xpath=ancestor-or-self::*[@data-talvt-turn-state][1]"
                    ).get_attribute("data-talvt-turn-state", timeout=250)
                    turn_complete = turn_state == "complete"
                except Exception:  # noqa: BLE001,S110 - legacy layouts have no completion marker.
                    pass
            if has_new_turn and download_baseline_count is not None:
                try:
                    attachment_ready = await response.locator(_DOWNLOAD_BUTTON_SELECTOR).count() > 0
                except Exception:  # noqa: BLE001 - attachment is optional while generation runs.
                    attachment_ready = False
            now = asyncio.get_running_loop().time()
            if current and current == previous:
                stable_since = stable_since or now
            else:
                stable_since = 0.0
            previous = current
            stop_visible = False
            for selector in (
                "button[data-testid='stop-button']",
                "button[aria-label*='Stop']",
                "button[aria-label*='Останов']",
            ):
                try:
                    stop_visible = stop_visible or await page.locator(selector).is_visible(timeout=250)
                except Exception:  # noqa: BLE001,S110 - selector is optional across ChatGPT UI versions.
                    pass
            file_mode = download_baseline_count is not None
            if (attachment_ready or (turn_complete and not file_mode)) and not stop_visible and turn_state not in {"in_progress", "streaming", "running"}:
                if on_response is not None:
                    on_response(response)
                return current
            if not file_mode and current.strip() and not stop_visible and stable_since and now - stable_since >= 4.0:
                if on_response is not None:
                    on_response(response)
                return current.replace("\r\n", "\n").replace("\r", "\n")
            await page.wait_for_timeout(500)
        raise ChatGPTBrowserError("ChatGPT не вернул новый готовый ответ за отведённое время")

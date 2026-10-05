"""Browser boundary for direct ChatGPT topic scenarios.

The adapter accepts only an operator-configured ChatGPT web route.  It never
uses API keys or an arbitrary URL supplied by a queued topic.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Self
from urllib.parse import urlparse

from .claude import chrome_path
from .config import ChromeSession


class ChatGPTBrowserError(RuntimeError):
    pass


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

    def __init__(self, session: ChromeSession, *, timeout_seconds: int = 900):
        self.session = session
        self.timeout_seconds = max(60, int(timeout_seconds))
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
                accept_downloads=False,
                viewport={"width": 1280, "height": 900},
            )
        except Exception as exc:  # noqa: BLE001 - Playwright exposes multiple runtime exception types.
            await self._close()
            self._raise_browser_error(exc)
        return self

    async def __aexit__(self, *_args) -> None:
        await self._close()

    async def _close(self) -> None:
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
                       requirements_file: str, task) -> str:
        """Send one task in its own confirmed fresh chat and return only its new turn."""
        del task  # identity is used by the queue, never inserted as hidden prose.
        if self._context is None:
            raise ChatGPTBrowserError("Сессия ChatGPT не запущена")
        page = await self._context.new_page()
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
            assistant_count = await page.locator("[data-message-author-role='assistant']").count()
            if requirements_file:
                await self._attach_requirements_file(page, requirements_file)
            await editor.click()
            await editor.fill(message)
            await editor.press("Enter")
            return await self._wait_for_answer(page, baseline_count=assistant_count)
        except ChatGPTBrowserError:
            raise
        except Exception as exc:  # noqa: BLE001 - normalize Playwright transport failures for the UI.
            self._raise_browser_error(exc)
        finally:
            try:
                await page.close()
            except Exception:  # noqa: BLE001,S110 - the tab may already be closed by Chromium.
                pass

    @staticmethod
    async def _start_new_chat(page) -> None:
        """Fail closed unless the tab is demonstrably a fresh conversation."""
        messages = page.locator("[data-message-author-role]")
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
    async def _attach_requirements_file(page, requirements_file: str) -> None:
        source = Path(requirements_file)
        if not source.is_file():
            raise ChatGPTBrowserError("Файл требований не найден. Выберите его заново.")
        inputs = page.locator("input[type='file']")
        try:
            await inputs.first.wait_for(state="attached", timeout=5_000)
            await inputs.first.set_input_files(str(source))
        except Exception as exc:
            raise ChatGPTBrowserError(
                "ChatGPT не показал поле прикрепления файла. Откройте новый чат и повторите запуск."
            ) from exc

    async def _wait_for_answer(self, page, *, baseline_count: int) -> str:
        deadline = asyncio.get_running_loop().time() + self.timeout_seconds
        previous = ""
        stable_since = 0.0
        answers = page.locator("[data-message-author-role='assistant']")
        while asyncio.get_running_loop().time() < deadline:
            current = ""
            try:
                count = await answers.count()
                if count > baseline_count:
                    # Only a newly-created assistant turn can satisfy this task.
                    current = await answers.nth(count - 1).inner_text(timeout=2_000)
            except Exception:  # noqa: BLE001 - no answer is normal while the turn is pending.
                current = ""
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
            if current.strip() and not stop_visible and stable_since and now - stable_since >= 4.0:
                return current.replace("\r\n", "\n").replace("\r", "\n")
            await page.wait_for_timeout(500)
        raise ChatGPTBrowserError("ChatGPT не вернул новый готовый ответ за отведённое время")

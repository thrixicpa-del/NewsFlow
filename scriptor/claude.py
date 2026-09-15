from __future__ import annotations

import asyncio
import os
import subprocess
import time
import re
from pathlib import Path

from .config import ChromeSession


CLAUDE_URL = "https://claude.ai/new"


class ClaudeError(RuntimeError):
    pass


class ClaudeLimitError(ClaudeError):
    pass


def response_has_limit_error(text: str) -> bool:
    value = " ".join((text or "").lower().split())
    markers = (
        "you've reached your limit", "you have reached your limit", "usage limit",
        "message limit", "limit reached", "out of messages", "try again after",
        "достигнут лимит", "лимит сообщений", "лимит исчерпан",
    )
    return any(marker in value for marker in markers)


def chrome_path() -> Path:
    candidates = [
        Path(os.environ.get("PROGRAMFILES", "")) / "Google/Chrome/Application/chrome.exe",
        Path(os.environ.get("PROGRAMFILES(X86)", "")) / "Google/Chrome/Application/chrome.exe",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Google/Chrome/Application/chrome.exe",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise ClaudeError("Google Chrome не найден. Установите Chrome и повторите запуск.")


def open_login_window(session: ChromeSession, url: str = CLAUDE_URL) -> subprocess.Popen:
    session.profile_dir.mkdir(parents=True, exist_ok=True)
    return subprocess.Popen([
        str(chrome_path()), f"--user-data-dir={session.profile_dir}",
        "--no-first-run", "--no-default-browser-check", url or CLAUDE_URL,
    ])


class ClaudeBrowserClient:
    def __init__(self, session: ChromeSession, timeout_seconds: int = 900, chat_url: str = CLAUDE_URL):
        self.session = session
        self.timeout_seconds = timeout_seconds
        self.chat_url = chat_url if chat_url.startswith("https://claude.ai/") else CLAUDE_URL

    async def generate(self, prompt: str, on_progress=None) -> str:
        return await asyncio.to_thread(self._generate_sync, prompt, on_progress)

    async def generate_fresh(self, prompt: str, on_progress=None) -> str:
        return await asyncio.to_thread(self._generate_sync, prompt, on_progress, CLAUDE_URL)

    def _generate_sync(self, prompt: str, on_progress=None, target_url=None) -> str:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise ClaudeError("Компонент управления Chrome не установлен. Переустановите StoryFlow Studio.") from exc

        self.session.profile_dir.mkdir(parents=True, exist_ok=True)
        try:
            with sync_playwright() as pw:
                context = pw.chromium.launch_persistent_context(
                    str(self.session.profile_dir), executable_path=str(chrome_path()),
                    headless=False, args=["--no-first-run", "--no-default-browser-check"],
                    accept_downloads=True,
                    viewport={"width": 1280, "height": 900},
                )
                try:
                    page = context.pages[0] if context.pages else context.new_page()
                    page.goto(target_url or self.chat_url, wait_until="domcontentloaded", timeout=120_000)
                    editor = self._find_editor(page)
                    if editor is None:
                        raise ClaudeError(
                            f"Сессия «{self.session.label}» не вошла в Claude. "
                            "Откройте её на странице «Сессии Chrome», войдите и закройте окно Chrome."
                        )
                    editor.click()
                    editor.fill(prompt)
                    editor.press("Enter")
                    result = self._wait_for_answer(page)
                    if response_has_limit_error(result):
                        raise ClaudeLimitError(f"В сессии «{self.session.label}» закончился лимит Claude")
                    if on_progress:
                        on_progress(result)
                    return result
                finally:
                    context.close()
        except ClaudeError:
            raise
        except Exception as exc:
            message = str(exc)
            if "ProcessSingleton" in message or "profile" in message.lower() and "lock" in message.lower():
                raise ClaudeError(f"Закройте окно Chrome сессии «{self.session.label}» перед запуском.") from exc
            raise ClaudeError(f"Сессия «{self.session.label}»: {message}") from exc

    @staticmethod
    def _find_editor(page):
        selectors = [
            "div[contenteditable='true'][data-testid*='chat']",
            "div[contenteditable='true'].ProseMirror",
            "div[contenteditable='true']",
            "textarea[placeholder]",
        ]
        for selector in selectors:
            locator = page.locator(selector).last
            try:
                locator.wait_for(state="visible", timeout=8_000)
                return locator
            except Exception:
                continue
        return None

    def _wait_for_answer(self, page) -> str:
        deadline = time.monotonic() + self.timeout_seconds
        last_text = ""
        stable_since = time.monotonic()
        quiet_seconds = 30

        def generation_is_active() -> bool:
            selectors = (
                "[data-is-streaming='true']",
                "button[aria-label*='Stop']",
                "button[aria-label*='stop']",
                "button[aria-label*='Останов']",
                "button[data-testid*='stop']",
            )
            for selector in selectors:
                try:
                    locator = page.locator(selector)
                    for index in range(min(locator.count(), 5)):
                        if locator.nth(index).is_visible():
                            return True
                except Exception:
                    continue
            return False

        while time.monotonic() < deadline:
            texts = []
            for selector in (
                "[data-testid*='assistant']",
                "div.font-claude-message",
                "[data-is-streaming]",
            ):
                try:
                    values = [value.strip() for value in page.locator(selector).all_inner_texts() if value.strip()]
                    if values:
                        texts = values
                        break
                except Exception:
                    pass
            current = texts[-1] if texts else ""
            if current and current != last_text:
                last_text = current
                stable_since = time.monotonic()
            elif generation_is_active():
                # Claude может надолго остановить изменение текста, продолжая генерацию.
                # Пока видна кнопка остановки или streaming-флаг, ответ не считаем готовым.
                stable_since = time.monotonic()
            elif current and time.monotonic() - stable_since >= quiet_seconds:
                attachment = self._download_text_attachment(page)
                return attachment or current
            page.wait_for_timeout(1000)
        attachment = self._download_text_attachment(page)
        if attachment:
            return attachment
        if last_text:
            return last_text
        raise ClaudeError("Claude не вернул ответ за отведённое время")

    @staticmethod
    def _decode_text_file(data: bytes) -> str:
        for encoding in ("utf-8-sig", "utf-8", "cp1251"):
            try:
                return data.decode(encoding)
            except UnicodeDecodeError:
                continue
        return data.decode("utf-8", errors="replace")

    def _download_text_attachment(self, page) -> str:
        selectors = (
            "a[download]", "a[href*='download']", "button[aria-label*='Download']",
            "button[aria-label*='download']", "button[aria-label*='Скачать']",
            "[data-testid*='download']",
        )
        candidates = []
        for selector in selectors:
            try:
                locator = page.locator(selector)
                for index in range(max(0, locator.count() - 5), locator.count()):
                    item = locator.nth(index)
                    if item.is_visible():
                        candidates.append(item)
            except Exception:
                continue
        for candidate in reversed(candidates):
            try:
                label = " ".join(filter(None, (
                    candidate.inner_text(timeout=1000), candidate.get_attribute("aria-label"),
                    candidate.get_attribute("title"), candidate.get_attribute("download"),
                )))
                # Prefer explicit TXT controls; generic download controls are allowed because
                # the downloaded filename is checked before reading.
                if label and not (re.search(r"\.txt\b", label, re.IGNORECASE)
                                  or "download" in label.lower() or "скач" in label.lower()):
                    continue
                with page.expect_download(timeout=5000) as info:
                    candidate.click(timeout=3000)
                download = info.value
                if not download.suggested_filename.lower().endswith(".txt"):
                    continue
                path = download.path()
                if path:
                    content = self._decode_text_file(Path(path).read_bytes()).strip()
                    if content:
                        return content
            except Exception:
                continue
        return ""


class ClaudeSessionPool:
    def __init__(self, sessions: list[ChromeSession], chat_url: str = CLAUDE_URL):
        if not sessions:
            raise ValueError("Включите хотя бы одну Chrome-сессию")
        self.clients = [ClaudeBrowserClient(item, chat_url=chat_url) for item in sessions]
        self._queue: asyncio.Queue[ClaudeBrowserClient] | None = None

    async def generate(self, prompt: str, on_progress=None) -> str:
        if self._queue is None:
            self._queue = asyncio.Queue()
            for client in self.clients:
                self._queue.put_nowait(client)
        client = await self._queue.get()
        try:
            return await client.generate(prompt, on_progress)
        finally:
            self._queue.put_nowait(client)

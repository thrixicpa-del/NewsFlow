"""Visible, per-channel Chrome automation for YouTube Studio.

This adapter deliberately has no access to NewsFlow OAuth tokens.  It opens
only the already associated persistent Chrome profile and records work as
complete only after the relevant Studio action succeeds.  If Studio changes
its UI or the profile is busy, callers receive a retryable error instead of a
false "published" state.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
import re
from typing import Mapping

from .claude import chrome_path


_TERMINAL = {"scheduled", "done", "failed", "skipped"}


class StudioAutomationError(RuntimeError):
    """A visible Studio action was not confirmed and may be retried later."""


def studio_editor_url(video_id: str) -> str:
    """Build the Studio editor URL for one YouTube video identifier only."""

    value = str(video_id or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9_-]{6,64}", value):
        raise StudioAutomationError("Некорректный идентификатор ролика для редактора Studio.")
    return f"https://studio.youtube.com/video/{value}/editor"


def studio_details_url(video_id: str) -> str:
    """Build the Studio details route used before opening the editor tab."""

    value = str(video_id or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9_-]{6,64}", value):
        raise StudioAutomationError("Некорректный идентификатор ролика для страницы сведений Studio.")
    return f"https://studio.youtube.com/video/{value}/edit"


def studio_shell_loaded(visible_text: str) -> bool:
    """Recognise a rendered Studio shell, not merely a loaded blank document."""

    return len(" ".join(str(visible_text or "").split())) >= 12


def studio_control_labels(kind: str) -> str:
    """Current Russian YouTube Studio names for editor engagement sections."""

    labels = {
        "cards": "Подсказки",
        "end-screen": "Конечные заставки",
    }
    if kind not in labels:
        raise ValueError("Неизвестный раздел редактора Studio")
    return labels[kind]


def _open_editor_section(page, kind: str) -> None:
    """Click the visible plus control on a current Studio editor row."""

    label = studio_control_labels(kind)
    opened = page.locator("body").evaluate("""(needle) => {
      const visible = (node) => Boolean(node) && node.getClientRects().length > 0;
      const matches = Array.from(document.querySelectorAll('*')).filter((node) => {
        const text = (node.innerText || '').replace(/\\s+/g, ' ').trim();
        return text === needle && !Array.from(node.children).some((child) =>
          (child.innerText || '').replace(/\\s+/g, ' ').trim() === needle);
      });
      for (const label of matches) {
        let row = label;
        for (let level = 0; level < 5 && row; level += 1, row = row.parentElement) {
          const controls = Array.from(row.querySelectorAll('button,[role="button"]')).filter(visible);
          if (controls.length) {
            controls[controls.length - 1].click();
            return true;
          }
        }
      }
      return false;
    }""", label)
    if not opened:
        raise StudioAutomationError(f"В новом редакторе не найдена кнопка + для раздела «{label}».")


def end_screen_requires_editor_entry(visible_text: str) -> bool:
    """Whether Studio is showing the legacy end-screen handoff panel."""

    return "перейти к редактору" in " ".join(str(visible_text or "").casefold().split())


def studio_transition_label() -> str:
    return "Перейти к редактору"


def _click_exact_visible_button(page, label: str) -> bool:
    """Click one visible button by its accessible label, then DOM fallback."""

    try:
        control = page.get_by_label(label, exact=True)
        if control.is_visible(timeout=1_500):
            try:
                control.click(timeout=10_000)
                return True
            except Exception:
                # Studio's warm-welcome button is occasionally covered by its
                # already mounted editor canvas.  The label is unique and was
                # verified visible, so force only this exact transition.
                control.click(timeout=10_000, force=True)
                return True
    except Exception:
        pass

    return bool(page.locator("body").evaluate("""(needle) => {
      const normalize = (value) => (value || '').replace(/\\s+/g, ' ').trim();
      const visible = (node) => Boolean(node) && node.getClientRects().length > 0;
      const controls = Array.from(document.querySelectorAll('button,[role="button"],a'));
      const control = controls.find((node) => visible(node) && normalize(node.innerText) === needle);
      if (!control) return false;
      control.click();
      return true;
    }""", label))


def _wait_for_studio_shell(page, *, timeout_seconds: int = 25) -> None:
    """Wait for Studio's client-side shell after navigation has committed."""

    for _attempt in range(timeout_seconds * 4):
        try:
            if studio_shell_loaded(page.locator("body").inner_text(timeout=1_000)):
                return
        except Exception:
            pass
        page.wait_for_timeout(250)
    raise StudioAutomationError("YouTube Studio открыл пустую страницу и не загрузил интерфейс. Проверьте вход в профиль канала.")


def planned_studio_actions(task: Mapping[str, object], *, action_kinds: set[str] | None = None) -> list[dict]:
    """Return only non-terminal actions, in safe post → cards → end-screen order."""

    plan = dict(task.get("plan") or {})
    draft = dict(task.get("postDraft") or {})
    actions: list[dict] = []
    if (action_kinds is None or "post" in action_kinds) and str(dict(task.get("post") or {}).get("status", "pending")) not in _TERMINAL and draft.get("text"):
        actions.append({"kind": "post", "text": str(draft.get("text", "")),
                        "videoUrl": str(draft.get("videoUrl", "")),
                        "publishAt": str(task.get("publishAt", ""))})
    if (action_kinds is None or "cards" in action_kinds) and str(dict(task.get("cards") or {}).get("status", "pending")) not in _TERMINAL:
        cards = list(plan.get("cards") or [])
        if cards:
            actions.append({"kind": "cards", "cards": cards})
    if (action_kinds is None or "end-screen" in action_kinds) and str(dict(task.get("endScreen") or {}).get("status", "pending")) not in _TERMINAL:
        end_screen = dict(plan.get("endScreen") or {})
        if end_screen and str(end_screen.get("status", "")) != "skipped":
            actions.append({"kind": "end-screen", "startSeconds": end_screen.get("startSeconds"),
                            "items": list(end_screen.get("items") or [])})
    return actions


def _first(page, selectors: list[str]):
    for selector in selectors:
        locator = page.locator(selector).first
        try:
            if locator.is_visible(timeout=1_500):
                return locator
        except Exception:
            continue
    raise StudioAutomationError("Не удалось найти нужный элемент в YouTube Studio. Обновите Studio и повторите шаг.")


def _click_text(page, labels: list[str]) -> None:
    for label in labels:
        try:
            locator = page.get_by_text(re.compile(label, re.IGNORECASE)).first
            if locator.is_visible(timeout=1_500):
                locator.click(timeout=10_000)
                return
        except Exception:
            continue
    details = ""
    try:
        tokens = [re.sub(r"[^a-zа-яё]", "", label.casefold())[:8] for label in labels]
        controls = page.locator("body").evaluate("""(tokens) => Array.from(document.querySelectorAll('*'))
          .filter((node) => tokens.some((token) => token && (node.innerText || '').toLowerCase().includes(token)))
          .slice(-8)
          .map((node) => `${node.tagName}[role=${node.getAttribute('role') || ''};aria=${node.getAttribute('aria-label') || ''};text=${(node.innerText || '').replace(/\\s+/g, ' ').slice(0, 90)}]`)
          .join(' | ')""", tokens)
        if controls:
            details = f" Найдено на экране: {controls[:700]}"
    except Exception:
        pass
    raise StudioAutomationError(
        "В Studio не найдена или недоступна кнопка "
        f"({', '.join(labels)}). Задание оставлено для повторной попытки.{details}"
    )


def _parse_schedule(value: str) -> tuple[str, str]:
    try:
        point = datetime.fromisoformat(value)
    except ValueError as exc:
        raise StudioAutomationError("Для отложенного поста не задано корректное время публикации.") from exc
    return point.strftime("%d.%m.%Y"), point.strftime("%H:%M")


def _publish_scheduled_post(page, action: Mapping[str, object]) -> None:
    """Create a scheduled Community post with the matching YouTube video URL.

    Studio creates an embedded video preview when the exact watch URL is
    pasted into the composer.  The link is retained in the post text as a
    fallback; the action is not marked complete until the schedule controls
    have been submitted.
    """

    _click_text(page, [r"создать.*запись", r"create.*post"])
    composer = _first(page, ["textarea", "div[contenteditable='true']"])
    composer.click()
    composer.fill(str(action.get("text", "")))
    video_url = str(action.get("videoUrl", "")).strip()
    if video_url:
        composer.press("Control+Enter")
        composer.press("Enter")
        composer.press_sequentially(video_url)
        page.wait_for_timeout(1_000)
    _click_text(page, [r"опубликовать", r"publish"])
    _click_text(page, [r"запланир", r"schedule"])
    date, clock = _parse_schedule(str(action.get("publishAt", "")))
    date_input = _first(page, ["input[type='date']", "input[aria-label*='дата' i]", "input[aria-label*='date' i]"])
    time_input = _first(page, ["input[type='time']", "input[aria-label*='время' i]", "input[aria-label*='time' i]"])
    date_input.fill(date)
    time_input.fill(clock)
    _click_text(page, [r"запланир", r"schedule"])


def _apply_cards(page, action: Mapping[str, object]) -> None:
    _open_editor_section(page, "cards")
    for card in list(action.get("cards") or []):
        _click_text(page, [r"добавить.*карточк", r"add.*card"])
        _click_text(page, [r"видео", r"video"])
        video_id = str(dict(card).get("videoId", "")).strip()
        if not video_id:
            raise StudioAutomationError("В плане карточки отсутствует идентификатор видео.")
        search = _first(page, ["input[type='search']", "input[aria-label*='поиск' i]", "input[aria-label*='search' i]"])
        search.fill(video_id)
        _click_text(page, [re.escape(video_id), r"выбрать", r"select"])
        timestamp = _first(page, ["input[aria-label*='время' i]", "input[aria-label*='time' i]"])
        timestamp.fill(str(int(float(dict(card).get("atSeconds", 0) or 0))))
    _click_text(page, [r"сохранить", r"save"])


def _apply_end_screen(page, action: Mapping[str, object]) -> None:
    if end_screen_requires_editor_entry(page.locator("body").inner_text(timeout=3_000)):
        if not _click_exact_visible_button(page, studio_transition_label()):
            raise StudioAutomationError("Не найдена большая кнопка перехода в новый видеоредактор Studio.")
        for _attempt in range(40):
            current_text = page.locator("body").inner_text(timeout=1_000)
            if not end_screen_requires_editor_entry(current_text):
                break
            page.wait_for_timeout(250)
        else:
            raise StudioAutomationError("Studio не открыл новый редактор после нажатия «Перейти к редактору».")
    _open_editor_section(page, "end-screen")
    # The Studio editor owns the exact positioning controls.  Insert elements
    # one by one so a changed template can never silently replace a video's
    # existing end screen wholesale.
    for item in list(action.get("items") or []):
        kind = str(dict(item).get("kind", ""))
        if kind == "best-for-viewer":
            _click_text(page, [r"добавить.*элемент", r"add.*element"])
            _click_text(page, [r"лучшее.*зрител", r"best.*viewer"])
        elif kind == "subscribe":
            _click_text(page, [r"добавить.*элемент", r"add.*element"])
            _click_text(page, [r"подпис", r"subscribe"])
        elif kind == "video":
            _click_text(page, [r"добавить.*элемент", r"add.*element"])
            _click_text(page, [r"видео", r"video"])
            search = _first(page, ["input[type='search']", "input[aria-label*='поиск' i]", "input[aria-label*='search' i]"])
            search.fill(str(dict(item).get("videoId", "")))
            _click_text(page, [r"выбрать", r"select"])
        elif kind == "playlist":
            _click_text(page, [r"добавить.*элемент", r"add.*element"])
            _click_text(page, [r"плейлист", r"playlist"])
            search = _first(page, ["input[type='search']", "input[aria-label*='поиск' i]", "input[aria-label*='search' i]"])
            search.fill(str(dict(item).get("playlistId", "")))
            _click_text(page, [r"выбрать", r"select"])
    _click_text(page, [r"сохранить", r"save"])


def _open_video_editor(page, video_id: str) -> None:
    """Follow Studio's supported Details → Editor path for one video."""

    page.goto(studio_details_url(video_id), wait_until="domcontentloaded", timeout=120_000)
    _wait_for_studio_shell(page)
    # Current Studio repeats the word "Редактор" in nested non-interactive
    # drawer containers before the actual navigation anchor.  Select only the
    # interactive menu item; a text locator can click a harmless LI/DIV.
    editor = page.get_by_role("menuitem", name="Редактор", exact=True)
    if not editor.is_visible(timeout=1_500):
        raise StudioAutomationError("В Studio недоступен пункт меню «Редактор».")
    editor.click(timeout=10_000)
    for _attempt in range(40):
        if "/editor" in page.url:
            return
        page.wait_for_timeout(250)
    raise StudioAutomationError("Studio не открыл вкладку «Редактор» со страницы сведений ролика.")


def execute_studio_task(
    task: Mapping[str, object], *, profile_dir: Path, youtube_channel_id: str,
    action_kinds: set[str] | None = None,
) -> list[str]:
    """Run planned actions in one visible, persistent Chrome profile.

    The caller updates status only after this function returns each completed
    action.  Closing the context preserves the Chrome profile's cookies and
    history; it never deletes or substitutes a user profile.
    """

    if not youtube_channel_id:
        raise StudioAutomationError("У канала нет подтверждённого YouTube ID.")
    actions = planned_studio_actions(task, action_kinds=action_kinds)
    if not actions:
        return []
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise StudioAutomationError("Компонент Playwright для Studio не установлен.") from exc
    profile_dir.mkdir(parents=True, exist_ok=True)
    completed: list[str] = []
    playwright = sync_playwright().start()
    page = None
    try:
        context = playwright.chromium.launch_persistent_context(
            str(profile_dir), executable_path=str(chrome_path()), headless=False,
            args=["--no-first-run", "--no-default-browser-check",
                  "--disable-background-timer-throttling", "--disable-backgrounding-occluded-windows"],
            viewport={"width": 1280, "height": 900},
        )
        page = context.new_page()
        page.goto(f"https://studio.youtube.com/channel/{youtube_channel_id}", wait_until="domcontentloaded", timeout=120_000)
        _wait_for_studio_shell(page)
        for action in actions:
            if action["kind"] == "post":
                _publish_scheduled_post(page, action)
            elif action["kind"] == "cards":
                _open_video_editor(page, str(task.get("videoId", "")))
                _apply_cards(page, action)
            elif action["kind"] == "end-screen":
                _open_video_editor(page, str(task.get("videoId", "")))
                _apply_end_screen(page, action)
            completed.append(str(action["kind"]))
        context.close()
    except StudioAutomationError as exc:
        # Keep a compact, local diagnostic for the retry queue. It tells us
        # whether Studio redirected to login, opened a blocking dialog, or
        # renamed a control without storing page source or credentials.
        if page is not None:
            try:
                visible = " ".join(page.locator("body").inner_text(timeout=2_000).split())[:700]
                raise StudioAutomationError(f"{exc} URL: {page.url}. Экран: {visible}") from exc
            except StudioAutomationError:
                raise
            except Exception:
                pass
        raise
    except Exception as exc:
        raise StudioAutomationError(f"Studio не подтвердил действие: {exc}") from exc
    finally:
        playwright.stop()
    return completed

"""Pure contracts for direct, browser-authenticated topic scenario runs.

This module deliberately knows nothing about OpenAI, Planner or Writer.  It
only turns operator-owned settings plus one durable ProductionItem identity
into the message and route that a browser adapter may later dispatch.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Protocol


def _clean_text(value: object) -> str:
    return str(value or "").strip()


def _format_characters(value: int) -> str:
    return f"{int(value):,}".replace(",", " ")


@dataclass(frozen=True)
class BrowserScenarioSettings:
    project_url: str = ""
    requirements_mode: str = "text"
    requirements_text: str = ""
    requirements_file: str = ""
    companion_prompt: str = ""
    minimum_chars: int = 0
    maximum_chars: int = 0
    concurrency: int = 1
    prompt_overrides: dict[str, str] = field(default_factory=dict)
    url_overrides: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class BrowserTopicTask:
    production_item_id: str
    title: str
    queue_index: int = -1
    existing_scenario: str = ""

    @property
    def browser_input_title(self) -> str:
        """The browser route accepts a topic only, never prior scenario prose."""
        return _clean_text(self.title)


@dataclass(frozen=True)
class BrowserTopicRoute:
    project_url: str
    companion_prompt: str


@dataclass(frozen=True)
class BrowserTopicCompletion:
    production_item_id: str
    title: str
    text: str


@dataclass(frozen=True)
class BrowserTopicFailure:
    """Truthful per-topic browser failure; no hidden second generation."""

    production_item_id: str
    title: str
    error: str


class BrowserTopicTransport(Protocol):
    async def generate(self, *, project_url: str, message: str, requirements_file: str,
                       task: BrowserTopicTask) -> str: ...


def resolve_topic_route(settings: BrowserScenarioSettings, task: BrowserTopicTask) -> BrowserTopicRoute:
    """Resolve only against the immutable ProductionItem identity."""
    production_item_id = _clean_text(task.production_item_id)
    return BrowserTopicRoute(
        project_url=_clean_text(settings.url_overrides.get(production_item_id, settings.project_url)),
        companion_prompt=_clean_text(
            settings.prompt_overrides.get(production_item_id, settings.companion_prompt)
        ),
    )


def build_browser_message(settings: BrowserScenarioSettings, task: BrowserTopicTask) -> str:
    """Compose the exact user-visible browser message from UI-owned values.

    The operator's editable prompt is not asked to carry topic or length.  The
    durable queue item and UI controls own those values and are appended here.
    """
    title = task.browser_input_title
    if not title:
        raise ValueError("У темы нет названия")
    route = resolve_topic_route(settings, task)
    if not route.companion_prompt:
        raise ValueError("Заполните сопроводительный prompt")
    minimum = max(0, int(settings.minimum_chars or 0))
    maximum = max(0, int(settings.maximum_chars or 0))
    if not minimum or not maximum or minimum > maximum:
        raise ValueError("Укажите корректный диапазон символов")

    sections: list[str] = []
    if settings.requirements_mode == "text" and _clean_text(settings.requirements_text):
        sections.append("Требования к стилю и структуре:\n" + _clean_text(settings.requirements_text))
    elif settings.requirements_mode == "file":
        sections.append("Используй прикреплённый файл как шаблон требований к стилю и структуре.")

    sections.extend((
        f"Тема сценария:\n{title}",
        route.companion_prompt,
        (
            "Напиши цельный оригинальный новостной сценарий объёмом "
            f"{_format_characters(minimum)}–{_format_characters(maximum)} символов."
        ),
        (
            "Не указывай дату и время. Не добавляй приветствие, план, "
            "комментарии автора и служебные пояснения. Выдай только готовый "
            "текст сценария."
        ),
    ))
    return "\n\n".join(section for section in sections if section.strip())


async def run_browser_topic_tasks(
    settings: BrowserScenarioSettings,
    tasks: list[BrowserTopicTask],
    transport: BrowserTopicTransport,
) -> list[BrowserTopicCompletion | BrowserTopicFailure]:
    """Run topic-bound browser work with slots, never queue-index routing.

    The concrete Playwright adapter can map each slot to one tab.  Keeping the
    scheduling seam pure makes the identity and concurrency contract testable
    without an authenticated browser or a provider call.
    """
    concurrency = max(1, int(settings.concurrency or 1))
    slots = asyncio.Semaphore(concurrency)

    async def run_one(task: BrowserTopicTask) -> BrowserTopicCompletion:
        route = resolve_topic_route(settings, task)
        if not route.project_url:
            raise ValueError("Укажите URL проекта ChatGPT")
        async with slots:
            text = await transport.generate(
                project_url=route.project_url,
                message=build_browser_message(settings, task),
                requirements_file=(settings.requirements_file
                                   if settings.requirements_mode == "file" else ""),
                task=task,
            )
        return BrowserTopicCompletion(
            production_item_id=_clean_text(task.production_item_id),
            title=task.browser_input_title,
            text=_clean_text(text),
        )

    outcomes = await asyncio.gather(*(run_one(task) for task in tasks), return_exceptions=True)
    return [
        outcome if isinstance(outcome, BrowserTopicCompletion) else BrowserTopicFailure(
            production_item_id=_clean_text(task.production_item_id),
            title=task.browser_input_title,
            error=str(outcome) or "ChatGPT не вернул текст сценария",
        )
        for task, outcome in zip(tasks, outcomes)
    ]

from __future__ import annotations

import asyncio
import inspect
import math
import threading
from dataclasses import dataclass
from enum import Enum
from typing import Callable

from .core import ScenarioRequest


def looks_like_action_required(text: str) -> bool:
    if not text:
        return False
    sample = " ".join(text.strip().lower().split())[:2500]
    refusal_prefixes = (
        "я не могу", "я не смогу", "к сожалению, я не", "не могу помочь",
        "не могу выполнить", "я вынужден отказаться", "я должна отказаться",
        "я не буду", "i can't", "i cannot", "i’m unable", "i'm unable",
        "unable to help", "i can’t assist", "i can't assist", "i must refuse",
        "i won’t", "i won't", "cannot comply",
    )
    requests = (
        "переформулируйте", "измените тему", "уточните тему", "please rephrase",
        "change the topic", "clarify the topic", "не могу продолжить", "не могу создать",
        "не могу сгенерировать", "не могу написать", "не могу предоставить",
        "i can't help with", "i cannot help with", "i can’t help with",
        "не могу помочь с этим", "не могу выполнить этот запрос",
        "не могу выполнить вашу просьбу", "не могу продолжить выполнение",
        "не могу создать такой", "не могу написать такой", "не могу повторить",
        "не могу перезапустить", "не могу выполнить задачу", "я отказываюсь",
        "это противоречит", "нарушает правила", "по соображениям безопасности",
        "i can't comply", "i can’t comply", "i cannot fulfill", "i cannot complete",
        "against my guidelines", "violates policy", "for safety reasons",
    )
    # В полноценном сценарии фразы персонажей вроде «я не могу» допустимы. Но короткий
    # Ответ текстового провайдера с отказом нельзя принимать за готовый сценарий.
    short_refusal = len(sample) < 700 and any(marker in sample[:600] for marker in (
        "я не могу", "не могу помочь", "не могу выполнить", "не могу создать",
        "не могу написать", "i can't", "i can’t", "i cannot", "unable to",
    ))
    return (sample.startswith(refusal_prefixes) or short_refusal
            or any(marker in sample[:1600] for marker in requests))


class RunState(str, Enum):
    WAITING = "Ожидает"
    RUNNING = "В обработке"
    DONE = "Готово"
    ERROR = "Ошибка"
    PAUSED = "Нужно действие"
    CANCELLED = "Остановлено"


@dataclass
class Job:
    request: ScenarioRequest
    state: RunState = RunState.WAITING
    result: str = ""
    error: str = ""
    actual_chars: int = 0
    length_status: str = ""
    length_repair_attempts: int = 0


def scenario_length_status(request: ScenarioRequest, text: str) -> tuple[str, int]:
    """Return the durable script-length state owned by the Python runtime.

    Empty bounds deliberately mean that an older preset has no length contract;
    it remains a normal finished scenario instead of being retroactively failed.
    """
    actual_chars = len(str(text or "").strip())
    if not request.allowed_min and not request.allowed_max:
        return "", actual_chars
    if request.allowed_min and actual_chars < request.allowed_min:
        return "SHORT", actual_chars
    if request.allowed_max and actual_chars > request.allowed_max:
        return "LONG", actual_chars
    return "READY", actual_chars


def scenario_length_requirement(request: ScenarioRequest) -> str:
    """Human-readable bounds for progress/errors without inventing a missing side."""
    if request.allowed_min and request.allowed_max:
        return f"{request.allowed_min}–{request.allowed_max} знаков"
    if request.allowed_min:
        return f"не менее {request.allowed_min} знаков"
    if request.allowed_max:
        return f"не более {request.allowed_max} знаков"
    return "без ограничения длины"


def scenario_output_token_budget(request: ScenarioRequest) -> int | None:
    """Reserve enough Responses output for the requested character contract.

    ``max_output_tokens`` also includes model reasoning tokens, so this uses a
    conservative 1.25 characters-per-token estimate plus one 1,024-token
    reserve and rounds up to a whole 1,024-token block.  The upper cap keeps a
    malformed preset from issuing an unexpectedly expensive request.
    """
    expected_chars = max(0, int(request.target_chars or 0), int(request.allowed_min or 0))
    if not expected_chars:
        return None
    requested = math.ceil(expected_chars / 1.25) + 1024
    return min(32768, max(2048, math.ceil(requested / 1024) * 1024))


def scenario_length_repair_instruction(request: ScenarioRequest) -> str:
    """Provider instruction that preserves one-sided contracts correctly."""
    target = f" Цель: {request.target_chars} знаков." if request.target_chars else ""
    if request.allowed_min and request.allowed_max:
        return (
            f"Верни только готовый сценарий длиной строго от {request.allowed_min} "
            f"до {request.allowed_max} знаков.{target}"
        )
    if request.allowed_min:
        return f"Верни только готовый сценарий длиной не менее {request.allowed_min} знаков.{target}"
    if request.allowed_max:
        return f"Верни только готовый сценарий длиной не более {request.allowed_max} знаков.{target}"
    return "Верни только полный готовый сценарий."


def scenario_length_continuation_instruction(request: ScenarioRequest, actual_chars: int) -> str:
    """Tell the provider to extend one short result instead of restarting it."""
    needed_total = max(request.target_chars, request.allowed_min)
    remaining = max(1, needed_total - actual_chars)
    maximum = max(0, request.allowed_max - actual_chars) if request.allowed_max else 0
    upper_bound = f" Не добавляй более {maximum} знаков." if maximum else ""
    return (
        "Это продолжение уже написанного сценария, а не новая версия. ПРОДОЛЖИ текст строго с места, "
        "на котором он заканчивается: не повторяй начало, не пересказывай готовые абзацы и не добавляй "
        "заголовки или комментарии. "
        f"Уже сохранено {actual_chars} знаков; добавь примерно {remaining} знаков, чтобы общий текст "
        f"соответствовал требованию {scenario_length_requirement(request)}.{upper_bound} "
        "Перед отправкой сам проверь длину добавленного продолжения и помни: NewsFlow склеит оба фрагмента "
        "и проверит итог через len(text.strip()). Верни только следующий фрагмент сценария."
    )




class ParallelRunner:
    def __init__(self, client, max_concurrency: int = 8, on_change: Callable[[Job], None] | None = None):
        self.client = client
        self.max_concurrency = max(1, min(max_concurrency, 100))
        self.semaphore = asyncio.Semaphore(self.max_concurrency)
        self.on_change = on_change
        self._paused = threading.Event()
        self._cancelled = threading.Event()

    def pause(self):
        self._paused.set()

    def resume(self):
        self._paused.clear()

    def cancel(self):
        self._cancelled.set()
        self._paused.clear()

    @property
    def is_paused(self) -> bool:
        return self._paused.is_set()

    def _notify(self, job: Job):
        if self.on_change:
            self.on_change(job)

    @staticmethod
    def _accepts_keyword(method, keyword: str) -> bool:
        """Keep lightweight legacy adapters usable without hiding provider errors."""
        try:
            parameters = inspect.signature(method).parameters.values()
        except (TypeError, ValueError):
            return False
        return any(parameter.name == keyword or parameter.kind is parameter.VAR_KEYWORD
                   for parameter in parameters)

    async def _generate_for_request(self, method, prompt: str, request: ScenarioRequest) -> str:
        budget = scenario_output_token_budget(request)
        if budget and self._accepts_keyword(method, "max_output_tokens"):
            return await method(prompt, max_output_tokens=budget)
        return await method(prompt)

    async def _repair_length_if_needed(self, job: Job) -> bool:
        """Make at most two explicit repairs before asking the operator to decide."""
        status, actual_chars = scenario_length_status(job.request, job.result)
        job.length_status = status
        job.actual_chars = actual_chars
        if status not in {"SHORT", "LONG"}:
            job.length_repair_attempts = 0
            return True

        generate_fresh = getattr(self.client, "generate_fresh", self.client.generate)
        for attempt in range(1, 3):
            job.length_repair_attempts = attempt
            job.error = (
                f"Длина {actual_chars} знаков вне требования "
                f"{scenario_length_requirement(job.request)}. "
                f"Корректировка длины {attempt}/2."
            )
            self._notify(job)
            if status == "SHORT":
                repair_prompt = (
                    f"{scenario_length_continuation_instruction(job.request, actual_chars)}\n\n"
                    f"УЖЕ НАПИСАННЫЙ ТЕКСТ:\n{job.result.strip()}"
                )
            else:
                repair_prompt = (
                    "Это новая отдельная редакторская задача. Перепиши сценарий целиком по исходному заданию. "
                    f"{scenario_length_repair_instruction(job.request)} "
                    "ПЕРЕД ОТПРАВКОЙ ФИНАЛЬНОГО ОТВЕТА сам проверь длину готового сценария "
                    "по правилу Python len(text.strip()); не печатай собственный подсчет символов и не считай "
                    "его доказательством соответствия. NewsFlow после ответа независимо повторит ту же проверку. "
                    "Не добавляй комментарии, объяснения, заголовки проверки длины или служебный текст.\n\n"
                    f"ИСХОДНОЕ ЗАДАНИЕ:\n{job.request.prompt}"
                )
            repaired_text = await self._generate_for_request(generate_fresh, repair_prompt, job.request)
            if looks_like_action_required(repaired_text):
                job.length_status = "FAILED"
                job.actual_chars = len(str(repaired_text or "").strip())
                job.state = RunState.PAUSED
                job.error = "Текстовый агент не вернул сценарий при корректировке длины"
                return False
            if status == "SHORT":
                job.result = f"{job.result.rstrip()}\n\n{repaired_text.strip()}"
            else:
                job.result = repaired_text
            status, actual_chars = scenario_length_status(job.request, job.result)
            job.length_status = status
            job.actual_chars = actual_chars
            if status == "READY":
                return True

        job.state = RunState.PAUSED
        job.error = (
            f"После {job.length_repair_attempts} корректировок длина сценария "
            f"осталась {job.actual_chars} знаков; требуется "
            f"{scenario_length_requirement(job.request)}. Проверьте текст и запустите выбранный сценарий повторно."
        )
        return False

    async def _run_one(self, job: Job) -> Job:
        async with self.semaphore:
            job.state = RunState.RUNNING
            job.error = ""
            self._notify(job)
            try:
                job.result = await self._generate_for_request(self.client.generate, job.request.prompt, job.request)
                refused = looks_like_action_required(job.result)
                for attempt in range(1, 3):
                    if not refused:
                        break
                    job.error = f"Повтор {attempt}/2 — повторный запрос к текстовому агенту"
                    self._notify(job)
                    retry_prompt = (
                        "Это новая отдельная задача. Сразу выполни её полностью и не обсуждай предыдущие ответы. "
                        "Если отдельная деталь недопустима, молча замени только её на безопасный близкий вариант, "
                        "но обязательно создай результат. Не задавай вопросов и не объясняй ограничения. "
                        "Верни только полный готовый текст.\n\n"
                        f"ЗАДАЧА:\n{job.request.prompt}"
                    )
                    generate_fresh = getattr(self.client, "generate_fresh", self.client.generate)
                    job.result = await self._generate_for_request(generate_fresh, retry_prompt, job.request)
                    refused = looks_like_action_required(job.result)
                if refused:
                    generate_openai = getattr(self.client, "generate_openai", None)
                    if generate_openai is not None:
                        job.error = "Агент не вернул готовый сценарий — задача передана следующему ключу ChatGPT API"
                        self._notify(job)
                        openai_prompt = (
                            "Напиши полный готовый сценарий по заданию ниже. Не задавай уточняющих вопросов. "
                            "Если отдельную формулировку нужно смягчить, самостоятельно используй ближайший "
                            "безопасный вариант. Верни только готовый сценарий без комментариев.\n\n"
                            f"ЗАДАЧА:\n{job.request.prompt}"
                        )
                        job.result = await self._generate_for_request(generate_openai, openai_prompt, job.request)
                        refused = looks_like_action_required(job.result)
                    if refused:
                        job.state = RunState.PAUSED
                        job.error = "Текстовый агент и доступные ключи ChatGPT API не вернули готовый сценарий"
                    else:
                        if await self._repair_length_if_needed(job):
                            job.state = RunState.DONE
                            job.error = ""
                else:
                    if await self._repair_length_if_needed(job):
                        job.state = RunState.DONE
                        job.error = ""
            except Exception as exc:
                job.state = RunState.ERROR
                job.error = str(exc)
                job.result = getattr(exc, "response", job.result)
            self._notify(job)
            return job

    async def run(self, requests: list[ScenarioRequest]) -> list[Job]:
        jobs = [Job(request) for request in requests]
        if not jobs:
            return jobs
        work: asyncio.Queue[Job | None] = asyncio.Queue()
        for job in jobs:
            work.put_nowait(job)

        async def worker():
            while True:
                job = await work.get()
                try:
                    if job is None:
                        return
                    while self._paused.is_set() and not self._cancelled.is_set():
                        await asyncio.sleep(0.05)
                    if self._cancelled.is_set():
                        job.state = RunState.CANCELLED
                        self._notify(job)
                        continue
                    await self._run_one(job)
                finally:
                    work.task_done()

        worker_count = min(self.max_concurrency, len(jobs))
        workers = [asyncio.create_task(worker()) for _ in range(worker_count)]
        await work.join()
        for _ in workers:
            work.put_nowait(None)
        await asyncio.gather(*workers)
        return jobs

    async def retry(self, job: Job) -> Job:
        return await self._run_one(job)

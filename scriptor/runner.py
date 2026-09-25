from __future__ import annotations

import asyncio
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

    async def _validate_length(self, job: Job) -> bool:
        """Validate one provider response; never regenerate solely to change its length."""
        status, actual_chars = scenario_length_status(job.request, job.result)
        job.length_status = status
        job.actual_chars = actual_chars
        job.length_repair_attempts = 0
        if status in {"SHORT", "LONG"}:
            job.state = RunState.ERROR
            job.error = (
                f"Длина {actual_chars} знаков вне требования "
                f"{scenario_length_requirement(job.request)}. "
                "Автоматическое переписывание по длине отключено."
            )
            return False
        return True

    async def _run_one(self, job: Job) -> Job:
        async with self.semaphore:
            job.state = RunState.RUNNING
            job.error = ""
            self._notify(job)
            try:
                job.result = await self.client.generate(job.request.prompt)
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
                    job.result = await generate_fresh(retry_prompt)
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
                        job.result = await generate_openai(openai_prompt)
                        refused = looks_like_action_required(job.result)
                    if refused:
                        job.state = RunState.PAUSED
                        job.error = "Текстовый агент и доступные ключи ChatGPT API не вернули готовый сценарий"
                    else:
                        if await self._validate_length(job):
                            job.state = RunState.DONE
                            job.error = ""
                else:
                    if await self._validate_length(job):
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

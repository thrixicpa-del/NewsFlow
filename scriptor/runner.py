from __future__ import annotations

import asyncio
import inspect
import math
import re
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .core import ScenarioRequest
from .story_planner import (
    StoryPlan,
    StoryPlanCapacityInsufficient,
    build_story_planner_prompt,
    build_story_writer_prompt,
    calculate_story_part_targets,
    parse_story_plan_response,
    story_plan_from_dict,
)


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
    story_plan: dict[str, Any] | None = None
    accepted_story_parts: list[dict[str, Any]] = field(default_factory=list)
    story_planner_status: str = ""


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


def scenario_output_token_budget(request: ScenarioRequest, expected_chars: int | None = None) -> int | None:
    """Reserve enough Responses output for the requested character contract.

    ``max_output_tokens`` also includes model reasoning tokens, so this uses a
    conservative 1.25 characters-per-token estimate plus one 1,024-token
    reserve and rounds up to a whole 1,024-token block.  The upper cap keeps a
    malformed preset from issuing an unexpectedly expensive request.
    """
    requested_chars = max(
        0,
        int(expected_chars or 0),
        int(request.target_chars or 0) if expected_chars is None else 0,
        int(request.allowed_min or 0) if expected_chars is None else 0,
    )
    if not requested_chars:
        return None
    requested = math.ceil(requested_chars / 1.25) + 1024
    return min(32768, max(2048, math.ceil(requested / 1024) * 1024))


def trim_text_to_sentence_boundary(text: str, allowed_max: int) -> str:
    """Keep text inside a maximum without asking the provider to rewrite it."""
    text = str(text or "").strip()
    if not allowed_max or len(text) <= allowed_max:
        return text
    prefix = text[:allowed_max]
    endpoint = max(prefix.rfind(mark) for mark in ".!?…")
    if endpoint >= 0:
        return prefix[:endpoint + 1].strip()
    return prefix.rstrip()


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

    async def _generate_for_request(
        self, method, prompt: str, request: ScenarioRequest, expected_chars: int | None = None,
    ) -> str:
        budget = scenario_output_token_budget(request, expected_chars)
        if budget and self._accepts_keyword(method, "max_output_tokens"):
            return await method(prompt, max_output_tokens=budget)
        return await method(prompt)

    async def _generate_usable(self, prompt: str, request: ScenarioRequest, expected_chars: int | None = None) -> str:
        """Retry an unusable provider reply before any scenario prose is accepted."""
        result = await self._generate_for_request(self.client.generate, prompt, request, expected_chars)
        refused = looks_like_action_required(result)
        for attempt in range(1, 3):
            if not refused:
                break
            retry_prompt = (
                "This is a new standalone task. Complete it now without discussing prior replies. "
                "Return only the requested result, with no questions or meta commentary.\n\n"
                f"TASK:\n{prompt}"
            )
            generate_fresh = getattr(self.client, "generate_fresh", self.client.generate)
            result = await self._generate_for_request(generate_fresh, retry_prompt, request, expected_chars)
            refused = looks_like_action_required(result)
        if refused:
            generate_openai = getattr(self.client, "generate_openai", None)
            if generate_openai is not None:
                openai_prompt = (
                    "Return only the completed requested result. Do not ask questions or explain limitations.\n\n"
                    f"TASK:\n{prompt}"
                )
                result = await self._generate_for_request(generate_openai, openai_prompt, request, expected_chars)
        return result

    @staticmethod
    def _story_target_chars(request: ScenarioRequest) -> int:
        return max(0, int(request.target_chars or 0), int(request.allowed_min or 0))

    @staticmethod
    def _assembled_story(plan: StoryPlan, accepted_parts: list[dict[str, Any]]) -> str:
        expected_ids = [part.id for part in plan.parts]
        accepted_ids = [str(record.get("part_id", "")) for record in accepted_parts]
        if accepted_ids != expected_ids[:len(accepted_ids)]:
            raise ValueError("accepted story parts must be one ordered plan prefix")
        for part, record in zip(plan.parts, accepted_parts, strict=False):
            if list(record.get("content_ids", [])) != list(part.content_ids):
                raise ValueError("accepted story part content ownership does not match its plan")
            if not str(record.get("text", "")).strip():
                raise ValueError("accepted story part cannot be empty")
        return "\n\n".join(
            str(record.get("text", "")).strip()
            for record in accepted_parts
            if str(record.get("text", "")).strip()
        ).strip()

    @staticmethod
    def _writer_output_is_structural(text: str) -> bool:
        """Reject planner/part labels before they can enter the user scenario."""
        return bool(re.search(
            r"(?im)^\s*(?:part|часть|p\d+|\{\s*\"(?:part|text|content))\b",
            str(text or "").strip(),
        ))

    async def _run_planned_story(self, job: Job) -> bool:
        """Plan long work once, then accept and persist a contiguous writer prefix."""
        target = self._story_target_chars(job.request)
        part_targets = calculate_story_part_targets(target)
        if len(part_targets) == 1:
            job.result = await self._generate_usable(job.request.prompt, job.request)
            if looks_like_action_required(job.result):
                job.state = RunState.PAUSED
                job.error = "Текстовый агент и доступные ключи ChatGPT API не вернули готовый сценарий"
                job.actual_chars = len(job.result.strip())
                job.length_status = "FAILED"
                return False
            job.length_status, job.actual_chars = scenario_length_status(job.request, job.result)
            if job.length_status == "LONG":
                job.result = trim_text_to_sentence_boundary(job.result, job.request.allowed_max)
                job.length_status, job.actual_chars = scenario_length_status(job.request, job.result)
            return job.length_status not in {"SHORT", "LONG"}

        if job.story_plan:
            plan = story_plan_from_dict(job.story_plan)
            if tuple(part.target_chars for part in plan.parts) != part_targets:
                raise ValueError("persisted story plan no longer matches the selected length contract")
        else:
            planner_prompt = build_story_planner_prompt(job.request, part_targets)
            planner_budget = max(2048, min(8192, 1024 + len(part_targets) * 350))
            planner_response = await self._generate_usable(planner_prompt, job.request, planner_budget)
            if looks_like_action_required(planner_response):
                job.result = planner_response
                job.actual_chars = len(planner_response.strip())
                job.length_status = "FAILED"
                job.state = RunState.PAUSED
                job.error = "Планировщик сценария не вернул рабочий план"
                return False
            try:
                plan = parse_story_plan_response(planner_response, part_targets)
            except StoryPlanCapacityInsufficient as exc:
                job.story_planner_status = "CAPACITY_INSUFFICIENT"
                job.state = RunState.PAUSED
                job.error = f"Недостаточно различающегося материала для выбранной длины: {exc.reason}"
                job.result = ""
                job.actual_chars = 0
                job.length_status = "SHORT" if job.request.allowed_min else "CAPACITY"
                return False
            job.story_plan = plan.to_dict()
            job.accepted_story_parts = []
            job.story_planner_status = "READY"
            # Persist the complete plan before a prose part is accepted.
            self._notify(job)

        self._assembled_story(plan, job.accepted_story_parts)
        for part_index, part in enumerate(plan.parts):
            if part_index < len(job.accepted_story_parts):
                continue
            writer_prompt = build_story_writer_prompt(
                job.request, plan, job.accepted_story_parts, part_index,
            )
            writer_result = await self._generate_for_request(
                self.client.generate, writer_prompt, job.request, part.target_chars,
            )
            if (looks_like_action_required(writer_result) or not writer_result.strip()
                    or self._writer_output_is_structural(writer_result)):
                job.state = RunState.PAUSED
                job.error = f"Писатель части {part.id} не вернул готовый фрагмент"
                job.result = self._assembled_story(plan, job.accepted_story_parts)
                job.actual_chars = len(job.result)
                job.length_status = f"PART {part_index + 1}/{len(plan.parts)}"
                return False
            job.accepted_story_parts.append({
                "part_id": part.id,
                "text": writer_result.strip(),
                "content_ids": list(part.content_ids),
                "target_chars": part.target_chars,
            })
            job.result = self._assembled_story(plan, job.accepted_story_parts)
            job.actual_chars = len(job.result)
            job.length_status = f"PART {part_index + 1}/{len(plan.parts)}"
            # Every accepted part is durable before calling the next writer.
            self._notify(job)

        job.length_status, job.actual_chars = scenario_length_status(job.request, job.result)
        job.length_repair_attempts = 0
        return job.length_status not in {"SHORT", "LONG"}

    async def _run_one(self, job: Job) -> Job:
        async with self.semaphore:
            job.state = RunState.RUNNING
            job.error = ""
            self._notify(job)
            try:
                if await self._run_planned_story(job):
                    job.state = RunState.DONE
                    job.error = ""
                elif job.state is RunState.RUNNING:
                    # Keep usable but out-of-contract text visible and honest;
                    # do not append a generic continuation or rewrite it.
                    job.state = RunState.PAUSED
                    job.error = "Сценарий не уложился в выбранный диапазон длины"
            # This is the runner's deliberately broad provider boundary: it
            # converts any adapter failure into durable per-job state instead
            # of leaving a background worker unobserved.
            except Exception as exc:  # noqa: BLE001
                job.state = RunState.ERROR
                job.error = str(exc)
                job.result = getattr(exc, "response", job.result)
            self._notify(job)
            return job

    async def run(
        self, requests: list[ScenarioRequest], resume_jobs: dict[int, Job] | None = None,
    ) -> list[Job]:
        """Run new requests or verified persisted prefixes keyed by request index."""
        resumable = resume_jobs or {}
        jobs: list[Job] = []
        for request in requests:
            job = resumable.get(request.index)
            if job is None:
                jobs.append(Job(request))
                continue
            job.request = request
            job.state = RunState.WAITING
            job.error = ""
            jobs.append(job)
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

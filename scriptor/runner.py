from __future__ import annotations

import asyncio
import hashlib
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
    build_story_plan_structure_repair_prompt,
    build_story_planner_prompt,
    build_story_writer_prompt,
    calculate_story_part_targets,
    parse_story_plan_response,
    repair_story_plan_parts_response,
    story_plan_from_dict,
)

_ANALYTIC_FILLER_PATTERNS = (
    "в этом и заключается", "именно поэтому", "в этой точке", "здесь важно понять",
    "главный нерв", "по сути", "меняет саму логику", "пространство для манёвра",
    "пространство для маневра", "политическая рамка", "новая конфигурация",
    "поле выбора", "архитектура давления", "политическая цена", "новый сигнал",
    "баланс становится", "баланс стал", "менее устойчив",
)
_WRITER_EVENT_CUES = (
    "атак", "удар", "обстрел", "нанес", "провел", "заяв", "потребов",
    "объяв", "ввел", "ввёл", "подпис", "встрет", "отказ", "задерж",
    "арест", "суд", "отправ", "закры", "откры", "переве", "направ",
    "запрос", "ответ", "реагир", "вышел", "вышл", "созвал", "приня",
    "решил", "голос", "назнач", "увол", "сократ", "увелич", "перекры",
    "эваку", "запуст", "прибыл", "обсуд", "отозв", "прекрат", "восстанов",
    "attack", "strike", "launch", "announce", "demand", "reject", "arrest",
    "detain", "send", "close", "open", "move", "request", "respond", "meet",
    "sign", "vote", "approve", "block", "evacuate",
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
    user_action_requests = (
        "переформулируйте", "измените тему", "уточните тему", "please rephrase",
        "change the topic", "clarify the topic",
    )
    refusal_markers = (
        "не могу продолжить", "не могу создать", "не могу сгенерировать",
        "не могу написать", "не могу предоставить", "i can't help with",
        "i cannot help with", "i can’t help with", "не могу помочь с этим",
        "не могу выполнить этот запрос", "не могу выполнить вашу просьбу",
        "не могу продолжить выполнение", "не могу создать такой",
        "не могу написать такой", "не могу повторить", "не могу перезапустить",
        "не могу выполнить задачу", "я отказываюсь", "это противоречит",
        "нарушает правила", "по соображениям безопасности", "i can't comply",
        "i can’t comply", "i cannot fulfill", "i cannot complete",
        "against my guidelines", "violates policy", "for safety reasons",
    )
    meta_request_context = (
        "этот запрос", "данный запрос", "ваш запрос", "вашу просьбу",
        "запрос пользователя", "this request", "your request", "the request",
        "my guidelines", "openai policy",
    )
    # В полноценном сценарии фразы персонажей вроде «я не могу» и новостные
    # формулировки вроде «нарушает правила» допустимы. Короткий отказ принимаем
    # как отказ напрямую; в длинном тексте safety/policy-маркер должен быть
    # привязан к мета-контексту самого запроса, а не к сюжету.
    short_refusal = len(sample) < 700 and any(marker in sample[:600] for marker in (
        "я не могу", "не могу помочь", "не могу выполнить", "не могу создать",
        "не могу написать", "i can't", "i can’t", "i cannot", "unable to",
    ))
    explicit_user_action = any(
        marker in sample[:1600] for marker in user_action_requests
    )
    contextual_refusal = (
        any(marker in sample[:1600] for marker in refusal_markers)
        and (
            len(sample) < 700
            or any(marker in sample[:1600] for marker in meta_request_context)
        )
    )
    return (
        sample.startswith(refusal_prefixes)
        or short_refusal
        or explicit_user_action
        or contextual_refusal
    )


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
    # Bounded, non-content diagnostics for a Planner response which exhausted
    # the accepted schema-recovery path. Provider prose never belongs here.
    story_planner_failure: dict[str, str] = field(default_factory=dict)


def _planner_schema_reason(error: BaseException) -> str:
    """Map local Story Map validation failures to stable, safe UI codes."""
    message = " ".join(str(error).casefold().split())
    known_reasons = (
        ("requires thesis", "MISSING_THESIS"),
        ("requires macro_blocks", "MISSING_MACRO_BLOCKS"),
        ("requires content_atoms", "MISSING_CONTENT_ATOMS"),
        ("requires exactly", "PART_TOPOLOGY"),
        ("owner_part_id", "CONTENT_OWNERSHIP"),
        ("content atom owner", "CONTENT_OWNERSHIP"),
        ("content atom ownership", "CONTENT_OWNERSHIP"),
        ("must return strict json", "NON_JSON"),
        ("response must be an object", "NON_OBJECT_JSON"),
    )
    for marker, code in known_reasons:
        if marker in message:
            return code
    return "INVALID_STORY_MAP"


def _pause_for_planner_schema_failure(job: Job, response: str, error: BaseException) -> None:
    """Pause safely after bounded recovery without retaining provider content."""
    reason = _planner_schema_reason(error)
    job.story_planner_status = "SCHEMA_RECOVERY_EXHAUSTED"
    job.story_planner_failure = {
        "phase": "FRESH_SCHEMA",
        "reason": reason,
        "response_chars": str(len(str(response or "").strip())),
        "response_sha256": hashlib.sha256(
            str(response or "").encode("utf-8"),
        ).hexdigest(),
    }
    job.state = RunState.PAUSED
    job.error = (
        "Планировщик не вернул совместимую карту истории после безопасного восстановления. "
        f"Код диагностики: FRESH_SCHEMA:{reason}."
    )
    job.result = ""
    job.actual_chars = 0
    job.length_status = "FAILED"


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
    def _story_length_contract(request: ScenarioRequest) -> dict[str, int]:
        """Persist the complete contract that produced a resumable Story Map."""
        return {
            "target_chars": max(0, int(request.target_chars or 0)),
            "allowed_min": max(0, int(request.allowed_min or 0)),
            "allowed_max": max(0, int(request.allowed_max or 0)),
        }

    @classmethod
    def _persisted_story_contract_changed(
        cls, persisted_plan: dict[str, Any], request: ScenarioRequest,
    ) -> bool:
        """Detect every persisted range change, with a safe legacy fallback."""
        if "length_contract" not in persisted_plan:
            return False
        stored = persisted_plan.get("length_contract")
        if not isinstance(stored, dict):
            return True
        try:
            stored_contract = {
                key: max(0, int(stored.get(key, 0) or 0))
                for key in ("target_chars", "allowed_min", "allowed_max")
            }
        except (TypeError, ValueError):
            # Corrupt contract metadata must fail safe instead of silently
            # adopting a new range on an immutable accepted prefix.
            return True
        return stored_contract != cls._story_length_contract(request)

    def _next_story_part_target(
        self, job: Job, plan: StoryPlan, part_index: int,
    ) -> int:
        """Rebalance only the remaining character budget; never rewrite accepted prose."""
        part = plan.parts[part_index]
        if not job.accepted_story_parts:
            return max(0, int(part.target_chars or 0))
        overall_target = self._story_target_chars(job.request)
        if not overall_target:
            return max(0, int(part.target_chars or 0))
        accepted_text = self._assembled_story(plan, job.accepted_story_parts)
        remaining_parts = len(plan.parts) - part_index
        # Each future accepted part adds one deterministic "\n\n" separator
        # to the already assembled prefix.
        remaining_separators = 2 * remaining_parts
        remaining_prose = max(
            remaining_parts,
            overall_target - len(accepted_text) - remaining_separators,
        )
        quotient, remainder = divmod(remaining_prose, remaining_parts)
        balanced_target = max(1, quotient + (1 if remainder else 0))
        # Length bounds are advisory for completed prose. If an earlier part
        # runs long, never starve future planned content just to force the
        # assembled story back under target; keep at least the planned budget.
        return max(max(0, int(part.target_chars or 0)), balanced_target)

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
            r'(?im)^\s*(?:(?:part|часть)\s+\d+\b|p\d+\b|\{\s*"(?:part|text|content)"\s*:)',
            str(text or "").strip(),
        ))

    @staticmethod
    def _writer_output_quality_unusable(text: str) -> bool:
        """Reject only unmistakable analytical filler before a part is durable.

        This is intentionally a small local guard, not a second model or a
        factuality judge.  Short/ambiguous prose remains accepted.  A retry is
        warranted only when a substantial response is overwhelmingly composed
        of known analytical-transition language and contains almost no named
        event/action cues, or when it puts a dramatized disclosure first.
        """
        cleaned = " ".join(str(text or "").split())
        if not cleaned:
            return False
        sentences = [
            sentence.strip() for sentence in re.split(r"(?<=[.!?…])\s+", cleaned)
            if sentence.strip()
        ]
        first = sentences[0].casefold() if sentences else cleaned.casefold()
        if "драматизирован" in first and "реконструкц" in first:
            return True
        # A local detector cannot reliably score terse prose, verse, or test
        # fixtures without normal sentence boundaries.  Let the Writer prompt
        # govern those instead of creating a false blocker.
        if len(sentences) < 6:
            return False
        analytic_sentences = sum(
            any(pattern in sentence.casefold() for pattern in _ANALYTIC_FILLER_PATTERNS)
            for sentence in sentences
        )
        event_sentences = sum(
            any(cue in sentence.casefold() for cue in _WRITER_EVENT_CUES)
            for sentence in sentences
        )
        return (
            analytic_sentences >= 5
            and analytic_sentences * 2 >= len(sentences)
            and event_sentences <= 1
        )

    def _writer_output_rejection_reason(self, text: str) -> str:
        if looks_like_action_required(text):
            return "ACTION_REQUIRED"
        if not str(text or "").strip():
            return "EMPTY"
        if self._writer_output_is_structural(text):
            return "STRUCTURAL"
        if self._writer_output_quality_unusable(text):
            return "QUALITY_UNUSABLE"
        return ""

    def _writer_output_unusable(self, text: str) -> bool:
        return bool(self._writer_output_rejection_reason(text))

    async def _generate_fresh_result(
        self,
        prompt: str,
        request: ScenarioRequest,
        expected_chars: int | None = None,
    ) -> str:
        """Run one bounded fresh-chat recovery before any new artifact is accepted."""
        generate_fresh = getattr(self.client, "generate_fresh", self.client.generate)
        result = await self._generate_for_request(
            generate_fresh, prompt, request, expected_chars,
        )
        if looks_like_action_required(result):
            generate_openai = getattr(self.client, "generate_openai", None)
            if generate_openai is not None:
                result = await self._generate_for_request(
                    generate_openai, prompt, request, expected_chars,
                )
        return result

    async def _generate_writer_usable(
        self,
        prompt: str,
        request: ScenarioRequest,
        expected_chars: int | None = None,
    ) -> str:
        """Retry only the current unaccepted Writer part.

        This is not continuation or regeneration of accepted prose: every retry
        receives the same bounded Story Map/ledger/seam prompt and happens
        before the current part is appended to accepted_story_parts.
        """
        result = await self._generate_for_request(
            self.client.generate, prompt, request, expected_chars,
        )
        for _attempt in range(2):
            reason = self._writer_output_rejection_reason(result)
            if not reason:
                return result
            if reason == "QUALITY_UNUSABLE":
                retry_prompt = (
                    "Retry the SAME unfinished NewsFlow story segment in a fresh chat. "
                    "Rewrite SAME unfinished segment as concrete event progression: name actors, actions or "
                    "decisions, reactions and a new consequence. Do not restart the whole story, do not repeat "
                    "accepted material, do not emit a part label or JSON, and return only the requested continuous "
                    "prose segment.\n\n"
                    f"TASK:\n{prompt}"
                )
            else:
                retry_prompt = (
                    "Retry the SAME unfinished NewsFlow story segment in a fresh chat. "
                    "Do not restart the whole story, do not emit a part label or JSON, "
                    "and return only the requested continuous prose segment.\n\n"
                    f"TASK:\n{prompt}"
                )
            generate_fresh = getattr(self.client, "generate_fresh", self.client.generate)
            result = await self._generate_for_request(
                generate_fresh, retry_prompt, request, expected_chars,
            )
        reason = self._writer_output_rejection_reason(result)
        if reason:
            generate_openai = getattr(self.client, "generate_openai", None)
            if generate_openai is not None:
                if reason == "QUALITY_UNUSABLE":
                    openai_prompt = (
                        "Write only the SAME unfinished NewsFlow story segment below as concrete event progression. "
                        "Name actors, actions or decisions, reactions and a new consequence. Do not restart the "
                        "story, repeat accepted material, ask questions, emit labels/JSON, or explain limitations.\n\n"
                        f"TASK:\n{prompt}"
                    )
                else:
                    openai_prompt = (
                        "Write only the SAME unfinished NewsFlow story segment below. "
                        "Do not restart the story, ask questions, emit labels/JSON, or explain limitations.\n\n"
                        f"TASK:\n{prompt}"
                    )
                result = await self._generate_for_request(
                    generate_openai, openai_prompt, request, expected_chars,
                )
        return result

    async def _run_planned_story(self, job: Job) -> bool:
        """Plan long work once, then accept and persist a contiguous writer prefix."""
        target = self._story_target_chars(job.request)
        part_targets = calculate_story_part_targets(target)

        if job.story_plan:
            plan = story_plan_from_dict(job.story_plan)
            # Older sessions stored a Covers-only marker in scenario state.
            # Do not carry it into a Writer resume or the Scenario UI.
            if job.story_planner_status == "FACE_REPAIR_DEFERRED":
                job.story_planner_status = "READY"
            if (
                self._persisted_story_contract_changed(job.story_plan, job.request)
                or tuple(part.target_chars for part in plan.parts) != part_targets
            ):
                job.state = RunState.PAUSED
                job.error = (
                    "Диапазон длины изменился после создания Story Map. "
                    "Сохранённые части не перезаписаны; для нового диапазона нужен явный перезапуск."
                )
                job.result = self._assembled_story(plan, job.accepted_story_parts)
                job.actual_chars = len(job.result)
                job.length_status = "PLAN_LENGTH_CHANGED"
                return False
        else:
            # A user-triggered retry starts a new bounded Planner attempt. Never
            # present a previous failure fingerprint as if it described it.
            job.story_planner_status = ""
            job.story_planner_failure = {}
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
            except (TypeError, ValueError):
                # Prefer the non-regenerative repair: keep the original Story
                # Map substance and correct only its part topology/ownership.
                try:
                    structural_repair = await self._generate_usable(
                        build_story_plan_structure_repair_prompt(job.request, planner_response, part_targets),
                        job.request,
                        planner_budget,
                    )
                    plan = repair_story_plan_parts_response(
                        structural_repair, planner_response, part_targets,
                    )
                except (TypeError, ValueError):
                    # Some real provider failures are outside the parts-only
                    # repair scope (missing content_kind, malformed macro/thesis,
                    # empty/non-JSON response). No Writer prose exists yet, so
                    # one fresh Planner retry is safe and does not regenerate an
                    # accepted scenario or mutate an accepted prefix.
                    fresh_planner_prompt = (
                        "FRESH STORY PLANNER RETRY. The previous planning response was invalid. "
                        "Plan the SAME NewsFlow story again from the original task below. "
                        "Return only the complete JSON Story Map; do not write scenario prose.\n\n"
                        f"TASK:\n{planner_prompt}"
                    )
                    fresh_planner_response = await self._generate_fresh_result(
                        fresh_planner_prompt, job.request, planner_budget,
                    )
                    if looks_like_action_required(fresh_planner_response):
                        job.result = fresh_planner_response
                        job.actual_chars = len(fresh_planner_response.strip())
                        job.length_status = "FAILED"
                        job.state = RunState.PAUSED
                        job.error = "Планировщик сценария не вернул рабочий план"
                        return False
                    try:
                        plan = parse_story_plan_response(
                            fresh_planner_response, part_targets,
                        )
                    except (TypeError, ValueError) as fresh_error:
                        # The bounded Planner recovery is exhausted before any
                        # Writer prose exists. Keep a durable, non-content
                        # diagnostic instead of leaking a raw exception or
                        # persisting provider text.
                        _pause_for_planner_schema_failure(
                            job, fresh_planner_response, fresh_error,
                        )
                        return False
            job.story_plan = plan.to_dict()
            job.story_plan["length_contract"] = self._story_length_contract(
                job.request,
            )
            job.accepted_story_parts = []
            job.story_planner_status = "READY"
            job.story_planner_failure = {}
            # Persist the complete plan before a prose part is accepted.
            self._notify(job)

        self._assembled_story(plan, job.accepted_story_parts)
        for part_index, part in enumerate(plan.parts):
            if part_index < len(job.accepted_story_parts):
                continue
            active_target = self._next_story_part_target(job, plan, part_index)
            writer_prompt = build_story_writer_prompt(
                job.request, plan, job.accepted_story_parts, part_index, active_target,
            )
            writer_result = await self._generate_writer_usable(
                writer_prompt, job.request, active_target,
            )
            writer_failure = self._writer_output_rejection_reason(writer_result)
            if writer_failure:
                job.state = RunState.PAUSED
                job.error = (
                    f"Писатель части {part.id} вернул аналитический текст без событийного развития"
                    if writer_failure == "QUALITY_UNUSABLE"
                    else f"Писатель части {part.id} не вернул готовый фрагмент"
                )
                job.result = self._assembled_story(plan, job.accepted_story_parts)
                job.actual_chars = len(job.result)
                job.length_status = (
                    "QUALITY_UNUSABLE"
                    if writer_failure == "QUALITY_UNUSABLE"
                    else f"PART {part_index + 1}/{len(plan.parts)}"
                )
                return False

            accepted_text = writer_result.strip()

            job.accepted_story_parts.append({
                "part_id": part.id,
                "text": accepted_text,
                "content_ids": list(part.content_ids),
                "target_chars": active_target,
            })
            job.result = self._assembled_story(plan, job.accepted_story_parts)
            job.actual_chars = len(job.result)
            job.length_status = f"PART {part_index + 1}/{len(plan.parts)}"
            # Every accepted part is durable before calling the next writer.
            self._notify(job)

        # Length is advisory once valid prose has been produced. Keep the
        # measured SHORT/LONG/READY diagnostic, but never spend another provider
        # request, trim prose, or block completion solely because of length.
        job.length_status, job.actual_chars = scenario_length_status(job.request, job.result)
        job.length_repair_attempts = 0
        return True

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
            if (
                isinstance(job.story_plan, dict)
                and "length_contract" not in job.story_plan
            ):
                # Migrate r26/legacy persisted Story Maps before replacing the
                # old request. Session already stores the request range, so use
                # that exact historical contract rather than guessing from the
                # new UI settings.
                job.story_plan["length_contract"] = self._story_length_contract(
                    job.request,
                )
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

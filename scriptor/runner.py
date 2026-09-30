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
        ("must return strict json", "NON_JSON"),
        ("response must be an object", "NON_OBJECT_JSON"),
        ("requires thesis", "MISSING_THESIS"),
        ("requires macro_blocks", "MISSING_MACRO_BLOCKS"),
        ("requires content_atoms", "MISSING_CONTENT_ATOMS"),
        ("content atom must be an object", "MISSING_CONTENT_ATOMS"),
        ("content atom ids must be unique", "ATOM_SEMANTIC_DUPLICATE"),
        ("content_kind", "INVALID_CONTENT_KIND"),
        ("requires before_development_after state transition contract", "INVALID_TRANSITION_CONTRACT"),
        ("requires structured concrete change", "MISSING_TRANSITION_FIELDS"),
        ("must describe an observable concrete change", "ABSTRACT_OR_NONCONCRETE_TRANSITION"),
        ("requires concrete story developments", "SEMANTIC_DENSITY"),
        ("requires at least", "SEMANTIC_DENSITY"),
        ("content atoms must be materially distinct", "ATOM_SEMANTIC_DUPLICATE"),
        ("parts must own materially distinct semantic content", "PART_SEMANTIC_DUPLICATE"),
        ("owner_part_id", "CONTENT_OWNERSHIP"),
        ("content atom owner", "CONTENT_OWNERSHIP"),
        ("content atom ownership", "CONTENT_OWNERSHIP"),
        ("content atom is assigned more than once", "CONTENT_OWNERSHIP"),
        ("structural repair must assign every existing atom exactly once", "CONTENT_OWNERSHIP"),
        ("requires exactly", "PART_COUNT"),
        ("part ids must be ordered", "PART_ID_ORDER"),
        ("part must be an object", "PART_CONTENT_IDS"),
        ("references unknown macro block", "PART_MACRO_REF"),
        (" role must be ", "PART_ROLE"),
        (" requires content_ids", "PART_CONTENT_IDS"),
        (" duplicates content ids", "CONTENT_OWNERSHIP"),
        ("macro block", "MISSING_MACRO_BLOCKS"),
    )
    for marker, code in known_reasons:
        if marker in message:
            return code
    # This remains a safe direct-retry category. The structural repairer can
    # only change parts, so an unknown schema failure must never be presented
    # to it as though it could repair atoms or top-level fields.
    return "MISSING_CONTENT_ATOMS"


_PARTS_ONLY_PLANNER_REASONS = frozenset({
    "PART_COUNT", "PART_ID_ORDER", "PART_ROLE", "PART_MACRO_REF",
    "PART_CONTENT_IDS", "CONTENT_OWNERSHIP",
})

_FRESH_PLANNER_REASON_GUIDANCE = {
    "INVALID_TRANSITION_CONTRACT": "Include the exact BEFORE_DEVELOPMENT_AFTER transition contract.",
    "MISSING_TRANSITION_FIELDS": "Give every atom all required before/development/after fields.",
    "ABSTRACT_OR_NONCONCRETE_TRANSITION": "Make every atom an observable concrete change, not an interpretation.",
    "ATOM_SEMANTIC_DUPLICATE": "Keep every content atom materially distinct from the others.",
    "PART_SEMANTIC_DUPLICATE": "Give every part distinct semantic ownership and novelty.",
    "SEMANTIC_DENSITY": "Provide enough distinct concrete developments for each part's target.",
    "PART_COUNT": "Use the exact runtime part count from the technical skeleton.",
    "PART_ID_ORDER": "Use the exact ordered part IDs from the technical skeleton.",
    "PART_ROLE": "Use the exact runtime roles from the technical skeleton.",
    "PART_MACRO_REF": "Reference only an existing macro block from each technical part.",
    "PART_CONTENT_IDS": "Give every technical part a valid, non-empty list of content IDs.",
    "CONTENT_OWNERSHIP": "Assign every existing content atom exactly once to a matching planned part.",
    "INVALID_CONTENT_KIND": "Use only SUPPORTED or DRAMATIZED as content_kind values.",
    "MISSING_THESIS": "Include one compact thesis.",
    "MISSING_MACRO_BLOCKS": "Include valid macro_blocks with unique IDs and purposes.",
    "MISSING_CONTENT_ATOMS": "Include valid content_atoms with the required schema.",
    "NON_JSON": "Return one strict JSON object only.",
    "NON_OBJECT_JSON": "Return one JSON object, not an array or prose.",
}


def _fresh_planner_retry_prompt(planner_prompt: str, reason: str) -> str:
    """Build a safe recovery prompt without reflecting provider output."""
    guidance = _FRESH_PLANNER_REASON_GUIDANCE[reason]
    return (
        "FRESH STORY PLANNER RETRY. The previous planning response failed a local "
        f"schema check with safe reason {reason}. {guidance} "
        "Plan the SAME NewsFlow story again from the original task below. Return only "
        "the complete JSON Story Map; do not write scenario prose. Do not quote or "
        "reuse any previous planner response.\n\n"
        f"TASK:\n{planner_prompt}"
    )


def _pause_for_planner_schema_failure(
    job: Job,
    response: str,
    error: BaseException,
    *,
    initial_reason: str,
    recovery_route: str,
    structural_repair_reason: str = "",
) -> None:
    """Pause safely after bounded recovery without retaining provider content."""
    reason = _planner_schema_reason(error)
    job.story_planner_status = "SCHEMA_RECOVERY_EXHAUSTED"
    job.story_planner_failure = {
        "phase": "FRESH_SCHEMA",
        "reason": reason,
        "initial_reason": initial_reason,
        "recovery_route": recovery_route,
        "fresh_reason": reason,
        "structural_repair_reason": structural_repair_reason,
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
        """Keep Writer volume aligned with material reserved in the Story Map.

        Accepted prose is immutable.  Its length cannot manufacture new
        content for later parts, so a short P1 must not turn a P3 designed for
        ~4k of owned material into an impossible ~8k assignment.  Final
        length remains an honest advisory diagnostic after all first passes.
        """
        del job
        return max(0, int(plan.parts[part_index].target_chars or 0))

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

    def _writer_output_rejection_reason(self, text: str) -> str:
        """Reject only technically unusable Writer responses.

        Scenario quality is owned upstream by the Story Map and Writer prompt.
        The runtime never rewrites or regenerates a completed Writer response
        merely because its style is analytical, literary, or otherwise weak.
        """
        if looks_like_action_required(text):
            return "ACTION_REQUIRED"
        if not str(text or "").strip():
            return "EMPTY"
        if self._writer_output_is_structural(text):
            return "STRUCTURAL"
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
        """Generate one Writer part exactly once.

        Planner recovery may happen before prose exists, but Writer prose is
        never regenerated. A technical failure pauses the job; a style defect
        must be fixed in the planning/writing architecture and verified by a
        new end-to-end run, not hidden by rewriting the same part.
        """
        return await self._generate_for_request(
            self.client.generate, prompt, request, expected_chars,
        )

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
            # A Planner response carries every atom's transition fields plus
            # the complete technical topology.  Three 4k parts own at least
            # nine atoms, so the former ~2k expected-character budget could
            # truncate a valid JSON map before content_atoms/parts completed.
            # This is an output allowance only; it neither adds provider
            # attempts nor changes the Writer's one-call contract.
            # Scale with the complete immutable map.  The provider-budget
            # helper remains the single global safety cap; an additional 8k
            # ceiling here would truncate the tail atoms of 50k+ scenarios.
            planner_budget = max(2304, 1536 + len(part_targets) * 768)
            planner_response = await self._generate_usable(planner_prompt, job.request, planner_budget)
            if looks_like_action_required(planner_response):
                job.result = planner_response
                job.actual_chars = len(planner_response.strip())
                job.length_status = "FAILED"
                job.state = RunState.PAUSED
                job.error = "Планировщик сценария не вернул рабочий план"
                return False
            try:
                plan = parse_story_plan_response(
                    planner_response,
                    part_targets,
                    require_state_transitions=True,
                )
            except (TypeError, ValueError) as initial_error:
                initial_reason = _planner_schema_reason(initial_error)
                recovery_route = "FRESH_DIRECT"
                structural_repair_reason = ""
                needs_fresh_planner = True

                # Parts-only repair is deliberately narrow. It preserves the
                # original Story Map and can correct only ordered part topology
                # and atom ownership. Atom, transition, semantic and top-level
                # schema errors instead get the one permitted fresh Planner
                # call directly; sending them to the repairer wastes a call and
                # cannot make the invalid map valid.
                if initial_reason in _PARTS_ONLY_PLANNER_REASONS:
                    recovery_route = "STRUCTURAL_REPAIR"
                    try:
                        structural_repair = await self._generate_usable(
                            build_story_plan_structure_repair_prompt(
                                job.request, planner_response, part_targets,
                            ),
                            job.request,
                            planner_budget,
                        )
                        plan = repair_story_plan_parts_response(
                            structural_repair,
                            planner_response,
                            part_targets,
                            require_state_transitions=True,
                        )
                        needs_fresh_planner = False
                    except (TypeError, ValueError) as repair_error:
                        # The original map is still unaccepted and no Writer
                        # prose exists. Fall through to one fresh Planner call.
                        structural_repair_reason = _planner_schema_reason(repair_error)

                if needs_fresh_planner:
                    fresh_planner_prompt = _fresh_planner_retry_prompt(
                        planner_prompt, initial_reason,
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
                            fresh_planner_response,
                            part_targets,
                            require_state_transitions=True,
                        )
                    except (TypeError, ValueError) as fresh_error:
                        # The bounded Planner recovery is exhausted before any
                        # Writer prose exists. Keep a durable, non-content
                        # diagnostic instead of leaking a raw exception or
                        # persisting provider text.
                        _pause_for_planner_schema_failure(
                            job,
                            fresh_planner_response,
                            fresh_error,
                            initial_reason=initial_reason,
                            recovery_route=recovery_route,
                            structural_repair_reason=structural_repair_reason,
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
                job.error = f"Писатель части {part.id} не вернул готовый фрагмент"
                job.result = self._assembled_story(plan, job.accepted_story_parts)
                job.actual_chars = len(job.result)
                job.length_status = f"PART {part_index + 1}/{len(plan.parts)}"
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

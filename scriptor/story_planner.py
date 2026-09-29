"""Deterministic planning records for long, continuous NewsFlow scripts.

This module deliberately contains no provider I/O. The runner owns calls and
persists these small JSON-safe records before it accepts the first writer part.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from typing import Any

PREFERRED_PART_CHARS = 5_000
_COMPACT_PURPOSE_CHARS = 180
_COMPACT_ATOM_CHARS = 180
_CONTENT_KINDS = frozenset({"SUPPORTED", "DRAMATIZED"})
_SEMANTIC_STOPWORDS = frozenset({
    "this", "that", "with", "from", "into", "over", "under", "then", "than", "their", "there",
    "котор", "этот", "этог", "того", "чтобы", "после", "перед", "между", "через", "снова",
    "также", "здесь", "только", "часть", "истор", "развит", "событ", "матер", "контекст",
})


@dataclass(frozen=True)
class StoryContentAtom:
    id: str
    summary: str
    owner_part_id: str
    content_kind: str


@dataclass(frozen=True)
class StoryPartPlan:
    id: str
    role: str
    purpose: str
    macro_id: str
    content_ids: tuple[str, ...]
    target_chars: int
    opens: tuple[str, ...] = ()
    closes: tuple[str, ...] = ()
    transition_direction: str = ""
    novelty_question: str = ""
    novelty_payload: str = ""


@dataclass(frozen=True)
class StoryPlan:
    thesis: str
    macro_blocks: tuple[dict[str, str], ...]
    content_atoms: tuple[StoryContentAtom, ...]
    parts: tuple[StoryPartPlan, ...]

    def to_dict(self) -> dict:
        rows = []
        for part in self.parts:
            row = asdict(part)
            row["content_ids"] = list(part.content_ids)
            row["opens"] = list(part.opens)
            row["closes"] = list(part.closes)
            rows.append(row)
        return {
            "thesis": self.thesis,
            "macro_blocks": [dict(block) for block in self.macro_blocks],
            "content_atoms": [asdict(atom) for atom in self.content_atoms],
            "parts": rows,
        }


def calculate_story_part_targets(target_chars: int) -> tuple[int, ...]:
    """Split a requested overall target into evenly distributed ~5k parts."""
    target = max(0, int(target_chars or 0))
    if not target:
        return (0,)
    # A compact 6–9k script is one complete narrative. Above that threshold,
    # use the normal ~5k part budget without introducing a synthetic middle.
    part_count = 1 if target <= 9_000 else max(1, (target + PREFERRED_PART_CHARS - 1) // PREFERRED_PART_CHARS)
    # Final assembly inserts exactly two newline characters between accepted
    # parts. Keep those deterministic separators inside the overall character
    # budget instead of making an exact max contract spuriously LONG.
    separator_chars = 2 * (part_count - 1)
    prose_target = max(0, target - separator_chars)
    quotient, remainder = divmod(prose_target, part_count)
    return tuple(
        quotient + (1 if index < remainder else 0) for index in range(part_count)
    )


def _clean_text(value: object, field: str) -> str:
    cleaned = " ".join(str(value or "").split())
    if not cleaned:
        raise ValueError(f"story plan requires {field}")
    return cleaned


def _load_json_object(
    value: object,
    *,
    invalid_message: str,
    object_message: str,
) -> dict[str, Any]:
    """Load one provider JSON object, tolerating only transport-style wrappers.

    Real text models sometimes wrap otherwise valid JSON in a Markdown fence or
    a short explanatory sentence.  The Story Map itself remains strict: this
    helper only extracts the first syntactically valid JSON object and does not
    repair fields, invent defaults or accept partial JSON.
    """
    text = str(value or "").strip()
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as first_error:
        decoder = json.JSONDecoder()
        for index, char in enumerate(text):
            if char != "{":
                continue
            try:
                candidate, _end = decoder.raw_decode(text[index:])
            except json.JSONDecodeError:
                continue
            if isinstance(candidate, dict):
                return candidate
        raise ValueError(invalid_message) from first_error
    if not isinstance(parsed, dict):
        raise TypeError(object_message)
    return parsed


def _optional_text(value: object) -> str:
    return " ".join(str(value or "").split())


def _semantic_tokens(value: object) -> frozenset[str]:
    """Return a compact lexical signature for obvious meaning-level duplicates.

    This is deliberately conservative: it catches near-copy plans locally but
    does not attempt model-like semantic classification or trigger extra calls.
    """
    tokens: set[str] = set()
    for word in re.findall(r"[A-Za-zА-Яа-яЁё0-9]+", str(value or "").casefold()):
        stem = word[:6] if len(word) > 6 else word
        if len(word) < 4 or word in _SEMANTIC_STOPWORDS or stem in _SEMANTIC_STOPWORDS:
            continue
        tokens.add(stem)
    return frozenset(tokens)


def _semantic_overlap(left: object, right: object) -> float:
    first = _semantic_tokens(left)
    second = _semantic_tokens(right)
    if min(len(first), len(second)) < 4:
        return 0.0
    return len(first & second) / min(len(first), len(second))


def _id_list(value: object, _field: str) -> tuple[str, ...]:
    """Normalise advisory loop IDs without making them Story Map blockers."""
    if not isinstance(value, list):
        return ()
    result: list[str] = []
    seen: set[str] = set()
    for item in value:
        cleaned = _optional_text(item)
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        result.append(cleaned)
    return tuple(result)


def _expected_roles(part_count: int) -> tuple[str, ...]:
    if part_count == 1:
        return ("COMPLETE",)
    return ("OPENING",) + ("MIDDLE",) * (part_count - 2) + ("FINAL",)


def _normalise_advisory_loops(parts: list[StoryPartPlan]) -> list[StoryPartPlan]:
    """Keep only unambiguous cross-part loop hints.

    Loop metadata helps a Writer preserve continuity, but it does not own story
    content. Provider mistakes such as closing a part ID or a free-text sentence
    that was never opened must not invalidate an otherwise complete Story Map.
    """
    opened_at: dict[str, list[int]] = {}
    closed_at: dict[str, list[int]] = {}
    for index, part in enumerate(parts):
        for loop_id in part.opens:
            opened_at.setdefault(loop_id, []).append(index)
        for loop_id in part.closes:
            closed_at.setdefault(loop_id, []).append(index)

    valid = {
        loop_id
        for loop_id, open_indexes in opened_at.items()
        if len(open_indexes) == 1
        and len(closed_at.get(loop_id, [])) == 1
        and open_indexes[0] < closed_at[loop_id][0]
    }
    if all(
        all(loop_id in valid for loop_id in (*part.opens, *part.closes))
        for part in parts
    ):
        return parts

    return [
        StoryPartPlan(
            id=part.id,
            role=part.role,
            purpose=part.purpose,
            macro_id=part.macro_id,
            content_ids=part.content_ids,
            target_chars=part.target_chars,
            opens=tuple(loop_id for loop_id in part.opens if loop_id in valid),
            closes=tuple(loop_id for loop_id in part.closes if loop_id in valid),
            transition_direction=part.transition_direction,
            novelty_question=part.novelty_question,
            novelty_payload=part.novelty_payload,
        )
        for part in parts
    ]


def parse_story_plan_response(text: str, part_targets: tuple[int, ...]) -> StoryPlan:
    """Parse and validate the complete planner map before any writer starts."""
    raw = _load_json_object(
        text,
        invalid_message="story planner must return strict JSON",
        object_message="story planner response must be an object",
    )

    targets = tuple(max(0, int(target or 0)) for target in part_targets) or (0,)
    part_count = len(targets)
    expected_ids = tuple(f"P{index}" for index in range(1, part_count + 1))
    expected_roles = _expected_roles(part_count)
    thesis = _clean_text(raw.get("thesis"), "thesis")

    raw_blocks = raw.get("macro_blocks")
    if not isinstance(raw_blocks, list) or not raw_blocks:
        raise ValueError("story plan requires macro_blocks")
    macro_blocks: list[dict[str, str]] = []
    block_ids: set[str] = set()
    for index, block in enumerate(raw_blocks, start=1):
        if not isinstance(block, dict):
            raise TypeError("story plan macro block must be an object")
        block_id = _clean_text(block.get("id"), f"macro_blocks[{index}].id")
        if block_id in block_ids:
            raise ValueError("story plan macro block IDs must be unique")
        block_ids.add(block_id)
        macro_blocks.append(
            {
                "id": block_id,
                "purpose": _clean_text(
                    block.get("purpose"), f"macro_blocks[{index}].purpose"
                ),
            }
        )

    raw_parts = raw.get("parts")
    if not isinstance(raw_parts, list) or len(raw_parts) != part_count:
        raise ValueError(f"story plan requires exactly {part_count} parts")
    parts: list[StoryPartPlan] = []
    for index, (raw_part, expected_id, expected_role, target) in enumerate(
        zip(raw_parts, expected_ids, expected_roles, targets, strict=True),
        start=1,
    ):
        if not isinstance(raw_part, dict):
            raise TypeError("story plan part must be an object")
        part_id = _clean_text(raw_part.get("id"), f"parts[{index}].id")
        if part_id != expected_id:
            raise ValueError(f"story plan part IDs must be ordered as {expected_id}")
        role = _clean_text(raw_part.get("role"), f"parts[{index}].role").upper()
        if role != expected_role:
            raise ValueError(f"story plan part {part_id} role must be {expected_role}")
        macro_id = _clean_text(raw_part.get("macro_id"), f"parts[{index}].macro_id")
        if macro_id not in block_ids:
            raise ValueError(
                f"story plan part {part_id} references unknown macro block"
            )
        raw_ids = raw_part.get("content_ids")
        if not isinstance(raw_ids, list) or not raw_ids:
            raise ValueError(f"story plan part {part_id} requires content_ids")
        content_ids = tuple(
            _clean_text(value, f"parts[{index}].content_ids") for value in raw_ids
        )
        if len(set(content_ids)) != len(content_ids):
            raise ValueError(f"story plan part {part_id} duplicates content IDs")
        parts.append(
            StoryPartPlan(
                id=part_id,
                role=role,
                purpose=_clean_text(raw_part.get("purpose"), f"parts[{index}].purpose"),
                macro_id=macro_id,
                content_ids=content_ids,
                target_chars=target,
                opens=_id_list(raw_part.get("opens"), f"parts[{index}].opens"),
                closes=_id_list(raw_part.get("closes"), f"parts[{index}].closes"),
                transition_direction=_optional_text(
                    raw_part.get("transition_direction")
                ),
                novelty_question=_optional_text(raw_part.get("novelty_question")),
                novelty_payload=_optional_text(raw_part.get("novelty_payload")),
            )
        )

    raw_atoms = raw.get("content_atoms")
    if not isinstance(raw_atoms, list) or not raw_atoms:
        raise ValueError("story plan requires content_atoms")
    atoms: list[StoryContentAtom] = []
    atom_by_id: dict[str, StoryContentAtom] = {}
    for index, raw_atom in enumerate(raw_atoms, start=1):
        if not isinstance(raw_atom, dict):
            raise TypeError("story plan content atom must be an object")
        content_kind = _clean_text(
            raw_atom.get("content_kind"),
            f"content_atoms[{index}].content_kind",
        ).upper()
        if content_kind not in _CONTENT_KINDS:
            raise ValueError("story plan content_kind must be SUPPORTED or DRAMATIZED")
        atom = StoryContentAtom(
            id=_clean_text(raw_atom.get("id"), f"content_atoms[{index}].id"),
            summary=_clean_text(
                raw_atom.get("summary"), f"content_atoms[{index}].summary"
            ),
            owner_part_id=_clean_text(
                raw_atom.get("owner_part_id"), f"content_atoms[{index}].owner_part_id"
            ),
            content_kind=content_kind,
        )
        if atom.id in atom_by_id:
            raise ValueError("story plan content atom IDs must be unique")
        if atom.owner_part_id not in expected_ids:
            raise ValueError(
                "story plan content atom owner must reference a planned part"
            )
        atom_by_id[atom.id] = atom
        atoms.append(atom)

    # Reject only obvious near-copy semantic atoms locally. This guard is
    # intentionally conservative; it prevents duplicate meaning from becoming
    # separate ownership units without adding a post-generation LLM review.
    for atom_index, atom in enumerate(atoms):
        for previous in atoms[:atom_index]:
            if _semantic_overlap(atom.summary, previous.summary) >= 0.9:
                raise ValueError("story plan content atoms must be materially distinct")

    assigned_ids = [content_id for part in parts for content_id in part.content_ids]
    if len(set(assigned_ids)) != len(assigned_ids):
        raise ValueError("story plan content atom is assigned more than once")
    if set(assigned_ids) != set(atom_by_id):
        raise ValueError(
            "story plan content atom ownership must cover every planned atom exactly once"
        )
    for part in parts:
        for content_id in part.content_ids:
            if atom_by_id[content_id].owner_part_id != part.id:
                raise ValueError(
                    "story plan content atom owner conflicts with its part"
                )

    # Attach a compact novelty contract to every part. New planners provide
    # explicit fields; legacy/persisted maps fall back to already validated
    # purpose + owned atom summaries, so resume compatibility is preserved.
    enriched_parts: list[StoryPartPlan] = []
    for part in parts:
        owned_summaries = "; ".join(
            atom_by_id[content_id].summary for content_id in part.content_ids
        )
        enriched_parts.append(
            StoryPartPlan(
                id=part.id,
                role=part.role,
                purpose=part.purpose,
                macro_id=part.macro_id,
                content_ids=part.content_ids,
                target_chars=part.target_chars,
                opens=part.opens,
                closes=part.closes,
                transition_direction=part.transition_direction,
                novelty_question=part.novelty_question or part.purpose,
                novelty_payload=part.novelty_payload or owned_summaries,
            )
        )
    parts = enriched_parts

    # A part may deepen an earlier subject, but its combined semantic contract
    # must not be an obvious near-copy of an earlier part.
    for part_index, part in enumerate(parts):
        material = " ".join((
            part.purpose,
            part.novelty_question,
            part.novelty_payload,
            *(atom_by_id[content_id].summary for content_id in part.content_ids),
        ))
        contract = f"{part.novelty_question} {part.novelty_payload}"
        for previous in parts[:part_index]:
            previous_material = " ".join((
                previous.purpose,
                previous.novelty_question,
                previous.novelty_payload,
                *(atom_by_id[content_id].summary for content_id in previous.content_ids),
            ))
            previous_contract = f"{previous.novelty_question} {previous.novelty_payload}"
            if (
                _semantic_overlap(contract, previous_contract) >= 0.9
                or _semantic_overlap(material, previous_material) >= 0.9
            ):
                raise ValueError("story plan parts must own materially distinct semantic content")

    # opens/closes are continuity hints, not story ownership. Keep strict
    # validation for parts/macros/atoms above, then locally discard malformed
    # loop metadata instead of asking the provider to repair prose.
    parts = _normalise_advisory_loops(parts)

    return StoryPlan(
        thesis=thesis,
        macro_blocks=tuple(macro_blocks),
        content_atoms=tuple(atoms),
        parts=tuple(parts),
    )


def repair_story_plan_parts_response(text: str, original_response: str, part_targets: tuple[int, ...]) -> StoryPlan:
    """Repair only part topology; atoms keep identity/meaning but may move owner."""
    original = _load_json_object(
        original_response,
        invalid_message="story plan structural repair requires a JSON Story Map",
        object_message="story plan structural repair requires an object Story Map",
    )
    repair = _load_json_object(
        text,
        invalid_message="story plan structural repair must return strict JSON",
        object_message="story plan structural repair must return an object",
    )
    if not isinstance(repair.get("parts"), list):
        raise TypeError("story plan structural repair must contain parts")
    original_atoms = original.get("content_atoms")
    if not isinstance(original_atoms, list) or not all(isinstance(atom, dict) for atom in original_atoms):
        raise TypeError("story plan structural repair requires existing content atoms")
    atom_ids = [str(atom.get("id", "")).strip() for atom in original_atoms]
    if not all(atom_ids) or len(set(atom_ids)) != len(atom_ids):
        raise ValueError("story plan structural repair requires unique existing atom IDs")
    ownership: dict[str, str] = {}
    for part in repair["parts"]:
        if not isinstance(part, dict):
            raise TypeError("story plan structural repair part must be an object")
        part_id = str(part.get("id", "")).strip()
        content_ids = part.get("content_ids")
        if not part_id or not isinstance(content_ids, list):
            raise ValueError("story plan structural repair part requires id and content_ids")
        for atom_id in content_ids:
            atom_id = str(atom_id).strip()
            if atom_id not in atom_ids or atom_id in ownership:
                raise ValueError("story plan structural repair must assign every existing atom exactly once")
            ownership[atom_id] = part_id
    if set(ownership) != set(atom_ids):
        raise ValueError("story plan structural repair must assign every existing atom exactly once")
    merged = dict(original)
    merged["parts"] = repair["parts"]
    merged["content_atoms"] = [
        {**atom, "owner_part_id": ownership[str(atom["id"]).strip()]}
        for atom in original_atoms
    ]
    return parse_story_plan_response(json.dumps(merged, ensure_ascii=False), part_targets)


def story_plan_from_dict(value: dict[str, Any]) -> StoryPlan:
    """Revalidate one persisted plan instead of trusting session JSON blindly."""
    if not isinstance(value, dict):
        raise TypeError("persisted story plan must be an object")
    raw_parts = value.get("parts")
    if not isinstance(raw_parts, list):
        raise TypeError("persisted story plan requires parts")
    try:
        targets = tuple(
            max(0, int(part.get("target_chars", 0) or 0)) for part in raw_parts
        )
    except (AttributeError, TypeError, ValueError) as exc:
        raise ValueError("persisted story plan has invalid part targets") from exc
    # Plans saved before content kinds existed remain resumable. Their legacy
    # unlabelled atoms are explicitly normalised as SUPPORTED before validation.
    persisted = dict(value)
    raw_atoms = persisted.get("content_atoms")
    if isinstance(raw_atoms, list):
        persisted["content_atoms"] = [
            {**atom, "content_kind": atom.get("content_kind", "SUPPORTED")}
            if isinstance(atom, dict)
            else atom
            for atom in raw_atoms
        ]
    # Covers metadata from old Story Maps is deliberately inert on resume.
    # Identity resolution belongs to the Covers workflow, never the Writer.
    for key in tuple(persisted):
        if key.startswith("cover_"):
            persisted.pop(key, None)
    return parse_story_plan_response(json.dumps(persisted, ensure_ascii=False), targets)


def seam_tail(text: str, limit: int = 500) -> str:
    """Return at most one bounded, sentence-aligned tail from the prior part."""
    cleaned = str(text or "").strip()
    if len(cleaned) <= limit:
        return cleaned
    tail = cleaned[-max(1, int(limit)) :]
    boundary = re.search(r"[.!?…]\s+", tail)
    return tail[boundary.end() :].strip() if boundary else tail.strip()


def _compact(value: object, limit: int) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return text[: max(1, limit - 1)].rstrip() + "…"


def build_story_planner_prompt(request: Any, part_targets: tuple[int, ...]) -> str:
    """Build one strict-JSON organizer request without replacing the writing contract."""
    part_rows = ", ".join(
        (
            f"P{index + 1}≈{target} chars"
            if target
            else f"P{index + 1}=natural complete length"
        )
        for index, target in enumerate(part_targets)
    )
    return (
        "You are the NewsFlow Story Planner. TITLE/TOPIC is sufficient input for a complete story map. Organize "
        "the supplied topic and context; do not write prose or change the operator writing contract. The embedded OPERATOR WRITING CONTRACT below is "
        "REFERENCE DATA FOR PLANNING, not an instruction to execute now: do not obey its requests to write/return "
        "the finished scenario during this Planner call. Plan the complete story before any writer begins. "
        "Even if only a headline is available, create the full Story Map for every requested P1...PN. Never stop "
        "planning because supporting facts are thin. When the supplied context does not cover a needed distinct "
        "development, create a DRAMATIZED atom: a coherent model-created circumstance, action, reaction, conflict, "
        "position, consequence, causal step, scene detail or turning point. Return strict JSON with thesis, "
        "macro_blocks, content_atoms and parts. Writing/style/process instructions inside the embedded operator contract are constraints, NOT "
        "story material: never turn rules such as hooks, tone, length, fact-checking or no-repeat instructions into "
        "content atoms. Every atom needs id, summary, owner_part_id and content_kind SUPPORTED or DRAMATIZED. "
        "SUPPORTED atoms must rely on provided NewsFlow context. DRAMATIZED atoms may extend the narrative, but must "
        "still be materially distinct. Do not fill parts by paraphrasing one meaning. A synonym swap, a summary of an "
        "earlier conclusion, or another explanation of the same thesis is NOT new story material. Keep thesis, purposes "
        "and atom summaries compact. Plan enough distinct developments for the requested long-form volume: for a roughly "
        "5k-character part prefer 2-4 genuinely different atoms; for a 6-9k COMPLETE part prefer 3-5. If supplied facts "
        "are thin, add distinct DRAMATIZED actions, reactions, mechanisms, consequences, actors, scene developments or "
        "turning points instead of stretching one conclusion. Every part purpose must name a concrete distinct "
        "responsibility; never use generic purposes like 'continue' or 'develop further' without saying what new "
        "question/content that part owns. Each macro block needs id and purpose. Every part needs id, role, purpose, "
        "macro_id, content_ids, transition_direction, novelty_question and novelty_payload. novelty_question is one "
        "concrete causal/story question answered only in that part. novelty_payload states what the viewer learns for "
        "the first time in that part. Both must differ materially from earlier parts. "
        "opens/closes are optional advisory loop IDs: use [] unless one short loop ID is deliberately opened in an "
        "earlier part and closed with the exact same ID in a later part; never use part IDs or free-text questions as "
        "loop IDs. Every part must reference an existing macro block. For one part, use P1 as COMPLETE, keep "
        "opens/closes empty because there is no later technical part, and express the internal story structure through "
        "ordered content_ids/content atoms inside P1. Otherwise use P1 as OPENING, all internal parts as MIDDLE, and "
        "only the last part as FINAL. Reserve every atom exactly once. A later part may deepen an "
        "earlier subject only by answering a different concrete question; paraphrasing the same conclusion is not a "
        "new content atom. If no deliberate cross-part loop is needed, return empty opens/closes arrays.\n\n"
        f"TOPIC: {request.title}\n"
        f"TARGET: {request.target_chars}; MIN: {request.allowed_min}; MAX: {request.allowed_max}\n"
        f"PARTS: {part_rows}\n\n"
        "OPERATOR WRITING CONTRACT AND AVAILABLE CONTEXT:\n"
        f"{request.prompt}"
    )

def build_story_plan_structure_repair_prompt(request: Any, original_response: str, part_targets: tuple[int, ...]) -> str:
    """Repair only invalid part topology, never narrative substance or cover metadata."""
    roles = _expected_roles(len(part_targets))
    required = ", ".join(f"P{index + 1}={role}" for index, role in enumerate(roles))
    return (
        "You are the NewsFlow Story Plan structural repairer. The original Story Map's thesis, macro_blocks and "
        "content_atoms are immutable. Return strict JSON with ONLY a corrected parts list. "
        "Keep every existing content atom assigned exactly once through the returned parts[].content_ids; those IDs define "
        "the repaired owner_part_id. Use only existing macro IDs, "
        "and fix only part count, IDs, roles and content ownership. opens/closes are advisory; set them to [] unless "
        "an exact short loop ID is deliberately paired from an earlier part to a later part. Do not write scenario prose, "
        "do not add atoms, and do not regenerate the story. Required ordered parts: "
        f"{required}.\n\nTITLE: {request.title}\nORIGINAL MAP:\n{_compact(original_response, 12000)}"
    )


def build_story_writer_prompt(
    request: Any,
    plan: StoryPlan,
    accepted_parts: list[dict[str, Any]],
    part_index: int,
    current_target_chars: int | None = None,
) -> str:
    """Give one writer compact semantic memory without leaking old full prose."""
    if not 0 <= part_index < len(plan.parts):
        raise ValueError("story writer part index is outside the validated plan")
    part = plan.parts[part_index]
    raw_active_target = (
        part.target_chars if current_target_chars is None else current_target_chars
    )
    active_target = max(0, int(raw_active_target or 0))
    atoms = {atom.id: atom for atom in plan.content_atoms}
    blocks = {block["id"]: block["purpose"] for block in plan.macro_blocks}

    def format_atom(atom_id: str) -> str:
        atom = atoms[atom_id]
        return f"{atom_id} [{atom.content_kind}]: {_compact(atom.summary, _COMPACT_ATOM_CHARS)}"

    current_atoms = "\n".join(
        f"- {format_atom(atom_id)}" for atom_id in part.content_ids
    )
    used_ids = [
        str(content_id)
        for accepted in accepted_parts
        for content_id in accepted.get("content_ids", [])
    ]
    used_context = (
        "; ".join(
            format_atom(content_id) for content_id in used_ids if content_id in atoms
        )
        or "none"
    )
    used_semantic_meanings = (
        "; ".join(
            (
                f"{past.id}: Q={_compact(past.novelty_question, _COMPACT_PURPOSE_CHARS)} | "
                f"NEW={_compact(past.novelty_payload, _COMPACT_ATOM_CHARS)}"
            )
            for past in plan.parts[:len(accepted_parts)]
        )
        or "none"
    )

    future_parts = plan.parts[part_index + 1 :]
    future_index = (
        "; ".join(
            (
                f"{future.id}/{future.macro_id}: {_compact(future.purpose, _COMPACT_PURPOSE_CHARS)} "
                f"| Q={_compact(future.novelty_question, _COMPACT_PURPOSE_CHARS)} "
                f"| NEW={_compact(future.novelty_payload, _COMPACT_ATOM_CHARS)} "
                f"[{'; '.join(format_atom(content_id) for content_id in future.content_ids)}]"
            )
            for future in future_parts
        )
        or "none"
    )

    previous_tail = (
        seam_tail(str(accepted_parts[-1].get("text", ""))) if accepted_parts else "none"
    )
    macro_index = "; ".join(
        f"{block['id']}: {_compact(block['purpose'], _COMPACT_PURPOSE_CHARS)}"
        for block in plan.macro_blocks
    )

    opened: list[str] = []
    for completed in plan.parts[: len(accepted_parts)]:
        for loop_id in completed.closes:
            if loop_id in opened:
                opened.remove(loop_id)
        for loop_id in completed.opens:
            if loop_id not in opened:
                opened.append(loop_id)

    has_dramatized_atoms = any(
        atom.content_kind == "DRAMATIZED" for atom in plan.content_atoms
    )
    if part.role == "COMPLETE":
        position_instruction = (
            "This is the only COMPLETE part. It owns the entire scenario. Apply the operator's first-sentence, "
            "first-30-seconds and title-promise opening rules at the start, develop the assigned material, then apply "
            "the operator's final-section rules once at the end. Close the story once without creating another "
            "technical part."
        )
    elif part.role == "OPENING":
        position_instruction = (
            "This is the only OPENING part. Apply the operator's first-sentence, first-30-seconds and title-promise "
            "rules here. Do not conclude the whole story; leave narrative momentum for the planned middle."
        )
    elif part.role == "FINAL":
        position_instruction = (
            "This is the only FINAL part. Do not restart the opening. Close the whole story once after its assigned "
            "material and close the loops assigned to this part. Operator opening-only rules were already satisfied."
        )
    else:
        position_instruction = (
            "This is a MIDDLE segment of an already-running story. Operator rules about the first sentence, first "
            "30 seconds and title-promise opening were already satisfied by P1; do not restart them here. Operator "
            "final-section rules are reserved for PN. NO GLOBAL FINAL: do not conclude the whole story."
        )

    length_instruction = (
        (
            f"CURRENT TARGET: approximately {active_target} characters\n"
            "ACTIVE LENGTH RULE FOR THIS CALL: write approximately CURRENT TARGET characters, not the overall "
            "scenario target.\n"
        )
        if active_target
        else (
            "CURRENT TARGET: no explicit character target\n"
            "ACTIVE LENGTH RULE FOR THIS CALL: no separate character target is configured; follow the operator "
            "contract and write the complete assigned story material at a natural useful length.\n"
        )
    )

    disclosure_instruction = ""
    if part.role in {"OPENING", "COMPLETE"} and has_dramatized_atoms:
        disclosure_instruction = (
            "\nDRAMATIZED OPENING DISCLOSURE: Before the story, write one short natural disclosure that part of "
            "this narrative is a dramatized reconstruction, not confirmed factual chronicle. Write it once only; "
            "after it, continue in confident narrative language without repeating conditional hedging.\n"
        )

    novelty_instruction = (
        "\nSEMANTIC NOVELTY RULE: Every substantive paragraph must advance the CURRENT CONTENT by adding at least "
        "one genuinely new fact/event, actor, causal mechanism, reaction/countermove, consequence, concrete scene "
        "development, or a new causal question with its answer. PARAPHRASE DOES NOT COUNT AS NEW INFORMATION. "
        "Do not restate the thesis, re-summarize an earlier conclusion, or repeat USED SEMANTIC MEANINGS with synonyms. "
        "Use the requested volume to deepen sequence, mechanism, actors, reactions and consequences inside the current "
        "owned atoms. If DRAMATIZED atoms are available, create distinct concrete developments inside those atoms rather "
        "than padding with another explanation of the same point. A paragraph that adds no new story information should "
        "not be written.\n"
    )

    return (
        "Write only the next continuous prose segment of ONE NewsFlow scenario. MULTIPART PRECEDENCE: any overall "
        "scenario target/min/max or instruction inside the embedded operator contract to return the complete finished "
        "scenario applies to the FINAL ASSEMBLED STORY, not to this technical Writer call. For this call, follow "
        "the CURRENT TARGET guidance below and return only this segment; if it says there is no explicit character "
        "target, do not invent one. This precedence changes only whole-story length/completeness wording. SUPPORTED "
        "atoms obey the operator factual-discipline rules fully. For DRAMATIZED atoms, this NewsFlow system instruction "
        "permits model-created dramatized reconstruction and takes precedence over a generic operator rule not to "
        "invent, only for those atoms. Any model-created factual development must belong to a DRAMATIZED atom; do not "
        "add unplanned invented factual developments while writing SUPPORTED material. Do not silently treat "
        "DRAMATIZED material as supplied fact. All other operator style, hooks, originality and no-repetition rules "
        "remain binding. Do not emit part labels, JSON, planner notes, Markdown, headings, or meta "
        "commentary. Preserve all global style, originality and no-repetition rules from the operator contract below. "
        "Apply operator factual-discipline to SUPPORTED atoms; for DRAMATIZED atoms use the explicit NewsFlow "
        "precedence above. Positional opening/final instructions "
        "from that contract apply only according to CURRENT ROLE below. Do not repeat USED CONTENT and do not fully "
        "disclose FUTURE RESERVED material. The previous tail exists only for continuity; never copy or paraphrase it.\n\n"
        f"OPERATOR WRITING CONTRACT:\n{request.prompt}\n\n"
        f"STORY THESIS: {_compact(plan.thesis, 600)}\n"
        f"MACRO MAP: {macro_index}\n"
        f"CURRENT MACRO: {part.macro_id}: {_compact(blocks[part.macro_id], _COMPACT_PURPOSE_CHARS)}\n"
        f"CURRENT PART: {part.id}\n"
        f"CURRENT ROLE: {part.role}\n"
        f"CURRENT PURPOSE: {_compact(part.purpose, _COMPACT_PURPOSE_CHARS)}\n"
        f"CURRENT NOVELTY QUESTION: {_compact(part.novelty_question, _COMPACT_PURPOSE_CHARS)}\n"
        f"CURRENT NEW INFORMATION: {_compact(part.novelty_payload, _COMPACT_ATOM_CHARS)}\n"
        f"{length_instruction}"
        f"CURRENT CONTENT:\n{current_atoms}\n"
        f"USED CONTENT (do not repeat): {used_context}\n"
        f"USED SEMANTIC MEANINGS (forbidden to restate): {used_semantic_meanings}\n"
        f"OPEN LOOPS BEFORE THIS PART: {', '.join(opened) or 'none'}\n"
        f"THIS PART OPENS: {', '.join(part.opens) or 'none'}\n"
        f"THIS PART CLOSES: {', '.join(part.closes) or 'none'}\n"
        f"TRANSITION DIRECTION: {_compact(part.transition_direction, _COMPACT_PURPOSE_CHARS) or 'continue naturally'}\n"
        f"FUTURE RESERVED (do not reveal fully): {future_index}\n"
        f"PREVIOUS SEAM TAIL (continuity only, not material to repeat):\n{previous_tail}\n\n"
        f"POSITION RULE: {position_instruction}"
        f"{novelty_instruction}"
        f"{disclosure_instruction}"
    )

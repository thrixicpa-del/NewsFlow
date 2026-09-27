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
_COVER_PERSON_ENTITY_TYPES = frozenset({"person", "public_figure", "politician", "human", "individual"})
_COVER_FACE_RESOLUTION_STATUSES = frozenset({"RESOLVED", "NEEDS_REVIEW"})


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


@dataclass(frozen=True)
class StoryPlan:
    thesis: str
    macro_blocks: tuple[dict[str, str], ...]
    content_atoms: tuple[StoryContentAtom, ...]
    parts: tuple[StoryPartPlan, ...]
    cover_face_required: bool = True
    cover_people_candidates: tuple[dict[str, Any], ...] = ()
    cover_primary_person: dict[str, Any] | None = None
    cover_face_resolution_status: str = "NEEDS_REVIEW"

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
            "cover_face_required": self.cover_face_required,
            "cover_people_candidates": [dict(candidate) for candidate in self.cover_people_candidates],
            "cover_primary_person": (
                dict(self.cover_primary_person) if self.cover_primary_person else None
            ),
            "cover_face_resolution_status": self.cover_face_resolution_status,
        }


def calculate_story_part_targets(target_chars: int) -> tuple[int, ...]:
    """Split a requested overall target into evenly distributed ~5k parts."""
    target = max(0, int(target_chars or 0))
    if not target:
        return (0,)
    part_count = max(1, (target + PREFERRED_PART_CHARS // 2) // PREFERRED_PART_CHARS)
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


def _optional_text(value: object) -> str:
    return " ".join(str(value or "").split())


def _id_list(value: object, field: str) -> tuple[str, ...]:
    if value in (None, ""):
        return ()
    if not isinstance(value, list):
        raise TypeError(f"story plan {field} must be a list")
    result = tuple(_clean_text(item, field) for item in value)
    if len(set(result)) != len(result):
        raise ValueError(f"story plan {field} must not contain duplicates")
    return result


def _cover_person_candidate(value: object, field: str) -> dict[str, Any]:
    """Normalise planner-owned public-person evidence for downstream Covers.

    The planner chooses the semantic subject.  Covers may verify a PNG later,
    but never upgrades an organisation/place merely because a matching folder
    happens to exist in the face tree.
    """
    if not isinstance(value, dict):
        raise TypeError(f"story plan {field} must be an object")
    entity_type = _clean_text(value.get("entity_type"), f"{field}.entity_type").casefold()
    if entity_type not in _COVER_PERSON_ENTITY_TYPES:
        raise ValueError("story plan cover person must have an explicit person/public_figure entity_type")
    try:
        confidence = float(value.get("confidence", 0))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"story plan {field}.confidence must be numeric") from exc
    if not 0 <= confidence <= 1:
        raise ValueError(f"story plan {field}.confidence must be between 0 and 1")
    return {
        "name": _clean_text(value.get("name"), f"{field}.name"),
        "entity_type": entity_type,
        "role_in_story": _clean_text(value.get("role_in_story"), f"{field}.role_in_story"),
        "relation_to_story": _clean_text(value.get("relation_to_story"), f"{field}.relation_to_story"),
        "source": _clean_text(value.get("source"), f"{field}.source"),
        "confidence": confidence,
    }


def _expected_roles(part_count: int) -> tuple[str, ...]:
    if part_count == 1:
        return ("COMPLETE",)
    return ("OPENING",) + ("MIDDLE",) * (part_count - 2) + ("FINAL",)


def parse_story_plan_response(text: str, part_targets: tuple[int, ...]) -> StoryPlan:
    """Parse and validate the complete planner map before any writer starts."""
    try:
        raw = json.loads(str(text or ""))
    except json.JSONDecodeError as exc:
        raise ValueError("story planner must return strict JSON") from exc
    if not isinstance(raw, dict):
        raise TypeError("story planner response must be an object")

    targets = tuple(max(0, int(target or 0)) for target in part_targets) or (0,)
    part_count = len(targets)
    expected_ids = tuple(f"P{index}" for index in range(1, part_count + 1))
    expected_roles = _expected_roles(part_count)
    thesis = _clean_text(raw.get("thesis"), "thesis")

    # Every planned ProductionItem gets an explicit Cover face-resolution
    # record. Missing fields are retained as a backwards-compatible
    # NEEDS_REVIEW result so a legacy resumable plan is never invalidated.
    face_required = bool(raw.get("cover_face_required", True))
    raw_candidates = raw.get("cover_people_candidates", [])
    if not isinstance(raw_candidates, list):
        raise TypeError("story plan cover_people_candidates must be a list")
    cover_people_candidates = tuple(
        _cover_person_candidate(candidate, f"cover_people_candidates[{index}]")
        for index, candidate in enumerate(raw_candidates, start=1)
    )
    if len({candidate["name"].casefold() for candidate in cover_people_candidates}) != len(cover_people_candidates):
        raise ValueError("story plan cover_people_candidates must not contain duplicate people")
    raw_primary = raw.get("cover_primary_person")
    cover_primary_person = (
        _cover_person_candidate(raw_primary, "cover_primary_person")
        if raw_primary not in (None, "") else None
    )
    face_status = _optional_text(raw.get("cover_face_resolution_status", "NEEDS_REVIEW")).upper()
    if face_status not in _COVER_FACE_RESOLUTION_STATUSES:
        raise ValueError("story plan cover_face_resolution_status must be RESOLVED or NEEDS_REVIEW")
    if face_status == "RESOLVED" and cover_primary_person is None:
        raise ValueError("story plan RESOLVED cover face requires cover_primary_person")
    if face_status == "NEEDS_REVIEW" and cover_primary_person is not None:
        raise ValueError("story plan NEEDS_REVIEW cover face must not set cover_primary_person")
    if cover_primary_person and not any(
        candidate["name"].casefold() == cover_primary_person["name"].casefold()
        for candidate in cover_people_candidates
    ):
        raise ValueError("story plan cover_primary_person must be one of cover_people_candidates")

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

    opened: set[str] = set()
    for part in parts:
        for loop_id in part.closes:
            if loop_id not in opened:
                raise ValueError(
                    f"story plan part {part.id} closes unopened loop {loop_id}"
                )
            opened.remove(loop_id)
        for loop_id in part.opens:
            if loop_id in opened:
                raise ValueError(f"story plan opens loop {loop_id} more than once")
            opened.add(loop_id)
    if opened:
        raise ValueError("story plan leaves planned loops unclosed")

    return StoryPlan(
        thesis=thesis,
        macro_blocks=tuple(macro_blocks),
        content_atoms=tuple(atoms),
        parts=tuple(parts),
        cover_face_required=face_required,
        cover_people_candidates=cover_people_candidates,
        cover_primary_person=cover_primary_person,
        cover_face_resolution_status=face_status,
    )


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
    persisted.setdefault("cover_face_required", True)
    persisted.setdefault("cover_people_candidates", [])
    persisted.setdefault("cover_primary_person", None)
    persisted.setdefault("cover_face_resolution_status", "NEEDS_REVIEW")
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
        "still be materially distinct. Do not fill parts by paraphrasing one meaning. Keep thesis/purposes/atom summaries compact. Every part purpose must name a concrete "
        "distinct responsibility; never use generic purposes like 'continue' or 'develop further' without saying what "
        "new question/content that part owns. Each macro block needs id and purpose. Every part needs id, role, purpose, macro_id, content_ids, opens, closes and transition_direction. "
        "Every part must reference an existing macro block. For one part, use P1 as COMPLETE, keep opens/closes "
        "empty because there is no later technical part, and express the internal story structure through ordered "
        "content_ids/content atoms inside P1. Otherwise use P1 as OPENING, all internal parts as MIDDLE, and only the "
        "last part as FINAL. Reserve every atom exactly once. A later part may deepen an "
        "earlier subject only by answering a different concrete question; paraphrasing the same conclusion is not a "
        "new content atom. Any opened loop must be closed by a later planned part.\n\n"
        "COVER FACE RESOLUTION (required for this ProductionItem): return cover_face_required=true, "
        "cover_people_candidates (ranked real public people only), cover_primary_person, and "
        "cover_face_resolution_status RESOLVED or NEEDS_REVIEW. Every candidate needs name, entity_type "
        "person/public_figure, role_in_story, relation_to_story, source and confidence from 0 to 1. Select a "
        "person only from explicit current-story evidence: selected people, typed person entities, a named person "
        "in title/topic/context, or a factual action/decision relation. Treat an institution/place/event as a semantic "
        "anchor: continue through the supplied sides, actions and responsibility to identify the factually relevant "
        "decision maker or public figure. Do not stop at the institution/place/event and do not use a static country-or-place "
        "to leader mapping. Never infer a person from geography, a country, an organisation or a place without a factual "
        "relation in the ProductionItem. Only after those evidence-based steps fail, return an empty candidate list, null "
        "cover_primary_person and NEEDS_REVIEW; do not invent a leader.\n\n"
        f"TOPIC: {request.title}\n"
        f"TARGET: {request.target_chars}; MIN: {request.allowed_min}; MAX: {request.allowed_max}\n"
        f"PARTS: {part_rows}\n\n"
        "OPERATOR WRITING CONTRACT AND AVAILABLE CONTEXT:\n"
        f"{request.prompt}"
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

    future_parts = plan.parts[part_index + 1 :]
    future_index = (
        "; ".join(
            (
                f"{future.id}/{future.macro_id}: {_compact(future.purpose, _COMPACT_PURPOSE_CHARS)} "
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
        f"{length_instruction}"
        f"CURRENT CONTENT:\n{current_atoms}\n"
        f"USED CONTENT (do not repeat): {used_context}\n"
        f"OPEN LOOPS BEFORE THIS PART: {', '.join(opened) or 'none'}\n"
        f"THIS PART OPENS: {', '.join(part.opens) or 'none'}\n"
        f"THIS PART CLOSES: {', '.join(part.closes) or 'none'}\n"
        f"TRANSITION DIRECTION: {_compact(part.transition_direction, _COMPACT_PURPOSE_CHARS) or 'continue naturally'}\n"
        f"FUTURE RESERVED (do not reveal fully): {future_index}\n"
        f"PREVIOUS SEAM TAIL (continuity only, not material to repeat):\n{previous_tail}\n\n"
        f"POSITION RULE: {position_instruction}"
        f"{disclosure_instruction}"
    )

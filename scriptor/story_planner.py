"""Deterministic planning records for long, continuous NewsFlow scripts.

This module deliberately contains no provider I/O.  The runner owns calls and
persists these small JSON-safe records before it accepts the first writer part.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from typing import Any

PREFERRED_PART_CHARS = 5_000


@dataclass(frozen=True)
class StoryContentAtom:
    id: str
    summary: str
    owner_part_id: str


@dataclass(frozen=True)
class StoryPartPlan:
    id: str
    role: str
    purpose: str
    content_ids: tuple[str, ...]
    target_chars: int


@dataclass(frozen=True)
class StoryPlan:
    thesis: str
    macro_blocks: tuple[dict[str, str], ...]
    content_atoms: tuple[StoryContentAtom, ...]
    parts: tuple[StoryPartPlan, ...]

    def to_dict(self) -> dict:
        return {
            "thesis": self.thesis,
            "macro_blocks": [dict(block) for block in self.macro_blocks],
            "content_atoms": [asdict(atom) for atom in self.content_atoms],
            "parts": [
                {**asdict(part), "content_ids": list(part.content_ids)}
                for part in self.parts
            ],
        }


def calculate_story_part_targets(target_chars: int) -> tuple[int, ...]:
    """Split a requested overall target into evenly distributed ~5k parts."""
    target = max(0, int(target_chars or 0))
    if not target:
        return (0,)
    part_count = max(1, (target + PREFERRED_PART_CHARS // 2) // PREFERRED_PART_CHARS)
    quotient, remainder = divmod(target, part_count)
    return tuple(quotient + (1 if index < remainder else 0) for index in range(part_count))


def _clean_text(value: object, field: str) -> str:
    cleaned = " ".join(str(value or "").split())
    if not cleaned:
        raise ValueError(f"story plan requires {field}")
    return cleaned


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
        macro_blocks.append({"id": block_id, "purpose": _clean_text(block.get("purpose"), f"macro_blocks[{index}].purpose")})

    raw_parts = raw.get("parts")
    if not isinstance(raw_parts, list) or len(raw_parts) != part_count:
        raise ValueError(f"story plan requires exactly {part_count} parts")
    parts: list[StoryPartPlan] = []
    for index, (raw_part, expected_id, expected_role, target) in enumerate(
        zip(raw_parts, expected_ids, expected_roles, targets, strict=True), start=1,
    ):
        if not isinstance(raw_part, dict):
            raise TypeError("story plan part must be an object")
        part_id = _clean_text(raw_part.get("id"), f"parts[{index}].id")
        if part_id != expected_id:
            raise ValueError(f"story plan part IDs must be ordered as {expected_id}")
        role = _clean_text(raw_part.get("role"), f"parts[{index}].role").upper()
        if role != expected_role:
            raise ValueError(f"story plan part {part_id} role must be {expected_role}")
        raw_ids = raw_part.get("content_ids")
        if not isinstance(raw_ids, list) or not raw_ids:
            raise ValueError(f"story plan part {part_id} requires content_ids")
        content_ids = tuple(_clean_text(value, f"parts[{index}].content_ids") for value in raw_ids)
        if len(set(content_ids)) != len(content_ids):
            raise ValueError(f"story plan part {part_id} duplicates content IDs")
        parts.append(StoryPartPlan(
            id=part_id,
            role=role,
            purpose=_clean_text(raw_part.get("purpose"), f"parts[{index}].purpose"),
            content_ids=content_ids,
            target_chars=target,
        ))

    raw_atoms = raw.get("content_atoms")
    if not isinstance(raw_atoms, list) or not raw_atoms:
        raise ValueError("story plan requires content_atoms")
    atoms: list[StoryContentAtom] = []
    atom_by_id: dict[str, StoryContentAtom] = {}
    for index, raw_atom in enumerate(raw_atoms, start=1):
        if not isinstance(raw_atom, dict):
            raise TypeError("story plan content atom must be an object")
        atom = StoryContentAtom(
            id=_clean_text(raw_atom.get("id"), f"content_atoms[{index}].id"),
            summary=_clean_text(raw_atom.get("summary"), f"content_atoms[{index}].summary"),
            owner_part_id=_clean_text(raw_atom.get("owner_part_id"), f"content_atoms[{index}].owner_part_id"),
        )
        if atom.id in atom_by_id:
            raise ValueError("story plan content atom IDs must be unique")
        if atom.owner_part_id not in expected_ids:
            raise ValueError("story plan content atom owner must reference a planned part")
        atom_by_id[atom.id] = atom
        atoms.append(atom)

    assigned_ids = [content_id for part in parts for content_id in part.content_ids]
    if len(set(assigned_ids)) != len(assigned_ids):
        raise ValueError("story plan content atom is assigned more than once")
    if set(assigned_ids) != set(atom_by_id):
        raise ValueError("story plan content atom ownership must cover every planned atom exactly once")
    for part in parts:
        for content_id in part.content_ids:
            if atom_by_id[content_id].owner_part_id != part.id:
                raise ValueError("story plan content atom owner conflicts with its part")

    return StoryPlan(
        thesis=thesis,
        macro_blocks=tuple(macro_blocks),
        content_atoms=tuple(atoms),
        parts=tuple(parts),
    )


def story_plan_from_dict(value: dict[str, Any]) -> StoryPlan:
    """Revalidate one persisted plan instead of trusting session JSON blindly."""
    if not isinstance(value, dict):
        raise TypeError("persisted story plan must be an object")
    raw_parts = value.get("parts")
    if not isinstance(raw_parts, list):
        raise TypeError("persisted story plan requires parts")
    try:
        targets = tuple(max(0, int(part.get("target_chars", 0) or 0)) for part in raw_parts)
    except (AttributeError, TypeError, ValueError) as exc:
        raise ValueError("persisted story plan has invalid part targets") from exc
    return parse_story_plan_response(json.dumps(value, ensure_ascii=False), targets)


def seam_tail(text: str, limit: int = 500) -> str:
    """Return at most one bounded, sentence-aligned tail from the prior part."""
    cleaned = str(text or "").strip()
    if len(cleaned) <= limit:
        return cleaned
    tail = cleaned[-max(1, int(limit)):]
    boundary = re.search(r"[.!?…]\s+", tail)
    return tail[boundary.end():].strip() if boundary else tail.strip()


def build_story_planner_prompt(request: Any, part_targets: tuple[int, ...]) -> str:
    """Build one strict-JSON organizer request without replacing the writing contract."""
    part_rows = ", ".join(
        f"P{index + 1}≈{target} chars" for index, target in enumerate(part_targets)
    )
    return (
        "You are the NewsFlow Story Planner. Organize only the supplied topic and context; do not invent news, "
        "write prose, or change the operator writing contract. Return strict JSON with thesis, macro_blocks, "
        "content_atoms and parts. Every atom must have id, summary and owner_part_id. Every part must have id, "
        "role, purpose and content_ids. Plan the complete story before any writer begins. Use P1 as OPENING, "
        "all internal parts as MIDDLE, and only the last part as FINAL. Reserve each atom exactly once.\n\n"
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
) -> str:
    """Give one writer its allocated material without leaking old full prose."""
    if not 0 <= part_index < len(plan.parts):
        raise ValueError("story writer part index is outside the validated plan")
    part = plan.parts[part_index]
    atoms = {atom.id: atom for atom in plan.content_atoms}
    current_atoms = "\n".join(
        f"- {atom_id}: {atoms[atom_id].summary}" for atom_id in part.content_ids
    )
    used_ids = [
        str(content_id) for accepted in accepted_parts
        for content_id in accepted.get("content_ids", [])
    ]
    future_parts = plan.parts[part_index + 1:]
    future_index = "; ".join(
        f"{future.id}: {future.purpose} [{', '.join(future.content_ids)}]"
        for future in future_parts
    ) or "none"
    previous_tail = seam_tail(str(accepted_parts[-1].get("text", ""))) if accepted_parts else "none"
    macro_index = "; ".join(
        f"{block['id']}: {block['purpose']}" for block in plan.macro_blocks
    )
    final_instruction = (
        "This is the only FINAL part: close the whole story once after its assigned material."
        if part.role == "FINAL"
        else "NO GLOBAL FINAL: do not conclude the whole story or resolve future reserved material."
    )
    return (
        "Write only the next continuous prose segment of one NewsFlow scenario. Do not emit part labels, JSON, "
        "planner notes, Markdown, headings, or meta commentary. Preserve the operator contract below exactly; "
        "it defines style and factual discipline. Do not repeat used atoms and do not fully disclose future atoms.\n\n"
        f"OPERATOR WRITING CONTRACT:\n{request.prompt}\n\n"
        f"STORY THESIS: {plan.thesis}\n"
        f"MACRO MAP: {macro_index}\n"
        f"CURRENT PART: {part.id}\n"
        f"CURRENT ROLE: {part.role}\n"
        f"CURRENT PURPOSE: {part.purpose}\n"
        f"CURRENT TARGET: approximately {part.target_chars} characters\n"
        f"CURRENT CONTENT:\n{current_atoms}\n"
        f"USED CONTENT IDS: {', '.join(used_ids) or 'none'}\n"
        f"FUTURE RESERVED: {future_index}\n"
        f"PREVIOUS SEAM TAIL (continuity only, not material to repeat):\n{previous_tail}\n\n"
        f"POSITION RULE: {final_instruction}"
    )

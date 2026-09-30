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
_COMPACT_AVOID_CHARS = 140
_WRITER_RECENT_USED_ATOMS = 6
_WRITER_RECENT_USED_PARTS = 2
_WRITER_DETAILED_FUTURE_PARTS = 2
_WRITER_DETAILED_MACROS = 6
_CONTENT_KINDS = frozenset({"SUPPORTED", "DRAMATIZED"})
_STATE_TRANSITION_CONTRACT = "BEFORE_DEVELOPMENT_AFTER"


def _strict_object(properties: dict[str, Any]) -> dict[str, Any]:
    """Return the small strict JSON-Schema object form accepted by Responses."""
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties),
        "additionalProperties": False,
    }


def _string_array_schema() -> dict[str, Any]:
    return {"type": "array", "items": {"type": "string"}}


def _story_part_schema() -> dict[str, Any]:
    return _strict_object({
        "id": {"type": "string"},
        "role": {"type": "string"},
        "purpose": {"type": "string"},
        "macro_id": {"type": "string"},
        "content_ids": _string_array_schema(),
        "opens": _string_array_schema(),
        "closes": _string_array_schema(),
        "transition_direction": {"type": "string"},
        "novelty_question": {"type": "string"},
        "novelty_payload": {"type": "string"},
    })


def story_planner_response_format() -> dict[str, Any]:
    """Trusted Responses Structured Outputs contract for a fresh Story Map.

    It constrains only JSON transport and the fields the runtime already owns;
    it deliberately does not encode subjective quality or minimum-event rules.
    """
    atom = _strict_object({
        "id": {"type": "string"},
        "summary": {"type": "string"},
        "owner_part_id": {"type": "string"},
        "content_kind": {"type": "string", "enum": sorted(_CONTENT_KINDS)},
        "state_before": {"type": "string"},
        "changed_subject": {"type": "string"},
        "development": {"type": "string"},
        "resulting_state": {"type": "string"},
        "state_after": {"type": "string"},
        "novelty_question": {"type": "string"},
        "novelty_payload": {"type": "string"},
        "do_not_repeat": {"type": "string"},
        "event_steps": _string_array_schema(),
    })
    return {
        "type": "json_schema",
        "name": "newsflow_story_plan",
        "strict": True,
        "schema": _strict_object({
            "state_transition_contract": {"type": "string", "enum": [_STATE_TRANSITION_CONTRACT]},
            "thesis": {"type": "string"},
            # The spine is planning evidence for fresh maps.  It is additive:
            # resumed legacy maps remain valid when this field is absent.
            "event_spine": _string_array_schema(),
            "macro_blocks": {"type": "array", "items": _strict_object({
                "id": {"type": "string"}, "purpose": {"type": "string"},
            })},
            "content_atoms": {"type": "array", "items": atom},
            "parts": {"type": "array", "items": _story_part_schema()},
        }),
    }


def story_plan_structure_repair_response_format() -> dict[str, Any]:
    """Trusted JSON transport contract for parts-only Planner recovery."""
    return {
        "type": "json_schema",
        "name": "newsflow_story_plan_parts_repair",
        "strict": True,
        "schema": _strict_object({
            "parts": {"type": "array", "items": _story_part_schema()},
        }),
    }
# These advisory lexical signatures are retained only for deterministic
# diagnostics/tests. They are not parser acceptance criteria: a schema parser
# cannot reliably decide that a natural-language development is insufficient.
_ABSTRACT_INTERPRETIVE_SUBJECT_STEMS = frozenset({
    "смысл", "логик", "сигнал", "цен", "давлен", "баланс", "ситуац", "простр",
    "важнос", "тревож", "интерп", "meanin", "logic", "signal", "pressu", "balanc",
    "situat", "import", "tensio", "interp",
})
_ABSTRACT_TRANSITION_SUBJECT_STEMS = frozenset({
    "интенс", "перспект", "корид", "окн", "состоян", "режим", "лини",
    "intens", "prospect", "corrid", "window", "state", "mode", "line",
})
_INTERPRETIVE_FRAME_STEMS = frozenset({
    "воспри", "выгляд", "означа", "показыв", "демонс", "символ",
    "тракту", "смысл", "значен", "ожидан", "вероят", "итог",
    "станов", "усил", "сузило", "растет", "повыш",
    "percei", "appear", "mean", "show", "demons", "symbol", "inter",
    "expect", "likely", "signif", "conclu", "intens", "narrow", "increa",
})
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
    novelty_question: str = ""
    novelty_payload: str = ""
    do_not_repeat: str = ""
    state_before: str = ""
    state_after: str = ""
    changed_subject: str = ""
    development: str = ""
    resulting_state: str = ""
    # Fresh planners use this one ordered action/result sequence as the
    # canonical expansion source.  It is additive so legacy persisted maps
    # continue to use writer_material or their transition fields on resume.
    event_steps: tuple[str, ...] = ()
    # Planner-supplied expansion beats are optional guidance for the first
    # Writer pass.  They must never invalidate an otherwise resumable map.
    writer_material: tuple[str, ...] = ()


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
    # Fresh Structured Outputs carry the whole causal-temporal sequence before
    # it is allocated to atoms.  Empty is the deliberate legacy value.
    event_spine: tuple[str, ...] = ()

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
            "event_spine": list(self.event_spine),
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
    """Load exactly one provider JSON object, tolerating transport wrappers.

    A model may put one complete JSON root in a Markdown fence or surround it
    with a short explanatory sentence.  That is a transport wrapper, not a
    license to scan an invalid root for a convenient child dictionary: doing
    so could turn a truncated Story Map into an unrelated macro block.
    """
    text = str(value or "").strip()
    # A short prose preface/suffix around one fenced body is a documented
    # transport wrapper used by older repair adapters.  The delimiter-free
    # prefix/suffix make a second fenced candidate impossible here.
    fenced = re.fullmatch(
        r"[^`]*```(?:json)?\s*\n?(.*?)\s*```[^`]*",
        text,
        re.DOTALL | re.IGNORECASE,
    )
    if fenced:
        text = fenced.group(1).strip()
    elif text.startswith("```"):
        # A fence is an explicit wrapper only when it encloses one complete
        # body.  In particular, two fenced candidates must not select the
        # first one as if the second had not been returned.
        raise ValueError(invalid_message)
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as first_error:
        # Only a plainly textual prefix may wrap a root object.  Once a JSON
        # root opener is present, parsing that root either succeeds in full or
        # fails: searching inside a damaged object/array could substitute a
        # nested macro, part, or atom for the Story Map itself.
        if text.startswith(("{", "[")):
            raise ValueError(invalid_message) from first_error
        decoder = json.JSONDecoder()
        root_start = text.find("{")
        if root_start < 0:
            raise ValueError(invalid_message) from first_error
        prefix = text[:root_start]
        if any(marker in prefix for marker in ("{", "[", "```")):
            raise ValueError(invalid_message) from first_error
        try:
            candidate, end = decoder.raw_decode(text[root_start:])
        except json.JSONDecodeError as wrapper_error:
            raise ValueError(invalid_message) from wrapper_error
        # An explicit prose wrapper may contain prose before/after exactly one
        # JSON object.  It may not hide another object, array or Markdown
        # fence, because that would make the parser choose a provider answer
        # arbitrarily.  This is intentionally stricter than brace balancing:
        # quotes and escaped braces are handled only by the JSON decoder.
        suffix = text[root_start + end:].strip()
        if any(marker in suffix for marker in ("{", "[", "```")):
            raise ValueError(invalid_message) from first_error
        parsed = candidate
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
        # Numeric limits and explicit negation carry meaning even though they
        # are short.  Losing either turns opposite states into a false
        # near-copy (for example 10→20 or permits→does not permit).
        meaningful_short = word.isdigit() or word in {"не", "нет", "not", "no"}
        if (len(word) < 4 and not meaningful_short) or word in _SEMANTIC_STOPWORDS or stem in _SEMANTIC_STOPWORDS:
            continue
        tokens.add(stem)
    return frozenset(tokens)


def _obvious_semantic_duplicate(left: object, right: object) -> bool:
    """Catch only obvious near-copies, never merely related story material.

    The guard is intentionally stricter than a containment score. Two rows may
    share topic words while adding a different actor/mechanism/consequence.
    Reject only when their compact signatures are effectively the same.
    """
    first = _semantic_tokens(left)
    second = _semantic_tokens(right)
    # A changed number or polarity is never a duplicate, even when every
    # surrounding topic word remains identical.
    first_anchors = {token for token in first if token.isdigit() or token in {"не", "нет", "not", "no"}}
    second_anchors = {token for token in second if token.isdigit() or token in {"не", "нет", "not", "no"}}
    if first_anchors != second_anchors:
        return False
    if min(len(first), len(second)) < 4:
        return False
    if first == second:
        return True
    intersection = len(first & second)
    containment = intersection / min(len(first), len(second))
    union = len(first | second)
    jaccard = intersection / union if union else 0.0
    return containment >= 0.95 and jaccard >= 0.82


def _has_concrete_story_development(atom: StoryContentAtom) -> bool:
    """Return true only for a declared, observable before/development/after arc.

    The test is deliberately domain-neutral: it validates the Planner's
    explicit structured change rather than guessing meaning from topic words.
    """
    before = _optional_text(atom.state_before)
    after = _optional_text(atom.state_after)
    changed_subject = _optional_text(atom.changed_subject)
    development = _optional_text(atom.development)
    resulting_state = _optional_text(atom.resulting_state)
    if not (
        before
        and after
        and changed_subject
        and development
        and resulting_state
        and before.casefold() != after.casefold()
        and not _obvious_semantic_duplicate(before, after)
    ):
        return False

    subject_tokens = _semantic_tokens(changed_subject)
    frame_tokens = _semantic_tokens(
        f"{atom.summary} {development} {resulting_state}"
    )
    return not (
        subject_tokens & (
            _ABSTRACT_INTERPRETIVE_SUBJECT_STEMS
            | _ABSTRACT_TRANSITION_SUBJECT_STEMS
        )
        and frame_tokens & _INTERPRETIVE_FRAME_STEMS
    )


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


def story_part_skeleton(part_targets: tuple[int, ...]) -> str:
    """Return the runtime-owned immutable technical part topology."""
    targets = tuple(part_targets) or (0,)
    roles = _expected_roles(len(targets))
    rows = [f"EXACT_PART_COUNT={len(targets)}"]
    rows.extend(f"P{index}={role}" for index, role in enumerate(roles, start=1))
    return "; ".join(rows)


def _minimum_semantic_atoms(target_chars: int, role: str) -> int:
    """Return advisory coverage guidance for a fresh Story Map prompt.

    This is deliberately not a parser/runtime floor: atom count alone cannot
    judge whether a structurally valid map has enough story material.
    """
    target = max(0, int(target_chars or 0))
    if not target:
        return 1
    if role == "COMPLETE" and target >= 6_000:
        return 5
    # A 12k story is split into three ~4k parts. Two developments per
    # part force the Writer to stretch each event into commentary; require
    # enough real progression for event-first prose instead.
    if target >= 3_500:
        return 3
    if target >= 2_500:
        return 2
    return 1


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


def _normalise_nested_part_atoms(raw: dict[str, Any]) -> dict[str, Any]:
    """Lift a complete provider ``parts[].content_atoms`` transport shape.

    The canonical persisted Story Map remains top-level ``content_atoms``.  A
    few valid Responses payloads place the same records beside each part; this
    bounded normalization accepts that representation only when the canonical
    field is absent and every declared part supplies an atom list.  All normal
    ID, role, macro and exact-ownership validation still runs afterward.
    """
    if "content_atoms" in raw:
        return raw
    parts = raw.get("parts")
    if not isinstance(parts, list) or not parts or not all(
        isinstance(part, dict) and isinstance(part.get("content_atoms"), list)
        for part in parts
    ):
        return raw
    atoms = [atom for part in parts for atom in part["content_atoms"]]
    return {**raw, "content_atoms": atoms}


def parse_story_plan_response(
    text: str,
    part_targets: tuple[int, ...],
    *,
    validate_semantic_novelty: bool = True,
    require_state_transitions: bool = False,
) -> StoryPlan:
    """Parse and validate the complete planner map before any writer starts.

    Fresh Planner responses validate obvious semantic near-copies. Persisted
    legacy maps may opt out of that new validation so an old accepted prefix
    never becomes unreadable after an upgrade.
    """
    raw = _load_json_object(
        text,
        invalid_message="story planner must return strict JSON",
        object_message="story planner response must be an object",
    )
    raw = _normalise_nested_part_atoms(raw)
    state_transition_contract = _optional_text(raw.get("state_transition_contract"))
    raw_spine = raw.get("event_spine", [])
    event_spine = tuple(
        text for text in (
            _optional_text(item)
            for item in (raw_spine if isinstance(raw_spine, list) else [])
        ) if text
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
        summary = _clean_text(
            raw_atom.get("summary"), f"content_atoms[{index}].summary"
        )
        atom = StoryContentAtom(
            id=_clean_text(raw_atom.get("id"), f"content_atoms[{index}].id"),
            summary=summary,
            owner_part_id=_clean_text(
                raw_atom.get("owner_part_id"), f"content_atoms[{index}].owner_part_id"
            ),
            content_kind=content_kind,
            novelty_question=_optional_text(raw_atom.get("novelty_question")) or summary,
            novelty_payload=_optional_text(raw_atom.get("novelty_payload")) or summary,
            do_not_repeat=_optional_text(raw_atom.get("do_not_repeat")),
            state_before=_optional_text(raw_atom.get("state_before")),
            state_after=_optional_text(raw_atom.get("state_after")),
            changed_subject=_optional_text(raw_atom.get("changed_subject")),
            development=_optional_text(raw_atom.get("development")),
            resulting_state=_optional_text(raw_atom.get("resulting_state")),
            event_steps=tuple(
                text for text in (
                    _optional_text(item)
                    for item in (
                        raw_atom.get("event_steps", [])
                        if isinstance(raw_atom.get("event_steps"), list)
                        else [raw_atom.get("event_steps", "")]
                    )
                ) if text
            ),
            writer_material=tuple(
                text for text in (
                    _optional_text(item)
                    for item in (
                        raw_atom.get("writer_material", [])
                        if isinstance(raw_atom.get("writer_material"), list)
                        else [raw_atom.get("writer_material", "")]
                    )
                ) if text
            ),
        )
        if atom.id in atom_by_id:
            raise ValueError("story plan content atom IDs must be unique")
        atom_by_id[atom.id] = atom
        atoms.append(atom)

    if require_state_transitions and state_transition_contract != _STATE_TRANSITION_CONTRACT:
        raise ValueError("story plan requires BEFORE_DEVELOPMENT_AFTER state transition contract")
    validate_state_transitions = (
        require_state_transitions or state_transition_contract == _STATE_TRANSITION_CONTRACT
    )
    if validate_state_transitions:
        for atom in atoms:
            if not (
                atom.state_before
                and atom.state_after
                and atom.changed_subject
                and atom.development
                and atom.resulting_state
            ):
                raise ValueError("story plan atom requires structured concrete change")
            # The parser owns hard structure only.  _has_concrete_story_development
            # remains an advisory diagnostic, not an acceptance blocker: stem
            # matching cannot reliably classify an otherwise complete map.

    # Only after all atom fields, transitions and atom novelty are valid may
    # the runtime assess technical parts. The runtime knows this skeleton; it
    # is not a model-owned narrative choice.
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
                transition_direction=_optional_text(raw_part.get("transition_direction")),
                novelty_question=_optional_text(raw_part.get("novelty_question")),
                novelty_payload=_optional_text(raw_part.get("novelty_payload")),
            )
        )

    for atom in atoms:
        if atom.owner_part_id not in expected_ids:
            raise ValueError("story plan content atom owner must reference a planned part")

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

    # opens/closes are continuity hints, not story ownership. Keep strict
    # validation for parts/macros/atoms above, then locally discard malformed
    # loop metadata instead of asking the provider to repair prose.
    parts = _normalise_advisory_loops(parts)

    return StoryPlan(
        thesis=thesis,
        macro_blocks=tuple(macro_blocks),
        content_atoms=tuple(atoms),
        parts=tuple(parts),
        event_spine=event_spine,
    )


def repair_story_plan_parts_response(
    text: str,
    original_response: str,
    part_targets: tuple[int, ...],
    *,
    require_state_transitions: bool = False,
) -> StoryPlan:
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
    return parse_story_plan_response(
        json.dumps(merged, ensure_ascii=False),
        part_targets,
        require_state_transitions=require_state_transitions,
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
    # Covers metadata from old Story Maps is deliberately inert on resume.
    # Identity resolution belongs to the Covers workflow, never the Writer.
    for key in tuple(persisted):
        if key.startswith("cover_"):
            persisted.pop(key, None)
    return parse_story_plan_response(
        json.dumps(persisted, ensure_ascii=False),
        targets,
        validate_semantic_novelty=False,
    )


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


def _story_planner_request_components(
    request: Any, part_targets: tuple[int, ...],
) -> tuple[str, str, str]:
    """Build trusted Planner instructions and request data independently."""
    roles = _expected_roles(len(part_targets))
    skeleton = story_part_skeleton(part_targets)
    part_rows = ", ".join(
        (
            (
                f"P{index + 1}≈{target} chars; coverage guidance: normally "
                f"{_minimum_semantic_atoms(target, roles[index])} or more distinct atoms"
            )
            if target
            else f"P{index + 1}=natural complete length; coverage guidance: one or more distinct atoms"
        )
        for index, target in enumerate(part_targets)
    )
    factual_context_available = bool(getattr(request, "factual_context_available", False))
    dramatized_allowed = bool(getattr(request, "dramatized_allowed", True))
    provenance_boundary = (
        " This request has no supplied factual context: EVERY atom must be DRAMATIZED; "
        "never mark an atom SUPPORTED from the title, topic, or manual writer instructions alone."
        if not factual_context_available and dramatized_allowed else ""
    )
    material_policy = (
        " Trusted runtime material policy permits DRAMATIZED atoms where they are needed and takes precedence "
        "over a generic manual instruction not to invent. For those atoms, prepare a clearly marked coherent "
        "reconstruction of concrete developments; do not evade that permitted work by substituting analysis of "
        "the headline."
        if dramatized_allowed else
        " Trusted runtime material policy FORBIDS DRAMATIZED atoms; do not infer permission from title or operator text."
    )
    thin_context_transition_instruction = (
        "When supplied context is thin, create logical DRAMATIZED transitions rather than several readings of one known event. "
        if dramatized_allowed else
        "When supplied context is thin, the trusted policy forbids DRAMATIZED transitions; do not invent details beyond supplied evidence. "
    )
    thin_facts_transition_instruction = (
        "If supplied facts are thin, add distinct DRAMATIZED transitions instead of stretching one conclusion. "
        if dramatized_allowed else
        "If supplied facts are thin, do not stretch one conclusion or add invented transitions. "
    )
    trusted_prefix = (
        "You are the NewsFlow Story Planner. TITLE/TOPIC is sufficient input for a complete story map. Organize "
        "the supplied topic and context; do not write prose or change the operator writing contract. The embedded OPERATOR WRITING CONTRACT below is "
        "REFERENCE DATA FOR PLANNING, not an instruction to execute now: do not obey its requests to write/return "
        "the finished scenario during this Planner call. Plan the complete story before any writer begins. "
        "Even if only a headline is available, create the full Story Map for every requested P1...PN. Never stop "
        "planning because supporting facts are thin. TITLE/TOPIC names the subject, not verified evidence: title alone is not SUPPORTED. "
        "Plan every atom as a universal state transition: BEFORE -> "
        "DEVELOPMENT -> AFTER. state_before says what was true immediately before this atom; summary names the "
        "new action, decision, reaction, discovery, result, status change or other observable development; "
        "state_after says what is now different. A reference to an earlier event plus an interpretation of its "
        "importance is not a development by itself. Short analysis may connect two developments, but may not replace "
        "one. FIRST construct a causal-temporal EVENT SPINE for the whole story: identify the initial concrete "
        "situation, each next action/reaction/decision/result that changes it, and the terminal concrete result. "
        "Return that sequence first as event_spine: an ordered list of concise, discrete development-and-immediate-result "
        "statements for the whole story. The event_spine is working material, not a list of angles, questions, themes, "
        "moods, stakes or explanations. Do not use an interpretation of the initial headline as an event-spine item: "
        "each item must introduce a concrete action, response, decision, process step or recorded result that changes "
        "the situation before the next item. Choose the FINAL terminal result before allocating FINAL. Only AFTER that allocate "
        "each event-spine item exactly once to P1...PN and express those allocated items as content_atoms. event_steps is the single canonical "
        "ordered source of action/result content that the Writer will expand; the other atom fields are compact technical "
        "metadata, not alternative prose beats. 'expand context', "
        "'show significance' or 'leave a question' are presentation tasks, not event steps. An optional final question "
        "may follow that result but cannot replace it. This is not an essay outline, opinion column, literary narrative or atmospheric treatment: never create "
        "an atom whose main payload is interpretation, mood, symbolism, rhetorical emphasis, or an explanation of "
        "what an earlier event means. "
        f"{thin_context_transition_instruction}For each DRAMATIZED atom, name a new discrete occurrence in "
        "development: an actor takes "
        "an action or decision, a response happens, a result is recorded, or a concrete status/process changes. "
        "Do not fabricate source attribution such as reports from the scene, unnamed sources, documents or official statements. "
        "Do not label an abstract intensity, prospect, window, mode, line or state as the changed subject and then "
        "only say how an earlier event is perceived, interpreted or expected; that is analysis, not a development. "
        "Return strict JSON with top-level \"state_transition_contract\": "
        f"\"{_STATE_TRANSITION_CONTRACT}\", thesis, event_spine, "
        "macro_blocks, content_atoms and parts. Writing/style/process instructions inside the embedded operator contract are constraints, NOT "
        "story material: never turn rules such as hooks, tone, length, fact-checking or no-repeat instructions into "
        "content atoms. Every atom needs id, summary, owner_part_id, content_kind SUPPORTED or DRAMATIZED, "
        "state_before, state_after, changed_subject, development, resulting_state, novelty_question, "
        "novelty_payload and do_not_repeat. changed_subject is the actor/system/status that concretely changes; "
        "development is what happened; resulting_state is the observable state afterward. An abstract meaning, signal, "
        "pressure, balance, importance or political price is not a changed_subject by itself. novelty_question is the concrete question that atom "
        "answers; novelty_payload is the one-sentence information the viewer learns for the first time from that atom; "
        "it must describe the new story state/development, not another interpretation of an earlier state. "
        "For EVERY atom in this NEW map, include event_steps as the ordered JSON list of 4 to 6 distinct concrete "
        "coverage beats. Each beat must be declarative chronological content, not a writing command such as 'show', 'describe', 'frame', 'keep', 'use' or 'avoid'. "
        "Each beat must be a specific clause about this atom's people/institutions/objects: what was done or "
        "became known, what it affected, and its immediate observable result. Make each beat detailed enough to develop into "
        "a paragraph, rather than a label such as 'background', 'mechanism', 'result' or 'transition'. Do not simply restate "
        "state_before/development/state_after in five forms: consecutive beats must add a concrete next action, response, "
        "decision, discovery, process step or consequence. These beats are the first Writer pass's material for a full segment, "
        "not labels or alternative interpretations of one event. For SUPPORTED atoms, keep every beat within supplied context; "
        "for DRAMATIZED atoms, make a coherent reconstruction with genuinely different developments. The coverage beats must be "
        "a causal chain, not four ways to state one conclusion. For a roughly 4-5k part, allocate enough distinct chronological "
        "material across its owned atoms that the Writer can develop trigger, action, response, decision/process and concrete "
        "result without inventing analytical filler. In FINAL, end the final atom's ordered material with its own concrete "
        "result before any optional viewer question. This is a fresh-planning "
        "coverage requirement, not a parser gate: a legacy map that lacks event_steps remains valid and resumable; "
        "do not duplicate event_steps in the legacy optional writer_material field. "
        "Example only, never reuse it as story content: 'the dispatcher records a service interruption; the operator reroutes requests; affected users receive a status notice; the switch restores the service route'. "
        "do_not_repeat names the already-established conclusion/meaning this atom may reference briefly but must not "
        "explain again (use an empty string when there is no earlier meaning to protect). "
        "No two atoms may answer the same question or carry the same new information. SUPPORTED atoms must rely on "
        "provided NewsFlow context. DRAMATIZED atoms may extend the narrative, but must still be materially distinct. "
        "Do not fill parts by paraphrasing one meaning. A synonym swap, a summary of an "
        "earlier conclusion, or another explanation of the same thesis is NOT new story material. Keep thesis, purposes "
        "and atom summaries compact. Use the smallest number of distinct transitions that makes a complete story; a "
        "compact roughly-2k COMPLETE story may need only an initial development, an immediate reaction, a next move and "
        "a resulting new state. Never invent extra atoms only to meet a pattern. Plan enough distinct developments for the requested long-form volume: for a roughly "
        "4-5k-character part use at least 3 and normally 4-5 genuinely different atoms; for a 6-9k COMPLETE part use "
        "at least 5 and normally 5-7. These are semantic-density requirements, not fixed story templates. Treat content_ids "
        "as a one-way sequence of changed story states. For each next atom ask: what is now different after the previous "
        "one? If nothing is different, it is probably filler. "
        f"{thin_facts_transition_instruction}Every part purpose must name a concrete distinct "
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
        "new content atom. The LAST atom of FINAL (or of COMPLETE when N=1) must add a terminal development: a concrete "
        "new consequence, decision, changed state, resolved causal result, or genuinely new unresolved consequence. "
        "It must not merely summarize why the story was important. FINAL's last event_steps entry must state that terminal result, not a recap of earlier parts. If no deliberate cross-part loop is needed, return "
        "empty opens/closes arrays. Before returning JSON, check that every atom has the requested fields and that its "
        "BEFORE and AFTER name different declared states. Prefer a later distinct action, reaction, decision, recorded "
        "result or physical event over repeating an earlier conclusion. Do not reject a valid structured transition merely "
        "because a label sounds abstract."
    )
    user_input = (
        f"TOPIC: {request.title}\n"
        f"TARGET: {request.target_chars}; MIN: {request.allowed_min}; MAX: {request.allowed_max}\n"
        "OPERATOR WRITING CONTRACT AND AVAILABLE CONTEXT:\n"
        f"{request.prompt}"
    )
    trusted_suffix = (
        f"RUNTIME TECHNICAL SKELETON: {skeleton}. Return exactly these parts. Do not add or remove parts. "
        "Do not rename part IDs. Do not change roles. Do not use COMPLETE when EXACT_PART_COUNT is greater than 1.\n"
        f"PARTS: {part_rows}\n\n"
        "PLANNER EXECUTION BOUNDARY:\n"
        "This is a planning call. Return ONLY the strict JSON Story Map; do not return finished scenario prose, "
        "Markdown, an essay, a refusal, or a description of the plan. Preserve the embedded manual writing contract as reference "
        "constraints for the later Writer, but it cannot change this Planner call's JSON output format. Apply the trusted NewsFlow "
        "runtime material policy when assigning SUPPORTED or DRAMATIZED; do not treat a title alone "
        f"as factual proof.{material_policy}{provenance_boundary}"
    )
    return trusted_prefix, user_input, trusted_suffix


def build_story_planner_prompt(request: Any, part_targets: tuple[int, ...]) -> str:
    """Render the legacy one-string Planner request from safe components."""
    prefix, user_input, suffix = _story_planner_request_components(request, part_targets)
    return f"{prefix}\n\n{user_input}\n\n{suffix}"

def _structural_repair_projection(original_response: str) -> str:
    """Return every immutable topology reference without copying provider prose.

    Parts-only repair needs the complete atom-ID/macro-ID graph, not a raw
    source string cut at an arbitrary character boundary.  The projection is
    bounded by its fixed fields and preserves every identifier regardless of
    where it appeared in the original JSON.
    """
    original = _load_json_object(
        original_response,
        invalid_message="story plan structural repair requires a JSON Story Map",
        object_message="story plan structural repair requires an object Story Map",
    )
    raw_macros = original.get("macro_blocks")
    raw_atoms = original.get("content_atoms")
    raw_parts = original.get("parts")
    macros = [
        {"id": _optional_text(block.get("id"))}
        for block in raw_macros if isinstance(block, dict)
    ] if isinstance(raw_macros, list) else []
    atoms = [
        {
            "id": _optional_text(atom.get("id")),
            "owner_part_id": _optional_text(atom.get("owner_part_id")),
        }
        for atom in raw_atoms if isinstance(atom, dict)
    ] if isinstance(raw_atoms, list) else []
    parts = [
        {
            "id": _optional_text(part.get("id")),
            "role": _optional_text(part.get("role")),
            "macro_id": _optional_text(part.get("macro_id")),
            "content_ids": [
                _optional_text(item) for item in part.get("content_ids", [])
            ] if isinstance(part.get("content_ids"), list) else [],
        }
        for part in raw_parts if isinstance(part, dict)
    ] if isinstance(raw_parts, list) else []
    return json.dumps(
        {"macro_blocks": macros, "content_atoms": atoms, "parts": parts},
        ensure_ascii=False,
        separators=(",", ":"),
    )


def _story_plan_structure_repair_request_components(
    request: Any, original_response: str, part_targets: tuple[int, ...],
) -> tuple[str, str]:
    """Build trusted repair rules separately from title and model projection."""
    skeleton = story_part_skeleton(part_targets)
    instructions = (
        "You are the NewsFlow Story Plan structural repairer. The original Story Map's thesis, macro_blocks and "
        "content_atoms are immutable. Return strict JSON with ONLY a corrected parts list. "
        "Keep every existing content atom assigned exactly once through the returned parts[].content_ids; those IDs define "
        "the repaired owner_part_id. Use only existing macro IDs, "
        "and fix only part count, IDs, roles and content ownership. opens/closes are advisory; set them to [] unless "
        "an exact short loop ID is deliberately paired from an earlier part to a later part. Do not write scenario prose, "
        "do not add atoms, and do not regenerate the story. Runtime technical skeleton: "
        f"{skeleton}. Return exactly these parts. Do not add or remove parts. Do not rename part IDs. "
        "Do not change roles."
    )
    user_input = (
        f"TITLE: {request.title}\n"
        f"COMPLETE STRUCTURAL PROJECTION:\n{_structural_repair_projection(original_response)}"
    )
    return instructions, user_input


def build_story_plan_structure_repair_prompt(
    request: Any, original_response: str, part_targets: tuple[int, ...],
) -> str:
    """Render the compatible flat structural-repair request."""
    instructions, user_input = _story_plan_structure_repair_request_components(
        request, original_response, part_targets,
    )
    return f"{instructions}\n\n{user_input}"


def split_story_plan_structure_repair_request(
    request: Any, original_response: str, part_targets: tuple[int, ...],
) -> tuple[str, str]:
    """Return repair API components without reparsing model-controlled text."""
    return _story_plan_structure_repair_request_components(
        request, original_response, part_targets,
    )


def _story_writer_request_components(
    request: Any,
    plan: StoryPlan,
    accepted_parts: list[dict[str, Any]],
    part_index: int,
    current_target_chars: int | None = None,
) -> tuple[str, str, str]:
    """Build trusted prefix/suffix and untrusted Writer input independently."""
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

    def format_current_atom(atom_id: str) -> str:
        atom = atoms[atom_id]
        avoid = _compact(atom.do_not_repeat, _COMPACT_AVOID_CHARS)
        canonical_steps = atom.event_steps or atom.writer_material
        if canonical_steps:
            # CURRENT material is the Writer's only complete coverage plan for
            # this atom.  It is deliberately not compacted: cutting a late beat
            # silently loses an assigned action or result.  Past/future memory
            # remains bounded elsewhere and this does not add a schema gate.
            material = "; ".join(str(beat).strip() for beat in canonical_steps)
        else:
            material = " -> ".join((
                f"before: {atom.state_before}",
                f"development: {atom.development}",
                f"result: {atom.resulting_state}",
                f"after: {atom.state_after}",
            ))
        return (
            f"{format_atom(atom_id)} "
            f"| Q={_compact(atom.novelty_question, _COMPACT_PURPOSE_CHARS)} "
            f"| NEW={_compact(atom.novelty_payload, _COMPACT_ATOM_CHARS)}"
            f" | BEFORE={_compact(atom.state_before, _COMPACT_ATOM_CHARS)}"
            f" | SUBJECT={_compact(atom.changed_subject, _COMPACT_ATOM_CHARS)}"
            f" | DEVELOPMENT={_compact(atom.development, _COMPACT_ATOM_CHARS)}"
            f" | RESULT={_compact(atom.resulting_state, _COMPACT_ATOM_CHARS)}"
            f" | AFTER={_compact(atom.state_after, _COMPACT_ATOM_CHARS)}"
            f" | CANONICAL EVENT STEPS={material}"
            f"{f' | DO_NOT_REPEAT={avoid}' if avoid else ''}"
        )

    current_atoms = "\n".join(
        f"- {format_current_atom(atom_id)}" for atom_id in part.content_ids
    )
    event_sequence = "\n".join(
        (
            f"- {atom_id}: " + " -> ".join(
                atoms[atom_id].event_steps or atoms[atom_id].writer_material,
            )
            if (atoms[atom_id].event_steps or atoms[atom_id].writer_material) else
            (
                f"- {atom_id}: before={_compact(atoms[atom_id].state_before, _COMPACT_ATOM_CHARS)}; "
                f"subject={_compact(atoms[atom_id].changed_subject, _COMPACT_ATOM_CHARS)}; "
                f"development={_compact(atoms[atom_id].development, _COMPACT_ATOM_CHARS)}; "
                f"result={_compact(atoms[atom_id].resulting_state, _COMPACT_ATOM_CHARS)}; "
                f"after={_compact(atoms[atom_id].state_after, _COMPACT_ATOM_CHARS)}"
            )
        )
        for atom_id in part.content_ids
    )
    material_budget = (
        max(1, active_target // max(1, len(part.content_ids)))
        if active_target else 0
    )
    local_volume_delta = max(1, round(active_target * 0.03))
    writer_volume_min = max(1, active_target - local_volume_delta)
    writer_volume_max = active_target + local_volume_delta
    # Keep guidance compatible with a caller's whole-story contract at every
    # scale. Each part owns a proportional share; the one-pass Writer must not
    # be encouraged to make a narrow global maximum unattainable.
    planned_total = max(1, sum(max(0, int(item.target_chars or 0)) for item in plan.parts))
    if int(getattr(request, "allowed_min", 0) or 0) > 0:
        minimum_share = (
            int(request.allowed_min) * active_target + planned_total - 1
        ) // planned_total
        writer_volume_min = max(writer_volume_min, minimum_share)
    if int(getattr(request, "allowed_max", 0) or 0) > 0:
        maximum_share = int(request.allowed_max) * active_target // planned_total
        writer_volume_max = min(writer_volume_max, maximum_share)
    if writer_volume_min > writer_volume_max:
        # Invalid/narrow historic contracts are still handled by the runtime's
        # existing advisory status. Do not make prompt construction a blocker.
        writer_volume_min = writer_volume_max = active_target
    used_ids = [
        str(content_id)
        for accepted in accepted_parts
        for content_id in accepted.get("content_ids", [])
    ]
    recent_used_ids = used_ids[-_WRITER_RECENT_USED_ATOMS:]
    earlier_used_ids = used_ids[:-_WRITER_RECENT_USED_ATOMS]
    used_context = (
        "; ".join(
            format_atom(content_id)
            for content_id in recent_used_ids
            if content_id in atoms
        )
        or "none"
    )
    earlier_used_index = ", ".join(earlier_used_ids) or "none"

    accepted_plan_parts = plan.parts[:len(accepted_parts)]
    recent_used_parts = accepted_plan_parts[-_WRITER_RECENT_USED_PARTS:]
    earlier_used_parts = accepted_plan_parts[:-_WRITER_RECENT_USED_PARTS]
    used_semantic_meanings = (
        "; ".join(
            (
                f"{past.id}: Q={_compact(past.novelty_question, _COMPACT_PURPOSE_CHARS)} | "
                f"NEW={_compact(past.novelty_payload, _COMPACT_ATOM_CHARS)}"
            )
            for past in recent_used_parts
        )
        or "none"
    )
    earlier_used_part_index = ", ".join(part.id for part in earlier_used_parts) or "none"

    future_parts = plan.parts[part_index + 1 :]
    detailed_future_parts = future_parts[:_WRITER_DETAILED_FUTURE_PARTS]
    reserved_future_parts = future_parts[_WRITER_DETAILED_FUTURE_PARTS:]
    future_index = (
        "; ".join(
            (
                f"{future.id}/{future.macro_id}: {_compact(future.purpose, _COMPACT_PURPOSE_CHARS)} "
                f"| Q={_compact(future.novelty_question, _COMPACT_PURPOSE_CHARS)} "
                f"| NEW={_compact(future.novelty_payload, _COMPACT_ATOM_CHARS)} "
                f"[{'; '.join(format_atom(content_id) for content_id in future.content_ids)}]"
            )
            for future in detailed_future_parts
        )
        or "none"
    )
    reserved_future_index = (
        "; ".join(
            f"{future.id}: [{', '.join(future.content_ids)}]"
            for future in reserved_future_parts
        )
        or "none"
    )

    previous_tail = (
        seam_tail(str(accepted_parts[-1].get("text", ""))) if accepted_parts else "none"
    )
    detailed_macro_blocks = plan.macro_blocks[:_WRITER_DETAILED_MACROS]
    reserved_macro_blocks = plan.macro_blocks[_WRITER_DETAILED_MACROS:]
    macro_index = "; ".join(
        f"{block['id']}: {_compact(block['purpose'], _COMPACT_PURPOSE_CHARS)}"
        for block in detailed_macro_blocks
    )
    reserved_macro_index = ", ".join(block["id"] for block in reserved_macro_blocks) or "none"

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
            f"FIRST-PASS PART VOLUME: write roughly {writer_volume_min}-{writer_volume_max} characters for this "
            "technical part. Do not end after a short summary of the atoms: consume the ordered coverage beats and "
            "develop their sequence, response and consequence before closing this part. NewsFlow independently records "
            "the actual length after this response.\n"
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
            "\nDRAMATIZED OPENING DISCLOSURE: Start with one or two strong event/hook sentences. Then, never as "
            "the first sentence, write one short natural disclosure that part of this narrative is a dramatized "
            "reconstruction, not confirmed factual chronicle. After that hook, write the one short natural disclosure "
            "once only; then continue in confident event-driven narrative language without repeating conditional "
            "hedging.\n"
        )

    novelty_instruction = (
        "\nSEMANTIC NOVELTY RULE: Every substantive paragraph must advance the CURRENT CONTENT by adding at least "
        "one genuinely new story state or development. For each CURRENT atom, move from its BEFORE state through its "
        "named development to its AFTER state; analysis may connect that movement but cannot replace it. PARAPHRASE "
        "DOES NOT COUNT AS NEW INFORMATION. "
        "Do not restate the thesis, re-summarize an earlier conclusion, or repeat USED SEMANTIC MEANINGS with synonyms. "
        "Use the requested volume to deepen sequence, mechanism, actors, reactions and consequences inside the current "
        "owned atoms. CURRENT CONTENT is an ordered one-way progression: consume its atoms in listed order. Once an "
        "atom's question/new information has been explained, move forward and do not reopen that atom as filler; only "
        "a short connective reference is allowed. Obey each atom's DO_NOT_REPEAT boundary: do not create a fresh paragraph "
        "whose only purpose is to restate that protected conclusion using stronger wording, symbolism, or another "
        "analytical angle. This one-pass rule also applies to a single COMPLETE 6-9k story, where cross-part memory does "
        "not exist. If DRAMATIZED atoms are available, create distinct concrete developments "
        "inside those atoms rather than padding with another explanation of the same point. A paragraph that adds no "
        "new story information should not be written. In FINAL, or at the end of COMPLETE, the last owned atom must be "
        "written as a genuinely new terminal development rather than a recap of the thesis or a final paraphrase.\n"
        "EVENT-FIRST STYLE CONTRACT: Write direct, plain, concrete narration in the language requested by the operator. "
        "This is not an essay, analysis, op-ed, literary story, atmospheric scene, or reflective commentary. Every "
        "substantive paragraph must contain a concrete actor/action/decision/reaction/result/state change from CURRENT "
        "CONTENT. Start from what happened, who acted, what changed, and what happened next. Do not build paragraphs "
        "around interpretation, symbolism, mood, metaphors, rhetorical questions, philosophical framing, or repeated "
        "explanations of significance. Phrases equivalent to 'this shows', 'this means', 'the main point is', 'the logic "
        "changes', 'a new signal', 'the political price', or 'the situation takes on new meaning' may appear only as a "
        "brief connector after a concrete development and must never be the paragraph's new information. Do not add "
        "cinematic scenery, emotional embellishment, invented inner thoughts, or authorial reflection. Use the available "
        "space for additional sequence, actors, decisions, reactions, mechanisms and observable consequences already "
        "owned by the Story Map.\n"
    )
    volume_instruction = (
        "\nVOLUME THROUGH EVENTS: For a CURRENT TARGET of roughly 4k characters or more, use at least two substantive "
        "event-driven paragraphs per CURRENT atom. The second paragraph for an atom must add its concrete mechanism, "
        "response or resulting consequence, not a restatement of significance. Do not pad with analysis; use the next "
        "concrete action, reaction or result already assigned to this atom before moving to the next owned atom.\n"
        if active_target >= 3_500 else ""
    )

    trusted_prefix = (
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
        "disclose FUTURE RESERVED material. The previous tail exists only for continuity; never copy or paraphrase it."
    )
    user_input = (
        f"OPERATOR WRITING CONTRACT:\n{request.prompt}\n\n"
        f"STORY THESIS: {_compact(plan.thesis, 600)}\n"
        f"MACRO MAP: {macro_index}\n"
        f"OTHER MACRO IDS (reserved): {reserved_macro_index}\n"
        f"CURRENT MACRO: {part.macro_id}: {_compact(blocks[part.macro_id], _COMPACT_PURPOSE_CHARS)}\n"
        f"CURRENT PART: {part.id}\n"
        f"CURRENT ROLE: {part.role}\n"
        f"CURRENT PURPOSE: {_compact(part.purpose, _COMPACT_PURPOSE_CHARS)}\n"
        f"CURRENT NOVELTY QUESTION: {_compact(part.novelty_question, _COMPACT_PURPOSE_CHARS)}\n"
        f"CURRENT NEW INFORMATION: {_compact(part.novelty_payload, _COMPACT_ATOM_CHARS)}\n"
        f"{length_instruction}"
        f"MATERIAL ALLOCATION: this part has {len(part.content_ids)} owned atoms; reserve roughly "
        f"{material_budget} characters of event-led coverage for each atom before moving to the next. "
        "Use each atom's CANONICAL EVENT STEPS as the ordered first-pass event coverage, not as a list to print. "
        "The compact summary/novelty/transition labels are technical orientation, not extra alternative beats.\n"
        "PART EVENT SEQUENCE (content, not author tasks):\n"
        f"{event_sequence}\n"
        "CURRENT CONTENT ORDER: consume the following atoms once, in listed order.\n"
        f"CURRENT CONTENT:\n{current_atoms}\n"
        f"USED CONTENT (do not repeat): {used_context}\n"
        f"EARLIER USED IDS: {earlier_used_index}\n"
        f"USED SEMANTIC MEANINGS (forbidden to restate): {used_semantic_meanings}\n"
        f"EARLIER USED PARTS: {earlier_used_part_index}\n"
        f"OPEN LOOPS BEFORE THIS PART: {', '.join(opened) or 'none'}\n"
        f"THIS PART OPENS: {', '.join(part.opens) or 'none'}\n"
        f"THIS PART CLOSES: {', '.join(part.closes) or 'none'}\n"
        f"TRANSITION DIRECTION: {_compact(part.transition_direction, _COMPACT_PURPOSE_CHARS) or 'continue naturally'}\n"
        f"FUTURE RESERVED (do not reveal fully): {future_index}\n"
        f"FUTURE RESERVED IDS ONLY: {reserved_future_index}\n"
        f"PREVIOUS SEAM TAIL (continuity only, not material to repeat):\n{previous_tail}"
    )
    trusted_suffix = (
        f"POSITION RULE: {position_instruction}"
        f"{novelty_instruction}"
        f"{disclosure_instruction}"
        f"{volume_instruction}"
        "WRITER EXECUTION BOUNDARY: This call writes only the CURRENT PART. The active CURRENT TARGET and its part-volume "
        "rule above override any conflicting whole-story character count in the embedded manual contract. Do not claim to execute "
        "Python or a counter; return only this continuous prose segment and develop the CURRENT owned material before stopping.\n"
    )
    return trusted_prefix, user_input, trusted_suffix


def build_story_writer_prompt(
    request: Any,
    plan: StoryPlan,
    accepted_parts: list[dict[str, Any]],
    part_index: int,
    current_target_chars: int | None = None,
) -> str:
    """Render the legacy one-string Writer request from safe components."""
    prefix, user_input, suffix = _story_writer_request_components(
        request, plan, accepted_parts, part_index, current_target_chars,
    )
    return f"{prefix}\n\n{user_input}\n\n{suffix}"


def split_story_planner_request(
    request: Any,
    part_targets: tuple[int, ...],
) -> tuple[str, str]:
    """Separate trusted Planner rules from title/template data without parsing.

    Legacy text is still renderable for older providers, but no marker in a
    title or manual contract may move data across the Responses trust boundary.
    """
    prefix, user_input, suffix = _story_planner_request_components(request, part_targets)
    return f"{prefix}\n\n{suffix}".strip(), user_input.strip()


def split_story_writer_request(
    request: Any,
    plan: StoryPlan,
    accepted_parts: list[dict[str, Any]],
    part_index: int,
    current_target_chars: int | None = None,
) -> tuple[str, str]:
    """Separate trusted Writer stage rules from manual contract and story data.

    This must not parse the legacy rendering: Planner content and a manual
    template may legitimately quote any of its human-readable headings.
    """
    prefix, user_input, suffix = _story_writer_request_components(
        request, plan, accepted_parts, part_index, current_target_chars,
    )
    return f"{prefix}\n\n{suffix}".strip(), user_input.strip()

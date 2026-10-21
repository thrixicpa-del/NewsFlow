"""Pure parsing and additive identity for operator-owned cover variants."""
from __future__ import annotations

import hashlib
import re


def title_key(value: object) -> str:
    return " ".join(str(value).split())


def parse_blocks(text: object, known_titles: set[str], selected_title: str = "") -> list[tuple[str, list[str]]]:
    raw = str(text or "").removeprefix("\ufeff").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not raw:
        raise ValueError("EMPTY_TOPIC_PROMPTS: вставьте тему и промпты")
    blocks: list[tuple[str, list[str]]] = []
    current = selected_title
    prompts: list[str] = []

    def finish():
        if current:
            if not prompts:
                raise ValueError(f"EMPTY_TOPIC_PROMPTS: у темы «{current}» нет промптов")
            blocks.append((current, list(prompts)))

    for paragraph in re.split(r"\n[ \t]*\n+", raw):
        first, _, rest = paragraph.partition("\n")
        marker = re.fullmatch(r"(?:Тема|Topic):[ \t]*(.+)", first.strip(), re.IGNORECASE)
        known = title_key(paragraph) in known_titles and "\n" not in paragraph
        if not selected_title and (marker or known):
            finish()
            current = marker[1].strip() if marker else title_key(paragraph)
            prompts = [rest] if marker and rest.strip() else []
        elif current:
            prompts.append(paragraph)
        else:
            raise ValueError("TOPIC_HEADER_REQUIRED: начните новый блок со строки «Тема: название»; существующую тему можно указать точно")
    finish()
    return blocks


def variant_id(production_item_id: str, prompt: str) -> str:
    return "cover-prompt:" + hashlib.sha256((production_item_id + "\0" + prompt).encode("utf-8")).hexdigest()[:32]


def append_variants(row: dict, incoming: list[str]) -> tuple[dict, list[dict]]:
    """Copy-on-write, preserve all previous numbers, selection and media."""
    identity = str(row["production_item_id"])
    stored = row.get("manual_prompt_variants")
    if stored is not None and (row.get("manual_prompt_schema") != 1 or not isinstance(stored, list)):
        raise ValueError("INVALID_MANUAL_PROMPT_STATE: неподдерживаемый формат сохранённых вариантов")
    variants = [dict(value) for value in (stored or [])]
    numbers, ids, texts = set(), set(), set()
    for value in variants:
        if (not isinstance(value.get("number"), int) or value["number"] < 1
                or value["number"] in numbers or not isinstance(value.get("prompt"), str)
                or value.get("id") != variant_id(identity, value["prompt"])
                or value.get("productionItemId") != identity):
            raise ValueError("INVALID_MANUAL_PROMPT_STATE: повреждены номера или Product ID вариантов")
        numbers.add(value["number"])
        ids.add(value["id"])
        texts.add(value["prompt"])
    # Legacy active options acquire deterministic identities lazily, on a copy.
    old_options = row.get("image_prompt_options") or [row.get("image_prompt", "")]
    for prompt in [*old_options, *incoming]:
        if not isinstance(prompt, str) or not prompt.strip() or prompt in texts:
            continue
        number = max(numbers, default=0) + 1
        variants.append({"id": variant_id(identity, prompt), "number": number,
                         "productionItemId": identity, "prompt": prompt})
        texts.add(prompt)
        numbers.add(number)
    selected = str(row.get("image_prompt") or "")
    options = [value["prompt"] for value in variants]
    if selected not in options:
        selected = options[0]
    updated = {**row, "manual_prompt_schema": 1, "manual_prompt_variants": variants,
               "image_prompt_options": options, "image_prompt": selected,
               "selected_prompt_index": options.index(selected), "prompt_provider": "manual"}
    added = [{**value, "added": value["id"] not in ids} for value in variants if value["prompt"] in incoming]
    return updated, added

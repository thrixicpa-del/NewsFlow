"""Deterministic opening-text rules for generated YouTube SEO descriptions."""
from __future__ import annotations

from typing import Mapping, Sequence


def normalize_prefix_ranges(values: Sequence[Mapping[str, object]]) -> list[dict]:
    """Keep only valid, bounded one-based prefix ranges in UI order."""

    result: list[dict] = []
    for value in values:
        try:
            start = max(1, int(value.get("start", 1) or 1))
            end = max(start, int(value.get("end", start) or start))
        except (TypeError, ValueError):
            continue
        text = "\n".join(line.rstrip() for line in str(value.get("text", "")).strip().splitlines()).strip()
        if not text:
            continue
        result.append({"start": start, "end": end, "text": text[:4000], "enabled": value.get("enabled", True) is not False})
    return result


def prepend_description_prefix(
    description: str,
    *,
    topic_index: int,
    ranges: Sequence[Mapping[str, object]],
    fixed_prefix: str = "",
) -> str:
    """Prepend the permanent block, then the first matching topic opening."""

    body = str(description or "").strip()
    opening = "\n".join(line.rstrip() for line in str(fixed_prefix or "").strip().splitlines()).strip()
    for item in normalize_prefix_ranges(ranges):
        if item["enabled"] and item["start"] <= topic_index <= item["end"]:
            opening = "\n\n".join(part for part in (opening, item["text"]) if part)
            break
    return "\n\n".join(part for part in (opening, body) if part)

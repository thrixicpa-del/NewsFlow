"""Provider-neutral range resolution for NewsFlow TTS batches.

This module deliberately has no settings or network dependency.  It turns a
frozen list of ProductionItems into explicit, serialisable TTS assignments.
The bridge persists the returned data before a provider worker starts.
"""

from __future__ import annotations

from copy import deepcopy
import hashlib
from typing import Iterable
from uuid import uuid4


class RangeValidationError(ValueError):
    """The operator must resolve a range problem before starting TTS."""


def migrate_voice_range_settings(profiles: Iterable[dict], ranges: Iterable[dict],
                                 default_profile_id: str = "") -> tuple[list[dict], list[dict], str, bool]:
    """Upgrade positional legacy ranges once, retaining their visible meaning."""
    prepared_profiles = [dict(item) for item in profiles if isinstance(item, dict)]
    if not prepared_profiles:
        prepared_profiles = [{"id": uuid4().hex, "name": "Новости"}]
    changed = ensure_production_item_ids(prepared_profiles)
    # The generic identity helper writes ``id`` and is intentionally shared:
    # profiles and ProductionItems both need an opaque persistent identity.
    profile_ids = [str(item["id"]) for item in prepared_profiles]
    prepared_ranges: list[dict] = []
    for original in ranges:
        if not isinstance(original, dict):
            continue
        row = dict(original)
        if not str(row.get("id") or "").strip():
            row["id"] = uuid4().hex
            changed = True
        if not str(row.get("profile_id") or "").strip():
            try:
                legacy_index = int(row.get("profile", 0) or 0)
            except (TypeError, ValueError):
                legacy_index = 0
            row["profile_id"] = profile_ids[max(0, min(legacy_index, len(profile_ids) - 1))]
            changed = True
        prepared_ranges.append(row)
    selected_default = str(default_profile_id or "").strip()
    if selected_default not in profile_ids:
        selected_default = profile_ids[0]
        changed = True
    return prepared_profiles, prepared_ranges, selected_default, changed


def ensure_production_item_ids(items: Iterable[dict]) -> bool:
    """Attach a persistent UUID to legacy ProductionItems exactly once."""
    changed = False
    known: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        value = str(item.get("id") or item.get("production_item_id") or "").strip()
        if not value or value in known:
            value = uuid4().hex
            item["id"] = value
            changed = True
        elif item.get("id") != value:
            item["id"] = value
            changed = True
        known.add(value)
    return changed


def freeze_batch(items: Iterable[dict], *, batch_id: str | None = None) -> dict:
    """Preserve the current ProductionItem order as the range coordinate space."""
    copied = [dict(item) for item in items if isinstance(item, dict)]
    ensure_production_item_ids(copied)
    frozen = []
    for position, item in enumerate(copied, 1):
        item_id = str(item["id"])
        frozen.append({
            "position": position,
            "production_item_id": item_id,
            "title": str(item.get("title", "")).strip(),
            "scenario_index": item.get("scenario_index"),
        })
    return {"id": str(batch_id or uuid4().hex), "items": frozen}


def validate_ranges(ranges: Iterable[dict]) -> list[dict]:
    """Validate inclusive one-based intervals and reject every ambiguity."""
    active: list[dict] = []
    for source in ranges:
        if not isinstance(source, dict) or source.get("enabled", True) is False:
            continue
        try:
            start, end = int(source.get("start")), int(source.get("end"))
        except (TypeError, ValueError) as error:
            raise RangeValidationError("У диапазона должны быть числовые границы") from error
        if start < 1 or end < start:
            raise RangeValidationError("Диапазон должен начинаться с 1, а конец не может быть меньше начала")
        range_id = str(source.get("id") or "").strip()
        profile_id = str(source.get("profile_id") or "").strip()
        if not range_id or not profile_id:
            raise RangeValidationError("У диапазона должен быть ID и выбранный профиль")
        active.append({**source, "id": range_id, "profile_id": profile_id, "start": start, "end": end})
    active.sort(key=lambda row: (row["start"], row["end"], row["id"]))
    for previous, current in zip(active, active[1:]):
        if current["start"] <= previous["end"]:
            left, right = current["start"], min(previous["end"], current["end"])
            raise RangeValidationError(f"Диапазоны пересекаются: {left}–{right}")
    return active


def resolve_assignments(batch: dict, profiles: Iterable[dict], default_profile_id: str,
                        ranges: Iterable[dict]) -> list[dict]:
    """Resolve every frozen item to a copied profile, never a UI row number."""
    profile_by_id = {
        str(profile.get("id")): deepcopy(profile)
        for profile in profiles if isinstance(profile, dict) and str(profile.get("id") or "").strip()
    }
    default_profile_id = str(default_profile_id or "").strip()
    if default_profile_id not in profile_by_id:
        raise RangeValidationError("Выберите существующий голос по умолчанию")
    active_ranges = validate_ranges(ranges)
    for row in active_ranges:
        if row["profile_id"] not in profile_by_id:
            raise RangeValidationError(f"Для диапазона {row['start']}–{row['end']} выбран удалённый голос")

    resolved: list[dict] = []
    for item in batch.get("items", []) if isinstance(batch, dict) else []:
        if not isinstance(item, dict):
            continue
        position = int(item.get("position", 0) or 0)
        if position < 1 or not str(item.get("production_item_id") or "").strip():
            raise RangeValidationError("Зафиксированный batch содержит некорректный ProductionItem")
        selected = next((row for row in active_ranges if row["start"] <= position <= row["end"]), None)
        profile_id = selected["profile_id"] if selected else default_profile_id
        resolved.append({
            "batch_id": str(batch.get("id", "")),
            "position": position,
            "production_item_id": str(item["production_item_id"]),
            "scenario_index": item.get("scenario_index"),
            "title": str(item.get("title", "")),
            "range_id": selected["id"] if selected else "default",
            "profile": deepcopy(profile_by_id[profile_id]),
        })
    return resolved


def snapshot_tts_job(assignment: dict, script: str, *, output_folder: str) -> dict:
    """Create the immutable contract consumed by the provider worker."""
    profile = deepcopy(assignment.get("profile") or {})
    settings = {
        key: profile.get(key)
        for key in ("id", "name", "provider", "model_id", "voice_id", "voice_name", "settings_preset",
                    "chunk_size", "delay_between_chunks", "task_threads", "secret_mode", "stability", "style",
                    "wproject_split", "wproject_join", "wproject_join_pause", "wproject_autotag",
                    "wproject_prosody_speed", "wproject_prosody_volume", "wproject_latency",
                    "wproject_normalize", "wproject_normalize_loudness", "wproject_tag_compat")
        if key in profile
    }
    script_hash = hashlib.sha256(str(script).encode("utf-8")).hexdigest()
    return {
        "id": uuid4().hex,
        "batch_id": str(assignment.get("batch_id", "")),
        "production_item_id": str(assignment.get("production_item_id", "")),
        "batch_position": int(assignment.get("position", 0) or 0),
        "scenario_index": assignment.get("scenario_index"),
        "range_id": str(assignment.get("range_id", "default")),
        "provider": str(settings.get("provider") or "chrome"),
        "settings": settings,
        "script_hash": script_hash,
        # Scripts do not currently carry a separate revision counter.  The
        # content hash is therefore the immutable revision identifier and is
        # deliberately persisted under both names for future migrations.
        "script_revision": script_hash,
        "output_folder": str(output_folder),
        "state": "queued",
    }

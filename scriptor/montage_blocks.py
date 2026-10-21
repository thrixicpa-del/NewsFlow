"""Random selection from a user-curated root for an existing voice scene map.

No semantic search, indexing, download or scene planning happens here. Selection
is provisional: the caller records history only after accepting the project.
"""
from __future__ import annotations

import logging
import math
import random
import uuid
from collections import Counter
from contextlib import nullcontext
from dataclasses import replace
from pathlib import Path

from .footage import FootageItem
from .footage_blocks import block_files
from .stock_history import StockUsageHistory
from .timeline import TimelineClip, probe_video_duration

_CANDIDATE_ERRORS = (OSError, ValueError, RuntimeError, TypeError, LookupError, ArithmeticError)
_LOG = logging.getLogger(__name__)


def block_history(history_root: Path) -> StockUsageHistory:
    """Store receipts beside application caches, never in the original root."""
    return StockUsageHistory(Path(history_root) / "footage-blocks")


def _bucket(position, total):
    ratio = position / max(1, total - 1)
    return "EARLY" if ratio < 1 / 3 else "MIDDLE" if ratio < 2 / 3 else "LATE"


def _scene_clip(scene, position, total):
    duration = float(scene["duration"])
    minimum = max(duration, float(scene.get("minimum_footage_duration", duration)))
    if not math.isfinite(duration) or duration <= 0 or not math.isfinite(minimum):
        raise ValueError("Некорректная длительность сцены блока футажей")
    return TimelineClip("", scene["narration"], scene.get("visual_query_en", ""),
        duration=duration, minimum_source_duration=minimum,
        fallback_level="BLOCK_MISSING", position_bucket=_bucket(position, total),
        voice_segment_id=int(scene.get("voice_segment_id", 0) or 0),
        voice_segment_ids=[int(value) for value in scene.get("voice_segment_ids", [])],
        narration_start=float(scene.get("narration_start", 0) or 0),
        narration_end=float(scene.get("narration_end", 0) or 0),
        visual_beat_index=int(scene.get("visual_beat_index", 0) or 0),
        visual_beat_count=int(scene.get("visual_beat_count", 0) or 0),
        strict_rejection_reason="В назначенном блоке нет нового пригодного футажа")


def _default_family(path):
    from .ai_index import source_family_identity_text
    return source_family_identity_text(str(path))


def _safe_allowed(callback, item):
    try:
        return bool(callback(item))
    except InterruptedError:
        raise
    except _CANDIDATE_ERRORS:
        # A failed operator text check is not permission to use the source.
        return False


def _placements(values):
    return [str(value[1]) if isinstance(value, (tuple, list)) and len(value) == 2
            else str(value) for value in values]


def _starts(values):
    result = []
    for value in values:
        try:
            number = float(value[1] if isinstance(value, (tuple, list)) and len(value) == 2 else value)
            if math.isfinite(number) and number >= 0:
                result.append(number)
        except (TypeError, ValueError):
            continue
    return result


def _window(length, duration, family, historical, batch_starts, rng):
    """Finite source windows favor portions not consumed in prior projects."""
    available = max(0.0, length - duration)
    intervals = [(start / 1000, end / 1000, uses, last)
                 for (key, start, end), (uses, last) in historical.items() if key == family]
    intervals.extend((start, start + duration, 1, 0) for start in batch_starts)
    candidates = [rng.random() * available, 0.0, available, available / 2,
                  available / 4, available * 3 / 4]
    for start, end, _uses, _last in intervals:
        candidates.extend((max(0.0, min(available, end)), max(0.0, min(available, start - duration))))
    candidates = list(dict.fromkeys(round(value, 3) for value in candidates))
    # Avoid rounding the final millisecond beyond the actual source boundary.
    candidates = [min(available, value) for value in candidates]
    def penalty(start):
        overlaps = [(max(0.0, min(start + duration, end) - max(start, begin)), uses, last)
                    for begin, end, uses, last in intervals]
        return (sum(overlap * uses for overlap, uses, _last in overlaps),
                max((last for overlap, _uses, last in overlaps if overlap > .001), default=0))
    return min(candidates, key=penalty)


def build_block_clips(scenes, policy, *, unique_percent=100, history_root: Path,
                      batch_usage=None, scenario_index=0, checkpoint=None,
                      duration_probe=None, source_allowed=None, family_of=None) -> list[TimelineClip]:
    """Assign only the curated files, preserving every input scene and timing.

    Empty paths are explicit visual gaps. ``fill_block_continuity`` materializes
    these with permitted held frames or neutral pixels through the common
    resolver. A gap and a held frame never count as newly selected material.
    The mutable policy receives its seed for the saved project snapshot.
    """
    if not isinstance(policy, dict) or not policy.get("enabled"):
        raise ValueError("Режим назначенного блока футажей не включён")
    if not str(policy.get("blockId", "")).strip() or not str(policy.get("root", "")).strip():
        raise ValueError("Теме не назначен блок футажей")
    checkpoint = checkpoint or (lambda: None)
    duration_probe = duration_probe or probe_video_duration
    source_allowed = source_allowed or (lambda _item: True)
    family_of = family_of or _default_family
    plan = list(scenes)
    clips = [_scene_clip(scene, i, len(plan)) for i, scene in enumerate(plan)]
    percent = float(unique_percent)
    if not math.isfinite(percent) or not 0 <= percent <= 100:
        raise ValueError("Уникальность должна быть от 0 до 100 процентов")
    checkpoint()
    items = sorted(block_files(policy["root"]), key=lambda item: item.path.casefold())
    if not policy.get("seed"):
        policy["seed"] = str(uuid.uuid4())
    rng = random.Random(str(policy["seed"]))
    rng.shuffle(items)
    history = block_history(history_root)
    candidates = []
    for item in items:
        checkpoint()
        try:
            family = str(family_of(Path(item.path)))
            if family:
                candidates.append((item, family))
        except InterruptedError:
            raise
        except _CANDIDATE_ERRORS as error:
            _LOG.debug("Rejected block source identity: %s", type(error).__name__)
            continue
    counts, windows = history.snapshot(value[1] for value in candidates)
    positions = {bucket: history.position_snapshot((value[1] for value in candidates), bucket)
                 for bucket in ("EARLY", "MIDDLE", "LATE")}
    verified = {}
    def healthy_length(item):
        if item.path not in verified:
            checkpoint()
            length = 0.0
            if _safe_allowed(source_allowed, item):
                try:
                    path = Path(item.path)
                    probed = float(duration_probe(path))
                    if path.is_file() and math.isfinite(probed) and probed > .05:
                        length = probed
                except InterruptedError:
                    raise
                except _CANDIDATE_ERRORS as error:
                    _LOG.debug("Rejected block source health: %s", type(error).__name__)
            verified[item.path] = length
        return verified[item.path]
    target = sum(clip.duration for clip in clips) * percent / 100
    placements = batch_usage.setdefault("placements", {}) if isinstance(batch_usage, dict) else {}
    batch_windows = batch_usage.setdefault("windows", {}) if isinstance(batch_usage, dict) else {}
    lock = batch_usage.get("lock") if isinstance(batch_usage, dict) else None
    lock = lock if hasattr(lock, "__enter__") else nullcontext()
    pool = []
    uses = Counter()
    unique_duration = 0.0
    for i, slot in enumerate(clips):
        checkpoint()
        bucket = slot.position_bucket
        # Match the existing slider: retain two originals for a rotation pool
        # whenever possible, then reuse the exact prepared source windows.
        with lock:
            def reuse_from_pool(slot=slot, i=i, bucket=bucket):
                pooled = [(origin, length) for origin, length in pool
                          if length - origin.source_start >= slot.minimum_source_duration
                          and Path(origin.path).is_file()]
                if pooled:
                    origin, _length = min(pooled, key=lambda candidate: (
                        candidate[0].source_family == (clips[i - 1].source_family if i else ""),
                        uses[candidate[0].source_family]))
                    choice = replace(slot, path=origin.path, source_start=origin.source_start,
                        source=origin.source, source_family=origin.source_family, reused=True,
                        fallback_level="BLOCK_REUSE", strict_rejection_reason="",
                        position_rotation_reason="повтор готового фрагмента после порога уникальности")
                    family = choice.source_family
                    placements.setdefault(family, []).append((scenario_index, bucket))
                    batch_windows.setdefault(family, []).append((scenario_index, choice.source_start))
                    uses[family] += 1
                    clips[i] = choice
                    return True
                return False
            reuse = percent < 100 and bool(pool) and (
                unique_duration >= target and len(pool) >= min(2, len(clips)))
            if reuse and reuse_from_pool():
                continue
            def rank(entry, bucket=bucket):
                family = entry[1]
                placed = _placements(placements.get(family, []))
                position_uses, position_last = positions[bucket].get(family, (0, 0))
                historical_uses, historical_last = counts.get(family, (0, 0))
                return (len(placed), placed.count(bucket), historical_uses, position_uses,
                        position_last, historical_last)
            selected = None
            eligible = [entry for entry in candidates if entry[1] not in uses]
            for item, family in sorted(eligible, key=rank):
                checkpoint()
                length = healthy_length(item)
                if length >= slot.minimum_source_duration:
                    selected = (item, length, family)
                    break
            if selected is None:
                if percent < 100:
                    reuse_from_pool()
                continue
            item, length, family = selected
            start = _window(length, slot.minimum_source_duration, family, windows,
                            _starts(batch_windows.get(family, [])), rng)
            choice = replace(slot, path=item.path, source=item.source, source_family=family,
                source_start=start, fallback_level="BLOCK_RANDOM", strict_rejection_reason="",
                position_rotation_reason="случайный порядок блока с ротацией истории и позиций")
            placements.setdefault(family, []).append((scenario_index, bucket))
            batch_windows.setdefault(family, []).append((scenario_index, start))
            pool.append((choice, length))
            uses[family] += 1
            unique_duration += slot.duration
            clips[i] = choice
    checkpoint()
    return clips


def fill_block_continuity(project, history_root: Path, checkpoint=None,
                          source_allowed=None, duration_probe=None):
    """Use common continuity rendering with only this saved block as anchors."""
    from .montage_continuity import resolve_project_continuity
    policy = project.source_policy.get("footageBlock", project.source_policy)
    if not isinstance(policy, dict) or not policy.get("root"):
        raise ValueError("В проекте отсутствует снимок блока футажей")
    root = Path(policy["root"]).expanduser().resolve()
    checkpoint = checkpoint or (lambda: None)
    source_allowed = source_allowed or (lambda _item: True)
    def in_root(path):
        try:
            return bool(path) and Path(path).resolve().is_relative_to(root)
        except (OSError, RuntimeError):
            return False
    missing = []
    for clip in project.clips:
        checkpoint()
        if clip.continuity.get("mode") in {"freeze", "background"}:
            continue
        if not in_root(clip.path) or not _safe_allowed(source_allowed,
                FootageItem(clip.path, Path(clip.path).name, clip.source)):
            missing.append(clip.path)
    def frame_allowed(path, anchor, _slot):
        if anchor.continuity.get("mode") in {"freeze", "background"} or not in_root(anchor.path):
            return False
        return _safe_allowed(source_allowed, FootageItem(str(path), Path(path).name, anchor.source))
    return resolve_project_continuity(project, Path(history_root) / "footage-blocks" / "continuity",
        missing_paths=missing, checkpoint=checkpoint, source_allowed=frame_allowed,
        duration_probe=duration_probe or probe_video_duration)

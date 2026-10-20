"""Materialize missing visual slots without replanning narration or looping motion."""
from __future__ import annotations

import math
import os
from copy import deepcopy
from dataclasses import replace
from pathlib import Path

from . import stock_media
from .stock_media import prepare_continuity_media
from .timeline import TimelineClip


def _key(path):
    return os.path.normcase(str(Path(path).resolve()))


def _manual_slot(marker):
    duration = float(marker['duration'])
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError('Некорректная длительность пропущенной сцены')
    ids = list(marker.get('voiceSegmentIds', []))
    return TimelineClip('', str(marker.get('narration', '')), str(marker.get('visualQuery', '')),
        duration=duration, voice_segment_id=int(ids[0]) if ids else 0,
        voice_segment_ids=ids, narration_start=float(marker.get('narrationStart', 0)),
        narration_end=float(marker.get('narrationEnd', 0)), minimum_source_duration=duration)


def resolve_project_continuity(project, output_root, *, missing_paths=(), duration_probe=None,
                               checkpoint=None, source_allowed=None):
    """Fill saved manual slots or missing files, preserving one clip per beat.

    Previous accepted footage supplies its last displayed frame. Leading gaps
    use the next accepted footage's first frame. If no permitted image exists,
    generate a neutral background rather than invent an unrelated event. All
    work is staged in memory; an encoding/cancellation failure leaves the plan
    untouched. Existing renderers receive ordinary silent CFR MP4s.
    """
    checkpoint = checkpoint or (lambda: None)
    duration_probe = duration_probe or (lambda path: stock_media._inspect(path)[0])
    source_allowed = source_allowed or (lambda _path, _anchor, _slot: True)
    total = len(project.clips) + len(project.manual_replacements)
    markers = {}
    for marker in project.manual_replacements:
        position = int(marker['sceneIndex'])
        if position in markers or not 0 <= position < total:
            raise ValueError('Некорректный порядок пропущенных сцен')
        markers[position] = marker
    existing = iter(project.clips)
    slots = [_manual_slot(markers[i]) if i in markers else next(existing) for i in range(total)]
    missing = {_key(path) for path in missing_paths}
    lengths = {}
    healthy = []
    gaps = []
    for i, clip in enumerate(slots):
        checkpoint()
        path = Path(clip.path)
        length = 0.0
        if clip.path and path.is_file() and _key(path) not in missing and i not in markers:
            key = _key(path)
            if key not in lengths:
                try:
                    lengths[key] = float(duration_probe(path))
                except InterruptedError:
                    raise
                except (OSError, ValueError, RuntimeError):
                    lengths[key] = 0.0
            length = lengths[key]
        if math.isfinite(length) and length > max(.05, float(clip.source_start)):
            healthy.append(i)
        else:
            gaps.append(i)
    if not gaps:
        return 0
    result = list(slots)
    for i in gaps:
        checkpoint()
        slot = slots[i]
        # Prefer earlier accepted images; never chain holds into fake new footage.
        anchors = sorted(healthy, key=lambda n: (n > i, abs(n - i)))
        prepared = None
        anchor = None
        frame_at = 0.0
        for position in anchors:
            checkpoint()
            candidate = slots[position]
            length = lengths[_key(candidate.path)]
            frame_at = float(candidate.source_start)
            if position < i:
                frame_at = max(0.0, min(length, frame_at + float(candidate.duration)) - 1 / 30)
            try:
                prepared = prepare_continuity_media(Path(candidate.path), Path(output_root),
                    duration=float(slot.duration), aspect_ratio=project.aspect_ratio, frame_at=frame_at)
                if not source_allowed(prepared, candidate, slot):
                    prepared = None
                    continue
            except InterruptedError:
                raise
            except (OSError, ValueError, RuntimeError):
                prepared = None
                continue
            anchor = candidate
            break
        if prepared is None:
            prepared = prepare_continuity_media(None, Path(output_root),
                duration=float(slot.duration), aspect_ratio=project.aspect_ratio)
        result[i] = replace(slot, path=str(prepared), source_start=0.0,
            source=anchor.source if anchor else 'generated', score=0.0,
            source_family=anchor.source_family if anchor else '', reused=True,
            fallback_level='CONTINUITY_HOLD' if anchor else 'CONTINUITY_BACKGROUND',
            minimum_source_duration=float(slot.duration),
            stock_provenance=deepcopy(anchor.stock_provenance) if anchor else {},
            position_rotation_reason='удержание кадра до следующего найденного футажа',
            continuity={'mode': 'freeze' if anchor else 'background',
                'anchorFamily': anchor.source_family if anchor else '',
                'anchorPath': anchor.path if anchor else '', 'frameAt': frame_at if anchor else 0.0,
                'reason': 'no_eligible_footage', 'sourceSelectedDuration': 0.0})
    checkpoint()
    project.clips = result
    project.manual_replacements = []
    return len(gaps)

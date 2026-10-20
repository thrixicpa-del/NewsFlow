from __future__ import annotations

import difflib
import hashlib
import json
import os
import re
import subprocess
import tempfile
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

from .config import app_data_root
from .timeline import fallback_visual_query, ffmpeg_executable, probe_media_duration

VOICE_MAP_SCHEMA_VERSION = 1
_SOFT_MAX_SEGMENT_SECONDS = 6.8
_HARD_MAX_SEGMENT_SECONDS = 10.0
_MIN_RECONCILIATION_COVERAGE = 0.78
_TOKEN_RE = re.compile(r"[\w]+(?:[-'’][\w]+)*", re.UNICODE)


@dataclass(frozen=True)
class TimedObservation:
    text: str
    start: float
    end: float
    confidence: float = 0.0
    kind: str = "segment"


@dataclass(frozen=True)
class AlignmentResult:
    engine: str
    observations: list[TimedObservation]
    confidence: float = 0.0


class AlignmentEngine(Protocol):
    name: str

    def availability(self) -> tuple[bool, str]: ...

    def align(self, context: VoiceMapContext) -> AlignmentResult: ...


@dataclass(frozen=True)
class VoiceMapContext:
    production_item_id: str
    scenario_index: int
    title: str
    script: str
    audio_path: Path
    audio_duration: float = 0.0
    storage_root: Path | None = None
    tombstoned: bool = False


@dataclass(frozen=True)
class VoiceMapStatus:
    state: str
    label: str
    path: str = ""
    reason: str = ""
    data: dict = field(default_factory=dict)
    reused: bool = False


@dataclass(frozen=True)
class _CanonicalToken:
    text: str
    start_char: int
    end_char: int
    start: float
    end: float
    confidence: float


def _normalise_token(value: str) -> str:
    return value.casefold().replace("ё", "е")


def _normalise_script(value: str) -> str:
    return " ".join(str(value or "").split())


def script_sha256(script: str) -> str:
    return hashlib.sha256(str(script).encode("utf-8")).hexdigest()


def audio_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _storage_root(context: VoiceMapContext) -> Path:
    return Path(context.storage_root) if context.storage_root else app_data_root() / "voice-maps"


def voice_map_path(context: VoiceMapContext) -> Path:
    identity = str(context.production_item_id).strip()
    if not identity:
        raise ValueError("VoiceMap requires a ProductionItem ID")
    name = hashlib.sha256(identity.encode("utf-8")).hexdigest()
    return _storage_root(context) / f"{name}.voice-map.json"


def _duration(context: VoiceMapContext) -> float:
    value = float(context.audio_duration or 0.0)
    return value if value > 0.0 else probe_media_duration(Path(context.audio_path))


def _token_spans(script: str) -> list[tuple[str, int, int]]:
    return [(match.group(0), match.start(), match.end()) for match in _TOKEN_RE.finditer(script)]


def _segment_text(script: str, tokens: list[tuple[str, int, int]], start: int, end: int) -> tuple[str, int, int]:
    start_char = tokens[start][1]
    end_char = tokens[end][2]
    if end + 1 < len(tokens):
        between = script[end_char:tokens[end + 1][1]]
        end_char += len(between.rstrip())
    else:
        end_char = len(script)
    return script[start_char:end_char].strip(), start_char, end_char


def timed_text_for_interval(payload: dict, start: float, end: float) -> str | None:
    """Read measured word ownership without inventing times or changing the map.

    A word belongs to the interval where it starts, including a boundary-crossing
    word only once. Maps without word observations retain the approximate path.
    """
    alignment = payload.get("alignment")
    if alignment is None:
        return None
    words = alignment.get("words") if isinstance(alignment, dict) else None
    script = " ".join(str(segment.get("text", "")).strip() for segment in payload["segments"])
    spans = _token_spans(script)
    if (not isinstance(words, list) or len(words) != len(spans)
            or any(not isinstance(word, dict)
                   or _normalise_token(str(word.get("text", ""))) != _normalise_token(token[0])
                   for word, token in zip(words, spans))):
        raise ValueError("VoiceMap measured words do not cover the canonical transcript")
    indices = [index for index, word in enumerate(words) if start <= float(word["start"]) < end]
    return _segment_text(script, spans, indices[0], indices[-1])[0] if indices else ""


def _boundary_score(script: str, left_end: int, right_start: int) -> int:
    punctuation = script[left_end:right_start]
    if re.search(r"[.!?…]", punctuation):
        return 4
    if re.search(r"[;:]", punctuation):
        return 3
    if re.search(r"[,—–-]", punctuation):
        return 2
    return 0


def _choose_boundary(
    script: str,
    spans: list[tuple[str, int, int]],
    timed: list[_CanonicalToken],
    start_index: int,
    final_index: int,
) -> int:
    start_time = 0.0 if start_index == 0 else timed[start_index - 1].end
    if timed[final_index].end - start_time <= _SOFT_MAX_SEGMENT_SECONDS:
        return final_index
    candidates: list[tuple[int, float, int]] = []
    for index in range(start_index, final_index):
        duration = timed[index].end - start_time
        if duration > _SOFT_MAX_SEGMENT_SECONDS:
            break
        if duration < 2.8:
            continue
        score = _boundary_score(script, spans[index][2], spans[index + 1][1])
        candidates.append((score, abs(duration - 4.8), index))
    if candidates:
        sentence = [item for item in candidates if item[0] >= 4]
        pool = sentence or candidates
        return min(pool, key=lambda item: (-item[0], item[1]))[2]
    for index in range(start_index, final_index):
        if timed[index].end - start_time >= 4.8:
            return index
    return final_index


def _segments_from_word_observations(
    script: str,
    timed: list[_CanonicalToken],
    duration: float,
) -> list[dict]:
    spans = _token_spans(script)
    result: list[dict] = []
    start_index = 0
    cursor = 0.0
    while start_index < len(timed):
        end_index = _choose_boundary(script, spans, timed, start_index, len(timed) - 1)
        end_time = duration if end_index == len(timed) - 1 else timed[end_index].end
        text, char_start, char_end = _segment_text(script, spans, start_index, end_index)
        segment_duration = round(end_time - cursor, 3)
        segment = {
            "id": len(result) + 1,
            "start": round(cursor, 3),
            "end": round(end_time, 3),
            "duration": segment_duration,
            "text": text,
            "visualQuery": fallback_visual_query(text),
            "scriptCharStart": char_start,
            "scriptCharEnd": char_end,
            "confidence": round(
                sum(item.confidence for item in timed[start_index:end_index + 1])
                / (end_index - start_index + 1),
                4,
            ),
        }
        if segment_duration > _SOFT_MAX_SEGMENT_SECONDS:
            segment["boundaryCondition"] = "no natural boundary within preferred maximum"
        result.append(segment)
        cursor = end_time
        start_index = end_index + 1
    return result


def _reconcile_word_observations(
    script: str,
    observations: list[TimedObservation],
    duration: float,
) -> tuple[list[dict], list[dict], float]:
    canonical = _token_spans(script)
    observed_tokens: list[tuple[str, TimedObservation]] = []
    for observation in observations:
        tokens = _TOKEN_RE.findall(observation.text)
        if observation.kind != "word" or len(tokens) != 1:
            raise ValueError("alignment engine did not provide real word timing evidence")
        observed_tokens.append((tokens[0], observation))
    matcher = difflib.SequenceMatcher(
        None,
        [_normalise_token(item[0]) for item in canonical],
        [_normalise_token(item[0]) for item in observed_tokens],
        autojunk=False,
    )
    mapping: dict[int, int] = {}
    for block in matcher.get_matching_blocks():
        for offset in range(block.size):
            mapping[block.a + offset] = block.b + offset
    coverage = len(mapping) / max(1, len(canonical))
    if coverage < _MIN_RECONCILIATION_COVERAGE or len(mapping) != len(canonical):
        raise ValueError(f"canonical reconciliation coverage is only {coverage:.1%}")
    timed: list[_CanonicalToken] = []
    words: list[dict] = []
    for index, (text, start_char, end_char) in enumerate(canonical):
        observation = observed_tokens[mapping[index]][1]
        if observation.end <= observation.start or observation.start < 0.0:
            raise ValueError("alignment observations are not positive and monotonic")
        if timed and observation.start < timed[-1].start:
            raise ValueError("alignment observations are not positive and monotonic")
        timed.append(_CanonicalToken(
            text=text,
            start_char=start_char,
            end_char=end_char,
            start=float(observation.start),
            end=float(observation.end),
            confidence=float(observation.confidence or 0.0),
        ))
        words.append({
            "text": text,
            "start": round(float(observation.start), 3),
            "end": round(float(observation.end), 3),
            "confidence": round(float(observation.confidence or 0.0), 4),
        })
    if timed[-1].end > duration + 0.25:
        raise ValueError("alignment observation exceeds audio duration")
    return _segments_from_word_observations(script, timed, duration), words, coverage


def _reconcile_phrase_observations(
    script: str,
    observations: list[TimedObservation],
    duration: float,
) -> tuple[list[dict], float]:
    canonical = _token_spans(script)
    observed_tokens: list[tuple[str, int]] = []
    for observation_index, observation in enumerate(observations):
        if observation.end <= observation.start or observation.start < 0.0:
            raise ValueError("alignment observations are not positive and monotonic")
        if observation_index and observation.start < observations[observation_index - 1].start:
            raise ValueError("alignment observations are not positive and monotonic")
        observed_tokens.extend(
            (token, observation_index) for token in _TOKEN_RE.findall(observation.text)
        )
    matcher = difflib.SequenceMatcher(
        None,
        [_normalise_token(item[0]) for item in canonical],
        [_normalise_token(item[0]) for item in observed_tokens],
        autojunk=False,
    )
    mapping: dict[int, int] = {}
    for block in matcher.get_matching_blocks():
        for offset in range(block.size):
            mapping[block.a + offset] = observed_tokens[block.b + offset][1]
    coverage = len(mapping) / max(1, len(canonical))
    if coverage < _MIN_RECONCILIATION_COVERAGE or len(mapping) != len(canonical):
        raise ValueError(f"canonical reconciliation coverage is only {coverage:.1%}")
    ranges: list[tuple[int, int, TimedObservation]] = []
    for observation_index, observation in enumerate(observations):
        indices = [index for index, mapped in mapping.items() if mapped == observation_index]
        if not indices:
            continue
        ranges.append((min(indices), max(indices), observation))
    if not ranges or ranges[0][0] != 0 or ranges[-1][1] != len(canonical) - 1:
        raise ValueError("canonical reconciliation did not cover the scenario boundaries")
    cursor_index = 0
    cursor_time = 0.0
    segments: list[dict] = []
    for range_index, (start_index, end_index, observation) in enumerate(ranges):
        if start_index != cursor_index:
            raise ValueError("canonical reconciliation produced overlapping phrase ranges")
        end_time = duration if range_index == len(ranges) - 1 else float(observation.end)
        item_duration = end_time - cursor_time
        if item_duration > _SOFT_MAX_SEGMENT_SECONDS:
            raise ValueError("segment-only alignment has no safe word boundary within preferred maximum")
        text, char_start, char_end = _segment_text(script, canonical, start_index, end_index)
        segment = {
            "id": len(segments) + 1,
            "start": round(cursor_time, 3),
            "end": round(end_time, 3),
            "duration": round(item_duration, 3),
            "text": text,
            "visualQuery": fallback_visual_query(text),
            "scriptCharStart": char_start,
            "scriptCharEnd": char_end,
            "confidence": round(float(observation.confidence or 0.0), 4),
        }
        if segments and item_duration < 2.8 and end_time - segments[-1]["start"] <= _SOFT_MAX_SEGMENT_SECONDS:
            previous = segments[-1]
            previous.update({
                "end": round(end_time, 3),
                "duration": round(end_time - previous["start"], 3),
                "text": f"{previous['text']} {text}",
                "visualQuery": fallback_visual_query(f"{previous['text']} {text}"),
                "scriptCharEnd": char_end,
                "confidence": round((previous["confidence"] + segment["confidence"]) / 2, 4),
            })
        else:
            segments.append(segment)
        cursor_index = end_index + 1
        cursor_time = end_time
    for index, segment in enumerate(segments, 1):
        segment["id"] = index
    return segments, coverage


def _natural_units(script: str) -> list[str]:
    sentences = [item.strip() for item in re.split(r"(?<=[.!?…])\s+", script) if item.strip()]
    return sentences or ([script] if script else [])


def _split_unit(unit: str, max_words: int) -> list[str]:
    if len(_TOKEN_RE.findall(unit)) <= max_words:
        return [unit]
    clauses = [item.strip() for item in re.split(r"(?<=[,;:—–])\s+", unit) if item.strip()]
    if len(clauses) > 1 and all(len(_TOKEN_RE.findall(item)) <= max_words for item in clauses):
        return clauses
    words = unit.split()
    return [" ".join(words[index:index + max_words]) for index in range(0, len(words), max_words)]


def _approximate_segments(script: str, duration: float) -> list[dict]:
    words = _TOKEN_RE.findall(script)
    if not words:
        raise ValueError("VoiceMap requires a non-empty canonical scenario")
    seconds_per_word = duration / len(words)
    max_words = max(1, int(_SOFT_MAX_SEGMENT_SECONDS / max(0.05, seconds_per_word)))
    units = [piece for unit in _natural_units(script) for piece in _split_unit(unit, max_words)]
    merged: list[str] = []
    for unit in units:
        estimated = len(_TOKEN_RE.findall(unit)) * seconds_per_word
        if merged:
            combined = (len(_TOKEN_RE.findall(merged[-1])) + len(_TOKEN_RE.findall(unit))) * seconds_per_word
            if estimated < 3.0 and combined <= _SOFT_MAX_SEGMENT_SECONDS:
                merged[-1] = f"{merged[-1]} {unit}"
                continue
        merged.append(unit)
    total_words = sum(len(_TOKEN_RE.findall(item)) for item in merged)
    script_cursor = 0
    elapsed = 0.0
    result: list[dict] = []
    for index, text in enumerate(merged):
        start_char = script.find(text, script_cursor)
        if start_char < 0:
            start_char = script_cursor
        end_char = start_char + len(text)
        script_cursor = end_char
        end = duration if index == len(merged) - 1 else elapsed + duration * (
            len(_TOKEN_RE.findall(text)) / max(1, total_words)
        )
        segment_duration = round(end - elapsed, 3)
        segment = {
            "id": index + 1,
            "start": round(elapsed, 3),
            "end": round(end, 3),
            "duration": segment_duration,
            "text": text,
            "visualQuery": fallback_visual_query(text),
            "scriptCharStart": start_char,
            "scriptCharEnd": end_char,
            "confidence": 0.0,
        }
        if segment_duration > _SOFT_MAX_SEGMENT_SECONDS:
            segment["boundaryCondition"] = "insufficient canonical word boundaries for audio duration"
        result.append(segment)
        elapsed = end
    return result


def _base_payload(context: VoiceMapContext, duration: float) -> dict:
    return {
        "schemaVersion": VOICE_MAP_SCHEMA_VERSION,
        "productionItemId": context.production_item_id,
        "scenarioIndex": context.scenario_index,
        "title": context.title,
        "audioPath": str(Path(context.audio_path)),
        "audioDuration": round(duration, 3),
        "scriptSha256": script_sha256(context.script),
        "audioSha256": audio_sha256(Path(context.audio_path)),
        "createdAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def _aligned_payload(context: VoiceMapContext, result: AlignmentResult, duration: float) -> dict:
    script = _normalise_script(context.script)
    word_level = bool(result.observations) and all(
        item.kind == "word" and len(_TOKEN_RE.findall(item.text)) == 1
        for item in result.observations
    )
    if word_level:
        segments, words, coverage = _reconcile_word_observations(script, result.observations, duration)
    else:
        segments, coverage = _reconcile_phrase_observations(script, result.observations, duration)
        words = []
    payload = {
        **_base_payload(context, duration),
        "timingMode": "aligned",
        "alignmentEngine": result.engine,
        "alignmentConfidence": round(min(float(result.confidence or 0.0), coverage), 4),
        "segments": segments,
    }
    if words:
        payload["alignment"] = {"words": words}
    return payload


def _approximate_payload(context: VoiceMapContext, duration: float, reason: str) -> dict:
    return {
        **_base_payload(context, duration),
        "timingMode": "approximate",
        "alignmentEngine": "newsflow-fallback",
        "alignmentConfidence": 0.0,
        "alignmentUnavailableReason": reason,
        "segments": _approximate_segments(_normalise_script(context.script), duration),
    }


def _validate_payload(context: VoiceMapContext, payload: dict, *, compare_hashes: bool = True) -> None:
    if int(payload.get("schemaVersion", 0)) != VOICE_MAP_SCHEMA_VERSION:
        raise ValueError("VoiceMap schema is unsupported")
    if str(payload.get("productionItemId", "")) != context.production_item_id:
        raise ValueError("VoiceMap ProductionItem identity mismatch")
    if payload.get("timingMode") not in {"aligned", "approximate"}:
        raise ValueError("VoiceMap timingMode is invalid")
    if compare_hashes:
        if payload.get("scriptSha256") != script_sha256(context.script):
            raise ValueError("VoiceMap script hash is stale")
        if payload.get("audioSha256") != audio_sha256(Path(context.audio_path)):
            raise ValueError("VoiceMap audio hash is stale")
    duration = float(payload.get("audioDuration", 0.0) or 0.0)
    segments = payload.get("segments")
    if duration <= 0.0 or not isinstance(segments, list) or not segments:
        raise ValueError("VoiceMap has no usable duration or segments")
    cursor = 0.0
    canonical_parts: list[str] = []
    for expected_id, segment in enumerate(segments, 1):
        if not isinstance(segment, dict) or int(segment.get("id", 0)) != expected_id:
            raise ValueError("VoiceMap segment identity is invalid")
        start = float(segment.get("start", -1.0))
        end = float(segment.get("end", -1.0))
        item_duration = float(segment.get("duration", -1.0))
        if abs(start - cursor) > 0.02:
            raise ValueError("VoiceMap segments are not contiguous")
        if end <= start or item_duration <= 0.0:
            raise ValueError("VoiceMap segments are not positive and monotonic")
        if abs(item_duration - (end - start)) > 0.02:
            raise ValueError("VoiceMap segment duration is inconsistent")
        if item_duration > _HARD_MAX_SEGMENT_SECONDS and not segment.get("boundaryCondition"):
            raise ValueError("VoiceMap segment exceeds the maximum without boundary evidence")
        canonical_parts.append(str(segment.get("text", "")).strip())
        cursor = end
    tolerance = max(0.05, min(0.25, duration * 0.002))
    if abs(cursor - duration) > tolerance:
        raise ValueError("VoiceMap final segment does not reach the audio duration")
    if " ".join(canonical_parts) != _normalise_script(context.script):
        raise ValueError("VoiceMap canonical transcript coverage is incomplete")
    alignment = payload.get("alignment")
    if alignment is not None:
        words = alignment.get("words") if isinstance(alignment, dict) else None
        if not isinstance(words, list) or not words:
            raise ValueError("VoiceMap word evidence is invalid")
        word_cursor = 0.0
        for word in words:
            if not isinstance(word, dict):
                raise TypeError("VoiceMap word evidence is invalid")
            start = float(word.get("start", -1.0))
            end = float(word.get("end", -1.0))
            if start < word_cursor - 0.01 or end <= start or end > duration + tolerance:
                raise ValueError("VoiceMap word evidence is not positive and monotonic")
            word_cursor = end


def _status_for_payload(path: Path, payload: dict, *, reused: bool = False) -> VoiceMapStatus:
    approximate = payload.get("timingMode") == "approximate"
    return VoiceMapStatus(
        state="approximate" if approximate else "ready",
        label="Приблизительный тайминг" if approximate else "Тайминг готов",
        path=str(path),
        reason=str(payload.get("alignmentUnavailableReason", "")),
        data=payload,
        reused=reused,
    )


def inspect_voice_map(context: VoiceMapContext) -> VoiceMapStatus:
    audio = Path(context.audio_path)
    if not audio.is_file():
        return VoiceMapStatus("waiting", "Ожидает MP3", reason="audio file is missing")
    path = voice_map_path(context)
    if not path.is_file():
        return VoiceMapStatus("missing", "Ожидает MP3", path=str(path), reason="VoiceMap is missing")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise TypeError("VoiceMap JSON root is not an object")
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError) as error:
        return VoiceMapStatus("error", "Ошибка тайминга", path=str(path), reason=f"VoiceMap JSON error: {error}")
    try:
        _validate_payload(context, payload)
    except (OSError, ValueError) as error:
        reason = str(error)
        state = "stale" if any(word in reason.casefold() for word in ("stale", "schema", "identity")) else "error"
        return VoiceMapStatus(
            state,
            "Тайминг устарел" if state == "stale" else "Ошибка тайминга",
            path=str(path),
            reason=reason,
            data=payload,
        )
    return _status_for_payload(path, payload, reused=True)


def _same_current_input(original: VoiceMapContext, current: VoiceMapContext | None) -> bool:
    if current is None or current.tombstoned:
        return False
    if current.production_item_id != original.production_item_id:
        return False
    try:
        return (
            script_sha256(current.script) == script_sha256(original.script)
            and audio_sha256(Path(current.audio_path)) == audio_sha256(Path(original.audio_path))
        )
    except OSError:
        return False


def _atomic_publish(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("w", encoding="utf-8") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass


def ensure_voice_map(
    context: VoiceMapContext,
    *,
    engine: AlignmentEngine | None = None,
    current_context: Callable[[], VoiceMapContext | None] | None = None,
    force: bool = False,
) -> VoiceMapStatus:
    if context.tombstoned:
        raise RuntimeError("VoiceMap identity is deleted")
    if not context.production_item_id.strip():
        raise ValueError("VoiceMap requires a ProductionItem ID")
    if not _normalise_script(context.script):
        raise ValueError("VoiceMap requires a completed canonical scenario")
    if not Path(context.audio_path).is_file():
        raise ValueError("VoiceMap requires an existing audio file")
    if not force:
        cached = inspect_voice_map(context)
        if cached.state in {"ready", "approximate"}:
            return cached
    duration = _duration(context)
    selected_engine: AlignmentEngine = engine or FfmpegWhisperAlignmentEngine()
    available, unavailable_reason = selected_engine.availability()
    if available:
        try:
            payload = _aligned_payload(context, selected_engine.align(context), duration)
        except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as error:
            payload = _approximate_payload(context, duration, str(error))
    else:
        payload = _approximate_payload(context, duration, unavailable_reason or "alignment engine unavailable")
    _validate_payload(context, payload)
    authority = current_context() if current_context else context
    if not _same_current_input(context, authority):
        raise RuntimeError("VoiceMap input was deleted or became stale before publish")
    # Hash the sources again after the potentially expensive engine call and
    # validate the final candidate immediately before the atomic replace.
    _validate_payload(authority, payload)
    target = voice_map_path(context)
    _atomic_publish(target, payload)
    return _status_for_payload(target, payload)


def remove_voice_map(context: VoiceMapContext) -> bool:
    path = voice_map_path(context)
    try:
        path.unlink()
        return True
    except FileNotFoundError:
        return False


class FfmpegWhisperAlignmentEngine:
    name = "ffmpeg-whisper-canonical-v1"

    def __init__(self, *, ffmpeg: str | None = None, model_path: Path | None = None):
        self.ffmpeg = ffmpeg
        configured = str(os.environ.get("NEWSFLOW_WHISPER_MODEL", "")).strip()
        cached = app_data_root() / "models" / "whisper" / "ggml-model.bin"
        self.model_path = Path(model_path) if model_path else (Path(configured) if configured else cached)

    def _ffmpeg(self) -> str:
        return self.ffmpeg or ffmpeg_executable()

    def availability(self) -> tuple[bool, str]:
        if not self.model_path.is_file():
            return False, "Alignment model not configured"
        try:
            result = subprocess.run(
                [self._ffmpeg(), "-hide_banner", "-filters"],
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )
        except (OSError, subprocess.SubprocessError) as error:
            return False, f"FFmpeg alignment capability unavailable: {error}"
        if result.returncode != 0 or not re.search(r"\bwhisper\b", result.stdout):
            return False, "FFmpeg whisper filter is unavailable"
        return True, ""

    @staticmethod
    def _filter_path(path: Path) -> str:
        return str(path).replace("\\", "/").replace(":", "\\:").replace("'", "\\'")

    @staticmethod
    def _extract_observations(value) -> list[TimedObservation]:
        result: list[TimedObservation] = []

        def visit(item) -> None:
            if isinstance(item, list):
                for child in item:
                    visit(child)
                return
            if not isinstance(item, dict):
                return
            text = str(item.get("text", "")).strip()
            offsets = item.get("offsets") if isinstance(item.get("offsets"), dict) else {}
            uses_offsets = bool(offsets) and "start" not in item and "end" not in item
            start = offsets.get("from") if uses_offsets else item.get("start")
            end = offsets.get("to") if uses_offsets else item.get("end")
            if text and start is not None and end is not None:
                scale = 1000.0 if uses_offsets else 1.0
                result.append(TimedObservation(
                    text=text,
                    start=float(start) / scale,
                    end=float(end) / scale,
                    confidence=float(item.get("confidence", item.get("probability", 0.0)) or 0.0),
                    kind="word" if len(_TOKEN_RE.findall(text)) == 1 else "segment",
                ))
            for child in item.values():
                if isinstance(child, (dict, list)):
                    visit(child)

        visit(value)
        unique = {
            (item.text, item.start, item.end): item
            for item in result if item.end > item.start >= 0.0
        }
        return sorted(unique.values(), key=lambda item: (item.start, item.end))

    def align(self, context: VoiceMapContext) -> AlignmentResult:
        available, reason = self.availability()
        if not available:
            raise RuntimeError(reason)
        with tempfile.TemporaryDirectory(prefix="newsflow-voice-map-") as folder:
            destination = Path(folder) / "whisper.json"
            filter_value = (
                "aformat=sample_rates=16000:channel_layouts=mono,"
                f"whisper=model='{self._filter_path(self.model_path)}':language=auto:"
                f"destination='{self._filter_path(destination)}':format=json:max_len=1"
            )
            completed = subprocess.run(
                [
                    self._ffmpeg(),
                    "-nostdin",
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-i",
                    str(context.audio_path),
                    "-af",
                    filter_value,
                    "-f",
                    "null",
                    "-",
                ],
                capture_output=True,
                text=True,
                timeout=max(120, int(_duration(context) * 4)),
                check=False,
            )
            if completed.returncode != 0:
                raise RuntimeError(f"FFmpeg whisper alignment failed: {completed.stderr[-500:]}")
            if not destination.is_file():
                raise RuntimeError("FFmpeg whisper produced no timing JSON")
            raw = destination.read_text(encoding="utf-8").strip()
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                payload = [json.loads(line) for line in raw.splitlines() if line.strip()]
            observations = self._extract_observations(payload)
            if not observations:
                raise RuntimeError("FFmpeg whisper produced no timed observations")
            confidence_values = [item.confidence for item in observations if item.confidence > 0.0]
            confidence = sum(confidence_values) / len(confidence_values) if confidence_values else 0.0
            return AlignmentResult(self.name, observations, confidence)

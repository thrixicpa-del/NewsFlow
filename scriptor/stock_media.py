"""Read-only preparation of user-selected stock files for a montage.

Video trimming retains source dimensions; the timeline owns final scaling.
Images become a slow centered zoom in the requested output aspect ratio.
Durations are rounded up to the next 30 FPS frame (at most one frame).
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import subprocess
import tempfile
from pathlib import Path

from .cutter import cut_single_clip
from .timeline import _proxy_lock, _replace_with_retry, ffmpeg_executable

_VERSION = "stock-media-v2"
_DIMENSIONS = {"16:9": (1920, 1080), "9:16": (1080, 1920), "1:1": (1080, 1080)}
_FPS = 30


def _number(value: float, name: str, *, positive: bool) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{name} must be a finite number")
    value = float(value)
    if not math.isfinite(value) or (value <= 0 if positive else value < 0):
        raise ValueError(f"Invalid {name}")
    return value


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _inspect(path: Path) -> tuple[float, bool, bool]:
    """Read stream headers without the app's persistent health/index stores."""
    result = subprocess.run(
        [ffmpeg_executable(), "-nostdin", "-hide_banner", "-i", str(path)],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30, check=False,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    text = result.stderr or ""
    match = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", text)
    if not match or not re.search(r"Stream[^\r\n]*Video:", text):
        raise ValueError(f"Unreadable video: {path.name}")
    hours, minutes, seconds = match.groups()
    duration = int(hours) * 3600 + int(minutes) * 60 + float(seconds)
    silent = not re.search(r"Stream[^\r\n]*Audio:", text)
    cfr30 = bool(re.search(r"Stream[^\r\n]*Video:[^\r\n]*\b30 fps\b", text))
    return duration, silent, cfr30


def _valid_cached(path: Path, duration: float) -> bool:
    if not path.is_file():
        return False
    try:
        length, silent, fps30 = _inspect(path)
        return silent and fps30 and abs(length - duration) <= .015
    except (ValueError, OSError, subprocess.SubprocessError):
        return False


def _image_video(source: Path, target: Path, frames: int, aspect_ratio: str) -> None:
    width, height = _DIMENSIONS[aspect_ratio]
    # Fit the complete still before animating: center-cropping a portrait to a
    # landscape frame can remove the politician's head. Padding preserves the
    # source composition; the modest zoom then stays within its safe margins.
    filtergraph = (
        f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1,"
        f"zoompan=z='1+0.08*on/{max(1, frames - 1)}':"
        "x='iw/2-iw/zoom/2':y='ih/2-ih/zoom/2':"
        f"d={frames}:s={width}x{height}:fps={_FPS}"
    )
    command = [
        ffmpeg_executable(), "-nostdin", "-hide_banner", "-y", "-i", str(source),
        "-map", "0:v:0", "-an", "-vf", filtergraph, "-frames:v", str(frames),
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
        "-threads", "2", "-filter_threads", "1", "-movflags", "+faststart", str(target),
    ]
    result = subprocess.run(
        command, capture_output=True, text=True, encoding="utf-8", errors="replace", check=False,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    if result.returncode:
        raise RuntimeError(f"Cannot prepare image {source.name}: {(result.stderr or '')[-2500:]}")


def prepare_stock_media(
    source: Path, output_root: Path, *, duration: float, trim: bool = True,
    kind: str = "video", aspect_ratio: str = "16:9", source_start: float = 0.0,
) -> Path:
    """Return an original video or an atomically cached silent derivative.

    ``trim=False`` videos pass through untouched, including their audio and
    original duration. The montage must apply its own interval and audio policy.
    All generated files live below a versioned ``output_root`` subfolder. Originals
    are only read and are never moved, replaced, or added to a media index.
    """
    duration = _number(duration, "duration", positive=True)
    source_start = _number(source_start, "source_start", positive=False)
    if not isinstance(trim, bool):
        raise TypeError("trim must be boolean")
    if kind not in ("video", "image"):
        raise ValueError("kind must be video or image")
    if aspect_ratio not in _DIMENSIONS:
        raise ValueError("Unsupported aspect ratio")
    source = Path(source)
    if not source.is_file():
        raise ValueError(f"Stock source does not exist: {source}")
    if kind == "video" and not trim:
        return source

    if not math.isfinite(duration * _FPS):
        raise ValueError("Duration exceeds frame range")
    frames = max(1, math.ceil(duration * _FPS - 1e-9))
    frame_duration = frames / _FPS
    if kind == "video":
        source_duration, _, _ = _inspect(source)
        if source_start + duration > source_duration + .015:
            raise ValueError("Requested stock interval exceeds source duration")

    source_hash = _sha256(source)
    key = hashlib.sha256(json.dumps({
        "version": _VERSION, "source_sha256": source_hash, "duration": duration.hex(),
        "source_start": source_start.hex(), "aspect_ratio": aspect_ratio, "kind": kind,
    }, sort_keys=True).encode("utf-8")).hexdigest()
    cache = Path(output_root) / _VERSION
    target = cache / f"{key}.mp4"
    # Protect even deliberately chosen cache paths from overwriting an original.
    if target.resolve() == source.resolve():
        raise ValueError("Stock cache would overwrite the original")
    cache.mkdir(parents=True, exist_ok=True)
    with _proxy_lock(target):
        if _valid_cached(target, frame_duration):
            return target
        with tempfile.TemporaryDirectory(prefix=f".{key}-", dir=cache) as temporary:
            staging = Path(temporary)
            if kind == "video":
                prepared = cut_single_clip(source, staging, duration=frame_duration, start=source_start)
            else:
                prepared = staging / "image.mp4"
                _image_video(source, prepared, frames, aspect_ratio)
            if not _valid_cached(prepared, frame_duration):
                raise ValueError("Prepared stock media has an invalid duration or video/audio stream")
            if _sha256(source) != source_hash:
                raise ValueError("Stock source changed during preparation")
            _replace_with_retry(prepared, target)
    return target

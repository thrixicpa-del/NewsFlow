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
_CONTINUITY_VERSION = "continuity-media-v2"
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


def stock_source_dimensions(source: str | Path, kind: str) -> tuple[int, int]:
    """Read original pixels; never consult API metadata or prepared proxies.

    Images must decode in Pillow. Videos must decode their first video frame
    in FFmpeg, which only writes to the null muxer. Unreadable/unknown sources
    raise ValueError and never create persistent health/index records.
    """
    if kind not in ("image", "video"):
        raise ValueError("kind must be video or image")
    source = Path(source)
    if not source.is_file():
        raise ValueError(f"Stock source does not exist: {source.name}")
    if kind == "image":
        from PIL import Image
        try:
            with Image.open(source) as image:
                image.load()
                return image.size
        except (OSError, ValueError, Image.DecompressionBombError) as error:
            raise ValueError(f"Unreadable stock image: {source.name}") from error
    try:
        result = subprocess.run(
            [ffmpeg_executable(), "-nostdin", "-hide_banner", "-threads", "1", "-i", str(source),
             "-map", "0:v:0", "-frames:v", "1", "-an", "-threads", "1", "-f", "null", "-"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30, check=False,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
    except (OSError, RuntimeError, subprocess.SubprocessError) as error:
        raise ValueError(f"Cannot inspect stock video: {source.name}") from error
    match = re.search(
        r"Stream[^\r\n]*Video:[^\r\n]*?(?<![\dA-Za-z])([1-9]\d{0,5})x([1-9]\d{0,5})(?!\d)",
        result.stderr or "",
    )
    if result.returncode or match is None:
        raise ValueError(f"Unreadable stock video dimensions: {source.name}")
    return int(match[1]), int(match[2])


def source_is_hd(source: str | Path, kind: str) -> bool:
    """Video:720x1280 minimum; photo:720 short side and921600 pixels.

    Portrait video is equivalent to landscape. Photos may be square (including
    1080x1080); dimensions always refer to the supplied original source.
    """
    try:
        width, height = stock_source_dimensions(source, kind)
    except ValueError:
        return False
    short, long = sorted((width, height))
    return short >= 720 and (long >= 1280 if kind == "video" else width * height >= 1280 * 720)


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


def _write_continuity_media(source: Path | None, target: Path, frames: int,
                            aspect_ratio: str, frame_at: float) -> None:
    """Encode a literal still, with bounded decoding around the chosen time."""
    width, height = _DIMENSIONS[aspect_ratio]
    ffmpeg = ffmpeg_executable()
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    if source is None:
        inputs = ["-f", "lavfi", "-i", f"color=c=0x101b2a:s={width}x{height}:r={_FPS}"]
    else:
        frozen = target.with_name("frame.png")
        # Retain the last frame at/before frame_at, including a final frame
        # whose display interval extends to the source duration. Decoding is
        # limited to about one second and only one PNG occupies staging.
        seek = max(0.0, frame_at - 1.0)
        offset = frame_at - seek
        filtergraph = (
            f"select='lte(t,{offset:.12f})',"
            f"scale={width}:{height}:force_original_aspect_ratio=increase,"
            f"crop={width}:{height},setsar=1"
        )
        capture = subprocess.run(
            [ffmpeg, "-nostdin", "-hide_banner", "-y", "-threads", "1", "-ss", str(seek),
             "-t", str(offset + .1), "-i", str(source), "-map", "0:v:0", "-an", "-vf", filtergraph,
             "-vsync", "0", "-update", "1", "-threads", "1", "-filter_threads", "1", str(frozen)],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30,
            check=False, creationflags=flags,
        )
        if capture.returncode or not frozen.is_file():
            raise RuntimeError(f"Cannot freeze source frame: {(capture.stderr or '')[-1500:]}")
        inputs = ["-loop", "1", "-framerate", str(_FPS), "-i", str(frozen)]
    result = subprocess.run(
        [ffmpeg, "-nostdin", "-hide_banner", "-y", *inputs, "-map", "0:v:0", "-an",
         "-frames:v", str(frames), "-r", str(_FPS), "-c:v", "libx264", "-preset", "veryfast",
         "-crf", "20", "-pix_fmt", "yuv420p", "-threads", "2", "-filter_threads", "1",
         "-movflags", "+faststart", str(target)],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=max(30, min(300, frames / _FPS * 3)), check=False, creationflags=flags,
    )
    if result.returncode:
        raise RuntimeError(f"Cannot prepare continuity media: {(result.stderr or '')[-1500:]}")


def prepare_continuity_media(source: Path | None, output_root: Path, *, duration: float,
                             aspect_ratio: str = "16:9", frame_at: float = 0.0) -> Path:
    """Return silent CFR30 hold/neutral media without altering its source.

    ``source=None`` explicitly requests a plain dark blue background. A video
    source freezes the frame displayed at frame_at; unreadable/out-of-range
    sources raise rather than silently becoming neutral. Output is rounded up
    by at most one30fps frame and cached with source/output content hashes.
    """
    duration = _number(duration, "duration", positive=True)
    frame_at = _number(frame_at, "frame_at", positive=False)
    if aspect_ratio not in _DIMENSIONS:
        raise ValueError("Unsupported aspect ratio")
    if not math.isfinite(duration * _FPS):
        raise ValueError("Duration exceeds frame range")
    frames = max(1, math.ceil(duration * _FPS - 1e-9))
    frame_duration = frames / _FPS
    source = Path(source) if source is not None else None
    if source is not None and not source.is_file():
        raise ValueError(f"Continuity source does not exist: {source.name}")
    source_hash = _sha256(source) if source is not None else None
    if source is not None:
        length, _, _ = _inspect(source)
        if frame_at >= length:
            raise ValueError("Continuity frame exceeds source duration")
    key = hashlib.sha256(json.dumps({
        "version": _CONTINUITY_VERSION, "source_sha256": source_hash,
        "duration": duration.hex(), "frame_at": frame_at.hex(), "aspect_ratio": aspect_ratio,
    }, sort_keys=True).encode("utf-8")).hexdigest()
    cache = Path(output_root) / _CONTINUITY_VERSION
    target, manifest = cache / f"{key}.mp4", cache / f"{key}.json"
    if source is not None and target.resolve() == source.resolve():
        raise ValueError("Continuity cache would overwrite the source")
    cache.mkdir(parents=True, exist_ok=True)
    with _proxy_lock(target):
        if target.is_symlink() or manifest.is_symlink():
            raise ValueError("Continuity cache cannot use symbolic links")
        try:
            saved = json.loads(manifest.read_text(encoding="utf-8"))
            valid = (target.is_file() and isinstance(saved, dict)
                     and saved.get("output_sha256") == _sha256(target)
                     and _valid_cached(target, frame_duration))
        except (OSError, ValueError):
            valid = False
        if valid:
            if source is not None and _sha256(source) != source_hash:
                raise ValueError("Continuity source changed during preparation")
            return target
        with tempfile.TemporaryDirectory(prefix=f".{key}-", dir=cache) as temporary:
            staging = Path(temporary)
            prepared = staging / "continuity.mp4"
            _write_continuity_media(source, prepared, frames, aspect_ratio, frame_at)
            if not _valid_cached(prepared, frame_duration):
                raise ValueError("Invalid continuity duration or video/audio stream")
            if source is not None and _sha256(source) != source_hash:
                raise ValueError("Continuity source changed during preparation")
            metadata = staging / "manifest.json"
            metadata.write_text(json.dumps({"output_sha256": _sha256(prepared), "frames": frames}),
                                encoding="utf-8")
            _replace_with_retry(prepared, target)
            _replace_with_retry(metadata, manifest)
    return target

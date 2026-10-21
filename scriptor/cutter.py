from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from .core import safe_filename
from .timeline import ffmpeg_executable


def build_cut_command(source: Path, target_pattern: Path, duration: float = 6.0,
                      fps: int = 30, bitrate: str = "4M") -> list[str]:
    """Return the uniform, silent H.264 segmentation command used by NewsFlow."""
    if duration <= 0:
        raise ValueError("Длительность клипа должна быть больше нуля")
    if fps < 1 or fps > 120:
        raise ValueError("FPS должен быть от 1 до 120")
    return [
        ffmpeg_executable(), "-hide_banner", "-y", "-i", str(source),
        "-map", "0:v:0", "-an", "-vf", f"fps={fps}", "-c:v", "libx264",
        "-preset", "medium", "-b:v", bitrate, "-maxrate", bitrate, "-bufsize", "8M",
        "-pix_fmt", "yuv420p", "-force_key_frames", f"expr:gte(t,n_forced*{duration:g})",
        "-f", "segment", "-segment_time", f"{duration:g}", "-reset_timestamps", "1",
        "-movflags", "+faststart", str(target_pattern),
    ]


def cut_sources(sources: list[str], output_root: Path, duration: float = 6.0,
                fps: int = 30, bitrate: str = "4M", progress=None) -> list[Path]:
    """Make normalized silent clips; each source gets its own recoverable folder."""
    output_root = Path(output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    created: list[Path] = []
    flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    # FFmpeg detects containers by content; an extension whitelist rejects
    # valid camera/stock media such as OGV, TS and extensionless recordings.
    valid = [Path(raw) for raw in sources if Path(raw).is_file()]
    if not valid:
        raise ValueError("Добавьте хотя бы один видеофайл для нарезки")
    for number, source in enumerate(valid, 1):
        folder = output_root / safe_filename(source.stem)
        folder.mkdir(parents=True, exist_ok=True)
        pattern = folder / f"{safe_filename(source.stem)}_%04d.mp4"
        if progress:
            progress({"current": number, "total": len(valid), "source": source.name, "stage": "cutting"})
        result = subprocess.run(build_cut_command(source, pattern, duration, fps, bitrate), capture_output=True,
                                text=True, encoding="utf-8", errors="replace", creationflags=flags, check=False)
        if result.returncode:
            detail = (result.stderr or result.stdout or "FFmpeg завершился с ошибкой")[-2500:]
            raise RuntimeError(f"{source.name}: {detail}")
        created.extend(sorted(folder.glob("*.mp4")))
        if progress:
            progress({"current": number, "total": len(valid), "source": source.name,
                      "stage": "done", "clips": len(created)})
    return created


def cut_single_clip(source: Path, output_root: Path, duration: float = 6.0,
                    fps: int = 30, bitrate: str = "4M", start: float = 0.0) -> Path:
    """Create exactly one normalized silent clip from an external source.

    Automatic footage fallback must never segment an entire two-hour web video
    just to use one shot.  The source is retained separately; this helper reads
    only the requested short interval and writes a deterministic 30 FPS MP4.
    """
    source = Path(source)
    if not source.is_file():
        raise ValueError("Добавьте существующий видеофайл")
    if duration <= 0:
        raise ValueError("Длительность клипа должна быть больше нуля")
    if fps < 1 or fps > 120:
        raise ValueError("FPS должен быть от 1 до 120")
    output_root = Path(output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    target = output_root / f"{safe_filename(source.stem)}_short.mp4"
    partial = target.with_suffix(".partial.mp4")
    flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    command = [
        ffmpeg_executable(), "-hide_banner", "-y", "-ss", f"{max(0.0, start):.3f}", "-i", str(source),
        "-t", f"{duration:.3f}", "-map", "0:v:0", "-an", "-vf", f"fps={fps}",
        "-c:v", "libx264", "-preset", "veryfast", "-b:v", bitrate, "-maxrate", bitrate,
        "-bufsize", "8M", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(partial),
    ]
    result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace",
                            creationflags=flags, check=False)
    if result.returncode:
        detail = (result.stderr or result.stdout or "FFmpeg завершился с ошибкой")[-2500:]
        raise RuntimeError(f"{source.name}: {detail}")
    partial.replace(target)
    return target
